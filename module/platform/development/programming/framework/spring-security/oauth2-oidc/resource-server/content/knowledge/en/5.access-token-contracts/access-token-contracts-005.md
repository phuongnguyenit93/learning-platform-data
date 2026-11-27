# Scope, Roles, Permissions, and System-Defined Authorization Rules

In a system using **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, an access token may contain `scope`, `roles`, `permissions`, and subject details. This information helps the API decide whether a request may proceed, yet **claim names appearing in a token do not automatically create a universal authorization rule across all systems**.

OAuth 2.0 standardizes the mechanism for **requesting, granting, and using access privileges**. Questions such as "Which orders does `orders.read` allow reading?", "Can a support agent view orders from another tenant?", or "Can the `ADMIN` role cancel orders or only view reports?" must be **agreed upon, defined, and explicitly enforced by the token issuer and the API**.

> **Lesson focus:** Scope describes the range of operations granted to an access token; role describes the subject's role in an organizational/application model; permission describes a specific allowed action. An authorization policy combines these facts with the target resource and request context. Spring Security converts selected claims into **`GrantedAuthority`** objects for checks, but it does not understand business permissions unless the application defines them.

## 1. Putting Scope, Role, and Permission in Their Proper Places

Suppose an e-commerce system consists of:

- **Shop Web**: the OAuth2 Client used to request and present access tokens.
- **Identity Server**: the Authorization Server that authenticates and issues tokens.
- **Orders API**: the Resource Server protecting order data.
- **Order Service / Database**: where owners, tenants, order statuses, and business rules are stored.

A typical request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

To return order 42, the Orders API must answer **several questions**, not merely inspect the `scope` string:

1. Is the token valid, issued by a trusted issuer, and intended for `orders-api`?
2. Does the token have permission to **invoke the order-reading operation**?
3. Is the subject in the token a human user or an application? Which roles and permissions are recognized?
4. Which tenant/owner does order 42 belong to, and is it in a readable state?
5. Does the active policy allow **this subject** to perform **this action** on **that object** in **this request context**?

Distinguish the concepts from the start:

| Concept | Question It Answers | Example | Source / Semantics |
| --- | --- | --- | --- |
| **Scope** | What range of operations was this access token granted for? | `orders.read`, `orders.write` | Client requests; Authorization Server grants per policy; API defines usage |
| **Role** | What role does the subject hold in the organization/application? | `ORDER_SUPPORT`, `TENANT_ADMIN` | Identity system or application manages; meaningful only within defined domain and tenant |
| **Permission** | Which specific action is the subject capable of performing? | `order:read:own`, `order:read:tenant` | System-defined permission model; may be granted directly or derived from roles |
| **Policy / authorization rule** | Under these circumstances, allow or deny? | "Has read scope, has permission to read own order, and matching tenant" | Enforced by Resource Server/business layer from verified token and trusted data |
| **Authority in Spring Security** | Internal set of privilege strings evaluated by security expressions | `SCOPE_orders.read`, `ROLE_ORDER_SUPPORT`, `PERM_order:read:own` | Built from authentication and application converters/configuration |

Never equate **role with scope**, **permission with claim**, or **authority with everything inside a JWT**. They relate to each other through **conversion contracts and policies** established by the engineering team.

## 2. Scope: The Privilege Boundary of an Access Token

### 2.1. Scope Is an OAuth 2.0 Concept

In OAuth 2.0, a Client may request one or more **scopes** using the `scope` parameter during authorization/token requests. In the standard protocol representation, scopes are case-sensitive strings separated by spaces.

Example:

~~~text
scope=orders.read orders.write
~~~

The Authorization Server evaluates the Client's registration, grant type, subject privileges, and security policies to determine the **actually granted scopes**. A scope requested by a Client does not automatically become a scope granted to the Client.

A JWT access token might represent the grant outcome as:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read",
  "exp": 1893459600
}
~~~

In this example, the Client may have requested `orders.read orders.write`, yet the token **carries only `orders.read`**. When calling a write endpoint, the Orders API must rely on the verified scope from the token, never trusting the scope the Client originally asked for.

