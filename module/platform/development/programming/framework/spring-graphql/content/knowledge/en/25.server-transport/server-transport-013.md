# CORS and transport

Spring for GraphQL can accept GraphQL operations over multiple transports. For web applications, HTTP is commonly used for queries and mutations; WebSocket or a suitable streaming transport is used for subscriptions. Each transport has different connection rules, security concerns, and processing behavior. CORS is an important part when browsers call a GraphQL API from another origin, yet CORS does not replace authentication, authorization, or CSRF protection.

When deploying, clearly define which origins the frontend is allowed to call from, which path hosts the GraphQL endpoint, which transports are enabled, how authentication headers are sent, and how upstream proxies forward requests. An overly permissive configuration can expose the API to unwanted websites; an incomplete configuration can cause preflight requests to be blocked before GraphQL requests even reach the server.

## 1. CORS and the same-origin policy

Browsers enforce the same-origin policy to restrict how a web page reads resources from another origin. An origin is defined by the tuple:

- Scheme, such as `http` or `https`.
- Host, such as `app.example.com`.
- Port, such as `443` or `8443`.

Therefore, the following URLs are distinct origins:

~~~text
https://app.example.com
https://api.example.com
http://app.example.com
https://app.example.com:8443
~~~

When a frontend at `https://app.example.com` calls a GraphQL endpoint at `https://api.example.com/graphql`, the browser checks the server's CORS policy. The server must return appropriate response headers so the browser allows JavaScript to read the response.

CORS is a browser-enforced mechanism. It is not authentication and does not prevent backend programs, `curl`, or native apps from calling the endpoint directly. Consequently, the GraphQL endpoint still needs authentication and authorization for every request regardless of how CORS is configured.

## 2. Preflight requests

For certain cross-origin requests, browsers send a preflight request using the `OPTIONS` method before the actual request. The preflight asks the server whether the intended origin, method, and headers are allowed.

For example, the frontend sends a `POST` with `Content-Type: application/json` and an `Authorization` header. The browser may send:

~~~http
OPTIONS /graphql HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

The server must return the appropriate allow headers:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type
Access-Control-Max-Age: 3600
Vary: Origin
~~~

If preflight is not handled properly, the browser will not send the actual GraphQL request. Therefore, when debugging CORS errors, inspect the `OPTIONS` request in browser developer tools before looking at resolvers or schemas.

Preflights typically do not carry cookies or bearer tokens like the actual request does. If Spring Security requires authentication on every request before CORS processing, `OPTIONS` may receive 401/403. Ensure CORS is processed before security authorization for preflight requests.

## 3. Configuring CORS with Spring Boot properties

Spring Boot provides a CORS configuration group for the GraphQL endpoint. An illustrative configuration in `application.yml`:

~~~yaml
spring:
  graphql:
    path: /graphql
    cors:
      allowed-origins:
        - https://app.example.com
        - https://admin.example.com
      allowed-methods:
        - GET
        - POST
        - OPTIONS
      allowed-headers:
        - Authorization
        - Content-Type
        - X-Correlation-Id
      exposed-headers:
        - X-Correlation-Id
      allow-credentials: true
      max-age: 1h
~~~

GraphQL endpoint CORS properties let you configure origins, methods, allowed request headers, exposed response headers, credentials, and preflight cache duration. Exact property names and value types can vary by Spring Boot version; consult the configuration metadata/reference for the version your project runs.

Do not enable wildcard origins casually in production. Declare the exact frontend origins needed, including scheme and host. If your frontend spans multiple environments, manage the allowlist per profile or deployment configuration instead of hardcoding a broad list across all environments.

## 4. Configuring CORS with Spring MVC

If the application uses Spring MVC and you want to manage CORS at the MVC layer, you can register a mapping for the GraphQL endpoint:

