# Network Errors, Timeouts, and Verifying There Is No Verification Bypass Path

A **Spring Security OAuth 2.0/OIDC Resource Server** often depends on an external identity service to verify access tokens. For JWTs, the Resource Server may need to fetch public keys from a JWKS endpoint; for opaque tokens, it calls a token introspection endpoint. Both paths can encounter DNS failures, TLS handshake failures, connection refusals, timeouts, HTTP 5xx errors, malformed responses, or temporary identity-service unavailability.

Integration tests must prove two things:

1. When the token-verification dependency fails, the API handles requests under a bounded-time error policy and **never accepts unverified tokens**.
2. No silent fallback converts a network error into a successful Authentication, a default principal, permitted anonymous access, or a "token valid" outcome.

Never equate invalid tokens with verification-service outages. `active=false`, wrong signatures, or wrong issuer/audience are authentication failures. Timeouts or unreachable AS/JWKS endpoints are infrastructure errors. Neither should grant access; how HTTP status codes map and whether retries apply must be explicitly designed.

> **Principle:** Without verification, no Authentication may be granted. A network error is never proof of a valid token.

## 1. Two Verification Paths and Their Failure Points

### 1.1. JWT: Signature Verification via JWKS

JWT access tokens are verified locally once the Resource Server holds the matching public key. When configured with issuer discovery or a JWK Set URI, Spring Security/Nimbus may have to call the identity provider for metadata or JWKS:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as JWT Resource Server
    participant JWKS as Issuer JWKS endpoint
    C->>RS: Authorization: Bearer signed-JWT
    RS->>RS: Parse protected header (kid, alg)
    RS->>RS: Find trusted key in JWKS cache
    alt Key is not cached / refresh required
        RS->>JWKS: GET configured JWKS URI
        JWKS-->>RS: JWK Set
    end
    RS->>RS: Verify signature
    RS->>RS: Validate iss, aud, exp, nbf, typ
    RS-->>C: Resource response or authentication failure
~~~

An important point when writing tests: **JWKS caching can allow requests to keep verifying even while the JWKS endpoint is offline**. If the needed key is already cached, the decoder can continue verifying signatures locally. To test key-fetch failures, use a fresh decoder/cache or a token whose `kid` is not cached, while controlling the JWKS endpoint response.

If the application configures a static public key directly, request verification does not call JWKS on each request. In that setup, JWKS network timeout tests do not apply to that request path; test the actual dependencies used by your production configuration.

### 1.2. Opaque Tokens: Calling the Introspection Endpoint

Opaque tokens carry no locally signature-verifiable claims. The Resource Server sends the token to the AS per RFC 7662:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Opaque Resource Server
    participant AS as Introspection endpoint
    C->>RS: Authorization: Bearer opaque-token
    RS->>AS: POST /introspect (token + client authentication)
    alt AS responds active=true
        AS-->>RS: active=true + claims/scope
        RS->>RS: Build authenticated principal
        RS-->>C: Resource response
    else AS responds active=false
        AS-->>RS: active=false
        RS-->>C: Authentication failure
    else Network / timeout / server error
        AS--xRS: No usable introspection response
        RS-->>C: Fail closed (401 or service error by API policy)
    end
~~~

Introspection is a network call in the authentication flow unless the application caches introspection results. Consequently, AS latency and availability directly affect opaque-token authentication.

### 1.3. Failure Classification Table

| Event | Meaning | Must Never Happen |
|---|---|---|
| `active=false` | AS replied the token is inactive | Create an authenticated principal |
| Invalid JWT signature | Token was not signed by a trusted key or was altered | Skip signature and read claims |
| Wrong issuer/audience/type | Token violates this trust contract/API | Accept merely because signature passes |
| DNS/connect/TLS failure | Cannot reach verification dependency | Treat connection error as `active=true` |
| Read/response timeout | No result received before deadline | Wait indefinitely or let request through |
| HTTP 5xx from AS/JWKS | Verification dependency is failing | Return a default principal |
| Malformed/unparseable response | No trustworthy verification result | Accept based on partial response |
| Circuit breaker open | Dependency isolated due to consecutive errors | Use fallback returning a valid token |
| Cache miss while AS is offline | No fresh verification result | Skip introspection/JWKS validation |

