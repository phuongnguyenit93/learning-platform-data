# Configuring introspection-uri, client-id, and client-secret

> **Module:** Spring Security - reactive. **Section:** Resource Server Opaque. This lesson guides configuring an OAuth 2.0 Opaque Token Resource Server using **Spring WebFlux, Spring Security 6.5.x, Spring Boot 3.x, Java 17+**. The focus is on the exact three properties `introspection-uri`, `client-id`, and `client-secret`, the RFC 7662 mechanism, Bearer authentication, scope authorities, error handling, secret security, and testing. The `example.test` domain and all credentials in examples are illustrative data only, not a live IdP.

## 1. Learning Outcomes

Learners should be able to:

1. Understand how opaque access tokens differ from JWTs: trusted claims cannot be extracted locally without verification.
2. Distinguish a Resource Server from an Authorization Server and an OAuth2 Client.
3. Correctly declare `spring.security.oauth2.resourceserver.opaquetoken.introspection-uri`, `client-id`, and `client-secret` via Spring Boot.
4. Explain the `application/x-www-form-urlencoded` POST flow to the Introspection Endpoint using introspection client credentials for authentication.
5. Explain `active:true`, `active:false`, and mapping scope `messages.read` to authority `SCOPE_messages.read`.
6. Protect a WebFlux API using `SecurityWebFilterChain`, `ServerHttpSecurity`, and `oauth2ResourceServer(...opaqueToken...)`.
7. Distinguish 401 from a missing/invalid Bearer token, 403 from a missing authority, and network/infrastructure errors when the IdP is unavailable.
8. Write WebFlux `WebTestClient` tests verifying 200/401/403 with a fake `ReactiveOpaqueTokenIntrospector`.
9. Write contract tests using the real `SpringReactiveOpaqueTokenIntrospector` and a local HTTP endpoint to verify the Basic header, form body, and `active` flag.
10. Apply a production checklist: HTTPS, secret manager, token revocation, timeouts, rate limiting, multi-tenancy, and fail-closed error handling.

**One sentence to remember:** The Resource Server receives the **caller's access token** in the `Authorization: Bearer` header, then uses the **Resource Server's own client ID/secret** to ask the **Authorization Server** whether the token is still active. The two types of credentials **must never be confused**.

## 2. Distinguishing Roles in OAuth 2.0

| Role | Responsibility | Input/Output |
| --- | --- | --- |
| Authorization Server / Identity Provider | Issues tokens, supports token introspection/revocation | Tokens, grants, token metadata |
| OAuth2 Client | Obtains access tokens via permitted flows and calls APIs | Outbound `Authorization: Bearer ...` |
| Resource Server | Verifies incoming Bearer tokens on the API, decides whether the user can call an endpoint | Inbound Bearer token, introspection response |
| API user / browser / machine caller | Sends requests to access data | Issued Bearer access token |

A WebFlux app can act simultaneously as an OAuth2 Client when calling downstream services and as a Resource Server when serving inbound APIs. However:

- `spring.security.oauth2.client.registration.*` configures an **OAuth2 Client requesting tokens**;
- `spring.security.oauth2.resourceserver.jwt.*` configures **JWT validation** on a Resource Server;
- `spring.security.oauth2.resourceserver.opaquetoken.*` configures **opaque token introspection** on a Resource Server.

Never use `client-secret` from `resourceserver.opaquetoken` to log users in, never send it to the frontend, and never treat it as an access token.

### 2.1 What Is an Opaque Access Token?

An opaque token is a credential that the Resource Server does not verify locally via readable characters/claims. Example:

```http
GET /api/messages HTTP/1.1
Host: api.example.test
Authorization: Bearer 6dab5a3b-demo-token
```

The string after `Bearer` may be a random reference issued by the IdP. The Resource Server does not know the user, client, expiry, or scopes from the token string alone. Rather than parsing and guessing permissions, it queries the **OAuth2 Token Introspection Endpoint** per RFC 7662.

Opaque **does not mean** it must be a short string: even a JWT can be verified via introspection if the architecture requires the IdP's online decision. What matters is the **verification method** being used, not "whether the string contains dots."

### 2.2 Compared to a JWT Resource Server

| Aspect | JWT Validation | Opaque Introspection |
| --- | --- | --- |
| Mechanism | Verifies signature, issuer/audience/expiry/claims | Sends token to IdP, accepts returned active/metadata |
| Need to contact IdP per request | Not necessarily once valid JWKS/keys are held | Typically makes an introspection request unless cached |
| Rapid token revocation | Depends on token lifetime/separate revocation policy | IdP can return `active:false` immediately upon revocation |
| Latency | Usually low for local verification | Depends on network/IdP |
| Common errors | Signature, kid, jwks, iss, aud, exp | Endpoint, Basic secret, TLS, timeout, active flag |
| Spring Boot config | `resourceserver.jwt.issuer-uri` | `resourceserver.opaquetoken.introspection-uri` + client credentials |

**There is no universal rule that JWT is always better or opaque is always safer.** Opaque introspection favors accurate active-status decisions at check time, but places the IdP on the Resource Server's authentication path.

## 3. The Three Exact Configuration Properties

Here is the **Spring Boot 3.x** configuration for Spring Security 6.5:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

