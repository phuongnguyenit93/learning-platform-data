# Keeping Tokens, Keys, Error Responses, and Negative Test Cases as a Baseline

When upgrading Spring Security, Spring Boot, or OAuth 2.0 / OIDC Resource Server configuration, an application may still start up and return HTTP 200 on the happy path while having altered how it validates tokens or handles errors. For example: an audience validator is dropped, an older key stops being recognized, an expired token is accepted, a 401 response loses its Bearer challenge, or a request missing a scope turns into 401 instead of 403.

To catch these shifts, maintain a reproducible **regression baseline** composed of four parts:

1. **Test token corpus:** JWT and opaque tokens representing valid, boundary, and rejected cases.
2. **Test key set:** private/public keys, JWKS, and stable key IDs for signing, verification, and rotation tests.
3. **Expected error responses:** status codes, headers, Bearer challenges, and response bodies per API contract.
4. **Negative test cases:** proving invalid tokens or insufficient permissions are blocked before business operations run.

The baseline is the application's behavioral contract. Whenever dependencies or configuration change, run the same vector suite against both the old and new configurations, compare outcomes, and investigate every intentional or unintended difference. Never build a baseline from production tokens or real secrets; all fixtures must use separately managed test data.

## 1. What Does the Baseline Protect?

A single migration can touch multiple layers:

- How Bearer tokens are extracted from HTTP requests.
- How JWTs are decoded and signatures are verified.
- How the JWK Set is fetched, cached, and refreshed.
- How issuer, audience, timestamps, and algorithms are validated.
- How opaque tokens are introspected and metadata maps to principals/authorities.
- How requests are allowed or denied.
- How exceptions map to HTTP statuses, headers, and bodies.
- How filter chains, method security, and custom handlers are registered.

A baseline does not test only a single succeeding endpoint. It must also capture every case the application **must reject**. A change that rejects valid tokens is an availability regression; a change that accepts invalid tokens is a severe security regression.

## 2. Four Layers of a Test Vector

Each vector should specify the input, verification fixture, authentication outcome, and HTTP outcome:

| Layer | Contents | Example |
| --- | --- | --- |
| Input | Token, headers, request method/path/body | JWT with wrong audience calling `GET /api/orders` |
| Verification fixture | Key/JWKS, issuer, clock, introspection response | Test JWKS containing a public key with a fixed `kid` |
| Expected security result | Authenticated, rejected, authorization denied | Rejected due to audience mismatch |
| Expected API result | Status, challenge, body, and side effects | 401, Bearer `invalid_token`, service not invoked |

A vector needs enough detail for someone else to rerun it without guessing which key signed the token, what time the clock was at, or which chain handled the endpoint.

## 3. Distinguishing Test Tokens from Production Tokens

Never pull real access tokens from browsers, logs, databases, or staging environments into fixtures. Real tokens may still be valid, contain PII, and depend on Authorization Server state.

Use purpose-built fixtures:

- JWTs signed with a test-only private key.
- Matching public JWK/JWKS used in decoder tests.
- Opaque tokens as synthetic strings invalid at any real IdP.
- Introspection responses mocked per test case.
- Synthetic subjects, tenants, client IDs, and audiences.
- Clock and key rotation controlled directly in tests.

A fixture can be committed to the repository if it contains only test keys and synthetic data. Name it clearly such as `test-only` so it is never mistaken for runtime configuration.

## 4. Defining the Token Corpus by Purpose

You do not need hundreds of random tokens. Build a small corpus covering critical verification boundaries:

| Group | Representative Vector | Expected Result |
| --- | --- | --- |
| Valid | Valid signature, issuer, audience, timestamps | Authentication success |
| Expired | `exp` earlier than test clock | Rejected |
| Not yet valid | `nbf` later than test clock | Rejected |
| Wrong issuer | `iss` outside trust configuration | Rejected |
| Wrong audience | `aud` lacks current resource | Rejected |
| Bad signature | Valid payload signed with a different key | Rejected |
| Unknown key | `kid` absent from trusted JWKS | Rejected or refreshed then rejected |
| Unsupported algorithm | `alg` outside allowlist | Rejected |
| Missing required claim | Claim required by token profile is absent | Rejected per policy |
| Insufficient scope | Valid token lacking authority | Authentication success, authorization denied |
| Wrong tenant/owner | Right scope but invalid domain access | Authorization denied |
| Opaque inactive | Introspection returns `active=false` | Rejected |
| Opaque active, no scope | `active=true` without required permission | Authenticated, authorization denied |
| Malformed credential | Invalid Bearer value/JWT format | Rejected |