## 2. Authentication Failures Differ from Identity-Provider Outages

The API must separate two outcome categories.

**Invalid credentials:** wrong signature, wrong issuer, wrong audience, expired, wrong token type, or introspection returning `active=false`. The Resource Server must reject Authentication. For Bearer APIs, the response is typically HTTP 401 and may include `WWW-Authenticate: Bearer`.

**Unable to verify due to infrastructure:** AS/JWKS endpoint timeout, DNS failure, TLS error, or 5xx response. The Resource Server must still grant no Authentication. However, this is a verification-service failure rather than proof the client's token is invalid.

Regarding HTTP responses:

- Default Bearer authentication entry points may map verification errors to 401.
- An API may map verification infrastructure failures to 503 Service Unavailable so clients distinguish "invalid credential" from "verification service temporarily unavailable."
- If distinguishing them, configure failure handling/entry points explicitly for Servlet or `ServerAuthenticationEntryPoint` for WebFlux. Never assume every library exception automatically maps to 503.
- Whether returning 401 or 503, the protected request must be blocked. Never return 2xx or create an authenticated principal without verification.

Never expose internal URLs, AS response bodies, client secrets, tokens, or stack traces in responses to callers. Internal logs should record error category, dependency, correlation ID, and duration; never log raw access tokens.

## 3. Timeouts Must Be Bounded at the HTTP Client Layer

Setting a timeout at only one layer is not always enough. Configure:

1. **Connection timeout:** caps time spent establishing a TCP/TLS connection.
2. **Read/response timeout:** caps time waiting for response data.
3. **Overall deadline:** caps total duration across the verification step, including retries.
4. **Bounded retries:** if retrying, cap attempts and apply only to suitable transient errors.

Illustrative budget:

~~~text
connect timeout: 1 second
response/read timeout: 2 seconds
overall authentication dependency budget: 3 seconds
retry: at most one attempt for selected transient failures
~~~

These numbers are illustrative only. Pick values matching your identity provider's latency/SLO, request budget, and end-to-end API SLA.

### 3.1. Why Never Wait Indefinitely?

If the AS stops responding, threads/requests stay blocked, connection pools exhaust, queues back up, and unrelated requests suffer. In WebFlux, blocking calls on the event loop can stall many concurrent requests at once. Finite deadlines free resources and return controlled error responses.

### 3.2. Retries Do Not Replace Timeouts

Retrying 3 times with a 10-second wait each still holds requests far too long. The overall deadline must cover retries and backoff. Never retry every error:

- Never retry invalid signatures, `active=false`, or wrong issuer/audience/type.
- Bounded retries can apply to transient connection errors or transient 5xx if policy allows.
- Never keep retrying when a circuit breaker is open.
- Never exceed the request's overall deadline.

Introspection uses POST, yet its purpose is querying token status. If retrying, weigh AS load, contract idempotency, attempt counts, and the chance token state changed between attempts. Never blindly retry all exceptions.

## 4. Configuring Timeouts for Servlet Resource Server

On the Servlet stack, `NimbusJwtDecoder` and `NimbusOpaqueTokenIntrospector` can use a timeout-configured `RestOperations`. Example with `RestTemplate` and `SimpleClientHttpRequestFactory`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestOperations;
import org.springframework.web.client.RestTemplate;

@Configuration
class IdentityHttpClientConfiguration {

    @Bean
    RestOperations identityRestOperations() {
        SimpleClientHttpRequestFactory requestFactory =
            new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(1_000);
        requestFactory.setReadTimeout(2_000);
        return new RestTemplate(requestFactory);
    }
}
~~~

Applying to JWT JWKS retrieval:

~~~java
@Bean
JwtDecoder jwtDecoder(RestOperations identityRestOperations) {
    return NimbusJwtDecoder
        .withJwkSetUri("https://identity.example.com/.well-known/jwks.json")
        .restOperations(identityRestOperations)
        .build();
}
~~~

Applying to opaque-token introspection:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        RestOperations identityRestOperations) {

    NimbusOpaqueTokenIntrospector introspector =
        new NimbusOpaqueTokenIntrospector(
            "https://identity.example.com/oauth2/introspect",
            "orders-resource-server",
            identityClientSecret);

    introspector.setRestOperations(identityRestOperations);
    return introspector;
}
~~~

