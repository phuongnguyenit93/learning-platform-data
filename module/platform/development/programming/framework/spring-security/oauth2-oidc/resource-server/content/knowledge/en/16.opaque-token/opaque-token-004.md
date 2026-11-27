# `introspection-uri`, `client-id`, `client-secret`, and Resource Server authentication

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, an API may receive access tokens that the API itself **cannot or does not need to decode and verify as signed JWTs**. Instead of validating tokens locally with public keys/JWKS, the Resource Server sends the token to the **Authorization Server** via a **token introspection** endpoint, receiving status information and permitted attributes to authenticate the request.

In Spring Boot, the three key configuration properties are:

- `introspection-uri`: URL of the **introspection endpoint** called by the Resource Server.
- `client-id`: identifier **of the Resource Server or a dedicated introspection client**, depending on registration at the Authorization Server.
- `client-secret`: secret proving the introspection client's identity when calling the endpoint; this is **not the user's access token**.

These three properties live under:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

The environment variables in this example are placeholders: **they must be supplied through a secret manager/deployment configuration**, never committed as real credentials to the repository.

**Lesson goal:** accurately understand the two authentication directions involved with opaque access tokens, distinguish the caller's identity from the Resource Server's credentials, configure Spring Security safely, read `active`/`scope` state, handle rejected tokens, and design behavior when the introspection endpoint experiences an outage.

> **Illustrative context:** OAuth Authorization Server at `https://login.example.com`, Orders API at `https://api.example.com`, published audience `orders-api` when provided, and scope `orders.read`. Java examples use Spring Boot 3.x and Spring Security 6.x on the Servlet stack. All URLs, client IDs, and tokens in this document are example values.

## 1. What is an opaque token, and why must the Resource Server introspect it?

An **opaque access token** is a token whose internal structure the Resource Server does not need to understand. It may simply be a random string:

```text
Authorization: Bearer K1cJ4H9vYp2Noa...REDACTED
```

The Resource Server cannot infer user, scope, audience, or expiration from this string on its own. It must query an authoritative source: the **Authorization Server**, which manages token issuance and state.

For instance, an opaque access token does not necessarily have three `header.payload.signature` segments like a JWT. Also note:

- **Opaque vs. JWT is how the Resource Server processes the token**, not purely a matter of string appearance. A token that looks like a JWT can still be sent to introspection by the Resource Server if the system is designed that way.
- In Spring Security, the `opaquetoken` configuration uses **`OpaqueTokenIntrospector`** rather than going through `JwtDecoder` as the `jwt` configuration does.
- If the Authorization Server returns `active=false`, the token must be rejected, even if the client insists the token has not expired.
- If the Authorization Server returns `active=true`, the API **must still verify** attributes and permissions per the resource contract, never assuming all actions are permitted.

### 1.1. What problem does token introspection solve?

With self-verifying JWTs, an API can check signatures and claims using trusted public JWKs without calling the AS on every request. With opaque tokens, the API typically relies on the introspection result to learn:

1. Is the token currently **active**?
2. Which **client** was the token issued to?
3. Which **subject** does the token represent, if any?
4. What scopes or authorities were granted?
5. Are there expiration/issuer/audience/tenant metadata fields to validate?
6. Is the token eligible to be used at the **Orders API**?

A revoked token can quickly yield `active=false` on subsequent introspection calls. However, how up-to-date that is depends on the Authorization Server, caching, replication, and revocation timing. **Do not assume introspection is always instantaneous in every architecture.**

### 1.2. Both are called "client", yet they are two different roles

In a typical flow there are **at least two client identities**:

| Role | Example | Where it is used |
|---|---|---|
| **OAuth application client** | `storefront-web` | Obtains access tokens from the Authorization Server and attaches them to API requests |
| **Introspection client / Resource Server credential** | `orders-api-introspector` | Orders API uses `client-id` and `client-secret` to authenticate **when calling the introspection endpoint** |

Some deployments allow those roles to share a client registration, yet **you should never assume they are always the same**. For least privilege and clean auditing, it is usually best to use separate credentials per Resource Server or resource group permitted to introspect matching tokens.

## 2. Two distinct authentication steps within a single request

There are two critical communication paths:

```mermaid
sequenceDiagram
    autonumber
    participant Caller as OAuth Client / API Caller
    participant RS as Orders API Resource Server
    participant AS as Authorization Server
    Caller->>RS: GET /api/orders/42; Authorization: Bearer ACCESS_TOKEN
    RS->>AS: POST /oauth2/introspect over HTTPS
    Note over RS,AS: Resource Server authenticates with client-id/client-secret
    Note over RS,AS: Body contains the token to inspect
    AS->>AS: Validate token and client's introspection permission
    AS-->>RS: active=true + attributes / active=false
    RS->>RS: Convert attributes into Authentication and authorities
    RS->>RS: Check scope, audience, tenant, object policy
    alt Token active and authorized
        RS-->>Caller: Return data or execute operation
    else Token inactive or unauthorized
        RS-->>Caller: Reject according to error type
    end
```

### 2.1. The caller authenticates to the Resource Server with a Bearer token

HTTP request from caller to API:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_FROM_AUTHORIZATION_SERVER
Accept: application/json
```

Key points:

- `ACCESS_TOKEN_FROM_AUTHORIZATION_SERVER` is the **request's bearer credential**.
- The client does not know and **must never know** the Resource Server's `client-secret`.
- The API must never treat `sub`, `roles`, or `tenant_id` supplied in request bodies/headers as authentication proof in place of introspection.
- The token is untrusted input until introspection and the API's validators/policies accept it.

### 2.2. The Resource Server authenticates to the Authorization Server

When introspecting a token, the Orders API makes an outbound request:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic BASE64_INTROSPECTION_CLIENT_ID_COLON_SECRET
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=ACCESS_TOKEN_FROM_CALLER&token_type_hint=access_token
```

This is a protocol illustration, **not containing real credentials**. When using HTTP Basic, the client ID/secret are Base64-encoded per HTTP Basic and OAuth rules; **Base64 does not secure the data**. The connection must use HTTPS and verify TLS certificates.

According to RFC 7662:

- `token` is the **required** parameter to introspect.
- `token_type_hint` is an **optional hint**; the Authorization Server may ignore it if unhelpful.
- The Authorization Server must protect the introspection endpoint, authenticate the caller appropriately, and apply policies governing what details the caller may learn.
- The protocol defines a JSON response containing a boolean `active` field.

