# HttpGraphQlClient

## Objectives

After this lesson, you will be able to:

- Explain the role of **HttpGraphQlClient** in Spring for GraphQL.
- Create an HTTP client from **WebClient** and configure its endpoint.
- Build GraphQL requests using a document, operation name, and variables.
- Use **retrieve()** to map a single field to a Java object.
- Use **execute()** when you need to inspect the entire GraphQL response and errors.
- Load GraphQL documents from files on the classpath.
- Configure headers, authentication, codecs, and interceptors.
- Set up timeouts, controlled retries, and transport error handling.
- Understand the HTTP client's subscription capability via Server-Sent Events.
- Distinguish **HttpGraphQlClient** from **HttpSyncGraphQlClient**.
- Test calling a GraphQL server from a client.

## 1. What is HttpGraphQlClient?

Spring for GraphQL provides a client API for a Java application to call a GraphQL server. **HttpGraphQlClient** is an implementation that uses Spring WebFlux's **WebClient** to send GraphQL requests over HTTP in a non-blocking manner.

This client is suitable when an application needs to:

- Call the GraphQL API of another service.
- Send Queries or Mutations from the backend.
- Combine data from multiple GraphQL servers.
- Integrate GraphQL into a reactive pipeline.
- Share the same request-building and response-reading pattern with Spring's other GraphQL client transports.

Spring for GraphQL defines the common abstraction **GraphQlClient**. Transport-specific clients such as **HttpGraphQlClient**, **WebSocketGraphQlClient**, and **RSocketGraphQlClient** share the same request, retrieve, and execute workflow. Therefore, most of the operation construction and response mapping code is transport-independent.

**HttpGraphQlClient** uses HTTP request-response for Queries and Mutations. For subscriptions, the HTTP client only works when the server supports streaming via Server-Sent Events (SSE). If the server uses WebSocket or RSocket, choose the corresponding client.

## 2. Preparing WebClient

**HttpGraphQlClient** is built on **WebClient**, so Spring WebFlux's **WebClient** must be on the classpath. This does not force the server application to switch to WebFlux; a Spring MVC application can still use WebClient as an HTTP client.

Example creating a WebClient with a GraphQL endpoint URL:

~~~java
WebClient webClient = WebClient.builder()
        .baseUrl("https://catalog.example.com/graphql")
        .build();
~~~

Then create **HttpGraphQlClient**:

~~~java
HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.create(webClient);
~~~

Or use the builder to configure additional headers:

~~~java
HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient)
                .headers(headers ->
                        headers.setBearerAuth(accessToken))
                .build();
~~~

In the example, **accessToken** is a token obtained from the application's authentication mechanism. Do not hard-code real tokens into source code or configuration files committed to the repository.

### Registering the client as a Spring bean

If multiple services or components need to call the same GraphQL endpoint, create a shared client instead of creating a new one for each request:

~~~java
@Configuration
public class GraphQlClientConfiguration {

    @Bean
    HttpGraphQlClient catalogGraphQlClient(WebClient.Builder builder) {
        WebClient webClient = builder
                .baseUrl("https://catalog.example.com/graphql")
                .build();

        return HttpGraphQlClient.builder(webClient).build();
    }
}
~~~

A component can inject the client:

~~~java
@Service
public class CatalogGateway {

    private final HttpGraphQlClient graphQlClient;

    public CatalogGateway(HttpGraphQlClient graphQlClient) {
        this.graphQlClient = graphQlClient;
    }
}
~~~

The client holds transport and codec configuration. For credentials that vary by user or tenant, design per-request token passing or create clients with corresponding configurations; do not set a single user's token as a shared default header for all requests.

## 3. Creating a GraphQL request with a document

A request starts from a GraphQL document. The document can be an inline string, a constant, or a .graphql file on the classpath.

Server-side SDL example:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

Client calling the Query:

~~~java
String document = """
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
                publishedYear
            }
        }
        """;

Mono<Book> bookMono = graphQlClient.document(document)
        .variable("id", "b-01")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Steps:

1. **document(document)** provides the operation.
2. **variable("id", "b-01")** passes the value for the $id variable.
3. **retrieve("book")** selects the book field in the data section of the response.
4. **toEntity(Book.class)** maps the field value into a Java object.
5. The result is **Mono<Book>**, because the HTTP client executes in a non-blocking manner.

