# Protecting Applications Behind an Authentication Gateway and Verifying Header-Spoofing Defenses

> **Module:** Spring Security – federation. **Group:** Comprehensive Practice. This Knowledge README builds an end-to-end scenario: a Spring Boot application running behind an **authentication gateway** (OIDC/SAML2/enterprise SSO) that must both accept properly verified identities and **reject forged HTTP identity/forwarding headers**. The exercise covers architecture, configuration, standalone runnable Java 17 examples, Spring Security API Resource Server, bounded pre-authentication options, NGINX/Cloud Gateway, a test matrix, observability guidance, and acceptance criteria.

## 1. Objectives and Security Conclusions

You will learn how to:
1. Define the **browser → gateway → application** boundary, separating end users from the gateway's own workload identity.
2. Distinguish **authentication at the gateway**, **authentication at the backend**, and **authorization at the resource**.
3. Choose between a **JWT access token or internal JWT verified by the backend itself** versus a **pre-authenticated identity header**.
4. Strip/overwrite all client-supplied `X-Authenticated-*`, `X-Remote-User`, `X-Forwarded-User`, `Forwarded`, and `X-Forwarded-*` headers.
5. Block direct backend access with network boundaries, firewalls/Kubernetes NetworkPolicy, and where needed mTLS/workload identity.
6. Enforce exact `iss`, `aud`, `exp`, `nbf`, `sub`, permission scopes, and identity/tenant linking.
7. Never turn a role string in an HTTP header into `ROLE_ADMIN`.
8. Verify OIDC `redirect_uri` callbacks, SAML Assertion Consumer Service, `Destination`, `Recipient`, and cookies when the gateway terminates HTTPS.
9. Write positive/negative tests proving forged identity headers, bearer tokens, or forwarding headers **do not** elevate privileges.
10. Operate the system with metrics, fail-closed behavior, key rotation, and release gates.

**Key takeaway:** **A successful login at the gateway does not mean the backend may trust any request header.** A header like `X-Authenticated-User: admin` is plain text that any client can send directly. Only when the gateway **strips client-supplied data**, authenticates the user, mints fresh identity evidence, and the backend **accepts traffic solely from trusted paths/gateways** can that data safely enter Spring Security.

## 2. Exercise Scenario: One SSO Portal, Two Resources

Sample application:
- Public gateway: `https://portal.example.test`.
- Private Spring Boot backend: `http://orders-api.private:8080`, reachable only from the gateway; in zero-trust environments, enforce mTLS between them.
- Test IdP: `https://identity.example.test`, supporting OIDC; can be swapped for a SAML2 IdP at the gateway without altering the backend's trust contract.
- API endpoint `GET /api/reports/{id}` requires `SCOPE_reports.read`.
- API endpoint `POST /api/reports/{id}/approve` requires an approved business privilege and tenant ownership.
- Test users: `alice-1001` with report-read access on `tenant-a`; `admin-test` with approve access per allowlist.
- Attacker tries sending `X-Authenticated-User: admin-test` or `X-Authenticated-Roles: ROLE_ADMIN` from the Internet.
- Network policy blocks attackers from calling `orders-api.private:8080` directly.
- IdP/Gateway supports key rotation, and logs record trace IDs without tokens or raw SAMLResponses.

### 2.1. Two Proof Layers That Must Stay Separate

**Gateway-to-backend authenticity:** the request genuinely came from an authorized gateway workload (network ACL/mTLS, never `X-Forwarded-For`).

**End-user identity proof:** the gateway verified the login and the backend receives **verifiable evidence** (a JWT) or an identity header **available only over a sufficiently secured pre-auth channel**.

An mTLS connection proves only that the **gateway workload** is calling the backend—it does not identify Alice. A valid JWT can prove the token was issued by the IdP/gateway for a specific audience; it does not check tenant ownership or account activation by itself. Both parts of the chain are required.

## 3. Recommended Architecture: Backend Verifies JWT

~~~text
           Browser / API client (UNTRUSTED)
                | HTTPS
                | may send forged identity headers
                v
        Public Gateway / Reverse Proxy
        -----------------------------------------
        Authenticates user via OIDC or SAML2
        Validates state/nonce/SAML signatures
        Sanitizes identity + forwarding headers
        Restricts public hosts, routes, redirects
        Sends approved access token to backend
                | private network or mTLS
                | Authorization: Bearer <signed access token>
                v
          Spring Security Resource Server
          -----------------------------------------
          Validates signed JWT via trusted issuer/JWKS
          Validates exp, nbf, iss, REQUIRED aud
          Maps only allowed scopes/permissions
          Authorizes URL, method, tenant, resource
          Ignores X-Authenticated-* for login
                |
                v
             Business resources
~~~

**Advantages:** the backend does not rely on `X-Authenticated-User` to build `Authentication`. If someone sends that header alongside a JWT issued for Alice, identity is established from the **validated token**; raw headers cannot swap the subject to Admin.

**Condition:** the gateway must actually receive an **access token meant for the backend API** with the matching audience. `TokenRelay` does not automatically guarantee the token targets the right audience; if the access token targets only the gateway or another API, use token exchange or have the gateway mint a proper internal JWT trusted by the backend under issuer policy. Never use an ID Token as an API access token.

### 3.1. Option B: Gateway Mints an Internal JWT

After authenticating via SAML2 or OIDC, an authorized token service at the gateway mints a **short-lived JWT with audience scoped to `orders-api`**:
- `iss`: identifier of the internal token issuer allowlisted by the backend.
- `sub`: stable identity linked from the IdP, never based on self-asserted email.
- `aud`: `orders-api`.
- `iat/nbf/exp`: short lifetimes with bounded clock skew.
- `scope`/permissions: approved per policy, never copying all raw groups.
- `jti`: token identifier supporting audit/revocation/replay policies when implemented.
- `kid`: select keys solely from the trusted issuer JWKS; never fetch arbitrary JWK URLs.
- `act`/actor claim when required by a token-exchange contract.

The gateway keeps its signing private key in KMS/HSM or a secret manager; the backend holds only issuer/JWKS public verification keys. Key rotation uses overlap and retirement. A validly signed JWT **never replaces local account/tenant checks**.

### 3.2. Option C: Conditionally Bounded Pre-Authenticated Header

Some legacy systems emit:
~~~http
X-Verified-Subject: alice-1001
X-Verified-Issuer: urn:example:trusted-idp
~~~

Spring offers `RequestHeaderAuthenticationFilter` and `PreAuthenticatedAuthenticationProvider` for pre-authentication; this is **wiring**, not proof that the header came from the gateway.

Accept this pattern only when **all** of the following hold:
- The gateway authenticates users with a trusted IdP.
- The edge strips inbound identity headers before authentication.
- The gateway reconstructs headers solely from a trusted auth session/result.
- Direct backend access is blocked even from unauthorized internal workloads.
- The backend verifies the real gateway workload via mTLS, approved upstream identity, or trusted network controls.
- Headers cannot arrive via an alternate ingress or service-mesh bypass path.
- The backend loads entitlements from an approved source and enforces policy by user+issuer+tenant.
- Missing, blank, or duplicate headers → fail closed.
- Never trust raw `X-Authenticated-Roles` as final permissions.
- Run header-spoofing regression tests after every proxy/ingress change.

**Recommendation for new systems:** prefer signed, audience-scoped tokens verified independently by the backend alongside network/mTLS controls over raw identity headers. Where legacy requirements mandate headers, maintain a threat model and gateway/network trust proof—not merely a custom servlet filter.

## 4. Header Classification: Metadata and Credentials Are Not the Same

| Header | Legitimate Purpose | Can It Automatically Establish Identity / Roles? |
|---|---|---|
| `X-Authenticated-User` | Legacy gateway forwarding verified identity | **No**, without a trusted gateway boundary |
| `X-Verified-Subject` | Canonical subject from a trusted auth service | Only across a verified pre-auth channel |
| `X-Remote-User`, `X-Forwarded-User` | Vendor-specific identity propagation | Never trust source implicitly |
| `X-Authenticated-Roles`, `X-Groups` | Legacy role hints | Never auto-grant `ROLE_ADMIN` |
| `Authorization: Bearer ...` | Access token credential | Backend must verify signature/claims/audience |
| `Cookie` | Browser session credential | Verified by gateway; never parsed as raw user header |
| `Forwarded` (RFC 7239) | Proxy hop info: `for/proto/host` | Not a credential |
| `X-Forwarded-For` | Effective client IP chain | Not identity proof; spoofable |
| `X-Forwarded-Host` | Public host | Must be canonical/allowlisted |
| `X-Forwarded-Proto` | Public HTTPS scheme | Must come from a trusted TLS terminator |
| `X-Forwarded-Port` | Public port | Never use raw to build redirect URIs |
| `X-Forwarded-Prefix` | Public path prefix | Requires approved routing |
| `X-Request-Id` | Correlation identifier | Creates no trust or authentication |
| `X-Tenant-Id` | Client request context | Must check tenant membership server-side |

**Distinction:** `X-Forwarded-For` can inform rate-limit analysis; it does not prove the user is Alice. `X-Tenant-Id` may indicate which tenant the caller asks for; it does not prove the caller belongs to that tenant.

### 4.1. Header-Spoofing Attack

