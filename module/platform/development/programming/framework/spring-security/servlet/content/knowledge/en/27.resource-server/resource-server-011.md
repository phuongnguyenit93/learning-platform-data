# Bearer Error Responses, WWW-Authenticate, and Limiting Information Disclosure in Spring Security Servlet Resource Server

## 1. Scenario: An API Receiving Bearer Access Tokens

When Spring Security Servlet acts as an **OAuth 2.0 Resource Server**, the application receives requests from clients carrying an access token, usually in the header:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...<illustrative-token-string>
~~~

The Resource Server must authenticate the token, verify whether the token is accepted for this API, and determine whether the caller has sufficient permissions. Error cases differ:

- The client **did not supply** credentials for an endpoint requiring authentication.
- The client sent an **expired, revoked, wrongly signed, or invalid** token.
- The client sent a **malformed** Bearer request or tried supplying tokens via multiple conflicting methods.
- The token **authenticated validly** yet lacks the scope/permission for the specific action.
- The gateway, application, or downstream hit a **system error** unrelated to the token.

Responses should help clients react properly while avoiding turning the API into an information leak about tokens, accounts, policies, and internal infrastructure.

**The two most important signals** are the HTTP status (400/401/403) and the `WWW-Authenticate` response header. OAuth 2.0 Bearer Token Usage (RFC 6750) specifies Bearer error parameters. HTTP authentication semantics further define the role of `401 Unauthorized` and authentication challenges in `WWW-Authenticate`.

> Despite its historical name, `401 Unauthorized` actually means “not properly authenticated,” not “authenticated but lacking permission”; the latter is typically `403 Forbidden`.

## 2. What Is the WWW-Authenticate Header?

`WWW-Authenticate` is a **response header** sent by the server to indicate the authentication scheme applicable to a resource. When an endpoint accepts OAuth 2.0 Bearer only, the challenge looks like:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
Cache-Control: no-store
~~~

Components:

- **`Bearer`**: the authentication scheme name. This is a *challenge*, distinct from the `Authorization: Bearer <token>` header sent by the client in the request.
- **`realm="api"`**: a server-chosen protection scope name. Realm hints at the credential scope; it is **not** an issuer, tenant ID, OAuth scope, or token endpoint URL. Set a fixed value containing no secrets.
- **`error="..."`**: standardized Bearer error code, such as `invalid_request`, `invalid_token`, or `insufficient_scope`.
- **`error_description="..."`**: human-readable error sentence; *optional* and usually best omitted or kept minimal to avoid leaking details.
- **`error_uri="..."`**: public documentation URL describing the error; *optional*, use only fixed trusted URLs.
- **`scope="reports.read"`**: hints at the required scope in an `insufficient_scope` context; *optional*. Values can be space-delimited scopes, though publishing scopes can sometimes reveal policy structure.

Example challenge with an error code:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api", error="invalid_token"
Cache-Control: no-store
~~~

Or with insufficient scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="api", error="insufficient_scope"
Cache-Control: no-store
~~~

HTTP header names are **case-insensitive**; parameter examples follow familiar Bearer conventions. The server must emit valid headers and never concatenate user-controlled strings directly into `realm`, `error_description`, or `error_uri`.

**Not every `403` should carry `error="insufficient_scope"`.** A user denied by business policy, account status, or an ACL does not necessarily lack an OAuth scope. Emit that code only when the application knows for sure the caller holds a valid OAuth token yet lacks the required scope/permission.

## 3. Error Classification According to RFC 6750 and HTTP

| Scenario | Typical Appropriate HTTP Status | Bearer Challenge | What the Client Should Do |
| --- | --- | --- | --- |
| Missing Bearer token on protected endpoint | `401` | `Bearer realm="api"` (usually **without `error`**) | Authenticate/authorize to obtain a token |
| Expired, unverified, or rejected token | `401` | `error="invalid_token"` | Obtain a fresh token / re-authenticate if permitted; do not retry endlessly |
| Malformed Bearer request or conflicting token transports | `400` | `error="invalid_request"` when caused by Bearer parsing | Fix request syntax; do not treat as a scope error |
| Valid OAuth token lacking scope for the resource | `403` | `error="insufficient_scope"`; may include `scope` | Request appropriate permissions or stop |
| Valid caller denied by business authorization / ACL | `403` | Need not emit Bearer error/scope codes | Handle resource permissions; do not guess missing scopes |
| Resource does not exist | `404` (after auth/authz if required) | Usually not a Bearer error | Check resource/path per permissions |
| Authorization server / JWK endpoint outage or internal API error | `5xx` depending on case | Should not pretend to be `invalid_token` when token was not verified | Bounded retry; monitor incident |

