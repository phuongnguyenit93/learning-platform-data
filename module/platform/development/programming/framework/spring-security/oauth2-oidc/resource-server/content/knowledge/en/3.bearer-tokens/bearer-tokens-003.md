# BearerTokenResolver and DefaultBearerTokenResolver in Servlet

In a **Spring Security OAuth 2.0 Resource Server** application using the **Servlet stack** (Spring MVC, `HttpServletRequest`), a client typically sends an access token via an HTTP header:

```http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

For the Resource Server to validate the token, Spring Security must first **locate the token string inside the HTTP request**. That responsibility belongs to `BearerTokenResolver`. `DefaultBearerTokenResolver` is the commonly used built-in implementation, supporting standard transport via the `Authorization` header and allowing additional RFC 6750 transport methods to be enabled.

The key point upfront: **the resolver only extracts the bearer token**. It does not verify JWT signatures, call token introspection, check audience/scopes, or decide read/write permissions on resources. Those steps occur in downstream components in the security processing chain.

## 1. Where do bearer tokens fit in the authentication flow?

In OAuth 2.0, a *bearer token* is a credential that the holder can present to access a Resource Server, subject to validity conditions and authorization policies. Spring Security receives that credential through a Servlet filter:

```mermaid
flowchart TD
    A["HTTP request\nAuthorization: Bearer ..."] --> B["Spring Security FilterChainProxy"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["BearerTokenResolver.resolve(request)"]
    D --> E{"Token present?"}
    E -->|"No / null"| F["Continue filter chain\nProtected endpoints may reject"]
    E -->|"Yes / String"| G["BearerTokenAuthenticationToken"]
    E -->|"Error / exception"| H["AuthenticationEntryPoint\nAppropriate error response"]
    G --> I["AuthenticationManager"]
    I --> J["JWT decoder or opaque-token introspector"]
    J --> K{"Authentication succeeded?"}
    K -->|"Yes"| L["SecurityContext / Authentication\nEvaluate authorization"]
    K -->|"No"| H
```

`BearerTokenAuthenticationFilter` calls the resolver to retrieve the bearer token string. When a token is found, the filter creates a `BearerTokenAuthenticationToken` and passes it to the configured authentication mechanism:

- **JWT Resource Server:** typically uses `JwtDecoder` to verify the JWT's algorithm/keys, timestamps, and configured validators.
- **Opaque token Resource Server:** typically uses `OpaqueTokenIntrospector` to query the Authorization Server or appropriate introspection handler.

After authentication succeeds, Spring Security places the resulting `Authentication` into the security context so `authorizeHttpRequests` rules, `@PreAuthorize`, and application logic can use it.

Replacing the resolver means **changing where credentials are read from the request**; it does **not** turn a JWT into an opaque token, change the IdP, or automatically grant permissions to the caller.

## 2. The BearerTokenResolver interface

In Spring Security Servlet, the interface resides in the package:

```java
org.springframework.security.oauth2.server.resource.web.BearerTokenResolver
```

Its core contract is:

```java
public interface BearerTokenResolver {
    String resolve(HttpServletRequest request);
}
```

Here `HttpServletRequest` is `jakarta.servlet.http.HttpServletRequest` in applications using Spring Security 6 / Spring Boot 3. In older branches using Java EE, the Servlet namespace may be `javax.servlet`; do not mix imports between the two generations.

Outcomes of `resolve`:

| Result | Meaning in the system |
|---|---|
| Non-`null` token string | The resolver found a bearer token to pass to the authentication mechanism |
| `null` | No bearer token was found via any method supported by the resolver; the filter continues the chain |
| `OAuth2AuthenticationException` | The request contains an invalid or conflicting bearer credential representation according to the resolver's rules |

`null` **does not mean the request is allowed**. For instance, a public URL can continue processing without a token, whereas a protected URL will be rejected when unauthenticated. Similarly, returning a string from the resolver **does not mean the token has been verified**.

### A small interface on a sensitive path

A bearer token is a secret. A resolver should avoid:

- Logging raw tokens or exposing them in exceptions, URLs, or observability telemetry.
- Returning tokens from externally spoofable headers without an explicit trust contract.
- Decoding JWT payloads on its own to decide whether to accept a token source; unverified JWTs are untrusted.
- Swallowing conflicting token source errors or silently picking one token out of multiple credentials sent by the caller.

Applications usually **do not need to write a custom** `BearerTokenResolver` if clients already send standard `Authorization: Bearer`.

## 3. DefaultBearerTokenResolver: default behavior

`DefaultBearerTokenResolver` lives in the same package as the interface:

```java
org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver
```

By default, the resolver looks for the access token in the **`Authorization`** header, using the **`Bearer`** authentication scheme:

```http
Authorization: Bearer <access-token>
```

Example:

```http
GET /api/profile HTTP/1.1
Host: api.example.com
Authorization: Bearer abc.def-123_XYZ
```

The resolver extracts the string `abc.def-123_XYZ` to pass to the authentication provider. This sample string may be syntactically a bearer credential without necessarily being a valid JWT; token verification happens afterwards.

### 3.1. Token transport locations

RFC 6750 describes three common bearer token transport methods. `DefaultBearerTokenResolver` prioritizes header transport by default:

| Transport method | Example | Default state | Notes |
|---|---|---|---|
| `Authorization` header | `Authorization: Bearer <token>` | **Enabled** | Recommended approach for APIs |
| `application/x-www-form-urlencoded` form body | `access_token=<token>` in POST body | **Disabled** | Enable only when genuinely needed for legacy/specialized client compatibility |
| URI query | `GET /api?access_token=<token>` | **Disabled** | Easily leaked via logs, history, referrer headers, and telemetry |

In its default state, the resolver **does not** extract tokens from:

```http
GET /api/orders?access_token=some-token HTTP/1.1
```

or:

```http
POST /api/orders HTTP/1.1
Content-Type: application/x-www-form-urlencoded

access_token=some-token
```

Therefore, if a client only sends the token in a query parameter or form body, the Resource Server will not find a bearer token under the default configuration.

### 3.2. Header cases

| Input header | Processing behavior |
|---|---|
| `Authorization: Bearer abc123` | Extracts `abc123` |
| `authorization: bearer abc123` | Header name and scheme are case-insensitive per specification; standard resolver handles the Bearer scheme |
| Missing `Authorization` | No bearer token found → `null` |
| `Authorization: Basic Zm9vOmJhcg==` | Not Bearer → does not extract a bearer token |
| `Authorization: Bearer` or malformed Bearer value | Malformed Bearer case → appropriate authentication error |
| `Authorization: Bearer abc def` | Not a valid single bearer token representation → error |

Exact header formatting may be normalized by HTTP servers/proxies; there is no need to manually split spaces or call `substring` on raw headers in place of the resolver. Using the built-in resolver preserves Spring Security's standard Bearer formatting rules and error handling.

### 3.3. Rejecting multiple simultaneous bearer token transport methods

When parameter-based token transport is enabled, a request might carry tokens in both the header and form/query:

```http
POST /api/checkout HTTP/1.1
Authorization: Bearer token-from-header
Content-Type: application/x-www-form-urlencoded

access_token=token-from-body
```

Under RFC 6750 principles, clients **must not use multiple bearer token transport methods in the same request**. `DefaultBearerTokenResolver` checks for conflicts between the header and enabled token parameters; when multiple tokens are detected, the resolver throws an error instead of arbitrarily picking one source.

Policies like “header wins over query” or “take the first token” easily cause mismatches across proxies, frameworks, and applications. Thus, when writing a custom resolver, be explicit and generally reject ambiguous credentials.

## 4. Default configuration in Spring Security Servlet

Example of a Resource Server application accepting JWTs via the standard header:

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/status").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

When the resolver is not overridden, Spring Security uses the default bearer token resolution consistent with `DefaultBearerTokenResolver`.

Assuming a valid JWT with the `orders.read` scope satisfies the decoder's validation checks, the following request can reach authorization evaluation:

```bash
curl --request GET 'https://orders.example.com/api/orders/123' \
  --header 'Authorization: Bearer ACCESS_TOKEN'
```

`ACCESS_TOKEN` here is only a placeholder, not a usable token. JWT validators for issuer, timestamps, and audience must be configured according to the API's security guarantees; **the resolver does not replace audience validation**.

One Servlet note: if the application uses sessions/cookies for state-changing operations, CSRF must be configured appropriately. Using Resource Server for bearer APIs does not mean every HTTP flow in the same application should disable CSRF.

## 5. Changing the header the resolver reads

Some systems have a proxy/gateway that sends the bearer token in a different header, such as `Proxy-Authorization`. `DefaultBearerTokenResolver` provides the API:

```java
setBearerTokenHeaderName(String headerName)
```

Complete configuration example on the Servlet stack:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ProxyBearerSecurityConfig {

    @Bean
    BearerTokenResolver bearerTokenResolver() {
        DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
        resolver.setBearerTokenHeaderName(HttpHeaders.PROXY_AUTHORIZATION);
        return resolver;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            BearerTokenResolver bearerTokenResolver) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(bearerTokenResolver)
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

With this configuration, a request uses:

```http
GET /api/orders/123 HTTP/1.1
Proxy-Authorization: Bearer some-token
```

The purpose of `setBearerTokenHeaderName` is to **change the header name to read**, while still using the `Bearer <token>` format. It does not add a fallback to the `Authorization` header, does not verify that the proxy is trusted, and does not alter `JwtDecoder` validation rules.

To avoid ambiguity, do not enable reading from multiple headers merely for “easy compatibility.” If an architecture genuinely requires multiple sources, establish a clear contract on which sources are trusted, how conflicts are handled, and which paths may send that header.

### 5.1. Does changing the header increase privileges or reduce security?

The header name itself does not make a token more or less valid. Risk arises from **trust boundaries**:

- If `Proxy-Authorization` is populated by a trusted proxy, the proxy must strip or overwrite any client-supplied copy and the hop from proxy to API must be protected.
- If external clients can send the header directly and the API mistakes it for trusted proxy input, the header becomes a spoofing vector.
- When changing the header name, synchronize client/gateway configuration, CORS (if called from browsers), log redaction rules, and infrastructure observability.
- If the gateway performs authentication and forwards the result as an identity (rather than forwarding the bearer token), that is **a different trust contract**, not solved merely by changing the header in the resolver.

## 6. Enabling tokens from form bodies

`DefaultBearerTokenResolver` provides:

```java
setAllowFormEncodedBodyParameter(boolean allowFormEncodedBodyParameter)
```

The default setting is `false`. If you genuinely need to support a client sending tokens in an `application/x-www-form-urlencoded` body, you can enable it:

```java
@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
    resolver.setAllowFormEncodedBodyParameter(true);
    return resolver;
}
```

Example of a matching request:

```http
POST /api/legacy HTTP/1.1
Host: api.example.com
Content-Type: application/x-www-form-urlencoded

