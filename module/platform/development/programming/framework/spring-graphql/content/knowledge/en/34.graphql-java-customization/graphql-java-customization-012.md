# Using GraphQL Java Directly

Spring for GraphQL is built on top of GraphQL Java. In a standard Spring application, you declare an SDL schema, register DataFetchers using controllers or `RuntimeWiringConfigurer`, and let Spring manage `GraphQlSource`, GraphQL execution, and HTTP/WebSocket transport.

However, there are situations where working directly with GraphQL Java is necessary: building a standalone GraphQL library, embedding GraphQL in a non-Spring process, generating dynamic schemas, writing schema inspection tooling, unit testing the execution engine, or deeply customizing execution strategies and instrumentation.

**GraphQL Java is the execution engine**. The library accepts a GraphQL schema and an operation, invokes DataFetchers, validates inputs, executes field selections, and produces an `ExecutionResult`. It does not provide an HTTP server, authentication, database connectivity, or router deployment mechanisms on its own.

This lesson shows how to build an executable schema using SDL and `RuntimeWiring`, instantiate `GraphQL`, execute operations, read `ExecutionResult`, access `DataFetchingEnvironment`, handle errors, customize type resolvers/scalars/directives, use DataLoader, configure execution strategies, add instrumentation, and run subscriptions. At the end, it contrasts when to use GraphQL Java directly versus keeping Spring for GraphQL abstractions.

## 1. Where Does GraphQL Java Sit in the Architecture?

A GraphQL server application typically comprises these layers:

~~~mermaid
flowchart TD
    A[Client] --> B[HTTP / WebSocket transport]
    B --> C[Authentication and request context]
    C --> D[GraphQL request adapter]
    D --> E[GraphQL Java execution engine]
    E --> F[Schema and RuntimeWiring]
    F --> G[DataFetcher]
    G --> H[Application services]
    H --> I[Database / remote services]
~~~

GraphQL Java focuses on the execution engine, schema, and DataFetchers. The transport receives bytes or JSON from clients, converts them into a GraphQL request, and sends results back over HTTP, WebSocket, or another protocol. Those transport responsibilities require a separate framework or adapter.

In Spring for GraphQL:

- `GraphQlSource` supplies the `GraphQL` instance and builder to construct the schema/runtime.
- `ExecutionGraphQlService` invokes GraphQL Java to execute requests in a transport-agnostic manner.
- `WebGraphQlHandler` adds request/response handling at the WebGraphQL layer.
- HTTP, WebSocket, and other transports forward requests to `ExecutionGraphQlService`.
- `RuntimeWiringConfigurer` and `AnnotatedControllerConfigurer` register DataFetchers, scalars, directives, and `TypeResolver`s.

When using GraphQL Java directly, you are responsible for creating and managing all required components. That works well for standalone libraries or tools, whereas a production server still needs transport handling, authentication, request limits, observability, and lifecycle management.

## 2. Adding GraphQL Java to a Java Application

GraphQL Java is published on Maven Central under `com.graphql-java:graphql-java`. Pick a version compatible with your Java runtime and related project libraries:

~~~gradle
repositories {
    mavenCentral()
}

dependencies {
    implementation("com.graphql-java:graphql-java:<graphql-java-version>")
}
~~~

Do not pick the latest version independently if your project uses Spring for GraphQL. Spring for GraphQL and Spring Boot manage a compatible range of GraphQL Java versions; use your project's dependency management/BOM or check the compatibility matrix before overriding.

Common packages:

| Package | Role |
|---|---|
| `graphql` | `GraphQL`, `ExecutionInput`, `ExecutionResult` |
| `graphql.schema` | `GraphQLSchema`, `DataFetcher`, `DataFetchingEnvironment`, `GraphQLObjectType` |
| `graphql.schema.idl` | `SchemaParser`, `TypeDefinitionRegistry`, `RuntimeWiring`, `SchemaGenerator` |
| `graphql.execution` | `ExecutionStrategy` and DataFetcher error handling |
| `graphql.execution.instrumentation` | `Instrumentation` and lifecycle hooks |
| `graphql.execution.preparsed` | Cache/parse-and-validate hooks |

## 3. Creating an Executable Schema from SDL

GraphQL Java supports two ways to construct a schema:

1. Declaring types via Java code.
2. Declaring types using Schema Definition Language (SDL), then connecting the schema to runtime logic via `RuntimeWiring`.

For most APIs with a stable schema, prefer SDL because schemas are easy to read, review, validate, and share between client and server. Building a schema purely in Java fits tools that generate schemas dynamically or libraries constructing types from metadata.

Example SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  published: Boolean!
}
~~~

This schema defines the shape of the data, but not where the `book` field retrieves its data. `RuntimeWiring` binds `Query.book` to a DataFetcher.

~~~java
String sdl = """
        type Query {
          book(id: ID!): Book
        }

        type Book {
          id: ID!
          title: String!
          published: Boolean!
        }
        """;

TypeDefinitionRegistry registry =
        new SchemaParser().parse(sdl);

RuntimeWiring wiring = RuntimeWiring.newRuntimeWiring()
        .type("Query", type -> type.dataFetcher("book", environment -> {
            String id = environment.getArgument("id");
            return bookRepository.findById(id).orElse(null);
        }))
        .build();

