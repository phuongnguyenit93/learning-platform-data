# Resolving Tenants Safely and Validating Hosts and Paths

## 1. Objectives and Scope

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**. This lesson focuses on the first step of a multi-tenant architecture: determining which tenant is receiving a request, validating that request's host/path, and propagating the tenant context to the right processing components.

An Authorization Server serving multiple organizations may use different issuers:

- A dedicated host per tenant: `https://acme.login.example.com`.
- A dedicated path on a shared host: `https://login.example.com/acme`.
- A combination of host and path: `https://acme.login.example.com/auth`.

The issuer is the security identity of the Authorization Server. It appears in discovery metadata, the token `iss` claim, signature verification, and client configuration. If a request for tenant A is misrouted to tenant B's signing keys, client repository, or authorization store, the security boundary is broken.

Spring Authorization Server 1.5.8 supports multiple issuers on the same host via path-containing issuers. This lesson uses the 1.5.8 API as a baseline and extends it into an allowlist-backed host/path routing workflow. When deploying another branch, verify the Javadoc and multitenancy guide for that exact version.

After this lesson, you will be able to:

1. Distinguish a tenant identifier, issuer, and host/path routing key.
2. Choose a tenant resolution strategy based on host, path, or both.
3. Enable multiple issuers in Spring Authorization Server.
4. Validate host, scheme, port, and path against server configuration.
5. Handle `Forwarded`/`X-Forwarded-*` headers through a trusted proxy.
6. Use `AuthorizationServerContext` to select components for the current issuer.
7. Isolate clients, authorizations, consents, and signing keys across tenants.
8. Test for host spoofing, path traversal, issuer mismatch, and cross-tenant access.

## 2. Tenant ID, Host, Path, and Issuer

### 2.1. Four Concepts to Keep Separate

| Concept | Meaning | Example |
| --- | --- | --- |
| Tenant ID | Internal key identifying the organization | `tenant-acme` |
| Host | Hostname accessed by the client | `login.example.com` |
| Path prefix | Path segment representing the tenant on the host | `/acme` |
| Issuer | Canonical URL identifier of the Authorization Server | `https://login.example.com/acme` |

The Tenant ID is an internal key. The host/path is routing input from the request. The issuer is a public identifier that must remain stable and match the value in tokens and discovery metadata. Never use an arbitrary host or path string directly as a tenant ID, and never construct an issuer from unvalidated request data.

### 2.2. The Issuer Is a Security Boundary

Example with two tenants:

| Tenant | Issuer | Discovery |
| --- | --- | --- |
| Acme | `https://login.example.com/acme` | `https://login.example.com/acme/.well-known/openid-configuration` |
| Globex | `https://login.example.com/globex` | `https://login.example.com/globex/.well-known/openid-configuration` |

Acme's metadata must advertise the issuer `https://login.example.com/acme`, and advertised endpoints must live under the corresponding base URL. Tokens issued by Acme must carry an `iss` matching Acme's issuer. A client configured for Acme's issuer must never accept tokens from Globex's issuer simply because both tenants share the same domain.

OIDC requires clients to check the exact issuer against the trusted discovery/configuration issuer. Therefore, do not treat the issuer as merely a URL for display or link generation.

### 2.3. Do Not Infer a Tenant from a Single Unverified Signal

The following signals do not prove a tenant by themselves:

- Query parameters such as `?tenant=acme`.
- Arbitrary headers such as `X-Tenant-Id`.
- `Host`/`X-Forwarded-Host` sent directly by the client.
- Unnormalized or unvalidated paths.
- A JWT `iss` before verifying its signature and checking an issuer allowlist.
- A `client_id` sent in the request before client authentication succeeds.

A signal may be used to select an initial route, but the result must be checked against the provisioned tenant/issuer directory. Selecting a tenant must never dynamically create a new tenant or trust an unregistered host.

## 3. Choosing a Host/Path Strategy

### 3.1. Dedicated Host per Tenant

Example:

```text
https://acme.login.example.com/oauth2/authorize
https://globex.login.example.com/oauth2/authorize
```

Advantages:

- The host is a clear routing boundary.
- DNS, TLS certificates, WAF rules, and rate limits can be configured independently.
- Tenants can be routed to separate ingresses or backends when needed.

Aspects to manage:

- Exact allowlist of hostnames and ports.
- Wildcard DNS/certificates do not mean every subdomain is a valid tenant.
- Validate `Host`/authority before deriving an issuer.
- Host aliases must map to a configured canonical issuer.

Do not accept every subdomain of `login.example.com` using an `endsWith("login.example.com")` check. A string like `evil-login.example.com` or a confusingly suffixed host can bypass a poorly written suffix check. Use exact matching or explicit DNS label boundary checks.

### 3.2. Dedicated Path on the Same Host

Example:

```text
https://login.example.com/acme/oauth2/authorize
https://login.example.com/globex/oauth2/authorize
```

