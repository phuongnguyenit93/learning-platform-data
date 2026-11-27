# Customizing the HTTP Client and Cache Within Decoder Capabilities

## 1. From Access Token to JWKS: Where Customization Needs Arise

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, a Spring Boot API typically receives access tokens as signed JWTs:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
~~~

If the token is a **JWS**, the Resource Server must verify its signature. The JWT header might carry:

~~~json
{
  "alg": "RS256",
  "kid": "shop-signing-key-2026-11",
  "typ": "at+jwt"
}
~~~

The issuer (**Authorization Server**) signs with a private key; the API retrieves the **public key** from the **JWK Set (JWKS)** published by the issuer. Example URI:

~~~text
https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

This is an illustrative Identity Provider URL; actual JWKS paths depend on the provider and should come from trusted metadata.

In principle, every request passes through multiple steps:

1. Extract the Bearer token from the HTTP request.
2. Identify the algorithm/key ID from the untrusted token; look up keys only in **trusted configured** JWKS sources.
3. Obtain the right public key to verify the JWS signature.
4. Validate issuer `iss`, audience `aud`, `exp`, `nbf`, and token profile constraints.
5. Map scopes/roles to authorities and authorize the endpoint/resource.

Operational pain points commonly appear at step 3:

- The JWKS endpoint responds slowly or drops connections.
- High API request volume drives repeated JWKS queries.
- The Authorization Server rotates signing keys and emits tokens with a new `kid`.
- Multiple API replicas hold separate caches and observe new keys at different times.
- An issuer exposes a large JWKS, or multiple issuers use distinct endpoints.
- Internal environments require custom proxies, truststores, timeouts, or caching beyond defaults.

Spring Security exposes extension points on **`NimbusJwtDecoder`** to customize the **HTTP client** and **JWK Set cache**. However, replacing the decoder also affects auto-configuration and JWT validators; you must understand the exact scope governed by each extension point.

> Focus of this lesson: **customizing how verification keys are fetched and cached** while keeping full JWT validation intact. Never equate JWKS caching with access-token caching, and never expect HTTP/cache extensions alone to supply full resilience.

This lesson uses a **Servlet Resource Server** (Spring MVC, `HttpSecurity`, `NimbusJwtDecoder`). With WebFlux, reactive decoders and reactive HTTP clients expose different APIs.

## 2. JWK, JWKS, and the Verification Flow

### 2.1. JWK and JWKS

A **JWK (JSON Web Key)** represents a key in JSON. An illustrative public RSA JWK:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "kid": "shop-signing-key-2026-11",
  "alg": "RS256",
  "n": "<PUBLIC_RSA_MODULUS_BASE64URL>",
  "e": "AQAB"
}
~~~

This JWK describes only a public key; `n` is a placeholder. A **JWKS (JSON Web Key Set)** holds a list of JWKs:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "shop-signing-key-2026-10",
      "alg": "RS256",
      "n": "<OLD_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "shop-signing-key-2026-11",
      "alg": "RS256",
      "n": "<NEW_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

The Authorization Server can publish both old and new keys simultaneously during **key rotation**. The Resource Server verifies older tokens with the old public key while those tokens remain permitted, and accepts tokens signed with the new key once it fetches the JWKS containing the new public key.

Never put private signing keys into a public JWKS. Resource Servers verify JWS signatures using public keys and never need the issuer's private key.

### 2.2. Key Retrieval Over HTTP and Caching Flow

~~~mermaid
sequenceDiagram
    participant Client as API Client
    participant API as Spring Resource Server
    participant Cache as JWK Set Cache
    participant IdP as IdP JWKS Endpoint
    Client->>API: Authorization: Bearer JWT
    API->>API: Read JWS alg/kid
    API->>Cache: Look up JWK Set by JWKS URI
    alt Matching public key available
        Cache-->>API: Cached JWK Set
    else Needs JWKS fetch or refresh
        API->>IdP: HTTPS GET jwks_uri
        IdP-->>API: JWKS JSON
        API->>Cache: Store JWK Set
    end
    API->>API: Verify JWS and validate JWT
    API->>API: Check authorization
    API-->>Client: HTTP response
