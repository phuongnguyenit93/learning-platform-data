# Concurrent Node Startups and Discovery/JWKS Load Spikes

A Spring Security OAuth 2.0 Resource Server cluster can run smoothly under normal conditions yet suffer outages during a new release rollout, scale-out, or recovery from a power/infrastructure outage. The cause is often not an individual API request: **many instances boot simultaneously and hit the Authorization Server together to fetch discovery metadata or signing keys**.

This phenomenon is commonly called a *thundering herd* or *cache stampede*. A rollout creates dozens or hundreds of new JVMs. Each instance maintains its own cache, so metadata or JWKS are absent from memory. If all instances run discovery, fetch JWKS, or refresh keys within a short window, the Authorization Server can become overloaded right when the system needs to recover.

This lesson explains the discovery/JWKS lifecycle, how to detect load surges, how to structure caching and refreshes, how to reduce pressure during startups/scale-outs, how to handle key rotation and dependency failures, and what to verify in your specific Spring Security version.

The operational goal is ensuring **instance growth does not turn into an uncontrolled burst of concurrent requests to the issuer**, while the Resource Server still verifies valid tokens properly and rejects unverifiable tokens.

## 1. Why Can Starting Many Instances Overload the Issuer?

Suppose the Orders API runs 40 pods. A rollout replaces all pods within a few minutes. Each pod builds a decoder from an issuer URI and needs metadata to locate the JWKS endpoint. Then, as the first Bearer requests arrive, decoders may need to fetch signing keys.

Depending on the Spring Security version, decoder configuration, and how beans are initialized, discovery may happen at startup or be deferred until token processing. JWKS is also typically fetched when the decoder needs a key and the cache lacks a matching entry. Therefore, measure your application's exact behavior rather than assuming every request triggers discovery or every startup fetches JWKS identically.

A typical scenario:

~~~text
Deployment controller
       |
       +-- spawns many new pods concurrently
               |
               +-- Pod 1: discovery / JWKS fetch
               +-- Pod 2: discovery / JWKS fetch
               +-- Pod 3: discovery / JWKS fetch
               +-- ...
               +-- Pod 40: discovery / JWKS fetch
                         |
                         v
              Authorization Server / proxy
                         |
                         v
              metadata/JWKS request spike
                         |
                         v
              latency, 429, 5xx, or timeout
                         |
                         v
              decoder fails to retrieve key
                         |
                         v
              valid tokens rejected / pods not ready
~~~

Common triggers for a surge:

- **Cold start:** new JVMs lack metadata/JWKS caches.
- **Scale-out:** an autoscaler creates many replicas in a short time.
- **Rolling deployment:** many new replicas are created per `maxSurge` or rollout policy.
- **Node recovery:** nodes/pods are lost simultaneously after an infrastructure incident.
- **Cache expiry:** many cache entries were populated around the same time and expire together.
- **Key rotation:** new tokens with a new `kid` cause many decoders to refresh JWKS simultaneously.
- **Unknown `kid`:** tokens with an unrecognized `kid` trigger refreshes; large volumes of unknown-`kid` tokens can create a refresh storm if unbounded.
- **Issuer outage recovery:** after the issuer comes back up, many instances retry in lockstep.
- **Poorly designed health checks:** probes or warm-up requests repeatedly trigger discovery/JWKS fetches.

## 2. Distinguishing Discovery Traffic from JWKS Traffic

These two request groups are often lumped together as "OAuth server calls", yet their lifecycles and caches differ.

| Request | Purpose | When It Can Occur | Returned Data |
| --- | --- | --- | --- |
| OIDC Provider Discovery | Locate OpenID Provider metadata | Decoder/registration needs discovery; startup or lazy init per config | issuer, jwks_uri, endpoints, and capability metadata |
| OAuth Authorization Server Metadata | Locate OAuth AS metadata per RFC 8414 | When OAuth issuer metadata is needed | issuer, jwks_uri, token/introspection/revocation endpoints if published |
| JWKS fetch | Retrieve public keys to verify JWTs | Cache miss, missing matching kid, or refresh per implementation | JSON Web Key Set |
| JWKS refresh | Update cached key set | TTL expiry, unknown kid, or refresh policy | Updated JWKS |
| Token introspection | Query opaque token or issuer-backed token status | Per introspection/cache miss | active flag and token metadata |

**Discovery is not JWKS.** Discovery returns metadata, which can include `jwks_uri`. The JWKS endpoint is what returns public keys. A deployment can generate heavy discovery traffic without fetching JWKS yet, or have discovery cached while JWKS refreshes due to key rotation.

Therefore, metrics and access logs must distinguish:
- Requests to the well-known metadata endpoint.
- Requests to the JWKS URI.
- Requests to the introspection endpoint.
- Requests to token/revocation endpoints if the same issuer serves multiple roles.