GraphQLSchema schema =
        new SchemaGenerator().makeExecutableSchema(registry, wiring);
~~~

Core components:

- `SchemaParser` reads SDL and produces a `TypeDefinitionRegistry`.
- `RuntimeWiring` registers DataFetchers, custom scalars, directives, and `TypeResolver`s.
- `SchemaGenerator` combines the registry with wiring to produce an executable `GraphQLSchema`.

When a field lacks an explicit DataFetcher, GraphQL Java typically uses `PropertyDataFetcher` to read the matching property from a JavaBean or `Map`. Thus, you only need to register DataFetchers for fields that access services, databases, or apply special logic.

## 4. Building a Schema Purely in Java

When a schema is generated from metadata or its type structure is known only at runtime, you can construct `GraphQLObjectType` and `GraphQLFieldDefinition` via builders:

~~~java
GraphQLObjectType queryType = GraphQLObjectType.newObject()
        .name("Query")
        .field(field -> field
                .name("hello")
                .type(Scalars.GraphQLString)
                .dataFetcher(environment -> "Hello from GraphQL Java"))
        .build();

GraphQLSchema schema = GraphQLSchema.newSchema()
        .query(queryType)
        .build();

GraphQL graphQL = GraphQL.newGraphQL(schema).build();
~~~

GraphQL Java offers builders for objects, interfaces, unions, enums, input objects, scalars, and fields. This enables dynamic schema generation, though the code is more verbose than SDL and harder to review as schemas grow.

Avoid mixing both schema-building approaches haphazardly. When most types are static, keep SDL as the primary source and customize `RuntimeWiring`. Reserve programmatic schema construction for parts that truly require dynamic generation.

## 5. Creating a GraphQL Instance and Executing Operations

Once you have a `GraphQLSchema`, construct a `GraphQL` instance:

~~~java
GraphQL graphQL = GraphQL.newGraphQL(schema).build();
~~~

A `GraphQL` instance can be reused across many requests if the schema and configured components are immutable or thread-safe. Never rebuild the schema and `GraphQL` instance per request.

### 5.1. ExecutionInput

`ExecutionInput` describes a single execution. Beyond the query document, it can hold an operation name, variables, context, root object, locale, and `DataLoaderRegistry`.

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query("""
                query FindBook($id: ID!) {
                  book(id: $id) {
                    id
                    title
                  }
                }
                """)
        .operationName("FindBook")
        .variables(Map.of("id", "book-01"))
        .build();
~~~

Never concatenate user input values directly into the GraphQL document. Pass them via variables so GraphQL Java performs coercion and schema validation.

### 5.2. execute and executeAsync

There are two common ways to execute:

~~~java
ExecutionResult result = graphQL.execute(input);
~~~

~~~java
CompletableFuture<ExecutionResult> future = graphQL.executeAsync(input);
~~~

`execute` returns an `ExecutionResult` once execution completes. `executeAsync` returns a `CompletableFuture` so callers can compose it with the application's asynchronous pipeline. Never call `join` or `get` on a WebFlux event-loop thread to await the future.

A DataFetcher can also return a `CompletionStage`. GraphQL Java composes asynchronous results into the overall execution result; selecting the `Executor` and performing I/O remain the responsibility of the DataFetcher or application service.

### 5.3. ExecutionResult

`ExecutionResult` holds `data` and `errors`. GraphQL allows responses to return partial data when one field fails while other fields succeed.

~~~java
ExecutionResult result = graphQL.execute(input);

Object data = result.getData();
List<GraphQLError> errors = result.getErrors();
Map<String, Object> response = result.toSpecification();
~~~

`toSpecification()` produces a map structure following the GraphQL response specification, including `data`, `errors`, and `extensions` when present. This is the right structure for transport adapters to serialize into JSON.

Never assume `errors` is empty simply because `data` is non-null. Nor assume `data` is always non-null: parse errors, validation errors, or root field failures can leave `data` absent or null.

## 6. DataFetcher and DataFetchingEnvironment

Every field in a GraphQL schema has a `DataFetcher`. A DataFetcher is the function that retrieves the field's value; in some ecosystems, this component is also called a resolver.

Example of registering a DataFetcher directly:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    return bookService.findById(id);
};

RuntimeWiring wiring = RuntimeWiring.newRuntimeWiring()
        .type("Query", type -> type.dataFetcher("book", bookFetcher))
        .build();
~~~

Every time the `Query.book` field is executed, GraphQL Java invokes the DataFetcher and passes a `DataFetchingEnvironment`.

### 6.1. Key Information in DataFetchingEnvironment

| Method | Meaning |
|---|---|
| `getArgument(name)` | Retrieve an argument parsed and coerced per the schema |
| `getArguments()` | Retrieve all arguments for the field |
| `getSource()` | Parent object returned by the preceding field |
| `getRoot()` | Initial root object of the operation |
| `getGraphQlContext()` | Shared context scoped to a single execution |
| `getLocalContext()` | Context passed down from parent DataFetcher via `DataFetcherResult` |
| `getExecutionStepInfo()` | Field/type/path details in the execution tree |
| `getSelectionSet()` | Child fields selected by the client |
| `getExecutionId()` | ID of the current execution |
| `getDataLoader(name)` | Retrieve a DataLoader registered for the request |