### 3.1. Missing Token — Minimal Challenge

A request to `/api/reports` without `Authorization` typically receives:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
~~~

RFC 6750 recommends **omitting `error` or error descriptions** if the request simply lacks authentication credentials. The client only needs to know Bearer authentication is required. Never return “user unknown,” “token missing for admin,” or internal policy lists.

If a route is `permitAll()`, a tokenless request can return 200; not every endpoint must issue a challenge. If a request sends an **invalid** token to a public route, the Resource Server filter may still attempt to validate it and fail: `permitAll()` governs **authorization**, not necessarily skipping **authentication filters**.

### 3.2. Invalid Token — invalid_token

Reasons can include a tampered token, expiration, invalid issuer, failed signature verification, revocation, or wrong target resource. For an unaccepted token, the response is typically:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api", error="invalid_token"
~~~

You do not need to expose the exact sub-reason publicly. Strings like these cause leaks if returned verbatim: `signature verification failed for key id=...`, `unknown tenant xxx`, `token for user alice@example.test revoked at 12:03`, or decoder stack traces.

**Never automatically treat every `JwtDecoder` error as a bad token.** JWK discovery/cache/authorization-server outages or network timeouts are infrastructure errors. Internal observability must distinguish operational failures from authentication failures; never turn every exception into “invalid token” forcing users to log in again.

### 3.3. Malformed Bearer Request — invalid_request

RFC 6750 uses `invalid_request` for structural errors in requests carrying access tokens—such as missing required transport parameters, duplicate parameters, or sending tokens via multiple methods in one request. The recommended status is **`400 Bad Request`**.

Not every malformed Authorization header triggers the exact same exception or status across all server/proxy versions. The Servlet container may reject it earlier; `BearerTokenResolver` may or may not detect certain syntax errors. When testing, observe **which layer actually raises the error** rather than promising every malformed string yields `400 invalid_request`.

Sending bearer tokens in query strings is discouraged because they leak via logs, history, referrers, and analytics. Spring Security's `DefaultBearerTokenResolver` prefers the `Authorization` header and rejects URI query parameters unless explicitly enabled; never loosen those options just to accommodate misconfigured clients.

### 3.4. Valid Token Lacking Permissions — insufficient_scope

If a valid JWT holds `profile.read` scope while `/api/reports` requires `reports.read`, the response may be:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="api", error="insufficient_scope"
~~~

An implementation may also suggest `scope="reports.read"` if that is useful public information. However, scopes like `billing.admin` or internal role names can expose authorization design; consider omitting them. **Never return raw `Authentication.getAuthorities()` or full lists of scopes a user has or lacks.**

A `403` is normally not fixed by refreshing **the same scopes**; the client needs additional permissions or consent via a valid flow, or must halt the operation. Clients cannot escalate privileges on their own merely because the server hinted at a scope name.

## 4. Distinguishing OAuth Bearer Errors from Other Errors

### 4.1. Access Tokens Differ from Refresh Tokens and ID Tokens

A Resource Server normally validates an **access token** received via `Authorization: Bearer ...`. The Authorization Server's `/token` endpoint handles token issuance/refresh and has its **own OAuth error model** (such as `invalid_grant`, `invalid_client`). Do not confuse token-endpoint error responses with Resource Server challenges.

With OIDC, an **ID token** serves to authenticate a user to a client. It is not automatically an access token allowed to call every Resource Server. Sending an ID token in a Bearer header can cause `invalid_token` if issuer/audience/policies do not match.

### 4.2. 401 Differs from 403, 400, 404, and 5xx