Do not lump all endpoints into one generic counter if you want to pinpoint the root cause of a cache stampede.

## 3. What Scope Does a Resource Server's Cache Have?

Typically, the metadata/JWKS cache is managed in-process by the decoder or HTTP/JWK client. With 30 pods, 30 independent caches may exist.

~~~text
                 Authorization Server
                   /metadata
                   /jwks
                        ^
                        |
       +----------------+----------------+
       |                |                |
   Pod A cache      Pod B cache      Pod C cache
   metadata        metadata         metadata
   JWKS            JWKS             JWKS
       |                |                |
   JwtDecoder       JwtDecoder        JwtDecoder
~~~

Consequences:

- A warm cache on Pod A does not mean Pod B is warm.
- JVM restarts wipe in-memory caches.
- Scale-out creates cold caches.
- Each replica can refresh on a different schedule.
- A shared HTTP proxy/cache can cut issuer requests, but must properly implement HTTP semantics, cache headers, and key rotation.
- Token status/introspection caching is distinct from metadata caching and JWKS caching.

Never assume JWKS caches are shared across instances simply because they run the same application. Verify the actual JWK source/cache implementation and configuration.

### Cache Layers to Distinguish

| Cache | Key/data | Risk When Expired or Stale |
| --- | --- | --- |
| Discovery metadata | Issuer -> metadata document | Stale endpoints, jwks_uri, or capabilities |
| JWKS | jwks_uri -> public key set | New key missing; retired key still trusted per cache |
| Negative lookup | Missing kid | May delay recognizing a new key if TTL is too long |
| DNS/connection pool | Hostname and HTTP connections | Endpoint IP changed or stale connections fail |
| Introspection result | Token/status/claims | Revoked tokens still accepted until entry TTL expires |
| Application config | issuer-uri, jwk-set-uri, audience | Wrong issuer/endpoint or config drift |

A JWKS cache is not a token revocation cache. Nor does an introspection cache replace a JWKS cache.

## 4. Why Does Synchronized Cache Expiry Cause Stampedes?

Suppose all 40 pods boot within the same minute. Each pod fetches JWKS around the same time and caches the response with an identical TTL. If the TTL expires after a fixed duration, caches across pods expire together. The first request arriving at each pod afterward triggers a refresh.

~~~text
Time            Pod A        Pod B        Pod C        Pod N
-------------------------------------------------------------
t0              fetch        fetch        fetch        fetch
t0 + TTL        expired      expired      expired      expired
t1              refresh      refresh      refresh      refresh
t1 + ...        retry        retry        retry        retry
~~~

A single refresh suffices for one pod to keep verifying tokens, yet if every pod refreshes together, the issuer still receives a massive burst.

Factors that raise the probability:
- Synchronized startup via the deployment controller.
- Fixed cache TTLs without jitter.
- Lack of single-flight/coalescing for concurrent requests on the same cache key.
- HTTP clients permitting excessive concurrent requests.
- Immediate retries on failure.
- Unknown `kid`s across many distinct requests.
- Health checks invoking the decoder or an endpoint with cache side effects.
- Missing rate limits at the proxy or issuer layer.

## 5. Measure Load Before Changing Configuration

Before tuning, determine which request type is spiking and whether it correlates with rollout or scale events.

Monitor at a minimum:

| Metric | Meaning |
| --- | --- |
| Discovery requests/minute | Metadata discovery request count |
| JWKS requests/minute | JWKS fetch/refresh count |
| Introspection requests/minute | Introspection call count if using opaque tokens |
| JWKS fetch latency | Latency to fetch signing keys |
| Discovery latency | Latency to fetch metadata |
| Fetch success/error rate | Rates of HTTP success, timeout, 429, 5xx |
| Cache hit/miss | Cache effectiveness if observable by implementation |
| Unknown kid count | Tokens referencing keys absent from cache |
| Decoder authentication failures | Failed JWT verification count |
| Startup/readiness duration | Time for a pod to become ready |
| Concurrent outbound requests | Simultaneous connections/requests to the issuer |
| Retry count | Retries triggered by dependency failures |

Split labels by issuer or endpoint class, while avoiding high-cardinality labels like raw `kid`, token, subject, tenant ID, or client-controlled full URLs. If investigating `kid`s, use rate-limited logs rather than turning `kid` into an unbounded metric label.

### Correlate with Deployment Events

Overlay these signals on the same timeline:
- Deployment start/finish.
- Replica count and pod creation rate.
- Discovery/JWKS request rates.
- Issuer CPU, connection count, 429/5xx.
- Pod readiness and authentication error rates.
- Key rotation events.
- Cache expiry/refresh events if observable.

