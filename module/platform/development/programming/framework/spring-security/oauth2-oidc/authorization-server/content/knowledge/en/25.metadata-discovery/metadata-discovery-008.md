# Discovery Behind a Reverse Proxy, Custom Domains, and Multi-Issuer Environments

## 1. Why Does Discovery Easily Break in Real Deployments?

In the **Metadata and Discovery** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson addresses a production problem: **the Authorization Server runs inside Kubernetes, behind a reverse proxy or load balancer, while OAuth 2.0/OIDC clients must see the exact public issuer and endpoints; when multiple tenants or custom domains coexist, each issuer must be clearly isolated**.

This content serves the module objective: **learning how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in Spring Boot**.

For example, Spring Boot listens internally at `http://auth-service:9000`, while ingress serves the public URL `https://login.example.com`. If metadata returns:

~~~json
{
  "issuer": "http://auth-service:9000",
  "token_endpoint": "http://auth-service:9000/oauth2/token",
  "jwks_uri": "http://auth-service:9000/oauth2/jwks"
}
~~~

then clients cannot reach the endpoints, the issuer mismatches security configuration, and token validation fails. Even worse is letting the server construct the issuer arbitrarily from `Host` or `X-Forwarded-Host`: an attacker can make metadata and trust boundaries carry an uncontrolled domain.

**Target outcome:** understand the discovery standards, configure public issuers and reverse proxies, choose between custom-domain/multi-issuer models, design an issuer-scoped registry, verify metadata/JWT/JWKS consistency, test against spoofed hostnames, and perform domain changes safely.

## 2. Discovery Standards and URL Differences

Two closely related mechanisms that are not identical:

1. **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** publishes OAuth Authorization Server capabilities and endpoints.
2. **OpenID Connect Discovery 1.0 — OpenID Provider Configuration:** publishes OpenID Provider metadata, including OIDC endpoints and ID Token capabilities.

### 2.1. When the Issuer Has No Path

Suppose the official issuer is:

~~~text
https://login.example.com
~~~

Common URLs:

| Metadata | URL |
| --- | --- |
| OAuth 2.0 Authorization Server Metadata | `https://login.example.com/.well-known/oauth-authorization-server` |
| OIDC Provider Configuration | `https://login.example.com/.well-known/openid-configuration` |

In Spring Authorization Server, the OAuth metadata endpoint is provided by the Authorization Server Metadata mechanism; OIDC Provider Configuration requires **enabling OpenID Connect support**. Do not treat the presence of `/oauth2/jwks` or `/oauth2/token` as proof that the OIDC discovery endpoint is enabled.

### 2.2. When the Issuer Has a Path

Example:

~~~text
https://identity.example.com/tenant/acme
~~~

**Distinguish the well-known URL construction rules of the two standards:**

| Standard | URL per Corresponding Rule |
| --- | --- |
| RFC 8414 OAuth metadata | `https://identity.example.com/.well-known/oauth-authorization-server/tenant/acme` |
| OIDC Discovery 1.0 | `https://identity.example.com/tenant/acme/.well-known/openid-configuration` |

RFC 8414 inserts the well-known path between the authority and the issuer path; OIDC Discovery appends `/.well-known/openid-configuration` after the issuer (stripping any trailing slash). Because specs and libraries vary in compatibility behavior, **do not assume all clients probe the exact same URL**, especially for issuers with paths. Verify actual discovery with your deployed Spring Authorization Server and client library versions.

### 2.3. Metadata URL Does Not Necessarily Equal Issuer

**Issuer** is a trusted identifier, not the name of a metadata file. A client hits the metadata URL to fetch JSON, then must verify that the JSON `issuer` field **matches the exact issuer the client intends to trust**. A website returning valid JSON at a URL is never enough for a client to trust an arbitrary issuer advertised in that JSON.

A redirect from an old discovery URL to a new discovery URL does not turn tokens signed by the old issuer into tokens of the new issuer. That is an identity and trust-policy change requiring dedicated design.

## 3. Metadata Contents Must Be Consistent

Example **OAuth 2.0 Authorization Server Metadata** for a public issuer:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "jwks_uri": "https://login.example.com/oauth2/jwks",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "code_challenge_methods_supported": ["S256"],
  "revocation_endpoint": "https://login.example.com/oauth2/revoke",
  "introspection_endpoint": "https://login.example.com/oauth2/introspect"
}
~~~

**This is an illustrative sample**, not a guarantee that the framework emits these exact fields/grants/client authentication methods. Only advertise features the Authorization Server truly supports and has configured. Actual endpoint URLs can also be customized via `AuthorizationServerSettings`.

Key fields:

| Field | What Clients Use It For | Risk If Wrong |
| --- | --- | --- |
| `issuer` | Establish Authorization Server identity | Wrong trust domain, token `iss` mismatch |
| `authorization_endpoint` | Send browser to authorization flow | Redirects to internal host or wrong tenant |
| `token_endpoint` | Exchange codes, refresh, or other grants | Clients send credentials/codes to the wrong host |
| `jwks_uri` | Fetch public keys to verify JWTs | Signature verification fails or uses wrong tenant key |
| `revocation_endpoint` | Revoke tokens | Logout ineffective or tokens sent to wrong domain |
| `introspection_endpoint` | Query token active status | Resource Server gets wrong active/trust result |
| `grant_types_supported` | Learn grants advertised by the server | Clients attempt unenabled grants |
| `token_endpoint_auth_methods_supported` | Learn client auth methods | Clients try incompatible secrets/JWT/mTLS |
| `code_challenge_methods_supported` | Learn PKCE methods | Clients use unsupported methods |

### 3.1. OIDC Provider Configuration

When OpenID Connect is enabled, Provider Configuration adds characteristic fields such as:

- `userinfo_endpoint`: endpoint returning user claims per granted permissions.
- `subject_types_supported`: supported subject types.
- `id_token_signing_alg_values_supported`: ID Token signing algorithms.
- `end_session_endpoint` when the server supports and advertises logout.
- `scopes_supported` may include `openid` and enabled OIDC scopes.

Shared fields such as `issuer`, `jwks_uri`, `authorization_endpoint`, and `token_endpoint` must stay consistent between OAuth/OIDC metadata and with issued tokens themselves.

### 3.2. Discovery Does Not Grant Permissions Automatically