~~~java
@Configuration
public class GraphQlCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/graphql")
            .allowedOrigins(
                "https://app.example.com",
                "https://admin.example.com")
            .allowedMethods("GET", "POST", "OPTIONS")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Correlation-Id")
            .exposedHeaders("X-Correlation-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

The mapping here applies only to the `/graphql` path. If the GraphQL endpoint is moved to another path, the CORS mapping must be updated in sync. There is no need to open CORS for the entire application if the frontend only needs to call GraphQL.

Choose one place as the primary source of configuration. If you simultaneously configure CORS in Spring Boot GraphQL properties, MVC config, a reverse proxy, and a gateway unintentionally, layers may emit duplicate headers or inconsistent policies. When a response contains two different `Access-Control-Allow-Origin` values, browsers reject it.

## 5. Configuring CORS with Spring WebFlux

With a WebFlux application, you can configure CORS at the WebFlux layer:

~~~java
@Configuration
public class GraphQlCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/graphql")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "OPTIONS")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Correlation-Id")
            .exposedHeaders("X-Correlation-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

WebFlux uses the reactive web stack; do not add a `WebMvcConfigurer` configuration into a pure WebFlux application. Use the configuration matching the web application type selected by Spring Boot.

If the project uses reactive Spring Security, ensure CORS is enabled in `SecurityWebFilterChain` and the CORS configuration is registered with the right source. MVC and WebFlux configurations are not interchangeable merely by renaming the interface.

## 6. CORS and Spring Security

In an application using Spring Security, CORS must be processed before standard authorization so `OPTIONS` preflight requests do not require login. With servlet Spring Security, the configuration typically looks like:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .cors(Customizer.withDefaults())
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.OPTIONS, "/graphql").permitAll()
            .anyRequest().authenticated())
        .build();
}
~~~

The snippet above assumes the application provides a `CorsConfigurationSource` or corresponding CORS configuration for Spring Security to use. Simply setting `permitAll` for `OPTIONS` does not generate `Access-Control-Allow-*` headers on its own; the CORS policy must still be declared.

With WebFlux Security, use `ServerHttpSecurity` and enable CORS on `SecurityWebFilterChain` per your Spring Security version's API. Do not mix servlet and reactive filter chains.

Never `permitAll` the entire `/graphql` endpoint just to resolve a CORS error. Actual requests must still pass through authentication and authorization. Only `OPTIONS` preflights need to be handled without requiring user credentials.

## 7. allowedOrigins, allowedOriginPatterns, and credentials

Two common origin configurations:

- `allowedOrigins` accepts explicit origins.
- `allowedOriginPatterns` supports patterns to match origins according to configuration rules.

With `allowCredentials(true)`, you cannot return `Access-Control-Allow-Origin: *` per the CORS standard. Browsers reject wildcard origins when responses allow credentials. The server must return a specific allowlisted origin.

Example:

~~~java
configuration.setAllowedOrigins(List.of(
    "https://app.example.com",
    "https://admin.example.com"));
configuration.setAllowCredentials(true);
~~~

If you need a pattern for organization-controlled subdomains, use `allowedOriginPatterns` with a strict pattern. Never use overly broad patterns like any host or any scheme in production. Patterns only match origins; they do not authenticate users or tenants.

When using cookie/session authentication, browsers must send requests with the matching credentials mode. The server must also enable `allowCredentials` and return an explicit origin. Beyond CORS, cookies need `Secure`, `HttpOnly`, and `SameSite` attributes suited to your frontend/backend architecture. CORS alone does not cause cookies to be sent cross-site.

## 8. allowedHeaders and exposedHeaders

These two properties apply in opposite directions:

| Configuration | Meaning |
| --- | --- |
| `allowedHeaders` | Request headers that browsers are allowed to send in cross-origin requests |
| `exposedHeaders` | Response headers that JavaScript is allowed to read |

For instance, if the frontend sends `Authorization` and `X-Correlation-Id`, both headers must be allowed. If the server returns `X-Correlation-Id` and the frontend wants to read that value to report errors to support, that header must be listed in `exposedHeaders`.

There is no need to allow all headers with a wildcard if the frontend only uses a small set. List the exact required headers, such as `Authorization`, `Content-Type`, `X-Correlation-Id`, and any CSRF headers if the application uses cookie authentication.

