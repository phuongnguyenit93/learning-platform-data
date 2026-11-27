# Opaque tokens and verification through introspection

When protecting APIs with **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, many developers start with JWT access tokens: the API receives a dot-separated string, fetches public keys from JWKS, and verifies the signature and claims. However, **OAuth 2.0 does not require an access token to be a JWT**. An Authorization Server can issue an **opaque access token**: a string that the Resource Server should not parse on its own to determine the caller, expiration, or permissions.

For this token type, a common mechanism is **OAuth 2.0 Token Introspection (RFC 7662)**. The Resource Server sends the token to a trusted endpoint on the Authorization Server to ask **whether the token is active, who it was issued to, which Client it belongs to, and what scopes it carries**. Only after obtaining a trusted introspection result does the Resource Server create an `Authentication` and enforce authorization.

A simple example:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer Y6f9HkA7Pz9rKx...opaque...
~~~

The Orders API **should not** attempt to split this string into header/payload/signature, Base64URL-decode it, or guess permissions from the token's shape. It queries the Authorization Server via the introspection endpoint, and then applies **the Orders API's own** security policy.

> **Core rule:** An **opaque token is a Bearer credential**, not a self-proving identity or permission set. `active: true` is a status check result from the Authorization Server; it **does not replace** checks for audience/resource, scope, tenant, data-level permissions, and the API's token contract. When a token cannot be verified, you must **fail closed**.

## 1. What is an opaque access token?

An opaque access token is considered to have **no meaningful structure for the Client or Resource Server to trust and decode on their own**. It may look like a random string:

~~~text
4Q0D6WnJ8z...qk93
~~~

or have another format decided by the issuer. That content may be a reference to server-side state at the Authorization Server, an encrypted/proprietary value, or even a structured string that the Resource Server still **chooses to verify through introspection**. Thus, "opaque" describes **the usage contract**: the recipient does not derive identity or permissions directly from the token itself.

### 1.1. Comparing opaque tokens and signed JWT access tokens

| Criterion | Opaque access token | Signed JWT access token |
| --- | --- | --- |
| Format | String not self-interpreted by the Resource Server | Compact JWS typically with three parts `header.payload.signature` |
| Source of state information | Introspection response or verification mechanism defined by the AS | Claims inside the JWT after signature verification |
| Typical validation method | Call the AS introspection endpoint | Verify JWS using trusted keys, validate claims |
| Dependency on AS connectivity during verification | Usually **yes**, if introspecting per request/token | Not necessarily, once the appropriate public key is available |
| Token revocation | The AS can reflect current status at introspection time | Signed JWTs are typically accepted until expiration without an additional revocation mechanism |
| Permission freshness | Can reflect more up-to-date AS data, depending on the contract and how the AS computes permissions | Claims are usually fixed at token issuance time |
| Latency | Adds a network hop, unless appropriately cached | Usually mostly CPU/memory once keys are available |
| Bearer credential security | Must be kept secret, sent over HTTPS, never logged in full | **Same**, even though the JWT payload is readable |

**It is not true that opaque is always "more secure than JWT" or that JWT is always "faster than opaque" in every system.** The choice depends on revocation requirements, availability, dynamic permission data, request volume, operations, and deployment architecture.

### 1.2. The token is still a Bearer token

OAuth 2.0 Bearer Token Usage (RFC 6750) specifies how a caller presents an access token, typically via the header:

~~~http
Authorization: Bearer <access-token>
~~~

**Anyone holding a valid Bearer token can attempt to use it.** Therefore, an opaque token does not automatically protect against copying: the Client and API still need HTTPS/TLS, must keep tokens out of URLs/logs, protect token storage, and apply minimal lifetimes and scopes. If cryptographic proof-of-possession binding to the holder is needed, that requires a separate token-binding design such as DPoP or mutual TLS—it does not come automatically with opaque tokens.

## 2. Parties in the introspection flow

In the Orders API example:

- **Shop Web or a service Client** obtains an access token via a valid grant.
- **Identity Server** is the Authorization Server, storing/knowing token state and providing the introspection endpoint.
- **Orders API** is the Resource Server receiving the Bearer token, and also holds its own credentials to call introspection.
- **Order database/policy** determines actual permissions on each order.

~~~mermaid
sequenceDiagram
    actor U as User
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant R as Orders API
    participant DB as Order policy / database

    U->>C: Request to view order
    C->>AS: Request access token via OAuth2 grant
    AS-->>C: Opaque access token
    C->>R: GET /api/orders/42 + Bearer token
    R->>AS: POST /introspect (token + API credential)
    AS-->>R: active, scope, sub, aud, client_id, exp...
    alt Token is active and matches API contract
        R->>R: Create Authentication/authorities
        R->>DB: Check scope, owner, tenant, status
        DB-->>R: Allow or deny
        R-->>C: Appropriate result
    else Token is not active or not accepted
        R-->>C: Reject protected request
    end
~~~

The introspection response must arrive over an **authenticated, trusted connection** to the right Authorization Server. It is not JSON that the caller can submit in place of introspection. The caller may only send the **Bearer token**, and must never self-declare `active`, `scope`, or `sub` via another header for the Resource Server to blindly trust.

## 3. OAuth 2.0 Token Introspection under RFC 7662

The **introspection endpoint** is the interface for a Resource Server or authorized party to query the Authorization Server about a token's status and metadata. The endpoint is published by the Authorization Server or provided via integration documentation/metadata; **there is no single fixed path that applies to every issuer**.

Example path:

~~~text
https://identity.example.test/realms/shop/protocol/openid-connect/token/introspect
~~~

This is an illustrative URL following one product's convention; the application must use the **actual endpoint** of its issuer, rather than constructing a path and assuming it is always right.

### 3.1. Introspection request

According to RFC 7662, the Resource Server sends an **HTTP POST** with an `application/x-www-form-urlencoded` body containing the required `token` parameter and optionally `token_type_hint`:

~~~http
POST /introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <resource-server-credential>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=4Q0D6WnJ8z...qk93&token_type_hint=access_token
~~~

