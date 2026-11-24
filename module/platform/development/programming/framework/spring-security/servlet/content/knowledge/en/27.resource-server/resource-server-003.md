# BearerTokenResolver and Choosing a Safe Token Source in Spring Security Servlet Resource Server

## 1. Problem Statement: Where Do Tokens Come From and How Much Should They Be Trusted?

An OAuth 2.0 Resource Server protects an API with access tokens issued by an Authorization Server. The client sends a token with each request; the Resource Server must **locate the right token**, **verify the token**, and then **check permissions** before executing business logic. The three steps have distinct responsibilities:

1. **Token extraction:** `BearerTokenResolver` reads a candidate token from the HTTP request, defaulting to the `Authorization: Bearer ...` header.
2. **Token authentication:** `BearerTokenAuthenticationFilter` passes the token to an authentication mechanism, such as `JwtAuthenticationProvider` and `JwtDecoder` for JWTs, or an introspection mechanism for opaque tokens.
3. **Authorization:** `authorizeHttpRequests` rules, method security, or business authorization decide whether the authenticated request is allowed to perform that operation.

**`BearerTokenResolver` only decides the source/string of the received token; it does not verify the signature, expiration, issuer, audience, scope, or permissions.** Returning a string from a resolver does not mean the token is valid.

Lesson objectives:
- Understand the role of `BearerTokenResolver` in the Servlet filter chain and the default behavior of `DefaultBearerTokenResolver`.
- Choose safe token sources: standard header, form body, query string, gateway-provided headers, and cookies.
- Know when to configure `setAllowFormEncodedBodyParameter`, `setAllowUriQueryParameter`, or an alternate header.
- Set up and test a Java 17+ / Spring Boot 3 JWT Resource Server; understand 401/403 responses and `WWW-Authenticate`.
- Prevent leaking bearer tokens via URLs, logs, referrers, caches, CDNs, or trust boundaries.

## 2. Why Must a Bearer Token Be Protected Like a Secret?

A bearer token means **whoever possesses the token can use it** within the system's scopes and validation rules. Even if a client sends the token from the right source, if it is copied from logs, URL history, or the browser, an attacker can still use it while it remains valid.

Minimum security conditions:

- Transmit access tokens only over **HTTPS/TLS** from the client to a trusted endpoint; if a proxy terminates TLS, protect backend connections and restrict access paths to the service.
- Never place tokens in URLs, query parameters, bookmarks, redirect URLs, or resource paths.
- Never include tokens in HTTP logs, APM traces, analytics, error responses, crash reports, or shared DevTools screenshots.
- Configure minimal lifetimes and scopes/authorities; validate issuer, signature, timestamps, and audience properly at the Resource Server.
- When multiple gateway/proxy/service layers exist, explicitly define which layer accepts credentials, which validates them, which forwards them, and how spoofed headers are prevented.
- Mitigate XSS and protect tokens on the client; `HttpOnly` cookies have different properties from JavaScript-held bearer tokens and introduce CSRF considerations.

## 3. How BearerTokenResolver Works in the Servlet Filter Chain

Typical flow when a client calls `GET /api/me`:

```text
Client
  |
  | GET /api/me
  | Authorization: Bearer <access_token>
  v
Servlet container
  |
  v
Spring Security FilterChainProxy
  |
  v
BearerTokenAuthenticationFilter
  |
  +-- BearerTokenResolver.resolve(HttpServletRequest)
  |      |
  |      +-- no token --> continue filter chain
  |      |                (protected endpoint may return 401)
  |      |
  |      +-- invalid bearer source/syntax
  |      |      --> OAuth2AuthenticationException / appropriate HTTP error
  |      |
  |      +-- token string extracted
  |             |
  |             v
  |      BearerTokenAuthenticationToken
  |             |
  |             v
  |      AuthenticationManager
  |        JWT decoder / opaque token introspector
  |             |
  |             +-- invalid token --> 401, invalid_token
  |             |
  |             +-- valid token --> SecurityContext
  |                                    |
  v                                    v
authorizeHttpRequests / method authorization
  |
  +-- sufficient permissions --> controller
  +-- insufficient permissions --> 403
```

Key interface in the Servlet stack:

```java
package org.springframework.security.oauth2.server.resource.web;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.AuthenticationException;

public interface BearerTokenResolver {
    String resolve(HttpServletRequest request);
}
```

