# Configuring and Resolving Issuers for Multitenancy

> **Chapter: Multitenancy.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module and covers designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot. It focuses on the model where multiple tenants share a single host with **separate issuers**, how Spring Authorization Server resolves the issuer from a request, how components are routed per tenant, and how to ensure data, signing keys, client registrations, and authorizations are never crossed.

## 1. The Issuer Is the Identity Boundary of the Authorization Server

An Issuer Identifier identifies the Authorization Server/OpenID Provider. In OIDC, the `iss` claim in an ID Token must identify the OP that issued the token; in OAuth 2.0, metadata advertises the issuer and corresponding protocol endpoints.

In a single-tenant system, the issuer is typically fixed:

~~~text
https://login.example.vn
~~~

When serving multiple tenants, an organization may need an independent issuer for each tenant:

| Tenant | Issuer | Can Client IDs overlap? |
|---|---|---|
| Company A | `https://auth.example.vn/acme` | Yes, if registrations are isolated |
| Company B | `https://auth.example.vn/contoso` | Yes, if registrations are isolated |
| Partner C | `https://auth.example.vn/partner-c` | Yes, if registrations are isolated |

An issuer is not just a display URL. It is used in discovery metadata, ID Tokens, access tokens depending on configuration, Resource Server validation, and client trust relationships. Selecting the wrong tenant can cause clients to receive tokens from the wrong trust domain or allow one tenant to access another tenant's clients, authorizations, consents, or signing keys.

**Principle:** a tenant must be resolved from a system-controlled identifier, and that same identifier must be used to select the issuer, data, signing keys, and policies. Never select a tenant by trusting an arbitrary tenant field in the request body.

## 2. Three Common Multi-Tenancy Models

Not every multi-tenant application needs multiple issuers. Choose a model based on security boundaries and the contract clients require.

| Model | Issuer | How tenants are separated | Best suited when |
|---|---|---|---|
| Dedicated deployment/domain | A dedicated issuer per deployment/host | Infrastructure and data are separated | Large tenants, strict isolation requirements, or divergent configurations |
| Shared host, path-based issuer | Each tenant has its own issuer path, e.g. `/acme` | Request path resolves the issuer | Multiple tenants share a runtime but need separate discovery, keys, and client registries |
| Shared issuer, tenant claim | One shared issuer for all | Tenant is a claim/context in authorization and API policies | Tenants are only data/permission scopes within the same identity domain |

This lesson focuses on the **shared host, path-based issuer** model, which Spring Authorization Server supports directly via `multipleIssuersAllowed(true)`.

### 2.1. A Shared Issuer Does Not Mean Multiple Issuers

If all users trust the same `https://auth.example.vn` issuer and access tokens carry a `tenant_id` claim, the system still has **a single issuer**. Tenant isolation must then be enforced in the user store, authorizations, scopes, claims, Resource Server, and database queries.

Conversely, if each tenant has an issuer like `https://auth.example.vn/acme` or `https://auth.example.vn/contoso`, clients can discover and pin a separate OP per tenant. Each issuer needs appropriate metadata, JWK Set, and token validation.

Do not mix the two models by only changing a tenant claim and expecting the ID Token issuer to change automatically.

## 3. Resolving the Issuer by Path Component

Spring Authorization Server 1.5.8 supports multiple issuers on the same host via the path component of the issuer identifier. Example:

~~~text
https://auth.example.vn/acme
https://auth.example.vn/contoso
~~~

Each tenant's endpoints sit under its issuer base:

| Protocol endpoint | Tenant acme | Tenant contoso |
|---|---|---|
| Issuer | https://auth.example.vn/acme | https://auth.example.vn/contoso |
| Authorization | /acme/oauth2/authorize | /contoso/oauth2/authorize |
| Token | /acme/oauth2/token | /contoso/oauth2/token |
| JWK Set | /acme/oauth2/jwks | /contoso/oauth2/jwks |
| Revocation | /acme/oauth2/revoke | /contoso/oauth2/revoke |
| Introspection | /acme/oauth2/introspect | /contoso/oauth2/introspect |
| OIDC Provider Configuration | /acme/.well-known/openid-configuration | /contoso/.well-known/openid-configuration |

