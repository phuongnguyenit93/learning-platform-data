# ExecutionId

Every time GraphQL Java processes an operation, the engine attaches an identifier to that execution. This identifier has the type `graphql.execution.ExecutionId` and is commonly called the **execution ID**.

In Spring for GraphQL, the execution ID helps correlate a GraphQL request with logs, errors, and observability data from the same execution. When a resolver throws an exception, Spring can log the execution ID so operators can locate the exact request. When needed, an application can also override the default transport-provided ID or assign an ID per request.

This lesson explains what `ExecutionId` means, how Spring for GraphQL generates IDs across HTTP/WebFlux, Spring MVC, and WebSocket, how to customize it via `ExecutionIdProvider` or an interceptor, how to read the ID in resolvers, and how to test it.

## 1. Why Do We Need ExecutionId?

A GraphQL request can invoke multiple resolvers, query databases, call other services, and fail at various layers. Looking solely at the operation name such as `GetBook` is not enough to know which log entries belong to the same execution.

For example, two clients send the same operation:

~~~graphql
query GetBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Both requests share the name `GetBook`, yet one might load `book-10` while the other loads `book-20`. When a resolver fails, operations teams need a distinct identifier to correlate:

- The request received over HTTP or WebSocket.
- The execution inside GraphQL Java.
- Logs emitted by resolvers and exception handlers.
- The GraphQL error returned to the client.
- Observations or traces recorded for the request.

`ExecutionId` supplies that identifier for a single execution. It does not replace the operation name, user ID, or distributed trace ID; each value describes a different aspect.

## 2. What Is ExecutionId?

`ExecutionId` is a GraphQL Java data type in the `graphql.execution` package. It is an opaque identifier used to uniquely identify a single query execution.

Two commonly used factory methods:

~~~java
import graphql.execution.ExecutionId;

ExecutionId generated = ExecutionId.generate();

ExecutionId supplied = ExecutionId.from("request-7f2a");
~~~

- `ExecutionId.generate()` creates a new ID.
- `ExecutionId.from(String)` wraps an existing ID string.
- `toString()` returns the string representation for logging or passing through APIs.
- `equals()` and `hashCode()` support comparing IDs.

Example:

~~~java
ExecutionId executionId = ExecutionId.generate();

log.info("GraphQL execution started: {}", executionId);
~~~

Do not treat `ExecutionId` as an object carrying query metadata. It represents only the identifier. The operation name, query document, variables, and GraphQL context reside in their own dedicated components.

## 3. Distinguishing ExecutionId from Operation Name and Trace ID

The following identifiers often appear together, but each serves a distinct purpose:

| Value | Meaning | Example |
| --- | --- | --- |
| Operation name | Name given to the operation by the client in the GraphQL document | `GetBook` |
| `ExecutionId` | Identifier for a single GraphQL execution | `e9a8...` |
| HTTP request ID | Request ID assigned by the transport or gateway | `req-7f2a` |
| Distributed trace ID | Identifier linking spans across multiple services | `4bf92f...` |
| User/tenant ID | Identity of the user or tenant | `user-42` |

A `GetBook` operation may be invoked thousands of times. Therefore, the operation name is not unique enough to pinpoint a specific request.

A distributed trace may span multiple GraphQL executions or multiple requests across different services. The trace ID describes the entire distributed journey, whereas `ExecutionId` describes a single GraphQL execution.

Within a system, you can derive an `ExecutionId` from a trusted request ID for easier lookup. However, if a trace encompasses multiple GraphQL requests, do not reuse the same trace ID as the `ExecutionId` for all of them, or you will lose the ability to tell individual executions apart.

## 4. How ExecutionId Flows Through Processing

`ExecutionId` is attached to `ExecutionInput` before GraphQL Java executes the operation. Components participating in the execution can then access this ID.

~~~mermaid
flowchart TD
    A["HTTP / WebSocket request"] --> B["Spring GraphQL transport"]
    B --> C["ExecutionGraphQlRequest"]
    C --> D["ExecutionInput"]
    D --> E["GraphQL Java execution"]
    E --> F["DataFetcher / resolver"]
    E --> G["Exception handling"]
    E --> H["Instrumentation / Observation"]
    F --> I["Logs with ExecutionId"]
    G --> J["GraphQL error and server log"]
    H --> K["Trace / observation"]
