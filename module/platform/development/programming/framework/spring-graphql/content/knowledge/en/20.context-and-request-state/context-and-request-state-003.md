# @ContextValue in Spring for GraphQL

`@ContextValue` binds a parameter of an annotated controller to an attribute in the **main `GraphQLContext`** of the current GraphQL execution. This annotation is suited for retrieving metadata shared across an operation, such as a request ID, verified tenant, locale, or tracing information.

`@ContextValue` does not read arguments passed by the client on a field, does not read HTTP headers directly, and is not an authentication mechanism. Data must be placed into `GraphQLContext` before or during GraphQL execution, usually via a `WebGraphQlInterceptor`. Only then can the controller retrieve the value with `@ContextValue`.

## 1. What is GraphQLContext?

GraphQL Java provides `GraphQLContext` to carry shared data within a GraphQL execution. The context can be read by multiple data fetchers in the same operation, even when fields are resolved in different branches.

For example, a request might need these values:

| Key in context | Purpose |
| --- | --- |
| `requestId` | Correlate logs and traces with the current request |
| `tenantId` | Scope data to the tenant determined from a trusted source |
| `locale` | Choose the appropriate language or formatting |
| `clientVersion` | Apply compatibility behavior by client version |
| `featureFlags` | Select features enabled for the current execution |

The main `GraphQLContext` is scoped to the entire query/operation. Therefore, it is the right place for metadata that may be needed across multiple resolvers. The context belongs to the current execution, not a global variable shared across the whole application.

## 2. Reading a value with @ContextValue

Suppose a controller needs to retrieve the request ID that was placed into the context:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class RequestInfoController {

    @QueryMapping
    public String requestId(
            @ContextValue("requestId") String requestId
    ) {
        return requestId;
    }
}
~~~

`@ContextValue("requestId")` instructs Spring to look up the attribute with key `requestId` from the main `GraphQLContext` and bind the value to the `String requestId` parameter.

`value` is an alias for `name`, so the following two forms are equivalent:

~~~java
@ContextValue("requestId") String requestId
~~~

~~~java
@ContextValue(name = "requestId") String requestId
~~~

If no name is specified, Spring infers the key from the method parameter name:

~~~java
@QueryMapping
public String requestId(@ContextValue String requestId) {
    return requestId;
}
~~~

When relying on inference, ensure parameter names are preserved in bytecode, for example by enabling the `-parameters` compiler option. In application code, specifying the name explicitly is usually easier to read and less dependent on build configuration.

## 3. Populating GraphQLContext with WebGraphQlInterceptor

`@ContextValue` only reads the context. For HTTP or WebSocket, `WebGraphQlInterceptor` is an appropriate place to extract metadata from the request and place it into `ExecutionInput` before GraphQL Java executes the operation.

Example reading the `X-Request-Id` header and storing it under the `requestId` key:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class RequestMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        String requestId = request.getHeaders().getFirst("X-Request-Id");

        request.configureExecutionInput((executionInput, builder) ->
                builder.graphQLContext(context -> {
                    if (requestId != null && !requestId.isBlank()) {
                        context.put("requestId", requestId);
                    }
                }).build()
        );

        return chain.next(request);
    }
}
~~~

When the interceptor calls `chain.next(request)`, the request continues to subsequent interceptors and the GraphQL engine. `requestId` is now in the main `GraphQLContext`, so the controller can read it using `@ContextValue("requestId")`.

Combined controller:

~~~java
@Controller
public class RequestInfoController {

    @QueryMapping
    public String requestId(
            @ContextValue("requestId") String requestId
    ) {
        return requestId;
    }
}
~~~

SDL:

~~~graphql
type Query {
    requestId: String!
}
~~~

If the header is missing, the interceptor does not add the `requestId` key. With the signature above, `@ContextValue` is required by default, so the resolver will raise an error when the value is missing. If the request ID is optional, use `required = false` or `Optional` as shown in the next section.

## 4. Using the built-in HttpRequestHeaderInterceptor

If you only need to copy certain HTTP headers into the GraphQL context, Spring for GraphQL provides `HttpRequestHeaderInterceptor`. You do not need to write a custom interceptor for simple cases:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.support.HttpRequestHeaderInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlHeaderConfiguration {

    @Bean
    HttpRequestHeaderInterceptor requestHeaderInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
                .mapHeader("X-Request-Id")
                .build();
    }
}
~~~