`${INTROSPECTION_CLIENT_ID}` and `${INTROSPECTION_CLIENT_SECRET}` are placeholders injected at runtime from environment variables or a secrets manager. **You must replace the endpoint with the URI published by a real IdP** before running end-to-end. Never use the `example.test` domain as a production IdP.

| Property | Meaning | Typical Mistake |
| --- | --- | --- |
| `introspection-uri` | Full HTTPS URL of the token introspection endpoint | Confusing with token endpoint, login endpoint, JWKS, or issuer metadata |
| `client-id` | ID of the confidential client **permitted to introspect** at the IdP | Using an SPA/client ID by mistake or an unauthorized client |
| `client-secret` | Secret proving the identity of the introspection client | Missing injection, expired/rotated secret, leaked in logs or config |

### 3.1 Which Endpoint Is introspection-uri?

A few illustrative paths:

```text
https://idp.example.test/oauth2/introspect
https://idp.example.test/protocol/openid-connect/token/introspect
https://idp.example.test/oauth2/v1/introspect
```

Different IdPs use different paths. **Never guess the URL from the issuer** and do not confuse `introspection-uri` with:

- `authorization-uri`: where browsers are redirected for login/consent;
- `token-uri`: where an OAuth2 Client exchanges a code or requests an access token;
- `jwk-set-uri`: the public key set used to validate JWTs;
- `issuer-uri`: metadata/issuer used in corresponding validation;
- `userinfo-uri`: OIDC UserInfo endpoint;
- `/api/messages`: the Resource Server path you are protecting.

The introspection URI **must be configured from a trusted source**, never taken from unverified headers, query parameters, or tokens. If an attacker controls the URI, the app could send both the bearer token and introspection client credentials to the attacker's server (**SSRF/credential leakage**).

### 3.2 Which Identity Is client-id?

This is the ID of the **resource-server introspection client**, not the `client_id` inside a token issued to a mobile app, and not the user's `sub`. A company might have:

```text
mobile-app-client             -> OAuth2 Client requesting access tokens
backend-api-introspection     -> Confidential client authorized to introspect
alice                         -> Resource owner / subject
```

These three identities are distinct. The IdP must grant `backend-api-introspection` permission to query token status per policy. If you use an SPA's client ID lacking introspection permissions, calls to the IdP can fail even while the access token itself is active.

### 3.3 Where Is client-secret Used?

The secret is used by the Resource Server when sending an **introspection request** to the Authorization Server. With default Spring Security 6.5 configuration, HTTP Basic client authentication is common. It is not a bearer token placed on inbound API calls.

**Basic uses Base64, which is not secure encryption.** Use HTTPS/TLS with valid certificates, hostnames, and truststores. In real environments, store the secret in a secrets manager / Key Vault / Vault / Kubernetes Secret with access controls; never commit it to Git or print it in CI logs.

An example **solely showing how to inject environment variables into a demo process**:

```powershell
$env:INTROSPECTION_CLIENT_ID = "local-introspector"
$env:INTROSPECTION_CLIENT_SECRET = "<insert-from-secret-store>"
.\gradlew.bat bootRun
```

`<insert-from-secret-store>` is not an active password. In production, avoid typing real secrets in terminals with command history and avoid any form of hardcoding.

### 3.4 Client Authentication Methods Beyond Basic

RFC 7662 allows the introspection endpoint to require client authentication. Many IdPs support Basic client secrets, while others use mTLS, `private_key_jwt`, or IdP-specific mechanisms. The three Boot properties cover the common configuration; when an IdP requires another method, customize `ReactiveOpaqueTokenIntrospector`/the HTTP client to match the IdP contract and secure TLS.

Do not "fix" a Basic 401 by putting the client secret in the query string or returning the secret to the browser. The client secret belongs to the backend and must have least-privilege permissions.

## 4. Opaque Bearer Token Verification Flow

```text
API caller
   |
   | GET /api/messages
   | Authorization: Bearer <opaque-token>
   v
Spring Security WebFlux
   |
   | 1. Bearer authentication filter extracts token
   | 2. ReactiveOpaqueTokenIntrospector calls IdP
   v
Authorization Server
   |
   | HTTPS POST introspection-uri
   | Basic <client-id:client-secret>
   | Content-Type: application/x-www-form-urlencoded
   | token=<opaque-token>
   |
   +-- {"active":true,...} -> verified principal/authorities
   +-- {"active":false}    -> invalid token, authentication fails
   +-- timeout/5xx         -> unable to validate, do not grant access
   v
Spring Security authorization
   |
   +-- sufficient scope -> invoke controller -> 200 per business logic
   +-- missing scope    -> 403
   +-- missing/bad token -> 401
```

### 4.1 What Does the Outbound POST Introspection Look Like?

A conceptual HTTP exchange:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <REDACTED_CLIENT_AUTH>

token=<REDACTED_USER_ACCESS_TOKEN>
```

This is not a complete curl command. Form field `token` is sent to the IdP; the Basic header carries the **Resource Server's** credentials. `token_type_hint=access_token` is an optional hint that an IdP may support, not something you need to add manually when using Spring's defaults.

The Resource Server sends sensitive values **in both the header and body** of the outbound POST; disable verbose logging that could leak credentials.

### 4.2 What Does active:true Mean?

Example IdP response:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "messages.read profile.read",
  "client_id": "mobile-app",
  "token_type": "Bearer",
  "exp": 1893456000
}
```

