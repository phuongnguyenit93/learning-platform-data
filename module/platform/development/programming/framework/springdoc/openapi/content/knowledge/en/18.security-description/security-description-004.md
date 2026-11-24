# HTTP Basic and HTTP Bearer

HTTP Basic and HTTP Bearer are two common authentication mechanisms in Spring Boot APIs. Both transmit credentials via the `Authorization` HTTP header, but the data sent and how the server validates it differ. Basic sends a Base64-encoded username and password; Bearer sends an access token issued by an authentication system. When documenting an API with springdoc-openapi, both mechanisms are declared as HTTP security schemes in OpenAPI, then attached to the document globally or per operation.

It is essential to distinguish the OpenAPI contract from actual security enforcement. `@SecurityScheme` and `@SecurityRequirement` help Swagger UI and clients understand how to send credentials; they do not automatically enable HTTP Basic, verify JWTs, or protect controllers. Those responsibilities must be configured separately with Spring Security.

## 1. HTTP Basic Authentication

HTTP Basic is a simple authentication mechanism defined in HTTP. The client sends the username and password in the `Authorization` header in the form:

```http
Authorization: Basic <base64(username:password)>
```

For example, with the sample account `api-user` and password `example-password`, the client joins the two values with a colon and encodes the string to Base64. The header looks like:

```http
GET /api/profile HTTP/1.1
Host: api.example.com
Authorization: Basic YXBpLXVzZXI6ZXhhbXBsZS1wYXNzd29yZA==
```

Base64 is merely a data representation, not cryptographic encryption. Anyone who can read the header can decode it to recover the username and password. Therefore, HTTP Basic must be used over HTTPS/TLS; never send credentials over plain HTTP connections.

### Characteristics of Basic

- Simple structure, supported by many HTTP clients.
- Clients typically send credentials on every request requiring authentication.
- The server must validate credentials against a user store or authentication provider.
- No built-in token expiration mechanism; credential lifecycle depends on account policy and client storage.
- Unsuitable for embedding user passwords in widely distributed apps when safer token issuance mechanisms exist.

HTTP Basic does not itself define roles or access permissions. After successful authentication, the application must still check authorization, such as whether the user has the `ADMIN` role or permission to read the requested resource.

## 2. HTTP Bearer Authentication

HTTP Bearer uses a bearer token. The client sends the token in the header:

```http
Authorization: Bearer <access-token>
```

Example:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example.signature
```

The token can be a JWT or an opaque string. With a JWT, the token typically contains claims and a signature for the server to verify integrity. With an opaque token, the server can look up or introspect the token at the authorization server. Both cases use HTTP Bearer syntax in the header.

Bearer means that whoever possesses the token can use it according to the granted permissions. Therefore, tokens must be protected like credentials:

- Transmit only over HTTPS/TLS.
- Do not log access tokens in logs, URLs, query parameters, or error messages.
- Limit lifetime and scope appropriately.
- Have processes for token revocation, rotation, or refresh according to the authentication architecture.
- Store tokens appropriately for the client type; avoid insecure storage in browsers.

Bearer is not synonymous with JWT. JWT is simply a common token format that can be used with the Bearer scheme. A bearer token can be an opaque token without JWT structure.

## 3. Comparing HTTP Basic and HTTP Bearer

| Criterion | HTTP Basic | HTTP Bearer |
|---|---|---|
| Value in `Authorization` | `Basic base64(username:password)` | `Bearer token` |
| Information sent | Username and password | Access token |
| Server-side verification | Authentication provider checks credentials | JWT decoder, token introspection, or token verification mechanism |
| Lifecycle | Tied to credential/account | Tied to token, usually with an expiration |
| Is JWT required? | No | No; Bearer can use JWT or opaque tokens |
| Suitability | Internal APIs, simple tools, or tightly controlled environments | Modern APIs, application clients, OAuth 2.0 resource servers |
| Main risk | Password is sent repeatedly if TLS is missing | A stolen token can be used until it expires or is revoked |

Neither mechanism is automatically secure if implemented improperly. Basic requires TLS and proper password management; Bearer requires protecting tokens and validating signatures/issuer/audience/expiry or performing proper introspection.

## 4. Declaring HTTP security schemes in OpenAPI

OpenAPI represents Basic and Bearer using a Security Scheme Object with `type: http`. The `scheme` field specifies the HTTP mechanism:

```yaml
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
      description: HTTP Basic authentication over HTTPS
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Access token sent in the Authorization header
```

Explanation:

- `type: http` indicates this is an HTTP authentication scheme.
- `scheme: basic` declares HTTP Basic.
- `scheme: bearer` declares HTTP Bearer.
- `bearerFormat: JWT` is a token format hint for readers and tools; it does not force the server to verify JWTs and does not replace decoder configuration.
- `description` explains how to obtain and use credentials.

If the application uses opaque tokens, you can omit `bearerFormat` or describe the internal format with an appropriate value. Do not write `JWT` merely because a token looks like a dot-separated string; base it on the actual authentication design.

## 5. Attaching a security scheme to an operation with a Security Requirement

Declaring `components.securitySchemes` alone does not mean an operation requires authentication. To attach a scheme to an operation, OpenAPI uses a Security Requirement Object.

Example of an operation requiring Bearer:

```yaml
paths:
  /api/orders:
    get:
      operationId: listOrders
      security:
        - bearerAuth: []
      responses:
        '200':
          description: List of orders
        '401':
          description: Unauthenticated or invalid token
