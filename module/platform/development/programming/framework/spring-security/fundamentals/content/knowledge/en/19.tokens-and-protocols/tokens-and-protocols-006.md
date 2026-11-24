# Opaque Tokens and Validity Verification via Introspection

## 1. Lesson Objectives

This lesson belongs to the **Tokens and Protocols** group of **Spring Security - Fundamentals**. When an API receives `Authorization: Bearer ...`, it must determine whether the token is still valid, issued for the right resource, and permitted to execute the request. One verification approach is **OAuth 2.0 Token Introspection**: the Resource Server asks the Authorization Server about the token's status and attributes.

After this lesson, you will be able to:

1. Explain what an **opaque access token** is, why the Resource Server does not decode it directly like a JWT, and why permissions cannot be inferred from the visible token string.
2. Describe the roles of **Client**, **Authorization Server (AS)**, **Resource Server (RS)**, and the introspection endpoint per **RFC 7662**.
3. Distinguish `active: true`, `active: false`, RS authentication failures when calling introspection, scope errors, and introspection service errors.
4. Understand the form-encoded `POST` request to the introspection endpoint, how the RS authenticates with the AS, and the attributes `scope`, `sub`, `client_id`, `aud`, `iss`, `exp`.
5. Configure Spring Boot / Spring Security Servlet as an OAuth2 Resource Server using opaque-token introspection, map scopes to `SCOPE_...`, and protect endpoints.
6. Run a Java 17 + Spring Boot 3.5.12 example, verify HTTP 200/401/403, and distinguish real HTTP testing from merely mocking an introspector.
7. Evaluate revocation, caching, latency, availability, TLS, token leakage, audience validation, and differences between opaque introspection and local JWT verification.

**Scope:** runnable examples use **Spring MVC/Servlet** (`HttpSecurity`, `SecurityFilterChain`, `OpaqueTokenIntrospector`). Spring WebFlux has its own `ReactiveOpaqueTokenIntrospector`, `ServerHttpSecurity`, and reactive security context. This lesson does not require you to build a production Authorization Server yourself.

## 2. What Is an Opaque Token?

An **opaque token** is a value from which the recipient must not assume it can directly read user/permission details. It can be a random string, a reference key to a record on the Authorization Server, or an arbitrary format whose structure the Resource Server does not know. Illustrative example:

```text
Authorization: Bearer 7CnV0aQ9w1...random...
```

The ellipsis is illustrative only, not a real token, and this string must never be used to protect a system.

**"Opaque" is from the Resource Server's perspective:** the API application does not read the token to extract `sub`, `scope`, or `exp`. It sends the token to a trusted service and receives issuer-confirmed attributes. A token can even look like a JWT yet still be configured for **verification via introspection**; the verification method and token format are two separate decisions.

### Who Does What?

| Component | Responsibility |
| --- | --- |
| **Client** (web/mobile/service) | Holds a valid access token and sends it in requests to the API |
| **Authorization Server / IdP** | Issues and manages token validity/revocation; provides the introspection endpoint |
| **Resource Server** | Receives bearer tokens, validates them via introspection, checks scopes and endpoint permissions |
| **Introspection endpoint** | Returns `active` and token attributes within what the RS is permitted to see |
| **User / subject** | May be the subject represented by the token, though an OAuth2 client-credentials token might not represent a specific user |

An opaque token differs from a **session ID** in usage context: a session ID typically points to a web application's `HttpSession`; an opaque OAuth2 access token is typically checked by an RS via an AS/introspection under OAuth2. Both may be unguessable strings, yet their **protocol, trust target, scopes, and management mechanisms** differ.

**A bearer token is a secret:** anyone holding a valid token can attempt to use it within the token's allowed scope. Treat tokens as credentials—do not log them, embed them in URLs, or send them to untrusted services.

## 3. Validity Verification Flow via RFC 7662

A resource-protected request follows this path:

```text
Client                         Resource Server                Authorization Server
  │                                  │                                │
  │ GET /api/orders                  │                                │
  │ Authorization: Bearer T          │                                │
  ├─────────────────────────────────>│                                │
  │                                  │ POST /introspect               │
  │                                  │ Authorization: Basic RS creds  │
  │                                  │ Content-Type: application/     │
  │                                  │   x-www-form-urlencoded        │
  │                                  │ token=T                        │
  │                                  ├───────────────────────────────>│
  │                                  │                                │ check T's
  │                                  │        HTTP 200                │ status,
  │                                  │ {active:true, scope, sub,...}  │ scopes & policy
  │                                  │<───────────────────────────────┤
  │                                  │                                │
  │                                  │ build request Authentication   │
  │                                  │ check SCOPE_orders.read        │
  │                                  │                                │
  │  HTTP 200 (if allowed)           │                                │
  │<─────────────────────────────────┤                                │
```

**Key points:**
- The Client sends the token to the **Resource Server** in `Authorization: Bearer ...`.
- The Resource Server sends the token to the **introspection endpoint** in a separate request. The RS must be trusted by the AS and authenticated per policy; a common example is HTTP Basic using the **Resource Server's client ID/secret**. This is **not** a user's password.
- The AS returns JSON containing `active`. The RS turns an accepted result into the **current request's** `Authentication`, then performs authorization such as `hasAuthority("SCOPE_orders.read")`.
- Introspection is the **token validity verification** step. `active: true` does not automatically permit every API; the application still needs to check scope, audience/resource, tenant, or business permissions.
- Never configure "allow on introspection error" (*fail open*). If the RS cannot verify a token, it must never assume the token is valid.

### Why Is a Separate Endpoint Needed?

The RS usually lacks the information to verify an opaque token itself. Only the AS or a verification service trusted by the AS knows whether the token was issued, has expired, was revoked, or was blocked by policy. RFC 7662 provides a standard way to ask: **is the token currently active, and which attributes may be disclosed to this RS?**

## 4. The Introspection Request: HTTP and Caller Permissions

