# `OpaqueTokenIntrospector` and `SpringOpaqueTokenIntrospector` across versions

## 1. The problem: a Resource Server authenticating a Bearer token it cannot decode locally

In a **Spring Security OAuth 2.0/OIDC Resource Server**, an API commonly receives an access token over HTTP:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer 8pABlP0q6sV2...opaque-token...
```

With a **signed JWT access token**, the Resource Server typically uses `JwtDecoder` to verify the JWS, issuer, audience, expiration, and claims. By contrast, with an **opaque access token**, the token string does not present a JWT structure that the API can safely parse and verify locally. The API must ask the **Authorization Server** (or an authorized token-checking service) whether the token is still active and what attributes it carries.

**RFC 7662 — OAuth 2.0 Token Introspection** defines an endpoint where the Resource Server submits the token and receives its status along with associated metadata.

In Spring Security Servlet:

- **`OpaqueTokenIntrospector`** is the *interface* describing the token-checking contract.
- **`SpringOpaqueTokenIntrospector`** is *an implementation* that sends HTTP requests to the introspection endpoint.
- **`NimbusOpaqueTokenIntrospector`** is the historical implementation present in older releases and marked deprecated in newer ones.
- **`RestClientOpaqueTokenIntrospector`** is the Spring `RestClient`-based replacement introduced in Spring Security 7.1.

Knowing **which Spring Security version you are running** matters greatly, because class names, builders, constructors, and client credential encoding behavior have changed over time.

> **Key principle:** Application code should depend on the **`OpaqueTokenIntrospector` interface**, choosing the framework-version-appropriate implementation solely in configuration. Never swap implementations to bypass checks for `active`, scope, issuer, audience, or API access boundaries.

## 2. RFC 7662: introspection request and response

### 2.1. What does the Resource Server send?

The Resource Server is issued **its own** credentials to call the introspection endpoint. Example request:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <encoded-introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=8pABlP0q6sV2...&token_type_hint=access_token
```

`token` is the credential the API received from the client. `token_type_hint` is an **optional** hint parameter per RFC 7662; the Spring implementation/provider contract governs whether the actual request includes it.

**Never confuse the two credential types:**

1. The user's or caller application's Bearer access token, sent **to the Resource Server**.
2. The Resource Server's `client-id`/`client-secret`, used **to authenticate to the introspection endpoint**.

These two credentials are not interchangeable and must be protected separately. The introspection client secret must never be placed in a browser or returned in API responses.

### 2.2. Active case

An example response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user-123",
  "client_id": "orders-web-client",
  "aud": ["orders-api"],
  "scope": "orders:read orders:export",
  "exp": 1893456000,
  "iat": 1893452400,
  "token_type": "Bearer"
}
```

This response contains illustrative data, not output from a live system. Common meanings:

| Attribute | Meaning | Points to note |
| --- | --- | --- |
| `active` | Issuer/introspection service confirms the token is currently recognized. | Not permission to access every API; resource policy is required. |
| `scope` | Granted scopes, usually a space-delimited string. | Spring can turn each scope into a `SCOPE_...` authority. |
| `sub` | Subject per the issuer's contract. | Not automatically an email or internal user ID. |
| `client_id` | OAuth client that received the token. | Does not replace `aud` or principal permissions. |
| `aud` | Intended recipient, if published by the provider. | API may need to validate the matching resource ID. |
| `iss` | Issuer, if returned by the provider. | Enforce an issuer contract when multiple sources exist. |
| `exp` / `iat` | Expiration/issuance timestamps, if returned. | Understand expiration policy and server-provided fields. |
| `token_type` | Token type per response. | Does not turn the credential into a signed JWT. |

Not every introspection endpoint returns **all** of these fields. RFC 7662 makes `active` the central field, while other metadata depends on the provider, introspection access privileges, and token profile. **The API contract must specify which metadata is mandatory for authorization decisions.**

### 2.3. Inactive case

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
```

The token may have expired, been revoked, never existed, or not be recognized by the issuer. Under RFC 7662, the checker does not have to disclose detailed reasons to the Resource Server. A proper introspector must never create an authenticated principal from an `active: false` response.

**Distinguish:** HTTP 200 from the introspection endpoint **does not mean the token is active**. You must read `active`. Conversely, an HTTP 401 at the **introspection endpoint** may indicate the Resource Server sent invalid client credentials, rather than proving the user's Bearer token is bad.

## 3. Processing flow inside Spring Security Servlet

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Introspection Endpoint
    participant A as AuthorizationFilter
    C->>F: GET /api/orders + Bearer token
    F->>F: Create BearerTokenAuthenticationToken
    F->>M: authenticate(token)
    M->>P: Select provider supporting Bearer token
    P->>I: introspect(rawToken)
    I->>AS: POST token + introspection credentials
    AS-->>I: active + metadata
    alt active=false or validation failure
        I-->>P: Exception
        P-->>F: AuthenticationException
        F-->>C: Reject Bearer credential
    else active=true and policy passes
        I-->>P: OAuth2AuthenticatedPrincipal + authorities
        P-->>M: BearerTokenAuthentication
        M-->>F: Authenticated Authentication
        F->>A: SecurityContext
        A-->>C: 2xx or 403 by permissions
    end
```

Role of each component:

1. `BearerTokenAuthenticationFilter` extracts the token string from the HTTP request.
2. `AuthenticationManager`, typically `ProviderManager`, routes the `BearerTokenAuthenticationToken` to the matching provider.
3. `OpaqueTokenAuthenticationProvider` invokes `OpaqueTokenIntrospector.introspect(token)`.
4. The introspector queries the endpoint or trusted state source and returns `OAuth2AuthenticatedPrincipal` if accepted.
5. The provider constructs `BearerTokenAuthentication`, carrying authorities and attributes from the introspection result.
6. Spring Security places the authentication into `SecurityContext`; URL security and method security enforce authorization.

**There is no mandatory JWS signature decoding step in this flow.** Spring Security does not require the token to be a JWT to call introspection; it can forward **any Bearer string** extracted by the resolver to the introspection endpoint. Consequently, even JWTs can be **authenticated via introspection** when policy requires checking the Authorization Server for revocation.

## 4. `OpaqueTokenIntrospector`: a stable contract across versions

The interface lives in package:

```java
org.springframework.security.oauth2.server.resource.introspection
    .OpaqueTokenIntrospector
