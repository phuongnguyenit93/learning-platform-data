# LDAP, Certificate, Issuer, or JWK Errors Mistaken for Wrong Password

## 1. Scenario: User Reports "Wrong Password," Yet the Cause Lies in the Authentication System

A Spring Security application can use multiple authentication mechanisms: form login against LDAP, client-certificate authentication over TLS/X.509, OAuth2/OIDC login from an Identity Provider (IdP), or an OAuth2 Resource Server verifying JWTs from an Authorization Server. When errors occur, the UI often shows only "Sign-in failed" or clients receive HTTP 401. That **does not prove the password was wrong**.

Completely different failures can produce the exact same user experience:

- LDAP server is unreachable, connection pool exhausted, DNS failed, StartTLS failed, or the LDAPS certificate expired.
- User exists, yet DN mapping, group search, referral, or locked account settings mismatch configuration.
- mTLS rejects the client certificate **before the request reaches Spring Security**; the app might not even see an HTTP request.
- Client certificate is valid at TLS, yet X.509 principal extraction fails to extract the right user, or the app finds no matching account mapping.
- Access JWT is structurally valid yet rejected because `iss`, `aud`, `exp`, `nbf`, `alg`, signature, or public key does not match.
- JWK Set endpoint has the wrong URL, is unreachable, has TLS/DNS errors, an overly stale cache, or the IdP is rotating `kid` keys.
- Frontend sends an **ID token** instead of an **access token** to the API, or a token issued by a different environment.
- Authentication actually succeeded, yet authorization lacks a role/scope, yielding 403 while the UI still says "wrong password".

This lesson belongs to the **Diagnostics** section of **Spring Security - authentication**. The goal is to distinguish **genuinely invalid credentials**, **identity/policy errors**, **infrastructure/trust errors**, **token verification errors**, and **authorization errors**, without leaking sensitive data.

**Overarching principle:** external responses may be normalized to prevent username enumeration; however, **internal, scrubbed** logs/metrics/traces must categorize failures clearly. Never use an HTTP status code or a single `BadCredentialsException` string as the root-cause conclusion.

## 2. Decision Diagram to Avoid Misdiagnosis

```text
Authentication request failed
        │
        ├─ Did the request reach the application?
        │    ├─ NO  → check TLS handshake, mTLS, reverse proxy/WAF,
        │    │        certificate chain, SNI, routing, ingress logs
        │    └─ YES
        │
        ├─ Which mechanism is handling the request?
        │    ├─ Form / LDAP → user search, bind/compare, LDAPS,
        │    │                DNS/connectivity, account policy, groups
        │    ├─ X.509       → did the certificate reach the Servlet?
        │    │                subject regex, account mapping, authorities
        │    ├─ OAuth2/OIDC login → authorize/callback, state/nonce/PKCE,
        │    │                      TLS/issuer/IdP metadata, ID token
        │    └─ Bearer JWT API → token format, decoder, iss/aud/time,
        │                        signature, kid/alg/JWK cache/endpoint
        │
        ├─ Authenticated yet missing privileges?
        │    └─ YES → check 403, role/scope/tenant, do not blame password
        │
        └─ Only after ruling out all layers above, conclude
           the credential/password was genuinely invalid
```

Start by asking **"which layer did the request reach?"** instead of automatically resetting user passwords. TLS handshake results, LDAP connection info, `JwtDecoder` traces, or gateway statuses pinpoint the failing layer without looking at raw passwords/tokens.

## 3. Quick Diagnostic Matrix by Mechanism

| Observation | Do Not Conclude | Reliable Check | First Action |
| --- | --- | --- | --- |
| Form login always redirects to `/login?error` | User typed wrong password | LDAP bind/search, service exception, directory status | Correlation ID + log category |
| Errors start right after LDAP certificate changed | Everyone forgot passwords | LDAPS trust chain, hostname, expiry, JVM truststore | Safe TLS/DNS check |
| LDAP returns `49 invalidCredentials` | Password definitely wrong | DN, account lock/expiry, vendor-specific subcodes | Cross-check directory policy |
| mTLS request never appears in access log | Spring failed to read user/password | TLS handshake / proxy client-cert verification | Inspect ingress/TLS logs |
| X.509 request has cert yet app does not log in | Certificate definitely invalid | Subject extraction, principal mapping, `UserDetailsService` | Inspect post-TLS mapping |
| JWT API returns 401 with unexpected `iss` | User logged in wrongly | Issuer string and token origin | Compare exact issuer |
| Only tokens signed by new key return 401 | User gave bad credentials | Does JWK Set have new `kid`, cache/rotation state? | Inspect trusted JWKS |
| 401 during IdP/JWKS DNS timeout | Password expired | Egress/DNS/TLS/JWKS availability | Check dependencies |
| Valid token yet API returns 403 | JWT/password rejected | Authority/scope/tenant | Verify authorization |
| Test `jwt()` passes yet production returns 401 | Production "wrong password" | Test bypassed real `JwtDecoder` | Integration-test signature/issuer/aud |

**Note:** HTTP 401 indicates only a requirement for valid protocol authentication; it does not identify a password error. With mTLS, handshake failures can yield **no HTTP status at all**; error reporting and logging depend on the proxy, TLS stack, and client.

## 4. Spring Security Separates Authentication and Authorization Into Layers

A Servlet application typically has `FilterChainProxy` selecting a `SecurityFilterChain`, then authentication filters such as `UsernamePasswordAuthenticationFilter`, `X509AuthenticationFilter`, or `BearerTokenAuthenticationFilter`.

```text
Client
  │
  ├─ TLS / mTLS ──> reverse proxy/ingress/Tomcat
  │                    │ handshake can fail here
  │                    ▼
  └────────────── HTTP request
                       │
                       ▼
                FilterChainProxy
                       │
             matching SecurityFilterChain
                       │
            Authentication filter/provider
                       │
                AuthenticationManager
                       │
              UserDetails/LDAP or JwtDecoder
                       │
                authenticated principal
                       │
                AuthorizationFilter
                       │
             200 / 401 / 403 / redirect
```

Do not confuse:

- **Authentication failure:** identity cannot be established or credentials are invalid. A rejected Bearer access token can produce `401 WWW-Authenticate: Bearer`.
- **Authentication service failure:** LDAP/JWKS or trust infrastructure cannot be reached; responses may be 401, redirects, 5xx, or custom handler outputs. **There is no single uniform default status** across all providers.
- **Authorization failure:** identity is authenticated yet lacks permission, usually 403.
- **Transport failure:** TLS/mTLS handshake fails; the app does not necessarily receive an HTTP request and Spring Security may emit no events.

If the frontend collapses every status into "Wrong password", users suffer and operations loses visibility into infrastructure. Keep UX safe while classifying internally by true source.

## 5. LDAP: Wrong Password Differs From Connection, Bind, Search, and Directory Permissions

Spring Security LDAP supports multiple strategies. With **bind authentication**, the app delegates credential verification via an LDAP bind on the DN; with **password comparison**, the provider compares passwords via attribute/LDAP compare per config. Common steps:

1. Normalize/validate the username (never turn user input into an unescaped LDAP filter).
2. Resolve the DN via a pattern or user search; wrong DN mapping causes user-not-found.
3. Connect to the directory over LDAP/LDAPS/StartTLS and perform bind or compare.
4. Load groups/authorities via `LdapAuthoritiesPopulator` if needed.
5. Build `Authentication` and save context/session via Spring Security on successful web login.

**LDAP 49** is the directory's `invalidCredentials` result, yet **does not necessarily prove** the user mistyped their password. It can stem from a wrong DN, account policy, bad service-account bind, or vendor-specific error encoding. For example, Active Directory embeds subcodes in the message like `52e` (credential mismatch), `533` (disabled), `775` (locked), `701` (expired). **Those subcodes are AD-specific, not universal across LDAP servers**, and must never be exposed on the login UI.

### 5.1. LDAP Error Categories Table

| Category | Possible Symptoms | What to Check |
| --- | --- | --- |
| Invalid credentials/bind | LDAP result `49`, `BadCredentialsException` | Password, DN pattern, user mapping, directory-specific policy |
| User not found | Search returns 0 entries; `UsernameNotFoundException` may be masked | Search base/filter, OU, UPN/uid, escaping |
| Directory unavailable | `CommunicationException`, timeouts, `ServiceUnavailableException`, or wrappers | DNS, firewall, port, pool, server availability |
| LDAPS/StartTLS trust failure | `SSLHandshakeException`, `PKIX path building failed`, hostname mismatch | Truststore, certificate chain, SAN, CA, expiry |
| Service bind account error | Search uses invalid bind DN/password | Secret rotation, search permissions, account lock |
| Bad LDAP referral or loop | Referral exceptions, queries crossing domains | Referral policy, domain topology, safe URIs |
| Group/authority lookup error | User bind succeeds yet groups are empty/failing | Group base, member filter, nested groups, access rights |
| Pool exhaustion / intermittent network | High p99 login latency, timeouts, max connections | Pool size, timeouts, load, retries/health checks |

**Never fix an LDAP outage by skipping password checks**, disabling LDAPS validation, or setting `authenticated=true`. When identity cannot be verified reliably, fail closed with a generic message or contract-appropriate service status.

### 5.2. Concrete LDAP Diagnostic Sequence

Suppose Alice logged in fine yesterday, and today every user gets "Invalid username or password":

1. Check failure volume over time: did it spike across many accounts at once or just one?
2. Verify directory hostname/IP/port, DNS resolution, and any certificate/CA or service-secret changes.
3. Inspect server logs after PII scrubbing: `javax.naming.CommunicationException`/`SSLHandshakeException` differs from LDAP 49.
4. Test LDAPS connectivity from **the application's own network namespace/pod**, not only an admin laptop.
5. If connectivity works, check service-account search permissions, DN pattern/user base, and bind flow.
6. If password bind succeeds yet roles are missing, inspect group mapping and authorization; it may be HTTP 403 rather than a bad login.
7. Restore login only after verifying upstream identity dependencies and safe policy enforcement.

Even when only a single account fails, do not assume a wrong password automatically: the user may have moved OUs, been locked/disabled, had their password expire, hit logon-hours policy, or triggered a referral.

## 6. LDAP Search/Bind: Three Spots Often Mistaken for Passwords

### 6.1. DN Pattern Does Not Match the LDAP Tree

For instance, the config sets `uid={0},ou=people` while the account moved to `ou=employees`. The user enters the right password, yet binding to a nonexistent DN still fails.

**How to diagnose:** using an authorized lab account, search for the entry under the configured base/filter via a safe LDAP tool; compare relative DNs against Spring's `BaseLdapPathContextSource` base DN. Never print full customer DNs into public logs.

### 6.2. Service Account Used for Search Fails

In search-before-bind, the app may need a service DN authorized to read account metadata. If that service DN's password expires or rotates incorrectly, **all users** fail even with right passwords. The fix is managing the service account's secret/health, **not** telling every employee to reset their password.

### 6.3. Group Search Breaks After Bind

The user authenticates their identity cleanly, yet `LdapAuthoritiesPopulator` finds no groups, leaving them without `ROLE_EMPLOYEE` or `ROLE_ADMIN`. If the app returns 403 while the UI shows "Wrong password", that is a classification bug between authentication and authorization.

**Check:** is `Authentication.isAuthenticated()` true? Does `getAuthorities()` have the expected roles? Nested groups, member attributes, group DN bases, and mapping prefixes must align. Never auto-grant default `ADMIN` roles when group lookup fails.

## 7. LDAPS/StartTLS: Server Certificates Failing Before Password Verification

LDAP can use TLS in two ways:

- **LDAPS** starts TLS immediately upon connecting, typically on port 636.
- **LDAP + StartTLS** starts on the plain LDAP port (typically 389) and upgrades the connection to TLS.

In both, the Java client must trust the directory's certificate chain and verify hostnames per configuration. When a CA rotates, a certificate expires, SAN lacks the service DNS name, or the JVM truststore is outdated, LDAP bind fails before ever checking passwords.

Java logs typically show `javax.net.ssl.SSLHandshakeException`, with root causes involving `sun.security.provider.certpath.SunCertPathBuilderException`, `CertificateExpiredException`, or hostname verification. **Exact exception names vary by JDK, provider, driver, and TLS termination point**; avoid rigidly searching for only one string.

### 7.1. Safe Inspection Procedure

1. Take the exact LDAP hostname from managed config and compare against the server certificate's SAN.
2. Check system clocks on app pods/LDAP server; clock skew affects certificate validity.
3. Inspect the chain presented by the server (root/intermediate) and CAs trusted by the JVM truststore.
4. Check pod egress permissions, DNS, and firewalls; timeouts are not expired certificates.
5. If only one node fails, compare JDK versions, truststores, container images, and mounted CA bundles across nodes.
6. Fix CA/hostname/chain via approved change procedures; never set `trustAll`, disable hostname verification, or downgrade to plaintext LDAP to "fix" login.

Tool to check the **server connection's** certificate in an authorized environment:

```bash
openssl s_client \
  -connect ldap.example.test:636 \
  -servername ldap.example.test \
  -showcerts -verify_return_error
```

This observes the handshake; evaluate results against the app's JVM truststore. OpenSSL succeeding on a laptop does not guarantee the container JVM trusts the same CA. Never include private keys or passwords in output/issue tickets.

### 7.2. The JVM Truststore Is a Deployment Artifact

Some teams update CAs on the Linux host while the Java app uses a separate JDK/container truststore. Check `javax.net.ssl.trustStore`, truststore type, JDK CA bundle, and actual mounted files. Never store truststore passwords in code, env dumps, or logs. Always use public/internal CA certificates approved by infrastructure teams; never add arbitrary certificates just to "make the test green".

## 8. X.509/mTLS: Client Certificate Errors Are Not Wrong Passwords

With **mutual TLS (mTLS)**, the server/proxy demands a **client certificate**, verifying the trust chain and constraints before (or while) forwarding the HTTP request to the app. Spring Security provides `x509()`/`X509AuthenticationFilter` to read the TLS-verified certificate and map it to a principal/application user.