Spring Authorization Server supports multiple issuers on a single host using path-containing issuers. This is the strategy used in the official multitenancy guide. The tenant path is part of the issuer and the base URL of protocol endpoints.

When using paths:

- The prefix must exist in the route table.
- Match on segment boundaries so `/acme` does not accidentally match `/acme-old`.
- Do not URL-decode multiple times.
- Reject abnormal path encodings, dot segments, or encoded slashes/backslashes if the routing layer does not support them.
- Preserve the provisioned canonical issuer.

### 3.3. Combining Host and Path

Some systems need a shared regional host with a dedicated path per tenant:

```text
https://apac.login.example.com/acme
https://apac.login.example.com/globex
https://eu.login.example.com/contoso
```

The route key then consists of scheme, hostname, port, and path prefix. If a tenant moves regions or changes hostnames, manage aliases and issuer migration deliberately. Never allow two tenants to share the same route key.

### 3.4. Choosing a Strategy Based on Isolation Requirements

| Criterion | Dedicated host | Dedicated path |
| --- | --- | --- |
| DNS/TLS | Needs multiple hostnames or controlled wildcard | Can use a single hostname |
| WAF/rate limiting | Policies can be applied per host | Usually applied per path/tenant route |
| Issuer | Different hostname | Different path |
| Reverse proxy | Must preserve trusted original host | Must preserve original path prefix |
| SAS configuration | Request-derived/tenant-aware issuer | `multipleIssuersAllowed(true)` for multiple issuers on one host |
| Operations | Manage DNS/certificates | Manage path routing and prefixes |

If strong isolation or customer custom domains are needed, dedicated hosts align well with TLS, ingress, and network policies. If you want a single centralized endpoint, dedicated paths are usually simpler. Either way, the issuer and tenant component registry must uniquely identify the tenant.

## 4. Enabling Multiple Issuers in Spring Authorization Server

### 4.1. Configuring multipleIssuersAllowed

By default, multiple issuers on the same host are disabled. For the path-based issuer model, enable it:

```java
@Configuration(proxyBeanMethods = false)
public class AuthorizationServerSettingsConfig {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .multipleIssuersAllowed(true)
                .build();
    }
}
```

In a model where multiple issuers are resolved from the request, do not fix a single issuer via `.issuer("https://login.example.com")`. Configuring a fixed issuer forces the server back to a single issuer and defeats per-request issuer resolution.

If the application serves only a single issuer, configure a fixed issuer according to single-tenant design. Do not enable multiple issuers merely to work around a host configuration bug.

The official Spring guide specifically describes multiple issuers on the same host using path components. Host-based routing is a routing layer at the ingress/tenant directory; do not treat the `multipleIssuersAllowed` flag alone as a hostname allowlist mechanism. With dedicated hosts per tenant, you must still validate the host and confirm the request-derived issuer matches the registered canonical issuer.

### 4.2. AuthorizationServerContext and the Current Issuer

Spring Authorization Server provides:

- `AuthorizationServerContext`: holds `AuthorizationServerSettings` and the issuer of the current request.
- `AuthorizationServerContextHolder`: accesses the context during request processing.

In a multi-issuer configuration, `AuthorizationServerContext.getIssuer()` can contain the tenant path. For example:

| Request endpoint | Resolved issuer |
| --- | --- |
| `https://login.example.com/acme/oauth2/token` | `https://login.example.com/acme` |
| `https://login.example.com/globex/oauth2/token` | `https://login.example.com/globex` |
| `https://login.example.com/auth/acme/oauth2/jwks` | `https://login.example.com/auth/acme` |

Read the issuer inside components invoked during the request lifecycle:

```java
AuthorizationServerContext context =
        AuthorizationServerContextHolder.getContext();

if (context == null || context.getIssuer() == null) {
    throw new IllegalStateException(
            "Authorization Server issuer context is unavailable"
    );
}

String issuer = context.getIssuer();
```

Do not cache the current issuer in a singleton bean field. `AuthorizationServerContextHolder` binds the context to the currently executing request; the tenant value must be read on each call rather than stored as shared state across requests.

### 4.3. Discovery Must Reflect the Right Tenant

With path issuer `https://login.example.com/acme`, OIDC discovery:

```http
GET /acme/.well-known/openid-configuration HTTP/1.1
Host: login.example.com
```

Key metadata fields must correspond:

```json
{
  "issuer": "https://login.example.com/acme",
  "authorization_endpoint": "https://login.example.com/acme/oauth2/authorize",
  "token_endpoint": "https://login.example.com/acme/oauth2/token",
  "jwks_uri": "https://login.example.com/acme/oauth2/jwks",
  "revocation_endpoint": "https://login.example.com/acme/oauth2/revoke",
  "introspection_endpoint": "https://login.example.com/acme/oauth2/introspect"
}
```

This is an abbreviated example. Verify all metadata returned by the server, especially `issuer`, endpoint URLs, and `jwks_uri`. If Acme's discovery returns Globex's endpoints or issuer, clients must not proceed with the flow.