Authentication errors, parsing errors, missing scopes, nonexistent URLs, and database errors can produce different status codes. Attach a Bearer challenge only when it matches the actual rejection mechanism—never turn every HTTP error into `401 invalid_token`.

In applications with multiple `SecurityFilterChain` beans or supporting **Basic + Bearer + sessions**, each endpoint must advertise challenges matching its actual policy. A `WWW-Authenticate: Basic ...` header cannot replace a Bearer challenge on a Bearer-only API. When a server supports multiple schemes, multiple challenges may appear; clients must parse per HTTP syntax rather than treating the whole header string as one key/value pair.

### 4.3. Never Use Error Messages to Confirm Account Existence

If errors reveal “user exists but token expired,” “client ID does not exist,” “tenant has reports.admin permission,” or “resource ID exists but is locked,” attackers can perform **enumeration**. Design responses informative enough for legitimate client flow control without exposing identities, policies, or unauthorized data.

For sensitive resources, `404` is sometimes returned instead of `403` to avoid confirming a resource's existence; this belongs to **authorization policy**, not a blanket trick of swapping status numbers everywhere. Keep behavior consistent to avoid side channels.

## 5. Which Layer of Spring Security Servlet Handles Bearer Errors?

With `spring-boot-starter-oauth2-resource-server` and a security chain enabling JWT Resource Server, typical components are:

1. **`BearerTokenAuthenticationFilter`** locates a Bearer token via `BearerTokenResolver` and invokes authentication if a token is present.
2. **`AuthenticationManager` / `JwtAuthenticationProvider` and `JwtDecoder`** (JWT case) verify and convert the token into an `Authentication`; for opaque tokens, **introspection** replaces the JWT decoder.
3. **`BearerTokenAuthenticationEntryPoint`** builds the response when Bearer authentication is required or certain authentication failures occur; typically sets HTTP 401 (or the `BearerTokenError`'s status when present) and constructs `WWW-Authenticate`.
4. **`BearerTokenAccessDeniedHandler`** handles access denied; if the authentication is a valid OAuth2 token, it can return `403` with `insufficient_scope`.
5. **`ExceptionTranslationFilter`** bridges authentication failures and access denied exceptions from downstream filters to `AuthenticationEntryPoint` and `AccessDeniedHandler`; errors thrown directly inside the bearer authentication filter have their own handling path.

Not every controller exception goes through Bearer handlers. A business `IllegalArgumentException` does not automatically become an OAuth `invalid_request`; that requires separate application error handling. If a custom `@ControllerAdvice` or reverse proxy alters responses, verify required security headers are not stripped.

### From Request to Decision

~~~text
Client
  │
  ├─ No token ─────────────────────┐
  ├─ Bad / expired token ──────────┤
  └─ Valid token ──────────────────┤
                                  ▼
                  Spring Security Servlet FilterChain
                                  │
                                  ├─ BearerTokenResolver
                                  ├─ JWT validation / introspection
                                  ├─ AuthenticationEntryPoint
                                  └─ Authorization / AccessDeniedHandler
                                  │
                   ┌──────────────┼───────────────────┐
                   ▼              ▼                   ▼
             Missing/bad      No permission      Valid token + perms
                   │              │                   │
            401 Bearer        403 insufficient_scope  Controller
            or 400 error      (when appropriate)      runs logic
~~~

The diagram is conceptual. On tokenless requests, filters may pass through to authorization before invoking the entry point; on bad tokens, the authentication filter may handle the failure immediately.

## 6. Minimal JWT Resource Server Configuration

Example using **Java 17+, Spring Boot 3.x, Spring Security 6.x**, and Servlet MVC. URIs are **illustrative**, not a real identity provider.

Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`application.yml` when using an issuer with compatible discovery metadata:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
~~~

Real applications need reachable metadata/JWKS and must verify **issuer, signature, lifetime, and the API's audience**, plus any tenant/claim requirements. Configuring `issuer-uri` supports issuer validation via Spring Security; never assume the API's audience and policies are automatically enforced if unconfigured.

File `SecurityConfig.java` illustrating one security chain:

~~~java
package com.example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

This is a **Spring configuration class**, running inside a Boot application with dependencies and a real IdP; it is not a standalone file runnable with plain JDK `javac SecurityConfig.java`. By default, when Resource Server enables Bearer support, Spring Security wires the standard Bearer handlers for authentication and access denied. Exact responses depend on version/config, filter chain, how the JWT failed, and the container.

`hasAuthority("SCOPE_reports.read")` uses standard JWT resource server mapping of OAuth2 scopes to `SCOPE_...`. If a system uses a custom `JwtAuthenticationConverter`, authority mapping may differ; test against your actual mapping.

Minimal controller in `ApiController.java` in the same package:

~~~java
package com.example.api;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Map<String, String> publicStatus() {
        return Map.of("status", "public");
    }

    @GetMapping("/api/reports")
    public Map<String, String> report() {
        return Map.of("status", "available");
    }
}
~~~

