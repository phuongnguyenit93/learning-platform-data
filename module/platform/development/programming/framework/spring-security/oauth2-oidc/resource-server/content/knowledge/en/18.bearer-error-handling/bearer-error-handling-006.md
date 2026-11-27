# BearerTokenAccessDeniedHandler and Insufficient-Permission Responses

When a **Spring Security OAuth 2.0 / OIDC Resource Server** application receives a Bearer access token, there are two distinct security questions: **can the token be authenticated** and **does the authenticated principal have sufficient permissions to perform the operation**. If the token is valid but permissions are insufficient, the API usually needs to return **HTTP 403 Forbidden**. With Bearer tokens, the response may also carry a **`WWW-Authenticate`** header per **RFC 6750**, stating the `insufficient_scope` error so the Client understands the current credential lacks the required permissions.

Spring Security provides **`BearerTokenAccessDeniedHandler`** to handle `AccessDeniedException` in a Resource Server. It is an **`AccessDeniedHandler`**, not the component that decodes JWTs, not where scopes are computed, and not where user access to specific orders is determined. It is responsible for **rendering access denial into an HTTP response aligned with Bearer authentication**.

For example, Shop Web holds a valid access token carrying only the `orders.read` scope:

~~~http
POST /api/orders/42/cancel HTTP/1.1
Host: orders.example.test
Authorization: Bearer <valid-access-token-with-orders.read>
~~~

The Orders API requires `SCOPE_orders.cancel` for the order-cancellation endpoint. The token was verified but lacks this authority, so **the cancellation must not run**. An illustrative response:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
~~~

Depending on version/configuration, the actual header may add `error_description` and `error_uri`. Do not assume the default handler will always pinpoint the exact missing scope or automatically generate a JSON body.

> **Key takeaway:** `BearerTokenAccessDeniedHandler` is invoked when authorization denies access. It emits the appropriate **403 and Bearer challenge**. **`BearerTokenAuthenticationEntryPoint`**, by contrast, serves cases requiring authentication initiation or invalid authentication, typically producing **401**. The two components solve **two different kinds of failures**.

## 1. Context: OAuth2 Client, Authorization Server, and Resource Server

Suppose the retail system consists of:

- **Identity Server:** Authorization Server issuing signed JWTs or opaque OAuth 2.0 access tokens.
- **Shop Web:** OAuth2/OIDC Client requesting access tokens and calling APIs on the user's behalf.
- **Orders API:** Spring Security Resource Server protecting orders.
- **Order Service/Database:** enforces ownership, tenant, order status, and staff assignment rules.

A permission contract:

| Request | Minimum Authority | Additional Business Condition |
| --- | --- | --- |
| `GET /api/orders/42` | `SCOPE_orders.read` | Caller is allowed to view order 42 |
| `POST /api/orders` | `SCOPE_orders.write` | Permitted to create orders in the current tenant |
| `POST /api/orders/42/cancel` | `SCOPE_orders.cancel` | Valid owner/role and order is still cancellable |
| `GET /api/public/catalog` | No Bearer token required | Displays public data only |

When checking a Bearer access token, **authentication** must verify the token per the AS/API contract: signature and `iss`/`aud`/expiration for JWTs, or `active` and resource binding for opaque tokens via introspection. Only then does **authorization** evaluate scopes/authorities and record-level permissions.

~~~mermaid
flowchart TD
    A["HTTP request + Bearer token"]
    B["BearerTokenAuthenticationFilter"]
    C["JWT verification or opaque introspection"]
    D{"Valid Authentication present?"}
    E["BearerTokenAuthenticationEntryPoint<br>401 (authentication)"]
    F["AuthorizationFilter / method security"]
    G{"Sufficient authority and policy?"}
    H["AccessDeniedException"]
    I["BearerTokenAccessDeniedHandler<br>403 + WWW-Authenticate"]
    J["Controller / service executes"]

    A --> B --> C --> D
    D -->|No| E
    D -->|Yes| F --> G
    G -->|No| H --> I
    G -->|Yes| J
~~~

This is a **conceptual flow**: some public requests do not require a token; exact errors and handling locations may vary by filter chain, exception handler, Spring Security version, and integration setup. The core rule is **never execute protected business logic when authentication/authorization has not succeeded**.

## 2. Distinguishing Authentication Failure and Access Denied

An API may return a similar "not allowed" message, yet the underlying causes differ greatly.

| Situation | Layer to Handle | Typical HTTP | Common Bearer Error |
| --- | --- | --- | --- |
| No token sent to protected endpoint | Authentication | **401** | `Bearer` challenge, possibly without `error` |
| Token has bad signature, inactive, or expired | Authentication | **401** | `invalid_token` when applicable |
| Malformed token / Bearer request violates rules | Authentication | Possibly 400/401 per error and framework | `invalid_request` or another RFC error |
| Valid token, missing endpoint scope | Authorization | **403** | `insufficient_scope` |
| Valid token, has scope, missing role/permission | Authorization | **403** | Possibly `insufficient_scope` under Bearer handler, even though cause is permission |
| Valid token, sufficient scope, wrong tenant/owner | Resource policy | **403** or **404** per contract | Depends on how policy and error handling are designed |
| API call to JWKS/introspection times out | Authentication dependency | Depends on exception handling | Must never pretend token is valid |

**401 is not a “stricter 403”**. It indicates the Client needs to provide an accepted credential; **403** indicates the request reached the permission boundary and was denied. Do not automatically return 401 for every missing-scope case, as that can trap Clients in pointless login/token-refresh loops.

### 2.1. Two Exception Paths in Spring Security

**`AuthenticationException`** represents an authentication failure. A Resource Server normally uses an `AuthenticationEntryPoint` to emit the corresponding challenge:

~~~java
BearerTokenAuthenticationEntryPoint authenticationEntryPoint =
        new BearerTokenAuthenticationEntryPoint();
~~~

**`AccessDeniedException`** represents permission denial after policy evaluates the request:

~~~java
BearerTokenAccessDeniedHandler accessDeniedHandler =
        new BearerTokenAccessDeniedHandler();
~~~