`DataFetchingEnvironment` is an essential information source when writing general-purpose DataFetchers. However, do not treat it as a service locator for fetching all dependencies. Inject services or repositories via the constructor of the class holding the DataFetcher.

### 6.2. Source Object and PropertyDataFetcher

The parent field's result becomes the source object for its child fields. For example, if `Query.book` returns a `Book`, when GraphQL Java resolves `Book.title`, the `source` is that `Book` instance.

Without a dedicated DataFetcher, `PropertyDataFetcher` looks up properties matching the field name on a JavaBean or `Map`:

~~~java
public record Book(String id, String title) {
}
~~~

For a `Book` type with `id` and `title` fields, GraphQL Java can read the `id()` and `title()` accessors from the record. For JavaBeans, it looks for standard getters such as `getTitle()`.

If the Java property name differs from the GraphQL field name, register `PropertyDataFetcher` with an explicit property name or provide a dedicated DataFetcher. Do not rely on Jackson annotations to rename GraphQL fields: GraphQL Java builds responses from field selections and property fetchers, not by serializing entire objects with Jackson.

### 6.3. GraphQLContext and Local Context

`GraphQLContext` stores data shared across a single execution, such as tenant ID, principal, or correlation metadata. You can populate context when building `ExecutionInput`:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query("{ currentTenant }")
        .graphQLContext(context -> context.put("tenantId", tenantId))
        .build();
~~~

DataFetcher reading the value:

~~~java
DataFetcher<String> tenantFetcher = environment ->
        environment.getGraphQlContext().get("tenantId");
~~~

`GraphQLContext` is scoped to a single execution. Never use a shared global mutable `Map` as context across multiple requests, or one user's data can leak into another's request.

Local context is scoped to a subtree of the execution tree. A parent DataFetcher can return a `DataFetcherResult` carrying `localContext`; child DataFetchers receive that value via `getLocalContext()`. Use local context when data pertains only to one branch rather than the entire request.

### 6.4. DataFetcherResult: Data, Errors, and Local Context

`DataFetcherResult` lets a DataFetcher return data along with GraphQL errors or local context:

~~~java
return DataFetcherResult.<Book>newResult()
        .data(book)
        .localContext(Map.of("canEdit", canEdit))
        .build();
~~~

When returning data alongside a recoverable error, add the error to the builder:

~~~java
return DataFetcherResult.<Book>newResult()
        .data(book)
        .error(GraphqlErrorBuilder.newError(environment)
                .message("Some metadata could not be loaded")
                .build())
        .build();
~~~

This represents a partial result at the field level. Only attach errors when clients need to know part of the data is missing or incomplete; do not turn normal situations into GraphQL errors.

## 7. RuntimeWiring and Schema Extension Components

`RuntimeWiring` does more than register DataFetchers. It also registers custom scalars, `TypeResolver`s for interfaces/unions, directive wirings, and other runtime components.

~~~java
RuntimeWiring wiring = RuntimeWiring.newRuntimeWiring()
        .type("Query", type -> type
                .dataFetcher("book", bookFetcher))
        .scalar(dateScalar)
        .type("SearchResult", type -> type.typeResolver(searchResultTypeResolver))
        .directive("auth", new AuthorizationDirectiveWiring())
        .build();
~~~

Register only components that the schema actually uses. If a type or directive in the SDL lacks matching runtime wiring, the schema may fail to build or fields may not behave as expected.

### 7.1. TypeResolver for Interfaces and Unions

GraphQL interfaces and unions can return multiple object types. GraphQL Java requires a `TypeResolver` to determine the concrete object type of a runtime value.

Example schema:

~~~graphql
interface SearchResult {
  id: ID!
}

type Book implements SearchResult {
  id: ID!
  title: String!
}

type Author implements SearchResult {
  id: ID!
  name: String!
}

type Query {
  search: [SearchResult!]!
}
~~~

Registering the resolver:

~~~java
TypeResolver searchResultTypeResolver = environment -> {
    Object value = environment.getObject();
    if (value instanceof Book) {
        return environment.getSchema().getObjectType("Book");
    }
    if (value instanceof Author) {
        return environment.getSchema().getObjectType("Author");
    }
    throw new IllegalArgumentException(
            "Unsupported SearchResult: " + value.getClass().getName());
};

RuntimeWiring wiring = RuntimeWiring.newRuntimeWiring()
        .type("SearchResult", type -> type.typeResolver(searchResultTypeResolver))
        .build();
~~~

`TypeResolver` must return a `GraphQLObjectType` present in the schema. Returning an incompatible type or failing to resolve a runtime class triggers a GraphQL execution error on the interface/union field.

### 7.2. Custom Scalars

GraphQL provides standard scalars such as `String`, `Int`, `Float`, `Boolean`, and `ID`. When a domain uses types like `LocalDate`, `UUID`, or `Decimal`, you can define custom scalars specifying how inputs are parsed and outputs are serialized.

A custom scalar typically implements three operations:

- `serialize`: convert a Java value into a client-ready output value.
- `parseValue`: convert an input variable into a Java type.
- `parseLiteral`: convert a literal value in the GraphQL document into a Java type.