Metadata is typically publicly accessible, yet advertising a grant or scope **does not mean every `RegisteredClient` may use that grant or scope**. Actual permissions are still governed by `RegisteredClient`, client authentication, authorization consent, and business policy.

Similarly, having `jwks_uri` in metadata does not make a `JWKSource` trustworthy if the client/Resource Server skips checking issuer, signature algorithm, and key suitability.

## 4. Boundary Between Public Origin and Internal Addresses

Real deployments typically span multiple addresses:

~~~mermaid
flowchart LR
    C["Browser / OAuth Client"] -->|"HTTPS https://login.example.com"| LB["Trusted Ingress / Reverse Proxy"]
    LB -->|"Internal HTTP or TLS<br/>auth-service:9000"| AS["Spring Boot Authorization Server"]
    AS -->|"DB / Key Store"| S["Authorization Store + JWK source"]
    LB -.->|"Sanitized Forwarded/X-Forwarded-*"| AS
~~~

| Component | Example Value | Safe as Public Issuer? |
| --- | --- | --- |
| External scheme | `https` | Yes |
| External host | `login.example.com` | Yes, if approved |
| External port | `443` (usually omitted) | Yes, when the issuer requires a non-default port |
| Internal service | `auth-service` | No |
| Internal port | `9000` | No |
| Pod IP | `10.10.4.12` | No |
| Namespace/cluster DNS | `auth-service.security.svc` | No |

**The issuer must not depend on Pod/Service names or headers controlled by external callers.** For a stable public issuer, explicit configuration prevents metadata from changing across restarts, scaling, or ingress updates.

## 5. Configuring a Fixed Issuer in Spring Authorization Server

For a single public domain, configure `AuthorizationServerSettings` explicitly:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
public class PublicIssuerConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://login.example.com")
                .build();
    }
}
~~~

With the issuer configured as above, the goal is to guarantee metadata and JWT `iss` claims both use `https://login.example.com`, never `http://auth-service:9000`.

Spring Authorization Server can infer the issuer from incoming requests when not pinned, depending on the version. While helpful in certain scenarios or multi-issuer setups, **never let an uncontrolled host/proxy dictate the trust domain**. For single-issuer production, pinning a fixed issuer and verifying outputs is far easier to audit.

### 5.1. Enabling OIDC Discovery When Needed

Example Authorization Server filter chain configuration using matching Spring Security/Spring Authorization Server 1.x APIs:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults()));

    // Add authentication/entry point and required beans in a real application.
    return http.build();
}
~~~

This is an **intentionally minimal configuration snippet**, not a complete production-ready Authorization Server. A real application also requires `RegisteredClientRepository`, `OAuth2AuthorizationService`, signing keys/`JWKSource`, a login chain, and user authentication configuration. `oidc(Customizer.withDefaults())` enables OIDC support; do not enable OIDC just to emit OAuth2 metadata if your application does not provide OIDC.

### 5.2. Custom Endpoints and Issuer Must Share the Same Domain

If you need to customize the Token Endpoint or JWK Set Endpoint, configure `AuthorizationServerSettings` accordingly:

~~~java
AuthorizationServerSettings settings =
        AuthorizationServerSettings.builder()
                .issuer("https://login.example.com")
                .authorizationEndpoint("/oauth2/authorize")
                .tokenEndpoint("/oauth2/token")
                .jwkSetEndpoint("/oauth2/jwks")
                .tokenRevocationEndpoint("/oauth2/revoke")
                .tokenIntrospectionEndpoint("/oauth2/introspect")
                .build();
~~~

The paths in this example illustrate common defaults. When changing paths, check compatibility with ingress rewrites, discovery, HTTP security matchers, clients, and Resource Servers. Never change a URL solely in metadata JSON while leaving the filter chain listening on the old path.

## 6. Reverse Proxies and Forwarded Headers

A proxy may accept HTTPS externally and forward HTTP to Spring Boot internally. Without forwarded-header handling, the application sees scheme `http`, host `auth-service`, and port `9000`.

Common headers:

~~~http
Forwarded: proto=https;host=login.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: login.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /auth
~~~

`Forwarded` is standardized in RFC 7239; `X-Forwarded-*` are de facto headers injected by proxies. These values are trustworthy only when **a trusted ingress verifies, strips client-sent values, and sets them anew**. Headers themselves are unsigned and prove nothing about trust on their own.

### 6.1. Spring Boot Forwarded-Header Strategy

Example when the application sits behind a trusted proxy and needs Spring to process scheme/host/port:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

`framework` generally uses Spring's forwarded-header handling, such as `ForwardedHeaderFilter` in Servlet applications. Depending on the environment, `native` lets the servlet container process forwarded headers. **Which strategy is right must be verified against your actual embedded server, ingress, and Spring Boot version.**

| Strategy | General Meaning | What to Test |
| --- | --- | --- |
| `none` | Do not use forwarded headers for request origin | Does the app emit internal HTTP URLs? |
| `native` | Use container-native support when available | Are proxy trust, host, scheme, and path prefix handled properly? |
| `framework` | Use Spring's `Forwarded`/`X-Forwarded-*` handling | Are headers sanitized and prefixes applied consistently? |

Do not configure both the proxy and the application in a way that **double-applies** scheme, host, or prefix. Likewise, never rely on `ForwardedHeaderFilter` as a "security control" against externally forged headers—it is a request-interpretation mechanism, **not a proxy authenticator**.

### 6.2. Rules at Ingress

The ingress/reverse proxy should:

1. Accept only allowlisted hostnames/public routes with valid TLS certificates.
2. **Strip** `Forwarded`/`X-Forwarded-*` (or equivalent headers) sent by internet clients.
3. Set or overwrite those headers from the verified TLS/public connection.
4. Allow the backend to receive traffic only from authorized proxies; block direct access bypassing ingress.
5. Protect the proxy → backend link per your threat model, typically via network policies and internal TLS/mTLS.
6. Align path rewrites, redirects, and forwarded prefixes.
7. Never accept arbitrary hosts and let the backend synthesize issuers for them.

**No `server.forward-headers-strategy` setting implements all seven steps on its own.** Those responsibilities belong to ingress infrastructure and security policy.

### 6.3. Watch Out for Host Header Injection

Malicious request example:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: attacker.example
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
~~~

If the server reflects `attacker.example` into `issuer`, `authorization_endpoint`, or `jwks_uri`, clients can be steered to untrusted endpoints. The system must reject unapproved hosts at ingress/app before building metadata. In single-issuer setups, pinning a fixed issuer sharply reduces this risk, though safe host routing is still required.