**Scope is an agreed set of permission names; the name itself carries no universal business meaning.** OAuth 2.0 does not stipulate that `orders.write` always implies `orders.read`, or that `admin` permits every action. If a system wants inclusion relationships between scopes, those relationships must be explicitly defined and enforced.

### 2.2. Scope Is an API-Level Privilege, Often Coarse-Grained

A scope contract might look like:

| Scope | Agreed Meaning | Endpoints That May Require It |
| --- | --- | --- |
| `orders.read` | Permitted to call order-reading operations per data policy | `GET /api/orders/{id}` |
| `orders.create` | Permitted to call order creation | `POST /api/orders` |
| `orders.cancel` | Permitted to call order cancellation | `POST /api/orders/{id}/cancel` |
| `reports.export` | Permitted to invoke report export | `POST /api/reports/export` |

Understand `orders.read` as **an entry-level privilege to invoke a read operation**, not proof of permission to read **every** order. Access to individual records depends on tenant, owner, role, status, or other conditions.

### 2.3. Scope Names Belong to the Issuer–API Contract

In practice, teams name scopes in many ways: `orders.read`, `read:orders`, `api://orders/read`. There is no single name standardized by OAuth 2.0 for reading orders.

The Client, Authorization Server, and Resource Server must agree on:

- Exact spelling of scope names, case-sensitively.
- Semantics and corresponding endpoints.
- Which Clients and grant types may request and receive them.
- Whether scopes imply one another or must be checked independently.
- Which claim carries scopes in the JWT or introspection response.

In particular, `openid`, `profile`, and `email` are **OIDC** scopes serving identity claims for the Client; they **do not automatically substitute** for business scopes such as `orders.read` on the Orders API.

## 3. Roles: The Subject's Position in the System

A **role** describes a group of responsibilities or the subject's position in a business domain. For example:

- `CUSTOMER`: a customer who can act on their own orders.
- `ORDER_SUPPORT`: an order support agent within assigned tenants.
- `TENANT_ADMIN`: an administrator of a specific tenant.
- `PLATFORM_AUDITOR`: personnel permitted to view audit data under audit policy.

Roles typically belong to **Role-Based Access Control (RBAC)**: the system assigns roles to subjects, assigns permissions to roles, and evaluates access based on active roles.

~~~mermaid
flowchart LR
    User["Subject: user-842"] --> Role["Role: ORDER_SUPPORT"]
    Role --> Perm1["Permission: order:read:tenant"]
    Role --> Perm2["Permission: order:comment"]
    Perm1 --> Policy["API + tenant + data rules"]
    Perm2 --> Policy
    Policy --> Decision["Allow or deny"]
~~~

Role is not a mandatory JWT claim. An Authorization Server may emit roles under `roles`, `realm_access.roles`, or a custom-namespaced claim; many systems **omit roles from tokens altogether**, and the Resource Server looks them up from a database, policy service, or authorization service.

### 3.1. A Role Does Not Automatically Define an Action

The `ORDER_SUPPORT` role **does not universally mean** permission to cancel orders, edit prices, export reports, or access other tenants. You need an explicit role → permission mapping and business constraints.

Example organizational contract:

| Role | Assigned Permissions | Scope of Validity |
| --- | --- | --- |
| `CUSTOMER` | `order:read:own`, `order:cancel:own` | User's own orders, when order status permits |
| `ORDER_SUPPORT` | `order:read:tenant`, `order:comment:tenant` | Orders within the assigned tenant |
| `TENANT_ADMIN` | `order:read:tenant`, `order:export:tenant` | Tenant administered by the user |
| `PLATFORM_AUDITOR` | `audit:read` | Audit data within granted scope |

This is only a **policy example**. Another system may define roles with identical names but completely different permissions.

### 3.2. Tenant-Scoped Roles Differ from Global Roles

In a multi-tenant model, a person might be `TENANT_ADMIN` in tenant A while only `CUSTOMER` in tenant B. If an access token contains `"roles": ["TENANT_ADMIN"]` with no tenant context, the API risks mistakenly applying administrative privileges to another tenant.

