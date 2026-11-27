# Test JWKS, Metadata, Introspection Servers and Resource Lifecycle

Integration verification of a Spring Security OAuth 2.0 Resource Server requires more than a JWT constructed in a unit test. A real application must discover Authorization Server metadata, fetch public keys from a JWKS endpoint or call an introspection endpoint, validate tokens, and handle changes over time such as key rotation, caching, timeouts, and server outages.

In integration tests, you can run local HTTP servers acting as the **OIDC/OAuth Authorization Server metadata endpoint**, **JWKS endpoint**, and **token introspection endpoint**. These test servers return controlled responses to test the entire HTTP boundary without depending on an external IdP.

A solid test environment should prove:

- The Resource Server resolves the configured metadata and JWKS URI properly.
- JWTs signed by the private key matching a public key in the JWKS are accepted.
- JWTs with invalid signatures, `kid`, issuer, audience, or expiration are rejected.
- Key rotation works according to the designed cache and overlap window.
- Opaque tokens are introspected at the right endpoint with the right client authentication and form request.
- Inactive tokens, introspection errors, timeouts, or contract-violating responses are handled safely.
- Test servers, ports, keys, caches, and authorized resources are initialized and shut down with proper lifecycle management, even when tests run in parallel.

> **Goal:** verify the HTTP contract between the Resource Server and the identity provider. Tests use local servers and dedicated test keys; they never depend on real-environment accounts, tokens, or private keys.

## 1. Integration Test Architecture

A test suite can stand up the following endpoints:

| Test Endpoint | Role | Key Response Fields |
| --- | --- | --- |
| `/.well-known/openid-configuration` | OIDC Provider Configuration | `issuer`, `jwks_uri`, endpoint metadata |
| `/.well-known/oauth-authorization-server` | OAuth Authorization Server Metadata per RFC 8414 | `issuer`, `jwks_uri`, endpoint metadata |
| `/oauth2/jwks` | JWK Set | Public JWKs for signature verification |
| `/oauth2/introspect` | Token Introspection per RFC 7662 | `active`, scope, subject, audience, and metadata |

These examples place the issuer at the root path for URL clarity. If the issuer includes a path, the discovery URL follows OIDC Discovery or RFC 8414 rules accordingly; tests must stub the exact URL that the Spring/Nimbus version calls.

~~~mermaid
flowchart TD
    T["MockMvc / Integration test"]
    RS["Spring Security Resource Server"]
    DISC["Metadata test server"]
    JWKS["JWKS test server"]
    INT["Introspection test server"]
    KEY["RSA / EC test key pair"]
    FIX["Token fixtures"]

    T -->|"Bearer JWT"| RS
    RS -->|"Discovery GET"| DISC
    DISC -->|"jwks_uri"| RS
    RS -->|"JWKS GET"| JWKS
    KEY --> JWKS
    KEY --> FIX
    FIX -->|"signed JWT"| T
    T -->|"Bearer opaque-token"| RS
    RS -->|"Introspection POST"| INT
    INT -->|"active + claims"| RS
~~~

In practice, a single MockWebServer/WireMock instance can serve multiple endpoints, or each endpoint can run on its own server. Using one server with a dispatcher usually keeps tests simpler, while separate servers are useful when simulating dependencies with different lifecycles or availability.

## 2. Choosing a Test Server and Managing Ports

Available options include:

- **MockWebServer** from OkHttp: lightweight HTTP server, response queuing, easy inspection of received requests (method/header/body).
- **WireMock**: stubbing by URL, method, header, body; supports scenarios, delays, faults, and dynamic ports.
- **Testcontainers**: runs a real IdP or container serving JWKS/metadata/introspection when testing production-like interactions.
- **JDK embedded HTTP server**: sufficient for tiny fixtures, though you must implement routing, request parsing, and cleanup yourself.

Never hardcode a fixed port like `8089` in a test suite. Two test processes or parallel workers can run concurrently and collide on the same port. Request an OS-assigned dynamic port instead:

~~~java
MockWebServer server = new MockWebServer();
server.start(); // MockWebServer picks an open port automatically

String baseUrl = server.url("/").toString();
String issuer = baseUrl.substring(0, baseUrl.length() - 1);
String jwksUri = server.url("/oauth2/jwks").toString();
~~~

The snippet above illustrates how to obtain the URLs. For real issuers, ensure the issuer value in metadata and the `iss` claim in JWTs match the configured issuer exactly; do not arbitrarily add or strip trailing slashes.

### 2.1. Avoiding Startup Race Conditions

Before creating the Spring ApplicationContext, the test server must:

1. Bind successfully to the dynamic port.
2. Be ready to accept HTTP requests.
3. Have metadata/JWKS/introspection responses configured for the scenario.
4. Register the dynamic URLs in Spring properties or test configuration.

Do not start the server asynchronously and immediately spin up the context before the port is listening. Avoid fixed Thread.sleep() calls; use lifecycle hooks or a bounded-timeout readiness check.

### 2.2. Lifecycle Example with JUnit

~~~java
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;

class ResourceServerIntegrationTest {

    static final MockWebServer identityServer = new MockWebServer();

    @BeforeAll
    static void startIdentityServer() throws Exception {
        identityServer.start();
        // Configure the dispatcher or enqueue responses needed for the suite.
    }

    @AfterAll
    static void stopIdentityServer() throws Exception {
        identityServer.shutdown();
    }
}
~~~

With Spring Test, combine `@DynamicPropertySource` to inject dynamically allocated URLs into the context:

~~~java
@DynamicPropertySource
static void resourceServerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.security.oauth2.resourceserver.jwt.issuer-uri",
            ResourceServerIntegrationTest::issuer);
}
~~~

In a complete example, issuer() returns the issuer URL from the started server. Ensure the server is started before Spring resolves dynamic properties. You can use a JUnit extension or a self-managed static test fixture to guarantee lifecycle ordering.

