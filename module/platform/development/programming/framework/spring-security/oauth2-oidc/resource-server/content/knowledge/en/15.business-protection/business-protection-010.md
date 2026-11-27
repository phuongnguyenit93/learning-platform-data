# Decoupling Business Policies from Issuer-Specific Claim Names

## 1. The Problem: Same Business Permission, Many Access Token Representations

A **Spring Security OAuth 2.0 Resource Server** receives access tokens from an **Authorization Server (AS)**. A token may carry scopes, roles, groups, or issuer-defined claims. However, **claim names and JSON structures are not the application's business permission model**.

Suppose an order-management API requires:

> A principal may view orders when holding read permission; and modify an order when holding edit permission **and** currently holding rights to that specific order.

Different issuers can express these permissions in various formats.

**Issuer A** uses a nested resource claim, often seen in systems with resource roles:

~~~json
{
  "iss": "https://login-a.example.com/realms/shop",
  "sub": "u-101",
  "aud": ["orders-api"],
  "resource_access": {
    "orders-api": {
      "roles": ["order-reader", "order-editor"]
    }
  },
  "exp": 1910003600
}
~~~

**Issuer B** provides an array-based `permissions` claim:

~~~json
{
  "iss": "https://login-b.example.com/",
  "sub": "person-918",
  "aud": ["orders-api"],
  "permissions": ["read:orders", "update:orders"],
  "exp": 1910003600
}
~~~

**Issuer C** uses a scope string:

~~~json
{
  "iss": "https://login-c.example.com/tenant-1",
  "sub": "user-222",
  "aud": ["orders-api"],
  "scp": "Orders.Read Orders.Update",
  "exp": 1910003600
}
~~~

These are **illustrative custom contract examples**, not a guarantee that every product or issuer version emits identical claims. In practice, each issuer, client, resource, and token profile can differ.

If a business service writes directly:

~~~java
if (jwt.getClaimAsMap("resource_access")
        .containsKey("orders-api")) {
    // Allow editing orders?
}
~~~

the service becomes tightly coupled to Issuer A's schema. Switching issuers, onboarding a tenant, or changing permission configuration at the AS forces edits inside business logic. Worse, that condition only checks **that a resource entry exists** without proving the edit role was granted.

**Goal of this lesson:** build a **translation boundary** from verified claims into an **application-defined canonical model of principals, permissions, and context**. Stable business rules such as **ORDER_READ**, **ORDER_EDIT**, and **ORDER_APPROVE** should never depend on whether an issuer calls them **role**, **scope**, **permissions**, **groups**, or some custom JSON claim.

## 2. Differences Between Claims, Authorities, and Business Permissions

Four concepts are frequently conflated:

| Concept | Example | Whose Responsibility? |
|---|---|---|
| **JWT claim** | `resource_access`, `permissions`, `scp`, `roles`, `tid` | Token issuer and token profile |
| **OAuth scope** | `orders.read`, `read:orders` | Scope of access granted by the AS to the access token |
| **Spring GrantedAuthority** | `SCOPE_orders.read`, `PERM_ORDER_EDIT` | How Spring Security represents authorities for an authenticated request |
| **Domain permission/policy** | `EDIT_ORDER` on order 42 in `tenant-blue` | Business application, trusted policy/permission source |
| **Principal identity** | `(iss, sub)`, local account ID, service principal | Authentication boundary and internal identity directory |

A claim is not automatically a permission. For instance:

- **groups** may be a group membership list, not permitted business actions.
- **roles** may be client-level, realm-level, or application-level roles with different semantics.
- **scp** may represent delegated scopes, while an app-only token carries a different claim.
- **permissions** may represent entitlements yet still depend on **audience** and token profile.
- **tenant_id** describes tenant context; it does not automatically permit reading every record in the tenant.
- **sub** identifies a subject per issuer; it is not a role or a global account ID.

An API should define core concepts in **its own business language**, for example:

~~~text
Domain permissions:
  ORDER_READ
  ORDER_EDIT
  ORDER_APPROVE
  ORDER_CANCEL

Actions:
  VIEW_ORDER
  MODIFY_ORDER
  APPROVE_ORDER
  CANCEL_ORDER

Context:
  issuer, external subject, local actor, tenant, resource state
~~~

These names need clear semantics: **ORDER_EDIT** might allow editing a draft order in a tenant where the actor holds valid membership, while disallowing edits to approved orders. When swapping Identity Providers, domain semantics **do not change**.

## 3. Two Boundary Layers: Token Acceptance and Domain Authorization

You cannot safely decouple claim names from business logic if the Resource Server accepts the wrong token up front.

~~~text
HTTP Authorization: Bearer <access-token>
            |
            v
[1] Authentication boundary
    - Verify JWT signature or introspection
    - Issuer matches trust domain
    - Audience/resource matches API
    - Token is unexpired
    - Token matches purpose/profile
            |
            v
[2] Issuer-specific adapter
    - Read verified claims per contract
    - Map external roles/scopes -> canonical permissions
    - Map (iss, sub) -> actor identity
    - Missing/conflicting claims: deny, never guess
            |
            v
[3] Application authorization
    - Check canonical permissions
    - Check tenant, owner, resource state
    - Check live permissions on demand
            |
            v
[4] Domain operation
    - Read/edit/approve order inside transaction
~~~

**Never grant permissions merely because a JWT payload contains a role-like string.** Base64URL-decoded JWTs are readable before signatures are verified. Converting claims into authorities must happen **only after `JwtDecoder` and validators accept the token**, or from an introspection response verified per the AS contract.

Separate responsibilities:

- **Authentication** confirms the token is trusted and bound to the right issuer, audience, and profile.
- **Claim adapter / authority converter** turns verified representations into canonical names.
- **Authorization policy** decides whether an actor may perform an action on a specific resource.
- **Business service** executes the action and protects data consistency.

## 4. What Problems Does Direct Claim Coupling Cause?

### 4.1. Vendor Lock-In Inside Services

Example code reading schema directly:

~~~java
// DO NOT couple business code to this structure.
Map<String, Object> realmAccess =
        jwt.getClaimAsMap("realm_access");
~~~

