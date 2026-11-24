# The Browser's Role in SSO Redirects and Message Exchanges

## 1. Objectives and Scope

In Single Sign-On (SSO), the browser (or *user agent*) is the agent moving the user back and forth between the application and the identity system. It executes HTTP navigation, sends domain-appropriate cookies, renders login pages, and sometimes relays protocol messages. **The browser does not decide on its own whether the user is authenticated**: the application and the identity provider (IdP) must verify the corresponding evidence according to the protocol.

After this lesson, you will be able to:
- Explain why web SSO requires browser participation and distinguish the login session at the IdP from the session at the application.
- Read OIDC Authorization Code and SAML 2.0 Web Browser SSO redirect flows, identifying messages passing through the browser versus messages sent directly between servers.
- State the meaning of `state`, `nonce`, PKCE, `SAMLRequest`, `SAMLResponse`, `RelayState`, cookies, and callback endpoints.
- Analyze errors involving redirect URIs, SameSite cookies, callbacks, CORS, anti-forgery protection, and signature verification.
- Relate protocol flows to Spring Security's default endpoints in a Servlet application.

In this lesson, "application" can refer to an OAuth/OIDC Relying Party (RP) or a SAML Service Provider (SP). IdP can refer to an OpenID Provider (OP) in OIDC or a SAML Asserting Party in SAML. Example URLs use the illustrative `.example` domain.

## 2. Who Does What in an SSO Flow?

| Component | Primary responsibility | What must not be assumed |
| --- | --- | --- |
| User | Initiates access, enters credentials or confirms MFA/consent at the IdP | Seeing a "login successful" page does not mean the application created a session |
| Browser | Follows `Location` in 302/303, sends GET/POST, loads forms, attaches cookies per domain/SameSite rules, receives session cookies | The browser is not a trusted party to verify identity, signatures, or permissions |
| RP/SP Application | Initiates login request, retains correlation state, handles callback/ACS, verifies response, establishes local session | Never trust values merely because the callback arrived at the expected URL |
| IdP/OP | Authenticates the user, maintains the IdP session, and issues protocol responses | The IdP does not directly own the application's session cookie on another domain |
| Token endpoint / metadata / JWKS | Provides code-to-token exchange and keys/information for verification when applicable | Not all of these interactions must go through the browser |

SSO commonly occurs when a user already has an **IdP session** from application A and then visits application B. The browser navigates to the IdP and includes the IdP cookie in an eligible request; the IdP recognizes the existing session and can issue a response for B without prompting for a password again. B must still verify the response and create its own **B session**. SSO does not mean two applications share the same cookie.

## 3. Front-Channel, Back-Channel, and Trust Boundaries

**Front-channel** is the portion of the exchange passing *through the user agent*: redirecting to the IdP, returning to the callback, or auto-POSTing a SAML response form. Because the browser is in the path, URLs, forms, navigation history, extensions, and developer tools can observe part of the data. Even over HTTPS, values sent by the browser remain untrusted input to the RP/SP.

**Back-channel** is direct server-to-server communication in a server-side web architecture: for instance, Spring Security sending an authorization code to the OP's token endpoint over HTTPS to obtain tokens, or fetching metadata/JWKS from the provider. The browser does not intermediate that HTTP call. The terms front-channel/back-channel describe the **actual transport path**, not just the endpoint type: in a pure browser SPA, calling the token endpoint with JavaScript still originates from the browser.

| Purpose | Usually via browser | Usually server-to-server |
| --- | --- | --- |
| Opening the IdP login page | OIDC/SAML: top-level navigation | No |
| Returning OAuth/OIDC authorization code | OIDC: callback via query in top-level redirect | RP server exchanges code at token endpoint in server-side architecture |
| Returning SAML evidence | SAML POST binding: form with `SAMLResponse` to ACS; Redirect binding often used for `AuthnRequest` | SAML Artifact binding may use back-channel to resolve the artifact if configured |
| Verifying identity/establishing session | Browser carries request and receives cookie | RP/SP performs verification and makes the authentication decision |
| Calling business APIs | Browser may call depending on architecture | Backend may call APIs using an access token |

