# HTTP GraphQL transport

## Objectives

After this lesson, you will be able to:

- Describe the path of a GraphQL request over HTTP in Spring for GraphQL.
- Configure the HTTP endpoint with Spring Boot.
- Distinguish between POST and GET, and understand the limitations of each method.
- Read and construct a request payload with `query`, `operationName`, `variables`, and `extensions`.
- Understand the roles of `Content-Type`, `Accept`, and response media types.
- Distinguish between the implementations on Spring MVC and Spring WebFlux.
- Use `WebGraphQlInterceptor` to add metadata to the GraphQL execution context.
- Integrate HTTP transport with security, CORS, request limits, and observability.
- Test an HTTP endpoint using `HttpGraphQlTester`.

## 1. What is HTTP GraphQL transport?

GraphQL defines a query language, schema, and how operations are executed. HTTP GraphQL transport specifies how clients send operations to the server and receive results over HTTP.

In a Spring for GraphQL application, clients typically send requests to a single endpoint, such as `/graphql`. This endpoint can accept multiple types of operations:

- Query to read data.
- Mutation to modify data.

Subscriptions require a transport that supports streaming, such as WebSocket or RSocket. Standard HTTP request-response returns one response per request, so it is not suitable for maintaining a long-lived event stream.

Example of a client sending a Query:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
~~~

The server executes the operation according to the schema and returns a JSON response:

~~~json
{
  "data": {
    "book": {
      "id": "b-01",
      "title": "GraphQL in Practice"
    }
  }
}
~~~

The HTTP transport is responsible for receiving requests, forwarding the content to GraphQL execution, and writing the result to the HTTP response. It does not replace the schema, resolvers, or business services.

## 2. HTTP processing flow in Spring for GraphQL

Spring for GraphQL separates GraphQL execution from the web transport layer. An HTTP request passes through the following main components:

~~~mermaid
flowchart TD
    A[GraphQL client] --> B[HTTP endpoint /graphql]
    B --> C[GraphQlHttpHandler]
    C --> D[WebGraphQlHandler]
    D --> E[WebGraphQlInterceptor chain]
    E --> F[ExecutionGraphQlService]
    F --> G[GraphQL Java engine]
    G --> H[DataFetcher / annotated controller]
    H --> I[Service and repository]
    I --> G
    G --> J[GraphQL response]
    J --> C
    C --> K[HTTP response]
~~~

Role of each layer:

| Component | Responsibility |
|---|---|
| HTTP endpoint | Receives requests at the configured URL |
| `GraphQlHttpHandler` | Adapter between HTTP and the GraphQL handler |
| `WebGraphQlHandler` | Processes requests at the Spring GraphQL layer and runs the interceptor chain |
| `WebGraphQlInterceptor` | Adds metadata, inspects, or transforms requests/responses |
| `ExecutionGraphQlService` | Coordinates GraphQL execution |
| GraphQL Java | Validates operations, resolves fields, and creates `ExecutionResult` |
| Controller/DataFetcher | Provides data for each field |

Spring Boot auto-configures the HTTP transport components when the appropriate starter is present. The application usually only needs to declare the schema, controllers, and endpoint configuration.

## 3. Configuring the HTTP endpoint in Spring Boot

With Spring Boot, the default GraphQL HTTP endpoint is typically `/graphql`. It can be changed using the `spring.graphql.path` property.

Example:

~~~yaml
spring:
  graphql:
    path: /api/graphql
~~~

When the application starts, clients send requests to:

~~~text
http://localhost:8080/api/graphql
~~~

If `spring.graphql.path` is not declared, the default endpoint is:

~~~text
http://localhost:8080/graphql
~~~

Spring Boot supports integrating Spring for GraphQL on both web stacks:

- Spring MVC based on the Servlet API.
- Spring WebFlux based on the reactive web stack.

Use the starter and web stack that suit your application. There is no need to create a custom REST controller just to accept GraphQL JSON if auto-configuration already provides the HTTP handler.

Example of commonly used Maven dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-graphql</artifactId>
</dependency>

<!-- Choose a web stack suitable for the application -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

If the application uses WebFlux, use `spring-boot-starter-webflux` instead of the MVC starter. Avoid including both web starters just to enable GraphQL; control the web application type and runtime configuration according to the chosen architecture.

