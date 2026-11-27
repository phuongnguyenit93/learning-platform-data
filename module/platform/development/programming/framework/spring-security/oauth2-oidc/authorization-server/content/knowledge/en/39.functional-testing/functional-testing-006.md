# Testing Token Exchange and scope/audience restrictions

Token Exchange allows an authorized client to exchange an input token for a new token scoped to a different access context. For example, a gateway receives an access token meant for `orders-api` and then needs to call `shipping-api`. Forwarding the original token directly could give the shipping service broader permissions than necessary. With OAuth 2.0 Token Exchange (RFC 8693), the Authorization Server can issue a new token whose subject, actor, audience, scopes, and lifetime are restricted according to a delegation policy.

Functional testing of this flow must prove two things: valid requests receive the exact token meant for the target resource, and over-privileged requests are rejected or narrowed down per published policy. Checking only HTTP 200 or the presence of `access_token` is not enough. You must inspect the new token, authorization persistence, the target Resource Server, and negative cases to catch confused deputy or privilege escalation bugs.

## 1. Defining the Token Exchange contract

RFC 8693 defines the grant type:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

Common parameters:

| Parameter | Meaning | Testing requirement |
|---|---|---|
| `grant_type` | Identifies the Token Exchange grant | Server recognizes the grant and does not confuse it with refresh token |
| `subject_token` | Token representing the subject being exchanged | Signature/issuer/audience/expiration and token status must be verified |
| `subject_token_type` | Type of the input token | Only configured types are accepted, e.g., access token |
| `actor_token` | Token of the actor performing the action on behalf of the subject, if any | Independently verify the actor and delegation relationship |
| `actor_token_type` | Type of the actor token | Do not infer token type from untrusted contents |
| `requested_token_type` | Token type the client wants to receive | Issue only token types supported by the server |
| `audience` | Target resource/audience | Accept only audiences within the client and subject policy |
| `resource` | Target resource URI per Resource Indicators, if supported | Verify exact URI and map to an allowed resource |
| `scope` | Permissions requested by the client in the new token | Do not grant more than the subject, client, and target resource allow |

Example request:

```bash
curl -X POST https://identity.example.com/oauth2/token \
  -u 'orders-gateway:<client-secret>' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=urn:ietf:params:oauth:grant-type:token-exchange' \
  --data-urlencode 'subject_token=<subject-access-token>' \
  --data-urlencode 'subject_token_type=urn:ietf:params:oauth:token-type:access_token' \
  --data-urlencode 'requested_token_type=urn:ietf:params:oauth:token-type:access_token' \
  --data-urlencode 'audience=shipping-api' \
  --data-urlencode 'scope=shipment.create'
```

The values in the command are placeholders. The client must authenticate using its registered method. Do not put secrets, real tokens, or user data into source control, lab docs, or logs.

A successful response typically looks like:

```json
{
  "access_token": "<new-access-token>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "shipment.create"
}
```

`scope` in the response may be omitted when it equals the requested scope per OAuth token response rules. Therefore, verify actual permissions inside the JWT or via introspection; do not rely solely on whether the response has a `scope` field. The output token can also be an opaque token instead of a JWT, depending on server configuration.

## 2. Designing a policy to restrict scopes and audiences

Before writing tests, define the policy clearly for a business flow. For example, the `orders-gateway` gateway needs to create a shipment after processing an order:

| Component | Illustrative value |
|---|---|
| Client performing the exchange | `orders-gateway` |
| Subject token issuer | `https://identity.example.com` |
| Subject token audience | `orders-api` |
| Subject token scopes | `orders.read shipment.request` |
| Allowed target audience | `shipping-api` |
| Allowed target scope | `shipment.create` |
| Prohibited sensitive scopes | `payment.refund`, `admin` |
| Maximum lifetime of new token | 5 minutes or shorter based on remaining lifetime of subject token |

An authorization decision can be expressed as the intersection of multiple permission sets:

```text
S_granted = intersection(
    S_requested,
    S_subject,
    S_client_policy,
    S_resource
)
```

Where:

- `S_requested` is the scopes requested by the client.
- `S_subject` is the permissions represented by the subject token and permitted for delegation by policy.
- `S_client_policy` is the scopes the client is allowed to exchange.
- `S_resource` is the scopes supported by the target resource.

If the client requests `shipment.create payment.refund`, the result cannot include `payment.refund` when the gateway policy allows only shipment actions. The application must choose a consistent behavior: reject the entire request if any out-of-policy scope is present, or grant only the valid intersection. Either approach can be designed, but it must be documented, tested, and applied uniformly. Never silently grant broader scopes than requested.

Audience must be controlled independently from scope. A token with `shipment.create` but an audience of `admin-api` could still be misused on another resource. Issue tokens only for audiences allowlisted per client, subject, and delegation relationship. If the client sends multiple `audience` or `resource` values, validate the entire list and do not accept an unauthorized value just because another value is valid.

The new token's lifetime should be bounded by policy and the remaining lifetime of the subject token. If the input token is about to expire, do not mint a new token with a longer lifetime merely because the client requested it. If the subject token is revoked or no longer valid under policy, the exchange must fail.

## 3. Layering the tests

A solid test suite has four layers. Each layer verifies one part of the contract and helps isolate failures faster.

| Layer | Component | What to prove |
|---|---|---|
| Policy unit tests | Service computing audience, scopes, lifetime, and delegation | Authorization decisions are correct for each client/subject/resource combination |
| Provider tests | Custom grant `AuthenticationProvider` or corresponding provider | Validates input token, client, and policy; failures mint no token |
| Endpoint integration tests | Token endpoint via MockMvc or real HTTP | Client authentication, request parsing, OAuth errors, and token responses are accurate |
| Resource Server integration tests | API receiving the new token | Only tokens with the right issuer, audience, and scopes are accepted |

If your Spring Authorization Server version provides a built-in Token Exchange implementation, test through that API. If the application extends the token endpoint with its own `AuthenticationConverter` and `AuthenticationProvider`, tests must exercise the actual converter and provider. Merely registering `AuthorizationGrantType` in `RegisteredClient` does not prove the grant is handled.

## 4. Preparing test data

Create dedicated fixtures per test or reset persistence between tests so tokens, authorizations, and revocation states do not leak across runs. A useful fixture set includes:

| Fixture | Required attributes |
|---|---|
| Valid client | `orders-gateway`, valid client authentication, Token Exchange grant permitted |
| Client disallowed from exchange | Registered client without permission to use the grant |
| Valid subject token | Trusted issuer, audience `orders-api`, scopes `orders.read shipment.request`, unexpired |
| Subject token with wrong audience | Audience `billing-api` or disallowed resource |
| Expired subject token | `exp` in the past |
| Subject token with wrong issuer/signature | Fails verification against declared trust configuration |
| Revoked subject token | Introspection or authorization state shows inactive/revoked |
| Valid actor token | Actor permitted by policy to act for the subject |
| Invalid actor token | Wrong issuer, expired, or lacking delegation relationship |
| Target resource | `shipping-api` supports `shipment.create`; `admin-api` is not on the allowlist |

For JWT fixtures, sign tokens with a dedicated test key and configure the decoder to trust only the test issuer/JWK Set. Do not use production tokens or disable signature verification just to make tests pass easily. For opaque tokens, mock introspection responses for active/inactive states, issuer, audience, and scopes as required by your implementation.

## 5. Testing scope and audience policies at the unit level

Separate authorization decisions from controllers and token serialization. A policy service can take the client, subject context, actor context, requested audiences, and requested scopes, then return a normalized decision or business error.

Illustrative service contract example:

```java
public interface TokenExchangePolicy {
    ExchangeDecision evaluate(ExchangeContext context);
}

public record ExchangeContext(
        RegisteredClient client,
        VerifiedToken subject,
        VerifiedToken actor,
        Set<String> requestedAudiences,
        Set<String> requestedScopes) {}

public record ExchangeDecision(
        Set<String> grantedAudiences,
        Set<String> grantedScopes,
        Instant expiresAt) {}
```

`VerifiedToken` and `ExchangeDecision` are illustrative application types. They must be constructed only after the token is verified; never construct them from untrusted claims or parameters. Using `Set` eliminates duplicate scopes/audiences and makes set intersection explicit.

Unit tests should cover:

1. Requested scopes are a valid subset: grant the exact requested scopes.
2. Requested scopes contain an out-of-policy permission: reject the whole request or narrow down per the chosen decision.
3. Requested scopes are empty: apply default scopes defined for the resource or reject if no default exists.
4. Client is valid but subject lacks the corresponding permission: do not grant that scope.
5. Subject has the permission but client is not allowed to delegate it: do not grant that scope.
6. Target resource does not support the scope: do not grant a scope that does not exist on the resource.
7. Requested audience is in the allowlist: grant that exact audience.
8. Audience is disallowed or mixes valid and invalid values: enforce the published all-or-nothing or filtering policy properly.
9. Input token is nearly expired: the new token does not exceed the maximum lifetime.
10. Actor is unauthorized: reject delegation even when subject and client are valid.

Example testing scope intersection:

```java
@Test
void grantsOnlyScopesAllowedBySubjectClientAndResource() {
    Set<String> requested = Set.of("shipment.create", "payment.refund");
    Set<String> subjectScopes = Set.of("shipment.create", "orders.read");
    Set<String> clientScopes = Set.of("shipment.create");
    Set<String> resourceScopes = Set.of("shipment.create", "shipment.read");

    Set<String> granted = policy.intersectScopes(
            requested, subjectScopes, clientScopes, resourceScopes);

    assertThat(granted).containsExactly("shipment.create");
    assertThat(granted).doesNotContain("payment.refund");
}
```

If the policy chooses to reject when disallowed scopes are present, the test must verify that the policy returns an error rather than returning a subset. What matters is that the behavior is intentional and never escalates privileges.

## 6. Testing the token endpoint with MockMvc

Endpoint tests must use the application's real filter chain, client authentication, converter/provider, and token generator. Mock dependencies outside the test boundary such as an introspection server or clock if needed, but do not mock the very policy you intend to verify.

Happy-path test example with a confidential client using HTTP Basic:

```java
@SpringBootTest
@AutoConfigureMockMvc
class TokenExchangeEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exchangesSubjectTokenForRestrictedAudienceAndScope() throws Exception {
        String subjectToken = tokenFixtures.validOrdersAccessToken();

        mockMvc.perform(post("/oauth2/token")
                        .with(httpBasic("orders-gateway", "test-secret"))
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("grant_type",
                                "urn:ietf:params:oauth:grant-type:token-exchange")
                        .param("subject_token", subjectToken)
                        .param("subject_token_type",
                                "urn:ietf:params:oauth:token-type:access_token")
                        .param("requested_token_type",
                                "urn:ietf:params:oauth:token-type:access_token")
                        .param("audience", "shipping-api")
                        .param("scope", "shipment.create"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access_token").isNotEmpty())
                .andExpect(jsonPath("$.issued_token_type").value(
                        "urn:ietf:params:oauth:token-type:access_token"))
                .andExpect(jsonPath("$.token_type").value("Bearer"));
    }
}
```

`tokenFixtures`, client registration, and the password encoder are test application fixtures. Endpoint path, client authentication method, and response fields must match the real implementation. Do not use `@WithMockUser` in place of client authentication at the token endpoint: a logged-in user and an OAuth client are two different principals.

After receiving the response, verify the new token the exact way the resource server will verify it. If the access token is a JWT, decode and verify its signature via the test decoder; if it is an opaque token, call the introspection endpoint or inspect authorization persistence in the test. Never just base64-decode a JWT and trust its claims.

