# Multi-Tenant Access with a Valid Token That Does Not Belong to the Requested Resource

## 1. A Valid Token Does Not Grant Access to Every Tenant

In a multi-tenant Spring Security OAuth 2.0 Resource Server application, an access token can be completely valid yet the request must still be denied access to the requested resource.

Example:

- Alice signs in to `tenant-a` and receives an access token with a valid `iss`, `aud`, signature, and timestamps, plus the claim `tenant_id=tenant-a`.
- Alice calls `GET /api/tenants/tenant-a/orders/100`, where order 100 belongs to tenant A.
- Using the exact same token, Alice calls `GET /api/tenants/tenant-b/orders/900`. The token remains cryptographically valid, yet it does not authorize Alice to read resources owned by tenant B.

This is the distinction between **authentication** and **authorization**:

- Authentication establishes that the credential is trustworthy and identifies the principal.
- Authorization determines whether that principal is allowed to perform an action on the specific tenant and resource.

Validating the JWT signature, issuer, and audience proves only that the token was minted by a trusted issuer and intended for the right API. Audience `orders-api` does not mean the caller may read every order across every tenant.

A strong integration test must prove both:

1. Valid tokens authenticate cleanly through the Resource Server.
2. Requests targeting an unauthorized tenant or resource are denied before data or side effects occur.

## 2. Identity Layers in a Multi-Tenant System

Before writing tests, clarify which identifiers the application binds permissions to.

| Identifier | Example | What Is It Used For? |
|---|---|---|
| Issuer | `https://id.example.test/realms/shop` | Identifies the security domain that issued the token |
| Subject | `user-123` | Identifies the principal within that issuer |
| Client ID | `orders-web` | Identifies the OAuth client calling the API |
| Audience | `orders-api` | Identifies the intended resource server |
| Active tenant | `tenant-a` | Tenant context represented by the current token/session |
| Resource tenant | `tenant-a` | Tenant owning the order/customer/document |
| Resource ID | `order-100` | Identifier of the specific record |
| Scope | `orders.read` | Coarse-grained API permission |
| Role/permission | `ORDER_APPROVER` | Domain permission or role inside the tenant |

A token might carry:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "orders-web",
  "scope": "orders.read",
  "tenant_id": "tenant-a",
  "exp": 2000000300
}
~~~

This token passes issuer, audience, signature, and timestamp validation. Yet it is only input to the authorization policy. The Resource Server still needs to check:

- Does the requested tenant match the token's active tenant?
- Is the principal still a member of that tenant?
- Does the resource ID actually belong to that tenant?
- Does the principal hold permissions on that resource type and action?
- Does the token carry the required scope?

Never treat a `tenant_id` claim as a replacement for all permission checks. If a user can belong to multiple tenants, the claim may represent only the current tenant context; membership and resource permissions may still require database verification.

## 3. Access Patterns to Distinguish

### 3.1. Wrong Tenant in the URL

Token representing tenant A:

~~~http
GET /api/tenants/tenant-a/orders/100 HTTP/1.1
Authorization: Bearer <TOKEN-A>
~~~

Request targeting tenant B:

~~~http
GET /api/tenants/tenant-b/orders/900 HTTP/1.1
Authorization: Bearer <TOKEN-A>
~~~

Token A is valid, but the path requests tenant B. If the API binds tenants by path, the second request must be rejected.

### 3.2. Right Tenant Path, Resource Owned by Another Tenant

This is a distinct bug and very easy to miss:

~~~http
GET /api/tenants/tenant-a/orders/900 HTTP/1.1
Authorization: Bearer <TOKEN-A>
~~~

Suppose order 900 actually belongs to tenant B. The path tenant matches the token, while the resource ID was guessed or copied from another response.

If the query uses only:

~~~java
repository.findById(orderId);
~~~

the application can leak tenant B's data. Queries must constrain by tenant:

~~~java
repository.findByIdAndTenantId(orderId, tenantId);
~~~

This is a form of **Insecure Direct Object Reference (IDOR)** or broken object-level authorization: a user with a valid token reads an object outside their allowed scope.

### 3.3. Right Tenant, User Lacks Membership

A token may carry `tenant_id=tenant-a` even though the user's membership was revoked or modified after token issuance.

If policy requires active membership, the Resource Server/application must verify current membership status. Relying solely on a stale claim keeps access alive after a user is removed from a tenant.

### 3.4. Right Tenant, Insufficient Resource Permissions

A user may be a member of tenant A yet only be allowed to view their own team's orders or specific data types.

Tenant authorization and resource authorization are two layers:

~~~text
Principal
  -> Is member of tenant A?
  -> Has orders.read scope?
  -> Can read this specific order?
  -> Is order in tenant A?
~~~