~~~java
GraphQLScalarType dateScalar = GraphQLScalarType.newScalar()
        .name("LocalDate")
        .description("ISO-8601 calendar date")
        .coercing(new LocalDateCoercing())
        .build();
~~~

`LocalDateCoercing` is a `Coercing` implementation for `LocalDate`. Reject invalid inputs with `CoercingParseValueException` or `CoercingParseLiteralException` and invalid outputs with `CoercingSerializeException` per your GraphQL Java version's API.

Register the scalar in `RuntimeWiring` via `scalar(dateScalar)`. Custom scalars need clear contracts regarding format, timezone, and precision; avoid silently accepting ambiguous input formats.

### 7.3. Schema Directives

Schema directives let you attach cross-cutting behavior to types or fields. For example, an `auth` directive can check permissions before invoking the original DataFetcher:

~~~graphql
directive @auth(role: String!) on FIELD_DEFINITION

type Employee {
  id: ID!
  name: String!
  salary: Float @auth(role: "manager")
}
~~~

An implementation can wrap the original DataFetcher:

~~~java
class AuthorizationDirectiveWiring implements SchemaDirectiveWiring {

    @Override
    public GraphQLFieldDefinition onField(
            SchemaDirectiveWiringEnvironment<GraphQLFieldDefinition> environment) {

        String role = (String) environment.getAppliedDirective()
                .getArgument("role")
                .getArgumentValue()
                .getValue();

        DataFetcher<?> original = environment.getFieldDataFetcher();
        DataFetcher<?> secured = dataEnvironment -> {
            AuthorizationContext auth = dataEnvironment.getGraphQlContext()
                    .get("authContext");
            if (!auth.hasRole(role)) {
                return null;
            }
            return original.get(dataEnvironment);
        };

        return environment.setFieldDataFetcher(secured);
    }
}
~~~

Register via `RuntimeWiring.directive("auth", wiring)`. Before execution, put the request's `AuthorizationContext` into `GraphQLContext`. Returning `null` in this example merely illustrates a field-hiding policy; production APIs may need to return a GraphQL error with an appropriate code so clients can distinguish denied fields.

Directives apply behavior across the schema. They do not replace authorization checks at the service layer, especially when the same service is called from REST, message consumers, or another GraphQL field.

### 7.4. Schema Directives vs. Operation Directives

These two directive categories differ in placement and evaluation timing:

| Category | Where Declared/Placed | How Read |
|---|---|---|
| Schema directive | SDL on schema, type, field, or argument | `SchemaDirectiveWiring` while building the executable schema |
| Operation directive | Query document on operation, field, fragment, or variable | `QueryDirectives` via `DataFetchingEnvironment` at execution time |

An operation directive such as `@cache` on a query field does not implement caching automatically. GraphQL Java parses and exposes the directive usage; the application must write the logic that reads the directive and performs caching.

Inside a DataFetcher, you can inspect directives applied to the field:

~~~java
List<QueryAppliedDirective> cacheDirectives = environment.getQueryDirectives()
        .getImmediateAppliedDirective("cache");

if (!cacheDirectives.isEmpty()) {
    QueryAppliedDirective cache = cacheDirectives.get(0);
    QueryAppliedDirectiveArgument maxAge = cache.getArgument("maxAge");
    Integer maxAgeMillis = maxAge.getValue();
    // Apply the application's cache policy.
}
~~~

Query directives can appear multiple times when declared `repeatable`. Handle empty lists and multiple directives properly instead of always assuming only the first element matters.

## 8. ExecutionStrategy and Error Handling

`ExecutionStrategy` governs how GraphQL Java executes fields in an operation. The default strategies suit most applications:

| Operation | Execution Strategy | Behavior |
|---|---|---|
| Query | `AsyncExecutionStrategy` (default) | Allows sibling fields to execute asynchronously |
| Mutation | `AsyncSerialExecutionStrategy` (default) | Executes root mutation fields sequentially |
| Subscription | `SubscriptionExecutionStrategy` | Required to support Reactive Streams `Publisher` |

Strategies can be configured when building the `GraphQL` instance:

~~~java
GraphQL graphQL = GraphQL.newGraphQL(schema)
        .queryExecutionStrategy(new AsyncExecutionStrategy())
        .mutationExecutionStrategy(new AsyncSerialExecutionStrategy())
        .subscriptionExecutionStrategy(new SubscriptionExecutionStrategy())
        .build();
~~~

This explicitly configures the standard strategies. Change strategies only when you have a specific requirement and understand the impact on concurrency, mutation order, DataLoader, and exception handling.

### 8.1. Asynchronous DataFetchers

A DataFetcher can return a `CompletionStage` so the engine composes results:

~~~java
DataFetcher<CompletableFuture<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    return CompletableFuture.supplyAsync(
            () -> bookService.findById(id),
            bookExecutor);
};
~~~

Pass an explicit executor for blocking work. If omitted, `CompletableFuture.supplyAsync` defaults to `ForkJoinPool.commonPool`; avoid using the common pool for blocking JDBC or HTTP calls in high-load servers.

