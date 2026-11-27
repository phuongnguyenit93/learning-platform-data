# Handling Cache-Control, Sensitive Data, and Token Transport Over HTTPS

## 1. Why Must Protecting the Token Endpoint Be Part of the Design?

In a **Spring Security OAuth2/OIDC Authorization Server**, the **Token Endpoint** is where the application exchanges a valid grant for an **access token**, sometimes accompanied by a **refresh token** or **OIDC ID token**. Because these values grant API access or allow requesting further tokens, a mistake in transport, caching, or logging can be severe even when grants, JWT signatures, and client authentication are all implemented properly.

For example, `orders-bff` uses `client_credentials` via `POST /oauth2/token`. The HTTP 200 response carries a valid access token. If a CDN or reverse proxy caches responses by URL, or the application dumps the full JSON response into APM logs, the token can surface somewhere unauthorized parties can read it. If HTTPS terminates at the load balancer and the forward leg carrying the token to the backend traverses an untrusted network, the token can also be exposed in transit.

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we learn how to **design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot**. This lesson belongs to the **Token Endpoint** chapter and focuses on three pillars that must be implemented together:

1. **Prevent caching of sensitive responses:** use `Cache-Control: no-store` and `Pragma: no-cache` per OAuth 2.0.
2. **Prevent credential/token leakage:** control logs, traces, metrics, exceptions, request bodies, headers, backups, debuggers, and client token storage.
3. **Protect transport:** enforce **HTTPS/TLS**, verify server certificates, and secure internal hops behind proxies.

### Learning Outcomes

After this lesson, you will be able to:

- Explain the exact requirements from **RFC 6749 §3.2, §5.1, and §5.2** for the Token Endpoint and credential-bearing responses.
- Distinguish `no-store`, `no-cache`, and `max-age=0` from **token lifetime**.
- Design an end-to-end token protection flow from client → gateway → Authorization Server → client → Resource Server.
- Preserve safe header configurations in Spring Security/Spring Authorization Server and test both success and error responses when extensions exist.
- Isolate leakage vectors: query URLs, Basic auth, reverse proxies, logs/APM, JWT claims, browser storage, and test environments.
- Produce verification evidence for HTTPS, certificate validation, cache headers, and zero-leakage operation across multiple instances.

**Technical Scope:** examples target the **Spring Authorization Server 1.5.x / Spring Security 6.x / Spring Boot 3.x** family, noting API alignment when migrating to Spring Security 7.x. Illustrative snippets may require additional client registration, signing key, session, and database setup to form a runnable project.

## 2. Where Does the Token Endpoint Sit in the System?

In Spring Authorization Server, the default Token Endpoint path is typically **`/oauth2/token`**. It accepts token requests via **HTTP POST**, usually with `Content-Type: application/x-www-form-urlencoded`, and authenticates clients using their registered authentication method. The Token Endpoint is a **back-channel** leg between the OAuth client and the Authorization Server, distinct from browser redirects to the Authorization Endpoint.

```mermaid
flowchart LR
    B["Browser / user"] -->|"Authorization Code redirect"| RP["OAuth Client / BFF"]
    RP -->|"POST /oauth2/token<br/>grant + client authentication"| GW["TLS / Gateway / Reverse proxy"]
    GW -->|"Protected upstream channel"| AS["Spring Authorization Server<br/>OAuth2TokenEndpointFilter"]
    AS --> STORE[("RegisteredClientRepository<br/>OAuth2AuthorizationService")]
    AS --> GEN["OAuth2TokenGenerator<br/>JwtEncoder / key service"]
    AS -->|"Sensitive JSON response<br/>no-store / no-cache"| GW
    GW -->|"HTTPS response<br/>non-cacheable"| RP
    RP -->|"Authorization: Bearer access_token"| API["Resource Server API"]
```

**Three places to protect:** the request carrying a grant or secret; the response carrying tokens; and subsequent Resource Server requests carrying the access token. No single header or JWT signing key can protect everything if one of those three legs leaks data.

### 2.1. What Can Appear in the Request

| Grant / Method | Credentials or Sensitive Data in Token Endpoint Request | Notes |
| --- | --- | --- |
| `authorization_code` | Authorization code, `code_verifier`, redirect URI, client credentials (if confidential) | Short-lived, single-use code; `code_verifier` must stay secret until code exchange. |
| `refresh_token` | Refresh token, client authentication | Refresh tokens can obtain new access tokens; require strict protection. |
| `client_credentials` | Client secret, private-key JWT assertion, or client certificate per method | No end user, yet the access token is issued for the client itself. |
| Device Code grant | `device_code`, `client_id` / client authentication | Never send `user_code` by mistake to the Token Endpoint. |
| Token Exchange (if enabled) | `subject_token`, `actor_token`, or other credentials | Can hold another subject's token; high sensitivity. |

None of these parameters should ever be printed to the console "just for debugging." Even when URL-encoded, **URL encoding is not cryptographic encryption**.

### 2.2. What Can Appear in the Response

```http
HTTP/1.1 200 OK
Content-Type: application/json;charset=UTF-8
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_EXAMPLE_NOT_REAL",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

Depending on the grant, client type, and policy, the response may contain `refresh_token`. During an OIDC flow, the response may contain `id_token`. **Not every response includes every token type**; however, the presence of even one sensitive credential makes anti-caching protections mandatory.

## 3. Standard Rules: Cache-Control and Pragma

### 3.1. What Does RFC 6749 §5.1 Require?

RFC 6749 §5.1 states that the Authorization Server **MUST** include the following two response headers on responses containing tokens, credentials, or sensitive information:

```http
Cache-Control: no-store
Pragma: no-cache
```

Meaning:

- **`Cache-Control: no-store`:** instructs compliant caches not to store any part of the **request or response**. This is the primary directive preventing copies of access/refresh token responses from lingering in browser or proxy caches.
- **`Pragma: no-cache`:** compatibility header for legacy HTTP/1.0 caches. OAuth 2.0 still requires sending it alongside `Cache-Control`.

Spring Security may send **stricter or more detailed** cache-control values:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
```