Separate invalid tokens from valid tokens lacking permissions. The two cases normally produce different statuses and require different metrics and runbooks.

## 5. Stable Vector Naming

Use IDs containing no sensitive data and independent of execution time:

```text
jwt.valid.orders-reader
jwt.expired.orders-reader
jwt.not-before.future
jwt.issuer.untrusted
jwt.audience.billing-only
jwt.signature.wrong-key
jwt.key.unknown-kid
jwt.algorithm.disallowed
jwt.scope.missing-write
jwt.subject.missing
opaque.active.orders-reader
opaque.inactive
opaque.active.scope-empty
opaque.introspection.invalid-client
opaque.introspection.timeout
```

Vector IDs are test fixture names, not mandatory metric labels. When renaming fixtures, keep a mapping or note the migration so regression history remains readable.

Never embed real subjects, emails, token values, or sensitive private key identifiers in vector names.

## 6. Fixing Time so Token Tests Are Reproducible

JWTs contain `NumericDate` claims such as `exp`, `nbf`, and `iat`. If tests call `Instant.now()` in multiple places, results can vary by run time, timezone, clock skew, or CI speed.

Choose a fixed instant:

```java
static final Instant TEST_NOW =
    Instant.parse("2030-01-15T10:00:00Z");

static final Clock TEST_CLOCK =
    Clock.fixed(TEST_NOW, ZoneOffset.UTC);
```

Construct tokens relative to that instant:

```java
Instant issuedAt = TEST_NOW.minusSeconds(60);
Instant expiresAt = TEST_NOW.plusSeconds(300);
Instant notBefore = TEST_NOW.minusSeconds(30);
```

Expired tokens can set `exp` before `TEST_NOW`; not-yet-valid tokens set `nbf` after `TEST_NOW`. Use the clock skew declared in the validator to test boundaries immediately before, exactly at, and immediately after acceptance limits.

Never use the CI machine's wall clock as an implicit oracle. If the decoder/validator supports injecting `Clock`, pass the test clock; otherwise design fixtures with wide enough margins and document tolerances explicitly.

## 7. Generating Test JWTs with a Stable Key Pair

A clean approach is creating a test-only RSA key pair with a fixed `kid` and sharing it between encoder and decoder fixtures.

Example with Nimbus JOSE + JWT:

```java
RSAKey signingJwk = new RSAKey.Builder((RSAPublicKey) keyPair.getPublic())
    .privateKey((RSAPrivateKey) keyPair.getPrivate())
    .keyID("test-rsa-2026-a")
    .build();

JWKSource<SecurityContext> jwkSource =
    new ImmutableJWKSet<>(new JWKSet(signingJwk));

JwtEncoder encoder = new NimbusJwtEncoder(jwkSource);
```

Exact imports and generics must match your project's Nimbus/Spring Security versions. The rule is that the private key is used only to sign fixtures; decoders or JWKS servers receive only the public key.

Do not generate a fresh key pair inside every test when the goal is stable signature/JWK comparison. Dedicated fixtures can test key rotation, yet each key should keep a fixed `kid` and clear metadata.

## 8. Generating JWTs with Deterministic Claims

Use a factory instead of duplicating token construction in every test:

```java
JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuer("https://issuer.test/realms/shop")
    .subject("user-1001")
    .audience(List.of("orders-api"))
    .issuedAt(TEST_NOW.minusSeconds(60))
    .expiresAt(TEST_NOW.plusSeconds(300))
    .claim("scope", "orders.read")
    .claim("tenant_id", "tenant-test-a")
    .build();

JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
    .keyId("test-rsa-2026-a")
    .build();

String token = encoder.encode(
    JwtEncoderParameters.from(header, claims)
).getTokenValue();
```

The factory can accept a baseline profile and mutate exactly one attribute to produce negative vectors. For example, `wrong-audience` alters only `aud`; `bad-signature` signs identical claims with a key absent from JWKS. Each test then exercises a single rejection cause.

Never mutate multiple claims at once in a single negative vector. If issuer, audience, and signature are all invalid, a passing test cannot tell you which validator actually ran.

## 9. Keeping Test Key Material and JWKS Readable

A practical fixture layout:

```text
src/test/resources/security-baseline/
  keys/
    rsa-a-private.pem
    rsa-a-public.pem
    rsa-b-private.pem
    rsa-b-public.pem
  jwks/
    jwks-a.json
    jwks-a-and-b.json
    jwks-b-only.json
  tokens/
    vectors.yml
  responses/
    unauthorized.json
    forbidden.json
    invalid-token.headers
```

