# Missing Token vs. Present but Invalid Token

## 1. Two requests can both return 401 while differing fundamentally

An **OAuth 2.0 Resource Server** protecting an API with Bearer access tokens can return `401 Unauthorized` in both of these cases:

1. **No Bearer token:** The client did not provide a credential required by the API. There is no token string to validate.
2. **Bearer token present but invalid:** The client supplied a credential, yet the Resource Server rejects it—for example, an expired token, invalid signature, or untrusted issuer.

Consider a `GET /api/reports` endpoint requiring an access token:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
```

This is a request **without a token**. In contrast:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...invalid-or-expired...
```

This is a request **with a Bearer credential**; the Resource Server attempts to validate it and determines that the credential is invalid. Distinguishing these two helps you interpret `WWW-Authenticate` properly, understand the Spring Security flow, and choose the right remediation.

In most Bearer-only APIs, both states lead to **401** when the endpoint requires authentication. However, they differ in root cause, processing stage, and error details. Moreover, **a valid token lacking permissions** is a third distinct case, typically yielding **403 Forbidden**.

## 2. Comparison table of the three states

| State | Authentication | Authorization | Typical response |
|---|---|---|---|
| No Bearer token | No credential provided to authenticate the caller. | Endpoint requires authentication, so access is denied. | `401`, header `WWW-Authenticate: Bearer`, usually **no `error` code**. |
| Token present but invalid | Credential received, but authentication failed. | Does not reach permission evaluation for a valid principal. | `401`, `error="invalid_token"` when the error is an invalid-token failure. |
| Valid access token lacking permissions | Authentication succeeded. | Fails scope/authority or permission policy checks. | `403`, possibly with `error="insufficient_scope"`. |

Decision flow:

```mermaid
flowchart TD
    A["Request enters Resource Server"] --> B{"Bearer credential present?"}
    B -- "No" --> C{"Endpoint requires auth?"}
    C -- "No" --> D["May be allowed to proceed"]
    C -- "Yes" --> E["401 - Bearer challenge, without invalid_token"]
    B -- "Yes" --> F{"Token passes validation?"}
    F -- "No" --> G["401 - invalid_token or corresponding syntax error"]
    F -- "Yes" --> H{"Sufficient endpoint permissions?"}
    H -- "No" --> I["403 - access denied / insufficient_scope"]
    H -- "Yes" --> J["Proceed to data and business permission checks"]
```

The diagram assumes a Bearer-only API. If the application also supports sessions, Basic auth, or another mechanism, a request **without a Bearer token** might still authenticate via that mechanism; the final result depends on the filter chain.

## 3. What does "no token" mean?

The Resource Server did not receive a Bearer credential in any way it is configured to read. For example:

- No `Authorization` header is present.
- The client mistakenly used `X-Access-Token` while the API only reads `Authorization`.
- The client sent `Authorization: Basic ...` to a Bearer-only API; the Bearer resolver does not treat this as a Bearer token.
- The client placed `access_token` in the query string, while the resource server uses the default `DefaultBearerTokenResolver` without URI token extraction enabled.

Request to a protected endpoint:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Accept: application/json
```

Typical response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

If the server configures a realm, the header may be:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api"
```

RFC 6750 advises servers **not to send an `error` code** when the client sent no authentication credentials. Therefore, **no token** usually results in a bare Bearer challenge or one with only `realm`, rather than `invalid_token`.

### Public endpoints may not require a token

Suppose `/api/public` is configured with `permitAll()`. A request without a token can still return **200 OK**. The Bearer filter finds no token and lets the request continue; at the authorization step, `permitAll()` grants access.

Conversely, `/api/reports` requiring `authenticated()` or `SCOPE_reports:read` cannot be accessed by an anonymous request in a Bearer-only application. Hence **having no token does not raise an error at the Bearer credential extraction step**; whether 401 occurs depends on whether the endpoint requires authentication.

## 4. What does "token present but invalid" mean?

The client sent a Bearer token string:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...expired...
```

The Resource Server received a credential, but validation failed. Typical response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Additional parameters may appear:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api", error="invalid_token", error_description="The access token expired"
```

`error_description` is only an optional field. Clients should rely on the HTTP status and standardized `error` code, not exact wording of the description.

### Causes to recognize