A test that only compares tenant IDs does not prove ownership, team boundaries, or fine-grained permission rules work.

## 4. Choosing the Tenant Context Source Explicitly

An API can resolve the tenant from the path, subdomain, header, or access token. Clearly separate which sources act as selectors and which serve as authorization proof.

### 4.1. Tenant ID in the Path

Example:

~~~text
GET /api/tenants/{tenantId}/orders/{orderId}
~~~

The path parameter is the tenant the caller asks for. The server checks it against the active tenant or verifies membership.

Never treat a path parameter as proof the caller has access. A client can swap `tenantId` to any other tenant.

### 4.2. Tenant ID in a Header

Example:

~~~http
X-Tenant-ID: tenant-a
~~~

A header can let a client choose an active tenant context, but because it is caller-supplied it cannot grant permission. If a token is valid only for tenant A, changing the header to tenant B must be rejected.

Never let a filter read `X-Tenant-ID` and establish tenant context without checking it against the token and membership policy.

### 4.3. Tenant ID in the Subdomain

Example:

~~~text
https://tenant-a.api.example.test/orders/100
~~~

A gateway or application can extract the tenant from the Host header. Host is also request input; validate it against trusted routing and principal permissions. Never infer authorization simply because a hostname contains a tenant ID.

### 4.4. Tenant ID in the Request Body

For resource creation:

~~~json
{
  "tenantId": "tenant-b",
  "description": "New order"
}
~~~

If the token is scoped only to tenant A, the client must not be able to specify tenant B in the body to create data there.

A safe design derives the tenant from the authorized security context. If the API must accept a tenant ID in the body, validate that it matches the authorized tenant before writing.

### 4.5. Tenant Source Matrix

| Source | Can Select Tenant? | Proves Authorization on Its Own? |
|---|---|---|
| Verified claim in access token | Yes | Only within the claim's semantics and policy |
| Path parameter | Yes | No |
| Client-sent header | Yes | No |
| Subdomain/Host | Yes | No |
| Request body | Possibly | No |
| Database membership/ACL | Used to verify | Yes, per active policy |
| Trusted gateway metadata | Possibly | Only when the sender is authenticated and policy defines it |

If the application supports multiple tenants per token, do not force a single `tenant_id` claim into a global rule. You can use membership lookups or a tenant-specific authorization manager, provided the policy is consistent and tested.

## 5. Multi-Tenant Authorization Models

A baseline policy may require all of the following:

1. Authenticated JWT.
2. `orders.read` scope present.
3. Requested tenant is permitted for the principal.
4. Order belongs to the requested tenant.
5. Principal is authorized to read that order.

### 5.1. Active-Tenant Policy Check

Example when the application allows a single active tenant in the token:

~~~java
@Component("tenantAccess")
public class TenantAccessPolicy {

    public boolean canAccess(
            Authentication authentication,
            String requestedTenantId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        String tokenTenant =
            jwtAuth.getToken().getClaimAsString("tenant_id");

        return tokenTenant != null
            && tokenTenant.equals(requestedTenantId);
    }
}
~~~

Used in method security:

~~~java
@Service
public class OrderService {