~~~

A straightforward flow:

1. The transport receives the request and may assign an ID.
2. Spring constructs `ExecutionGraphQlRequest` with the document, variables, and ID.
3. Spring passes the ID into `ExecutionInput`.
4. GraphQL Java executes the operation with that ID.
5. Resolvers, exception handlers, and instrumentations can read the ID.
6. Logs or observations use the ID to correlate events belonging to the same execution.

`ExecutionId` does not automatically create a distributed trace. It is an identifying property within GraphQL execution; propagating traces across services still relies on Spring/Micrometer tracing or OpenTelemetry.

## 5. Default ID in GraphQL Java

If the application does not supply its own ID, GraphQL Java uses a default `ExecutionIdProvider` to generate an ID for each execution. The default provider generates a unique UUID-based ID.

You can reference the default provider:

~~~java
import graphql.execution.ExecutionIdProvider;

ExecutionIdProvider provider =
        ExecutionIdProvider.DEFAULT_EXECUTION_ID_PROVIDER;
~~~

`ExecutionIdProvider` is a functional interface. Its `provide` method receives:

- The query document as a string.
- The operation name, which may be `null`.
- The execution context object.

The method must return a non-null `ExecutionId`:

~~~java
ExecutionId provide(
        String query,
        String operationName,
        Object context
);
~~~

In Spring for GraphQL, the transport-provided ID is normally passed into `ExecutionInput`. Consequently, the actual ID used by the application may differ from what GraphQL Java generates when run standalone.

## 6. How Spring for GraphQL Generates IDs by Transport

Spring for GraphQL supports multiple transports. The default ID depends on the transport receiving the request:

| Transport | Default ID | Correlation Capability |
| --- | --- | --- |
| Spring WebFlux | ID of `ServerHttpRequest` | Can match WebFlux logs; with Reactor Netty it can also match server logs |
| Spring MVC | ID generated via `AlternativeJdkIdGenerator` | Does not correlate by default with another transport log ID |
| WebSocket | ID of the `subscribe` message per the GraphQL over WebSocket protocol | Used to distinguish and correlate individual operations on the same connection |

This means:

- With WebFlux, keeping the default ID is usually preferable if the goal is correlating GraphQL logs with HTTP server logs.
- With Spring MVC, the default ID still identifies the execution, though it does not automatically tie to another request ID.
- With WebSocket, a single connection can run multiple concurrent subscriptions; each `subscribe` message carries its own ID to distinguish operations.

Do not confuse the WebSocket connection ID with `ExecutionId`. A single connection can be long-lived and carry many different executions.

## 7. Reading ExecutionId in a DataFetcher

GraphQL Java provides `DataFetchingEnvironment.getExecutionId()`. Resolvers can read the current ID when logging or attaching metadata to internal work.

~~~java
import graphql.execution.ExecutionId;
import graphql.schema.DataFetchingEnvironment;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private static final Logger log =
            LoggerFactory.getLogger(BookController.class);

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id, DataFetchingEnvironment environment) {
        ExecutionId executionId = environment.getExecutionId();

        log.debug("Resolving book id={} executionId={}", id, executionId);

        return bookService.findById(id);
    }
}
~~~

Here `DataFetchingEnvironment` exposes information about the field being resolved, including the execution ID, arguments, source object, GraphQL context, and selection set.

Log only the ID and necessary metadata. Avoid logging entire query variables or sensitive data merely for troubleshooting convenience.

If a resolver does not need to emit its own logs, there is no need to read `ExecutionId` just to pass it through internal methods. Spring already uses this ID in several default logs and errors.

## 8. Global ID Customization with ExecutionIdProvider

If you want every GraphQL execution to follow a unified ID policy, you can configure an `ExecutionIdProvider` on GraphQL Java.

In Spring Boot, a clean approach is configuring it via `GraphQlSourceBuilderCustomizer`:

~~~java
import graphql.execution.ExecutionId;
import graphql.execution.ExecutionIdProvider;

import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer; // Spring Boot 3.x
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlExecutionIdConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer executionIdCustomizer() {
        ExecutionIdProvider provider =
                (query, operationName, context) -> ExecutionId.generate();

        return builder ->
                builder.configureGraphQl(graphQlBuilder ->
                        graphQlBuilder.executionIdProvider(provider));
    }
}
~~~