Notes:

- `token` in the body is the **access token the Client presented to the Orders API**.
- The credential in the `Authorization: Basic ...` header is the **Resource Server's credential when calling the AS** (if the issuer chooses that authentication method), not the user's credential.
- `token_type_hint=access_token` is a **hint**, not proof of a valid token; the Authorization Server processes it according to its protocol.
- Spring Security typically provides a mechanism to configure Client ID/secret for calling introspection; if the issuer requires mutual TLS, `private_key_jwt`, or another mechanism, the HTTP client/authentication must be configured accordingly.
- Both the token and the introspection credential are sensitive; the dot-separated placeholders here **are not real credentials**.

To understand the protocol in a test environment, you can write a cURL example:

~~~bash
# Request illustration only. Use test environment credentials/test token.
curl --request POST \
  --url "https://identity.example.test/introspect" \
  --user "orders-api-introspection:<test-secret>" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=<test-access-token>" \
  --data-urlencode "token_type_hint=access_token"
~~~

**Never run commands with production tokens/secrets in a way that leaves them in shell history, process lists, or logs.** In real environments, secrets should be provisioned via a secret manager and secure invocation practices. cURL is a protocol illustration, not an operational guide for production credentials.

### 3.2. Active token

An HTTP-level successful response might look like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read orders.cancel",
  "client_id": "shop-web",
  "sub": "user-842",
  "username": "linh.nguyen",
  "token_type": "Bearer",
  "iss": "https://identity.example.test/realms/shop",
  "aud": ["orders-api"],
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900
}
~~~

Attributes other than `active` are examples. RFC 7662 defines common metadata names such as `scope`, `client_id`, `username`, `token_type`, `exp`, `iat`, `nbf`, `sub`, `aud`, `iss`, and `jti`. **Authorization Servers may return different sets of attributes**, or add custom claims; the API needs a clear contract specifying which attributes are required for security decisions.

**`active: true` does not mean the token has all permissions.** The Resource Server must still confirm:

1. The response came from the trusted introspection endpoint that the API authenticated against.
2. The token was issued for this API under the agreed audience/resource binding.
3. The required scope/permissions for the endpoint are actually present.
4. The subject/Client/tenant complies with policy.
5. Record-level permissions are checked at the business layer.

### 3.3. Inactive token

A token that does not exist, has expired, has been revoked, or is no longer active under AS policy may yield:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
~~~

This is a **successful introspection call where the token is not accepted**, not an authentication failure of the Resource Server against the introspection endpoint. RFC 7662 requires that the response for an inactive token **must not disclose additional metadata** beyond `active` in the normal case.

The Resource Server must not read `scope` from a caller-supplied token and ignore `active: false`. For an endpoint protected by Bearer authentication, an inactive token typically results in **401 Unauthorized** from the Orders API.

### 3.4. Various HTTP scenarios

| Response when Orders API calls AS | Typical meaning | How Orders API should handle it |
| --- | --- | --- |
| `200`, `active: true` | Token is active according to AS | Still must check the token contract and policy |
| `200`, `active: false` | Token is not accepted | Do not create a valid authentication |
| `401 Unauthorized` from introspection endpoint | Resource Server credential sent to AS is wrong/not accepted | This is an introspection integration/credential error; **never** treat the token as active |
| `403 Forbidden` from introspection endpoint | Resource Server is not allowed to introspect under AS policy | Check client/endpoint permissions, reject the protected request |
| `400 Bad Request` from AS | Malformed introspection request syntax or parameters | Fix integration, do not let the token through |
| `429`/`5xx`/timeout | Rate limit, AS or network outage | Fail closed; apply timeout/retry/backoff by design |
| Malformed JSON or missing `active` | No valid response per contract | Do not treat the token as authenticated |

**Do not hardcode a single HTTP status from the Orders API for every AS error.** Depending on exception handling/framework behavior, a network error may manifest differently from an inactive token error. What matters for security is **never executing a protected operation without a trusted authentication result**.

## 4. Introspection verifies token status, not token issuance

OAuth2 has several different endpoints:

| Endpoint | Who calls it? | Purpose |
| --- | --- | --- |
| **Authorization endpoint** | OAuth2 Client, browser | Start authorization code/consent flow |
| **Token endpoint** | OAuth2 Client | Exchange code/refresh token/client credentials for tokens |
| **Introspection endpoint** | Resource Server or authorized party | Query status and metadata of an issued token |
| **Revocation endpoint** | Client or authorized subject per policy | Request token revocation |
| **JWKS endpoint** | Party needing to verify JWT signatures | Fetch public keys |

**Introspection is not token revocation.** Calling introspection does not invalidate a token. **Revocation** is a separate mechanism/request, and whether the AS reflects revocation in `active` depends on its implementation.

**JWKS is not directly used to verify opaque tokens.** Public keys verify JWT signatures; opaque tokens do not have a JWS contract for the Resource Server to verify locally. A Resource Server may use introspection even for tokens shaped like JWTs if that is the system's design, but the two mechanisms should not be mixed accidentally.

## 5. Configuring a Spring Boot Resource Server to accept opaque tokens

The example uses **Spring Boot 3 / Spring Security 6** with a RESTful Orders API receiving access tokens via `Authorization: Bearer`.

### 5.1. Dependency

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Or with Maven, add `spring-boot-starter-oauth2-resource-server`. You do not need `oauth2Login()` just for an API to accept opaque access tokens; **Resource Server** and **OAuth2/OIDC Client** are two distinct roles.

### 5.2. application.yml with introspection

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

Example dev environment:

~~~text
OAUTH_INTROSPECTION_URI=https://id.dev.example.test/introspect
OAUTH_INTROSPECTION_CLIENT_ID=orders-api-introspection-dev
OAUTH_INTROSPECTION_CLIENT_SECRET=<secret-provisioned-by-deployment-system>
~~~