Use variables instead of concatenating values directly into the GraphQL document. This keeps queries stable, avoids escaping bugs, and makes operations reusable.

## 4. Passing multiple variables and an operation name

A request can contain multiple variables. Use **variables(Map)** when you want to pass an entire map:

~~~java
Map<String, Object> variables = Map.of(
        "keyword", "Spring",
        "first", 10
);

Mono<List<Book>> booksMono = graphQlClient.document("""
        query SearchBooks($keyword: String!, $first: Int!) {
            searchBooks(keyword: $keyword, first: $first) {
                id
                title
            }
        }
        """)
        .operationName("SearchBooks")
        .variables(variables)
        .retrieve("searchBooks")
        .toEntityList(Book.class);
~~~

**operationName("SearchBooks")** specifies the operation to run when a document contains multiple operations or when you want to explicitly record the operation name in the request.

You can pass each variable individually with multiple calls to **variable(name, value)**:

~~~java
graphQlClient.document(document)
        .operationName("BookById")
        .variable("id", "b-01")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Variable names and data types must match the declarations in the GraphQL document and the server schema. The GraphQL server still performs validation and coercion; the client does not replace that validation step.

## 5. retrieve(): extracting a single field from the response

**retrieve(path)** is a concise way when the client only needs one specific field in the data section.

Example server response:

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

Client:

~~~java
Mono<Book> bookMono = graphQlClient.document("""
        query {
            book(id: "b-01") {
                id
                title
            }
        }
        """)
        .retrieve("book")
        .toEntity(Book.class);
~~~

The path is evaluated relative to the data key. For nested fields, use dots:

~~~java
Mono<String> authorName = graphQlClient.document(document)
        .retrieve("book.author.name")
        .toEntity(String.class);
~~~

For lists, you can use an index in the path:

~~~java
Mono<String> firstBookTitle = graphQlClient.document("""
        query {
            books {
                title
            }
        }
        """)
        .retrieve("books[0].title")
        .toEntity(String.class);
~~~

If you need to map the entire list:

~~~java
Mono<List<Book>> books = graphQlClient.document("""
        query {
            books {
                id
                title
            }
        }
        """)
        .retrieve("books")
        .toEntityList(Book.class);
~~~

**retrieve()** is suitable when the response path is known and the client only needs a single value. If you need to read multiple fields, inspect errors across multiple branches, or handle partial data, use **execute()**.

## 6. execute(): full control over the GraphQL response

**execute()** returns **Mono<ClientGraphQlResponse>**. This approach lets you check request validity, access multiple fields, and read errors attached to individual fields.

~~~java
Mono<ClientGraphQlResponse> responseMono =
        graphQlClient.document("""
                query {
                    book(id: "b-01") {
                        id
                        title
                    }
                    latestBooks {
                        id
                        title
                    }
                }
                """)
                .execute();
~~~

Handling the response:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .execute()
        .flatMap(response -> {
            if (!response.isValid()) {
                return Mono.error(
                        new IllegalStateException(
                                "GraphQL request was rejected"));
            }

            ClientResponseField field = response.field("book");

            if (field.getValue() == null) {
                if (field.getErrors().isEmpty()) {
                    return Mono.empty();
                }

                return Mono.error(
                        new IllegalStateException(
                                "The book field could not be resolved"));
            }

            return Mono.just(field.toEntity(Book.class));
        });
~~~

Distinguish the following cases:

- **response.isValid() == false**: request-level failure, such as an invalid GraphQL document or variables.
- Field value is null with no errors: a nullable field may simply have no data.
- Field value is null with errors: the field resolver failed or GraphQL null propagation affected the field.
- Field has a value but cannot be decoded into the Java type: a client conversion error occurs.

**execute()** is useful when the client needs to handle partial data. One field may fail while other fields still have valid data.

## 7. Handling FieldAccessException and GraphQlClientException

With **retrieve(path)**, Spring needs to locate the right response field and convert its value into a Java type. This process can raise errors:

- **FieldAccessException**: the path does not exist or the field has a null value accompanied by GraphQL errors.
- **GraphQlClientException**: the field exists, but its value cannot be decoded into the requested Java type.
- **GraphQlTransportException**: a transport-layer error, such as failing to connect to the server or a response that cannot be processed as a GraphQL response.

