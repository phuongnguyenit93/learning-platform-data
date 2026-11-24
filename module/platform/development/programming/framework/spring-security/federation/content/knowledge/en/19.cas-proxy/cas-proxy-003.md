# Proxy Callback Endpoint and HTTPS / Certificate Requirements

> **Topic:** Spring Security – federation. **Group:** CAS Proxy. This Knowledge lesson explains how a Spring Security application acts as a **CAS proxying service** to receive a **Proxy-Granting Ticket (PGT)** via a callback endpoint, properly configure `pgtUrl`/`proxyCallbackUrl`/`proxyReceptorUrl`, satisfy the CAS Server's **HTTPS and TLS/PKIX certificate validation** requirements, and then use the PGT to request a **Proxy Ticket (PT)** to access a back-end service. The scope covers CAS protocol 2.0/3.0, Java 17+, and the Spring Security Servlet CAS client; integration examples target Spring Security 6.5.x, with notes to verify APIs on other versions.

## 1. Learning Objectives and Prerequisites

After this lesson, you will be able to:

1. Distinguish `Service Ticket (ST)`, `Proxy-Granting Ticket (PGT)`, `Proxy-Granting Ticket IOU (PGTIOU)`, `Proxy Ticket (PT)`, `Ticket-Granting Ticket (TGT)`, and application sessions.
2. Explain why the CAS Server **actively makes a server-to-server connection** to `pgtUrl` rather than merely redirecting the browser back to the app.
3. Correctly define two separate addresses: `ServiceProperties.service` is the endpoint receiving the ST, while `proxyCallbackUrl` is the endpoint CAS calls to deliver the PGT.
4. Configure **`Cas20ProxyTicketValidator` and `CasAuthenticationFilter` to share the same `ProxyGrantingTicketStorage`**; understand the relationship between the absolute callback URL and the local filter matcher.
5. Understand the exact CAS protocol requirements: `pgtUrl` must be **HTTPS**, the CAS Server must establish peer trust via certificate/PKIX validation, and the callback must return HTTP **200 OK** before PGTIOU issuance completes.
6. Diagnose hostname/SAN errors, certificate expiry, trust chains, root CAs, reverse proxies, redirects, ingress, firewall/WAF rules, and mismatched paths.
7. Operate `pgtId ↔ pgtIou` storage/correlation safely with TTLs, tenant isolation, node synchronization, and protection against losing PGTs when callbacks hit a different node.
8. Validate the `proxy chain` downstream rather than arbitrarily enabling `acceptAnyProxy=true`.
9. Write illustrative Spring Security CAS bean configurations alongside a standalone Java 17 example to verify correlation semantics, URL matching, and failure modes.
10. Build a complete positive/negative test matrix verifying PGT issuance, HTTPS callbacks, certificates, proxy ticket scoping, and zero secret leakage.

**Lesson scope:** If an application only needs CAS SSO and a local HttpSession, **no PGT callback is needed**. The proxy mechanism should only be enabled when **application A needs to access a CAS-protected application B on behalf of the user**. Do not expose new endpoints or grant proxying privileges without an approved use case.

## 2. Why Does CAS Proxy Need a Different Callback from CAS Login?

Scenario: a user logs into App A through CAS. App A needs to fetch data from API B, but B cannot see browser cookies/TGT and must not trust a self-asserted username in an HTTP header.

```text
                   [ CAS SERVER ]
                   /cas/login
                   /cas/serviceValidate
                   /cas/proxy
                   /cas/proxyValidate
                         |
               HTTPS GET pgtUrl callback
                         |
                         v
[ Browser ] ---> [ APP A / CAS CLIENT ] ----PT----> [ BACKEND SERVICE B ]
                   /login/cas                      /data, /proxyValidate
                   /login/cas/proxyreceptor
```

App A authenticated the user with an ST, but the ST is **single-use for App A only** and cannot be copied to B. For A to represent the user, CAS issues a **PGT** to A. App A uses that PGT to ask CAS for a **PT specifically bound to service B**. B must validate the PT with CAS `/proxyValidate` and evaluate the **proxy chain** permitted by B's policy.

The control gate for PGT creation sits at the **proxy callback endpoint**. CAS does not simply trust an app with a valid ST and hand out a PGT over an arbitrary HTTP channel; it must verify that the HTTPS callback truly belongs to a service authorized to proxy.

### 2.1. Ticket Comparison Table

| Artifact | Where Is It Used? | Scope / Properties | What Is It Allowed to Do? |
| --- | --- | --- | --- |
| `ST-...` / Service Ticket | Browser delivers to App A; App A validates at CAS | Single-use and bound to `service` | Proves login to A; **never** used to call B |
| `PGT-...` / Proxy-Granting Ticket | Issued by CAS to App A via HTTPS callback | Sensitive credential held server-side by A; can request many PTs until expired/revoked | Requests new PTs at CAS `/proxy` |
| `PGTIOU-...` | Returned by CAS in `/serviceValidate`/`/proxyValidate` responses | Correlation handle for A to retrieve the PGT stored during callback | **Never** replaces PGT when calling `/proxy` |
| `PT-...` / Proxy Ticket | App A calls service B; B validates at CAS | Bound to `targetService`, single-use upon validation, includes proxy chain | Represents user specifically to B |
| `TGT`/`TGC` | CAS Server and browser at CAS origin | CAS Server SSO session | Helps CAS mint new STs; not a PGT |
| `JSESSIONID` / local session | Browser and App A | App A's application session | Not a PT, PGT, or PGTIOU |

**Note:** A PGT is not an OAuth2 refresh token and a PT is not an OIDC access token; the CAS proxy model has its own endpoints and verification semantics. Never give a PGT to the browser or store it in `localStorage`/cookies. If service B only supports OAuth2, you need a policy-governed broker/token exchange—**never** send a CAS PT as a Bearer JWT.

### 2.2. Two Types of “Callbacks” in One Application

| URL | Caller | Data Sent | Responsibility |
| --- | --- | --- | --- |
| `https://app.example.org/login/cas` | **Browser** after CAS login | `?ticket=ST-...` | `CasAuthenticationFilter` receives ST to create local `Authentication` |
| `https://app.example.org/login/cas/proxyreceptor` | **CAS Server** (HTTP client) | `?pgtId=PGT-...&pgtIou=PGTIOU-...` | CAS client stores PGT keyed by IOU, returns HTTP 200 |
| `https://sso.example.org/cas/serviceValidate` | **App A Backend** | `ticket=ST`, `service=...`, `pgtUrl=...` | CAS validates ST and initiates PGT issuance if callback passes |
| `https://sso.example.org/cas/proxy` | **App A Backend** | `pgt=PGT`, `targetService=B` | CAS issues PT for B |
| `https://sso.example.org/cas/proxyValidate` | **Backend B** | `ticket=PT`, `service=B` | CAS validates PT and proxy chain |
| `https://app.example.org/logout` | Browser | Local logout request | Not a PGT callback and does not automatically revoke all PGTs/TGTs |

**The two callbacks are distinct endpoints.** CAS `/login` redirects the browser to `/login/cas`; CAS `/serviceValidate` opens a server-to-server connection to `/login/cas/proxyreceptor`. Conflating these two endpoints can prevent CAS from getting HTTP 200, trigger redirects to login, or treat a PGT like an ST.

## 3. Detailed PGT Issuance Flow per CAS Protocol

Suppose three real systems exist in a test environment:

```text
CAS Server base:       https://sso.example.org/cas
App A service URL:     https://app.example.org/login/cas
App A proxy callback:  https://app.example.org/login/cas/proxyreceptor
Target service B:      https://api.example.org/reports
```

Standard sequence:

1. A browser without a local session on A accesses `/reports` on A.
2. App A redirects the browser to `https://sso.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas`.
3. CAS authenticates the user (or reuses a valid TGT/TGC) and **issues an ST for service A**.
4. Browser sends GET `https://app.example.org/login/cas?ticket=ST-...`. Spring Security's `CasAuthenticationFilter` receives the ST.
5. App A's backend calls `/cas/serviceValidate` with **`ticket`, `service`, and `pgtUrl`**, where `pgtUrl` is the absolute HTTPS callback URL.
6. CAS validates the ST/service and App A's proxy policy; before handing over the PGT, CAS **connects over HTTPS to `pgtUrl` and verifies the peer certificate per PKIX/trust policy**.
7. CAS sends an **HTTP GET** to `pgtUrl?pgtId=PGT-...&pgtIou=PGTIOU-...`. Real values are sensitive credentials; these are symbolic placeholders.
8. The proxy receptor endpoint on A stores the `(PGTIOU, PGT)` pair in `ProxyGrantingTicketStorage`. It responds HTTP **200 OK**, without redirecting to the IdP/login.
9. If the callback succeeds, CAS returns the `serviceValidate` result containing `<cas:authenticationSuccess>` and `<cas:proxyGrantingTicket>PGTIOU-...</cas:proxyGrantingTicket>`.
10. Client A looks up the PGT matching PGTIOU in storage. This is the **correlation step**—the PGT is never read directly from the validation XML response.
11. App A uses the PGT to call CAS `/proxy?pgt=PGT-...&targetService=https%3A%2F%2Fapi.example.org%2Freports`. CAS issues a PT.
12. App A calls API B carrying the PT per CAS client/protocol; B calls CAS `/proxyValidate`, verifying the PT matches target service, is valid, and has an allowed proxy chain.
13. B returns results to A only if **both CAS validation and B's business authorization** pass. A must not treat holding a PT as permission to read every API or tenant.