| Cause | JWT access token | Opaque access token |
|---|---|---|
| Expired | `exp` claim has expired. | Introspection reports token is no longer active. |
| Invalid signature/algorithm | JWT decoder cannot verify signature or algorithm is disallowed. | Opaque tokens do not undergo JWT-style signature checks by the Resource Server. |
| Untrusted issuer | `iss` claim does not match configured issuer. | Checked per issuer/introspection contract and API policy. |
| Wrong audience | `aud` does not target this API, **if the API configures audience validation**. | Evaluate token info and target resource from introspection/provider data. |
| Not yet valid | `nbf` or related time condition is invalid. | Depends on introspection state and provider rules. |
| Token revoked | Offline JWT validation does not detect all revocations without additional mechanisms. | Introspection typically reflects inactive state when supported by provider. |
| Wrong token type | For example, sending an **OIDC ID token** to an API checking audience/token type. | Enforce provider token-type policies. |

**A validly signed JWT is not automatically authorized to call an API.** An OIDC ID token may be signed by the same issuer yet meant for an OIDC Client; the API must validate audience, access-token profile, and resource-specific policies. Simply enabling a JWT decoder without verifying the token is intended for the API can cause improper token acceptance.

### Malformed request syntax is a separate branch

For example, the header:

```http
Authorization: Bearer
```

does not provide a valid Bearer string. Or a client might send tokens via multiple transport methods simultaneously when multi-source extraction is enabled. These cases happen at the **BearerTokenResolver** step and can throw `OAuth2AuthenticationException` before the JWT decoder/introspection even runs.

RFC 6750 distinguishes these codes:

| Bearer error code | Meaning | Common HTTP status |
|---|---|---|
| `invalid_token` | Token expired, revoked, malformed, or unacceptable. | **401** |
| `invalid_request` | Malformed Bearer request, duplicate parameters, multiple transport methods, etc. | **400** |
| `insufficient_scope` | Valid token lacking required resource permissions. | **403** |

**Do not assert that every malformed Bearer header returns the exact same code.** Outcomes depend on the specific error and how `DefaultBearerTokenResolver` or a custom resolver represents errors. Inspect both status code and `WWW-Authenticate`.

## 5. How does Spring Security handle each branch?

Within `oauth2ResourceServer()`, a key component is `BearerTokenAuthenticationFilter`. The filter uses `BearerTokenResolver` (typically `DefaultBearerTokenResolver` by default) to extract the token.

### Branch A: No Bearer token

1. The resolver returns `null` because no Bearer credential was detected.
2. `BearerTokenAuthenticationFilter` **does not call the JWT decoder or introspection**; it lets the request continue through the filter chain.
3. If the endpoint requires an authenticated user, the authorization step rejects the anonymous request.
4. `ExceptionTranslationFilter` invokes the appropriate authentication entry point; in a Bearer Resource Server, `BearerTokenAuthenticationEntryPoint` typically returns **401** with a Bearer challenge without `invalid_token`.

Because no credential was sent, **you cannot conclude a JWT was expired or had a bad signature**. No token was ever inspected.

### Branch B: Token present, validation fails

1. The resolver extracts the Bearer token.
2. The filter passes the token to `AuthenticationManager` and the authentication provider.
3. For JWTs, `JwtDecoder` verifies signature, timestamps, issuer, and configured validators. For opaque tokens, the Resource Server uses `OpaqueTokenIntrospector` or matching introspection logic.
4. If the credential is rejected, authentication fails; the failure handler/entry point emits a Bearer challenge, typically **401** with `invalid_token`.

If the resolver itself throws an exception due to a malformed request, JWT validation may never execute; the response then reflects the `BearerTokenError` produced by the resolver.

### Branch C: Authentication succeeds, insufficient permissions

1. A valid access token produces an `Authentication` in `SecurityContext`.
2. The endpoint requires an authority or authorization condition that the `Authentication` does not satisfy.
3. The access denied handler runs. `BearerTokenAccessDeniedHandler` can produce **403** with `insufficient_scope` for applicable Bearer authentications.

Key ordering: **extract credential → validate token → endpoint authorization → data/business authorization**.

## 6. Spring Boot Resource Server example