## 5. Trust Boundaries for Host and Forwarded Headers

### 5.1. Host/Authority Is Spoofable Input

HTTP requests carry authority/`Host` so the server knows which hostname the request targets. Applications should never blindly trust any `Host` value to construct absolute issuers or redirect URLs. An unregistered host can lead to:

- Forged issuers in discovery.
- Token/JWKS endpoint URLs pointing to an attacker's host.
- Cache poisoning when cache keys omit the host.
- Password reset/consent links or redirects using the wrong domain.
- Tenant confusion between two host aliases.

Enforce a host allowlist at the ingress/reverse proxy and re-check it in the application. Reject hosts absent from the tenant directory; never use a default tenant as a fallback for an unknown host.

### 5.2. Forwarded and X-Forwarded Headers

When an application sits behind a load balancer or reverse proxy, internal requests may see a different host, scheme, port, and path than the URL the client accessed. The proxy can pass the original details via:

- `Forwarded` per RFC 7239;
- `X-Forwarded-Host`;
- `X-Forwarded-Proto`;
- `X-Forwarded-Port`;
- `X-Forwarded-Prefix`.

Use these headers only when the proxy at the trust boundary strips client-sent values and writes its own. Spring Framework warns that forwarded headers must never pass directly from outside into the application as trusted data.

### 5.3. Configuring Spring Boot Behind a Trusted Proxy

If infrastructure already has a trusted proxy that overwrites forwarded headers, configure Spring Boot with the matching strategy:

```yaml
server:
  forward-headers-strategy: framework
```

`FRAMEWORK` uses `ForwardedHeaderFilter` on the servlet stack. `NATIVE` uses the web server's native support. Choose according to the actual proxy/server and test how host, scheme, port, and prefix are restored. Never enable forwarded-header processing blindly if the application can receive direct traffic from the Internet.

If forwarded headers cannot be trusted, do not use them to determine the issuer. You can configure remove-only mode on the appropriate filter or leave the forwarded-headers strategy at `NONE`, while requiring the proxy to route by a verified `Host`/URL.

With path tenancy, the proxy should preserve the tenant prefix or restore the original prefix using a forwarded-prefix header written exclusively by a trusted proxy. If the proxy rewrites `/acme/oauth2/token` to `/oauth2/token`, a resolver relying on `getRequestURI()` will no longer see `/acme`; `AuthorizationServerContext` must also see the same external issuer. Never append an unverified `X-Forwarded-Prefix` to the path or issuer. Test requests behind the proxy with integration tests.

### 5.4. Proxy Boundary Example

```text
Internet client
    |
    | Host: attacker.example
    | X-Forwarded-Host: login.example.com
    v
Trusted ingress / reverse proxy
    |
    | validate public host against virtual-host allowlist
    | remove incoming Forwarded and X-Forwarded-* headers
    | set trusted Forwarded/X-Forwarded-* values
    v
Spring Boot Authorization Server
    |
    | forwarded-header strategy matches ingress contract
    | resolve canonical issuer
    v
Tenant directory / component registry
```

Never let an external client choose `X-Forwarded-Host` and cause the application to issue tokens with another tenant's issuer. If the backend is directly reachable, restrict network access so only the ingress can connect, or ensure the backend never trusts forwarded headers from direct paths.

## 6. Validating Host/Path via the Tenant Directory

### 6.1. Use a Provisioned Route Table

Instead of constructing the issuer dynamically from the request, declare governed routes:

| Scheme | Host | Port | Path prefix | Tenant ID | Canonical issuer |
| --- | --- | --- | --- | --- | --- |
| `https` | `login.example.com` | `443` | `/acme` | `tenant-acme` | `https://login.example.com/acme` |
| `https` | `login.example.com` | `443` | `/globex` | `tenant-globex` | `https://login.example.com/globex` |
| `https` | `acme.login.example.com` | `443` | `/` | `tenant-acme` | `https://acme.login.example.com` |

The route table is an allowlist. Each route maps to an existing tenant and a canonical issuer. Never add a route just because a request arrives for the first time with a new host/path.

### 6.2. Route Model and Resolver

The example below illustrates a simple resolver. It assumes the request has already passed through trusted proxy configuration if present; the path prefix is matched on segment boundaries:

The code uses Java 17+ (`record`) and omits imports as well as application-specific exceptions/services. `pathPrefix` in the route table must match the path format returned by the servlet container via `getRequestURI()`, consistently including or excluding any context path. If a proxy rewrites paths, the route table must match the post-rewrite path or an original prefix restored from a trusted proxy.

```java
public record TenantRoute(
        String tenantId,
        String scheme,
        String host,
        int port,
        String pathPrefix,
        String issuer) {
}
```