Example communication **between the Resource Server and Authorization Server**, not between a browser and the API:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.test
Authorization: Basic <base64-resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>&token_type_hint=access_token
```

This is a **protocol template**; items in `<...>` are descriptive placeholders, not real credentials. `token_type_hint` is an **optional** field hinting to help the AS optimize lookup; it does not prove the token is an access token.

Requirements to understand accurately:

1. RFC 7662 uses **HTTP POST** with the `token` parameter in an `application/x-www-form-urlencoded` body. Do not put access tokens in URL query parameters, as URLs are frequently logged or stored in history/proxies.
2. The introspection endpoint requires **TLS and certificate verification** in real deployments. The `http://127.0.0.1` example below is solely for local learning.
3. The RS must prove it is authorized to query the endpoint, typically via client credentials. An AS may enforce other client authentication mechanisms per policy.
4. The AS may restrict an RS to introspecting only tokens that the RS is permitted to know about, preventing arbitrary services from probing token status.
5. Introspection responses may contain sensitive data (`sub`, username, scopes, tenant...). The RS must keep them private, avoiding returning the full response to clients or logging it.
6. A 401 at the **introspection endpoint** when the **RS's credentials are invalid** differs from a 401 that the **API returns to the Client** when a bearer token is invalid.

### Two Commonly Confused Cases

**The token is no longer active**, yet the RS is authorized to call the endpoint:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

This is a **valid result of the introspection call**, not an HTTP error from the introspection service. The AS should not include `reason=revoked`, `reason=not_found`, or other details for inactive tokens, as doing so can leak token state. RFC 7662 recommends a minimal response.

**The RS calls introspection with invalid client credentials:**

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"error":"invalid_client"}
```

This is an **authentication error of the introspection caller**, not an indication that the target token is "inactive". The RS must handle it as a verification failure and never default to granting access.

### Is the Introspection Endpoint Public?

"Public as a URL" does not mean public data. Callers must be **authenticated and authorized**; arbitrary Internet clients must not be allowed to submit tokens to probe metadata. Even an introspection response with `active:true` should never be displayed to unauthenticated end users via a debug endpoint.

## 5. Meaning of Fields in the Returned JSON

Under RFC 7662, `active` is the core field. Other fields depend on the token, authorization server, and RS permissions.

**Active token example:**

```json
{
  "active": true,
  "sub": "alice",
  "client_id": "orders-web",
  "scope": "orders.read profile.read",
  "token_type": "Bearer",
  "aud": ["orders-api"],
  "iss": "https://idp.example.test",
  "exp": 1910000000,
  "iat": 1909996400
}
```

The `exp`/`iat` numbers illustrate Unix timestamp seconds; they **do not** imply the token above is real or active at the time you read this. Meanings:

| Attribute | Meaning | Important Checks |
| --- | --- | --- |
| `active` | AS confirms the token is currently accepted under AS policy | If missing/false/invalid, do not grant access |
| `sub` | Subject the token represents, if any | Not always a display username; client-credentials tokens may differ |
| `client_id` | Client that was issued the token | Is it a valid client for this use case? |
| `scope` | Granted scopes, typically a space-separated string | Map to authorities, enforce least privilege |
| `token_type` | Token type (typically Bearer) | Does not replace validation decisions |
| `aud` | Intended audience/resource | Reject tokens issued for another API |
| `iss` | Token issuer | Does it belong to a trusted issuer/AS per policy? |
| `exp` | Expiration in epoch seconds | Combine with `active` and AS expiration policy |
| `iat` | Issuance time | Used if business/policy checks token age |
| `nbf` | Not valid before a given time | Enforce appropriate policy if returned by the AS |

**Do not over-infer:** `active: true` means the AS confirms the token is active under AS policy and the RS is permitted to ask. It **does not by itself prove** the token has `orders.read`, has the right `aud` for this API, or has permission to read order ID 123 of the current tenant.

**Audience is especially critical.** An access token for `billing-api` should not be accepted at `orders-api` just because both share the same AS. Spring Security by default may map scopes and rely on the AS reporting `active`; specific audience/issuer/tenant checks **must be explicitly designed and verified**, never assuming every introspection field was checked for your application.

### `active: false` Can Have Many Causes

- The token was never issued or is a random string.
- The token has expired.
- The token was revoked, or its session/consent was invalidated per policy.
- The token is not intended for the introspecting RS and the AS refuses to disclose details.
- The token is no longer valid under another AS policy.

Because all of these can produce `{"active":false}`, the RS **must not guess a specific reason** from that JSON alone.

## 6. How Do Opaque Introspection and JWT Differ?

| Criterion | Opaque Token + Introspection | JWT + Local Validation |
| --- | --- | --- |
| How is the token read? | RS does not assume it can read it; asks AS | RS decodes claims and verifies signature/validity locally |
| Status at request time | Can learn revocation quickly from AS if introspected per call | Self-contained JWTs are typically accepted until `exp` unless another revocation mechanism exists |
| Latency per request | May add network round-trip, TLS, AS processing | Typically no AS call needed per request |
| Availability | Depends on introspection endpoint and network (if uncached) | Depends on keys/JWK refresh and policy, yet processing is usually local |
| Permissions/claims | Received from AS response and enforced by RS | Claims live in the token and do not update before expiration |
| Data exposure from token | Opaque tokens do not expose claims to the holder | JWT payloads are usually readable even when signed |
| Caching | Introspection results can be cached with stale-state trade-off | Keys/validation metadata can be cached |
| Best suited for | Need centralized revocation/control, small tokens, dynamic metadata | Want local verification and reduced AS call dependency |

**Do not conflate:** you can still use introspection with JWTs to check status/revocation; Spring Security's opaque-token support does not require the token string "not to be a JWT". Conversely, an opaque token does not guarantee fast revocation if you cache results for too long.

### A Valid JWT Signature Does Not Mean the Token Is Still Permitted

A JWT with a valid signature can be revoked by AS policy before `exp`. If an RS only performs local verification, it will not know about that revocation unless additional design is added. Introspection gives the RS a way to ask the AS about current status, at the cost of network/availability dependency and potential latency.

## 7. How Does Spring Security Handle Opaque Bearer Tokens?

With Spring Boot Servlet, the key components are:

- `BearerTokenAuthenticationFilter`: extracts the bearer token from the request via the configured resolver.
- `OpaqueTokenAuthenticationProvider`: uses `OpaqueTokenIntrospector` to validate the token.
- `SpringOpaqueTokenIntrospector` (or variants using `RestClient`/custom logic): calls the introspection endpoint using the RS's credentials.
- `OAuth2AuthenticatedPrincipal`: holds attributes and granted authorities after introspection.
- `BearerTokenAuthentication`: the `Authentication` representing an accepted bearer token.
- `AuthorizationFilter` with `authorizeHttpRequests`: checks permissions after authentication.

High-level flow:

```text
GET /api/orders
Authorization: Bearer read-token
       │
       ▼