In production, load `identityClientSecret` from a secret manager or protected configuration. The example merely demonstrates wiring a timeout-configured `RestOperations` into the introspector. If the decoder uses a static public key instead of a JWKS URI, no JWKS HTTP request runs during verification.

**Version note:** Builder/setter APIs can change across Spring Security and Spring Framework versions. Verify the exact Javadoc for the version managed by your Spring Boot BOM. What matters is that the HTTP client actually used for JWKS/introspection has finite connect/read timeouts; declaring a timeout bean without wiring it into the decoder/introspector does nothing.

## 5. Timeouts for WebFlux Resource Server

WebFlux should use a non-blocking HTTP client. With Reactor Netty, configure connect and response timeouts on `WebClient`:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

WebClient identityWebClient() {
    HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
        .responseTimeout(Duration.ofSeconds(2));

    return WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
}
~~~

For a reactive JWT decoder, pass the configured `WebClient` into `NimbusReactiveJwtDecoder`'s builder per your version's API:

~~~java
ReactiveJwtDecoder reactiveJwtDecoder(WebClient identityWebClient) {
    return NimbusReactiveJwtDecoder
        .withJwkSetUri(trustedJwkSetUri)
        .webClient(identityWebClient)
        .build();
}
~~~

For reactive opaque introspection, use a `ReactiveOpaqueTokenIntrospector`/`NimbusReactiveOpaqueTokenIntrospector` configured with a timeout-bounded HTTP client. You can wrap an additional reactive boundary deadline:

~~~java
ReactiveOpaqueTokenIntrospector boundedIntrospector(
        ReactiveOpaqueTokenIntrospector delegate) {
    return token -> delegate.introspect(token)
        .timeout(Duration.ofSeconds(3));
}
~~~

`Mono.timeout` bounds the publisher and emits a timeout error when exceeded. It does not replace HTTP connector connect/response timeouts; configure the network layer as well so sockets and connections are released cleanly.

Never call `block()` inside a reactive authentication flow to query the AS/JWKS. Never run a blocking `RestTemplate` on the Netty event loop. If integrating a blocking library is unavoidable, isolate it on a bounded scheduler or pick a reactive client/implementation; prefer a non-blocking verification path.

**Version note:** Constructors and methods for passing `WebClient` into reactive decoders/introspectors vary across versions. Confirm available builders/constructors in your project's Spring Security BOM. Never build a timeout-configured `WebClient` and forget to wire it into the actual implementation.

## 6. Caching, Key Rotation, and Behavior When Dependencies Are Offline

### 6.1. JWT JWKS Cache

JWT verification can continue working while the JWKS endpoint is offline if the required public key was already fetched and remains cached per decoder policy. This is not a bypass: signatures are still verified using a key previously fetched from a trusted JWKS.

Different scenarios:

| Key State | JWKS Endpoint | Possible Outcome |
|---|---|---|
| Valid key already cached | Offline | Decoder may continue verifying via cached key |
| New `kid` not yet cached | Online | Decoder may refresh JWKS and locate key |
| New `kid` not yet cached | Offline/timeout | Cannot fetch key; authentication fails |
| Key removed from JWKS | Online after refresh | Decoder can no longer verify tokens using that key |
| Unknown `kid` | Online, key absent | Authentication fails |

Do not write a blanket test asserting "JWKS offline must always return 401" when the key is already cached and caching is intentionally enabled. Separate warm-cache tests from cold-cache/unknown-key tests. Document your library/application key-cache lifetime and rotation policy clearly.

### 6.2. Opaque Introspection Cache

If the application caches introspection results, caching can keep previously verified tokens accepted briefly while the AS is offline. That is an intentional availability vs. revocation-latency decision, never an excuse to accept un-introspected tokens.

Cache policy should require:

- Cache only responses parsed and validated per contract.
- Never cache exceptions, timeouts, 5xx errors, or malformed responses as active results.
- TTL never exceeds the token's remaining lifetime when responses provide a trusted expiry.
- TTL fits within the token revocation SLA: long caches slow revocation propagation.
- Define handling for `active=false`; never turn it into active via cache fallback.
- Bind cache keys safely to the token; avoid logging raw tokens or using keys that leak credentials.