The snippet above only shows the **API shape**, not a source file you need to create in your application. In actual Spring Security, `resolve` can return `null` when no token is found, return the token string when found, or throw `OAuth2AuthenticationException` (a subtype of `AuthenticationException`) when the token format or source is invalid.

When the resolver finds no token, that **does not automatically mean the request is allowed**. The request still goes through protection rules; a `permitAll` endpoint can succeed without a token, whereas `authenticated()` usually leads to the authentication entry point returning 401. Therefore, never design `BearerTokenResolver` to enforce authorization.

## 4. DefaultBearerTokenResolver: Reading the Authorization Header by Default

`DefaultBearerTokenResolver` is the standard implementation used by Spring Security OAuth2 Resource Server Servlet. By default, it looks for a token in:

```http
GET /api/me HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
```

The `Authorization` header name is standard. `Bearer` is the authentication scheme, followed by the token. OAuth 2.0 Bearer Token Usage (RFC 6750) defines bearer usage in this header; it is the **preferred method** for APIs.

Characteristics:
- By default, **does not allow `access_token` in URL query parameters**.
- By default, **does not allow `access_token` from form-urlencoded bodies**.
- The `Authorization` header is the standard token channel; options to read tokens from other sources must be explicitly enabled.
- For a header carrying the Bearer scheme with invalid syntax, or multiple competing bearer sources when extra methods are enabled, the resolver can reject the request and throw an exception rather than arbitrarily picking one value.

Example that is valid at the **extraction** level (does not mean the JWT is authenticated):

```http
GET /api/me HTTP/1.1
Authorization: Bearer demo-token.abc_123
```

Example that is not recognized as a token under default configuration:

```http
GET /api/me?access_token=demo-token HTTP/1.1
Host: api.example.test
```

Without a Bearer header, the default resolver ignores the query token above. Depending on protection rules, the Resource Server may return 401 due to missing authentication. This is **intended behavior**, not a client bug to be “fixed” by enabling query tokens.

## 5. Comparing Token Sources

| Token Source | Illustration | `DefaultBearerTokenResolver` Default | Assessment / Handling Guidance |
| --- | --- | --- | --- |
| HTTP `Authorization` header | `Authorization: Bearer TOKEN` | **Enabled** | **Preferred** for APIs/SDKs/service-to-service over HTTPS |
| Form-urlencoded body | `access_token=TOKEN` in a `POST` body | **Disabled** | Use only if protocol truly requires it and RFC 6750 conditions are met |
| URI query parameter | `/api/me?access_token=TOKEN` | **Disabled** | **Avoid** due to logs, history, analytics, referrers, caches, URL copying |
| Custom header attached by gateway | `Proxy-Authorization: Bearer TOKEN` | Must be configured | Accept only when gateway strips client headers and injects trusted header; restrict service access |
| Cookie holding a token | `Cookie: access_token=TOKEN` | **Not read automatically** | Browsers auto-send cookies; increases CSRF risk and requires a different design (BFF/session or explicit controls) |
| WebSocket/SSE with client header limits | Some client APIs cannot add an Authorization header | Do not blindly move to URL | Consider BFF/session, fetch streaming, or single-use limited tickets; avoid long-lived access tokens in URLs |

Note: supporting multiple credential transport forms simultaneously increases confusion. **Do not** build custom “try header, else try query, else try cookie” fallback logic across the entire API. Each source must have a clear threat model and scope, and must handle conflicting tokens.

### 5.1. Why Is the Header Preferred?

- The access token is not part of the URL, so it is less likely to enter browser history, referrers, or shared links.
- Standard HTTP libraries and client SDKs support `Authorization: Bearer` directly.
- This representation cleanly separates business paths/queries from credentials.
- Browsers do not automatically attach a JavaScript-managed `Authorization: Bearer` value to cross-site requests from other pages, unlike auto-sent cookies. However, **XSS can still expose the token or trigger requests**; headers do not replace frontend security.
- Reverse proxies and API gateways usually have standard mechanisms to mask or avoid logging `Authorization`; you must still **configure and verify** this rather than assuming all logs are safe.

### 5.2. When Can a Form Body Be Used?

RFC 6750 permits form-encoded bodies under strict conditions; not every JSON `POST` or multipart upload counts as a valid bearer source. When enabled on the resolver, for requests with `Content-Type: application/x-www-form-urlencoded`, the token can reside in the `access_token` field. Do not enable this option merely for legacy client convenience, especially when standard headers are already available.

