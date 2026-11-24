# Opaque Tokens and How They Differ from Self-Verified JWTs in Spring Security Reactive

## 1. Learning Objectives

An API system using OAuth 2.0 typically receives an access token via the HTTP header `Authorization: Bearer <token>`. Both are Bearer tokens, yet one system issues an **opaque** string whose contents the resource server cannot read on its own and must verify with the Authorization Server; another system issues a structured, signed **JWT (JSON Web Token)** so the resource server can verify it locally with a public key. These two choices strongly affect how requests are authenticated, token revocation capability, latency, IdP dependency, and trust boundaries.

In **Spring Security reactive / Spring WebFlux**, this topic corresponds to the two configuration branches `ServerHttpSecurity.oauth2ResourceServer(...).opaqueToken(...)` and `.jwt(...)`, not Servlet's `HttpSecurity`.

After this lesson, you can:

1. Explain opaque access tokens, JWT access tokens, Bearer tokens, and why **token format** differs from **token verification strategy**.
2. Describe the flow in which `ReactiveOpaqueTokenIntrospector` sends a token to the OAuth 2.0 Token Introspection Endpoint per **RFC 7662**, receives `active` and metadata, and creates an `Authentication`.
3. Compare this with `ReactiveJwtDecoder` verifying the JWT signature, `iss`, `exp`, `nbf`, and `aud` using a JWK/public key without necessarily calling the IdP on every request.
4. Configure Spring Boot 4.1.x + Spring Security WebFlux for opaque tokens using the URI, introspection client ID/secret, and `SecurityWebFilterChain`.
5. Build a standalone local Java 17+ demo with a **custom reactive introspector restricted to the demo profile**, observing HTTP 200/401/403 and mapping scopes to `SCOPE_*`.
6. Analyze response latency, network failures, caching, revocation, audience, token/secret security, and correctness testing.
7. Decide when to choose opaque introspection, self-verified JWTs, or **introspected JWTs** for online status checks.

**Core takeaway:** "Opaque" does not unconditionally mean "more secure than JWT," "JWT" does not mean "already authenticated just because it has three Base64URL segments," and **any leaked Bearer token can be replayed** without additional binding constraints.

## 2. Concepts: Bearer, Opaque, JWT, and Introspection

### 2.1. Bearer Is a Presentation Method, Not a Token Structure

Consider two example requests:

~~~http
GET /api/messages HTTP/1.1
Host: api.example.com
Authorization: Bearer 9LzSxY7kExampleRandomString
~~~

~~~http
GET /api/messages HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.signature
~~~

Both use the **Bearer authentication scheme** per RFC 6750. The second string only simulates three JWT segments and is **not a validly signed JWT**; do not send it as a real access token. The Resource Server determines the **verification mechanism** from its configuration rather than counting dots in the string to trust it.

A Bearer token is a credential that **anyone who possesses it can present** to the resource server, unless the system enforces appropriate proof-of-possession/token binding mechanisms. Therefore, always require TLS/HTTPS, limit logging/headers/query exposure, and control token issuance.

### 2.2. Opaque Access Token

An access token that is **opaque to the resource server** means the resource server should not or cannot infer claims/permissions simply by parsing the token. Typically, it is an unguessable random string issued by the Authorization Server and mapped to server-side state.

Illustrative example:

~~~text
opaque-token: a8f26e7b9c... (issued random string)
~~~

The Resource Server sends the token to a controlled **introspection endpoint**, receiving the `active` status and metadata. It does not need to know whether the token stores state in a database, cache, or any internal mechanism inside the Authorization Server.

**Key point:** a token handled as opaque can still **carry the JWT format**. If the resource server always sends that string to the introspection endpoint instead of locally decoding/accepting its signature, the actual verification method is still **online introspection**. Conversely, a random string containing a few dots does not become a valid JWT.

### 2.3. JWT Access Token

A JWT is a three-segment structure when using **JWS Compact Serialization**:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

The payload can contain claims such as:

~~~json
{
  "iss": "https://idp.example.com",
  "sub": "user-123",
  "aud": ["api.example.com"],
  "scope": "messages.read reports.read",
  "iat": 1790000000,
  "exp": 1790003600
}
~~~

This is **illustrative** data, not a signed token. A typical JWS-signed JWT is only **Base64URL-encoded**, so its payload content is not confidential; anyone holding the string can read the claims. JWE is the **encrypted** form, distinct from JWS; never assume a JWT is secret just because the payload looks unreadable.

A resource server must **not merely decode** the payload and trust the claims. It must:

- Verify the signature and a trusted algorithm, rejecting `alg=none` or algorithm confusion.
- Check that issuer `iss` is an allowed issuer.
- Check `exp` and `nbf` timestamps, handling clock skew in a controlled way.
- Check `aud`/resource indicators matching this exact API, along with any required tenant/client/scope constraints.
- Retrieve public keys from a trusted **JWK Set**; handle key rotation without accepting attacker-supplied keys.
- Check authorities at the authorization step rather than treating "valid JWT" as "sufficient permissions."

### 2.4. Two Distinct Axes

| Axis | Options |
| --- | --- |
| **Format/representation** | Random opaque string, JWT/JWS, other token formats |
| **Verification strategy** | Local cryptographic validation, OAuth2 token introspection, lookup in a dedicated store/validator |

Do not equate "JWT = always offline verification" and "opaque = always a network call." However, in common Spring Security WebFlux usage, **`jwt()`** represents the self-verified JWT strategy, while **`opaqueToken()`** calls the introspection endpoint by default.

## 3. Authentication Flow for an Opaque Bearer Token

~~~text
OAuth2 Client                      Resource Server (WebFlux)          Authorization Server
     |                                       |                              |
     | GET /api/messages                     |                              |
     | Authorization: Bearer opaque-123      |                              |
     |-------------------------------------->|                              |
     |                               Bearer authentication filter           |
     |                               ReactiveOpaqueTokenIntrospector        |
     |                                       | POST /introspect             |
     |                                       | token=opaque-123             |
     |                                       | client authentication        |
     |                                       |----------------------------->|
     |                                       |       active + scope + sub   |
     |                                       |<-----------------------------|
     |                               Map OAuth2AuthenticatedPrincipal       |
     |                               + SCOPE_* authorities                  |
     |                               AuthorizationWebFilter                 |
     |                                      / \                             |
     |                                   pass deny                          |
     |                                     |    |                           |
     |<--------------------------- 200 or 403/401                           |
~~~

Spring Security reactive handles the filter/authentication pipeline in WebFlux. When a Bearer token is present, `ReactiveOpaqueTokenIntrospector.introspect(token)` checks the token and returns `Mono<OAuth2AuthenticatedPrincipal>`. Upon success, a `BearerTokenAuthentication` is placed into the `SecurityContext` in the Reactor Context; authorization uses the principal and authorities to make access decisions.