Note: the security examples only check scope on `/api/reports`; production also requires authorization per organization, user, and resource. A JWT with matching scope **does not prove** the client may view every report across every tenant.

## 7. Controlling Information Disclosure in Errors

### 7.1. Accurate Yet Minimal

| Information | Can Be Returned Publicly? | Rationale |
| --- | --- | --- |
| HTTP 401/403/400 | Yes, when semantically accurate | Client needs to decide whether to log in, request scopes, or fix the request |
| `Bearer` challenge | Yes, when endpoint uses Bearer | Tells client which credential scheme is required |
| `error="invalid_token"` | Can be | Standardized error; reveals no details on where the token failed |
| `error="insufficient_scope"` | Can be when conditions match | Tells client appropriate permissions are needed |
| `scope="..."` | Consider carefully | May expose API capability/policy names |
| Detailed `error_description` from JWT decoder | **Avoid** | May leak issuer, key ID, claims, signature, timestamps, or stack |
| Access/refresh/ID tokens, Authorization header | **Never** | Are credentials or contain sensitive data |
| Full claims, authorities, subject, email, tenant, ACL | Not by default | Leaks identity, policies, and enumeration surface |
| Random correlation ID without PII | Usually yes | Aids support tracing without exposing sensitive causes |
| Link to fixed public documentation page | Can be | Assists clients without revealing internal infrastructure |

**Limiting disclosure does not mean lying about HTTP status.** Returning the same `401` for everything makes clients refresh tokens when they actually lack a scope, or disguises an IdP `5xx` as a bad credential. Keep the **necessary error category** while stripping **sensitive technical causes**.

### 7.2. Never Reflect Attacker-Controlled Content

Never directly concatenate `request.getHeader("Authorization")`, malformed token strings, `exception.getMessage()`, or claim values into:

- `WWW-Authenticate: ... error_description="..."`,
- JSON error bodies,
- HTML error messages,
- `error_uri` URLs,
- redirect locations,
- HTTP access logs or tracing tags.

Header values follow strict syntax rules; reflecting control characters, quotes, or attacker-controlled strings can even cause header injection if the server does not block them. Use **preselected constants**, and escape/canonicalize strictly whenever dynamic parameters are unavoidable.

If a gateway or tracer logs all request headers automatically, configure **redaction** for `Authorization`, `Cookie`, and secrets. Leaks often happen in infrastructure logs/APM rather than just controller-generated HTTP bodies.

### 7.3. Internal Telemetry Can Be More Detailed, Safely

Categorize errors for operations, for example:

- `bearer_auth.missing`,
- `bearer_auth.invalid_token`,
- `bearer_auth.invalid_request`,
- `bearer_auth.insufficient_scope`,
- `jwks.fetch.timeout`.

Store **error category, random request ID, route template, timestamp, and status**; use metrics/tracing. Never log raw tokens, full Authorization headers, refresh tokens, or decoder exceptions carrying tokens/claims. Restrict log read permissions. Apply log rate limiting or sampling to prevent attacker log flooding.

For account-related errors, avoid unnecessary differences in latency, body, or headers between “user exists” and “user does not exist” if they become an oracle. Removing `error_description` alone does not eliminate every side channel.

## 8. Customizing Entry Points to Reduce Leaks Without Breaking Protocol

