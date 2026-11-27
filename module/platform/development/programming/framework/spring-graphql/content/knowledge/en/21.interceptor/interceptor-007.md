# Adding Headers to the Response

In web applications, HTTP response headers carry metadata alongside the response body. For example, the server may return a correlation ID for the client to include when reporting errors, add a cookie after login, specify caching policies, or provide an API version identifier. In Spring for GraphQL, you can add these headers using **WebGraphQlInterceptor** after the GraphQL engine processes the operation.

The GraphQL response body and HTTP response headers are two different things. The body contains data in `data`, errors in `errors`, and GraphQL metadata in `extensions`. Headers belong to the HTTP transport layer. If the client needs to read a value such as a request ID from the HTTP response, put it in a response header; if the value is part of the GraphQL data contract, consider returning it in a field or `extensions`.

## Where Does WebGraphQlInterceptor Process the Response?

WebGraphQlInterceptor sits in the request-processing chain of Spring for GraphQL. The interceptor receives WebGraphQlRequest, can inspect or add information before invoking the GraphQL engine, and then receives WebGraphQlResponse when the operation completes:

~~~text
HTTP request
    |
    v
WebGraphQlInterceptor
    |
    v
GraphQL engine and resolvers
    |
    v
WebGraphQlResponse
    |
    v
WebGraphQlInterceptor processes response
    |
    v
HTTP response headers and body
~~~

The intercept method returns Mono<WebGraphQlResponse>. Calling chain.next(request) forwards the request to the next interceptor and eventually to the GraphQL engine. When the publisher emits the response, the interceptor can add headers to the response before the transport writes the HTTP response back to the client.

Spring for GraphQL provides WebGraphQlResponse.getResponseHeaders() to access the HttpHeaders that will be written to the HTTP response. By default, this header list is empty. This API is meant for GraphQL over HTTP; it does not add separate HTTP headers per WebSocket operation because the HTTP handshake has already completed before operations begin.

## Adding a Fixed Header to a GraphQL HTTP Response

The following example adds the X-GraphQL-Server header to every response passing through the interceptor:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class ResponseHeaderInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        return chain.next(request).doOnNext(response -> {
            response.getResponseHeaders()
                    .set("X-GraphQL-Server", "catalog-api");
        });
    }
}
~~~

The code performs three things:

1. Receives the request and forwards it with chain.next(request).
2. Waits for GraphQL to finish processing and emit WebGraphQlResponse.
3. Writes the header into response.getResponseHeaders().

doOnNext is suitable because adding a header is a side effect on the response object. If you want to transform and return a different response, you can use map and return the response after updating headers:

~~~java
return chain.next(request).map(response -> {
    response.getResponseHeaders().set("X-GraphQL-Server", "catalog-api");
    return response;
});
~~~

Both approaches process the response inside the reactive pipeline, without needing block() or synchronously waiting for GraphQL execution.

## Registering the Interceptor in Spring Boot

When using Spring Boot with the GraphQL starter and HTTP transport, simply declare WebGraphQlInterceptor as a Spring bean. You can use @Component as in the previous example or create a bean with @Configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebGraphQlInterceptor;

@Configuration
public class GraphQlInterceptorConfiguration {

    @Bean
    WebGraphQlInterceptor responseHeaderInterceptor() {
        return (request, chain) ->
                chain.next(request).doOnNext(response ->
                        response.getResponseHeaders()
                                .set("X-GraphQL-Server", "catalog-api"));
    }
}
~~~

Spring Boot automatically detects WebGraphQlInterceptor beans and registers them with the web transport. If creating WebGraphQlHandler manually or configuring the transport manually, you must add the interceptor to the corresponding chain. When the application has multiple interceptors, design a clear processing order, especially when one interceptor creates data in GraphQLContext and another reads it after execution completes.

## Adding Dynamic Headers from GraphQLContext

Sometimes a header value is only known after a resolver runs. For example, a login mutation creates a session cookie or a resolver generates a business tracking code. The controller can put the value into GraphQLContext; the interceptor reads that value after chain.next(request) completes and adds the header.

Controller storing the value to issue:

~~~java
import graphql.GraphQLContext;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class SessionController {

    private final SessionService sessionService;

    public SessionController(SessionService sessionService) {
        this.sessionService = sessionService;
    }

    @MutationMapping
    public LoginPayload login(
            @Argument LoginInput input,
            GraphQLContext context) {

        CreatedSession session = sessionService.login(input);
        context.put("sessionCookieValue", session.cookieValue());

        return new LoginPayload(session.userId(), session.expiresAt());
    }
}
~~~

Interceptor reading the value after GraphQL engine execution:

~~~java
import graphql.GraphQLContext;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class SessionCookieInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        return chain.next(request).doOnNext(response -> {
            GraphQLContext context =
                    response.getExecutionInput().getGraphQLContext();
            String cookieValue = context.get("sessionCookieValue");

            if (cookieValue != null) {
                ResponseCookie cookie = ResponseCookie
                        .from("SESSION", cookieValue)
                        .httpOnly(true)
                        .secure(true)
                        .sameSite("Lax")
                        .path("/")
                        .build();

                response.getResponseHeaders()
                        .add(HttpHeaders.SET_COOKIE, cookie.toString());
            }
        });
    }
}
~~~

This example illustrates passing a value from a resolver to an interceptor via GraphQLContext. The GraphQL payload only returns userId and expiration time; the cookie value is not included in the response body. In a real application, SessionService must create and verify sessions according to the system's authentication policy.

GraphQLContext here belongs to a single execution. Do not hold cookie values in a field of the interceptor or a singleton service, because multiple requests can run concurrently. If an operation has multiple resolvers writing to the same key, clearly define which resolver owns that value or use a separate per-field data structure.

## Using ResponseCookie to Create Set-Cookie

When adding cookies, use Spring's ResponseCookie instead of concatenating header strings manually. The builder supports important attributes:

| Attribute | Meaning |
| --- | --- |
| httpOnly | Prevents browser-side JavaScript from reading the cookie via document.cookie |
| secure | Only sends the cookie over HTTPS connections |
| sameSite | Controls cookie transmission in cross-site contexts |
| path | Restricts the path to which the cookie is sent |
| domain | Restricts the host/domain receiving the cookie |
| maxAge | Duration the cookie remains valid |

Session cookie example:

~~~java
import java.time.Duration;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;

ResponseCookie cookie = ResponseCookie.from("SESSION", sessionId)
        .httpOnly(true)
        .secure(true)
        .sameSite("Strict")
        .path("/")
        .maxAge(Duration.ofHours(8))
        .build();

response.getResponseHeaders().add(
        HttpHeaders.SET_COOKIE,
        cookie.toString());
~~~

Choose SameSite according to how the frontend and backend are deployed. Strict restricts sending cookies on cross-site navigations; Lax allows some top-level navigations; None allows cross-site contexts and requires Secure. When using authentication cookies, also design appropriate CSRF protection. Never log tokens or cookie values.

## Distinguishing add and set

getResponseHeaders() returns HttpHeaders. Two commonly used operations are add and set:

| Method | Behavior | When to Use |
| --- | --- | --- |
| set(name, value) | Replaces existing values of the header with a single value | Single-valued headers like X-Request-Id |
| add(name, value) | Appends a new value while keeping existing values | Headers allowing multiple values or multiple Set-Cookie headers |

Example:

~~~java
HttpHeaders headers = response.getResponseHeaders();
headers.set("X-Request-Id", requestId);
headers.add(HttpHeaders.SET_COOKIE, firstCookie.toString());
headers.add(HttpHeaders.SET_COOKIE, secondCookie.toString());
~~~

Do not combine multiple Set-Cookie values into a single comma-separated string. Each cookie needs its own Set-Cookie header; use add to keep cookies independent.

If multiple interceptors write to the same header, chain order can determine the final value when using set. Agree on which interceptor owns each header to avoid overwriting one another or creating unwanted duplicate values.

## Adding a Correlation ID to Response Headers

An application often needs to return a correlation ID for clients to attach when reporting errors. You can generate the ID in an interceptor before invoking the GraphQL engine, put it in GraphQLContext so resolvers and logs can read it, and then return the same value in the HTTP response header.