There are at least two completely different branches:

### 8.1. Handshake Fails at Ingress/Proxy/Container

The client sends an expired certificate, one untrusted by the CA, wrong key-usage policy, omits a certificate when required, or TLS negotiation fails. Application controllers/filters may **never see the request**; Spring has no data to throw `BadCredentialsException` for a "password".

```text
Client -- TLS ClientHello / Certificate -->
Ingress/Proxy -- verify client certificate -->
    FAILURE: TLS alert / connection aborted
    (no HTTP response from app)
```

If the proxy is configured for optional client-cert verification or returns its own HTTP error, behavior differs. **Do not claim every mTLS error must be HTTP 401/403**, since many fail before HTTP.

### 8.2. Handshake Succeeds, Yet App Cannot Map Principal

A TLS client certificate trusted by the truststore does not automatically guarantee a matching app account. `X509AuthenticationFilter` typically extracts a principal (e.g., regex on subject DN, defaulting to CN in some configs) and calls `UserDetailsService`/provider to load authorities. Mapping failures cause authentication to fail even without a password.

Check:

- Does the actual cert reach Servlet attribute `jakarta.servlet.request.X509Certificate`? Does ingress forward cert info under a trusted contract?
- Does Subject DN contain the expected field? Do `CN`, SAN/UPN/email, and application identifier actually align?
- Does the extraction regex match multiple fields or map to the wrong account?
- Is the mapped user active/allowed with the needed authorities?
- Does the proxy strip/spoof-protect headers before injecting client cert info? **Never trust certificate headers set by Internet clients themselves.**

**Spring Security 6.x Servlet** config example, placed only in a `SecurityFilterChain` dedicated to mTLS endpoints:

```java
http
    .securityMatcher("/mtls/**")
    .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
    .x509(Customizer.withDefaults());
```

This is a **DSL snippet**, omitting mTLS proxy/connector, user store, and trust setup. **Enabling the `x509` filter does not turn on mTLS handshakes by itself**; the server/ingress must verify the certificate first. If the backend receives raw HTTP from the Internet, never accept `X-Client-Cert` from unprotected headers.

## 9. Diagnosing mTLS Without Exposing Private Keys

In an authorized lab environment, verify the client cert and handshake at the exact ingress users traverse:

```bash
openssl x509 -in client-lab.crt -noout \
  -subject -issuer -dates -ext extendedKeyUsage
```

Confirm the certificate is unexpired, has the right issuer, identifies the right subject/SAN, and meets EKU policies. Exact output varies by OpenSSL version; avoid pasting full certificate chains containing PII into tickets unnecessarily.

To test the client-authentication handshake:

```bash
openssl s_client -connect api.example.test:443 \
  -servername api.example.test \
  -cert client-lab.crt -key client-lab.key \
  -verify_return_error
```

**Never print, upload, or commit `client-lab.key`**. Use test keys with minimal read permissions and delete per policy. Compare handshake results with ingress logs: if requests never reach the app, look at the TLS/proxy layer instead of turning on DEBUG across all of Spring Security hunting for a nonexistent event.

### 9.1. Difference Between Server Certificates and Client Certificates

- **Server certificate** proves the HTTPS/LDAPS endpoint is the right server, normally verified by the client.
- **Client certificate** in mTLS proves the client possesses the private key matching a certificate accepted by the server.

These are two opposite trust directions. Fixing the server's truststore does not fix a client rejecting the server's cert; conversely, importing a client CA on the server does not make the client trust the server's cert. Pinpointing the **exact verification point** is mandatory.

## 10. OAuth2 Resource Server: Bearer Token Errors Are Unrelated to Passwords

With Spring Security Resource Server, API requests usually send:

```http
GET /api/reports HTTP/1.1
Authorization: Bearer eyJ...<redacted>
```

**The snippet above is a protocol illustration**; never put real raw tokens into logs or docs. `BearerTokenAuthenticationFilter` extracts the token, `JwtAuthenticationProvider` calls `JwtDecoder`, and Spring verifies signature, `exp`/`nbf`, `issuer`, and configured validators. Only valid tokens map to `JwtAuthenticationToken` and scopes/authorities.

Possible causes of 401:

- Missing token or malformed `Authorization` header.
- Token is not valid JWT structure, malformed base64url/JSON, or bad signature.
- Token expired (`exp`), not yet valid (`nbf`), or server clock skew exceeds allowance.
- `iss` does not equal the trusted issuer, including mismatched host/path/trailing slash.
- `aud` lacks the expected API audience; the token may belong to another service.
- Signature algorithm `alg` is not in the trusted list, or JWK lacks a matching key.
- Token was signed with a new `kid` not yet present in the JWK Set/cache.
- JWK endpoint has DNS/TLS/timeout errors, or IdP metadata discovery is unreachable.

The user **may have logged into the IdP with the exact right password**. The Resource Server still rejects the **access token** due to invalid trust/claims/signature. Resetting the password will not fix a wrong `iss` or stale JWK cache.

### 10.1. 401 and 403 Mean Different Things

| Situation | Typical Expectation |
| --- | --- |
| Missing Bearer token on protected API | `401` + `WWW-Authenticate: Bearer` |
| JWT bad signature / wrong issuer / expired | `401`, Bearer challenge may include `invalid_token` |
| Verified JWT yet missing `SCOPE_reports.read` | `403`, may include `insufficient_scope` |
| JWT decoder cannot fetch JWK/metadata | Depends on version, exception/handler; may be 401 or 5xx |
| TLS error between Resource Server and IdP/JWKS | Outbound HTTP/TLS failure; needs internal dependency diagnostics |
| Client-credentials access token lacks user permissions | Does not automatically carry human MFA/identity |

**Do not use 401 to conclude a token had a wrong password.** Access JWTs are issued by the Authorization Server after prior user/client authentication. The Resource Server validates tokens; **it does not re-check the user's password**.

## 11. Issuer: Even a Single-Character Difference Fails