### 2.3. Shared Server vs. One Server per Test?

| Organization | Pros | Risks/Costs |
| --- | --- | --- |
| Server per test class | Faster startup, stable fixtures, fewer ports | Must reset state/queues between tests |
| Server per test method | Strong state isolation, easy to test isolated failures | Many startups, slower tests |
| Suite-wide server | Resource-efficient | Easy to leak state, response queues, and keys across tests |
| Testcontainers per suite/class | Close to real environment | Heavier startup/cleanup, requires Docker |

Choose the scope based on the state each test mutates. Key rotation, response delay, or inactive introspection tests usually need isolated state; never let test execution order determine which response another test receives.

## 3. Building an OIDC Metadata Server

When `issuer-uri` is configured, the Resource Server may need discovery metadata to locate `jwks_uri`. OIDC Discovery uses Provider Configuration; OAuth Authorization Server Metadata is standardized in RFC 8414. The metadata response must contain the exact issuer and a valid JWKS URI.

Illustrative OIDC response:

~~~json
{
  "issuer": "http://127.0.0.1:49152",
  "jwks_uri": "http://127.0.0.1:49152/oauth2/jwks",
  "authorization_endpoint": "http://127.0.0.1:49152/oauth2/authorize",
  "token_endpoint": "http://127.0.0.1:49152/oauth2/token",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

The authorization/token endpoints in this example are supplementary metadata; the Resource Server JWT decoder primarily needs issuer and JWKS URI. Not every Resource Server test needs to stand up an authorization endpoint.

### 3.1. Stubbing the Metadata Response

With MockWebServer, you can enqueue a response:

~~~java
String issuer = identityServer.url("/").toString();
if (issuer.endsWith("/")) {
    issuer = issuer.substring(0, issuer.length() - 1);
}
String jwksUri = identityServer.url("/oauth2/jwks").toString();

String metadata = """
    {
      "issuer": "%s",
      "jwks_uri": "%s"
    }
    """.formatted(issuer, jwksUri);

identityServer.enqueue(new MockResponse()
    .setHeader("Content-Type", "application/json")
    .setBody(metadata));
~~~

This is a simple way to queue a response for a single request. When testing discovery, verify the exact path the client calls and use a dispatcher if one server serves both metadata and JWKS. Do not assume all Spring/Nimbus versions use the same discovery URL for issuers that include a path.

### 3.2. Metadata Cases to Test

| Scenario | Metadata Server Response | Expected Outcome |
| --- | --- | --- |
| Successful discovery | Matching issuer, valid jwks_uri | Decoder initializes and fetches keys |
| Issuer mismatch | Issuer differs from configured issuer | Discovery/validation fails |
| Missing jwks_uri | Metadata lacks required field | Cannot fetch signing keys |
| Invalid URI | Malformed jwks_uri | Initialization or key fetch fails |
| Metadata 404 | Discovery endpoint does not exist | Discovery fails |
| Metadata 500 | IdP metadata server error | Startup/fetch fails per configuration |
| Timeout | Server does not respond | Request/context fails on timeout |
| Malformed JSON | Unparseable body | Discovery fails |
| Wrong Content-Type | Response is not valid JSON | Client may reject parsing |

### 3.3. Verifying the Exact Issuer

An issuer is an identifier, not a URL to normalize arbitrarily. The following values may not be equivalent under the contract:

~~~text
https://id.example.test/realms/shop
https://id.example.test/realms/shop/
http://id.example.test/realms/shop
~~~

Tests must use the exact same value in:

- Spring's `issuer-uri` property.
- Metadata `issuer`.
- Access token `iss` claim.

Do not strip trailing slashes or change schemes just to make a test pass. If a reverse proxy produces a public issuer distinct from an internal address, metadata and tokens must use a consistent public issuer.

### 3.4. Discovery vs. Direct JWKS URI Configuration

These are two different test paths:

**Discovery path:** configure `issuer-uri`, stub the metadata endpoint, and verify the Resource Server resolves `jwks_uri`.

**Direct JWKS path:** configure `jwk-set-uri` directly and test the decoder fetching JWKS without relying on discovery metadata. If both `issuer-uri` and `jwk-set-uri` are configured per Spring Boot support, the application can still validate the token's issuer without needing discovery to locate the JWKS.

Do not use a direct JWKS test to conclude that metadata discovery works. These are two separate configuration paths.

## 4. Building a JWKS Endpoint and Signing Test JWTs

A JWKS is a JSON Web Key Set containing the public keys the Resource Server uses to verify JWT signatures. A key typically has `kty`, `kid`, `use`, `alg`, and public parameters. Never include private parameters such as RSA `d`, `p`, `q` or the EC private scalar in a JWKS response.

RSA JWKS example:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "orders-test-key-1",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

### 4.1. Generating a Dedicated Test RSA Key Pair

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(2048);
KeyPair keyPair = generator.generateKeyPair();

RSAPublicKey publicKey = (RSAPublicKey) keyPair.getPublic();
RSAPrivateKey privateKey = (RSAPrivateKey) keyPair.getPrivate();
~~~

The private key is used only to sign test fixtures. The JWKS endpoint publishes only the public key. Each test suite should generate its own keys or use version-controlled test fixture keys; never use production private keys.

### 4.2. Creating JWK and JWKS with Nimbus

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;

RSAKey signingJwk = new RSAKey.Builder(publicKey)
    .privateKey(privateKey)
    .keyID("orders-test-key-1")
    .algorithm(com.nimbusds.jose.JWSAlgorithm.RS256)
    .keyUse(com.nimbusds.jose.jwk.KeyUse.SIGNATURE)
    .build();

JWKSet publicJwkSet =
        new JWKSet(signingJwk.toPublicJWK());

String jwksJson = publicJwkSet.toString();
~~~

When constructing the public JWKS, call `toPublicJWK()` before serializing. Never serialize the full `signingJwk` because it contains the private key.

Stubbing the endpoint:

~~~java
identityServer.enqueue(new MockResponse()
    .setHeader("Content-Type", "application/json")
    .setBody(publicJwkSet.toString()));
~~~

If using a dispatcher, serve JWKS on `/oauth2/jwks` and metadata on the discovery path; do not rely on response queue ordering when tests can issue multiple requests.

### 4.3. Signing an Access Token for the Resource Server

`NimbusJwtEncoder` can sign JWTs using a JWK source holding the test private key:

~~~java
JWKSource<SecurityContext> jwkSource =
        new ImmutableJWKSet<>(new JWKSet(signingJwk));

JwtEncoder encoder = new NimbusJwtEncoder(jwkSource);

Instant now = Instant.now();
JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuer(issuer)
    .subject("alice-42")
    .audience(List.of("orders-api"))
    .issuedAt(now.minusSeconds(5))
    .notBefore(now.minusSeconds(5))
    .expiresAt(now.plusSeconds(300))
    .claim("scope", "orders.read")
    .build();

JwsHeader header = JwsHeader
    .with(SignatureAlgorithm.RS256)
    .keyId("orders-test-key-1")
    .build();

String token = encoder.encode(
    JwtEncoderParameters.from(header, claims)).getTokenValue();
~~~

Required imports from Nimbus and Spring Security JOSE:

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
~~~

The `kid` header must match the key ID in the JWKS. If `kid` matches no key, the decoder cannot select an appropriate signing key and must reject the token.

### 4.4. Testing Signatures and Key Selection

Baseline tests:

| Token | JWKS | Result |
| --- | --- | --- |
| Signed by private key A, `kid=A` | Public key A | Signature passes |
| Signed by private key B, `kid=B` | Only public key A | Signature fails |
| Signed by A, `kid=unknown` | Public key A with `kid=A` | No key found for `kid`; rejected |
| Signed by A, `kid=A` | Empty JWKS | Rejected |
| `alg=none` | Public RSA key present | Rejected |
| Signed with an algorithm not in allowlist | Matching key in JWKS | Rejected per decoder policy |

Do not test only valid JWT signatures. Testing wrong `kid` values and untrusted keys verifies the decoder does not accept tokens merely because the payload has valid claims.

### 4.5. Connecting the Metadata/JWKS Server to Spring Resource Server

With Boot configuration, point the issuer to the test server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${TEST_ISSUER_URI}
~~~

In tests, pass the dynamic value via `@DynamicPropertySource` or test properties. When the context starts, Spring/Nimbus performs metadata discovery and fetches JWKS from `jwks_uri`.

When testing the decoder directly:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer));
~~~

