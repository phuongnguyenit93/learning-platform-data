# Customizing WebClient, Timeouts, and Caching by Version API

In a **Spring Security OAuth 2.0/OIDC Resource Server using Spring WebFlux**, JWT access tokens are typically verified with public keys fetched from the Authorization Server's (AS) **JWK Set endpoint (JWKS)**. When routing through a proxy, configuring custom TLS, bounding latency, protecting the app against AS outages, or controlling key refreshes, developers often need to customize **`WebClient`**, **timeouts**, and **caching**.

The tricky part is not `WebClient.builder()` syntax, but that **the configuration APIs of the Reactive decoder and the Servlet decoder are not the same**, and several builder methods were added or changed across Spring Security versions.

> **Principle:** network/cache configuration may change only how the Resource Server **obtains trusted keys**. It must never skip signature verification, weaken `iss`/`aud`/expiration checks, trust arbitrary client-sent JWK URIs, or accept unverified JWTs merely because the JWKS endpoint is failing.

This lesson explains the JWKS fetching architecture in WebFlux, distinguishes `NimbusReactiveJwtDecoder` from `NimbusJwtDecoder`, shows how to configure `WebClient` with Reactor Netty, covers three timeout categories, handles issuer discovery, caching/rotation, common pitfalls, and testing strategies. Examples use **Java 17+, Spring Boot, WebFlux, and Spring Security 6.5/7.x** where indicated. Projects on older versions must check Javadoc/version compatibility before copying.

## 1. What Does WebClient Do in the JWT Authentication Flow?

A business request:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
~~~

may follow this flow:

~~~text
Client
  |
  | Bearer JWT
  v
Spring WebFlux Resource Server
  |
  v
AuthenticationWebFilter
  |
  v
ReactiveJwtDecoder.decode(token)
  |
  +-- Read JWS header: alg, kid, typ ...
  |
  +-- Select a key capable of verifying the signature
  |      |
  |      +-- JWK Set already in key source/cache?
  |      |       |
  |      |       +-- Matching key found -> verify signature
  |      |
  |      +-- Need to fetch/refresh JWKS
  |              |
  |              v
  |        WebClient -> HTTPS -> Authorization Server JWKS
  |              |
  |              +-- HTTP/network timeout -> no trusted key available
  |              +-- Success -> process JWK Set per policy
  |
  +-- Verify signature with permitted algorithm
  |
  +-- Validate claims: iss, aud, exp, nbf, token type ...
  |
  v
JwtAuthenticationToken
  |
  v
authorizeExchange -> service authorization
~~~

**Not every API request needs to call WebClient.** Once the matching key is already in the decoder's cache/source, JWT signature verification can be completely local. Metadata and JWKS fetching typically happen at initialization/first decode, when cached keys expire, or when key rotation requires an update. Exact timing, TTL, unknown-`kid` handling, and cache refresh behavior depend on the **Spring Security version, Nimbus, and configuration**.

### 1.1. Which Requests Actually Go Through WebClient?

In a Reactive decoder configuration, WebClient may be used for:

1. **Issuer discovery:** fetching OIDC Provider Configuration or OAuth Authorization Server Metadata to find `jwks_uri`.
2. **JWKS retrieval:** fetching the JWK Set containing permitted public keys for verification.
3. **JWKS refresh:** reloading when the key source policy requires it, such as when a new key appears.
4. **Additional requests if a custom source explicitly implements them**, though that is not the default for a standard JWT decoder.

**Do not** assume this WebClient automatically calls an introspection endpoint for JWTs. A JWT Resource Server using `jwt()` verifies signatures; opaque token flows use **`ReactiveOpaqueTokenIntrospector`** with their own network/client configuration.

### 1.2. Distinguishing Network Timeouts from JWT Validation

| Issue | Handling layer | Example |
|---|---|---|
| Cannot connect to AS | WebClient / TCP / TLS / DNS | Connection timeout |
| AS does not return HTTP response in time | WebClient / Reactor Netty | Response timeout |
| JWKS returns invalid JSON schema | JWKS parser/key source | Unable to extract public key |
| `kid` matches no current key | Key selection/refresh | Unknown signing key |
| Invalid JWS signature | `NimbusReactiveJwtDecoder` | Invalid signature |
| Expired JWT | JWT validator | `exp` |
| Wrong issuer or audience | JWT validator | `iss`, `aud` |
| Missing scope to call endpoint | HTTP authorization | 403 after token authenticates |

Never use long timeouts or stale caches to "fix" signature errors. Those are two completely separate failure categories.

## 2. Before Customizing: Understand Spring Boot's Defaults

For a WebFlux JWT Resource Server, usually only these dependencies are needed:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

The Spring Boot starter manages compatible OAuth2 Resource Server and JOSE/JWT dependencies via the BOM. If managing dependencies directly, ensure both the Resource Server **and** OAuth2 JOSE modules required for JWT verification are included.

A minimal configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

In Spring Boot versions supporting `audiences`, the Resource Server constrains the `aud` claim per configuration. On other versions, add a custom audience validator.

If the AS supports discovery, `issuer-uri` locates `jwks_uri` and sets up issuer validation. Such simple configuration is usually **better** than writing a custom decoder when default networking/caching already meets system needs.

### 2.1. Why Not Customize the Decoder Right Away?

Defining a custom `ReactiveJwtDecoder` bean can cause Spring Boot to **stop creating the default decoder bean**. Things you assumed "Boot handles for you"—such as issuer validation, audience properties, trusted JWS algorithms, or lazy initialization—may need to be restored explicitly depending on configuration.

Therefore, a sensible preference order is:

1. **Use only Boot properties** when sufficient.
2. **Customize the decoder via public builders** when needing `WebClient`, timeouts, proxies, or algorithms.
3. **Customize validators** while keeping issuer/time/audience checks.
4. **Deeply customize JWK sources/caching** only with a concrete requirement, API version support, and thorough tests.
5. Avoid hand-rolling "Base64-decode JWT" logic in place of cryptographic verification.

## 3. Distinguishing Servlet and Reactive APIs by Version

This is the core reference table for the lesson.

| Goal | Servlet/MVC | Reactive/WebFlux |
|---|---|---|
| Decoder interface | `JwtDecoder` | **`ReactiveJwtDecoder`** |
| Nimbus decoder | `NimbusJwtDecoder` | **`NimbusReactiveJwtDecoder`** |
| Custom HTTP client on JWK Set URI builder | `.restOperations(RestOperations)` | **`.webClient(WebClient)`** |
| HTTP client timeouts | `RestTemplate`/`RestClient` or equivalent client | **Reactor Netty `HttpClient` + `WebClient`** |
| Custom Spring Cache on JWKS builder | Servlet `NimbusJwtDecoder...cache(Cache)` | **No `.cache(Cache)` on the Reactive JWK Set URI builder in 6.5/7.1** |
| Initialize from issuer discovery | `withIssuerLocation(...)` | **`withIssuerLocation(...)`** on Reactive builder in supported versions |
| Initialize with fixed JWK Set URI | `withJwkSetUri(...)` | **`withJwkSetUri(...)`** |
| Lazily initialized decoder | `SupplierJwtDecoder` | **`SupplierReactiveJwtDecoder`** |
| Principal authentication | `JwtAuthenticationToken` | `JwtAuthenticationToken` in reactive context |
| HTTP security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |

### 3.1. API of `NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder`

Per Spring Security **6.5.x and 7.1.x** Javadocs, the Reactive JWK Set URI builder exposes these public methods:

~~~java
.webClient(WebClient)
.jwsAlgorithm(SignatureAlgorithm)
.jwsAlgorithms(Consumer<Set<SignatureAlgorithm>>)
.jwtProcessorCustomizer(...)
.validateType(boolean)   // available since Spring Security 6.5
.build()
~~~

Methods that **do not exist** on this Reactive builder:

~~~java
.restOperations(restTemplate) // belongs to Servlet decoder
.cache(springCache)          // belongs to Servlet JWK Set builder
.responseTimeout(duration)   // must be configured on WebClient/HTTP connector
~~~

If you see a snippet like:

~~~java
// Does not compile on JwkSetUriReactiveJwtDecoderBuilder.
NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
    .cache(cacheManager.getCache("jwks"))
    .build();
~~~

the author very likely confused **Servlet `NimbusJwtDecoder`** with **WebFlux `NimbusReactiveJwtDecoder`**.

### 3.2. Why "Spring Security Supports `cache(Cache)`" Is Incomplete

That statement may be true for the **Servlet builder** while false for the **Reactive builder**.

To avoid confusion when reading online examples, check:

- Is the import `NimbusJwtDecoder` or `NimbusReactiveJwtDecoder`?
- What type does the builder return?
- Does the Javadoc belong to version 6.4, 6.5, 7.0, or 7.1?
- Does `cache(...)` actually appear in the *Reactive* Javadoc?
- Is the cache discussed a **JWK Set cache**, a **JWT authentication cache**, or an **HTTP response cache**?

Never just swap the class name while leaving the rest of the builder calls unchanged.

### 3.3. Version Milestones to Note

| API/feature | Javadoc milestone | Remarks |
|---|---|---|
| `NimbusReactiveJwtDecoder.withJwkSetUri(...)` | Since Spring Security 5.2 line | Explicit JWKS URL config |
| Reactive `.webClient(...)` | Present in 6.5.x and 7.1.x | Custom HTTP client for JWKS/discovery |
| `NimbusReactiveJwtDecoder.withIssuerLocation(...)` | Since 6.1 | Derives JWKS via issuer metadata |
| `SupplierReactiveJwtDecoder` | Since 5.6 | Defers decoder initialization |
| Reactive `.validateType(boolean)` | Since 6.5 | Never disable type validation without a replacement |
| Reactive `.withJwkSource(...)` | Present on modern decoder lines | Deep extension; requires safe source/key selection |
| Servlet `.cache(Cache)` | On `NimbusJwtDecoder` JWK Set builder | **Does not apply directly to Reactive** |

Version numbers in the table are API/Javadoc milestones and do not guarantee every Spring Boot release uses that exact Spring Security version. Your **project BOM and actual dependency graph** determine which methods exist.

## 4. `issuer-uri` and `jwk-set-uri`: Choose Properly Before Changing the Network Client

There are two common configuration patterns.

### 4.1. Knowing Only the Issuer

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
~~~

The Resource Server uses OIDC Discovery/OAuth Authorization Server Metadata to locate `jwks_uri`. This requires a network call to **issuer metadata** before knowing the JWKS URL.

Key points:

- `iss` in the JWT must match the canonical issuer.
- Metadata must come from a trusted issuer/discovery endpoint.
- The JWK Set URL may differ from the issuer URL, especially behind a reverse proxy.
- If issuer discovery or the JWKS endpoint is unavailable, new tokens needing keys cannot be verified.

### 4.2. Having an Explicit JWK Set URI

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

With `jwk-set-uri` explicitly configured, the Resource Server does not need discovery to locate keys. **However, `iss` must still be validated** when required by the API contract.

An internal deployment might set:

~~~text
Canonical issuer:    https://login.example.com/realms/shop
Internal JWKS route: https://keys.internal.example/realms/shop/certs
```

This can be valid when both the canonical issuer and internal key source are properly governed, the Resource Server trusts that internal URI, and **still validates token `iss` against the public issuer**. Never change `iss` to an internal hostname just to make JWKS connectivity work.

### 4.3. Do Not Conflate Public Key Location with Issuer Identity

`jwk-set-uri` is where public keys are fetched. `issuer-uri`/the `iss` claim is the **identity of the issuing authority**. The same key may be shared across multiple contexts; verifying signatures alone while omitting issuer/audience validation risks **token substitution** or cross-service acceptance.

## 5. Configuring a Dedicated WebClient for JWT Key Retrieval

The full example below uses:

- `NimbusReactiveJwtDecoder.withJwkSetUri(...)`.
- `.webClient(...)` on the Reactive builder.
- `Reactor Netty HttpClient` with connect and response timeouts.
- An HTTPS URL from a trusted configured source.
- `JwtValidators.createDefaultWithIssuer(...)`.
- An audience validator for `orders-api`.

**This is a WebFlux configuration**; it does not use `RestTemplate` or `RestOperations`.

### 5.1. Illustrative Properties

~~~yaml
app:
  security:
    jwt:
      issuer: https://idp.example.com/realms/shop
      jwk-set-uri: https://keys.internal.example/realms/shop/certs
      audience: orders-api
~~~

Using `app.security.jwt.*` makes clear that the custom decoder reads and applies these values itself; do not assume Boot will still process `audiences` automatically after overriding the bean.

### 5.2. `ReactiveJwtDecoder` Bean with Timeouts

~~~java
package com.example.orders.security;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class JwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String audience) {

        HttpClient httpClient = HttpClient.create()
            // TCP connect timeout = 2 seconds.
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            // Timeout waiting for response from the remote endpoint.
            .responseTimeout(Duration.ofSeconds(3));

        // Dedicated to issuer/JWKS; does not carry request bearer tokens.
        WebClient jwkWebClient = WebClient.builder()
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(512 * 1024))
            .build();

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withJwkSetUri(jwkSetUri)
                .webClient(jwkWebClient)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "Required audience is missing",
                null
            );
            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

With this decoder bean, the filter chain usually needs only:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Imports for the filter chain: `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`, `Bean`.

### 5.3. What Was Customized?

| Component | Change | What must still be preserved |
|---|---|---|
| `HttpClient` | Connect timeout, response timeout | TLS certificate/hostname validation |
| `WebClient` | Connector and memory buffer size for JWKS body | Connect only to trusted endpoints |
| `NimbusReactiveJwtDecoder` | Uses custom WebClient to fetch JWKs | Signature/JWS algorithm selection |
| Validators | Enforces issuer and audience | Timestamp validation and token-type policy |
| Security chain | Access rules at HTTP boundary | Business tenant/ownership checks |

The example does not mean every token with `aud=orders-api` is valid: signature, algorithm, `iss`, `exp`, `nbf`, and other validators must still pass.

### 5.4. What Timeout Values Should You Choose?

`2 seconds` and `3 seconds` in the code are **illustrative values**, not recommended defaults for every system. Real values depend on:

- API and AS SLOs/SLAs.
- Network distance to the JWKS endpoint.
- p95/p99 connect/TLS/JWKS latencies in the deployment environment.
- Proxy/service mesh/DNS behavior.
- Remaining request latency budget.
- How caching and key rotation behave.
- Impact of an outage on requests needing uncached keys.

A low-latency API may choose shorter timeouts; a cross-region system may need longer ones. **Never raise timeouts indefinitely to mask a network outage.**

## 6. Connect Timeout, Response Timeout, and Overall Duration: Not the Same

| Timeout type | Approximate scope | Example |
|---|---|---|
| TCP connect timeout | Waiting to establish network connection | `CONNECT_TIMEOUT_MILLIS` |
| TLS handshake timeout | Waiting for TLS handshake completion | Netty SSL handler config |
| Response timeout | Waiting for server response activity per Netty policy | `HttpClient.responseTimeout(...)` |
| Read/write inactivity timeout | Waiting on network read/write I/O | Netty `ReadTimeoutHandler`, `WriteTimeoutHandler` |
| Overall request deadline | Total budget from start to finish | Must be designed per call chain |
| JWT timestamp validation | Token past `exp`/before `nbf` | `JwtTimestampValidator` |
| JWK cache TTL | How long a JWK set is retained | Belongs to cache/key source, not HTTP timeout |

### 6.1. Connect Timeout

~~~java
HttpClient client = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000);
~~~

Bounds the time to establish the TCP connection. It does not by itself bound the full TLS handshake, DNS resolution, retry count, or response reading time.

### 6.2. Response Timeout

~~~java
HttpClient client = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(3));
~~~

Applies response waiting policy at the Reactor Netty layer. This is not always equivalent to an **end-to-end total deadline**; consult Reactor Netty/Spring WebClient docs to understand exact semantics for your version.

A slow JWKS response caused by server overload can hit response timeout even when TCP connect is instantaneous.

### 6.3. TLS Handshake Timeout

When proxies, mTLS, large truststores/certificate chains, or slow networks are involved, you may want to tune the handshake separately. Reactor Netty provides SSL options depending on version:

~~~java
HttpClient client = HttpClient.create()
    .secure(ssl -> ssl
        .handshakeTimeout(Duration.ofSeconds(3)));
~~~

This is **optional configuration** and unnecessary when TLS defaults suffice. Never disable certificate verification to "fix" a handshake timeout.

### 6.4. Deadline of the Entire JWKS Retrieval

A flow can involve DNS, connect, TLS, HTTP response, body decoding, and retries:

~~~text
DNS
 + connect
 + TLS
 + server response
 + body parsing
 + retry/backoff
 = total latency borne by the request invoking the decoder
~~~

Setting only `responseTimeout=3s` does not guarantee **the entire decode always finishes under 3s**. Account for connector setup, DNS, retries, discovery calls, connection pooling, and caching.

If your system applies an overall request deadline in the Reactor pipeline, place it at the appropriate boundary and ensure a **signature-check timeout** never turns into a bypass decision. A timeout must lead to **failing to authenticate the token**, not granting access.

### 6.5. Browser/CORS Does Not Apply to This WebClient

The `WebClient` fetching JWKS performs **server-to-server** HTTP initiated by the Resource Server. It is not subject to browser CORS. If JWKS cannot be fetched, inspect DNS, TLS, proxies, firewalls, URLs, redirects, timeouts, and response schemas—**never add `Access-Control-Allow-Origin: *` trying to fix JWKS requests**.

## 7. Customizing WebClient When Issuer Discovery Is Needed

When `jwks_uri` is not known upfront, you can use:

~~~java
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder
        .withIssuerLocation(issuer)
        .webClient(jwkWebClient)
        .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer)
);
~~~

`withIssuerLocation(...)` has been available since Spring Security **6.1** per Javadoc. It uses issuer metadata to discover the JWK Set URI; `.webClient(...)` can serve both discovery and JWKS retrieval per the builder contract.

### 7.1. Bean Method Example

~~~java
@Bean
ReactiveJwtDecoder issuerBasedDecoder(
        @Value("${app.security.jwt.issuer}") String issuer) {

    HttpClient http = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
        .responseTimeout(Duration.ofSeconds(3));

    WebClient metadataAndJwksClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(http))
        .build();

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
            .webClient(metadataAndJwksClient)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

**Do not register this bean alongside the bean from Section 5 expecting Boot to pick one automatically.** This is an **alternative approach**. If audience validation is needed, add it to the validator as in Section 5.

### 7.2. Preserve the Canonical Issuer

An AS deployed behind a reverse proxy might have:

~~~text
Public issuer:  https://login.example.com/realms/shop
Internal JWKS:  https://keys.internal.example/realms/shop/certs
~~~

Valid JWTs still carry `iss=https://login.example.com/realms/shop`. Changing the issuer validator to `keys.internal.example` merely because the Resource Server connects to an internal JWKS route can reject valid tokens or break issuer boundaries.

Issuer is an identity; JWKS URL is a public-key transport path. Design those two concepts separately.

### 7.3. Startup Independence and Lazy Discovery

Per Spring Security Reactive docs, `issuer-uri` can use a mechanism that defers discovery until the first JWT request, avoiding coupling application startup to the AS being online. The docs mention `SupplierReactiveJwtDecoder` to preserve lazy initialization when declaring a bean yourself.

You can wrap it:

~~~java
@Bean
ReactiveJwtDecoder lazyDecoder(
        @Value("${app.security.jwt.issuer}") String issuer) {

    return new SupplierReactiveJwtDecoder(() -> {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
                .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer)
        );
        return decoder;
    });
}
~~~

This is yet **another alternative** illustrating lazy creation; if custom timeouts are needed, build the `WebClient` and attach `.webClient(...)` inside the supplier as shown earlier.

`SupplierReactiveJwtDecoder` has existed since **Spring Security 5.6**, but must be paired with builder methods available in your project's version. Lazy discovery does not guarantee the first request succeeds if the AS/JWKS is down: it simply **defers the failure from startup to the first request**.

### 7.4. Direct JWKS URI Usually Eliminates One Network Dependency

If the JWK Set URL is already known and trusted:

~~~java
NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
    .webClient(jwkWebClient)
    .build();
~~~

can skip the metadata discovery step. However, **keep the issuer validator** and other validators intact. Never trade away `iss` validation for key-fetch speed.

## 8. TLS, Proxies, and Network Trust for WebClient

A decoder fetching keys through a custom HTTP client must still uphold trust boundaries.

### 8.1. HTTPS and Certificate Validation

JWKS contains **public keys**, yet the channel delivering them must still be protected against key-substitution attacks. If an attacker controls the JWKS response, they can inject their own public key into a trusted source and trick the Resource Server into accepting forged JWTs if other checks are met.

Therefore:

- Use HTTPS for the JWKS endpoint whenever architecture allows.
- Validate hostnames and certificate chains properly.
- Manage private CAs/truststores when using mTLS or internal networks.
- Restrict egress to configured endpoints.
- Never disable TLS verification in production.
- Never write secrets, tokens, or full headers into HTTP logs.