## 4. POST request: the common way to send GraphQL operations

POST is the common way to send GraphQL operations over HTTP. The request body is typically a JSON object with the following properties:

| Property | Required? | Meaning |
|---|---|---|
| `query` | Yes | GraphQL document containing the operation |
| `operationName` | Conditional | Selects which operation to execute when the document contains multiple operations |
| `variables` | No | Maps variable names to values |
| `extensions` | No | Extension metadata, such as the persisted query protocol |

Example POST using curl:

~~~bash
curl -X POST http://localhost:8080/graphql \
  -H "Content-Type: application/json" \
  -H "Accept: application/graphql-response+json, application/json" \
  -d '{
    "query": "query BookById($id: ID!) { book(id: $id) { id title } }",
    "operationName": "BookById",
    "variables": {
      "id": "b-01"
    }
  }'
~~~

In the example:

- `Content-Type: application/json` indicates the body is JSON.
- `Accept` lists the response media types that the client can handle.
- `query` contains the operation.
- `operationName` identifies the operation named `BookById`.
- `variables` passes the ID separately from the GraphQL document.

Using variables helps reuse the same document with different values, reduces query string concatenation on the client, and makes input data types explicit.

### Example response

If the book exists, the server may return:

~~~json
{
  "data": {
    "book": {
      "id": "b-01",
      "title": "GraphQL in Practice"
    }
  }
}
~~~

If a field throws an error during execution, the GraphQL response may contain both `data` and `errors`:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Book was not found",
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

Clients need to inspect both `data` and `errors`. Do not assume that every business error prevents the HTTP request from receiving a JSON response.

## 5. operationName when a document has multiple operations

A GraphQL document can declare multiple operations:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
  }
}

query LatestBooks {
  latestBooks {
    id
    title
  }
}
~~~

When sending a document with multiple operations, the client must specify which operation to run using `operationName`:

~~~json
{
  "query": "query BookById($id: ID!) { book(id: $id) { id title } } query LatestBooks { latestBooks { id title } }",
  "operationName": "LatestBooks"
}
~~~

If the document contains only one operation, `operationName` can be omitted. If there are multiple operations without specifying which operation to execute, GraphQL cannot safely choose one, and the request will fail during validation/execution preparation.

You should give operations meaningful names to make logging, tracing, and performance analysis easier. Avoid using the same generic name such as `Query1` for every request.

## 6. GET requests and limitations of GET

Some GraphQL servers support sending Queries via HTTP GET. Parameters are placed in the URL:

- `query`: URL-encoded GraphQL document.
- `operationName`: operation name if needed.
- `variables`: JSON encoded as a string.
- `extensions`: JSON metadata if supported.

Example of the request shape:

~~~http
GET /graphql?query=query%20BookById%28%24id%3AID%21%29%7Bbook%28id%3A%24id%29%7Bid%20title%7D%7D&operationName=BookById&variables=%7B%22id%22%3A%22b-01%22%7D
~~~

GET is suitable for Queries because Queries are designed to read data. Mutations change server state and must not be executed via GET according to GraphQL-over-HTTP semantics. A specification-compliant server must reject mutations sent via GET, typically with HTTP 405.

Some notes when using GET:

- URLs have length limits depending on browsers, proxies, and servers.
- Variables appear in the URL and can be recorded in access logs, browser history, or monitoring tools.
- GET requests can be cached by browsers, proxies, or CDNs if caching policies allow.
- Do not put tokens, passwords, or sensitive data into the query string.
- Do not use GET for mutations.

In practice, POST is usually simpler and safer for operations with large variables or sensitive data. Enable GET only when the client, caching strategy, and server have a clear need for it.

## 7. Content-Type and Accept

HTTP GraphQL has two important headers:

- `Content-Type` describes the format of the body the client is sending.
- `Accept` describes the format of the response the client wants to receive.

Example POST request:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json
~~~

`application/json` is the standard request body media type for JSON GraphQL requests. For responses, the GraphQL-over-HTTP specification defines `application/graphql-response+json` as the dedicated media type for GraphQL responses; `application/json` is still supported by many clients and servers for compatibility.