For direct JWKS testing:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUri)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer));
~~~

These two configurations illustrate two distinct initialization paths. `withJwkSetUri` does not automatically discover metadata; if issuer validation is needed, still attach the issuer validator explicitly.

### 4.6. Verifying Actual Requests to JWKS

After calling a Resource Server endpoint with a JWT:

~~~java
RecordedRequest metadataRequest = identityServer.takeRequest();
RecordedRequest jwksRequest = identityServer.takeRequest();

assertThat(metadataRequest.getMethod()).isEqualTo("GET");
assertThat(metadataRequest.getPath()).contains("openid-configuration");
assertThat(jwksRequest.getMethod()).isEqualTo("GET");
assertThat(jwksRequest.getPath()).isEqualTo("/oauth2/jwks");
~~~

This example applies when metadata discovery is configured and the server queues responses in order. With a dispatcher or concurrent requests, inspect requests by path rather than assuming arrival order. You can use `takeRequest(timeout, unit)` to prevent tests from hanging indefinitely if the server receives no request.

## 5. Key Rotation and JWKS Caching

Key rotation is one of the primary reasons to run a JWKS test server. An Authorization Server can begin issuing tokens with a new key while the Resource Server still holds the old JWKS in cache. A safe design needs an overlap window so tokens still valid under the old key can be verified while instances update their key sets.

Example:

~~~text
Time t0:
  JWKS = [key-A]
  token-A is signed with private-A

Time t1:
  JWKS = [key-A, key-B]
  AS starts signing new tokens with private-B

Time t2:
  Resource Servers have fetched the updated JWKS
  both token-A and token-B verify successfully

Time t3:
  Tokens signed with key-A have expired + overlap window elapsed
  JWKS = [key-B]
~~~

### 5.1. Keeping the Old Key During the Overlap Window

Do not remove key A from the JWKS as soon as you start signing with key B. Previously issued access tokens signed with A may still be valid. If the JWKS drops A while token A should still be accepted, valid requests will fail with 401.

The overlap window must account for:

- Maximum lifetime of old access tokens.
- Clock skew accepted by the Resource Server.
- JWKS cache TTL and refresh interval.
- Propagation delay across instances/regions.
- Ability to roll back to the old key.

### 5.2. Simulating Rotation with a Dispatcher

A test server can hold the active JWKS in an `AtomicReference`:

~~~java
AtomicReference<JWKSet> currentJwks =
        new AtomicReference<>(new JWKSet(keyA.toPublicJWK()));

identityServer.setDispatcher(new Dispatcher() {
    @Override
    public MockResponse dispatch(RecordedRequest request) {
        if ("/oauth2/jwks".equals(request.getPath())) {
            return new MockResponse()
                .setHeader("Content-Type", "application/json")
                .setHeader("Cache-Control", "public, max-age=5")
                .setBody(currentJwks.get().toString());
        }
        return new MockResponse().setResponseCode(404);
    }
});
~~~

Inside a test, swap the JWKS:

~~~java
currentJwks.set(new JWKSet(
    keyA.toPublicJWK(),
    keyB.toPublicJWK()));
