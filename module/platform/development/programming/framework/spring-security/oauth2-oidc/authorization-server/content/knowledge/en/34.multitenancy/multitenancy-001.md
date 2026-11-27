# Choosing a Single-Issuer or Multi-Issuer Model for Tenants

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect Authorization Server** using **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, multiple organizations can share a single login platform while still needing to separate clients, users, policies, signing keys, and authorization data. This architecture is commonly known as multi-tenancy.

A foundational decision when designing a multi-tenant Authorization Server is choosing between:

- **A shared single issuer:** all tenants share the same OpenID Provider (OP) identity and the same issuer value. Tenants are distinguished by context, client, claim, or authorization data.
- **One issuer per tenant:** each tenant has its own issuer identifier. Each issuer is an independent OP identity at the protocol level, even though they may run on the same deployment and share infrastructure.

This is not just a URL decision. The issuer affects discovery metadata, the `iss` value in tokens, how clients verify ID Tokens, how Resource Servers verify access tokens, key sets, the client registry, consent, logout, caching, and operations.

Running example: the `login.example.com` platform serves three tenants: Acme, Fabrikam, and Northwind. All three tenants can share a common login UI, but Acme requires its own signing key and its own issuer to integrate with its federation system. Fabrikam and Northwind only need data and access separation within the same trust domain.

After this lesson, you will be able to:

1. Distinguish an issuer identifier from a tenant ID, client ID, and login domain.
2. Compare the shared single-issuer model with the per-tenant multi-issuer model.
3. Choose a model based on trust boundaries, federation, key management, compliance, and operational cost.
4. Design tenant resolution from hostname/path safely.
5. Ensure consistency across discovery metadata, endpoints, and the `iss` claim.
6. Partition `RegisteredClient`, authorization, consent, signing keys, and persistence by tenant.
7. Understand the limitations of Spring Authorization Server's static issuer configuration and the extensions required for multiple issuers.
8. Design a Resource Server that trusts the right list of issuers.
9. Plan an issuer migration without breaking circulating tokens.
10. Test for tenant routing errors, cross-tenant access, and data leakage.

**Version scope:** Examples reference Spring Authorization Server 1.5.8 and Spring Security 6.x. The framework provides the core services and issuer configuration; routing across multiple tenants/issuers is an application architecture responsibility. A static issuer configuration bean does not automatically turn an Authorization Server into a multi-issuer server.

## 2. What Is an Issuer and Why Does This Decision Matter?

### 2.1. An Issuer Identifies an OpenID Provider

An issuer identifier is the URL identifier of an OpenID Provider. It appears in:

- The `issuer` field of OpenID Provider Discovery metadata.
- The `iss` claim in ID Tokens.
- The `iss` claim in JWT access tokens if the Authorization Server issues JWT access tokens.
- The trust configuration of OIDC clients and OAuth 2.0 Resource Servers.
- How clients locate the discovery document and JWKS endpoint.

Example of an issuer:

~~~text
https://login.example.com
~~~

An issuer is not a tenant name, tenant ID, or client ID. Two tenants can have different tenant IDs while still sharing the same issuer. Conversely, two issuers can serve the same tenant if the architecture has multiple OP identities for independent environments or regions.

### 2.2. The iss Value Must Be Consistent

Clients and Resource Servers verify the issuer against a trusted value. The `iss` value in a token must match the exact issuer that the client/Resource Server has configured or retrieved from discovery metadata.

Example:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-8f2a",
  "aud": "orders-api",
  "tenant_id": "acme"
}
~~~

In this example, `iss` identifies the shared OP; `tenant_id` is an application claim representing the tenant. The `tenant_id` claim does not replace verification of the issuer, signature, audience, and token expiration.

Do not issue a token with `iss=https://login.example.com/acme` if the client's discovery metadata advertises the issuer as `https://login.example.com`. Inconsistency causes token validation to fail or creates conditions for trust misconfiguration vulnerabilities.

### 2.3. An Issuer Is a Protocol-Level Trust Boundary

A dedicated issuer helps clients and Resource Servers identify which OP issued a token. However, a dedicated issuer **does not automatically guarantee** that data, databases, signing keys, or processes are physically isolated.

Example of two issuers:

~~~text
https://acme.login.example.com
https://fabrikam.login.example.com
~~~

They may use two separate databases and two separate HSM keys, or still share a PostgreSQL database with a tenant ID column and the same application process. The actual isolation level depends on storage design, key management, runtime, and operational permissions.

### 2.4. Do Not Equate the Login Domain with the Issuer

A platform can use:

- A shared login domain with multiple issuers.
- Multiple custom domains with a single canonical issuer.
- A shared issuer with tenant switching after the user logs in.

What matters is that the discovery document, endpoints, ID Tokens, and access tokens remain consistent with the advertised issuer. Do not infer the issuer solely from the request hostname without verifying which tenant that hostname belongs to.

### 2.5. Formatting Rules and Stability of an Issuer

An issuer identifier in OpenID Connect is an HTTPS URL. It must not contain a query or fragment; choose a stable canonical URL and keep the exact same representation in discovery metadata and tokens. Variants differing only by a trailing `/`, hostname alias, or scheme may be treated by clients as different issuers.