    @PreAuthorize(
        "@tenantAccess.canAccess(authentication, #tenantId)"
    )
    public Order getOrder(String tenantId, UUID orderId) {
        return repository.findByIdAndTenantId(orderId, tenantId)
            .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

This example assumes a JWT principal where the tenant claim represents the active tenant. If the application uses opaque tokens, custom principals, or multi-tenant membership, the policy must inspect the matching principal contract.

Method security must be enabled, for example via `@EnableMethodSecurity`. Ensure parameter names are preserved or use parameter-reference syntax compatible with your build setup. Never place tenant checks exclusively in controllers while leaving services/repositories reachable through another path without checks.

### 5.2. Checking Current Membership

If users can belong to multiple tenants, the policy can combine claims and membership lookups:

~~~java
@Component("tenantAccess")
public class TenantAccessPolicy {

    private final TenantMembershipRepository memberships;

    public TenantAccessPolicy(
            TenantMembershipRepository memberships) {
        this.memberships = memberships;
    }

    public boolean canAccess(
            Authentication authentication,
            String requestedTenantId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        Jwt jwt = jwtAuth.getToken();
        String subject = jwt.getSubject();
        String issuer = jwt.getIssuer() == null
            ? null
            : jwt.getIssuer().toString();

        if (subject == null || issuer == null) {
            return false;
        }

        return memberships.existsActiveMembership(
            issuer,
            subject,
            requestedTenantId
        );
    }
}
~~~

In this model, the membership repository is the live source of truth. If the access token also carries a tenant allowlist claim, you can enforce both the claim and database membership per contract.

User identity must be scoped by issuer. `sub` is unique only within an issuer; with multiple issuers, the identity key typically needs the `(iss, sub)` pair or a normalized internal identity mapping.

### 5.3. Repositories Must Scope Queries by Tenant

Even with `@PreAuthorize` in place, queries should still filter by tenant:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    Optional<Order> findByIdAndTenantId(
        UUID id,
        String tenantId
    );
}
~~~

This protects against guessed/leaked IDs from another tenant, services invoked from alternate entry points, controller path-binding bugs, or missing authorization checks.

Never call `findById(id)` and filter by tenant only when serializing the response. Another tenant's data should never enter the application response path when the query can exclude it upfront.

### 5.4. Ownership or Team Policies

If an order also has an owner or team, queries or policies may add another constraint:

~~~java
Optional<Order> findByIdAndTenantIdAndOwnerId(
    UUID id,
    String tenantId,
    String ownerId
);
~~~

Alternatively, the service checks specific permissions after loading a tenant-scoped resource. Pick what fits the domain, but tests must prove both tenant isolation and resource-level authorization.

## 6. Designing Purposeful Test Data

An integration suite needs at least two tenants and multiple resources so scenarios can be clearly distinguished.

Example:

| Tenant | User | Order ID | Owner | Purpose |
|---|---|---|---|---|
| tenant-a | user-a | order-a1 | user-a | Valid resource for token A |
| tenant-a | user-b | order-a2 | user-b | Same tenant, different owner |
| tenant-b | user-c | order-b1 | user-c | Tenant B resource |
| tenant-b | user-a | order-b2 | user-a | Multi-tenant membership check if permitted by policy |

The two tenants must have distinct IDs and distinguishable data. Do not seed identical order IDs in both tenants if the test aims to prove tenant-scoped querying; ID collisions make results ambiguous. If the database uses a composite key `(tenant_id, id)`, test those exact semantics.

### 6.1. Token Fixtures

| Fixture | Claims | Expected |
|---|---|---|
| token-a-read | Valid issuer, audience orders-api, tenant A, read scope | Authentication accepted |
| token-b-read | Valid issuer, audience orders-api, tenant B, read scope | Authentication accepted |
| token-a-no-scope | Tenant A, missing orders.read | Authentication accepted; request gets 403 |
| token-a-no-tenant | Missing tenant claim | Rejected or denied per contract |
| token-wrong-aud | Audience billing-api | 401 |
| token-expired | Past exp | 401 |
| token-a-sub-unknown | Tenant A, subject has no membership | Denied |
| token-a-revoked-member | Tenant A, inactive membership | Denied if policy checks live membership |

Token A and token B can both be valid JWTs. The difference lies in tenant authorization, not signature validity.

### 6.2. Seeding Data via Repositories

In integration tests, seed data directly through repositories or test fixture builders:

~~~java
@BeforeEach
void seedOrders() {
    orderRepository.save(order("order-a1", "tenant-a", "user-a"));
    orderRepository.save(order("order-a2", "tenant-a", "user-b"));
    orderRepository.save(order("order-b1", "tenant-b", "user-c"));
}
~~~

Use a consistent test transaction/cleanup strategy. If the application handles requests in its own transactions, do not assume the test transaction wraps server transactions. Inspect persisted data after requests with a fresh repository call or appropriate transaction boundary.

## 7. Integration Tests Must Traverse the Decoder and Security Filter Chain

For integration verification, send a **signed compact JWT** in the Authorization header. Mocking `Jwt` directly or using `@WithMockUser` does not exercise the token authentication path.

Flow:

~~~text
Test private key
    |
    v
JWT fixture factory ----> signed compact token
                              |
                              v
WebTestClient / MockMvc -> Security filter chain
                              |
                              v
                       real JwtDecoder
                              |
                              v
                    JwtAuthenticationToken
                              |
                              v
                    tenant authorization
                              |
                              v
                  tenant-scoped repository
~~~

In the test context, the decoder can use a test public key along with issuer and audience validators. The private key is used only to mint fixtures. Never use production access tokens or signing keys.

### 7.1. Decoder Using a Test Public Key

Configuration example:

~~~java
@Bean
JwtDecoder jwtDecoder(
        RSAPublicKey testPublicKey) {

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withPublicKey(testPublicKey).build();

    OAuth2TokenValidator<Jwt> issuer =
        new JwtIssuerValidator(
            "https://id.example.test/realms/shop"
        );

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("orders-api")) {
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
            issuer,
            new JwtTimestampValidator(),
            audience
        )
    );

    return decoder;
}
~~~

This is a Servlet decoder example with an RSA public key. The test context must supply the public key matching the private key used by the fixture factory. In production, keys typically come from a trusted JWKS URI; this test intentionally avoids calling a real issuer.

If the application uses custom validators or converters, keep them in the test context to verify real wiring. Swap only the key source for the test key.