### 8.2. Never Send Client-Received Bearer Tokens When Calling JWKS

The `WebClient` fetching public keys does not need the caller's access token. Never copy:

~~~text
Incoming Authorization: Bearer <user-token>
```

into:

~~~text
Outgoing GET /jwks
Authorization: Bearer <user-token>
```

just to "preserve context." That leaks credentials to an endpoint that does not need them, especially if redirects occur.

Create a **dedicated WebClient for JWKS/metadata**. If reusing a globally configured `WebClient.Builder` that has an `ExchangeFilterFunction` attaching credentials, verify carefully so user tokens/API keys are never sent to issuer endpoints by mistake.

### 8.3. Internal Proxies and DNS

A Resource Server running in Kubernetes or a corporate network might reach the AS only via a proxy. Configure the proxy/connector per your Reactor Netty version's documentation while considering:

- Proxy auth, NoProxy/bypass lists, and allowlists.
- DNS resolution, IPv4/IPv6.
- TLS SNI/hostname.
- Path rewriting and HTTP redirects.
- Service mesh sidecar latency.
- Connections over split-horizon DNS.
- Proxy certificate chains.

Never blindly rewrite `https://login.example.com/...` to `http://auth-service:8080/...` and switch issuer validation to the internal hostname as well. Manage network routing and token issuer separately.

### 8.4. Avoid SSRF via URI/Key Sources

JWT headers may contain fields such as `kid`, `jku`, `x5u`. These are **client-supplied token inputs**, never arbitrary URLs for `WebClient`:

~~~text
JWT header (untrusted until verified):
{"kid":"abc","jku":"https://attacker.example/jwks"}
~~~

Wrong:

~~~text
JWK Set URI = JWT header jku
  -> WebClient calls attacker's URL
  -> Resource Server trusts attacker-controlled public key
```

Take `jwk-set-uri` from **allowlisted server/issuer configuration**, never from an arbitrary caller-supplied header/query. `kid` should only select a key within an already-trusted source, with bounded refresh policies.

## 9. "Cache" Means Several Different Things

The word **cache** can refer to at least four layers:

| Cache | What it holds | Primary concern |
|---|---|---|
| Issuer discovery cache | Provider metadata, `jwks_uri` | Metadata changes or temporary AS errors |
| **JWK Set cache** | Public key set from a trusted source | Key rotation, TTL, unknown `kid` |
| HTTP response cache | JWKS HTTP response per `Cache-Control`/ETag | Compatibility with the key source library |
| Decoded/validated JWT cache | Token verification results | Can bypass expiry/revocation/policy if poorly designed |

The usual optimization target is **JWK Set retrieval**, not caching entire JWT authentications yourself.

### 9.1. A JWK Set Is Not a JWT Token

A JWK Set looks like:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

`<base64url-modulus>` is an illustrative placeholder, not a usable JWK. A JWKS should contain only the **required public key material**; never publish private parameters such as `d`, `p`, `q`.

A JWK cache helps the Resource Server avoid calling the JWKS endpoint when many JWTs share a signing key. Even when JWKS is cached, **every JWT must still have its signature and claims verified**.

### 9.2. Do Not Confuse Servlet TTL with Reactive

Servlet `NimbusJwtDecoder` documentation describes a default in-memory JWK Set cache of **5 minutes** in documented versions. You cannot take that number and assert that **every `NimbusReactiveJwtDecoder` across all versions has the exact same TTL**.

`NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder` in 6.5 and 7.1 **does not have** `.cache(Cache)`; the reactively fetched key source has its own implementation and lifecycle.

**Right approach:** verify behavior from the Javadoc, the source of the exact dependency version in use, and tests counting calls to the JWKS endpoint. Never rely on assumptions from a cache API in the other stack.

### 9.3. Why You Cannot Call `.cache(...)` on the Reactive Builder

This is valid in **Servlet**:

~~~java
NimbusJwtDecoder.withJwkSetUri(jwkSetUri)
    .cache(cacheManager.getCache("jwks"))
    .build();
~~~

Do not mechanically swap the class to `NimbusReactiveJwtDecoder`:

~~~java
// WRONG on Reactive JWK Set builder 6.5/7.1.
NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
    .cache(cacheManager.getCache("jwks"))
    .build();
~~~

If configurable TTL or shared caching is required, **pick an extension point supported by your Reactive version** or build caching outside the key source with thorough verification; never invoke a non-existent method.

## 10. JWKS Caching Options for WebFlux

### 10.1. Option A — Keep the Default Mechanism

Start with:

~~~java
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
        .webClient(jwkWebClient)
        .build();
~~~

Then measure:

- Requests to the JWKS endpoint under normal load.
- Request spikes after restarts/scale-outs.
- When JWKS gets refetched.
- Behavior when a token with a new `kid` arrives.
- Behavior when JWKS temporarily fails while old keys are already loaded.
- Concurrent network requests when multiple calls need a new key.

Many systems do not need a custom cache upfront. Deeper caching raises the chance of rotation-policy bugs and extends the trust window for old keys.

### 10.2. Option B — Managed HTTP Layer/CDN or JWK Gateway

If the AS is distant, you can deploy a **trusted** internal JWKS endpoint (gateway/mirror) with formally operated caching, and point the Resource Server's `jwk-set-uri` to that endpoint.

Key conditions:

1. Mirror JWKS only from the exact configured AS/issuer.
2. HTTPS or a properly secured channel between the Resource Server and gateway.
3. TTL/invalidation reflecting key rotation.
4. Size, schema, and content-type limits.
5. Never let request headers/JWT `jku` drive the upstream URL.
6. Never turn the gateway into a key issuer or skip signature checks.
7. Test outages and rotation, not only cache hits.

Model:

~~~text
Authorization Server JWKS (source of truth)
               |
               v
Trusted internal JWKS gateway/cache
               |
               v
Resource Server WebClient
               |
               v
NimbusReactiveJwtDecoder -> verify signature + claims
```

A shared cache/gateway reduces fetches across instances but **does not replace** issuer/audience validators.

### 10.3. Option C — Custom Reactive JWK Source

`NimbusReactiveJwtDecoder` offers an extension point:

~~~java
NimbusReactiveJwtDecoder.withJwkSource(
    Function<SignedJWT, Flux<JWK>> source
)
~~~

The idea is to supply an application-managed Reactive key source. This is an **advanced API**, not a one-line TTL cache utility. If implemented, ensure:

- Fetch keys only from trusted configured issuer/JWK sources.
- Select keys matching `kid`, `kty`, `alg`, `use`/`key_ops`.
- Never let token headers specify unapproved URLs.
- Manage TTL, invalidation, refresh/unknown `kid`, and retries.
- Coalesce concurrent refreshes to avoid thundering herds.
- Handle failures fail-closed.
- Bound JWK Set size and key count to prevent resource exhaustion.
- Preserve signature and issuer/audience/token-type validation.

**Never** ship sample custom `withJwkSource(jwt -> Flux.just(attackerKey))` in production. If a key source returns wrong data or lacks context, the Resource Server may accept the wrong issuer or suffer outages during rotation.

### 10.4. Option D — Using Spring Cache in a Custom Layer