**Never commit real secrets** to `application.yml`, `application-prod.yml`, Dockerfile, README, or test fixtures. Secrets should be provisioned separately per dev/staging/production via a secret manager, CI/CD, or an appropriate secret storage mechanism. `OAUTH_INTROSPECTION_CLIENT_SECRET` is the **API's credential when calling the Authorization Server**; it is different from the access token that Shop Web sends to the API.

### 5.3. SecurityFilterChain for opaque tokens

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersOpaqueSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

In this configuration:

- `oauth2ResourceServer().opaqueToken()` tells Spring Security that **Bearer tokens must be introspected**, rather than using `JwtDecoder` to verify JWS.
- An introspector is created/configured from `introspection-uri`, `client-id`, and `client-secret`, unless the application provides an alternative bean/configuration.
- After successful introspection, Spring Security creates authentication/authorities from the trusted data and evaluates rules like `SCOPE_orders.read` or `SCOPE_orders.write`.
- `anyRequest().denyAll()` in the chain blocks API paths that have not been explicitly permitted.

The example assumes `/api/**` **authenticates solely via Bearer tokens** and does not use session cookies, so CSRF is disabled in the API chain and session management is stateless. If the application serves a web UI using cookies/sessions, appropriate CSRF/filter chain configuration must be used for that part. If `securityMatcher("/api/**")` does not cover paths outside the API, there must be **another chain or a deny-all fallback** so no endpoint is left unprotected.

### 5.4. Trying a request

The Client calls:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <opaque-token>
~~~

The Authorization Server returns introspection:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-842",
  "client_id": "shop-web",
  "aud": ["orders-api"]
}
~~~

Spring Security can map the `scope` value to the authority `SCOPE_orders.read` via its default introspection handling. When the API rule requires that authority, the request **can proceed** to the controller/service. However, it may still be denied if order 42 does not belong to an authorized user or tenant.

## 6. Inside Spring Security: from opaque token to Authentication

A conceptual processing pipeline:

~~~text
HTTP Authorization: Bearer opaque-token
  |
  v
BearerTokenAuthenticationFilter
  |
  v
OpaqueTokenAuthenticationProvider
  |
  v
OpaqueTokenIntrospector
  |
  +-- POST to trusted introspection endpoint
  +-- authenticate Resource Server with AS
  +-- parse active + token metadata
  |
  v
OAuth2AuthenticatedPrincipal + GrantedAuthorities
  |
  v
BearerTokenAuthentication
  |
  v
authorizeHttpRequests / method security
  |
  v
resource policy: owner, tenant, status...
~~~

Key classes:

| Component | Responsibility |
| --- | --- |
| `BearerTokenAuthenticationFilter` | Extracts the Bearer token from the request as configured |
| `OpaqueTokenAuthenticationProvider` | Uses the introspector to authenticate the token and build authentication |
| `OpaqueTokenIntrospector` | Interface for introspecting a token string, returning `OAuth2AuthenticatedPrincipal` |
| `OAuth2AuthenticatedPrincipal` | Principal holding attributes and authorities from the trusted result |
| `BearerTokenAuthentication` | Authentication for a Bearer token after successful introspection |
| `SecurityFilterChain` | Applies rules by URL/HTTP method/authority |
| Business service/policy | Checks permissions on the actual data |

With a JWT Resource Server, the principal inside `JwtAuthenticationToken` is usually a `Jwt` object; with an opaque token, **do not cast `@AuthenticationPrincipal Jwt`** or assume the token has a JWT claims set. Use `OAuth2AuthenticatedPrincipal` and the attributes provided by the introspector.

### 6.1. Reading subject and attributes in a controller

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class CallerController {

    @GetMapping("/whoami")
    CallerInfo whoAmI(
            Authentication authentication,
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        String subject = principal.getAttribute("sub");
        String clientId = principal.getAttribute("client_id");

        return new CallerInfo(
                authentication.getName(),
                subject,
                clientId);
    }

    record CallerInfo(String principalName, String subject, String clientId) {}
}
~~~

This is an illustrative endpoint. **Not every introspection response contains `sub` or `client_id`**, so a production design must define whether they are required, handle nulls explicitly, and avoid exposing sensitive data in diagnostic endpoints.

**`Authentication.getName()` is not automatically a username or internal user ID**: its meaning depends on the principal created by the introspector and the data returned by the AS. If the API needs a stable user identity across issuers/tenants, it should maintain a clear contract for `(iss, sub)` and map to an internal user rather than trusting only a display username string.

### 6.2. How scopes are converted into authorities

Suppose the AS returns:

~~~json
{
  "active": true,
  "scope": "orders.read orders.cancel",
  "sub": "user-842"
}
~~~

The Resource Server can receive authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

These prefixes are a Spring Security convention:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

which differs from:

~~~java
.hasAuthority("orders.read")
~~~

If the AS returns scopes in a different format/claim than the profile Spring supports by default, a **custom introspector or converter** is needed. Do not assume an arbitrary `roles` or `permissions` object will automatically turn into `ROLE_ADMIN` or `PERM_order:read:tenant`.

## 7. Distinguishing introspection credentials from Client credentials and Bearer tokens

There are three different kinds of credentials/information in the system:

| Value | Held by | Purpose | Is it secret? |
| --- | --- | --- | --- |
| **Bearer access token** | OAuth2 Client and temporarily received by Resource Server | Client presents credential to call API | **Has sensitive credential characteristics** |
| **Introspection client ID** | Resource Server, issued by AS | Identifies the party calling introspection | Usually not |
| **Introspection client secret** | Resource Server and AS | Resource Server authenticates to the introspection endpoint | **Yes** |
| **Shop Web's Client ID/secret** | Shop Web and AS | Shop Web requests tokens via an appropriate grant | Secret must be protected if confidential Client |
| **AS signing private key** | AS/signing system | Signs JWTs if AS issues JWT tokens | **Highly sensitive** |
| **Public JWK/JWKS** | JWT verifier | Verifies JWT signatures | Not a private secret |

Do not reuse Shop Web's `client-secret` as the credential for Orders API unless the AS separately registers/authorizes it for the Resource Server. Separate Client registrations and secrets by responsibility, grant least privilege for introspection, and rotate secrets independently.

