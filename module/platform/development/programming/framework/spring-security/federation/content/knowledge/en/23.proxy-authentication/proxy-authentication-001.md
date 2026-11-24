# Pre-authentication and authentication responsibilities performed at an upstream layer

**Pre-authentication** is a model in which a component sitting in front of the application — such as an **identity-aware proxy, API gateway, SSO-enabled reverse proxy, web access management agent, or servlet container** — has already verified the user's identity before the request reaches Spring Security. The application receives **the identity result already authenticated by that component**, rather than performing the full login step again with a password, Kerberos ticket, SAML assertion, or OIDC authorization code on every request.

In Spring Security, pre-authentication **does not mean bypassing Spring Security**. The framework still needs to: (1) obtain the trusted principal from the request/container, (2) create the `Authentication` in `SecurityContext` with the proper lifecycle, (3) load or map authorities, (4) reject requests that violate the trust boundary or come from unapproved accounts, and (5) enforce **authorization** on resources/tenants.

This is one of the easiest integration patterns to get wrong: if a public application reads `X-Verified-User: admin` from a header sent by any browser, an attacker can log in as admin **without authenticating at the proxy**. Spring Security's `RequestHeaderAuthenticationFilter` **only reads the header**; it does not verify signatures, tokens, login state, or proxy identity. Spring Security's documentation directly warns about identity spoofing when this filter is misused.

This article belongs to the **Proxy Authentication** group, covering trust architecture, layer responsibilities, configuring `RequestHeaderAuthenticationFilter`/`PreAuthenticatedAuthenticationProvider`, user/role mapping, session/identity lifecycle, failure modes, a Java 17 demo, a test matrix, and a production checklist. The `.example` domain, users, and policies in the examples are illustrative only; they are not production configurations or identities.

## 1. Distinguishing authentication, pre-authentication, and authorization

| Activity | Responsible party | Input | Output |
| --- | --- | --- | --- |
| **Actual authentication** | Trusted IdP/gateway/container | Credentials, session, Kerberos/SPNEGO, SAML, OIDC, client cert depending on the mechanism | Verified identity, authenticated state |
| **Pre-authentication adapter** | Spring Security in the backend | **Trusted identity signal** forwarded by upstream | `Authentication` and principal inside the app |
| **Identity mapping** | Approved app/identity directory | Issuer/realm + subject ID | Local account, active/locked status, tenant |
| **Authorization** | Spring + service/business layer | Local authorities, object permissions, tenant | Allow/deny per operation |
| **Session/revocation policy** | Gateway and application, each handling its share | Session lifetime, logout, offboarding, revalidation | No reuse of revoked identities |

**Authentication** answers "who is this request actually associated with?". **Authorization** answers "is that person allowed to perform this action in this context?". **Pre-authentication** is an **integration pattern between the two layers**, not a way to "mark every request as authenticated".

### Enterprise example

~~~text
User browser
  -> https://reports.corp.example/reports
  -> Identity-Aware Gateway
       checks OIDC login at corporate IdP + MFA + active session
       resolves trusted subject: employee-4102
       strips all client-supplied identity headers
       writes X-Verified-Subject: employee-4102
  -> private HTTPS/mTLS to Spring backend
       reads X-Verified-Subject ONLY on authenticated gateway hop
       loads local user 4102, status ACTIVE, tenant REPORTS
       assigns ROLE_REPORT_VIEWER from local policy
       checks the requested report belongs to tenant REPORTS
  -> HTTP 200 / 403
~~~

If the browser tries to send `X-Verified-Subject: ceo`, the gateway **must strip** that value and replace it with the authenticated identity or block the request. If the browser accesses the backend pod directly, the network/authn layer must block it **before the header filter processes it**.

## 2. Request flow and trust boundaries

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant G as Trusted Gateway
    participant I as Identity Provider
    participant S as Spring Backend
    participant D as Local Identity/Policy
    B->>G: GET /reports + cookies / request headers
    G->>G: Strip client-supplied identity headers
    alt No valid gateway session
        G-->>B: Redirect/401 to IdP
        B->>I: Login / MFA
        I-->>G: Verified identity per protocol
    end
    G->>G: Validate session, issuer, audience, expiration
    G->>G: Derive approved stable subject
    G->>S: Private HTTPS/mTLS + X-Verified-Subject: employee-4102
    S->>S: Confirm request came via trusted ingress
    S->>S: Pre-auth filter extracts principal
    S->>D: Look up active local user, tenant and authorities
    D-->>S: ROLE_REPORT_VIEWER
    S->>S: Check report ownership/tenant and authorization
    S-->>B: Response via Gateway
~~~

The diagram illustrates a **gateway with its own SSO mechanism**; SAML/OIDC/Negotiate details depend on the gateway product. The core point is that **Spring should only read the identity when trust in the gateway/hop has been proven by infrastructure or cryptography**. Merely seeing a header is not proof.

### Three separate boundaries

1. **Internet/Browser → Gateway:** a request can come from any client, and HTTP headers supplied by the user are **untrusted**.
2. **Gateway → Backend:** only approved gateways have access, with connections protected by network policies, firewalls/security groups, mTLS, or an equivalent mechanism. Identity headers are generated by the gateway after a real login.
3. **Spring → business data:** even a user authenticated upstream may only view resources authorized locally.

**Do not treat a private IP, `X-Forwarded-For`, or `X-Forwarded-Proto` header as sufficient proof that a request passed through the gateway**. A backend with a direct listener, a misconfigured ingress rule, or another sidecar could let an attacker attach these headers themselves.

## 3. What responsibilities must the proxy fulfill?

An **identity-aware proxy** entrusted with authentication responsibility must at least:

- Accept only sessions or credentials verified under a **standard authentication protocol** at the upstream layer: OIDC, SAML, Kerberos, client certificate, or policy-compliant session.
- Validate issuer/identity provider, audience/client/service, expiry, and flow constraints (**state**, **nonce**, signature when applicable), without trusting an ID Token/access token merely because it decodes to JSON.
- Check for locked accounts, expired sessions, logout/revocation, and **MFA/assurance** level if the resource requires it.
- **Strip all client-supplied identity headers** before computing and attaching gateway-generated headers.
- Ensure every path into the backend goes exclusively through a **valid gateway**; with no unintended "debug port", node IP, health ingress, or path bypass.
- Separate **identity headers** from `X-Forwarded-*` headers describing host/proto/IP; reserve a dedicated namespace solely for authenticated signals.
- Never allow users to freely choose `trusted issuer`, `principalId`, tenant, or role.
- Enforce header length and format limits; handle multiple same-named headers, header folding, Unicode, and duplicate case according to policy.
- Transmit identity over a protected channel, defending against packet capture, spoofing, and replay according to the threat model.
- Propagate a correlation ID/audit trail without containing sensitive credentials or tokens; log enough to attribute actions to a real upstream session.
- Implement fail-closed behavior when the IdP, policy engine, session store, or gateway identity validation fails.