```

Core signature:

```java
@FunctionalInterface
public interface OpaqueTokenIntrospector {

    OAuth2AuthenticatedPrincipal introspect(String token);
}
```

In practice, the method throws an exception when the token is invalid or introspection cannot be performed.

Key points:

- The argument is the **token string**, not the full `Authorization` header.
- The return type is `OAuth2AuthenticatedPrincipal`, holding attributes, authorities, and principal name.
- **Returning a principal signals the token passed introspection.** Never return a principal for `active: false`.
- You can write a **custom implementation/decorator** to add policy checks, metrics, or controlled caching.
- When swapping the underlying HTTP implementation, business code depends only on this interface.

Related exception types:

| Type | Typical meaning |
| --- | --- |
| `BadOpaqueTokenException` | Token rejected because it is invalid, inactive, or fails an acceptance condition. |
| `OAuth2IntrospectionException` | Error during introspection, including certain request/response/remote-service problems. |
| `AuthenticationException` at provider/filter layer | Spring Security translates appropriate authentication failures into Bearer responses. |

**Do not equate every introspection error with a revoked token.** For instance, timeouts, DNS/TLS failures, or wrong client credentials are communication/configuration incidents. Handle them **fail-closed** (never accept the token), while classifying operational errors and HTTP responses appropriately; 5xx/503 may suit infrastructure outages rather than always claiming the token itself is bad.

## 5. What is `SpringOpaqueTokenIntrospector`?

`SpringOpaqueTokenIntrospector` is an implementation that sends configured HTTP introspection requests, parses the response, and builds `OAuth2AuthenticatedPrincipal`. It resides in the same package as the interface:

```java
import org.springframework.security.oauth2.server.resource.introspection
        .SpringOpaqueTokenIntrospector;
```

The name **`SpringOpaqueTokenIntrospector`** easily causes two misunderstandings:

1. It is **not** a new interface replacing `OpaqueTokenIntrospector`; it **implements** that interface.
2. The word "Spring" in the class name **does not mean every Spring Security version has the same builders/constructors**.

Specifically, code written for 6.5+ may **fail to compile** on 6.4 or 5.6 simply because it uses the `withIntrospectionUri(...)` builder that had not yet been added in those releases.

## 6. API changes across Spring Security versions

The milestones below are **Spring Security library versions**, not Spring Boot version numbers. In a Boot project, check the actual dependency-managed `spring-security-oauth2-resource-server` version resolved, rather than guessing from a blog post or Spring Boot starter name.

| Spring Security version line | Notable API/behavior | Recommendation when writing code |
| --- | --- | --- |
| **5.2–5.5** | `OpaqueTokenIntrospector` and `NimbusOpaqueTokenIntrospector` exist from early introspection support. | Use APIs actually present in the running version; Nimbus examples may fit legacy projects. |
| **5.6–6.4** | `SpringOpaqueTokenIntrospector` was introduced (Since 5.6); uses constructors/`RestOperations`. | On 5.6+, you can choose the Spring implementation; **do not use the 6.5 builder** if the dependency lacks it. |
| **6.5** | `SpringOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` added; three-arg constructor `(uri,id,secret)` deprecated (forRemoval). `NimbusOpaqueTokenIntrospector` marked deprecated in 6.5 docs in favor of the Spring implementation. | On 6.5+, **prefer the builder** and migrate Nimbus-dependent code where appropriate. |
| **7.0** | Migration guide notes client ID/secret encoding updated per RFC; the builder accepts **unencoded values** and the new default mechanism handles encoding for you. | Carefully test special characters in introspection client credentials when upgrading from 6.x. |
| **7.1+** | `RestClientOpaqueTokenIntrospector` added using Spring `RestClient` (Since 7.1), alongside `RestOperations`/`RestTemplate`-based `SpringOpaqueTokenIntrospector`. | You can use the `RestClient` implementation when supported; do not copy this code into 6.x/7.0. |

Two key notes:

- `SpringOpaqueTokenIntrospector` **was not "renamed" to `OpaqueTokenIntrospector`**: the interface is still used. New implementations and builders are what changed.
- `NimbusOpaqueTokenIntrospector` was used by many older tutorials; seeing Nimbus code does not mean **it is the recommended API for newer releases**. Nor should you assume it was deleted from every version simply because it is deprecated; consult Javadoc for your exact dependency.

### 6.1. Avoid mixing documentation from different versions

Example:

```java
// Builder API for Spring Security 6.5+.
SpringOpaqueTokenIntrospector.withIntrospectionUri(uri)
        .clientId(id)
        .clientSecret(secret)
        .build();
```

If a project is on **Spring Security 6.3** and the IDE reports `withIntrospectionUri` cannot be found, the cause is likely that **the builder did not exist yet**, not a mysterious missing import.

Similarly:

```java
// Available only in Spring Security 7.1+.
RestClientOpaqueTokenIntrospector.withIntrospectionUri(uri)
        .clientId(id)
        .clientSecret(secret)
        .build();
```

If a 6.5 project fails to compile that line, choose the `SpringOpaqueTokenIntrospector` matching that version instead of mixing Spring Security 7.1 JARs into a 6.5 dependency set and causing version mismatches.

## 7. Simplest configuration: Spring Boot properties

With Spring Boot auto-configuration for an opaque Resource Server, **in many cases you do not need to define an introspector bean manually**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

This is a configuration example; `INTROSPECTION_CLIENT_ID`/`INTROSPECTION_CLIENT_SECRET` must be provided via an appropriate secret manager/environment. Never commit real credentials to source control.

And:

```java
@Configuration
class OpaqueApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

When no custom bean replaces it, Boot can auto-configure a default `OpaqueTokenIntrospector` from properties and Spring Security wires it into `OpaqueTokenAuthenticationProvider`. In principle, service/controller code remains unaware of the underlying HTTP implementation.

### 7.1. Dependencies

With Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

In modern Spring Security lines, opaque-token support resides in `spring-security-oauth2-resource-server` with Boot managing the necessary HTTP dependencies. Older Spring Security 5.5 docs required adding the Nimbus OAuth 2.0/OIDC SDK dependency for the default Nimbus implementation; when upgrading, do not blindly carry legacy dependency requirements into 6.5/7.x without checking the actual dependency graph.