After the header is mapped into the context, the controller can retrieve the value by the corresponding key:

~~~java
@QueryMapping
public String requestId(
        @ContextValue("X-Request-Id") String requestId
) {
    return requestId;
}
~~~

The built-in interceptor is useful when the context key can match the header name. If you want to normalize key names, combine multiple metadata sources, or validate values before adding them to the context, use a custom `WebGraphQlInterceptor`.

Only copy headers that resolvers genuinely need. Do not put all headers into the context by default, as they may contain cookies, credentials, or irrelevant information.

## 5. Handling optional context values

By default, `@ContextValue` has `required = true`. If the key is absent from `GraphQLContext`, Spring throws an error when binding the parameter.

When a value may be absent, there are two common approaches.

**Option 1: `required = false`**

~~~java
@QueryMapping
public String locale(
        @ContextValue(name = "locale", required = false) String locale
) {
    return locale != null ? locale : "vi";
}
~~~

If the `locale` key does not exist, the parameter receives `null`. The parameter type must allow null and the method must handle that case.

**Option 2: using `Optional<T>`**

~~~java
import java.util.Optional;

@QueryMapping
public String locale(
        @ContextValue("locale") Optional<String> locale
) {
    return locale.orElse("vi");
}
~~~

`Optional` explicitly conveys in the signature that the context value may be absent. Both approaches are appropriate; pick one consistent convention across your project.

Do not use `required = false` for security-critical or data-partitioning data and silently fall back to a default value. For `tenantId` or metadata governing access permissions, missing context should generally cause the request to be rejected explicitly.

## 6. Accessing multiple values with GraphQLContext

When a method needs multiple keys or needs to read keys dynamically, it can accept `GraphQLContext` directly:

~~~java
import graphql.GraphQLContext;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class RequestInfoController {

    @QueryMapping
    public RequestInfo requestInfo(GraphQLContext context) {
        String requestId = context.get("requestId");
        String tenantId = context.get("tenantId");
        String locale = context.get("locale");

        return new RequestInfo(requestId, tenantId, locale);
    }
}

public record RequestInfo(
        String requestId,
        String tenantId,
        String locale
) {}
~~~

Choose `@ContextValue` when the method needs one or a few known keys; choose `GraphQLContext` directly when a varying set of metadata is needed depending on logic. Both access the main context of the same execution.

## 7. Distinguishing @ContextValue from @Argument

The two annotations obtain data from two different sources:

| Annotation | Data source | Example |
| --- | --- | --- |
| `@Argument("id")` | Argument declared on a field in the SDL and sent by the client | `book(id: "book-1")` |
| `@ContextValue("tenantId")` | Attribute placed into the main `GraphQLContext` by the server or an interceptor | Tenant determined from authentication info |
| `@LocalContextValue("permission")` | Attribute in the local GraphQL context passed down from a parent resolver | Metadata intended only for a child data branch |

Example combining an argument with context:

~~~java
@QueryMapping
public Book book(
        @Argument("id") Long id,
        @ContextValue("tenantId") String tenantId
) {
    return bookService.findByTenantAndId(tenantId, id);
}
~~~

The client specifies `id` via the GraphQL argument. The server determines `tenantId` from the context established after authentication. The resolver combines both when querying data.

Do not turn `tenantId` into an argument just to let the client send it if the tenant must be bound to the authenticated identity. Clients can modify arguments; context should be populated from a trusted server source.

## 8. Distinguishing main context and local context

Spring for GraphQL supports two types of context:

- **Main `GraphQLContext`:** shared across the entire GraphQL execution. `@ContextValue` and the `GraphQLContext` parameter access this context.
- **Local `GraphQLContext`:** passed from a data fetcher down to child data fetchers in a portion of the result tree. `@LocalContextValue` is used to read this value.

For example, a parent resolver returns `DataFetcherResult` with local context:

~~~java
import graphql.execution.DataFetcherResult;
import java.util.Map;

@QueryMapping
public DataFetcherResult<Book> book(@Argument("id") Long id) {
    Book book = bookService.findById(id);

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .localContext(Map.of("includeInternalNotes", false))
            .build();
}
~~~