Illustrative example:

```http
POST /api/legacy-action HTTP/1.1
Content-Type: application/x-www-form-urlencoded

access_token=TOKEN&action=preview
```

Even when an endpoint only accepts form POSTs, the token remains a secret; avoid body logging, APM request capture, retry logging, and request copies. If the resource server has separate authorization or CSRF rules, those must still be evaluated independently. Apply only when the client cannot send headers and all consequences are controlled.

### 5.3. Why Are Query Parameters More Dangerous?

```http
GET /api/me?access_token=SECRET HTTP/1.1
```

URLs can appear in access logs of load balancers, reverse proxies, origins, CDNs, browser history, bookmarks, shared screens, monitoring dashboards, analytics, and sometimes referrer contexts. Query tokens are also easy to copy alongside links, and it is hard to ensure every intermediary redacts them.

Adding `Cache-Control: no-store` should not be treated as a complete fix: cache headers do not remove URLs from logs or history. If a client lacks custom header support, fix the client, use a BFF, or redesign the protocol before considering `setAllowUriQueryParameter(true)`.

### 5.4. Cookies and CSRF Are a Different Design

`DefaultBearerTokenResolver` does not read cookies as bearer tokens by default. If an application writes a custom resolver reading tokens from cookies, browsers may automatically send the credential on requests, changing the **CSRF** attack surface. `SameSite` helps but does not cover the entire threat model, especially with multiple subdomains, embedded apps, or custom CORS setups.

A common pattern for browsers is **Backend-for-Frontend (BFF)**: the browser holds an appropriate `HttpOnly; Secure; SameSite` session cookie and sends requests to the BFF; the BFF stores access tokens server-side and calls Resource Servers via `Authorization: Bearer`. Browsers using cookies require an appropriate CSRF policy. Never add a “convenience feature” that reads access tokens from any cookie on any request.

## 6. Safe Configuration: Spring Boot 3 / Spring Security 6 / Java 17+

