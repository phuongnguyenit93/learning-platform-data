# Latency, availability, and token revocation visibility

## 1. Why do opaque tokens create a distinct operational problem?

In a **Spring Boot + Spring Security OAuth 2.0 Resource Server**, an API typically receives a Bearer access token:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

There are two common verification paths:

- **JWT verification:** The Resource Server checks the JWS signature using a trusted public key and validates the access token's claims. Once keys are cached, it usually does not need to call the Authorization Server (AS) on every request.
- **Opaque token introspection:** The Resource Server treats the token as an unreadable string, sending it to the **introspection endpoint** to ask the AS whether the token is still active and what attributes it carries.

Opaque token introspection is appealing when a system requires **revocation visibility**. However, this approach introduces three questions:

1. **Latency:** How long must a request wait for an HTTP round trip to the AS?
2. **Availability:** If the AS times out or returns 429 or 5xx, how does the Resource Server behave?
3. **Data freshness:** After a token is revoked, how many more requests can still be accepted?

Adding **introspection result caching** can cut latency and AS load, yet `active` status, scopes, and attributes can **go stale**. That is an intentional architectural trade-off, not something solved merely by flipping a property.

This lesson focuses on **Spring Security Servlet Resource Server** using `OpaqueTokenIntrospector`, while comparing with JWTs to clarify latency, availability, and revocation. Timeout/TTL numbers in examples are illustrative values, not universal configuration recommendations.

## 2. OAuth 2.0 Token Introspection under RFC 7662

### 2.1. How does the Resource Server query token status?

An opaque token may look like a random string:

~~~text
n5bP2u9XwQ7s1VtK3mA8...
~~~

The Resource Server does not decode `sub`, `scope`, or `exp` from this string on its own. It sends the token to the introspection endpoint provided by the AS.

Example request under **RFC 7662**:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Authorization: Basic <RESOURCE_SERVER_INTROSPECTION_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<ACCESS_TOKEN>&token_type_hint=access_token
~~~

`token_type_hint` is an **optional** parameter. The Resource Server's authentication credential for calling introspection (such as HTTP Basic) is a **separate credential**, not the user's Bearer token, and must never be placed in the frontend.

The AS may return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read profile",
  "client_id": "shop-web",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iss": "https://id.example.test/realms/shop",
  "exp": 2000000000
}
~~~

This is illustrative data. Under RFC 7662, `active` is the field governing status; other fields depend on token type and AS contract. Not every provider returns `aud`, `iss`, `exp`, or `tenant_id`.

When a token is inactive, a valid response can be:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

**Never infer a token is active simply because introspection returns HTTP 200.** The HTTP response indicates the introspection request was processed; JSON `active` represents token status.

### 2.2. Introspection endpoint 401 vs. API endpoint 401

If the Resource Server uses the wrong client ID/secret, the AS may return **401** on the introspection HTTP POST itself. That is a **Resource Server-to-AS client authentication error**, not proof that the caller's bearer token was revoked.

There are two independent HTTP exchanges:

~~~text
Exchange A: API client -> Resource Server
Exchange B: Resource Server -> AS introspection
~~~

Distinguish carefully:

| Outcome from AS | Reliable meaning | How to handle |
|---|---|---|
| HTTP 200, `active:true` | Token confirmed active by AS at query time | Build principal and check authorization |
| HTTP 200, `active:false` | AS does not confirm token active | Reject Bearer token |
| HTTP 401/403 from introspection endpoint | RS introspection credentials/access policy problem | Investigate configuration; do not assume token is revoked |
| HTTP 429 | AS rate-limiting introspection | Throttle load, apply controlled backoff |
| HTTP 5xx | AS infrastructure error | Never grant access by guessing |
| Connect/read timeout | No fresh decision from AS | Fail closed or report infrastructure error |

In Spring Security, the final status returned to the caller also depends on exception mapping. Never claim every network failure maps strictly to `401 invalid_token`; keep token errors distinct from service errors.

### 2.3. Revocation and introspection are two distinct actions

**RFC 7009** specifies requesting token revocation; **RFC 7662** specifies inspecting token status.

~~~mermaid
flowchart TD
    A["Client or admin requests revocation"] --> B["Authorization Server"]
    B --> C["AS updates token/grant state"]
    C --> D["Introspection endpoint"]
    E["Resource Server"] -->|"Re-queries token"| D
    D -->|"active=false"| E
    E --> F["Reject subsequent requests"]
~~~

Between a revocation call and the next introspection, there may be synchronization or cache lag. Opaque tokens **do not guarantee instantaneous revocation automatically**; the AS must actually reflect the change at its endpoint.

## 3. Where does Spring Security handle opaque tokens?

In the Servlet stack, the typical path is:

~~~mermaid
sequenceDiagram
    participant Client as API Client
    participant Filter as BearerTokenAuthenticationFilter
    participant Provider as OpaqueTokenAuthenticationProvider
    participant Introspector as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant Authz as AuthorizationFilter
    Client->>Filter: GET + Authorization Bearer token
    Filter->>Provider: BearerTokenAuthenticationToken
    Provider->>Introspector: introspect(token)
    Introspector->>AS: HTTP POST introspection
    AS-->>Introspector: active + token attributes
    alt active=false
        Introspector-->>Provider: authentication failure
        Provider-->>Client: typically 401
    else active=true
        Introspector-->>Provider: OAuth2AuthenticatedPrincipal
        Provider-->>Filter: BearerTokenAuthentication
        Filter->>Authz: SecurityContext populated with Authentication
        Authz-->>Client: Controller or 403
    end
~~~

Components:

| Component | Role |
|---|---|
| `BearerTokenAuthenticationFilter` | Extracts Bearer token from HTTP header |
| `OpaqueTokenAuthenticationProvider` | Invokes introspector to authenticate |
| `OpaqueTokenIntrospector` | Abstraction checking tokens via AS or another implementation |
| `SpringOpaqueTokenIntrospector` | Implementation calling the introspection endpoint |
| `OAuth2AuthenticatedPrincipal` | Principal holding attributes and authorities |
| `BearerTokenAuthentication` | Authentication built when token is valid |
| `AuthorizationFilter` | Checks endpoint permissions after authentication |

Spring Security by default normally maps scopes in the introspection response to authorities prefixed with `SCOPE_`. For example, `scope = "orders.read profile"` produces `SCOPE_orders.read` and `SCOPE_profile`.

Do not mechanically apply `@AuthenticationPrincipal Jwt` in opaque mode. The default principal is typically `OAuth2AuthenticatedPrincipal`, even when a JWT-shaped token string is verified via introspection.

## 4. Minimal configuration for Spring Boot

### 4.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 4.2. Introspection configuration

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

The endpoint and client ID are examples, while the client secret comes from environment/secret manager. Never commit secrets to the repository, place them in a browser, or write them to logs. The AS must grant appropriate introspection permissions to this client.

### 4.3. Filter chain configuration

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

`oauth2ResourceServer(...opaqueToken(...))` sets up the introspection pipeline. You do not need to write a custom filter reading `Authorization` or invoke introspection in each controller.

If the API uses Bearer headers and stateless authentication, configure sessions/CSRF according to your threat model. Never disable CSRF on endpoints using cookies/sessions just to run an example.

### 4.4. Reading the principal in a controller

~~~java
package com.example.orders.api;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        return Map.of("name", principal.getName());
    }
}
~~~

This snippet assumes the endpoint requires authentication and `name` is non-null per contract. For machine-to-machine tokens, the principal name is not necessarily a user ID; check the AS profile.

## 5. Latency: introspection on the request path

### 5.1. Latency budget

When **uncached**, a Bearer request typically waits on the network:

~~~text
Client
  |
  v
Resource Server
  |
  +-- BearerTokenAuthenticationFilter
  |
  +-- Introspection HTTPS POST
  |     +-- DNS/TLS/proxy
  |     +-- network RTT
  |     +-- AS reads token store / grant state
  |     +-- AS returns JSON
  |
  +-- create Authentication + authorities
  +-- endpoint authorization
  +-- business logic and database
  |
  v
HTTP response
~~~

A conceptual model:

~~~text
T_response = T_security_local
           + T_introspection
           + T_authorization
           + T_business
           + T_network_response
~~~

This is not an exact measurement formula for every app, yet it highlights how an AS-dependent HTTP call can dominate latency even when the controller itself is fast.

Do not naively add each component's p95 and call it the overall p95; percentiles do not necessarily occur simultaneously. Measure end-to-end p50, p95, and p99 and create a dedicated span for introspection.

### 5.2. Sources of slowness

| Cause | Impact |
|---|---|
| API and AS geographically distant | Increases round-trip time |
| Frequent new TLS/DNS/connect handshakes | Adds overhead |
| Lack of connection pooling | Prevents connection reuse |
| HTTP proxies/service meshes | Adds hops, timeouts, and retry policies |
| Slow AS token store | Increases state-lookup latency |
| AS rate-limited or under peak traffic | Increases latency and errors |
| Many Resource Servers introspecting together | Heavy aggregate load on AS |
| Synchronized cache misses | Causes bursts |
| Unbounded retries | Increases tail latency and amplifies load |

On the Servlet stack, a synchronous outbound introspection call holds request-handling resources while waiting. You cannot solve this sustainably by scaling worker threads indefinitely.

### 5.3. Load scales with RPS

If an API handles 500 requests/second requiring Bearer authentication, uncached introspection can generate roughly 500 introspection calls/second to the AS. If a single user action traverses 4 microservices and all 4 introspect the token, total calls multiply further.

Capacity planning should account for:

- Peak requests/second, not just averages.
- Fan-out across microservices.
- Token-store processing time at the AS.
- Network latency and connection counts.
- Retry counts during outages.
- Token reuse ratio.
- Distribution of valid tokens vs. random token-spray traffic.

An idle benchmark never proves a system can sustain peak p99.

