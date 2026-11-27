# Correlation ID

A Correlation ID is an identifier attached to a request so components across a system can link logs, errors, and service calls originating from the same processing flow. With GraphQL, a single HTTP request may execute many resolvers and call multiple backends. If each component logs on its own without a shared identifier, tracing the root cause of an error or latency becomes difficult.

In Spring for GraphQL, you can accept or generate a Correlation ID in a `WebGraphQlInterceptor`, place that value into `GraphQLContext`, read it in resolvers, and propagate it to downstream services. This ensures logs from the same GraphQL operation share a common reference identifier.

## 1. What problem does Correlation ID solve?

Suppose a client sends a query fetching an order along with its customer and line items:

```graphql
query OrderDetail($id: ID!) {
    order(id: $id) {
        id
        status
        customer {
            name
        }
        items {
            quantity
            product {
                name
            }
        }
    }
}
```

A single operation may pass through many components:

- The HTTP server receives the GraphQL request.
- The `Query.order` resolver loads the order.
- The `Order.customer` resolver fetches the customer.
- The `Order.items` resolver loads the line items.
- The `OrderItem.product` resolver calls the catalog service.
- Other repositories or services access the database.

If each log entry only contains a class name or message, it is hard to tell which logs belong to the same request, especially when many users call the API concurrently. Correlation ID provides a common value to filter and stitch these logs together.

Example logs for a single request:

```text
correlationId=7b2... operation=OrderDetail event=request_received
correlationId=7b2... field=Query.order event=resolver_started
correlationId=7b2... service=customer event=lookup_completed
correlationId=7b2... service=catalog event=timeout
correlationId=7b2... event=request_completed status=ERROR
```

Thanks to this, operators can search for all events sharing the same `correlationId` and reconstruct the request's path.

## 2. Distinguishing Correlation ID, Request ID, and Trace ID

Different systems may use these names with varying conventions. Align on their meaning within your project:

| Value | Common purpose | Scope |
| --- | --- | --- |
| Request ID | Identify one specific request at a single service or gateway | One request receipt |
| Correlation ID | Link multiple related logs and activities across a business flow | May span multiple services |
| Trace ID | Identify a distributed trace composed of multiple spans per tracing standards | One distributed trace |
| Span ID | Identify a single unit of work inside a trace | One span |

A Correlation ID may be created at a gateway and propagated across multiple services. Trace ID and Span ID are typically managed by a tracing system such as Micrometer Tracing, with propagation following standards like W3C Trace Context (`traceparent`).

Do not treat `X-Correlation-ID` as `traceparent` or replace distributed tracing with a plain UUID. Correlation ID is useful for searching and correlating logs; tracing provides parent-child relationships, timing, and span topology. Both mechanisms can coexist.

## 3. Choosing where to generate or accept a Correlation ID

There are two common scenarios:

1. The incoming request already carries a Correlation ID from an API gateway or upstream service. The application validates its format and continues using that value.
2. The request has no valid ID. The application generates a new ID, such as a UUID, and uses it throughout processing.

Example using the `X-Correlation-ID` HTTP header:

```http
POST /graphql HTTP/1.1
Content-Type: application/json
X-Correlation-ID: 7b2d9a1f-4a9b-4d5c-9c7d-1f6a0d4e8b10
```

The header name is an application convention, not a mandatory part of GraphQL. You can use a different name, but the client, gateway, server, and downstream services must agree on it.

Do not accept arbitrary header values sent by clients verbatim. Limit length, allowed characters, and logging format to prevent log injection or oversized data. If a value is invalid, reject the request per security policy or generate a new ID. The example below generates a new ID when the header is missing or malformed.

## 4. Creating a WebGraphQlInterceptor

`WebGraphQlInterceptor` is Spring for GraphQL's extension point for intercepting requests and responses at the web layer. An interceptor is ideal for reading the HTTP header, generating a Correlation ID, putting it into execution context, and adding it back to the response header.

```java
package com.example.graphql.config;

import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.core.annotation.Order;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    public static final String HEADER_NAME = "X-Correlation-ID";
    public static final String CONTEXT_KEY = "correlationId";

    private static final Pattern VALID_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId = resolveCorrelationId(
            request.getHeaders().getFirst(HEADER_NAME));

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context ->
                context.put(CONTEXT_KEY, correlationId)
            ).build()
        );

        return chain.next(request)
            .doOnNext(response -> response.getResponseHeaders()
                .set(HEADER_NAME, correlationId));
    }

    private String resolveCorrelationId(String incoming) {
        if (incoming != null && VALID_ID.matcher(incoming).matches()) {
            return incoming;
        }
        return UUID.randomUUID().toString();
    }
}
```