Example discovery request:

~~~http
GET /acme/.well-known/openid-configuration HTTP/1.1
Host: auth.example.vn
Accept: application/json
~~~

The returned metadata must advertise:

~~~json
{
  "issuer": "https://auth.example.vn/acme",
  "authorization_endpoint": "https://auth.example.vn/acme/oauth2/authorize",
  "token_endpoint": "https://auth.example.vn/acme/oauth2/token",
  "jwks_uri": "https://auth.example.vn/acme/oauth2/jwks",
  "revocation_endpoint": "https://auth.example.vn/acme/oauth2/revoke",
  "introspection_endpoint": "https://auth.example.vn/acme/oauth2/introspect"
}
~~~

This is an illustrative example. Public URLs must remain consistent with the reverse proxy, TLS termination, and the issuer resolved inside the application.

### 3.1. OIDC Provider Configuration and OAuth AS Metadata

OIDC Provider Configuration is typically discovered at:

~~~text
/{tenant}/.well-known/openid-configuration
~~~

OAuth 2.0 Authorization Server Metadata has its own well-known path rules, for example:

~~~text
/.well-known/oauth-authorization-server/{tenant}
~~~

Clients must use the metadata protocol they support. Never fetch an issuer from one metadata document and then retrieve a JWK Set from a different host outside the trust contract.

### 3.2. Request Flow by Issuer

~~~mermaid
flowchart TD
    A[HTTP request to issuer path] --> B[Spring Authorization Server resolves issuer]
    B --> C{Issuer in tenant registry?}
    C -->|No| D[Fail closed]
    C -->|Yes| E[AuthorizationServerContextHolder]
    E --> F[Delegating protocol component]
    F --> G[RegisteredClientRepository]
    F --> H[OAuth2AuthorizationService]
    F --> I[OAuth2AuthorizationConsentService]
    F --> J[JWKSource]
    G --> K[(Tenant A data / keys)]
    H --> K
    I --> K
    J --> L[Tenant A signing key set]
~~~

The issuer is resolved once during a protocol request and used to select the components for that same tenant. If the registry lookup finds no tenant, the request must stop at the registry step; it must never continue with default components.

## 4. Enabling Multiple Issuers in Spring Authorization Server

By default, support for multiple issuers on the same host is disabled. Enable it with `AuthorizationServerSettings.builder().multipleIssuersAllowed(true)`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .multipleIssuersAllowed(true)
                .build();
    }
}
~~~

Important notes:

- **Do not call** `.issuer("https://auth.example.vn")` in this multi-issuer configuration. Configuring a fixed issuer forces the Authorization Server to use one issuer, defeating per-request issuer resolution.
- `multipleIssuersAllowed(true)` only enables support for multiple issuers. It does not automatically create tenants, databases, client registries, signing keys, or authorization stores per tenant.
- The application must still build tenant-aware components and reject unregistered issuers.
- For single-tenant deployments, configuring a fixed issuer remains appropriate.

The issuer is resolved in the Authorization Server request context. While processing a protocol endpoint, the application can retrieve the context via `AuthorizationServerContextHolder`.

## 5. Retrieving the Current Issuer with AuthorizationServerContextHolder

Spring Authorization Server provides:

- `AuthorizationServerContext`: holds the issuer and authorization server settings for the current request.
- `AuthorizationServerContextHolder`: accesses the current context during request processing.

Example:

~~~java
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContext;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;

AuthorizationServerContext context =
        AuthorizationServerContextHolder.getContext();

if (context == null || context.getIssuer() == null) {
    throw new IllegalStateException("Authorization Server issuer is unavailable");
}

String issuer = context.getIssuer();
~~~

In a request with issuer `https://auth.example.vn/acme`, the context needs to resolve that issuer so components select the acme tenant configuration.

**Do not construct an issuer from untrusted headers.** A reverse proxy may only set `Forwarded`/`X-Forwarded-*` if the application accepts traffic solely from trusted proxies and the proxy strips client-supplied values. If the issuer depends on host/path, normalize the public URL and validate the route before using it as a tenant key.

