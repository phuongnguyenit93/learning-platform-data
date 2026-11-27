# Testing expiration of codes, tokens, client secrets, and certificates

An Authorization Server must reject any expired credential while continuing to accept valid credentials throughout their configured lifetime. With Spring Authorization Server, testing must cover where credentials are issued, where OAuth2 state is stored, and where credentials are verified. A test that only checks the `exp` claim inside a JWT does not prove the token is rejected at the resource server; similarly, checking a certificate's expiration date by reading a PEM file does not prove the TLS handshake will reject that certificate.

This lesson belongs to the `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER` module, focusing on designing and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Authorization Server. The examples aim to test authorization code, access token, refresh token, client authentication, and TLS flows in an integration environment.

## 1. Distinguishing expiration types

Each credential type has a different lifecycle and enforcement point. Identifying the right checkpoint before writing tests helps avoid drawing false conclusions from a component that is not responsible for verifying that credential.

| Subject | Where expiration is represented | Component that must reject on expiration |
|---|---|---|
| Authorization code | `expiresAt` of the authorization code stored in `OAuth2Authorization` | Authorization Server token endpoint |
| JWT access token | `exp` claim in the JWT and stored authorization metadata | Resource server when validating JWT; Authorization Server when handling related state |
| Opaque access token | Token metadata and authorization state in the store | Resource server via introspection or corresponding verification mechanism |
| Refresh token | `expiresAt` of the refresh token in authorization state | Token endpoint when receiving `grant_type=refresh_token` |
| Client secret | `clientSecretExpiresAt` of `RegisteredClient` | Client authentication mechanism at the token endpoint or endpoints requiring client authentication |
| TLS server certificate | `notBefore` and `notAfter` in the server certificate | TLS client when verifying the Authorization Server's certificate |
| TLS client certificate | `notBefore` and `notAfter` in the client certificate | TLS terminator or mTLS verification component before processing the request |

Expiration differs from revocation or invalidation. An authorization code may still be within its validity window yet already used; a refresh token may not be expired yet already rotated or revoked; a client secret may not be expired yet already replaced. Tests must verify each cause separately so failures are categorized accurately.

## 2. Preparing testable expiration configurations

Spring Authorization Server lets you configure access token and refresh token lifetimes via `TokenSettings`. Each `RegisteredClient` can use its own token settings.

```java
import java.time.Duration;

import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build();
```

In this example, the refresh token is rotated upon a successful refresh. Configuring `reuseRefreshTokens(false)` makes the token endpoint issue a new refresh token and invalidate the old refresh token according to the behavior of the Spring Authorization Server version in use.

A client using the settings above can be registered as follows:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.client.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient client = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-service")
        .clientSecret(passwordEncoder.encode("test-secret"))
        .clientSecretExpiresAt(Instant.now().plus(Duration.ofDays(30)))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://client.example.com/login/oauth2/code/orders")
        .scope("orders.read")
        .tokenSettings(tokenSettings)
        .build();
```

This is an illustrative configuration for a test fixture. A real application must use an appropriate `PasswordEncoder`, persist clients via a durable repository, and manage secrets through a secure configuration store. Never use plaintext secrets in production configurations.

### 2.1. Do not assume all credentials share the same TTL

`TokenSettings` controls the token lifetimes supported by that API, such as access tokens and refresh tokens. Authorization codes may be generated and expired by the provider handling authorization requests; TTL configurability depends on the Spring Authorization Server version and customization. Check the API of your project's version, then test the actual persisted `expiresAt` value. Do not infer authorization code lifetime from `accessTokenTimeToLive`.

Client secrets use `clientSecretExpiresAt` on `RegisteredClient`, not `TokenSettings`. TLS certificates have their own lifetimes issued by a CA and checked by the TLS stack. Separating configuration per credential type ensures tests pinpoint exactly which policy is misconfigured.

## 3. Testing expired and single-use authorization codes

An authorization code is a short-lived credential issued after the user completes the authorization flow. The client sends the code to the token endpoint to exchange it for tokens. The token endpoint must reject codes that are expired, belong to a different client, have a mismatched redirect URI, or have already been used.

Two cases must be tested separately:

- **Expiration:** the current time is equal to or past the code's `expiresAt`.
- **Replay:** a code that was previously exchanged successfully is submitted again.

### 3.1. Creating an expired code fixture

To test expiration without waiting for the real TTL, create an `OAuth2Authorization` fixture containing an authorization code with `expiresAt` in the past, then save it through the `OAuth2AuthorizationService` used by the token endpoint. The fixture must include the registered client, principal, `AUTHORIZATION_CODE` grant type, and appropriate authorization request attributes so the provider has enough data to perform remaining checks.

Example of creating the code in a test:

```java
import java.time.Instant;

