# Why Authorization Should Not Be Declared Merely as a Regular Header Parameter

The `Authorization` header carries authentication credentials that clients send to prove identity or access rights. When documenting an API with OpenAPI, this header must be represented using security mechanisms (`security scheme` and `security requirement`) rather than being declared merely as a regular header parameter.

The reason lies directly in the OpenAPI Specification rules: header parameters named `Accept`, `Content-Type`, and `Authorization` are ignored. These three headers carry standard protocol-level semantics and are described through dedicated OpenAPI structures. `Accept` and `Content-Type` are expressed through media types in `content`; authentication credentials are described using `components.securitySchemes` and `security`.

With Spring Boot, `springdoc-openapi` can read security annotations to generate those structures. Swagger UI uses them to render the **Authorize** button and attach credentials when testing requests. Spring Security or the application's authentication layer remains responsible for validating tokens and enforcing access control.

## 1. Why Is `Authorization` Different from a Regular Header?

Headers like `X-Request-Id`, `X-Tenant-Id`, or `If-Match` can be part of the request contract. You can document them with `@Parameter` or `@RequestHeader` so clients know the header's name, data type, meaning, and requirement.

`Authorization` serves a different role: it transports credentials per HTTP authentication mechanisms. Example:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOi...
Accept: application/json
```

In the request above:

- `Authorization` carries a Bearer access token.
- `Accept` tells the server which representation the client prefers.
- `GET /api/orders/42` identifies the invoked operation.

OpenAPI reserves dedicated structures for these three special-purpose headers. According to Parameter Object rules, header parameters named `Accept`, `Content-Type`, or `Authorization` are ignored. Therefore, declaring `@Parameter(name = "Authorization", in = HEADER, ...)` is not the right way to document authentication and may not appear as expected in documents consumed by validators or client generators.

| Header | How to Document in OpenAPI |
|---|---|
| `Authorization` | `components.securitySchemes` and `security` |
| `Accept` | Media types in `responses.content` |
| `Content-Type` | Media types in `requestBody.content` |
| `X-Request-Id` | Regular header parameter |
| `X-Tenant-Id` | Regular header parameter, if it is genuinely request data rather than credentials |

Never place real tokens in `@Parameter` examples, `@ExampleObject`, or API descriptions. Tokens are secrets and not static sample contract data.

## 2. Declaring HTTP Bearer Authentication

If the API accepts a Bearer access token in the `Authorization` header, declare an HTTP security scheme with `scheme: bearer`.

Corresponding OpenAPI specification:

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: 1.0.0
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - bearerAuth: []
paths:
  /api/orders/{id}:
    get:
      summary: Get order by ID
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Order found
```

Key parts:

- `components.securitySchemes.bearerAuth` defines an authentication scheme named `bearerAuth`.
- `type: http` specifies that this is an HTTP authentication scheme.
- `scheme: bearer` indicates the Bearer scheme.
- `bearerFormat: JWT` is a format hint for readers; it does not make validators check JWT signatures nor mandate that tokens must be JWTs.
- Document-level `security` applies the security requirement to operations unless an operation specifies its own rules.
- `bearerAuth: []` declares no OAuth2 scopes; for HTTP Bearer, the scope array is empty.

When using Bearer authentication, clients send a header formatted as `Authorization: Bearer <token>`. Swagger UI can construct this header from the security scheme once the user enters a token in the **Authorize** dialog.

## 3. Configuring a Bearer Scheme with Swagger Annotations

With Springdoc, you can declare a security scheme using `@SecurityScheme`. Example:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "Enter access token to authenticate requests"
)
class OpenApiSecurityConfiguration {
}
```

The annotation above creates the definition in `components.securitySchemes`. It only describes how clients send credentials.

To require a token for controller operations, attach `@SecurityRequirement`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
@SecurityRequirement(name = "bearerAuth")
class OrderController {

    @GetMapping("/{id}")
    @Operation(summary = "Get order by ID")
    OrderResponse getById(@PathVariable Long id) {
        return orderService.getById(id);
    }
}
```

In this example, `@SecurityRequirement` attaches the `bearerAuth` requirement to the controller's operations. The annotation can be placed on methods when only certain operations require authentication. The name in `@SecurityRequirement(name = "bearerAuth")` must match the security scheme's `name` exactly.