Spring Cache/Redis/Caffeine can be used inside an **application-controlled key retrieval layer**, though this is not native `.cache(Cache)` on the Reactive Nimbus builder.

When doing so, define:

~~~text
Cache key   = trusted issuer + configured jwkSetUri
Cache value = validated JWKS public-key data
TTL         = rotation policy + approved upper bound
```

Never derive a cache key from a lone `kid` without binding the issuer namespace. Never cache allow decisions/JWT authentications as a shortcut around verification. On a cache miss while the AS is unreachable, **never** accept tokens whose signatures have not been verified.

### 10.5. Which Option Should You Choose?

| Need | Preferred option |
|---|---|
| Most APIs, infrequent JWKS changes | Keep default decoder/cache; measure behavior |
| Need bounded network timeouts | Customize `.webClient(...)` |
| Distant AS, many Resource Server replicas | Trusted JWKS gateway/mirror if appropriate |
| Mandatory custom TTL/refresh | Version-supported key source extension, tested thoroughly |
| Want to avoid verifying signatures per JWT | **Do not** cache decoded JWTs as a shortcut |
| Want `.cache(Cache)` on WebFlux builder | **Method does not exist in 6.5/7.1** |
| JWKS temporarily unavailable | Must fail closed for tokens without a trusted key |

## 11. Key Rotation, New `kid`, and Cache Refresh

An AS may rotate keys as follows:

~~~text
T0: JWKS has key-A
    JWT-A signed with key-A -> Resource Server verifies successfully

T1: AS publishes key-A + key-B
    Caches may still see only key-A

T2: AS issues JWT-B with kid=key-B
    Resource Server needs to find/update the JWK Set

T3: AS stops issuing JWT-A, keeps key-A in JWKS for a period
    so unexpired JWT-As can still be verified

T4: After the overlap window, AS removes key-A
~~~

Exact details vary by AS and token TTL, yet an **overlap window between old and new keys** is the standard rotation model that minimizes disruption.

### 11.1. An Unknown `kid` Is No Reason to Trust a New Key Automatically

JWT header:

~~~json
{
  "alg": "RS256",
  "kid": "key-B",
  "typ": "at+jwt"
}
~~~

`kid` is a **key-selection hint**, not proof the key was issued by the AS. When `key-B` is not found:

- The decoder may refetch JWKS per version behavior.
- If JWKS contains trusted `key-B` and signature/validators pass, the token can be valid.
- If JWKS lacks a matching key or cannot be loaded, reject the token.
- Never fetch a public key from a JWT-supplied URL to "find the key somehow."

### 11.2. Cache TTL Too Long vs. Too Short

**TTL too long:**

- Slow to pick up new keys, causing 401s during rotation.
- May keep trusting old keys after the AS retired them per policy.
- Easily creates reliance on manual cache eviction.

**TTL too short:**

- Increases network fetches to the AS/gateway.
- Causes load spikes when many replicas restart/refetch together.
- Makes request latency more dependent on networking.
- Widens the blast radius of an AS outage.

There is no universally ideal TTL. Combine AS rotation policy, JWT TTL, SLOs, and replica count.

### 11.3. Stale-While-Revalidate and Outage Tolerance

Some cache gateways support serving stale data during outages. Use this only if **security policy permits it** with explicit bounds:

- Stale keys must still come from a trusted source.
- Enforce an upper bound on JWKS age.
- Never skip signature validation.
- Never default to allowing tokens with unknown keys when refresh fails.
- Plan audits/recovery and test key-compromise scenarios.

Never turn "JWKS unavailable" into "any JWT with `alg=RS256` is valid."

## 12. Do Not Cache JWT Verification Arbitrarily

An optimization that looks tempting:

~~~text
Cache key: raw JWT
Cache value: permitted authentication
TTL: 1 hour
```

fails if:

- The JWT expires before the TTL.
- The token is revoked and the API has a denylist/policy to check.
- Issuer/audience or allowed algorithm configuration changes.
- Roles/memberships change during the cache period.
- Large tokens put sensitive credentials in cache keys.
- Cache responses/traces accidentally log the JWT.

With JWTs, caching the public key source is enough to avoid per-request network calls; signature and claim verification should still execute through the request's security pipeline.

If a system designs a specialized session/token cache, that is a **threat-model change** requiring separate review, not a default JWK cache tweak.

## 13. Protecting Algorithms and Token Types When Changing Builders

Per Spring Security documentation, `NimbusReactiveJwtDecoder` defaults to trusting only `RS256` in basic setups. You can add more when the AS contract requires it, for example:

~~~java
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
        .webClient(jwkWebClient)
        .jwsAlgorithm(SignatureAlgorithm.RS512)
        .build();
~~~

Import needed:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
~~~

If the system only issues RS256, **do not add RS512, ES256, or all algorithms "just to try."** Allowed algorithms must be a contract allowlist, never driven by the client-sent JWT header.

### 13.1. `alg=none` and Algorithm Confusion

Never accept unsigned JWTs or replace verification by parsing claims without checking signatures:

~~~text
Header {"alg":"none"} + payload {"scope":"admin"} -> INVALID
```

Similarly, never confuse HMAC shared secrets with RSA public keys based on the `alg` requested by the token. Let the Nimbus decoder handle JWS per configured policy.

### 13.2. `validateType(boolean)` Is a Versioned API

The Reactive builder from Spring Security **6.5** provides:

~~~java
.validateType(boolean)
~~~

It adjusts Nimbus's `typ` header validation. Do not call this method on versions that lack it.

More importantly, **do not set `.validateType(false)` to accept every token type**. When disabling the Nimbus type verifier, the application must have an equivalent type/profile validator—such as validating the JWT access-token profile (RFC 9068) when the API requires `at+jwt`.

If an application accepts an OIDC ID token instead of an access token merely because its signature is valid, it risks **cross-token confusion**. Configure proper `iss`, `aud`, `exp`, `nbf`, `typ`/token-profile, and client-context validators per contract.

### 13.3. Using Validators Must Not Erase Defaults

Wrong example:

~~~java
// WRONG: replaces all validators with a single audience check.
decoder.setJwtValidator(myAudienceOnlyValidator);
~~~

Issuer/timestamp checks may then disappear.

Conceptually safe example:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        audienceValidator
    )
);
~~~

If the project uses a dedicated RFC 9068/token-type validator, integrate it via the version-appropriate API; do not assume `JwtValidators.createDefaultWithIssuer(...)` covers every profile.

## 14. Do Default Boot Properties Still Modify This WebClient?

Spring Boot provides properties such as:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ...
          jwk-set-uri: ...
          jws-algorithms: RS256
~~~

Yet a bean:

~~~java
@Bean
ReactiveJwtDecoder customDecoder() { ... }
~~~

typically **replaces the auto-configured decoder**. That means `issuer-uri`, audience, and JWS algorithm in Boot properties do not necessarily carry over to the custom bean automatically.

**Reliable approach:** when writing a custom bean, inject the needed values and configure them **explicitly** on the builder/validator, or use a customization mechanism that does not replace the decoder when appropriate.

### 14.1. Specifying One Decoder Explicitly

Two common approaches:

**Bean:**

~~~java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder() {
    return NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
        .webClient(jwkWebClient)
        .build();
}
~~~

**Wiring directly into the DSL:**

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.decoder(myReactiveJwtDecoder)))
~~~

If using both across multiple places/chains, know **which decoder is actually chosen**. One chain may override a different bean from another chain.

**Do not define two beans of the same type and treat injection ambiguity lightly**: a Resource Server could inadvertently use a decoder for the wrong issuer/JWKS in a multi-issuer environment.

### 14.2. Multi-Issuer/Tenant and Caches

With multiple issuers, each issuer requires:

- An allowlist of trusted issuer URLs.
- Matching public JWK source.
- Separate `iss`/`aud` validators.
- Non-colliding cache keys across issuers.
- Role/scope policies matching the issuer.
- No unverified token controlling arbitrary JWKS URIs.

A custom reactive resolver choosing issuers must follow a contract/trust registry rather than reading an unverified `iss` and calling arbitrary Internet URLs.

## 15. Retry/Backoff: Use with Caution

A network call to JWKS can fail transiently. Retries can help for genuinely transient failures, but never default to an aggressive policy:

~~~text
1000 requests hit unknown kid
   |
   +-- each request retries 5 times
   |
   +-- 5000 requests hit JWKS while the AS is already degraded
```

