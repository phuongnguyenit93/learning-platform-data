# AuthorizationManager or Custom Authorization Decision Components

In a **Spring Security OAuth 2.0/OIDC Resource Server**, a valid JWT access token only proves that the request passed **authentication** according to the trust configuration. Afterward, the application must still decide **whether the principal is allowed to perform a specific action on a specific resource**. Built-in rules like `authenticated()`, `hasAuthority("SCOPE_orders.read")`, and `hasRole("ADMIN")` cover straightforward cases. However, a business rule such as "staff may only approve refunds for merchants they manage, within their limit, and only when the transaction has not yet been refunded" requires additional relationships, state, and dynamic policies.

Spring Security provides **`AuthorizationManager<T>`** to express access decisions; an application can also write a **business authorization service** or **policy component** invoked at the method/service boundary.

> **Principle:** custom authorization is where you **check permissions based on trustworthy evidence**, not where you manually re-verify JWT signatures, invent scopes/roles, or trust a client-supplied tenant ID as proof of granted authority.

This lesson targets **Java 17+, Spring Boot, Spring Security Servlet/Spring MVC, and a JWT Resource Server**. With WebFlux, the reactive APIs differ, though the trust and business-authorization reasoning remains similar.

## 1. Authentication Does Not Replace Business Authorization

Suppose a JWT access token contains:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 2000000300
}
~~~

The Resource Server uses `JwtDecoder` to verify signature, issuer, audience, expiration, and token policies. Spring Security typically maps scopes into:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

However, two scopes are not enough to answer:

- Does user 42 belong to tenant `merchant-a`?
- Is the user allowed to view all orders of the merchant or only assigned orders?
- Does `order-9001` actually belong to the requested tenant?
- Can an order that is already locked, delivered, or refunded still be modified?
- Can a recently revoked role still be exercised from an unexpired JWT?
- Does an approval request require separation between creator and approver?

Those questions belong to **business authorization**.

| Layer | Question | Common Mechanism |
|---|---|---|
| Authentication | Is the token valid and meant for this API? | JWT verification, `iss`, `aud`, `exp` |
| HTTP authorization | Which scope/role does the route require? | `authorizeHttpRequests`, `hasAuthority` |
| Tenant authorization | Does the principal have permissions in the requested tenant? | Membership policy, tenant DB |
| Object-level authorization | Does the principal have permission on the specific record? | Owner/ACL, relationship policy |
| State authorization | Is the action valid in the current state? | Domain policy, transaction |
| Enforcement | Where do we block unauthorized calls? | Filter, method, business service |

A JWT with a valid signature is an **input** to authorization, not a blanket allow decision.

## 2. When Should You Write a Custom Component?

Prefer built-in rules when you only need to check an authority:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
.anyRequest().denyAll()
~~~

A custom policy is appropriate when also checking:

1. Membership in an organization or tenant.
2. Ownership of or assignment to a record.
3. Management relationships between two principals.
4. Financial limits and transaction status.
5. Separation of duties between creator and approver.
6. Policy-driven step-up authentication/MFA.
7. Dynamic permissions from a database or policy service.
8. Consistent permissions enforced across HTTP, message consumers, and batch services.

**Choose the check point based on available context.** An HTTP manager has the URL, method, authentication, and path variables, but may not yet have the actual entity. When decisions depend on mutable entity state, placing critical checks at the service/transaction boundary is usually safer and clearer.

## 3. The `AuthorizationManager<T>` Mechanism

Modern Spring Security uses `AuthorizationManager<T>` for access decisions at request and method boundaries. It replaces legacy APIs like `AccessDecisionManager` and `AccessDecisionVoter` in the new authorization architecture.

Abbreviated API concept:

~~~java
public interface AuthorizationManager<T> {
    AuthorizationResult authorize(
        Supplier<Authentication> authentication,
        T secureObject
    );
}
~~~

The snippet above illustrates structure only, not the full interface source.

- `Supplier<Authentication>` allows retrieving authentication lazily when needed.
- `T` describes the secured object, such as `RequestAuthorizationContext` or `MethodInvocation`.
- `AuthorizationResult` represents the decision result; `AuthorizationDecision` is the standard implementation.
- `authorize(...)` can return `new AuthorizationDecision(true)` or `new AuthorizationDecision(false)`.
- `null` typically means abstain: the manager renders no decision. Never equate abstain with deny across every composition strategy.

In Spring Security 6.4+/7.x, the documentation recommends **`authorize(...)`**. The legacy **`check(...)`** API has been marked deprecated. For projects on older Spring Security versions, verify method signatures against that version.

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;