`AsyncExecutionStrategy` does not automatically offload synchronous DataFetchers onto a thread pool. A DataFetcher returning an object directly still runs its synchronous code on the calling thread.

### 8.2. DataFetcherExceptionHandler

When a DataFetcher throws an exception, GraphQL Java defaults to creating a GraphQL error carrying the field path and source location. Other fields can still return data depending on nullability and the error's position in the response tree.

You can customize exception mapping:

~~~java
DataFetcherExceptionHandler exceptionHandler = parameters -> {
    GraphQLError error = GraphqlErrorBuilder.newError()
            .message("Unable to load data for field")
            .path(parameters.getPath())
            .location(parameters.getSourceLocation())
            .errorType(ErrorType.DataFetchingException)
            .build();

    return CompletableFuture.completedFuture(
            DataFetcherExceptionHandlerResult.newResult()
                    .error(error)
                    .build());
};
~~~

Attach the handler to the execution strategies:

~~~java
GraphQL graphQL = GraphQL.newGraphQL(schema)
        .queryExecutionStrategy(new AsyncExecutionStrategy(exceptionHandler))
        .mutationExecutionStrategy(new AsyncSerialExecutionStrategy(exceptionHandler))
        .build();
~~~

In real applications, classify business errors, validation errors, and system errors into appropriate GraphQL error types and extensions. Never expose stack traces, SQL, access tokens, or internal details in client error messages; log full details on the server alongside the execution ID for investigation.

## 9. DataLoader When Using GraphQL Java Directly

If every child field queries the database independently, one operation can trigger N+1 queries. GraphQL Java integrates `DataLoader` to batch multiple keys within the same execution into one call.

Example where multiple `Book` objects need their `Author` by `authorId`:

~~~java
MappedBatchLoader<String, Author> authorBatchLoader = authorIds ->
        CompletableFuture.supplyAsync(
                () -> authorService.findAllByIds(authorIds),
                authorExecutor);

DataLoader<String, Author> authorLoader =
        DataLoaderFactory.newMappedDataLoader(authorBatchLoader);
~~~

Register the loader into the request's `DataLoaderRegistry`:

~~~java
DataLoaderRegistry registry = new DataLoaderRegistry();
registry.register("authorById", authorLoader);

ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(query)
        .dataLoaderRegistry(registry)
        .build();
~~~

DataFetcher retrieving the loader from `DataFetchingEnvironment`:

~~~java
DataFetcher<CompletableFuture<Author>> authorFetcher = environment -> {
    Book book = environment.getSource();
    DataLoader<String, Author> loader =
            environment.getDataLoader("authorById");
    return loader.load(book.authorId());
};
~~~

### 9.1. Lifecycle and Batching Conditions

DataLoaders maintain a cache and dispatch state, so you must create a fresh `DataLoaderRegistry` and loaders for each execution/request. Never share a mutable registry across requests from different users.

DataLoader batching relies on `AsyncExecutionStrategy` to identify optimal dispatch points. Using another execution strategy that does not support this dispatch mechanism may leave DataLoader caching keys without batching them as expected.

GraphQL Java automatically registers `DataLoader` dispatch instrumentation in its default configuration. If you replace the instrumentation chain or construct a `GraphQL` instance manually, verify `DataLoaderDispatcherInstrumentation` remains installed; you can register it explicitly when statistics configuration is needed.

The result of a mapped batch loader must map each loaded key to its result. For list-based batch loaders returning a `List` rather than a `Map`, element order must match input key order. Test missing keys, duplicate keys, and batch load failures.

### 9.2. Do Not Enqueue DataLoader from Another Async Task

Never wrap `DataLoader.load()` inside `CompletableFuture.supplyAsync` directly inside the DataFetcher:

~~~java
// Avoid: the key might be enqueued after the engine's dispatch window.
return CompletableFuture.supplyAsync(() -> loader.load(book.authorId()));
~~~

GraphQL Java tracks `load` calls enqueued during field tree traversal to pick dispatch points. If a `load` call only runs after a task on another thread completes, the engine may miss the key at the right dispatch moment and execution can hang.

Invoke `loader.load()` directly inside the DataFetcher as shown earlier. Place asynchronous I/O inside `BatchLoader`/`MappedBatchLoader`; batch loaders are allowed to return a `CompletionStage` and execute work on an appropriate executor.

GraphQL Java 25 supports chained DataLoaders, which must be enabled explicitly via `GraphQLUnusualConfiguration.DataloaderConfig.enableDataLoaderChaining(true)`. Enable it only when needed and after verifying dispatch order across dependent loaders.

## 10. Instrumentation and Profiling

`Instrumentation` lets you observe or modify steps during GraphQL execution. Applications commonly use it for timing, tracing, metrics, logging, field interception, or adding metadata to `ExecutionResult`.

An instrumentation can observe execution start and completion:

~~~java
class TimingInstrumentation extends SimplePerformantInstrumentation {

    @Override
    public InstrumentationContext<ExecutionResult> beginExecution(
            InstrumentationExecutionParameters parameters,
            InstrumentationState state) {

        long startNanos = System.nanoTime();
        return new SimpleInstrumentationContext<>() {
            @Override
            public void onCompleted(ExecutionResult result, Throwable throwable) {
                long elapsedNanos = System.nanoTime() - startNanos;
                metrics.recordGraphQlExecution(elapsedNanos);
            }
        };
    }
}
~~~