An unauthenticated client sends:
~~~http
GET /api/reports/42 HTTP/1.1
Host: portal.example.test
X-Authenticated-User: admin-test
X-Authenticated-Roles: ROLE_ADMIN
X-Forwarded-For: 10.0.0.1
X-Forwarded-Proto: https
Forwarded: for=10.0.0.1;proto=https;host=internal.example.test
~~~

If the gateway passes headers through verbatim and the backend contains code like:
~~~java
String username = request.getHeader("X-Authenticated-User");
// Anti-pattern: treating this raw value as an authenticated user.
~~~

then an attacker can impersonate Admin. Once the proxy **strips/overwrites** those headers and the backend enforces signed-token validation and an mTLS boundary, the attack fails.

### 4.2. Variants That Remain Dangerous

- Case-insensitivity: `x-authenticated-user` vs. `X-Authenticated-User`.
- Duplicates: two lines of the same header—parsers vary in picking first, last, or merging.
- Underscore vs. hyphen normalization across proxies and application servers.
- `Connection` header listing hop-by-hop names mishandled by a proxy.
- HTTP/2-to-HTTP/1 translation with duplicate or invalid pseudo-headers.
- Multi-hop proxies retaining `Forwarded` even after stripping `X-Forwarded-Host`.
- Proxy `$proxy_add_x_forwarded_for` appending onto a forged client chain.
- Requests hitting the backend via an internal Service/Pod, bypassing the edge gateway.
- Headers containing CR/LF/control characters or oversized values causing parser confusion.

**Reject or normalize at the gateway rather than patching individual controllers with ad-hoc checks.**

## 5. Minimal STRIDE Threat Model

| Threat | Scenario | Security Property |
|---|---|---|
| Spoofing | Forged `X-Authenticated-User` | Identity comes solely from verified token/gateway |
| Tampering | Client alters `X-Groups` to Admin | Approved entitlements never come from client |
| Repudiation | Spoofed XFF alters audit IP | Normalized client IP from trusted chain |
| Information disclosure | Logging Bearer tokens / SAMLResponse | Redact raw credentials |
| Denial of service | Oversized/duplicate headers, invalid JWT floods | Size/rate/time limits |
| Elevation of privilege | Regular user injects `ROLE_ADMIN` | Resource/method/tenant authorization |
| Confused deputy | Gateway relays token meant for another audience | Validate `aud` / token exchange |
| Lateral movement | Another pod calls backend private port | NetworkPolicy / mTLS workload identity |
| Replay | Reusing a still-valid bearer token | Short TTL, revoke/jti policy for risky actions |
| Session mix-up | Same username across two issuers | Namespace by issuer+subject/tenant |

Checking `403` on a forged header is insufficient if the gateway returned 403 because the app was down rather than because security filters rejected it. Tests must prove **legitimate paths still work** and forged credentials create no authenticated principal or privileges.

## 6. Trust Sources: Who Proves What?

In an approved design:
- **Public TLS**: browser communicates with the gateway on the exact hostname.
- **OIDC/SAML2 at gateway**: gateway verifies trusted IdP keys, issuer, recipient/redirect URI, state/nonce/SAML conditions.
- **Gateway service identity**: mTLS SPIFFE/SVID or approved certificate/service identity trusted by the backend—never a client-supplied `X-Gateway-Id`.
- **JWT signature**: token signed by a trusted issuer with claims scoped for the backend; mTLS does not replace signatures.
- **Local authorization**: business service verifies account status, memberships, resource owner, and authorities.
- **Audit**: trace IDs and sanitized token metadata; never log credentials.

### 6.1. Authentication ≠ Authorization

Suppose Alice holds a valid JWT with scope `reports.read`:
- `GET /api/reports/42` may pass URL-level scope checks.
- Yet if report 42 belongs to `tenant-b` while Alice belongs only to `tenant-a`, **domain authorization must still deny**.
- `POST /api/reports/42/approve` must deny if `reports.approve` is missing, even though gateway login succeeded.

Never configure `anyRequest().authenticated()` as the entirety of security policy for sensitive resources; it covers only one layer.

### 6.2. Never Use IP Addresses as User Identity

`X-Forwarded-For` can be spoofed if the chain is mishandled by the gateway; NAT/CDN/VPNs also change client IPs. IP rate limiting is only one defense layer; principals must derive from verified subject/issuer, never IP addresses or `Host` headers.

## 7. Preparing the Lab Environment

Assumptions:
- Java 17+ and a compatible Spring Boot release.
- A test OIDC issuer or test SAML2 IdP serving the gateway.
- A sandbox JWT issuer/JWKS with at least two test subjects.
- Gateway/router controlling public host, TLS, and routing.
- Backend exposes no public listener; private network only.
- Test subjects:
  - Alice: `reports.read`, `tenant-a`.
  - Bob: lacks `reports.read`.
  - Approved admin: `reports.approve`, `tenant-a`.
- API contract:
  - `GET /api/reports/{id}` → requires `SCOPE_reports.read` and ownership.
  - `POST /api/reports/{id}/approve` → requires `SCOPE_reports.approve` and server-side approval policy.

**Never use production accounts, refresh tokens, or signing keys in the lab.** Use synthetic users and test keys controlled by the sandbox signer; never commit private keys or place bearer tokens in CI artifacts.

### 7.1. Data-Origin Flow Diagram

~~~text
IdP trusted subject/issuer
        |
        v
Gateway OIDC/SAML authentication
        |
        +-- Verify login + session
        |
        +-- Access token (aud=orders-api), or controlled token exchange
        |
        v
Backend JwtDecoder (public JWK, iss, aud, exp, nbf)
        |
        v
JwtAuthenticationToken with approved SCOPE_ authorities
        |
        v
Local user lookup (issuer + sub)
        |
        v
Tenant/report policy + HTTP/method security
~~~

In the legacy pre-auth variant, `JwtDecoder` is replaced by a verified gateway workload channel and an approved local-user mapper. That path **must never trust raw header user constants**.

## 8. Configuring Spring Boot Resource Server: Primary Approach

In the `orders-api` backend, use the Web/Security/OAuth2 Resource Server starters. Example Spring Boot Maven dependencies fragment:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

This is a fragment for a POM managed by the Spring Boot parent/BOM, **not a standalone buildable POM**. Spring Security / Spring Cloud Gateway versions must match your release train. Never pin OpenSAML/Nimbus dependencies outside the BOM without justification.

### 8.1. Specifying Trusted Issuer and Required Audience