### 3.1. Sequence Diagram

```text
Browser         App A (Spring CAS)              CAS Server                Service B
  |                    |                            |                         |
  |-- GET /reports --->|                            |                         |
  |<-- CAS login 302 --|                            |                         |
  |------------------------------ CAS login -------->|                         |
  |<----------------------------- service ST --------|                         |
  |-- /login/cas?ticket=ST ----->|                    |                         |
  |                    |-- /serviceValidate -------->|                         |
  |                    |   ticket=ST, service=A      |                         |
  |                    |   pgtUrl=https://A/receptor |                         |
  |                    |                            |-- TLS PKIX to A ----->  |
  |                    |<--- GET /receptor ----------|                         |
  |                    |    pgtId + pgtIou           |                         |
  |                    |--- 200 OK ----------------->|                         |
  |                    |<-- success + PGTIOU --------|                         |
  |                    |-- lookup PGT by PGTIOU      |                         |
  |<-- App A session --|                            |                         |
  |                    |-- /proxy?pgt&targetService ->|                         |
  |                    |<--------------- PT --------|                         |
  |                    |-------------------------------- PT ------------------>|
  |                    |                            |<-- /proxyValidate PT ----|
  |                    |                            |---- valid + proxies ---->|
  |                    |<----------------------------------- authorized data --|
  |<-- page/data ------|                            |                         |
```

In the diagram, the “TLS PKIX to A” arrow represents the **CAS Server** opening a connection to A's public HTTPS callback—not service B. The callback can occur concurrently while App A is waiting on the validation response. **Therefore PGT storage must be safe in multi-threaded and multi-node environments**.

### 3.2. Illustrative Request Formats

ST validation step from App A to CAS:

```http
GET /cas/serviceValidate?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas&ticket=ST-EXAMPLE&pgtUrl=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas%2Fproxyreceptor HTTP/1.1
Host: sso.example.org
```

CAS callback step (from CAS Server to App A, **not the browser**):

```http
GET /login/cas/proxyreceptor?pgtId=PGT-EXAMPLE&pgtIou=PGTIOU-EXAMPLE HTTP/1.1
Host: app.example.org
```

CAS response to App A after callback 200:

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxyGrantingTicket>PGTIOU-EXAMPLE</cas:proxyGrantingTicket>
  </cas:authenticationSuccess>
</cas:serviceResponse>
```

**Do not misunderstand:** The XML returns **PGTIOU**, not the raw `PGT-EXAMPLE`. The PGT arrives at App A via the **HTTPS callback** and is persisted server-side. The examples above are not valid STs/PGTs and cannot be used against a production CAS Server.

## 4. `pgtUrl` Is a Sensitive Identifier, and HTTPS Is a Protocol Requirement

Under CAS Protocol 3.0, `pgtUrl` is sent during ST/PT validation and **MUST use HTTPS**. The CAS Server must evaluate the endpoint to establish trust; at minimum it uses **PKIX** and its runtime certificate truststore to verify:

- The certificate signature and certificate chain up to a trust anchor accepted by CAS.
- The certificate validity window (`notBefore`, `notAfter`)—neither expired nor not-yet-valid.
- The callback's hostname identity per TLS hostname verification, typically via Subject Alternative Name (SAN) under deployment compatibility policy.
- Key algorithm/size, key usage/EKU, CA constraints, and operational policy if enforced by the CAS/TLS client.
- That the HTTPS endpoint is actually reachable, completes the handshake, and returns **HTTP 200** on the callback path.

**A two-way distinction:** The CAS Server acts as the **TLS client** when calling App A's callback; A's reverse proxy/ingress acts as the **TLS server** and must present a valid certificate. This is **A's TLS certificate**, not an IdP's public SAML signing certificate or an SP private key used to sign a SAML AuthnRequest.

### 4.1. Who Trusts Whose Certificate?

| Connection | TLS Client | TLS Server | Which Certificate Is Verified? | Where Does the Truststore Live? |
| --- | --- | --- | --- | --- |
| Browser → App A `/login/cas` | Browser | App A/ingress | App A's TLS server cert | Browser/OS trust |
| Browser → CAS `/cas/login` | Browser | CAS Server | CAS's TLS server cert | Browser/OS trust |
| **App A → CAS `/cas/serviceValidate`** | **App A JVM** | **CAS Server** | **CAS's TLS server cert** | JVM/app truststore |
| **CAS → App A `pgtUrl` callback** | **CAS HTTP client** | **App A ingress** | **App A's TLS server cert** | CAS HTTP client/JVM/local truststore |
| App A → CAS `/cas/proxy` | App A JVM | CAS Server | CAS's TLS cert | App A JVM truststore |
| App B → CAS `/cas/proxyValidate` | App B JVM | CAS Server | CAS's TLS cert | App B JVM truststore |
| App A → Service B | App A | Service B | B's TLS cert | App A truststore |

**An easy asymmetry mistake:** Adding the CAS Server's root CA to **App A's** truststore does not mean the CAS Server trusts App A's callback. If CAS calls A and hits `PKIX path building failed`, fix trust/the certificate chain **on the CAS side** or **A's** reverse proxy certificate. The two TLS connections have different verifiers and different truststores.

### 4.2. Checking the Certificate Chain

Suppose App A is published at `https://app.example.org/login/cas/proxyreceptor` with a certificate issued by a valid CA. CAS receives the certificate chain from the TLS endpoint. Common failures:

| Error | Behavior | Remediation |
| --- | --- | --- |
| **Expired** certificate | CAS TLS handshake/PKIX fails | Renew certificate and deploy full chain before cutover |
| Certificate **before NotBefore** | Cert not yet valid | Fix clock/replace cert for valid window, sync UTC/NTP |
| Missing **intermediate CA** | CAS cannot build trust path | Configure full chain on the TLS terminator |
| Internal root CA untrusted by CAS | `PKIX path building failed` | Import approved CA/cert into CAS truststore via process; never trust-all |
| SAN does not match `app.example.org` | Hostname verification fails | Issue certificate with SAN matching public callback host |
| Callback uses IP while cert only has DNS SAN | Hostname mismatch | Use FQDN matching cert instead of raw IP |
| **Default virtual host** certificate | SNI/LB route serves another domain's cert | Fix SNI/ingress virtual host configuration |
| Reverse proxy nodes serve inconsistent certs | Some callbacks succeed, some fail | Synchronize cert/chain across all nodes/LB listeners |
| No common TLS protocol/cipher | Handshake fails | Use mutually allowed TLS versions/ciphers; never downgrade security arbitrarily |
| Rejected by revocation/status policy | CRL/OCSP or policy fails if enabled | Check exact CAS/JVM policy and fix certificate/chain |
| Untrusted self-signed certificate | CAS cannot verify chain by default | Use a trusted CA or import an approved trust anchor; never bypass PKIX |

**Note:** The CAS Protocol requires PKIX and certificate validity; SAN/hostname checks, EKU, revocation, OCSP/CRL, and algorithm constraints are also governed by HTTPS client/JDK settings and deployment policy. **Test against the real CAS Server** rather than relying on the browser's “HTTPS padlock.”

### 4.3. “Certificate Valid in Browser” Does Not Guarantee Valid in CAS

Browsers use OS/browser trust stores that differ from the JVM on the CAS Server. A CAS container may use a stripped-down or custom local truststore. An internal CA installed on your laptop but **absent on the CAS host** will cause the callback to fail.

Conversely, operators adding certificates via a `trust-all` setting increase risk: CAS can no longer validate the callback's identity, allowing an intermediary or attacker endpoint to intercept the PGT. **Never disable hostname verification or use an accept-all TrustManager** to force a test to “pass.”

### 4.4. HTTPS Termination at a Reverse Proxy

```text
CAS Server -- HTTPS --> Load Balancer/Ingress :443
                                 |
                                 | Internal HTTP to app:8080
                                 v
                         Spring CAS Client
                         proxyReceptorUrl=/login/cas/proxyreceptor
```

CAS sees only the TLS certificate at the **load balancer/ingress**, not an internal cert on port 8080, when TLS terminates there. Consequently:

- The cert/SAN/chain on the ingress must match the external FQDN of `pgtUrl`.
- The ingress must forward the exact request path and `pgtId`, `pgtIou` query parameters to the app without replacing them with a login redirect or auth portal.
- Plain HTTP between ingress and backend is acceptable **only when** topology/policy permits and the internal network is protected; CAS→ingress **must still be HTTPS**. In zero-trust/sensitive networks, consider end-to-end TLS/mTLS to the backend.
- Never change `pgtUrl` to `http://app-internal:8080/...` for faster server-side HTTP: it violates the CAS protocol and strips PGT protection.
- Trust `Forwarded`/`X-Forwarded-*` headers only from controlled proxies; strip client-supplied headers. Never build `pgtUrl` dynamically from a raw `Host` header.
- If the LB acts as a WAF, do not place challenges/CAPTCHAs/logins on the CAS callback; the CAS HTTP client has no browser session.