If request spikes coincide with new pod creation, cold-start traffic is the likely cause. If spikes recur periodically without rollouts, inspect TTLs and refresh schedules.

## 6. Reduce Concurrent Instance Startups

The first lever is usually rollout and autoscaling behavior, not changing validators.

### Bounded Rolling Deployments

Do not launch all new replicas at once. Tune:
- Deployment `maxSurge` and `maxUnavailable`.
- How many pods are replaced per batch.
- Pauses between batches if supported by the deployment platform.
- `PodDisruptionBudget` to avoid losing too many serving instances.
- Readiness gates so new instances receive traffic only after required dependencies are ready.

Conceptual Kubernetes example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 0
  template:
    spec:
      containers:
        - name: app
          image: example/orders-api:version
~~~

Calculate `maxSurge` from total replica count and issuer capacity. Never copy illustrative numbers into production without load testing.

### Batched Scale-Out

Autoscalers can add replicas rapidly when CPU or queue depth spikes. If each new replica starts with a cold cache, rapid autoscaling can hit the issuer with a secondary burst. Apply:
- Scale-up rate limits if supported by your platform.
- Adding replicas in small batches.
- Controlled readiness delays or warm-up.
- Tracking issuer capacity as a scale-out dependency.

Do not throttle scale-up so aggressively that the application fails to handle business traffic. Account for existing replicas' capacity while new pods warm up.

## 7. Jitter to Prevent Simultaneous Cache Expiration

Jitter adds a random offset to refresh timing or TTLs. Rather than every instance refreshing at the exact same instant, instances spread refreshes across a window.

Conceptual example:
- Base TTL: T.
- Jitter: a random value in [0, J].
- Refresh point: T - random(0, J), or cache lifetimes distributed around T per policy.

Do not force jitter arbitrarily if the cache implementation does not support controlling TTL. Jitter can be implemented in a cache wrapper, proxy cache, or library-supported refresh mechanism.

Jitter helps when:
- Many replicas start together.
- Cache TTLs are fixed.
- The issuer can handle the aggregate load but not sharp spikes.
- The key set does not require strictly synchronized refreshes across all instances.

Never let jitter push TTL past your freshness/security policy. Jitter only spreads refresh timing; it must never extend trust in a revoked key beyond acceptable bounds.

## 8. Single-Flight and Request Coalescing

Single-flight means many concurrent requests needing the same data trigger only **one fetch** within that mechanism's scope. Remaining requests wait for that shared result.

~~~text
100 requests hit a JWKS cache miss together
              |
              v
        Single-flight gate
              |
              +-- one HTTP GET JWKS
              |
              +-- other requests await the same result
              |
              v
         Update cache
              |
              v
        continue token verification
~~~

Scope matters greatly:

- In-JVM single-flight coalesces requests within a single instance only.
- It does not merge 50 pods into one request.
- A shared cache/proxy can coalesce at the cluster or edge layer.
- A distributed lock can cut duplicate fetches, but requires timeouts, fencing/leases, and owner-crash handling; do not introduce a distributed lock without proving the need.

Check whether your version's JWK source/HTTP client provides request coalescing. Never assume a decoder guarantees single-flight merely because it has a cache.

### Never Lock the Entire API Request Path

When one thread is refreshing JWKS, never hold a global lock that blocks all application requests indefinitely. Coalesce only fetches for the same resource/key set, with timeouts and bounded waits. Tokens using already-cached keys can continue verifying per policy during brief issuer errors.

## 9. Shared Proxy/Cache for Discovery and JWKS

An internal reverse proxy or caching layer can eliminate duplicate requests from multiple pods to the issuer:

~~~text
Pod A ----\
Pod B -----+----> Internal metadata/JWKS cache ----> Authorization Server
Pod C -----+
Pod N ----/
~~~

Benefits:
- Caches metadata/JWKS in one shared tier.
- Can coalesce concurrent fetches.
- Cuts connection count from applications to the issuer.
- Centralizes timeouts, rate limits, and observability.

However, the proxy cache becomes part of the trust boundary. Enforce:
- Cache only allowlisted issuers and URIs.
- Never let clients specify arbitrary JWKS URLs.
- Never skip TLS server validation when the proxy fetches JWKS.
- Honor cache headers and freshness policy.
- Never serve another issuer's key set via cache key collisions.
- Never turn a stale cache into acceptance of unverifiable tokens.
- Maintain an emergency purge/refresh procedure when a key is compromised.
- Bound response size and fetch duration.
- Never cache an introspection active response as if it were JWKS.

JWKS is typically public data, yet it remains security-critical because it dictates which signatures are trusted. Public does not mean infinitely cacheable or fetchable from unauthenticated sources.

## 10. Discovery Metadata: Caching and Static Configuration

### Using issuer-uri

