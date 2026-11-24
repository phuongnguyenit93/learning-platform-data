# Testing Spoofed Headers and Authentication Gateway Bypass Access

**Module:** Spring Security – federation  
**Parent topic:** SSO Testing  
**Focus:** security testing of Single Sign-On (SSO) systems using an authentication gateway/reverse proxy, specifically spoofed identity headers and backend access paths bypassing the gateway.  
**Technologies:** HTTP/HTTPS, OIDC/SAML2 gateway, Nginx/ingress, Kubernetes/network policies, Spring Boot 3.x, Spring Security 6.x, Java 17+.

## 1. The Problem: Can a Single Fake Header Bypass SSO?

In a common architecture, the browser logs in via OIDC/SAML or another SSO mechanism at an **authentication gateway**. The gateway validates the session and forwards identity information to the backend in an internal HTTP header:

~~~text
Client / Browser
     |
     | Valid SSO Cookie or Authorization
     v
Public Edge / WAF
     |
     v
Authentication Gateway (verifies OIDC/SAML/session)
     |
     | X-Verified-Subject: account-42
     | X-Verified-Issuer: https://idp.example.test
     v
Internal Ingress / Reverse Proxy
     |
     v
Spring Security Backend
     | Pre-authentication: reads gateway-verified identity
     v
Local account / roles / resource authorization
~~~

In this setup, Spring Security may use **`RequestHeaderAuthenticationFilter`** to read the username from a header. According to Spring Security documentation, this filter **simply extracts the username from a request header and does not validate the header's origin**. If an attacker sends a request containing **`X-Verified-Subject: administrator`** straight to the backend, or if the gateway passes through client-supplied headers, Spring may mistake it for an authenticated identity.

There are **two distinct yet related test groups**:

1. **Public-path header spoofing:** an attacker supplies `X-Verified-Subject`, `X-Remote-User`, `SM_USER`, `X-Role`, `X-Forwarded-User`, etc., expecting the gateway to **strip/overwrite** them rather than forwarding them to the backend.
2. **Gateway bypass:** an attacker or another workload connects **directly to the backend, NodePort, secondary ingress, service mesh endpoint, or management route** without traversing the authentication gateway, then sends headers shaped like gateway output.

A gateway with perfect sanitization is **insufficient** if the backend has a bypass path. A backend accepting traffic solely from ingress is **also insufficient** if ingress forwards headers from callers not authenticated by the auth gateway.

### Learning Objectives

After this lesson, you will be able to:

- Identify **who is allowed to assert identity** versus who is only allowed to transport HTTP bytes.
- Diagram trust boundaries from browser to backend along with **alternate paths**.
- Design positive/negative tests using synthetic test accounts without impacting production.
- Distinguish **identity headers** from **`Forwarded`/`X-Forwarded-\*`** used for host, scheme, client IP, and routing.
- Prove spoofed headers and bypass requests **cannot create a Spring Security `Authentication`** or grant business permissions.
- Verify results across **gateway, backend, `SecurityContext`, and protected endpoints**, not merely HTTP status codes.
- Write a Java 17 example modeling fail-closed policy and understand MockMvc's limitations.

**Testing safety:** Run direct network tests only in **authorized staging/lab environments**, using test hostnames/IPs and synthetic users; never scan production IPs/NodePorts or attempt to impersonate real users.

## 2. Key Concept: Pre-Authentication Does Not Mean Self-Verification

Spring Security supports **pre-authentication** when an external component has already authenticated the user. Relevant components:

| Component | Function | What It Does Not Guarantee By Itself |
| --- | --- | --- |
| Authentication gateway | Verifies browser session, IdP token, or client certificate | Downstream headers cannot be forged unless trust controls exist |
| `RequestHeaderAuthenticationFilter` | Reads principal from a header like `X-Verified-Subject` | Does not verify signatures, issuers, gateway certs, or header authenticity |
| `PreAuthenticatedAuthenticationToken` | Carries principal from pre-auth source into Spring | Not independent proof that the IdP authenticated the user |
| `PreAuthenticatedAuthenticationProvider` | Loads user details/authorities from app sources | Does not re-verify the gateway's SAMLResponse/OIDC token |
| `UserDetailsService` | Maps allowed user, roles, enabled/locked status | Cannot validate an HTTP header if its origin was spoofed |
| `SecurityContext` | Holds request/session `Authentication` per config | Does not prove `Authentication` came from the genuine gateway |
| `AuthorizationFilter`/method security | Enforces roles/resources/tenants | Cannot fix an already-impersonated principal |

Spring Security's **Request-Header Authentication (Siteminder)** documentation explicitly warns that an attacker can **choose an arbitrary username if headers can be spoofed**. By default `RequestHeaderAuthenticationFilter` reads **`SM_USER`**, though applications can configure another header.

**Never confuse HTTP headers:**

- **`X-Verified-Subject`, `X-Authenticated-User`, `X-Remote-User`, `X-Forwarded-User`, `SM_USER`**: identity claims *if* the application is configured to trust them.
- **`X-Groups`, `X-Roles`, `X-Admin`, `X-Tenant`, `X-Email`**: authorization/context claims; dangerous if trusted for privilege escalation.
- **`X-Forwarded-For`, `X-Real-IP`, `Forwarded: for=...`**: IP/hop metadata, **not user authentication**.
- **`Forwarded: proto=...;host=...`, `X-Forwarded-Host`/`Proto`/`Prefix`/`Port`**: origin/routing metadata; can affect SSO callbacks and redirects.
- **`X-Forwarded-Client-Cert`**: may be a cert chain inserted by a proxy, **not automatically equivalent to a backend-verified mTLS client certificate**.
- **`Authorization: Bearer ...`**: trustworthy only when the gateway/backend **genuinely verifies** issuer/audience/signature/expiry.
- **`Cookie`**: proves a session only when verified by the server/gateway and bound to the user; a client-invented cookie string is never a “login.”

**Takeaway:** A header named `X-Verified-Subject` does not mean it was verified. Header names carry no cryptographic meaning.

## 3. Diagramming Trust Boundaries and Identity Issuers

Example four-hop system:

~~~text
B0 Browser/Internet
    |
    v
P0 CDN / WAF / public edge
    |
    v
P1 SSO authentication gateway  <-- OIDC/SAML IdP
    |
    v
P2 internal ingress / mesh proxy
    |
    v
A0 Spring Boot app :8080
~~~

Distinguish **trust roles**:

| Hop | Request Source | Authenticates Users? | Allowed to Issue Identity Headers? |
| --- | --- | --- | --- |
| B0 browser | Internet | Not by self-assertion | **No** |
| P0 public edge | Internet | Usually transport/WAF only | **No**, unless P0 itself performs approved auth |
| P1 SSO gateway | Trusted P0 or upstream policy only | **Yes**: validates session/OIDC/SAML | **Yes**, after verification |
| P2 ingress | Trusted P1 | Usually forwards only | **Must not invent users**; only forwards protected assertions |
| A0 Spring app | Trusted P2 | May verify signed assertions itself | Accepts identity with provenance; checks local user/rights |