Per Spring Security Opaque Token support:

- `active:true` indicates the IdP confirms the token is active under its policy.
- Spring constructs an `OAuth2AuthenticatedPrincipal` from the attributes and a `BearerTokenAuthentication` for the request.
- Scopes are mapped into authorities prefixed with `SCOPE_`:
  - `messages.read` -> `SCOPE_messages.read`;
  - `profile.read` -> `SCOPE_profile.read`.
- `Authentication#getName()` is typically populated from `sub` when returned by the IdP.
- After authentication, **authorization still checks** scopes and domain policies.

Never trust `sub` or `scope` taken from a **caller-supplied** JSON payload. Use only attributes confirmed by trusted introspection.

### 4.3 What Does active:false Mean?

```json
{
  "active": false
}
```

This is the standard response when a token does not exist, has expired, was revoked, or the introspection client is not allowed to query it. The Resource Server **grants no valid principal** and protected APIs typically return a 401 Bearer challenge.

The IdP may intentionally withhold specific reasons to reduce token-probing risk. Never echo the token or internal details in the error body.

### 4.4 Active:true Does Not Mean Access to Every API

A token with `scope="profile.read"` is still denied on an endpoint requiring `SCOPE_messages.read`. A token with `messages.read` is also not automatically allowed to read another tenant's messages. Authorization encompasses both **HTTP rules** and **business/resource ownership rules**.

## 5. Key Spring Security Types to Know

| Type | Layer Used | Responsibility |
| --- | --- | --- |
| `ServerHttpSecurity` | WebFlux security configuration | `authorizeExchange`, `oauth2ResourceServer` |
| `SecurityWebFilterChain` | Security WebFilter | Authenticates/authorizes requests |
| `ReactiveOpaqueTokenIntrospector` | Authentication pipeline | `Mono<OAuth2AuthenticatedPrincipal> introspect(String token)` |
| `SpringReactiveOpaqueTokenIntrospector` | HTTP introspection | Calls configured endpoint, checks active, and maps |
| `OAuth2AuthenticatedPrincipal` | Post-introspection | Claims/attributes and authorities |
| `BearerTokenAuthentication` | Reactive SecurityContext | Authentication representing the bearer caller |
| `ReactiveSecurityContextHolder` | Reactor | Propagates SecurityContext through the reactive chain |
| `ServerAuthenticationEntryPoint` | Authentication error | Handles 401/challenges |
| `ServerAccessDeniedHandler` | Authorization error | Handles 403 when user lacks permission |

**Avoid mixing Servlet APIs**: `HttpSecurity`, `SecurityFilterChain`, and synchronous `OpaqueTokenIntrospector` are Servlet-side types. In WebFlux, use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ReactiveOpaqueTokenIntrospector`.

### 5.1 How Does Boot Auto-Config Work?

When a project includes the OAuth2 Resource Server starter and defines the three properties:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

if **no custom `ReactiveOpaqueTokenIntrospector` bean exists**, Spring Boot creates the corresponding introspector. If **no custom `SecurityWebFilterChain` bean exists**, Boot adds a default chain protecting requests and enabling opaque tokens.

When you define your own `SecurityWebFilterChain`, **do not assume** it enables opaque support automatically unless you declare `oauth2ResourceServer(...opaqueToken...)`. In this lesson, we configure it explicitly for scope-based authorization.

**Dependency note:** `spring-boot-starter-oauth2-resource-server` provides the proper Resource Server dependencies. `spring-boot-starter-oauth2-client` does not replace it; the client starter is for apps requesting outbound tokens.

## 6. Java 17+ Spring Boot 3.x Project Following This Configuration

### 6.1 Dependencies

Create a Spring Initializr project (Java 17+, Spring Boot 3.x, Gradle Groovy), selecting Spring Reactive Web, Spring Security, and OAuth2 Resource Server. In `build.gradle` (already containing the Boot plugin/dependency management), add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add `spring-boot-starter-web` if you genuinely want to run **reactive WebFlux**; when both MVC and WebFlux are present, Boot typically selects MVC by default.

### 6.2 File Structure

```text
src/main/java/com/example/opaqueapi/
  OpaqueApiApplication.java
  OpaqueSecurityConfig.java
  MessageController.java
src/main/resources/
  application.yml
src/test/java/com/example/opaqueapi/
  OpaqueHttpTest.java
  IntrospectionContractTest.java
```

Each public class resides in a matching Java file under package `com.example.opaqueapi`; the code requires Spring dependencies and cannot be compiled with bare `javac`.

### 6.3 OpaqueApiApplication.java

`src/main/java/com/example/opaqueapi/OpaqueApiApplication.java`:

```java
package com.example.opaqueapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueApiApplication.class, args);
    }
}
```

### 6.4 application.yml

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

The `idp.example.test` domain is illustrative and **makes no real connection**. To run in staging, substitute your IdP endpoint and inject client ID/secret. The unit tests later supply a fake introspector so no IdP is needed.

### 6.5 OpaqueSecurityConfig.java

`src/main/java/com/example/opaqueapi/OpaqueSecurityConfig.java`:

```java
package com.example.opaqueapi;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class OpaqueSecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/messages")
                    .hasAuthority("SCOPE_messages.read")
                .pathMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