To declare document-wide security requirements, place the security requirement in `@OpenAPIDefinition` or use an OpenAPI bean/customizer. Once document-level security is applied, check whether public operations need to override that requirement.

## 4. Distinguishing Security Scheme from Security Requirement

These two components serve different roles:

| Component | Question It Answers | Example |
|---|---|---|
| Security Scheme | Which authentication mechanism does the application support and how do clients send credentials? | HTTP Bearer, HTTP Basic, OAuth2, API key |
| Security Requirement | Which scheme does an operation or the entire document require? | `security: - bearerAuth: []` |

Merely declaring `components.securitySchemes` does not mean every endpoint requires authentication. A scheme is just a reusable definition. To enforce it in the contract, add `security` at the document or operation level.

Example specifying security for one operation:

```yaml
paths:
  /api/profile:
    get:
      security:
        - bearerAuth: []
      responses:
        '200':
          description: User profile
```

Example declaring document-level security:

```yaml
security:
  - bearerAuth: []
```

When security is declared at the document level, it acts as the default for operations. An operation with its own `security` field overrides the document-level security requirement for that operation.

## 5. Documenting Public Endpoints When the Document Has Global Security

A service often has both public endpoints and endpoints requiring authentication. For instance, `/api/catalog` may be public while `/api/orders` requires a Bearer token.

In OpenAPI, if the document has global security while an operation needs no authentication, that operation must declare `security: []` to clear the inherited requirement:

```yaml
security:
  - bearerAuth: []
paths:
  /api/catalog:
    get:
      summary: Browse public catalog
      security: []
      responses:
        '200':
          description: Catalog list
  /api/orders:
    get:
      summary: View current user's orders
      responses:
        '200':
          description: Order list
```

`security: []` indicates the operation requires no security scheme according to the OpenAPI contract. It does not configure Spring Security to allow anonymous access. If runtime still enforces login, Swagger UI may call the documented public operation and receive `401` or `403`.

Conversely, if the documentation lacks a security requirement while runtime demands a token, Swagger UI users will not see an **Authorize** prompt and test requests will fail. Documentation and runtime security policies must remain synchronized.

## 6. Common Security Scheme Types

OpenAPI supports several authentication types. Choose the type reflecting how the server actually validates credentials.

| Mechanism | OpenAPI Declaration | Common Credential Format |
|---|---|---|
| HTTP Bearer | `type: http`, `scheme: bearer` | `Authorization: Bearer <token>` |
| HTTP Basic | `type: http`, `scheme: basic` | `Authorization: Basic <credentials>` |
| API key in header | `type: apiKey`, `in: header`, `name: X-API-Key` | `X-API-Key: <key>` |
| API key in cookie | `type: apiKey`, `in: cookie`, `name: SESSION` | Cookie with declared name |
| OAuth2 | `type: oauth2`, declaring flows and scopes | Access token via OAuth2 flow; typically sent as Bearer |
| OpenID Connect | `type: openIdConnect`, declaring discovery URL | Authentication based on OpenID Connect |

### HTTP Basic

```yaml
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
security:
  - basicAuth: []
```

Basic authentication sends Base64-encoded username/password credentials in the Authorization header. Base64 is not encryption; use only over TLS and in accordance with system security policies.

### API Key in a Custom Header

```yaml
components:
  securitySchemes:
    apiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
security:
  - apiKeyAuth: []
```

`X-API-Key` is a custom header, so it can be documented using an API key security scheme. If a legacy API uses the `Authorization` header with a custom convention, model it with an appropriate HTTP authentication scheme if applicable and check tool support. Do not turn it into an ordinary header parameter.

### Declaring an API Key with Annotations

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "apiKeyAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key",
    description = "System-issued API key"
)
class ApiKeySecurityConfiguration {
}
```

When applying this scheme, reference it via `@SecurityRequirement(name = "apiKeyAuth")` or declare it in the document's `security`.

## 7. OAuth2 and Scopes

OAuth2 differs from HTTP Bearer schemes in level of detail. A Bearer scheme states that clients send a token in the Authorization header. OAuth2 additionally documents the flow clients use to obtain access tokens and the scopes tokens can be granted.

OpenAPI example:

```yaml
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            orders:read: Read orders
            orders:write: Create or update orders