BearerTokenAuthenticationFilter
       │ extracts token
       ▼
OpaqueTokenIntrospector.introspect("read-token")
       │ POST /introspect
       │ checks active + metadata
       ▼
OAuth2AuthenticatedPrincipal
       │ sub=alice, scope=orders.read
       ▼
BearerTokenAuthentication
       │ authorities=[SCOPE_orders.read]
       ▼
authorizeHttpRequests
       ├─ has SCOPE_orders.read → allow
       └─ missing scope → deny
```

### Mapping Scopes to Authorities

When introspection returns `"scope": "orders.read orders.write"`, Spring Security by default maps them to:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Accordingly, the matching rule is:

```java
.requestMatchers("/api/orders").hasAuthority("SCOPE_orders.read")
```

**This is a fragment** and must sit inside `authorizeHttpRequests`. `hasRole("ADMIN")` is **not automatically equivalent** to `hasAuthority("SCOPE_orders.read")`. Roles and OAuth2 scopes are two permission systems; they can be integrated, but the mapping must be explicit.

### Distinguishing 401 and 403 for API Callers

| Request | Typical Result | Reason |
| --- | --- | --- |
| No Bearer sent | 401 | Unauthenticated at the API |
| Random token, introspection `active:false` | 401 | Invalid Bearer token |
| Revoked/expired token, AS returns inactive | 401 | Authentication rejected |
| Active token, missing `orders.read` | 403 | Authenticated but missing authority |
| Active token, has `orders.read` | 200 | Passes endpoint authorization |
| Introspection service down/timeout | Access denied; final status depends on config/error handling | Never fail open |
| Wrong RS client credentials | Introspection endpoint 401; API must not treat token as valid | Service-to-service config/trust failure |

**Do not hard-assume 503 or 401 for every network introspection error.** Spring Security classifies exceptions differently and supports custom handlers; verify actual results on your target version. What is mandatory is **never allowing sensitive requests simply because the AS is unresponsive**.

## 8. Minimal Spring Boot Configuration with a Real AS

When a real Authorization Server provides an introspection endpoint, typical production configuration has three properties:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://idp.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=orders-resource-server
spring.security.oauth2.resourceserver.opaquetoken.client-secret=REPLACE_VIA_SECRET_MANAGER
```

The hosts/values here **only illustrate configuration**, not real endpoints/certificates/credentials; never commit real client secrets to source control. In production, supply client secrets via a secret manager or appropriate environment variables configured per environment, enable TLS, control DNS/egress proxies, and trust the right CA.

Java application configuration:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders").hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults()))
        .build();
}
```

This is a **fragment**: it needs `@Configuration`, `@Bean`, proper imports, Resource Server dependencies, and policies for other endpoints. Once you declare a custom `SecurityFilterChain`, Spring Boot no longer creates the default chain for you; define appropriate public/protected/fallback routes.

### Dependencies

With Spring Boot, use the starter:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
```

The starter pulls in the required resource-server libraries. You do not need to turn the application into an OAuth2 Client just to accept bearer tokens. `spring-boot-starter-oauth2-client` serves other flows (login/authorized clients), not the minimum requirement for a Resource Server validating opaque tokens.

### What Else Must Be Designed Beyond Three Properties?

- Does the API require `aud=orders-api`, which issuer, which client, which tenant?
- How does the AS ensure `active:true` means the token is unexpired, unrevoked, and intended for this RS?
- How are scopes issued by the AS? Is additional mapping for roles/groups/permissions needed?
- How are AS TLS and secure RS client credential authentication handled?
- What are the timeouts, retries, circuit breakers, AS overload handling, and fail-closed policies?
- Is introspection cached? For how long? What revocation latency is acceptable?
- If the API uses both browser cookies and bearer tokens, what is the CSRF threat model?
- How must logs, metrics, and audits avoid exposing full tokens?

## 9. Runnable Java 17 Example with Real Local HTTP Introspection

This example provides **a single Spring Boot 3.5.12 application** that learners can run immediately without a separate IdP. Inside the app is a **stub AS endpoint** named `/demo-idp/introspect`, called by the RS over loopback HTTP. Demo tokens are fixed strings for verification and carry no security value.

**SCOPE WARNING:** in real systems, the introspection endpoint lives on a **separate Authorization Server**, protected by TLS, strong client authentication, and introspection authorization policies. Never expose the demo endpoint, demo tokens, or demo client secret to the Internet. The sample app binds to `127.0.0.1` and is strictly for learning.

Scenario:

| Illustrative Token | Introspection Response | Identity/Scopes | Expected API |
| --- | --- | --- | --- |
| `read-token` | `active:true` | `sub=alice`, `orders.read` | `GET /api/orders` → 200 |
| `profile-token` | `active:true` | `sub=bob`, `profile.read` | `GET /api/orders` → 403; `/api/me` → 200 |
| `inactive-token` | `active:false` | No metadata returned | API → 401 |
| `expired-token` | `active:false` | No metadata returned | API → 401 |
| `revoked-token` | `active:false` | No metadata returned | API → 401 |
| No token | Introspection not called | — | API → 401 |

