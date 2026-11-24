# Customizing HTTPS Connections, Timeouts, and Errors When Calling Token Endpoints in Spring Security Reactive OAuth2 Client

## 1. Lesson Objectives

In Spring Security - reactive, **OAuth2 Client** is more than declaring `client-id` and `client-secret`. When acquiring an access token, the client must call the Authorization Server's **Token Endpoint** over HTTP. If the environment uses internal CAs, mutual TLS, corporate proxies, high network latency, or an overloaded Token Endpoint, the application must tune **HTTPS/TLS, timeouts, connection pooling, error handling, and observability** in the right place.

This lesson focuses on the **token endpoint call** in WebFlux OAuth2 Client: `client_credentials` for service-to-service, and shows how to apply the same concepts to `authorization_code` and `refresh_token`. It is not a lesson on designing an OpenID Provider or implementing a Resource Server.

After this lesson, you will be able to:

1. Locate where the Token Endpoint sits in OAuth2 flows and distinguish it from the Authorization Endpoint, callback URLs, and Resource Server APIs.
2. Identify the proper reactive classes: `WebClientReactiveClientCredentialsTokenResponseClient`, `WebClientReactiveAuthorizationCodeTokenResponseClient`, `WebClientReactiveRefreshTokenTokenResponseClient`, `ReactiveOAuth2AccessTokenResponseClient`, and `ReactiveOAuth2AuthorizedClientManager`.
3. Use `setWebClient(...)` with `ReactorClientHttpConnector` and Reactor Netty `HttpClient` to customize connections **specifically for token requests**.
4. Preserve **certificate chain validation + hostname verification** over HTTPS, configure a truststore for internal CAs, and distinguish a truststore from an mTLS keystore.
5. Configure limits for **pool acquire, TCP connect, TLS handshake, response timeout, and overall token exchange deadline**; understand what each timeout measures.
6. Recognize `invalid_client`, `invalid_scope`, `invalid_grant`, 429/5xx, DNS/TCP/SSL, and timeout failures; separate **OAuth2 protocol** errors from **transport** errors.
7. Decide when **not to retry**, avoiding replaying authorization codes or flooding the Authorization Server.
8. Build a Java 17+ / Spring Boot 3.3.13 / WebFlux app using `client_credentials` against a local HTTPS Keycloak with a self-signed certificate and explicit truststore.
9. Test an operational endpoint with `WebTestClient` across successful issuance, provider rejections, network timeouts, and caller 401/403; understand how mock tests differ from E2E TLS.
10. Apply the rule **never leak access tokens or client secrets** in responses, logs, metrics, or traces, even on errors.
11. Distinguish configurations for OAuth2 Login, background jobs, and grant types so you never customize the wrong `WebClient`.
12. Design latency budgets, health/observability, resource isolation, and fail-closed behavior for production.

**Key takeaway:** Changing `spring.security.oauth2.client.provider.*.token-uri` only changes the **address**; it does not configure pooling, TLS trust, or HTTP client timeouts. Conversely, defining a shared `WebClient.Builder` does not guarantee OAuth2 token exchanges automatically adopt it. You must wire the customized `WebClient` into the **token response client** for the target grant type.

## 2. Where Does the Token Endpoint Appear?

### 2.1. Client Credentials: Machine to Machine

```text
Spring WebFlux Service                 Authorization Server
   |                                         |
   | 1. Needs access token to call API       |
   |                                         |
   | 2. POST /realms/learning/.../token      |
   |    grant_type=client_credentials        |
   |    Authorization: Basic <client-credentials>
   |---------------------------------------->|
   |                                         |
   | 3. Verifies client ID/secret/permissions|
   |<----------------------------------------|
   |  200 {access_token,token_type,expires_in}|
   |                                         |
   | 4. Client saves OAuth2AuthorizedClient  |
   |    then uses Bearer to call another API |
   |                                         |
Other Resource Server: Authorization: Bearer <access-token>
```

`client_credentials` involves no browser login, authorization code, `state`, or callback. It uses the **client application's identity**; typical uses are background jobs, data syncs, or server-to-server calls. Access tokens must still carry the proper audience and scopes for the Resource Server.

**Basic HTTP example:**

```http
POST /realms/learning/protocol/openid-connect/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-client-id-and-secret>

grant_type=client_credentials
```

A valid response might look like:

```json
{
  "access_token": "REDACTED",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "profile"
}
```

This is a **protocol illustration**, not a real access token. Never include `access_token`/`refresh_token` from the provider in the HTTP response of an operational check endpoint.

### 2.2. Authorization Code Grant

In OAuth2/OIDC login, the browser redirects to the Authorization Server and calls back to the Spring client with `code`. **The token exchange is still a backend-to-backend request**:

```text
Browser -> /oauth2/authorization/{registrationId} -> Provider login
Browser -> /login/oauth2/code/{registrationId}?code=...&state=...
WebFlux client -> POST Token Endpoint, grant_type=authorization_code
Provider -> access_token, id_token (if OIDC), ...
```

The token response client class for this grant is `WebClientReactiveAuthorizationCodeTokenResponseClient`. It also provides `setWebClient(...)`, yet **must be wired into OAuth2 Login**, not merely an isolated service manager if you use browser login.

Never blindly retry `authorization_code`: codes are short-lived and single-use, so a failed or timed-out exchange may have already consumed the code even if the client missed the response. For users, the fix is normally to **restart the authorization flow**, not resend the same code five times.

### 2.3. Refresh Token Grant

When an access token is nearing expiration, the Client can use a refresh token (if issued) to obtain a new token. The matching reactive class is `WebClientReactiveRefreshTokenTokenResponseClient`. Refresh tokens can be **rotated** and single-use per provider policy; retrying after a request timeout can invalidate the rotation chain.

`client_credentials` normally **does not rely on refresh tokens** like user logins. The client manager requests a new access token when the old one approaches expiry; manager calls do not always hit the Token Endpoint because the authorized client is cached.

### 2.4. Three Error Categories That Must Be Separated

| Category | Examples | Decision |
| --- | --- | --- |
| OAuth2 protocol rejection | `invalid_client`, `invalid_scope`, `invalid_grant` | Identity/grant/policy failure; usually no automatic retry |
| HTTP/provider availability | 429, 502/503/504, or malformed payload | Check rate limits/SLO; bounded retries if policy permits |
| Transport/TLS | DNS failure, TCP connect failure, unknown certificate, hostname mismatch, TLS handshake timeout | No successful OAuth2 response; fix connectivity/trust/certs/network |

**Never equate HTTP 401 from the Token Endpoint with HTTP 401 from a Resource Server.** A token endpoint 401 usually means client authentication failed; a Resource Server 401 usually means the Bearer token is invalid or missing. Check the path and error code before acting.

## 3. Which Components Actually Send the Token Request?

Spring Security WebFlux uses a chain:

```text
Application service / WebClient with OAuth2
            |
            v
ReactiveOAuth2AuthorizedClientManager
            |
            v
ReactiveOAuth2AuthorizedClientProvider
   (client_credentials, authorization_code, refresh_token...)
            |
            v
ReactiveOAuth2AccessTokenResponseClient<TGrantRequest>
            |
            v
WebClientReactive*TokenResponseClient
            |
            v
WebClient + ReactorClientHttpConnector
            |
            v
Reactor Netty HttpClient (TLS, pool, timeouts, proxy)
            |
            v
HTTPS Token Endpoint
```

Classes and roles:

| Type | Purpose |
| --- | --- |
| `ReactiveClientRegistrationRepository` | Supplies `ClientRegistration`, including token URI and client auth method |
| `OAuth2AuthorizeRequest` | Asks the manager to authorize a registration with a principal key |
| `ReactiveOAuth2AuthorizedClientManager` | Coordinates authorization, cache/re-authorization, and persistence |
| `ClientCredentialsReactiveOAuth2AuthorizedClientProvider` | Handles the `client_credentials` grant |
| `WebClientReactiveClientCredentialsTokenResponseClient` | HTTP POST to Token Endpoint, parses OAuth2 responses |
| `WebClientReactiveAuthorizationCodeTokenResponseClient` | Token exchange for authorization code |
| `WebClientReactiveRefreshTokenTokenResponseClient` | Refresh token exchange |
| `ReactorClientHttpConnector` | Connects Spring `WebClient` to Reactor Netty `HttpClient` |
| `ConnectionProvider` | Connection pool and acquire wait controls |
| `SslContextBuilder` + `TrustManagerFactory` | Defines trusted CA sources for TLS |
| `ServerHttpSecurity` | Protects inbound HTTP; **does not** alter outbound WebClient token requests |
| `OAuth2AuthorizationException` | Spring Security OAuth2 exception carrying an `OAuth2Error` |