### 5.1. Do Not Use the Request Context Outside the Request Lifecycle

`AuthorizationServerContextHolder` is scoped to the current request. Do not assume the context automatically propagates across async processing, messaging, or background jobs.

If a background task needs a tenant, pass the verified tenant ID/issuer as an explicit parameter, look it up again in the tenant registry, and check the tenant's status. Do not read the tenant from an old thread or store the context in a singleton.

## 6. Tenant Registry: Allowlisting Valid Issuers

Each issuer must be pre-registered in an application-controlled registry. The registry maps a **full, canonical issuer** to that tenant's component set.

Example model:

~~~java
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

record TenantComponents(
        RegisteredClientRepository clients,
        OAuth2AuthorizationService authorizations,
        OAuth2AuthorizationConsentService consents,
        JWKSource<SecurityContext> jwkSource) {
}
~~~

Illustrative registry:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContext;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.Assert;
import org.springframework.util.StringUtils;

@Component
final class TenantComponentRegistry {

    private final Map<String, TenantComponents> tenants =
            new ConcurrentHashMap<>();

    public void register(String issuer, TenantComponents components) {
        Assert.hasText(issuer, "issuer must not be blank");
        Assert.notNull(components, "tenant components must not be null");

        TenantComponents previous = tenants.putIfAbsent(issuer, components);
        Assert.state(previous == null, "issuer is already registered");
    }

    public TenantComponents current() {
        AuthorizationServerContext context =
                AuthorizationServerContextHolder.getContext();

        Assert.state(context != null
                        && StringUtils.hasText(context.getIssuer()),
                "Current Authorization Server issuer is unavailable");

        // Exact full-issuer lookup: unknown issuer must fail closed.
        TenantComponents components = tenants.get(context.getIssuer());
        Assert.state(components != null,
                "No tenant is registered for the requested issuer");

        return components;
    }
}
~~~

The example uses the full issuer as the key, avoiding simple suffix matching like `endsWith("acme")`, which can misroute tenants with similarly structured identifiers. If mapping from a tenant slug to an issuer is needed, perform it during onboarding and store a canonical, unique mapping.

### 6.1. Why Is the Registry an Allowlist?

The registry both routes components and acts as an allowlist of valid issuers. If an issuer is not in the registry, the request must fail explicitly. Never create a new datasource, JWK URL, or tenant context simply because a request sent an arbitrary path.

Do not implement patterns like:

~~~java
// Unsafe: turns request data into a source for building connections or URLs.
String issuer = request.getRequestURL().toString();
String jwksUrl = issuer + "/oauth2/jwks";
~~~

This opens the door to issuer spoofing, SSRF, host-header poisoning, or creating unauthorized tenants.

## 7. Components That Must Be Tenant-Aware in Spring Authorization Server

The Spring Authorization Server multitenancy guide identifies four core components that must delegate by issuer:

| Component | Responsibility | Why tenant separation is required |
|---|---|---|
| `RegisteredClientRepository` | Stores/looks up OAuth client registrations | Client IDs, redirect URIs, auth methods, scopes, and settings belong to a tenant |
| `OAuth2AuthorizationService` | Stores/looks up authorizations and tokens | Authorization codes, access/refresh tokens, and grants must not mix across tenants |
| `OAuth2AuthorizationConsentService` | Stores user/client consents | Consents from tenant A must not apply in tenant B |
| `JWKSource<SecurityContext>` | Supplies signing keys/JWK Sets | Each issuer's tokens must be signed/verified according to its key policy |

Other components may also need tenant awareness depending on the system: user lookup/authentication, tenant-specific login/consent pages, auditing, rate limiting, branding, password/MFA policies, session store, email/SMS providers, and token customizers.

### 7.1. Delegating Components

Each core interface can be implemented via a composite/delegating adapter. The adapter gets the current tenant from the registry and forwards the call to the concrete implementation.

Example for `RegisteredClientRepository`:

~~~java
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