An application using JWT access tokens can configure the issuer like this:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
```

Endpoint rules:

```java
@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/reports/**")
                            .hasAuthority("SCOPE_reports:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

The example uses Spring Security classes such as `HttpSecurity`, `SecurityFilterChain`, `HttpMethod`, and `Customizer`. Typically, the JWT's `scope`/`scp` claim is mapped to authorities prefixed with `SCOPE_`. Requiring `SCOPE_reports:read` means the token needs the `reports:read` scope under the configured mapping mechanism.

**Configuring `issuer-uri` alone does not prove the token has an audience intended for this API.** Depending on Spring Security/Boot version and provider, add an audience validator and required access-token profile/type checks. Authorization checks also include ownership, tenant, and business policies.

For opaque tokens, configure Resource Server under `opaquetoken` and provide the introspection URI and client credentials per the Authorization Server. The “missing Bearer token” and “rejected token” branches still carry the same meaning.

### Case 1: No token sent

```bash
curl -i https://api.example.test/api/reports/2026
```

Typical response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

### Case 2: Fake/invalid token sent

```bash
curl -i \
  -H 'Authorization: Bearer definitely-not-a-valid-token' \
  https://api.example.test/api/reports/2026
```

With the JWT decoder, the fake token fails validation:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

### Case 3: Valid token lacking `reports:read`

```bash
curl -i \
  -H 'Authorization: Bearer <VALID_ACCESS_TOKEN_WITHOUT_REPORTS_READ>' \
  https://api.example.test/api/reports/2026
```

Typical response:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

The header may include parameters such as `scope` depending on the handler; do not rely on every implementation always enumerating all missing scopes.

### Case 4: Valid token with sufficient scope

```bash
curl -i \
  -H 'Authorization: Bearer <VALID_ACCESS_TOKEN_WITH_REPORTS_READ>' \
  https://api.example.test/api/reports/2026
```

After checking data permissions and business conditions, the endpoint can return **200 OK**. Values in angle brackets are placeholders, not usable tokens. In test environments, always use tokens issued by a valid Authorization Server.

### Special scenario: `permitAll()` with an invalid Bearer token still returns 401

With the same filter chain above, calling `GET /api/public` **without a token** can return 200 due to `permitAll()`. However, if an HTTP client automatically attaches `Authorization: Bearer <expired-token>` to that same public endpoint, `BearerTokenAuthenticationFilter` still attempts to validate the credential and can return **401** before the request reaches authorization.

**`permitAll()` does not automatically disable the Bearer authentication filter.** If an API area genuinely needs to skip Bearer processing completely, design separate `SecurityFilterChain`/matcher configurations. This is why HTTP clients that blindly attach expired tokens to every request can trigger unexpected errors on public routes.

## 7. Reading the `WWW-Authenticate` header

For the Bearer scheme, `WWW-Authenticate` is an important signal indicating the situation:

| Illustrative header | Meaning |
|---|---|
| `WWW-Authenticate: Bearer` | Prompts client to provide a Bearer credential; typically seen when no token was sent. |
| `WWW-Authenticate: Bearer realm="reports-api"` | Bearer challenge identifying a protection space. |
| `WWW-Authenticate: Bearer error="invalid_token"` | A token/credential was sent, but the token was rejected. |
| `WWW-Authenticate: Bearer error="invalid_request"` | Request transporting the Bearer credential is malformed. |
| `WWW-Authenticate: Bearer error="insufficient_scope"` | Token authenticated, but permissions are insufficient. |

Servers may append `error_description`, `error_uri`, or `scope` as appropriate. A JSON body is **not required** by Bearer challenges; an API may return an empty body, a custom error payload, or let a gateway alter the response. Therefore, clients should not classify errors solely from a JSON `message` field.

## 8. How clients should handle each case

### 8.1. No token

If an endpoint requires authentication, the client must obtain an access token using an appropriate OAuth 2.0 flow (such as Authorization Code + PKCE for user-facing apps, or Client Credentials for service-to-service when permitted). Then send the token via:

```http
Authorization: Bearer <access_token>
```

If the client insists it sent a token yet the API responds as if none was present, verify the header name, target URL, reverse proxy/gateway path, and whether `Authorization` is being stripped or overwritten.

### 8.2. Token present but `invalid_token`

- If the token is **expired**, run the refresh token flow if the client holds a refresh token and is permitted to refresh; retry with bounded attempts.
- If refreshing is not possible, re-run the appropriate login/token acquisition flow.
- If **wrong audience, issuer, or token type**, fix configuration and token issuance/selection flow. Refreshing repeatedly with the same broken configuration will not help.
- If the token was revoked, acquire a fresh credential per the issuer's policy.

Avoid a `401 → refresh → retry → 401` loop. When multiple concurrent requests hit expiration errors, coordinate refreshes to avoid simultaneous refresh storms, especially when refresh token rotation is enabled.

### 8.3. Valid token with `insufficient_scope`

This is an **authorization** failure, not an expired token. Determine which scope/authority the endpoint requires, what the token was granted, and what role/tenant/ownership conditions apply. Refreshing the current token will not grant new permissions; additional scopes or permission changes must be requested through a valid process.

Never fix `401` by disabling signature, issuer, expiration, or audience checks or relaxing API protection.

## 9. Diagnosing in Spring Security

| Symptom | What to check |
|---|---|
| No `Authorization`, login-protected endpoint returns 401 | Are `authenticated()`/scope rules applied? Is a Bearer challenge present? |
| Client sent token, response looks like missing token | Did the header reach Resource Server? Wrong header name, wrong scheme, gateway stripping header? |
| JWT repeatedly gets `invalid_token` | Issuer, JWKS, signature, `exp`, `nbf`, audience validator, and token type/profile. |
| Opaque token repeatedly rejected | Introspection endpoint/credentials, `active` result, and token attributes. |
| ID token accepted for API calls | Check for missing audience validation or missing access-token profile constraints. |
| Valid token returns 403 | Mapping `scope`/`scp` to `SCOPE_`, `hasAuthority()`, method security, and business permissions. |
| `permitAll()` still returns 401 when an old token is attached | Bearer filter is validating the attached request token before authorization runs. |
| 401 without `WWW-Authenticate` | Entry point configuration, response handler, API gateway/reverse proxy. |

Enable diagnostic logging in development environments:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Never print raw access tokens, ID tokens, or refresh tokens into logs. For observability, log request IDs, endpoint names, error categories, timestamps, and non-sensitive technical metadata. Set log levels and retention according to operational policy.

## 10. Common misconceptions

**“No token means invalid token.”** False: without a credential, nothing has been validated yet. Protected endpoints typically return a 401 challenge **without** `invalid_token`.

**“Any 401 means you must log in again.”** Incomplete: distinguish missing headers, expired tokens, wrong audience/issuer, or a gateway dropping headers.

**“Having an Authorization header means the Bearer resolver extracted a token.”** False: `Authorization: Basic ...`, malformed headers, or unconfigured mechanisms may not produce a valid Bearer credential.

**“Missing scope is invalid_token.”** False: an authenticated access token lacking permissions typically results in **403 insufficient_scope**.

**“`permitAll()` always ignores a broken attached token.”** False: in a filter chain handling Bearer auth, a bad attached token can be rejected before authorization runs.

**“Since both are JWTs from the same issuer, an ID token works for API calls.”** False: ID tokens are for OIDC Clients, whereas access tokens target Resource Servers. APIs must check tokens for the intended audience and purpose.

## 11. Request classification exercises

| Request / condition | Typical outcome |
|---|---|
| `GET /api/reports` without `Authorization` | **401**, Bearer challenge without error code. |
| `GET /api/reports` with expired JWT | **401 invalid_token**. |
| `GET /api/reports` with unexpired JWT but untrusted `iss` | **401 invalid_token**. |
| `GET /api/reports` with valid token lacking `reports:read` | **403 insufficient_scope**. |
| `GET /api/public` without token, `permitAll()` endpoint | May succeed. |
| `GET /api/public` with bad Bearer token, same filter chain | May return **401** before authorization. |
| Sending token in `X-Access-Token` when API only reads `Authorization` | Usually treated as **no Bearer token**. |
| Sending structurally malformed Bearer credential | May be rejected by resolver with `invalid_token` or `invalid_request` depending on error. |

## 12. Guiding principles to remember

With an API using Spring Security OAuth 2.0 Resource Server, inspect requests through four questions:

1. **Did the resolver detect a Bearer token?** If not, the request carries no Bearer credential; protected endpoints typically return a 401 challenge.
2. **Did the token pass authentication?** If not, it typically returns 401 with `invalid_token`, or the corresponding request syntax error.
3. **Does the valid principal/token have sufficient permissions?** If scope/authority is missing, it typically returns 403.
4. **Is the caller permitted to access that specific data?** Scopes are only one layer; tenant/ownership permissions and business policies must still be verified.

**Key takeaway:** *no token* means the Resource Server received no credential to authenticate; *token present but invalid* means a credential was sent and rejected. They can both return HTTP 401, yet differ in processing stage, Bearer challenge, and client remediation.