Register the instrumentation when building the `GraphQL` instance:

~~~java
GraphQL graphQL = GraphQL.newGraphQL(schema)
        .instrumentation(new TimingInstrumentation())
        .build();
~~~

`InstrumentationState` can hold per-execution data. Never store request state in mutable fields of a shared instrumentation without proper synchronization; a single `GraphQL` instance can process many concurrent requests.

Multiple instrumentations can be combined via `ChainedInstrumentation`. When replacing the default instrumentation, verify that essential capabilities such as DataLoader dispatch continue to function.

### 10.1. Profiling execution

GraphQL Java v25 includes an execution profiler. You can enable profiling on `ExecutionInput`:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(query)
        .profileExecution(true)
        .build();
~~~

After execution, `ProfilerResult` is stored in `GraphQLContext` under `ProfilerResult.PROFILER_CONTEXT_KEY`:

~~~java
ExecutionResult result = graphQL.execute(input);
ProfilerResult profilerResult = input.getGraphQLContext()
        .get(ProfilerResult.PROFILER_CONTEXT_KEY);

if (profilerResult != null) {
    Map<String, Object> summary = profilerResult.shortSummaryMap();
    logger.info("GraphQL profile: {}", summary);
}
~~~

The profiler exposes DataFetcher invocations, DataLoader dispatches, and execution timings. Enable it only during analysis or in environments where overhead has been evaluated; do not log raw queries, variables, or sensitive data by default.

## 11. Subscriptions When Using GraphQL Java Directly

Subscriptions produce an event stream. The subscription field's DataFetcher returns a Reactive Streams `Publisher`; GraphQL Java applies the selection set to each event and emits one `ExecutionResult` per update.

Example schema:

~~~graphql
type StockPrice {
  symbol: String!
  price: Float!
}

type Subscription {
  stockPrice(symbol: String!): StockPrice!
}
~~~

DataFetcher producing a publisher:

~~~java
DataFetcher<Publisher<StockPrice>> stockPriceFetcher = environment -> {
    String symbol = environment.getArgument("symbol");
    return stockPriceService.streamFor(symbol);
};
~~~

Building a `GraphQL` instance with `SubscriptionExecutionStrategy`:

~~~java
GraphQL graphQL = GraphQL.newGraphQL(schema)
        .subscriptionExecutionStrategy(new SubscriptionExecutionStrategy())
        .build();

ExecutionResult initialResult = graphQL.execute(subscriptionInput);
Publisher<ExecutionResult> events =
        (Publisher<ExecutionResult>) initialResult.getData();
~~~

`Publisher<ExecutionResult>` is the result stream. The application must subscribe and manage backpressure, cancellation, upstream errors, and cleanup when clients disconnect.

GraphQL Java only constructs the execution result stream. It does not transmit the stream over WebSocket or Server-Sent Events on its own. A transport adapter is needed to manage handshakes, authentication, sessions, serialization, and sending each event to the client. Spring for GraphQL provides transport abstractions to handle these tasks.

## 12. Responsibilities Required for a Production Server

GraphQL Java focuses on schema execution. When using it directly to build a server, the application must supply operational and security layers:

| Responsibility | What Must Be Done |
|---|---|
| Transport | Accept HTTP/WebSocket/SSE, parse request envelopes, and serialize responses |
| Authentication | Verify credentials prior to execution |
| Authorization | Enforce permissions in services or DataFetchers per resource/field |
| Input validation | Use schema validation and enforce business constraints |
| Query limits | Cap request size, depth, complexity, aliases, and field counts |
| Timeouts | Enforce timeouts on databases, remote APIs, and execution |
| Rate limiting | Throttle requests per client, principal, or tenant |
| Observability | Record execution ID, latency, errors, DataFetcher timings, and DataLoader statistics |
| Lifecycle | Manage executors, subscriptions, cancellation, and graceful shutdown |

### 12.1. Parsing, validation, and operation caching

GraphQL Java parses documents and validates operations against the schema before running DataFetchers. Requests with invalid syntax or schema violations return validation errors without calling resolvers.

In servers receiving repeated requests for the same documents, `PreparsedDocumentProvider` can cache `PreparsedDocumentEntry` instances to reuse parsed/validated `Document`s. This eliminates redundant parsing/validation work without caching `ExecutionResult`. Cache keys must account for document content and any factors affecting validation. Never cache execution results solely by document, as results also depend on variables, users, tenants, and live data.

When using persisted queries, the transport adapter must validate hashes/documents and enforce a policy permitting only registered operations if required by the architecture.

### 12.2. Depth and complexity limits

A single operation can request deeply nested fields or multiply element counts across lists. Depth and complexity limits reduce the risk of a query exhausting CPU, database connections, or memory.

Thresholds should be tuned based on the schema and real workloads. Even a shallow query can be expensive if a field returns a huge list; conversely, a deep query can be harmless if every branch is small. Combine depth/complexity limits with mandatory pagination, timeouts, request size caps, and rate limiting.

### 12.3. Authentication and authorization