In the filter chain, `ExceptionTranslationFilter` translates security exceptions into responses via the entry point or access denied handler. If the caller has no trusted authentication in a protected context, an `AccessDeniedException` can also trigger the entry point instead of 403. Branching depends on authentication context and configured filters.

**Do not manually throw `AccessDeniedException` just to produce a 403 before validating the token**. Let the Bearer filter and authentication provider handle invalid/missing tokens; policy decides permissions.

## 3. RFC 6750: Bearer Challenges and `insufficient_scope`

**RFC 6750 — OAuth 2.0 Bearer Token Usage** describes how Clients present Bearer tokens and how Resource Servers respond to certain errors. The `WWW-Authenticate` header uses the `Bearer` authentication scheme and may include parameters:

| Parameter | Purpose | Note |
| --- | --- | --- |
| `realm` | Advertised protection space | Configurable; not required on every response |
| `error` | Bearer error code | E.g., `invalid_token`, `insufficient_scope` |
| `error_description` | Short Client-facing description | Must not leak tokens, internal data, or other users' identities |
| `error_uri` | URI to error documentation | May point to the relevant specification section |
| `scope` | Hint of required scope | Optional per RFC; do not assume Spring's default handler computes it automatically |

For permission errors:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

A configuration with a realm might return:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", error_description="The request requires higher privileges than provided by the access token."
~~~

These are **examples**; parameter ordering, `error_description`, and `error_uri` may differ in real releases. Test the exact response of the Spring Security version you deploy.

### 3.1. `insufficient_scope` Does Not Mean “The Scope Will Fix Itself”

The `insufficient_scope` code says **the credential does not provide enough permissions to satisfy the request**. It does **not** automatically:

- Request additional scopes from the Authorization Server.
- Refresh the access token.
- Add authorities to `SecurityContext`.
- Convert roles into scopes.
- Modify permissions in the database.
- Delete or revoke the access token.
- Return the exact scope the Client needs to request.

The Client can use the error info to **display an insufficient-permissions message** or initiate a **deliberate flow requesting additional permissions** if supported by the product and Authorization Server. **Never automatically retry infinitely or unilaterally request higher scopes** just because a 403 was received.

### 3.2. `WWW-Authenticate` Can Appear on Both 401 and 403

A common misconception is that “`WWW-Authenticate` is only used with 401”. In the Bearer protocol, `WWW-Authenticate` can also accompany **403** with `insufficient_scope`. It provides error metadata under the authentication scheme and does not mean the server is asking the Client to log in again.

Comparison example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

and:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
~~~

Clients should inspect both status and error code, not merely check whether the header contains the word `Bearer`.

### 3.3. Should the `scope` Parameter Be Sent?

RFC 6750 permits the Resource Server to indicate the required scope via the `scope` parameter in an `insufficient_scope` error when appropriate. However, many endpoints require **roles, permissions, data rights, or combined conditions** that cannot be expressed as a simple scope string.

**The default `BearerTokenAccessDeniedHandler` does not inspect the entire `SecurityFilterChain` to deduce “the missing scope”**. If you want to send `scope="orders.cancel"`, you need a custom design backed by trusted endpoint requirement data, weighing the risk of disclosing policy details. Never inject Client-supplied values or exception messages containing internal data into headers.

## 4. What Does `BearerTokenAccessDeniedHandler` Actually Do?

`BearerTokenAccessDeniedHandler` is an `AccessDeniedHandler` implementation in Spring Security OAuth2 Resource Server:

~~~java
import org.springframework.security.oauth2.server.resource.web.access
        .BearerTokenAccessDeniedHandler;

BearerTokenAccessDeniedHandler handler =
        new BearerTokenAccessDeniedHandler();
~~~

When `handle(request, response, accessDeniedException)` is called, its job is to:

1. Set **HTTP 403 Forbidden** on the denied request.
2. Create or append an appropriate **`WWW-Authenticate: Bearer ...`**.
3. When Spring Security determines the request has valid OAuth2 authentication in a Bearer context, include `insufficient_scope` info per RFC 6750.
4. If a valid Bearer authentication context cannot be confirmed, do not unconditionally assert missing scope; the response may simply contain a generic Bearer challenge or 403 per implementation behavior.

This handler class is **not responsible for**:

- Verifying JWT signatures with JWKS.
- Introspecting opaque tokens.
- Selecting `SecurityFilterChain` or matching `requestMatchers`.
- Mapping `scope` or nested roles into `GrantedAuthority`.
- Determining owner/tenant of an Order.
- Producing a default business JSON body following your application's template.

### 4.1. The Handler Is Not the Authorization Decision Maker

Example:

~~~java
.requestMatchers(HttpMethod.POST, "/api/orders/{id}/cancel")
    .hasAuthority("SCOPE_orders.cancel")
~~~

The `hasAuthority(...)` rule itself decides whether the caller may invoke the URL. If the required authority is missing, Spring Security may throw `AccessDeniedException`. **`BearerTokenAccessDeniedHandler` translates that decision into HTTP 403**; it does not replace the rule.

If a developer removes the `hasAuthority` rule while keeping the handler, the endpoint may accidentally become open because **there is no longer a deny decision invoking the handler**. That is why both allow and deny paths must be tested.

### 4.2. `setRealmName`

You can configure a realm so the API challenge carries a recognizable identifier:

~~~java
BearerTokenAccessDeniedHandler deniedHandler =
        new BearerTokenAccessDeniedHandler();
deniedHandler.setRealmName("orders-api");
~~~

Realm is a **protection label**, not a JWT audience, OAuth2 Client ID, issuer, or role name. Setting `realm="orders-api"` **does not automatically verify `aud`** on the token. The API still must validate audience/resource per contract.

### 4.3. Differences from `BearerTokenAuthenticationEntryPoint`

| Component | Type | Used For | Typical Status |
| --- | --- | --- | --- |
| `BearerTokenAuthenticationEntryPoint` | `AuthenticationEntryPoint` | Requests needing authentication or invalid tokens | 401 |
| `BearerTokenAccessDeniedHandler` | `AccessDeniedHandler` | Requests denied by authorization | 403 |