Spring Boot automatically detects the `GraphQlSourceBuilderCustomizer` bean and applies the configuration to the GraphQL builder.

The import package for `GraphQlSourceBuilderCustomizer` depends on the Spring Boot major version. In Spring Boot 3.x, the package is `org.springframework.boot.autoconfigure.graphql`; in Spring Boot 4.x, the package is `org.springframework.boot.graphql.autoconfigure`.

In the example, the provider generates a fresh ID for each execution. This works well when you want a transport-independent ID policy.

If your goal is correlating WebFlux logs or WebSocket protocol messages, think carefully before replacing the default ID. A global provider can break the link to the transport-supplied ID.

## 9. Creating ExecutionId from Existing Data

If the application already receives a unique request ID from a trusted gateway, you can wrap that string with `ExecutionId.from(...)`.

~~~java
ExecutionId executionId =
        ExecutionId.from("gateway-request-7f2a");
~~~

This is helpful when:

- The gateway assigns a unique request ID to each HTTP request.
- Multiple logs need to share the same lookup key.
- The system follows a consistent correlation ID convention across layers.

However, `ExecutionId.from(...)` merely wraps the string; it does not check whether the string is unique, safe, or trustworthy.

When accepting an ID from an HTTP header:

- Trust only values issued by an authenticated gateway or trusted internal source.
- Validate length and allowed character sets.
- Guarantee the ID is unique per execution.
- Never use values containing tokens, emails, phone numbers, or sensitive information.
- If no valid ID is present, keep the default transport ID or generate a new one.

Do not generate IDs using `query.hashCode()` or the operation name alone. Two concurrent requests with the same query would receive the same ID, mixing their logs together.

## 10. Overriding ExecutionId per HTTP Request

`ExecutionGraphQlRequest` lets you set `ExecutionId` directly. For HTTP and WebSocket, you can do so via `WebGraphQlInterceptor`.

Example that uses the `X-Request-ID` header only when issued by a trusted gateway and matching a valid format:

~~~java
import graphql.execution.ExecutionId;

import java.util.regex.Pattern;

import reactor.core.publisher.Mono;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

@Component
public class ExecutionIdInterceptor implements WebGraphQlInterceptor {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String requestId = request.getHeaders().getFirst("X-Request-ID");

        if (requestId != null && SAFE_ID.matcher(requestId).matches()) {
            request.executionId(ExecutionId.from(requestId));
        }

        return chain.next(request);
    }
}
~~~

If the header is valid, that ID is used for the request's `ExecutionInput`. If the header is missing or fails validation, the request retains the transport-assigned ID.

This example targets HTTP requests, which carry per-request headers. For WebSocket, do not grab a header during the handshake and reuse it for every subscription on the connection; each `subscribe` message may need its own execution ID.

If you have no gateway request ID but want to proactively generate a dedicated ID per request, you can call `ExecutionId.generate()` in the interceptor:

~~~java
@Override
public Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        Chain chain) {

    request.executionId(ExecutionId.generate());
    return chain.next(request);
}
~~~

Only do this when you have a reason to replace the default transport ID, such as standardizing an ID policy across multiple transports. Otherwise, keeping the default ID preserves built-in log correlation.

## 11. When to Use ExecutionIdProvider vs. an Interceptor

These two customization approaches serve different scopes:

| Approach | Scope | Suitable Use Case |
| --- | --- | --- |
| `ExecutionIdProvider` | ID generation policy on the GraphQL builder | Applying a consistent ID generation scheme across executions |
| `ExecutionGraphQlRequest.executionId(...)` | A specific request | Using a gateway request ID or conditionally overriding per request |
| Keeping default transport ID | Transport-specific | Correlating with WebFlux, Reactor Netty, or the WebSocket protocol |

Avoid configuring multiple layers to overwrite the ID simultaneously without an explicit order. Decide on the authoritative ID source and set it in one place.

A practical rule of thumb:

- Keep the default if the transport ID already meets your logging needs.
- Use an interceptor if only a subset of requests requires a custom ID.
- Use a provider if the whole application requires a uniform ID policy.
- Keep trace IDs in the tracing system; only promote one to `ExecutionId` when justified and its uniqueness scope is well understood.

