# @PreAuthorize, Authorities, and Call Input Data

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, a JWT Access Token helps the API authenticate the caller and obtain authorities such as `SCOPE_orders.read` or `SCOPE_orders.write`. However, a token carrying the order-reading scope **does not implicitly grant access to view every order**. A request might attempt to access someone else's ID, select another tenant via the URL, or inject unauthorized data into the body.

**`@PreAuthorize`** is a key tool for protecting **business method invocations** using both types of information:

- **Trusted data from authentication:** `Authentication`, authorities, principal, and verified JWT claims.
- **Call input data:** `orderId`, `tenantId`, `command`, method arguments — typically originating from the HTTP path, query, or body and **not trustworthy merely because they have been parsed into Java objects**.

This lesson explains how to combine `@PreAuthorize`, `hasAuthority`, SpEL, and a **policy bean** to make data-driven access decisions, while distinguishing method security from HTTP security and transactional business checks. Examples use **Spring Boot 3.x, Spring Security 6.x, Java 17+, and a Servlet Resource Server** receiving JWT Access Tokens. Issuer, audience, ID, tenant, and scope values are illustrative.

## 1. Why Is Protection Needed at the Method Layer?

Suppose the application exposes two endpoints:

~~~http
GET /api/orders/7e9b... HTTP/1.1
Authorization: Bearer ACCESS_TOKEN
~~~

~~~http
PATCH /api/orders/7e9b... HTTP/1.1
Authorization: Bearer ACCESS_TOKEN
Content-Type: application/json

{"note":"Deliver before 17:00"}
~~~

Spring Security can require:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.PATCH, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

This is an **HTTP-layer** condition, suitable for blocking requests lacking the required scope early. Yet with the same `orders.read` scope, two users A and B should not necessarily be allowed to view the same order. If `orderId` belongs to user B, user A must be blocked even if A's JWT has a valid signature, issuer, audience, and scope.

