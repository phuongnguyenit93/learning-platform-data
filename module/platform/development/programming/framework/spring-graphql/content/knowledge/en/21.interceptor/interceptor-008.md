# Correlation ID in Interceptors

In a GraphQL request, an operation can pass through the web transport, interceptors, GraphQL execution, resolvers, DataLoaders, and multiple downstream services. When errors or latency occur, looking at a single component's logs is often insufficient to know whether those events belong to the same request. A **Correlation ID** is an identifier attached to a request so application layers and related services can link logs, traces, and processing events.

In Spring for GraphQL, a suitable place to receive or generate a Correlation ID is WebGraphQlInterceptor. The interceptor can put the ID into GraphQLContext before the operation executes. Resolvers, batch loaders, and other components in the same execution can then read the same value without depending directly on the HTTP request.

A Correlation ID supports observability and diagnostics. It is not authentication data, and it does not replace authorization, distributed tracing, or idempotency keys.

## 1. What Is a Correlation ID?

A Correlation ID is an identifier attached to a request or business flow to connect related logs and events. For example, a GraphQL request calls a resolver to fetch an order, which then calls a customer service and a payment service. If all layers log the same Correlation ID, operators can filter logs by ID to see the entire journey.

A good Correlation ID has the following characteristics:

- Unique with a very low collision probability across the system.
- Concise, easy to pass in an HTTP header, and easy to search in logs.
- Contains no personal information, tokens, tenant secrets, or sensitive business data.
- Kept consistent throughout a request and propagated to downstream calls when appropriate.
- Validated for format and length limits if received from a client or proxy.

Applications commonly use a random UUID as a new value when the request does not yet carry a trusted ID. Do not construct IDs from emails, user IDs, phone numbers, or data that could reveal identity.

## 2. Distinguishing Correlation ID, Request ID, Trace ID, and Idempotency Key

These types of IDs may coexist in a system while serving different purposes:

| Value | Purpose | Typical Scope |
| --- | --- | --- |
| Request ID | Identifies a single receipt of a request at one service | One HTTP request or one processing pass at a service |
| Correlation ID | Links logs/events of the same business flow | May span multiple services and multiple requests |
| Trace ID | Links spans within a distributed trace | One trace, spanning multiple services/spans |
| Span ID | Identifies a unit of work within a trace | One specific operation or call |
| Idempotency Key | Identifies a command intent to prevent duplicate side effects | One business operation and its retries |

W3C Trace Context defines the traceparent header to propagate trace ID and parent span ID between components. When an application uses Micrometer Tracing or OpenTelemetry, let the tracing framework manage traces/spans and propagation. The Correlation ID can be an additional application ID, or the trace ID can serve as a shared search field if the system's observability policy allows it.

Do not manually overwrite traceparent with an arbitrary Correlation ID. Trace IDs have their own format and lifecycle, whereas Correlation ID is an application convention.

An Idempotency Key also differs from a Correlation ID. When a client retries the same mutation, each attempt may be a new HTTP request with a new Correlation ID, yet it must still use the same Idempotency Key so the server recognizes it as the same command. Conversely, one GraphQL request can contain many fields while usually having only one Correlation ID for that execution.

## 3. Why Handle Correlation ID in WebGraphQlInterceptor?

WebGraphQlInterceptor sits at the web layer of Spring for GraphQL. It receives WebGraphQlRequest before the GraphQL operation executes, so it can:

- Read headers such as X-Correlation-Id or X-Request-Id.
- Validate format and decide whether to keep or replace the incoming value.
- Generate a UUID if the request does not have a valid ID.
- Put the ID into GraphQLContext via configureExecutionInput.
- Add the ID to the response header so the client can include it when reporting errors.
- Record logs or metrics around web GraphQL request processing time.

Resolvers should not depend directly on ServletRequest or HTTP headers. Putting metadata into GraphQLContext establishes a clear boundary between transport and GraphQL execution. This also allows resolvers to be tested without simulating the entire HTTP request.

Processing flow:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[WebGraphQlRequest]
    B --> C[WebGraphQlInterceptor]
    C --> D[Read or generate Correlation ID]
    D --> E[Put ID into GraphQLContext]
    E --> F[GraphQL execution]
    F --> G[Resolvers and DataLoaders]
    G --> H[Services and downstream clients]
    H --> I[Log with the same Correlation ID]
    I --> J[GraphQL response + response header]
~~~

WebGraphQlInterceptor applies to the corresponding web transport. If the application uses WebSocket, consider WebSocketGraphQlInterceptor and distinguish connection-level metadata from per-GraphQL-operation metadata.

## 4. Generating or Validating a Correlation ID

