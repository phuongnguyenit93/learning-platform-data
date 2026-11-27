# Managing Tenant Lifecycles and Domain Configuration

## 1. Context and Objectives

An **OAuth 2.0/OpenID Connect Authorization Server** built with **Spring Security**, **Spring Authorization Server**, and **Spring Boot** can serve multiple organizations on the same platform. Each organization is a tenant with its own clients, users, authentication policies, authorizations, consents, and domain configuration. When the platform supports custom domains, each tenant can also request a branded login hostname.

Managing tenants is not merely inserting a row into a tenant table. A new tenant must undergo domain ownership verification, DNS configuration, TLS certificate issuance, data namespace creation, client and signing key configuration, discovery metadata publication, and login flow verification before serving traffic. When a tenant is suspended or leaves the platform, the reverse process must handle tokens, sessions, keys, data, and domains in a controlled sequence.

Running example: the `login.example.com` login platform serves Acme, Fabrikam, and Northwind. Acme wants to use `auth.acme.example` as a custom login domain; Fabrikam uses a platform-assigned subdomain; Northwind is active now but may move to a new domain next quarter. All three tenants run on a single Spring Authorization Server cluster behind a reverse proxy.

After this lesson, you will be able to:

1. Model the tenant lifecycle using states and guarded transitions.
2. Design a retryable onboarding workflow that avoids creating duplicate resources.
3. Verify custom domain ownership via DNS or HTTP challenges.
4. Configure DNS, TLS certificates, SNI, and reverse proxies for tenant domains.
5. Distinguish tenant ID, custom domain, canonical host, and OIDC issuer.
6. Route requests to the right tenant using a trusted domain registry.
7. Manage domain changes without inadvertently breaking issuers and client trust.
8. Handle suspension, reactivation, offboarding, and data deletion.
9. Organize provisioning, outbox, auditing, and tenant administration permissions.
10. Test against domain takeover, `Host` header poisoning, certificate failures, and cross-tenant routing.

**Version scope:** Examples reference Spring Authorization Server 1.5.8 and Spring Security 6.x. The framework provides core services and endpoint configuration; tenant lifecycle, domain registries, DNS verification, certificate provisioning, and administrative workflows are application/infrastructure responsibilities.

## 2. Concepts to Keep Separate

### 2.1. Tenant ID

The Tenant ID is a stable internal identifier for the tenant, such as `tenant-acme-001`. It is used in databases, audits, routing, and policies. Tenant IDs should not depend on company name, hostname, or issuer URL because those values can change.

### 2.2. Domain

A domain is a hostname that users or clients use to access the service, for example:

- `acme.login.example.com`: platform-assigned subdomain for Acme.
- `auth.acme.example`: custom domain owned by Acme.
- `login.example.com`: shared platform domain.

A tenant can have multiple domain aliases pointing to the same tenant. A verified domain does not automatically become an issuer.

### 2.3. Canonical Host

The canonical host is the primary hostname chosen by the system for a specific purpose, such as the login page or tenant endpoints. The system can keep old domains as aliases and redirect the UI to the canonical domain.

The canonical host must come from a verified domain registry. Never take the request's `Host` value directly and treat it as the canonical host.

### 2.4. OIDC Issuer

The issuer is the identifier of the OpenID Provider, advertised in discovery metadata and appearing in the `iss` claim of ID Tokens. Clients and Resource Servers use the issuer to verify that tokens come from a trusted OP.

Example:

~~~text
Issuer: https://login.example.com
Login domain: https://auth.acme.example
Tenant ID: tenant-acme-001
~~~

These three values can differ. If clients already trust `https://login.example.com`, changing the login page to `https://auth.acme.example` does not automatically require changing the issuer. Conversely, changing the issuer is a protocol migration requiring updates to clients and Resource Servers.

### 2.5. Domain Verification and TLS Certificates

Domain verification proves the tenant controls the domain at verification time. A TLS certificate proves an endpoint can complete a TLS handshake for that hostname. These are two separate steps:

- A DNS TXT challenge proves DNS management control.
- An HTTP challenge proves the ability to serve a resource under the hostname.
- A certificate issued afterward allows the endpoint to use HTTPS.

Do not treat a valid certificate as sole proof of tenant ownership; likewise, do not treat completed DNS verification as meaning the certificate is ready.

### 2.6. Formatting Rules and Stability of an Issuer

An issuer identifier in OpenID Connect is an HTTPS URL. It must not contain queries or fragments; choose a stable canonical URL and keep the exact representation in discovery metadata and tokens. Variants differing only by a trailing slash, hostname alias, or scheme may be treated by clients as different issuers.

Do not change the issuer per login, based on a renameable tenant label, or based on a request-supplied hostname. If a tenant changes its display name, keep the old issuer identifier; changing an issuer URL must be treated as a protocol migration.

## 3. Tenant Lifecycle

### 3.1. State Model

A tenant can transition through the following states:

| State | Meaning | Serves protocol traffic? |
| --- | --- | --- |
| `REQUESTED` | Tenant creation request received. | No |
| `PENDING_VERIFICATION` | Verifying organization/domain. | No |
| `PROVISIONING` | Creating configuration, storage, keys, and domain resources. | No |
| `READY` | Provisioning complete; readiness checks passed. | Not yet; awaiting activation |
| `ACTIVE` | Tenant permitted to operate. | Yes |
| `SUSPENDED` | Temporarily halted per policy or operational request. | No, or restricted per policy |
| `DECOMMISSIONING` | Revoking clients/tokens, removing domains, and handling retention. | Rejects new transactions |
| `DELETED` | Tenant deleted or anonymized per retention policy. | No |
| `FAILED` | Provisioning workflow failed; requires retry or intervention. | No |

`READY` is a useful state to separate provisioning from activation. A tenant may already have databases, keys, and certificates yet not be exposed in the load balancer or tenant resolver.

