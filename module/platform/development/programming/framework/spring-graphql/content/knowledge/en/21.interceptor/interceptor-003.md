# WebGraphQlRequest

In Spring for GraphQL, **WebGraphQlRequest** is the abstraction representing a GraphQL request passing through a web transport. It provides GraphQL content such as document, operation name, variables, and extensions, while also allowing access to HTTP request information such as headers, URI, remote address, and request attributes.

This object is commonly used in **WebGraphQlInterceptor**. An interceptor can read metadata from the request, validate or normalize the data, and then add information to the GraphQL execution input before resolvers run. As a result, transport-handling code stays in the web layer; controllers and services receive only the data needed for the use case.

This article presents the structure and lifecycle of WebGraphQlRequest, the groups of information that can be accessed, how to use the request in an interceptor, how to configure ExecutionInput and GraphQLContext, the boundary between web request and GraphQL execution, along with security and testing notes.

## 1. What Is WebGraphQlRequest?

**WebGraphQlRequest** is the web-layer request object of Spring for GraphQL. It combines two groups of information:

1. The GraphQL content sent by the client.
2. The HTTP/web transport information accompanying the request.

The GraphQL content group is provided through the core GraphQL request contract:

| Component | Meaning |
|---|---|
| Document | GraphQL query, mutation, or subscription document |
| Operation name | Name of the operation selected for execution if the document has multiple operations |
| Variables | Input values for variables in the document |
| Extensions | Protocol- or application-specific extension metadata |

The web information group typically includes:

| Component | Meaning |
|---|---|
| Headers | HTTP headers such as Authorization, Accept-Language, or X-Correlation-Id |
| URI | URI of the endpoint receiving the request |
| Remote address | Network address of the connecting peer, if provided by the transport |
| Attributes | Attributes attached to the web request by the adapter or application |

In addition to reading information, WebGraphQlRequest also provides a mechanism to configure **ExecutionInput** so that an interceptor can enrich GraphQLContext or adjust execution input data before the GraphQL engine processes the operation.

## 2. Where Does WebGraphQlRequest Fit in the Architecture?

A typical HTTP request is processed in the following flow:

~~~mermaid
flowchart TD
    A[HTTP client] --> B[Spring Web MVC or WebFlux]
    B --> C[WebGraphQlHandler]
    C --> D[WebGraphQlInterceptor chain]
    D --> E[WebGraphQlRequest]
    E --> F[GraphQL execution input]
    F --> G[GraphQL engine]
    G --> H[DataFetcher / annotated controller]
    H --> I[Service and repository]
    I --> J[GraphQL response]
~~~

WebGraphQlRequest is the boundary between the web transport and GraphQL execution. It allows interceptors to access HTTP details without requiring controllers to depend directly on the Servlet API or WebFlux ServerWebExchange.

The components have distinct roles:

- **WebGraphQlRequest**: represents the request and provides transport information along with GraphQL content.
- **WebGraphQlInterceptor**: handles request/response before and after GraphQL execution.
- **ExecutionInput**: input used by GraphQL Java to execute the operation.
- **GraphQLContext**: place to share data within the execution scope.
- **DataFetcher/Controller**: resolves fields according to the schema and selection set.

Do not treat WebGraphQlRequest as a service or domain object. It is a web-layer abstraction.

## 3. Reading GraphQL Content from the Request

WebGraphQlRequest provides the core information of a GraphQL operation. For example, an interceptor can inspect the operation name to apply observability policies or logging:

~~~java
@Component
public class OperationLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(OperationLoggingInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String operationName = request.getOperationName();

        log.debug("GraphQL operation received: {}", operationName);

        return chain.next(request);
    }
}
~~~

Commonly used GraphQL content methods:

- getDocument() returns the document as a string.
- getOperationName() returns the operation name chosen by the client, which may be absent.
- getVariables() returns the variables map.
- getExtensions() returns the extensions map.

Example of reading the operation name and variables:

~~~java
String operationName = request.getOperationName();
Map<String, Object> variables = request.getVariables();
Map<String, Object> extensions = request.getExtensions();
~~~

### When Should These Values Be Read?

Some reasonable use cases:

- Recording the operation name in logs or metrics.
- Inspecting extensions used by persisted query protocols.
- Applying limits or policies by operation type.
- Attaching diagnostic information to the execution context.
- Investigating failed requests when a corresponding correlation ID is available.

Do not log the entire document and variables by default. Variables may contain personal information, access tokens, or sensitive business data. When diagnostics are needed, log the operation name, correlation ID, and selected attributes.

## 4. Reading HTTP Headers

WebGraphQlRequest provides headers in Spring's HTTP structure. An interceptor can read a header using getFirst:

~~~java
@Component
public class ClientMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String clientVersion =
                request.getHeaders().getFirst("X-Client-Version");

        String correlationId =
                request.getHeaders().getFirst("X-Correlation-Id");

        return chain.next(request);
    }
}
~~~

Some common headers:

| Header | Purpose |
|---|---|
| Authorization | Credentials sent to the security infrastructure |
| Accept-Language | Client's preferred language |
| X-Correlation-Id | Request correlation ID if supported by the application |
| X-Client-Version | Client application version |
| Content-Type | Request content type |
| Origin | Browser origin, often related to CORS |

Headers are input data from the transport. Not every header is trustworthy. For example, a client can set X-Tenant-Id itself; the server needs to determine the tenant from the principal or a verified source rather than trusting this value directly.

### Headers May Be Missing or Have Multiple Values

Do not assume a header is always present:

~~~java
String clientVersion =
        request.getHeaders().getFirst("X-Client-Version");

if (!StringUtils.hasText(clientVersion)) {
    clientVersion = "unknown";
}
~~~

For headers that can have multiple values, use the appropriate HttpHeaders API and clearly define how values are selected or combined. Do not arbitrarily concatenate values with different meanings.

## 5. Reading URI and Remote Address

WebGraphQlRequest provides the URI and remote address information of the request:

~~~java
@Override
public Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        Chain chain) {

    URI uri = request.getUri();
    InetSocketAddress remoteAddress = request.getRemoteAddress();

    log.debug(
            "GraphQL endpoint={}, remote={}",
            uri,
            remoteAddress);

    return chain.next(request);
}
~~~

The URI is useful when:

- The application has multiple GraphQL endpoints.
- You need to observe which endpoint was called.
- There are routing or endpoint versioning rules.
- Transport information needs to be recorded in logs.

The remote address is useful for connection diagnostics or network-level statistics. However, this address may belong to a reverse proxy, gateway, or load balancer rather than the end user's device.

If you need to read forwarded headers such as Forwarded or X-Forwarded-For, only trust them when the request passes through a proxy configured as trusted. Clients can send those headers themselves if the system does not filter or overwrite them at the gateway.

Do not use the remote address or IP as the sole basis for authenticating users or granting data access permissions.

## 6. Request Attributes

WebGraphQlRequest can provide **request attributes** attached to the web request. This is where web-layer components can exchange auxiliary per-request data if the adapter or application has set those attributes.

Example of reading an attribute set by an earlier web component:

~~~java
Object gatewayMetadata =
        request.getAttributes().get("gatewayMetadata");
~~~

Attributes differ from GraphQL variables and GraphQLContext:

| Data Type | Purpose |
|---|---|
| GraphQL variables | Inputs sent by the client for the operation |
| Web request attributes | Data attached to the request at the web layer |
| GraphQLContext | Data shared during GraphQL execution |

Do not assume a request attribute automatically appears in GraphQLContext. If a resolver needs to use that value, the interceptor should explicitly transfer the appropriate value into ExecutionInput/GraphQLContext.

Attributes should also not become a place to store state shared across requests. Keep data properly request-scoped and avoid passing web-specific objects deep into the service layer.

## 7. Using WebGraphQlRequest in WebGraphQlInterceptor

An interceptor receives WebGraphQlRequest and Chain. The interceptor can read the request, configure the execution input, and then call chain.next(request) to forward it.

Example of reading the client version and correlation ID, then putting the normalized values into GraphQLContext:

~~~java
@Component
public class ClientMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String clientVersion =
                request.getHeaders().getFirst("X-Client-Version");

        String correlationId =
                request.getHeaders().getFirst("X-Correlation-Id");

        if (!StringUtils.hasText(correlationId)) {
            correlationId = UUID.randomUUID().toString();
        }

        String normalizedVersion =
                StringUtils.hasText(clientVersion)
                        ? clientVersion.trim()
                        : "unknown";

        String requestId = correlationId;

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context -> {
                    context.put("clientVersion", normalizedVersion);
                    context.put("correlationId", requestId);
                }).build());

        return chain.next(request);
    }
}
~~~

Resolvers can read the context:

~~~java
@QueryMapping
public List<Book> books(
        @ContextValue("clientVersion") String clientVersion) {

    return bookService.findBooksForClientVersion(clientVersion);
}
~~~

This example only illustrates how to pass data. If the client version is only used for logs or metrics, there is no need to pass it into a business service. If metadata affects business behavior, define a clear contract and validate input values.

### Role of chain.next

chain.next(request) forwards the request to the next interceptor or to GraphQL execution when no interceptors remain.

If an interceptor does not call chain.next, the operation will not proceed through the normal processing chain. This is only appropriate when the interceptor intentionally terminates the request via a clearly designed mechanism; do not accidentally skip the chain.

Because the interceptor method returns Mono<WebGraphQlResponse>, preserve the reactive flow and avoid calling block() inside the interceptor.

## 8. What Does configureExecutionInput Change?

WebGraphQlRequest provides configureExecutionInput to customize ExecutionInput before the GraphQL engine executes the operation.

Example of adding GraphQLContext:

~~~java
request.configureExecutionInput((input, builder) ->
        builder.graphQLContext(context -> {
            context.put("tenantId", tenantId);
            context.put("correlationId", correlationId);
        }).build());
~~~

ExecutionInput is the input object for GraphQL Java. Besides the context, depending on the use case and the APIs supported by Spring for GraphQL, an interceptor can adjust appropriate execution properties.

Use this configuration for data genuinely needed at the GraphQL execution layer, such as:

- Verified tenant.
- Normalized locale.
- Correlation ID.
- Principal or appropriate actor information.
- Request-scoped service or helper data for resolvers if clearly designed.

Do not use ExecutionInput to stuff the entire HTTP request or all headers into the context. Only pass values that are needed, validated, and clearly typed.

### Preserving Existing Configuration

When multiple interceptors call configureExecutionInput, each interceptor should only add the configuration it owns and avoid overwriting context keys of other interceptors.

Standardize keys via constants:

~~~java
public final class GraphQlContextKeys {

    public static final String TENANT_ID = "tenantId";
    public static final String CORRELATION_ID = "correlationId";

    private GraphQlContextKeys() {
    }
}
~~~

This reduces typos and makes it clear which keys are used across the application.

## 9. How WebGraphQlRequest Differs from HttpServletRequest and ServerWebExchange

Spring for GraphQL can run on Spring MVC or Spring WebFlux. If a controller depends directly on HttpServletRequest, the code becomes tied to the Servlet stack. If it depends on ServerWebExchange, it becomes tied to WebFlux.

WebGraphQlRequest provides a web abstraction tailored for Spring for GraphQL:

| Criterion | WebGraphQlRequest | HttpServletRequest | ServerWebExchange |
|---|---|---|---|
| Purpose | GraphQL web transport request | HTTP request in Servlet | Request/response exchange in WebFlux |
| Has GraphQL document/variables | Yes, via GraphQL request contract | Not directly | Not directly |
| Access HTTP headers | Yes | Yes | Yes |
| Configure GraphQL ExecutionInput | Yes | No | Not directly |
| Specific transport dependency | Spring GraphQL web abstraction | Servlet | WebFlux |

For GraphQL logic, prefer WebGraphQlRequest in interceptors. For business logic, do not pass any of these three request objects into services. Convert necessary information into plain Java types.

## 10. How WebGraphQlRequest and GraphQLContext Differ

The two objects serve two different phases:

- WebGraphQlRequest represents the request at the web layer.
- GraphQLContext represents the context shared during GraphQL execution.

Data flow:

~~~text
HTTP headers / URI / request attributes
                |
                v
        WebGraphQlRequest
                |
                v
      WebGraphQlInterceptor
                |
                v
       configureExecutionInput
                |
                v
          GraphQLContext
                |
                v
       @ContextValue / DataFetcher
