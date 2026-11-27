# Separating Transport and Execution

A GraphQL API can be invoked over HTTP, WebSocket, or RSocket. Even though the ways requests are sent and responses are received differ, the schema, resolvers, and GraphQL execution rules can still be shared. Spring for GraphQL organizes its components around layered separation: transport adapters handle the protocol; the execution service turns requests into GraphQL engine calls; resolvers implement data-fetching logic.

Understanding this boundary makes servers easier to extend. You can add a new transport for new requirements without rewriting all your resolvers, and you can test GraphQL logic directly without spinning up an HTTP server. However, each transport has its own connection lifecycle, authentication model, timeouts, and data delivery semantics; those concerns still need to be handled properly at the boundary layer.

After this lesson, you will be able to explain the path of a GraphQL request in Spring for GraphQL, distinguish the responsibilities of transport and execution, choose HTTP/WebSocket/RSocket according to your needs, pass context safely to resolvers, and test each layer appropriately.

## 1. Transport and execution are two distinct responsibilities

**Transport** is how a request travels from client to server and how results are sent back. The transport governs concerns such as:

- Whether requests are sent over HTTP, WebSocket, or RSocket.
- Whether payloads are encoded in a JSON body, query parameters, or frames/messages.
- Whether a connection lives for a single request or is long-lived.
- Whether responses are sent once or as an event stream.
- How headers, cookies, tokens, metadata, and connection details are carried.
- How timeouts, payload limits, disconnects, and backpressure are enforced.

**Execution** is the process of handling a GraphQL operation against the schema. It includes:

- Parsing the GraphQL document and identifying the operation to run.
- Validating whether the operation conforms to the schema.
- Validating and coercing variables according to declared types.
- Executing fields, invoking data fetchers/resolvers, and assembling results.
- Collecting errors, returned data, and extensions.

For example, a client sends the same operation to fetch a book over HTTP or WebSocket. The request envelope and delivery mechanism differ, but GraphQL still validates fields, invokes the Query resolver, and produces results according to the same schema. Resolvers should not need to know whether a request arrived via HTTP or WebSocket unless business logic actually depends on that fact.

The boundary can be visualized as follows:

~~~mermaid
flowchart TD
    C[GraphQL client] --> T[Transport]
    T --> A[Transport adapter]
    A --> W[WebGraphQlHandler for web transport]
    A --> E[ExecutionGraphQlService]
    W --> E
    S[GraphQlSource: schema and wiring] --> E
    E --> G[GraphQL Java execution]
    G --> R[Data fetcher and resolver]
    R --> D[(Service / repository / external systems)]
    D --> R
    R --> G
    G --> E
    E --> A
    A --> T
    T --> C
~~~

The diagram illustrates the conceptual boundary. HTTP and WebSocket typically pass through the web handler/interceptor pipeline; RSocket has its own handler and integration mechanism. Specific paths vary by transport, while the GraphQL execution core can be shared.

## 2. Processing architecture in Spring for GraphQL

Spring for GraphQL combines GraphQL Java with Spring abstractions. Key components play the following roles:

| Component | Responsibility |
|---|---|
| GraphQlSource | Builds the GraphQL schema and runtime wiring from SDL and configurations for scalars, resolvers, directives, or type resolvers |
| ExecutionGraphQlService | Receives a GraphQL request at the execution layer and invokes the GraphQL engine |
| WebGraphQlHandler | Orchestrates web requests through the WebGraphQlInterceptor chain and delegates to ExecutionGraphQlService |
| WebGraphQlInterceptor | Handles web-boundary concerns such as authentication, enriching GraphQL context, logging, or adjusting responses |
| Transport handler/adapter | Translates HTTP or WebSocket requests into Spring GraphQL's request model, then converts responses back into the protocol format |
| GraphQL Java | Parses, validates, and executes operations against the schema |
| DataFetcher/resolver | Provides values for each field |