In the demo, the AS stub is **programmed to return inactive** for the corresponding token names; it is not an expiration clock simulator or a real issuance/revocation workflow. Testing time-based revocation requires a real IdP/store transitioning a token from active to inactive.

### 9.1. Directory Structure

```text
opaque-introspection-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/opaque/
    │   │   ├── OpaqueDemoApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   ├── DemoIntrospectionController.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/opaque/
            └── OpaqueTokenIntegrationTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'opaque-introspection-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.5.x requires Java 17+ and a compatible Gradle version. Use Gradle 8.4+ or an appropriately configured Gradle Wrapper. Classes use Spring libraries and therefore **cannot compile with bare `javac`** lacking a classpath; Gradle supplies dependencies and the classpath.

### 9.2. `application.properties`: Introspection Target URL

**`src/main/resources/application.properties`**

```properties
# Run locally only for this lesson
server.address=127.0.0.1
server.port=8080

# Resource Server validates tokens via demo introspection endpoint
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=http://127.0.0.1:8080/demo-idp/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=resource-client
spring.security.oauth2.resourceserver.opaquetoken.client-secret=resource-secret
```

**Note:** the client ID/secret here belong to the **Resource Server when calling introspection**, not to a user's access token, not to the OAuth2 client receiving tokens, and not to Alice's password. In production, these are server configuration secrets that must be protected and rotated, never hardcoded.

### 9.3. Main Application

**`src/main/java/com/example/opaque/OpaqueDemoApplication.java`**

```java
package com.example.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueDemoApplication.class, args);
    }
}
```

### 9.4. SecurityFilterChain

**`src/main/java/com/example/opaque/SecurityConfiguration.java`**

```java
package com.example.opaque;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/demo-idp/introspect")
                    .permitAll()
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .csrf(csrf -> csrf
                .ignoringRequestMatchers("/demo-idp/introspect")
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(withDefaults())
            )
            .build();
    }
}
```

**Explanation of each decision:**

1. `/demo-idp/introspect` is allowed past **Spring Security's HTTP authorization** so Basic requests from the RS to the demo endpoint reach the controller. **This does NOT mean the introspection endpoint is public**: the controller itself enforces the RS's Basic credentials. This is strictly a single-process lab setup; production must separate onto a trusted AS and protect it properly.
2. CSRF is ignored solely for **the demo introspection POST endpoint** because it is a service-to-service call not using browser cookies to prove login. Never disable CSRF globally out of convenience if the application also uses cookies/form login for other flows.
3. `/api/orders` requires `SCOPE_orders.read`; an active token holding only `profile.read` is insufficient.
4. `/api/me` requires authentication via a valid bearer token, with no specific scope required.
5. `anyRequest().denyAll()` blocks unclassified routes, preventing accidental exposure of other controllers.
6. `oauth2ResourceServer(...opaqueToken(...))` enables Bearer Token authentication using introspection, driven by the three Boot properties. There is no `jwt()` in this flow.
7. The AS stub uses `Authorization: Basic`, not Bearer; the resource server filter does not treat that Basic header as a bearer token.
8. If using Servlet endpoints as a real API, continue designing HTTPS, session policy, CSRF/headers, forwarded proxies, and monitoring for your application's context.

**Note on independence:** `SecurityConfiguration` here **is part of the complete demo app**, separate from the production fragment in Section 8. Do not combine two overlapping `SecurityFilterChain` beans when running the example.

### 9.5. Stub Introspection Endpoint Authenticating the RS

**`src/main/java/com/example/opaque/DemoIntrospectionController.java`**

```java
package com.example.opaque;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoIntrospectionController {

    private static final String EXPECTED_BASIC =
        "Basic " + Base64.getEncoder().encodeToString(
            "resource-client:resource-secret".getBytes(StandardCharsets.UTF_8)
        );

    @PostMapping(
        value = "/demo-idp/introspect",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> introspect(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION,
                           required = false) String authorization,
            @RequestParam("token") String token) {

        if (!Objects.equals(EXPECTED_BASIC, authorization)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_client"));
        }

        if ("read-token".equals(token)) {
            return ResponseEntity.ok(Map.of(
                "active", true,
                "sub", "alice",
                "client_id", "orders-client",
                "scope", "orders.read",
                "token_type", "Bearer",
                "aud", List.of("orders-api"),
                "exp", Instant.now().plusSeconds(600).getEpochSecond()
            ));
        }

        if ("profile-token".equals(token)) {
            return ResponseEntity.ok(Map.of(
                "active", true,
                "sub", "bob",
                "client_id", "profile-client",
                "scope", "profile.read",
                "token_type", "Bearer",
                "aud", List.of("orders-api"),
                "exp", Instant.now().plusSeconds(600).getEpochSecond()
            ));
        }

        return ResponseEntity.ok(Map.of("active", false));
    }
}
```

Key takeaways:

- The AS stub **does not issue tokens**: it merely simulates looking up two active tokens in a token store and returns inactive for every other string.
- The `EXPECTED_BASIC` check only simulates Basic client authentication. String comparison like this **is not** a production auth server: there is no secret manager, rotation, strong client authentication, per-client permissions, TLS, or real token store.
- `active:false` returns HTTP 200 with **no extra metadata**. This is a memorable RFC 7662 behavior. On invalid Basic credentials, the stub returns HTTP 401 without revealing whether the token exists.
- `scope` is an RFC-convention string, not directly a Java `GrantedAuthority`. The Spring introspector converts it to `SCOPE_orders.read` or `SCOPE_profile.read`.
- `exp` is generated in the future to show the epoch-seconds shape; the stub **does not** actually manage token lifetimes, revocation, or dynamic state transitions. The `expired-token`/`revoked-token` tokens in the table always fall into the inactive branch.
- The endpoint shares the same app as the RS solely to keep the example single-process. In real systems, the AS/IdP is a separate trusted system; introspection must never be opened to arbitrary callers or run over unencrypted HTTP.

### 9.6. API Using the Introspected Authentication

**`src/main/java/com/example/opaque/ApiController.java`**

```java
package com.example.opaque;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/orders")
    public String orders(Authentication authentication) {
        return "orders for " + authentication.getName();
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "name", authentication.getName(),
            "authorities", authorities
        );
    }
}
```

`Authentication.getName()` for an opaque bearer token is typically taken from `sub` if introspection returns that attribute. In the example, `read-token` carries `sub=alice` and `profile-token` carries `sub=bob`.

**Never return raw access tokens, client secrets, the entire raw introspection response, or sensitive principal attributes** from APIs. The `/api/me` endpoint returns only two illustrative fields—name and authorities—to demonstrate scope mapping.

### 9.7. Running and Sending HTTP Requests

Your machine needs JDK 17+, a compatible Gradle version, and port `8080` free:

```bash
gradle test
gradle bootRun
```

You can use `./gradlew test` / `./gradlew bootRun` if the project has a suitable Gradle Wrapper, or `gradlew.bat` on Windows. `gradle bootRun` starts the server on `127.0.0.1:8080` under the demo config.

In another terminal:

```bash
# Public route
curl -i http://127.0.0.1:8080/public