**Key rule:** a redirect only sends the user to a new URL; it does not directly exchange tokens between the application backend and the IdP backend. When the server returns `302 Location: https://idp.example/...`, the browser is the party that creates the next HTTP request to the IdP.

## 4. HTTP Operations the Browser Actually Performs

1. **Top-level navigation:** after `HTTP 302 Found` or `303 See Other`, the browser reads `Location` and navigates to the target address. The HTTP method when following a redirect depends on the status code and HTTP rules; login callbacks typically see GET. Do not assume every 307/308 turns POST into GET.
2. **Form submission:** the IdP can return HTML containing a form and an auto-submit script, causing the browser to POST to the SP's ACS. The `SAMLResponse` form field is transported data, not a "verification result" from the browser.
3. **Sending cookies by destination:** in requests to `idp.example`, the browser sends eligible IdP cookies; in requests to `app.example`, it sends eligible application cookies. The browser does not automatically send domain A's cookies to domain B.
4. **Receiving Set-Cookie and maintaining a session:** after authentication, the application can return a session cookie such as `JSESSIONID`; subsequent requests attach cookies per browser rules.
5. **Rendering UI:** the user normally enters passwords, passkeys, or MFA codes on the IdP's origin. Third-party applications do not need and should not collect IdP passwords to implement federation.

Abbreviated exchange example (not the full flow):

~~~http
GET /private HTTP/1.1
Host: app.example

HTTP/1.1 302 Found
Location: /oauth2/authorization/corp

GET /oauth2/authorization/corp HTTP/1.1
Host: app.example

HTTP/1.1 302 Found
Location: https://idp.example/authorize?response_type=code&client_id=corp-web&state=XYZ...
~~~

The `Location` header is a navigation instruction; the subsequent request is a **new HTTP request sent by the browser**. URLs containing `...` here only illustrate the shape, not real reachable URLs.

## 5. OIDC Authorization Code Flow Through the Browser

Consider Spring Security MVC/Servlet running at `https://app.example`, logging in via OP `https://idp.example` with registration ID `corp`.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as RP (Spring Security)
    participant I as IdP / OP
    B->>R: GET /private
    R-->>B: 302 to login / oauth2 authorization
    B->>R: GET /oauth2/authorization/corp
    R-->>B: 302 to OP /authorize (state, PKCE...)
    B->>I: GET /authorize
    I-->>B: Login page or reuse existing IdP session
    B->>I: Login/MFA if needed
    I-->>B: 302 to RP callback (code, state)
    B->>R: GET /login/oauth2/code/corp?code=...&state=...
    R->>I: POST /token (code, client authentication/PKCE)
    I-->>R: Token response (ID token, access token...)
    R->>R: Verify result and create Authentication/session
    R-->>B: Session Set-Cookie; redirect to /private
    B->>R: GET /private with RP cookie
~~~

Steps to understand accurately:

1. **Detecting unauthenticated access:** the browser requests a protected resource. Spring Security's `AuthorizationFilter` and exception/login handling direct the user to the login page or straight to the OIDC initiation endpoint depending on configuration.
2. **Building the authorization request:** Spring Security handles `/oauth2/authorization/corp`, selects the `ClientRegistration`, and builds the URL to the OP authorization endpoint. It typically includes `response_type=code`, `client_id`, `scope=openid`, `redirect_uri`, `state`; `nonce` is used per OIDC requirements/mechanisms, and PKCE includes `code_challenge` when enabled/applicable.
3. **Browser moves to IdP:** the OP decides independently whether login/MFA is required. The IdP's cookie determines whether the user already has a session at the IdP; this cookie is distinct from the RP's cookie.
4. **IdP returns to application:** the OP returns a redirect to the registered callback URI, typically `/login/oauth2/code/corp?code=...&state=...`. The browser carries the **authorization code**; do not infer solely from the code that the user is logged in.
5. **RP processes the callback:** Spring Security matches `state` against the stored request and exchanges the code at the token endpoint via a server-side HTTP call, using client authentication and/or PKCE depending on client type and configuration. For OIDC, the RP verifies the ID token and related constraints before accepting the principal. Then the RP creates an `Authentication`, usually stores it in the HTTP session, and redirects to the original URL.
6. **Reaching the original resource:** the browser receives and resends the RP's cookie; Spring Security relies on the RP session for subsequent requests without forcing the IdP onto every page load.