Do not change the issuer per login, based on a renameable tenant label, or based on a request-supplied hostname. If a tenant changes its display name, keep the old issuer identifier; changing an issuer URL must be treated as a protocol migration.

## 3. Two Architectural Models

### 3.1. One Shared Issuer for All Tenants

Example:

~~~text
Issuer: https://login.example.com

Tenant Acme      -> tenant_id=acme
Tenant Fabrikam  -> tenant_id=fabrikam
Tenant Northwind -> tenant_id=northwind
~~~

All clients use the same discovery document. Tokens share the same issuer; the tenant is bound via tenant context, client policy, and claims.

~~~mermaid
flowchart TD
    A["Tenant Acme"] --> D["Shared Authorization Server"]
    B["Tenant Fabrikam"] --> D
    C["Tenant Northwind"] --> D
    D --> E["Issuer: login.example.com"]
    E --> F["Shared discovery and JWKS"]
    E --> G["Tenant-aware client / authorization policy"]
    G --> H[("Tenant-partitioned storage")]
    G --> I["Tokens with tenant context"]
~~~

Characteristics:

- One issuer identifier and one discovery document.
- A shared signing key set can be used.
- The client registry and authorization store must resolve tenant context when separation is needed.
- Resource Servers verify a single issuer and then check tenant claims/authorization.
- Easier discovery operations and client integration.

This model fits when tenants belong to the same trust domain, share platform policies, and do not need independent federation identities.

### 3.2. One Issuer per Tenant

Example:

~~~text
Tenant Acme:
  https://acme.login.example.com

Tenant Fabrikam:
  https://fabrikam.login.example.com

Tenant Northwind:
  https://northwind.login.example.com
~~~

Each tenant has its own issuer identifier. Discovery metadata, token issuer, and client/Resource Server trust configuration are scoped by tenant.

~~~mermaid
flowchart TD
    A["Tenant Acme"] --> D["Tenant routing"]
    B["Tenant Fabrikam"] --> D
    C["Tenant Northwind"] --> D
    D --> E["Acme issuer context"]
    D --> F["Fabrikam issuer context"]
    D --> G["Northwind issuer context"]
    E --> H["Acme discovery / JWKS / keys"]
    F --> I["Fabrikam discovery / JWKS / keys"]
    G --> J["Northwind discovery / JWKS / keys"]
    H --> K[("Tenant-scoped persistence")]
    I --> K
    J --> K
~~~

Characteristics:

- Each tenant has its own issuer identifier and discovery metadata.
- Can have separate key sets, signing keys, client registries, consents, and policies.
- Clients can trust a specific tenant instead of trusting the entire shared OP.
- Resource Servers must verify that the issuer is in an allow-list.
- Higher operational complexity due to managing multiple issuers, endpoints, key rotations, and discovery documents.

This model fits when tenants have independent trust domains, federation, key ownership, compliance requirements, or lifecycles.

### 3.3. Multiple Issuers Do Not Necessarily Mean Multiple Deployments

There are three common deployment approaches:

| Deployment approach | Characteristics | Complexity |
| --- | --- | --- |
| Single deployment, single issuer | One shared Authorization Server configuration set. | Low |
| Single deployment, multiple issuers | Requests are routed into tenant-specific issuer contexts and services. | High |
| Multiple deployments, one issuer each | Each tenant or group of tenants has its own configuration and runtime. | Higher infrastructure operations, clearer boundaries |

There is no requirement that one issuer must run on a separate server. An issuer is a protocol-level identity; deployment is how the runtime is organized.

## 4. Choosing a Model Based on Requirements

### 4.1. Decision Matrix

| Criterion | Shared single issuer | One issuer per tenant |
| --- | --- | --- |
| Trust domain | Tenants trust the same OP. | Each tenant can have its own trust relationship. |
| Discovery | One metadata document. | Separate metadata per issuer. |
| Client registration | Can share a registry; needs tenant scoping. | Separate registry or namespaced by issuer. |
| Signing keys | Can share a key set. | Can separate key sets and key management permissions. |
| Token issuer | Same `iss`; tenant is additionally represented in claims/context. | Different `iss` per tenant. |
| Resource Server | Single issuer validator and tenant authorization. | Allow-list or multi-issuer resolver. |
| Federation | Shared OP configuration, per-tenant policy. | Independent federation endpoints/policies are easier to express. |
| Custom domain | Can use a shared domain or alias. | Can have a per-tenant issuer hostname. |
| Compliance | Suitable when sharing a trust boundary is acceptable. | Supports logical issuer separation; physical isolation must still be designed separately. |
| Key rotation | Usually coordinated centrally. | Can rotate per tenant. |
| Operations | Fewer metadata documents, keys, and endpoints. | More issuers and configurations to manage. |
| Tenant onboarding/offboarding | Usually creating/configuring a tenant within one OP. | Needs creating/retiring the corresponding issuer and trust configuration. |
| Blast radius | A shared key/policy error can affect all tenants. | Can be bounded by issuer if infrastructure is also appropriately separated. |

### 4.2. Choose a Single Issuer When

A single issuer is usually a reasonable choice if:

- All tenants belong to the same organization or the same trust domain.
- Clients can determine the tenant from tenant context, business domain, or client registration.
- Tenants do not need to own a dedicated issuer identifier.
- Key management and signing policies can be managed centrally.
- Discovery, federation, and onboarding should be unified.
- Resource Servers can check the tenant claim and access permissions after verifying the token.

Example: an order-management SaaS serving multiple businesses. All businesses log in through the same platform, use the same OP identity, and share the same MFA policy. Tokens carry `tenant_id`, while the API checks whether the user has permissions on the requested tenant.

### 4.3. Choose Multiple Issuers When

A per-tenant issuer is appropriate if:

- A tenant needs an independent trust relationship/federation with the OP.
- A tenant requires a dedicated issuer URL in its OIDC client configuration.
- A tenant needs signing keys under its own control or independent key rotation.
- A tenant has significantly different authentication, token lifetime, or consent policies.
- A tenant needs to offboard/retire trust without affecting other tenants' issuers.
- Downstream systems distinguish tenants by issuer and cannot rely solely on claims.
- Contractual/compliance regulations require separate issuer identities.

Example: Acme requires a dedicated issuer to configure enterprise federation, place its public key into a separate trust store, and accept only tokens with Acme's `iss`.

### 4.4. Do Not Use Multiple Issuers Just to Replace a Tenant Claim

If all tenants still use the same policies, same keys, same client registry, and same trust relationship, creating separate issuers can significantly increase costs:

- Discovery metadata and JWKS must be served separately.
- Clients and Resource Servers must configure multiple issuers.
- Monitoring, key rotation, and incident response become more complex.
- Each issuer may require separate client/authorization data.

If the requirement is only to distinguish tenants in business logic, a tenant claim combined with authorization policies is usually simpler.

### 4.5. Do Not Use a Single Issuer When True Trust Isolation Is Needed

Conversely, if a tenant requires a separate trust store, separate signing keys, separate federation metadata, and the ability to revoke trust independently, simply adding `tenant_id` to the token may not meet the requirement. In that case, multiple issuers or separate deployments are needed according to the committed isolation level.

## 5. Single-Issuer Model: Designing Tenant Context

### 5.1. Tenant Context Must Be Determined Before Protocol Processing

With a shared single issuer, the server needs to determine the tenant on each request to apply the right:

- Allowed client list.
- Login and MFA policies.
- User consent and permissions.
- Tenant claim placed into tokens.
- Branding or login UI.
- Rate limits, quotas, and auditing.

Tenant context must be available before endpoints authenticate clients, read authorizations, or mint tokens. Do not wait until adding claims to determine the tenant.

### 5.2. Sources for Determining the Tenant

| Source | How it is used | Risks/controls |
| --- | --- | --- |
| Registered hostname | `acme.login.example.com` maps to tenant Acme. | Trust host only after proxy normalization and allow-list check. |
| Fixed path | `/t/acme/oauth2/authorize`. | Normalize path, block path traversal and route ambiguity. |
| Client registration | Client ID belongs to a defined tenant. | Client lookup must be tenant-aware; do not trust only the client ID sent by the caller. |
| User membership | User selects a tenant after login. | Verify membership and permission to switch tenants. |
| Trusted gateway assertion | Internal gateway passes signed/authenticated tenant context. | Trust headers only from an authenticated gateway; strip client-sent headers. |

Do not take the tenant directly from a query parameter like `?tenant=acme` and immediately use it for persistence lookups. A query parameter can serve as a UI hint, but the server must verify the allowed tenant against host, client, user, or trusted routing policy.

### 5.3. Hostnames and Forwarded Headers

If using hostnames:

1. Use an allow-list mapping canonical hostnames to tenant IDs.
2. Reverse proxies must strip client-supplied `Forwarded`/`X-Forwarded-Host` headers and set trusted values.
3. Trust forwarded headers only from authenticated proxies/gateways.
4. Normalize hostname, port, trailing dot, and letter casing using a single consistent rule.
5. Unknown hosts must be rejected; do not fall back to a default tenant.
6. Do not construct an arbitrary issuer by concatenating strings from the `Host` header.

If an attacker can control the hostname used to construct the issuer, the Authorization Server risks issuing tokens with an unexpected issuer or advertising wrong endpoints.

### 5.4. Tenant Context Must Be Scoped to the Request

Example model:

~~~java
public record TenantContext(
    String tenantId,
    String issuer,
    TenantPolicy policy
) {}
~~~

A filter resolves the tenant from the normalized request:

~~~java
TenantContext tenant = tenantResolver.resolve(request);
if (tenant == null) {
    response.sendError(404);
    return;
}

try (TenantContextScope ignored = tenantContext.bind(tenant)) {
    filterChain.doFilter(request, response);
}
~~~

This is pseudocode. `TenantContextScope` must ensure the context is cleared in `close()`/`finally`, even if authentication fails or downstream throws an exception. For async processing, executors, or reactive flows, propagate the context through the appropriate mechanism; do not rely solely on `ThreadLocal`.

### 5.5. Tenant Claims and Authorization

With a shared single issuer, a token may contain:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-123",
  "aud": "orders-api",
  "tenant_id": "acme",
  "scope": "orders.read"
}
~~~

The Resource Server needs to verify:

- Valid signature and issuer.
- Audience contains the target API.
- Token is not expired and has not been revoked according to the mechanism used by the API.
- Tenant claim has a valid value.
- Principal has permissions on the requested tenant.
- The accessed resource belongs to the corresponding tenant.

Do not treat `tenant_id` as an access permission by itself. The claim only indicates which tenant context the token was issued in; the API must still enforce authorization and tenant boundaries on every data operation.

### 5.6. Tenant Context Must Be Bound to Client and User

In a shared single issuer, client IDs may be globally unique or unique only within a tenant. If a client ID is unique only within a tenant, the repository must look up by the `(tenant_id, client_id)` pair. Do not use a default global client ID repository if collisions across tenants are possible.

When a user has membership in multiple tenants, the specific tenant context must be determined for the authorization transaction. Do not let a login session in tenant A automatically issue tokens for tenant B without proper membership/consent checks.

## 6. Multi-Issuer Model: Routing Issuers by Tenant

### 6.1. The Issuer Registry Must Be Server-Managed

Maintain a trusted tenant registry:

| tenant_id | issuer | hostname | status |
| --- | --- | --- | --- |
| `acme` | `https://acme.login.example.com` | `acme.login.example.com` | ACTIVE |
| `fabrikam` | `https://fabrikam.login.example.com` | `fabrikam.login.example.com` | ACTIVE |
| `northwind` | `https://northwind.login.example.com` | `northwind.login.example.com` | ACTIVE |

The registry can be stored in a configuration service or administration database. Do not accept an arbitrary issuer URL from a request to fetch metadata or use as the issuer context.

### 6.2. Resolve the Issuer Before Processing Endpoints

General flow:

1. Receive the request and determine the canonical host/path.
2. Look up the tenant registry entry.
3. Verify the tenant is ACTIVE and the hostname belongs to that issuer.
4. Load the tenant-specific Authorization Server configuration.
5. Bind the issuer context for the duration of the request.
6. Run protocol endpoints and core services in the right tenant namespace.
7. Clear the context after the request.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OIDC Client
    participant P as Reverse Proxy
    participant R as Tenant Registry
    participant AS as Authorization Server
    participant S as Tenant Services
    C->>P: Request to acme.login.example.com
    P->>AS: Forward normalized host
    AS->>R: Resolve canonical host
    R-->>AS: Tenant Acme + issuer + policy
    AS->>AS: Bind tenant/issuer context
    AS->>S: Resolve client, authorization, keys
    S-->>AS: Tenant Acme data
    AS-->>C: Response with Acme issuer
~~~

### 6.3. A Single Multi-Issuer Deployment Needs Tenant-Aware Components

Spring Authorization Server 1.5.8 provides `AuthorizationServerSettings` to configure the issuer and endpoint settings. The `.issuer(...)` configuration is typically declared as a shared bean. Declaring only a single static bean configures a single issuer for that server context.

To serve multiple issuers in a single deployment, the application must have a routing layer and tenant-aware components. Approaches include:

- One Authorization Server application context/filter chain per issuer.
- Tenant-specific runtime/configuration selected before endpoints process the request.
- Decorators for core services, JWK source, and issuer context to delegate to the right tenant.
- Multiple separate deployments if stronger operational boundaries are required.

Do not simply read the `Host` header and replace `iss` in the JWT. Discovery, endpoint URLs, token generators, JWK source, client authentication, authorization store, and issuer validation must all use the same tenant context.

### 6.4. Tenant Runtime

A configuration model can be expressed as:

~~~java
public record TenantAuthorizationServerRuntime(
    String tenantId,
    AuthorizationServerSettings settings,
    RegisteredClientRepository clients,
    OAuth2AuthorizationService authorizations,
    OAuth2AuthorizationConsentService consents,
    JWKSource<SecurityContext> jwkSource
) {}
~~~

The application maintains a registry from validated tenant ID/issuer to the corresponding runtime. Adapters use the current context to delegate:

~~~java
RegisteredClient findByClientId(String clientId) {
    TenantAuthorizationServerRuntime runtime =
        tenantRuntimeRegistry.requireCurrent();
    return runtime.clients().findByClientId(clientId);
}
~~~

This is pseudocode illustrating the pattern, not a complete configuration ready to copy into an application. Check the APIs and lifecycle of the exact Spring Authorization Server version in use, especially how `AuthorizationServerContext` is established, how `AuthorizationServerSettings` is resolved, and filter ordering.

### 6.5. AuthorizationServerContext and the Issuer

Spring Authorization Server uses `AuthorizationServerContext` to supply the issuer/settings to request-processing components. In a single-issuer model, the framework can use static settings configuration.

In a multi-issuer model, the request needs the right context before components generate discovery metadata, authorization responses, or tokens. If extending the context per tenant, you must:

- Resolve the tenant from a trusted registry.
- Bind the context before endpoints/providers that need the issuer.
- Prevent components from falling back to a default issuer when the tenant is invalid.
- Clear the context after the request.
- Ensure the context does not leak to another thread or subsequent request.
- Test concurrent requests for two issuers in the same process.

If you cannot guarantee these conditions with stable extension points, using separate application contexts/filter chains or separate deployments per issuer is safer and easier to test.

### 6.6. Do Not Unintentionally Share a Single JWK Source