~~~

Then sign a new token using private key B with its own `kid`. When the decoder refreshes the JWKS per its cache/unknown-kid behavior, token B must verify once public key B is published.

This snippet illustrates a stateful fixture; `keyA`/`keyB` are freshly generated test JWKs. For deterministic tests, configure a cache with a known TTL or create a fresh decoder per scenario. Do not rely on `Thread.sleep(5000)` hoping the cache expires on its own.

### 5.3. Testing Rotation Across Milestones

| Scenario | JWKS | Token | Expected Outcome |
| --- | --- | --- | --- |
| Before rotation | A | token-A | Passes |
| JWKS with overlap | A + B | token-A | Passes |
| JWKS with overlap | A + B | token-B | Passes once decoder learns key B |
| After overlap | B | token-B | Passes |
| After overlap | B | unexpired token-A | Fails if A was removed and cache refreshed; indicates overlap is too short if token should still be accepted |
| Temporary JWKS endpoint error | Cache holds A | token-A | Depends on cache validity; verify the configured policy without assuming always-pass or always-fail |

### 5.4. Understanding Caching When Writing Tests

The decoder may cache the JWK Set. Therefore:

- Changing the JWKS server response does not mean the decoder immediately sees the new key.
- A token with an unknown `kid` may trigger a refresh depending on library version and cache implementation.
- A new decoder can fetch the updated key set even while an older decoder continues using its cached copy.
- HTTP `Cache-Control` and decoder-configured caching must be tested against the actual stack in use.
- Tests should control cache/TTL explicitly or use fresh decoders to isolate scenarios.

Do not assert a hardcoded number of JWKS requests unless the cache policy is explicitly configured. If you need to test cache behavior, configure a cache with clock/test control or test the caching layer directly.

### 5.5. Verifying Private Keys Are Not Published

Beyond verifying token signing, the test fixture can assert that the public JWKS JSON contains no private parameters:

~~~java
String jwks = new JWKSet(keyA.toPublicJWK()).toString();

assertThat(jwks).doesNotContain("\"d\"");
assertThat(jwks).doesNotContain("\"p\"");
assertThat(jwks).doesNotContain("\"q\"");
~~~

This is a fixture safeguard; the public JWKS must contain only public material. Never serialize a JWK containing private parameters onto the test endpoint just for encoder convenience.

## 6. Building a Token Introspection Server for Opaque Tokens

An opaque access token does not carry locally verifiable claims like a JWT. The Resource Server sends the token to an **introspection endpoint** so the Authorization Server returns metadata describing the token's status and privileges.

RFC 7662 specifies an HTTP POST introspection request with a `token` form parameter. The endpoint typically requires client authentication; the response includes `active` and may contain `scope`, `sub`, `aud`, `iss`, `exp`, `client_id`, and other contract claims.

Illustrative request:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

token=opaque-token-value
~~~

Active response:

~~~json
{
  "active": true,
  "scope": "orders.read orders.cancel",
  "client_id": "shop-web",
  "sub": "alice-42",
  "aud": ["orders-api"],
  "iss": "https://identity.example.test/realms/shop",
  "exp": 1893459600,
  "username": "alice"
}
~~~

Inactive response:

~~~json
{
  "active": false
}
~~~

`active=false` means the token is not considered active by the Authorization Server. An Authentication must never be created merely because the request carries a token string.

### 6.1. Configuring an Opaque Token Resource Server

Servlet example:

~~~java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer -> resourceServer
            .opaqueToken(opaque -> opaque
                .introspectionUri(
                    "http://127.0.0.1:49152/oauth2/introspect")
                .introspectionClientCredentials(
                    "orders-api-test", "test-secret")))
        .build();
}
~~~

The URL and client credentials in this example are for tests only. In a real application, retrieve secrets from a secret manager or use the appropriate client authentication mechanism.

Spring Security also lets you provide a custom `OpaqueTokenIntrospector` bean. This is useful when wrapping the default introspector to enforce additional policy checks, emit metrics, or map principals per contract.

### 6.2. Stubbing the Introspection Response

With MockWebServer:

~~~java
identityServer.enqueue(new MockResponse()
    .setHeader("Content-Type", "application/json")
    .setBody("""
        {
          "active": true,
          "scope": "orders.read",
          "sub": "alice-42",
          "aud": ["orders-api"],
          "iss": "https://identity.example.test/realms/shop"
        }
        """));
~~~

In a test, send the opaque token:

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-token-value"))
    .andExpect(status().isOk());
~~~

If the introspector is configured properly, Spring sends a POST to the endpoint, reads the response, and creates an Authentication for the request. Inspect the received request to ensure the right token and client authentication were sent.

### 6.3. Verifying Form Body and Client Authentication

You can capture and inspect the request:

~~~java
RecordedRequest request = identityServer.takeRequest();

assertThat(request.getMethod()).isEqualTo("POST");
assertThat(request.getPath()).isEqualTo("/oauth2/introspect");
assertThat(request.getHeader("Content-Type"))
    .contains("application/x-www-form-urlencoded");
assertThat(request.getBody().readUtf8())
    .contains("token=opaque-token-value");
~~~

If client authentication uses HTTP Basic, verify the header per the test contract. Never hardcode production secrets in test assertions or log output. Some AS implementations support `client_secret_post`, `private_key_jwt`, or mTLS; tests should reflect the method used by your ClientRegistration/introspector.

### 6.4. Scopes and Authorities from Introspection

Spring Security by default converts scopes in the introspection principal into authorities prefixed with `SCOPE_`. Example:

~~~json
{
  "active": true,
  "scope": "orders.read orders.cancel"
}
~~~

Expected authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

If the Authorization Server returns a different permission claim or nested structure, use a custom `OpaqueTokenIntrospector`/principal mapper per contract. Do not assume every field in an introspection response automatically becomes a GrantedAuthority.