The contract must choose an unambiguous representation, such as:

~~~json
{
  "sub": "user-842",
  "aud": ["orders-api"],
  "tenant_id": "tenant-A",
  "roles": ["TENANT_ADMIN"]
}
~~~

In that case, the API must verify the tenant of the **accessed resource**, the tenant bound to the role, and active membership per policy. If a token spans multiple tenants, design claims or policy sources capable of expressing **per-tenant roles**, not just a flat global role array.

## 4. Permissions: Specific Actions on Resources

A **permission** typically describes a finer-grained capability than a role, such as:

~~~text
order:read:own
order:read:tenant
order:comment:tenant
order:cancel:own
order:refund:approved
report:export:tenant
~~~

The names above are not standardized by OAuth 2.0 or Spring Security. They are conventions for this example. In real designs, permissions can be strings, numeric codes, policy objects, or records in a policy engine.

Role usually answers **"Which responsibility group does the subject belong to?"**; permission answers **"Which capability does that group/subject hold?"**. The final decision may still require **"On which record, and in what state?"**.

Example with the `order:cancel:own` permission:

~~~text
Has permission "order:cancel:own"
        AND order.owner == authenticatedSubject
        AND order.tenant == authorizedTenant
        AND order.status IN [NEW, CONFIRMED]
        => allowed to cancel per policy
~~~

If the order has already shipped or belongs to someone else, having `order:cancel:own` **does not automatically** make cancellation valid.

### 4.1. Permissions Can Live in the Token or in the Backend

Two common deployment models:

| Permission Management Approach | Advantages | Limitations to Handle |
| --- | --- | --- |
| **Embed permissions in the access token** | API can quickly check issuer-attested permissions; less dependent on online lookups | Permissions can change before the token expires; tokens can grow large; must strictly verify issuer/audience and claim semantics |
| **Look up permissions in the API/policy service** | Enforces up-to-date permissions and data-dependent policies | Must manage latency, availability, caching, and trusted data sources |

A hybrid approach works too: the token carries scope/identity/tenant while the Resource Server looks up current roles and permissions. No single model fits every system.

### 4.2. Never Mistake Permissions for Arbitrary Client-Sent Claims

If an API receives:

~~~http
X-Role: TENANT_ADMIN
X-Permissions: order:read:tenant
~~~

those headers **are not trustworthy just because the Client sent them**. They can be forged. The Resource Server should only rely on roles/permissions from trusted sources: claims from a verified token, a protected internal session/identity store, or server-managed authorization data.

## 5. Authorization Rules: From Token to Access Decision

An **authorization policy** is the rule determining under what context a subject may perform an action on a resource. Expressed concisely:

~~~text
allow = authenticated_token
    AND intended_for_this_api
    AND required_scope
    AND required_permission_or_role_policy
    AND resource_constraints
    AND contextual_constraints
~~~

This is an **illustrative model**; some organizations build policies with allow/deny rule sets, deny-overrides, or dedicated permissions rather than requiring every claim type simultaneously. Combination rules must be written into an explicit contract.

### 5.1. Example Endpoint and Record-Level Policies

| Action | Required Scope | Role/Permission Condition | Data Constraints |
| --- | --- | --- | --- |
| View own order | `orders.read` | `order:read:own` | `sub` matches owner; matching tenant |
| Support staff views order | `orders.read` | `order:read:tenant` or corresponding role | Order within assigned tenant/group |
| Customer cancels order | `orders.cancel` | `order:cancel:own` | Order owner; cancellable status |
| Export tenant report | `reports.export` | `report:export:tenant` | Valid tenant; adheres to data limits |
| Batch service syncs orders | `orders.sync` | Client/service principal on allowlist | Only approved data, timing, and purpose |

A token with sufficient scope but lacking the appropriate permission may be rejected. Conversely, a token with a support role that lacks `orders.read` will not necessarily be allowed to call the read endpoint; the contract in this example requires **both the scope and the role/permission condition**.

### 5.2. Three Familiar Rule Models