In JWTs, `iss` identifies the issuer. When configured with `issuer-uri`, Spring Security verifies the token came from that trusted issuer. For example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/finance
```

Token carries:

```json
{
  "iss": "https://idp.example.test/realms/sales",
  "sub": "user-123",
  "aud": ["finance-api"],
  "exp": 1893456000
}
```

Even if the signature verifies against a key in the IdP's JWKS, a token with `iss` for the `sales` realm instead of `finance` must be rejected under trust policy. **Never** broaden `issuer-uri` to a shared root host or drop the issuer validator just to let tokens pass.

Real-world causes of issuer mismatch:

1. Frontend logged into staging yet called the production API.
2. Multiple realms/tenants share an IdP host; token carries another realm's path.
3. Reverse proxy alters public vs internal URL, making the IdP emit an `iss` not matching client config.
4. Differences in trailing slashes, URL encoding, casing, or `http`/`https` scheme.
5. Resource Server points to another issuer's metadata endpoint/JWK URL.
6. Client confuses an **ID token** (whose audience is the OAuth client ID) with an **access token** meant for the API.

**Diagnosis:** compare the expected issuer with AS config and **test-token claims in a controlled environment**. Never copy real users' raw JWT payloads into logs/tickets. JWT claims are **untrusted data** prior to signature verification; never use them to dynamically pick an arbitrary issuer/JWKS.

## 12. JWK Set, `kid`, `alg`, and Key Rotation

Asymmetrically signed JWTs carry an issuer-generated header such as:

```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-11"
}
```

**Attributes to understand:**

- `alg`: signature algorithm. The Resource Server must restrict to trusted algorithms; never trust the `alg` header to override policy.
- `kid`: key identifier **hinting** which public key to pick in the JWK Set; it does not prove the key or issuer is valid.
- `jwks_uri`: endpoint in issuer metadata serving public signing keys; URL paths vary by IdP.
- JWK public fields like `kty`, `n`, `e` (RSA) or `crv`/`x`/`y` (EC), `use`, and `key_ops`: help select the right key.
- `exp`/`nbf` and `iss` are JWT payload **claims**, distinct from public key fields.
- Private signing keys stay on the Authorization Server/HSM; the Resource Server needs only **public keys** and trust policy.

When the AS rotates keys:

```text
T0: JWKS = {kid: K1}             New tokens signed with K1
T1: JWKS = {kid: K1, kid: K2}    Publish K2 before or at switch time
T2: AS issues new tokens with K2 Resource Server must find K2
T3: JWKS drops K1 after old tokens expire per policy
```

If the AS deletes K1 too early, valid older tokens fail. If the AS starts signing with K2 before JWKS/CDN/caches have K2, new tokens get 401. This is a **key-rotation coordination issue**, not a wrong password. When `kid` is not found, decoders may re-fetch JWKS depending on cache/provider, yet that does not guarantee all caches/proxies sync instantaneously.

### 12.1. Never "Fix" by Disabling Signature Verification

Dangerous workarounds to avoid:

- Accepting `alg=none` or picking secrets from a client-controlled JWT header.
- Base64-decoding the token and trusting unverified `sub`/`role` claims to grant access.
- Fetching JWKS from a URL specified inside the token/client request (SSRF/key-substitution risk).
- Dropping issuer/audience validators so tokens from any realm/service pass.
- Pinning a single public key forever without a key-rotation plan.
- Logging raw Bearer tokens to "inspect easily".

The rule is **fix issuer/JWK metadata, truststores, caches, and AS rotation properly**, never lower verification standards.

## 13. JWK Endpoint Network/TLS Errors: A Separate Infrastructure Branch

The Resource Server must retrieve keys to verify signatures. When the JWK Set URL:

- Returns 404 due to wrong configured path.
- Returns 5xx during an IdP outage.
- Has an expired TLS certificate or CA not yet trusted by the JVM.
- Fails DNS resolution, hits egress firewall blocks, or lacks outbound proxy config.
- Returns JSON violating JWK Set schema, missing keys, wrong `kid`, or mismatched algorithm.
- Serves stale cached/CDN keys past rotation.
- Times out or exhausts connection pools under traffic spikes.

…then tokens cannot be verified per policy and you must **never accept tokens just because keys could not be fetched**. Public responses depending on filters/exception handling may look like `invalid_token` or 5xx; internal diagnostics and monitoring must distinguish them.

### 13.1. Layered Diagnostics

1. Confirm the API actually selects the Resource Server chain (not falling into a form-login chain).
2. Confirm the trusted issuer and JWK Set URI are server-side trusted config.
3. From the Resource Server's node/pod, test DNS, TCP, and TLS to the IdP per allowlist.
4. Check HTTP status, content type, cache headers, and whether JWK Set contains the expected public `kid`.
5. Check JWKS cache/rotation: are new tokens signed with K2 while one node's cache still holds only K1?
6. Check clocks, `exp`/`nbf`/issuer/audience so not every JWT 401 is blamed on JWK.
7. Watch p95/p99 decode latency and cache-refresh/timeout rates.
8. Never log tokens; if tracing is needed, log only **non-replayable token fingerprints**, correlation IDs, allowlisted key IDs, categories, and configured issuer aliases.

**Caution:** the JWT `kid` header is unverified and can be attacker-chosen. Never put raw `kid` into unbounded metric labels/logs. Validate size/charset and use sampling/allowlists when analyzing.

## 14. `issuer-uri`, `jwk-set-uri`, and Discovery Timing

In Spring Boot 3.x/Spring Security 6.x, Resource Server JWT config typically looks like:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${JWT_ISSUER}
          jwk-set-uri: ${JWT_JWK_SET_URI}
          audiences: ${JWT_AUDIENCE}
```

This **declares both issuer and trusted JWK URL explicitly**; `issuer-uri` is still used to validate `iss`. Using only `issuer-uri` lets the framework discover metadata/JWKS from the issuer. **Discovery timing depends on version and decoder construction**: Spring Security 6.5 docs describe default discovery deferred until the first JWT request; a custom app-built `JwtDecoder` may initialize/discover differently. Do not assert every app contacts the IdP at startup or that every decoder is lazy.

Verify:

- `JWT_ISSUER` matches the trusted access token's `iss` **exactly**.
- `JWT_JWK_SET_URI` is a **trusted** endpoint matching the AS contract, never taken from user-supplied URLs.
- `JWT_AUDIENCE` is the API's audience, distinct from the client ID used in OIDC ID tokens in many flows.
- DNS/TLS, hostnames/CAs, and outbound egress work from **all pods**, not just one node.
- If declaring a custom `JwtDecoder @Bean`, you may have replaced auto-configured validators. Confirm issuer/audience/time/signature checks are intact.
- Never share one global issuer/JWKS across multiple tenants without evaluating trust boundaries; design trusted issuer resolution instead.

**Example:** adding only `jwk-set-uri` without `issuer-uri` or building a signature-only decoder can skip the required `iss` validator. A signed token from a different issuer must never be accepted just because a public key sits at some URL.

## 15. Spring Security `AuthenticationEventPublisher`: Why "Bad Credentials" Logs Mislead

Spring Security includes `AuthenticationEventPublisher`; `DefaultAuthenticationEventPublisher` maps `AuthenticationException`s to event types. In **Spring Security 6.5** docs, default mappings include:

| Exception | Event |
| --- | --- |
| `BadCredentialsException` | `AuthenticationFailureBadCredentialsEvent` |
| `UsernameNotFoundException` | `AuthenticationFailureBadCredentialsEvent` |
| `InvalidBearerTokenException` | `AuthenticationFailureBadCredentialsEvent` |
| `AuthenticationServiceException` | `AuthenticationFailureServiceExceptionEvent` |
| `LockedException` | `AuthenticationFailureLockedEvent` |
| `DisabledException` | `AuthenticationFailureDisabledEvent` |
| `ProviderNotFoundException` | `AuthenticationFailureProviderNotFoundEvent` |

**Memorable detail:** `InvalidBearerTokenException` maps to **`AuthenticationFailureBadCredentialsEvent`**, even when the request **contained no password at all**. If a dashboard counts every `AuthenticationFailureBadCredentialsEvent` as "wrong password", metrics will be wrong. Likewise `UsernameNotFoundException` is commonly masked to prevent account enumeration.