paths:
  /api/orders:
    get:
      security:
        - oauth2:
            - orders:read
      responses:
        '200':
          description: Order list
```

Under `security`, scope lists are meaningful only for OAuth2 or OpenID Connect. For HTTP Bearer, Basic, and API key, the scope value is typically an empty array.

When using OAuth2, declare flows matching your client type and active identity provider setup. Never use example URLs as production endpoints; pull the authorization URL, token URL, and scopes from your system's identity provider configuration. Swagger UI can help initiate the OAuth2 flow, though client registration, redirect URIs, PKCE, and token policies must still be configured properly on the identity provider.

## 8. OR and AND Logic in Security Requirements

OpenAPI allows an operation to accept multiple authentication methods.

Objects in the `security` array represent alternative options (OR). Schemes listed together inside the same Security Requirement Object must all be satisfied simultaneously (AND).

Example accepting either a Bearer token or an API key:

```yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
```

The client only needs to satisfy one of the two options.

Example requiring both a Bearer token and a tenant API key:

```yaml
security:
  - bearerAuth: []
    tenantKey: []
```

The client must send both credentials. Verify that the server actually enforces the exact same AND/OR logic; OpenAPI descriptions do not alter filters or authorization rules in Spring Security.

## 9. Why Not Use `@RequestHeader` or `@Parameter` for Authorization?

Spring MVC can accept headers via `@RequestHeader`:

```java
@GetMapping("/profile")
ProfileResponse getProfile(
    @RequestHeader("X-Request-Id") String requestId
) {
    return profileService.getProfile(requestId);
}
```

This suits business headers or request metadata like correlation IDs. For `Authorization`, Spring Security typically reads and validates credentials via the security filter chain before requests reach controllers. Controllers do not need to declare tokens as parameters solely so Springdoc includes them in documentation.

Example to avoid:

```java
// Do not use this approach to document authentication in OpenAPI.
@GetMapping("/profile")
ProfileResponse getProfile(
    @RequestHeader("Authorization") String authorization
) {
    // ...
}
```

Declaring this gives the impression that the controller is directly responsible for authentication, whereas tokens are usually handled in the filter chain. More importantly, OpenAPI ignores header parameters named Authorization. Define a security scheme and attach a security requirement instead.

If the application genuinely must read the `Authorization` header manually for a special protocol, separate the runtime handling decision from contract documentation. Never rely on a regular header parameter to substitute for a security scheme.

## 10. Spring Security Enforces Actual Authentication and Authorization

Declaring `@SecurityScheme` or `@SecurityRequirement` only creates OpenAPI documentation. They do not:

- Verify JWT signatures or token expiration.
- Validate issuer, audience, or claim permissions.
- Populate `Authentication` in `SecurityContext`.
- Reject unauthenticated requests or return `401`/`403`.
- Issue or refresh tokens.

With Spring Security Resource Server, runtime configuration can use JWT as follows:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/catalog/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

The example above only illustrates protecting the API at runtime; the application also needs the Resource Server dependency and an issuer/JWK or decoder configuration. If Swagger UI/API Docs endpoints are protected, decide explicitly which matchers are permitted and which require authentication. When customizing API Docs or Swagger UI paths, update the corresponding matchers.

An endpoint marked `security: []` in documentation can still be blocked by Spring Security. Conversely, an endpoint marked as requiring Bearer in documentation may still be publicly open if runtime is misconfigured. Testing both layers is mandatory.

## 11. How Does Swagger UI Use Security Schemes?

When a document contains `components.securitySchemes` and operations define `security`, Swagger UI can:

1. Display the **Authorize** button labeled with the scheme name.
2. Let users enter tokens or credentials matching the scheme.
3. Attach the Authorization header, API key header, or matching credentials to **Try it out** requests.
4. Show whether credentials are currently applied during the UI session.

For HTTP Bearer, users typically paste the access token into the Authorize dialog. Swagger UI prepends the `Bearer` prefix per the scheme. Check the documentation for your bundled Swagger UI version if token entry or OAuth2 flow behavior differs.

Do not enable persistent credential storage in shared browsers or public environments without proper justification and safeguards. Never place tokens in query strings, documentation examples, logs, or screenshots. When testing APIs, use least-privilege tokens in appropriate environments.

## 12. CORS When Swagger UI Calls Authenticated APIs

If Swagger UI and the API reside on different origins, browsers enforce CORS policies. The `Authorization` header typically triggers an `OPTIONS` preflight request. The server must permit the required origins, methods, and headers.

Illustrative CORS configuration example:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(List.of("https://docs.example.com"));
    configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    configuration.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-Request-Id"));

    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", configuration);
    return source;
}
```