**Never manually declare mixed Spring Security versions** just to make a single class appear. If an API lacks a builder, use the configuration supported by the project's managed version or upgrade the entire dependency set cleanly.

### 7.2. Authorization outcome

Suppose introspection returns:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders:read orders:export"
}
```

Spring Security typically creates authorities:

```text
SCOPE_orders:read
SCOPE_orders:export
```

A `GET /api/orders` request requiring `SCOPE_orders:read` can proceed to the controller. A request requiring `SCOPE_orders:write` must be denied at authorization if the principal lacks that authority.

**`active: true` does not mean "sufficient scope".** Authentication and authorization are two distinct steps.

## 8. Creating a `SpringOpaqueTokenIntrospector` bean on Spring Security 6.5+

Starting in **6.5**, you can use the builder to configure the introspection URI and **unencoded** client credentials:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection
        .OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
        .SpringOpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        return SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();
    }
}
```

Key points about the builder in Spring Security 6.5+:

- `withIntrospectionUri(uri)` creates a `SpringOpaqueTokenIntrospector.Builder`.
- `clientId(clientId)` and `clientSecret(clientSecret)` accept **raw, unencoded values** per the builder Javadoc.
- `build()` returns a `SpringOpaqueTokenIntrospector` assignable to `OpaqueTokenIntrospector`.
- Declaring a custom bean can suppress Boot's default bean creation; ensure this bean is actually wired into the chain handling requests.

This example reuses the same properties as section 7, but as a **deliberate alternative**, not something you always have to declare alongside auto-configuration. When property auto-configuration already meets your needs, properties alone are cleaner; define a bean only to customize the HTTP client, validation, metrics, or response source.

### 8.1. Note when customizing `SecurityFilterChain`

Declaring an `OpaqueTokenIntrospector` bean does not automatically turn a chain configured with `oauth2ResourceServer().jwt()` into an opaque Resource Server. The chain must configure:

```java
.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()))
```

Or pass an explicit introspector for that specific chain:

```java
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(opaque ->
        opaque.introspector(customIntrospector)))
```

`jwt()` uses `JwtDecoder`; `opaqueToken()` uses `OpaqueTokenIntrospector`. Do not assume Spring inspects whether a string has dots to pick between them per request.

## 9. Legacy projects: `NimbusOpaqueTokenIntrospector`

In many Spring Security 5.x codebases, introspector creation looked like this:

```java
// Legacy example: verify constructor against your exact Spring Security version.
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String clientId,
        @Value("${introspection.client-secret}") String clientSecret) {

    return new NimbusOpaqueTokenIntrospector(
            uri, clientId, clientSecret);
}
```

On versions containing that class, Nimbus code may still run. Yet once an application upgrades to **Spring Security 6.5**, the Javadoc marks `NimbusOpaqueTokenIntrospector` deprecated and directs users toward `SpringOpaqueTokenIntrospector`.

Do not **mechanically swap the class name** while ignoring:

- How HTTP requests are built and sent.
- How client ID/secret are URL-encoded when building Basic authentication.
- Timeout/TLS/proxy policies.
- How responses map to principal and authorities.
- Any registered custom request entity converters or interceptors.
- Test suites tied to specific behavior of the older implementation.

When migrating from Nimbus to Spring, keep the application's abstraction as `OpaqueTokenIntrospector` and run integration tests against a **mock introspection endpoint** to verify wire format and response behavior.

### 9.1. `SpringOpaqueTokenIntrospector` before 6.5

`SpringOpaqueTokenIntrospector` has existed since **5.6**, whereas the `withIntrospectionUri` builder appeared in **6.5**.

In 5.6–6.4, sample code uses the constructor:

```java
OpaqueTokenIntrospector introspector =
        new SpringOpaqueTokenIntrospector(
                introspectionUri, clientId, clientSecret);
```

The three-argument constructor still exists in 6.5 Javadoc but is `@Deprecated(since="6.5", forRemoval=true)`. The constructor Javadoc describes pre-URL-encoded client credentials; the 6.5+ builder explicitly takes **unencoded credentials**. Consequently, for credentials containing special characters such as `:`, `@`, `+`, `/`, or Unicode, verify your exact Spring Security version and **do not encode them a second time when using the builder**.

Older examples may appear fine when client IDs/secrets contain only simple characters, yet fail with **401 from the introspection endpoint** after rotating to a secret containing special characters. That is usually a sign of incorrect **Basic auth encoding**, not a revoked Bearer token.

## 10. Version 7.1+: `RestClientOpaqueTokenIntrospector`

Spring Security **7.1** Javadoc adds `RestClientOpaqueTokenIntrospector`, which uses Spring `RestClient` to call the introspection endpoint. This is a **new implementation option**, not a rename of the interface.

```java
// Spring Security 7.1+.
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String clientId,
        @Value("${introspection.client-secret}") String clientSecret) {

    return RestClientOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();
}
```

The code needs imports for `org.springframework.security.oauth2.server.resource.introspection.RestClientOpaqueTokenIntrospector` and the interface. If a 7.0 or 6.x project does not recognize this class, that is an **expected version difference**.

Brief comparison:

| Option | Underlying HTTP client | Version milestone | Notes |
| --- | --- | --- | --- |
| `NimbusOpaqueTokenIntrospector` | Historical Spring Security implementation tied to Nimbus SDK. | Available since 5.2; deprecated in 6.5. | Suitable for reading/maintaining legacy code; avoid for new code on 6.5+. |
| `SpringOpaqueTokenIntrospector` | Spring `RestOperations`/`RestTemplate`. | Available since 5.6; builder since 6.5. | Primary choice across many 6.5/7.0 setups. |
| `RestClientOpaqueTokenIntrospector` | Spring `RestClient`. | Available since 7.1. | Fits 7.1+ projects wanting `RestClient`-based HTTP configuration. |

**Do not use `RestClientOpaqueTokenIntrospector` in a WebFlux reactive chain.** For WebFlux, Spring Security provides **`ReactiveOpaqueTokenIntrospector`** and matching reactive implementations, distinct from the synchronous Servlet interface. This lesson focuses on Servlet.

## 11. Client credentials encoding: a key change when upgrading 6.5 → 7