Headers like those satisfy the OAuth requirement because they include the **`no-store` directive** and `Pragma: no-cache`. **The response does not have to match the exact string `Cache-Control: no-store`**; in tests, assert that the header contains the `no-store` directive along with the appropriate `Pragma` header.

### 3.2. `no-cache` Does Not Mean `no-store`

| Header / Directive | Purpose | Sufficient in Place of `no-store` on Token Responses? |
| --- | --- | --- |
| `Cache-Control: no-store` | Prevents compliant caches from storing request/response | **Yes** for preventing caching (must still send `Pragma` per RFC). |
| `Cache-Control: no-cache` | Caches may store, but must revalidate before reuse | **No**; a sensitive copy may still sit in cache storage. |
| `Cache-Control: private` | Shared caches may not store; private caches may store | **No**; browser/private caches may still retain the token. |
| `Cache-Control: max-age=0` | Marks response stale immediately for revalidation | **No**; does not prohibit storage. |
| `Pragma: no-cache` | Compatibility with legacy HTTP caches | **No**, if `no-store` is missing for modern caches. |
| `Expires: 0` | Signals immediate expiration under legacy cache rules | **No**; helpful, but does not replace `no-store`. |

**Key point:** `no-cache` means do not reuse without revalidation, **not necessarily do not store**. For credentials and tokens, always prioritize `no-store`.

### 3.3. Cache TTL Is Not Token TTL

Suppose an access token has `expires_in=600`, meaning a **10-minute** lifetime. That **does not allow** browsers or proxies to cache the token response for 10 minutes:

```text
Token lifetime (10 minutes):
    The token may be accepted by the Resource Server until expiration and per policy.

Cache-Control: no-store:
    Do not store a copy of the credential-bearing HTTP response in any cache.

Conclusion:
    An unexpired token DOES NOT mean the response may be cached.
    An expired token DOES NOT mean caches have purged the stored credential.
```

Likewise, `TokenSettings.accessTokenTimeToLive(...)` does not emit HTTP cache headers. Conversely, `Cache-Control: no-store` does not shorten token lifetimes or revoke tokens.

### 3.4. Which Responses Must Enforce This?

| Response | Requirement / Handling |
| --- | --- |
| Successful `authorization_code` | **MUST include `no-store` + `Pragma: no-cache`** because it carries access tokens/credentials. |
| Successful `refresh_token` | **MUST** because it carries tokens, possibly including a rotated refresh token. |
| Successful `client_credentials` | **MUST** because it carries an access token. |
| Successful Device Code / Token Exchange | **MUST** when the response contains tokens/credentials. |
| Errors `invalid_client`, `invalid_grant`, `invalid_scope` | Keep **`no-store`** and **`Pragma: no-cache`** across the entire Token Endpoint for defense in depth; RFC 6749 §5.1 mandates them on **responses containing sensitive data**, without implying bare error codes inherently contain tokens. |
| Introspection, revocation, discovery | Have their own endpoints/specs; configure caching by sensitivity. Never cite Token Endpoint rules to claim public discovery metadata cannot be cached. |

**Warning:** `invalid_client` errors can occur **before** the Token Endpoint authentication provider inside the client authentication filter. Therefore, header tests must cover error responses produced by **earlier filters** in the `SecurityFilterChain`, not just the Token Endpoint success handler.

### 3.5. Do Not Rely on Headers to Prevent Logging or Tracing

`Cache-Control: no-store` governs compliant HTTP caches; it **does not prevent**:

- Reverse proxies or API gateways from explicitly dumping request/response bodies to logs.
- Tracing agents from capturing `Authorization` headers, form parameters, or JSON responses.
- Applications from writing tokens into logs, metrics, error trackers, audit tables, or databases improperly.
- Debuggers, heap dumps, crash reports, or CI logs from retaining secrets in environment variables.
- Clients from saving tokens into `localStorage`, insecure cookies, or analytics tools.

These are **data-capture paths outside HTTP caching** and must be configured and tested independently.

## 4. Transporting Tokens Over HTTPS: Securing Every Hop

### 4.1. TLS Requirement for the Token Endpoint

RFC 6749 §3.2 requires the Token Endpoint to use **TLS** because credentials are exchanged there. Clients must verify the server certificate; RFC 6750 also requires protecting bearer tokens with TLS or equivalent transport security in transit.

**Never use plaintext HTTP** for a production Token Endpoint, even if every token is a signed JWT:

- A **JWT signature** protects integrity and authenticates the issuer—it **does not encrypt the payload**.
- **TLS** protects confidentiality and integrity of HTTP requests and responses in transit.
- **`client_secret_basic`** merely Base64-encodes client ID/secret; Base64 **is not encryption**.
- If a bearer token is intercepted, whoever holds it can call APIs within its scope unless the token is sender-constrained and the Resource Server enforces that binding.

```mermaid
flowchart TB
    subgraph CLIENT["OAuth2 Client / BFF"]
        C["HTTPS request<br/>client auth + grant"]
    end
    subgraph EDGE["Edge / TLS termination"]
        P["Reverse proxy / gateway<br/>No cache, no token logging"]
    end
    subgraph PRIVATE["Trusted backend segment"]
        A["Spring Authorization Server<br/>Token Endpoint"]
        K["Key management / HSM / secret store"]
        DB[("Authorization + client persistence")]
    end
    C -->|"TLS: certificate validated"| P
    P -->|"TLS/mTLS or protected private channel"| A
    A --> K
    A --> DB
    A -->|"no-store token response"| P
    P -->|"HTTPS encrypted response"| C
```