### 6.5. Audience and Issuer with Opaque Tokens

Do not assume every introspector automatically enforces the same issuer/audience checks as a JWT decoder. The introspection response provides claims per the AS contract; if the Resource Server needs to enforce a specific `iss`, `aud`, token profile, or tenant, verify the behavior of the active introspector and add an explicit wrapper/validator when needed.

Conceptual wrapper example:

~~~java
final class ContractOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    ContractOpaqueTokenIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        String issuer = principal.getAttribute("iss");
        if (!"https://identity.example.test/realms/shop".equals(issuer)) {
            throw new BadOpaqueTokenException("Unexpected token issuer");
        }

        Object audience = principal.getAttribute("aud");
        if (!(audience instanceof Collection<?> values)
                || !values.contains("orders-api")) {
            throw new BadOpaqueTokenException("Unexpected token audience");
        }
        return principal;
    }
}
~~~

This is an illustrative contract wrapper; imports include `OpaqueTokenIntrospector`, `OAuth2AuthenticatedPrincipal`, `BadOpaqueTokenException`, and `Collection`. If the AS does not return issuer/audience, agree on how resource binding is established with the AS rather than inferring it solely from `active=true`.

### 6.6. Introspection Negative Cases

| Scenario | Response/Server Behavior | Expected Outcome |
| --- | --- | --- |
| Active token | `active=true`, sufficient scope | Authentication succeeds |
| Inactive token | `active=false` | 401 |
| Missing `active` in response | Violates RFC 7662 contract | Rejected |
| Malformed JSON response | Unparseable body | Authentication fails |
| Invalid client credentials | 401/403 from introspection server | Resource Server does not authenticate token |
| Endpoint 404/500 | HTTP error | Request is not treated as authenticated |
| Timeout/connection refused | Unreachable | Fails closed per error handling |
| Missing scope | Active but lacks authority | Authentication may succeed; endpoint returns 403 |
| Wrong audience | Active but not intended for this API | Custom contract validator must reject if policy requires |
| Expired token | AS returns inactive or custom policy rejects | 401 |

Never return `active=true` unconditionally for every token in test fixtures. That turns the introspection server into an overly permissive fake trust provider and masks token transmission bugs.

## 7. Testing Introspection Failures and Revocation

Introspection has a characteristic that differs from local JWT validation: the Resource Server depends on an external HTTP service to know token status. Tests must simulate both business outcomes and infrastructure failures.

### 7.1. Inactive and Non-Existent Tokens

When a token is no longer valid, the AS returns:

~~~json
{
  "active": false
}
~~~

The Resource Server must reject authentication. Use two distinct opaque tokens in tests:

~~~text
opaque-active-001   -> active=true
opaque-revoked-002  -> active=false
~~~

A dispatcher can choose responses based on the form body:

~~~java
identityServer.setDispatcher(new Dispatcher() {
    @Override
    public MockResponse dispatch(RecordedRequest request) {
        if (!"/oauth2/introspect".equals(request.getPath())) {
            return new MockResponse().setResponseCode(404);
        }

        String body = request.getBody().readUtf8();
        if (body.contains("token=opaque-active-001")) {
            return jsonResponse("""
                {"active":true,"scope":"orders.read","sub":"alice-42"}
                """);
        }
        if (body.contains("token=opaque-revoked-002")) {
            return jsonResponse("{\"active\":false}");
        }
        return jsonResponse("{\"active\":false}");
    }
});
~~~

`jsonResponse` is a test helper returning a `MockResponse` with `Content-Type: application/json`. In real code, parse the form body using a URL-encoded decoder rather than substring matching if tokens can contain characters requiring encoding.

### 7.2. Revocation Between Two Requests

Testing a token lifecycle:

1. Introspection server returns `active=true`.
2. Send the first request; Resource Server allows it.
3. Switch the test server state to `active=false`.
4. Send a second request with the same opaque token.
5. Verify the second request is rejected according to the introspector/cache behavior in use.

Do not assume a server response change is immediately visible if the application uses a custom introspection cache. If caching is present, tests must verify TTL, invalidation, and revocation delay. If there is no cache, each request typically triggers an introspection call; verify with the request recorder.

### 7.3. Transport and HTTP Errors

Cases that should be modeled explicitly:

- HTTP 401/403 from the introspection endpoint due to invalid client authentication.
- HTTP 404 due to wrong endpoint URI.
- HTTP 429 due to rate limiting.
- HTTP 500/503 due to temporary Authorization Server failure.
- Responses slower than the client timeout.
- Connection reset or socket closed mid-response.
- Truncated JSON or mismatched field types.

Never turn an introspection failure into a default principal. If the Resource Server cannot verify an opaque token, the request must not be treated as authenticated. Public error responses should expose minimal detail, while internal logs/metrics distinguish transport errors, client authentication failures, and inactive tokens.

### 7.4. Timeouts Must Be Bounded

Timeout tests should enforce clear bounds on both the introspector's HTTP client and the test suite:

~~~java
identityServer.enqueue(new MockResponse()
    .setHeadersDelay(2, TimeUnit.SECONDS)
    .setHeader("Content-Type", "application/json")
    .setBody("{\"active\":true,\"scope\":\"orders.read\"}"));
~~~

This example simulates a server returning headers slowly. The client timeout must be shorter than the delay to exercise timeout failure handling. Do not use long delays for testing; a couple of seconds is enough, and the test method should have its own timeout so the suite never hangs.

### 7.5. Do Not Log Real Tokens in Request Logs

MockWebServer retains request bodies for assertions. Use dummy tokens in test fixtures, never access tokens from dev/staging environments. If the test framework prints requests on failure, avoid meaningful token values or real secrets in output.

## 8. Using Testcontainers When a Real IdP Is Needed