A **transport proxy** allowed to forward requests is not automatically an **identity issuer** allowed to declare “this is alice.” Trust needs two layers:

1. **Peer/transport trust:** the TCP/TLS peer is genuinely an authorized workload/gateway, enforced via network ACLs, ingress auth, mTLS service identity, or mesh authorization.
2. **User identity provenance:** identity was established **by a component that authenticated the user**, not merely relayed from an unauthenticated caller.

### Critical Checkpoints

- Does P1 **strip client-supplied identity headers before login**?
- Does P1 **overwrite existing headers** after authentication?
- Does P2 accept traffic from pods other than P1?
- Can the backend be reached directly via public IP/NodePort/LoadBalancer, secondary ingress, internal DNS, localhost, or a debugging route?
- Is there a second HTTP listener or separate management port bypassing identity policy?
- Do proxies use mTLS **verifying peer identity**, or merely encrypting TLS?
- Are there bypass paths on `/api`, `/admin`, `/actuator`, WebSocket, gRPC, or HTTP/2?
- When the auth gateway fails, does the system **fail closed** or let requests through anonymously/with stale headers?
- Does the backend read roles/permissions from `HeaderUser`/Email/Role or from a DB/policy engine?
- Can an old session keep an old principal even when a new request changes the gateway subject?
- Do multi-tenant systems bind **issuer + subject + tenant**?

## 4. Preparing the Test Suite: Positive Baseline and Layered Observation

Before attempting bypasses, define a **test contract**. Example:

~~~text
Public URL:    https://portal.staging.example.test
Gateway P1:    auth-gateway.staging
App backend:   sso-app:8080 (non-public)
Identity key:  X-Verified-Subject
Test subject:  reader-42
Other subject: admin-77 (must not impersonate a real user)
Protected URL: /api/me
Admin URL:     /admin/report
Identity source: gateway-verified IdP issuer+subject
Expected role: ROLE_READER (from app DB/policy only)
~~~

All hostnames here are **illustrative examples, not live targets**.

### Positive Control P0: Valid Login

Log in with **`reader-42`** through the public gateway. Expectations:

1. The gateway runs OIDC/SAML/session validation rather than merely trusting a username header.
2. The gateway emits `X-Verified-Subject` **from the verified identity**, never from browser request headers.
3. The backend receives user `reader-42` over the trusted path and maps the local account/`ROLE_READER`.
4. `GET /api/me` reports the authorized principal accurately.
5. `GET /admin/report` returns 403 or denies per role policy.
6. After logout/revocation, the old session cannot mint new identities per policy.

**If the positive baseline fails**, negative tests returning 401/403 may be false positives because SSO was broken to begin with. Never mark security PASS before verifying the baseline.

### Observable Signals to Collect

- HTTP status/`Location` at both **gateway** and **backend** (via internal telemetry).
- Route, selected `SecurityFilterChain`, and authentication method/session source.
- **Trusted gateway assertion issuance** events and mapped subject ID (never log raw tokens).
- Backend `Authentication` principal, authorities, tenant, and resource decision.
- Network/mTLS denials on direct connection attempts.
- Sanitized traces/correlation IDs at each hop; never trust attacker-supplied request trace IDs without resetting them.
- Confirmation that no new user accounts/privileges were provisioned by spoofed requests.
- Consistency across fresh sessions, existing sessions, and logout/revocation windows.

An **HTTP 200** on a public login/error page does not prove a bypass succeeded; an **HTTP 500** from an app crash is not a passing security test either. Conclusions require confirming **zero unauthorized authenticated access and accurate layer-specific denial reasons**.

## 5. Test 1: Spoofing Identity Headers Through the Public Gateway

A client can inject internal-looking headers itself:

~~~http
GET /api/me HTTP/1.1
Host: portal.staging.example.test
X-Verified-Subject: admin-77
X-Authenticated-User: admin-77
X-Forwarded-User: admin-77
SM_USER: admin-77
X-Roles: ROLE_ADMIN
~~~

If P0/P1 **forwards client-supplied headers verbatim** and the backend uses pre-auth, an attacker can become `admin-77`. Some systems accept multiple header names or legacy aliases; test **every header capable of influencing application code**.

### Testing with `curl` Against Authorized Staging

~~~bash
curl -i \
  -H "X-Verified-Subject: admin-77" \
  -H "X-Roles: ROLE_ADMIN" \
  https://portal.staging.example.test/api/me
~~~

**Expectation without a valid session:** gateway returns a login challenge/redirect or 401/403; backend creates no `Authentication` for `admin-77`. **Expectation with a valid `reader-42` session:** gateway strips forged headers and emits **`reader-42`**; `/api/me` reflects `reader-42`, never `admin-77`.

Note: `curl -i` **does not send a browser SSO session automatically**; to test the authenticated variant, use cookies/tokens belonging to a **test account** provisioned per staging procedure. Never use someone else's cookies.

### Verifying Outcomes Instead of Guessing

| Variant | Expectation |
| --- | --- |
| Unauthenticated, forged `X-Verified-Subject` | No `Authentication` created |
| Logged in as `reader-42`, forged `admin-77` | If gateway forwards the request, backend sees **`reader-42`** |
| Forged `X-Roles=ROLE_ADMIN` | Local roles unchanged |
| Forged `X-Tenant=other-tenant` | Tenant unchanged / no cross-tenant read |
| `X-Authenticated-User` or `SM_USER` alias | Not accepted as a trusted alternative |
| Two conflicting identity headers | Gateway rejects or emits **one** canonical header |

**Never test against production admin accounts**. Use synthetic IDs and clearly verifiable test resources.

## 6. Test 2: Bypass Paths Directly to the Backend

This test is **separate** from header spoofing via the gateway. Even when P1 strips/overwrites perfectly, if the backend exposes an alternate listener, another caller can send:

~~~text
Normal: Client -> P0 -> P1 (SSO) -> P2 -> backend

Bypass A: Authorized test host -------> backend:8080
Bypass B: Untrusted test pod ---------> ClusterIP service:8080
Bypass C: Alternate public ingress --> backend:8080
Bypass D: Exposed NodePort ----------> backend:8080
Bypass E: Management/debug port -----> protected business handler
~~~

The goal is not to hunt random ports offensively, but to **verify every path to the backend is inventoried and covered by policy**.

### Preparation