Private keys belong strictly in test resources and must never be packaged into production artifacts. If organizational policy forbids committing private test keys, generate key fixtures once during test setup and retain matching public JWKS snapshots; ensure generation is deterministic or snapshots are stored for comparison.

Never use exported production keys. Never use test keys as a runtime fallback if a JWK endpoint fails.

## 10. JWKS Fixtures and `kid`

A JWKS holds public keys that the decoder selects by `kid`:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "test-rsa-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "TEST_PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
```

The modulus above is an illustrative placeholder; real fixtures must hold the public JWK derived from your test key pair. Never substitute an arbitrary modulus and expect signature verification to succeed.

`kid` helps the decoder pick the right key in the JWKS. If a token carries an unknown `kid`, the decoder may refresh the JWK Set per its cache policy and still reject it. Tests should confirm there is no fallback to another key merely because that key happens to verify a signature.

## 11. Key Rotation Sets Must Have Distinct Stages

A safe key rotation typically includes an overlap period:

1. **Before rotation:** JWKS contains only key A; token A is accepted.
2. **Overlap:** JWKS contains keys A and B; both token A and B are accepted.
3. **After retirement:** JWKS contains only key B; token B is accepted, and token A is rejected once the decoder refreshes per policy.
4. **Unknown `kid`:** a token signed by key C absent from JWKS is rejected.

Fixtures should include at least three JWKS snapshots:

```text
jwks-a.json          -> key A
jwks-a-and-b.json    -> key A + key B
jwks-b-only.json     -> key B
```

Tests must control the mock JWK endpoint/cache so refresh timing is deterministic. If a decoder is caching key A, changing the mock response to key B does not automatically mean the very next request sees the new JWKS. Make cache TTL/refresh behavior explicit instead of writing flaky timing-dependent tests.

## 12. Verifying the Algorithm Allowlist

The baseline should contain tokens signed with allowed algorithms and tokens using disallowed algorithms.

Example policy accepting only RS256:

```java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwkSetUri)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .build();
```

Production configurations can permit one or more organization-approved algorithms. Tests should confirm:
- Valid RS256 is accepted.
- Key/algorithm mismatches are rejected.
- Unsigned tokens or disallowed `alg` values are rejected.
- Weak algorithms are never enabled automatically just to accommodate legacy tokens.

Never reuse a single key across multiple purposes or algorithms if the security profile requires key separation.

## 13. Baseline for Issuer and Audience

A JWT with a valid signature can still belong to the wrong issuer or resource.

Vectors should include:

| Vector | `iss` | `aud` | Outcome |
| --- | --- | --- | --- |
| Valid | Trusted issuer | `orders-api` | Accept |
| Wrong issuer | Different issuer | `orders-api` | Reject |
| Wrong audience | Trusted issuer | `billing-api` | Reject |
| Missing audience | Trusted issuer | None | Reject if required by profile |
| Multiple audience | Trusted issuer | `orders-api` + `billing-api` | Per published policy |

Preserve exact issuer strings, trailing slashes, and audience identifiers in fixtures. Nearly identical strings still differ under exact matching.

When using `JwtValidators.createDefaultWithIssuer`, attach a dedicated audience validator when required by the API. The baseline must verify the real decoder enforces that validator, not merely test a standalone helper.

## 14. Baseline for Timestamps and Clock Skew

Test boundary conditions:

- `exp` older than `TEST_NOW` beyond clock skew: reject.
- `exp` within clock skew: per validator policy.
- `exp` right at the acceptance boundary: verify semantics via tests.
- `nbf` greater than `TEST_NOW` beyond clock skew: reject.
- `iat` in the future beyond tolerance: per validator/profile.
- Unexpired token whose age exceeds maximum age: reject if policy enforces max age.

Document the clock skew in the baseline, such as 60 seconds. Never increase tolerance just to make a stale fixture pass after migration; doing so widens the token acceptance window.

## 15. Baseline for Required Claims and Authority Mapping

Build vectors covering:
- Valid `sub`.
- Missing or blank `sub`.
- Valid `scope`.
- Missing `scope`.
- Wrong-type `scope`.
- `roles` at the expected claim path.
- `roles` at an unexpected claim path.
- Valid/missing tenant claim.
- Custom claims carrying values outside the allowlist.

Verify both principal attributes and granted authorities. For example, scope `orders.read orders.write` must produce two authorities per the defined converter. A token with `profile.read` must never grant `orders.read`.

If service tokens lack a user subject, maintain a dedicated baseline profile based on client identity. Never build a test factory that always injects a default `sub`, as it would mask an Authorization Server omitting that claim in reality.

## 16. Opaque Tokens Need a Stable Corpus Too

Opaque tokens lack a JWT structure to edit claims directly. Use synthetic token strings and mock introspection responses:

```text
opaque-valid-orders-reader
opaque-inactive
opaque-valid-without-scope
opaque-active-missing-subject
opaque-client-profile
opaque-invalid-client-fixture
```

Each string is purely a test fixture identifier/value. Real Authorization Servers must never recognize or accept these strings.

Store response fixtures separately so metadata variations can be tested independently of token values. One token string can be mocked active in one test and inactive in another, though avoid reusing names in ways that imply fixed state outside the fixture.

## 17. Introspection Response Set for Opaque Tokens

Active response with sufficient permissions:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-1001",
  "aud": ["orders-api"],
  "iss": "https://issuer.test/realms/shop"
}
```