## 6. Availability: the AS becomes a direct dependency

### 6.1. When the AS does not respond

With uncached opaque introspection, the Resource Server generally cannot verify tokens on its own. An AS outage impacts protected endpoints even when the Orders API and its database are completely healthy.

~~~mermaid
flowchart TD
    A["Request Bearer token"] --> B["Resource Server"]
    B --> C["Introspection"]
    C --> D{"AS returns decision?"}
    D -->|"active=true"| E["Authorization"]
    D -->|"active=false"| F["Reject token"]
    D -->|"Timeout/5xx"| G["No trusted confirmation"]
    G --> H["Fail closed or service error"]
~~~

**Fail closed:** never accept a token merely because it previously looked valid or because the AS is experiencing an outage. If a positive cache with a hard TTL exists, serving an unexpired entry must be a **pre-approved policy decision**, never an unbounded fallback.

### 6.2. Separating business and infrastructure errors

| Scenario | Data from AS? | Interpretation |
|---|---|---|
| `active:false` | Yes | Token is inactive per AS |
| `active:true`, missing scope | Yes | Authentication succeeded, authorization denied |
| Connect timeout | No | Cannot determine fresh status |
| Read timeout | Incomplete | No trusted introspection result |
| Introspection HTTP 401 | Endpoint error | RS client credentials may be invalid |
| Introspection HTTP 429 | AS throttling | Does not mean the token was revoked |
| Introspection HTTP 5xx | AS error | Not an active/inactive decision |

The final HTTP status returned to API clients depends on exception mapping. Never turn all network errors into `invalid_token` or return `200 OK` to mask outages. Internal metrics and logs must categorize them clearly.

### 6.3. Retries, circuit breakers, and bulkheads

Consider:

- **Timeouts:** never block threads indefinitely.
- **Retries with backoff/jitter:** only for transient errors, with bounded attempts and overall deadline.
- **Circuit breakers:** avoid hammering an unhealthy AS.
- **Bulkheads/concurrency limits:** prevent introspection from exhausting outbound connections or Servlet threads.
- **Rate limiting:** protect both API and AS against abnormal floods of invalid Bearer tokens.
- **Load shedding:** shed load gracefully when the authentication dependency exceeds capacity.

Never retry `active:false`: that is a decision about the token, not a transient failure. When a circuit breaker is open, **never** treat every token as active.

## 7. Configuring timeouts to match SLOs

Current Spring Security Servlet documentation notes that default connect and socket timeouts for introspection are typically **30 seconds each**. Defaults can vary across versions; for low-latency APIs, configure timeouts explicitly.

Different timeouts are distinct:

- **Connect timeout:** waiting to establish a TCP/TLS connection.
- **Read/socket timeout:** waiting for response bytes.
- **Connection-pool acquisition timeout:** waiting for a pooled connection, if pooling is used.
- **Overall deadline:** bounding the full authentication/API request including retries.

The 1-second or 2-second timeouts in the examples below illustrate configuration syntax, not universal network settings.

### 7.1. Creating `OpaqueTokenIntrospector` with a custom HTTP client

Spring Security versions support the `SpringOpaqueTokenIntrospector(String, RestOperations)` constructor. When supplying `RestOperations`, that client **must configure client authentication to the introspection endpoint itself**.

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.http.client.support.BasicAuthenticationInterceptor;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;
import org.springframework.web.client.RestTemplate;

@Configuration
public class IntrospectionHttpConfig {

    @Bean
    OpaqueTokenIntrospector introspector(
            @Value("${app.security.introspection.uri}") String uri,
            @Value("${app.security.introspection.client-id}") String clientId,
            @Value("${app.security.introspection.client-secret}") String secret) {

        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(1_000); // milliseconds
        factory.setReadTimeout(2_000);    // milliseconds

        RestTemplate http = new RestTemplate(factory);

        // RestOperations in this constructor must authenticate the client itself.
        http.getInterceptors().add(
            new BasicAuthenticationInterceptor(clientId, secret));

        return new SpringOpaqueTokenIntrospector(uri, http);
    }
}
~~~

YAML:

~~~yaml
app:
  security:
    introspection:
      uri: https://id.example.test/oauth2/introspect
      client-id: orders-api-introspector
      client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

`app.security.*` are application-defined properties. When `spring.security.oauth2.resourceserver.opaquetoken.*` via Spring Boot already fits, you can avoid defining a manual bean when no customization is needed.

`SimpleClientHttpRequestFactory` illustrates basic timeouts only. In production requiring connection pools, proxies, custom trust stores, mTLS, or tracing, choose an appropriate `ClientHttpRequestFactory`. Never attach an interceptor forwarding users' Bearer tokens onto this infrastructure HTTP client.

### 7.2. Default builder

In Spring Security 6.5+ you can use:

~~~java
OpaqueTokenIntrospector remote =
    SpringOpaqueTokenIntrospector
        .withIntrospectionUri(
            "https://id.example.test/oauth2/introspect")
        .clientId("orders-api-introspector")
        .clientSecret(secretFromSecretManager)
        .build();