Main steps:

1. Read the `X-Correlation-ID` header from `WebGraphQlRequest`.
2. Check that the value contains only allowed characters and stays within the length limit.
3. If missing or invalid, generate a new UUID.
4. Use `configureExecutionInput` to put the ID into `GraphQLContext`.
5. After the chain finishes processing, add the same ID to the response header.

`@Component` lets Spring register the interceptor. `@Order` can specify ordering when the application has multiple interceptors; choose an order compatible with the other interceptors in your project.

## 5. Why put Correlation ID into GraphQLContext?

`GraphQLContext` is the context area bound to GraphQL execution. It is suited for sharing request-level data among resolvers without adding an argument to the schema.

In the interceptor example:

```java
request.configureExecutionInput((input, builder) ->
    builder.graphQLContext(context ->
        context.put("correlationId", correlationId)
    ).build()
);
```

The value is stored under the key `correlationId`. Resolvers, data fetchers, or execution components can read that value within the same GraphQL execution.

Do not add Correlation ID as an argument on every field like `book(id: ID!, correlationId: String)`. It is request metadata, not business data for clients to control. Putting it in context keeps the schema clean and avoids repeating arguments across fields.

`GraphQLContext` is also not a global state store. Every request needs its own context; never store Correlation ID in a static field or singleton mutable state, because concurrent requests can overwrite each other's values.

## 6. Reading Correlation ID in a resolver with @ContextValue

Spring for GraphQL provides `@ContextValue` to retrieve a value from GraphQL context in a handler method.

```java
package com.example.graphql.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class OrderQueryController {

    private static final Logger log =
        LoggerFactory.getLogger(OrderQueryController.class);

    private final OrderService orderService;

    public OrderQueryController(OrderService orderService) {
        this.orderService = orderService;
    }

    @QueryMapping
    public OrderView order(
            @Argument("id") String id,
            @ContextValue("correlationId") String correlationId) {

        log.info("Resolving order id={} correlationId={}", id, correlationId);
        return orderService.findById(id);
    }
}
```

`@ContextValue("correlationId")` reads the exact key written to context by the interceptor. No fields need to be added to the SDL, and the client cannot alter this value via GraphQL variables.

If the context value is optional, configure how missing keys are handled or use an appropriate nullable parameter type. In this application, the interceptor always creates an ID before execution, so the resolver can treat it as required. Even so, verify configuration if there are multiple entry points or tests that bypass the interceptor.

## 7. Reading context directly via DataFetchingEnvironment

When you need GraphQL Java APIs or need to pass context to a complex component, you can accept `DataFetchingEnvironment`:

```java
import graphql.schema.DataFetchingEnvironment;

@QueryMapping
public OrderView order(
        @Argument("id") String id,
        DataFetchingEnvironment environment) {

    String correlationId = environment.getGraphQlContext()
        .get("correlationId");

    return orderService.findById(id);
}
```

`environment.getGraphQlContext()` provides the context of the GraphQL execution. This is useful when a method needs several other metadata items such as tenant, locale, or authenticated request details.

If only one value is needed, `@ContextValue` usually keeps the method signature cleaner and makes the dependency more explicit. Avoid reading context arbitrarily in every layer; pass the ID as an explicit parameter to services or components that need to log it.

## 8. Propagating Correlation ID to downstream services

A Correlation ID is only useful system-wide when downstream services also receive and log it. When a resolver calls another HTTP service using `WebClient`, pass the ID in a header on that call.

```java
package com.example.graphql.order;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class CustomerClient {

    private final WebClient webClient;

    public CustomerClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<CustomerView> findCustomer(
            String customerId,
            String correlationId) {

        return webClient.get()
            .uri("/customers/{id}", customerId)
            .header("X-Correlation-ID", correlationId)
            .retrieve()
            .bodyToMono(CustomerView.class);
    }
}
```

Intermediate services can read this header, log it, and forward it to the next system. Each service should keep the same Correlation ID value for a request flow if the goal is linking logs across services.