Spring Security 6.3+ documentation allows exposing a `ReactiveOAuth2AccessTokenResponseClient<OAuth2ClientCredentialsGrantRequest>` bean so the framework wires it into default components. In the example below, we **deliberately construct the manager manually** and call `provider.setAccessTokenResponseClient(...)` so the exact wiring is visible and works inside a background service without a `ServerWebExchange`.

**Never use Servlet types** like `DefaultClientCredentialsTokenResponseClient`, synchronous `OAuth2AuthorizedClientManager`, or `RestTemplate` in WebFlux. Similar names belong to a different stack. Likewise, never wrap a blocking HTTP call in `Mono.just(restTemplate...)`, as the call executes synchronously before the publisher is even subscribed.

## 4. HTTPS for Token Endpoints: Trust Does Not Mean Skipping Verification

### 4.1. What Does TLS Verify?

When the Client calls `https://auth.example.test/oauth2/token`, client TLS must check:

1. Hostname resolution and TCP connectivity succeed.
2. TLS handshake succeeds with mutually supported protocol/cipher suites.
3. The certificate chain leads to a trusted CA or properly configured pin/truststore.
4. Certificates are within their validity window and violate no relevant policies.
5. **Hostname verification**: the certificate's SAN matches the hostname the Client actually connects to.
6. Client mTLS certificate checks **if** required by the Token Endpoint, in addition to OAuth2 client authentication.

**CA trust != hostname verification.** A certificate signed by a trusted CA whose SAN lists only `api.example.test` must still fail when the client connects to `https://auth.example.test`. **mTLS != `client_secret_basic`**: both can coexist, where one is the TLS client certificate and the other is OAuth2 token-endpoint client authentication.

### 4.2. Production Public CAs

If the Authorization Server uses a certificate chain from a public CA already trusted by the runtime, the default HTTP client handles TLS validation. Not every environment needs a custom truststore.

Never configure `trustManager(InsecureTrustManagerFactory.INSTANCE)` or `verifyHostname(false)` to silence test errors. That opens the door to **man-in-the-middle** attacks: an attacker could impersonate the Token Endpoint, steal client credentials, and issue forged tokens.

### 4.3. Internal / Self-Signed: Trust Only the Required CA/Cert

When an organization uses a private CA or a local self-signed lab cert:

- Create a `PKCS12` truststore containing the trusted root/intermediate CAs; a lab can import a self-signed server cert.
- Load the truststore using Java `KeyStore` + `TrustManagerFactory`.
- Pass it to Netty's `SslContextBuilder.forClient().trustManager(...)`.
- Use `HttpClient.secure(sslSpec -> sslSpec.sslContext(...))`. In Reactor Netty 1.1.x, the `secure` overload taking a `Consumer` enables hostname verification by default; confirm this with a negative hostname-mismatch test.
- Keep the token URI on HTTPS with a hostname matching the SAN.
- Manage truststore/keystore passwords via a secrets manager or environment variables, never committing them to Git.

**Never turn a truststore into a dumping ground for arbitrary user-uploaded certificates.** Trust anchors must go through approval and lifecycle/rotation management.

### 4.4. Truststore vs. mTLS Keystore

| Store | Typically Contains | Purpose |
| --- | --- | --- |
| Truststore | Public CA certificates / trusted server certs | Verifies the Token Endpoint **server** |
| Client keystore (mTLS) | Client private key and certificate chain | Proves **client** identity during TLS handshake |
| OAuth2 client secret | Secret registered at the Authorization Server | Client authentication at the OAuth2 token request layer |
| Access token | Permissions for resource APIs | Bearer token sent to Resource Server, not a TLS credential |

If the Token Endpoint requires mTLS, load the client key/certificate via `KeyManagerFactory` and `SslContextBuilder.keyManager(...)`. Never copy the truststore into the keyManager or store private keys in lesson docs.

### 4.5. TLS Failures Must Fail Closed

Common failures:

| Symptom | Likely Cause | Action |
| --- | --- | --- |
| `SSLHandshakeException: PKIX path building failed` | Untrusted CA/server chain | Import the right CA into truststore; inspect chain |
| `No subject alternative names matching ...` | Token URI host mismatches SAN | Fix DNS/URL/cert SAN |
| `certificate expired` | Server/CA certificate expired | Rotate certificate; never disable checks |
| `handshake timed out` | Slow/broken SSL negotiation, network, or proxy | Check infrastructure and handshake timeout budget |
| `Connection refused` | No listener or wrong port | Check token URI, health, and network |
| `UnknownHostException` | Broken DNS | Check DNS, VPN/proxy, pod DNS |
| `invalid_client` | Mismatched client ID/secret/auth method | Fix OAuth2 registration, not TLS |

Adjusting timeouts alone will never fix a certificate trust failure. In particular, **never auto-retry hostname/cert errors**, since retrying only adds load without making the certificate valid.

## 5. Timeouts: Multiple Different Clocks

A token request can pass through:

```text
Authorization call
   |
   +-- wait for pool connection      pending acquire timeout
   +-- DNS lookup                    resolver timeout
   +-- open TCP                      CONNECT_TIMEOUT_MILLIS
   +-- TLS handshake                 SSL handshakeTimeout
   +-- send POST form data
   +-- wait/read HTTP response       responseTimeout
   +-- decode JSON, OAuth2 errors
   |
   +-- total exchange (from subscribe) Mono.timeout / overall deadline
```

### 5.1. Layered Timeouts

| Timeout | Typical Configuration | What Does It Bound? |
| --- | --- | --- |
| Pool acquire | `ConnectionProvider.pendingAcquireTimeout(Duration)` | Waiting for a connection slot in the pool |
| Pool queue cap | `pendingAcquireMaxCount(n)` | Number of queued waiters, preventing unbounded queues |
| TCP connect | `ChannelOption.CONNECT_TIMEOUT_MILLIS` | Establishing the TCP connection |
| TLS handshake | `HttpClient.secure(ssl -> ssl.handshakeTimeout(...))` | Incomplete TLS handshakes |
| HTTP response | `HttpClient.responseTimeout(Duration)` | Waiting/reading response from peer per Reactor Netty semantics |
| Overall token exchange | `Mono.timeout(Duration)` around `getTokenResponse` | Entire time waiting for publisher to emit token response or error |
| Resource Server request | **Separate** outbound `WebClient` config | Latency calling the API after obtaining a token |

**Do not simply add timeouts together and assume maximum latency equals that exact sum.** Some limits apply per phase; pooled connections skip DNS/connect/TLS, whereas the overall deadline covers all stages once subscribed.

Reactor Netty's `responseTimeout` bounds response/read timing per request mechanics, not replacing an absolute deadline covering pool wait, DNS, TLS, and body decoding. Wrap **`getTokenResponse`** in `Mono.timeout`, not merely a `WebClient` `next.exchange(request)` filter, because `exchange` may complete after response headers arrive while the token body is still decoding.

### 5.2. Budget Example

For a system needing timely error responses:

```text
Pending pool acquire:       1 second
TCP connect:                2 seconds
TLS handshake:              4 seconds
HTTP response timeout:      4 seconds
Overall token deadline:     9 seconds
```

These are **illustrative values to tune against SLOs**, not universal defaults. The 9-second deadline can cut off earlier than the theoretical sum of individual steps; that is deliberate to avoid waiting indefinitely. If an endpoint has a 2-second SLO, the time budget must be shorter and aligned with any retry budget. On cross-region links or slow PKI, measure real p95/p99 latencies and adjust.

### 5.3. Reactive Cancellation Does Not Roll Back the Server

When `Mono.timeout` emits `TimeoutException`, the upstream subscriber is canceled. Yet the request may already have reached the Authorization Server and a token may have been issued, with the response merely arriving late. **Never** assume "timeout guarantees the server did nothing".

This matters especially for:
- `authorization_code`: the code may already be consumed.
- `refresh_token`: rotation may already have occurred.
- `client_credentials`: repeated retries can mint multiple tokens, burning quota and adding load.