Client authentication **is not limited to HTTP Basic**. Depending on the Authorization Server and deployment profile, the introspection endpoint may support `client_secret_post`, `private_key_jwt`, mutual TLS, or other methods. Spring Resource Server's simple `client-id/client-secret` properties generally fit client credentials sent via HTTP Basic; if the AS requires another method, configure a dedicated HTTP client/introspector accordingly—**never switch to a weaker method merely for convenience**.

### 2.3. Two tokens/credentials that must never be confused

```text
INBOUND — caller -> API
  Authorization: Bearer <access-token>
                |
                v
OUTBOUND — API -> introspection endpoint
  Authorization: Basic <id-and-secret-of-introspection-client>
  body: token=<the-access-token-to-check>
```

Never put the Resource Server's `client-secret` into `Authorization: Bearer` when calling the Orders API. Never use the caller's access token as an "OAuth client password" to connect to the introspection endpoint. Each value has its own role and trust boundary.

## 3. RFC 7662: what does an introspection response contain?

RFC 7662 specifies **OAuth 2.0 Token Introspection**, centered around the `active` field.

### 3.1. Active token

Example response:

```json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "storefront-web",
  "token_type": "Bearer",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "iss": "https://login.example.com",
  "exp": 2000000000,
  "iat": 1999996400,
  "nbf": 1999996400,
  "tenant_id": "tenant-a"
}
```

Meaning:

| Field | Interpretation | Resource Server action |
|---|---|---|
| **`active`** | Authorization Server indicates whether the token is still active per its policy | **Must be true** to proceed |
| `scope` | List of scopes granted to the token, typically space-delimited | Map to authorities and enforce per endpoint |
| `client_id` | **OAuth client that the access token was issued to** | Can be used for client allowlist policy; **not** the configured introspection client-id |
| `token_type` | Token type declared by issuer | Validate if required by contract |
| `sub` | Token subject if present | Identify user/service per grant/profile; do not assume always a user |
| `aud` | Resource Server/audience permitted to use the token, when provided by AS | Verify `orders-api` if required by contract |
| `iss` | Token issuer if provided by AS | Match against trusted issuer when required by contract |
| `exp` | Expiration NumericDate | Verify consistency with `active` and API policy |
| `iat`, `nbf` | Issuance / not-before timestamps | Use for token-age or time-window rules if any |
| `tenant_id` | Custom attribute | Use only under AS–RS contract, and still enforce resource permissions |

**Not every field beyond `active` is required in every introspection response.** RFC 7662 defines optional fields; the AS profile and Resource Server requirements dictate which fields must be present. If the API needs `aud` to reject tokens issued for other services, ensure the AS provides corresponding trusted data; if absent, **do not assume the token is intended for this API**.

### 3.2. Inactive token

A common response:

```json
{
  "active": false
}
```

Under RFC 7662, responses for inactive tokens are normally minimal to avoid leaking unintended details about the token. `active=false` can mean:

- The token never existed or is invalid.
- The token has expired.
- The token was revoked.
- The token is not permitted to be introspected in this context.
- The AS enforces a policy withholding token details from this specific introspection caller.

Do not return overly detailed internal reasons to the API caller such as "this token belongs to tenant X" or "revoked by admin Y." At the Resource Server, the outcome is simply an **invalid token** and the request is rejected.

### 3.3. `active=true` does not mean sufficient permission on all resources

An active access token might carry only:

```json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "storefront-web",
  "sub": "customer-42"
}
```

For `POST /api/orders/42/cancel` requiring `orders.cancel`, the API must deny the request for **insufficient scope**, regardless of the token being active.

Likewise, for `GET /api/orders/99`, a token with `orders.read` whose subject does not own order 99 must still be denied by the object policy.

## 4. Exact meaning of the three configuration properties

### 4.1. `introspection-uri`: token verification endpoint

Example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
```

`introspection-uri` is the **HTTP(S) URL provided by the Authorization Server for RFC 7662 introspection**, not:

- The access token issuance URL `/oauth2/token`.
- The user sign-in URL `/authorize`.
- `issuer-uri` used for JWT issuer discovery.
- The JWKS endpoint `/jwks` or `/.well-known/jwks.json`.
- An API endpoint on the Orders Resource Server.

The actual path varies by provider: `/oauth2/introspect`, `/protocol/openid-connect/token/introspect`, or a custom route. It must come from **trusted Authorization Server documentation/metadata**, never guessed or taken from a caller-supplied URL.

**HTTPS is mandatory in real environments.** Sending the caller's access token in the body and the client secret over an unencrypted connection can expose both caller and Resource Server credentials.

### 4.2. `client-id`: identity used to introspect

Example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
```

Suppose the environment variable holds `orders-api-introspector`. The Authorization Server recognizes this as a client authorized to call the introspection endpoint.

Points to note:

- This is the **client ID configured in the Resource Server**, not the `client_id` returned inside the introspection response.
- It can be registered separately per API, environment, and permission group.
- Only authorized Resource Servers/instances should hold that identity.
- The AS can apply policies restricting introspection to tokens belonging to specific resources, audiences, or clients.
- Avoid an overly broad client ID with "blanket access to read every token" unless required.

In OAuth, `client_id` is usually an **identifier**, not a secret. A client ID alone does not prove authorization to call the introspection endpoint; client authentication or another mechanism required by the AS is needed.

### 4.3. `client-secret`: proving endpoint access rights

`client-secret` is the credential issued to the introspection client and used when the Resource Server authenticates to the AS.

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Protect it like an application password:

- Never hardcode real values in committed `application.yml` files.
- Never log or print it to stdout on startup.
- Never embed it in JavaScript/frontend or mobile app code.
- Never expose it in exceptions, URL/query strings, metric labels, traces, or HTTP access logs.
- Restrict read access in a secret manager, Kubernetes Secret mount, or runtime secret injection.
- Support rotation and secret distribution to authorized instances.
- Use HTTPS to the endpoint, verifying hostname and certificate chain.

**Never reuse the same secret for other purposes**, such as signing HS256 JWTs, database connections, or another OAuth client. If the secret leaks, the blast radius corresponds to the privileges held by that introspection client.

### 4.4. Not every Authorization Server uses a client secret

An AS may require stronger client authentication, such as **mTLS** or **`private_key_jwt`**. In that model, the three properties `introspection-uri/client-id/client-secret` may be **insufficient** or inappropriate.

Follow the authentication method supported by the AS and registered for the RS. Using secret-based Basic auth is a common example, not the sole mandatory method under RFC 7662.

## 5. Configuring a Spring Boot Resource Server for opaque tokens