## 7. Context Paths, Prefixes, and Rewrites

Two common architectures must be distinguished:

### 7.1. External Path Matches Internal Path

~~~text
Public:   https://login.example.com/oauth2/token
Internal: http://auth-service:9000/oauth2/token
~~~

This is usually the simplest model. Ingress translates only scheme/host/port without changing the path; `AuthorizationServerSettings` can keep default paths.

### 7.2. External Prefix Differs from Internal Path

~~~text
Public:   https://id.example.com/auth/oauth2/token
Internal: http://auth-service:9000/oauth2/token
~~~

In this model, the proxy strips `/auth` when forwarding, while metadata must publish URLs with `/auth` per the public contract. `X-Forwarded-Prefix` can help, yet actual behavior depends on filters, container, routes, and versions.

Typical incident:

- Browser calls `https://id.example.com/auth/oauth2/authorize`.
- Metadata advertises `https://id.example.com/oauth2/token`.
- Ingress routes only `/auth/**` to the Authorization Server.
- Authorization Code Flow fails at the code-exchange step.

**Never "fix" this by exposing arbitrary unauthenticated paths.** Decide path ownership, proxy rewrites, base URLs, and security matchers clearly, then test the exact public URLs.

### 7.3. Issuer Path Differs from Proxy Prefix

A path-based issuer, such as `https://id.example.com/tenant/acme`, is an **identity component** under OAuth/OIDC specs. A proxy prefix `/auth` is a **routing detail**. Both may appear together, yet they should not be conflated automatically.

| Element | Example | Role |
| --- | --- | --- |
| Issuer | `https://id.example.com/tenant/acme` | Authorization Server/tenant identifier |
| External route prefix | `/auth` | Application mount point behind ingress |
| Internal servlet context path | `/` | Internal mount point |
| Token Endpoint | `https://id.example.com/auth/tenant/acme/oauth2/token` if designed and supported | URL clients actually call |

If a deployment cannot keep issuer, metadata, and endpoints consistent under a prefix, consider **using a dedicated hostname** instead of complex rewrites.

## 8. Custom Domains: Alias or New Issuer?

Suppose a tenant wants to use:

~~~text
https://login.customer.example
~~~

instead of the shared domain:

~~~text
https://login.saas.example
~~~

There are two very different architectural choices.

### 8.1. Custom Domain Is Only an Entry Alias; Issuer Stays Fixed

Clients may reach the custom domain, while tokens still carry `iss=https://login.saas.example` and discovery returns that canonical issuer. This can be a valid **alias/routing** setup if client discovery and trust contracts are clearly specified, though it easily causes confusion if clients assume the custom domain is the issuer.

Do not place the alias hostname into the `issuer` field just because the request arrived on the alias. Maintain one **canonical issuer** and instruct clients to always validate tokens against it.

### 8.2. Custom Domain Becomes a True Issuer

When `iss=https://login.customer.example` is required, it is a **distinct issuer**. You need:

- Valid TLS certificate for the custom domain (including renewal/revocation plans).
- DNS/CNAME setup, domain ownership verification, and host allowlisting.
- Metadata returning that exact issuer on that domain.
- Endpoints and `jwks_uri` aligned with the domain/tenant.
- Keys and authorization data scoped to the issuer/tenant per policy.
- Resource Servers/clients validating that exact issuer.
- Safeguards preventing tenant A from claiming tenant B's domain or metadata.

**A custom domain is not just a CNAME change.** It can be a security-identity change affecting token validation, logout, redirect URIs, and OAuth client registrations.

### 8.3. Never Trust a Domain Just Entered in an Admin Form

When a tenant registers a custom domain, verify domain ownership, configure certificates, update allowlists, handle DNS takeover risks, and define ownership-transfer procedures. **Never issue tokens under an unapproved issuer** merely because an HTTP request carries that hostname.

## 9. Multi-Issuer Models: Dedicated Domains vs. Tenant Paths

A multi-tenant system can structure issuers as:

~~~text
https://auth.example.com/tenant/acme
https://auth.example.com/tenant/zen
~~~

or:

~~~text
https://login.acme.example.com
https://login.zen.example.com
~~~

Each issuer is a **trust domain**. It needs explicit mapping to its tenant, registered clients, authorization records, and signing keys per architecture.

### 9.1. Comparing the Models

| Model | Advantages | Risks / Trade-offs |
| --- | --- | --- |
| Single issuer for all tenants | Simple for clients/JWKS; centralized operations | Tenant separation relies mainly on claims, DB, and policy; wider blast radius |
| Multiple issuers on one host via path | Single domain; path separates issuers | Non-trivial discovery path rules; complex routing and data lookups |
| Multiple issuers via subdomain/custom domain | Clear hostname boundary; strong branding | More TLS/DNS, onboarding, host allowlist, and certificate lifecycle work |
| One deployment per issuer | Strongest key, data, and config isolation | Higher operational and deployment cost |

There is no single default best option for every system; what matters is that the issuer boundary is enforced **consistently from metadata through tokens to Resource Servers**.

### 9.2. Spring Authorization Server and Multiple Issuers

Spring Authorization Server versions with multi-issuer support allow hosting multiple issuers on the same host, e.g., via `AuthorizationServerSettings`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class MultiIssuerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .multipleIssuersAllowed(true)
                .build();
    }
}
~~~

**Precondition:** use this API only if your running Spring Authorization Server version provides `multipleIssuersAllowed` and your request routing model aligns with it. When multi-issuer mode is enabled, you must supply **tenant-aware** components; toggling the flag while sharing every repository and key provides no isolation.

Do not simultaneously pin a static issuer like `https://login.example.com` for all requests while expecting metadata to turn into `https://login.example.com/tenant/acme`. Explicitly choose either a static single issuer or dynamic multi-issuer setup and test the contract.

### 9.3. Isolating Components by Issuer

Components typically designed per issuer:

- `RegisteredClientRepository`: client registrations for each tenant.
- `OAuth2AuthorizationService`: authorization and token state belonging to that tenant.
- `OAuth2AuthorizationConsentService`: user–client consent scoped to the tenant.
- `JWKSource<SecurityContext>` and signing key policy: separate keys per issuer when cryptographic isolation is desired.
- `JwtDecoder` and related validation policies, especially for OIDC/UserInfo/introspection.
- User authentication, identities, login branding, session/tenant mapping, and auditing.