### 3.1. Introspection Request per RFC 7662

A typical introspection request is an **HTTPS POST** with form parameter `token` and client authentication required by the Authorization Server:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64-of-introspection-client-credentials>

token=opaque-123&token_type_hint=access_token
~~~

`token_type_hint` is optional in the protocol and is not always sent by default introspectors. The Basic line only illustrates HTTP authentication; do not write raw client secrets into documentation, logs, or command history. The Authorization Server may support other client authentication methods such as mTLS or private_key_jwt; configure the corresponding implementation rather than assuming one client ID/secret works with every IdP.

An active response per RFC 7662 may look like:

~~~json
{
  "active": true,
  "client_id": "report-web",
  "scope": "messages.read reports.read",
  "sub": "user-123",
  "token_type": "Bearer",
  "exp": 1790003600,
  "iat": 1790000000,
  "aud": ["api.example.com"],
  "iss": "https://idp.example.com"
}
~~~

An **inactive** token should return a minimal response:

~~~json
{
  "active": false
}
~~~

`active=false` can occur because the token does not exist, has expired, was revoked, is not intended for the querying resource server, or per Authorization Server policy. Do not use that response to expose granular details such as "which user was revoked" in public HTTP responses.

### 3.2. active Does Not Replace Audience/Authorization Policy

`active=true` means the Authorization Server confirms the token's status under its introspection policy. However, the resource server must still protect the **right API**:

- Verify the token was **issued for this resource server**, preventing a valid token for API A from being used on API B.
- Verify `aud`, resource indicator, `client_id`/issuer/tenant, and scopes when provided by the IdP contract.
- If the introspection response lacks the information needed to restrict audience, ask the IdP to configure per-resource-server introspection policy or add explicit validation.
- Do not grant `ROLE_ADMIN` merely because introspection returns an attribute named `role` whose semantics have not been verified.
- `active=true` does not automatically allow access to every URL. Rules like `hasAuthority("SCOPE_messages.read")` still govern access.

### 3.3. Errors from the Introspection Endpoint

You must distinguish between:

| Case | Nature | Principle |
| --- | --- | --- |
| HTTP 200 `{"active":true,...}` | Token verified | Proceed to authorization |
| HTTP 200 `{"active":false}` | Token invalid according to server | Reject authentication |
| HTTP 401 from introspection endpoint | **Resource server failed to authenticate to the IdP** (wrong client secret/method) | Configuration or credentials incident, not inherently a user token error |
| HTTP 429/503/timeout from introspection | IdP/network overloaded or failing | **Fail closed**; do not skip validation just because the IdP is down |
| Malformed JSON/missing `active` | Non-conformant protocol response | Do not assume token is active |
| HTTP 403 at API after active introspection | Token may be valid but lacks required scope | Authorization denied; do not automatically turn into a token error |

External callers should only receive errors fitting the HTTP security contract (typically 401 for an invalid token, 403 for missing scope; outages may yield 5xx depending on handling). Do not expose stack traces, client secrets, tokens, internal endpoints, or introspection details in responses.

## 4. Self-Verified JWT at the Resource Server: Comparison Flow

~~~text
Client                   Spring WebFlux Resource Server           Authorization Server
  |                                  |                                  |
  | GET /api/messages                |                                  |
  | Authorization: Bearer JWS        |                                  |
  |--------------------------------->|                                  |
  |                           ReactiveJwtDecoder                        |
  |                           parse header/payload                      |
  |                           find key by kid / trusted JWKS            |
  |                           verify signature + validators             |
  |                                  |                                  |
  |                           key cache miss / rotation? ---------- JWKS|
  |                           (no per-request introspection call)       |
  |                           validate iss, exp, nbf, aud               |
  |                           map scopes -> SCOPE_*                     |
  |                           authorization                             |
  |<-------------------------- 200 / 401 / 403                          |
~~~

With JWTs, the resource server can hold **public keys** and verify tokens without calling the IdP on every request. This typically reduces latency and runtime dependency on the introspection endpoint. However, when keys rotate, the JWK cache expires, or the issuer changes, the resource server still needs a key refresh strategy.

The trade-off: a validly signed JWT **can still be accepted until it expires**, even if the user/account/token was just revoked at the Authorization Server, unless the application uses a revocation list, introspection, session/token version, very short lifetimes, or an additional policy check.

### 4.1. Self-Verification Does Not Mean "Signature Check Only"

A resource server that verifies only the signature **without checking `aud` or issuer** can accept a JWT meant for another service. JWT has **no implicit mechanism** guaranteeing every claim fits the API; designers must verify default validations and add explicit audience/tenant/permission policies.

Similarly, a custom `JwtDecoder` replacing the default can accidentally drop `iss`/`aud` validation if misconfigured. For security, rely on standard validators and add explicit validators rather than just decoding the payload.

### 4.2. When JWTs Also Use Introspection

Spring Security Opaque Token support **does not depend on how many segments the token has**. If a JWT is sent to the introspection endpoint, the resource server can use `opaqueToken()` and let the Authorization Server decide whether it is still active. This is a sound choice when **rapid revocation** matters more than local self-verification. Therefore, the technical choice should be phrased as:

- **JWT local validation**: verification based on signature/public key and claims.
- **Online token introspection**: calling the Authorization Server, applicable to random opaque strings **or** JWTs.
- **Hybrid**: local JWT validation combined with an online state check for sensitive actions/operations; must be designed explicitly so neither step is accidentally bypassed.

## 5. Decision Comparison Table

| Criterion | Opaque + Introspection | Self-Verified JWT |
| --- | --- | --- |
| Does the resource server read the token? | No need to parse structure | Must decode/verify JWS |
| Source of truth for active token | Authorization Server (introspection) | Local signature + claims/validators |
| Network call during authentication | Usually **every request** without caching | Usually none, except JWKS discovery/refresh |
| Revocation before expiration | Can take effect nearly immediately with real-time introspection | Not automatically visible while signature/claims remain valid |
| Impact during temporary IdP outage | High without caching | Usually lower while public keys are cached |
| Per-request latency | Adds network and endpoint processing | Local crypto verification, usually lower latency |
| Scalability | Introspection must scale with API traffic or use caching | Easier to distribute, no central per-request lookup needed |
| Token contains PII | Opaque string typically hides claims from clients | JWS payload is readable by anyone holding the token |
| State storage cost | AS usually needs token state/lookup | Can be stateless at AS, though rotation/revocation trade-offs remain |
| Primary complexity | Trusting introspection endpoint, HTTP client, credentials, availability | JWKS, crypto, algorithms, issuer/audience/time validators |
| Scope/role | From introspection response | From verified JWT claims |
| Caching | Reduces load but delays revocation | Caches JWKS; token validation still runs per request |
| Can JWT use introspection? | **Yes** | Not applicable if only local decoder is used |
| Best suited for | Early permission revocation, centralized IdP | High-traffic APIs, many services, low latency |
| Failure mode | Introspection timeout/503 -> fail closed | Invalid signature/key/claim -> fail closed |

