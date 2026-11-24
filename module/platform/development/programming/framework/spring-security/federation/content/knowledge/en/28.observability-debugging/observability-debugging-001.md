# Tracing the Redirect Chain and Pinpointing the Failing SSO Step

> **Topic:** Spring Security – federation. **Category:** Observability and debugging. Standalone Knowledge article guiding how to reconstruct Single Sign-On (SSO) steps, find the **last successful step** and **first failing step** when a Java 17+/Spring Security Servlet application integrates OpenID Connect (OIDC)/OAuth2 Login, SAML 2.0, CAS, Kerberos/SPNEGO, or authenticates behind a reverse proxy. The goal is accurate observability while **not leaking authorization codes, SAMLResponse, service tickets, session cookies, private keys, or tokens**.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish requests made by the browser (**front-channel**) from requests Spring makes directly to the IdP/token endpoint/CAS (**back-channel**).
2. Understand `302`/`303`/`307`, auto-submitting HTML `200`, `401` Negotiate challenge, and `403` authorization denial in the right context.
3. Diagram the OIDC Authorization Code flow: `/oauth2/authorization/{registrationId}` → IdP authorize → `/login/oauth2/code/{registrationId}` → token/JWKS/UserInfo → session → business resource.
4. Diagram the SAML flow: `/saml2/authenticate/{registrationId}` → AuthnRequest → IdP login → browser **POST** `SAMLResponse` to `/login/saml2/sso/{registrationId}` → OpenSAML validation.
5. Recognize CAS `service`/`ticket`/`serviceValidate` and Kerberos `401 WWW-Authenticate: Negotiate`/`Authorization: Negotiate`; do not force these two protocols into the OIDC mold.
6. Find failures caused by lost `state`, `RelayState`, `InResponseTo`, PKCE `code_verifier`, browser cookie `SameSite`, Proxy `Forwarded`, session store, token endpoint, signing keys, or authorization.
7. Collect DevTools Network Preserve log/HAR in a controlled manner, trace IDs, sanitized logs from proxy/Spring/IdP, and classify failures by owner.
8. Safely instrument a Spring Boot filter to track **route category, method, status, duration** without accessing raw query/form/header credentials.
9. Run a standalone Java 17 program to classify a simulated event sequence into `COMPLETE`, `CORRELATION_GAP`, `REDIRECT_LOOP`, callback/back-channel error, or normal challenge.
10. Build a happy path/negative cases test matrix and an acceptance checklist without weakening state/signature/CSRF/issuer/audience protections.

**Principle:** An HTTP `302` only states that the browser was told to navigate to another URL. It **is not itself an SSO success or failure**. A callback returning 302 might be redirecting to the target page after successful authentication, or to `/login?error` after failed authentication. Diagnosis requires evidence about the request, the responding component, correlation, provider validation, and session.

## 2. Four-Boundary Observability Model

```text
                  BROWSER
                   |   ^
          (1) navigation / cookies /
              redirects / HTML form POST
                   |   |
                   v   |
          [EDGE / CDN / WAF / PROXY]
              TLS, Host, routing
                   |   ^
                   v   |
          [SPRING SECURITY APP]
              FilterChainProxy,
              AuthnEntryPoint,
              callback filters,
              SecurityContext, session
                   |   ^
      server HTTP  |   |  server responses
                   v   |
          [OP / IDP / CAS / DIRECTORY]
          token, JWKS, UserInfo,
          CAS ticket validation
                   |
          [BUSINESS AUTHORIZATION]
            user + role + tenant + resource
```

What the diagram separates:

- **Browser:** sees HTTP redirections, the IdP login page, consent/MFA, SAML auto-submit forms, and cookies sent/blocked. DevTools only records requests made by the browser.
- **Proxy:** sees the status it returns itself and the upstream status from Spring, latency, TLS, virtual host/path rewriting; it can return 413, 502, 504 before Spring ever receives the request.
- **Spring:** selects the SecurityFilterChain, creates the authentication request, receives the callback, verifies correlation/claims/certs, calls the back-channel, saves SecurityContext to HttpSession/Spring Session, and then redirects.
- **IdP/OP/CAS/KDC:** is responsible for credential login, MFA, signed assertions, token issuance, or ticket validation. Separate logs from that system are needed; Spring cannot automatically see every IdP policy failure.
- **Business application:** a passing login does not mean permission to view/pay/administer a resource. An HTTP `403` after a valid session can be **correct authorization**.

### 2.1. Measurements Needed for Each Request

```text
UTC timestamp
origin/category (browser, edge, app, IdP)
HTTP method and status
sanitized route category
redirect target origin/path (NO query values)
Set-Cookie/Cookie presence & attributes (NO cookie values)
application requestId / traceId where available
SSO protocol & configured registrationId
authentication stage (START, IDP, CALLBACK, TOKEN, SESSION, RESOURCE)
signed/correlated/denied decision category
instance/pod and session lookup result if instrumented
upstream status and duration at edge
```

Do not infer a `sessionLookup=MISS` event unless it was measured at the session repository. Do not put NameID/username/email, user-supplied Host, full redirect URL, raw `state`, or `ticket` into Prometheus labels.

## 3. Reading HTTP Status Codes in Context

| Status | Valid Case | Sign Worth Investigating |
| --- | --- | --- |
| `200 OK` | IdP login page; HTML form auto-POSTing SAML; business page after login | 200 but returns HTML login instead of the requested resource |
| `302 Found` | SP to IdP, IdP to callback, SP to saved request | Continuous 302 loop without creating a session |
| `303 See Other` | Switch to GET after POST | Redirect not in the allowlist |
| `307/308` | Preserve method/body on redirect | SAML POST could be sent with its body intact to the wrong host/route; avoid |
| `400` | Not an SSO success | Malformed form/callback/state, invalid SAML response format |
| `401` | Initial SPNEGO `WWW-Authenticate: Negotiate` challenge | Invalid API Bearer, SPNEGO does not continue, CAS callback error |
| `403` | Authenticated user without permission | SAML ACS POST blocked by CsrfFilter/WAF; missing tenant/role |
| `404` | Route does not exist | Wrong callback/ACS route or filter chain |
| `413` | Not a successful login | SAMLResponse form body/attributes too large |
| `429` | System rate limit | Login storm/loop, IdP throttling |
| `500` | App error | Provider/validator exception, request mapping bug |
| `502` | Gateway cannot connect/read upstream | TLS, DNS, upstream reset; request may not have reached Spring |
| `503/504` | Downstream down/timeout | Token/JWKS/IdP/Redis service unavailable |

For example, `302 → 200 → 302 → 302 → 200` is a **potentially valid** SSO sequence; do not blame the flow just because there are multiple `302`s. Read the outcome of the step **after** the redirect. A `302` with `Location: /login?error` plus an authentication failure event is stronger evidence than an isolated HTTP status code.

### 3.1. What Is Special About `Location`

```text
HTTP/1.1 302 Found
Location: https://idp.example.org/authorize?
    client_id=portal&
    redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcorp&
    response_type=code&
    state=REDACTED&
    nonce=REDACTED&
    code_challenge=REDACTED
```

In reports, keep only: status 302, host `idp.example.org`, path `/authorize`, query key **names**, and stage `OIDC_AUTHORIZATION_REDIRECT`. Raw `code`/`state`/`ticket`/`RelayState`/`SAMLResponse` must not be logged. Do not send tokens into an external redirect tracing service.

## 4. General Playbook: Tracing an Attempt to Completion