The event publisher uses **exact exception class mapping** per Spring Security 6.5 docs; subclasses/custom exceptions may not auto-map unless registered. Some TLS failures occur before Spring and emit no events. Never treat "no `AuthenticationFailureEvent` seen" as proof the system has no authentication failures.

### 15.1. Designing More Accurate Metrics

Do not use event class as the sole business label. Also capture:

- **`auth_mechanism`** from the configured filter/chain: `LDAP_BIND`, `X509_MTLS`, `JWT_BEARER`, `OIDC_LOGIN`.
- **`failure_category`** from a reviewed internal enum: `CREDENTIAL_REJECTED`, `DEPENDENCY_UNAVAILABLE`, `TLS_TRUST_ERROR`, `TOKEN_ISSUER_INVALID`, `TOKEN_KEY_UNAVAILABLE`, `TOKEN_SIGNATURE_INVALID`, `AUTHORIZATION_DENIED`, or `UNKNOWN`.
- **`dependency_alias`** from config: `corporate-ldap`, `trusted-idp`; never raw URLs or user input.
- **`correlation_id`** issued by server/gateway with bounded length/charset; zero PII.
- **`status/outcome`**: login redirect, 401, 403, TLS pre-HTTP error, 5xx.

A single `BadCredentialsException` cannot always identify the root cause; inspect the **trusted cause chain** or scrubbed provider metadata. Never let clients send `X-Failure-Type: LDAP_OUTAGE` to alter classification logic.

## 16. Spring Security 6.x Example: Listener Without Exposing Credentials

The following Java code is a Spring component class compilable in a **Spring Boot 3.x/Spring Security 6.x** project with an authentication event publisher. It never reads passwords/tokens, never logs `Authentication.toString()`, and records only allowlisted **event categories**.

**`SafeAuthEventDiagnostics.java`**

```java
package com.example.authdiagnostics;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationFailureServiceExceptionEvent;
import org.springframework.stereotype.Component;

@Component
public final class SafeAuthEventDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(SafeAuthEventDiagnostics.class);

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        String category;
        if (event instanceof AuthenticationFailureServiceExceptionEvent) {
            category = "SERVICE_EXCEPTION_NEEDS_ROOT_CAUSE";
        } else if (event instanceof AuthenticationFailureBadCredentialsEvent) {
            category = "CREDENTIAL_OR_TOKEN_REJECTED_NEEDS_CONTEXT";
        } else {
            category = "OTHER_AUTHENTICATION_FAILURE";
        }

        log.warn("auth_failure category={} eventClass={}",
                category, event.getClass().getSimpleName());
    }
}
```

Key points:

- `SERVICE_EXCEPTION_NEEDS_ROOT_CAUSE` does not automatically prove an LDAP/network outage; inspect the trusted cause and dependencies before concluding.
- `CREDENTIAL_OR_TOKEN_REJECTED_NEEDS_CONTEXT` does **not** mean wrong password; it could be an invalid Bearer token, masked unknown username, or rejected credentials.
- Some JWT decode errors are thrown through other filter chains/entry points without hitting a provider event listener; instrument decoders/HTTP clients in the right places.
- Even when mechanism logging exists, never catch every exception and dump stack traces/credentials. Sample and rate-limit logs so attackers cannot flood millions of events.
- **This is only an event listener** and cannot determine route/issuer/LDAP cause from event type alone. Never push full `Authentication`, raw exceptions, or requests onto async queues.

### 16.1. Configuring the Event Publisher If Needed

Add this bean in a `@Configuration` class if Framework/Boot has not already configured a publisher:

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    return new DefaultAuthenticationEventPublisher(publisher);
}
```

Imports:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
```

This is a **snippet inside a configuration class**, not a standalone source file. When using a custom `ProviderManager`, verify it actually uses the configured publisher. Avoid registering duplicate publishers/listeners that count a single request multiple times.

## 17. Runnable Java 17: Separating Signals From Public Outcomes

This program runs **without Spring**, using an enum of signals verified by internal diagnostics. It deliberately accepts **no** raw passwords, JWTs, or certificate bytes. The goal is to prove the same "authentication failed" message maps from multiple branches.

**`AuthFailureClassifierDemo.java`**

```java
public class AuthFailureClassifierDemo {

    enum Signal {
        LDAP_BAD_SECRET,
        LDAP_UNREACHABLE,
        LDAPS_TRUST_FAILURE,
        MTLS_HANDSHAKE_REJECTED,
        JWT_ISSUER_MISMATCH,
        JWKS_FETCH_TIMEOUT,
        JWT_EXPIRED,
        MISSING_SCOPE
    }

    record Decision(String category, String publicOutcome) {}

    static Decision decide(Signal signal) {
        return switch (signal) {
            case LDAP_BAD_SECRET ->
                    new Decision("CREDENTIAL_REJECTED",
                                 "GENERIC_LOGIN_FAILURE");
            case LDAP_UNREACHABLE, JWKS_FETCH_TIMEOUT ->
                    new Decision("DEPENDENCY_UNAVAILABLE",
                                 "TEMPORARY_SERVICE_ERROR");
            case LDAPS_TRUST_FAILURE ->
                    new Decision("TLS_TRUST_ERROR",
                                 "TEMPORARY_SERVICE_ERROR");
            case MTLS_HANDSHAKE_REJECTED ->
                    new Decision("CLIENT_CERT_REJECTED",
                                 "TLS_ERROR_PRE_HTTP");
            case JWT_ISSUER_MISMATCH, JWT_EXPIRED ->
                    new Decision("TOKEN_INVALID",
                                 "HTTP_401_BEARER");
            case MISSING_SCOPE ->
                    new Decision("AUTHORIZATION_DENIED",
                                 "HTTP_403");
        };
    }

    public static void main(String[] args) {
        for (Signal signal : Signal.values()) {
            Decision decision = decide(signal);
            System.out.println(signal + " -> "
                    + decision.category() + " / "
                    + decision.publicOutcome());
        }
    }
}
```

Run with JDK 17+:

```bash
javac AuthFailureClassifierDemo.java
java AuthFailureClassifierDemo
```

**Exact stdout:**

```text
LDAP_BAD_SECRET -> CREDENTIAL_REJECTED / GENERIC_LOGIN_FAILURE
LDAP_UNREACHABLE -> DEPENDENCY_UNAVAILABLE / TEMPORARY_SERVICE_ERROR
LDAPS_TRUST_FAILURE -> TLS_TRUST_ERROR / TEMPORARY_SERVICE_ERROR
MTLS_HANDSHAKE_REJECTED -> CLIENT_CERT_REJECTED / TLS_ERROR_PRE_HTTP
JWT_ISSUER_MISMATCH -> TOKEN_INVALID / HTTP_401_BEARER
JWKS_FETCH_TIMEOUT -> DEPENDENCY_UNAVAILABLE / TEMPORARY_SERVICE_ERROR
JWT_EXPIRED -> TOKEN_INVALID / HTTP_401_BEARER
MISSING_SCOPE -> AUTHORIZATION_DENIED / HTTP_403
```