### 7.2. Minting Signed Test JWTs

You can use `NimbusJwtEncoder` with an RSA test key. Pseudocode:

~~~java
String issueToken(
        String subject,
        String tenantId,
        String scope,
        Instant now) {

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(TRUSTED_ISSUER)
        .subject(subject)
        .audience(List.of("orders-api"))
        .issuedAt(now)
        .expiresAt(now.plusSeconds(300))
        .claim("tenant_id", tenantId)
        .claim("scope", scope)
        .claim("client_id", "orders-test-client")
        .build();

    JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
        .keyId("orders-test-key")
        .build();

    return jwtEncoder.encode(
        JwtEncoderParameters.from(header, claims)
    ).getTokenValue();
}
~~~

This is an illustrative token factory. `jwtEncoder` must be configured with a test-only private key. To test audience/issuer failures, sign tokens with the trusted test key while changing the audience/issuer claim; to test signature failures, sign with a different key pair.

### 7.3. Sending Tokens with WebTestClient or MockMvc

WebFlux:

~~~java
webTestClient.get()
    .uri("/api/tenants/tenant-a/orders/order-a1")
    .headers(headers ->
        headers.setBearerAuth(token)
    )
    .exchange()
    .expectStatus().isOk();
~~~

Servlet:

~~~java
mvc.perform(get("/api/tenants/tenant-a/orders/order-a1")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
    .andExpect(status().isOk());
~~~

Match the client to your stack. What matters is sending the compact token in the HTTP header so the Bearer authentication filter runs.

## 8. Integration Test Matrix for Tenant Isolation

Assume token A has valid issuer/audience/signature/time, `orders.read` scope, and active tenant A.

| Request | Actual Resource | Expected Outcome |
|---|---|---|
| Token A → tenant A path → order A1 | Owned by A | 200 |
| Token A → tenant B path → order B1 | Owned by B | 403 or 404 per policy |
| Token A → tenant A path → order B1 | Owned by B | 404 or 403; never return data |
| Token A → tenant A path → another user's order A2 | Same tenant, different owner | 403/404 if owner policy requires |
| Token B → tenant B path → order B1 | Owned by B | 200 |
| Token B → tenant A path → order A1 | Owned by A | 403/404 |
| Token A missing scope → order A1 | Owned by A | 403 |
| Token wrong audience → order A1 | Owned by A | 401 |
| Expired token → order A1 | Owned by A | 401 |
| Missing token → order A1 | Owned by A | 401 |

Separate cases so you know which layer rejected:

- 401: unauthenticated token or invalid credential.
- 403: authenticated principal denied by policy.
- 404: application intentionally conceals existence of out-of-scope resources.

Choosing 403 vs. 404 depends on your threat model and API contract. Either way, tests must assert that no response body or header reveals cross-tenant resource data.

## 9. Cross-Tenant Testing Example with MockMvc

Suppose the application uses a Servlet Resource Server with endpoint:

~~~java
@GetMapping("/api/tenants/{tenantId}/orders/{orderId}")
OrderDto getOrder(
        @PathVariable String tenantId,
        @PathVariable UUID orderId) {
    return orderService.getOrder(tenantId, orderId);
}
~~~

Integration test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class MultiTenantOrderIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    TestAccessTokenFactory tokens;

    @Autowired
    OrderRepository orders;

    @BeforeEach
    void seed() {
        orders.save(order("order-a1", "tenant-a", "user-a"));
        orders.save(order("order-b1", "tenant-b", "user-b"));
    }

    @Test
    void tenantATokenCanReadTenantAOrder() throws Exception {
        String token = tokens.issue(
            "user-a", "tenant-a", "orders.read"
        );

        mvc.perform(get(
                "/api/tenants/tenant-a/orders/order-a1")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + token
                ))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("tenant-a"));
    }

    @Test
    void validTenantATokenCannotReadTenantBOrder() throws Exception {
        String token = tokens.issue(
            "user-a", "tenant-a", "orders.read"
        );

        mvc.perform(get(
                "/api/tenants/tenant-b/orders/order-b1")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + token
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void tenantAPathCannotExposeOrderOwnedByTenantB() throws Exception {
        String token = tokens.issue(
            "user-a", "tenant-a", "orders.read"
        );

        mvc.perform(get(
                "/api/tenants/tenant-a/orders/order-b1")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + token
                ))
            .andExpect(status().isNotFound());
    }
}
~~~

This is an illustrative skeleton. `TestAccessTokenFactory` must emit compact JWTs signed with the test private key; the test context uses the matching decoder/public key. The `order(...)` fixtures and ID parsers must match your real entity types.

Notice the two distinct negative tests:

- The second test checks a path tenant that mismatches the token's active tenant.
- The third test checks IDOR: the path tenant looks valid, yet the queried record belongs to another tenant.