### GraphQlSource: where the schema is built

GraphQlSource is the provider of the configured GraphQL instance. It combines SDL, runtime wiring, and extension components to produce an executable schema. Components such as annotated controllers, custom scalars, type resolvers, and instrumentation participate in this configuration process.

The schema does not belong exclusively to HTTP or WebSocket. A built schema can be reused when the same application serves multiple transports. Switching from HTTP to WebSocket to support subscriptions does not require re-declaring object types or rewriting resolvers just because the protocol changed.

### ExecutionGraphQlService: entry point for execution

ExecutionGraphQlService receives a GraphQL-level request, builds an ExecutionInput, and calls GraphQL Java. The output is a GraphQL-level response containing data, errors, and extensions if any. DefaultExecutionGraphQlService is the default implementation typically configured by Spring Boot.

This component does not need to know about HTTP methods, WebSocket frames, or RSocket interaction models. Adapters are responsible for translating protocols into suitable requests before invoking the execution service.

### WebGraphQlHandler and the interceptor chain

For web transports, WebGraphQlHandler provides a shared pipeline. WebGraphQlRequest holds the GraphQL operation details along with web attributes such as URI, headers, cookies, locale, and attributes. WebGraphQlInterceptor can inspect requests, attach needed details, and call the next interceptor in the chain.

After execution completes, interceptors can also observe or adjust the response. This is well suited for logging, tracing, authentication, enriching context, and enforcing shared web-boundary policies.

RSocket has its own request and metadata model. When integrating RSocket, use RSocket-specific handler/interceptor components instead of assuming every request is a WebGraphQlRequest. What remains consistent is that business logic and the GraphQL schema are shared at the execution layer.

## 3. Request processing flow

For an HTTP request, a typical path consists of these steps:

1. The client sends a GraphQL payload to the endpoint.
2. The HTTP handler reads the body or query parameters, headers, and request metadata.
3. The adapter builds a request object that Spring GraphQL can process.
4. WebGraphQlHandler runs the WebGraphQlInterceptor chain.
5. ExecutionGraphQlService builds ExecutionInput and invokes GraphQL Java.
6. GraphQL Java parses, validates, coerces variables, and executes the operation.
7. Resolvers/data fetchers are called to retrieve data; errors are collected according to GraphQL rules.
8. The execution service creates the GraphQL response.
9. The adapter converts the response to JSON or the corresponding wire format and sends it back to the client.

This flow can be summarized as:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as HTTP adapter
    participant I as WebGraphQlInterceptor
    participant E as ExecutionGraphQlService
    participant G as GraphQL Java
    participant R as Resolver
    C->>A: HTTP request with GraphQL payload
    A->>I: WebGraphQlRequest
    I->>E: Proceed after enriching context
    E->>G: ExecutionInput
    G->>G: Parse, validate, coerce variables
    G->>R: Resolve fields
    R-->>G: Values or errors
    G-->>E: ExecutionResult
    E-->>I: GraphQL response
    I-->>A: Response after interceptor chain
    A-->>C: HTTP response
~~~

This is the general model. With WebSocket, the adapter maintains the connection and maps messages according to the protocol. With RSocket, the adapter maps request-response or request-stream interactions. Do not equate one transport message with one resolver: a single operation can invoke many resolvers, and a single WebSocket connection can carry many independent operations.

## 4. HTTP: request-response for Query and Mutation

HTTP is the common choice for Query and Mutation because its request-response model is simple and integrates easily with reverse proxies, gateways, observability, and existing web infrastructure.

With Spring Boot, the default GraphQL HTTP endpoint is typically **/graphql**. You can change the path via configuration:

~~~properties
spring.graphql.path=/api/graphql
~~~

A POST request typically sends a JSON body:

~~~http
POST /api/graphql HTTP/1.1
Content-Type: application/json
Authorization: Bearer <access-token>