Most APIs should start with **Spring Security's defaults**, then measure real responses. When policy mandates stripping all technical error descriptions from challenges, customize `AuthenticationEntryPoint` to emit only **standardized error codes**.

The next example is a **replacement version** of `SecurityConfig.java` from section 6 (do not add a second `SecurityFilterChain` with the same matcher). It uses an empty response body and a fixed realm; application business errors must be handled separately.

~~~java
package com.example.api;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.AuthenticationEntryPoint;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.authentication.AbstractOAuth2TokenAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        AuthenticationEntryPoint safeBearerEntryPoint =
            (request, response, failure) -> {
                String errorCode = failure
                    instanceof OAuth2AuthenticationException oauthFailure
                    ? oauthFailure.getError().getErrorCode()
                    : "";

                String challenge = "Bearer realm=\"api\"";

                if ("invalid_request".equals(errorCode)) {
                    response.setStatus(
                        HttpServletResponse.SC_BAD_REQUEST);
                    challenge += ", error=\"invalid_request\"";
                } else {
                    response.setStatus(
                        HttpServletResponse.SC_UNAUTHORIZED);
                    if ("invalid_token".equals(errorCode)) {
                        challenge += ", error=\"invalid_token\"";
                    }
                }

                response.setHeader(
                    HttpHeaders.WWW_AUTHENTICATE, challenge);
                response.setHeader(
                    HttpHeaders.CACHE_CONTROL, "no-store");
                // Never send exception messages, tokens, or stack traces.
            };

        AccessDeniedHandler safeBearerDenied =
            (request, response, denied) -> {
                Authentication current = SecurityContextHolder
                    .getContext().getAuthentication();

                response.setStatus(
                    HttpServletResponse.SC_FORBIDDEN);

                // Only attach the OAuth scope error code when the authentication
                // is genuinely an OAuth token already verified by Spring.
                if (current
                    instanceof AbstractOAuth2TokenAuthenticationToken<?>) {
                    response.setHeader(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Bearer realm=\"api\", error=\"insufficient_scope\"");
                }

                response.setHeader(
                    HttpHeaders.CACHE_CONTROL, "no-store");
            };

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
                .authenticationEntryPoint(safeBearerEntryPoint)
                .accessDeniedHandler(safeBearerDenied));

        return http.build();
    }
}
~~~

**Why this design?**

- **Requests missing a token** usually do not carry an `OAuth2AuthenticationException` with `invalid_token`; the entry point returns `401` with `Bearer realm="api"` **without fabricating an error code**.
- **Invalid tokens** with `OAuth2AuthenticationException` and `errorCode = "invalid_token"` return `401` and the error code, **omitting `error_description`** from the decoder.
- **Malformed Bearer requests** raising `invalid_request` at the Bearer layer return `400` with the matching challenge. Note that earlier errors from a proxy/container may not reach this entry point.
- **Access denied** with OAuth2 token auth returns `403` with `insufficient_scope` per the `/api/reports` policy; for other authentication types it does not claim a missing scope.
- `response.setStatus(...)` does not generate HTML containing stack traces; the example leaves the response body empty. `Cache-Control: no-store` helps prevent caching sensitive auth responses at cache-compliant layers; still configure proxies and caching for successful payloads too.

**Limitations of this example:** checking `AbstractOAuth2TokenAuthenticationToken<?>` only proves an OAuth token authentication is in SecurityContext—**it does not prove every 403 in every application is a missing OAuth scope**. If ACL/tenant policies exist, classify by exception and business permission before emitting `insufficient_scope`. In systems with multiple chains or custom error handlers, test exact routes and error propagation. Keep a single owner responsible for setting the header so multiple handlers/proxies do not overwrite `WWW-Authenticate`.

### When Should You Keep the Default Handlers?

Use the default `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` if the application has no special requirement to strip descriptions and observed responses already satisfy policy. You can configure a fixed `realm` on those handlers via `setRealmName(...)`. Do not reimplement the framework unnecessarily; custom code must be thoroughly retested whenever Spring Security or OAuth2 providers change.

If using a **global `@ControllerAdvice`** to return `ProblemDetail` JSON, remember Spring Security filter errors can occur before the controller and thus bypass advice automatically. To keep error bodies consistent, coordinate exception handling **at the right layer** while preserving status and `WWW-Authenticate`. Never mix a JSON body with a servlet container's HTML error page.