This creates a **retry storm / thundering herd**.

Guidelines:

- Retry only select connection/5xx errors per policy; never retry invalid JWT signatures.
- Bound attempt counts, total deadline, and concurrency.
- Use exponential backoff/jitter as needed.
- Never retry infinitely.
- Add circuit breakers/metrics for the network source.
- Use single-flight cache refresh if the key source/gateway supports it.
- Never turn key-retrieval errors into accepted tokens.

A WebClient filter that blindly retries every GET can amplify both metadata and JWKS calls unexpectedly. If unsure when the builder calls out, **measure network behavior in integration tests** before adding retries.

## 16. Metrics to Monitor

Do not look solely at overall API latency. For JWT/JWKS, separate:

| Metric/event | Meaning |
|---|---|
| `jwks_fetch_requests` | Frequency of key fetches from AS |
| `jwks_fetch_duration` | Network p50/p95/p99 latency |
| `jwks_fetch_failure` | DNS, connect, TLS, HTTP 4xx/5xx, parse errors |
| `jwks_cache_hit` (if instrumentation supports it) | How often cached keys are reused |
| `jwks_refresh` | Rotation/refresh frequency |
| `jwt_invalid_signature` | Tokens with invalid signatures |
| `jwt_unknown_kid` | Missing matching key (could be rotation or attack) |
| `jwt_invalid_issuer` | Issuer mismatch |
| `jwt_invalid_audience` | Token not meant for this API |
| `jwt_expired` | Expired tokens |
| `authentication_401` | Unauthenticated requests |
| `authorization_403` | Valid principal lacking business permission |

Exact metric names depend on Micrometer/observability libraries and custom instrumentation; the table is a **suggested classification**, not a claim that Spring Security emits all of these automatically.

### 16.1. Never Log JWTs or Private Keys

Never record:

- Raw `Authorization: Bearer ...`.
- Full JWT payloads containing PII.
- Private JWK parameters (`d`, `p`, `q`, ...).
- Full HTTP TLS headers/proxy credentials.
- Client secrets, private cert keys.
- JWKS JSON in public logs if restricted by environment policy.

You may log configured issuer IDs, JWK Set endpoint identifiers, bounded `kid`, HTTP status, duration, trace ID, and error category, while still enforcing data-leakage controls.

## 17. Testing with a Mock JWKS Server

To verify timeouts and caching, use a **test-only** JWKS HTTP server rather than hitting the production AS continuously. Tools such as WireMock or MockWebServer can be used if the project already includes them.

### 17.1. Minimal Test Dataset

Generate an RSA keypair for tests:

~~~text
Private key: in test fixture only, to sign test JWTs
Public JWK:  served by JWKS response
kid:         key-A
```

JWKS response:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-A",
      "use": "sig",
      "alg": "RS256",
      "n": "<test-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

This is illustrative JSON without real RSA key values; actual tests must generate valid keys. Never place private keys in a JWKS response.

Test JWT:

~~~json
{
  "iss": "https://idp.test.example/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

The token must be **signed with the private key matching the public JWK**. The example `exp` field is illustrative only; real integration tests should compute timestamps relative to the test `Clock` so tokens do not expire unexpectedly.

### 17.2. JWKS/Network/Cache Test Matrix

| Case | Setup | Expectation |
|---|---|---|
| Normal JWKS | Server returns valid public JWK | Token signed with matching key verifies |
| Invalid JWT signature | Same claims, bad signature | Reject |
| Wrong JWT issuer | Valid signature, different `iss` | Reject |
| Wrong JWT audience | Valid signature, `aud` not this API | Reject |
| Expired JWT | `exp` in the past | Reject |
| JWKS 404 | Key endpoint missing | Reject token needing key; report key-source error |
| JWKS 500 | AS failing | Never accept unverified tokens |
| Connect timeout | Server unreachable | Does not hang forever; does not fail open |
| Response timeout | Server accepts yet never sends data | Does not hang forever |
| Malformed JWKS JSON | Unparseable body | Reject |
| Oversized JWKS | Exceeds buffer size or schema limits | Does not consume unbounded resources |
| Warm cache | Repeated tokens using existing key | Count how many times the server is called |
| Key rotation | Add `key-B` then issue JWT-B | Observe refresh behavior per version |
| Unknown `kid` | JWT carries unauthorized key | Reject |
| Concurrent refreshes | Burst of requests at the same time | No fetch storm if cache/gateway designed well |
| Issuer discovery failure | Metadata 404/timeout | Never accept arbitrary tokens |
| Bad proxy/TLS | Untrusted certificate | Fail closed |
| Two issuers with same `kid` | Different public keys | No cache/issuer confusion |

**Important:** cache test suites must **count actual HTTP requests** hitting the stub JWKS server. Never just count `decoder.decode()` calls and conclude a cache hit; the decoder is always called whenever a request needs authentication.

### 17.3. Do Not Replace Decode Tests with `mockJwt()`

`WebTestClient` with Spring Security Test offers `mockJwt()`:

~~~java
webTestClient.mutateWith(
    mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")
    ))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

This is an **authorization mock**; it can **completely bypass `ReactiveJwtDecoder`**, and therefore tests neither `WebClient`, timeouts, JWKS caching, signatures, nor issuer validators.

To test networking/caching, use real JWTs signed with test keys and send requests through a real `ReactiveJwtDecoder` against a mock JWKS server.

### 17.4. Using Reactor `StepVerifier` When Testing the Decoder

Testing the decoder standalone:

~~~java
// signedJwt: test JWT genuinely signed with the test private key.
// decoder: ReactiveJwtDecoder pointing to the test JWKS server.
StepVerifier.create(decoder.decode(signedJwt))
    .expectNextMatches(jwt ->
        "user-42".equals(jwt.getSubject()))
    .verifyComplete();
~~~

For an invalid token:

~~~java
StepVerifier.create(decoder.decode(invalidSignatureJwt))
    .expectError(JwtException.class)
    .verify();
~~~

The variables `signedJwt`, `invalidSignatureJwt`, and `decoder` are test fixtures supplied by the test author; imports needed are `reactor.test.StepVerifier` and `org.springframework.security.oauth2.jwt.JwtException`. Expected error classes may need adjustment depending on exception wrapping in your version.

Never turn a fake decoder like `token -> Mono.just(anyJwt)` into a "signature test": it performs no JWS verification.

## 18. Common Issues When Upgrading Versions

### 18.1. `.cache(...)` Does Not Compile

~~~text
Cannot resolve method 'cache' in
NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder
```