A child field resolver can read that value:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(
        Book book,
        @LocalContextValue("includeInternalNotes") Boolean includeInternalNotes
) {
    if (!Boolean.TRUE.equals(includeInternalNotes)) {
        return null;
    }
    return bookService.findInternalNotes(book.id());
}
~~~

This example illustrates the scope of passing local context down to a child branch. For data needed across multiple branches or multiple fields without a parent-child relationship, the main `GraphQLContext` is more suitable. Do not use local context as a global variable to replace `@ContextValue`.

## 9. Using @ContextValue in @SchemaMapping and @BatchMapping

`@ContextValue` can be used across annotated controller handlers, not only root queries. For example, a `Book.author` field resolver needing the locale:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(
            Book book,
            @ContextValue("locale") String locale
    ) {
        return authorService.findLocalized(book.authorId(), locale);
    }
}
~~~

`@BatchMapping` can also accept `@ContextValue` or `GraphQLContext`. The context is passed to the batch loader from the same GraphQL execution's `DataFetchingEnvironment`. This is useful when a batch query requires a previously determined tenant or locale.

Example:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> authors(
        List<Book> books,
        @ContextValue("tenantId") String tenantId
) {
    Set<Long> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

    return authorService.findByTenantAndIds(tenantId, authorIds)
            .map(authorsById -> books.stream()
                    .filter(book -> authorsById.containsKey(book.authorId()))
                    .collect(Collectors.toMap(
                            book -> book,
                            book -> authorsById.get(book.authorId())
                    )));
}
~~~

The service receives the tenant as a parameter and applies it in the query. Do not store the current tenant in a field of a singleton service, as multiple GraphQL executions can run concurrently.

## 10. @ContextValue is not an authentication mechanism

Context may contain security-related information, but `@ContextValue` itself only binds a value. It does not verify the origin, check token signatures, or grant access permissions.

For user identity, prefer obtaining `Principal` or `@AuthenticationPrincipal` from the Spring Security context when integrating with Spring Security. If verified claims or metadata need to be placed into GraphQLContext, do so after authentication and permission checks at the security layer or service.

Some principles:

1. Do not trust `tenantId`, `userId`, roles, or permissions sent by the client in GraphQL arguments or unverified headers.
2. Obtain identity and tenant from an authenticated principal or token.
3. Only put verified values into `GraphQLContext`.
4. Resolvers/services must still enforce authorization when reading or updating data.
5. Do not treat a cache hit or the presence of a context key as proof of access permission.

For example, the `X-Tenant-Id` header can be spoofed by a client if the system does not verify it. If a tenant is tied to the logged-in account, determine the tenant from `Authentication` or validate the header against the list of tenants the principal is allowed to access before putting it into the context.

## 11. Per-request context and ThreadLocal

`GraphQLContext` is propagated through the GraphQL execution and can be read by data fetchers on their respective execution threads. It is not a `ThreadLocal` and does not depend on the resolver running on the same thread as the HTTP handler.

Do not use a `static ThreadLocal` variable to replace `GraphQLContext`. When GraphQL execution runs asynchronously, resolvers may execute on different threads; data in `ThreadLocal` does not automatically follow the execution without a dedicated context propagation mechanism.

For Spring MVC and WebFlux, Spring for GraphQL provides context propagation for supported cases. However, when data is metadata of the GraphQL operation, passing it via `GraphQLContext` remains the most direct and explicit approach. For Reactor-specific context, distinguish it from the main GraphQLContext and explicitly bridge it via an interceptor if required by the application.

## 12. Do not use GraphQLContext as a mutable global state store

The main context can be read by multiple resolvers in the same execution. Some APIs allow updating the context, but you should not use it as an arbitrary scratchpad for parallel resolvers to overwrite each other's state.

You should:

- Populate required metadata into the context before the GraphQL engine executes, typically in an interceptor.
- Treat context as prepared input data for the operation.
- Use clearly named keys and consistent value types.
- Only store small data that is meaningful throughout a single execution.
- Avoid storing DataLoaders, large request bodies, entity graphs, or shared mutable collections in the context without a clear reason.
- Avoid holding references to the context in singleton services or static fields after the request completes.