Example handling field errors in a reactive pipeline:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .retrieve("book")
        .toEntity(Book.class)
        .onErrorResume(FieldAccessException.class, exception -> {
            ClientGraphQlResponse response = exception.getResponse();
            ClientResponseField field = exception.getField();

            log.warn(
                    "Book field failed, errors={}",
                    field.getErrors());

            return Mono.empty();
        });
~~~

Do not turn every error into **Mono.empty()**. Doing so can cause the application to confuse missing data with server errors. Only use a fallback when business logic accepts a substitute result.

If you need to fully distinguish request errors from field errors, use **execute()** to read **ClientGraphQlResponse** and **ClientResponseField**.

## 8. Loading GraphQL documents from files

When queries are long or used in multiple places, store documents as files instead of embedding strings in Java.

Place the file in the directory:

~~~text
src/main/resources/graphql-documents/bookById.graphql
~~~

File contents:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
    publishedYear
  }
}
~~~

Invoke by document name:

~~~java
Mono<Book> bookMono = graphQlClient.documentName("bookById")
        .variable("id", "b-01")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Spring for GraphQL provides **DocumentSource** to load documents from the classpath. By default, .graphql or .gql files are looked up under **graphql-documents/**.

You can configure **DocumentSource** via the GraphQlClient builder if the application needs a different directory or document loading strategy.

Storing operations in files offers several benefits:

- Queries are easier to review and version control.
- IDEs can provide syntax highlighting and completion.
- Documents can be validated separately against the schema.
- Java code focuses on variables and result handling.

Name files and operations consistently, and avoid putting too many unrelated operations in a single file.

## 9. Configuring headers and authentication

The **HttpGraphQlClient** builder allows setting HTTP headers shared across requests made through the client.

Basic Authentication example:

~~~java
HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient)
                .headers(headers ->
                        headers.setBasicAuth(username, password))
                .build();
~~~

Bearer token example:

~~~java
HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient)
                .headers(headers ->
                        headers.setBearerAuth(accessToken))
                .build();
~~~

You can call **mutate()** on an existing client to build a new client with a different transport configuration:

~~~java
HttpGraphQlClient serviceAccountClient =
        graphQlClient.mutate()
                .headers(headers ->
                        headers.setBearerAuth(serviceToken))
                .build();
~~~

The new client is built from the existing configuration but can use its own headers. This is useful when an application calls the same server using different credentials or configurations.

Do not use a singleton client with headers containing continuously changing user tokens. If each request has a different principal, design a token provisioning mechanism and pass headers per request using an appropriate WebClient filter/interceptor, or create separate clients scoped to the security context. Never store a previous request's token in shared state.

## 10. Customizing WebClient and codecs

Because **HttpGraphQlClient** uses WebClient, you can customize HTTP features such as:

- Base URL.
- Default headers.
- TLS and proxy.
- Connection pool.
- HTTP connector.
- Codecs and buffer size limits.
- Exchange filters for integrating tracing or authentication.

Example configuring WebClient with a base URL and filter:

~~~java
WebClient webClient = WebClient.builder()
        .baseUrl("https://catalog.example.com/graphql")
        .filter((request, next) -> {
            log.debug("Calling GraphQL endpoint: {}", request.url());
            return next.exchange(request);
        })
        .build();

HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

If you need to serialize custom types or support **ArgumentValue** to distinguish omitted input from explicit null, configure the appropriate Spring for GraphQL Jackson module.

Example with Jackson 3:

~~~java
@Bean
GraphQlJacksonModule graphQlJacksonModule() {
    return new GraphQlJacksonModule();
}
~~~

With Jackson 2, Spring for GraphQL provides **GraphQlJackson2Module**. When creating WebClient and codecs manually, ensure the encoder/decoder actually uses the ObjectMapper with that module registered.

Do not replace the default codec without a specific requirement. Misconfiguring codecs can cause variables not to serialize properly or break response decoding.

## 11. GraphQlClientInterceptor

**GraphQlClientInterceptor** allows intercepting GraphQL requests and responses at the client layer. With a non-blocking client like **HttpGraphQlClient**, the interceptor uses Reactor **Mono** and **Flux**.

Example interceptor logging response validity:

~~~java
public class LoggingGraphQlClientInterceptor
        implements GraphQlClientInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(
                    LoggingGraphQlClientInterceptor.class);

    @Override
    public Mono<ClientGraphQlResponse> intercept(
            ClientGraphQlRequest request,
            Chain chain) {

        return chain.next(request)
                .doOnNext(response ->
                        log.debug(
                                "GraphQL response valid={}",
                                response.isValid()));
    }

    @Override
    public Flux<ClientGraphQlResponse> interceptSubscription(
            ClientGraphQlRequest request,
            SubscriptionChain chain) {

        return chain.next(request);
    }
}
~~~

Register the interceptor when creating the client:

~~~java
HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient)
                .interceptor(
                        new LoggingGraphQlClientInterceptor())
                .build();
~~~

Interceptors are suitable for cross-cutting logic across multiple requests:

- Logging operations or correlation metadata.
- Measuring GraphQL server call latency.
- Attaching tracing.
- Standardizing transport error handling.
- Adding or forwarding metadata according to client policy.

Do not log full variables if they may contain passwords, tokens, or personal data. Log the operation name, endpoint, duration, request ID, and necessary error codes instead.

## 12. Timeouts, retries, and cancellation

Because **HttpGraphQlClient** returns reactive publishers, you can combine Reactor operators to enforce time limits and handle transient errors.

Example timeout for a Query:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .variable("id", "b-01")
        .retrieve("book")
        .toEntity(Book.class)
        .timeout(Duration.ofSeconds(3));
~~~

If the response does not arrive within the specified duration, the publisher emits a timeout error and the request subscription is cancelled.

You can retry on transient transport errors:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .variable("id", "b-01")
        .retrieve("book")
        .toEntity(Book.class)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                        .filter(GraphQlTransportException.class::isInstance)
        );
~~~

Only retry when the error is recoverable and the operation is safe to re-run. Queries are generally more suitable than mutations. If the server has already executed a mutation but the response was lost over the network, the client cannot know for sure whether the operation was committed. Retrying a mutation may create duplicate data or execute side effects twice.

If a mutation requires retries, design an idempotency key or deduplication mechanism on the server. Do not retry every GraphQL field error as if it were a connection error.

When downstream no longer needs the result and the subscriber cancels the publisher, cancellation propagates through the reactive chain so WebClient aborts the request when possible.

## 13. Using HttpGraphQlClient for Subscriptions over SSE

**HttpGraphQlClient** is primarily used for HTTP request-response, but Spring for GraphQL also supports subscriptions over HTTP when the server provides Server-Sent Events (SSE).

Example:

~~~java
Flux<Book> bookEvents = graphQlClient.document("""
        subscription {
            bookAdded {
                id
                title
            }
        }
        """)
        .retrieveSubscription("bookAdded")
        .toEntity(Book.class);
~~~

**retrieveSubscription(...)** returns a Flux because the client can receive multiple responses over time.

Requirements:

- The server must have GraphQL subscriptions over SSE configured.
- The HTTP endpoint and content negotiation must support streaming responses.
- The client must handle stream errors, timeouts, and cancellation.
- Proxy/load balancer infrastructure must allow SSE connections to stay open long enough.

If the server only supports WebSocket, use **WebSocketGraphQlClient**. If using RSocket, use **RSocketGraphQlClient**. Do not assume every HTTP GraphQL endpoint automatically supports subscriptions.

## 14. Distinguishing HttpGraphQlClient and HttpSyncGraphQlClient

Spring for GraphQL has two main HTTP clients:

| Criterion | **HttpGraphQlClient** | **HttpSyncGraphQlClient** |
|---|---|---|
| HTTP API | WebClient | RestClient |
| Model | Non-blocking | Blocking |
| Result type | Mono/Flux | Synchronous value |
| Interceptor | GraphQlClientInterceptor | SyncGraphQlClientInterceptor |
| Best suited for | Reactive pipelines, WebFlux, async integration | Imperative/blocking code |
| Field read method | retrieve(...) | retrieveSync(...) |
| Execute | execute() | executeSync() |

If the application uses WebFlux or wants to keep the processing chain non-blocking, choose **HttpGraphQlClient**.

If an imperative application uses **RestClient** and needs a synchronous API, choose **HttpSyncGraphQlClient**. Do not arbitrarily call **block()** on **HttpGraphQlClient** inside an event-loop or reactive pipeline to simulate a synchronous client.

Both clients share the **GraphQlClient** workflow, so writing documents, variables, retrieve, and execute is very similar.

## 15. Testing calls to a GraphQL server

There are two testing scopes to distinguish:

- Testing a GraphQL server using **HttpGraphQlTester** or **WebTestClient**.
- Testing a client application calling another GraphQL server using **HttpGraphQlClient**.

When testing the client, you can run a local test GraphQL server or use a mock HTTP server such as MockWebServer/WireMock to verify the request body and response mapping.

Example integration test calling a running test server:

~~~java
@Test
void shouldFetchBookFromGraphQlServer() {
    Mono<Book> result = graphQlClient.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "b-01")
            .retrieve("book")
            .toEntity(Book.class);

    StepVerifier.create(result)
            .assertNext(book -> {
                assertThat(book.id()).isEqualTo("b-01");
                assertThat(book.title())
                        .isEqualTo("GraphQL in Practice");
            })
            .verifyComplete();
}
~~~

The test above assumes the test GraphQL server returns the matching Book and **graphQlClient** is configured to point to that server.

What should be tested:

1. Queries with valid variables.
2. Mutations with input objects.
3. Operation names when a document has multiple operations.
4. Response mapping to records/DTOs.
5. Nullable fields returning null without errors.
6. Failing fields producing **FieldAccessException** when using retrieve.
7. **execute()** reading request-level and field-level errors.
8. Proper handling of HTTP transport failures.
9. Timeouts and retries applied only to safe operation types.
10. Authorization headers sent properly.
11. Document source loading the right file on the classpath.
12. Subscriptions over SSE receiving multiple events and stopping upon cancellation.

If using a mock HTTP server, in addition to the response body, verify the method, URL, Content-Type, Accept, authorization header, and JSON request payload.

## 16. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| Cannot connect to server | Wrong base URL, DNS, or TLS | Check endpoint and HTTP connector |
| Server returns 401/403 | Missing or invalid credentials | Check Bearer token and access permissions |
| Field path does not exist | Wrong path passed to retrieve | Cross-check against response data |
| Retrieve throws FieldAccessException | Field is null with GraphQL errors or path is missing | Use execute to read field errors |
| Cannot decode DTO | Java type does not match response shape | Check fields, generic types, and codecs |
| Variables are not sent | Wrong variable name or Map | Cross-check document and schema |
| Request is blocked | Calling block inside reactive/event-loop | Keep Mono/Flux or use HttpSyncGraphQlClient |
| Retry creates duplicate data | Retrying a non-idempotent mutation | Use an idempotency key or disable retry |
| Subscription receives no events | Server does not support SSE or wrong transport used | Check SSE, WebSocket, or RSocket |
| User headers get mixed up | Using mutable credentials on a shared client | Pass credentials per request or separate clients |
| Document file not found | Wrong directory or document name | Check classpath graphql-documents/ |

## 17. Principles for using HttpGraphQlClient

When building a GraphQL client in a Spring application:

- Use **HttpGraphQlClient** for non-blocking HTTP based on WebClient.
- Reuse configured clients for the same endpoint.
- Use variables instead of string-concatenating queries.
- Give operations meaningful names.
- Use **retrieve()** when only a single field is needed; use **execute()** when the full response is needed.
- Handle request errors, field errors, and transport errors separately.
- Use document files for long or reused operations.
- Configure authentication and headers according to credential scope.
- Use interceptors for logging, tracing, and shared metadata.
- Set appropriate timeouts and only retry operations that are safe to re-run.
- Do not block reactive pipelines.
- Choose SSE, WebSocket, or RSocket matching the subscription transport.
- Test request payloads, headers, response mapping, and error behavior.

## Conclusion

**HttpGraphQlClient** is Spring for GraphQL's non-blocking GraphQL client, using **WebClient** to send operations over HTTP. After creating the client, the application uses the unified **GraphQlClient** workflow to build documents, pass variables, select operations, and read results.

**retrieve()** enables quick mapping of a single field to a Java object; **execute()** lets you inspect the entire response and distinguish request-level from field-level errors. Combining WebClient headers, codecs, **GraphQlClientInterceptor**, timeouts, and controlled retries creates a reusable and observable client. For subscriptions, the server must support SSE, or you should choose the corresponding WebSocket/RSocket client.

## References

- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — HttpGraphQlClient API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/HttpGraphQlClient.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring for GraphQL — GraphQlClientInterceptor API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClientInterceptor.html)
- [Spring for GraphQL — Client Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