access_token=example-token
```

RFC 6750 permits form body transport only under specific conditions, including requests with a form-suitable body using `application/x-www-form-urlencoded`; in Spring Security, enabling this targets form-encoded POST requests according to the resolver's rules. Do not treat this as a mechanism to extract tokens from JSON bodies:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"access_token":"example-token"}
```

`DefaultBearerTokenResolver` is not designed to parse arbitrary JSON into an access token. Intentionally reading tokens from business DTOs mixes the authentication layer with the application handling layer, exposing tokens to body logs, validation errors, or tracing systems.

**When should you consider enabling form bodies?** Only when integrating a legacy client adhering to RFC 6750 that genuinely cannot switch to the `Authorization` header. Even then, evaluate logging, gateways, content type, body size, and ensuring tokens are not sent in multiple locations simultaneously. For new APIs, prefer the standard header.

## 7. Enabling tokens from URI queries

The resolver also provides:

```java
setAllowUriQueryParameter(boolean allowUriQueryParameter)
```

The default is `false`. If enabled:

```java
@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
    resolver.setAllowUriQueryParameter(true);
    return resolver;
}
```

Then the resolver can read:

```http
GET /api/orders?access_token=example-token HTTP/1.1
Host: api.example.com
```

This capability exists for special compatibility scenarios, **not as a recommendation to put tokens in URLs**. URLs routinely appear in:

- access logs of load balancers, reverse proxies, WAFs, and application servers;
- browser history, bookmarks, copied or shared links;
- analytics, APM, telemetry, tracing, and monitoring tools;
- certain navigation or referrer-logging scenarios depending on browser/policy;
- screenshots, operational support tickets, or error reports containing the full request URI.

Because a bearer token can be used by anyone holding it, exposing `access_token` in a URL can mean exposing the credential. If an existing legacy client uses query parameters, plan a migration to headers and ensure logs/telemetry mask the token during the transition.

Do not enable `setAllowUriQueryParameter(true)` just to work around frontend CORS errors or difficulties setting the `Authorization` header. Those issues should be fixed at the client/CORS/API gateway layer.

## 8. Can both form and query be enabled?

At the API level, both setters can be called on the same resolver:

```java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowFormEncodedBodyParameter(true);
resolver.setAllowUriQueryParameter(true);
```

This widens where a token may appear. However, the client must still **choose one token transport method per request**; a request carrying tokens in multiple places can be rejected as `invalid_request`. Enabling both modes does not mean the resolver merges or combines credentials.

In a public-facing system, the more places allowed to contain bearer tokens, the more infrastructure layers must handle and redact sensitive data. Consequently, the most maintainable and auditable configuration is usually accepting only `Authorization: Bearer`.

