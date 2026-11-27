# ExecutionGraphQlService in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain the role of `ExecutionGraphQlService` in the Spring for GraphQL architecture.
- Distinguish between `ExecutionGraphQlService`, `DefaultExecutionGraphQlService`, `GraphQlSource`, and `WebGraphQlHandler`.
- Describe the path of a GraphQL request from transport to the GraphQL Java engine and back to the client.
- Understand the data `ExecutionGraphQlRequest` carries into execution and how the response is produced.
- Know how Spring Boot provides the default execution service and when to replace or wrap the service.
- Choose the right extension point for context, error handling, logging, metrics, and testing.
- Avoid putting business logic or transport handling into the execution service at the wrong layer.

## 1. What is ExecutionGraphQlService?

`ExecutionGraphQlService` is the contract for executing a GraphQL request in Spring for GraphQL. It receives a request represented as a Spring GraphQL object, passes that request to the GraphQL runtime, and returns the execution result using the reactive model.

You can summarize its responsibility in one sentence: **receive operation details, ask the GraphQL engine to execute that operation, and return the result to the caller**.

The contract looks like this:

~~~java
public interface ExecutionGraphQlService {

    Mono<ExecutionGraphQlResponse> execute(ExecutionGraphQlRequest request);
}
~~~

Key data types:

- `ExecutionGraphQlRequest` represents the request to execute, including the GraphQL document, operation name, variables, and relevant contextual information.
- `ExecutionGraphQlResponse` represents the execution result, including data, errors, and extensions produced by the GraphQL runtime.
- `Mono` is Reactor's return type, representing an asynchronous result that may complete later or terminate with an error at the reactive layer.

`ExecutionGraphQlService` is a server-side component, not a URL endpoint that clients call directly. Clients send requests over HTTP, WebSocket, or a transport supported by the application. The transport handler passes the request into the web processing chain; that chain is what invokes the execution service.

In a typical Spring Boot application, you do not need to write an implementation of this interface yourself. Spring Boot can configure the default implementation based on `GraphQlSource` and the registered GraphQL components.

## 2. Position of the execution service in the architecture

A Spring for GraphQL application has multiple layers. Each layer handles a distinct responsibility:

| Component | Responsibility |
| --- | --- |
| HTTP, WebSocket, or RSocket handler | Receives data from the transport and writes responses back to the client |
| `WebGraphQlHandler` | Orchestrates request processing at the GraphQL web layer |
| `WebGraphQlInterceptor` | Intercepts web requests/responses, adding context or metadata |
| `ExecutionGraphQlService` | Orchestrates the execution of a GraphQL request |
| `GraphQlSource` | Provides the GraphQL runtime built from the schema and runtime wiring |
| GraphQL Java engine | Parses, validates, selects the operation, and executes fields |
| DataFetcher or controller | Provides values for fields according to the schema |

Overall flow:

~~~mermaid
flowchart TD
    A["GraphQL client"] --> B["HTTP / WebSocket / RSocket"]
    B --> C["WebGraphQlHandler"]
    C --> D["WebGraphQlInterceptor chain"]
    D --> E["ExecutionGraphQlService"]
    E --> F["GraphQL engine from GraphQlSource"]
    F --> G["DataFetcher / @Controller"]
    G --> F
    F --> H["ExecutionGraphQlResponse"]
    H --> C
    C --> B
    B --> A
~~~

`GraphQlSource` and `ExecutionGraphQlService` are closely related but do not replace each other:

- `GraphQlSource` provides the configuration and GraphQL runtime, built from SDL schemas, runtime wiring, scalars, instrumentation, and related components.
- `ExecutionGraphQlService` receives each request and instructs the runtime to execute that request.

An easy comparison to remember: `GraphQlSource` provides the configured GraphQL engine; the execution service feeds each operation into that engine.

`WebGraphQlHandler` sits at a higher layer. It connects the interceptor chain with the execution service and creates responses for the transport layer. Therefore, when you need to read HTTP headers, determine user identity, or enrich per-request data, an interceptor is usually the more appropriate extension point.

## 3. Path of a request

Suppose a client sends an operation:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "id": "book-42"
}
~~~

A request passes through the following high-level steps.

