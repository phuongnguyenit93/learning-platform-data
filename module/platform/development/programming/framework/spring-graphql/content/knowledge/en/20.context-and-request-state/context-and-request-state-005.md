# GraphQLContext in controllers

## Objectives

After this lesson, you will be able to:

- Explain the role of GraphQLContext within a single GraphQL execution.
- Populate request metadata into GraphQLContext using WebGraphQlInterceptor.
- Read context values in an annotated controller using `@ContextValue`.
- Distinguish GraphQLContext from arguments, source objects, and local context.
- Choose appropriate data to share among resolvers within the same request.
- Avoid security and concurrency bugs when using request state.
- Test context propagation with GraphQlTester.

## What is GraphQLContext?

When GraphQL executes an operation, multiple resolvers may need to share request information. For example:

- Correlation ID to link logs across resolvers within the same request.
- Verified tenant ID to restrict data by tenant.
- Locale or region information for formatting data.
- Feature flags or server-determined metadata.
- Tracing information and per-request execution settings.

GraphQLContext stores values scoped to a single GraphQL execution. Data fetchers and controller methods can read the same context while processing the operation.

In Spring for GraphQL, you can add values to GraphQLContext before execution using WebGraphQlInterceptor, then read them in annotated controllers using `@ContextValue`.

GraphQLContext is not a global variable. Each request/execution has its own context, so one request's data should not leak into another request.

## When should you use GraphQLContext?

Use context when a value is metadata or state shared by multiple resolvers within the same execution, rather than business data passed by the client specifically for one field.

| Data kind | Appropriate way to pass |
| --- | --- |
| Book ID the client wants to look up | GraphQL argument via `@Argument` |
| Filter or input object sent by client | Input object via `@Argument` |
| Parent object currently being resolved | Source parameter in `@SchemaMapping` |
| Request correlation ID | GraphQLContext |
| Authenticated, server-determined tenant ID | GraphQLContext or security principal |
| Current principal and authorities | Spring Security integration, such as `@AuthenticationPrincipal` |
| Data that only needs to pass down a child field branch | Local context |

Do not put every parameter into GraphQLContext. If a value belongs to the field's contract and the client needs to supply it explicitly, declare an argument or input object in the SDL. Context is for execution-scoped information, not a replacement for the schema.

## Adding values to GraphQLContext with WebGraphQlInterceptor

WebGraphQlInterceptor sits in the web layer of Spring for GraphQL. The interceptor can read request details, customize execution input, and forward the request through the processing chain.

For example, an application wants to record a correlation ID for every request. The client can send an `X-Correlation-Id` header; if the header is absent, the server generates a new ID:

~~~java
import java.util.UUID;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId =
                request.getHeaders().getFirst("X-Correlation-Id");

        if (correlationId == null || correlationId.isBlank()) {
            correlationId = UUID.randomUUID().toString();
        }

        String requestCorrelationId = correlationId;

        request.configureExecutionInput((executionInput, builder) ->
                builder.graphQLContext(context ->
                        context.put("correlationId", requestCorrelationId)
                ).build()
        );

        return chain.next(request);
    }
}
~~~

`configureExecutionInput` lets you customize `ExecutionInput` before the GraphQL engine executes the operation. The `graphQLContext` callback adds the key/value pair into GraphQLContext. Then `chain.next(request)` passes the request to the next interceptor or execution step.

In the example, the key is `correlationId`. Keep key names consistent between the interceptor and controllers; if a literal string is used in multiple places, centralize it as a constant to avoid typos.

The interceptor is a Spring bean so it is discovered in the application context. With standard Spring Boot for GraphQL configuration, `WebGraphQlInterceptor` beans are registered into the GraphQL web processing chain.

A correlation ID from an HTTP header is client-supplied data. If you log that value, limit its length and sanitize unwanted characters. Never use an arbitrary header as the basis for authorization or tenant resolution.

## Reading context in an annotated controller with @ContextValue

After the interceptor adds the value, the controller can read it using `@ContextValue`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

import java.util.List;

@Controller
public class BookQueryController {

    private final BookService bookService;
    private final Logger logger =
            LoggerFactory.getLogger(BookQueryController.class);

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(
            @ContextValue("correlationId") String correlationId) {

        logger.debug("Loading books for request {}", correlationId);
        return bookService.findAll();
    }
}
~~~

Spring retrieves the value with key `correlationId` from GraphQLContext and binds it to the method parameter. The controller does not need to accept the full HTTP request or read headers directly.

You can combine context with arguments:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("first") int first,
        @ContextValue("correlationId") String correlationId) {

    logger.debug("Request {} asks for {} books", correlationId, first);
    return bookService.findFirst(first);
}
~~~

`first` is query data sent by the client according to the schema; `correlationId` is request metadata. The two kinds of data have different sources and purposes.

If a context key is not set, binding a required parameter can fail. Ensure the interceptor always sets the value, or declare the parameter as optional using the API of the Spring for GraphQL version you use. Do not assume an absent key will automatically be replaced by a Java default value.

