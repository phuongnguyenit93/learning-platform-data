# Obtaining identity and authorities from a gateway, container, or centralized access system

In many enterprise systems, **Spring Security is not the component directly verifying users' passwords, security keys, or SSO sessions**. An **API gateway**, **authenticating reverse proxy**, **Java Servlet container**, or **centralized access system** (access manager) has already authenticated the user upstream. The Java application receives a **pre-authenticated identity** and translates it into `Authentication`, `UserDetails`, and `GrantedAuthority` to enforce access control.

The hardest part **is not how to read an HTTP header**, but proving **who injected the header/principal into the request, whether they actually authenticated the user, and whether that information could be forged or altered by a client at any hop**. If the backend trusts `X-User: admin` solely because the header exists, any direct caller or misconfigured gateway can impersonate an admin.

**Principle:** verify the **trusted source/evidence** first, establish the **stable identity and issuer scope** second, load the **account/authorities under server policy** third, and then **enforce tenant, action, and resource checks** in the application. Headers injected by a gateway **are not cryptographic proof on their own**; HTTP container principals are trustworthy only when the container has genuinely enabled authentication; groups from a centralized system are policy inputs, not unconditional admin permits.

This article belongs to **Spring Security – federation → Proxy Authentication**, focusing on three identity sources: **gateway/reverse proxy**, **Servlet container**, and **centralized access manager**; how to protect trust boundaries, Spring Security pre-authentication classes, authority mapping, Spring configuration code, a runnable Java 17 example, plus testing and operational checklists.

## 1. Distinguishing authentication, pre-authentication, and authorization

**Authentication** answers: "Who is sending this request, and what evidence proves that identity?". **Pre-authentication** is the situation where another system performed verification and Spring receives the result across a trusted integration protocol/layer. **Authorization** answers: "What is that identity allowed to do on a specific resource, in which tenant?".

Illustrative example:

~~~text
Browser
  |
  | OIDC / SAML / Kerberos / session cookie with SSO system
  v
Access Gateway
  | 1. Verify token or session
  | 2. Determine issuer + subject + assurance
  | 3. Strip client-supplied identity headers
  | 4. Attach trusted identity context
  | 5. Connect to backend over authenticated channel
  v
Spring Boot Backend
  | 6. Accept requests only from authenticated gateway
  | 7. Read pre-authenticated principal
  | 8. Link external identity -> local account
  | 9. Load roles/tenant membership via allowlist
  | 10. Check action and permissions per object
  v
Business response
~~~

**Note:** In Spring Security, `PreAuthenticatedAuthenticationProvider` **does not verify passwords, JWT signatures, or SAML assertions itself**. It assumes external authentication has already occurred safely and primarily loads user/authority information. The boundary at step 6 must be engineered separately.

## 2. The three identity sources covered in this topic

| Source | Where can Spring read it? | Who actually authenticates? | Prominent risk |
| --- | --- | --- | --- |
| **Gateway/reverse proxy** | Headers injected by gateway; sometimes JWT/verified request attributes | Gateway/IdP or service mesh | Header spoofing; backend reached via bypass |
| **Servlet/Jakarta EE container** | `HttpServletRequest.getUserPrincipal()`, `getRemoteUser()`, `isUserInRole()` | Container authentication realm, possibly using BASIC/FORM/CLIENT-CERT/SPNEGO/JASPIC per config | Assuming container principal exists even when container security is off |
| **Centralized access manager** | Headers like `SM_USER`, trusted application context, validated signed assertion/JWT | SiteMinder or governed IAM product/rules | Trust namespace shift, role collision, expired session/changed permissions |
| **Spring OAuth2 Resource Server** | `Authorization: Bearer` JWT/opaque token | Spring verifies the token itself against issuer/JWK or introspection | Audience/token type mismatch, issuer spoofing |
| **Spring session** | `SecurityContext` stored per session strategy | Spring authenticated on a prior request | Stale session, disabled account with unrefreshed permissions |

**Distinguishing the two approaches:** if Spring **verifies the JWT access token itself**, that is OAuth2 Resource Server authentication, **not necessarily header-based pre-authentication**. If the gateway verified the token and the backend receives only identity headers, the backend relies on a **pre-auth trust contract** with the gateway and must enforce matching protections.

## 3. The trust boundary is the most critical piece

A secure infrastructure diagram must show which paths are **allowed** and which paths are **blocked**:

~~~text
Internet
  |
  +----> Public Gateway / Access Proxy
  |            |
  |            | HTTPS/mTLS, authenticated gateway identity
  |            | overwrite trusted identity headers
  |            v
  |       Private Backend
  |       no public ingress
  |
  +--X--> Direct backend pod/VM
  |
  +--X--> Bypass via alternate hostname/port/health endpoint
~~~

**Four layers that must be evaluated together:**

1. **Network reachability:** the backend has no public ingress/port/alternate route bypassing the gateway; Kubernetes NetworkPolicy, firewalls, security groups, or service mesh authorization genuinely block direct access.
2. **Hop authentication:** the backend confirms requests come from an authorized gateway/service mesh via **mTLS identity** or an equivalent trusted authentication mechanism; **never rely solely on IP or `X-Forwarded-For`**.
3. **Header integrity:** the gateway strips all client-supplied identity headers and sets a **controlled header set emitted by the gateway itself** after successful authentication.
4. **Application identity mapping:** the backend uses only subject/issuer/tenant from the trusted context, never auto-merging by email or converting raw upstream roles into admin.

**"Internal network" is not proof that the caller is the gateway.** Other pods, developer VPNs, SSRF, misconfigured ingress, or sidecars can open bypass paths. One overlooked hop invalidates the entire pre-auth contract.

## 4. Identity header values are mere data without a trusted source

Common illustrative headers, **not a universal standard**:

~~~http
GET /app/invoices/42 HTTP/1.1
Host: service.internal.example.test
X-Verified-Subject: usr-8fa1
X-Verified-Issuer: https://sso.example.test
X-Verified-Auth-Method: mfa
X-Verified-Groups: finance-readers,finance-approvers
~~~

This is illustrative data only. An attacker can send the exact same text with `curl` if the backend accepts direct requests.

**Safer approach:** the gateway verifies the user's session, **strips first** any browser/client-supplied `X-Verified-*` headers, and then writes contract-defined headers, signing them or protecting the transport and authenticating the gateway. The backend must reject any request not arriving from the authenticated hop.

**Unacceptable:** 

- Only checking `request.getHeader("X-Verified-Subject") != null`.
- Treating `X-Forwarded-For` or `X-Real-IP` as proof the user is authenticated.
- Trusting any request carrying `X-Groups: admins`.
- Accepting headers from one ingress without locking down the backend's original port.
- Using the gateway's browser cookie as a Spring identity when the backend cannot validate that cookie.

Header names like `SM_USER` or `X-Authenticated-User` carry no intrinsic security. **Assurance belongs to the system setting the header and the transport**, not the name.

## 5. Responsibilities of the gateway/access proxy

The gateway may validate **OIDC authorization flows, OAuth bearer tokens, SAML sessions, Kerberos, client certificates**, or cookies issued by an access manager. After verification, it must transform the result into an **identity contract** suitable for the backend.

A contract should define at least:

| Field | Example | Rule |
| --- | --- | --- |
| `auth_source` | `corp-gateway-v1` | Source identity configured/trusted by backend |
| `issuer` | `https://id.example.test/realm/corp` | Identity origin, never arbitrarily chosen from request |
| `subject` | `user-1044` | Opaque, preserved as exact string, never defaulted to email |
| `client/actor` | `portal-web` | Application actually making the request, when needed for audit |
| `auth_time` | Authentication timestamp | Used for freshness policy, per contract semantics |
| `assurance` | `mfa` or trust level | Trusted only if gateway/IdP enforces matching semantics |
| `tenant_context` | `north` | Hint or verified context, **never auto-grants membership** |
| `groups` | `billing-readers` | Input signal for SP mapping through an allowlist policy |
| `correlation_id` | Non-secret trace ID | Never used as an authentication credential |
| `session_id` | Controlled session identifier | Watch PII/session hijack risk; omit if unused |

