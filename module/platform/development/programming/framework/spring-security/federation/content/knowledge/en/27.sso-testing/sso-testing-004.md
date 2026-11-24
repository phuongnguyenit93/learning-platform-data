# Testing CAS Proxy with Callbacks and Disallowed Proxy Chains

## 1. The Problem: How CAS Proxy Differs from Direct SSO Login

In the **Spring Security - federation** module under **SSO Testing**, **CAS Proxy** allows an application that has already authenticated a user via **Central Authentication Service (CAS)** to call a **downstream service on the user's behalf** without passing the user's password or Ticket Granting Ticket (TGT) to that service. It is a **ticket- and target-service-scoped delegation** mechanism in the CAS protocol, not an ordinary HTTP reverse proxy and not OAuth access-token delegation.

Example enterprise architecture:

~~~text
                       CAS Server
                    https://cas.example.org/cas
                         /login
                         /serviceValidate
                         /proxy
                         /proxyValidate
                            ^
                            |
Browser ---> Portal A ------+---------> Reports API B
            (CAS client,                   (CAS client, validates PT)
             CAS proxy)                    |
                |                          |
                +-- PGT callback <---------+ (CAS Server does not call API B
                    at Portal A                to deliver Portal A's PGT)
~~~

A typical session: the user logs into Portal A via CAS; Portal A receives a **Service Ticket (ST)** and asks CAS to issue a **Proxy-Granting Ticket (PGT)** via a **secure callback**; Portal A uses the PGT to obtain a **Proxy Ticket (PT)** for Reports API B; B calls CAS **`/proxyValidate`** and must decide whether the **entire proxy chain is allowed** before trusting the delegated identity.

**The testing problem has two distinct yet tightly linked focuses:**

1. **PGT Callback:** is it genuinely received from the CAS Server over the right channel, storing `pgtId` secretly, matching the right `pgtIou` to the ticket validation response, and rejecting spoofing/mis-correlation/races/lost callbacks?
2. **Proxy Chain:** in the `/proxyValidate` response, is it evaluated **in full and in exact order**, accepting only approved delegation paths while rejecting unknown, overly long, reversed, or empty chains when a route requires proxying, as well as overly broad `acceptAnyProxy=true` configurations?

This article covers terminology and protocol, trust boundary design, Spring Security/CAS Java Client setup, test diagrams, test matrices, mock and integration/E2E tests, a standalone Java 17 policy simulation, troubleshooting, and an acceptance checklist.

> **Secure by default:** a **PT valid at the CAS Server** is not automatically valid **for accessing Reports API B**. B must still verify the exact `targetService`, the **allowed proxy chain**, local user/account status, and resource permissions. A **PGT callback hitting the right URL** does not by itself prove the caller is the CAS Server without inbound trust or reliable correlation.

## 2. Distinguishing Four Ticket Types and Two Callback Forms

| Concept | Who Holds It / Where It Appears? | Purpose and Lifetime |
| --- | --- | --- |
| **TGT** – Ticket Granting Ticket | Managed by CAS Server; browser holds CAS TGC cookie for the SSO session. | Allows CAS to issue multiple STs during SSO. **Never pass raw TGT to Portal or API B**. |
| **ST** – Service Ticket | Browser is redirected back to Portal A with `ticket=ST-...`. | **One-time** ticket bound to A's `service`; A validates server-to-server with CAS. |
| **PGT** – Proxy-Granting Ticket | Issued by CAS Server to **Portal A** via secure callback or another approved mechanism. | Credential for A to request multiple PTs per targetService; has its own lifecycle and is invalidated by policy/CAS logout. **Never expose to browser**. |
| **PGTIOU** – PGT I Owe You | Same value appears in the CAS callback and the ticket validation response. | **Correlation key** so A locates the exact PGT matching an ST/PT validation. Not a PGT and cannot be used directly to obtain PTs. |
| **PT** – Proxy Ticket | Portal A calls CAS `/proxy?pgt=...&targetService=...` and receives `PT-...`. | **One-time ticket when validated at CAS**, scoped solely to the **target service** such as B. |
| **Proxy chain** | Returned by CAS in `<cas:proxies>` inside the `/proxyValidate` response. | List of **proxy callback URLs** that relayed authentication, with the **most recent proxy closest to the target appearing first**. |

**Never confuse the two callbacks:**

- **Browser → A with ST**: the user returns to A's declared service URL, e.g., `https://portal.example.org/login/cas?ticket=ST-...`; A validates the ticket at CAS.
- **CAS Server → A's PGT receptor**: **server-to-server HTTP GET** to `https://portal.example.org/login/cas/proxyreceptor?pgtId=...&pgtIou=...`, where A must receive and store the PGT in secret storage.

An HTTP reverse proxy/ingress at `portal.example.org` may forward both requests; however, the **CAS proxy chain** is the **sequence of services using PTs**, not the list of CDN/ingress/LB hops in `X-Forwarded-For`.

### 2.1. Not Every Ticket Type Uses the Same Validation Endpoint

| CAS Endpoint | What Is It For? | Non-Negotiable Requirements |
| --- | --- | --- |
| `/serviceValidate` | Validates an **ST** for the exact `service`; may request `pgtUrl`. | ST matches service, is unexpired, and is unused. |
| `/proxyValidate` | Validates an **ST or PT**, returning the proxy chain when proxied. | All ST constraints plus the receiving service's **proxy policy**. |
| `/proxy` | Exchanges a PGT for a PT for a specific `targetService`. | Valid PGT, CAS permits service to proxy, `targetService` approved. |
| App PGT receptor | Receives `pgtId` and `pgtIou` during CAS callback. | HTTPS, CAS/inbound trust, secret storage, and proper correlation. |

CAS 1.0's legacy `/validate` **does not support proxy tickets**. Never pick the CAS 1.0 validator and interpret a `yes` response as a valid PT.

## 3. End-to-End Flow: Receiving a PGT and Using a PT

Illustrative hostnames and paths:

~~~text
CAS Server: https://cas.example.org/cas
Portal A:   https://portal.example.org/app/login/cas
PGT URL A:  https://portal.example.org/app/login/cas/proxyreceptor
Reports B:  https://reports.example.org/api/v1/summary
~~~

### 3.1. Phase A: ST Validation and PGT Callback

~~~text
Browser                  Portal A                     CAS Server
  |                         |                              |
  | /login/cas?ticket=ST-a  |                              |
  |------------------------>|                              |
  |                         | GET /serviceValidate          |
  |                         | ticket=ST-a                   |
  |                         | service=https://portal.../login/cas
  |                         | pgtUrl=https://portal.../proxyreceptor
  |                         |----------------------------->|
  |                         |                              | check ST/service
  |                         |<-----------------------------|
  |                         |  CAS calls PGT callback      |
  |                         |<-----------------------------|
  |                         | GET proxyreceptor?            |
  |                         |     pgtId=PGT-abc             |
  |                         |     pgtIou=PGTIOU-xyz         |
  |                         | store IOU -> secret PGT       |
  |                         | HTTP 200                      |
  |                         |----------------------------->|
  |                         |                              |
  |                         |  /serviceValidate response   |
  |                         |<-----------------------------|
  |                         |  <cas:user>alice</cas:user>   |
  |                         |  <cas:proxyGrantingTicket>    |
  |                         |       PGTIOU-xyz             |
  |                         |  </cas:proxyGrantingTicket>   |
  |                         | fetch PGT by verified IOU     |
~~~

**Do not assume the callback arrives after the XML response:** per the CAS protocol, CAS usually invokes the receptor **before** returning the response containing the IOU; the app must handle **reordered timing** and multi-node deployments. Trust only an **IOU matching a verified CAS validation response**, never matching by “most recent PGT” or username.

The CAS 2.0 protocol mandates `pgtUrl` use **HTTPS** and requires the CAS Server to evaluate trust of the service callback per PKIX/certificate policy. If the callback is unreachable or fails to return a success response, CAS **must not issue the PGT normally**. ST validation may still return an authentication result depending on proxy failure policy; the app **must not claim a PGT was obtained** without a verified IOU→PGT mapping.

### 3.2. Phase B: Obtaining a PT and Calling the API

~~~text
Portal A                    CAS Server                    Reports API B
   |                            |                               |
   | GET /proxy                 |                               |
   |   pgt=PGT-abc              |                               |
   |   targetService=https://reports.../summary                 |
   |--------------------------->|                               |
   |                            | validate PGT and permission   |
   |<---------------------------|                               |
   | <cas:proxyTicket>PT-b</cas:proxyTicket>                     |
   |                            |                               |
   | GET /api/v1/summary?ticket=PT-b                              |
   |------------------------------------------------------------>|
   |                            |                               |
   |                            |  GET /proxyValidate           |
   |                            |  ticket=PT-b                  |
   |                            |  service=exact-targetService  |
   |                            |<------------------------------|
   |                            |------------------------------>|
   |                            |  success + user + proxies     |
   |                            |                               |
   |                            |                        B checks chain:
   |                            |                        all hops/order
   |                            |                        B checks local authz
   |<------------------------------------------------------------|
   | 200 response only if all checks pass                         |
~~~

**A PT is issued for the exact `targetService`.** If A requests a PT for `https://reports.example.org/api/v1/summary` yet B validates against `https://reports.example.org/api/v1/admin`, CAS must reject with `INVALID_SERVICE` or equivalent; B must never “fix” this by accepting arbitrary service URLs.

### 3.3. Proxy Chain in the CAS Response

Illustrative CAS XML:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxies>
      <cas:proxy>https://gateway.example.org/pgtCallback</cas:proxy>
      <cas:proxy>https://portal.example.org/pgtCallback</cas:proxy>
    </cas:proxies>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**Order from top to bottom is most recent first**: in the example, Portal proxied first, then Gateway proxied next; Gateway is the proxy closest to Reports API B. When B requires the exact two-hop chain `[Gateway, Portal]`, `[Portal, Gateway]`, `[Gateway, Evil]`, and `[Gateway, Portal, Evil]` must all be rejected.

**The URLs in `<cas:proxy>` are proxy callback identifiers** recorded by CAS in the proxy history—**not** the user's origin URL, email, hostname from HTTP `Host`, or anonymized LB hops.

## 4. Two Independent Trust Boundaries to Test

### 4.1. Boundary A: CAS Server → PGT Receptor

The CAS Server checks the **PGT callback endpoint's** HTTPS certificate to prove CAS is connecting to the **genuine Portal A**. However, CAS checking Portal A's certificate **does not prove to Portal A that an inbound request was sent by the CAS Server**. A needs appropriate source-authentication controls: mTLS if deployed by the organization, network ACLs/service mesh identity, dedicated ingress, strict trusted gateway, and token/correlation controls. Never rely on a client-supplied `X-Forwarded-For: cas.example.org`.

**Critical bug:** a browser directly calls the receptor with `pgtId=PGT-attacker` and `pgtIou=PGTIOU-xyz`, causing A to overwrite the real mapping. If a subsequent CAS response uses the same IOU, A could accidentally use the attacker's PGT. Block spoofed callbacks and **never overwrite an unverified `PGTIOU` mapping** on duplicate/conflict.

### 4.2. Boundary B: B → CAS `/proxyValidate`

Reports B **must not trust a PT**, `<cas:user>`, or `<cas:proxies>` merely because they arrived in A's request. **B must call the CAS Server to validate the PT** against the exact service URL over TLS to the trusted CAS host, inspect the proxy chain **from the verified validation result**, and then enforce local admission/authorization.

**Critical bug:** B only checks `cas:user=alice` or allows any proxy via `acceptAnyProxy=true`. An attacker controlling another CAS-proxied service could obtain a PT on Alice's behalf for B and traverse an unapproved chain.

### 4.3. Why Checking Only One Hop Is Not Enough

A chain may have a trusted closest proxy while containing an unauthorized hop underneath:

~~~text
CAS login -> Unknown Partner X -> Trusted Gateway -> Reports B

CAS reports:
  [Trusted Gateway, Unknown Partner X]
~~~

If B checks only the first element `Trusted Gateway` or uses “contains trusted hostname,” B can let an unauthorized hop appear in the history. **For applications enforcing a strict chain policy, check the entire list with exact ordered matching**. A policy requiring only the immediate proxy is acceptable **only when business/security owners intentionally delegate downstream trust to that proxy**; do not assume this by default in these tests.

## 5. Proxy Chain Acceptance Rules: Exact, Ordered, Bounded

Policy for Reports B:

~~~text
Allowed (most recent first):
  [https://gateway.example.org/pgtCallback,
   https://portal.example.org/pgtCallback]

Optional allowed direct path (if business separately approves):
  [https://portal.example.org/pgtCallback]

Not allowed:
  [https://portal.example.org/pgtCallback,
   https://gateway.example.org/pgtCallback]     # reversed order

  [https://gateway.example.org/pgtCallback,
   https://untrusted.example.net/pgtCallback]   # malicious hop

  [https://gateway.example.org/pgtCallback,
   https://portal.example.org/pgtCallback,
   https://untrusted.example.net/pgtCallback]   # extra injected hop
~~~

### 5.1. Questions the Policy Must Answer

1. Does B accept **direct STs**, PTs from Portal A, PTs from A→Gateway, or all three?
2. Is an empty chain `[]` allowed? If the endpoint is strictly for **proxy delegation**, you must **deny empty**.
3. Which exact callback URLs are trusted, including scheme, host, port, path, and context root?
4. Is **further delegation** through Gateway permitted? If so, how many hops and in what exact order?
5. Do separate partners/tenants require distinct chain allowlists? If so, route/`targetService` policy must distinguish them.
6. Is the proxy chain read **from the CAS validation response**, never from a self-asserted HTTP header?
7. Does the policy enforce max hops, no duplicates/cycles, HTTPS-only, and no unexpected URL encoding?
8. When the chain is missing/invalid/unknown, does it **fail closed** before creating `Authentication`/permissions?
9. Are there tests confirming **admin rights are never granted solely because the CAS principal and allowed chain are valid**?

### 5.2. URL Matching and Regex

In Apereo Java CAS Client, `allowedProxyChains` can declare each permitted chain, with URLs separated by whitespace within each chain. Some versions support **regex URLs starting with `^`**. **Prefer exact URL allowlists**, because overly broad regexes like `^https://.*example.org/.*` or unanchored regexes can admit unintended hosts/paths. Test against the exact matching implementation/version in use.

Never “normalize” proxy URLs by:
- Stripping HTTP/HTTPS schemes.
- Matching hostname only and ignoring path.
- Checking only `contains("portal")`.
- Ignoring port because “the proxy sits behind a load balancer.”
- Sorting the proxy list before comparison: **order is a security fact**.
- Accepting an approved prefix while the tail holds an unknown hop.
- Treating `X-Forwarded-For` IP/network hops as a CAS proxy chain.

The CAS protocol specifies **the most recently traversed proxy comes first**; therefore configure the allowlist in CAS response order, not in the forward source-to-target order drawn in diagrams. Integration tests must verify every hop and order against your specific CAS/Java Client version.

### 5.3. `acceptAnyProxy` Configuration Can Defeat Testing

Spring Security CAS reference docs show a legacy example using:

~~~xml
<property name="acceptAnyProxy" value="true"/>
~~~

That example **merely illustrates the feature**, not a production recommendation for systems needing proxy chain restrictions. For Reports B under a strict policy, you must set **`acceptAnyProxy=false` + explicit `allowedProxyChains`**, while testing complementary policies in the provider/service layer.

**`allowEmptyProxyChain`** is a separate option on some `Cas20ProxyTicketValidator` versions; if B accepts PTs only via specified proxies, configure and test **disallowing empty chains**. If B accepts both direct STs and PTs, separate route/matcher policies may be needed rather than allowing empty chains on every resource.

## 6. Testing PGT Callbacks: Security-Focused Failure Checklist

### 6.1. HTTPS and Certificates in Both Directions

The PGT URL must use **HTTPS**; the CAS Server must verify the certificate chain, hostname, and validity period. When Portal A sits behind an ingress, CAS sees the registered **public hostname**, not the pod name; a certificate mismatching the public hostname can break PGT callbacks.

On A's side, **never infer the caller is CAS just because the request arrived over HTTPS**. HTTPS proves A to the caller, not the caller to A without mTLS/trusted ingress. Enforce actionable trust boundaries:
- mTLS client identity of the CAS Server/approved gateway, if available.
- Firewall/IP allowlist only as a defense-in-depth layer; never rely on HTTP forwarded IP headers as proof.
- Dedicated ingress route, WAF/rate limits, machine identity, no direct pod access.
- Write `PGTIOU→PGT` **only after** the callback passes source trust policy; duplicates must not overwrite.
- Correlate via the IOU in the verified CAS validation response before allowing the PGT to be used.

### 6.2. Exact HTTP 200 Response

The CAS protocol specifies a successful GET callback must return **HTTP 200 OK** so CAS knows the service receptor is ready. When the callback returns a non-200 status, the PGT will typically not be issued through the normal flow; the spec permits CAS to handle certain **3xx redirects** per profile, so do not claim “every 302 is always rejected.”

**Production recommendation:** the callback URL must point straight to the final receptor, **never depending on 302 redirects**, which can drop query params, change hostnames, downgrade TLS, or leak credentials. Test:
- 200 after committing `IOU→PGT`.
- 500/timeout when store is unavailable: **never** fake-ack 200.
- 302 to a login page: **bug** for a server-to-server callback.
- 401 from Spring form-login filter: receptor matcher is misconfigured.
- 403 from mTLS/network policy: test fail-closed on wrong CAS identity, success on right identity.
- 200 returned before the store write completes: catches IOU resolution races.

### 6.3. No Browser Session on the PGT Receptor

The PGT receptor is a **CAS Server → Portal A callback**, with no reason to use a browser's `JSESSIONID` cookie to correlate PGTs. A proper receptor:
- Creates no local user/session simply upon receiving `pgtId`.
- Never depends on user cookies.
- Never renders `pgtId` or `pgtIou` in HTML, JS, or response bodies.
- Never logs them in Nginx access logs, APM traces, or error messages.
- Stores PGTs solely in secret storage with TTL, encryption/ACLs, and cleanup.
- Allows pending ticket validation responses to locate the exact mapping by IOU.

### 6.4. Spoofed Callback and Duplicate IOU Risks

| Case | Security Expectation |
| --- | --- |
| Browser request with well-formatted `pgtId/IOU`. | **Deny** if it fails CAS-origin machine trust; do not write to store. |
| Two callbacks with same IOU, different PGTs. | **Conflict/deny**; never overwrite the first PGT or pick randomly. |
| Identical duplicate callback from authenticated source. | May be handled idempotently per policy; grant no extra rights; audit. |
| Empty IOU or empty PGT. | Reject input; create no mapping. |
| `PGTIOU` absent from CAS validation response. | Do not use the stored PGT to call `/proxy`. |
| CAS validation returns IOU but store lookup misses. | No PGT available; never fall back to matching by username/timestamp. |
| Callback arrives before validation response. | Store with short TTL and correlate when validation response arrives. |
| Callback arrives after validation response. | Correlation mechanism must wait/bounded-retry per flow; never grab “latest.” |
| Callback hits Node A, validation hits Node B. | Shared/consistent store or guaranteed affinity with failover tests. |
| Store write fails yet receptor returns 200. | Test FAIL: CAS assumes PGT delivered while Portal lacks it. |
| Callback redirects to an unknown host. | Reject/reconfigure receptor; never leak PGT in `Location`. |
| Proxy logs query parameters verbatim. | Security incident/test FAIL; redact across all hops. |

**Note the one-way nature:** CAS Server verifying Portal's callback certificate does not stop an attacker from calling a public receptor. Verify the **inbound peer** separately; without mTLS, enforce proper network trust and correlation. **An IOU itself is not a digital signature**, so merely seeing an IOU is never proof the caller was authenticated by CAS.

## 7. Testing PTs and Rejecting Out-of-Policy Proxy Chains

### 7.1. Enforcement at Reports API B

B must execute in this exact sequence:

~~~text
receive PT from Portal A
 -> validate exact service URL and PT with trusted CAS /proxyValidate
 -> parse authenticated CAS response (not raw client XML)
 -> obtain complete proxy chain
 -> compare against explicit ordered allowlist
 -> check local account status/tenant and resource permission
 -> grant only approved business access
~~~

**Never invert this:** creating a Spring `Authentication` from raw `ticket=PT-*` and leaving the proxy chain only for auditing. Chain policy belongs in **authentication admission** before business authorization touches resources.

### 7.2. Automatable Chain Test Matrix

Suppose only this chain is allowed:

~~~text
APPROVED:
[https://gateway.example.org/pgtCallback,
 https://portal.example.org/pgtCallback]
~~~

| Chain Returned by CAS | Expectation | Reason |
| --- | --- | --- |
| `[gateway, portal]` | **ACCEPT** after PT/service validation. | Exact 2 hops and order. |
| `[portal, gateway]` | **DENY**. | Reversed order, different delegation path. |
| `[gateway, unknown]` | **DENY**. | Untrusted hop in chain. |
| `[unknown, portal]` | **DENY**. | Hop closest to B is untrusted. |
| `[gateway, portal, unknown]` | **DENY**. | Extra hop/prefix-only match. |
| `[gateway]` | **DENY** unless separately approved. | Missing required hop. |
| `[]` or missing `cas:proxies` | **DENY** on PT-only endpoint. | No valid proxy chain proof. |
| `[gateway, gateway]` | **DENY**. | Duplicate/cycle not in allowlist. |
| URL changes `https` to `http` | **DENY**. | Identity/transport changed. |
| URL shares host with different path | **DENY**. | Callback identity must be exact. |
| URL uses deceptive domain suffix like `portal.example.org.evil.net` | **DENY**. | Never substring-match. |
| URL uses different port | **DENY** unless approved. | Different callback identity. |
| Valid chain but PT for different service | **DENY**. | `targetService`/service binding fails. |
| Valid chain but PT already validated at CAS | **DENY** per CAS one-time semantics, unless app cache behavior is explicitly designed/tested. | Replay. |
| Valid chain but CAS validation fails | **DENY**. | No CAS proof. |
| Valid chain, CAS valid, local user DISABLED | **DENY**. | Identity does not override local admission. |
| Valid chain, active user missing `reports:read` | **403**. | Separate local authorization. |

**Testing warning:** an **unsigned** mock CAS endpoint or a hand-edited XML fixture does not prove someone can “attack the CAS Server.” Unit/integration tests aim to **verify the application validates the proxy list returned by CAS**, while E2E requires a real test CAS server issuing PTs per protocol.

### 7.3. One “Success” Is Never Enough

If happy-path `PT` returns HTTP 200, run at least:
- `acceptAnyProxy=true` mutation test: an unknown chain **must not** turn into ACCEPT.
- Empty/missing `allowedProxyChains`: **fail closed**, never accept all proxies.
- Test **long chains** and duplicate hops.
- Same URL with altered casing/path/encoding per policy.
- Test expired PT, replay, wrong service URL, and CAS Server timeout.
- Test an active user lacking permissions at Reports B.

## 8. Spring Security: Relevant Components and Sample Configuration

CAS integration spans Spring Security and Apereo Java CAS Client classes; APIs/packages/versions can vary across Spring Security 5/6/7, Boot Jakarta, and CAS client releases. **Never copy legacy XML snippets from an old article and mix them with newer classes without compiling and testing.**

| Component | Role |
| --- | --- |
| `CasAuthenticationEntryPoint` | Redirects browser to CAS `/login` with service URL. |
| `CasAuthenticationFilter` | Receives ST at login callback or PT in stateless mode per matcher. |
| `ServiceProperties` | Specifies exact service URL and `authenticateAllArtifacts` when PTs are needed. |
| `ServiceAuthenticationDetailsSource` | Builds the service URL used to validate artifacts per request; review behind reverse proxies. |
| `CasAuthenticationProvider` | Invokes ticket validator, consults `CasProxyDecider`, and loads `UserDetails/GrantedAuthority`. |
| `Cas20ServiceTicketValidator` | Validates STs; do not use for PTs. |
| `Cas20ProxyTicketValidator` | Validates PTs and proxy chains; configures `allowedProxyChains` and `acceptAnyProxy`. |
| `CasProxyDecider` | Proxy verification abstraction in Spring Security, depending on provider/version. |
| `ProxyGrantingTicketStorage` | Stores `IOU→PGT`; requires shared/secure storage in clusters. |
| `Cas20ProxyReceivingTicketValidationFilter` | CAS Client filter receiving/validating tickets and supporting the PGT receptor where applicable. |
| `StatelessTicketCache` | Caches PT authentication for stateless remoting in Spring Security; needs TTL/scope and security review. |

### 8.1. Avoiding `acceptAnyProxy`

**This is a Java configuration fragment inside a project depending on Apereo Java CAS Client**, not a standalone Java SE program; align classes/methods with your pinned release:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;
import org.apereo.cas.client.validation.ProxyList;

public class ProxyValidatorConfiguration {

    public Cas20ProxyTicketValidator strictProxyValidator() {
        Cas20ProxyTicketValidator validator =
            new Cas20ProxyTicketValidator(
                "https://cas.example.org/cas");

        // Do not accept arbitrary proxies.
        validator.setAcceptAnyProxy(false);
        validator.setAllowEmptyProxyChain(false);

        // NOTE: order follows <cas:proxies>, most recent first.
        List<String[]> chains = new ArrayList<>();
        chains.add(new String[] {
            "https://gateway.example.org/pgtCallback",
            "https://portal.example.org/pgtCallback"
        });

        validator.setAllowedProxyChains(new ProxyList(chains));
        return validator;
    }
}
~~~

**Limitations:** the Java snippet above configures **B's validator**; it does not build `SecurityFilterChain`, `CasAuthenticationProvider`, `AuthenticationManager`, a PGT receiver, service URLs, or local accounts. Some older versions use the `org.jasig.cas.client` package or factory/property-style config; verify your dependency tree and release JavaDocs, and **test chain acceptance with a CAS response**. Keep `acceptAnyProxy=false` even when an allowlist is declared.

### 8.2. CAS Client Filter Config Is Not the Same as Spring Security Provider

Apereo Java CAS Client exposes configuration properties such as:

~~~properties
casServerUrlPrefix=https://cas.example.org/cas
service=https://reports.example.org/api/v1/summary
proxyReceptorUrl=/login/cas/proxyreceptor
proxyCallbackUrl=https://reports.example.org/login/cas/proxyreceptor
acceptAnyProxy=false
allowedProxyChains=https://gateway.example.org/pgtCallback https://portal.example.org/pgtCallback
~~~

These are **examples of Java CAS Client property meanings**; **they are not a drop-in Spring Boot `application.properties` file**. Starter prefixes/namespaces differ by version. When **Reports B only validates PTs**, B generally **does not need `proxyReceptorUrl`** unless B also intends to acquire a PGT to proxy further. Never expose an unused receptor; if used, B needs its own secret store and trust boundary.

In the CAS Client, `proxyReceptorUrl` is the **context-relative path** where the filter listens for callbacks, whereas `proxyCallbackUrl` is the **full HTTPS URL** sent to the CAS Server. Both must point to the **same actual receptor**; mismatched public host/port/context paths will lose PGTs.

### 8.3. `CasProxyDecider` Is a Separate Control Layer

Spring Security CAS also provides `RejectProxyTickets`, `AcceptAnyCasProxy`, and `NamedCasProxyDecider` depending on API/version. A system may have **two gates**:
1. **CAS client ticket validator** checking PT and `allowedProxyChains`.
2. **Spring provider `CasProxyDecider`** inspecting the proxy list returned by the validator.

Never set `AcceptAnyCasProxy` at the second gate and conclude “it's fine because the first gate rejects it” when enterprise policy demands **defense in depth**. Both configs must **share the same goal**, be tested independently, and both reject unknown proxies. Check version defaults: `RejectProxyTickets` can reject all PTs even when `Cas20ProxyTicketValidator` accepted them; never fix that by switching to AcceptAny without reviewing requirements.

### 8.4. Service URLs and Stateless Remoting

Spring Security CAS docs describe a **stateless client** model: PTs are sent to an endpoint without relying on an HTTP session; `ServiceProperties.authenticateAllArtifacts=true` and `ServiceAuthenticationDetailsSource` validate tickets against the request's service URL. When the external URL differs from the internal URL due to TLS termination/load balancers, configure a **stable public service identity** and a trusted forwarded-header policy.

Spring Security CAS also provides `StatelessTicketCache` to **cache `CasAuthenticationToken` after the first CAS validation**. This detail matters: CAS **itself only lets a PT validate once**, yet when Spring caches the result, **the app may still accept the same PT on subsequent requests without calling CAS again**, depending on cache policy. Therefore:
- Cache duration/scope must fit credential lifetime, endpoint sensitivity, and risk.
- A PT must never turn into an **indefinitely reusable access token**.
- Do not assume CAS prevents every replay against B if B caches and re-accepts PTs.
- If tokens are cached across URLs, enforce strict `targetService`/resource binding.
- Authority/tenant/resource checks and revocation SLAs still apply locally on every decision.

**Testing must cover both cache hits and cache misses**, especially when a PT for `/api/v1/summary` is replayed against `/api/v1/admin`.

## 9. PGT Callbacks: Multi-Node and Race Scenarios

### 9.1. Two Concurrent Login Requests

~~~text
User alice:
  Login browser tab A -> ST-1 -> CAS PGT callback IOU-1/PGT-1
  Login browser tab B -> ST-2 -> CAS PGT callback IOU-2/PGT-2

Forbidden:
  map "alice" -> latest PGT and return PGT-2 to tab A

Required:
  IOU-1 -> PGT-1 per ST-1 verified validation response
  IOU-2 -> PGT-2 per ST-2 verified validation response
~~~

**Correlate by IOU**, never by principal username, HTTP session ID, timestamp, or “current thread,” because the callback from the CAS Server may hit a different node or thread.

### 9.2. Callback Arriving Before or After the Validation Response

Suggested state machine:

~~~text
CALLBACK_RECEIVED(IOU, PGT)
     |
     | verify inbound trust, validate input
     v
PENDING_PGT_IOU_STORE(IOU -> secret-PGT, short TTL)
     |
     | ST validation response from trusted CAS
     | contains matching <cas:proxyGrantingTicket>IOU
     v
CORRELATED_AND_APPROVED
     |
     | business call requests allowed targetService
     v
PGT used server-to-server at CAS /proxy
     |
     v
PT for targetService, never expose PGT to browser
~~~

Never place PGTs in JSP/JSON responses, JavaScript, redirect URLs, or browser storage. If correlation does not complete within the wait window, **expire the pending mapping** rather than reusing IOUs indefinitely. The CAS protocol does not mandate a specific retention duration for application storage; pick a TTL based on observed latency and risk with an upper bound.

### 9.3. Shared Store and Atomic Semantics

In a cluster:
- Callback Node A writes `IOU→PGT` to shared storage.
- ST validation Node B reads by IOU from the XML response.
- Under weak consistency, Node B might miss the mapping and fail despite a 200 callback; design for read-after-write/atomic storage.
- **Duplicate IOUs** must never overwrite a previously stored PGT; use SETNX/CAS or DB unique constraints.
- PGTs are secrets requiring encryption at rest/in transit, restricted ACLs/TTLs, and expiry cleanup.
- If shared storage is unavailable, the receptor **must not return a fake 200** and proceed with SSO assuming the PGT exists.
- Test failover between Node A/B and purge PGTs on CAS logout/local offboarding per policy.

### 9.4. When Callbacks Are Blocked by Routers or Security Filters

| Callback Outcome | Suspect Cause |
| --- | --- |
| 302 to `/login` | Spring form/CAS EntryPoint intercepted a sessionless server-to-server receptor. |
| 401/403 | Misconfigured inbound machine trust/mTLS or wrong filter authorization matcher. |
| 404 | `proxyReceptorUrl` and `proxyCallbackUrl` mismatch in context/matcher. |
| 500 | PGT store unavailable, parser error, or service misconfiguration. |
| 200 yet no PGTIOU in validation response | CAS policy forbids issuing PGT, or callback response/correlation failed. |
| TLS certificate error from CAS | Wrong public certificate/hostname/chain/expiry on the receptor. |
| PGTIOU present yet A cannot find PGT | Different-node local IOU store, race, too-short TTL, or map conflict. |

**Never resolve this by making `/proxyreceptor` unrestricted public, disabling certificate checks, or writing PGTs into browser cookies.** Fix the root cause: receptor route, CAS trust/certificate, shared IOU store, response timing, or service registration.

## 10. A Trustworthy Test Architecture

### 10.1. Testing Levels

| Level | Components Run | Value |
| --- | --- | --- |
| **Unit** | Proxy chain policy, callback correlation/state machine; mocked verified CAS outcomes. | Fast; proves exact/order/deny semantics. |
| **Component** | CAS client validator + mock CAS validation endpoint, PGT receptor + mock inbound caller. | Tests wiring, XML parsing, `allowedProxyChains`, status handling. |
| **Integration** | Portal A, Reports B, test CAS server, TLS certs, test IdP/users. | Verifies real `ST→PGT callback→PT→proxyValidate`. |
| **Multi-node E2E** | A/B ≥2 nodes, shared PGT store/session/cache, ingress/firewall. | Catches races, node failover, callback routing, TLS/source trust. |
| **Security/adversarial** | Attacker-spoofed callbacks/chains, wrong service, replay, SSRF attempts. | Proves fail-closed without production credentials. |
| **Chaos** | CAS down, store timeout, dropped callbacks, DNS rotation, pod restarts. | Tests failure modes, retry bounds, and cleanup. |

**Important:** a unit test cannot simulate a “CAS cryptographically validated response” simply by setting a boolean true in a public request. Test doubles only verify **post-validation application policy**. E2E must verify end-to-end against a real CAS Server with TLS trust.

### 10.2. Controlled Synthetic Data

~~~text
CAS:     https://cas.test.example/cas
Portal:  https://portal.test.example/app
Receptor:https://portal.test.example/app/login/cas/proxyreceptor
B:       https://reports.test.example/api/v1/summary
Allowed proxy list: [Gateway, Portal] (most recent first)
Users:   alice ACTIVE reports:read; bob ACTIVE no reports:read
Tickets: opaque fresh ST/PT/PGT from test CAS (never prod)
~~~

For negative tests, use the **test CAS service registry** to toggle proxy permissions, issue PTs via untrusted proxies, or supply wrong callback URLs. Never copy real PGTs into fixtures, logs, CI snapshots, or public directories.

### 10.3. Recording QA Evidence

Record for every test case:
- Test ID, CAS/client/Spring Security versions, and config policy version.
- Source service/`targetService` identifier (no tokens).
- Callback outcome: HTTP status, inbound identity verified yes/no, IOU presence boolean, store outcome.
- CAS validation result code and **redacted proxy chain or canonical partner refs**—never log secrets.
- Chain decision ALLOW/DENY and local account/authority decision.
- Number of CAS validation calls, cache hits/misses, replay outcome.
- Node/ingress path and a dedicated correlation ID (do not reuse `pgtIou` in metrics).
- Expected vs. actual; whether failure occurred at CAS, gateway, Spring validator, or business layer.

## 11. Integration Test Scenarios: PGT Callback and CAS Protocol

### 11.1. Happy Path

1. Create a test CAS service registry permitting only Portal A to receive PGTs and proxy to B.
2. Test browser logs into CAS and obtains an ST for A's exact service URL.
3. Portal A calls CAS `/serviceValidate` with `pgtUrl=https://portal.../proxyreceptor`.
4. CAS Server checks the receptor's TLS certificate and sends HTTPS GET with `pgtId, pgtIou`.
5. Receptor verifies the inbound peer, persists `IOU→PGT`, and returns 200 after persisting.
6. CAS returns validation success with `cas:user` and **`cas:proxyGrantingTicket=PGTIOU...`**.
7. A looks up the PGT by exact IOU; A calls `/proxy` for **targetService B** and receives a PT.
8. A calls B with the PT; B calls `/proxyValidate`.
9. CAS returns username and **proxies list**; B verifies the exact ordered allowed chain.
10. B enforces local permissions, returning 200 for Alice and denying Bob.

Also confirm the PGT never appears in URLs/responses/browser, and the server-to-server callback needs no browser cookie.

### 11.2. Spoofed Callback Source

Using an HTTP client not authenticated by inbound trust, send:

~~~http
GET /app/login/cas/proxyreceptor?pgtId=PGT-fake&pgtIou=PGTIOU-fake HTTP/1.1
Host: portal.test.example
~~~

Expect the request to be **denied** by firewall/mTLS/gateway, or fail closed at the receptor per trust contract. No mapping written, no session/login created, no PT issued. Returning 200 while storing a mapping from an arbitrary client is a **critical test FAIL**.

### 11.3. Missing / Mismatched IOU Callbacks

- Callback has IOU A, CAS validation returns IOU B → do not pick PGT A.
- CAS validation omits PGTIOU because proxying is forbidden → do not call CAS `/proxy`.
- Duplicate IOU callback with a different PGT → conflict, do not overwrite.
- Callback arrives past TTL → do not use stale PGT.
- Users A and B log in concurrently → exact per-IOU mapping.
- Callback hits Node 1, validation hits Node 2 → reads shared store without relying on local memory.

### 11.4. HTTP Errors and TLS on Callbacks

- Expired HTTPS certificate/wrong hostname on receptor: CAS does not issue a PGT normally.
- Callback route redirects to login: CAS callback fails as designed.
- Network timeout before persistence: retry per CAS/client contract; never fake-ack 200.
- Store write succeeds yet 200 response is lost: any duplicate callback must be idempotent without leaking/overwriting.
- Security layer blocks callback from a non-allowlisted CAS instance: properly denied.
- IdP/CAS outage: never fall back to reusing old PGTs indefinitely or skipping proxy chain validation.

## 12. Test Matrix: Disallowed Chains and Ticket Binding

| Case | CAS/Chain/Ticket Condition | Expectation at Reports B |
| --- | --- | --- |
| Valid PT, exact chain | `[Gateway, Portal]`, target B, active Alice | 200 if authorized. |
| Valid PT, reversed chain | `[Portal, Gateway]` | Deny. |
| Valid PT, unknown first hop | `[Evil, Portal]` | Deny. |
| Valid PT, unknown last hop | `[Gateway, Evil]` | Deny. |
| Valid PT, extra proxy hop | `[Gateway, Portal, Evil]` | Deny. |
| Valid PT, missing hop | `[Gateway]` | Deny if policy requires both. |
| Valid PT, empty chain | `[]` | Deny if proxy-only endpoint. |
| Valid PT, duplicated hop | `[Gateway, Gateway]` | Deny. |
| Valid PT, wrong scheme | `http://gateway...` | Deny; never “normalize” to HTTPS. |
| Valid PT, same host wrong path | `/otherCallback` | Deny. |
| Valid PT, suffix trick | `portal.example.org.evil.net` | Deny. |
| Valid PT, wrong port | `:8443` outside policy | Deny. |
| Valid PT, targetService B2 | Validated as B1 | CAS `INVALID_SERVICE`; no auth created. |
| PT already validated at CAS | Replayed to `/proxyValidate` | CAS rejects; if cache active, test cache semantics. |
| Raw fake PT | Ticket not issued by CAS | CAS rejects. |
| Valid chain but CAS never validated | Self-asserted XML/client claim | Deny. |
| Valid chain but local account DISABLED | Legit CAS principal | Deny admission. |
| Valid chain but user lacks permission | Active user, wrong role | 403 authz. |
| `acceptAnyProxy` misconfiguration | Unknown chain would pass | Config test FAIL. |
| No allowed proxy chains | New proxy implicitly accepted | Test FAIL. |
| Wrong CAS server host/cert | Untrusted validation | Fail closed; never skip TLS verification. |
| Filter uses only `Cas20ServiceTicketValidator` | PT from valid proxy | Rejects PT; configure proxy-aware validator if PTs needed. |
| Wrong Spring provider proxy decider | Validator passes yet decider rejects | Intentional auth failure; fix policy rather than blindly enabling accept-any. |
| Wrong cache scope | PT from summary reused on admin | Deny resource access by scope; bound TTL. |

## 13. Runnable Java 17: Simulating PGT Callback and Exact Proxy-Chain Policy

The program below **runs standalone with JDK 17** using only the Java Standard Library. It tests **application policy**, not the CAS Client, makes no CAS Server calls, performs no real TLS/mTLS verification, and parses no CAS XML.

**Testing assumption:** booleans `trustedCasPeer`, `casValidationSuccessful`, and `exactTargetService` merely represent checks **already performed by the authentication/gateway/CAS validator layer**. Never take them from a caller's query/header/JSON to make production authentication decisions. `PGTIOU`/`pgt` values here are dummy strings with **no real credentials**.

File **`CasProxyPolicyDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class CasProxyPolicyDemo {

    private static final String PORTAL =
        "https://portal.example.org/pgtCallback";
    private static final String GATEWAY =
        "https://gateway.example.org/pgtCallback";
    private static final String CALLBACK =
        "https://portal.example.org/login/cas/proxyreceptor";

    // CAS reports most recently visited proxy first.
    private static final List<String> APPROVED =
        List.of(GATEWAY, PORTAL);

    record ValidatedTicket(boolean casValidationSuccessful,
                           boolean exactTargetService,
                           boolean unusedAtCas,
                           List<String> proxies) {}

    static String decide(ValidatedTicket t) {
        if (!t.casValidationSuccessful()) return "DENY_CAS_VALIDATION";
        if (!t.exactTargetService()) return "DENY_TARGET_SERVICE";
        if (!t.unusedAtCas()) return "DENY_REPLAY";
        if (t.proxies() == null || t.proxies().isEmpty())
            return "DENY_EMPTY_CHAIN";
        if (!APPROVED.equals(t.proxies()))
            return "DENY_UNTRUSTED_CHAIN";
        return "ALLOW";
    }

    static final class Receptor {
        private final Map<String, String> pending =
            new ConcurrentHashMap<>();

        String receive(boolean trustedCasPeer, String calledUrl,
                       String iou, String pgt) {
            if (!trustedCasPeer) return "DENY_CALLBACK_PEER";
            if (!CALLBACK.equals(calledUrl)) return "DENY_CALLBACK_URL";
            if (iou == null || !iou.startsWith("PGTIOU-")
                    || pgt == null || !pgt.startsWith("PGT-"))
                return "DENY_CALLBACK_FIELDS";

            String existing = pending.putIfAbsent(iou, pgt);
            if (existing == null) return "STORED";
            if (existing.equals(pgt)) return "DUPLICATE_IGNORED";
            return "DENY_IOU_CONFLICT";
        }

        String correlate(boolean validationFromCas, String verifiedIou) {
            if (!validationFromCas) return "DENY_UNVERIFIED_RESPONSE";
            if (verifiedIou == null) return "DENY_IOU_MISSING";
            String pgt = pending.remove(verifiedIou);
            return pgt == null ? "DENY_IOU_NOT_FOUND" : "MATCHED";
        }
    }

    public static void main(String[] args) {
        Receptor receptor = new Receptor();

        System.out.println("FAKE_CALLBACK=" + receptor.receive(
            false, CALLBACK, "PGTIOU-1", "PGT-1"));
        System.out.println("WRONG_CALLBACK=" + receptor.receive(
            true, "https://other.example.org/receptor",
            "PGTIOU-1", "PGT-1"));
        System.out.println("PGT_STORED=" + receptor.receive(
            true, CALLBACK, "PGTIOU-1", "PGT-1"));
        System.out.println("PGT_DUPLICATE=" + receptor.receive(
            true, CALLBACK, "PGTIOU-1", "PGT-1"));
        System.out.println("PGT_CONFLICT=" + receptor.receive(
            true, CALLBACK, "PGTIOU-1", "PGT-other"));
        System.out.println("UNVERIFIED_XML=" + receptor.correlate(
            false, "PGTIOU-1"));
        System.out.println("OTHER_IOU=" + receptor.correlate(
            true, "PGTIOU-other"));
        System.out.println("MATCH_IOU=" + receptor.correlate(
            true, "PGTIOU-1"));
        System.out.println("REUSED_IOU=" + receptor.correlate(
            true, "PGTIOU-1"));

        System.out.println("CHAIN_OK=" + decide(
            new ValidatedTicket(true, true, true,
                List.of(GATEWAY, PORTAL))));
        System.out.println("REVERSED=" + decide(
            new ValidatedTicket(true, true, true,
                List.of(PORTAL, GATEWAY))));
        System.out.println("UNKNOWN=" + decide(
            new ValidatedTicket(true, true, true,
                List.of(GATEWAY, "https://evil.example.org/pgt"))));
        System.out.println("EXTRA_HOP=" + decide(
            new ValidatedTicket(true, true, true,
                List.of(GATEWAY, PORTAL,
                    "https://evil.example.org/pgt"))));
        System.out.println("EMPTY=" + decide(
            new ValidatedTicket(true, true, true, List.of())));
        System.out.println("WRONG_SERVICE=" + decide(
            new ValidatedTicket(true, false, true,
                List.of(GATEWAY, PORTAL))));
        System.out.println("REPLAY=" + decide(
            new ValidatedTicket(true, true, false,
                List.of(GATEWAY, PORTAL))));
        System.out.println("NO_CAS_PROOF=" + decide(
            new ValidatedTicket(false, true, true,
                List.of(GATEWAY, PORTAL))));
    }
}
~~~

Compile/run:

~~~bash
javac CasProxyPolicyDemo.java
java CasProxyPolicyDemo
~~~

**Deterministic stdout:**

~~~text
FAKE_CALLBACK=DENY_CALLBACK_PEER
WRONG_CALLBACK=DENY_CALLBACK_URL
PGT_STORED=STORED
PGT_DUPLICATE=DUPLICATE_IGNORED
PGT_CONFLICT=DENY_IOU_CONFLICT
UNVERIFIED_XML=DENY_UNVERIFIED_RESPONSE
OTHER_IOU=DENY_IOU_NOT_FOUND
MATCH_IOU=MATCHED
REUSED_IOU=DENY_IOU_NOT_FOUND
CHAIN_OK=ALLOW
REVERSED=DENY_UNTRUSTED_CHAIN
UNKNOWN=DENY_UNTRUSTED_CHAIN
EXTRA_HOP=DENY_UNTRUSTED_CHAIN
EMPTY=DENY_EMPTY_CHAIN
WRONG_SERVICE=DENY_TARGET_SERVICE
REPLAY=DENY_REPLAY
NO_CAS_PROOF=DENY_CAS_VALIDATION
~~~

### 13.1. Why Do These Lines Matter?

- `FAKE_CALLBACK` stores no PGT even when the caller supplies well-formatted IOU and PGT prefixes.
- `PGT_CONFLICT` never overwrites an existing IOU with a different PGT.
- `UNVERIFIED_XML` cannot retrieve a PGT without a trusted ticket validation result.
- `OTHER_IOU` never grabs the user's “latest PGT.”
- `MATCH_IOU` works once; `REUSED_IOU` cannot retrieve the secret again.
- `CHAIN_OK` accepts only both proxy URLs in exact CAS order.
- `REVERSED`, `UNKNOWN`, `EXTRA_HOP`, and `EMPTY` are denied.
- `WRONG_SERVICE`, `REPLAY`, and `NO_CAS_PROOF` are rejected despite a valid proxy chain.

**What the demo intentionally omits:** it does not verify CAS XML responses, certificates, chains, mTLS, principals, user roles, real ST/PT state, PGT TTLs, encrypted storage, or multi-node DB transactions. `ConcurrentHashMap` is atomic only within **one JVM**, not a replacement for a distributed store. `unusedAtCas` models CAS one-time validation; when Spring `StatelessTicketCache` is enabled, test cache behavior separately instead of trusting a boolean. `PGT-`/`PGTIOU-` prefixes validate **syntax only**, not cryptographic authentication; production must never treat them as caller proof.

## 14. Common Issues and Resolution Paths

| Symptom | Common Cause | Correct Action |
| --- | --- | --- |
| ST login succeeds yet no PGT arrives. | CAS cannot reach HTTPS receptor, service not allowed to proxy, callback non-200. | Check CAS logs, public callback TLS/host, service registry, response IOU. |
| Callback gets 302 to CAS login. | Security chain intercepts receptor as a browser page. | Route server-to-server path through proper filter while preserving inbound trust. |
| Callback returns 200 yet IOU lookup is null. | Different node's local store, async persistence, too-short TTL. | Atomic/read-after-write shared store, multi-node tests. |
| PGT appears in query logs. | Proxy logs full URI or APM records request params. | Redact at gateway+backend; rotate compromised secrets. |
| CAS delivers PGT to callback yet app picks wrong user. | PGT looked up by username instead of IOU. | Correlate by exact verified PGTIOU. |
| Duplicate callback alters mapping. | `PUT`/overwrite map by IOU. | SETNX/unique constraint; reject conflicts. |
| PT to B returns `INVALID_TICKET`. | PT already validated or not a CAS-issued ticket. | One-time semantics; never retry PT endlessly. |
| PT to B returns `INVALID_SERVICE`. | `targetService` requested by A mismatches service validated by B. | Fix exact public service URL/ingress config. |
| B accepts unknown proxies. | `acceptAnyProxy=true`, overly broad regex, checking only first proxy. | Exact ordered `allowedProxyChains` + provider decider tests. |
| B rejects all valid PTs. | Using `Cas20ServiceTicketValidator` only, or default `RejectProxyTickets`. | Configure proxy-aware validator and policy-driven decider, not accept-any. |
| Chain order mismatches test fixture. | Reading `cas:proxies` in reverse order. | CAS protocol: most recent first; fix expected array. |
| B appears to accept replayed PTs. | Spring `StatelessTicketCache` cached `Authentication`. | Test cache hit/miss, TTL, route/scope/tenant checks. |
| PGT callback fails with alias. | `proxyCallbackUrl` has wrong DNS/port/TLS or redirect. | Use exact public HTTPS URL of receptor with valid cert. |
| Test callback from internet gets 200. | Receptor lacks inbound trust; relies on HTTPS alone. | mTLS/service identity/ACL, peer auth, IOU correlation. |
| CAS `/proxy` returns `UNAUTHORIZED_SERVICE_PROXY`. | CAS service registry forbids A from proxying. | Admin approves exact service proxy authorization without wildcards. |
| B receives right chain yet user lacks role. | Local user status/permission denied. | Keep 403 authz; do not alter allowlist. |
| API calls CAS over HTTP or ignores TLS certs. | Misconfigured back-channel client. | HTTPS verifying CA/hostname; never trust-all. |
| Nodes A/B see different chains during rollout. | Unsynchronized allowed chains/versions. | Versioned policy, canary/fail-closed, rollout tests. |
| CAS Server upgrade alters PGT flow. | CAS3/extensions differ in callback profiles. | Pin versions, run integration compatibility tests, never assume callbacks unconditionally. |

### 14.1. Distinguishing Validation Errors from Authorization Errors

- **`INVALID_TICKET` / `INVALID_SERVICE`**: CAS rejected the ticket or service binding. This is a protocol authentication error.
- **`UNAUTHORIZED_SERVICE_PROXY`**: service lacks proxy permission in CAS registry/policy.
- **`UNTRUSTED_CHAIN` / `REJECT_PROXY`**: application B disallowed the delegation chain even though CAS validated the PT.
- **`LOCAL_ACCOUNT_DISABLED`**: identity was verified but blocked by application account policy.
- **`FORBIDDEN_RESOURCE`**: account is authenticated yet lacks permission/tenant/resource ownership.
- **`PGT_IOU_NOT_FOUND`**: A cannot retrieve a PGT; not proof that the user entered a wrong password.

HTTP statuses vary across filters/error handlers and CAS client versions; QA should inspect **reason codes and `Authentication` state**, not merely 401/403/500.

## 15. Observability and Privacy

### 15.1. Recommended Log Fields

~~~text
event=CAS_PROXY_VALIDATION
trace_id=casproxy-test-384
cas_server_ref=corporate-cas
service_ref=reports-summary
origin_proxy_ref=portal
chain_policy_version=proxy-allow-v3
chain_length=2
chain_decision=ALLOW
pgt_callback_status=STORED
pgt_iou_correlation_status=MATCHED
ticket_validation=SUCCESS
local_account_status=ACTIVE
resource_authz=ALLOW
~~~

This is a recommended schema, not Spring Security/CAS default logging. Use **references/hashes** instead of raw ticket values; never put `pgtId`, `pgtIou`, `ticket=PT-*`, TGTs, TGC cookies, usernames, or attributes into metric labels. PGTs and PTs are bearer credentials.

### 15.2. Metrics and Alerts

- `cas_pgt_callback_received_total{outcome}` – includes peer denied, store failed, duplicate/conflict.
- `cas_pgt_iou_match_failed_total{service}` – tracks callback/validation races.
- `cas_proxy_chain_denied_total{reason,service}` – especially unknown hop/order/empty.
- `cas_proxy_ticket_validation_failed_total{reason}` – invalid ticket/service, TLS failure.
- `cas_proxy_ticket_cache_hit_total{service}` – detects applications re-accepting cached PTs.
- `cas_proxy_unauthorized_service_total{service}` – CAS registry forbids proxying.
- `cas_pgt_store_lag_ms{bucket}` – store visibility/latency (use real histograms).
- `cas_proxy_session_revocation_lag_ms{bucket}` – if logout/revocation is integrated.

**Security alert:** an unexpected proxy chain being accepted after a config change is far more dangerous than an isolated 500 callback. Bound metric cardinality by partner refs, never full attacker-supplied URLs.

## 16. Anti-Patterns to Avoid

1. **Enabling `acceptAnyProxy=true` on Reports B** when business policy permits only an approved chain.
2. **Checking only the first proxy** or using `chain.contains(trustedPortal)`.
3. **Sorting or reversing the proxy chain before comparison** thinking order does not matter.
4. **Allowing a valid chain prefix** while ignoring trailing proxies.
5. **Allowing overly broad regexes** in `allowedProxyChains` without threat modeling.
6. **Treating matching callback hostname as sufficient** while ignoring scheme/path/port.
7. **Accepting PGT callbacks from browsers** because the endpoint is public without inbound trust.
8. **Using Portal's HTTPS server cert as proof the CAS Server called in**: wrong authentication direction.
9. **Correlating PGTs by username/latest session**, causing cross-login mix-ups.
10. **Returning 200 before persisting** `PGTIOU→PGT`, causing lost PGTs and races.
11. **Storing PGTs in browser/localStorage/cookies** or logging query strings.
12. **Accepting raw PTs without calling CAS** or without verifying `targetService`.
13. **Treating CAS `/proxyValidate` success as sufficient for admin access**, skipping local authz.
14. **Skipping CSRF/session protections “because CAS is used”** on other browser endpoints.
15. **Using `Cas20ServiceTicketValidator` for PTs** and bypassing failures with custom code.
16. **Disabling certificate/hostname verification on the CAS back-channel** to work around PGT errors.
17. **Failing to test cache hits** in Spring stateless proxy mode; PT replays behave differently when cached.
18. **Testing only one node** and overlooking callbacks hitting another node.
19. **Mixing up the ST browser callback and the PGT server-to-server callback**.
20. **Logging raw `ticket=ST-*` and `pgtId` in access logs** while debugging.
21. **Sharing one proxy chain policy across all tenants** despite differing sensitivity levels.
22. **Allowing unbounded proxy chaining** without hop limits or approved exact paths.
23. **Treating HTTP 200 from `/proxyreceptor` as proof PGT correlation succeeded**.
24. **Using hand-edited XML fixtures as proof the real CAS Server emits that chain**, without test-CAS E2E.
25. **Modifying production proxy allowlists without versioning, approval, and rollback**.

## 17. Acceptance Checklist

1. Initial ST is validated at CAS for the **exact Portal A service URL**.
2. CAS service registry allows A to request PGTs/PTs without opening proxying to every service.
3. `pgtUrl` is an exact public HTTPS URL and CAS verifies certificate/hostname.
4. Receptor does not depend on browser cookies/sessions and creates no login on receiving `pgtId`.
5. Inbound receptor trust is enforced via mTLS/ACLs/gateway identity as appropriate.
6. PGT IOU is stored and correlated strictly with a **verified ST/PT validation response**.
7. Duplicate/conflict IOUs do not overwrite PGTs; TTL/cleanup and encrypted storage are active.
8. Callback failures/timeouts/redirects are never reported as PGT success.
9. Multi-node callbacks and ST validation share the same storage/consistency guarantees.
10. A calls `/proxy` server-to-server with the secret PGT and exact `targetService` for Reports B.
11. B uses `/proxyValidate` and a proper `Cas20ProxyTicketValidator`/proxy-aware validator.
12. B rejects unknown/intermediate/extra/reversed/empty chains per policy.
13. `acceptAnyProxy=false`, `allowedProxyChains`, and `CasProxyDecider` are tested consistently.
14. Exact chain URLs include scheme, host, port, path, and **most-recent-first** order.
15. Wrong-service, expired, already-validated, or fake PTs are all denied.
16. Spring `StatelessTicketCache` is bounded and tested against TTL/scope/replay policy.
17. Disabled local users, tenant mismatches, and missing permissions are denied after CAS auth.
18. ST/PT/PGT/IOU are redacted at gateway/APM/app logs and never leaked in responses.
19. Integration tests run against a real test CAS Server with TLS-trusted certificates.
20. Failure injection covers CAS down, PGT store down, callback 302/500, and DNS/cert failures.
21. Concurrent first logins by the same and different users are tested for IOU mix-ups.
22. Auditing and alerts cover callback spoof attempts, untrusted chains, and policy changes.
23. No direct service/ingress shortcuts bypass policies.
24. Every trust chain change has a reviewer, policy version, canary, and safe rollback.

## 18. Self-Check Knowledge Questions

1. **What does CAS Proxy solve?** – Allows service A to call service B on a user's behalf using a CAS PT without sharing passwords/TGTs.
2. **How does an ST differ from a PT?** – An ST is for the initial service; a PT is obtained via a PGT for a downstream `targetService`.
3. **What is a PGT used for?** – Allows a proxying service to request multiple PTs from CAS.
4. **What is PGTIOU?** – The correlation key linking a PGT callback with a trusted ticket validation response.
5. **Where does the PGT callback originate?** – The CAS Server calls Portal A's HTTPS receptor, not the user's browser.
6. **Why can't the receptor trust the caller solely because of HTTPS?** – Inbound HTTPS proves the receptor to CAS/the caller, not CAS to the receptor.
7. **Why must the IOU be checked?** – To match each PGT to the exact login/ST validation, preventing cross-session mix-ups.
8. **What does CAS `/proxy` accept?** – A PGT and `targetService`; returns the corresponding PT.
9. **How does B validate a PT?** – CAS `/proxyValidate` with the PT and exact service URL.
10. **What order does `cas:proxies` use?** – Closest/most recent proxy first, not forward order from the origin.
11. **Why is `acceptAnyProxy=true` dangerous?** – It can accept PTs from unapproved proxy chains.
12. **Why isn't checking only the first proxy enough?** – Earlier hops may be untrusted even when the hop closest to B is valid.
13. **May the proxy chain be sorted before comparing?** – No; order is part of the delegation history.
14. **What does `allowEmptyProxyChain` control?** – Whether an empty chain is accepted; proxy-only routes should deny it.
15. **What happens on a wrong `targetService`?** – CAS rejects the ticket per service binding.
16. **Can a PT be validated twice at CAS?** – No, per CAS one-time semantics; Spring caching must be tested separately.
17. **Why do two pods need a shared `PGTIOU` store?** – Callback and validation may be handled by different nodes.
18. **Does a 200 callback prove the PGT is valid for login?** – No; CAS validation response and IOU correlation are still required.
19. **Does a CAS-authenticated user automatically get `reports:read`?** – No; B still enforces local account status/authorization.
20. **Which tests prove resistance to chain spoofing?** – E2E/negative tests with unknown, reversed, extra, missing, and empty proxy chains alongside genuine CAS validation.

## References

- [Apereo CAS — CAS Protocol Specification, §2.5.4 proxy callback, §2.6 proxyValidate, §2.7 proxy](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Spring Security — CAS Authentication and Proxy Ticket Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Apereo Java CAS Client — README: Proxy Receiving Validation Filter, allowedProxyChains, acceptAnyProxy](https://github.com/apereo/java-cas-client/blob/master/README.md)
- [Cas20ProxyTicketValidator JavaDoc: allowedProxyChains, allowEmptyProxyChain](https://javadoc.io/static/org.jasig.cas.client/cas-client-core/3.6.4/org/jasig/cas/client/validation/Cas20ProxyTicketValidator.html)
- [Apereo CAS — Proxy Authentication Configuration](https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html)
- [Spring Security — StatelessTicketCache and CasProxyDecider](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html#_proxy_ticket_authentication)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)