Distinguish three easily confused items: an **authorization code** is a short-lived one-time code to exchange for tokens; an **ID token** describes the authentication event/user for the RP; an **access token** is used to access authorized resources. An ID token is not a "replacement password," and an access token should not by default be used as proof of login merely because it is signed.

In the **server-side RP/BFF** architecture above, the ID token and access token travel from the token endpoint to the RP server and need not be exposed in browser callback URLs. In a **SPA public client**, JavaScript may directly use Authorization Code + PKCE and make the token request; in that case, token protection must be designed for browser threats. Do not equate the two architectures.

## 6. Roles of state, nonce, and PKCE Along the OIDC Path

| Data | Who creates / who verifies? | Problem solved |
| --- | --- | --- |
| `state` | Client/RP creates and stores bound to the browser transaction; returned on callback and compared by RP | Correlates callback with the initiated request; helps prevent login CSRF |
| `nonce` | RP creates per OIDC flow; OP embeds in ID token; RP verifies in context | Binds the ID token to the request and reduces token replay/injection risk |
| PKCE `code_verifier` / `code_challenge` | Client keeps verifier, sends challenge on authorization request and verifier when exchanging code | Reduces the ability of a code thief to exchange the code for tokens; critically important for public clients |
| `redirect_uri` | RP registers and OP matches strictly per standard policy | Restricts where the OP returns the code, preventing codes from being redirected to arbitrary destinations |
| `iss`, `aud`, `exp`, ID token signature | OP issues, RP verifies | Controls issuing source, intended recipient, lifetime, and integrity |

`state` is **not** an identity token and must never grant access simply by being present. `nonce` does not replace signature, issuer, and audience verification. PKCE does not replace user authentication. When an RP integrates with multiple OPs, prevent *authorization server mix-up* through issuer identification / separate callback handling.

For example, a callback with a mismatched `state` must be rejected, even if the URL looks right and `code` is syntactically valid. The browser cannot verify these values on the RP's behalf.

## 7. SAML 2.0 Web Browser SSO Flow

SAML 2.0 commonly uses **HTTP-Redirect binding** to send `AuthnRequest` from the SP to the IdP and **HTTP-POST binding** to send `SAMLResponse` from the IdP back to the Assertion Consumer Service (ACS). Actual bindings can vary by configuration; this is the typical SP-initiated SSO case.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as SP (Spring Security)
    participant I as SAML IdP
    B->>S: GET /private
    S-->>B: Initiate SAML login
    B->>S: GET /saml2/authenticate/corp
    S-->>B: Redirect to IdP?SAMLRequest=...&RelayState=...
    B->>I: GET IdP SSO carrying AuthnRequest
    I-->>B: Login/MFA or use IdP session
    I-->>B: HTML form containing SAMLResponse, RelayState
    B->>S: POST /login/saml2/sso/corp (form)
    S->>S: Verify SAML and request correlation
    S-->>B: SP session cookie; redirect to resource
    B->>S: GET /private with SP cookie
~~~

**Stage by stage:**

1. The SP creates a `<saml2:AuthnRequest>` with an ID and required fields and sends it to the IdP via the browser; with Redirect binding, it is typically DEFLATE-compressed, Base64-encoded, and URL-encoded into the `SAMLRequest` query parameter. Accompanying signatures depend on configuration; Base64 encoding alone does **not** make content confidential or trustworthy.
2. The IdP processes the request, authenticates the user or uses an existing SSO session, and issues a `SAMLResponse` containing one or more assertions per policy.
3. With POST binding, the IdP returns an HTML page with a form; the browser submits the form to the SP's ACS. The form contains `SAMLResponse` and optionally `RelayState`. **The browser transports encoded XML; the browser does not verify the assertion's signature.**
4. Spring Security at the ACS decodes/parses the response and verifies the signature against trusted keys, issuer, audience, destination/recipient, validity timestamps, SubjectConfirmation conditions, `InResponseTo` correlation where appropriate, and replay protection. Only after successful verification does it create `Saml2Authentication`/the SP session.
5. `RelayState` helps correlate the flow/return to the target page, but must not be used as an unvalidated open redirect URL. Validity of `RelayState` alone does not prove authenticity of `SAMLResponse`.