Both handlers may share the same realm, yet they are not interchangeable. Using the entry point to handle missing scopes makes the API return **401** instead of **403**. Using the access denied handler for malformed token errors misleads Clients with a bogus `insufficient_scope`.

## 5. Default Behavior with a JWT Resource Server

Symbolic example of a verified JWT access token:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893459600
}
~~~

In Spring Security JWT Resource Server, the `scope` claim is typically mapped to:

~~~text
SCOPE_orders.read
~~~

Suppose the cancellation endpoint requires:

~~~java
hasAuthority("SCOPE_orders.cancel")
~~~

Outcome:

~~~text
Authentication: valid
JWT issuer/audience/time: verified
GrantedAuthorities: [SCOPE_orders.read]
Endpoint rule: requires SCOPE_orders.cancel
Authorization: denied
BearerTokenAccessDeniedHandler: emits 403 response
WWW-Authenticate: Bearer ... insufficient_scope ...
~~~

**A validly signed token does not mean the token has sufficient permissions**. Likewise, **the `orders.read` scope does not automatically imply `orders.cancel`**, unless AS/API policy defines an implication rule and the system enforces it properly.

### 5.1. Opaque Tokens Can Also Hit This Handler

For an opaque access token, `OpaqueTokenIntrospector` might return:

~~~json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "user-842"
}
~~~

After introspection, Spring Security creates an OAuth2 Bearer authentication with the appropriate authorities. If an HTTP rule requires `SCOPE_orders.cancel`, the request can likewise be denied by `BearerTokenAccessDeniedHandler`. The handler **does not need to know** whether the token was verified via JWS or introspection; it operates at the **authorization response layer**.

However, scope, issuer, audience, active status, and required claims must still be handled beforehand per contract. **Never treat `active=true` or a valid signature as permission to execute every request**.

## 6. Spring Boot 3 / Spring Security 6 Configuration

Example Orders API using signed JWT access tokens.

### 6.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 6.2. Configuring the Token Verification Source

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}
~~~

Example:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
~~~

URIs are illustrative only. Beyond issuer, the app must ensure **the audience matches Orders API**, token type/profile, algorithm, and lifetime per contract. `BearerTokenAccessDeniedHandler` does not add those JWT validators. If building a custom `JwtDecoder`, configure validators properly and never substitute response handler logic for them.

### 6.3. SecurityFilterChain with Bearer Handlers

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access
        .BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        BearerTokenAuthenticationEntryPoint entryPoint =
                new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler deniedHandler =
                new BearerTokenAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.POST,
                        "/api/orders/{id}/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().denyAll())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Points to note:

- `oauth2ResourceServer().jwt()` enables the Bearer JWT authentication pipeline.
- `authenticationEntryPoint(...)` formats errors when authentication fails, commonly **401**.
- `accessDeniedHandler(...)` formats insufficient-permission errors, commonly **403**.
- `requestMatchers` **makes the authorization decision** by method and URL.
- `anyRequest().denyAll()` within the chain blocks undeclared API routes.
- Realm is only a challenge label; it does not grant permissions or validate audience.

In standard Resource Server setups, Spring Security normally configures suitable Bearer entry points and denied handlers when not overridden. **Explicit configuration** here clarifies the functionality and provides a customization hook. You do not need to recreate handlers in every app; what matters is not accidentally losing Bearer behavior when plugging in another exception handler.

This example is solely for REST APIs **authenticated by Bearer tokens in headers**, using no session cookies for `/api/**`; hence the chain disables CSRF and uses stateless sessions. Apps with a web UI/sessions must configure CSRF/filter chains appropriately. Additionally, `securityMatcher("/api/**")` only covers `/api/**`; another policy/chain must cover endpoints outside this scope.

### 6.4. Opaque Token Variant

If the Resource Server uses token introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

In `SecurityFilterChain`, replace the JWT portion with:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

**This is an alternative configuration**, not adding both pipelines and expecting the framework to guess the token type. The access denied handler still responds to insufficient-permission errors after the opaque token has been introspected and authentication is valid.

## 7. Analyzing Specific HTTP Scenarios

Suppose `GET /api/orders/{id}` requires `orders.read` and `POST /api/orders/{id}/cancel` requires `orders.cancel`.

### 7.1. No Bearer Token Sent

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
~~~

This is a **missing authentication** error, not a missing-scope error on a verified token. The API typically responds:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

**`BearerTokenAuthenticationEntryPoint`** is the appropriate component. Do not return `insufficient_scope` because the caller has not provided a token for the system to evaluate permissions.

### 7.2. Expired JWT, Bad Signature, or Wrong Issuer/Audience

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <invalid-or-expired-token>
~~~

`JwtDecoder` or a contract validator rejects the token. This is an **authentication failure**, usually producing 401 and potentially carrying `invalid_token`. The Client may need to obtain a new access token **via a valid OAuth flow**. Do not include private key details, sensitive claims, or stack traces in the response.

### 7.3. Valid Token with Insufficient Scope

~~~http
POST /api/orders/42/cancel HTTP/1.1
Authorization: Bearer <valid-token-with-only-orders.read>
~~~

The token is verified, yet the authority lacks `SCOPE_orders.cancel`. This is **access denied**, commonly:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
~~~

Order 42 must not be cancelled and no cancellation event may be emitted when the request is denied.

### 7.4. Valid Token and Sufficient Scope, but Data Permissions Denied

The caller has `orders.read`, yet Order 42 belongs to another tenant:

~~~text
Authentication: success
HTTP scope: success
Data policy: denied (tenant mismatch)
~~~

If the policy throws `AccessDeniedException` and passes through Bearer exception handling, the response may be **403**, sometimes carrying `insufficient_scope` because the handler sees an existing OAuth2 Authentication. That **does not prove the true cause was a missing OAuth scope**: it could be role, owner, tenant, or data status.

If the API wants to avoid disclosing the existence of Order 42, it can deliberately return **404** under a consistent policy. A generic `AccessDeniedHandler` does not decide per-resource 403-vs-404 policies on its own. The development team must design clear resource policies and exception mappings so Clients cannot infer other users' data from error descriptions.