- **RBAC (Role-Based Access Control):** Decisions based on roles and permissions attached to roles.
- **ABAC (Attribute-Based Access Control):** Decisions based on subject, resource, and environmental attributes such as tenant, owner, status, or location.
- **ReBAC (Relationship-Based Access Control):** Decisions based on relationships between entities, e.g., a user is a member of the team owning an order.

Real systems often combine them. Scope typically acts as the API's "outer gate," while RBAC/ABAC/ReBAC enforce detailed business constraints.

### 5.3. Define the Source of Truth for Permissions

When sources disagree, the API needs a clear trust hierarchy:

1. **Token:** Use only verified claims matching the issuer/audience/token-type contract.
2. **Identity/privilege data:** Accept roles or permissions only from a trusted issuer or a managed server-side source.
3. **Resource data:** Fetch owner/tenant/status from the database or authoritative business source; never trust a Client-declared tenant ID.
4. **Active policy:** Apply the properly configured policy version; if critical decision data is missing, deny under fail-closed principles.

**The Authorization Server decides token/scope issuance per issuance policy; the Resource Server decides resource access per API policy.** The AS issuing `orders.read` does not mean the AS verified permission to read order 42.

## 6. Who Controls Which Part of the Access Token Contract?

~~~mermaid
sequenceDiagram
    actor U as User
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server
    participant DB as Order DB / Policy Store

    U->>C: Request to view order
    C->>AS: Request token with scope orders.read
    AS->>AS: Validate Client, grant, user, and policy
    AS-->>C: Issued token (actual scopes)
    C->>RS: GET /api/orders/42 + access token
    RS->>RS: Verify signature, iss, aud, exp
    RS->>RS: Read trusted scope/roles/permissions
    RS->>DB: Fetch order, tenant, owner, status
    DB-->>RS: Authoritative data
    RS->>RS: Evaluate policy
    RS-->>C: 200 or reject 401/403/404
~~~

| Party | Primary Responsibility for Privileges |
| --- | --- |
| **Client** | Request needed scopes; use the granted access token; never escalate its own scope/role/permission |
| **Authorization Server** | Validate Client/subject/grant; decide granted scopes/claims; sign or protect tokens; publish format and semantics |
| **Resource Server** | Verify token; check audience, scope/authority; fetch needed data and enforce action/resource policies |
| **Privilege/business management service** | Maintain roles, permissions, tenant memberships, ownership, object states, and policies changing over time |

The Resource Server may embed policies directly or call a separate policy decision service. Either way, **the API must govern how the result is used** and never assume a valid token means "allow."

## 7. Spring Security Claims and Authorities

In Spring Security, **`GrantedAuthority`** represents a privilege attached to an `Authentication` object. The framework uses these authorities to evaluate `hasAuthority(...)`, `hasRole(...)`, and other access expressions.

**Authority is Spring Security's internal model, not a mandatory standard JWT field.** When the Resource Server successfully validates a JWT, Spring Security creates a `JwtAuthenticationToken` and converts selected claims into authorities via `JwtGrantedAuthoritiesConverter` or a custom converter.

### 7.1. Default Scope Mapping

For a JWT containing a `scope` or `scp` claim in a supported format, Spring Security's default converter typically adds the **`SCOPE_`** prefix.

Example:

~~~json
{
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read orders.cancel"
}
~~~

Once the token is verified, the authority list becomes:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

In HTTP security configuration:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

**Note:** `hasAuthority("orders.read")` will not match `SCOPE_orders.read` when using the default converter. Authority names must match the exact strings populated in `Authentication`.

### 7.2. `hasRole` and the `ROLE_` Prefix

Spring Security typically interprets:

~~~java
hasRole("ORDER_SUPPORT")
~~~

as matching the authority:

~~~text
ROLE_ORDER_SUPPORT
~~~

Meanwhile:

~~~java
hasAuthority("ROLE_ORDER_SUPPORT")
~~~

checks that exact authority string directly. The `ROLE_` convention is a Spring Security mechanism; **it does not mean a JWT is required to contain a `role` or `roles` claim**.