final class TenantAwareRegisteredClientRepository
        implements RegisteredClientRepository {

    private final TenantComponentRegistry registry;

    TenantAwareRegisteredClientRepository(TenantComponentRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void save(RegisteredClient registeredClient) {
        registry.current().clients().save(registeredClient);
    }

    @Override
    public RegisteredClient findById(String id) {
        return registry.current().clients().findById(id);
    }

    @Override
    public RegisteredClient findByClientId(String clientId) {
        return registry.current().clients().findByClientId(clientId);
    }
}
~~~

`JWKSource` adapter:

~~~java
import com.nimbusds.jose.KeySourceException;
import com.nimbusds.jose.jwk.JWK;
import com.nimbusds.jose.jwk.JWKSelector;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;

import java.util.List;

final class TenantAwareJWKSource implements JWKSource<SecurityContext> {

    private final TenantComponentRegistry registry;

    TenantAwareJWKSource(TenantComponentRegistry registry) {
        this.registry = registry;
    }

    @Override
    public List<JWK> get(
            JWKSelector selector,
            SecurityContext context) throws KeySourceException {
        return registry.current().jwkSource().get(selector, context);
    }
}
~~~

For `OAuth2AuthorizationService`, delegate `save`, `remove`, `findById`, and `findByToken`. For `OAuth2AuthorizationConsentService`, delegate `save`, `remove`, and `findById`. All methods must use the same tenant context with no fallback to a default store.

### 7.2. Separating Repositories Alone Is Not Enough

If `RegisteredClientRepository` is separated but `OAuth2AuthorizationService` is shared without a tenant discriminator, one tenant's tokens can still be looked up in another tenant. Similarly, if `JWKSource` shares private keys and the consent store is unpartitioned, issuers differ while trust boundaries remain mixed.

Verify the entire path: client authentication → authorization lookup → consent → token generation/signing → JWK publication → introspection/revocation → Resource Server validation.

## 8. Persistence Isolation Strategies by Tenant

There are three common options. Choose based on isolation level, tenant count, operational cost, and backup/restore requirements.

| Strategy | Implementation | Advantages | Trade-offs |
|---|---|---|---|
| Separate databases | Each tenant has its own `DataSource`/database | Strong isolation, independent backup/restore | Many connection pools and migrations |
| Separate schemas | Same DB server, dedicated schema per tenant | Balances isolation and operations | Must route schemas/connections safely |
| Shared tables + tenant key | Add tenant/issuer discriminator to every table and unique key | Minimal infrastructure, scales easily with tenant count | Every query, index, and transaction must be tenant-aware |

Spring Authorization Server provides JDBC implementations such as `JdbcRegisteredClientRepository`, `JdbcOAuth2AuthorizationService`, and `JdbcOAuth2AuthorizationConsentService`. You can create one instance per tenant and delegate by issuer.

Example configuring components with a dedicated `DataSource`:

~~~java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.client.JdbcRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;

TenantComponents createTenantComponents(
        DataSource dataSource,
        JWKSource<SecurityContext> tenantJwkSource) {

    JdbcTemplate jdbc = new JdbcTemplate(dataSource);

    RegisteredClientRepository clients =
            new JdbcRegisteredClientRepository(jdbc);

    OAuth2AuthorizationService authorizations =
            new JdbcOAuth2AuthorizationService(jdbc, clients);

    OAuth2AuthorizationConsentService consents =
            new JdbcOAuth2AuthorizationConsentService(jdbc, clients);

    return new TenantComponents(
            clients, authorizations, consents, tenantJwkSource);
}
~~~

This is an illustrative factory; inject the tenant's proper schema/migrations and transaction manager. Never create a `DataSource` from an unverified tenant slug.

### 8.1. Shared Tables Require Composite Uniqueness

If multiple tenants share tables, every record must carry a verified tenant/issuer ID. Unique constraints and indexes must include the tenant key wherever identifiers are only unique within a tenant:

- `(tenant_id, client_id)` for client registrations.
- `(tenant_id, authorization_id)` or an equivalent key for authorizations.
- `(tenant_id, registered_client_id, principal_name)` for consents.
- `(tenant_id, token_lookup_digest)` for token lookups if using a digest.
- Tenant discriminator in every update/delete/select.

Do not merely add `tenant_id` to Java objects while omitting the predicate in SQL. A single query missing a tenant filter can cause a cross-tenant data leak.

### 8.2. Tenant Context and Transactions

The tenant must be resolved before calling repositories and kept consistent throughout the transaction. Never switch tenants mid-request. For async or event-driven transactions, pass the tenant ID explicitly and re-verify it.

With schema-per-tenant, avoid changing `search_path` or schema context on a pooled connection without resetting it in a `finally` block. A connection returned to the pool with the old schema can cause the next request to read/write the wrong tenant.

## 9. Separate Signing Keys and JWK Sets per Issuer

Each issuer should have an explicit key policy. Isolating JWK Sets by tenant ensures:

- Tenant A does not publish Tenant B's public keys.
- ID Tokens and JWT access tokens are signed with keys belonging to the issuing issuer.
- Key rotation and compromise handling can occur per tenant.
- RPs discover the right issuer and download the corresponding JWK Set.

The JWK Set endpoint must delegate to the current tenant's `JWKSource`. Never select a key solely by a client-supplied `kid`; `kid` is only used to look up a key within the resolved issuer's key set.

### 9.1. Shared Keys or Separate Keys?

Using separate keys per tenant typically reduces blast radius and helps isolate trust. Sharing signing keys may simplify operations, but weakens isolation: compromising one key can affect every issuer sharing that key. If sharing intentionally, document an explicit threat model, key governance, and client trust policy.

Never generate a new random key pair on every application restart. Keys must be persisted in a KMS/HSM/keystore with a `kid`, algorithm, active/retired status, and rollover plan. All pods must use the same key set for the same tenant.

### 9.2. Token Claims and Issuer

When issuing a JWT/ID Token for a tenant, the `iss` claim must be the current tenant's issuer. An acme token must never carry the contoso issuer. RPs/Resource Servers must validate the exact issuer and signature using that issuer's JWK Set.

Never derive `iss` from user attributes, request bodies, or unverified upstream claims. The issuer is an Authorization Server-controlled property.

## 10. Static and Dynamic Tenants

### 10.1. Static Tenants at Startup

If the number of tenants is small and changes rarely, each tenant's configuration can be declared upfront, creating the corresponding `DataSource`/repositories/`JWKSource` at startup and registering them into the registry. The advantage is that configuration is reviewed and deployed with the application. The drawback is that adding a tenant may require configuration changes or a rollout.

### 10.2. Dynamic Tenants at Runtime

If tenants are onboarded frequently, a `TenantProvisioningService` with a dedicated workflow is needed:

1. Receive an onboarding request from an authenticated admin/control plane.
2. Verify that the tenant ID/slug does not already exist and conforms to naming policies.
3. Construct the canonical issuer from the configured public base URL and valid tenant slug.
4. Create the database/schema and run migrations.
5. Create the client repository, authorization service, and consent service.
6. Provision signing keys/JWK Set in KMS/HSM or a key store.
7. Atomically register all components into the registry.
8. Verify discovery metadata and tenant health.
9. Transition the tenant to active status once all components are ready.

Never add an issuer to the registry before the database and signing keys are ready. If part of provisioning fails, the tenant must stay in a pending/failed state and reject authorization requests.

### 10.3. Deactivating and Removing Tenants

When deactivating a tenant, define policies for clients, tokens, consents, signing keys, backups, and retention. Do not just delete the registry entry while requests are in flight.

A lifecycle process may include: stop accepting new authorization/token requests, drain in-flight requests, disable client registrations, revoke/expire tokens per policy, archive audit/backups, update discovery routing, and finally retire keys/data according to retention. Deleting a tenant is a high-impact administrative action requiring strict authorization and auditing.

## 11. Resolving Tenants on the Resource Server

A multi-issuer Authorization Server is only part of the system. The Resource Server must validate tokens against the right issuer, signing keys, audience, and policies.

If the Resource Server accepts JWTs from a known set of issuers, Spring Security supports `JwtIssuerAuthenticationManagerResolver` to select an authentication manager based on the issuer claim. Configure trusted issuers as an allowlist:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;

@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    JwtIssuerAuthenticationManagerResolver resolver =
            JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                    "https://auth.example.vn/acme",
                    "https://auth.example.vn/contoso");

    http.authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.authenticationManagerResolver(resolver));

    return http.build();
}
~~~