## 12. ExecutionId in GraphQL Errors and Logs

Spring for GraphQL registers exception handling for DataFetchers. When an exception goes unhandled by resolvers, the default error is classified as `INTERNAL_ERROR` and its generic message includes the execution ID from `DataFetchingEnvironment`.

Spring also logs unresolved exceptions at `ERROR` level along with the `ExecutionId` so they can be matched against the error sent to the client. Resolved exceptions are typically logged at `DEBUG` level.

Example scenario:

~~~text
GraphQL executionId=webflux-req-91a2
DataFetcher failed while resolving Query.book
GraphQL response contains INTERNAL_ERROR
~~~

Given the ID from the log or error message, operators can search logs sharing that ID to pinpoint which resolver failed.

Not every GraphQL error includes `ExecutionId` in its message. Parse or validation errors can occur before any DataFetcher is invoked. Therefore, do not assume every error response contains a field or extension carrying the execution ID.

If the application defines a custom `DataFetcherExceptionResolver`, it can read the execution ID from `DataFetchingEnvironment` for internal logging. Only expose the ID in error responses when the API intentionally publishes it; never expose stack traces or internal details to clients.

## 13. ExecutionId in Micrometer Observation

Spring for GraphQL can emit observations for GraphQL requests via `GraphQlObservationInstrumentation` when the application configures an `ObservationRegistry` and the corresponding instrumentation.

Default request observations include keys such as:

| Key | Type | Meaning |
| --- | --- | --- |
| `graphql.operation.type` | Low cardinality | `query`, `mutation`, `subscription`, or `operation` |
| `graphql.outcome` | Low cardinality | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` |
| `graphql.execution.id` | High cardinality | `ExecutionId` of the request |
| `graphql.operation.name` | High cardinality | Operation name sent by the client |

`graphql.execution.id` is a high-cardinality key because every execution can have a distinct value.

This is useful for looking up a specific trace or observation. Do not put `ExecutionId` into labels of aggregated metrics with unbounded time series. Metric labels should favor low-cardinality values such as operation type and outcome.

You can use `ExecutionId` to link logs with traces, provided trace propagation is configured properly at the transport and instrumentation layers. Simply logging an ID does not create a distributed trace on its own.

## 14. ExecutionId with WebSocket Subscriptions

A WebSocket connection can stay open for a long time and carry multiple concurrent subscriptions. The GraphQL over WebSocket protocol uses the message ID in `subscribe` messages to distinguish operations.

Spring for GraphQL uses the `subscribe` message ID as the ID for the corresponding execution. Therefore:

- A single connection can have multiple `ExecutionId`s.
- Each subscription may live longer than a typical HTTP request.
- When a client cancels a subscription, the `complete` message is associated with that subscription's ID.
- Do not use the connection ID as the `ExecutionId` for all subscriptions.

If the application customizes WebSocket IDs, ensure each operation still gets a distinct ID and protocol correlation for `next`, `error`, and `complete` messages remains intact.

## 15. Testing ExecutionId with ExecutionGraphQlServiceTester

Spring for GraphQL provides `ExecutionGraphQlServiceTester` to test the server directly without going through HTTP, WebSocket, or RSocket.

The builder exposes `configureExecutionInput(...)`, allowing you to set the execution ID before GraphQL Java executes the operation.

Suppose a controller returns the current ID:

~~~java
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ExecutionIdController {

    @QueryMapping
    public String currentExecutionId(DataFetchingEnvironment environment) {
        return environment.getExecutionId().toString();
    }
}
~~~

Schema:

~~~graphql
type Query {
    currentExecutionId: String!
}
~~~

The test sets a fixed ID and verifies the resolver receives that exact value:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import graphql.execution.ExecutionId;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ExecutionIdTests {

    private final ExecutionGraphQlService graphQlService;

    @Autowired
    ExecutionIdTests(ExecutionGraphQlService graphQlService) {
        this.graphQlService = graphQlService;
    }

    @Test
    void passesConfiguredExecutionIdToDataFetcher() {
        ExecutionId expected = ExecutionId.from("test-execution-42");

        ExecutionGraphQlServiceTester tester =
                ExecutionGraphQlServiceTester.builder(graphQlService)
                        .configureExecutionInput((input, builder) ->
                                builder.executionId(expected).build())
                        .build();

        tester.document("{ currentExecutionId }")
                .execute()
                .path("currentExecutionId")
                .entity(String.class)
                .isEqualTo(expected.toString());
    }
}
~~~

This test verifies that an ID placed on `ExecutionInput` can be read from `DataFetchingEnvironment`. It does not test WebFlux or WebSocket default IDs; to verify transport behavior, use the corresponding tester and test the interceptor/handler at the appropriate layer.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Two requests share the same ID | Using operation name or query hash as the ID | Generate a unique ID per execution |
| GraphQL logs do not match HTTP logs | Replacing the default transport ID with a global provider | Keep the transport ID or pass a trusted correlation ID |
| WebSocket has multiple subscriptions but logs cannot tell them apart | Reusing the connection ID across all operations | Preserve the ID of each `subscribe` message |
| `ExecutionId.from(...)` receives an unsafe string | Blindly trusting a client-sent header | Accept IDs only from trusted sources and validate format |
| ID missing from a GraphQL error | Error occurred before DataFetcher or custom error handler | Check transport logs and request-level errors |
| Metric time-series count grows unbounded | Using `ExecutionId` as a metric label | Keep ID in traces/logs; use low-cardinality tags for metrics |
| IDs vary across test runs | Tests rely on auto-generated IDs | Set a deterministic ID via `ExecutionGraphQlServiceTester` |
| ID loses link to transport logs | ID overridden in an interceptor or provider | Define clearly which ID is the primary correlation source |
| Trace ID and `ExecutionId` are confused | Using one ID for both trace and execution without checking scope | Keep the two values separate or define a clear mapping rule |

## 17. Workflow for Choosing and Configuring ExecutionId

When implementing `ExecutionId` in Spring for GraphQL, follow this sequence:

1. Identify the active transport: WebFlux, Spring MVC, WebSocket, or RSocket.
2. Check whether the transport's default ID is sufficient for log lookup.
3. If the default ID fits, keep it to leverage built-in correlation.
4. If a global ID policy is needed, configure an `ExecutionIdProvider`.
5. If only specific requests need a custom ID, set `ExecutionGraphQlRequest.executionId(...)` via an interceptor.
6. If using an ID from a gateway, authenticate the source, validate the format, and ensure uniqueness per execution.
7. Read the ID in `DataFetchingEnvironment` when a resolver genuinely needs to log it.
8. Combine the ID with GraphQL error logs and Micrometer observations.
9. Never use the ID as a metric label or embed sensitive data in it.
10. Test ID propagation into `ExecutionInput` using `ExecutionGraphQlServiceTester`.
11. Test HTTP/WebSocket behavior separately if the application overrides the ID at the transport layer.

## 18. Key Takeaways

- `ExecutionId` identifies a single GraphQL execution in GraphQL Java.
- `ExecutionId.generate()` creates a new ID; `ExecutionId.from(String)` wraps an existing ID.
- The operation name is not an `ExecutionId` because many requests can share the same operation name.
- Spring for GraphQL typically uses the transport-supplied ID: WebFlux request ID, MVC generated ID, or WebSocket `subscribe` message ID.
- `ExecutionGraphQlRequest.executionId(...)` allows overriding the ID per request.
- `ExecutionIdProvider` configures the ID generation policy on the GraphQL builder.
- `DataFetchingEnvironment.getExecutionId()` lets resolvers read the current ID.
- Spring uses the ID to assist log and error correlation; Micrometer observations include the high-cardinality `graphql.execution.id` key.
- `ExecutionId` does not replace a distributed trace ID on its own.
- An ID must be unique per execution, contain no sensitive data, and never be used as a metric label.

`ExecutionId` is a small part of GraphQL execution with high operational value. By preserving the transport ID or customizing it cleanly at a single deliberate point, applications can connect requests, resolvers, errors, and observations into an easily traceable flow.

## References

- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Server Transports and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — ExecutionGraphQlRequest API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/ExecutionGraphQlRequest.html)
- [GraphQL Java — ExecutionId API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/ExecutionId.html)
- [GraphQL Java — ExecutionIdProvider API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/ExecutionIdProvider.html)
- [GraphQL Java — DataFetchingEnvironment API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetchingEnvironment.html)