Ideally define the **contract version**, schema, encoding, string format, multiplicity, max lengths, expiration, and missing-field handling. When multiple gateways send traffic to one backend, define explicit **namespaces/issuers/trust contexts** per source.

**Never accept `X-User` from the client and infer `issuer` from email.** Issuer and identity namespace are part of trust policy, not merely profile data.

## 6. What does RequestHeaderAuthenticationFilter actually do?

In Spring Security Servlet, `org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter`:

1. Reads the **principal** from a request header, defaulting to `SM_USER` (SiteMinder model compatibility).
2. Can be configured with `setPrincipalRequestHeader("X-Verified-Subject")`.
3. By default throws `PreAuthenticatedCredentialsNotFoundException` when the header is missing; behavior is configurable via `setExceptionIfHeaderMissing(...)`.
4. Constructs a `PreAuthenticatedAuthenticationToken` holding the principal and dummy/configured credentials, and passes it to `AuthenticationManager`.
5. **Does not verify signatures, passwords, client certificates, or identity proofs** just because the header is present.

Spring Security's own Javadoc warns: if you use this filter when an external authentication system does not protect every access path to the backend, an attacker can **choose any username** simply by setting the header.

### What is NOT inside the filter?

- Does not verify OAuth JWT issuer/audience.
- Does not verify CAS Service Tickets.
- Does not verify SAML assertion signatures.
- Does not guarantee mTLS gateway identity.
- Does not enforce domain/tenant authorization.
- Does not check who set the groups header.
- Does not block direct routes into the backend.
- Does not verify container authentication realms.

Those guarantees require **infrastructure, protocol-specific validators, and application policy**.

## 7. AbstractPreAuthenticatedProcessingFilter and AuthenticationManager

Both `RequestHeaderAuthenticationFilter` and `J2eePreAuthenticatedProcessingFilter` build on the `AbstractPreAuthenticatedProcessingFilter` framework.

Flow:

~~~text
HTTP request having passed trusted external authentication
             |
             v
AbstractPreAuthenticatedProcessingFilter
  getPreAuthenticatedPrincipal(request)
  getPreAuthenticatedCredentials(request)
             |
             v
PreAuthenticatedAuthenticationToken (not yet fully authenticated)
             |
             v
AuthenticationManager / ProviderManager
             |
             v
PreAuthenticatedAuthenticationProvider
             |
             v
AuthenticationUserDetailsService
  local account lookup, account status, authorities
             |
             v
PreAuthenticatedAuthenticationToken (authenticated)
             |
             v
SecurityContext -> AuthorizationFilter / @PreAuthorize
~~~

**Misleading name:** `PreAuthenticatedAuthenticationProvider` essentially **accepts that an external party already authenticated**, then loads `UserDetails` and checks account status. Never describe it as a validator of HTTP identity headers.

The provider normally requires non-null `principal` and `credentials`; `RequestHeaderAuthenticationFilter` uses a dummy credential when `credentialsRequestHeader` is not set. This dummy **is not the user's password** and carries no identity-proofing value.

If the external system supplies no principal or supplies an invalid one, you must **fail closed** instead of falling back to guest/admin.

## 8. PreAuthenticatedAuthenticationProvider: accounts and authorities

The provider uses `setPreAuthenticatedUserDetailsService(...)` to accept an `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>`. The loader can:

- Map verified external subject → local account ID.
- Check that the account is still enabled and not locked/suspended.
- Load the local account's roles from the database/authorization service.
- Enforce tenant/scope/caller restrictions.
- Retain only `GrantedAuthority` values on an approved allowlist.
- Prevent an identity pair belonging to another local account from being reassigned.
- Reject unlinked accounts when JIT provisioning is disallowed.

The provider's Javadoc explicitly states it **performs no authentication check on the request**, because upstream already did. It may throw `UsernameNotFoundException` or another exception when the local account cannot be found or accepted.

**Do not confuse "received a header" with "found an active local account".** Even when the gateway successfully authenticates a user, the backend may still have to deny access because the account is disabled, not in the tenant, or lacks permissions.

## 9. UserDetailsService and AuthenticationUserDetailsService

`UserDetailsService` takes a `String username` and typically queries a database. `AuthenticationUserDetailsService<T extends Authentication>` receives the full authentication token, making it suitable when context or external authorities are needed.

| Need | Choice |
| --- | --- |
| Single trusted issuer, unique subject, and all roles in local DB | `UserDetailsService` + `UserDetailsByNameServiceWrapper` |
| Need source/trust context, tenant, actor, or verified extra claims | Custom `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` or custom AuthenticationProvider |
| Container provides verified role names | `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` + mapping/authorization |
| Receiving trusted `GrantedAuthoritiesContainer` from details | `PreAuthenticatedGrantedAuthoritiesUserDetailsService` may fit |
| Raw gateway header contains group names | **Do not promote directly** to roles; parse + allowlist + tenant checks |
| Signed JWT access token issued by IdP/AS | Consider `oauth2ResourceServer().jwt()`, rather than manual header parsing |

**PreAuthenticatedGrantedAuthoritiesUserDetailsService** simply pulls authorities from `token.getDetails()` when details implements `GrantedAuthoritiesContainer`. It **does not inspect all request headers or verify that the role list is trustworthy**. If details can be influenced by browser-controlled input, copying it straight into UserDetails creates a privilege escalation vulnerability.

## 10. Java EE/Jakarta Servlet container: getUserPrincipal and isUserInRole

In a container-authenticated request:

~~~java
// Code snippet in a container-protected Servlet/Controller:
java.security.Principal principal = request.getUserPrincipal();
String userName = principal == null ? null : principal.getName();

boolean isAuditor = request.isUserInRole("auditor");
~~~

Servlet APIs expose **container-managed identity/roles**. If the container has no real security constraint/realm/authentication mechanism configured, `getUserPrincipal()` can be `null`, and role methods do not prove the user logged in.

Spring provides `org.springframework.security.web.authentication.preauth.j2ee.J2eePreAuthenticatedProcessingFilter` to read the username from `getUserPrincipal()`, rather than trusting client-sent HTTP identity headers.

### Roles from the container

`J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` checks a **predefined list of mappable roles** via `request.isUserInRole(role)`. Then `Attributes2GrantedAuthoritiesMapper` converts them into authorities (typically adding `ROLE_`). The role list must be governed and **bounded**; containers provide no standard API to enumerate unbounded roles.

**Do not assume every role in every container deployment equals an application business role.** `isUserInRole("admin")` only proves the container mapped a role of that name under container security config; the application still needs entitlement/tenant/object checks.

## 11. Container-authenticated flow example

An application server/WAS/WildFly/Tomcat-with-realm can authenticate users via container policy and expose `Principal` on the ServletRequest.

~~~text
Browser
   |
   | HTTPS, container-managed auth mechanism
   v
Servlet Container
   | authenticate client
   | set HttpServletRequest userPrincipal + roles
   v
J2eePreAuthenticatedProcessingFilter
   | read container principal
   v
PreAuthenticatedAuthenticationProvider
   | load local account / authorities
   v
Spring SecurityContext
   |
   v
Tenant + resource authorization
~~~

**Prerequisite:** the container must genuinely configure authentication and enforce access before the Servlet filter. A plain Tomcat with `/app/**` unprotected does not magically provide pre-authentication just because Java code has `getUserPrincipal()`.