~~~

The diagram illustrates the logical stages. **Not every request sends an HTTP GET to the JWKS**: actual behavior depends on cache state, algorithms, and the Nimbus/Spring Security implementation in your running version.

Distinguish responsibilities:

| Component | Responsibility |
|---|---|
| `BearerTokenAuthenticationFilter` | Extracts the token from the request and initiates authentication |
| `NimbusJwtDecoder` | Parses signed JWTs, selects keys, verifies signatures, and runs validators |
| JWKS endpoint | Distributes the issuer's public keys |
| Decoder's HTTP client | Connects to metadata/JWKS endpoints when needed |
| JWKS cache | Retains the JWK Set to reduce repeated key lookups |
| `JwtValidators` | Enforces issuer, expiration, and other configured claims |
| `AuthorizationFilter` / method security | Uses authorities/principal to make access decisions |

**`kid` is not proof of trust.** A token can declare any `kid`. The decoder should select keys only from key sets belonging to Resource Server-approved issuers/JWKS URIs, paired with a signing-algorithm allowlist.

## 3. Built-In Capabilities of `NimbusJwtDecoder`

In Spring Security Servlet, `JwtDecoder` is an abstraction interface. The standard implementation is **`NimbusJwtDecoder`**, providing builders:

~~~java
NimbusJwtDecoder.withIssuerLocation(issuer)
NimbusJwtDecoder.withJwkSetUri(jwksUri)
~~~

Primary customization hooks:

| API | Meaning |
|---|---|
| `withIssuerLocation(issuer)` | Initializes from issuer and metadata discovery to resolve the JWKS URI |
| `withJwkSetUri(jwksUri)` | Uses an explicitly configured trusted JWKS URI |
| `restOperations(restOperations)` | Customizes the HTTP transport used by the corresponding builder path |
| `cache(cache)` | Supplies a Spring `Cache` to cache JWK Set contents |
| `jwsAlgorithm(...)` / `jwsAlgorithms(...)` | Restricts accepted JWS algorithms |
| `setJwtValidator(...)` | Configures issuer/time/audience/contract validation |
| `setClaimSetConverter(...)` | Customizes claim conversion when needed by profile |

**`restOperations(...)` and `cache(...)` are not methods on every `JwtDecoder`**. They are capabilities of specific builders/implementations. If replacing `NimbusJwtDecoder` with another decoder, check that implementation's own capabilities.

### 3.1. A Simple Configuration May Suffice

If the provider supports discovery:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

And filter chain:

~~~java
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
~~~

Imports for the example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
~~~

When Spring Boot auto-configures the decoder, it already includes public key fetching and JWKS caching. If default HTTP/cache policies meet your needs, there is no reason to define a custom `JwtDecoder` bean.

If your system requires dedicated audience/token type/claim validation, configure them per contract: `issuer-uri` alone is not enough for every JWT access token profile.

## 4. Timeouts When the Resource Server Fetches JWKS

### 4.1. Connect Timeout vs. Read Timeout

To verify a new token carrying an uncached `kid`, the Resource Server may need an HTTPS GET to the JWKS endpoint. If the connection stalls, API requests stall at the authentication layer.

Two commonly configured limits:

- **Connect timeout**: maximum wait time to establish the connection.
- **Read/socket timeout**: maximum wait time reading the response over an open connection.

According to **current Spring Security Servlet documentation**, the default timeouts are described as **30 seconds for connect and 30 seconds for read**. Earlier Spring Security releases had different defaults; when SLAs matter, **verify your exact version and configure timeouts explicitly**.

These timeouts do not necessarily cap total wall-clock duration for the entire operation. DNS, TLS, proxies, connection pools, retries, and multiple metadata/JWKS calls can shift total elapsed time. Different HTTP clients also implement timeout details slightly differently.

### 4.2. Creating a `RestOperations` with Explicit Timeouts

Example using `RestTemplate` and `SimpleClientHttpRequestFactory`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestOperations;
import org.springframework.web.client.RestTemplate;

@Configuration
public class JwksHttpConfig {