When calling an RFC 7662 introspection endpoint, the Resource Server must authenticate to the Authorization Server. A common method is HTTP Basic. Representing `client_id` and `client_secret` in Basic auth when they contain URL-unsafe characters must follow protocol rules and library-version behavior.

Hypothetical credentials:

```text
client_id     = orders:api+introspection
client_secret = p@ss/word:with+chars
```

These are illustrative strings, not real secrets.

Key points from Spring Security migration docs:

- The old constructor `SpringOpaqueTokenIntrospector(uri, clientId, clientSecret)` was deprecated in 6.5, with Javadoc warnings regarding credential encoding.
- The builder `SpringOpaqueTokenIntrospector.withIntrospectionUri(uri).clientId(...).clientSecret(...).build()` added in 6.5 **accepts unencoded values and handles encoding**.
- The migration guide to 7.0 recommends using the builder because the new path encodes client credentials automatically per the RFC.
- If a project previously stored `clientId`/`clientSecret` percent-encoded in a secret manager for the old constructor, **do not pass that pre-encoded data into the builder** without verifying; doing so can cause double encoding and 401 introspection failures.

### 11.1. Double-encoding bug example

Suppose the logical secret contains `+`. When URL-encoded, `+` becomes `%2B`. If one layer encodes it to `%2B` and then the builder encodes it again, the string becomes `%252B`. The Authorization Server decodes once and sees `%2B` instead of `+`, causing Basic authentication to fail.

Never jump straight to **"the client secret is wrong"** when tokens are rejected. Check how credentials are stored, which implementation version performs encoding, and what the endpoint expects.

### 11.2. Safe migration strategy

1. Identify your exact Spring Security version and legacy implementation.
2. Check whether credentials in the secret manager are **raw** or **pre-encoded**.
3. Use the 6.5+/7.x builder with **raw client ID/secret** per contract.
4. Test credentials containing `+`, `:`, `@` if permitted by the issuer **against an HTTP mock endpoint**, without logging secrets.
5. Confirm the introspection server recognizes the client identity and returns valid JSON.
6. Roll out gradually while monitoring endpoint errors, 401/5xx rates, latency, and `active=false` ratios.

**Never print Basic Authorization headers, tokens, or secrets to stdout, test snapshots, or logs** just to inspect encoding. Assert on decoded values inside the mock server test or use placeholder test secrets.

## 12. Customizing the HTTP client and timeouts

Introspection is a **remote call**, so Authorization Server latency and availability directly affect the API.

`SpringOpaqueTokenIntrospector` offers a constructor taking `RestOperations`, suitable when configuring:

- Connect and read timeouts.
- Proxies, TLS trust, and mTLS if required by the Authorization Server.
- Controlled connection pooling/retries.
- Basic authentication or another contracted client authentication method.
- Sanitized metrics/tracing.

Illustrative approach using Spring Boot's `RestTemplateBuilder` (timeout method names can vary across Boot versions):

```java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        RestTemplateBuilder builder,
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String clientId,
        @Value("${introspection.client-secret}") String clientSecret) {

    RestOperations rest = builder
            .basicAuthentication(clientId, clientSecret)
            .setConnectTimeout(Duration.ofSeconds(3))
            .setReadTimeout(Duration.ofSeconds(3))
            .build();

    return new SpringOpaqueTokenIntrospector(uri, rest);
}
```

This snippet illustrates the builder style of certain Spring Boot 3.x lines; newer Boot releases may rename timeout configuration methods. **Check the API for your exact Boot version**, and ensure `RestOperations` authenticates to the introspection endpoint per contract. Never copy the `(uri, RestOperations)` constructor while forgetting to attach credentials to the HTTP client.

In Spring Security 7.1+, consider `RestClientOpaqueTokenIntrospector` with a customized `RestClient`. Whichever HTTP client you pick, keep URL handling, TLS, HTTP status handling, credential encoding, and response parsing consistent.

### 12.1. Timeouts are never a reason to fail open

If the introspection server is slow or temporarily unreachable, **never**:

```java
// WRONG: network failure yet accepts every token.
try {
    return delegate.introspect(token);
} catch (RuntimeException exception) {
    return makeAdminPrincipal();
}
```

The application must separate **invalid tokens** from **unavailable dependencies**, granting zero privileges to unverified tokens. You may apply circuit breakers, bounded retries, or caching aligned with your revocation SLA, with an explicit fail-closed policy when valid introspection data is unavailable.

## 13. Structure of the returned principal and authorities

The introspector returns an `OAuth2AuthenticatedPrincipal`; the provider builds `BearerTokenAuthentication` on successful authentication. Spring Security can derive authorities from `scope`:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders:read orders:export",
  "client_id": "web-client",
  "aud": ["orders-api"]
}
```

Logical result:

```text
Authentication type: BearerTokenAuthentication
Principal type:      OAuth2AuthenticatedPrincipal
principal.name:      typically from sub if provided
authorities:         SCOPE_orders:read
                     SCOPE_orders:export
```

Some newer Spring Security versions also include authorities representing **authentication factors**; therefore, avoid asserting `getAuthorities().size() == 2` as an invariant across versions. Instead, assert that **the required authorities are present** and unexpected sensitive privileges are absent.

### 13.1. Controller reading attributes

```java
@GetMapping("/api/me")
public Map<String, Object> me(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Map.of(
            "subject", principal.getAttribute("sub"),
            "client", principal.getAttribute("client_id"));
}
```

This is an illustrative snippet: `Map.of` rejects `null`, so production code must handle cases where the provider **omits `sub` or `client_id`**. Not every introspection response carries full metadata, nor should raw attributes be dumped directly to clients.

Using `BearerTokenAuthentication`:

```java
@GetMapping("/api/token-info")
public String tokenSubject(BearerTokenAuthentication authentication) {
    Object subject = authentication.getTokenAttributes().get("sub");
    return subject == null ? "unknown" : subject.toString();
}
```

Use this example only to learn principal access; production endpoints need a deliberate disclosure policy. **Never return the Bearer token**, client secret, or full introspection response on a public API.

### 13.2. Scope does not replace object-level authorization

`SCOPE_orders:read` authorizes the read action under policy. It does not prove the user may read **every order**. The API must still check owner/tenant/roles:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_orders:read') "
    + "and @orderPolicy.canRead(authentication, #orderId)")
public OrderDto readOrder(@P("orderId") UUID orderId) {
    // ...
}
```

