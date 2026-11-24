# WWW-Authenticate for HTTP Basic and Bearer in Spring Security

## 1. Problem Statement: Why Does an API Return 401 Without the Client Knowing How to Authenticate?

A protected Java API may receive requests **without credentials**, with wrong credentials, or with valid credentials that **lack permission**. Simply returning JSON `{"error":"unauthorized"}` does not clearly explain **which authentication mechanism the HTTP client must use**. HTTP provides a header-based *challenge–response* protocol:

- The server returns **`WWW-Authenticate`** in the **HTTP response** to advertise one or more **authentication schemes** applicable to the resource.
- The client can retry with **`Authorization`** in the **HTTP request**, supplying credentials under the right scheme.
- `401 Unauthorized` states there are no **valid credentials** for the resource yet; `403 Forbidden` usually states the credentials are recognized but **lack permission** to perform the action.
- `Basic` and `Bearer` have **different syntax, credential lifecycles, error handling, and threat models**. Do not use them interchangeably.

Example when calling an endpoint requiring HTTP Basic:

~~~http
GET /basic/report HTTP/1.1
Host: api.example.org

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Legacy Lab"
~~~

With an OAuth 2.0 Resource Server endpoint:

~~~http
GET /bearer/report HTTP/1.1
Host: api.example.org

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="Report API"
~~~

**Learning objectives:**
1. Read, produce, and test the `WWW-Authenticate` header properly per HTTP semantics.
2. Distinguish **challenge** in the response from **credential** in the request, and `WWW-Authenticate` from `Proxy-Authenticate`.
3. Understand Basic `realm`, Base64, `charset="UTF-8"`, browser credential prompts, and HTTPS.
4. Understand Bearer `realm`, `error`, `error_description`, `error_uri`, `scope`; distinguish `invalid_request`, `invalid_token`, and `insufficient_scope`.
5. Map **401/403** to Spring Security `AuthenticationEntryPoint` and `AccessDeniedHandler`.
6. Configure Spring Boot Java 17+ with two separate filter chains for Basic and Bearer, observe the results, and write MockMvc tests.
7. Avoid production mistakes such as dropped headers from handlers/proxies, returning 401 in the wrong cases, leaking tokens in logs, and advertising the wrong auth scheme.

## 2. The HTTP Contract: WWW-Authenticate Is an Invitation to Authenticate

According to [RFC 9110, `11.3 and `11.6.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-11.6.1):

- A server returning `401` **must** send at least one applicable challenge via `WWW-Authenticate`.
- The header may appear on other statuses when using different credentials could grant access; it does **not** mean every `403` must carry a challenge.
- A response may contain **multiple challenges**, across multiple header fields or as a list per HTTP syntax. The client picks a scheme it understands and can satisfy.
- `407 Proxy Authentication Required` uses `Proxy-Authenticate`, not `WWW-Authenticate`; the client sends `Proxy-Authorization` to the proxy, not as origin-server credentials.

General syntax:

~~~text
WWW-Authenticate: <auth-scheme> [challenge-data]
Authorization: <auth-scheme> <credentials>
~~~

In HTTP, **requests** and **responses** differ. Do not send `WWW-Authenticate` in a request expecting the server to authenticate it. Do not use `Authorization: Bearer ...` as a response challenge. A client that already knows an endpoint's policy can **send Authorization preemptively** before receiving `401` (preemptive authentication); it must still follow the scheme and protect credentials.

### 2.1. Comparison Table of Three Commonly Confused Headers

| Header | Direction | Meaning | Accompanied By |
| --- | --- | --- | --- |
| `WWW-Authenticate` | Response from **origin server** | Challenges the client to use a scheme appropriate for the resource | Primarily `401`; occasionally other statuses |
| `Authorization` | Request to **origin server** | Credentials supplied by the client | `Basic ...`, `Bearer ...`, or another scheme |
| `Proxy-Authenticate` | Response from **proxy** | Proxy requires authentication before forwarding | `407` |
| `Proxy-Authorization` | Request to **proxy** | Credentials intended for the proxy | After a `407` challenge or sent preemptively |

Example:

~~~http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Basic realm="Corporate Proxy"
~~~

This is not the API server rejecting an access token; this is the proxy requesting authentication for the **proxy itself**. The client sends `Proxy-Authorization` to the trusted proxy, never forwarding the proxy password to the API origin.

### 2.2. Challenges Can Have Multiple Parameters

A Basic challenge:

~~~http
WWW-Authenticate: Basic realm="Legacy Lab", charset="UTF-8"
~~~

A Bearer challenge:

~~~http
WWW-Authenticate: Bearer realm="Report API", error="invalid_token"
~~~

The comma here may separate **auth-params of the same challenge**, rather than marking a new challenge. HTTP also allows sending multiple challenges. Therefore:
- **Do not parse** `WWW-Authenticate` via `split(",")` assuming every piece is a scheme.
- Quoted values may contain escaped characters and commas; parsers must follow HTTP syntax.
- Do not assume there is always a single header field or a single challenge; use a compliant HTTP library.

Example response with multiple schemes:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Legacy"
WWW-Authenticate: Bearer realm="Report API"
~~~

At the HTTP level, multiple options can be offered. However, **do not enable both in Spring merely because an endpoint can return multiple headers**; you must design and test the actual policy, filter order, browser prompt behavior, and how each scheme authenticates/authorizes.

## 3. Status 401 vs 403: Authenticated or Not?

| Scenario | Typically Appropriate HTTP Status | `WWW-Authenticate` |
| --- | --- | --- |
| Protected resource, request has no credentials | **401** | **Yes**, e.g. `Basic realm="..."` or `Bearer` |
| Wrong Basic password or unable to decode valid credentials | **401** | Basic challenge per policy |
| Bearer access token expired/revoked/invalid signature/audience | **401** | Bearer with `error="invalid_token"` when appropriate |
| Valid Bearer token, lacking scope required by endpoint | **403** | May include Bearer `error="insufficient_scope"` |
| Valid Basic user, insufficient role | **403** | Challenge not required; returning 401 can make the client re-enter password uselessly |
| Malformed Bearer request, multiple token transmission methods | Usually **400** per RFC 6750 `invalid_request` | Bearer challenge/error when appropriate |
| Resource hidden by policy to avoid confirming existence | Possibly **404** | Do not leak unnecessary details |
| CSRF token error on unsafe request | Usually **403** | Should not default to invalid Basic/Bearer token |
| Rate limiting or upstream outage | `429` or `5xx` per cause | Do not re-advertise auth if the error is not a credential issue |