Each issuer must publish a JWKS corresponding to the signing keys that issuer uses to sign tokens. If tenants require separate keys:

- Separate key aliases in HSM/KMS by tenant.
- Separate the JWK Set and `kid` namespace.
- Separate key rotation/revocation permissions.
- Do not let Acme's issuer return public keys used to verify Fabrikam's tokens if policy requires isolation.
- Audit key activation/retirement per tenant.

If multiple issuers intentionally share keys, you must still ensure `iss` is verified accurately. Sharing keys does not turn two issuers into a single issuer.

## 7. Partitioning Core Services and Data by Tenant

### 7.1. RegisteredClientRepository

`RegisteredClientRepository` defines `findById`, `findByClientId`, and `save`; the API does not take a separate tenant parameter. With a shared single issuer where client IDs overlap across tenants, a custom repository must obtain the tenant from the validated context and query by the tenant/client pair.

Example schema:

~~~sql
CREATE TABLE oauth2_registered_client (
    tenant_id varchar(100) NOT NULL,
    id varchar(100) NOT NULL,
    client_id varchar(200) NOT NULL,
    client_secret varchar(500),
    client_settings text NOT NULL,
    token_settings text NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, client_id)
);
~~~

This DDL only illustrates the composite key. Verify against the full `RegisteredClient` schema, column lengths, unique constraints, and mapper in use. If tenants have globally unique client IDs, a global unique key can be used, but you must still verify which tenant the client belongs to.

### 7.2. OAuth2AuthorizationService

Authorizations must be bound to the tenant from creation:

- Authorization ID belongs to the tenant namespace.
- `RegisteredClient` ID must reference a client in the same tenant.
- Token lookups must be tenant-aware.
- `findById` and `findByToken` must not return authorizations belonging to another tenant.
- Refresh/revoke/introspection must use the same resolved tenant context.

A shared schema can add `tenant_id` and indexes starting with the tenant ID. Example:

~~~sql
CREATE INDEX idx_authorization_tenant_id
    ON oauth2_authorization (tenant_id, id);
~~~

Illustrative indexes must match real queries. A `tenant_id` column in the row is not enough if a query or repository forgets to include the tenant condition.

### 7.3. OAuth2AuthorizationConsentService

Consents are looked up by `RegisteredClient` ID and principal name. With a shared single issuer, ensure the internal client ID already belongs to the right tenant. If the same principal name exists in multiple tenants, the consent key needs a tenant namespace in storage/custom service.

Do not use email as a tenant-independent principal key if emails can be reused or changed. Choose an immutable subject/user ID appropriate to the identity model.

### 7.4. Shared Database or Separate Databases?

| Persistence model | Benefits | Drawbacks |
| --- | --- | --- |
| Shared tables + `tenant_id` | Easy operations, centralized migrations and connection pooling. | Every query must be tenant-scoped; a missing predicate can cause cross-tenant data leaks. |
| Separate schema per tenant | Better namespace and access permission separation. | Complex migrations, connection routing, and schema lifecycle. |
| Separate database per tenant | Strong data boundary, independent backup/restore and residency. | High operational, connection pool, monitoring, and migration costs. |
| Hybrid | Large/special tenants get dedicated DBs; others use a shared schema. | Requires unified abstraction and routing. |

The issuer model and the database model are two separate decisions. A single issuer can use separate databases per tenant; multiple issuers can also share a database with a tenant ID column. Make each decision based on trust and data isolation requirements.

### 7.5. Row-Level Security and Connection Pools

If the database supports Row-Level Security (RLS), policies can add an extra layer of protection for tenant-scoped tables. However:

- Tenant context must be set via a reliable mechanism within the transaction.
- Session variables must be reset properly when returning connections to the pool.
- Prevent subsequent requests from inheriting the previous request's tenant ID.
- Application roles must not have unintentional privileges to bypass RLS.
- Test native queries, batch jobs, and migration accounts as well.

RLS is an additional defense layer, not a replacement for tenant predicates in repositories and authorization policies.

## 8. Discovery, Endpoints, and Token Validation

### 8.1. Discovery Metadata Must Match the Issuer

With a shared single issuer, the discovery document advertises the shared issuer and shared endpoints.

With multiple issuers, each discovery document must advertise the exact tenant issuer and corresponding endpoints. Never return Acme's discovery document for a request resolved as Fabrikam.

Verify:

- `issuer` matches the tenant issuer exactly.
- `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `userinfo_endpoint`, and other endpoints belong to the right issuer.
- TLS certificate/hostname matches the public issuer URL.
- Endpoint URLs are not built from an arbitrary `Host` header.
- Metadata caches are namespaced by issuer and invalidated when configuration changes.

### 8.2. Issuer Paths and Hostnames

Two common URL styles:

~~~text
https://acme.login.example.com
https://login.example.com/issuers/acme
~~~

Dedicated hostnames are usually easier to observe and map to TLS. Path-based issuers can reduce the number of hostnames but require reverse proxies, discovery well-known URLs, and endpoint routing to handle paths consistently according to the specification.

Do not construct well-known URLs manually via string concatenation while ignoring discovery rules when the issuer has a path. Use standards-compliant libraries/clients and test the URLs advertised externally through the proxy.

### 8.3. Clients Must Bind Authorization Requests to the Issuer

When a client supports multiple issuers, each authorization transaction needs to record the expected issuer. The client must verify the issuer in the response according to the protocol and mix-up protection mechanisms it supports.

Do not select the issuer solely from a callback or state parameter sent by the caller without matching it against the initial authorization request. For OIDC, the client must also verify that `iss` in the ID Token matches the selected issuer.

An OAuth 2.0 Authorization Server can support the issuer response parameter per RFC 9207 so clients can distinguish authorization servers in multi-issuer environments. Verify client and framework/version support before relying on it; do not assume every client checks this parameter.

### 8.4. Resource Servers Verifying Multiple Issuers

If an API accepts tokens from multiple issuers, the Resource Server needs a resolver pointing to an `AuthenticationManager`/decoder corresponding to each trusted issuer. The issuer list must be governed:

~~~java
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://acme.login.example.com",
        "https://fabrikam.login.example.com",
        "https://northwind.login.example.com"
    );
~~~

This snippet illustrates the issuer allow-list pattern with Spring Security. Do not use a resolver that accepts any arbitrary issuer taken from the `iss` claim and automatically fetches discovery metadata. If an attacker can supply an issuer URL they control, the Resource Server can suffer SSRF or trust malicious keys.

After verifying the issuer, the Resource Server must still check audience, scopes/authorities, tenant binding, and permissions on the resource.

### 8.5. Coexistence of Issuer and Tenant Claims

With multiple issuers, tokens can still carry a tenant claim for API authorization:

~~~json
{
  "iss": "https://acme.login.example.com",
  "sub": "user-123",
  "aud": "orders-api",
  "tenant_id": "acme",
  "scope": "orders.read"
}
~~~

Verify that `tenant_id` is consistent with the issuer-to-tenant mapping. If a token has Acme's `iss` but a tenant claim of Fabrikam, reject it or handle it according to an explicit policy; do not arbitrarily pick one of the two values.

## 9. Key Management and Security

### 9.1. Single Issuer: One Key or Multiple Keys?

A shared single issuer can use:

- One shared signing key set across all tenants.
- Multiple keys within the same JWKS, still belonging to one issuer.
- Per-tenant key aliases in an HSM, while the issuer's JWKS publishes the appropriate public keys.

The choice depends on policy. If all tokens share an issuer and Resource Servers only trust the issuer, compromise of one key published by the issuer can affect trust for the entire issuer.

### 9.2. Multiple Issuers: Separate Keys

With separate issuers, you can:

- Give each tenant its own signing keys.
- Let tenants manage key rotation independently.
- Scope operator permissions by tenant.
- Revoke or retire one tenant's key without changing other tenants' keys.

The key store must be namespaced by tenant/issuer. Do not use `kid` alone as a global key lookup if `kid` values can collide across issuers; the issuer + `kid` pair determines the key context.

### 9.3. Do Not Infer the Issuer from kid

`kid` is only a key identifier within the scope of the selected JWK Set/key source. Do not use `kid` to decide the tenant or issuer. The safe sequence is:

1. Resolve the issuer from trusted request/client configuration.
2. Select issuer-specific metadata/JWKS.
3. Select the key by `kid` within that JWKS.
4. Verify the signature and claims.

### 9.4. TLS, Domains, and DNS

Per-tenant custom domains/hostnames require:

- Domain ownership verification before attaching to a tenant.
- TLS certificates matching the hostname.
- Protection against domain takeover when a tenant offboards.
- Controls over CNAME/DNS changes.
- Preventing tenants from pointing an issuer to an unverified hostname.
- Keeping the issuer stable once clients have configured trust.

Do not delete DNS/TLS mappings before completing issuer retirement and handling active tokens/clients.

## 10. Tenant Lifecycle and Issuer Changes

### 10.1. Tenant Onboarding

With a shared single issuer:

1. Create the tenant record and tenant policy.
2. Configure hostname/path or tenant selection mechanism.
3. Provision clients in the tenant namespace.
4. Set up user memberships, consents, and quotas.
5. Configure Resource Server/API tenant authorization.
6. Test that tokens contain the expected tenant claim.

With multiple issuers:

1. Create the tenant record and canonical issuer identifier.
2. Verify domain and TLS.
3. Provision signing keys/HSM alias.
4. Create discovery metadata and JWKS endpoint.
5. Configure client registry, authorization, and consent store.
6. Add the issuer to Resource Server trusted issuer allow-lists.
7. Test discovery, authorization, token validation, logout, and key rotation.

### 10.2. Issuers Should Not Change Arbitrarily

Clients use the issuer as a trust identifier. Changing the hostname or path can cause:

- Old discovery URLs to stop working.
- Clients to reject ID Tokens due to `iss` changes.
- Resource Servers to stop trusting newly issued tokens.
- Logout/session management to fail to locate the right OP.
- Federation trust to break.

If an issuer must change, treat it as a protocol migration. Publish a plan, support old and new issuers in parallel during the transition window, update clients/resource servers, and wait for old tokens to expire or revoke them per policy.

### 10.3. Migrating from Single Issuer to Multiple Issuers

A migration plan can include:

1. Identify which tenants need dedicated issuers and why.
2. Create the new issuer, key set, discovery metadata, and storage namespace.
3. Configure Resource Servers to trust both the old and new issuers during migration.
4. Update OIDC clients with the new issuer and redirect URIs.
5. Re-authenticate or re-issue tokens under the new issuer.
6. Do not modify the `iss` claim of already-issued tokens to simulate the new issuer.
7. Wait for old tokens to expire or handle revocation.
8. Remove the old issuer from the allow-list when no dependencies remain.

### 10.4. Migrating from Multiple Issuers to a Single Issuer

The reverse process follows the same pattern:

- Choose the new canonical issuer.
- Configure tenant claims and tenant authorization.
- Update client discovery/trust configuration.
- Re-issue tokens under the shared issuer.
- Keep validating the old issuer for the necessary transition period.
- Retire old keys/endpoints once tokens expire and logout/session policies are satisfied.

You cannot change `iss` on a stored token while preserving its signature. Tokens must be re-issued.

### 10.5. Tenant Offboarding

Offboarding must handle:

- Blocking new logins and client authentication.
- Revoking/disabling clients.
- Revoking authorizations/tokens per policy.
- Invalidating refresh tokens and sessions.
- Removing the issuer from discovery/trusted issuers when appropriate.
- Retaining audit/retention data as required.
- Safely cleaning up custom domain/TLS/DNS.
- Confirming other tenants are unaffected.

With a shared single issuer, never disable the entire issuer just to offboard one tenant. With separate issuers, retiring an issuer still requires handling tokens and clients already in circulation.

## 11. Common Pitfalls

### Pitfall 1: Confusing Tenant ID with Issuer

**Symptom:** Tokens have a tenant claim, but client validation uses that claim instead of `iss`.

**Cause:** Failing to distinguish tenant context from OP identity.

**Fix:** Verify the issuer against discovery/trust configuration; use the tenant claim for authorization afterward.

### Pitfall 2: Using a Single Issuer Without Enforcing Tenant in Authorization

**Symptom:** Users from tenant A can access resources in tenant B.

**Cause:** The API only checks signatures and scopes, ignoring tenant boundaries.

**Fix:** Bind the tenant claim, client, principal, and resource in authorization policies.

### Pitfall 3: Selecting the Tenant from an Untrusted Host Header

**Symptom:** Attackers send `Host`/`X-Forwarded-Host` to access another tenant or forge an issuer.

**Cause:** Trusting headers from the Internet or concatenating the host directly into the issuer.

**Fix:** Normalize at a trusted proxy, allow-list hostnames, and look up the tenant registry.

### Pitfall 4: Multiple Issuers Sharing a Non-Tenant-Aware Client Registry

**Symptom:** Duplicate client IDs across tenants return the wrong `RegisteredClient` or validate against another tenant's secret.

**Cause:** The repository only queries by global client ID.

**Fix:** Separate repositories or add a tenant/issuer namespace and appropriate unique constraints.

### Pitfall 5: One Tenant's Discovery Returning Another Tenant's Issuer

**Symptom:** Clients fetch metadata, but ID Tokens are rejected due to an `iss` mismatch.

**Cause:** Tenant routing and issuer context are inconsistent.

**Fix:** Test discovery, endpoint URLs, and token `iss` on every tenant hostname/path.

### Pitfall 6: Unintentionally Sharing a JWK Source

**Symptom:** A tenant sees another tenant's public keys or key rotation affects the wrong scope.

**Cause:** Key source is not tenant-aware.

**Fix:** Namespace keys by issuer/tenant and enforce HSM/KMS permissions.

### Pitfall 7: Resource Server Automatically Trusting Any Issuer

**Symptom:** The API fetches discovery/JWKS from an issuer supplied in an attacker's token.

**Cause:** Missing trusted issuer allow-list.

**Fix:** Maintain a trusted issuer registry; never let an arbitrary `iss` claim determine outbound URLs.

### Pitfall 8: Tenant Context Leaking Across Requests

**Symptom:** A subsequent request is processed under the previous request's tenant.

**Cause:** `ThreadLocal` is not cleared or async context is not propagated properly.

**Fix:** Use a scope with `try`/`finally`, clear the context, and test thread reuse/concurrency.

### Pitfall 9: Adding tenant_id to the Database Only While Forgetting Queries

**Symptom:** Repositories return authorizations/clients/consents from another tenant.

**Cause:** Queries lack the tenant predicate or unique constraints are incorrect.

**Fix:** Use tenant-aware repositories, composite keys/indexes, supplementary RLS, and negative cross-tenant tests.

### Pitfall 10: Changing the Issuer Without Migrating Clients

**Symptom:** Clients/resource servers reject tokens after rollout.

**Cause:** `iss` and discovery URLs changed while trust configurations remained old.

**Fix:** Perform an issuer migration with a dual-trust phase, re-issue tokens, and retire the old issuer as planned.

## 12. Test Matrix

| Case | Expected outcome |
| --- | --- |
| Single issuer, tenant Acme | Discovery and tokens both use the shared issuer; tenant claim is Acme. |
| Single issuer, tenant Fabrikam | Same issuer; cannot read Acme's clients/authorizations. |
| Non-existent tenant | Request is rejected; no fallback to a default tenant. |
| Forged Host header | Cannot switch tenant/issuer via untrusted headers. |
| Trusted proxy forwarded host | Maps to the canonical hostname accurately. |
| Multi-issuer Acme discovery | Issuer and endpoints belong to Acme. |
| Multi-issuer Fabrikam discovery | Issuer and endpoints belong to Fabrikam. |
| Acme token sent to Fabrikam-only validator | Rejected due to issuer mismatch. |
| Token with Acme `iss` but Fabrikam `tenant_id` | Rejected by tenant/issuer consistency policy. |
| Duplicate client ID across tenants | Repository returns the right client for the tenant context or rejects collision. |
| Token lookup collision/namespace overlap | Does not return another tenant's authorization. |
| Consent lookup | Returns only consent matching tenant/client/principal. |
| Acme key rotation | Does not alter Fabrikam's key set. |
| Unknown issuer in JWT | Resource Server rejects it; does not fetch arbitrary issuers. |
| Tenant context with thread reuse | Subsequent request does not inherit previous context. |
| Concurrent requests for two issuers | Discovery/tokens do not mix issuer contexts. |
| Tenant offboarding | Clients/tokens/issuer handled per policy while other tenants stay operational. |
| Issuer migration | Clients/resource servers validate issuers across transition phases. |
| JWT local validation | Revocation on the Authorization Server is not mistaken for automatic JWT revocation at the API. |

## 13. Production Checklist

| Item | Question to confirm |
| --- | --- |
| Issuer decision | Is there a clear rationale for single issuer vs. multiple issuers? |
| Trust boundary | Which tenants share a trust domain and which require separation? |
| Canonical issuer | Are issuer URLs stable, HTTPS, and centrally managed? |
| Tenant resolution | Is host/path/client/user context validated before endpoints? |
| Proxy | Are forwarded headers stripped/overwritten at the trusted proxy? |
| Unknown tenant | Are requests with unresolved tenants rejected without fallback? |
| Discovery | Do metadata issuer/endpoints/JWKS match the tenant context? |
| Token claims | Are `iss`, `aud`, tenant claim, and client binding consistent? |
| Client registry | Do lookups and unique constraints have tenant/issuer scope? |
| Authorization store | Can `findById`/`findByToken` never read across tenants? |
| Consent | Is the key namespaced by client, principal, and tenant? |
| Signing keys | Do key/JWK sources and rotation permissions match boundaries? |
| Resource Server | Are only allow-listed issuers trusted? |
| Persistence | Does shared schema, separate schema, or separate DB match isolation requirements? |
| RLS | Is session context safely set/reset if used? |
| Cache | Are cache keys namespaced by tenant/issuer with proper invalidation? |
| Logout/session | Are logout and session state scoped by issuer/tenant? |
| Migration | Is there a dual-trust and token re-issuance plan if changing issuers? |
| Offboarding | Is there a procedure to revoke, retire issuers, and handle custom domains? |
| Observability | Do logs/metrics include safe tenant IDs without tokens/secrets? |
| Tests | Are there negative cross-tenant and multi-issuer concurrency tests? |

## 14. Practice Exercise

A SaaS platform has three tenants:

- Acme requires a dedicated issuer, signing keys in a separate HSM, and OIDC federation with its IdP.
- Fabrikam and Northwind share a login UI, MFA policy, and Resource Server; they only require business data separation.
- The system currently has one Spring Authorization Server deployment, PostgreSQL, and three instances running behind a reverse proxy.

Design the architecture:

1. Choose the issuer model for each tenant and explain why.
2. Define canonical issuer URLs, hostnames, and discovery endpoints.
3. Design the tenant registry and trusted host mapping.
4. Decide what is shared and what is separated for `RegisteredClient`, authorization, consent, and signing keys.
5. Design a tenant-aware repository when client IDs can overlap across tenants.
6. Describe how to bind the issuer context in a request and clear it safely.
7. Design the Resource Server validator for Acme's issuer and the shared Fabrikam/Northwind issuer.
8. Define claims and authorization checks to prevent Fabrikam from accessing Northwind resources.
9. Design key rotation for Acme without affecting the other two tenants.
10. Write tests for `Host`/`X-Forwarded-Host` spoofing, issuer mismatch, and tenant context leakage.
11. Plan how to support Fabrikam if it later requests a dedicated issuer as well.
12. Define the process to offboard Acme while keeping Fabrikam/Northwind services operational.

**Acceptance criteria:** Issuers accurately reflect trust boundaries; tenants are resolved from trusted sources; discovery, token `iss`, JWK source, and persistence all use the same tenant context; Resource Servers only trust allow-listed issuers; tests prove there is no cross-tenant access.

## 15. References

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Issuer Identifier and Provider Configuration metadata.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token issuer, audience, and validation.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer and authorization server metadata.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer identification in authorization responses to support mix-up protection.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): configuring Authorization Server endpoints and settings.
- [Spring Authorization Server 1.5.8 — AuthorizationServerSettings Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.html): issuer and endpoint settings.
- [Spring Authorization Server 1.5.8 — AuthorizationServerContext Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/context/AuthorizationServerContext.html): context providing issuer and settings.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, authorization, consent, and service contracts.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer validation, and Resource Server configuration.
- [Spring Security — Multitenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): routing multiple issuers to `AuthenticationManager` in Resource Server.