Inactive response:

```json
{
  "active": false
}
```

Active response missing scope:

```json
{
  "active": true,
  "sub": "user-1001",
  "aud": ["orders-api"]
}
```

Malformed responses or responses missing `active` require their own fixtures. Tests should distinguish confirmed inactive tokens from response contract violations if custom adapters categorize those separately.

## 18. Introspection Client Errors Are Another Vector

The Resource Server sends its own client credentials when calling the introspection endpoint. The baseline should include:

- HTTP 401 with `invalid_client`.
- HTTP 403 when the client is unauthorized to introspect.
- HTTP 429 rate limiting.
- HTTP 5xx.
- Connect/read timeouts.
- TLS/DNS failures if the test harness can simulate them.
- HTTP 200 with malformed JSON or missing `active`.

These cases must not be recorded as `active=false`. They demonstrate the Resource Server cannot verify the token due to a dependency/configuration error.

When testing against a stub endpoint, verify the client authentication method, `POST` method, `token` form field, timeouts, and response parsing. Never put production secrets into fixtures or test output.

## 19. Storing Expected Error Responses as an API Contract

A baseline should not merely state "returns 401." For each rejection case, capture the stable parts of the response:

- HTTP status.
- `WWW-Authenticate` challenge.
- `Content-Type`.
- Error code/body per API contract.
- Expected security headers.
- Whether any business side effects occurred.

For example, an invalid Bearer token may return:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
```

A valid token lacking scope may return 403 and an `insufficient_scope` challenge if the Bearer access denied handler is configured that way. Actual responses depend on Spring Security handlers and API customization. Capture the currently approved behavior as the baseline rather than assuming every application shares identical bodies and headers.

## 20. Distinguishing Missing Token, Invalid Token, and Insufficient Scope

These cases typically carry distinct semantics:

| Scenario | Authentication | Common HTTP Status | Bearer Challenge |
| --- | --- | --- | --- |
| Missing token | Unauthenticated | 401 | `Bearer` |
| Invalid/expired token | Authentication rejected | 401 | `Bearer error=invalid_token` |
| Valid token, missing scope | Authenticated | 403 | Possibly `insufficient_scope` |
| Valid token, ownership denied | Authenticated | 403 or 404 | Per API contract |

Do not reuse a single expected response across all cases. If the application uses a custom `ProblemDetail` body, keep the status and body contract consistent while never exposing tokens, subjects, or sensitive failure internals.

## 21. Normalizing Responses Before Comparison

Some response fields vary from run to run:
- `Date` header.
- Trace ID / request ID.
- Server timing.
- Nonce or correlation ID.
- JSON field ordering.
- Whitespace.
- Header order/casing.

Do not compare entire HTTP responses byte-for-byte when dynamic fields are present. Instead, normalize:
1. Keep the status code.
2. Extract contract-governed headers and compare semantics case-insensitively.
3. Parse JSON bodies and compare objects or stable fields.
4. Strip pre-identified dynamic fields.
5. Never strip `WWW-Authenticate`, error codes, or security headers just to make tests pass.

Do not over-normalize. Stripping all headers prevents the baseline from catching a missing Bearer challenge.

## 22. Golden Files and Test Vector Manifests

A simple manifest can describe the corpus:

```yaml
vectors:
  - id: jwt.valid.orders-reader
    token: jwt-valid-orders-reader
    expectedAuthentication: success
    expectedStatus: 200

  - id: jwt.expired.orders-reader
    token: jwt-expired-orders-reader
    expectedAuthentication: rejected
    expectedStatus: 401
    expectedChallenge: invalid_token

  - id: jwt.scope.missing-write
    token: jwt-valid-orders-reader
    expectedAuthentication: success
    expectedAuthorization: denied
    expectedStatus: 403

  - id: opaque.inactive
    token: opaque-inactive
    introspectionFixture: inactive.json
    expectedAuthentication: rejected
    expectedStatus: 401