Lab backend `application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://identity.example.test/issuer"
          audiences:
            - "orders-api"

logging:
  level:
    org.springframework.security: INFO
~~~

**Note:** this is a fictional lab issuer; replace it with a real sandbox identity service over trusted TLS/JWKS when running full integration tests. Spring Security Resource Server validates signatures against trusted JWKs, `iss`, `exp`, and `nbf`; `audiences` adds expected audience enforcement. Never accept an issuer/JWKS URL from an arbitrary JWT claim or request parameter.

If the gateway **mints an internal JWT**, set the issuer URI to the **internal token service's issuer**, not the upstream IdP, and verify subject/actor trust for token exchange. When a gateway relays an IdP access token, the backend must verify that the IdP actually issued the token for its audience.

### 8.2. Spring Security Servlet `SecurityFilterChain`

File `ApiSecurityConfig.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            // Only for an API using Bearer JWT, never browser cookies.
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(a -> a
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports/*/approve")
                    .hasAuthority("SCOPE_reports.approve")
                .anyRequest().denyAll())
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(a -> a.anyRequest().denyAll())
            .build();
    }
}
~~~

**CSRF warning:** `csrf(AbstractHttpConfigurer::disable)` on the **dedicated `/api/**` chain** is meant strictly for stateless APIs accepting only `Authorization: Bearer`, with no session cookies or browser auto-submitted credentials. If the backend also serves cookie auth, forms, or mixed SSO, **never copy that line**; configure CSRF protection per your threat model. HTTP matchers and path pattern syntax vary by Spring Security/Servlet version—verify with real tests.

**Matcher ordering note:** `GET /api/reports/**` and `POST /api/reports/*/approve` are URL-layer rules; tenant/owner checks must run at the service/method layer. Unknown API methods default to deny. If real routes include `/api/reports/list` or `/api/reports/42/export`, design explicit authorization rules.

### 8.3. JWT: Scopes Are Not Automatically Business Roles

Resource Server defaults map OAuth2 scopes to `SCOPE_*` authorities, e.g.:
~~~text
scope="reports.read" -> SCOPE_reports.read
scope="reports.approve" -> SCOPE_reports.approve
~~~

Never treat `OIDC_USER`, `SCOPE_profile`, or `X-Authenticated-Roles: ROLE_ADMIN` as report-approval permission. For a custom JWT `roles` claim, map only per approved issuer and role allowlist alongside local entitlement/tenant checks.

### 8.4. Adding Business Checks in the Service Layer

A business service can use `@PreAuthorize` to add scope and resource-owner checks:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public ReportDto viewReport(String reportId, String userId) {
    // Load report from trusted database.
    // Check that userId is allowed to access report's tenant.
    // Return only data authorized for this user.
    return reportRepository.loadAuthorized(reportId, userId);
}
~~~

This is a **Spring service fragment** lacking imports/domain types, so it is not standalone Java. In multi-tenant apps, `userId` must come from the validated `Authentication` + approved local identity link—**never trust a query parameter `userId` or `X-Tenant-Id`**. Enable `@EnableMethodSecurity` and verify the AOP proxy actually enforces the annotation. Repository queries must enforce tenant membership/ownership rather than filtering only in the frontend.

## 9. Accepting Identity Headers Only Through a Controlled Pre-Auth Gateway

Spring Security provides pre-authentication APIs for enterprise SSO systems:
- `RequestHeaderAuthenticationFilter` reads a principal from an HTTP request header.
- `PreAuthenticatedAuthenticationProvider` with `UserDetailsService` maps the principal to authorities.
- Container-authenticated user principals and X.509 auth are other pre-auth forms.

**The framework does not itself prove a request header came from a trusted gateway.** Configuration like:
~~~java
// Unsafe as a complete security solution on its own:
RequestHeaderAuthenticationFilter filter =
        new RequestHeaderAuthenticationFilter();
filter.setPrincipalRequestHeader("X-Authenticated-User");
~~~

merely tells the filter which header to read—**it does not verify gateway identity**. If the backend accepts direct requests, an attacker sending `X-Authenticated-User: admin` impersonates Admin. Never deploy this fragment without an approved edge/network/mTLS trust boundary and `UserDetailsService` policy.

### 9.1. Minimum Requirements for Using Legacy Identity Headers

| Layer | Control | Verification |
|---|---|---|
| Public gateway | Login via validated OIDC/SAML2 | Invalid IdP signatures/nonces rejected |
| Header sanitization | Strip client-sent identity headers | Forged user/groups never reach app |
| Auth service | Emits only verified stable subjects | Anonymous requests carry no subject |
| Transport | Backend accepts only gateway workload | Direct pod/backend IP requests blocked |
| mTLS when required | Approved client certificate / service identity | Wrong gateway cert rejected |
| Spring pre-auth | No missing-principal fallback | Blank/duplicate headers fail |
| User lookup | Subject+issuer → approved local account | Unknown/inactive users fail |
| Authorization | Group/tenant/resource policy | No role escalation |
| Observability | Safe trace and denial reasons | No session/token leaks |

### 9.2. Gateway-Derived Subject vs. Browser-Supplied Subject

If a browser sends `X-Verified-Subject: admin-test`, the gateway must **strip** it before querying the auth service and setting the fresh header. Fresh values come from:
- Verified OIDC session `iss+sub`.
- Verified SAML2 Assertion `NameID`/persistent attribute + IdP issuer.
- An enterprise identity broker that verified a ticket/token.
- An approved local user-mapping service.

**Never treat a browser-supplied value** as trusted merely because the gateway renamed the header to `X-Verified-Subject`.

### 9.3. Pre-Auth Does Not Automatically Determine Permissions

A header holding only a username without a verified entitlement contract says nothing about granted permissions. Spring can load authorities via `UserDetailsService` or an approved directory/DB. If a header carries groups, bind them to the gateway identity proof and an allowlist mapping; never copy `X-Roles: ADMIN` straight into `ROLE_ADMIN`.

## 10. Edge NGINX: Stripping Forged Headers Before Setting Internal Headers

This example targets a topology where **NGINX directly terminates public TLS**, checks authentication via an internal auth service, and forwards to a private backend. Replace the auth-service path and response header with your **auth provider's tested/deployed protocol**—never assume NGINX validates OIDC tokens by itself.

~~~nginx
server {
    listen 443 ssl;
    server_name portal.example.test;

    ssl_certificate     /etc/nginx/tls/public.crt;
    ssl_certificate_key /etc/nginx/tls/public.key;

    location = /_auth {
        internal;

        proxy_pass http://auth-service.private:9000/check;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";

        proxy_set_header Host auth-service.private;
        proxy_set_header X-Original-URI $request_uri;

        # Avoid sending a client-supplied identity marker to auth service.
        proxy_set_header X-Verified-Subject "";
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Authenticated-Roles "";
    }

    location / {
        auth_request /_auth;
        auth_request_set $verified_subject
            $upstream_http_x_verified_subject;

        proxy_pass http://orders-api.private:8080;

        # Backend must never see client-injected identity headers.
        proxy_set_header X-Verified-Subject $verified_subject;
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Authenticated-Roles "";
        proxy_set_header X-Remote-User "";
        proxy_set_header X-Forwarded-User "";
        proxy_set_header X-Groups "";

        # Fixed approved public origin; no raw $http_host.
        proxy_set_header Host portal.example.test;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host portal.example.test;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Prefix "";

        # Header pre-auth variant: do not relay client Bearer token.
        proxy_set_header Authorization "";
    }
}
~~~

**This configuration illustrates the legacy pre-auth variant**, **not** the JWT relay pattern from section 8. For the JWT route, the gateway must pass `Authorization: Bearer <approved access token>` from an authenticated token service with the backend's audience. Never forward the browser's `Authorization` untouched when policy requires gateway token issuance/exchange.

**Conditions for this example to be safe:**
- NGINX's public TLS listener accepts only approved hostnames; unknown Host/SNI must be rejected.
- Auth service `/check` genuinely verifies the session/token and returns the verified subject header from internal state without echoing client headers.
- `auth_request` denies or redirects anonymous callers per documented error flow; never auto-authenticate when the auth service is down.
- NGINX and `auth-service` are reachable only inside the approved network; auth subrequests carry proper session cookies/tokens per contract.
- NGINX's backend upstream reaches only the private service; firewall/Kubernetes policies prevent gateway bypass.
- `$remote_addr` is the true client peer **only when NGINX is the public edge TLS terminator**; behind a CDN/LB, verify trusted upstream real-IP config and hop handling.
- NGINX handles default hop-by-hop headers per module, yet you must audit vendor-specific identity/forwarded headers, duplicates, and upstream proxies.
- The pre-auth path needs gateway-to-backend service identity, ideally mTLS; the NGINX snippet does not configure mTLS itself.
- **Never use this `X-Verified-Subject` as a principal without the entire trust boundary described above.**

### 10.1. Separating Header Sanitization from Auth Service Decisions

Proper flow:
~~~text
Client untrusted headers
     |
     v
Gateway rejects unknown Host / malformed request
     |
     v
Remove all inbound identity/forwarding markers
     |
     v
Authenticate via trusted auth service / IdP
     |
     v
Derive canonical verified subject (not raw input)
     |
     v
Attach internal identity data or backend token
     |
     v
Private authenticated connection to backend
~~~

An NGINX line like `proxy_set_header X-Verified-Subject $http_x_verified_subject;` is wrong because it merely **renames/copies** the client-supplied value. During reviews, search for all `$http_x_authenticated_*`, `$http_x_remote_user`, `$http_authorization`, and inbound variables treated as trusted identity.

### 10.2. Auth Service Availability

When the auth service times out or returns 5xx:
- The gateway must fail closed on protected routes.
- Never fall back to a last-known principal from a prior request.
- Never allow guest/anonymous access to protected resources.
- Alert on auth-dependency failures.
- Cache only authenticated decisions with explicit TTL/revocation policies tied to session/token, never keyed solely by URL or IP.

## 11. Spring Cloud Gateway: `TokenRelay` and Its Limitations

Spring Cloud Gateway provides a `TokenRelay` filter that retrieves the OAuth2 access token from an authenticated OAuth2 client and forwards it to a downstream service.

Config example for a Spring Cloud Gateway **Server WebFlux** release supporting this schema:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: "http://orders-api.private:8080"
              predicates:
                - Path=/api/reports/**
              filters:
                - TokenRelay=
~~~

This is a **route fragment**. It requires a matching Spring Cloud Gateway release/BOM, OAuth2 client configuration, authenticated user context, and authorized client service per docs. `TokenRelay=` does not mean the gateway minted a new access token with the right audience; if the relayed token is meant for the gateway while the backend requires `aud=orders-api`, the backend **must reject it**. When token exchange is needed, follow OAuth 2.0 Token Exchange supported by the IdP or use a dedicated internal issuer rather than rewriting headers.

### 11.1. Gateway Filter Config Alone Is Not a Trust Boundary

- Even when `TokenRelay` runs, strip client-injected identity headers.
- Route predicates do not replace backend `NetworkPolicy`.
- The API Resource Server still verifies JWT issuer, audience, signature, and `exp`/`nbf`.
- If the gateway also accepts Bearer tokens from clients, define explicit precedence: validate the client token first or use the authenticated session token—never mix up two principals.
- Sanitize CORS headers and HTTP forwarded metadata as well.
- Spring Cloud Gateway Server MVC and WebFlux use different classes and filter configs. Read your exact release docs instead of pasting WebFlux snippets into Servlet MVC.

### 11.2. When Not Relaying an Access Token

If the gateway logs users in via SAML2:
- The browser holds a gateway session after a verified XMLDSig Assertion.
- The gateway can mint an internal JWT with a trusted internal issuer/audience.
- The backend verifies that JWT and local entitlements.
- Never forward the raw `SAMLResponse` under `X-SAMLResponse` for the backend to parse casually.
- If the backend is genuinely an independent SAML SP, it needs its own `RelyingPartyRegistration`, trusted IdP signing cert, Audience/Recipient/Destination checks, and request context—do not confuse it with gateway SAML login.

## 12. Forwarded Headers: Public Origin Is Not a Principal

Spring Framework's `ForwardedHeaderFilter` / WebFlux `ForwardedHeaderTransformer` interprets public scheme/host/port behind a proxy, yet **does not verify header origin itself**. Per Spring docs, strip inbound `Forwarded` and `X-Forwarded-*` headers at the trust edge so the proxy sets fresh trusted values.

Spring Boot property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Enable only when:
- The backend cannot be called directly bypassing the gateway.
- The gateway sanitizes incoming `Forwarded` and `X-Forwarded-*` headers.
- The public origin is approved.
- No double handling occurs between a container valve and the framework filter.
- Your Servlet/WebFlux framework version behaves as expected.

Without a trusted proxy boundary, use `none`/`removeOnly` or statically configured canonical URLs instead of trusting request-controlled `X-Forwarded-Host`.

### 12.1. Host Spoofing Impacts Federation Callbacks

OIDC:
~~~text
Expected redirect_uri:
https://portal.example.test/login/oauth2/code/staff
~~~

Attacker sends:
~~~http
X-Forwarded-Host: attacker.invalid
X-Forwarded-Proto: https
~~~

If the framework trusts this header, it can emit wrong redirect URIs or absolute links. The IdP may block it via exact registered redirect URI checks; **never rely on IdP rejection as proof your proxy is safe**. The gateway must enforce a canonical host, and the backend/`ClientRegistration` must never trust arbitrary hosts.

SAML2:
~~~text
Expected ACS:
https://portal.example.test/login/saml2/sso/staff
~~~

SP metadata, `Response.Destination`, and `SubjectConfirmationData.Recipient` must stay consistent with the public ACS. Never disable checks on scheme/host mismatches; fix trusted forwarding and canonical URLs.

### 12.2. `X-Forwarded-For` and Spoofed IPs

An attacker sends:
~~~http
X-Forwarded-For: 127.0.0.1
~~~

If the gateway simply appends the observed peer IP:
~~~http
X-Forwarded-For: 127.0.0.1, 198.51.100.42
~~~

then the first entry can be forged. Trusted-chain resolution must start from the **raw socket peer** and walk trusted hops right-to-left, never blindly picking `split(",")[0]`. Proxy IP allowlists must be exact rather than trusting entire private IP ranges. Even with the real effective IP, never treat an IP as an authenticated user identity.

## 13. Standalone Java 17: Seeing Why Trusting Headers Fails

`GatewayHeaderBoundaryDemo.java` runs standalone on JDK 17. It simulates:
- A browser able to send forged identity headers.
- A gateway holding a **trusted session identity** after auth-service verification (modeled with server-side data, never from request headers).
- The gateway constructing a fresh `InternalRequest` containing only the verified subject and workload connection identity.
- The backend rejecting unknown direct peers or headers lacking a verified subject.
- Business roles resolved via a server-side allowlist rather than `X-Authenticated-Roles`.

~~~java
import java.util.Map;
import java.util.Set;

public class GatewayHeaderBoundaryDemo {

    record BrowserRequest(
            Map<String, String> clientHeaders,
            String verifiedSessionSubject) {
    }

    record InternalRequest(
            String workloadPeerIdentity,
            String verifiedSubject) {
    }

    static InternalRequest routeThroughTrustedGateway(
            BrowserRequest browser) {

        // The verifiedSessionSubject is a SERVER-SIDE result
        // of OIDC/SAML authentication, never an HTTP input.
        return new InternalRequest(
                "spiffe://lab/gateway",
                browser.verifiedSessionSubject());
    }

    static String backendDecision(InternalRequest request) {
        if (!"spiffe://lab/gateway".equals(
                request.workloadPeerIdentity())) {
            return "DENY_UNTRUSTED_GATEWAY";
        }

        String subject = request.verifiedSubject();
        if (subject == null || subject.isBlank()) {
            return "DENY_NO_AUTHENTICATED_SUBJECT";
        }

        Map<String, Set<String>> approvedRoles = Map.of(
                "alice-1001", Set.of("ROLE_REPORT_VIEW"),
                "admin-test", Set.of(
                        "ROLE_REPORT_VIEW", "ROLE_REPORT_APPROVE"));

        Set<String> roles = approvedRoles.get(subject);
        if (roles == null) {
            return "DENY_UNKNOWN_LOCAL_USER";
        }

        if (roles.contains("ROLE_REPORT_APPROVE")) {
            return "ALLOW_APPROVE:" + subject;
        }
        return "ALLOW_VIEW:" + subject;
    }

    public static void main(String[] args) {
        BrowserRequest anonymousAttacker = new BrowserRequest(
                Map.of(
                        "X-Authenticated-User", "admin-test",
                        "X-Authenticated-Roles", "ROLE_ADMIN"),
                null);

        BrowserRequest aliceWithForgedRole = new BrowserRequest(
                Map.of(
                        "X-Authenticated-User", "admin-test",
                        "X-Authenticated-Roles", "ROLE_ADMIN"),
                "alice-1001");

        BrowserRequest approvedAdmin = new BrowserRequest(
                Map.of(), "admin-test");

        InternalRequest directAttacker =
                new InternalRequest(
                        "spiffe://lab/attacker",
                        "admin-test");

        System.out.println("spoofed-anonymous=" +
                backendDecision(routeThroughTrustedGateway(
                        anonymousAttacker)));
        System.out.println("spoofed-role=" +
                backendDecision(routeThroughTrustedGateway(
                        aliceWithForgedRole)));
        System.out.println("approved-admin=" +
                backendDecision(routeThroughTrustedGateway(
                        approvedAdmin)));
        System.out.println("direct-peer=" +
                backendDecision(directAttacker));
    }
}
~~~

Compile and run:

~~~bash
javac GatewayHeaderBoundaryDemo.java
java GatewayHeaderBoundaryDemo
~~~

**Exact stdout:**

~~~text
spoofed-anonymous=DENY_NO_AUTHENTICATED_SUBJECT
spoofed-role=ALLOW_VIEW:alice-1001
approved-admin=ALLOW_APPROVE:admin-test
direct-peer=DENY_UNTRUSTED_GATEWAY
~~~

**Explanation:**
- Attacker sends an Admin name without logging in; the gateway never turns headers into a verified session subject, so the backend denies.
- Alice is genuinely logged in yet sends forged roles; the backend uses only Alice's verified subject and server-side mapping, withholding approve rights.
- Approved Admin with valid entitlements is permitted to approve in the simplified model.
- Requests from any workload identity other than the gateway are rejected.

**Important limitations:** `verifiedSessionSubject` and `workloadPeerIdentity` are internal simulated values **that must never arrive from client JSON/headers**. The code performs no TLS/mTLS/SPIFFE verification, no OIDC/SAML validation, and no tenant/resource/expired-session checks. It is a **model of trust invariants**, not a production implementation. It does not prove a real HTTP proxy stripped headers; dedicated integration tests are required.

## 14. Standalone Java 17: Signing Internal Assertions Against Tampering and Wrong Audience

In an internal token model, public-key signatures let the backend verify message contents. Java 17 supports `Ed25519` in JCA; the demo below uses an **opaque canonical string** to illustrate signing and verifying `issuer/audience/time/jti`. **It is not JWT/JOSE/JWS and must never be used to invent a proprietary production authentication protocol.** Production should use standard OAuth2/JWT with audited libraries, proper claim normalization, and trust rules.

File `GatewayAssertionSignatureDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.util.HashSet;
import java.util.Set;

public class GatewayAssertionSignatureDemo {

    record Assertion(
            String issuer,
            String subject,
            String audience,
            long notBefore,
            long expires,
            String jti) {

        byte[] canonical() {
            String value = issuer + "|" + subject + "|" +
                    audience + "|" + notBefore + "|" +
                    expires + "|" + jti;
            return value.getBytes(StandardCharsets.UTF_8);
        }
    }

    static byte[] sign(Assertion a, KeyPair key) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(key.getPrivate());
        signer.update(a.canonical());
        return signer.sign();
    }

    static boolean signatureValid(
            Assertion a, byte[] signed, PublicKey trusted)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trusted);
        verifier.update(a.canonical());
        return verifier.verify(signed);
    }

    static String validate(
            Assertion a, byte[] signed, PublicKey trusted,
            long now, Set<String> seen) throws Exception {

        if (!signatureValid(a, signed, trusted)) {
            return "REJECT_SIGNATURE";
        }
        if (!"gateway-issuer-lab".equals(a.issuer())) {
            return "REJECT_ISSUER";
        }
        if (!"orders-api".equals(a.audience())) {
            return "REJECT_AUDIENCE";
        }
        if (now < a.notBefore() || now >= a.expires()) {
            return "REJECT_TIME";
        }
        if (!seen.add(a.jti())) {
            return "REJECT_REPLAY";
        }
        return "ACCEPT:" + a.subject();
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair gatewayKey = generator.generateKeyPair();
        KeyPair attackerKey = generator.generateKeyPair();

        long now = 1_800_000_000L;
        Assertion valid = new Assertion(
                "gateway-issuer-lab", "alice-1001",
                "orders-api", now - 10, now + 60, "id-001");

        byte[] trustedSig = sign(valid, gatewayKey);
        Set<String> seen = new HashSet<>();

        System.out.println("valid=" + validate(
                valid, trustedSig, gatewayKey.getPublic(),
                now, seen));
        System.out.println("replay=" + validate(
                valid, trustedSig, gatewayKey.getPublic(),
                now, seen));

        Assertion altered = new Assertion(
                valid.issuer(), "admin-test",
                valid.audience(), valid.notBefore(),
                valid.expires(), "id-002");
        System.out.println("tampered=" + validate(
                altered, trustedSig, gatewayKey.getPublic(),
                now, new HashSet<>()));

        Assertion wrongAudience = new Assertion(
                "gateway-issuer-lab", "alice-1001",
                "other-api", now - 10, now + 60, "id-003");
        System.out.println("audience=" + validate(
                wrongAudience, sign(wrongAudience, gatewayKey),
                gatewayKey.getPublic(), now, new HashSet<>()));

        Assertion expired = new Assertion(
                "gateway-issuer-lab", "alice-1001",
                "orders-api", now - 100, now - 1, "id-004");
        System.out.println("expired=" + validate(
                expired, sign(expired, gatewayKey),
                gatewayKey.getPublic(), now, new HashSet<>()));

        System.out.println("wrong-signer=" + validate(
                valid, sign(valid, attackerKey),
                gatewayKey.getPublic(), now, new HashSet<>()));
    }
}
~~~

