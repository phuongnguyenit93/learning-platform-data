# Controlled Token Fixture Suites for Testing Compatibility When Issuers Change

## 1. Why Does a Resource Server Need a Controlled Token Fixture Suite?

A **Spring Security OAuth 2.0 / OIDC Resource Server** depends on the contract published by its Authorization Server (AS) or OpenID Provider (OP): issuer, audience, signature, algorithm, key ID, lifetime, token type, scopes, roles, and extended claims.

When an issuer changes configuration or upgrades versions, access tokens can change in many ways:

- Signing keys rotate and a new `kid` appears in the JWKS.
- The Issuer URL moves to a new realm/domain.
- Audiences are added, removed, or renamed.
- The `scope` claim shifts from a space-delimited string to another schema.
- `roles`/`groups` claims are renamed or change data types.
- Token profiles change, such as `typ`, `client_id`, `sub`, or required claims.
- Introspection responses change structure or how `active` is represented.
- OIDC discovery metadata changes `jwks_uri` or related endpoints.

Testing only against one live active token can miss breaking compatibility changes. A suite of **controlled token fixtures** supplies reproducible credentials and issuer responses with clear provenance and explicit expected results that run repeatedly in CI.

The fixture suite helps answer:

1. Are tokens matching the current contract still accepted?
2. Are tokens with wrong issuer, audience, signature, or lifetime rejected?
3. Are tokens from a new key verified after rotation?
4. Are older tokens still valid during the overlap window handled properly?
5. Do issuer claim/scope changes alter authorities or endpoint permissions?
6. When the introspection/JWKS service fails, does the Resource Server fail closed and classify errors properly?
7. Are new issuers added under control while issuers outside the allowlist remain rejected?

**Controlled token fixtures are test data**, not production credentials. Use dedicated test keys, synthetic tokens, and sandbox issuers. Never copy active access tokens or refresh tokens of real users into repositories, CI logs, or documentation.

### 1.1. Distinguishing Fixture Types

| Data Type | Purpose | Should It Be Stored in Git? |
|---|---|---|
| Synthetic JWT signed with test private key | Tests signature, claims, issuer, audience, expiry, and authority mapping | Possibly, if key is strictly test-only; better to generate tokens at runtime |
| Test public JWKS | Lets decoder verify test signatures | Yes, since it holds only public keys |
| Simulated opaque token | Tests resolver/introspector and authorization | Yes using dummy strings, never live tokens |
| Introspection JSON fixture | Tests `active`, scope, audience, and claim mapping | Yes once sensitive data is stripped |
| OIDC discovery metadata fixture | Tests issuer/JWKS URI and metadata contract | Yes if it is a controlled sandbox snapshot |
| Production-captured token | Debugging or compatibility testing | Never commit, never put in logs/fixtures |
| Refresh token or client secret | Credential to mint tokens or call AS | Never commit, never use as fixtures |
| Production private signing key | Signs real tokens | Absolutely never place in test resources |

A JSON file containing only payload claims **is not a JWT signature test**. If the goal is testing `JwtDecoder`, you need compact JWTs signed with a test private key alongside the public key/JWKS trusted by the decoder.

Conversely, if solely testing business mapping from claims to authorities, a mock `Jwt` or `Authentication` works. Yet mock authentication never proves signature, issuer, or audience validation works.

### 1.2. Fixtures Must Have Provenance

Each fixture should document:

- Fixture ID and fixture-set version.
- Issuer alias and expected issuer URL.
- Token profile/version.
- Audience and client/resource identifier.
- Signing algorithm and `kid`.
- Key claims and data types.
- Issued/expiry timestamps relative to the test clock.
- Expected outcome: accept, reject authentication, or authenticated-but-forbidden.
- Reason the fixture exists: baseline, issuer drift, key rotation, wrong audience, scope regression.
- Origin: generated test key, sandbox contract snapshot, or provider-published example.

Provenance distinguishes "this token is intentionally invalid" from "a fixture broke accidentally."

## 2. Building a Token Fixture Matrix Aligned with the Issuer Contract

Suppose the Orders API accepts access tokens following this profile:

~~~text
issuer    = https://id.example.test/realms/orders
audience  = orders-api
algorithm = RS256
type      = at+jwt
scope     = space-delimited OAuth scopes
~~~

Baseline claims might include:

~~~json
{
  "iss": "https://id.example.test/realms/orders",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 2000000000,
  "exp": 2000000300,
  "jti": "fixture-jti-001",
  "client_id": "orders-web",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a"
}
~~~

This payload is illustrative. Mandatory fields depend on the access token profile and issuer contract. For instance, RFC 9068 defines the JWT Profile for OAuth 2.0 Access Tokens with stricter claim and header type requirements. Do not enforce the RFC 9068 profile on every JWT unless the AS commits to issuing tokens under that profile.

### 2.1. Baseline JWT Fixture Set

| Fixture ID | Change vs. Baseline | Expected Result |
|---|---|---|
| `valid-orders-read` | Valid issuer, audience, signature, time; has `orders.read` | Authentication accepted; GET read allowed |
| `valid-orders-write` | Has `orders.write` | Authentication accepted; write policy may allow |
| `wrong-issuer` | `iss` differs from trusted issuer | Reject authentication |
| `wrong-audience` | `aud` only has `billing-api` | Reject authentication |
| `expired-token` | `exp` in the past relative to test clock | Reject authentication |
| `not-yet-valid` | `nbf` in the future beyond clock skew | Reject authentication |
| `bad-signature` | Signed with untrusted private key | Reject authentication |
| `unknown-kid` | Header `kid` absent from trusted JWKS | Reject authentication |
| `unsupported-alg` | Algorithm outside allowlist | Reject authentication |
| `missing-sub` | Missing claim required by profile | Reject if contract requires |
| `missing-scope` | Valid token lacking required scope | Authentication accepted; endpoint returns 403 |
| `scope-type-drift` | Scope changes type from string to array/object | Contract test must catch drift |
| `role-claim-renamed` | `roles` renamed to `groups` | Never grant unexpected privileges |
| `wrong-tenant` | Token has different tenant from resource path | Authentication may succeed; domain authorization denies |
| `old-key-during-overlap` | Token signed with old still-published key | Accept during overlap if policy allows |
| `new-key-after-rotation` | Token signed with new key | Accept once JWKS updates |
| `id-token-as-access-token` | Token profile/audience meant for OIDC client | Reject if outside access token contract |