{
  "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
  "operationName": "FindBook",
  "variables": {
    "id": "book-01"
  }
}
~~~

Common fields in the request payload:

| Field | Meaning |
|---|---|
| query | GraphQL document containing one or more operations |
| operationName | Name of the operation to execute when the document defines multiple operations |
| variables | Input variable values |
| extensions | Extended metadata agreed upon between client and server |

A successful response can look like:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "title": "GraphQL with Spring"
    }
  }
}
~~~

If a field encounters an error, GraphQL can return both the data already fetched and an errors array:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "title": null
    }
  },
  "errors": [
    {
      "message": "Unable to load book title",
      "path": ["book", "title"]
    }
  ]
}
~~~

Response shape and HTTP status code are two separate layers of information. Clients should inspect status, content type, and the GraphQL response body. A GraphQL execution error does not mean the entire HTTP request failed at the network layer; conversely, connection or gateway errors can occur before the GraphQL engine is ever invoked.

GraphQL over HTTP may allow GET for Queries depending on implementation and protocol rules. Mutations should not be sent over GET because GET is expected to be a safe method that does not mutate state. POST is usually the cleanest choice for both Queries and Mutations. If GET is used, note that the query and variables appear in the URL and can show up in browser history, proxy logs, or access logs.

HTTP works well when each call can complete with a finite response. It can also be used for high-latency queries, provided timeouts across client, server, and gateway are aligned consistently. Subscriptions produce an ongoing stream of results and therefore need a transport with explicit streaming support.

## 5. WebSocket: long-lived connections and Subscriptions

WebSocket begins with an HTTP handshake and upgrades to a bidirectional connection. Once established, client and server can exchange multiple messages without opening a new HTTP request for each message.

Spring for GraphQL supports GraphQL over WebSocket for operations requiring communication over a long-lived connection, especially Subscriptions. WebSocket can also carry Queries and Mutations; choosing the transport does not alter the meaning of those operations.

In the modern GraphQL over WebSocket protocol, client and server exchange messages following connection and operation lifecycles. A typical flow:

1. The client opens a WebSocket connection and negotiates an appropriate subprotocol, typically **graphql-transport-ws**.
2. The client sends **connection_init**, optionally with authentication payload or metadata.
3. The server acknowledges the connection with **connection_ack**.
4. The client sends **subscribe** with the operation and variables.
5. The server emits **next** messages whenever results arrive.
6. The client or server sends **complete** when the operation ends; **error** messages represent operation errors per the protocol.
7. When no longer needed, the client closes the connection.

Example of a GraphQL subscription:

~~~graphql
subscription OnBookPublished($authorId: ID!) {
  bookPublished(authorId: $authorId) {
    id
    title
    publishedAt
  }
}
~~~

Subscription resolvers typically provide a Publisher or a reactive event source. Each emitted event triggers execution of the selection set to produce the payload sent to the client. Distinguish the two parts: the event source produces values; GraphQL execution applies the selection set to each value to build a response.

A single WebSocket connection can carry multiple operations. Each operation has its own identifier in the protocol and can be terminated independently. Closing one subscription does not necessarily close the entire connection; closing the connection requires cleaning up every operation bound to that connection.

WebSocket is beneficial when clients need continuous updates such as order statuses, notifications, or live monitoring data. In return, the server must manage long-lived connections, connection and subscription limits, heartbeats, timeouts, reconnects, and cleanup. Do not open subscriptions for every screen if the client only needs a one-time read.

## 6. RSocket: request-response, streams, and backpressure

RSocket is a message-oriented protocol supporting multiple interaction models. Spring for GraphQL integrates with RSocket to carry GraphQL requests across these interaction models.

| RSocket interaction model | Common GraphQL usage |
|---|---|
| Request-response | Query or Mutation returning a single result |
| Request-stream | Subscription emitting multiple results over time |
| Fire-and-forget | Not a typical choice for GraphQL operations that expect a response |
| Request-channel | Bidirectional stream exchange; use only when the application has a specific use case and appropriate support |