import org.springframework.security.oauth2.core.OAuth2AuthorizationCode;

Instant issuedAt = Instant.now().minusSeconds(120);
OAuth2AuthorizationCode expiredCode = new OAuth2AuthorizationCode(
        "expired-code-for-test",
        issuedAt,
        Instant.now().minusSeconds(60));
```

Attach this code to the authorization fixture via the `OAuth2Authorization.withRegisteredClient(...)` builder, set `AuthorizationGrantType.AUTHORIZATION_CODE`, the principal, and required authorization request attributes, then call `authorizationService.save(authorization)`. The exact structure of the fixture depends on the principal and how the application persists authorization requests; use a shared fixture factory across token endpoint tests to avoid omitting required attributes.

Send a code exchange request to the token endpoint with the matching client and redirect URI. The expected result is the OAuth2 error `invalid_grant`; no access token or refresh token may be issued. Do not assert only the HTTP status while ignoring the error body, as the body distinguishes `invalid_grant` from `invalid_client` or `invalid_request`.

### 3.2. Testing code replay

With a non-expired code, perform a valid authorization flow and exchange the code once. The first request must succeed. Resend the same code with the same client and redirect URI; the second request must be rejected with `invalid_grant`.

When running tests across multiple instances, save the authorization in a shared repository, send the first code exchange to node A, and send the replay request to node B. Node B's response must reflect that the code has already been used. If node B still accepts the code, inspect the consistency of `OAuth2AuthorizationService`, transactions, and the single-use status update mechanism.

Do not use an expired code to test replay: both cases are rejected, which fails to prove the server distinguishes between the two rules.

## 4. Testing expired access tokens

An access token can be a JWT or an opaque token. Testing approaches differ where the resource server verifies the token.

### 4.1. Checking expiration upon JWT issuance

For JWTs, inspect the `iat` and `exp` claims in the issued token. If policy specifies a five-minute access token TTL, `exp` must correspond to the issuance time plus that duration, within clock precision and timestamp rounding tolerances.

You can inspect metadata in the authorization store via `OAuth2AuthorizationService.findByToken(...)` and compare `OAuth2Authorization.Token.getToken().getExpiresAt()` against the `exp` claim. Decoding the payload only serves to verify data in tests; it does not verify signatures and cannot replace resource server testing.

### 4.2. Verifying expired JWTs at the resource server

The resource server must verify the signature, issuer, audience if required, and `exp` expiration. Create a test JWT signed with a trusted test key with `exp` in the past, then send the JWT to a protected endpoint. The result must be `401 Unauthorized` and the request must never reach business logic.

Example HTTP-level test:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.HttpHeaders;

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + expiredJwt))
    .andExpect(status().isUnauthorized());
```

`expiredJwt` must be a JWT with a valid signature and an issuer/key trusted by the resource server, but with an elapsed `exp`. If a token with an invalid signature or mismatched issuer is used, the test may receive `401` for a different reason and fail to prove the expiration validator works.

Spring Security may apply clock skew when verifying timestamps to tolerate clock drift between systems. Read the resource server's `JwtTimestampValidator` configuration and test timestamps outside the clock skew window. If a test sends a token expired by only a few milliseconds, it may still be accepted under the clock skew policy. Document the grace margin in test expectations.

### 4.3. Testing opaque access tokens

