# Default Token Source and Customizing the Header Name by Contract

## 1. Where are bearer tokens read from?

In **Spring Security OAuth 2.0 Resource Server**, an API access request typically carries an access token in an HTTP header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
~~~

The Resource Server needs to find the access token string in the request before verifying the JWT signature, expiration, issuer, audience, and access permissions. The component that locates the token string is called **BearerTokenResolver**.

By default, Spring Security reads from **`Authorization: Bearer <access_token>`**. This is also the standard way to transmit Bearer tokens per RFC 6750. Some integration setups, however, use a contract that delivers the token in a custom header:

~~~http
X-Access-Token: Bearer <access_token>
~~~

In such cases, configuration can change **the header name being read** to match the client or API gateway. Distinguish clearly between:

- **Token source:** HTTP header, form body, or query parameter.
- **Value format:** does it have a `Bearer ` prefix or is it a raw token string?
- **Token validation:** was the token actually issued for this API, is it unexpired, and does it carry the required permissions?

Changing the header name affects only the token source; it does not alter the trust checks performed on the access token.

## 2. Default behavior of Spring Security

### 2.1. Basic Resource Server configuration

Spring Boot example using Spring MVC and JWT access tokens:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

The URI above is only an example; replace it with the actual issuer trusted by the application.

Security configuration:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );
        return http.build();
    }
}
~~~

This example lets Spring Security use the default resolver. The client calls:

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

There is no need to call `request.getHeader("Authorization")` manually inside the controller; the Spring Security filter processes the token string before the request reaches business logic.

### 2.2. Participating components

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenResolver"]
    C --> D{"Bearer token present?"}
    D -->|No| E["Continue filter chain; protected endpoints require authentication"]
    D -->|Yes| F["AuthenticationManager"]
    F --> G["JwtDecoder or OpaqueTokenIntrospector"]
    G --> H{"Token valid?"}
    H -->|No| I["401 Unauthorized"]
    H -->|Yes| J["Authentication in SecurityContext"]
    J --> K["Check scope/authority and business permissions"]
    K --> L{"Permitted?"}
    L -->|No| M["403 Forbidden"]
    L -->|Yes| N["Controller processes request"]
~~~

`BearerTokenResolver` only **extracts** the token. `JwtDecoder` or the opaque token validation component decides whether the token is trustworthy. Authorization rules then decide whether the authenticated request is permitted to invoke the resource.

### 2.3. `DefaultBearerTokenResolver`

`DefaultBearerTokenResolver` is the default implementation based on RFC 6750. It:

1. Looks up the value from the `Authorization` header.
2. Recognizes the `Bearer` scheme and extracts the token portion.
3. Returns `null` if no Bearer token is present in the checked source.
4. Does not read access tokens from the `access_token` query parameter by default.
5. Does not read access tokens from a form-encoded `access_token` body by default.

Examples:

| Request | Default resolver |
|---|---|
| `Authorization: Bearer abc.def.ghi` | Extracts `abc.def.ghi` for authentication |
| `Authorization: Basic abcdef` | Not treated as a Bearer token |
| `X-Access-Token: Bearer abc.def.ghi` | Does not read custom header |
| `Authorization: abc.def.ghi` | Does not match Bearer format |
| `GET /api/orders?access_token=abc` | Does not accept tokens via URL by default |

**Extracting a token string does not mean authentication succeeded.** For example, `abc.def.ghi` could be forged, expired, or from the wrong issuer.

## 3. Changing the header name by integration contract

Suppose a client must use:

~~~http
GET /api/orders HTTP/1.1
X-Access-Token: Bearer eyJhbGciOi...
~~~

This is a contract that changes the **header name**, while the value still uses the **Bearer** scheme. Spring Security supports this directly via `DefaultBearerTokenResolver#setBearerTokenHeaderName`.

### 3.1. Java configuration

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    BearerTokenResolver bearerTokenResolver() {
        DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();

        // Contract: X-Access-Token: Bearer <access_token>
        resolver.setBearerTokenHeaderName("X-Access-Token");

        return resolver;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            BearerTokenResolver bearerTokenResolver) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(bearerTokenResolver)
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Passing the resolver into the DSL makes it explicit which header the filter chain uses. This is especially useful when an application has multiple `SecurityFilterChain` beans for paths with different authentication styles.