## 5. Distinguishing Three URLs in Spring Security CAS Proxy

Suppose App A runs at public host `app.example.org`:

| Setting | Illustrative Value | Exact Role |
| --- | --- | --- |
| `ServiceProperties.service` | `https://app.example.org/login/cas` | CAS ST is issued for this URL |
| `CasAuthenticationFilter.filterProcessesUrl` | `/login/cas` | Filter watches for ST callbacks from the browser |
| `Cas20ProxyTicketValidator.proxyCallbackUrl` | `https://app.example.org/login/cas/proxyreceptor` | CAS Server receives this value in `pgtUrl` |
| `CasAuthenticationFilter.proxyReceptorUrl` | `/login/cas/proxyreceptor` | Filter watches for inbound CAS GET callbacks |
| CAS Server base | `https://sso.example.org/cas` | Base URL for `Cas20ProxyTicketValidator` validate/proxy calls |
| Downstream target service | `https://api.example.org/reports` | CAS PT is issued/validated solely for service B |

**Constraint 1:** `ServiceProperties.service` must match the service ID in `/cas/login` and `/cas/serviceValidate`; it is **not** `pgtUrl`.

**Constraint 2:** The local path `proxyReceptorUrl` must correspond to the public path of `proxyCallbackUrl` (accounting for context paths/proxy prefixes). It is not an absolute URL; the CAS Validator needs an **absolute HTTPS URL**, while the Filter needs a **local path**.

**Constraint 3:** `Cas20ProxyTicketValidator` and `CasAuthenticationFilter` must use **the same instance or the same logical distributed storage**. If each uses a different map or Redis namespace, the callback stores the PGT but authentication logic cannot find it via PGTIOU.

### 5.1. What About a Context Path?

For example, a Java Servlet app with `server.servlet.context-path=/portal`:

```text
public service URL:
  https://app.example.org/portal/login/cas

absolute pgtUrl:
  https://app.example.org/portal/login/cas/proxyreceptor

local filterProcessesUrl:
  /login/cas

local proxyReceptorUrl:
  /login/cas/proxyreceptor
```

Local paths **typically** omit the servlet context path; however, if an ingress adds/strips prefixes or modifies the servlet path, verify the actual matcher in Spring Security. Never guess that `proxyReceptorUrl` must be `/portal/login/cas/proxyreceptor` when the servlet already has context path `/portal`.

In Spring Security 7.x, the matching API of `CasAuthenticationFilter` changes regarding `RequestMatcher`; consult your version's reference/migration guide and write callback endpoint tests. Do not copy 6.x config verbatim into 7.x when matching semantics change.

### 5.2. Why Must the Callback Never Redirect?

The CAS Protocol allows CAS to **optionally** follow HTTP 3xx when accessing `pgtUrl`, yet successful PGT issuance requires CAS to observe an HTTP **200** response from the appropriate endpoint. Your implementation should have the callback return 200 **directly**, never relying on 301/302/307 because:

- An HTTP→HTTPS redirect could expose the PGT over HTTP on the first hop; the initial `pgtUrl` must be HTTPS.
- Redirecting to a login page could cause the CAS HTTP client to receive a 200 HTML page without storing the PGT, causing misleading diagnostics.
- Redirecting to another hostname/path may violate service registry/hostname validation, break correlation, and open SSRF avenues.
- A 302 redirect may be blocked or capped by load balancers, WAFs, or CAS policy.
- Browser cookies and the user's SSO session are **not** sent in server-to-server callbacks from CAS.

Therefore `GET /login/cas/proxyreceptor?pgtId=...&pgtIou=...` must be intercepted by the filter and answered **200 OK** after proper processing. Never return a login HTML page, 401/403 due to a missing browser cookie, 404 due to a missing MVC controller, or 302 back to CAS login.

## 6. Spring Security: Which Beans Need Configuration?

Referring to Spring Security CAS Servlet support, there are five core groups:

1. `ServiceProperties`: the ST-receiving service callback, `sendRenew`/protocol parameters. Keep `authenticateAllArtifacts=false` if A only receives STs from browsers; do not blindly enable proxy-ticket auth on all URLs.
2. `CasAuthenticationEntryPoint`: redirects unauthenticated browsers to CAS `/login` with `service`.
3. `CasAuthenticationFilter`: receives STs at `filterProcessesUrl` and PGT callbacks at `proxyReceptorUrl`; invokes the authentication manager and saves context for the web session.
4. `CasAuthenticationProvider` with `Cas20ProxyTicketValidator`: validates STs (and when separately configured, PTs) and configures `proxyCallbackUrl` + `ProxyGrantingTicketStorage`.
5. `ProxyGrantingTicketStorage`: stores `PGTIOU → PGT` for both the callback and validator lookup. Pick a production implementation with TTL, distributed state, cleanup, access controls, and secure secret handling.

**Note:** Having `Cas20ProxyTicketValidator` does not automatically enable accepting incoming PTs on every API. If App A **only requests a PGT to call B**, keep browser ST handling at `/login/cas`. If A also needs to **accept incoming PTs from other clients**, that is a separate concern requiring `authenticateAllArtifacts`, `ServiceAuthenticationDetailsSource`, and a dedicated stateless cache/proxy-chain allowlist—do not conflate them just to reduce bean count.

### 6.1. Do Not Write a Custom Controller That Captures `pgtId` and Saves Plaintext

`CasAuthenticationFilter` provides built-in proxy receptor support when both `proxyReceptorUrl` and `proxyGrantingTicketStorage` are set. A `@GetMapping("/proxyreceptor")` controller that reads `pgtId` and writes to a database can:

- Accept tickets from untrusted callers and store forged PGTs.
- Leak PGTs into access logs or tracing.
- Store PGTIOUs disconnected from the validator/store.
- Neglect cleanup, TTLs, and concurrency.
- Return wrong statuses or unintended redirects.

When the CAS Client product already provides a filter, **prefer the official filter**. If a custom receptor is unavoidable, preserve equivalent HTTP semantics, atomic correlation, secret protection, input validation, timeouts, and auditing; test against a real CAS Server.

## 7. Configuring Spring Boot 3.x + Spring Security 6.5.x, Java 17+

### 7.1. Dependencies

In a Spring Boot project with parent/BOM and Java 17, the minimal Maven dependencies for Servlet CAS web are:

```xml
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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
  </dependency>
</dependencies>
```

`spring-security-cas` pulls in a compatible Apereo Java CAS Client; if the project overrides versions, inspect `./mvnw dependency:tree` and the actual version's Javadoc. This is a **`pom.xml` snippet**, not a standalone POM.

A staging CAS Server must be ready with a registered service for App A, policy allowing **proxy authentication**, trusted HTTPS certificates, and backend target B also registered with CAS. The `example.org` URLs below are lab placeholders, **not live Internet services**.

### 7.2. `application.yml` — Public URLs and Local Filter Paths

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

app:
  cas:
    server-base-url: "https://sso.example.org/cas"
    login-url: "https://sso.example.org/cas/login"
    service-url: "https://app.example.org/login/cas"
    proxy-callback-url: "https://app.example.org/login/cas/proxyreceptor"
    proxy-receptor-path: "/login/cas/proxyreceptor"
```

In this illustrative deployment, an ingress/TLS terminator accepts public HTTPS and forwards to the Spring backend on port 8080. When running directly in dev, set up proper HTTPS/context path/certs or use a production-like staging reverse proxy; never change `proxy-callback-url` to plain HTTP.

**Protect configuration:** Manage these URLs through reviewed configuration/secret management. Never let the browser construct `pgtUrl` from `?callback=...`, `Host`, or `X-Forwarded-Host`. If a user can choose an arbitrary callback URL, the CAS Server can be forced into SSRF connections or hand the PGT to the wrong host.

### 7.3. Configuring Filter, Provider, Validator, and Shared Storage

File `src/main/java/com/example/casproxy/CasProxySecurityConfig.java`:

```java
package com.example.casproxy;