### 5.1. Dependencies

Example with Spring Boot 3.x, Spring Security 6.x, Servlet/Spring MVC, and Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

You do not need login UI/OIDC client integration just for the Orders API to introspect bearer access tokens. Do not confuse a **web application OAuth2 Client** with an **OAuth2 Resource Server**. The Resource Server only needs tools to verify access tokens and enforce API policies.

### 5.2. Full configuration via YAML and secret injection

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

At runtime, supply the two environment variables from a secret manager or deployment platform. Never use placeholder strings as real credentials.

Spring Boot also supports **environment binding** so you can supply properties directly, for example:

```text
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_INTROSPECTION_URI
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_CLIENT_ID
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_CLIENT_SECRET
```

These environment variable names correspond to Spring Boot's property prefix; follow your deployment system's injection practices and never put secrets into manifests tracked like public source code.

### 5.3. Enabling opaque-token Resource Server in `SecurityFilterChain`

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OpaqueResourceServerSecurity {

    @Bean
    SecurityFilterChain ordersApiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
```

How this works:

1. `BearerTokenAuthenticationFilter` extracts the bearer token from the request.
2. The authentication manager passes the token to the opaque-token provider.
3. The provider uses `OpaqueTokenIntrospector` to query the Authorization Server.
4. When the result is accepted, Spring Security creates an `Authentication` containing the principal and authorities.
5. `AuthorizationFilter` uses `SCOPE_orders.read` and `SCOPE_orders.write` for functional access control.
6. The service/domain layer continues checking permissions per order, tenant, and business state.

**Chain scope:** `securityMatcher("/api/**")` covers only URLs under `/api/**`. Other URLs require appropriate security chain policies; do not leave internal endpoints outside the matcher unprotected by default.

### 5.4. How does `STATELESS` relate to introspection?

`SessionCreationPolicy.STATELESS` indicates the API does not rely on HTTP sessions to persist authentication across requests. Callers generally must send a bearer access token **on every request**.

That does not mean the AS is necessarily called over the network on every single request in all setups: whether caching happens depends on the introspector and configuration. With default introspection, the endpoint is typically called to validate the token unless you explicitly add caching in the appropriate layer.

At the same time, `STATELESS` is not the sole criterion for disabling CSRF. CSRF decisions also depend on whether the API accepts **browser-submitted cookies/credentials** or other authentication mechanisms. In hybrid session/cookie + bearer systems, evaluate all security chains together.

## 6. How does Spring Security create `Authentication` from introspection?

In the JWT model:

```text
JwtDecoder
  → JwtAuthenticationProvider
  → JwtAuthenticationToken
```

In the opaque-token model:

```text
OpaqueTokenIntrospector
  → OpaqueTokenAuthenticationProvider
  → BearerTokenAuthentication
```

The principal typically implements `OAuth2AuthenticatedPrincipal`, giving access to attributes and authorities returned by the introspector once the token is accepted.

### 6.1. Reading the current `Authentication`

```java
package com.example.orders.api;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentCallerController {

    @GetMapping("/api/me")
    public Map<String, Object> currentCaller(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
            .map(a -> a.getAuthority())
            .toList();

        return Map.of(
            "principalName", authentication.getName(),
            "authorities", authorities
        );
    }
}
```

This is an **illustrative** endpoint. In production systems, do not return all authorities/attributes to every caller by default; expose only the minimum required data.

### 6.2. Principal and attributes in opaque tokens

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

@GetMapping("/api/subject")
public Map<String, String> subject(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    String sub = principal.getAttribute("sub");
    return Map.of("sub", sub != null ? sub : "not-present");
}
```

This code assumes placement inside an appropriate controller on a protected endpoint. If the principal/claim is missing, the application must handle it per contract rather than treating a fallback string like `not-present` as a valid identity for authorization.

**Note:** `authentication.getName()` depends on how the introspector builds the principal and what the issuer returns; never assume it is always an end-user ID. With `client_credentials`, the subject may be a service, client, or another AS-defined identifier.

### 6.3. Converting scopes into authorities

Given the introspection response:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

Spring Security commonly represents the scopes as:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Hence:

```java
.hasAuthority("SCOPE_orders.read")
```

is the standard permission check.

Do not assume fields like `roles`, `groups`, or `permissions` automatically become `ROLE_*` or `PERMISSION_*`. To map custom claims, design an appropriate introspector or converter per the AS contract.

## 7. Difference between `client-id` in config and `client_id` in the introspection response

Two strings look alike yet have completely different meanings:

```yaml
# Identity the Orders API uses to call the introspection endpoint
spring.security.oauth2.resourceserver.opaquetoken.client-id:
  orders-api-introspector
```

And:

```json
{
  "active": true,
  "client_id": "storefront-web"
}
```

| Value | Who owns it? | Role |
|---|---|---|
| `orders-api-introspector` | Resource Server / introspection client | Proves permission to **query token status** at the Authorization Server |
| `storefront-web` | OAuth client receiving the token | Metadata about **which client the token was issued to** |

In addition:

- `sub` can represent a user or a service.
- `aud` identifies the Resource Server intended to consume the token.
- `scope` identifies permissions granted to the token.
- `iss` identifies the Authorization Server, when provided and verified.

Never use the token's `client_id` to construct HTTP Basic credentials for introspection. Never use the Resource Server's `client-id` as proof of which user or client owns the token.

### 7.1. Key identification questions

When the API receives an introspection response, ask:

1. Is this token actually active?
2. Do the issuer, audience, or resource contract confirm the token was issued for the **Orders API**?
3. Which OAuth client was issued the token, and is it on the allowlist for sensitive actions?
4. Is the subject a user or a service, and is that actor supported by this endpoint?
5. Which scopes were granted, and what additional tenant/ownership permissions are required?
6. Are the present attributes **AS-verified data** rather than arbitrary caller-supplied input?

An `active=true` response **does not eliminate** checking the remaining conditions.

## 8. Introspection credentials under the principle of least privilege

### 8.1. A dedicated client registration for the Orders API

A sound layout:

```text
Authorization Server
  |
  +-- Introspection client: orders-api-introspector
  |     - Permitted to call the token introspection endpoint
  |     - Restricted to introspecting tokens for orders-api per AS policy
  |     - Has its own secret or client authentication method
  |
  +-- Introspection client: billing-api-introspector
        - Permitted only to introspect tokens for billing-api
        - Has its own credentials
```

This reduces exposure if the Orders API's credential is compromised. It also yields clear audit trails showing which Resource Server made each introspection request.

RFC 7662 allows the AS to protect the endpoint and limit returned metadata; **not every Authorization Server natively supports scoping introspection by audience**. Verify your provider's configuration and actual deployment policies.

### 8.2. What if multiple Resource Servers share one `client-secret`?

Risks include:

- One RS losing its secret enables an attacker to call introspection on behalf of the other RS instances.
- Audits struggle to distinguish the true source of each request.
- Secret rotation impacts multiple environments/services at once.
- The AS may return more metadata than a single RS needs.
- Revoking credentials becomes hard to coordinate due to widespread dependencies.

Prefer client identities/secrets provisioned **along real trust boundaries**, separating at least development, staging, and production, and separating APIs whenever token access differs.

### 8.3. Never give the secret to callers

Browser/mobile clients only send a **valid access token** to the Orders API. They do not need to know and must never receive:

```text
ORDERS_INTROSPECTION_CLIENT_SECRET
```

If an API asks the frontend to send an introspection secret, that is usually a **severe security boundary error**. Secrecy of that credential can only be maintained within a backend/server-controlled environment.

## 9. HTTPS and data protection when calling introspection

An introspection request carries two sensitive credentials: **the caller's access token** in the body and **the Resource Server's credential** in client authentication.

Therefore:

- Use `https://...`, verifying hostnames and certificate chains.
- The JVM/container must hold the proper truststore/CA for its environment.
- If using a private CA, provision the approved CA to the workload rather than disabling TLS validation.
- Never configure `trustAllCertificates`, `InsecureTrustManager`, or a permissive hostname verifier just to "make errors go away."
- Never automatically follow redirects to unknown hosts with request bodies or Authorization headers carrying credentials.
- Restrict DNS/egress so the RS only reaches authorized introspection endpoints.
- Avoid logging HTTP request bodies containing `token` or `Authorization: Basic ...` headers.

### 9.1. Distinguishing trust layers

| Layer | What to verify | If wrong |
|---|---|---|
| **TLS to AS** | Certificate, host, CA, HTTPS scheme | Resource Server cannot protect tokens/credentials in transit |
| **Client authentication** | `client-id/client-secret` or other method | AS denies introspection, typically rejecting the request |
| **Introspection response** | Valid JSON, `active=true`, contracted claims | Token rejected or must be denied due to missing metadata |
| **API authorization** | Scope, audience/resource, client/subject/tenant/ownership | Request denied even though token is active |

A valid TLS connection to an endpoint in the wrong environment is not "success" either. For example, a production API misconfigured with a staging introspection URI can receive wrong data or treat all production tokens as inactive. Bind endpoints to the **exact issuer/environment**.

### 9.2. Testing with curl without exposing secrets

An illustrative syntax example for authorized environments only:

```bash
curl --fail-with-body --request POST \
  --url "https://login.example.com/oauth2/introspect" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --user "ORDERS_INTROSPECTION_CLIENT_ID" \
  --data-urlencode "token=REDACTED_TEST_TOKEN"
```

In this command, `--user` supplies only the client ID so curl can **prompt interactively for the password**, instead of writing the secret after `:` into command history. In non-interactive CI/container runs, use an organization-approved credential mechanism and avoid exposing secrets in process lists, logs, or artifacts.

This is **not** a ready-to-run command with dummy IDs/tokens; it is a template for verifying form POST and Basic client authentication. If your curl version lacks `--fail-with-body`, use `--fail` and inspect status/headers separately.

In practice, also verify that the AS authorizes that specific introspection client and returns the expected `active` output. Never send real production tokens to external debugging services or CI logs.

## 10. Authentication model in Spring Security

### 10.1. Component names

Typical Servlet flow:

```text
HTTP request: Authorization: Bearer opaque-access-token
        |
        v
BearerTokenAuthenticationFilter
        |
        v
BearerTokenAuthenticationToken (unauthenticated)
        |
        v
AuthenticationManager
        |
        v
OpaqueTokenAuthenticationProvider
        |
        v
OpaqueTokenIntrospector.introspect(token)
        |
        +--> HTTPS POST to Authorization Server
        |
        +--> active=false / error -> Authentication fails
        |
        +--> active=true + attributes / authorities
        |
        v
BearerTokenAuthentication
        |
        v
SecurityContext
        |
        v
AuthorizationFilter / Method Security
        |
        v
Object-level business policy
```

**There is no `JwtDecoder` in the default opaque authentication path.** If a configuration specifies only `oauth2ResourceServer().jwt()` while the AS issues opaque tokens, the API tries to parse them as JWTs and typically fails authentication.

### 10.2. Authentication does not replace Authorization

`OpaqueTokenIntrospector` returns the principal and authorities after introspection. It does not decide which order ID a user may access.

For example, a token is active and carries `SCOPE_orders.read`, yet the caller requests an order from another tenant:

```text
Authentication          : valid
Functional authorization: has SCOPE_orders.read
Object authorization    : DENY (different tenant/owner)
```

The service/domain layer must still verify tenant, ownership, resource state, and client policies. Without object-level checks, an API remains vulnerable to **BOLA/IDOR** even if every access token is introspected properly.

## 11. Validating active tokens, permissions, and remaining metadata

### 11.1. How should `active` be interpreted?

RFC 7662 allows the Authorization Server to derive `active` from conditions it manages, such as existence, lifetime, or revocation state. The Resource Server trusts that result **within the scope the caller is permitted to introspect**, never inferring token state from string appearance.

Reject if:

- The response omits `active` or `active` is not a boolean per contract.
- `active=false`.
- The introspection client cannot authenticate.
- TLS validation fails.
- The response cannot be parsed or the endpoint is untrusted.
- Additional mandatory API conditions are not satisfied.

### 11.2. Scope mapping

Per RFC 7662, `scope` is typically a space-delimited string:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

Spring Security can map this to `SCOPE_orders.read` and `SCOPE_orders.write`.

However, if the provider uses another role/custom claim format, never assume Spring automatically turns every field into authorities. Build an explicit adapter mapping whenever the AS metadata contract differs from the default mechanism.

### 11.3. Checking audience and issuer

**Opaque tokens do not mean skipping resource-scope checks.**

If the introspection response contains:

```json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "orders.read"
}
```

The Orders API must not accept that token simply because it has a matching scope name; `aud` shows the token was issued for a different API.

Align between AS and RS:

- Does the AS return `aud`/`iss`/`token_type` per contract?
- If `aud` is absent, does the AS **guarantee the introspection client can only inspect tokens meant for the Orders API**?
- Can `orders-api-introspector` introspect tokens belonging to other resources?
- With multiple issuers/tenants, how does the RS route to the right AS and policy?
- If a mandatory attribute is missing or mistyped, how does it **fail closed**?

Never quietly drop audience validation just because the introspection response returns only `active` and `scope`. If resource isolation is required, design a trusted source of proof for it across AS and RS.

## 12. Adding audience enforcement in a custom `OpaqueTokenIntrospector`

Spring Boot auto-configures an introspector from the three properties shown above. When additional metadata checks are required, the application can define a custom `OpaqueTokenIntrospector` bean.

The example below uses `NimbusOpaqueTokenIntrospector`, a familiar implementation in the Spring Security 6.x line; **implementation APIs can change in newer versions**, so verify matching dependencies/builders when applying it. The goal is to illustrate the **decorator** pattern: run standard introspection first, then enforce the audience contract.

```java
package com.example.orders.security;

import java.util.Collection;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class OrdersIntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String introspectionUri,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String introspectionClientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String introspectionClientSecret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(
                introspectionUri,
                introspectionClientId,
                introspectionClientSecret
            );

        return token -> {
            // Delegate handles HTTP introspection and active status.
            OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

            Object rawAudience = principal.getAttribute("aud");
            boolean forOrdersApi = false;

            if (rawAudience instanceof String singleAudience) {
                forOrdersApi = "orders-api".equals(singleAudience);
            } else if (rawAudience instanceof Collection<?> audiences) {
                forOrdersApi = audiences.contains("orders-api");
            }

            if (!forOrdersApi) {
                throw new BadOpaqueTokenException(
                    "Introspected token is not for orders-api"
                );
            }

            return principal;
        };
    }
}
```

Explanation:

1. `NimbusOpaqueTokenIntrospector` sends the token to the configured URI and authenticates using the configured client ID/secret.
2. If the token is inactive, the delegate does not return a valid authenticated principal.
3. Upon receiving the principal, the wrapper reads the `aud` attribute.
4. If `aud` does not indicate `orders-api` under the agreed structure, the wrapper rejects the token.
5. Only then does `OpaqueTokenAuthenticationProvider` turn the principal into an `Authentication`.

**Limitations of this example:** it assumes the AS returns `aud` as a string or collection. Real contracts may require validating `iss`, `exp`, `client_id`, token type, tenant, and extra policies. Never allow or deny based on attributes the AS does not guarantee.

**Note on auto-configuration:** when an application defines its own `OpaqueTokenIntrospector` bean, Spring Boot uses that bean in place of the auto-configured introspector. Therefore, the custom implementation must **preserve complete `active` checks, client authentication, TLS, and error handling**, rather than returning a "valid" principal whenever a token string looks formatted.

### 12.1. Never construct a principal from token text while skipping introspection

An anti-pattern:

```java
// DO NOT do this in a real system:
return token -> new DefaultOAuth2AuthenticatedPrincipal(
    "someone",
    Map.of("scope", "orders.admin"),
    List.of(new SimpleGrantedAuthority("SCOPE_orders.admin"))
);
```

This is **deliberately wrong**: it bypasses the AS, accepts every bearer token, and grants privileges. A custom introspector must rely on a trusted introspection result or another explicitly designed verification mechanism, never "translating a token string into permissions" on its own.

## 13. Customizing authorities and principal for opaque tokens

Not every Authorization Server returns scopes and roles in the same structure. If the AS returns:

```json
{
  "active": true,
  "sub": "customer-42",
  "scope": "orders.read",
  "permissions": ["orders.export"],
  "tenant_id": "tenant-a"
}
```

and the Orders API wants to add `PERMISSION_orders.export`, you can write an introspector wrapper that reads `permissions`, rebuilds the principal preserving verified attributes, and merges authorities.

Conceptual approach:

```text
Trusted introspection response
       |
       +--> scope -> SCOPE_orders.read
       |
       +--> permitted permissions -> PERMISSION_orders.export
       |
       +--> principal sub, tenant_id
       |
       v
OAuth2AuthenticatedPrincipal with contracted authorities
       |
       v
BearerTokenAuthentication
```

Safety requirements:

- Never turn arbitrary `"ADMIN"` or `"SUPERUSER"` strings into system-wide roles.
- Scope permissions by resource/tenant.
- Keep base scope authorities when adding custom authorities.
- Reject or ignore mistyped permission values outside the contract.
- Avoid using mutable usernames/emails as business identifiers when `issuer+subject` is more stable.
- Grant no permissions when introspection fails or required metadata is missing.

With custom introspection, use the Spring Security abstractions appropriate to your library version to return an `OAuth2AuthenticatedPrincipal` with an explicit `GrantedAuthority` list. Never store client secrets or raw tokens inside attributes where controllers could read them.

## 14. Error statuses: 401, 403, and introspection service errors

A critical operational need is distinguishing **caller bearer token errors** from **Resource Server credential or network errors**.

| Scenario | Where does it happen? | How to interpret |
|---|---|---|
| Missing Bearer token on protected API | Inbound HTTP | Caller provided no credentials; typically `401` |
| Introspection returns `active=false` | AS confirms token is inactive | Token not accepted; typically `401 invalid_token` |
| Active token lacks `orders.read` | `AuthorizationFilter` / policy | Caller authenticated but lacks scope; typically `403` |
| Active token with scope, wrong owner/tenant | Domain service | Deny with `403` or `404` per policy |
| Introspection returns HTTP `401` to Basic client | RS → AS | Likely wrong introspection client-id/secret or auth method; **do not** treat as inactive token |
| Introspection endpoint timeout/`5xx` | RS → AS | Infrastructure dependency failure; **do not** authenticate token by guessing |
| Untrusted TLS certificate | RS → AS | Authentication channel failure; never disable TLS validation |
| Malformed JSON / missing `active` | AS/proxy response | Insufficient proof to authenticate; reject |
| Rate limit `429` from AS | RS → AS | Handle capacity/backoff; never treat token as automatically valid |

### 14.1. HTTP Basic 401 is not a bearer 401

Suppose the Resource Server calls introspection with the wrong secret:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
```

This is **the Authorization Server rejecting Resource Server authentication**. It differs from the Orders API returning `401` to a caller when an access token is inactive.

If you conflate the two, operations may blame "users sending bad tokens" while every token fails because the introspection secret expired. Log and categorize **outbound client authentication errors** without logging the secret.

### 14.2. Difference between 401 and 403 on the inbound API

Example missing/invalid token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Example active token lacking scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Exact headers/challenges depend on Spring Security's `AuthenticationEntryPoint` and `AccessDeniedHandler` configuration. When a token is completely absent, the bearer challenge can differ from an `invalid_token` challenge; do not assume all 401 errors produce the exact same message.

### 14.3. Should an AS outage return 401 or 503?

This is an **application policy and error-mapping decision**, not a fixed automatic rule.

- If the token cannot be introspected, the RS **has no proof to authenticate** the caller.
- Never fall back to `permitAll`, default `"active=true"`, or a hardcoded temporary client secret.
- You may map AS dependency failures to `503 Service Unavailable` when infrastructure is down, while keeping genuine token failures at `401`.
- Understand the default behavior and exception mapping of your Spring Security/HTTP client version; never claim the framework always returns a single fixed status for timeouts.

The goal is to **fail closed on access control** while preserving operational visibility separating caller errors from system failures.

## 15. SSRF risk and introspection endpoint mix-ups

`introspection-uri` must be a URL **configured and permitted by the application or organization**, never derived dynamically from:

- A caller's HTTP header.
- An `introspection_url` query parameter.
- An unverified claim inside the access token.
- A client-supplied hostname.
- Unverified metadata from an issuer outside the allowlist.

If an API lets clients choose the URI to which the server POSTs tokens, it opens an **SSRF** risk and **leaks both bearer tokens and introspection credentials** to an attacker's endpoint.

In multi-issuer/multi-tenant setups, route tokens to the right AS using trusted configuration rather than "trying tokens sequentially against every AS" uncontrollably. Sending an access token from issuer A to issuer B's introspection endpoint can also disclose credentials to an unauthorized party.

### 15.1. One introspection client per environment

Example:

| Environment | `introspection-uri` | Client identity |
|---|---|---|
| Development | `https://login.dev.example.com/oauth2/introspect` | `orders-api-introspector-dev` |
| Staging | `https://login.staging.example.com/oauth2/introspect` | `orders-api-introspector-staging` |
| Production | `https://login.example.com/oauth2/introspect` | `orders-api-introspector-prod` |

Each environment should have its own secret/credentials, TLS policy, and token scope; never use a production client secret on a developer laptop.

**If the issuer uses a realm/tenant path**, the introspection endpoint may also include that provider-specific path, e.g. `/realms/orders/protocol/openid-connect/token/introspect`. Confirm the exact URL from the provider and tenant context rather than assembling paths by guesswork.

## 16. Secret managers, rotation, and protecting the introspection client

### 16.1. Provisioning credentials

The Authorization Server administration team should register the introspection client with appropriate policies:

1. Assign a meaningful client ID for the Orders API or a specific Resource Server group.
2. Choose the client authentication method (Basic secret, `private_key_jwt`, mTLS, etc.).
3. Restrict introspection permissions to only the required tokens, if the AS supports such policy.
4. Generate and store the secret using the organization's secret management system.
5. Share endpoint details, audience/resource expectations, and the claim contract with the Resource Server team.
6. Document the rotation plan, lifetime, and recovery procedure if credentials break.
7. Enable endpoint logging/auditing safely, without recording tokens or raw `client-secret` values.

### 16.2. Secret rotation without disrupting all requests

A common rollout sequence:

```text
T0: Resource Server uses secret A
T1: Authorization Server creates secret B (if overlap is supported)
T2: Distribute B securely to all RS instances
T3: Switch RS to B and verify introspection succeeds
T4: Revoke A after all instances have switched
```

If the AS does not support multiple active secrets simultaneously, plan a safe cutover/rollback window.

Never log both secret A and B in app logs to "debug." Track active credentials via secret IDs/versions or non-sensitive config metadata.

### 16.3. Leaked introspection credentials vs. leaked access tokens

If the **introspection client's `client-secret`** is compromised, an attacker can impersonate the Resource Server at the **introspection endpoint** within the client's granted permissions. That does not automatically let them sign new JWTs or mint new access tokens; exact impact depends on granted permissions and AS design.

If a **bearer access token** is compromised, anyone holding it can try to use it at the API while it remains active, unless it is sender-constrained or otherwise protected.

Both are serious yet require **different incident responses**: revoke/rotate introspection credentials and audit introspection queries, or revoke the access token and investigate data access.

## 17. Performance: one API request can require one introspection request

A benefit of self-verifying JWTs is that the RS can usually verify them offline using cached public keys. With opaque tokens, introspection typically introduces a network dependency:

```text
N API requests per second
          |
          v
N introspection calls per second (if uncached)
          |
          v
Authorization Server capacity, network latency, TLS, rate limits
```

If the Orders API serves 2,000 RPS and every request introspects, the AS must handle a matching query load **unless caching or another optimization is used**.

### 17.1. Caching introspection: faster, yet carries staleness risk

Per-token caching can cut latency and AS load. However:

- Revoked tokens can still be accepted until the cache entry expires.
- `exp` must be respected; cache entries must never outlive remaining token validity.
- Cache keys/tokens are sensitive data; avoid plaintext exposure in metrics, dumps, or logs.
- Bound cache size to prevent memory exhaustion from random tokens.
- Role/tenant attributes can change while an entry remains cached.
- Systems requiring near-instant revocation may not permit long caching.

A cache design rule:

```text
cacheTtl <= min(
    configuredMaxCacheTtl,
    remainingTimeToExp,
    acceptableRevocationDelay
)
```

This is a **policy guideline**; if introspection omits `exp`, the RS must apply a fail-closed rule or risk-appropriate TTL rather than assuming infinite validity.

**Do not assume Spring Security caches introspection responses automatically by default.** When adding caching via a decorator or infrastructure layer, explicitly design and test its interaction with revocation.

### 17.2. Timeouts and circuit breakers

To prevent hanging all HTTP threads:

- Set connect/read timeouts aligned with API and AS SLAs.
- Bound concurrency for calls to the introspection endpoint.
- Use conditional retries with backoff/jitter where appropriate; avoid retry storms that overwhelm the AS.
- Add a circuit breaker to protect capacity, **never allowing tokens through automatically when the breaker opens**.
- Monitor latency/timeouts/error rates by error type.
- Define readiness/dependency handling when the AS is unavailable.

Never treat client authentication 401s as infinitely retryable; classify them and fix the secret/policy. Technical settings such as timeouts/caching depend on your introspector/HTTP client version, so never assume a single default property applies to every project.

## 18. When to choose opaque tokens over self-verifying JWTs?

| Criterion | Opaque token + introspection | Signed JWT + local validation |
|---|---|---|
| Token verification method | RS calls AS/introspection endpoint | RS verifies signature locally with trusted keys |
| Network dependency during verification | Usually yes, unless cached/designed otherwise | Usually no per-request network call |
| Revocation status updates | Can reflect revocation on re-introspection | Local JWT validation usually accepts until `exp` without a separate revocation feed |
| AS secret needed by RS? | No JWT signing private key needed; introspection credentials needed if AS requires them | Only public key/JWKS for asymmetric signatures |
| Token details visible to caller | String can be unreadable | JWS payload is Base64URL-readable unless encrypted |
| Centralizing policy at AS | Can centralize at introspection, depending on AS | Requires claim validation and extra policy sources |
| Latency and availability | Depends on AS and network | Optimized for local verification |
| Operating many Resource Servers | Manage client credentials/AS capacity | Manage public keys, issuers, key rotation |

Neither option is universally best. Opaque + introspection fits when you need centralized token state management, want to avoid exposing claims inside tokens, or the AS provides online verification. Local JWT fits when reducing per-request AS dependency is vital, provided revocation and claim freshness are handled separately.

**Important:** introspection does not solve all authorization concerns by itself. Even with an active token, the Resource Server must enforce functional and object-level permissions.

## 19. Specific concerns with OAuth scopes and OIDC

### 19.1. OAuth access token vs. OIDC ID token

An OIDC ID token proves sign-in results to the **OIDC client**, whereas an access token is used to call the **Resource Server**.

An AS may support introspection for multiple token types, yet the Orders API must require an **access token** per contract; never accept an ID token or refresh token as a bearer access token merely because an introspection endpoint returned metadata.

If the introspection response includes `token_type` or classification metadata, validate it accordingly. Clarify with the AS that `active=true` is returned only for access tokens intended for this API, not tokens issued for other purposes.

### 19.2. Client Credentials has no end user

Example machine-token introspection:

```json
{
  "active": true,
  "client_id": "nightly-worker",
  "sub": "nightly-worker",
  "scope": "orders.export",
  "aud": ["orders-api"],
  "exp": 2000000000
}
```

`sub` can represent a service/client rather than an end user. The Resource Server must apply **client allowlists**, tenant rules, and job policies; do not apply the same customer ownership rule indiscriminately to every token.

### 19.3. Never treat scope as permission on every record

A token with `scope=orders.read` still cannot read another customer's order if the API forbids it. Require all of:

```text
active token
AND trusted AS
AND resource/audience is orders-api
AND SCOPE_orders.read
AND actor can read this order
AND tenant and business rules allow
```

Omitting the object-authorization step leaves the application exposed to BOLA even when opaque tokens are introspected properly.

## 20. Testing an introspection configuration

### 20.1. Unit tests at the service/policy layer

You can mock `OAuth2AuthenticatedPrincipal` and authorities to test authorization logic. These tests do not call the AS or test HTTP Basic/TLS; they test mapping and authorization logic only.

### 20.2. Spring Security Test with mock opaque tokens

Spring Security Test provides `opaqueToken()` for MockMvc to inject test authentication:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

mvc.perform(get("/api/orders/42")
    .with(opaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")
    )))
    .andExpect(status().isOk());
```

This is an **illustrative snippet**, assuming the test endpoint/order is readable and the test class configures `MockMvc`, data fixtures, and dependencies appropriately.

**Limitation:** `opaqueToken()` sets up a SecurityContext/principal in tests; it **does not prove** the app sent a POST to the AS, used valid Basic credentials, verified TLS, or handled `active=false` properly.

### 20.3. Integration tests with a fake introspection server

A thorough Resource Server test suite can run a local test HTTP server simulating the introspection endpoint in an isolated test environment. Example cases:

| Input | Mock introspection | Expected behavior |
|---|---|---|
| Valid Bearer token | `200 {"active":true,"scope":"orders.read","aud":["orders-api"]}` | Request passes auth, proceeds to object policy |
| Revoked Bearer token | `200 {"active":false}` | Request fails authentication |
| Active token missing scope | `200 {"active":true,"scope":"orders.read"}` | POST endpoint requiring `orders.write` is blocked |
| Active token with wrong audience | `200 ... "aud":["billing-api"]` | Rejected by validator/decorator |
| Wrong introspection client ID/secret | `401` from mock AS | Token not accepted |
| AS returns `500` | Server-side error | Fail closed, classify dependency failure |
| AS timeout | No response | No access granted and threads do not hang indefinitely |
| Untrusted TLS certificate | TLS handshake failure | Never bypass TLS |
| Malformed response / missing `active` | JSON violates contract | Never treat as active |
| Wrong order tenant/owner | Token active and sufficient scope | Domain policy still denies |

To test **real HTTP**, send an `Authorization: Bearer <TEST_TOKEN>` header through the real Spring Security filter chain against a controlled fake AS endpoint with client auth, verifying both outbound requests and inbound responses; do not rely on `opaqueToken()` as proof of per-request introspection.

### 20.4. Verifying HTTP Basic client authentication

On the fake AS, assert:

- Client authentication follows the registered method.
- Client ID matches.
- Secret matches without appearing in logs or assertion output.
- Request has `Content-Type: application/x-www-form-urlencoded`.
- Body contains `token` matching the test token.
- `active` is parsed strictly as boolean.
- An unauthorized introspection caller is rejected.
- Outbound TLS trust and timeouts match production-like settings.

When mocking secrets, use harmless dummy values; never copy production secrets into fixtures.

## 21. Common operational issues

### 21.1. Resource Server returns 401 for all tokens even though the AS just issued them

Possible causes:

- `introspection-uri` points to the wrong host/realm/environment.
- AS rejects the client ID/secret or the introspection client lacks permission.
- Request uses the wrong client authentication method.
- Token audience/issuer does not satisfy the AS's introspection policy.
- Spring is configured with `jwt()` instead of `opaqueToken()`.
- Custom introspector/validator rejects missing required metadata.

Inspect **safe server-side logs** on both RS and AS, separating inactive tokens from client authentication failures. Never print real tokens or secrets to "compare" them.

### 21.2. Curl succeeds on a laptop, fails inside a Java container

Common reasons:

- JVM truststore is missing a private CA.
- Container/pod lacks egress/DNS to the AS.
- Container proxy differs from the laptop.
- SNI/hostname certificate mismatch.
- Network policy/firewall blocks only the workload.
- URL configured in the pod differs from the command tested on the laptop.

Test from a **network/TLS environment matching the real pod**, never enabling `--insecure` to hide the issue.

### 21.3. The API worked yesterday, then every request failed after secret rotation

Check:

1. Was the new secret activated on the AS?
2. Was the secret distributed to **all instances**?
3. Are old pods or failed rollout replicas still holding the revoked secret?
4. Was the Client ID accidentally changed along with the secret?
5. Is there another Basic auth or token endpoint setting that the app is misusing?

Never work around this by switching the API to `permitAll()`; restore proper introspection authentication.

### 21.4. Token is active yet the API returns 403

Reasons include:

- Scope does not include the authority required by the endpoint.
- The `SCOPE_` prefix was not mapped properly.
- Introspection response lacks a role/permission field expected by a custom converter.
- The client is not permitted to access that feature despite having the scope.
- Tenant/ownership/resource policy denied access.

This can be a valid **authorization failure**, not necessarily an `introspection-uri` bug.

### 21.5. AS rate-limits requests after traffic increases

Opaque introspection creates a load dependency. Monitor:

- Introspection calls/sec per RS/client.
- Latency p50/p95/p99 and timeouts.
- Ratio of inactive vs. active tokens.
- AS rate limits/client quotas.
- Cache/revocation trade-off.
- Retry storms, HTTP connection counts, and concurrency.

Never lengthen cache TTLs arbitrarily if business rules require near-instant revocation.

## 22. Per-environment rollout checklist

| Check | Development | Staging | Production |
|---|---|---|---|
| `introspection-uri` matches right issuer/realm | Required | Required | Required |
| Valid HTTPS certificate/SAN/truststore | Yes | Yes | Yes |
| Dedicated Client ID/secret with introspection permission | Yes | Yes | Yes |
| Secret injected safely, never committed/logged | Yes | Yes | Yes |
| No mixing of dev/staging/prod tokens | Yes | Yes | Yes |
| `active=false` results rejected | Yes | Yes | Yes |
| Scopes mapped to authorities per contract | Yes | Yes | Yes |
| Audience/resource policy enforced | Yes | Yes | Yes |
| Client/subject/tenant/object policy enforced | Yes | Yes | Yes |
| AS errors, timeouts, rate limits fail closed | Yes | Yes | Yes |
| Client credential rotation plan | Yes | Yes | Yes |
| Monitoring for outages, latency, Basic credential errors | Yes | Yes | Yes |
| No raw tokens leaked in logs/traces | Yes | Yes | Yes |
| Cache TTL aligned with revocation requirements | Yes | Yes | Yes |

This table lists **conditions to verify**, not pre-measured outcomes in any environment.

## 23. An end-to-end decision walkthrough

Suppose a user holds token `T1`, and the Orders API uses introspection client `orders-api-introspector`.

**Step 1 — Request arrives at Orders API**

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer T1
```

**Step 2 — Orders API introspects**

The Orders API sends `T1` over HTTPS in the form body to `https://login.example.com/oauth2/introspect`, authenticating with **the Orders API's own** client ID/secret.

**Step 3 — AS returns status**

```json
{
  "active": true,
  "client_id": "storefront-web",
  "scope": "orders.read",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "tenant_id": "tenant-a"
}
```

**Step 4 — Spring creates `Authentication`**

```text
Principal:
  subject = customer-42
  client_id = storefront-web
  tenant_id = tenant-a

GrantedAuthorities:
  SCOPE_orders.read
```

**Step 5 — Service checks order 42**

The database confirms order 42 belongs to `customer-42` and `tenant-a`, in a readable status. Data can then be returned if all other business rules pass.

If the same token is used for order 99 belonging to `tenant-b`, **the scope still matches** yet the service must deny access. If `active=false`, the request is rejected **before** object policy runs. If the introspection `client-secret` is wrong, the AS rejects the Orders API and the API must fail closed rather than guessing validity from `T1`.

This cleanly separates three responsibilities:

```text
Bearer credential from caller
         |
         v
Resource Server authenticates to Authorization Server
(introspection-uri + client-id/client-secret)
         |
         v
Authorization Server confirms token active
         |
         v
Spring builds Authentication with authorities
         |
         v
API and service enforce functional + object policies
```

## 24. Key takeaways

- **`introspection-uri`** is the Authorization Server's RFC 7662 endpoint; the Resource Server calls it to query access token state.
- **`client-id` and `client-secret` under `opaquetoken`** are credentials for **the Resource Server to authenticate to the introspection endpoint**, not the caller's access token.
- **`client_id` in the response** usually identifies the OAuth client that received the token; it differs from the `client-id` in the Resource Server's configuration.
- Callers send `Authorization: Bearer <access token>` to the API; the API uses **its own client authentication** when querying the AS.
- **`active=true` is a foundational condition, not sufficient by itself**: the API still checks scope, audience/resource, client/subject, tenant, ownership, and business rules.
- **`active=false` or introspection errors can never be interpreted as "allow"**; always fail closed.
- **TLS must be verified** because introspection requests carry both the caller's token and the RS's credentials.
- Spring Security Servlet uses `OpaqueTokenIntrospector` and `OpaqueTokenAuthenticationProvider`; the result is typically `BearerTokenAuthentication` with `OAuth2AuthenticatedPrincipal`, distinct from the `JwtDecoder` flow.
- Opaque introspection introduces network/AS dependencies, requiring deliberate timeouts, capacity planning, and cache/revocation trade-offs.
- Protect introspection secrets, isolate permissions by API/environment, rotate credentials, and monitor carefully.
- Unit/MockMvc `opaqueToken()` tests do not test real HTTP introspection; add integration tests with a fake AS to verify Basic auth, TLS, `active`, and network failures.

## 25. Standards and references

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): endpoint, introspection caller authentication/authorization, request/response, and the `active` field.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client authentication, scopes, and tokens.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer tokens in the `Authorization` header and `invalid_token` / `insufficient_scope` errors.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata that may publish the introspection endpoint and supported client authentication methods.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): opaque token introspection configuration and architecture for Servlet.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): bearer authentication, `SecurityContext`, and authorization.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): endpoint permissions and scope authorities.

**Conclusion:** In an opaque-token Resource Server, **the caller's access token and the API's introspection credential are two distinct identities on two separate connections**. Properly configuring `introspection-uri`, `client-id`, and `client-secret` lets Spring Security query the right Authorization Server with an authorized identity; the introspection response merely provides the basis for authenticating the token. Access to resources must still be governed by **scope, audience, subject/client, and the Resource Server's business policies**.