When the application migrates from a realm-based issuer to one issuing a scope string, order-processing methods break even though the rule "only someone authorized to edit orders may edit" **never changed**.

### 4.2. Same Role Name, Different Meaning

Two issuers both define role **admin**:

~~~text
Issuer A: admin = manage login configuration
Issuer B: admin = administer orders
~~~

If a converter does:

~~~text
"admin" -> ROLE_ADMIN -> full access across all APIs
~~~

it can introduce **privilege escalation** because matching role names do not mean equivalent business authority. Always map by **issuer + token type + audience/resource + role name**, under a contract confirmed by responsible owners.

### 4.3. Claims Intended for Another Resource Interpreted as Current API Permissions

A JWT may contain:

~~~json
{
  "resource_access": {
    "billing-api": {
      "roles": ["billing-admin"]
    },
    "orders-api": {
      "roles": ["order-reader"]
    }
  }
}
~~~

If an application collects all nested roles and elevates to **ADMIN**, a billing admin role is misapplied inside the orders API. The adapter must read **only the section meant for `orders-api`**, and the JWT must also carry the corresponding audience per the access-token contract.

### 4.4. Difficulty Changing Authorization Policies

If endpoints reference an issuer-specific string:

~~~java
.hasAuthority("SCOPE_https://provider.example/scopes/editOrder")
~~~

HTTP logic becomes tied to how the issuer names scopes. Changing issuers or scope URIs forces edits across controllers, annotations, and tests.

Keep internal names durable:

~~~java
.hasAuthority("PERM_ORDER_EDIT")
~~~

and update the mapping inside **the issuer's adapter** without changing domain semantics.

### 4.5. Failing to Distinguish Identity, Token Grant, and Object Ownership

An access token carrying role **order-editor** does not prove the actor may edit **order 42**. That actor might:

- No longer hold membership in the order's tenant.
- Be restricted to editing orders in their own department.
- Hold a token issued before the role was revoked.
- Be allowed to edit only `DRAFT` orders, not `APPROVED` ones.
- Be using a client-credentials token not permitted for user-delegated actions.

**Canonical permission is a necessary condition, not the final decision** when the domain enforces object-level permissions.

## 5. Issuer Vocabulary and Domain Vocabulary Should Be Managed Separately

Example of a deliberately designed mapping table:

| Issuer / Token Profile | External Claim | Issuer Value | Internal Permission |
|---|---|---|---|
| Realm issuer A, audience `orders-api` | `resource_access.orders-api.roles` | `order-reader` | `PERM_ORDER_READ` |
| Realm issuer A, audience `orders-api` | `resource_access.orders-api.roles` | `order-editor` | `PERM_ORDER_EDIT` |
| Issuer B, audience `orders-api` | `permissions` | `read:orders` | `PERM_ORDER_READ` |
| Issuer B, audience `orders-api` | `permissions` | `update:orders` | `PERM_ORDER_EDIT` |
| Issuer C, audience `orders-api` | `scp` | `Orders.Read` | `PERM_ORDER_READ` |
| Issuer C, audience `orders-api` | `scp` | `Orders.Update` | `PERM_ORDER_EDIT` |

**These mappings are illustrative contracts only.** They cannot be inferred automatically from role or scope names; the API-owning team must confirm actual semantics.

Principles:

1. **Allow-list mapping**—never automatically turn every role into an application permission.
2. Every mapping has an **explicit issuer/profile source**.
3. Minimum OAuth scopes may be required **alongside** roles when grants and business permissions are distinct conditions.
4. Never grant permissions for unknown claims or unknown values.
5. Define the outcome of missing, null, wrong-type, or conflicting claims.
6. Track mapping versions when an issuer changes its contract.
7. Prevent an issuer from granting privileges beyond the scope delegated to that issuer.

An **unknown** role must never slip through via a rule like:

~~~text
externalRole.toUpperCase() -> PERM_ + role
~~~

That lets any new value added by an issuer turn into an unintended internal permission.

## 6. Different Issuers Express Roles and Scopes Differently

The examples below illustrate the variety of representations, **not a guaranteed default schema across all products**.

| Ecosystem | Claims You May Encounter | Points to Control |
|---|---|---|
| Keycloak | `realm_access.roles`; `resource_access.[client].roles` | Realm roles and client/resource roles differ; never merge arbitrarily |
| Microsoft Entra ID | `scp`, `roles`, `groups`, `tid`, `oid` | Delegated scopes and app roles have distinct semantics; group overage may omit full group lists from the JWT |
| Auth0 | `scope`, `permissions`, or custom namespaced claims | `permissions` claim depends on RBAC/API configuration and token audience |
| Amazon Cognito | `scope`, `cognito:groups`, `client_id`, `token_use` | Resource Server must distinguish access tokens from ID tokens; groups do not automatically mean app permissions |
| Internal provider | `entitlements`, `grants`, `authorities`, `roles`, `resource_permissions` | Requires an independent contract and versioning |

For example, the absence of **groups** in a JWT does not always mean the user **belongs to no groups**. Some providers supply group memberships via another endpoint or emit an overage claim. If policies rely on groups, the adapter must distinguish **omitted due to token size limits** from **genuinely lacking permission**.

Similarly, **roles** in a machine-to-machine token may represent app roles; they do not prove an end user is present. Always distinguish **principal type** before applying business policies.

## 7. Designing a Stable Internal Permission Model

Instead of letting domain services reference issuer roles, define a dedicated vocabulary:

~~~java
public enum BusinessPermission {
    ORDER_READ,
    ORDER_EDIT,
    ORDER_APPROVE,
    ORDER_CANCEL
}
~~~

When Spring Security needs string authorities, define a naming convention:

~~~text
BusinessPermission.ORDER_READ    -> PERM_ORDER_READ
BusinessPermission.ORDER_EDIT    -> PERM_ORDER_EDIT
BusinessPermission.ORDER_APPROVE -> PERM_ORDER_APPROVE
BusinessPermission.ORDER_CANCEL  -> PERM_ORDER_CANCEL
~~~

Modeling principles:

- **Permission names should describe business actions**, not which IdP issued a role.
- Never treat **ORDER_EDIT** as proof that every order can be edited; domain resource checks may still be needed.
- Avoid using a coarse **ADMIN** role as a global privilege when the domain spans multiple subsystems.
- Specify which roles/permissions apply to user tokens, service tokens, or both.
- Control permission names and mapping versions in reviewed code/config.
- Consider separating **coarse-grained** permissions (API route/action) from **fine-grained** permissions (object, tenant, state).

### Permissions vs. Capabilities

A **permission** is usually a stable domain capability name, such as **ORDER_APPROVE**. A specific **capability** may be bound to an order ID, time window, tenant, or workflow state.

Example:

~~~text
Principal has ORDER_APPROVE:
  Eligible initially to be evaluated for approval.

Yet order 42:
  status = CANCELLED
  => policy disallows approval.
~~~

Never encode every variation of resource state into JWT roles just to simplify an expression. Doing so bloats tokens, goes stale quickly, and creates concurrency hazards.

## 8. The Translation Layer Is an Anti-Corruption Layer

In domain-driven design, an **anti-corruption layer** prevents external models from leaking into the internal domain model.

For a Resource Server:

~~~text
Issuer-specific token claims
   resource_access / permissions / scp / groups
                       |
                       v
        Trusted token adapter
        - schema validation
        - issuer-specific mapping
        - role/scope allow-list
        - principal kind
                       |
                       v
       Canonical authorization model
       - BusinessPermission
       - ExternalPrincipalKey
       - ApplicationActor
                       |
                       v
             Domain policies
       canReadOrder(actor, order)
       canEditOrder(actor, order)
       canApproveOrder(actor, order)
~~~

Provider changes should be absorbed inside the **adapter**, never spreading into repositories, order services, or business rules.

### What the Adapter Must Know

- Which issuers the Resource Server trusts.
- Whether the token is the right **access token** type and matches the right resource/audience.
- Which claim paths and data types the contract specifies.
- Which external roles/scopes map to which internal permissions.
- Whether roles are scoped to a user, client, tenant, or resource.
- Whether missing/unknown claims should deny or trigger introspection/external lookup.
- Whether provenance (issuer, client, grant) must be preserved for policies.

### What Domain Policies Must Never Know

A domain policy should say:

~~~text
canEditOrder(actor, order)
~~~

not:

~~~text
if provider is Keycloak and resource_access.orders-api.roles
   contains order-editor ...
~~~

It may need to understand **local tenants**, **order ownership**, and **canonical permissions**, but never how a provider names JSON fields.

## 9. Concrete Example: Translating Client Roles into Canonical Authorities

Suppose there is a single trusted issuer:

~~~text
https://login-a.example.com/realms/shop
~~~

and an access token for **orders-api** contains:

~~~json
{
  "iss": "https://login-a.example.com/realms/shop",
  "sub": "user-101",
  "aud": ["orders-api"],
  "resource_access": {
    "orders-api": {
      "roles": ["order-reader", "order-editor"]
    }
  }
}
~~~

We can build a **`Converter<Jwt, Collection<GrantedAuthority>>`** that reads only the resource roles intended for **orders-api**. The converter runs **after** `JwtDecoder` verifies the token.

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

public final class OrdersPermissionsConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final String API_RESOURCE = "orders-api";

    private static final Map<String, String> ALLOWED_ROLE_MAPPING =
            Map.of(
                    "order-reader", "PERM_ORDER_READ",
                    "order-editor", "PERM_ORDER_EDIT",
                    "order-approver", "PERM_ORDER_APPROVE"
            );

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Map<String, Object> resourceAccess =
                jwt.getClaimAsMap("resource_access");

        if (resourceAccess == null) {
            return Set.of(); // Never grant permissions when claim is missing.
        }

        Object resourceObject = resourceAccess.get(API_RESOURCE);
        if (!(resourceObject instanceof Map<?, ?> resource)) {
            return Set.of();
        }

        Object rolesObject = resource.get("roles");
        if (!(rolesObject instanceof Collection<?> roles)) {
            return Set.of();
        }

        Set<GrantedAuthority> granted = new LinkedHashSet<>();

        for (Object item : roles) {
            if (!(item instanceof String role)) {
                continue;
            }

            String mappedAuthority = ALLOWED_ROLE_MAPPING.get(role);
            if (mappedAuthority != null) {
                granted.add(
                        new SimpleGrantedAuthority(mappedAuthority));
            }
        }

        return Set.copyOf(granted);
    }
}
~~~

Security properties:

1. Claims are read from a **decoder-verified `Jwt`**.
2. The converter inspects only **`resource_access.orders-api.roles`**, ignoring roles for other resources.
3. Only **allow-listed** values become authorities.
4. Missing claims, wrong types, or unrecognized roles **receive no corresponding authority**.
5. The converter never infers **ROLE_ADMIN** or **PERM_ORDER_APPROVE** from a similarly named role.
6. It does not query live permissions; if privileges can be revoked after token issuance, domain policies must still verify freshness as required.

**Limitation of this example:** issuer, audience, and token purpose must be validated before using the converter. Some issuers do not emit nested claims like this; build adapters matching the provider contract rather than forcing other tokens into this schema.

### Registering the Converter in Spring Security Resource Server

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationConverter;

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(
            new OrdersPermissionsConverter());

    converter.setPrincipalClaimName("sub");

    return converter;
}
~~~

Then wire it into the security chain:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt.jwtAuthenticationConverter(
                jwtAuthenticationConverter())))
~~~

The converter builds a **`JwtAuthenticationToken`** with canonical authorities. At the HTTP layer:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("PERM_ORDER_READ")
.requestMatchers(HttpMethod.PATCH, "/api/orders/**")
    .hasAuthority("PERM_ORDER_EDIT")
~~~

The domain does not need to know the original roles were named **order-reader** or **order-editor**. If the issuer renames them to **orders.viewer** and **orders.editor**, only the adapter updates its mapping after reviewing semantics.

### Do Not Accidentally Lose Required Scopes

In this example, calling **`setJwtGrantedAuthoritiesConverter`** replaces the default converter with a custom one. As a result, **`SCOPE_...`** authorities from default scope extraction will no longer appear in `Authentication` unless your custom converter preserves them.