**Important note:** `setBearerTokenHeaderName("X-Access-Token")` only changes the header name to read; it **still requires a `Bearer <token>` formatted value**. For example:

~~~http
X-Access-Token: eyJhbGciOi...
~~~

does not work with the resolver above because the `Bearer` scheme is missing.

With a renamed resolver, do not assume it falls back to reading `Authorization`. If a client still sends `Authorization: Bearer ...`, protected endpoints typically return 401 because no token is found in the newly configured source.

### 3.2. Header name as a deployment configuration

When the header name depends on an environment contract, you can define a custom application property:

~~~yaml
app:
  security:
    bearer-header: X-Access-Token

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

`app.security.bearer-header` is a **project-defined property**, not a property Spring automatically uses to alter the resolver.

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            @Value("${app.security.bearer-header}") String headerName)
            throws Exception {

        DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
        resolver.setBearerTokenHeaderName(headerName);

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(resolver)
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Configuring a `@Bean BearerTokenResolver` versus creating the resolver inline inside `SecurityFilterChain` are independent choices; pick whichever fits the architecture. The goal is to wire the right resolver instance into the filter chain to be protected.

HTTP header names are case-insensitive, though integration docs should use one canonical casing so both sides implement consistently.

### 3.3. `Proxy-Authorization` example

Spring Security includes an example using the HTTP constant:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setBearerTokenHeaderName(HttpHeaders.PROXY_AUTHORIZATION);
~~~

Matching request:

~~~http
Proxy-Authorization: Bearer <ACCESS_TOKEN>
~~~

`Proxy-Authorization` has specific HTTP semantics related to proxies, so choose it only when the gateway/proxy-to-backend contract explicitly requires it. Intermediary proxies may process this header differently from ordinary application headers.

## 4. Custom header with a raw token: a different contract

Compare:

~~~http
X-Access-Token: Bearer eyJhbGciOi...
~~~

and:

~~~http
X-Access-Token: eyJhbGciOi...
~~~

First case: change the header name using `DefaultBearerTokenResolver#setBearerTokenHeaderName`.

Second case: **no Bearer scheme**. In some integrations with a provider/gateway sending a raw token or identity assertion in a custom header, Spring Security provides `HeaderBearerTokenResolver`:

~~~java
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.HeaderBearerTokenResolver;

// Contract header carries the JWT directly, without a Bearer prefix.
BearerTokenResolver resolver =
    new HeaderBearerTokenResolver("X-JWT-Assertion");
~~~

This resolver treats the custom header's value as the value to pass to authentication processing. It does not by itself prove that the header was created by a trusted gateway. If the provider sends an identity assertion rather than an access token meant for the API, the system must also clearly define the validation mechanism, token type, and trust boundary before using it.

**Do not switch to reading raw tokens merely to work around a client omitting `Bearer`.** Updating the client to match the contract is the preferred path. If the contract genuinely specifies raw tokens, clearly specify who is allowed to set the header, its format, issuer, audience, TTL, and how the application validates it.

## 5. Do not confuse renaming the header with enabling query/form sources

Besides HTTP headers, `DefaultBearerTokenResolver` has two transport-related options:

### 5.1. Form-encoded body parameter

~~~java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowFormEncodedBodyParameter(true);
~~~

This allows reading `access_token` in form-encoded requests under supported conditions:

~~~http
POST /api/process HTTP/1.1
Content-Type: application/x-www-form-urlencoded

access_token=<ACCESS_TOKEN>&action=check
~~~

This option **defaults to `false`**. Enable it only if compatibility truly requires it; tokens in bodies can end up in payload logs or be mishandled by infrastructure.

### 5.2. URI query parameter

~~~java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowUriQueryParameter(true);
~~~

Example URL:

~~~http
GET /api/orders?access_token=<ACCESS_TOKEN> HTTP/1.1
~~~

This option also **defaults to `false`**. RFC 6750 advises against URI-based transport: URLs can appear in browser history, proxy logs, access logs, monitoring, analytics, or be accidentally shared.

If you only need to change the header from `Authorization` to `X-Access-Token`, **keep both form and query options at their default values**. Renaming the header does not require enabling extra token sources.

### 5.3. Avoid ambiguous multi-source token input

A request carrying a token in both a header and a URL/form creates an ambiguity: which value should the system trust? `DefaultBearerTokenResolver` handles certain multi-source cases when query/form support is enabled, but API design should pick **one clear token source**. Do not build an ad-hoc fallback from an old header to a new header without defining control policies and precedence rules.

## 6. Header configuration is independent of JWT validation and authorization

A successfully extracted access token is not guaranteed to be permitted for use.

For example, a token contains:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "aud": ["inventory-api"],
  "scope": "items.read",
  "exp": 2000000000
}
~~~