## Accessing GraphQLContext directly when needed

In some cases, a resolver needs to read multiple keys or work with dynamically typed context. Spring for GraphQL also supports accessing execution context via `DataFetchingEnvironment`:

~~~java
import graphql.schema.DataFetchingEnvironment;

@QueryMapping
public List<Book> books(DataFetchingEnvironment environment) {
    String correlationId =
            environment.getGraphQlContext().get("correlationId");

    return bookService.findAll();
}
~~~

`DataFetchingEnvironment` holds details of the field being executed, including arguments, source, `GraphQLContext`, and selection. Only use this approach when the method genuinely needs those details; for a single simple value, `@ContextValue` is usually clearer and easier to read.

`GraphQLContext` can hold values of specific types. When retrieving values by string key, keep types consistent between writes and reads:

~~~java
context.put("tenantId", tenantId);
~~~

~~~java
String tenantId = environment.getGraphQlContext().get("tenantId");
~~~

Do not store one data type and read it as another. For context keys shared across multiple modules, you can define constants and small wrappers to reduce type-mismatch risks.

## Putting tenant or identity into context safely

Tenant ID is commonly used to restrict data visibility. It is access-scope sensitive information, so it must be determined from the authenticated identity or a trusted server-side source.

A safe flow can include:

1. Spring Security authenticates the request.
2. A security layer or interceptor determines which tenant the current principal is allowed to access.
3. The server puts the verified tenant ID into GraphQLContext.
4. The resolver reads the tenant ID via `@ContextValue` and passes it to the service.
5. The service always enforces the tenant constraint in data queries.

Example controller:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("first") int first,
        @ContextValue("tenantId") String tenantId) {

    return bookService.findVisibleToTenant(tenantId, first);
}
~~~

This example assumes a prior server-side component authenticated the user and placed a trusted `tenantId` into the context. Do not take a tenant ID from a header or argument that the client can freely alter and use it directly as a security boundary.

If the application uses Spring Security, you can read the principal with `@AuthenticationPrincipal` or the corresponding security context mechanism. There is no need to copy the entire `SecurityContext` into `GraphQLContext` just for convenience. Only put the tenant ID or needed metadata into `GraphQLContext` after permissions have been verified.

`GraphQLContext` does not perform authorization itself. It merely transports data within the request. The service or security layer must still check permissions for each resource and action.

## Distinguishing GraphQLContext and local context

GraphQL Java has two types of context to distinguish:

- GraphQLContext: execution-level context, shared within the scope of a single GraphQL execution.
- Local context: data passed from a parent resolver down to child resolvers in one branch of the response.

For example, a parent resolver can return `DataFetcherResult` and attach local context:

~~~java
@QueryMapping
public DataFetcherResult<Book> book(@Argument("id") String id) {
    Book book = bookService.findById(id).orElse(null);

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .localContext(Map.of("includeInternalFields", false))
            .build();
}
~~~

A child field resolver can read local context using `@LocalContextValue`:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(
        Book book,
        @LocalContextValue("includeInternalFields") Boolean includeInternalFields) {

    if (!Boolean.TRUE.equals(includeInternalFields)) {
        return null;
    }
    return book.internalNotes();
}
~~~

This example illustrates branch-scoped state propagation. In a real application, do not use a local context flag set by a parent resolver as the sole authorization mechanism; sensitive fields must still enforce permissions on the server.

Local context is suitable when data is only meaningful for child fields of a specific source object. GraphQLContext is suitable when metadata is used by multiple resolvers across different branches.

| Criterion | GraphQLContext | Local context |
| --- | --- | --- |
| Scope | Entire execution | Parent resolver branch and its child fields |
| Where set | `ExecutionInput`, interceptor, or execution setup | Parent resolver, typically via `DataFetcherResult` |
| How read in controller | `@ContextValue` or `DataFetchingEnvironment` | `@LocalContextValue` |
| Example | Correlation ID, verified tenant, locale | Branch-specific rules or internal data |

## GraphQLContext is not an argument or source object

These three data sources serve different purposes:

~~~java
@SchemaMapping(typeName = "Book", field = "recommendations")
public List<Book> recommendations(
        Book source,
        @Argument("first") int first,
        @ContextValue("tenantId") String tenantId) {

    return bookService.findRecommendations(
            source.id(), tenantId, first);
}
~~~

- `source` is the parent `Book` that GraphQL is currently resolving.
- `first` is the argument of the `recommendations` field sent by the client.
- `tenantId` is the context determined by the server for the execution.

Do not put the `Book`'s ID into GraphQLContext when it is already available on the source object. Likewise, do not put page size into context if it is a field argument controlled by the client.

## Lifetime and thread safety

GraphQL can execute independent fields in parallel. Multiple resolvers can read the same `GraphQLContext` concurrently. Therefore:

- Prefer storing immutable values such as `String`, `UUID`, `Locale`, or an immutable identity object.
- Do not use context to hold a mutable list or mutable map written concurrently by multiple resolvers.
- If mutable state is necessary, define synchronization and lifecycle clearly; usually it is better to use a service or dedicated mechanism rather than shared context.
- Do not hold a `GraphQLContext` reference in a singleton bean or retain it for another request.
- Do not store user data in static fields or instance variables shared across requests.