```java
public final class TenantRouteResolver {

    private final List<TenantRoute> routes;

    public TenantRouteResolver(List<TenantRoute> routes) {
        this.routes = List.copyOf(routes);
    }

    public TenantRoute resolve(HttpServletRequest request) {
        String scheme = request.getScheme().toLowerCase(Locale.ROOT);
        String host = normalizeHost(request.getServerName());
        int port = effectivePort(scheme, request.getServerPort());
        String path = request.getRequestURI();

        return this.routes.stream()
                .filter(route -> route.scheme().equals(scheme))
                .filter(route -> normalizeHost(route.host()).equals(host))
                .filter(route -> route.port() == port)
                .filter(route -> pathMatches(path, route.pathPrefix()))
                .max(Comparator.comparingInt(
                        route -> route.pathPrefix().length()
                ))
                .orElseThrow(() ->
                        new UnknownTenantException("No trusted tenant route"));
    }

    private static String normalizeHost(String host) {
        try {
            return IDN.toASCII(host, IDN.USE_STD3_ASCII_RULES)
                    .toLowerCase(Locale.ROOT);
        } catch (IllegalArgumentException ex) {
            throw new UnknownTenantException("Invalid request host", ex);
        }
    }

    private static int effectivePort(String scheme, int port) {
        if (port > 0) {
            return port;
        }
        return "https".equals(scheme) ? 443 : 80;
    }

    private static boolean pathMatches(String requestPath, String prefix) {
        if ("/".equals(prefix)) {
            return requestPath.startsWith("/");
        }
        String normalizedPrefix = prefix.endsWith("/")
                ? prefix.substring(0, prefix.length() - 1)
                : prefix;
        return requestPath.equals(normalizedPrefix)
                || requestPath.startsWith(normalizedPrefix + "/");
    }
}
```

`UnknownTenantException` is an application-defined exception. The sample resolver assumes route config was validated at startup: scheme is strictly `https` in production, host is a valid DNS name, port is a standard port, path prefix starts with `/`, contains no query/fragment or dot segments, and issuer is a managed canonical URL.

For IPv6 literal hosts, use a dedicated canonicalization branch rather than calling `IDN.toASCII`. If the application does not support IPv6 hosts at the public edge, reject such routes explicitly.

The sample resolver does not automatically strip trailing dots from hostnames. Production should adopt an explicit policy: reject hosts with trailing dots, or canonicalize them identically at route provisioning time. Never allow these two forms to accidentally produce two different issuers.

### 6.3. Why Match Paths on Segment Boundaries?

If the tenant prefix is `/acme`, a `startsWith("/acme")` check would also match `/acme-old`. Proper matching must be:

- Request path equals `/acme`; or
- Request path starts with `/acme/`.

For nested prefixes such as `/region/acme` and `/region/acme/admin`, select the most specific route via longest-prefix match, while disallowing two routes with the same scheme/host/port/prefix.

### 6.4. Normalize Paths Once

Paths can be transformed by proxies, servlet containers, or routers. Cases that must be handled consistently:

- `%2F`/`%5C` (encoded slash/backslash);
- `%2E` and dot segments `.`/`..`;
- double slashes `//`;
- trailing slashes;
- multi-layer percent encoding;
- path prefixes stripped or added by proxies.

Do not decode paths multiple times or write custom decoders that diverge from the container. Configure the ingress and servlet container to agree on a canonical path form; keep the default `StrictHttpFirewall` unless there is a clear reason and security review. If a path has multiple representations that could map to different tenants, reject the request rather than guessing.

## 7. Connecting Tenant Routes to AuthorizationServerContext

### 7.1. Verify Route and Issuer Belong to the Same Tenant

The route resolver confirms the request matches a provisioned route. Spring Authorization Server resolves the issuer in `AuthorizationServerContext`. During protocol request processing, verify that both results match:

```java
public TenantRoute requireCurrentTenant(
        HttpServletRequest request,
        TenantRouteResolver routeResolver) {

    TenantRoute route = routeResolver.resolve(request);
    AuthorizationServerContext context =
            AuthorizationServerContextHolder.getContext();

    if (context == null || context.getIssuer() == null) {
        throw new UnknownTenantException(
                "Authorization Server context is unavailable"
        );
    }

    if (!route.issuer().equals(context.getIssuer())) {
        throw new UnknownTenantException(
                "Request route and Authorization Server issuer do not match"
        );
    }
    return route;
}
```

This is a defense-in-depth check. The resolver does not overwrite `AuthorizationServerContextHolder`; Spring Authorization Server's context remains managed by the framework's filter/context infrastructure. If the issuer produced by the framework differs from the canonical route, fail closed and fix the proxy/path/issuer configuration.

### 7.2. Exact-Issuer Component Registry

Spring Authorization Server requires several components capable of resolving by tenant. You can use a registry:

```java
public record TenantComponents(
        RegisteredClientRepository registeredClientRepository,
        OAuth2AuthorizationService authorizationService,
        OAuth2AuthorizationConsentService authorizationConsentService,
        JWKSource<SecurityContext> jwkSource) {
}
```