Custom headers can trigger preflights. Whenever a new header is added on the frontend, update the CORS policy and test `OPTIONS`.

## 9. HTTP transport for GraphQL

HTTP is the most common transport for queries and mutations. Spring for GraphQL provides an HTTP handler integrated with Spring MVC or WebFlux. Spring Boot typically configures the endpoint at `/graphql`, though it can be changed via `spring.graphql.path`.

A GraphQL HTTP request typically contains a document and metadata:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json

{
  "query": "query Book($id: ID!) { bookById(id: $id) { id title } }",
  "operationName": "Book",
  "variables": {
    "id": "book-01"
  }
}
~~~

Common request fields:

| Field | Meaning |
| --- | --- |
| `query` | GraphQL document |
| `operationName` | Selects the operation when the document contains multiple operations |
| `variables` | Runtime values for variables |
| `extensions` | Extension metadata per client/server contract, such as persisted queries |

With POST, the request body is typically JSON. The server must limit body size and check content types; it should not accept unbounded arbitrary payloads.

## 10. GET and POST semantics

GraphQL over HTTP permits GET for query operations matching the transport contract. GET must not be used to execute mutations because GET has safe read semantics and can be automatically replayed by browsers, proxies, or caches.

Guidelines:

- Use POST for mutations.
- Use POST for queries if documents/variables are large or should not appear in URLs.
- Use GET for queries when caching/CDN is needed and the data suits URL semantics.
- Never put secrets, tokens, or personal data in query strings.
- The server must reject GET operations of type mutation instead of executing side effects.

GET requests typically encode `query`, `operationName`, and `variables` as query parameters. URLs can appear in browser history, proxy logs, and analytics; therefore, never pass passwords, access tokens, or sensitive data over GET.

If using persisted queries, clients can send hashes/extensions per an agreed protocol. Persisted queries do not replace authorization or query complexity limits.

## 11. HTTP responses and GraphQL errors

HTTP status and GraphQL execution results are two separate layers. A request can be valid at the transport layer while one or more fields fail during execution. In that case, the response may contain both `data` and `errors`.

Clients should:

- Check status and content type at the HTTP layer.
- Parse the GraphQL response per contract.
- Check `errors` even when `data` is populated.
- Use `extensions.code` to handle business errors.
- Avoid relying solely on HTTP 200 to conclude that all fields succeeded.

HTTP status rules for GraphQL depend on the GraphQL over HTTP specification, error type, and how your project's Spring for GraphQL version handles request/execution errors. Verify actual behavior with integration tests rather than assuming every GraphQL error returns 400 or 500.

## 12. WebSocket transport for subscriptions

Subscriptions require a long-lived streaming mechanism. Spring for GraphQL supports WebSocket transport using the GraphQL WebSocket protocol. Client and server must agree on the subprotocol, typically `graphql-transport-ws`.

Connections typically proceed as follows:

1. The browser opens a WebSocket to the GraphQL endpoint.
2. Client and server negotiate the subprotocol.
3. The client sends `connection_init`, optionally containing authentication info per contract.
4. The server authenticates the connection and sends `connection_ack` if accepted.
5. The client sends a subscription operation.
6. The server emits `next` payloads for each event and `complete`/`error` when the stream ends.

WebSocket connections typically use the same path as or a separate path from the HTTP GraphQL endpoint depending on application configuration. Publish both path and protocol clearly for the frontend.

WebSocket does not use CORS preflights the way `fetch`/XHR does. Browsers send `Origin` during the handshake; the server must check allowed origins in the WebSocket configuration. Never assume that enabling CORS for HTTP automatically secures WebSocket.

## 13. WebSocket Origin, authentication, and CSRF

For WebSocket, checking `Origin` is especially critical when using cookie/session authentication. If the server accepts connections from any website, a malicious page could attempt to open a WebSocket using the logged-in user's cookies. This is a form of Cross-Site WebSocket Hijacking.

