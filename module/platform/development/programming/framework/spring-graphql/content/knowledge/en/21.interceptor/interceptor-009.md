# Authentication in Spring for GraphQL Interceptors

Authentication determines who is sending a request; authorization decides what actions they are permitted to perform and what data they can access. In Spring for GraphQL, these two concerns must be placed in the right layers because HTTP GraphQL typically uses a single shared endpoint such as `/graphql`, while a single operation can read multiple fields and invoke multiple services.

`WebGraphQlInterceptor` lets you intervene in requests and responses at the transport layer. However, for HTTP, the Spring Security filter chain is usually where credentials are authenticated. For GraphQL over WebSocket, Spring for GraphQL provides `AuthenticationWebSocketInterceptor` to extract credentials from the `connection_init` payload, authenticate them, and propagate `SecurityContext` to subsequent requests on the connection. Once an identity is established, resolvers and services enforce authorization at the field or business level.

## 1. Distinguishing Authentication and Authorization

The two concepts are related but answer two different questions:

| Concept | Question | Example |
|---|---|---|
| Authentication | Who is sending the request? | A valid token represents user `alice`. |
| Authorization | What is that user allowed to do? | `alice` can read her own team's projects but cannot delete another team's projects. |

Authentication typically produces an `Authentication` object in Spring Security, containing the principal and authorities. This object is stored in `SecurityContext`.

Authorization uses the authenticated identity and permissions to decide whether to allow or deny an operation. An authenticated user may still lack the authority to invoke a mutation or read a sensitive field.

Do not use an interceptor merely to check whether a header exists and treat the request as authenticated. Headers can be forged by clients; credentials must be verified by an appropriate authentication provider.

## 2. Where Does Authentication Sit in the GraphQL Architecture?

Where authentication happens depends on the transport:

```text
HTTP GraphQL
Client Authorization header
        |
        v
Spring Security Filter Chain
        |
        | authenticate token/session
        v
SecurityContext
        |
        v
WebGraphQlInterceptor chain
        |
        v
GraphQL execution
        |
        v
@QueryMapping / @SchemaMapping
        |
        v
Service + method authorization

WebSocket GraphQL
Client connection_init payload
        |
        v
AuthenticationWebSocketInterceptor
        |
        | AuthenticationManager
        v
SecurityContext bound to connection
        |
        v
Subsequent subscribe requests
        |
        v
GraphQL execution + authorization
```

For HTTP, Spring Security protects the GraphQL URL before the request reaches the GraphQL handler. `WebGraphQlInterceptor` can read request metadata, configure `ExecutionInput`, or process the response, but it does not replace the authentication filter chain.

For WebSocket, the HTTP handshake only establishes the connection. Tokens for GraphQL are typically sent in the `connection_init` message; therefore, an interceptor that understands the WebSocket lifecycle and preserves `SecurityContext` for subsequent operations is required.

## 3. Protecting the HTTP GraphQL Endpoint with Spring Security

With Spring MVC, you can require every request to `/graphql` to be authenticated in `SecurityFilterChain`. The following example uses OAuth2 Resource Server with JWT:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/graphql").authenticated()
                .anyRequest().permitAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

The Resource Server validates the Bearer token against the application's issuer/JWK or public key configuration. When the token is valid, Spring Security creates an `Authentication` and places it in `SecurityContext`.

If the application uses Spring WebFlux, the corresponding configuration is `SecurityWebFilterChain`:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/graphql").authenticated()
                .anyExchange().permitAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

These two configurations are stack-specific alternatives; MVC applications use `HttpSecurity`, whereas WebFlux uses `ServerHttpSecurity`. Appropriate dependencies and issuer/JWT settings matching your authentication system are required.

When a request has a missing or invalid token, Spring Security rejects it at the HTTP layer before GraphQL executes. If the endpoint permits anonymous access, requests can still reach GraphQL in an unauthenticated state; resolvers/services must handle that case according to the API policy.

## 4. Accessing the Principal in Annotated Controllers

Spring for GraphQL supports `java.security.Principal` and `@AuthenticationPrincipal` as method arguments in annotated controllers. `@AuthenticationPrincipal` retrieves `Authentication.getPrincipal()` from the Spring Security context.