MockWebServer/WireMock are ideal for testing HTTP contracts and controlled failure cases. When you need to verify interactions against a real Authorization Server implementation, you can run an IdP in Testcontainers.

Skeleton example:

~~~java
@Testcontainers
@SpringBootTest
class RealIdentityProviderIntegrationTest {

    @Container
    static final GenericContainer<?> identityProvider =
        new GenericContainer<>("example-identity-server:test")
            .withExposedPorts(8080)
            .waitingFor(Wait.forHttp("/health/ready"));

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.security.oauth2.resourceserver.jwt.issuer-uri",
            RealIdentityProviderIntegrationTest::issuer);
    }

    static String issuer() {
        return "http://" + identityProvider.getHost() + ":"
            + identityProvider.getMappedPort(8080) + "/realms/test";
    }
}
~~~

This is a skeleton; image, port, health endpoint, and issuer path must match the chosen IdP. Do not treat this placeholder image as a ready-to-run IdP. You must provision the test realm/client/keys/metadata inside the container before the Spring context starts.

Testcontainers is valuable when verifying an IdP's real discovery endpoint, how it publishes JWKS and `kid`, the token profile/claims it emits, introspection client authentication, and real key rotation/revocation features.

The downside is slower execution and dependence on Docker/image availability. You do not need to boot a real container for every negative test case; keep detailed HTTP failure testing in MockWebServer/WireMock.

## 9. Test Resource Lifecycle and Spring ApplicationContext

An integration test may manage multiple resources simultaneously:

| Resource | Initialization | Cleanup |
| --- | --- | --- |
| MockWebServer/WireMock | BeforeAll/JUnit extension | Shutdown/stop |
| Testcontainers | Container extension | Stop container |
| RSA/EC key pair | Test fixture setup | Release references; never publish private key |
| Mutable JWKS state | BeforeEach or fixture reset | Reset to initial key set |
| Introspection response state | BeforeEach | Reset token status/responses |
| Executor/scheduler | Test configuration | Shutdown and await termination |
| Temporary directory | JUnit `@TempDir` | Cleaned up automatically by JUnit |
| HTTP client/connection pool | Spring bean/test fixture | Closed when context terminates |
| Cache | Test setup | Clear or instantiate fresh cache |

### 9.1. Using Appropriate Lifecycle Hooks

Typically:

- `@BeforeAll`: start class-shared server, create key fixtures.
- `@BeforeEach`: reset JWKS/introspection scenario, request logs, and mutable state.
- `@AfterEach`: clear per-test state if not reset at the next start.
- `@AfterAll`: stop servers, containers, and executors.

A JUnit extension can manage start/stop to reduce boilerplate in test classes. Whether using extensions or hooks, ensure resource cleanup runs even when assertions fail or tests throw exceptions.

### 9.2. Spring Test Context Caching and Server Lifetime

Spring Test may cache an ApplicationContext for reuse across test classes with compatible configurations. This creates a risk: one test class shuts down MockWebServer in `@AfterAll`, while the cached context is reused by another test class whose decoder/introspector still points to the closed port.

Remedies:

- Keep the test server alive using a shared fixture whose lifecycle aligns with the context cache.
- Use a dedicated context and mark `@DirtiesContext` when dependencies must shut down with the context.
- Use a JUnit extension that manages resources at the matching scope.
- Never stop a server before beans/clients inside the context finish using it.

Do not assume `@AfterAll` always means the Spring context has been destroyed. Test server lifetime and context lifetime must be designed together.

### 9.3. Isolating State During Parallel Execution

Parallel test execution can cross-contaminate:

- MockWebServer response queues.
- JWKS state undergoing rotation.
- Introspection active/revoked token state.
- Request recorders/assertions.
- Shared decoder caches.
- Ports and test properties.

Prefer per-class or per-test servers with independent state. If sharing a server, route responses by path and token/test identifier; never depend on request ordering. You can disable parallel execution for test groups using mutable singleton fixtures if safe isolation is not yet in place.

### 9.4. Avoiding Order-Dependent Tests

Do not write:

~~~java
server.enqueue(activeResponse);
server.enqueue(inactiveResponse);
~~~

and assume test A always runs before test B. When JUnit reorders tests or runs them in parallel, responses can be consumed by the wrong test. Use a dispatcher keyed on request body/path or reset queues/state in `@BeforeEach`.

### 9.5. Readiness and Cleanup

A started test server does not guarantee the simulated service is ready. When running containers:

- Use a health/readiness check with a timeout.
- Wait until metadata/JWKS endpoints actually return responses.
- Only then initialize the Spring context.
- When finished, shut down servers/containers and executors.

Never use an infinite loop or a fixed `Thread.sleep()` to wait. Readiness checks must have bounded timeouts and report clearly which endpoint failed to become ready.



## 10. End-to-End JWT Integration Scenario

A complete JWT integration test should verify the HTTP request, discovery/JWKS, and endpoint authorization together. Example flow:

1. Start MockWebServer on a dynamic port.
2. Generate RSA key pair A and a public JWKS containing key A.
3. Stub metadata with the exact issuer and `jwks_uri` pointing to the server.
4. Stub the JWKS endpoint to return public key A.
5. Configure Spring Resource Server with the dynamic `issuer-uri`.
6. Sign a JWT with private key A, matching `kid`, and valid issuer/audience/scope.
7. Send the JWT via MockMvc in the Authorization header.
8. Verify the response succeeds and metadata/JWKS requests hit the server.
9. Send a token signed by key B or with the wrong audience and verify rejection.
10. Shut down the Spring context/test server per the designed lifecycle.

### 10.1. JWT Request Test Example

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class JwksBackedResourceServerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsTokenSignedByKeyPublishedInJwks() throws Exception {
        String token = tokenSignedByKeyA();

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk());
    }

    @Test
    void rejectsTokenSignedByKeyNotPublishedInJwks() throws Exception {
        String token = tokenSignedByKeyB();

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }
}
~~~