Illustration of a form the browser might receive (response value abbreviated; not a real assertion):

~~~html
<form method="post" action="https://app.example/login/saml2/sso/corp">
  <input type="hidden" name="SAMLResponse" value="BASE64_ENCODED_SAML_RESPONSE">
  <input type="hidden" name="RelayState" value="CORRELATION_VALUE">
  <button type="submit">Continue</button>
</form>
~~~

In practice, the IdP usually uses JavaScript to auto-submit the form, but the protocol mechanism is a POST from the browser to the ACS. Because the form comes from the IdP and the browser merely forwards it, the SP must verify the response server-side. SAML Responses often contain identifiers or personal attributes; **Base64 is not security encryption**, so never write raw responses to public logs.

**IdP-initiated SSO:** the browser may start at the IdP page and POST a response that does not correspond to an SP AuthnRequest. A dedicated policy is needed to accept/reject unsolicited responses and mitigate login CSRF risks; do not assume SP-initiated and IdP-initiated have the same level of correlation.

**SAML Artifact binding:** the browser may carry only a short reference artifact; the SP then contacts the IdP directly to retrieve the message. This shows that "the entire SAML assertion always passes through the browser" does not hold for every binding.

## 8. Comparing Browser Footprints in OIDC and SAML

| Criterion | OIDC Authorization Code (server-side RP) | SAML Web Browser SSO (Redirect + POST) |
| --- | --- | --- |
| Request to IdP | Authorization request in URL/redirect | AuthnRequest encoded in `SAMLRequest` |
| Response passing through browser | `code` and `state` in GET callback | `SAMLResponse` and `RelayState` via form POST |
| Evidence used by RP/SP | ID token from token endpoint, after verification | SAML assertion/response at ACS, after verification |
| Typical direct server communication | Exchanging code for tokens, metadata/JWKS | Metadata/certificates; artifact resolution with artifact binding |
| Anti-forgery/correlation | `state`, `nonce`, PKCE by role | Request ID/`InResponseTo`, `RelayState`, and replay protection |
| Sensitive cookie case | Cross-site GET callback and RP session | ACS callback is typically a cross-site POST |
| Common Spring Security endpoints | `/oauth2/authorization/{registrationId}` and `/login/oauth2/code/{registrationId}` | `/saml2/authenticate/{registrationId}` and `/login/saml2/sso/{registrationId}` |

Commonality: the user experiences "single sign-on" thanks to the IdP session, yet each SP/RP remains responsible for verifying the message and establishing its own session.

## 9. Cookies, SameSite, and Browser-Imposed Constraints

Cookies are the link where cross-domain navigation directly affects SSO success. Distinguish:
- **IdP cookie:** sent by the browser on eligible requests to the IdP domain. It allows the IdP to reuse an SSO session.
- **RP/SP cookie:** sent by the browser on eligible requests to the application, holding authorization request/SAML request state and the post-login session.
- **Cookies are not automatically shared across domains:** two systems recognizing the same person still maintain separate sessions and cookies.

Important attributes:
- `Secure`: cookie is sent only over HTTPS (local exceptions depend on the browser); enable in real environments.
- `HttpOnly`: JavaScript cannot read the cookie, reducing script-based cookie theft, though it does not by itself prevent all XSS/CSRF.
- `Domain`, `Path`: restrict where the browser sends the cookie; host-only cookies are tighter when subdomain sharing is unnecessary.
- `SameSite=Strict`: never sent on cross-site requests, easily breaking login correlation across redirects.
- `SameSite=Lax`: allows cookies on top-level navigations from other sites **when the HTTP method is safe such as GET**; do not rely on Lax for cross-site POST.
- `SameSite=None; Secure`: allows sending cookies on many cross-site requests, but widens the CSRF surface that must be controlled; also subject to browser cookie-blocking policies.

**Common scenario:** the SP stores `AuthnRequest` in the HTTP session, yet the IdP POSTs `SAMLResponse` to the ACS in a cross-site request. If the browser omits the SP session cookie due to `SameSite=Lax`, the SP cannot find the saved request and reports a correlation error. The fix must rely on evaluated session/response-repository design and cookie policy (for example, configuring `SameSite=None; Secure` for the appropriate cookie or using another correlation storage mechanism); never disable `InResponseTo` verification to "fix" the error.

