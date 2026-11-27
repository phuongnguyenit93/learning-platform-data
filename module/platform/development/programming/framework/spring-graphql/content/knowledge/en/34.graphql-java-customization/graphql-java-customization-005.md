# ExecutionInput

GraphQL Java executes an operation through the `ExecutionInput` object. This object bundles all the data required for a single GraphQL run: the document, operation name, variables, context, root object, DataLoader registry, execution ID, locale, and other metadata.

`ExecutionInput` is the boundary between the application's request and the GraphQL engine. When `GraphQL.execute(input)` is called, the engine uses the input to parse, validate, and execute the operation against the configured `GraphQLSchema`.

In Spring for GraphQL, an HTTP, WebSocket, or RSocket request is converted into a `GraphQlRequest`/`ExecutionGraphQlRequest`. Spring builds an `ExecutionInput` from that request and invokes GraphQL Java via `ExecutionGraphQlService`. If an application needs to supply additional data for an execution, it can customize `ExecutionInput` in a transport interceptor.

## What Is ExecutionInput?

`ExecutionInput` is the input object for a single GraphQL execution. It is neither the parsed GraphQL document nor the GraphQL response. It holds the document as a string along with values that help the engine process that document.

Key data components:

| Component | Role |
| --- | --- |
| `query` | GraphQL document as a string, containing one or more operations |
| `operationName` | Selects which operation to run when the document defines multiple operations |
| `variables` | Input values for variables declared in the operation |
| `GraphQLContext` | Context shared across all data fetchers in a single execution |
| `root` | Initial source object for top-level fields |
| `localContext` | Initial context provided to root data fetchers, which can be propagated down to child fields |
| `DataLoaderRegistry` | Registry holding the DataLoaders used in the execution |
| `executionId` | Identifier of the execution |
| `locale` | Locale associated with the operation |
| `extensions` | Protocol- or implementation-specific extension metadata |

`ExecutionInput` is created via a Builder. Once built, treat the input as an immutable input value; if changes are needed, create a new input via `transform` or from a builder.

## Lifecycle of ExecutionInput

In Spring for GraphQL, the typical processing flow is:

~~~mermaid
flowchart TD
    A["HTTP / WebSocket / RSocket request"] --> B["GraphQlRequest"]
    B --> C["WebGraphQlInterceptor / RSocketQlInterceptor"]
    C --> D["ExecutionGraphQlRequest"]
    D --> E["Build and customize ExecutionInput"]
    E --> F["ExecutionGraphQlService"]
    F --> G["GraphQL Java"]
    G --> H["Parse and validate document"]
    H --> I["Execute operation"]
    I --> J["ExecutionResult"]
~~~

The transport adapter reads the request from its protocol. For HTTP POST, the payload typically contains `query`, `operationName`, `variables`, and `extensions`. Spring constructs the request abstraction and passes it through the interceptor chain.

After interceptors run, `ExecutionGraphQlService` builds `ExecutionInput` and invokes GraphQL Java. GraphQL Java parses the document, validates against the schema, selects the operation, coerces variables, and runs the data fetchers. The final result is wrapped into a `GraphQlResponse` for the transport to write back to the client.

Crucially, `ExecutionInput` represents a single execution. Never share an `ExecutionInput` containing per-request state across multiple clients or invocations.

## Building ExecutionInput with the Builder

Standalone example without Spring:

Assume the `graphQL` variable points to a `GraphQL` instance built from a schema and runtime wiring:

~~~java
import graphql.ExecutionInput;
import graphql.ExecutionResult;
import graphql.GraphQL;
import org.dataloader.DataLoaderRegistry;

import java.util.Locale;
import java.util.Map;