Never assume identical `client_id` values across two tenants refer to the same client. Namespace data by issuer or tenant ID. If keys are shared for operational reasons, back that decision with its own threat model, key rotation plan, and blast-radius analysis.

## 10. Issuer Registry: Allowlist Instead of Host Reflection

A safe two-step design:

1. **The proxy validates allowed public hosts/paths**; the app never accepts arbitrary hosts.
2. **A server-side issuer registry** maps approved exact issuers to tenant configurations.

Pure Java 17 example for an HTTP-independent registry:

~~~java
import java.util.Map;
import java.util.Objects;

public final class ApprovedIssuerRegistry<T> {

    private final Map<String, T> byIssuer;

    public ApprovedIssuerRegistry(Map<String, T> registeredIssuers) {
        this.byIssuer = Map.copyOf(registeredIssuers);
    }

    public T requireIssuer(String issuer) {
        Objects.requireNonNull(issuer, "issuer");
        T component = byIssuer.get(issuer);
        if (component == null) {
            throw new IllegalArgumentException("Unapproved issuer");
        }
        return component;
    }
}
~~~

Usage:

~~~java
ApprovedIssuerRegistry<TenantComponents> registry =
        new ApprovedIssuerRegistry<>(Map.of(
                "https://auth.example.com/tenant/acme", acmeComponents,
                "https://auth.example.com/tenant/zen", zenComponents));

// Issuer must be resolved from the request using trusted configuration,
// then checked against the allowlist before selecting tenant components.
TenantComponents components = registry.requireIssuer(resolvedIssuer);
~~~

`TenantComponents` is an application-defined type; `resolvedIssuer` must come from a trusted resolver, never a raw `Host` or query parameter. This registry illustrates the **exact issuer allowlist** principle, not a complete multi-tenant authorization server.

### 10.1. Spring Authorization Server Context

Inside the `SecurityFilterChain` handling Authorization Server requests, the context exposes the issuer to components:

~~~java
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContext;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;

AuthorizationServerContext serverContext =
        AuthorizationServerContextHolder.getContext();
String issuer = serverContext.getIssuer();

TenantComponents tenant =
        approvedIssuerRegistry.requireIssuer(issuer);
~~~

This snippet illustrates usage **inside a component/provider running within a request context**. Never call `AuthorizationServerContextHolder` from background threads or startup code assuming a context is always populated. Handle null contexts, startup paths, and any out-of-band tenant resolution explicitly.

### 10.2. Never Select a Tenant Solely from an Unverified Token

In introspection, token exchange, or Resource Servers, never decode a JWT and immediately trust its `iss` to fetch whatever JWKS URL the token suggests. Instead, select only among issuers **already in the approved registry**, then verify signature, algorithm, audience, timestamps, and status.

A token signed by issuer Acme must never be accepted in tenant Zen simply because both issuers share a host, key, or `sub` claim.

## 11. Routing Metadata, OAuth Endpoints, and JWKS per Tenant

A tenant needs more than a different JSON `issuer`. Clients need **complete routing** to the Authorization Endpoint, Token Endpoint, JWKS, Introspection, and Revocation for that exact issuer, all reachable over the public TLS domain.

Suppose an organization chooses path-based issuers:

~~~text
Tenant Acme issuer: https://auth.example.com/tenant/acme
Tenant Zen  issuer: https://auth.example.com/tenant/zen
~~~

**Illustrative URL design**:

| Component | Acme | Zen |
| --- | --- | --- |
| Issuer | `https://auth.example.com/tenant/acme` | `https://auth.example.com/tenant/zen` |
| OAuth metadata RFC 8414 | `https://auth.example.com/.well-known/oauth-authorization-server/tenant/acme` | `https://auth.example.com/.well-known/oauth-authorization-server/tenant/zen` |
| OIDC metadata | `https://auth.example.com/tenant/acme/.well-known/openid-configuration` | `https://auth.example.com/tenant/zen/.well-known/openid-configuration` |
| Authorization Endpoint | `https://auth.example.com/tenant/acme/oauth2/authorize` | `https://auth.example.com/tenant/zen/oauth2/authorize` |
| Token Endpoint | `https://auth.example.com/tenant/acme/oauth2/token` | `https://auth.example.com/tenant/zen/oauth2/token` |
| JWK Set Endpoint | `https://auth.example.com/tenant/acme/oauth2/jwks` | `https://auth.example.com/tenant/zen/oauth2/jwks` |

**Important:** this is an **architectural target URL contract**, not a guarantee that a given Spring Authorization Server version listens on all these paths by default. In particular, well-known rules, path-based multi-issuer handling, and proxy rewrites must be verified against your actual version and components. If a deployment cannot keep all endpoints consistent, choose simpler routes or separate deployments.

### 11.1. Map the Same Issuer Across All Endpoints

A request to `/tenant/acme/oauth2/token` must never fall into Zen's `RegisteredClientRepository` because a filter or repository used a shared singleton without tenant selection. Similarly:

- Authorization Codes issued by Acme must be exchanged at Acme's Token Endpoint.
- Client `redirect_uri`s must be registered in the matching tenant.
- Acme authorizations/consents must never be read or written under tenant Zen.
- Acme's JWKS must never silently serve Zen's keys when policy requires key isolation.
- Introspection/revocation must verify both client and token belong to the same trust domain.

### 11.2. Safe Routing Pattern

~~~mermaid
flowchart TD
    A["HTTPS request arrives at trusted ingress"] --> B{"Public host/path in allowlist?"}
    B -->|No| X["404 / 400, do not construct issuer"]
    B -->|Yes| C["Route to Authorization Server"]
    C --> D["Resolver determines exact issuer"]
    D --> E{"Issuer exists in registry?"}
    E -->|No| Y["Reject, audit request"]
    E -->|Yes| F["Select tenant repositories and key policy"]
    F --> G["Handle discovery / authorize / token / JWKS"]
    G --> H["Verify response issuer and endpoint URLs"]
~~~

Never fall back to "if tenant not found, serve the default tenant's metadata." Fallbacks can cause tokens, keys, or client credentials from multiple tenants to mix.

### 11.3. Does Multi-Issuer Require Multi-Key?

