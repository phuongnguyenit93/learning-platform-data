# Testing Valid Tokens Belonging to a Different Tenant Than the Requested Resource

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server** serving multiple tenants, an access token can be **completely valid cryptographically and at the protocol level** yet still **not be authorized to access a resource**. For example: a JWT is properly signed, not expired, has the right issuer and audience, and carries the `orders.read` scope, but it represents a user active in **tenant-A**, whereas the requested order belongs to **tenant-B**.

This is not necessarily an **authentication** failure. The Resource Server has already identified who the caller is; the issue lies in **tenant- and resource-level authorization**. If the backend only checks `hasAuthority("SCOPE_orders.read")` and then loads the record by ID without binding the tenant, an attacker can use a valid access token from their own tenant to access another tenant's data. This is a form of **Broken Object Level Authorization (BOLA/IDOR)** and **cross-tenant data leakage**.

This lesson focuses on how to **design and test scenarios where a token is valid but the tenant does not match**, from the Spring Security filter chain down to repositories, business services, API responses, and side effects. The goal is not merely to observe an HTTP 403 or 404, but to prove that **no data, state mutation, event, or cache entry belonging to another tenant is leaked or misused**.

> **Security invariant:** A valid access token **only authenticates the caller and provides its granted permissions**; it does not automatically grant access across **all tenants**. Every resource operation must prove that the caller has permission for **that resource's exact tenant**. When that cannot be proven, **fail closed**; do not query broadly and try to hide results in the UI.

## 1. Minimal Example: Tenant-A Token, Tenant-B Order

Suppose the Orders API serves multiple stores/business units:

| Tenant | User | Order | Owner |
| --- | --- | --- | --- |
| `tenant-A` | `alice` | `order-A100` | `alice` |
| `tenant-A` | `bob` | `order-A200` | `bob` |
| `tenant-B` | `carol` | `order-B100` | `carol` |
| `tenant-B` | `alice` (if she has separate membership) | `order-B200` | `alice` in tenant B |

The JWT access token Alice uses for tenant A has illustrative claims:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.cancel",
  "tenant_id": "tenant-A",
  "iat": 1893456000,
  "exp": 1893459600
}
~~~

Under this example contract, `tenant_id` is a **tenant context reliably established by the Authorization Server** when issuing the access token, not a string the caller can freely supply in a request. The Orders API also needs to ensure the token has its **signature, issuer, audience, expiration, and profile verified** before trusting that claim.

Two requests must be distinguished:

~~~http
# Request 1: URL specifies tenant-B, token is bound to tenant-A.
GET /api/tenants/tenant-B/orders/order-B100 HTTP/1.1
Authorization: Bearer <valid-token-of-alice-in-tenant-A>
~~~

~~~http
# Request 2: URL specifies tenant-A, but the ID actually belongs to a tenant-B order.
GET /api/tenants/tenant-A/orders/order-B100 HTTP/1.1
Authorization: Bearer <valid-token-of-alice-in-tenant-A>
~~~

**Both must be rejected.**

- In **Request 1**, the tenant in the URL differs from the tenant proven from the token/context.
- In **Request 2**, the URL and token both state tenant A, yet **the target record belongs to tenant B**. If the code only checks `pathTenant.equals(jwtTenant)` and then calls `findById("order-B100")`, the system can still expose Order B100. That makes this a crucial negative test that path-only test suites often miss.

Valid request:

~~~http
GET /api/tenants/tenant-A/orders/order-A100 HTTP/1.1
Authorization: Bearer <valid-token-of-alice-in-tenant-A>
~~~

With a valid token, the `orders.read` scope, and matching owner/tenant policy, this request can return 200.

## 2. Three Boundaries That Must Be Tested Independently

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer token"]
    B["JwtDecoder or opaque introspection"]
    C{"Valid token, right issuer/audience?"}
    X["Authentication failure"]
    D["Authentication + SCOPE_orders.read"]
    E{"Does endpoint allow this scope?"}
    F["Authorization denied"]
    G["Resolve trusted tenant context"]
    H{"Is tenant context allowed?"}
    I["Find resource with tenant predicate + object permission"]
    J{"Is resource within caller's scope?"}
    K["Return no data / produce no side effects"]
    L["Execute valid business operation"]

    A --> B --> C
    C -->|No| X
    C -->|Yes| D --> E
    E -->|No| F
    E -->|Yes| G --> H
    H -->|No| K
    H -->|Yes| I --> J
    J -->|No| K
    J -->|Yes| L
~~~

### 2.1. Authentication: Is the token trusted?

For a signed JWT, the Resource Server must verify:

- Signature using a trusted key according to the issuer/JWKS.
- `iss` belongs to the set of issuers accepted by the API.
- `aud` is intended for the **Orders API**, not some other API.
- Validity times `exp`, `nbf`, and required validators.
- Access-token profile/type per the contract; do not accept an OIDC ID token as an access token.

For an opaque access token, the Resource Server must introspect via a trusted Authorization Server, checking `active` and the corresponding resource/audience binding. Do not parse an opaque token speculatively.

If this stage fails, **there is no valid Authentication**. That scenario differs from the core test case of this lesson: **a valid token that is not allowed to access another tenant**.

### 2.2. Endpoint Authorization: Is the operation type allowed?

After authentication, Spring Security can map `scope` or `scp` to `GrantedAuthority` values such as:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

The rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/tenants/*/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

only states that the caller may perform the **order-reading operation type** under the scope contract. It does **not** state that the caller can read orders across all tenants. The next condition must be **tenant- and resource-scoped authorization**.

### 2.3. Resource Authorization: Which tenant does the order belong to?

A policy:

~~~text
canReadOrder(caller, requestedOrder)
  = valid JWT for Orders API
  AND scope orders.read
  AND tenant context caller is permitted to use
  AND requestedOrder.tenantId == authorizedTenantId
  AND requestedOrder.owner/assignment matches caller
~~~

In systems that support support staff, the owner condition can be replaced by `owner OR explicitly assigned support`, provided **every branch is bound to the right tenant**. Never let an un-namespaced `ADMIN` role turn into permission to view all tenants.

## 3. Distinguishing Issuer, Audience, Tenant, and Subject

These attributes answer different questions:

| Attribute | Question | Must not be confused with |
| --- | --- | --- |
| `iss` | Which token issuer issued the token? | Tenant ID |
| `aud` | Which Resource Server/API is the token intended for? | Tenant permitted for access |
| `sub` | Who is the token subject within the issuer namespace? | Owner of all records |
| `client_id` / `azp` per profile | Which OAuth2 Client uses / was issued the token? | User ID or tenant ID |
| `scope` | Which operation types does the token allow? | Specific resource/tenant list |
| `tenant_id` (custom) | Which tenant context is bound to the token, **if the AS has such a contract** | Independent proof that every order belongs to that tenant |
| Local membership | Which memberships/roles does the user/service hold in the tenant? | JWT signature or issuer |
| Resource `tenant_id` | Which tenant does the record actually belong to? | Tenant path sent by the Client |

An identical `sub` string across two issuers **is not necessarily the same person**. When linking users from an AS to internal data, a safe mapping by **`(iss, sub)`** is usually required. In a single-issuer API like the practice example, `sub` can be used after the issuer is verified; a multi-issuer API must extend the owner key or map to an internal user ID.

### 3.1. `tenant_id` is a custom claim, not an OAuth2/OIDC default requirement

OAuth 2.0 does not require every access token to contain `tenant_id`. An Authorization Server may use `organization_id`, `org_id`, `tenant`, memberships metadata, or dedicated per-resource/per-tenant tokens. Those names **do not carry universal semantics on their own**.

If the system chooses `tenant_id`, it must explicitly document:

1. Which AS issues this claim?
2. Does the claim represent the **active tenant** or **one membership among multiple tenants**?
3. Can the user freely choose an arbitrary value when requesting a token, and does the AS verify permission to select that tenant?
4. Can the claim change upon switching tenants, or must a new access token be issued?
5. When a user is removed from a tenant, under what SLA are tokens/cached memberships revoked or expired?
6. Do Client Credentials service tokens carry `tenant_id`, or do they use separate service permissions?

Do not simply write `jwt.getClaimAsString("tenant_id")` and assume every boundary is protected.

### 3.2. Tenant in URL/header is input, not permission

Request:

~~~http
GET /api/tenants/tenant-B/orders/order-B100 HTTP/1.1
Authorization: Bearer <token-tenant-A>
X-Tenant-Id: tenant-B
~~~

`tenant-B` in the URL/header is **the value requested by the caller**. It can serve as a selector, but it must be checked against the **verified** tenant context/membership. Never trust `X-Tenant-Id` as the sole source of tenant authorization.

Wrong:

~~~java
String tenantId = request.getHeader("X-Tenant-Id");
return orderRepository.findByTenantId(tenantId);
~~~

Right in principle:

~~~text
Requested tenant (untrusted)
  -> compare against verified tenant context / active membership
  -> use the approved tenant as a data query predicate
~~~

## 4. Two Mandatory Cross-Tenant Test Types

This is the **core** of the lesson.

### 4.1. Type A: Tenant-A token, Tenant-B URL

~~~text
verified JWT tenant_id = tenant-A
GET /api/tenants/tenant-B/orders/order-B100
~~~

Expected:

- The token is authenticated, not conflated with a forged token.
- The endpoint may see `SCOPE_orders.read`, yet tenant authorization must reject it.
- Do not call the repository to query by `tenant-B` just because the URL says so.
- Do not return Order B100's content, balance, owner, or metadata.
- HTTP status may be **403** or **404** depending on the API disclosure policy.

A test that merely supplies a valid token and asserts status 403 may not be enough: you need to verify that **server-side tenant context is not overwritten by a caller-supplied path/header**.

### 4.2. Type B: Tenant-A token and URL, resource ID belonging to Tenant B

~~~text
verified JWT tenant_id = tenant-A
GET /api/tenants/tenant-A/orders/order-B100
Database: order-B100.tenant_id = tenant-B
~~~

Expected:

- The tenant path check may succeed.
- The repository must look up Order B100 **within tenant A** and get an empty result.
- Do not read/return the actual record belonging to tenant B.
- Do not update caches with tenant B's data.
- If it is POST/DELETE, produce no mutations or events.

**This is the negative test that catches a missing tenant filter in `findById(id)`**, even when developers already compare the JWT tenant with the URL tenant. Never skip this test.

### 4.3. Type C: Right tenant, wrong owner

~~~text
JWT: tenant-A, sub=alice
URL: tenant-A
Order: tenant-A, owner=bob
~~~

Expected: reject if the endpoint is owner-only. Being in the right tenant is a **necessary condition**, not a sufficient one. B2B APIs may allow support staff to read someone else's data, but that requires an **explicitly proven tenant-scoped assignment or role**.

## 5. Choosing 401, 403, or 404 for Cross-Tenant Cases

| Scenario | Error layer | Typical appropriate response |
| --- | --- | --- |
| No token sent | Authentication | **401 Unauthorized** |
| Invalid JWT signature, expired, or wrong audience | Authentication/token validation | Typically **401** |
| Valid token lacking `SCOPE_orders.read` | Route authorization | **403 Forbidden** |
| Valid token and sufficient scope, but tenant path is disallowed | Tenant authorization | **403** or **404** per API policy |
| Valid token, matching tenant path, resource ID belongs to another tenant | Object authorization | Usually **404 Not Found** to avoid leaking record existence |
| Valid token, same tenant, wrong owner/assignment | Object authorization | **403** or **404**, consistent with the contract |
| Cannot reach membership DB required for authorization | Dependency/policy failure | Fail closed; status per exception handling |

**A valid token for the wrong tenant should not be mischaracterized as an invalid-signature token.** This is usually an **authorization denial**, not necessarily a 401. Some APIs choose **404** for any object outside the caller's scope to avoid revealing whether the object exists. Some administrative APIs choose **403** so the Client knows authentication succeeded but access was denied.

Choosing 403 or 404 must be **consistent** with the anti-enumeration policy. If cross-tenant objects return 403 while nonexistent IDs return 404, an attacker can infer that the object exists. Body content, latency, pagination, and log/trace details should all be considered as well.

**Do not use automatic login redirects or token refresh as a fix for a wrong-tenant error**: the token is still valid. A user can only switch tenants via a flow allowed by the AS/app, or by being granted the appropriate membership/permission.

## 6. Designing Test Fixtures to Catch Tenant Leakage

A good fixture needs more than one tenant and more than one user:

| ID | tenant_id | owner_subject | status | Purpose |
| --- | --- | --- | --- | --- |
| `order-A100` | `tenant-A` | `alice` | `OPEN` | Happy path |
| `order-A200` | `tenant-A` | `bob` | `OPEN` | Same tenant, wrong owner |
| `order-B100` | `tenant-B` | `carol` | `OPEN` | Cross-tenant ID |
| `order-B200` | `tenant-B` | `alice` | `OPEN` | Same subject, different tenant |
| `order-A300` | `tenant-A` | `alice` | `CANCELLED` | Business state disallowing operation |

Why include `order-B200` with `owner_subject=alice`? To catch a query that **filters only by owner while forgetting the tenant**. The same user can belong to multiple tenants, or two systems might share identical subjects. If the API only runs:

~~~sql
SELECT * FROM orders
WHERE id = :orderId AND owner_subject = :subject;
~~~

then Alice's tenant-A token context could still find Order B200. The tenant predicate must appear in the query or an equivalent row-level authorization mechanism.

### 6.1. Safe SQL: bind ID, tenant, and owner together

~~~sql
SELECT id, tenant_id, owner_subject, status
FROM orders
WHERE id = :orderId
  AND tenant_id = :authorizedTenant
  AND owner_subject = :authorizedSubject;
~~~

If support roles can view non-owned orders, add a policy branch that is **authorized and tenant-bound**. Do not rewrite it as:

~~~sql
-- WRONG: OR can break tenant boundaries.
WHERE id = :orderId
  AND (tenant_id = :authorizedTenant
       OR owner_subject = :authorizedSubject);
~~~

A misplaced `OR` can expose another tenant's orders simply because the subject matches. Queries with `OR`, `JOIN`, or dynamic filters strongly benefit from negative tests using multi-tenant fixtures.

### 6.2. Do not test only nonexistent IDs

If a negative test only calls `/orders/nonexistent` and receives 404, it **proves nothing about tenant isolation**. Use an **ID guaranteed to exist in tenant B** and request it with a tenant-A token. Only real cross-tenant data exposes queries missing a tenant predicate.

## 7. Spring Boot 3 / Spring Security 6 Example with a Single Tenant Context in JWT

The following example uses **Spring MVC/Servlet Resource Server**, Java 17+, Spring Data JPA, and JWT access tokens. It illustrates a policy where **one token represents one active tenant**, with a single trusted issuer. This is **one specific profile**, not a universal standard for every multi-tenant system.

### 7.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Database drivers and dependency versions are chosen according to the project's environment and Spring Boot release line.

### 7.2. Configuring JWT issuer and audience

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: orders-api
~~~

Example URIs:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
~~~

These are illustrative addresses. Do not use a Client-supplied JWKS URL, do not accept dev issuers in production, and do not treat `tenant_id` as trustworthy before the JWT is verified. In many setups an issuer validator is already configured, while **audience still needs explicit verification** per the contract.

An illustrative `JwtDecoder` checking issuer + audience:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtValidationConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Access token audience is not accepted",
                            null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audience));
        return decoder;
    }
}
~~~

When creating a custom `JwtDecoder` bean, you are responsible for keeping all appropriate validators for issuer, timestamps, and audience; this is not a place to skip checks just to make cross-tenant tests pass easily. Other decoders/profiles may be used depending on the Spring Security version, but **real token validation must exist** in production.

### 7.3. `SecurityFilterChain`: scope is only the first layer

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST,
                        "/api/tenants/*/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This snippet carries three conditions/assumptions to keep in mind:

1. The API only accepts a **Bearer token in the Authorization header** and does not accept sessions/cookies as credentials for these routes; therefore CSRF is disabled **according to a specific threat model**, not simply because JWTs are stateless.
2. `hasAuthority("SCOPE_orders.read")` and `hasAuthority("SCOPE_orders.cancel")` **do not compare tenants**. The service/repository underneath must enforce that.
3. `securityMatcher("/api/**")` only covers URLs under `/api/**`; another policy/filter chain is needed for out-of-scope endpoints if any exist.

All scopes/roles must be mapped from verified claims using an appropriate converter; an identically named scope in another API does not remove the need for JWT audience checks.

## 8. Repository: Always Bind the Tenant to the Record

An illustrative entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private String id;

    @Column(nullable = false)
    private String tenantId;

    @Column(nullable = false)
    private String ownerSubject;

    @Column(nullable = false)
    private String status;

    protected OrderEntity() {}

    public OrderEntity(String id, String tenantId,
                       String ownerSubject, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.ownerSubject = ownerSubject;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOwnerSubject() { return ownerSubject; }
    public String getStatus() { return status; }

    public void cancel() { this.status = "CANCELLED"; }
}
~~~

Repository:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, String> {

    Optional<OrderEntity> findByIdAndTenantIdAndOwnerSubject(
            String id,
            String tenantId,
            String ownerSubject);

    List<OrderEntity> findByTenantIdAndOwnerSubjectOrderByIdAsc(
            String tenantId,
            String ownerSubject);
}
~~~

In a production design, `ownerSubject` is only appropriate when **the issuer is fixed and subject mapping is explicitly managed**. With multiple issuers or potentially colliding subjects, prefer storing an **internalUserId** after safe linking by `(iss, sub)`, or binding the issuer sufficiently in the schema/query.

**Key security point:** the repository exposes methods **with the tenant in the lookup predicate**, instead of `findById(id)` where checks are easily forgotten or deferred. Using a tenant-scoped primary key or composite index can also make it more natural for queries to always require `(tenant_id, id)`.

### 8.1. Whether a resource ID is guessable does not change the requirement

Even if an order ID is a hard-to-guess UUID, it **must not be treated as a credential**. If another tenant's UUID leaks through logs, URLs, or linked responses, the Resource Server must still block access. **Do not substitute “random IDs” for tenant authorization.**

### 8.2. List and search queries must filter by tenant

A list endpoint can use:

~~~java
orderRepository.findByTenantIdAndOwnerSubjectOrderByIdAsc(
    authorizedTenantId, subject);
~~~

Do not call `findAll()` and filter in Java after pagination:

~~~text
SELECT all tenants
  -> system-wide pagination/sorting
  -> filter tenant on the result
~~~

That approach can leak **counts, ordering, pagination, aggregations**, or return confusing empty pages. The tenant predicate should sit **inside the DB query or a trusted row-level security mechanism**, before pagination and aggregation.

## 9. Service Verifying Path Tenant and Resource Tenant

Example simple policy: **an access token has a single active `tenant_id`**, and users may only read/cancel their own orders within that tenant.

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrdersService {

    private final OrderRepository orders;

    public OrdersService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderDto read(String requestedTenant,
                         String orderId, Jwt jwt) {

        String authorizedTenant =
                requireAuthorizedTenant(requestedTenant, jwt);

        OrderEntity entity = orders
            .findByIdAndTenantIdAndOwnerSubject(
                orderId, authorizedTenant, jwt.getSubject())
            .orElseThrow(OrdersService::notVisible);

        return new OrderDto(
            entity.getId(), entity.getTenantId(), entity.getStatus());
    }

    @Transactional
    public void cancel(String requestedTenant,
                       String orderId, Jwt jwt) {

        String authorizedTenant =
                requireAuthorizedTenant(requestedTenant, jwt);

        OrderEntity entity = orders
            .findByIdAndTenantIdAndOwnerSubject(
                orderId, authorizedTenant, jwt.getSubject())
            .orElseThrow(OrdersService::notVisible);

        if (!"OPEN".equals(entity.getStatus())) {
            throw new ResponseStatusException(
                HttpStatus.CONFLICT, "Order cannot be cancelled");
        }

        entity.cancel();
        // JPA dirty checking within @Transactional persists the change.
    }

    private static String requireAuthorizedTenant(
            String requestedTenant, Jwt jwt) {

        String tokenTenant = jwt.getClaimAsString("tenant_id");
        String subject = jwt.getSubject();

        if (tokenTenant == null || tokenTenant.isBlank()
                || subject == null || subject.isBlank()
                || !tokenTenant.equals(requestedTenant)) {
            throw notVisible();
        }
        return tokenTenant;
    }

    private static ResponseStatusException notVisible() {
        return new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Order not found");
    }
}

record OrderDto(String id, String tenantId, String status) {}
~~~

Safety aspects of this code:

- `requireAuthorizedTenant` takes `tenant_id` exclusively from the **`Jwt` verified by the Resource Server**, never using the path/header as a source of authority.
- If the tenant in the path differs from the claim, it does not proceed to read the resource.
- `findByIdAndTenantIdAndOwnerSubject` guarantees **the ID is queried within the right tenant and owner**, so even when the path matches the token, another tenant's order cannot be read.
- For cancel operations, only an entity retrieved by tenant/owner can be updated.
- Returns 404 uniformly for out-of-scope resources per the **example's disclosure policy**.

**Limitations of the example:** the code uses an **owner-only** policy and a single trusted issuer; it does not yet model assigned support, managers, multiple issuers, or multi-membership. Do not compromise security by letting every `ROLE_ADMIN` bypass the tenant predicate without a dedicated, approved, and audited **system-level cross-tenant permission**.

### 9.1. Write operations must guard against race conditions

Reading a record and modifying it inside a transaction can suffice for simple cases, but if tenant membership, owner, or status can change concurrently, critical operations should consider an **atomic conditional update**:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE id = :orderId
  AND tenant_id = :authorizedTenant
  AND owner_subject = :authorizedSubject
  AND status = 'OPEN';
~~~

Check the **updated row count**. If it is 0, do not reveal that the record exists in another tenant. Tenant and subject values in the condition must come from **server-verified identity/policy**, never merely from the request body.

### 9.2. Avoid exceptions/logs that leak tenant B

Wrong:

~~~json
{
  "error": "You cannot read order-B100 because it belongs to tenant-B"
}
~~~

This message can disclose the existence and owning tenant of the record. Normal responses should use a generic message:

~~~json
{
  "error": "Order not found"
}
~~~

In controlled internal logs, you can still record the **tenant violation type** and correlation ID for auditing, without logging raw Bearer tokens or another tenant's customer data.

## 10. Controller Preserving the Boundary Between Request and Principal

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
public class OrdersController {

    private final OrdersService orders;