For opaque tokens, the resource server typically calls the introspection endpoint. When a token expires, the Authorization Server must return `active: false`; the resource server must reject the corresponding request. Tests should cover:

1. An active, non-expired token introspects as active and accesses the protected endpoint successfully.
2. An expired token introspects as inactive.
3. The resource server rejects an inactive token, even when the client sends a well-formed token.
4. Introspection caching does not retain active status past the token's expiration time per cache policy.

If introspection responses are cached, the cache TTL must be shorter than or equal to the token's remaining lifetime. When a token is revoked, the cache also needs to be handled within the system's acceptable revocation latency.

## 5. Testing expired and rotated refresh tokens

A refresh token lets a client request new access tokens without requiring the user to log in again. Because refresh tokens are long-lived and highly privileged, the token endpoint must reject refresh tokens that are expired, revoked, or replaced during rotation.

Create an authorization fixture containing a refresh token with `expiresAt` in the past and save it in `OAuth2AuthorizationService`. Send a `grant_type=refresh_token` request with the matching client. The expected outcome is `invalid_grant`, with no new token issued.

Beyond expiration, test rotation as follows:

1. Issue a valid access token and refresh token.
2. Use the refresh token to request new tokens.
3. Confirm the request succeeds and returns a new refresh token if `reuseRefreshTokens(false)` is configured.
4. Resubmit the old refresh token; the server must reject it per the rotation policy.
5. Confirm the new refresh token is valid and has the configured lifetime.

When testing concurrency, send two refresh requests nearly simultaneously using the same refresh token. Only one request may consume the old token successfully. The remaining request must be rejected or handled according to the system's documented anti-replay policy. If both requests produce valid tokens, inspect transactions and verify whether authorization state updates are atomic.

## 6. Testing expired client secrets

`RegisteredClient` has a `clientSecretExpiresAt` field representing when the client secret expires. Client authentication must reject the secret after this timestamp, even when the submitted secret still matches the stored hash.

In a test fixture, create a client with an expired secret:

```java
RegisteredClient expiredSecretClient = RegisteredClient.withId("test-client-id")
        .clientId("expired-secret-client")
        .clientSecret(passwordEncoder.encode("expired-secret"))
        .clientSecretExpiresAt(Instant.now().minusSeconds(60))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .build();

registeredClientRepository.save(expiredSecretClient);
```

Call the token endpoint using the valid client ID and secret via HTTP Basic. Because the secret is expired, the server must return `invalid_client` and issue no token. Use a wrong secret in a separate test to prove credential mismatches are also rejected.