import org.apereo.cas.client.proxy.ProxyGrantingTicketStorage;
import org.apereo.cas.client.proxy.ProxyGrantingTicketStorageImpl;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class CasProxySecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
            @Value("${app.cas.service-url}") String serviceUrl) {

        ServiceProperties props = new ServiceProperties();
        props.setService(serviceUrl);
        props.setSendRenew(false);
        // Do not enable authenticateAllArtifacts when only accepting browser STs
        // and acting as an OUTBOUND proxy to service B.
        props.setAuthenticateAllArtifacts(false);
        return props;
    }

    @Bean
    ProxyGrantingTicketStorage pgtStorage() {
        // LAB ONLY: in-memory data, no HA/replication.
        // Production: distributed storage with TTL/cleanup/secret controls.
        return new ProxyGrantingTicketStorageImpl();
    }

    @Bean
    Cas20ProxyTicketValidator ticketValidator(
            @Value("${app.cas.server-base-url}") String casBase,
            @Value("${app.cas.proxy-callback-url}") String callback,
            ProxyGrantingTicketStorage storage) {

        Cas20ProxyTicketValidator validator =
            new Cas20ProxyTicketValidator(casBase);
        validator.setProxyCallbackUrl(callback);
        validator.setProxyGrantingTicketStorage(storage);
        return validator;
    }

    // Lab assumes CAS Server has user alice.
    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}unused-by-cas")
                .roles("USER")
                .build());
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
            ServiceProperties props,
            Cas20ProxyTicketValidator validator,
            UserDetailsService users) {

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(props);
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        provider.setKey("cas-proxy-demo-provider");
        return provider;
    }

    @Bean
    SecurityContextRepository contextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            ServiceProperties props,
            CasAuthenticationProvider provider,
            ProxyGrantingTicketStorage storage,
            SecurityContextRepository repo,
            @Value("${app.cas.login-url}") String loginUrl,
            @Value("${app.cas.proxy-receptor-path}") String receptor)
            throws Exception {

        CasAuthenticationEntryPoint entryPoint =
            new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(loginUrl);
        entryPoint.setServiceProperties(props);

        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setServiceProperties(props);
        filter.setFilterProcessesUrl("/login/cas");
        filter.setProxyReceptorUrl(receptor);
        filter.setProxyGrantingTicketStorage(storage);
        filter.setAuthenticationManager(new ProviderManager(provider));
        filter.setSecurityContextRepository(repo);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/cas-error",
                    "/signed-out").permitAll()
                // CAS Server must GET the receptor WITHOUT a web session.
                .requestMatchers("/login/cas/proxyreceptor")
                    .permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .securityContext(sec -> sec
                .securityContextRepository(repo))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true));

        // Add the CAS filter into SecurityFilterChain once only.
        // Do NOT expose CasAuthenticationFilter as a @Bean or Boot will auto-register a duplicate Servlet Filter.
        http.addFilterAt(filter, CasAuthenticationFilter.class);
        return http.build();
    }
}
```

**Key points in the Spring code:**

- `setProxyCallbackUrl(callback)` configures the **absolute HTTPS URL** that the validator sends to CAS as `pgtUrl`.
- `setProxyReceptorUrl(receptor)` configures the **local relative path** intercepted by `CasAuthenticationFilter`.
- **The exact same `storage` instance** is passed to both `Cas20ProxyTicketValidator` and `CasAuthenticationFilter`; if instances differ, the client cannot find the PGT by PGTIOU.
- `ServiceProperties.service` remains `https://app.example.org/login/cas`. It is not replaced by the receptor URL.
- `setFilterProcessesUrl("/login/cas")` still handles the browser ST return.
- Marking the receptor `permitAll` lets CAS call it **without a login cookie**. The CAS filter must still match that URL and return **200**; `permitAll` alone **does not create an endpoint**.
- Because CAS sends the PGT in a GET query string, the endpoint must avoid **caching, logging, analytics, and verbose request tracing**, and never render HTML containing secrets.
- `new ProxyGrantingTicketStorageImpl()` is for labs only; Spring Security documentation warns **not to use in-memory storage in production** and notes expired tickets must be cleaned up.
- The demo `UserDetailsService` returns user `alice` with a local role; the `{noop}unused-by-cas` password is never used as a CAS credential. This is a test fixture, not a production user directory.
- `http.addFilterAt(...)` registers the filter **inside the Spring Security chain** without declaring an independent Filter `@Bean` that Spring Boot would auto-register a second time.
- `setAuthenticateAllArtifacts(false)` is the safe setting when App A **only accepts STs** and **requests PTs outbound**. If App A **also accepts inbound PTs**, you must configure `authenticateAllArtifacts` and `ServiceAuthenticationDetailsSource` per docs with a proxy chain allowlist and appropriate stateless ticket cache.
- This is Spring configuration **inside a project with dependencies already present**, not a standalone Java 17 program runnable with plain `javac`.

**Version check requirement:** `CasAuthenticationFilter.setProxyReceptorUrl(String)` and `setProxyGrantingTicketStorage(...)` exist in the Spring Security 6.5.x Javadoc; when upgrading to 7.x, string-to-`RequestMatcher` handling changes. Consult the migration guide/version Javadoc and run integration tests rather than assuming this source compiles unchanged across every major version.

### 7.4. Minimal Spring Boot Application and Controller

File `src/main/java/com/example/casproxy/CasProxyDemoApplication.java`:

```java
package com.example.casproxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasProxyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CasProxyDemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/casproxy/DemoController.java`:

```java
package com.example.casproxy;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "CAS Proxy lab");
    }

    @GetMapping("/reports")
    public Map<String, String> reports(Authentication authentication) {
        return Map.of(
            "message", "Authenticated with CAS",
            "user", authentication.getName());
    }

    @GetMapping("/cas-error")
    public Map<String, String> casError() {
        return Map.of("status", "CAS authentication failed");
    }

    @GetMapping("/signed-out")
    public Map<String, String> signedOut() {
        return Map.of("status", "Local session ended");
    }
}
```

**Do not create `@GetMapping("/login/cas/proxyreceptor")`** in this controller. The receptor endpoint must be handled by `CasAuthenticationFilter`'s built-in proxy receptor logic—never add an MVC route that fakes a 200 without storing the PGT. If the receptor filter is not matching, the CAS callback should **fail** so the integration team fixes the path instead of masking it behind a fallback controller.

### 7.5. Reading and Using the PGT on Service A: Never Read Directly from the Callback

Once ST validation succeeds, `CasAuthenticationToken` carries the corresponding CAS assertion. Spring CAS samples show obtaining a PT through the authenticated token's CAS assertion principal:

```java
// Integration snippet INSIDE a CAS-authenticated application,
// not a standalone REST controller or plain Java class.
CasAuthenticationToken token =
    (CasAuthenticationToken) authentication;

String targetService = "https://api.example.org/reports";
String proxyTicket =
    token.getAssertion().getPrincipal()
        .getProxyTicketFor(targetService);
```

**Only execute when** the caller is genuinely CAS-authenticated, the assertion/PGT is properly bound, target service B is permitted, the CAS proxy facility completed PGT issuance, and your CAS client version supplies this API. If no PGT is present, the method may fail or return no PT depending on implementation; the app must **refuse to call B or return a controlled error**, never falling back to a username HTTP header or copying an old ST.

The new PT is bound to `targetService`. Service B must use `/cas/proxyValidate` to validate the PT and **whitelist A's proxy chain**, rather than trusting strings merely starting with `PT-`. If B accepts stateless tickets across calls, design proper single-use validation/caching per Spring docs; never assume unlimited PT replay.

**Permissions note:** A verified CAS ST/PT does not authorize A to read every user's or tenant's data. B still must map the principal and check scopes/entitlements/record ownership per business policy.

## 8. Certificates: Testing the TLS Path from the CAS Server's Perspective

Engineers often debug on a laptop and report `curl OK`, yet a laptop has a different truststore, DNS, and network from the CAS Server. Always test **from where the CAS HTTP client actually runs** (the CAS container/pod/VM), with appropriate permissions.

### 8.1. Commands to Verify Certificate, Hostname, and Chain

**Check on a host with OpenSSL**:

```bash
openssl s_client \
  -connect app.example.org:443 \
  -servername app.example.org \
  -showcerts \
  -verify_return_error </dev/null
```

Verify `Verify return code: 0 (ok)` against the host's OpenSSL truststore; inspect the Subject Alternative Name, chain, and dates. **Note:** This machine's OpenSSL trust bundle may differ from the CAS JVM truststore; `openssl OK` **is not sufficient** to prove the CAS Java client will succeed.

**Inspect the official certificate file from the HTTPS terminator**:

```bash
keytool -printcert -file app-tls-server.crt
```

Verify `Owner/Issuer`, `Valid from...until`, SHA-256 fingerprint, and SAN. `keytool -printcert` only reads the cert—it **does not test whether the CAS truststore has the right root/intermediate or whether the callback is reachable**.

**Test HTTP callback reachability from CAS**:

```bash
curl -i --max-time 10 https://app.example.org/login/cas/proxyreceptor
```

A GET without `pgtId`/`pgtIou` may validly return an error due to missing parameters, since the receptor only serves real CAS callbacks. **Never treat a parameterless 200 from curl as sufficient**; test a real callback when CAS issues a PGT. Never pass `-k`/`--insecure` to “fix” certificate validation, as that bypasses the critical check.

### 8.2. CAS JVM Truststore

If the callback TLS certificate is issued by a private enterprise CA, the CAS team may need to import approved CA certificates/chains into the CAS truststore. Example creating a **dedicated truststore** in a test environment:

```bash
keytool -importcert \
  -alias corp-proxy-callback-root \
  -file corp-root-ca.crt \
  -keystore cas-proxy-truststore.p12 \
  -storetype PKCS12
```