A fixture can have authentication accepted yet authorization denied. **Never collapse expected results of both layers** into a single boolean.

### 2.2. Expected Results Must Specify the Verification Layer

~~~text
Authentication:
    Is the credential trusted and valid?

Authorization:
    Is this authenticated principal allowed to perform this action
    on this resource and tenant?
~~~

Example:

~~~text
Fixture: valid-token-without-orders-write
Decoder result: ACCEPT
Authentication result: AUTHENTICATED
POST /api/orders result: 403
GET /api/orders result: per remaining scopes
~~~

If a test only asserts "request returns 403," the decoder might have rejected the token while a security handler returned a semantically wrong 403; assert status, challenge, and handling layer explicitly.

## 3. Defining a Versioned Fixture Manifest

A manifest describing the fixture suite tells CI which issuer/profile each fixture belongs to and its expected behavior.

**Illustrative** manifest example:

~~~yaml
fixtureSet:
  id: orders-resource-server
  version: 3
  generatedFor: contract-test
  issuerAlias: orders-sandbox
  issuer: https://id.example.test/realms/orders
  audience:
    - orders-api
  tokenProfile: rfc9068
  signing:
    algorithm: RS256
    keyId: fixture-rsa-2026-01

fixtures:
  - id: valid-read
    scenario: valid-access-token
    expectedAuthentication: ACCEPT
    expectedAuthorities:
      - SCOPE_orders.read

  - id: wrong-audience
    scenario: wrong-audience
    expectedAuthentication: REJECT
    reason: TOKEN_NOT_INTENDED_FOR_RESOURCE

  - id: expired
    scenario: expired
    expectedAuthentication: REJECT
    reason: TOKEN_EXPIRED

  - id: read-only
    scenario: valid-read-only
    expectedAuthentication: ACCEPT
    expectedAuthorities:
      - SCOPE_orders.read
    expectedAuthorization:
      post-api-orders: DENY
~~~

This is a **project-defined schema**, not Spring Boot properties or a standard OAuth manifest. You can replace scenarios with test factory names so tokens are generated at runtime, avoiding static compact JWTs in files.

Manifests should be reviewed alongside validators and authorization rules. When an issuer changes, bump the fixture-set version or create a new profile version rather than silently editing the baseline and losing the ability to reproduce legacy failures.

### 3.1. Versions That Must Not Be Conflated

- **Fixture-set version:** version of the test scenario suite.
- **Token profile version:** access token format/claim contract.
- **Issuer configuration version:** snapshot of trusted issuer, audience, JWKS URI, algorithms, and mappings.
- **Application version:** Resource Server version under test.

When a test fails, you must know whether the failure stems from a fixture change, an issuer contract change, or an application regression.

### 3.2. Use Synthetic Data

A fixture manifest may contain subject `fixture-user-01`, tenant `tenant-test-a`, and client `orders-test-client`. Never use emails, phones, customer IDs, order IDs, or personal claims taken from production without approved protections and purpose.

## 4. Generating Genuinely Signed Test JWTs with Test Private Keys

To test the Resource Server decoder, tokens must be signed with test keys. Matching public keys are supplied to the decoder/test JWKS server. Private keys serve strictly to mint fixtures in the test environment.

### 4.1. Principles for Managing Test Signing Keys

- Use dedicated RSA/EC keys for tests; never reuse production keys.
- Set explicit `kid` values, such as `fixture-rsa-2026-01`.
- Never publish private keys in the JWKS endpoint.
- Optionally generate key pairs at test runtime to avoid long-lived private key files.
- If using fixed key fixtures, restrict read permissions and never use them outside tests.
- Never use short/guessable secrets for HMAC token signing.
- Trust only the test public JWKS endpoint in the test decoder.
- Isolate test keys per issuer so tokens from another issuer are never accidentally verified.

### 4.2. Factory for Generating Test Keys and JwtEncoder

Example with Spring Security JOSE/Nimbus:

~~~java
package com.example.orders.testsecurity;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

public final class TestSigningKeys {

    private TestSigningKeys() {}

    public static RSAKey newRsaKey(String keyId) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair pair = generator.generateKeyPair();

        return new RSAKey.Builder(
                (RSAPublicKey) pair.getPublic())
            .privateKey((RSAPrivateKey) pair.getPrivate())
            .keyID(keyId)
            .build();
    }

    public static JwtEncoder encoder(RSAKey signingKey) {
        JWKSource<SecurityContext> source =
            new ImmutableJWKSet<>(new JWKSet(signingKey));

        return new NimbusJwtEncoder(source);
    }
}
~~~

These Nimbus JOSE types are used by Spring Security OAuth2 JOSE. If your project lacks these classes on the test classpath, check the Spring Boot Resource Server starter's dependency management and add the version-aligned JOSE dependency—never pull in an arbitrary Nimbus version.

### 4.3. Minting Tokens with Controlled Claims

~~~java
package com.example.orders.testsecurity;

import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.RSAKey;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;

public final class AccessTokenFixtures {

    public static final String ISSUER =
        "https://id.example.test/realms/orders";

    public static final String AUDIENCE = "orders-api";

    private final JwtEncoder encoder;
    private final String keyId;

    public AccessTokenFixtures(RSAKey signingKey) {
        this.encoder = TestSigningKeys.encoder(signingKey);
        this.keyId = signingKey.getKeyID();
    }

    public String validReadToken(Instant now) {
        return token(
            now,
            ISSUER,
            List.of(AUDIENCE),
            now.plusSeconds(300),
            "orders.read",
            "tenant-test-a"
        );
    }

    public String token(
            Instant issuedAt,
            String issuer,
            List<String> audience,
            Instant expiresAt,
            String scope,
            String tenant) {

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("fixture-user-01")
            .audience(audience)
            .issuedAt(issuedAt)
            .expiresAt(expiresAt)
            .claim("jti", "fixture-jti-001")
            .claim("client_id", "orders-test-client")
            .claim("scope", scope)
            .claim("tenant_id", tenant)
            .build();

        JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
            .keyId(keyId)
            .type("at+jwt")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims)
        ).getTokenValue();
    }
}
~~~

This example assumes the issuer contract uses `typ=at+jwt` per JWT Access Token Profile. If your actual issuer uses another type or omits `typ`, the fixture must reflect **the agreed profile** rather than forcing every issuer to mirror the example.

`iat`/`exp` values are passed into the factory so tests can use a fixed `Clock`. Never rely on random times or wait for real token expiration in tests.

### 4.4. Creating Intentionally Invalid Fixtures

