# Diagnosing Lost AuthnRequest, Wrong InResponseTo, and Unsent Cookies

## 1. Goal and Error Context

In **Spring Security – federation**, under **Observability and debugging**, a common SAML 2.0 Web SSO failure is that the user logs in and completes MFA at the Identity Provider (IdP), the browser receives the page that POSTs `SAMLResponse` to the application, yet Spring Security fails to establish a session, returns 401/403, or redirects the user back to the login screen.

Do not lump every failure under one "SAML failed" label. Three distinct phenomena must be separated:

1. **Lost AuthnRequest**: the SP created the login request, but at the callback it cannot read back the saved request.
2. **InResponseTo mismatch**: the IdP returns a Response referencing AuthnRequest A, while the SP is checking request B or has no request at all.
3. **Cookie not sent or session missing**: the browser does not send the SP session cookie on the cross-site POST, or the cookie is present yet the server cannot find the session data.

Causes may include SameSite, Secure/Domain/Path, session timeout, reverse proxy, load balancer, Spring Session, request repository, concurrent tabs, wrong callback route, and IdP-initiated SSO. They exhibit similar symptoms yet require completely different fixes.

**Learning objectives:** understand the SAML request/response and state lifecycle, diagnose with evidence from browser to IdP/Spring/server session, classify InResponseTo errors, defend against login CSRF and replay, design logging that never leaks assertions/cookies, run standalone Java 17 code, build a negative test matrix, and complete an acceptance checklist.

> **Security invariant:** For **SP-initiated SSO**, the issued AuthnRequest and received SAMLResponse must match the exact transaction/browser binding per policy. Never drop InResponseTo, RelayState, signature, issuer, audience, or recipient checks just so users can log in again.

## 2. Five Similar-Sounding Names That Are Not Interchangeable

| Data | Source | Role | Confusion to Avoid |
| --- | --- | --- | --- |
| **AuthnRequest ID** | SP-generated inside XML `<saml2:AuthnRequest ID="_REQ-A">` | Identifies an issued authentication request. | Not the SAMLResponse ID or session ID. |
| **Response InResponseTo** | Returned by IdP in `<saml2:Response>` and/or SubjectConfirmationData | Declares which AuthnRequest the Response answers. | Insufficient to prove the current browser initiated the request. |
| **RelayState** | Sent by SP with AuthnRequest, echoed by IdP per binding | Opaque correlation / application state. | Not a SAML signature, and not a trusted redirect URL by default. |
| **JSESSIONID / HttpSession** | Issued by SP server, stored as a browser cookie | Binds browser to pending AuthnRequest in the default session repository. | Not AuthnRequest ID, and does not itself replace SAML evidence. |
| **RelyingPartyRegistrationId** | Spring Security configuration | Selects IdP, ACS, verification credentials, and SP entityID. | Not the IdP issuer or proof that the caller was authenticated. |

**Response ID** and **Assertion ID** are two different IDs used for replay protection and message tracing. **IdP entityID**, **SP entityID**, **Destination**, **Recipient**, and **AudienceRestriction** are also distinct fields. Mixing up ID types easily leads to falsely blaming "InResponseTo failed".

### 2.1. A Properly Correlated Login

```text
SP creates:
  sessionRef    : S1
  registration  : corp-idp
  request ID    : _REQ-A1
  RelayState    : R-A1
  expected ACS  : https://portal.example.org/login/saml2/sso/corp-idp

IdP receives AuthnRequest ID=_REQ-A1 and RelayState=R-A1.

Browser returns:
  POST /login/saml2/sso/corp-idp
  SAMLResponse:
    Response ID=_RESP-B1
    InResponseTo=_REQ-A1
    Issuer=https://idp.corp.example/saml
    Destination=https://portal.example.org/login/saml2/sso/corp-idp
  RelayState=R-A1
  Cookie: JSESSIONID=<redacted>

SP repository finds pending request _REQ-A1,
bound to the expected browser transaction.
  -> correlation MATCH
  -> validate XML signature, issuer, audience, recipient,
     Conditions, SubjectConfirmation and replay
  -> create Authentication only after all checks
```

**Matching InResponseTo is not yet login success.** An attacker must not be granted access if a signed assertion has the wrong issuer/audience, is expired, or maps to a disabled local user.

## 3. Spring Security SAML2 Web SSO: Filter Chain and Repository

In Spring Security Servlet, the SP-initiated flow:

```text
Browser         Spring Security SP                 IdP
  |                    |                            |
  | GET /reports       |                            |
  |------------------->|                            |
  |<-------------------| 302 /saml2/authenticate/corp
  |                    |                            |
  | GET /saml2/authenticate/corp                      |
  |------------------->|                            |
  |                    | Saml2WebSsoAuthenticationRequestFilter
  |                    | create AuthnRequest _REQ-A
  |                    | save via Saml2AuthenticationRequestRepository
  |                    | redirect with SAMLRequest, RelayState
  |<-------------------|                            |
  | Redirect to IdP -------------------------------->|
  |                    |                            | user MFA
  | Browser POST ACS  |<----------------------------|
  |------------------->|                            |
  |                    | Saml2WebSsoAuthenticationFilter
  |                    | Saml2AuthenticationTokenConverter
  |                    | load pending AuthnRequest
  |                    | validate response with OpenSAML provider
  |                    |                            |
  | success / failure  |                            |
  |<-------------------|                            |
```

Common endpoints:
- **Create AuthnRequest**: `/saml2/authenticate/{registrationId}`.
- **Receive SAMLResponse at ACS**: `/login/saml2/sso/{registrationId}`.

In current Spring Security, `Saml2WebSsoAuthenticationRequestFilter` uses **`Saml2AuthenticationRequestRepository`** to store an `AbstractSaml2AuthenticationRequest` before redirecting the browser to the IdP; `Saml2WebSsoAuthenticationFilter` and `Saml2AuthenticationTokenConverter` can use the repository to retrieve the request.

**The default is `HttpSessionSaml2AuthenticationRequestRepository`**, which stores the pending request in `HttpSession`. This mechanism depends on maintaining the browser↔session binding all the way to the IdP and back.