### Can container and gateway be combined?

Yes, provided you decide who is the **source of truth**: does the gateway validate JWTs and the container set the principal, or does the container have its own realm? If the container populates the principal from a reverse proxy header, the trust boundary remains the gateway; `getUserPrincipal()` does not miraculously turn forged headers into security. Never enable two providers with unconditional fallback logic that lets a weaker source override a stronger one.

## 12. Centralized access manager: SiteMinder, SSO proxy, access broker

Systems like SiteMinder or enterprise access proxies can:

1. Redirect to a centralized login.
2. Validate session cookies/tokens at the proxy/policy server.
3. Enforce URL access policies at the gateway.
4. Pass the principal in `SM_USER` or a protected identity context.
5. Let the backend map to local accounts and permissions.

**The SiteMinder model** is a well-known example in Spring Security: `RequestHeaderAuthenticationFilter` defaults to `SM_USER`. This is **not a security interoperability standard**: each vendor differs in attribute propagation, signing, proxy chaining, and session lifecycles.

**An access manager may decide URL-level access**, yet that **does not replace business-object authorization** inside the application. Knowing the gateway allowed a user onto `/app/invoices` does not mean they may read **every tenant's invoices**. Backend authorization is required.

If the access manager issues a signed token to the backend rather than a bare header, consider **verifying the token at the backend** for cryptographic issuer/audience/expiry guarantees. Never extract a username from a Base64-decoded token payload and pretend it is authenticated.

## 13. Header spoofing: what does a malicious request look like?

~~~http
GET /app/admin/users HTTP/1.1
Host: service.internal.example.test
X-Verified-Subject: administrator
X-Verified-Groups: admin,superuser
~~~

A client can craft this request directly. If the backend is reachable directly and only checks headers, an attacker can **impersonate administrator**.

### Configuration must defend in multiple layers

- **Strip:** at the public edge, strip all inbound identity headers, including aliases/case variants that runtimes normalize.
- **Rewrite:** set identity headers **only after successful authentication**, preserving zero client-supplied values.
- **Authenticate hop:** the backend trusts only a gateway authenticated via mTLS/service identity or an equivalent mechanism.
- **Network deny:** no direct path to the pod/backend port exists.
- **Header contract:** reject duplicate/conflicting headers or headers with newlines/control chars/oversized values.
- **Scope:** which source do issuer/subject/tenant belong to, and are they authorized for this service?
- **Authorization:** even a valid identity never receives privileges beyond policy.

**Do not rely solely on a reverse proxy hostname in `X-Forwarded-Host` or IP in `X-Forwarded-For`**, because those fields are trustworthy only when a trusted proxy sanitized them.

## 14. Gateway–backend connection via mTLS

**Mutual TLS (mTLS)** lets the backend verify the gateway/service-mesh peer's identity, while the gateway verifies the backend's server certificate. When using mTLS as gateway proof:

1. Certificate issuance is governed by a controlled PKI/trust domain.
2. The backend checks the certificate chain, SAN/service identity, and peer trust policy.
3. Only authorized gateway identities may connect to protected backend routes.
4. If TLS terminates at an ingress/sidecar, ensure the subsequent hop is properly protected and the sidecar cannot be bypassed.
5. Certificate rotation/revocation must work reliably.
6. Avoid accepting any certificate signed by a broad CA when only one gateway is authorized.

**mTLS authenticates only the gateway/hop**, **not the end user**. The gateway must still prove it validated the session/JWT/OIDC/SAML properly and emitted identity headers from that result.

**Complete chain:** "gateway authenticated the user" **AND** "backend authenticated that this really is the gateway" **AND** "backend constrained user permissions".

## 15. Signed assertion/JWT: a better alternative to bare headers in many architectures

A gateway may forward a **signed identity assertion** or a JWT access token issued for the backend. The backend uses a validator to check:

- Signature against trust anchor/JWKS/allowed algorithms for the right issuer.
- `iss` is an approved issuer.
- `aud` includes the current backend/API.
- `exp`, `nbf`, token lifetime, and bounded clock skew.
- Appropriate token type/purpose, preventing an ID Token from being used as an API Access Token.
- `sub` is a stable subject scoped to the issuer.
- `scope` or claims defined per contract, with no auto-admin.
- Actor/client, `azp`, or delegation context when required by policy.
- Replay/freshness/revocation matched to risk level.

If the application verifies JWT access tokens from `Authorization: Bearer` itself, Spring should typically use **`oauth2ResourceServer().jwt()`**. If handling standalone JWT assertions from a gateway, use a clear trust policy/validator; **never Base64-decode payloads yourself and treat them as valid signatures**.

**An OIDC ID Token** is issued for an OIDC client, not as a default API access token. Even a valid signature can be misused across audiences if the application fails to verify properly.

## 16. Designing identity keys: username is insufficient in multi-provider setups

Case with multiple gateways/tenants/identity providers:

~~~text
Gateway Corp emits subject "123" for person A.
Gateway Partner emits subject "123" for person B.

If backend looks up solely by subject = "123":
  Risk of mistakenly merging A and B.

Correct key:
  (trusted-source/issuer, subject)
    -> local_account_id
~~~

If upstream uses OIDC, the standard stable key is **`(iss,sub)` of the OP-verified ID Token**. When a gateway forwards identity, the backend needs a **verified issuer context** from configuration/contract or signed claims, never using email as the key.

If container authentication supplies `getUserPrincipal().getName()`, the application must know the **container realm/trust namespace**. Username `alice` from container A and from container B are not automatically the same account.

Example DB schema:

~~~sql
CREATE TABLE federated_identity (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  local_account_id BIGINT NOT NULL REFERENCES local_account(id),
  trusted_source VARCHAR(128) NOT NULL,
  issuer VARCHAR(512) NOT NULL,
  subject VARCHAR(255) NOT NULL,
  linked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (trusted_source, issuer, subject)
);
~~~

This is a PostgreSQL example assuming `local_account` already exists. For identity strings, use **case-sensitive exact matching** per the issuer/provider contract and proper DB collation; never lower-case subjects or strip issuer paths automatically.

**Email, display name, preferred_username, and phone number are not immutable identifiers across all providers.** Linking two identities to the same account requires verified evidence and an approved linking workflow.

## 17. Receiving authorities from a gateway: when is direct mapping dangerous?

Suppose the gateway sends:

~~~text
X-Verified-Groups: finance,operations,ROLE_ADMIN
~~~

An unsafe implementation:

~~~java
// DO NOT apply to an untrusted or unrestricted group header.
for (String group : rawGroups) {
    authorities.add(new SimpleGrantedAuthority(group));
}
~~~

If upstream groups can be user-chosen or the gateway simply forwards raw unvetted IdP claims, a user could become `ROLE_ADMIN` in the application.

**Role mapping principles:**

1. **Allowlist per issuer/trusted_source and application**.
2. Map only group IDs approved by the app owner.
3. Check the local account's **tenant**, never trusting a request tenant to grant membership automatically.
4. Enforce exact matching/encoding per contract; avoid regexes like "contains admin".
5. Distinguish groups/departments from scoped permissions.
6. Sensitive roles require local entitlements or policies with appropriate assurance/step-up.
7. When groups are missing or attributes are malformed, **fail closed** for privileged roles.
8. Bound group count/length/format; prevent header overflows and memory abuse.
9. Revocation/role changes can occur after session/JWT creation; design a freshness strategy.
10. Never emit raw group names as metric labels or PII logs.

**Good model:** external groups are an input signal; **backend policy** decides GrantedAuthority. For sensitive actions, check permissions at the **resource level** on every request.