A notable feature of RSocket is built-in backpressure on data streams. Subscribers can regulate how many items they wish to receive, helping the system coordinate emission and consumption rates. That alone does not automatically bound resolver or database query cost; the server still needs query limits, subscription limits, payload size limits, and processing resource caps.

RSocket is often well suited for service-to-service systems or applications already using RSocket for reactive communication. Choosing RSocket requires evaluating support across gateways, clients, deployment infrastructure, and observability tooling. For standard web applications, HTTP for request-response and WebSocket for subscriptions are often easier to operate.

RSocket uses its own metadata and routing. Therefore, do not assume HTTP headers or servlet requests exist in every resolver. If business logic needs tenant, principal, or trace context, map the information from RSocket metadata into the GraphQL context through the appropriate integration point.

## 7. Transport-independent execution semantics

Whether a request arrives via HTTP, WebSocket, or RSocket, GraphQL operations follow GraphQL execution rules:

- **Query:** fields at the same level may execute in parallel; do not rely on resolver execution order in Queries.
- **Mutation:** top-level fields execute sequentially in the order they appear in the operation. This allows expressing ordered state changes within a single mutation operation.
- **Subscription:** a subscription operation has a single root field producing an event source. For each event, the server executes the selection set to produce a new response.

Query example:

~~~graphql
query Dashboard {
  profile {
    id
    name
  }
  notifications {
    id
    message
  }
}
~~~

Resolvers for **profile** and **notifications** may run concurrently. If they both mutate shared mutable state or depend on execution order, that design can cause unpredictable bugs.

Mutation example:

~~~graphql
mutation CompleteOrder($id: ID!) {
  reserveInventory(orderId: $id) {
    reservationId
  }
  confirmOrder(orderId: $id) {
    status
  }
}
~~~

Top-level mutation fields are processed sequentially within the operation. However, sequential execution does not automatically create a database transaction. If two changes must succeed or roll back together, manage transactions at the appropriate service layer.

The transport also does not alter rules for nullability, validation, field selection, authorization, or how GraphQL represents partial data and errors. Those rules belong to the schema, the execution engine, and server policies.

## 8. Propagating authentication and GraphQL context

Resolvers need user details, tenant, correlation ID, or locale in certain business workflows. However, resolvers should not read directly from a specific transport API. Instead, the boundary layer extracts details from the request and places them into the GraphQL execution context.

With HTTP, information may come from the Authorization header, cookies, or request attributes. With WebSocket, information may be sent during the handshake or in the connection initialization payload. With RSocket, information may live in metadata. Each transport has a different entry point, but once authenticated, the application can normalize the required values into the GraphQL context.

Example using WebGraphQlInterceptor to put a tenant identifier into the GraphQL context:

~~~java
@Component
public class TenantGraphQlInterceptor implements WebGraphQlInterceptor {

    private final TenantResolver tenantResolver;

    public TenantGraphQlInterceptor(TenantResolver tenantResolver) {
        this.tenantResolver = tenantResolver;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String tenantId = tenantResolver.resolve(request.getHeaders());

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("tenantId", tenantId)).build());

        return chain.next(request);
    }
}
~~~

A resolver can read the context via DataFetchingEnvironment:

~~~java
@QueryMapping
public Book book(
        @Argument String id,
        DataFetchingEnvironment environment) {

    String tenantId = environment.getGraphQlContext().get("tenantId");
    return bookService.findBook(tenantId, id);
}
~~~

This example is for web transports. With RSocket, extract the tenant from metadata and place it into context using the corresponding RSocket integration. Do not expect an HTTP interceptor to automatically run for every transport type.

Important security principles:

- Authenticate at the transport boundary before allowing operations to access protected data.
- Authorize per user and per field/resource in the appropriate service or resolver; having a valid connection does not mean every field may be accessed.
- For WebSocket, verify identity during handshake or connection initialization and define policies for token expiration, revocation, closing connections, and re-authentication.
- Never treat client-sent metadata such as tenant ID or role as trustworthy unless verified.
- Never store mutable user state in a singleton interceptor or shared variable across requests; context must be scoped to the request/operation.
- Never log access tokens, session secrets, or sensitive data.

## 9. Distinguishing interceptors, instrumentation, and resolvers

Extension points in Spring for GraphQL and GraphQL Java serve different purposes:

| Mechanism | Appropriate scope | Example |
|---|---|---|
| Transport adapter | Protocol and wire format | HTTP body, WebSocket message, RSocket payload |
| WebGraphQlInterceptor | Web GraphQL request/response boundary | Authentication, context, request logging, response headers |
| RSocket-specific integration | RSocket metadata and lifecycle | Mapping principal or trace metadata |
| GraphQL Instrumentation | GraphQL execution lifecycle | Timing execution, tracking fields, tracing |
| DataFetcherExceptionResolver | Translating data fetcher exceptions into GraphQL errors | Normalizing business error codes |
| Resolver/DataFetcher | Logic to fetch field data | Calling services, repositories, or external APIs |

For example, recording the URI and request ID is a transport-boundary concern. Measuring resolver duration or executed field count is an execution concern. Checking whether a user is allowed to view a specific invoice belongs to business security logic. Placing concerns in the right layer keeps the same resolver working consistently across multiple transports.

Not every error passes through a resolver. Parse, validation, or variable coercion errors can occur before any resolver is invoked. Connection, handshake, or payload decoding errors can occur before the request reaches the GraphQL engine. Logging and monitoring must distinguish these phases to pinpoint root causes.

## 10. Configuring transports in Spring Boot

A Spring Boot application typically starts with the GraphQL starter and one web runtime:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

If the application uses WebFlux, choose the WebFlux starter instead of the Spring MVC web starter. There is no need to include both web stacks in the same application without a clear reason.

SDL schemas typically live under:

~~~text
src/main/resources/graphql/
~~~

Spring Boot auto-configures the GraphQL source and HTTP endpoint by convention. You can change the endpoint with:

~~~properties
spring.graphql.path=/api/graphql
~~~

To enable WebSocket, add WebSocket support matching the web stack in use and configure the path:

~~~properties
spring.graphql.websocket.path=/graphql
~~~

The WebSocket path can match the HTTP path because upgrade handshakes and HTTP requests are distinguished by protocol mechanics. When deploying behind a reverse proxy, configure the proxy to forward WebSocket upgrades and set timeouts long enough for persistent connections. Do not assume changing the HTTP path automatically configures your entire gateway or proxy.

RSocket is configured through Spring's RSocket integration. Applications must select routes, mappings, serialization, authentication metadata, and interaction models matching their infrastructure. Exact configuration depends on the RSocket topology and the Spring Boot/Spring for GraphQL version in use; the architectural rule to preserve is that the RSocket handler delegates requests into the GraphQL execution service rather than duplicating schemas and resolvers.

## 11. Testing execution and testing transport

Because transport and execution are separated, you can test at multiple levels:

| Testing level | Appropriate tool | What to verify |
|---|---|---|
| Resolver/service | Standard unit tests | Business logic, authorization, data processing |
| GraphQL execution | ExecutionGraphQlServiceTester or service-level tester | Schema, operations, variables, resolver mappings, errors |
| Web GraphQL pipeline | WebGraphQlTester | Interceptors, context, execution, and web responses |
| HTTP endpoint | HttpGraphQlTester | URL, headers, serialization, status codes, and responses |
| WebSocket | WebSocketGraphQlTester | Handshake, protocol, multiple messages, subscriptions, and cleanup |
| RSocket | RSocketGraphQlTester | Route, metadata, request-response, and request-stream |