~~~java
import java.util.Map;
import java.util.UUID;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class RequestIdInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String requestId = UUID.randomUUID().toString();
        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(Map.of("requestId", requestId)).build());

        return chain.next(request).doOnNext(response ->
                response.getResponseHeaders().set("X-Request-Id", requestId));
    }
}
~~~

Resolvers can read the same request ID:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;

@QueryMapping
public String requestId(@ContextValue("requestId") String requestId) {
    return requestId;
}
~~~

In cases where multiple interceptors add data to GraphQLContext, check how they combine context and their registration order so existing keys are not accidentally replaced. You can use a dedicated interceptor to generate the request ID and configure the context once.

## Response Headers vs. GraphQL Response Extensions

A GraphQL response body can contain an extensions field:

~~~json
{
  "data": {
    "greeting": "Hello"
  },
  "extensions": {
    "requestId": "d6d5a5f1-7b2d-4a55-a2a5-8f4e8f1d0001"
  }
}
~~~

This is metadata inside the JSON body. Whereas the header:

~~~http
X-Request-Id: d6d5a5f1-7b2d-4a55-a2a5-8f4e8f1d0001
~~~

is metadata of the HTTP response. Choose based on your needs:

- Use HTTP headers for request IDs, cache policies, cookies, or transport metadata.
- Use extensions for metadata tied to GraphQL execution that GraphQL clients need to read in the body.
- Use fields in the schema if the data is part of the business contract and needs to be queried with types.

Do not put business data into headers merely because an interceptor can write headers. Headers have size limits, lack GraphQL typing, and are unsuitable for complex objects or lists.

## WebSocket and RSocket Have Different Limitations from HTTP

WebGraphQlInterceptor is used in the HTTP and WebSocket processing chain. However, WebGraphQlResponse.getResponseHeaders() is designed to add headers to HTTP responses. With WebSocket, the HTTP handshake has already completed before the client sends GraphQL operations. Therefore, this API cannot be used to send a new HTTP response header for each query or subscription over an open connection.

If you need to send metadata alongside each WebSocket result, use the GraphQL response body, extensions, or a protocol-appropriate payload design. If metadata is needed during the handshake, configure it at the WebSocket handshake/interceptor layer before the connection is established.

RSocket uses its own interceptor mechanism, RSocketQlInterceptor, and has no HTTP response headers. Do not apply WebGraphQlResponse examples to the RSocket transport.

## CORS: Allowing Browsers to Read Custom Headers

The server may return the X-Request-Id header, but JavaScript running on another origin cannot automatically read every response header. For cross-origin requests, the server must declare the header in Access-Control-Expose-Headers or the corresponding Spring Boot configuration.

Example application.yml:

~~~yaml
spring:
  graphql:
    cors:
      allowed-origins: https://app.example.com
      allowed-methods: POST
      exposed-headers:
        - X-Request-Id
        - X-GraphQL-Server
~~~

The exposed-headers property instructs the browser to allow scripts to read the listed headers. If the application uses cookies or credentials in cross-origin requests, configure allow-credentials and specific origins appropriately; never combine credentials with a wildcard origin. CORS only controls browser access permissions and is not an API authentication or authorization mechanism.

The client can read the header after the request completes:

~~~javascript
const response = await fetch("/graphql", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    query: "{ greeting }"
  })
});

const requestId = response.headers.get("X-Request-Id");
const body = await response.json();
~~~

If the header is not exposed in CORS, the response may still contain the header on the wire, but JavaScript receives null when calling headers.get.

## Security When Adding Response Headers

Response headers can influence how browsers, proxies, and caches handle data. Apply these principles:

- Do not put access tokens, refresh tokens, or personal data into custom headers without a clear requirement.
- Do not echo client-sent headers verbatim without validating format and length.
- Do not allow untrusted data to inject newline characters into header values.
- Use ResponseCookie with appropriate HttpOnly, Secure, and SameSite attributes when issuing cookies.
- Do not overwrite Content-Type, Content-Length, Transfer-Encoding, or server-managed transport headers without special reason.
- Avoid manually adding hop-by-hop headers such as Connection or Transfer-Encoding; they belong to the connection/proxy layer.
- Only return Cache-Control appropriate to the data. Responses containing private information typically require no-store or private policies per application requirements.
- Do not treat headers as a security boundary. Authorization must still be enforced in Spring Security, services, or the domain layer.