```

This format is illustrative; projects can use JSON/YAML or Java test factories. Manifests must never store raw production tokens, secrets, or private keys. When tokens are generated dynamically, the manifest stores profile/claims and key fixture IDs instead of raw bearer strings.

Golden files fit stable response contracts. For headers containing dynamic values, use targeted assertions rather than full-response snapshots.

## 23. Running the Baseline Against Old and New Configurations

During migration, you can maintain two test contexts or two test applications:

- Legacy configuration running with old dependency versions in an isolated module/branch or test fixture.
- Candidate configuration running with the new versions.
- Both share the identical token corpus, key/JWKS fixtures, clock, and HTTP response assertions.
- Results export to a report containing vector ID, old outcome, and new outcome.

Never attempt to load two different Spring Security versions into the same classloader. If dependency incompatibilities prevent running both contexts in one process, execute two separate build/test jobs and diff the resulting artifacts.

## 24. Behavior Comparison Table

A comparison report might look like:

| Vector | Old Baseline | New Candidate | Disposition |
| --- | --- | --- | --- |
| `jwt.valid.orders-reader` | 200 | 200 | Unchanged |
| `jwt.expired.orders-reader` | 401 `invalid_token` | 401 `invalid_token` | Unchanged |
| `jwt.audience.billing-only` | 401 `invalid_token` | 200 | Critical regression |
| `jwt.scope.missing-write` | 403 `insufficient_scope` | 403 `insufficient_scope` | Unchanged |
| `opaque.inactive` | 401 `invalid_token` | 401 `invalid_token` | Unchanged |
| `opaque.invalid-client` | Dependency error | 401 generic | Check error telemetry/mapping |

Every difference needs a disposition:
- Expected change: approved policy or API contract update.
- Regression: unintended behavioral change.
- Environment variance: difference caused by test environment or dependency fixture.
- Unclassified: insufficient evidence; never auto-mark as passing.

Matching HTTP statuses do not prove identical behavior. For example, two 401s could represent an expired token in one run and an introspection client misconfiguration in the other. Compare internal outcome categories as well.

## 25. Rejection Cases Must Verify Business Code Does Not Execute

Asserting only 401/403 may be insufficient. Verify that services, repository writes, event publishers, or downstream clients are never invoked.

Example:

```java
@Test
void expiredTokenDoesNotReachOrderService() throws Exception {
    String expiredToken = tokenFactory.expiredOrdersReader();

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + expiredToken))
        .andExpect(status().isUnauthorized());

    verify(orderService, never()).listOrders();
}
```

For authorization denial:

```java
@Test
void readOnlyTokenCannotCreateOrder() throws Exception {
    String readOnlyToken = tokenFactory.validOrdersReader();

    mvc.perform(post("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + readOnlyToken)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"sku\":\"TEST-1\"}"))
        .andExpect(status().isForbidden());

    verify(orderService, never()).createOrder(any());
}
```

This requires a real service bean/spy and test application context. If method security lives on the service, tests must invoke through the Spring proxy. Never mock away the entire secured service and conclude its annotations are enforced.

## 26. Negative Tests for JWT

A minimum JWT test suite should verify:

1. Valid token is accepted.
2. Expired token is rejected.
3. Token before `nbf` is rejected.
4. Token with tampered signature is rejected.
5. Token signed with untrusted key is rejected.
6. Wrong issuer is rejected.
7. Wrong/missing audience is rejected per profile.
8. Disallowed algorithm is rejected.
9. Missing required subject/claim is rejected per policy.
10. Missing scope fails authorization rules.
11. Key rotation overlap succeeds.
12. Retired key is rejected after refresh per cache contract.

Each test should identify the expected failure point: decoder, validator, authority converter, or `AuthorizationManager`. This pinpoints which layer regressed.

## 27. Negative Tests for Opaque Tokens

Minimum opaque token suite:

1. Introspection `active=true` with valid metadata.
2. Introspection `active=false`.
3. Response missing `active`.
4. Wrong type for `active`.
5. Active response missing required subject.
6. Active response missing scope.
7. Active response with wrong audience.
8. Introspection client `invalid_client`.
9. Client unauthorized to introspect.
10. Timeouts, DNS/TLS errors, or upstream 5xx.
11. Malformed response body.
12. Token cache hits after status changes per freshness policy.

Use an HTTP-level mock introspection endpoint for request/credential/response-parsing tests. The `opaqueToken()` post-processor injects a mock `Authentication` and bypasses the introspection endpoint.

## 28. Preserving 401/403 and Bearer Challenges

Response assertions should check:

```java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + invalidToken))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("Bearer")));
```

For insufficient scope, when the active contract uses Bearer challenges:

```java
mvc.perform(post("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + readOnlyToken))
    .andExpect(status().isForbidden())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("insufficient_scope")));
