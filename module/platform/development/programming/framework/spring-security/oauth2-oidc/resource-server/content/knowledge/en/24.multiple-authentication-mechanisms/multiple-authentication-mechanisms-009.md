# Customizing Token Resolvers While Keeping Input Validation Consistent

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, an HTTP request can carry several credential types: a **Bearer access token**, HTTP Basic, an API key, a session cookie, a client certificate, or credentials forwarded by a reverse proxy. When an application starts supporting **multiple authentication mechanisms**, deciding "where to find the access token" easily becomes a weak spot: two token locations may conflict, an invalid credential may be ignored to try a weaker mechanism, or a custom resolver may accidentally bypass syntax checks Spring Security normally enforces.

This lesson focuses on **customizing token resolvers** while keeping **a consistent input-validation contract**. The emphasis is on `BearerTokenResolver` and `DefaultBearerTokenResolver` in the **Servlet stack**; in **Spring WebFlux**, the corresponding role is typically handled by `ServerAuthenticationConverter` and `ServerBearerTokenAuthenticationConverter`.

A sound design has three independent layers:

1. **Credential resolution:** Is there a Bearer token? How was it sent? Are there multiple values, conflicts, syntax errors, or prohibited channels?
2. **Token authentication:** Does the extracted token have a valid signature, issuer, audience, and lifetime, or `active=true` on introspection?
3. **Authorization:** Does the valid token hold the scopes/permissions for the specific endpoint, tenant, and resource?

**Overarching principle:** customizing where tokens are extracted **must never** turn into customizing how tokens are trusted; all valid credential paths must go through **the same input-acceptance policy** and **the same mandatory verification mechanism**.

> **Running example:** Orders API running Spring Boot 3.x / Spring Security 6.x, accepting access tokens via `Authorization: Bearer ...`, using JWTs signed by issuer `https://login.example.com`. Some legacy endpoints may use HTTP Basic or API keys under separate policies. Code snippets target Spring Security versions with matching APIs; verify against your actual version's Javadoc before integrating.

## 1. Why Does This Issue Appear with Multiple Authentication Mechanisms?

For a Bearer-only API:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

The flow is relatively straightforward:

```text
Authorization header
      |
      v
BearerTokenResolver
      |
      v
BearerTokenAuthenticationFilter
      |
      v
AuthenticationManager
      |
      v
JwtDecoder or OpaqueTokenIntrospector
      |
      v
Authentication + authorities
      |
      v
Authorization + business policy
```

Yet once HTTP Basic, API keys, or proxy tokens are also supported, questions arise:

- If a client sends a **malformed Bearer** and a **valid API key**, should the API reject or ignore Bearer and authenticate with the API key?
- If two `Authorization` headers appear, do you pick the first or the second?
- If a Bearer token appears in **both header and query parameter**, which is primary?
- If a proxy sets `X-Forwarded-Access-Token`, does the backend trust that header from external Internet clients?
- If a token looks like a JWT and the AS also supports introspection, may failed JWT validation fall back to opaque introspection?
- If an endpoint can be called with a cookie or Bearer, how are CSRF, sessions, 401/403 errors, and credential precedence designed?

**Never answer these questions with ad-hoc `if/else` branches inside a resolver.** Write down an explicit **credential contract** and enforce it across the security chain, resolver, manager, gateway, and tests.

## 2. What Does a Token Resolver Do — and Not Do?

In the Servlet stack, the interface:

```java
package org.springframework.security.oauth2.server.resource.web;

public interface BearerTokenResolver {
    String resolve(HttpServletRequest request);
}
```

`resolve(...)` extracts the raw bearer token from the request. Semantically:

- **Returns the token string** if the request carries a Bearer credential matching policy.
- **Returns `null`** when no Bearer credential is present to process.
- **Throws `OAuth2AuthenticationException`** for invalid or malformed Bearer requests at the input layer, so Spring Security can translate it into a Bearer error.

The resolver **does not** verify JWT signatures itself, call introspection to check `active`, or determine scopes/ownership.

### 2.1. Related Components

| Component | Responsibility |
|---|---|
| `BearerTokenResolver` | Locates and extracts raw Bearer credentials from Servlet requests |
| `DefaultBearerTokenResolver` | Implements standard Bearer extraction rules |
| `BearerTokenAuthenticationFilter` | Calls the resolver and triggers authentication |
| `BearerTokenAuthenticationToken` | Holds the raw token as an unverified authentication request |
| `AuthenticationManager` | Selects the authentication provider |
| `JwtAuthenticationProvider` / `JwtDecoder` | Verifies JWT signature/claims |
| `OpaqueTokenAuthenticationProvider` / `OpaqueTokenIntrospector` | Validates opaque tokens via introspection |
| `BearerTokenAuthenticationEntryPoint` | Produces Bearer error responses/challenges |
| `BearerTokenAccessDeniedHandler` | Handles insufficient permissions after authentication |
| `SecurityFilterChain` | Defines which mechanisms and authz rules apply to URLs |
| Domain authorization | Checks tenant, ownership, and business state |

In WebFlux, the corresponding roles involve `ServerAuthenticationConverter`, `ServerBearerTokenAuthenticationConverter`, `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, and `SecurityWebFilterChain`.

### 2.2. Do Not Confuse Extraction with Verification

This line only extracts a string:

```java
String token = bearerTokenResolver.resolve(request);
```

Even when `token` looks like:

```text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0...
```

it is still **untrusted**. Only once `JwtDecoder` verifies signature, issuer, audience, lifetime, access-token type, and related validators may the Resource Server use claims to build authentication and authorize access.

A severe anti-pattern:

```java
// DELIBERATELY WRONG: making permission decisions from unverified payload.
String rawToken = resolver.resolve(request);
String scope = parseUnverifiedJwtPayload(rawToken).get("scope");
if (scope.contains("orders.admin")) {
    grantAdminAccess();
}
```

**Resolvers must never turn client-sent data into identity or authorities prior to verification.**

## 3. RFC 6750: Standard Contract for Receiving Bearer Tokens

**RFC 6750** specifies how OAuth 2.0 Bearer tokens are used over HTTP. The recommended method is the **Authorization request header**:

```http
Authorization: Bearer ACCESS_TOKEN
```

The spec also describes a **form-encoded body parameter** and **URI query parameter** under specific conditions; however, each request **must not use more than one token-transmission method**. In modern API deployments, the header is usually the safest and most reliable option.

### 3.1. Token Transmission Methods

| Method | Example | Recommendation for typical APIs |
|---|---|---|
| Authorization header | `Authorization: Bearer abc` | **Preferred and default** |
| Form body | `access_token=abc` in `application/x-www-form-urlencoded` | Only if contract genuinely requires it and meets spec conditions |
| URI query | `GET /api?access_token=abc` | **Avoid** due to URL logging/history/cache risks |
| Cookie | `Cookie: access_token=abc` | Never auto-treat as Bearer; needs separate browser/CSRF model |
| Custom header | `X-Internal-Access-Token: abc` | Only with a gateway trust boundary and explicit rules |
| WebSocket subprotocol/other | Per dedicated protocol | Do not blindly extend default HTTP resolvers |

### 3.2. Why Are Query Tokens Dangerous?

Example:

```http
GET /api/orders/42?access_token=secret-token HTTP/1.1
```

The token can leak into:

- Browser history and bookmarks.
- Reverse proxy/CDN access logs.
- Server request logs.
- Monitoring/tracing URL attributes.
- Copied/shared links.
- Referer headers or URL analytics systems when misconfigured.
- Cache keys and audit records.

Therefore, **never enable query-parameter Bearer tokens just to "support another client"** unless your application has a risk-analyzed exception.

### 3.3. One Credential, One Source, One Meaning

The most defensible policy:

```text
Bearer accepted source = Authorization header only