## 9. Writing a custom BearerTokenResolver: when is it needed?

Implementing the interface directly is useful when a system has an **infrastructure-controlled credential transport protocol** that `DefaultBearerTokenResolver` cannot express—for example, an API that only accepts tokens from a header injected by a trusted gateway under a dedicated contract.

Distinguish two cases:

1. **Different header name but still using Bearer syntax**: use `DefaultBearerTokenResolver#setBearerTokenHeaderName`; no custom class needed.
2. **Different format or different source with its own trust policy**: consider a custom `BearerTokenResolver`, while carefully controlling the data source.

The example below shows how to **wrap the standard resolver** to record non-credential request status. It does not change the token source and only serves to demonstrate the interface contract:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

public final class ObservedBearerTokenResolver implements BearerTokenResolver {

    private final DefaultBearerTokenResolver delegate =
        new DefaultBearerTokenResolver();

    @Override
    public String resolve(HttpServletRequest request) {
        String token = delegate.resolve(request);

        // You can increment a "credential present/absent" metric here.
        // Never log or tag metrics with the token itself.

        return token;
    }
}
```

Registration is similar to the earlier configuration example:

```java
http.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(new ObservedBearerTokenResolver())
    .jwt(Customizer.withDefaults()));
```

This example shows the resolver can be passed directly into `oauth2ResourceServer`. In real applications, the resolver is usually registered as a Spring bean for consistent configuration management, testing, and reuse.

### 9.1. Preserve standard error reporting

If a custom resolver reads from multiple sources, distinguish:

- **No credential present**: return `null`.
- **Syntactically valid credential present**: return the token string for Spring Security to validate.
- **Malformed/conflicting credential**: throw `OAuth2AuthenticationException` with an appropriate error code; do not silently turn error cases into `null`.

In many cases you can delegate Bearer header parsing to `DefaultBearerTokenResolver` before adding custom logic, rather than writing regexes by hand. If reading an internal header, restrict it with network configuration, gateway authentication, and edge stripping of client-supplied headers. A resolver is not the right place to build a proxy trust mechanism solely by checking a header name.

### 9.2. Do not arbitrarily forward credentials between services

Example:

```text
Browser ── Authorization: Bearer token-A ──▶ Orders API
Orders API ── ? ──▶ Payments API
```

Orders API's `BearerTokenResolver` only extracts `token-A`. It does not authorize sending `token-A` onward to Payments API. The downstream API must validate tokens issued for its own audience, with the required scopes and policies. When appropriate, Orders API should use token exchange or service credentials rather than relaying a token with the wrong audience.

Do not use a custom resolver to “let through” tokens with a different audience or issuer; that belongs to token verification and each Resource Server's security policy.

## 10. BearerTokenAuthenticationFilter and error handling

The processing flow splits into four cases:

| Case | Resolver outcome | Security system response |
|---|---|---|
| No bearer token | `null` | Continues filter chain; public endpoints may proceed, protected endpoints require authentication |
| Bearer token with bad signature/expired | Token string | JWT/opaque authentication mechanism rejects it |
| Malformed bearer token representation | `OAuth2AuthenticationException` | Authentication entry point handles error at the bearer layer |
| Two conflicting token sources | `OAuth2AuthenticationException` | Rejects request per bearer policy |

Per RFC 6750, responses typically use the `WWW-Authenticate` header with the Bearer scheme. Typical error cases:

| Error scenario | Common OAuth bearer error | Typical HTTP status |
|---|---|---|
| Missing credential for an authenticated endpoint | Bearer challenge, possibly without an error code | 401 |
| Expired, invalid, or unverifiable access token | `invalid_token` | 401 |
| Multiple token transport methods or invalid request format | `invalid_request` | 400 |
| Valid token missing required scope | `insufficient_scope` | 403 |

Illustrative response example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Exact status codes depend on error type and the application's `AuthenticationEntryPoint`/`AccessDeniedHandler` configuration. If replacing default exception handling, preserve appropriate HTTP semantics and Bearer challenges so clients can respond correctly.

Do not confuse them:

- `BearerTokenResolver` reads the token.
- `BearerTokenAuthenticationFilter` feeds the token into the authentication flow.
- `JwtDecoder` or `OpaqueTokenIntrospector` validates the token.
- `AuthorizationManager`/method security decides which operations are permitted.

## 11. Servlet behaviors to keep in mind

### 11.1. Do not confuse Servlet with Reactive WebFlux

In Spring Security Servlet, the resolver accepts `HttpServletRequest`. In WebFlux, converting tokens from requests uses a separate reactive API (such as `ServerBearerTokenAuthenticationConverter`). Do not pass a Servlet `BearerTokenResolver` into a `SecurityWebFilterChain` application expecting it to be invoked automatically.

### 11.2. Content type, POST bodies, and request parameters

Servlet has the `getParameter` API and form/query parameter parsing behavior that depends on the request and container. Therefore, enabling reading `access_token` from form bodies brings in the Servlet stack's request parameter handling. Never treat arbitrary JSON/XML/multipart bodies containing an `access_token` field as standard bearer credentials.

If a controller also uses a parameter named `access_token` for business purposes, major confusion can arise. Reserve that parameter name for protocol bearer credentials and prefer the standard header.

### 11.3. Public endpoints and malformed bearer tokens

A route declared `permitAll()` does not mean the authentication filter ignores every bearer token sent to that route. If a client sends a malformed `Authorization: Bearer ...` to a public endpoint, the filter can still detect and report an error before reaching the controller. That differs from **sending no token** to a public route.

If you need to bypass the Resource Server filter for a specific group of endpoints, design separate `SecurityFilterChain` beans with appropriate `securityMatcher` rules. Do not write a custom resolver returning `null` selectively by path to mask route/filter-chain design issues.

### 11.4. CORS, reverse proxies, and headers

Browsers must be allowed via CORS to send the `Authorization` header on cross-origin requests with preflight. Configure CORS for the required origins, methods, and headers. Moving tokens to query parameters just to avoid preflight is an unsafe choice.

If a reverse proxy strips the `Authorization` header, inspect the header forwarding configuration and ensure the proxy protects credentials properly. Do not switch to a custom header by default when the root cause is proxy misconfiguration.

## 12. Observing behavior with HTTP examples

Suppose an endpoint `GET /api/orders/123` requires the `orders.read` scope and the Resource Server uses the default `DefaultBearerTokenResolver`.

### Case A: standard header

```bash
curl -i 'https://orders.example.com/api/orders/123' \
  -H 'Authorization: Bearer VALID_ACCESS_TOKEN'