- Network/infra team supplies the **approved list of staging endpoints to test**: public ingress, internal service, NodePort (if any), pod/mesh listeners, and relevant management ports.
- Deploy an **untrusted test workload** whose service identity/namespace is outside the allowlist.
- Deploy a **trusted gateway workload** for positive control.
- Ensure the SSO backend accepts traffic only from the exact gateway/ingress per ACL/NetworkPolicy/mTLS policy.
- Never run automated network scans outside the approved staging scope.

### Test Flow

1. Via the public URL, log in as `reader-42` and verify `/api/me`.
2. From the untrusted test host/pod, open a **connection to the approved staging backend endpoint**. Send no real secrets.
3. Verify you hit a **network denial, mTLS peer rejection, or ingress authorization denial**. Connections must not reach business handlers.
4. Repeat with **`X-Verified-Subject: reader-42`** or fake `admin-77`. Outcome must be no better than without the header.
5. Repeat across alternate inventoried routes: secondary ingress hostnames, other ports, sidecar vs. application listeners, HTTP/HTTPS, and sensitive routes.
6. Check telemetry: **request rejected upstream of business auth**; backend emits no security session or protected data.
7. If a direct connection reaches the pre-auth filter and creates an `Authentication` from a spoofed header, that is a **critical gateway bypass** that must be fixed before production.

**Critical note:** MockMvc can simulate requests to a controller, yet MockMvc executes no network routing, TLS handshakes, or Kubernetes policies. Therefore **MockMvc alone cannot prove the backend is unreachable directly**. Network-path/integration evidence is mandatory.

### Why “Private IP Only” Is Insufficient

Not every workload inside a VPC/cluster shares the same trust level. NAT/sidecars/port-forwards, a compromised pod, internal VPN links, or misconfigured NodePorts can allow a non-gateway peer to call the backend directly. Never treat every `10.0.0.0/8` IP as a “trusted identity issuer.”

## 7. Test 3: Trusted Last Proxy Hop, Untrusted Upstream Caller

Suppose the backend trusts only ingress P2 via mTLS:

~~~text
Untrusted pod U
    |
    | X-Verified-Subject: admin-77
    v
P2 internal ingress (mTLS trusted by backend)
    |
    | Forwards header verbatim
    v
Backend
~~~

If P2 fails to restrict **who may send identity assertions**, the backend can still be tricked through a completely valid transport peer.

**Tests:**

- From U, call P2 on a valid backend route without P1 authentication proof.
- Send spoofed identity headers. P2 must **reject or strip the headers** rather than passing them as principals.
- From valid P1 after successful SSO, send a request; P2 accepts and forwards the right identity.
- Check secondary P2 routes/ingress classes (if any) for “auth optional” paths.
- Simulate gateway outage: P2 must **not** proceed with stale identities or skip auth.
- Verify mTLS **service identity** of P1, not merely TLS encryption.

**Conclusion:** A trusted **last hop** does not prove a claim **came from the right identity issuer**. You need gateway authentication, message provenance, and transport restricted strictly to authorized sources.

## 8. Test 4: Role and Tenant Header Spoofing

Even when the principal cannot be forged, an app fails if it reads privileges from client-supplied headers:

~~~http
X-Roles: ROLE_ADMIN
X-Admin: true
X-Groups: security-admins
X-Tenant: tenant-b
X-Email: ceo@example.test
~~~

**Negative cases:**

- Log in as `reader-42` and add `X-Roles=ROLE_ADMIN`. `GET /admin/report` must **deny**.
- Add `X-Tenant=tenant-b`; user may read only `tenant-a` data mapped by local policy, never cross-tenant.
- Change `X-Email` to another user's email; stable issuer+subject must remain `reader-42`.
- Keep a valid authenticated user yet request an object ID owned by someone else; resource-level authorization must deny.
- Disable the local account in the DB; even if the gateway authenticated the user, access must be revoked per SLA.

**Trusted role sources:** local DB/LDAP/policy engine or signed/verified authorization claims with matching issuer/audience/TTL. Trusting raw `X-Roles` headers because “they came from the internal network” is a vulnerability.

Never use email or username local-part as a global identity key across multiple issuers/tenants. Prefer stable **issuer + subject (+ tenant per contract)**.

## 9. Test 5: `X-Forwarded-For` Is Not Proof of User Identity

`X-Forwarded-For` (XFF) typically holds a list of IPs:

~~~http
X-Forwarded-For: 198.51.100.23, 10.0.0.10, 10.0.0.11
~~~

Test example:

~~~text
Spoofed client:  203.0.113.77 (injected in header)
Real client:     198.51.100.23 (address observed by P0)
P0 trusted:      10.0.0.10
P1 trusted:      10.0.0.11
P2 TCP peer app: 10.0.0.12
~~~

If the edge merely appends to XFF without stripping client input, the app may see:

~~~http
X-Forwarded-For: 203.0.113.77, 198.51.100.23, 10.0.0.10, 10.0.0.11
~~~

An app picking the **leftmost element** mistakes spoofed IP `203.0.113.77` for the client IP.

### How to Test Properly

- At the public edge, send `X-Forwarded-For` containing a **synthetic IP** like `203.0.113.77`.
- The edge should **reset XFF to the real peer it observes**, or the proxy chain must walk right-to-left picking the first untrusted hop against an **exact list of trusted proxies**.
- If the immediate TCP peer is untrusted, the app should ignore XFF or reject per policy.
- IP allowlists, internal-only routes, rate limits, and audit attribution must never read raw `XFF[0]`.
- Test repeated XFF headers, IPv6, whitespace, and quoted IPv6 only in parsers/environments that support them.
- Never infer user identity from IP behind shared NATs/office networks.

**Remember:** trusted IP/hop selection and SSO identity verification are separate concerns. Even an accurate source IP in XFF **does not** prove a user logged in.

## 10. Test 6: `Forwarded`, `Host`, `Proto`, and `Prefix` Poisoning

Origin/routing headers can corrupt SSO redirects and cookies:

~~~http
Forwarded: for=198.51.100.23;proto=http;host=attacker.example.test
X-Forwarded-Host: attacker.example.test
X-Forwarded-Proto: http
X-Forwarded-Prefix: /admin
X-Forwarded-Port: 80
Host: portal.staging.example.test
~~~

RFC 7239 `Forwarded` standardizes `for`/`by`/`host`/`proto`, **yet clients can still send it themselves**. `X-Forwarded-*` is another widespread header set; proxies and frameworks may prioritize them differently. Simply bearing the RFC-standard name `Forwarded` does not make a header trustworthy.

**Negative tests:**