1. **Transport receives the request.** The HTTP handler or WebSocket handler receives the payload from the client and converts it into a request that Spring for GraphQL can process.
2. **Web handler builds execution context.** `WebGraphQlHandler` runs the `WebGraphQlInterceptor` chain. Interceptors can add authentication details, tenant, correlation ID, or other contextual data.
3. **Execution service receives the request.** `ExecutionGraphQlService.execute(...)` receives the `ExecutionGraphQlRequest` prepared for execution.
4. **GraphQL runtime processes the operation.** GraphQL Java parses the document, validates syntax and schema conformance, selects the operation, validates variables, and executes the selection set.
5. **Fields are resolved.** The runtime calls the corresponding DataFetchers. In a Spring application, DataFetchers may be created from controller methods such as `@QueryMapping`, `@SchemaMapping`, or other wiring mechanisms.
6. **Results are packaged.** The execution service returns `ExecutionGraphQlResponse` to the web handler.
7. **Transport sends the response.** The web handler and transport convert the result into a response matching the protocol the client is using.

The execution service does not decide the business data for the `book` field itself. It initiates execution; the DataFetcher or controller is responsible for supplying the field value.

### 3.1. Where do parsing and validation happen?

The client sends a document as GraphQL text. GraphQL Java is responsible for parsing the document, validating the operation against the schema, and executing it. Errors such as syntax mistakes, selecting nonexistent fields, or passing arguments of the wrong type are detected during GraphQL engine processing.

Therefore, do not think of the execution service as a parser or a place to re-implement GraphQL rules. The service orchestrates execution through the configured runtime.

### 3.2. A request can contain multiple operations

A document can declare multiple operations:

~~~graphql
query GetBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}

query GetBooks {
    books {
        id
        title
    }
}
~~~

When a document contains multiple operations, the request must specify the operation name so the GraphQL runtime knows which operation to execute. If the document contains only a single operation, the operation name can be omitted.

The execution service passes the operation name along with the document and variables into execution. Selecting the operation and validating it belong to the GraphQL engine.

## 4. ExecutionGraphQlRequest and ExecutionGraphQlResponse

### 4.1. What does a request contain?

`ExecutionGraphQlRequest` is the request representation at the execution layer. Depending on how the request is created and which transport is used, key fields typically include:

| Information | Purpose |
| --- | --- |
| Document | The text of the GraphQL operation |
| Operation name | Selects the operation when the document defines multiple operations |
| Variables | Input values for variables declared in the operation |
| Extensions | Extended request metadata, such as persisted query conventions |
| GraphQL context | Contextual data shared across a single execution |
| Locale | Language/region that may be used in processing or message resolution |
| Execution ID | Identifier for a single execution, useful for tracing and correlating logs |

Not every transport provides every piece of metadata. For example, HTTP headers only exist at the web request layer; a pure execution request should not be treated as an object holding all details of an HTTP exchange.

Variables are validated against the types declared in the schema. If an operation requires `ID!` and the client does not supply a valid value, the GraphQL runtime can return an error before any business resolver is invoked.

### 4.2. Responses contain data and errors

A successful response typically has the structure:

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

If a field encounters an error during execution, the response can contain both `data` and `errors`:

~~~json
{
    "data": {
        "book": null
    },
    "errors": [
        {
            "message": "Book not found",
            "path": ["book"]
        }
    ]
}
~~~

This is an illustrative structure. Actual error contents depend on the GraphQL engine, DataFetchers, and the application's error handling mechanism.

Distinguish between two groups of errors:

- **Parse/validation/coercion errors:** the operation has invalid syntax, does not match the schema, or variables are invalid. The GraphQL engine cannot execute the operation as requested.
- **Execution errors:** a DataFetcher or component called while resolving a field encounters an error. GraphQL may still return data for other fields alongside the error list.

`ExecutionGraphQlResponse` is the result at the Spring GraphQL layer. The transport layer converts this result into a response appropriate for HTTP or the protocol in use. Thus, a GraphQL error does not mean every case must turn into an HTTP 500.

## 5. DefaultExecutionGraphQlService

`DefaultExecutionGraphQlService` is the standard implementation of `ExecutionGraphQlService`. It uses `GraphQlSource` to obtain the GraphQL runtime and executes requests via GraphQL Java.

In a Spring Boot application, auto-configuration usually creates the default execution service once the required components are present. With standard configuration, you only need to provide the schema, runtime wiring, and resolvers; you do not need to create the service manually.

If assembling Spring GraphQL outside auto-configuration, you can create the default implementation from `GraphQlSource`:

~~~java
@Bean
ExecutionGraphQlService executionGraphQlService(GraphQlSource graphQlSource) {
    return new DefaultExecutionGraphQlService(graphQlSource);
}
~~~