~~~

Example:

~~~java
@QueryMapping
public List<Book> books(
        @ContextValue("tenantId") String tenantId) {

    return bookService.findBooks(tenantId);
}
~~~

The controller does not need to accept WebGraphQlRequest to read headers. The interceptor has already transferred the verified tenant ID into GraphQLContext.

This clarifies responsibilities:

- Interceptor understands the HTTP request.
- GraphQLContext carries execution metadata.
- Controller understands GraphQL fields and inputs.
- Service understands use cases and business rules.

## 11. Do Not Treat WebGraphQlRequest as a Trusted Data Source by Default

WebGraphQlRequest reflects the request data received by the server. The mere presence of a value in the request does not make it trustworthy.

Example:

~~~http
X-Tenant-Id: tenant-root
X-User-Role: ADMIN
X-Internal-Client: true
~~~

Clients can set these headers themselves if the gateway does not strip or control them. Do not pass them straight into GraphQLContext and use them for authorization.

Rules:

- Credentials must be verified by Spring Security or the authentication infrastructure.
- Tenant must be derived from the principal or a trusted source.
- Forwarded headers are only trustworthy when set by a trusted proxy.
- Correlation IDs need length and character restrictions before logging.
- Client version should only be used for metrics or feature behavior after format validation.
- Do not log the Authorization header, cookies, or full variables.

If a request contains invalid data, the interceptor can reject the request according to policy or replace it with a safe server-side value. Do not let unverified values enter services or repositories.

## 12. What Information Can an HTTP Request Contain Besides the Operation?

A GraphQL request over HTTP typically has:

~~~http
POST /graphql
Content-Type: application/json
Accept: application/json
X-Correlation-Id: req-123
Accept-Language: vi-VN
Authorization: Bearer <token>
~~~

The JSON body may contain:

~~~json
{
  "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
  "operationName": "FindBook",
  "variables": {
    "id": "book-01"
  },
  "extensions": {}
}
~~~

WebGraphQlRequest provides both the GraphQL group of information in the body and the HTTP group of information from the request. This enables the interceptor to coordinate:

- Operation name to observe the operation type.
- Variables to apply protocol-layer limits or checks when needed.
- Headers to read locale, correlation ID, or client information.
- URI to identify the endpoint.
- Remote address to assist with network diagnostics.

Do not re-validate every schema rule in an interceptor. The GraphQL engine is responsible for parsing, document validation, and variable coercion against the schema. Interceptors should only handle appropriate request/transport policies.

## 13. Error Handling and Request Termination in Interceptors

An interceptor may encounter errors when reading or validating metadata. For example, a client sends a malformed client version or a request fails to meet a policy.

There are two approaches:

1. Reject the request before calling chain.next if it is a transport/request-level error.
2. Put verified information into the execution context and let GraphQL execution/error handling deal with field- or operation-level errors where appropriate.

Do not manually build an improperly structured GraphQL response or swallow exceptions and return a fake success response.

When you need to stop the interceptor chain, use the response/error mechanism supported by Spring for GraphQL in your application's version. For GraphQL errors arising in resolvers, use an exception resolver or appropriate GraphQL error handling rather than handling every case in a WebGraphQlRequest interceptor.

### Preserving Reactivity

WebGraphQlInterceptor returns Mono<WebGraphQlResponse>. Example of asynchronous handling:

~~~java
@Override
public Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        Chain chain) {

    return metadataService.lookupClientPolicy(request)
            .flatMap(policy -> {
                request.configureExecutionInput((input, builder) ->
                        builder.graphQLContext(context ->
                                context.put("clientPolicy", policy))
                            .build());

                return chain.next(request);
            });
}
~~~

This example assumes metadataService returns a Mono and that looking up the policy is necessary. If the data is already available, synchronous handling is simpler. Avoid block() because it can block the event loop in WebFlux.

## 14. Testing WebGraphQlRequest and Interceptors

To test headers, URI, or remote address flowing through the web adapter, use an integration test at the HTTP layer. **HttpGraphQlTester** combined with WebTestClient allows sending operations with headers.