This example illustrates an issuer allowlist. Production also requires validating audience, expiry, algorithm, tenant-specific authorities, and resource policies.

**Never** fetch a JWK Set dynamically from an arbitrary `iss` in an unverified JWT. If dynamic issuers are allowed, check the issuer against a tenant repository/allowlist before creating a decoder or calling any URL; otherwise, you risk SSRF or trusting attacker-controlled tokens.

### 11.1. Resolving and Propagating Tenants

Spring Security distinguishes two tasks:

- **Resolve tenant:** determine the tenant from a verified issuer or trusted request context.
- **Propagate tenant:** pass the verified tenant context to downstream authorization/data access.

If the tenant is derived from a JWT claim, the Resource Server should only use that claim after signature and issuer validation succeed. If the tenant is determined from hostname/path, the API must use the same mapping and ensure the token's issuer/audience do not conflict with the route.

Tenant context should be enforced in service/repository policies, not merely stored in an internal header that a client could spoof.

### 11.2. JWTs and Opaque Tokens

One tenant may use JWTs while another uses opaque tokens/introspection. When choosing a strategy at request time, Spring Security provides `AuthenticationManagerResolver<HttpServletRequest>` to select `JwtAuthenticationProvider` or `OpaqueTokenAuthenticationProvider`.

Do not decide token format solely by checking whether the string contains dots. Use a controlled tenant registry/configuration and the proper validator for that issuer.