Clients should send an `Accept` header explicitly stating the media types they support. If the server does not support the requested media type, HTTP may return a content negotiation error such as 406. If the request uses an unsupported body media type, the server may reject it with 415.

Do not confuse the two headers:

| Header | Question answered |
|---|---|
| `Content-Type` | What format is the body I am sending? |
| `Accept` | What response formats can I receive? |

## 8. Distinguishing HTTP errors and GraphQL execution errors

HTTP transport and GraphQL execution are two different error layers.

### HTTP/transport errors

Errors occurring before or outside GraphQL execution, for example:

- Unsupported HTTP method.
- Request body is not valid JSON.
- Unsupported Content-Type.
- Request body exceeds server limits.
- Endpoint does not exist.
- Failed authentication conditions at the web security layer.

These errors are typically represented by HTTP status codes and may not have a GraphQL response envelope.

### GraphQL request/execution errors

Errors occurring during GraphQL processing, for example:

- Query is invalid according to the schema.
- Variable has the wrong type.
- Resolver throws an exception.
- User is not authorized to read a field.
- Custom scalar cannot serialize a value.

The GraphQL response may contain `errors`, and for field execution errors, it may also contain partial `data`.

Do not rely solely on checking the HTTP status to determine whether an operation succeeded. Clients must inspect the GraphQL response, especially `errors`, `path`, and `extensions`.

Exact HTTP status codes and media types also depend on how the server implements GraphQL-over-HTTP and the Spring for GraphQL version. Test actual endpoint behavior and agree on the contract with clients.

## 9. Spring MVC and Spring WebFlux

Spring for GraphQL supports both Spring MVC and Spring WebFlux. Both can provide an HTTP endpoint for GraphQL, though the web stacks' request-handling models differ.

| Criterion | Spring MVC | Spring WebFlux |
|---|---|---|
| Foundation | Servlet API | Reactive Streams |
| Web model | Blocking request thread | Non-blocking event loop when using reactive APIs |
| GraphQL controller | Annotated controller | Annotated controller |
| Reactive return types | Supported by Spring for GraphQL | Naturally integrated with the reactive stack |
| Blocking persistence integration | Well-suited for traditional JDBC/JPA | Requires isolating blocking calls or using reactive clients |

Choose MVC if most of the application uses Spring MVC and synchronous persistence like JPA/JDBC. Choose WebFlux if the application already follows the reactive stack and downstream dependencies also support non-blocking I/O.

Simply switching to WebFlux does not automatically make database queries non-blocking. If a resolver calls JPA directly on an event-loop thread, the application still risks blocking. Use an appropriate reactive repository or properly isolate blocking calls using Reactor mechanisms.

## 10. WebGraphQlInterceptor: intercepting requests and responses

`WebGraphQlInterceptor` is an extension point at the Spring GraphQL web request layer. It can:

- Read HTTP headers and request metadata.
- Add information to the GraphQL execution input/context.
- Log or trace requests.
- Apply common policies before an operation runs.
- Observe or transform the response before returning it to the transport.

Example adding a correlation ID to `GraphQLContext`:

~~~java
@Component
public class RequestMetadataInterceptor
        implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String requestId =
                request.getHeaders().getFirst("X-Request-Id");

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context -> {
                    if (requestId != null) {
                        context.put("requestId", requestId);
                    }
                }).build());

        return chain.next(request);
    }
}
~~~

A resolver can read the metadata:

~~~java
@QueryMapping
public Book book(DataFetchingEnvironment environment) {
    String requestId = environment.getGraphQlContext()
            .get("requestId");

    log.debug("Resolving book, requestId={}", requestId);

    String id = environment.getArgument("id");
    return bookService.findById(id);
}
~~~

A correlation ID is useful for linking logs across the HTTP request, resolvers, and service calls. If clients supply a request ID, validate its format and limit its length before logging to prevent log injection or log bloat.

Never use an arbitrary client-supplied header as proof of identity or access permissions. The principal and tenant must be determined by Spring Security or a trusted authentication mechanism before being placed into `GraphQLContext`.

## 11. WebGraphQlInterceptor and Spring Security

HTTP requests to the GraphQL endpoint pass through the web security chain just like other endpoints. Spring Security can be used to authenticate requests and enforce access policies.

Several protection layers can work together:

- HTTP security filter chain: authenticates requests, checks CSRF, CORS, and endpoint access permissions.
- GraphQL interceptor: puts metadata about the authenticated principal into `GraphQLContext`.
- Method/field security: protects resolvers or services based on business permissions.
- Service/domain layer: verifies resource ownership and tenant boundaries.

For example, a resolver can retrieve the authenticated principal from the application-populated context. Do not trust a client-supplied argument like `userId` or a header like `X-User-Id` to determine the current user.

GraphQL usually has a single shared endpoint for many fields, so securing only the `/graphql` URL is not enough. A user allowed to call the endpoint may still not be permitted to read a specific field or execute a particular mutation. Apply authorization at the operation, field, and resource levels.

If using cookie/session authentication, configure CSRF appropriately because GraphQL POST requests can execute mutations. CORS only controls which browser origins are allowed to access the endpoint; it does not replace authentication or authorization.

## 12. CORS for HTTP GraphQL

If the frontend runs on a different origin than the backend, browsers may send a preflight request before sending a GraphQL POST. The server must configure CORS for the GraphQL endpoint.

Factors to consider:

- Allowed origins: only permitted frontend domains.
- Allowed methods: typically includes POST and possibly GET if the server supports it.
- Allowed headers: e.g., `Authorization`, `Content-Type`, `Accept`, `X-Request-Id`.
- Allow credentials: enable only when actually using cookies or cross-origin credentials, and configure specific origins.
- Exposed headers: declare only the response headers that browser clients need to read.

Do not use a wildcard origin together with credentials. In production environments, declare explicit origins and verify CORS configuration on the actual web stack in use: Spring MVC or Spring WebFlux.

CORS is a browser policy. Clients like curl or backend services can call the endpoint without being subject to the same browser CORS mechanism; therefore, CORS is not an API security boundary.

## 13. Limiting and protecting the HTTP endpoint

A GraphQL request can contain deeply nested operations or request a large number of fields. Because a single endpoint is typically shared by many operations, the server needs resource limits at multiple layers.

Common measures include:

- Limiting HTTP request body size.
- Configuring timeouts for requests and downstream calls.
- Limiting concurrency and connection counts.
- Enforcing pagination limits in resolvers/services.
- Using query depth or complexity analysis if the application needs to control expensive queries.
- Rate limiting by principal, API key, or IP as appropriate.
- Limiting the number of aliases/fields according to application policy.
- Protecting mutations with authorization and validation.
- Avoiding logging full variables if they may contain sensitive data.

For example, a resolver should enforce a page size limit:

~~~java
@QueryMapping
public List<Book> books(@Argument Integer first) {
    int limit = first == null ? 20 : first;

    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException(
                "first must be between 1 and 100");
    }

    return bookService.findFirst(limit);
}
~~~

Limiting at the controller is only one layer of defense. The service and data access layers should also ensure they cannot be invoked with limits exceeding policy from another entry point.

## 14. HTTP caching and persisted queries

GET can be suitable for caching because Queries are designed for reading data. However, the cache key must fully reflect the operation and variables. For data that depends on the user, tenant, or access permissions, public caching can leak data between users.

POST is generally not cached by default like GET, although custom caching may exist in infrastructure.

Persisted queries are a technique where clients send an identifier or hash of a registered query instead of sending the entire document in every request. This information is typically passed via `extensions`. Benefits may include:

- Reducing request size.
- Allowing the server to accept only an approved set of queries.
- Supporting caching by query identifier.
- Reducing arbitrary document submissions from clients if an allowlist is properly implemented.

Persisted queries are not enabled automatically just because a request includes an `extensions` field. Client and server must agree on the protocol, hash storage, and fallback policy. Treat this as a separate implementation feature rather than a mandatory requirement of HTTP GraphQL transport.

## 15. Testing the HTTP endpoint with HttpGraphQlTester

`HttpGraphQlTester` lets you test GraphQL over the HTTP transport instead of invoking the GraphQL engine directly. It is useful for verifying the endpoint path, request serialization, headers, responses, and interceptors.

Example creating a tester from `WebTestClient`:

~~~java
WebTestClient webTestClient = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.builder(webTestClient).build();
~~~

Testing a Query:

~~~java
@Test
void shouldExecuteBookQueryOverHttp() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
            .operationName("BookById")
            .variable("id", "b-01")
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("b-01");
}
~~~

You can add headers to the request:

~~~java
HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.builder(webTestClient)
                .headers(headers ->
                        headers.setBearerAuth("test-token"))
                .build();
~~~

The token in the example is test data; in real tests, use a token generated by a security test fixture.

Scenarios worth testing:

1. Valid POST request with query and variables.
2. Document with multiple operations and `operationName` selected properly.
3. GET Query if the endpoint supports GET.
4. Mutation sent via GET is rejected.
5. Malformed request body or unsupported Content-Type.
6. `Authorization` header and principal are recognized properly.
7. Interceptor puts correlation ID into `GraphQLContext`.
8. CORS preflight from allowed origins and rejected origins.
9. GraphQL execution error has expected `data`/`errors`/`path`/`extensions`.
10. Oversized requests or queries exceeding limits are rejected per policy.
11. Subscriptions are sent over the corresponding streaming transport instead of standard HTTP request-response.

If you want to verify exact HTTP status codes, headers, or media types, use `WebTestClient` directly or combine it with `HttpGraphQlTester` to verify both the transport layer and the GraphQL payload.

## 16. Common errors

| Symptom | Possible cause | How to handle |
|---|---|---|
| Client receives 404 | Calling the wrong endpoint path | Check `spring.graphql.path` |
| Client receives 415 | Unsupported request Content-Type | Send the appropriate JSON media type |
| Client receives 406 | `Accept` has no media type supported by the server | Adjust `Accept`/content negotiation |
| Query runs but data is null | Resolver, service, or GraphQL errors | Check response `errors` and the resolver |
| GET mutation is rejected | GET is not used to execute mutations | Send mutations via POST |
| Variables fail to bind | Mismatched variable name, structure, or type against SDL | Check the document and variables |
| CORS preflight fails | Origin, method, or header not allowed | Configure CORS on the web stack |
| Principal missing from `GraphQLContext` | Security/interceptor not integrated | Populate the authenticated principal into context |
| Subscription does not work over HTTP | HTTP request-response does not maintain an event stream | Use WebSocket or RSocket |
| Large requests slow down the server | Missing body size, pagination, or complexity limits | Add limits at the web and GraphQL layers |

## 17. Design principles for HTTP GraphQL transport

When implementing an HTTP endpoint for Spring for GraphQL:

- Use a clear endpoint and configure it via `spring.graphql.path`.
- Use POST as the default method for operations, especially mutations.
- Support GET only for Queries and adhere to GraphQL-over-HTTP restrictions.
- Pass variables separately instead of concatenating values into the query string.
- Set `Content-Type` and `Accept` to the proper media types.
- Distinguish HTTP transport errors from GraphQL execution errors.
- Choose Spring MVC or WebFlux to match the existing stack.
- Use `WebGraphQlInterceptor` for metadata and cross-cutting logic at the GraphQL web layer.
- Integrate Spring Security and authorization at the field/resource level.
- Configure CORS for specific origins; do not treat CORS as authentication.
- Limit request size, timeouts, pagination, query complexity, and request rate.
- Do not log secrets or full sensitive variables.
- Use `HttpGraphQlTester` to test over the HTTP transport.
- Use WebSocket or RSocket for GraphQL Subscriptions.

## Conclusion

HTTP GraphQL transport is the layer connecting clients to GraphQL execution over HTTP. Spring Boot can auto-configure the endpoint, typically at `/graphql`, and Spring for GraphQL provides handlers and interceptors to process requests, context, and responses.

POST is the appropriate method for Queries and Mutations; GET can be used for Queries when supported and must not be used to execute mutations. Understanding the request payload, `operationName`, `variables`, `Content-Type`, `Accept`, and the boundary between HTTP errors and GraphQL errors helps keep client-server communication reliable. In production deployments, combine the transport with security, CORS, resource limits, observability, and testing via `HttpGraphQlTester`.

## References

- [Spring for GraphQL — HTTP Transport](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Web Interception](https://docs.spring.io/spring-graphql/reference/transports.html#server.web-interception)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL over HTTP Specification](https://graphql.github.io/graphql-over-http/draft/)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