Run:

~~~bash
javac GatewayAssertionSignatureDemo.java
java GatewayAssertionSignatureDemo
~~~

**Exact stdout:**

~~~text
valid=ACCEPT:alice-1001
replay=REJECT_REPLAY
tampered=REJECT_SIGNATURE
audience=REJECT_AUDIENCE
expired=REJECT_TIME
wrong-signer=REJECT_SIGNATURE
~~~

**Limitations:**
- `canonical()` uses a custom text delimiter that **risks ambiguity/injection** if inputs contain `|`. Thus it is **strictly an Ed25519 exercise**, not a production token format.
- Production JWTs require JOSE canonical serialization, algorithm/key validation, exact issuer/audience checks, timestamp claims, and audited signed-payload libraries.
- Never use an in-memory `HashSet` as a distributed replay cache. Bearer JWTs are replayable within their validity window by design; `jti` alone does not prevent replay without shared state/cache or DPoP/mTLS-bound tokens.
- Fixed `now` keeps stdout reproducible, not a wall clock for production token verification.
- Private keys are generated randomly and held only by the gateway in the model; the backend needs a trusted public key, never reading it from an unverified JWT header `jwk`/`jku`.
- Checking audience/time after signature ensures `wrongAudience` has a valid signature yet is rejected by policy, whereas mutating the payload post-signing to `admin-test` fails signature checks.