If an access token carries `"roles": ["ORDER_SUPPORT"]`, the default JWT converter **does not automatically guarantee** creating `ROLE_ORDER_SUPPORT`. You must define the claim source and configure the mapping per contract.

### 7.3. Choosing Non-Colliding Authority Conventions

In a system with scopes, roles, and permissions, you can standardize on:

| Verified Source | Example Claim Shape | Internal GrantedAuthority |
| --- | --- | --- |
| Scope | `"scope": "orders.read"` | `SCOPE_orders.read` |
| Role | `"roles": ["ORDER_SUPPORT"]` | `ROLE_ORDER_SUPPORT` |
| Permission | `"permissions": ["order:read:tenant"]` | `PERM_order:read:tenant` |

Using `PERM_` is an **application-defined convention**, not a built-in Spring Security prefix. Distinct prefixes prevent semantic collisions across claim sources, though this only works if both converters and policies adhere to it consistently.

## 8. Example Resource Server Receiving a JWT and Mapping Authorities

The example below uses Spring Boot 3 / Spring Security 6 and assumes the **Authorization Server issued a JWT access token** under this contract:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["ORDER_SUPPORT"],
  "permissions": ["order:read:tenant"],
  "tenant_id": "tenant-A",
  "exp": 1893459600
}
~~~

In this example contract, `roles` and `permissions` are **string arrays**; role names lack the `ROLE_` prefix, and permission names lack the `PERM_` prefix.

### 8.1. Dependencies and Issuer

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test

app:
  security:
    audience: orders-api
~~~

The issuer in this example is a placeholder for a managed environment. In real deployments, the API must use the exact issuer published by the Authorization Server and may add `jwk-set-uri` if the architecture requires pointing directly to the JWKS.

### 8.2. Protecting the API with Scopes

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This snippet focuses on scope-based rules at the HTTP layer. In a stateless Bearer-token API, CSRF and session configurations must be evaluated per your architecture; if the same application also serves a session-cookie website, protect that flow accordingly.

### 8.3. Mapping Roles and Permissions from Trusted Claims

Spring Security can combine default scope mapping with application-defined role/permission mapping:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
class JwtAuthoritiesConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter authenticationConverter =
                new JwtAuthenticationConverter();

        authenticationConverter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Collection<GrantedAuthority> authorities =
                    new ArrayList<>(scopes.convert(jwt));

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                for (String role : roles) {
                    authorities.add(
                            new SimpleGrantedAuthority("ROLE_" + role));
                }
            }

            List<String> permissions =
                    jwt.getClaimAsStringList("permissions");
            if (permissions != null) {
                for (String permission : permissions) {
                    authorities.add(
                            new SimpleGrantedAuthority("PERM_" + permission));
                }
            }
            return authorities;
        });

        return authenticationConverter;
    }
}
~~~

To use this converter, wire it into the Resource Server configuration:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter)))
        .build();
}
~~~

This is an **alternative variant** of the `apiSecurity` bean in Section 8.2 to illustrate wiring the converter; in a real project, combine all needed endpoint rules into **one** bean rather than declaring two beans with the same name. Only map `roles` and `permissions` like this once issuer, audience, and claim format are verified per contract. If the issuer provides tenant-scoped roles or nested claims, mapping logic must accurately reflect that structure and semantics.

In a multi-issuer system, **never blindly apply the same role mapping across all tokens**. An `ADMIN` claim from issuer A is not automatically equivalent to `ADMIN` from issuer B. Validation and mapping configurations must be bound to their respective issuing sources.

### 8.4. Checking Issuer, Expiration, and Audience

Configuring only an issuer lets the API verify the issuing origin using Spring Security's built-in capabilities, but you still must check that **the token is intended for the Orders API**. Example defining a custom `JwtDecoder`:

~~~java
import org.springframework.beans.factory.annotation.Value;
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

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwks-uri}") String jwksUri,
            @Value("${app.security.audience}") String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(expectedAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token is not intended for this API",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(standard, audience));
        return decoder;
    }
}
~~~

Additional configuration for the example:

~~~yaml
app:
  security:
    issuer: https://identity.example.test
    jwks-uri: https://identity.example.test/.well-known/jwks.json
    audience: orders-api