1. Identify the **test** user/environment, public hostname, protocol, expected IdP/registrationId, tenant, UTC timestamp, and browser version. Do not reproduce with production credentials in an unapproved debug environment.
2. Open DevTools → Network **before** logging in, enable **Preserve log**, filter `All` when there is a SAML POST. Use only one tab to initiate the first flow; test concurrent tabs afterward.
3. Record the **first protected resource request**: method/status, redirect location origin/path, did it reach Spring or get blocked at the edge?
4. Identify the SP initiation request: `/oauth2/authorization/corp` or `/saml2/authenticate/corp`, CAS `/cas/login?service=...`, or `401 Negotiate`.
5. Find the IdP interaction: login page `200`, MFA, consent, policy deny, or redirect. Failures at the IdP require a separate IdP audit event ID.
6. Find the **callback to the SP**: OIDC GET `/login/oauth2/code/corp`, SAML POST `/login/saml2/sso/corp`, CAS GET `/login/cas` with ticket; SPNEGO uses the same endpoint with a Negotiate header.
7. Prove the callback **passed through the proxy to Spring**, was handled by the right filter, the correlation state was found, and the authentication provider produced a decision.
8. If the callback reached Spring but failed, check the server back-channel (OIDC token/JWKS/UserInfo, CAS validation) and SAML XML signature/conditions, along with the exact error category.
9. After authentication success, check that the app `SecurityContext` was saved, a cookie was issued, and the next request **sends the cookie properly**; if multi-pod, check the Redis/JDBC session store.
10. Access the final resource: 200 correct page, 401 missing authentication, 403 expected/incorrect authorization, or 302 back to login?
11. Record **last good stage → first failed stage → actor/owner → evidence ID → remediation → regression test**. Do not conclude "the IdP is broken" just because the browser returned to login.
12. After the investigation, turn off broad TRACE, purge sensitive artifacts per policy, and report using redacted evidence only.

**Conclusion standard:** "Browser reached the SP callback at 09:50 UTC; callback was received by the filter; correlation lookup MISS on pod-2, token endpoint was not called; browser did not send the session cookie on the callback" is more accurate than "SSO redirect failed".

## 5. OAuth2/OIDC Authorization Code: Reference Flow

Spring Security Servlet uses:

```text
(1) Browser -> GET https://portal.example.org/private
(2) Spring  -> 302 /login or /oauth2/authorization/corp
(3) Browser -> GET /oauth2/authorization/corp
(4) Spring  -> 302 https://idp.example.org/authorize?
                    response_type=code&client_id=...&
                    redirect_uri=...&state=...&
                    code_challenge=...&nonce=...
(5) Browser -> IdP authorize/login/MFA (200 or more 302)
(6) IdP     -> 302 https://portal.example.org/
                    login/oauth2/code/corp?code=...&state=...
(7) Browser -> GET /login/oauth2/code/corp?code=...&state=...
(8) Spring  -> [SERVER-TO-SERVER] POST IdP /token
                    code + client authentication + PKCE code_verifier
(9) Spring  <- [SERVER-TO-SERVER] tokens / error
(10) Spring -> verify ID Token, iss/aud/nonce/exp/signature/JWKS
             optional UserInfo / local account mapping
(11) Spring -> save Authentication / SecurityContext / session
(12) Spring -> 302 originally requested URL
(13) Browser-> GET /private with session cookie
(14) Spring -> 200 resource or 403 business authorization
```

**Steps (8)–(10) do not appear in browser Network**; those are outbound requests from the JVM. A `302` callback only says Spring redirected, not that step (8) was executed or succeeded.

### 5.1. Values That Must Be Correlated

| Value | Managed By Whom? | Condition | If Wrong/Missing |
| --- | --- | --- | --- |
| `state` | Generated by OAuth2 client before redirect, matched on callback | Matches saved authorization request | `invalid_state`/authorization request not found |
| `OAuth2AuthorizationRequestRepository` | Usually bound to `HttpSession` in Servlet flow | Prior request still retrievable | Callback cannot link the transaction |
| `redirect_uri` | ClientRegistration + IdP allowlist | Exact public callback + token exchange | `invalid_redirect_uri`/`invalid_grant` |
| `code` | Issued once by OP for client | Unused, unexpired | `invalid_grant` or code replay |
| PKCE `code_challenge`/`code_verifier` | Initiated/proven by client at token exchange | Same transaction | Token endpoint rejects |
| `nonce` in OIDC | Client + ID Token | Matches request when requested | ID Token rejected |
| `iss`/`aud`/`azp` | ID Token / OP metadata | Correct OP and client policy | Invalid issuer/audience |
| `exp`/`iat` | ID Token | Valid time per validator | Expired token, clock skew |
| JWKS `kid`/signature | OP signing keys | Key currently trusted | Unknown kid/invalid signature |
| Session cookie | Browser, Spring session store | Cookie sent back on callback/resource | Saved request/session lookup miss |

**Do not log `state` to "stitch traces"**. If you need an identifier for the entire login journey, generate a random server-side ID bound to the trusted authorization request state/session; log only that ID, or log a keyed HMAC digest after security review. Do not use raw state/ticket/code as trace IDs.

### 5.2. OIDC Failures by Step

- **Step (4) never appears:** Wrong login link, missing `ClientRegistrationRepository`, filter chain does not match `/oauth2/authorization/{registrationId}`, wrong registrationId.
- **IdP rejects at (5):** `redirect_uri` not in client allowlist, wrong `client_id`, user policy/MFA/consent denied. Need IdP logs, do not manually edit browser query parameters.
- **Callback (7) arrives but state lookup MISSES:** Browser did not send session cookie or session expiry/Redis issue/multi-pod memory session/parallel tabs caused state overwrite. Keep the state check, fix session/cookies.
- **Token endpoint (8) returns `invalid_grant`:** Code expired/reused, different redirect_uri, wrong PKCE verifier, client authentication, or timing. Do not replay a production code to retry.
- **Token exchange PASSES but OIDC `OidcUserService`/decoder FAILS:** Check `iss`/`aud`/`nonce`/`exp`/JWK kid/signature, UserInfo/network/TLS, local account status. Do not accept unsigned JWTs or arbitrary JWKS.
- **App succeeds but (13) returns to login:** `Set-Cookie`/`Cookie` Domain/Path/Secure/SameSite, session fixation ID rotation, Redis saves, load balancer, wrong forwarded proto.
- **OIDC web login PASSES but API returns 401:** An `oauth2Login` session cookie does not automatically substitute for an `oauth2ResourceServer` Bearer access token for another service. The token must have the right audience/scopes; do not use an ID Token as an API access token.
- **Callback with `response_mode=form_post`:** Do not assume GET; must test cross-site POST cookies/CSRF like SAML if the OP uses this mode.

### 5.3. Example Configuration for an OIDC Web App

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-op
            client-id: "portal-client"
            client-secret: "SET_VIA_SECRET_MANAGER_NOT_IN_GIT"
            scope: openid,profile,email
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp-op:
            issuer-uri: "https://idp.example.org/realms/corp"

server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

This is a **Spring Boot 3.x fragment**, and will not run standalone without a project/dependencies, a test IdP, and safely mounted secrets. `same-site: lax` is usually valid for a top-level GET OAuth2 callback, but is **not** a universal rule for every SAML/POST callback. `forward-headers-strategy` is only appropriate when a trusted edge strips/overwrites `Forwarded`/`X-Forwarded-*`.

## 6. SAML2: HTTP-POST Callbacks Often Have No 302 from the IdP

### 6.1. Typical SP-Initiated Sequence

```text
(1) Browser -> GET /finance/reports
(2) Spring  -> 302 /login or /saml2/authenticate/corp
(3) Browser -> GET /saml2/authenticate/corp
(4) Spring  -> create AuthnRequest ID R-123,
               store correlation/request context
(5) Spring  -> 302 IdP SSO URL with SAMLRequest + RelayState
               (HTTP-Redirect Binding)
               OR 200 HTML form POST to IdP
(6) Browser -> IdP login/MFA (200 or 302)
(7) IdP     -> 200 HTML with hidden SAMLResponse,
               RelayState and auto-submitting form
(8) Browser -> POST /login/saml2/sso/corp
               Content-Type: application/x-www-form-urlencoded
               SAMLResponse=<Base64 signed XML>
(9) Spring  -> Saml2WebSsoAuthenticationFilter/OpenSAML
               signature, issuer, destination, audience,
               recipient, time, InResponseTo/replay
(10) Spring -> map NameID/attributes; save Authentication
(11) Spring -> 302 saved resource
(12) Browser-> GET resource with app session cookie
(13) Spring -> 200 or authorized 403
```

**Do not apply a Network filter that only shows 302 redirects**. Step (7) is HTML `200`, step (8) is a browser **POST**. Browser JavaScript/CSP/extensions can block auto-submit; in that case the IdP reports login success but the app **never receives SAMLResponse**.

### 6.2. Correlating SAML Values