Therefore, retry policies must account for **idempotency/grant semantics** and token cache state rather than blindly applying `Retry.backoff(...)`.

### 5.4. Connection Pool and Backpressure

Under heavy load, concurrent requests needing tokens can cause:
- TCP/TLS connection bursts;
- Large pending-acquire queues;
- Authorization Server 429 or 503 responses;
- Cache stampedes when tokens expire simultaneously;
- Socket exhaustion and event-loop stalls if blocking code creeps in.

Bounding the connection pool, pending queue, and request concurrency is essential. Too small a pool causes timeouts even when the provider is healthy; too large a pool can overload the provider. Measure `pendingAcquire`, handshake, response latency, and actual token exchanges—not just overall API HTTP latency.

**Cache tokens properly:** `AuthorizedClientManager` / `AuthorizedClientService` normally reuses unexpired tokens for the same `(registrationId, principal)` key. Never hit the token endpoint before **every** business request unnecessarily, and never pass `principal("random-UUID")` per call, which defeats caching.

## 6. Token Endpoint Errors and Fail-Closed Behavior

### 6.1. OAuth2 Error Responses

Per OAuth2, the Authorization Server may return error JSON:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "error": "invalid_client",
  "error_description": "Client authentication failed"
}
```

Typical error codes:

| OAuth2 Error | Common Meaning | Retry? |
| --- | --- | --- |
| `invalid_client` | Wrong client ID/secret, auth method, or disabled client | **No**; fix config/secret |
| `invalid_grant` | Bad/expired/replayed code or refresh token, redirect/PKCE mismatch | **No** with the same code/refresh token |
| `invalid_scope` | Scope unauthorized or nonexistent | **No**; fix scopes/permissions |
| `unsupported_grant_type` | Provider does not permit the grant | **No**; fix registration/IdP |
| `invalid_request` | Missing or invalid form parameters | **No**; fix payload/wiring |
| `unauthorized_client` | Client not permitted to use grant/scope | **No**; fix IdP policy |

In Spring Security, OAuth2 protocol errors can be represented by `OAuth2AuthorizationException` and `OAuth2Error`; wrappers may vary by grant/client/version. When writing custom error handling, inspect the **cause chain and test against your real version**, never assuming every 401/400/429 maps to one single exception class.

### 6.2. HTTP 429 and 5xx

The Token Endpoint can return:
- 429 Too Many Requests: quota/rate limiting, potentially with `Retry-After`.
- 500 Internal Server Error: provider failure.
- 502/503/504: gateway/ingress/upstream failure.
- 200 with malformed JSON or missing `access_token`: protocol/schema error; never treat as a valid token.

**Bounded retries** may be considered when safe/idempotent, using exponential backoff + jitter + an upper deadline, honoring `Retry-After` and circuit breakers. On a 429 triggered by your own app's overload, immediate retries only worsen the problem.

**Never apply one retry policy across all grants.** Authorization codes and rotating refresh tokens carry replay risks; `client_credentials` requests are more stateless yet still incur quota and cost. Retry only with clear provider/contract justification and tight bounds.

### 6.3. Transport Errors

Errors like DNS failures, TCP connection refused, TLS trust failures, `WebClientRequestException`/Netty exceptions, or `TimeoutException` are **not** `invalid_client`. Map them to internal error categories like `TOKEN_ENDPOINT_UNAVAILABLE`/`TOKEN_TIMEOUT`, emit metrics, and return an appropriate error to callers—never fabricate `invalid_grant` just to unify formats.

If acquiring a token fails, **never call the Resource Server as if authenticated**. Never return an expired old token, never mint a fake bearer token, and never swallow the error into `Mono.empty()` where downstream code might assume authorization succeeded.

### 6.4. Keeping Logs and Responses Safe

Safe to log:
- `registrationId`, provider alias, category (`timeout`/`tls_error`/`oauth_error`/`http_5xx`);
- HTTP status, latency, correlation ID;
- Allowlisted sanitized OAuth2 `error_code`;
- Pool active/pending counts and timeout counts.

Never log:
- `Authorization: Basic ...` / `client-secret`;
- Token response bodies containing access/refresh tokens;
- Authorization codes, `code_verifier`, client assertions, DPoP proofs;
- Raw TLS private keys or keystore passwords;
- Session cookies or raw ID Tokens;
- Full request/response wiretaps of the token endpoint.

**Especially:** `HttpClient.wiretap(true)` or an `ExchangeFilterFunction` logging headers/bodies can dump **full credentials and tokens**. Never enable wiretaps or debug body logging in production; in tests, use fake data and redaction.

## 7. Complete Example: Spring Boot WebFlux + HTTPS Keycloak + Token Timeouts

The hands-on lab uses:
- **Java 17+**, Spring Boot **3.3.13**, Gradle;
- A WebFlux server at `http://localhost:8080` allowing only one demo OPS user to call the probe endpoint;
- **HTTPS Keycloak** Authorization Server at `https://localhost:9443`;
- Client registration `machine` using `client_credentials` and `client_secret_basic`;
- A `PKCS12` TLS truststore containing the lab's self-signed certificate;
- A dedicated outbound token `WebClient` with pool, connect/handshake/response/overall timeouts;
- Service-tier `ReactiveOAuth2AuthorizedClientManager`, independent of browser `ServerWebExchange`;
- A check endpoint returning **status + `expiresAt`**, **never** the raw access token.

**Security note:** the local setup uses a lab private key and password solely for learning. Never expose Keycloak dev mode or public ports, and never deploy the token probe endpoint or `{noop}` passwords to production.

### 7.1. Directory Tree

```text
reactive-token-endpoint-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/TokenTlsApplication.java
      java/example/TokenClientConfig.java
      java/example/TokenProbeController.java
      resources/application.yml
    test/
      java/example/TokenProbeControllerTests.java
  tls/
    (cert.pem, key.pem, truststore.p12 generated locally)
```

Never commit `tls/key.pem` or production truststores/private keys. Self-signed lab certs are trusted **only in the demo environment**.

### 7.2. settings.gradle

```groovy
rootProject.name = 'reactive-token-endpoint-lab'
```

### 7.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Gradle 7.5+/8.x and Java 17+ are compatible with Spring Boot 3.3.13; prefer a pinned Gradle Wrapper in real projects. **Never** add Servlet `spring-boot-starter-web`, `RestTemplate`, or synchronous token clients.

### 7.4. application.yml

Create `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          machine:
            provider: machine-idp
            client-id: reactive-machine
            client-secret: ${LAB_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: []
        provider:
          machine-idp:
            token-uri: https://localhost:9443/realms/learning/protocol/openid-connect/token

lab:
  token:
    trust-store: ${LAB_TOKEN_TRUSTSTORE:}
    trust-store-password: ${LAB_TOKEN_TRUSTSTORE_PASSWORD:}
```

With `client_credentials`, only a valid token URI is needed; no authorization URI, callback, login page, or OIDC issuer discovery is needed here. Omitting `issuer-uri` is intentional to avoid extra TLS HTTP discovery calls at startup. **With real OIDC login**, issuer discovery/JWK/userinfo also require proper trust policies; customizing the token endpoint `WebClient` alone does not configure all other outbound HTTP clients.

`scope: []` is a demo choice letting the IdP assign default client scopes; Keycloak may attach scopes per realm config. In production, specify least-privilege scopes and enforce proper audience/permission mappings.

`LAB_CLIENT_SECRET` must be the real secret of the Keycloak client. `LAB_TOKEN_TRUSTSTORE` and its password are for the custom CA only. If left blank, Java/Netty uses default trust anchors, which will reject the lab's self-signed cert—matching fail-closed behavior.

### 7.5. TokenTlsApplication.java

Create `src/main/java/example/TokenTlsApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails
        .MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
public class TokenTlsApplication {

    public static void main(String[] args) {
        SpringApplication.run(TokenTlsApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/ops/token-check").hasRole("OPS")
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("ops")
                .password("{noop}lab-only")
                .roles("OPS")
                .build();
        return new MapReactiveUserDetailsService(user);
    }
}
```

`/ops/token-check` is a **demo endpoint protected by HTTP Basic**. Never leave it public where callers could overload the Token Endpoint. `{noop}lab-only` is strictly for localhost lab use; real apps need a proper password encoder, inbound HTTPS, strict authorization, and rate limiting—or omit such an endpoint entirely.