## 18. Servlet container roles: controlled mapping

A Servlet container may recognize roles like `auditor`, `billing-editor`, and `container-admin`. Spring J2EE pre-auth details can query:

~~~java
// Snippet running in a Servlet context with container auth configured:
boolean auditor = request.isUserInRole("auditor");
boolean billingEditor = request.isUserInRole("billing-editor");
~~~

In Spring's pre-auth framework, `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` collects **pre-declared** roles; `Attributes2GrantedAuthoritiesMapper` maps them to Spring authorities. **Never enumerate or accept arbitrary role names** from request parameters.

Example policy table:

| Container role | Internal authority | Additional condition |
| --- | --- | --- |
| `auditor` | `ROLE_VIEWER` | Active account, tenant membership |
| `billing-editor` | `ROLE_EDITOR` | Membership and authorized target object |
| `container-admin` | Do not auto-map `ROLE_ADMIN` | App admin must be separately approved |
| No role | Baseline access only if app policy allows | No special privileges granted |

**A container role is not an OAuth access token**, nor does it eliminate the need for CSRF/XSS/session protections.

## 19. Spring Security 6.x example: accepting a principal from an authenticated gateway

The following example targets **Spring Boot 3.x/Spring Security 6.x Servlet**, built for an internal API whose gateway is **network-isolated and authenticated via mTLS/service identity**. For clarity, Spring reads a fixed header `X-Verified-Subject` and maps it to accounts/authorities in a **local trusted directory**. The example **does not implement mTLS validation or header sanitization itself**: those are **mandatory deployment prerequisites at the edge/ingress/mesh**, not something a Spring header filter can replace.

File `src/main/java/com/example/security/GatewayPreAuthSecurity.java`:

~~~java
package com.example.security;

import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.AuthenticationUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;

@Configuration
public class GatewayPreAuthSecurity {

    // Application must supply a real database-backed implementation/bean.
    public interface TrustedAccountDirectory {
        LinkedAccount findByExternalIdentity(String trustedSource, String subject);
    }

    public record LinkedAccount(
            String localAccountId, boolean active, Set<String> appRoles) {}

    private static final String TRUSTED_SOURCE = "corp-gateway";
    private static final Set<String> ROLE_ALLOWLIST =
            Set.of("ROLE_VIEWER", "ROLE_APPROVER");

    @Bean
    AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>
            gatewayAccountLoader(TrustedAccountDirectory directory) {

        return token -> {
            String externalSubject = token.getName();
            if (externalSubject == null || externalSubject.isBlank()) {
                throw new UsernameNotFoundException("Missing gateway subject");
            }

            LinkedAccount account = directory.findByExternalIdentity(
                    TRUSTED_SOURCE, externalSubject);
            if (account == null) {
                throw new UsernameNotFoundException(
                        "No verified external identity link");
            }
            if (!account.active()) {
                throw new DisabledException("Local account is disabled");
            }

            // Authorities are granted by local DB/policy, NOT read from raw headers.
            List<GrantedAuthority> granted =
                    account.appRoles().stream()
                            .filter(ROLE_ALLOWLIST::contains)
                            .map(role -> (GrantedAuthority)
                                    new SimpleGrantedAuthority(role))
                            .toList();

            // Password marker is not used to authenticate pre-auth.
            // Do not use this UserDetails in password-based login.
            return new User(
                    account.localAccountId(),
                    "{noop}UNUSED_PREAUTH_PASSWORD",
                    true, true, true, true, granted);
        };
    }

    @Bean
    PreAuthenticatedAuthenticationProvider gatewayProvider(
            AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>
                    gatewayAccountLoader) {

        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(gatewayAccountLoader);
        provider.setThrowExceptionWhenTokenRejected(true);
        return provider;
    }