Import a root CA **only after verifying its fingerprint and ownership out-of-band**. Alias and file names are illustrative. The command may prompt for a truststore password; never record plaintext passwords in shell history or repositories. **Creating this truststore does not automatically make CAS use it**: configure CAS HTTP client/JVM trust settings for your deployed version, restart/reload as needed, and test the callback.

**Minimum rules:**

- Prefer certificates issued by a CA already trusted in the CAS trust chain; avoid unnecessary trust anchors.
- When using a private CA, restrict scope and manage CA/cert lifecycles with auditing.
- Never import App A's private key into the CAS Server; CAS needs only **public trust anchors** to verify TLS.
- Never disable chain validation/hostname verification or set `trustAll=true` to obtain a PGT.
- If a cert expired or has the wrong SAN, **fix the certificate/hostname**, never skew clocks or spoof DNS.
- Keep the truststore where **CAS trusts A's callback** distinct from the truststore where **A trusts the CAS validation endpoint**.

### 8.3. During Certificate Rotation

The HTTPS callback certificate must be renewed **before expiration**, ensuring CAS trusts the new chain:

```text
T0: CAS trusts old CA chain; callback serves cert C_old
T1: CAS already trusts required chain/CA for C_new (if CA changes)
T2: Ingress deploys C_new with valid SNI/SAN
T3: CAS callback HTTPS GET 200, PGTIOU correlation PASS
T4: Remove old root/chain trust no longer needed per policy
```

This is **TLS certificate rotation**, not an IdP SAML signing certificate rollover. Never apply “accept two SAML signing keys” logic to bypass HTTPS PKIX.

If CAS's CA truststore is not updated before the ingress switches certs, PGT issuance can fail abruptly even while browser SSO into App A keeps working. **The contrast between “ST login OK” and “PGT callback FAIL” pinpoints the failure layer.**

## 9. Endpoint from CAS Network to App A: Network, DNS, and Ingress

The CAS HTTP client must reach `pgtUrl` from the CAS pod/VM itself:

- DNS for `app.example.org` must resolve to the IP/load balancer reachable from CAS.
- Firewalls, network policies, egress proxies, and service meshes must allow CAS → A TCP 443.
- The ingress listener must present the right TLS cert for SNI `app.example.org`.
- Path `/login/cas/proxyreceptor` must route to the app instance whose `CasAuthenticationFilter` handles the receptor.
- Query parameters `pgtId` and `pgtIou` must be preserved—never stripped, mutated, truncated, or renamed.
- WAF rules must not block valid ticket prefixes/patterns or serve CAPTCHA challenges.
- Requests from CAS carry **no browser session cookie**, so they must not redirect to CAS login.
- A healthy response must be HTTP 200, ideally with `Cache-Control: no-store` and no raw query logging.
- Timeouts/connect/read limits must be bounded, not infinite; failures must fail closed rather than pulling a PGT from elsewhere.

### 9.1. SameSite/CSRF Are Related, Not the Root Cause

The CAS→App A callback is a **server-to-server GET**, independent of browser SameSite cookies. Default CSRF filters typically guard unsafe methods like POST/PUT/DELETE; a GET callback should not require a browser CSRF token. However:

- If the app has custom middleware rejecting any GET without CSRF or a user session, the callback will fail.
- If the ingress enforces form login/OIDC auth in front of Spring, the CAS Server will get 302/401 instead of 200.
- If a WAF blocks queries containing `pgtId`/`pgtIou`, configure a **narrow** exception for that endpoint and CAS source per policy rather than disabling the entire WAF/CSRF.
- Even though the method is GET, **storing a PGT** is a CAS-mandated state change; it still demands anti-caching, source/correlation checks, and rate limiting rather than relying on “GET is safe” as a security argument.

### 9.2. mTLS and IP Allowlists: Defense-in-Depth, Not a Substitute for PKIX

At minimum, the CAS Protocol requires CAS to verify the **callback's TLS server certificate**. You can harden further with:

- mTLS between the CAS Server and App A's ingress, if the CAS HTTP client supports client certificates.
- Source IP allowlists or private network/mesh authentication tied to managed CAS egress.
- Rate limiting and network policies on the receptor.
- Anomaly monitoring: callbacks missing an IOU, duplicate IOUs, storage misses, or unexpected callers.

However, **do not claim the CAS protocol always mandates mTLS**: client authentication on the callback is deployment-specific. An IP allowlist alone is also weak if NAT/shared IPs change. Even with mTLS, you must still match `PGTIOU` in the validation response against storage and check ticket/service/issuer per the CAS protocol.

## 10. PGT Storage, Callback Ordering, and Correlation

A surprising detail is that the CAS callback carrying the **PGT** arrives before or while `/serviceValidate` returns **PGTIOU** to App A. The CAS client needs shared storage to pair them:

```text
CAS --> GET A /proxyreceptor?pgtId=PGT-123&pgtIou=PGTIOU-abc
        storage.put("PGTIOU-abc", "PGT-123")

CAS --> /serviceValidate response:
        <cas:proxyGrantingTicket>PGTIOU-abc</cas:proxyGrantingTicket>

App A:
        storage.get("PGTIOU-abc") -> "PGT-123"
        uses PGT-123 to call CAS /proxy
```

PGTIOU cannot be reversed into PGT in reasonable time; it is a separate correlation handle. **Never pass `PGTIOU` as the `pgt` credential when calling CAS `/proxy`.**

### 10.1. One Shared Storage Everywhere

Spring Security specifies that `CasAuthenticationFilter` and `Cas20ProxyTicketValidator` must reference **the exact same `ProxyGrantingTicketStorage`**. A single-JVM lab can use an in-memory instance. Across 3 pods, however:

```text
            HTTPS Load Balancer
                   |
           +-------+-------+
           |               |
       Pod A             Pod B
    /serviceValidate     /proxyreceptor?pgtIou=...
           |               |
       Local Map A       Local Map B
        [empty]         [PGTIOU -> PGT]
           |
           +-- PGT lookup MISS!
```

**Production must solve HA:** a secure distributed PGT store (or engineered and tested session routing/callback affinity, bearing in mind plain sticky sessions may not steer CAS server-side callbacks). The cache/store should provide:

- TTL aligned with PGT validity/policy, expired entry cleanup, and capacity caps.
- Encryption and restricted access; a PGT is a sensitive bearer credential.
- Namespacing by CAS Server/issuer and application/tenant to avoid collisions and cross-tenant leaks.
- Protection against races/duplicate callbacks, preventing unauthorized overwrites of active IOUs.
- Atomic correlate/consume or bounded retrieval matching library semantics.
- Handling callbacks arriving before or after the validation response, with bounded retries/backoff in the service layer if APIs exhibit lag—never fabricating a PGT.
- Resilience to rolling deploys, node restarts, and policy-compliant cache eviction.
- Revocation/clearing of ticket state on user logout or incidents per CAS protocol and risk level—never retaining PGTs indefinitely.
- Auditing via request IDs and storage hit/miss counters, **never logging PGT/ST/PT/raw IOU**.

**Version warning:** `ProxyGrantingTicketStorageImpl` implementations can be in-memory maps. Spring Security docs explicitly note that production clusters should not rely on in-memory implementations and need `cleanup()` to purge expired PGTs. Choose a distributed implementation matching your Apereo CAS Client version—never instantiate the same bean class independently in each pod's local memory.

### 10.2. Callback Is Not “Proof of User Login”

The CAS callback proves only the PGT handoff between CAS and App A; it **does not replace** App A validating the ST for the right service and establishing principal/session state. A request carrying `pgtId`/`pgtIou` query parameters must never create a local user `Authentication` or assign roles from a PGT string.

All of the following must hold:

1. ST/PT was validly verified by CAS for the exact service.
2. CAS HTTPS/PKIX callback succeeded and a PGTIOU was returned.
3. PGTIOU matches the right PGT in the application/service context's storage.
4. App A is authorized to proxy in the CAS service registry.
5. App B accepts the proxy chain and the PT issued specifically for its target service.
6. B's authorization verifies permissions on the requested resource and tenant.

## 11. Standalone Java 17: Modeling PGTIOU Correlation and Target Service Protection

This example **simulates only correlation and policy**—it makes no CAS calls, parses no XML, and creates no real TLS or PGTs. It shows learners that **IOU is not PGT**, why HTTPS callbacks and target allowlists matter, and why a forged or already-consumed IOU must be rejected.

File `PgtCallbackPolicyDemo.java`:

```java
import java.net.URI;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class PgtCallbackPolicyDemo {

    static final String EXPECTED_CALLBACK =
        "https://app.example.org/login/cas/proxyreceptor";

    static final Set<String> ALLOWED_TARGETS = Set.of(
        "https://api.example.org/reports");

    private final Map<String, String> tickets = new HashMap<>();

    static boolean approvedCallback(String url) {
        try {
            URI uri = URI.create(url);
            return "https".equals(uri.getScheme())
                && EXPECTED_CALLBACK.equals(uri.toString())
                && uri.getUserInfo() == null
                && uri.getFragment() == null;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    // Simulates a CAS callback delivered over a verified connection.
    // Do NOT use this method as a real HTTP endpoint.
    void storeFromVerifiedCallback(
            String pgtIou, String pgt, boolean trustedTransport) {
        if (!trustedTransport || pgtIou == null || pgt == null
                || !pgtIou.startsWith("PGTIOU-")
                || !pgt.startsWith("PGT-")
                || pgtIou.isBlank() || pgt.isBlank()) {
            return;
        }
        tickets.putIfAbsent(pgtIou, pgt);
    }

    String takePgt(String validatedIou, String targetService) {
        if (validatedIou == null
                || !ALLOWED_TARGETS.contains(targetService)) {
            return "DENIED";
        }
        String pgt = tickets.remove(validatedIou);
        return pgt == null ? "MISSING" : "READY";
    }

    public static void main(String[] args) {
        PgtCallbackPolicyDemo demo = new PgtCallbackPolicyDemo();

        System.out.println("httpsCallback=" +
            approvedCallback(EXPECTED_CALLBACK));
        System.out.println("httpCallback=" +
            approvedCallback(
                "http://app.example.org/login/cas/proxyreceptor"));
        System.out.println("wrongHost=" +
            approvedCallback(
                "https://evil.example.org/login/cas/proxyreceptor"));

        demo.storeFromVerifiedCallback(
            "PGTIOU-one", "PGT-one", true);

        System.out.println("allowedLookup=" +
            demo.takePgt(
                "PGTIOU-one", "https://api.example.org/reports"));
        System.out.println("replayedIou=" +
            demo.takePgt(
                "PGTIOU-one", "https://api.example.org/reports"));

        demo.storeFromVerifiedCallback(
            "PGTIOU-two", "PGT-two", true);
        System.out.println("wrongTarget=" +
            demo.takePgt(
                "PGTIOU-two", "https://evil.example.org/data"));
        System.out.println("correctTargetAfterDenied=" +
            demo.takePgt(
                "PGTIOU-two", "https://api.example.org/reports"));

        demo.storeFromVerifiedCallback(
            "PGTIOU-three", "PGT-three", false);
        System.out.println("untrustedCallback=" +
            demo.takePgt(
                "PGTIOU-three", "https://api.example.org/reports"));
    }
}
```

Compile and run on JDK 17+:

```bash
javac --release 17 PgtCallbackPolicyDemo.java
java PgtCallbackPolicyDemo
```

Fixed stdout:

```text
httpsCallback=true
httpCallback=false
wrongHost=false
allowedLookup=READY
replayedIou=MISSING
wrongTarget=DENIED
correctTargetAfterDenied=READY
untrustedCallback=MISSING
```

**Explanation of each test case:**

- `httpsCallback=true`: the expected URL uses HTTPS and matches the exact approved callback.
- `httpCallback=false`: HTTP cannot be used as `pgtUrl`.
- `wrongHost=false`: a different host sharing the same path is not an approved callback.
- `allowedLookup=READY`: PGTIOU was delivered via a **simulated trusted callback**, its PGT sits in the map, and the target service is allowlisted.
- `replayedIou=MISSING`: the demo consumes the mapping once to illustrate correlation; in a real CAS Client, the PGT itself can request **multiple PTs**, so do not infer `PGT single use`.
- `wrongTarget=DENIED`: holding a PGT does not grant access to arbitrary target services.
- `correctTargetAfterDenied=READY`: a denied target lookup does not consume the mapping in the demo.
- `untrustedCallback=MISSING`: data from an unverified source is never admitted into storage.

**Explicit limitations:** `approvedCallback` only validates URI/string against an allowlist—it performs **no TLS/PKIX** checks, issuer checks, or certificate verification. `trustedTransport` is a **simulated flag** and must never come from a client-supplied header. `storeFromVerifiedCallback` lacks distributed TTL/expiry/cleanup/race protection and must not be used as a production implementation. In reality, Spring CAS filters/validators handle the ticket protocol, CAS Server enforces HTTPS PKIX, and target/proxy-chain policies live on server and client per contract.

## 12. PT for Service B: A Successful Callback Is Not the End

After App A obtains the PGT, it calls:

```http
GET /cas/proxy?pgt=PGT-EXAMPLE&targetService=https%3A%2F%2Fapi.example.org%2Freports HTTP/1.1
Host: sso.example.org
```

CAS returns a PT if the PGT is valid and service B is authorized. A passes the PT to B per protocol; B must verify:

- The `PT` is unused, unexpired, and issued by the trusted CAS Server.
- The `service` used to validate the PT **matches the `targetService` used when issuing it**.
- The proxy chain in the response lists the proxies traversed; B accepts only approved chains.
- The user principal/attributes are CAS-verified; B maps them to a local account and tenant/permissions.
- TLS between A and B is trusted; PT/PGT are never logged.
- Never accept a `PT` merely because App A sent `X-User: alice` or because A's callback returned 200.

### 12.1. Allowed Proxy Chains—Never Enable `acceptAnyProxy` Arbitrarily

CAS `/proxyValidate` can return `<cas:proxies>`. Operators of B must restrict **which proxying services** may represent a user:

```text
Allowed proxy:
  https://app.example.org/login/cas/proxyreceptor

Not allowed:
  https://attacker.example.org/callback
  https://other-tenant.example.org/callback
  * (any proxy)
```

Spring CAS samples sometimes show `Cas20ProxyTicketValidator` with `acceptAnyProxy=true` for demos, which is **not recommended for production**. Configure exact allowed proxy chains for your CAS client version and test multi-hop chain ordering. Under CAS 2/3, the proxy list is returned most-recent-first; verify your CAS client's exact matcher semantics before writing rules.

### 12.2. Why Should PGTs Not Live Forever in Storage?

The CAS protocol defines PGTs as reusable to mint **multiple PTs**, yet they must expire or be revoked per policy—especially when the user's CAS SSO session ends. Applications also need local logout/session revocation and proper storage cleanup. Never treat a PGT as a perpetual secret or persist it inside long-retention job queues, URLs, or logs.

**When a user logs out locally on A:** That does not automatically log out the CAS TGT/TGC or revoke all PGTs/PTs. In high-security use cases, design explicit revocation for proxy credentials and access sessions across CAS Server and apps rather than assuming `HttpSession.invalidate()` revokes the PGT at CAS.

## 13. Requirements for Publishing a Proxy Callback Endpoint Safely

Because the CAS Server must call App A, the callback must be **reachable**; however, “reachable” does not mean “wide open to the entire Internet without controls.”

A production design should include:

1. **HTTPS reachable by CAS (public or private)** with a fixed FQDN and trusted certificate chain.
2. **A canonical URL** configured server-side, never derived from untrusted `Host`/`Forwarded` headers.
3. **CAS service registry** permitting App A to perform proxy authentication and allowing `pgtUrl` per policy.
4. **GET callback** accepting `pgtId`/`pgtIou` query parameters, handled by the official filter, returning 200.
5. **No browser authentication**/form login required on the receptor; optionally add mTLS or network IP policy where supported.
6. **No open redirects/302** on the receptor; never render the PGT in response bodies.
7. **Zero logging** of raw queries, tickets, IOUs, or secret-bearing bodies; apply `Cache-Control: no-store` and `Referrer-Policy` as appropriate.
8. **Secret lifecycle controls** for PGT storage: encrypted at rest/in transit, TTL, cleanup, namespacing, replication, and access control.
9. **Request size and rate limits** to prevent DoS or storage poisoning.
10. **Anti-spoofing correlation**: never treat a GET with `pgtId` as proof of an authenticated user; require correlation with a pending ST/PT validation and CAS PGTIOU response.
11. **Egress/ingress allowlisting** so only authorized CAS Servers can reach the receptor where feasible and HA-tested.
12. **Monitoring** for TLS expiry, 200 callback rates, PGT issuance rates, storage misses, and proxy ticket failures.
13. **Tenant isolation:** never share PGT namespaces across tenants/issuers in multi-tenant setups with separate trust boundaries.
14. **Change approval** for callback URLs, certs, DNS, load balancers, proxy policies, and the CAS server truststore.
15. **Integration tests** executed from the real CAS Server, not just curl from a laptop.

**Never rely on `robots.txt` or obscurity as security controls.** This is a server-to-server protocol endpoint requiring genuine cryptographic verification and network controls.

## 14. Mandatory Test Matrix for HTTPS / PGT Callbacks

Each test case requires a **fresh valid Service Ticket from test CAS**, avoiding reused STs that skew results. For TLS failure tests, use a dedicated staging environment and test certificates—**never alter a production truststore** to trigger failures.