Necessary safeguards:

- Allowlist specific origins for the WebSocket handshake.
- Authenticate the principal during handshake or connection initialization per design.
- Never trust a `userId`/`role` sent by the client in payloads.
- Enforce authorization for each subscription operation and resource.
- Handle token expiry, logout, and permission revocation in long-lived streams.
- Limit concurrent connections and subscriptions per principal/IP where appropriate.

Origin validation does not replace authentication. A request with a valid `Origin` can still be unauthenticated; likewise, a valid token does not mean any arbitrary origin should be permitted.

If using cookie authentication, consider CSRF protection for HTTP mutations and protecting WebSockets against cross-site hijacking. Never disable CSRF application-wide just to make WebSocket or GraphQL POST work. Design tokens/headers/cookies and origin policies tailored to each transport.

## 14. Configuring the WebSocket endpoint

In Spring MVC or WebFlux, the WebSocket handler is registered at a path and an origin allowlist can be configured at the WebSocket registration layer. Exact configuration shape depends on your web stack and how Spring Boot auto-configures the GraphQL WebSocket handler.

Illustrative example with Spring WebSocket handler registration:

~~~java
@Configuration
@EnableWebSocket
public class GraphQlWebSocketConfiguration implements WebSocketConfigurer {

    private final WebSocketHandler graphQlWebSocketHandler;

    public GraphQlWebSocketConfiguration(
            WebSocketHandler graphQlWebSocketHandler) {
        this.graphQlWebSocketHandler = graphQlWebSocketHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(graphQlWebSocketHandler, "/graphql")
            .setAllowedOrigins("https://app.example.com");
    }
}
~~~

This example shows where origin configuration sits on Spring's WebSocket registry; obtain the actual handler type and bean from the GraphQL WebSocket configuration your application uses. If Spring Boot already registers the endpoint automatically, do not register a second handler on the same path. Customize the existing registration or use extension points provided by your Spring for GraphQL version.

Never use `allowedOrigins("*")` on endpoints with cookie/session authentication. If multiple environments are needed, configure allowlists per deployment profile.

## 15. RSocket and other transports

Spring for GraphQL also integrates with RSocket. RSocket suits reactive communication between services or protocol-supporting clients, providing interaction models such as `request-response` and `request-stream`. Queries/mutations typically correspond to `request-response`; subscriptions/streaming can use `request-stream` depending on integration.

RSocket is not an HTTP fetch from a browser, so CORS is not the primary protection mechanism. Instead, configure authentication metadata, authorization, TLS, routes, and connection limits according to the deployment environment. Do not assume that using RSocket automatically makes an API private or safer than HTTP.

If an application only serves a browser frontend, HTTP for queries/mutations and WebSocket for subscriptions are usually sufficient. Do not add extra transports simply because the framework supports them; each transport increases configuration, test coverage, and security surface to maintain.

## 16. Reverse proxies, TLS, and path forwarding

Production deployments typically place APIs behind an ingress, load balancer, or reverse proxy. Ensure:

- TLS is used from the browser to the edge; if internal hops exist, define where TLS terminates and secure subsequent hops.
- The proxy forwards `/graphql` or the configured path accurately.
- `Origin`, `Authorization`, and required headers are not stripped or overwritten unintentionally.
- Forwarded headers are accepted only from trusted proxies; never trust `X-Forwarded-Host` sent directly by clients.
- WebSocket upgrade headers are supported by the proxy.
- Proxy idle timeouts are long enough for subscriptions while maintaining appropriate heartbeats/keep-alive.
- Request body size, connection counts, and rate limits are configured.

If the proxy rewrites `/api/graphql` to `/graphql`, the frontend must call the public URL and server/proxy must agree on paths. A 404 may indicate a path mismatch; 502/504 errors may indicate an upstream timeout or the proxy dropping connections.

Do not set overly short timeouts for long-lived WebSocket subscriptions. Conversely, do not leave connections hanging indefinitely without connection limits, heartbeats, or cleanup when clients lose connectivity.