~~~

`secretFromSecretManager` is a system-provided variable, not a hardcoded value. When using this builder without customizing the client, HTTP behavior follows the library version.

Some newer Spring Security versions also offer `RestClientOpaqueTokenIntrospector` backed by `RestClient` (e.g., API since 7.1). Do not use newer classes in a Spring 6.x project where the dependency lacks them. For **WebFlux**, use the corresponding reactive introspector and HTTP client.

## 8. Revocation visibility: uncached vs. cached

### 8.1. Uncached: re-queried on the next request

Suppose:

~~~text
t0: API introspects token T -> active=true
t1: admin revokes T
t2: AS records and propagates revocation
t3: new request with T hits API
t4: API introspects T -> active=false
t5: request is rejected
~~~

If the AS updated state by `t2` and the Resource Server queries again at `t4`, the token is rejected. Still:

- Requests already authorized before revocation may still finish.
- The AS may have replication lag.
- Some user/grant disablements do not automatically mark every token inactive immediately.
- Gateways or the AS itself may hold internal caches.
- Introspection might land on an AS node that has not yet received the revocation event.

Thus "opaque tokens revoke instantaneously" is not an absolute guarantee of the token format itself.

### 8.2. Caching introduces a stale `active` window

If the API caches `active:true`:

~~~text
t0: introspection active=true -> cache entry C
t1: token is revoked
t2: new request -> cache hit C -> may still be accepted
t3: C expires -> new introspection call
t4: AS knows revocation -> active=false
~~~

Positive caching cuts AS call volume yet **extends the revocation exposure window**.

Approximate model:

~~~text
Exposure window ≈
    AS propagation delay
  + RS positive-cache staleness
  + other caches along the path
  + requests/transactions already authorized prior to revocation
~~~

This is a risk analysis, not a hard bound if the AS does not guarantee consistency/latency. A 10-second TTL at the RS does not by itself guarantee end-to-end revoke-to-deny within 10 seconds.

### 8.3. Token revocation differs from permission changes

The AS may return `active:true` even though a user's scopes or roles changed:

- If the AS keeps a snapshot of permissions from issuance time, introspection can still return old permissions until `exp`.
- If the AS computes dynamic entitlements during introspection, results can reflect recent changes.
- If the Resource Server caches the principal, scopes/attributes can also go stale.

**`active:true` does not prove a user currently holds permission on every record.** The API may still need to verify tenant, owner, local ACLs, or entitlements from its own authoritative data source.

## 9. Comparing strategies

| Strategy | Latency | During AS outage | Revocation freshness |
|---|---|---|---|
| Uncached opaque introspection | Usually a remote call per request | Directly dependent on AS | Best reflection of AS state at query time |
| Opaque + short positive cache | Many requests hit cache | Unexpired entries usable per policy | Delayed by TTL and propagation |
| Opaque + long positive cache | Lower latency/load on cache hits | Survives longer on cache | Stale window can be large |
| Opaque + reliable event invalidation | Fast and low load | Depends on AS + event infrastructure | Good if delivery/reconciliation is solid |
| Offline JWT verification | Usually local crypto only once JWKS loaded | Continues using cached keys | Unaware of revocations before `exp` |
| JWT format verified via introspection | Same as opaque introspection | Depends on AS | Follows introspection policy |

**Opaque is not always better than JWT, nor vice versa.** Choose based on latency budgets, dependency availability, revocation needs, token profile, and operational complexity.

## 10. Caching introspection results: mandatory decisions

### 10.1. What to cache?

A positive cache can store:

- Principal and attributes from introspection.
- Authorities mapped from `scope`.
- Timestamp of the active decision.
- Cache entry expiration timestamp.

Never store raw tokens in logs, metrics, or Redis keys. An opaque token is a **bearer credential**; anyone obtaining it can attempt to use it.

### 10.2. Use a cache key that does not expose the token

One option:

~~~text
cache_key = HMAC-SHA256(server_secret, access_token)
~~~

The HMAC key must be sufficiently random, stored in a secret manager, and access-controlled. HMAC merely identifies the cache entry without exposing the raw token; **it does not validate the token**.

When sharing a cache across replicas, design namespacing, HMAC key rotation, cache access controls, and limits on cached contents. A public-key JWKS cache is very different from an introspection token-status cache.

### 10.3. TTL must be bounded by `exp` if present

If the AS returns `exp`, positive cache lifetime must not exceed token expiration:

~~~text
valid_until = min(
    introspection_time + positive_cache_ttl,
    token_expiration_time
)
~~~

`exp` is an optional claim in RFC 7662. If the provider omits `exp`, a conservative policy is **not to positive-cache** or to cache only within a token lifetime guaranteed by a trusted contract.

A 15-second cache never gives a token 15 extra seconds past `exp`. Even before expiration, the token may have been revoked while cached.

### 10.4. Negative caching

Very short `active:false` caching can reduce load when clients repeatedly resend the same bad token. Still consider:

- Token-spray attacks with countless unique strings can cause high cache key cardinality.
- A stale AS node might produce an unexpected negative result.
- Network failures **must never** be turned into `active:false` and cached as a revocation decision.
- Cache size, TTL, and invalidation must be bounded.

Negative caching is not always necessary; rate limiting and bounded outbound calls may be cleaner solutions.

## 11. Example short-TTL positive cache decorator

Spring Security provides the `OpaqueTokenIntrospector` extension point. You can wrap a remote introspector with a decorator implementing application-specific caching policy.

The example below caches only positive results with a readable `exp` claim, using an HMAC token key and a maximum 10-second TTL. It never caches exceptions or inactive tokens.

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

~~~java
package com.example.orders.security;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class ShortTtlCachedIntrospector
        implements OpaqueTokenIntrospector {

    private static final Duration TTL = Duration.ofSeconds(10);

    private final OpaqueTokenIntrospector delegate;
    private final SecretKeySpec cacheKeySecret;
    private final Cache<String, Entry> cache =
        Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(TTL)
            .build();

    public ShortTtlCachedIntrospector(
            OpaqueTokenIntrospector delegate,
            byte[] hmacSecret) {

        if (hmacSecret.length < 32) {
            throw new IllegalArgumentException(
                "Cache HMAC secret must contain at least 32 bytes");
        }

        this.delegate = delegate;
        this.cacheKeySecret =
            new SecretKeySpec(hmacSecret.clone(), "HmacSHA256");
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        Instant now = Instant.now();
        String key = keyedHash(token);
        Entry cached = cache.getIfPresent(key);

        if (cached != null) {
            if (now.isBefore(cached.validUntil())) {
                return cached.principal();
            }
            cache.invalidate(key);
        }

        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token); // remote call / active check

        Instant exp = expiration(principal);

        if (exp != null && !exp.isAfter(now)) {
            throw new BadOpaqueTokenException("Token expired");
        }

        // Do not cache when AS omits exp or exp has an unexpected type.
        if (exp == null) {
            return principal;
        }

        Instant until = now.plus(TTL);
        if (exp.isBefore(until)) {
            until = exp;
        }

        if (until.isAfter(now)) {
            cache.put(key, new Entry(principal, until));
        }

        return principal;
    }

    private static Instant expiration(
            OAuth2AuthenticatedPrincipal principal) {
        Object raw = principal.getAttribute("exp");

        if (raw instanceof Instant instant) {
            return instant;
        }
        if (raw instanceof Number seconds) {
            return Instant.ofEpochSecond(seconds.longValue());
        }
        return null;
    }

    private String keyedHash(String token) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(cacheKeySecret);

            byte[] hashed =
                mac.doFinal(token.getBytes(StandardCharsets.UTF_8));

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(hashed);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "Cannot build cache lookup key", ex);
        }
    }

    private record Entry(
        OAuth2AuthenticatedPrincipal principal,
        Instant validUntil
    ) {}
}
~~~

This is an **illustrative example**, not a complete production caching library. In production deployments, also add:

- Clock skew handling and expiration policy matching.
- Defensive copies if attributes/principals are mutable.
- Protection for the cache and HMAC secret.
- Coalescing concurrent cache misses for the same token.
- Hit/miss/stale observability.
- Invalidation rules when roles/policies change.
- Revoke-to-deny tests and cache-secret key rotation.
- Evaluation of positive caching per endpoint sensitivity level.

This code uses **per-process local Caffeine**. Separate replicas hold separate caches, so the same token may be introspected at different times across instances.

### 11.1. Wiring the decorator into Spring Security

~~~java
package com.example.orders.security;

import java.util.Base64;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
public class CachedIntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector introspector(
            @Value("${app.security.introspection.uri}") String uri,
            @Value("${app.security.introspection.client-id}") String id,
            @Value("${app.security.introspection.client-secret}") String secret,
            @Value("${app.security.cache-key-base64}") String keyBase64) {

        OpaqueTokenIntrospector remote =
            SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(id)
                .clientSecret(secret)
                .build();

        return new ShortTtlCachedIntrospector(
            remote,
            Base64.getDecoder().decode(keyBase64));
    }
}
~~~

YAML:

~~~yaml
app:
  security:
    introspection:
      uri: https://id.example.test/oauth2/introspect
      client-id: orders-api-introspector
      client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
    cache-key-base64: ${INTROSPECTION_CACHE_HMAC_KEY_BASE64}
~~~

`INTROSPECTION_CACHE_HMAC_KEY_BASE64` must be Base64 of a sufficiently long, protected random secret. This is an **alternative configuration** to the dedicated timeout introspector bean above; never register two competing `OpaqueTokenIntrospector` beans without explicit wiring.

If you need **both custom HTTP timeouts and caching**, pass the `RestOperations`-configured remote `SpringOpaqueTokenIntrospector` from section 7 as the delegate to `ShortTtlCachedIntrospector`.

**Note:** when providing your own `OpaqueTokenIntrospector` bean, Spring Boot normally defers to that bean; the application is then responsible for ensuring client authentication, timeouts, caching, and contracted validations.