Example:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebGraphQlRequestTest {

    @LocalServerPort
    int port;

    @Test
    void shouldPassRequestMetadataToGraphQlContext() {
        WebTestClient webClient = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .defaultHeader("X-Correlation-Id", "test-req-001")
                .defaultHeader("X-Client-Version", "2.4.0")
                .build();

        HttpGraphQlTester tester = HttpGraphQlTester.create(webClient);

        tester.document("""
                query {
                    requestInfo {
                        correlationId
                        clientVersion
                    }
                }
                """)
            .execute()
            .path("requestInfo.correlationId")
            .entity(String.class)
            .isEqualTo("test-req-001");
    }
}
~~~

This example assumes the application has a requestInfo field for testing or business purposes. Do not add debug fields to the production schema solely for internal inspection.

What should be tested:

1. Document and operation name are read accurately.
2. Variables and extensions match the values sent in the request.
3. Missing headers are handled via fallbacks.
4. Multi-valued headers are handled according to convention.
5. URI and remote address are read when provided by the transport.
6. Request attributes are used within the proper scope.
7. The interceptor transfers necessary metadata into GraphQLContext.
8. Resolvers can read context with @ContextValue.
9. Metadata is not shared between two concurrent requests.
10. Spoofed tenant or role headers cannot bypass authorization.
11. The interceptor continues the chain properly and does not block reactive execution.
12. Sensitive variables or headers do not appear in logs.

If you only need to test the handler and the configured GraphQLContext, you can use a tester at the execution layer. However, that test does not verify that the HTTP adapter and WebGraphQlInterceptor are actually invoked.

## 15. Common Pitfalls When Working with WebGraphQlRequest

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Header is always null | Client did not send it, proxy stripped it, or wrong name | Check the actual request and header mapping |
| Context is missing metadata | Only reading the header without configuring ExecutionInput | Use configureExecutionInput |
| Resolver depends on HttpServletRequest | Bringing transport APIs into controller/service | Read in interceptor and transfer into GraphQLContext |
| Remote address is not the client IP | Request passes through a proxy/load balancer | Configure trusted proxy and forwarded header policy |
| Operation name is null | Client sent an anonymous operation or omitted selection | Handle optional values |
| Logs leak data | Logging full document, variables, or headers | Log selected metadata only |
| Interceptor does not run | Bean not registered or test does not go through web transport | Check configuration and use HttpGraphQlTester |
| Operation does not continue | Forgot to call chain.next(request) | Continue the chain or terminate the request intentionally |
| WebFlux is blocked | Calling block inside the interceptor | Use reactive composition |
| Tenant is spoofed | Trusting client-sent headers directly | Derive tenant from verified authentication |
| Multiple interceptors overwrite context keys | No agreement on keys and ownership | Use constants and divide responsibilities |

## 16. Workflow for Using WebGraphQlRequest

When you need to handle request metadata or transport information:

1. Identify whether the data to read belongs to the GraphQL operation or the HTTP transport.
2. Use WebGraphQlRequest in WebGraphQlInterceptor to read document, operation name, variables, extensions, or HTTP details.
3. Select headers, URI, remote address, and attributes fitting the use case.
4. Check for missing values, format, and trust boundaries.
5. Do not use headers or remote address as authentication proof without verification.
6. Transfer values needed by resolvers into GraphQLContext via configureExecutionInput.
7. Use @ContextValue or DataFetchingEnvironment to read them in the GraphQL handler.
8. Convert necessary data into a plain Java request context or command before calling services.
9. Call chain.next(request) to continue processing and preserve reactivity.
10. Test via HttpGraphQlTester if you need to verify web transport behavior.
11. Limit logging so credentials or sensitive variables are not recorded.

WebGraphQlRequest is the unified access point to the GraphQL payload and web request information in Spring for GraphQL. It enables WebGraphQlInterceptor to read document, operation, variables, extensions, headers, URI, remote address, and request attributes before the GraphQL engine executes. When sharing metadata with resolvers, interceptors should configure ExecutionInput and GraphQLContext rather than letting controllers depend directly on HTTP APIs. Keeping a clear boundary between transport, execution, and service makes request metadata easy to control, secure, and convenient to test.