### 7.5. Public Endpoint

~~~http
GET /api/public/catalog HTTP/1.1
~~~

`permitAll()` allows the request without authentication. Still, sending a **broken Bearer token** to a public endpoint can cause the Bearer filter to process the token and return an error before reaching the public rule; do not assume `permitAll()` bypasses all filters. Public tests should include a case **without an Authorization header**.

## 8. `insufficient_scope` vs. `hasRole` and `hasAuthority`

Spring Security checks `GrantedAuthority`. In a JWT Resource Server, the default `JwtGrantedAuthoritiesConverter` typically maps the `scope` or `scp` claim to authorities prefixed with `SCOPE_`:

~~~json
{
  "sub": "user-842",
  "scope": "orders.read orders.write"
}
~~~

into:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

The rule:

~~~java
hasAuthority("SCOPE_orders.cancel")
~~~

differs from:

~~~java
hasAuthority("orders.cancel")
~~~

If the app uses roles:

~~~java
hasRole("ORDER_SUPPORT")
~~~

Spring Security normally checks `ROLE_ORDER_SUPPORT` by the role-prefix convention. **`BearerTokenAccessDeniedHandler` does not map or fix prefixes**. If roles live in nested claims, you must configure a converter per contract; otherwise the API may keep returning 403 even when the token carries an `order_support` string that the backend never turned into an authority.

### 8.1. Missing OAuth Scope or Missing Business Permission?

| Rule | Permission Data Source | When Denied |
| --- | --- | --- |
| `hasAuthority("SCOPE_orders.read")` | OAuth scope mapped from token | Matches `insufficient_scope` semantics |
| `hasAuthority("ROLE_ORDER_SUPPORT")` | Role mapping per contract | 403; handler may still emit generic `insufficient_scope` |
| `hasAuthority("PERM_order:cancel:own")` | Custom permission from token/policy | 403; not necessarily missing OAuth scope |
| `@orderAccess.canRead(authentication, id)` | Actual tenant/owner/data | 403 or 404 per policy |

If detailed reporting between “missing scope” and “does not own order” is required, **design a separate business error taxonomy** without leaking sensitive information. Never make an exception handler guess the cause purely from `AccessDeniedException.getMessage()`.

## 9. Customizing the JSON Body While Preserving `WWW-Authenticate`

Many REST APIs want JSON responses using `application/problem+json` or a uniform error schema. One approach is to **delegate to `BearerTokenAccessDeniedHandler` first to set status/headers**, then write a public JSON body.

### 9.1. Mistake: Replacing the Handler with Pure JSON Responses

Example:

~~~java
// Do not use if it strips the Bearer challenge required by the contract.
response.setStatus(403);
response.setContentType("application/json");
response.getWriter().write("{\"error\":\"forbidden\"}");
~~~

This code can return 403, yet omits `WWW-Authenticate` per RFC 6750. An OAuth2 Client or API gateway relying on the Bearer header loses the info needed to handle the error.

### 9.2. Wrapping the Standard Handler

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web.access
        .BearerTokenAccessDeniedHandler;

public final class JsonBearerAccessDeniedHandler {

    public static AccessDeniedHandler create() {
        BearerTokenAccessDeniedHandler delegate =
                new BearerTokenAccessDeniedHandler();
        delegate.setRealmName("orders-api");

        return (request, response, exception) -> {
            // Delegate writes 403 and the appropriate WWW-Authenticate Bearer header.
            delegate.handle(request, response, exception);

            if (!response.isCommitted()) {
                response.setCharacterEncoding(
                        StandardCharsets.UTF_8.name());
                response.setContentType("application/problem+json");
                response.getWriter().write("""
                    {
                      "type": "about:blank",
                      "title": "Forbidden",
                      "status": 403,
                      "detail": "You do not have permission to perform this action."
                    }
                    """);
            }
        };
    }

    private JsonBearerAccessDeniedHandler() {}
}
~~~

The illustrative code uses **Java 17+ text blocks**. `delegate` handles status and Bearer headers; the JSON body provides only a **generic** message without leaking tokens, other users' object IDs, or internal permission names. In production, a request/correlation ID can be added per application convention.

Attaching to the filter chain:

~~~java
.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(entryPoint)
    .accessDeniedHandler(
        JsonBearerAccessDeniedHandler.create()))
~~~

This is a **replacement variant for `accessDeniedHandler(deniedHandler)`** in section 6; do not declare both expecting both to be invoked.

### 9.3. Considerations When Adding JSON

- **Preserve status 403** and Bearer headers produced by the delegate.
- Never write the response body **before** the delegate sets headers.
- Do not call `sendError(...)` after writing JSON, as the response may already be committed or the container may overwrite the body.
- Do not use framework exception messages as `detail` for Clients if they contain internal info.
- Ensure the body is valid JSON with proper UTF-8 encoding and no data-escaping bugs.
- If the app's error schema has a `code`, avoid confusing the OAuth protocol error `insufficient_scope` with a business error code.
- For endpoints needing **404 to conceal resources**, do not route every business denial through a generic 403 handler.

A response might look like:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to perform this action."
}
~~~

This is an illustrative response for JSON customization, **not the default body of `BearerTokenAccessDeniedHandler`**.

## 10. Customizing 401 Authentication Responses Must Be Kept Separate

If the API also needs a JSON body for 401 errors, configure `AuthenticationEntryPoint` (or the framework-supported authentication error mechanism), not only `AccessDeniedHandler`.

A standard entry point:

~~~java
BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();
entryPoint.setRealmName("orders-api");
~~~

Key distinction:

~~~text
401 -> no accepted credential present yet
403 -> authentication may be valid, but permission was denied
~~~

If you want the same JSON schema for both 401 and 403, write **two separate wrappers** around the entry point and access denied handler. Never collapse all exceptions into `{"status":403}`, leaving the Client unsure whether it needs a new token or must stop due to missing permissions.

### 10.1. Do Not Disclose Why a JWT Signature Failed