This is an illustrative payload, not a signed JWT. Suppose Orders API only accepts tokens whose `aud` includes `orders-api`; the token above must be rejected even if it arrives in the expected header and has a valid signature from the same issuer.

Separate the processing layers clearly:

| Layer | Question | Typical component |
|---|---|---|
| Token resolution | Which header holds the token and does it match the scheme? | `BearerTokenResolver` |
| Authentication | Is the token valid, with the right issuer, audience, expiration, signature, or introspection? | `JwtDecoder` / opaque token introspector |
| Authorization | Does the subject have the necessary authority/scope and resource permissions? | `authorizeHttpRequests` and business logic |

An endpoint can require a scope as follows:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
);
~~~

Import `org.springframework.http.HttpMethod` when using the snippet above. For JWTs with supported scope claims, Spring Security by default maps `orders.read` to authority `SCOPE_orders.read`.

When the token is an **opaque token**, the resolver can still read the same header, while the Resource Server uses `opaqueToken(...)` and introspection instead of `jwt(...)`. Header format and token-string validation are two distinct decisions.

## 7. Illustrating a contract with an API Gateway

An architecture might use the following convention:

~~~mermaid
sequenceDiagram
    participant Client as Web / Mobile Client
    participant Gateway as API Gateway
    participant API as Spring Resource Server
    Client->>Gateway: Authorization: Bearer access_token
    Gateway->>API: X-Access-Token: Bearer access_token
    API->>API: BearerTokenResolver reads X-Access-Token
    API->>API: Validate access token and authorize
    API-->>Gateway: HTTP response
    Gateway-->>Client: HTTP response
~~~

The diagram is merely an **example of a header-forwarding contract**. In many systems, the gateway can keep `Authorization` unchanged; there is no need to rename it unless required.

For a custom header set by the gateway, specify:

- **Inbound:** which header the client sends, and how the gateway receives and transforms it.
- **Outbound:** which header the backend reads, and whether legacy versions are supported.
- **Trusted source:** whether the gateway strips any externally supplied value of that custom header before setting its internal value.
- **Network path:** whether the backend can be called directly to bypass the gateway.
- **Validation:** which token checks are performed by the gateway, the backend, or both.
- **Logging:** whether token-bearing headers are masked/redacted from logs and telemetry.

Renaming a header **does not encrypt the token** and adds no security by itself. Use TLS on appropriate links, restrict network access, enforce policy on internal headers, and prevent tokens from leaking into logs.

In particular, a header named `X-Access-Token` does not prove the request came from the gateway. If the backend trusts a gateway-generated header, infrastructure must ensure clients cannot inject spoofed values and call the backend directly to bypass controls.

## 8. API call examples and interpreting results

Suppose Orders API is configured for `X-Access-Token` in `Bearer <token>` format and protects `GET /api/orders`.

### Case A: right source and right syntax

~~~bash
curl -i \
  -H "X-Access-Token: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

The resolver extracts the token; the system validates it and checks permissions. It can return `200 OK` if all steps succeed.

### Case B: sent using the old header

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

If the filter chain only reads `X-Access-Token` and has no other authentication mechanism, protected endpoints typically return **401 Unauthorized** because no token is found.

### Case C: missing scheme

~~~bash
curl -i \
  -H "X-Access-Token: <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

`DefaultBearerTokenResolver` does not recognize this as a Bearer header under the configured rules. Protected endpoints typically return **401**.

### Case D: invalid token

~~~bash
curl -i \
  -H "X-Access-Token: Bearer invalid.token.value" \
  https://api.example.test/api/orders
~~~

The resolver can extract the string, but the JWT validation step rejects it; typically **401**.

### Case E: valid token lacking scope