```java
public final class TenantComponentRegistry {

    private final ConcurrentMap<String, TenantComponents> tenants =
            new ConcurrentHashMap<>();

    public void register(String issuer, TenantComponents components) {
        Assert.hasText(issuer, "issuer cannot be empty");
        Assert.notNull(components, "components cannot be null");
        TenantComponents previous = this.tenants.putIfAbsent(issuer, components);
        Assert.state(previous == null, "Issuer is already registered");
    }

    public TenantComponents requireCurrent() {
        AuthorizationServerContext context =
                AuthorizationServerContextHolder.getContext();
        Assert.state(context != null && StringUtils.hasText(context.getIssuer()),
                "Authorization Server issuer context is unavailable");

        TenantComponents components = this.tenants.get(context.getIssuer());
        Assert.state(components != null,
                "No components registered for the requested issuer");
        return components;
    }
}
```

This registry looks up by the exact registered issuer string. Avoid patterns like `issuer.endsWith(tenantId)` where tenant IDs can share suffixes or issuer paths can share prefixes. Tenant registration must occur in a controlled provisioning flow; requests must never insert entries into the registry on the fly.

If a hostname alias is accepted, canonicalize the alias at the trusted ingress before the request enters the Authorization Server. If the application still receives the alias as a distinct host, the request-derived issuer may differ from the canonical issuer; in that case, the alias must be provisioned and treated as its own issuer, or rejected. Never silently map one external issuer to another.

### 7.3. Delegating Components

A composite `RegisteredClientRepository` can forward calls to the current issuer's repository:

```java
public final class TenantAwareRegisteredClientRepository
        implements RegisteredClientRepository {

    private final TenantComponentRegistry registry;

    public TenantAwareRegisteredClientRepository(TenantComponentRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void save(RegisteredClient registeredClient) {
        registry.requireCurrent()
                .registeredClientRepository()
                .save(registeredClient);
    }

    @Override
    public RegisteredClient findById(String id) {
        return registry.requireCurrent()
                .registeredClientRepository()
                .findById(id);
    }

    @Override
    public RegisteredClient findByClientId(String clientId) {
        return registry.requireCurrent()
                .registeredClientRepository()
                .findByClientId(clientId);
    }
}
```

Other delegating services follow the same principle:

- `OAuth2AuthorizationService`: delegate `save`, `remove`, `findById`, `findByToken`.
- `OAuth2AuthorizationConsentService`: delegate `save`, `remove`, `findById`.
- `JWKSource<SecurityContext>`: get the current issuer's JWK source and call `get(selector, context)`.

These wrappers are meant for protocol requests that have an `AuthorizationServerContext`. Provisioning/admin control planes running outside a request lack this context; they should call the specific governed tenant's component directly rather than invoking the delegating wrapper and assuming a default tenant.

Composite JWK source example:

```java
public final class TenantAwareJwkSource
        implements JWKSource<SecurityContext> {

    private final TenantComponentRegistry registry;

    public TenantAwareJwkSource(TenantComponentRegistry registry) {
        this.registry = registry;
    }

    @Override
    public List<JWK> get(
            JWKSelector selector,
            SecurityContext securityContext) throws KeySourceException {
        JWKSource<SecurityContext> tenantJwkSource =
                registry.requireCurrent().jwkSource();
        return tenantJwkSource.get(selector, securityContext);
    }
}
```

Never let a component infer the tenant by searching for a client ID across all tenant repositories. Every operation must start from the issuer already resolved for the current request.

## 8. Isolating Data and Keys by Tenant

### 8.1. Components That Must Be Tenant-Aware

The official Spring Authorization Server guide identifies four core components that must support multitenancy:

| Component | Data to isolate |
| --- | --- |
| `RegisteredClientRepository` | Client ID, secret, grants, scopes, redirect URIs, auth methods |
| `OAuth2AuthorizationService` | Authorization codes, access/refresh tokens, ID Tokens, token state |
| `OAuth2AuthorizationConsentService` | Resource owner consents per client and principal |
| `JWKSource<SecurityContext>` | Signing keys, verification keys, key rotation, and public JWKS |

In addition, applications typically need tenant awareness for:

- User directory/`UserDetailsService`;
- policy service, consent policies, and claim mappers;
- audit logs and event publishers;
- rate limits/quotas;
- caches and distributed locks;
- key management/KMS aliases;
- email, branding, and custom login/consent pages.

### 8.2. Database Isolation

There are three common options:

| Model | How it works | Assessment |
| --- | --- | --- |
| Separate database | Each tenant has its own database/cluster | Strong isolation, high operational cost |
| Separate schema | Each tenant has its own schema in the same database | Good isolation if DB permissions and migrations are managed |
| Shared schema + tenant key | Shared tables with `tenant_id` | Cost-effective; requires ensuring every query/unique key includes tenant |