**Version note:** Spring Security 6.x/7.x and custom repositories can have different APIs/defaults. Always record exact dependency versions, the active filter chain, repository implementation, session store type, and binding (HTTP-POST/Redirect) before drawing conclusions.

## 4. Distinguishing the Three Core Failures with Evidence

### 4.1. AuthnRequest Not Found

```text
T0: save AuthnRequest A in browser session S1.
T1: callback POST from IdP contains InResponseTo=A.
T2: loadAuthnRequest(callback) returns null.
```

Possibilities:
- Browser **did not send JSESSIONID** due to SameSite/scope/browser policy.
- Browser sent the cookie, yet gateway/WAF did not forward it.
- Session S1 timed out, was invalidated, or was evicted.
- Callback hit an app node that does not share sessions with the node that created the request.
- Repository saved into session, yet callback loaded from a different cache repository.
- Request was consumed/removed earlier by a duplicate ACS callback or a twice-registered filter.
- App restart/rolling deploy wiped in-memory sessions or failed serialization.
- Multiple tabs overwrote the single request in session, and then the request was removed.
- ACS was routed to staging or another host.

**A single "request not found" log is not enough to infer that the IdP returned the wrong InResponseTo.**

### 4.2. Request Found, Yet Wrong InResponseTo

```text
AuthnRequest saved or loaded : _REQ-B
SAMLResponse.InResponseTo    : _REQ-A

=> MISMATCH, even though SAMLResponse has a valid signature.
```

This can be **concurrency**: tab A sends request A, tab B in the same HTTP session sends request B; storage that holds only one request overwrites A. Other possibilities: IdP response for an older request, wrong RelayState, different registration, unexpected session rotation/change, or cache mapping mixing transactions.

### 4.3. At Which Layer Is the Cookie Missing?

| Layer | Symptom | Proper Analysis |
| --- | --- | --- |
| SP HTTP response | No `Set-Cookie` seen | An older cookie may already exist; check Application/Storage. |
| Browser receives `Set-Cookie` | Browser refuses to store | `SameSite=None` missing `Secure`, Domain, or browser policy. |
| Browser sends ACS | Cookie excluded | SameSite, Secure, Domain, Path, iframe/third-party policy. |
| Reverse proxy | Browser included it, app lacks Cookie | Ingress/WAF/CDN stripped or rewrote it. |
| Spring Servlet | Cookie present yet `getSession(false)` is null | Session expired/evicted/namespace/node mismatch. |
| Repository | Session exists yet request is null | Save failed, removed, overwritten, or repo contract mismatch. |

Do not call all six phenomena "lost cookie". Each layer has its own remediation and testing.

## 5. SameSite and SAML HTTP-POST: A Frequent Root Cause

In the HTTP-POST Binding, the IdP renders an HTML form so **the browser POSTs from the IdP site to the SP's ACS**. When the two systems are cross-site, this is a **non-safe-method cross-site POST**.

| Cookie Attribute | Cross-Site Top-Level GET | Cross-Site Top-Level POST | Impact |
| --- | --- | --- | --- |
| `SameSite=Strict` | Not sent | Not sent | Even a return GET navigation from the IdP can lose the session. |
| `SameSite=Lax` (explicit) | Usually sent | Usually **not sent** | SAMLResponse POST easily omits `JSESSIONID`. |
| `SameSite=None; Secure` | May be sent | May be sent | Requires HTTPS; still constrained by browser privacy/partitioning policies. |
| SameSite unset | Browser picks default (usually Lax) | May have a browser-specific grace window | Too inconsistent to rely on when designing SSO. |

MDN notes that some browsers apply a **default Lax** behavior with a relaxed POST exception when a cookie was created within about **two minutes**. This can make fast logins succeed while users taking several minutes for MFA fail. **Do not confuse the default-Lax exception with explicit `SameSite=Lax`**, and never rely on a grace period in production.

### 5.1. Illustrative HTTP Trace

```http
HTTP/1.1 302 Found
Location: https://idp.corp.example/sso?SAMLRequest=...&RelayState=...
Set-Cookie: JSESSIONID=<redacted>; Path=/; Secure; HttpOnly; SameSite=Lax
```

On callback:

```http
POST /login/saml2/sso/corp-idp HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded
Origin: https://idp.corp.example

SAMLResponse=<redacted>&RelayState=<redacted>
```

The browser may **omit `Cookie: JSESSIONID`** on this POST. Spring cannot locate the HTTP session holding AuthnRequest A. The example headers merely depict typical data; `Origin`/Fetch Metadata may be absent or differ by browser. **Origin never replaces SAML signature validation.**

### 5.2. Spring Boot Cookie Config: Apply Only After Confirming the Cause

Example properties:

```properties
server.servlet.session.cookie.same-site=none
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
```

Spring Boot documentation supports `server.servlet.session.cookie.same-site` for embedded containers and servlet Spring Session repositories depending on version. **Do not treat this config as a cure-all for every SAML error.** Verify the cookie writer, which Boot/container the app uses, public HTTPS, and the ACS path.

With `SameSite=None`, browsers may attach the session cookie to broader cross-site requests; **every business action using cookies still needs CSRF protection**, such as CSRF tokens or an appropriate Origin/Fetch Metadata policy. The SAML ACS POST may need a **narrow CSRF exemption matching only the callback**, without disabling CSRF app-wide or on admin endpoints.

### 5.3. When `None` Does Not Solve It

- Cookie `Path=/app` while ACS callback is `/login/saml2/sso/...` (outside Path).
- Host-only cookie belongs to `old.portal.example.org` while IdP POSTs to `portal.example.org`.
- Secure cookie while callback hits HTTP due to a misconfigured public ACS.
- Browser/iframe blocks third-party cookies regardless of `SameSite=None`.
- Browser cleared cookies or user opened a private browsing context.
- Proxy/WAF strips Cookie or rewrites Domain.
- Session store expires during MFA.
- Callback hits a node lacking the session.
- Multi-tab overwrite even when `JSESSIONID` is sent.