| Component | What Is Checked? | Corresponding Failure |
| --- | --- | --- |
| `registrationId` | Correct internal SP–IdP pair | Unknown registration/wrong tenant |
| `AuthnRequest@ID` | Issued saved request | Lost `InResponseTo` correlation |
| `RelayState` | Transaction/navigation state per binding | Lost/altered context, open redirect |
| `Issuer` | IdP EntityID matches registration | Wrong IdP/tenant |
| XML Signature | Trusted IdP key, exact signed node | Invalid signature/unknown certificate |
| `Destination` | Public ACS to which Response is sent | Wrong scheme/host/path |
| `SubjectConfirmationData.Recipient` | SP ACS receiving bearer assertion | Wrong recipient |
| `AudienceRestriction` | Correct SP EntityID | Wrong audience |
| `InResponseTo` | Points to created request (when SP-initiated) | Missing request/session/mismatch |
| `NotBefore/NotOnOrAfter` | Validity window | Clock skew/NTP/expired assertion |
| `NameID`/`AttributeStatement` | Verified principal/attributes | User mapping/group explosion |
| `SessionIndex` | Links SAML SLO session | Not the `HttpSession` ID |

**Byte/crypto layer:** SAMLResponse is Base64 of XML under HTTP-POST binding; it can contain many group values, multiple signatures, and encrypted assertions. There must be size limits at the edge/container/parser. Do not parse XML with regex and trust NameID/Role before OpenSAML signature/conditions verification.

### 6.3. Symptoms and Root-Cause Candidates

- **SP `/saml2/authenticate/corp` returns 404:** Missing RelyingPartyRegistration, wrong Spring SecurityFilterChain, default/custom URL mismatch.
- **IdP displays an error before returning callback:** SP EntityID/ACS unregistered, AuthnRequest signature/binding error, IdP login/MFA policy denied.
- **IdP 200 HTML form but no POST to ACS:** JS/CSP/extension/browser, wrong form action, network block. Check DevTools Console/Initiator before debugging XML signatures.
- **Edge sees ACS POST, Spring does not:** NGINX/WAF 413/403/502, upstream TLS, route/host/path mismatch. Use `upstream_status`, do not disable validation.
- **ACS POST reaches Spring and returns 403:** Either `CsrfFilter` blocked **before** the SAML filter or a WAF returned 403; distinguish from logs. An ACS POST from the IdP does not carry a normal Spring CSRF token; a precisely scoped exception for the SAML endpoint is required. **Do not disable CSRF app-wide**.
- **OpenSAML authentication FAILS:** Signature/issuer/audience/recipient/destination/time/InResponseTo mismatch, certificate rollover, replay. Check the sanitized reason and IdP metadata/trusted keys; do not trust unverified `KeyInfo`.
- **SAML provider succeeds, browser returns to IdP:** Spring session/cookie lost, SameSite cross-site POST, session repository, multiple pods; IdP SSO may still be alive while the app session is not.
- **Login OK but resource returns `403`:** Business tenant/roles, not signature. Do not fix by setting `permitAll()` on the resource.

### 6.4. SameSite and Cross-Site POST Correlation

```text
T0  Browser GET /saml2/authenticate/corp
    Spring creates HttpSession H-1 and stores AuthnRequest R-123.

T1  Browser visits external IdP at another site.

T2  IdP HTML auto-POSTs SAMLResponse back to SP ACS.

T3  Browser may omit SESSION=H-1 cookie
    because SameSite=Lax normally blocks cross-site POST.

T4  Spring cannot retrieve R-123 for InResponseTo.
    Login fails or loops despite valid IdP signature.
```

Check the browser's **Cookies/Blocked cookies reasons** and `SameSite`, `Secure`, `Domain`, `Path` attributes. When a use case requires `SameSite=None; Secure`, HTTPS is required, along with browser CSRF protection on business endpoints and evaluation of browser/third-party cookie policies. Cookie behavior depends on browser version/heuristics; test on target browsers rather than assuming one absolute rule for all devices. Do not drop `InResponseTo`/replay/signature checks to compensate for cookie issues.

## 7. CAS: Service Ticket in Browser, Validation on Server

```text
(1) GET https://portal.example.org/private
(2) App 302 https://cas.example.org/cas/login?
              service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas
(3) CAS login page 200; user authenticates / TGC SSO
(4) CAS 302 https://portal.example.org/login/cas?ticket=ST-...
(5) Browser GET /login/cas?ticket=ST-...
(6) Spring -> [SERVER-TO-SERVER] CAS /serviceValidate
              with exact service URL and ticket
(7) CAS -> [SERVER-TO-SERVER] ticket success/error
(8) Spring -> local Authentication, session, redirect resource
```

`/login/cas` is the default URL in many `CasAuthenticationFilter` integrations; systems may use a custom route. `service` must match the public service URL registered and used by CAS to issue the ticket: differing HTTPS/HTTP, hostname, port, path, or trailing slash can cause ticket rejection.

**If the callback has a ticket but the app returns to login:** check CAS back-channel network/TLS, CAS service registry, ticket single-use/expiry, `ServiceProperties`, and session. **Do not replay raw tickets** taken from production HARs or `ticket` query logs. CAS Server TGT/TGC and the local app session have different lifecycles; local logout does not automatically guarantee CAS global logout.

## 8. Kerberos/SPNEGO: A 401 Challenge Is a Normal Step

```text
(1) Browser -> GET https://intranet.example.org/private
               without Authorization: Negotiate
(2) Server  -> 401 Unauthorized
               WWW-Authenticate: Negotiate
(3) Browser -> obtains service ticket through OS/KDC
               then GET with Authorization: Negotiate <token>
(4) Server  -> JAAS/GSS validates AP-REQ via HTTP service keytab
(5) Server  -> 200 resource OR further challenge/failure
```

**Do not call step (2) "SSO failed" solely because of 401.** Look for the subsequent request: does the browser send `Authorization: Negotiate`? If not, check browser enterprise policy/trusted intranet zone, SPN DNS/host, KDC ticket cache, and user environment. If it did send it and still got 401, check `HTTP/public-host@REALM`, keytab/KVNO, etype, time skew, GSS service acceptor, and delegation/channel binding per design.

`Authorization: Negotiate` carries a sensitive token; do not print the raw header. When SPNEGO terminates at the edge, Spring only accepts an identity if there is a trusted pre-auth contract over a protected channel; an unverified HTTP `X-User` header is not Kerberos proof. Some integrations have a `302` form login fallback; distinguish fallback policy from Kerberos success.

## 9. Reverse Proxy: Losing Public URL and Redirect Loops

```text
Browser: https://portal.example.org/private
             |
             v
    NGINX HTTPS termination
             |
             v
    Spring app http://spring:8080
             |
             +-- WITHOUT trusted forwarding:
                   Spring sees http://spring:8080
                   generates redirect_uri/ACS/service with wrong host/scheme
             |
             +-- WITH canonical forwarding:
                   Spring sees https://portal.example.org
                   generates expected registered callback URLs
```

Wrong forwarded headers can cause OIDC `invalid_redirect_uri`, SAML `Destination`/`Recipient` mismatch, CAS `service` mismatch, and `https → http → https` loops. Do not simply change the IdP allowlist to the internal URL, because the browser may not be able to reach it and TLS/sessions will be wrong.

### 9.1. NGINX Trusted Edge Fragment

```nginx
# Fragment inside server { listen 443 ssl; ... }
location / {
    proxy_pass http://spring.internal:8080;

    # At trusted edge: do not forward client-asserted values.
    proxy_set_header Host portal.example.org;
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Host portal.example.org;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;

    # Request correlation internal to app/edge only.
    proxy_set_header X-Request-ID $request_id;

    proxy_connect_timeout 5s;
    proxy_read_timeout 30s;
}
```

If proxy→backend mTLS is required, replace `proxy_pass http://...` with an HTTPS upstream having `proxy_ssl_verify on`, proper CA/SNI, and a client certificate; the example above illustrates canonical forwarding, not an mTLS deployment. The edge must strip/overwrite both `Forwarded` and the `X-Forwarded-*` group; client-supplied `X-Request-ID` should also be replaced by an ID generated at the trusted edge, and not used as identity.

Spring Boot fragment:

```yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

**Note:** `forward-headers-strategy` does not itself verify proxy identity. If the app is directly exposed publicly or an attacker spoofs `X-Forwarded-Host`, malicious redirects/open redirects can occur. Block bypass paths, enforce canonical hosts, trusted proxy IPs/workload identity, and test host spoofing. If the IdP uses cross-site POST, `same-site: lax` must be reviewed per section 6.4.

### 9.2. Common Loops

| Loop | Evidence | Remediation Step |
| --- | --- | --- |
| `/private → /login → /private` infinite | Auth cookie not sent/Redis MISS | Cookie + session storage |
| `https → http → https` | Edge 301, Spring 302 back | Forwarded scheme, HTTPS policy |
| `OIDC IdP → callback → /login?error` | Auth failure handler | State, PKCE, token/JWKS |
| `SAML IdP → ACS → /login` | OpenSAML fail or no session | Signature/InResponseTo/cookie |
| `CAS → /login/cas → CAS` | Ticket validation/cookie failed | Service URL, CAS back-channel |
| Repeated 401 Negotiate | No Negotiate token/GSS failure | Browser policy, SPN, keytab |
| `/error` redirects to `/login` again | Error route protected or wrong chain | Secure error page config |
| 302 to internal hostname | Wrong Host/XFH | Canonical public base URL |
| Login succeeds but original URL lost | SavedRequest/handler override | RequestCache, success handler |

Avoid dangerous workarounds: `permitAll()` on all routes, global `csrf.disable()`, skipping `state`/SAML signature, or trusting all certificates. Fix each boundary based on evidence.

## 10. Using DevTools Network and HAR Properly

1. Use staging IdP/accounts, open DevTools **before** starting.
2. Enable **Preserve log** to keep the timeline when the browser crosses sites. For SAML, view `All`, including POST and HTML forms, not only GET/Doc.
3. Record request method/status/host/path/response `Location` origin/path **without storing query values**.
4. Check **Initiator**: 302 navigation, auto-submitting HTML form, or script; check Console if the ACS POST does not appear.
5. Inspect `Request Headers` and `Response Headers` on the test machine, but only **share** presence/cookie attributes, not values.
6. Go to Network → Cookies / blocked reasons to check SameSite/Secure/Domain/Path and third-party restrictions.
7. Check timings: DNS/connect/TLS/wait; distinguish browser network outages from OIDC token endpoint calls that are not visible.
8. Use the `All` filter so you do not miss redirect responses/statuses of iframes, favicons, or forms; note that other requests may be noise.
9. Export **HAR (sanitized)** only when necessary. Per Chrome DevTools, sanitized mode strips some sensitive headers such as `Cookie`/`Set-Cookie`/`Authorization`, **but does not guarantee removing all query code/state/CAS tickets or form SAMLResponse**.
10. Review/redact every `request.url`, `postData`, `response.content`, custom headers, and screenshots before putting them into tickets/chat/IdP.
11. Store artifacts in access-restricted storage with short retention; do not use raw URLs as labels or send secrets to third-party APM tools.
12. Turn off debug mode once evidence is captured; check credential/session impact if an artifact was ever exposed.

### 10.1. Useful HAR Fields

| Field | Diagnostic Value | Security Rule |
| --- | --- | --- |
| `startedDateTime` | Order timeline by UTC | Ensure clock sync |
| `request.method` | GET vs SAML POST | Safe to log |
| `request.url` | Origin/path and query key names | Redact `code/state/ticket` values |
| `response.status` | Redirect/4xx/5xx | Do not infer authentication result alone |
| `response.redirectURL` | Next destination | Store origin/path only |
| `request.postData` | Did SAMLResponse/RelayState appear? | **Do not store raw payload** |
| `headers.Cookie` | Was session sent? | Presence only |
| `headers.Set-Cookie` | Was session issued? | Attributes only, no value |
| `timings` | Latency/network trouble | Safe to measure and compare |
| `_initiator` | Auto-submit/JS vs redirect | Find blocked POSTs |

### 10.2. Why `curl -L` Is Not Enough

`curl -L` does not execute HTML JavaScript auto-submitting SAML forms, does not perform IdP MFA/consent like a browser, does not simulate browser SameSite cookie rules, and does not show Spring backend token/JWKS/CAS validator requests. `curl -I` sends HEAD rather than GET; an endpoint may return a different status between HEAD and GET, so do not use it as full-flow evidence.

Simple test on staging, **without following redirects**, printing only status:

```bash
curl -sS --max-redirs 0 \
  -o /dev/null -w '%{http_code}\n' \
  https://portal.example.org/private
```

If printing response headers with `curl -D -`, it may expose `Location` containing code/ticket or `Set-Cookie`; do not copy the raw output into a ticket. These commands do not perform real authentication.

## 11. Correlation IDs: Do Not Use Tokens/Sessions as Trace IDs

There are three distinct correlation types:

- **Request ID:** Generated at the trusted edge or Spring for **a single HTTP request**. Useful for comparing NGINX status with Spring status; does not automatically carry over to the IdP when the browser navigates to another origin.
- **Distributed trace ID:** `traceId`/`spanId` from Micrometer Tracing/OpenTelemetry with instrumented server-to-server HTTP clients. Only propagates across supported/trusted hops, with no guarantee the IdP participates in the trace.
- **SSO journey ID:** A random ID generated by the app upon login initiation and stored with the server-side authentication request/session. Can correlate start, callback, token exchange, and session save under one safe ID, without logging raw `state`/`RelayState`/authorization code.

**Do not use a plain SHA-256 hash of `state`/ticket as a "safe correlation ID" by default**: some values may be guessable/reversible, and a hash can still act as a PII identifier. If a derived marker is needed, use keyed HMAC with secret management, scoped retention, and security review. Do not allow clients to supply `X-Request-ID`/`traceparent` to influence security decisions or metric cardinality; regenerate/normalize at the trust boundary.

### 11.1. Illustrative Structured Event

```json
{
  "event": "SSO_STAGE",
  "utc": "2030-05-10T09:50:00Z",
  "journeyId": "generated-server-side-id",
  "requestId": "generated-edge-id",
  "protocol": "OIDC",
  "registrationId": "corp",
  "stage": "CALLBACK",
  "method": "GET",
  "routeCategory": "oidc_callback",
  "status": 302,
  "decision": "FAIL",
  "reason": "AUTHORIZATION_REQUEST_NOT_FOUND",
  "cookiePresented": false,
  "sessionLookup": "MISS",
  "appNode": "portal-pod-2",
  "elapsedMs": 19
}
```

**This is a proposed schema, not a built-in Spring Security event.** `sessionLookup`/`decision` must only be recorded from actual measured/validation results. Do not use raw tokens, SAMLResponse, NameID, cookies, client secrets, or principal data as fields.

### 11.2. What Each Layer Can Prove

| Layer | Reliable Evidence | Does Not Prove |
| --- | --- | --- |
| Browser | Requests and responses seen; cookies blocked | That Spring called the token endpoint |
| Edge | Route/upstream status, TLS, request ID | That the user was authenticated by the IdP |
| Spring filter | Chain selection, callback received/validation outcome | Internal redirects inside the IdP without tracing |
| Spring Session | Session save/read HIT/MISS, TTL | That the IdP SSO session was logged out |
| OP/IdP | Login policy, MFA, token/assertion issued | That the local app session was saved successfully |
| CAS validator | Ticket valid/invalid and service URL | Browser session cookie policy |
| KDC/GSS | Ticket/SPN/keytab validation | Whether the app user has business tenant permission |
| App authorization | Role/tenant/resource allow/deny | That OAuth code state passed without a linked trace |

## 12. Spring Security Logging: Finding the Right Filter/Stage

Spring Security Servlet uses `FilterChainProxy` with multiple `SecurityFilterChain` instances. Enable targeted DEBUG/TRACE to confirm whether the callback passes through the expected filters.

Example **temporarily in staging**:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
    org.springframework.security.oauth2: DEBUG
    org.springframework.security.saml2: DEBUG
```

Commonly involved filters:

| Filter/provider | Role | When to Inspect |
| --- | --- | --- |
| `ExceptionTranslationFilter` | Invokes auth entry point when unauthenticated | Where GET to protected resource leads |
| `OAuth2AuthorizationRequestRedirectFilter` | Sends authorize request to OP | OIDC redirect never happens |
| `OAuth2LoginAuthenticationFilter` | Receives authorization response callback | OIDC callback fails |
| OAuth2 token response client/`OidcUserService` | Backend token exchange/UserInfo | Callback arrives but does not log in |
| `Saml2WebSsoAuthenticationRequestFilter` | Builds SAML AuthnRequest | Does not leave SP to IdP |
| `Saml2WebSsoAuthenticationFilter` | Receives SAMLResponse at ACS | POST reaches Spring without authenticating |
| `CsrfFilter` | Checks browser CSRF token | POST to ACS/other endpoint gets 403 before provider |
| `SecurityContextHolderFilter`/repositories | Reads/writes auth context per config | Login succeeds but session is lost |
| `AuthorizationFilter` | Resource permissions after auth | Auth PASSES but resource returns 403 |
| `CasAuthenticationFilter`/`CasAuthenticationProvider` | CAS ST processing/validation | CAS callback error |
| `SpnegoEntryPoint`/`SpnegoAuthenticationProcessingFilter` | Negotiate challenge/GSS | SPNEGO 401 repeats |

**Warning:** Exact filters/classes and ordering depend on the Spring Security version and active feature configuration. Spring 6 and Spring 7 have differences. Enabling `org.springframework.security=TRACE` may log URLs/parameters/headers depending on custom filters; it must be scoped by time/tenant/staging, checked for redaction, and disabled after investigation.

If a callback reaches the proxy with no Spring filter log, check gateway `502/404/413`, Service URL/upstream routing, or Servlet filter registration **before** guessing an XML/JWT failure. If Spring has multiple chains (API Bearer and browser SSO), test which chain the callback matched; routing into an API-only chain can return `401 Bearer` without ever running the OAuth2/SAML login filter.

## 13. Java Spring Boot Observation Filter Without Leaking Tokens

The following code uses Spring Boot 3.x, Spring Web, SLF4J, and Java 17. It **does not modify authentication**, only logs **category**/status and attaches appRequestId. It does not read `getQueryString()`/`getParameter()`/`SAMLResponse`/`Authorization`/`Cookie`/`Location`.

File `src/main/java/com/example/sso/SsoObservationFilter.java`:

```java
package com.example.sso;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class SsoObservationFilter
        extends OncePerRequestFilter {

    private static final Logger LOG =
        LoggerFactory.getLogger(SsoObservationFilter.class);

    private static String route(String path) {
        if (path == null) return "unknown";
        if (path.matches("^/oauth2/authorization/[^/]+$")) {
            return "oidc_start";
        }
        if (path.matches("^/login/oauth2/code/[^/]+$")) {
            return "oidc_callback";
        }
        if (path.matches("^/saml2/authenticate/[^/]+$")) {
            return "saml_start";
        }
        if (path.matches("^/login/saml2/sso(?:/[^/]+)?$")) {
            return "saml_acs";
        }
        if ("/login/cas".equals(path)) {
            return "cas_callback";
        }
        if ("/login".equals(path)) {
            return "login_page";
        }
        if (path.startsWith("/private/")) {
            return "protected_resource";
        }
        return "other";
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String id = UUID.randomUUID().toString();
        String routeCategory = route(request.getServletPath());
        long t0 = System.nanoTime();

        MDC.put("appRequestId", id);
        response.setHeader("X-App-Request-ID", id);

        try {
            chain.doFilter(request, response);
        }
        finally {
            long elapsedMs = (System.nanoTime() - t0) / 1_000_000L;

            LOG.info(
                "sso_request id={} route={} method={} status={} ms={}",
                id, routeCategory, request.getMethod(),
                response.getStatus(), elapsedMs);

            MDC.remove("appRequestId");
        }
    }
}
```

File `src/main/java/com/example/sso/ObservationFilterConfig.java`:

```java
package com.example.sso;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class ObservationFilterConfig {

    @Bean
    FilterRegistrationBean<SsoObservationFilter> ssoFilter() {

        var bean = new FilterRegistrationBean<>(
            new SsoObservationFilter());

        bean.addUrlPatterns("/*");
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return bean;
    }
}
```

**Scope:** Both files require Spring Boot dependencies/an actual project, and do not compile standalone with `javac`. The filter is a **Servlet Filter** registered by `FilterRegistrationBean` before the Spring Security FilterChain under normal ordering; do not also annotate it with `@Component` or attach the same instance via `http.addFilterBefore` to avoid running it twice. `getServletPath()` depends on Servlet/context-path and proxy rewriting; test actual routes.

**What can it not do?** This filter only reports request/route/status; **it cannot distinguish a 302 success from a 302 failure**, cannot read credential state, does not follow the back-channel, does not bridge the IdP origin, and does not prove the user was authenticated. To know success/failure, hook auth provider events or redacted success/failure handlers. Do not replace `SavedRequestAwareAuthenticationSuccessHandler` with a hardcoded handler without testing saved-request restoration.

`X-App-Request-ID` is a random ID for **each request**, not a login journey ID. `MDC.remove` in `finally` prevents leaking the ID to the next request on the thread pool. For async requests, `finally` may run before the response finishes; use appropriate Observation/AsyncListener for accurate final timing. If an exception is thrown and container error mapping runs after the filter, `response.getStatus()` may not be the final HTTP status and should be cross-checked against server access logs.

## 14. Spring Security SecurityFilterChain and Callback Routing

Spring Security 6.x Servlet fragment sample:

```java
package com.example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SsoSecurityConfiguration {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
```

You must add a real OAuth2 ClientRegistrationRepository and SAML RelyingPartyRegistrationRepository with appropriate module dependencies. When enabling both OIDC and SAML, design a login page/entry point to choose the IdP and regression test login. This is a **fragment**, not runnable with plain Java.

A callback must reside inside the security chain containing the right authentication filter, and must **not** be routed to a custom controller that manually grabs `code`/`SAMLResponse` and builds a session. `permitAll` must not replace verification at the callback. If the application configures multiple `SecurityFilterChain`s, inspect chain matchers and ordering; a resource server chain might intercept the callback and return 401/404, making it look like an IdP error.

### 14.1. Authentication Result Differs from HTTP Redirect

- A Spring success handler may redirect to `SavedRequest` or a default success URL. Depending on custom handlers, the URL can vary.
- A failure handler may redirect to `/login?error`, which is also an HTTP `302`.
- An exception from token exchange or SAML validation can be mapped to `401`/`400`/`302` depending on the handler.
- Log an **auth outcome event** (SUCCESS/FAIL with safe reason) at an approved extension point if proof is needed; do not guess success solely from a 302.
- `RequestCache` and `SavedRequestAwareAuthenticationSuccessHandler` return the user to the requested URL; a hardcoded custom success handler can lose proper navigation even when authentication succeeds.
- Server-side session save can fail due to Redis/downstream issues; auth success does not guarantee subsequent requests remain authenticated.

## 15. Micrometer Tracing and Session Continuity

Spring Boot Actuator/Micrometer Tracing can populate `traceId`/`spanId` in MDC when the proper dependencies/config are present; plain Spring Web alone does not provide full tracing. Boot-instrumented HTTP client builders can propagate traces over outbound calls to the OP token endpoint, UserInfo, and CAS, but cannot automatically bridge browser redirects across an external IdP.

```yaml
management:
  tracing:
    sampling:
      probability: 0.10

logging:
  pattern:
    correlation: "[${spring.application.name:},%X{traceId:-},%X{spanId:-}] "
```

This is a **Spring Boot version-dependent** fragment, with no guarantee of identical properties/dependencies across all 3.x/4.x releases. `0.10` is a sample rate, not real data or a compliance recommendation. Low sampling should not be used as the sole source of security auditing. **Do not put state/RelayState/authorization code/session cookies into baggage**; tracing exporters can ship data to external providers.

### 15.1. Session Continuity Checklist

```text
Before redirect:
   saved request or OAuth2AuthorizationRequest/AuthnRequest exists?
   session record created? Set-Cookie attributes?

At callback:
   browser sends corresponding cookie? (presence only)
   state/RelayState/InResponseTo points to saved transaction?
   same or other pod? shared Spring Session repository working?

After authentication success:
   SecurityContext saved? Session ID changed as expected?
   Set-Cookie sent? Cookie Domain/Path/Secure/SameSite correct?

After redirect back to resource:
   browser sent new app session cookie?
   Spring Session lookup HIT?
   Authentication restored, or anonymous?
   authorization allowed for tenant/resource?
```