The Spring guide illustrates separate JDBC repositories per issuer with separate `DataSource` instances. This is a clear way to reduce cross-tenant query risks. If using a shared schema, do not just add `tenant_id` to entities: enforce the tenant predicate across every related query, unique constraint, and foreign key.

### 8.3. Client and Authorization Isolation

Client IDs do not have to be globally unique if repositories are isolated by tenant. However, in a shared repository, unique keys must include the tenant or client IDs must be explicitly namespaced. During lookup, apply the tenant context before querying the client.

Authorization records must always reference a client belonging to the same tenant. Never allow an Acme authorization to reference a `registered_client_id` that only exists in Globex's repository. Consent lookups must also include client/tenant context; the same `principalName` in two tenants represents two identities in two separate security domains.

### 8.4. JWK and Signing Key Isolation

Each issuer should have its own signing keys and JWKS, or a key management design with verified tenant boundaries. For JWTs:

- Acme signs with Acme keys.
- Globex signs with Globex keys.
- Acme's JWKS publishes only Acme public keys.
- Tokens with Acme `iss` must be verified using Acme's issuer/key configuration.

Do not share private signing keys across tenants merely to simplify configuration. If one tenant's key is compromised, the blast radius must not spread to other tenants. Key rotation should be performed independently or under a controlled synchronized policy.

## 9. Tenant Context in Applications and Background Tasks

### 9.1. Per-Request Context

In HTTP protocol flows, `AuthorizationServerContextHolder` provides the current request's issuer. Read the context on every service/repository invocation and delegate immediately to the tenant's component.

Never store the current `TenantComponents` in a singleton field or mutable static variable. Concurrent requests can belong to different tenants; shared state could cause an Acme request to write data into Globex's database.

### 9.2. Async Tasks, Schedulers, and Message Consumers

`AuthorizationServerContextHolder` is bound to the request lifecycle and does not automatically propagate to async or background tasks. When work is queued or scheduled:

- Record the verified tenant ID/issuer in message metadata.
- When the consumer processes it, look up the tenant from the allowlist registry.
- Authenticate the message producer and tenant access permissions.
- Establish task-scoped context through an application-managed mechanism.
- Clear the context in `finally` upon completion.

Never serialize an `AuthorizationServerContext` object from an HTTP request and reuse it in the background. Pass only stable identifiers and re-verify access permissions when the consumer receives the message.

### 9.3. Cache Keys Must Include the Tenant

Caches easily leak data if keys contain only client ID, user ID, or token hash. Use tenant/issuer-scoped keys:

```text
tenant-acme:registered-client:client-123
tenant-globex:registered-client:client-123
tenant-acme:user-profile:user-100
tenant-globex:user-profile:user-100
```

Apply the same pattern to caches for authorizations, consents, JWKS, discovery metadata, rate limits, and distributed locks. When a tenant is deleted or keys rotate, invalidate the exact namespace.

## 10. Dynamic Tenant Onboarding and Lifecycle Management

### 10.1. Provisioning Tenants via a Control Plane

Dynamic tenants require an administrative workflow independent of protocol requests:

1. Verify the organization/domain and administrator permissions.
2. Assign a unique internal tenant ID.
3. Register the hostname/path prefix and canonical issuer.
4. Verify DNS, TLS certificate, and ingress route.
5. Create the `DataSource`/schema and run migrations.
6. Create `RegisteredClientRepository`, `OAuth2AuthorizationService`, consent service, and JWK source.
7. Register components by issuer in the registry.
8. Run health/discovery checks before marking the tenant active.

Never create a new database, key pair, or issuer on the first incoming request to an unknown hostname. That turns public routing into an uncontrolled provisioning API.

### 10.2. Thread-Safe Registry and Lifecycle

Use a thread-safe structure such as `ConcurrentHashMap` for the registry. Adding a tenant must verify that the issuer does not already exist, the route key is not claimed by another tenant, and all components are ready before publishing the tenant as active.

When retiring a tenant:

- Transition status to disabled to reject new requests.
- Revoke or handle tokens per contractual policy.
- Retain audit/retention data as required.
- Remove routes and discovery after transition completes.
- Close `DataSource`/key resources once no in-flight requests remain.

Do not remove a tenant from the registry the instant deprovisioning begins if requests are still in flight. Follow an explicit lifecycle/graceful shutdown process.

### 10.3. Aliases and Changing Issuers

An issuer is a stable identifier. Changing domains or paths can impact client discovery caches, issuer validation, token `iss`, redirect URIs, and JWKS. If migration is necessary:

- Publish an issuer migration plan.
- Maintain aliases/redirects only when protocols and security policies permit.
- Issue new tokens with the new issuer after clients are updated.
- Do not validate tokens with an old issuer merely because a domain redirects to the new domain.
- Retain key/authorization history according to policy and token lifetimes.

Never silently change a canonical issuer in the route registry while the database and existing tokens still hold the previous issuer.

## 11. Testing and Troubleshooting