```

The name `bearerAuth` must match a key in `components.securitySchemes`. For HTTP Basic and HTTP Bearer, the scope list is an empty array `[]`; scopes are used with OAuth 2.0 or OpenID Connect, not plain HTTP Basic/Bearer schemes.

You can attach Basic to another operation:

```yaml
paths:
  /api/admin/audit:
    get:
      security:
        - basicAuth: []
      responses:
        '200':
          description: Audit log
```

## 6. Protecting the entire document or individual operations

OpenAPI allows declaring security at the document level or the operation level.

### Global security

When most of the API requires Bearer, you can declare it at the root level:

```yaml
security:
  - bearerAuth: []
```

Operations inherit this security requirement if they do not declare their own `security`.

### Per-operation security

An operation can alter the inheritance rule. For example, a login or health check endpoint is public:

```yaml
paths:
  /api/health:
    get:
      security: []
      responses:
        '200':
          description: Application is running
```

`security: []` on an operation means no OpenAPI security scheme is required for that operation, even if the document has global security. This is how public endpoints are documented in the specification; the server must still be properly configured to allow public access.

### Selecting among multiple alternative schemes

If an operation accepts either Basic or Bearer, declare two separate Security Requirement Objects:

```yaml
security:
  - basicAuth: []
  - bearerAuth: []
```

Elements in the array are **OR** options: the client can use Basic or Bearer.

If an operation requires both schemes simultaneously, place them in the same object:

```yaml
security:
  - basicAuth: []
    bearerAuth: []
```

Schemes in the same object form an **AND** condition: the client must satisfy both. Only use this if the server genuinely requires both credentials; do not confuse it with two alternative authentication methods.

## 7. Declaring Basic and Bearer with springdoc annotations

Springdoc reads Swagger annotations to generate security schemes and requirements. Both schemes can be declared on a configuration class:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.SecuritySchemes;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.0.0",
        description = "Order management API"
    )
)
@SecuritySchemes({
    @SecurityScheme(
        name = "basicAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "basic",
        description = "Username and password over HTTPS"
    ),
    @SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT",
        description = "Bearer access token"
    )
})
class OpenApiSecurityConfiguration {
}
```

The imports and annotations above belong to Swagger Annotations integrated by springdoc. If the project uses a different major version, check the dependency version and corresponding packages.

`@SecurityScheme` creates an entry in `components.securitySchemes`. It does not automatically attach the scheme to every operation; you need to add `@SecurityRequirement` or declare security at the document level.

## 8. Attaching `@SecurityRequirement` at the controller or method level

You can attach a requirement to a controller so its operations share the same mechanism, or attach it individually to a method for finer-grained scope.

Example of a controller requiring Bearer:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
@RequestMapping("/api/orders")
@SecurityRequirement(name = "bearerAuth")
class OrderController {

    @Operation(summary = "List orders")
    @GetMapping
    List<OrderResponse> listOrders() {
        return orderService.listOrders();
    }
}
```

If only one admin endpoint uses Basic:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
@RequestMapping("/api/admin")
class AdminController {

    @Operation(
        summary = "Read audit log",
        security = @SecurityRequirement(name = "basicAuth")
    )
    @GetMapping("/audit")
    List<AuditEntry> audit() {
        return auditService.findRecent();
    }
}
```