## 12. Protecting Tenant Boundaries

Multi-tenant bugs often arise when one component is configured properly while another falls back to a default context or shared state.

| Boundary | What to protect | Negative case |
|---|---|---|
| Issuer resolution | Exact issuer and canonical route | `/acme-evil` must not match `/acme` |
| Client registration | Client lookup within the current tenant | Acme client fails authentication at contoso |
| Authorization/token store | Token lookup/save/remove with tenant context | Tenant A token cannot be revoked/introspected from B |
| Consent | Consent keyed by tenant + client + principal | Acme consent must not be reused at contoso |
| JWKSource | Key set per issuer | Acme token fails verification with contoso's private key |
| User identity | Local user/tenant membership | A user in tenant A does not automatically have membership in B |
| Resource Server | Issuer, audience, scope, and tenant policy | Valid signature but wrong audience/tenant is rejected |
| Cache | Cache keys include issuer/tenant | Client/token metadata is never cached across tenants |
| Audit/logging | Tag verified tenant, redact secrets | Never log tokens and never misattribute tenant |
| Admin plane | Authorized tenant onboarding/deactivation | Callers cannot create issuers outside the allowlist |

### 12.1. Never Fall Back to a Default Tenant

If an issuer has no registered components, the request must fail. Never fall back to a default tenant's repository/`JWKSource`. Falling back can turn a routing bug into unauthorized access to another tenant's data.

### 12.2. Cache Keys Must Include Tenant Identity

If caching `RegisteredClient`, authorization, consent, JWK, or user profile objects, cache keys must include the tenant/issuer. For example, a cache key containing only `client_id=portal-web` can return acme's registration to a contoso request if both tenants use the same client ID.

### 12.3. Host and Forwarded Headers

If tenants are routed by subdomain, trust `Host`/`Forwarded` headers only from authenticated proxies/load balancers. Proxies must strip client-supplied headers and set canonical headers. Configure allowed hosts, TLS, and canonical external URLs; never let an attacker alter `X-Forwarded-Host` to change the issuer.

## 13. Multi-Issuer Test Matrix