The `tokenSignedByKeyA()` and `tokenSignedByKeyB()` helpers sign JWTs with the same claim contract but different private keys. The JWKS server publishes only public key A. This test verifies signature validation against JWKS, not just claim mapping.

### 10.2. Testing Discovery Metadata Mismatch

Set metadata `issuer` to a value different from the configured issuer, then initialize the decoder or call a protected endpoint. Expect discovery/decoder initialization to fail; do not alter the `iss` claim inside the token to hide the mismatch.

Separately test `jwks_uri` pointing to a 404 or timing-out endpoint. This separates discovery errors from token verification errors.

### 10.3. Testing Metadata Discovery and Direct JWKS Separately

Do not use a single test to claim both paths work:

- Test A uses `issuer-uri` and exercises metadata discovery.
- Test B uses `jwk-set-uri` directly while still attaching an issuer validator if the contract requires it.

When test A fails while test B passes, the bug likely lies in the discovery path or metadata response. When both fail, inspect JWKS, signing keys, and token claims.

## 11. End-to-End Opaque Token Integration Scenario

A complete opaque token test should:

1. Start an introspection server on a dynamic port.
2. Configure the Resource Server with the test introspection URI and client authentication.
3. Stub an `active=true` response with appropriate scope/audience/issuer.
4. Send the opaque token in the Authorization header.
5. Verify the introspection request is a POST, the form body contains the expected token, and client auth is correct.
6. Verify scopes map to the required authorities.
7. Switch the token to inactive and resend.
8. Verify the Resource Server rejects it.

### 11.1. Active Token Accepted

~~~java
@Test
void acceptsActiveOpaqueTokenWithRequiredScope() throws Exception {
    introspectionFixture.respondFor(
        "opaque-active-001",
        """
        {
          "active": true,
          "scope": "orders.read",
          "sub": "alice-42",
          "aud": ["orders-api"],
          "iss": "https://identity.example.test/realms/shop"
        }
        """);

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer opaque-active-001"))
        .andExpect(status().isOk());
}
~~~

`introspectionFixture` is a test-defined fixture that configures the dispatcher/state; it is not a built-in Spring Security class.

### 11.2. Inactive Token Rejected

~~~java
@Test
void rejectsInactiveOpaqueToken() throws Exception {
    introspectionFixture.respondFor(
        "opaque-revoked-002",
        "{\"active\":false}");

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer opaque-revoked-002"))
        .andExpect(status().isUnauthorized());
}
~~~

### 11.3. Active Token Missing Scope

~~~java
@Test
void activeOpaqueTokenWithoutRequiredScopeIsForbidden()
        throws Exception {
    introspectionFixture.respondFor(
        "opaque-profile-only",
        """
        {
          "active": true,
          "scope": "profile.read",
          "sub": "alice-42",
          "aud": ["orders-api"]
        }
        """);

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer opaque-profile-only"))
        .andExpect(status().isForbidden());
}
~~~

An active token means authentication can succeed; missing scope is an authorization failure. Do not assert 401 for every case where an introspection response does not allow endpoint access.

## 12. Diagnosing Failures in Test Servers

| Symptom | Common Cause | Investigation Path |
| --- | --- | --- |
| Context fails to start with `issuer-uri` | Wrong discovery URL, metadata server not ready, issuer mismatch | Request path, response body, exact issuer |
| JWT always 401 despite valid claims | JWKS lacks matching key, wrong `kid`, invalid signature, disallowed alg | Inspect JOSE header, JWKS public key, key ID |
| First JWT passes, new-key token fails | Decoder still caches old JWKS or new key not yet published | Cache TTL, refresh behavior, overlap set |
| Old token fails immediately after rotation | Old key removed too early or caches/instances out of sync | Token expiry, skew, overlap window |
| Metadata passes but no JWKS request appears | Decoder not invoked yet or using cached keys | Trigger protected request, inspect decoder lifecycle |
| JWKS requested repeatedly | Cache unconfigured/expired, multiple decoder instances | Cache scope, context count, key selection |
| Opaque token always 401 | `active=false`, wrong introspection URI/client auth, error response | Recorded POST, body, auth scheme, response |
| Opaque token passes despite wrong scope | Route does not require scope or test stub granted wrong scope | Security rule, introspection fixture |
| Revoked token still passes | Introspection cache still valid or fixture response unchanged | Cache TTL/invalidation, request recorder |
| Tests pass alone but fail in full suite | Shared server/state/cache or premature cleanup | Context cache, parallel mode, dispatcher reset |
| Test hangs | Server fails to respond or `takeRequest()` blocks forever | HTTP timeouts, bounded request waits, server readiness |
| Flaky CI failures | Fixed port, startup race, time-dependent readiness | Dynamic port, lifecycle hooks, readiness timeouts |

## 13. Security Principles When Building Identity Test Servers

### 13.1. Use Only Test Keys and Tokens

- Generate dedicated private keys for tests.
- The JWKS endpoint returns only public keys.
- Test tokens use dummy subjects and short lifetimes.
- Never read tokens/private keys from production environment variables.
- Never print Authorization headers or introspection request bodies into logs on test failure.

### 13.2. Metadata/JWKS URLs Must Stay Within the Trust Boundary

The Resource Server must never derive `jwks_uri` from an unverified JWT or caller-controlled data. Issuer and metadata sources must be configured/allowlisted. In tests, URLs point to loopback/dynamic ports managed by the test fixture.

When running test containers, use an isolated network and never expose the test identity server to public networks. If tests require HTTPS, use dedicated test certificates and trust stores; never disable TLS validation just to make requests pass.

### 13.3. Test Fail-Closed Behavior

The following failures must never result in successful authentication:

- Untrusted metadata or issuer mismatch.
- Unreachable JWKS with no valid cache entry.
- Key not found or invalid signature.
- Inactive or invalid introspection response.
- Unavailable introspection endpoint.
- Required claims failing contract validation.

If the cache still holds a valid key set, behavior during temporary JWKS endpoint failures depends on cache policy. Tests must reflect the chosen policy rather than assuming immediate fail-closed if the decoder is designed to serve from a valid cache.

## 14. Integration Verification Checklist

### Metadata

- [ ] Issuer in config, metadata, and token claim match exactly.
- [ ] Discovery path matches OIDC Discovery/RFC 8414 and the issuer path.
- [ ] Metadata contains a valid `jwks_uri`.
- [ ] Metadata 404, 500, timeout, malformed JSON, and issuer mismatch are tested.
- [ ] Separate tests exist for discovery and direct JWKS URI.

### JWKS/JWT

- [ ] Dedicated test key pair generated.
- [ ] JWKS contains only public keys.
- [ ] Tokens are signed with the right private key and carry matching `kid`.
- [ ] Untrusted keys, missing/wrong `kid`, empty JWKS, and disallowed algorithms are tested.
- [ ] Caching and key rotation with an overlap window are tested.
- [ ] JWKS updates are not assumed to take effect instantaneously.
- [ ] Both old and new tokens are tested during the rotation phase.

### Introspection

- [ ] Request is a POST form with the token parameter.
- [ ] Client authentication matches configuration.
- [ ] Both `active=true` and `active=false` responses are tested.
- [ ] Missing `active`, malformed JSON, HTTP errors, and timeouts are tested.
- [ ] Scope mapping is verified.
- [ ] Issuer/audience/tenant are validated per contract where needed.
- [ ] Revocation and cache invalidation are tested.

### Resource Lifecycle

- [ ] Dynamic ports are used.
- [ ] Server is ready before the Spring context initializes.
- [ ] Test state is reset between tests.
- [ ] No execution-order dependency or shared response queues.
- [ ] Servers/containers/executors are closed on completion.
- [ ] Spring ApplicationContext caching and server lifetime are coordinated.
- [ ] Parallel tests are isolated.
- [ ] Bounded timeouts are set for HTTP requests and readiness checks.

## 15. Practical Scenarios

**A.** The Resource Server uses `issuer-uri`, but the test only stubs `/oauth2/jwks`. Does the test prove metadata discovery?

No. You must stub the discovery metadata endpoint returning issuer and `jwks_uri`, then verify the decoder actually calls JWKS.

**B.** A token is validly signed by key A, but the `kid` header says key B. Should it be accepted because public key A is in the JWKS?

No. `kid` tells the decoder which key to select. If no key matches the header, the token must be rejected.

**C.** The JWKS endpoint added key B, yet token B still gets 401 immediately afterward. What is a likely cause?

The decoder is still serving a stale cached JWK Set or has not refreshed yet. Check cache TTL, unknown-key refresh behavior, and ensure key B is published before the AS begins signing with B.

**D.** Can key A be removed from the JWKS as soon as signing switches to B?

Not if tokens signed with A are still valid and must remain accepted. Keep the old key for an overlap window accounting for token lifetime, skew, caching, and propagation.

**E.** Introspection returns `active=true` with only `profile.read`; the endpoint requires `SCOPE_orders.read`. What should happen?

Authentication can succeed, but authorization must return 403 due to missing scope.

**F.** The introspection endpoint times out. Can the Resource Server allow the request since a token was supplied?

No. Without verifying the opaque token, an authenticated principal cannot be created from the raw token string.

**G.** A test class stops MockWebServer in `@AfterAll`, but another class reuses the Spring context and sends requests to the old port. Why?

Spring Test may cache the ApplicationContext after the first class finishes. The server lifetime is shorter than the context lifetime. Use a shared fixture or dirty the context appropriately before stopping the server.

**H.** Tests pass individually but fail in parallel because active/inactive responses get swapped. What needs to change?

Use a dispatcher keyed by token/path, dedicated fixtures, or state resets; never share an order-dependent response queue.

**I.** Is Testcontainers required for every JWKS/introspection test?

No. MockWebServer/WireMock are suited for contract and negative cases. Use an IdP container when verifying real provider behavior.

**J.** Can the public JWKS include the private RSA parameter `d` to make signing tokens easier in tests?

No. The encoder holds the private key inside the fixture; the JWKS endpoint must publish only `toPublicJWK()`.

---

## Conclusion

Test JWKS, metadata, and introspection servers verify the real HTTP boundary between a Spring Security Resource Server and an Authorization Server. For JWTs, tests must stand up metadata discovery or a JWKS URI, generate dedicated key pairs, publish public JWKs, sign tokens, and verify signatures, `kid`, issuer, audience, and key rotation/caching. For opaque tokens, tests must simulate RFC 7662 POST requests, client authentication, active/inactive responses, scope mapping, revocation, and transport failures.

Test server lifecycle is equally part of correctness. Use dynamic ports, bounded-timeout readiness checks, isolated fixtures, state resets, and explicit cleanup, while aligning server lifetime with Spring's ApplicationContext cache. Tests must distinguish token failures from infrastructure errors, avoid execution-order dependencies, and never allow an unavailable dependency to turn into successful authentication.

## References

1. [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
2. [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
3. [Spring Security — Testing OAuth 2.0 Resource Servers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
4. [OpenID Connect Discovery 1.0 — Provider Configuration](https://openid.net/specs/openid-connect-discovery-1_0.html)
5. [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html)
6. [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html)
7. [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html)
8. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)
9. [OkHttp MockWebServer](https://square.github.io/okhttp/5.x/mockwebserver/)
10. [WireMock Documentation](https://wiremock.org/docs/)
11. [Testcontainers for Java](https://java.testcontainers.org/)