**A question about privacy:** Not every Resource Server is authorized to inspect metadata for every token. The Authorization Server should restrict which Clients may introspect which tokens, returning only the data needed by contract. If an introspection client lacks permission, the response may be inactive or an error depending on issuer policy and standards; either way, the Resource Server must not use that token to grant access.

## 8. `active: true` still requires audience and token contract validation

A dangerous mistake:

~~~text
If active == true:
    authentication = authenticated
    allow calling every API
~~~

A token may be **active in the Authorization Server** yet issued for the **Billing API**, not the Orders API.

Example:

~~~json
{
  "active": true,
  "scope": "billing.read",
  "aud": ["billing-api"],
  "client_id": "billing-web",
  "sub": "user-842"
}
~~~

The Orders API must have a policy verifying that the token is intended for `orders-api`. If the introspection response does not include `aud`, an **equivalent binding agreed upon by the AS and API** must be established, such as the introspection endpoint scoping tokens by resource or returning another resource claim. **Never skip audience checking by default just because `active = true`.**

### 8.1. Checking attributes against the contract

| Attribute | Question | Notes |
| --- | --- | --- |
| `active` | Is the token still recognized by the AS? | Required for an introspection result |
| `aud` | Which API is the token intended for? | Can be a string or list; sometimes absent under another contract |
| `iss` | Who issued the token? | Not every AS returns this claim; the introspection source must still be bound |
| `scope` | What actions was the token granted? | Does not prove data-level permission |
| `sub` | Which subject does the token refer to? | Can be a user or service depending on grant/profile |
| `client_id` | OAuth2 Client that received the token | **Not the same as** the introspection Client credential |
| `token_type` | Token type, e.g., Bearer | Does not by itself prove the token is for this API |
| `exp`, `nbf`, `iat` | Validity and issuance timestamps | AS already evaluated `active`; policy may require further limits |
| `tenant_id`/custom claims | Organizational permission context | Must have clear definition/data type |

**An active response may not contain all of these fields.** Which conditions are mandatory must come from the API's security requirements and contract with the AS, not from an assumption that all introspection endpoints behave identically.

### 8.2. Writing an audience-checking wrapper

With Spring Security 6, you can customize `OpaqueTokenIntrospector` to validate metadata before an Authentication is accepted. The following illustration uses `NimbusOpaqueTokenIntrospector` as a delegate, with a constructor present in many Spring Security 6 releases; depending on your project version, you can use `SpringOpaqueTokenIntrospector`/the corresponding builder while keeping the **delegate then validate** pattern.

~~~java
import java.util.Collection;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
class OpaqueAudienceValidationConfig {

    @Bean
    OpaqueTokenIntrospector introspector(
            @Value("${spring.security.oauth2.resourceserver.opaque-token.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaque-token.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaque-token.client-secret}")
            String clientSecret,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        OpaqueTokenIntrospector delegate =
                new NimbusOpaqueTokenIntrospector(
                        uri, clientId, clientSecret);

        return token -> {
            // Delegate the introspection request and reject inactive tokens.
            OAuth2AuthenticatedPrincipal principal =
                    delegate.introspect(token);

            // Metadata came from the trusted introspection endpoint.
            Object rawAudience = principal.getAttribute("aud");
            if (!containsAudience(rawAudience, expectedAudience)) {
                throw new BadOpaqueTokenException(
                        "Token is not intended for this resource server");
            }
            return principal;
        };
    }

    private static boolean containsAudience(
            Object rawAudience, String expected) {

        if (rawAudience instanceof String value) {
            return expected.equals(value);
        }
        if (rawAudience instanceof Collection<?> values) {
            return values.contains(expected);
        }
        return false;
    }
}
~~~

When using the code above, add the property:

~~~yaml
app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

In this example, a token **without `aud`** is rejected. This is the **right choice for the Orders API contract assuming introspection returns an audience**. If a real Authorization Server does not return `aud` but guarantees resource binding through another mechanism, you must design/verify the alternative condition per the issuer's documentation rather than blindly accepting every active token.

A custom `OpaqueTokenIntrospector` bean replaces how auto-configuration selects the introspector in matching setups; therefore, the application must ensure this bean still authenticates requests to the introspection endpoint, handles `active`, enforces audience binding, and checks all required conditions. Never return a principal with elevated authorities just because the introspection endpoint is temporarily unreachable.

**Why not check only scope?** A token with the same `orders.read` scope issued for a different resource can still carry an identical scope name. Audience/resource binding helps prevent **token substitution** across APIs.

### 8.3. Adding issuer and token profile checks

If the AS provides `iss`, the API can compare it against the expected issuer per contract. If `iss` is absent, trust in the issuer can come from the **introspection endpoint and Resource Server credential**, plus AS rules limiting which tokens can be introspected. Do not assume an arbitrary `iss` string in an unauthenticated body has security value.

Similarly, in systems issuing both access tokens and other credential types, the API must ensure **introspection only creates authentication from tokens permitted as OAuth2 access tokens for the API**. Do not allow an OIDC ID token to substitute for an access token simply because it also carries user claims.

## 9. Customizing authorities from introspection metadata

Spring Security can map `scope` to `SCOPE_...` via the default introspection implementation. If the Identity Server returns additional roles or permissions, the Resource Server needs **an explicit mapping contract**, following the same principle as with JWTs, except the **data source is the introspected principal**, not `Jwt`.

For example, the AS returns:

~~~json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "support-12",
  "roles": ["order_support", "billing_admin"],
  "tenant_id": "tenant-A"
}
~~~

Under the Orders API contract, only the `order_support` role is mapped to `ROLE_ORDER_SUPPORT`; the `billing_admin` role is outside the Orders permission domain and is ignored.

An illustrative converter wrapper:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

final class OrdersRoleIntrospector implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    OrdersRoleIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(principal.getAuthorities());

        Object rawRoles = principal.getAttribute("roles");
        if (rawRoles instanceof Collection<?> roles
                && roles.contains("order_support")) {
            authorities.add(
                    new SimpleGrantedAuthority("ROLE_ORDER_SUPPORT"));
        }

        // Do not automatically grant authorities for roles outside the allowlist.
        return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                authorities);
    }
}
~~~