**Do not change SameSite to mask an InResponseTo error caused by two tabs.**

## 6. Investigating with Browser DevTools / Network

Perform only with **test accounts** and non-sensitive data; enable Preserve log:

1. Start by accessing a protected resource on the SP.
2. Locate `GET /saml2/authenticate/{registrationId}` and the outbound `SAMLRequest`.
3. Inspect response `Set-Cookie` **attributes**: name, Path, Domain, Secure, HttpOnly, SameSite, Max-Age; **never copy cookie values**.
4. Record browser/version, normal tab vs iframe, HTTP method, and cross-site context.
5. Follow the IdP/MFA flow to ACS `POST /login/saml2/sso/...`.
6. Open the Cookies tab of the ACS request, looking for **Included/Excluded** and the **specific reason**.
7. Check public ACS origin, host, path, scheme, and `Set-Cookie` scope.
8. Record only boolean presence/absence of `SAMLResponse` and `RelayState`; do not export raw XML/Base64 assertions.
9. Join with the application trace using a separate correlation ID.
10. Repeat under controlled conditions: 1 tab, 2 tabs, fast/slow MFA, clean browser, and another browser.

**HAR exports can contain cookies, SAMLResponse, NameID, and PII.** If a HAR is required, redact it in a protected location, restrict read access, and limit retention. Never post raw HARs or bearer assertions to public issue trackers.

### 6.1. Browser Evidence → Debug Step

| Observed in Browser Network | Check First |
| --- | --- |
| Cookie excluded due to SameSite | Cross-site POST vs GET, Lax/Strict/None. |
| Cookie excluded due to Secure | Public HTTPS callback and reverse proxy. |
| Cookie excluded due to Domain/Path | Cookie scope relative to ACS. |
| Cookie included yet app misses it | Proxy forwarding/filters/WAF. |
| Cookie included, session found, loaded request B | Multi-tab/repository overwrite. |
| No outbound SAMLRequest | Initiation flow or IdP-initiated SSO. |
| ACS POST blocked 403 before SAML filter | CSRF matcher/WAF/chain order. |
| Request found, InResponseTo matches yet signature fails | IdP cert/trust; not cookies. |

## 7. Instrumenting the Repository to Prove the Request Was Saved

`HttpSessionSaml2AuthenticationRequestRepository` uses HttpSession to store pending requests. To diagnose accurately, emit **events from real save/load/remove calls** rather than calling the repository a second time yourself.

Example instrumentation schema:

```text
event=SAML_AUTHN_REQUEST_CREATED
trace=login-001
registration=corp-idp
request_ref=HMAC(_REQ-A)
relay_ref=HMAC(R-A)
session_ref=HMAC(S1)
node=portal-1

event=SAML_AUTHN_REQUEST_SAVED
trace=login-001
repository=HttpSession
outcome=SUCCESS
request_ref=HMAC(_REQ-A)
session_ref=HMAC(S1)
node=portal-1

event=SAML_RESPONSE_RECEIVED
trace=acs-319
method=POST
session_cookie_present=true
server_session_found=true
response_in_response_to_ref=HMAC(_REQ-A)
node=portal-2

event=SAML_AUTHN_REQUEST_LOADED
trace=acs-319
repository=HttpSession
outcome=FOUND
stored_request_ref=HMAC(_REQ-A)
node=portal-2

event=SAML_CORRELATION
trace=acs-319
decision=MATCH
```

This is a **proposed schema**, not default Spring Security logging. Use **HMAC-keyed references** for sensitive data; never log raw SAMLResponse, RelayState, session IDs, or AttributeStatement. Labels like `node`, `registration`, `repository`, and `outcome` help compare across multiple nodes.

### 7.1. Outcomes to Distinguish

| Save | Cookie/Session at ACS | Load | Provisional Conclusion |
| --- | --- | --- | --- |
| A saved in S1 | No S1 | NOT_FOUND | Browser Cookie/ingress. |
| A saved in S1 | Cookie S1 present, session absent | NOT_FOUND | Session TTL/eviction/node. |
| A saved in S1 | Session S1 present, attribute absent | NOT_FOUND | Remove/overwrite/replication/repo mismatch. |
| A then B saved in S1 | Session S1 present, loads B, response A | MISMATCH | Multi-tab overwrite or wrong mapping. |
| A saved and loads A | Response InResponseTo=A | MATCH | If still failing, check other validations. |

**Investigating lost sessions must use `request.getSession(false)`.** `request.getSession()` can create a brand-new session, making a "server session present" log meaningless for the session that stored the AuthnRequest.

### 7.2. Failures Caused by Instrumentation Itself

- A debug filter calls `removeAuthnRequest` to "inspect state", and then the SAML filter calls it again and finds nothing.
- A custom filter is registered twice, causing load/remove to run twice.
- A callback is retried/replayed by the browser, and the first call already consumed the request.
- A wrapper computes correlation from the current cookie after session rotation occurred prior to callback.
- A debug filter inadvertently prints raw queries containing `SAMLRequest`/`RelayState`.

**Never introduce side effects while observing.** Wrap only calls made by the framework, redact secrets, and test duplicate callbacks.

## 8. Two Tabs Sharing HttpSession: InResponseTo Mismatch Despite Present Cookie

One browser has two tabs sharing `JSESSIONID=S1`:

```text
T0 Tab A:
  AuthnRequest ID=_REQ-A
  RelayState=R-A
  session[SAML_REQUEST] = _REQ-A

T1 Tab B:
  AuthnRequest ID=_REQ-B
  RelayState=R-B
  session[SAML_REQUEST] = _REQ-B

T2 Tab A finishes IdP login first:
  POST ACS with JSESSIONID=S1
  SAMLResponse InResponseTo=_REQ-A

Repository:
  load session[SAML_REQUEST] = _REQ-B

=> _REQ-A != _REQ-B -> failure.
```

Spring Security had issue #14793 reported regarding storing requests under a single session key causing newer requests to overwrite older ones in certain versions. **Do not assume all versions behave identically**; inspect the actual class/release and observe save A, save B, and load A/B events.

### 8.1. Confirming Evidence