1. **`X-Forwarded-Host`** cannot swap the allowed public hostname used in redirect URLs.
2. **`X-Forwarded-Proto=http`** cannot downgrade HTTPS callbacks or security policies.
3. **`X-Forwarded-Prefix`** cannot turn `/public` into `/admin` for access control.
4. **Conflicting `Forwarded` and `X-Forwarded-Host`** must be canonicalized or rejected by the edge per contract.
5. **Unexpected `Host` headers** are rejected by the default virtual host/public gateway.
6. **OIDC `redirect_uri`/SAML ACS URLs** are never derived from untrusted `Host`/`Proto`/`Prefix`.
7. **Password reset links** never embed client-supplied hostnames.
8. **`Secure` cookies, `SameSite`, and CSRF** protections are never weakened by forged proxy metadata.
9. Spoofed **`X-Forwarded-Client-Cert`** is never accepted in place of a verified mTLS handshake/peer certificate.

### Spring Boot `forwarded-headers-strategy`

Spring Boot 3.x supports strategies:

~~~yaml
server:
  forward-headers-strategy: none
~~~

- **`NONE`:** do not use forwarded headers to construct external request origins.
- **`NATIVE`:** servlet containers like Tomcat use native handling; verify trusted proxy lists and parser behavior.
- **`FRAMEWORK`:** Spring Framework `ForwardedHeaderFilter` processes `Forwarded`/`X-Forwarded-*` after a **trusted edge has sanitized** them.

**`ForwardedHeaderFilter` does not verify which client or proxy created the header**. Mode **`removeOnly=true`** strips forwarded headers without trusting their values. When the app does not need dynamic URLs built from forwarded headers, prefer a canonical server-side public base URL.

Never enable `FRAMEWORK`/`NATIVE` just to “make SSO work” before verifying trust boundaries, `Host` allowlists, redirect policies, and direct bypass paths.

## 11. Test 7: Duplicate Headers, Aliases, and HTTP Parser Differentials

Proxies can normalize HTTP headers differently. A test request might contain:

~~~http
X-Verified-Subject: reader-42
X-Verified-Subject: admin-77
~~~

Or variants:

~~~http
x-verified-subject: reader-42
X_Verified_Subject: admin-77
X-Authenticated-User: admin-77
SM_USER: admin-77
~~~

**Header names are case-insensitive**, yet duplicate header values, underscores/hyphens, aliases, and proxy/container normalization can cause different hops to read **different values**.

Essential tests:

- Gateway **removes all inbound identity headers** before issuing verified claims—not merely checking whether a header exists.
- After login, the gateway emits **exactly one canonical identity header**.
- Duplicate identity headers are rejected or canonicalized before the trust boundary so a WAF never inspects the first value while the app uses the last.
- Header aliases must not accidentally map to the same trusted backend variable/attribute.
- Clients cannot send **`Connection: X-Verified-Subject`** to make one hop drop a security header while a later hop misinterprets it.
- No HTTP/1.1 vs. HTTP/2 framing discrepancies merge headers from one request into another.
- Gateway and backend handle invalid header bytes/CRLF/ambiguous parsing consistently and fail closed.
- No route-specific normalization lets `/api` or `/admin` skip sanitization.

**On request smuggling:** this is a distinct parser/framing test class—run it only in **authorized, isolated harnesses**, never sending desynchronization payloads against production. The goal here is ensuring **identities from two requests never mix**.

## 12. Test 8: Sessions, Logout, Stale Identities, and SSO Gateway Outage

Browser SSO often relies on a **gateway session cookie**; the backend may use an `HttpSession` or stateless pre-auth. Both designs carry distinct test cases.

### Stateful Backend

If Spring stores `SecurityContext` in `HttpSession`, an identity may outlive missing or changed headers on subsequent requests. Verify:

- Does the backend session persist after the gateway session expires or logs out?
- If the browser switches from `reader-42` to another user, does the backend retain the old principal?
- Does the session cookie enforce proper session fixation protection, `Secure`, `HttpOnly`, and `SameSite`?
- Do session timeout/revocation policies meet enterprise requirements?
- Can mismatched gateway/app hosts or cookie domains let sessions cross auth boundaries?
- In Spring Security pre-auth, **`setCheckForPrincipalChanges(true)`** and **`setInvalidateSessionOnPrincipalChange(true)`** help with stateful sessions, yet **never replace verifying the header's origin**.
- If the header is absent, a previously authenticated session may still be accepted depending on filter/repository config. Define an explicit policy rather than assuming “missing header auto-logs out.”

### Stateless Backend

If the gateway authenticates every request and emits a trusted identity header, the app can use **`SessionCreationPolicy.STATELESS` + `NullSecurityContextRepository`**. Tests must confirm:

- Every request carries a fresh trusted identity assertion or valid signed token.
- No backend session retains principals from prior requests.
- If the header is missing or the gateway is down, the request is denied.
- No Basic/form/anonymous fallback grants access to protected endpoints.
- When a local account is disabled, subsequent requests are denied per policy.

**CSRF must still be evaluated** whenever browsers automatically send gateway session cookies on cross-site requests. A “stateless” backend does not automatically exempt the whole browser SSO system from CSRF.

## 13. Documenting Test Expectations per Enforcement Point

The goal is not merely observing status codes, but proving the **right layer rejected the request**.

| Test | Expected Blocking Point | Success Indicator |
| --- | --- | --- |
| Client sends forged principal | P0/P1 sanitization | Backend never sees forged identity |
| Client sends forged admin role | P1 or backend role policy | No `ROLE_ADMIN` / 403 on admin resource |
| Unauthenticated client hits public URL | P1 auth | Login redirect or 401/403; no authenticated user forwarded |
| Untrusted pod calls backend directly | NetworkPolicy/mTLS/ACL | Connection denied; never reaches business handler |
| Untrusted caller calls P2 instead of P1 | P2 authorization | No identity assertion accepted |
| Wrong public `Host`/`Proto` | Public edge/request normalization | SSO redirect/ACS still uses trusted URL |
| Spoofed IP in XFF | Edge trusted-hop parser | Raw forged IP not chosen for allowlist |
| Session user changed | Gateway plus backend lifecycle | Principal/roles match new user or deny |
| Gateway outage | P1/P2 fail-closed | No anonymous-to-admin fallback created |
| Valid SSO `reader-42` | P1 + Spring + DB | `/api/me` shows `reader-42`; `/admin/report` denied |

### Why “Denied” Alone Is Not Enough

A test may receive 403 because **no local account existed**, not because headers were stripped. If the goal is proving the gateway never forwarded a forged identity, inspect sanitized gateway emissions or safe backend principal traces. Likewise, a direct-backend test returning 401 because Spring saw no header **does not** prove network isolation if sending a forged header succeeds. Test both with and without the header, then conclude per layer.

## 14. Spring Boot 3 / Spring Security 6: Externally Protected Pre-Auth Header Example

**Mandatory warning:** the code below **does not stop someone from spoofing headers by itself**. It illustrates only the **application** piece inside an architecture that already enforces gateway authentication, header stripping/overwriting, and backend network controls blocking direct untrusted requests. **Never expose this application directly to the internet or an untrusted cluster without boundary, transport, or signed-assertion controls.**

### 14.1. Maven Dependencies