### 11.1. Test Matrix

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| TENANT-01 | Request to registered Acme host | Resolves tenant Acme |
| TENANT-02 | Request to unregistered host | Rejected; no fallback to default tenant |
| TENANT-03 | Host with mixed uppercase/lowercase | Canonicalized per policy and mapped to the right host |
| TENANT-04 | Host with confusing suffix like `evil-login.example.com` | Does not match `login.example.com` allowlist |
| TENANT-05 | Host with trailing dot | Handled per configured canonicalization; does not create a new issuer |
| TENANT-06 | Unicode/IDN host | Converted to ASCII IDN per policy or rejected |
| TENANT-07 | Host with unregistered port | Rejected |
| TENANT-08 | HTTP request when tenant requires HTTPS | Rejected or redirected at edge per policy; never emits HTTP issuer |
| TENANT-09 | Request path `/acme/oauth2/token` | Resolves Acme |
| TENANT-10 | Request path `/acme-old/oauth2/token` | Does not resolve to Acme |
| TENANT-11 | Missing tenant path | Rejected |
| TENANT-12 | Path contains `..` or encoded slash | Rejected by firewall/route policy |
| TENANT-13 | Path has double slash or multi-layer encoding | Rejected if not in canonical route |
| TENANT-14 | Host and path belong to two different tenants | Route does not match; rejected |
| TENANT-15 | Client directly sends forged `X-Forwarded-Host` | Header stripped by proxy or untrusted |
| TENANT-16 | Trusted proxy sets verified forwarded host | Request uses the exact canonical external host |
| TENANT-17 | Proxy fails to strip client forwarded headers | Security test detects unsafe configuration |
| TENANT-18 | `multipleIssuersAllowed` not enabled for path issuers | Discovery/endpoint tests catch unhandled issuer path |
| TENANT-19 | Fixed issuer configured in multi-issuer mode | Configuration policy test rejects this single-issuer setup |
| TENANT-20 | Acme discovery | Metadata `issuer` and endpoint URLs belong to Acme |
| TENANT-21 | Globex discovery | Does not return Acme endpoints/issuer |
| TENANT-22 | `AuthorizationServerContextHolder` has no context | Component registry fails closed |
| TENANT-23 | Issuer context not in registry | Request is rejected |
| TENANT-24 | Route resolver and `AuthorizationServerContext` have different issuers | Request is rejected |
| TENANT-25 | Two tenants share the same client ID | Lookup returns the client for the right tenant |
| TENANT-26 | Acme uses Globex's authorization ID | Cross-tenant record is not found |
| TENANT-27 | Consent with same `principalName` in different tenants | Consent is not shared |
| TENANT-28 | Acme JWKS accessed | Returns only Acme's public keys |
| TENANT-29 | Acme JWT verified with Globex key | Verification fails |
| TENANT-30 | Cache keys between two tenants with same user ID | Never returns cross-tenant data |
| TENANT-31 | Async consumer processes Acme message | Acme context is verified and cleared after processing |
| TENANT-32 | Tenant disabled | New requests rejected; in-flight requests handled per lifecycle |
| TENANT-33 | Two concurrent requests for Acme and Globex | No context/component sharing between requests |
| TENANT-34 | Rolling deployment with differing tenant registries | Readiness check prevents under-configured node from receiving traffic |
| TENANT-35 | Issuer migration | Old and new clients/tokens handled per migration plan |

### 11.2. Testing Discovery and Issuers

For each tenant, test:

1. Call the discovery URL.
2. Read `issuer` in the metadata.
3. Compare exact string equality against the canonical issuer in the tenant directory.
4. Verify `authorization_endpoint`, `token_endpoint`, `jwks_uri`, revocation, and introspection URLs.
5. Execute a token issuance flow.
6. Decode the token to verify `iss`, then verify the signature using that issuer's own JWKS.
7. Attempt to verify the token under another tenant and confirm failure.

Do not check only for HTTP 200 on discovery. Metadata can succeed while returning the wrong tenant's issuer or endpoints.

### 11.3. Troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Discovery omits tenant path and returns root issuer | Fixed issuer configured or proxy/path not recognized | Remove fixed issuer in multi-issuer mode; check ingress rewrites |
| Issuer is always a fixed URL | `.issuer(...)` was called in multi-issuer mode | Remove fixed issuer and inspect request context |
| Issuer contains internal host | Forwarded headers not processed properly | Configure trusted proxy and forward-header strategy |
| Issuer controlled by attacker | Proxy fails to strip forwarded headers or host lacks allowlist | Fix trust boundary; reject unknown hosts |
| Route `/acme` matches `/acme-old` | Path matched with `startsWith` without segment boundary | Use exact/prefix boundary matching |
| Repository not found for issuer | Canonical issuer unregistered or context missing | Check provisioning and request lifecycle |
| Acme client not found | Client saved in another tenant's repository | Check tenant routing and `DataSource` |
| Authorization lookup returns wrong tenant's data | Service uses shared store without tenant predicate | Fix delegating service/query and unique keys |
| JWKS returns another tenant's keys | JWK source ignores issuer context | Delegate JWK source by exact issuer |
| Valid token signature but wrong `iss` | Validator only checks signature/key without binding issuer | Enforce exact issuer and check decoder config |
| Error occurs only behind proxy | Host/path/port rewritten differently from route table | Compare external URL and post-proxy request |
| New tenant not active on one node | Unsynchronized registry provisioning | Use readiness checks and sync components before traffic |
| Async request loses tenant context | Thread-local/request context not propagated | Pass verified tenant ID in message and re-resolve |