If there are multiple gateways side by side, all must enforce **the exact same sanitize/overwrite rules**. A single gateway that "just forwards" client headers breaks the entire trust contract, even when all other gateways do the right thing.

### Which headers count as an authenticated identity?

Example of custom naming within an internal network:

~~~text
X-Verified-Subject: employee-4102
X-Verified-Issuer: https://login.corp.example/realms/employees
X-Verified-Tenant: reports
X-Verified-Assurance: mfa
~~~

These **are not headers with built-in security semantics merely because they carry an X-Verified prefix**. They only have value when:

1. **The proxy is configured/tested** to derive values from a verified login;
2. **The proxy strips/overwrites** any client-supplied copies of the same name;
3. **The backend cannot be called directly**, and authenticates/restricts the gateway hop;
4. Fields have clear schemas, issuer/tenant namespaces, and lifecycles;
5. The app uses the information only according to local policy, without granting admin from a role string.

A client-supplied `X-Verified-Assurance: mfa` header does not prove MFA. If the backend makes sensitive business decisions based on assurance, it should use a **trusted attestation** with a verified source/TTL/contract or verify a signed assertion directly, rather than merely comparing a literal string.

## 4. How does Spring Security understand pre-authentication?

Spring Security documentation lists these scenarios:

- **X.509 client-certificate authentication:** an external TLS stack receives the certificate; Spring uses the processed certificate/principal per trust setup.
- **Identity management agent/SiteMinder:** an external system authenticates and sends the principal via an HTTP request header.
- **Container-managed authentication:** the Servlet container has already authenticated the user and provides `HttpServletRequest.getUserPrincipal()`.
- **Custom proxy/Gateway:** the application can integrate under a specific contract using the pre-auth processing classes.

Spring Security needs to **obtain identity + authorities**, not re-verify a password or IdP redirect from a header inside `RequestHeaderAuthenticationFilter`.

Key classes:

| Class/interface | Responsibility |
| --- | --- |
| `AbstractPreAuthenticatedProcessingFilter` | Checks SecurityContext, extracts principal/credentials from the request, sends to `AuthenticationManager` |
| `RequestHeaderAuthenticationFilter` | Reads the principal (default `SM_USER`) from an HTTP header |
| `J2eePreAuthenticatedProcessingFilter` | Reads the principal provided by the servlet container |
| `PreAuthenticatedAuthenticationToken` | Carries principal and details through the auth pipeline |
| `PreAuthenticatedAuthenticationProvider` | Delegates to `AuthenticationUserDetailsService` to load `UserDetails`/authorities |
| `AuthenticationUserDetailsService<T>` | Loads the user based on the `Authentication` token, optionally using details |
| `UserDetailsByNameServiceWrapper` | Wraps a standard `UserDetailsService` into a compatible adapter |
| `PreAuthenticatedGrantedAuthoritiesUserDetailsService` | Uses authorities from token details when the contract is genuinely trusted |
| `GrantedAuthoritiesContainer` | Way to pass authorities from an external system into details per policy |
| `SecurityFilterChain` / `HttpSecurity` | Wires filters, authorization, and session policy |
| `SecurityContext` | Holds the Authentication for the request/session |

**The pre-authentication provider itself does not know the user's password**. Typically it checks the account/authorities from a local source and constructs an Authentication using an identity already deemed authenticated at the previous hop. If the identity source is not sufficiently trusted, do not use it as a pre-auth principal.

## 5. Processing lifecycle of AbstractPreAuthenticatedProcessingFilter

A typical `AbstractPreAuthenticatedProcessingFilter`:

1. Is invoked in the filter chain protecting the resource, checking `SecurityContext` according to version/configuration.
2. When authentication is needed, calls `getPreAuthenticatedPrincipal(request)` and `getPreAuthenticatedCredentials(request)`.
3. Creates an initial `PreAuthenticatedAuthenticationToken` (without authorities yet).
4. Sends the token to `AuthenticationManager`/`PreAuthenticatedAuthenticationProvider`.
5. The provider calls `AuthenticationUserDetailsService`, retrieving the valid user/roles.
6. If successful, places the result into `SecurityContext` according to the version's lifecycle and repository.
7. Authorization rules such as `hasRole("REPORT_VIEWER")` check the mapped user.
8. On failure, policy must **fail closed** — never letting protected routes proceed as an authorized anonymous user.

**The critical step not performed by the framework:** `RequestHeaderAuthenticationFilter` **does not verify who issued the header**. That is the combined responsibility of the proxy/network or a separately built backend cryptographic attestation verifier.

### Properties that change behavior

- `setPrincipalRequestHeader("X-Verified-Subject")`: name of the principal header; defaults to `SM_USER` for compatibility with legacy agents.
- `setCredentialsRequestHeader(...)`: reads a credentials header value if present; typically pre-auth has no password and defaults to a dummy value. **Do not pass the user's password or access token to the backend just to populate credentials**.
- `setExceptionIfHeaderMissing(true)`: `RequestHeaderAuthenticationFilter` throws `PreAuthenticatedCredentialsNotFoundException` if the header is missing (default true).
- `setExceptionIfHeaderMissing(false)`: allows the principal header to be missing; if the entire backend still requires `authenticated()` and has no auth fallback, a request missing the header is not treated as authenticated. Exact filter chain/exception handling must be verified.
- `setContinueFilterChainOnUnsuccessfulAuthentication(false)`: prevents swallowing `AuthenticationException` and trying another authentication mechanism on a pre-auth-only route. Modern versions may default to true, so check the resolved version's Javadoc.
- `setCheckForPrincipalChanges(true)`: compares the principal header against the current Authentication and refreshes on change (weigh overhead/policy).
- `setInvalidateSessionOnPrincipalChange(true)`: when principal-change checks are enabled, the old session can be invalidated when the principal changes to avoid reusing a session for the wrong user; verify exact behavior per version.

**Do not just set one property and claim every request is automatically 401.** Filter order, missing-header behavior, AuthenticationEntryPoint, Spring Security version, and other authentication mechanisms all affect the HTTP response. Fail-closed decisions must be proven with integration tests.

## 6. PreAuthenticatedAuthenticationProvider and role mapping

The provider is built to **load `UserDetails`**, not to re-verify passwords already used at the IdP/gateway:

~~~text
Trusted gateway header:
  X-Verified-Subject = employee-4102

RequestHeaderAuthenticationFilter
  -> PreAuthenticatedAuthenticationToken("employee-4102", dummy)
  -> AuthenticationManager
  -> PreAuthenticatedAuthenticationProvider
  -> AuthenticationUserDetailsService
  -> local UserDetailsService.loadUserByUsername("employee-4102")
  -> UserDetails { enabled=true, authorities=[ROLE_REPORT_VIEWER] }
  -> authenticated Authentication