**Session ID rotation** after authentication can be valid session fixation protection. Do not assume different cookie values before/after login are a bug. Conversely, a `200` login page when accessing `/private` after success can be a **lost session** even though the URL did not 302.

## 16. Standalone Java 17: Classifying Failure Steps from Trusted Events

The following example requires no Spring, IdP, HTTP server, or certificates. It illustrates how to read a list of **simulated events** to distinguish callback correlation, back-channel failure, and SPNEGO challenge; it does **not** perform real OIDC/SAML/CAS/Kerberos, does not decode tokens, and does not verify signatures. The `correlated`/`outcome` flags in the example are test fixtures, not values accepted from a browser.

File `SsoRedirectDiagnosisDemo.java`:

```java
import java.util.List;

public final class SsoRedirectDiagnosisDemo {

    enum Protocol { OIDC, SAML, CAS, SPNEGO }

    enum Stage {
        START, TO_IDP, CALLBACK, BACKCHANNEL,
        SESSION, RESOURCE, CHALLENGE
    }

    record Event(
        Protocol protocol,
        Stage stage,
        int status,
        boolean correlated,
        String outcome
    ) { }

    static String diagnose(List<Event> events) {
        if (events == null || events.isEmpty()) {
            return "NO_EVIDENCE";
        }

        Protocol protocol = events.get(0).protocol();
        for (Event event : events) {
            if (event.protocol() != protocol) {
                return "MIXED_PROTOCOL";
            }
        }

        if (protocol == Protocol.SPNEGO
                && events.size() == 1
                && events.get(0).stage() == Stage.CHALLENGE
                && events.get(0).status() == 401) {
            return "EXPECTED_NEGOTIATE_CHALLENGE";
        }

        // Heuristic demo, NOT an SSO standard:
        // 4 consecutive 302 redirects between START and TO_IDP.
        if (events.size() >= 4) {
            boolean looping = true;
            for (int i = events.size() - 4;
                    i < events.size(); i++) {
                Event event = events.get(i);
                if (event.status() != 302
                        || (event.stage() != Stage.START
                            && event.stage() != Stage.TO_IDP)) {
                    looping = false;
                }
            }
            if (looping) return "REDIRECT_LOOP";
        }

        for (Event event : events) {
            if (event.stage() == Stage.CALLBACK
                    && !event.correlated()) {
                return "CORRELATION_GAP@CALLBACK";
            }
            if ("FAIL".equals(event.outcome())) {
                return "FAIL@" + event.stage() + ":" + event.status();
            }
        }

        Event last = events.get(events.size() - 1);
        if (last.stage() == Stage.RESOURCE
                && last.status() == 200
                && "OK".equals(last.outcome())) {
            return "COMPLETE";
        }

        return "INCOMPLETE@" + last.stage();
    }

    static Event event(Protocol p, Stage s, int code,
            boolean correlated, String outcome) {
        return new Event(p, s, code, correlated, outcome);
    }

    public static void main(String[] args) {
        var oidcOk = List.of(
            event(Protocol.OIDC, Stage.START, 302, true, "OK"),
            event(Protocol.OIDC, Stage.TO_IDP, 200, true, "OK"),
            event(Protocol.OIDC, Stage.CALLBACK, 302, true, "OK"),
            event(Protocol.OIDC, Stage.BACKCHANNEL, 200, true, "OK"),
            event(Protocol.OIDC, Stage.SESSION, 302, true, "OK"),
            event(Protocol.OIDC, Stage.RESOURCE, 200, true, "OK"));

        var oidcLostState = List.of(
            event(Protocol.OIDC, Stage.START, 302, true, "OK"),
            event(Protocol.OIDC, Stage.TO_IDP, 200, true, "OK"),
            event(Protocol.OIDC, Stage.CALLBACK, 302, false, "UNKNOWN"));

        var samlDenied = List.of(
            event(Protocol.SAML, Stage.START, 302, true, "OK"),
            event(Protocol.SAML, Stage.TO_IDP, 200, true, "OK"),
            event(Protocol.SAML, Stage.CALLBACK, 403, true, "FAIL"));

        var casInvalid = List.of(
            event(Protocol.CAS, Stage.START, 302, true, "OK"),
            event(Protocol.CAS, Stage.CALLBACK, 302, true, "OK"),
            event(Protocol.CAS, Stage.BACKCHANNEL, 401, true, "FAIL"));

        var spnegoChallenge = List.of(
            event(Protocol.SPNEGO, Stage.CHALLENGE, 401, true, "OK"));

        var redirectLoop = List.of(
            event(Protocol.OIDC, Stage.START, 302, true, "OK"),
            event(Protocol.OIDC, Stage.TO_IDP, 302, true, "OK"),
            event(Protocol.OIDC, Stage.START, 302, true, "OK"),
            event(Protocol.OIDC, Stage.TO_IDP, 302, true, "OK"));

        System.out.println("oidcOk=" + diagnose(oidcOk));
        System.out.println("oidcLostState=" + diagnose(oidcLostState));
        System.out.println("samlDenied=" + diagnose(samlDenied));
        System.out.println("casInvalid=" + diagnose(casInvalid));
        System.out.println("spnegoChallenge=" +
            diagnose(spnegoChallenge));
        System.out.println("redirectLoop=" + diagnose(redirectLoop));
        System.out.println("empty=" + diagnose(List.of()));
    }
}
```

Compile and run with Java 17+:

```bash
javac --release 17 SsoRedirectDiagnosisDemo.java
java SsoRedirectDiagnosisDemo
```

**Exact** stdout:

```text
oidcOk=COMPLETE
oidcLostState=CORRELATION_GAP@CALLBACK
samlDenied=FAIL@CALLBACK:403
casInvalid=FAIL@BACKCHANNEL:401
spnegoChallenge=EXPECTED_NEGOTIATE_CHALLENGE
redirectLoop=REDIRECT_LOOP
empty=NO_EVIDENCE
```

### 16.1. Accurately Explaining the Limits

- `oidcOk`: the event list contains RESOURCE 200 with outcome OK; this **does not prove** the IdP actually signed a real token because the data was set by a test fixture.
- `oidcLostState`: the callback has `correlated=false`, so a correlation gap is reported; this must not be inferred from HTTP 302 alone.
- `samlDenied`: shows the callback was rejected with 403, **without identifying CSRF/WAF/signature** until an actor/failure reason is present.
- `casInvalid`: failure on the CAS ticket-validation back-channel; the browser may still observe a normal callback redirect.
- `spnegoChallenge`: the initial 401 is an expected negotiation stage; the next request is needed to conclude success.
- `redirectLoop`: a 4-redirect heuristic is not a theorem; IdP MFA can also produce multiple valid 302s, so a production detector needs URL categories, session progression, bounded time, and rate thresholds.
- `empty`: no evidence; more data must be collected rather than blaming the IdP.
- The code does not store/read raw tokens, cookies, or SAMLResponse; production observability must take trust decisions from real filters/providers.

## 17. Redirect and Localization Test Matrix