Common Resource Server configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Spring Security can use the issuer to run metadata discovery and locate the JWKS URI. Exactly when discovery executes depends on version, decoder/bean creation, and lazy/deferred initialization. Verify via logs or HTTP stub tests on your exact dependency version.

Do not assume:
- Every startup calls discovery exactly once.
- Every API request calls discovery.
- JWKS is fetched immediately when metadata is read.
- Metadata cache and JWKS cache share the same TTL.
- All replicas share the same cache.

### Explicit jwk-set-uri Configuration

In supported versions, both `issuer-uri` and `jwk-set-uri` can be declared:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
          jwk-set-uri: https://auth.example.com/realms/shop/protocol/openid-connect/certs
~~~

Configuring the JWKS URI explicitly can reduce discovery dependence during decoder initialization while still keeping `issuer-uri` for issuer validation per your version and configuration's behavior. Verify this in your version's docs and real tests; never drop issuer validation just to avoid discovery.

Operational benefits:
- The Resource Server does not need to look up `jwks_uri` from metadata at runtime when the endpoint is statically configured.
- Discovery metadata can be checked separately in pipeline/deployment validation.
- Startup can depend less on a metadata endpoint, depending on how the decoder is initialized.

Limitations:
- JWKS still must be fetched/refreshed when keys are needed.
- Endpoint changes require configuration updates.
- Config drift across environments can lead to mismatched issuers/JWKS.
- Host allowlists and TLS validation must still be maintained.
- Issuer/time/audience validators must still be kept.

### Discovery in Pipelines and Deployments

You can validate metadata before rollout:
- Fetch metadata with a bounded job/monitor.
- Verify the issuer matches the expected value exactly.
- Verify `jwks_uri` uses HTTPS and belongs to an allowed host.
- Verify JWKS returns a valid schema and active keys.
- Record verification results/config versions for auditability.

Not every pod has to re-run discovery on its own if metadata is already validated and static endpoints are safely managed. Still, maintain a process to detect endpoint/key changes; never turn an old snapshot into a permanent source of truth.

## 11. JWKS Caching and Key Rotation

JWKS caching lowers issuer load, yet must coordinate cleanly with key rotation.

A safe rotation typically has these phases:

~~~text
1. JWKS publishes K1
2. Publish K2 alongside K1
3. Resource Servers refresh and receive K2
4. Authorization Server starts signing new tokens with K2
5. Old K1 tokens gradually expire
6. After overlap, remove K1 from JWKS
~~~

If the issuer switches to signing with K2 before Resource Servers have had a chance to fetch K2, the first requests carrying `kid=K2` can trigger a fleet-wide refresh spike. This is especially likely right after a rollout when pod caches are cold.

### Pre-Publishing New Keys

If your Authorization Server supports publishing keys before activating them:
1. Add K2 to JWKS while still signing with K1.
2. Give Resource Server caches time to fetch K2.
3. Confirm JWKS refreshes succeeded across the fleet or cache layer.
4. Switch the issuer to signing new tokens with K2.
5. Retain K1 long enough for existing tokens and cache policy.
6. Retire K1 on the published schedule.

Do not assume simply waiting a fixed interval guarantees every cache refreshed; confirm via cache/proxy metrics or a controlled refresh process.

### Unknown kid

When a JWT presents an unseen `kid`:
- Trigger a bounded refresh per policy.
- Coalesce concurrent refreshes for the same JWKS URI.
- Rate-limit refreshes triggered by unknown `kid`s.
- If the fetch succeeds without a matching key, reject the token.
- If the fetch fails and no trusted matching key is cached, the token cannot be verified.

Never try every key sequentially or verify with an arbitrary key. Never let each token with a random `kid` trigger an unbounded network request.

### Compromised Keys Differ from Normal Rotation

During a key compromise incident:
- Remove the key from the trust set per emergency procedures.
- Evaluate cache TTL and stale behavior.
- Invalidate caches or force refreshes per operational capabilities.
- Revoke affected tokens if supported by the issuer.
- Account for token lifetimes and offline Resource Servers.
- Never keep trusting an old key simply because caches still hold it if incident policy mandates immediate distrust.

A stale-if-error policy can improve availability during network glitches, but must never be used to keep trusting a known-compromised key.

## 12. Timeouts, Retries, and Exponential Backoff

Immediate retries when the issuer times out can worsen an overload. Enforce a clear retry budget.

A backoff strategy with jitter:

~~~text
delay(n) = random(0, min(maxDelay, baseDelay * 2^n))
~~~

Illustrative parameters:
- `baseDelay`: 200 ms.
- `maxDelay`: 5 s.
- Retry count: small cap aligned with startup/request budget.
- Total retry time: must not exceed the dependency timeout budget.

Actual numbers must align with the issuer SLA and API latency budget. Never use unbounded retries or stack retries across multiple layers (HTTP client, decoder wrapper, application filter) without summing total attempts.