# No token
curl -i http://127.0.0.1:8080/api/me

# Active token with matching orders.read scope
curl -i -H 'Authorization: Bearer read-token' \
    http://127.0.0.1:8080/api/orders

# Active token with only profile.read
curl -i -H 'Authorization: Bearer profile-token' \
    http://127.0.0.1:8080/api/orders

# Same profile token on a route requiring only authenticated
curl -i -H 'Authorization: Bearer profile-token' \
    http://127.0.0.1:8080/api/me

# Inactive token
curl -i -H 'Authorization: Bearer inactive-token' \
    http://127.0.0.1:8080/api/me

# Token hitting the stub's expired/revoked branch
curl -i -H 'Authorization: Bearer revoked-token' \
    http://127.0.0.1:8080/api/me
```

**Expected HTTP status codes:**

| Request | HTTP | Explanation |
| --- | :---: | --- |
| `GET /public`, no Bearer | 200 | `permitAll` |
| `GET /api/me`, no Bearer | 401 | Missing credentials |
| `GET /api/orders`, `read-token` | 200 | `active:true` and `SCOPE_orders.read` |
| `GET /api/orders`, `profile-token` | 403 | `active:true` but missing scope |
| `GET /api/me`, `profile-token` | 200 | Only requires authenticated |
| `GET /api/me`, `inactive-token` | 401 | AS stub returns `active:false` |
| `GET /api/me`, `expired-token` | 401 | AS stub returns `active:false` |
| `GET /api/me`, `revoked-token` | 401 | AS stub returns `active:false` |

Success response bodies explicitly defined by the code:

```text
GET /public, no token                   -> public
GET /api/orders, read-token             -> orders for alice
GET /api/me, profile-token              -> JSON name=bob, authorities contains SCOPE_profile.read
```

JSON objects may vary **property ordering** during serialization; assert content rather than byte-by-byte string equality. Error bodies can vary depending on exception handling/headers; the table focuses on HTTP status and authorization.

**Using curl on Windows:** the `\` line continuations above fit Unix shells. In PowerShell, you can use `curl.exe` and keep the command on **one line**, for example:

```powershell
curl.exe -i -H "Authorization: Bearer read-token" http://127.0.0.1:8080/api/orders
```

### 9.8. Calling the Introspection Endpoint Directly

These are **direct calls to the AS stub** (different from sending tokens to the API):

```bash
# Valid Resource Server Basic credentials; active token
curl -i -u resource-client:resource-secret \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'token=read-token' \
    http://127.0.0.1:8080/demo-idp/introspect

# Invalid client credentials → 401 at introspection endpoint
curl -i -u wrong-client:wrong-secret \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'token=read-token' \
    http://127.0.0.1:8080/demo-idp/introspect

# Inactive token with valid introspection client → HTTP 200
curl -i -u resource-client:resource-secret \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'token=inactive-token' \
    http://127.0.0.1:8080/demo-idp/introspect
```

Sample responses:

```text
Valid Basic + read-token:
HTTP 200
JSON with active=true, sub=alice, scope=orders.read, aud=[orders-api]

Invalid Basic + read-token:
HTTP 401
{"error":"invalid_client"}

Valid Basic + inactive-token:
HTTP 200
{"active":false}
```

These are **HTTP statuses from the introspection endpoint**, not the HTTP status the API returns to Clients when a bearer token is invalid.

**Do not run this example with these tokens/secrets on a public network.** Both mock tokens and Basic credentials are hardcoded for learning, and unencrypted HTTP is acceptable only inside a closed loopback environment.

### 9.9. Integration Tests with Real HTTP Introspection

To test not just a mocked bean but also that the **Resource Server genuinely calls the HTTP introspection endpoint**, use `@SpringBootTest` with an embedded server listening on a dedicated port **18080** during tests. The test overrides the introspection URI to that port, so API requests in tests **call back into the AS stub over real HTTP**, rather than hitting only a `@MockBean OpaqueTokenIntrospector`.

**`src/test/java/com/example/opaque/OpaqueTokenIntegrationTests.java`**

```java
package com.example.opaque;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT,
    properties = {
        "server.port=18080",
        "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri="
            + "http://127.0.0.1:18080/demo-idp/introspect"
    }
)
class OpaqueTokenIntegrationTests {

    @Autowired
    TestRestTemplate http;

    private ResponseEntity<String> apiGet(String path, String token) {
        HttpHeaders headers = new HttpHeaders();
        if (token != null) {
            headers.setBearerAuth(token);
        }
        return http.exchange(
            path,
            HttpMethod.GET,
            new HttpEntity<>(headers),
            String.class
        );
    }