In a `pom.xml` with a Spring Boot parent/BOM compatible with Spring Security 6.x:

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

### 14.2. `application.yml`

**src/main/resources/application.yml**

~~~yaml
server:
  forward-headers-strategy: none

spring:
  application:
    name: proxy-sso-test
~~~

`none` is chosen for the demo when building absolute external URLs dynamically is unnecessary. If a production app needs proxy metadata for callbacks/redirects, configure per the **trusted edge** and test `Host`/`Proto` poisoning.

### 14.3. Java 17 Main Class

**src/main/java/com/example/ssogateway/SsoGatewayDemoApplication.java**

~~~java
package com.example.ssogateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SsoGatewayDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SsoGatewayDemoApplication.class, args);
    }
}
~~~

### 14.4. `SecurityFilterChain` Using Pre-Auth

**src/main/java/com/example/ssogateway/GatewayPreauthSecurityConfig.java**

~~~java
package com.example.ssogateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class GatewayPreauthSecurityConfig {

    @Bean
    UserDetailsService localUsers() {
        // Demo: internal identity from trusted gateway.
        // Production: DB/LDAP/policy with issuer, subject, tenant.
        return username -> {
            if (!"reader-42".equals(username)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("No approved account");
            }
            return User.withUsername(username)
                .password("{noop}not-used-for-proxy-sso")
                .roles("READER")
                .build();
        };
    }

    @Bean
    PreAuthenticatedAuthenticationProvider preauthProvider(
            UserDetailsService localUsers) {

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
            wrapper = new UserDetailsByNameServiceWrapper<>();
        wrapper.setUserDetailsService(localUsers);

        PreAuthenticatedAuthenticationProvider provider =
            new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(wrapper);
        return provider;
    }

    @Bean
    SecurityFilterChain protectedApi(
            HttpSecurity http,
            PreAuthenticatedAuthenticationProvider provider)
            throws Exception {

        NullSecurityContextRepository repo =
            new NullSecurityContextRepository();

        // No @Bean for this filter: avoids Boot auto-registering
        // a Servlet Filter outside the security chain.
        RequestHeaderAuthenticationFilter headerFilter =
            new RequestHeaderAuthenticationFilter();
        headerFilter.setPrincipalRequestHeader("X-Verified-Subject");
        headerFilter.setExceptionIfHeaderMissing(false);
        headerFilter.setAuthenticationManager(
            new ProviderManager(provider));
        headerFilter.setSecurityContextRepository(repo);

        http
            .securityContext(sc -> sc
                .securityContextRepository(repo))
            .sessionManagement(sm -> sm
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new Http403ForbiddenEntryPoint()))
            .addFilterBefore(
                headerFilter,
                UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Significance:**

1. **`RequestHeaderAuthenticationFilter`** reads strictly `X-Verified-Subject`, **without verifying the gateway or any signature**.
2. **`PreAuthenticatedAuthenticationProvider`** checks local users via `UserDetailsByNameServiceWrapper`.
3. **`UserDetailsService`** permits only `reader-42` with `ROLE_READER`, ignoring client-supplied `X-Roles`.
4. **`NullSecurityContextRepository` + `STATELESS`** prevents backend sessions from keeping stale identities; the gateway must supply a validated header on every request.
5. **`Http403ForbiddenEntryPoint`** handles unauthenticated requests per the demo contract; status codes may vary if the app customizes exception handling.
6. **No `formLogin`/`BasicAuth` fallback configured**; if additional mechanisms exist, test their bypass paths separately.
7. **No global `csrf.disable()` configured**; when browsers carry gateway session cookies, unsafe cross-site requests still need proper CSRF controls at the gateway/app.
8. **Do not expose the filter as a Spring Servlet Filter bean** alongside `addFilterBefore`; that can execute it twice outside the chain.
9. **Never treat `request.getRemoteAddr()` after XFF parsing as user authentication proof**. User identity needs its own provenance.
10. **Most importantly:** If an attacker reaches the backend directly and sends `X-Verified-Subject: reader-42`, **this code will authenticate them as `reader-42`**. That illustrates exactly why network/identity trust boundaries must be tested, **not a standalone security solution**.

### 14.5. Controller and Endpoints

**src/main/java/com/example/ssogateway/CurrentUserController.java**

~~~java
package com.example.ssogateway;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {
    @GetMapping("/api/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("subject", principal.getName());
    }

    @GetMapping("/admin/report")
    public Map<String, String> admin(Principal principal) {
        return Map.of("admin", principal.getName());
    }
}
~~~

The app holds **only `ROLE_READER`** in the demo; `/admin/report` is denied even when `X-Roles: ROLE_ADMIN` is sent. This demonstrates **authorization roles do not come from client headers**. Yet calling the backend directly with `X-Verified-Subject: reader-42` still returns 200 on `/api/me`—which is why the app must sit strictly behind a protected boundary.

### 14.6. MockMvc Test for Application-Level Policy

**src/test/java/com/example/ssogateway/GatewayPreauthMvcTest.java**

~~~java
package com.example.ssogateway;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;

@SpringBootTest
@AutoConfigureMockMvc
class GatewayPreauthMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void missingIdentityIsForbidden() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isForbidden());
    }

    @Test
    void approvedLocalSubjectIsMapped() throws Exception {
        // Only verifies application mapping; does not prove
        // gateway/network auth because MockMvc sends headers directly.
        mvc.perform(get("/api/me")
                .header("X-Verified-Subject", "reader-42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("reader-42"));
    }

    @Test
    void clientRoleHeaderDoesNotGrantAdmin() throws Exception {
        mvc.perform(get("/admin/report")
                .header("X-Verified-Subject", "reader-42")
                .header("X-Roles", "ROLE_ADMIN"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownLocalSubjectIsNotAccepted() throws Exception {
        mvc.perform(get("/api/me")
                .header("X-Verified-Subject", "admin-77"))
            .andExpect(status().isForbidden());
    }
}
~~~

**What this test DOES NOT prove:** MockMvc runs inside the application context without traversing CDN/WAF/gateway, Kubernetes `NetworkPolicy`, or mTLS. When `approvedLocalSubjectIsMapped` passes, it only shows the app's pre-auth reads a **header sent by the test**; never call that header-spoofing prevention. Real verification must go through the public gateway and test direct-backend paths in staging.

**Practical sample limitations:** `unknownLocalSubjectIsNotAccepted` may behave differently depending on the project's failure handling/security chain. With fail-fast pre-auth or a custom `AuthenticationEntryPoint`, the status may differ; still assert **no authenticated identity is created** rather than relying solely on the demo's 403. Requires a complete project and dependencies to run, with no built-in IdP/gateway.

## 15. Standalone Java 17: Modeling Identity-Issuance and Anti-Bypass Policy

This program **runs standalone with JDK 17**, requiring no Spring, servers, certificates, or network. It demonstrates decisions based on **trusted ingress source**, gateway auth state, canonical identity, and local permissions. Booleans/strings represent **evidence issued by trusted infrastructure**, **not HTTP headers** an attacker could inject in production.

**File: `GatewaySpoofingPolicyDemo.java`**

~~~java
import java.util.Set;

public final class GatewaySpoofingPolicyDemo {

    private static final String APPROVED_INGRESS = "mtls:auth-gateway";
    private static final Set<String> LOCAL_READERS =
        Set.of("reader-42");

    enum Result {
        BLOCKED_AT_NETWORK,
        LOGIN_REQUIRED,
        LOCAL_ACCOUNT_REJECTED,
        ADMIN_FORBIDDEN,
        VIEW_ALLOWED
    }

    record TestRequest(
        String authenticatedPeer,
        boolean ssoSessionVerifiedByGateway,
        String clientClaimedUser,
        String gatewayVerifiedUser,
        String clientClaimedRole,
        boolean adminResource) { }

    static Result evaluate(TestRequest request) {
        // authenticatedPeer is real mTLS/mesh attestation
        // in this model, NOT a self-asserted HTTP X-Peer header.
        if (!APPROVED_INGRESS.equals(request.authenticatedPeer())) {
            return Result.BLOCKED_AT_NETWORK;
        }

        if (!request.ssoSessionVerifiedByGateway()
                || request.gatewayVerifiedUser() == null) {
            return Result.LOGIN_REQUIRED;
        }

        // Never use clientClaimedUser or clientClaimedRole.
        String subject = request.gatewayVerifiedUser();
        if (!LOCAL_READERS.contains(subject)) {
            return Result.LOCAL_ACCOUNT_REJECTED;
        }
        if (request.adminResource()) {
            return Result.ADMIN_FORBIDDEN;
        }
        return Result.VIEW_ALLOWED;
    }

    public static void main(String[] args) {
        TestRequest normal = new TestRequest(
            "mtls:auth-gateway", true,
            null, "reader-42", null, false);

        TestRequest forgedUser = new TestRequest(
            "mtls:auth-gateway", true,
            "admin-77", "reader-42", null, false);

        TestRequest direct = new TestRequest(
            "untrusted-pod", false,
            "reader-42", null, "ROLE_ADMIN", false);

        TestRequest withoutLogin = new TestRequest(
            "mtls:auth-gateway", false,
            "admin-77", null, null, false);

        TestRequest fakeAdminRole = new TestRequest(
            "mtls:auth-gateway", true,
            "admin-77", "reader-42", "ROLE_ADMIN", true);

        TestRequest unknownUser = new TestRequest(
            "mtls:auth-gateway", true,
            null, "unknown-55", null, false);

        System.out.println("normal=" + evaluate(normal));
        System.out.println("forgedUser=" + evaluate(forgedUser));
        System.out.println("directBackend=" + evaluate(direct));
        System.out.println("withoutLogin=" + evaluate(withoutLogin));
        System.out.println("fakeAdminRole=" + evaluate(fakeAdminRole));
        System.out.println("unknownLocalUser=" + evaluate(unknownUser));
    }
}
~~~

Compile and run:

~~~bash
javac GatewaySpoofingPolicyDemo.java
java GatewaySpoofingPolicyDemo
~~~

**Deterministic stdout from the program logic:**

~~~text
normal=VIEW_ALLOWED
forgedUser=VIEW_ALLOWED
directBackend=BLOCKED_AT_NETWORK
withoutLogin=LOGIN_REQUIRED
fakeAdminRole=ADMIN_FORBIDDEN
unknownLocalUser=LOCAL_ACCOUNT_REJECTED
~~~

**Line-by-line explanation:**

- **normal:** trusted peer + verified SSO + local reader permitted to view.
- **forgedUser:** client claims `admin-77` while gateway verified `reader-42`; forged claim discarded, allowed only as `reader-42`.
- **directBackend:** peer outside trusted ingress is blocked before trusting identity headers.
- **withoutLogin:** despite claiming `admin-77`, gateway holds no verified session so login is required.
- **fakeAdminRole:** client-supplied `X-Roles` grants no admin privileges; `ROLE_READER` can only access ordinary resources.
- **unknownLocalUser:** a gateway-verified subject without a valid local account still receives no business access.

**This is a logic simulation, not an implementation of mTLS, OIDC, SAML, or servlet filters.** Production must obtain peer identity from verified TLS/mesh/network policy, obtain gateway-verified users from an auth engine or signed assertion, and run checks **before** creating an `Authentication`. Never treat booleans from HTTP request bodies/headers as trusted proof.

## 16. Designing E2E Tests with a Staging Gateway in an Authorized Environment

MockMvc tests only the app. To prove SSO boundaries, an integration setup is needed:

~~~text
Test browser/client
    |
    v
Public staging edge
    |
    v
Test authentication gateway
    - Authenticates test session reader-42
    - Removes inbound X-Verified-Subject, SM_USER, X-Roles ...
    - Creates canonical X-Verified-Subject from verified user
    |
    v
Staging ingress with mTLS/service identity allowlist
    |
    v
Spring Boot app
    - Accepts only approved ingress
    - Maps reader-42 to local ROLE_READER
~~~

**Two mandatory execution paths:**

1. **Gateway path:** client → public edge → authentication gateway → ingress → Spring.
2. **Direct-backend path:** untrusted test identity → infra-approved backend test endpoint; **must deny** even when the client sends forged headers.

### E2E Scenario A: Gateway Sanitizes User Headers

1. Log in as `reader-42`.
2. Send a request with `X-Verified-Subject: admin-77`.
3. Gateway verifies the session and overwrites `X-Verified-Subject` with `reader-42`.
4. Backend `/api/me` reflects `reader-42`; `/admin/report` denies.
5. In telemetry, confirm the backend **never received `admin-77` as a trusted identity**.
6. Never log raw session tokens or private user PII.

### E2E Scenario B: Unauthenticated User Cannot Bypass via Headers

1. Craft a request with no cookie/SSO session.
2. Send forged `X-Verified-Subject: reader-42` to the public endpoint.
3. Gateway does not promote the request to authenticated.
4. Response prompts for login/401/403 per UX, with no backend `Authentication`.
5. No `Set-Cookie` creating an authenticated backend session is issued.

### E2E Scenario C: Direct-Backend Attempt

1. Infra provides the exact staging backend endpoint and an authorized test identity.
2. From an untrusted test namespace/service identity, send an HTTP request without headers.
3. Expect network denial/mTLS rejection/ingress denial.
4. Repeat adding `X-Verified-Subject: reader-42`.
5. Result **does not change**: the request still creates no `Authentication` and returns no business data.
6. Repeat across all inventoried alternate routes.
7. Ensure tests have zero impact on production systems.

### E2E Scenario D: Gateway Outage / Fail Closed

1. In the lab, configure the auth gateway to reject all sessions or simulate an IdP session validation outage.
2. Public requests carrying self-asserted headers cannot proceed as authenticated.
3. P2 creates no default identity and does not toggle auth to optional.
4. Backend issues no new sessions and accepts no roles from headers.
5. Verify alerts and recovery behavior once the gateway returns to service.

## 17. Comprehensive Negative Test Matrix

| # | Test Case | Expectation |
| --- | --- | --- |
| 1 | Valid `reader-42` login via P1 | `/api/me` matches `reader-42` |
| 2 | Reader accesses `/admin/report` | Denied per `ROLE_READER` |
| 3 | No session + `X-Verified-Subject=admin-77` | No `Authentication` |
| 4 | Valid reader session + forged admin subject | Remains `reader-42`, not admin |
| 5 | `SM_USER=admin-77` | Does not override canonical user |
| 6 | `X-Authenticated-User=admin-77` | Does not override canonical user |
| 7 | `X-Forwarded-User=admin-77` | Does not override canonical user |
| 8 | `X-Roles=ROLE_ADMIN` | Does not grant `ROLE_ADMIN` |
| 9 | `X-Admin=true` | No privilege escalation |
| 10 | `X-Tenant=tenant-b` | No cross-tenant access |
| 11 | Another user's `X-Email` | Does not remap local identity |
| 12 | Duplicate `X-Verified-Subject` values | Safely rejected/canonicalized |
| 13 | Case-varied identity header | Sanitization not bypassed |
| 14 | Underscore/hyphen header aliases | No parser-differential bypass |
| 15 | `Connection` lists identity header name | Trust check not skipped |
| 16 | Raw XFF spoofing internal IP | Does not bypass IP-based controls |
| 17 | Multi-hop XFF with leftmost spoof | Trusted-hop policy holds |
| 18 | Conflicting `Forwarded` and `X-Forwarded-For` | Canonicalized/rejected |
| 19 | `X-Forwarded-Host attacker.example.test` | Does not alter public redirect host |
| 20 | Forged `X-Forwarded-Proto=http` | Does not weaken TLS/redirect/security controls |
| 21 | `X-Forwarded-Prefix=/admin` | Does not bypass route auth |
| 22 | Forged `X-Forwarded-Client-Cert` | Not treated as mTLS authenticated |
| 23 | Request `Host` outside allowlist | Default virtual host denies |
| 24 | Untrusted test host calls backend directly | Network/TLS/ingress denied |
| 25 | Untrusted pod calls app `ClusterIP` | NetworkPolicy/mTLS denied |
| 26 | Bypass via `NodePort`/alternate listener | No business access |
| 27 | Bypass via secondary ingress/hostname | No business access |
| 28 | Untrusted U calls P2 with forged identity | P2 denies/strips header |
| 29 | Gateway P1 fail-open scenario | No authenticated access |
| 30 | Auth gateway outage | Fails closed; metrics/alerts fire |
| 31 | Disabled local user | No business access even if gateway authenticated |
| 32 | Gateway subject changes in stateful session | Does not retain stale principal outside policy |
| 33 | Logout and old browser cookie | Denied per revocation/lifetime policy |
| 34 | Direct pre-auth MockMvc with user header | May map local user; **never cite as proof of network security** |
| 35 | Wrong-tenant object ID after valid login | Resource-level denial |
| 36 | HTTP/2→HTTP/1 header normalization | Never mixes identities across requests |
| 37 | Repeated malformed headers in lab | Parser fails safely; no identity smuggling |
| 38 | URI path casing/trailing slash/encoded delimiters | Does not hit wrong security chain |
| 39 | `OPTIONS`, `POST`, WebSocket upgrade via other routes | Gateway policy enforced consistently |
| 40 | `/actuator`/`admin` metrics/debug paths | No policy bypass or secret exposure |
| 41 | Unknown signed gateway JWT audience | Backend rejects when using assertion tokens |
| 42 | Expired/revoked gateway token | Backend rejects |
| 43 | Raw `KeyInfo`/JWT header with self-asserted issuer | Never promoted to trusted identity |
| 44 | Cross-site unsafe request with session cookie | CSRF protections work per design |
| 45 | Backend test has legitimate public endpoint | `permitAll` strictly scoped; holds no business data |
| 46 | Before/after ingress policy updates | Regression still passes; no bypass routes added |

**Prioritizing test groups:** Cases 3–15 test header spoofing, 24–29 test **gateway bypass**, 16–23 test proxy metadata, 31–35 test SSO session/authorization, and 36–46 test parser/routing/config drift. Never declare the whole system safe simply because tests in one group passed.

## 18. Evaluation Findings and Severity Classification

### Critical / High

- **Backend can be called directly with forged `X-Verified-Subject` to create an authenticated user**: critical authentication bypass, typically High/Critical depending on scope and exploitability.
- Gateway forwards untrusted `X-Role`/`X-Admin` causing privilege escalation.
- P2 accepts identities from an untrusted pod and the backend trusts them: bypass via a trusted transport proxy.
- Secondary ingress route bypasses auth yet reaches `/admin`.
- App trusts self-asserted public keys/identity tokens from requests as trusted gateway claims.

### Medium / Threat-Model Triage

- `X-Forwarded-Host` poisoning altering `Location`/reset links/SSO callbacks.
- `X-Forwarded-For` spoofing corrupting audits/rate limits/IP policies—can become High if used to permit admin access.
- Broken session lifecycle when switching users or accessing resources with stale privileges.
- Inconsistent header duplication/normalization creating conditional vulnerabilities.
- Gateway outage falling back to a weaker mechanism without proven full bypass.

### Corresponding Remediation Recommendations

| Finding | Remediation |
| --- | --- |
| Client identity headers preserved | Edge/gateway strips and overwrites after auth |
| Direct backend access | Default-deny `NetworkPolicy`/ACL, mTLS service identity, remove public NodePort/listeners |
| Trusted P2 accepts from U | P2 allowlists **authenticated gateway workload**, not just private CIDRs |
| Spring trusts plain headers while network is hard to lock down | Gateway-issued signed identity assertions; backend verifies `iss`/`aud`/signature/`exp` |
| Roles/tenant taken from raw headers | DB/policy-verified claims and local authorization |
| XFF spoofing | Edge reset, right-to-left trusted proxies, never treat XFF as user identity |
| Host/Proto poisoning | Canonical URL/allowlist, sanitized forwarded headers |
| Header duplicates/aliases | Reject duplicates, emit one canonical header, strict proxy parser policy |
| Stale sessions | Explicit session expiry/revocation/principal-change checks |
| Gateway outage fail-open | Fail closed, alert, and test recovery |
| Spring chain mismatch | Explicit `securityMatcher`/ordering, protected fallback chain, tests |
| Parser disagreement | Align HTTP versions/normalization and run regression tests |

**Never remediate by “renaming `X-Verified-Subject` to something more secret.”** A header name is not a credential and can be guessed or observed. Likewise, a private network does not automatically confer trusted identity.

## 19. When Should Raw Identity Headers Be Replaced with Signed Assertions?

An architecture trusting plain headers works only when the **entire network path** is tightly controlled, protected by an upstream auth gateway, and backed by mTLS/ACL proof against direct paths. Across multiple teams, namespaces, proxies, and service-to-service hops, a **signed identity assertion** from P1 to A0 is often far easier to audit.

For example, the gateway emits a JWT with:

- **`iss`**: trusted gateway issuer.
- **`sub`**: stable user identifier (not email alone).
- **`aud`**: exact target backend/service.
- **`exp`/`nbf`/`iat`**: lifetime and freshness.
- **`jti`**: token ID if revocation/replay controls are needed.
- **`tenant`/roles**: strictly from trusted policy; backend still enforces authorization.
- **`signature`**: signed with an onboarded trusted key with rotation/algorithm allowlisting.

The backend **must verify JWT signature, issuer, audience, expiry, and key selection itself** using Spring Security OAuth2 Resource Server/`JwtDecoder` or equivalent. Never fetch JWK URLs from untrusted token headers; never reuse an OIDC ID Token as an API access token without an explicit security contract.

**JWTs do not solve everything automatically:** a compromised gateway signer can still mint bad claims; exposed bearer tokens are not replay-proof by themselves; audience validation and short TTLs remain essential. Network isolation, mTLS, resource authorization, monitoring, and revocation policies must still be maintained.

### A Note on mTLS

If the backend only enforces mTLS from P2, the app knows the peer is P2, **not necessarily that P2 authenticated the user**. End-to-end proof from P1 can be a signed assertion, or P2 must guarantee only P1 can issue identities and no bypass paths exist. Never accept untrusted **`X-Forwarded-Client-Cert`** as equivalent to a certificate verified directly by the app over TLS.

## 20. Enterprise Testing Rollout Checklist

- [ ] Architecture diagram covers all hops and alternate backend paths, including CDN/WAF/SSO gateway/ingress/mesh/admin listeners.
- [ ] Single **identity issuer** authorized to mint trusted user claims is identified.
- [ ] Public edge strips client identity headers, including aliases, duplicates, and underscore variants.
- [ ] Gateway genuinely validates OIDC/SAML/sessions and overwrites the canonical subject per request.
- [ ] Internal ingress accepts identity assertions strictly from the authenticated gateway workload/service account.
- [ ] Backend is non-public and receives traffic only through allowlisted ingress with proper ACLs/`NetworkPolicy`/mTLS.
- [ ] **Direct-to-backend** tests run from authorized untrusted namespaces/devices, both with and without forged headers.
- [ ] **P2 bypass** tests run from non-SSO upstreams even when P2 uses mTLS with the backend.
- [ ] Positive control user `reader-42` genuinely logs in successfully via the gateway.
- [ ] Forged user/role/tenant/email headers never alter `Authentication`, authorities, or tenant.
- [ ] No permissions assigned from raw `X-Roles`/`X-Admin`/`X-Groups`.
- [ ] XFF/`Forwarded` never treated as user login proof; trusted-hop parsing and IP policies tested.
- [ ] Host/Proto/Prefix poisoning never alters SSO `redirect_uri`/ACS/`Location` or cookie security.
- [ ] Header duplication, casing, aliases, `Connection` headers, and HTTP/1.1↔HTTP/2 handled consistently.
- [ ] Spring `SecurityFilterChain`, `/admin`, `/api`, `/actuator`, and alternate routes all audited.
- [ ] Pre-auth filter placed in the right chain without duplicate auto-registration or out-of-policy fallbacks.
- [ ] Local `UserDetailsService` checks account enabled/tenant and never promotes administrators from headers.
- [ ] For stateful backends, session logout/expiry/principal-change tested; for stateless, fresh requests require fresh trusted identities.
- [ ] CSRF/Origin/Cookie `SameSite`/`Secure`/`HttpOnly` match browser SSO design.
- [ ] If using JWT assertions, signature/`iss`/`aud`/`exp`/`alg`/key rotation verified at backend.
- [ ] Gateway outages **fail closed** without falling back to default users or cached headers.
- [ ] Tests never use real admins/prod secrets or scan outside approved staging.
- [ ] Observability logs sanitized subject, route, source service identity, deny reason, and trace; never tokens/cookies.
- [ ] Test results distinguish denials at network, gateway, Spring pre-auth, and local authorization.
- [ ] CI/staging runs regression suite after proxy, ingress, service mesh, SSO gateway, or Spring Security upgrades.

**Conclusion:** Gateway SSO testing does not stop at “login succeeded” or “API returns 401 without a cookie.” The system must prove **clients cannot pick arbitrary users via HTTP headers** and **no path delivers forged headers to the backend bypassing the authentication gateway**. When designing tests, always separate: **who authenticates the user**, **who may issue identity assertions**, **who may transport them**, **whether the backend verifies assertions itself**, and **whether the app enforced resource authorization**. A `RequestHeaderAuthenticationFilter` wired strictly by the API docs can still become a vulnerability if trust boundaries go untested.

## 21. References

- [Spring Security 6.5 – Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html): `RequestHeaderAuthenticationFilter`, `PreAuthenticatedAuthenticationProvider`, requirement to protect headers from external authenticators.
- [Spring Security 6.5 – `RequestHeaderAuthenticationFilter` API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html): `principalRequestHeader`, `exceptionIfHeaderMissing`.
- [Spring Security 6.5 – `AbstractPreAuthenticatedProcessingFilter` API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): context persistence, failure handling, and principal-change checking.
- [Spring Security 6.5 – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextRepository`, session lifecycle.
- [Spring Framework 6.2 – `ForwardedHeaderFilter`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): trust boundaries, forwarded headers, `removeOnly`.
- [Spring Boot 3.5 – `ForwardHeadersStrategy` API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html): `NONE`/`NATIVE`/`FRAMEWORK`.
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html): `for`/`by`/`host`/`proto` and security considerations.
- [OWASP Web Security Testing Guide – Bypassing Authorization Schema](https://owasp.org/www-project-web-security-testing-guide/): testing unauthorized/forced browsing and authorization boundaries.
- [OWASP WSTG – Other HTTP Security Header Misconfigurations](https://owasp.github.io/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management/14-Other_HTTP_Security_Header_Misconfigurations): header injection, hop-by-hop handling, header stripping concerns.
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, per-resource authorization.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login/session trust boundaries.
- [MDN – X-Forwarded-For](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For): handling forwarded IPs and risks of spoofed values.