    public OrdersController(OrdersService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    public OrderDto read(
            @PathVariable String tenantId,
            @PathVariable String orderId,
            @AuthenticationPrincipal Jwt jwt) {

        return orders.read(tenantId, orderId, jwt);
    }

    @PostMapping("/{orderId}/cancel")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void cancel(
            @PathVariable String tenantId,
            @PathVariable String orderId,
            @AuthenticationPrincipal Jwt jwt) {

        orders.cancel(tenantId, orderId, jwt);
    }
}
~~~

**`@AuthenticationPrincipal Jwt` is only appropriate when the chain authenticates a JWT and the principal remains a `Jwt`.** If the API uses opaque tokens or an authentication converter changes the principal type, the controller must accept the matching principal type. Tests still preserve the exact same tenant invariant regardless of token format.

In Spring Security JWT Resource Server, `JwtAuthenticationToken.getPrincipal()` is normally `Jwt`. Never manually decode the raw Authorization header in a controller to extract `tenant_id`, because Base64 decoding does not prove signature or audience.

## 11. Testing with MockMvc: Valid Token, Wrong Tenant

Spring Security Test provides `SecurityMockMvcRequestPostProcessors.jwt()` to create a **simulated `JwtAuthenticationToken`**. It lets you test **tenant- and resource-level authorization** without standing up an Authorization Server or signing JWTs for every test.

**Crucial boundary:** `jwt()` **does not prove JWT signature verification occurred**, nor does it check issuer, audience, expiration, or JWKS. Unit/HTTP authorization tests using `jwt()` must be complemented by **integration tests using genuinely signed JWTs through `JwtDecoder`**.

### 11.1. Fixtures must include data from at least two tenants

Example test skeleton using Spring Boot, MockMvc, and the JPA repository from section 8. Entities are seeded cleanly per test; the application can use an H2 test DB or Testcontainers/PostgreSQL to match the real schema.

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class TenantIsolationHttpTest {

    @Autowired MockMvc mvc;
    @Autowired OrderRepository orders;

    @BeforeEach
    void seed() {
        orders.deleteAll();
        orders.save(new OrderEntity(
            "order-A100", "tenant-A", "alice", "OPEN"));
        orders.save(new OrderEntity(
            "order-A200", "tenant-A", "bob", "OPEN"));
        orders.save(new OrderEntity(
            "order-B100", "tenant-B", "carol", "OPEN"));
        orders.save(new OrderEntity(
            "order-B200", "tenant-B", "alice", "OPEN"));
    }

    private SecurityMockMvcRequestPostProcessors.JwtRequestPostProcessor
    token(String tenant, String subject, String... scopes) {
        return jwt()
            .jwt(builder -> builder
                .issuer("https://identity.example.test/realms/shop")
                .subject(subject)
                .audience(List.of("orders-api"))
                .claim("tenant_id", tenant)
                .claim("scope", String.join(" ", scopes)))
            .authorities(Arrays.stream(scopes)
                .map(s -> new SimpleGrantedAuthority("SCOPE_" + s))
                .toList());
    }

    @Test
    void aliceCanReadOwnOrderWithinTenantA() throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-A100")
                .with(token("tenant-A", "alice", "orders.read")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("order-A100"))
            .andExpect(jsonPath("$.tenantId").value("tenant-A"));
    }