    @Test
    void publicEndpointRequiresNoToken() {
        ResponseEntity<String> response = apiGet("/public", null);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("public", response.getBody());
    }

    @Test
    void missingBearerIsUnauthorized() {
        assertEquals(
            HttpStatus.UNAUTHORIZED,
            apiGet("/api/me", null).getStatusCode()
        );
    }

    @Test
    void activeTokenWithReadScopeCanReadOrders() {
        ResponseEntity<String> response =
            apiGet("/api/orders", "read-token");

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("orders for alice", response.getBody());
    }

    @Test
    void activeTokenWithoutReadScopeIsForbidden() {
        ResponseEntity<String> response =
            apiGet("/api/orders", "profile-token");

        assertEquals(HttpStatus.FORBIDDEN, response.getStatusCode());
    }

    @Test
    void profileTokenCanUseAuthenticatedEndpoint() {
        ResponseEntity<String> response =
            apiGet("/api/me", "profile-token");

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertTrue(response.getBody().contains("\"bob\""));
        assertTrue(response.getBody().contains("SCOPE_profile.read"));
    }

    @Test
    void inactiveAndRevokedTokensAreUnauthorized() {
        assertEquals(
            HttpStatus.UNAUTHORIZED,
            apiGet("/api/me", "inactive-token").getStatusCode()
        );
        assertEquals(
            HttpStatus.UNAUTHORIZED,
            apiGet("/api/me", "revoked-token").getStatusCode()
        );
        assertEquals(
            HttpStatus.UNAUTHORIZED,
            apiGet("/api/me", "expired-token").getStatusCode()
        );
    }