```

**Detailed explanation:**

- `@EnableWebFluxSecurity` enables the reactive security stack.
- `/public/health` is the demo health endpoint, explicitly marked public.
- `/api/messages` requires the **exact authority** `SCOPE_messages.read` from trusted introspection scopes; `messages.read` is not `ROLE_messages.read`.
- `/api/profile` only requires an authenticated bearer token; tighten the rule if tenant policy requires a specific scope.
- `anyExchange().denyAll()` is a safe default.
- `oauth2ResourceServer(...opaqueToken...)` enables Bearer token authentication using the introspector from auto-config or a bean.
- `Customizer.withDefaults()` does not mean "allow every token." Tokens are still introspected and must be valid.

### 6.6 MessageController.java

`src/main/java/com/example/opaqueapi/MessageController.java`:

```java
package com.example.opaqueapi;

import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class MessageController {

    public record MessageView(String owner, String text) {}
    public record ProfileView(String subject) {}

    @GetMapping(
        value = "/public/health",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping(
        value = "/api/messages",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<MessageView> messages(BearerTokenAuthentication auth) {
        return Mono.just(new MessageView(
            auth.getName(), "protected-example"
        ));
    }

    @GetMapping(
        value = "/api/profile",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ProfileView> profile(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(new ProfileView(principal.getName()));
    }
}
```

Once the opaque token is valid, `BearerTokenAuthentication`/`OAuth2AuthenticatedPrincipal` reflects the trusted identity from the IdP. The controller does not parse `Authorization` itself to extract username or scopes and **never returns raw bearer tokens or client secrets** to API callers.

**Sample for learning only:** The text `"protected-example"` is dummy data; when replacing it with real messages, add owner/tenant/resource access checks rather than relying solely on a coarse scope.

## 7. Testing WebFlux Authorization with a Fake Introspector

This is an application test decoupled from any IdP. It defines two mock tokens:

- `opaque-read`: user alice, `SCOPE_messages.read`.
- `opaque-profile`: user bob, `SCOPE_profile.read`.
- Every other token is rejected with `BadOpaqueTokenException`.

Use `WebTestClient.bindToApplicationContext(...)` and `springSecurity()` to exercise WebFlux security filters. This **does not directly test Basic auth / outbound POST introspection**; Section 8 tests that separately.

### 7.1 OpaqueHttpTest.java

`src/test/java/com/example/opaqueapi/OpaqueHttpTest.java`:

```java
package com.example.opaqueapi;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = {
        "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://unused.example.test/introspect",
        "spring.security.oauth2.resourceserver.opaquetoken.client-id=offline",
        "spring.security.oauth2.resourceserver.opaquetoken.client-secret=offline"
    }
)
@Import(OpaqueHttpTest.TestTokens.class)
class OpaqueHttpTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @TestConfiguration(proxyBeanMethods = false)
    static class TestTokens {
        @Bean
        @Primary
        ReactiveOpaqueTokenIntrospector testIntrospector() {
            return token -> {
                if ("opaque-read".equals(token)) {
                    return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                        "alice",
                        Map.of("sub", "alice", "scope", "messages.read"),
                        List.of(new SimpleGrantedAuthority(
                            "SCOPE_messages.read"))
                    ));
                }
                if ("opaque-profile".equals(token)) {
                    return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                        "bob",
                        Map.of("sub", "bob", "scope", "profile.read"),
                        List.of(new SimpleGrantedAuthority(
                            "SCOPE_profile.read"))
                    ));
                }
                return Mono.error(
                    new BadOpaqueTokenException("Inactive token"));
            };
        }
    }

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/public/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void missingBearerGets401() {
        client.get().uri("/api/messages")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void goodReadTokenGets200() {
        client.get().uri("/api/messages")
            .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-read")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice")
            .jsonPath("$.text").isEqualTo("protected-example");
    }

    @Test
    void activeTokenMissingScopeGets403() {
        client.get().uri("/api/messages")
            .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-profile")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void invalidBearerGets401() {
        client.get().uri("/api/messages")
            .header(HttpHeaders.AUTHORIZATION, "Bearer expired-token")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void profileAllowsAnyAuthenticatedToken() {
        client.get().uri("/api/profile")
            .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-profile")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("bob");
    }

    @Test
    void unmatchedRouteIsDenied() {
        client.get().uri("/api/admin")
            .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-read")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Run in the project:

```bash
./gradlew test --tests '*OpaqueHttpTest'
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*OpaqueHttpTest'
```

**These results are expected assertions, not output from an executed build.** The test does not call a real HTTPS IdP. It verifies the integration of **Bearer filter + fake introspector + authorization rules + controller**.

### 7.2 How Does mockOpaqueToken() Differ?

Spring Security Test supports:

```java
client.mutateWith(
    mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_messages.read"))
).get()
 .uri("/api/messages")
 .exchange()
 .expectStatus().isOk();
```

This is a test snippet requiring static import `mockOpaqueToken`, variable `client`, and `SimpleGrantedAuthority`. It injects a mock Authentication, **bypassing outbound introspection**, so it cannot prove the three properties are configured properly.

Sensible test layering:

| Test | Proves | Does Not Prove |
| --- | --- | --- |
| `mockOpaqueToken()` | Authorization rules recognize authorities/principal | Credentials/POST to IdP |
| Fake `ReactiveOpaqueTokenIntrospector` | Bearer header reaches introspector and handles 200/401/403 | Real HTTP Basic/introspection URI |
| Real `SpringReactiveOpaqueTokenIntrospector` + local stub | HTTP POST, Basic credentials, form token, active flag | Real TLS trust / IdP policy |
| E2E with IdP sandbox | Introspection client registration/permissions, TLS, scopes, revocation | Production scale/security by itself |

## 8. Testing Real HTTP Introspection Requests Against a Loopback Server

You do not need an external IdP to verify how `client-id`/`client-secret` are sent. Java 17 includes `com.sun.net.httpserver.HttpServer` (module `jdk.httpserver`). The test opens an ephemeral port on `127.0.0.1` and verifies:

- HTTP method: POST;
- `Authorization: Basic ...` header with demo client ID and secret;
- `Content-Type: application/x-www-form-urlencoded` header;
- Request body containing `token=opaque-good`;
- `active:true` response yields a principal, while `active:false` does not.

**Use HTTP loopback only in tests.** Production must use HTTPS; never send Basic credentials or access tokens over plain HTTP between machines.

### 8.1 IntrospectionContractTest.java

`src/test/java/com/example/opaqueapi/IntrospectionContractTest.java`:

```java
package com.example.opaqueapi;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicReference;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import reactor.test.StepVerifier;

class IntrospectionContractTest {

    private HttpServer server;
    private SpringReactiveOpaqueTokenIntrospector introspector;

    private final AtomicReference<String> method = new AtomicReference<>();
    private final AtomicReference<String> authorization = new AtomicReference<>();
    private final AtomicReference<String> contentType = new AtomicReference<>();
    private final AtomicReference<String> formBody = new AtomicReference<>();

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0
        );
        server.createContext("/introspect", this::handle);
        server.start();

        String uri = "http://127.0.0.1:" +
            server.getAddress().getPort() + "/introspect";

        introspector = SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId("local-introspector")
            .clientSecret("local-demo-secret")
            .build();
    }

    private void handle(HttpExchange exchange) throws IOException {
        try {
            method.set(exchange.getRequestMethod());
            authorization.set(exchange.getRequestHeaders()
                .getFirst("Authorization"));
            contentType.set(exchange.getRequestHeaders()
                .getFirst("Content-Type"));

            String body = new String(
                exchange.getRequestBody().readAllBytes(),
                StandardCharsets.UTF_8
            );
            formBody.set(body);

            String json = body.contains("token=opaque-good")
                ? "{\"active\":true,\"sub\":\"alice\",\"scope\":\"messages.read\"}"
                : "{\"active\":false}";

            byte[] response = json.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                .set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
        }
        finally {
            exchange.close();
        }
    }

    @AfterEach
    void shutdown() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void postsTokenAndBasicClientCredentials() {
        StepVerifier.create(introspector.introspect("opaque-good"))
            .assertNext(principal ->
                assertThat((String) principal.getAttribute("sub"))
                    .isEqualTo("alice")
            )
            .verifyComplete();

        assertThat(method.get()).isEqualTo("POST");

        String basic = "Basic " + Base64.getEncoder()
            .encodeToString(
                "local-introspector:local-demo-secret"
                    .getBytes(StandardCharsets.UTF_8)
            );
        assertThat(authorization.get()).isEqualTo(basic);
        assertThat(contentType.get())
            .startsWith("application/x-www-form-urlencoded");
        assertThat(formBody.get()).contains("token=opaque-good");
    }

    @Test
    void inactiveResponseCannotAuthenticate() {
        StepVerifier.create(introspector.introspect("opaque-revoked"))
            .expectError()
            .verify();
    }
}
```

Run:

```bash
./gradlew test --tests '*IntrospectionContractTest'
```

**Expected:** Test 1 verifies Spring Security sends POST/form/Basic and receives a principal; Test 2 verifies `active:false` fails. This test uses the `SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` builder from **Spring Security 6.5**, requiring no real IdP. In modular builds with custom configurations, ensure JDK module `jdk.httpserver` is present.

### 8.2 Test Scope

An HTTP stub does not verify real client IDs authorized by the IdP, does not verify certificate trust since it uses loopback HTTP, and does not verify real token revocation. Staging integration tests against the environment's actual IdP are mandatory before production.

## 9. Advanced Configuration Options

### 9.1 Java DSL Instead of application.yml

Spring Security 6.5 allows configuring the URI and credentials directly in `ServerHttpSecurity`:

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex ->
            ex.anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque
                .introspectionUri("https://idp.example.test/introspect")
                .introspectionClientCredentials(
                    clientId, clientSecret
                )
            )
        )
        .build();
}
```

This is a **method snippet** requiring `clientId` and `clientSecret` variables from secrets/config (not literal secrets) and the corresponding imports. DSL configuration can **override auto-config**; avoid pointing YAML at IdP A while DSL points at IdP B. If only the three properties are needed, prefer property-driven configuration for easier environment management and to avoid duplicate logic.

### 9.2 Custom ReactiveOpaqueTokenIntrospector Bean

When you need custom network timeouts, a custom `WebClient`, mTLS, or claim mapping:

```java
@Bean
ReactiveOpaqueTokenIntrospector introspector(
    @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
    String uri,
    @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
    String id,
    @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
    String secret
) {
    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(uri)
        .clientId(id)
        .clientSecret(secret)
        .build();
}
```

This is a **bean snippet** requiring Spring `Value`, `Bean`, and introspection class imports. Use the builder because the three-String constructor of `SpringReactiveOpaqueTokenIntrospector` is **deprecated for removal in 6.5**.

**Caution:** When you define a custom `ReactiveOpaqueTokenIntrospector` bean, Boot's default auto-config backs off. You become responsible for checking `active`, expiry/metadata, and proper mapping. A lambda like `token -> Mono.just(new Principal(...))` in production would turn **every bearer token** into an authenticated user — a critical flaw.

### 9.3 Custom Authority Mapping

Spring Security maps `scope` in the response to `SCOPE_<scope>` authorities by default. If the IdP returns roles in a separate attribute:

1. Use a **trusted introspector** as a delegate so the token is verified first.
2. Read only verified attributes from the delegate; never read roles from request headers.
3. Map into clearly namespaced authorities and avoid arbitrarily granting `ROLE_ADMIN`.
4. Enforce issuer/audience/tenant boundaries and write negative test cases.

Structural snippet:

```java
public final class DelegatingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public DelegatingIntrospector(
        ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .map(verified -> {
                // Mapping uses only verified.getAttributes()
                // and configured/trusted policy.
                return verified;
            });
    }
}
```

This is a **class snippet** in its own file requiring imports for `ReactiveOpaqueTokenIntrospector`, `OAuth2AuthenticatedPrincipal`, and `Mono`. Returning `verified` preserves the principal verified by the delegate; IdP-specific mapping logic must never be guessed.

### 9.4 When Should You Not Override?

If the IdP supports standard RFC 7662 with Basic credentials, the three Boot properties suffice for many apps. Avoid writing custom code merely to duplicate library functionality: it increases the risk of botching token requests, dropping validations, leaking secrets, or mishandling errors.

## 10. Diagnosing 401/403/Introspection Failures

| Scenario | Source | Typical Outcome |
| --- | --- | --- |
| Missing `Authorization: Bearer` | Inbound API caller missing credential | 401 |
| Empty/malformed Bearer | Inbound authentication parser | 401 |
| IdP returns `active:false` | Invalid/expired/revoked token | 401 |
| IdP returns `active:true`, matching scope | Authenticated + authorized | 200, endpoint-dependent |
| IdP returns `active:true`, missing scope | HTTP authorization | 403 |
| Wrong `client-id` or `client-secret` | IdP rejects outbound introspection call | Does not automatically mean inbound 401/403; handle auth service error |
| Wrong `introspection-uri` path | HTTP 404 from IdP | Integration error, fix the URI |
| TLS handshake/cert error | Outbound HTTPS to IdP | Cannot verify token, fail closed |
| IdP 5xx/timeout | Outbound dependency unavailable | Return no data; status depends on exception handling, possibly 5xx |
| Active token, wrong tenant | Business authorization | 403/404 per privacy policy |
| Unregistered API path | `anyExchange().denyAll()` | Typically 403 if token is valid |
| Public health request | `permitAll()` | 200 if handler succeeds |

**Distinguish the two HTTP requests:** The Resource Server receives an inbound GET with Bearer; simultaneously, it makes an **outbound POST** to the IdP with Basic auth. Outbound 401/403 errors from the IdP **should not simply** be forwarded verbatim as 401/403 to the API consumer. Never catch all introspector exceptions and return 200 or a default principal.

### 10.1 When to Fail Closed?

If the IdP does not return a valid result, the Resource Server cannot know whether the Bearer token is active and holds sufficient scopes. Never create an authenticated principal or return sensitive data. You can return a sanitized infrastructure error response (e.g., 503) per architecture, but **never allow by default**.

### 10.2 403 Does Not Mean Invalid Token

An active token with scope `profile.read` can still be rejected when calling `/api/messages`. That is an **authorization denial**, not an introspection failure. Do not blindly tell users to log in again on every 403; inspect scopes and domain policies first.

### 10.3 Why Does curl Succeed While the Browser Fails with CORS?

CORS is enforced by the browser, not by `active:true`. If a cross-origin SPA frontend calls the API, configure CORS preflight properly before authentication. CORS success **does not guarantee an active token**; the Resource Server still validates Bearer tokens per policy.

## 11. Protecting the Introspection Client Secret and Bearer Token

**An outbound introspection request contains two sets of secrets:**
- The Resource Server's Basic client secret;
- The API caller's Bearer token in the body.

Therefore:

- Use **HTTPS/TLS** with certificate/hostname validation from the Resource Server to the IdP.
- Never use insecure trust-all TLS in production.
- Place the IdP URI in trusted configuration; never let an attacker choose the URL when sending tokens.
- Never write `Authorization: Basic`, `Bearer`, `token=...`, or `client_secret` into logs, traces, CI artifacts, or support tickets.
- Restrict IAM/ACL permissions so only the Resource Server workload can read the introspection secret.
- Use a secret manager with a rotation/rollback runbook.
- Consider an outbound egress allowlist to prevent SSRF.
- Never store secrets in frontend `localStorage`, cookies/query strings, or API responses.
- Scope the introspection client per least privilege; in multi-tenant setups, separate client credentials/trust boundaries.
- Never assume HTTP Basic Base64 encoding hides secrets from eavesdroppers.
- Configure timeouts, rate limiting, and metrics so floods of junk bearer tokens cannot overwhelm the IdP.

**Never log raw tokens for debugging:** log the route, error category, latency, request ID, and allowlisted IdP name; if token correlation is needed, evaluate a salted/rotated hash/HMAC with restricted access to avoid creating an oracle or PII leak.

## 12. Caching, Revocation, and IdP Dependency

### 12.1 Should Introspection Results Be Cached?

Caching reduces per-request API latency and IdP load, but means a revoked token may **continue being accepted until the cache expires**. You must define:

- A TTL not exceeding access token expiration and short enough for your revocation SLO;
- Cache keys partitioned by issuer/tenant/audience, protecting the token value;
- Invalidation when the IdP revokes a token (if events/hooks exist);
- Never using a stale active cache as an automatic fallback during an IdP outage;
- Negative caching/rate limiting that avoids creating a token-existence oracle;
- Monitoring for token cache hits/misses, stale errors, and revoked-token acceptance.

Do not assume Spring Security Opaque Token support caches introspection results for you automatically. Any custom cache must be vetted for security implications.

### 12.2 Timeouts and Retries

Because introspection uses outbound HTTP on the authentication critical path:

1. Cap connect/read timeouts and concurrent introspections.
2. Retry with backoff only for transient network failures, with strict bounds.
3. Never retry indefinitely on `active:false` or wrong client credentials.
4. Configure Netty/WebClient connection pooling properly.
5. Add a circuit breaker/bulkhead aligned with SLOs if the IdP is persistently slow.
6. Alert on latency, outages, and spikes in invalid tokens.

**Never call `block()` on the Netty event loop.** `ReactiveOpaqueTokenIntrospector` returns a `Mono` that plugs directly into WebFlux reactive authentication.

### 12.3 Rate Limiting Before Introspection

An attacker can send thousands of random Bearer strings to force the app to query the IdP for each one. Even if the API returns 401, the outbound calls consume resources. Ingress/gateways and applications need request budgets, rate limits, bot protection/quotas by IP or client identity, and must avoid logging token values.

### 12.4 Revocation and Latency

The source of trust is the Authorization Server. If a token is revoked, the IdP can return `active:false` and the Resource Server rejects the next introspection call. However, if the app caches positive results for 5 minutes, rejection can be delayed by up to ~5 minutes. That is a security decision requiring approval based on data sensitivity.

## 13. Multi-Tenancy and Authority Mapping

### 13.1 Active Is Not a Complete Policy

If an API serves multiple tenants, `active:true` and scope `messages.read` do not confirm the user may read tenant B's documents. You need business rules based on trusted tenant/owner claims and database access controls.

### 13.2 Issuer/Audience

Some introspection endpoints return `aud`, `iss`, `client_id`, and `exp`; others return only `active`/`scope`/`sub`. Those fields can be optional or vary by provider. Do not assume every IdP returns `aud` in the expected format. If your architecture requires audience restriction, configure the IdP to scope resource introspection or write a policy verifying trusted attributes.

### 13.3 Multiple IdPs

A single `introspection-uri` fits a single IdP/trust boundary. When supporting multiple issuers/tenants, you need trusted routing and separate credentials — never choose an IdP from an unverified string inside an opaque token, never send issuer A's token to IdP B, and never accept arbitrary URLs from requests as the introspection URI.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Confusing `introspection-uri` with `token-uri` | 404/invalid request | Obtain the exact RFC 7662 endpoint from the IdP |
| Omitting `client-id`/`client-secret` | Boot fails to build introspector or IdP rejects | Inject all three properties |
| Using SPA client ID instead of introspection client | IdP denies introspection | Create a confidential client with proper permissions |
| Committing client secret to Git | Credential compromise | Secret manager, rotation, redaction |
| Plain HTTP without TLS to IdP | Basic secret/token exposure | Use HTTPS and certificate verification |
| Using `HttpSecurity` in WebFlux | Wrong stack | `ServerHttpSecurity` + `SecurityWebFilterChain` |
| Using Servlet `OpaqueTokenIntrospector` | Wrong reactive interface | `ReactiveOpaqueTokenIntrospector` |
| Assuming `active:true` allows every method/path | Privilege escalation | Scope + resource authorization |
| Writing `hasAuthority("messages.read")` | Does not match `SCOPE_messages.read` | Use the `SCOPE_` prefix |
| Treating outbound IdP 401 as inbound client 401 | Wrong error classification | Separate request hops |
| Catching network errors and returning a principal | Authentication bypass | Fail closed |
| Using fake introspector in production | Bypasses token verification | Keep fakes in tests only |
| Using `mockOpaqueToken()` to test client secrets | No HTTP introspection happens | Add contract tests / staging integration |
| Caching positive results without TTL/revocation | Accepts revoked tokens | Bound TTL per security SLO |
| Logging full tokens and Basic headers | Credential leakage | Redaction and safe metrics |
| IdP 5xx slows down API | Critical dependency lacks budgets | Timeouts/concurrency limits/circuit breaker |
| Multi-tenant token sent to wrong IdP | Cross-issuer trust confusion | Trusted routing and isolated credentials |
| Client lacking scope gets 403 and keeps refreshing | Does not grant extra permissions | Check scopes, consent, and domain policy |
| Reading `X-User`/`X-Role` from caller | Caller spoofing | Use only verified principal/attributes |
| Confusing CORS 401 with token 401 | Debugging wrong layer | Inspect preflight and auth separately |
| Enabling verbose network logging in production | Body/header leaks | Logging allowlist, secret scrubbing |

## 15. Self-Check Questions

**1. Where does `introspection-uri` point?** To the **Authorization Server's Token Introspection Endpoint**, not the URL of the API being protected.

**2. Do `client-id`/`client-secret` belong to the user calling the API?** No. They are the introspection client credentials used by the Resource Server.

**3. Where does the Bearer access token go?** The caller sends it to the Resource Server. The Resource Server passes the token to the IdP in the introspection form body; never send refresh tokens.

**4. Is `active:false` treated as authenticated?** No; token validation fails.

**5. What happens when a token with `active:true` and scope `profile.read` calls `/api/messages` requiring `messages.read`?** Typically 403 due to missing `SCOPE_messages.read`.

**6. Why is introspection usually an HTTP POST?** RFC 7662 defines an endpoint accepting a form request containing `token` and client authentication; Spring Security follows the protocol.

**7. Are `oauth2Client()` and `oauth2ResourceServer()` interchangeable?** No; one obtains outbound tokens, while the other validates inbound tokens.

**8. Is a Basic client secret protected by Base64?** No; Base64 is not encryption. You must use HTTPS.

**9. Why not use `issuer-uri` instead of `introspection-uri`?** `issuer-uri` is used for JWT validation/discovery; opaque introspection requires an explicitly configured endpoint.

**10. If the IdP times out, should access be granted to avoid downtime?** No. You must fail closed and handle the infrastructure error.

**11. When should you use a custom introspector bean?** When you have a specific need such as mTLS, a custom HTTP client, or claim mapping; delegate to trusted validation and test thoroughly.

**12. Why does `mockOpaqueToken()` not verify Basic credentials?** It creates a mock principal in tests without sending a real introspection request.

**13. Why is caching risky?** Revoked tokens may continue to be accepted for the duration of the TTL.

**14. Can an active token read data across all tenants?** No; scope, audience/tenant, and object ownership checks still apply.

**15. Which HTTP status codes should tests verify?** Missing/bad bearer typically 401; active lacking scope 403; sufficient scope 200; IdP network failures must never turn into 200.

## 16. Production Checklist

- [ ] Configured as an **opaque Resource Server**, not confused with JWT or OAuth2 Client.
- [ ] Correct `introspection-uri` from a trusted IdP, over HTTPS/TLS.
- [ ] `client-id` belongs to a confidential introspection client with required permissions.
- [ ] `client-secret` stored in a server secret manager, never in Git/frontend/logs.
- [ ] Uses `ReactiveOpaqueTokenIntrospector` and `ServerHttpSecurity` for the WebFlux stack.
- [ ] Enables `oauth2ResourceServer(...opaqueToken...)` for protected APIs.
- [ ] No fake introspector bean present in production.
- [ ] `active:false` is rejected; only `active:true` produces a principal.
- [ ] Scopes mapped to `SCOPE_...` and route rules enforce the right authorities.
- [ ] Owner/tenant/domain checks enforced when APIs return private data.
- [ ] 401/403/200 and negative cases verified with `WebTestClient`.
- [ ] Basic/form POST verified with a real introspector contract test.
- [ ] HTTPS connectivity, certificates, and client secret permissions verified in an IdP sandbox.
- [ ] Timeouts, concurrency limits, rate limits, monitoring, and outage runbooks in place.
- [ ] Positive cache TTL evaluated against the revocation SLO.
- [ ] Raw bearer tokens, Basic credentials, and token form bodies never logged.
- [ ] Egress allowlist, SSRF protection, and issuer/tenant separation configured where needed.
- [ ] Secret rotation strategy in place to avoid downtime on credential changes.
- [ ] CORS, CSRF, and gateway policies designed independently, never replacing bearer validation.

## 17. Summary

The three essential properties for Spring Boot **opaque token introspection** are:

```yaml
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri: https://idp.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id: ${INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

When receiving `Authorization: Bearer <opaque-token>`, Spring Security WebFlux uses `ReactiveOpaqueTokenIntrospector` to query the Authorization Server over HTTPS, confirm `active:true`, and map scopes to `SCOPE_...`. Invalid tokens are typically rejected with **401**, while active tokens lacking sufficient permissions receive **403**. Never bypass authentication because the IdP is unavailable.

**Most importantly:** `client-id`/`client-secret` here are the **Resource Server's credentials for introspection**, not the API caller's Bearer token. Protect them with TLS and secrets management, verify the exact endpoint, authorize by scope/tenant, and test both fake HTTP policies and real introspection contracts.

### Official Documentation

- [Spring Security 6.5 — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/index.html)
- [Spring Security 6.5 — Reactive OAuth2 Tests, mockOpaqueToken](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [Spring Security 6.5 — SpringReactiveOpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security 6.5 — SpringReactiveOpaqueTokenIntrospector.Builder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.Builder.html)
- [Spring Security 6.5 — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Boot 3.5 — Security configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