AuthorizationResult allow = new AuthorizationDecision(true);
AuthorizationResult deny = new AuthorizationDecision(false);

boolean canProceed = allow.isGranted(); // true
~~~

**Do not return `null` to mean "unsure, let it pass."** For a policy enforcing mandatory permissions, return an explicit deny whenever required data is missing.

## 4. Relationship Between PEP, PDP, and PIP

An authorization architecture can be separated into:

~~~text
HTTP request / service call
          |
          v
PEP — Policy Enforcement Point
    (Security Filter or service)
          |
          | asks for decision
          v
PDP — Policy Decision Point
    (AuthorizationManager / policy engine)
          |
          | fetches trusted data
          v
PIP — Policy Information Point
    (Verified JWT, ACL, membership, resource state)
          |
          v
ALLOW / DENY / ERROR
          |
          v
PEP executes the operation only when ALLOW
~~~

**PEP** is where execution is gated. **PDP** computes decisions from policies. **PIP** supplies permission and resource attributes.

In Spring Security, `AuthorizationFilter` can act as the PEP at the HTTP boundary and a custom `AuthorizationManager` as the PDP. Yet an `OrderService` can also act as a PEP to enforce order-state invariants at the transaction boundary.

Having HTTP authorization does not remove the responsibility to enforce business invariants in the service layer.

## 5. Sample Problem: Tenant-Scoped Order Reading Permissions

Consider the endpoint:

~~~http
GET /api/tenants/{tenantId}/orders
Authorization: Bearer <access_token>
~~~

Business rules simultaneously require:

- Valid JWT with matching issuer, audience, and expiration.
- Authentication holds `SCOPE_orders.read`.
- URL contains a valid tenant ID.
- Subject is mapped via `(issuer, subject)` to avoid ambiguity across IdPs.
- Subject has membership allowing order reads in the requested tenant.
- Orders actually returned belong to that tenant.

Membership must be proven from an **authoritative permission source**; the tenant ID in the path only describes the **target**, never proving access rights.

### 5.1. Contract for the Membership Source

~~~java
package com.example.orders.security;

// Requires an implementation querying a DB or trusted authorization service.
public interface TenantMembershipPolicy {

    boolean canReadOrders(
        String issuer,
        String subject,
        String tenantId
    );
}
~~~

If subjects are identified solely by `sub`, two different issuers could accidentally merge users. The `(iss, sub)` pair is a safer basis when multiple issuers exist.

### 5.2. Implementing a Custom HTTP Manager

~~~java
package com.example.orders.security;

import java.util.function.Supplier;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;

@Component
public final class TenantOrdersReadAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final TenantMembershipPolicy memberships;

    public TenantOrdersReadAuthorizationManager(
            TenantMembershipPolicy memberships) {
        this.memberships = memberships;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current = authentication.get();

        if (!(current instanceof JwtAuthenticationToken jwtAuth)
                || !current.isAuthenticated()) {
            return new AuthorizationDecision(false);
        }

        boolean hasReadScope = current.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch("SCOPE_orders.read"::equals);

        if (!hasReadScope) {
            return new AuthorizationDecision(false);
        }

        String tenantId = context.getVariables().get("tenantId");

        if (tenantId == null || tenantId.isBlank()) {
            return new AuthorizationDecision(false);
        }

        Jwt jwt = jwtAuth.getToken();
        String subject = jwt.getSubject();
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();

        if (issuer == null || subject == null || subject.isBlank()) {
            return new AuthorizationDecision(false);
        }

        boolean allowed =
            memberships.canReadOrders(issuer, subject, tenantId);

        return new AuthorizationDecision(allowed);
    }
}
~~~

Notable points:

- The manager **does not manually parse JWTs** and does not select public keys itself.
- It only accepts a `JwtAuthenticationToken` verified by the JWT Resource Server infrastructure.
- It retains the `SCOPE_orders.read` check; membership does not replace scope.
- Missing path variable or missing identity → deny.
- Membership from the trusted source determines the final outcome.
- It never injects `ROLE_ADMIN` or new scopes into `Authentication`.

### 5.3. What Does `RequestAuthorizationContext` Contain?

`RequestAuthorizationContext` provides:

- `getRequest()`: `HttpServletRequest`.
- `getVariables()`: path variables extracted by the matcher if the matcher supports them.