```

The resolver extracts the token and hands it to authentication. If the token validates, has the appropriate scope, and the caller is permitted to view order `123`, the request proceeds normally.

### Case B: token in query parameter

```bash
curl -i 'https://orders.example.com/api/orders/123?access_token=EXAMPLE_TOKEN'
```

The default resolver does not read tokens from the query string. A protected endpoint treats the request as unauthenticated if no other valid credential is present.

### Case C: using Basic instead of Bearer

```bash
curl -i 'https://orders.example.com/api/orders/123' \
  -H 'Authorization: Basic Zm9vOmJhcg=='
```

`DefaultBearerTokenResolver` does not extract a Bearer token from a Basic header. The outcome depends on any other authentication mechanisms configured on the `SecurityFilterChain`.

### Case D: only the renamed header is present

```bash
curl -i 'https://orders.example.com/api/orders/123' \
  -H 'Proxy-Authorization: Bearer VALID_ACCESS_TOKEN'
```

If the application still uses the default resolver, the token is not read from this header. If the application called `setBearerTokenHeaderName(HttpHeaders.PROXY_AUTHORIZATION)`, the token is found and passed to authentication.

### Case E: sending both header and query after enabling query

```bash
curl -i 'https://orders.example.com/api/orders/123?access_token=TOKEN_B' \
  -H 'Authorization: Bearer TOKEN_A'