Some browsers have temporary exceptions when a cookie has **no SameSite declared**; do not rely on such exceptions as a stable design. Iframes, silent logins, or embedded IdPs also face third-party cookie restrictions unlike top-level navigation; an iframe failure does not mean redirect-based SSO is broken overall.

## 10. Boundaries of Navigation, Form POST, CORS, and CSRF

**Top-level navigation vs. `fetch()`:** the browser navigating from `app.example` to `idp.example` via `Location` does not behave like an XHR/fetch reading cross-origin data. CORS primarily governs JavaScript reading cross-origin responses; adding CORS headers usually **cannot fix** a SAML callback missing its session or a redirect URI mismatch. If a SPA actively calls the token endpoint via `fetch()`, CORS on that endpoint becomes a real constraint.

**SAML POST vs. business data form submission:** the ACS receives a POST from the IdP, so a generic CSRF rule requiring an application token could block the request before SAML processes it. Spring Security/SAML must configure appropriate handling for the exact ACS alongside signature, correlation, and replay checks. Never disable CSRF across the entire application just to allow the ACS.

**Never trust browser data:** query parameters, fragments, form bodies, cookies, and `Referer` can be missing or altered. HTTPS protects data in transit but **does not** guarantee a callback originated from the expected transaction. The backend must correlate and verify on its own.

**URLs and history:** codes/values appearing in query strings can end up in browser history, proxy logs, monitoring, or leak via other mechanisms if misconfigured. Minimize sensitive codes in URLs, keep long-lived tokens out of query strings, prevent open redirects, restrict referrers, and avoid logging raw callbacks containing codes unnecessarily.

## 11. Where Does Spring Security See This Flow?

For the Servlet stack, default endpoints help map the Network tab to the filter chain:

| Action | Common endpoint | Handling component |
| --- | --- | --- |
| Initiate OIDC/OAuth2 login | `GET /oauth2/authorization/corp` | `OAuth2AuthorizationRequestRedirectFilter` builds authorization request, redirects to OP |
| Receive authorization code | `GET /login/oauth2/code/corp?code=...&state=...` | `OAuth2LoginAuthenticationFilter` processes callback |
| Initiate SAML AuthnRequest | `GET /saml2/authenticate/corp` | `Saml2WebSsoAuthenticationRequestFilter` |
| Receive SAML Response | `POST /login/saml2/sso/corp` | `Saml2WebSsoAuthenticationFilter` and authentication provider |

Example **Spring Security Java (Servlet) configuration illustrating OAuth2/OIDC** in a Spring Boot project with `spring-boot-starter-security`, `spring-boot-starter-oauth2-client`, and a valid `ClientRegistration`. This is a project configuration class, **not a standalone Java program run with `javac SecurityConfig.java`**:

~~~java
package com.example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

- `anyRequest().authenticated()` causes unauthenticated access to trigger the login mechanism.
- `oauth2Login(...)` adds the Authorization Code flow, initiation endpoint, and callback per `ClientRegistration`.
- `ClientRegistration` must specify the right issuer/authorization endpoint, token endpoint, client ID, redirect URI, and scope; OIDC requires the `openid` scope. PKCE usage also depends on client type and corresponding configuration.
- There is no fixed stdout for the class above: the output is the HTTP response sequence when the application runs and connects to a valid OP.

If the application chooses SAML 2.0, replace the login mechanism with `.saml2Login(Customizer.withDefaults())` in a corresponding configuration and provide `RelyingPartyRegistration`, IdP metadata/certificates, and the SAML 2.0 Service Provider dependency. Never enable SAML with a hand-rolled redirect alone: verifying the response, signature, timestamps, audience, and ACS is the critical security core.

Two *illustrative* HTTP snippets, not proof of successful login:

~~~http
HTTP/1.1 302 Found
Location: https://idp.example/authorize?response_type=code&state=...&client_id=...

HTTP/1.1 302 Found
Location: https://app.example/login/oauth2/code/corp?code=...&state=...
~~~