1. A single tab logs in successfully.
2. Enable safe `requestRef`/`sessionRef` logging.
3. Open tab A and start SSO; before its callback returns, open tab B and start SSO.
4. Record `SAVE A`, `SAVE B`, and the same `sessionRef`.
5. Let tab A's callback return; record `LOAD B`, `InResponseTo A`, and mismatch.
6. Reverse callback order to reproduce systematically.
7. Repeat across multiple nodes if applicable.
8. After changing the repository, both tabs must succeed and replays must still be rejected.

**Do not drop InResponseTo validation** just because single-tab passes while multi-tab fails. You need a design capable of storing multiple distinct pending AuthnRequests.

## 9. CacheSaml2AuthenticationRequestRepository and Browser-Binding Trade-Offs

In newer versions, Spring Security provides `CacheSaml2AuthenticationRequestRepository`, which can cache AuthnRequests keyed by RelayState. It is useful when HTTP sessions do not fit strict cookie rules, or when multiple requests must wait concurrently.

A transaction record should contain:

```text
key:
  unpredictable one-time RelayState reference

value:
  AuthnRequest ID
  relying-party registration
  expected IdP entityID
  expected ACS and SP entityID
  issuedAt, expiresAt
  original browser/session transaction binding
  safe post-login relative destination
  state=PENDING
```

On callback:
1. Look up the record using the opaque transaction key.
2. Verify browser/session binding or an equivalent anti-login-CSRF control.
3. Match `InResponseTo` against AuthnRequest ID.
4. Verify signature, issuer, audience, recipient/destination, Conditions, SubjectConfirmation, and replay.
5. Atomically consume/clean up once; never reuse the record after login.
6. Expired TTL/missing record/conflict → deny, never fall back to auto-login.

### 9.1. Official Spring Security Warning

A session-based repository has a natural defense against **login fixation**: a response from an attacker finds no AuthnRequest in the victim's browser session. If you only use `RelayState` or `InResponseTo` from an inbound response to look up an AuthnRequest in a **shared cache**, **nothing inherently proves the victim's browser initiated that transaction**.

Therefore:
- Do not treat "putting requests in Redis keyed by RelayState" as a complete, safe fix by itself.
- Add binding between the request and the original browser or equivalent login CSRF controls, under security review.
- RelayState must be unpredictable, short-lived (TTL), and single-use, containing no session secrets.
- Never use RelayState as an arbitrary redirect URL.
- Match full IdP/registration/tenant context, not just the ID.
- Test cross-browser response injection, replay, and callback retries.
- Never disable session fixation protection to fix SSO.

### 9.2. Per-Session Maps Are Not Risk-Free Either

If using `Map<RelayState, PendingRequest>` inside HttpSession:
- A mutable map needs concurrency control across threads.
- Spring Session/serialization may not persist in-place mutations as developers expect.
- Lost updates can occur when two nodes concurrently modify a session snapshot.
- You must re-set the session attribute or use an atomic distributed store per contract.
- Enforce quotas/TTLs and remove only the right transaction, not all tabs.
- Account for rolling deployments/class changes, store errors, and fail-closed behavior.

## 10. Reverse Proxy, Forwarded Headers, and ACS URL

Example:

```text
Public browser origin:
  https://portal.example.org

Internal Spring app:
  http://portal-service:8080

Configured ACS at IdP:
  https://portal.example.org/login/saml2/sso/corp-idp
```

If Spring or the IdP mixes in an internal URL, cookies may be set for the wrong host, callbacks routed wrongly, and SAML Recipient/Destination mismatched.

| Check | Where to Read? | Compare Against |
| --- | --- | --- |
| Public ACS URL | Browser Network | IdP registration/metadata. |
| AuthnRequest AssertionConsumerServiceURL | Outbound SAMLRequest (controlled parse) | Public ACS. |
| Response Destination | Validated response context | Expected ACS. |
| SubjectConfirmationData Recipient | Assertion | Expected service/ACS. |
| Registration ID | Spring path/metadata | Allowed IdP entityID. |
| Cookie Domain/Path/Secure | Browser cookie view | Public ACS origin/path. |
| Forwarded-Host/Proto | Approved ingress | External HTTPS host; never trust attacker headers. |
| Backend node/store namespace | App trace | Request creation node/store. |

The Spring Boot property:

```properties
server.forward-headers-strategy=framework
```

can help when the architecture has a **trusted reverse proxy**. Only enable it when ingress **strips user-supplied `X-Forwarded-Host`/Proto/Port** and writes genuine values; otherwise attackers can trick the app into generating wrong ACS/redirects. Always test exact public URLs; never open wildcard ACS/redirects due to mismatched configuration.

### 10.1. Cookie Path/Domain/Name

- A cookie with `Path=/app` is not sent to ACS `/login/saml2/sso/corp-idp`.
- A host-only cookie for `old.portal.example.org` is not sent to `portal.example.org`.
- A `Secure` cookie is not sent over an HTTP callback on the public Internet.
- Multiple `JSESSIONID` cookies may exist at different Paths/Domains, causing the server to pick the wrong one.
- Ingress rewriting `Set-Cookie` or `Cookie` can alter cookie policies.
- HSTS, TLS termination, and port/context path must be consistent.

**Only set a broad Domain when truly necessary.** Host-only cookies with the minimal sufficient Path reduce the surface where session data can leak.

## 11. Multi-Node Session Store and Session Fixation

Example:

```text
GET initiation:
  Node A creates S1 and saves AuthnRequest _REQ-A
Callback:
  Node B receives JSESSIONID=S1
  Node B only has local in-memory HttpSession
  -> session not found
```

Sticky sessions reduce the likelihood, yet do not survive restarts, node failures, LB rebalances, or rolling deploys. Spring Session Redis/JDBC or a distributed request store is better suited when multi-node consistency is required.

**Things to verify:**
- Do Node A and B use the same session namespace/prefix/config?
- Does session TTL exceed real-world MFA duration?
- Did the `AuthnRequest` session attribute serialize and persist?
- Are there store evictions, timeouts, or deserialization errors after rollouts?
- Did a duplicate callback already remove the request earlier?
- Do repo save and load share the same implementation and config?
- Did the session ID change before callback due to logout/invalidation?