**An HTTPS request seen from the client alone does not prove the entire path is secure.** After TLS termination at the gateway, traffic may travel in plaintext over another network segment. Design transport protection around trust boundaries, network reachability, compliance requirements, and threat models.

### 4.2. Securing Upstream Connections Behind a Reverse Proxy

| Segment | Required Controls |
| --- | --- |
| OAuth client → edge / load balancer | HTTPS, valid certificate, hostname verification, policy-compliant TLS versions/ciphers |
| Edge → Authorization Server | Protected internal channel; prefer TLS/mTLS when trust boundaries require it; never send credentials across untrusted networks |
| AS → database / secret store | TLS and service authentication where supported, least-privilege access, secret/key rotation |
| Client → Resource Server | HTTPS for `Authorization: Bearer ...` and server certificate verification |
| Browser → Authorization / Verification Endpoint | HTTPS, `Secure`/`HttpOnly`/`SameSite` cookies as appropriate, CSRF and open-redirect protection |

**Never disable certificate validation** with `curl -k`, a "trust-all" Java `TrustManager`, or `InsecureSkipVerify` in production. When using an internal CA certificate, install the CA into a managed trust store; never bypass hostname verification.

### 4.3. HSTS, Issuer, and Forwarded Headers

- **HSTS** (`Strict-Transport-Security`) instructs browsers to remember HTTPS-only access for a securely visited host. HSTS is a helpful browser defense, **not a substitute for TLS verification** in non-browser OAuth clients.
- `AuthorizationServerSettings.issuer(...)` must advertise the **exact HTTPS issuer URL**, matching discovery metadata, JWT `iss`, JWKS, and Resource Server settings.
- Behind a proxy, configure forwarded-header processing **strictly from trusted proxies**. Never treat `X-Forwarded-Proto`/`Host` sent by an untrusted Internet client as ground truth to construct token endpoint URLs or issuers.
- When enforcing HTTPS, test actual behavior at both the public entrypoint and internal paths; never redirect `POST /oauth2/token` from HTTP to HTTPS and expect clients to handle it without having already exposed credentials on the first request.

Example declaring the public issuer:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .tokenEndpoint("/oauth2/token")
            .build();
}
```

This configures the issuer and endpoint paths—it **does not** enable TLS itself. HTTPS must be provided by Spring Boot's embedded server or a reverse proxy; configure real TLS outside this snippet.

### 4.4. Never Put Tokens in URLs or Redirects

**Unsafe patterns:**

```http
GET /oauth2/token?grant_type=refresh_token&refresh_token=SECRET HTTP/1.1
Host: auth.example.com
```

```http
GET /api/orders?access_token=SECRET HTTP/1.1
Host: api.example.com
```

URLs are routinely copied into **browser history, server access logs, proxy logs, telemetry, referrers, analytics, and monitoring dashboards**. RFC 6750 advises **against sending bearer tokens in URI query parameters**; the Token Endpoint must use POST per spec, and there is no valid modern design reason to place credentials in URLs.

For **Resource Servers**, use:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_EXAMPLE_NOT_REAL
```

Although bearer tokens in headers are strongly preferred over query parameters, **the header remains sensitive** and must be redacted from logs and traces. Never accept a token in a header and then forward it as a query parameter to a downstream backend.

## 5. Managing Sensitive Data at the Token Endpoint

### 5.1. Data Classification

| Value | Exposure Risk | Policy |
| --- | --- | --- |
| `client_secret` | Attacker can impersonate the confidential client at the Token Endpoint | Secret manager, hashed/encoded on registration, rotated, never logged |
| Private key / JWT client assertion | Client impersonation if key leaks or assertion remains valid | KMS/HSM, short assertion TTL, replay protection, never logged |
| Authorization code | Could be exchanged for tokens if other checks are bypassed | Single-use, short TTL, PKCE, never logged |
| `code_verifier` | Combined with authorization code, may suffice to exchange for tokens | Scoped to transaction, never sent via front-channel or logged |
| Refresh token | Mints new access tokens within granted scopes | Stored safely server-side when applicable, rotation/revocation, never logged |
| Access token | Grants API access while valid | Minimal scope/audience/TTL, protected in transit and storage |
| OIDC ID token | May carry user claims; lets clients verify user identity | Used only by OIDC clients, never log payload/PII claims |
| Device code / `subject_token` | Can be redeemed in specialized grants | TTL, binding, never exposed in UI or logs |
| Session cookie | Browser or BFF session hijacking if leaked | `Secure`, `HttpOnly`, `SameSite`, fixation/CSRF protection |

**Raw access tokens are not the only secrets to protect.** Refresh tokens, client assertions, private keys, PKCE verifiers, and authorization codes can carry equal or greater security impact.

### 5.2. Logging, Tracing, and Metrics

Separate three operational tiers:

**Safe to log (sanitized):**

- Timestamps, random request/correlation IDs, endpoint name, and **validated** grant type.
- Client ID under appropriate access controls (client ID is not a secret, though it may still be internal metadata).
- OAuth error codes (`invalid_client`, `invalid_grant`, `invalid_scope`), outcome, latency, and duration.
- Correlation hashes/IDs that do not allow reconstructing tokens, if needed for auditing and backed by properly designed HMAC/secret keys.

**Never log:**

- Full request or response bodies of `/oauth2/token`.
- Values of `Authorization` headers, `client_secret`, `refresh_token`, `access_token`, `code`, `code_verifier`, `device_code`, or client assertions.
- Raw query strings containing credentials, `Set-Cookie` headers, or session IDs.
- JWT claims containing sensitive PII, private JWKs, signing keys, or raw payload dumps.

**Check every layer:** Spring Boot application logs, Tomcat/Jetty access logs, ingress/gateway logs, load balancers, WAFs, service meshes, OpenTelemetry/Zipkin/Jaeger, APM vendors, Sentry/error trackers, reverse-proxy error pages, CI test reports, and support dumps.

Sample **credential-free** audit event:

```json
{
  "timestamp": "2026-11-16T09:10:00Z",
  "correlation_id": "req-a24e",
  "event": "oauth.token.grant",
  "grant_type": "client_credentials",
  "client_id": "orders-bff",
  "result": "success",
  "duration_ms": 42
}
```

If you need to trace an abused token, do not log raw bearer tokens claiming "only internal staff see logs." Use controlled token IDs or authorization IDs, or keyed HMAC correlation tags, and restrict log access and retention.

### 5.3. Why Enabling DEBUG Can Be Risky

Spring Security and Spring Authorization Server generally avoid printing credentials by design, **but** custom logging filters, interceptors, gateways, or HTTP client debug hooks can log full form bodies and authorization headers. Never assume "Spring's DEBUG logger is always safe" or "always leaks"—inspect actual output in tests.

Avoid these anti-patterns:

```java
// WRONG: can expose client_secret, refresh_token, or code_verifier.
log.debug("Token request: {}", request.getParameterMap());

// WRONG: exposes tokens and user data in the response.
log.info("Token response: {}", tokenResponseJson);

// WRONG: leaks Bearer / Basic credentials into error logs.
log.error("Authorization header was: {}", request.getHeader("Authorization"));
```

When debugging an incident, log **error types and correlation IDs**, never raw credentials. Do not rely on Java `toString()` of token-bearing objects in logs unless you have verified that sensitive fields are masked.

### 5.4. Protecting Tokens on the Client and in the Browser

- Confidential web clients/BFFs should keep OAuth tokens server-side and issue a hardened session cookie to the browser; avoid pushing refresh tokens into JavaScript.
- Public SPAs cannot safely keep static shared secrets; use Authorization Code + PKCE, strict token policies, and consider a BFF when handling sensitive data.
- For native apps, use platform-provided secure storage and never hard-code credentials into binaries.
- Never treat browser URLs, unguarded `localStorage`, or unprotected cookies as a "default secure vault" for refresh tokens.
- Minimize scopes, audiences, and token lifetimes; evaluate sender-constrained tokens (DPoP/mTLS) when required by the threat model, without treating them as an excuse to drop TLS.
- Never share tokens across separate clients/RPs merely because they share an Authorization Server.

## 6. Configuring Spring Security / Spring Authorization Server: Keep Safe Defaults

### 6.1. Request/Response Handling Classes

Per Spring Authorization Server 1.5.x docs, the Token Endpoint uses:

| Component | Responsibility |
| --- | --- |
| `OAuth2TokenEndpointFilter` | Receives Token Endpoint requests and delegates to `AuthenticationManager`. |
| `OAuth2AuthorizationCodeAuthenticationConverter` and peer converters | Converts POST form parameters per grant into `Authentication` objects. |
| `OAuth2AuthorizationCodeAuthenticationProvider`, `OAuth2RefreshTokenAuthenticationProvider`, `OAuth2ClientCredentialsAuthenticationProvider`, etc. | Validates grants/clients and coordinates token issuance. |
| `OAuth2AccessTokenResponseAuthenticationSuccessHandler` | Handles success and writes the token response. |
| `OAuth2ErrorAuthenticationFailureHandler` | Handles OAuth error responses. |
| `OAuth2TokenEndpointConfigurer` | Extension points for request converters, providers, and success/error handlers. |
| `SecurityFilterChain` / Spring Security Headers | Adds security response headers per config, including default cache-control headers. |

**Prefer keeping default success/error handlers and security headers.** If you replace a handler, test that JSON, HTTP statuses, OAuth errors, and cache headers remain compliant. A custom handler that writes JSON tokens but forgets `Cache-Control: no-store` introduces a vulnerability even if the token generator is solid.

### 6.2. Example SecurityFilterChain for the Authorization Server

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .headers(headers ->
            // Preserve Spring Security's cache-control headers.
            headers.cacheControl(Customizer.withDefaults()));

    return http.build();
}
```

This is a **filter-chain snippet illustrating cache-control**, not a complete Authorization Server. The app still needs a user/login chain, client repository, signing keys, authorization services, issuer, consent, and version-appropriate beans. Never make the entire `SecurityFilterChain` stateless if doing so breaks login/consent sessions at the Authorization Endpoint.

By default, Spring Security adds secure response headers (including `Cache-Control` with `no-store`, `Pragma: no-cache`, and `Expires: 0`), **unless you disable or overwrite them elsewhere**. Calling `headers.cacheControl(...)` here simply makes the intent explicit and is not strictly mandatory when defaults are intact.

**Do not do this:**

```java
// WRONG if this removes no-store on the Token Endpoint:
http.headers(headers -> headers.cacheControl(cache -> cache.disable()));

// Also avoid a custom filter/controller resetting the header like this:
response.setHeader("Cache-Control", "public, max-age=600");
```

If a custom filter or controller sets `Cache-Control` itself, Spring Security may **not overwrite** that header. Always inspect the final response from the client side through your proxy/gateway rather than relying solely on reading filter code.

### 6.3. Writing a Custom Token Response Handler Safely

When a custom success handler is unavoidable, minimal requirements are:

1. Run only after the provider validates the grant and client; never mint tokens in a `@RestController` bypassing validators.
2. Preserve standard OAuth response formatting (`access_token`, `token_type`, `expires_in`, `scope` when needed, `refresh_token`/`id_token` when applicable).
3. Enforce `Cache-Control: no-store` and `Pragma: no-cache` on the **final response**.
4. Never print or return internal details/stack traces; never place tokens into redirect URLs, cookies, or easily logged custom headers.
5. Test error handlers, content types, proxy header rewrites, non-cacheable responses, and concurrency.

Example **helper** when managing responses manually (not a replacement for default handlers):

```java
import jakarta.servlet.http.HttpServletResponse;

public final class SensitiveResponseHeaders {
    private SensitiveResponseHeaders() {}