`@orderPolicy` is an application-implemented bean that must read trusted identity and data. If an opaque-token principal lacks a user subject, never treat `email` or display names as an ownership key.

## 14. Adding resource/audience policy via a decorator

An introspection endpoint can return `active: true` for a token valid **within the issuer's ecosystem**, yet that token may not have been minted for **this API**. If the contract requires `aud=orders-api` and the introspection response includes `aud`, the API can validate it before trusting the principal.

Example decorator:

```java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
        .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
        .OpaqueTokenIntrospector;

public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        Object aud = principal.getAttribute("aud");
        boolean matches =
                (aud instanceof String value
                        && expectedAudience.equals(value))
                || (aud instanceof Collection<?> values
                        && values.contains(expectedAudience));

        if (!matches) {
            throw new BadOpaqueTokenException(
                    "Access token is not for this resource");
        }

        return principal;
    }
}
```

The decorator receives the principal from the delegate **only after the delegate has introspected successfully**. It performs no HTTP calls itself and builds no principal if the token is inactive.

Configuration usage:

```java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String clientId,
        @Value("${introspection.client-secret}") String clientSecret) {

    OpaqueTokenIntrospector delegate =
            SpringOpaqueTokenIntrospector
                    .withIntrospectionUri(uri)
                    .clientId(clientId)
                    .clientSecret(clientSecret)
                    .build();

    return new AudienceCheckingIntrospector(delegate, "orders-api");
}
```

This bean example uses the **Spring Security 6.5+** builder. On 6.4 or earlier, replace the delegate creation with the implementation supported by that version; **keep the decorator interface unchanged**.

### 14.1. Important limitations

- If the introspection endpoint **does not return `aud`**, an audience policy like this example will **reject** every token. Agree on resource-binding metadata/endpoints with the issuer rather than assuming every provider returns `aud`.
- If the issuer returns `aud` in a type other than string or collection of strings, write a parser/validator matching the contract; never coerce arbitrary objects to strings.
- `Collection.contains` is not a full authorization engine, only **one resource-identifier check**.
- Alongside audience, you may also need to verify `iss`, `client_id`, expiry, actor kind, tenant, and scopes per contract.
- If the remote introspection service already guarantees a token is **active only for the calling Resource Server** based on client credentials/context, duplicating the audience check may be unnecessary—provided that guarantee is documented and tested.

## 15. Custom authority mapping: never grant extra privileges from arbitrary metadata

An introspection response may carry scopes that the API wants to map into authorities under a custom contract. There are two distinct extension layers:

1. Customizing **`OpaqueTokenIntrospector`** to validate or transform `OAuth2AuthenticatedPrincipal`/attributes/authorities.
2. Customizing **`OpaqueTokenAuthenticationConverter`** to build the `Authentication` result from the introspected principal, where supported by your version.

In Spring Security 6.3+, `SpringOpaqueTokenIntrospector` has `setAuthenticationConverter(...)` taking a converter from `OAuth2TokenIntrospectionClaimAccessor` to `OAuth2AuthenticatedPrincipal`. Do not confuse this setter with `OpaqueTokenAuthenticationConverter` at the provider layer: **they handle two different steps**.

### 15.1. Decorator pattern keeping only allowed authorities

To avoid accepting out-of-contract scopes, construct a new principal from the introspected one:

```java
OpaqueTokenIntrospector rawIntrospector = /* trusted delegate */;

OpaqueTokenIntrospector constrained = token -> {
    OAuth2AuthenticatedPrincipal principal =
            rawIntrospector.introspect(token);

    Set<String> allowed = Set.of(
            "SCOPE_orders:read", "SCOPE_orders:write");

    List<GrantedAuthority> authorities = principal.getAuthorities()
            .stream()
            .filter(a -> allowed.contains(a.getAuthority()))
            .toList();

    return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities);
};
```

This snippet is conceptual and needs imports for `DefaultOAuth2AuthenticatedPrincipal`, `GrantedAuthority`, `Set`, and `List`. Because newer versions may add authentication-factor authorities, filtering out **every** authority outside an allowlist can interfere with security policies; carefully decide which authorities to retain or strip per version contract. If the intent is to **reject tokens carrying out-of-contract scopes**, throw an exception rather than silently filtering them out.

Never extract arbitrary `roles` or `permissions` from an introspection response to auto-grant `ROLE_ADMIN`. Only map verified data using an explicit allowlist and authorization policy.

### 15.2. When both `scope` and `roles` are present

```json
{
  "active": true,
  "scope": "orders:read",
  "roles": ["ADMIN"]
}
```

The application must define:

- Is `roles` a trusted claim emitted by the issuer?
- Does this role belong to **`orders-api`** or to another application?
- Which authority does it map to, e.g., `ROLE_ADMIN` or `ORDER_ADMIN`?
- May scopes and roles be combined within the same authorization rule?

Never treat `"ADMIN"` as system-wide administrative access simply because introspection returned that field. That mistake is **privilege escalation via authority mapping**, not an HTTP client or introspection version bug.

## 16. Introspection with JWTs: not only for unreadable strings

Opaque token support in Spring Security really selects **token verification via introspection**, without requiring the token string to lack dots.

Suppose an issuer mints signed JWTs, yet the business requires **server-side revocation checks** on every request. The API can configure:

```java
.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()))
```

and forward the entire JWT string to the introspection endpoint. In that mode:

- `JwtDecoder` is not the decision component along the chosen opaque path.
- Principal/authorities come from the introspection response.
- Even though the string has JWT headers/payloads, **never parse unverified payloads directly** to grant permissions.
- If you want both local signature verification and introspection, that is a **custom design** requiring explicit ordering, failure handling, performance budgeting, and contract—it does not happen automatically when enabling `opaqueToken()`.

**Never use token string formatting as a "security router" based on dots or length** without an explicit policy. When a system genuinely supports two token mechanisms, separate them by filter chain/client/issuer or use a securely designed resolver.

## 17. Performance, revocation, and caching

With uncached introspection, each Bearer request triggers a call to the Authorization Server or introspection service. This lets the Resource Server observe revocation relatively quickly, at the cost of a runtime dependency:

```text
API latency ≈ business processing + introspection latency + other network overhead
```

High-throughput systems may consider caching introspection results:

| Approach | Benefit | Risk |
| --- | --- | --- |
| No cache | Revocations can be reflected on every endpoint call. | Increases latency/AS load; exposed to network failures. |
| Short-lived cache | Reduces remote calls/latency. | Newly revoked tokens may still be accepted during the TTL window. |
| Long-lived cache | Major load reduction. | Undermines rapid revocation; depends on expiry/profile. |
| Fail-open cache when AS is down | Appears to improve availability. | **Dangerous:** unverified tokens may still gain access. |

If caching is used, you must:

1. Bound TTL by the token's **remaining lifetime** and revocation SLA; never cache past `exp` if present.
2. Cache only **fully validated `active=true` results**, handling inactive/errors separately per policy.
3. Protect the cache as credential-sensitive data; never expose raw tokens as keys in logs/metrics.
4. Use a secure keyed hash or non-exposing key abstraction; account for collisions, invalidation, and policy version/tenant scope.
5. Account for role/tenant changes occurring during the cache window.
6. Guard against cache stampedes, retry storms, and introspection endpoint downtime.

**There is no single "always right" TTL for every system.** Financial transaction tokens may demand near-real-time revocation; lower-sensitivity APIs may tolerate bounded staleness by contract.

## 18. Error classification: invalid token vs. introspection service unavailable

| Event | Where does it happen? | Interpretation | API response / investigation |
| --- | --- | --- | --- |
| Client sends no Bearer token | HTTP Bearer filter | Missing credential. | Protected endpoints typically return **401**. |
| Introspection returns `{"active":false}` | Issuer status check | Token not accepted. | Typically **401 `invalid_token`**. |
| Introspection returns `active=true` but lacks `orders:read` | Authorization | Token accepted but lacks permission. | Typically **403 Forbidden**. |
| Introspection returns `active=true` but `aud` is for another API | Resource policy | Token not meant for this API. | Reject authentication, usually 401 when enforced in introspector. |
| Introspection endpoint returns 401 due to bad client secret | Resource Server → AS | **Resource Server credentials misconfigured.** | Never accept token; alert operations. |
| HTTP 503/timeout during introspection | AS/network dependency | Cannot verify token. | Fail closed; classify service outage, 5xx/503 may fit depending on handler. |
| Malformed introspection response | API/AS protocol | No trustworthy verification result. | Reject and log controlled protocol error. |
| Introspected token lacks required metadata | Issuer/API contract | Insufficient data to evaluate permissions. | Reject per policy; fix issuer contract. |
| Resource Server mistakenly configured `jwt()` instead of `opaqueToken()` | Security config | Wrong authentication mechanism. | Verify filter chain and active introspector/decoder. |

In production, never expose internal messages like `client_secret rejected` or internal introspection URLs in `WWW-Authenticate`. Clients generally only need safe Bearer errors; internal logs and categorized metrics help operators distinguish invalid tokens from outages.

### 18.1. What to monitor

- Introspection request count, latency percentiles, and timeout rate.
- `active=false` rate, separated from introspection HTTP 4xx/5xx responses.
- Client credential/TLS authentication failures toward the issuer.
- Cache hit/miss ratio, TTL, and staleness relative to SLA.
- API 401/403 responses by route and normalized cause.
- Impact during introspection client secret rotation.

Never use raw access tokens, Basic headers, or secrets as metric labels. Untrusted input values can cause high cardinality or credential leaks.

## 19. Testing by version and responsibility layer

### 19.1. Unit tests for decorators/policies

For `AudienceCheckingIntrospector` in section 14, a fake delegate can test policy without HTTP:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
        .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
        .OpaqueTokenIntrospector;

class AudienceCheckingIntrospectorTest {

    private OpaqueTokenIntrospector fake(String audience) {
        return token -> new DefaultOAuth2AuthenticatedPrincipal(
                "user-123",
                Map.of(
                        "sub", "user-123",
                        "aud", List.of(audience)),
                List.of(new SimpleGrantedAuthority(
                        "SCOPE_orders:read")));
    }

    @Test
    void acceptsExpectedAudience() {
        var guard = new AudienceCheckingIntrospector(
                fake("orders-api"), "orders-api");

        OAuth2AuthenticatedPrincipal principal =
                guard.introspect("test-token");

        assertEquals("user-123", principal.getName());
    }

    @Test
    void deniesOtherResourceAudience() {
        var guard = new AudienceCheckingIntrospector(
                fake("payments-api"), "orders-api");

        assertThrows(BadOpaqueTokenException.class,
                () -> guard.introspect("test-token"));
    }
}
```

This is a unit test for the **decorator**; it does not prove HTTP introspection or client credential verification. The fake delegate always returns a principal and has no `active=false` logic; URL/response verification must be tested at another layer.

### 19.2. HTTP client tests with a mocked introspection endpoint

With `SpringOpaqueTokenIntrospector` or `RestClientOpaqueTokenIntrospector` for your version, verify:

1. POST goes to the **configured introspection URI**, not a URL declared inside a Bearer token.
2. `Content-Type: application/x-www-form-urlencoded` and the `token` parameter are sent intact.
3. Client authentication matches the contract and **client IDs/secrets with special characters are not double-encoded**.
4. `active=true` responses create principals with the right attributes and scopes.
5. `active=false` responses are rejected.
6. HTTP 401 from wrong introspection client credentials is classified separately from inactive tokens.
7. HTTP 429/5xx, timeouts, malformed JSON, or TLS failures **never create an authenticated principal**.
8. No sensitive tokens/secrets appear in logs, exception responses, or test snapshots.

Use **WireMock**, **MockWebServer**, or an equivalent test HTTP server to inspect the wire format. When testing secrets, assert only inside the mock server or protected environment, never logging real values.

### 19.3. Integration tests through the Spring Security filter chain

Suppose the API has an endpoint:

```java
@GetMapping("/api/orders")
List<OrderDto> orders() {
    return orderService.listVisibleOrders();
}
```

Integration tests can inject a test introspector via `@TestConfiguration`/test bean or use a mocked introspection endpoint:

```java
mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-active-read"))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-active-no-scope"))
        .andExpect(status().isForbidden());

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-inactive"))
        .andExpect(status().isUnauthorized());