## 15. When Is Network Trust Enough, and When Is mTLS Needed?

In simple setups, Security Groups / firewalls / `NetworkPolicy` restricting backend ingress to gateway IPs or Pod labels shrinks the attack surface. However:
- Pod labels can be abused if RBAC lets another workload deploy with the same label.
- Pod IPs change; entire cluster CIDRs are overly broad.
- Service mesh sidecars introduce extra hops needing distinct identity.
- An internal network does not stop lateral movement from a compromised workload.

Therefore, sensitive systems should combine:
1. **mTLS between gateway and backend** with a verified gateway client certificate / workload identity.
2. Governed SPIFFE IDs, service identities, or managed certificate subjects/extensions.
3. Network ACLs as defense in depth.
4. Backend-verified JWTs separating end-user identity from the gateway workload identity.

**Never trust browser-sent `X-Gateway-Authenticated: true` or `X-Client-Cert: ...` as proof.** If a TLS-terminating gateway passes mTLS client-cert metadata in an HTTP header, enforce a strict translation contract, header stripping, and source authentication—otherwise attackers forge it.

### 15.1. Direct Backend Bypass Test

A test must prove that a request from a workload outside the trusted gateway principal/network fails:
~~~text
untrusted-pod -> orders-api.private:8080
Expected: network connection denied OR mTLS handshake denied
~~~

Receiving HTTP 401 from the backend shows JWT validation still protects users, yet **the "backend accepts gateway traffic only" requirement failed**. Test network and application layers separately.

## 16. Role Mapping and Tenant Separation

A valid JWT might contain:
~~~json
{
  "iss": "https://identity.example.test/issuer",
  "sub": "alice-1001",
  "aud": ["orders-api"],
  "scope": "reports.read",
  "tenant": "tenant-a"
}
~~~

This is an **illustrative payload**, not a real JWT (it has no header/signature). Spring `JwtDecoder` must verify first before any claims are read. Claim `tenant` may express session context, yet must be checked against local memberships; a user authorized for `tenant-a` must never read `tenant-b` reports simply by changing the URL.

### 16.1. Allowlist Principles

- `reports.read` → `SCOPE_reports.read` when the JWT comes from an approved issuer with the right audience.
- `reports.approve` → `SCOPE_reports.approve` only when issued per policy and the account still holds sufficient privileges.
- `ROLE_REPORT_ADMIN` is granted solely from approved server-side entitlements, never from browser `X-Roles`.
- `iss + sub` forms the OIDC identity namespace; never auto-merge by email.
- With a SAML2 gateway, `IdP entityID + stable NameID/qualifier` or an approved persistent identifier maps to the local account.
- Never trust `X-Tenant-Id` implicitly; requested tenant must match an authorized tenant.
- Logging in at the gateway does not automatically grant `ROLE_ADMIN` on the backend.

### 16.2. Distinguishing HTTP Policy from Domain Policy

HTTP:
~~~text
GET /api/reports/42
Required: SCOPE_reports.read
JWT: valid, has SCOPE_reports.read
=> HTTP authorization may pass
~~~

Domain:
~~~text
Report 42 tenant = tenant-b
Alice approved tenant = tenant-a
=> Domain check denies even if HTTP scope passes
~~~

Test both separately. If an API checks only JWT signatures and omits resource authorization, the gateway can inadvertently become a "confused deputy" acting on another tenant's data.

## 17. Header-Spoofing Tests: Lab Execution Guide

In an authorized lab environment, prepare:
- Public gateway URL.
- Private backend address.
- Test identities/tokens from the sandbox issuer.
- Browser session cookie plus separate valid/invalid test JWTs.
- A/B identities, roles, and tenant resources.
- Access to sanitized gateway logs and backend audit events by trace ID.

### 17.1. Unauthenticated Request Forging Admin

~~~bash
curl -i \
  -H 'X-Authenticated-User: admin-test' \
  -H 'X-Authenticated-Roles: ROLE_ADMIN' \
  -H 'X-Verified-Subject: admin-test' \
  https://portal.example.test/api/reports/42
~~~

Expected:
- If the gateway uses browser SSO: redirects to the IdP or rejects/challenges.
- If the gateway is a bearer API: 401/403 per chain.
- **No** authenticated Admin backend principal and no sensitive report returned.
- If the request reaches the app, sanitized logs confirm the forged headers were stripped.
- Do not hardcode one status code across all gateways; **assert no privilege or granted resource**.

### 17.2. Authenticated Alice Forging Admin Roles

Inside an E2E test harness holding a **valid Alice session**, send:
~~~http
GET /api/reports/42 HTTP/1.1
Host: portal.example.test
Cookie: session-cookie-issued-to-Alice
X-Authenticated-User: admin-test
X-Authenticated-Roles: ROLE_ADMIN
X-Tenant-Id: tenant-b
~~~

This is an **illustrative HTTP shape**; the valid cookie must be issued by the sandbox gateway, never a literal string on a live network. Expected:
- Backend identity remains Alice.
- No `ROLE_ADMIN` elevation.
- Request for `tenant-b` is denied if Alice lacks membership.
- If Alice owns a `tenant-a` report, a valid GET still passes with the right token/route.

### 17.3. Direct-Backend Spoof

From an **unauthorized** pod/test network:
~~~bash
curl -i \
  -H 'X-Verified-Subject: admin-test' \
  -H 'X-Authenticated-Roles: ROLE_ADMIN' \
  http://orders-api.private:8080/api/reports/42
~~~

Expected at network layer: connection blocked or mTLS denied. If the port is still reachable, backend JWT validation must reject requests lacking a Bearer token, yet **that is only defense in depth; fix the network boundary**.

### 17.4. Forged `Forwarded` / `X-Forwarded-*`

~~~bash
curl -i \
  -H 'Forwarded: for=127.0.0.1;proto=http;host=attacker.invalid' \
  -H 'X-Forwarded-For: 127.0.0.1' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Host: attacker.invalid' \
  -H 'X-Forwarded-Port: 8080' \
  https://portal.example.test/api/reports/42
~~~

Expected:
- Proxy rejects or reconstructs approved public metadata.
- Backend never treats fake `127.0.0.1` as an IP allowlist / rate-limit bypass.
- Redirects, links, and ACS never contain `attacker.invalid`.
- If virtual Host routing is invalid, the request fails closed.
- Forwarding metadata is never used as identity.

### 17.5. Duplicates and Case Variations

A thorough integration suite should test:
- `X-Authenticated-User: alice-1001` followed by a second line `X-Authenticated-User: admin-test`.
- Lowercase `x-authenticated-user` and mixed casing.
- `X_Authenticated_User` where gateways/containers normalize underscores.
- Both `Forwarded` and `X-Forwarded-Host` carrying conflicting hosts.
- `Connection: X-Authenticated-User` and hop-by-hop handling.
- Header values with commas, whitespace, Unicode, or control characters rejected by the parser.
- HTTP/2 requests across gateway → HTTP/1 backend.
- Abnormally long headers and counts exceeding header-size limits.