This configuration illustrates the case where you manage beans explicitly. If the application already uses auto-configuration and has no requirement to customize the execution service, let Spring Boot supply the default implementation.

### 5.1. Why keep the default implementation?

The default implementation connects Spring GraphQL's abstractions with GraphQL Java. It lets the application share an execution mechanism already integrated with:

- `GraphQlSource` and the runtime schema.
- Spring GraphQL's request/response abstractions.
- The reactive model used in the execution API.
- Dedicated extension points such as interceptors, instrumentation, and error handling.

Writing a custom implementation just to call a resolver or query a repository violates responsibility boundaries. Resolvers are the right place for business logic; the execution service should retain the role of orchestrating the entire operation.

## 6. Enriching contextual data before execution

A common requirement is passing user information, tenant, or correlation ID into field resolution. This data usually comes from HTTP headers, security context, or transport metadata.

`WebGraphQlInterceptor` is the right extension point because it operates at the web request layer before invoking the execution service.

Example of adding a tenant to the GraphQL context:

~~~java
@Component
class TenantGraphQlInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String tenantId = request.getHeaders().getFirst("X-Tenant-Id");

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("tenantId", tenantId)));

        return chain.next(request);
    }
}
~~~

In this example, the interceptor reads the request header and puts the tenant ID into the GraphQL context. DataFetchers within the same execution can access this data through the context.

Example of a resolver reading the context value:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book book(
            @Argument String id,
            DataFetchingEnvironment environment) {

        String tenantId = environment.getGraphQlContext()
                .get("tenantId");

        return bookService.findById(tenantId, id);
    }
}
~~~

This example only demonstrates how to propagate context. In a real application, the tenant ID must be authenticated and bound to a verified identity or access permission. Never trust a header sent directly by a client if that header could allow a user to access another tenant's data.

Guidelines when using the GraphQL context:

- Only store data needed within a single execution.
- Use the context to pass metadata and contextual information, not as a dumping ground for all application state.
- Do not include secrets or sensitive information in logs when logging context.
- Create data per request; avoid sharing a single mutable map across multiple requests.
- Use the application's authentication and authorization mechanisms to verify identity before putting trusted information into the context.

## 7. ExecutionGraphQlService and other extension points

Not every customization requirement calls for replacing the execution service. Spring for GraphQL provides extension points at multiple layers.

| Requirement | Appropriate extension point |
| --- | --- |
| Read HTTP headers, enrich context, handle web metadata | `WebGraphQlInterceptor` |
| Change GraphQL execution behavior at the service level | `ExecutionGraphQlService` |
| Build schema, runtime wiring, scalars, and DataFetchers | `GraphQlSource` |
| Handle exceptions thrown from DataFetchers | `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler` |
| Measure or hook into GraphQL engine lifecycle | GraphQL Java `Instrumentation` |
| Execute business logic for a field | Controller method, `@SchemaMapping`, or DataFetcher |
| Batch loading and reducing N+1 | `BatchLoaderRegistry`, DataLoader, and `@BatchMapping` |

### 7.1. When should you customize ExecutionGraphQlService?

Only consider customizing it when you need to alter execution orchestration behavior at the service level and other specialized extension points cannot satisfy the requirement. Examples include:

- Wrapping the service to measure execution time at the service boundary.
- Integrating a custom execution orchestration mechanism for the application.
- Applying a cross-cutting policy that must run before or after every execution specifically at this layer.

If the goal is merely reading headers, adding a user to context, or converting exceptions into GraphQL errors, prefer an interceptor or exception resolver. If the goal is fetching data for a field, implement a DataFetcher or controller.

### 7.2. Wrapping the service to record timing

A decorator can delegate to another implementation and record completion duration:

~~~java
final class MeasuredExecutionGraphQlService
        implements ExecutionGraphQlService {

    private final ExecutionGraphQlService delegate;
    private final GraphQlMetrics metrics;

    MeasuredExecutionGraphQlService(
            ExecutionGraphQlService delegate,
            GraphQlMetrics metrics) {
        this.delegate = delegate;
        this.metrics = metrics;
    }

    @Override
    public Mono<ExecutionGraphQlResponse> execute(
            ExecutionGraphQlRequest request) {

        long startedAt = System.nanoTime();

        return this.delegate.execute(request)
                .doOnNext(response -> this.metrics.record(
                        request.getOperationName(),
                        System.nanoTime() - startedAt));
    }
}
~~~