### 6.3. Do Not Confuse Stale Caches with Fail-Open

If policy permits serving a **previously verified active result still within TTL**, requests may succeed while the AS is temporarily offline. On a cache miss or expired TTL, requests must invoke introspection; when verification fails, reject them. Never build a cache fallback along the lines of "if the AS is unreachable, treat tokens as active."

## 7. Fail Closed and Dangerous Bypass Paths

### 7.1. What Does Fail Closed Mean?

Fail closed does not necessarily mean every failure returns the exact same HTTP status. It means:

- Never create an authenticated principal without a trustworthy verification result.
- Never turn network errors into `active=true`.
- Never skip validators when the decoder/introspector errors.
- Never downgrade a protected request to anonymous and let it proceed.
- Never fall back to arbitrary keys or issuers when JWKS is unreachable.
- Never grant broad default permissions when authorities could not be built.

### 7.2. Anti-Pattern: Catching Errors and Allowing Access

Never do this:

~~~java
try {
    return delegate.introspect(token);
}
catch (RuntimeException ex) {
    // Identity server is unavailable, allow request to continue.
    return trustedDefaultPrincipal();
}
~~~

This turns an outage into authentication success. Whenever a token cannot be verified, propagate the authentication/service failure so the Security filter blocks the request.

### 7.3. Anti-Pattern: Parsing Unverified JWT Payloads When Decoder Fails

Never do this:

~~~java
try {
    return jwtDecoder.decode(token);
}
catch (JwtException ex) {
    return parsePayloadWithoutVerifyingSignature(token);
}
~~~

A JWT payload is purely caller-supplied data until its signature is verified. Reading `sub`, `scope`, or `iss` from an unverified payload to construct a principal is a direct security bypass.

### 7.4. Anti-Pattern: Falling Back to an Arbitrary Key

Never do this:

~~~text
unknown kid / JWKS timeout
    -> choose first cached key
    -> skip signature error
    -> accept claims
~~~

`kid` is only a key selector. If no matching key is found or the signature fails verification, the token is unauthenticated. Never fall back to an unrelated old key or a token-supplied public key.

### 7.5. Anti-Pattern: Returning Mono.empty() as a Verification Result

In custom reactive authentication code, never convert timeouts/errors into `Mono.empty()` where a `permitAll()` rule might accidentally permit anonymous access. `Mono.empty()` signals no authentication result; `permitAll()` routes can still let the request through. Protected endpoints must explicitly require authentication/authorities and be tested with missing Authentication as well.

### 7.6. Anti-Pattern: permitAll Fallbacks

Never configure:

~~~java
.anyExchange().permitAll()
~~~

for an API requiring access tokens just to keep the app up when the AS is offline. Truly public endpoints may use `permitAll()`, isolated under dedicated matchers. Never leave a catch-all rule permitting requests after authentication failures.

## 8. Testing with MockWebServer or WireMock

Use a simulated HTTP server to control JWKS/introspection responses. Tests must still send Bearer tokens through the application's real Security filter chain.

Common tools:

- **MockWebServer:** controls responses, delays, disconnects, and inspects received requests.
- **WireMock:** stubs HTTP statuses/bodies, fixed delays, faults, and verifies requests.
- An equivalent local test server if your project already has test infrastructure.

There is no need to call a real AS in standard unit/integration tests. Test servers should bind loopback/ephemeral ports and shut down cleanly after tests to avoid environment coupling.

### 8.1. Response Matrix for Opaque Introspection

| Mock AS Response | What to Verify |
|---|---|
| 200 with `active=true` | Principal is built and authorization runs |
| 200 with `active=false` | Token is rejected |
| 401/403 from introspection endpoint | Resource Server credentials/config are wrong; no principal created |
| 500/503 | Authentication fails; infrastructure error classified per policy |
| Malformed response / missing `active` | Rejected |
| Delay exceeding read timeout | Request terminates within deadline and grants no access |
| Disconnect before response | No principal created |
| Connection refused | No principal created |

### 8.2. Response Matrix for JWKS