Do not merge them into a single test: if the second test stops early at the path policy, the third test is what proves the repository query includes a tenant predicate.

## 10. Testing Membership and Resource Ownership

### 10.1. Multi-Tenant Users

A user may belong to both tenant A and B. The system may let the user choose an active tenant per request.

If the token carries only subject and scope, the application must check membership:

~~~text
token issuer + subject
       |
       v
membership lookup
       |
       +-- member of tenant A -> continue
       |
       +-- not member of tenant B -> deny
~~~

If the token also carries `tenant_id`, policy must still clarify whether that claim means a fixed active tenant or merely one of several memberships. Never rely on a claim with ambiguous semantics.

### 10.2. Revoked Membership

Tests should create an active membership, execute a successful request, revoke the membership, and call again with the same token:

~~~java
@Test
void revokedTenantMembershipStopsAccessEvenIfTokenIsUnexpired() {
    TenantMembership membership =
        membershipRepository.save(activeMembership("user-a", "tenant-a"));

    String token = tokens.issue(
        "user-a", "tenant-a", "orders.read"
    );

    assertThat(callOrderApi(token, "tenant-a", "order-a1"))
        .isEqualTo(200);

    membership.revoke();

    assertThat(callOrderApi(token, "tenant-a", "order-a1"))
        .isEqualTo(403);
}
~~~

This pseudocode illustrates live membership checks. If your system intentionally honors a membership snapshot inside the token until expiry, expected behavior differs; document the revocation model clearly and test against the exact contract.

### 10.3. Same-Tenant Ownership

If orders have owners, another user within the same tenant may still be barred from viewing them:

~~~text
tenant_id = tenant-a
token subject = user-a
order owner = user-b
~~~

Tenant matches while ownership mismatches. Tests must prove domain authorization denies access. Scope `orders.read` is usually a coarse API permission; it does not grant read access to every object.

### 10.4. Service-to-Service / Client Credentials

With client credentials, the principal represents an OAuth client rather than an end user. The `sub` claim may not carry a user identity in the way user-delegated tokens do.

Policies should distinguish:

- User-delegated tokens: user subject, client ID, tenant membership, and user permissions.
- Client-credentials tokens: service client, allowed tenants, service scopes, and resource policies.

Do not apply a user-ownership check to a service principal when the domain contract permits service accounts. Conversely, never let a broad-scoped client token access every tenant without an explicit tenant grant.

## 11. Testing Spoofed Tenant IDs via Headers and Bodies

A common bug occurs when a token is verified properly, yet the tenant context is taken from unvalidated client-supplied input.

### 11.1. Header Mismatch

Suppose the token carries `tenant_id=tenant-a`:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <TOKEN-A>
X-Tenant-ID: tenant-b
~~~

If the API allows a header to select the active tenant, the request must be rejected when the user/client lacks membership in tenant B. Never let a header unconditionally override the tenant context from the token claim.

~~~java
@Test
void tenantHeaderCannotOverrideTokenTenant() throws Exception {
    String token = tokens.issue(
        "user-a", "tenant-a", "orders.read"
    );

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .header("X-Tenant-ID", "tenant-b"))
        .andExpect(status().isForbidden());
}
~~~

If the API does not support a tenant header, ignore it or reject it per contract. What matters is that the header can never cross a tenant boundary.

### 11.2. Body Mismatch When Creating an Order

A create endpoint may accept a DTO:

~~~java
public record CreateOrderRequest(
    String tenantId,
    String description
) {}
~~~

The service should resolve the tenant from the authorized authentication context:

~~~java
public Order createOrder(
        String authorizedTenantId,
        CreateOrderRequest request) {

    if (request.tenantId() != null
            && !request.tenantId().equals(authorizedTenantId)) {
        throw new AccessDeniedException("Tenant mismatch");
    }

    return repository.save(
        new Order(authorizedTenantId, request.description())
    );
}
~~~

Test:

~~~java
@Test
void cannotCreateOrderForAnotherTenant() throws Exception {
    String token = tokens.issue(
        "user-a", "tenant-a", "orders.write"
    );

    mvc.perform(post("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "tenantId": "tenant-b",
                  "description": "cross-tenant attempt"
                }
                """))
        .andExpect(status().isForbidden());

    assertThat(orders.countByTenantId("tenant-b")).isEqualTo(0);
}
~~~

This tests side effects: beyond checking status, assert no new order was written into tenant B. If the DTO does not need a client-supplied tenant ID, a cleaner design removes that field from the request contract and assigns the tenant purely from the security context/service policy.

## 12. Verifying Tenant Isolation in Queries and Responses

### 12.1. Repository Queries Must Be Scoped

With Spring Data JPA:

~~~java
Optional<Order> findByIdAndTenantId(
    UUID id,
    String tenantId
);
~~~

With custom queries:

~~~java
@Query("""
    select o
    from Order o
    where o.id = :orderId
      and o.tenantId = :tenantId
    """)
Optional<Order> findVisibleOrder(
    UUID orderId,
    String tenantId
);
~~~

Never load a resource globally and forget the tenant check in one code path. The tenant predicate must live at the query boundary or inside a consistently enforced data-access abstraction.

### 12.2. Verifying Responses Leak No Data

Negative integration tests should assert:

- Status matches policy.
- Body contains no description, customer, owner, or tenant data of the forbidden resource.
- No nested relationships belonging to another tenant are returned.
- No file URLs or download links for another tenant appear.
- No unauthorized sensitive data is written into audit events.

A 403 response can still accidentally expose a resource DTO if the controller loaded the data before rejecting. Assert both response bodies and side effects, not just HTTP status codes.

### 12.3. Lists, Searches, Exports, and Pagination

Cross-tenant leaks do not happen only on single-ID lookup endpoints:

- Lists/searches using a client-supplied tenant ID.
- Searches by customer ID.
- CSV/Excel exports.
- Dashboard counts and summaries.
- Pagination cursors.
- Bulk actions taking lists of IDs.
- Attachment downloads.
- WebSocket/SSE subscriptions.

List endpoint tests must prove queries are always scoped by tenant. For bulk IDs, all IDs must belong to the caller's scope or the request must fail atomically per contract; never partially process some IDs and ignore others if that causes unwanted side effects.

### 12.4. Caches Must Include Tenant in Cache Keys

If a cache keys solely by order ID when IDs are not globally unique or authorization results depend on tenant, it can serve cached data from another tenant.

Safer key format:

~~~text
orders:{tenantId}:{orderId}
~~~

Test two tenants reading the same logical ID or identical query parameters and verify the cache never serves the other tenant's response. If cache keys incorporate principal/permission context, evaluate cache growth and invalidation when memberships are revoked.

## 13. Testing Multiple Issuers and Identity Collisions

A multi-tenant system can accept tokens from multiple issuers. In that case, `sub` alone cannot serve as a global user ID.

Example:

~~~text
Issuer A: iss=https://id-a.example.test, sub=user-123
Issuer B: iss=https://id-b.example.test, sub=user-123
~~~

Two tokens share the same `sub` yet may represent two completely different people.

Tests should verify:

- Issuer A cannot reuse Issuer B's identity mapping.
- Membership lookups use the issuer/subject pair or a normalized internal identity.
- Tenant IDs never collide across identity providers.
- Non-allowlisted issuers fail authentication (401).
- Tokens from a valid issuer lacking tenant membership fail authorization.

Never trust an issuer merely because a JWT carries a syntactically valid `iss`. The issuer must be configured in the Resource Server's trust settings.

## 14. Verifying Tenant Boundaries in Method Security and Entry Points

### 14.1. URL Authorization Alone Is Not Enough

A URL matcher can require a scope:

~~~java
.pathMatchers("/api/tenants/**")
    .hasAuthority("SCOPE_orders.read")
~~~

That checks only the scope. It does not check whether the path tenant matches the principal or resource ownership.

Place tenant authorization in method security:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') and " +
    "@tenantAccess.canAccess(authentication, #tenantId)"
)
public OrderDto getOrder(String tenantId, UUID orderId) {
    // tenant-scoped repository query
}
~~~

Or use a custom `AuthorizationManager` if policy belongs at the request authorization layer. Wherever it lives, enforce the policy consistently across all entry points.

### 14.2. Never Let Any Call Path Bypass Policy

The same service might be called from a REST controller, scheduled job, message listener, GraphQL resolver, admin endpoint, or internal service.

If only the controller checks the tenant, a message listener or admin route can invoke the service directly. Enforce the tenant invariant at the service/data-access boundary or pass an explicitly verified authorization context.

### 14.3. Cross-Tenant Admin Access Must Be Explicit

A platform admin may hold permissions across multiple tenants. Never turn a missing tenant match into a silent bypass.

Policy requires a dedicated authority/permission, full auditing, and often explicit tenant selection. Test:

- Regular users cannot cross tenants.
- Tenant admins administer only their own tenant.
- Platform admins succeed only under explicit policy.
- Platform admins lacking the required permission are still denied.
- Audit records capture actor, target tenant, and action.

## 15. Verifying Semantic Use of 401, 403, and 404

| Case | Authentication | Authorization / Resource Lookup | Typical Response |
|---|---|---|---|
| Missing token | Unauthenticated | Policy not run | 401 |
| Bad signature/issuer/audience/expiry | Authentication failure | Policy not run | 401 |
| Valid token missing scope | Authenticated | Scope denied | 403 |
| Tenant A token requesting tenant B | Authenticated | Tenant denied | 403 or 404 |
| Tenant A token requesting B's resource ID | Authenticated | Scoped lookup finds nothing | 404 or 403 |
| Matching tenant, user not owner | Authenticated | Resource ACL denied | 403 or 404 |
| Resource does not exist in current tenant | Authenticated | Not found | 404 |
| Revoked membership | Authenticated token, live policy denies | Membership denied | 403 or 404 |

Choose responses according to the API contract and resource-existence concealment policy. Never return 401 for a valid token simply because the user does not belong to a tenant; 401 signals an authentication failure, whereas tenant mismatch is an authorization failure.

When returning 404 to prevent enumeration, ensure genuinely nonexistent resources and resources in another tenant produce sufficiently matching bodies, statuses, and timing under your threat model. Never reveal "this order exists, but belongs to tenant B."

## 16. Testing Deeper Database Isolation

### 16.1. Composite Tenant Keys

Some schemas include the tenant in the primary key:

~~~sql
create table orders (
    tenant_id varchar(80) not null,
    order_id varchar(80) not null,
    description varchar(500) not null,
    primary key (tenant_id, order_id)
);
~~~

Repositories should then query by both keys. Tests must verify the tenant ID is always present in predicates.

### 16.2. Database Row-Level Security

When using PostgreSQL Row-Level Security (RLS), database policies can restrict rows by a session tenant context. Integration tests should then run against a database engine supporting RLS (such as PostgreSQL Testcontainers), rather than H2 alone if semantics differ.

Critical tests:

- Queries with no tenant context set return zero rows or fail per policy.
- Setting tenant A cannot read tenant B's rows.
- Connections returned to the pool do not retain the previous request's tenant context.
- Transaction/session variables reset properly on connection reuse.
- Native queries and bulk updates also respect RLS.
- Background jobs establish tenant context explicitly.

Never treat RLS as an excuse to drop application authorization. RLS and service policies protect different layers. Verify the exact transaction/session behavior of your database driver and connection pool.

### 16.3. Connection Pools and Tenant Context

If tenant context lives in a database session variable, tests should simulate reusing the same connection across two requests:

~~~text
Request A sets tenant-a
Request A completes and returns connection to pool
Request B obtains reused connection
Request B must not inherit tenant-a accidentally
~~~

Leftover context can cause cross-tenant denials or leaks. Cleanup must live in reliable transaction/session lifecycle hooks, not solely in a controller `finally` block.

## 17. Testing Side Effects and Atomicity

For write operations, assert more than HTTP status:

- No records created in the wrong tenant.
- No updates/deletes on another tenant's resources.
- No messages/events emitted before authorization succeeds.
- No files uploaded into another tenant's bucket/prefix.
- No downstream services called with the wrong tenant context.
- No caches or search indexes updated for the wrong tenant.

Update test example:

~~~java
@Test
void tenantATokenCannotModifyTenantBOrder() throws Exception {
    String token = tokens.issue(
        "user-a", "tenant-a", "orders.write"
    );

    mvc.perform(put("/api/tenants/tenant-b/orders/order-b1")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"description":"changed by tenant A"}
                """))
        .andExpect(status().isForbidden());

    Order stored = orders.findByIdAndTenantId(
        UUID.fromString("..."),
        "tenant-b"
    ).orElseThrow();

    assertThat(stored.getDescription())
        .isEqualTo("original tenant B description");
}
~~~