### Retries by Error Category

| Error | Handling Approach |
| --- | --- |
| DNS/connect timeout | Bounded retries with backoff |
| HTTP 429 | Honor Retry-After if present; reduce concurrency |
| HTTP 5xx | Bounded retries with jitter |
| TLS certificate validation failure | Do not retry pointlessly; fix trust/hostname/certificate |
| HTTP 404 metadata/JWKS | Check endpoint/config; do not tight-loop |
| Invalid JWKS JSON response | Fail closed, alert; never treat an error response as a valid empty key set |
| Unknown kid after successful refresh | Reject token; apply negative lookup/rate limit |
| Introspection active=false | Token inactive; do not retry as a network error |
| Introspection client 401/403 | Investigate credentials/registration |

### Timeouts

Set or explicitly control:
- DNS/connect timeout.
- TLS handshake timeout.
- Response/read timeout.
- Connection pool acquisition timeout.
- Total refresh duration.
- Wait time for requests awaiting a key.

Overly long timeouts tie up request threads and connections; overly short timeouts fail refreshes under normal issuer latency. Measure from the application's runtime network, not only from a laptop.

## 13. Circuit Breakers and Stale Key Policy

A circuit breaker stops the application from sending continuous requests to a failing dependency. Apply it carefully around token verification.

A sensible policy:
- Tokens using cached keys still permitted by policy can continue verifying locally.
- Tokens requiring a new key while the circuit is open cannot be verified and must be rejected.
- Never accept keyless or unverified tokens just because the issuer is down.
- In half-open state, allow only a small number of probe calls.
- Prevent all pods from probing simultaneously; use jitter or a shared proxy.

Stale key policy must balance:
- Availability: using known cached keys during a brief issuer outage keeps current traffic flowing.
- Security freshness: revoked or compromised keys could remain trusted if cached too long.

Define explicitly:
- Cache max age.
- Stale-if-error window, if any.
- Emergency key removal/compromise path.
- How to force refresh/invalidation.
- Max token lifetime.
- Issuer outage policy.

No single TTL fits every system. Decide based on risk, rotation cadence, SLAs, and compromise-detection speed.

## 14. Startup, Readiness, and Liveness

Discovery/JWKS failures can impact pod lifecycle state. Distinguish three concepts:

- **Startup:** the process and application context have initialized.
- **Readiness:** the instance is eligible to serve traffic per policy.
- **Liveness:** whether the process is wedged/broken and requires a restart.

Never turn transient issuer errors into liveness failures, which causes the orchestrator to restart pods en masse and create another cold-start storm.

### When Discovery Is Required to Build the Decoder

If the application cannot build the decoder while the metadata endpoint is unavailable, startup may fail. In that case:
- Bound startup retries.
- Use backoff/jitter.
- Pace rollouts so too many pods do not retry together.
- Consider explicit `jwk-set-uri` configuration where appropriate while keeping issuer validation.
- Alert on dependency startup failures.

### When Startup Succeeds Before JWKS Is Fetched

The pod starts, yet the first requests needing a key will fail. Define a readiness policy:
- If the API requires JWT verification to serve traffic, do not mark ready until minimum verification capability exists.
- If public/health endpoints can serve without JWTs, use a finer readiness policy, while refusing protected requests until the decoder can verify.
- Never invoke discovery/JWKS on every health probe; warm-up must be bounded and idempotent.

### Liveness Should Not Depend Directly on the Issuer

If the issuer is temporarily down, restarting pods will not fix the dependency and can make things worse. Liveness should reflect process health. Readiness and monitoring can reflect token-verification capability per policy.

## 15. Controlled Warm-Up

Warm-up can load metadata/JWKS before a pod receives traffic. However, if all pods run warm-up at once, it merely shifts the thundering herd from the first request to the startup hook.

Safe warm-up:
- Runs once per instance or through a shared cache proxy.
- Has timeouts and a retry budget.
- Adds jitter across instances.
- Never uses production tokens or dummy tokens to force unrepresentative decoder paths.
- If testing the decoder with a canary token, issue it for the proper issuer/audience and never log it.
- Never fires repeated requests just to "keep the cache hot".
- Never lets readiness probes invoke warm-up repeatedly.

Warm-up can be implemented as a bounded application startup task or a pre-deployment job/monitor validating the issuer/JWKS. Choose based on whether the app must hold keys before its first protected request.

## 16. Concurrency Limits and Connection Pools

If the issuer enforces concurrent request limits, the decoder/JWK source HTTP client should align:
- Connection pool with bounded max connections.
- Bounded pending-acquire timeout.
- Fetch requests with deadlines.
- Retries staying within concurrency caps.
- Coalesced refreshes per JWKS URI where supported by the implementation.
- Never share one unbounded pool across all dependencies.