| Case | How to Reproduce in Staging | Failure Step/Criteria |
| --- | --- | --- |
| **OIDC happy path** | Resource → authorize → callback → token → session | 200 resource, correct login |
| **OIDC wrong redirect_uri** | Client URI not in OP allowlist | IdP authorization reject |
| **OIDC state missing** | Expire saved authorization request | Callback reject, do not drop state |
| **OIDC two tabs** | Start two concurrent logins | Separate correlation, no wrong overwrite |
| **OIDC code reuse** | Replay a test authorization code | Token endpoint `invalid_grant` |
| **OIDC PKCE wrong verifier** | Test with wrong verifier | Token request reject |
| **OIDC issuer wrong** | ID Token from OP B instead of OP A | Validation fail |
| **OIDC audience wrong** | ID Token aud for another client | Validation fail |
| **OIDC nonce mismatch** | Nonce differs from request | Validation fail |
| **OIDC signing key rotated** | OP publishes new JWK | Trusted JWKS refresh, unknown key reject |
| **OIDC token endpoint 503** | OP staging outage | Server-side back-channel fail |
| **OIDC UserInfo timeout** | Mock UserInfo timeout | App failure handled, no infinite loop |
| **OIDC form_post cross-site** | OP uses POST callback | Cookie/CSRF policy correct |
| **SAML happy path** | Signed Response ACS POST | Signature/conditions/session pass |
| **SAML JS blocked** | Block IdP auto-submit form | IdP 200 but no ACS POST |
| **SAML ACS wrong** | IdP POST to different path/host | Proxy 404, recipient/destination reject |
| **SAML CsrfFilter 403** | SAML ACS matcher lacks proper exclusion | Blocked before provider, fix scoped config |
| **SAML signature wrong** | Sign Response with unknown test cert | OpenSAML reject |
| **SAML issuer wrong** | Different IdP from registration | Reject |
| **SAML audience wrong** | Wrong SP EntityID | Reject |
| **SAML InResponseTo wrong** | Signed response R2, saved R1 | Reject |
| **SAML expired assertion** | NotOnOrAfter in the past | Reject |
| **SAML replay** | Replay assertion/response fixture | Reject per replay policy |
| **SAML 413** | Many groups make body too large | Edge/Servlet rejects before parser |
| **SAML SameSite=Lax POST** | Cross-site IdP ACS POST | Cookie blocked, correlation miss |
| **SAML two IdPs** | IdP A response to registration B | Reject, do not grant tenant B |
| **CAS happy path** | ST + serviceValidate | Login success |
| **CAS wrong service URL** | Public URL protocol mismatch | CAS ticket reject |
| **CAS ST replay** | Reuse a test ticket twice | Must not authenticate a second time |
| **CAS server TLS fail** | Untrusted CA on CAS endpoint | Back-channel failure |
| **SPNEGO first 401** | Request without token | Expected Negotiate challenge |
| **SPNEGO browser no token** | Browser does not trust origin | No Authorization header after 401 |
| **SPNEGO wrong SPN** | Ticket SPN differs from HTTP hostname | GSS reject |
| **SPNEGO keytab KVNO mismatch** | Stale server keytab | GSS reject |
| **Proxy wrong XFP** | App sees internal http | Wrong redirect_uri/ACS/service |
| **Proxy 502** | Backend TLS/DNS fail | Edge fails, Spring never receives |
| **HTTP/HTTPS loop** | Edge redirects HTTPS, app redirects HTTP | Repeated canonical path |
| **307 SAML POST** | Redirect ACS POST preserving body | Reject unsafe redirect/leak risk |
| **Session Redis outage** | Kill test Redis during callback | Authentication passes but session save/read fails |
| **Multiple pods local sessions** | Start pod A, callback pod B | Auth request missing |
| **Browser cookie Path wrong** | Session cookie does not reach callback | Correlation gap |
| **SavedRequest lost** | Hardcoded success handler | Login success, wrong post-login URL |
| **API Bearer only chain** | Callback routes into Resource Server chain | 401 instead of OIDC/SAML callback |
| **Authenticated but 403** | User lacks tenant permission | Expected business deny |
| **TRACE output audit** | Enable debug in staging | No raw code/ticket/SAMLResponse in shared logs |
| **Sanitized HAR audit** | Export HAR/test | Query/form secrets remain redacted |
| **IdP policy MFA deny** | User fails MFA requirement | Clear IdP error stage/owner |
| **Clock skew** | OP/IdP/adapter NTP drift | Token/assertion time reject; fix NTP |
| **Unknown registrationId** | Non-existent start URL | Do not fall back to another tenant |

**Post-validation cannot be tested by modifying signed SAML XML after signing**, because that causes a signature error before reaching the stage you want to test. For "wrong audience with valid signature", generate a signed fixture **with the wrong audience before signing** using a test IdP. For token exchange, use a staging OP and do not log production codes.

## 18. Six Practical Runbooks

### A. OIDC IdP Login Completes but Returns to `/login?error`

1. Verify the `/login/oauth2/code/corp` callback reaches Spring, not just the edge.
2. Confirm `OAuth2LoginAuthenticationFilter` actually matches.
3. Check the session cookie, `AuthorizationRequestRepository` lookup, and `state` correlation (do not log raw state).
4. If correlation passes, check token back-channel HTTP status/error class, PKCE verifier, redirect URI, and client auth.
5. If token passes, check ID Token `iss/aud/nonce/exp/signature`, JWKS, and local user mapping.
6. Record the sanitized reason. Avoid "fixing" by disabling state/PKCE.

### B. SAML IdP Reports 200 but No Login Occurs at the SP

1. Check whether the IdP returns an auto-submitting HTML POST form.
2. Look for the browser POST to ACS in Network. If missing, check JS/CSP/Console.
3. If the POST hits the edge but Spring does not see it, check WAF/413/502/location/TLS.
4. If Spring receives it, distinguish `CsrfFilter` 403 from OpenSAML signature/conditions rejection.
5. If SAML succeeds, check session persistence/cookies/browser.
6. Do not collect production SAMLResponses in uncontrolled tickets.

### C. SAML `InResponseTo` Invalid After Load Balancing

1. AuthnRequest is issued on pod A with state stored locally.
2. Callback ACS POST lands on pod B.
3. Pod B cannot find the local session/saved AuthnRequest → `InResponseTo` rejection.
4. Fix with shared Spring Session Redis/JDBC or a controlled sticky architecture, and test cookie SameSite.
5. Retest across two pods with signed IdP fixtures. Do not disable InResponseTo just to get 200.

### D. CAS Has a Ticket but Ticket Validation Fails

1. Browser callback GET has `ticket` (record presence only).
2. Check Spring CAS validator's outbound request to the CAS server.
3. Compare exact public `service` URL, client TLS truststore/hostname, and CAS registry.
4. Check ticket single-use/expiry; generate a new ticket in staging, do not replay.
5. Fix forwarded canonical URL if Spring sees an internal HTTP hostname.

### E. SPNEGO Repeatedly Returns 401

1. Does `WWW-Authenticate: Negotiate` appear? If not, check the entry point/chain.
2. Does the browser send `Authorization: Negotiate` on the next request? If not, check enterprise browser trust/OS ticket.
3. Does the server have a GSS acceptor and the right keytab `HTTP/host@REALM`?
4. Check SPN/DNS, KVNO, etype, NTP, and GSS error codes.
5. Do not log GSS tokens/keytabs; fall back to form login only if allowed by policy.

### F. Login PASSES but `/admin` Returns 403

1. Is there an authentication success event and session HIT?
2. Is the 403 from Spring `AuthorizationFilter`/`@PreAuthorize`/policy service or from a WAF?
3. Check the user's internal ID, issuer-scoped identity, tenant membership, and resource action.
4. If the user lacks permission, 403 is **correct**, not an IdP outage.
5. Do not `permitAll()` `/admin` just to see 200; test cross-tenant access.

## 19. Security Pitfalls While Debugging

| Dangerous "Quick Fix" | Consequence | Proper Fix |
| --- | --- | --- |
| Disable OIDC `state` check | Login CSRF/session mix-up | Fix cookie/request repository |
| Skip PKCE/nonce validation | Code/token substitution | Fix verifier/nonce correlation |
| Disable JWT signature/`iss/aud` | Forged tokens or other clients accepted | Fix trust/JWKS/client config |
| Trust certificate inside raw SAML `KeyInfo` | Signature trust bypass | Trusted IdP registration keys |
| Skip `InResponseTo` | Replay/unsolicited login risk | Fix saved request/session |
| App-wide `csrf.disable()` | Business CSRF | Scope ACS exception, keep CSRF elsewhere |
| `SameSite=None` without `Secure` | Browser rejects cookie | HTTPS/Secure + CSRF review |
| NGINX logs `$request_uri` | Leaks code/ticket via URL query | Sanitized route category/status |
| Spring debugs raw `SAMLResponse` | Leaks NameID/groups/PII | Staging fixtures, redacted reason |
| Leave production TRACE on permanently | Secrets/PII leakage + cost | Time-boxed debug/ACL/retention |
| Use `curl -k` | Disables TLS server authentication | Fix CA/hostname/cert |
| Trust browser-set `X-Request-ID` | Spoofing/correlation pollution | Generate at trusted edge |
| Redirect from raw `RelayState` | Open redirect/phishing | Bind saved request + allowlist |
| `permitAll()` all endpoints on loop | Authorization bypass | Fix filter/session/entrypoint |
| Use email as account key across IdPs | Account collision | issuer+subject→stable local account |
| Log raw CAS ST/OIDC code to correlate | Bearer secret replay/leak | Separate per-request/journey ID |