Replace the placeholder ID with the real fixture UUID. The crucial assertion is that tenant B's stored state remains untouched after the rejected request.

If requests emit events, inspect the event publisher or outbox table as well. Authorization must complete before any irreversible side effect is emitted.

## 18. Tests That Create a False Sense of Security

### "Token A was rejected on tenant B's path, so isolation works"

Insufficient. Code might reject path mismatches while still allowing token A to access order B via IDOR on tenant A's path. Test resource-tenant mismatches separately.

### "A valid JWT audience means the user belongs to the tenant"

False. Audience identifies the token's intended recipient. Tenant membership is separate authorization data.

### "The JWT has a tenant_id claim, so no database check is needed"

True only if your contract treats the claim as valid for the entire token lifetime. If memberships can be revoked immediately, policy must check live state or use a revocation mechanism.

### "The controller checked the tenant, so the repository does not need a filter"

Services can be invoked from other entry points, and one un-scoped query can leak rows. Tenant predicates at the data-access boundary provide defense in depth.

### "Tests using @WithMockUser proved the multi-tenant Resource Server"

No. They bypass the JWT decoder, token claims, and principal contract. Use signed JWTs through the filter chain for integration tests.

### "MockMvc jwt() tests issuer and signature"

No. That helper builds a simulated Authentication. It is suitable for principal/authorization checks, not token validation integration.