| # | Scenario | Expected outcome |
|---|---|---|
| 1 | Call OIDC discovery for acme | Metadata issuer and endpoints belong to acme |
| 2 | Call OIDC discovery for contoso | Metadata issuer and endpoints belong to contoso |
| 3 | `multipleIssuersAllowed` not enabled | Tenant paths are not treated as supported multi-issuer endpoints |
| 4 | Fixed issuer configured simultaneously | Detected as single-issuer configuration, not deployed as multi-tenant |
| 5 | Issuer path not in registry | Rejected, no fallback |
| 6 | Path `/acme-evil` similar to `/acme` | Does not match wrong tenant |
| 7 | Duplicate Client ID across two tenants | Each tenant looks up its own registration |
| 8 | Acme client used on contoso issuer | Client authentication fails |
| 9 | Acme authorization code sent to contoso token endpoint | Cannot exchange code |
| 10 | Acme refresh token sent to contoso | Cannot refresh |
| 11 | Revoke acme token via contoso issuer | Does not alter acme authorization |
| 12 | Introspect acme token via contoso | Does not disclose acme token status |
| 13 | Acme consent looked up from contoso | Returns no consent |
| 14 | Acme JWK endpoint | Publishes only acme's JWK Set |
| 15 | Contoso JWK endpoint | Publishes only contoso's JWK Set |
| 16 | Verify acme token with contoso JWK | Signature/issuer validation fails |
| 17 | Acme token with forged contoso issuer | Resource Server rejects it |
| 18 | Valid issuer token with wrong audience | Resource Server rejects it |
| 19 | JWT issuer not in allowlist | Authentication fails; does not fetch arbitrary JWK URL |
| 20 | Client-forged `X-Forwarded-Host` | Does not alter public issuer |
| 21 | Registration cache with same client ID across tenants | Does not return cross-tenant data |
| 22 | JWK cache with same `kid` across tenants | Does not use wrong key |
| 23 | Dynamic tenant currently provisioning | Rejects requests until components are ready |
| 24 | Provisioning fails mid-way | Tenant stays inactive and unroutable |
| 25 | Two admins onboard the same slug | Unique constraint prevents duplicate tenants |
| 26 | Deactivate tenant with in-flight requests | Drain/deny per lifecycle policy; never route to another tenant |
| 27 | Pod A and Pod B serving same issuer | Use identical registry/config/keys/store for tenant |
| 28 | Background job without request context | Must pass tenant explicitly; never uses default tenant |
| 29 | Shared table query missing tenant predicate | Tests detect cross-tenant read/write |
| 30 | Database/schema pool reuses connection | Schema context is reset; no tenant leak |
| 31 | Acme user logs in at contoso | Rejected without membership |
| 32 | Acme token carries scope absent in contoso | Does not grant permissions based on another tenant's scope |
| 33 | Signing key rotation in acme | Does not impact contoso's JWK/keys |
| 34 | Acme KMS/database unavailable | Acme requests fail closed; contoso follows isolation policy |
| 35 | Single-tenant backup/restore | Restores that tenant's exact data, issuer, keys, and metadata |

### 13.1. Critical Assertions

Integration tests should verify:

- Issuer in metadata and tokens matches the path/tenant.
- `AuthorizationServerContextHolder` returns the expected issuer in every protocol request.
- All four core components delegate to the right tenant.
- No fallback occurs when an issuer is unregistered.
- Duplicate client IDs across two tenants do not mix registrations.
- Tokens, consents, JWKs, caches, and user mappings never leak across tenants.
- Resource Server validates exact issuer, audience, and authorities.
- Dynamic onboarding becomes active only after all components are ready.
- Multi-pod requests yield identical results for the same issuer.
- Reverse proxies cannot be abused to spoof issuers.

## 14. Troubleshooting and Production Checklist

| Symptom | Possible cause | Resolution |
|---|---|---|
| Metadata returns root issuer, missing tenant path | Fixed issuer configured or proxy/path not recognized | Remove fixed issuer in multi-issuer mode; check public routes |
| All tenants share the same client registry | Missing delegating `RegisteredClientRepository` | Route via `AuthorizationServerContext` issuer |
| Tenant A token found in Tenant B | `AuthorizationService` improperly shared or missing tenant discriminator | Separate service or fix query/tenant predicate |
| Wrong tenant JWK Set | `JWKSource` not tenant-aware or cache key missing issuer | Delegate `JWKSource` by issuer and isolate cache |
| Unknown tenant returns default data | Component falls back to default tenant | Fail closed and add negative tests |
| One pod resolves a different issuer than another | Mismatched forwarded headers, host/path, or config | Normalize proxy and synchronize deployments |
| Resource Server fetches JWKs from strange URLs | Trusts unverified `iss` or dynamic issuers lack allowlist | Use a trusted issuer registry |
| Duplicate client ID causes wrong authentication | Lookup runs without tenant context | Verify context and per-tenant unique keys |
| Old schema uses wrong tenant connection | Schema/connection pool not reset | Manage transactions and reset schema safely |
| Dynamic tenant active but token endpoint errors | Components registered before DB/keys ready | Use provisioning state machine and atomic activation |