If a header is an application-wide policy, such as Strict-Transport-Security or Content-Security-Policy, consider configuring it in Spring Security or the web server so it applies uniformly across all endpoints. WebGraphQlInterceptor is suited for metadata tied specifically to GraphQL responses.

## Testing Response Headers

GraphQlTester is useful for verifying GraphQL data, but when verifying HTTP response headers, test via WebTestClient or MockMvc. Example with WebTestClient:

~~~java
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ greeting }"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("X-Request-Id")
        .expectBody()
        .jsonPath("$.data.greeting").isEqualTo("Hello");
~~~

Scenarios that should be tested:

| Scenario | What to Verify |
| --- | --- |
| Successful query | Custom header appears in the HTTP response |
| Mutation returning a GraphQL error | Interceptor still adds the header if the GraphQL engine returns a normal response |
| Request validation failure | Clearly verify whether the interceptor receives a response to add headers |
| Multiple interceptors writing the same header | No unintended overwriting |
| Multiple Set-Cookie headers | Each cookie is sent as a separate header value |
| CORS cross-origin | Browser script can read exposed headers |
| WebSocket operation | Do not expect HTTP response headers per message |
| Missing context value | Interceptor does not issue a cookie/header with a null value |

For cookies, check HttpOnly, Secure, SameSite, Path, and Max-Age attributes in the Set-Cookie header as well. Do not just verify that the cookie name appears.

## Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Header does not appear | Interceptor is not registered or response bypassed the chain | Check the WebGraphQlInterceptor bean and web transport |
| Header appears in server logs but browser cannot read it | CORS exposed-headers is not configured | Add the header to spring.graphql.cors.exposed-headers |
| Header is always null | Context key not set by resolver or misspelled | Check key name and execution order |
| Cookie gets overwritten | Using set for multiple Set-Cookie headers | Use add for each cookie |
| Header is duplicated | Multiple interceptors calling add for the same value | Pick one owner for the header or use set |
| WebSocket has no new headers | HTTP handshake completed before operations | Use extensions or payload for per-message metadata |
| Response header contains invalid value | Input data was not validated | Validate and restrict header values |
| Changing response body has no effect | Using getResponseHeaders for JSON data or vice versa | Choose HTTP header, extensions, or field according to purpose |

## Design Principles for Response Header Interceptors

When adding headers in Spring for GraphQL, remember:

1. **Use WebGraphQlInterceptor.** Add headers after chain.next(request), once WebGraphQlResponse is available.
2. **Write to getResponseHeaders().** These are the HttpHeaders that the HTTP transport puts into the response.
3. **Distinguish body and headers.** Use extensions or fields for GraphQL data; use headers for HTTP metadata.
4. **Choose add or set purposefully.** Use add for multiple Set-Cookie headers and set for single-valued headers.
5. **Register the interceptor as a bean.** Spring Boot automatically registers WebGraphQlInterceptor beans with the web transport.
6. **Use GraphQLContext for per-execution dynamic values.** Never store request values in singleton fields.
7. **Configure CORS exposed headers.** Browsers require exposed-headers for JavaScript to read custom headers.
8. **Protect cookies and headers.** Validate values, use secure cookie attributes, and never leak credentials.
9. **Understand transport limitations.** The response header API is for HTTP; it does not add headers per WebSocket message or RSocket response.
10. **Test at the HTTP layer.** Use WebTestClient or MockMvc to verify actual headers.

WebGraphQlInterceptor allows adding HTTP response headers after the GraphQL engine completes an operation. Spring for GraphQL provides WebGraphQlResponse.getResponseHeaders() to write metadata to the response; GraphQLContext can pass resolver-created values to the interceptor; ResponseCookie supports issuing cookies with security attributes. Clearly distinguishing HTTP headers from the GraphQL response body, configuring CORS properly, and respecting WebSocket/RSocket limitations make adding headers consistent and safer.

## References

- [Spring for GraphQL - Server Transports and WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL - WebGraphQlResponse API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/WebGraphQlResponse.html)
- [Spring Boot - Spring for GraphQL and CORS](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Boot - Application Properties: spring.graphql.cors](https://docs.spring.io/spring-boot/appendix/application-properties/)