If using `RestClient`, `RestTemplate`, messaging, or gRPC, the mechanism for attaching metadata differs. Establish a unified propagation convention and use the corresponding client interceptor/filter to avoid forgetting the header on certain calls.

Never send Correlation ID as proof of authentication. Downstream services must still authenticate the caller and check permissions independently.

## 9. Correlation ID in logs and MDC

You can log Correlation ID as a structured logging field:

```java
log.info("Loading customer customerId={} correlationId={}",
    customerId, correlationId);
```

Or put it into MDC so the logging pattern appends the field automatically:

```java
try (var ignored = org.slf4j.MDC.putCloseable(
        "correlationId", correlationId)) {
    log.info("Loading order id={}", orderId);
}
```

MDC is normally thread-bound. With Spring WebFlux, Reactor, and asynchronous resolvers, work may execute on different threads. Do not assume MDC propagates automatically across every async boundary. Manually setting and clearing MDC around a synchronous block does not guarantee the value remains present in callbacks running later.

For reactive applications, prefer passing Correlation ID explicitly or using a context propagation mechanism compatible with Reactor/Micrometer configured in the application. If using an MDC bridge, verify thread switches, errors, and cancellations; avoid leaking a previous request's value into another request.

## 10. Combining with Micrometer Tracing

Correlation ID and distributed tracing complement each other. If your application already uses Micrometer Tracing, spans can include trace ID and span ID to capture relationships between the GraphQL server, resolvers, and downstream clients when instrumentation is configured.

A logging convention might include:

```text
correlationId=7b2... traceId=4bf... spanId=91a... operation=OrderDetail
```

- `correlationId` helps search logs by business identifier or gateway-assigned ID.
- `traceId` links spans within a distributed trace.
- `spanId` identifies a specific step within the trace.

If the system already uses W3C Trace Context, let tracing instrumentation manage `traceparent` and propagation. Do not hand-craft `traceparent` headers in arbitrary formats. You can keep Correlation ID as an extra log attribute so operators can easily cross-reference support tickets, client requests, or legacy systems.

## 11. Correlation ID with multiple resolvers and DataLoaders

A GraphQL operation can invoke multiple resolvers in parallel or across different execution stages. Therefore, Correlation ID should belong to the GraphQL execution context, not to a single resolver.

For example, `Query.order`, `Order.customer`, and `Order.items` can all read the same `correlationId` from context. When resolvers use DataLoader, the batch loader can also receive `BatchLoaderEnvironment` and access the context passed during execution via the appropriate Spring for GraphQL/GraphQL Java API.

Do not store Correlation ID in mutable fields of singleton services or static variables. Those components are used concurrently by many requests and could cause logs to record the wrong ID.

With DataLoader's default per-request cache, Correlation ID normally does not need to be part of the cache key if the loader only lives for that request. However, if a loader or cache is shared beyond request scope, review the design so user/tenant data is never mixed. Correlation ID does not replace a tenant key or authorization context.

## 12. Correlation ID with GraphQL errors

A GraphQL response can contain both `data` and `errors`. Correlation ID should be logged when a resolver or exception handler handles an error so clients can supply that identifier when reporting an incident.

For example, the client receives a response header:

```http
X-Correlation-ID: 7b2d9a1f-4a9b-4d5c-9c7d-1f6a0d4e8b10
```

If the response contains errors, the client sends this ID along with the operation name and timestamp to operations. The server can locate the corresponding logs without the client sending sensitive data.

There is no strict need to repeat Correlation ID in every `errors[].extensions`. The response header is usually sufficient for HTTP clients and avoids complicating error payloads. If the API specifically requires clients that only read the response body, you can add an extension via an error handler, while standardizing the error schema and avoiding leaking internal details.

The interceptor example above adds the header when the GraphQL handler returns a response, even when the response contains GraphQL errors. If every HTTP response must include the ID, including errors occurring before the GraphQL handler is invoked, set the Correlation ID in an HTTP filter or gateway layer and configure the GraphQL interceptor to read that value.

## 13. Security when accepting Correlation ID

Correlation ID is external input if clients are allowed to send the header. Treat it as untrusted input:

- Enforce maximum length and an allowed character set.
- Disallow newline characters or control characters that could forge log entries.
- Never use Correlation ID as a token, session ID, API key, or authorization basis.
- Never embed emails, phone numbers, access tokens, or personal data in the ID.
- Do not let clients submit arbitrarily long IDs that inflate log volume or cardinality.
- If a gateway is the trusted source, trust only headers normalized by the gateway and block client spoofing via appropriate network architecture.
- Never use Correlation ID as a high-cardinality metric label; use logs or traces to query individual requests.

