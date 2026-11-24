# Scenario Where a Service Needs to Call Another Service on Behalf of a User with CAS Proxy

> **Module:** Spring Security – federation. **Group:** CAS Proxy. Topic: An application that has authenticated a user via Central Authentication Service (CAS) needs to call a downstream service **on behalf of that same user**. This lesson clarifies CAS ticket types, the **Proxy-Granting Ticket (PGT) → Proxy Ticket (PT)** flow, proxy chains, trust policies, and authorization at each service. The standalone example runs on pure **Java 17**; Spring Security CAS configuration is presented at the integration level and must be verified against the exact Spring Security/CAS Client version, without assuming a single toggle enables proxy support in Spring Boot 3.5.x.

## 1. Objectives and Prerequisites

After this lesson, learners should be able to:

1. Explain why **Service A, already logged in via CAS**, cannot simply take its own `JSESSIONID` or Service Ticket and send it to Service B to call an API on the user's behalf.
2. Accurately distinguish **Ticket-Granting Ticket (TGT)**, **Ticket-Granting Cookie (TGC)**, **Service Ticket (ST)**, **Proxy-Granting Ticket (PGT)**, **Proxy-Granting Ticket IOU (PGTIOU)**, and **Proxy Ticket (PT)**.
3. Describe how A requests a PGT when validating an ST via `/serviceValidate` (or `/p3/serviceValidate`), handles the HTTPS `pgtUrl` callback, correlates `pgtIou`, and requests a PT from `/proxy` for a **fixed targetService B**.
4. Describe how B validates a PT at `/proxyValidate` or `/p3/proxyValidate`, compares `service`, processes `cas:proxies`, and enforces **trusted proxies policy**.
5. Separate the responsibilities of the CAS Server, browser/user, A (proxying service), B (back-end target), the Spring Security filter/provider, and the business authorization layer.
6. Apply **least privilege**, destination allowlisting, TLS, secure PGT storage, anti-replay, SSRF prevention, and safeguards against forwarding PT/PGT to the wrong service.
7. Design a Spring Security CAS solution on A/B, understanding `Cas20ProxyTicketValidator`, `ProxyGrantingTicketStorage`, `CasAuthenticationFilter`, and `NamedCasProxyDecider` according to the target version.
8. Run a Java 17 demo on proxy/target policy and compare stdout against predictions; distinguish the demo from real cryptographic/protocol validation.
9. Write integration tests against a CAS sandbox for ST, PGTIOU, PGT, PT, /proxyValidate, chains, session expiry, cancellation, and security failures.
10. Compare CAS Proxy with **service accounts** and **OAuth2 Token Exchange / on-behalf-of** to avoid misapplying it in new environments.

**Prerequisites:** CAS login flow, HTTP 302/HTTPS, cookies/HTTP session, CAS `/login` and `/serviceValidate`, Spring Security `Authentication`/`SecurityFilterChain`, TLS/PKIX, backend REST APIs, and resource authorization.

**Versions:** The CAS protocol URLs here are based on CAS 2.0/3.0. Spring Security CAS documentation contains some XML/namespace configuration snippets from older versions; you must cross-check against the **CAS module and Java APIs of your exact deployment version** and verify compatibility before going to production.

## 2. Real-World Problem: Portal Needs to Call Reports API

User Lan logs into **Portal (Service A)** via CAS. In Portal, Lan clicks “View my reports”. Portal needs to call **Reports API (Service B)** to read data that only Lan is allowed to view.

~~~text
Lan + Browser
     |
     | 1. CAS SSO login
     v
Portal A (CAS-protected, stateful web app)
     |
     | 2. Server-to-server call: GET /reports/me
     v