`context.getVariables().get("tenantId")` relies on the `{tenantId}` pattern matching and extracting properly. Differences in `PathPatternRequestMatcher`, Spring MVC integration, servlet paths, or framework versions can affect this. If the variable is absent, the sample code **fails closed**, never falling back to a client-sent header as proof of membership.

## 6. Wiring the Manager into `SecurityFilterChain`

`build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

`audiences` is a property in modern Spring Boot versions; if your version does not support it, configure an audience validator on `JwtDecoder`. Use genuine access tokens for the Resource Server, never substituting an OIDC client ID token.

Declaring the filter chain:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            TenantOrdersReadAuthorizationManager tenantOrdersRead)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()

                .requestMatchers(
                    HttpMethod.GET,
                    "/api/tenants/{tenantId}/orders/**")
                    .access(tenantOrdersRead)

                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()

                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

`access(tenantOrdersRead)` instructs Spring Security to invoke the custom manager for requests matching that specific matcher. `anyRequest().denyAll()` closes any path not declared in the chain.

This example focuses on authorization. CSRF, sessions, and CORS must be configured according to how clients transmit credentials. With browser cookies/sessions, **never disable CSRF unconditionally**. For stateless APIs receiving only bearer headers, CSRF policy may differ but still requires review.

### 6.1. Matcher Ordering Can Bypass Custom Policies

Wrong:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/tenants/{tenantId}/orders/**")
        .access(tenantOrdersRead)
    .anyRequest().denyAll()
)
~~~

The broad rule `/api/**` matches first and prevents the custom manager **from ever being called**. Place specific rules before general ones.

When multiple `SecurityFilterChain` beans exist, `securityMatcher` selects the chain while `requestMatchers` selects rules within that chain. Never assume `anyRequest().denyAll()` on a chain with `securityMatcher("/api/**")` protects URLs outside `/api/**`.

## 7. HTTP Authorization Does Not Prove Record-Level Permission

Suppose a user belongs to `tenant-a`, yet intentionally calls:

~~~http
GET /api/tenants/tenant-a/orders/order-from-tenant-b
Authorization: Bearer <valid-access-token>
~~~

The HTTP manager confirms the user has the scope and tenant A membership. Yet if the service queries:

~~~java
// DANGEROUS when not checking the order's tenant.
Order order = repository.findById(orderId).orElseThrow();
~~~

it can return tenant B's data. This is **Broken Object Level Authorization (BOLA/IDOR)**.

The right approach checks the order–tenant relationship in the query and service logic:

~~~java
// Pseudocode: application-defined repository API.
Order order = repository
    .findByIdAndTenantId(orderId, tenantId)
    .orElseThrow(NotFoundException::new);

if (!orderPolicy.canReadOrder(principal, order)) {
    throw new AccessDeniedException("Not permitted");
}

return order;
~~~

`Order`, `NotFoundException`, `orderPolicy`, and `principal` are illustrative domain components. Never assume an HTTP membership check alone is enough to expose every record in a tenant.

## 8. `@PreAuthorize` and Custom Authorization Beans

A policy needing `orderId` or the actual entity usually belongs near the business service. Spring Security method security lets `@PreAuthorize` invoke a policy bean.

### 8.1. Enabling Method Security

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

### 8.2. Defining Policy at the Service Boundary

~~~java
package com.example.orders.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("orderAuthz")
public final class OrderAuthorization {

    private final OrderAccessPolicy orderAccess;

    public OrderAuthorization(OrderAccessPolicy orderAccess) {
        this.orderAccess = orderAccess;
    }

    public boolean canRead(
            Authentication authentication,
            String orderId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !authentication.isAuthenticated()
                || orderId == null || orderId.isBlank()) {
            return false;
        }

        boolean hasScope = authentication.getAuthorities().stream()
            .anyMatch(a ->
                "SCOPE_orders.read".equals(a.getAuthority()));

        if (!hasScope) {
            return false;
        }

        Jwt jwt = jwtAuth.getToken();
        if (jwt.getIssuer() == null || jwt.getSubject() == null) {
            return false;
        }

        return orderAccess.canReadOrder(
            jwt.getIssuer().toString(),
            jwt.getSubject(),
            orderId
        );
    }
}
~~~

Per-order permission contract:

~~~java
package com.example.orders.security;

public interface OrderAccessPolicy {

    boolean canReadOrder(
        String issuer,
        String subject,
        String orderId
    );
}
~~~

Implementations of `OrderAccessPolicy` must check owner/tenant/ACL from trusted sources, rather than merely comparing the token subject against a client-sent field.

### 8.3. Using It on a Method

~~~java
package com.example.orders.service;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@orderAuthz.canRead(authentication, #orderId)")
    public OrderDto getOrder(String orderId) {
        return repository.loadWithSecurityConstraints(orderId);
    }
}
~~~

`OrderRepository`, `OrderDto`, and `loadWithSecurityConstraints` are illustrative domain components. `#orderId` is the method parameter name; the project may require `-parameters` compiler metadata or appropriate parameter annotations so SpEL resolves it accurately.

**Advantage:** service-level policies also protect calls coming from multiple controllers. Still, check whether methods are invoked through Spring AOP proxies.

### 8.4. Self-Invocation Trap

With proxy-based method security:

~~~java
public OrderDto internalRead(String orderId) {
    return getOrder(orderId); // May bypass the AOP proxy
}
~~~

If an internal call within the same class skips the proxy, `@PreAuthorize` on the target method may **not execute**. Design proper boundaries, call through managed beans, or place core policies inside unbypassable service/domain code.

### 8.5. `@PostAuthorize` and Side Effects

`@PostAuthorize` checks after the method runs. It can be useful for certain read cases after inspecting the returned object. However, never rely on post-checks as the sole barrier against **money transfers, refunds, record deletions, or sending emails**, because side effects may already have occurred before the policy denies.

For write operations, pre-checks and invariants enforced inside transactions are generally required.

## 9. Custom `AuthorizationManager<MethodInvocation>`

When a more general method-authorization mechanism is needed than calling individual beans via SpEL, you can implement:

~~~java
package com.example.orders.security;

import java.util.function.Supplier;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;

public final class BusinessMethodAuthorizationManager
        implements AuthorizationManager<MethodInvocation> {

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            MethodInvocation invocation) {

        // Illustrative skeleton: inspect method + args,
        // apply authoritative policy, return explicit decision.
        boolean allowed = false;

        return new AuthorizationDecision(allowed);
    }
}
~~~

This is **strictly a skeleton illustrating the interface**, not a usable business implementation: as written, it always denies.

Spring Security provides `AuthorizationManagerBeforeMethodInterceptor` and advisors/pointcuts to attach custom method managers. If replacing default method-security mechanisms, configure interceptors according to your framework version and ensure no policy gaps remain.

For rules tied to one or a few service methods, **`@PreAuthorize` invoking a Java bean** is usually more readable and easier to test than custom infrastructure interceptors.

## 10. Composing Managers Instead of One Large Conditional Function

Spring Security offers combinators:

- `AuthorizationManagers.allOf(...)`: combines conditions with AND logic.
- `AuthorizationManagers.anyOf(...)`: combines branches with OR logic.
- `AuthorizationManagers.not(...)`: negates a decision.

For example, if you have two independent managers—**checking scope** and **checking tenant membership**—you can compose them:

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

AuthorizationManager<RequestAuthorizationContext> scope =
    AuthorityAuthorizationManager.hasAuthority("SCOPE_orders.read");

// tenantOnlyManager is a separate manager checking only membership.
AuthorizationManager<RequestAuthorizationContext> tenant =
    tenantOnlyManager;

AuthorizationManager<RequestAuthorizationContext> combined =
    AuthorizationManagers.allOf(
        new AuthorizationDecision(false),
        scope,
        tenant
    );
~~~

This example uses the overload specifying a **default decision when all managers abstain**, supported in modern Spring Security versions. `tenantOnlyManager` is an application-provided illustrative variable. If using `TenantOrdersReadAuthorizationManager` from Section 5, it **already checks both scope and membership**, so duplication is unnecessary.

### 10.1. Abstain Does Not Automatically Mean Deny

In certain compositions, a manager returning `null` means abstaining. `allOf` and `anyOf` follow specific rules when all managers abstain; never blindly assume the result is deny.

For critical permissions:

1. Prefer explicit `AuthorizationDecision(true/false)` results.
2. Define behavior when no manager renders a decision.
3. Use default deny where the API/version supports it.
4. Test cases where a manager returns null or throws an error.

**Choosing OR can also be a security flaw.** If a policy requires both scope and membership, using `anyOf` allows someone holding only one of them through.

## 11. Not Every Business Policy Must Be a Spring Security Interface

A policy depending on entity state may fit better as a domain service:

~~~java
public interface RefundPolicy {

    boolean canApprove(
        SubjectIdentity actor,
        RefundRequest request,
        Merchant merchant
    );
}
~~~

Used inside a transaction:

~~~java
@Transactional
public RefundReceipt approveRefund(
        String refundId,
        SubjectIdentity actor) {

    RefundRequest refund =
        refundRepository.findForUpdate(refundId);

    Merchant merchant =
        merchantRepository.findById(refund.merchantId());

    if (!refundPolicy.canApprove(actor, refund, merchant)) {
        throw new AccessDeniedException("Not permitted");
    }

    // Verify invariants and update atomically.
    return executeRefund(refund);
}
~~~

`SubjectIdentity`, `RefundRequest`, `Merchant`, `RefundReceipt`, and the repositories are domain examples, not built-in Spring Security APIs. `@Transactional` comes from Spring's transaction support.

Why do this here?

- The freshest entity state can be loaded.
- Checking and writing happen inside the same transaction.
- Domain services are also invoked by message consumers and jobs.
- Avoids duplicating policies across multiple controllers.
- Unit tests stay closer to business requirements.

A custom `AuthorizationManager` can **fail fast** before the controller, yet it does not replace permission checks at the transaction boundary when underlying data fluctuates.

## 12. TOCTOU: Permissions Changing Between Check and Operation

**Time-of-check to time-of-use** is the gap between decision time and execution time.

Example:

~~~text
T0     AuthorizationManager sees order not refunded -> ALLOW
T0+50  Another request successfully refunds the same order
T0+100 Original service proceeds to refund a second time
~~~

For refunds, money transfers, state transitions, or creating unique resources, also enforce:

- State checks inside the transaction.
- Optimistic locking via `@Version` where appropriate.
- Pessimistic locking / row locks if the design requires it.
- Conditional updates constraining status.
- Idempotency keys and unique constraints.
- Approval authority and separation of duties at the domain boundary.

**An `AuthorizationManager` is not a lock or transaction manager.**

## 13. External PDPs and Policy Services

An organization may manage permissions via a database, an entitlement service, or a policy engine like OPA.

~~~text
AuthorizationFilter / Service PEP
             |
             v
Custom AuthorizationManager
             |
             | identity, action, resource, tenant
             v
Policy Decision Point (PDP)
             |
             +-- membership
             +-- ACL / role / policy versions
             +-- resource attributes
             |
             v
ALLOW / DENY / UNAVAILABLE
~~~

Example internal policy request:

~~~json
{
  "subject": {
    "issuer": "https://idp.example.com/realms/shop",
    "id": "user-42"
  },
  "action": "orders.read",
  "resource": {
    "type": "tenant-orders",
    "tenantId": "merchant-a"
  },
  "application": "orders-api"
}
~~~

`subject` data must originate from the verified `Authentication`, never from a self-declared client body or header.

### 13.1. Trust Boundary with the PDP

A trustworthy PDP setup requires:

- A server-managed endpoint, never letting clients choose an arbitrary URL.
- TLS/mTLS or a protected authenticated channel by design.
- Scoped permissions for calling the PDP and accessing tenant data.
- Decisions bound to the **exact subject, action, resource, tenant, and policy version**.
- Responses parsed against a strict schema; unknown fields or errors never default to allow.
- Auditing and policies for handling stale permissions.

### 13.2. Policy Service Timeout: Never Fail Open

If the PDP or database is unavailable, **do not return ALLOW** just to keep API latency down. Reject the request or return an availability error such as 503 by design, ensuring business operations never execute without verified authorization.

**Failing closed** does not force every infrastructure failure to return 403. Distinguish business denials from policy-service outages in telemetry, without leaking sensitive details to clients.

### 13.3. Caching Authorization Decisions

Caching can improve latency but must include full context in the key:

~~~text
issuer + subject + action + resource + tenant + policyVersion
~~~

Never cache an allow keyed solely by `sub` and reuse it across tenants. Configure TTLs, invalidation on membership/role changes, revocation policies, per-tenant cache isolation, and limits on stale decisions. For sensitive or immediately revocable privileges, long-lived allow caches may be inappropriate.

## 14. RBAC, ABAC, and ReBAC

Many systems combine models:

| Model | Focus | Example |
|---|---|---|
| **RBAC** | Assigned roles | `ROLE_ORDERS_OPERATOR` |
| **OAuth scope** | API-level operation permissions | `SCOPE_orders.read` |
| **ABAC** | Subject/resource/context attributes | Merchant, order type, limit |
| **ReBAC** | Subject–resource relationships | User belongs to the team owning the order |
| **Policy-based** | Combining multiple conditions | Scope AND membership AND state |

For example, a valid refund approval requires:

~~~text
valid access token for refunds-api
AND SCOPE_refunds.approve
AND actor belongs to matching merchant
AND refund amount <= remaining limit
AND payment is settled
AND payment not yet refunded
AND actor != request creator (if policy requires)
~~~

Never infer `ROLE_ADMIN` from an arbitrary email, username, or group. Role/entitlement sources must be organization-controlled, tied to the right issuer and right application.

## 15. Multi-Issuer, Multi-Tenant, and BOLA

Two different issuers can both produce `sub=user-42`:

~~~text
(https://idp-a.example.com, user-42)
(https://idp-b.example.com, user-42)
~~~

These are **not implicitly the same identity**. If membership is queried by `sub` alone, the Resource Server can confuse principals across issuers.

A token carrying `tenant_id=tenant-a` also does not implicitly prove the principal has admin access to tenant A. A tenant claim may indicate context; explicit contracts and object/relationship policies are still required.

A request like:

~~~text
GET /api/tenants/tenant-a/orders/order-from-tenant-b
~~~

might pass HTTP tenant-A membership checks, yet the service must still verify which tenant the order belongs to. Adding a tenant predicate directly inside queries reduces **Broken Object Level Authorization (BOLA/IDOR)** risk.

## 16. Anti-Patterns to Avoid

### 16.1. Trusting Roles in the Request

~~~java
// WRONG: client controls the X-Role header.
if ("ADMIN".equals(request.getHeader("X-Role"))) {
    return new AuthorizationDecision(true);
}
~~~

### 16.2. Treating Target Tenant as Proof of Permission

~~~java
// WRONG: any non-null tenantId is allowed.
String tenantId = request.getParameter("tenantId");
return new AuthorizationDecision(tenantId != null);
~~~

### 16.3. Adding Extra Permissions to "Fix" 403s

~~~java
// WRONG: a token with only read scope must not be granted write.
if (hasReadScope) {
    authorities.add(new SimpleGrantedAuthority("SCOPE_orders.write"));
}
~~~

### 16.4. Placing the Manager Only on the Controller

If a service is called from a scheduler or queue consumer, those paths can bypass the policy. Extract policies into shared services and define authentication for those workloads/entry points.

### 16.5. Placing Broad Matchers Before Business Matchers

~~~java
// WRONG: broad matcher shadows the custom access rule.
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/tenants/{tenantId}/orders/**")
    .access(tenantOrdersRead)
~~~

### 16.6. Post-Authorization on Side-Effecting Actions

A database write performed before a post-check cannot always be rolled back. Use pre-checks and enforce invariants inside transactions.

### 16.7. Allowing When the Policy Source Fails

A null result, timeout, or exception from a policy service must never default to allow.

## 17. 401, 403, and Policy Infrastructure Errors

| Scenario | Typical Outcome | Cause |
|---|---|---|
| No bearer token sent to private endpoint | 401 | Missing authentication |
| JWT invalid signature/issuer/audience/expiration | 401 | Authentication failure |
| Valid JWT missing `SCOPE_orders.read` | 403 | Authorization denial |
| Has scope but not member of tenant | 403 or 404 per API policy | Business authorization |
| User in tenant A, order in tenant B | 403/404 | Object-level denial |
| Policy service timeout | 5xx/503 or deny by design | Policy infrastructure unavailable |
| Unable to extract tenant ID | Deny | Missing policy context |
| Valid JWT, scope, and membership all pass | Enters handler | Must still check entity |

A custom `AuthorizationManager` normally **returns an `AuthorizationResult`**, rather than writing an HTTP response directly. Spring Security enforcement and exception handling determine the resulting response.

RFC 6750 defines Bearer challenges with `invalid_token` or `insufficient_scope`. Never include real JWTs or sensitive internal entitlements in error responses.

## 18. Unit Testing a Custom Manager

`TenantOrdersReadAuthorizationManager` can be tested with a mock `JwtAuthenticationToken` and `RequestAuthorizationContext`.

~~~java
package com.example.orders.security;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class TenantOrdersReadAuthorizationManagerTest {

    static JwtAuthenticationToken userWithReadScope() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only")
            .header("alg", "RS256")
            .claim("iss", "https://idp.example.com/realms/shop")
            .claim("sub", "user-42")
            .build();

        return new JwtAuthenticationToken(
            jwt,
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
        );
    }

    static RequestAuthorizationContext forTenant(String tenantId) {
        MockHttpServletRequest request =
            new MockHttpServletRequest(
                "GET", "/api/tenants/" + tenantId + "/orders"
            );

        return new RequestAuthorizationContext(
            request, Map.of("tenantId", tenantId)
        );
    }

    @Test
    void grantsOnlyWhenMembershipExists() {
        TenantMembershipPolicy policy =
            mock(TenantMembershipPolicy.class);

        when(policy.canReadOrders(
            "https://idp.example.com/realms/shop",
            "user-42",
            "tenant-a"
        )).thenReturn(true);

        var manager = new TenantOrdersReadAuthorizationManager(policy);

        AuthorizationResult decision = manager.authorize(
            () -> userWithReadScope(),
            forTenant("tenant-a")
        );

        assertTrue(decision.isGranted());
    }

    @Test
    void deniesWhenTenantMembershipMissing() {
        TenantMembershipPolicy policy =
            mock(TenantMembershipPolicy.class);

        var manager = new TenantOrdersReadAuthorizationManager(policy);

        AuthorizationResult decision = manager.authorize(
            () -> userWithReadScope(),
            forTenant("tenant-b")
        );

        assertFalse(decision.isGranted());
    }

    @Test
    void deniesWhenScopeMissing() {
        TenantMembershipPolicy policy =
            mock(TenantMembershipPolicy.class);

        var manager = new TenantOrdersReadAuthorizationManager(policy);
        var withScope = userWithReadScope();

        var withoutScope = new JwtAuthenticationToken(
            withScope.getToken(), List.of()
        );

        AuthorizationResult decision = manager.authorize(
            () -> withoutScope,
            forTenant("tenant-a")
        );

        assertFalse(decision.isGranted());
    }
}
~~~

This is a **policy unit test**, not a JWT signature test: `Jwt.withTokenValue` builds a mock object and does not prove issuer, audience, or signature verification.

### 18.1. Scenarios to Test

| Scenario | Expected |
|---|---|
| Missing/anonymous Authentication | Deny |
| Valid JWT without scope | Deny |
| Has scope without membership | Deny |
| Blank tenant ID / not extracted by matcher | Deny |
| Missing required subject or issuer | Deny |
| Two issuers sharing the same subject | No membership confusion |
| PDP timeout | Never allow |
| Order ID in another tenant | Deny in service |
| Recently revoked role | Follows revocation/cache policy |
| Read scope calling write endpoint | Deny |
| Manager returning null in composition | Never accidentally grants |

With `MockMvc`, the `jwt()` utility helps verify HTTP rules/wiring, though it can skip signature validation and production converters. Add integration tests with JWTs signed by test keys to prove the full authentication path.

### 18.2. Testing Method-Security Proxies

When using `@PreAuthorize`, test through the Spring-managed bean/proxy rather than calling a newly instantiated object directly and assuming advice applied. Key tests include:

- Normal method call from a controller.
- Method called from another service.
- Self-invocation passing or bypassing the proxy.
- Business invariants still denying when HTTP pre-checks are not invoked.
- Concurrency/state transitions within transactions for side-effecting operations.

## 19. Auditing, Latency, and Sensitive Data

When access is denied, logs can record:

~~~text
event=authorization_decision
decision=DENY
policy=tenant-orders-read
subjectRef=<internal-principal-reference>
tenantRef=tenant-b
reason=membership_not_found
traceId=7af3...
bearerToken=[REDACTED]
~~~

Never log raw `Authorization` headers, access tokens, refresh tokens, or secrets. Apply data-protection policies to subject/tenant/resource IDs.

Separate metrics into:

- **Authentication failures:** signature, issuer, audience, expiration.
- **Authorization denials:** missing scope, absent membership, wrong owner, wrong state.
- **Policy infrastructure failures:** database timeout, PDP unavailable, cache issues.

A policy evaluated on every request can increase latency. Measure response times, cache hit rates, and policy error rates, without ever trading security for a fallback allow when a service slows down.

## 20. When to Use `PermissionEvaluator`, `@PreAuthorize`, or a Custom Manager?

| Option | When Appropriate | Things to Watch |
|---|---|---|
| `hasAuthority` / `hasRole` | Simple scopes or roles | Does not replace ownership |
| Custom HTTP `AuthorizationManager<RequestAuthorizationContext>` | Checks based on request, path, principal, and policy source | Matcher order, lacks entity state |
| `@PreAuthorize` + policy bean | Permissions tied to service methods/arguments | Spring AOP proxies, parameter names |
| `PermissionEvaluator` / `hasPermission` | Applications with an existing object-permission model | ACL source, performance |
| Custom `AuthorizationManager<MethodInvocation>` | Specialized method-security infrastructure integration | Advisors/pointcuts, version specifics |
| Business service guard inside transaction | State-dependent / side-effecting operations | Atomicity, concurrency, shared entry points |
| External PDP | Centralized permissions across many services | Availability, trust, caching, latency |

You do not need a custom manager just to express a single-scope condition. The best mechanism is the one that makes it **easy to prove unauthorized actions cannot get through**.

## 21. Misconceptions to Avoid

**"AuthorizationManager is used to decode and verify JWTs."** No. That is the responsibility of Resource Server authentication/`JwtDecoder`.

**"A token with the read scope can read every record."** No. Tenant/ownership/ACL policies may restrict access.

**"The `tenantId` path variable proves membership."** No. It only identifies the target resource.

**"One HTTP manager covers message consumers and schedulers too."** Not if those entry points bypass the HTTP chain. Business policies must be enforced at shared boundaries.

**"`@PreAuthorize` always runs when a method is called from the same class."** Not guaranteed in proxy-based security.

**"`@PostAuthorize` is enough to protect refunds."** Not once side effects have already occurred.

**"If the policy DB fails, let requests pass to preserve SLA."** Wrong for any mandatory security rule.

**"Caching a user's allow works across all tenants."** Wrong; decisions must be keyed by resource/action/tenant/version.

**"`allOf` and `anyOf` are safe if a manager returns null."** Not by default; verify abstain/default behavior explicitly.

**"Seeing a 403 means we should add permissions in the JWT converter."** No. Verify whether the authority was legitimately granted by an authoritative source.

## 22. Self-Check Questions

**Question 1.** When is `hasAuthority("SCOPE_orders.read")` insufficient?

> Whenever tenant, owner, ACL, entity state, or business policy conditions apply that are not represented by the scope alone.

**Question 2.** What does `AuthorizationManager<RequestAuthorizationContext>` receive?

> A `Supplier<Authentication>` and a context containing the HTTP request plus path variables extracted by the matcher.

**Question 3.** In modern Spring Security, which method should be implemented?

> `authorize(...)` returning `AuthorizationResult`; `check(...)` is deprecated in newer versions.

**Question 4.** Why should you never trust a client-supplied `tenantId`?

> Clients can freely alter the target tenant; access must be verified against an authoritative membership source.

**Question 5.** Given an HTTP membership manager, why must the service still filter by tenant?

> Because an order ID might belong to another tenant. Without tenant-constrained queries, BOLA/IDOR can still occur.

**Question 6.** Where should a refund-state-dependent policy be checked?

> In the service/domain transaction, with proper concurrency/atomicity. An HTTP manager can fail fast, but does not replace transaction checks.

**Question 7.** Does returning `null` in a custom manager definitely mean deny?

> No. It can mean abstain; understand the composition logic and test default decisions.

**Question 8.** Should a PDP timeout ever allow access?

> No. Fail closed or return an unavailable error without executing unauthorized business logic.

**Question 9.** Does MockMvc `jwt()` verify production token signatures?

> No. It simulates authentication; integration tests with a real decoder and signed test tokens are required.

**Question 10.** When is `@PreAuthorize` invoking a policy bean preferable to a custom method interceptor?

> When permissions belong to specific methods, where Java policies are easier to read and test; custom interceptors fit shared cross-cutting method-security infrastructure rules.

## 23. References

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, `AuthorizationResult`, and the authorization model.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `access(...)`, and custom authorization.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, policy beans, and custom method authorization.
- [Spring Security — AuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize` and `verify`.
- [Spring Security — AuthorizationResult API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationResult.html): authorization decision results.
- [Spring Security — RequestAuthorizationContext API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/intercept/RequestAuthorizationContext.html): requests and path variables.
- [Spring Security — AuthorizationManagers API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagers.html): `allOf`, `anyOf`, `not`, and abstain behavior.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWTs and scope mapping.
- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): MockMvc JWT authentication tests.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer semantics and errors.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): issuer and subject claims.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access tokens, audience, and scopes.

**Conclusion:** a custom `AuthorizationManager` or business policy component should accept the **authenticated principal**, action, and target resource, query a **trusted permission source**, and return an explicit allow/deny decision. For mutable tenant, ownership, and state rules, business protection must also live at the **service/transaction boundary**, not just HTTP. Choose the right check points, avoid granting extra permissions yourself, and fail closed whenever access cannot be proven.
