# OpaqueTokenAuthenticationProvider and OAuth 2.0 Token Introspection in Spring Security

## 1. Learning Objectives and Problem Statement

A Resource Server (RS) receiving an HTTP request containing `Authorization: Bearer <access-token>` needs to know whether the token is still valid and which permissions it grants. With an **opaque token**, the token's contents are not parsed directly by the application; the RS typically queries the Authorization Server (AS) via **OAuth 2.0 Token Introspection** per [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662). Spring Security provides `OpaqueTokenAuthenticationProvider` in the **Servlet** architecture to perform this authentication using an `OpaqueTokenIntrospector`.

After this lesson, you should be able to clarify:

1. How opaque access tokens, Bearer tokens, and token introspection differ; why "opaque" describes how the RS treats the token value rather than a cryptographic algorithm.
2. The path from `BearerTokenAuthenticationFilter` → `BearerTokenAuthenticationToken` → `ProviderManager` → `OpaqueTokenAuthenticationProvider` → `OpaqueTokenIntrospector` → `BearerTokenAuthentication` in Spring Security Servlet.
3. The request/response contents of RFC 7662, especially the difference between `{"active":true}`, `{"active":false}`, and an HTTP 401 caused when the **client calling the introspection endpoint** is unauthorized by the AS.
4. How Spring Boot configures the introspection URI, client credentials, scope-to-authority mapping, and endpoint protection policies; how to read principal details after authentication.
5. The boundary between token authentication and authorization by `scope`, `aud`, `client_id`, `sub`, or tenant; why `active=true` alone should not be treated as sufficient for every API.
6. The differences between Servlet `OpaqueTokenAuthenticationProvider` and WebFlux `OpaqueTokenReactiveAuthenticationManager`/`ReactiveOpaqueTokenIntrospector`.
7. How to design timeouts, AS error handling, caching, and revocation; how to test with Java/JUnit and real HTTP without exposing access tokens or introspection credentials.

**Technical context:** Spring Security 6.x, Spring Boot 3.x, Java 17+; the main APIs continue to exist in newer Spring Security lines. A few builders and defaults change across versions, so always check the javadoc of the dependency your project uses. This lesson focuses on **Bearer token authentication at the Resource Server**, not implementing an Authorization Server that mints tokens, and does not mix with OIDC `oauth2Login()`.

## 2. From Bearer Token to Opaque Token

### 2.1. Bearer Describes Usage; Opaque Describes Token Interpretation

A Bearer token is a credential: anyone who possesses and presents a valid token to an endpoint can be accepted subject to the token's conditions and authorization scope. For example:

```http
GET /api/messages HTTP/1.1
Host: api.example.org
Authorization: Bearer N6E9XyGd7xq...redacted
```