In WebFlux, take special care not to block the event loop when fetching JWKS or writing custom synchronous wrappers. Use a reactive client matching your stack and version API; never call `block()` on the event loop.

In Servlet stacks, also avoid letting hundreds of concurrent requests wait unboundedly on a single network refresh. Monitor request queues, pool saturation, and wait times.

## 17. Spring Security Configuration: Preserving Policy While Optimizing Load

### Configuring issuer-uri and jwk-set-uri

Example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
          jwk-set-uri: https://auth.example.com/realms/shop/protocol/openid-connect/certs
~~~

This is an illustrative configuration. Verify:
- Your Spring Boot/Security version supports these properties.
- Discovery behavior when both are declared.
- Issuer validator remains active.
- Your API's audience validator remains configured.
- Decoder/JWK source cache behavior in that version.
- Endpoint reachability from pods across TLS, DNS, and network policies.

Never drop the issuer validator or accept any audience just to shed load. Discovery traffic is an operational concern; issuer/audience validation is security policy.

### Custom Decoders and Validators

When customizing a decoder, keep required default validators and compose audience/profile validators:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(
            "https://auth.example.com/realms/shop/protocol/openid-connect/certs")
            .build();

    OAuth2TokenValidator<Jwt> issuerAndTimestamp =
        JwtValidators.createDefaultWithIssuer(
            "https://auth.example.com/realms/shop");

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("orders-api")) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Required audience is missing",
                null));
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTimestamp,
            audience));

    return decoder;
}
~~~

This is a Servlet decoder example. Match imports and APIs to your version. If using WebFlux, configure `ReactiveJwtDecoder` instead; never inject a synchronous decoder and block inside a reactive chain.

This snippet demonstrates that validators are independent of fetch tuning. Optimizing fetches must never lose issuer, timestamp, or audience checks.

### Version-Dependent Cache Customization

Spring Security can use Nimbus JOSE/JWT and a remote JWK source for JWKS. Support for passing a Spring `Cache`, customizing `JWKSource`, HTTP clients, cache TTLs, or refresh policies varies across releases and APIs. Before using:
- Inspect the builder API of your exact version.
- Confirm whether caching applies to metadata, JWK source, or both.
- Check whether the cache supports concurrent refresh/coalescing.
- Check TTLs and behavior when the endpoint returns 304/429/5xx.
- Confirm how unknown `kid`s and key removals are handled.
- Write integration tests proving the actual number of HTTP requests.

Never invent property names like `jwks-cache-ttl` if your Spring Boot/Security version does not publish such a property. If customizing `JWKSource`, wrap it clearly as a bean and test behavior; never assume an API name from a newer version exists in an older one.

## 18. Never Miscache or Mis-Share JWKS

Cache keys must distinguish issuer and JWKS URI. Never cache JWKS by hostname alone if the same host serves multiple realms or tenants.

Example:

~~~text
https://auth.example.com/realms/shop/protocol/openid-connect/certs
https://auth.example.com/realms/finance/protocol/openid-connect/certs
~~~

Both endpoints can serve completely different key sets despite sharing a hostname. A cache collision can cause the decoder to select the wrong key or fail verification.

Principles:
- Key caches by canonical URI/issuer context.
- Never let a token pick an arbitrary `jwks_uri` or `jku`.
- Permit only allowlisted issuer/JWKS endpoints.
- Never follow redirects to untrusted hosts.
- Verify TLS hostnames and certificate chains.
- Cap response size, key count, and parsing time.
- Never share stale caches between two issuers.
- Invalidate by issuer/key set.

## 19. Rate Limiting and Protecting the Issuer

At the issuer or internal proxy, you can enforce limits on:
- Discovery request rate per client/network.
- JWKS fetch rate per endpoint.
- Introspection request rate per client registration.
- Concurrent connections.
- Burst and sustained request rates.
- Retry-after behavior.

Do not apply the exact same limits to JWKS and introspection if their traffic profiles differ. JWKS can usually be cached longer; introspection often sees higher request volume because it tracks token state.

If 429 is returned, the Resource Server should honor `Retry-After` when present, lower concurrency, and avoid synchronized retry loops. Coordinate retry policies across every layer so total attempts do not multiply.

## 20. Estimating Load for a Rollout

A simple estimation model:

~~~text
R_discovery = N_new_instances * discovery_fetches_per_instance
R_jwks      = N_new_instances * jwks_fetches_per_instance
~~~

If 60 new instances each perform one metadata fetch and one JWKS fetch within the same minute, the issuer receives roughly 60 discovery requests and 60 JWKS requests that minute—before counting retries, health checks, unknown `kid`s, or other apps.

With 3 retries, request counts can multiply severalfold. If each pod initializes multiple decoders/issuers, multiply by actual cache keys.