**This is a classification model, not a real HTTP handler or validator.** `TEMPORARY_SERVICE_ERROR` means the app should show a generic policy-compliant message; the exact HTTP status may be 503 when backends design for it, yet Spring does not return that code by default on every branch. `TLS_ERROR_PRE_HTTP` may have no HTTP status at all. `MISSING_SCOPE` assumes the token was already verified; invalid tokens must be rejected at authentication first.

A single fault can **simultaneously** impact multiple layers — for example, an IdP serving JWKs over HTTPS with an expired certificate: classify the technical cause as a trust failure while flagging the impacted dependency.

## 18. Spring Boot 3.x Example: Separating LDAP Web Login and JWT Resource Server

This problem commonly arises when an app serves both an enterprise web UI and a REST API. Separating chains makes clear which provider handles which request. The example below uses **Java 17+, Spring Boot 3.x/Spring Security 6.x** and assumes external LDAP/IdP servers.

### 18.1. Dependencies

A Gradle project with Boot plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-ldap'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

In practice, align versions with the Spring Boot BOM. `spring-security-ldap` provides LDAP authentication support; JWT Resource Server needs JOSE support managed by the starter. Do not confuse the resource-server dependency with `spring-boot-starter-oauth2-client`, which is for client/OIDC login flows.

### 18.2. `application.yml`

```yaml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.test:636/dc=example,dc=test}

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${JWT_ISSUER}
          jwk-set-uri: ${JWT_JWK_SET_URI}
          audiences: ${JWT_AUDIENCE}
```

Take trusted URLs/secrets from deployment configuration, never from client payloads. `example.test` URLs are illustrative only; the app needs reachable directory and IdP/JWKS servers to actually log in.

### 18.3. Configuring Two `SecurityFilterChain`s

**`DiagnosticSecurityConfig.java`** (package `com.example.authdiagnostics`):

```java
package com.example.authdiagnostics;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.ldap.authentication.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.context.BaseLdapPathContextSource;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DiagnosticSecurityConfig {

    @Bean
    BaseLdapPathContextSource ldapContext(
            @Value("${app.ldap.url}") String url) {
        return new DefaultSpringSecurityContextSource(url);
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {
        var factory =
                new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserDnPatterns("uid={0},ou=people");
        return factory.createAuthenticationManager();
    }

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .anyRequest().hasAuthority("SCOPE_reports.read"))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .oauth2ResourceServer(server -> server
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(
            HttpSecurity http,
            AuthenticationManager ldapAuthenticationManager)
            throws Exception {
        return http
                .authenticationManager(ldapAuthenticationManager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
```

**Explanation:**

- `/api/**` requests enter `@Order(1)`, verifying bearer JWTs without form login or LDAP passwords.
- Other web requests enter `@Order(2)`, where form login calls the LDAP bind manager. On failed logins, the default form failure handler may redirect to `/login?error`; that alone is insufficient to identify an LDAP outage.
- `securityMatcher` selects the chain, unlike `requestMatchers` which selects authorization rules inside the chain. With a wrong matcher, users may get an HTML redirect instead of Bearer 401.
- `LDAPS` also requires the right JVM truststore/CA; bean construction does not prove TLS/LDAP connectivity. `JWT_ISSUER`/`JWT_JWK_SET_URI` must match metadata/trusted AS.
- `SessionCreationPolicy.STATELESS` is strictly for **pure API bearer headers**; web login retains sessions and CSRF. Never disable CSRF system-wide just to test an API.
- The LDAP bind demo uses DN pattern `uid={0},ou=people`; if the real directory uses user search, UPN, or multiple OUs, configure accordingly. Successful user bind does not grant business roles automatically; map authorities per app rules.
- Controllers, LDAP servers, JWKS servers, and test credentials are omitted. **This is integration configuration for a project with real infrastructure**, not a standalone runnable Java program; do not claim this code ran in this environment.

### 18.4. Do Not Use One Generic Failure Handler to Collapse All Errors

If the frontend wants distinct states for an LDAP dependency outage vs an invalid password, define an explicit policy:

```text
LDAP truly rejected credential / unknown username:
    web user sees generic "Cannot sign in"
    internal category: AUTH_CREDENTIAL_REJECTED

LDAP network/trust dependency unavailable:
    web user sees generic "Sign-in temporarily unavailable"
    internal category: LDAP_DEPENDENCY_UNAVAILABLE
    no password retry storm; alert ops

JWT invalid signature/issuer/audience/expired:
    API returns 401 Bearer challenge
    internal category: TOKEN_INVALID (safe subcategory)

JWKS endpoint outage:
    do not accept token without signature verification
    internal category: JWKS_DEPENDENCY_UNAVAILABLE
    response according to deliberate security/error contract

TLS/mTLS fails before application:
    client sees TLS error or ingress-defined response
    internal category: TLS_HANDSHAKE_FAILURE
```

This is **policy pseudocode**, not guaranteed default behavior across all Spring providers. If distinguishing service-unavailable in the UI, ensure it never becomes an **account enumeration oracle** (e.g., a connection error happening only for real usernames); classify strictly from trusted infrastructure signals without exposing account policies.

## 19. OAuth2 Login/OIDC and Resource Server Are Two Different Flows

A web app using `oauth2Login()` runs the **Authorization Code flow** (typically with OIDC) via browser redirects, state, nonce, PKCE per architecture, and callbacks. Errors can include:

- `invalid_state` / lost state cookie or session.
- Redirect URI missing from the IdP allowlist.
- Callback/reverse proxy scheme/host differing from configured URI.
- Authorization Server token-endpoint timeouts or TLS certificate failures.
- ID token having wrong issuer, audience (client ID), signature, nonce, or key rotation mismatch.
- Missing OIDC `sub`/`iss` to local user mapping, or failed role mapping.

Meanwhile `oauth2ResourceServer().jwt()` accepts an **access token** in the HTTP `Authorization` header. It neither runs password-based browser logins nor follows IdP login forms.

| Aspect | OIDC Client Login | Resource Server JWT |
| --- | --- | --- |
| Primary artifact | Authorization response, ID token/authorized client | Access token for API calls |
| Token issuer trust | Client registration's IdP | Protected API's issuer |
| Audience | Usually client ID in ID token | Resource/API audience in access token |
| HTTP UX | Redirects to login/callback/error page | 401 Bearer or 403 for insufficient scope |
| State | Web session, state, nonce, authorized client | Usually stateless per-request decoder |
| Common mistake | "User mistyped password" when state/redirect breaks | "User mistyped password" when `iss`/`kid`/JWK breaks |

**Never use an ID token as an API access token.** A JWT ID token can be validly signed, yet its audience/semantics prove login to an OAuth client rather than authorizing a Resource Server. Dropping audience validation to "fix" 401 introduces token-substitution risk.

## 20. Differences Between Auth Errors, Service Outages, and 403 in Logs

Some errors are intentionally masked:

- `DaoAuthenticationProvider` and some providers convert `UsernameNotFoundException` into `BadCredentialsException` to prevent enumeration.
- LDAP servers may withhold account disabled/locked reasons in public APIs.
- JWT bearer filters can return `InvalidBearerTokenException` and HTTP 401 without specifying signature, issuer, or expiration in the body.
- Ingress/proxies can return TLS errors with zero application logs.
- `AccessDeniedException` after authentication produces 403; it is not a password failure.