If policies require **both OAuth scopes and business permissions**, explicitly combine both verified sources and enforce AND per contract. Never assume installing a custom converter keeps all default scope authorities automatically.

## 10. Token Validation Must Not Be Skipped Just Because a Converter Exists

A forged token can easily declare:

~~~json
{
  "iss": "https://login-a.example.com/realms/shop",
  "aud": ["orders-api"],
  "resource_access": {
    "orders-api": {
      "roles": ["order-editor"]
    }
  }
}
~~~

If the Resource Server trusts claims without verifying the JWT, an attacker can grant themselves any role. The converter is only safe after the JWT passes through a trusted **decoder and validators**.

Example decoder configuration for a specific issuer with audience **orders-api**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class TokenValidationConfig {

    private static final String ISSUER =
            "https://login-a.example.com/realms/shop";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> apiAudience = jwt ->
                jwt.getAudience().contains("orders-api")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Access token is not for orders-api",
                                    null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, apiAudience));
        return decoder;
    }
}
~~~

This setup focuses on **issuer and audience**; the Resource Server must also verify **token purpose/profile**, trusted JWS algorithms, and other contract constraints. If the provider emits RFC 9068 JWT access tokens, enforce profile rules (such as **`typ=at+jwt`**) appropriately. If a provider uses **`token_use=access`** or a custom profile, never assume those fields exist across all issuers.

**Note:** calling **`setJwtValidator(...)`** replaces the decoder's existing validators. Retain required default validators for issuer, timestamps, and custom rules. An audience validator does not check signatures on its own.

### Why Checking Only Issuer Is Still Insufficient

One issuer can mint:

- An **ID token** for a web client, with **`aud=web-client`**.
- An **Access token** for `orders-api`, with **`aud=orders-api`**.
- An Access token for `billing-api` carrying invoice privileges.

All three tokens may share the same issuer or JWKS, yet **do not share the same purpose**. Even if a converter could read a `roles` claim from an ID token, the API must never accept that token as a bearer access token simply because the claim name matches.

## 11. From Token Adapter to Local Actor

Do not pass **`Jwt`** objects throughout every domain service and read claims everywhere. Map external identities into a system-defined **`ApplicationActor`**.

Conceptual model:

~~~java
public record ExternalPrincipalKey(
        String issuer,
        String subject) {
}

public enum PrincipalKind {
    USER,
    SERVICE
}

public record ApplicationActor(
        java.util.UUID localId,
        PrincipalKind kind,
        java.util.Set<BusinessPermission> permissions) {
}
~~~

Explanation:

- **`(issuer, subject)`** preserves the AS/OP's identity scope; **`sub`** alone is not unique across multiple issuers.
- **`localId`** is the internal identifier, independent of how any provider formats **`sub`**.
- **`kind`** distinguishes users from service/client principals. Never assume every token represents a human user.
- **`permissions`** uses domain vocabulary; they can come from verified grants, a permission store, or a controlled combination of policies.

Mapping pipeline:

~~~text
Verified JWT / trusted introspection
         |
         v
Issuer-specific claim adapter
         |
         v
ExternalPrincipalKey(iss, sub)
         |
         v
IdentityDirectory:
  (issuer, subject) -> local account/service
         |
         v
ApplicationActor(localId, kind, permissions)
         |
         v
Domain policy:
  mayEditOrder(actor, order)
~~~

With multiple issuers, the **`(iss, sub)`** pair prevents identity collisions:

~~~text
Issuer A, sub=123 -> local account Alice
Issuer B, sub=123 -> local account Bob

If looking up users by sub=123 alone:
  may grant permissions and data to the wrong person.
~~~

**Never automatically link accounts by email or username** across issuers. Account linking requires dedicated workflows and trustworthy proof.

### 11.1. Local Identity Mapping Is Not Permission Mapping

Two independent steps:

1. **Identity mapping:** which local actor does this authenticated token represent?
2. **Permission mapping:** which rights do verified external claims/entitlements and internal policies grant that actor?

Having an identity mapping alone does not mean the actor can perform all actions. Conversely, a valid-looking role claim is not enough to bypass a disabled local account status.

### 11.2. OIDC Pairwise Subjects

OIDC can issue distinct **pairwise subject identifiers** for the same person across different sectors. Thus one person can hold multiple valid **`sub`** values at the same OP depending on client context.

Local `ApplicationActor` mapping can support explicit identity linking, yet **never infer** that two pairwise subjects belong to the same person via email or display name. Respect the OP's privacy boundaries.

## 12. Domain Policies Need No Knowledge of Claim Paths

An order may be edited when all of the following hold:

~~~text
Principal is authenticated
AND holds PERM_ORDER_EDIT
AND local account is active
AND actor holds active membership in order's tenant
AND order is in an editable status
AND actor is not blocked by conflict-of-interest policy
~~~

The policy layer should expose a domain-oriented interface:

~~~java
public interface OrderAuthorizationPolicy {
    boolean mayEditOrder(ApplicationActor actor, Order order);
    boolean mayApproveOrder(ApplicationActor actor, Order order);
}
~~~

Conceptual implementation:

~~~java
public boolean mayEditOrder(ApplicationActor actor, Order order) {
    return actor.permissions().contains(
                    BusinessPermission.ORDER_EDIT)
            && membershipStore.hasActiveMembership(
                    actor.localId(), order.tenantId())
            && order.status() == OrderStatus.DRAFT
            && !order.isLocked();
}
~~~

**`MembershipStore`**, **`Order`**, and **`OrderStatus`** are hypothetical domain types to be defined in a real project. The point is that resource permissions must rely on **business vocabulary and live state**, never on an issuer's claim names.

Avoid code like:

~~~java
if ("login-a.example.com".equals(provider)
        && jwt.getClaimAsMap("resource_access") != null) {
    return true;
}
~~~

inside domain policies. Both mistakes appear here: provider coupling and overly broad authorization.

### 12.1. Integrating with Spring Method Security

Method security can be used:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

In the application service:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import java.util.UUID;

@Service
public class OrderService {

    @PreAuthorize(
        "hasAuthority('PERM_ORDER_EDIT') " +
        "and @orderGuard.mayEdit(authentication, #orderId)")
    public void editOrder(
            @P("orderId") UUID orderId,
            OrderPatch patch) {
        // Perform operation within an appropriate transaction.
    }
}
~~~