**Neither option wins in every scenario.** For sensitive transactions requiring immediate revocation, introspection is advantageous. For high-throughput APIs, self-verified JWTs are often appropriate if access token TTLs are short and risky actions have additional revocation checks.

## 6. Spring Security Reactive APIs

| Component | Opaque | JWT |
| --- | --- | --- |
| `ServerHttpSecurity` DSL | `oauth2ResourceServer(o -> o.opaqueToken(...))` | `oauth2ResourceServer(o -> o.jwt(...))` |
| Primary validator | `ReactiveOpaqueTokenIntrospector` | `ReactiveJwtDecoder` |
| Default implementation | `SpringReactiveOpaqueTokenIntrospector` | `NimbusReactiveJwtDecoder` per config |
| Input | `String token` | `String token` |
| Output | `Mono<OAuth2AuthenticatedPrincipal>` | `Mono<Jwt>` |
| Typical Authentication | `BearerTokenAuthentication` | `JwtAuthenticationToken` |
| Principal | `OAuth2AuthenticatedPrincipal` | `Jwt` |
| Default authorities | Introspection scope -> `SCOPE_*` | JWT scope/`scp` -> `SCOPE_*` |
| Spring Boot property namespace | `spring.security.oauth2.resourceserver.opaquetoken.*` | `spring.security.oauth2.resourceserver.jwt.*` |
| Needs OAuth2 Client registration? | **No**, this is a Resource Server | **No**, this is a Resource Server |

### 6.1. ReactiveOpaqueTokenIntrospector

Abbreviated signature:

~~~java
@FunctionalInterface
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
~~~

This describes the contract, **not** a class to define yourself. Correct imports:

~~~java
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import reactor.core.publisher.Mono;
~~~

The publisher must **emit a verified principal** when the token is valid; an inactive/invalid token must **error**, never creating an "anonymous yet authenticated" principal to bypass security. For the standard implementation, `SpringReactiveOpaqueTokenIntrospector` performs HTTP introspection and maps the response per RFC 7662.

**Do not use** Servlet/blocking `OpaqueTokenIntrospector` or `SpringOpaqueTokenIntrospector` in WebFlux unless you intentionally bridge blocking calls onto a bounded scheduler (usually unnecessary). Avoid `block()` inside `introspect(...)` on the event loop.

### 6.2. WebFlux DSL Configuration

A minimal chain:

~~~java
@Bean
SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges ->
                    exchanges.anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
}
~~~

This is a **method snippet**; import `@Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and `Customizer`. When using Spring Boot's introspection properties, `introspection-uri`/client ID/secret can be auto-configured by Boot. If you define your own `ReactiveOpaqueTokenIntrospector` bean or call `.introspector(custom)`, you **replace** default introspection and must ensure your custom code actually verifies tokens.

### 6.3. Spring Boot Properties — Opaque Resource Server

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=${INTROSPECTION_URI}
spring.security.oauth2.resourceserver.opaquetoken.client-id=${INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret=${INTROSPECTION_CLIENT_SECRET}
~~~

When the article is saved, the `${...}` notation is converted to the standard property placeholder using the dollar sign. The endpoint must use **HTTPS** and accept only a trusted Authorization Server. These are **introspection client credentials**, not the client ID/secret of an end user calling the API; do not commit them to Git or print them in logs, and manage them via a secret manager with rotation.

### 6.4. Customizing with SpringReactiveOpaqueTokenIntrospector

In Spring Security 6.5+/7.x, older constructors taking URI/ID/secret may be deprecated; Javadoc guides you to use the **builder**:

~~~java
ReactiveOpaqueTokenIntrospector introspector =
        SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(introspectionUri)
                .clientId(introspectionClientId)
                .clientSecret(introspectionClientSecret)
                .build();
~~~

This snippet belongs inside a configuration class, and the variables above must be injected from protected secrets/config. When creating a bean explicitly:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector customIntrospector(
        @Value("${demo.introspection-uri}") String uri,
        @Value("${demo.introspection-client-id}") String id,
        @Value("${demo.introspection-client-secret}") String secret) {
    return SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(uri)
            .clientId(id)
            .clientSecret(secret)
            .build();
}
~~~

This bean snippet is **optional** for applications with those three `demo.*` properties and **must not be used simultaneously** with the mock introspector bean in the demo section. It demonstrates how to use the builder; when default configuration suffices, **prefer configuring only the three Spring Boot properties** in Section 6.3.

### 6.5. Customizing Authorization

Introspection response:

~~~json
{
  "active": true,
  "sub": "reader",
  "scope": "messages.read reports.read"
}
~~~

Spring Security maps scopes by default to:

~~~text
SCOPE_messages.read
SCOPE_reports.read
~~~

Example policy:

~~~java
.pathMatchers("/api/messages")
        .hasAuthority("SCOPE_messages.read")
.pathMatchers("/api/admin")
        .hasAuthority("SCOPE_admin")
~~~

`hasAuthority` checks the exact string. `hasRole("ADMIN")` looks for `ROLE_ADMIN` by default and **does not automatically match `SCOPE_admin`**. If the IdP provides a dedicated role claim, map it from a trusted source using an allowlist and never blindly prepend `ROLE_` to arbitrary client-supplied strings.

## 7. Local Java 17+ Example: Opaque Resource Server

To avoid **registering a real IdP** while learning, we use a `ReactiveOpaqueTokenIntrospector` scoped to the `demo` profile. It accepts **exactly two fixed illustrative tokens** and rejects every other value. This lets you observe the actual HTTP/Authentication/Authorization pipeline in Spring Security WebFlux.

**Mandatory warning:** this is only a **fake introspector for learning** and provides **zero real token security**. Never enable the `demo` profile in production or expose it to the Internet; production must use a real introspection endpoint. None of the test data/tokens below have any security value.

### 7.1. Create the Project

Use Maven + Java 17+, group `com.example`, artifact `reactive-opaque-demo`, Spring Boot **4.1.2**, selecting **Spring Reactive Web**, **Spring Security**, and **OAuth2 Resource Server**.

With Spring Boot 4, the standard starter is named `spring-boot-starter-security-oauth2-resource-server` (the older `spring-boot-starter-oauth2-resource-server` name is kept for compatibility/deprecated). Full `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>reactive-opaque-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Do not add `spring-boot-starter-webmvc` or `spring-boot-starter-web` to avoid mixing Servlet/MVC with WebFlux. Let the Boot BOM manage Spring Security module versions; do not override individual versions into conflicting combinations.