Every callback URI generated behind a reverse proxy/TLS termination must match the URI registered at the IdP; mismatched `http`/`https` scheme, host, or port can cause the IdP to reject the request or send the browser to the wrong place.

## 12. What Happens When the Browser Goes Off Track?

| Symptom in browser / server | Possibility to check | Verification direction |
| --- | --- | --- |
| Redirect loop between app and IdP | RP cookie not saved/sent, login session missing, wrong proxy URL | Inspect 302 chain, `Set-Cookie` and `Cookie` request headers, scheme/host/port |
| OP returns "invalid redirect_uri" | Registered callback does not match sent URI | Compare exact URIs; check proxy forwarded headers configuration |
| OIDC callback reports "invalid state" | Browser lost session, multiple tabs/race, altered state, wrong request storage | Compare sent/received state and authorization request storage; never skip check |
| Token endpoint rejects `invalid_grant` | Code expired/used, wrong PKCE verifier, mismatched redirect URI | Check sanitized server logs and token request; do not log secrets |
| SAML ACS reports missing AuthnRequest/InResponseTo | Session cookie missing on cross-site POST; request repository cannot find it | Check SameSite, ACS POST, SP cookie, and correlation data |
| SAML reports invalid signature/audience/recipient | Wrong IdP metadata/cert, wrong ACS URL, invalid response | Check issuer, certificate, entity ID, ACS, timestamps, and signature |
| Browser stalls at IdP even after login | No redirect/form returned; broken or blocked callback URL | Network tab: after IdP login, is there a 302 or HTML form POST? |
| SSO works in a new tab but fails in an iframe | Browser restricts third-party cookies/embedded context | Test top-level redirect; verify embedded login mechanism |
| 403 error at ACS | CSRF rule, request matcher, or security filter blocking POST | Confirm endpoint/method then review scoped protection config |
| API fetch reports CORS | Frontend is making cross-origin JS calls | Distinguish fetch from top-level login; fix CORS on the exact called endpoint |

Never "fix" errors by removing SAML signature validation, skipping `state` matching, allowing arbitrary redirect URIs, or disabling CSRF system-wide. Such changes can turn an operational issue into an authentication vulnerability.

## 13. Reading the Flow in Developer Tools

Practice in a test environment with dedicated accounts and an IdP you are authorized to test:

1. Open the **Network** tab, enable **Preserve log**, and filter by **Document** (viewing other requests when needed). Disable cache if you want a clean trace.
2. Access a protected URL while unauthenticated. Record the initial URL, 302/303 statuses, `Location`, request methods, and origins at each step.
3. Identify whether the request to the IdP is `/authorize` (OIDC) or a URL with `SAMLRequest` (SAML). Check for corresponding `state`/`RelayState` without copying raw values verbatim.
4. After login, identify the callback: OIDC is typically a GET to `/login/oauth2/code/...` with `code`; SAML is typically a POST to `/login/saml2/sso/...` with form field `SAMLResponse`.
5. Check whether the RP/SP cookie was sent on the callback and subsequent request; pay close attention to `SameSite`, `Secure`, `Domain`, and cookie-blocked warnings.
6. Check whether the post-callback step redirects to the original page. If the callback fails, distinguish browser failure to send the request/cookie from server rejection during message verification.
7. Sketch a minimal diagram `Browser → App → IdP → Browser → App`; clearly mark that the server calling the token endpoint in OIDC is a separate branch, usually **not visible in the browser's Network tab**.

**Security note when debugging:** never export/share full HAR files containing cookies, authorization codes, SAML assertions, access tokens, or personal data. When sharing evidence, redact URL queries, bodies, cookies, and sensitive headers while preserving method, path, status, domain, and chronological order.

## 14. Real-World Scenario: Why Can "Already Logged In at IdP" Still Fail to Enter the App?

Suppose the browser already has an IdP cookie and visits the SP. The IdP recognizes the user and returns a SAMLResponse to the ACS. The browser submits the POST without attaching the SP session cookie due to SameSite. Because the SP stored AuthnRequest in that session, the SP cannot find the original transaction to match `InResponseTo` and rejects it. **The IdP authenticated successfully, yet the SP still cannot trust the response.**