`OrderResponse`, `AuditEntry`, `orderService`, and `auditService` are illustrative components. The name in `@SecurityRequirement(name = ...)` must match the declared scheme name exactly.

If the document has global security but a method is public, configure the operation to clear the inherited security requirement in the manner supported by your Swagger Annotations version, then verify the result in `/v3/api-docs`. You can adjust it with a customizer if annotations cannot express the required case. Do not rely on hiding the Authorize button in Swagger UI to treat an endpoint as public.

## 9. Complete OpenAPI example for Basic and Bearer

The following document illustrates an API with a public endpoint, an endpoint using Bearer, and an endpoint accepting Basic or Bearer:

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: '1.0.0'
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
      description: HTTP Basic over HTTPS
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Bearer access token
security:
  - bearerAuth: []
paths:
  /api/health:
    get:
      security: []
      responses:
        '200':
          description: Public health check
  /api/orders:
    get:
      operationId: listOrders
      responses:
        '200':
          description: List of orders
        '401':
          description: Missing or invalid token
  /api/admin/audit:
    get:
      operationId: getAuditLog
      security:
        - basicAuth: []
        - bearerAuth: []
      responses:
        '200':
          description: Audit log
        '401':
          description: Unauthenticated
        '403':
          description: Insufficient admin privileges