Context belongs to a single execution. Do not use it in place of a long-lived cache. If you need to cache shared data, choose a cache with explicit scope, keys, invalidation, and tenant policies.

## Context and DataLoader

DataLoaders are typically created per request/execution to batch and cache data loads. `GraphQLContext` and `DataLoader` can participate in the same execution, but they have different responsibilities:

- `GraphQLContext` holds shared metadata and state.
- `DataLoader` batches data load requests, dispatches batches, and caches results by key.

Do not configure a DataLoader's cache as a singleton shared across users. For tenant- or principal-dependent data, loaders must be registered per execution and queries must apply the proper security scope. Context can supply the tenant ID to a batch loader, yet the batch loader must still enforce data-scope checks.

## Testing GraphQLContext

When context is populated via `WebGraphQlInterceptor`, test through the web GraphQL handler or HTTP endpoint to verify both the interceptor and controller binding.

Example integration test using `HttpGraphQlTester` in Spring Boot:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class GraphQlContextIntegrationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void exposesCorrelationIdToResolver() {
        HttpGraphQlTester tester = graphQlTester.mutate()
                .headers(headers ->
                        headers.set("X-Correlation-Id", "test-request-123"))
                .build();

        tester.document("""
                query {
                    currentCorrelationId
                }
                """)
                .execute()
                .path("currentCorrelationId")
                .entity(String.class)
                .isEqualTo("test-request-123");
    }
}
~~~

For this test to run, the schema and resolver need a field returning the correlation ID:

~~~graphql
type Query {
  currentCorrelationId: String!
}
~~~

~~~java
@QueryMapping
public String currentCorrelationId(
        @ContextValue("correlationId") String correlationId) {
    return correlationId;
}
~~~

If you only test a controller using a `GraphQlTester` that bypasses web interceptors, context must be added directly to the tester's `ExecutionInput` or the test must use an appropriate execution setup. A standalone controller test does not prove that an HTTP header was transferred into context by the interceptor.

You should test:

1. The correlation ID header is transferred into GraphQLContext.
2. When the header is missing, the interceptor generates a default ID.
3. The resolver reads the context value accurately with `@ContextValue`.
4. Two requests with different contexts do not share values.
5. Tenant ID comes from a verified server-side source, not directly from untrusted input.
6. Local context is only read inside the resolver branch that received it.
7. Batch loaders apply the right tenant scope within the same execution.

## Common errors

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `@ContextValue` does not receive a value | Interceptor did not set the key or key name mismatch | Check `graphQLContext.put` and the annotation |
| Context value is null | Context key is absent in the current execution | Ensure every request path sets the value or handle optional |
| Controller does not see HTTP header value | Missing `WebGraphQlInterceptor` or test bypasses web layer | Check interceptor chain and tester type |
| Tenant can be spoofed | Taking tenant from client header/argument without verification | Determine tenant from principal or trusted server-side source |
| One request reads another request's data | Storing context in singleton/static state | Use execution context only and never share mutable state |
| Context overwritten unexpectedly | Multiple interceptors use the same key | Establish clear key conventions and interceptor order |
| Using GraphQLContext for single-branch data | Wrong state scope chosen | Use local context and `@LocalContextValue` |
| Resolver has too many context parameters | Putting business data into context | Use arguments, source objects, or appropriate services |

## Comprehensive practice

Build a library API with request metadata and tenant scope:

1. Create `CorrelationIdInterceptor` that reads `X-Correlation-Id`, generates a UUID if missing, and puts the `correlationId` key into `GraphQLContext`.
2. Create a `currentCorrelationId` query and read the value using `@ContextValue`.
3. Create an authentication component that determines the tenant ID from the principal or a trusted server-side source.
4. Put the verified tenant ID into `GraphQLContext`.
5. Create a `books(first: Int!)` query accepting `first` via `@Argument` and `tenantId` via `@ContextValue`.
6. Pass the tenant ID down to the service to query the proper data scope.
7. Send two requests with different correlation IDs and verify that contexts are not shared.
8. Write an integration test going through the HTTP interceptor; write standalone resolver tests where appropriate.

After the practice, explain why correlation ID can come from a request header while tenant ID must be verified, why page size belongs in an argument, and when local context is a better fit than GraphQLContext.

## Key takeaways

GraphQLContext stores metadata and shared state scoped to a single GraphQL execution. Spring for GraphQL lets you populate context via `WebGraphQlInterceptor` and read it in annotated controllers using `@ContextValue`. Use context for correlation IDs, locales, or server-verified tenants; use `@Argument` for client-sent data and source parameters for parent objects. Local context fits data passed down only a single branch. Because resolvers can run in parallel, prefer immutable values, never store context in singletons, and never use context in place of authorization or a global cache. Test both the interceptor chain and controller binding to confirm data is passed within the right scope.