Expected: requests are rejected or normalized per policy without **ever creating an unapproved user or role**. Never rely on one library picking the first header while another picks the last.

## 18. Bearer Token Tests: Signed Tokens Can Still Be Rejected

| Case | JWT Signature | `iss` | `aud` | Time | Expected |
|---|---|---|---|---|---|
| Valid Alice | valid | approved | `orders-api` | valid | Authenticated + scopes mapped |
| Tampered payload | invalid | arbitrary | arbitrary | arbitrary | 401 / invalid token |
| Wrong issuer | valid under another issuer | wrong | `orders-api` | valid | Reject issuer/trust |
| Wrong audience | valid | approved | `another-api` | valid | Reject audience |
| Expired | valid | approved | `orders-api` | expired | Reject time |
| Future `nbf` | valid | approved | `orders-api` | not yet valid | Reject time |
| `alg` none/weak | unapproved | any | any | any | Reject algorithm |
| Unknown `kid` | no approved key | approved claim | `orders-api` | valid | Reject unknown signer |
| Client-supplied `jku` | untrusted URL | arbitrary | `orders-api` | valid | No arbitrary JWKS fetch |
| Missing required scope | valid | approved | `orders-api` | valid | 403 authorization |
| Approve scope yet wrong tenant | valid | approved | `orders-api` | valid | Domain deny |
| Relayed token meant for gateway | valid | approved | `gateway` | valid | Reject at `orders-api` |
| Revoked/expired user session | may still be cryptographically valid | approved | `orders-api` | valid | Apply revocation/recheck policy |
| Replayed bearer within TTL | valid | approved | `orders-api` | valid | Policy-dependent: bearer alone is replayable |

**Never claim a JWT prevents replay automatically just because it has `jti`.** Bearer JWTs are replayable within their lifetime by design; if proof-of-possession or a replay cache is required, implement and test DPoP, mTLS-bound tokens, or a JTI registry separately.

### 18.1. Verify Tokens at the Backend, Not from Gateway Logs

A gateway may log "authenticated Alice", yet the backend must still verify the token sent to it. Never accept a self-asserted JSON flag from gateway or client:
~~~json
{"authenticated":true,"role":"ADMIN"}
~~~

This is not JWT verification proof. Even with a verified gateway session, use audience-matched token relay or a protected pre-auth channel.

## 19. SAML2/OIDC at the Gateway: Do Not Confuse with Backend Authorization

### 19.1. OIDC

Gateway uses Authorization Code flow/PKCE per client policy:
1. Sends `AuthorizationRequest` with `state`/`nonce`.
2. IdP authenticates the user.
3. Gateway receives `code` at the registered redirect URI.
4. Gateway exchanges `code` for tokens and verifies ID Token issuer/audience/signature/nonce.
5. Gateway creates a user session.
6. Gateway relays the right access token or mints an internal JWT per contract.
7. Backend verifies the backend token, then runs local role/tenant authorization.

Never repurpose an ID Token as a backend access token unless protocol permits. Never let request headers choose issuer, client secret, or JWKS.

### 19.2. SAML2

Gateway acts as the SP facing the IdP:
1. `AuthnRequest` and request state are stored for SP-initiated flows.
2. IdP sends `SAMLResponse` to the exact gateway ACS.
3. Gateway verifies trusted XMLDSig, issuer, Audience, Destination, Recipient, Conditions, `InResponseTo`, and `SubjectConfirmation`.
4. Gateway builds a canonical user identity from the **validated Assertion**.
5. Gateway issues an internal token or secure pre-auth evidence.
6. Backend verifies internally and maps the approved local account and permissions.

Never Base64-decode a raw `SAMLResponse` and stuff `NameID` into `X-Authenticated-User` **before** the OpenSAML/Spring provider completes validation. Never verify signed Assertion A while reading attributes from unsigned Assertion B (XML Signature Wrapping).

### 19.3. CAS/Kerberos/LDAP

Enterprise gateways may validate CAS service tickets, Kerberos SPNEGO, or LDAP binds; success proves only an external principal within a realm/issuer scope. The backend still requires stable identity mapping and resource permissions—never accept HTTP `REMOTE_USER` from clients without pre-auth trust.

## 20. CSRF, CORS, Sessions, and Logout in a Gateway Model

### 20.1. Gateway Using Browser Cookies

When the gateway stores SSO sessions in cookies:
- Cookies must enforce `Secure`, `HttpOnly`, and flow-appropriate `SameSite`.
- Enforce CSRF protection for state-changing browser actions or equivalent design controls.
- Never disable OAuth2/OIDC `state`/`nonce` or SAML `InResponseTo` to work around login loops.
- Logout must invalidate the gateway session and any backend propagated state/tokens if policy includes revocation.
- Allowlist return URLs/`RelayState`; prevent open redirects.

### 20.2. Stateless Bearer Backend API

When the backend uses no cookies and accepts only Bearer tokens:
- No server-side browser session is needed to authenticate the API.
- Spring Security Resource Server filters verify the bearer token on every request.
- CSRF configuration may be narrowed on the dedicated API chain per threat model without disabling CSRF for browser endpoints.
- Handle CORS preflight properly and never grant API access to unapproved Origins.
- Session JWT audience/issuer must never depend on raw `X-Forwarded-Proto`.
- Separate revocation may be needed if tokens are stolen.

### 20.3. HTTP Errors Are Not One Fixed Code

- Anonymous browser → `302` to gateway IdP/login.
- Invalid/missing API Bearer token → typically `401`/challenge.
- Valid authentication lacking permission → typically `403`.
- Missing CSRF token on cookie-auth POST → may be `403`.
- `NetworkPolicy`/mTLS failure → request never reaches the app; no Spring HTTP status.
- Gateway WAF rejection → gateway returns `403` before the backend.

A strong QA suite checks the **exact layer** rather than comparing only HTTP 200/401/403.

## 21. Docker/Kubernetes Network Controls

### 21.1. Docker / Test Topology

A Compose lab can use two networks:
~~~text
public_net: browser/test client -> gateway (published TLS only)
private_net: gateway -> orders-api, auth-service, token-issuer
orders-api: no published ports on host
auth-service: no public ports
~~~

Never leave `ports: "8080:8080"` on a production backend when the goal is gateway-only ingress. In Docker Compose, omitting host port publishing is necessary yet insufficient without checking network attachments, host privileges, and access from peer containers.

### 21.2. Kubernetes `NetworkPolicy`

Design principles:
- Namespace `api` defaults to deny ingress for `orders-api`.
- Allow ingress to `orders-api` port 8080 only from Pods in the `gateway` namespace with approved labels.
- RBAC prevents arbitrary workloads from spoofing ingress labels.
- Gateway egress reaches only required auth/token/JWKS services.
- API service has no unexpected public `NodePort`/`LoadBalancer`.
- Service mesh mTLS policy requires the exact gateway principal.
- Health probes operate through an approved control plane without exposing the whole API.
- `NetworkPolicy` enforcement depends on the CNI, namespace labels, and actual traffic paths.

A skeletal Kubernetes policy illustrating the principle:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-api-only-gateway
  namespace: api
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: gateway
          podSelector:
            matchLabels:
              app: trusted-gateway
      ports:
        - protocol: TCP
          port: 8080
~~~

This is a **sample policy**: verify namespace labels, cluster CNI, ambient/service mesh, gateway Pods, and RBAC. A `NetworkPolicy` does not encrypt traffic or cryptographically verify the gateway workload; combine with mTLS where required.

## 22. Testing with Spring Security MockMvc

Test business authorization separately with `SecurityMockMvcRequestPostProcessors.jwt()`/`user()`:

~~~java
// Fragment in a Spring Boot JUnit/MockMvc test with matching routes.
mvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile"))))
    .andExpect(status().isForbidden());
~~~

**Prerequisites:** matching controller routes, imports, and approved test data where report 42 belongs to the mock principal's tenant. This tests **authorization**, not real signed JWT/JWKS `JwtDecoder` verification—the `jwt()` helper bypasses decoding and signatures. Therefore, add integration tests using **real signed JWTs** from a sandbox issuer pointing the backend to trusted test JWKS.

### 22.1. Testing Forged Headers with MockMvc

~~~java
// Fragment: verifies app ignores raw identity header under JWT policy.
mvc.perform(get("/api/reports/42")
        .header("X-Authenticated-User", "admin-test")
        .header("X-Authenticated-Roles", "ROLE_ADMIN"))
    .andExpect(status().isUnauthorized());
~~~

On a Bearer-only API chain, `401` is normally expected, though status varies by handler. What matters: raw headers **never** create an authenticated principal. This MockMvc test **does not** prove NGINX stripped headers or `NetworkPolicy` blocked direct backend access; test those through the real gateway.

### 22.2. Testing GET vs. POST Regarding CSRF

When browser sessions and cookies are active:
- GET may pass.
- POST without CSRF returns 403.
- POST with valid CSRF yet missing scope also returns 403, at the authorization layer.
- Never add `ROLE_ADMIN` to "fix" CSRF.
- On a dedicated stateless bearer API, align CSRF behavior with the reviewed threat model.

## 23. Real-World Verification CI Pipeline