A business method can declare:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @orderAccess.canRead(authentication, #orderId)")
public OrderDto getOrder(UUID orderId) {
    // ...
}
~~~

This method simultaneously requires the read authority and satisfaction of the policy for the **specific `orderId`**. This addresses part of the **Broken Object Level Authorization (BOLA/IDOR)** risk.

### 1.1. Three Layers of Responsibility

~~~text
HTTP request + Authorization: Bearer JWT
         |
         v
1. JWT authentication
   - Signature/JWKS, issuer, audience, expiration, token profile
   - Produces JwtAuthenticationToken, GrantedAuthority
         |
         v
2. HTTP authorization
   - authorizeHttpRequests
   - GET /api/orders/** requires SCOPE_orders.read
         |
         v
3. Method/domain authorization
   - @PreAuthorize checks scope and orderId/tenant
   - Service checks actual order state
   - Query/update constrains owner, tenant, state
         |
         v
        Execute business logic or deny
~~~

| Layer | What Does It Know? | Example Condition |
| --- | --- | --- |
| **JWT decoder** | Signed/verified token, claims, and token type. | Valid `iss`, `aud`, `exp`, `nbf`, and signature. |
| **HTTP authorization** | URL, HTTP method, `Authentication`. | GET requires `SCOPE_orders.read`. |
| **Method security** | Invoked method, arguments, and `Authentication`. | Allowed to read **this `orderId`**? |
| **Domain/data authorization** | Record, owner, tenant, state at operation time. | Does the order belong to the permitted tenant and owner? |

Never rely on **only one** layer to protect everything. Business methods can be invoked from HTTP controllers, message consumers, scheduled jobs, or elsewhere; policies should live where sufficient context is available and be enforced consistently. In flows without HTTP or a `SecurityContext`, there must be a dedicated authentication/context mechanism rather than assuming a JWT is always present.

## 2. Enabling Method Security with @EnableMethodSecurity

In Spring Security 6.x, use the **`@EnableMethodSecurity`** annotation:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

By default, this enables processing of essential annotations such as **`@PreAuthorize`** and **`@PostAuthorize`** on methods supported by the Spring AOP/security infrastructure. There is no need to enable the legacy `@EnableGlobalMethodSecurity(prePostEnabled = true)` in new Spring Security 6 projects.

Common Gradle dependencies (version-managed by Spring Boot):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Example JWT Resource Server configuration in `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

`issuer-uri` configures the trusted JWT issuer and validates `iss`. `audiences` is supported in compatible Spring Boot versions to enforce that tokens carry audience `orders-api`; in other versions, configure an explicit audience validator. **Method security does not replace JWT validation**: before trusting `Authentication` or Access Token claims, the Resource Server must verify signature, algorithm, issuer, audience, and expiration.

### 2.1. Baseline HTTP Protection Complemented by Method Security

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
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

This configuration snippet strictly describes an API using Bearer headers without cookie sessions. `csrf.disable()` is **not a general recommendation for web OIDC Login using session cookies**; cookie-based authentication requires an appropriate CSRF strategy.

**HTTP matcher ordering** still matters: specific rules must precede broader ones; `anyRequest().denyAll()` helps prevent accidentally exposing new endpoints. Even if the HTTP layer allows GET, `@PreAuthorize` on the service can still deny the request when the user does not own the resource.

## 3. How @PreAuthorize Works

Spring Security evaluates the `@PreAuthorize` expression **before the method body runs**. The expression is written in **Spring Expression Language (SpEL)** and evaluated against the security context.

Example:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public ReportDto readReport(UUID reportId) {
    // Runs only when the caller has the report-reading authority.
}
~~~

If the expression evaluates to `false`, the method is not executed and the request is rejected with an authorization exception (typically `AccessDeniedException`).

### 3.1. Common Expressions

| SpEL | Meaning | When to Use |
| --- | --- | --- |
| `isAuthenticated()` | Requires an authenticated Authentication. | Internal endpoints not requiring a specific scope. |
| `hasAuthority('SCOPE_orders.read')` | Must have that exact authority. | Reading resources with an OAuth scope. |
| `hasAnyAuthority('SCOPE_orders.read', 'SCOPE_orders.audit')` | Has at least one of the listed authorities. | Multiple roles/scopes allowed to read per contract. |
| `hasRole('ADMIN')` | With the default prefix, requires `ROLE_ADMIN`. | Roles properly mapped from a trusted source. |
| `hasAnyRole('ADMIN', 'SUPPORT')` | Has one of the corresponding roles. | Domain role policies. |
| `authentication` | Current Authentication object. | Passed into policy beans to read principal/authorities. |
| `principal` | Currently authenticated principal. | Accessing fields on a known principal type. |
| `#orderId` | Method argument named `orderId`. | Checking permissions on a record. |
| `#p0`, `#a0` | First argument by position. | Used when parameter name metadata is unavailable. |
| `@orderAccess.canRead(authentication, #orderId)` | Invokes bean named `orderAccess`. | Combining permissions with database state. |

`@PreAuthorize` supports `and`, `or`, `!`, and various SpEL comparisons. **Avoid overly long, complex expressions in place of testable Java business policies.** Whenever conditions require database lookups or tenant/owner checks, an explicit policy bean is far easier to maintain.

### 3.2. hasAuthority vs. hasRole and hasAnyAuthority

A JWT Access Token might contain:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "person-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1893456000
}
~~~

In a standard JWT Resource Server setup, `JwtGrantedAuthoritiesConverter` converts `scope` (or `scp` depending on profile) into:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Therefore:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
~~~

matches the read scope. Conversely:

~~~java
@PreAuthorize("hasRole('ADMIN')")
~~~

typically checks for the `ROLE_ADMIN` authority and **is not automatically present** if the JWT only carries scopes. Likewise, a custom claim `roles: ["ADMIN"]` **does not automatically become `ROLE_ADMIN`** unless a converter or policy maps it to the corresponding authority.

| Provided JWT / Authority | Expression | Authority Outcome |
| --- | --- | --- |
| `SCOPE_orders.read` | `hasAuthority('SCOPE_orders.read')` | True. |
| `SCOPE_orders.write` | `hasAuthority('SCOPE_orders.read')` | False, if lacking read permission. |
| `ROLE_ADMIN` | `hasRole('ADMIN')` | True with default role prefix. |
| `SCOPE_admin.manage` | `hasRole('ADMIN')` | False, unless another converter/authority grants it. |
| `SCOPE_orders.read` | `hasAnyAuthority('SCOPE_orders.read', 'SCOPE_orders.audit')` | True. |

**Never map client-supplied role/permission strings from the request** into `GrantedAuthority`. Authorities must only be derived from authenticated sources under a trusted API contract; data permissions must still be evaluated separately.

## 4. Method Input Data Does Not Become Trusted Just Because the Token Is Valid

Controller example:

~~~java
@GetMapping("/api/orders/{orderId}")
OrderDto get(@PathVariable UUID orderId) {
    return orders.getOrder(orderId);
}
~~~

The `orderId` argument has been parsed into a `UUID`, yet **the client still chooses its value**. An authenticated user can try the ID of someone else's order. Likewise, `tenantId`, `ownerUserId`, `role`, or `approved` in a request body are **untrusted data**.

### 4.1. BOLA/IDOR Attacks Using Valid IDs

~~~text
JWT user A:
  sub = person-A
  scope = orders.read

Database:
  Order 111 -> owner A
  Order 222 -> owner B

Request 1: GET /api/orders/111
  -> May be allowed.

Request 2: GET /api/orders/222
  -> MUST be denied if user A is not permitted to read order 222.
~~~

Changing the order ID **does not require changing the JWT**. Thus, a rule checking only scope:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto getOrder(UUID orderId) { ... }
~~~

is insufficient when data is scoped to individual users or tenants.

### 4.2. Arguments Commonly Misunderstood

| Argument | Client-Controllable? | Required Policy |
| --- | --- | --- |
| `orderId` in path | Yes. | Look up owner/tenant by `orderId`; do not treat ID as proof of access. |
| `tenantId` in URL/query | Yes. | Check principal's permitted tenant/membership. |
| `ownerUserId` in JSON body | Yes. | Never let clients change owners outside authorized workflows. |
| `status`, `approved` in body | Yes. | Verify state transitions and approval permissions. |
| `limit`, `sort` in query | Yes. | Validate bounds, sortable fields, and data exposure risks. |
| `Authentication` provided by Spring Security | Created by framework post-authentication. | Trust only when requests traverse the proper security chain and principal type is controlled. |
| `Jwt` obtained via `@AuthenticationPrincipal` | From Authentication, post-decoder. | Use verified claims; authentication does not replace authorization. |

Example of an unsafe design:

~~~java
// DO NOT DO THIS: trusting client-supplied userId.
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') and #request.userId == principal.subject")
public OrderDto getOrder(ReadOrderRequest request) {
    return repository.findById(request.orderId()).orElseThrow();
}
~~~

Even when `request.userId` matches the JWT subject, the client can still supply someone else's `orderId`. Comparing a client-supplied `userId` against the JWT **does not prove the record belongs to that user**.

**Rule:** input data locates the resource; **trusted business data sources** establish the actual owner, tenant, and state of the resource.

## 5. Data Obtained from Authentication and JwtAuthenticationToken

Once a Resource Server validates a Bearer JWT, `Authentication` is typically a **`JwtAuthenticationToken`**. It holds the decoder-verified token, `getAuthorities()`, `getName()`, and claims.

Policy method example:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

public boolean hasVerifiedTenant(
        Authentication authentication, String expectedTenant) {

    if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
            || !authentication.isAuthenticated()) {
        return false;
    }

    Jwt jwt = jwtAuth.getToken();
    Object tenant = jwt.getClaims().get("tenant_id");

    return tenant instanceof String tenantId
        && !tenantId.isBlank()
        && tenantId.equals(expectedTenant);
}
~~~

In this example:

- `authentication` is the context Spring Security passes into the expression, **not an object fabricated by the client in a JSON body**.
- `jwtAuth.getToken()` retrieves the JWT already processed by the Resource Server.
- The custom claim `tenant_id` is checked for **string type** and value rather than blindly calling `toString()`.
- The comparison only verifies that the token carries the expected tenant; it does not yet prove that an **order** actually belongs to that tenant.

**Never assume every Authentication is a JwtAuthenticationToken.** An application may simultaneously support opaque tokens, session/OIDC Login, or other `Authentication` types. For each model, policies must identify the expected principal type and obtain identity/tenant from a trusted, agreed-upon source.

### 5.1. Why Both Issuer and Subject Are Needed When Mapping Internal Users

If the domain stores `owner_user_id` as an internal UUID, the external `sub` claim is not the internal primary key. When mapping is needed, look up accounts by the verified **`(iss, sub)`**:

~~~text
JWT:
  iss = https://identity.example.test/realms/demo
  sub = external-person-42

external_identity:
  (issuer, subject) -> local_user_id

orders:
  owner_user_id = local_user_id
~~~

Avoid looking up accounts solely by `sub` when multiple issuers exist; never automatically merge accounts by token `email`. For client credentials without a human user, policies need a dedicated service-principal model rather than assuming a local user exists.

## 6. Complete End-to-End Example: Only the Order Owner May Read or Edit

The example below illustrates a design where **`@PreAuthorize` invokes a policy bean that queries the database**. It uses:

- A verified `JwtAuthenticationToken`;
- An external identity mapping `(issuer, subject) → localUserId` when the domain has internal users;
- An orders table storing `ownerUserId` and `tenantId`;
- A repository checking whether an order exists with matching owner and tenant;
- A service protected by **scope + policy on `orderId`**.

### 6.1. Required Tables

Illustrative schema (PostgreSQL):

~~~sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);

CREATE TABLE external_identity (
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    user_id UUID NOT NULL REFERENCES app_user(id),
    PRIMARY KEY (issuer, subject)
);

CREATE TABLE app_order (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    owner_user_id UUID NOT NULL REFERENCES app_user(id),
    note TEXT NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL
);

CREATE INDEX idx_app_order_owner_tenant
    ON app_order(owner_user_id, tenant_id);
~~~

**One `(issuer, subject)` pair maps to at most one local user** thanks to the primary key. Data relationships on orders use the internal `user_id`. Production systems require migrations, transactions, domain constraints, and proper database privileges; this SQL focuses strictly on the structure needed for authorization checks.

### 6.2. Order Entity and Repository

The Java snippets below belong in separate class files within the same application.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "app_order")
public class OrderEntity {

    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "owner_user_id", nullable = false)
    private UUID ownerUserId;

    @Column(nullable = false)
    private String note;

    @Column(nullable = false)
    private String status;

    protected OrderEntity() {}

    public UUID getId() { return id; }
    public String getTenantId() { return tenantId; }
    public UUID getOwnerUserId() { return ownerUserId; }
    public String getNote() { return note; }
    public String getStatus() { return status; }

    public void changeNote(String nextNote) {
        this.note = nextNote;
    }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    boolean existsByIdAndTenantIdAndOwnerUserId(
        UUID id, String tenantId, UUID ownerUserId);
}
~~~

`existsByIdAndTenantIdAndOwnerUserId` checks the **real relationship in the database**. It does not use a client-supplied `ownerUserId`. Derived Spring Data JPA query methods depend on the entity's Java property names and configured Spring Data JPA setup.

### 6.3. Looking Up the Linked Local User

Define the contract for an identity-link lookup service:

~~~java
import java.util.Optional;
import java.util.UUID;

public interface LocalIdentityLookup {

    Optional<UUID> findActiveUserId(
        String issuer, String subject);
}
~~~

An implementation of this interface queries **`external_identity`** by both `issuer` and `subject`, joins **`app_user`**, and **only returns the user ID if the account is ACTIVE**. Never auto-create accounts from JWTs without an approved provisioning/linking workflow.

Corresponding SQL example:

~~~sql
SELECT u.id
FROM external_identity ei
JOIN app_user u ON u.id = ei.user_id
WHERE ei.issuer = :issuer
  AND ei.subject = :subject
  AND u.status = 'ACTIVE';
~~~

This separates identity lookup from per-order policies. If a system uses issuer and subject directly as domain IDs from the start, the design may differ, though mixing principals across issuers must still be prevented.

### 6.4. Policy Bean Invoked from SpEL

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component("orderAccess")
public class OrderAccessPolicy {

    private final LocalIdentityLookup identities;
    private final OrderRepository orders;

    public OrderAccessPolicy(
            LocalIdentityLookup identities,
            OrderRepository orders) {
        this.identities = identities;
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public boolean canRead(
            Authentication authentication, UUID orderId) {
        return isOwner(authentication, orderId);
    }

    @Transactional(readOnly = true)
    public boolean canWrite(
            Authentication authentication, UUID orderId) {
        // Real applications must also check order status
        // or state-transition permissions.
        return isOwner(authentication, orderId);
    }

    private boolean isOwner(
            Authentication authentication, UUID orderId) {

        if (orderId == null
                || !(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !authentication.isAuthenticated()) {
            return false;
        }

        Jwt jwt = jwtAuth.getToken();
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        Object tenantClaim = jwt.getClaims().get("tenant_id");

        if (issuer == null
                || subject == null
                || subject.isBlank()
                || !(tenantClaim instanceof String tenantId)
                || tenantId.isBlank()) {
            return false;
        }

        Optional<UUID> localUserId =
            identities.findActiveUserId(issuer, subject);

        return localUserId.isPresent()
            && orders.existsByIdAndTenantIdAndOwnerUserId(
                orderId, tenantId, localUserId.get());
    }
}
~~~

Because it is declared `@Component("orderAccess")`, the bean can be referenced in SpEL as **`@orderAccess`**. If no mapping exists, the account is locked, the tenant claim has the wrong type, the order does not exist, or the owner differs, the policy returns **false** instead of opening access by default.

This example implements an **owner-only** policy; real domains may allow support staff or delegated users to view orders. When such exceptions exist, define **explicit, verifiable rules** rather than changing the fallback to `true`.

### 6.5. Service with @PreAuthorize and Input orderId

~~~java
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record OrderDto(UUID id, String tenantId, String note, String status) {}
record UpdateNoteCommand(String note) {}

@Service
public class OrderService {

    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderAccess.canRead(authentication, #orderId)")
    public OrderDto getOrder(UUID orderId) {
        OrderEntity order = orders.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found"));

        return new OrderDto(
            order.getId(),
            order.getTenantId(),
            order.getNote(),
            order.getStatus());
    }

    @Transactional
    @PreAuthorize(
        "hasAuthority('SCOPE_orders.write') " +
        "and @orderAccess.canWrite(authentication, #orderId)")
    public OrderDto updateNote(
            UUID orderId, UpdateNoteCommand command) {

        if (command == null || command.note() == null) {
            throw new IllegalArgumentException("Invalid command");
        }

        OrderEntity order = orders.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found"));

        // For high-risk updates, re-verify owner, tenant,
        // and domain state inside the transaction.
        order.changeNote(command.note());

        return new OrderDto(
            order.getId(),
            order.getTenantId(),
            order.getNote(),
            order.getStatus());
    }
}
~~~

Here:

- `hasAuthority('SCOPE_orders.read')` or `SCOPE_orders.write` checks the scope mapped to an authority.
- `@orderAccess.canRead(authentication, #orderId)` or `canWrite` checks permission on the **specific record**.
- `#orderId` is a **method argument**, likely coming from the path, not an ID guaranteed to belong to the caller.
- `UpdateNoteCommand` contains only `note`, omitting `ownerUserId` or `tenantId` so clients cannot alter owner or tenant.

**Critical transaction boundary:** having the policy query before the call and the service load the record afterward constitutes **two separate reads**. If ownership, status, or tenant can change concurrently, the system must also guard the **mutation step itself** — for instance by re-checking inside a transaction with locking/versioning or using a conditional `UPDATE` on owner/tenant/state. `@PreAuthorize` is a **pre-method gate**, not an atomic guarantee over all data conditions.

### 6.6. Controller Passes Inputs Without Asserting Permissions

~~~java
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    OrderDto get(@PathVariable UUID orderId) {
        return orders.getOrder(orderId);
    }

    @PatchMapping("/{orderId}")
    OrderDto patch(
            @PathVariable UUID orderId,
            @RequestBody UpdateNoteCommand command) {
        return orders.updateNote(orderId, command);
    }
}
~~~

The controller simply forwards inputs to the **Spring-managed service bean**, without accepting client-supplied `ownerId` or `roles`. Production code must add request body validation, error handling, entity/lifecycle rules, and database transaction policies. Even when controllers have security annotations, placing guards on the service ensures other callers of the service cannot accidentally bypass them.

## 7. Using Input Data Properly in SpEL

Spring Security method expressions can reference parameters by name, object property, or position.

### 7.1. Referencing the #orderId Argument

~~~java
@PreAuthorize("@orderAccess.canRead(authentication, #orderId)")
public OrderDto getOrder(UUID orderId) { ... }
~~~

`#orderId` must be resolved by SpEL as a method parameter. In Java, compile with **parameter name metadata** (such as `-parameters`, depending on Spring Boot/Gradle/Maven configuration), or name the parameter with the `@P` annotation:

~~~java
import org.springframework.security.core.parameters.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("@orderAccess.canRead(authentication, #orderId)")
public OrderDto getOrder(@P("orderId") UUID id) {
    // ...
}
~~~

You can use **`#p0`** or **`#a0`** to reference the first parameter by position when parameter names are absent:

~~~java
@PreAuthorize("@orderAccess.canRead(authentication, #p0)")
public OrderDto getOrder(UUID id) { ... }
~~~

However, positional references break easily if refactoring changes argument order. **Keep explicit parameter names/annotations** and write tests proving the expression receives the expected argument. An expression referencing a nonexistent parameter can fail evaluation or cause request rejection; never expect it to pull values from the URL automatically.

### 7.2. Accessing Properties of a Command Object

Order creation method example:

~~~java
public record CreateOrderCommand(
    String tenantId,
    String productCode,
    int quantity) {}
~~~

A policy can inspect the tenant the client wishes to act upon:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and @tenantAccess.canCreate(authentication, #command.tenantId)")
public UUID createOrder(CreateOrderCommand command) {
    // ...
}
~~~

Crucially, `#command.tenantId` is still a **client-requested value**. The `tenantAccess` bean must **verify membership and permissions against a trusted data source**, rather than returning `true` simply because `command.tenantId` is non-empty. In Java, SpEL accesses properties via record/JavaBean accessors; if using different object types or SpEL versions, declare consistent accessors and test the expression. When you want to avoid property resolution, pass the whole `#command` to a Java policy method.

### 7.3. Never Use Input as an Expression or Arbitrary Authority Name

What not to do:

~~~java
// DO NOT DO THIS: treating a client-requested authority as the required one,
// or concatenating input into a dynamic SpEL string.
@PreAuthorize("hasAuthority(#command.requestedAuthority)")
public void perform(AdminCommand command) {
    // ...
}
~~~

The condition above only checks whether the caller holds **the authority the caller themselves chose** inside the command. If they hold a lower authority such as `SCOPE_profile.read`, the caller can set `requestedAuthority` to that value and pass the check, while the actual operation might delete a user.

Replace it with a policy based on the **server-defined action**:

~~~java
@PreAuthorize("hasAuthority('SCOPE_admin.users.delete')")
public void deleteUser(UUID targetUserId) {
    // ...
}
~~~

Similarly, never take strings from a URL or body and **concatenate them into SpEL for evaluation**. `@PreAuthorize` expressions must be statically defined in controlled code/configuration; caller inputs must strictly be treated as **parameter values** inside policies.

## 8. Using @PreAuthorize for Read, Write, and Admin

A system with multiple rules can build the following guards:

### 8.1. Reading Only for the Resource Owner

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @orderAccess.canRead(authentication, #orderId)")
public OrderDto getOrder(UUID orderId) { ... }
~~~

Use this when read permission is tied to the order owner or tenant. Never skip `canRead` just because the token carries the read scope.

### 8.2. Writing Data and Checking State

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and @orderAccess.canWrite(authentication, #orderId)")
public void updateOrder(UUID orderId, UpdateNoteCommand command) {
    // ...
}
~~~

The `canWrite` method must check domain-specific policies such as ownership, tenant, and editable states. For concurrently modified data, transactions and conditional updates remain essential; see Section 10.

### 8.3. Admin Overrides Must Be Explicit

If the domain grants administrative permission to view others' orders:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_admin.orders.read') " +
    "or (hasAuthority('SCOPE_orders.read') " +
    "and @orderAccess.canRead(authentication, #orderId))")
public OrderDto getOrder(UUID orderId) { ... }
~~~

This is an example policy **allowing admin reads**; not every system should grant that privilege. If an admin is only permitted to administer assigned tenants, the admin branch must also enforce a **tenant policy**, never acting as a system-wide bypass. Avoid overly broad `or` clauses like `hasRole('USER') or ...` that nullify the owner condition.

### 8.4. Data-Dependent Permissions, Not Just Arguments

An `approveOrder(orderId)` request may require:

- `SCOPE_orders.approve`.
- The approver is not the order creator (separation of duties).
- Holding an approver role within the order's tenant.
- The order being in `PENDING_APPROVAL` status.
- The approver's financial limits and policies permitting the amount.

These conditions require reading **actual record state and policy data**, and cannot be verified solely from `orderId` or a client-sent `approve=true`. `@PreAuthorize` can invoke a policy bean to reject early; the service must still enforce a valid transition **inside the transaction** so concurrent updates do not cause erroneous approvals.

## 9. Writing Policy Beans Instead of Overly Long SpEL

A long expression:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and #request.tenantId == authentication.tokenAttributes['tenant_id'] " +
    "and #request.ownerId == authentication.name " +
    "and #request.status != 'CLOSED'")
~~~

looks like it covers many checks, but in practice:

- `request.tenantId`, `ownerId`, and `status` may be client-chosen.
- `authentication.name` may be an external `sub`, not a local user ID.
- `request.status` is not the order status **currently persisted in the database**.
- The types of the `tenant_id` claim or object properties may violate the contract.
- It cannot replace checking real record state and concurrency.

A clearer approach:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and @orderPolicy.canApply(authentication, #orderId, #command)")
public void apply(UUID orderId, UpdateOrderCommand command) {
    // ...
}
~~~

`orderPolicy.canApply` can perform:

1. Identify the trusted principal and token type.
2. Resolve the local account if the domain uses local users.
3. Verify tenant membership from the database.
4. Load the actual order, actual owner, and actual status.
5. Check which command fields the caller is allowed to modify.
6. Return `false` if data is insufficient or permission is lacking.

**Never assume having a policy bean automatically makes every mutation safe.** If the policy and write run in separate transactions or data can change concurrently, guard the update in the service/repository as shown in the next section.

## 10. TOCTOU: @PreAuthorize Does Not Make Check and Write Atomic

**Time-of-check to time-of-use (TOCTOU)** occurs when permission or state holds at check time but changes before use.

~~~text
T0: @PreAuthorize calls canWrite
    -> Order belongs to user A, status DRAFT -> true

T1: Another transaction moves order to CLOSED
    or changes owner/tenant under another policy.

T2: updateOrder loads and saves order
    -> Without re-checking, it may write against the current state illegally.
~~~

Because method security checks generally run **before the method body**, do not assume `@Transactional` on a service automatically locks all queries in both the policy bean and method body within the same condition. Advisor ordering and transaction behavior depend on configuration; even within a single transaction, isolation levels may not prevent all race conditions.

### 10.1. Re-Checking Inside the Transaction or Using Conditional Updates

One technique is a query that updates only when **owner, tenant, and status** currently match:

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface GuardedOrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    @Modifying
    @Query("""
        update OrderEntity o
           set o.note = :nextNote
         where o.id = :id
           and o.tenantId = :tenantId
           and o.ownerUserId = :ownerId
           and o.status = 'DRAFT'
        """)
    int updateDraftNoteIfOwned(
        @Param("id") UUID id,
        @Param("tenantId") String tenantId,
        @Param("ownerId") UUID ownerId,
        @Param("nextNote") String nextNote);
}
~~~

The service can call this method **inside a transaction**, taking `tenantId` and `ownerId` from the verified/resolved context—**never from an unchecked body**—and then check the updated row count:

~~~java
int affected = repository.updateDraftNoteIfOwned(
    orderId, verifiedTenant, currentLocalUserId, newNote);

if (affected != 1) {
    throw new AccessDeniedException(
        "Operation is not permitted");
}
~~~

Thus, the database updates only if the owner/tenant/state conditions **still hold at statement execution time**. Never treat `affected == 0` as success; it may mean the order does not exist, the caller lacks permission, or the status no longer permits editing.

In production applications, `@Modifying` requires an appropriate transaction, and you must understand the effect of bulk JPQL updates on the persistence context/cache (entities may need to be cleared or refreshed). Furthermore, complex concurrent updates may require optimistic locking (`@Version`), pessimistic locking, or an appropriate transaction isolation level. **No single option fits every domain.**

### 10.2. @PreAuthorize Remains Useful

The `@PreAuthorize` layer rejects requests missing scopes or obviously lacking permission early, avoiding unnecessary business execution. The transaction/data-policy layer guarantees that the **actual operation** never bypasses critical conditions. This is **defense in depth**, not pointless duplication.

## 11. How Do @PostAuthorize, @PreFilter, and @PostFilter Differ?

Beyond `@PreAuthorize`, Spring Security method security provides annotations that evaluate data at different points.

| Annotation | Timing | Example Usage | Notes |
| --- | --- | --- | --- |
| **`@PreAuthorize`** | Before method body. | Caller has scope and permission to invoke with `orderId`. | Cannot see return object; usually best for early blocking. |
| **`@PostAuthorize`** | After method has produced a result. | Check owner of returned object. | Method has already run; **never use as the sole guard for writes/side effects**. |
| **`@PreFilter`** | Filters input collections before method. | Drop unauthorized items from an input collection. | Can mask client errors; consider rejecting the whole batch instead of silent filtering. |
| **`@PostFilter`** | Filters returned collection. | Return only viewable items. | May already overfetch data, hurting performance and risking leaks outside the filter layer. |

### 11.1. @PostAuthorize Example for Reading Data

~~~java
@PostAuthorize(
    "returnObject.ownerUserId == @currentAccount.id(authentication)")
public OrderDto getOrder(UUID orderId) {
    // ...
}
~~~

**This is purely a conceptual example**: the `OrderDto` in the earlier service did not include `ownerUserId`, so a real DTO/domain object with `ownerUserId` and an implemented `currentAccount` bean would be needed to run this. `@PostAuthorize` can be useful for read results, though the method has already executed and may have loaded sensitive data into memory. Avoid it if calling the method sends emails, writes to the database, or causes external side effects before the check.

For multi-record lists, it is generally better to **constrain the query by tenant/owner directly in the database** rather than fetching everything and applying `@PostFilter`; this keeps pagination/counts policy-compliant and reduces leakage risks via other side effects.

### 11.2. Why @PreAuthorize + Policy Bean Is Often a Good Choice

For `getOrder(orderId)`, the **input ID is known prior to reading**. A policy bean can query owner/tenant conditions and deny immediately. If you want to combine the business query and authorization to avoid two reads, use a repository method incorporating owner/tenant in its conditions and throw `AccessDeniedException` when not found. `@PreAuthorize` does not have to contain all domain logic; what matters is that **no path to the data skips permission checks**.

## 12. Method Security Uses Proxies: Do Not Let Annotations Be Bypassed

In a typical Spring Security Servlet setup, method authorization is applied via **Spring AOP proxies**. This has several practical consequences.

### 12.1. Calling from Another Bean Through the Proxy

~~~text
OrderController
    |
    | calls Spring-managed OrderService bean
    v
Spring proxy of OrderService
    |
    | evaluates @PreAuthorize
    v
OrderService.getOrder(...)
~~~

If an instance is created via `new OrderService(...)` outside the Spring container, annotations are not automatically applied by Spring AOP. Use dependency injection for services using method security.

### 12.2. Self-Invocation Can Bypass Protection

Example:

~~~java
@Service
public class UnsafeOrderService {

    public void batchProcess(UUID orderId) {
        // Internal call via 'this' may not pass through the proxy.
        updateSensitiveOrder(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public void updateSensitiveOrder(UUID orderId) {
        // ...
    }
}
~~~

In the standard proxy model, `batchProcess` calls `updateSensitiveOrder` **within the same instance**, so `@PreAuthorize` can be skipped. Do not treat an annotation as guaranteed protection if the method is invoked via `this`.

Clear solutions:

- Move the sensitive method to **another Spring-managed bean** and invoke it via dependency injection.
- Protect the `batchProcess` entry point as well if it allows triggering sensitive actions.
- Keep **domain authorization checks** inside the actual operation, especially when multiple call paths exist.
- Test both **internal and external** call paths so no bypasses remain.

`private` methods, `final` methods, or `final` classes may not be intercepted as expected depending on proxy mode and configuration. Place `@PreAuthorize` on public methods of Spring beans and invoke them through proxies; if using AspectJ or a custom proxy strategy, understand your project's mechanism. Never merely check that an annotation "exists in source" without verifying it actually executes.

### 12.3. Calls Outside Request Threads

With `@Async`, scheduled jobs, message listeners, or multithreaded processing, the `SecurityContext` from an HTTP request is not automatically available on every thread. Do not assign a fake `Authentication` with admin privileges just to "make the code run." Instead, system flows need dedicated service identities and policies, or an appropriate context-propagation mechanism where permitted.

Method security is part of **application execution rules**, not a mechanism to fabricate Authentication wherever a service is used.

## 13. Testing @PreAuthorize and Call Input Data

Tests must prove that **the expression is triggered**, **authorities are read properly**, **arguments are received accurately**, and **policies protect the resource**. Two test groups can be separated:

1. **Method security/unit-integration tests:** Spring context with `@EnableMethodSecurity`, service beans, and intentional mock `Authentication`.
2. **HTTP + JWT integration tests:** sending genuinely signed Bearer JWTs through the Resource Server to verify decoder, scopes, and policies together.

### 13.1. Testing with @WithMockUser: What You Gain and Lose

`spring-security-test` allows:

~~~java
@WithMockUser(authorities = "SCOPE_orders.read")
@Test
void readScopeCanCallMethod() {
    // Call service via Spring bean, expecting allow
    // when orderId policy is satisfied by mock/fixture.
}
~~~

This is a good test for **authority expressions** and the proxy mechanism. However, `@WithMockUser` typically creates a username/password-style Authentication, **not a `JwtAuthenticationToken`**. If the policy checks:

~~~java
authentication instanceof JwtAuthenticationToken
~~~

then `@WithMockUser` **is not sufficient to test the real flow successfully**; the policy may return false because the principal type differs. Use a simulated `JwtAuthenticationToken` or MockMvc `jwt()` instead.

### 13.2. Creating a JwtAuthenticationToken in Service Tests

A fixture can build a structurally valid mock `JwtAuthenticationToken` and place it into `SecurityContext` for **method security tests** (not signature tests):

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

public final class JwtMethodSecurityFixture {

    private JwtMethodSecurityFixture() {}

    public static void authenticate(
            String issuer,
            String subject,
            String tenantId,
            String authority) {

        Instant now = Instant.now();

        Jwt jwt = new Jwt(
            "synthetic-test-token",
            now,
            now.plusSeconds(600),
            Map.of("alg", "RS256"),
            Map.of(
                "iss", issuer,
                "sub", subject,
                "aud", List.of("orders-api"),
                "tenant_id", tenantId));

        JwtAuthenticationToken authentication =
            new JwtAuthenticationToken(
                jwt,
                List.of(new SimpleGrantedAuthority(authority)));

        SecurityContextHolder.getContext()
            .setAuthentication(authentication);
    }

    public static void clear() {
        SecurityContextHolder.clearContext();
    }
}
~~~

This is a **test helper**, never to be used in production to mint arbitrary privileges. Clear the `SecurityContext` after every test (e.g., via JUnit `@AfterEach`) to avoid leaking Authentication across tests on the same thread. Because authorities in this fixture are set manually, it **does not prove `JwtGrantedAuthoritiesConverter`** maps scopes properly.

### 13.3. Unit/Integration Testing Policy by orderId Argument

Conceptual test with Spring-managed service and repository/test fixtures:

~~~text
Given JWT subject = person-A, tenant_id = tenant-A,
      authority = SCOPE_orders.read
And identity(person-A) -> local-user-A ACTIVE
And order-111 belongs to local-user-A and tenant-A
And order-222 belongs to local-user-B and tenant-A

When OrderService.getOrder(order-111)
Then allowed (if order-111 exists and query succeeds)

When OrderService.getOrder(order-222)
Then AccessDeniedException

When JWT authority only = SCOPE_orders.write
And OrderService.getOrder(order-111)
Then AccessDeniedException
~~~

A sample test class with Spring context invoking the service and using `assertThrows`; this assumes **repository test data has been prepared**:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class OrderMethodSecurityTest {

    @Autowired OrderService service;

    private final UUID orderOwnedByOtherUser =
        UUID.fromString("22222222-2222-4222-8222-222222222222");

    @AfterEach
    void tearDown() {
        JwtMethodSecurityFixture.clear();
    }

    @Test
    void readerCannotReadSomeoneElsesOrder() {
        JwtMethodSecurityFixture.authenticate(
            "https://identity.example.test/realms/demo",
            "person-A",
            "tenant-A",
            "SCOPE_orders.read");

        assertThrows(
            AccessDeniedException.class,
            () -> service.getOrder(orderOwnedByOtherUser));
    }
}
~~~

**Note:** the test above requires database fixtures mapping principal A and order 222 belonging to another user; it is not a standalone test runnable from the snippet alone. It demonstrates **invoking the Spring-managed service bean** so the Spring method interceptor has a chance to execute. Without fixture data, the test may fail for reasons unrelated to permissions.

### 13.4. MockMvc(jwt()) to Test HTTP + @PreAuthorize

For a controller calling a service bean, you can use the helper:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", ownOrderId)
        .with(jwt()
            .jwt(jwt -> jwt
                .issuer("https://identity.example.test/realms/demo")
                .subject("person-A")
                .claim("tenant_id", "tenant-A"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

For `otherOrderId`, under the same security context:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", otherOrderId)
        .with(jwt()
            .jwt(jwt -> jwt
                .issuer("https://identity.example.test/realms/demo")
                .subject("person-A")
                .claim("tenant_id", "tenant-A"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isForbidden());
~~~

Both examples assume tests have seeded identity/order data and an appropriate Spring Security/MVC context. `spring-security-test`'s `jwt()` helper constructs an authenticated principal **without passing through `JwtDecoder` for signature verification**. It is useful for testing permissions based on **method arguments and database policies**, but does not prove tokens from a real issuer will be accepted.

To verify signature, audience, expiration, and JWT claim conversion, write a dedicated test using **JWTs signed with a test private key** and a real `NimbusJwtDecoder` or test JWKS server.

### 13.5. Mandatory Test Matrix for Input Data

| Scenario | Expected Outcome |
| --- | --- |
| Valid JWT, `SCOPE_orders.read`, order belongs to caller | Readable if domain permits. |
| Valid JWT, has read scope, order belongs to another user | **403** from method/domain policy. |
| Valid JWT, has read scope, order belongs to another tenant | **403** (or 404 per resource-hiding policy). |
| Valid JWT, missing read scope, order belongs to caller | **403** from `hasAuthority`. |
| JWT has write scope, calls read endpoint under another policy | Follows defined policy; never infer write implies read. |
| Valid JWT, internal user is SUSPENDED | Denied due to identity/domain policy. |
| Valid JWT, `tenant_id` missing or wrong type | Validator or policy denies; no access granted. |
| JWT from another issuer with colliding `sub` | Do not use another trusted issuer's identity link. |
| Forged JWT signature with valid user's `sub` | **401** from decoder; never enters method as valid principal. |
| Client sets `ownerId` in body to another user | Never changes owner outside authorized workflows. |
| Client sets `requestedAuthority` in body to low privilege to bypass | Sensitive method still requires server-defined authority. |
| Nonexistent `orderId` | Returns no data; 404/403 per non-disclosure policy. |
| Order changes status/owner between check and write | Transaction/update guard blocks policy-violating update. |
| Service calls `@PreAuthorize` method on itself via `this` | Test detects bypass; fix architecture/proxy afterward. |

**Most important negative test:** with the exact same JWT and scope, changing the **`orderId` argument** from an authorized order to an unauthorized order must flip the outcome from **allow** to **deny**. If both still succeed, the policy is not truly binding permissions to the data.

## 14. HTTP Errors and Appropriate Responses

In a Resource Server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

typically occurs when no valid token is provided or the token fails signature, issuer, audience, or expiration checks. The request cannot establish a trusted principal.

If the JWT is authenticated, yet lacks the authority or `@PreAuthorize` returns false:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"code":"forbidden","message":"Insufficient permissions to perform this operation."}
~~~

Details of `WWW-Authenticate` and the response body depend on Spring Security exception handling and the API contract. For errors raised in the filter chain before the controller, `@RestControllerAdvice` does not cover every case. For `AccessDeniedException` thrown inside services/controllers, add integration tests verifying translation into the expected HTTP status code.

Avoid returning responses like:

~~~json
{
  "error": "Order 222 belongs to user-B in tenant-secret"
}
~~~

Such a message leaks resource existence and owner information. For systems needing to hide resource existence, **404 Not Found** can be returned when read access is denied, provided it is consistent, avoids timing/size/error-detail leaks, and still writes internal audit logs as needed.

Never log raw Bearer JWTs, `Authorization` headers, or personal claims merely to debug `@PreAuthorize`. Logs may record **request IDs, normalized error category codes, and policy outcomes**, alongside controlled internal identifiers in an access-restricted audit system.

## 15. Common Mistakes When Combining Authorities and Inputs

| Mistake | Consequence | Proper Approach |
| --- | --- | --- |
| Checking only `hasAuthority` on a method taking `orderId`. | Callers with the scope can view/modify others' records. | Check owner/tenant against real data. |
| Comparing JWT subject with a client-sent `userId`. | Does not prove the order belongs to the subject. | Look up the order and verified identity mapping. |
| Trusting `tenantId`/role/owner in the body as verified permission. | Client self-asserts permissions. | Compare against verified claims and membership/domain state. |
| Dynamically picking required authority from `command.requestedAuthority`. | Client can pick a low-privilege check. | Require fixed server-defined authorities per operation. |
| Mixing `hasRole` and `hasAuthority` without understanding prefixes. | Broken rules or accidental access. | Distinguish `ROLE_` and `SCOPE_`; test converters. |
| Forgetting `@EnableMethodSecurity`. | Annotations may not be enforced. | Enable method security and test through Spring context. |
| Calling annotated method via `this` in the same bean. | Bypasses Spring AOP proxy. | Call via another bean / design explicit method guards. |
| Putting annotations on `private` or `final` methods assuming interception. | Guards may not run. | Protect proxy-compatible public methods and test behavior. |
| `#orderId` fails to resolve due to missing parameter name metadata. | Unexpected evaluation errors or denials. | Use `-parameters`, `@P`, or `#p0` intentionally. |
| Using `@PostAuthorize` as the sole guard for writes. | Side effects already occurred before blocking. | `@PreAuthorize` + domain transaction guard. |
| Checking owner only before transaction without protecting the update. | TOCTOU / race condition. | Re-check inside transaction, conditional update/locking. |
| Testing with `@WithMockUser` when policy requires `JwtAuthenticationToken`. | Test does not simulate the right principal type. | Use `JwtAuthenticationToken` fixture or `jwt()`. |
| Testing with MockMvc `jwt()` and concluding the decoder is secure. | Helper skips signature/issuer/audience checks. | Test genuinely signed JWTs and decoder separately. |
| Permitting all URLs because one service has `@PreAuthorize`. | Other endpoints may call unguarded logic. | HTTP rules with deny fallback plus method/domain security. |
| Failing to distinguish service principals and human users. | Client credentials tokens may impersonate user privileges. | Enforce policies by token profile and identity type. |

## 16. Method for Designing a Policy for a New Method

When protecting `approveOrder(UUID orderId, ApproveCommand command)`, do not start with a long SpEL expression. Answer sequentially:

1. **How is the caller authenticated?** JWT Access Token or opaque token? Have issuer/audience/expiry been validated? Should this be a user or service principal?
2. **What coarse operation permission is required?** E.g., `SCOPE_orders.approve` — an authority provided by a trusted token/converter.
3. **What inputs does the method receive?** `orderId`, `command.reason`, `command.status` — all are data requiring validation, not permissions.
4. **Where does the real business data live?** The database holds order owner, tenant, and workflow state; the policy must read that record.
5. **What permission exceptions are allowed?** Supervisor/admin, delegation, limits; define them explicitly and verify tenant scope so general admin roles never become unintended bypasses.
6. **Where do we block before the method?** `@PreAuthorize` combining fixed authority checks and a policy bean call with arguments.
7. **How do we protect the write itself?** Transactions, constraints, optimistic locking, or conditional updates when state/owner can change.
8. **What call paths exist?** HTTP, batch, async, self-invocation; every entry point needs appropriate guards.
9. **Which cases must be rejected?** Missing scope, wrong issuer, unmapped subject, wrong tenant, wrong owner, invalid status for action, abnormal inputs, race conditions.
10. **How do we know the guard actually runs?** Test through the Spring proxy, test across different `orderId`s, and add signed-JWT integration tests for authentication.

The final expression can stay concise:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.approve') " +
    "and @approvalPolicy.canApprove(authentication, #orderId, #command)")
public ApprovalResult approveOrder(
        UUID orderId, ApproveCommand command) {
    // Domain transaction still constrains state/owner/tenant.
}
~~~

`approvalPolicy`, `ApproveCommand`, and `ApprovalResult` above are **illustrative components to be implemented per business requirements**, not built-in Spring Security APIs. The Java policy beneath the annotation must handle both authenticated data and current order conditions.

## 17. Summary

Three rules to apply consistently:

1. **Authorities answer "Is the caller permitted this operation type?"** For example `SCOPE_orders.read` or `SCOPE_orders.write`, derived from a verified `Authentication`.
2. **Input data answers "Which object does the caller want to act on?"** For example `#orderId` or `#command.tenantId`; these values are generally client-controlled and do not prove permission.
3. **Business policies answer "Is the caller allowed on that exact object in its current state?"** Check owner, tenant, local account, membership, and database state; for writes, guard the outcome inside a transaction.

`@PreAuthorize` is most effective when applied to **Spring-managed service methods**, combining `hasAuthority` with a **policy bean evaluating arguments against trusted data**, backed by **tests that genuinely execute through the proxy**. JWT validation, HTTP rules, and transaction/data guards are complementary layers — none should be omitted simply because another layer allowed the request.

## References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html).
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — JWT Authentication Converter](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html#oauth2resourceserver-jwt-authorization).
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/).