    @Test
    void rejectsRequestedTenantBDifferentFromTokenTenantA()
            throws Exception {
        mvc.perform(get("/api/tenants/tenant-B/orders/order-B100")
                .with(token("tenant-A", "alice", "orders.read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void rejectsForeignOrderEvenWhenPathMatchesTokenTenant()
            throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-B100")
                .with(token("tenant-A", "alice", "orders.read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void rejectsSameSubjectFromDifferentTenant()
            throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-B200")
                .with(token("tenant-A", "alice", "orders.read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void rejectsSameTenantButDifferentOwner() throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-A200")
                .with(token("tenant-A", "alice", "orders.read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void deniesValidTokenWithoutReadScope() throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-A100")
                .with(token("tenant-A", "alice", "orders.cancel")))
            .andExpect(status().isForbidden());
    }

    @Test
    void rejectsMissingToken() throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-A100"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void crossTenantCancelCannotMutateForeignOrder()
            throws Exception {
        mvc.perform(post(
                "/api/tenants/tenant-A/orders/order-B100/cancel")
                .with(token("tenant-A", "alice", "orders.cancel")))
            .andExpect(status().isNotFound());

        org.junit.jupiter.api.Assertions.assertEquals(
            "OPEN",
            orders.findById("order-B100").orElseThrow().getStatus());
    }
}
~~~

The code above is a **Spring context integration fixture** for the controller/service/JPA example in earlier sections. When bringing it into a real project, make sure the test datasource is isolated, the schema is created properly, and Spring Security filters are actually active. If a test has an outer transaction separate from the service transaction, double-check how DB state is observed after the request.

**The most critical tests are `rejectsForeignOrderEvenWhenPathMatchesTokenTenant` and `rejectsSameSubjectFromDifferentTenant`**: both catch bugs that tests checking only the path tenant against the JWT cannot detect.

### 11.2. Why grant authorities explicitly in tests?

The helper:

~~~java
.authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))
~~~

makes clear that **the HTTP scope is already valid**. If a cross-tenant test returns 403 simply because it accidentally **lacks the scope**, it proves nothing about the tenant policy. Keep scopes **sufficient** in cross-tenant negative tests so that the tenant layer is the reason access is blocked.

Similarly, a missing-token test verifies the 401 authentication path, and a missing-scope test verifies 403 HTTP authorization; **do not use those two tests as substitutes for cross-tenant testing**.

### 11.3. Test against real resources in another tenant

Do not use an ID like `unknown-order` when testing cross-tenant isolation. The database must contain that record in **tenant B**, and a tenant-A token must attempt to access it. After the request, a repository reserved for **test setup/verification** can confirm record B remains intact, while the public API **must never query by ID without a tenant guard**.

### 11.4. Both reads and writes need negative cases

A system might block GET properly yet still let POST mutate data:

~~~java
@PostMapping("/{orderId}/cancel")
void cancel(@PathVariable String orderId) {
    orderRepository.findById(orderId)
        .ifPresent(OrderEntity::cancel);
}
~~~

This design is **unsafe** if the code omits tenant/owner checks, even when the GET endpoint behaves properly. Therefore **every operation/method** must enforce tenant-scoped authorization, especially PATCH, DELETE, bulk updates, and workflow state transitions.

## 12. Testing Services and Repositories Independently

HTTP tests prove behavior from the filter chain through the controller; repository/service tests help pinpoint root causes.

### 12.1. Repository never returns records from another tenant

A JPA integration test can check:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

// Test body with pre-seeded OrderRepository data.
@Test
void repositoryNeverFindsOrderInAnotherTenant() {
    assertTrue(orders
        .findByIdAndTenantIdAndOwnerSubject(
            "order-B100", "tenant-A", "carol")
        .isEmpty());
}
~~~

This differs from checking whether a query returns empty because an order ID does not exist: `order-B100` must genuinely exist in tenant B.

### 12.2. Unit testing that the service never triggers unscoped queries

With Mockito, you can mock the repository and assert that the service **calls the method containing the tenant predicate**:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

@Test
void wrongTenantCannotTriggerUnscopedLookup() {
    OrderRepository repo = mock(OrderRepository.class);
    OrdersService service = new OrdersService(repo);

    Jwt verifiedJwt = testJwt(
        "tenant-A", "alice"); // unit-test helper building a Jwt object

    assertThrows(ResponseStatusException.class,
        () -> service.read("tenant-B", "order-B100", verifiedJwt));

    verifyNoInteractions(repo);
}
~~~

`testJwt(...)` is a helper creating a mock `Jwt` for unit tests; like MockMvc's `jwt()`, it **does not check signatures**. This test proves the service rejects a mismatched path tenant **before calling the repository**. Another test should mock an empty result from `findByIdAndTenantIdAndOwnerSubject` when **the path matches the token tenant but the order ID belongs to another tenant**, confirming the resource layer also fails closed.

### 12.3. Testing for “zero side effects”

When a POST cancel is rejected, beyond the HTTP status you should assert:

~~~text
Order B100 still has status OPEN
No rows were updated/deleted
No OrderCancelled event was emitted
No outbox event was created
No email / webhook was sent
No false audit entry claims Alice cancelled order B100
~~~

If the application uses a transactional outbox, check the outbox table by tenant. If a message broker or downstream HTTP call happens before returning 403, the negative test must catch that side effect. **A 403 status at the end of a request is not enough** if the unauthorized action already happened earlier.

## 13. Signed-JWT Integration Tests: Distinguishing Valid Tokens from Forged Tokens

Spring Security Test's `jwt()` simulates Authentication, so it does not prove a token passed cryptographic verification or validators. You need another group of integration tests:

1. Generate a **test-only** RSA/EC key pair or run a test JWKS server.
2. Configure the real `JwtDecoder` to point at the **mock JWKS** and the test environment's trusted issuer.
3. Sign a test JWT access token with `iss`, `aud`, `scope`, `tenant_id`, `sub`, and `exp` matching the profile.
4. Send the actual JWT string via `Authorization: Bearer ...`, **without using `jwt()`**.
5. Seed resources in tenants A and B; verify a properly signed JWT for tenant A **cannot access B**.
6. Test mutating a single byte of the payload without re-signing → authentication must fail.
7. Test wrong issuer/audience/expiration → the decoder must reject **before the service is ever invoked**.

### 13.1. Two-axis matrix: valid JWT vs. tenant authorization

| Token | Resource | Expected |
| --- | --- | --- |
| JWT with valid signature, issuer/audience, tenant A, read scope | Caller's Order A | Allowed if data policy matches |
| **Valid JWT**, tenant A, read scope | Order B | **Denied at tenant/resource authorization** |
| Valid JWT, tenant A, read scope | Another user's Order A | Denied by owner/assignment |
| Valid JWT lacking `orders.read` | Order A | 403 at scope authorization |
| JWT with invalid signature, claims say tenant A | Order A | Authentication fails, never reaches business policy |
| Properly signed JWT with `aud=billing-api` | Order A | Rejected by JWT validation |
| Expired JWT | Order A | Authentication fails |
| Dev-issuer JWT in production | Order A | Authentication fails |

**The scenario highlighted in this lesson is the second row:** the token is **genuinely valid** while the resource belongs to **a different tenant**. Only testing forged/expired tokens and seeing 401 does not test tenant isolation flaws at all.

### 13.2. Never make a JWT “valid” by bypassing the decoder in production

Do not alter the validator like this:

~~~java
// WRONG: Never use this as a shortcut to make tests pass.
decoder.setJwtValidator(jwt ->
    OAuth2TokenValidatorResult.success());
~~~

The goal of testing is to separate token validation from tenant authorization, **not to disable authentication**. Only use a mock principal in authorization-layer tests, and test the real signing/verification pipeline separately.

### 13.3. Opaque access tokens must also obey tenant policies

If the system uses introspection:

~~~json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "alice",
  "tenant_id": "tenant-A"
}
~~~

The Resource Server must verify active state, audience, and the metadata contract; after that it must still block Order B100. Unit tests can mock `OpaqueTokenIntrospector` to return a valid tenant-A principal, while integration tests mock a real HTTP introspection endpoint and try cross-tenant requests.

**Token format does not solve BOLA.** Both JWTs and opaque tokens require data-level policies.

## 14. Testing When the URL Does Not Contain the Tenant

Not every API has a `/tenants/{tenantId}` path. An endpoint might look like:

~~~http
GET /api/orders/order-B100
Authorization: Bearer <token-tenant-A>
~~~

In that case, the API must derive the **authorized tenant context** from the verified token or membership policy, and then query:

~~~sql
SELECT *
FROM orders
WHERE id = :orderId
  AND tenant_id = :authorizedTenant;
~~~

Having no tenant in the path does **not** mean skipping tenant checks. Negative tests still use a tenant-B resource ID with a tenant-A token.

### 14.1. Header selector

An API might use:

~~~http
X-Tenant-Id: tenant-B
~~~

This header is only a **tenant selection request**, not a permission. With a token issued strictly for tenant A, the API must reject tenant B. If a token grants access across multiple tenants, you must verify that the user is an active member of tenant B or that the token was issued for tenant B per the profile.

### 14.2. Tenant from subdomain

~~~text
tenant-a.shop.example.test
tenant-b.shop.example.test
~~~

A hostname can also serve as a tenant selector, but you must account for proxies, trusted Host headers, domain routing, and authorization. Never treat an arbitrary Client-supplied Host header as proof of permission. Test requests hitting tenant B's host with token A, even when routing/frameworks parse the host cleanly.

## 15. Multi-Tenant Tokens and Users With Memberships in Multiple Organizations

A variant:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_ids": ["tenant-A", "tenant-B"]
}
~~~

This list may describe memberships at token-issuance time, so you must clarify whether it is an **actual authorization grant** or merely profile information. Design decisions:

- Can a user pick tenant B via URL/header, or must they go through a “switch tenant” flow to get a new token?
- Does `ORDER_ADMIN` in tenant A apply in tenant B? **Usually no.**
- Can membership be revoked while the JWT has not yet expired?
- Do memberships need to be checked dynamically in the database?
- Is there a tenant-admin service or automation permitted to access multiple tenants under audit?

**Never turn a tenant list inside a JWT into blanket permission to read all resources across all those tenants.** Roles/scopes can be tenant-scoped, and even inside tenant B the user still needs permission for the target order.

### 15.1. Multi-tenant policy with an active tenant

A highly testable design:

~~~text
Token carries tenant_id = activeTenant confirmed by the AS.
When the user switches tenants:
    AS/app verifies membership
    -> issues a new token or updates trusted server-side context
Every request:
    activeTenant must match requested tenant
    resource.tenant_id must match activeTenant
~~~

Another design lets callers pick a tenant per request and **looks up membership per request**; in that case, scopes and roles must be evaluated **within the exact selected tenant**. Whichever model you choose, tests must include **a user belonging to A but not B**, and **a user belonging to both A and B with different roles**, to catch privilege “bleeding” between tenants.

### 15.2. Admin roles do not cross tenant boundaries by default

A user:

~~~text
tenant-A -> ROLE_ORDER_ADMIN
tenant-B -> ROLE_VIEWER
~~~

if flattened into a global `ROLE_ORDER_ADMIN`, risks viewing or modifying tenant B's data. Tests should verify:

~~~text
Admin in A + resource A -> allowed per policy
Admin in A + resource B -> denied if lacking matching role in B
Viewer in B + cancel action on B -> denied
~~~

Only a clearly designed **platform-wide** role, provisioned under strict controls and auditing, may perform certain cross-tenant operations. Never assign a global `ROLE_ADMIN` carelessly.

## 16. Testing Returned Data: Not Just GET by ID

Many cross-tenant bugs hide in “secondary” APIs:

| Endpoint type | Risk | Negative test |
| --- | --- | --- |
| `GET /orders/{id}` | Reading order B with token A | Existing ID B returns no data |
| `GET /orders` | List mixes in order B | Response only contains tenant A's orders |
| `GET /orders?search=...` | Cross-tenant search | Querying a keyword unique to B returns no results |
| `GET /orders/count` | Leaking system-wide order totals | Count reflects only the allowed tenant |
| `GET /reports/revenue` | Aggregations mix in B's revenue | Totals and groupings cover only the active tenant |
| `GET /orders/{id}/items` | Child resources lack tenant filtering | Never returns items of order B |
| `GET /attachments/{id}` | Direct file/attachment access | Tenant B's attachment is denied |
| `GET /exports/{jobId}` | Exports/downloads include B's data | Jobs/files bind tenant + owner |
| `POST /orders/bulk-cancel` | An ID from B mixed into an A batch | Never modifies B; clear all-or-nothing/partial policy |
| `PATCH /orders/{id}` | Mutating B even when reads are blocked | Does not update row B |
| `DELETE /orders/{id}` | Deleting B by ID | Does not delete row B |
| `POST /orders/{id}/refund` | Financial side effect | Creates no refund/payment command for B |

**An empty list alone is not enough to prove there is no leak.** Also check `totalElements`, `totalPages`, sorting/pagination, aggregations, and response headers if they carry summary info.

### 16.1. Easily overlooked pagination tests

Wrong:

~~~text
SELECT all orders ORDER BY created_at LIMIT 20 OFFSET 0
  -> filter tenant A in Java
~~~

This can return 3 orders for A even when tenant A actually has 50 orders, while pagination metadata is computed across all tenants. Better:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = :authorizedTenant
ORDER BY created_at
LIMIT :limit OFFSET :offset;
~~~

Test with interleaved A/B creation timestamps, small page sizes, and multiple pages to catch post-pagination filtering bugs.

### 16.2. Search and count

Give tenant B an order with a unique keyword `secret-B-keyword` that tenant A lacks. Token A searching that keyword must receive **no results**, and must not receive `totalHits=1` or autocomplete suggestions containing B's info.

### 16.3. Nested resources

`GET /api/orders/{orderId}/attachments/{attachmentId}` must confirm:

~~~text
order.tenant_id == authorizedTenant
AND attachment.order_id == requestedOrderId
AND attachment.tenant_id == authorizedTenant (if present)
AND caller has permission to view order/attachment
~~~

Do not check only the attachment ID while skipping order/tenant binding. The same applies to invoices, payments, shipping labels, and customer profiles.

## 17. Testing Mutations and Side Effects

Write operations are often more dangerous than reads because they carry lasting consequences:

~~~text
POST /api/tenants/tenant-A/orders/order-B100/cancel
Valid Bearer token for tenant-A + orders.cancel
~~~

Expected:

- Request is rejected by tenant/resource authorization.
- Order B100 remains `OPEN`.
- No `OrderCancelled` event is emitted for B100.
- No outbox entry is written for tenant B.
- No email, webhook, or refund request is triggered.
- No audit record claims a business action succeeded.

### 17.1. Bulk requests

A payload:

~~~json
{
  "orderIds": ["order-A100", "order-B100"]
}
~~~

The API must enforce a clear policy:

- **All-or-nothing:** if any ID does not belong to tenant A, reject the entire batch and update neither A nor B.
- **Partial success:** process only authorized items and report results appropriately, while **never modifying B** and never leaking unnecessary details about B.

Test both patterns according to the contract; never let a service call `findAllById(ids)` and update everything.

### 17.2. Idempotency keys

When using `Idempotency-Key`, cached idempotency responses must be bound to **tenant + caller/request context**. A key used in tenant A must never replay a response from tenant B. Test reusing the same idempotency key across two tenants and verify zero cross-contamination.

### 17.3. Async jobs, events, and message consumers

Once an authorized request spawns an async job, the background job usually runs **without a direct HTTP Bearer token**. Tenant context must be propagated as **controlled internal data** bound to the authorized job; workers must verify the tenant before reading or writing.

Test that an export job owned by tenant B cannot have its file downloaded with a tenant-A token, even if the job ID is known. Avoid capturing tenant from an initial request header and storing it in a static/global variable lacking request scope.

## 18. Caches, CDNs, File Storage, and Search Indexes Also Need Tenant Isolation

An API whose repository filters tenants properly can still leak data through a misconfigured cache.

### 18.1. Cache keys missing the tenant

Wrong in principle:

~~~java
@Cacheable(cacheNames = "order", key = "#orderId")
public OrderDto read(String tenantId, String orderId) {
    // ...
}
~~~

If a cache key contains only the order ID and IDs are only unique per tenant, or responses depend on permissions, two tenants can receive each other's cached data. Key caches by **tenant, resource ID, and any required authorization dimensions**:

~~~java
@Cacheable(
    cacheNames = "order",
    key = "#tenantId + ':' + #orderId")
public OrderDto readTenantScoped(String tenantId, String orderId) {
    // tenantId has already been verified, never taken arbitrarily from the request.
    // ...
}
~~~

If responses also depend on owner, role, or field-level entitlements, **tenant+order alone may still be insufficient**. Caches must mirror the exact visibility scope and invalidate on permission changes. Never put raw tokens into cache keys or logs.

### 18.2. Cache poisoning and ensuring cache hits never skip policy

Another mistake:

~~~text
if (cache contains orderId):
    return cachedOrder; // skips tenant authorization
else:
    validate tenant -> query DB
~~~

Policy must apply to both **cache hits** and **cache misses**. Test: successfully fetch Order B with token B to warm the cache, then request the same ID with token A; token A must still be denied and must never receive B's cached data.

### 18.3. CDN/object storage

If the API returns links to object storage or signed URLs, check that:

- Links are generated only after tenant/object authorization.
- Object paths/buckets/metadata do not mix tenants uncontrollably.
- Signed URLs have expiration, scope, and intended audience aligned with the risk model.
- Caches/CDNs do not serve B's private responses to A due to missing Authorization/Vary keys or cache policies.

Test downloading directly via the object URL, not just the metadata endpoint.

### 18.4. Search indexes

Elasticsearch/OpenSearch or standalone search services must receive tenant filters from **server-verified context**. Never rely on the frontend always appending `tenantId`; a Client can submit queries directly. Test tenant-B-only keywords as in section 16.2.

## 19. Database Row-Level Security as an Additional Layer

Some systems use **PostgreSQL Row-Level Security (RLS)** to add a safeguard inside the DB. Conceptual example:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_isolation ON orders
USING (
  tenant_id =
  current_setting('app.current_tenant', true)
)
WITH CHECK (
  tenant_id =
  current_setting('app.current_tenant', true)
);
~~~

This is a **conceptual illustration**, not a complete production DB configuration. RLS requires managing roles, table ownership, table privileges, migrations, connection pooling, and how tenant context enters each transaction. With connection pools, you must **set tenant context safely per transaction** and guarantee state never leaks to the next request; never accept `app.current_tenant` from an unverified Client.

**RLS is defense in depth, not a replacement for application authorization.** The API still needs to verify scopes, tenant membership, ownership, and business rules before touching data.

### 19.1. Testing RLS when the tenant setting is missing

The expectation when tenant context is absent must be **deny**, never “see everything”. Test:

- Tenant A reads only A's rows.
- Tenant B reads only B's rows.
- No tenant set → cannot read any other tenant's rows.
- Transaction A followed by B reusing a physical connection → context does not bleed over.
- The application DB user does not hold privileges bypassing RLS outside policy.

Even when RLS is enabled, keep running HTTP cross-tenant tests to verify **the entire pipeline**.

## 20. WebFlux Needs the Same Negative Test Suite

With **Spring Security WebFlux**, tokens are verified via `ReactiveJwtDecoder` and authorization via `SecurityWebFilterChain`/`ServerHttpSecurity.authorizeExchange(...)`. Non-blocking execution does not make tenant isolation appear automatically.

Example reactive repository:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

interface ReactiveOrderRepository
        extends ReactiveCrudRepository<ReactiveOrderEntity, String> {

    Mono<ReactiveOrderEntity> findByIdAndTenantIdAndOwnerSubject(
        String id, String tenantId, String ownerSubject);
}
~~~

A service:

~~~java
Mono<OrderDto> read(String requestedTenant, String orderId, Jwt jwt) {
    String tokenTenant = jwt.getClaimAsString("tenant_id");
    if (tokenTenant == null || !tokenTenant.equals(requestedTenant)) {
        return Mono.error(new ResponseStatusException(
            HttpStatus.NOT_FOUND));
    }

    return reactiveOrders
        .findByIdAndTenantIdAndOwnerSubject(
            orderId, tokenTenant, jwt.getSubject())
        .map(order -> new OrderDto(
            order.getId(), order.getTenantId(), order.getStatus()))
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND)));
}
~~~