### "A 403 response is enough"

No. The controller might have loaded data or triggered side effects before returning 403. Assert response bodies, database state, outbox/events, and downstream calls.

### "No data in the JSON means no leak"

Data can still leak via counts, pagination, timing, caches, exports, download URLs, or error messages. Test every data channel your API exposes.






## 19. Integration Verification Scenarios by Endpoint Type

| Endpoint Type | Required Negative Cases |
|---|---|
| Get by ID | ID belonging to another tenant; path tenant mismatch; owner mismatch |
| List/search | Querying another tenant; spoofed filter/header; pagination count leakage |
| Create | Spoofed body tenant; principal missing write scope; revoked membership |
| Update | Record belonging to another tenant; changed tenant ID in payload |
| Delete | IDOR; soft-delete side effects; no event/outbox entry created |
| Bulk operation | Mixed-tenant ID list; no unintended partial processing |
| Export/download | Other tenant's file object/prefix; no signed URL issued |
| Admin operations | Tenant admin accessing another tenant; explicit platform admin permission |
| Async job/message | Tenant context propagated and verified; never reuse prior request context |

Not every endpoint needs the same implementation, but every path accessing tenant data must have a verified invariant.

## 20. CI and Multi-Tenant Test Data

A pipeline can be structured into:

~~~text
Pull request:
  1. Tenant policy unit tests
  2. Repository tenant-scope tests
  3. Signed JWT Resource Server integration tests
  4. Cross-tenant read/write negative tests
  5. Membership and owner authorization tests
  6. Cache / event / outbox side-effect tests

Database integration suite:
  7. PostgreSQL Testcontainers for RLS/session behavior (if used)
  8. Connection-pool tenant-context isolation
  9. Concurrent requests across tenants

Release candidate:
 10. Gateway / proxy / identity-provider sandbox tests
 11. Tenant admin and platform admin policy scenarios
 12. Audit and operational monitoring checks
~~~

Test data must be synthetic, never production customer records. Use clear tenant IDs and user IDs that read cleanly in assertions. Tests must not depend on execution order or shared mutable tenant contexts.

For parallel tests, give each test its own namespace/fixture or reliable database cleanup. Avoid two tests mutating the same shared membership or tenant state concurrently.

## 21. Multi-Tenant Verification Checklist

- [ ] Token has valid signature, issuer, audience, and timestamps.
- [ ] Tests send compact signed JWTs through the Resource Server filter chain.
- [ ] Tenant A token reads resource A when scope and policy allow.
- [ ] Tenant A token cannot read resource B.
- [ ] Tenant A path never leaks resource IDs belonging to tenant B.
- [ ] Users without membership are denied.
- [ ] Membership revocation takes effect per the revocation policy.
- [ ] Missing scope results in authorization denial.
- [ ] Tenant headers/bodies cannot override authorization context.
- [ ] Repository queries always include a tenant predicate.
- [ ] Owner/team permissions are checked where required by the domain.
- [ ] List/search/export/bulk endpoints leak no cross-tenant data.
- [ ] Cache keys include tenant context whenever data is tenant-scoped.
- [ ] Rejected writes produce no database changes, events, or downstream calls.
- [ ] Multi-issuer identities include issuer context, not subject alone.
- [ ] Client-credentials and user-delegated tokens have separate policies.
- [ ] Platform admin cross-tenant access is explicit and audited.
- [ ] 401, 403, and 404 reflect the right failure layer.
- [ ] If using RLS, tests run against the real database engine and verify connection reuse.
- [ ] CI uses synthetic users/tenants/tokens and never production credentials.

## 22. Conclusion

In a multi-tenant system, **a valid token proves only that the principal has been authenticated**. It does not automatically grant access to every tenant or every resource in the API.

An integration test must pass a signed access token through the Resource Server filter chain and verify these boundaries:

1. **Token trust:** valid issuer, audience, signature, timestamps, and token profile.
2. **Tenant context:** the selected request tenant aligns with the principal's policy or live membership.
3. **Resource ownership:** the actual record belongs to the authorized tenant and satisfies owner/team permissions.
4. **Data isolation:** repositories, lists/searches, caches, exports, and database layers never return another tenant's data.
5. **Side-effect isolation:** writes, events, files, and downstream calls never occur when authorization is denied.
6. **HTTP semantics:** invalid tokens return 401; valid tokens lacking permission return 403 or 404 per contract.

Always include at least two separate negative scenarios: a tenant A token calling a tenant B path, and a tenant A token calling a tenant A path while supplying a resource ID owned by tenant B. Together these two tests protect two distinct boundaries: tenant selection and resource-level access.

### References

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security Reference — Multi-tenancy for JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security Reference — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)