~~~java
String wrongAudience = fixtures.token(
    fixedNow,
    AccessTokenFixtures.ISSUER,
    List.of("billing-api"),
    fixedNow.plusSeconds(300),
    "orders.read",
    "tenant-test-a"
);

String wrongTenant = fixtures.token(
    fixedNow,
    AccessTokenFixtures.ISSUER,
    List.of(AccessTokenFixtures.AUDIENCE),
    fixedNow.plusSeconds(300),
    "orders.read",
    "tenant-test-b"
);

String expired = fixtures.token(
    fixedNow.minusSeconds(600),
    AccessTokenFixtures.ISSUER,
    List.of(AccessTokenFixtures.AUDIENCE),
    fixedNow.minusSeconds(300),
    "orders.read",
    "tenant-test-a"
);
~~~

`wrongAudience` must fail authentication when the audience validator is configured. `wrongTenant` can pass authentication yet must fail domain authorization when the request targets another tenant. `expired` must fail per the decoder's clock and clock-skew policy.

### 4.5. Why Are Runtime-Generated Tokens Still Controlled Fixtures?

A fixture is controlled by its **scenario, signing key, issuer, claims, test clock, and expected outcome**, not necessarily by a frozen compact JWT string.

Generating tokens at runtime helps:

- Avoid committing raw tokens into source control.
- Easily produce intentional claim variations.
- Test expiration independently of the calendar date.
- Generate tokens with old/new keys.
- Test multiple issuer/audience profiles.

To reproduce a production bug, record redacted metadata and a reproducible scenario; there is no need to copy production bearer credentials.

## 5. Configuring Test Decoders and a Fixed Clock

A token fixture suite is valuable when the real decoder is tested, not merely mocked `Jwt` objects.

### 5.1. Decoder Using Test Public Key

~~~java
package com.example.orders.testsecurity;

import java.time.Clock;
import java.time.Duration;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.RSAKey;

import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public final class TestJwtDecoderFactory {

    private TestJwtDecoderFactory() {}

    public static NimbusJwtDecoder decoder(
            RSAKey trustedKey,
            String issuer,
            String audience,
            Clock clock) {

        RSAPublicKey publicKey = trustedKey.toRSAPublicKey();

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withPublicKey(publicKey).build();

        JwtTimestampValidator timestamps =
            new JwtTimestampValidator(Duration.ZERO);
        timestamps.setClock(clock);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience is not accepted",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                new JwtIssuerValidator(issuer),
                timestamps,
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

This decoder tests **JWS with an RSA public key**. In production, keys usually come from a trusted JWKS URI with matching validators. If your project's Nimbus version lacks the public-key helper above, retain the `RSAPublicKey` directly when generating the key pair and pass it to the factory.

**Profile note:** this example checks issuer, timestamps, and audience. It does not yet cover full JWT Access Token Profile validation such as `typ`, required `client_id`/`jti`, or custom claim schemas. If your issuer contract requires those, add dedicated `OAuth2TokenValidator<Jwt>` instances and fixtures for each claim.

### 5.2. Time Tests Must Be Deterministic

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-15T00:00:00Z"),
    ZoneOffset.UTC
);
~~~

Generate cases:

- Token expired before the fixed clock.
- Token currently valid.
- Token with `nbf` after the fixed clock.
- Token at the exact clock skew boundary.

Never use `Thread.sleep` to wait for tokens to expire. Tests must be fast, reproducible, and independent of CI machine wall clocks.

If the validator configures clock skew, document that value in contract tests. A token expired 10 seconds ago may still be accepted if policy allows 60 seconds of skew; expected outcomes must reflect real policy.

## 6. Checking JWT Profiles, Headers, and Claims When Issuers Change

### 6.1. Header Fields

A JWS JWT has a header:

~~~json
{
  "alg": "RS256",
  "kid": "fixture-rsa-2026-01",
  "typ": "at+jwt"
}
~~~

Fields to control:

- `alg`: allow only approved algorithms.
- `kid`: locates the public key in the trusted JWKS; not proof of key trust.
- `typ`: token type/profile per issuer contract.
- `crit`/`cty` if used by the profile.

Never accept an algorithm solely because the token declares it. **The verifier determines the allowlist**, not the token header.

### 6.2. Claims and Data Types

| Claim | Contract to Define | Drift Fixtures to Include |
|---|---|---|
| `iss` | Exact issuer identifier | Old/new issuer, issuer outside allowlist |
| `sub` | Subject identifier and stability | Missing/changed subject, cross-issuer collision |
| `aud` | Resource Server audience | Wrong audience, string/array representation |
| `exp` | Expiry semantics | Expired, missing if required by profile |
| `nbf` | Not-before | Future value |
| `iat` | Issued-at | Missing/invalid if required by profile |
| `jti` | Token identifier if required by profile | Missing/duplicate per policy |
| `client_id` | Client identity | Missing/renamed/type drift |
| `scope`/`scp` | Scope schema | Space string, array, renamed claim |
| `roles`/`groups` | Role mapping | New claim name, unexpected role |
| `tenant_id` | Tenant binding | Missing, wrong tenant, type drift |
| `typ` | Access-token type | Missing/wrong type |

Not every claim in the table is mandatory for every issuer. Mark each as **required / optional / ignored / forbidden** per the agreed token profile.

### 6.3. Scope Strings and Provider-Specific Claims

OAuth 2.0 scope values in access tokens are commonly represented as a space-delimited string:

~~~json
{"scope": "orders.read orders.write"}
~~~

Some providers emit other claims such as `scp` or role arrays. Never assume all providers use the same schema.

Example internal contract:

~~~yaml
scopeMapping:
  claim: scope
  representation: space-delimited-string
  authorityPrefix: SCOPE_
  allowed:
    - orders.read
    - orders.write
    - orders.approve
~~~

This is an application-defined manifest. If an issuer switches from `scope` to `scp`, do not blindly "accept both" without a migration plan. You can support both during a transition window with clear precedence and a deadline, then remove the old claim.

### 6.4. Token Profile and `typ`

If the Resource Server requires the RFC 9068 JWT Access Token Profile, the header type is typically `at+jwt` and claims/profile must comply with that standard. Not all existing JWT access tokens follow RFC 9068.

Include fixtures for:

- Profile-compliant `typ=at+jwt`.
- Missing `typ` when required by profile.
- Mismatched `typ` outside profile.
- Token with audience targeting an OIDC client rather than the API.
- ID Token with valid issuer signature yet wrong intended use.

Never verify only the signature and accept every JWT from the same issuer.
## 7. Fixture Suites for JWKS and Key Rotation

### 7.1. JWKS Is Part of the Issuer Contract

The Resource Server typically fetches public signing keys from a JWKS endpoint supplied by discovery metadata or trusted config.

Test JWKS can contain:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "fixture-rsa-old",
      "use": "sig",
      "alg": "RS256",
      "n": "<PUBLIC-MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "fixture-rsa-new",
      "use": "sig",
      "alg": "RS256",
      "n": "<PUBLIC-MODULUS-NEW>",
      "e": "AQAB"
    }
  ]
}
~~~