## 12. Production Checklist and Reference Material

### 12.1. Pre-Production Checklist

- [ ] Tenant ID, route key, and canonical issuer are distinct values.
- [ ] Every host/path is pre-registered in the tenant directory.
- [ ] Hosts are matched exactly; no wildcard/suffix matching without DNS boundaries.
- [ ] Scheme/port are validated and production issuers use HTTPS.
- [ ] Path prefixes are matched on segment boundaries.
- [ ] Path encoding, dot segments, slashes/backslashes, and duplicate slashes are handled consistently.
- [ ] `Forwarded`/`X-Forwarded-*` are trusted only when the proxy strips client headers and writes its own values.
- [ ] Backends have no direct access path bypassing the ingress trust boundary.
- [ ] `multipleIssuersAllowed(true)` is enabled when multiple issuers share a host.
- [ ] Fixed `.issuer(...)` is not configured in request-derived multi-issuer mode.
- [ ] Discovery metadata matches the tenant's exact issuer and endpoint URLs.
- [ ] `AuthorizationServerContextHolder` is used within request scope; never cached in singleton fields.
- [ ] Registry lookups use exact issuer keys and fail closed when components are missing.
- [ ] `RegisteredClientRepository`, authorization service, consent service, and JWK source are all tenant-aware.
- [ ] Databases/schemas, caches, rate limits, audits, and user directories are isolated by tenant.
- [ ] Signing keys and JWKS are isolated with dedicated rotation procedures.
- [ ] Async/background jobs receive a verified tenant ID and clear context afterward.
- [ ] Tests cover host spoofing, path traversal, issuer mismatch, cross-tenant data access, and concurrent requests.
- [ ] Procedures exist to provision, disable, delete, and migrate issuers.
- [ ] All cluster instances share a consistent tenant registry/configuration.

### Memory Map

```text
Incoming HTTP request
       |
       v
Trusted ingress / proxy
  - validate public host
  - strip untrusted forwarded headers
  - set trusted external scheme/host/prefix
       |
       v
TenantRouteResolver
  - scheme + host + port
  - path prefix boundary
  - exact route allowlist
       |
       v
Canonical tenant route
  tenantId + canonical issuer
       |
       +-------------------------------+
       |                               |
       v                               v
AuthorizationServerContext       Tenant route check
  current issuer                    exact issuer match
       |                               |
       +---------------+---------------+
                       |
                       v
             TenantComponentRegistry
                       |
        +--------------+---------------+
        |              |               |
        v              v               v
 RegisteredClient  Authorization    Consent
 Repository         Service         Service
                       |
                       v
                 Tenant JWKSource
                       |
                       v
             tenant-scoped protocol flow
```

**Key takeaway:** Tenants are selected from provisioned routes and canonical issuers, never from arbitrary headers or query parameters. Spring Authorization Server 1.5.8 supports multiple issuers on the same host via `multipleIssuersAllowed(true)` and path-containing issuers. Once a request is resolved, every repository, authorization service, consent service, and JWK source must delegate by the exact current issuer. Host/path, forwarded headers, discovery metadata, caches, and data must all enforce the same tenant boundary.

## Authoritative References

- [Spring Authorization Server 1.5.8 — How-to: Implement Multitenancy](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-multitenancy.html): path-based issuers, `multipleIssuersAllowed`, `AuthorizationServerContextHolder`, component registry, and tenant-aware components.
- [Spring Authorization Server 1.5.8 — AuthorizationServerSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.html): issuer and `isMultipleIssuersAllowed`.
- [Spring Authorization Server 1.5.8 — AuthorizationServerContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/context/AuthorizationServerContext.html): issuer resolved from the current request.
- [Spring Authorization Server 1.5.8 — AuthorizationServerContextHolder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/context/AuthorizationServerContextHolder.html): accessing the request-scoped Authorization Server context.
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html): configuring `server.forward-headers-strategy`, `NATIVE` and `FRAMEWORK`.
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): handling `Forwarded`/`X-Forwarded-*` and security considerations.
- [Spring Security — HttpFirewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html): strict firewall, path matching, and request hardening.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html): semantics of the HTTP `Forwarded` header.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): issuer and metadata endpoints.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): issuer identifier and ID Token/UserInfo validation.