An application-layer **`orderGuard`**:

~~~java
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("orderGuard")
public class OrderGuard {

    private final CurrentActorResolver actorResolver;
    private final OrderRepository orders;
    private final OrderAuthorizationPolicy policy;

    public OrderGuard(
            CurrentActorResolver actorResolver,
            OrderRepository orders,
            OrderAuthorizationPolicy policy) {
        this.actorResolver = actorResolver;
        this.orders = orders;
        this.policy = policy;
    }

    public boolean mayEdit(
            Authentication authentication, UUID orderId) {

        ApplicationActor actor =
                actorResolver.resolve(authentication).orElse(null);

        if (actor == null) {
            return false;
        }

        return orders.findById(orderId)
                .map(order -> policy.mayEditOrder(actor, order))
                .orElse(false);
    }
}
~~~

This is an **integration pattern**: types **`OrderPatch`**, **`CurrentActorResolver`**, and **`OrderRepository`** must be defined in the application. The goal is that only **`CurrentActorResolver`/claim adapter** knows how to extract principals from `Authentication`, while **`OrderAuthorizationPolicy`** knows only `ApplicationActor` and `Order`.

Practical notes:

- **`@PreAuthorize`** requires method security enabled, calls routed through the Spring AOP proxy, and SpEL parameter names available.
- Domain authorization should execute close to the mutation, especially when order status can change between check and write. Transactions, versioning, or locking may be needed.
- Permission to call an endpoint does not prove the actor has access to **each individual order** retrieved.
- **`PERM_ORDER_EDIT`** is a coarse permission; checking order and tenant is fine-grained policy.

## 13. Beyond Normalizing Permissions: Distinguish User and Service Principals

OAuth 2.0 access tokens fall into two cases:

**User-delegated token:**

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "client_id": "shop-web",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1910003600
}
~~~

**Client-credentials token:**

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "inventory-sync",
  "client_id": "inventory-sync",
  "aud": "orders-api",
  "scope": "orders.sync",
  "exp": 1910003600
}
~~~

Having **`sub`** does not mean the principal is a human user. Depending on the AS/profile, **`sub`** in client credentials may represent a service/client principal. Adapters must identify the principal kind permitted by contract and map to the right local actor.

Example:

| Action | User Token | Service Token |
|---|---|---|
| View user's own orders | Evaluated by ownership | Not allowed by default |
| Run inventory data sync | Not allowed by default | Evaluated with service-designated permissions |
| Manually approve an order | Requires user identity + workflow policy | Often forbidden |
| View technical job status | Depends on scope and domain | Depends on service permission |

If an adapter translates **every token with a manager role** into a human **ADMIN**, it can accidentally elevate a service principal. **`PrincipalKind`** must be normalized based on verified token profile/claims, never guessed from the string format of **`sub`**.

## 14. Multi-Issuer: Each Issuer Needs Its Own Trust and Mapping Contract

When an API accepts tokens from multiple issuers, the work is not just adding a **`switch`** inside one converter. **Each issuer must be validated with its own key source and validators**.

~~~text
Issuer A (trusted)
  -> JWKS A
  -> JWT validation A
  -> Claim adapter A
  -> PERM_ORDER_READ / PERM_ORDER_EDIT
                                |
                                v
                         Domain policy
                                ^
                                |
Issuer B (trusted)              |
  -> JWKS B                     |
  -> JWT validation B           |
  -> Claim adapter B -----------+
  -> PERM_ORDER_READ / PERM_ORDER_EDIT

Unknown issuer
  -> Reject; never dynamically discover and trust unknown JWKS
~~~

In Spring Security Servlet applications, you can use multiple **`SecurityFilterChain`** beans by route or an **`AuthenticationManagerResolver<HttpServletRequest>`** with multi-tenant/multi-issuer configuration. If reading an unverified **`iss`** to select a manager, treat it strictly as a **routing hint** and accept only values from a **pre-configured issuer allow-list**. The selected decoder must still verify signature and issuer.

### Never Reuse Issuer A's Decoder Across All Issuers

Wrong:

~~~text
Token iss=B
  -> uses JWKS A just because alg/kid look similar
  -> skips issuer check
  -> accepts B's roles
~~~

Right:

~~~text
Token iss=B
  -> issuer B must be in trusted issuers
  -> decoder B uses JWKS B
  -> verifies iss=B, aud=orders-api, timestamps, profile
  -> claim adapter B maps per contract B
~~~

Two issuers can share **`kid`**, **`sub`**, or role names; that is never evidence they share keys, principals, or permission semantics.

### Never Merge Role Names Across Two Issuers Simply Because the Text Matches

For example, **`admin`** from Issuer A administers the login realm, while **`admin`** from Issuer B administers merchant profiles. Never map both to **`PERM_ORDER_APPROVE`** unless business policy confirms **each issuer is authorized to grant approval rights**.

## 15. Design Policies Around Authority Provenance, Not Just Claim Names

A core security question:

> Is this issuer **authorized to grant this business permission** to the Resource Server?

An issuer might mint JWTs with valid signatures and audiences while only being authorized to authenticate identity, not to grant domain administrative permissions.

Example:

~~~text
Issuer A:
  Trusted to authenticate employees.
  Not authorized to grant payment-approval rights.

Domain application:
  PERM_PAYMENT_APPROVE is managed by an internal system.

Conclusion:
  Issuer A emits role="payment-admin"
  -> must not map to PERM_PAYMENT_APPROVE
     without an explicit authorization contract for Issuer A.
~~~

Minimal model:

~~~text
Trusted token source
   AND issuer permitted to issue this grant type
   AND JWT matches audience/profile
   AND external permission is allow-listed
   AND live account/tenant policy holds
        => action may be evaluated
~~~

For sensitive permissions, tokens can **prove only identity and a minimal scope**, while approval privileges are decided by a **local authorization store/PDP**. This prevents an identity provider from becoming able to mint out-of-bounds business permissions.

## 16. How Should Token Scopes and App Permissions Combine?

Two common strategies exist:

### Strategy A: One Canonical Permission Suffices for Coarse Authorization

If the AS token contract states that role **`order-editor`** already represents entitlement for `orders-api`, the adapter can translate it to **`PERM_ORDER_EDIT`**, after which domain policies check tenant/order.

~~~text
allow coarse = PERM_ORDER_EDIT
allow final = coarse AND domain conditions
~~~

### Strategy B: OAuth Scope as Upper Bound, App Permission as Additional Condition

If the issuer grants scopes to the client while domain policies govern user/role permissions:

~~~text
allow =
    token has SCOPE_orders.write
    AND actor has PERM_ORDER_EDIT
    AND object policy accepts
~~~

Example:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and hasAuthority('PERM_ORDER_EDIT') " +
    "and @orderGuard.mayEdit(authentication, #orderId)")
~~~

Under this strategy, a custom authorities converter must **preserve both authority sets** if both are needed together. Calling **`setJwtGrantedAuthoritiesConverter`** with a converter returning only **`PERM_...`** stops **`SCOPE_...`** from appearing automatically.

Never accidentally turn **scope AND permission** into **scope OR permission**. A service token with broad scopes or incomplete roles could escalate privileges if policies misuse `OR`.

## 17. Opaque Access Tokens: Adapter Receives Introspected Metadata

When an AS issues opaque tokens, JWT converters do not apply because the Resource Server cannot inspect JWT claims directly. Instead, Spring Security uses **OAuth2 Token Introspection** per the AS contract.

Example response:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "custom_permissions": ["order:edit"],
  "exp": 1910003600
}
~~~

**`active=true`** does not automatically grant all permissions. Depending on contract, introspection responses may carry sparse or rich metadata; **`iss`** is not mandatory in every introspection response under RFC 7662.

At the adapter boundary:

1. Trust responses only from **configured and authenticated introspection endpoints**.
2. Verify issuer/resource binding per the AS contract.
3. Normalize attributes into the application's identity/permission model.
4. When decision data is missing, **never guess allow**.
5. Domain policies continue checking live permissions when needed.

You can customize **`OpaqueTokenIntrospector`** or post-introspection converters/adapters to produce a unified model. **Never couple domain services directly to the JSON shape of introspection responses.**

### Does Introspection Always Reflect the Latest Permissions?

Not automatically. An AS may return a snapshot of scopes from token issuance or recompute current rights; API-side introspection caching can also become stale. Clarify AS semantics, cache TTLs, revocation SLAs, and domain rules—especially for sensitive actions.

## 18. Permission Changes After Issuance: Canonical Permissions Can Still Be Stale

Decoupling claim names is necessary, yet **does not solve permission freshness on its own**.

~~~text
09:00 AS issues JWT:
  external role=order-editor

09:05 Admin revokes role.
  External authorization store updated.

09:06 Client presents old JWT:
  JWT still carries external role=order-editor.

Converter:
  order-editor -> PERM_ORDER_EDIT

If API checks only PERM_ORDER_EDIT:
  may still allow until token expires.
~~~

Therefore, in domains requiring rapid revocation, combine:

- Short JWT lifetimes where the AS re-evaluates roles upon renewal.
- Token revocation, introspection, denylists, or versioning per contract.
- Local account status, tenant membership, or PDP checks at request time.
- Explicit cache invalidation and maximum staleness bounds.
- Enforcement close to the business operation inside transactions.

Decoupling **claim names** from **policies** makes swapping issuers easier; enforcing live permissions still requires its own data sources and SLAs.

## 19. Deny-by-Default Policy When Claims Deviate from Expectations

When an adapter receives data violating the contract, **do not guess**.

| Received Data | Conservative Behavior |
|---|---|
| Missing role/scope claim required for permission | Do not grant the corresponding permission |
| Claim has wrong type, e.g., string instead of promised array | Reject permission or token per profile/validator |
| New role absent from allow-list mapping | Grant no new permission |
| Same role name from a different issuer | Use that issuer's dedicated mapping; never copy rights |
| Valid JWT signature with wrong audience | Reject token at validator before adapter |
| JWT with unclear access-token purpose | Reject per profile/contract |
| Claim states a role, yet local account is disabled | Domain/account policy denies |
| Claim carries an unknown group ID | Never infer roles; handle per group-mapping contract |
| Group claim truncated/overage | Do not assume all groups are held; query authoritative source or deny |
| Adapter mapping version incompatible with token | Deny unproven permissions; follow explicit migration process |
| Policy service unreachable | Fail closed for sensitive operations |
| External issuer not in allow-list | Never establish trust from the JWT |

There are two fail-closed levels:

- **Invalid token:** Resource Server rejects authentication (typically 401).
- **Authenticated token lacking permission:** authorization rejects (typically 403).

You do not necessarily turn every missing optional claim into **`invalid_token`** if it only grants an optional privilege. However, **never default to allow** when information required for a decision is missing.

## 20. Anti-Pattern: Automatically Converting Every Role into an Authority

Risky design example:

~~~java
// AVOID: any provider-named role becomes an API permission.
for (String role : rolesFromJwt) {
    authorities.add(
            new SimpleGrantedAuthority("PERM_" + role.toUpperCase()));
}
~~~

A provider could introduce a new **`SUPERUSER`** role for an unrelated workflow; if the application happens to check **`hasAuthority("PERM_SUPERUSER")`**, an unintended role silently turns into an internal privilege.

Use **explicit mapping**:

~~~text
issuer A + orders-api + order-reader
    -> PERM_ORDER_READ

issuer A + orders-api + order-editor
    -> PERM_ORDER_EDIT

any other external role
    -> no additional domain permissions
~~~

Review every mapping for **semantics**, not just spelling. Record metadata: owner, purpose, version, validity, and which APIs may trust it.

## 21. Anti-Pattern: Reading Claims Directly Inside Controllers or Repositories

Do not do:

~~~java
@GetMapping("/api/orders/{id}")
OrderDto get(
        @PathVariable String id,
        @AuthenticationPrincipal Jwt jwt) {

    if (jwt.getClaimAsStringList("groups").contains("manager")) {
        return orderRepository.load(id);
    }
    throw new AccessDeniedException("Denied");
}
~~~