A 401 response should not state “private key kid X of issuer Y does not exist” or echo the raw JWT/header in the body. Those details belong in access-controlled security logs, never in Client responses. Most Clients only need to know the current access token was rejected and must be handled via the appropriate OAuth flow.

### 10.2. Do Not Encourage Infinite Token Refreshes on 403

A Client receiving:

~~~http
403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

should not automatically send refresh tokens repeatedly hoping scopes will grow. Refresh tokens normally cannot grant new permissions beyond the existing authorization grant and policy. If the product supports **incremental authorization/consent**, the Client may explicitly guide the user through a new consent flow when appropriate, never self-escalate permissions.

## 11. Multiple SecurityFilterChains and Handler Placement

A system may host both a Bearer JWT API and a session-cookie web UI:

~~~text
Chain A @Order(1): /api/** -> Bearer Resource Server
Chain B @Order(2): /web/** -> Session login + CSRF
Chain C @Order(3): fallback -> denyAll
~~~

Not every forbidden request should receive `WWW-Authenticate: Bearer`. If a web-session user visits an admin screen without the required role, the app may want to return an **HTML/JSON 403** per web-session conventions, without a Bearer challenge.

Therefore:

- Place `BearerTokenAccessDeniedHandler` in the **SecurityFilterChain protecting APIs with Bearer tokens**.
- Place the web UI's entry point/denied handler in the corresponding session chain.
- Order `@Order` and `securityMatcher` carefully so requests hit the **right chain**.
- Provide a fallback for paths not matched by any specific chain, per system architecture.

### 11.1. Mistake: Handler in a Chain That Does Not Cover the Endpoint

Suppose:

~~~java
.securityMatcher("/api/**")
.exceptionHandling(ex -> ex
    .accessDeniedHandler(new BearerTokenAccessDeniedHandler()))
~~~

The handler belongs only to that chain. `GET /internal/secrets` **is not automatically protected** just because the API chain has an access denied handler. If a request matches no chain, another chain or server/gateway policy must cover it.

### 11.2. Mistake: Overly Broad Rule Prevents the Handler from Ever Running

~~~java
.requestMatchers("/api/**").permitAll()
.requestMatchers(HttpMethod.POST, "/api/orders/{id}/cancel")
    .hasAuthority("SCOPE_orders.cancel")
~~~

An earlier broad matcher can allow the request through before the cancel rule is evaluated. Then **the handler is never invoked**—not because the handler is broken, but because the authorization rule was shadowed. Protect by ordering **specific rules first, default deny last**, backed by negative tests.

## 12. Testing 401/403 and Headers with MockMvc

At the HTTP authorization testing stage, Spring Security Test provides `SecurityMockMvcRequestPostProcessors.jwt()` to simulate a `JwtAuthenticationToken` with defined authorities. It lets you test `hasAuthority` and the access denied handler without starting an Authorization Server.

**Note:** `jwt()` **does not verify signatures or issuer/audience/expiration**; that test checks `SecurityFilterChain` and responses for a mocked authentication. To test `JwtDecoder`, you need an integration test with **genuinely signed Bearer JWTs**.

### 12.1. Test Fixture Controller

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class DemoOrdersController {

    @GetMapping("/orders/{id}")
    String read(@PathVariable String id) {
        return "order:" + id;
    }

    @PostMapping("/orders/{id}/cancel")
    String cancel(@PathVariable String id) {
        return "cancelled:" + id;
    }

    @GetMapping("/public/catalog")
    String catalog() {
        return "public";
    }
}
~~~

This controller is a **fixture** with no real database or policy. When testing business policies, use a real controller/service or mock service asserting no side effects.

### 12.2. Testing Status and `WWW-Authenticate`

Example with **JUnit Jupiter**, `@WebMvcTest`, and MockMvc:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = DemoOrdersController.class)
@Import({OrdersApiSecurity.class, BearerDeniedTest.TestDecoder.class})
class BearerDeniedTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class TestDecoder {
        @Bean
        JwtDecoder jwtDecoder() {
            // Allows testing rules with jwt() without calling JWKS.
            // DO NOT use this decoder in real-signature integration tests.
            return token -> {
                throw new JwtException(
                    "Real JWT verification is tested separately");
            };
        }
    }

    @Test
    void publicCatalogWorksWithoutToken() throws Exception {
        mvc.perform(get("/api/public/catalog"))
            .andExpect(status().isOk());
    }

    @Test
    void noTokenGetsBearerChallenge() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Bearer")));
    }

    @Test
    void readScopeCanRead() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void writeScopeCannotReadOrder() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("insufficient_scope")));
    }

    @Test
    void readScopeCannotCancel() throws Exception {
        mvc.perform(post("/api/orders/42/cancel")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("insufficient_scope")));
    }

    @Test
    void cancelScopeCanCancel() throws Exception {
        mvc.perform(post("/api/orders/42/cancel")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.cancel"))))
            .andExpect(status().isOk());
    }
}
~~~

In the test, `OrdersApiSecurity` is the configuration from section 6. `jwt()` attaches a mocked authentication to the request: that is why tests pass the security filter even though `TestDecoder` never verifies real JWT strings. On different Spring Security/MockMvc versions, adjust imports/auto-config as needed; ensure **Spring Security filters are enabled**.

### 12.3. Why Assert `containsString("insufficient_scope")` Instead of the Entire Header?

Spring Security may include `realm`, `error_description`, `error_uri`, or change header ordering/details across versions. If the test goal is **insufficient permissions → 403 + Bearer insufficient_scope**, asserting essential attributes keeps tests resilient against minor formatting changes.

However, in an **API gateway or Client contract test**, you may need to verify the full header matching your deployed version. Separate the two test levels:

- **Security behavior test:** 403, Bearer challenge, insufficient_scope.
- **HTTP contract test:** exact published parameters and body schema if any.

### 12.4. No-Token and Missing-Scope Tests Must Be Separate Tests

If you only run:

~~~java
get("/api/orders/42").with(jwt())
~~~

the request already carries a mocked authentication and never tests the **no-token** scenario. Similarly, testing only 403 with a token lacking authority does not verify the 401 entry point works.

## 13. Directly Unit Testing `BearerTokenAccessDeniedHandler`

To isolate handler response formatting from HTTP routing, you can use `MockHttpServletRequest` and `MockHttpServletResponse` in a test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.access
        .BearerTokenAccessDeniedHandler;

class BearerAccessDeniedHandlerTest {

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void returnsBearerInsufficientScopeForAuthenticatedJwt()
            throws Exception {

        Jwt jwt = Jwt.withTokenValue("test-only-not-a-signed-token")
                .header("alg", "RS256")
                .claim("sub", "user-842")
                .claim("scope", "orders.read")
                .build();

        JwtAuthenticationToken authentication =
                new JwtAuthenticationToken(
                    jwt,
                    List.of(new SimpleGrantedAuthority(
                        "SCOPE_orders.read")));
        SecurityContextHolder.getContext()
                .setAuthentication(authentication);

        var request = new MockHttpServletRequest();
        var response = new MockHttpServletResponse();

        var handler = new BearerTokenAccessDeniedHandler();
        handler.setRealmName("orders-api");
        handler.handle(request, response,
                new AccessDeniedException("Denied by policy"));

        assertEquals(403, response.getStatus());
        String challenge =
                response.getHeader(HttpHeaders.WWW_AUTHENTICATE);
        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Bearer"));
        assertTrue(challenge.contains("insufficient_scope"));
    }
}
~~~

This test **only verifies the handler with a mocked SecurityContext**. It does not test `JwtDecoder`, JWS signatures, issuer/audience, or how a URL triggers `AccessDeniedException`. Thus you still need the filter-chain tests in section 12 and signed-token integration tests in section 14.

In a real request, Spring Security must only consider JWT authentication valid after the token is verified by the decoder/provider. A unit test manually constructing an authentication is not proof of token authenticity.

## 14. Integration Testing with Genuinely Signed Bearer JWTs

`jwt()` is great for testing rules, yet **skips cryptographic verification**. An end-to-end test for a Resource Server needs to:

1. Generate a test-only RSA/EC key pair; keep the private key strictly inside the test fixture.
2. Configure a mock JWKS endpoint publishing the corresponding public key.
3. Mint genuinely signed JWTs with `iss`, `aud`, `exp`, and `scope` per contract.
4. Send requests carrying `Authorization: Bearer <signed-JWT>` through the real filter chain.
5. Verify sufficient-permission cases pass, and missing-scope cases return **403 + insufficient_scope**.
6. Verify bad signature/issuer/audience/expiration cases produce an **authentication failure**, never confused with a 403 for missing scope.

A test matrix:

| JWT / Request | Token Verification | Endpoint Permission | Expected Result to Verify |
| --- | --- | --- | --- |
| Valid signature, `aud=orders-api`, scope `orders.cancel`, POST cancel | Succeeds | Sufficient | Passes security; business logic decides next |
| Valid signature, scope `orders.read` only, POST cancel | Succeeds | Insufficient | **403**, Bearer insufficient_scope |
| Valid signature, scope `orders.write`, GET order | Succeeds | Insufficient | **403**, Bearer insufficient_scope |
| Bad signature, payload claims `orders.cancel` | Fails | Not evaluated | **Must never** execute protected business logic |
| Expired JWT | Fails | Not evaluated | Usually 401/invalid_token |
| Untrusted `iss` | Fails | Not evaluated | Usually 401 |
| `aud=billing-api` | Fails validation | Not evaluated | Usually 401 |
| Valid JWT with scope, wrong tenant | Succeeds | HTTP scope sufficient, data policy denies | 403/404 per contract |

In particular, when a token carries `"scope": "orders.cancel"` but has an **invalid signature**, the Resource Server must reject it at **authentication**, never building `SCOPE_orders.cancel` from an unverified payload. An access denied handler is never a substitute for token verification.

### 14.1. With Opaque Tokens

The integration test path is similar, replacing JWT/JWKS with a mock introspection endpoint:

~~~text
Bearer opaque token
  -> mock AS introspection POST
  -> active:true, valid audience, scope orders.read
  -> GET orders => passes HTTP authorization
  -> POST cancel => 403 insufficient_scope
~~~

Add cases for `active:false`, wrong audience, wrong introspection credentials, and endpoint 503/timeout: **no permissions are granted when a valid token cannot be introspected**. `BearerTokenAccessDeniedHandler` is not the place to fix introspection errors.

## 15. Testing Negative Paths and Absence of Side Effects

A thorough test for the order-cancellation endpoint does not stop at status codes:

~~~text
POST /api/orders/42/cancel
Valid Bearer token lacking SCOPE_orders.cancel

Expectations:
  - 403 Forbidden
  - WWW-Authenticate contains Bearer insufficient_scope if applicable
  - OrderService.cancel(42) is NOT called
  - Order 42 status does NOT change
  - NO OrderCancelled event is published
~~~

This boundary is vital: an application can end up returning 403 **after** a service already mutated data due to misplaced exception handling. In that case, status tests pass while security has already failed.

### 15.1. Testing with a Mock Service

Illustrative side-effect check:

~~~java
// After sending POST cancel with a token carrying only orders.read:
mockMvc.perform(post("/api/orders/42/cancel")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isForbidden());

verify(orderService, never()).cancel("42");
~~~

This snippet is a **test body** with `orderService` mocked and Mockito imports configured. In real integration tests, check the database and event/outbox if the operation has side effects. The crucial condition is that **authorization must occur before any protected action**.

### 15.2. Negative Cases Beyond Missing Scopes

| Negative Case | Why Test It? |
| --- | --- |
| No token | Ensures the 401 entry point path works |
| Broken Bearer token | Prevents mistaking authentication errors for insufficient_scope |
| Valid token with another scope | Prevents accidentally granting unrelated permissions |
| Token with scope calling undeclared URL | Ensures default deny |
| Token with scope calling different HTTP method | Prevents path-only privilege expansion |
| Token with scope for another tenant | Blocks Broken Object Level Authorization |
| Admin role token from another resource | Prevents cross-API role mapping |
| Endpoint outside `securityMatcher` | Ensures chain/fallback coverage |
| Custom JSON handler | Verifies 403, headers, and body match contract |

Do not rely only on an "all-powerful admin" token in tests. High-privilege tokens can make every route return 200 without proving denial boundaries hold.

## 16. Error Codes for Clients: Handling 401 Differently from 403

Clients can follow these rules:

~~~text
401:
  - credential missing or not accepted
  - consider obtaining a new access token if OAuth flow permits
  - if not possible, guide user to re-authenticate/re-authorize

403 + insufficient_scope:
  - current credential lacks sufficient permissions
  - do not retry identically forever
  - display insufficient permissions or run controlled privilege-request flow

Other 403:
  - caller not permitted under active policy
  - may relate to role, owner, tenant, or data policy

404 per resource protection policy:
  - do not assume the resource exists and is forbidden
~~~

### 16.1. Client Handling Example

Pseudocode:

~~~javascript
async function cancelOrder(orderId, accessToken) {
  const response = await fetch('/api/orders/' + orderId + '/cancel', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + accessToken }
  });

  if (response.status === 401) {
    // Transition to token-acquisition/login flow per application contract.
    throw new Error('Authentication is required or has expired');
  }

  if (response.status === 403) {
    // Do not refresh infinitely by default; permission may genuinely be denied.
    throw new Error('You do not have permission to cancel this order');
  }

  if (!response.ok) {
    throw new Error('Order cancellation failed');
  }
}
~~~

This is an **application-logic** example, not complete secure OAuth2 Client code. In a real browser app, storing and using tokens must follow your Client's security architecture, CORS, CSRF if session cookies exist, refresh/reauthorization mechanisms, and user policies.

### 16.2. Do Not Let Clients Unilaterally Request Higher Scopes

An API may deny a request because organizational policy deliberately withholds that permission from the caller. Receiving `insufficient_scope` does not mean the Client may unilaterally alter authorization requests to ask for `orders.cancel` without user/organization consent or eligibility. If "requesting additional privileges" exists, it must be an explicitly designed flow controlled by the AS.

## 17. Observability, Logging, and Error Info Security

When debugging `BearerTokenAccessDeniedHandler`, determine whether the error comes from:

- Missing/invalid authentication leading to the entry point.
- Valid authentication lacking an authority.
- Method security lacking a permission or role.
- Resource policy blocking owner/tenant.
- Overly broad/narrow matcher or wrong chain order.
- OAuth scope converter not producing `SCOPE_...` properly.

Fields safe to log per policy:

~~~text
request_id
method + normalized path
http_status
security_chain_name / logical policy
error_category: insufficient_authority / invalid_token / forbidden_resource
token_issuer (only once verified)
subject or internal ID (per audit/PII policy)
correlation_id
~~~

**Never log raw Bearer tokens**, client secrets, refresh tokens, private keys, full authorization headers, or unnecessary sensitive claims. Never put tokens in query parameters for "easier tracing". If logging unverified `kid`/`sub`, treat them as caller-controlled data to avoid log injection or high-cardinality metric explosions.

### 17.1. Why Not Return the List of Missing Roles?

An error body like:

~~~json
{
  "requiredInternalRole": "SUPER_ADMIN",
  "allowedTenantIds": ["tenant-A", "tenant-B"],
  "hiddenPolicy": "fraud-team override"
}
~~~

can expose permission logic and organizational data. Clients usually only need to know **insufficient permissions**. If users need instructions to request an official scope, provide appropriate public docs/API contract details—never echo full internal policies in headers or bodies.

### 17.2. Proxies and Gateways Can Modify Headers

If `SecurityFilterChain` emits `WWW-Authenticate` yet the Client does not see it, check reverse proxies/API gateways, CORS, and error-handling layers. A gateway may overwrite statuses/bodies or strip headers. In cross-origin requests, JavaScript may need CORS `Access-Control-Expose-Headers` to **read** `WWW-Authenticate`; the browser blocking JS from reading a response header does not necessarily mean the header was absent on the wire. Verify from authorized Clients and check CORS policy.

## 18. Common Implementation Mistakes

### 18.1. Using the Denied Handler Instead of AuthenticationEntryPoint

If a request missing a token receives `403 insufficient_scope` from the API, the Client cannot tell whether it needs to authenticate or lacks permissions. Keep the **401 authentication** and **403 authorization** paths aligned with their roles.

### 18.2. Configuring the Handler Without Writing Permission Rules

The handler does not automatically know `orders.cancel` is the required scope. If an endpoint is `permitAll()` or only `authenticated()`, the handler may never be called for an under-privileged token.

### 18.3. Assuming `insufficient_scope` Only Appears When OAuth `scope` Is Wrong

With a valid Bearer authentication, the default handler may return `insufficient_scope` for an **AccessDeniedException** caused by roles, permissions, or other policies. It is a general protocol header, not a complete explanation of the business reason.

### 18.4. Assuming 403 Automatically Contains JSON

`BearerTokenAccessDeniedHandler` primarily manages status and `WWW-Authenticate`. Application-standard JSON bodies require explicit configuration; do not assume the default handler generates a fixed schema.

### 18.5. Replacing the Handler with Code That Only Calls `sendError(403)`

This can lose the Bearer challenge or cause the servlet container to render an HTML body violating the API contract. If a custom body is needed, delegate to the standard handler and append safe JSON.

### 18.6. Changing the Principal Name to Fix Scope Errors

`Authentication.getName()` is the principal name (usually from `sub` in JWTs). Changing it to email/username **does not create the `SCOPE_orders.cancel` authority**. Missing permissions must be fixed in token scopes, claim converters, policies, or the AS/API contract—not by renaming the principal.

### 18.7. Forgetting the `SCOPE_` or `ROLE_` Prefix

A token with `scope = orders.cancel` does not mean `hasAuthority("orders.cancel")` will match. With the default converter, rules normally must look for `SCOPE_orders.cancel`. Similarly, `hasRole("ORDER_SUPPORT")` normally matches `ROLE_ORDER_SUPPORT`.

### 18.8. Returning 401 Instead of 403 to Force Clients to Refresh Tokens

Refreshing a token does not automatically grant new permissions and can trigger a 401/refresh loop. If the caller is authenticated yet lacks permission, returning 403 fits the contract properly.

### 18.9. Skipping Tenant/Owner Checks Because the Scope Is Present

`SCOPE_orders.read` may only permit read-type operations. It does not grant access to **every order**. Even a properly configured access denied handler cannot prevent IDOR/BOLA without data-level policies.

### 18.10. Registering the Handler on the Wrong Chain

A Bearer handler in the `/api/**` chain does not protect `/admin/**` or `/internal/**` if no other chain covers them. Verify `securityMatcher`, `@Order`, and fallback policies.

### 18.11. Testing with `jwt()` and Assuming JWT Signatures Are Verified

Spring Security Test's `jwt()` mocks authentication; you must send genuinely signed Bearer JWTs through `JwtDecoder` to test signature/issuer/audience/expiration.

### 18.12. Widening Scopes Excessively to Avoid 403

If an endpoint returns 403, never switch all of `/api/**` to `permitAll()` or `authenticated()`. Determine whether the token genuinely lacks the authority, the claim converter is wrong, or the endpoint needs a different scope. **Resolving permission errors must never violate least privilege**.

## 19. Implementation and Testing Checklist

| Item | What to Verify |
| --- | --- |
| JWT / introspection | Token is verified before creating Authentication |
| Audience/issuer | Token is genuinely intended for this Resource Server |
| Scope mapping | `scope`/`scp` claim maps to the right authorities |
| HTTP matchers | Rules use appropriate method + URL |
| Default | Unpermitted requests are denied |
| Bearer 401 | Missing/invalid tokens use the right entry point |
| Bearer 403 | Valid authentication lacking permissions uses the access denied handler |
| Header | `WWW-Authenticate` includes Bearer challenge and `insufficient_scope` when appropriate |
| Realm | `realm` reflects the protection label, not used in place of audience |
| JSON body | If customized, preserves headers/status and leaks no internal policy |
| Method security | `@PreAuthorize` is enabled and enforced through appropriate proxies |
| Data policy | Owner/tenant/assignment are still verified |
| Side effects | Denied requests never update the DB or emit events |
| Multiple chains | API/web/fallback chains are selected accurately |
| Client behavior | 401 and 403 are handled differently, without infinite retries/refreshes |
| Logging | Never logs raw Bearer tokens, client secrets, or sensitive JWTs |

## 20. Scenario Exercises

**Scenario A — No token:** A Client calls `GET /api/orders/42` without an Authorization header. Should the API return `403 insufficient_scope`?

**No.** This case requires authentication and usually returns a **401 Bearer challenge** via the entry point, not insufficient permissions on an already valid authentication.

**Scenario B — Read-only scope token:** A Client holds a valid JWT with `orders.read` and calls `POST /api/orders/42/cancel`. How should the handler respond?

The rule lacks `SCOPE_orders.cancel` so it must **deny**, typically returning **403 Forbidden** with `WWW-Authenticate: Bearer error="insufficient_scope"` if the handler recognizes a valid Bearer authentication.

**Scenario C — Sufficient scope, wrong tenant:** Caller has `orders.read` but tries to view another tenant's order. The handler emits `insufficient_scope`. Can we conclude the caller lacks an OAuth scope?

**Not necessarily.** Access denied can originate from a **resource policy** rather than scope. Check logs/policies and design messages that do not leak another tenant's data.

**Scenario D — `jwt()` test passes:** A MockMvc test constructs a `JwtAuthenticationToken` with `SCOPE_orders.cancel` and receives 200. Can we conclude JWT signing and JWKS are working?

**No.** `jwt()` mocks authentication. A separate test must send a signed Bearer JWT through the real decoder.

**Scenario E — API returns 403 JSON without `WWW-Authenticate`:** The framework might still be working, so what should be checked?

Check whether a **custom `AccessDeniedHandler`** or gateway stripped the Bearer challenge required by the contract/RFC. If Clients need the header, delegate to `BearerTokenAccessDeniedHandler` when customizing JSON.

**Scenario F — Valid token lacking `SCOPE_orders.write`:** The dev team changes `hasAuthority("SCOPE_orders.write")` to `authenticated()` so the request returns 200. Is this the right fix?

**No.** They opened permissions to every authenticated caller. Inspect the actual grant, scope mapping, policy, and business requirements instead.

**Scenario G — `WWW-Authenticate` header is present, yet browser JS cannot read it:** Did the handler fail to send the header?

**Not necessarily.** In cross-origin requests, CORS may not expose the header to JavaScript. Inspect the raw network response and configure `Access-Control-Expose-Headers` per policy.

**Scenario H — Active opaque token with wrong audience:** Should the API let the denied handler decide whether to accept the token?

**No.** Audience/resource binding is part of **contract-level token validation** before authorization. If wrong, the token must be rejected before scopes are ever evaluated.

**Scenario I — Order-cancellation request returns 403, yet the DB already updated the status:** Does the negative test pass?

**No.** Authorization ran too late or side effects happened before denial. Fix the execution flow so no data changes occur when permissions are missing.

---

## Conclusion

**`BearerTokenAccessDeniedHandler`** is the specialized component for responding to **access denial** in Spring Security OAuth2 Resource Server. When a request has valid Bearer authentication yet fails a `hasAuthority`, `hasRole`, or other permission policy, the handler can produce **HTTP 403 Forbidden** with **`WWW-Authenticate: Bearer ... error="insufficient_scope"`** per RFC 6750. It differs from **`BearerTokenAuthenticationEntryPoint`** on the authentication-error path, which typically returns **401** for missing or invalid credentials.

To implement it properly, **configure permissions by method/path**, enforce issuer/audience/token validation, place Bearer handlers on the right `SecurityFilterChain`, and **preserve `WWW-Authenticate` when customizing JSON responses**. Test **401 missing token**, **403 valid token lacking permissions**, **allowed paths**, **owner/tenant checks**, and **absence of side effects on denial**. The handler formats insufficient-permission responses; **it does not replace token verification, scope mapping, or the application's authorization policies**.