| JWKS Behavior | Token | What to Verify |
|---|---|---|
| JWKS returns public key A | Signed with private key A | Signature verifies |
| JWKS returns public key A | Signed with private key B | Signature rejected |
| JWKS returns 500 | Uncached `kid` | Cannot verify; no bypass |
| JWKS times out | Uncached `kid` | No Authentication created |
| JWKS offline | Cached `kid` | Configured cache behavior verified |
| JWKS returns unparseable JWK Set | Uncached `kid` | Decoder creates no principal |
| JWKS online, `kid` absent | Token uses key absent from set | Authentication fails |

To test JWKS failures deterministically, use a fresh decoder/cache for cold-cache tests. If tests share a decoder across cases, keys cached by an earlier test can prevent outage tests from hitting JWKS at all.

## 9. Opaque Token Integration Test Example with MockMvc

The example below illustrates the test structure. `MockWebServer` acts as the introspection endpoint; the application's URI properties and introspector bean must point to this server.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpaqueIntrospectionFailureIntegrationTest {

    static MockWebServer identityServer;

    @BeforeAll
    static void startIdentityServer() throws IOException {
        identityServer = new MockWebServer();
        identityServer.start();
    }

    @AfterAll
    static void stopIdentityServer() throws IOException {
        identityServer.shutdown();
    }

    @Autowired
    MockMvc mockMvc;

    @Test
    void activeTokenCanReachProtectedEndpoint() throws Exception {
        identityServer.enqueue(new MockResponse()
            .setHeader("Content-Type", "application/json")
            .setBody("""
                {
                  "active": true,
                  "sub": "alice",
                  "scope": "orders.read",
                  "aud": ["orders-api"]
                }
                """));

        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-test-token"))
            .andExpect(status().isOk());

        RecordedRequest request = identityServer.takeRequest();
        assertThat(request.getMethod()).isEqualTo("POST");
        assertThat(request.getPath()).isEqualTo("/introspect");
        assertThat(request.getBody().readUtf8())
            .contains("token=opaque-test-token");
    }

    @Test
    void inactiveTokenIsRejected() throws Exception {
        identityServer.enqueue(new MockResponse()
            .setHeader("Content-Type", "application/json")
            .setBody("{\"active\":false}"));

        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer inactive-token"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

This example requires imports from OkHttp MockWebServer and Spring Test. If the introspector uses caching, configure an isolated cache or disable caching for these tests so every request receives its expected response. Verify request bodies per your implementation's encoding/form contract; do not assume every provider sends form parameters in the same order.

### 9.1. Testing Timeouts

MockWebServer can delay responses past the read timeout:

~~~java
identityServer.enqueue(new MockResponse()
    .setHeadersDelay(5, TimeUnit.SECONDS)
    .setBody("{\"active\":true,\"sub\":\"alice\"}"));
~~~

If the HTTP client's read timeout is 2 seconds, the test must prove:

- The request does not wait the full 5 seconds for a response.
- No authenticated principal is created.
- The protected endpoint never returns 2xx.
- Exceptions map per the API contract (401, or 503 if custom handling is configured).
- No fallback introspector or default principal is invoked.

Give timeouts enough headroom to avoid CI scheduling flakiness while staying clearly shorter than the server delay. Never use `Thread.sleep` to measure timeouts; use test deadlines/Awaitility or deterministic MockWebServer configuration.

### 9.2. Testing Server Disconnects

You can use `SocketPolicy.DISCONNECT_AT_START` or your MockWebServer version's equivalent fault policy to drop connections. Expected behavior matches timeouts: the request is blocked and no Authentication is created. If the test server library changes APIs across versions, select the matching fault mode; what matters is proving the client receives no valid verification response.

## 10. Example JWKS Outage Tests

To test JWKS, the test server must serve a JWK Set containing the test public key. Tokens are signed with the matching private key. Configure `NimbusJwtDecoder` with the server's URI.

### 10.1. Happy Path with JWKS

~~~text
1. Generate RSA keypair A.
2. Publish public key A as a JWK with kid=test-key-a.
3. Sign access token with private key A and header kid=test-key-a.
4. Send Authorization: Bearer <token> through MockMvc/WebTestClient.
5. Assert request succeeds and JWKS endpoint received a GET.
~~~

Illustrative JWK Set response:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "test-key-a",
      "n": "BASE64URL_RSA_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

In test code, build the JWK from the public key using Nimbus `RSAKey` and serialize `JWKSet` instead of hardcoding fake moduli. Never place private keys inside the JWKS response.

### 10.2. Unknown kid When JWKS Errors

Create a token signed by key B with `kid=test-key-b` while JWKS contains only key A or returns 503. Use a fresh decoder to guarantee key B is not cached.

Expected:

- The decoder finds no trusted public key.
- Authentication fails.
- The protected endpoint never returns 2xx.
- No fallback to payload parsing or arbitrary keys occurs.

### 10.3. Cached Key While JWKS Is Offline

This is a separate test:

1. Send an initial request so the decoder fetches key A and verifies the token.
2. Make the JWKS server stop responding.
3. Send another token signed by key A with the same `kid`.
4. Observe behavior matching your decoder/version's cache rules.

If the decoder continues verifying from cached keys, that may be expected behavior. Never call this "fail-open" from this result alone; signatures are still verified against a public key fetched from a trusted source. Document cache TTL, rotation, and revocation assumptions explicitly.

## 11. Verifying There Is No Verification Bypass Path

A test asserting only 401 when the AS fails is insufficient if another code path can still mint an Authentication. You must prove protected requests never reach controllers and no fallback path exists.

### 11.1. Verifying Controllers/Services Are Never Invoked

~~~java
@Test
void introspectionFailureNeverInvokesProtectedHandler() throws Exception {
    identityServer.enqueue(new MockResponse().setResponseCode(503));

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-test-token"))
        .andExpect(status().isServiceUnavailable());

    verify(orderService, never()).listOrders(any());
}
~~~

This example expects 503 if the application configures custom identity-provider outage error mapping. If your API uses the default Bearer entry point returning 401 on authentication failures, assert the contract's actual status while still verifying the service/controller was never called.

### 11.2. Verifying Introspector Invocation Counts

Use a spy/mock or counting test introspector to confirm:

- Valid Bearer requests invoke the introspector/decoder.
- Timed-out Bearer requests are never replaced by a fixture principal.
- No fallback call hits a second introspector returning `active=true`.
- Cache hits occur only when a previously verified entry remains within TTL.

For JWKS, assert requests to the JWKS endpoint on cold-cache/unknown-kid runs; keep in mind caching may result in zero HTTP calls on subsequent requests.

### 11.3. Never Use Mock Authentication in Trust Integration Tests

These helpers intentionally skip token verification:

- `mockJwt()` in WebTestClient.
- `jwt()`/`mockJwt()` in MockMvc.
- `opaqueToken()`/`mockOpaqueToken()` in MockMvc/WebTestClient.
- `@WithMockUser`.
- Manually setting `SecurityContext` or `JwtAuthenticationToken`.

They are useful for post-authentication authorization/controller tests. They cannot prove decoder/introspector timeouts or network errors are handled safely. In these integration tests, send real Bearer tokens (genuinely signed test JWTs, or opaque test strings against an introspection stub) through the filter chain.

### 11.4. Verifying Protected Routes Never Allow Anonymous Access

When authentication fails, the framework may produce no Authentication and leave the request anonymous. Every sensitive route must therefore carry explicit `authenticated()`/authority rules. Test:

- Missing token → cannot access protected route.
- Token unverifiable due to dependency outage → cannot access protected route.
- Inactive/invalid token → cannot access protected route.
- Valid token with sufficient privileges → allowed.
- Public routes opened only via explicit matchers, never a global fallback.

If `permitAll()` routes exist, test matchers to verify protected paths cannot accidentally fall into public routes.

## 12. Circuit Breakers, Retries, and Bulkheads

A circuit breaker stops the application from piling load onto a failing AS. When the circuit opens, the authentication dependency must fail clearly and protected requests must remain blocked.

### 12.1. Circuit Breakers Must Have No "Active" Fallback

Behavior pattern:

~~~text
introspection call
    |
    +-- success + active=true -> authenticated principal
    +-- success + active=false -> invalid token
    +-- timeout / connection / 5xx -> authentication service failure
    +-- circuit open -> authentication service failure
~~~

Never configure a fallback returning a default principal, default scopes, or `active=true`. A circuit breaker only throttles dependency calls; it never replaces token verification.

### 12.2. Bounded Retries

Retries should:

- Apply only to clearly defined transient errors.
- Enforce a finite attempt limit.
- Use small backoff and jitter where appropriate.
- Count toward the overall deadline.
- Never retry invalid tokens, bad signatures, wrong issuers/audiences, or `active=false`.
- Never keep retrying while the circuit breaker is open.

### 12.3. Bulkheads and Connection Pools

Cap concurrency toward the identity provider so an outage cannot exhaust all API resources. Monitor:

- Requests waiting on verification.
- Connection pool utilization.
- Timeout counts and latency percentiles.
- Circuit breaker state.
- Authentication failures from bad credentials vs. service failures from dependency outages.

Never expand pool sizes endlessly to mask timeouts; doing so turns an AS outage into a full Resource Server outage.

## 13. Caching and Outage Policies Must Be Tested

When implementing introspection caching or relying on JWKS caching, tests must specify exact cache behavior:

| Test | Cache State | Dependency | Outcome to Verify |
|---|---|---|---|
| Opaque token first use | Miss | AS `active=true` | Principal built and entry cached |
| Opaque token reuse | Hit, within TTL | AS offline | Per policy, verified cached active result may be used |
| Opaque token after TTL | Expired | AS offline | Fail closed; never turn a miss into active |
| Opaque token after revoke | Cached active | AS `active=false`/revoked | Revocation delay stays within defined SLA |
| JWT known `kid` | Public key cached | JWKS offline | Signature still verified via cached key if policy/cache permits |
| JWT unknown `kid` | Miss | JWKS offline | Cannot verify; rejected |
| Cache store unavailable | Unknown | AS online/offline | Per explicit policy; never serve unverified entries |

Avoid blanket assertions like "when the AS is offline, all tokens must be rejected" if the system intentionally uses a TTL-bounded cache. The invariant to uphold is: **without a valid cache entry and without verification, there is no Authentication**.

## 14. Common Mistakes

| Anti-pattern | Risk | Fix |
|---|---|---|
| No connect/read timeouts | Requests/threads/connections hang indefinitely | Set finite timeouts on the HTTP client |
| Using `Mono.timeout` without configuring the HTTP connector | Publisher times out while underlying network resources linger | Configure both the connector and the overall deadline |
| Retrying every exception | Amplifies AS load and prolongs requests | Bound retries to transient failures only |
| Returning `active=true` on AS timeout | Direct verification bypass | Propagate service/authentication failure |
| Parsing payload when JWT decoder errors | Trusts unverified claims | Never build a principal if signature/key validation fails |
| Picking the first key when JWKS is offline | Could verify with the wrong key | Use only keys matching the trusted JWK Set and `kid` |
| Using `mockJwt()` to test JWKS timeouts | Bypasses decoder/JWKS | Send signed Bearer JWTs through the filter chain |
| Using `opaqueToken()` to test introspection timeouts | Bypasses introspector | Send opaque Bearer tokens through the filter chain |
| Caching exceptions as active | Turns outages into unauthorized access | Cache only verified successful responses per policy |
| Conflating `active=false` and 5xx | Credential failures confused with outages | Classify errors and metrics separately |
| Returning `Mono.empty()` fallback on auth error | `permitAll()` routes may admit anonymous requests | Require `authenticated()`/authorities on protected routes |
| Circuit breaker fallback principal | Grants access while circuit is open | Open circuits must fail closed |
| Sharing decoder/key caches across outage tests | JWKS outage tests never hit the network | Create a fresh decoder/cache for cold-cache cases |
| Asserting only status without checking handlers | Handler may have executed via fallback | Verify controllers/services were never called |
| Logging raw tokens or client secrets | Credential leakage | Redact tokens/secrets and log correlation IDs |

## 15. Comprehensive Test Matrix

| Scenario | Trigger | Security Outcome | Additional Assertions |
|---|---|---|---|
| Opaque active | AS returns `active=true` | Authenticated | Handler invoked |
| Opaque inactive | AS returns `active=false` | 401 | Handler not invoked |
| Introspection 500 | Mock AS returns 500 | Fail closed | 401/503 per contract; no principal |
| Introspection timeout | Response delayed past deadline | Fail closed | Completes within deadline; handler not invoked |
| Introspection disconnect | Server closes socket | Fail closed | No fallback |
| JWKS valid | JWKS contains matching public key | Authenticated | Decoder verifies signature |
| JWKS 503, cold cache | Unknown `kid` | Fail closed | Payload not parsed to grant access |
| JWKS timeout, cold cache | Unknown `kid` | Fail closed | Handler not invoked |
| JWKS outage, warm cache | Key still cached | Per cache policy | Signature still verified |
| Circuit open | Simulate open breaker | Fail closed | No continuous AS calls, no principal |
| Missing Bearer | No token sent | 401 | Protected handler not invoked |
| Valid token missing scope | Token verified cleanly | 403 | Authentication present, authorization fails |
| Valid token with scope | Token verified cleanly | 2xx | Handler invoked |

## 16. Pre-Release Checklist

### Network Resilience

- [ ] Connect timeout configured on JWKS/introspection HTTP clients.
- [ ] Read/response timeout configured.
- [ ] Overall deadline enforced on authentication dependencies.
- [ ] Retries are bounded and limited to transient failures.
- [ ] Connection pools and concurrency are capped.
- [ ] WebFlux performs no blocking I/O on the event loop.

### Fail-Closed

- [ ] `active=false` never creates an Authentication.
- [ ] Timeouts/DNS/TLS/5xx never create an Authentication.
- [ ] Decoder never parses unverified payloads to build principals.
- [ ] Unknown `kid` never falls back to arbitrary keys.
- [ ] Cache miss + offline dependency is rejected.
- [ ] Open circuit breakers have no fallback authenticated principal.
- [ ] Protected routes never admit anonymous requests.

### Integration Tests

- [ ] Tests send Bearer tokens through the real filter chain.
- [ ] Introspection active/inactive responses tested.
- [ ] Introspection timeouts, disconnects, and 5xx tested.
- [ ] Valid JWKS, unknown `kid`, and cold-cache timeouts/5xx tested.
- [ ] JWKS warm-cache behavior tested separately.
- [ ] Assertions verify controllers/services do not execute when verification fails.
- [ ] 401/503 status mapping tested per API contract.
- [ ] `mockJwt()`/`opaqueToken()` never replace network verification tests.

## 17. Conclusion

~~~text
TOKEN VALIDATION
  JWT: trusted key + signature + iss/aud/time/type
  Opaque: successful introspection + active=true

DEPENDENCY FAILURE
  DNS / connect / TLS / timeout / 5xx / malformed response
      |
      v
  NO VERIFIED AUTHENTICATION
      |
      v
  Protected endpoint remains inaccessible
  (401 or 503 according to explicit API policy)

NEVER
  network error -> active=true
  decoder error -> unverified payload principal
  unknown kid -> arbitrary key
  circuit open -> default authenticated user
  cache miss -> accept without verification
~~~

Network failures and timeouts are normal operational conditions that must be tested as part of your trust boundary. A JWT Resource Server can keep verifying with cached public keys; an opaque Resource Server can serve cached introspection results within its policy-approved TTL. Whenever no trustworthy key or introspection result is available, the system must never grant an Authentication.

Configure timeouts on the actual HTTP client used by your decoder/introspector, bound retries and deadlines, and test dependency failures using MockWebServer or WireMock. Most importantly, send Bearer tokens through the real Security filter chain in integration tests, verify protected handlers never run, and confirm no fallback converts network errors into access. `mockJwt()` and `opaqueToken()` remain valuable for controller/authorization tests, yet they prove neither network verification nor fail-closed behavior.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection requests/responses, `active`, and token metadata.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK Sets, key identifiers, and public key distribution.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): discovery metadata and endpoint configuration.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token validation profile.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): signature verification, trusted key sources, and JWT validation.
- [Spring Security Reference — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector` and opaque-token authentication.
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, JWKS, and JWT validation.
- [Spring Security Reference — Reactive Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): reactive opaque-token introspection.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` and WebFlux JWT authentication.
- [Spring Framework Reference — HTTP Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): configuring HTTP clients and request factories.
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client.
- [Reactor Netty Reference — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connect timeout, response timeout, and connection settings.
- [OkHttp MockWebServer](https://github.com/square/okhttp/tree/master/mockwebserver): controlling HTTP responses and network failures in tests.
- [WireMock Documentation](https://wiremock.org/docs/): stubbing, delays, faults, and request verification.