Problems:

- The controller depends on the provider's **`groups`** claim.
- The string **`manager`** has no defined meaning for `orders-api`.
- No check on which issuer or tenant that group belongs to.
- No check on order ownership.
- Missing claims can cause null errors or inconsistent outcomes.
- Switching providers forces controller changes.

Better approach:

~~~text
Controller calls application service.
Application service obtains verified ApplicationActor.
OrderAuthorizationPolicy.canReadOrder(actor, order).
Repository queries data scoped to policy-verified tenant/owner.
~~~

This does not force all authorization into one giant class. The goal is **business policies using a stable vocabulary and enforced consistently** across REST APIs, background jobs, and message consumers.

## 22. Avoid Leaking Claim Names into Annotations and Database Schemas

Decoupling claim names only in controllers is insufficient if they persist inside:

- **`@PreAuthorize`** annotations across the codebase.
- Column names like **`keycloak_realm_role`** in domain authorization tables.
- Business events like **`PermissionGrantedFromCognitoGroup`** treated as generic permission events.
- Service APIs like **`isKeycloakOrderEditor(jwt)`**.
- Cache keys built solely from provider group names.
- Audit logs treating a provider claim as the sole user ID.

A cleaner model:

~~~text
Integration adapters:
  ProviderAClaimReader
  ProviderBClaimReader
  ExternalPrincipalResolver

Application:
  ApplicationActor
  BusinessPermission
  OrderAuthorizationPolicy
  OrderCommandService

Persistence:
  external_identity(issuer, subject, local_actor_id)
  membership(local_actor_id, tenant_id, status)
  permission_grant(local_actor_id, permission_code, context)
~~~

The **`external_identity`** table can use a unique key on **`(issuer, subject)`**. The **`permission_grant`** table stores internal permission codes. The database may record provenance of external grants separately for auditing, without turning provider claim names into public domain APIs.

## 23. Switching Issuers Without Rewriting Domain Policies

Suppose the system migrates from Issuer A to Issuer B. Before migration:

~~~text
Issuer A:
  resource_access.orders-api.roles = [order-editor]

Adapter A:
  order-editor -> PERM_ORDER_EDIT

Domain:
  canEditOrder(actor, order)
~~~

After migration:

~~~text
Issuer B:
  permissions = [update:orders]

Adapter B:
  update:orders -> PERM_ORDER_EDIT

Domain:
  canEditOrder(actor, order)
~~~

**The domain policy stays untouched.** Still, changing issuers is not just updating claim paths; it also requires **identity and trust migration**:

1. Identify the newly trusted issuer, JWKS/introspection endpoint, and valid audience.
2. Define the new mapping with equivalent or intentionally revised semantics.
3. Verify ID token vs. access token purpose; never use login tokens as API credentials.
4. Map new **`(issuer, sub)`** pairs to existing local actors through a trusted workflow, never auto-linking by email.
5. Handle the transition window when both issuers are accepted simultaneously.
6. Verify no unintended role grants elevated administrative rights.
7. Update auditing/provenance, operations, caches, and rollback plans.
8. Block the old issuer after cutoff once its contract is no longer trusted.

### Versionable Contract Mappings

Illustrative configuration data:

~~~yaml
authorization-mapping:
  version: 3
  issuers:
    issuer-a:
      issuer-uri: https://login-a.example.com/realms/shop
      resource: orders-api
      source: resource_access.orders-api.roles
      mapping:
        order-reader: PERM_ORDER_READ
        order-editor: PERM_ORDER_EDIT
    issuer-b:
      issuer-uri: https://login-b.example.com/
      resource: orders-api
      source: permissions
      mapping:
        read:orders: PERM_ORDER_READ
        update:orders: PERM_ORDER_EDIT
~~~

**The YAML above is a custom-designed format**, not built-in Spring Boot properties. In real YAML, keys containing colons like **`read:orders`** should be quoted where needed to avoid unexpected parsing. Critical permissions and mappings require code review and change control—never allow tokens or requests to supply mapping configuration.

## 24. Test Against the Contract, Not Just Claim Names

An adapter should have test cases verifying **canonical permission outcomes**:

| Scenario | Input Token / Claim | Expected Outcome |
|---|---|---|
| Valid read role from Issuer A | `order-reader` | `PERM_ORDER_READ` |
| Valid edit role from Issuer A | `order-editor` | `PERM_ORDER_EDIT` |
| Unknown role | `unexpected-admin` | No additional permissions |
| Token with wrong audience | `aud=billing-api` | Rejected before permission mapping |
| Role intended for another resource | `billing-api.roles=admin` | Grants no `orders-api` permissions |
| Issuer B role with same name as Issuer A | `admin` | Mapped per contract B or denied |
| Missing `resource_access` claim | `null` | Grants no permissions from claim |
| `roles` claim is not a collection | `"order-editor"` | Never guesses; fail-closed policy |
| Token from untrusted issuer | `iss=attacker` | Token rejected |
| Expired JWT | old `exp` | No authenticated principal created |
| OIDC ID token with access-token-like claims | `aud=web-client` | Never accepted as API access token |
| Client-credentials token | `sub=service-id` | Actor type `SERVICE` per contract |
| User membership changes after JWT issuance | old role still in JWT | Current domain policy denies if required |
| Actor has `PERM_ORDER_EDIT` yet order is `APPROVED` | `status=APPROVED` | Domain policy denies |
| Two issuers sharing `sub=123` | differing `iss` | Distinct `ExternalPrincipalKey` |

Distinguish two test categories:

- **Converter/unit tests:** pass a **prepared mock `Jwt` object** into the converter and assert permission mapping. This does not test signatures or issuers.
- **Resource Server integration tests:** run through a real `JwtDecoder`/validator/`AuthenticationManager` to verify signatures, issuers, audiences, token purpose, and the filter chain.

Spring Security Test can fabricate JWT authentications for authorization tests; that does not prove production verifies JWT signatures. **The cases above describe design expectations only; no test suite was executed here.**

## 25. Ensuring Safe Behavior When Permissions Change or Roles Are Revoked

Claims inside a JWT are **snapshotted when the AS issues the token**. When someone loses a role afterward, an old JWT can still carry that role and be mapped by the adapter to **`PERM_ORDER_EDIT`**.