Example with a JWT principal:

```java
@Controller
class AccountController {

    private final AccountService accountService;

    AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @QueryMapping
    Account myAccount(@AuthenticationPrincipal Jwt jwt) {
        return accountService.findBySubject(jwt.getSubject());
    }
}
```

Here `Jwt` is the principal provided by OAuth2 Resource Server after validating the token. Never extract `sub` directly from an unverified JWT.

You can also accept `Principal` if you only need the general identity:

```java
@QueryMapping
List<Project> myProjects(Principal principal) {
    return projectService.findVisibleTo(principal.getName());
}
```

Spring for GraphQL provides `AuthenticationPrincipalArgumentResolver` to support both Spring MVC and WebFlux. The resolver uses `SecurityContextHolder` for MVC and `ReactiveSecurityContextHolder` for WebFlux. Therefore, in a reactive application, do not read `SecurityContextHolder.getContext()` manually inside a resolver and assume ThreadLocal always has data.

If the endpoint permits anonymous access, the principal may be absent. Declare and handle nullable types appropriately or require authentication at the endpoint before invoking resolvers.

## 5. Authorization by Operation and Field

Protecting the `/graphql` URL only answers whether a user may call the endpoint. It does not distinguish whether a user may call `myProjects` while being forbidden from calling `allAccounts`, because both fields share the same URL.

For finer-grained control, Spring for GraphQL recommends placing method security on the service methods invoked when resolving fields. For example:

```java
@Service
class ProjectService {

    @PreAuthorize("hasAuthority('project:read')")
    List<Project> findAll() {
        return projectRepository.findAll();
    }

    @PreAuthorize("@projectAuthorization.canRead(authentication, #projectId)")
    Project findById(UUID projectId) {
        return projectRepository.findById(projectId).orElseThrow();
    }
}
```

`@EnableMethodSecurity` enables method authorization in servlet applications. With WebFlux, use `@EnableReactiveMethodSecurity`. When Spring Security method security is enabled, `@PreAuthorize` checks permissions before invoking the method; `@PostAuthorize` can inspect the return value, though it must be used carefully with write methods because the action may already have occurred before the post-check.

For example, a controller can call the service without implementing all authorization rules itself:

```java
@Controller
class ProjectController {

    private final ProjectService projectService;

    ProjectController(ProjectService projectService) {
        this.projectService = projectService;
    }

    @QueryMapping
    Project project(@Argument UUID id) {
        return projectService.findById(id);
    }
}
```

Permission to read a project is enforced in the service, so other entry points calling the same business logic follow the same policy. This prevents protecting only one resolver while leaving another call path unguarded.

## 6. `WebGraphQlInterceptor` and Authentication for HTTP

`WebGraphQlInterceptor` can read HTTP headers and pass necessary metadata into `GraphQLContext`. However, if Spring Security has already authenticated the HTTP request, there is no need to parse the Bearer token again inside the interceptor.

Example of an interceptor that only adds the tenant ID once a trusted source has determined the tenant:

```java
@Component
class TenantContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(WebGraphQlRequest request, Chain chain) {
        String tenantId = resolveTrustedTenant(request);

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context -> context.put("tenantId", tenantId)).build()
        );

        return chain.next(request);
    }

    private String resolveTrustedTenant(WebGraphQlRequest request) {
        // Retrieve the tenant from information already verified by the security layer.
        // Do not trust an arbitrary tenant header sent by the client.
        return "resolved-tenant";
    }
}
```

This is an example of context propagation, not a complete authentication implementation. In a real application, `resolveTrustedTenant` must rely on verified principal/claims or a trusted tenant resolver; do not use a hardcoded value as shown in the example.

If you only want to copy certain HTTP headers into the GraphQL context, Spring for GraphQL provides `HttpRequestHeaderInterceptor`. Only map non-sensitive headers that are genuinely needed. Avoid putting access tokens into context or logs when resolvers can obtain the principal directly from Spring Security.

## 7. Authentication for GraphQL over WebSocket

WebSocket is a long-lived connection. After the handshake completes, the client sends a `connection_init` message according to the GraphQL over WebSocket protocol. This message's payload can carry authentication credentials:

```json
{
  "type": "connection_init",
  "payload": {
    "Authorization": "Bearer <access-token>"
  }
}
```

Spring for GraphQL provides `AuthenticationWebSocketInterceptor` for both transports:

| Transport | Interceptor | Authenticator |
|---|---|---|
| Spring MVC | `org.springframework.graphql.server.webmvc.AuthenticationWebSocketInterceptor` | `AuthenticationManager` |
| Spring WebFlux | `org.springframework.graphql.server.webflux.AuthenticationWebSocketInterceptor` | `ReactiveAuthenticationManager` |

These two interceptors use `AuthenticationExtractor` to extract authentication from the `connection_init` payload, authenticate it with the corresponding manager, and propagate `SecurityContext` to subsequent GraphQL requests on the same connection.

### Configuration for Spring MVC

```java
@Configuration
class GraphQlWebSocketSecurityConfiguration {

    @Bean
    WebSocketGraphQlInterceptor authenticationWebSocketInterceptor(
            AuthenticationManager authenticationManager) {

        return new org.springframework.graphql.server.webmvc.AuthenticationWebSocketInterceptor(
            new BearerTokenAuthenticationExtractor(),
            authenticationManager
        );
    }
}
```

### Configuration for Spring WebFlux

```java
@Configuration
class GraphQlWebSocketSecurityConfiguration {

    @Bean
    WebSocketGraphQlInterceptor authenticationWebSocketInterceptor(
            ReactiveAuthenticationManager authenticationManager) {

        return new org.springframework.graphql.server.webflux.AuthenticationWebSocketInterceptor(
            new BearerTokenAuthenticationExtractor(),
            authenticationManager
        );
    }
}
```

These two examples are alternatives depending on the application stack; do not register both simultaneously. `BearerTokenAuthenticationExtractor` reads the `Authorization` key in the `connection_init` payload by default. You can pass a different key name to the constructor if the client uses a custom payload key.

`AuthenticationManager` or `ReactiveAuthenticationManager` must be configured to authenticate the token type produced by the extractor. Merely extracting the token does not mean the token is valid.

Spring Boot Starter detects interceptor beans and registers them in the `WebGraphQlHandler` chain. Note that a chain can contain at most one interceptor of type `WebSocketGraphQlInterceptor`; it can be combined with other regular `WebGraphQlInterceptor` beans.

## 8. Customizing How Credentials Are Extracted from `connection_init`

If the payload does not use the `Authorization` key or needs a custom credential format, you can provide a custom `AuthenticationExtractor`. This interface receives the `Map<String, Object>` payload and returns `Mono<Authentication>`.

Example of a payload with an `accessToken` key:

```json
{
  "type": "connection_init",
  "payload": {
    "accessToken": "<access-token>"
  }
}
```

The extractor is responsible for turning the token into an unauthenticated authentication object suitable for the application's authentication provider. The authentication manager is where signature, issuer, audience, expiration, or other authentication details are verified.

When you need to customize both the authentication flow and how `SecurityContext` is written to the Reactor context, you can extend `AbstractAuthenticationWebSocketInterceptor`. The base class offers `authenticate(...)` and `getContextToWrite(...)` extension points. Normally, prefer the built-in interceptors and `BearerTokenAuthenticationExtractor`; customize only when the credential protocol genuinely differs.

## 9. Using the Principal in Subscriptions and Subsequent Requests

After `AuthenticationWebSocketInterceptor` successfully authenticates `connection_init`, Spring for GraphQL stores the authentication in WebSocket session attributes and propagates `SecurityContext` to subsequent subscribe requests.

Resolvers can continue receiving the principal just as with HTTP:

```java
@Controller
class NotificationController {

    @SubscriptionMapping
    Flux<Notification> notifications(@AuthenticationPrincipal Jwt jwt) {
        return notificationService.streamFor(jwt.getSubject());
    }
}
```

For subscriptions, ensure the data stream is scoped to the authenticated principal. Never allow clients to send a `userId` in an argument and use it as the sole basis to select another user's notification stream.