### 14.1. Production Checklist

- [ ] Clearly choose dedicated issuer, path-based multi-issuer, or shared issuer + tenant claim.
- [ ] For path-based multi-issuer, enable `multipleIssuersAllowed(true)`.
- [ ] Do not configure a fixed issuer when resolving multiple issuers from requests.
- [ ] Canonical issuers and tenant mappings live in a server-managed allowlist.
- [ ] Unknown issuers fail closed with no fallback to a default tenant.
- [ ] `RegisteredClientRepository`, `OAuth2AuthorizationService`, `OAuth2AuthorizationConsentService`, and `JWKSource` are all tenant-aware.
- [ ] Choose dedicated databases, dedicated schemas, or shared tables with tenant discriminator/composite constraints.
- [ ] Signing keys/JWK Sets and key rotation are managed per tenant.
- [ ] Cache keys include tenant/issuer.
- [ ] Resource Server validates exact issuer, audience, signature, expiry, and tenant authorities.
- [ ] Never fetch JWKs from arbitrary issuer URLs in unverified tokens.
- [ ] Proxy/Host/Forwarded headers are restricted to the trust boundary.
- [ ] Tenant context is preserved across async/background processing.
- [ ] Dynamic onboarding/deactivation has a state machine, auditing, and atomic activation.
- [ ] Negative tests verify against cross-tenant token, client, consent, cache, and user access.
- [ ] Per-tenant backup/restore and incident runbooks exist.
- [ ] Metrics/logs include verified tenant IDs without tokens/secrets.

**Self-assessment questions**

1. What is the difference between a shared issuer with a `tenant_id` claim and path-based multiple issuers?
2. Why is an issuer part of the trust boundary rather than just a URL?
3. Which configuration enables multiple issuers in Spring Authorization Server?
4. Why does configuring a fixed issuer disable per-request issuer resolution?
5. What information does `AuthorizationServerContextHolder` provide and what are its lifecycle limits?
6. Why should a tenant registry look up exact full issuers instead of suffix matches?
7. Which four core components must be tenant-aware?
8. What is the risk if `RegisteredClientRepository` is tenant-isolated while `OAuth2AuthorizationService` is not?
9. Why should JWK Sets be managed per issuer?
10. How do separate databases, separate schemas, and shared tables differ in isolation?
11. Why can a cache key using only client ID cause cross-tenant leaks?
12. How does a Resource Server select a decoder by issuer and why is a trusted issuer allowlist required?
13. Why must you never fetch a JWK URL from an arbitrary `iss` in an unverified JWT?
14. During dynamic tenant onboarding, when is it safe to transition to active?
15. How do you ensure multi-pod requests always select the same tenant store?
16. When deactivating a tenant, why should you not simply delete the registry entry immediately?

## References

- [Spring Authorization Server 1.5.8 — How-to: Implement Multitenancy](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-multitenancy.html): `multipleIssuersAllowed`, issuer paths, `AuthorizationServerContextHolder`, component registry, and the four multi-tenant components.
- [Spring Authorization Server — AuthorizationServerSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.Builder.html): `multipleIssuersAllowed(boolean)` and fixed issuer notes.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, authorization, consent, and `JWKSource` components.
- [Spring Security — OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): resolving/propagating tenants, trusted issuers, and `AuthenticationManagerResolver`.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer and Provider Configuration metadata.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): issuer and well-known metadata endpoints.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): issuer, audience, and JWT access token validation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): securing authorization servers, issuers, tokens, and trust boundaries.