The `Authorization: Bearer` header belongs to the OAuth 2.0 Bearer Token Usage layer [RFC 6750](https://www.rfc-editor.org/rfc/rfc6750). **Bearer does not mean JWT.** An access token can be a random opaque string, a self-contained JWT with claims, or another AS-defined format.

An opaque token typically looks like a string with no structure useful to the RS:

```text
qL8rX9vP2... (hypothetical string, not a real token)
```

The RS must not arbitrarily slice the string, Base64-decode it, or infer user/scope itself. It must apply the protocol or verification mechanism published by the AS. An opaque value may be a lookup key for a server-side record, though RFC 7662 does not mandate that implementation.

A JWT access token **can also go through introspection**. Spring Security's `opaquetoken` configuration is named after the **AS-lookup verification strategy**, not forcing the token to be a non-JWT random string. If you choose introspection for a JWT, the RS trusts the AS's response instead of relying solely on offline verification in `JwtDecoder`.

### 2.2. Who Participates?

| Component | Function |
| --- | --- |
| Client | Obtains an access token via the appropriate grant and sends it in `Authorization: Bearer` to the RS |
| Authorization Server (AS) | Issues tokens, maintains active/revoked/expired policy, exposes the introspection endpoint to authorized parties |
| Resource Server (RS) | Authenticates Bearer tokens and enforces authorization on its API |
| Introspection client | The identity/credentials the RS uses to call the AS introspection endpoint; **distinct from** the Bearer token presented by the caller |
| Spring Security | Reads the Bearer header, calls the introspector, creates `Authentication`, and enforces permissions per application policy |

```text
Client                    API / Resource Server                      Authorization Server
  |                              |                                           |
  | GET /api/messages            |                                           |
  | Authorization: Bearer T      |                                           |
  |----------------------------->|                                           |
  |                              | POST /introspect                          |
  |                              | Basic <RS client credentials>            |
  |                              | form token=T                              |
  |                              |------------------------------------------>|
  |                              |             {active:true,scope:...,sub:...}|
  |                              |<------------------------------------------|
  |                              | Create Authentication, check permissions  |
  |<-----------------------------| 200 / 401 / 403 depending on outcome      |
```

The API's client **does not** need to know the introspection client secret. The RS must never send this client secret to browsers/mobile apps. An invalid token request must not automatically retry against a different introspection endpoint or skip validation.

## 3. RFC 7662: Request, Response, and Semantics

### 3.1. Introspection Request

The RS calls an HTTPS endpoint provided by the AS. RFC 7662 uses `application/x-www-form-urlencoded`, typically via `POST`:

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.org
Authorization: Basic <base64-of-introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<bearer-token-presented-to-api>&token_type_hint=access_token
```

This sample contains **two distinct sets of credentials**:

- `Authorization: Basic ...`: the RS proves to the AS that it is authorized to introspect tokens. The AS may use another client authentication method per configuration.
- `token=...`: the access token sent by the external client to the RS to be verified. The token must never go into URL query strings or logs.
- `token_type_hint=access_token`: optional hint for the AS; does not turn the submitted value into an access token and does not replace AS checks.

Never send `client-secret` over unencrypted HTTP. Never reuse the caller-supplied token as the RS's authentication credential to the introspection endpoint unless the AS explicitly mandates a controlled authorization model for it.

### 3.2. Response When the Token Is Active

An illustrative response:

```json
{
  "active": true,
  "scope": "messages:read messages:write",
  "client_id": "web-client",
  "sub": "user-42",
  "username": "alice",
  "token_type": "Bearer",
  "exp": 1900000000,
  "iat": 1899990000,
  "aud": "messages-api",
  "iss": "https://auth.example.org"
}
```

This is **illustrative** data. `exp`/`iat` are Unix timestamps (seconds since epoch); actual values are decided by the AS, and the AS is not required to return every attribute shown above. Key claims:

| Attribute | Role | What to Avoid |
| --- | --- | --- |
| `active` | **Mandatory** boolean per RFC 7662, indicating whether the AS considers the token active in this query context | Do not infer that the token has access to every resource |
| `scope` | Space-separated list of scopes | Do not automatically map to business roles outside policy |
| `client_id` | OAuth client that was issued the token | Do not confuse with the introspection client's `client_id` |
| `sub` | Subject if the token is tied to a user or principal | Do not assume it is an email/username; client credentials grants may differ |
| `username` | Human-readable name if provided by the AS | Do not treat as a unique identifier across tenants/issuers |
| `aud` | Intended target for token usage, if provided by the AS | Must define the API's audience policy |
| `iss` | Issuer, if provided by the AS | Must match the trusted issuer per trust contract |
| `exp`, `iat`, `nbf` | Expiration, issued-at, not-before (when present) | Do not confuse epoch seconds with milliseconds |
| `token_type` | Token type | Do not infer token type from length or characters |
| `jti` | Token identifier when present | No need to log the full token for correlation |

The AS may intentionally return only a minimal set of fields to a given RS for privacy. The RS must not assume `email`, `groups`, `roles`, or `aud` are always present. If policy requires a claim that the AS does not return, the right choice is to **fail closed** or adjust the AS/RS contract rather than guessing.

### 3.3. Inactive Token or Not Permitted to Disclose

Standard response:

```json
{
  "active": false
}
```

The AS may return this when the token is expired, revoked, nonexistent, or the RS **is not allowed to inspect** that token. The RS should not expose detailed distinctions between these causes in responses to the caller, as that can enable token probing.

Crucial point: **HTTP 200 with `{"active":false}` is a valid introspection response**, not a protocol error. The introspector must reject authentication; never see status 200 and allow the request.

### 3.4. Errors Calling the Introspection Endpoint

An RS with misconfigured introspection client credentials may receive:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="..."
```

This is an **HTTP 401 from the AS to the RS**, not the HTTP 401 returned by the API to the Bearer token caller. If the AS times out or returns 5xx, the RS does not know whether the token is active. The safe policy is **never assume the token is active**; depending on availability design, return 503/5xx with controlled error handling. Never mask network errors by returning a default privileged `OAuth2AuthenticatedPrincipal`.

**Distinguishing three outcomes:**

1. Introspection HTTP 200, `active=true`, valid metadata → can create authentication, then still enforce authorization.
2. Introspection HTTP 200, `active=false` → authentication rejected (typically API 401).
3. Introspection endpoint 401/403/5xx/timeout/malformed response → communication, client-auth, or AS-contract failure; fail closed, log safely, and monitor operationally without allowing access.

## 4. Spring Security Servlet: What Does OpaqueTokenAuthenticationProvider Do?

In Spring Security Servlet, the Bearer token authentication layer typically follows this chain:

```text
HTTP Servlet request
   |
   v
BearerTokenAuthenticationFilter
   |  BearerTokenResolver extracts token from Authorization header
   v
BearerTokenAuthenticationToken (untrusted authentication request)
   |
   v
AuthenticationManager / ProviderManager
   |
   v
OpaqueTokenAuthenticationProvider
   |  supports(BearerTokenAuthenticationToken)
   |  calls introspector.introspect(rawToken)
   v
OpaqueTokenIntrospector
   |  HTTPS to AS introspection
   |  validates response per RFC 7662 contract
   v
OAuth2AuthenticatedPrincipal + attributes/authorities
   |
   v
OpaqueTokenAuthenticationConverter (default or custom)
   |
   v
BearerTokenAuthentication (authenticated)
   |
   v
SecurityContextHolder of Servlet request
   |
   v
authorizeHttpRequests / method security / controller
```

`OpaqueTokenAuthenticationProvider` is an `AuthenticationProvider` in package:

```java
org.springframework.security.oauth2.server.resource.authentication
    .OpaqueTokenAuthenticationProvider
```

It accepts an `OpaqueTokenIntrospector` and uses the introspection result to build an `Authentication`. Under standard configuration, you **do not need to instantiate the provider yourself**: `oauth2ResourceServer(...opaqueToken(...))` makes Spring Security wire the filter, manager, provider, introspector, and converter.

Separated responsibilities:

- **BearerTokenAuthenticationFilter:** extracts the Bearer credential from the request; sets `SecurityContext` on successful authentication.
- **ProviderManager:** selects a provider supporting the authentication request type.
- **OpaqueTokenAuthenticationProvider:** authenticates the token via the introspector and converts principal/attributes into an authentication.
- **OpaqueTokenIntrospector:** interface `introspect(String token)`; implementations can call the AS, cache, check audience, and map authorities.
- **OpaqueTokenAuthenticationConverter:** converts the introspection result into an authentication token. Never mark all results as authenticated without verification.
- **Authorization layer:** compares scopes/roles/attributes against resource permissions, completely separate from determining whether the token is active.

The public provider API also exposes `supports(Class<?>)`, `authenticate(Authentication)`, and `setAuthenticationConverter(...)`. The Spring Security 6.x line supports this structure; minor differences in extra authorities or builders across versions do not change the rule: **introspection first, authorization second**.

### Note on the Name "Opaque"

The name `OpaqueTokenAuthenticationProvider` does **not** mean the provider decodes tokens itself or runs a validation algorithm on opaque strings. It **delegates to the introspector**. The AS reporting the token as active is the primary verification signal; scopes/claims are passed forward to authorization.

## 5. Mapping Introspection Responses to Authentication and Authorities

Suppose the AS returns:

```json
{
  "active": true,
  "sub": "alice-id-42",
  "scope": "messages:read messages:write",
  "client_id": "reader-client"
}
```

With default configuration, Spring Security converts scopes into `GrantedAuthority` instances prefixed with `SCOPE_`:

```text
messages:read  -> SCOPE_messages:read
messages:write -> SCOPE_messages:write
```

Thus an endpoint requiring `hasAuthority("SCOPE_messages:read")` should not be written as `hasAuthority("messages:read")`, unless a custom converter was explicitly configured to omit the prefix.

Post-authentication details can be accessed via:

- `BearerTokenAuthentication`: an `Authentication` implementation for verified Bearer tokens; `getTokenAttributes()` provides introspection claims.
- `OAuth2AuthenticatedPrincipal`: principal holding `getName()`, `getAttributes()`, and `getAuthorities()`; injectable with `@AuthenticationPrincipal`.
- `Authentication#getName()`: usually mapped from `sub` if returned by the AS. Not guaranteed to be an email or display name.
- `SecurityContextHolder`: holds the authentication on a Servlet request; WebFlux uses the reactive context instead.

Servlet controller example, **snippet** inside a `@RestController`:

```java
@GetMapping("/api/subject")
String subject(@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return principal.getAttribute("sub") == null
            ? "subject-not-provided"
            : String.valueOf(principal.getAttribute("sub"));
}
```

This only illustrates reading an attribute from the principal; `sub` might be absent if the AS does not return it, in which case security policy must decide whether to accept the token. Never use `username`/email not guaranteed unique by the AS to grant user object ownership.

**Authentication does not equal authorization.** An introspection response with `active=true` and scope `profile:read` must not unlock `/api/admin/delete`. Business roles such as `ROLE_ADMIN`, resource ownership, and tenant boundaries must come from trusted data and be checked in the right place.

## 6. Configuring a Spring Boot Resource Server with Introspection

### 6.1. Dependencies

In a **Spring Boot 3.x Java 17+ project configured with the Spring Boot plugin/Dependency Management**, using Gradle Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

`spring-boot-starter-web` selects the **Servlet** stack; WebFlux in section 9 has an alternative dependency. Do not include both starters in the same app just to test code, as Spring Boot chooses the web application type via auto-configuration rules.

### 6.2. application.yml

Save to `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: "${INTROSPECTION_URI}"
          client-id: "${INTROSPECTION_CLIENT_ID}"
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

Use real environment variables for the URI/client ID/secret. Typical provider URI example: `https://auth.example.org/oauth2/introspect`. **Never** commit real client secrets or access tokens to the repository. The URI must be HTTPS with verified certificate/hostname; use network policy so the RS calls only permitted endpoints.

These three `spring.security.oauth2.resourceserver.opaquetoken.*` properties are standard Spring Boot configuration. They configure the Resource Server itself, **distinct from** `spring.security.oauth2.client.registration.*` used when the app acts as an OAuth client/`oauth2Login()`.

### 6.3. Complete Java Class in Spring Boot Servlet

Place file `src/main/java/example/opaque/OpaqueResourceServerApplication.java`:

```java
package example.opaque;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OpaqueResourceServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueResourceServerApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/messages")
                        .hasAuthority("SCOPE_messages:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .opaqueToken(Customizer.withDefaults()))
                .build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/api/me")
        Map<String, Object> me(BearerTokenAuthentication authentication) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("name", authentication.getName());
            result.put("authorities", authentication.getAuthorities()
                    .stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList());
            return result;
        }

        @GetMapping("/api/messages")
        String messages() {
            return "You may read messages";
        }
    }
}
```

**Characteristics of this example:**

- Includes `main`, `@SpringBootApplication`, and controller; compiles when the project has the dependencies listed above and JDK 17+.
- `HttpSecurity` builds a Servlet `SecurityFilterChain`. `oauth2ResourceServer(...opaqueToken(...))` uses the introspector Boot creates from `application.yml`.
- `/api/me` requires authentication; `/api/messages` additionally requires `SCOPE_messages:read`.
- No login form, session login, or token issuance is configured. Callers must present an access token issued by a **real AS**.
- The controller does not return raw tokens, client secrets, or all introspection claims. This minimizes data exposure in the lesson.
- In a stateless API, bearer authentication is established per request; calling `POST /logout` on the API does not automatically invalidate the opaque token at the AS.

Run with the project's Gradle wrapper:

```bash
./gradlew bootRun
```

Windows: `gradlew.bat bootRun`. The application starts cleanly only with appropriate dependencies, configuration, and environment; authentication outcomes can only be verified against a real AS/introspection endpoint.

### 6.4. Testing the API with curl

POSIX shell example with a valid `ACCESS_TOKEN` obtained from the AS:

```bash
curl -i http://localhost:8080/api/me

curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/me

curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/messages
```

Expected behavior under standard configuration:

| Request | Observed Outcome |
| --- | --- |
| Missing Bearer token | Typically HTTP **401 Unauthorized**; with `WWW-Authenticate: Bearer` |
| Active token, valid metadata | `/api/me` returns 200 with principal name/authorities |
| Active token lacking `messages:read` | `/api/messages` returns **403 Forbidden** |
| Active token with `messages:read` scope | `/api/messages` returns 200, body `You may read messages` |
| Inactive/invalid token | Typically HTTP **401 Unauthorized** |
| AS introspection timeout/5xx | Token must not be treated as valid; HTTP status depends on error handling, monitor and enforce fail-closed policy |

If calling from a browser tool or Postman, always protect the token. Never paste real tokens into issue trackers, log screenshots, URL query strings, or public pastes.

## 7. Constructing OpaqueTokenAuthenticationProvider Directly to Understand Mechanics

In real applications, prefer the DSL from section 6. When learning or unit-testing the provider, however, you can create a mock `OpaqueTokenIntrospector` to verify how the provider turns a Bearer credential into an `Authentication`.

**Note:** the mock introspector below is for tests only. It **does not call an AS**, and therefore must never be copied into production to accept tokens via string comparison.

File `src/test/java/example/opaque/OpaqueTokenProviderTest.java`; add JUnit dependencies via `spring-boot-starter-test`:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Java test:

```java
package example.opaque;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.junit.jupiter.api.Assertions.*;

class OpaqueTokenProviderTest {

    @Test
    void convertsIntrospectionPrincipalToBearerAuthentication() {
        OpaqueTokenIntrospector fakeIntrospector = token -> {
            assertEquals("test-opaque-token", token);

            return new DefaultOAuth2AuthenticatedPrincipal(
                    "alice",
                    Map.of(
                            "sub", "alice",
                            "scope", List.of("messages:read")),
                    List.of(
                            new SimpleGrantedAuthority(
                                    "SCOPE_messages:read")));
        };

        OpaqueTokenAuthenticationProvider provider =
                new OpaqueTokenAuthenticationProvider(fakeIntrospector);

        Authentication result = provider.authenticate(
                new BearerTokenAuthenticationToken("test-opaque-token"));

        assertNotNull(result);
        assertInstanceOf(BearerTokenAuthentication.class, result);
        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        assertTrue(result.getAuthorities().stream()
                .anyMatch(authority -> authority.getAuthority()
                        .equals("SCOPE_messages:read")));
    }
}
```

With JDK 17 and a Gradle project configured with test dependencies, run:

```bash
./gradlew test
```

Goal: one test **PASSES** when the fake introspector returns `OAuth2AuthenticatedPrincipal` for the controlled token. Verifying the provider/converter **does not prove** RFC 7662 HTTP exchange works, does not verify RS client authentication at the AS, and does not validate a real token's lifetime. Add separate integration tests with an AS or mock HTTP server.

**Should you instantiate `ProviderManager` manually?** Usually no. The Spring Security DSL registers the appropriate manager/provider automatically. Manually creating filters/providers can accidentally bypass the token resolver, exception translation, SecurityContext setup, and request matchers.

## 8. Turning Claims into Business Permissions: Mappers and Audience Validation

`active=true` answers "Does the AS consider the token active in this query context?" It is **not enough** for an RS to allow every request. At minimum, verify the token's resource/audience and endpoint-appropriate permissions.

### 8.1. Use Only AS-Verified Scopes

If the response has `scope="messages:read"`, Spring grants authority `SCOPE_messages:read` by default. When mapping organization claims into custom authorities, place that logic in an `OpaqueTokenIntrospector` wrapper or `OpaqueTokenAuthenticationConverter` matching your Spring version's API.

Example **snippet in a Java 17 configuration class**, mapping without broadening permissions:

```java
@Bean
OpaqueTokenIntrospector validatingIntrospector(
        @Value("${app.security.expected-audience}") String expectedAudience,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
        String uri,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
        String clientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
        String clientSecret) {

    OpaqueTokenIntrospector delegate =
            new SpringOpaqueTokenIntrospector(uri, clientId, clientSecret);

    return token -> {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
        Object audiences = principal.getAttribute("aud");

        boolean allowed = expectedAudience.equals(audiences);
        if (audiences instanceof java.util.Collection<?> values) {
            allowed = values.contains(expectedAudience);
        }

        if (!allowed) {
            throw new BadOpaqueTokenException("Token audience rejected");
        }

        return principal;
    };
}
```

The code above is a **snippet to place in `@Configuration` with imports `@Bean`, `@Value`, `OpaqueTokenIntrospector`, `SpringOpaqueTokenIntrospector`, `OAuth2AuthenticatedPrincipal`, `BadOpaqueTokenException`**. It illustrates failing closed on `aud`; use only when the AS guarantees returning `aud` by contract. In newer versions, the three-argument constructor of `SpringOpaqueTokenIntrospector` may be deprecated; replace it with the builder recommended by your version's docs. If the AS does not return `aud`, this wrapper will **reject all tokens**, and you must fix the AS/RS contract rather than allowing everything.

For multi-AS/multi-tenant apps, restrict expected issuer and audience via routing/trust policies. Never read `expectedAudience` from request headers or query parameters supplied arbitrarily by the client.

### 8.2. Roles and Ownership Are a Different Level from Scopes

A token with `scope=orders:read` only proves the application is authorized to read that resource category per AS policy. If the API receives `GET /orders/123`, it must also verify resource 123 belongs to a tenant/owner the principal is allowed to view.

Service example:

```java
// Illustrative snippet: repository returns Optional<Order>.
Order order = repository.findById(orderId)
        .orElseThrow(NotFoundException::new);

if (!order.tenantId().equals(currentTenantId)) {
    throw new AccessDeniedException("Forbidden");
}
return order;
```

This is not a runnable file (`repository`, `Order`, and exception types are hypothetical domain types); it highlights data-level authorization. Never work around it by granting `ROLE_ADMIN` simply because introspection returned `active=true`.

### 8.3. Avoid Confusing Subject Identifiers

`sub` is the AS-defined subject; `client_id` is the OAuth client that received the token; `username`/`email` (if present) are usually for display or conditional business logic. Client credentials grants may not correspond to any end user. Never treat `client_id` or email as "the logged-in human user" in every model.

## 9. Reactive WebFlux: OpaqueTokenReactiveAuthenticationManager

WebFlux does not run Servlet's `BearerTokenAuthenticationFilter`. In the Reactive stack, Spring Security processes credentials via WebFilters and `ReactiveAuthenticationManager`, typically using:

- `OpaqueTokenReactiveAuthenticationManager`, instead of Servlet `OpaqueTokenAuthenticationProvider`.
- `ReactiveOpaqueTokenIntrospector`, with method `Mono<OAuth2AuthenticatedPrincipal> introspect(String token)`.
- `SpringReactiveOpaqueTokenIntrospector` working over non-blocking WebClient, or a verified custom reactive implementation.
- `ReactiveSecurityContextHolder`/Reactor Context instead of thread-local `SecurityContextHolder` to read authentication in reactive services.

High-level pipeline:

```text
WebFlux ServerWebExchange
    |
    v
SecurityWebFilterChain -> authentication WebFilter
    |
    v
BearerTokenAuthenticationToken
    |
    v
OpaqueTokenReactiveAuthenticationManager
    |
    v
ReactiveOpaqueTokenIntrospector.introspect(token)
    |
    v
Mono<OAuth2AuthenticatedPrincipal> + authorities
    |
    v
Mono<Authentication> -> Reactor SecurityContext
    |
    v
authorizeExchange -> Handler returns Mono/Flux
```

### 9.1. Gradle and YAML

In a WebFlux application, use:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

The `spring.security.oauth2.resourceserver.opaquetoken.*` properties from section 6 can be used similarly. Boot provides the reactive introspector when configured as a WebFlux/Reactive Resource Server.

### 9.2. Java 17 WebFlux Security Chain

This is a **configuration file** for a WebFlux app that already has `@SpringBootApplication`, named `src/main/java/example/opaque/ReactiveOpaqueSecurityConfig.java`:

```java
package example.opaque;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOpaqueSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/messages")
                        .hasAuthority("SCOPE_messages:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

A reactive controller can accept the framework-injected `BearerTokenAuthentication` and return a publisher:

```java
// Snippet inside a @RestController of a WebFlux application.
@GetMapping("/api/me")
Mono<String> me(BearerTokenAuthentication authentication) {
    return Mono.just(authentication.getName());
}
```

In reactive services outside the HTTP boundary, read context like this:

```java
Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
```

These two short pieces are **snippets** requiring proper Reactor and Spring Security imports, not standalone programs. Never call `.block()` or `.subscribe()` manually just to extract the principal, and never switch to `ThreadLocal` after choosing WebFlux.

### 9.3. Introspection Performance in Reactive

`ReactiveOpaqueTokenIntrospector` must use genuinely non-blocking APIs. If you wrap a blocking HTTP client inside `Mono.just(blockingCall())`, the call still executes eagerly on the current thread, potentially blocking the Netty event loop. For unavoidable legacy blocking calls, isolate them on `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` as a transitional measure and monitor timeouts/concurrency. In new applications, prefer `SpringReactiveOpaqueTokenIntrospector`.

WebFlux's non-blocking I/O **does not make the introspection endpoint faster**; every request still incurs network latency, timeouts, and AS load. Evaluate caching and near-real-time revocation needs in section 11.

## 10. Comparing Introspection with Offline JWT Validation

| Criterion | Opaque token / introspection | JWT offline signature validation |
| --- | --- | --- |
| Does RS understand token structure? | No need, just forwards to AS | Can read signed claims per JWT/JWS |
| Source of truth for active token | AS via introspection endpoint | Usually signature, issuer, audience, time claims at RS |
| Near-instant revocation | Visible on next introspection, barring cache/AS propagation | Requires denylist/introspection/short-lived token or extra mechanism |
| Per-request AS dependency | Typically yes, unless cached | Typically no, except during JWKS refresh |
| Network latency | Adds round trip to AS | Low, no per-request AS call |
| Scalability | Must size AS capacity/cache/timeouts | Offloads AS, incurs key/policy management overhead |
| Effective metadata | AS controls which claims are disclosed | Claims sit inside token, visible to client |
| Primary risks | AS outage, stale cache, introspection credentials | Unexpired token stays usable after revocation if RS is unaware |

**Token shape does not dictate validation strategy.** A JWT can still be sent to an introspection endpoint. When configured that way, `OpaqueTokenAuthenticationProvider` no longer "attempts to decode" the JWT; the AS returns status and attributes. The security policy depends on how AS and RS coordinate.

Regarding caching: with uncached introspection, token status changes at the AS can take effect on the next API request. Yet if the AS has replication lag, the RS caches positive responses, or a gateway caches, actual rejection timing depends on TTL and invalidation mechanisms. Never claim "instant revocation" solely because introspection is used.

## 11. Designing Timeouts, Caching, Revocation, and Reliability

### 11.1. Timeouts Are Both a Security and Latency Concern

Every inbound HTTP request may trigger an outbound introspection HTTP call. If the AS slows down, API latency rises and thread/connection resources can exhaust.

- Set connection timeouts, response timeouts, and overall deadlines within the API's latency budget.
- Bound concurrency, connection pool size, request queues, and retries; an AS slowdown must not cause unbounded RS resource growth.
- Never retry all errors in a way that amplifies load during an AS outage; consider backoff/jitter and a circuit breaker that fails closed.
- Log request correlation and introspection status/latency/timeouts, **never raw tokens** or Authorization headers.
- Enable TLS hostname verification and proper truststore/CA validation. Never configure "trust all certificates" just to make tests pass.

Spring Security supports swapping the introspector/HTTP client to tune timeouts; exact configuration depends on version and whether `RestClient`, `RestTemplate`, or `WebClient` is used. To customize timeouts, consult the docs for `SpringOpaqueTokenIntrospector` / `RestClientOpaqueTokenIntrospector` or `SpringReactiveOpaqueTokenIntrospector` for your dependency version rather than assuming a single universal YAML property.

### 11.2. Caching Introspection Results

Positive caching is an optimization with a trade-off: the RS avoids calling the AS on every request, yet **revoked tokens may continue being accepted while the cache entry remains valid**. A strategy must decide:

- Cache keys must not expose raw tokens in logs/metrics; restrict memory access and avoid leaking tokens in key generation. Use a keyed digest if the cache is shared.
- Positive TTL ≤ token expiration and ≤ product-accepted revocation latency window; never cache forever.
- Cache negative responses only if needed, with a very short TTL and token-guessing protections. Never cache 5xx/timeout errors as active.
- Avoid stampedes: concurrent cache misses for the same token can flood the AS; use request coalescing/single-flight when appropriate.
- Never assume the introspector cache automatically learns when a token is revoked; early invalidation requires events/invalidation or shorter TTLs.

Per RFC 7662, an RS **may** cache introspection responses per policy; weigh token sensitivity, revocation requirements, and privacy. Enforce TTL limits consistently wherever post-auth metadata is used.

### 11.3. Fail Closed When the AS Does Not Respond

Timeouts, DNS errors, TLS trust failures, or AS 5xx responses do not prove a token is inactive, nor do they **prove the token is active**. Never use a fallback like:

```java
// WRONG: absolutely never use in production.
return new DefaultOAuth2AuthenticatedPrincipal(
        "guest", Map.of("active", true),
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
```

This is an **anti-pattern snippet** (not a runnable file). Any "allow by default" path when authentication fails can break security. For architectures requiring high availability, explicitly design policies for caching previously verified results with bounded TTLs, appropriate API targets, and auditing; never use AS failures to escalate privileges.

### 11.4. Revocation and Active State

The AS can mark a token revoked per RFC 7009. The RS will learn on the next successful introspection if the AS has updated its state and caches do not serve stale responses. However, revoking a refresh token and revoking an access token are distinct actions; a local browser logout also does not automatically revoke a Bearer token issued for an API.

If a requirement demands "instant logout across all APIs," the design must span access token lifetimes, revocation propagation, cache TTLs, client sessions, AS policies, and RS enforcement. `OpaqueTokenAuthenticationProvider` only authenticates at request time based on what the introspector returns.

## 12. 401 and 403 Errors: Distinguishing Root Causes

A REST API using introspection should behave consistently:

| State | Handling Layer | Expected Behavior |
| --- | --- | --- |
| Missing Bearer header | Resource Server authentication entry point | 401 |
| Malformed Bearer header | Token resolver/filter | 400 or 401 depending on case and RFC 6750 |
| Token active=false | Introspector/AuthenticationProvider | 401 |
| Token active=true, missing required scope | Authorization filter | 403 |
| Token active=true, wrong audience | Custom fail-closed validation | 401 or corresponding error mapping |
| AS returns 401 to RS introspection client | AS-RS config/connectivity failure | RS blocks access, safely logs credentials issue |
| AS timeout/5xx | Dependency failure | Fail closed; 5xx/503 may be appropriate after error handling |
| AS returns invalid JSON or omits `active` | Introspection protocol validation | Reject/throw; never default to active |

Specific HTTP codes during AS failures depend on exception translation and custom handlers; do not hardcode 401 for every outage if that hides operational failures. When a Bearer token is valid yet lacks scope, the standard Bearer challenge may include `insufficient_scope`; never expose sensitive claims.

### 12.1. Why Does an "Active" Token Still Receive 403?

Flow:

```text
AS: active = true; scope = "profile:read"
             |
             v
Spring: authenticated=true; authorities=[SCOPE_profile:read]
             |
             v
Rule: /api/messages needs SCOPE_messages:read
             |
             v
HTTP 403
```

Do not "fix" this by changing `hasAuthority` to `authenticated()` just to get a 200. That removes scope-based authorization rather than fixing token validation.

### 12.2. Why Does the RS Return 401 Even Though the AS Returned HTTP 200?

Because the AS body is `{"active":false}`. RFC 7662 intentionally uses HTTP 200 to return a valid query result about **an invalid token**. The RS must inspect the JSON `active` field, never just the HTTP status.

## 13. Testing at the Right Layer: Unit, Slice, and Integration

### 13.1. Provider/Introspector Unit Tests

Test `OpaqueTokenAuthenticationProvider` with the stub introspector from section 7 to verify authentication type and authorities. Add stub tests signaling inactive tokens, asserting no authenticated principal is created, and tests for custom mappers/audience rejection.

### 13.2. Spring MVC Security Tests

You can use `spring-security-test` with `MockMvc` to verify authorization rules. For example, `SecurityMockMvcRequestPostProcessors.opaqueToken()` injects an authentication fixture into the test request:

```java
// Snippet inside a test with MockMvc and appropriate static imports.
mockMvc.perform(get("/api/messages")
                .with(opaqueToken().authorities(
                        new SimpleGrantedAuthority(
                                "SCOPE_messages:read"))))
        .andExpect(status().isOk());
```

**Note:** `opaqueToken()` in Spring Security Test typically **bypasses actual HTTP introspection** to simulate authentication; this test verifies application rules, **not that AS client credentials/URI or RFC 7662 responses are handled properly**.

### 13.3. Integration Tests with a Mock AS or Real Test AS

For end-to-end verification, stand up a test introspection HTTP endpoint or use a configured AS to test:

1. RS sends POST with the right URI, `token` form field, and auth credentials to the AS.
2. `active=true` with matching scope → authenticated and 200 on permitted endpoint.
3. `active=true` missing scope → 403 on protected endpoint.
4. `active=false` → 401, no principal granted permissions.
5. AS 401 due to wrong client secret → RS fails closed and records operational error.
6. AS timeout/TLS failure/invalid JSON → request rejected; no unbounded retries.
7. Wrong audience or wrong tenant → rejected even when `active=true`.
8. Token revoked at AS, requests before/after revocation and before/after cache TTL to measure effective latency.
9. Concurrent requests and multiple tokens to measure introspection calls, AS load, and ensure no principal mix-up.

You can use WireMock, MockWebServer, or a scoped mock HTTP server strictly in tests. Avoid mocking both the authentication provider and introspection at once and concluding the protocol has been tested.

### 13.4. Testing WebFlux

In WebFlux, use `WebTestClient` + `spring-security-test` reactive support for authorization unit tests. To test real introspection, mock the HTTP endpoint and keep `SpringReactiveOpaqueTokenIntrospector` in the test pipeline. Test two concurrent requests with two different Bearer tokens to verify principals do not leak into `ThreadLocal` or mix across Reactor contexts.

## 14. Standalone Java 17 Exercise: Post-Introspection Decision Model

The following example **does not replace a real introspector**; it models the simple decision step so you can see `active`, `aud`, `exp`, and scopes acting independently. No Spring Security dependencies; compiles with JDK 17+. Save as `IntrospectionDecisionDemo.java`:

```java
import java.util.Set;

public class IntrospectionDecisionDemo {

    record Claims(boolean active, long exp, String audience,
                  Set<String> scopes) {}

    static boolean canReadMessages(Claims claims, long nowEpochSeconds) {
        return claims.active()
                && claims.exp() > nowEpochSeconds
                && "messages-api".equals(claims.audience())
                && claims.scopes().contains("messages:read");
    }

    public static void main(String[] args) {
        long now = 1000L;

        Claims allowed = new Claims(
                true, 1200L, "messages-api", Set.of("messages:read"));
        Claims revoked = new Claims(
                false, 1200L, "messages-api", Set.of("messages:read"));
        Claims wrongAudience = new Claims(
                true, 1200L, "other-api", Set.of("messages:read"));
        Claims expired = new Claims(
                true, 900L, "messages-api", Set.of("messages:read"));
        Claims missingScope = new Claims(
                true, 1200L, "messages-api", Set.of("profile:read"));

        System.out.println("allowed: " + canReadMessages(allowed, now));
        System.out.println("revoked: " + canReadMessages(revoked, now));
        System.out.println("wrong audience: "
                + canReadMessages(wrongAudience, now));
        System.out.println("expired: " + canReadMessages(expired, now));
        System.out.println("missing scope: "
                + canReadMessages(missingScope, now));
    }
}
```

Compile and run:

```bash
javac IntrospectionDecisionDemo.java
java IntrospectionDecisionDemo
```

**Exact** expected stdout:

```text
allowed: true
revoked: false
wrong audience: false
expired: false
missing scope: false
```

The values `now=1000` and `exp=1200` are synthetic test data, not real token timestamps. In a real environment, the RS must rely on the introspector and designed policies rather than parsing an opaque token into `Claims` like this example. This exercise simply illustrates that **a valid token differs from an authorized request**.

## 15. Using curl to Distinguish the Introspection Server and Resource Server

This experiment assumes you have a test AS issuing real tokens and permission to call its introspection endpoint. Set environment variables for your shell; Bash example:

```bash
# These variables are supplied by the test environment; never put secrets in Git.
# INTROSPECTION_URI=https://auth.example.org/oauth2/introspect
# INTROSPECTION_CLIENT_ID=...
# INTROSPECTION_CLIENT_SECRET=...
# ACCESS_TOKEN=...

curl --silent --show-error \
  --request POST "$INTROSPECTION_URI" \
  --user "$INTROSPECTION_CLIENT_ID:$INTROSPECTION_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=$ACCESS_TOKEN" \
  --data-urlencode "token_type_hint=access_token"
```

With an RFC 7662-compliant AS and valid credentials, the reply may be `{"active":true,...}` or `{"active":false}`. There is no fixed JSON/stdout because token state is determined by the AS. If the command produces a TLS error, 401, or connection failure, that signal differs from `active:false`.

Next call the RS:

```bash
curl --silent --show-error --include \
  --header "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/messages
```

Comparison:

- AS reports `active=true` with `messages:read` and RS grants permission → expect 200.
- AS reports `active=true` without the scope → expect 403.
- AS reports `active=false` → expect 401.
- AS endpoint unreachable → RS must not allow the request through.

Never echo tokens or print commands containing secrets into CI logs. If your shell saves history, supply variables via a secret manager and test accounts; never record screens displaying raw tokens.

## 16. Troubleshooting by Technical Symptoms

### "InvalidBearerTokenException" or API Always Returns 401

Verify the Bearer token format, that the token belongs to the configured AS, and that the AS responds `active=true`. If the AS returns `active=false`, do not try to force the provider to return true; check whether the token expired, was revoked, belongs to another environment, or the RS lacks permission to introspect it.

### 401 from AS During Introspection

Check `client-id`/`client-secret` of the **RS introspection client**, Basic authentication config, TLS, endpoint permissions, secret rotation, and special-character encoding rules for your Spring Security version. From 6.5 to 7.x, guidance on credential encoding changed; prefer the builder/implementation recommended for your current version.

### Authenticated Yet Always 403

Inspect `GrantedAuthority` safely in a test environment; verify whether the AS `scope` was parsed into `SCOPE_messages:read`. If using a custom converter, check that it did not accidentally strip prefixes, change types, or drop authorities. Also check path matchers, roles, and tenant policies; never turn every endpoint into `authenticated()` to "fix" the error.

### Response Latency Spikes

Measure introspection HTTP call latency, DNS/TLS handshakes, connection pools, and thread saturation. Use a pooled client with timeouts, limit concurrency, review cache policy, and check AS scalability. In WebFlux, never run a blocking HTTP client on the event loop.

### Token Revoked Yet API Still Returns 200

Check whether the RS caches `active=true` introspection results and for what TTL, whether the AS actually marked the access token revoked, AS replication lag, and proxy layers. If the RS verifies JWTs offline locally, that configuration **is not using** the opaque introspection strategy covered here.

### Token `active=true` Yet Targets Wrong API

Check `aud` / resource indicators / issuer / tenant and AS policies. Never rely solely on `active=true` when tokens are used across multiple APIs. If the AS does not return audience, expand the contract or enforce an appropriate fail-closed policy.

### Returns 500 When AS Is Down, Wanted 401

That reflects the difference between "definitely invalid credential" and "dependency unable to determine state." Not all AS errors should be disguised as 401; configure intentional error handling that avoids leaking secrets while keeping outages observable, using documented HTTP status codes.

## 17. Production Readiness Checklist

1. **Trust boundary:** the RS trusts only the configured AS introspection endpoint; use HTTPS with hostname verification. Endpoint and secrets are server-managed.
2. **Token contract:** define issuer, audience/resource, scopes, client identity, subject/tenant, and required RS claims. Never guess when a claim is missing.
3. **Right stack enabled:** Servlet uses `OpaqueTokenAuthenticationProvider` via `HttpSecurity.oauth2ResourceServer().opaqueToken()`; WebFlux uses `OpaqueTokenReactiveAuthenticationManager` via `ServerHttpSecurity`.
4. **Authorization policy:** `active` is the authentication step; scopes/roles/resource ownership are still required. Never grant admin rights from untrusted data.
5. **Credential hygiene:** never log tokens/client secrets, never send tokens in query parameters, and do not expose introspection data unnecessarily.
6. **AS errors:** fail closed on timeouts, HTTP 401, 5xx, and invalid JSON; monitor and handle operational failures.
7. **Performance:** timeouts, connection pools, concurrency, cache TTL, and circuit breakers must align with latency/revocation SLAs.
8. **Revocation:** test real AS revocation and measure when the RS starts rejecting; if caching, publish the maximum acceptable latency.
9. **Testing:** separate provider/converter unit tests, authorization tests, RFC 7662 integration tests, invalid tokens, wrong audiences, AS outages, and concurrent traffic.
10. **Versions:** check javadocs for your Spring Security version before changing `SpringOpaqueTokenIntrospector` constructors/builders or custom converters; avoid copying 7.x code into 6.x unverified.

Key takeaway: **`OpaqueTokenAuthenticationProvider` does not decide token validity from the character string itself; it uses `OpaqueTokenIntrospector` to ask a trusted source, builds `Authentication`, and lets Spring Security and business logic enforce authorization.** A token with `active=true` is only the starting point of an access decision.

## 18. Official Documentation

- [Spring Security 6.5 — Servlet OAuth 2.0 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): configuration, provider, introspector, scope mapping, and customization.
- [Spring Security — OpaqueTokenAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenAuthenticationProvider.html): constructor, `authenticate`, `supports`, and converter.
- [Spring Security — OpaqueTokenReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html): reactive manager and `ReactiveOpaqueTokenIntrospector`.
- [Spring Security — WebFlux Opaque Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): reactive DSL, principal, authorities, and introspection.
- [Spring Security — Migrating OAuth2 to 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html): version migration changes, client credential encoding.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): request/response structure, `active`, and security considerations.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credential transport and error codes.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation model and relation to introspection.
- [Spring Boot OAuth2 Resource Server Properties](https://docs.spring.io/spring-boot/reference/web/spring-security.html): Boot-managed configuration and dependencies.