    @Bean
    RestOperations jwksRestOperations() {
        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();

        // int-based setters use milliseconds.
        factory.setConnectTimeout(2_000);
        factory.setReadTimeout(4_000);

        return new RestTemplate(factory);
    }
}
~~~

Here **2 seconds** and **4 seconds** are purely illustrative. Choose real values based on system latency, issuer availability, gateway timeouts, and concurrency levels.

`SimpleClientHttpRequestFactory` illustrates basic setup and **does not provide connection pooling, jittered retries, or circuit breaking**. If you need proxies, enterprise TLS truststores, connection pools, mTLS, or tracing, select an appropriate `ClientHttpRequestFactory` and construct a dedicated `RestOperations` for JWKS fetching.

Never reuse a REST client whose interceptor attaches user access tokens to outgoing requests for JWKS fetching; JWKS retrieval is an infrastructure operation and must never leak caller credentials to key endpoints.

### 4.3. Wiring the HTTP Client into a Decoder with an Explicit JWKS URI

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.web.client.RestOperations;

@Configuration
public class JwksDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Qualifier("jwksRestOperations") RestOperations rest,
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwks-uri}") String jwksUri) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .restOperations(rest)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer));

        return decoder;
    }
}
~~~

Corresponding properties:

~~~yaml
app:
  security:
    issuer: https://id.example.test/realms/shop
    jwks-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

The `app.security.*` names are **application-defined properties**, not properties Spring Boot automatically wires into Resource Server. The JWKS URI is illustrative; in practice obtain it from `jwks_uri` in provider metadata or your IdP contract.

Specifically, `withJwkSetUri(...)` sets **the public key source**; to validate `iss`, attach an issuer validator as shown. Never assume specifying the key source automatically validates the issuer.

### 4.4. When Issuer Discovery Is Needed

If you want the decoder to resolve `jwks_uri` via metadata:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .restOperations(jwksRestOperations)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer));
~~~

This is the API documented by Spring Security for customizing the HTTP client with issuer discovery. Distinguish **when discovery happens**:

- Current Spring Boot/Spring Security auto-configuration can use **lazy discovery** when the first JWT request arrives.
- Calling `withIssuerLocation(...).build()` directly inside a bean may trigger discovery during bean initialization, depending on version and setup.
- Using `withJwkSetUri(...)` skips discovery to locate the JWKS, yet fetching public keys over HTTP still needs the network when no matching cached key exists.

Never state unconditionally that the IdP must be online at startup or that the IdP can never affect the first request. That depends on how the decoder is built and your exact version.

## 5. JWKS Caching Is Key Caching, Not Token Caching

### 5.1. What Does the Cache Hold?

Spring Security documentation notes that a JWT Resource Server typically **caches the JWK Set in memory**, with a default reference lifetime of about **5 minutes**. Caching reduces the need to download public keys on every request.

| Data | Is It Stored in the JWK Set Cache? | Notes |
|---|---|---|
| **Issuer's JWKS JSON** | Yes | Holds public keys for JWS validation |
| User's JWT access token | No | JWTs are still validated per request |
| "Approved" `exp`, `aud`, `scope` claims | No | Not an authorization result cache |
| Opaque token introspection results | No | Uses separate introspection mechanisms |
| Authorization Server's private signing key | No | Never placed in a public JWKS |

**JWKS caching never extends a token's lifetime.** Even while the public key sits in cache, an expired JWT must be rejected per `exp`; tokens with wrong issuer or audience are still rejected by configured validators.

Caching also does not guarantee detecting JWTs revoked prior to `exp`. If instant revocation is required, design token lifetimes, introspection/denylists, and threat models accordingly.

### 5.2. The Decoder's `cache(Cache)` Keys by URI

The builder supports:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUri)
    .cache(jwkSetCache)
    .build();
~~~

`jwkSetCache` must be an `org.springframework.cache.Cache` implementing the semantics used by Spring Security:

- **Key:** JWK Set URI.
- **Value:** JWK Set JSON.

A single cache entry holds the **entire JWK Set**, potentially containing many `kid`s. It is **not** keyed per JWT, per `sub`, per `jti`, or per `kid`. Never write a cache provider assuming the key is a token ID and expect this builder to work.