    @Test
    void introspectionRequiresResourceServerClientCredentials() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBasicAuth("wrong-client", "wrong-secret");
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);

        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("token", "read-token");

        ResponseEntity<String> response = http.postForEntity(
            "/demo-idp/introspect",
            new HttpEntity<>(form, headers),
            String.class
        );

        assertEquals(HttpStatus.UNAUTHORIZED, response.getStatusCode());
    }

    @Test
    void inactiveTokenIntrospectionIsHttp200WithActiveFalse() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBasicAuth("resource-client", "resource-secret");
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);

        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("token", "inactive-token");

        ResponseEntity<String> response = http.postForEntity(
            "/demo-idp/introspect",
            new HttpEntity<>(form, headers),
            String.class
        );

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertTrue(response.getBody().contains("\"active\":false"));
    }
}
```

**Verified behaviors:**
- An HTTP server runs on **18080**, and the Resource Server calls real loopback introspection for `apiGet` calls with a bearer token.
- An active token missing a scope results in **403**, distinct from an inactive token resulting in **401**.
- The introspection endpoint returns **401** for invalid client credentials and **200 + active:false** for inactive tokens.
- Because both run on embedded Tomcat, API requests and internal introspection requests execute on different request threads; this small lab model works, yet **does not** replace an independent AS design.
- If port 18080 is already occupied on your machine, update **both** `server.port` and the introspection URI in the test annotation accordingly. This style of test should not run concurrently with another process bound to the same port.
- The tests do not measure time-based revocation, caching, AS outages, TLS/certificates, or performance. Do not claim those aspects were tested.

### 9.10. Why Writing a Fake Introspector in Tests Is Not Enough

You can mock `OpaqueTokenIntrospector` to unit-test rules faster. When mocking, however, you **fail to verify**:
- The HTTP POST and `token` form body.
- The RS's HTTP Basic client authentication.
- How `active`/`scope` are parsed from the AS's JSON.
- TLS, timeouts, and network errors.
- Compatibility of the real endpoint with Spring's introspector.

In this lesson, the integration test intentionally hosts an HTTP AS stub on the same server to observe the **introspection request–response**. For production, add contract/integration tests against a real test IdP or standalone mock server, especially covering `active:false`, missing scopes, `exp`/`aud` mismatches, client credential rotation, and AS errors.

## 10. Customizing Audience/Issuer Checks After Introspection

A resource server may receive `active:true` from an AS even when the token was intended for a different resource. If the AS guarantees returning active only when the RS is a valid audience, document that contract and test it explicitly. If the AS returns `aud` in the response and the RS enforces a local policy, **verify audience yourself** using a decorator around the introspector.

**Conceptually standalone fragment** (do not drop into the running demo without redesigning dependency injection and tests):

```java
OpaqueTokenIntrospector audienceChecked(
        String uri, String clientId, String clientSecret) {

    OpaqueTokenIntrospector delegate =
        SpringOpaqueTokenIntrospector.withIntrospectionUri(uri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();

    return token -> {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
        Object audience = principal.getAttribute("aud");

        if (!(audience instanceof java.util.Collection<?> values)
                || !values.contains("orders-api")) {
            throw new BadOpaqueTokenException("Invalid token");
        }

        return principal;
    };
}
```

This fragment requires the imports:
- `org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector`.
- `org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector`.
- `org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException`.
- `org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal`.

This is an **illustrative method for creating a decorator**, not a standalone Java file and not an auto-registered `@Bean`. In a real app, you can configure an `OpaqueTokenIntrospector` bean using the RS's properties/secrets for Spring Boot to pick up. Throwing `BadOpaqueTokenException` rejects the token under opaque token authentication.

**This only checks a collection-typed `aud`**, whereas a real AS may return `aud` as a string or collection depending on contract. Validate the exact data shapes guaranteed by your IdP, as well as issuer, expiration, token type, tenant, and resource-specific permissions where applicable. Never apply code mechanically across all providers.

### When Is Custom Authority Mapping Needed?

If the AS returns `roles`/`groups` instead of OAuth2 `scope`, or you want to translate custom claims into Spring `GrantedAuthority`, define an appropriate `OpaqueTokenIntrospector`/`OpaqueTokenAuthenticationConverter`. Authorities must come from **attributes verified by the AS**, never from query parameters supplied by the Client.

Do not blindly turn every role/group into `ROLE_ADMIN` or grant `SCOPE_orders.read` to all active tokens. Review claim sources, prefixes, tenants, and per-endpoint permissions.

## 11. Revocation, Caching, and Latency

### Why Introspection Helps with Token Revocation

With an opaque reference token, the AS can flip a token's state from active to inactive in its token store (e.g., on revocation or account permission loss). When the RS queries the AS again, it receives the updated state.

```text
Time t0:
AS: token T active=true
RS introspects T → allow if scope suffices

Time t1:
AS: revoke T

Time t2:
RS introspects T again → active=false
RS rejects token (typically API 401)
```

How "immediate" this is depends on **whether the RS introspects again**, AS/store consistency, and whether results are cached. **Introspection does not automatically guarantee zero-latency revocation.**

### Introspection Caching: Cost Savings vs. Stale State

If the RS introspects on every request:
- Adds network RTT/CPU and load on the AS.
- Can detect revocation quickly if the AS always reflects current state.
- If the AS is slow or down, many requests are impacted; capacity, timeouts, circuit breakers, and retry-storm protections are required.

If the RS caches `active:true` results for 60 seconds:
- Reduces requests to the AS and lowers latency.
- Yet a token revoked at second 1 may still be treated as active by the RS until the cache expires, depending on invalidation mechanisms.
- Never cache longer than the token's `exp` if known; cache keys must bind the exact token + RS/audience/tenant context where needed.
- Cache safely for both active and inactive results, never store raw tokens in metrics/logs, and protect the cache as sensitive data.

**Back-of-the-envelope trade-off:** at 1,000 API requests/sec with one introspection per request, the AS must handle roughly **1,000 introspection calls/sec** before caching or batching. Caching reduces load while widening the "window accepting revoked tokens".

### Fail Closed When the AS Is Unavailable

Do not do this:

```java
try {
    return delegate.introspect(token);
} catch (Exception ex) {
    // DANGEROUS: never grant access just because introspection is down
    return unrestrictedPrincipal;
}
```

This is an **incomplete anti-example, not standalone runnable code**; its purpose is a warning. When a token cannot be verified, **never construct a privileged principal to bypass security**. Choose an appropriate failure response and record it clearly in internal logs/metrics without exposing secrets or raw tokens.

Operational parameters to tune per SLO:
- Appropriate connect/read timeouts.
- Bounded retries with backoff that do not trigger cascading storms when the AS fails.
- Circuit breakers and a fallback that **denies access** with a message revealing no internals.
- Monitor introspection success/inactive/error rates, p50/p95/p99 latency, TLS failures, and AS availability.
- Separate "token inactive" metrics from "invalid client credentials" and "AS 5xx/down".
- When caching, track hit ratio and revocation propagation delay.

## 12. Security Controls and Threats

| Threat | Mitigation |
| --- | --- |
| Bearer token logged in URL/query | Use only `Authorization` header to APIs, form POST body to introspection; redact logs |
| Token sent to rogue host via SSRF/misconfiguration | Trusted/allowlisted introspection URI, TLS certificate validation, egress proxy policy |
| RS client credentials leaked | Secret manager, least privilege, rotation, never store in repository |
| Unauthorized party calling introspection to probe tokens | RS client authentication and authorization, minimize returned data |
| AS returns active for token with wrong audience | Enforce AS policy and `aud`/issuer per resource contract |
| Blindly trusting `active:true` | Separately check scopes, tenant, owner/resource permissions |
| Introspection fails and RS fails open | Fail closed and return controlled error |
| Active result cached too long | TTL aligned with `exp` and revocation SLA; design invalidation |
| Token replay | HTTPS, short lifetimes, narrow scopes, token binding/DPoP/mTLS if architecture requires |
| CSRF | Analyze browser credentials; explicitly attached bearer headers differ from ambient cookies |
| XSS and token storage | Mitigate script injection, protect client-side tokens, CSP/`HttpOnly` per architecture |
| Overly broad scopes | Grant least privilege, map `SCOPE_...` accurately |
| Misunderstood logout | Deleting client tokens does not necessarily revoke at AS; support revocation endpoints/policies |
| Cross-tenant IDOR | Scope does not prove order ownership; add object-level authorization |
| Network latency/AS outage | Monitoring, timeouts, AS HA, bounded cache, and fail closed |

### CSRF in Bearer-Token APIs

If the client **explicitly** attaches the token to `Authorization: Bearer` and the browser does not automatically send this credential from third-party origins, CSRF risk differs from cookie-based sessions. However, if an access token is stored in a cookie automatically sent by the browser, CSRF remains a threat. Never claim "opaque means no CSRF needed" or disable protections across all endpoints just because OAuth2 is used.

The runnable example only creates a demo introspection POST endpoint using RS Basic credentials, with no cookie login; the CSRF exception is scoped strictly to that demo route to illustrate service-to-service calls.

### Scope Is Not Object Permission

`SCOPE_orders.read` may permit a user to **read orders within an application-defined scope**, not automatically view every order across all tenants. When a request hits `/api/orders/123`, the service must verify that the caller is permitted to read resource 123, its owner/tenant, and its state. That is object-level protection at the business layer and cannot be inferred from `active:true` or `scope` alone.

## 13. Common Spring Security Configuration Mistakes

| Mistake | Outcome | Fix |
| --- | --- | --- |
| Configuring `oauth2ResourceServer().jwt()` when AS issues opaque tokens | RS cannot verify opaque tokens as JWTs | Use `opaqueToken`/`OpaqueTokenIntrospector` |
| Missing `introspection-uri` or client credentials | Cannot call AS | Configure valid properties and protect secrets |
| AS reports inactive yet RS still lets request in | Revoked/expired tokens reused | Issue `Authentication` only on valid introspection |
| Treating HTTP 200 from AS as active | Confusing HTTP status with JSON `active` | Check `active`; 200 can contain `false` |
| Treating HTTP 401 from AS as "user not logged in" | Ignoring RS–AS client authentication failure | Monitor client credentials separately; never fail open |
| Active token lacking scope returns API 200 | Wrong authorization policy | `hasAuthority("SCOPE_orders.read")` or matching policy |
| Using `hasRole("orders.read")` instead of `hasAuthority("SCOPE_orders.read")` | Wrong prefix/authority system | Distinguish roles and scopes |
| Ignoring audience/issuer | Tokens meant for another API accepted | Enforce contract and validators on RS |
| Logging full introspection body/token | Leaking PII/credentials | Redact data, limit retention |
| Caching active tokens forever | Revocation has no effect | TTL, `exp`-bound, invalidation |
| Allowing fallback on every AS error | Loses API security boundary | Fail closed, monitor outages |
| Calling introspection via GET with query token | Token easily leaks in logs/history | RFC-compliant HTTP POST form body |
| Returning token metadata when `active=false` | May disclose token state | Return only `{"active":false}` |
| Placing a mock AS beside RS in production | No clear trust boundary | Separate AS, real TLS/client auth |
| Treating JWT as "always stateless" | Ignoring revocation/state at IdP | Separate token format from validation method |
| Testing only 200 | Misses 401/403, client auth, AS outages | Test positive, negative, and network cases |

## 14. Self-Check Questions

**1. Why can't the Resource Server read scopes directly from an opaque token?**

Because an opaque token string has no format/claims the Resource Server is permitted to trust directly. It must verify via an AS-provided mechanism, typically RFC 7662 introspection.

**2. If introspection returns HTTP 200 with JSON `{"active":false}`, should the API allow the request?**

No. 200 only means the introspection call itself was processed validly; the token was reported inactive and must be rejected.

**3. When the RS sends wrong client credentials to introspection, what should the AS return?**

Typically HTTP 401 per OAuth2 client authentication, distinct from HTTP 200 + `active:false` for an invalid token when the introspection client itself authenticated properly.

**4. Can an active token with `scope=profile.read` access an endpoint requiring `SCOPE_orders.read`?**

No. `active:true` passes token authentication, yet authorization lacks the required authority; the API typically returns 403.

**5. Is `sub` always the user's email address or username?**

No. `sub` is a subject identifier defined by the issuer/AS and token type; never assume it is an email, tenant ID, or safe to display publicly.

**6. Must an opaque token always be a random string and never a JWT?**

No. "Opaque" describes how the RS treats/validates the token; Spring Security's opaque introspector can send any appropriate bearer token to the AS, including a JWT-formatted string.

**7. Why can introspection caching allow revoked tokens to keep being accepted?**

Because the RS reuses an older `active:true` result until the cache expires or is invalidated, instead of querying the AS on every request.

**8. If the introspection endpoint is down, should tokens be assumed valid so the API stays up?**

No. That is fail-open. The RS must deny access when verification fails; handle availability via architecture/timeouts/monitoring, not by bypassing security.

**9. When is checking `aud` necessary?**

When a token must be bound to a specific Resource Server/resource. If a token intended for `billing-api` is accepted by `orders-api`, there is token substitution / cross-resource risk.

**10. Why should access tokens not be placed in the query string when calling introspection?**

URLs are easily written to proxy/server logs, access histories, and monitoring systems. RFC 7662 uses POST with a form body and requires protecting the endpoint with TLS.

**11. What authority does Spring Security map `scope="orders.read"` to by default?**

Typically `SCOPE_orders.read`. The rule `hasAuthority("SCOPE_orders.read")` checks this exact authority.

**12. If a token is active and has `orders.read`, can the caller definitely view another user's orders?**

No. Scope does not prove ownership of individual records; resource/tenant/owner authorization is still required.

**13. Does testing `active:false` on the stub prove real revocation works immediately?**

No. It only proves the RS rejects an inactive introspection response. Testing real revocation requires an AS whose token state changes over time while measuring propagation/caching.

**14. Why does the Resource Server need its own client ID/secret to introspect when the client already brings a bearer token?**

Because the bearer token authenticates the **API caller's** authorization, whereas introspection client credentials authenticate the **Resource Server** to the Authorization Server. These are two distinct trust relationships.

**15. Can opaque tokens be used without configuring `SessionCreationPolicy.STATELESS`?**

Yes. OAuth2 Resource Server can process bearer tokens per request independently of login sessions. If the application also has cookie/form login mechanisms, design state/persistence and CSRF explicitly; `STATELESS` is a separate configuration choice, not a defining requirement of opaque tokens.

## 15. Summary

- An **opaque token** is a token whose structure/claims the Resource Server does not trust directly; it typically asks the **Authorization Server** for its status.
- **RFC 7662** standardizes `POST` introspection with `token` in the form body, RS authentication, and JSON `active`.
- **HTTP 200 + `active:false`** means the introspection request succeeded but the token is invalid. **HTTP 401 at introspection** typically indicates an RS authentication/authorization error calling the endpoint. **HTTP 401/403 at the API** carries its own distinct meaning.
- In Spring Security, `OpaqueTokenIntrospector` verifies the token and produces `Authentication`; `scope` typically maps to `SCOPE_...` for `hasAuthority`.
- **`active: true` is not enough:** check scopes, audience/issuer, tenant, and object-level permissions per policy.
- Introspection can support rapid revocation, yet depends on AS/network and caching; **never fail open** on lost connectivity.
- Token format (opaque/JWT), validation method (local/introspection), and session policy (stateful/stateless) are **independent decisions**.
- The local example hosts a stub AS in the same process solely to observe Spring Resource Server's real flow; production requires a trusted AS, TLS, protected client secrets, and complete policies.

## 16. Official References

- Spring Security — OAuth 2.0 Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Boot 3.5 — Spring Security Resource Server properties: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- Spring Security — `SpringOpaqueTokenIntrospector` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html
- Spring Security — Servlet Resource Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