The following example uses **Spring Security Servlet**, with equivalent Maven/Gradle dependencies:
- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-oauth2-resource-server`

These examples are files **inside a Spring Boot application** that already has `@SpringBootApplication`; they are not standalone Java files run simply with `javac`. The JWT issuer below is a placeholder to explain the configuration; for integration runs, replace it with a real reachable issuer URL, JWK/signing keys, and valid tokens.

### 6.1. JWT Resource Server Reading Only the Authorization Header

File `ResourceServerSecurityConfig.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurityConfig {

    @Bean
    BearerTokenResolver bearerTokenResolver() {
        DefaultBearerTokenResolver resolver =
            new DefaultBearerTokenResolver();

        // These values are already the defaults; listed explicitly to emphasize
        // the contract accepting bearer tokens only from the Authorization header.
        resolver.setAllowFormEncodedBodyParameter(false);
        resolver.setAllowUriQueryParameter(false);
        return resolver;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            BearerTokenResolver bearerTokenResolver) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(bearerTokenResolver)
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
```

This configuration explicitly wires the resolver bean into `oauth2ResourceServer(...).bearerTokenResolver(...)`, avoiding assumptions that an arbitrary bean will always be auto-selected if the app has multiple chains or custom setups. For apps needing no token-source customization, you can **omit the bean and the `bearerTokenResolver(...)` call**; standard Resource Server configuration already uses the default header-only resolver.

File `application.yml` (example):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/training
```

`issuer-uri` must be the Authorization Server's real issuer; the Resource Server can use discovery/JWKS information to verify signatures and check issuer and validity timestamps. Configuring the right issuer **does not automatically ensure desired audience checks**: if an API requires a specific audience, configure appropriate audience validation. Token extraction and claim validation are two independent steps.

**Regarding CSRF:** the configuration above does not disable CSRF. For APIs that only accept Bearer tokens in headers and **do not** rely on credentials auto-sent by browsers, you can consider a CSRF policy matching your threat model; if the application still supports session/cookie authentication, never disable `csrf` globally out of habit. The GET examples below do not require sending a CSRF token by default.

### 6.2. Example Endpoint Requiring an Authenticated JWT

File `MeController.java`:

```java
import java.util.Map;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    Map<String, String> me(JwtAuthenticationToken authentication) {
        return Map.of("subject", authentication.getToken().getSubject());
    }
}
```

With a valid JWT, the endpoint returns JSON such as:

```json
{"subject":"alice"}
```

This is an **example body** assuming a JWT with `sub=alice`; it is not output from a placeholder token. This endpoint requires `authenticated()` under the configuration above. In real applications, you must also check permissions, scopes, and audience according to business rules; **authenticating a JWT does not mean the caller may access all data**.

### 6.3. When a Gateway Requires Using an Alternate Header

In systems with a trusted API gateway, the gateway may pass the bearer token to the Resource Server under a different header name. `DefaultBearerTokenResolver` lets you change the header name via `setBearerTokenHeaderName(...)`:

```java
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

// Only replace the bean in section 6.1 with this version when you have
// a trusted gateway contract and have verified the trust boundary.
@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
    resolver.setBearerTokenHeaderName("Proxy-Authorization");
    return resolver;
}
```

This is an **illustrative bean method snippet inside a configuration class**, not a standalone Java file: import `Bean` if placing it in a real class. Because it still uses `DefaultBearerTokenResolver`, the alternate header must still follow the `Bearer TOKEN` syntax:

```http
GET /api/me HTTP/1.1
Proxy-Authorization: Bearer eyJhbGciOi...
```

**Mandatory security condition:** external clients must never directly control headers that the backend treats as gateway-supplied information. The gateway must **strip any client-sent values of the same header name** and regenerate the required value per its policy; the Resource Server must not be exposed directly to untrusted networks; and the gateway → backend link must be protected. Otherwise, an attacker can simply send `Proxy-Authorization` directly to impersonate “approved by gateway.”

Changing the header name **does not mean the token has already been validated**. JWT/opaque tokens must still be verified by the Resource Server; never use a resolver to blindly trust a string merely because the header is named “Trusted.”

## 7. Options to Avoid Enabling Indiscriminately

### 7.1. setAllowFormEncodedBodyParameter(true)

```java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowFormEncodedBodyParameter(true);
```

This snippet is part of a bean/configuration, not a standalone class. When enabled, the resolver can accept `access_token` from a form body **for the supported request type** (typically POST `application/x-www-form-urlencoded`). The risk is that tokens enter body logs and form-processing pipelines. If a request carries tokens in both the header and form simultaneously, do not silently pick one by precedence; treat ambiguous requests as errors.

### 7.2. setAllowUriQueryParameter(true)

```java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowUriQueryParameter(true);
```

Enabling this option allows the `access_token` query source when resolver conditions are met, but increases leakage risk. Consider it only when a protocol requirement cannot be met with headers and you have performed a risk assessment with specific mitigations; in modern systems **keep it false**.

### 7.3. Do Not Write Custom Resolvers with Implicit Fallbacks

A custom resolver like the pseudocode below is an **anti-pattern** and should not be implemented:

```text
if Authorization header exists:
    use header token
else if query.access_token exists:
    use query token
else if Cookie.access_token exists:
    use cookie token
```

Problems: lack of transparency about accepted token sources, difficulty handling two conflicting tokens, accidentally enabling auto-sent browser credentials, and opening up parameter pollution or proxy normalization bugs. If business requirements truly demand multiple sources, explicitly specify which requests may use which source, reject conflicting cases, and test across every layer.

## 8. HTTP Status Codes and Layer-Accurate Errors

Token source and token validity are two orthogonal dimensions. Some scenarios:

| Request | Resolver Observation | Next Step / Typical Response |
| --- | --- | --- |
| No `Authorization` on a `permitAll` endpoint | No bearer token | Endpoint can be served normally |
| No `Authorization` on an `authenticated()` endpoint | Returns `null` | Authentication entry point; typically **401** with `WWW-Authenticate: Bearer` |
| `Authorization: Bearer` header missing token or bad syntax | Invalid bearer scheme | Typically **401**, bearer error description per Spring Security handling |
| Header has token, but bad signature / expired / wrong issuer | Resolver extracts string | Authentication rejects; typically **401**, `invalid_token` |
| Valid JWT but insufficient scope/authority | Both resolver and authentication succeed | Authorization rejects; typically **403**; may include `insufficient_scope` |
| Client sends token in query when only header is enabled | Resolver ignores query as a token source | Protected endpoint may return **401** as unauthenticated |
| Token in both header and another enabled source | Request carries conflicting sources | Resolver may reject per `invalid_request` handling |
| Gateway attaches custom header, but backend still reads only Authorization | Resolver finds no bearer | Request treated as tokenless if no other auth mechanism applies |

A standard response when a token is missing on a protected API might look like:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

When the token is actually invalid, the response might look like:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

These are illustrative examples: exact header details, `error_description`, `realm`, body, and status depend on the specific error and entry point configuration. Never expose the raw access token string, decoded private claims, secret keys, or stack traces in error responses. For insufficient permissions, never return `401 invalid_token` when the JWT already authenticated successfully; return `403` via authorization.

## 9. Testing DefaultBearerTokenResolver Directly

This is a Java 17+ unit test class using JUnit 5 and Spring Test in a project with `spring-boot-starter-test`, `spring-boot-starter-security`, and `spring-boot-starter-oauth2-resource-server`. File `BearerTokenResolverTest.java`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class BearerTokenResolverTest {
    private final DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    @Test
    void readsAuthorizationHeader() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/me");
        request.addHeader(HttpHeaders.AUTHORIZATION,
            "Bearer abc.def_ghi");

        assertEquals("abc.def_ghi", resolver.resolve(request));
    }

    @Test
    void missingHeaderReturnsNull() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/me");

        assertNull(resolver.resolve(request));
    }

    @Test
    void ignoresQueryParameterByDefault() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/me");
        request.addParameter("access_token", "query-token");

        assertNull(resolver.resolve(request));
    }

    @Test
    void rejectsMalformedBearerHeader() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/me");
        request.addHeader(HttpHeaders.AUTHORIZATION,
            "Bearer not a token");

        assertThrows(OAuth2AuthenticationException.class,
            () -> resolver.resolve(request));
    }

    @Test
    void formBodyMustBeEnabledExplicitly() {
        DefaultBearerTokenResolver formResolver =
            new DefaultBearerTokenResolver();
        formResolver.setAllowFormEncodedBodyParameter(true);

        MockHttpServletRequest request =
            new MockHttpServletRequest("POST", "/api/legacy-action");
        request.setContentType(MediaType.APPLICATION_FORM_URLENCODED_VALUE);
        request.addParameter("access_token", "body-token");

        assertEquals("body-token", formResolver.resolve(request));
    }
}
```

The tests above verify **the resolver's output**, not JWT signature verification or API permissions. Strings like `abc.def_ghi` and `body-token` are syntactically shaped test tokens; they **are not verifiable JWTs**. This distinction is critical when analyzing cases where the resolver “extracted the token” yet the endpoint still returns 401.

If using Maven:

```bash
mvn -Dtest=BearerTokenResolverTest test
```

Or Gradle in a corresponding project:

```bash
./gradlew test --tests BearerTokenResolverTest
```

Commands and task names may differ if the project has custom build logic or tests are not in the root module. All five tests are expected to **PASS** in a Spring Security 6 project with the dependencies above; there is no separate business stdout.

### 9.1. End-to-End Testing Through the Resource Server

Resolver unit tests alone are not enough. You need scenarios exercising `BearerTokenAuthenticationFilter`, JWT verification, authorization, and proxies:

| Scenario | Evidence to Verify |
| --- | --- |
| No token on protected route | 401, controller does not run, appropriate `WWW-Authenticate` |
| Valid JWT sent in Authorization | Resolver extracts right token, decoder verifies, and endpoint returns 2xx if authorized |
| Expired / bad-signature JWT | 401 `invalid_token`, does not enter controller |
| Malformed Bearer header | Structured bearer error, raw token not logged |
| Token only in query | Not authenticated via query source when disabled by default |
| Token only in form | Not authenticated via form source when disabled by default |
| Header + query/form when secondary source enabled | Classified as ambiguous request, rejected when policy forbids |
| Spoofed gateway header from the Internet | Gateway strips client-supplied value; backend does not blindly trust |
| Valid JWT but missing scope | 403 from authorization, not misdiagnosed as a resolver failure |
| Browser CORS preflight | `OPTIONS`/CORS handled properly; client permitted to send Authorization header to allowed origin |
| Logs, tracing, reverse proxy/CDN | No token in URLs, query logs, request logs, or trace exports |

Manual HTTP testing with cURL (replace `VALID_TOKEN` with a real token in your test environment and avoid leaking secrets into shell history/logs):

```bash
# Missing token on protected endpoint: typically 401.
curl -i https://api.example.test/api/me