~~~text
1. Build gateway/backend with pinned dependencies
2. Start isolated IdP or trusted test JWT issuer
3. Generate signing keypair only for test and publish public JWKS
4. Start private backend with issuer+audience validation
5. Start gateway with valid TLS and header sanitation
6. Assert gateway→backend path and direct-backend deny
7. Run authenticated Alice and approved Admin positive tests
8. Send forged identity/role/tenant headers
9. Send Forwarded/X-Forwarded-* spoof/duplicate variants
10. Send invalid/expired/wrong-audience JWTs
11. Run SAML/OIDC callback, session and logout tests
12. Assert principal/tenant/authority at backend without leaking tokens
13. Audit logs, traces and key handling
14. Publish sanitized JUnit reports; clean secrets and sessions
15. Fail release if privilege escalation or bypass is observed
~~~

### 23.1. CI Hardening

- Test keys must never match production keys.
- Never put private signing keys into repos, container layers, or public CI artifacts.
- Never log full JWTs, `Authorization` headers, cookies, `SAMLResponse`s, or ID Tokens.
- Restrict test issuers/JWKS and auth services to the private lab.
- Run E2E with synthetic identities only.
- Test that auth-service 5xx/timeouts fail closed without trusting cached anonymous headers.
- Feature flags must never disable signature validation in production.
- Release pipelines should diff/review gateway routes, NGINX headers, `NetworkPolicy`, and Spring `SecurityFilterChain` together in one change set.

## 24. Comprehensive Test Matrix

| ID | Test | Secure Expectation |
|---|---|---|
| G01 | Alice logs into gateway with valid OIDC | Gateway creates verified session |
| G02 | Alice SAML Response with trusted signature | Gateway extracts exact stable subject |
| G03 | Wrong SAML signature / Issuer / Audience | Gateway rejects login |
| G04 | Wrong OIDC nonce / state / PKCE | Gateway rejects login |
| G05 | Anonymous sends `X-Authenticated-User: Admin` | No Admin `Authentication` |
| G06 | Alice sends `X-Authenticated-Roles: ADMIN` | No role elevation |
| G07 | Client sends `X-Verified-Subject: admin-test` | Gateway ignores / replaces |
| G08 | Conflicting duplicate identity headers | Reject or sanitize; no admin |
| G09 | Mixed-case identity headers | No bypass |
| G10 | Underscore/hyphen header ambiguity | Reject / normalize |
| G11 | Client sends `Connection: X-Authenticated-User` | No proxy bypass |
| G12 | Oversized / malformed identity header | Bounded fail-closed |
| G13 | Direct backend connection from untrusted pod | Network denied |
| G14 | Wrong mTLS gateway identity | Handshake / access denied |
| G15 | Valid gateway mTLS with no user credential | API rejects user auth |
| G16 | Forged `X-Forwarded-Host: attacker.invalid` | Canonical host preserved |
| G17 | Forged `Forwarded` `proto=http` | Public HTTPS preserved |
| G18 | Forged `XFF=127.0.0.1` | No IP allowlist bypass |
| G19 | Conflicting `Forwarded`/`XFH` | Reject / normalize |
| G20 | Multi-hop trusted proxy chain | Accurate origin/IP interpretation |
| J01 | Signed JWT with valid `iss`/`aud`/`exp`/`nbf` | Backend authenticated |
| J02 | Invalid JWT signature | Reject |
| J03 | Wrong issuer | Reject |
| J04 | Wrong audience despite valid signature | Reject |
| J05 | Expired token | Reject |
| J06 | Future `nbf` | Reject |
| J07 | Unknown `kid` / external `jku` | Never accept untrusted keys |
| J08 | Valid Alice token + forged Admin headers | Identity stays Alice |
| J09 | Token meant only for gateway, not backend | Reject wrong audience |
| J10 | Valid token missing read scope | Deny read |
| J11 | Approved read scope, other tenant's resource | Domain deny |
| J12 | Approved approve scope, inactive local account | Deny |
| J13 | Rotated JWT signing key overlap | Accept only approved key phases |
| J14 | Revoked signing key | Reject after trust removal |
| J15 | Replayed bearer token | Handled per documented replay policy |
| S01 | SAML Destination/Recipient mismatch | Gateway rejects assertion |
| S02 | Signed SAML A with unsigned Assertion B | Never consume B attributes |
| S03 | IdP-initiated when disabled | Reject unsolicited login |
| S04 | SAML → internal JWT subject mapping | Exact issuer + stable subject |
| S05 | OIDC → internal JWT subject mapping | Exact `iss` + `sub` |
| B01 | Browser session cookie lost after redirect | No anonymous privilege |
| B02 | Missing browser CSRF on state-changing POST | Reject |
| B03 | CORS preflight blocked | Diagnose as CORS, not role |
| B04 | OAuth2 `redirect_uri` influenced by forged `Host` | No attacker redirect |
| B05 | Auth service unavailable | Protected routes fail closed |
| B06 | Gateway restart/rollout across pods | Sessions and trust preserved |
| B07 | Wrong tenant from URL/header | Domain deny |
| B08 | Logs expose raw token/private key | Security regression; block release |
| B09 | Header spoof tested only with MockMvc | Insufficient: gateway E2E required |
| B10 | Unknown API route/method | Deny by default |

**Evaluation criteria:** negative tests must prove **no authenticated Admin principal exists and no resource leaks**, not merely assert one HTTP status code. Suites must also include at least one allowed positive request so you do not mistake "everything is broken and returns 403" for working security.

## 25. Observability and Operations Plan

Categorize events by:
- Gateway login success/failure per OIDC/SAML2 registration.
- Gateway rejections of inbound identity headers.
- Gateway auth-service timeouts/unavailability.
- Direct-backend/mTLS unauthorized service identities.
- Backend invalid JWT signature/issuer/audience/time.
- Backend authorization denials due to scope/tenant.
- Proxy forwarded-header conflicts / invalid `Host`.
- Session cookie / callback correlation errors.
- Unexpected elevated authority grants.
- Key rotation / JWKS refresh and certificate changes.

### 25.1. Data-Safe Logging

Sanitized log sample:
~~~text
trace=gw-01 stage=gateway-auth result=SUCCESS protocol=OIDC
trace=api-02 stage=jwt-validation result=ACCEPT issuer=trusted-lab
trace=api-02 stage=authorization result=DENY reason=TENANT_MISMATCH
trace=gw-03 stage=header-sanitization result=DROP_UNTRUSTED_IDENTITY
trace=gw-04 stage=auth-service result=UNAVAILABLE action=FAIL_CLOSED
~~~

This is a suggested format, not automatic Spring output. **Never log raw `Authorization: Bearer`, `SAMLResponse`, session cookies, ID Tokens, private keys, or full claims.** Manage token fingerprints, trace IDs, and user pseudonyms per privacy policy. Avoid high-cardinality metric labels such as raw IPs, hosts, subjects, or XFF contents.

### 25.2. Metrics and Alerts

Recommended:
- `gateway_authn_success_total`.
- `gateway_authn_failure_total`.
- `identity_header_spoof_rejected_total`.
- `backend_invalid_jwt_total{reason}`.
- `backend_authz_denied_total{policy}`.
- `backend_mtls_rejected_total`.
- `gateway_auth_service_unavailable_total`.
- `proxy_header_conflict_total`.
- `unexpected_privileged_grants_total`.

These are **custom implementation metrics**, not framework defaults. Elevated 403 counts are normal during attacker probes; compare ratios against legitimate requests and alert on unexpected privileged access rather than chasing `403=0`.

## 26. Symptom-Based Troubleshooting

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Client-sent Admin header becomes Admin user | Gateway echoes client header | Strip/overwrite; fix auth-service contract |
| Pre-auth app reachable directly | Open backend port / `NetworkPolicy` | Block direct path and enforce mTLS |
| Valid JWT at gateway yet 401 at backend | Audience mismatch, wrong issuer/JWKS | Fix token exchange / issuer+aud config |
| JWT signature passes yet 403 at backend | Missing scope/tenant/role | Fix authz mapper / domain policy |
| OIDC login loop | Session/cookie/state/proxy mismatch | Check `SameSite`, `redirect_uri`, trusted origin |
| SAML Recipient mismatch | Wrong gateway public ACS URL | Fix `Forwarded`/metadata; never drop validator |
| Spoofed client IP logged as localhost | XFF parser trusts first hop | Normalize trusted chain |
| Service mesh bypass | Internal workload can call API | Enforce service identity and sidecar policy |
| Unknown `kid` still accepted | Broken dynamic JWK trust | Pin issuer and JWKS |
| Browser sends both Cookie and Bearer | Identity ambiguity | Define explicit precedence/policy and test |
| No JWT reaches backend after SAML login | Gateway did not mint/exchange token | Add internal token service |
| Forged header returns 403 from CSRF | Wrong auth layer checked | Add valid CSRF test to isolate authz |
| Proxy returns 403 with no backend logs | Gateway/WAF blocked request | Inspect gateway traces |
| One node sees different user/roles | Session/cache/config drift | Compare deployment revisions and key sets |
| Valid JWT issuer yet wrong tenant | Wrong local identity link | Enforce `issuer+sub` and membership check |
| Empty `X-Verified-Subject` yields anonymous | Pre-auth defaults not fail-closed | Require non-empty principal and reject |
| Valid SAML signature yet wrong user | Converter / XSW issue | Verify protected Assertion provenance |
| Production trusts test issuer | Misconfigured secrets/JWKS | Block release and rotate trust |
| CSRF accidentally disabled on browser routes | Mixed chain scope wrong | Separate stateless and browser chains |
| `TokenRelay` passes token meant for another API | Missing audience validation | Reject / use token exchange |
| Auth service down yet cached user persists | Faulty fallback/caching design | Fail closed / use revocation-aware cache |