If missing:
    leave request unauthenticated
If malformed/duplicated:
    reject with Bearer input error
If syntactically acceptable:
    pass token to standard authentication manager
```

Never use a query parameter to rescue a request with a malformed Bearer header. Never use an API key to legitimize an invalid Bearer request unless the contract permits it.

## 4. DefaultBearerTokenResolver and Baseline Behavior

Spring Security provides `DefaultBearerTokenResolver` for Servlet. By default, it accepts Bearer tokens via the **Authorization header**; form body and URI query methods are not enabled just because a client sends them.

Example:

```java
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    resolver.setAllowFormEncodedBodyParameter(false);
    resolver.setAllowUriQueryParameter(false);

    return resolver;
}
```

Both setters are shown explicitly here so the policy is obvious to readers. Exact defaults and APIs are governed by the Javadoc of your project's version; never assume those setters perform cryptographic validation.

### 4.1. Useful Configuration APIs

| API | Purpose |
|---|---|
| `setAllowFormEncodedBodyParameter(boolean)` | Enable/disable reading tokens from form bodies |
| `setAllowUriQueryParameter(boolean)` | Enable/disable reading tokens from query parameters |
| `setBearerTokenHeaderName(String)` | Change the header name used for Bearer tokens in controlled proxy/gateway setups |

**Note:** `setBearerTokenHeaderName` changes the **source header**; it does not verify gateway trustworthiness or accept multiple headers in priority order.

### 4.2. What Not to Reimplement by Hand

Instead of writing manually:

```java
// DO NOT DO THIS: misses bad syntax, duplicates, and scheme checks.
String authorization = request.getHeader("Authorization");
if (authorization != null) {
    return authorization.substring(7).trim();
}
return null;
```

delegate to `DefaultBearerTokenResolver` to handle Bearer syntax according to Spring Security's managed behavior, then **wrap additional specific constraints** if needed.

The naive slicing snippet above has latent bugs:

- Headers shorter than 7 characters throw unexpected exceptions.
- `Basic ...` gets sliced into a bogus token.
- `Bearer` with no value may be handled arbitrarily.
- Tokens with spaces/invalid characters get masked by `trim()`.
- Duplicate Authorization headers go unhandled.
- Case-insensitive auth schemes and exact RFC 6750 formatting are ignored.
- Semantics distinguishing missing credentials from malformed credentials are lost.

**Do not use `trim()`, `split(" ")`, and guesswork.** Every auth scheme has its own grammar.

## 5. What Does Consistent Input Validation Mean?

For an API accepting multiple credentials, "consistent" does not mean every auth mechanism shares one parser. It means **each mechanism has a clear contract**, and all paths to the same mechanism obey **the same rules**:

1. Which source is accepted?
2. Can credentials be sent from multiple sources simultaneously?
3. May the header be repeated?
4. Are the scheme and token syntax valid?
5. On error, fail or try another option?
6. Who performs cryptographic/introspection verification?
7. Which attributes become principal/authorities?
8. On authentication failure, may a weaker mechanism run?
9. Which 401/403 status and `WWW-Authenticate` challenge are returned?
10. Do loggers, gateways, proxies, and tests all share the same credential policy?

### 5.1. Input Classification Table

| Request | Situation | Expected Bearer-only API behavior |
|---|---|---|
| No `Authorization` | No credential | Unauthenticated; protected endpoint returns 401 |
| `Authorization: Bearer abc` | Single syntactically valid token | Passed to decoder/introspector |
| `Authorization: bearer abc` | Case-insensitive scheme per HTTP | Standard resolver behavior |
| `Authorization: Bearer` | Missing token | Syntax error; never accept empty token |
| `Authorization: Bearer a b` | Contains invalid whitespace | Reject; never trim/split to fix |
| `Authorization: Basic ...` | Credential for another mechanism | Bearer resolver ignores it; chain decides |
| Two `Authorization` lines | Ambiguous | **Reject under strict policy** |
| Bearer header + query token | Multiple sources | Reject query; may explicitly reject per strict policy |
| `?access_token=abc` without header | Query-only credential | Not treated as Bearer under header-only policy |
| `X-API-Key` on bearer-only route | Out-of-contract credential | Must not bypass Bearer |
| Valid syntax, bad signature | Extraction succeeds; authn fails | **401 `invalid_token`**, no fallback |
| Valid token missing `orders.read` | Authn succeeds; authz fails | **403** per contract |

Some statuses for malformed input may be `400 invalid_request` rather than 401 depending on RFC 6750 and Spring Security handlers. **What never changes** is that a request must never authenticate successfully with ambiguous or invalid credentials.

### 5.2. Why Must `null` and Exceptions Be Distinguished?

This is one of the most critical rules when customizing a resolver:

```text
resolve(...) == null
    -> No Bearer credential for the resolver to process

resolve(...) throws OAuth2AuthenticationException
    -> Request has a Bearer input error; must report failure

resolve(...) == "token"
    -> Candidate string found; still must be authenticated
```

If a custom resolver returns `null` upon seeing malformed `Authorization: Bearer ???`, the filter may allow other authentication mechanisms to continue. Thus a Bearer input error gets **downgraded** into "no Bearer present".

**Never convert malformed Bearer into `null` to let API keys or cookies be tried.** If multiple credentials must be supported, define an explicit policy for conflicts and per-mechanism failures.

## 6. Servlet Example: Wrapper Preserving Standard Parser and Rejecting Ambiguity

A conservative customization **keeps `DefaultBearerTokenResolver` as a delegate** and adds checks upfront for **duplicate `Authorization`** and **forbidden query parameters**.

### 6.1. `StrictHeaderBearerTokenResolver` Class

```java
package com.example.orders.security;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