With a coalescing proxy cache, requests from the proxy to the issuer drop closer to the proxy's cache miss rate, though the proxy itself must handle pod traffic and needs its own capacity.

A rollout planning table:

| Parameter | Example | Meaning |
| --- | ---: | --- |
| Total replicas | 60 | Fleet after rollout |
| Max surge | 3 | Max extra new pods per batch above desired count |
| Issuer discovery capacity | Per SLA | Metadata request threshold |
| Issuer JWKS capacity | Per SLA | Key set request threshold |
| Retry attempts | Small cap | Total re-attempts |
| Jitter window | Load-based | Spreads fetch timing |
| Cache TTL | Policy-based | Freshness vs. load |
| Warm-up concurrency | Bounded | Instances warming concurrently |

Values in this table illustrate how to plan. Use load tests and issuer SLAs to choose real numbers.

## 21. Testing Cold Starts and Cache Stampedes

Do not test only a single long-running instance. Verify behavior when multiple decoders start with cold caches.

### Testing Discovery

- Serve metadata from an HTTP stub server.
- Initialize multiple application contexts/decoders mimicking deployment.
- Trigger controlled concurrent startups.
- Count requests hitting the metadata endpoint.
- Verify request rates stay within budget.
- Test when the metadata endpoint times out or returns 429/5xx.

### Testing JWKS

- Start with an empty cache.
- Send concurrent tokens sharing the same `kid`.
- Observe `GET JWKS` request count.
- Confirm cache/coalescing behaves per implementation.
- Update JWKS to add a new key.
- Send a token with the new `kid` and measure refresh behavior.
- Send many nonexistent `kid`s to verify refresh rate limiting.
- Simulate timeouts and malformed schemas.

### Fleet Testing

Simulate:
- 10, 50, 100 instances starting together.
- Small-batch rollouts.
- Synchronized cache TTLs vs. jittered TTLs.
- Nominal and elevated issuer latency.
- Issuer returning 429/503.
- Issuer outage followed by recovery.
- Key rotation while some instances hold cold caches.
- Multiple instances receiving a new-`kid` token concurrently.

You do not need to spin up 100 JVMs on every build. Run small unit/integration tests routinely and dedicated load tests for release/infrastructure validation.

## 22. Failure Behavior Matrix

| Incident | Cached Key | New Key / Unknown kid | Required Policy Behavior |
| --- | --- | --- | --- |
| Discovery endpoint outage | Decoder already has metadata | Decoder lacks metadata | Startup/deferred initialization policy |
| JWKS endpoint timeout | Matching key present | No matching key | Cache policy; unknown key fails closed |
| JWKS returns 429 | Matching key present | No matching key | Backoff, Retry-After, readiness |
| JWKS returns 5xx | Matching key present | No matching key | Retry budget and stale-key policy |
| Invalid JWKS JSON | Old key may stay cached | Cannot fetch new key | Alert, fail closed for unknown keys |
| Prolonged issuer outage | Old key cached | New tokens use new key | SLA/cache freshness and incident runbook |
| Compromised key | Cache may hold old key | May refresh key set | Emergency invalidation, revocation, denylist if needed |
| Unknown kid storm | Cache holds other keys | Flood of unknown kids | Refresh coalescing, rate limit, negative cache |

An availability policy may permit using cached keys within a defined window during brief issuer errors. However, tokens lacking a trusted key must never be accepted. If a key is compromised, incident policy may require immediate distrust even while caches remain valid.

## 23. Readiness and Warm-Up Must Not Add Extra Load

Health checks typically run continuously from orchestrators or load balancers. If a readiness endpoint invokes the decoder or validates a token using a new key on every probe, it can generate unnecessary traffic.

Design:
- Liveness never calls the issuer.
- Readiness reads status updated by a bounded background check.
- The background check uses caching and single-flight rather than firing a fresh request per probe.
- Warm-up has timeouts/backoff and runs only per necessary lifecycle hooks.
- When the issuer fails, readiness reflects token-verification capability per security requirements.
- Never report healthy solely because the pod process is alive if the protected API cannot verify any required tokens.

Never turn a probe into a public endpoint that an attacker can abuse to force JWKS fetches on demand.

## 24. Safe Logging and Observability

Record safely:
- Configured issuer alias.
- Endpoint class: discovery, jwks, or introspection.
- HTTP status, latency, timeout category.
- Cache hit/miss/refresh if exposed by the implementation.
- Missing `kid`s via rate-limited logs.
- Pod identity, deployment revision.
- Decoder failure category.
- Rollout/incident correlation ID.

Never log:
- Access tokens.
- Refresh tokens.
- Client secrets.
- Private keys.
- Full Authorization headers.
- DPoP proofs or sensitive JWT payloads.
- Subject/tenant/token as high-cardinality metric labels.