Separate key sets are not strictly mandatory in every scenario, yet **key separation per issuer** reduces blast radius and limits the risk of loosely configured verifiers accepting cross-tenant tokens. If signing keys are shared, Resource Servers must still enforce exact `iss`, audience, and tenant policy. Identical keys never merge two issuers into one trust domain.

## 12. JWK Set URI and Key Lifecycle Behind a Proxy

The `jwks_uri` field in metadata points to **public keys** used by clients and Resource Servers to verify tokens or ID Tokens per contract.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client / Resource Server
    participant P as Public HTTPS Ingress
    participant AS as Authorization Server
    C->>P: GET /.well-known/openid-configuration
    P->>AS: Forward normalized metadata request
    AS-->>P: JSON issuer + public jwks_uri
    P-->>C: JSON metadata
    C->>P: GET /oauth2/jwks
    P->>AS: Forward JWK request
    AS-->>C: JWK Set containing public keys
    C->>C: Select key by kid/alg and verify token
~~~

### 12.1. Never Put Internal URLs or Keys in Metadata

Wrong:

~~~json
{
  "issuer": "https://login.example.com",
  "jwks_uri": "http://auth-service:9000/oauth2/jwks"
}
~~~

Right per the sample public contract:

~~~json
{
  "issuer": "https://login.example.com",
  "jwks_uri": "https://login.example.com/oauth2/jwks"
}
~~~

If a proxy path prefix makes the URL `https://login.example.com/auth/oauth2/jwks`, ensure ingress actually serves that path. Never publish an internal `jwks_uri` and expect clients to "know how to rewrite it."

### 12.2. Public JWK Set Contains No Private Keys

Public JWKS contains only required public key material. For RSA, a JWK may contain `kty`, `n`, `e`, `kid`, `alg`, `use`; **never** private exponent `d` or CRT parameters. For EC, never include the private scalar. Private keys stay inside an appropriate keystore/HSM/KMS or secret store per the signing service design.

### 12.3. Key Rotation in Multi-Issuer Environments

When rotating signing keys:

1. Publish the new public key in the corresponding JWKS before issuing tokens signed with it if needed for caching clients.
2. Begin signing new tokens with the new key and matching `kid`.
3. Retain the old public key until old tokens expire and caching clients can still verify them.
4. Only after that window ends, remove the old key from JWKS—unless a security incident requires emergency revocation.
5. Monitor `unknown kid`, issuer mismatch, algorithm mismatch, and stale-cache errors.

With multiple issuers, track which issuer owns each key. **Never select a key system-wide by `kid` alone while ignoring issuer**; `kid` is not guaranteed to be globally unique across tenants.

### 12.4. Caching and CDNs

Metadata and JWKS are commonly cached. When placing a CDN in front of discovery:

- Cache keys must include hostname, path, and other distinguishing elements so tenants never mix.
- Never cache Acme's metadata response and serve it to Zen.
- Align `Cache-Control` headers, `ETag`, and TTLs with key rotation procedures.
- Cache purging must work per issuer/tenant, not only globally.
- For custom-domain issuers, validate CDN/proxy origin routing, TLS certs, and host-based cache keys.

Never cache token/introspection responses under the same public strategy as metadata/JWKS; credential endpoints demand completely different protection.

## 13. Contract with OAuth2 Clients and Resource Servers

### 13.1. OAuth2 Clients Should Be Configured from a Trusted Issuer

OIDC Clients typically configure `issuer-uri` or a discovery URL to locate authorization/token/JWKS endpoints. Key rules:

1. The client must get its **expected issuer** from trusted configuration, never blindly from arbitrary user input.
2. After discovery, the `issuer` field must match the expected issuer.
3. The client uses endpoint URLs advertised in metadata **only after metadata passes trust-policy validation**.
4. If the client supports both OAuth AS Metadata and OIDC Provider Configuration, pick the right metadata/profile.
5. Never hardcode one tenant's Token Endpoint and mix it with another tenant's ID Tokens or authorizations.

### 13.2. Configuring Issuer on Spring Security Resource Server

Example Resource Server accepting tokens only from Acme:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/tenant/acme
~~~

Spring Security uses the issuer to discover public keys/JWK Set and validate `iss` per configuration, with lookup and well-known route behavior depending on version. Verify that your Resource Server actually supports discovery URLs for path-based issuers along your chosen route.

**Still validate audience.** Configuring `issuer-uri` alone does not ensure a token was issued for your API. For instance, the Orders API should accept only `aud=orders-api`.

### 13.3. Audience Validator

Example audience validator component in Spring Security:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    if (jwt.getAudience().contains("orders-api")) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Invalid audience", null));
};
~~~

This configures a **validator component**, not a complete `JwtDecoder` or `SecurityFilterChain`. Combine it with the default issuer and timestamp validators (never replace all validators with an audience-only validator). Tokens with the wrong issuer must still be rejected even if verified by the same key.

### 13.4. Multiple Issuers on a Resource Server

A Resource Server accepting tokens from both Acme and Zen needs an issuer allowlist and per-issuer validators, e.g., using `JwtIssuerAuthenticationManagerResolver` or an equivalent Spring Security resolver with trusted issuers.

Mental model:

~~~text
Incoming Access Token
  -> Resolve candidate issuer (not yet treated as trusted)
  -> Lookup exact issuer in trusted allowlist
  -> Select JwtDecoder/keys/validators for that issuer
  -> Verify signature, iss, aud, exp, nbf, token type
  -> Tenant/resource authorization
  -> Accept or reject
~~~

**The `iss` claim read prior to verification may only hint which pre-trusted configuration to select**—never use it as a dynamic URL to fetch JWKS over the network. If the issuer is absent from the registry, reject immediately.

## 14. How Can Metadata Be Abused?

### 14.1. Host Header Injection and Issuer Spoofing

An attacker sends `X-Forwarded-Host: evil.invalid`. If ingress passes it through untouched and the app uses it to build the issuer, metadata can advertise an attacker-controlled domain. Mitigate with:

- Public host allowlists on both proxy and application.
- Stripping/overwriting forwarded headers from untrusted sources.
- Fixed issuer for single-issuer setups.
- Exact issuer registry for multi-issuer setups.
- Never reflecting raw headers directly into JWT `iss` claims or metadata URLs.

### 14.2. SSRF via Dynamic Issuer / `jwks_uri`