Modulus values are placeholders. **Never include private RSA parameters `d`, `p`, `q`, `dp`, `dq`, `qi` in a public JWKS.**

### 7.2. Rotation Usually Has an Overlap Window

~~~text
T0: JWKS publishes key-old
T1: JWKS publishes key-old + key-new
T2: issuer begins signing new tokens with key-new
T3: tokens signed with key-old expire / pass overlap window
T4: JWKS removes key-old
~~~

The Resource Server may cache JWKS. Therefore, testing rotation is not just verifying "JWKS JSON has the new key," but proving the decoder actually retrieves the new key according to your library version's cache/refresh behavior.

### 7.3. Rotation Fixture Scenarios

| Scenario | JWKS | Token | Expected |
|---|---|---|---|
| Baseline | Only key-old | Signed by key-old | Accept |
| Publish new key | old + new | Signed by key-old | Accept |
| Begin signing new key | old + new | Signed by key-new | Accept |
| Old token during overlap | old + new | Signed by key-old, unexpired | Accept |
| Old key removed too early | Only key-new | Signed by key-old | Reject or error per policy; catches bad rollout |
| Unknown key ID | Lacks `kid` | Signed by key outside set | Reject |
| JWKS unavailable | Endpoint timeout/5xx | Token needing uncached key | Never fail open |
| Duplicate/ambiguous key IDs | Invalid JWKS | Token has duplicate `kid` | Never guess trusted key |

There is no single fixed overlap duration for all issuers. Calculate it from max access token lifetime, clock skew, JWKS cache/refresh behavior, and rollout topology.

### 7.4. Unknown `kid` Is Never a Reason to Fetch Arbitrary URLs

If a token header contains:

~~~json
{
  "kid": "attacker-key",
  "jku": "https://attacker.example/jwks.json"
}
~~~

the Resource Server must never fetch arbitrary `jku` URLs to find keys. Fetch keys only from the **trusted JWKS URI** of a configured/allowlisted issuer. `kid` merely selects a key within the trusted set.

### 7.5. Algorithm Migration

If an issuer switches from RS256 to ES256, that is a contract change affecting key type and algorithm:

- The Resource Server must configure an appropriate algorithm allowlist.
- JWKS must publish public EC keys with matching curves/metadata.
- Key rotation and algorithm rollout need overlap if client/token lifetimes require it.
- Tokens signed with disallowed algorithms must be rejected.
- Never automatically accept whatever `alg` a token header sends.

Create fixtures for old/new algorithms during migration and negative fixtures for disallowed algorithms.

## 8. Fixtures for Issuer, Audience, and Discovery Metadata

### 8.1. Issuer Is an Exact Identifier

JWT `iss` must match the trusted issuer per contract. Seemingly minor changes break authentication:

~~~text
https://id.example.test/realms/orders
https://login.example.test/realms/orders
https://id.example.test/realms/orders/
~~~

Never normalize slashes, schemes, or hostnames "to make them match" unless specified by contract. Treat issuer migration as a trust configuration change.

### 8.2. OIDC Discovery Snapshot

A metadata fixture might contain:

~~~json
{
  "issuer": "https://id.example.test/realms/orders",
  "jwks_uri": "https://id.example.test/realms/orders/protocol/openid-connect/certs",
  "authorization_endpoint": "https://id.example.test/realms/orders/protocol/openid-connect/auth",
  "token_endpoint": "https://id.example.test/realms/orders/protocol/openid-connect/token",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Resource Server JWT verification mainly relies on the issuer/JWKS relationship; other fields serve OAuth/OIDC clients or other capabilities. Do not mistake OIDC Provider discovery metadata as meaning every field is required for access token validation.

Contract tests should verify:

- Metadata `issuer` exactly matches the configured issuer.
- `jwks_uri` lies within the trusted domain/allowlist.
- HTTPS and certificate validation remain enabled.
- Metadata does not point to unintended hosts.
- The JWKS endpoint returns a key set matching schema.
- Metadata endpoint errors are distinguished from invalid tokens.
- Discovery changes do not inadvertently alter OAuth2 Client registration/login behavior.

### 8.3. Issuer URL Migration

If an issuer changes its URL, older tokens still carry the old `iss`. A migration plan can:

1. Add the new issuer to the trusted registry after review.
2. Configure the manager/decoder for the new issuer with full audience/profile validators.
3. Temporarily support both old and new issuers if security policy permits.
4. Run fixtures for both issuers, including wrong-audience and spoofed-issuer tests.
5. Ensure identity mapping distinguishes `(iss, sub)`.
6. Monitor old vs. new token ratios and unmigrated clients.
7. Wait for old tokens to expire and complete migration.
8. Remove the old issuer from the allowlist and run regression tests.

Never replace the old issuer with the new URL in config expecting old tokens to remain valid automatically. Likewise, do not keep an old issuer around indefinitely once its trust domain is retired.

## 9. Opaque Tokens and Introspection Fixtures

Not all issuers emit JWTs. For opaque tokens, the Resource Server calls an introspection endpoint per RFC 7662. The fixture suite must test the **request and response contract**, not merely a token string.

### 9.1. Active Response Fixture

~~~json
{
  "active": true,
  "scope": "partner.reports.read",
  "client_id": "partner-export-client",
  "sub": "partner-user-01",
  "aud": ["partner-api"],
  "iss": "https://partner-id.example.test",
  "exp": 2000000300
}
~~~

Fields beyond `active` are provider-dependent. Never assume every Authorization Server returns `aud`, `iss`, `exp`, or `tenant_id`.

### 9.2. Inactive Response Fixture

~~~json
{"active": false}
~~~

HTTP 200 with `active:false` is a valid introspection result indicating an inactive token. It differs from:

- HTTP 401 from wrong Resource Server client credentials.
- HTTP 403 from an unauthorized introspection client.
- HTTP 429 from rate limiting.
- HTTP 5xx or timeout from dependency failures.

Never convert network failures into `active:false` and cache them as revocation decisions.

### 9.3. Opaque Fixture Matrix

| Fixture | Response/Request Variation | Expected |
|---|---|---|
| `opaque-active-read` | active true, read scope | Authentication accepted |
| `opaque-inactive` | active false | Reject token |
| `opaque-missing-scope` | active true, no write | Authentication accepted; write 403 |
| `opaque-wrong-audience` | active true yet wrong aud | Reject if API requires audience |
| `opaque-expired` | past exp | Reject if profile/validator requires exp |
| `introspection-unauthorized` | HTTP 401 | RS credential error with AS |
| `introspection-forbidden` | HTTP 403 | Introspection client policy |
| `introspection-rate-limited` | HTTP 429 | Backoff/availability policy |
| `introspection-timeout` | No response | Fail closed |
| `introspection-schema-drift` | Claim type/name changed | Contract test fails explicitly |

### 9.4. Opaque Tokens in Tests Do Not Need to Be Real Tokens

~~~text
fixture-opaque-partner-read-001
~~~

You can use dummy strings and a mock introspector or HTTP stub returning the corresponding JSON fixtures. The goal is testing the introspection protocol, authority mapping, and failure handling. Never use production opaque access tokens, as they are bearer credentials even when opaque.

When testing HTTP client authentication, use dedicated test client IDs/secrets and verify request bodies/headers are never logged. Authentication method details must match the AS contract; never assume every provider uses HTTP Basic when another method is supported.

### 9.5. Classifying Introspection Outcomes

| Result | Authentication Interpretation |
|---|---|
| HTTP 200 + `active:true` | Token confirmed active; proceed to validators/policies |
| HTTP 200 + `active:false` | Token inactive |
| HTTP 200 yet missing `active` or wrong type | Response violates contract; never default to active |
| HTTP 401/403 | Introspection client authentication/authorization failure |
| HTTP 429 | AS rate limit |
| HTTP 5xx/timeout | Dependency failure |
| Malformed JSON | Introspection protocol/contract failure |

Never treat bare HTTP 200 as a valid token. Likewise, never cache timeouts as negative token results.

### 9.6. Scope and Audience of Opaque Tokens

Opaque introspection can return `scope` as a string and provider-specific attributes. Check:

- Does the scope belong to the API namespace?
- Does the provider return `aud` per contract?
- If the API requires audience and introspection omits it, agree on another profile/validation with the AS.
- Is `exp` present in a type supported by the converter?
- Are `client_id`/`sub` distinguished properly for user-delegated vs. client-credentials flows?

Never assume opaque tokens always represent human users; principals may be service clients depending on grant type.

## 10. Separating Contract Tests Across Resource Server Layers

A solid test suite should not rely solely on end-to-end calls to a live issuer. Split tests across layers so you know precisely what broke when a provider changes.

~~~mermaid
flowchart TD
    A["Versioned fixture manifest"] --> B["JWT/JWKS unit tests"]
    A --> C["Opaque introspection contract tests"]
    A --> D["Issuer discovery tests"]
    B --> E["Decoder + claim validators"]
    C --> F["Introspector + authority mapping"]
    D --> G["Issuer/JWKS metadata trust"]
    E --> H["SecurityFilterChain integration"]
    F --> H
    G --> H
    H --> I["Authorization + tenant tests"]
    I --> J["Sandbox provider compatibility"]
    J --> K["Release gate / rollout"]
~~~

### 10.1. Decoder Unit Tests

Verify:

- Valid signed JWT accepted.
- Wrong issuer rejected.
- Wrong audience rejected.
- Expired/not-yet-valid rejected against fixed clock.
- Bad signature rejected.
- Unknown key rejected.
- Disallowed algorithm rejected.
- Missing/wrong-type required claims rejected if required by profile.
- Wrong `typ` rejected if required by profile validator.

Unit tests should be fast with no network calls. Pass test public keys directly or use test JWKS snapshots depending on the target.

### 10.2. SecurityFilterChain Integration Tests

Use MockMvc/Spring Security Test to verify:

- Unauthenticated requests to protected endpoints return 401.
- Valid tokens with the right scope are permitted.
- Valid tokens lacking scope return 403.
- Wrong-audience tokens fail authentication.
- Partner tokens are not processed on the Orders JWT chain.
- Fallback chain denies undeclared paths.
- Body, headers, and status do not contradict each other.

The `jwt()` helper constructs a simulated Authentication for testing authorization. It **does not prove signature, issuer, audience, or JWKS decoder behavior**; write dedicated decoder tests or send real compact test JWTs through the Bearer filter.

### 10.3. Contract Tests for OIDC Discovery/JWKS

Use metadata/JWKS snapshots or a local mock server:

- Exact metadata issuer.
- JWKS URI in trust registry.
- JWKS contains matching key IDs/algorithms.
- Old/new key rotation.
- Unknown key behavior.
- Network timeouts/5xx.
- TLS certificate failures if supported by test infrastructure.
- Metadata issuer mismatch.

There is no need to hit the production IdP in every unit test. A sandbox contract suite or scheduled job can verify real integration, while pull request tests run against fixed fixtures.

### 10.4. Contract Tests for Opaque Introspection

Stub the HTTP endpoint to return:

- `active` true/false.
- Complete/minimal claim sets.
- HTTP 401/403/429/5xx.
- Timeouts.
- Malformed JSON.
- Missing `active` or wrong type.
- Scope schema changes.
- Audience/issuer drift.

Assert the request too: endpoint, POST method, `token` form parameter, Resource Server authentication method, and zero token leakage in logs. Auth method details must match the AS contract.
## 11. Example Decoder Tests with JUnit

A basic test using the decoder and token factory:

~~~java
package com.example.orders.security;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import com.nimbusds.jose.jwk.RSAKey;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

class IssuerCompatibilityTests {

    private final Instant now =
        Instant.parse("2026-11-15T00:00:00Z");

    private RSAKey signingKey;
    private AccessTokenFixtures fixtures;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        signingKey = TestSigningKeys.newRsaKey("fixture-rsa-01");
        fixtures = new AccessTokenFixtures(signingKey);

        decoder = TestJwtDecoderFactory.decoder(
            signingKey,
            AccessTokenFixtures.ISSUER,
            AccessTokenFixtures.AUDIENCE,
            Clock.fixed(now, ZoneOffset.UTC)
        );
    }

    @Test
    void acceptsValidAccessToken() {
        String token = fixtures.validReadToken(now);

        assertDoesNotThrow(() -> decoder.decode(token));
    }

    @Test
    void rejectsWrongAudience() {
        String token = fixtures.token(
            now,
            AccessTokenFixtures.ISSUER,
            List.of("billing-api"),
            now.plusSeconds(300),
            "orders.read",
            "tenant-test-a"
        );

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsExpiredToken() {
        String token = fixtures.token(
            now.minusSeconds(600),
            AccessTokenFixtures.ISSUER,
            List.of(AccessTokenFixtures.AUDIENCE),
            now.minusSeconds(300),
            "orders.read",
            "tenant-test-a"
        );

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }
}
~~~

This is a structural example. `AccessTokenFixtures` and `TestJwtDecoderFactory` belong in the test source set with complete imports. The decoder uses the public key derived from the same test key; to test **bad signatures**, generate a second key pair and sign the token with the private key that does not match the decoder's trusted public key.

### 11.1. Testing Wrong Issuer

Mint a token with a valid signature using the same test key yet a different `iss`:

~~~java
String wrongIssuer = fixtures.token(
    now,
    "https://untrusted.example.test",
    List.of(AccessTokenFixtures.AUDIENCE),
    now.plusSeconds(300),
    "orders.read",
    "tenant-test-a"
);

assertThrows(JwtException.class, () -> decoder.decode(wrongIssuer));
~~~

This test proves issuer validation executes after signature decoding.

### 11.2. Tenant Mismatch Is Authorization, Not a Decoder Failure

A token with `tenant_id=tenant-test-b` can still be a valid JWT. The decoder should only verify issuer, audience, signature, and token profile. Afterwards, service/authorization policies must deny requests to `tenant-test-a` if the principal lacks permission.

Do not stuff all business ACLs into the JWT decoder. The decoder lacks context about resource IDs, current memberships, or data state.

## 12. Testing Issuer Changes by Individual Drift Category

An issuer release can alter multiple properties at once. The fixture suite should isolate each change to pinpoint root causes.

### 12.1. Compatibility Matrix

| Provider Change | Risk | Fixture/Test to Add | Rollout Approach |
|---|---|---|---|
| JWKS adds new key | Decoder cache/refresh misses key | Signed token with new `kid` | Publish overlap, then switch signing |
| JWKS drops old key | Unexpired old tokens rejected | Old-key token and expiry boundary | Wait max token lifetime + skew/cache |
| Algorithm changes | Decoder unsupported or overly permissive policy | Old/new alg and disallowed alg | Explicit allowlist, timed overlap |
| Issuer URL changes | `iss` mismatch, identity split | Old/new issuer fixtures | Reviewed dual trust, sunset old |
| Audience changes | Token not intended for API | Old/new audience fixtures | Additive transition if contract permits |
| `scope` becomes `scp` | Authorities disappear | Claim type/name fixtures | Dual mapping with deadline, then remove |
| Role claim renamed | Privileges lost or escalated | Role mapping fixtures | Explicit mapping and least privilege |
| `sub` format changes | Wrong user identity/ownership mapping | Subject stability/collision tests | Identity mapping migration |
| `client_id`/`azp` changes | Client policy fails | Client identity fixtures | Update registered clients/validators |
| Token `typ` changes | Profile mismatch | Header type fixtures | Approve profile/version |
| `exp` lifetime changes | Session/availability/revocation shifts | Short/long lifetime fixtures | Review cache, clock skew, SLOs |
| Introspection schema changes | Wrong opaque principal/authorities | Active/claims response fixtures | Contract tests and versioned mapping |
| Discovery `jwks_uri` changes | Fetch from unexpected endpoint | Metadata snapshot diff | Allowlist/validate new URI |
| Issuer signing cert rotates | Key trust gap | Old/new key overlap fixtures | Planned rotation |
| Scope revoked | Caller keeps old permission via cache | Valid token missing scope, cache invalidation test | Invalidate/shorten cache per policy |

### 12.2. Additive Changes vs. Breaking Changes

**Additive** does not automatically mean safe. An issuer adding a new optional claim is low risk if the Resource Server ignores unused claims; yet adding a new role when a converter blindly maps all roles to authorities can escalate privileges.

Breaking changes typically include:

- Changing the issuer identifier.
- Changing audience so the API is no longer the intended recipient.
- Removing/renaming a scope actively used by clients.
- Changing the type of a claim a converter depends on.
- Changing signing algorithms/key types outside decoder support.
- Changing token profiles or required claims.

Evaluate every change across both **authentication acceptance** and **authorization outcome**. A token that still authenticates while losing its permissions is still a client-impacting compatibility change.

### 12.3. Provider Drift Must Fail Tests Meaningfully

If `scope` changes from:

~~~json
{"scope": "orders.read orders.write"}
~~~

to:

~~~json
{"scp": ["orders.read", "orders.write"]}
~~~

a test asserting only HTTP 200 on a public endpoint will miss it. The contract suite must verify:

- The decoder accepts profile-compliant tokens.
- The converter creates the expected authorities.
- Read/write endpoints reflect the proper permissions.
- Out-of-contract claims do not accidentally grant roles.
- Tokens lacking scopes genuinely receive 403.

## 13. Controlling OIDC Discovery and Issuer Configuration

### 13.1. Metadata Snapshots Must Match the Configured Issuer

OIDC discovery documents contain `issuer` and `jwks_uri` fields. A Resource Server must not trust a metadata document merely because the HTTP request succeeded. It must belong to the exact configured/allowlisted issuer.

When a provider changes:

- `issuer` must match the identifier trusted by the application.
- `jwks_uri` must pass network/trust policies.
- HTTPS and certificate validation must remain intact.
- Redirects/host changes must be evaluated against SSRF.
- Metadata versions/capabilities must be diffed intentionally.

Never fetch metadata/JWKS from arbitrary `iss` or `jku` claims supplied by a token.

### 13.2. Discovery Contract Tests

A test can verify a metadata snapshot:

~~~java
assertEquals(
    "https://id.example.test/realms/orders",
    metadata.getIssuer().toString()
);

assertTrue(
    trustedJwksHosts.contains(metadata.getJwksUri().getHost())
);
~~~

This is pseudocode since metadata types depend on the client/discovery library. The intent is exact issuer matching and a trusted JWKS host policy. Never use an overly broad host allowlist when the trust boundary requires only one specific host.

### 13.3. Never Let Discovery Tests Auto-Modify Production Trust

Contract tests can detect a new issuer, yet **must never automatically add a new issuer to the production allowlist** merely because a discovery endpoint returned it. Trust changes require review, security approval, and organizational release policies.

## 14. CI Pipeline for the Controlled Token Fixture Suite

An effective pipeline layers tests by speed and external dependencies:

~~~text
Pull request:
  1. Compile/test fixtures factory
  2. JWT decoder tests with local keys
  3. JWKS rotation tests with local stub
  4. Opaque introspection tests with HTTP stub
  5. SecurityFilterChain authorization tests
  6. Tenant/issuer negative tests

Scheduled / release candidate:
  7. Sandbox issuer discovery contract
  8. Sandbox JWKS and key rotation compatibility
  9. Sandbox opaque introspection contract
 10. Compatibility report and approval gate
~~~

There is no need to hit the production IdP on every pull request. Unit/contract fixtures must be reproducible and offline; sandbox tests verify live integration on a schedule or prior to release.

### 14.1. PR Tests Must Be Deterministic

- Fixed test clock.
- Dedicated test signing keys.
- Local JWKS stub/endpoint.
- Introspection stub.
- No real tokens.
- No reliance on provider uptime.
- No sleeping to wait for token expiration.
- No parallel execution across tests sharing mutable key/metadata state if it introduces races.

### 14.2. Sandbox Contract Suite

Sandbox tests should:

- Use a dedicated client registration with minimal scopes.
- Use short-lived tokens.
- Use synthetic user/service principals.
- Have zero access to production data.
- Redact Authorization headers/bodies from HTTP logs.
- Capture issuer metadata/JWKS versions and response schemas.
- Perform only reversible test operations.
- Clean up test data per policy.

Never call production endpoints just to harvest tokens as fixtures.

### 14.3. Compatibility Report

~~~text
Issuer alias: orders-sandbox
Issuer contract version: 4
Fixture set version: 3
Application version: 2.8.0

JWT valid baseline: PASS
Wrong issuer: PASS (rejected)
Wrong audience: PASS (rejected)
Old/new key overlap: PASS
Unknown kid: PASS (rejected)
Scope mapping: PASS
Tenant mismatch: PASS (denied)
Opaque active/inactive: PASS
Introspection timeout: PASS (fail closed)
OIDC discovery metadata: PASS
~~~

This is an illustrative report format. **PASS on a negative test** means the system rejected properly, not that the request succeeded.

## 15. Compatibility Workflow When an Issuer Announces Changes

### Step 1 — Pinpoint the Exact Change

Request release notes/contract diffs from the issuer:

- When does the change take effect?
- Is there an overlap window?
- Does the issuer identifier change?
- Does the audience change?
- When are new keys published and old keys retired?
- How do scopes/roles/claims change?
- Does the opaque introspection response schema change?
- Does the discovery/JWKS URI host change?

Never inspect a single sample token and guess the entire scope of the change.

### Step 2 — Create Fixtures for Old and New States

Key rotation example:

~~~text
old JWKS + old key token
old+new JWKS + old key token
old+new JWKS + new key token
new JWKS only + new key token
new JWKS only + old key token
~~~

Scope migration example:

~~~text
old claim: scope = "orders.read"
new claim: scp = ["orders.read"]
missing scope
unexpected scope
~~~

Each fixture pairs with its expected outcome and rollout phase.

### Step 3 — Run Tests Locally and in CI

Run decoder, introspection, security chain, tenant, and negative tests with the fixtures. Ensure failures happen cleanly at the right layer—never weaken validators just to make all fixtures pass.

### Step 4 — Assess Backward Compatibility

- How long will old tokens continue to be issued or remain valid?
- Is temporary dual trust required?
- Are there issuer mapping/identity collisions?
- Are any clients not yet upgraded?
- Did any API scope change semantics?
- Do any caches/replicas still hold old keys/claims?

### Step 5 — Roll Out with Overlap and Observe

- Publish the reviewed new trust config.
- Verify new keys/issuers in sandbox.
- Deploy canary.
- Monitor failure categories by issuer alias.
- Keep a clear rollback path.
- Remove old issuers/keys/claims only after token lifetime/cache windows elapse and migration finishes.

### Step 6 — Close Out the Legacy Contract

- Remove old issuer/key trust on schedule.
- Remove legacy claim mappings.
- Retire old fixtures from active suites or move them to a regression archive if still valuable.
- Update manifest/profile versions.
- Retain negative tests proving revoked legacy issuers are rejected.

Never keep two trusted issuers forever solely to avoid updating clients; the old trust domain may no longer be authorized.

## 16. Do Not Compare Compact JWTs by Fixed String Equality

A JWT has the structure:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

When tests mint fresh tokens on each run:

- `iat`/`exp` differ.
- Signatures differ when signing keys change.
- Header serialization/key order can vary.
- `jti` may be freshly generated.

Therefore, avoid asserting compact JWTs by exact string equality unless specifically testing serialization/canonicalization.

Assert the semantic contract instead:

- Decoder returns the right issuer/subject/audience.
- Authorities match.
- Invalid conditions are rejected.
- Security endpoints return the right status codes.
- Key ID resolves from the trusted JWKS.
- Claim types/mappings hold.

If snapshot-testing token bytes, pin both the key and clock and be clear about what the test protects. Byte snapshots never replace signature/validator integration tests.

## 17. Protecting Secrets and Test Data

### 17.1. Never Commit Production Credentials

Keep out of fixture repositories:

- Production access tokens.
- Refresh tokens.
- ID Tokens containing personal data.
- Client secrets.
- Private signing keys.
- Production-valid mTLS private keys/certificates.
- Raw introspection request logs.
- Authorization headers in CI artifacts.

JWT payloads are normally Base64URL-encoded, **not encrypted**; anyone holding the token can read claims. Opaque tokens are bearer credentials even though their contents cannot be decoded.

### 17.2. Test Key and Secret Rotation

Test keys may be versioned in test resources when valid strictly for tests. However:

- Never share them with production.
- Never grant trust to test JWKS in production configs.
- Never publish private keys in public artifacts.
- Never reuse one test HMAC secret across unrelated systems.
- Whenever a test key changes, update the fixture manifest and public JWKS snapshot together.

### 17.3. Logs and Failure Diagnostics

A safe log entry:

~~~text
event=jwt_validation_failed
issuer_alias=orders-sandbox
failure=WRONG_AUDIENCE
request_id=req-test-014
fixture_id=wrong-audience
~~~

Avoid:

~~~text
Authorization: Bearer eyJ...
introspection client_secret=...
private_key=...
~~~

Logging a fixture ID is fine because it is a test identifier, yet never log raw token strings or full introspection request bodies.

## 18. Common Misconceptions

### "A valid JWT JSON payload is enough to test a Resource Server"

No. Unsigned payloads lack cryptographic verification; the decoder must verify compact tokens against trusted keys.

### "Using mockJwt() tests signature verification"

No. Mock helpers build an Authentication for authorization tests; separate decoder/JWKS tests are required.

### "Production-captured tokens make the best fixtures"

No. They are live bearer credentials and may contain personal claims; use sandbox/synthetic test tokens.

### "One valid token suffices to test issuer compatibility"

No. You need negative fixtures plus key rotation, audience, scopes, claims, tenant, introspection, and discovery scenarios.

### "If the issuer changes its URL, just edit the property"

Old tokens still carry the old `iss`. Migrations need controlled overlap, identity mapping, and a sunset schedule.

### "If JWKS has the new key, the Resource Server uses it immediately"

Decoders may cache JWKS. Test refresh/unknown-`kid` behavior and rollout overlap against your library's actual behavior.

### "No decoder error means the token is authorized to call the API"

Successful authentication never guarantees scopes, roles, tenants, ownership, or ACLs.

### "Switching the scope claim from string to array stays compatible automatically"

Not by default. Converters and provider contracts need explicit data-type/schema tests.

### "`kid` in a token is trustworthy"

No. `kid` is only a selector inside a trusted key set; never fetch keys from a token-advertised URL.

### "Introspection timeout equals `active:false`"

No. Timeouts are dependency failures, whereas `active:false` is an inactive-token outcome.

### "Adding a new issuer in discovery metadata makes it trusted"

No. A trusted issuer allowlist and security review remain mandatory; metadata never confers trust by itself.

### "Keep the old issuer forever so tokens never break"

That widens trust past its intended lifespan. Use a migration window, measure usage, and remove old trust on schedule.

## 19. Matrix for Choosing Test Types per Change

| Issuer Change | Unit Fixture | Integration Test | Sandbox Test |
|---|---|---|---|
| JWT claim name/type | Yes | Yes, via filter/authority mapping | When confirming live provider |
| Issuer URL | Yes, old/new fixtures | Yes, resolver/decoder | Yes, discovery |
| Audience | Yes, positive/negative | Yes, 401 behavior | Yes if provider alters token audience |
| Signing key rotation | Yes, old/new test keys | Yes, JWKS stub/cache | Yes, before rollout |
| Algorithm | Yes, key/alg fixtures | Yes, decoder test | Yes if provider changes it |
| Opaque active/schema | Yes, JSON fixtures | Yes, introspector HTTP stub | Yes, sandbox introspection |
| Client auth method | Yes, request contract | Yes, mock endpoint | Yes, real provider |
| Scope semantics | Yes, mapping fixtures | Yes, endpoint 403/allow tests | Yes if issuer alters scopes |
| Tenant claim | Yes, claim fixtures | Yes, service ACL tests | Only when provider contract changes |
| OIDC metadata | Snapshot tests | Yes, mock discovery/JWKS | Yes before release |
| Provider outage | Simulated failure | Yes, timeout/5xx tests | Never intentionally break production |
| Cache/revocation | Deterministic clock/state | Yes, integration | Yes in sandbox if semantics need proof |

Not every change requires calling sandbox. Most regressions can be caught with local fixtures; sandbox confirms the real issuer adheres to the contract.

## 20. Checklist for Applying Controlled Token Fixture Suites

- [ ] Every fixture has an ID, purpose, issuer alias/profile, and expected outcome.
- [ ] The fixture set has its own version.
- [ ] Synthetic users, tenants, and clients are used throughout.
- [ ] No production tokens, refresh tokens, or client secrets are stored.
- [ ] JWT signature tests use test private keys and trusted test public keys/JWKS.
- [ ] Tests cover wrong issuer, wrong audience, expiry, nbf, bad signature, and unknown kid.
- [ ] Algorithm allowlist and token type/profile are checked per contract.
- [ ] Required/optional claims and data types are verified.
- [ ] Scope/role mappings have both positive and negative fixtures.
- [ ] Tenant mismatches and cross-issuer identity collisions are tested.
- [ ] JWKS key rotation covers old/new overlap and unknown key cases.
- [ ] Discovery metadata checks exact issuer and trusted JWKS URI.
- [ ] Opaque introspection covers active true/false, timeouts, 401/403/429/5xx, and schema drift.
- [ ] Authentication acceptance is separated from authorization decisions.
- [ ] Test clock is fixed—never sleep waiting for token expiration.
- [ ] Unit/CI tests do not depend on production issuer availability.
- [ ] Sandbox contract tests use minimal test clients and scopes.
- [ ] Logs and test artifacts are redacted.
- [ ] Issuer migrations have a dual-trust window and an old-issuer sunset.
- [ ] CI reports clearly record fixture version and issuer contract version.

## 21. Summary

A controlled token fixture suite is a **reproducible contract test suite** spanning valid tokens, intentionally invalid tokens, public JWKS, introspection responses, and metadata snapshots. It lets a Resource Server catch issuer changes before they reach production.

Remember:

- **JWT fixtures must be genuinely signed** to test the decoder; JSON payloads or `mockJwt()` only test part of the pipeline.
- **Test keys are strictly for tests**; never store or replay production bearer credentials.
- **Issuer, audience, algorithm, key ID, time, type, and claims** can all change and need dedicated fixtures.
- **JWKS rotation** must test overlap between old/new keys, cache refreshes, and unknown keys.
- **Opaque introspection** must distinguish `active:false` from client authentication errors, rate limits, and timeouts.
- **OIDC discovery** must enforce exact issuer and trusted JWKS URIs; never trust arbitrary metadata/URLs.
- **Authentication and authorization** are separate layers; a valid token can still receive 403 from scope/tenant/ACL rules.
- **Issuer migrations** require allowlists, compatibility tests, overlap windows, identity mapping, and sunsetting.
- CI should run deterministic fixtures on every pull request, while sandbox contract tests verify real integration on schedule or before releases.

### References

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Multi-tenancy for JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security API — JwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security API — JwtTimestampValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html)
- [Spring Security API — NimbusJwtEncoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html)
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