### 5.3. Spring Cache Is an Abstraction

`org.springframework.cache.Cache` and `CacheManager` are generic APIs; the backing provider handles eviction/TTL and in-memory vs. distributed storage. For a local cache with TTL, Caffeine is a common choice.

Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Caffeine integrates with Spring Cache through Spring Boot's cache starter when classpath and config match. Use dependency versions managed by your Spring Boot BOM.

### 5.4. Caffeine Example: TTL and Size Bounds

~~~java
package com.example.orders.security;

import java.time.Duration;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JwksCacheConfig {

    @Bean
    CacheManager jwksCacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("jwks");

        manager.setCaffeine(Caffeine.newBuilder()
            .maximumSize(20)
            .expireAfterWrite(Duration.ofMinutes(3)));

        return manager;
    }
}
~~~

This example:

- Names the cache `jwks`.
- Retains at most 20 cache entries; each `NimbusJwtDecoder` entry corresponds to one JWKS URI.
- Sets entry TTL to roughly **3 minutes after write**.
- Creates an **in-process cache**: other replicas do not share it.
- Has no direct link to token `exp` claims.

Three minutes and 20 entries are illustrative numbers, not fixed recommendations. TTL should balance JWKS traffic against key-rotation freshness; entry capacity depends on the actual number of issuers/JWKS URIs.

### 5.5. Wiring the Cache into the Decoder

~~~java
package com.example.orders.security;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class CachedDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Qualifier("jwksCacheManager") CacheManager manager,
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwks-uri}") String jwksUri) {

        Cache cache = Objects.requireNonNull(
            manager.getCache("jwks"),
            "The JWKS cache must exist");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .cache(cache)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer));

        return decoder;
    }
}
~~~

`CacheManager#getCache(...)` can return `null`. Requiring the cache explicitly avoids silently falling back on a misnamed cache. When an app has multiple `CacheManager` beans, use `@Qualifier` to inject the right one.

This is a **standalone example**; in a real codebase keep only one active decoder configuration to avoid conflicting `JwtDecoder` beans.

## 6. Combining HTTP Client, Cache, and Validators

Suppose the Orders API requires:

| Property | Illustrative Value |
|---|---|
| JWT issuer | `https://id.example.test/realms/shop` |
| JWKS URI | `https://id.example.test/realms/shop/protocol/openid-connect/certs` |
| Audience | `orders-api` |
| JWS algorithm | `RS256` |
| JWKS connect timeout | 2 seconds |
| JWKS read timeout | 4 seconds |
| Cache | Local Caffeine, 3-minute TTL, max 20 entries |

YAML:

~~~yaml
app:
  security:
    jwt:
      issuer: https://id.example.test/realms/shop
      jwks-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
      audience: orders-api
~~~

Java:

~~~java
package com.example.orders.security;

import java.time.Duration;
import java.util.Objects;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.web.client.RestOperations;
import org.springframework.web.client.RestTemplate;

@Configuration
public class OrdersJwtInfrastructureConfig {

    @Bean
    CacheManager jwksCacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("jwks");
        manager.setCaffeine(Caffeine.newBuilder()
            .maximumSize(20)
            .expireAfterWrite(Duration.ofMinutes(3)));
        return manager;
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwks-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String audience,
            @Qualifier("jwksCacheManager") CacheManager manager) {

        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2_000);
        factory.setReadTimeout(4_000);
        RestOperations jwksHttp = new RestTemplate(factory);

        Cache jwksCache = Objects.requireNonNull(
            manager.getCache("jwks"),
            "Missing 'jwks' cache");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .restOperations(jwksHttp)
            .cache(jwksCache)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token has incorrect audience",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                expectedAudience));

        return decoder;
    }
}
~~~

**Explanation of each extension point:**