A simple policy is to accept the X-Correlation-Id header if its value matches an allowed format; if missing or invalid, generate a new UUID. The following example restricts the ID to 64 alphanumeric, dot, underscore, and hyphen characters:

~~~java
private static final Pattern SAFE_ID =
    Pattern.compile("[A-Za-z0-9._-]{1,64}");

private String resolveCorrelationId(String incoming) {
    if (incoming != null && SAFE_ID.matcher(incoming).matches()) {
        return incoming;
    }
    return UUID.randomUUID().toString();
}
~~~

This is an illustrative policy. A system may choose to reject the request when the header is malformed rather than generating a new ID, but it must enforce consistent behavior. If the ID is generated by an internal gateway, only keep the ID when the request genuinely comes from a trusted gateway and infrastructure has stripped forged headers sent by external clients.

Never trust any header value as an identity or proof of access permission. A client can set X-Correlation-Id itself. This value only serves to link logs, so spoofing it must never alter the tenant, principal, or authorization.

Do not allow overly long IDs, control characters, or newlines. This helps prevent log injection, abnormal header parsing, and hard-to-search log entries. Do not reflect an unvalidated header verbatim into responses or logs.

## 5. Implementing WebGraphQlInterceptor

The following example reads the header, generates an ID if needed, puts the value into GraphQLContext, and returns the ID in the response header:

~~~java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    public static final String HEADER_NAME = "X-Correlation-Id";
    public static final String CONTEXT_KEY = "correlationId";

    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String correlationId = resolveCorrelationId(
            request.getHeaders().getFirst(HEADER_NAME));

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context ->
                context.put(CONTEXT_KEY, correlationId)
            ).build()
        );

        return chain.next(request)
            .doOnNext(response ->
                response.getResponseHeaders().set(HEADER_NAME, correlationId));
    }

    private String resolveCorrelationId(String incoming) {
        if (incoming != null && SAFE_ID.matcher(incoming).matches()) {
            return incoming;
        }
        return UUID.randomUUID().toString();
    }
}
~~~

Key parts:

1. getHeaders().getFirst(...) reads the header from WebGraphQlRequest.
2. resolveCorrelationId validates the format and generates a UUID when needed.
3. configureExecutionInput adds correlationId to GraphQLContext before the operation runs.
4. chain.next(request) passes the request to the next interceptor or GraphQL service.
5. doOnNext adds the same ID to the response header once the response is ready.

The snippet uses WebGraphQlResponse's response headers API. When implementing, verify the exact Spring for GraphQL version your project uses and ensure the transport adapter writes response headers to the HTTP response as intended.

If other interceptors also need the Correlation ID, set ordering via @Order or design a consolidated metadata interceptor. Avoid having multiple interceptors generate IDs independently or overwrite the same context key.

## 6. Reading the Correlation ID in Resolvers

Spring for GraphQL supports @ContextValue to bind a value from GraphQLContext to a controller parameter:

~~~java
@Controller
public class OrderQueryController {

    private static final Logger log =
        LoggerFactory.getLogger(OrderQueryController.class);

    private final OrderService orderService;

    public OrderQueryController(OrderService orderService) {
        this.orderService = orderService;
    }

    @QueryMapping
    public Order orderById(
            @Argument("id") String id,
            @ContextValue("correlationId") String correlationId) {

        log.info("Loading order, correlationId={}", correlationId);
        return orderService.findById(id);
    }
}
~~~

If a resolver needs multiple pieces of execution information, it can accept DataFetchingEnvironment:

~~~java
@QueryMapping
public Order orderById(
        @Argument("id") String id,
        DataFetchingEnvironment environment) {

    String correlationId = environment.getGraphQlContext()
        .get("correlationId");
    return orderService.findById(id);
}
~~~

@ContextValue retrieves data the server attached to the execution context. It differs from @Argument, which retrieves data passed by the client for a field. A client cannot overwrite correlationId in GraphQLContext by sending a variable or argument with the same name.

If the context key may be absent in certain tests or transports, you can declare the parameter as optional via @ContextValue's required attribute and handle null appropriately. With the interceptor above, the ID is always created, so resolvers can expect the key to exist when requests pass through that interceptor.

## 7. Passing Correlation ID into DataLoaders and Batch Loaders

A batch loader may need to log when loading a batch of keys. Spring for GraphQL lets a batch loader accept BatchLoaderEnvironment and read the execution context via the corresponding API:

~~~java
registry.forTypePair(Long.class, Author.class)
    .registerMappedBatchLoader((authorIds, environment) -> {
        GraphQLContext context = (GraphQLContext) environment.getContext();
        String correlationId = context.get("correlationId");

        log.debug("Loading authors, count={}, correlationId={}",
            authorIds.size(), correlationId);

        return authorService.findAllByIdsAsync(authorIds);
    });