**Keep two messaging layers:**

1. **Public response:** generic, safe, protocol-compliant; never expose DNs, username existence, server names, private keys, token payloads, truststore paths, or sensitive validation subcodes.
2. **Internal evidence:** bounded classification, UTC timestamp, correlation ID, app instance, chain name, dependency alias, error category, status, latency, and certificate expiry **without secrets**.

Never log raw `Authentication`, `Authentication.getCredentials()`, bearer tokens, `Authorization` headers, session cookies, private keys, password request bodies, or unnecessary full LDAP bind DNs. Apply structured logging allowlists **at the source**.

## 21. Practical Incident Inspection Sequence

Suppose 40% of users report "wrong password" after a deployment:

**Step 1 — Group requests.** How many errors are on web forms, how many on API Bearer, how many on mTLS? Check gateway/filter-chain logs; never lump all 401s into password metrics.

**Step 2 — Correlate with timeline.** Did errors spike after a CA update, JWK rotation, LDAP OU migration, issuer/realm change, JDK/truststore deploy, or clock drift? Tag release/instance IDs to detect single-node faults.

**Step 3 — Confirm requests reach the app.** If TLS/mTLS handshakes fail at the edge, Spring Security never sees the request. Inspect ingress TLS logs and certificate chains; do not hunt for `BadCredentialsException` in app logs.

**Step 4 — For LDAP, separate bind outcome from transport.** Using a lab account, check trusted LDAP connectivity, TLS, DN patterns, service accounts, user bind, and group search. Never test real users' passwords or send them in tickets.

**Step 5 — For JWT, verify trust boundaries.** Confirm the token came from the right AS, `iss`, `aud`, `exp`/`nbf`, `kid`/`alg`, and JWK Set. If real tokens carry PII, use test/synthetic tokens and log only defined fingerprints.

**Step 6 — If authn succeeded yet returned 403, check authorization.** Verify Spring scope prefixes `SCOPE_`, roles `ROLE_`, tenants, resource ownership, group lookup, and method security; do not reset credentials.

**Step 7 — Assess blast radius.** Are all nodes failing or only one AZ/pod? Does one node have a stale JWK cache/truststore? Is there a localized Redis/LDAP/IdP outage? Are retries causing request storms?

**Step 8 — Fix the right layer.** Apply reviewed CA/trust updates; fix exact issuer/JWKS configs; coordinate key rotation; restore LDAP service; fix group mappings; roll back when needed. Never disable signature, hostname, certificate, or authentication checks.

**Step 9 — Regression and postmortem.** Write tests for the exact failure mode (mTLS handshake, LDAP outage, JWKS rotation, issuer mismatch), add safe alerts, and update runbooks.

## 22. CI and Staging Test Matrix

| Scenario | Simulation / Fixture | Expectation |
| --- | --- | --- |
| Valid LDAP login | Test LDAP server with known-good user | Authenticated, right principal/authorities |
| LDAP wrong password | Lab account + wrong password | Fails, generic public message |
| Nonexistent user | Lab login with nonexistent username | Message/timing does not become an enumeration oracle |
| LDAP server down | Stop test container / block port | Fails closed; categorized internally as dependency error |
| LDAP TLS invalid CA | Test LDAPS server with untrusted CA | No bind; trust error, not classified as bad password |
| LDAP DN moved OU | Test directory moves account path | Search/lookup mismatch detected without password reset |
| Group search broken | Directory returns user without groups | High roles withheld; 403 verified per policy |
| mTLS missing client cert | Test ingress requiring certificate | TLS handshake or edge error per config |
| mTLS expired cert | Synthetic expired client certificate | Rejected by TLS/trust policy; Spring may never see request |
| mTLS valid cert yet unmapped principal | Trusted test certificate | App fails mapping/denies access, classified distinctly from TLS |
| JWT wrong `iss` | Signed test JWT from different issuer | 401, rejected |
| JWT wrong `aud` | Signed test JWT meant for another API | 401 when audience validator is enabled |
| Expired JWT or future `nbf` | Controlled clock fixture | 401, independent of user password |
| JWT bad signature | Untrusted test key | 401; never skip signature verification |
| JWT key rotation K1→K2 | JWKS test endpoint rotates public keys | New tokens valid after trust/refresh; old tokens per policy |
| JWKS down / DNS / TLS failure | Mock HTTP/JWKS server timing out | Unverified tokens rejected; dependency alert fires |
| Valid JWT lacking scope | Valid signed JWT, wrong scope | 403, not treated as login/password failure |
| Wrong OIDC state/nonce | Test IdP/callback | Login rejected, not blamed on wrong password |
| Two-node cache divergence | Two pods with differing caches/truststores | Per-instance discrepancy detected |
| Excessive invalid tokens | Rate-limited load test and sampling | Zero raw tokens logged; no logging DoS |

### 22.1. What Spring Security Test Provides — and Does Not Provide

`MockMvc` with `spring-security-test` is great for testing matchers/authorization. However:

- `.with(jwt())` **fabricates a `JwtAuthenticationToken`** without calling real `JwtDecoder` to verify signatures, issuers, audiences, or JWKS.
- `.with(user("alice"))` **never calls LDAP bind**. It cannot prove the directory is reachable or passwords work.
- `.with(x509(...))` or manually setting certificate attributes on mock requests **does not prove TLS handshakes or ingress client-cert verification**.
- Standard MockMvc tests bypass reverse proxies and TLS termination, so HTTP/mTLS integration tests are still needed.

To test real root causes, use a **team-controlled LDAP test container/embedded LDAP**, a **JWKS HTTP stub + JWTs signed with test keys**, and a **TLS test ingress** with test CAs/expired certs to verify flows end-to-end. Tests must avoid production private keys or real user tokens.

### 22.2. Assertions to Include

In security integration tests, also assert:

- **Right HTTP response** for browser/API: 302 form login, 401 Bearer challenge, 403 insufficient privileges; 503 if dependency-outage handlers intend it.
- **Accurate internal category** without leaking root causes in public responses.
- **No bypasses:** LDAP/JWKS/CA failures never authenticate as admin.
- **No data leaks:** captured logs contain no raw passwords, JWTs, cookies, or private keys.
- **No retry storms:** connection/JWKS retries have proper timeouts, backoff, and rate limits.
- **Isolation across flows:** API bearer failures do not wipe web sessions; LDAP outages do not disable JWT validation.
- **Post-recovery operation:** once directories/keys recover, valid logins/tokens resume working without mass password resets.

## 23. Metrics and Alerts Worth Having