## 9. Automated Testing: 401, 403, Challenge, and No Leaks

### 9.1. Basic Test Matrix

| Test Request | Expectation from Section 8 Safe Config |
| --- | --- |
| `GET /api/reports` without Authorization | `401`, `WWW-Authenticate: Bearer realm="api"`, empty body |
| Bad Bearer token rejected by JwtDecoder with `invalid_token` | `401`, challenge adds `error="invalid_token"`, no decoder message leaked |
| Bearer request rejected by resolver with `invalid_request` | `400`, challenge adds `error="invalid_request"` if reaching entry point |
| Valid JWT with `SCOPE_profile.read` but without `SCOPE_reports.read` | `403`, challenge includes `error="insufficient_scope"` |
| Valid JWT with `SCOPE_reports.read` | Controller executes, can return `200` |
| Request to `/api/public` without token | `200` |
| Resource server / Gateway system error | Never masquerade everything as a bad token; appropriate status, safe logs |

### 9.2. MockMvc with Java 17+ and Spring Boot 3.x

Example `SecurityErrorTest.java` in the same `com.example.api` package as the app with section 8's `SecurityConfig` and section 6's controller. Requires `spring-boot-starter-test` and `spring-security-test`. In Boot 3.x, `@MockBean` can replace the real decoder for integration tests; it is deprecated in Boot 3.4, where newer projects can use the corresponding Mockito bean-override mechanism.

~~~java
package com.example.api;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityErrorTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    JwtDecoder decoder;

    @Test
    void missingTokenHasPlainBearerChallenge() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer realm=\"api\""))
            .andExpect(content().string(""));
    }

    @Test
    void invalidTokenDoesNotLeakDecoderMessage() throws Exception {
        when(decoder.decode("bad-token"))
            .thenThrow(new BadJwtException(
                "SECRET_INTERNAL_DECODER_DIAGNOSTIC"));

        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer bad-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer realm=\"api\", error=\"invalid_token\""))
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                not(containsString("SECRET_INTERNAL_DECODER_DIAGNOSTIC"))))
            .andExpect(content().string(""));
    }

    @Test
    void insufficientScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer realm=\"api\", error=\"insufficient_scope\""))
            .andExpect(content().string(""));
    }

    @Test
    void expectedScopeAllowsRequest() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read"))))
            .andExpect(status().isOk());
    }
}
~~~

**Test scope:** the snippets depend on a Spring Boot application context with a `JwtDecoder` and the example config. Spring Security Test's `jwt()` builds simulated authentication to test authorization/handlers, not real JWT signature verification. The bad-token test with mocked `JwtDecoder` checks the error response on the authentication path. In real environments, test tokens signed with valid/invalid keys, issuer, audience, expiry, and real IdP/JWK/introspection integration.

**Java syntax note on the test example:** the line-wrapped `import static` lines above may not match project formatters/compilers when wrapped after a package name; when copying into an IDE, keep each qualified import on a single line as usual. The test class/methods must live inside a Boot project with Maven/Gradle, not a plain Java program runnable with `java SecurityErrorTest`.

### 9.3. Observing Real HTTP Responses

Assuming the real application is running against a test environment issuer/endpoint:

~~~bash
# Without credentials:
curl -i https://api.example.test/api/reports

# Invalid Bearer token (illustrative string only):
curl -i -H 'Authorization: Bearer bad-token' \
  https://api.example.test/api/reports

# With a validly issued test token and sufficient scope:
curl -i -H 'Authorization: Bearer <test-access-token>' \
  https://api.example.test/api/reports
~~~

Never put real tokens in shell history, CI logs, or tickets; in CI tests use safe secret injection and configured redaction. `curl` only observes status/headers/body; it does not replace full security testing across proxies, TLS, token validation, scopes, and ACLs.

Also read `WWW-Authenticate` on failed requests. Never conclude from status alone: a `401` from reverse-proxy Basic auth differs from a `401` from Resource Server Bearer; headers and safe logs at the originating layer tell them apart.

### 9.4. Testing Adverse Cases