### 7.2. Complete Java Source

Create `src/main/java/com/example/opaque/OpaqueVsJwtApplication.java`:

~~~java
package com.example.opaque;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class OpaqueVsJwtApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueVsJwtApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/api/messages")
                                .hasAuthority("SCOPE_messages.read")
                        .pathMatchers("/api/admin")
                                .hasAuthority("SCOPE_admin")
                        .pathMatchers("/api/me").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }

    // For local demo only. DO NOT run the demo profile in production.
    @Bean
    @Profile("demo")
    ReactiveOpaqueTokenIntrospector demoOpaqueIntrospector() {
        return token -> {
            if ("opaque-reader-demo".equals(token)) {
                return Mono.just(principal(
                        "reader", "messages.read",
                        List.of("SCOPE_messages.read")));
            }
            if ("opaque-admin-demo".equals(token)) {
                return Mono.just(principal(
                        "administrator", "messages.read admin",
                        List.of("SCOPE_messages.read", "SCOPE_admin")));
            }
            // Do not return Mono.empty() or a fake anonymous principal.
            // An invalid token must result in an authentication failure.
            return Mono.error(new BadOpaqueTokenException(
                    "Inactive or unknown token"));
        };
    }

    private static OAuth2AuthenticatedPrincipal principal(
            String subject, String scopes, List<String> authorities) {

        List<GrantedAuthority> granted = authorities.stream()
                .map(SimpleGrantedAuthority::new)
                .map(authority -> (GrantedAuthority) authority)
                .toList();

        return new DefaultOAuth2AuthenticatedPrincipal(
                subject,
                Map.of("sub", subject, "scope", scopes),
                granted);
    }

    @RestController
    static class Api {

        @GetMapping(value = "/public",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> publicEndpoint() {
            return Mono.just(Map.of("message", "PUBLIC_OK"));
        }

        @GetMapping(value = "/api/me",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, Object>> me(
                BearerTokenAuthentication authentication) {
            return Mono.just(Map.<String, Object>of(
                    "subject", authentication.getName(),
                    "authorities", authentication.getAuthorities()
                            .stream()
                            .map(GrantedAuthority::getAuthority)
                            .sorted()
                            .toList()));
        }

        @GetMapping(value = "/api/messages",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> messages() {
            return Mono.just(Map.of("message", "MESSAGES_OK"));
        }

        @GetMapping(value = "/api/admin",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> admin() {
            return Mono.just(Map.of("message", "ADMIN_OK"));
        }
    }
}
~~~

**Technical analysis:**

1. The `SecurityWebFilterChain` bean configures reactive `ServerHttpSecurity` properly.
2. `oauth2ResourceServer(...opaqueToken(...))` uses the opaque authentication manager; Spring Security locates the matching `ReactiveOpaqueTokenIntrospector` bean.
3. `@Profile("demo")` ensures fake token acceptance only exists when the `demo` profile is active. **Production must never enable this profile**; when `demo` is off, configure the introspection endpoint and credentials as shown in Section 8.
4. In the fake introspector, `Mono.just(principal(...))` represents an active token; `Mono.error(new BadOpaqueTokenException(...))` represents an inactive token. Never return `Mono.empty()` as a way of silently treating a token as valid.
5. `DefaultOAuth2AuthenticatedPrincipal` holds the name, attributes, and explicit authorities. The fake implementation hardcodes scopes/authorities; in reality, `SpringReactiveOpaqueTokenIntrospector` retrieves them from the introspection endpoint.
6. `BearerTokenAuthentication` in the controller is supplied by Spring Security **after successful authentication**. Do not manually extract the token from the header in the controller to parse/authorize it.
7. `/api/messages` requires `SCOPE_messages.read`. `/api/admin` requires `SCOPE_admin`. A valid reader token lacking the admin scope produces **403**.
8. `/public` uses `permitAll()`, yet if a client **intentionally sends an invalid Bearer token** to a public route, the authentication filter may still reject it before the controller; test public routes **without sending a token**.
9. The demo endpoints only expose GET, so cookie-authenticated POST CSRF handling is not yet involved. For APIs using only Bearer tokens and no browser-auto-sent cookie/session credentials, the CSRF threat model differs; do not globally disable CSRF when form/session login also exists.
10. Demo tokens provide **no security** and must not be treated as proof of real signature verification, introspection protocol behavior, or revocation.
11. `Map.of` does not guarantee JSON key ordering; tests should assert values by field name.
12. Because the demo uses two literal tokens, those `Authorization` values must never be used in any Internet-accessible system.

### 7.3. Running the Local Demo

In the directory containing `pom.xml`:

~~~bash
./mvnw clean package
SPRING_PROFILES_ACTIVE=demo ./mvnw spring-boot:run
~~~

On Windows PowerShell, set the environment variable:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "demo"
.\mvnw.cmd clean package
.\mvnw.cmd spring-boot:run
~~~

If the wrapper is absent, use an installed `mvn`. With the source above, Spring Boot runs by default on `http://localhost:8080`. **Bind/use on localhost only**, with fake data for learning; when deploying for real, enable HTTPS and use online introspection.

### 7.4. Calling the API with curl

~~~bash
# Public endpoint requires no Authorization header.
curl -i http://localhost:8080/public

# Private endpoint missing Bearer token.
curl -i http://localhost:8080/api/me

# Valid opaque reader token.
curl -i -H 'Authorization: Bearer opaque-reader-demo' \
  http://localhost:8080/api/me

# Reader accessing messages.
curl -i -H 'Authorization: Bearer opaque-reader-demo' \
  http://localhost:8080/api/messages

# Reader lacks admin authority.
curl -i -H 'Authorization: Bearer opaque-reader-demo' \
  http://localhost:8080/api/admin

# Admin has sufficient scope.
curl -i -H 'Authorization: Bearer opaque-admin-demo' \
  http://localhost:8080/api/admin

# Unrecognized token.
curl -i -H 'Authorization: Bearer unknown-demo-token' \
  http://localhost:8080/api/me
~~~

Expected behavior table:

| Request | Status | Main Content |
| --- | --- | --- |
| `GET /public` without header | **200** | `{"message":"PUBLIC_OK"}` |
| `GET /api/me` anonymous | **401** | Bearer challenge; no valid principal |
| `GET /api/me` reader | **200** | Subject `reader`, authorities include `SCOPE_messages.read` |
| `GET /api/messages` reader | **200** | `{"message":"MESSAGES_OK"}` |
| `GET /api/admin` reader | **403** | Valid token but missing `SCOPE_admin` |
| `GET /api/admin` admin | **200** | `{"message":"ADMIN_OK"}` |
| `GET /api/me` unknown | **401** | Token rejected by fake introspector |

Exact 401/403 status/error bodies/headers may vary by Spring Security version and exception handler; do not assert a hardcoded default error JSON string not produced by your controller. In WebFlux, the principal exists via the Reactor Security Context after the filter, not via Servlet `HttpSession`.

### 7.5. Practice Exercise: Observing Without a Token Parser

Try three small changes **locally only**:

1. Change `"opaque-reader-demo"` to a token not recognized by the bean: you receive 401, even if the string looks like a JWT.
2. Call `/api/admin` with the reader token: you receive 403, because authentication succeeds but authorization lacks the required scope.
3. Add `SCOPE_admin` to the reader's authority list in the fake introspector: after restarting, `/api/admin` succeeds. This proves **permissions come from trusted introspection/mapping results**, not merely from the shape of the token string.

This illustrates server responsibility; never allow clients to send their own authority list and skip source verification.

## 8. Moving from Demo to Real Introspection

### 8.1. Disable the Demo Profile and Configure Production

Do not set `SPRING_PROFILES_ACTIVE=demo` on a real server. Set the three Spring Boot properties in `application.properties`, or via suitable environment variables/secret manager:

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=${INTROSPECTION_URI}
spring.security.oauth2.resourceserver.opaquetoken.client-id=${INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret=${INTROSPECTION_CLIENT_SECRET}
~~~

Provide real values through a secret manager or managed environment:

~~~bash
export INTROSPECTION_URI='https://idp.example.com/oauth2/introspect'
export INTROSPECTION_CLIENT_ID='api-resource-server'
export INTROSPECTION_CLIENT_SECRET='secret-issued-by-idp'
./mvnw spring-boot:run
~~~

**The values in this example are illustrative**; no public IdP is pre-provisioned. You must substitute a real introspection endpoint, real client credentials, and a real token issued by the Authorization Server. Spring Boot auto-configures `SpringReactiveOpaqueTokenIntrospector` when no mock introspector bean is active.

In production, never store the introspection secret in Git, never log request bodies/headers containing bearer tokens or secrets, and configure timeouts, connection pools, and observability to the IdP according to your actual topology.

### 8.2. Verifying a Token Before Spring Integration

If you have a test access token and a valid introspection client, one way to probe manually **in a protected environment**:

~~~bash
curl --fail-with-body \
  --user "$INTROSPECTION_CLIENT_ID:$INTROSPECTION_CLIENT_SECRET" \
  --data-urlencode "token=$ACCESS_TOKEN" \
  "$INTROSPECTION_URI"
~~~

Ensure the endpoint uses trusted HTTPS. **Do not enable verbose HTTP logging**, and never put tokens into URLs, tickets, public screenshots, or shell history. Depending on the environment, commands may expose credentials in process arguments; in production, use managed tooling/secret injection and log controls.

If the IdP returns `{"active":false}`, **do not** alter the response or forge a local principal to force API 200. Check which resource server the real token was issued for, whether it expired/was revoked, or whether client authentication/issuer is mismatched.

### 8.3. Minimum Policy for the Resource Server

Even when introspection returns `active=true`, the resource server **must still** require appropriate authorities per route:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/messages")
                .hasAuthority("SCOPE_messages.read")
        .pathMatchers("/api/admin")
                .hasAuthority("SCOPE_admin")
        .anyExchange().authenticated())
~~~

If the introspection response uses custom claims, map them in a controlled manner before authorization decides. In particular, validate `aud` and resource restrictions when the API spans multiple services. An active token belonging to another client or audience **must not automatically gain access to this API**.

### 8.4. Custom Delegate Pattern for Policy Validation

If you need extra issuer/audience checks from introspection metadata, you can wrap the standard introspector with a delegate:

~~~java
ReactiveOpaqueTokenIntrospector delegate =
        SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(introspectionUri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();

ReactiveOpaqueTokenIntrospector validating = token ->
        delegate.introspect(token)
                .flatMap(principal -> {
                    Object aud = principal.getAttribute("aud");
                    if (!(aud instanceof java.util.Collection<?> c)
                            || !c.contains("api.example.com")) {
                        return Mono.error(new BadOpaqueTokenException(
                                "Token not intended for this API"));
                    }
                    return Mono.just(principal);
                });
~~~

This is an **optional configuration snippet**, not a standalone runnable file. It **assumes the IdP contract returns `aud` as a Collection**; if the provider returns a String or a different metadata field, adapt the validator to the agreed schema instead of skipping the audience check. Use an introspection client authorized to query tokens meant for this API and protect response data. For richer customization, you can use `ReactiveOpaqueTokenAuthenticationConverter` to customize the principal/authorities after introspection.

### 8.5. Do Not Confuse Introspection Client ID with User Client ID

The introspection endpoint may require **resource server credentials** to query tokens, distinct from the client that requested the token for the user. The `client_id` value in the introspection response identifies the original client to which the token was issued; it differs from `INTROSPECTION_CLIENT_ID` used by the resource server to authenticate to the IdP. Do not compare the two unless your contract explicitly requires them to match.

## 9. Comparing with Self-Verified JWT Configuration

Also on Spring Boot WebFlux, if the IdP issues JWT access tokens and the API wants **local signature verification**, use JWT configuration instead of opaque.

### 9.1. application.properties for JWT

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=${JWT_ISSUER_URI}
spring.security.oauth2.resourceserver.jwt.audiences=${JWT_EXPECTED_AUDIENCE}
~~~

Real deployments must replace issuer/audience with values published by the IdP. `issuer-uri` uses discovery metadata to locate the JWK Set; `audiences` ensures the token was actually issued for this API. You can also configure `jwk-set-uri` when specifying the public keys endpoint directly or avoiding discovery dependency at startup/first request, while still requiring proper `iss`/`aud` validators.

### 9.2. SecurityWebFilterChain for JWT

~~~java
@Bean
SecurityWebFilterChain jwtSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/messages")
                            .hasAuthority("SCOPE_messages.read")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}
~~~

**Replacement snippet** for the opaque chain in an application using JWT; do not paste a second catch-all chain with the same order. For JWT, the primary bean is `ReactiveJwtDecoder`, and the `Authentication` object is typically `JwtAuthenticationToken`. Validate allowed algorithms, signature, issuer, expiresAt, notBefore, and audience. `JWT_EXPECTED_AUDIENCE` has no universal safe default across projects — set it specifically for your resource server.

### 9.3. Why "I Can Decode the JWT" Is Not Enough

A JWT with payload `{"scope":"admin"}` can be **forged by anyone** if the server only Base64URL-decodes without verifying the signature. Never write code like:

~~~javascript
// ANTI-PATTERN: read payload for display only,
// NEVER treat it as token authentication.
const payload = JSON.parse(atob(token.split(".")[1]));
if (payload.scope === "admin") grantAdmin();
~~~

This is an anti-pattern to recognize; Base64URL also differs from standard Base64 rules. Perform server-side authorization only after Spring Security has verified the token using a trusted decoder and validators.

### 9.4. Public Key Caching and Revocation

A JWT resource server can cache the JWKS and avoid calling the IdP on every request. It still needs to refresh public keys when the IdP rotates keys or a `kid` is missing from the cache. If an account is locked or a token is revoked before the JWT expires, local verification may **continue accepting the token** under policy until `exp`; strict requirements need a dedicated revocation mechanism.

Do not rely on "deleting the JWT public key" to revoke a single user token: that can break **all tokens** signed with the same key. If rapid per-token revocation is required, consider opaque introspection or a well-designed hybrid/revocation list.

## 10. When to Choose Which?

### 10.1. Opaque + Introspection Fits Best When

- The system requires **near-real-time access token revocation**.
- Permissions/scopes can change rapidly; the Authorization Server must remain the centralized decision source.
- The service footprint is moderate or the introspection endpoint has sufficient capacity/HA.
- You want to avoid exposing claim data inside tokens that clients could decode.
- You can operate HTTPS introspection with SLAs, timeouts, observability, and secret rotation.

### 10.2. Self-Verified JWT Fits Best When

- High API throughput or many microservices require low latency.
- Services must continue operating during brief IdP unavailability while the JWK cache remains valid.
- Access token TTLs are short and revocation delay is acceptable, or a separate revocation check exists.
- Operations can manage JWKS/algorithms/key rotation/issuer/audience validation.
- Minimal claims do not expose unnecessary PII to the bearer holder.

### 10.3. Hybrid: JWT + Introspection

If the IdP issues JWTs but **rapid revocation** is required, you can:

1. Use `opaqueToken()` to introspect the JWT like any bearer string; do **not** run both local verification and introspection unless policy explicitly calls for it.
2. Use `jwt()` local verification for most requests, while querying online state separately on sensitive routes/actions.
3. Use short-lived JWT access tokens and refresh-token revocation at the Authorization Server according to your threat model.

Each option has trade-offs; if adopting a hybrid model, clearly define **failure behavior for each layer** and fail-closed conditions. Avoid silently "falling back to local verification when introspection fails" on resources requiring immediate revocation.

## 11. Caching, Performance, and Consistency

### 11.1. Introspecting Every Request Can Be Costly

Suppose every incoming API request makes an HTTPS call to the IdP; as request volume grows, the introspection endpoint and network sit on the critical path. Request latency depends on:

~~~text
Total time ~ network to resource server
           + network to introspection
           + token state processing at IdP
           + authorization/controller work
~~~

This is a conceptual model, not a specific latency forecast. Measure actual P50/P95/P99, timeouts, circuit breakers, and saturation. Never deploy a single IdP endpoint in one network zone without an HA strategy.

### 11.2. Should Introspection Results Be Cached?

Possibly, but caching reduces token revocation effectiveness:

| Policy | Benefit | Risk |
| --- | --- | --- |
| No caching of introspection results | Every request sees latest state | High load/latency, IdP dependency |
| Very short positive cache | Reduces call volume | Revocation may not take effect until TTL expires |
| Cache per token until `exp` | Eliminates many calls | Nullifies near-real-time revocation benefit |
| Controlled short negative cache | Mitigates invalid-token storms | Must avoid distorting new-token behavior or outage classification |
| JWKS cache for JWT | Reduces public key fetches | Not equivalent to caching per-JWT status |

If caching introspection results, the TTL should **not exceed the token's remaining lifetime** and must be smaller than the maximum stale-authorization window acceptable to the business. For sensitive actions, consider bypassing the cache or re-querying status. Always test revoking a token immediately after a cache hit.

**Cache key security:** avoid storing raw bearer tokens in metrics/logs/visible Redis keys. Use a key-managed HMAC/fingerprint and avoid caching values containing unnecessary PII. Invalidate cache entries on revocation events if the IdP supports them, while keeping an expiry-bound TTL.

### 11.3. Do Not Assume Mono.cache() Creates an App-Wide Cache

~~~java
return delegate.introspect(token).cache();
~~~

This is an **anti-pattern if written inside a per-request introspect method** expecting cross-request caching. Each invocation can create a new `Mono`; `cache()` only memoizes that single publisher instance and does not create a global token cache. Cross-request caching requires an actual store/key/TTL/concurrency control and consideration of token revocation.

### 11.4. When Introspection Is Down

Do not do this:

~~~java
return delegate.introspect(token)
        .onErrorResume(error ->
                Mono.just(fakeAuthenticatedPrincipal));
~~~

This is an illustrative **anti-pattern**; `fakeAuthenticatedPrincipal` is undefined and **not standalone compilable code**. It turns an IdP failure into successful authentication and can bypass revocation/authorization. Any fail-open behavior for availability requires special security review and safe constraints, never default API security.

For sensitive requests, fail closed: deny access and report an appropriate infrastructure error, separating `invalid_token` metrics from `introspection_unavailable`. Never mask IdP 5xx/timeouts as "wrong password" on dashboards, and never retry infinitely.

## 12. 401, 403, Audience, and Configuration Errors

| Scenario | Typical Resource Server HTTP | What to Check |
| --- | --- | --- |
| Missing Authorization on protected URL | **401** + Bearer challenge | Did the client send the header |
| Malformed/unknown/inactive token | **401** | Did introspection return active false? Valid Bearer format? |
| Active token lacking `SCOPE_messages.read` | **403** | Scopes and authority mapping |
| Active token with wrong `aud` | **401** if validator treats it as invalid | IdP introspection audience contract |
| Active token, right scope, handler runs | **200** | Business rules must still be checked |
| IdP introspection 401 | Potential infrastructure issue (resource server client credentials) | Client ID/secret and auth method |
| Introspection timeout/503 | System error; do not fail-open | Timeouts, retry budget, circuit breaker |
| Invalid JWT signature | **401** | JWKS, key rotation, alg/issuer |
| Expired JWT `exp` | **401** | Exp/nbf/clock skew |
| Validly signed JWT but different API `aud` | **401** if aud validator enabled | Audience configuration |
| Active token belonging to wrong tenant | Must be rejected per policy | Issuer/client/tenant mapping |

A resource server may return 401/403 whose response body is not controlled by the controller. Inspect both `WWW-Authenticate` and authentication/authorization details rather than relying on a fixed error JSON string.

### 12.1. Resource Server vs. OAuth2 Client

The `spring.security.oauth2.resourceserver.opaquetoken.*` properties configure an **API that accepts Bearer tokens**. They do not register OAuth2 Login `/oauth2/authorization/...`, do not create an `OAuth2AuthorizedClient` for downstream calls, and do not issue tokens. Acting as an OAuth2 Client requires separate dependencies/managers/client registrations.

### 12.2. Never Accept a Token by Appearance

Do not classify tokens using heuristics like:

- "The token has three parts so it's a JWT, no introspection needed."
- "A 64-character token must be random and valid."
- "An ID Token is a JWT, use it as an access token to call APIs."
- "Introspection active=true from any tenant is enough to grant admin."
- "Base64URL-decoding the JWT means the signature is valid."

The resource server must enforce validation configured for the actual issuer/audience/resource/authorities.

## 13. Accurate Testing with WebTestClient and Mock IdP

### 13.1. WebTestClient Testing Authorization Policy

Spring Security Test reactive provides `mockOpaqueToken()` to populate a `BearerTokenAuthentication` in the `SecurityContext` during tests:

~~~java
// Snippet inside a test class with a configured WebTestClient.
webTestClient.mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_messages.read")))
        .get().uri("/api/messages")
        .exchange()
        .expectStatus().isOk();

webTestClient.mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_profile")))
        .get().uri("/api/messages")
        .exchange()
        .expectStatus().isForbidden();
~~~

This is a **test snippet** requiring `SecurityMockServerConfigurers.mockOpaqueToken`, `SimpleGrantedAuthority`, and compatible WebFlux Test/Spring Security Test imports; it is not a complete JUnit class.

**Important limitation:** `mockOpaqueToken()` **does not call the introspection endpoint**. It attaches a mock Authentication to the request to test **authorization policy**. To integration-test `SpringReactiveOpaqueTokenIntrospector`, write tests against a real mock HTTP introspection endpoint per RFC 7662 and assert request/response/timeout/error mapping.

### 13.2. Business and Protocol Test Matrix

| Case | Input | Expected Result |
| --- | --- | --- |
| Public anonymous | GET `/public` without header | 200 |
| Protected without token | GET `/api/me` | 401 |
| Valid opaque token | Introspection `active=true` | Authentication succeeds |
| Introspection `active=false` | Random/revoked/expired token | 401, controller not invoked |
| Active token lacking scope | `scope="profile"`, URL requires messages.read | 403 |
| Active token matching scope | `scope="messages.read"` | 200 |
| Wrong audience | `aud` excludes current API | Must be rejected if policy requires |
| IdP introspection HTTP 401 | Wrong client secret | Infrastructure config error, no bypass |
| IdP timeout or HTTP 503 | Network/IdP outage | Fail closed; monitor and avoid infinite retries |
| Malformed introspection JSON | Missing `active` or wrong `active` type | Do not treat token as valid |
| Token is JWT using `opaqueToken()` | Introspection verifies JWT | Depends on active result, no local verify |
| Validly signed JWT, wrong `aud` | JWT decoder with audience validation | 401 |
| Expired JWT `exp` | JWT decoder time validation | 401 |
| JWT revoked before expiry | Local JWT validation only | May still be accepted without revocation check |
| JWT key rotated | JWKS cache refresh | Accepts new key per policy |
| 429 introspection or burst on same token | Rate/availability policy | No fail-open, no request storm |
| Token from disallowed issuer | Issuer/token metadata policy | Grant no permissions |
| Public JSON business route with invalid Bearer | Invalid header sent | May be rejected by auth filter despite permitAll |

### 13.3. Performance and Revocation Testing

Test using this sequence:

1. Issue a valid access token, call API -> 200.
2. Revoke the token at the IdP.
3. Call the API immediately: opaque introspection **without caching** should return 401 once the IdP reports active=false.
4. Enable a short introspection cache TTL: measure the exact **stale window** before the API begins rejecting.
5. For local-only JWTs, revoke at the IdP while keeping an unexpired JWT: note that policy may continue accepting it; do not misinterpret this as a signature verification bug.
6. Measure throughput/P95 and IdP call rate at peak traffic.
7. Shut down the introspection endpoint in a test environment: verify the API **fails closed** rather than silently accepting old tokens indefinitely.
8. Test introspection client secret rotation: no prolonged outage, no credential leakage.

This is a **test scenario**, not measured benchmark results.

## 14. Common Mistakes

### 14.1. Using Servlet APIs in WebFlux

`OpaqueTokenIntrospector` and `SpringOpaqueTokenIntrospector` (without Reactive) belong to synchronous Servlet usage; WebFlux should use `ReactiveOpaqueTokenIntrospector`, `SpringReactiveOpaqueTokenIntrospector`, and `ServerHttpSecurity`.

### 14.2. Copying JWT Properties to Opaque Config

`spring.security.oauth2.resourceserver.jwt.issuer-uri` does not auto-configure online introspection. For opaque tokens, configure `opaquetoken.introspection-uri` and valid introspection client authentication, or a `ReactiveOpaqueTokenIntrospector` bean with a clear contract.

### 14.3. Forgetting Audience/Resource Restrictions

`active=true` on a token issued for another API is insufficient to grant access. Enforce audience/client/issuer/tenant constraints per the Authorization Server contract and never trust scopes from another tenant.

### 14.4. Calling the Introspection Endpoint over HTTP

Bearer tokens and introspection client secrets can leak without TLS. Use HTTPS and validate the certificate chain; never disable TLS verification with trust-all.

### 14.5. Granting Admin Roles from Arbitrary Raw Claims

A claim like `roles=["admin"]` should only be mapped if the Authorization Server authoritatively manages that claim and it belongs to the right API/tenant. Never prepend `ROLE_` to arbitrary token/client-supplied strings.

### 14.6. Handling Inactive Tokens with an Empty Principal

A custom introspector must not return `Mono.just(new DefaultOAuth2AuthenticatedPrincipal(...))` if the token is unverified; nor return `Mono.empty()` to signify "no error" instead of invalid. Signal an error per the contract.

### 14.7. Assuming JWTs Are Encrypted

Common JWT/JWS tokens are only signed, leaving the Base64URL payload readable. Never place passwords, API secrets, or unnecessary sensitive PII in JWT claims.

### 14.8. Decoding JWTs Without Verifying Signature and Issuer

Anyone can decode a self-crafted JWT string. Use `ReactiveJwtDecoder` and validators instead of parsing the payload yourself to grant authorities.

### 14.9. Caching Introspection Results Too Long

A positive cache with TTL up to `exp` can mask token revocation or account suspension. Choose TTL based on revocation SLAs, not throughput alone.

### 14.10. Accepting All Tokens When IdP Connection Fails

This is a dangerous fail-open flaw. Distinguish invalid tokens from unavailable introspection, preserve fail-closed behavior, and implement incident handling/circuit breakers.

### 14.11. Confusing OAuth2 Resource Server with OAuth2 Login

A Resource Server only authenticates Bearer tokens sent to an API; it does not issue tokens, redirect users to an IdP, or create an `OAuth2AuthorizedClient` for downstream calls.

### 14.12. Ignoring WWW-Authenticate on 401/403

401 may indicate a bad/missing token header, while 403 indicates insufficient scope; the Bearer challenge conveys protocol details. Do not translate everything into "wrong password."

### 14.13. Testing Only mockOpaqueToken Without Testing Introspection Networking

`mockOpaqueToken()` bypasses the introspector; it validates policy but does not prove client credentials, endpoint URL, or `active` parsing work. Include integration tests against a mock IdP.

### 14.14. Exposing the Fake Demo Introspector to the Internet

Hardcoded token `opaque-admin-demo` becomes a **critical vulnerability** if run in production. Restrict the demo profile to learning machines and exclude fake beans from production artifacts when possible. Never treat `@Profile("demo")` as sufficient protection if operators could accidentally activate the profile.

### 14.15. Passing Tokens in Query Parameters

Bearer tokens in URLs easily leak into browser history, access logs, analytics, and Referer headers; send `Authorization: Bearer ...` over HTTPS.

### 14.16. Disabling CSRF Simply Because It Is a "REST API"

For APIs that accept only Bearer headers and use no automatic browser credentials, the CSRF model differs from cookie sessions. However, if the app also uses form login, cookie auth, WebSockets, or cookie-sending SPAs, evaluate separately before disabling CSRF. Choosing opaque vs. JWT **does not determine CSRF requirements**.

## 15. Production Deployment Checklist

1. Correctly determine the token **format** and **verification strategy**; do not assume JWTs are always local or opaque tokens are always random.
2. Use `ReactiveOpaqueTokenIntrospector`/`ServerHttpSecurity` with WebFlux; do not copy Servlet APIs.
3. Align Spring Boot/Spring Security versions, using the proper Boot 4.x resource server starter.
4. Ensure the introspection endpoint uses verified HTTPS/TLS, and client credentials are protected and rotated.
5. Verify introspection responses return `active=true` and sufficient metadata to identify the target resource server.
6. Define scope/authority rules for every URL; `active` alone never grants unrestricted permissions.
7. Validate issuer, audience, client, and tenant per the token and resource server contract.
8. Never fail-open on IdP outage, timeout, or invalid response.
9. Design timeouts, connection pooling, rate limiting, circuit breakers, and observability appropriately.
10. If caching introspection results, bound TTL within `exp` and revocation requirements; test the stale window.
11. Ensure JWT local validation enforces trusted algorithms, keys, `iss`/`exp`/`nbf`/`aud` validators, and key rotation.
12. Never log Bearer tokens, introspection secrets, or sensitive claims.
13. Never transmit tokens in URLs/query strings.
14. Test 200, 401, 403, active false, wrong audience, expired, revoked, invalid introspection client, 503, and caching.
15. Test the resource server behind proxies/TLS termination, preserving the Bearer header and avoiding accidental gateway logging.
16. Ensure the `demo` profile or hardcoded test tokens can never be activated in production.
17. Across many microservices, evaluate introspection throughput/availability versus JWT JWKS caching.
18. Choose a dedicated revocation mechanism if local JWT validation cannot meet business requirements.

## 16. Self-Check

**Question 1.** How do opaque tokens and Bearer tokens differ?

**Answer:** Bearer is the authentication scheme for presenting a token in an HTTP header; opaque means the resource server does not independently infer contents/permissions from the token and typically needs introspection or a token store to verify it.

**Question 2.** Must Spring Security always verify JWTs offline?

**Answer:** No. A JWT can be processed via `jwt()` with local signature validation, or sent to an introspection endpoint via `opaqueToken()` when online status is required.

**Question 3.** Is an introspection response of `{"active":true}` enough to call any API?

**Answer:** No. You must verify the token is intended for the right resource server/audience and carries the required scope/authority for the endpoint.

**Question 4.** Why does `GET /api/admin` with the demo reader token return 403 instead of 401?

**Answer:** The reader token is recognized as active by the fake introspector, but its authorities lack `SCOPE_admin`. Authentication succeeds, while authorization fails.

**Question 5.** If a JWT signature is valid but `aud` is wrong, should it be accepted?

**Answer:** No. The resource server needs audience validation in addition to signature/issuer/time checks.

**Question 6.** Why can local JWT validation accept a recently revoked token?

**Answer:** A local verifier only knows signatures/claims/keys; it does not ask the Authorization Server about per-token revocation state. You need an online check/revocation mechanism or short token TTLs.

**Question 7.** Why does caching introspection results change revocation behavior?

**Answer:** A cached `active=true` entry can remain valid after the IdP has revoked the token, until the TTL expires or the cache is invalidated.

**Question 8.** Which interface does Spring Security WebFlux use for opaque tokens?

**Answer:** `ReactiveOpaqueTokenIntrospector`, returning `Mono<OAuth2AuthenticatedPrincipal>`; the standard implementation is `SpringReactiveOpaqueTokenIntrospector`.

**Question 9.** What does `mockOpaqueToken()` verify?

**Answer:** It tests HTTP authorization using a mock Authentication; it does not call the introspection endpoint or verify real client credentials or tokens.

**Question 10.** If the introspection endpoint times out, can tokens be temporarily treated as active to preserve availability?

**Answer:** Not under safe defaults. You should fail closed, handle IdP errors, monitor, and design HA/caching within approved risk limits.

## 17. Official Documentation

- [Spring Security — Reactive OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth2 WebFlux overview](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [Javadoc — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Javadoc — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Javadoc — ServerHttpSecurity OAuth2 OpaqueTokenSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2ResourceServerSpec.OpaqueTokenSpec.html)
- [Javadoc — BadOpaqueTokenException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/BadOpaqueTokenException.html)
- [Javadoc — DefaultOAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html)
- [Javadoc — BearerTokenAuthentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html)
- [Spring Security — Testing OAuth2 in Reactive WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Boot — OAuth2 Resource Server auto-configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