1. `withJwkSetUri(jwksUri)` pins the configured public key URI.
2. `restOperations(jwksHttp)` supplies the HTTP transport with contract-aligned timeouts.
3. `cache(jwksCache)` plugs in Spring Cache for JWKS JSON.
4. `jwsAlgorithm(RS256)` restricts the permitted signing algorithm.
5. `JwtValidators.createDefaultWithIssuer(issuer)` preserves issuer and default timestamp validators.
6. `expectedAudience` rejects tokens not issued for Orders API.
7. Inside Spring Resource Server, this decoder is invoked whenever a Bearer JWT arrives for authentication.

If the actual issuer uses PS256 or ES256, adjust `jwsAlgorithm(...)` accordingly; never let incoming tokens choose arbitrary algorithms. JWE or opaque token flows are not enabled by this signed-JWT builder.

### 6.1. Filter Chain Using the Decoder

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
~~~

If there is no single unambiguous `JwtDecoder` bean to auto-wire, or if multiple decoders exist, pass the decoder explicitly to the DSL: `.jwt(jwt -> jwt.decoder(customDecoder))`. Keep only one intentional decoder mechanism per chain.

### 6.2. When Defining a Custom Bean, Re-Check Auto-Configuration

Spring Boot can auto-configure a decoder from:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences: orders-api
~~~

Yet once the application defines its own `@Bean JwtDecoder`, Boot's auto-configuration typically **backs off in favor of that bean**. Convenient properties like `audiences` must then not be assumed to apply automatically to the custom decoder.

Every custom decoder must preserve **JWT signature verification**, issuer/time/audience validation, and token-profile/claim constraints per contract. Never lose `iss` or `aud` validation just because you customized timeouts or caching.

## 7. TTL and Key Rotation: What Actually Drives Refreshes?

### 7.1. JWT Lifetime Differs from JWKS TTL

An access token contains:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "aud": ["orders-api"],
  "exp": 2000000000
}
~~~

A three-minute JWKS cache TTL **does not alter `exp`**. An expired token remains invalid even when its signing public key is cached. Conversely, an unexpired token without a matching public key still cannot be verified.

Multiple independent TTLs can coexist:

- JWT lifetime of the token itself.
- TTL of the Spring Cache holding JWKS JSON.
- Internal cache/refresh policy inside the Nimbus key source, depending on version.
- HTTP cache headers on a CDN/proxy serving the JWKS.
- DNS caching and connection pooling, which are not JWKS data caches directly.

Never deduce key-update timing across every layer from a single TTL number.

### 7.2. Publish Before Using a New Key

A solid rotation sequence looks like:

~~~mermaid
flowchart TD
    A["Issuer signs tokens with K1"] --> B["JWKS publishes K1"]
    B --> C["Issuer adds K2 to JWKS while keeping K1"]
    C --> D["API gets a chance to refresh JWKS"]
    D --> E["Issuer starts signing new tokens with K2"]
    E --> F["API verifies K2 with new public key"]
    F --> G["Retain K1 until old tokens expire per policy"]
    G --> H["Issuer removes K1 on schedule"]
~~~

In practice, issuers may rotate on schedule or in emergencies, always requiring coordination on:

- When the new key is published.
- The K1/K2 overlap window.
- TTL and refresh policy on the Resource Server.
- Remaining unexpired old tokens.
- Clock skew and cache states across multiple replicas.
- Handling when the JWKS endpoint is unavailable.

**Never assert that an unknown `kid` always triggers an immediate cache refresh.** Refresh-on-unknown-key behavior depends on Nimbus/Spring internals and custom caches. Some configurations proactively fetch new keys, yet always verify in a realistic environment.

### 7.3. TTL Too Short vs. Too Long

| TTL Choice | Advantage | Disadvantage |
|---|---|---|
| Very short | Observes JWKS updates sooner | Higher HTTP traffic, tighter dependency on IdP |
| Moderate | Balances traffic and key freshness | Slight lag seeing new keys in some cases |
| Very long | Minimal repeated JWKS traffic | Can delay rotation pickup or emergency key revocation |

Caching alone does not solve a **private signing key compromise**. That requires key revocation/rotation policies, cache invalidation, token revocation, and incident response—not merely tweaking TTL.

## 8. Local Caches, Multiple Replicas, and Shared Caches

### 8.1. Caffeine Defaults to Per-Process Storage