A token that authenticates successfully but lacks `SCOPE_orders.read` for an endpoint requiring that authority typically yields **403 Forbidden**.

Summary table:

| Request | `X-Access-Token` resolver | Expected result |
|---|---|---|
| `X-Access-Token: Bearer <valid_access_token>` | Token found | 200 if authorized, otherwise 403 |
| `Authorization: Bearer <valid_access_token>` | Does not read old header | 401 if no other auth mechanism |
| `X-Access-Token: <token>` | Does not match Bearer syntax | 401 |
| No token header | No token | 401 |
| `X-Access-Token: Bearer <expired_token>` | Token found, but expired | 401 |
| `X-Access-Token: Bearer <token_with_wrong_audience>` | Token found, but not for this API | 401 if audience validation is configured |

The table assumes the endpoint genuinely requires authentication and uses standard Resource Server error handling; gateways, custom filters, or business logic may add extra conditions and error messages.

## 9. Common mistakes

### 9.1. Assuming renaming the header makes the resolver read raw JWTs

`setBearerTokenHeaderName` only changes the header name; it **does not remove the `Bearer` prefix**. If the contract value has no scheme, handle the exact format explicitly from the start rather than silently accepting arbitrary strings.

### 9.2. Manually reading the token in a controller to decide permissions

~~~java
String token = request.getHeader("X-Access-Token");
~~~

This snippet only reads raw input. It does not replace signature, issuer/audience, expiration, authority, and data policy checks. Configure the source via `BearerTokenResolver` so Spring Security establishes an authenticated principal before the controller is invoked.

### 9.3. Confusing ID Tokens with access tokens

An OIDC **ID Token** is used by an OIDC client to confirm login identity. A Resource Server needs an **OAuth 2.0 access token intended for the API**. Changing the header to accept an ID Token does not make an ID Token a valid API access token.

### 9.4. Checking only the resolver and forgetting audience

A validly signed JWT issued for a different service still must not be accepted by this API. Use an audience validator and appropriate token checks; the header name does not solve this.

### 9.5. Letting all clients use multiple headers via fallback

Some clients send `Authorization`, while others send `X-Access-Token`. If a migration is needed, define exact timelines, intake rules, precedence, and behavior when both are present; avoid ad-hoc fallbacks that blur the trust source.

### 9.6. Forgetting to update gateway or client configuration

If the backend switches to `X-Access-Token` while the gateway still forwards `Authorization`, the backend will not see the token. Transport contracts must be updated consistently on both sides.

## 10. Quick application example for a specific contract

New contract:

~~~text
Endpoint: GET /api/orders
Header:   X-Partner-Authorization
Value:    Bearer <access_token>
~~~

Corresponding resolver:

~~~java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setBearerTokenHeaderName("X-Partner-Authorization");

http.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(resolver)
    .jwt(Customizer.withDefaults())
);
~~~

Client sends:

~~~http
GET /api/orders HTTP/1.1
X-Partner-Authorization: Bearer eyJhbGciOi...
~~~

Ensure the access token is issued by a trusted issuer, intended for Orders API, unexpired, and carries the `orders.read` permission. None of these token properties change just because the header has a different name.

If the contract instead specifies `X-Partner-Authorization: <raw-jwt>`, the configuration concern shifts to **header value syntax**; `HeaderBearerTokenResolver` and additional trust policies may be needed.

## 11. Takeaways

- By default, Spring Security Servlet Resource Server looks for tokens in **`Authorization: Bearer <access_token>`**.
- `DefaultBearerTokenResolver#setBearerTokenHeaderName(...)` changes **which header is read**, while still using the Bearer scheme.
- For contracts carrying raw tokens in a custom header, use an appropriate solution such as `HeaderBearerTokenResolver` and clearly define the trust boundary.
- Body and query parameters for carrying tokens are **disabled by default**; avoid enabling them unless truly necessary.
- Token extraction, token validation, and authorization are independent steps.
- For standard OAuth 2.0 APIs, keep `Authorization: Bearer ...` for standards compatibility; rename the header only when an integration contract explicitly requires it.

### References

- [Spring Security — OAuth 2.0 Resource Server Bearer Tokens (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security API — DefaultBearerTokenResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html)
- [Spring Security API — HeaderBearerTokenResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/HeaderBearerTokenResolver.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