How to analyze:
- Is there a SAML response from the IdP? If yes, the IdP login stage completed.
- Does the form POST to the exact ACS? If not, check URL/binding.
- Is the SP cookie present in the POST request? If not, inspect SameSite/Domain/Secure and browser policy.
- Can the SP correlate the request ID and verify the assertion signature? If not, fix state storage or protocol configuration without skipping checks.
- Once valid, the SP issues its own session and redirects the user to the resource.

Switching to OIDC Authorization Code may turn the callback into a top-level GET, so a `SameSite=Lax` cookie is normally sent when conditions match. **That is an HTTP path difference**, not proof that OIDC is always more secure than SAML or that every SAML setup needs `SameSite=None`. Specific architecture and configuration decide.

## 15. Common Conceptual Misconceptions

1. **"302 means the app backend called the IdP."** False: the server produces the response; the browser follows `Location` and creates a new request.
2. **"The browser knows the ID token/SAML Response, so it authenticates on its own."** False: the RP/SP server must verify it. The browser only transports/renders; SPAs must handle tokens according to their own architecture.
3. **"Successful IdP login means every application is logged in."** False: each application establishes its own session and access permissions after accepting the response.
4. **"A Base64 SAMLResponse is encrypted."** False: Base64 is only encoding; HTTPS, signatures, and proper assertion protection are required.
5. **"`state` or `RelayState` is an identity signature."** False: they serve correlation/state restoration; separate protocol verification is required.
6. **"CORS causes all cross-domain login errors."** False: CORS for fetch/XHR is different from top-level navigation and form POST.
7. **"SameSite=Lax cookies behave identically for cross-site GET and POST."** False: cross-site POST requests normally do not receive Lax cookies; do not depend on short-term browser exceptions.
8. **"App logout automatically logs out the IdP and other apps."** False: local logout and Single Logout / OIDC logout are separate flows depending on protocol and integration.
9. **"Just seeing the callback URL means it is valid."** False: must verify state/PKCE/nonce in OIDC or signature/correlation/timestamps/audience in SAML; prevent replay and open redirects.
10. **"All tokens are exchanged in the browser."** False in server-side RP OIDC Code; the token endpoint is back-channel. However, SPAs handle it differently, so always identify the client type.

## 16. Self-Check Exercises

**Exercise 1.** In the Network tab you see `GET /login/oauth2/code/corp?code=...&state=...`; you do not see a `POST /token` request. Is the token exchange step missing?  
**Suggested answer:** inconclusive. If the RP is a Spring Security Servlet app, the token request is typically sent by the RP backend to the OP, outside the browser's Network tab. Check secret-redacted backend logs/traces.

**Exercise 2.** The browser POSTs `SAMLResponse` to the ACS, yet the server reports `AuthnRequest` not found. List three things to check.  
**Suggested answer:** (1) SP session cookie in the POST and SameSite, (2) ACS endpoint/registrationId and request repository, (3) `InResponseTo`/`RelayState` relationship and stored request ID. Do not disable matching just to make it pass.

**Exercise 3.** A user logs into app A, visits app B without re-entering a password, yet still receives a new cookie from B. Why?  
**Suggested answer:** The IdP reuses the user's session when the browser navigates to it; B verifies the federated response and creates a local session. Cookies for A, B, and the IdP have separate scopes.

**Exercise 4.** An OIDC callback carries a valid authorization code, but `state` differs from the stored value. Should the token endpoint be called?  
**Suggested answer:** no. The transaction must be rejected due to correlation state mismatch to avoid accepting a response that did not originate from the initiated browser flow.

## 17. Key Takeaways for Practice

The browser is the **front-channel navigation and message-relay medium**; the IdP is where the user authenticates; the RP/SP is where **evidence is verified and the application session is created**. To troubleshoot an SSO error, identify the three paths accurately: (1) browser to IdP, (2) browser back to callback/ACS, (3) direct server-to-server exchange if used by the protocol/architecture. Then inspect request correlation, cookies, signatures/tokens, and endpoints on the right path.

### Technical References for Cross-Checking
- Spring Security — OAuth 2.0 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Producing SAML AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- OpenID Connect Core — Authorization Code Flow: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700
- MDN — Set-Cookie / SameSite: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