With three replicas:

~~~text
Orders API replica A --> Caffeine cache A
Orders API replica B --> Caffeine cache B
Orders API replica C --> Caffeine cache C
~~~

Each cache can populate at a different time. When many pods roll out together or caches expire simultaneously, the IdP can see a **burst of JWKS requests**.

Operational mitigations:

- Provision the IdP/JWKS endpoint with enough availability and capacity.
- Schedule key publication ahead of signing cutover.
- Tune TTLs thoughtfully and monitor JWKS fetch count/latency.
- Consider prewarming or controlled rollouts where required, while keeping policy-compliant key verification.
- Never log raw JWTs to inspect cache behavior.

### 8.2. When Is a Shared Cache Needed?

`Spring Cache` can back onto Redis or another distributed store if configured properly. A shared cache can cut outbound JWKS calls compared to independent local caches.

~~~text
API replica A ----+
                  |
API replica B ----+----> Shared JWKS cache
                  |
API replica C ----+
~~~

However, a shared cache adds a new dependency. Evaluate:

- How does the Resource Server behave if the shared cache goes down?
- Is network latency to Redis lower than hitting a local cache?
- Do all replicas share compatible cache names, TTLs, serializers, and key prefixes?
- Do multiple issuers/tenants share the same cache?
- Who has permission to overwrite entries keyed by JWKS URI?
- What is the eviction/invalidation policy when an issuer revokes a key?
- Does Nimbus hold an internal layer of caching that does not sync immediately with the shared cache?

**The trusted source remains the configured issuer/JWKS URI.** Even though a shared public-key cache holds no private keys, it must still be protected against tampering, misconfiguration, or untrusted writes.

Use a shared cache only when genuinely needed and verified compatible. With a small replica count, local caching plus a resilient JWKS endpoint is often cleaner.

### 8.3. Is the Cache Key `kid`?

No. Under the `cache(Cache)` contract documented by Spring Security:

~~~text
Cache key:
  https://id.example.test/realms/shop/protocol/openid-connect/certs

Cache value:
  {"keys":[{"kid":"K1",...},{"kid":"K2",...}]}
~~~

A cache entry stores **JWKS JSON**, so one entry can hold multiple keys. Never build a custom cache adapter storing `kid -> JWK` and hand it to the builder unless it honors Spring's key/value contract.

## 9. When the JWKS Endpoint Fails

### 9.1. Matching Key Already in Cache

If the Resource Server already caches the matching public key and the token passes validators, it can verify signatures without fetching JWKS for that request. A brief network blip need not break every token.

Still, availability depends on expiry/refresh rules, caching internals, and process state. Never promise that after one JWKS fetch an API will authenticate offline forever.

### 9.2. New Key Needed While the Network Is Down

A new JWT carries `kid` K2, while cache holds only K1. If trusted public key K2 cannot be retrieved, the Resource Server **must not accept the token**, even if `iss` and `scope` inside the payload look valid.

Report JWKS HTTP failures clearly—never skip signatures, never accept `alg=none`, and never trust a JWKS URL proposed by the token.

### 9.3. Do Timeouts Always Produce 401?

Do not commit to one fixed status code. When the decoder fails to verify a token, the API may return authentication failure/401; however, network outages, timeouts, or infrastructure errors during JWKS fetching can surface as service errors depending on library internals and custom exception handlers.

Separate cleanly in logs and metrics:

- **Invalid signature**: matching key existed, yet signature failed verification.
- **Unknown `kid`**: no matching key located.
- **JWKS fetch timeout / HTTP 5xx**: failed to retrieve required key data.
- **Issuer/audience/time validation error**: signature may be valid, yet claims failed.
- **Insufficient scope**: authentication succeeded, authorization denied (typically 403).

Do not lump every 401 under "broken cache," nor every network failure under "revoked token."

### 9.4. Never Enable Unbounded Retries

`restOperations(...)` customizes the HTTP transport. It does not magically supply complete retry/backoff/circuit-breaker logic. Unbounded retries pin request threads and amplify load while the IdP is degraded.