```

In the example:

- `/api/health` is public thanks to `security: []`.
- `/api/orders` inherits Bearer from the document level.
- `/api/admin/audit` replaces the inherited security with two options: Basic or Bearer.

The document describes how clients send credentials. Whether an authenticated user is permitted to read the audit log still depends on server-side authorization.

## 10. Swagger UI and the Authorize button

When an OpenAPI document has `components.securitySchemes` along with Security Requirements, Swagger UI can display an **Authorize** button. Users enter the corresponding credentials:

- For `basicAuth`, the UI asks for a username and password.
- For `bearerAuth`, the UI accepts an access token; Swagger UI constructs the header according to the Bearer scheme.

After authorizing, Swagger UI sends credentials in the `Authorization` header for operations that require the corresponding scheme. Public operations with `security: []` do not require that scheme.

For Bearer, users typically enter only the token value without adding the `Bearer ` prefix manually if the UI already recognizes the scheme as HTTP Bearer and builds the header. Inspect the actual request in Swagger UI to avoid sending `Bearer Bearer ...`.

The Authorize button only assists with testing the API from the UI. It does not issue tokens, validate tokens on behalf of the server, or automatically protect the Swagger UI page or `/v3/api-docs` endpoint.

## 11. Configuring HTTP Basic in Spring Security

For the API to actually accept Basic, the application needs Spring Security and an appropriate authentication provider. Example of a minimal configuration for an illustrative environment:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BasicSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("api-user")
                        .password(encoder.encode("change-this-password"))
                        .roles("USER")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain basicSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

This is an illustrative configuration, not a production account-storage approach. The example account only has the `USER` role, so calling `/api/admin/**` will return `403`; a real system must assign the `ADMIN` role to authorized users. Use an appropriate user store, identity provider, or authentication provider; do not hard-code passwords in source code. `BCryptPasswordEncoder` stores password hashes instead of plaintext passwords.

`httpBasic()` enables HTTP Basic processing. It does not automatically create an OpenAPI security scheme; documentation still needs to be declared with springdoc annotations or OpenAPI configuration.

## 12. Configuring HTTP Bearer with a JWT Resource Server

If the access token is a JWT, Spring Security can verify tokens through OAuth 2.0 Resource Server support. The project needs the appropriate resource server dependency, such as `spring-boot-starter-oauth2-resource-server` matching your Spring Boot version.

Configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BearerSecurityConfiguration {

    @Bean
    SecurityFilterChain bearerSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated()
                )
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

You can configure the issuer via property:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
```

Spring Security uses the configured issuer metadata/JWK to verify JWTs. In a real environment, specify the issuer, audience, algorithms, expiration, claim mapping, and access permissions to match the authorization server. Declaring `bearerFormat: JWT` in OpenAPI alone configures no verification steps.

If the token is opaque, use the appropriate opaque token/introspection configuration instead of `jwt()`. OpenAPI can still use the HTTP Bearer scheme because the header syntax does not depend on whether the token is JWT or opaque.

## 13. When an application accepts both Basic and Bearer

Spring Security can configure multiple authentication mechanisms in the same application, but you must clearly define which endpoints accept which mechanism. A configuration with both `.httpBasic(...)` and `.oauth2ResourceServer(...)` does not automatically guarantee every endpoint accepts both as intended; authorization rules, authentication providers, and filter chains must align.

The two Basic and Bearer configuration classes above are independent examples. Do not simultaneously register two filter chains matching all requests without explicit matchers and ordering. You can split `SecurityFilterChain` by path or request matcher to isolate Basic and Bearer APIs. For example, an older API group uses Basic while newer public-facing APIs use Bearer. When doing so:

- Define the order and matcher of each filter chain.
- Ensure each request enters only the intended chain.
- Configure the authentication provider for Basic.
- Configure the JWT decoder or opaque token introspection for Bearer.
- Use consistent role/authority mapping.
- Describe the corresponding scheme on each operation in OpenAPI.

If an endpoint genuinely accepts either mechanism, OpenAPI needs to describe the two options as OR. If the document specifies OR while the server only enables one mechanism, clients will encounter authentication errors even though Swagger UI lets them choose either.

## 14. Distinguishing Authentication and Authorization

Authentication establishes identity or credential validity. Authorization decides what that identity is permitted to do.

Examples:

- Valid Basic credentials or valid Bearer token: authentication succeeds.
- User with role `USER` calls an endpoint restricted to `ADMIN`: authorization fails.
- Expired token, invalid signature, or wrong password: authentication fails.

Common responses:

| HTTP status | Typical meaning |
|---|---|
| `401 Unauthorized` | Missing credentials, invalid credentials, or invalid/expired token |
| `403 Forbidden` | Authenticated but lacking permission to perform the action |

The server typically returns a `WWW-Authenticate` challenge in a `401` response to indicate the authentication mechanism. For Basic, the challenge can be `WWW-Authenticate: Basic realm="..."`; for Bearer, the challenge can specify `Bearer` along with appropriate error metadata.

OpenAPI can describe `401` and `403` responses, but it does not generate challenge headers or determine status codes. The Spring Security authentication entry point and access denied handler are responsible at runtime.

## 15. CORS and the Authorization header

If a frontend calls the API from a different origin, the browser may send a CORS preflight because `Authorization` is not a simple request header. The server must permit the appropriate origin, methods, and headers.

Example CORS configuration allowing the `Authorization` header:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(List.of("https://app.example.com"));
    configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    configuration.setAllowedHeaders(List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}
```

Register `CorsConfigurationSource` with the filter chain and enable CORS integration:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

This example needs to be integrated with your existing filter chain and CORS policy. Do not use wildcard origins carelessly for APIs that accept credentials. CORS is a browser policy; it does not replace server-side authentication or authorization.

## 16. HTTPS, CSRF, and credential storage

Both Basic and Bearer require TLS to protect credentials in transit. Deploy HTTPS on the application or a trusted reverse proxy and configure forwarded headers properly so the application knows the external scheme.

CSRF must be decided based on how credentials are sent and the client model. If browsers automatically send cookies/sessions, CSRF is a risk that must be mitigated. For stateless APIs using Bearer tokens manually attached by clients in `Authorization`, the risk model differs, but you should not blindly disable CSRF if the application still has endpoints using cookies or sessions. Configure per security chain and client type.

Do not store passwords or tokens in query strings. URLs frequently appear in logs, browser history, analytics, and Referer headers. With Swagger UI, only use test credentials with appropriate scope and lifetime; do not store production tokens in documentation, examples, or shared configurations.

## 17. Checking security schemes in the generated document

After adding annotations, open `/v3/api-docs` or `/v3/api-docs.yaml` and confirm:

1. `components.securitySchemes.basicAuth` has `type: http`, `scheme: basic`.
2. `components.securitySchemes.bearerAuth` has `type: http`, `scheme: bearer`.
3. `bearerFormat` accurately reflects the token type if declared.
4. Operations requiring protection have `security` referencing the exact scheme name.
5. Public endpoints have `security: []` if the document declares global security.
6. If Basic or Bearer are alternatives, each scheme is in its own Security Requirement Object.
7. If both schemes are required simultaneously, both keys are in the same object.
8. Swagger UI displays the right credential type when clicking Authorize.
9. Test requests actually send `Authorization: Basic ...` or `Authorization: Bearer ...` according to the chosen scheme.

Do not stop at seeing Swagger UI show the Authorize button. The document must attach requirements to the right operations; if a scheme is declared without requirements, tools may not know which operations need that scheme.

## 18. Testing Spring Security at runtime

Verifying OpenAPI and verifying runtime security are two separate tasks. For each protected endpoint, test the following cases:

| Case | Usually expected result |
|---|---|
| Missing `Authorization` | `401` if endpoint requires authentication |
| Wrong Basic username/password | `401` |
| Invalid signature or expired Bearer token | `401` |
| Valid credentials but missing role | `403` |
| Valid credentials with sufficient permissions | Business success status |
| Public endpoint without credentials | Accessible according to public policy |

You can use curl to test Basic:

```bash
curl -i -u api-user:example-password \
  https://api.example.com/api/profile
```

And Bearer:

```bash
curl -i \
  -H "Authorization: Bearer <access-token>" \
  https://api.example.com/api/orders
```

Use test credentials only. Never put real tokens or passwords into shell history, tickets, or shared logs. For automated testing, use test users and narrow-scoped tokens in a test environment.

## 19. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Swagger UI has no Authorize button | Operation requirement declared without scheme, or vice versa | Check `components.securitySchemes` and `security` |
| Authorize button exists but endpoint still returns 401 | Spring Security runtime has not enabled the corresponding mechanism or credentials are wrong | Configure Basic/resource server and inspect request headers |
| Bearer sent as `Bearer Bearer ...` | User entered the prefix manually while UI already adds the scheme | Enter token per dialog instructions and inspect actual header |
| `bearerFormat: JWT` but JWTs are not verified | Confusing OpenAPI metadata with decoder configuration | Configure OAuth2 Resource Server/JWT decoder |
| Basic credentials exposed | Using HTTP without TLS or logging headers | Enforce HTTPS and redact credentials from logs |
| Public endpoint still shows authentication requirement | Inherits global security without operation override | Declare `security: []` and verify OpenAPI output |
| Operation accepts either scheme but docs require both | Placed Basic and Bearer in the same Security Requirement Object | Split into two objects to express OR |
| Signed-in user receives 403 | Authentication succeeded but missing authority/role | Check authorization mapping and endpoint rules |
| Browser blocked by CORS | CORS does not allow Authorization header or preflight | Configure appropriate allowed origins/methods/headers |
| Docs state Basic/Bearer but server lacks the mechanism | Only configured springdoc annotations | Configure Spring Security and run runtime tests |

## 20. Design principles

- Use `type: http`, `scheme: basic` to describe HTTP Basic.
- Use `type: http`, `scheme: bearer` to describe HTTP Bearer; only include `bearerFormat: JWT` when appropriate.
- Declare security schemes in `components` and attach requirements to the document or operations.
- Use separate Security Requirement Objects to express Basic **or** Bearer; share one object only when both are required.
- Use `security: []` for public operations when the document has global security.
- Use `@SecurityScheme`/`@SecuritySchemes` to declare schemes and `@SecurityRequirement` to attach them to operations.
- Configure Spring Security separately for Basic authentication or a Bearer resource server.
- Protect credentials and tokens with HTTPS, manage lifecycles, and never log them.
- Distinguish authentication from authorization; test both `401` and `403`.
- Check CORS if browser clients send the `Authorization` header.
- Verify `/v3/api-docs` alongside real requests from Swagger UI and external clients.

## Conclusion

HTTP Basic sends a Base64-encoded username and password in `Authorization`; HTTP Bearer sends an access token in the same header. OpenAPI describes them using an HTTP security scheme with `scheme: basic` or `scheme: bearer`, then uses Security Requirements to specify which operations require authentication and which mechanisms are accepted. Springdoc provides `@SecurityScheme` and `@SecurityRequirement` to generate metadata, while Spring Security performs the actual credential verification, token validation, and access control. Keep the contract aligned with runtime, enforce HTTPS, protect credentials, and test `401`, `403`, and public endpoints.