| Signal | Meaning on Sharp Spike |
| --- | --- |
| `ldap_connect_timeout_total` | LDAP/DNS/firewall/pool issue |
| `ldap_tls_handshake_failure_total` | Certificate chain/CA/SAN/truststore/clock issue |
| `ldap_bind_rejected_total` | Credential/policy/DN issue; investigate further |
| `ldap_group_lookup_failure_total` | Authorization mapping dependency issue |
| `mtls_handshake_rejection_total` at ingress | Client certificate/trust/policy issue before the app |
| `x509_principal_mapping_failure_total` | TLS succeeded yet app failed to map user |
| `jwt_invalid_issuer_total` | Token has wrong issuer/realm/environment |
| `jwt_invalid_audience_total` | Token not intended for this API |
| `jwks_fetch_failure_total` | Metadata/JWK availability/trust issue |
| `jwt_kid_not_found_total` | Rotation/cache/issuer mismatch/attacker input |
| `token_signature_rejected_total` | Key/algorithm/signature mismatch |
| `authz_denied_total` | Missing role/scope/tenant |
| `auth_provider_latency_seconds` | Dependency latency, risking login timeouts |

These are **illustrative metric names the application must instrument itself**, **not** built-in Spring Security metrics. Never use usernames/emails/IPs/raw `kid`/`iss` from unverified tokens as unbounded-cardinality metric labels. Use only low-cardinality labels from trusted config such as `mechanism`, `routeGroup`, `dependencyAlias`, and `outcome`; if user identifiers must be stored for investigations, keep them in a separate secured store with retention limits.

**Alerting tip:** do not alert solely on total 401s — break down rates by mechanism, node/version/AZ; a `jwks_fetch_failure` spike after key rotation differs completely from a credential-stuffing wave. Watch p99 LDAP bind/JWK request latency rather than response status alone.

## 24. Common Dangerous Fixes

| "Quick Fix" | Risk | Right Approach |
| --- | --- | --- |
| "If LDAP fails, use a static admin password" | Authentication bypass | Fail closed and restore LDAP |
| Disable LDAPS hostname validation | Accepts spoofed servers | Fix SAN/hostname/CA chain |
| Switch from LDAPS to plaintext LDAP | Exposes credentials on the wire | Fix TLS, keep encryption |
| Trust-all certificates or skip chain validation | MITM, IdP/LDAP spoofing | Approved truststore/CA |
| Disable mTLS client-certificate requirement | Anyone can reach the endpoint | Fix cert policy and provisioning |
| Trust `X-Client-Cert` headers from the Internet | Clients forge certificates | Accept only from verified trusted proxies |
| Drop `iss` checks because token "signed validly" | Tokens from other realms accepted | Enforce exact issuer validator |
| Drop `aud` checks due to JWT 401 | Cross-service token substitution | Validate API audience |
| Accept any `alg` from JWT header | Algorithm confusion | Trusted algorithm allowlist |
| Fetch JWKS from URL declared inside token | SSRF/rogue signing keys | Server-side trusted JWKS config |
| Skip signature validation when JWKS is down | Forged tokens accepted | Fail closed + dependency alert |
| Run `jwt()` mock and assume JWKS works | Skips decoder/network/issuer | Signed-JWT integration tests |
| Log raw `Authentication` or tokens | Credential/PII leakage | Redacted structured logs |
| Show "Wrong password" for all API 401s | Misdirected triage, forced user resets | Mechanism-appropriate UX; internal categories |
| Expose LDAP results/subcodes on login form | Username enumeration / account-state leak | Generic response, internal-only evidence |
| Map every `AuthenticationFailureBadCredentialsEvent` to password failures | Invalid Bearer tokens miscounted | Separate mechanism/provider context |
| Return 403 for all invalid tokens | Violates HTTP semantics, confuses SDKs | 401 for authn; 403 for missing privileges |
| Omit timeouts/backoff on LDAP/JWKS | Thread exhaustion, cascading failures | Bounded timeouts, circuit breakers, retry policies |
| Mass password resets during JWK rotation | Does not solve issue, causes disruption | Check key rotation/cache/issuer |

**Never use disabling authentication to prove "the error is fixed".** The goal of a runbook is preserving trust and pinpointing root causes, not forcing endpoints to return 200 at all costs.

## 25. Practice Exercises

1. A corporate form login returns `/login?error` even for users with right passwords after the directory rotates its CA. Trace the flow from browser to Spring Security/LDAP and identify **which layer never reached password checking**. Propose three internal pieces of evidence containing no secrets.
2. Given LDAP code 49 and AD subcode `775`, explain why you must not conclude the user mistyped their password; how should the public response behave to prevent enumeration?
3. An mTLS request never shows up in the app. List the inspection order across TLS handshake, ingress logs, trusted CA, client EKU, and principal mapping.
4. Client certificate handshake succeeds, yet Spring `x509()` fails to map the user. Distinguish "TLS trust failure" from "app principal-mapping failure".
5. An API JWT has `iss=https://idp.example.test/realm-a` while trusted issuer config expects `realm-b`. The signature verifies; why must it return 401?
6. New tokens are signed with `kid=K2`, node A's cached JWKS holds only K1, and node B already has K2. Design an integration test demonstrating this cache/rotation discrepancy without logging raw tokens.
7. The JWKS endpoint returns an expired TLS certificate. Should you temporarily disable the signature validator? Why not?
8. Install a Spring Security listener and see why `InvalidBearerTokenException` can emit `AuthenticationFailureBadCredentialsEvent`. Adjust metrics so it is not miscounted as a wrong password.
9. Write MockMvc authorization tests with mock JWTs having/lacking scopes, then **add** integration tests with genuinely signed JWTs and a JWKS stub to verify issuer/audience/keys.
10. Design a per-mechanism dashboard tracking 401/403, LDAP connect/TLS, JWKS fetches, cache misses, mTLS ingress errors, and release versions.
11. Make a test LDAP service unavailable; verify handlers neither grant authentication nor leak hostnames/stack traces in public responses.
12. Pick sensible retry timing after an IdP outage so thousands of pods or clients do not trigger a retry storm.

## 26. Summary and Reference Sources

- **Never equate "login failed" messages with wrong passwords.** Identify whether the request failed at TLS, directory/provider, `JwtDecoder`, or authorization.
- LDAP can fail on bind/search/DN, network, service accounts, LDAPS truststores, or group mappings; `49 invalidCredentials` does not prove a bad password in every directory.
- With X.509/mTLS, TLS client certificates can be rejected **before HTTP/Spring**; if handshakes succeed yet principal mapping fails, that is a separate bug category.
- Resource Servers process access tokens, not user passwords; `iss`, `aud`, signatures, `kid`/`alg`, JWKS cache/rotation, and dependency outages are the diagnostic branches.
- Spring Security's `AuthenticationFailureBadCredentialsEvent` can fire for `InvalidBearerTokenException`; dashboards must not count all such events as password failures.
- Public responses must stay safe while internal evidence separates credentials, service outages, trust errors, invalid tokens, and denied authorizations without logging secrets.
- **Never bypass trust** to remediate: never disable TLS validation, certificate checks, or issuer/audience/signature validation; fail closed when verification is impossible.
- Test LDAP, mTLS, signed JWT/JWKS, issuers, roles, and failovers; MockMvc mock users/JWTs cannot replace real credential and cryptographic integration tests.

**Official Documentation:**

- [Spring Security 6.5 — LDAP Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html)
- [Spring Security 6.5 — X.509 Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/x509.html)
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security 6.5 — Authentication Events and Exception Mappings](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)