Example of testing an operation at the GraphQlTester level:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-01")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("GraphQL with Spring");
~~~

Execution-level tests are great for quickly verifying schemas and resolvers. However, they do not prove that the HTTP endpoint accepts the expected content type, that the WebSocket handshake succeeds, or that RSocket metadata is decoded properly. Those parts require testing through the corresponding transport.

For Subscriptions, verify both event delivery and stream lifecycle: whether events carry the right payload, whether client cancellation stops the source emitter when appropriate, how errors are delivered to clients, and whether closing the connection releases resources. Merely testing that a resolver returns a Publisher is not enough to prove the protocol works.

## 12. Choosing a transport by use case

| Need | Typically suitable choice | Reason |
|---|---|---|
| Reading and writing data via request-response | HTTP | Simple, compatible with web infrastructure and gateways |
| Client needs continuous updates over a bidirectional connection | WebSocket | Long-lived connections and multiple message exchanges |
| Reactive services exchanging request-response and streams | RSocket | Multiple interaction models and backpressure |
| Testing schemas/resolvers without network overhead | Execution-level test | Focuses on GraphQL execution |

Do not choose a transport merely because it is newer or has higher theoretical throughput. Check whether clients support the protocol, whether gateways can forward it, whether the system truly needs streaming, and whether operations teams can monitor long-lived connections.

An application can support multiple transports simultaneously: HTTP for Queries/Mutations, WebSocket for Subscriptions, or RSocket for internal communication. In that setup, schemas and resolvers can be shared, while authentication, context, and timeouts are wired per transport using the appropriate mechanism.

## 13. Common design mistakes

| Issue | Consequence | How to address |
|---|---|---|
| Putting HTTP header logic directly inside resolvers | Resolvers are hard to reuse over WebSocket/RSocket | Normalize required information into GraphQL context |
| Treating a WebSocket connection as equivalent to one GraphQL operation | Fails to manage multiple operations on the same connection properly | Separate connection lifecycle from operation lifecycle |
| Using HTTP request-response for long-running event streams | Hard to handle streaming and disconnects | Use a transport that supports streaming properly |
| Testing only ExecutionGraphQlService | Misses handshake, route, or serialization errors | Add tests over the actual transport |
| Authenticating only at WebSocket handshake while ignoring token lifecycle | Long-lived connections may retain expired permissions | Design expiration, revocation, and re-authentication |
| Trusting client-supplied tenant/role values | Risk of cross-tenant access or privilege escalation | Verify claims/metadata on the server |
| Logging entire payloads and headers | May leak tokens or sensitive data | Redact sensitive fields and log only needed metadata |
| Failing to limit subscription counts | Increases load and holds resources long-term | Enforce limits, timeouts, quotas, and cleanup |
| Assuming RSocket backpressure automatically bounds GraphQL cost | Resolvers or databases can still be overloaded | Limit query complexity, batch size, and resources |

## 14. Checklist when designing multi-transport support

Before enabling multiple transports on a GraphQL server, review:

1. Are the schema and resolvers truly independent of HTTP/WebSocket/RSocket?
2. Does each transport have an appropriate adapter and authentication mechanism?
3. Are principal, tenant, locale, and trace ID populated into the GraphQL context consistently?
4. Are authorization policies enforced across every entry point?
5. Are timeouts, payload size, query depth/complexity, and concurrency bounded?
6. Do Subscriptions have count limits, lifetime limits, and cleanup on client disconnect?
7. Do logs and tracing distinguish transport errors from parse, validation, and execution errors?
8. Are both the execution service and all deployed transports tested?

Separating transport from execution allows Spring for GraphQL to share schemas, resolvers, and business logic across multiple communication modes. Transport adapters handle protocol specifics; the execution service and GraphQL Java execute operations against the schema. Maintaining this boundary makes applications easier to extend across protocols, easier to test, and less coupled to connection details, while still allowing transport-specific security and operational policies.