```

This example assumes the test introspector or mock endpoint **actually** classifies those three tokens accordingly, the endpoint returns 200 when authorized, and the Spring Security filter chain is active. Add project-specific test setup/beans/service mocks.

**Do not confuse this with**:

```java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))));
```

Spring Security Test's `jwt()` injects a mocked `Authentication` and **bypasses `OpaqueTokenIntrospector`**. It is useful for testing authorization rules, yet proves nothing about whether introspection requests were sent or `active` was checked.

### 19.4. Version compatibility matrix

| Item | 5.2–5.5 | 5.6–6.4 | 6.5–7.0 | 7.1+ |
| --- | --- | --- | --- | --- |
| `OpaqueTokenIntrospector` interface | Yes | Yes | Yes | Yes |
| `NimbusOpaqueTokenIntrospector` | Yes | Yes | May exist, deprecated in 6.5 | Check exact API; do not choose by default for new code |
| `SpringOpaqueTokenIntrospector` | Unavailable before 5.6 | Yes | Yes | Yes |
| `SpringOpaqueTokenIntrospector.Builder` | No | No | Yes | Yes |
| Non-deprecated three-string Spring constructor | N/A | Available per version API | Deprecated since 6.5 | Deprecated/subject to removal per API |
| `RestClientOpaqueTokenIntrospector` | No | No | No | Available from 7.1 |
| Special-character credential encoding test | Needed | Needed | **Especially critical when migrating to 7** | Needed |

This matrix is based on public API milestones rather than assuming which implementation Boot picks in every minor release. The most reliable check is inspecting the **resolved `spring-security-oauth2-resource-server` version**, the exact Javadoc for that line, and wire tests against your real issuer.

## 20. Anti-patterns to avoid

### 20.1. Treating an opaque token as a broken JWT

Opaque tokens do not need three JWS segments. When an issuer mints opaque access tokens, use valid introspection; never attempt to Base64URL-decode the string and manually build a `JwtAuthenticationToken`.

### 20.2. Checking only HTTP status 200 from introspection

RFC 7662 can return 200 with `{"active":false}`. Succeed only when **`active=true`** and resource/claims policies pass.

### 20.3. Putting the client secret on the frontend

Introspection client credentials belong to the Resource Server/trusted backend. Embedding them in an SPA/mobile app or frontend config lets third parties call the introspection endpoint unauthorized.

### 20.4. Switching from Nimbus to Spring while ignoring URL encoding

Legacy constructors and newer builders have different credential encoding semantics. After upgrading, bad encoding can make every introspection request return HTTP 401. Check raw vs. pre-encoded client IDs/secrets and test wire behavior.

### 20.5. Copying builders without checking versions

`SpringOpaqueTokenIntrospector.withIntrospectionUri` is a 6.5+ API; `RestClientOpaqueTokenIntrospector` is 7.1+. Never copy 7.1 code into a 6.3 project and "fix" compilation by mixing mismatched JAR versions.

### 20.6. Returning a principal when the introspection service times out

A timeout means **unverified**. Never grant permissions inside a catch block; fail closed and address availability/caching under control.

### 20.7. Treating `active=true` as enough for every API

A token may be active yet issued for another resource. When the contract demands resource binding, verify `aud` or an equivalent policy, alongside scopes, tenants, and ownership.

### 20.8. Using email/name to grant permissions

Introspection may return `email`, `name`, or `preferred_username`; these are usually mutable metadata, not immutable principal keys. Use an `(iss, sub)` identity contract or a provider-verified internal mapping.

### 20.9. Calling `.authenticated()` and assuming the endpoint is protected

`.authenticated()` only verifies a valid authentication; if an endpoint requires `orders:read`, enforce `SCOPE_orders:read` or a custom authorization policy.

### 20.10. Caching active results indefinitely

Unbounded caching of active tokens defeats revocation and expiration. When caching is needed, enforce bounded TTLs, assess risk, and test tokens revoked while cached.

## 21. Workflow for choosing an implementation in your project

When configuring an opaque Resource Server or upgrading from an older tutorial, walk through these decisions:

```mermaid
flowchart TD
    START["Bearer token needs introspection"] --> V{"Spring Security line?"}
    V -->|"5.2–5.5"| NIM["Legacy NimbusOpaqueTokenIntrospector API"]
    V -->|"5.6–6.4"| SPR["SpringOpaqueTokenIntrospector<br/>constructor/RestOperations"]
    V -->|"6.5–7.0"| BUILDER["SpringOpaqueTokenIntrospector<br/>withIntrospectionUri builder"]
    V -->|"7.1+"| CHOICE{"Prefer RestClient?"}
    CHOICE -- "Yes" --> REST["RestClientOpaqueTokenIntrospector"]
    CHOICE -- "No / RestOperations" --> BUILDER
    NIM --> POLICY["Configure credentials, active/status, resource policy"]
    SPR --> POLICY
    BUILDER --> POLICY
    REST --> POLICY
    POLICY --> TEST["Test inactive/active/error/encoding/scopes/HTTP"]
    TEST --> DEPLOY["Deploy, monitor, enforce revocation SLA"]