## 7. Verifying claims and token responses

For a JWT access token, the claims/attributes to verify include:

| Claim/attribute | Expected condition |
|---|---|
| `iss` | Exact issuer of the Authorization Server |
| `sub` | Preserves the right subject per policy; never turns actor into subject unintentionally |
| `aud` | Contains only the allowed target resource, e.g., `shipping-api` |
| `scope` or `scp` | Contains only granted scopes per policy and chosen token format |
| `exp` | Does not exceed policy lifetime or remaining lifetime of subject token |
| `iat` | Valid issuance timestamp, not in the future beyond allowed clock skew |
| `act` | Present only when the delegation profile uses an actor claim; value matches the verified actor |
| `jti` | If used, the new token has a distinct identifier per anti-replay/audit policy |

The scope claim name can depend on token format and converter. For opaque tokens, verify equivalent attributes via the introspection response, such as `active`, `sub`, `aud`, `scope`, `iss`, and `exp` if published by the server. Compare audience according to JWT data types and rules: `aud` may be a single string or an array of strings.

The token exchange response must verify `issued_token_type` matches the issued token type and `token_type` matches Bearer or another supported type. `expires_in` must align with the token's actual lifetime. If the response returns `scope`, that value must match the actual permissions; if the response omits `scope`, inspect the JWT/introspection to confirm permissions.

Example verifying a JWT with a decoder configured with a trusted issuer/JWK:

```java
Jwt jwt = jwtDecoder.decode(response.accessToken());

assertThat(jwt.getIssuer()).isEqualTo(URI.create("https://identity.example.com"));
assertThat(jwt.getSubject()).isEqualTo("user-123");
assertThat(jwt.getAudience()).containsExactly("shipping-api");
assertThat(jwt.getClaimAsStringList("scope"))
        .containsExactly("shipment.create");
assertThat(jwt.getExpiresAt()).isBeforeOrEqualTo(policyExpiry);
```

This example assumes a JWT access token with a list-typed `scope` claim. If the application's token generator uses a string-typed `scope` claim, `scp`, or opaque tokens, write matching assertions. What stays constant is verifying signature/active state, issuer, subject, audience, scopes, and expiration.

## 8. Testing rejection cases

Do not test only valid requests. The following negative cases help uncover missing validation or bypassed policies:

| Scenario | Expected result |
|---|---|
| Unregistered client or wrong secret | Client authentication fails; no token issued |
| Valid client not permitted to use Token Exchange | Grant rejected per policy |
| Missing `subject_token` or `subject_token_type` | Invalid request rejected |
| Unsupported `subject_token_type` | Rejected; never guess token type |
| Subject token with invalid signature or issuer | Rejected with `invalid_grant` or matching OAuth error per implementation |
| Expired or not-yet-valid subject token | Exchange rejected |
| Inactive or revoked subject token | Exchange rejected |
| Subject token with audience unsuitable for policy | Rejected or handled per defined delegation rules; no default access granted |
| Target audience not on allowlist | Target rejected per published error mapping |
| Scopes include permissions exceeding policy | Rejected or narrowed to intersection per policy; never grant excess scopes |
| Invalid actor token | Delegation rejected |
| Unsupported `requested_token_type` | Requested token type rejected |
| Subject token used by a different client | Accepted only if delegation relationship explicitly permits it |
| Request missing or repeating parameters illegally | Rejected per endpoint parser and profile |

The exact OAuth error depends on the error type and the profile implemented by the server. For instance, `invalid_client`, `unauthorized_client`, `unsupported_grant_type`, `invalid_request`, `invalid_grant`, and `invalid_scope` have distinct meanings. If the implementation uses an extension error for an invalid target/resource, document and test that exact error code. Never turn all errors into HTTP 500 or a 200 response with an empty token.

Example test verifying that out-of-policy scopes are rejected:

```java
@Test
void rejectsExchangeWhenRequestedScopeExceedsPolicy() throws Exception {
    String subjectToken = tokenFixtures.validOrdersAccessToken();

    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("orders-gateway", "test-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type",
                            "urn:ietf:params:oauth:grant-type:token-exchange")
                    .param("subject_token", subjectToken)
                    .param("subject_token_type",
                            "urn:ietf:params:oauth:token-type:access_token")
                    .param("audience", "shipping-api")
                    .param("scope", "shipment.create payment.refund"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_scope"));
}
```

This test assumes the policy rejects the entire request when an out-of-allowlist scope is present and maps the error to `invalid_scope`. If the system chooses to narrow down scopes instead, replace the assertion to verify the token contains only `shipment.create` and not `payment.refund`. Do not assert status codes rigidly if the implementation uses a different error handler; verify the exact defined OAuth contract.

After every rejected case, verify that no new authorization/token was persisted. You can check via `OAuth2AuthorizationService`, the test repository, or introspection. This is critical for catching providers that mint or save tokens before completing full policy validation.

## 9. Testing actors and delegation

If the flow uses `actor_token`, subject and actor must be verified independently. The subject is the user or workload whose access is being delegated; the actor is the client/service acting on the subject's behalf. Never take `actor` from a request parameter and copy it straight into token claims.

Required tests:

- A valid, trusted-issuer, unexpired actor token is accepted when the client has delegation permission.
- An actor token with wrong issuer, invalid signature, expiration, or inactive state is rejected.
- A valid actor without a delegation relationship to the subject is rejected.
- A client permitted to exchange tokens but not permitted to use a specific actor is still rejected.
- The new token preserves `sub` and represents the actor via the chosen claim/profile, such as `act` when implementing the RFC 8693 JWT actor claim.
- Multi-hop delegation chains have bounded depth and cannot form actor cycles.

If the application does not use actor tokens, tests must verify that the server does not infer an actor from headers or untrusted request data. Audit the subject and the client performing the exchange using protected internal identifiers.

## 10. Testing the Resource Server receiving the new token

Token Exchange is complete only when the target Resource Server accepts the new token properly. Use a test Resource Server with two endpoints:

```java
@RestController
class ShippingController {

    @GetMapping("/shipments")
    @PreAuthorize("hasAuthority('SCOPE_shipment.read')")
    List<String> listShipments() {
        return List.of("shipment-001");
    }

    @PostMapping("/shipments")
    @PreAuthorize("hasAuthority('SCOPE_shipment.create')")
    String createShipment() {
        return "created";
    }
}
```

The Resource Server must verify issuer and audience. You can combine a validator for the expected audience with the issuer validator:

```java
OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains("shipping-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token", "Invalid audience", null));

JwtDecoder decoder = JwtDecoders.fromIssuerLocation("https://identity.example.com");
((NimbusJwtDecoder) decoder).setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer("https://identity.example.com"),
                audienceValidator));
```

This snippet illustrates composing an issuer validator and an audience validator; use the application's actual `JwtDecoder` bean and avoid creating competing decoders. `JwtDecoders.fromIssuerLocation` requires discovery/JWKS to be reachable in the test environment; you can use a decoder backed by a fixed test JWK Set for integration tests.

End-to-end tests must prove:

1. A valid exchanged token for `shipping-api` can call the endpoint matching its granted scope.
2. That same token calling an endpoint requiring an ungranted scope gets `403`.
3. A token with audience `orders-api` gets `401` at `shipping-api`, even with a valid signature.
4. An expired token or wrong issuer gets `401`.
5. The new token is not accepted by another resource merely because it shares the same issuer.
6. A token with a valid scope but wrong audience is still rejected.

Test both `401 Unauthorized` (invalid or unaccepted token) and `403 Forbidden` (valid token lacking authority). Distinguishing the two statuses pinpoints whether a failure lies in token verification or endpoint authorization.

## 11. Testing lifetimes, revocation, and consistency