Therefore:

~~~text
Issued token:
  role=order-editor
       |
       v
Adapter:
  PERM_ORDER_EDIT
       |
       v
Domain policy:
  Checks current membership + order ownership
       |
       v
Allows or denies based on live permissions
~~~

If the business tolerates brief staleness, use short JWT lifetimes paired with appropriate token renewal policies. When near-instant revocation is required, rely on a live permission store, introspection, denylists, token versioning, or a PDP per architecture.

**Never treat the claim adapter as the source of truth for current permissions**; it only translates data attested by the token issuer at issuance time.

## 26. Error Handling and Logging for Invalid Mappings

Never expose tokens or sensitive role details in HTTP responses. Typically:

- Invalid token, wrong issuer, wrong audience, or wrong purpose: **authentication failure**, usually 401 with a Bearer challenge.
- Valid token lacking **`PERM_ORDER_EDIT`**: **authorization failure**, usually 403.
- Valid token with permission but lacking rights on the order/tenant: domain authorization denies, typically 403 per policy.
- Adapter encountering a missing optional claim: may **omit granting the permission**, letting HTTP authorization deny rather than necessarily failing the entire token parse.

Challenge examples:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

and:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Exact responses depend on Spring Security entry points, denied handlers, and policy types. For denials caused strictly by a business permission absent from scopes, **`insufficient_scope`** may not be an accurate description; use a clear error contract without leaking resource details.

Logging should record:

~~~text
request_id
trusted_issuer_id
local_actor_id (if permitted by policy)
provider_adapter_version
canonical_permission_checked
policy_decision
reason_code
~~~

Never log raw bearer access tokens, full JWT payloads, credentials, introspection secrets, or private signing keys. Unverified claims may be attacker-controlled and should not be logged as trusted facts.

## 27. Design Checklist for API and IAM Teams

Before allowing a new issuer to grant internal permissions, ask:

1. Which issuers are trusted by the Resource Server and where are they configured?
2. Does the API accept **JWT access tokens** or **opaque access tokens**?
3. How are signature, algorithm, issuer, audience, expiration, and token profile checked?
4. Which claim genuinely carries **grants/entitlements for this API**, rather than issuer administrative roles?
5. Does that claim live in the **access token** or only in the **ID token**?
6. How are role/scope names versioned, and which team owns them?
7. Is the issuer authorized to grant each specific **`BusinessPermission`**, or only to authenticate identity?
8. Must delegated user tokens and client-credentials service tokens be distinguished?
9. Do missing claims, wrong types, or issuer schema changes fail closed?
10. Who owns mapping **`(issuer, sub)`** to local actors and account linking?
11. Is OAuth scope an upper bound or just one input to permission mapping?
12. Which permissions require request-time checks on membership, tenant, and owner?
13. If a role is revoked after token issuance, how quickly must the API stop allowing it?
14. What are the staleness bounds and failure modes of authorization/introspection caches?
15. Which domain services or event consumers still read provider claims directly?
16. Are there sufficient contract tests for old issuers, new issuers, and unrecognized roles?
17. Are permission provenance, mapping versions, and policy decisions audited?
18. Does switching issuers require migrating account IDs or adjusting privacy boundaries?

These are questions for **authentication and authorization contract design**, not questions controllers should figure out on every request.

## 28. Conclusion: Adapters Know the Issuer, Domains Know Only the Business

Keep one principle in mind:

~~~text
Issuer-specific claim names:
  realm_access, resource_access, scp, permissions, groups
                  |
                  v
     Trusted integration/adapter boundary
                  |
                  v
Application vocabulary:
  ApplicationActor
  BusinessPermission.ORDER_EDIT
  BusinessPermission.ORDER_APPROVE
                  |
                  v
Domain authorization:
  mayEditOrder(actor, order)
  mayApproveOrder(actor, order)
~~~

Key principles to maintain:

1. **Never write business policies around issuer-specific claim names.**
2. **Let `JwtDecoder`/introspection validate tokens before reading claims as trusted permissions.**
3. **Map external roles/scopes via allow-lists bound to explicit issuers and audiences.**
4. **Keep internal permission and principal models stable**, even when providers rename claims.
5. **Never infer equivalent authority from matching role strings** across different issuers.
6. **Separate identity, token grants, and domain permissions**, especially for multi-tenant and client-credentials flows.
7. **Separate coarse permissions from object-level authorization**; a role does not authorize every action on every record.
8. **Token permissions can go stale**; when rapid revocation is needed, pair with live policies or revocation mechanisms.
9. **Missing or unrecognized claims never grant permissions**, and never load arbitrary issuers/JWKS from unverified tokens.
10. **When changing Identity Providers, update adapters and trust config**; keep business rules in the domain vendor-independent.

**Conclusion:** the Resource Server is responsible for verifying **who issued a credential, which API it is meant for, and which grants it may carry**. The adapter layer translates provider-specific claims into a canonical model. Domain policies rely strictly on **system permission semantics** and resource data to decide actions. Consequently, switching issuers does not alter how business logic is protected, while avoiding privilege bugs caused by misinterpreting claims out of context.

## 29. References

- **Spring Security Reference — OAuth 2.0 Resource Server JWT (Servlet):** JWT configuration, authorities converters, issuer/audience validation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — OAuth 2.0 Resource Server Opaque Token:** introspection and principals/authorities for opaque tokens. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Method Security:** `@EnableMethodSecurity`, `@PreAuthorize`, and domain policies. https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- **Spring Security API — JwtAuthenticationConverter:** mapping `Jwt` to `Authentication`. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html
- **Spring Security API — JwtGrantedAuthoritiesConverter:** scope-to-authority mapping rules. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html
- **RFC 6749 — OAuth 2.0 Authorization Framework:** scopes and access token semantics. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer access token usage and errors. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token:** `iss`, `sub`, `aud`, `exp` claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JWT Best Current Practices:** issuer/audience validation and preventing token confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** JWT access token profile requirements. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 7662 — OAuth 2.0 Token Introspection:** validating tokens through the AS and related metadata. https://www.rfc-editor.org/rfc/rfc7662