Commonly caused by copying from **Servlet `NimbusJwtDecoder`** docs. Fix: read the Reactive builder Javadoc for your exact version and use the default cache or an appropriate key source extension.

### 18.2. `.restOperations(...)` Does Not Compile

~~~text
Cannot resolve method 'restOperations'
```

Cause: the Reactive builder uses **`.webClient(...)`** instead of `RestOperations`.

### 18.3. `withIssuerLocation(...)` Is Missing

The project may be on Spring Security **prior to 6.1**. Check your BOM/dependencies; use `withJwkSetUri(...)` or `ReactiveJwtDecoders.fromIssuerLocation(...)` per the actual API. Do not work around it by hand-parsing metadata unnecessarily.

### 18.4. `validateType(...)` Is Missing

This method appeared in Javadocs around **6.5+**. On older versions, configure token type/validators via supported APIs or plan a version upgrade per project process.

### 18.5. Custom Bean Makes Issuer Validation Disappear

Symptom: tokens from another issuer are accepted despite valid signatures, or behavior differs from Boot properties.

Cause: declaring `ReactiveJwtDecoder` yourself and forgetting:

~~~java
decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer)
);
~~~

This is only part of the validation contract; add audience/token-type policies when required by the API.

### 18.6. Timeout Config Has No Effect

Check:

- Was the custom `WebClient` actually attached to `NimbusReactiveJwtDecoder` via `.webClient(...)`?
- Did `SecurityWebFilterChain` actually select your custom decoder bean?
- Does another chain have its own decoder?
- Is the network call actually hitting issuer discovery or JWKS?
- Is a proxy/gateway masking the timeout?
- Is the wait happening in DNS, TLS, connect, response, or cache?
- Are retries inflating total duration?
- Is the request hitting the key cache, so no network call occurs and timeouts never trigger?

### 18.7. Startup Succeeds Yet the First Request Fails

When issuer discovery/decoder initialization is deferred, the app can start even while the AS is failing. The first request needing JWKS may return 401 or an authentication/network error depending on handlers. This is a consequence of deferred network dependencies.

Distinguish **startup readiness** from **first-request token verification capability**. If the system includes a readiness check for JWT verification, keep it bounded and never make every liveness probe depend on the AS.

### 18.8. Key Rotation Causes Periodic 401s

If a new `kid` is used by the AS before the Resource Server updates its key source, some new JWT requests can be rejected.

Check the JWKS publication timeline, token `kid`, cache refresh behavior, AS overlap window, and egress. Never turn off signature validation to cope with rotation.

### 18.9. Connection Pool Exhaustion

If the decoder must repeatedly fetch JWKS during an outage or high concurrency, the `WebClient` connection pool can saturate. Fixes include caching, request coalescing, concurrency limits, and retry budgets—not merely growing the pool indefinitely.

### 18.10. WebClient Configured with a Global `Authorization` Header

If a shared HTTP client automatically attaches user bearer tokens to every outgoing request, the JWKS endpoint may receive credentials it does not need. Isolate a dedicated `WebClient` for JWKS.

## 19. 401, 403, and 5xx When JWKS Encounters Issues

| Case | Typical outcome | Handling layer |
|---|---|---|
| No bearer token to private API | 401 | Unauthenticated |
| Invalid JWT signature | 401 | Crypto verification |
| Expired token | 401 | JWT timestamp |
| Wrong issuer or audience | 401 | JWT claims validation |
| Valid JWT lacking scope | 403 | Authorization |
| Token needs uncached public key and JWKS is unavailable | Not authenticated; status depends on handler/config | Key retrieval/authentication dependency |
| AS returns malformed JWKS JSON | Not authenticated; key source error | JWKS parsing |
| Unknown non-existent `kid` | Not authenticated | Key selection |
| Redis cache/JWKS gateway failure | Never auto-allow; handle dependency outage | Infrastructure |
| Browser CORS preflight failure | May report CORS error | Not JWT key retrieval |

Record the failure type in observability. Some authentication failures return 401; upstream outages can map to 5xx/503 depending on design. **Do not claim every JWKS failure is always 401 or always 503 without checking actual exception handling.**

More important than the status code is **fail-closed** behavior: when you cannot prove a token was signed by a trusted source, business logic must not proceed.

## 20. Protecting Resource-Level Authorization After JWT Decoding

Even when WebClient fetches the right JWK and the JWT has:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

`SCOPE_orders.read` only proves the access token was granted read scope by the AS per contract. It **does not** prove user 42 can view orders in another tenant.

A service must still check:

~~~text
Authenticated JWT
  AND SCOPE_orders.read
  AND subject belongs to requested tenant
  AND order actually belongs to that tenant
  AND owner/ACL policy permits
```

Changing timeouts/caching at the JWKS layer **must never alter the semantics of these permissions**.

## 21. Systematic Diagnosis Before Editing Code

When seeing reports that "JWT verification is occasionally slow":

**Step 1 — Check whether it is actually JWKS fetching.** Inspect outbound HTTP telemetry to issuer/JWKS rather than assuming every JWT decode hits the network.

**Step 2 — Confirm JWT vs. opaque token.** If the system uses introspection, `NimbusReactiveJwtDecoder` is not the main component to tune.

**Step 3 — Confirm the stack.** WebFlux must use `ReactiveJwtDecoder`/`WebClient`, not `JwtDecoder`/`RestTemplate`.

**Step 4 — Check versions.** Inspect effective dependency versions/BOM in the project build (not just the latest blog post).

**Step 5 — Identify the type of network delay.** DNS, TCP connect, TLS, response, redirect, or retries?

**Step 6 — Check key-source URIs.** Is discovery metadata accurate? Is a reverse proxy rewriting incorrectly? Are internal URIs configured as trusted by the server?

**Step 7 — Inspect caching and rotation.** Is JWKS fetched on every request or periodically? When does the AS publish new `kid` values?

**Step 8 — Make targeted WebClient changes.** Configure dedicated timeouts/connectors without disabling validators.

**Step 9 — Run stub JWKS tests.** Validate signatures and measure network fetches across cold/warm/rotation/outage cases.

**Step 10 — Monitor post-deploy.** Watch 401/403s, fetch failures, p99 latency, connection pools, and AS load.

Do not tweak timeouts, retries, caching, algorithms, and issuer all at once—otherwise it becomes hard to tell which change caused an issue.

## 22. Misconceptions to Avoid

**"A WebFlux JWT Resource Server must call the Authorization Server on every request."** Not by default. Once matching public keys are cached, JWTs can be verified locally; network calls depend on key source/cache/rotation.