Token Exchange creates a new authorization/token, so its lifecycle must be tested. Use a controllable clock in unit tests to avoid real-time dependencies. For integration tests, mint short-lived tokens in the test environment and verify behavior after expiration.

Cases to check:

- `expires_in` and `exp` match the lifetime permitted by policy.
- A nearly expired input token does not produce a new token outliving delegation limits.
- If the subject token is revoked prior to exchange, the request fails.
- If the new token is revoked, the Resource Server handles it per the designed revocation/introspection mechanism or JWT lifetime.
- If the new token is a self-contained JWT, explicitly test revocation limits: a resource server checking only signatures may keep accepting the JWT until `exp` without a state check.
- Two concurrent exchange requests do not exceed delegation quotas or yield inconsistent permissions due to stale policy reads.
- All instances share the same client registrations, policies, authorization persistence, and signing keys.

If the policy enforces quotas or exchange count limits, test concurrency with parallel requests and verify the limit is enforced in the shared store. Do not rely on in-memory counters inside a single instance when running multiple nodes.

## 12. Auditing and protecting test data

Audit events should record which client requested the exchange, which subject was represented, which actor participated, which audiences and scopes were granted, the outcome, timestamp, and correlation ID. Never write `subject_token`, `actor_token`, client secrets, new access tokens, or full form bodies to logs.

In tests, use synthetic tokens and dedicated test keys. Clean up authorization and token fixtures after tests. If debug logging for Spring Security or HTTP clients is enabled, verify logs do not contain `Authorization: Basic`, Bearer tokens, or secrets. Log tests should assert the absence of known secret strings.

## 13. Functional test matrix

| Group | Test case | Expected outcome |
|---|---|---|
| Client | Valid client permitted to exchange | Request processed |
| Client | Wrong secret or unauthorized client | Rejected, no token issued |
| Subject | Token with valid issuer/signature/audience/lifetime | Proceeds to policy evaluation |
| Subject | Token with wrong signature, issuer, audience, expired, or revoked | Exchange rejected |
| Actor | Valid, authorized actor token | Output token represents delegation accurately |
| Actor | Invalid actor or no relationship to subject | Rejected |
| Scope | Scopes within policy intersection | Token holds only permitted scopes |
| Scope | Scopes exceed subject/client/resource permissions | Rejected or narrowed per chosen policy |
| Audience | Target audience on allowlist | Token has exact target audience |
| Audience | Audience outside allowlist or multiple audiences with unknown value | Rejected per policy; no overly broad token issued |
| Token response | Token type and lifetime accurate | Response and token claims match |
| Resource Server | Token with valid audience and scope | Endpoint accessible |
| Resource Server | Wrong audience or missing scope | Returns 401 or 403 respectively per error type |
| Persistence | Failed request | No new authorization/token persisted |
| Audit | Successful/failed exchange | Traceable event emitted without leaking tokens |

## 14. Completion checklist

- [ ] Verified which clients are allowed Token Exchange and that the grant is actually processed at the token endpoint.
- [ ] Subject token verified for signature or introspection, issuer, audience, lifetime, and status.
- [ ] Actor token and delegation relationship verified if the flow uses an actor.
- [ ] Target audiences/resources taken solely from server-side policy allowlists.
- [ ] New token scopes never exceed subject, client, and target resource permissions.
- [ ] New token lifetime honors delegation limits and remaining input token lifetime.
- [ ] Token response, JWT/introspection claims, and authorization persistence are consistent.
- [ ] Resource Server verifies issuer, audience, and scopes; both 401 and 403 tested.
- [ ] Negative cases create no new tokens or authorizations.
- [ ] Concurrency and multi-instance tests run if policy has quotas or distributed persistence.
- [ ] Logs/audits contain no raw tokens, secrets, or credentials.

A reliable Token Exchange test suite verifies the full path from client authentication, subject/actor token validation, scope/audience policy, and token generation through to the Resource Server. Only when every layer proves that permissions stay within defined boundaries does Token Exchange genuinely narrow token scope across services rather than becoming a wider privilege path.