```

This diagram does not claim "older classes always break," rather it guides choosing **available, recommended APIs per version**. When Spring Boot properties satisfy all requirements, you may not need to pick a class manually; Boot/Spring Security handles the wiring.

### 21.1. Pre-merge configuration checklist

1. Which exact **version** of the Spring Security Resource Server dependency is resolved?
2. Are you using **Servlet** or WebFlux—synchronous or reactive interfaces?
3. Does the issuer support an RFC 7662 introspection endpoint?
4. Which authentication method does the Resource Server use toward the endpoint: Basic, mTLS, or another contract?
5. Are Client ID/secret stored **raw** or **pre-encoded**?
6. Beyond `active` and scope, what `aud` or resource policy must be checked?
7. In what format are scopes returned, and how are they converted to authorities?
8. Do you need custom `RestOperations`, `RestClient`, timeouts, or a proxy?
9. When the endpoint is unreachable, does the API enforce fail-closed behavior and clear infrastructure error responses?
10. Does any token introspection caching align with revocation requirements?
11. Is every `SecurityFilterChain` using the intended introspector rather than accidentally using a JWT decoder?
12. Do tests exercise the **real Bearer filter + introspector path**, rather than relying solely on `jwt()` mocks?

## 22. Practical scenarios

### A. A Spring Security 6.3 project reports `withIntrospectionUri` not found

The code was copied from 6.5+ docs with the builder. On 6.3, use a `SpringOpaqueTokenIntrospector` constructor/`RestOperations` supported by that version, or upgrade dependencies consistently. Never create a fake class of the same name to make code compile.

### B. A 6.5 project still uses Nimbus and shows deprecation warnings

This warning signals a needed API migration review, not broken token validation by itself. Prefer the `SpringOpaqueTokenIntrospector` builder where appropriate, and re-verify Basic credential encoding, active responses, scopes, and timeouts against a mock introspection server.

### C. Upgrading to 7.0 causes the introspection endpoint to return 401

If user JWT/opaque tokens previously worked yet the AS now consistently returns 401 when **the Resource Server calls introspection**, inspect client ID/secret, percent-encoding, and double-encoding before assuming all user tokens became invalid.

### D. Spring Security 7.1 wanting to use `RestClient`

Pick `RestClientOpaqueTokenIntrospector` and configure `RestClient` if supported by your version. Keep application code dependent on `OpaqueTokenIntrospector` and test wiring; never alter scope or audience rules merely because the HTTP client changed.

### E. Tokens are JWTs, yet immediate revocation checks are required

The API can use `opaqueToken()` to introspect entire JWT strings with the AS. This places token validity decisions on the AS and adds latency; design availability and caching per SLA instead of assuming un-introspected JWT claims alone.

### F. `active=true` yet scope is missing

Spring Security can authenticate the token and build a principal without `SCOPE_orders:write`. An endpoint requiring write must return 403 per authorization policy, never "upgrading" authorities inside the introspector to let the client through.

### G. `active=true` yet the token belongs to another API

If metadata includes `aud=["payments-api"]` while the API expects `orders-api`, the Resource Server's decorator or policy must reject it per contract. Never accept a token solely because it shares an issuer and has `active=true`.

### H. Introspection service temporarily returns 503

The token cannot be verified. The Resource Server must not fail open. Configure timeouts, alerts, and circuit breakers/caching per SLA, classifying this as a **dependent authentication service outage** rather than labeling all tokens revoked.

## 23. Self-check questions

**1. Is `OpaqueTokenIntrospector` an interface or an implementation?** It is an interface defining `introspect(String token)` returning `OAuth2AuthenticatedPrincipal`.

**2. How does `SpringOpaqueTokenIntrospector` differ from `OpaqueTokenIntrospector`?** It is a concrete implementation using HTTP introspection; business code should depend on the interface.

**3. Since which version has `SpringOpaqueTokenIntrospector` existed?** Per Javadoc: Spring Security **5.6**.

**4. Since when has the `withIntrospectionUri` builder existed?** Spring Security **6.5**; do not copy builder examples directly into 6.4.

**5. When was the `SpringOpaqueTokenIntrospector(uri,id,secret)` constructor deprecated?** Since **6.5**; the Javadoc recommends the builder.

**6. Is `NimbusOpaqueTokenIntrospector` the recommended API for 6.5?** No. The 6.5 Javadoc marks it deprecated and recommends the Spring implementation.

**7. Since which version has `RestClientOpaqueTokenIntrospector` existed?** Since **7.1**, using Spring `RestClient`.

**8. Does the 6.5+ builder expect raw or pre-percent-encoded client ID/secret?** It expects **raw/unencoded** values; the builder handles encoding per Javadoc. Avoid double encoding.

**9. What if the introspection endpoint returns HTTP 200 with `active=false`?** The token is rejected; HTTP status 200 only means the introspection HTTP request was processed.

**10. Is an `active=true` token automatically authorized to call every API?** No. You must still check resource/audience, scopes, and object-level policies.

**11. When introspection times out, may a default principal be granted?** No. Fail closed and handle the dependency outage per policy.

**12. Is `JwtDecoder` automatically invoked when configuring `opaqueToken()`?** Not along the default opaque Resource Server authentication path; this choice relies on introspection even if the token string has JWT formatting.

**13. Does `MockMvc jwt()` test HTTP introspection?** No. It bypasses the introspector with a mocked authentication.

**14. Must an opaque token be a random string with no dots?** No. Spring's opaque path can forward JWTs to the introspection endpoint too; "opaque" describes **how the Resource Server verifies** the token in this setup.

**15. What is the biggest risk when caching introspection?** Stale active results can continue to be accepted after revocation or permission changes; bounded TTLs and proper cache policies are required.

## 24. Official documentation and standards

- **RFC 7662 — OAuth 2.0 Token Introspection:** https://www.rfc-editor.org/rfc/rfc7662 — `active`, introspection requests and responses.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** https://www.rfc-editor.org/rfc/rfc6750 — sending Bearer credentials and `invalid_token`/`insufficient_scope` errors.
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server Opaque Token:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security 6.5 API — `OpaqueTokenIntrospector`:** https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html
- **Spring Security 6.5 API — `SpringOpaqueTokenIntrospector`:** https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html
- **Spring Security 6.5 API — `SpringOpaqueTokenIntrospector.Builder`:** https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.Builder.html
- **Spring Security 6.5 API — `NimbusOpaqueTokenIntrospector`:** https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/server/resource/introspection/NimbusOpaqueTokenIntrospector.html
- **Spring Security 6.5 Migration to 7 — OAuth 2.0 credential encoding:** https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html
- **Spring Security 7.1 API — `RestClientOpaqueTokenIntrospector`:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/RestClientOpaqueTokenIntrospector.html
- **Spring Security — Servlet Architecture:** https://docs.spring.io/spring-security/reference/servlet/architecture.html — `FilterChainProxy`, `SecurityFilterChain`, authentication, and authorization filters.

**Conclusion:** `OpaqueTokenIntrospector` is the stable **token-verification contract**; `SpringOpaqueTokenIntrospector` is the HTTP implementation supported since Spring Security 5.6 with a convenient builder since 6.5; `NimbusOpaqueTokenIntrospector` is the legacy option deprecated in 6.5; and `RestClientOpaqueTokenIntrospector` arrived in 7.1. When upgrading, verify **exact dependency versions, introspection client credential encoding, HTTP client behavior, `active` handling, resource/audience policies, scope mapping, timeouts, and tests**. Changing implementations must never alter the security boundary: **a token not successfully introspected and validated against the contract can never become an authorized API principal**.