| Test Case | Scenario | Expected Result |
| --- | --- | --- |
| **Happy path** | App A validates ST with valid HTTPS `pgtUrl`, CAS GETs receptor 200, store saves PGT | CAS returns PGTIOU, client retrieves right PGT and can request PT for B |
| **`pgtUrl` omitted** | App A performs normal ST validation only | No PGTIOU/PGT; ST login may still succeed if CAS policy allows |
| **HTTP `pgtUrl`** | `http://app.example.org/...` | CAS rejects proxy callback, issues no PGT |
| **Expired certificate** | App A's TLS server cert expired | PKIX/handshake fails, no PGT issued |
| **Not-yet-valid certificate** | Future `NotBefore` | PKIX/handshake fails |
| **Untrusted self-signed cert** | CAS truststore lacks trust anchor | Rejected |
| **Missing intermediate** | Ingress sends incomplete chain | PKIX path building fails or rejected |
| **SAN hostname mismatch** | URL is app.example.org but cert is for other.example.org | Hostname validation fails |
| **Wrong SNI cert** | LB returns default cert of another host | TLS fails hostname check |
| **CAS custom CA not imported** | Local browser trusts it, CAS JVM does not | CAS callback fails |
| **WAF blocks GET** | Query `pgtId/pgtIou` blocked | CAS does not get 200, PGT issuance fails |
| **302 to login page** | Receptor guarded by browser auth gateway | CAS does not get valid receptor 200; fails or invalid redirect |
| **404 wrong path** | `proxyCallbackUrl` mismatches `proxyReceptorUrl`/context | PGT not saved, no PGT issued |
| **401/403 missing cookie** | Security filter demands local user session | CAS callback fails; receptor needs an independent protocol route |
| **Timeout** | CAS cannot connect to A | No PGT issued, alert on CAS→A network |
| **Fake 200 without storing PGT** | MVC fallback controller replaces filter | CAS may return PGTIOU, but app storage misses; cannot request PT |
| **Two separate PGT stores** | Validator and Filter use unshared instances | PGTIOU correlation miss |
| **Cluster node A/B** | Callback hits pod B; ST validation runs on pod A | Must find PGT via distributed store or engineered routing |
| **Duplicate callback** | CAS retries/duplicates query | Must not create duplicate records or corrupt mapping |
| **Unknown PGTIOU** | Client receives IOU absent from store | Never calls `/proxy` with IOU; fails closed |
| **PGT leaked** | Raw query logged in ingress access log | Tests redaction/no-store policy; triggers incident if real |
| **Target B outside allowlist** | Requests PT for unknown service | Denied by CAS service policy/app allowlist |
| **PT sent to target C** | PT issued for B, validated by C | CAS rejects due to target service mismatch |
| **Disallowed proxy chain** | B receives PT from unapproved proxy A | B rejects even though CAS PT crypto/protocol check passed |
| **TGT logged out** | User logs out of CAS, invalidating PGT per protocol | PGT cannot mint new PTs after revocation |
| **Local logout on A** | Only A's `HttpSession` invalidated | Do not assume PGT/TGT revoked at CAS; handle per policy |
| **CA rotation** | App A cert/CA rotated before CAS trust updates | Controlled failure; recovers once trust chain aligns |
| **IdP SAML cert rotated** | SAML signing cert changed in another system | Does not affect CAS TLS callback PKIX if A's TLS cert is unchanged |

A test PASSES only when **the PGTIOU in the CAS validation response matches the stored PGT**, not merely when the browser finally sees a 200 page on App A. Normal ST login may succeed even when PGT issuance fails under certain configs/versions; therefore include explicit assertions for “PGT received, PT issued, and B accepted.”

### 14.1. Gathering Evidence Without Leaking Tickets

In staging/test logs, record only:

```text
eventId
utcTimestamp
casServerId
registeredServiceId
callbackHostAndPath  (no raw query)
tlsValidationResult
tlsPeerCertificateFingerprintSHA256
callbackHttpStatus
pgtIssuanceStatus
storageCorrelationStatus
targetServiceId
proxyChainPolicyDecision
podOrRegion
testCaseId
```

Never log:

```text
?ticket=ST-...
?pgtId=PGT-...&pgtIou=PGTIOU-...
/cas/proxy?pgt=PGT-...
PT-...
Session cookie/JSESSIONID
CAS TGT/TGC
Java truststore passwords or TLS private keys
```

If correlating events across CAS and apps is necessary, use controlled request/trace IDs or policy-governed HMAC pseudonyms—never raw tokens. Just because the PGT travels in a GET query string does **not** permit forwarding query strings into analytics pipelines.

## 15. Evidence-Ordered Diagnostics

### 15.1. ST Login Succeeded, Yet No PGT Exists

```text
1. Is App A actually using Cas20ProxyTicketValidator?
       |
       +-- No --> ST login only; configure the proxy validator properly.

2. Does Validator set the right HTTPS proxyCallbackUrl (pgtUrl)?
       |
       +-- No --> fix canonical URL; never take from user headers.

3. Does CAS Server allow service A to proxy and approve the callback URL?
       |
       +-- No --> update service registry with approval.

4. Can CAS resolve DNS and open TCP 443 to the callback?
       |
       +-- No --> network/DNS/egress/ingress.

5. Does the CAS -> A TLS handshake pass PKIX/cert/SAN/validity?
       |
       +-- No --> fix chain, CA trust, hostname, expiry.

6. Does GET /proxyreceptor?pgtId&pgtIou reach Spring?
       |
       +-- No --> LB, WAF, path rewrite, timeout.

7. Does CAS observe a direct HTTP 200 from the receptor filter?
       |
       +-- No --> 302 login, 401/403, 404, wrong matcher.

8. Do Validator and receptor share the exact same PGT store?
       |
       +-- No --> bean/HA/namespace/TTL.

9. Does CAS validation response carry PGTIOU? Does store hold the matching PGT?
       |
       +-- No --> inspect CAS proxy issuance/IOU correlation.

10. Does App A call /proxy for a PT and does B accept it?
       |
       +-- No --> PGT validity, targetService, proxy chain, authz.
```

### 15.2. Common Errors Table

| Operational Error | Symptom | Resolution |
| --- | --- | --- |
| `INVALID_PROXY_CALLBACK` | CAS reports pgtUrl/cert/endpoint failure | Check HTTPS, PKIX, callback URL, reachability, and status |
| `UNAUTHORIZED_SERVICE_PROXY` | Service not permitted to proxy | Update CAS service registry with approval; never rename URLs to bypass |
| `INVALID_SERVICE` | ST/PT service mismatch | Compare `ServiceProperties.service` and targetService/validator |
| `INVALID_TICKET` | Fake, expired, or consumed ST/PT | Mint fresh ticket, re-check service; never retry the same ticket |
| `SSLHandshakeException` | TLS cert/trust/cipher error | Check CA, chain, hostname, protocol from CAS runtime |
| `SunCertPathBuilderException` | CAS cannot build PKIX chain | Add proper intermediate/CA trust; never trust-all |
| Callback 302 to CAS login | Filter chain/gateway requires local session | Allow server-to-server receptor per policy; filter returns 200 |
| Callback 401/403 | WAF/SecurityFilterChain auth blocks it | Review matchers and ingress ACLs; never disable global security |
| Callback 404 | Wrong path/context prefix/route | Align absolute proxyCallbackUrl and local proxyReceptorUrl |
| HTTP 200 but no PGT | MVC placeholder returns 200, filter never stores | Remove fake controller; configure CasAuthenticationFilter/storage |
| PGTIOU present, PGT missing | Separate store instances, different pods, short TTL, race | Shared distributed store with proper cleanup/replication |
| PGT exists, PT request fails | Expired/revoked PGT, CAS target policy | Inspect `/proxy` response and authorized target services |
| B rejects PT | Disallowed PT scope/target/chain | `/proxyValidate` exact service, proxy allowlist, and authz |
| Fails after cert deploy | Inconsistent ingress cert/SNI/chain | Check every LB backend reachable from CAS Server |
| Fails only from CAS pod | CAS DNS/egress/truststore differs from laptop | Test from CAS runtime/namespace |
| PGT leaked in access log | Reverse proxy logs raw query | Redact immediately, treat as incident if live; fix log pipeline |
| Client manually GETs callback with fake PGT | Publicly reachable endpoint | Rely on CAS validation+IOU, add network/mTLS controls where feasible |
| Rollback breaks proxying | Config mismatch across callback URLs/versions | Roll out configs atomically and run end-to-end PGT regression tests |

**Never attempt dangerous workarounds:** enabling HTTP `pgtUrl`, disabling certificate verification, allowing any proxy chain, storing PGTs in the browser, faking 200s, sending STs to B, or relaxing target service policies. Every one of those defeats CAS Proxy's security model.

## 16. Review Questions and Answers

**Q1.** App A receives STs at `https://app.example.org/login/cas`. For CAS to issue a PGT via the receptor, how should `ServiceProperties.service` and `proxyCallbackUrl` be configured?

**Answer:** `ServiceProperties.service=https://app.example.org/login/cas`; `proxyCallbackUrl=https://app.example.org/login/cas/proxyreceptor`. The two URLs serve different purposes; local `proxyReceptorUrl=/login/cas/proxyreceptor`.

**Q2.** CAS calls `pgtUrl` over HTTPS, but App A's certificate is issued by an internal CA missing from the CAS truststore. Browser login to A still succeeds. Is a PGT issued?