## 17. Configuring and testing multiple transports

Have dedicated integration tests for each enabled transport:

| Transport | Tests to include |
| --- | --- |
| HTTP POST | Queries, mutations, variables, content type, auth, and GraphQL errors |
| HTTP GET | Queries allowed, mutations rejected, query string contains no secrets |
| CORS | `OPTIONS` preflight, valid/invalid origins, allowed headers, and credentials |
| WebSocket | Handshake, subprotocol, `connection_init`, authentication, subscription events, and cancellation |
| RSocket (if used) | Routes, authentication metadata, `request-response`, and `request-stream` |
| Reverse proxy | Path, TLS, forwarded headers, WebSocket upgrade, and timeouts |

Example checking CORS preflight with `WebTestClient`:

~~~java
webTestClient.options()
    .uri("/graphql")
    .header("Origin", "https://app.example.com")
    .header("Access-Control-Request-Method", "POST")
    .header("Access-Control-Request-Headers", "authorization,content-type")
    .exchange()
    .expectStatus().is2xxSuccessful()
    .expectHeader().valueEquals(
        "Access-Control-Allow-Origin", "https://app.example.com");
~~~

Also test disallowed origins and verify browsers do not receive permissive policy headers. With `allowCredentials(true)`, verify the server returns the explicit origin rather than a wildcard.

For WebSocket, use a WebSocket-capable test client and verify invalid origins are rejected at handshake. After a successful connection, test `connection_init` and operation authorization; testing only the handshake is not enough.

## 18. Common errors

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Browser reports CORS error while `curl` works | CORS is enforced by browsers; `curl` does not apply same-origin policy | Inspect `OPTIONS` and CORS response headers |
| `OPTIONS` returns 401/403 | Spring Security blocks preflight before CORS | Enable CORS in the security chain and permit `OPTIONS` handling |
| Duplicate CORS headers | Multiple layers add `Access-Control-Allow-Origin` | Pick one primary configuration source |
| Credentialed request blocked by browser | Wildcard origin used with `allowCredentials` | Return an explicit allowlisted origin |
| Custom header cannot be sent | Header missing from `allowedHeaders` | Add the required header to the preflight policy |
| JavaScript cannot read response header | Header not listed in `exposedHeaders` | Expose the exact response headers needed |
| WebSocket handshake rejected | `Origin` or subprotocol not permitted | Check `Origin` allowlist and `graphql-transport-ws` |
| WebSocket opened from untrusted site | Missing `Origin` check or unprotected cookie-based auth | Restrict origins and handle CSWSH/CSRF |
| GET mutation executes | Server does not enforce HTTP method semantics | Allow only GET queries; use POST for mutations |
| Subscription drops after a fixed interval | Proxy idle timeout or missing keep-alive | Tune timeouts and heartbeats per transport |
| Endpoint returns 404 after deploy | Proxy path and `spring.graphql.path` mismatch | Check path rewrites and public routes |

## 19. Design principles for CORS and transport

Allowlist only the frontend origins that genuinely need to call the API. Open only the required methods and headers; enable credentials when your auth model requires cookies/sessions and always return explicit origins. Let CORS process preflights before Spring Security authorization while still requiring authentication for actual GraphQL requests.

Use HTTP for queries/mutations with proper GET/POST semantics. Use WebSocket for subscriptions requiring streams, and enforce `Origin`, subprotocol, connection authentication, and operation/event-level authorization. Choose RSocket when protocol capabilities match communication needs, and configure metadata authentication and TLS.

Capture transport paths, CORS policies, proxy rewrites, TLS, body sizes, rate limits, and timeouts as testable deployment configuration. CORS only governs whether browsers can read cross-origin responses; data access permissions must still be enforced in Spring Security and application services.

In Spring for GraphQL, schemas and resolvers describe the business API, while transports determine how requests enter the server. A clean configuration keeps these boundaries clear so the frontend can call the API, subscriptions run reliably, and the endpoint remains properly secured.