If you need to guarantee system-generated IDs, ignore external headers and always generate a fresh UUID at the gateway or application. If you must preserve IDs across systems, define clear trust boundaries and format validation rules.

## 14. Testing Correlation ID

Test all three behaviors: generating an ID when missing, preserving a valid ID, and propagating the ID into execution context and the response header.

For HTTP integration testing, send a request to `/graphql` and verify the response header:

```java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorrelationIdHttpTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void echoesValidCorrelationId() {
        webTestClient.post()
            .uri("/graphql")
            .header("Content-Type", "application/json")
            .header("X-Correlation-ID", "test-request-42")
            .bodyValue(Map.of("query", "{ books { id } }"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Correlation-ID", "test-request-42");
    }
}
```

This snippet demonstrates testing with `WebTestClient`; a GraphQL endpoint and corresponding `books` schema must exist in the test context. You can add assertions verifying that a mock service/resolver receives the expected context value `test-request-42`.

Scenarios to test:

- Header omitted: server generates an ID and returns it in the response header.
- Valid header: response preserves the ID per propagation policy.
- Malformed or overly long header: server generates a new ID or returns an error per chosen policy.
- GraphQL response with `errors`: Correlation ID is still present in the header.
- Concurrent requests: each request gets its own ID and logs are not mixed.
- Downstream clients: header is forwarded properly when calling other services.
- Reactive flows: context and logs remain accurate across thread switches or async completions.

## 15. CORS and reading response headers from a browser

If the frontend runs on a different origin, the browser may prevent JavaScript from reading arbitrary response headers unless the server exposes that header via CORS.

Example CORS configuration exposing `X-Correlation-ID`:

```http
Access-Control-Expose-Headers: X-Correlation-ID
```

Without exposing it, the header may still appear in the network inspector, but the frontend cannot read it via the Fetch API or `XMLHttpRequest`. Configure CORS at the responsible layer, such as Spring Security, Web MVC/WebFlux, or the API gateway; avoid declaring conflicting CORS policies.

## 16. Common errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Resolver cannot read Correlation ID | Interceptor not registered or context key mismatch | Check bean registration, interceptor ordering, and key name |
| Every request shares the same ID | Storing ID in a static field or singleton mutable state | Put value in per-request context |
| Downstream logs missing ID | Header/metadata not forwarded in client calls | Add propagation in HTTP client or messaging adapter |
| ID changes mid-flow | Each service generates a new ID instead of keeping the received one | Align on trust and propagation rules |
| MDC lost when resolver is async | MDC is thread-bound and does not follow Reactor automatically | Use context propagation or pass ID explicitly |
| Logs contain fake IDs or anomalous data | Accepting unvalidated headers | Validate length, characters, and trust source |
| Browser cannot read response header | Header not exposed via CORS | Add `Access-Control-Expose-Headers` |
| Metric cardinality spikes sharply | Using per-request ID as a metric label | Put ID in logs/traces instead of metric labels |

## 17. Implementation checklist

- Are the header name and Correlation ID scope agreed upon across gateway, GraphQL server, and downstream services?
- Does the interceptor accept valid IDs or generate a new ID when needed?
- Are input values constrained in length and allowed characters?
- Is the ID placed into `GraphQLContext` per request?
- Do resolvers and batch loaders read context properly?
- Do downstream HTTP/messaging clients forward the ID?
- Does logging preserve the ID during asynchronous execution?
- Is Correlation ID distinguished from Trace ID and Span ID?
- Does the GraphQL response return the ID so clients can report errors?
- Can browser clients read the header via CORS when needed?
- Is the ID prevented from being used as an authentication mechanism or high-cardinality metric label?
- Do tests cover concurrent requests, errors, and propagation?

Correlation ID ties together events arising from a single GraphQL request across resolvers and downstream services. In Spring for GraphQL, `WebGraphQlInterceptor` can accept or generate an ID, store it in `GraphQLContext`, and return it in a response header. Resolvers read it with `@ContextValue`, then forward the ID to downstream clients and logging. By keeping request scope clear, validating incoming headers, and integrating cleanly with Micrometer Tracing, teams can trace errors and latency across the system without turning Correlation ID into authentication data or shared state.