Reports API B (CAS-protected, without Lan's browser session)
     |
     | 3. Needs to know "this is Lan, A acting on behalf of Lan"
     v
Data and authorization scoped to Lan
~~~

**Why not forward A's cookie or ST?**

- The `JSESSIONID` cookie is Portal A's local session; B does not necessarily share the same session store and has no reason to trust that cookie.
- The CAS `TGC` is the SSO session cookie at the CAS Server, belonging to the browser/CAS domain—not a credential for A to pass to B.
- A's CAS `ST-...` is **bound to a specific service identifier** and is **single-use** when A validates it; it cannot be reused for B.
- A username in an HTTP header like `X-User: lan` sent by A itself is **not proof** unless B has a separate delegation relationship and trusted channel.
- If A calls B using A's own **service account**, B knows “A is calling” but cannot reliably distinguish or audit user Lan.

**CAS Proxy** solves **delegated authentication**: A obtains a **separate PT** issued by CAS specifically for **targetService B**, then B **independently** validates the PT with CAS and learns the username along with the proxy chain used. Afterward, B must still enforce **authorization**.

### 2.1. Who Decides Whether Proxying Is Allowed?

Agreement is required from at least three parties:

1. **CAS Server** only issues PGTs/PTs to services registered and permitted to proxy under its policy.
2. **Service A** only requests a PT when the user has a valid authentication and the purpose of calling B is permitted, never accepting an arbitrary targetService from user input.
3. **Service B** only accepts a PT when CAS validation succeeds **and** the proxy chain contains intermediaries permitted by B; then B checks user/tenant/roles/resource ownership.

CAS Proxy does **not** carry a full OAuth scope system by itself or guarantee that every operation A performs on the user's behalf is authorized.

## 3. CAS Ticket Vocabulary: ST, PGT, PGTIOU, and PT

| Artifact | Issued By | Held / Used By | Purpose | Security Notes |
| --- | --- | --- | --- | --- |
| **TGT** | CAS Server | CAS server-side ticket registry | Maintains user SSO session | **Never** send TGT to apps A/B |
| **TGC** | CAS Server | Browser sent to CAS | Cookie referencing the SSO session | Not a token A sends to B |
| **ST-...** (Service Ticket) | CAS Server | Browser delivers to A; A sends to CAS to validate | Authenticates user **for service A** | `service`-bound, one-time, short TTL |
| **PGT-...** (Proxy-Granting Ticket) | CAS Server | **Service A**, usually via HTTPS callback | Allows A to request multiple PTs on the user's behalf | **Not one-time**; high-privilege secret, must be protected |
| **PGTIOU-...** | CAS Server | A receives in callback and validation response | Correlates the PGT callback with ST validation | **Not** a credential replacing PGT |
| **PT-...** (Proxy Ticket) | CAS Server | A receives then presents to B; B validates with CAS | Authenticates user **for targetService B** | Target-bound, single-use validation, short TTL |
| **CAS user/proxies** | Returned by CAS Server after validation | A/B read from trusted CAS response | Identifies user and proxy history | Does not grant application permissions by itself |

The prefixes `ST-`, `PGT-`, `PGTIOU-`, `PT-` help illustrate roles, but **never rely on prefixes instead of validation**. Tickets are bearer secrets: anyone capturing the right value within its lifetime can attempt to present it to the target service.

### 3.1. ST and PT Are Not Interchangeable

~~~text
ST-A:
  issued for: https://portal.example.org/login/cas
  validate via CAS /serviceValidate with exact service A
  => only A, one-time

PT-B:
  issued by CAS /proxy using A's PGT,
  targetService = https://reports.example.org/api/cas
  validate via CAS /proxyValidate with exact service B
  => only B, one-time
~~~

If B receives `ST-A` and calls `/proxyValidate` with service B, CAS must reject it because the service identifier does not match. If A reuses PT-B a second time, CAS must reject it due to its single-use semantics. The fact that **A has an authenticated session** does not allow A to forge a “CAS ticket” by embedding a username into its own JWT.

### 3.2. How Does PGT Differ from PT?

A **PGT** is the “authority to request further proxy tickets,” so the impact of its compromise is far greater than that of a short-lived PT. Under the CAS protocol, a PGT **can issue multiple PTs**, is not single-use, and should expire when the user logs out of CAS per protocol/policy; implementers still need to verify actual ticket registry configuration, logout/revocation, and time-to-live settings.

A **PT** is a specific grant for one targetService B, service-restricted and one-time. Each time A needs to call B, it may need to request a fresh PT depending on the client flow. Do not use PT-B for Payroll API if it was issued for Reports API.

**PGTIOU** is only a **correlation** key, not an access ticket. The PGTIOU value in the CAS validation response must be matched against the same PGTIOU in the HTTPS callback to retrieve the right PGT, avoiding mix-ups between concurrent logins.

## 4. Full Event Sequence from Browser to Reports API

Example service identifiers:

~~~text
CAS Server base URL:  https://cas.example.org/cas
A callback for login: https://portal.example.org/login/cas
A PGT callback URL:   https://portal.example.org/login/cas/proxyreceptor
B targetService ID:   https://reports.example.org/api/cas
A calls business API: https://reports.example.org/api/reports/me
~~~

**Note:** `targetService` is the identifier B supplies when **validating the PT**, and it is **not required** to match the business HTTP endpoint. For example, B might have a fixed validation callback URL `/api/cas`, while the data endpoint is `/api/reports/me`. B must define how it receives PTs and exposes data according to its actual architecture.

### 4.1. Step-by-Step Flow

1. **Browser accesses A**: `GET https://portal.example.org/private`; A has no local authentication yet.
2. **A redirects browser to CAS `/login`** with `service=https://portal.example.org/login/cas`.
3. **CAS authenticates Lan** or uses an existing TGC SSO session; CAS issues an ST for **service A** and redirects the browser back to A: `/login/cas?ticket=ST-...`.
4. **A receives the ST**; when calling CAS `/serviceValidate` (or `/p3/serviceValidate`), A sends `ticket=ST-...`, `service=...A...`, and **`pgtUrl=https://portal.example.org/login/cas/proxyreceptor`**.
5. **CAS validates the ST** for the exact service, unused/unexpired; at the same time CAS checks the policy “is A allowed to proxy?” and validates the HTTPS **PGT callback URL**.
6. **CAS Server opens an HTTPS connection to `pgtUrl`**. **Per the CAS 2.0/3.0 protocol, the callback passes `pgtId` and `pgtIou` via HTTP GET query parameters**, not POST; CAS must verify the endpoint's TLS/PKIX peer certificate and trust. A receives the callback and stores the PGT record keyed by PGTIOU with security commensurate with a secret.
7. **A returns HTTP 200 for a valid callback**; CAS returns the validation response for A's ST with `<cas:proxyGrantingTicket>PGTIOU-...</cas:proxyGrantingTicket>`. If callback/trust fails, there is no usable PGT; do not assume proxying is ready.
8. **A matches the response's PGTIOU with the callback**, retrieving the right PGT; creates/maintains local authentication, and stores the PGT in secure storage bound to the user/session and policy.
9. **User clicks to view Reports**; A checks permission to initiate this feature and never takes `targetService` from arbitrary input.
10. **A calls CAS `/proxy`** over TLS with `pgt=PGT-...` and `targetService=https://reports.example.org/api/cas`. CAS verifies the PGT is valid, checks proxy policy and target service, and issues **PT-B**.
11. **A calls B server-to-server** and presents PT-B per B's CAS client contract (for instance, an HTTPS request carrying `ticket=PT-...` at the CAS-protected endpoint). **Never forward the PGT** to B.
12. **B calls CAS `/proxyValidate` or `/p3/proxyValidate`** with `ticket=PT-B` and **`service=https://reports.example.org/api/cas`**. CAS verifies that the PT is valid, unused, and matches the target, returning the user and proxy chain.
13. **B validates the proxy chain**, accepting only A or trusted proxies; establishes the user principal in the request context if it passes.
14. **B performs its own authorization**: is user Lan allowed to view Lan's reports, is the tenant/resource ID right, and may the data be returned?
15. **B returns data to A**, and A renders the appropriate UI to the Browser; audit logs record user, proxy A, action, outcome, and sanitized correlation ID.

~~~text
Browser        Portal A             CAS Server               Reports B
   |               |                    |                       |
   | GET /private  |                    |                       |
   |-------------->|                    |                       |
   | 302 /login?service=A               |                       |
   |<--------------|                    |                       |
   |----------------------------------->|                       |
   |   login / TGC / ST-A               |                       |
   |<-----------------------------------|                       |
   |--- GET A?ticket=ST-A ------------->|                       |
   |               |-- /serviceValidate(ST-A, service=A,
   |               |                    pgtUrl=A/callback) ---->|
   |               |------------------->|                       |
   |               |                    |-- HTTPS GET A/callback
   |               |<-- pgtId + pgtIou--|                       |
   |               |---- HTTP 200 ----->|                       |
   |               |<-- user + PGTIOU --|                       |
   |               |                    |                       |
   | GET reports   |                    |                       |
   |-------------->|                    |                       |
   |               |-- /proxy(PGT,targetService=B)              |
   |               |------------------->|                       |
   |               |<------ PT-B -------|                       |
   |               |                    |                       |
   |               |----- HTTPS request with PT-B ------------>|
   |               |                    |      /proxyValidate(PT-B,service=B)
   |               |                    |<----------------------|
   |               |                    |------ user, proxies -->|
   |               |                    |                       | authorize
   |               |<------------------------ report data ------|
   |<-- HTML ------|                    |                       |
~~~

**Note:** This is a logical sequence diagram; the callback arrows indicate a **CAS→A** connection, not the browser. The PGT callback data is delivered **out-of-band** from the validation response, and A correlates them via PGTIOU. CAS may invoke the callback before A receives the validation response. Therefore, PGT storage must tolerate asynchrony and race conditions.

## 5. URIs You Must Distinguish

| CAS Server URI | Caller | Ticket / Input | Function |
| --- | --- | --- | --- |
| `/login?service=A` | Browser | CAS TGC or credentials | Issues an ST for A |
| `/serviceValidate?ticket=ST&service=A&pgtUrl=...` | A | ST and optional pgtUrl | Validates **ST**, requests PGT via callback |
| `/p3/serviceValidate` | A | ST and optional pgtUrl | CAS 3 validation returning attributes, same semantics |
| `/proxy?pgt=PGT&targetService=B` | A | PGT held by A | Requests a new PT for service B |
| `/proxyValidate?ticket=PT&service=B` | B | PT-B | Validates **PT or ST** against target service |
| `/p3/proxyValidate` | B | PT/ST | CAS 3 proxy validation with attributes |
| `/logout` | Browser or logout flow | CAS session | Terminates CAS SSO session per policy |

**Do not use `/serviceValidate` for PT-B**: per the CAS protocol, `/proxyValidate` is the endpoint that supports proxy tickets; `/serviceValidate` is the service-ticket validation endpoint. In Apereo CAS 3.0, `/p3/...` variants return attributes. Configure the exact base CAS URL and version; examples may not match every CAS server vendor.

**Example URLs are not real credentials.** Ticket values may appear in query strings per the CAS protocol, so TLS is mandatory; you must redact access logs, reverse-proxy logs, browser history/referrer/caches, traces, and monitoring. A should not expose PT/PGT in response bodies or frontend JavaScript.

## 6. PGT Callback: Proving A Is Actually the Proxying Service

A cannot simply send `service=Portal` and ask for an arbitrary PGT. CAS checks **pgtUrl** to verify that application A controls the callback at the registered HTTPS endpoint.

### 6.1. Four Callback Steps

~~~text
A --> CAS:
  /serviceValidate
    ?ticket=ST-for-A
    &service=https://portal.example.org/login/cas
    &pgtUrl=https://portal.example.org/login/cas/proxyreceptor

CAS --> A over HTTPS GET:
  /login/cas/proxyreceptor
    ?pgtId=PGT-issued-to-A
    &pgtIou=PGTIOU-random

A --> CAS:
  HTTP 200 OK

CAS --> A as ST validation response:
  <cas:proxyGrantingTicket>PGTIOU-random</cas:proxyGrantingTicket>

A:
  lookup PGT by matching PGTIOU
  verify correlation + state + permissions
  store PGT securely for subsequent /proxy
~~~

**Important:** The CAS specification uses **HTTP GET** when CAS delivers `pgtId` and `pgtIou` to the proxy callback. Some docs/implementations have other extensions (including encrypted or direct ticket delivery modes); do not mix those into the standard callback flow. If your CAS Server uses custom features, verify the exact contract and documentation for the running version.

### 6.2. Why HTTPS and PKIX Are Mandatory

CAS sends the **PGT—a sensitive credential—** to the callback; if the endpoint is spoofed or TLS verification is skipped, an attacker can receive the PGT. Per the CAS protocol, `pgtUrl` must be HTTPS; CAS must establish peer trust at minimum via PKIX certificate chain/signature/validity checks. Application A must also ensure the callback URL belongs to an allowlist, has a valid certificate, and routes only to A—never to a user-chosen URL via `?pgtUrl=...`.

On the other hand, **A must defend against forged callbacks**. Because an attacker could try sending GET requests to the callback, A should apply network policy, mTLS, or a reverse-proxy allowlist where feasible, combined with correlating PGTIOU against an ST validation just returned by the trusted CAS. A PGTIOU callback without a matching CAS validation result **must never be used** to establish an authenticated delegated identity.

### 6.3. Race Conditions and Storage

The CAS callback can arrive at A nearly simultaneously with the ST validation response. If A only keeps a single static variable storing the latest PGT, two users logging in at the same time can overwrite each other:

~~~text
ST-Alice -> callback (PGTIOU-1, PGT-1)
ST-Bob   -> callback (PGTIOU-2, PGT-2)

If only "latestPGT" is stored -> users can get mixed up!
Correct: concurrency-safe PGTIOU -> PGT map with TTL.
When validating ST:
  receive PGTIOU-1 -> retrieve PGT-1 matching Alice
  receive PGTIOU-2 -> retrieve PGT-2 matching Bob
~~~

The mapping must prevent replay/key overwrite, enforce a short TTL for orphan IOUs, perform cleanup, and maintain auditability. In a multi-node cluster, a callback hitting a different node from the ST validation requires **shared PGT storage** or proper routing; do not rely solely on in-memory storage when HA is required. Restrict PGT read access by user/session/tenant, and never treat PGTIOU as a user identity.

### 6.4. Can ST Validation Succeed Without a PGT?

Yes, an ST can be validated as a normal login while **lacking permission or failing to obtain a PGT** due to proxy policy, callback TLS, connectivity, or proxy support not being enabled on CAS. Application A may let the user into regular pages, but any feature **calling B on the user's behalf must fail-closed**, never falling back to another user's PGT or a broad-privilege service account.

A response containing `cas:authenticationSuccess` **does not by itself prove** PGT acquisition succeeded; you must observe a valid PGTIOU and its matching PGT callback.

## 7. From PGT to Proxy Ticket for Service B

After login, A holds a valid PGT bound to the user. When the user invokes a feature requiring B:

~~~text
A has PGT-Alice and targetService=B
    |
    v
GET https://cas.example.org/cas/proxy
    ?pgt=PGT-Alice
    &targetService=https://reports.example.org/api/cas
    |
    v
CAS validates PGT + registered service/proxy policy
    |
    +-- SUCCESS: <cas:proxyTicket>PT-for-B</cas:proxyTicket>
    |
    +-- FAILURE: <cas:proxyFailure code="...">...</...>
    |
A receives PT-for-B, calls B over TLS
B validates PT-for-B with CAS for targetService=B
~~~

### 7.1. Sample CAS proxySuccess XML

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:proxySuccess>
    <cas:proxyTicket>PT-demo-target-B</cas:proxyTicket>
  </cas:proxySuccess>
</cas:serviceResponse>
~~~

This is **illustrative mock** XML, not a real ticket. Before trusting a PT, A must verify it came from the configured HTTPS CAS Server, the response corresponds to the in-flight request, the XML parser is hardened, and the result is a genuine success without errors. Never log `PT-...`.

### 7.2. Sample CAS proxyFailure XML

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:proxyFailure code="UNAUTHORIZED_SERVICE">
    Proxy service is not authorized to request this target
  </cas:proxyFailure>
</cas:serviceResponse>
~~~

On errors such as `INVALID_REQUEST`, `UNAUTHORIZED_SERVICE`, or an expired/revoked PGT, A must **never call B with a forged credential**. The frontend can display “Unable to access reports right now” rather than leaking tickets or internal CAS configuration.

### 7.3. TargetService Is an Authorization Boundary

**Wrong:**

~~~java
// Anti-pattern: never turn user input into a CAS targetService.
String targetService = request.getParameter("targetService");
String proxyUrl = casBaseUrl + "/proxy?targetService=" + targetService;
~~~

An attacker could make A request a PT for another service or trick A into sending an HTTP request to an internal host (SSRF/open proxy). **Right:** A maintains a fixed allowlist of targetServices each feature is permitted to call; never concatenate URLs from browser input, especially not from user-supplied Host or forwarded headers.

In a production app, for each business capability:
- Backend feature `GET_MY_REPORTS` → targetService `https://reports.example.org/api/cas`.
- Backend feature `VIEW_PAYROLL` → a distinct targetService if both user and A are authorized; never fall back by default.
- No approved entry → deny.
- Never follow 3xx redirects to an origin outside the allowlist when sending a PT. Send the ticket over TLS to the exact endpoint, verifying certificate and host.
- B verifies the HTTP request URI and corresponding resource authorization; a PT for B **does not grant unlimited permissions inside B**.

## 8. Service B Validates the Proxy Ticket and Proxy Chain

B must **never** trust an `X-CAS-User` HTTP header fabricated by A. Instead, B receives the PT and calls CAS `/proxyValidate` with **`service` matching B's exact identifier**; CAS returns a response containing the user and proxy chain if valid.

~~~text
Service A -- PT-B --> Service B
                         |
                         | /proxyValidate(ticket=PT-B, service=B)
                         v
                       CAS Server
                         |
                         +-- PT issued for B?
                         +-- unused/not expired?
                         +-- valid user?
                         +-- which proxy chain?
                         |
                         v
                cas:authenticationSuccess
                cas:user=Lan
                cas:proxies=[https://portal.example.org/.../proxyreceptor]
                         |
Service B:
  - verify entire proxy chain is allowed
  - map Lan to B's user/tenant
  - resource-level authorization
  - return data or 403
~~~

### 8.1. Sample CAS proxyValidate Response

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>lan</cas:user>
    <cas:proxies>
      <cas:proxy>
        https://portal.example.org/login/cas/proxyreceptor
      </cas:proxy>
    </cas:proxies>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**Explanation:** `cas:user` is the identity authenticated by CAS; `cas:proxies` lists the proxying services in the chain. B needs a policy deciding which proxies are accepted. Never use a username from an HTTP header if CAS validation has failed.

### 8.2. Proxy Chain Ordering and Length

The CAS protocol requires the proxy list to reflect traversal order: **the most recently traversed proxy appears first**. In A→Middle→B, B may see Middle followed by A. B must decide whether it accepts A directly, Middle, or the A+Middle chain according to exact rules; do not check only the first element or “any valid proxy” if policy requires the full chain.

Example:

~~~text
cas:proxies = [
  "https://gateway.example.org/cas/proxyreceptor",
  "https://portal.example.org/login/cas/proxyreceptor"
]

B trusts only Portal directly:
  -> DENY (unauthorized Gateway intermediary present)

B trusts exact sequence Gateway then Portal:
  -> MAY ACCEPT, still must check user/tenant/action.
~~~

### 8.3. Reject, AcceptAny, and Named Proxy Policies

Spring Security CAS documentation describes these `CasProxyDecider` types:
- `RejectProxyTickets`: rejects all proxied credentials. This is the safe choice for services requiring direct CAS login only.
- `NamedCasProxyDecider`: accepts a configured list of trusted proxies (check version-specific semantics and chain behavior).
- `AcceptAnyCasProxy`: accepts any proxy chain; **unsuitable** for B holding sensitive data unless backed by another strong trust boundary.

**Best practice:** The CAS service registry must enforce that **A is allowed to request PGT/PT**, and B must independently validate the **proxy chain** on every request. Either check alone is insufficient. Never configure “accept any proxy” to work around an unverified hostname or PGT callback error.

### 8.4. A PT Does Not Automatically Grant Report Access Either

Even after B receives a valid PT from CAS and approved A, B still needs to verify:
- Does user Lan have an active internal account at B?
- Is Lan's tenant permitted to access the requested report?
- Does B's resource owner/scope/role policy permit `GET /reports/me` or `GET /reports/{id}`?
- Are rate limits, auditing, read/write separation, and specific delegation policies enforced?
- If A is a multi-tenant application, does mapping identity by CAS issuer/service context prevent username collisions?

A CAS ticket proves the **authentication/delegation path**, not “Lan is an admin” or “A can manipulate everyone's data.”

## 9. Spring Security CAS Configuration: How Do A and B Differ?

Spring Security CAS documentation describes these core components:
- `CasAuthenticationEntryPoint`: redirects A's browser to CAS `/login` when authentication is needed.
- `ServiceProperties`: defines A's callback URL; `service` must match the exact CAS service identifier.
- `CasAuthenticationFilter`: receives `ST`/`PT` at the configured URL, builds an authentication token to validate; can handle the **proxy receptor** when supplied with PGT storage.
- `CasAuthenticationProvider`: authenticates via the CAS Client `TicketValidator` and loads application user details/authorities.
- `Cas20ServiceTicketValidator`: validates STs for standard login flows.
- `Cas20ProxyTicketValidator`: used when proxy support/PGT callbacks and PT validation are needed.
- `ProxyGrantingTicketStorage`: holds PGTs keyed by PGTIOU; wired into both `CasAuthenticationFilter` and the ticket validator.
- `CasProxyDecider`: decides which proxy chains to trust, especially on B.

**Caution:** Spring CAS docs still show many historical XML configuration snippets. They are useful for understanding components and flow, but **are not a Spring Boot 3.5 application you can copy-paste and run as-is**. You must use compatible `spring-security-cas` and CAS Client versions, and configure Spring Security 6.5 APIs/filters using tested Java or XML/bean definitions.

### 9.1. Components on A

Service A plays two roles:
1. **Receives ST login**: A's CAS filter/AuthenticationProvider validates the browser's ST to create a local authenticated session.
2. **Acts as proxying client**: A's ticket validator requests a PGT via `pgtUrl`; A's filter receives the CAS callback, storage holds the PGT, and the backend client uses the PGT to request a PT for B.

**Historical XML configuration snippet illustrating wiring relationships (not a complete pom/app):**

~~~xml
<!-- Verify APIs/constructors and libraries against your exact version. -->
<bean id="pgtStorage"
      class="org.apereo.cas.client.proxy.ProxyGrantingTicketStorageImpl"/>

<bean id="proxyTicketValidator"
      class="org.apereo.cas.client.validation.Cas20ProxyTicketValidator">
  <constructor-arg value="https://cas.example.org/cas"/>
  <property name="proxyCallbackUrl"
            value="https://portal.example.org/login/cas/proxyreceptor"/>
  <property name="proxyGrantingTicketStorage" ref="pgtStorage"/>
</bean>

<bean id="casAuthenticationProvider"
      class="org.springframework.security.cas.authentication.CasAuthenticationProvider">
  <property name="ticketValidator" ref="proxyTicketValidator"/>
  <!-- serviceProperties, authenticationUserDetailsService,
       key, and other required components must also be configured -->
</bean>

<bean id="casAuthenticationFilter"
      class="org.springframework.security.cas.web.CasAuthenticationFilter">
  <property name="proxyGrantingTicketStorage" ref="pgtStorage"/>
  <property name="proxyReceptorUrl"
            value="/login/cas/proxyreceptor"/>
  <!-- authenticationManager and filter chain are still required -->
</bean>
~~~

**Mandatory rule:** `Cas20ProxyTicketValidator.proxyCallbackUrl` must point to the **exact public HTTPS URL** that CAS Server calls, and `CasAuthenticationFilter.proxyReceptorUrl` must match **A's callback receiver path** (especially behind a reverse proxy). Both the ticket validator and filter must share **the same PGT storage**. Never use a global map outside the framework to store “the current PGT.”

### 9.2. A Must Know Which User Owns Each PGT

In stateful applications, the Spring CAS provider/filter can store an authentication result containing the CAS Assertion and ticket-related information. From the proxy client layer, you must look up the PGT/PGTIOU associated with the exact authenticated user/session. If no PGT exists because the callback failed, never grab “the most recent PGT” from a singleton.

PGT storage must:
- Protect secrets at rest/in transit, encrypt if needed, and enforce least-privilege RBAC.
- Enforce TTL, cleanup of expired entries, and bounded capacity.
- Handle concurrency/races and out-of-order callbacks.
- Support distributed session/cache when clustered (if needed).
- Never log PGT/PGTIOU values directly in request logging.
- Revoke/clean up when the user logs out of CAS or app policy ends the session.
- Avoid exposing a “get PGT by username” API to unprivileged code.

In Spring docs, `ProxyGrantingTicketStorageImpl` is an in-memory example; the docs warn **not to use the default for production storage** and that cleanup is required. Choosing Redis/DB/KMS or another implementation must fit the ticket lifecycle and security controls.

### 9.3. B: Receive PT via CAS Validation, Then Authorize

B needs `Cas20ProxyTicketValidator` or an equivalent validator rather than just `Cas20ServiceTicketValidator`. B sets **its own service URL** in `ServiceProperties`/`ServiceAuthenticationDetails` and authorizes the proxy chain via `CasProxyDecider`. For stateless APIs, the CAS client filter can process the request ticket on every call, provided replay/idempotency and credential transport are properly protected.

**Bean responsibility diagram** (conceptual, insufficient to run standalone):

~~~text
B SecurityFilterChain
  -> CasAuthenticationFilter
       |__ serviceUrl resolver for B
       |__ AuthenticationManager
            |__ CasAuthenticationProvider
                 |__ Cas20ProxyTicketValidator(CAS base URL)
                 |__ NamedCasProxyDecider(approved A callback URLs)
                 |__ user/authority service
  -> method/API authorization by user + proxy identity
~~~

Configuring Spring Security CAS for a **stateless service** differs from a stateful Portal; CAS docs describe `authenticateAllArtifacts`, `ServiceAuthenticationDetailsSource`, and CAS stateless identifiers. Do not assume that merely setting `sessionCreationPolicy(STATELESS)` will make an API validate PTs properly. You need CAS-specific filter/provider/ticket-validation wiring and a security review of request URL/service identity.

### 9.4. Dependencies and Versions

When setting up Spring Boot 3.5.x with Java 17, CAS integration typically requires the **Spring Security CAS module and compatible Apereo CAS Client libraries**, in addition to `spring-boot-starter-security`/`spring-boot-starter-web`. There is no standard property like `spring.security.cas.proxy.enabled=true` that wires the entire flow automatically. Packages/classes in Spring documentation may differ across versions; inspect the Maven dependency tree/APIs before building your `SecurityFilterChain`.

**Modern alternative:** If the core requirement is “API A calls API B on behalf of a user” and B is not required to speak the CAS protocol, consider **OAuth2 Token Exchange / on-behalf-of** with proper audiences/scopes/consent and token validation. Never build a custom converter from CAS PGT to JWT without a trusted Authorization Server.

## 10. CAS Server Policy: Do Not Issue PGTs Indiscriminately

The CAS service registry must contain administrator-approved entries:

~~~text
Registered CAS Service A
  serviceId = https://portal.example.org/login/cas
  allowProxy = true, conditional
  approved pgtUrl = https://portal.example.org/login/cas/proxyreceptor
  allowed/approved target services (per CAS policy)
  attributes released = minimal

Registered CAS Service B
  serviceId = https://reports.example.org/api/cas
  mayAcceptProxyTickets = true (per CAS implementation)
  trusted proxiers = Service A (and specific chain)
~~~

**This is pseudoconfiguration**, not valid JSON/YAML for every Apereo CAS version. CAS Server/registry supports proxy policies depending on version and registration type. Modern Apereo deployments may **deny proxying by default** if a service is not approved; never assume “CAS Proxy is in the protocol” means any application can obtain a PGT.

### 10.1. Policies to Lock Down

- Service IDs/`targetService` registered in CAS—no `.*` regexes or broad host wildcards.
- Only approved Service A may request a PGT, and only via an approved HTTPS callback.
- Callback certificates must be PKIX-verified by CAS; never bypass the trust manager.
- Only PTs for allowed targetServices; if the CAS registry does not enforce this strictly enough, A must also enforce its own allowlist.
- B must deny unknown proxy chains—never `AcceptAnyCasProxy` without a compensating trust boundary.
- Ticket TTL, PGT inactivity, session logout revocation, audit, and rate limits must align with the threat model.
- Downstream authorization (B) must enforce user/tenant permissions; CAS proxy is not a resource scope engine.

### 10.2. Prevent pgtUrl from Becoming SSRF

Because CAS **actively calls pgtUrl**, a service able to specify an arbitrary pgtUrl could make CAS Server send requests to internal addresses or an attacker, or leak the PGT. Restrict pgtUrl via the service registry and egress/URL validation policy, block redirects to internal/link-local/metadata IPs, allow HTTPS only, and verify certificate chain/host. Never accept `https://example.org.evil.test` based on substring matching.

A must also prevent users from altering `pgtUrl`, the CAS base URL, or targetService via query parameters. Never enable trust-all certificate modes for debugging.

## 11. Standalone Java 17: Policy for A Calling B on Behalf of a User

The following code **runs on JDK 17** without Maven or a CAS Server. It simulates the decision of **whether to accept targetService B and the proxy chain** before making a delegated request. Its goal is to teach “allowlist and fail-closed” policy; it does **not** mint real PGTs/PTs, parse CAS XML, or validate TLS or security assertions. In production, you must use standard CAS Client/Spring CAS validation.

**File `CasProxyPolicyDemo.java`:**

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CasProxyPolicyDemo {

    record Request(String user, String action, String targetService) {}

    static final String REPORTS =
            "https://reports.example.org/api/cas";
    static final String PAYROLL =
            "https://payroll.example.org/api/cas";
    static final String PROXY_A =
            "https://portal.example.org/login/cas/proxyreceptor";

    // Only approved actions map to a targetService.
    static final Map<String, String> APPROVED_ACTIONS = Map.of(
            "READ_MY_REPORTS", REPORTS);

    static final Set<String> ENABLED_USERS = Set.of("lan");

    static String authorizeProxyRequest(Request request) {
        if (!ENABLED_USERS.contains(request.user())) {
            return "DENY_USER";
        }
        String approved = APPROVED_ACTIONS.get(request.action());
        if (approved == null || !approved.equals(request.targetService())) {
            return "DENY_TARGET";
        }
        return "ALLOW_PGT_TO_PT";
    }

    // The proxy chain must be confirmed by CAS, never read from HTTP headers.
    static String authorizeBackend(
            String validatedCasUser,
            List<String> validatedProxyChain,
            String resourceOwner) {
        if (!ENABLED_USERS.contains(validatedCasUser)) {
            return "DENY_USER";
        }
        if (!validatedProxyChain.equals(List.of(PROXY_A))) {
            return "DENY_PROXY_CHAIN";
        }
        if (!validatedCasUser.equals(resourceOwner)) {
            return "DENY_RESOURCE";
        }
        return "ALLOW_REPORT";
    }

    public static void main(String[] args) {
        System.out.println("A valid=" + authorizeProxyRequest(
                new Request("lan", "READ_MY_REPORTS", REPORTS)));
        System.out.println("A otherTarget=" + authorizeProxyRequest(
                new Request("lan", "READ_MY_REPORTS", PAYROLL)));
        System.out.println("A disabled=" + authorizeProxyRequest(
                new Request("bob", "READ_MY_REPORTS", REPORTS)));

        System.out.println("B trusted=" +
                authorizeBackend("lan", List.of(PROXY_A), "lan"));
        System.out.println("B unknownProxy=" +
                authorizeBackend("lan",
                        List.of("https://evil.example/proxy"), "lan"));
        System.out.println("B extraHop=" +
                authorizeBackend("lan",
                        List.of("https://gateway.example/proxy", PROXY_A),
                        "lan"));
        System.out.println("B otherOwner=" +
                authorizeBackend("lan", List.of(PROXY_A), "bob"));
    }
}
~~~

Run:

~~~bash
javac CasProxyPolicyDemo.java
java CasProxyPolicyDemo
~~~

**Exact stdout:**

~~~text
A valid=ALLOW_PGT_TO_PT
A otherTarget=DENY_TARGET
A disabled=DENY_USER
B trusted=ALLOW_REPORT
B unknownProxy=DENY_PROXY_CHAIN
B extraHop=DENY_PROXY_CHAIN
B otherOwner=DENY_RESOURCE
~~~

**Explanation of each result:**

1. A is only permitted to request a PT for Reports when the user is active and `READ_MY_REPORTS` maps to the exact targetService.
2. A rejects the Payroll target even though the user specified `READ_MY_REPORTS`; arbitrary target selection is disallowed.
3. User Bob is not simulated as active, so A denies.
4. B accepts the **CAS-validated** proxy chain consisting solely of A, and user Lan may only read Lan's data.
5. An unknown proxy is rejected by B.
6. The chain A→Gateway→B has an extra intermediary and is rejected by B because policy allows A directly only.
7. User Lan cannot read Bob's report simply because a valid PT exists.

**Limitation:** `validatedCasUser` and `validatedProxyChain` in the demo are **assumed inputs coming from successful CAS validation**. If production reads them from HTTP headers, request parameters, or unvalidated XML, an attacker can supply arbitrary values and bypass checks. The demo cannot prove real CAS tickets; it is only a unit test for *post-protocol authorization policy*.

## 12. Spring Boot 3.5/Java 17: Application B Behind CAS Validation

It is an architectural mistake to put all CAS ticket validation inside business controllers instead of filters/providers. With Spring Boot 3.5.x, attach the CAS adapter/filter in `SecurityFilterChain` and only let MVC controllers execute after the authentication context has been populated.

**The `ReportsController.java` code below is a Spring MVC skeleton**; it compiles in a Spring Boot web + security project, but **does not implement the CAS filter/ticket validation itself**. Without the CAS filter, `Authentication` could originate from another mechanism and **must not be assumed CAS-proxy-validated**. You must configure a dedicated CAS `SecurityFilterChain` and guard the authentication type before production.

~~~java
package demo;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {

    // Use only when CAS authentication/provider is configured.
    // In production, verify the authenticated CAS token,
    // approved proxies, tenant membership, and resource access.
    @GetMapping("/api/reports/me")
    public ResponseEntity<Map<String, String>> myReports(
            Authentication authentication) {

        if (authentication == null || !authentication.isAuthenticated()) {
            return ResponseEntity.status(401)
                    .body(Map.of("error", "unauthenticated"));
        }
        // Illustrative API response only, NOT a complete
        // authorization decision for CAS proxy.
        return ResponseEntity.ok(Map.of(
                "user", authentication.getName(),
                "status", "authenticated"));
    }
}
~~~

**Must be clearly understood:** The code above performs no CAS PT validation, proxy chain verification, or resource ownership checks; therefore it **must not be deployed for sensitive data endpoints** without the corresponding security layer. In a real system, check `CasAuthenticationToken`/details as well as tenant/role permissions before querying the DB. If a token came from a direct CAS user login while the action requires proxied authentication, distinguish and reject it.

### 12.1. What Must Be Configured on A

- `CasAuthenticationEntryPoint` redirecting browsers to CAS `/login`.
- `ServiceProperties` with A's exact callback service URL, registered in CAS.
- `CasAuthenticationFilter` receiving STs and handling the `proxyReceptorUrl` PGT callback.
- `CasAuthenticationProvider` using `Cas20ProxyTicketValidator`, `proxyCallbackUrl`, and `ProxyGrantingTicketStorage`.
- `AuthenticationUserDetailsService` loading only approved roles/permissions; never blindly turning arbitrary group strings into admin.
- Storage with concurrency-safe IOU correlation, TTL, secure cleanup, and cluster support.
- Backend client service obtaining PTs for approved targetServices without ever sending raw PGTs to B.

### 12.2. What Must Be Configured on B

- `ServiceProperties.service` set to B's exact service identifier, never derived from an arbitrary Host header.
- CAS filter/provider using `Cas20ProxyTicketValidator` (or version/client equivalent) and a deny-by-default `CasProxyDecider`.
- ST/PT validation over CAS Server TLS; verifying CAS `authenticationSuccess`, user, proxies, service binding, and ticket replay/time.
- Separate API authorization and identity linking. When receiving a PT, require both user and proxy chain to match policy.
- Stateless requests must not share sessions across users; CAS PT is a one-time bearer credential, so the call lifecycle must be designed accordingly.
- Block direct access via `X-Authenticated-User` headers and ensure no other filter chain uses `permitAll` on the same URL.

**Never assume that succeeding at Spring Security CAS authentication means the user is allowed to read all data.** The CAS provider authenticates; domain authorization on B enforces the rest.

## 13. Why Must targetService Be Exact?

A CAS PT is bound to the targetService specified when A requested the PT. B validates the PT using B's own exact service identifier.

~~~text
A requests from CAS:
  /proxy?pgt=PGT-...&targetService=https://reports.example.org/api/cas

CAS issues:
  PT-... specifically for https://reports.example.org/api/cas

B validates:
  /proxyValidate?ticket=PT-...&service=https://reports.example.org/api/cas
  -> YES if valid and unused

B uses wrong service:
  /proxyValidate?ticket=PT-...&service=https://payroll.example.org/api/cas
  -> INVALID_SERVICE / failure
~~~

Distinguish the `targetService` identifier from the business call endpoint URL. In CAS clients, the service URL is sometimes built dynamically from the request; backends behind a proxy must configure/canonicalize scheme/host/port/path accurately and trust forwarded headers only from a **trusted reverse proxy**. If B listens on `http://service-b:8080` while its public CAS service ID is `https://reports.example.org/api/cas`, validation fails due to mismatch. **Do not work around this with wildcard validation**; fix the service identity/proxy configuration.

### 13.1. One-Time Validation and Retries

PTs are designed for **single-use validation**. If A calls B and times out after B has already validated the PT, A **cannot** retry with the same PT and expect CAS to accept it a second time. You need logic to acquire a fresh PT, business idempotency keys, and a controlled retry policy. For write operations (payments/updates), never blindly replay the business operation just because the ticket validation response was lost without deduplication; delegated authentication and **business idempotency** are separate concerns.

### 13.2. Never Reuse PGTs Across Users

A PGT is bound to a specific user/session. A service A serving hundreds of users must associate PGTs with authenticated contexts via secure keys, never reading a global `currentPGT`. Upon session expiry or logout, handle revocation/cleanup and avoid queuing long-running jobs using the credentials of a user whose session has ended. If a background job runs post-logout, use an approved workload authorization model rather than silently relying on a lingering PGT.

## 14. Multi-Hop Proxy Chains: A → B → C

A more complex scenario: Portal A needs Reports B, and B in turn needs to call Document Store C on the user's behalf. For B to proxy onward, it must be **authorized** and able to request its own PGT when validating the PT it received, using B's corresponding `pgtUrl`.

~~~text
Lan Browser -> A
  CAS ST-A validation
      -> A PGT-A
  A /proxy(PGT-A,target=B)
      -> PT-B
  B /proxyValidate(PT-B,service=B,pgtUrl=B/receptor)
      -> B PGT-B (if allowed)
  B /proxy(PGT-B,target=C)
      -> PT-C
  C /proxyValidate(PT-C,service=C)
      -> cas:user=Lan
      -> cas:proxies has B before A (most recent first)
~~~

Holding PT-B does **not** let B re-sign or rename it into PT-C. B must obtain PGT-B via the CAS proxy callback and request PT-C from CAS, or use another approved delegation mechanism.

### 14.1. Multi-Hop Chain Policy

C can:
- Accept only direct user CAS STs and reject all PTs (deny all proxies).
- Allow a single hop from A, but not via B.
- Allow the exact `[B, A]` chain in the order returned by CAS.
- Allow a set of proxies with hop-count, tenant, or action limits.

**Do not validate chains with** `proxies.contains("https://portal.example.org")` if an untrusted intermediary proxy is also present; one good element does not make the whole chain safe. Do not allow proxy identities matched by unvalidated substrings or host suffixes.

### 14.2. What If B Is Not Granted a PGT?

B cannot proxy onward to C even if B successfully validated PT-B. This is a sound security design: permission to **receive a delegated identity** is distinct from permission to **further delegate**. CAS Server needs explicit registry/PGT policies per service hop. B should return an appropriate business error rather than silently substituting a service account or bypassing proxy policy.

## 15. Authentication vs. Authorization and Auditing

Inside Reports B:

~~~text
CAS proxyValidate passes:
  principal=lan
  proxyChain=[Portal A]

Still not enough!
  |
  +-- internal identity link for CAS user?
  +-- user is active?
  +-- tenant scope matches?
  +-- action READ_MY_REPORTS allowed?
  +-- report belongs to Lan?
  +-- sensitive data redaction/purpose limitation?
  +-- rate limit / audit?
  |
  v
  200 data or 403
~~~

**CAS authentication** supplies the trusted user/proxy chain; **authorization** decides the specific action. Just because A is allowed to call B on Lan's behalf does not mean B can return Bob's data. If CAS username `lan` can exist across multiple CAS realms/tenants, B must include the CAS server issuer/registration in the identity link rather than relying on bare username/email alone.

**Audits should record** tenant, internal user ID, A/B service IDs, normalized proxy chain, business action, sanitized resource ID, correlation ID, and outcome. **Never log** ST/PT/PGT/PGTIOU, cookies, raw XML attributes, or credentials. Because CAS tickets may travel in query parameters, redact them across ingress, app access logs, APM, tracing, error dumps, and support screenshots.

## 16. Design Option Comparison

| Option | When to Use | Advantages | Limitations |
| --- | --- | --- | --- |
| **CAS Proxy (PGT/PT)** | Both A/B are CAS services, delegated user identity is needed, CAS Server/registry supports it | Fits CAS trust, PT is target-bound and single-use, provides proxy chain | Callback/TLS/storage setup is complex; lacks standard OAuth scopes |
| **A's service account** | B only needs to know system A is calling, actions aren't strictly “as user” | Simple machine-to-machine, independent of user session | Does not represent user permissions; passing user headers needs extra auth/audit design |
| **OAuth2 Token Exchange / OBO** | Modern APIs already using an Authorization Server with designed audiences/scopes/delegation | Scoped tokens for resources, easy API integration, standardized policy | Requires AS/RS support; cannot convert CAS PT to OAuth token directly |
| **User direct-login to B** | Browser can navigate directly to B and B supports CAS | A does not need to hold a PGT | Does not solve server-to-server calls without a browser |
| **Forwarding CAS ST-A to B** | **Never use** | None | ST is service-bound and one-time; B must reject |
| **Using PGT-A directly as B bearer token** | **Never use** | None | Exposes credential capable of minting many PTs |

**Choose based on “who is acting” and “with what permissions”**: If the system specifically needs “A acting on behalf of Lan at B” and both are CAS-enabled, use CAS Proxy with chain validation. For system jobs not tied to a user, a service account with scoped authorization may fit better. If a greenfield architecture uses OAuth2/OIDC APIs, consider dedicated delegation standards rather than mixing protocols without proper trust translation.

## 17. Positive/Negative Testing with a CAS Sandbox

| Test | Execution | Expected Outcome |
| --- | --- | --- |
| Valid ST login | User logs into A, CAS issues ST-A for exact service | A authenticated |
| ST replay | Resubmit ST-A after validation | CAS rejects |
| ST wrong service | Validate ST-A with service B | `INVALID_SERVICE` / fail |
| A omits pgtUrl | Normal ST validation | Login may pass, but no PGT for proxying |
| A PGT policy denied | A not permitted to proxy by CAS | No PGT issued; B call fails closed |
| PGT callback HTTPS/TLS error | CAS does not trust callback cert or cannot reach it | No usable PGT |
| Callback differs from approved URL | User/attacker-controlled `pgtUrl` | Deny, do not send PGT |
| Callback returns non-200 | Receptor errors out | PGT issuance fails |
| Callback arrives before validation response | Race between CAS callback and A | Storage correlates PGTIOU correctly |
| Concurrent Alice/Bob | Two interleaved PGTIOUs | No PGT swap between users |
| PGTIOU mismatch | Callback has PGT-1 but response has PGTIOU-2 | No correlation, no proxy |
| PGT leaked in logs | Ticket appears in URL/logs | Security incident; rotate/revoke and redact logs |
| /proxy valid PGT target B | A requests PT-B | CAS returns PT-B |
| /proxy expired/revoked PGT | A tries requesting PT with bad PGT | ProxyFailure |
| /proxy unknown target | A requests PT for unknown URL | CAS/A policy denies |
| PT-B valid for B | A presents PT-B; B calls proxyValidate(service=B) | CAS authSuccess + proxies |
| PT-B presented to Payroll | Another service validates with Payroll service | Fails service binding |
| PT-B replay | Validate PT-B a second time | CAS rejects |
| B uses /serviceValidate for PT | B misconfigured validator | Fails to process PT per protocol |
| Empty proxy chain when B requires A | Direct user ST sent to B | B policy rejects if only A is allowed |
| Proxy chain has unknown hop | PT reaches B via unapproved gateway | B rejects |
| Valid proxy chain A but disabled user | CAS authSuccess, internal account locked | 403 |
| User Lan reads Bob's report | B has valid PT but different resource owner | 403 |
| CAS logout | User CAS SSO session terminates | PGT lifetime/revocation per protocol; retry fails |
| CAS Server unavailable | /proxy or /proxyValidate times out | Fail-closed, never synthesize user headers |
| Cross-node callback | CAS callback hits node 2, validation hits node 1 | Shared PGT storage or safe failure |
| Wrong reverse proxy host | A/B service URLs generate internal hostnames | Fix public CAS service IDs, never disable validation |
| PT redirected to external host | B returns HTTP 302 to attacker | A must not forward ticket/cookie across redirect |

### 17.1. Testing Without False Positives

Changing `targetService` after a PT is issued causes CAS validation to fail, which proves target binding. To test **proxy chain policy** separately, use a valid CAS sandbox to issue a real PT with a proxy chain outside the allowlist and verify B still rejects it. Simply sending fake XML to B without going through CAS may fail earlier at ticket validation; that test does not prove `NamedCasProxyDecider`.

For PGT callbacks, specifically test **races, concurrency, and cleanup**. A Java Map unit test does not prove CAS HTTPS GET/PKIX behavior, so integration tests against a CAS sandbox with valid TLS certificates are required.

## 18. Common Errors and Troubleshooting

| Symptom | Possible Cause | Check |
| --- | --- | --- |
| A logs in but cannot call B | A failed to obtain PGT | `pgtUrl`, callback/200, proxy policy, PGTIOU mapping |
| Missing `cas:proxyGrantingTicket` | CAS did not issue PGT | HTTPS callback PKIX, registered service, allowProxy |
| `INVALID_PROXY_CALLBACK` | URL/certificate/endpoint rejected | Public HTTPS URL, chain trust, redirects, allowed callback |
| PGTIOU mismatch | Race, wrong storage, wrong node | Shared store, concurrency, TTL, correlation |
| CAS `/proxy` returns `UNAUTHORIZED_SERVICE` | A/target not authorized | CAS service registry/proxy policy |
| CAS `/proxy` returns `INVALID_REQUEST` | Missing `pgt` or `targetService` | Correct parameters, no secrets in logs |
| B reports invalid ticket | PT expired/replayed/wrong service | Correct `/proxyValidate`, service URL, one-time use |
| B sees unexpected proxy chain | Gateway/relay or trust misconfiguration | Exact trusted proxies, hop ordering |
| B login succeeds but returns 403 | App authorization denied | User status, tenant, resource ownership |
| A loses PGT after restart | Non-persistent in-memory storage | Secure distributed storage/lifecycle strategy |
| Fails on only one node | Callback and validation hit different nodes | Shared PGTIOU mapping or session affinity |
| Fails behind reverse proxy | scheme/host/port mismatch | CAS serviceId/pgtUrl, trusted forwarded headers |
| Retried PTs fail | CAS PT is one-time | Request fresh PT, idempotency/retry logic |
| B still callable after logout | PGT/session/ticket lifecycle or app cache | CAS logout revocation, B request validation, cache invalidation |
| B accepts user from attacker header | B trusts `X-User` without CAS validation | Remove header-based trust, enforce CAS validation |
| App debug logs contain PT/PGT | Unredacted URL query/tracing | Sanitization + incident response |

**Diagnostic order:** ST validation on A → pgtUrl trust → CAS callback GET pgtId/pgtIou → PGTIOU correlation → /proxy target policy → PT presentation → B /proxyValidate exact service → proxy chain policy → B business authorization. Never fix errors on B by disabling CAS validation or accepting any proxy.

## 19. Security Hardening and Runbook

**PGT is a high-sensitivity credential:**
- Store in a secret-aware store or encrypted storage, accessible only to A's runtime for the right user/session.
- Never print PGT/PT/ST in `toString()`, exceptions, tracing tags, URLs sent to the browser, audit events, or support tickets.
- Use HTTPS to CAS and B, validate server certificates; protect callback TLS/PKIX and never use a trust-all SSL context.
- Enforce least privilege for A and B, deny-by-default CAS registry, and targetService allowlists.
- Manage TTL/cleanup, logout revocation, cache validity, and race/session expiration.
- Block open redirects when sending PTs; prevent callback SSRF, `X-Forwarded-Host` spoofing, and `serviceId` wildcards.
- Monitor: PGT acquisition failures, callback TLS failures, /proxy unauthorized, PT validation errors, trusted proxy rejections, user entitlement 403s, and ticket replays.
- Keep audit event metadata separate from bearer secrets.

### Runbook When a PGT/PT Is Compromised

1. **Containment:** revoke the PGT/close the CAS session or apply CAS revocation policy, disable affected accounts/services if needed; stop service A from issuing further PTs.
2. **Scope:** identify affected users/sessions, CAS service registry entries, targetServices B, exposure window, logs/traces/backups, and calls made.
3. **Credentials:** handle ticket lifecycle, and rotate keys/trust stores when compromise is evidenced—do not confuse rotating a TLS cert with immediately revoking all issued PGTs.
4. **Audit:** use metadata like correlation ID, trusted source IP, target service, action, and status; do not copy live tickets into broader-access locations.
5. **Remediation:** redact logs, tighten allowlists, enforce egress TLS, tighten proxy chain policies, fix storage permissions/TTL/cleanup, and add regression tests.
6. **Notification:** coordinate with owners of CAS, A, and B, plus privacy/security per organizational process.
7. **Verification:** verify `/proxy` fails with the old PGT and B rejects the old PT; confirm there is no evidence of unauthorized user access.

## 20. Hands-On Exercises

**Exercise A – Identify credentials.** Explain how ST, PGT, PGTIOU, and PT differ; which are single-use and which can request multiple tickets; explain why A's `JSESSIONID` cannot serve as B's credential.

**Exercise B – Draw the flow.** Diagram the sequence of CAS login to A, `/serviceValidate` with `pgtUrl`, CAS HTTPS **GET callback**, validation response with PGTIOU, A `/proxy`, and B `/proxyValidate`. Mark exactly where the browser is involved and where communication is server-to-server.

**Exercise C – Java 17.** Run `CasProxyPolicyDemo.java` and verify the seven-line stdout. Add a new targetService without adding it to `APPROVED_ACTIONS` and prove `DENY_TARGET`. Explain why this Java test does not verify CAS XML/TLS.

**Exercise D – Concurrency.** Alice and Bob log in simultaneously; PGTIOU-1 and PGTIOU-2 callbacks hit node 2 while validation responses hit node 1. Design shared storage with TTL, atomic lookup, and cleanup to prevent PGT mix-ups.

**Exercise E – Proxy chain.** B only accepts A. CAS confirms chain `[Gateway, A]`. Should B accept just because A is present? Why? Adjust the policy to accept *exactly* the two-hop chain if business-approved.

**Exercise F – Endpoint compatibility.** Compare B calling `/serviceValidate` vs. `/proxyValidate` when presented with a PT. Explain why targetService and service must match.

**Exercise G – Security review.** A user supplies `targetService=https://internal.example/metadata` or `pgtUrl=https://attacker.example/capture`. Name the two risks and the policy layers that must block them.

**Exercise H – Business permissions.** B verifies Lan's PT via A, yet the request asks to read Bob's report. Why is 403 still correct? Design tenant/resource ownership checks.

**Exercise I – Retries and logout.** B validated the PT successfully, but A timed out. Can A reuse the PT? Is an idempotency key needed? If the user logs out of CAS, how should the PGT be handled?

**Exercise J – Technology selection.** Your organization is building new APIs using OAuth2 only. Compare CAS Proxy against service accounts and OAuth2 Token Exchange/OBO: which fits resource scopes, audiences, and consent?

**Completion criteria:** Learners can explain the chain **ST-A → PGT callback/PGTIOU → PGT-A → PT-B → /proxyValidate → proxy chain policy → authorization at B**, upholding invariants **HTTPS, exact service/target binding, one-time PT, PGT secrecy, allowlists, trust, and fail-closed**.

## 21. Official References

- Apereo CAS Protocol Specification 3.0.3 – sections 2.5 proxy callback, 2.6 proxyValidate, 2.7 proxy, 3.1–3.4 ST/PT/PGT/PGTIOU: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- Apereo CAS – Proxy Authentication, use case where Service A calls backend B with a PT: https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html
- Apereo CAS – Registered Service Proxy Policy: https://apereo.github.io/cas/development/services/Configuring-Service-Proxy-Policy.html
- Spring Security – CAS Authentication, “Authenticating to a Stateless Service with CAS” and ProxyGrantingTicketStorage/Cas20ProxyTicketValidator: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security 6.5 – CAS Authentication versioned reference: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/cas.html
- CAS Client / Apereo CAS documentation portal: https://apereo.github.io/cas/
- RFC 8693 – OAuth 2.0 Token Exchange (an alternative solution, not CAS Proxy): https://www.rfc-editor.org/rfc/rfc8693
- OWASP – Secrets Management Cheat Sheet (protecting PGTs/credentials): https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