This wrapper **only illustrates mapping a single role**. In a real application, audience checking, issuer checking, token profile validation, and role mapping can be combined in **a single clearly configured introspector chain**. Do not register multiple competing `OpaqueTokenIntrospector` beans without specifying which one is used. Principal permission checks must rely on the authenticated introspection result, not JSON sent along by the requesting client.

**Roles do not replace resource policy:** `ROLE_ORDER_SUPPORT` only represents a role. The service must still verify whether the support agent is allowed to view order 42 in tenant A or belonging to their team.

## 10. Controlling user identities and service principals

Opaque tokens may be issued under:

- **Authorization Code**: typically represents access tied to a user, a Client, and consent/policy.
- **Client Credentials**: typically represents a **Client/service**, without necessarily involving an end user.
- **Other supported grants or mechanisms**: metadata and how `sub` is interpreted depend on the AS design.

Example introspection for a Client Credentials token:

~~~json
{
  "active": true,
  "client_id": "nightly-sync",
  "sub": "nightly-sync",
  "scope": "orders.sync",
  "aud": ["orders-api"]
}
~~~

Do not treat `sub = nightly-sync` as if it were the customer ID owning an order. The API can enforce policies such as:

~~~text
User endpoint:
  requires user context + orders.read + resource ownership

Service sync endpoint:
  requires allowed client identity + orders.sync
  + additional service-level policy
~~~

If the API accepts tokens from multiple issuers or tenants, the same `sub` does not necessarily represent the same subject. For user identity, the pair **`(iss, sub)`** is often useful as a key linking to an internal user, provided the introspection contract guarantees both attributes. If only `username` is returned, a dedicated identification strategy is required; **username/email are not inherently stable or globally unique keys**.

## 11. HTTP authorization and data-level permissions

An example endpoint:

~~~text
GET /api/orders/42
~~~

should only be permitted when:

1. The caller sends a Bearer opaque token.
2. Introspection succeeds against a trusted AS and the token has `active = true`.
3. The token is intended for the Orders API per the audience/resource contract.
4. The token carries the `SCOPE_orders.read` authority.
5. Order 42 falls within the caller's tenant/owner/permission scope.

The condition in step 5 cannot be inferred from `scope` alone. Someone with `orders.read` is not automatically allowed to view everyone else's orders.