~~~

The JWKS URI is an example; replace it with the real endpoint published by your trusted issuer. If an application defines its own `JwtDecoder`, preserve signature verification, allowed algorithms, issuer, timestamps, and profile constraints; never replace default validators with a standalone `aud` check. The Resource Server should also distinguish access tokens from ID tokens per the issuance profile to prevent token-type confusion.

### 8.5. Method-Level Authorization

With `@EnableMethodSecurity`, you can protect a business method:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    private final OrderRepository orders;
    private final OrderAccessPolicy accessPolicy;

    OrderQueryService(
            OrderRepository orders,
            OrderAccessPolicy accessPolicy) {
        this.orders = orders;
        this.accessPolicy = accessPolicy;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') and " +
        "(hasAuthority('PERM_order:read:own') or " +
        "hasAuthority('PERM_order:read:tenant'))")
    public OrderDto getOrder(String id, CallerContext caller) {
        Order order = orders.findById(id)
                .orElseThrow(OrderNotFoundException::new);

        // Verify tenant, owner, and record-level permissions.
        accessPolicy.assertCanRead(caller, order);
        return OrderDto.from(order);
    }
}
~~~

`OrderRepository`, `OrderAccessPolicy`, `CallerContext`, `OrderDto`, and `OrderNotFoundException` are illustrative business types, not built-in Spring Security classes. `CallerContext` must be constructed from the verified `Authentication` along with trusted server data; **never trust caller attributes self-declared in the request body**.

Here, the `@PreAuthorize` expression filters coarse-grained scope and permission. `assertCanRead` then enforces concrete conditions such as:

~~~text
order.tenantId == caller.authorizedTenantId
AND (
    (caller.has("order:read:own") AND order.ownerSubject == caller.subject)
    OR caller.has("order:read:tenant")
)
~~~

If roles/permissions are fetched dynamically from a database, `accessPolicy` can evaluate from that source rather than relying solely on authorities inside the JWT. What matters is **enforcing policy on the actual resource**, not just checking claims in a filter.

## 9. Token Issuance Flow Differs from Request Evaluation Flow

### 9.1. At the Authorization Server: Deciding Scope Issuance

In the Authorization Code flow, scope issuance decisions may be based on:

- Which scopes the registered Client is permitted to request.
- Whether the user has authenticated and what permissions they hold.
- Whether consent is required and, if so, what the user consented to.
- Which resource/audience the token is being issued for.
- Organizational, tenant, and security policies.

For example, Shop Web registers `orders.read` and `orders.cancel`. When a user lacks cancellation privileges, the Authorization Server may issue only `orders.read`. Actual behavior depends on policy, yet **a Client can never add `orders.cancel` itself by modifying the token payload**.

In the `client_credentials` flow, the token may represent the application/service itself with no end user. Scopes should be issued based on Client identity and service privileges; the API must never assume `sub` in such a token is a customer ID.

### 9.2. At the Resource Server: Evaluating Request Permissions

Once a request arrives with a Bearer token, it passes through these steps:

~~~mermaid
flowchart TD
    A["Receive access token"] --> B{"Signature/issuer/expiration/audience valid?"}
    B -->|No| C["401 Unauthorized"]
    B -->|Yes| D{"Has endpoint-required scope?"}
    D -->|No| E["403 Forbidden"]
    D -->|Yes| F{"Role/permission satisfies policy?"}
    F -->|No| E
    F -->|Yes| G{"Owner/tenant/status allows access?"}
    G -->|No| H["403 or 404 per policy"]
    G -->|Yes| I["Execute action"]
~~~

A missing or invalid token typically results in 401; an authenticated token lacking privileges typically results in 403. When avoiding leaking whether a record exists, an API may return 404 per policy. Exact behavior also depends on entry point, access denied handler, and application configuration.

## 10. Differences Between Scope, Role, and Permission Across Common Flows

### 10.1. User Calling the API via a Client

Illustrative token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "customer-47",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read orders.cancel",
  "roles": ["CUSTOMER"],
  "permissions": ["order:read:own", "order:cancel:own"],
  "tenant_id": "tenant-A"
}
~~~