Example request in MockMvc:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(post("/oauth2/token")
        .with(httpBasic("expired-secret-client", "expired-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "client_credentials")
        .param("scope", "orders.read"))
    .andExpect(status().isUnauthorized())
    .andExpect(jsonPath("$.error").value("invalid_client"));
```

Tests must run with the exact `RegisteredClientRepository` and client authentication mechanism used in production. Mocking the entire client authentication provider only confirms the mock was called without testing actual expiration behavior.

For secret rotation, also test the replacement workflow: the old secret is rejected after expiration or replacement, the new secret is accepted, and there is no window where a revoked secret still authenticates due to stale client caches. If `RegisteredClient` is cached, clearly define synchronization timing and invalidation across instances.

## 7. Testing expired TLS certificates

TLS certificates serve two common roles in an authorization system:

- Server certificates authenticate the Authorization Server's hostname to connecting clients.
- Client certificates authenticate workloads when using mutual TLS (mTLS), which can be used for client authentication or binding access tokens to certificates.

Certificate validity is recorded in `notBefore` and `notAfter`. The TLS stack checks the validity period along with the trust chain, CA signature, hostname/SAN, and key usage constraints. Expired certificates are usually rejected during the TLS handshake, before the request reaches an OAuth2 endpoint. Therefore, do not expect every expired certificate case to return an OAuth2 JSON error.

### 7.1. Testing server certificates

From a client machine or an external test environment outside the cluster, inspect the certificate advertised by the proxy or server:

```bash
openssl s_client \
  -connect auth.example.com:443 \
  -servername auth.example.com \
  -CAfile trusted-ca.pem \
  -verify 5 \
  -verify_return_error \
  -showcerts
```

Read the validity dates of a saved certificate:

```bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates
```

Integration tests should start a local TLS server with an expired test certificate and confirm the TLS client rejects the connection. Use test-only CAs and keys; never use production private keys in test fixtures. Test a valid certificate separately to prove the test fails specifically due to expiration rather than a wrong trust store or hostname.

If TLS terminates at an ingress, API gateway, or reverse proxy, the certificate seen by clients is the certificate at that layer. Test the public endpoint and verify renewal/deployment configuration at the actual TLS terminator. Internal certificates between the proxy and application represent a separate TLS connection and require a separate test suite if upstream TLS is enabled.

### 7.2. Testing client certificates in mTLS

With mTLS, the client presents a certificate during the handshake. The TLS terminator must reject certificates that are expired, not yet valid, or outside the trusted CA chain. Test at least these cases:

- Valid client certificate, trusted CA, and matching registered identity: handshake succeeds.
- Expired client certificate: handshake fails before the token endpoint processes the request.
- Not-yet-valid certificate: handshake fails.
- Certificate signed by an untrusted CA: handshake fails.
- Valid certificate whose SAN/Subject does not match the registered client: client authentication is rejected per the configured mapping mechanism.

If a reverse proxy terminates mTLS and forwards client identity via a header, the backend may trust that header only when the request demonstrably comes from the trusted proxy. The proxy must strip same-named headers sent by Internet clients, set the value itself after verifying the certificate, and secure the proxy-to-backend channel. Never allow clients to call the backend directly and spoof certificate identity headers.

Example calling an mTLS endpoint with a test certificate:

```bash
curl --cacert test-ca.pem \
  --cert client-cert.pem \
  --key client-key.pem \
  https://auth.example.test/oauth2/token \
  -u mtls-client:unused \
  -d grant_type=client_credentials
```

This example assumes the endpoint requires both mTLS and client authentication matching the test configuration. With `tls_client_auth`, certificate-based client identification must match client registration and server TLS configuration. Do not add HTTP Basic if the client is configured solely for certificate authentication.

### 7.3. Testing certificate-bound access tokens

If a client is registered to bind access tokens to certificates, verify the token contains the `cnf` confirmation claim with the certificate thumbprint per the implemented profile, typically `x5t#S256`. The resource server must compare the client certificate presented on the request with the thumbprint in the token.

Test cases should include a token used with the matching certificate, a token used with another valid certificate, and an expired certificate. The different certificate must be rejected due to thumbprint mismatch; the expired certificate must be rejected at the TLS handshake. These two cases prove two distinct layers of control.

## 8. Controlling time in tests

Expiration testing easily becomes slow and flaky if it relies on `Thread.sleep`. Prefer creating fixtures with known past/future timestamps, then invoking the exact component responsible for verification.

For application-authored business logic, inject `Clock` so fixed time can be used in tests:

```java
import java.time.Clock;

import org.springframework.context.annotation.Bean;

@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
```

In tests, replace the bean with a fixed or adjustable clock, then verify behavior immediately before, exactly at, and immediately after expiration. This is especially useful for secret rotation policies, certificate expiry alerts, and application-managed renewal logic.

Do not assume every internal provider in Spring Authorization Server uses the application's `Clock` bean. If a provider uses internal system time, an application test clock will not automatically alter its behavior. For framework-generated codes/tokens, use expired authorization fixtures, signed JWTs with `exp` in the past, or integration tests with short TTLs and controlled waits. Avoid altering the CI environment's OS-wide clock.

Test three boundary points for every expiration rule:

| Point in time | Expectation |
|---|---|
| Before `expiresAt` | Credential is valid |
| At or after `expiresAt` | Credential is expired per the verifier's rule |
| After `expiresAt` plus clock skew (if applicable) | Credential is rejected once past the configured tolerance window |

For X.509 certificates, the boundary points are `notBefore` and `notAfter`; for JWTs, `nbf` and `exp`; for client secrets and authorization state, the timestamps stored in the repository. Explicitly specify timezones and use UTC to avoid timezone conversion or daylight saving bugs.

## 9. Recommended test matrix

| Component | Valid case | Expired case | Expected outcome on expiration |
|---|---|---|---|
| Authorization code | Exchange valid code once | Exchange code with `expiresAt` in the past | Token endpoint returns `invalid_grant` |
| Authorization code replay | First code exchange succeeds | Resubmit already-used code | Token endpoint returns `invalid_grant` |
| JWT access token | Validly signed JWT with future `exp` | Validly signed JWT with `exp` past clock skew | Resource server returns 401 |
| Opaque access token | Introspection returns `active: true` | Introspection returns `active: false` | Resource server rejects |
| Refresh token | Non-expired refresh token | Refresh token with `expiresAt` in the past | Token endpoint returns `invalid_grant` |
| Client secret | Non-expired matching secret | Matching secret past `clientSecretExpiresAt` | Client authentication returns `invalid_client` |
| TLS server certificate | Valid chain, matching hostname, unexpired | Expired server certificate | TLS client rejects handshake |
| TLS client certificate | Valid mTLS certificate for right client | Expired client certificate | TLS terminator rejects handshake |

Beyond isolated tests, run tests behind a load balancer to verify all instances share policies and state. A single node must not accept an expired credential because its local cache or data is staler than another node's.

## 10. Common testing pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Expired code test receives `invalid_client` | Wrong client secret or client authentication fixture | Fix fixture so client authenticates successfully before testing the code |
| Expired JWT test still accepts token right after `exp` | Resource server clock skew allows a tolerance window | Set `exp` far enough in the past or test beyond clock skew |
| Expired JWT is rejected but unclear if due to `exp` | Signature, issuer, audience, or algorithm is also invalid | Use a test JWT valid in every other attribute and alter only `exp` |
| Old refresh token still works on another node | Unshared authorization store, stale cache, or non-atomic updates | Check persistence, transactions, and cross-node invalidation |
| Expired secret is still accepted | `clientSecretExpiresAt` not saved or repository/cache returns stale `RegisteredClient` | Reload client from repository and check each instance's cache |
| Expired certificate returns TLS error instead of OAuth2 JSON | TLS handshake rejected request before reaching the application | Confirm this is the expected layer and inspect TLS terminator logs |
| Expired mTLS test still reaches token endpoint | TLS terminated at another proxy or proxy does not require client certificates | Verify where TLS actually terminates and client certificate verification config |
| Certificate test fails due to hostname instead of expiry | SAN does not match test hostname | Use a hostname matching SAN to isolate expiration |
| Expiration tests flake on CI | `sleep` too short or clock drift between nodes | Use fixed-time fixtures, UTC, and sufficiently wide timestamp margins |

## 11. Pre-release checklist

- [ ] Confirm access token and refresh token TTLs per client type.
- [ ] Verify actual `expiresAt` values stored with authorization state.
- [ ] Expired authorization codes are rejected with `invalid_grant`.
- [ ] Used authorization codes cannot be replayed on the same node or another node.
- [ ] Expired JWT access tokens are rejected by the resource server beyond clock skew.
- [ ] Expired opaque access tokens return `active: false` on introspection.
- [ ] Expired, revoked, or rotated refresh tokens are rejected.
- [ ] Expired client secrets return `invalid_client`, even when the submitted secret matches.
- [ ] Expired TLS server certificates are rejected by clients connecting to public endpoints.
- [ ] Expired TLS client certificates are rejected by the TLS terminator in mTLS flows.
- [ ] Certificate-bound tokens are verified with the matching certificate and rejected on thumbprint mismatch.
- [ ] Tests run with near-production persistence/cache configurations and across multiple instances.
- [ ] Private keys, client secrets, and tokens never appear in logs or test reports.

A reliable expiration test suite must prove that valid credentials are accepted, expired credentials are rejected at the responsible layer, and that state remains consistent across instances. By separating expiration, replay, revocation, credential mismatch, and trust chain errors, test results pinpoint the exact security policy that needs fixing.