## 12. Why can caching a principal also preserve stale permissions?

When introspection returns:

~~~json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-42"
}
~~~

the Resource Server maps it into a principal and authorities. If an admin removes `orders.write` at the AS while the token stays active, an old cache entry can keep holding `SCOPE_orders.write`.

Even without caching at the RS, the AS itself may keep a snapshot of the token's scopes until `exp`. Therefore distinguish:

- **Token revocation:** AS marks the token inactive.
- **Claim/entitlement updates:** does the AS reflect changes immediately during introspection?
- **Local authorization:** must the API check current data permissions directly?

For sensitive operations, never let a positively cached principal replace owner/tenant/ACL checks in the database.

## 13. Should you cache across every endpoint?

Not necessarily.

### 13.1. Low-sensitivity, read-heavy endpoints

For `GET /api/catalog` with scope `catalog.read`, an organization might allow a very short-TTL introspection cache to reduce latency and AS load, **provided** the corresponding revocation window is explicitly accepted.

### 13.2. Approval or financial endpoints

For:

~~~http
POST /api/orders/42/approve
Authorization: Bearer <ACCESS_TOKEN>
~~~

you may require:

- No positive cache, or always performing an online active check.
- Checking the latest local entitlements.
- Verifying approval/owner/tenant status right inside the transaction.
- Step-up authentication or short token lifetimes if policy demands.
- Failing closed whenever status cannot be verified.

A globally enabled caching introspector affects every endpoint in that chain. If splitting filter chains by sensitivity, configure `securityMatcher`/`@Order` carefully: Spring Security picks **the first matching chain**. Avoid letting a broad caching chain catch all endpoints ahead of a specialized chain.

## 14. Audience, scope, and business permissions after introspection

`active:true` is insufficient if the API also requires tokens minted specifically for itself. The AS might return:

~~~json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "payments.read"
}
~~~

The Orders API must check audience per contract instead of trusting every active token. Because `aud` is not mandatory in every introspection response, agree on the profile with the Authorization Server; never assume providers always return `aud`.

### 14.1. Wrapping the introspector to check audience

~~~java
package com.example.orders.security;

import java.util.Collection;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public AudienceCheckingIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object aud = principal.getAttribute("aud");

        boolean valid =
            "orders-api".equals(aud)
            || (aud instanceof Collection<?> values
                && values.contains("orders-api"));

        if (!valid) {
            throw new BadOpaqueTokenException(
                "Access token not intended for Orders API");
        }

        return principal;
    }
}
~~~

This is a **specific contract** requiring `aud` in the introspection response; tokens lacking `aud` are rejected. If the issuer does not provide `aud`, design another AS-guaranteed resource binding rather than dropping the policy in a multi-API environment.

When combining with caching, order layers as:

~~~text
Remote introspection
   -> validate required token attributes/audience
   -> optional positive cache with approved TTL
   -> OpaqueTokenAuthenticationProvider
~~~

Never cache a principal that has not passed contract validation. When business policies change, consider invalidating caches holding old decisions.

### 14.2. Scope does not replace tenant permissions

If a token is active and holds `SCOPE_orders.read` yet order 42 belongs to another tenant, the API must still deny access. A reference policy:

~~~text
ALLOW_READ_ORDER =
    token active
    AND intended for Orders API
    AND SCOPE_orders.read
    AND local entitlement allows READ
    AND order belongs to allowed tenant/owner
~~~

Method security/services enforce these conditions; never use a client-sent `X-Tenant` header or query parameter to grant access.

## 15. Availability when caching is enabled

During an AS outage:

~~~text
Token A: cache hit and within TTL -> may proceed per policy
Token B: cache miss -> cannot introspect -> fail closed
~~~

This difference is a consequence of caching, **not** proof that the Resource Server can verify all tokens while the AS is offline.

In particular, avoid:

- **Unbounded stale-if-error:** using expired positive results when the AS is down.
- **Unbounded stale-while-revalidate:** continuing to accept revoked tokens during retries.
- **Default fail-open:** treating HTTP client timeouts as `active:true`.
- **Turning network exceptions into `active:false` and negative-caching them:** equating infrastructure faults with invalid tokens.

If a specialized use case truly requires a stale fallback, document a threat model, hard time bounds, revocation detection, and tests proving no out-of-contract access is granted.

## 16. Beware token-spray and request amplification

An attacker does not need a valid access token to trigger many introspection calls. Every random string in a Bearer header can trigger an HTTP POST to the AS.

Countermeasures:

1. Edge/API rate limiting.
2. Bounded connect/read timeouts.
3. Outbound concurrency limits to avoid exhausting pools/threads.
4. Retry budgets, never retrying `active:false`.
5. Bounded cache sizes for both positive and negative entries.
6. Alerts on spikes in unique token attempts.
7. Coordinating AS rate limits and capacity.
8. Never logging raw tokens in gateways or HTTP clients.