**Answer:** Per CAS Proxy PKIX requirements, CAS cannot establish trust with the callback and **must not issue a PGT**; depending on CAS client/Server implementation, ST login alone may still succeed. Configure the truststore **on the CAS side** after verifying the CA/cert per policy.

**Q3.** CAS sends `GET /proxyreceptor?pgtId=...&pgtIou=...` and the server returns 302 to `/login` because there is no cookie. Does the callback count as successful?

**Answer:** No. The CAS Server is an HTTP client without a browser session; the protocol endpoint must be handled by the filter and return 200. Fix the filter chain/gateway—never disable TLS validation.

**Q4.** App A sees `<cas:proxyGrantingTicket>PGTIOU-xyz</...>`. Can `PGTIOU-xyz` be passed as the `pgt` parameter to CAS `/proxy`?

**Answer:** No. You must query `ProxyGrantingTicketStorage` by IOU to retrieve the **real PGT** delivered by CAS via the callback.

**Q5.** In a cluster, the CAS callback hits pod B while App A awaits `/serviceValidate` on pod A. Each pod uses its own in-memory `ProxyGrantingTicketStorageImpl`. What happens?

**Answer:** Pod A may fail to find the IOU/PGT even though the CAS callback to B returned 200. Production should use shared/distributed ticket storage with proper tenant namespacing/TTL and cross-node tests.

**Q6.** Which certificate does the CAS Server verify when calling the PGT callback: the SAML IdP signing certificate, the CAS Server's certificate, or App A's TLS certificate?

**Answer:** **App A's TLS server certificate** presented by the ingress/callback endpoint, checked by the CAS TLS client for chain/PKIX/hostname/validity. Conversely, App A verifies the CAS Server's TLS certificate on `/serviceValidate`—that is the opposite direction.

**Q7.** App A holds a PGT and wants to read API B. Can it simply send `X-User: alice` instead of a PT?

**Answer:** No. A uses the PGT to request a PT for exact `targetService=B` from CAS; B verifies the PT via `/proxyValidate`, validates the proxy chain, and enforces business permissions.

**Q8.** CAS may follow HTTP 302 on callbacks, so should the receptor just return 302 to login and end at a 200 page?

**Answer:** No. A 200 from a login page does not prove the PGT was saved. Have the receptor return 200 directly upon processing `pgtId/pgtIou`, without relying on browser sessions or redirects.

**Q9.** Someone can hit the callback endpoint from the Internet and send arbitrary `pgtId`/`pgtIou`. Should that count as an authenticated CAS user?

**Answer:** No. The callback only delivers a PGT; it is valid only when CAS Server verified an ST/PT, the validation response contains the matching IOU, the app holds the ticket mapping, and proper network/trust controls apply. Never create a user session from raw callback queries.

**Q10.** Should `ServiceProperties.authenticateAllArtifacts=true` be enabled to fix a 404 on the CAS callback?

**Answer:** No. `authenticateAllArtifacts` supports receiving Proxy Tickets across arbitrary URLs/stateless clients; a 404 callback requires fixing `proxyReceptorUrl`/filter matching/ingress and PGT storage. Enabling it broadly increases attack surface.

## 17. Pre-Production Handover Checklist

- [ ] CAS proxy use case is approved; App A genuinely needs to obtain PTs to call Service B.
- [ ] ST/PGT/PGTIOU/PT/TGT and sessions are clearly separated; PGTs are never stored in or sent to the browser.
- [ ] `ServiceProperties.service` = public ST callback, while `proxyCallbackUrl` = **absolute HTTPS URL** of the proxy receptor.
- [ ] `CasAuthenticationFilter.proxyReceptorUrl` = local matcher for the proxy receptor, distinct from `filterProcessesUrl` receiving STs.
- [ ] CAS `/serviceValidate` receives exact `ticket`, `service`, and `pgtUrl`; CAS GET callback delivers `pgtId`/`pgtIou`.
- [ ] CAS Server requires HTTPS and verifies PKIX/trust/hostname/expiry of the callback certificate; full TLS root/intermediate chain is served.
- [ ] The **CAS→App A** truststore is managed separately from the **App A→CAS** truststore; both directions verified from actual runtimes.
- [ ] CAS service registry authorizes App A to proxy; `pgtUrl` and target B are approved with no allow-all rules.
- [ ] CAS callback requires no browser cookie, no login redirect, and no CAPTCHA; returns 200 upon processing.
- [ ] No fake-200 MVC fallback replaces the CAS filter; the filter is not registered twice.
- [ ] `Cas20ProxyTicketValidator` and `CasAuthenticationFilter` share the same logical `ProxyGrantingTicketStorage` with TTL/cleanup and access controls.
- [ ] Multi-pod/region setups use appropriate shared/distributed PGT storage rather than the in-memory demo.
- [ ] IOU↔PGT correlation is exact and scoped by CAS source/tenant, preventing duplicates and poisoning.
- [ ] Callback HTTPS certificate has exact FQDN SAN, valid dates, accepted algorithms, and CA chain trusted by CAS; verification is never disabled.
- [ ] DNS/firewall/ingress/WAF/forwarded headers and path rewrites are tested from the CAS Server runtime.
- [ ] Ingress TLS certificate rotation has a runbook covering CAS trust updates and PGT integration testing.
- [ ] App A requests PTs for the exact `targetService`; B uses CAS `/proxyValidate` and strict allowed proxy chains.
- [ ] `acceptAnyProxy=true` is not used in production unless under an evaluated, monitored exception policy.
- [ ] Queries containing PGT/PT/ST/IOU, cookies, private keys, or truststore passwords are never logged; responses include `no-store` where appropriate.
- [ ] Alerts exist for non-200 callback statuses, PKIX failures, PGTIOU storage misses, CAS `INVALID_PROXY_CALLBACK`/`UNAUTHORIZED_SERVICE_PROXY`, and PT failures.
- [ ] Failure matrix tested: TLS errors, expired/wrong-SAN/missing-intermediate certs, 302 login, 404, cross-node storage, and unknown proxy chains.
- [ ] Local logout, CAS logout, and deprovisioning have clear credential/session revocation policies without assuming one step revokes everything.
- [ ] All endpoint and proxy URLs come from trusted backend config, never from client-supplied hosts or arbitrary `pgtUrl`.
- [ ] Exact Spring Security and Apereo CAS Client versions are pinned and integration-tested after every upgrade.

**Conclusion:** The proxy callback endpoint is the **server-to-server channel through which CAS delivers a PGT to the application**, not a browser login callback. When App A sends `pgtUrl` during ST validation, CAS **must** establish HTTPS with PKIX/certificate validation of the callback, issue a GET to the receptor with `pgtId` and `pgtIou`, receive HTTP 200, and return **PGTIOU** in the ticket validation response. Spring Security connects both halves via **`Cas20ProxyTicketValidator.proxyCallbackUrl` + `CasAuthenticationFilter.proxyReceptorUrl` + the same `ProxyGrantingTicketStorage`**. Only after successful correlation does App A hold a PGT to request a PT for Service B, and B must still independently verify the PT, proxy chain, and data permissions. Skipping HTTPS/PKIX, storing PGTs on the wrong node, or misconfiguring callback URLs can break proxying or introduce severe vulnerabilities.

## 18. References

1. [CAS Protocol 3.0 Specification – `/serviceValidate`, `pgtUrl`, and `2.5.4 Proxy Callback`](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): HTTPS MUST rules, PKIX/trust chain, GET `pgtId/pgtIou`, 200 OK, PGTIOU correlation, and PGT/PT lifecycles.
2. [Spring Security – CAS Authentication, Proxy Ticket Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `Cas20ProxyTicketValidator`, `proxyCallbackUrl`, `ProxyGrantingTicketStorage`, `proxyReceptorUrl`, proxy chains, and stateless ticket caches.
3. [Spring Security 6.5 Javadoc – CasAuthenticationFilter](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): default `/login/cas` ST callback, proxy receptor, and storage API.
4. [Spring Security 6.5 Javadoc – CasAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html): provider/validator and local user details.
5. [Apereo CAS – Proxy Authentication](https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html): PGT/PT flow, callback authorization in the CAS service registry, CAS HTTP client truststore, and SSL.
6. [Apereo Java CAS Client README – Proxy Callback and Distributed Storage](https://github.com/apereo/java-cas-client/blob/master/README.md): `proxyReceptorUrl`, `proxyCallbackUrl`, `allowedProxyChains`, and clustered PGT storage.
7. [Spring Security – Migration: CAS Proxy Receptor Matching](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/migration-7/web.html): `RequestMatcher` differences when migrating from Spring Security 6 to 7.
8. [Oracle Java 17 – JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): TLS trust managers, X.509 certificate validation, and truststores.
9. [Oracle Java 17 – keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): inspecting and importing public certificates/CA trust anchors.
10. [OWASP TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS configuration, hostname/certificate validation, and channel protection.
11. [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): restricting URL/service callbacks outside trusted allowlists.
12. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): managing credentials in URLs/queries, cookies, caches/logs, and sessions.