### 7.6. TokenClientConfig.java — The Core Piece

Create `src/main/java/example/TokenClientConfig.java`:

```java
package example;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.time.Duration;

import javax.net.ssl.TrustManagerFactory;

import io.netty.channel.ChannelOption;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.client
        .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
        .ClientCredentialsReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
        .InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.endpoint
        .OAuth2ClientCredentialsGrantRequest;
import org.springframework.security.oauth2.client.endpoint
        .ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint
        .WebClientReactiveClientCredentialsTokenResponseClient;
import org.springframework.security.oauth2.client.registration
        .ReactiveClientRegistrationRepository;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class TokenClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider tokenConnectionPool() {
        return ConnectionProvider.builder("oauth-token-pool")
                .maxConnections(10)
                .pendingAcquireMaxCount(30)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .maxIdleTime(Duration.ofSeconds(30))
                .build();
    }

    @Bean
    WebClient tokenEndpointWebClient(
            ConnectionProvider tokenConnectionPool,
            @Value("${lab.token.trust-store:}") String trustPath,
            @Value("${lab.token.trust-store-password:}") String trustPass)
            throws Exception {

        SslContextBuilder sslBuilder = SslContextBuilder.forClient();

        if (!trustPath.isBlank()) {
            KeyStore store = KeyStore.getInstance("PKCS12");

            try (InputStream input =
                    Files.newInputStream(Path.of(trustPath))) {
                store.load(input, trustPass.toCharArray());
            }

            TrustManagerFactory trustManager =
                    TrustManagerFactory.getInstance(
                            TrustManagerFactory.getDefaultAlgorithm());
            trustManager.init(store);
            sslBuilder.trustManager(trustManager);
        }

        // Declare trust anchors; NEVER disable certificate
        // validation or hostname verification.
        SslContext sslContext = sslBuilder.build();

        HttpClient netty = HttpClient.create(tokenConnectionPool)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
                .responseTimeout(Duration.ofSeconds(4))
                .followRedirect(false)
                .secure(ssl -> ssl
                        .sslContext(sslContext)
                        .handshakeTimeout(Duration.ofSeconds(4)));

        return WebClient.builder()
                .clientConnector(new ReactorClientHttpConnector(netty))
                .build();
    }

    @Bean
    ReactiveOAuth2AccessTokenResponseClient<OAuth2ClientCredentialsGrantRequest>
            clientCredentialsTokenResponseClient(
                    WebClient tokenEndpointWebClient) {

        var delegate =
                new WebClientReactiveClientCredentialsTokenResponseClient();

        // Preserve Spring Security's default converter/form encoding
        // and OAuth2 error parsing.
        delegate.setWebClient(tokenEndpointWebClient);

        // Deadline wrapping the token exchange publisher itself.
        return request -> delegate.getTokenResponse(request)
                .timeout(Duration.ofSeconds(9));
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager machineAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AccessTokenResponseClient<OAuth2ClientCredentialsGrantRequest>
                    clientCredentialsTokenResponseClient) {

        var provider =
                new ClientCredentialsReactiveOAuth2AuthorizedClientProvider();
        provider.setAccessTokenResponseClient(
                clientCredentialsTokenResponseClient);

        var store = new InMemoryReactiveOAuth2AuthorizedClientService(
                registrations);

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, store);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

**Layer-by-layer explanation:**

1. `ConnectionProvider` caps the token HTTP client at 10 connections, 30 pending requests, and 1 second waiting for a pool slot. Benchmark numbers for your workload; no single value fits every app.
2. `SslContextBuilder.forClient()` preserves default trust policies when `trustPath` is empty. When a `PKCS12` path is set, `TrustManagerFactory` validates server certs against imported trust anchors.
3. Never use `InsecureTrustManagerFactory` or disable hostname verification. Reactor Netty's `HttpClient.secure(Consumer)` enables hostname verification by default; verify mismatches in your target environment.
4. `CONNECT_TIMEOUT_MILLIS` is TCP connect timeout; `handshakeTimeout` is TLS timeout; `responseTimeout` bounds response waiting; `pendingAcquireTimeout` bounds pool wait time.
5. `followRedirect(false)` stops HTTP token requests from sending credentials across unexpected redirects. Treat a 302 from a token endpoint as a config/provider error rather than following to another domain.
6. `WebClient.builder().clientConnector(...)` creates a `WebClient` **dedicated exclusively to the token endpoint**, not shared by business HTTP calls.
7. `WebClientReactiveClientCredentialsTokenResponseClient` preserves Spring Security's `application/x-www-form-urlencoded` encoding, Basic client authentication, and OAuth2 response/error parsing.
8. `setWebClient(tokenEndpointWebClient)` plugs the HTTPS/timeout connector into the exact component sending the POST.
9. `getTokenResponse(request).timeout(9s)` sets a deadline for the **full token exchange publisher**, not just until response headers arrive.
10. `ClientCredentialsReactiveOAuth2AuthorizedClientProvider.setAccessTokenResponseClient(...)` ensures the manager actually uses the customized token client.
11. `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` runs in the **service/background tier without needing `ServerWebExchange`**. It differs from `DefaultReactiveOAuth2AuthorizedClientManager` used in web contexts.
12. `InMemoryReactiveOAuth2AuthorizedClientService` fits labs and single-instance apps only. Multi-node production must evaluate shared storage, token caching/rotation, and failure risk rather than letting every instance hit the IdP unchecked.

**Do not slap `.retryWhen(...)` onto every `getTokenResponse` in the lab.** Design retries deliberately per error/grant/provider with time budgets and replay safety—never treat availability workarounds as changes to OAuth2 semantics.

### 7.7. TokenProbeController.java — Never Return the Access Token

Create `src/main/java/example/TokenProbeController.java`:

```java
package example;