Clients/Resource Servers must never auto-fetch discovery or JWKS from an unverified `iss`, especially when the URI could point to localhost, a cloud metadata endpoint, or a private network. An approved issuer set should constrain metadata/JWKS destinations, enforce HTTPS/TLS validation, and apply DNS/network egress policies.

### 14.3. Cross-Tenant Metadata Cache Poisoning

If a CDN caches solely by path and ignores `Host`, custom domain A's metadata can be served to B. If a tenant resolver falls back to a default tenant, a mis-prefixed request can fetch another tenant's JWKS. Enforce complete cache keys, exact host/path routing, and negative test cases.

### 14.4. Open Redirect via Authorization Endpoint

Discovery guides clients to the Authorization Endpoint, yet `redirect_uri` must still be validated strictly against `RegisteredClient` and the grant. Never use arbitrary query parameters to determine callbacks. Similarly, `post_logout_redirect_uri` must be validated per OIDC logout profile rules.

### 14.5. Public Discovery Does Not Mean "Everything Public"

Well-known metadata and public JWKS may permit unauthenticated `GET`, but:

- Never leak private keys, client secrets, passwords, or user data.
- Never advertise unauthenticated administrative endpoints.
- Token/Introspection/Revocation endpoints keep independent security rules.
- Configure CORS and CSRF per endpoint type and browser flow—never slap `permitAll()` broadly across the server.
- Never expose private management, actuator, or internal health endpoints in metadata.

## 15. Testing Directly Through the Public Ingress

### 15.1. Checking HTTPS Metadata

~~~bash
curl -i 'https://login.example.com/.well-known/oauth-authorization-server'
~~~

When OIDC is enabled:

~~~bash
curl -i 'https://login.example.com/.well-known/openid-configuration'
~~~

Verify:

- HTTP 200, valid parseable JSON, and right content type.
- `issuer` matches the expected public issuer.
- No `http://auth-service`, `localhost`, Pod IP, or internal ports.
- Token/JWKS/Authorization/Revocation/Introspection URLs use the exact public TLS domain/path.
- `jwks_uri` is reachable and publishes public keys only.

Never use `curl -k` to skip TLS verification in acceptance tests: doing so hides certificate and custom-domain errors.

### 15.2. Using `jq` to Inspect Core Fields

~~~bash
curl --silent --show-error \
  'https://login.example.com/.well-known/oauth-authorization-server' |
  jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri, revocation_endpoint}'
~~~

This shell snippet requires `jq`. It reads metadata only and sends no credentials. In CI, assert **exact values** rather than merely printing JSON for manual inspection.

### 15.3. Testing a Custom Domain Before Official DNS Cutover

Suppose the test ingress IP is known and the organization controls the domain. Use `curl --resolve` to force connecting to that IP while keeping the hostname/SNI:

~~~bash
curl --resolve 'login.customer.example:443:203.0.113.25' \
  'https://login.customer.example/.well-known/openid-configuration'
~~~

IP `203.0.113.25` is an **example address**, not a real production address. This verifies public TLS certificates, host routing, and domain-scoped metadata prior to DNS rollout. Never use `--insecure` to mask certificate issues.

### 15.4. Testing Path-Based Issuers per Spec

Example issuer `https://auth.example.com/tenant/acme`:

~~~bash
curl -i \
  'https://auth.example.com/.well-known/oauth-authorization-server/tenant/acme'

curl -i \
  'https://auth.example.com/tenant/acme/.well-known/openid-configuration'
~~~

If the app does not serve one of these routes, determine whether your library/version or reverse proxy provides a different profile-specific well-known URL variant. **Never change the expected issuer to match a URL that happens to return HTTP 200**; resolve the standard contract, client compatibility, and routing intentionally.

### 15.5. Testing Untrusted `Host` / `X-Forwarded-Host`

Against the test ingress, send a request with spoofed headers:

~~~bash
curl -i \
  -H 'X-Forwarded-Host: attacker.invalid' \
  -H 'X-Forwarded-Proto: http' \
  'https://login.example.com/.well-known/oauth-authorization-server'
~~~

Expected: metadata still returns `https://login.example.com` or the request is blocked by policy; **never** emit `issuer=https://attacker.invalid` or endpoints using the attacker's `http` scheme. Also test a `Host` header completely outside the allowlist.

## 16. Integration Testing with Spring Security and MockMvc

`MockMvc` is valuable for checking the contract at the application layer, yet **cannot replace end-to-end tests through ingress**. Proxy header stripping/injection and TLS/SNI must be tested in a production-like environment.

### 16.1. Fixed Issuer Test

JUnit 5 / Spring Boot test example with a configured Authorization Server:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationMetadataIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void metadataUsesPublicIssuerRatherThanInternalHost() throws Exception {
        mvc.perform(get("/.well-known/oauth-authorization-server")
                    .header("Host", "auth-service:9000"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.issuer")
                    .value("https://login.example.com"))
            .andExpect(jsonPath("$.token_endpoint")
                    .value("https://login.example.com/oauth2/token"))
            .andExpect(jsonPath("$.jwks_uri")
                    .value("https://login.example.com/oauth2/jwks"));
    }
}
~~~

**Fixture preconditions:** the `AuthorizationServerSettings` bean uses the public issuer, security filter chains enable the metadata endpoint, and `JWKSource` is registered. This test proves the in-JVM response matches config; it does not prove ingress TLS/Host filtering is right.

### 16.2. Test OIDC Only When OIDC Is Enabled

If the application enables `oidc(Customizer.withDefaults())`, add:

~~~java
@Test
void oidcConfigurationKeepsIssuerConsistent() throws Exception {
    mvc.perform(get("/.well-known/openid-configuration"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.issuer")
                .value("https://login.example.com"))
        .andExpect(jsonPath("$.jwks_uri")
                .value("https://login.example.com/oauth2/jwks"));
}
~~~

This is an illustrative method for the corresponding test class; `MockMvc` and static imports match the previous example. Do not copy it into a project without OIDC enabled and mistake HTTP 404 for an OAuth 2.0 metadata bug.

### 16.3. Multi-Issuer Tests Must Verify Data Isolation

Do not just assert that `issuer` values differ. Also test:

1. Acme clients exist only in Acme's repository.
2. Acme's Authorization Codes/Refresh Tokens cannot be redeemed at Zen.
3. Acme and Zen `JWKS` return the right public keys per key-separation policy.
4. Zen's Resource Server rejects Acme's JWTs, even with matching `aud` or `sub`.
5. Revocation/Introspection never look up or mutate tokens across tenants.
6. Wrong issuer paths never fall back to a default tenant.
7. Unapproved custom domains are blocked before metadata generation.

## 17. Production Discovery Test Matrix

| # | Scenario | Expected |
| --- | --- | --- |
| 1 | Single issuer behind HTTPS proxy | Metadata contains public HTTPS issuer and endpoints |
| 2 | Internal backend uses HTTP | No internal scheme/host/port exposed in metadata |
| 3 | RFC 8414 OAuth well-known | Returns JSON with right issuer, endpoints, and metadata schema |
| 4 | OIDC enabled | OIDC well-known returns valid JSON with matching issuer |
| 5 | OIDC disabled | Does not advertise fake OIDC capabilities |
| 6 | Proxy overwrites `Forwarded` headers | Host/scheme accurately match public request |
| 7 | Client sends spoofed `X-Forwarded-Host` | Does not reflect attacker domain |
| 8 | Unknown Host/SNI | Blocked or safely routed; never generates issuer |
| 9 | External path prefix `/auth` | Published endpoint URLs carry prefix matching real routes |
| 10 | Proxy strips prefix | Clients still call Token Endpoint and JWKS successfully |
| 11 | Path-based issuer per RFC 8414 | Well-known URL and `issuer` field follow spec |
| 12 | Path-based issuer per OIDC Discovery | OIDC well-known URL and `issuer` field match |
| 13 | Approved custom domain | TLS cert/SNI, issuer, and endpoint URLs consistent |
| 14 | Unverified custom domain | Never used as an issuer |
| 15 | Acme metadata request | Never receives Zen's issuer/keys/endpoints |
| 16 | Unknown issuer path | Rejected; no fallback |
| 17 | Key rotation | `jwks_uri` serves both new and old keys as planned |
| 18 | JWKS behind CDN | Cache isolates issuer/host; never returns wrong tenant's keys |
| 19 | Resource Server trusts only Acme | Rejects Zen tokens |
| 20 | Valid signature, wrong `aud` | Resource Server rejects |
| 21 | Redirect URI differs from `RegisteredClient` | Authorization request rejected |
| 22 | Cross-tenant Introspection/Revocation | Never reveals or affects another tenant's token |
| 23 | Issuer domain migration | Clients/Resource Servers do not accidentally treat both as one |
| 24 | Direct backend call bypassing ingress | Blocked by network policy or app routing |
| 25 | Multi-node proxy/cache | Consistent metadata, routing, and key policy |

**PASS criterion:** tests must verify the JSON response, live endpoint calls, and signature/issuer/audience checks on issued tokens. Seeing HTTP 200 at the well-known endpoint alone is never enough.

## 18. Diagnosing Common Errors

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Metadata issuer is `http://localhost:9000` | Public issuer not set or wrong proxy headers | Set `AuthorizationServerSettings.issuer` and check forwarded policy |
| Endpoint URL contains internal port | App unaware of external origin | Inspect ingress/`Forwarded` headers and metadata |
| OIDC discovery 404 | OIDC not enabled or wrong route | Check `oidc(...)` and security matcher |
| OAuth metadata 404 while OIDC works | Well-known path/router mapping mismatch | Check RFC 8414 path and proxy routing |
| OAuth Client reports issuer mismatch | `issuer` field differs from expected issuer | Fix issuer contract; never disable issuer validation |
| Authorization Code exchange returns 404 | Token Endpoint advertises wrong public prefix | Check rewrite rules and metadata |
| Redirect to `http` after login | Wrong proxy header/scheme | Check trusted proto, app redirects, and HSTS/TLS |
| JWT `kid` absent from JWKS | Wrong tenant JWKS or stale rotation/cache | Check `jwks_uri` and key publishing |
| Validly signed token gets API 401 | Wrong `iss`/`aud` or clock skew | Verify trusted issuer and audience |
| Custom domain fails only on some clients | DNS/SNI/TLS cert or discovery URI profile | Check certificate, domain verification, and client SDK |
| Acme metadata mixes with Zen | Tenant routing fallback, shared cache, or broken registry | Disable fallback, fix cache key, test isolation |
| Same issuer alternates between http and https | Inconsistent header trust/overwriting | Standardize proxy headers, static issuer, or exact allowlist |
| One node returns different metadata from another | Out-of-sync config/keys/registry | Check rollout, registry version, and caches |

### 18.1. Ordered Investigation Steps

1. Record the expected issuer from trusted client configuration.
2. From **outside ingress**, call the standard-compliant well-known URL.
3. Compare `issuer` strictly—never by approximate hostname similarity.
4. Confirm all endpoint URLs and `jwks_uri` are reachable over HTTPS.
5. If the issuer has a path, verify which discovery standard the client uses.
6. Inspect host/forwarded-header handling and proxy rewrites.
7. Verify JWT `iss`, `aud`, `kid`, `exp` on a non-production test token.
8. Verify Resource Servers have matching trusted issuers and keys.
9. In multi-issuer setups, inspect tenant registry, data/keys, caches, and routing.
10. Fix configuration and re-run both integration tests and E2E tests through the proxy.

Never resolve an issuer mismatch by disabling the `iss` validator or accepting wildcard hosts: that breaks the OAuth/OIDC trust boundary.

## 19. Changing Custom Domains or Issuers Safely

### 19.1. Changing a Domain Is Not Just Changing DNS

If the old issuer is `https://login.old.example` and the new issuer is `https://login.new.example`, an old Access Token with `iss=https://login.old.example` does not automatically belong to the new issuer. Clients/Resource Servers may need to trust both issuers during a transition period, under an **explicit policy and deadline**—never indefinitely.

### 19.2. Migration Plan

1. **Inventory:** list clients, Resource Servers, redirect URIs, logout URIs, JWKS consumers, and token lifetimes.
2. **Verify domain:** validate ownership, DNS, TLS certificate, SNI, and routing.
3. **Publish metadata:** new issuer exposes valid discovery/endpoint URLs and JWK Set.
4. **Create tenant/issuer registry entry:** tenant data, signing keys, `RegisteredClient`s, and consent mappings per policy.
5. **Test before rollout:** run the full suite including code flow, refresh, introspection, revocation, OIDC UserInfo, and logout if used.
6. **Update clients/Resource Servers:** add the new issuer in a controlled rollout without disabling issuer validation.
7. **Cutover:** shift traffic/registrations to the new issuer; newly issued tokens must carry the new `iss`.
8. **Drain old issuer:** let old tokens expire or revoke per policy; manage refresh and session migration.
9. **Remove old trust:** retire old endpoints/keys/issuer after transition completes, with clear notice.
10. **Audit/rollback:** retain change records, monitor issuer mismatches, and keep a rollback path that never accepts tokens from the wrong trust domain.

### 19.3. Rollback May Still Need to Serve the New Issuer

Once tokens have been issued under the new issuer, rolling traffic back to the old issuer does not make new tokens accepted by every API. You may need to keep serving the new issuer temporarily until users re-authenticate or tokens expire. Never flip the `issuer` field in metadata back and forth between two domains.

### 19.4. Multi-Issuer Key Compromise Considerations

If one tenant's signing key is compromised, key separation limits the blast radius. If multiple issuers shared a key, an incident may force trust rotation across multiple tenants. Your runbook must map issuer → keys → active tokens → affected Resource Servers, plus JWKS update and revocation plans.

## 20. Design and Operations Checklist

1. **Issuer is a contract:** choose a stable canonical issuer, exact string; never infer from raw `Host`.
2. **Well-known URLs:** verify RFC 8414/OIDC Discovery especially when the issuer has a path.
3. **Metadata fields:** `issuer`, endpoints, `jwks_uri`, and capabilities reflect real config.
4. **Public URLs:** never publish localhost, internal service DNS, pod IPs, or internal ports.
5. **Reverse proxy:** trust forwarded headers only from trusted ingress and strip external client headers.
6. **Prefix/rewrite:** test public routes across login, code exchange, JWKS, introspection, and revocation.
7. **OIDC:** advertise Provider Configuration only when OIDC is genuinely enabled.
8. **Custom domains:** verify ownership, DNS/TLS/SNI, issuer mapping, and domain lifecycle.
9. **Multiple issuers:** enforce an exact allowlist; never accept-all dynamically or fall back.
10. **Tenant isolation:** repositories, authorizations, consents, client registries, and keys respect trust boundaries.
11. **Resource Server:** validate JWT signature, issuer, audience, timestamps, and tenant policy.
12. **JWKS:** public keys only, per-issuer key rotation/caching; never use another tenant's key.
13. **Cache:** metadata/JWKS never mix hosts or tenants; cache purging has a defined workflow.
14. **SSRF/Host injection:** never fetch JWKS from unapproved issuers or reflect spoofed hosts.
15. **Testing:** cover `MockMvc`, HTTP via ingress, custom domains, and multi-issuer negative cases.
16. **Migration:** maintain plans for domain/issuer transitions, key rollovers, and unexpired tokens.
17. **Observability:** track metadata errors, issuer mismatches, unknown `kid`s, and endpoint URL mismatches.
18. **Privacy:** never log authorization codes, Access Tokens, client secrets, or raw token responses.

## 21. Practice Exercises and Review Questions

**Exercise A — Proxy mismatch.** Backend runs at `http://auth-service:9000`; public URL is `https://login.example.com`. Metadata returns the internal issuer. Write the `AuthorizationServerSettings` config and describe a test proving JWT `iss` and metadata match.

**Exercise B — Discovery paths.** Issuer is `https://auth.example.com/tenant/acme`. Compute the RFC 8414 and OIDC Provider Configuration URLs, and explain why the two specs place paths differently.

**Exercise C — Host injection.** The proxy forwards client `X-Forwarded-Host` untouched. An attacker sends `attacker.invalid`. Explain the exploit and list four infrastructure/application controls to prevent issuer reflection.

**Exercise D — External prefix.** Public Token Endpoint is `https://id.example.com/auth/oauth2/token`; the backend only listens on `/oauth2/token`. Design the ingress rewrite, forwarded prefix, and assertions needed in metadata tests.

**Exercise E — Custom domain.** Tenant Acme wants `https://login.acme.example` as its official issuer. List every component that must change: domain ownership, TLS, metadata, JWT issuer, JWKS, clients, Resource Servers, and rollback.

**Exercise F — Multi-issuer.** Acme and Zen share a host with different issuer paths. Implement an exact-match issuer registry and write a test proving an Acme authorization code cannot be redeemed at Zen's Token Endpoint.

**Exercise G — Keys.** A Resource Server trusts only issuer Acme yet receives a Zen JWT sharing the same `kid` and public key. Explain why it must still be rejected.

**Exercise H — CDN.** Two custom domains share the path `/.well-known/openid-configuration`. Design the cache key and tests preventing cross-tenant metadata contamination.

**Self-assessment questions:**

1. How does `issuer` differ from the metadata URL?
2. Do OAuth 2.0 Authorization Server Metadata and OIDC Discovery share the same URL rule when the issuer has a path?
3. Why must `issuer` match exactly between metadata and token `iss`?
4. Can `jwks_uri` point to a Pod IP or internal service DNS?
5. Does `server.forward-headers-strategy=framework` protect against Host header injection on its own?
6. Why must the proxy strip and overwrite `X-Forwarded-*` from external requests?
7. When is a custom domain merely an alias versus a new issuer?
8. Why is enabling `multipleIssuersAllowed(true)` insufficient by itself for multi-tenant isolation?
9. Which repositories need to be tenant-aware?
10. How should a Resource Server select keys by issuer and `kid`?
11. Why should a Resource Server never fetch JWKS directly from an untrusted `iss`?
12. If old JWTs are still valid when changing issuers, how should migration be handled?
13. Why is HTTP 200 on metadata discovery insufficient to prove Authorization Code Flow works?
14. What errors can prefix rewrites or CDN caches cause?

## 22. References

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8414, Section 3 — Obtaining Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414#section-3)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Multitenancy](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-multitenancy.html)
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/reference/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Multitenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)

**Remember:** Discovery is an **identity and routing contract used to establish trust**, not decorative JSON. Behind a reverse proxy, `issuer` and every endpoint must use the exact public HTTPS domain/path, and forwarded headers must only be trusted through a controlled proxy. A custom domain becomes a real issuer only when metadata, tokens, keys, and clients/Resource Servers all adhere to the new identity. In multi-issuer environments, always enforce an exact issuer allowlist, tenant-aware storage/keys/policies, and isolation tests—never accept dynamic issuers from `Host`/headers and never disable `iss` checks to mask misconfiguration.