```

If query parameter tokens are enabled, the request contains two bearer token transport methods and must be rejected rather than arbitrarily picking `TOKEN_A` or `TOKEN_B`.

## 13. Verifying custom resolvers in Servlet with unit tests

You can use `MockHttpServletRequest` from `spring-test` to demonstrate the resolver's contract without running an HTTP server:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

class BearerResolverExamples {

    private final DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    @Test
    void readsAuthorizationHeader() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");
        request.addHeader(HttpHeaders.AUTHORIZATION, "Bearer abc.def-123");

        assertThat(resolver.resolve(request)).isEqualTo("abc.def-123");
    }

    @Test
    void returnsNullWhenBearerTokenIsMissing() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        assertThat(resolver.resolve(request)).isNull();
    }

    @Test
    void ignoresQueryTokenByDefault() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");
        request.setQueryString("access_token=abc");
        request.addParameter("access_token", "abc");

        assertThat(resolver.resolve(request)).isNull();
    }

    @Test
    void detectsMultipleTokenSourcesWhenQueryIsEnabled() {
        DefaultBearerTokenResolver withQuery =
            new DefaultBearerTokenResolver();
        withQuery.setAllowUriQueryParameter(true);

        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");
        request.setQueryString("access_token=token-b");
        request.addParameter("access_token", "token-b");
        request.addHeader(HttpHeaders.AUTHORIZATION, "Bearer token-a");

        assertThatThrownBy(() -> withQuery.resolve(request))
            .isInstanceOf(OAuth2AuthenticationException.class);
    }
}
```

This example tests **extraction rules**, not JWT signatures or access permissions. To actually test the filter chain in an MVC application, send HTTP requests with an `Authorization` header through `MockMvc` using a test-configured `JwtDecoder`. Note that `SecurityMockMvcRequestPostProcessors.jwt()` primarily populates an authentication context for authorization tests and may **bypass the branch that reads bearer tokens from raw HTTP headers**; therefore, do not rely on that alone to conclude a custom resolver works properly.

## 14. Choosing a configuration for each system

| Scenario | Recommended option | Reason |
|---|---|---|
| SPA/mobile/backend clients send `Authorization: Bearer` | Keep default `DefaultBearerTokenResolver` | Standards-compliant, minimal leak vectors |
| Proxy forwards token via `Proxy-Authorization: Bearer` | `setBearerTokenHeaderName` with a protected proxy source | Changes header while keeping standard parser |
| Legacy client only sends standard form body | Consider `setAllowFormEncodedBodyParameter(true)` | Controlled compatibility; plan migration to header |
| Client wants to put token in query | Fix client first; enable `setAllowUriQueryParameter(true)` only as a controlled exception | URLs easily leak credentials |
| Gateway uses custom credential transport protocol | Custom `BearerTokenResolver` after clearly defining trust boundary | Must validate source, format, and conflicts |
| API returns 401 because JWT has wrong issuer/audience | Inspect decoder/validator config, do not change resolver | Resolver is not responsible for claim verification |
| API returns 403 due to missing scope/object permission | Inspect authorization and business policies | Resolver finished its job once the token was extracted |

### Design questions to answer

Before changing defaults, clarify:

1. Does the credential arrive via header, form, or query? Who controls that source?
2. Could a client/gateway send two credentials at once? How must the system reject it?
3. Could the token appear in URLs, body logs, traces, or error messages?
4. Which proxies/gateways are trusted to inject headers? Are there direct paths bypassing the proxy?
5. After extraction, which issuer, audience, and authorization rules will the decoder/introspector enforce?

## 15. Summary of each component's role

```text
HttpServletRequest
  |
  v
BearerTokenResolver / DefaultBearerTokenResolver
  |  reads credential per source / format rules
  v
BearerTokenAuthenticationFilter
  |  creates BearerTokenAuthenticationToken
  v
AuthenticationManager + JWT / Opaque Token provider
  |  validates token, creates Authentication
  v
SecurityContext
  |
  v
Authorization rules + Business policy
  |  decides whether resource operation is permitted
  v
Controller / Service
```

**`BearerTokenResolver` answers “where is the token in the request?”**.  
**`DefaultBearerTokenResolver` answers that using standard Bearer rules, prioritizing the `Authorization` header.**  
**JWT validation, token introspection, and authorization answer independent questions about token validity and usage permissions.**

When expanding token extraction sources, proactively design trust boundaries and conflict handling. For most REST APIs, the default configuration—accepting a single bearer token via the `Authorization` header—is the best starting point.

## References

- [Spring Security Reference — OAuth 2.0 Resource Server, Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security Reference — Bearer Token Resolution](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security API — BearerTokenResolver](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/BearerTokenResolver.html)
- [Spring Security API — DefaultBearerTokenResolver](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