## 27. Severe Anti-Patterns

1. Calling `request.getHeader("X-Authenticated-User")` and creating `Authentication` without verifying the gateway.
2. Granting roles from browser-sent `X-Authenticated-Roles` or `X-Groups`.
3. Leaving the backend public while assuming "the gateway handles all logins".
4. Treating `X-Forwarded-For: 127.0.0.1` as a local admin request.
5. Enabling `server.forward-headers-strategy: framework` while the backend remains directly reachable.
6. Stripping `X-Forwarded-Host` while ignoring standard `Forwarded`.
7. Proxy using raw `$http_x_authenticated_user` to populate a trusted subject header.
8. Proxy using `$proxy_add_x_forwarded_for` at the public edge without sanitizing client XFF.
9. Gateway `TokenRelay` without backend `aud` validation.
10. Using an OIDC ID Token as an OAuth2 access token to call APIs.
11. Trusting a JWT from its own `jku` or arbitrary issuer URL.
12. Granting `ROLE_ADMIN` when seeing `groups=["Admin"]` without an approved mapping.
13. Relying on HTTP `X-Tenant-Id` to establish tenant membership.
14. Disabling SAML signature/Recipient/Destination checks when a proxy changes hostnames.
15. Disabling OIDC `state`/`nonce` simply because cookies behind the gateway failed.
16. Disabling CSRF across all browser SSO routes just to make a POST pass.
17. Failing to guard against duplicate/mixed-case/underscore header ambiguity.
18. Treating mTLS gateway service identity as automatic end-user authentication.
19. Assuming a JWT's `jti` provides replay protection by itself.
20. Testing MockMvc with a mocked user and claiming E2E header-spoofing coverage.
21. Inventing custom text-signing header/token protocols in production.
22. Letting auth-service outages fall back to anonymous access on protected endpoints.
23. Printing raw tokens, SAML XML, or cookies into application logs.
24. Judging security solely by 401/403 responses without positive-path tests.
25. Deleting backend authorization because "the gateway already checked permissions".

## 28. Final Deployment Checklist

- [ ] Public gateway hostname/TLS/SNI are approved and unknown hosts are rejected.
- [ ] Gateway validates OIDC/SAML2/CAS/Kerberos per the trusted IdP contract.
- [ ] Gateway strips inbound identity headers at the edge before authentication.
- [ ] Gateway strips/normalizes inbound `Forwarded` and `X-Forwarded-*`.
- [ ] Duplicate, case, underscore, and hop-by-hop spoofing variants are tested.
- [ ] Backend has no public `NodePort`, `LoadBalancer`, or direct exposed port.
- [ ] Kubernetes/Docker/firewall allows only the trusted gateway workload.
- [ ] mTLS workload identity is enforced in environments requiring zero-trust.
- [ ] Choice between JWT/token exchange and legacy pre-auth headers is explicit, never mixed.
- [ ] For JWT: backend verifies signature, trusted issuer/JWKS, `aud`, `exp`, and `nbf`.
- [ ] For JWT: `TokenRelay` passes only tokens with backend audience or uses token exchange.
- [ ] For legacy headers: verified subject comes solely from the auth service, never the browser.
- [ ] For legacy headers: no missing-principal fallback and authorities are allowlisted.
- [ ] No homegrown internal tokens bypassing JOSE/JWT standards.
- [ ] Local identity namespace includes issuer/realm and stable subject.
- [ ] Scope/role mapping never auto-grants elevated privileges.
- [ ] Tenant/resource-owner policies execute on the backend.
- [ ] Public OIDC `redirect_uri` and SAML ACS/Destination/Recipient are accurate.
- [ ] Proxy forwarding never compromises authentication or tenant trust.
- [ ] CSRF/session/`SameSite` settings match browser vs. bearer architecture.
- [ ] Positive valid Alice and approved Admin tests pass.
- [ ] Anonymous and authenticated forged-role tests deny elevation.
- [ ] Direct backend bypass tests are denied at network/mTLS layers.
- [ ] Wrong issuer/aud/key/expiry JWT tests are denied.
- [ ] Full gateway E2E header-spoof/duplicate/`Forwarded` tests pass.
- [ ] Spring MockMvc tests are not used in place of real crypto/ingress tests.
- [ ] Key rotation/revocation policy and JWKS caching are tested.
- [ ] Auth-service timeouts/errors fail closed.
- [ ] Secrets/tokens never appear in source, logs, or artifacts.
- [ ] Owners, monitoring, incident playbooks, canary, and rollback are in place.
- [ ] No Spring Security validators were disabled just to make a test request pass.

## 29. Review Questions

1. **Does a successful login at the gateway guarantee the backend is secure?** No, if the backend trusts forged headers or skips authorization.
2. **Is `X-Authenticated-User` a credential?** No, it is plain text; it has pre-auth value only when a protected trust boundary guarantees its origin.
3. **What is the difference between mTLS gateway identity and JWT user identity?** mTLS proves the workload; a user JWT proves subject/issuer/audience and claims.
4. **Why strip headers before authentication?** So browser-supplied values are never mistaken for verified results.
5. **Can `X-Forwarded-For` be trusted to grant `ROLE_ADMIN`?** No.
6. **What must a JWT verify besides its signature?** Trusted issuer, audience, expiry/not-before, scope/policy, and subject.
7. **Does `TokenRelay` change a token's audience?** No.
8. **When is token exchange needed?** When the source token is not targeted to the backend resource.
9. **Can an OIDC ID Token act as an API access token?** Not by default; they serve different purposes and protocols.
10. **What does a SAML gateway verify before emitting a subject?** Signed Assertion/Response, issuer, audience, recipient/destination, conditions, and correlation.
11. **Is extracting SAML `NameID` from raw XML before validation dangerous?** Yes—identity spoofing / XSW risk.
12. **What if a user holds `reports.read` yet the report belongs to another tenant?** Domain authorization denies.
13. **What if a request carries a fake Admin header alongside Alice's JWT?** The backend must keep identity as Alice.
14. **What if the backend is called directly from another pod and returns 401?** JWT defense worked, yet the gateway-only network boundary failed.
15. **Can every private IP be trusted as a gateway?** No.
16. **Why test duplicate identity headers?** Proxies and servlet parsers may pick different occurrences.
17. **Does `ForwardedHeaderFilter` verify whether a proxy is trusted?** No.
18. **How do you protect the public origin?** Gateway strips/reconstructs forwarding metadata + exact host allowlist.
19. **Why not disable CSRF on every route?** Browser session/cookie flows still face CSRF risk.
20. **Does a JWT `jti` prevent replay by itself?** No; you need a replay cache/revocation or proof-of-possession policy.
21. **Should you design a custom text-signing protocol in production?** No; use standard JWT/JOSE with audited libraries.
22. **Does MockMvc `jwt()` verify real signatures?** No; it mocks the authorization context.
23. **What must end-to-end gateway tests prove?** Forged headers cannot change identity/roles and valid paths still succeed.
24. **Key metrics to track?** Spoof rejections, invalid-token reasons, authz denials, and gateway auth availability.
25. **What should happen when the auth service is down?** Fail closed.
26. **Across multiple IdPs, does a matching email mean the same user?** No; require an approved issuer+stable-subject link.
27. **What if a signed JWT has the wrong audience yet the right issuer?** Reject.
28. **Why does the backend need authz even when the gateway authenticated the user?** Resource/tenant permissions are not implied by login.
29. **What must be checked when the gateway replaces an ingress controller?** Header sanitization, network trust, callback origins, cookies, JWT/token exchange, and E2E regressions.
30. **Summary rule?** Never trust raw headers; verify both gateway origin and end-user evidence, and enforce backend resource policy.

## 30. References

- Spring Security – Pre-Authentication Scenarios: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- Spring Security – Servlet Architecture and SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security – OAuth2 Resource Server JWT (issuer, audience, scope): https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – HTTP Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – SAML2 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Framework – ForwardedHeaderFilter security considerations: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Boot – Reverse Proxy/Forward Headers: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Cloud Gateway – TokenRelay (WebFlux): https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html
- IETF RFC 7239 – Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
- IETF RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- IETF RFC 8693 – OAuth 2.0 Token Exchange: https://www.rfc-editor.org/rfc/rfc8693
- OWASP – Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Session Management: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP – HTTP Security Headers: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- NGINX – proxy_set_header: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- Kubernetes – Network Policies: https://kubernetes.io/docs/concepts/services-networking/network-policies/

**Summary:** Protecting a Spring Security application behind an authentication gateway is a **practice combining protocol authentication, network trust, header sanitization, backend token validation, and resource authorization**. Never create `Authentication` merely upon seeing `X-Authenticated-User` in an HTTP request. The preferred architecture has the gateway forward an **audience-matched access token/JWT** while the backend verifies signature, issuer, `exp`/`nbf`, and scopes, with `NetworkPolicy`/mTLS blocking gateway bypass; legacy pre-auth requires a controlled transport/workload identity and headers regenerated post-authentication. A system passes acceptance only when **valid users access their proper resources, forged headers never elevate privileges, direct backend traffic is blocked, invalid tokens are rejected, and no secrets leak into logs/CI**.