If logging `kid` to investigate rotation, `kid` is typically public metadata, yet you still must bound cardinality and prevent clients from generating infinite labels.

## 25. Runbook When the Issuer Overloads During a Rollout

When discovery/JWKS latency spikes:

1. Identify which endpoint is overloaded: discovery, JWKS, or introspection.
2. Check new pod counts and concurrent rollout/scale events.
3. Inspect request rate, concurrency, 429/5xx, timeouts, and retry counts.
4. Temporarily slow down rollout batches or scale-up rates if possible.
5. Check whether instances have cache hits or are all cold.
6. Confirm whether a key rotation is happening concurrently.
7. Dampen retry storms and apply policy backoff/jitter.
8. If using a cache proxy, check proxy health, hit ratio, and cache keys.
9. Never disable issuer/audience/signature validation to restore traffic.
10. For cached keys, apply approved stale policy; for unverified new keys, fail closed.
11. As the issuer recovers, let instances retry in jittered batches rather than all at once.
12. Post-incident, review rollout policy, TTLs, coalescing, timeouts, and alert thresholds.

Never flush the entire cache while the issuer is overloaded unless the incident requires distrusting a key; flushing forces the entire fleet to re-fetch simultaneously.

## 26. Common Operational Mistakes

**"Each pod has a cache, so total load is negligible."** False. In-memory caches are typically independent; cold starts multiply requests by replica count.

**"Discovery and JWKS are a single request."** False. Discovery fetches metadata; JWKS returns public keys. Measure and optimize them separately.

**"Just set a huge TTL."** Long TTLs cut fetches but delay key rotation and removal visibility. Choose based on freshness and security policy.

**"On cache miss, retry immediately."** Synchronized retries worsen issuer overload. Use backoff, jitter, concurrency caps, and retry budgets.

**"Setting a static JWKS URI eliminates JWKS requests."** False. It can reduce discovery, but the decoder still must fetch and refresh keys.

**"Setting issuer-uri gives identical startup behavior everywhere."** False. Discovery timing depends on version, bean lifecycle, and configuration.

**"One warm pod means the whole fleet is warm."** False when caches are independent.

**"Refresh unboundedly on unknown kids."** That can cause request storms. Cap refreshes and reject when no matching key exists.

**"During an issuer outage, accept unverified tokens."** False. If a new key cannot be verified, those tokens must not be accepted.

**"Fail liveness on issuer errors so pods auto-restart."** This can trigger a cold-start storm. Separate process liveness from dependency readiness.

**"A cache proxy can serve JWKS indefinitely."** False. Caches still need freshness, key rotation, and emergency invalidation.

**"Flushing caches fixes every key issue."** While the issuer is overloaded, flushing fleet-wide caches causes a massive load spike.

## 27. Design and Rollout Process

1. **Measure baseline:** separate discovery, JWKS, and introspection traffic; record cache behavior.
2. **Confirm versions:** record exact Spring Boot, Spring Security, Nimbus, and HTTP client versions.
3. **Inspect lifecycle:** determine whether discovery/JWKS fetches run at startup, lazy initialization, or refresh.
4. **Define cache scope:** per-JVM in-memory, proxy cache, or shared cache; document TTLs and invalidation.
5. **Pace rollouts:** tune batch size, `maxSurge`, and scale-up rate to issuer capacity.
6. **Spread refreshes:** add jitter where supported and enable single-flight/coalescing.
7. **Configure networking:** timeouts, pools, retry budgets, exponential backoff, and rate limits.
8. **Separate startup/readiness/liveness:** avoid probes that fetch continuously and avoid fleet-wide restarts during transient issuer errors.
9. **Manage key rotation:** pre-publish new keys, keep overlap, watch refreshes, and maintain emergency invalidation.
10. **Protect trust:** keep issuer, audience, signature, and TLS validation; never fall back fail-open.
11. **Test cold starts:** multi-instance, cold caches, unknown `kid`s, 429/5xx, and outage recovery.
12. **Monitor operations:** dashboards, alerts, runbooks, and metrics free of tokens/secrets.
13. **Roll out in batches:** deploy to staging first, measure issuer load, then roll out to production.

**Takeaway:** Many Resource Servers booting together can trigger a discovery/JWKS fetch spike because caches are usually per-JVM. Separate metadata discovery from JWKS, measure requests and cache hits/misses, pace rollouts, use jitter and single-flight where supported, configure timeouts/backoff/concurrency, and align key rotation with cache freshness. Explicitly configuring `jwk-set-uri` can reduce discovery dependency but does not eliminate JWKS fetches. When the issuer fails or a key is unknown, verify only with existing trusted keys under approved stale policy; unverifiable tokens must be rejected.