This WebFlux snippet is an **illustrative service method body** paired with its repository/entity; it is not a standalone class. Never call `.block()` to fetch an order inside a request event loop. **Never store the active tenant in a mutable global static/`ThreadLocal`** across Reactor subscriptions. When context propagation is needed, use Reactor Context/`ReactiveSecurityContextHolder` or explicit parameters from a verified Authentication.

### 20.1. `WebTestClient` and `mockJwt()`

Spring Security Test provides `mockJwt()` for WebFlux:

~~~java
webTestClient.mutateWith(mockJwt()
        .jwt(jwt -> jwt.claim("tenant_id", "tenant-A"))
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/tenants/tenant-A/orders/order-B100")
    .exchange()
    .expectStatus().isNotFound();
~~~

This test is useful when the service uses a data fixture where Order B100 genuinely belongs to tenant B. `mockJwt()` **simulates Authentication** and does not verify signatures/issuer/audience; separate integration tests with signed tokens through `ReactiveJwtDecoder` are required.

### 20.2. Testing reactive repositories and caches

Use **StepVerifier** for reactive services:

~~~java
StepVerifier.create(
        service.read("tenant-A", "order-B100", tenantAJwt))
    .expectError(ResponseStatusException.class)
    .verify();
~~~

`tenantAJwt` is a constructed test Jwt, not proof that the decoder accepts its signature. Also test `Mono.empty()` when the query finds no order in the tenant, and verify **no mutations occur** when the pipeline denies access. Never manually `.subscribe()` inside a repository flow and emit results before policy checks complete.

## 21. Comprehensive Tenant Test Matrix

A table you can add directly to a test plan:

| Code | Token | URL/Target | Authorization | Expected result |
| --- | --- | --- | --- | --- |
| T01 | Valid JWT tenant A, `orders.read` | A / Caller's Order A | Valid | 200 |
| T02 | **Valid JWT tenant A**, `orders.read` | **B / Order B** | Wrong tenant path | Deny, usually 404/403 |
| T03 | **Valid JWT tenant A**, `orders.read` | **A / Order B ID** | Matching path, resource wrong tenant | Deny, leak nothing from B |
| T04 | Valid JWT tenant A, `orders.read` | A / Bob's Order | Wrong owner | Deny |
| T05 | Valid JWT tenant A, `orders.cancel` | A / Order B | Wrong tenant, write | Deny, zero mutations/events |
| T06 | Valid JWT tenant A, missing `orders.read` | A / Order A | Missing scope | 403 |
| T07 | No token | A / Order A | Unauthenticated | Typically 401 |
| T08 | Invalid JWT signature | A / Order A | Authentication failure | Typically 401 |
| T09 | JWT `aud=billing-api` | A / Order A | Audience failure | Typically 401 |
| T10 | Dev-issuer JWT | A / Order A | Issuer failure | Typically 401 |
| T11 | JWT missing/wrong-type tenant claim | A / Order A | Insufficient trusted tenant context | Deny |
| T12 | JWT tenant A, `ROLE_ADMIN` in tenant A | B / Order B | Cross-tenant role not allowed | Deny |
| T13 | JWT tenant A, user is also member of B | A / Order B | Token's active tenant is still A | Deny under single-tenant profile |
| T14 | Valid AS-issued JWT tenant B, proper scope | B / Authorized Order B | Valid tenant/owner | Allowed |
| T15 | JWT tenant A | List/search/report with A+B data | Tenant filter | Only A's data/counts |
| T16 | JWT tenant A | Attachment/export file owned by B | Indirect wrong tenant | Cannot download |
| T17 | JWT tenant A | Bulk IDs with A and B | Batch policy | Never mutates B |
| T18 | JWT tenant A | Order B already cached | Cache hit | Leaks nothing from B |
| T19 | JWT tenant A, membership revoked | Order A | Dynamic membership policy | Deny per revocation contract |
| T20 | Service/client-credentials token | Tenant-B order | Separate service permission | Deny unless explicitly granted |

**Not every test must return the exact same HTTP status.** Hidden resources may use 404; missing scopes typically return 403. What must never change is **zero unauthorized data or side effects**.

### 21.1. Testing multiple identifier formats

If the system supports:

- Order IDs as UUIDs or auto-incrementing numbers.
- Tenant IDs as UUIDs, slugs, or hostnames.
- APIs accepting tenants in URLs, headers, or claims.
- Multi-issuer subjects.

you must test the exact **production identifier formats**, including URL encoding/normalization, case sensitivity, and tenant slug → ID mapping. A faulty string comparison can turn two distinct tenants into the same normalized value or bypass policy checks.

### 21.2. Testing tenant switches between two requests from the same user

If Alice is valid in A and B, but her current token is for A:

~~~text
Request 1: tenant-A token -> Order A -> allowed
Request 2: same tenant-A token -> Order B -> denied
User switches tenant via an authorized flow
Request 3: new tenant-B token -> Order B -> allowed if B policy permits
~~~

Never use a static `currentTenant` variable to pass context across requests. Caches/sessions must never mix active tenants across two sessions/users or two browser tabs.

## 22. Tenant Permissions Changing While a Token Is Still Unexpired

A JWT may remain valid for 15 minutes even after a user has been removed from a tenant. If the Orders API policy requires **current membership**, reading only the tenant claim from the JWT can lag behind changes.

Strategies to consider:

1. Short-lived access tokens with the AS issuing accurate tenant claims at grant time.
2. Opaque introspection reflecting current active/membership state per AS contract.
3. Reactive/DB membership lookups at the authorization layer when required.
4. Short-TTL membership caches with invalidation on membership updates.
5. Token/session revocation when accounts are locked or leave an organization.

Each choice trades off latency, availability, and revocation delay. **An unexpired token does not by itself prove membership still exists at execution time** if the contract demands dynamic authorization.

### 22.1. Negative test scenario with revoked membership

~~~text
T0: Alice belongs to tenant-A, token is issued
T1: Admin revokes Alice's membership in A
T2: Alice uses the unexpired token to call Order A
~~~

Outcome depends on the defined revocation policy. If near-instant enforcement is required, authorization must detect the revoked membership or invalidate its cache. Tests must verify **operations are blocked** within the committed SLA rather than waiting passively for JWT expiry.

### 22.2. Membership service failure never means permission granted

If the membership DB or remote service times out, never fall back to:

~~~java
// WRONG: Never do this when policy requires membership.
catch (Exception timeout) {
    return true;
}
~~~

Without trustworthy proof of authorization, you must **fail closed**. HTTP status can reflect dependency failure per contract, but the operation must never execute.

## 23. Threat Model: Attackers Using Legitimate Accounts

Cross-tenant tests do not assume the attacker can forge JWT signatures. An attacker could be:

- A legitimate employee in tenant A trying to guess order IDs in tenant B.
- A tenant-A client tampering with `/tenant-B` path segments or `X-Tenant-Id`.
- A user holding memberships in both A and B, with read-only access in B, attempting to exercise A's admin role.
- A service account holding a token for one tenant calling endpoints for another tenant's resources.
- A user accidentally receiving a tenant-B link or order ID via email or logs and trying to open it.

**This is why cross-tenant authorization must be tested using properly signed tokens with valid scopes.** An API that only blocks forged tokens has proven nothing against legitimate users from another tenant.

### 23.1. Do not mistake CORS or UI hiding for tenant isolation

Hiding a cancel button in the frontend does not stop callers hitting the API directly. CORS is not authentication or authorization; curl or machine clients can still send requests. Tenant policies must be enforced **on the server and on the data-access path**, independent of any UI.

### 23.2. Do not treat the API gateway as the sole layer

A gateway may verify tokens and inject verified tenant headers into internal requests. Even then, the backend needs a **clear trust boundary**: trust headers only from the trusted gateway, block Clients from bypassing the gateway, and strip forged external headers. Test direct-to-service and internal invocation paths if they lie within the threat model. **An arbitrary `X-Tenant-Id` header is never a security credential on its own.**

## 24. Auditing and Observability on Cross-Tenant Attempts

Useful fields to capture:

~~~text
request_id
api_route
http_method
response_status
decision = DENY_TENANT_MISMATCH
trusted_issuer
trusted_subject_or_internal_user_id
authorized_tenant_id
requested_tenant_id (untrusted input, handled safely)
resource_type
policy_version
~~~

Only record `resource.tenant_id` when accessed via an authorized internal auditing path for legitimate security reasons; do not “fetch tenant B's record first just to log full details” as a standard check. Never log raw access tokens, Authorization headers, private keys, client secrets, or another tenant's sensitive data.

### 24.1. Measuring metrics while avoiding high cardinality

Never put raw `sub`, tokens, or millions of order IDs into metric labels. You can track aggregate counts for `tenant_mismatch`, `owner_denied`, `missing_scope`, and `jwt_invalid` by service/environment. For auditing requiring specific identities, use an access-controlled logging system with proper retention.

### 24.2. Distinguishing false positives from attacks

A cross-tenant request might stem from a UI holding onto a stale active tenant after switching organizations rather than a deliberate attack. Even so, **never loosen authorization rules because of it**. Fix Client state and return safe error messages; continue denying requests targeting the wrong tenant.

## 25. Common Mistakes Tests Must Catch

**“A valid token with read scope can view any order.”** Wrong; tenant and resource owner/assignment must still be verified.

**“We checked the URL tenant against the JWT, so queries don't need a tenant filter.”** Wrong; an order ID can belong to tenant B even when the URL specifies tenant A.

**“A user sharing the same `sub` in A and B can use token A to read B.”** No; active tenant context and tenant-B permission must be proven. Multi-issuer setups must also protect against `(iss, sub)` collisions.

**“An ADMIN role in tenant A makes them a platform-wide admin.”** Not by default; roles must be tenant-scoped unless an explicit, separate platform role is granted.

**“Returning 404 for a nonexistent ID means cross-tenant tests pass.”** No; you must test with an **ID that genuinely exists in tenant B**.

**“Forged tokens can't reach B, so tenant isolation works.”** No; forged JWTs are stopped by the decoder before tenant policies ever run.

**“We can take `tenantId` from a frontend header.”** Never as an authorization source; headers/paths are only selectors and must be matched against trusted context.

**“Calling repository `findById` and checking the tenant right before returning JSON is always enough.”** Easy to miss, prone to producing side effects, polluting caches, or leaking hints. Prefer tenant predicates directly inside queries and policy checks before mutations.

**“Only GET needs tenant checks; POST/DELETE already check write scopes.”** Wrong; cross-tenant mutations can cause greater damage than reads.

**“Seeing 403 proves the DB wasn't modified.”** No; you must assert that DB, outbox, and event state stayed untouched.

**“Caching by `orderId` is enough.”** Not when IDs or responses depend on tenant/owner; cache hits must respect tenant policy.

**“As long as the JWT hasn't expired, tenant membership can't change.”** Wrong; an appropriate freshness/revocation policy is needed.

**“If the tenant DB lookup fails, allow through to avoid downtime.”** Fails open and is dangerous.

**“`jwt()` in MockMvc proves signatures and audiences are validated.”** No; separate signed-JWT integration tests are required.

**“CORS restricts origins so other tenants can't call the API.”** CORS does not replace server-side access control.

**“The frontend hides order IDs so nobody knows them.”** No; UUIDs/IDs leak through links and logs; object-level authorization remains mandatory.

**“Database Row-Level Security means we don't need Spring Security.”** No; JWT validation, scopes, business entitlements, and RLS reinforce one another.

## 26. Handoff Checklist and Acceptance Criteria

A tenant-isolation test suite should prove:

1. **JWTs/opaque tokens are verified properly** (issuer, audience, expiration, active/profile) in integration tests.
2. A tenant-A token has **sufficient scopes** and a valid Authentication, yet Order B is still denied.
3. Tests cover **tenant path B differing from tenant claim A**.
4. Tests cover **tenant path A matching claim A, while the order ID genuinely belongs to B**.
5. Tests cover **same tenant, wrong owner/assignment**.
6. Tests cover **the same subject across different tenants** and, for multi-issuer systems, the same subject across different issuers.
7. Queries for GET, list, search, count, and aggregations **filter by tenant before pagination**.
8. POST/PATCH/DELETE/bulk operations **never update another tenant**.
9. Zero **events, outbox entries, webhooks, or exports/downloads** occur for another tenant upon denial.
10. Cache hits, CDNs/object storage, and search indexes never expose another tenant.
11. Roles, permissions, and memberships are bound to **the exact tenant**, avoiding accidental global admins.
12. Tenant selectors in paths/headers/hosts are compared **against trusted principal/membership context**.
13. 401 for authentication failures is clearly distinguished from 403/404 for authorization denials.
14. Dependency outages or missing required membership checks **fail closed**.
15. API responses/logs never leak tokens, foreign tenant data, or out-of-policy resource existence.
16. Unit tests with mock Authentication are backed by **signed-token or introspection HTTP integration tests**.

**Acceptance criteria go beyond “status is not 200”.** They require: **no unauthorized data disclosure, no unauthorized mutations, and no tenant authorization derived from untrusted input**.

## 27. Scenario Exercises

**Scenario A:** Alice's JWT verifies successfully with `SCOPE_orders.read` and `tenant_id=tenant-A`. Alice calls `GET /api/tenants/tenant-B/orders/order-B100`. How should this be handled?

**Deny at tenant authorization.** Do not treat the JWT as invalidly signed. Choose 403 or 404 per disclosure policy; return none of Order B100's data.

**Scenario B:** A developer verifies the URL tenant matches the JWT, then calls `findById(orderId)`. With URL `tenant-A` and `order-B100` belonging to B, is a path-mismatch test sufficient?

**No.** You need a test where **the path matches the token yet the resource ID belongs to tenant B**. Records must be filtered by tenant in the repository/policy.

**Scenario C:** Order B200 has ownerSubject `alice`, and Alice's token is for tenant A. The query filters only `owner_subject=alice`, omitting the tenant. What is the risk?

Alice can read tenant B's order. You must bind **both tenant and owner simultaneously**, never treating a global subject as permission across organizations.

**Scenario D:** A tenant-A token has `orders.cancel`, POST cancel on Order B returns 404, yet the database flips B's status to CANCELLED. Does the test pass?

**No.** Even with HTTP 404, the unauthorized side effect occurred. Tests must assert DB, outbox, and event state remained unchanged.

**Scenario E:** Valid token A and proper scope; the list API returns only A's orders, yet `totalElements` counts A+B together. Does tenant isolation hold?

**No.** Pagination metadata already leaked aggregate data and can reveal other tenants' activity. Tenant filtering must apply before count/pagination.

**Scenario F:** Alice is an admin in tenant A and a reader in tenant B. Token/role mapping creates a global `ROLE_ADMIN`. May she cancel B's orders?

**Not by default.** Admin privilege in A does not carry over to B. Roles/memberships must be tenant-bound and tested per tenant.

**Scenario G:** A unit test uses `jwt()` with tenant A and gets 404 reading order B. Can we conclude `JwtDecoder` validates signatures and audiences?

**No.** `jwt()` mocks Authentication. You need integration tests sending genuinely signed JWTs through the decoder, including bad issuer/audience/signature cases.

**Scenario H:** Two tenants share the local order ID `42`. The cache keys only by `42` and serves B's cached Order to tenant A. Where is the bug?

**Cache isolation.** Keys and policies must include the verified tenant context; cache hits must never bypass permission checks.

**Scenario I:** A user leaves tenant A while their JWT `exp` still has 20 minutes left. The system requires membership revocation within 1 minute. Is checking `exp` enough?

**No.** Fresh membership validation or a revocation/cache invalidation mechanism meeting the committed SLA is required.

**Scenario J:** A request sends `X-Tenant-Id: tenant-B` while its valid token only permits tenant A. The backend passes that header directly into SQL. What is wrong?

The header is caller-supplied input; the backend treated a **tenant selector as proof of permission**. It must be validated against trusted tenant context / active membership before querying.

---

## Conclusion

**Testing a valid token belonging to a different tenant** is a test of **authorization isolation**, not merely JWT signature checking or 401 status codes. A Bearer access token can have **the right issuer, audience, validity window, and scopes** while still having **no permission** to read or mutate resources belonging to another tenant. Therefore Spring Security route rules like `hasAuthority("SCOPE_orders.read")` are only the **first layer**; the backend must also bind **trusted tenant context, owner/role/membership, and the record's actual tenant**.

The two mandatory negative tests are: **(1) tenant-A token, tenant-B URL** and **(2) tenant-A token, tenant-A URL, but a resource ID belonging to tenant B**. The second test is especially critical for catching `findById` queries lacking a tenant filter. For writes, verify **zero mutations, events, or outbox records** upon denial; for lists, search, caches, and exports, prove zero cross-tenant data or metadata leakage. Use `jwt()`/`mockJwt()` to isolate business authorization, while complementing them with **signed-JWT / introspection integration tests** to verify real authentication. **A valid token is only the starting point; permission for the right tenant and the right resource decides whether a request succeeds.**