Never build cache keys from full tokens inside logging/metrics systems or put `Authorization` values into high-cardinality tags.

## 17. Metrics and tracing to monitor

| Observation | Meaning |
|---|---|
| Introspection requests/sec | AS load generated by Resource Servers |
| Introspection latency p50/p95/p99 | Authentication tail latency |
| Connect/read timeouts | Network/AS missing SLOs |
| Introspection HTTP 401/403 | Potential client auth/config error |
| Introspection HTTP 429/5xx | Rate limiting or AS outage |
| `active:false` count | Inactive tokens detected |
| Positive-cache hit/miss | Reduction in remote calls |
| Cache age/TTL | Staleness window accepted by the API |
| Concurrent outbound calls | Risk of resource exhaustion |
| End-to-end API p95/p99 | Actual impact on clients |
| Revoke-to-deny latency | Delay from revocation until requests are rejected |
| Policy-based 401/403 | Distinguishing invalid tokens from missing scopes |

These are **metrics worth instrumenting**, not guaranteed built-in metric names in Spring Security. You can add a dedicated tracing span around the introspection POST, provided you redact request bodies containing tokens and Authorization headers containing client secrets.

### 17.1. Tracing the request path

~~~text
HTTP GET /api/orders
  -> BearerTokenAuthenticationFilter
     -> OpaqueTokenIntrospector
        -> POST /oauth2/introspect
  -> AuthorizationFilter
  -> OrdersController
  -> Database
~~~

When latency spikes, traces reveal whether time is spent at the AS or in business logic. Never enable full HTTP wire logging in production where it could capture tokens or secrets.

## 18. Test matrix

| Test case | What to verify |
|---|---|
| Active token, right scope | Authentication succeeds and authorization permits |
| `active:false` | Resource Server rejects token |
| Missing token | Protected endpoint returns appropriate challenge |
| Active token missing scope | Typically 403 |
| Active token with wrong audience | Rejected per contract |
| Connect timeout | Does not fail open |
| Read timeout | Does not fail open; distinct metric emitted |
| AS returns 401 due to bad client secret | Infrastructure/config error detected |
| AS returns 429 | No infinite retries |
| AS returns 500 | Unverified token not accepted |
| Cache hit before revocation | Observe how long cache continues permitting |
| Cache TTL expires after revocation | Queries AS and rejects on `active:false` |
| Cached entry whose `exp` passed | Entry not used even if cache TTL remains |
| Introspection omits `exp` | Not positive-cached if policy requires `exp` |
| AS updates scope | Cached principal does not outlive agreed window |
| Multiple replicas | Each local cache may reflect different state |
| Token-spray with many random values | Cache/RPS/memory remain bounded |
| User tenant/ACL changes | Service still denies unauthorized access |
| Request authorized just before revocation | In-flight behavior matches policy |

When writing integration tests, use a **mock introspection HTTP server** in the test environment to return `active:true` then `active:false`, or induce timeouts and HTTP 500s. Test through the real Spring Security filter chain rather than merely invoking controllers with a mocked principal.

### 18.1. Do not confuse authority tests with introspection tests

A `MockMvc` test injecting an `Authentication` can prove `hasAuthority` rules, yet **does not prove HTTP introspection was called, timeouts work, or cache TTL reflects revocation**.

Separate:

- Unit tests for cache decorators and audience validation.
- HTTP client tests against a mocked introspection endpoint.
- Integration tests through `BearerTokenAuthenticationFilter`.
- Load/chaos tests for AS outages and tail latency.
- Revoke-to-deny tests aligned with organizational SLOs.

## 19. Revoke-to-deny exercise

Suppose:

~~~text
Opaque introspection enabled
Positive cache TTL = 15 seconds
AS propagation delay = nonzero
Token exp = 20 minutes remaining
API endpoint = GET /api/orders/42
~~~

Hypothetical timeline:

~~~text
10:00:00  API introspects T -> active=true, writes cache
10:00:03  Admin revokes T
10:00:04  Request with T hits API -> may hit cache
10:00:15  Cache entry TTL expires
10:00:16  API introspects T again
~~~

If the AS has processed the revocation by `10:00:16`, the request is rejected. If the AS still returns `active: true` due to replication lag, a fresh cache entry can delay revoke-to-deny further.

Hence **a 15-second TTL does not guarantee the entire system reflects revocation within 15 seconds**. Determine:

1. When does the AS record the revocation?
2. Which introspection node serves the request and with what consistency?
3. Are there other caches in the gateway/AS?
4. Where does the Resource Server use local/shared caches?
5. Is there event-driven invalidation, and what happens if events are dropped?
6. Are in-flight requests allowed to finish?
7. Does the business operation verify current entitlements before committing?

Revocation freshness is an **end-to-end property**, not just a single TTL at the Resource Server.

## 20. Incident diagnostic runbook

### 20.1. Slow API while the database is healthy

Check:

- p95/p99 latency of POST introspection.
- Cache hit/miss ratios and outbound call counts.
- Connect/read timeouts and connection pools.
- DNS/TLS/proxies/service mesh.
- AS token store latency and rate limits.
- Retry amplification and concurrent replica load on AS.
- Correlation between peak RPS and introspection errors.

Never increase timeouts unboundedly. API SLOs and overall deadlines must fit within the authentication budget.

### 20.2. Spikes in 401s after secret rotation

Separate `active:false` from Resource Server credential errors. Inspect client ID/secret, authentication method, TLS, and introspection permissions. Never force users to sign in again if the AS is actually rejecting **the API's own client authentication**.

### 20.3. Revoked tokens still succeed

Check:

- Did the AS actually revoke the active access token `T` being presented?
- Does AS introspection reflect the revocation yet?
- Does the API hold an unexpired `active:true` cache entry?
- Are there other gateway/AS caches?
- Was the request already in flight before revocation?
- Is any security chain verifying JWTs offline or bypassing opaque introspection?
- Is any service method skipping authorization?

If the contract requires rapid revocation, never extend cache TTLs or turn on stale-while-revalidate to mask issues.

### 20.4. AS returns `active: true` yet API returns 403

This can be completely expected: the token is valid yet lacks `SCOPE_orders.read`, or local entitlement/owner/tenant policy denied it. Inspect scope mapping and authorization rather than adding scopes to the principal when the AS did not grant them.

## 21. Misconceptions to avoid

### "Opaque tokens are always revoked instantaneously"

No. The AS must update and return the new state; the RS must re-query; replication and caches can add delay.

### "Introspection 200 means the token is valid"

No. HTTP 200 with `{"active":false}` is a completely valid response.

### "AS introspection returning 401 means the user's token is definitely bad"

No. The Resource Server's own credentials for calling the AS may be invalid.

### "Positive caching keeps latency low and still guarantees instant revocation"

Not without an explicit invalidation/consistency mechanism under a clear contract. Longer caches increase staleness risk.

### "If the AS is down, old tokens can be accepted indefinitely"

That is fail-open. Only entries within approved policy bounds may be used; once expired, a fresh trusted decision is required.

### "Opaque tokens don't need scope/audience checks"

`active:true` does not grant access to every API or resource. Check contracted audience, scopes, and tenant/ownership.

### "JWT is always more efficient than opaque"

Offline JWTs reduce network dependency yet do not detect early revocations on their own. Opaque introspection solves different needs at the cost of network calls.

### "The JWKS cache is shared with opaque introspection"

No. A JWKS cache holds JWS public signing keys; an opaque cache holds introspected `active`/principal decisions.

### "No rate limiting is needed because bad tokens are rejected"

False. Bad tokens still trigger remote introspection and load the AS.

## 22. Strategy selection matrix

| Primary requirement | Recommended approach |
|---|---|
| Freshest revocation state per AS is top priority | Per-request introspection, no positive cache |
| High RPS with a small acceptable stale window | Short-TTL positive cache, capped by `exp` |
| Greater resilience to AS faults | Improve AS availability, tune HTTP timeouts/bulkheads, fail closed |
| Lower load while keeping very fast revocation | Evaluate push invalidation + reconciliation |
| Highly sensitive operations | Online active check and local entitlement/transaction policy |
| Mostly offline authentication needed | JWT signature validation plus supplementary revocation strategy if needed |
| Token has JWT format yet AS requires introspection | Use opaque mode if supported by AS |
| Multiple Resource Servers / replicas | Design local/shared caching and AS capacity |
| AS omits audience | Agree on an alternative resource-specific contract/validation |
| High token-spray volume | Rate limiting, bounded caches, and outbound concurrency limits |
| Need revoke-to-deny auditing | Measure end-to-end AS-to-RS timing, not TTL alone |

## 23. Key takeaways

- **Opaque token introspection** delegates the active/inactive decision to the Authorization Server. It can reflect revocations better than offline JWT verification when re-queried and when the AS updates state properly.
- **Every remote introspection call** adds latency and an availability dependency. Monitor p95/p99, RPS, timeouts, and rate limits.
- **No caching** provides the freshest AS state at the cost of depending directly on the endpoint on every authenticated request.
- **Positive caching** cuts load and latency while creating a **revocation window**. Bound TTL, `exp`, and size, and define invalidation clearly.
- **Never fail open** when the AS is lost. Clearly separate inactive tokens from HTTP client timeouts/5xx or bad introspection credentials.
- `active:true` does not replace **audience, scope, entitlements, and tenant/owner/ACL checks**.
- Spring Security Servlet supports customization via **`OpaqueTokenIntrospector`**, custom HTTP clients, and cache decorators; preserve the trust contract throughout.
- Revocation freshness depends on **the AS, caches, propagation, request timing, and business authorization**, not just a single TTL value.

### References

- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security API — `OpaqueTokenIntrospector`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security API — `SpringOpaqueTokenIntrospector`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html)
- [Spring Security API — `RestClientOpaqueTokenIntrospector`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/RestClientOpaqueTokenIntrospector.html)
- [Spring Security Reference — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