Assuming the token is verified and unexpired, `customer-47` may attempt to view or cancel their own orders subject to scope, permissions, and order status. This token **does not grant permission to read another customer's orders**, even within the same tenant, unless policy allows it.

### 10.2. Support Agent in the Same Tenant

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "support-12",
  "aud": ["orders-api"],
  "client_id": "support-console",
  "scope": "orders.read",
  "roles": ["ORDER_SUPPORT"],
  "permissions": ["order:read:tenant"],
  "tenant_id": "tenant-A"
}
~~~

The support agent's role/permission allows reading orders assigned to them within `tenant-A`. If the system enforces team or regional boundaries, the API must still apply those constraints; a claim named `order:read:tenant` does not necessarily mean the entire tenant in every design.

### 10.3. Service-to-Service via Client Credentials

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "nightly-sync",
  "client_id": "nightly-sync",
  "aud": ["orders-api"],
  "scope": "orders.sync"
}
~~~

`nightly-sync` is a service Client and does not necessarily have any user role. The Orders API may allow `/internal/sync` when the token targets the right audience, carries `orders.sync`, and the Client meets service policy. The API must never assign `CUSTOMER` privileges merely because the token has a `sub`.

If a service needs to call an API **on behalf of a user**, token forwarding or token exchange requires explicit delegation rules. A token with an audience for Service A is not automatically valid for Service B.

## 11. Common Mistakes When Defining Permissions

### "Having the ADMIN role bypasses scope"

A role named `ADMIN` may only be valid within one tenant or application. If the API contract requires `orders.read`, that role does not automatically replace the scope. If admin exceptions are desired, define and enforce them explicitly while avoiding turning a local role into global privilege.

### "Having the `orders.read` scope grants access to every order"

Scope typically constrains the category of operation invoked. The API must verify owner, tenant, assignment, status, and other business rules.

### "Spring Security automatically understands a `roles` claim in the JWT"

The default JWT converter primarily maps scopes from supported claims into `SCOPE_...`. To use `roles` or `permissions` in custom structures, configure an appropriate converter or policy mechanism.

### "If the Client sends `X-Permissions`, the API should use it"

Clients must never self-assert permissions via headers or JSON request fields. Permissions must come from a verified issuer or a protected server-side data source.

### "Permissions in a JWT are always up to date immediately"

An issued JWT can retain stale permission claims until expiration unless the system uses additional checks or revocation. For sensitive operations, combine short token lifetimes, introspection, live permission checks, or a centralized policy source.

### "If the scope name is the same, every issuer is equally trusted"

A `scope = orders.read` claim from two different issuers does not imply equivalent trust. The Resource Server must verify issuer, audience, keys, and token profile, honoring claims only per an approved issuer's contract.

### "Successful OIDC login means permission to call the Orders API"

OIDC authenticates the user for the Client. ID tokens and `openid profile email` scopes do not grant order-reading privileges. The API requires an **access token with the right audience and business privileges**.

### "Checking an annotation alone is enough"

`@PreAuthorize("hasRole('ORDER_SUPPORT')")` can guard a broad feature, yet it may not verify whether the agent may access a **specific order** or **specific tenant**. Authorization must reach the data layer.

## 12. Designing an Implementable Access Token Contract

A permission contract for the Orders API should specify:

| Component | Example Agreement | Enforcing Party |
| --- | --- | --- |
| Issuer | `https://identity.example.test` | AS issues; API verifies |
| Audience | `orders-api` | AS issues; API verifies |
| Token type | OAuth2 access token; ID tokens not accepted as API Bearer tokens | AS/Client/API |
| Read-orders scope | `orders.read` | AS grants; API checks |
| Role claim | `roles` as string array with `CUSTOMER`, `ORDER_SUPPORT`, etc. | AS issues or API looks up; API maps |
| Permission claim | `permissions` as string array per permission table | AS issues or API looks up; API maps |
| Spring prefixes | `SCOPE_`, `ROLE_`, `PERM_` | API configuration |
| Tenant | `tenant_id` and rules binding tenant to subject/role | AS or policy store; API checks |
| Data policy | Owner, tenant, assigned group, order status | Business API |
| Service principal rights | Scopes/Clients permitted to call internal APIs | AS and API |
| Privilege updates | Token lifetime, revocation/cache/live-lookup strategy | AS/API |
| Error responses | 401 invalid token; 403 insufficient privilege; 404 when hiding resources | API |