    public static void apply(HttpServletResponse response) {
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");
        response.setHeader("X-Content-Type-Options", "nosniff");
    }
}
```

**Do not** attach this helper to the default Token Endpoint if responses are already compliant. If used in a custom handler, invoke it before the response commits and preserve infrastructure controls such as HSTS and certificate validation. A header helper neither creates HTTPS nor stops proxies from logging.

### 6.4. Distinguishing Back-Channel Endpoints from Login CSRF

The Token Endpoint serves machine-to-machine or client back-channel calls, not cookie-session HTML forms mutating browser state. Spring Authorization Server configures protocol endpoints and appropriate CSRF exemptions on its security chain. **Never disable CSRF globally across the whole application** just to make `POST /oauth2/token` succeed: doing so can strip protections from login/consent screens or cookie-based admin APIs.

Never configure CORS `*` allowing arbitrary frontends to call the Token Endpoint simply because token responses have `no-store`. **CORS does not replace client authentication, PKCE, `state`, or redirect URI validation**. If a public browser client genuinely requires CORS, allow only approved origins and test the flow end-to-end; never expect CORS to keep a client secret embedded in frontend JavaScript confidential.

## 7. Testing the Token Endpoint Over Real HTTP

### 7.1. Using Safe Fixtures

Prepare a client **dedicated to integration tests**, for example:

```text
client_id: orders-test-service
client_authentication_method: client_secret_basic
authorization_grant_type: client_credentials
scopes: {orders.read}
endpoint: https://auth.test.example/oauth2/token

Secrets and tokens:
    - fixture only, never use production credentials
    - never save to shared logs
    - never include in screenshots, debug output, or source control
```

Send a controlled POST request, **printing only headers** without printing the token-bearing JSON:

```bash
# Use only fake/test-only secrets in a dedicated test environment.
# Do not use -k/--insecure and do not auto-follow redirects.
curl --silent --show-error \
  --dump-header - \
  --output /dev/null \
  --request POST 'https://auth.test.example/oauth2/token' \
  --user 'orders-test-service:TEST_ONLY_SECRET' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode 'scope=orders.read'
```

**Expected:** the successful response uses HTTPS, `Cache-Control` includes the `no-store` directive, and `Pragma: no-cache` is present. `Content-Type` must indicate a JSON token response. In automated tests, verify status and response body via a client with redaction, never printing raw tokens to terminal or CI logs.

**Warning about curl:** `--user` puts credentials in command-line arguments, exposing them in process listings and shell history. This syntax is **purely illustrative for fixtures**; production or real-secret testing should use a client library fetching secrets from a vault/secret manager rather than embedding credentials in shell commands or committed scripts. Never run `--trace-ascii`, `-v`, or redirect response bodies into public logs when credentials are present.

### 7.2. Why Testing Through the Edge Matters

Tests against `localhost:9000/oauth2/token` can PASS while responses traversing a real proxy suffer from:

- A gateway rule overwriting `Cache-Control` with `public, max-age=...`.
- Stripping `Pragma` or security headers in the response pipeline.
- Caching every response on a misconfigured route.
- Logging response bodies in access logs, WAFs, or APMs for "incident analysis."
- Disabling TLS or certificate validation on an internal hop.

Always test the Token Endpoint through **both** the public issuer/edge and the architecturally permitted upstream path. **Never** check a header at `HttpServletResponse` alone while ignoring the final response leaving the gateway.

### 7.3. Do Not Use HEAD/GET to Test Token Issuance

The Token Endpoint processes grants via **POST**. A `HEAD /oauth2/token` or `GET /oauth2/token` returning 404/405/redirect proves nothing about cache headers on actual token responses. Use HTTP POST against test fixtures and inspect the real successful grant response; for negative tests, inspect real Token Endpoint errors.

## 8. Testing Spring Boot with MockMvc

### 8.1. Successful `client_credentials` Integration Test

Below is a **test skeleton** to complete in a Spring Boot integration test once the app provides:

- `spring-security-test`, `spring-boot-starter-test`, and MockMvc configuration.
- Authorization Server `SecurityFilterChain`, `RegisteredClientRepository`, and token generator.
- Test client `orders-test-service` with properly registered/hashed secret `test-secret`, grant `client_credentials`, and scope `orders.read`.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class TokenEndpointResponseSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulTokenResponseIsNotCacheable() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("orders-test-service", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "orders.read"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("no-store")))
            .andExpect(header().string(
                    HttpHeaders.PRAGMA, containsString("no-cache")))
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.access_token").isNotEmpty())
            .andExpect(jsonPath("$.token_type").value("Bearer"));
    }

    @Test
    void invalidScopeDoesNotExposeCredentialOrCacheableResponse() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("orders-test-service", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "orders.admin"))
            .andExpect(status().isBadRequest())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("no-store")))
            .andExpect(header().string(
                    HttpHeaders.PRAGMA, containsString("no-cache")))
            .andExpect(jsonPath("$.error").value("invalid_scope"))
            .andExpect(jsonPath("$.access_token").doesNotExist());
    }
}
```

This snippet intentionally **does not print token values**. It verifies Spring Test MVC response headers, **not** real network TLS or gateway caching rules. If your app customizes grant validation or uses a different Spring Boot/Spring Security version, adjust fixtures and assertions accordingly. This is sample code for learners, not executed inline.

### 8.2. Testing Error Responses at Different Stages

Include these cases:

| Request | Outcome to Verify |
| --- | --- |
| Valid Client Credentials | 200; JSON access token; `no-store` + `Pragma`. |
| `invalid_scope` | OAuth error JSON, no token; safe headers. |
| Wrong client secret | Client authentication rejected; safe headers even when handled **before the Token Endpoint provider**. |
| Missing `grant_type` | Appropriate request error; no credential/stack trace leaks. |
| Expired/reused `authorization_code` | `invalid_grant` or context-appropriate error; no token issued. |
| Revoked refresh token | Grant error, no new access token issued; safe headers. |
| Unsupported grant | `unsupported_grant_type`; no token issued. |
| HTTP GET instead of POST | No token issued; no unexpected redirect. |
| Token Exchange / Device Code if enabled | Success/error per profile; cache/security policies preserved. |