~~~

If the user does not exist, is disabled, or lacks an entitlement, `UserDetailsService` must throw an error/enforce deny policy. Some user service setups only check a credential store without checking the tenant; local policy must be added.

### Preserving identity namespace boundaries

A multi-IdP/multi-tenant system must not treat the string `alice` as sufficient:

~~~text
Gateway issuer A: alice -> local user 100
Gateway issuer B: alice -> local user 999

Unsafe mapping:
  alice -> local user 100 (without storing namespace)

Safer mapping:
  (trustedIssuer, stableSubject) -> localUserId
~~~

If the gateway only sends `X-Verified-Subject` and the application accepts only a single fixed trusted issuer, the contract must explicitly document that namespace; if multiple issuers exist, both issuer and subject must be transmitted reliably in an **identity assertion** and verified before mapping. Do not simply accept an additional `X-Verified-Issuer` from the client request and concatenate the key.

### Should group/role headers from the proxy be used?

Be very careful. `PreAuthenticatedGrantedAuthoritiesUserDetailsService` can consume authorities from token details implementing `GrantedAuthoritiesContainer`, but that **does not verify the correctness of the role list**. If you only need authentication via the proxy, prefer looking up permissions in the application's database/policy engine.

If the gateway genuinely owns authorization for certain permissions, there must be a **strict contract** covering issuer, tenant, group mapping, freshness, revocation, and least privilege. Do not automatically turn `X-Verified-Groups: GlobalAdmins` into `ROLE_ADMIN` across every application.

## 7. Spring Security Servlet JavaConfig: header pre-auth + local roles