**Warning about HTTP status names:** `401 Unauthorized` actually describes *missing or invalid authentication credentials*. It does not mean "logged in but not permitted", which typically belongs to `403`. Do not let the status name lead to inverted handling.

If a resource server receives a token with a **valid signature but wrong `aud`/`iss`**, it is still an **invalid token for the current resource**, typically `401 invalid_token`, not `403 insufficient_scope`. Scope checks happen only after the token is verified as valid for the API.

## 4. HTTP Basic: WWW-Authenticate: Basic realm="..."

[**RFC 7617**](https://www.rfc-editor.org/rfc/rfc7617.html) defines HTTP Basic Authentication.

**Challenge:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Documents"
~~~

**Credentials in the subsequent request:**

~~~http
GET /documents/private HTTP/1.1
Host: api.example.org
Authorization: Basic dGVzdDoxMjM=
~~~

The string `dGVzdDoxMjM=` is Base64 of the ASCII string `test:123`. **Base64 is only a representation encoding, not encryption**. Anyone reading this header can decode the username/password. Therefore **always use HTTPS** and never store credential headers in logs/traces.

### 4.1. What Is `realm` in Basic?

`realm` is a **required** parameter of a Basic challenge; it names the **protection space** within the origin so the client knows which group of resources shares credentials. For example:

~~~http
WWW-Authenticate: Basic realm="Internal Reports"
~~~

The realm content may appear in the browser's native login dialog or credential cache. Never put passwords, sensitive information, secret tenant IDs, or personal data into the realm name. Sharing the same realm name does not guarantee that all URLs/hosts share the same permissions; the client must check **origin, scheme, TLS, and protection scope**.

Changing the realm can make browsers/HTTP clients treat the resource as a different protection space and prompt for credentials again. Do not vary the realm arbitrarily per request; keep configuration stable and avoid constructing realms from user input.

### 4.2. UTF-8 in a Basic Challenge

RFC 7617 allows:

~~~http
WWW-Authenticate: Basic realm="Documents", charset="UTF-8"
~~~

`charset="UTF-8"` indicates the server expects proper Unicode/UTF-8 handling (with NFC normalization per RFC 7617). The `charset` parameter belongs in the **challenge**, **not** inside the `Authorization` credential via some custom Basic syntax. For Unicode usernames/passwords, client and server must agree on encoding handling. Without advertising `charset`, the historical default encoding is not fully specified, which can cause compatibility differences.

### 4.3. Basic and Browsers

When a browser receives `401` with `WWW-Authenticate: Basic ...`, it may open a native UI prompting for username/password, or use cached credentials. HTTP clients like `curl` or code may retry automatically. **Do not expect browsers to always pop up a dialog**:
- `fetch`/XHR in frontends have distinct behavior; Spring Security has mechanisms to suppress some browser dialogs on AJAX requests, depending on version and headers.
- Proxies, API gateways, CORS, and custom authentication entry points can alter headers.
- Traditional form login uses HTML/cookies/sessions; it is **not** synonymous with HTTP Basic even though both ask for username/password.

HTTP Basic resends credentials on every request when a client uses that scheme; avoid it for modern browser experiences and high-sensitivity services when stronger methods exist. Enable MFA, protect password storage, rate limit, enforce TLS, and apply account policies as required.

## 5. OAuth 2.0 Bearer: WWW-Authenticate: Bearer

According to [**RFC 6750, `3**](https://www.rfc-editor.org/rfc/rfc6750#section-3), the Bearer challenge uses the `Bearer` scheme and may contain auth-params. In the OAuth model:

- The **Authorization Server** issues an access token to the client.
- The **Client** sends the access token via `Authorization: Bearer <access_token>` to the **Resource Server**.
- The **Resource Server** verifies the token against the issuer, lifetime, audience, and scope/authority contract, then decides access.
- Without a valid token, the RS responds using the HTTP Bearer challenge mechanism.

Example request:

~~~http
GET /reports/42 HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...opaque-or-jwt...
~~~

**The token in the example is purely illustrative notation.** An access token **does not have to be a JWT**; it can be an opaque string checked via introspection. `Bearer` specifies how the credential is presented, not which algorithm signed the token.

### 5.1. Missing Token: 401 Without Leaking Extra Errors

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="Report API"
~~~

When the request **contains no authentication information**, RFC 6750 recommends **not** adding `error` or an error description. Simply telling the client the resource uses Bearer is enough. Do not return `invalid_token` when the client did not send a token at all.

Some Spring Resource Servers leave the header as simply `WWW-Authenticate: Bearer`, with no `realm`. That is normal: **realm is optional** for Bearer. Do not write tests requiring `realm="..."` unless you configured one.

### 5.2. Invalid Token: invalid_token

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="Report API",
                  error="invalid_token"
~~~

`invalid_token` is used when a token is expired, revoked, forged, malformed, invalid for the API, or violates policy. RFC 6750 specifies the status is normally **401**. Clients can request a fresh token from the Authorization Server and retry per policy, but **must not retry infinitely** when the token is invalid or permissions are missing.

It may include:

~~~http
WWW-Authenticate: Bearer realm="Report API",
                  error="invalid_token",
                  error_description="The access token expired"
~~~

**This is only a protocol example**. Production should not leak sensitive details such as the raw token, internal key ID, algorithm/certificate name, introspection response, stack trace, or exact JWT check failure reason. Error descriptions are not a debug channel for attackers; internal logs should record request IDs and properly redacted information.

### 5.3. Valid Token but Lacking Scope: insufficient_scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="Report API",
                  error="insufficient_scope",
                  scope="reports.write"
~~~

`insufficient_scope` means the token may be valid for authentication, yet lacks the privileges needed to access the resource. RFC 6750 recommends **403** and **allows** adding `scope` describing required scopes. `scope` contains a **space-delimited** list of scopes; scopes are **case-sensitive** values determined by the resource server's policy.

The header may contain only:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

if the server does not want/need to disclose specific scopes. **Do not send a token with different scopes to an API and think you can fix 403 by refreshing the same grant**: the client needs to be granted proper permissions, have appropriate consent/authorization policy, and satisfy business-level resource permissions.

### 5.4. Invalid Token Request: invalid_request

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

RFC 6750 recommends 400 for `invalid_request` such as missing required parameters, duplicate parameters, invalid transmission format, or the client trying to pass an access token via **multiple methods simultaneously**. Each framework/decoder may have specific behavior; test against the API contract and RFC.

Do not use `invalid_request` as the default code when a JWT has a bad signature: if credentials are recognized yet the **token is invalid**, most cases belong to `invalid_token`.

## 6. Table of Bearer Challenge Fields

| Field | Required? | Meaning | Notes |
| --- | --- | --- | --- |
| `Bearer` | Scheme | Tells the client how to send the access token | Does not need `realm` for the scheme to be valid |
| `realm` | Optional | Protected resource scope | Never include secret data |
| `error` | Optional | Standard codes `invalid_request` / `invalid_token` / `insufficient_scope` | Omit error if auth information is completely absent per RFC recommendation |
| `error_description` | Optional | Brief human-readable description that can help clients | Never return tokens, secrets, or stack traces |
| `error_uri` | Optional | URI to error documentation | Use a fixed URL without sensitive credentials/query parameters |
| `scope` | Optional | Required scope(s) per policy; typically in `insufficient_scope` | Space-delimited, case-sensitive; disclosure may be omitted |
| Extension auth-param | Per contract | Server-defined extension data | Do not insert arbitrary content disallowed by the RFC |

**Watch out for quotes:** realm, description, and scope lists typically use quoted-string syntax. Never concatenate raw user input into `WWW-Authenticate`; use standard builders/exception handlers and escape characters per the RFC. Never inject CR/LF from request parameters to prevent response header injection.

## 7. 401, 403, and Bearer Errors: Decision Matrix

| Scenario at Resource Server | HTTP | Illustrative Header |
| --- | --- | --- |
| Missing `Authorization` | 401 | `WWW-Authenticate: Bearer` |
| Unsupported header scheme, no valid Bearer | 401 or 400 depending on cause | Bearer challenge without extra disclosure |
| Expired Bearer token | 401 | `Bearer error="invalid_token"` |
| Bearer JWT invalid signature/issuer/audience | 401 | `Bearer error="invalid_token"` |
| Revoked opaque token or introspection reports inactive | 401 | `Bearer error="invalid_token"` |
| Valid Bearer token with `reports.read`, endpoint needs `reports.write` | 403 | `Bearer error="insufficient_scope"` when handler has evidence |
| Malformed multiple methods for token | Usually 400 | `Bearer error="invalid_request"` |
| Valid Bearer token, object belongs to another tenant | 403 or 404 per policy | Not required to reveal scope/owner |
| Valid Basic user, insufficient role | 403 | Basic challenge not needed by default |
| Wrong Basic password | 401 | `Basic realm="..."` |

**A Spring Security nuance:** `BearerTokenAccessDeniedHandler` emits `insufficient_scope` only when it can determine the request already holds a valid OAuth2 `Authentication`. If it cannot prove that, the handler may emit just the `Bearer` scheme. Do not assert `insufficient_scope` on every `403` regardless of principal.

### 7.1. Do Not Mix Token Authorization with HTTP Auth Challenges

An access token carrying `SCOPE_reports.read` does not guarantee the subject can read **any arbitrary record** in the API. The Resource Server also checks tenant, ownership, RBAC/ABAC, and domain policies. If the principal is not allowed to view record 42 despite having the right scope, that is a business authorization failure. Returning `scope="reports.read"` is not required since the token already has that scope.

Conversely, a token issued for API A sent to API B is **not** "missing a business role" but an invalid token for B's audience; it must be rejected before object-level authorization.

## 8. Where Does Spring Security Place WWW-Authenticate?

Spring Security Servlet includes these components:

| Component | Role |
| --- | --- |
| `SecurityFilterChain` / `FilterChainProxy` | Selects the right filter set for the endpoint |
| `AuthorizationFilter` | Checks request permissions; can throw `AccessDeniedException` |
| `ExceptionTranslationFilter` | Translates authentication/authorization exceptions into the proper entry point or denied handler |
| `AuthenticationEntryPoint` | Starts authentication for the client; with Basic/Bearer, typically generates `401` + challenge |
| `AccessDeniedHandler` | Handles an authenticated principal lacking permissions; typically `403` |
| `BasicAuthenticationFilter` | Reads `Authorization: Basic ...`, creates auth request for username/password |
| `BearerTokenAuthenticationFilter` | Reads `Authorization: Bearer ...`, creates auth request for token |
| `BasicAuthenticationEntryPoint` | Can send `WWW-Authenticate: Basic realm="..."` |
| `BearerTokenAuthenticationEntryPoint` | Generates Bearer challenge and error params per `BearerTokenError` |
| `BearerTokenAccessDeniedHandler` | Handles access denied per RFC 6750, including `insufficient_scope` when appropriate |

Conceptual processing flow:

~~~text
HTTP request
    |
    v
FilterChainProxy selects SecurityFilterChain
    |
    +-- Has Authorization Basic? --> BasicAuthenticationFilter
    |
    +-- Has Authorization Bearer? -> BearerTokenAuthenticationFilter
    |
    v
AuthenticationManager / Provider / token verifier
    |
    +-- Missing credential / invalid credential
    |      -> AuthenticationEntryPoint
    |      -> 401 + WWW-Authenticate
    |
    +-- Valid Authentication
           |
           v
      AuthorizationFilter checks role/scope/policy
           |
           +-- Sufficient permissions -> controller -> 200/2xx
           |
           +-- Insufficient permissions -> AccessDeniedHandler
                                      -> 403; may include Bearer challenge
~~~

This is a **logical** diagram, not a description of every exact filter order. On Basic/Bearer authentication failures, the filter can invoke the entry point directly; for credential-less requests, `ExceptionTranslationFilter` handles the authorization exception. Actual ordering also depends on filter chain configuration and framework version.

**Do not replace the entry point with a JSON handler that sends `401` while forgetting `WWW-Authenticate`.** Per RFC 9110, an origin server returning 401 must include a challenge. If an SPA frontend wants JSON and does not want a browser Basic dialog, design the frontend/API contract **and** HTTP authentication policy properly rather than silently breaking compliance.

### 8.1. Spring Security and AJAX Basic

Spring Security 6.5 documentation notes: default Basic support handles AJAX-style requests specially to avoid browsers popping up native Basic login dialogs; emission of `WWW-Authenticate` and response bodies may vary depending on headers identifying XMLHttpRequest and configuration.

Therefore, when testing Basic challenges:
- Use a plain HTTP client or a `MockMvc` request **without** simulating AJAX headers if you want to verify the default challenge.
- If custom JSON errors are needed for an SPA, verify `AuthenticationEntryPoint` interaction on the real filter chain.
- Do not assume every response missing a challenge was stripped by a proxy; check the entry point and request conditions of the active version.

This is an **implementation exception** worth knowing; not a reason to treat RFC 9110's 401 rule as invalid. If an API requires strict spec compliance, provide the appropriate challenge via a custom entry point for those paths/clients.

## 9. Complete Java 17+ Example: Two Endpoints (Basic and Bearer) with Separate Challenges

Lab goal: **without needing a real Authorization Server or JWT signing infrastructure**, still observe Spring Security Basic + OAuth2 Resource Server Bearer challenges. A **mock** `OpaqueTokenIntrospector` handles two fixed tokens so we can verify HTTP statuses and headers. **For localhost learning only; never use this kind of static-token introspector in production.**

The lab uses Java 17, Spring Boot **3.3.12**, Spring Security Servlet, and Spring Test. The API has:
- `GET /basic/report`: valid Basic username/password returns `200`.
- `GET /basic/admin`: Basic user `reader` lacks `ROLE_ADMIN`, returning `403`.
- `GET /bearer/read`: Bearer token requires `SCOPE_reports.read`.
- `GET /bearer/write`: Bearer token requires `SCOPE_reports.write`.

### 9.1. Create the Gradle Project

~~~text
auth-challenge-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/challenge/
    │   ├── ChallengeApplication.java
    │   ├── SecurityConfig.java
    │   └── ProtectedController.java
    └── test/java/demo/challenge/
        └── ChallengeSecurityTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'auth-challenge-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
~~~

You can generate the Gradle Wrapper for your environment, or run `gradle test`/`gradle bootRun` if a compatible Gradle is installed. This is a **Servlet application**, not WebFlux.

### 9.2. Application Entry Point

`src/main/java/demo/challenge/ChallengeApplication.java`:

~~~java
package demo.challenge;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChallengeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChallengeApplication.class, args);
    }
}
~~~

### 9.3. Two Separate SecurityFilterChains

`src/main/java/demo/challenge/SecurityConfig.java`:

~~~java
package demo.challenge;

import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password(encoder.encode("lab-password-123"))
                        .roles("USER")
                        .build());
    }

    // /bearer/** only accepts OAuth2 Bearer handled by Resource Server.
    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/bearer/**")
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/bearer/read")
                            .hasAuthority("SCOPE_reports.read")
                        .requestMatchers("/bearer/write")
                            .hasAuthority("SCOPE_reports.write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .opaqueToken(Customizer.withDefaults()))
                .build();
    }

    // /basic/** only uses HTTP Basic with a dedicated realm.
    @Bean
    @Order(2)
    SecurityFilterChain basicApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/basic/**")
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/basic/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(basic -> basic.realmName("Legacy Lab"))
                .build();
    }

    // Do not accidentally expose URLs outside the two demo zones.
    @Bean
    @Order(3)
    SecurityFilterChain otherPaths(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/error").permitAll()
                        .anyRequest().denyAll())
                .build();
    }

    // Local lab only: NO real OAuth Authorization Server!
    // Static tokens have no real issuer/audience/expiry/revocation.
    @Bean
    OpaqueTokenIntrospector labTokenIntrospector() {
        return token -> {
            if ("lab-read-token".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                        "report-client",
                        Map.of("sub", "report-client", "scope", "reports.read"),
                        List.of(new SimpleGrantedAuthority(
                                "SCOPE_reports.read")));
            }
            if ("lab-write-token".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                        "report-writer",
                        Map.of("sub", "report-writer", "scope", "reports.write"),
                        List.of(new SimpleGrantedAuthority(
                                "SCOPE_reports.write")));
            }
            throw new BadOpaqueTokenException("Invalid lab access token");
        };
    }
}
~~~

**How to read it:**
1. `@Order(1)` selects the Bearer chain for `/bearer/**`; `@Order(2)` selects the Basic chain for `/basic/**`; finally, the default chain denies undeclared routes (except `/error` for error handling).
2. `httpBasic(basic -> basic.realmName("Legacy Lab"))` configures the Basic challenge with a stable realm.
3. `oauth2ResourceServer(...opaqueToken(...))` uses `BearerTokenAuthenticationFilter`, `BearerTokenAuthenticationEntryPoint`, and the appropriate denied handler.
4. `OpaqueTokenIntrospector` is the **opaque access token verification point**. In the lab, it mocks tokens with two fixed strings to construct principals/authorities. **Do not equate** this with real introspection: the code intentionally omits signature, issuer, audience, expiry, user revocation, mTLS, and production conditions.
5. `STATELESS` lets each request authenticate independently; having no session does **not** make `WWW-Authenticate` meaningless.
6. We **do not disable CSRF application-wide**. The sample endpoints are all read-only `GET`s; if POST/PUT/DELETE are added later, evaluate CSRF against credentials browsers send automatically—especially Basic, cookies, or sessions.
7. `User.withUsername("reader")` has `ROLE_USER`, not `ROLE_ADMIN`. Thus `/basic/admin` with the right password receives `403`, unlike `401` from a wrong password.
8. Lab `scope` maps to authorities prefixed with `SCOPE_`. Production systems must derive scopes from verified tokens/AS, never trusting caller-supplied JSON.

**Do not deploy the lab-token model on a public server.** All tokens/passwords in this lesson are dummy learning values; never reuse them as credentials in real projects.

### 9.4. Controller Returns Content Only After Filters Authenticate/Authorize

`src/main/java/demo/challenge/ProtectedController.java`:

~~~java
package demo.challenge;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProtectedController {

    @GetMapping("/basic/report")
    public Map<String, String> basicReport(Principal principal) {
        return Map.of(
                "subject", principal.getName(),
                "result", "basic: READY");
    }

    @GetMapping("/basic/admin")
    public Map<String, String> basicAdmin(Principal principal) {
        return Map.of(
                "subject", principal.getName(),
                "result", "basic-admin: READY");
    }

    @GetMapping("/bearer/read")
    public Map<String, String> bearerRead(Principal principal) {
        return Map.of(
                "subject", principal.getName(),
                "result", "bearer-read: READY");
    }

    @GetMapping("/bearer/write")
    public Map<String, String> bearerWrite(Principal principal) {
        return Map.of(
                "subject", principal.getName(),
                "result", "bearer-write: READY");
    }
}
~~~

The controller **does not generate `WWW-Authenticate` headers itself**. When a request lacks/has invalid credentials, filters/entry points handle it before the controller. When authenticated but lacking scope, the authorization filter/denied handler rejects before the method, and the controller does not need to throw exceptions manually.

### 9.5. Testing Challenges with MockMvc

`src/test/java/demo/challenge/ChallengeSecurityTest.java`:

~~~java
package demo.challenge;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ChallengeSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void missingBasicCredentialsGetsBasicChallenge() throws Exception {
        mvc.perform(get("/basic/report"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", startsWith("Basic ")))
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("realm=\"Legacy Lab\"")));
    }

    @Test
    void wrongBasicPasswordGets401() throws Exception {
        mvc.perform(get("/basic/report")
                        .with(httpBasic("reader", "wrong-password")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", startsWith("Basic ")));
    }

    @Test
    void validBasicPasswordGets200() throws Exception {
        mvc.perform(get("/basic/report")
                        .with(httpBasic("reader", "lab-password-123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject").value("reader"))
                .andExpect(jsonPath("$.result").value("basic: READY"));
    }

    @Test
    void basicUserWithInsufficientRoleGets403() throws Exception {
        mvc.perform(get("/basic/admin")
                        .with(httpBasic("reader", "lab-password-123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingBearerGetsBearerChallengeWithoutError() throws Exception {
        mvc.perform(get("/bearer/read"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", startsWith("Bearer")))
                .andExpect(header().string(
                        "WWW-Authenticate",
                        org.hamcrest.Matchers.not(containsString("invalid_token"))));
    }

    @Test
    void invalidBearerGetsInvalidTokenChallenge() throws Exception {
        mvc.perform(get("/bearer/read")
                        .header("Authorization", "Bearer not-valid-lab-token"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("invalid_token")));
    }

    @Test
    void bearerWithReadScopeGets200() throws Exception {
        mvc.perform(get("/bearer/read")
                        .header("Authorization", "Bearer lab-read-token"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject").value("report-client"))
                .andExpect(jsonPath("$.result").value("bearer-read: READY"));
    }

    @Test
    void bearerValidButScopeInsufficientGets403() throws Exception {
        mvc.perform(get("/bearer/write")
                        .header("Authorization", "Bearer lab-read-token"))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("insufficient_scope")));
    }

    @Test
    void bearerWithWriteScopeGets200() throws Exception {
        mvc.perform(get("/bearer/write")
                        .header("Authorization", "Bearer lab-write-token"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject").value("report-writer"))
                .andExpect(jsonPath("$.result").value("bearer-write: READY"));
    }

    @Test
    void schemesAreNotInterchangeable() throws Exception {
        mvc.perform(get("/bearer/read")
                        .with(httpBasic("reader", "lab-password-123")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", startsWith("Bearer")));

        mvc.perform(get("/basic/report")
                        .header("Authorization", "Bearer lab-read-token"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", startsWith("Basic ")));
    }
}
~~~

**Expectation:** 10 tests pass with matching dependencies/versions. The focus is the assertion semantics:
- Missing Basic credentials → **401 + Basic challenge**.
- Wrong password → **401**, not 403.
- Valid Basic lacking role → **403**.
- Missing Bearer token → **401 + Bearer**, normally without `error`.
- Invalid Bearer token → **401 + invalid_token**.
- Valid Bearer token lacking scope → **403 + insufficient_scope**.
- Two schemes on separate chains **cannot substitute credentials for each other**.

**About the 403 Bearer test:** the standard handler can emit `insufficient_scope` when `OAuth2Authentication` is present and access is denied for missing authority; if you replace `AccessDeniedHandler` or write a custom `Authentication` outside the OAuth2 model, headers may differ. Tests must be tailored **to the chosen contract**, never deleting security just to "pass tests".

Run tests:

~~~bash
gradle test

# If the project has Gradle Wrapper:
./gradlew test

# Windows:
# gradlew.bat test
~~~

Do not present fabricated Gradle output as executed results; this example has not been compiled/run inside this document. With a matching project and dependencies, the assertions reflect expected Spring Security behavior. On failure, inspect the stack trace/test runner rather than disabling `WWW-Authenticate` or relaxing security matchers just to pass.

## 10. Calling the API with curl and Observing Response Headers

After running locally:

~~~bash
gradle bootRun
~~~

Open another terminal:

~~~bash
# Missing Basic credentials:
curl -i http://localhost:8080/basic/report

# With demo password (localhost only, never use with real secrets):
curl -i -u 'reader:lab-password-123' \
  http://localhost:8080/basic/report

# Missing Bearer:
curl -i http://localhost:8080/bearer/read

# Invalid Bearer:
curl -i -H 'Authorization: Bearer invalid-lab-token' \
  http://localhost:8080/bearer/read

# Valid Bearer with read scope:
curl -i -H 'Authorization: Bearer lab-read-token' \
  http://localhost:8080/bearer/read

# Valid Bearer missing reports.write:
curl -i -H 'Authorization: Bearer lab-read-token' \
  http://localhost:8080/bearer/write

# Bearer with write scope:
curl -i -H 'Authorization: Bearer lab-write-token' \
  http://localhost:8080/bearer/write
~~~

`-i` displays **HTTP response status and headers**, allowing you to observe `WWW-Authenticate`. Never use `curl -v` or `-u` commands containing **real passwords in shell history**, process arguments, or logs. In production, APIs are always protected by HTTPS.

| Request | Expected Status | What to Look for in Response? |
| --- | --- | --- |
| `/basic/report` without credentials | 401 | `WWW-Authenticate: Basic realm="Legacy Lab"` |
| `/basic/report` with correct password | 200 | JSON `result=basic: READY` |
| `/basic/admin` with user `reader` | 403 | No longer a password error |
| `/bearer/read` missing token | 401 | `WWW-Authenticate: Bearer` |
| `/bearer/read` fake token | 401 | `error="invalid_token"` |
| `/bearer/write` with read token | 403 | `error="insufficient_scope"` |
| `/bearer/write` with write token | 200 | JSON `result=bearer-write: READY` |

**Avoid misunderstanding:** the strings `lab-read-token` and `lab-write-token` **have no signature, are not issued by an AS, and are not real OAuth access tokens**. Only the custom lab introspector accepts them to illustrate HTTP behavior; never use in production.

## 11. Standalone Java 17: Reading the Scheme from Responses (Without Sending Secrets)

The following client sends no `Authorization`. It calls two local endpoints to observe HTTP 401 challenges, printing the status and **scheme name**. Create `ChallengeClient.java` in a separate directory:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;

public class ChallengeClient {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        for (String path : List.of("/basic/report", "/bearer/read")) {
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://localhost:8080" + path))
                    .GET()
                    .build();

            HttpResponse<Void> response = client.send(
                    request, HttpResponse.BodyHandlers.discarding());

            String challenge = response.headers()
                    .firstValue("WWW-Authenticate")
                    .orElse("(missing)");

            // Only to print scheme in lab: not an HTTP challenge parser.
            String scheme = challenge.split(" ", 2)[0];

            System.out.println(path + " status: "
                    + response.statusCode());
            System.out.println("Challenge scheme: " + scheme);
        }
    }
}
~~~

When the lab application from section 9 is running and requests carry no credentials, expected stdout:

~~~text
/basic/report status: 401
Challenge scheme: Basic
/bearer/read status: 401
Challenge scheme: Bearer
~~~

Compile and run on JDK 17+:

~~~bash
javac ChallengeClient.java
java ChallengeClient
~~~

**Example limitation:** `split(" ", 2)` in the client snippet merely **grabs the first token** from a simple known challenge; it is **not an RFC 9110 compliant parser** for multiple challenges/quoted params. If a server returns multiple challenges, the application must use a proper HTTP parser; do not copy this snippet to drive credential selection in a production HTTP client.

`HttpClient` is used via `newHttpClient()` normally, without `try-with-resources` on Java 17 since JDK 17's `HttpClient` did not yet implement `AutoCloseable`. HTTPS/TLS, timeouts, retry policies, and credential protection must be configured separately for production.

## 12. Switching to a Real Resource Server: JWT or Opaque Introspection

The custom introspector `labTokenIntrospector()` is strictly a **mock**. When using real OAuth2:

### 12.1. JWT Access Tokens

A Resource Server application typically uses:

~~~java
// Spring Security Servlet config snippet; not a standalone class.
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Example `application.yml` with an AS/OP providing issuer metadata:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/training
~~~

Production must also verify the API-targeted **audience**, algorithm, and appropriate trust policy; having `issuer-uri` alone does not guarantee every audience/tenant authorization check is right automatically. JWT signature, issuer, expiry, and claim/authority mapping must be tested using actually issued tokens or test tokens signed with valid lab keys.

Do not hardcode a browser-supplied JWKS endpoint, and never let an attacker change the issuer via HTTP headers to bypass token verification.

### 12.2. Real Opaque Access Tokens / Introspection

Replace the lab bean with an `OpaqueTokenIntrospector` calling the trusted AS's introspection endpoint:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.org/oauth2/introspect
          client-id: reports-api
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

When running for real, you must **remove the custom lab introspector bean** if you want Boot auto-config to connect to the endpoint. Keeping that bean may cause the properties above not to take effect as expected. `INTROSPECTION_CLIENT_SECRET` is the secret for the resource server calling introspection, **not an end user's password**. Protect it with a secret manager/HTTPS; never log tokens/introspection credentials.

When a token is revoked or inactive, the resource server should return `401` with an appropriate Bearer challenge. When a token is active yet lacks scope, return `403`; both must be tested. Do not treat `active=true` as sufficient if the token lacks audience/resource binding required by policy.

### 12.3. Basic Is Not OAuth Client Authentication Everywhere

An OAuth AS may require confidential clients to authenticate with HTTP Basic at the **token endpoint**, e.g. `client_id:client_secret`. That is a distinct Basic relationship from user/password auth on a resource server. Do not infer from an API's `WWW-Authenticate: Basic` that it is an OAuth Authorization Server. Each endpoint needs its scheme, principal, credentials, and permissions clearly documented.

## 13. Customizing Error JSON Must Still Respect Headers

In REST APIs, clients often want a standardized JSON body, for instance:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication required"
}
~~~

**JSON bodies and `WWW-Authenticate` are not mutually exclusive**: the body helps humans/apps read errors, while the header helps HTTP clients pick the scheme. When using a custom entry point, avoid:

~~~java
// BROKEN illustrative snippet (do not use): missing WWW-Authenticate in 401.
response.setStatus(401);
response.getWriter().write("{\"error\":\"unauthorized\"}");
~~~

If a JSON body is needed, **delegate** to `BasicAuthenticationEntryPoint`/`BearerTokenAuthenticationEntryPoint` or configure an implementation that fulfills the proper challenge/status, then write the body **only if the response is not committed and the protocol allows it**. Do not recklessly call `sendError()` after writing headers/body, because container error handling may alter the response.

For Bearer, the framework may emit `WWW-Authenticate` with parameters depending on `BearerTokenError`; preserve this header. A generic middleware/exception handler should not overwrite every `AuthenticationException` into a challenge-less `401`.

**Watch error information:** responses must not expose passwords, raw tokens, private keys, sensitive JWT claims, introspection payloads, table names, or stack traces. You can return a `requestId` and generic error code while logging internal causes per policy (redacted).

## 14. Gateway/Proxy: Headers Can Be Stripped or Altered

If there is a CDN/WAF/API Gateway/Ingress:
- Verify `Authorization` **reaches the right service**. Some proxies strip/override this header based on the proxy's own authentication configuration.
- `WWW-Authenticate` in responses must reach the HTTP client intact; RFC 9110 specifies proxies **must not arbitrarily modify** this field when forwarding responses.
- Distinguish `401` from the **API origin** versus `407` from a **proxy**; use response headers, trace IDs, and safe logs to find where denial occurred.
- Never allow internet clients to inject "authenticated" headers like `X-Authenticated-User` and have the backend trust them without a trust boundary.
- With SSO/browsers, a custom SPA may not want a native Basic dialog; configure behavior per endpoint, avoiding advertising Basic challenges on every route error when the app actually uses cookie/form login only.
- If a gateway performs auth upfront and the backend has separate auth, align scheme/realm/error/403 policies consistently across both layers. Never leave a request returning `Basic` from the gateway and `Bearer` from the backend by accident.

### 14.1. Caching Mistakes and Header Security

Auth responses carry sensitive privilege context:
- `Cache-Control: no-store` is appropriate for sensitive responses; verify `401/403` responses are not cached incorrectly across users/credentials.
- Never embed tokens in URL query/fragments; the `Authorization` header reduces URL leakage, though it can still be logged at gateways if full-header logging is enabled.
- Use HTTPS/TLS, restrict cross-origin redirects, and never forward credentials to unfamiliar hostnames.
- Use structured log formats for `status`, `route`, `scheme`, `requestId`, and categorized error reasons without logging full `Authorization`.
- When a token expires, the client may obtain a new one from the AS per policy; do not infinitely auto-retry every 401 or fall back to Basic passwords without approval.

## 15. Troubleshooting: Getting an Unexpected Status

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| `401` without `WWW-Authenticate` | Custom entry point/handler; AJAX-specific Basic behavior; proxy stripping; committed response | Inspect network response and actual entry point |
| `302` to `/login` instead of `401` | Form login/default entry point active on chain | Check `SecurityFilterChain` matchers, `formLogin`, and request media |
| `401 Basic` when API is expected to use Bearer | Wrong chain matched, gateway advertising Basic | Check `@Order` and `securityMatcher` |
| `401 Bearer invalid_token` when JWT parses fine | Wrong issuer, signature, expiry, audience, or token revocation | Check token validation, not just JWT decoding |
| `403 Bearer insufficient_scope` | Token active but missing properly mapped `SCOPE_*` | Check scopes/authorities and authorization policy |
| `403` despite correct Basic password | User authenticated but missing role/permission; or CSRF on unsafe request | Check exception category, do not force to 401 |
| `400 Bearer invalid_request` | Malformed/duplicate header, token sent in multiple places | Check `DefaultBearerTokenResolver` and client |
| `401` after token refresh | Client sending refresh token as Bearer access token; new token invalid | Send only **access tokens** to the resource server |
| `WWW-Authenticate` parse error on client | Multiple challenges, commas in params, quoted-string | Use RFC-compliant library, avoid naive splitting |
| Browser shows unwanted password popup | Basic challenge sent to browser page/XHR | Separate API/browser auth or proper custom entry point |
| Login succeeds yet API still returns 403 | Authentication and authorization are two separate steps | Check permissions, scopes, tenant, policy |
| Proxy returns 407 | Proxy requiring credentials | Inspect `Proxy-Authenticate`, do not change API code |
| Error handler returns same JSON 401 for everything | Handler overwrites status/header | Keep authentication and access-denied paths separate |

## 16. Production Test Matrix to Add

Alongside the section 9 MockMvc lab, production needs to verify:

1. **No credentials:** right status, right scheme, never leak `invalid_token` nonsensically when no token was sent.
2. **Wrong/right Basic:** wrong password → 401; right password → 200 or 403 by role; stable realm.
3. **Invalid Bearer:** wrong issuer, expired, revoked, invalid signature, wrong audience → never reaches controller.
4. **Bearer insufficient scope:** valid token with scope A lacking B → 403; scope shown in challenge only when policy permits.
5. **Object-level denial:** token has sufficient scope but does not own the object → 403/404 per policy, no data leak.
6. **Multiple/unknown schemes:** handling clients that do not understand a scheme, multiple challenges and headers; no improper auth fallback.
7. **Header forwarding:** edge/CDN/gateway does not drop `WWW-Authenticate` or confuse origin/proxy headers.
8. **Correlation:** logs contain no raw `Authorization`, passwords, tokens, or session cookies; status and request ID suffice for debugging.
9. **Rate limiting:** Basic brute-force/throttling; Bearer invalid-request flooding; avoid timing/log differences enabling identity enumeration.
10. **Browser behavior:** Basic dialogs, XHR, form login, cookie sessions, and CSRF are distinct flows.
11. **TLS:** never send Basic passwords or bearer tokens over plaintext HTTP; never auto-follow cross-host redirects with Authorization.
12. **Session/CSRF:** if Basic is automatically sent by a browser to unsafe endpoints, still evaluate CSRF; `WWW-Authenticate` is not CSRF protection.
13. **Authorization Server vs Resource Server:** OAuth token-endpoint errors differ from protected API Bearer challenges; do not mix `invalid_client` with `invalid_token`.
14. **Account lifecycle:** locked/disabled accounts must not be "fixed" merely by switching 403 to 401; responses must not leak overly detailed state.
15. **Dependency updates:** re-test HTTP headers when upgrading Spring Security, changing entry points/filters, or switching proxies.

### 16.1. When Is a Separate JSON Response Needed Per Mechanism?

If an API serves diverse clients, the body can follow RFC 9457 Problem Details, while headers must reflect the exact challenge. You can standardize:
- Basic 401: `WWW-Authenticate: Basic realm="Legacy Lab"` + short JSON error.
- Bearer 401 no token: `WWW-Authenticate: Bearer`.
- Bearer 401 invalid token: `WWW-Authenticate: Bearer error="invalid_token"`.
- Bearer 403 insufficient permissions: `WWW-Authenticate: Bearer error="insufficient_scope"` when feasible.
- Basic authenticated insufficient permissions: `403`, **do not** trigger a password prompt if re-entering the password will not increase privileges.

API contract documentation needs examples of statuses, headers, and bodies. Never just write "failure returns 401", as that hides the entire distinction between missing credentials and lacking privileges.

## 17. Common Mistakes

1. **"`WWW-Authenticate` is a request header."** Wrong; it is a **response challenge**. Requests normally carry `Authorization`.
2. **"Every authentication or authorization error returns 403."** Wrong; missing/invalid credentials usually return 401, insufficient permissions usually return 403.
3. **"401 does not need a header because JSON already describes the error."** Wrong under RFC 9110; a challenge is required.
4. **"A `Bearer` token must be a JWT."** Wrong; bearer tokens can be opaque.
5. **"Expired tokens should return `insufficient_scope`."** Wrong; invalid tokens normally return 401/`invalid_token`.
6. **"A valid token lacking scope should force the user into Basic login."** Wrong; proper permissions/valid tokens per OAuth policy are needed, never downgrade schemes arbitrarily.
7. **"Basic uses Base64 so passwords are safely encrypted."** Wrong; Base64 is trivial to decode; HTTPS is mandatory.
8. **"`realm` can hold secrets to distinguish customers."** Wrong; realm is publicly visible information.
9. **"HTTP Basic and form login are the same mechanism."** Wrong; form login usually uses HTML/cookies/sessions, not necessarily a Basic challenge.
10. **"Having `Authorization: Bearer` means every Spring API verifies tokens automatically."** Wrong; Resource Server/validators and issuer/audience/scope configs are required.
11. **"`403` must always carry `WWW-Authenticate`."** Wrong; it may, but it is not a universal mandatory rule.
12. **"`scope` is a comma-separated list."** Wrong in Bearer challenges; scopes are typically space-separated inside one quoted string.
13. **"A challenge with a comma means multiple schemes."** Wrong; commas also separate params, requiring a proper parser.
14. **"You can log `Authorization` to debug 401s."** Wrong; logging credentials risks leakage and hijacking.
15. **"A proxy 407 is the API server returning 401."** Wrong; `Proxy-Authenticate` is a separate flow.
16. **"Changing 403 to 401 so the browser asks for the password again fixes the error."** Wrong; if already authenticated with insufficient permissions, the same password will not solve it.
17. **"Requests missing a token return `invalid_token` by default."** RFC 6750 recommends omitting error codes when no authentication info is present.
18. **"Having the scope grants access to every record."** Wrong; tenant/ownership and business permissions must still apply.
19. **"HTTP Basic has no CSRF because there are no cookies."** Potentially false if the browser caches and auto-sends Basic credentials to unsafe endpoints; evaluate your threat model.
20. **"Writing a 200 test is enough."** Wrong; test 400/401/403, challenge headers, invalid/scope cases, and proxy/browser behavior.

## 18. Self-Check Questions

**Q1.** An API receives a GET without `Authorization` and returns `401` with no `WWW-Authenticate`. What is wrong?  
**Answer:** Under HTTP authentication semantics, 401 must contain at least one challenge applicable to the resource.

**Q2.** Does `WWW-Authenticate: Basic realm="Finance"` send the password to the client?  
**No.** It only advertises the scheme/realm. Any password resides in the `Authorization: Basic ...` request header, and TLS is still required.

**Q3.** A client sends an expired access token. Which Bearer error should the resource server use?  
**`invalid_token`**, usually with status 401, not insufficient_scope.

**Q4.** A verified valid token has `reports.read` while the endpoint needs `reports.write`. Which status?  
**403**, optionally with `Bearer error="insufficient_scope", scope="reports.write"`.

**Q5.** Basic password is correct, yet user `reader` calls an `ADMIN`-only endpoint. Should 401 be returned?  
**Usually no.** The user is authenticated; lacking the role yields 403.

**Q6.** Does `407 Proxy Authentication Required` use `WWW-Authenticate`?  
**No.** Proxies use `Proxy-Authenticate`; clients send `Proxy-Authorization`.

**Q7.** Is `WWW-Authenticate: Bearer` without a realm invalid?  
**No.** `realm` is optional for Bearer; Basic challenges require a realm.

**Q8.** Should `String.split(",")` be used to parse all Bearer challenges?  
**No.** Commas separate params or challenges, and quoted-strings follow specific rules.

**Q9.** A Bearer token is a JWT whose payload decodes fine, yet its signature is invalid. Is that `insufficient_scope`?  
**No.** The token fails authentication, so it falls under `invalid_token`.

**Q10.** An API puts a secret key in the URL to avoid adding `Authorization`. Is this good design?  
**No.** Credentials in URLs leak easily through logs/history/proxies; use headers per contract over HTTPS.

### Checklist for Designing API Authentication Responses

- [ ] Every origin-server 401 has `WWW-Authenticate` with at least one appropriate challenge.
- [ ] `Authorization` requests use the exact scheme; Basic and Bearer are not mixed.
- [ ] Basic `realm` is clear, stable, and contains no sensitive data.
- [ ] Bearer no-token 401 leaks no extra error; invalid_token is 401; insufficient_scope is 403.
- [ ] Choose 400/401/403 status by cause rather than one generic code.
- [ ] AuthenticationEntryPoint and AccessDeniedHandler separate responsibilities cleanly.
- [ ] Custom JSON handlers preserve status and challenge headers.
- [ ] SecurityFilterChain matchers/priority are exact; no Basic popups triggered on Bearer-only APIs.
- [ ] JWT/opaque tokens are verified strictly for trust, lifetime, audience, and scope; never use lab introspectors in production.
- [ ] Enforce HTTPS, never log passwords/tokens/Authorization; verify proxies do not strip challenges.
- [ ] Test missing/invalid/valid credentials, insufficient permissions, and multiple challenges.
- [ ] Evaluate business authorization and CSRF on browser credentials separately.

## 19. Official References

- [RFC 9110 — HTTP Semantics `11.3, `11.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-11.6.1): `WWW-Authenticate`, `Authorization`, `401`/`403`, and distinguishing `407`.
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617.html): Basic, realm, Base64, Unicode, and `charset="UTF-8"`.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer challenge, `invalid_request`, `invalid_token`, `insufficient_scope`.
- [Spring Security 6.5 — Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html): `BasicAuthenticationFilter`, `BasicAuthenticationEntryPoint`, special AJAX behavior.
- [Spring Security 6.5 — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/): `BearerTokenAuthenticationFilter` and Bearer challenge.
- [Spring Security 6.5 — Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector`, auth mapping, and introspection.
- [Spring Security 6.5 — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html): error-to-header behavior.
- [Spring Security 6.5 — BearerTokenAccessDeniedHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html): handling `403` and `insufficient_scope`.
- [Spring Security Test — MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/): testing authentication and status/challenges.

**Conclusion:** `WWW-Authenticate` is the **server's challenge**, whereas `Authorization` is the **client's supplied credentials**. HTTP Basic uses `Basic realm="..."` with Base64 username/password that must be protected by HTTPS; OAuth Resource Server uses `Bearer` with `invalid_token` or `insufficient_scope` errors according to cause. Ensure **401s carry the right challenge**, **403s reflect insufficient permissions**, and use the proper Spring Security entry points and access-denied handlers so the HTTP contract remains intact.