public final class StrictHeaderBearerTokenResolver
        implements BearerTokenResolver {

    private final DefaultBearerTokenResolver delegate;

    public StrictHeaderBearerTokenResolver() {
        this.delegate = new DefaultBearerTokenResolver();
        this.delegate.setAllowFormEncodedBodyParameter(false);
        this.delegate.setAllowUriQueryParameter(false);
    }

    @Override
    public String resolve(HttpServletRequest request) {
        rejectRepeatedAuthorizationHeaders(request);
        rejectBearerInQuery(request.getQueryString());

        // Spring Security remains responsible for parsing Bearer grammar.
        return delegate.resolve(request);
    }

    private static void rejectRepeatedAuthorizationHeaders(
            HttpServletRequest request) {

        Enumeration<String> values =
            request.getHeaders(HttpHeaders.AUTHORIZATION);

        int count = 0;
        while (values != null && values.hasMoreElements()) {
            values.nextElement();
            if (++count > 1) {
                throw invalidRequest(
                    "Multiple Authorization headers are not allowed"
                );
            }
        }
    }

    private static void rejectBearerInQuery(String rawQuery) {
        if (rawQuery == null || rawQuery.isEmpty()) {
            return;
        }

        for (String pair : rawQuery.split("&", -1)) {
            int equals = pair.indexOf('=');
            String encodedName =
                equals < 0 ? pair : pair.substring(0, equals);

            final String parameterName;
            try {
                parameterName = URLDecoder.decode(
                    encodedName,
                    StandardCharsets.UTF_8
                );
            } catch (IllegalArgumentException ex) {
                throw invalidRequest(
                    "Malformed query parameter encoding"
                );
            }

            if ("access_token".equals(parameterName)) {
                throw invalidRequest(
                    "Bearer token in URI query is not allowed"
                );
            }
        }
    }

    private static OAuth2AuthenticationException invalidRequest(
            String description) {
        return new OAuth2AuthenticationException(
            BearerTokenErrors.invalidRequest(description)
        );
    }
}
```

**Role of the wrapper:**

- If multiple `Authorization` headers exist, reject rather than letting the HTTP container/proxy pick one arbitrarily.
- If the URL contains `access_token`, reject under the API's **strict policy**; tokens in URLs are discouraged.
- Without extra input violations, delegate to **`DefaultBearerTokenResolver`** for Bearer parsing.
- If the Bearer token is malformed, the delegate throws standard errors; the wrapper **never swallows exceptions**.
- A **syntactically** valid token must still pass `JwtDecoder` or `OpaqueTokenIntrospector`.

### 6.2. Limitations of the Wrapper Class

This is an **illustrative policy**, not a complete URL parser or security gateway. Rejecting query parameter names via `URLDecoder` fits form-style query interpretation in this example; real environments must align URL decoding across proxy, Servlet container, and application, enforce length/encoding limits at the edge, and test percent-encoding variants.

Additionally:

- A gateway may have already **folded** multiple headers into one line before reaching the Servlet; the wrapper cannot see information already lost.
- Never parse the entire request body just to look for form `access_token` if doing so consumes the input stream before the controller; by default the delegate **rejects Bearer from forms**.
- If an endpoint genuinely permits form body tokens, design around RFC 6750, content-type/method, precedence, duplicate sources, and dedicated tests rather than flipping a global API flag.
- If a request has another query parameter colliding after proxy normalization, apply identical normalization policies at edge and app.
- If an API legitimately needs a business query parameter named `access_token` not used as Bearer, rename that parameter clearly instead of creating an ambiguous policy.

### 6.3. Why Not Verify JWT Signatures Inside the Resolver?

Resolvers handle credential extraction. JWT verification belongs to `JwtDecoder` and the authentication provider. Creating a `JwtDecoder` inside `resolve(...)` can:

- Verify the token multiple times.
- Break 401/403 exception handling.
- Pick the wrong decoder/issuer in multi-tenant setups.
- Trigger network JWKS discovery during input parsing.
- Push unverified data into caches/contexts.
- Entangle extraction with authorization, making testing hard.

**Separation of responsibilities is a security measure**, not just a clean-code habit.

## 7. Wiring a Custom Resolver into Spring Security Resource Server

### 7.1. Dependencies

Gradle Groovy DSL example for Servlet MVC:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Issuer and audience configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
```

`audiences` is supported in matching Spring Boot versions; with a custom decoder or another version, attach a dedicated audience validator.