### 11.1. Using method security for resource policy

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrdersQueryService {

    private final OrdersRepository orders;

    OrdersQueryService(OrdersRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') and " +
        "@orderAccess.canRead(authentication, #orderId)")
    public OrderDto readOrder(String orderId) {
        return orders.findVisibleDtoById(orderId)
                .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

`OrdersRepository`, `OrderDto`, `OrderNotFoundException`, and the `orderAccess` bean are illustrative business components, not built-in Spring classes. For `@PreAuthorize` to work, the application must enable `@EnableMethodSecurity` and invoke the method through the appropriate Spring security proxy.

The `orderAccess` bean must extract identity/tenant from the introspected `Authentication` and check against records in the database/policy service. Never allow the Client to send `X-Tenant-Id` or `ownerId` and use it directly as proof of authorization.

### 11.2. Introspection does not make permissions permanent

A response containing `roles`/`scope` reflects data **at the moment the AS generated the response**. If the system caches results, permission updates can be delayed. It is also possible for the AS to fix scopes at token issuance time, even when introspection is online. Therefore, when dynamic permissions and rapid revocation are required, you must understand **how the AS actually computes `active` and metadata**, rather than assuming introspection automatically applies every permission change instantaneously.

## 12. Impact on latency, availability, and scale

A request to the Orders API may trigger **an HTTP request to the AS**. At high traffic, this affects:

- **Latency:** overall API response time includes network/introspection latency.
- **Throughput:** the AS must serve a high volume of introspection requests.
- **Availability:** if the AS/introspection endpoint goes down, the API may be unable to authenticate tokens.
- **Connection resources:** connection pools, DNS, TLS, timeouts, and API threads carry load.
- **Rate limiting:** the AS may throttle introspection calls or apply quota policies.

### 12.1. When the AS is temporarily down

With signed JWTs, a Resource Server that already holds the appropriate public key **can** verify tokens locally when the AS is down, provided the token has not expired and satisfies other conditions.

With opaque tokens:

~~~text
Bearer opaque token
        |
        v
Need trusted introspection response?
        |
    Yes, but AS unavailable
        |
        v
Cannot establish valid Authentication
        |
        v
Do not perform protected operation
~~~

If the Resource Server uses **online introspection per token** and the endpoint does not respond, the API cannot know on its own whether the token is active or revoked. The right behavior is to **reject or return a dependency error** per configuration while **never executing the protected action**.

Never write:

~~~java
// SECURITY FLAW: Must not be used as a fallback.
try {
    return introspect(token);
} catch (Exception unavailable) {
    return adminPrincipalForEveryone();
}
~~~

Or:

~~~text
If AS is down -> treat every token as active.
If introspection times out -> read a few characters of the token as userId.
If introspection secret is wrong -> disable authentication for /api/**.
~~~

These approaches turn an availability outage into **fail-open authentication**.

### 12.2. Timeouts, retries, and protecting the AS

Operational settings to configure per library and environment:

1. Finite **connection timeout** and **response timeout**.
2. **Bounded retries**, suited to transient error statuses and the API's latency budget.
3. Backoff/jitter when the AS returns 429/5xx to avoid retry storms.
4. Circuit breaker or bulkhead when needed to limit impact on thread/connection pools.
5. Metrics: introspection latency, active/inactive counts, client authentication errors, timeouts, 5xx, rate limits.
6. Distinguish **inactive tokens** from **introspection dependency down** in internal logs/alerts.

Do not turn every connection error into `active: false` and hide operational incidents; nor use that distinction to **let requests through**. The HTTP status returned to the Client can be tailored by policy/exception handler, but the security invariant is that no fake authenticated principal is created when the AS cannot verify the token.

### 12.3. Caching introspection results: a deliberate trade-off

Caching can reduce latency and request volume to the AS:

~~~text
token T -> introspection active + metadata
        -> cache briefly, per policy
        -> subsequent requests reuse the valid cached result
~~~

However, caching can extend the window during which the API continues trusting a token **after the token has been revoked, permissions have changed, or the user has been locked**.

If caching is applied, you must define:

- **Maximum TTL** based on risk level and the token's `exp` if provided by the AS; never cache past the token's valid lifetime.
- Separate rules for storing **positive** and **negative** (inactive) results, if applicable.
- **Invalidation** capability when a token/credential is known to be revoked.
- How cache keys are protected (tokens are secrets; consider hashing/HMAC and access control).
- Whether cached active results may be used when the AS is down, **strictly within the policy-approved window**.
- When the cache expires and the AS is still down, requests must fail safely.

**Never use unbounded caching** and never extend TTL automatically when the AS is down. If near-instant revocation is required, caching must be strictly limited or paired with active invalidation.

### 12.4. Availability of the AS and different APIs

Introspection gives the Resource Server status visibility from the AS, at the cost of an added dependency. Systems requiring very high availability may need to evaluate:

- Does the AS have sufficient replicas/regions and an SLA for the introspection endpoint?
- Does the API need graceful degradation **only for public/unauthenticated features** when the AS is down?
- Is there an approved caching mechanism?
- Should short-lived JWT access tokens with local verification be used for certain APIs?
- When the AS recovers, can the API recover automatically without rolling restarts?

Do not choose a mechanism solely because "opaque is more secure" while ignoring latency and availability; nor use JWT solely to avoid all revocation concerns. Decide based on business risk and operational capability.

## 13. Designing introspection tests for both allowed and rejected cases

The test suite should be split into **HTTP authorization**, **introspection client/protocol**, and **data policy**.

### 13.1. Matrix of tokens and introspection responses

| Scenario | AS introspection | Result at Resource Server |
| --- | --- | --- |
| Valid token for Orders API | `active: true`, `aud = orders-api`, `scope = orders.read` | Can authenticate; read endpoint passes HTTP rule |
| Non-existent token | `active: false` | Authentication rejected |
| Revoked token | `active: false` | Authentication rejected |
| Expired token | `active: false` (per AS) | Authentication rejected |
| Active token with Billing API audience | `active: true`, `aud = billing-api` | Rejected by audience contract |
| Active token with right audience but missing `orders.read` | `active: true`, `scope = profile` | Authentication may succeed; HTTP authorization 403 |
| Active token with right audience/scope but wrong tenant | `active: true` | Rejected by data policy |
| Resource Server uses wrong introspection secret | AS returns 401 | Resource Server authentication error with AS, no access granted |
| Introspection endpoint returns 503 or times out | No trusted result | Fail closed, protected business logic does not run |
| Introspection returns malformed JSON | Invalid response | Valid Authentication is not created |
| Token metadata missing required audience | `active: true` but missing `aud` | Rejected by validator if contract requires audience |

When testing, verify that **controllers/services produce no side effects** in every rejected case; do not check only an HTTP status code.

### 13.2. Mocking the introspector for HTTP authorization tests

If you only want to test `hasAuthority` and `SecurityFilterChain`, you can build a fake `OpaqueTokenIntrospector` without running a real AS. Example with JUnit Jupiter/MockMvc and Spring Security test:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@TestConfiguration
class FakeOpaqueIntrospection {

    @Bean
    OpaqueTokenIntrospector introspector() {
        return token -> {
            if ("active-read".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                        "user-842",
                        Map.of(
                                "sub", "user-842",
                                "aud", List.of("orders-api"),
                                "scope", "orders.read"),
                        List.of(
                            new SimpleGrantedAuthority(
                                    "SCOPE_orders.read")));
            }
            if ("active-write".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                        "user-842",
                        Map.of(
                                "sub", "user-842",
                                "aud", List.of("orders-api"),
                                "scope", "orders.write"),
                        List.of(
                            new SimpleGrantedAuthority(
                                    "SCOPE_orders.write")));
            }
            throw new BadOpaqueTokenException("inactive or unknown token");
        };
    }
}
~~~

This is a **test fixture**, not a production introspector. It intentionally constructs principals from test strings like `active-read` and does not call an Authorization Server. Use it only to isolate HTTP/authority rules.

Example test requests:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// When MockMvc is configured with SecurityFilterChain and FakeOpaqueIntrospection:
mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer active-read"))
    .andExpect(status().isOk());

mockMvc.perform(post("/api/orders")
        .header("Authorization", "Bearer active-read"))
    .andExpect(status().isForbidden());

mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer inactive-token"))
    .andExpect(status().isUnauthorized());

mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isUnauthorized());
~~~

The snippet above is an **illustrative test body inside a test with `mockMvc` and a mock controller**, not a standalone complete test class. With real business policy, `GET /api/orders/42` can still be rejected after HTTP authorization if the owner/tenant does not match.

### 13.3. Integration tests with a mocked introspection endpoint

To prove that the protocol and credentials actually work, test at a higher level:

1. Run **MockWebServer** or **WireMock** as the test environment's introspection endpoint.
2. Configure the Spring Security Resource Server to point `introspection-uri` to the test HTTP server.
3. Send a real request to the API with `Authorization: Bearer <test-token>`.
4. Assert the request received by the AS: **POST**, `Content-Type: application/x-www-form-urlencoded`, the `token` parameter, and the agreed authentication mechanism.
5. Have the mock AS return `{"active":true,"scope":"orders.read","aud":["orders-api"]}` and verify authorities and rules.
6. Have the mock AS return `{"active":false}` and verify the API rejects it.
7. Have the mock AS return 401 for wrong credentials, 503, timeout, malformed JSON, and data missing audience; verify that **no protected request is executed**.

Always use **test credentials and test tokens**, never calling production introspection from unit/integration tests. If introspection responses vary in metadata across issuers, test against your system's exact schema and additional validation.

### 13.4. Testing client identity and token substitution

Beyond active/inactive, also test:

- A token issued by the AS for `billing-api` sent to the Orders API → rejected by audience validation.
- A `client_credentials` token for service A sent to a user-only endpoint → rejected by policy.
- Two Clients with different `client_id` values but the same scope → only the Client authorized in that business context may operate.
- A token from an untrusted issuer → rejected by the endpoint/issuer validation contract.
- A valid token missing secondary roles/permissions → 403 at authorization.

These cases ensure **`active = true` is not treated as an "all-access pass to every API"**.

## 14. Failure scenarios and HTTP codes at the Orders API

| Symptom seen by Client | Possible cause | What to check |
| --- | --- | --- |
| **401** when no token is sent | Endpoint requires authentication | Confirm Client is sending the Bearer header |
| **401** with a previously working token | Token expired, revoked, or AS returned inactive | Check introspection output in a safe test/diagnostics environment |
| **401** even though token is active | Wrong audience/resource, missing required claim, or custom token policy | Check introspection contract and validator |
| **403** with an active token | Missing `SCOPE_orders.read` or another authority | Check `scope` from AS and Spring Security rules |
| **403/404** when viewing a record | Wrong owner/tenant/assignment or resource does not exist | Check data-level policy |
| **5xx** or continuous auth failures when AS is down | Timeout, TLS, DNS, HTTP errors from introspection endpoint | Inspect dependency logs, timeouts, connection pool, alerts |
| Failures after rotating client secret | Resource Server is still using the old secret | Check secret injection, rollout, AS registration |
| All tokens inactive in one environment | Wrong introspection URI/tenant/realm or introspection Client permissions | Check issuer and environment contract |

**Actual HTTP status codes depend on the Spring Security version and exception handler**, especially for network/AS 5xx errors. Never mask AS errors by converting them to success or granting default authorities. From a security standpoint, a request must never perform an operation if the token cannot be verified.

### 14.1. Logging, tracing, and sensitive data

You may log:

- Request ID, endpoint, timestamp, HTTP status.
- Environment name and **configured** introspection endpoint.
- Failure category: inactive, invalid audience, insufficient scope, upstream timeout, client authentication error.
- Introspection round-trip duration, retry count, cache status.
- Subject/client ID **only after receipt from a trusted source**, in accordance with audit and privacy rules.

**Never log raw Bearer tokens or introspection client secrets** in access logs, HTTP client logs, trace spans, exceptions, URL query strings, or metric labels. If tracing correlation for a token is needed, use an opaque/HMAC identifier dedicated to observability per policy, never storing plaintext tokens.

## 15. How does OIDC relate to opaque access tokens?

**OpenID Connect (OIDC)** is an identity layer built on OAuth 2.0, featuring an **ID token** so the OIDC Client knows the authentication outcome. An ID token is usually a JWT per OIDC, while **the access token a Client receives does not have to be a JWT**.

A system might work like this:

~~~text
Shop Web:
  receives JWT ID token -> used to handle OIDC sign-in
  receives opaque access token -> used to call Orders API

Orders API:
  receives opaque access token
  uses introspection to authenticate and obtain scope/metadata
  does not accept ID token in place of access token
~~~

This setup is completely valid. Not seeing `sub` by decoding the access token **does not mean** the user failed to sign in with OIDC; it is simply the separation between identity delivery to the Client and authorization for the API.

### 15.1. An ID token does not replace an access token

An ID token is primarily intended for the **OIDC Client** (its audience is typically the Client ID). The Orders API requires an access token with the proper audience/resource and scope. When AS introspection accepts a given string, the system must still ensure it is a **credential permitted as an API access token** under the contract, not merely any token still active at the issuer.

### 15.2. OAuth2 Client and Resource Server have separate configurations

Shop Web may need:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          shop-login:
            provider: shop-id
            client-id: ${SHOP_WEB_CLIENT_ID}
            client-secret: ${SHOP_WEB_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          shop-id:
            issuer-uri: ${SHOP_IDP_ISSUER_URI}
~~~

This is **Client** configuration, completely distinct from the Orders API's `spring.security.oauth2.resourceserver.opaque-token.*`. In this example Shop Web is a confidential Client; public Clients require a different model (such as PKCE, without embedding a client secret in browser/mobile code).

Do not copy Shop Web's Client secret into the Orders API for introspection. Each role uses its own appropriate registration and credentials.

## 16. Common misconceptions

**"An opaque token must be an unstructured random string."** Not necessarily. The core point is that the Resource Server must not interpret the token itself; it relies on introspection or a contracted verification mechanism.

**"Because you cannot read the payload, an opaque token cannot have scopes."** False. The AS can return `scope`, `sub`, `aud`, `client_id`, and plenty of other metadata via introspection.

**"`active = true` means any API may accept it."** False. Each API must enforce resource/audience binding along with its own scopes and policies.

**"The introspection endpoint is the same as the token endpoint."** No. The token endpoint issues tokens; the introspection endpoint queries the status of an already-issued token.

**"Calling introspection revokes the token."** No. Revocation is a separate operation.

**"A Resource Server accepting opaque tokens needs the AS's private key."** No. Standard introspection requires the endpoint and an authorized credential; the private signing key stays on the AS.

**"The introspection client ID is the OAuth2 Client ID recorded inside the token."** Not by default. One ID identifies **the party calling introspection**; the `client_id` in the response typically describes **the party the token was issued to**.

**"Use `JwtDecoder` to handle opaque tokens by splitting on dots."** Wrong mechanism. Use `OpaqueTokenIntrospector` or a verification method supported by the AS.

**"Online introspection always reflects every permission change immediately."** Not guaranteed. You must understand how the AS stores and computes `scope`/roles/permissions; caching on the Resource Server can also delay updates.

**"If the AS is down, just allow previously seen tokens."** Not by default. If caching is used, behavior must stay within the designed TTL and policy. Without valid trusted evidence, fail closed.

**"JSON sent directly by the Client can also be used as introspection."** No. Only responses from the trusted AS endpoint, over the proper authenticated protocol/channel, may establish an Authentication.

**"Once introspection returns active, there is no need to check owner/tenant."** False. Record-level authorization remains the Resource Server's responsibility.

## 17. Practical integration workflow

### Step 1 — Agree on the token contract

The Identity team and Orders API team should document:

~~~yaml
# Illustrative contract, not a configuration automatically read by Spring.
resource_server: orders-api
access_token_format: opaque
trusted_authorization_server: https://identity.example.test
introspection_endpoint: https://identity.example.test/introspect
introspection_client: orders-api-introspection
introspection_auth_method: client_secret_basic
expected_audience: orders-api
required_response_attributes:
  - active
  - aud
  - scope
  - sub
authorization:
  GET /api/orders/{id}:
    scope: orders.read
    data_policy: owner_or_assigned_support
  POST /api/orders:
    scope: orders.write
    data_policy: tenant_can_create_order
inactive_token: reject
upstream_unavailable: fail_closed
~~~

If the AS does not return `sub` for Client Credentials, or does not provide `aud`, define a separate contract for that token type rather than forcing every token to carry a user subject. Required fields must match how the issuer actually behaves.

### Step 2 — Provision credentials and configure per environment

Dev/staging/production need:

- The exact introspection URI for the environment.
- An authorized introspection Client registration and **its own credential**.
- TLS trust, proxy/network policy requirements.
- Specific audience/resource and scope mappings.
- A client secret rotation mechanism and error observability.

Never hardcode secrets in source code. If secrets are distributed via environment variables, control access to process/config visibility, logs, and CI/CD.

### Step 3 — Configure the Resource Server and additional validation

Use `opaque-token` in Spring Security, not `jwt`, for tokens issued under an opaque contract. If the AS returns an audience, write a validator as in section 8 to reject tokens meant for other APIs. Map roles/permissions strictly from trusted introspection metadata.

### Step 4 — Test both allowed and rejected paths

Run test cases for active/inactive, wrong audience, missing scope, wrong owner/tenant, introspection 401, 503, timeout, and malformed responses. Ensure **no business operations occur on rejection**. For protocol tests, use a mock HTTP server to verify the actual POST/body/authentication rather than mocking only the principal.

### Step 5 — Measure latency and design for resilience

Measure P95/P99 introspection latency, connections, retries, AS load, and timeout rates. If caching is used, explicitly document TTL limits and invalidation triggers. Track the difference between normal inactive tokens and AS outages.

### Step 6 — Operations and rotation

Plan for rotating introspection client secrets, changing endpoints, updating active/scope policies, and AS recovery. Avoid rolling out many API replicas simultaneously while the AS is unavailable if they depend directly on introspection. Never alter configuration to **disable authentication** just to work around an outage.

## 18. Scenario exercises

**Scenario A:** The Orders API receives an opaque token. A developer tries to Base64URL-decode the token, fails, and concludes the Client is not signed in. Is that conclusion right?

**No.** An opaque token has no local decoding contract. The Resource Server must use introspection as agreed to determine active status and metadata.

**Scenario B:** Introspection returns `{"active":true,"scope":"orders.read","aud":["billing-api"]}`. Should the Orders API allow `GET /api/orders/42`?

**No.** The token is not intended for the Orders API. It must be rejected by audience/resource binding even though it is active.

**Scenario C:** The token is active and the audience is right, but it lacks `orders.write`. The Client calls `POST /api/orders`. Which layer fails?

Authentication may succeed, but **HTTP authorization** must reject the request for lacking the required scope/authority, typically returning **403**.

**Scenario D:** The introspection endpoint returns `200 {"active":false}`. Should the API retry indefinitely because the HTTP status is 200?

**No.** `active: false` means the token is inactive, not a service error. The API rejects the token; retrying does not replace obtaining a new token.

**Scenario E:** The introspection endpoint returns `401` because the Orders API used an expired secret. Should every token be treated as user-invalid and trigger account deletion?

**No.** This is a Resource Server credential error against the AS. The API must still refuse tokens, but diagnostics and operations should pinpoint the integration issue rather than blaming the token subject.

**Scenario F:** The AS is down, and the API has a cached `active=true` entry for a token from several hours ago that has since been revoked. Should it keep accepting the token indefinitely to preserve availability?

**No.** Caching may only be used within an approved TTL/revocation policy; once expired or without a trusted basis, fail closed.

**Scenario G:** Shop Web signs in via OIDC with a JWT ID token and receives an opaque access token. Does the Orders API need a JWT decoder for the access token?

**Not under this contract.** The ID token serves the OIDC Client. The Orders API uses introspection for the opaque access token issued to call the API.

**Scenario H:** A unit test faking `OpaqueTokenIntrospector` returns a principal with `SCOPE_orders.read`, and the API returns 200. Can you conclude that the HTTP POST to the introspection endpoint and Basic auth actually work?

**Not yet.** A mocked test only proves HTTP authorization. You need an integration test against a mock introspection HTTP endpoint to verify the actual request, credentials, and response handling.

---

## Conclusion

**An opaque access token is not a JWT whose claims a Resource Server can read and trust on its own.** With Spring Security OAuth 2.0 Resource Server, the standard mechanism is **OAuth 2.0 Token Introspection**: `BearerTokenAuthenticationFilter` delegates the token to `OpaqueTokenAuthenticationProvider`/`OpaqueTokenIntrospector`, the Resource Server calls a trusted endpoint using dedicated credentials, evaluates `active` and metadata, and only then builds an `Authentication` with authorities such as `SCOPE_orders.read`.

To use it safely, keep three boundaries clear: **(1) an active token does not mean a token intended for this API; (2) scopes/roles do not replace record-level and tenant permissions; (3) network errors or failed introspection must never fail open**. A complete design requires an audience/resource contract, dedicated introspection secrets, positive/negative tests, observability, timeout handling, and a cache/revocation policy suited to business requirements.