ExecutionInput input = ExecutionInput.newExecutionInput()
        .query("""
                query BookDetails($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
        .operationName("BookDetails")
        .variables(Map.of("id", "book-42"))
        .graphQLContext(context -> {
            context.put("tenantId", "tenant-01");
            context.put("requestSource", "catalog-api");
        })
        .localContext(Map.of("traceGroup", "book-details"))
        .locale(Locale.forLanguageTag("vi-VN"))
        .extensions(Map.of("clientVersion", "2.4"))
        .dataLoaderRegistry(new DataLoaderRegistry())
        .build();

ExecutionResult result = graphQL.execute(input);
~~~

In this example:

- `query` is the GraphQL document to execute.
- `operationName` selects the `BookDetails` operation.
- `variables` supplies the value for the `id` variable.
- `graphQLContext` adds shared data for data fetchers.
- `root` provides the initial source object for root fields.
- `localContext` provides initial context for root data fetchers.
- `locale` specifies the operation's locale.
- `extensions` carries extension metadata.
- `dataLoaderRegistry` supplies the DataLoaders for the execution.

When using Spring for GraphQL, most of `query`, `operationName`, `variables`, `extensions`, and `locale` are populated by the framework from the transport request. Applications usually only need to add context, root, or genuinely needed metadata.

## Query Document and operationName

`query` is the GraphQL document string. A document may contain a single operation or multiple operations along with fragments:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
  }
}

query RecentBooks($limit: Int!) {
  recentBooks(limit: $limit) {
    id
    title
  }
}
~~~

If the document contains multiple operations, the client must supply `operationName` so the GraphQL engine knows which operation to execute. If the document has only one operation, `operationName` may be omitted.

Example input selecting `RecentBooks`:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(document)
        .operationName("RecentBooks")
        .variables(Map.of("limit", 10))
        .build();
~~~

Operation names make it easier for logs, tracing, and metrics to categorize query types. Prefer meaningful operation names like `BookById` or `RecentBooks` instead of anonymous operations in client applications.

If `operationName` does not match any operation in the document, or if the document has multiple operations without an `operationName`, GraphQL validation/execution returns an error. Resolvers are not invoked when no valid operation can be selected.

## Variables and Coercion

Variables separate input values from the query string:

~~~graphql
query BookById($id: ID!, $includeReviews: Boolean!) {
  book(id: $id) {
    id
    title
    reviews @include(if: $includeReviews) {
      rating
    }
  }
}
~~~

Building the input:

~~~java
Map<String, Object> variables = Map.of(
        "id", "book-42",
        "includeReviews", true);

ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(document)
        .operationName("BookById")
        .variables(variables)
        .build();
~~~

Keys in `variables` do not include the `$` prefix. Each key is the variable name declared in the operation. Values can be scalars, lists, or nested maps corresponding to input objects.

`ExecutionInput.Builder.variables` accepts raw variables. GraphQL Java validates types, applies default values, and performs coercion against the schema declarations during operation processing. Therefore, do not manually cast variable types in an interceptor and assume that replaces GraphQL variable coercion.

Distinguish three cases:

| Case | Meaning |
| --- | --- |
| Variable omitted from map | GraphQL can apply the default value if declared in the operation |
| Variable has value `null` | `null` is explicitly passed and follows non-null variable rules |
| Variable has incompatible type | GraphQL returns a coercion/validation error before invoking the related resolver |

Never concatenate variables directly into the query string. Using variables keeps the document stable, reduces escaping bugs, and supports operation caching.

## GraphQLContext: Shared Context for Execution

`GraphQLContext` is a key-value map attached to a single GraphQL execution. Every data fetcher in that execution can read the same context via `DataFetchingEnvironment` or Spring for GraphQL parameter injection.

The context typically holds:

- Authenticated principal or user information.
- Verified tenant ID.
- Correlation ID or request metadata.
- Locale or verified feature flags.
- Shared execution-scoped services or objects when genuinely needed.

Creating context when using GraphQL Java directly:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(document)
        .graphQLContext(context -> {
            context.put("tenantId", tenantId);
            context.put("principal", principal);
        })
        .build();
~~~

In a GraphQL Java data fetcher:

~~~java
DataFetcher<BookView> bookFetcher = environment -> {
    String tenantId =
            environment.getGraphQlContext().get("tenantId");

    String id = environment.getArgument("id");
    return bookService.findVisibleBook(tenantId, id);
};
~~~

In a Spring for GraphQL annotated controller, you can receive the context directly:

~~~java
import graphql.GraphQLContext;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookView book(
            @Argument String id,
            GraphQLContext context) {

        String tenantId = context.get("tenantId");
        return bookService.findVisibleBook(tenantId, id);
    }
}
~~~

Or use `@ContextValue` if you only need a single entry:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;

@QueryMapping
public BookView book(
        @Argument String id,
        @ContextValue("tenantId") String tenantId) {
    return bookService.findVisibleBook(tenantId, id);
}
~~~

`GraphQLContext` is designed to be safe when multiple data fetchers run concurrently. Still, objects stored as values might not be thread-safe themselves. Prefer storing stable request data; avoid placing mutable collections or state updated concurrently by multiple resolvers into the context.

`GraphQLContext` requires non-null keys and values. When a value is absent, omit the key or use an appropriate optional representation instead of putting `null`.

## Do Not Use Legacy Context APIs in New Code

GraphQL Java has an older Object-based context API:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(document)
        .context(legacyContext)
        .build();
~~~

The `context(Object)` builder method is deprecated. For new code, use `graphQLContext(...)` for an explicit context map that allows multiple components to collaborate cleanly.

Similarly, inside data fetchers prefer `environment.getGraphQlContext()` over the legacy `getContext()` API. When upgrading GraphQL Java, check deprecated methods to avoid depending on legacy APIs.

## localContext: Data Passed from Parent Field to Child Field

`localContext` differs from `GraphQLContext`:

- `GraphQLContext` is shared across the entire execution.
- `localContext` is bound to a specific field subtree, typically passed by a parent resolver to child resolvers.
- The source object is the value returned by the parent resolver, whereas `localContext` is auxiliary data that does not necessarily belong on the domain object.

For example, a root resolver loads `Book` and computes review visibility permissions. Those permissions are only needed by child fields of `Book`:

~~~java
import graphql.execution.DataFetcherResult;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;

@QueryMapping
public DataFetcherResult<BookView> book(@Argument String id) {
    BookView book = bookService.findById(id);
    BookFieldPermissions permissions =
            permissionService.permissionsFor(book);

    return DataFetcherResult.<BookView>newResult()
            .data(book)
            .localContext(permissions)
            .build();
}
~~~

A nested resolver can read the local context:

~~~java
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.SchemaMapping;

@SchemaMapping(typeName = "Book", field = "reviews")
public List<ReviewView> reviews(
        BookView book,
        DataFetchingEnvironment environment) {

    BookFieldPermissions permissions =
            environment.getLocalContext();

    if (!permissions.canReadReviews()) {
        return List.of();
    }

    return reviewService.findByBookId(book.id());
}
~~~

`DataFetcherResult.localContext` is propagated to child fields of that specific result. If another parent field returns its own local context, that subtree gets its own context. This avoids polluting the operation-wide context with metadata relevant only to a single branch.

`ExecutionInput.localContext` sets the initial local context for root data fetchers. Parent fields can subsequently return `DataFetcherResult.localContext` to pass branch-specific data down the field tree.

## Root Object

`root` is the initial source object used for top-level fields when running GraphQL Java directly. For instance, an application might supply a facade object as the root.

The corresponding schema defines an `apiVersion` field:

~~~graphql
type Query {
  apiVersion: String!
}
~~~

~~~java
public class QueryRoot {

    private final String apiVersion;

    public QueryRoot(String apiVersion) {
        this.apiVersion = apiVersion;
    }

    public String getApiVersion() {
        return apiVersion;
    }
}
~~~

Building the input:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query("""
                query {
                    apiVersion
                }
                """)
        .root(new QueryRoot("catalog-api"))
        .build();
~~~

With the default property fetcher, the `apiVersion` field can be read from the `getApiVersion()` getter on the root object. The root object can also be read directly via `DataFetchingEnvironment.getRoot()` in a custom data fetcher. If a field requires arguments such as `book(id: ID!)`, register a custom data fetcher to read arguments from the environment; GraphQL Java does not automatically pass arguments into plain POJO getters.

In Spring for GraphQL, annotated controllers usually handle root mappings via `@QueryMapping` and `@MutationMapping`. Applications do not need to create a `QueryRoot` just to use annotated controllers. Only configure `root` when using GraphQL Java directly or when a custom data fetcher expects an initial source object.

## DataLoaderRegistry

`DataLoaderRegistry` holds the DataLoaders accessible to data fetchers during an execution. Each DataLoader typically batches multiple keys into a single load call, helping eliminate N+1 queries.

Standalone example of creating a registry:

~~~java
import org.dataloader.DataLoaderFactory;
import org.dataloader.DataLoaderRegistry;
import org.dataloader.MappedBatchLoader;

import java.util.Set;
import java.util.concurrent.CompletableFuture;

MappedBatchLoader<String, AuthorView> authorBatchLoader =
        (Set<String> ids) -> CompletableFuture.completedFuture(
                authorService.findViewsByIds(ids));

DataLoaderRegistry registry = new DataLoaderRegistry();
registry.register(
        "authorLoader",
        DataLoaderFactory.newMappedDataLoader(authorBatchLoader));

ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(document)
        .dataLoaderRegistry(registry)
        .build();
~~~

Never reuse the same `DataLoaderRegistry` or `DataLoader` across executions. DataLoaders typically cache by key for the duration of a request; sharing a registry across requests can leak data between users or tenants and serve stale cached values.

In Spring for GraphQL, register batch loaders through `BatchLoaderRegistry`. Spring creates a dedicated `DataLoaderRegistry` per request and wires it into `ExecutionInput`:

~~~java
@Configuration
public class AuthorDataLoaderConfig {

    public AuthorDataLoaderConfig(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(String.class, AuthorView.class)
                .registerMappedBatchLoader((ids, environment) ->
                        authorService.findByIds(ids));
    }
}
~~~

`BatchLoaderRegistry` manages loader registration at the Spring layer. Never create a singleton `DataLoaderRegistry` and attach it to every `ExecutionInput`.

## Extensions

`extensions` is an extension metadata map used by the transport or implementation. It commonly appears in GraphQL client/server protocols that define custom extensions.

For example, a persisted query protocol may transmit hashes or version info inside `extensions`. Some clients also use `extensions` to send server-compatible metadata.

Do not use `extensions` as a substitute for `variables` or `GraphQLContext`:

- Business inputs needed by a query must be declared as variables or input objects.
- Application context such as principal and tenant should go into `GraphQLContext`.
- `extensions` is meant for protocol- or implementation-level extension metadata.

Do not blindly trust `extensions` sent by clients. The server must validate format, permissions, and usage scope before acting on that metadata.

## ExecutionId and Tracing

`ExecutionId` identifies a single GraphQL execution. GraphQL Java can assign a default ID or the application can supply its own.

`ExecutionId` is useful for:

- Linking logs to a specific GraphQL execution.
- Finding corresponding traces or events in an observability system.
- Distinguishing two requests that send the same document and variables.
- Investigating errors or latency of a specific operation.

Do not use `ExecutionId` as proof of authentication or authorization. It is strictly an observability identifier.

In Spring for GraphQL, `ExecutionGraphQlRequest` carries a transport-assigned ID and can pass that ID as the `ExecutionId` in `ExecutionInput`. If custom rules are needed, `GraphQL.Builder` supports `ExecutionIdProvider`; configure the shared engine via `GraphQlSourceBuilderCustomizer`.

Do not confuse `ExecutionIdProvider` with modifying `ExecutionInput` per request. `ExecutionIdProvider` generates IDs according to an engine-wide policy, whereas `WebGraphQlInterceptor` can set `ExecutionId` or add request-specific values.

## Locale

`locale` is the `Locale` bound to the operation. `DataFetchingEnvironment` exposes the locale so data fetchers or custom scalars can format or process data according to language/region conventions.

Example:

~~~java
DataFetcher<String> priceFetcher = environment -> {
    Locale locale = environment.getLocale();
    BigDecimal price = environment.getSource();
    return NumberFormat.getCurrencyInstance(locale).format(price);
};
~~~

Do not use `locale` as an authorization signal. Locale only affects language/region formatting or handling. Spring transports can populate `locale` from the request; if custom rules are required, it can be configured via `ExecutionInput`.

## Customizing ExecutionInput in Spring for GraphQL

Spring for GraphQL provides `WebGraphQlInterceptor` to inspect requests and customize `ExecutionInput` before GraphQL Java executes.

An interceptor is suitable when you need to:

- Put an authenticated principal into `GraphQLContext`.
- Add verified tenant or request metadata.
- Set an execution ID or locale per request policy.
- Capture transport details needed inside data fetchers.

Example of adding a tenant ID to context:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class TenantContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String tenantId =
                request.getHeaders().getFirst("X-Tenant-Id");

        if (tenantId != null && !tenantId.isBlank()) {
            request.configureExecutionInput((input, builder) ->
                    builder.graphQLContext(context ->
                            context.put("tenantId", tenantId))
                            .build());
        }

        return chain.next(request);
    }
}
~~~

Controller reading the value:

~~~java
@QueryMapping
public BookView book(
        @Argument String id,
        @ContextValue("tenantId") String tenantId) {
    return bookService.findVisibleBook(tenantId, id);
}
~~~

The example above illustrates the technique for passing metadata from the transport into the execution context. In a production system, never treat an `X-Tenant-Id` header sent by a client as proof of access rights. Validate the tenant against a verified principal or claim before writing it to context; the service must still enforce authorization when querying data.

`configureExecutionInput` accepts a `BiFunction` receiving the current `ExecutionInput` and an `ExecutionInput.Builder`. The input is already pre-populated with values from the request; the builder lets you add or change selected parts and build a new input. Thus, the client's `query`, `variables`, and `operationName` remain intact if the interceptor only adds entries to `GraphQLContext`.

## Distinguishing Interceptors from GraphQlSourceBuilderCustomizer

These two extension points have different scopes:

| Extension Point | Scope | Example |
| --- | --- | --- |
| `WebGraphQlInterceptor` | Per HTTP/WebSocket request | Adding principal, tenant, or request metadata to `GraphQLContext` |
| `RSocketQlInterceptor` | Per RSocket request | Adding context for GraphQL over RSocket |
| `ExecutionGraphQlRequest.configureExecutionInput` | Per request before calling GraphQL | Modifying `ExecutionInput` |
| `GraphQlSourceBuilderCustomizer` | Configuring the GraphQL engine at startup | `ExecutionIdProvider`, instrumentation, execution strategy |
| `RuntimeWiringConfigurer` | Configuring schema/runtime wiring | Registering data fetchers, scalars, type resolvers |

Do not put user-specific data into `GraphQlSourceBuilderCustomizer`. `GraphQlSource` and the `GraphQL` instance are shared across requests; per-request context must be attached to the `ExecutionInput` or `GraphQLContext` of that specific execution.

Example configuring `ExecutionIdProvider` at the GraphQL engine level:

~~~java
import graphql.execution.ExecutionId;
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlExecutionConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer executionIdCustomizer() {
        return builder -> builder.configureGraphQl(graphQlBuilder ->
                graphQlBuilder.executionIdProvider(
                        (query, operationName, context) ->
                                ExecutionId.generate()));
    }
}
~~~

The example uses the Spring Boot 4.x package. In Spring Boot 3.x, the package for `GraphQlSourceBuilderCustomizer` is `org.springframework.boot.autoconfigure.graphql`. If you do not need a custom ID policy, keep Spring for GraphQL's default IDs.

## RSocket and Other Transports

HTTP and WebSocket use `WebGraphQlInterceptor`. For GraphQL over RSocket, Spring for GraphQL provides `RSocketQlInterceptor` to customize requests before GraphQL Java executes.

Do not assume HTTP headers are always present when handling WebSocket or RSocket. Each transport carries metadata differently:

- HTTP has headers and request attributes.
- WebSocket has a connection initialization payload and per-operation info.
- RSocket has metadata and payload per interaction.

Normalize application-level data into `GraphQLContext` after validating the data source. Controllers and services can then read context uniformly regardless of transport.

## Modifying ExecutionInput with transform

`ExecutionInput` provides `transform` to produce a new input based on existing values:

~~~java
ExecutionInput updatedInput = input.transform(builder ->
        builder.locale(Locale.forLanguageTag("vi-VN")));
~~~

`transform` creates a Builder from the current input, applies changes, and builds a new `ExecutionInput`. Unmodified fields are preserved.

This is the right approach when code already holds an `ExecutionInput` and wants to make a small adjustment. Do not try to mutate an already built input by modifying internal fields.

The `GraphQLContext` inside `ExecutionInput` remains mutable according to GraphQL Java's API. Still, avoid mutating it once execution begins; prepare all required data before invoking the engine so resolvers executing concurrently observe a stable state.

## Protecting Data in ExecutionInput

`ExecutionInput` can carry sensitive information such as principal, tenant, variables, and extensions. Follow these rules:

- Never log raw variables, access tokens, passwords, or personal data.
- Never place access rights in client-editable variables without server-side verification.
- Never reuse `GraphQLContext` or `DataLoaderRegistry` across requests.
- Never put shared mutable state into `GraphQLContext` if multiple resolvers could modify it concurrently.
- Never treat client-sent `extensions` or custom HTTP headers as trusted without validation.
- Limit document and variable sizes at the transport layer to prevent oversized requests.
- Never put long-lived objects or out-of-request resources into `localContext`.

In particular, tenant context only delivers the authenticated tenant to the data fetcher. Repositories or services must still scope queries by tenant; context does not automatically enforce row-level authorization.

## Testing ExecutionInput

You can test at three levels:

| Level | Tool | What to Verify |
| --- | --- | --- |
| Direct GraphQL Java | `GraphQL.execute(input)` | `query`, `operationName`, `variables`, context, `root`, and `DataLoader` |
| Execution service | `ExecutionGraphQlServiceTester` | `ExecutionInput` is configured properly before running the engine |
| Transport/interceptor | `WebGraphQlTester` | Headers, principal, interceptor chain, and response |

Example of testing `ExecutionInput` directly:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import graphql.ExecutionInput;
import java.util.Map;

ExecutionInput input = ExecutionInput.newExecutionInput()
        .query("query Book($id: ID!) { book(id: $id) { id } }")
        .operationName("Book")
        .variables(Map.of("id", "book-42"))
        .graphQLContext(context -> context.put("tenantId", "tenant-01"))
        .build();

assertThat(input.getOperationName()).isEqualTo("Book");
assertThat(input.getVariables()).containsEntry("id", "book-42");
assertThat(input.getGraphQLContext().get("tenantId"))
        .isEqualTo("tenant-01");
~~~

This example verifies that data was placed into the input. To verify context reaches the data fetcher, execute the operation and inspect the response or spy that the service was called with the expected tenant.

Spring for GraphQL provides `ExecutionGraphQlServiceTester` for server-side testing without an HTTP client. Its builder exposes `configureExecutionInput`, allowing tests to set an execution ID or modify the input:

~~~java
import graphql.execution.ExecutionId;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

ExecutionId executionId = ExecutionId.generate();

ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.builder(executionGraphQlService)
                .configureExecutionInput((input, builder) ->
                        builder.executionId(executionId).build())
                .build();
~~~

To test an interceptor, use `WebGraphQlTester` with `WebGraphQlHandler` so the request runs through the interceptor chain before reaching `ExecutionGraphQlService`. To test actual HTTP transport, use `HttpGraphQlTester`.

Scenarios to test:

- Documents with single and multiple operations.
- Missing, matching, and non-existent `operationName`.
- Missing, null, wrongly typed, and defaulted variables.
- Context added prior to execution and read inside resolvers.
- `localContext` propagating only to the intended child field branch.
- A fresh `DataLoaderRegistry` created for each execution.
- Two concurrent requests never sharing principal, tenant, or DataLoader cache.
- `ExecutionId` traceable in logs and observations.
- Interceptor not inadvertently overwriting client-sent `query`/`variables`.
- Invalid metadata from headers or `extensions` rejected.

## Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cannot select operation | Document has multiple operations but lacks `operationName` | Supply the correct `operationName` |
| Resolver does not receive variable | Key name in `variables` mismatches declaration or variable was omitted | Check variable definition and map |
| Variable type mismatch | Raw variable is incompatible with the GraphQL input type | Let GraphQL coercion validate and fix the input type |
| Context is always null | Interceptor did not call `configureExecutionInput` or used wrong key | Check context key and interceptor chain |
| Using legacy context API | `Builder.context(Object)` is deprecated | Use `graphQLContext(...)` |
| Child field misses metadata | Set `localContext` without returning `DataFetcherResult.localContext` from parent | Return `DataFetcherResult` and verify the branch |
| DataLoader returns another request's data | Reusing `DataLoaderRegistry`/`DataLoader` across executions | Create registry per request or use `BatchLoaderRegistry` |
| Root resolver receives null source | `root` object not configured when using GraphQL Java directly | Configure `root` or use Spring annotated controllers |
| Unexpected `ExecutionId` | Transport ID or `ExecutionIdProvider` is overriding it | Check request ID and provider configuration |
| Incorrect `Locale` | Transport did not supply locale or input was not customized | Check request locale and `ExecutionInput` |
| Tenant spoofing | Blindly trusting client-sent headers/extensions | Validate tenant against principal/claims and enforce in services |
| Engine config leaks request state | Placing user-specific context in `GraphQlSourceBuilderCustomizer` | Move state to `WebGraphQlInterceptor` and `GraphQLContext` |

## Principles for Using ExecutionInput

When working with `ExecutionInput`, follow these guidelines:

1. **Treat it as input for a single execution.** Never share objects or request state across runs.
2. **Keep `query` and `operationName` clear.** Use meaningful operation names and select the right operation in multi-operation documents.
3. **Use `variables` instead of string concatenation.** Let GraphQL Java perform schema coercion.
4. **Use `GraphQLContext` for execution-wide data.** Verified principal, tenant, and request metadata belong here.
5. **Use `localContext` for branch-scoped data.** Pass from parent to child via `DataFetcherResult.localContext`.
6. **Use `root` for its intended purpose.** It is the initial source object, not a container for request metadata.
7. **Create `DataLoaderRegistry` per request.** In Spring for GraphQL, prefer `BatchLoaderRegistry`.
8. **Distinguish `extensions` from context.** Extensions hold protocol metadata, not arbitrary business data.
9. **Manage `executionId` and `locale` intentionally.** Use ID for observability and locale for language/region handling.
10. **Customize at the right layer.** `WebGraphQlInterceptor` adjusts per-request input; `GraphQlSourceBuilderCustomizer` configures the shared engine.
11. **Use `GraphQLContext` instead of legacy APIs.** Avoid deprecated `Builder.context(Object)`.
12. **Test transport and service layers separately.** Verify data actually reaches the data fetcher, not just the builder.

`ExecutionInput` is the input contract between the application and GraphQL Java. It carries the document, operation name, raw variables, context, root object, local context, `DataLoaderRegistry`, execution ID, locale, and extensions for a single execution. In Spring for GraphQL, transport requests are converted into `ExecutionInput` via `ExecutionGraphQlService`; `WebGraphQlInterceptor` or `RSocketQlInterceptor` can attach per-request data before engine execution. `GraphQLContext` is shared across the operation, whereas `localContext` passes branch-scoped data from parent fields to child fields. Creating a fresh `DataLoaderRegistry` per request, keeping context stable, and customizing only the appropriate extension points keeps execution safe, testable, and observable.

## References

- [GraphQL Java - ExecutionInput](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/ExecutionInput.html)
- [GraphQL Java - ExecutionInput.Builder](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/ExecutionInput.Builder.html)
- [GraphQL Java - GraphQLContext](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/GraphQLContext.html)
- [GraphQL Java - DataFetchingEnvironment](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetchingEnvironment.html)
- [Spring for GraphQL - Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL - Server Transports and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL - Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