### 7.2. Bearer-Only SecurityFilterChain

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BearerApiSecurityConfiguration {

    @Bean
    StrictHeaderBearerTokenResolver strictBearerResolver() {
        return new StrictHeaderBearerTokenResolver();
    }

    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(
            HttpSecurity http,
            StrictHeaderBearerTokenResolver resolver) throws Exception {

        return http
            .securityMatcher("/api", "/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS
                )
            )
            .requestCache(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(resolver)
                .jwt(Customizer.withDefaults())
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new BearerTokenAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new BearerTokenAccessDeniedHandler()
                )
            )
            .build();
    }
}
```

**Read the configuration in order of responsibility:**

1. `securityMatcher` restricts this chain to `/api` and `/api/**`, rather than all paths.
2. `oauth2ResourceServer` establishes the Bearer token pipeline.
3. `bearerTokenResolver(resolver)` changes **how/where the token is extracted**, not the decoder/manager.
4. `jwt(...)` still enforces signature, issuer, expiration, audience, and configured validators.
5. `hasAuthority("SCOPE_orders.read")` checks scopes after authentication.
6. `formLogin` and `httpBasic` are disabled **inside the Bearer API chain** to avoid unintended mechanisms.
7. `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` preserve Bearer 401/403 errors.

**CSRF:** the illustrative code does not disable CSRF. If the API uses only Bearer headers and accepts no cookies/session credentials, design a dedicated CSRF policy per threat model; never blindly disable CSRF across all endpoints when cookie-based authentication exists in the system.

### 7.3. When Using Opaque Tokens

Replace the JWT part:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(resolver)
    .opaqueToken(Customizer.withDefaults())
)
```

Also configure Spring Boot's `opaquetoken.introspection-uri/client-id/client-secret`. **The same resolver can serve JWT or opaque**, because it only extracts the Bearer token. The provider/decoder mechanism decides how authentication works.

Do not invent "dots mean JWT, no dots mean opaque, let it pass". Format may assist contracted routing, but never replaces cryptographic validation or introspection.

## 8. Multiple Authentication Mechanisms: Prefer Splitting by SecurityFilterChain

When an application serves both a Bearer REST API and a legacy HTTP Basic API, the clearest approach is **explicit route separation**:

```text
/api/**           -> Bearer access token
/legacy/**        -> HTTP Basic, only while still needed
/web/**           -> Session/OIDC Login if present
remaining routes  -> deny or matching chain
```

### 8.1. Example Basic-Only Chain for the Legacy Path

```java
@Bean
@Order(2)
SecurityFilterChain legacyBasicApi(HttpSecurity http)
        throws Exception {
    return http
        .securityMatcher("/legacy/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .sessionManagement(session ->
            session.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS
            )
        )
        .formLogin(AbstractHttpConfigurer::disable)
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This is **a separate chain** from the bearer chain above. The actual authentication provider/`UserDetailsService` for HTTP Basic must be configured securely; this is not an endorsement to use HTTP Basic for a new API when OAuth Bearer fits.

### 8.2. Fallback for Unclassified URLs

```java
@Bean
@Order(99)
SecurityFilterChain fallbackDenyAll(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll()
        )
        .build();
}
```

A chain with a narrow `securityMatcher` **does not protect** URLs outside that matcher. The fallback prevents new endpoints from accidentally sitting outside any protective chain.

If the app has actuator, OAuth2 login callbacks, or web UIs, configure matching chains/matchers before the fallback; never copy `denyAll` while forgetting valid endpoints.

### 8.3. `@Order` Matters

Spring Security selects **the first chain matching the request**. If a web chain has an overly broad matcher ahead of the API chain, `/api/orders` requests can hit `formLogin` and get a 302 HTML login instead of a 401 Bearer challenge.

Rules:

- Bearer API chain has an explicit matcher and higher priority order.
- Basic/API-key/web chains have their own URL scopes.
- Fallback chain handles everything left over.
- Never rely on `Accept: application/json` to pick an authentication mechanism.
- Test URLs with and without trailing slashes, context paths, and reverse proxy path rewrites.

## 9. If Multiple Credentials Must Be Supported on the Same Endpoint

Sometimes an endpoint must serve both old and new clients during migration. This is a sensitive situation because **credential precedence** becomes part of the security contract.

### 9.1. Avoid "Whichever Credential Works Wins"

Example:

```http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer EXPIRED_TOKEN
X-API-Key: VALID_LEGACY_KEY
```

A design to avoid:

```text
Try Bearer
  -> invalid_token error
  -> ignore
Try API key
  -> valid
  -> allow
```

Consequence: a client sending a bad Bearer credential is still authenticated via another mechanism, complicating audits and creating unintended **downgrades/fallbacks**.

### 9.2. A Clearer Policy

You can stipulate:

| Credentials on one request | Behavior |
|---|---|
| Bearer only | Authenticate via Bearer |
| API key only | Authenticate via API key when route/contract allows |
| No credential | 401 |
| Malformed Bearer | Reject immediately; no fallback |
| Bad-signature/expired Bearer | Reject; no fallback |
| Both Bearer and API key present | **Reject due to credential conflict** |
| Two Bearer headers | Reject |
| Two API key headers | Reject |
| Both Cookie and Bearer present | Explicit policy; prefer splitting routes |
| Valid Bearer missing scope, stronger API key | No fallback after 403 |

If multiple mechanisms must be allowed on the same route, place **a credential-conflict check layer ahead of authentication filters** or build one explicitly designed authentication gateway/filter. Never drop in two independent filters and hope execution order handles everything.

### 9.3. Conflicts Must Be Handled Before Authentication

Good principle:

```text
Inspect credential sources (bounded, no secret logging)
     |
     +-- 0 credentials -> unauthenticated
     +-- 1 supported scheme -> authenticate with its provider
     +-- >1 conflicting sources -> reject
     +-- malformed scheme -> reject
```

If using a custom pre-auth filter to check conflicts, it must only **classify sources**, never validate tokens or grant roles itself. Return consistent error responses (status/body/`WWW-Authenticate`) and insert it in the right order; otherwise, the simpler choice remains **splitting routes**.

## 10. Never Let Bearer Errors Fall Into Basic, API Key, or Session

### 10.1. Distinguish Absent Bearer from Invalid Bearer

Example:

```http
Authorization: Basic BASE64_USER_PASSWORD
```

`DefaultBearerTokenResolver` can return `null` because this is not a Bearer credential. If the chain supports HTTP Basic, the Basic filter decides how to process it per contract.

However:

```http
Authorization: Bearer INVALID!! TOKEN
```

is a **Bearer input error**. A custom resolver must never return `null` just to let the request pass through to a Basic filter, session cookie, or API key filter.

### 10.2. Never Fall Back After JWT Validation Failure

If the system accepts both JWT and opaque tokens, a dangerous pattern is:

```text
Try verifying JWT
   |
   +-- wrong signature/issuer/audience
   |
   v
Try introspecting raw token at another endpoint
   |
   +-- active=true -> allow through
```

This can create a **confused deputy** or **downgrade path** if the two mechanisms have different trust/policies. If both JWT and opaque must be accepted, you need:

- Explicit token class contracts from the AS.
- Approved manager/decoder routing that never relies on token-supplied issuer/JWKS URLs.
- No "try all Authorization Servers" for a bearer token.
- Never sending tokens to introspection endpoints outside the trust boundary.
- Verification of audience, issuer/resource, scopes, expiration, and token type in **each branch**.
- Treating authentication failure as failure, not a trigger to open a weaker branch.

**The token resolver only picks the input source; deciding JWT vs. opaque belongs to the authentication manager/provider architecture.**

## 11. Custom Headers from Reverse Proxies: Risks and Mitigations

In some architectures, a gateway or service mesh forwards Bearer tokens via a custom header:

```http
X-Internal-Access-Token: ACCESS_TOKEN
```

If the backend accepts that header from any client, attackers can forge the header to impersonate the gateway.

### 11.1. The Trust Boundary Must Sit Outside the Header

A header cannot prove on its own:

- The request came from an authorized gateway.
- The gateway already authenticated the caller.
- The header was not injected by the client and blindly forwarded by the proxy.
- The header carries an access token with the right audience.
- The header was not tampered with by intermediate proxies.

To use a custom header, combine a **trusted network/identity boundary** such as mTLS between gateway and service, inbound firewall/ingress policies, header stripping/overwriting at the edge, and backend config accepting traffic only from authenticated gateways.

**Never use** `X-Forwarded-For`, `X-Real-IP`, or a caller-sent `X-Gateway-Trusted: true` as sole proof that a request came from the gateway.

### 11.2. Using `setBearerTokenHeaderName`

In a system that already enforces a trust boundary ahead of the backend, you can configure the resolver to read only the proxy-managed header:

```java
@Bean
BearerTokenResolver gatewayBearerTokenResolver() {
    DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    // Only for a clearly protected proxy protocol.
    resolver.setBearerTokenHeaderName(
        "X-Internal-Access-Token"
    );
    resolver.setAllowFormEncodedBodyParameter(false);
    resolver.setAllowUriQueryParameter(false);
    return resolver;
}
```

**Prerequisites:** the gateway must **strip this header from external requests and overwrite it with a system-managed value**, the gateway–backend link must be authenticated, and the backend must reject direct untrusted traffic. `setBearerTokenHeaderName` only switches the token source header; **it does not verify any of those prerequisites**.

Because the standard resolver is used with a custom header, ensure the gateway sends the **Bearer format expected by the resolver** (do not assume a raw token without the `Bearer ` prefix will be accepted). Integration tests between edge and backend must verify actual header values.

### 11.3. Prefer Preserving `Authorization: Bearer` Across Hops When Possible

If the gateway acts as a normal reverse proxy and the backend still verifies access tokens, the simpler solution is usually **forwarding `Authorization: Bearer` with proper secret-redaction policies** rather than inventing a new header.

Custom headers should be used when an approved internal proxy protocol exists, not as a workaround for a client sending malformed Bearer headers.

### 11.4. Never Enable Two Headers Simultaneously Without Conflict Rules

If a resolver reads both:

```http
Authorization: Bearer TOKEN_A
X-Internal-Access-Token: Bearer TOKEN_B
```

and picks arbitrarily, clients and gateways may disagree. If two sources genuinely exist, the contract must define:

- Are requests permitted to send both?
- If both are present, **reject** or follow a specific migration policy?
- Which header is accepted solely from an authenticated gateway?
- Which headers must be stripped at ingress?
- How are errors returned, and do logs/traces avoid leaking tokens?

Never use "take the first non-empty value" logic without an anti-conflict policy.

## 12. Multi-Tenant and Multi-Issuer: Resolvers Must Not Arbitrarily Expand Trust

A Bearer token may be a JWT containing:

```json
{
  "iss": "https://id.tenant-a.example",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Yet `iss` is unverified. If a custom resolver reads `iss` and fetches metadata/JWKS from an arbitrary issuer URL, the Resource Server risks **SSRF and issuer confusion**.

**Proper design:**

1. The resolver extracts the Bearer token per the HTTP contract.
2. The authentication manager resolver (if multi-issuer) selects only from a **trusted issuer allowlist**.
3. The selected issuer's decoder verifies signature, exact issuer, audience, timestamp, allowed algorithm, and token profile.
4. Scope/tenant/business authorization runs after authentication.
5. Unknown issuers are rejected **before** running discovery or making network calls to untrusted hosts.

Never treat `iss`, `kid`, `jku`, or URLs from an unverified token as network configuration sources.

### 12.1. Why Is This the Authentication Manager's Job, Not the Token Resolver's?

The resolver knows **where the Bearer token lives**; the manager decides **whether the token is trustworthy**. Merging both into the resolver makes it hard to guarantee every mechanism enforces the same validators.

In Spring Security Servlet you can use `JwtIssuerAuthenticationManagerResolver` with trusted issuers, but never replace it with `JwtDecoders.fromIssuerLocation(unverifiedIssuer)` for arbitrary requests.

### 12.2. Even One Issuer Can Have Multiple Audiences

A JWT validly signed by `https://login.example.com` with `aud=billing-api` must not be accepted by the Orders API. A custom resolver must never "fix" audience by altering payload fields or dropping validators for compatibility.

## 13. WebFlux: `ServerBearerTokenAuthenticationConverter` Is the Resolver Equivalent

In **Spring WebFlux**, the interface typically used to turn a request into an authentication request is:

```java
public interface ServerAuthenticationConverter {
    Mono<Authentication> convert(ServerWebExchange exchange);
}
```

Spring Security provides `ServerBearerTokenAuthenticationConverter` to read Bearer credentials and construct `BearerTokenAuthenticationToken` in the reactive chain.

### 13.1. Do Not Use Servlet Resolvers in WebFlux

| Servlet | WebFlux |
|---|---|
| `HttpServletRequest` | `ServerWebExchange` |
| `BearerTokenResolver` | `ServerAuthenticationConverter` |
| `DefaultBearerTokenResolver` | `ServerBearerTokenAuthenticationConverter` |
| `BearerTokenAuthenticationFilter` | `AuthenticationWebFilter` for Bearer Resource Server |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `JwtDecoder` | `ReactiveJwtDecoder` |
| `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |

**Do not attach a Servlet `BearerTokenResolver` to `ServerHttpSecurity` expecting WebFlux to call it.** Both request types and authentication pipelines differ.

### 13.2. Default WebFlux Converter

```java
import org.springframework.security.oauth2.server.resource.web.server
    .ServerBearerTokenAuthenticationConverter;

ServerBearerTokenAuthenticationConverter converter =
    new ServerBearerTokenAuthenticationConverter();

converter.setAllowUriQueryParameter(false);
```

Exact configuration APIs vary by Spring Security version, yet the principle stays the same: **prefer the Authorization header and do not enable query tokens casually**.

### 13.3. Wrapper Converter Enforcing a Single Source

A custom converter can check for duplicate headers/queries and **delegate parsing to the standard converter**:

```java
package com.example.orders.security;

import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
import org.springframework.security.oauth2.server.resource.web.server.ServerBearerTokenAuthenticationConverter;
import org.springframework.security.web.server.ServerWebExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;

import reactor.core.publisher.Mono;

public final class StrictReactiveBearerConverter
        implements ServerAuthenticationConverter {

    private final ServerBearerTokenAuthenticationConverter delegate =
        new ServerBearerTokenAuthenticationConverter();

    public StrictReactiveBearerConverter() {
        delegate.setAllowUriQueryParameter(false);
    }

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        List<String> authorizationValues =
            exchange.getRequest().getHeaders()
                .getOrEmpty(HttpHeaders.AUTHORIZATION);

        if (authorizationValues.size() > 1) {
            return Mono.error(
                new OAuth2AuthenticationException(
                    BearerTokenErrors.invalidRequest(
                        "Multiple Authorization headers"
                    )
                )
            );
        }

        if (exchange.getRequest().getQueryParams()
                .containsKey("access_token")) {
            return Mono.error(
                new OAuth2AuthenticationException(
                    BearerTokenErrors.invalidRequest(
                        "Bearer token in URI query is not allowed"
                    )
                )
            );
        }

        // Do not parse Bearer grammar manually or mint Authentication.
        return delegate.convert(exchange);
    }
}
```

This class enforces **the same baseline policy** as the Servlet wrapper:

- Only one `Authorization` header.
- Forbids tokens in query parameters.
- Standard converter handles Bearer syntax.
- Missing credential → empty publisher per converter contract.
- Invalid credential → error, no automatic fallback to another scheme.
- Extracted credential → only an authentication request, still requiring verification by the reactive manager.

### 13.4. Wiring the Converter into `ServerHttpSecurity`

Example on versions supporting `bearerTokenConverter(...)` in the WebFlux Resource Server DSL:

```java
@Bean
SecurityWebFilterChain apiWebFlux(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/public/**").permitAll()
            .anyExchange().authenticated()
        )
        .formLogin(form -> form.disable())
        .httpBasic(basic -> basic.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .bearerTokenConverter(
                new StrictReactiveBearerConverter()
            )
            .jwt(Customizer.withDefaults())
        )
        .build();
}
```

This is a **WebFlux variant**; do not place it beside Servlet `SecurityFilterChain` beans in the same app without ensuring the proper web application type.

If your minor Spring Security version has different API names or requires configuring `AuthenticationWebFilter` directly, consult the Javadoc and keep the same goal: **strict conversion + standard reactive authentication manager**, without duplicating Bearer filters in the same chain.

### 13.5. Never `block()` or `subscribe()` Inside a Converter

`ServerAuthenticationConverter.convert(...)` returns `Mono<Authentication>`. Never call:

```java
Authentication authentication =
    someReactiveDecoder.decode(token).block();
```

inside a converter to "pre-check the token". WebFlux must keep authentication inside the reactive pipeline, avoiding blocking the event loop, losing Reactor Context, or repeating verification.

## 14. Multiple Mechanisms in WebFlux Also Need Separate SecurityWebFilterChains

Example:

```java
@Bean
@Order(1)
SecurityWebFilterChain bearerRoutes(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        )
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated()
        )
        .httpBasic(basic -> basic.disable())
        .formLogin(form -> form.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .bearerTokenConverter(
                new StrictReactiveBearerConverter()
            )
            .jwt(Customizer.withDefaults())
        )
        .build();
}
```

Legacy route if Basic is needed:

```java
@Bean
@Order(2)
SecurityWebFilterChain basicRoutes(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/legacy/**")
        )
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

These snippets are fragments needing Spring Security WebFlux imports and `@Order`. Add a fallback chain protecting other routes per your application contract.

**Do not confuse the two matchers:**

- `securityMatcher(...)` selects the **`SecurityWebFilterChain`**.
- `authorizeExchange().pathMatchers(...)` selects **authorization rules** inside the chosen chain.

If a request mistakenly hits a web-login chain, fixing only the Bearer converter will not stop HTML login redirects.

## 15. HTTP Basic Differs from Introspection Client Authentication

In a Resource Server using opaque tokens, HTTP Basic and Bearer headers may exist on **two completely different connections**:

```text
API caller -> Orders API:
    Authorization: Bearer ACCESS_TOKEN

Orders API -> Authorization Server introspection:
    Authorization: Basic CLIENT_ID:CLIENT_SECRET
    body: token=ACCESS_TOKEN
```

Do not confuse the **outbound** HTTP Basic that the Resource Server uses to call introspection with an **inbound** HTTP Basic mechanism for callers.

Therefore, to use opaque tokens, the API **does not need `httpBasic()` enabled** in the Bearer security chain. Enabling inbound `httpBasic` just because introspection uses a client secret mixes up responsibilities.

### 15.1. Why Can Inbound Basic Cause Unexpected UI Behavior?

An HTTP Basic challenge on a Bearer API can cause browsers to display a username/password prompt, whereas OAuth clients expect:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Similarly, form login can return `302 Location: /login`. On Bearer-only routes, avoid enabling entry points outside the API contract.

## 16. CORS, CSRF, and Cookies with Multiple Mechanisms

A cross-origin frontend may send a preflight:

```http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflights do not necessarily carry a Bearer access token. Configure CORS so preflights pass before authentication where appropriate; never treat every `OPTIONS` request as a malformed token.

### 16.1. CORS Does Not Replace Authentication

Allowing a specific origin in CORS **does not prove** a Bearer token is valid. Browsers set the `Origin` header in certain contexts, yet it can never serve as authentication proof for API clients.

### 16.2. CSRF Depends on Credential Type

- An API **accepting only Bearer from the `Authorization` header** and not relying on auto-sent cookies has a different CSRF model from a session-based web app.
- If an API also permits **cookie session authentication**, browsers may auto-attach cookies → design proper CSRF protection.
- If an endpoint accepts both cookies and Bearer, set clear rules when both appear, and avoid "Bearer invalid so fall back to cookie" outside the contract.
- Disabling CSRF application-wide is not the fix for credential-resolver bugs.

### 16.3. Do Not Move Tokens into Cookies to Avoid the Authorization Header

If an application wants a BFF/session architecture, design it as **a separate authentication boundary**, rather than merely moving a Bearer token into a Cookie and assuming it is safer. SameSite, HttpOnly, Secure, CSRF, session fixation, and refresh token handling still apply.

## 17. Controlling Header Ambiguity at Proxy/Gateway

Not every HTTP intermediary preserves headers identically. For example:

```http
Authorization: Bearer TOKEN_A
authorization: Bearer TOKEN_B
```

HTTP header names are **case-insensitive**. Proxies may fold, pick one line, reject, or forward depending on implementation. If edge and backend interpret them differently, **request smuggling / credential confusion** risks arise.

### 17.1. Policies to Enforce from Ingress to Application

- Reject duplicate `Authorization` headers right at ingress if infrastructure supports it.
- Never fold multiple Bearer values into a single accepted value.
- Never let one hop do "last header wins" while another does "first header wins".
- Bound `Authorization` header/token sizes.
- Explicitly define whether custom proxy headers are accepted.
- Strip/overwrite gateway-owned headers.
- Ensure logs/traces redact both Bearer tokens and API keys.
- Test through the actual reverse proxy/ingress in use, not only mock servlet unit tests.

A `StrictHeaderBearerTokenResolver` in the backend is **defense in depth**; it cannot recover duplicate values already merged by a proxy prior to forwarding.

### 17.2. HTTP Request Smuggling and Caching

If proxy, gateway, and backend parse headers differently, users can observe inconsistent responses, especially with caching/CDNs. Never cache private API responses without proper `Cache-Control`/`Vary`/identity isolation, and never use tokens as URL cache keys.

### 17.3. Never Send Raw Credentials to Observability

Fields to redact:

```text
Authorization
Proxy-Authorization
X-API-Key
X-Internal-Access-Token
Cookie
Set-Cookie (when holding session tokens)
access_token query/body
```

Log only status, error class, latency, route, request correlation ID, and the **validly identified mechanism**. Never put raw tokens or high-cardinality token hashes into metric labels.

## 18. 401, 400, 403, and Auth Mechanism Errors

Per RFC 6750, a Bearer Resource Server can respond with a challenge:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

When a token is invalid:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

When a Bearer request is structurally invalid:

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
```

When a valid token lacks scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

**Exact statuses depend on error context and Spring Security handlers**; not every malformed header produces the exact same status across different error spaces or extensions. Yet the API must avoid HTML login redirects, false 200 successes, and silent fallbacks.

### 18.1. Cause → Handler Table

| Issue | Responsible layer | Behavior |
|---|---|---|
| No credential | Resolver + authorization | 401 when endpoint requires auth |
| Repeated Authorization header | Strict resolver/ingress policy | Reject input |
| Malformed Bearer grammar | Standard resolver | Authentication error, no fallback |
| Expired/bad-signature JWT | JwtDecoder/provider | 401 `invalid_token` |
| Opaque introspection `active=false` | Introspector/provider | 401 `invalid_token` |
| Valid token missing `orders.write` | Authorization | 403 `insufficient_scope` |
| Token with scope, wrong owner | Domain policy | 403/404 per contract |
| Introspection/JWKS timeout | Dependency/decoder | Fail closed; error mapping per config |
| Invalid API key on API-key route | API-key authentication provider | 401 per API key contract |
| Expired login cookie on web route | Web session mechanism | May redirect to login per UX |

### 18.2. Never Turn an Infrastructure Outage into an "Empty Bearer Token"

If `JwtDecoder` or `OpaqueTokenIntrospector` hits an infrastructure error, the resolver **already found the token**. Never write a catch-all in the resolver or manager returning `null` to let the request pass through Basic/API key.

Categorize network, TLS, timeout, and outbound client authentication errors for monitoring, yet never grant access when a Bearer token cannot be verified.

## 19. Test the Resolver Independently Before Testing Authentication

A good test suite separates three layers:

1. **Resolver tests:** HTTP request input → token, `null`, or exception.
2. **Authentication tests:** candidate token → valid/invalid after JWT/opaque verification.
3. **Authorization tests:** valid Authentication → scope, tenant, and object permissions.

Testing only layers 2 and 3 will not necessarily catch duplicate inputs or improper fallbacks.

### 19.1. Unit Testing the Servlet Resolver

Example with Spring `MockHttpServletRequest`:

```java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;

import static org.junit.jupiter.api.Assertions.*;

class StrictHeaderBearerTokenResolverTest {

    private final StrictHeaderBearerTokenResolver resolver =
        new StrictHeaderBearerTokenResolver();

    @Test
    void extractsSingleBearerHeader() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer test-token"
        );

        assertEquals("test-token", resolver.resolve(request));
    }

    @Test
    void returnsNullWhenBearerIsAbsent() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        assertNull(resolver.resolve(request));
    }

    @Test
    void doesNotTreatBasicAsBearer() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Basic dXNlcjpwYXNzd29yZA=="
        );

        assertNull(resolver.resolve(request));
    }

    @Test
    void rejectsMultipleAuthorizationHeaderValues() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer first-token"
        );
        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer second-token"
        );

        assertThrows(
            OAuth2AuthenticationException.class,
            () -> resolver.resolve(request)
        );
    }

    @Test
    void rejectsTokenInQuery() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        request.setQueryString("access_token=secret");
        assertThrows(
            OAuth2AuthenticationException.class,
            () -> resolver.resolve(request)
        );
    }

    @Test
    void rejectsMalformedBearerHeader() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer token with whitespace"
        );

        assertThrows(
            OAuth2AuthenticationException.class,
            () -> resolver.resolve(request)
        );
    }
}
```

These tests **do not verify JWT signatures or introspection**. They only prove the strict resolver extracts/evaluates inputs per contract.

### 19.2. Testing Easy-to-Miss Variants

| Input | What to check |
|---|---|
| `Authorization: bearer token` | Scheme case-insensitivity per standard resolver |
| `Authorization: BEARER token` | Scheme and parser rules |
| `Authorization: Bearer` | Missing token must error |
| `Authorization: Bearer   token` | Do not normalize outside grammar |
| `Authorization: Bearer token, Bearer other` | Do not pick one token arbitrarily |
| Two headers with different casing | Header names are case-insensitive |
| Very long header | Bounded at edge/container before exhausting resources |
| `?access_token=abc` | Query blocked per strict policy |
| `?access%5Ftoken=abc` | Encoded name must not bypass policy |
| Token in form body | Not accepted by default |
| Cookie + Bearer | Multi-credential policy enforced |
| API key + Bearer | Must not switch to API key |
| JWT-like string without valid signature | Resolver extracts only; decoder rejects |
| Opaque string with dots | Do not use token shape to skip validation |

### 19.3. Test That Parser Errors Are Not Swallowed

A flawed custom resolver might write:

```java
try {
    return delegate.resolve(request);
} catch (OAuth2AuthenticationException ex) {
    return null; // DO NOT USE
}
```

Tests must prove a malformed Bearer produces an **error**, rather than turning into an anonymous request for another mechanism to continue. This is an essential anti-downgrade test.

## 20. MockMvc Integration Test: API with Bad Bearer Does Not Produce Login HTML

Unit tests alone do not prove the security chain and entry point are right. Use `MockMvc` through Spring Security:

```java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BearerApiContractTest {

    @Autowired MockMvc mvc;

    @Test
    void missingBearerIsNotHtmlLogin() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Bearer")
            ))
            .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
    }
}
```

This is an entry-point/chain check template; real endpoint/bean dependencies are required to run. For malformed Bearer, also test the corresponding RFC/framework status and **zero redirects**. For bad-signature JWTs, use fake JWKS/test-signed tokens or a controlled mock decoder.

### 20.1. Testing Non-Fallback to API Key

If an endpoint accepts both schemes under a migration contract, integration tests should send:

```http
Authorization: Bearer INVALID_TOKEN
X-API-Key: VALID_TEST_API_KEY
```

and assert **the request is rejected per the conflict rule**, never reaching the controller. Beyond status, assert the backend **did not call the API-key authentication provider as a fallback** after Bearer failed.

### 20.2. Testing That 403 Does Not Fall Back to 200

A valid JWT with `SCOPE_orders.read` on a POST requiring `SCOPE_orders.write` must receive 403. Never try another credential to "elevate privileges" for a request that already had an authenticated Bearer token lacking scope.

## 21. WebTestClient: Testing Reactive Converters and Routes

In WebFlux, use `MockServerWebExchange` and `MockServerHttpRequest` to test the converter:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;

import reactor.test.StepVerifier;

class StrictReactiveBearerConverterTest {

    private final StrictReactiveBearerConverter converter =
        new StrictReactiveBearerConverter();

    @Test
    void extractsBearerFromHeader() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/orders")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer test-token"
                )
        );

        StepVerifier.create(converter.convert(exchange))
            .assertNext(authenticationRequest ->
                org.junit.jupiter.api.Assertions.assertEquals(
                    "test-token",
                    authenticationRequest.getCredentials()
                )
            )
            .verifyComplete();
    }

    @Test
    void rejectsQueryToken() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get(
                "/api/orders?access_token=unwanted"
            )
        );

        StepVerifier.create(converter.convert(exchange))
            .expectError()
            .verify();
    }
}
```

In typical Spring Security releases, `BearerTokenAuthenticationToken` stores the raw token in credentials. If contracts/internal APIs change, tests should assert **the authentication request type and token value** matching your actual API version.

### 21.1. `WebTestClient` Integration Differs from Converter Unit Tests

`mockJwt()` or `mockOpaqueToken()` in Spring Security Test injects **test** Authentication to verify authorization; they **do not exercise the converter reading Bearer headers** and do not verify signatures/introspection.

To test end-to-end:

1. Send real HTTP Bearer headers via `WebTestClient`.
2. Let `AuthenticationWebFilter` and the custom converter execute.
3. Use a fake issuer/JWKS or fake introspection endpoint.
4. Test valid, invalid, missing, and duplicate tokens.
5. Assert 401/403 and `WWW-Authenticate`.
6. With two chains, verify API requests do not enter the login chain.
7. With multiple mechanisms, send conflicting credentials and assert no fallback.
8. Ensure malformed requests never invoke controllers/business services.

## 22. Comprehensive Multi-Mechanism Test Suite

| Test | Credential source | Expectation |
|---|---|---|
| Bearer only, valid token | Authorization header | Verify token, enforce scopes |
| Bearer only, expired token | Authorization header | 401, no fallback |
| Malformed Bearer header | Authorization header | Input error, no fallback |
| Missing Bearer on protected route | No credential | 401 Bearer |
| Basic on Bearer-only route | Authorization: Basic | Does not become Bearer; route rejects |
| Valid Basic on Basic-only route | Authorization: Basic | Authenticates via Basic provider |
| Bearer on Basic-only route | Authorization: Bearer | Must not auto-grant access |
| Valid API key on API-key route | X-API-Key | Handled by route's provider |
| Bearer + API key on shared route | Two sources | Reject conflict per policy |
| Bearer + cookie on shared route | Two sources | Enforce explicit contract; never pick silently |
| Two Authorization headers | Duplicated headers | Reject |
| Header + query token | Multiple sources | Reject per strict policy |
| Query-only token | URL | Not accepted as Bearer |
| Custom gateway header from Internet | Untrusted header | Reject/strip at edge; never trust |
| Gateway mTLS + managed header | Trusted channel | Authenticate via Bearer decoder after extraction |
| Token with `aud=billing-api` | Syntactically valid Bearer | 401 `invalid_token` from Orders API |
| JWT wrong `iss` | Syntactically valid Bearer | No dynamic discovery of unknown issuer |
| Valid token, missing scope | Bearer | 403 |
| Token with scope, wrong tenant | Bearer | 403/404 per domain |
| Opaque `active=false` | Bearer | 401 |
| Introspection timeout | Bearer | Fail closed; do not switch to API key |
| API gateway rewrites Authorization | Proxy path | Backend receives/rejects per contract |
| Browser sends `Accept: text/html` | Bearer-only API | 401 Bearer, no login redirect |

### 22.1. Testing Behind the Actual Reverse Proxy

If you test only directly with `MockMvc`, many ingress behaviors remain unseen:

- Folding duplicate headers.
- Stripping or overwriting `Authorization`.
- Forwarding custom headers.
- Rewriting request paths and hitting the wrong security chain.
- Proxy returning 302/HTML login itself.
- CORS preflights being rejected.
- Tokens in URLs written to access logs.

Run integration/e2e tests through a **production-equivalent proxy configuration**, especially when custom resolvers read internal headers.

## 23. Monitoring and Diagnostics

If a 401 spike occurs after changing a resolver, distinguish:

- Did clients actually stop sending `Authorization`?
- Did a proxy strip the header?
- Did the resolver switch to reading a custom header absent in this environment?
- Are duplicate headers being rejected by the strict policy?
- Did requests accidentally append an `access_token` query parameter?
- Are JWT signatures/issuers/audiences invalid?
- Is the introspection endpoint failing?
- Did scope mapping/authorization change?
- Did requests fall into another Basic/web chain?

### 23.1. Suggested Metrics

| Metric | Purpose |
|---|---|
| `credential.source=authorization_header` | Valid Bearer source selected, without logging token |
| `credential.error=duplicate_header` | Detects ambiguity/proxy misconfiguration |
| `credential.error=query_token_rejected` | Detects forbidden token source |
| `credential.error=malformed_bearer` | Tracks non-compliant clients |
| `authentication.mechanism=bearer/basic/api_key` | Usage ratio of each mechanism on allowed routes |
| `authentication.outcome=success/invalid/error` | Separates outcome categories |
| `authorization.outcome=granted/denied` | Measures 403s and object policies |
| `jwt.decoder.failure` | Signature, issuer, audience, exp |
| `introspection.failure` | AS errors / client authentication |
| `gateway.auth_header_rewrite` | Observes credential source changes |
| `request.route_group` | Breakdown by endpoint group |

Metric names are **suggestions**, not all built-in Spring Security metrics. Use low-cardinality tags and never put raw tokens, `sub`, arbitrary URLs, or API keys in labels.

### 23.2. Safe Logging

Example:

```text
WARN credential_rejected
  requestId=...
  route=/api/orders/*
  source=authorization_header
  reason=multiple_headers
  mechanism=bearer
```

Never log:

```text
Authorization: Bearer <raw-token>
X-API-Key: <raw-api-key>
X-Internal-Access-Token: <raw-token>
Cookie: SESSION=<raw-session>
```

A Bearer token is a replayable credential. Even while debugging, never paste it into issue trackers, traces, or test reports.

## 24. Common Anti-Patterns

### 24.1. Using `substring(7)` Instead of the Standard Resolver

Fails to handle full Bearer grammar and easily misreads Basic/empty/malformed tokens.

### 24.2. Catching Exceptions and Returning `null`

Turns Bearer errors into "missing credential", opening fallback paths to other mechanisms.

### 24.3. Manually Parsing JWTs in a Resolver to Mint Authorities

Unverified payloads must never be used as proof of permissions.

### 24.4. Accepting Tokens from Header, Query, and Form Without Rules

Leads to credential ambiguity, URL leaks, and proxy/backend discrepancies.

### 24.5. Picking Tokens by "Whichever Source Appears First"

When two sources conflict, arbitrary selection produces inconsistent behavior. Prefer rejecting conflicts.

### 24.6. Letting API Keys Rescue Expired Bearer Tokens

This is a silent downgrade; support migrations only with explicit policies and conflict tests.

### 24.7. Trusting Proxy Headers from Arbitrary IPs/Clients

Leads to spoofing. Proxy-owned headers must be stripped/overwritten and travel over a trusted channel.

### 24.8. Building Issuer URLs from `Host`/`X-Forwarded-Host`

Creates SSRF and trust confusion risks; use a trusted issuer registry.

### 24.9. Enabling Inbound Basic Just Because Opaque Introspection Uses Client Secret

Introspection Basic is outbound Resource Server → AS, not inbound API callers.

### 24.10. Fixing Only `AuthenticationEntryPoint` Without Fixing the Chain Matcher

If API requests land in a form/OIDC login chain by mistake, they can still get HTML redirects.

### 24.11. Turning a WebFlux Converter into a Blocking `JwtDecoder`

Blocks the event loop, loses Reactor context, and duplicates verification. Keep converters focused purely on credential extraction.

### 24.12. Treating `mockJwt()` as Resolver Testing

Mock auth usually skips header resolution, so test converters/resolvers independently.

### 24.13. Treating `Authorization: Bearer` as an Acceptable Empty Token

Missing token is an input error; never create an anonymous principal with privileges.

### 24.14. Assuming HTTP 200 Means Authentication Worked

The controller might be public, or an HTML redirect might have been followed. Verify Authentication and scope/route contracts rather than guessing from status codes alone.

## 25. Implementation Workflow for a Multi-Mechanism System

**Step 1 — Map routes and credentials.**

```text
/api/**       Bearer only
/legacy/**    Basic only, concrete deprecation timeline
/web/**       Session/OIDC Login
/internal/**  mTLS/workload identity per network contract
```

If a route requires multiple mechanisms, document migration timelines, conflict handling, and fallback policies.

**Step 2 — Pick a single default Bearer source.**

Prefer `Authorization: Bearer`. Evaluate carefully before enabling form/query/custom headers. Never enable extra token sources just because they are easy to code.

**Step 3 — Delegate to standard resolvers/converters.**

Use `DefaultBearerTokenResolver` in Servlet and `ServerBearerTokenAuthenticationConverter` in WebFlux. Add strict checks for duplicates/queries or custom rules without rewriting grammar carelessly.

**Step 4 — Preserve error semantics.**

`null` means absent Bearer; malformed credential means error; validation failure returns 401; missing scope returns 403. Never convert errors into `null`.

**Step 5 — Configure `SecurityFilterChain` by route.**

Give the Bearer API chain priority, disable unintended mechanisms within that chain, and provide a fallback for other routes.

**Step 6 — Verify tokens with the right provider.**

JWTs must check signature, issuer, audience, exp/nbf/algorithm/profile. Opaque tokens must check introspection `active` and AS policy. Never assert authenticated principals inside a resolver.

**Step 7 — Enforce business authorization.**

Scopes alone do not authorize reading every order: verify tenant, subject/client, owner, and resource state.

**Step 8 — Harden the gateway.**

Reject duplicated/ambiguous headers, strip custom headers, enforce mTLS/egress protection where needed, limit header sizes, and redact logs.

**Step 9 — Test in three layers.**

Unit test resolver/converter; integration test authentication; end-to-end test through the gateway and domain authorization. Thoroughly test source conflicts and fail-closed behavior.

**Step 10 — Measure and retire legacy mechanisms.**

Track request counts per mechanism, deprecation schedules, and migration errors. Never leave API-key/Basic fallbacks enabled indefinitely once unapproved.

## 26. Decisions to Record in the Contract

| Decision | Example value |
|---|---|
| Bearer source | Single `Authorization` header |
| Query/body Bearer | Rejected |
| Duplicate Authorization | Reject |
| Malformed Bearer | Reject, no fallback |
| JWT/opaque validation | Matching provider and issuer/resource contract |
| Multiple credential classes on same route | Disallowed, except under migration contract |
| If Bearer + API key both present | Reject conflict |
| If Bearer invalid while API key valid | No fallback |
| Proxy-managed token header | Only over authenticated gateway path |
| Error response | 401/403 Bearer, no login HTML |
| Logging | Redact raw tokens/keys/cookies |
| Rate limiting | Gateway + per-route + auth dependency limits |
| Tenant binding | Per verified issuer/tenant policy |
| Migration ownership | API + Security + Identity teams |
| Mandatory tests | Duplicates, wrong scheme, bad signature, ambiguity, proxy rewrites |

This is an **example contract**; authentication mechanisms and error handling must fit your product, clients, and applicable standards. What never changes is **no branch may grant access based on an unverified credential or an unapproved source**.

## 27. References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer header, form/query alternatives, one token source per request, `invalid_request`, `invalid_token`, `insufficient_scope`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): `Authorization`, authentication challenges, 401/403, and HTTP headers.
- [Spring Security — Servlet OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer filter, authentication, and Resource Server configuration.
- [Spring Security API — DefaultBearerTokenResolver](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html): Bearer sources and form/query/header config.
- [Spring Security — WebFlux OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): reactive Bearer authentication.
- [Spring Security API — ServerBearerTokenAuthenticationConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/server/ServerBearerTokenAuthenticationConverter.html): reactive token conversion.
- [Spring Security — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): multiple `SecurityFilterChain` beans and matcher ordering.
- [Spring Security — WebFlux Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`/`ServerHttpSecurity`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token profiles and distinguishing access tokens.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): validating opaque access tokens, `active`, and metadata.
- [OWASP API Security Top 10](https://owasp.org/API-Security/): authorization and credential handling risks.
- [OWASP HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): HTTP protection headers relevant to web deployments.

**Conclusion:** A good custom token resolver is not one that "finds a token in as many places as possible", but one that **accepts only approved credential sources, detects ambiguity, preserves standard parsing/challenges, and never swallows Bearer errors**. When multiple authentication mechanisms exist, **split `SecurityFilterChain` by route**; if they must share an endpoint, enforce a **conflict policy with zero fallback after credential failure**. Whether tokens come from the standard header or a protected gateway header, **`JwtDecoder`/`OpaqueTokenIntrospector` and authorization policies remain mandatory steps**. Keeping a sharp boundary between *credential extraction*, *credential verification*, and *resource permission checks* is how you keep input validation consistent without weakening system security.