The code below is a **Spring project configuration template** for versions with the corresponding `SecurityFilterChain`/`RequestHeaderAuthenticationFilter` APIs. It is **not a standalone program runnable with javac**: it requires Spring Boot Web + Security dependencies, a real `UserDetailsService`, gateway infrastructure already blocking direct backend traffic, and the SecurityFilterChain wired into the application.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class TrustedProxyPreauthConfig {

    @Bean
    SecurityFilterChain preauthSecurityFilterChain(
            HttpSecurity http,
            UserDetailsService localUsers) throws Exception {

        // Account status, tenant, and roles are checked in localUsers.
        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
                userDetailsAdapter =
                new UserDetailsByNameServiceWrapper<>(localUsers);

        provider.setPreAuthenticatedUserDetailsService(
                userDetailsAdapter);

        AuthenticationManager authenticationManager =
                new ProviderManager(provider);

        RequestHeaderAuthenticationFilter preauthFilter =
                new RequestHeaderAuthenticationFilter();

        preauthFilter.setPrincipalRequestHeader("X-Verified-Subject");
        preauthFilter.setExceptionIfHeaderMissing(false);
        preauthFilter.setContinueFilterChainOnUnsuccessfulAuthentication(
                false);
        preauthFilter.setCheckForPrincipalChanges(true);
        preauthFilter.setAuthenticationManager(authenticationManager);

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/reports/**").hasRole("REPORT_VIEWER")
                .anyRequest().authenticated())
            .addFilterBefore(
                preauthFilter,
                UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Mandatory prerequisites before use:** `X-Verified-Subject` must be **stripped and overwritten** by the gateway, and the backend **must not** be reachable from the Internet/untrusted workloads. This code itself **does not verify source IP, client certificates, or identity assertion signatures**. That is the trust layer infrastructure must guarantee (or a dedicated verifier running before the pre-auth filter).

**Why choose STATELESS in this example?** This pattern expects the proxy to attach the verified identity **on every request**. When Spring does not rely on a server-side session to retain a previous Authentication, losing the identity header on a subsequent request will not reuse an authenticated session. However, session policy **does not authenticate the gateway** and must be tested alongside CSRF, API/browser flows, the security context repository, and the real application.

**Why `setExceptionIfHeaderMissing(false)`?** The health endpoint is permitted without an identity; all remaining routes are restricted by `authenticated()`/`hasRole`. This is a **specific design choice**, not a recommendation to disable the exception for every app. If you want every request on a gateway-only chain to require the header, you can leave the default true and split health/anonymous endpoints into a separate chain. Each branch's HTTP status/error handler must be tested.

**Why not declare `@Bean RequestHeaderAuthenticationFilter`?** In Spring Boot, a servlet `Filter` bean may be auto-registered by the container **outside** the Spring Security filter chain unless its ordering/registration is explicitly managed, causing double execution or wrong ordering. The example creates the filter inline inside the chain to simplify scope. In multi-chain systems, `securityMatcher` selection and filter placement must be explicitly designed.

**Why `setContinueFilterChainOnUnsuccessfulAuthentication(false)`?** So that a provider failure is not ignored and allowed to fall through to another less secure auth mechanism. In systems that also have an approved login form, use separate chains/path trust boundaries instead of accidentally letting header authentication fail and **fall back** to an authentication method that bypasses the gateway.

### What must be added in real production systems

- A `UserDetailsService` bean backed by real data sources/identity links, checking active/locked/tenant state.
- An AuthenticationEntryPoint and consistent handler for 401/403 or proxy redirect semantics; the code above does not guarantee a specific status.
- A mechanism to authenticate the **gateway hop**/mTLS, network policies, ingress listeners, and header sanitization.
- Principal normalization, issuer-scoped keys, and tenant allowlists per contract.
- Audit/correlation IDs, session/CSRF design, error handling, and rate limiting.
- Integration tests against the **exact resolved Spring Security/Boot version**.

## 8. Illustrative local UserDetailsService example

In a single-issuer application, a local service looking up by ID can be used:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

UserDetailsService localUsers = subject -> {
    if (!"employee-4102".equals(subject)) {
        throw new UsernameNotFoundException("Unknown local subject");
    }
    return User.withUsername(subject)
            .password("{noop}NOT_USED_FOR_PREAUTH")
            .roles("REPORT_VIEWER")
            .disabled(false)
            .build();
};
~~~

**This is only an illustrative fragment, not a database implementation**. The dummy password is not used to authenticate at the pre-auth provider; in production do not hardcode or rely on fake passwords as a security measure. User status/roles must come from a verified business source; if the application also allows form/password login, never use a placeholder password as an actual account credential.

The field `employee-4102` is a **stable subject authenticated by the gateway**, not a user-mutable `displayName`/email. With multiple issuers, pass the principal namespace in a trusted identity key/attestation and map it to the internal ID. **Do not automatically lower-case the subject** if the IdP contract treats case as significant.

## 9. Paths into the backend: no gateway bypass allowed

An insecure flow:

~~~text
Public internet
  -> https://portal.example.com (gateway verifies login)
  -> http://spring-backend:8080 (Spring reads X-Verified-Subject)

BUT ALSO:
Public internet -> http://spring-backend-public-ip:8080
  with X-Verified-Subject: admin
  -> Spring treats admin as authenticated
~~~

**This is a critical vulnerability.** Headers from a client on a direct path go straight into the Spring filter. No Spring property can turn a user-supplied HTTP header into a valid authentication assertion when the trust boundary is missing.

### Mandatory controls

1. The backend listens on a private interface/subnet and firewalls/security groups block every source other than the gateway.
2. In Kubernetes, `ClusterIP`/NetworkPolicy allows only designated ingress pods to call the backend; restrict internal pods in the same cluster too, not only Internet traffic.
3. The ingress controller/gateway strips all inbound identity headers prior to authentication, including duplicate spellings or hyphen/underscore variants that stacks might interpret differently.
4. The gateway generates the header solely from the identity context after verifying session/credentials.
5. Gateway↔backend uses TLS/mTLS or an equivalent connection per threat model; with mTLS, verify the client cert identity matches the right gateway, not merely "any valid cert".
6. Strip/do not forward authentication headers through untrusted secondary proxies, caches, or middlewares; maintain an explicit chain inventory.
7. Run network tests verifying that direct pod/NodePort/load-balancer/management endpoints cannot bypass.
8. Restrict health/admin listeners and separate public/untrusted routes from the pre-auth-only chain.
9. Test that **spoofed headers** from the Internet are stripped or blocked.
10. Monitor for policy drift after deployments or Kubernetes ingress changes.

**An IP allowlist alone is not strong enough identity verification** in all cloud/service-mesh architectures: pods/IPs can change, NAT can share addresses, or a gateway host can run multiple workloads. Choose workload/service identity + network segmentation + TLS as required.

## 10. Ingress proxy and header contract example

Some gateway products use auth sub-requests, an OIDC proxy, a SAML gateway, or a sidecar. The guidelines below are a **logical contract**, not a complete nginx.conf you can paste into production:

~~~text
ON PUBLIC REQUEST:
  drop any inbound X-Verified-Subject
  drop any inbound X-Verified-Issuer
  drop any inbound X-Verified-Tenant
  authenticate the browser/session using approved IdP
  reject unauthenticated/expired/revoked sessions
  derive immutable subject and verified issuer
  set X-Verified-Subject and related fields from trusted identity context
  proxy only to private backend over authenticated hop

ON BACKEND:
  accept requests only from the authenticated gateway identity
  do not trust headers on direct/untrusted routes
  find local user and authorities
  deny unknown/disabled user or wrong tenant
  apply resource-level authorization
~~~

**Do not implement this by simply writing `proxy_set_header X-Verified-Subject $http_x_verified_subject;`**: in many proxy stacks, `$http_x_verified_subject` carries the exact value **sent by the client**. Forwarding it directly lets an attacker choose their own username. You need an internal proxy identity source populated **after authentication** and a mechanism that overwrites from it; if the gateway lacks a trusted user API/variable, do not configure header-based pre-auth.

### X-Forwarded headers are not authentication assertions

`X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, and `Forwarded` describe client IP/scheme/host across proxies; they carry no guarantee that a user has been authenticated. Only trust segments added by trusted proxies after stripping untrusted values. Even when `X-Forwarded-For` accurately identifies an IP, **an IP is not a user principal**.

Setting `server.forward-headers-strategy=framework` enables Spring Boot to process forwarded host/proto for URL generation, but **does not verify who created the headers**. The gateway/ingress must protect the source; never use an IP or hostname from a client header to decide the user.

## 11. When to use headers, and when to use signed assertions or JWTs?

There is no single "right method for every architecture". Choose based on trust boundaries and verification capability:

| Identity propagation type | Advantages | Risks/conditions |
| --- | --- | --- |
| **Plain internal identity header** | Simple; fits private trusted-hop setups | Safe only when network/mTLS/gateway sanitization are genuinely guaranteed; no per-header proof |
| **Signed gateway assertion/JWT** | Backend can verify issuer, audience, signature, expiry | Requires key rotation, alg allowlist, replay/privacy controls; never trust claims before verifying |
| **Direct OIDC Access Token** | Backend acts as OAuth2 Resource Server | Must check Access Token intended audience/scopes; differs from pre-auth headers and ID Tokens |
| **Mutual TLS client cert** | Backend verifies service/gateway identity via cert | Does not authenticate the **end-user** if only the gateway has a cert; still needs user binding |
| **Container principal** | Container verifies authentication and exposes `getUserPrincipal()` | Unavailable if container is unconfigured; principal is not a raw header |
| **Native browser OIDC Login** | Spring handles code/ID Token itself, trusts no raw headers | Suitable when the app itself acts as RP and needs to manage login |

If the gateway issues a **signed JWT** to the backend, a solid approach is `oauth2ResourceServer().jwt()` with validators for issuer/audience/exp and token purpose, provided the token is genuinely an access token intended for the API. Do not manually call `jwt.decode()` and construct an authenticated `UsernamePasswordAuthenticationToken` without cryptographic verification. If the token is a **custom gateway identity assertion**, use a dedicated verifier with an explicit contract; do not assume every JWT follows the OAuth2 Resource Server profile.

**JWT signatures do not replace channel controls** when replay/exfiltration risks exist; likewise, mTLS to the gateway **does not authenticate the user** if headers are not bound to a valid session.

## 12. Mistakes regarding authenticationDetails and roles

An `Authentication.getDetails()` object can hold metadata such as remote address/session ID. Spring Security's pre-auth documentation also permits configuring a `GrantedAuthoritiesContainer` inside details to carry authorities from an external container.

**Do not treat every attribute in details as trustworthy**. The source populating details must be verified via gateway/container trust. Flags like the servlet container's `isUserInRole()` are only trustworthy when the **container** itself authenticated the principal and mapped roles properly. An `X-Groups` header added by a browser does not become a trusted `GrantedAuthority` simply because it was placed into details.

If group membership must be forwarded from the gateway:

- Accept only issuer + stable subject + role claims verified by the gateway under contract.
- Restrict role values to an allowlist, avoiding regex mappings like "contains Admin".
- Clearly state which policies are **gateway authorization** and which are **app local authorization**.
- Ensure disabled/offboarded accounts are checked at the backend or covered by a session revocation SLA.
- For multi-tenant systems, scope permissions by issuer/tenant/resources; never rely on bare group names alone.
- Keep an audit trail of who approved the permission mapping.

## 13. Sessions, principal changes, and logout

A gateway typically maintains an **upstream SSO session**, while Spring may use either a **local HTTP session** or stateless per-request processing. These are **two distinct states**.

| Scenario | Risk if undesigned |
| --- | --- |
| Browser logged out of gateway but still has Spring JSESSIONID | App continues trusting the old Authentication |
| User A logs into gateway then switches to B in the same browser | Spring retains A's SecurityContext if not re-evaluated |
| Proxy session expires yet proxy still sends a cached identity header | Backend accepts a revoked user |
| App has public bypass routes and protected routes sharing a session | Authentication can carry over across trust contexts |
| Multiple Spring nodes share a session store | Stale roles/identities diverge when policies change |
| Gateway MFA session expired while backend session remains alive | Sensitive operation relies on stale assurance |

### Two models

**Model A — stateless per request (matches the JavaConfig example):** The gateway verifies the session and emits the verified header on **every request**; the backend does not rely on a long-lived persisted `SecurityContext`. If the header disappears, protected routes fail. This incurs local user lookup/caching costs and requires explicit refresh/revocation policies.

**Model B — stateful Spring session:** Spring creates a session after pre-auth and reuses it on subsequent requests. You must configure SecurityContextRepository, session fixation/concurrency, principal-change detection, logout propagation, or clear TTL/revalidation. **Never assume gateway logout automatically clears Spring's `JSESSIONID`**.

### Identity switching and Spring filter options

`setCheckForPrincipalChanges(true)` lets the filter compare the current principal with the principal extracted from the request; `setInvalidateSessionOnPrincipalChange(true)` takes effect when a session exists and principal-change detection triggers. However, missing headers, custom principal normalization, multi-issuer identities, and multiple authentication chains can behave differently; test the exact behavior for your framework version rather than relying on a single flag.

**Do not disable `csrf` site-wide** just to make pre-auth work. If the browser carries cookies and makes state-changing requests, CSRF still needs analysis. In a stateless API with gateway-injected headers, CSRF/risk depends on the browser credential model and system policy, not an automatic exemption.

## 14. MFA, authorization context, and step-up

The gateway can prove the user completed basic login, yet a business action such as approving a payment may require **fresh MFA** (*step-up authentication*) or separate assurance.

Example:

~~~text
GET /reports
  requires authenticated user + ROLE_REPORT_VIEWER

POST /payments/approve
  requires local ROLE_PAYMENT_APPROVER
  and independently verified recent MFA assurance
  and dual control / maker-checker business rule
~~~

A string like `X-Verified-Assurance: mfa` is safe only if the gateway generated it from a **trusted authentication context**, with expiration, issuer/audience, replay/freshness policy, and a non-bypassable backend. If the gateway cannot guarantee freshness, the application must trigger a protocol-level redirect/step-up or verify a signed assertion carrying `auth_time`/`acr`/`amr` per contract.

**Never grant payment approval rights based solely on a role or assurance header**. Authentication strength and authorization entitlement are two independent checks.

## 15. Correctness of identity mapping

In an enterprise, a user may have multiple identifiers:

~~~text
Gateway subject:        employee-4102
OIDC upstream subject:  00u.... (per issuer)
Email:                  an@example.org
Display name:           Nguyen An
Local user:             internal-user-704
Tenant:                 reports-corp
~~~

If the application keys users by email, changing an email or having another tenant create a matching email can cause an account collision. Prefer a **stable subject guaranteed by the IdP/gateway**, scoped by issuer/tenant with a proper migration process.

**Things to verify:**

- Never use a client-supplied `X-Remote-User` header.
- If the gateway allows multiple IdPs, preserve **issuer + subject** and an account-linking policy.
- Never auto-canonicalize case/Unicode if the source ID treats them as distinct.
- Never use displayName as a key.
- When `UserDetailsService` cannot find the user, reject or use JIT provisioning **only under an approved policy**.
- When a user is disabled, the backend must stop granting access even if the gateway session remains valid.
- Prevent local username aliases/duplicates and user deletion/reuse collisions.

## 16. Observing logs and isolating failures by layer

When a flow fails, you need to know **whether authentication happened at the gateway**, **whether the header was attached**, **whether Spring found the local user**, and **whether the app granted permission**.

| Symptom | Suspected layer | What to check? |
| --- | --- | --- |
| Gateway keeps redirecting to login | Upstream login/session/cookie | IdP redirect/callback/session/MFA |
| Request never reaches backend | Gateway ACL/network/route | Ingress route, auth subrequest, backend health |
| Backend receives header but rejects gateway | mTLS/service identity/network policy | Certificate/ingress identity, path bypass |
| `PreAuthenticatedCredentialsNotFoundException` | Missing principal header | Proxy injection logic, header strip, filter config |
| `UsernameNotFoundException` | Local user lookup | Issuer-scoped identity, provisioning, account disabled |
| Spring 401/403 after gateway login | Filter order/authorization | SecurityContext, UserDetails, requestMatchers |
| User A sees B's data | Session identity collision/tenant authorization | Principal changes, local mapping, object-level policy |
| Disabled user still has access | Stale session/revocation | Gateway session expiration, local cache TTL |
| User receives wrong ROLE_ADMIN | Overly trusted group/role header | Local authority mapper, allowlist |
| Browser spoofs `X-Verified-Subject` and logs in | Header sanitization/direct backend bypass | **Security incident — block immediately, fix trust boundary** |
| External X-Forwarded-Host alters redirect | Broken trusted proxy forwarding | Strip/replace Host/Forwarded chain |
| Health check missing header returns 500 | Missing-header behavior on public route | Split chains or set exceptionIfHeaderMissing false |
| Backend still sees auth after gateway logout | Stale Spring session | Stateless request or coordinated session invalidation |
| Fails only on pod B | Misaligned ingress/identity injection config | Compare network policies, filter chains, deployment config |

### Minimal yet sufficient logging

Logs should include a request correlation ID, verified gateway/service ID, **local user ID**, tenant, and decision code (authenticated/denied/unknown). Never log raw access tokens, ID tokens, cookies, client secrets, SAML assertions, Kerberos tickets, full identity headers, or unnecessary personal data.

**If header injection from the Internet succeeds, do not patch just one endpoint:** inspect every entry path, abused sessions, admin privileges, and accessed data, and execute incident response according to enterprise policy.

## 17. Standalone Java 17 demo: simulating the trust contract between gateway and Spring

The **plain Java** program below helps learners distinguish **trusting the gateway channel** from **authorizing resources for a user**. It uses an identity record containing edge-declared subject, issuer, tenant, assurance, and role, alongside a local policy granting roles from a simulated database.

Important: the `evaluate` method **does not actually verify TLS/mTLS, signatures, OIDC tokens, or gateway sessions**. The booleans `trustedGatewayHop` and `headersSanitized` merely simulate checks that infrastructure **already** performed. Do not use this program to create production Authentication objects.

Create the file **`TrustedGatewayPreauthDemo.java`**:

~~~java
import java.util.Map;
import java.util.Set;

public class TrustedGatewayPreauthDemo {

    record EdgeIdentity(
            String subject,
            String issuer,
            String tenant,
            String assurance,
            String claimedRole) {}

    static final String ISSUER =
            "https://login.corp.example/realms/employees";

    static final Map<String, Set<String>> LOCAL_ROLES = Map.of(
            "employee-4102", Set.of("ROLE_REPORT_VIEWER"));

    static String evaluate(
            EdgeIdentity identity,
            boolean trustedGatewayHop,
            boolean headersSanitized) {

        if (!trustedGatewayHop) {
            return "DENY: untrusted gateway hop";
        }
        if (!headersSanitized) {
            return "DENY: headers not sanitized";
        }
        if (identity == null
                || identity.subject() == null
                || identity.subject().isBlank()) {
            return "DENY: missing subject";
        }
        if (!ISSUER.equals(identity.issuer())) {
            return "DENY: unexpected issuer";
        }
        if (!"reports".equals(identity.tenant())) {
            return "DENY: tenant not allowed";
        }

        Set<String> localRoles =
                LOCAL_ROLES.get(identity.subject());
        if (localRoles == null) {
            return "DENY: local user not approved";
        }

        if (!"mfa".equals(identity.assurance())) {
            return "DENY: assurance too low";
        }

        // Do NOT trust identity.claimedRole() for local authorities!
        return "ALLOW: " + String.join(",", localRoles);
    }

    public static void main(String[] args) {
        EdgeIdentity user = new EdgeIdentity(
                "employee-4102",
                ISSUER,
                "reports",
                "mfa",
                "ROLE_ADMIN");

        System.out.println("Trusted: "
                + evaluate(user, true, true));
        System.out.println("Direct: "
                + evaluate(user, false, true));
        System.out.println("Unstripped header: "
                + evaluate(user, true, false));

        EdgeIdentity unknownUser = new EdgeIdentity(
                "outside-999", ISSUER, "reports", "mfa", "ROLE_USER");
        System.out.println("Unapproved: "
                + evaluate(unknownUser, true, true));

        EdgeIdentity otherTenant = new EdgeIdentity(
                user.subject(), ISSUER, "payments", "mfa", "ROLE_ADMIN");
        System.out.println("Wrong tenant: "
                + evaluate(otherTenant, true, true));

        EdgeIdentity weakLogin = new EdgeIdentity(
                user.subject(), ISSUER, "reports", "pwd", "ROLE_ADMIN");
        System.out.println("No MFA: "
                + evaluate(weakLogin, true, true));

        EdgeIdentity wrongIssuer = new EdgeIdentity(
                user.subject(), "https://attacker.example",
                "reports", "mfa", "ROLE_ADMIN");
        System.out.println("Wrong issuer: "
                + evaluate(wrongIssuer, true, true));

        System.out.println("External admin promoted: "
                + evaluate(user, true, true)
                    .contains("ROLE_ADMIN"));
    }
}
~~~

Compile and run on JDK 17 or later:

~~~bash
javac TrustedGatewayPreauthDemo.java
java TrustedGatewayPreauthDemo
~~~

**Exact stdout:**

~~~text
Trusted: ALLOW: ROLE_REPORT_VIEWER
Direct: DENY: untrusted gateway hop
Unstripped header: DENY: headers not sanitized
Unapproved: DENY: local user not approved
Wrong tenant: DENY: tenant not allowed
No MFA: DENY: assurance too low
Wrong issuer: DENY: unexpected issuer
External admin promoted: false
~~~

**Point-by-point explanation:**

- `Trusted` is allowed **because the demo assumes the gateway has been verified + headers sanitized + local account/tenant/MFA and role are valid**.
- `Direct` is denied even though the identity body looks like a valid user, because the request did not arrive from a trusted hop.
- `Unstripped header` denies because the browser could have supplied an arbitrary principal.
- `Unapproved` denies an account absent from the local store.
- `Wrong tenant` is denied when the tenant does not match the resource contract.
- `No MFA` illustrates a policy requiring appropriate assurance.
- `Wrong issuer` shows identifiers must be scoped; however, string-comparing issuer is **not** real signature verification.
- `External admin promoted: false` shows `claimedRole=ROLE_ADMIN` is not automatically mapped to local privileges.

**Do not turn `trustedGatewayHop=true` into a hardcoded value in production Spring code.** Knowing whether the gateway is genuinely trusted requires network/service identity/mTLS/signatures or an organization-approved mechanism; only then may the pre-auth filter accept the principal. The demo code also does not implement sessions, CSRF, authentication filters, or real HTTP networking.

## 18. Mandatory test matrix for proxy pre-auth integration

| Test | Scenario | Expected outcome |
| --- | --- | --- |
| Gateway SSO | User logs in via approved IdP | Gateway verifies session/credentials before attaching header |
| Anonymous | No gateway login yet | Gateway redirects/401, attaches no verified identity |
| MFA policy | User logged in with password only | Sensitive route cannot bypass step-up |
| Valid identity | Valid gateway sends verified subject | Spring loads the right local user |
| Missing header | Protected request lacks principal | Not authenticated |
| Forged principal | Browser sends `X-Verified-Subject: admin` | Gateway strips/overwrites, backend never receives admin |
| Duplicate identity headers | Client sends multiple values/case variants | Proxy canonicalizes and blocks ambiguous request |
| Direct backend | Accessing NodePort/pod/private IP bypassing gateway | Network/mTLS rejects |
| Wrong gateway cert | Unauthorized workload holds a client certificate | Backend does not trust |
| Proxy skipped path | URL-encoded/alternate host bypasses auth route | Blocked, never reaches protected backend |
| Alternate ingress | Calling backend via secondary ingress/debug endpoint | Does not bypass pre-auth |
| Valid external subject | `employee-4102` + approved issuer | Local lookup in the right namespace |
| Unknown issuer | Attestation from a source not on allowlist | Deny |
| Same username, different issuer | Two users both named `alice` | Never merged into one local account |
| Unknown local user | Gateway auth OK, local record missing | Deny or JIT under reviewed policy |
| Disabled account | Locally disabled while gateway session remains | App denies |
| Local role missing | User has identity, lacks role for resource | HTTP 403 per policy |
| Role spoof | Header contains `ROLE_ADMIN` | Admin is never granted from raw header |
| Tenant boundary | Reports user reads Payments data | Deny |
| Gateway logout | Gateway session expired/revoked | Backend does not reuse old authenticated session |
| Identity switch | User A → B in browser | Does not retain A's SecurityContext/roles |
| Gateway 5xx/session store down | Proxy cannot verify identity | Fail closed, never forward verified header |
| Proxy header rules change | One gateway node forgets to sanitize | Test detects and blocks drift |
| Forwarded header spoof | Client sets `X-Forwarded-Host`/For | Never alters auth/redirect/tenant trust |
| Session fixation | Identity changes across requests/sessions | Never retains privileges from old principal |
| CORS/CSRF | Cross-site browser request | Never bypasses business rules just because of pre-auth |
| Spring filter chain | Request traverses the right chain | Filters run in proper order/routes |
| Java role mapping | `UserDetailsService` returns local authorities | Does not use unreviewed proxy groups |

**Merely mocking `Authentication` in Spring MVC tests is not enough**: it tests controllers/RBAC, but does not verify gateway header sanitization, direct backend isolation, mTLS, or real session logout. You need E2E tests traversing the gateway and negative tests intentionally sending spoofed headers on authorized test paths.

### Awareness test example using curl

~~~bash
# In an authorized lab, call the public GATEWAY with a forged header:
curl -i \
  -H "X-Verified-Subject: admin" \
  "https://reports.corp.example/reports"

# Direct backend test must be rejected by network/mTLS:
curl -i \
  -H "X-Verified-Subject: admin" \
  "https://backend-test-private.example/reports"
~~~

The hosts above are illustrative. There is no fixed stdout, and HTTP 200 from the gateway must not be treated as proof of security PASS: you must check **which user the backend received**, whether the header was generated by the gateway itself, and the actual account roles. If the direct path returns a response with admin privileges, that is a **security bug that must be fixed**, not something acceptable in staging.

## 19. Isolating filter chain scopes and other authentication mechanisms

An application can expose multiple endpoint categories:

~~~text
/health                health checks requiring no identity
/reports/**            proxy-preauthenticated web app
/api/**                OAuth2 resource server with bearer access token
/login/**              OIDC RP login if the app has its own flow
/internal/**           mTLS service-to-service
~~~

Do not place a `RequestHeaderAuthenticationFilter` trusting raw headers across **all** paths and then stack form login/OIDC/Bearer on the same poorly designed chain; that can weaken one mechanism via fallback or misread users across request contexts.

Design choices:

- Create a dedicated **SecurityFilterChain** for proxy-only routes; every request reaching this chain must come from a trusted proxy.
- API bearer-token routes use a chain with `oauth2ResourceServer(...)` and issuer/audience validation.
- Health endpoints get a permitAll chain, but **only exposed on the appropriate network/port**.
- Native form/OIDC login should live on its own chain/path with its own state/session/CSRF rules.
- When the gateway terminates TLS and injects identity, Spring must trust only **that network interface**, never mixing it with a public listener.
- Where the proxy sends a **signed bearer access token**, consider resource-server validation rather than merely extracting `sub` into a header.

**Never use `anyRequest().permitAll()` or anonymous with a default authority as a "fallback" when pre-auth fails.** Fail closed, return well-designed 401/403 responses, inspect logs, and fix the trust boundary.

## 20. Container and X.509 pre-auth: same concept, different source

Spring Security does not limit pre-auth to HTTP headers:

### Java EE/Jakarta Servlet container authentication

The servlet container can authenticate users via a configured realm before Spring processes the request. `J2eePreAuthenticatedProcessingFilter` obtains the principal from `HttpServletRequest.getUserPrincipal()`. `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` can use `isUserInRole(...)` and role mapping per configuration.

**Trust condition:** the servlet container itself must genuinely perform authentication, not a custom request wrapper reading `getUserPrincipal()` from raw user header input. Container roles do not automatically grant business tenant rights.

### X.509 client certificate

Spring Security supports X.509 authentication, where the TLS layer verifies the client certificate under mTLS. The principal is extracted according to configured rules from certificate fields. This requires certificate chain trust, revocation/lifetime checks, subject/issuer mapping, and proper client-auth policy. `X.509` is not equivalent to forwarding `X-Client-Cert` from the Internet into Spring and trusting its value: any certificate header must be protected/verified through the proxy trust contract.

### Agent/legacy SSO

SiteMinder or a web access management agent can attach the `SM_USER` header. `RequestHeaderAuthenticationFilter` documentation still keeps `SM_USER` as its **default header name**, yet **being the default does not make it safe**. You must be certain the agent is the only source capable of supplying that header.

## 21. Assessing "pre-auth": bypass or defense-in-depth?

In essence, pre-auth **moves the identity verification boundary** from the backend to a trusted upstream. That can strengthen security when the gateway enforces centralized SSO/MFA, isolates secrets/tokens, and passes minimal identity to the backend. However, it also creates a **centralized failure mode**: a single header sanitization bug, bypass path, or gateway compromise can affect all applications behind it.

### Recommended additional defenses

1. **Network identity:** verify workload/proxy identity, mTLS, no public backend exposure.
2. **Cryptographic identity attestation:** signed assertions when independent hop protection or intermediary mitigation is needed.
3. **App-local entitlement checks:** active/locked user state, roles, tenant object ACLs.
4. **Header contract versioning:** names, encoding, max length, duplicates, issuer namespace, freshness.
5. **Observability:** metrics for missing headers, unapproved users, denied roles, gateway errors.
6. **Revocation:** gateway logout and app sessions/caches synchronized within SLA.
7. **Security testing:** direct backend access, spoofed roles, header collisions, alternate ingress.
8. **Operational ownership:** who owns incidents when the gateway is down, a user is offboarded, or policies change.
9. **Fallback discipline:** no "open route" when the gateway fails; any OIDC fallback must be explicitly designed.
10. **Incident response:** revoke sessions/tokens, audit bypassed endpoints, fix security groups/ingress.

### Avoiding the "add a secret check header" trap

Some systems add `X-Shared-Secret: fixed-value` and treat it as proof of a trusted gateway. A static secret in an HTTP header can leak through logs/sidecars, be copied/replayed, lacks binding to a user/session, and is hard to rotate. **Do not treat a shared-secret header as a substitute for mTLS or short-lived signed identity assertions** when the threat model requires protection against spoofing/replay.

## 22. Step-by-step production rollout process

1. **Define the gateway's authority**: how the gateway authenticates users (OIDC, SAML, Kerberos, session) and who operates it.
2. **Map the network paths**: browser→gateway, ingress/sidecar→backend, all ports, and every potential bypass path.
3. **Choose the signals**: stable subject + trusted issuer + tenant (if needed), without passing raw passwords/tokens.
4. **Define the sanitization contract**: drop/overwrite identity headers; never let the client decide the trusted user.
5. **Establish backend isolation**: firewalls, security groups, NetworkPolicy, mTLS workload identity.
6. **Configure Spring pre-auth**: header filter + provider + user details + explicit authorization.
7. **Analyze sessions**: stateless per-request vs Spring session, logout, principal switching, revocation.
8. **Separate authentication chains**: isolate proxy-only paths from resource server/OIDC/API/health where appropriate.
9. **Integration testing**: real gateway, real lab users, local roles, tenant object ownership.
10. **Run negative tests**: direct/duplicate spoofed headers, issuer/tenant mismatches, gateway down, disabled user.
11. **Monitor drift**: gateway/pod configs, header contract, RBAC, and TLS certificates.
12. **Operational runbooks**: dashboards, alerts, incident playbook, rollback when changing ingress/auth policies.

**Do not ship to production until direct backend tests with forged headers are rejected**. That is the single most important negative test for a header-based pre-auth deployment.

## 23. Self-check questions and answers

### Case A — where did the request header come from?

The browser sends `X-Verified-Subject: admin` to the gateway, and the gateway forwards it unchanged.

**Answer:** **Header spoofing** vulnerability. The gateway must strip/overwrite it and the backend must accept only the protected hop. Spring's `RequestHeaderAuthenticationFilter` cannot tell a user's header from a proxy's header if both look identical.

### Case B — are roles from the gateway unconditionally trustworthy?

The gateway sends `X-Verified-Groups: ADMIN`; the user has not been approved in the tenant.

**Answer:** No. The app must enforce local role/tenant policy; if proxy group claims are used, a reviewed contract is required. Never blindly map `ADMIN` to `ROLE_ADMIN` across every app.

### Case C — is gateway logout sufficient?

The user logs out of the IdP, yet the browser still holds Spring's `JSESSIONID` and the backend uses the old SecurityContext.

**Answer:** Not sufficient. Design for **stateless per-request** processing or coordinate session expiration/invalidation/revalidation with the gateway. Login/logout/session state must be analyzed separately.

### Case D — does HTTPS on requests mean the gateway is trusted?

The backend uses HTTPS but allows any workload to connect and accepts arbitrary identity headers.

**Answer:** Not yet. Server-side HTTPS typically authenticates only the server to the client; the backend needs to **authenticate/restrict the gateway identity** (mTLS/client cert/network policy/signed assertion) and sanitize headers.

### Case E — same name alice across two IdPs

`alice` from issuer A and `alice` from issuer B.

**Answer:** Never auto-merge. Use `(trustedIssuer, subject)` to link to `localUserId`, preserve tenant boundaries, and only perform account linking through a verified process.

### Case F — proxy login succeeded but Spring returns 403?

**Answer:** This may be proper authorization. Spring may have received a valid principal while the user lacks the local role/entitlement for the resource. Never fix this with `permitAll()`.

### Case G — which mechanism should be used when the gateway sends a JWT?

**Answer:** If it is a genuine OAuth2 Access Token intended for the backend API, use Resource Server JWT validation with proper issuer, audience, and scopes; if it is a custom signed identity assertion, a corresponding verifier is required. Do not merely decode the token for `sub` and treat it as pre-authenticated.

### Case H — is setting `exceptionIfHeaderMissing=false` always safe?

**Answer:** No. It only allows the filter to continue when the header is missing; all protected routes must still require Authentication, with no permissive fallback or stale stateful session. Verify the chain and actual statuses with tests.

## 24. QA checklist before handoff

- [ ] Gateway authenticates users according to protocol and proper MFA/assurance policy.
- [ ] Proxy strips/overwrites **all** client-supplied identity headers.
- [ ] Spring backend has no direct/untrusted ingress, NodePort, or listener bypass.
- [ ] Gateway→backend has network isolation and appropriate service identity/mTLS.
- [ ] `RequestHeaderAuthenticationFilter` reads only headers attested via the trust contract.
- [ ] `PreAuthenticatedAuthenticationProvider` loads local UserDetails/authorities.
- [ ] Raw group/role headers are never used to grant ROLE_ADMIN.
- [ ] Stable subject and issuer namespace are mapped accurately to the local user.
- [ ] Disabled/unknown users are denied; JIT provisioning has a dedicated policy if enabled.
- [ ] Tenant/object-level authorization is enforced at each business operation.
- [ ] SecurityFilterChain for proxy-only paths is isolated from bearer/API/OIDC flows.
- [ ] Missing headers, gateway session failures, or auth provider failures all fail closed.
- [ ] `continueFilterChainOnUnsuccessfulAuthentication` and missing-header behavior are tested.
- [ ] Stateless/stateful sessions, logout, and identity switching are designed/tested.
- [ ] Reverse proxy `Forwarded`/`X-Forwarded-*` headers are never used as proof of user identity.
- [ ] Duplicate/ambiguous header values and header-size limits are tested.
- [ ] MFA/step-up claims are verified under a trusted assurance/freshness contract.
- [ ] Logs/metrics contain no raw tokens/cookies/PII while providing sufficient correlation/audit.
- [ ] No auth bypass exists via health/debug/alternate ingress or proxy config drift.
- [ ] Integration tests cover spoofed admin headers and direct backend denial.
- [ ] mTLS/secret/identity assertion rotation mechanisms have an owner and rollback plan.
- [ ] Spring Security/Boot/Jakarta Servlet versions and filter order have been verified.

## 25. Official references

1. [Spring Security — Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html): pre-auth concepts, principal, authorities, and framework classes.
2. [Spring Security — RequestHeaderAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html): default `SM_USER`, header reading, spoofing and missing-header warnings.
3. [Spring Security — AbstractPreAuthenticatedProcessingFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): auth lifecycle, principal change/session options, and fallback.
4. [Spring Security — PreAuthenticatedAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html): provider loading UserDetails and authorities.
5. [Spring Security — UserDetailsByNameServiceWrapper Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsByNameServiceWrapper.html): adapting an ordinary UserDetailsService into an AuthenticationUserDetailsService.
6. [Spring Security — PreAuthenticatedGrantedAuthoritiesUserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedGrantedAuthoritiesUserDetailsService.html): authorities from a trusted GrantedAuthoritiesContainer.
7. [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain, SecurityContext, multiple security chains, and request matchers.
8. [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext persistence, session policies, and logout.
9. [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): validating bearer access tokens instead of trusting raw subject headers when the architecture calls for it.
10. [Spring Boot — How-to: Embedded Web Servers and Forwarded Headers](https://docs.spring.io/spring-boot/how-to/webserver.html): forwarded headers strategy and reverse proxy considerations.
11. [OWASP — HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): headers belonging to different trust contexts, avoiding header security confusion.
12. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): reauthentication, session/context, and threat controls.
13. [MDN — X-Forwarded-For Security Considerations](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For): header source/trust boundaries and spoofing.
14. [Keycloak — Configuring Reverse Proxy](https://www.keycloak.org/server/reverseproxy): documented forwarded-header rewriting/spoof risks (for trust-boundary principles, not as a replacement guide for Spring).

**Key takeaway:** in pre-authentication, **the proxy/IdP authenticates the user; Spring still verifies the trustworthiness of the channel/identity source (via infrastructure or verifier), loads the principal and authorities, and then enforces authorization**. `RequestHeaderAuthenticationFilter` is merely an adapter; **a header has no inherent authentication value**. A single direct-backend path or a proxy bug that fails to strip headers can turn centralized SSO into forged logins. Verify trust boundaries, session lifecycles, local roles, and negative tests before considering a proxy SSO integration complete.