`GraphQlMetrics` in the example is an application-defined component. The decorator preserves the delegate's result and only observes when the response is emitted.

In real implementations, decide how to record error cases or cancelled reactive subscriptions as well. You can use operators such as `doOnError` or `doFinally` depending on measurement goals. Avoid logging full documents and variables by default because they may contain sensitive data.

When registering a decorator in Spring, make sure there is a real delegate and only one execution service is selected for the web handler. Avoid bean configurations that inject themselves or create circular dependencies. If you need to wrap the default implementation, explicitly create the delegate from `GraphQlSource` and wrap that delegate.

## 8. The reactive model of the execution service

The `ExecutionGraphQlService` API returns `Mono<ExecutionGraphQlResponse>`. This allows the caller layer to integrate with asynchronous processing in Spring GraphQL.

Distinguish between:

- `Mono` represents the result of a single invocation of the execution service.
- `Flux` represents a sequence of elements in Reactor.
- A GraphQL Subscription represents an operation producing an event stream according to the GraphQL model and a subscription-capable transport.

Do not conclude that because the execution service returns `Mono`, a Subscription can only emit one event. `Mono` here is the asynchronous result of the service call; the GraphQL result of a subscription has its own stream semantics and is handled accordingly by the Spring GraphQL/transport layers.

### 8.1. Avoid blocking the processing thread

When writing code around the execution service, do not call blocking operations such as `block()` inside the reactive request chain. Blocking can reduce concurrency or cause deadlocks depending on the execution environment.

Example to avoid on the request path:

~~~java
ExecutionGraphQlResponse response =
        delegate.execute(request).block();
~~~

Keep the result reactive and chain additional processing with appropriate operators:

~~~java
return delegate.execute(request)
        .doOnNext(this::recordResponse);
~~~

If an underlying business service is blocking, run it on an appropriate scheduler or use Spring-supported blocking integration. Do not arbitrarily hop every segment of processing onto another scheduler without understanding the application's execution model.

## 9. Error handling in relation to the execution service

The execution service returns results from the GraphQL runtime. How an application translates DataFetcher exceptions into GraphQL errors is typically handled at error-specific extension points.

Example of a business exception:

~~~java
class BookNotFoundException extends RuntimeException {

    BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
~~~

A resolver can throw the exception when the book is not found:

~~~java
@QueryMapping
Book book(@Argument String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

The application can map the exception to a GraphQL error using `DataFetcherExceptionResolver` or Spring for GraphQL's `@GraphQlExceptionHandler` mechanism. Illustrative example with controller advice:

~~~java
@ControllerAdvice
class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    GraphQLError handle(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Book not found")
                .errorType(ErrorType.NOT_FOUND)
                .build();
    }
}
~~~

The example above focuses on how exceptions are mapped; exact imports and error code types should match the Spring GraphQL version and the application's error conventions.

Do not catch every exception and return a fake success response. Hiding system errors makes it hard for logs and monitoring to pinpoint root causes. Separate business errors safe to expose to clients from internal errors that should be logged and handled safely.

The execution service is not the right place to construct error messages for individual business cases. It can observe execution outcomes overall; resolvers and exception resolvers understand field and exception semantics much better.

## 10. Testing the execution service

Spring for GraphQL provides testers at different layers. If the goal is to verify GraphQL execution without starting an HTTP server, you can use `ExecutionGraphQlServiceTester`.

Example:

~~~java
ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);

tester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

The test sends the operation and variables to the execution service, then asserts fields in the result. It is well suited for verifying the schema, DataFetchers, and execution at the service layer.

Choose the tester according to the scope you want to verify:

| Tester | Testing scope |
| --- | --- |
| `ExecutionGraphQlServiceTester` | GraphQL execution via the execution service |
| `WebGraphQlTester` | Processing chain at the GraphQL web layer, including interceptors |
| `HttpGraphQlTester` | Request/response over the HTTP endpoint |
| `WebSocketGraphQlTester` | Interaction over WebSocket |
| `RSocketGraphQlTester` | Interaction over RSocket |

For example, if you need to verify an interceptor reading a header and putting a tenant into the GraphQL context, testing the execution service directly may bypass the interceptor. In that case, test at the `WebGraphQlHandler` or HTTP tester layer to verify that the entire processing chain works.

A sensible test suite can cover:

- Valid operations with valid variables.
- Nonexistent fields or variables of the wrong type.
- Resolvers returning data successfully.
- Resolvers throwing exceptions and exceptions mapping properly.
- Context populated by interceptors being accessible from resolvers.
- Responses containing partial data when one field errors while other fields still execute.
- Subscriptions verified over the appropriate transport and tester if the application uses them.

## 11. Performance, security, and operations

The execution service is a convenient boundary for observing a GraphQL execution, though performance and security also depend on other layers.

### 11.1. Metrics

Useful metrics include:

- Execution count by operation name.
- Execution duration at the request level.
- Error counts by normalized error type or code.
- Rate of cancelled or timed-out requests.
- Query depth and complexity distribution if the application has corresponding measurement mechanisms.

Do not use raw operation names as metric labels unconditionally if clients can send an unbounded number of arbitrary names. Limit cardinality using a known operation list or normalized labels.

### 11.2. Protecting data in logs

Documents and variables can contain personal information, tokens, or business data. Before logging, decide which data may be stored and which must be masked or omitted.

Prefer correlation IDs, normalized operation names, processing duration, and error codes. Do not log access tokens, session IDs, or full variables purely for debugging convenience.

### 11.3. Resource limits

An execution service can receive operations requesting many deeply nested fields or a large volume of data. Enforcing query depth limits, query complexity limits, timeouts, pagination, and request size limits usually needs to be configured at the corresponding GraphQL engine and transport extension points.

The execution service does not automatically solve N+1. To reduce database query counts, applications need well-designed resolvers and DataLoader, `BatchLoaderRegistry`, or `@BatchMapping` where appropriate.

### 11.4. Per-request and per-field security

Authentication at the web layer establishes request identity. Authorization may need to be checked in business services or field resolvers depending on data rules.

Putting user information into the GraphQL context does not automatically create security. Resolvers must still verify whether the user has permission to access the requested object or action. In particular, never trust a client-supplied tenant ID, role, or user ID unless it has been verified.

## 12. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| `ExecutionGraphQlService` is a controller receiving HTTP | It is a service executing GraphQL requests; transports and web handlers handle HTTP |
| `GraphQlSource` and execution service are the same | Source provides the runtime; the service uses the runtime to execute requests |
| Every field needs to be written inside the execution service | Fields are resolved by DataFetchers or controllers registered with the schema |
| Reading headers requires modifying the execution service | Use `WebGraphQlInterceptor` at the web layer |
| All exceptions should be caught in the execution service | Use exception resolvers or `@GraphQlExceptionHandler` for DataFetcher errors |
| Returning `Mono` means Subscriptions cannot stream | `Mono` is the async result of the service call; subscriptions have their own stream semantics |
| Replacing the default implementation makes GraphQL faster | Only replace when there is a specific requirement and measurements proving the benefit |
| Using the execution service automatically solves N+1 | N+1 must be addressed in resolver design and batch loading mechanisms |

## 13. Workflow when intervening in the execution service

When a requirement arises to modify the execution layer, determine the exact scope before making changes:

1. **Identify where the requirement originates.** Does the issue lie in transport, web request, context, the GraphQL engine, or a resolver?
2. **Choose the appropriate extension point.** Use interceptors for web metadata; use resolvers for field logic; only use the execution service when service-level orchestration is needed.
3. **Keep the default implementation if possible.** Only replace or wrap `DefaultExecutionGraphQlService` when there is a concrete technical reason.
4. **Preserve the reactive chain.** Do not block results with `block()` in the request path.
5. **Verify results and errors.** Ensure responses preserve GraphQL semantics, including partial data and errors.
6. **Test at the right layer.** Service tester for execution; web or transport tester for interceptors and protocols.
7. **Observe after deployment.** Measure latency, errors, and resource usage; protect sensitive data in logs.

## 14. Summary

`ExecutionGraphQlService` is the central abstraction for executing GraphQL requests in Spring for GraphQL. It accepts `ExecutionGraphQlRequest`, uses the GraphQL runtime supplied by `GraphQlSource`, and returns `ExecutionGraphQlResponse` using the reactive model.

In a standard Spring Boot application, `DefaultExecutionGraphQlService` satisfies most needs and is auto-configured. When extending behavior, pick the right layer: `WebGraphQlInterceptor` for web request metadata and context, DataFetchers or controllers for field logic, exception resolvers for errors, and instrumentation for observing the GraphQL engine. Only customize the execution service when the requirement genuinely sits at the execution orchestration boundary.

Understanding this boundary helps the application maintain an architecture that is easy to test, easy to observe, and consistent across schemas, operations, resolvers, and transports.