Beyond the happy path, test:

- No token; non-Bearer Authorization scheme; empty header, extra whitespace, malformed syntax; multiple token locations simultaneously if multiple transport methods are enabled.
- Expired access token, bad signature, wrong issuer, wrong audience, future `nbf`, key rotation, and JWK lookup failures.
- Valid Bearer token lacking scope, sufficient scope yet wrong tenant/resource; never turn every 403 into missing scope.
- Errors from authorization server / JWKS timeouts; 5xx responses or fallback handling leaking no internal details.
- Requests through gateway/CDN, HTTP/2, and custom error pages/filters; verify headers are neither stripped/overwritten nor unexpectedly cached.
- Response bodies, logs, tracing, APM, metrics, and reverse-proxy access logs **contain no access tokens, refresh tokens, or Authorization headers**, even on failure.
- Routing across multiple SecurityFilterChains; Bearer APIs must hit the right chain, entry point, and denied handler.

## 10. Common Implementation Mistakes and Fixes

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Missing token returns `403` instead of `401` | Entry point or chain replaced; route not treated as bearer-only | Check security matchers, authentication entry point, and exception translation |
| Expired token receives HTML login page | Bearer API hit a formLogin/session chain | Separate chain/API policies cleanly; ensure Bearer entry point applies |
| `401` lacks `WWW-Authenticate` | Custom handler or proxy stripped challenge | Restore valid Bearer challenge and integration test at edge |
| Bad token response includes stack trace or JWT claims | Reflected exception message into header/body | Use fixed error codes, hide descriptions, keep details in sanitized telemetry |
| Valid token lacking scope returns `401` | Handled access denied as authentication failure | Use proper AccessDeniedHandler; distinguish 401 and 403 |
| Every `403` includes `insufficient_scope` | Custom handler fails to distinguish ACL/tenant/business denial | Emit insufficient_scope only when genuinely related to OAuth permissions |
| API returns `400 invalid_request` for every JSON validation error | Conflated OAuth Bearer invalid_request with invalid payload | Separate MVC validation handling from Bearer request handling |
| Client refreshes tokens endlessly on `403` | Client assumed 403 means token expired | Refresh only under valid flow conditions; handle missing permissions separately |
| Header `scope` exposes internal privileges | Returned too much info to clients | Omit scope or publish only stable public scopes |
| Tokens/secrets appear in logs | Logged full request headers, Authorization, or exceptions | Redact at app/gateway/APM; strictly control access log permissions |
| JWT valid for issuer yet wrong audience still accepted | Missing audience validation or tenant policy | Configure audience/claims validation matching the API |
| Gateway returns a different status than Spring Security | Upstream tier rejects/transforms responses | Inspect controlled traces, status, and headers at real clients |

### Production Checklist

- [ ] Distinguish **missing credentials → 401**, **invalid token → 401 invalid_token**, **malformed Bearer request → 400 invalid_request when appropriate**, **valid token lacking scope → 403 insufficient_scope**.
- [ ] Bearer endpoints return proper `WWW-Authenticate` and gateways/error handlers do not strip it.
- [ ] When detailed descriptions are unnecessary, **omit `error_description`**, and emit `scope` only when safe and stable.
- [ ] Never leak tokens, Authorization headers, key IDs, JWT claims, users/tenants, client secrets, or stack traces in error bodies, headers, logs, or APM.
- [ ] Handle system/JWKS errors separately; never treat all errors as `invalid_token`.
- [ ] Test missing token, bad token, valid token lacking scope, valid token with scope, and ACL-blocked resources.
- [ ] Verify headers/statuses both in the Servlet filter chain and through real reverse proxies/CDNs.
- [ ] Fully validate JWT/introspection for issuer, expiry, audience, scopes/authorities, and resource policies.

**Conclusion:** `WWW-Authenticate: Bearer` is the standard HTTP/OAuth2 authentication error interface for a Resource Server. Spring Security Servlet already provides `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler`; you can customize them to expose only **status + standard error codes** without leaking decoder exceptions or tokens. Diagnostic power must come from sanitized metrics/logs and correlation IDs, never from returning sensitive internals to API callers.