~~~

In the example, the loader receives the same ID that the interceptor placed into GraphQLContext. Use the exact context type and BatchLoaderEnvironment API of the GraphQL Java/Spring for GraphQL version in use.

Never store the Correlation ID in a singleton field or static mutable variable for resolvers and batch loaders to read. Multiple requests can run concurrently; shared variables will be overwritten and cause logs to carry the wrong ID. Request data must travel via GraphQLContext, Reactor Context, or an explicitly designed context propagation mechanism.

## 8. Passing the ID to Services and Downstream HTTP Calls

An easy-to-control approach is passing the Correlation ID explicitly from the resolver into the service when the service needs to call another system:

~~~java
@QueryMapping
public CompletableFuture<OrderView> orderById(
        @Argument("id") String id,
        @ContextValue("correlationId") String correlationId) {
    return orderService.findView(id, correlationId);
}
~~~

The service can add the header to WebClient:

~~~java
public CompletableFuture<Customer> findCustomer(
        String customerId, String correlationId) {

    return webClient.get()
        .uri("/customers/{id}", customerId)
        .header("X-Correlation-Id", correlationId)
        .retrieve()
        .bodyToMono(Customer.class)
        .toFuture();
}
~~~

Explicit passing makes dependencies visible and does not rely on ThreadLocal. If the system uses Micrometer Tracing or OpenTelemetry, enable standard propagation so trace context is automatically transmitted via WebClient. An application Correlation ID can be added separately when downstream systems need to link logs using internal conventions.

When making multiple downstream calls, pass the same Correlation ID for calls belonging to the same request. If a downstream service initiates a new request for an independent business workflow, decide consistently whether to preserve the original Correlation ID or create a new ID linked via trace context or business operation ID.

## 9. Correlation ID in Async and Reactive Flows

Spring for GraphQL uses reactive APIs at the web layer. WebGraphQlInterceptor returns Mono<WebGraphQlResponse>, and the request may proceed through asynchronous operators or resolvers before the response completes.

Do not use ThreadLocal to store the Correlation ID and assume every callback will read that value. CompletableFuture can run on a different thread pool; Reactor can switch schedulers. ThreadLocal/MDC does not automatically follow execution everywhere.

Safer alternatives:

- Put the ID into GraphQLContext for resolvers and DataLoaders to read per execution.
- Pass the ID explicitly to services or clients when making downstream calls.
- Use Reactor Context for metadata that needs to follow the reactive subscriber chain.
- Use Micrometer Context Propagation or a compatible mechanism to propagate MDC/SecurityContext across executors when genuinely needed.
- Use Micrometer Tracing/OpenTelemetry for trace/span context rather than rolling custom distributed tracing propagation.

Do not call block() in WebGraphQlInterceptor or on event-loop threads. Keep the chain reactive by returning the Mono from chain.next and chaining appropriate operators.

## 10. Attaching Correlation ID to MDC and Structured Logging

MDC lets logging frameworks automatically include certain fields in every log event. However, traditional MDC is based on ThreadLocal. Setting and clearing MDC around a reactive call like this can be wrong:

~~~java
MDC.put("correlationId", correlationId);
return chain.next(request)
    .doFinally(signal -> MDC.remove("correlationId"));
~~~

Calling chain.next may return the Mono immediately before the pipeline actually completes. Removal might occur on a different thread or before callbacks that need to log have run. This approach does not guarantee the context is properly preserved.

If MDC is needed, use context propagation supported by your application's logging/observability stack. With Reactor, you can use Micrometer Context Propagation and compatible configuration to bridge Reactor Context to MDC. With executors for CompletableFuture, use a TaskDecorator or wrapped executor to capture/restore context. Ensure context is restored and cleaned up after callbacks to avoid leaking IDs between tasks on the same thread.

A simpler option is logging correlationId as a structured logging field where the value is already available:

~~~java
log.info("Order lookup started, correlationId={}, orderId={}",
    correlationId, orderId);
~~~

Do not log raw GraphQL variables, tokens, cookies, or payment data just to get extra context. The Correlation ID should be a searchable log field, not a high-cardinality metric tag.

## 11. Security and Trust of Incoming IDs

A client-sent Correlation ID can be spoofed. API callers might intentionally reuse the same ID across many requests to pollute logs or complicate investigations. Therefore:

- Do not use Correlation ID to identify a user, tenant, role, or access permission.
- Restrict the length and accepted character set.
- Disallow CR/LF or control characters to prevent log/header injection.
- Only trust gateway-generated IDs when the connection comes from a trusted gateway and external headers have been sanitized.
- If an ID is invalid, generate a new one or reject per policy; do not write malicious values into logs.
- Do not embed personal data or secrets into the ID.
- Do not use Correlation ID as an idempotency key or security cache key.

If returning the ID in the response header, only echo the validated value or the newly server-generated ID. The response header helps clients provide the ID when reporting issues to operations teams.

## 12. Interceptor Chains and Multiple Transport Types

An application may have multiple WebGraphQlInterceptors: one generating the Correlation ID, one resolving locale, one measuring duration, and one adding tenant metadata. They are chained together; order matters if a later interceptor needs data a previous interceptor put into GraphQLContext.

You can use @Order to set a clear order. Standardize context key names, avoid overwrites, and keep each interceptor focused on a single concern. If an interceptor terminates a request early, decide whether the response should include the Correlation ID.

With WebSocket, a connection can persist across many GraphQL operations. Do not use a single connection-level Correlation ID for every operation if the goal is tracking individual requests. You can have a separate connection ID while generating or resolving a Correlation ID per operation/message according to the protocol and corresponding interceptor. Connection state and per-execution GraphQLContext have two different scopes.

## 13. Testing Correlation ID

Test the interceptor at the web layer to ensure the header is read, the context is set, and the response header is returned. Testing a resolver in isolation with GraphQlTester is not enough to prove the HTTP interceptor ran.

With HttpGraphQlTester built from WebTestClient, you can send headers like this:

~~~java
HttpGraphQlTester tester = HttpGraphQlTester.builder(webTestClient)
    .headers(headers -> headers.set(
        "X-Correlation-Id", "test-request-001"))
    .build();
~~~

Then send an operation through the application and use a mock service or spy to verify the resolver/service received the corresponding correlationId. To inspect response headers, use WebTestClient directly or an appropriate tester API to read HTTP response headers.

Cases that should be tested:

- A valid header is preserved and appears in GraphQLContext.
- A missing header causes the server to generate a new UUID.
- An overly long header or one with disallowed characters is replaced with a new ID or rejected per policy.
- The response returns the accepted ID.
- Two concurrent requests have separate IDs and do not overwrite each other's context.
- Resolvers and DataLoaders within the same execution read the same ID.
- Downstream clients receive the right header when passed correlationId.
- Resolver errors still produce logs carrying the right ID.
- The interceptor does not call block() and does not break the reactive chain.

Do not only assert that the response has the header. Verify that the same ID propagates all the way to the execution components you want to observe.

## 14. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Resolver does not see Correlation ID | Interceptor did not call configureExecutionInput or used a different key | Check the key and ensure it is set before chain.next |
| Each layer logs a different ID | Multiple places generating IDs or overwriting context | Generate once at the request boundary and pass forward |
| ID is lost when running CompletableFuture | Relying on ThreadLocal/MDC across different threads | Pass explicitly or configure context propagation |
| ID is lost downstream | HTTP client did not add header or tracing propagation is not configured | Pass ID via WebClient or use tracing instrumentation |
| Logs get wrong IDs across requests | Using static/singleton mutable state | Use per-execution GraphQLContext/Reactive Context |
| Log injection or malformed headers | Accepting incoming IDs without validation | Restrict characters, length, and do not reflect raw values |
| Trace UI does not group requests as expected | Confusing Correlation ID with traceparent/trace ID | Use Micrometer Tracing/OpenTelemetry for distributed tracing |
| Metrics explode in cardinality | Using unique ID as a metric tag | Put ID in logs/traces; metrics should only use bounded-cardinality tags |

## 15. Design Principles

Generate or validate the Correlation ID at the web request boundary, then put it into GraphQLContext using WebGraphQlInterceptor. Use @ContextValue or DataFetchingEnvironment for resolvers to read the ID; pass it explicitly to services and downstream clients when needed. For DataLoaders, use the execution context instead of shared variables.

Distinguish Correlation ID from trace ID, request ID, and idempotency key. Use Micrometer Tracing or OpenTelemetry to propagate distributed trace context; do not replace W3C traceparent with an arbitrary header. Never use the ID to make access control decisions and never record sensitive data in the ID or logs.

In async/reactive flows, avoid relying on ThreadLocal and ensure MDC/context propagation matches the scheduler or executor. Test the entire path from HTTP header to resolver, batch loader, downstream call, and response header.

Correlation ID is a small detail at the request boundary that brings major value when investigating incidents. In Spring for GraphQL, WebGraphQlInterceptor and GraphQLContext provide a clear channel so components within the same execution share one ID without depending on a specific transport or thread.