GraphQL Java does not impose a security model. DataFetchers must call a service layer that verifies permissions for the target resource, tenant, and action. Never rely on a client omitting a field as a form of data protection.

You can pass an authenticated principal or security context via `GraphQLContext`, while still enforcing authorization in the service layer because the same service may be invoked from multiple entry points.

Never put access tokens or secrets into error messages, response extensions, metric tags, or raw query logs.

### 12.4. Schema mapping verification

GraphQL Java does not automatically verify that every schema field has a matching DataFetcher. Fields without an explicit DataFetcher fall back to `PropertyDataFetcher`; if no matching property is found, the field can resolve to `null` with zero schema-build errors.

Therefore, write tests covering critical fields—especially non-null fields, interfaces/unions, and programmatically wired fields. In Spring for GraphQL applications, schema mapping inspection helps detect unmapped fields, registrations targeting non-existent fields, and argument mismatches.

## 13. Using GraphQL Java Customization Inside Spring for GraphQL

If your application already uses Spring for GraphQL, most scenarios do not require creating a `GraphQL` instance directly. Spring already manages `GraphQlSource`, `ExecutionGraphQlService`, transports, and integrated resolvers.

You can still tap into GraphQL Java APIs to customize the runtime through Spring extension points:

| Need | Extension Point |
|---|---|
| Registering DataFetchers, scalars, directives, `TypeResolver` | `RuntimeWiringConfigurer` |
| Customizing `GraphQL.Builder` | `GraphQlSourceBuilderCustomizer` |
| Customizing schema creation | `GraphQlSource.Builder.schemaFactory(...)` |
| Adding execution instrumentation | `Instrumentation` bean or `GraphQlSourceBuilderCustomizer` |
| Customizing DataFetcher errors | `DataFetcherExceptionResolver` |

### 13.1. Registering a DataFetcher via RuntimeWiringConfigurer

~~~java
@Bean
RuntimeWiringConfigurer bookWiring(BookService bookService) {
    return builder -> builder
            .type("Query", type -> type.dataFetcher("book", environment -> {
                String id = environment.getArgument("id");
                return bookService.findById(id);
            }));
}
~~~

Spring Boot detects `RuntimeWiringConfigurer` beans and applies them to the `GraphQlSource` builder. In applications using annotated controllers, prefer letting `AnnotatedControllerConfigurer` register `@QueryMapping`/`@SchemaMapping` methods. Use direct DataFetchers when low-level GraphQL Java integration is required.

### 13.2. Customizing GraphQL.Builder

You can use `GraphQlSourceBuilderCustomizer` to add instrumentation or configure `GraphQL.Builder`:

~~~java
@Bean
GraphQlSourceBuilderCustomizer graphQlCustomizer() {
    return builder -> builder.configureGraphQl(graphQlBuilder ->
            graphQlBuilder.instrumentation(new TimingInstrumentation()));
}
~~~

The Boot starter still creates `GraphQlSource` and connects it to `ExecutionGraphQlService`. The customizer modifies only the specified settings.

When replacing an execution strategy in Spring, preserve how Spring builds `DataFetcherExceptionHandler` from `DataFetcherExceptionResolver`s. Setting GraphQL Java's default handler manually can bypass the exception resolvers your application relies on.

### 13.3. When Should You Use GraphQL Java Directly?

| Situation | Appropriate Choice |
|---|---|
| Spring Boot application serving a GraphQL API | Spring for GraphQL and GraphQL Java via extension points |
| Registering custom scalars or directives | `RuntimeWiringConfigurer` |
| Customizing execution strategy or instrumentation | `GraphQlSourceBuilderCustomizer` |
| Writing a standalone validation or schema-generator tool | GraphQL Java directly |
| Embedding GraphQL in a CLI, desktop app, or non-Spring service | GraphQL Java directly |
| Implementing custom transport/protocol handling | GraphQL Java with a custom transport adapter |

Bypass Spring abstractions only when the application genuinely requires low-level control over the execution lifecycle or runs outside Spring. If you only need a custom DataFetcher, scalar, directive, or instrumentation, keep Spring as the integration layer and apply GraphQL Java APIs through the appropriate extension points.

## 14. Testing GraphQL Java Directly

When using GraphQL Java directly, you can test execution without an HTTP server. Build the schema and `GraphQL` instance in the test, call `execute` with an operation, and assert data and errors.

~~~java
@Test
void shouldResolveBookById() {
    ExecutionInput input = ExecutionInput.newExecutionInput()
            .query("""
                    query {
                      book(id: "book-01") {
                        id
                        title
                      }
                    }
                    """)
            .build();

    ExecutionResult result = graphQL.execute(input);

    assertThat(result.getErrors()).isEmpty();

    Map<String, Object> data = result.getData();
    Map<String, Object> book = (Map<String, Object>) data.get("book");
    assertThat(book.get("id")).isEqualTo("book-01");
    assertThat(book.get("title")).isEqualTo("GraphQL Java");
}
~~~

Tests should cover these categories:

1. SDL parsing and schema construction succeed.
2. Valid operations return the expected data.
3. Syntactically invalid or schema-invalid operations return validation errors without invoking DataFetchers.
4. Variables undergo proper coercion according to scalars and nullability.
5. DataFetcher exceptions produce GraphQL errors with the right path and extensions.
6. Interfaces/unions resolve to the right concrete type.
7. Custom scalars parse/serialize properly and reject invalid inputs.
8. DataLoaders batch keys, handle missing keys, and preserve mappings.
9. Queries and mutations follow their configured execution strategy order.
10. Subscriptions emit events, honor cancellation, and terminate streams cleanly.

If the application uses Spring for GraphQL, add integration tests at the `WebGraphQlHandler` or HTTP transport layer to verify request mapping, security context, and serialization. Direct GraphQL Java tests verify only the execution engine, not the transport layer.

## 15. Common Pitfalls When Using GraphQL Java Directly

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Schema build reports missing `Query` root | SDL lacks `type Query` or custom root type is not configured | Declare the query root and verify the schema definition |
| Field always returns null | DataFetcher not registered or `PropertyDataFetcher` cannot find property | Check `RuntimeWiring`, source object, and getters/record accessors |
| DataFetcher is never invoked | Syntax error, invalid field/argument, or validation failure | Inspect `ExecutionResult.getErrors()` before debugging resolvers |
| Interface/union reports unresolved type | Missing `TypeResolver` or resolver returns wrong object type | Register `TypeResolver` and check runtime classes |
| Custom scalar rejects valid data | `parseValue`/`parseLiteral`/`serialize` formats are inconsistent | Test variables, literals, and outputs together |
| DataLoader does not batch | Not using `AsyncExecutionStrategy` or registry is not per-request | Check execution strategy, dispatcher instrumentation, and registry lifecycle |
| Data leaks between two requests | Sharing a mutable `DataLoaderRegistry` or `GraphQLContext` | Create a fresh registry/context for every execution |
| Requests remain slow despite `executeAsync` | DataFetcher still blocks or awaits futures on the event loop | Return truly asynchronous `CompletionStage`s and use an appropriate executor |
| Mutation fields execute out of order | Using a non-serial execution strategy | Use `AsyncSerialExecutionStrategy` for mutation root fields |
| Subscription does not send events over the network | Created a `Publisher` without a transport adapter | Connect the `Publisher` to WebSocket/SSE transport |
| Custom error handler drops Spring error resolvers | Replaced handler at `GraphQL.Builder` inside a Spring app | Wire `DataFetcherExceptionResolver` into custom strategies |
| Instrumentation fails to record telemetry | Not registered or overwritten in the instrumentation chain | Check `GraphQL.Builder` and `ChainedInstrumentation` |
| Client receives stack traces or SQL | Error handler returns raw exception messages | Map errors to safe messages and log details on the server |

## 16. Workflow When Using GraphQL Java Directly

1. Confirm whether low-level GraphQL Java execution engine control is truly needed or if Spring extension points suffice.
2. Choose a GraphQL Java version compatible with your Java runtime and Spring dependency management if present.
3. Declare the schema in SDL; build schemas in Java only when dynamic type generation is required.
4. Build `RuntimeWiring` for DataFetchers, `TypeResolver`s, scalars, and directives.
5. Build `GraphQLSchema` and create a single reusable `GraphQL` instance.
6. Create a separate `ExecutionInput` per request, passing variables and context appropriately.
7. Create a fresh `DataLoaderRegistry` per request when operations use DataLoaders.
8. Select appropriate execution strategies and exception handlers; keep queries async and mutations serial.
9. Add instrumentation, profiling, and query limits per operational needs.
10. For subscriptions, connect the `Publisher` to transport and handle cancellation.
11. Test schema construction, execution, errors, batching, and concurrency.
12. If running inside Spring, prefer `RuntimeWiringConfigurer` and `GraphQlSourceBuilderCustomizer` so you do not spin up a parallel execution/transport lifecycle.

GraphQL Java gives you direct control over schemas, DataFetchers, and execution strategies. Apply each layer within its scope: SDL defines the contract, `RuntimeWiring` binds the contract to code, `GraphQL` executes operations, and `ExecutionResult` captures data and errors. DataLoader, `TypeResolver`, custom scalars, directives, and `Instrumentation` extend engine behavior. With Spring for GraphQL, these APIs remain accessible through `GraphQlSource` and configurers; build a standalone server only when you genuinely want to own transport, security, lifecycle, and operations yourself.

## References

- GraphQL Java — Getting Started: https://graphql-java.com/documentation/getting-started/
- GraphQL Java — Schema: https://graphql-java.com/documentation/schema/
- GraphQL Java — Data Fetching: https://graphql-java.com/documentation/data-fetching/
- GraphQL Java — Execution: https://graphql-java.com/documentation/execution/
- GraphQL Java — Batching and DataLoader: https://graphql-java.com/documentation/batching/
- GraphQL Java — SDL Directives: https://graphql-java.com/documentation/directives/
- GraphQL Java — Instrumentation: https://graphql-java.com/documentation/instrumentation/
- GraphQL Java — Subscriptions: https://graphql-java.com/documentation/subscriptions/
- Spring for GraphQL — Request Execution and GraphQlSource: https://docs.spring.io/spring-graphql/reference/request-execution.html
- Spring for GraphQL — Standalone Setup: https://docs.spring.io/spring-graphql/reference/standalone-setup.html