### 3.2. State Transitions

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> PENDING_VERIFICATION
    PENDING_VERIFICATION --> PROVISIONING: Domain / organization verified
    PENDING_VERIFICATION --> FAILED: Verification expired
    PROVISIONING --> READY: Provisioning and health checks pass
    PROVISIONING --> FAILED: Unrecoverable provisioning error
    FAILED --> PROVISIONING: Retry / repair
    READY --> ACTIVE: Explicit activation
    ACTIVE --> SUSPENDED: Admin / security / billing policy
    SUSPENDED --> ACTIVE: Reinstatement checks pass
    ACTIVE --> DECOMMISSIONING: Offboarding approved
    SUSPENDED --> DECOMMISSIONING: Offboarding approved
    DECOMMISSIONING --> DELETED: Retention and cleanup complete
~~~

Disallow arbitrary transitions. For example:

- `REQUESTED → ACTIVE` must be rejected without verification and provisioning.
- `FAILED → ACTIVE` must be rejected without re-running readiness checks.
- `DELETED → ACTIVE` is disallowed; if a customer returns, create a new tenant or follow a dedicated recovery workflow.
- `SUSPENDED → ACTIVE` must verify that suspension reasons have been resolved.
- `DECOMMISSIONING` must not accept new domain bindings or issue new tokens.

### 3.3. Transitions Must Record Actor, Reason, and Version

Each state change should record:

- Tenant ID.
- Old state and new state.
- Acting user or service.
- Reason and related ticket/reference.
- Timestamp.
- Before/after version.
- Workflow correlation ID.

A monotonically increasing version detects concurrent updates and out-of-order events. Never allow a stale command to overwrite a newer state.

### 3.4. Tenant State Does Not Replace Domain State

A tenant can be `ACTIVE` while one custom domain has `certificate_status=PENDING` or a `SUSPENDED` binding. Conversely, a domain can be `VERIFIED` while the tenant remains `PENDING_VERIFICATION` or `SUSPENDED`.

Manage tenants and domains with two linked yet independent state machines. This allows suspending a broken domain while keeping the tenant active via the platform domain, if policy allows.

## 4. Tenant and Domain Data Model

### 4.1. Tenant Record

A tenant record can contain:

| Field | Meaning |
| --- | --- |
| `tenant_id` | Immutable identifier. |
| `display_name` | Mutable display name. |
| `status` | Tenant state. |
| `issuer` | Canonical issuer if the tenant has a dedicated issuer; may use the shared platform issuer. |
| `default_domain_id` | Canonical domain for UI or endpoints per policy. |
| `created_at` / `updated_at` | Creation/update timestamps. |
| `version` | Optimistic locking/version. |
| `policy_ref` | Reference to authentication, token, and retention policies. |

Tenant IDs should never be reused after a tenant is deleted.

### 4.2. Domain Record

A domain registry can store:

| Field | Meaning |
| --- | --- |
| `domain_id` | ID of the domain binding. |
| `tenant_id` | Tenant owning the binding. |
| `hostname_ascii` | Normalized hostname in ASCII/IDNA A-label form. |
| `hostname_display` | Display hostname if preserving Unicode is needed. |
| `domain_type` | `PLATFORM_SUBDOMAIN` or `CUSTOM_DOMAIN`. |
| `purpose` | `LOGIN`, `ISSUER`, `API`, or defined purpose. |
| `verification_status` | `PENDING`, `VERIFIED`, `EXPIRED`, or `FAILED`. |
| `dns_status` | `UNKNOWN`, `PENDING`, `READY`, or `MISMATCH`. |
| `certificate_status` | `PENDING`, `ACTIVE`, `RENEWING`, `FAILED`, or `EXPIRED`. |
| `binding_status` | `PENDING`, `ACTIVE`, `SUSPENDED`, or `REMOVED`. |
| `is_canonical` | Whether this is the canonical domain for the corresponding purpose. |
| `verified_at` | Timestamp when verification succeeded. |
| `certificate_ref` | Reference to the certificate in the secret/certificate manager. |
| `version` | Version to guard against stale updates/events. |

One hostname must never be simultaneously bound to two tenants. Enforce a unique constraint on the canonical hostname, accounting for reservation/release states.

### 4.3. Example Schema

Simplified PostgreSQL example:

~~~sql
CREATE TABLE tenant (
    tenant_id varchar(100) PRIMARY KEY,
    display_name varchar(200) NOT NULL,
    status varchar(32) NOT NULL,
    issuer varchar(500),
    default_login_domain_id varchar(100),
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE tenant_domain (
    domain_id varchar(100) PRIMARY KEY,
    tenant_id varchar(100) NOT NULL REFERENCES tenant(tenant_id),
    hostname_ascii varchar(253) NOT NULL,
    domain_type varchar(32) NOT NULL,
    purpose varchar(32) NOT NULL,
    verification_status varchar(32) NOT NULL,
    dns_status varchar(32) NOT NULL,
    certificate_status varchar(32) NOT NULL,
    binding_status varchar(32) NOT NULL,
    is_canonical boolean NOT NULL DEFAULT false,
    verified_at timestamptz,
    certificate_ref varchar(300),
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE UNIQUE INDEX uq_tenant_domain_hostname_reserved
    ON tenant_domain (hostname_ascii)
    WHERE binding_status <> 'RELEASED';

CREATE UNIQUE INDEX uq_tenant_domain_canonical_purpose
    ON tenant_domain (tenant_id, purpose)
    WHERE is_canonical AND binding_status = 'ACTIVE';

CREATE INDEX idx_tenant_domain_tenant
    ON tenant_domain (tenant_id, purpose, binding_status);
~~~

This DDL illustrates core attributes only. Production requires reservation expiry, ownership challenges, audit fields, certificate renewal metadata, soft-delete/retention, and constraints ensuring each tenant has at most one canonical domain per purpose. Design partial unique indexes or transactional constraints according to your database engine.

### 4.4. Do Not Store Private Keys in Domain Records

Domain records store only references to the certificate/key manager. TLS private keys must reside in a certificate manager, HSM, or access-controlled secret store. OAuth/OIDC signing keys must also have their own key lifecycle; never reuse a TLS private key as a token-signing key.

## 5. Tenant Onboarding

### 5.1. Overall Workflow

An onboarding workflow can include:

1. Receive request and create tenant in `REQUESTED` state.
2. Verify organization/administrator per registration process.
3. Create domain binding in `PENDING` state.
4. Issue ownership challenge and verify domain.
5. Configure DNS pointing to the platform ingress.
6. Provision TLS certificate and verify HTTPS.
7. Provision client registry, authorization/consent namespace, signing keys, and tenant policy.
8. Test discovery, authorization, tokens, and Resource Server validation.
9. Transition tenant to `READY`.
10. Admin or activation workflow transitions tenant to `ACTIVE`.

~~~mermaid
flowchart TD
    A["Tenant request"] --> B["Create REQUESTED tenant"]
    B --> C["Verify organization and domain"]
    C --> D{"Verification passed?"}
    D -->|No| E["FAILED / retry / expire"]
    D -->|Yes| F["Configure DNS"]
    F --> G["Issue TLS certificate"]
    G --> H["Provision tenant services and keys"]
    H --> I["Run readiness checks"]
    I --> J{"All checks pass?"}
    J -->|No| E
    J -->|Yes| K["READY"]
    K --> L["Explicit activation"]
    L --> M["ACTIVE"]
~~~

### 5.2. Idempotent Provisioning

Provisioning may be retried due to timeouts, worker restarts, or transient external API errors. Each step must be idempotent:

- Create tenant with an idempotency key.
- Create domain binding protected by a unique hostname constraint.
- Create signing keys using a stable key alias rather than generating a new key on every retry.
- Create clients/policies with stable identifiers.
- Look up existing certificate orders before submitting a new order.
- Persist workflow steps and external resource IDs to resume after restarts.

Never wrap DNS providers, ACME CAs, HSMs, and brokers inside a single long database transaction. This is a distributed workflow; use sagas/outbox, backoff retries, and appropriate compensation.

### 5.3. Readiness Checks Before Activation

Before a tenant becomes `ACTIVE`, verify:

- Domain ownership remains valid per policy.
- DNS resolves to the right ingress.
- TLS handshake succeeds and the certificate SAN includes the hostname.
- Discovery metadata returns the right issuer/endpoints.
- JWKS endpoint is reachable and contains the matching public keys.
- `RegisteredClient` lookups do not read across tenants.
- Authorization and consent stores use the right tenant namespace.
- Tokens are issued with the right issuer, audience, and tenant claims.
- Resource Server validates tokens and tenant binding successfully.
- Auditing/monitoring captures tenant context.

Do not check only for HTTP 200 on the login page. A working login page does not prove the token endpoint, discovery, JWKS, and tenant isolation are ready.

## 6. Verifying Custom Domain Ownership

### 6.1. DNS TXT Challenge

DNS TXT is a common method to prove a tenant controls a DNS zone. Workflow:

1. Tenant submits a hostname, e.g., `auth.acme.example`.
2. Server normalizes the hostname and checks that the domain can be registered.
3. Server generates a random challenge with sufficient entropy.
4. Server stores the challenge hash, tenant ID, hostname, expiry, and `PENDING` status.
5. Server instructs the tenant to create a TXT record under a fixed challenge name, e.g., `_platform-verify.auth.acme.example`.
6. Verification worker queries authoritative/recursive DNS per policy.
7. Compare TXT value against the pending challenge.
8. If matched, mark `VERIFIED` and record the verification timestamp.

Example:

~~~text
Name:  _platform-verify.auth.acme.example
Type:  TXT
Value: platform-domain-verification=7mK...random...Q2
~~~

The challenge must:

- Be generated with a cryptographically secure random generator.
- Have high entropy and be unpredictable.
- Be valid for only one tenant and one hostname.
- Have a short lifetime and be one-time use.
- Be stored safely; prefer storing a hash if plaintext retrieval is unnecessary.
- Be invalidated after verification or when the domain binding is canceled.

Never use a fixed static challenge string across all tenants.

### 6.2. HTTP Well-Known Challenge

Another option is requiring the tenant to serve a resource at a fixed challenge path, e.g.:

~~~text
https://auth.acme.example/.well-known/platform-domain-verification
~~~

The verification worker fetches the URL and verifies the body matches the challenge. This suits cases where a tenant can configure the web server but lacks DNS zone access.

Constrain outbound fetches:

- Fetch only the hostname being verified.
- Do not follow redirects to other IPs/hosts outside policy.
- Block private, loopback, link-local, and metadata service IPs.
- Guard against DNS rebinding during connection.
- Enforce timeouts, response size limits, and content-type checks.
- Allow HTTPS only with valid certificates as required by the challenge.

Without these controls, the domain verification endpoint can become an SSRF primitive.

### 6.3. Choosing a Verification Method

| Method | Suitable when | Limitations |
| --- | --- | --- |
| DNS TXT | Tenant manages the DNS zone. | Must wait for propagation/caches; record might be deleted later. |
| HTTP challenge | Tenant manages the web server at the hostname. | Must harden verifier against SSRF and redirect abuse. |
| CNAME delegation | Tenant points hostname to a platform-provided target. | Needs initial ownership proof and target lifecycle management. |
| Registrar/API integration | Platform integrates with domain providers. | Depends on provider support and API permissions. |

Never treat the fact that a hostname already points to the platform ingress as sufficient proof of tenant ownership; an attacker can configure a CNAME to an arbitrary service before any challenge occurs.

### 6.4. Normalizing Hostnames

Before storing/comparing hostnames:

1. Accept hostnames only, never full URLs with scheme/path/query.
2. Strip trailing dots per canonicalization policy.
3. Normalize casing to lowercase.
4. Convert Unicode domains to IDNA A-label form using a single consistent profile.
5. Validate label lengths and total hostname length.
6. Reject wildcards unless the product has a dedicated wildcard management workflow.
7. Reject IP literals, `localhost`, internal suffixes, and policy-disallowed domains.
8. Store the canonical ASCII hostname for unique constraints and routing.

Never write custom IDNA algorithms. Use battle-tested libraries/platform implementations while keeping the Unicode display form and ASCII canonical form clearly separated.

### 6.5. Domain Reservation and Anti-Takeover

When a tenant requests a hostname, create a reservation immediately to prevent two concurrent workflows from binding the same domain. Reservations have their own expiry and states:

- `PENDING_VERIFICATION`: awaiting challenge.
- `VERIFIED`: tenant proved control.
- `ACTIVE`: domain routed to tenant.
- `RELEASE_PENDING`: awaiting offboarding/cooldown.
- `RELEASED`: eligible for re-registration per policy.

When a tenant offboards, do not immediately release the hostname if DNS/TLS/proxies still point to the platform or cached mappings remain live. If a domain is released and later re-claimed by the old tenant or another party, domain takeover risks can affect callbacks, login pages, and issuer endpoints.

### 6.6. Re-Verifying Domains

Initial verification does not prove the tenant controls the domain forever. Depending on risk level, you can:

- Require re-verification when changing owners/admins or modifying domain bindings.
- Periodically verify DNS targets and certificates.
- Alert if TXT proof is deleted when policy requires continuous proof.
- Suspend the domain when DNS points to an out-of-policy target.
- Keep the domain binding in `SUSPENDED` state until re-verified.

Do not automatically delete a tenant just because a single DNS lookup fails; distinguish DNS propagation, resolver outages, and transient errors from genuine loss of control.

## 7. DNS and TLS Certificate Lifecycle

### 7.1. DNS Records

For tenant domains/subdomains, platforms typically require one of:

~~~text
auth.acme.example  CNAME  tenant-ingress.example.net
~~~

Or A/AAAA records pointing to an assigned ingress address. For apex/root domains, DNS providers may support ALIAS/ANAME or flattening because CNAME at a zone apex has limitations under DNS standards and providers.

DNS instructions must specify record name, record type, target/value, recommended TTL, whether old records must be removed, how to verify via DNS lookup, and when certificate issuance begins.

### 7.2. Verifying DNS

Do not query only a single resolver. You may need to check public recursive resolvers, authoritative nameservers, A and AAAA records, CNAME chains, TTL/propagation, and DNSSEC validation if enabled on the domain.

If the A record points to the right ingress while the AAAA record points to an old server, IPv6 clients will hit certificate or routing errors. Readiness checks should cover all record types supported by the ingress.

### 7.3. TLS Certificates

Once ownership verification and DNS readiness succeed, the workflow can request a certificate via ACME or a certificate provider:

~~~mermaid
sequenceDiagram
    autonumber
    participant T as Tenant
    participant D as DNS
    participant P as Platform
    participant CA as ACME CA
    T->>D: Create TXT ownership proof and CNAME/A record
    P->>D: Verify proof and ingress target
    P->>CA: Create certificate order
    CA->>D: DNS-01 challenge (if used)
    D-->>CA: TXT challenge response
    CA-->>P: Certificate issued
    P->>P: Store certificate reference
    P->>P: Bind SNI / ingress route
    P-->>T: Domain ready
~~~

Certificate lifecycles can include `PENDING`, `ISSUED`, `ACTIVE`, `RENEWING`, `FAILED`, `EXPIRED`, and `REVOKED`. Monitor expiry many days ahead, renew automatically, and alert on renewal failures.

### 7.4. Certificates and Signing Keys Are Two Different Key Types

TLS certificates protect HTTPS connections and prove the hostname at the TLS layer. Authorization Server signing keys sign JWTs/ID Tokens. Never share private keys simply because both belong to the same tenant.

TLS certificates contain SANs for hostnames; JWKs carry `kid`, `use`, `alg`, and corresponding public key parameters. The two have separate lifecycles, access permissions, and rotation procedures.

### 7.5. SNI and Certificate Selection

When multiple tenants use custom domains, the TLS terminator typically selects a certificate using Server Name Indication (SNI) in the TLS `ClientHello`. The domain registry/certificate manager must guarantee:

- The SNI hostname is verified and bound `ACTIVE`.
- The certificate SAN matches the hostname.
- The certificate is neither expired nor revoked.
- Unknown SNI never returns another tenant's certificate outside policy.
- During certificate renewal, routes update safely without disrupting handshakes.

If TLS terminates at a load balancer/CDN, clearly establish private key ownership and how certificates synchronize across edge locations.

### 7.6. Reverse Proxies and Forwarded Headers

Applications behind reverse proxies may receive `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and port headers. Trust only headers stripped and rewritten by a trusted proxy. Never let Internet clients send these headers directly to manipulate public URLs or issuers.

Safe flow:

1. Ingress accepts traffic from public networks per policy.
2. Ingress strips forwarded headers from the incoming request.
3. Ingress sets normalized scheme/host/port.
4. Application trusts headers only from authenticated proxy networks.
5. Tenant resolver validates the host against the domain registry.
6. Discovery/redirect URLs use verified canonical configuration.

Never enable forwarded-header processing blindly across all network interfaces.

## 8. Routing Requests to the Right Tenant

### 8.1. The Domain Registry Is the Source of Truth

The tenant resolver takes the canonical hostname and queries the domain registry:

~~~java
TenantDomainBinding binding =
    domainRegistry.findActiveByHostname(canonicalHost);

if (binding == null || !binding.isRoutable()) {
    throw new UnknownTenantDomainException(canonicalHost);
}

Tenant tenant = tenantRepository.findActive(binding.tenantId())
    .orElseThrow(UnknownTenantDomainException::new);
~~~

This is pseudocode. Lookups must verify both domain binding and tenant state. An `ACTIVE` domain belonging to a `SUSPENDED` tenant must still not be routed into protocol flows.

### 8.2. Request-Scoped Tenant Context

After resolution, bind the tenant context for the request duration:

~~~java
TenantContext context = tenantResolver.resolve(request);

try (TenantContextScope ignored = tenantContext.bind(context)) {
    filterChain.doFilter(request, response);
}
~~~

The context may include tenant ID, canonical domain, issuer, policy, and runtime references. Clear the context in `finally`/`close`. For async servlets, executors, or reactive flows, propagate the context using the corresponding mechanism; do not rely on `ThreadLocal` without a propagation strategy.

### 8.3. Do Not Fall Back to a Default Tenant

If a hostname is unregistered or its binding is suspended, return an appropriate error rather than routing to a default tenant. Falling back can expose another tenant's login page or metadata and create confusion in OIDC flows.

### 8.4. Preventing Host Header Poisoning

Never build redirect URLs, issuers, or discovery endpoints by directly concatenating the `Host` header:

~~~java
// Host is input for lookup only; issuer comes from verified configuration.
String issuer = tenantRegistry.require(tenantId).issuer();
~~~

Public URLs must come from verified tenant registry/configuration. The `Host` header is solely an input for looking up the binding, never a trusted data source.

### 8.5. Caching Domain Mappings

The domain registry can be cached to reduce lookups, but domain bindings and tenant states are security-sensitive data. When a domain transfers tenants, is suspended, or offboards:

- Evict both old and new hostname mappings.
- Broadcast invalidation events to all nodes.
- Use versions/generations to stop stale loaders from writing old mappings.
- If invalidation lag exceeds SLA, bypass the cache or reject hosts transitioning state.

Never cache mappings longer than reservation/binding policies allow.

## 9. Configuring Domains and Issuers in Spring Authorization Server

### 9.1. AuthorizationServerSettings

Spring Authorization Server uses `AuthorizationServerSettings` to configure the issuer and endpoint URIs. In a simple server context, settings are typically a static bean:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://login.example.com")
        .build();
}
~~~

This example configures a shared issuer. A tenant's custom login domain may be solely a presentation/login domain; changing the issuer is unnecessary if the shared issuer remains the trust identity clients use.

### 9.2. Multiple Domains with One Issuer

If multiple hostnames serve a single issuer:

- The domain registry maps hostnames to tenant/UI context.
- Issuer settings retain the shared canonical value.
- Discovery metadata must advertise the shared issuer.
- Endpoint URLs must be built from trusted public endpoint configuration.
- Clients must use the canonical issuer during discovery.

If a shared canonical endpoint is required, redirect UI pages or provide aliases per policy. Never synthesize discovery metadata with different issuers merely because requests arrive on different hostnames.

### 9.3. One Issuer per Tenant

If tenants have separate issuers, each request must resolve the right tenant-specific settings before endpoints needing the issuer execute. Never mutate a shared singleton `AuthorizationServerSettings` per request; two concurrent requests would overwrite each other's issuer.

Implementation approaches:

- Dedicated application context/filter chain per issuer.
- Tenant runtime registry with adapters/context designed for multi-issuer.
- Separate deployments per tenant or tenant group.

Test concurrent requests from two hostnames to prove issuers, endpoints, JWK sources, and core services never mix.

### 9.4. AuthorizationServerContext

Spring Authorization Server uses `AuthorizationServerContext` to supply issuer/settings to request processing. If extending context per tenant, it must be bound at the right point and scoped to the current request. Never modify global/static values or mutable singletons to switch issuers.

Specifically test the discovery endpoint, authorization responses and ID Tokens, JWT access token `iss`, token generator/`JWKSource`, metadata endpoint cache, error responses, and redirect URLs.

### 9.5. A Domain Change Is Not Automatically an Issuer Change

You can switch the login domain from `login.example.com` to `auth.acme.example` while keeping the issuer `https://login.example.com`. Clients continue discovering via the canonical issuer while users see the custom domain in their browsers.

If a contract requires the issuer itself to be the custom domain, plan a dedicated issuer migration. Never change the issuer mid-flight without updating clients, Resource Servers, discovery, JWKS, and token lifecycles.

## 10. Changing Domains

### 10.1. Adding a Domain Alias

When a tenant wants to add a domain:

1. Create a `PENDING` domain binding.
2. Verify ownership.
3. Confirm the hostname does not belong to another tenant.
4. Configure DNS and TLS.
5. Add mappings in ingress and tenant resolver.
6. Run readiness checks.
7. Transition the binding to `ACTIVE`.
8. Retain the old canonical domain until a cutover decision is made.

Never activate a domain before certificates and routing are ready.

### 10.2. Switching the Canonical Login Domain

When changing the primary domain:

1. Verify the new domain and issue a certificate.
2. Configure the new domain as an `ACTIVE` alias.
3. Test discovery/login/token flows per issuer policy.
4. Update UI links, email links, admin portal, and tenant configuration.
5. Switch the canonical login domain inside a versioned transaction.
6. Keep the old domain in alias/redirect state during the transition period.
7. Monitor callbacks, cookies, sessions, and OIDC errors.
8. Release the old domain only after dependencies clear and cooldown elapses.

Cookie domains, `SameSite`, `Secure`, redirect URIs, and browser sessions can all be impacted when hostnames change. Never assume cookies are shared between two different registrable domains.

### 10.3. If the Old Domain Is Also the Issuer

If the old domain is simultaneously the issuer, execute a protocol migration:

- Maintain old discovery/JWKS during the transition window.
- Publish the new issuer and new metadata.
- Update OIDC clients and Resource Server trusted issuers.
- Issue new tokens under the new issuer.
- Never rewrite `iss` on old tokens.
- Wait for old tokens to expire or revoke them per policy.
- Retire the old issuer once client/session/token dependencies are resolved.

An HTTP redirect from the old issuer to the new issuer cannot replace issuer validation; clients must know and trust the new issuer explicitly.

### 10.4. Transferring Domain Ownership

When a tenant transfers a domain to another organization:

- Require fresh ownership verification.
- Suspend the old domain binding.
- Revoke old certificates and routes in a safe order.
- Remove the association between the hostname and the old tenant.
- Enforce a cooldown before binding the hostname to another tenant.
- Audit callbacks/redirect URIs and custom domain references.

Never transfer a domain binding simply because an admin changed a display name or sent an unauthenticated email request.

## 11. Suspension, Reactivation, and Offboarding

### 11.1. Suspension

A tenant may be suspended due to tenant request, terms violations or security risks, billing/contract issues, expired domain verification, signing key/certificate compromise, or operational incidents.

When suspending, define exact handling for:

- Blocking new authorization requests.
- Blocking token issuance/refresh.
- Blocking dynamic client registration and configuration changes.
- Whether discovery/JWKS continue to be served.
- Whether the logout endpoint remains available to end sessions.
- Whether existing tokens/sessions are revoked.
- How Resource Servers treat existing tokens.

Do not assume blocking login automatically invalidates already-issued access tokens.

### 11.2. Per-Domain Suspension

If a custom domain suffers DNS/certificate issues while the tenant remains valid, suspend only that domain binding and continue serving via the platform domain. If the domain is taken over or points to an untrusted endpoint, remove the route/certificate promptly and alert the tenant.

Do not suspend an entire tenant when only one domain alias fails, unless that domain is the issuer or a mandatory security boundary.

### 11.3. Reactivation

Before reactivating:

1. Confirm suspension reasons have been resolved.
2. Re-verify the domain if ownership or DNS changed.
3. Check certificate and key status.
4. Confirm clients/redirect URIs were not altered improperly.
5. Review token/session policies and decide whether to force re-login.
6. Run readiness checks.
7. Record actor/reason and transition state using optimistic locking.

Never automatically become `ACTIVE` solely because billing or an external provider signals recovery.

### 11.4. Offboarding

Offboarding is an ordered workflow:

1. Transition tenant to `DECOMMISSIONING` and block new provisioning.
2. Block authorization/token issuance and client registration.
3. Disable client credentials and revoke clients if policy requires.
4. Revoke refresh tokens, authorizations, and sessions per retention/security policies.
5. Handle issued JWT access tokens according to published revocation strategies.
6. Remove domain routes and certificate bindings.
7. Retire signing keys per archival/audit procedures.
8. Export or retain audit data per contractual/regulatory requirements.
9. Delete or anonymize data once retention allows.
10. Release the domain after cooldown and verify no dependencies remain.
11. Transition tenant to `DELETED`.

### 11.5. Deleting a Tenant Is Not a Single DELETE Statement

Tenant data can span many systems: `RegisteredClient` records and client secrets; `OAuth2Authorization`, access/refresh tokens, and metadata; authorization consents; signing keys/HSM; TLS certificate manager; domain/DNS provider; caches and message brokers; audit logs, backups, and analytics; and Resource Server tenant registries.

The deletion workflow must track every external resource with retries. A single database `DELETE` does not automatically revoke certificates, DNS records, keys, or cache mappings.

### 11.6. Retention and Backups

Retention policies must specify:

- Which data is deleted immediately on offboarding.
- Which data is retained for auditing/investigation.
- Which tokens/secrets must be destroyed early.
- How long backups are retained before expiring.
- How deletions are re-applied when restoring backups.
- Which data must be anonymized rather than physically deleted right away.

Do not keep signing keys active solely to decrypt or verify old data unless explicitly required. Key archival and key destruction require separate policies.

## 12. Workflows, Transactions, and Events

### 12.1. Tenant Lifecycle Is a Distributed Workflow

Domain provisioning typically spans multiple systems: databases, DNS providers, ACME CAs, load balancers, HSM/KMS, and message brokers. You cannot assume a single ACID transaction spans all of them.

Use a saga/workflow featuring a workflow ID and idempotency key, step statuses and retry counts, external resource IDs, deadlines/expiries, compensation actions, audit events, and dead-letter/manual repair paths.

### 12.2. Transactional Outbox

When updating tenant/domain state in the database, write the event to an outbox in the same transaction:

~~~sql
CREATE TABLE tenant_outbox (
    event_id varchar(100) PRIMARY KEY,
    tenant_id varchar(100) NOT NULL,
    aggregate_type varchar(40) NOT NULL,
    aggregate_version bigint NOT NULL,
    event_type varchar(100) NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    published_at timestamptz
);
~~~

Example event:

~~~json
{
  "eventId": "evt-1002",
  "tenantId": "tenant-acme-001",
  "aggregateType": "TENANT_DOMAIN",
  "aggregateVersion": 8,
  "eventType": "DOMAIN_ACTIVATED",
  "domainId": "domain-42",
  "hostname": "auth.acme.example"
}
~~~

Events should never contain private keys, client secrets, or tokens. Domain hostnames may be public configuration data, yet still require policy-appropriate protection.

### 12.3. Idempotent Event Consumers

Consumers may receive duplicate events. Use event IDs, aggregate versions, and current state to guarantee:

- Activating a domain twice does not create two ingress routes.
- Retrying key provisioning does not generate a new random key alias.
- Duplicate domain removal does not accidentally delete another binding.
- Stale events do not move a tenant from `SUSPENDED` back to `ACTIVE`.

### 12.4. Compensation

If certificate issuance succeeds while key provisioning fails, the workflow can keep the domain in `PROVISIONING`/`FAILED` to retry, cancel the certificate order or revoke an unused issued certificate, temporarily remove the route, and keep the reservation so another tenant cannot claim the hostname mid-workflow.

Never compensate by deleting data still needed for circulating tokens if doing so breaks auditing or revocation handling.

## 13. Tenant Administration and Operational Security

### 13.1. Administrative Permission Separation

Separate roles:

- Tenant owner: manages profile and domains for their own tenant.
- Tenant administrator: manages users/clients per policy.
- Platform operator: manages tenant lifecycle and status.
- Security operator: suspends, revokes, and handles incidents.
- DNS/certificate service account: accesses only required domain/certificate resources.

A tenant admin must never bind a domain owned by another tenant, arbitrarily change issuers, or read another tenant's domain challenges.

### 13.2. Domain Challenges Must Resist Replay

Challenges must bind tenant ID, hostname, purpose, and expiry. Once used successfully, mark them consumed. If the tenant changes hostnames, issue a new challenge. Never allow one TXT record verifying hostname A to be reused to verify hostname B.

### 13.3. Rate Limiting and Abuse Controls

Tenant creation and domain verification endpoints can be abused to hoard reservations, flood DNS lookups, spam ACME orders, turn the HTTP verifier into an SSRF vector, or race-claim domain bindings.

Enforce rate limits per account, tenant, IP, and provider quota; cap pending domains; require approvals per threat model; and limit concurrent verifications.

### 13.4. Auditing

Audit tenant create/activate/suspend/reactivate/delete; domain add/verify/activate/change canonical/release; certificate issue/renew/revoke; issuer changes; signing key create/rotate/retire; client registration and secret rotation; and offboarding and data deletion.

Audits need actor, tenant ID, domain ID, timestamp, correlation ID, old/new states, and reason. Never log plaintext challenges, tokens, client secrets, or private keys.

## 14. Common Pitfalls

### Pitfall 1: Activating a Tenant Immediately Upon Creating the Database Row

**Symptom:** Endpoints are reachable for the tenant, yet discovery, keys, or certificates are not ready.

**Cause:** Provisioning is not separated from activation.

**Fix:** Use a `READY` state and readiness checks before `ACTIVE`.

### Pitfall 2: Treating DNS Pointing to Ingress as Ownership Proof

**Symptom:** A domain can be bound by someone who does not own it.

**Cause:** Missing challenge bound to tenant and hostname.

**Fix:** Use random, expiring, one-time-use DNS TXT/HTTP challenges.

### Pitfall 3: Equating Verification with TLS Readiness

**Symptom:** Domain is `VERIFIED`, yet browsers show certificate errors.

**Cause:** Certificate issuance/activation is not tracked separately.

**Fix:** Separate domain state machine and TLS readiness checks.

### Pitfall 4: Using the Host Header as the Issuer

**Symptom:** Tokens have unstable issuers or attackers control public URLs.

**Cause:** Trusting request headers instead of the issuer registry.

**Fix:** Take the issuer from verified configuration; use host only to look up bindings.

### Pitfall 5: Mutating an AuthorizationServerSettings Singleton per Request

**Symptom:** Acme requests receive Fabrikam's issuer or endpoints.

**Cause:** Shared mutable settings modified across concurrent requests.

**Fix:** Use properly designed tenant-specific runtime/context, or separate application contexts/deployments.

### Pitfall 6: Deleting Only the Domain Mapping During Offboarding

**Symptom:** Certificates, DNS, caches, or issuer endpoints remain active.

**Cause:** Offboarding does not track external resources.

**Fix:** Use a saga with a resource inventory, retries, and post-cleanup verification.

### Pitfall 7: Releasing a Domain Immediately

**Symptom:** Old domain gets bound to another tenant while caches/routes/callbacks still exist.

**Cause:** Missing cooldown and dependency checks.

**Fix:** Use `RELEASE_PENDING`, remove routes/certificates, flush caches, verify completion, then release.

### Pitfall 8: Suspending Login Only While Leaving Refresh Tokens Active

**Symptom:** Tenant is suspended, yet clients still refresh and obtain new tokens.

**Cause:** Blocking only the authorization endpoint.

**Fix:** Enforce tenant status on token endpoint, refresh, client auth, and related grants.

### Pitfall 9: Assuming Revocation at the Authorization Server Revokes Offline JWTs

**Symptom:** Resource Servers still accept previously issued JWTs.

**Cause:** APIs only verify signatures and expiry locally.

**Fix:** Use introspection, denylist/version checks, or short TTLs as required.

### Pitfall 10: Inconsistent Normalization of Unicode Domains

**Symptom:** The same display domain creates two bindings or compares inconsistently.

**Cause:** Not using a canonical IDNA representation.

**Fix:** Use an IDNA library, store A-labels, and enforce unique constraints on canonical hostnames.

### Pitfall 11: Certificate Renewal Failures Without Alerts

**Symptom:** A custom domain's certificate expires unexpectedly.

**Cause:** Certificates checked only during onboarding.

**Fix:** Monitor expiry, renew ahead of schedule, alert on failures, and have a policy-defined fallback domain.

### Pitfall 12: Async Workers Processing Stale Events

**Symptom:** Tenant is `SUSPENDED`, yet an old event reactivates the domain.

**Cause:** Consumer ignores aggregate version/current state.

**Fix:** Enforce monotonic versions, idempotency keys, and transition guards.

## 15. Test Matrix

| Case | Expected outcome |
| --- | --- |
| Create new tenant | `REQUESTED`, does not serve traffic yet. |
| Valid verification | Domain becomes `VERIFIED` and workflow proceeds. |
| Expired challenge | Does not activate; generates new challenge per policy. |
| Tenant A's TXT challenge used for Tenant B | Rejected. |
| HTTP challenge redirects to private IP | Verifier blocks request. |
| Two tenants register the same hostname | Unique constraint/reservation lets only one tenant succeed. |
| Unicode/punycode hostname | Consistent canonicalization; no duplicate bindings. |
| DNS A valid, AAAA wrong | Readiness fails or warns per ingress policy. |
| Certificate SAN mismatch | Domain does not become `ACTIVE`. |
| Certificate renewal | New certificate binds without downtime. |
| Unknown SNI/Host | Does not return another tenant's certificate/mapping. |
| Forged forwarded header | Does not alter tenant, issuer, or public URL. |
| `READY` tenant | Does not receive traffic before explicit activation. |
| `SUSPENDED` tenant | Issues no new authorizations/tokens per policy. |
| Domain suspended, tenant active | Other domains continue serving if policy allows. |
| Tenant reactivation | Runs readiness checks and audits actor/reason. |
| Domain change with issuer unchanged | Clients still validate issuer; new login domain works. |
| Issuer migration | Clients/resource servers trust new issuer in phases; old tokens never have `iss` altered. |
| Offboarding | Clients/tokens/domains/keys handled per workflow. |
| Duplicate/out-of-order events | No duplicate resources created or stale state re-activated. |
| Worker restarts mid-provisioning | Retries resume from the saved step. |
| Domain release cooldown | Hostname cannot be rebound before cleanup completes. |
| Cross-tenant lookup | Cannot access another tenant's clients, authorizations, or domains. |

## 16. Production Checklist

| Item | Condition to confirm |
| --- | --- |
| Tenant state machine | States, transition guards, and actor/reason/version tracking exist? |
| Domain state machine | Verification, DNS, certificates, and bindings managed separately? |
| Tenant ID | Immutable and never reused? |
| Domain canonicalization | Lowercase, IDNA A-label, trailing dot, and validation consistent? |
| Ownership proof | Random, tenant-bound, hostname-bound, expiring, one-time challenge? |
| Reservation | Unique hostname and reservation expiry preventing races? |
| DNS | Clear guidance for A/AAAA/CNAME/TXT, TTL, and propagation? |
| TLS | Certificate SAN, SNI, renewal, and private key storage verified? |
| Proxy | Forwarded headers trusted only from trusted proxies? |
| Routing | Unknown/suspended domains fail closed with no tenant fallback? |
| Issuer | Canonical issuer independent of request `Host`? |
| SAS configuration | Singleton settings never mutated per request to switch issuer? |
| Provisioning | Idempotent, retryable, and supports compensation? |
| Persistence | Client/authorization/consent namespaces partitioned by tenant? |
| Key lifecycle | TLS keys and token-signing keys strictly separated? |
| Domain change | Alias/cutover/cooldown and separate issuer migration defined? |
| Suspension | Blocks authorization, token, refresh, and DCR per policy? |
| Offboarding | Handles tokens, sessions, keys, certificates, DNS, caches, and retention? |
| Auditing | Records actor, old/new states, reason, version, and correlation ID? |
| Observability | Monitors certificate expiry, DNS mismatch, provisioning backlog, and event lag? |
| Recovery | Retry/manual repair paths and runbooks for external provider failures? |
| Tests | Covers SSRF, domain takeover, `Host` poisoning, cross-tenant, and concurrency tests? |

## 17. Practice Exercise

A SaaS platform has 5,000 tenants running Spring Authorization Server across three deployment regions. Each tenant gets a default subdomain; some tenants pay extra for custom domains. The platform uses a shared issuer `https://login.example.com`. Custom domains require automated TLS. Tenants can be suspended for billing or security incidents.

Design:

1. The tenant state machine and domain state machine.
2. Tenant/domain schema with unique hostname reservation and optimistic versioning.
3. DNS TXT challenge with expiry, one-time use, and retries.
4. HTTP verification worker with SSRF protection.
5. DNS readiness and TLS certificate lifecycle.
6. SNI/ingress mapping and trusted forwarded-header policy.
7. Tenant resolver without fallback when hostnames are unknown/suspended.
8. Workflow for adding domain aliases and switching the canonical login domain.
9. How to keep the shared issuer while changing custom login domains.
10. An issuer migration plan if a tenant later requires a dedicated issuer.
11. Suspension/offboarding workflow covering tokens, sessions, keys, certificates, DNS, and retention.
12. Transactional outbox, idempotent workers, and compensation for ACME/HSM failures.
13. Metrics/SLOs for certificate renewal, provisioning latency, and domain routing.
14. Integration tests for two tenants registering the same hostname and `Host`/`X-Forwarded-Host` poisoning tests.

**Acceptance criteria:** Tenants become `ACTIVE` only after readiness checks; domains route only after ownership verification and TLS readiness; domain mappings come from a trusted registry; issuers are never built from the `Host` header; suspension/offboarding handles both tokens and external resources; retries never create duplicate resources.

## 18. References

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer, Provider Configuration, and discovery endpoints.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer and metadata endpoints.
- [RFC 1034 — Domain Names: Concepts and Facilities](https://www.rfc-editor.org/rfc/rfc1034) and [RFC 1035 — Domain Names: Implementation and Specification](https://www.rfc-editor.org/rfc/rfc1035): DNS naming, records, and resolution.
- [RFC 8555 — Automatic Certificate Management Environment (ACME)](https://www.rfc-editor.org/rfc/rfc8555): certificate orders and challenge lifecycles.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): authority/`Host` and HTTP request semantics.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): configuring Authorization Server and endpoint settings.
- [Spring Authorization Server 1.5.8 — AuthorizationServerSettings Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.html): issuer and endpoint configuration.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, authorization, consent, and core service contracts.
- [Spring Framework — ForwardedHeaderFilter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html): handling proxy forwarded headers and trust boundary limits.
- [Spring Authorization Server 1.5.8 — AuthorizationServerContext Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/context/AuthorizationServerContext.html): context providing issuer and `AuthorizationServerSettings` in a request.
- [Let's Encrypt — Challenge Types](https://letsencrypt.org/docs/challenge-types/): HTTP-01 and DNS-01 challenges for TLS certificate issuance.
- [Let's Encrypt — Certificate Renewal](https://letsencrypt.org/docs/renewal/): automated certificate renewal and operating an ACME client.