### 11.1. Session ID Change Before vs. After Authentication

```text
Normal:
 T0 create and save AuthnRequest in S1
 T1 callback uses S1, request loads and matches
 T2 SAML authentication succeeds
 T3 session-fixation strategy may rotate ID

Problem:
 T0 save pending request in S1
 T1 logout/Session invalidation or S2 created too early
 T2 callback cannot find original pending request
```

**Rotating the Session ID after authentication success can be completely normal.** Never disable session fixation protection. To find the root cause, timestamp each step and distinguish events before vs. after callback.

## 12. IdP-Initiated SSO: No Initial AuthnRequest

When a user clicks a tile in the IdP dashboard, the IdP may send an **unsolicited** response with no SP AuthnRequest and possibly no `InResponseTo`. That is the **IdP-initiated** profile, distinct from SP-initiated.

- If app policy allows SP-initiated only, an unsolicited SAMLResponse **must be rejected**.
- If the business requires IdP-initiated, you need an approved policy covering trusted issuer, signature, audience, recipient, replay, user/tenant authorization, and defenses against login CSRF/session confusion.
- Never turn an `AuthnRequest not found` error into `accept unsolicited` just to get logins working.
- Auditing should distinguish SP-initiated from IdP-initiated for accurate diagnosis.

**Never having had an AuthnRequest** and **losing an AuthnRequest that existed** are two completely different security and operational cases.

## 13. Distinguishing Correlation Errors from Other SAML Validation Failures

| State | Error Category |
| --- | --- |
| Repository load null | Cookie/session/repo/overwrite/timeout. |
| Loaded ID B while Response InResponseTo A | Transaction mapping or concurrent tabs. |
| Inbound RelayState mismatches outbound | IdP/state propagation/encoding/repository. |
| Response signature invalid | IdP signing cert/metadata/XML signature. |
| Wrong issuer | Wrong partner/registration. |
| Wrong audience | Assertion meant for another SP. |
| Wrong Destination/Recipient | Misconfigured ACS reverse proxy/metadata. |
| NotBefore/NotOnOrAfter invalid | Clock skew/NTP/expired assertion. |
| SubjectConfirmation failure | Invalid bearer/recipient/correlation conditions. |
| Assertion replay | Duplicate SAMLResponse / replay store. |
| CSRF/WAF 403 before SAML filter | HTTP routing/security chain, never reached XML validation. |
| Local account disabled after SAML verify | Application admission, not cookies. |
| Resource permission denied | Authorization, not federation authentication. |

**Correct correlation does not waive cryptographic validation**, and valid cryptographic validation does not by itself prove correlation/SP-initiated flow.

## 14. Spring Security Instrumentation Without Exposing Cookies

**Never use**:

```java
log.info("Cookie={}", request.getHeader("Cookie"));
log.info("SAMLResponse={}", request.getParameter("SAMLResponse"));
log.info("Session={}", request.getSession().getId());
```

This both leaks bearer material/PII and risks **creating a new session when calling `getSession()`**.

### 14.1. Illustrative Filter Observing Presence

The snippet below is for a **Spring Boot Servlet/Jakarta project with SLF4J**, not standalone Java SE. Register the filter exactly once; avoid registering it both as a Servlet Filter Bean and inside SecurityFilterChain, which would run it twice.

```java
package example.sso;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

public final class SamlCookieProbeFilter extends OncePerRequestFilter {
    private static final Logger LOG =
        LoggerFactory.getLogger(SamlCookieProbeFilter.class);

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return !path.contains("/saml2/authenticate/")
            && !path.contains("/login/saml2/sso/");
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain) throws ServletException, IOException {

        boolean hasSessionCookie = false;
        Cookie[] cookies = request.getCookies();
        if (cookies != null) {
            for (Cookie cookie : cookies) {
                if ("JSESSIONID".equals(cookie.getName())) {
                    hasSessionCookie = true;
                    break;
                }
            }
        }

        LOG.info("saml_probe path={} method={} cookie_present={} "
                + "session_found={} session_id_valid={}",
            request.getRequestURI(),
            request.getMethod(),
            hasSessionCookie,
            request.getSession(false) != null,
            request.isRequestedSessionIdValid());

        chain.doFilter(request, response);
    }
}
```

**Limitations:** logs only booleans and route, never printing cookie values or SAML XML; change the cookie name if your organization uses another name. Distinguishing request A vs B requires a repository wrapper logging hashed request/RelayState refs. Never add extra `load/remove` calls for debugging, as that can consume state.

### 14.2. Safe Repository Wrapper Pseudocode

```text
saveAuthnRequest(request):
    derive safe requestRef, relayRef, sessionRef using HMAC
    delegate.save(...)
    emit SAVED status + node + registration + repoType

loadAuthnRequest(callback):
    derive safe browser/callback presence flags
    delegate.load(...)
    emit FOUND / NOT_FOUND + storedRequestRef if found

removeAuthnRequest(callback):
    delegate.remove(...)
    emit REMOVED / ALREADY_ABSENT
```

Method signatures/generic types vary by Spring Security version; the snippet above **is not a drop-in Java API**. Every event must strip raw SAML assertions, cookies, NameID, and URLs containing RelayState.

## 15. Runnable Java 17: Reproducing Cookie Loss, InResponseTo Mismatch, and Multi-Request Storage

The following Java SE program uses **`HashMap` and `record`** to illustrate the rules. It does not connect to an IdP, verify SAML XML, or provide TLS, HTTP sessions, or multi-node storage.

- `SinglePendingSessionRepository`: one request per session; tab B overwrites tab A.
- `PerTransactionRepository`: looks up by RelayState, while also checking browser-session binding, InResponseTo, TTL, and single-use consumption.
- `cookieSent`: simplified model of **explicit** SameSite, not simulating default-Lax grace, browser privacy, Domain/Path, or iframe/partitioning.

File **SamlCorrelationDiagnosticsDemo.java**:

```java
import java.util.HashMap;
import java.util.Map;

public final class SamlCorrelationDiagnosticsDemo {

    record Login(String id,
                 String relay,
                 String browserSession,
                 long expiresAt) {}

    static final class SinglePendingSessionRepository {
        private final Map<String, Login> pending = new HashMap<>();

        void save(Login request) {
            pending.put(request.browserSession(), request);
        }

        String callback(String browserSession, String inResponseTo) {
            if (browserSession == null) return "COOKIE_MISSING";
            Login found = pending.get(browserSession);
            if (found == null) return "REQUEST_NOT_FOUND";
            if (!found.id().equals(inResponseTo))
                return "IN_RESPONSE_TO_MISMATCH";
            return "MATCH";
        }
    }

    static final class PerTransactionRepository {
        private final Map<String, Login> pendingByRelay = new HashMap<>();

        void save(Login request) {
            pendingByRelay.put(request.relay(), request);
        }

        String callback(String relay, String inResponseTo,
                        String browserSession, long now) {
            if (relay == null) return "RELAY_MISSING";
            Login found = pendingByRelay.get(relay);
            if (found == null) return "REQUEST_NOT_FOUND";
            if (!found.browserSession().equals(browserSession))
                return "BROWSER_BINDING_MISMATCH";
            if (now >= found.expiresAt()) {
                pendingByRelay.remove(relay);
                return "REQUEST_EXPIRED";
            }
            if (!found.id().equals(inResponseTo))
                return "IN_RESPONSE_TO_MISMATCH";
            pendingByRelay.remove(relay);
            return "MATCH";
        }
    }

    static boolean cookieSent(String sameSite, String method,
                              boolean crossSite, boolean topLevel,
                              boolean https) {
        return switch (sameSite) {
            case "Strict" -> !crossSite;
            case "Lax" -> !crossSite ||
                (topLevel && "GET".equals(method));
            case "None" -> https;
            default -> false;
        };
    }

    public static void main(String[] args) {
        Login tabA = new Login("_REQ-A", "R-A", "SID-1", 100);
        Login tabB = new Login("_REQ-B", "R-B", "SID-1", 100);

        System.out.println("LAX_CROSS_POST=" +
            cookieSent("Lax", "POST", true, true, true));
        System.out.println("LAX_CROSS_GET=" +
            cookieSent("Lax", "GET", true, true, true));
        System.out.println("STRICT_CROSS_GET=" +
            cookieSent("Strict", "GET", true, true, true));
        System.out.println("NONE_CROSS_POST_HTTPS=" +
            cookieSent("None", "POST", true, true, true));
        System.out.println("NONE_CROSS_POST_HTTP=" +
            cookieSent("None", "POST", true, true, false));

        SinglePendingSessionRepository single =
            new SinglePendingSessionRepository();
        single.save(tabA);
        System.out.println("ONE_TAB=" +
            single.callback("SID-1", "_REQ-A"));
        System.out.println("COOKIE_LOST=" +
            single.callback(null, "_REQ-A"));

        single.save(tabA);
        single.save(tabB);
        System.out.println("TAB_A_AFTER_B=" +
            single.callback("SID-1", "_REQ-A"));
        System.out.println("TAB_B=" +
            single.callback("SID-1", "_REQ-B"));

        PerTransactionRepository multi =
            new PerTransactionRepository();
        multi.save(tabA);
        multi.save(tabB);
        System.out.println("MULTI_A=" +
            multi.callback("R-A", "_REQ-A", "SID-1", 10));
        System.out.println("MULTI_B=" +
            multi.callback("R-B", "_REQ-B", "SID-1", 10));
        System.out.println("REPLAY_A=" +
            multi.callback("R-A", "_REQ-A", "SID-1", 11));

        multi.save(new Login("_REQ-C", "R-C", "SID-1", 50));
        System.out.println("WRONG_BROWSER=" +
            multi.callback("R-C", "_REQ-C", "SID-EVIL", 10));
        System.out.println("WRONG_ID=" +
            multi.callback("R-C", "_REQ-OTHER", "SID-1", 10));
        System.out.println("EXPIRED=" +
            multi.callback("R-C", "_REQ-C", "SID-1", 50));
        System.out.println("NO_RELAY=" +
            multi.callback(null, "_REQ-C", "SID-1", 20));
    }
}
```

Compile and run:

```bash
javac SamlCorrelationDiagnosticsDemo.java
java SamlCorrelationDiagnosticsDemo
```

**Deterministic stdout:**

```text
LAX_CROSS_POST=false
LAX_CROSS_GET=true
STRICT_CROSS_GET=false
NONE_CROSS_POST_HTTPS=true
NONE_CROSS_POST_HTTP=false
ONE_TAB=MATCH
COOKIE_LOST=COOKIE_MISSING
TAB_A_AFTER_B=IN_RESPONSE_TO_MISMATCH
TAB_B=MATCH
MULTI_A=MATCH
MULTI_B=MATCH
REPLAY_A=REQUEST_NOT_FOUND
WRONG_BROWSER=BROWSER_BINDING_MISMATCH
WRONG_ID=IN_RESPONSE_TO_MISMATCH
EXPIRED=REQUEST_EXPIRED
NO_RELAY=RELAY_MISSING
```

### 15.1. Interpreting the Output

- `LAX_CROSS_POST=false`: explicit Lax does not send cookies on cross-site POST per the model.
- `LAX_CROSS_GET=true`: top-level safe GET can carry the cookie.
- `STRICT_CROSS_GET=false`: Strict blocks cross-site navigation.
- `NONE_CROSS_POST_HTTPS=true`: None+Secure can send cookies over HTTPS, though browser settings still apply.
- `COOKIE_LOST`: session never reaches the server, so request ID cannot be compared yet.
- `TAB_A_AFTER_B`: request B overwrote A in the same session; InResponseTo mismatch.
- `MULTI_A`/`MULTI_B`: per-transaction storage demonstrates two tabs without overwriting.
- `REPLAY_A`: request already consumed, cannot be reused.
- `WRONG_BROWSER`: a matching RelayState is insufficient when browser binding fails.
- `WRONG_ID`: response does not answer the pending AuthnRequest.
- `EXPIRED`: transactions do not live forever.