For operational clarity, the permission matrix can use a structured representation:

~~~yaml
# Illustrative contract document; not a standard config read automatically by Spring.
api: orders-api
scope_contract:
  orders.read: "May request order read endpoints"
  orders.cancel: "May request order cancellation"
role_mapping:
  CUSTOMER:
    - order:read:own
    - order:cancel:own
  ORDER_SUPPORT:
    - order:read:tenant
    - order:comment:tenant
policy:
  read_order:
    required_scope: orders.read
    required_any_permission:
      - order:read:own
      - order:read:tenant
    requires_tenant_match: true
    requires_ownership_for: order:read:own
  cancel_order:
    required_scope: orders.cancel
    required_permission: order:cancel:own
    requires_owner_match: true
    allowed_order_statuses:
      - NEW
      - CONFIRMED
~~~

In a real specification, add rules for missing roles/permissions, controls over which scopes each Client may receive, tenant boundaries, policy evolution, and error observability. If the system uses a policy engine, this YAML template can be translated into the engine's format; otherwise, engineers implement the rules across the security and business layers in a controlled manner.

## 13. Scenario Thought Exercises

**Scenario A:** Token has `orders.read`, `ROLE_ORDER_SUPPORT`, but Order 42 belongs to another tenant.

Outcome per the example contract: **deny**. Scopes and roles do not cross tenant boundaries.

**Scenario B:** Token has `roles = ["TENANT_ADMIN"]` without `orders.cancel`. Client sends a cancel request.

If the API requires `orders.cancel`, the request is rejected for missing scope—even though the role is named "admin." If that role should permit cancellation, the contract must align scope, permission, and tenant rules consistently.

**Scenario C:** Client requests `orders.read orders.cancel`; AS grants only `orders.read`.

The Client may use the token within the granted scope; the API must reject cancellation because the token lacks that scope. The Client cannot escalate privileges by tampering with the payload or sending an extra `scope` parameter when calling the API.

**Scenario D:** Token carries `permissions = ["order:cancel:own"]`, but Order 42 has already shipped.

Even when the order owner has the right permission and scope, the API denies the request if policy forbids cancelling shipped orders. Permissions describe capability, not exemption from state constraints.

**Scenario E:** A `client_credentials` job token has `orders.sync`, yet API code tries to look up a user based on `sub`.

This is a false assumption about principal kind. The API must apply policy designed for **service principals/Clients** and never treat a service token as an end user.

## 14. Questions to Answer Before Going to Production

1. Are scopes defined around API capabilities or user roles? What is each scope's exact meaning and boundary?
2. How does the AS decide which scopes to grant per Client, subject, and grant type? Can a Client over-request privileges?
3. Who manages roles—are they tenant-scoped or global? Is there an explicit role → permission table?
4. Are permissions issued inside tokens or looked up server-side? When privileges are revoked, is immediate enforcement required?
5. Does the Resource Server validate `iss`, `aud`, expiration, token type, and signature before reading privilege claims?
6. Do Spring Security converters map claims to authorities with the exact expected names and prefixes?
7. Where are owner, tenant, group, status, and delegation policies enforced?
8. If privilege claims or policy data are missing, does the API fail closed safely or permit by default?
9. Are user tokens distinguished from `client_credentials` tokens?
10. Does the API return consistent 401/403/404 status codes and log by request ID without exposing Bearer tokens?

**Remember:** **Scope** bounds the privileges granted to an access token; **role** represents a subject's position in the business model; **permission** describes an action capability; and **authorization policy** renders the decision on a specific resource and context. In Spring Security Resource Server, every claim must be read from a verified token and mapped under an explicit contract, and the API must still verify permissions against real business data before returning results.