If adding retries, enforce a total deadline, backoff with jitter, max attempt caps, GET idempotence safety, and overload behavior aligned with your SLO.

## 10. Limitations to Recognize Before Customizing

### 10.1. `NimbusJwtDecoder` Is Only One `JwtDecoder` Implementation

The primary Servlet OAuth 2.0 Resource Server flow for signed JWTs is:

~~~text
BearerTokenAuthenticationFilter
    |
    v
JwtAuthenticationProvider
    |
    v
NimbusJwtDecoder
    |---- HTTP fetch JWKS when needed
    |---- JWK Set cache
    |---- JWS signature verification
    |---- JWT claim validators
    v
Authentication + authorities
    |
    v
AuthorizationFilter
~~~

The builder does not dictate every nuance of networking, caching, and key selection. For deeper customization, Spring Security provides an extension point to build a **Nimbus `JWTProcessor`** and pass it to the `NimbusJwtDecoder` constructor. Doing so requires explicitly governing key-source trust, JWS algorithm allowlists, cache/refresh behavior, and validators.

Never roll your own parser by Base64URL-decoding a JWT and trusting `kid`/`iss` as authentication proof. Signature verification and full validation must remain intact.

### 10.2. Custom HTTP Clients Do Not Apply to Every Outbound Request

The decoder's `restOperations(...)` handles configuration/key fetching on that builder path. It **does not alter**:

- `RestTemplate`/`WebClient` instances used by the app for business API calls.
- OAuth 2.0 Client exchanges for authorization codes or refresh tokens.
- HTTP clients for opaque token introspection.
- Upstream API Gateways or browsers sending Bearer tokens.
- WebFlux `NimbusReactiveJwtDecoder`.

If the Resource Server uses **opaque access tokens**, configure an `OpaqueTokenIntrospector`; there is no analogous JWS/JWKS verification flow.

### 10.3. Default JWT Decoders Do Not Automatically Decrypt JWEs

The Nimbus JOSE + JWT library supports many features, yet Spring Resource Server's `NimbusJwtDecoder` in the standard signed-JWT path verifies **JWS**. If a provider issues **JWE encrypted access tokens**, dedicated decryption and validation architecture is needed; adding `cache(...)` or `restOperations(...)` does not enable JWE decryption.

### 10.4. Never Relax Verification Algorithms

Just because a signing key and token both mention `RS256` is no reason to trust arbitrary `alg` values sent by tokens. The API must enforce an algorithm allowlist per issuer contract. Never fetch public keys from untrusted `jku`/`x5u` headers or switch between RSA and HMAC based on token input.

## 11. Practical Scenario Checklist

### 11.1. HTTP/Cache Verification Test Cases

When verifying the application in a test environment with a controlled issuer/JWKS:

| Case | What to Observe |
|---|---|
| K1-signed JWT, empty cache | JWKS is fetched and token verifies cleanly |
| Second JWT with same K1 | Fetch count drops if caching works |
| Bad signature, K1 present in JWKS | Rejected even though key is cached |
| Expired JWT, K1 still cached | Rejected due to `exp` |
| Valid issuer, wrong audience | Rejected by audience validator |
| JWKS adds K2 | Decoder has a path to observe the updated key set |
| K2-signed JWT while cache holds K1 | Observe refresh/fetch behavior per implementation |
| JWKS times out, K2 needed | Unverifiable token is rejected |
| JWKS times out, K1 cached | Verifies or not depending on cache/refresh state |
| Cache TTL expires | Observe JWKS reload and key rotation behavior |
| Multiple replicas restart | Observe initial fetch burst and local/shared cache behavior |
| Nonexistent `kid` | Never grants trust to arbitrary keys |

Tests should use **test JWTs signed by a test issuer**, a test JWKS endpoint, and the real filter chain. MockMvc `jwt()` mocks authentication to test authorization rules, but **does not verify** HTTP JWKS fetching or caching.

### 11.2. What Should Observability Measure?

Key signals to track:

- JWKS HTTP GET counts, latency, timeouts, and HTTP error codes.
- Cache hits, misses, and expiries/evictions from the cache provider.
- Duration/counts of token failures when the issuer rotates `kid`.
- JWT decode errors separated from `403` authorization denials.
- Concurrent requests triggering key refreshes.
- JWKS endpoint health and multi-replica rollout convergence.
- Changes to issuer, JWKS, and allowed-algorithm configuration.

These metrics are **instrumentation targets**, not all built-in with identical names in Spring Security. Instrument the HTTP client and cache provider to collect them. Never log raw Bearer tokens, secrets, or private keys.

### 11.3. Inspecting Metadata and JWKS per Contract

Using illustrative URLs:

~~~bash
curl -i \
  https://id.example.test/realms/shop/.well-known/openid-configuration
~~~

After finding `jwks_uri` in metadata, inspect:

~~~bash
curl -i \
  https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

Do not assume every provider uses those exact paths. TLS certificates, issuer metadata, and JWKS URIs must match organization-trusted sources.

Testing the API:

~~~bash
curl -i \
  -H "Authorization: Bearer <TEST_ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

A 401 response may stem from an unverifiable JWT, wrong issuer/audience, or expired token; a 403 response may stem from a valid token missing `orders.read`. Never equate API HTTP status directly with JWKS fetch health.

## 12. Configuration Selection Matrix

| Requirement | Approach |
|---|---|
| Provider supports issuer discovery and defaults meet SLA | Spring Boot `issuer-uri` with auto-configuration |
| Need an explicit pre-known JWKS endpoint | `withJwkSetUri(...)` plus issuer validator |
| Need HTTP timeouts for JWKS fetches | `restOperations(...)` builder with configured HTTP client |
| Need custom TTL or eviction for JWKS | `cache(Cache)` builder with a Spring Cache provider |
| Need timeouts, cache, and audience together | Custom `JwtDecoder` bean with full validators |
| Need to restrict JWS algorithms | `jwsAlgorithm(...)` per issuer policy |
| Many replicas and high JWKS GET traffic | Evaluate shared caches, rollout pacing, and IdP capacity |
| Complex key rotation | Coordinate K1/K2 issuance, caching, refreshes, and monitoring |
| Need refresh-ahead, failover, or custom key sources | Evaluate Nimbus `JWTProcessor` extension and trust model |
| Opaque access tokens | Dedicated `OpaqueTokenIntrospector` |
| JWE access tokens | Dedicated decryption architecture, not just signed-JWT builder |
| WebFlux applications | Reactive decoder/HTTP client APIs, never raw Servlet code |

## 13. Core Principles to Remember

- **JWK Sets** hold public keys for verifying signed JWT/JWS tokens. The JWKS URI must be configured from a trusted source or discovered from a trusted issuer.
- **`NimbusJwtDecoder`** supports customizing the **HTTP client via `restOperations(...)`** and the **JWK Set cache via `cache(Cache)`** on supporting builders.
- Per current Spring Security Servlet docs, JWKS is typically cached in memory for around **5 minutes**, with default connect/read timeouts described as **30 seconds each**. For strict latency requirements, verify your version and configure values explicitly.
- **Custom Spring Caches** use the **JWKS URI as key** and **JWKS JSON as value**. JWKS caching is distinct from JWT lifetime, introspection results, and token revocation.
- **TTLs and key rotation must be coordinated**. Issuers should publish new keys before signing with them and retain old keys long enough per policy. Never assume every unseen `kid` forces an immediate decoder refresh.
- When defining a custom `JwtDecoder` bean, **retain issuer/time/audience/token-profile validation and algorithm allowlists**; network/cache tuning must never weaken trust boundaries.
- Timeouts and caching aid availability, yet **do not automatically provide retries, circuit breakers, failover**, or guarantee offline operation during JWKS outages.
- For needs beyond the builder API, a custom Nimbus `JWTProcessor` can be used, provided keys, algorithms, caches, and validators are all properly governed.

### References

- [Spring Security Reference — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security Reference — OAuth 2.0 Migrations](https://docs.spring.io/spring-security/reference/migration/servlet/oauth2.html)
- [Spring Framework API — Cache](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework API — CacheManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/CacheManager.html)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)