# Valid token via standard header: may return 200 if audience/permissions match.
curl -i https://api.example.test/api/me \
  -H 'Authorization: Bearer VALID_TOKEN'

# Token with bad signature/expired/invalid: typically 401.
curl -i https://api.example.test/api/me \
  -H 'Authorization: Bearer invalid-token'

# Query token is ignored by default: typically 401.
curl -i 'https://api.example.test/api/me?access_token=invalid-token'
```

**Never run the query example with a real access token** because doing so puts the token into the URL. For integration tests, use dummy tokens in negative cases, protect test secrets in an appropriate secret store/fixture, and scrub/redact sensitive data in CI logs. The cURL commands above only illustrate the flow, not real responses from a fictitious issuer/host.

## 10. Troubleshooting Workflow for Bearer Token Extraction Failures

1. **Inspect the request at the client first:** does the `Authorization` header have the proper `Bearer` scheme and token; or is it using URL/query/form/cookie instead of the standard header?
2. **Check CORS and the browser:** did the request actually send the custom header to the API, did `OPTIONS` preflight pass proxy/CORS config, or did the frontend mistakenly move the token to a cookie/query?
3. **Identify the SecurityFilterChain:** is the request hitting the chain configured with `oauth2ResourceServer`; which resolver is attached to that chain? An app with multiple chains should never assume one bean applies to all of them.
4. **Separate resolution from verification:** did the resolver return `null`, throw an exception, or return a string? If it returned a string, did the decoder/introspection reject the token due to signature, issuer, expiry, audience, or introspection network issues?
5. **Cross-check the error contract:** 401 means missing or invalid authentication; 403 means authenticated but insufficient permissions. Check `WWW-Authenticate` before guessing from the response body.
6. **Verify every trust boundary:** does the gateway strip/overwrite custom headers? Can the backend be called directly? Do logs mask `Authorization` and other token headers?
7. **Run regression tests:** valid header, bad token, disabled query/form, spoofed header, expired token, missing scope, browser/CORS API. Confirm failed requests produce no side effects.

### Common Implementation Mistakes

- Assuming `BearerTokenResolver` validates JWTs; in reality it only extracts the string.
- Enabling `setAllowUriQueryParameter(true)` because one client lacks header support.
- Reading tokens from cookies while ignoring CSRF or treating cookies identically to headers.
- Logging full `Authorization`, `Proxy-Authorization`, or URLs containing `access_token` for debugging.
- Switching to an “internal” header without having the gateway strip client-supplied headers.
- Enabling form-urlencoded tokens on all POSTs without considering body logging or requests sending both header + form.
- Skipping the `aud` claim check because issuer/JWKS already passed.
- Confusing a 401 expired token with a 403 missing scope/authority.
- Believing a header token is immune to XSS or non-TLS networks.
- Writing a custom resolver that falls back to query/cookie without a security contract.

## 11. Token Source Decision Checklist

- [ ] For standard APIs, accept `Authorization: Bearer TOKEN` over HTTPS and keep query/form options at their default false.
- [ ] Allow other sources only with a clear protocol rationale, narrow endpoint/client scope, and tests.
- [ ] If using a custom gateway header, the gateway strips client-set headers and the backend trusts only requests arriving from the protected gateway.
- [ ] If browsers use cookies as credentials, review CSRF, SameSite, Secure, HttpOnly, and BFF/session architecture.
- [ ] The Resource Server validates signature/introspection, issuer, expiry, audience, and scopes/permissions independently of token extraction.
- [ ] CORS, reverse proxies, logs, APM, metrics, caches, and CI never expose bearer tokens.
- [ ] Both resolver unit tests and filter-chain/HTTP 401/403 integration tests exist, including disallowed sources.
- [ ] Never put long-lived access tokens in URLs or error responses.

**Remember:** In Spring Security Servlet Resource Server, `DefaultBearerTokenResolver` **reads bearer tokens from the `Authorization` header by default**, while form body and query sources are disabled. Keep this safe default, widen token sources only when truly necessary, and verify trust boundaries before changing headers. Even when the resolver succeeds, the JWT or opaque token must still be **authenticated and authorized** in subsequent steps.