This is an example for a predetermined origin. Do not open wildcard origins indiscriminately when using credentials. CORS only controls browser cross-origin access; it does not validate tokens and does not replace authorization.

## 13. Verifying Documentation Generated by Springdoc

After configuring, open the API Docs endpoint, typically `/v3/api-docs`, and inspect these fields:

```json
{
  "components": {
    "securitySchemes": {
      "bearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT"
      }
    }
  },
  "security": [
    {
      "bearerAuth": []
    }
  ]
}
```

Verify that specific operations require the right scheme, public operations declare `security: []` if needed, and `Authorization` does not appear as an ordinary parameter. You can run an OpenAPI validator to detect structural errors or references to nonexistent security schemes.

Test runtime behavior with standalone requests:

```bash
# Without token: protected endpoint must reject per policy.
curl -i http://localhost:8080/api/orders/42

# Send valid token in test environment.
curl -i -H "Authorization: Bearer <ACCESS_TOKEN>" \
  http://localhost:8080/api/orders/42
```

Replace `<ACCESS_TOKEN>` with a test token issued for the corresponding environment. Never commit real tokens into source code or stored documentation.

## 14. Common Issues

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Authorization` does not appear in Parameters list | OpenAPI ignores header parameters named Authorization | Use `securitySchemes` and `security` |
| Authorize button missing in Swagger UI | Scheme not declared or operations do not reference a scheme | Check `components.securitySchemes` and `security` |
| Scheme exists but operation shows no lock icon | Security Requirement not attached | Declare security at document, controller, or operation level |
| Swagger UI sends request and receives `401` | Token missing, malformed, expired, or invalid | Inspect header, token, issuer, audience, and decoder |
| Receives `403` despite valid token | User lacks required authority/scope | Check authorization rules and scope-to-authority mapping |
| Public endpoint still shows security lock | Operation inherits global security | Declare `security: []` on public operations |
| Docs require Bearer but API allows anonymous | Spring Security runtime does not require auth | Inspect `SecurityFilterChain` and test anonymous requests |
| Request from Swagger UI fails with CORS error | Origin or `Authorization` header not allowed | Check preflight `OPTIONS` and CORS configuration |
| API key sent in wrong header | Wrong `in` or `name` in API key scheme | Match `in: header` and actual header name |

## 15. Checklist for Documenting Authorization Properly

- [ ] Identify the real mechanism: Bearer, Basic, API key, OAuth2, or OpenID Connect.
- [ ] Declare the security scheme in `components.securitySchemes` or via `@SecurityScheme`.
- [ ] Attach security requirements at document, controller, or operation level per policy.
- [ ] Do not declare `Authorization` via `@Parameter` or `@RequestHeader` just to describe credentials.
- [ ] Use `security: []` on public operations if the document has global security.
- [ ] Declare OAuth2 scopes only when the scheme is OAuth2/OpenID Connect and scopes are meaningful.
- [ ] Verify Swagger UI renders Authorize and sends credentials properly on Try it out.
- [ ] Verify Spring Security actually rejects requests with missing or invalid credentials.
- [ ] Check CORS if UI and API are on different origins.
- [ ] Never put real tokens, API keys, or passwords in docs, examples, or logs.

`Authorization` is part of HTTP security mechanics, so OpenAPI describes it using security schemes and security requirements. This enables Swagger UI and client generators to understand how to send credentials while keeping a clear boundary between the API contract and actual protection enforcement. Spring Security must still validate tokens and authorize each request; documentation is only valuable when it accurately reflects that policy.