import java.util.Map;
import java.util.concurrent.TimeoutException;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.client
        .OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class TokenProbeController {

    private final ReactiveOAuth2AuthorizedClientManager manager;

    public TokenProbeController(
            ReactiveOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @GetMapping("/ops/token-check")
    public Mono<ResponseEntity<Map<String, String>>> check() {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("machine")
                        .principal("service-probe")
                        .build();

        return manager.authorize(request)
                .map(client -> ResponseEntity.ok(
                        Map.of(
                                "status", "authorized",
                                "expiresAt", String.valueOf(
                                        client.getAccessToken()
                                                .getExpiresAt()))))
                .switchIfEmpty(Mono.just(
                        ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                                .body(Map.of(
                                        "status", "no_authorized_client"))))
                .onErrorResume(TimeoutException.class, error ->
                        Mono.just(ResponseEntity
                                .status(HttpStatus.GATEWAY_TIMEOUT)
                                .body(Map.of("status", "token_timeout"))))
                .onErrorResume(OAuth2AuthorizationException.class, error ->
                        Mono.just(ResponseEntity
                                .status(HttpStatus.BAD_GATEWAY)
                                .body(Map.of(
                                        "status", "oauth2_rejected",
                                        "code", safeCode(
                                                error.getError()
                                                        .getErrorCode())))))
                .onErrorResume(Exception.class, error ->
                        Mono.just(ResponseEntity
                                .status(HttpStatus.SERVICE_UNAVAILABLE)
                                .body(Map.of(
                                        "status", "token_endpoint_unavailable"))));
    }

    private static String safeCode(String providerCode) {
        return switch (providerCode) {
            case "invalid_client" -> "invalid_client";
            case "invalid_scope" -> "invalid_scope";
            case "invalid_grant" -> "invalid_grant";
            case "unauthorized_client" -> "unauthorized_client";
            default -> "oauth2_token_error";
        };
    }
}
```

**Why use principal `service-probe`?** In `client_credentials`, the manager uses the principal key to store/look up the authorized client. This is a **fixed internal service key**, not an OAuth2-logged-in user. Generating random principals per request creates multiple cache keys and causes token churn.

**HTTP 502/503/504 codes in the demo are application choices**, not mandatory OAuth2 mappings:
- `502 Bad Gateway` when the provider returns an OAuth2 rejection and the app acts as an IdP-dependent facade;
- `503 Service Unavailable` on unclassified transport/TLS/connection errors;
- `504 Gateway Timeout` when the token deadline is exceeded;
- `200` when a valid authorized client is obtained.

In real apps, persistent configuration errors like `invalid_client` should fire operational alerts rather than client retries. Never let external callers use such an endpoint to probe IdP status or secrets. You can omit this endpoint altogether and monitor tokens through metrics and the business service itself.

**Never expose:** `client.getAccessToken().getTokenValue()`. Even an OPS-role endpoint must not return raw tokens, as they are credentials for accessing other resources.

### 7.8. Generating the Lab HTTPS Certificate and Truststore

Linux/macOS example with OpenSSL and JDK 17+ installed; generate a self-signed cert with **SAN for localhost**:

```bash
mkdir -p tls

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout tls/key.pem \
  -out tls/cert.pem \
  -days 7 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

**Strictly never use the lab `key.pem` in production.** It is a private key—restrict filesystem permissions and never commit it.

Import the public certificate into the truststore for the **WebFlux Client**:

```bash
keytool -importcert -noprompt \
  -alias keycloak-local \
  -file tls/cert.pem \
  -keystore tls/truststore.p12 \
  -storetype PKCS12 \
  -storepass changeit
```

- `tls/cert.pem` is the public certificate trusted in the lab.
- `tls/key.pem` is the **Keycloak TLS server's private key**, mounted only into the container.
- `tls/truststore.p12` contains no private key from this import step.
- `changeit` is a lab password, **not** recommended for production.
- On Windows PowerShell, place the OpenSSL/keytool command on one line or use PowerShell's line continuation (`\``) instead of copying bash backslashes (`\`).

### 7.9. Running Keycloak over HTTPS

From the project directory containing `tls/cert.pem`/`tls/key.pem`:

```bash
docker run --rm --name keycloak-token-lab \
  -p 127.0.0.1:9443:8443 \
  -v "$PWD/tls/cert.pem:/opt/keycloak/conf/lab-cert.pem:ro" \
  -v "$PWD/tls/key.pem:/opt/keycloak/conf/lab-key.pem:ro" \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.8.2 \
  start-dev \
  --hostname=https://localhost:9443 \
  --https-port=8443 \
  --https-certificate-file=/opt/keycloak/conf/lab-cert.pem \
  --https-certificate-key-file=/opt/keycloak/conf/lab-key.pem
```

- Host exposes port 9443 on `127.0.0.1` only; backend app runs on 8080.
- Keycloak listens on HTTPS port 8443 internally, mapped to host port 9443.
- `--hostname=https://localhost:9443` makes Keycloak emit URLs matching the public host/issuer.
- Keycloak `start-dev` uses development defaults and is **not** for production.
- If Docker on Windows does not mount `$PWD` cleanly for your shell, substitute an explicit absolute host path and ensure both PEM files exist and are readable.

Open `https://localhost:9443/admin/`. The browser may warn about the untrusted self-signed cert; you can proceed in the lab to configure it, while **never** using "ignore TLS cert" in the Spring OAuth2 HTTP client. WebFlux trusts only that certificate via the created truststore.

### 7.10. Creating the Realm and Confidential Service Client

In the Keycloak Admin Console:

1. Log in as the lab admin.
2. Create realm `learning`.
3. Inside that realm, choose **Clients -> Create client**, type OpenID Connect.
4. Set **Client ID = reactive-machine**.
5. Enable **Client authentication** (confidential client).
6. Enable **Service accounts roles** (service account / client credentials). In newer Keycloak versions, this sits under capability flow/settings.
7. Disable Standard flow / authorization code if unneeded for this client-credentials lab.
8. Open the **Credentials** tab and copy the client secret. Set `LAB_CLIENT_SECRET` in Spring's environment; never copy it into source/repos.
9. If resource-specific scopes/audiences are needed, configure client scopes and service account roles in Keycloak; never grant realm-admin permissions to the lab client.
10. The realm's token endpoint is:

```text
https://localhost:9443/realms/learning/protocol/openid-connect/token
```

Verify TLS and endpoint reachability with:

```bash
curl -sS --cacert tls/cert.pem \
  -o /dev/null \
  -w "token endpoint HTTP=%{http_code}\n" \
  https://localhost:9443/realms/learning/protocol/openid-connect/token
```

GET to the token endpoint may return 405 or 400 because POST is required. This command verifies **certificate/hostname/TCP**, not successful token issuance.

Test POST client credentials **without printing the token body** (lab only):

```bash
curl -sS --cacert tls/cert.pem \
  -o /dev/null \
  -w "token POST HTTP=%{http_code}\n" \
  -u "reactive-machine:$LAB_CLIENT_SECRET" \
  -d "grant_type=client_credentials" \
  https://localhost:9443/realms/learning/protocol/openid-connect/token
```

If `LAB_CLIENT_SECRET` is set properly and the Keycloak client permits service accounts, expect HTTP 200. **Limitation** of `curl -u`: credentials can appear in shell history or process listings depending on your shell. Use only in local labs; production uses secrets managers and secure credential handling, never raw CLI secrets.

### 7.11. Running the WebFlux App

Linux/macOS:

```bash
export LAB_CLIENT_SECRET='replace-with-keycloak-client-secret'
export LAB_TOKEN_TRUSTSTORE="$PWD/tls/truststore.p12"
export LAB_TOKEN_TRUSTSTORE_PASSWORD='changeit'

gradle bootRun
```

On Windows PowerShell, set the equivalent variables:

```powershell
$env:LAB_CLIENT_SECRET = "replace-with-keycloak-client-secret"
$env:LAB_TOKEN_TRUSTSTORE = "C:\path\to\tls\truststore.p12"
$env:LAB_TOKEN_TRUSTSTORE_PASSWORD = "changeit"

gradle bootRun
```

`C:\path\to\tls\truststore.p12` is an **example path to replace with your real path**. If the project has a Gradle Wrapper, use `./gradlew bootRun` or `gradlew.bat bootRun`.

**Important:** If Spring Boot runs **inside another container**, its `https://localhost:9443` will not point to Keycloak on the host. Use proper Docker network hostnames/ports and ensure the certificate SAN matches the hostname the Client actually calls.

### 7.12. Calling the Probe Endpoint

```bash
curl -i http://localhost:8080/ops/token-check

curl -i -u ops:lab-only \
  http://localhost:8080/ops/token-check
```

- Without credentials: **401 Basic challenge** from inbound Spring Security.
- Valid demo ops user: backend calls the manager to acquire a token if uncached and returns a response **with no token inside**.
- Example body on success:

```json
{
  "status": "authorized",
  "expiresAt": "2026-11-07T09:00:00Z"
}
```

**The `expiresAt` timestamp is only a format example**; real values depend on token TTL and runtime clock. Never assert absolute timestamps in unit tests.

If the provider fails, the token request may return:
- 502 + `{"status":"oauth2_rejected","code":"invalid_client"}` for Spring-classified OAuth2 errors;
- 503 + `{"status":"token_endpoint_unavailable"}` for TLS/connect/network failures;
- 504 + `{"status":"token_timeout"}` for deadline timeouts;
- 502 + `{"status":"no_authorized_client"}` if the manager completes empty.

Controller status mappings are a **demo contract**, not defaults of Spring Security or RFC 6749.

### 7.13. Observing Caching

Call `/ops/token-check` twice in a row. Because the manager uses principal key `service-probe` and the service stores the authorized client, the second call **can reuse the unexpired access token** without necessarily POSTing to the Token Endpoint again.

To test timeouts or `invalid_client` against live Keycloak, trigger a fresh token acquisition in the **lab**: restart the app (clearing the in-memory authorized-client cache), wait for expiration, or use a test setup controlling the cache. Do not assume changing a secret immediately forces a Token Endpoint call while a valid token remains cached.

In production, coordinate refresh/caching across instances per policy to prevent token stampedes. Clock skew on token expiration causes the client to request a replacement slightly ahead of `exp`, preventing near-expired tokens from failing at APIs.

## 8. Testing with WebTestClient — HTTP Error Contract

To test 200/401/502/503/504 **without depending on a running Keycloak**, mock `ReactiveOAuth2AuthorizedClientManager`. This tests the **controller and inbound Spring Security**, without proving real truststore/TLS behavior; TLS is tested separately in section 9.

Create `src/test/java/example/TokenProbeControllerTests.java`:

```java
package example;

import java.time.Instant;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration
        .ClientRegistration;
import org.springframework.security.oauth2.core
        .AuthorizationGrantType;
import org.springframework.security.oauth2.core
        .OAuth2AccessToken;
import org.springframework.security.oauth2.core
        .OAuth2AuthorizationException;
import org.springframework.security.oauth2.core
        .OAuth2Error;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class TokenProbeControllerTests {

    @Autowired
    WebTestClient client;

    @MockBean
    ReactiveOAuth2AuthorizedClientManager manager;

    @Test
    void missingInboundCredentialsIs401() {
        client.get().uri("/ops/token-check")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authorizedResponseDoesNotExposeRawToken() {
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
                .thenReturn(Mono.just(testAuthorizedClient()));

        client.get().uri("/ops/token-check")
                .headers(h -> h.setBasicAuth("ops", "lab-only"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("authorized")
                .jsonPath("$.access_token").doesNotExist();
    }

    @Test
    void tokenDeadlineMapsTo504() {
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
                .thenReturn(Mono.error(
                        new TimeoutException("token request timed out")));

        client.get().uri("/ops/token-check")
                .headers(h -> h.setBasicAuth("ops", "lab-only"))
                .exchange()
                .expectStatus().isEqualTo(504)
                .expectBody()
                .jsonPath("$.status").isEqualTo("token_timeout");
    }

    @Test
    void invalidClientMapsTo502WithoutSecret() {
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
                .thenReturn(Mono.error(
                        new OAuth2AuthorizationException(
                                new OAuth2Error(
                                        "invalid_client",
                                        "secret must not be echoed",
                                        null))));

        client.get().uri("/ops/token-check")
                .headers(h -> h.setBasicAuth("ops", "lab-only"))
                .exchange()
                .expectStatus().isEqualTo(502)
                .expectBody()
                .jsonPath("$.code").isEqualTo("invalid_client");
    }

    @Test
    void transportFailureMapsTo503() {
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
                .thenReturn(Mono.error(
                        new IllegalStateException("simulated TLS failure")));

        client.get().uri("/ops/token-check")
                .headers(h -> h.setBasicAuth("ops", "lab-only"))
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectBody()
                .jsonPath("$.status")
                .isEqualTo("token_endpoint_unavailable");
    }

    private static OAuth2AuthorizedClient testAuthorizedClient() {
        ClientRegistration registration =
                ClientRegistration.withRegistrationId("machine")
                        .clientId("test-client")
                        .clientSecret("test-secret")
                        .authorizationGrantType(
                                AuthorizationGrantType.CLIENT_CREDENTIALS)
                        .tokenUri("https://localhost:9443/token")
                        .build();

        OAuth2AccessToken token =
                new OAuth2AccessToken(
                        OAuth2AccessToken.TokenType.BEARER,
                        "TOKEN_ONLY_FOR_UNIT_TEST",
                        Instant.now(),
                        Instant.now().plusSeconds(600));

        return new OAuth2AuthorizedClient(
                registration, "service-probe", token);
    }
}
```

Run:

```bash
gradle test
```

**Test framework note:** `@MockBean` belongs to Spring Boot 3.3.x and replaces the manager bean in the test context. In newer Boot releases, bean mocking annotations may change or be deprecated; update tests to match your target version instead of copying annotations blindly.

**What these tests verify:**
- The operational endpoint is not public (401).
- When authorized, the app returns metadata only, never the raw token.
- `TimeoutException` maps to 504.
- `OAuth2AuthorizationException` with `invalid_client` maps to 502 without echoing the provider description.
- General transport errors return 503 rather than a fake HTTP 200.

**What mocks do NOT prove:**
- That the real truststore loads and the certificate chain is valid;
- That hostname verification is enabled;
- That Reactor Netty connect/response timeouts work over a real network;
- That the provider encodes/parses OAuth2 responses accurately;
- That real client-secret Basic POSTs work;
- Retry semantics or caching as grants expire.

Those require dedicated transport/integration tests.

## 9. Testing Real TLS and Timeouts

### 9.1. Positive TLS Test

With HTTPS Keycloak and the truststore from section 7:

1. `curl --cacert tls/cert.pem` to the token endpoint completes the TLS handshake.
2. Spring Boot starts with `LAB_TOKEN_TRUSTSTORE` set properly.
3. First call to `/ops/token-check` -> 200 authorized when client/secret match.
4. Check Keycloak logs/metrics (redacted): token request observed, zero certificate errors.
5. Second call -> can reuse the cached token without a second token endpoint POST.

### 9.2. Untrusted CA

To test fail-closed behavior in the **lab**:

- Start Spring with a different truststore lacking Keycloak's CA/cert, or leave the custom truststore unset.
- Restart the app to clear the in-memory cached token.
- Call `/ops/token-check`.
- Expect authorization to fail; the controller returns 503 due to a TLS handshake/PKIX error.

**Never** "fix" this with `InsecureTrustManagerFactory.INSTANCE`. Configuring the real truststore is the secure solution.

### 9.3. Hostname Mismatch

The lab certificate SAN only lists `localhost` and `127.0.0.1`. If you use a host alias missing from the SAN (e.g., `keycloak.internal.test`) whose DNS resolves to the same IP, TLS hostname verification must **reject** it. This is a vital check so you never confuse "truststore holds the cert" with "accepting any hostname".

### 9.4. TCP Connect Timeout and DNS Failure

Point the test profile's token URI to an unreachable HTTPS host/port, restart the app, and call the endpoint:
- Connection refused can fail immediately, **not** via timeout.
- Packet drops wait up to `CONNECT_TIMEOUT_MILLIS` and error.
- DNS failures emit their own error; the 9s deadline prevents the token publisher from hanging forever.

**Never** simulate network failures by blocking production traffic or sending requests to public hosts you do not own. Use a mock proxy, container network, or dedicated test environment.

### 9.5. Response Timeout

Use a controlled HTTPS test server (TLS-enabled WireMock/MockWebServer/MockServer, or a test IdP) delaying the response/body past `responseTimeout(4s)`. Verify:
- The error path triggers and callers receive no access token.
- The overall `timeout(9s)` bounds the entire token exchange duration.
- No automatic retries exceed the deadline (if a test enables retries, document them explicitly).
- Connection pool slots do not leak after cancellation or errors.

Never use a plain HTTP stub to claim you tested **certificate validation**; without real TLS/CA setup, a stub only tests timeouts and payload parsing.

### 9.6. Pool Overload

Run a bounded load test in the lab to generate concurrent token requests. With `maxConnections(10)`, `pendingAcquireMaxCount(30)`, and `pendingAcquireTimeout(1s)`, some requests fail pool acquisition **before** reaching the Token Endpoint. That is not `invalid_client` and must not trigger secret rotation.

Consider single-flight token refresh/caching to prevent dozens of simultaneous token requests. When testing races, ensure the token cache does not mask traffic; you can invoke an explicit test token client rather than the caching manager.

### 9.7. Testing OAuth2 Error Responses

Using a test IdP:
- Wrong client secret -> `invalid_client`.
- Client lacking grant permission -> `unauthorized_client`.
- Invalid scope -> `invalid_scope` per provider.
- Quota 429 -> distinguish from auth errors.
- Properly formatted error JSON -> token client parser emits an error without producing an `OAuth2AuthorizedClient`.
- HTTP 200 whose body lacks `access_token` -> fails parsing/protocol validation, never treated as success.
- Provider returns HTML 502 -> never log raw HTML if it may contain internal details.

**Never depend on exact exception classes across providers without testing**, because Spring Security may wrap protocol or HTTP errors differently across versions.

## 10. Customizing Other Grants

### 10.1. Authorization Code Token Client

If the WebFlux app supports `oauth2Login` or authorization code, the matching class is:

```java
// ILLUSTRATIVE SNIPPET, not a bean to merge into
// the client_credentials demo in section 7.
@Bean
ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
        authorizationCodeTokenResponseClient(
                WebClient tokenEndpointWebClient) {

    var client = new WebClientReactiveAuthorizationCodeTokenResponseClient();
    client.setWebClient(tokenEndpointWebClient);

    return request -> client.getTokenResponse(request)
            .timeout(Duration.ofSeconds(9));
}
```

Imports for this snippet:
```java
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
```

Starting in Spring Security 6.3+, publishing a generic bean for the grant lets the framework auto-wire the token client. However, **if you manually build `ReactiveOAuth2AuthorizedClientManager`/`authenticationManager` or deeply customize `SecurityWebFilterChain`**, verify that it actually uses your bean—otherwise the customization sits around unused.

With `oauth2Login` and direct DSL customization, ensure wiring applies to both `OidcAuthorizationCodeReactiveAuthenticationManager` and `OAuth2LoginReactiveAuthenticationManager` where applicable. **Never** change grant types or flows merely to share one timeout.

### 10.2. Refresh Token Token Client

```java
// ILLUSTRATIVE SNIPPET, for apps using refresh_token.
@Bean
ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
        refreshTokenResponseClient(WebClient tokenEndpointWebClient) {

    var client = new WebClientReactiveRefreshTokenTokenResponseClient();
    client.setWebClient(tokenEndpointWebClient);

    return request -> client.getTokenResponse(request)
            .timeout(Duration.ofSeconds(9));
}
```

Matching imports:
```java
import org.springframework.security.oauth2.client.endpoint.OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient;
```

**Warning:** Refresh-token rotation can cause retries after a timeout to be rejected. Never add `retryWhen(Retry.max(5))` to the wrapper without verifying provider policies and idempotency.

### 10.3. Should One WebClient Be Shared?

You can share an HTTP connector/trust policy across multiple token response clients if they **target endpoints within the same trust boundary**. Yet note:
- Different IdPs may have distinct CAs, mTLS setups, proxies, and timeouts.
- Sharing a `WebClient` with resource/business APIs can cause pool contention or wrong timeout settings.
- An overly broad corporate truststore widens the trust surface when you only meant to trust one CA.
- Sharing one pool for token endpoints and userinfo/JWK/discovery can create head-of-line contention.

Across multiple providers, configure routing and trust policies per registration/provider with exact hostname tests; never deploy **one** `InsecureTrustManager` just to "make every IdP work".

### 10.4. Client Authentication Methods

Common methods:

| Method | Meaning | Notes |
| --- | --- | --- |
| `client_secret_basic` | Client ID/secret via HTTP Basic on token request | Supported by default; requires HTTPS |
| `client_secret_post` | Secret in form POST body | Valid when required by provider, yet risks body/log exposure |
| `private_key_jwt` | Client assertion signed with a private key | Requires protecting the key and signing exact audience/time/jti |
| `tls_client_auth` / mTLS | Client certificate at TLS / OAuth client auth policy | Requires client key material and IdP configuration |
| `none` | Public client without secret | Needs PKCE for authorization code; never use to mimic a confidential service |

**Do not treat sending an `Authorization: Bearer ...` header to the token endpoint as client authentication for `client_credentials`.** OAuth2 Client Registration and the provider dictate the client authentication method.

## 11. Corporate Proxies, DNS, and TLS Termination

An enterprise may require HTTPS token traffic to traverse an HTTP CONNECT proxy:

```text
WebFlux OAuth2 client
    |
    | HTTPS CONNECT
    v
Corporate proxy
    |
    v
Authorization Server HTTPS
```

Reactor Netty `HttpClient.proxy(...)` supports configuring a `ProxyProvider` when needed. Settings depend on proxy type/credentials and bypass lists; test that **end-to-end** TLS still validates the Authorization Server's certificate without blindly trusting unapproved CAs.

**Watch out for TLS-inspecting proxies:** If a corporate proxy performs TLS interception, the certificate presented to the client may be signed by an enterprise CA. Install the enterprise CA only after formal policy approval and ensure hostname verification stays intact. Never use an insecure trust manager to "fix" networking.

If the IdP uses private DNS or a Kubernetes service hostname, the URI `https://auth.svc.cluster.local` must match the SAN, issuer, and network policy. If the public issuer is `https://login.example.com` while the backend token URI uses an internal hostname, evaluate impacts on the token endpoint, OIDC discovery, ID Token `iss`, and certificates—never disable issuer or hostname verification.

**Token endpoint redirects:** An HTTP 302 from a token endpoint is abnormal. `followRedirect(false)` prevents sending Basic client credentials to another host; fix misconfigured endpoints at the config or IdP/proxy level instead of auto-following redirects.

## 12. Retries, Circuit Breakers, and Concurrent Callers

### 12.1. Retry Decision Table

| Scenario | Default Recommendation |
| --- | --- |
| `invalid_client` / `invalid_scope` / `unauthorized_client` | Do not retry; alert on config/secret/permission |
| Invalid certificate / hostname mismatch | Do not retry; fix PKI/hostname |
| DNS NXDOMAIN / bad URL | Do not retry continuously; fix DNS/config |
| Authorization code `invalid_grant` | Do not reuse code; start a new flow |
| Rotating refresh token timeout | Do not retry blindly; verify provider contract |
| `client_credentials` 429 | Very limited retry if policy allows; honor `Retry-After` |
| `client_credentials` 503 / transient network | Conditional retry allowed, bounded by overall deadline |
| Pool acquire timeout from internal overload | Reduce concurrency / improve caching; do not increase retries |
| Token endpoint returns 200 with invalid payload | Fail closed, alert provider/schema; never synthesize a token |

A retry strategy can use `Retry.backoff(maxRetries, backoff)` with jitter, filtering **strictly** on permitted exceptions and capping the total time budget. Test it against a real provider or IdP stub, and never apply it blindly to authorization code or refresh token grants.

**Dangerous example:**

```java
// WRONG: retrying every error across every grant.
return tokenResponseClient.getTokenResponse(request)
        .retryWhen(Retry.max(10));
```

It can replay codes, spam invalid credentials, blow past quotas, or trigger cascading outages.

### 12.2. Circuit Breakers

When an IdP is down, shed load to avoid a storm. Use a dedicated circuit breaker/bulkhead for token exchanges:
- CLOSED allows normal requests.
- OPEN fails fast for a short window once error rates pass a threshold.
- HALF_OPEN probes with very few requests.

Never turn an OPEN circuit breaker into **ALLOW** or mint fake tokens. If an unexpired cached token already exists, the manager can reuse it per policy, yet never accept expired tokens out of convenience. Base the circuit breaker on **transport/availability** errors—never trip on `invalid_client` as if it were a network outage.

### 12.3. Clocks and Token Expiration

`OAuth2AuthorizedClient` stores the access token and its `expiresAt`. Providers often use **clock skew** to fetch new tokens ahead of expiration. Large clock drift can cause tokens to be treated as expired too early or too late. Synchronize clocks via NTP and inspect TTL/issuer rather than disabling expiry checks.

### 12.4. Thundering Herd

If 500 business requests see an expired token simultaneously, they can flood the token endpoint together. Mitigations include:
- Caching tokens by `registrationId` and a stable service principal;
- Single-flight / in-flight request coalescing;
- Rate limiting token acquisitions;
- Short jittered refresh windows;
- Suitable shared token caches across multiple nodes with strict secret/token protection;
- Capacity planning with the IdP.

**Note:** Any shared/cached access token mechanism must preserve audience, scope, client, and grant boundaries—never serve one tenant's/client's token to another.

## 13. Observability and SLOs

Minimum metrics:

| Metric | Meaning |
| --- | --- |
| `token_exchange_duration_seconds` (p50/p95/p99) | Latency from subscription to token response/error |
| `token_acquisition_success_total` | Count of successful new token acquisitions |
| `token_acquisition_error_total{category}` | OAuth2, TLS, DNS, connect, timeout, 429, 5xx errors |
| `token_pool_pending_connections` | Pool wait indicating internal bottlenecks |
| `token_pool_active_connections` | Connections currently in use |
| `token_cache_hit/miss` | How often manager requests actually hit the token endpoint |
| `token_client_credential_rotation` | Secret rotation success/failure |
| `auth_server_rate_limit_total` | IdP quota/throttling hits |
| `resource_api_401_after_token` | Token issued yet rejected by resource server |

Never use **raw client IDs/secrets, tokens, or URLs with sensitive queries** as metric labels. Label by allowlisted `registrationId`/provider alias, never unbounded emails or user inputs.

### Splitting the Latency Budget

```text
Business request SLO 1500 ms
  |
  +-- Internal work 600 ms
  +-- Resource Server API 600 ms
  +-- Buffer 300 ms
  |
  +-- Token cache hit: tiny (no exchange)
  +-- Token cache miss: 9 s token endpoint = blows SLO!
```

If a token miss can take 9 seconds, an HTTP business request with a 1.5s SLO cannot meet its target; design caching, pre-warming, fail-fast, async jobs, or tighter application-specific deadlines. The lab's 9s timeout is **not** suitable for every frontend latency SLO.

### Useful Yet Safe Logging

Safe to log:

```text
traceId=... operation=oauth2_token_exchange
registrationId=machine outcome=timeout
durationMs=9012 stage=overall_deadline
```

Never log:

```text
Authorization: Basic ...
access_token=eyJ...
client_secret=...
code_verifier=...
```

Spring Security can include URLs or response text in exception messages/causes. Configure logging sanitizers/redaction before shipping to centralized logging. Never enable full Reactor Netty wiretaps outside synthetic tests.

## 14. Pre-Production Deployment Checklist

1. `token-uri` is a **fixed/controlled HTTPS URL**, never taken arbitrarily from requests (prevents SSRF).
2. Certificate chains verify against the proper CA; **hostname verification** remains active.
3. Truststores/keystores follow lifecycle, rotation, and secret-storage policies; private keys are never committed.
4. For mTLS, the client keystore holds the right alias/cert/key, distinct from the client secret.
5. Configure **pool limits**, pending queue caps, and connect/handshake/response/overall deadlines.
6. Separate the token endpoint `WebClient` from resource/business HTTP clients when distinct trust or pooling is needed.
7. Confirm the custom token client is **actually wired into the provider/manager**, not an unused bean.
8. Test `invalid_client` and secret rotation; never retry config errors.
9. Test untrusted CAs and hostname mismatches; never use insecure trust workarounds.
10. Test slow responses, pool contention, 429/503, and cancellation.
11. Never retry authorization code or refresh token blindly; bound retries per grant.
12. Never emit raw tokens/secrets in probe endpoints, logs, traces, or metrics.
13. Resource Server still validates access token audience/scopes; token acquisition success never guarantees API 200.
14. Key the authorized client cache properly by grant/registration/principal without generating random keys.
15. Track p95/p99 latency, error rates, cache misses, and failure-aware circuit breakers.
16. Verify multiple providers/tenants with distinct CAs/hostnames/permissions where applicable.
17. Public servers enforce inbound HTTPS, authentication/authorization, and rate limiting; lab Basic/`{noop}` is never used in production.
18. Run E2E tests through proxies/ingress with real TLS trust chains, not just mocked `WebClient` tests.
19. When upgrading Spring Boot/Spring Security, re-verify reactive token response client APIs and wrapped exceptions.
20. Enforce fail-closed behavior: without a valid token, never use expired or fake tokens to call APIs.

## 15. Self-Check Questions

**1. In WebFlux OAuth2 Client, which component actually POSTs the token request?**  
The `ReactiveOAuth2AccessTokenResponseClient` for that grant—such as `WebClientReactiveClientCredentialsTokenResponseClient`, which uses `WebClient` underneath.

**2. Does creating a default `WebClient.Builder` bean guarantee the token response client uses it?**  
No. It must be wired explicitly via `setWebClient(...)`, generic bean auto-configuration, or provider/manager wiring.

**3. Why must `InsecureTrustManagerFactory` never be used to work around a self-signed cert?**  
Because it disables certificate chain verification, opening MITM risks and exposing client secrets and tokens. Import the approved CA/cert into a truststore instead.

**4. How does a truststore differ from a client keystore?**  
A truststore verifies the server. A client keystore holds the client's certificate and private key for mTLS.

**5. If a certificate is already in the truststore yet the hostname mismatches, what should happen?**  
TLS must fail; CA trust never replaces hostname verification.

**6. How does `pendingAcquireTimeout` differ from connect timeout?**  
Pending acquire waits for a connection pool slot; connect timeout bounds establishing the TCP socket. Pool overload can fail before any network request is sent.

**7. Is `responseTimeout` the deadline for the entire OAuth2 token exchange?**  
No. Also wrap `getTokenResponse(...)` with `Mono.timeout` if you need an overall deadline on the full publisher.

**8. Does a timeout guarantee the IdP did not issue a token?**  
No. The request may have been processed while the response arrived late or was canceled.

**9. Should an authorization code be retried after a timeout?**  
Never retry blindly: codes are single-use and may already be consumed. Typically restart the authorization flow.

**10. Should `invalid_client` be retried 10 times?**  
No; inspect client ID/secret/auth method/permissions instead of spamming the IdP.

**11. How does a Token Endpoint 429 differ from `invalid_client`?**  
429 indicates quota/overload and may include `Retry-After`; `invalid_client` is an OAuth client authentication/configuration failure.

**12. Why is a stable principal key important for `client_credentials`?**  
The authorized client service keys tokens by `registration + principal`; a random key per request breaks caching and increases token requests.

**13. The client obtained a token, yet the Resource Server returns 403—what does that mean?**  
Successful token acquisition does not guarantee API permissions. Check audience, scopes, roles, and resource authorization.

**14. In Spring Security 6.3, which bean lets you customize the token HTTP `WebClient` separately?**  
A `ReactiveOAuth2AccessTokenResponseClient<OAuth2ClientCredentialsGrantRequest>` bean or the matching grant's token response client configured with `setWebClient`.

**15. Why should a token `WebClient` never auto-follow 302s to another domain?**  
To prevent sending client credentials or token requests to unintended hosts; token endpoints must be configured accurately.

**16. Does a `WebTestClient` test with a mocked manager prove TLS certificates are valid?**  
No. It tests the HTTP response contract/controller; E2E HTTPS Keycloak/truststore and negative TLS tests are needed.

**17. May you log the token response body to debug a 500?**  
No. The body contains access/refresh tokens. Log only sanitized error categories, statuses, and trace IDs.

**18. If the app runs in Docker, does `localhost:9443` reach Keycloak on the host?**  
Not necessarily. A container's `localhost` is the container itself; use the proper network hostname and matching SAN.

**19. Does HTTP Basic `ops:lab-only` on `/ops/token-check` relate to `client_secret_basic` to Keycloak?**  
No. Basic on Spring's inbound endpoint protects the demo endpoint; `client_secret_basic` is the OAuth2 machine client's authentication at the Token Endpoint.

**20. Can an expired token response continue to be used when the IdP is offline?**  
Not by default. An expired access token is no longer valid; never fail open with expired tokens.

**Takeaway:** Customizing **HTTPS + timeouts + error handling for Token Endpoints** must be done on the **matching reactive token response client**, using a `WebClient` with a Reactor Netty connector enforcing TLS trust, hostname verification, and pool/timeouts. Wrap the token response publisher in an overall deadline; separate OAuth2 errors from transport failures; bound retries per grant; preserve caching and metrics; and never leak secrets. For service-to-service calls, `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` fits because it requires no `ServerWebExchange`.

## References

- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/): examples publishing `ReactiveOAuth2AccessTokenResponseClient` beans and customizing `WebClient` for token HTTP transport.
- [Spring Security — Reactive Authorization Grant Support](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html): `client_credentials`, `authorization_code`, `refresh_token`, `setWebClient(...)`.
- [Spring Security — Reactive OAuth2 Client Core](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html): `ReactiveOAuth2AuthorizedClientManager`, background service manager, provider/client service.
- [Spring Security — Client Authentication Support](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/client-authentication.html): `client_secret_basic`, token request credentials, and grants.
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/1.1.28/reference/index.html#http-client): TCP connect, TLS, SSL handshake, response timeout, pooling, proxies.
- [Reactor Netty — HttpClient API](https://projectreactor.io/docs/netty/1.1.28/api/reactor/netty/http/client/HttpClient.html): `secure(Consumer)`, hostname verification, and timeouts.
- [Reactor Netty — ConnectionProvider API](https://projectreactor.io/docs/netty/1.1.28/api/reactor/netty/resources/ConnectionProvider.html): pool limits and acquire timeout.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): connectors, ExchangeStrategies, error handling.
- [Spring Boot 3.3.13 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java 17+ and Gradle support.
- [Keycloak — Configuring TLS](https://www.keycloak.org/server/enabletls): HTTPS certificates, port 8443.
- [Keycloak — Containers and Hostnames](https://www.keycloak.org/server/containers): Docker HTTPS and hostname configuration.
- [Keycloak — Docker Quickstart](https://www.keycloak.org/getting-started/getting-started-docker): local realm/client/service accounts setup.
- [OAuth 2.0 — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, client credentials grant, error responses.
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): TLS, credential handling, and flow security.