**Avoid false conclusions:** if a request is rejected at the client authentication layer before the grant validator runs, the test only proved **bad credentials are rejected**, not `invalid_scope` or token issuance logic. Give each case valid prerequisite fixtures so execution reaches the target branch.

### 8.3. Avoid Exact-String Header Assertions

Because Spring Security may emit:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
```

an assertion like `Cache-Control == "no-store"` can **falsely fail** even though the response is well protected. Assert the presence of the `no-store` directive instead of hard-coding an exact string. For strict checks, parse the directive list and reject conflicting gateway additions such as `public`.

### 8.4. MockMvc Is Not Real HTTPS Testing

`MockMvc` runs at the Servlet/test-context layer; even `request().secure(true)` only **simulates the request's secure flag** without performing a real TLS handshake. To verify HTTPS:

- Run a staging environment behind the real public TLS endpoint.
- Verify certificate chain, hostname, issuer, and cipher/TLS settings.
- Confirm HTTP requests are handled safely without transmitting credentials over plaintext HTTP.
- Verify upstream mTLS/TLS when required by the architecture.
- Inspect `no-store` headers on responses passing through the real ingress.

## 9. Controlling Reverse Proxies, CDNs, Gateways, and HTTP Caches

### 9.1. Which Paths Must Never Be Cached?

Endpoints **returning tokens or credentials** require special handling:

```text
POST /oauth2/token                    -> NO STORE
POST /oauth2/device_authorization     -> contains device_code/user_code: NO STORE
POST /oauth2/introspect               -> contains sensitive state/claims: strict cache policy
POST /oauth2/revoke                   -> protect request/response and logging, do not cache
GET  /oauth2/jwks                     -> public keys may use reasonable policy-based caching
GET  /.well-known/openid-configuration -> public discovery metadata may be cached carefully
```

This is **operational guidance**, not a claim that every endpoint above shares the exact Token Endpoint caching rule in OAuth specs. Do not accidentally disable JWKS/discovery caching globally and then blame the Token Endpoint for latency; conversely, **never enable caching across all `/oauth2/*`** just to optimize discovery/JWKS.

### 9.2. Gateway Rules to Verify

At proxies, CDNs, and gateways:

1. **Never cache** `POST /oauth2/token` or other credential-bearing protocol routes.
2. Preserve `Cache-Control: no-store` and `Pragma: no-cache` emitted by the AS.
3. Never write `Authorization` headers, request/response bodies, `client_secret`, or tokens to access logs.
4. Never enable "full request/response capture" on the Token Endpoint for APM or WAF without verified redaction.
5. Never build custom response caching keyed by `client_id`, `scope`, or a hash of grant parameters to "reuse tokens."
6. Enforce TLS upstream per trust boundaries; strictly control forwarded headers and host/issuer values.
7. Never turn backend failures into HTML error pages echoing raw URLs or credential headers.

**A standard CDN may not cache POST requests by default**, but that is never enough reason to omit `no-store`. Edge configs, plugins, or middleware can alter behavior; the RFC requires explicit headers independent of deployment assumptions.

### 9.3. Headers That Cannot Replace `no-store`

`Vary: Authorization`, `ETag`, and `Last-Modified` **are not solutions to prevent storing token responses**. They govern cache keying and revalidation and can still leave sensitive copies stored. For the Token Endpoint, keep responses **non-cacheable** and disable caching at the gateway as well.

## 10. Difference Between Token Transport and Token Usage

### 10.1. Issuing Tokens Safely at the AS Does Not Guarantee Safe Resource Server Validation

The Token Endpoint might issue an access token over flawless HTTPS with `no-store`, while a Resource Server still fails securely by:

- Accepting plaintext HTTP requests carrying bearer tokens.
- Failing to validate `iss`/`aud`/`exp`/scope, allowing tokens to be misused on the wrong API.
- Writing Bearer tokens into access logs.
- Accepting tokens from query strings or unprotected cookies.
- Skipping revocation checks when an API needs immediate revocation and relies solely on offline JWT verification.

**Protecting the Token Endpoint is necessary, not sufficient, for a secure OAuth deployment.**

### 10.2. Signed JWTs Are Not Confidential

JWS access tokens typically carry a **base64url-decodable** payload, which must never be treated as encrypted:

```text
header.payload.signature
```

The signature proves integrity and signing-key authenticity; it **does not hide** claims such as `sub`, `roles`, tenant, email, or permissions. Never place client secrets, passwords, refresh tokens, or unnecessary personal data in claims. TLS protects the JWT **in transit**, while storage and logging need their own protections.

Opaque/reference tokens do not expose readable claims directly from the token string, yet they remain **bearer credentials**; stealing the value is still dangerous if accepted by the Resource Server.

### 10.3. Sender-Constrained Tokens as Defense in Depth

**DPoP** (RFC 9449) and **OAuth 2.0 mutual-TLS client authentication / certificate-bound access tokens** (RFC 8705) reduce misuse if a raw token value is stolen. However:

- Not all clients, grants, and Resource Servers support them by default.
- Binding and proof must be verified at the appropriate endpoints.
- The Token Endpoint still requires TLS and `no-store`.
- An attacker who compromises the private key or device can still bypass sender constraints.

Never treat DPoP/mTLS as a replacement for short access token TTLs, minimal scopes/audiences, log redaction, and token revocation policies.

## 11. Incident Response Scenarios

### 11.1. Tokens Found in APM Logs

Suppose operations discovers `response.body.access_token` in a tracing record:

1. **Stop new capture immediately** or enable redaction at instrumentation/gateway layers.
2. Scope the exposed tokens, time window, affected grants/clients, and who had log access.
3. Revoke affected refresh tokens/authorization state and evaluate live access tokens.
4. For offline JWTs, **do not** assume deleting a DB row stops APIs immediately; use short TTLs, denylists, or introspection/state checks per policy.
5. Restrict retention and access to affected logs following incident/legal procedures rather than blindly destroying evidence.
6. Add regression tests confirming log capture excludes credential field names and values while keeping safe metrics intact.

`Cache-Control: no-store` remains mandatory, though it **does not fix** an APM agent explicitly copying response bodies.

### 11.2. Proxy Returns `Cache-Control: public` Even When AS Is Correct

Trace along the path:

```mermaid
flowchart TD
    U["Client observes response<br/>Cache-Control: public"] --> E["Gateway/CDN rule"]
    E --> F{"Does upstream call in test<br/>environment include no-store?"}
    F -->|"Yes"| P["Proxy modifies/overwrites header<br/>Fix rule, disable cache on /oauth2/token"]
    F -->|"No"| A["AS or custom success handler<br/>dropped security header"]
    P --> T["Retest final response via HTTPS edge"]
    A --> T
    T --> V["Verify no-store + Pragma<br/>and no cacheable public/max-age"]
```

Never skip inspecting the **final response**. Across multi-tier networks, ingress A might preserve the header while CDN B strips it.

### 11.3. Token Endpoint Responds Over HTTP on an Internal Network

First identify the trust boundary: who can connect to or observe the internal segment, whether traffic crosses network zones, whether a service mesh encrypts hop-to-hop, and whether traffic is mirrored/tapped. If security policy requires internal encryption, deploy TLS/mTLS properly—never "fix" failures by disabling server certificate verification.

**HTTPS at the edge alone does not automatically guarantee every internal hop is encrypted.** Document security boundaries and verify the real infrastructure.

### 11.4. Client Reports TLS Handshake/Certificate Errors

Never downgrade security with `curl --insecure` or a trust-all handler. Check hostname, certificate chain, CA trust store, certificate expiration, SNI, proxy interception, protocol/cipher compatibility, and system clock. Fix the configuration or certificates; never send refresh tokens or client secrets over plaintext HTTP "just to test temporarily."

## 12. Pre-Production Security Test Matrix

| ID | Component | Scenario | Expected Result |
| --- | --- | --- | --- |
| H01 | Token success | Valid `client_credentials` | `no-store` and `Pragma: no-cache`; not cached by gateway. |
| H02 | Token success | Valid authorization code exchange | Anti-cache headers present even when refresh/ID tokens appear. |
| H03 | Token success | Valid refresh token | Anti-cache headers; new refresh token never logged. |
| H04 | Token errors | `invalid_scope` | Proper error JSON; no token; safe headers. |
| H05 | Client auth error | Wrong client secret | No token; safe headers even when handled by client authentication filter. |
| H06 | Custom handlers | Replaced success/error handler | Preserves `no-store`/`Pragma`, compliant JSON and status. |
| H07 | Cache semantics | Response overwritten with `public`/`max-age` | Detected and fixed; token responses never cached. |
| H08 | TLS | Call Token Endpoint over valid HTTPS | Handshake, hostname, and chain verification succeed. |
| H09 | TLS | Expired/wrong-host/untrusted-CA certificate | Client rejects; certificate validation never disabled. |
| H10 | HTTP | Attempt POST over `http://` | No token issued over plaintext; never rely on redirecting credentials to HTTPS. |
| H11 | Reverse proxy | TLS edge → upstream | Internal path meets encryption and authentication policies. |
| H12 | Proxy headers | Client sends spoofed `X-Forwarded-Proto`/`Host` | Ignored/stripped by proxy; issuer/host/HTTPS policy unaltered. |
| H13 | URL query | Sending `refresh_token`/`access_token` in query | Token Endpoint does not accept credentials from query strings. |
| H14 | Logging | TRACE/DEBUG enabled on server/edge | No raw grant, `Authorization` header, or token response logged. |
| H15 | Tracing | APM instrumentation enabled | Header/form/body redaction works; no tokens in spans. |
| H16 | Metrics | Labels/tokens/correlation | Tokens/secrets never used as metric labels. |
| H17 | JWT claims | Issued token contains claims | No secrets or unnecessary PII; proper issuer/audience/scope. |
| H18 | Resource Server | API accepts bearer token | HTTPS only; checks signature/token, issuer, audience, expiry, and scope. |
| H19 | Multi-instance | Token Endpoint across multiple nodes | Consistent security headers and TLS policy; no configuration drift. |
| H20 | CI / test | Failing test prints HTTP body | Test runner/reports never output real tokens or secrets. |
| H21 | OIDC | Token response includes ID token | ID token transmitted over HTTPS with `no-store`; no PII claims logged. |
| H22 | Token Exchange | Subject/actor token in request | Source credentials never logged/copied; back-channel protected. |
| H23 | Session / CSRF | Token Endpoint works while login/consent stays protected | CSRF never disabled globally just for token POSTs. |
| H24 | Cache headers | `no-cache` alone without `no-store` | Test FAILS; `no-store` must be added. |
| H25 | Gateway | Cache disabled for token route while discovery/JWKS keep own policies | Token responses never reused across clients. |

### 12.1. Negative Tests Must Never Leak Credentials

Some HTTP test frameworks dump full requests and responses into assertion failure messages. When testing with client secrets or refresh tokens, use **test-only credentials** and consider redaction tools; never put production tokens into unit or integration tests. Never upload packet captures containing real credentials to public tickets merely to prove headers.

### 12.2. Release Evidence to Retain

Test artifacts should contain only **safe information**:

- Header captures showing `Cache-Control`, `Pragma`, HTTP status, and issuer URL without token bodies.
- Redacted TLS/certificate validation reports.
- Automated test results covering both success/error paths and gateway routing.
- Evidence that logging/tracing pipelines strip credentials and never record token endpoint bodies.
- Versions of Spring Boot, Spring Security, Spring Authorization Server, proxies, and relevant configurations.

Never attach an unredacted token JSON screenshot to "prove token issuance succeeded."

## 13. Practical Deployment Checklist

**Protocol & HTTP**

- [ ] Token Endpoint accepts POST with protocol-compliant format and client authentication per registration.
- [ ] Every token/credential response includes `Cache-Control` with `no-store` and `Pragma: no-cache`.
- [ ] Error responses preserve safe headers; error handlers never emit stack traces, tokens, or secrets.
- [ ] `no-cache`, `private`, and `max-age=0` are never used in place of `no-store`.
- [ ] Tokens are never issued via GET/query parameters or redirected to arbitrary URLs.

**TLS & Infrastructure**

- [ ] Public issuer and Token Endpoint use HTTPS; clients verify hostnames and certificates.
- [ ] TLS policy meets current standards; no trust-all clients exist.
- [ ] Reverse proxy, upstream, database, and secret manager hops are secured per trust boundaries.
- [ ] Gateways neither cache nor log full bodies/tokens and never overwrite `no-store`/`Pragma`.
- [ ] Forwarded headers and `Host` are trusted only from controlled proxies; HSTS is configured appropriately.

**Sensitive Data**

- [ ] Client secrets, refresh tokens, codes, verifiers, assertions, and access tokens are protected in transit and storage.
- [ ] Shared secrets are never embedded in public frontends or mobile binaries.
- [ ] Application logs, proxy logs, APM/traces, metrics, and test reports have verified redaction.
- [ ] Token scopes, audiences, and TTLs are minimized; JWTs contain no secrets or unnecessary PII.
- [ ] Processes exist for credential rotation, token/authorization revocation, and token leakage incident response.

**Testing & Operations**

- [ ] Automated tests verify success/error paths, required headers, and zero tokens on errors.
- [ ] Real HTTPS tests through the edge and certificate-failure tests are run; `MockMvc` is not treated as TLS proof.
- [ ] Tested custom handlers, multiple `SecurityFilterChain`s, multi-node setups, and gateway rules.
- [ ] Release evidence contains no credentials; monitoring uses safe correlation IDs.

## 14. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "Signed JWTs don't need HTTPS." | A JWT signature does not encrypt the request, response, or claims. |
| "`Cache-Control: no-cache` means do not store." | Caches may store and revalidate; you must use `no-store`. |
| "`max-age=0` is enough for OAuth token responses." | Does not forbid storage; the RFC requires `no-store` and `Pragma`. |
| "If access token TTL is 10 minutes, caching the response for 10 minutes is fine." | Token TTL and HTTP cache TTL are independent mechanisms. |
| "Token Endpoint uses POST, so it can't be cached." | Custom cache middleware may still cache it; explicit headers and gateway policies are required. |
| "The gateway uses HTTPS, so the AS is definitely encrypted on every hop." | You must verify upstream hops after TLS termination as well. |
| "`client_secret_basic` is Base64-encoded, so it's safe over HTTP." | Base64 is encoding, not confidentiality. |
| "With `no-store`, APM won't record tokens." | Cache headers do not govern logs or tracing; explicit redaction is needed. |
| "Logging only request form parameters won't leak tokens." | `refresh_token`, `code`, and `code_verifier` all live in the form body. |
| "Printing `toString()` on OAuth objects is always safe." | Verify actual masking/redaction; never assume it is safe. |
| "`MockMvc.secure(true)` proves TLS certificates work." | It only sets a mock request attribute without a handshake. |
| "Disabling CSRF so Token Endpoint POSTs work is fine." | It can break protections on login, consent, and admin endpoints. |
| "CORS `*` lets a public SPA send a secret safely." | CORS never keeps secrets embedded in JavaScript confidential. |
| "If the token isn't in the URL, logging is always safe." | Headers, bodies, and traces can still contain tokens. |
| "Spring Security adds headers by default, so proxy tests aren't needed." | Custom filters or gateways can strip or overwrite them; always inspect final responses. |

## 15. References

- [RFC 6749 §3.2 — Token Endpoint](https://www.rfc-editor.org/rfc/rfc6749#section-3.2): Token Endpoint, HTTP POST, TLS requirement, and client authentication.
- [RFC 6749 §5.1 — Successful Response](https://www.rfc-editor.org/rfc/rfc6749#section-5.1): requirement for `Cache-Control: no-store` and `Pragma: no-cache` on responses containing tokens, credentials, or sensitive info.
- [RFC 6749 §5.2 — Error Response](https://www.rfc-editor.org/rfc/rfc6749#section-5.2): OAuth error JSON and error codes at the Token Endpoint.
- [RFC 6750 §2 and §5 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer tokens via `Authorization` header, TLS requirement, and URI query leakage warnings.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): modern OAuth requirements/recommendations on authorization, tokens, redirects, and client security.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): semantics of `no-store`, `no-cache`, `private`, and cache directives.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens when deployed.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): mTLS client authentication and certificate-bound access tokens.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2TokenEndpointFilter`, converters/providers, and response handlers.
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` and security filters.
- [Spring Security — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): cache-control defaults and customization/overriding.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): API-side JWT validation, issuer, and signature checks.

**Conclusion:** **The Token Endpoint is a sensitive credential-exchange boundary**, so a sound implementation goes beyond validating grants and signing JWTs—it must protect **responses from HTTP caching**, protect **requests and responses from uncontrolled logging/tracing**, and enforce **HTTPS/TLS across every trust boundary**. In Spring Authorization Server, keep default security headers and handlers wherever possible, customize only with tests proving `no-store` and `Pragma: no-cache` remain intact, and verify both real edge responses and Resource Server token consumption.