**Important limitations:** `HashMap` is not thread-safe/cluster-safe. `browserSession` and the boolean cookie flags model trusted data; in production never read them from attacker-supplied HTTP queries/headers. The demo removes the request upon correlation match **before checking the SAML signature**, so it is **only a policy simulation**; a real implementation requires a protocol validator, atomic consumption, replay protection, and full security review.

## 16. Root-Cause and Security Regression Test Matrix

| ID | Scenario | Expected Outcome |
| --- | --- | --- |
| CK01 | Explicit SameSite=Lax + SAML cross-site POST. | Browser normally excludes JSESSIONID. |
| CK02 | SameSite=Strict + cross-site GET. | Cookie excluded, no session. |
| CK03 | SameSite=None without Secure. | Browser rejects cookie per policy. |
| CK04 | Secure cookie + HTTP callback. | Cookie not sent; requires public HTTPS. |
| CK05 | Cookie Path=/app while ACS=/login/saml2/sso. | Cookie not sent due to Path. |
| CK06 | Cookie host A, ACS host B. | Domain/host mismatch. |
| CK07 | Browser included cookie, ingress strips Cookie. | Backend lacks cookie; fix ingress. |
| CK08 | Browser included cookie, Redis session expired. | App finds no session; deny safely. |
| CK09 | Browser iframe/third-party cookie blocked. | Diagnose privacy settings, top-level flow. |
| CK10 | IdP MFA takes longer than session TTL. | Request expired; do not accept unsolicited. |
| CK11 | Explicit Lax and default Lax behave differently. | Do not rely on grace window. |
| CK12 | Two JSESSIONID cookies at different Paths. | Detect ambiguity; do not use wrong session. |
| RE01 | No outbound AuthnRequest. | Identify initiation/IdP-initiated flow. |
| RE02 | AuthnRequest created yet repository save failed. | Fail closed; do not bypass InResponseTo. |
| RE03 | Save A, callback cookie absent. | Repository not found, reason cookie. |
| RE04 | Save A, callback cookie present yet session absent. | TTL/eviction/node/namespace. |
| RE05 | Save A, session present yet request absent. | Remove/overwrite/repo mismatch. |
| RE06 | Save A, save B same session, callback InResponseTo A. | Detect mismatch, reject. |
| RE07 | Per-transaction repository, 2 tabs. | Both succeed once; replay rejected. |
| RE08 | Inbound RelayState differs from outbound. | Reject, no open redirect. |
| RE09 | Cache lookup matches RelayState yet wrong browser. | Reject login CSRF/cross-browser injection. |
| RE10 | Cache record expired. | Reject, no indefinite TTL. |
| RE11 | Duplicate ACS response. | Atomic replay/consumption rejection. |
| RE12 | Repository remove called twice. | Detect duplicate filter/side effect. |
| RE13 | Node A saves, Node B loads without shared session. | Not found; fix distributed storage. |
| RE14 | Node B session deserialization error. | Explicit fail, no fallback. |
| RE15 | Session rotates after SAML success. | Do not treat as pre-auth root cause. |
| RE16 | Session invalidates before callback. | Missing request; start fresh login. |
| SA01 | Wrong IdP Issuer. | Reject even if InResponseTo matches. |
| SA02 | Wrong signature/trust cert. | Reject. |
| SA03 | Wrong AudienceRestriction. | Reject. |
| SA04 | Wrong Destination/Recipient. | Reject; inspect ACS/metadata. |
| SA05 | Conditions expired. | Reject; inspect clock skew/NTP. |
| SA06 | Assertion replayed on another pod. | Shared replay store rejects. |
| SA07 | IdP-initiated response sent to SP-only app. | Reject per policy. |
| SA08 | SAML valid, local account DISABLED. | Deny local admission. |
| SA09 | SAML valid, missing reports:read. | 403 business authorization. |
| PX01 | ACS POST blocked by CSRF/WAF before SAML filter. | Fix narrow matcher; do not disable CSRF app-wide. |
| PX02 | Ingress rewrites https→http in public ACS. | Fix trusted forwarded headers. |
| PX03 | Callback hits staging while request created in prod. | Reject; fix IdP registration. |
| PX04 | Multi-tab + multi-node + duplicate callbacks. | No overwrite/session leak; proper replay policy. |

**Tests must cover both happy paths and negative paths.** Never mark QA PASS for a configuration that "stopped erroring" by accepting responses without correlation/signatures.

## 17. Root-Cause Response and Remediation Workflow

### Step 1: Confirm the SSO Profile

SP-initiated or IdP-initiated? If SP-initiated, is there an outbound AuthnRequest ID? If IdP-initiated, is an unsolicited policy approved?

### Step 2: Check Evidence at the SP

Are `REQUEST_CREATED` and `REQUEST_SAVED` present with `requestRef`, `sessionRef`, `registration`, and `node`? If not, fix the initiation matcher/filter/config.

### Step 3: Check the Browser HTTP Callback

Right ACS URL/method? `JSESSIONID` included/excluded? SameSite/Domain/Path/Secure/tracking protection? Is the browser inside an iframe?

### Step 4: Check Ingress and the Session Store

Did the cookie reach the backend? Does `getSession(false)` return a session? Are session TTL, invalidation, Redis namespace, node routing, and serialization proper?

### Step 5: Reconcile the Transaction

Was the saved Request ID A or B? What is Response `InResponseTo`? What is `RelayState`? Did the repository load A, B, or null? Did another tab overwrite it or a duplicate callback consume it?

### Step 6: Classify SAML Validation

After correlation, verify signature, issuer, audience, recipient, destination, Conditions/SubjectConfirmation/replay; finally verify local account and authorization.

### Step 7: Apply Minimal Fix and Retest