**"`.cache(Cache)` exists on every Nimbus JWT builder."** False. Servlet and Reactive APIs differ; the Reactive JWK Set URI builder in 6.5/7.1 has no such method.

**"Copying `RestTemplateBuilder` config from MVC works in WebFlux."** False. The Reactive builder uses `WebClient`.

**"WebClient timeouts determine whether a JWT is expired."** False. HTTP timeouts differ from `exp`/`nbf` validation.

**"Setting `responseTimeout` to 3 seconds means the whole decode takes at most 3 seconds."** Not necessarily; discovery, DNS, connect, TLS, retries, parsing, and other layers still add time.

**"Caching JWKS means you no longer need to verify signatures per request."** False. Caching public keys is not caching authentication results.

**"5-minute JWKS caching is the exact default for every Reactive version."** Do not assume this from Servlet documentation.

**"If the JWKS endpoint is failing, allow JWTs temporarily to avoid API downtime."** False. Without trusted key evidence, tokens must never authenticate.

**"JWT header `jku` or `kid` is trustworthy enough to fetch keys."** False. JWT headers are client-controlled until verified; the JWKS source must come from configuration/allowlists.

**"Checking only the signature is enough."** False. You need issuer, audience, timestamps, and token profile/algorithms per contract.

**"Declaring a custom decoder bean still lets Boot apply all JWT properties automatically."** Do not assume that; a custom bean can override auto-configuration.

**"`withIssuerLocation` exists on all Spring Security 5.x."** False. Per Javadoc, the Reactive builder gained that method in 6.1.

**"`.validateType(false)` is an easy way to accept all access tokens."** Dangerous unless replaced by a proper type/profile validator.

**"Seeing no JWKS requests in logs means the decoder isn't working."** Not necessarily; it may be using cached keys.

**"JWKS public keys should be stored alongside private signing keys."** No. The Resource Server needs only public keys; private keys belong strictly in the AS/signing service.

**"MockMvc/`WebTestClient.mockJwt()` proves timeouts and JWKS caching work."** No. Mock JWT authentication normally skips the real decoder.

## 23. Self-Check Questions

**1.** Does `NimbusReactiveJwtDecoder` belong to WebFlux or the Servlet stack?

> Reactive/WebFlux. It implements `ReactiveJwtDecoder`.

**2.** Which method on the Reactive builder customizes the HTTP client retrieving JWKS?

> `.webClient(WebClient)`.

**3.** Can `.restOperations(RestTemplate)` be used on `NimbusReactiveJwtDecoder` just like MVC?

> Not on the Reactive JWK Set URI builder. That is a Servlet decoder pattern.

**4.** Can `.cache(Cache)` be called directly on the Reactive builder in Spring Security 6.5/7.1?

> No. Choose the default mechanism or a version-compatible cache/key source extension.

**5.** How does `issuer-uri` differ from `jwk-set-uri`?

> Issuer identifies the trusted token-issuing authority; JWK Set URI is where public keys are fetched. They may use different hostnames, yet proper issuer validation must remain intact.

**6.** Why use a dedicated `WebClient` for JWKS?

> To control timeouts/TLS/proxies and prevent accidentally attaching bearer tokens/sensitive headers from a shared outgoing client.

**7.** Are `CONNECT_TIMEOUT_MILLIS` and `responseTimeout` the same?

> No. One bounds TCP connection establishment; the other applies response waiting policy. Total request time may also include DNS/TLS/retries.

**8.** If the JWKS URL returns 404 or times out when a token carries a new `kid`, should the token be allowed?

> No. Without a trusted public key to verify the signature, the token cannot be authenticated.

**9.** How is `SupplierReactiveJwtDecoder` useful?

> It lazily initializes the delegate decoder, preserving deferred discovery when declaring a bean yourself; it does not guarantee the first request succeeds if the AS is down.

**10.** Why not cache "this JWT is valid" indefinitely?

> Because expiration, revocation/policy changes, and validation profiles can change; caching public keys differs from caching authenticated principals.

**11.** Why does key rotation need an overlap window?

> So Resource Servers have time to observe the new key while already-issued older tokens remain verifiable until expiration per policy.

**12.** When seeing an unknown `kid`, is it right to fetch the key from `jku` in the JWT header?

> Never by default. The JWK source must be server-configured and allowlisted, not taken from URLs specified by an untrusted token.

**13.** With a custom decoder using `WebClient`, why must `setJwtValidator(...)` still be called?

> Because once you declare a custom decoder bean, you cannot assume Boot still applies issuer/audience/token-type validators automatically. Preserve the validation contract.

**14.** Why is `mockJwt()` insufficient to test JWKS caching?

> Because it mocks authentication and usually bypasses JWKS networking and the decoder; use real signed JWTs, a real decoder, and a mock JWKS endpoint counting requests.

**15.** Does changing the WebClient timeout allow a token lacking `SCOPE_orders.write` to make a POST request?

> No. Network key retrieval and HTTP authorization are two independent layers.

## 24. References

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): issuer discovery, JWKS, `ReactiveJwtDecoder`, trusted algorithms, and validators.
- [Spring Security 6.5 — Reactive JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html): code and API reference for the 6.5 branch.
- [Spring Security — NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): `withJwkSetUri`, `withIssuerLocation`, `withJwkSource`, `setJwtValidator`.
- [Spring Security — JwkSetUriReactiveJwtDecoderBuilder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder.html): `webClient`, `jwsAlgorithm`, `validateType`, `build`; **no `.cache(Cache)`**.
- [Spring Security 6.5 — Reactive JWK Set builder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder.html): compare with 7.1 Javadoc.
- [Spring Security — SupplierReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/SupplierReactiveJwtDecoder.html): lazy decoder initialization.
- [Spring Security — Reactive JWK Source builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.JwkSourceReactiveJwtDecoderBuilder.html): advanced extension for Reactive key sources.
- [Spring Security — Servlet JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): compare `NimbusJwtDecoder`, `.restOperations(...)`, `.cache(...)`.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): `ReactorClientHttpConnector`, connect/response/read timeouts, codec buffer limits, and resource management.
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection pooling, timeouts, TLS, proxies, and Netty behavior.
- [Spring Security — WebFlux OAuth2](https://docs.spring.io/spring-security/reference/reactive/oauth2/): Resource Server role and WebFlux security integration.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK and JWK Set.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf`.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): avoiding algorithm confusion, cross-JWT confusion, and flawed validation.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): Authorization Server discovery metadata.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token JWT profile and audience.

**Conclusion:** When customizing public key retrieval in a **WebFlux JWT Resource Server**, start from `NimbusReactiveJwtDecoder.withJwkSetUri(...)` or `withIssuerLocation(...)`, configure the HTTP client via **`.webClient(...)`**, and set timeouts on Reactor Netty/`WebClient`. For caching, **do not copy `.cache(Cache)` from the Servlet decoder to the Reactive builder**; verify your exact version and requirements before choosing the default mechanism, a trusted JWKS gateway, or a custom key source. Regardless of network optimizations, always preserve signature, issuer, audience, expiry, and token-type validation, test rotation/outages, and **fail closed when trusted keys cannot be obtained**.