If a resolver needs to create data intended only for child fields, consider `DataFetcherResult.localContext` and `@LocalContextValue` instead of mutating the main context.

## 13. Testing @ContextValue with WebGraphQlTester

Because values are typically placed into context by a `WebGraphQlInterceptor`, testing through `WebGraphQlHandler` validates both the interceptor and the controller. `WebGraphQlTester` sends a mock web request through the interceptor chain before GraphQL execution occurs.

Controller using request ID:

~~~java
@Controller
public class RequestInfoController {

    @QueryMapping
    public String requestId(
            @ContextValue("requestId") String requestId
    ) {
        return requestId;
    }
}
~~~

SDL:

~~~graphql
type Query {
    requestId: String!
}
~~~

Integration test with `WebGraphQlTester`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.WebGraphQlTester;

@SpringBootTest
class ContextValueTests {

    @Autowired
    WebGraphQlHandler handler;

    @Test
    void readsRequestIdFromHttpHeader() {
        WebGraphQlTester tester = WebGraphQlTester.builder(handler)
                .headers(headers -> headers.set("X-Request-Id", "req-test-123"))
                .build();

        tester.document("{ requestId }")
                .execute()
                .path("requestId")
                .entity(String.class)
                .isEqualTo("req-test-123");
    }
}
~~~

The test assumes `RequestMetadataInterceptor` is a bean and `WebGraphQlHandler` is configured by Spring Boot. The header is added to the mock request, the interceptor copies it into the context, and the controller reads the value via `@ContextValue`.

You should add tests for:

1. Context key exists and binds to the expected type.
2. When a required key is missing, the request returns the appropriate GraphQL error.
3. When an optional key is missing, the controller receives `null` or `Optional.empty()`.
4. Two requests with different request IDs or tenants do not see each other's context.
5. Tenant value is derived from the authenticated principal, not taken directly from an untrusted header.
6. `@LocalContextValue` only receives values passed from the parent resolver.

## 14. Common errors and how to handle them

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `@ContextValue` reports missing value | Context key has not been added or key name mismatch | Check the interceptor and use an explicit name |
| Value is always `null` | Interceptor did not run, header missing, or context written under a different key | Check interceptor order and `configureExecutionInput` |
| `@ContextValue` cannot read HTTP header | Annotation only reads GraphQLContext, not transport directly | Copy the header into context using an interceptor |
| Parameter receives wrong type | Value placed in context differs from declared Java type | Standardize type where context is created or use matching type |
| Key inferred incorrectly | Parameter name not preserved or does not match context key | Declare `@ContextValue("key")` explicitly |
| Error when optional key is absent | `required` defaults to `true` | Use `required = false` or `Optional<T>` |
| Using `@ContextValue` when data is only needed in a child branch | Wrong context scope chosen | Use `@LocalContextValue` and `DataFetcherResult.localContext` |
| Tenant leaks between requests | Storing tenant in singleton/static mutable state | Use per-execution context and pass tenant via service parameters |
| Data still accessible despite missing context | Resolver uses an unsafe default value | Fail closed and enforce authorization at the service/security layer |

## 15. Workflow for using @ContextValue

When a resolver needs request metadata:

1. Determine whether the value is truly shared across the entire operation or only belongs to a child branch.
2. For operation-wide metadata, choose the main `GraphQLContext` and `@ContextValue`.
3. Populate the value into the context from an interceptor or execution configuration before resolvers run.
4. Only copy necessary headers; verify the source before using tenant- or permission-related data.
5. Use explicit key names in `@ContextValue`; choose `required = false` or `Optional` for optional data.
6. Use `GraphQLContext` directly when multiple keys or dynamic access is needed.
7. Use `@LocalContextValue` for metadata passed from a parent resolver down to a child branch.
8. Do not store request state in static fields or singleton mutable state.
9. Test both the interceptor and controller via `WebGraphQlTester`, and verify isolation between requests.

`@ContextValue` enables annotated controllers to receive GraphQL execution metadata through a clearly named parameter. When properly combined with `WebGraphQlInterceptor`, `GraphQLContext`, and your application's security mechanisms, resolvers can share request metadata without relying on global state or ThreadLocal.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — ContextValue API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/ContextValue.html)
- [Spring for GraphQL — Server Transports and WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Testing and WebGraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