- Cookie excluded by SameSite: fix SameSite/HTTPS if approved, or use a repository with proper browser binding.
- Wrong cookie scope: fix Path/Domain/host.
- Proxy strips Cookie: fix gateway.
- Multi-node session store: shared storage/consistent TTL.
- Multi-tab overwrite: per-transaction storage + browser binding + atomic consume.
- Wrong ACS/registration: fix metadata/IdP/ingress in sync.
- IdP-initiated: explicit policy, never enable unconditional fallback.
- Other validation: fix trust/clock/user status, **never disable checks**.

### Step 8: Observe and Run Regressions

Reproduce single tab, two tabs, out-of-order callbacks, slow MFA, session timeout, pod failover, replay, wrong RelayState/InResponseTo, cross-browser injection, wrong issuer, and disabled local account.

## 18. Anti-Patterns to Avoid

1. Disabling InResponseTo to "fix login".
2. Enabling unsolicited responses from any IdP.
3. Treating RelayState presence as proof of browser ownership.
4. Using RelayState as an arbitrary open redirect URL.
5. Caching requests by RelayState without browser binding.
6. Using one request per session when concurrent tabs are needed without testing.
7. Simply increasing session TTL indefinitely.
8. Disabling session fixation protection because Session ID rotates after auth.
9. Dropping signature/Audience/Recipient validation because a cookie was present.
10. Using internal HTTPS as proof of the public callback URL.
11. Trusting browser-asserted forwarded headers.
12. Testing only GET without testing SameSite on POST.
13. Enabling `SameSite=None` and then disabling CSRF app-wide.
14. Assuming cookie included means the session is still alive.
15. Assuming session alive means the pending request is still there.
16. Calling `removeAuthnRequest` yourself while debugging.
17. Logging raw SAMLResponse, RelayState, JSESSIONID, or NameID.
18. Using a local in-memory session map per pod in a cluster without affinity/failover.
19. Confusing Response ID with AuthnRequest ID.
20. Treating a local permission 403 as an InResponseTo error.

## 19. Pre-Production Acceptance Checklist

1. AuthnRequest is genuinely created and stored by a known-version repository.
2. Safe `requestRef`, `relayRef`, `registration`, and `node`/`sessionRef` exist to stitch traces.
3. Browser callbacks reach the exact HTTPS ACS specified in metadata.
4. Browser DevTools confirms cookie included/excluded status and reason.
5. Cookie SameSite properly accounts for cross-site POST and browser privacy policies.
6. `SameSite=None`, if used, has `Secure`/HTTPS and full business CSRF protection.
7. Cookie Domain/Path/name/lifetime cover ACS without conflicts.
8. Gateway does not strip Cookie and does not trust attacker forwarded headers.
9. Backend distinguishes Cookie present, Session present, and PendingRequest found.
10. Session store shares properly across pods with appropriate TTL/serialization.
11. Multi-tab does not overwrite AuthnRequest, or policy provides safe fallback handling.
12. Caching requests by RelayState includes browser binding, single-use consumption, and anti-login-CSRF protection.
13. Wrong InResponseTo/RelayState/issuer/audience/recipient are all rejected.
14. IdP-initiated SSO has its own policy and is never a fallback for missing requests.
15. Spring probe never creates a session while debugging and never logs raw secrets.
16. ACS filter/CSRF matcher is narrowly scoped without opening business routes.
17. Multi-node failover, Redis outage, long MFA, and request expiry are tested.
18. SAML signature/Conditions/replay and local account authorization are verified.
19. Logs/audit/metrics contain no raw assertions/cookies/user secrets.
20. Security validations are never traded away for login success rates.

## 20. Self-Check Knowledge Questions

1. **How do AuthnRequest ID and InResponseTo relate?** — InResponseTo points back to AuthnRequest ID.
2. **Is RelayState alone enough to verify the browser?** — No; binding is required.
3. **Where does Spring Security store AuthnRequest by default?** — `HttpSessionSaml2AuthenticationRequestRepository`.
4. **Why can explicit SameSite=Lax lose the cookie?** — A cross-site POST from the IdP is not a top-level safe GET.
5. **What does SameSite=None require?** — Secure/HTTPS and business CSRF protection, plus awareness of browser privacy policies.
6. **What does Cookie included yet Session null indicate?** — Store TTL/eviction/node/namespace/invalidation.
7. **Session exists yet loads B while InResponseTo is A?** — Multi-tab overwrite or wrong mapping.
8. **Should InResponseTo be removed?** — No, it protects login correlation.
9. **What must a RelayState-keyed cache add?** — Browser binding, TTL, atomic consumption, and replay policy.
10. **Is Session ID rotation after success a bug?** — No, it can be proper session fixation protection.
11. **How does IdP-initiated login differ from SP-initiated?** — No original AuthnRequest; requires a dedicated profile policy.
12. **Best evidence for an excluded cookie?** — Browser DevTools on the ACS POST showing the reason.
13. **Best evidence for multi-tab overwrite?** — Save A, Save B in the same session; callback A loads B.
14. **What does multi-node require?** — Shared session/request state, TTL, atomicity, and failover QA.
15. **What to do when InResponseTo matches yet signature fails?** — Fix trust/IdP validation, do not tweak SameSite.
16. **Why avoid `getSession()` in a probe?** — It can create a new session and skew conclusions.
17. **Can raw SAMLResponse be logged for debugging?** — No, it contains assertions and PII.
18. **Why does cookie scope matter?** — Domain/Path/Secure determine whether the browser sends it on ACS.
19. **What if SAML validates OK yet the local account is disabled?** — Deny local admission.
20. **Fastest debugging order?** — Outbound/save → browser cookie → ingress/session → request load/ID match → SAML validator → local authz.

## References

- [Spring Security — Producing SAML2 AuthnRequests: HttpSession repository, CacheSaml2AuthenticationRequestRepository, RelayState trade-offs](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML2 Responses and OpenSAML provider](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security issue #14793 — Multi-tab AuthnRequest overwrite in session (version-specific)](https://github.com/spring-projects/spring-security/issues/14793)
- [Spring Boot Servlet Web Applications — SameSite session cookie configuration](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [MDN — Set-Cookie: SameSite, Secure, default-Lax grace](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Using HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Secure Cookie Configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- [Spring Security — Session Management and Fixation Protection](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)