Note: **A sanitized HAR can still contain query `code/state/ticket`, form `SAMLResponse`, response bodies, or custom headers**. Inspect all contents before sharing; never blindly trust a "sanitized" label.

## 20. Check-Your-Understanding Questions and Answers

**1.** There are seven HTTP 302 responses in an OIDC flow. Is this a redirect loop?

**Answer:** You cannot conclude that from the 302 count alone. Check URL categories, callback, authentication outcome, session, and final resource; IdP MFA can also legitimately redirect multiple times.

**2.** Browser Network shows the OIDC callback but no `POST /token`. Did Spring fail to exchange the code?

**Answer:** Token exchange is server-to-server; browser DevTools normally will not show it. You need Spring/OP server-side logs/traces.

**3.** The SAML IdP returns a 200 page with no redirect. Did the IdP fail to send a Response?

**Answer:** Not necessarily. SAML HTTP-POST uses an auto-submitting HTML form. Check the ACS POST/Initiator/CSP/Console.

**4.** The SAML ACS receives a POST and returns 403. Can we conclude the signature is invalid?

**Answer:** No. `CsrfFilter` or a WAF may have blocked it beforehand. Check edge upstream status and Spring filter/authentication failure reason.

**5.** The browser did not send the cookie on the ACS POST even though it sent it when initiating SAML. Why?

**Answer:** SameSite cross-site POST, Secure/Domain/Path, or browser restrictions. Do not drop `InResponseTo` to "rescue" login.

**6.** The CAS callback has a `ticket`, but the browser never shows a ticket validation call. Why?

**Answer:** CAS ticket validation is sent from the Spring server to CAS on the back-channel.

**7.** Initial Kerberos returns 401 with `WWW-Authenticate: Negotiate`. Is that an error?

**Answer:** It can be a normal challenge. You must check whether the next request carries `Authorization: Negotiate` and check the GSS verification result.

**8.** Behind a proxy, the app generates an internal HTTP redirect URI; should we configure the IdP to allow that URI?

**Answer:** No. Fix the public HTTPS canonical URL and trusted forwarded headers, ClientRegistration/ACS/service config.

**9.** Authentication succeeds, yet `/tenant/b` returns 403 for a tenant A user. Is that valid?

**Answer:** It may be correct authorization. Do not treat every 403 as an SSO login failure.

**10.** Can a sanitized HAR be sent directly to a vendor/partner?

**Answer:** You must inspect query/POST body/tokens/PII and redact them; default sanitization is not an absolute safety guarantee.

**11.** Does a proxy request ID automatically carry across IdP redirects?

**Answer:** No. The browser creates new requests to different origins. To link the journey, use controlled server-side transaction correlation/IdP audit IDs.

**12.** Why can a custom authentication success handler cause "logged in, then landed on a strange page"?

**Answer:** If `SavedRequestAwareAuthenticationSuccessHandler` behavior is replaced, the original requested URL is no longer restored, even though authentication passed.

## 21. Checklist for Closing an SSO Ticket

- [ ] Expected protocol and registrationId/issuer/tenant identified, not guessed from username/email.
- [ ] UTC timeline recorded from initial protected request through callback, back-channel, session, and final resource.
- [ ] Actor identified for each status: browser, proxy, IdP, Spring filter, OP token/CAS validator, business service.
- [ ] Preserve log enabled and SAML HTML auto-submit/POST observed, not just HTTP 302.
- [ ] SPNEGO 401 Negotiate challenge not treated as an error if handshake steps follow.
- [ ] OIDC state/PKCE/nonce/redirect_uri and JWT iss/aud/signature/time verified.
- [ ] OAuth2 token endpoint/JWKS/UserInfo back-channel checked via server logs/traces.
- [ ] SAML signature/issuer/audience/destination/recipient/InResponseTo/time/replay verified.
- [ ] CAS service URL, single-use ST, and server ticket validation checked.
- [ ] Reverse proxy canonical HTTPS host/path/Forwarded configured properly; spoofed headers blocked.
- [ ] Callback/ACS matches the right Spring SecurityFilterChain, not captured by an API-only chain.
- [ ] Cookie Set-Cookie/Cookie presence and Secure/HttpOnly/SameSite/Domain/Path checked, without logging values.
- [ ] Session store Redis/JDBC/multiple pods saves/reads properly; session fixation rotation understood.
- [ ] SavedRequest/success/failure handler behavior checked, no open redirects/redirect loops.
- [ ] Authenticated user mapping uses issuer+stable subject; business tenant authorization independent.
- [ ] HTTP 401/403/413/502/504 pinpointed to the right layer, not all blamed on the IdP.
- [ ] TRACE/DEBUG approved/timeboxed, logs and HAR redacted, free of credential artifacts.
- [ ] Staging tests cover invalid state, wrong PKCE, invalid issuer/audience, SAML signature/recipient, CAS service, SPNEGO SPN, missing cookie, proxy loop, and multi-pod.
- [ ] Synthetic Java test or automated diagnostic regression test exists without relying on raw user tokens.
- [ ] First failed stage + last known-good step + owner + sanitized evidence ID + remediation + regression pass documented.
- [ ] After fixing, tested that the user **accesses the authorized resource properly**, not just seeing a 200 login page.

**Conclusion:** Debugging SSO is investigating **a distributed state machine**, not counting redirects. OIDC token exchange happens on the server, SAML HTTP-POST returns via a form rather than necessarily a 302, CAS service tickets are validated on the back-channel, and SPNEGO 401 can be completely normal. A reliable methodology connects the browser timeline, edge upstream status, Spring filter/provider outcomes, session continuity, and business authorization **without disabling state/PKCE/signature/tenant checks and without leaking secrets**.

## 22. Official Documentation

1. [Spring Security – OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): default OAuth2 authorization/callback endpoints, token/UserInfo callbacks.
2. [Spring Security – OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): Authorization Code flow and redirect-uri.
3. [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): AuthnRequest, ACS, Browser Redirect/POST.
4. [Spring Security – SAML Response Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): OpenSAML signature/conditions.
5. [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): FilterChainProxy, filter order, DEBUG/TRACE logging.
6. [Spring Security – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF protection and scope exclusions.
7. [Spring Security – Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): saved request, session/context behavior.
8. [Spring Security – CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): CasAuthenticationFilter/provider, service-ticket validation.
9. [Spring Security Kerberos](https://docs.spring.io/spring-security-kerberos/reference/): SPNEGO negotiation.
10. [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing/log correlation.
11. [Chrome DevTools – Network Reference](https://developer.chrome.com/docs/devtools/network/reference): Preserve log, Initiator, HAR sanitized export.
12. [MDN – Redirections](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Redirections): 302/303/307/308 semantics.
13. [MDN – Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie): SameSite/Secure/HttpOnly.
14. [RFC 6749 – OAuth2](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code, state and token request.
15. [RFC 7636 – PKCE](https://www.rfc-editor.org/rfc/rfc7636): code_challenge/code_verifier.
16. [RFC 9700 – OAuth2 Security BCP](https://www.rfc-editor.org/rfc/rfc9700): redirect URI, mix-up and transaction security.
17. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, iss/aud/nonce.
18. [OASIS – SAML2 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): Redirect/POST and RelayState.
19. [OASIS – SAML2 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Request/Response, Assertion validation.
20. [RFC 4559 – SPNEGO HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): Negotiate challenge.
21. [RFC 7239 – Forwarded](https://www.rfc-editor.org/rfc/rfc7239): forwarded protocol/host trust boundaries.
22. [W3C – Trace Context](https://www.w3.org/TR/trace-context/): traceparent/tracestate.
23. [OWASP – Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session cookies/session fixation.
24. [OWASP – Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): secrets redaction and event logging.
25. [OWASP – SAML Security](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signing trust and validated SAML assertions.