```

Challenges may vary if the application customizes handlers. Avoid hardcoding the entire header string if parameter ordering is insignificant; assert the scheme and key parameters. If the API contract intentionally omits challenges on 403, the baseline must reflect that decided behavior.

## 29. Checking `ProblemDetail` or Custom Error Bodies

If the API returns a JSON error body:

```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "code": "AUTHENTICATION_REQUIRED"
}
```

or:

```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "code": "INSUFFICIENT_PERMISSION"
}
```

Lock down the contractually required fields: status, code, title/type, and public message. Never expose stack traces, introspection responses, token values, or client secrets in response bodies.

If the response body is not part of the public API contract, avoid overly brittle full-body snapshots that turn harmless wording tweaks into regression noise. Keep assertions meaningful to clients.

## 30. Testing `WWW-Authenticate` per Scenario

Bearer challenges are an integral part of API behavior:

- Missing credentials: `Bearer` challenge does not necessarily include an error parameter.
- Invalid/expired token: challenge normally includes `error=invalid_token`.
- Insufficient scope: access denied handler may return `error=insufficient_scope` and the required scope.
- Custom error handler: challenges must be preserved if required by the API contract.

Test challenges over real HTTP responses rather than unit-testing a helper alone. A migration can swap exception handlers and inadvertently drop the header even though the status stays 401.

Never leak internal details like the introspection client's `invalid_client` inside challenges returned to callers. That is an error between the Resource Server and Authorization Server.

## 31. `WithMockUser` Does Not Replace a Token Baseline

`WithMockUser` populates a mock `Authentication` in `SecurityContext`. It is helpful for method security and controller policy tests, yet it bypasses:
- Bearer token extraction.
- JWT signature verification.
- Issuer/audience/timestamp validation.
- JWK retrieval/rotation.
- Opaque token introspection.
- Authority conversion from token claims.

Therefore, maintain two test layers:
1. Policy tests using mock `Authentication` to verify method/domain rules.
2. Resource Server integration tests sending real Bearer token fixtures through the filter chain.

Never rely on `WithMockUser` to prove token validation still works after a dependency upgrade.

## 32. Distinguishing Decoder Tests, Filter-Chain Tests, and End-to-End Tests

| Test Type | What Is Tested | Suitable Fixture |
| --- | --- | --- |
| Decoder unit/integration | Signature, issuer, audience, timestamps, algorithm | JWT signed with test key and fixed clock |
| Filter-chain test | Bearer extraction, authentication entry point, status/challenge | MockMvc + real decoder/JWK fixture |
| Opaque introspection test | HTTP call, client auth, active/metadata parsing | Mock introspection server |
| Authorization test | Scope, role, tenant, ownership | Authentication fixture + domain fixtures |
| End-to-end test | IdP/resource integration and API contract | Test IdP or isolated test environment |

Small, focused tests pinpoint regressions faster than sprawling E2E tests. Still, at least one integration test must traverse the exact filter chain and decoder/introspector used in production.

## 33. Keeping Test Fixtures Compatible Across Dependency Upgrades

When Spring Security or Nimbus versions change, builder APIs may change. Decouple fixture generation from test assertions:

- A `TokenFixtureFactory` that builds JWTs.
- A `TestKeySet` supplying private/public keys and JWKS.
- A `TestClock` fixing time.
- An `IntrospectionStub` managing response fixtures.
- `SecurityResponseAssertions` standardizing HTTP response checks.
- A `BaselineVector` describing expected outcomes.

When a library API changes, update the adapter/factory in one place. Never bulk-edit expected results just to make tests green; verify whether the behavioral shift was intentional.

## 34. Managing the Baseline When Policies Change Intentionally

Not every difference is a regression. For instance, an organization may:
- Enforce an audience previously left unchecked.
- Deprecate and remove a legacy signing algorithm.
- Retire an end-of-life key.
- Drop a legacy scope.
- Standardize error bodies or switch from 404 to 403 per API contract.

In such cases, update the baseline through a reviewed process:
1. State the rationale and threat/compatibility impact.
2. Identify which vectors change.
3. Update expected results for those specific vectors.
4. Keep unrelated vectors untouched.
5. Record the date/policy version or migration reference.
6. Run the entire corpus before merging.

Never modify baseline snapshots alongside code changes without explanation. Doing so turns snapshots into passive recordings of new behavior rather than change evaluators.

## 35. Protecting Private Test Keys and Fixture Repositories

Test private keys are not production secrets, yet they still require discipline to avoid confusion:

- Name keys and paths clearly as test-only.
- Never copy production keys into test resources.
- Never package test private keys into production artifacts.
- Use CI-generated ephemeral keys when static snapshots are unnecessary.
- When using static keys for deterministic signature/JWKS regression tests, keep them strictly test-only and never trust them in production.
- Never log PEMs or bearer tokens in test failure messages.
- Public JWKS fixtures can be shared; private keys stay strictly within test scope.

Fixed test keys keep results deterministic; ephemeral keys avoid storing private material. Pick the approach matching your reproducibility needs and repository policies, but never use production keys.

## 36. Do Not Compare Full Token Strings When Testing Behavior

JWT strings change whenever:
- `iat`/`exp` change.
- JSON claim ordering differs.
- Header serialization differs.
- Signing key/`kid` differs.
- Libraries update serialization details.

If testing signature output or token issuance, separate assertions can check a defined serialization contract. However, a Resource Server regression baseline should primarily compare:
- Whether the token is accepted.
- Which principal/authorities are created.
- Whether the request is allowed or denied.
- Whether the HTTP response/challenge matches.
- Whether business side effects are blocked.

Do not turn harmless JSON ordering changes into security regressions; equally, never ignore genuine claim or authority discrepancies.

## 37. Testing Caches and Key Rotation in the Baseline

Key caches and opaque introspection caches can make outcomes depend on test execution order. To keep the baseline reproducible:

- Create a fresh cache instance per test group or reset state explicitly.
- Control clocks/TTLs whenever possible.
- Configure mock JWK endpoints to serve snapshots in a deterministic sequence.
- Verify the decoder refreshes upon encountering an unknown `kid` per the active version's behavior.
- Test old tokens during overlap and after key retirement.
- For opaque caches, confirm positive TTLs never exceed expiry/revocation policies.
- Never allow an earlier test to warm the cache implicitly for a later test.

If the framework provides no cache-reset API, create a new decoder/introspector per test context or isolate endpoint fixtures per test.

## 38. Baseline for Error Mapping When Dependencies Are Unavailable

Introspection client errors, JWK timeouts, or TLS failures may pass through default authentication failure handling. Final HTTP responses depend on the framework and custom handlers.

The baseline should capture two outcomes:
- **Internal failure category:** invalid client, timeout, malformed response, JWK unavailable.
- **Public API response:** status/body/challenge per the chosen error contract.

Do not require every upstream error to return the same status if the API has a custom availability policy. Under no circumstances, however, construct an `Authentication` or let business requests proceed when a token has not been verified.

If the API is designed to return 503 when the IdP is unavailable, tests must prove that mapping works without turning ordinary invalid tokens into 503s.

## 39. Running the Corpus in CI

A pipeline can be structured as:

1. Compile test fixtures and key resources.
2. Run decoder/token validation tests.
3. Run filter-chain HTTP tests.
4. Run opaque introspection HTTP tests.
5. Run authorization denial tests.
6. Emit a report keyed by vector ID.
7. Compare against the approved baseline artifact if supported by the pipeline.
8. Fail the build on unexpected acceptance, rejection, or response contract changes.

Fail immediately if an invalid token is accepted. Wording or dynamic header variations can be normalized per policy, never security-relevant fields.

Never depend on a production Authorization Server in CI. Use test keys, mock endpoints, or a test IdP with a controlled lifecycle.

## 40. Pre- and Post-Migration Baseline Matrix

Sample review table:

| Area | Old Baseline | New Candidate | What to Preserve |
| --- | --- | --- | --- |
| Valid JWT | Accepted | Accepted | Correct principal and authorities |
| Expired JWT | 401 | 401 | No business execution |
| Wrong issuer/audience | 401 | 401 | No widening of trust boundaries |
| Bad signature | 401 | 401 | No fallback key |
| Key overlap | A and B accepted | A and B accepted | Rotation window |
| Retired key | Rejected after refresh | Rejected after refresh | Retirement semantics |
| Opaque inactive | 401 | 401 | No principal created |
| Introspection invalid client | Dependency error category | Dependency error category | Not misclassified as inactive |
| Missing scope | 403 | 403 | Authentication still succeeds |
| Ownership denied | 403/404 per contract | Preserve contract | No side effects |
| Error challenge | Bearer challenge | Bearer challenge | Client compatibility |
| Custom body | Stable problem code | Stable problem code | No internal details leaked |

A baseline does not require identical internal implementation details on the candidate. It requires published security/API guarantees to remain intact or change deliberately.

## 41. Anti-Patterns When Maintaining a Baseline

| Anti-Pattern | Consequence | Right Approach |
| --- | --- | --- |
| Using production tokens | Credential/PII leaks, non-reproducible tests | Test-only token corpus |
| Using production private keys | Risk of exposing signing authority | Dedicated test keys |
| Generating tokens against system clock | Flaky CI | Fixed clock |
| Testing only the happy path | Misses fail-open regressions | Comprehensive negative corpus |
| Packing multiple errors in one token | Unclear which validator actually ran | Each vector tests one primary condition |
| Asserting only HTTP status | Loses challenge/body semantics | Assert headers and stable body fields |
| Byte-for-byte full response diff | False positives from dynamic fields | Selective normalization |
| Using `jwt()` as a decoder test | Skips signature/JWK | Bearer tokens through real decoder |
| Using `opaqueToken()` as an introspection test | Skips HTTP introspection | Mock endpoint + Bearer header |
| Blindly updating snapshots with code | Masks regressions | Review every expected change |
| Not resetting caches | Order-dependent tests | Isolated caches/decoders |
| Omitting side-effect assertions | Denied requests still run writes | Verify services/repositories/events are untouched |

## 42. Checklist for Reviewing a New Baseline

Before using a corpus as a migration benchmark, confirm:

- Every vector has a stable ID and clear purpose.
- JWTs are signed exclusively with test keys.
- Public JWKS and matching private test keys are managed properly.
- `kid`, issuer, audience, algorithm, and clock are deterministic.
- Vectors cover `exp`, `nbf`, signature, issuer, audience, and scope.
- Vectors cover key overlap, unknown `kid`, and retired keys.
- Opaque responses include `active` true/false and missing/malformed metadata.
- Introspection `invalid_client`, timeouts, and upstream errors are covered.
- 401/403, `WWW-Authenticate`, and error bodies match the contract.
- Negative cases verify business operations do not execute.
- Dynamic headers/fields are normalized deliberately.
- Metrics, logs, and test output contain no raw tokens or secrets.
- Every change to expected outcomes has a rationale and reviewer.
- CI runs the exact same corpus against candidate dependencies/configurations.

## 43. References

- [Spring Security 6.5 — JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT decoders, validators, and JWK Set.
- [Spring Security 6.5 — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection and custom `OpaqueTokenIntrospector`.
- [Spring Security 6.5 — Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html): test support for authentication and HTTP security.
- [Spring Security 6.5 — MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html): testing the filter chain with MockMvc.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517.html): JWK/JWKS and key identifiers.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): registered claims and `NumericDate`.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer challenges and `invalid_token`/`insufficient_scope`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): introspection responses and active metadata.

## 44. Conclusion

A reliable migration baseline preserves the same corpus of tokens, keys/JWKS, expected error responses, and negative test cases across changes to Spring Security, Spring Boot, or OAuth/OIDC configuration. JWT fixtures need real signatures with test-only keys, stable `kid` values, and a fixed clock. Opaque token fixtures need separate introspection responses for active/inactive states, missing metadata, and client/dependency errors.

Compare authentication outcomes, authorization decisions, HTTP statuses, Bearer challenges, stable response bodies, and side effects together. Invalid tokens must be rejected; valid tokens lacking scope or ownership must be denied; and JWK/introspection errors must be recognized as verification failures rather than turned into valid principals. When policies change intentionally, update the matching vectors and record the rationale.

**Key takeaway:** *Reuse the exact same reproducible corpus to prove the migration preserves security boundaries and API contracts; every shift in a negative test case must be explained before acceptance.*