    @Bean
    SecurityFilterChain privateGatewayChain(
            HttpSecurity http,
            PreAuthenticatedAuthenticationProvider gatewayProvider)
            throws Exception {

        ProviderManager manager = new ProviderManager(gatewayProvider);

        RequestHeaderAuthenticationFilter preAuth =
                new RequestHeaderAuthenticationFilter();
        preAuth.setPrincipalRequestHeader("X-Verified-Subject");
        preAuth.setExceptionIfHeaderMissing(true);
        preAuth.setContinueFilterChainOnUnsuccessfulAuthentication(false);
        preAuth.setAuthenticationManager(manager);

        return http
                .securityMatcher("/private/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(new Http403ForbiddenEntryPoint()))
                .authenticationProvider(gatewayProvider)
                .addFilterBefore(preAuth,
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

### Conditions for the example to be safe and functional

1. **The gateway must authenticate the end user**, sanitize/overwrite the header, and never send anonymous requests to `/private/**`.
2. The backend **must not be directly reachable** and must enforce mTLS/service authorization before the Servlet request; otherwise, this code is **easily spoofed**.
3. Every external subject must link via **trusted source + subject** to a local account. With multiple issuers, extend to **issuer+subject** and a versioned trust contract.
4. The app must implement `TrustedAccountDirectory` and provide a bean; the example **does not create a database or account provisioning**.
5. Role mapping comes from the local trusted DB, not from `X-Verified-Groups`.
6. Requests in this chain must carry the right identity header; missing/invalid headers must not fall back to form login. Verify failure handling for your Spring version.
7. For browsers holding gateway cookies and state-changing methods, **CSRF still requires analysis/protection**; a stateless backend does not eliminate CSRF when the browser automatically sends credentials to the gateway.
8. If other routes exist, **other SecurityFilterChains must protect them**; do not treat `securityMatcher("/private/**")` as whole-application protection.
9. Versions/JDK/dependencies must align; this class is for a **Spring project**, **not** standalone Java.
10. Configure infrastructure guardrails **before** enabling this chain in production; Spring cannot verify gateway identity on its own.

**Illustrative limitation:** the external issuer is fixed in `TRUSTED_SOURCE`. For a gateway aggregating multiple IdPs, add issuer to the identity link and ensure the gateway/AS verifies it. Never use a user-supplied issuer header to select the trust provider.

## 20. Container pre-auth in Spring: component-level configuration

If the Servlet container already authenticates via its own mechanism, Spring can use `J2eePreAuthenticatedProcessingFilter` instead of reading gateway headers:

~~~java
// Bean wiring snippet for a Spring project; requires authenticationManager
// and real container-managed authentication/realm configured.
J2eePreAuthenticatedProcessingFilter containerFilter =
        new J2eePreAuthenticatedProcessingFilter();
containerFilter.setAuthenticationManager(authenticationManager);

// Add to SecurityFilterChain via addFilterBefore(...) per
// project filter ordering and protect container URLs at the server layer.
~~~

**Note:** `J2eePreAuthenticatedProcessingFilter` only extracts the container principal. To obtain container-verified roles, configure `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` with mappable roles and a mapper, or use a local UserDetailsService; **never assume all roles are automatically read from the container**.

If the container returns `getUserPrincipal() == null` or `isUserInRole() == false`, do not fabricate an "anonymous admin" principal/role and do not fall back to a raw header to fill the gap. Configure security constraints/realms on the app server and validate E2E.

## 21. When to choose OAuth2 Resource Server instead of header pre-auth?

| Scenario | Usually sensible design direction |
| --- | --- |
| Public API receives signed JWT access tokens with clear issuer/aud | **Spring OAuth2 Resource Server JWT** |
| Public API uses opaque tokens | **Spring Resource Server opaque token introspection** |
| Gateway authenticated browser SSO, private backend is unbypassable, header contract is protected | **Header pre-auth** may be appropriate |
| Governed Servlet container authenticated the request and supplies standard principal/roles | **Container pre-auth** |
| Access manager already produces signed assertions for the service | **Validate signed assertion** or token at backend |
| Many independent clients/tenants/cross-network hops | Prefer **cryptographically verifiable tokens**, audience, and issuance policy |
| User identity needs delegated authorization to downstream APIs | Use proper OAuth2 access tokens/delegation policy, **do not forward user headers blindly across APIs** |
| Service-to-service with no human user | **mTLS/service identity or OAuth client_credentials**, never fake a human username |

A header pre-auth contract should be used only within a **very clear trust domain**; it does not establish a standard identity federation protocol across arbitrary network boundaries.

## 22. Sessions and principal changes: an easy detail to miss

`AbstractPreAuthenticatedProcessingFilter` provides these options:

- `setCheckForPrincipalChanges(true)`: compares the incoming principal against the current Authentication; triggers re-authentication on change.
- `setInvalidateSessionOnPrincipalChange(true)`: when enabled and a principal change is detected, can invalidate the session via the configured strategy.
- `setContinueFilterChainOnUnsuccessfulAuthentication(false)`: avoids silently letting other filters attempt authentication after an AuthenticationManager failure.

Evaluate these options alongside your session strategy. **By default**, if `SecurityContext` already holds an Authentication, the pre-auth filter may skip re-checking the principal header on every request. Risk in session-backed browsers:

~~~text
Request 1: gateway subject = alice
  Spring session stores alice's Authentication

Gateway logs out alice, logs in bob in same browser
Request 2: gateway subject = bob
  If app still uses old Authentication without comparing principal,
  backend may process bob's request under alice's identity.
~~~

**Solutions by app type:**

- Stateless API: evaluate identity from the authenticated hop on **every request** and retain no unintended stale login state.
- Stateful browser app: consider principal-change detection and session invalidation, or integrate logout/session events.
- Account/tenant changes: when a user is locked or permissions change, enforce session revocation/role version checks.
- If `Authentication.getName()` is a **local account ID** while the header holds an **external subject**, default principal comparison may treat them as unequal. You need a **reliable custom mapping/comparator** or appropriate session strategy rather than toggling flags blindly and forcing re-authentication on every request.
- Systems with multiple logins: do not combine formLogin and header pre-auth in the same trust boundary without separation; the Javadoc explicitly warns of bypass risk.

**Do not just set `SessionCreationPolicy.STATELESS` and assume all cookie and CSRF risks disappear**. The browser may still send the gateway SSO cookie, and the gateway forwards the request into the backend.

## 23. Pulling roles from a centralized access system: what assurances suffice?

An access manager often computes roles/entitlements per policy. Three common patterns:

**A. Backend loads permissions from its own DB (often simplest to control):**
- Accept only the verified subject and trust source.
- Map to the local account.
- Load groups/permissions server-side with account status and tenant checks.
- Optionally treat gateway group claims as an additional vetted signal.

**B. Backend receives signed/verified roles from the access manager:**
- Explicit contract for issuer, service audience, entitlement version, TTL, role naming/tenant.
- Backend validates token/proof or relies on a trusted channel with gateway guarantees.
- Mapper constrains role names/scopes.
- Revocation policy when the access manager updates groups.

**C. Backend queries an authorization service at request time:**
- Used for sensitive privileges or rapidly changing scopes.
- Enforce timeout/fail-closed behavior, short cache TTLs, and auditing.
- Request includes authenticated subject, actor, tenant, action, and resource.
- Do not trust merely the gateway's verdict that "the user can reach this URL".

### Never create a global "role" spanning tenants

For example, group `finance-approvers` in tenant North does not grant approval rights in South. A role token/header issued for another application also must not automatically apply inside the current application.

**Mental formula:** effective privilege = **valid identity** ∩ **active account** ∩ **tenant membership** ∩ **valid role/permission** ∩ **resource rule** ∩ **required assurance/freshness**.

## 24. Standalone Java 17 demo: verifying trust context and authorization

The Java 17 example below runs on plain JDK to test **decision logic after an external system has provided authentication evidence**. It deliberately has upstream supply `ROLE_ADMIN` to prove the backend **does not grant admin when local permissions lack it**.

**File:** `PreAuthTrustBoundaryDemo.java`

~~~java
import java.util.Set;

public class PreAuthTrustBoundaryDemo {

    record ExternalIdentity(String source, String issuer, String subject) {}

    record Evidence(
            boolean trustedHop,
            boolean upstreamAuthenticated,
            ExternalIdentity identity,
            Set<String> externalClaims) {}

    record LocalAccount(
            String id,
            ExternalIdentity linkedIdentity,
            boolean active,
            Set<String> tenants,
            Set<String> appAuthorities) {}

    static String authorize(
            Evidence evidence,
            LocalAccount account,
            String tenant,
            String requiredAuthority) {

        if (!evidence.trustedHop()) {
            return "DENY_UNTRUSTED_HOP";
        }
        if (!evidence.upstreamAuthenticated()) {
            return "DENY_NO_UPSTREAM_AUTH";
        }
        if (evidence.identity() == null
                || evidence.identity().issuer() == null
                || evidence.identity().subject() == null
                || evidence.identity().subject().isBlank()) {
            return "DENY_INVALID_IDENTITY";
        }
        if (!evidence.identity().equals(account.linkedIdentity())) {
            return "DENY_IDENTITY_MISMATCH";
        }
        if (!account.active()) {
            return "DENY_DISABLED";
        }
        if (!account.tenants().contains(tenant)) {
            return "DENY_TENANT";
        }
        if (!account.appAuthorities().contains(requiredAuthority)) {
            return "DENY_AUTHORITY";
        }

        // externalClaims is intentionally NOT used to grant privileges directly.
        return "ALLOW " + account.id();
    }

    public static void main(String[] args) {
        ExternalIdentity user = new ExternalIdentity(
                "gateway-corp", "https://id.example.test", "u-42");

        LocalAccount active = new LocalAccount(
                "acct-7", user, true,
                Set.of("north"),
                Set.of("ROLE_VIEWER"));

        Evidence verified = new Evidence(
                true, true, user, Set.of("ROLE_ADMIN"));

        System.out.println("Valid viewer: "
                + authorize(verified, active, "north", "ROLE_VIEWER"));
        System.out.println("Claimed admin: "
                + authorize(verified, active, "north", "ROLE_ADMIN"));

        Evidence directCall = new Evidence(
                false, true, user, Set.of("ROLE_ADMIN"));
        System.out.println("Direct bypass: "
                + authorize(directCall, active, "north", "ROLE_VIEWER"));

        Evidence noUpstreamProof = new Evidence(
                true, false, user, Set.of());
        System.out.println("Unverified upstream: "
                + authorize(noUpstreamProof, active, "north", "ROLE_VIEWER"));

        ExternalIdentity otherIssuer = new ExternalIdentity(
                "gateway-partner", "https://partner.example.test", "u-42");
        Evidence wrongIdentity = new Evidence(
                true, true, otherIssuer, Set.of());
        System.out.println("Same sub wrong source: "
                + authorize(wrongIdentity, active, "north", "ROLE_VIEWER"));

        System.out.println("Wrong tenant: "
                + authorize(verified, active, "south", "ROLE_VIEWER"));

        LocalAccount disabled = new LocalAccount(
                "acct-7", user, false,
                Set.of("north"),
                Set.of("ROLE_VIEWER"));
        System.out.println("Disabled account: "
                + authorize(verified, disabled, "north", "ROLE_VIEWER"));
    }
}
~~~

Run on **JDK 17 or later**:

~~~bash
javac PreAuthTrustBoundaryDemo.java
java PreAuthTrustBoundaryDemo
~~~

**Exact stdout:**

~~~text
Valid viewer: ALLOW acct-7
Claimed admin: DENY_AUTHORITY
Direct bypass: DENY_UNTRUSTED_HOP
Unverified upstream: DENY_NO_UPSTREAM_AUTH
Same sub wrong source: DENY_IDENTITY_MISMATCH
Wrong tenant: DENY_TENANT
Disabled account: DENY_DISABLED
~~~

### Explanation

- **Valid viewer:** both hop and upstream are authenticated, external identity links to the right local account, and user holds view permission for North.
- **Claimed admin:** gateway carries claim ROLE_ADMIN, yet local app allows only ROLE_VIEWER so privileges are not escalated.
- **Direct bypass:** direct request lacking proof of a trusted hop is blocked before identity evaluation.
- **Unverified upstream:** gateway/hop did not prove the user was authenticated → deny.
- **Same sub wrong source:** matching subject string from a different issuer/source is not auto-linked to the account.
- **Wrong tenant:** global-looking role cannot bypass tenant membership.
- **Disabled account:** user authenticated upstream successfully, yet backend blocks the disabled local account.

**Crucial limitation:** the two booleans `trustedHop` and `upstreamAuthenticated` **assume post-verification evidence** to teach policy. The program **does not validate mTLS/JWT/session/gateway**, parse headers, or touch a DB or network. In production **never take these two booleans from request parameters/headers**; they must come from trusted security middleware/validators. This is **not a Spring AuthenticationProvider**, and must never be deployed as a production security filter.

## 25. Mistakes with request attributes and Forwarded headers

Not only headers, **request attributes** also require a trust boundary. An internal filter might attach:

~~~java
// Servlet code snippet in trusted upstream middleware:
request.setAttribute("verifiedPrincipal", verifiedUserId);
~~~

Spring's `RequestAttributeAuthenticationFilter` reads a designated request attribute, yet it is **safe only when that attribute is set by trusted middleware running in the proper order and unreachable by client manipulation**. If another component copies raw client input into an attribute, that merely moves untrusted data to a different container.

**Forwarded headers** (`Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`) primarily describe hops/network/URLs, **not identity proofs**. Spring's `ForwardedHeaderFilter` can process these values to reconstruct the original URL, yet **does not authenticate the end user**. If a trusted proxy fails to strip/rewrite them, they can be spoofed to corrupt redirect URIs, origins, callbacks, or audit logs.

### HTTP header normalization and duplicate headers

Proxies, ingresses, and containers can differ in how they handle:
- Header name casing.
- Hyphens versus underscores.
- Repeated headers or multiple values.
- Control characters, newlines, and Unicode values.
- Headers merged across multiple proxies or truncated.

**Never build an identity contract on arbitrary header names without testing the real pipeline.** Run standalone tests sending duplicate, mixed-case, and spoofed variants across every hop.

## 26. Reverse proxy/mesh topology: bypasses to uncover

A design that looks clean on a diagram can harbor side paths:

| Entry path | Risk | How to verify |
| --- | --- | --- |
| Public ingress → auth gateway → backend | Primary path | Verify authenticated gateway hop and header rewrite |
| Public ingress → backend service on another path | Auth bypass | Audit host/path routing and policies |
| Legacy backend NodePort/LoadBalancer | Direct backend calls | Remove ingress or enforce firewall deny |
| Kubernetes pod-to-pod | Internal pod impersonates gateway | NetworkPolicy/service-mesh authorization, mTLS peer identity |
| Internal VPN → backend admin port | Bypasses gateway | ACLs and dedicated authentication for admin interface |
| Health/metrics endpoint | Leaks info/role headers | Isolate endpoints with proper access controls |
| HTTP callback/webhook | Uses route bypassing auth gateway | Dedicated signature/mTLS and separate SecurityFilterChain |
| Service mesh sidecar → plaintext localhost app | Local bypass or misrouted traffic | Accept only from sidecar, container isolation, and policy |
| Background queue consumer | No HTTP gateway | Dedicated service identity and domain auth |
| Test/staging hostname pointing to production | Trust contract bypass | Host allowlists and environment-isolated configs/secrets |

**IP-based network allowlists are only one layer**, can shift with autoscaling/proxies, and do not prove end-user identity. In Zero Trust, prefer workload identity/authentication and continuous policy enforcement over merely "being inside the VPC".

## 27. Lifetimes, logout, and privilege revocation

A gateway pre-auth architecture typically has at least **three lifecycles**:

1. **Gateway/IdP session/token:** has its own expiry, refresh, logout, and account disable policies.
2. **Spring Authentication/local session:** can hold a snapshot of UserDetails/authorities if the app uses sessions.
3. **Local account/tenant permissions:** can change independently of both layers above.

Example:

~~~text
09:00 User completes SSO login at gateway
09:01 Gateway forwards verified principal; Spring creates session
09:15 Admin revokes user's ROLE_APPROVER
09:16 Spring session still holds old authority if not refreshed/revoked
09:30 Gateway SSO session expires
09:31 If backend still has direct access or a stale session,
      risk of reusing stale identity/role if policy is missing
~~~

This timeline is illustrative. **Never assume gateway logout will immediately invalidate all Spring sessions**, or that group changes synchronize on every request.

Mechanisms to consider:

- **Stateless per-request pre-auth:** evaluate trusted gateway identity on each request.
- **Short local sessions:** bound revocation lag when the app uses cookies/sessions.
- **Revalidation/entitlement lookup:** check sensitive permissions against the DB/authorization service per request.
- **Revocation events:** IdP/gateway can signal logout/disabled accounts to services, provided they are implemented and tested.
- **Account/role versions:** sessions or tokens carry a version; backend compares against current version.
- **Gateway assertion TTL:** trust proofs/tokens only within lifetime and for the right audience.
- **Principal changes:** a browser switching from user A to user B must not retain A in Spring's SecurityContext.
- **Multi-node:** session/role cache invalidation must take effect across all pods.

**Simply changing a header value does not guarantee Spring's UserDetails session updates**, especially when the filter skips principal-change checks because SecurityContext already holds an Authentication.

## 28. CSRF, cookies, OAuth scopes, and MFA must not be skipped

**Header pre-auth does not automatically exempt CSRF.** If the browser automatically sends a gateway SSO cookie to the access proxy, an attacker can attempt to trigger state-changing requests from another origin. Gateway and backend need **CSRF defenses suited to browser flows**, SameSite/cookie policies, and Origin/Referer validation as appropriate, rather than skipping them merely because the backend uses no HttpSession.

**OAuth scopes:** The gateway may verify an access token carries `scope=profile.read`, yet the backend must never infer `invoice.approve`. Audience must match the backend, and scopes and tenant policies must be mapped explicitly.

**MFA/step-up:** A header like `X-Auth-Method: mfa` is meaningful only when the gateway/IdP genuinely enforces and protects it under contract. For sensitive operations, the backend may require trustworthy `auth_time`/`acr`/`amr` evidence, maximum authentication age, and step-up sessions.

**XSS/clickjacking/session fixation:** Spring Security still needs standard defenses. Gateway authentication does not make the UI automatically safe.

**Client IP:** useful for auditing/rate limiting, not as an identity key. Never use a shared office public IP to map users.

## 29. Auditing and observability without exposing sensitive identities

Log these fields under a data-minimization policy:

| Field | Purpose |
| --- | --- |
| Request correlation ID | Correlate traces across gateway/authorization/backend |
| Trusted source ID | Identify which gateway/container/access manager was trusted |
| Auth mechanism type | E.g. GATEWAY_PREAUTH, CONTAINER_PREAUTH, OAUTH_JWT |
| External identity fingerprint | Investigate without exposing raw subject unnecessarily |
| Local account ID | Identify who performed the action |
| Tenant, action, resource ID | Audit domain authorization |
| Decision | ALLOW/DENY and categorized reason |
| Auth/role policy version | Detect stale permissions after deployment |
| Gateway hop identity | Prove the request traversed the right service identity |
| Assurance freshness bucket | Confirm authentication strength met policy without leaking credentials |

**Never log** raw JWTs, session cookies, SAML assertions, access tokens, plaintext passwords, private keys, full PII-laden group claims, or unbounded identity headers in APM. If pseudonymization is needed, use an internal HMAC key with governed rotation and retention.

**Limit account enumeration:** UI or HTTP errors should not reveal specifics like "username exists in IdP X" if callers should not know; internal logs can use controlled internal error codes.

## 30. Typical failures and diagnostics

| Symptom | Likely cause | Remediation |
| --- | --- | --- |
| Anyone sending `X-Verified-Subject: admin` gets in | Backend has direct ingress, lacks hop authentication | Block bypasses and authenticate gateway/mTLS |
| User logs in at gateway yet backend returns 403 | Identity unlinked, account disabled, or tenant role missing | Check local link and policy; do not grant default admin |
| RequestHeaderAuthenticationFilter does not run | Missing from right SecurityFilterChain/filter order | Check matchers and filter wiring |
| Header missing yet app runs another filter | Loose continue-chain/fallback policy | Separate mechanisms; fail closed at gateway/backend |
| Provider receives principal yet authorities are empty | UserDetailsService loads none or account unlinked | Check loader, role mapping, account DB |
| Header group "admins" grants ROLE_ADMIN | Raw authority mapping lacks allowlist | Map only owner-approved privileges |
| User switches A to B yet backend stays A | Stale SecurityContext/session, principal change unchecked | Stateless re-evaluation or session invalidation |
| Gateway logs out yet Spring session stays alive | Two separate session lifecycles | SLO/revocation/freshness policy |
| API succeeds using an ID Token | API lacks token type/audience checks | Proper Resource Server JWT validation |
| Container getUserPrincipal() returns null | Container auth realm/security constraints disabled | Enable container authentication, fail closed |
| Container role "admin" fails hasRole | Different prefix/mapping | Check mappable roles and mapper |
| User holds role in tenant North yet uses it in South | Global role lacks tenant isolation | Enforce membership/resource-level authorization |
| Same username across two gateways merges accounts | Lookup lacks issuer/source | Use verified source+issuer+subject |
| Strange underscores/duplicate headers | Proxies normalize differently | Audit sanitization/reject duplicate headers |
| Backend exposed via Kubernetes NodePort | Network bypass | Close public route, enforce network policy |
| Gateway forwards browser-set `X-Forwarded-For` | Spoofed forwarded headers | Strip/rewrite at trusted edge |
| Signed JWT expired yet header persists | Gateway ignores exp or backend skips freshness | Fix gateway validator, signed assertion exp |
| Role changes yet user keeps access | Stale authorities snapshot/caches | Evict caches or use online entitlement lookup |
| Gateway service cert rotation causes 401/503 | Broken mTLS trust/cert renewal | Fix SAN/CA/rotation; never disable verification |
| Two auth mechanisms share one route | Overlapping filter chains, bypass | Separate matchers and precedence |
| Gateway outage causes backend to admit directly | Fail-open fallback | Fail closed and add circuit breaker policy |
| Admin interface remains separately open | Bypass/alternate port | Enforce network identity controls on all ingresses |

**Never "quick-fix" by disabling TLS, accepting any certificate, hardcoding ROLE_ADMIN, or enabling an unapproved formLogin fallback.**

## 31. Security test matrix

| # | Scenario | Required outcome |
| --- | --- | --- |
| 01 | Client sends forged identity header to public gateway | Gateway strips and replaces with verified identity or rejects |
| 02 | Client calls backend directly with identity header | Blocked by network/hop auth |
| 03 | Non-gateway pod calls backend via internal service | Blocked by service policy/mTLS |
| 04 | Gateway has not authenticated the user | Sets no trusted identity for backend |
| 05 | Gateway properly authenticated the user | Backend resolves the right external identity link |
| 06 | Principal header is missing | Never defaults to anonymous/admin |
| 07 | Subject header is empty or whitespace-only | Rejected |
| 08 | Duplicate identity headers with differing values | Rejected or handled deterministically per strict contract |
| 09 | Header name case/underscore variant | Cannot evade sanitization |
| 10 | Header size/value exceeds policy | Rejected without causing DoS |
| 11 | Issuer not on allowlist | Identity not accepted |
| 12 | Same sub from two issuers | Treated as two distinct identities |
| 13 | Matching email, different issuer/sub | Not auto-linked |
| 14 | Unlinked local account | Onboarded/denied per policy |
| 15 | Disabled local account | Denied even while gateway still authenticates |
| 16 | X-Verified-Groups contains ROLE_ADMIN | Never auto-grants ROLE_ADMIN |
| 17 | Gateway role group from another tenant | Zero cross-tenant privilege |
| 18 | User holds only ROLE_VIEWER, attempts invoice approval | 403/domain DENY |
| 19 | Invoice belongs to another tenant | Domain DENY |
| 20 | SSO cookie auto-sent on unsafe cross-site POST | CSRF protection blocks it |
| 21 | Gateway logs out while Spring session is active | Verify session invalidation/freshness policy |
| 22 | Gateway switches user A→B in same browser | Never retains A's stale SecurityContext |
| 23 | Container getUserPrincipal is null | Creates no authenticated principal |
| 24 | Container role absent | Does not grant that role |
| 25 | Matching container role name in different scope | Policy maps accurately |
| 26 | Validly signed JWT with wrong audience | Rejected by Resource Server |
| 27 | Expired JWT / invalid issuer | Rejected |
| 28 | ID Token sent to API as access token | Not accepted as API auth |
| 29 | Gateway–backend mTLS cert has wrong service identity | Blocked |
| 30 | Reverse proxy/sidecar bypassed | Test fails; close ingress |
| 31 | Role revoked in local DB | Revocation SLA honored |
| 32 | Authorization service times out | Fails closed for sensitive privileges |
| 33 | Another SecurityFilterChain matches wrong path | Test matchers and ordering |
| 34 | Gateway headers written to access logs | Redacted with proper retention |
| 35 | Signed gateway assertion replayed past TTL | Rejected |
| 36 | Active access manager session while account locked | Backend local policy DENIES |
| 37 | New gateway release changes header schema | Contract versioning; fails closed on mismatch |
| 38 | Backend load balancer switches nodes | Consistent trust/cache/role policy |
| 39 | Gateway certificate revoked | mTLS authorization blocks that gateway |
| 40 | External API webhook without gateway user | Route uses dedicated webhook signature/service auth, never fakes human identity |

**E2E tests must exercise real gateway/container infrastructure**, not merely mock HTTP headers in Spring MockMvc. A unit test showing the filter reads `X-Verified-Subject` does not prove production resists spoofing.

## 32. Phased safe rollout runbook

### Phase A — Design the contract

1. Inventory gateways, access managers, containers, IdPs, and backend routes/services.
2. Define who authenticates end users, via which protocol, issuer, and assurance level.
3. Lock down the identity key: source/issuer+subject mapped to local account; avoid email.
4. Finalize header names, encoding, duplicate handling, max lengths, contract version, and who grants roles.
5. Define service audience, tenant membership, role allowlist, and resource rules.
6. Choose browser session vs. stateless API; specify session/CSRF/refresh/revocation.

### Phase B — Lock down the trust boundary

1. Block all public/direct backend ingresses; allow only gateway/trusted mesh identities.
2. Enforce TLS/mTLS, check SAN/peer identities, and manage cert lifecycles.
3. Edge strips all client identity headers prior to authentication.
4. Gateway rewrites trusted headers after successful authentication; reject anonymous.
5. Audit alternate ports, health/metrics, pod-to-pod bypasses, and webhook routes.
6. Design fail-closed behavior when gateway/access manager/authorization service fails.

### Phase C — Integrate Spring Security

1. Pick `RequestHeaderAuthenticationFilter` **or** `J2eePreAuthenticatedProcessingFilter` based on the real principal source.
2. Configure `PreAuthenticatedAuthenticationProvider` with a trusted account loader.
3. Verify the provider **does not validate upstream itself**, so infrastructure must supply proof.
4. Separate SecurityFilterChains by routes, forbidding lower-trust fallbacks.
5. Enforce local account status/tenant checks and role allowlists.
6. Protect CSRF/session/security context when browsers carry SSO cookies.
7. Where signed access tokens are used, prefer a Resource Server validator over bare headers.

### Phase D — Canary and cutover

1. Test legitimate login paths, direct backend spoofing, and duplicate header variants.
2. Test logout, A→B principal switching, role updates, and disabled accounts.
3. Test tenant isolation and object-level authorization.
4. Test mTLS rotation, gateway outages, backend failover, and DNS/reverse-proxy changes.
5. Monitor 401/403 rates, proxy failures, role denials, and suspicious bypass traffic.
6. Open traffic only after the security owner approves E2E trust-boundary proof.
7. Keep routing rollback ready, **never opening a direct header bypass** as an emergency workaround.

### Phase E — Operations

1. Monitor access manager/gateway sessions and backend account entitlement freshness.
2. Check for policy drift whenever adding IdPs, tenants, gateways, or services.
3. Periodically audit firewalls/NetworkPolicy and direct backend exposure.
4. Rotate secrets/certs and invalidate caches on events.
5. Audit role mappings, IAM ownership, and incident procedures.
6. Eliminate role/admin fallback exceptions and obsolete routes.

## 33. Self-assessment questions

**1. Is header `X-Verified-Subject: alice` enough to authenticate a user?**  
No. You must prove the gateway authenticated the user and the backend accepts the header only when set by the trusted gateway.

**2. Does `PreAuthenticatedAuthenticationProvider` verify JWTs or passwords itself?**  
No. It assumes upstream already authenticated and typically loads UserDetails/authorities.

**3. Does calling `getUserPrincipal()` guarantee the container authenticated the user?**  
Only when the Servlet container has properly configured and enforced an authentication realm/security constraints.

**4. Why should email not be used as the primary key for external identity?**  
Because email can change, be recycled, or collide across providers; use issuer/source + stable subject.

**5. Does `PreAuthenticatedGrantedAuthoritiesUserDetailsService` verify role headers itself?**  
No. It reads GrantedAuthorities from the details container; the details source must be trusted and policy-compliant.

**6. Is `isUserInRole("admin")` sufficient for all application admin rights?**  
No. Container roles and app business roles can differ; dedicated mapping and entitlements are needed.

**7. Why is gateway–backend mTLS still insufficient to prove the end user?**  
mTLS authenticates the gateway as a peer; the gateway must still prove it authenticated the end user and protected the identity assertion.

**8. Does gateway logout automatically destroy all Spring sessions?**  
Not by default. Session lifecycle/logout/revocation integration is required.

**9. If an API receives a valid JWT, should it extract `sub` and ignore `aud`?**  
No. Verify issuer, audience, timestamps, token type, and authorization.

**10. What can you do to avoid relying on header trust across multiple hops?**  
Prefer signed access/identity assertions with audience/expiry and a backend validator, or use OAuth2 Resource Server where appropriate.

**11. What if a user belongs to North, yet the header says tenant=South?**  
The backend must check membership and resource scope; never treat the header as auto-granted access.

**12. Why check for principal changes when using sessions?**  
Because the browser may switch logged-in users at the gateway while Spring's SecurityContext still holds the old principal.

## 34. Production checklist

- [ ] Complete diagram exists covering public gateway → access manager/mesh → backend hops.
- [ ] Backend has no direct access paths/alternate ports bypassing the auth gateway.
- [ ] Gateway proves end-user authentication rather than merely having a login page/redirect.
- [ ] Trusted gateway hop is authenticated at the backend (mTLS/service identity or equivalent).
- [ ] Gateway strips/overwrites all client-supplied identity headers; forwarding headers are never trusted as auth proof.
- [ ] Identity sources are versioned with exact issuer/source/subject mapping.
- [ ] No auto-linking by email or matching usernames across realms.
- [ ] `RequestHeaderAuthenticationFilter` is used only after a real trust boundary is guaranteed.
- [ ] `J2eePreAuthenticatedProcessingFilter` is used only when container auth is genuinely configured.
- [ ] `PreAuthenticatedAuthenticationProvider` has a local account/status and role loader; never assumed to verify upstream.
- [ ] External groups/roles are checked via allowlist, tenant, and business policy.
- [ ] Raw ROLE_ADMIN headers are never converted into admin privileges.
- [ ] Route-specific SecurityFilterChains exist with no impersonation-prone fallbacks.
- [ ] Policies cover stateless/session principal changes, logout, and revocation.
- [ ] Browser SSO cookie flows have appropriate CSRF protection.
- [ ] Signed JWT/opaque tokens are verified for type, issuer, audience, expiry, and scope.
- [ ] Tenant membership and object permissions are checked server-side on every operation.
- [ ] Timeouts/fail-closed behavior exist for account/authorization lookups.
- [ ] Unit tests cover mappers and E2E tests cover spoofing/bypass/mTLS/header normalization.
- [ ] Raw identity assertions, session tokens, or sensitive group claims are never logged.
- [ ] Monitoring tracks 401/403/cross-tenant denials with incident response procedures.
- [ ] Owners are assigned for trust contracts, certificate rotation, and release policies.
- [ ] Policies are re-verified after any ingress/gateway/IdP/tenant/container change.

## 35. Conclusion

**Obtaining identity and authorities from a gateway, container, or centralized access system** is a practical **pre-authentication** pattern for letting Spring Security enforce authorization while another system authenticates users. Spring supplies `RequestHeaderAuthenticationFilter`, `J2eePreAuthenticatedProcessingFilter`, `PreAuthenticatedAuthenticationProvider`, `AuthenticationUserDetailsService`, and GrantedAuthorities utilities.

Yet **reading an identity is not proving an identity**. Success depends on a **real trust boundary**, preventing header injection, scoping identity namespaces with issuer+subject, evidence-backed account linking, allowlisted role mapping, and tenant/resource authorization. When independent per-service assurance across multiple network hops is needed, **signed access tokens/verified assertions** are generally clearer than trusting bare headers. The gateway may authenticate the user, but **the backend must still decide what that user may do** and remains accountable for its own sessions and permissions.

### Official documentation

- Spring Security Reference — Pre-Authentication Scenarios, Request Header and Java EE Container: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- Spring Security Javadoc — RequestHeaderAuthenticationFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html
- Spring Security Javadoc — AbstractPreAuthenticatedProcessingFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
- Spring Security Javadoc — PreAuthenticatedAuthenticationProvider: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html
- Spring Security Javadoc — PreAuthenticatedGrantedAuthoritiesUserDetailsService: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedGrantedAuthoritiesUserDetailsService.html
- Spring Security Javadoc — J2eePreAuthenticatedProcessingFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/j2ee/J2eePreAuthenticatedProcessingFilter.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Authorization Architecture and Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Jakarta Servlet Specification — Request principal and isUserInRole: https://jakarta.ee/specifications/servlet/
- NIST SP 800-207 — Zero Trust Architecture: https://csrc.nist.gov/pubs/sp/800/207/final