A WebSocket connection can outlive an access token's lifetime. Decide on the policy when a token expires or is revoked: close the connection, require the client to reconnect with a fresh token, or re-check permission validity on each event depending on security requirements. Never assume a token authenticated once remains valid forever across an unbounded connection.

## 10. Testing Authentication and Authorization

Test layers separately to pinpoint whether an issue lies in authentication, authorization, or GraphQL execution.

| Scenario | What to Verify |
|---|---|
| HTTP without credentials | Security filter chain rejects or endpoint handles anonymous access per config. |
| HTTP with invalid token | Authentication fails; resolver is not executed if the endpoint requires authentication. |
| Valid token | Principal is provided to the annotated controller. |
| User lacks authority | Method security rejects the corresponding service method. |
| User accesses another user's resource | Ownership/tenant rules deny access even though the user is logged in. |
| WebSocket missing or invalid token in `connection_init` | Authenticated operations are not allowed to run under an invalid identity. |
| Valid WebSocket token | Principal is propagated to subsequent queries/subscriptions. |
| Token expires during long-lived connection | Closing connection or requiring re-authentication matches policy. |

For controllers/services, you can use `@WithMockUser` or an appropriate test security context to test method authorization. For HTTP endpoints, use MockMvc or WebTestClient to test the filter chain and GraphQL response. For WebSocket, test the handshake, `connection_init` payload, connection acknowledgment response, and a subsequent operation.

Do not check HTTP status alone. A GraphQL operation can partially execute and return `data` alongside `errors`; method security denying a field may surface as a GraphQL error in the response. Check `data`, `errors`, `path`, and error codes per your application contract.

## 11. Common Pitfalls

**Treating the presence of an Authorization header as authenticated.** The header only carries credentials; they must be verified by a Spring Security authentication provider.

**Using `WebGraphQlInterceptor` instead of the HTTP security filter chain.** For HTTP, protect `/graphql` in `SecurityFilterChain` or `SecurityWebFilterChain`; interceptors primarily handle concerns at the GraphQL request boundary.

**Only protecting the `/graphql` URL.** All queries and mutations pass through the same endpoint. Use method security or service-level permission checks to enforce authorization by business operation and resource.

**Confusing Authentication with Authorization.** A valid token does not mean a user can read every object or invoke every mutation.

**Using `SecurityContextHolder` directly in reactive flows.** With WebFlux, the security context lives in the Reactor context. Use `@AuthenticationPrincipal`, `Principal`, reactive method security, or `ReactiveSecurityContextHolder` as appropriate.

**Forgetting to authenticate the `connection_init` payload.** A successful WebSocket handshake does not mean the user is authenticated for GraphQL operations. Configure `AuthenticationWebSocketInterceptor` if tokens are sent in the connection payload.

**Registering two `WebSocketGraphQlInterceptor` beans.** A chain supports at most one interceptor of this type. Combine required logic or use regular interceptors for other concerns.

**Passing tokens in GraphQL variables or query arguments.** Tokens can end up in logs, traces, or caches. Use the HTTP Authorization header or the `connection_init` payload depending on the transport.

**Ignoring token expiration for WebSocket.** Long-lived connections can continue after a token expires. Establish policies for expiration, revocation, and reconnection.

## Conclusion

In Spring for GraphQL, HTTP authentication should be handled in the Spring Security filter chain; `WebGraphQlInterceptor` only adds metadata and processes requests/responses as needed. For WebSocket, use `AuthenticationWebSocketInterceptor` together with `BearerTokenAuthenticationExtractor` and `AuthenticationManager` or `ReactiveAuthenticationManager` to authenticate the `connection_init` payload and propagate `SecurityContext` to subsequent operations. After authentication, use `@AuthenticationPrincipal`, `Principal`, and method security to protect data at the field/business level. Test HTTP, WebSocket, per-resource permissions, and token lifecycles separately.

## References

- [Spring for GraphQL — Security](https://docs.spring.io/spring-graphql/reference/security.html)
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL API — `AuthenticationWebSocketInterceptor` for WebMVC](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/webmvc/AuthenticationWebSocketInterceptor.html)
- [Spring for GraphQL API — `AuthenticationWebSocketInterceptor` for WebFlux](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/webflux/AuthenticationWebSocketInterceptor.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
