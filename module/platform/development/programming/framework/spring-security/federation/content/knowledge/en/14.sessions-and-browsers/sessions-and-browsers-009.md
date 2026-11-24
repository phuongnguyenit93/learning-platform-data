# Third-Party Cookie Restrictions and Their Impact on Browser-Based Login and Logout

In **Spring Security federation**, the browser acts as the transport intermediary between the **Service Provider (SP/Relying Party)** application and the **Identity Provider (IdP/Asserting Party)**. The browser also holds session cookies for each website. Consequently, a SAML 2.0 flow with completely valid signatures and IdP configuration can still fail merely because **cookies are omitted on the return leg**, or **an iframe is blocked from reading/writing the embedded website's cookies**.

This lesson clarifies two mechanisms that are often conflated:

1. **Third-party cookie blocking/partitioning:** the browser restricts a website's cookies when that site appears **as an embedded component** inside another website—for example, an IdP running inside an SP's iframe or an SP receiving logout messages inside an IdP's iframe.
2. **`SameSite`:** a per-cookie attribute governing when a cookie is sent based on the request's *same-site/cross-site* nature. A **cross-site top-level POST** from the IdP to the SAML Assertion Consumer Service (**ACS**) can withhold `SameSite=Lax` cookies even when the request is not inside an iframe.

**Key takeaway:** setting `SameSite=None; Secure` can allow session cookies to accompany a valid **cross-site POST**, yet **does not bypass third-party cookie blocking policies** in Safari, Firefox, or Chrome protection modes. Sustainable designs prioritize **top-level redirects** for login, preserve secure request/session correlation, and never rely on hidden iframes to claim Single Logout succeeded.

## 1. Concepts: Origin, Site, First-Party, and Third-Party

Suppose two parties integrate:

~~~text
SP Portal:
https://portal.example.com

IdP:
https://login.partner-b.example

SP's ACS:
https://portal.example.com/login/saml2/sso/partner-b

SP's SAML2 start:
https://portal.example.com/saml2/authenticate/partner-b

SP's SAML2 SLO:
https://portal.example.com/logout/saml2/slo
~~~

The `.example` domains are illustrative placeholders and cannot serve as production IdP/SP endpoints.

| Concept | Explanation | Easily Confused With |
| --- | --- | --- |
| **Origin** | Scheme + hostname + port; e.g., `https://portal.example.com:443` | *Site* does not necessarily match origin |
| **Site** | Typically based on scheme + registrable domain (schemeful site) | Not synonymous with full hostname |
| **First-party/top-level context** | Website currently in the tab/window's top-level context | Does not mean every request from that page is same-site |
| **Third-party/embedded context** | Another site embedded inside a top-level page, e.g., `iframe src=https://idp.example` | Not every cross-site redirect is an iframe |
| **Session cookie** | Cookie referencing HTTP session state, e.g., `JSESSIONID` or `SESSION` | Not a SAML Assertion or `RelayState` |
| **`SameSite`** | Instructs the browser whether to send a cookie on same-site/cross-site requests | Not CORS, and not a SAML signature |
| **Third-party cookie blocking** | Browser privacy policy restricting cookies in third-party contexts | Cannot be fixed completely by `SameSite=None` alone |
| **Storage partitioning** | Separates cookies/storage per *top-level site* | Does not maintain one global IdP session across embedded sites |
| **`HttpOnly`** | Page JavaScript cannot read the cookie | Does not stop the browser from sending the cookie on HTTP requests |
| **`Secure`** | Cookie sent only over HTTPS (with localhost exceptions in some browsers) | Does not replace proper TLS at the reverse proxy |

### Same-Origin and Same-Site Are Not the Same

For example, `https://app.company.example` and `https://idp.company.example` are **cross-origin** due to different hostnames, yet usually **same-site** because they share a registrable domain and HTTPS scheme. Even on a same-site request, a **host-only** cookie set by `app.company.example` is **not** sent to `idp.company.example` merely because they are same-site. Cookies remain bounded by `Domain`, `Path`, `Secure`, and storage state.

Conversely, `https://portal.example.com` to `https://login.partner-b.example` is clearly **cross-site**; `SameSite=Lax/Strict/None` directly affects requests returning to the SP.

**Do not treat two domains being owned by the same enterprise as proof they are same-site.** Browsers apply domain/scheme rules, not corporate contracts.

## 2. Where Does SAML Web Browser SSO Use Cookies?

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as SP Portal
    participant IdP as IdP B
    B->>SP: GET /reports
    SP-->>B: Set-Cookie JSESSIONID (pre-SSO state)
    SP-->>B: Redirect to /saml2/authenticate/partner-b
    B->>SP: GET /saml2/authenticate/partner-b
    SP->>SP: Create AuthnRequest, store ID/RelayState in session
    SP-->>B: Redirect/POST AuthnRequest to IdP
    B->>IdP: Request to IdP, using IdP cookie per context
    IdP->>IdP: Authenticate or reuse existing IdP session
    IdP-->>B: Form POST SAMLResponse
    B->>SP: POST /login/saml2/sso/partner-b
    SP->>SP: Restore session + AuthnRequest, validate SAMLResponse
    SP-->>B: Authentication success or error
~~~

There are two **distinct** sets of cookies:

- **SP cookie:** lets Spring retrieve the right `HttpSession`/`SecurityContext` and `AuthnRequest` saved before visiting the IdP.
- **IdP cookie:** lets the IdP recognize the user has an existing session and issue SSO without prompting for a password again.

A missing IdP cookie leads to **re-logging in at the IdP** or failing silent SSO. A missing SP cookie when **POSTing `SAMLResponse` to the ACS** prevents Spring from finding the old `AuthnRequest`, causing `RelayState`/`InResponseTo` mismatches or creating a new session instead of the original one.

Both failures look like "SAML login failed", yet require different fixes. Never extend Assertion lifetimes or disable `InResponseTo` checks to mask cookie bugs.

## 3. Confusing Scenario: Top-Level Redirect Differs from Embedded Iframe

Separate four distinct scenarios:

| Browser Context | Example | Does `SameSite=Lax` send SP cookie? | How does third-party blocking apply? |
| --- | --- | --- | --- |
| **Same-site request** to SP | `GET /reports` while user is on SP | Usually yes, if Domain/Path/Secure match | Not a third-party context |
| **Cross-site top-level GET** to SP | IdP redirects browser to an SP GET URL | **Yes** with normal Lax | Browser navigated top-level to SP; differs from iframe |
| **Cross-site top-level POST** to ACS | IdP returns a form POSTing SAMLResponse to SP | **No** with explicit `SameSite=Lax` | Primary issue is usually SameSite; do not equate with iframe third-party blocking |
| **Cross-site iframe** loading SP | IdP page embeds an `iframe` to SP SLO | **No** with Lax/Strict | `SameSite=None` can still be blocked/partitioned by browsers |
| **Cross-site iframe** loading IdP | SP embeds IdP for "silent login" | Lax IdP cookies omit on embedded requests | Privacy controls may block IdP cookies even with None |

**Key explanation:** `SameSite=Lax` permits cookies during cross-site navigation **at top-level using safe methods such as GET**. Under standard rules, it does **not** send cookies on cross-site `POST`. `SameSite=Strict` even withholds them on top-level cross-site GETs. `SameSite=None` permits sending cookies across cross-site requests when paired with `Secure` and unblocked by other policies.

Some Chromium browsers apply a temporary **Lax-allowing-unsafe** exception for cookies **omitting `SameSite`**, set within a very short window (often cited as roughly two minutes). **Never rely on this exception**: it does not apply to explicit `SameSite=Lax` on POSTs and varies across browsers, versions, and contexts.

### When Does POST ACS Still Work Despite `SameSite=Lax`?

To diagnose accurately, verify in practice: the app might not rely on restoring a prior session, IdP and SP might happen to be same-site, the browser might apply an exception to cookies omitting `SameSite`, or the request might use a different state strategy. Working on one developer machine **does not prove** cookie policy is right for all users. Always inspect the `Cookie` request header and real session/request correlation.

## 4. Comparing SameSite=Strict, Lax, and None for SAML

| Attribute | Top-level cross-site GET to SP | Top-level cross-site POST to SP | Third-party iframe | Recommendation |
| --- | --- | --- | --- | --- |
| `Strict` | Cookie not sent | Cookie not sent | Cookie not sent | Suits cookies needing strong isolation, but can break SAML browser flows |
| `Lax` | Usually sent | **No** with explicit Lax | No | Sensible for many ordinary sites; must test SAML POST callbacks |
| `None; Secure` | May be sent | May be sent | Only if browser/policy allows third-party context | Use only for cookies truly needing cross-site transport, with CSRF protection and HTTPS |
| `SameSite` omitted | Browser/default dependent | Varies, unstable | Browser/privacy dependent | Never rely on defaults or short-lived timing exceptions |

This is a **general rule model**, not a substitute for testing on real browsers/OSes. When `SameSite=None` omits `Secure`, modern browsers routinely **reject the cookie**. Setting `Secure` on a site running over plain HTTP also breaks cookies in non-HTTPS environments.

### Which Cookie Belongs to Which Policy?

Spring Boot Servlet typically issues `JSESSIONID` from the servlet container. With Spring Session, the session cookie may be `SESSION`. Reverse proxies/load balancers, SSO gateways, or upstreams may have separate cookies. Fixing only `JSESSIONID` while `SESSION` or the IdP cookie is blocked leaves the error unresolved.

**Do not confuse `Set-Cookie` on responses with `Cookie` on requests**:

~~~text
Response from SP:
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=None

Request returning to ACS:
Cookie: JSESSIONID=...
~~~

Verify both legs. Never paste real cookie values into tickets/chats/logs. A successful `Set-Cookie` does not prove the browser stored it, and storing it does not guarantee the browser is allowed to **send it back** in a cross-site context.

## 5. Why Does the SP Lose AuthnRequest When the IdP POSTs the Response?

Per Spring Security 7.x documentation, `Saml2WebSsoAuthenticationRequestFilter` creates `AuthnRequest` and saves it via `Saml2AuthenticationRequestRepository`. By default, `HttpSessionSaml2AuthenticationRequestRepository` stores the request in `HttpSession`. Upon receiving `SAMLResponse`, `Saml2WebSsoAuthenticationFilter`/`Saml2AuthenticationTokenConverter` must locate the saved request to handle correlation.

Before-and-after state example:

~~~text
Before going to IdP:
SP response Set-Cookie: JSESSIONID=sid-A; SameSite=Lax
SP HttpSession sid-A:
  AuthnRequest ID=_req-123
  RelayState=_state-abc
  registrationId=partner-b

IdP returns top-level POST to SP:
POST /login/saml2/sso/partner-b
Cookie: [no JSESSIONID due to SameSite=Lax]

SP sees HTTP request:
Cannot look up sid-A via cookie
May create session sid-B or find no request
InResponseTo=_req-123 has no matching request in sid-B

Outcome:
SSO fails or enters a retry/redirect loop
~~~

**A validly signed message is still insufficient** to prove the browser delivering it is the browser that initiated SP-initiated SSO. Losing request/session correlation is a key security signal, not merely a UX bug.

Never "fix" this by **dropping `InResponseTo`, disabling validators, or blindly accepting unsolicited SAMLResponses**. Those weaken defenses against login CSRF/login fixation.

## 6. Enabling Cross-Site POST Cookie Support in Spring Boot Servlet Only When Needed

With Spring Boot 3.x/4.x supporting the matching properties, configure `application.yml`:

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: none
~~~

Or `application.properties`:

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=none
~~~

**Effect:** instructs the servlet container or Spring Session (depending on version) to issue the session cookie with `SameSite=None; Secure; HttpOnly`, letting browsers send the cookie when the IdP executes a **cross-site top-level POST** to the ACS. Verify dependencies, runtime servlet container, custom session/cookie beans, and actual response headers. Spring Boot 3.3/3.5/4.0 officially document `server.servlet.session.cookie.same-site`; older releases or custom containers may behave differently.

**Do not treat this as the "best default config for every application".** `SameSite=None` exposes cookies on more cross-site requests than `Lax`, requiring full CSRF protection, endpoint separation, and narrow `Path`/`Domain` cookie scoping where design allows. Deploy only after threat modeling and real browser testing.

### Passing Through an HTTPS Reverse Proxy

If the browser connects to `https://portal.example.com` while the Spring container runs internally on `http://app:8080`, ensure:

- The public URL uses real HTTPS with properly configured TLS.
- Cookies needing cross-site delivery carry `Secure`.
- `Forwarded`/`X-Forwarded-*` headers are trusted only from verified proxies and stripped when sent directly by Internet clients.
- `Domain`, `Path`, context path, session cookie name, and multi-subdomain cases are checked.
- No duplicate `Set-Cookie` headers with the same name/path/domain yet differing SameSite values confuse the browser.
- Overly broad `Domain=.example.com` is not issued solely to "share login"; that expands subdomain takeover/session fixation risks.
- `HttpOnly` prevents JS from reading session cookies; CSRF tokens and CSP remain enforced per policy.

When using Spring Session's `SESSION` cookie, verify `CookieSerializer`/`DefaultCookieSerializer` or your version's mechanism applies the same attributes. Never read YAML alone and assume cookies are right.

## 7. Spring Security JavaConfig for SAML Login and Logout

Example **configuration inside a Spring Security Servlet project**, not standalone Java 17:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlBrowserSecurityConfig {

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

The code assumes `spring-security-saml2-service-provider` and a valid `RelyingPartyRegistrationRepository`, IdP metadata, certificates, and contract-aligned SLO support. It enables SAML2 flows; it **does not configure cookies by itself**. Cookies are written by Spring Boot/container/Spring Session and must align with `HttpSession` and `Saml2AuthenticationRequestRepository`.

**Never build a custom controller to decode Base64 `SAMLResponse` and mint sessions just to avoid SameSite.** Every login must still pass through the provider verifying signature, issuer, audience, recipient, NotBefore/NotOnOrAfter, request correlation, and anti-replay.

### If a Request Hits the Wrong SecurityFilterChain

An application with multiple filter chains can route `/login/saml2/sso/**` into a chain lacking SAML, yielding 404/302/403. Cookie diagnostics must run alongside filter-chain diagnostics; an ACS unmatched by the SAML filter can easily be misdiagnosed as a blocked cookie.

## 8. When You Must Store AuthnRequest Outside HttpSession

Spring Security provides `Saml2AuthenticationRequestRepository`, and modern documentation includes `CacheSaml2AuthenticationRequestRepository` to support storing AuthnRequests in a distributed cache when session cookies do not survive every hop. Bean example per current docs:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.web.authentication.CacheSaml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestRepository;

@Configuration
public class SamlRequestRepositoryConfiguration {

    @Bean
    Saml2AuthenticationRequestRepository<?> authenticationRequestRepository() {
        return new CacheSaml2AuthenticationRequestRepository();
    }
}
~~~

**Verify the exact package/API for your Spring Security version** before compiling and see how the app provides caching. This code merely configures a repository bean, not a self-securing cache workflow. Spring Security documentation stresses an important risk: if AuthnRequest lookup relies **solely on `InResponseTo` or `RelayState`** without binding to the initiating browser/session, an attacker can use their own transaction to trigger **login fixation** against a victim.

Therefore, when replacing the default repository, explicitly design:

1. Random, unpredictable state with sufficient entropy and a short lifetime.
2. Binding of the request to the browser/tab/session or an equivalent CSRF/login-fixation defense of comparable strength.
3. Exact storage of issuer/registration, AuthnRequest ID, relay state, and public ACS.
4. Full validation of `InResponseTo`, `Recipient`, `Destination`, `Audience`, signature, and timestamps as before.
5. Preventing reuse after login via atomic consume-once and anti-replay.
6. Purging expired state; avoiding state leaks in logs, referrers, analytics, or browser history.
7. Verifying whether multiple tabs starting two SSO flows cause state collisions.
8. If state is signed/encrypted or embeds a browser-bound secret, designing/testing against a concrete threat model.

**There is no "magic cache workaround"** for every browser blocking third-party cookies: it may rescue certain flows at the cost of the request-binding guarantee sessions previously gave. Prefer top-level login and proper sessions whenever feasible.

## 9. IdP Cookies in Embedded Logins / Iframes

A legacy approach to "silent login" embeds an iframe:

~~~html
<iframe src="https://login.partner-b.example/silent-sso"></iframe>
~~~

With top-level page `https://portal.example.com`, `login.partner-b.example` runs in a **third-party context**. Browsers restrict or partition the IdP's cookies under privacy settings. Even if the IdP cookie has `SameSite=None; Secure`, browsers can still:

- Omit the IdP cookie inside the iframe.
- Partition cookies by top-level site, failing to reuse an IdP session created in a separate tab.
- Block setting new cookies inside the iframe.
- Require the Storage Access API and user interaction in certain cases.
- Block frame embedding via `Content-Security-Policy: frame-ancestors` or `X-Frame-Options` even when cookies are not the issue.

**Consequence:** silent SSO misses the IdP session, the iframe shows an unusable login form, times out, or loops on redirects. This is not proof that the SAML signing certificate is wrong.

### Replacing Iframes with Top-Level Redirects Where Appropriate

Prefer the flow:

~~~text
Top-level browser on SP
  -> top-level navigation to IdP
  -> IdP uses its own first-party session cookie
  -> browser POSTs SAMLResponse to SP ACS
  -> SP verifies and establishes session
~~~

Top-level navigation lets the IdP operate in its own first-party context without relying on iframe cookies. However, **the return POST to the ACS still requires checking the SP's SameSite cookie** as covered earlier. Switching the UI to a redirect does not automatically solve all cookie/session correlation.

If the app is an SPA, never pass SAML XML assertions to frontend JavaScript to verify. Use a backend handling SAML at the ACS and issuing an origin-scoped app session, or a BFF (backend-for-frontend) keeping SAML verification on the server.

## 10. Third-Party Cookie Restrictions by Browser (Updated from Official Sources)

Each browser has different privacy defaults, exceptions, and storage mechanisms. Verify status by **actual version/OS/profile**; never build designs on a blanket premise like "all Chrome already blocked third-party cookies".

| Browser or Mode | Published Platform Information | Implications for SAML |
| --- | --- | --- |
| **Safari/WebKit** | WebKit enforces **full third-party cookie blocking** by default, offering the Storage Access API under specific conditions | IdP/SP iframes can lose cookies; top-level redirects are usually better |
| **Firefox** | **Total Cookie Protection** isolates third-party cookies/storage per top-level site alongside tracker protections | An IdP cookie inside SP A's iframe is not automatically shared with SP B's iframe |
| **Standard Chrome** | Google announced on **22/04/2025** it is maintaining current third-party cookie user choice without rolling out a new standalone prompt; users can still block in Settings | Do not assume blocked by default everywhere; still test with blocking enabled |
| **Chrome Incognito** | Google states third-party cookies are blocked by default in Incognito mode | Test Incognito separately from normal profiles |
| **Chrome/Edge with enterprise policy or extensions** | Admin policies/tracker blockers can restrict cookies per site | Differing behavior across profiles/enterprises is normal |
| **Brave / privacy-focused modes** | Aggressive cookie/tracker restrictions | Embedded SSO/SLO needs clean fallbacks without relying on exceptions |

Important timing note: do not infer from an old roadmap that by 2026 Chrome eliminated all third-party cookies. Google's official 22/04/2025 update stated it **maintains user choice**, and MDN documents that Chrome does not block all by default in normal browsing yet does in Incognito or when user-selected. **Browser policies can evolve**, so verify behavior on your exact target browsers.

Never advise users to disable all tracking protection just to make a tool work. Fix the design/flow first; any privacy exceptions must be approved by security, scoped per site, and communicated clearly.

## 11. Do Storage Partitioning, CHIPS, and the Storage Access API Solve This?

### 11.1. Partitioned Cookies / CHIPS

Example cookie attributes:

~~~http
Set-Cookie: __Host-embed_session=...; Path=/; Secure; HttpOnly; SameSite=None; Partitioned
~~~

A `Partitioned` cookie isolates state per top-level site; `__Host-` additionally requires `Secure`, `Path=/`, and no `Domain` in supporting browsers. CHIPS suits **embedded widgets** maintaining per-embedder state.

**CHIPS cannot be treated as a direct replacement for a global IdP session.** If the same IdP B is embedded under SP A and SP C, the two top-level sites receive two separate cookie partitions. "Logged into the IdP in a separate tab" does not mean "IdP iframes across every SP see that cookie". For SAML SLO, an SP cookie partitioned under the IdP's top-level site may not match the SP session cookie created in the SP's top-level context.

### 11.2. Storage Access API

The Storage Access API lets embedded content request access to certain unpartitioned storage/cookies when supported by the browser and permitted by user/policy. It typically requires **user interaction, visit history criteria, or permissions**, and browsers apply it differently.

Do not:

- Assume `document.requestStorageAccess()` automatically succeeds inside a hidden iframe.
- Drop `frame-ancestors`/CSP checks to allow iframes on every domain.
- Abuse popups or user-gesture tricks to bypass privacy policies.
- Treat storage access permission as proof of SAML authentication.

If an embedded IdP UI is truly required, verify API support, interaction requirements, IdP contracts, CSP, and fallback to **top-level redirects**. For enterprise systems, designs independent of silent iframes are more resilient.

### 11.3. Same Top-Level Site and Reverse Proxies

Some systems place SP and IdP under hosts sharing a registrable domain so they are **same-site**. That can ease some SameSite limits, yet does not share host-only cookies, does not ensure SAML trust, and can expand the attack surface (shared parent-domain cookies, subdomain takeover). Never "change DNS" or reverse-proxy an IdP just to dodge third-party policies without security and IdP approval.

## 12. Impact on SAML Single Logout (SLO)

SAML2 Single Logout has two fundamental flows:

- **RP-initiated:** user logs out at the SP; SP builds and signs a `LogoutRequest` to the IdP; IdP processes it and returns `LogoutResponse`.
- **AP-initiated:** logout starts at the IdP; IdP sends `LogoutRequest` to the SP; SP validates, executes logout, and returns `LogoutResponse`.

Spring Security Servlet provides `Saml2LogoutRequestFilter`, `Saml2LogoutResponseFilter`, `Saml2LogoutRequestRepository` (typically backed by `HttpSessionLogoutRequestRepository` by default), signing credentials, and SLO validators. **Request/response state and cookies/sessions affect `InResponseTo` correlation**, similar to—though distinct from—SSO.

### 12.1. RP-Initiated via Top-Level Navigation

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as SP Portal
    participant IdP as IdP B
    U->>SP: POST /logout (same-site, valid CSRF)
    SP->>SP: Execute local logout and build SAML LogoutRequest
    SP-->>U: Redirect/POST to IdP SLO
    U->>IdP: LogoutRequest
    IdP->>IdP: Verify signature, NameID, SessionIndex
    IdP-->>U: Return SAML LogoutResponse
    U->>SP: Redirect or POST back to SP SLO
    SP->>SP: Verify signature, Destination, InResponseTo, Status
    SP-->>U: Logout page/result
~~~

When the Response returns to the SP via **cross-site POST**, the SP's `SameSite=Lax` cookie may be omitted. If the SLO repository needs the session to retrieve the original LogoutRequest, correlation can fail. Using **top-level GET Redirect binding** with Lax allows cookies under Lax rules, provided the binding, signing rules, and security policy are supported by both IdP and SP. **Never force SLO POST to GET arbitrarily** or assume GET carries no security impact.

Additional note: depending on Spring Security configuration, local logout may have already terminated the HTTP session when sending `LogoutRequest`. Verify the **repository and session lifecycle** in your exact version rather than assuming the old JSESSIONID survives logout.

### 12.2. AP-Initiated or Front-Channel Logout via Iframes

Some systems implement **front-channel logout** where the IdP sends requests to multiple SPs via hidden iframes to close sessions. From the IdP's top-level page, each embedded SP sits in a **third-party context**. If the browser blocks/partitions SP cookies, the SLO request reaching the SP may **omit the `JSESSIONID` of the user's active SP session**.

Possible outcomes:

- The SP fails to identify the session to revoke.
- The SP receives a valid signed LogoutRequest yet cannot find the matching SAML principal/session.
- An iframe returns HTTP 200 while the SP tab's session remains alive.
- Some SPs log out while others do not, producing **partial logout**.
- During navigation, the user returns to the SP and gets silently re-SSOd by the IdP if the IdP session has not actually ended.

**Never call HTTP 200 on an iframe proof of global logout.** Verify actual cookie/session revocation, signatures/correlation/NameID/SessionIndex, and each SP's `LogoutResponse`.

If the design requires revoking multiple server sessions independently of the browser, evaluate back-channel/server-side mechanisms matching **IdP/SP standards and capabilities**, or centralized session management/revocation APIs within approved scope. **Standard Spring Security SAML2 SLO documentation focuses on POST/Redirect front-channel**; never claim SOAP/back-channel SLO works merely because an IdP supports it.

## 13. SLO and Logout in Other Applications: What Can Be Guaranteed?

A system may comprise:

~~~text
IdP B
  ├── SP Portal A
  ├── SP Reports C
  └── SP HR D
~~~

When a user logs out at Portal A:

1. Portal A can terminate its local session immediately.
2. Portal A issues a LogoutRequest (if SLO is supported/configured).
3. The IdP may coordinate logout at C and D via registered bindings.
4. Browser privacy policies may stop an iframe or cross-site POST from carrying C/D's cookies.
5. An SP may error, time out, or return another status.
6. The IdP may return `PartialLogout` or indicate failures.

**Proof that App A logged out is not enough to claim C/D logged out.** Operations should distinguish `LOCAL_LOGOUT_DONE`, `SAML_SLO_CONFIRMED`, `SAML_SLO_PARTIAL`, and `SAML_SLO_UNKNOWN` in telemetry and user messages, rather than using an unfounded boolean `loggedOutEverywhere`.

## 14. Protecting CSRF When Using SameSite=None

A common mistake: after setting `SameSite=None` so SAML POST carries cookies, developers assume "SAML is signed so the whole web app needs no CSRF". That reasoning is wrong.

- `SameSite` is **browser-layer CSRF assistance**, not a replacement for tokens or `Origin`/`Referer` checks on appropriate endpoints.
- `SameSite=None` lets cookies travel on more cross-site requests; **CSRF protection needs even greater care**.
- The SAML ACS is a **legitimate cross-site POST**; Spring Security provides built-in/scoped exclusions to accept `SAMLResponse`, which **does not mean disabling CSRF for every POST**.
- The SAML ACS endpoint must still verify signature, issuer, audience, recipient, `InResponseTo`, and timestamps per profile.
- `POST /logout` initiating internal logout requires CSRF protection per Spring policy, unlike SAML `LogoutRequest` sent by the IdP.
- For SLO endpoints receiving SAMLRequest/Response, verify signatures/destination/correlation and keep CSRF exemptions **narrowly scoped** to the exact filter/route.

**Never deploy the following just because POST ACS failed:**

~~~java
// Wrong approach to fixing cookies/csrf for the entire app:
http.csrf(csrf -> csrf.disable());
~~~

A `403` at the ACS can stem from CSRF matchers, filter chains, session/correlation, or SAML validation. Investigate the root cause before changing rules. Changing `SameSite` also does not alter SAML signature verification algorithms.

## 15. Do Dedicated Cookies or State Separation Help?

In complex architectures, consider:

- Keeping the general application session cookie `Lax` while using a **separate** state/callback cookie with `SameSite=None; Secure` if framework/architecture supports it, narrowing sensitive cookie exposure.
- A backend-for-frontend handling SAML ACS server-side and transitioning to a same-site session for an SPA.
- A request repository with encrypted/signed state, short TTL, consume-once semantics, and browser binding.
- OIDC Authorization Code + PKCE with top-level redirects if supported by product and IdP, though that is a **protocol change**, not a direct SAML "trick".
- Routing SAML callbacks so browsers always return to one stable public host instead of varying hosts by environment.

**Warning:** SAML sessions and `SecurityContext` typically bind to an HTTP session. Simply "adding a callback cookie" does not automatically let `Saml2WebSsoAuthenticationFilter` look up the old session; design matching repository/transport logic and check login fixation. Never write session IDs into URLs, LocalStorage, or query strings: risks leakage via referrer/logs/history and session hijacking.

## 16. Diagnosing with Developer Tools

To troubleshoot a SAML login or logout failure:

1. Open the DevTools Network tab before clicking SSO.
2. Enable **Preserve log** to retain requests across cross-domain redirects/POSTs.
3. Log in with a test account; never capture/post raw `SAMLResponse` or cookies.
4. Locate the initiating `/saml2/authenticate/{registrationId}` request and the SP's `Set-Cookie` response.
5. Locate POST `/login/saml2/sso/{registrationId}`; check **whether the request has a `Cookie` header** and whether the Cookies/Issues tab cites a blocked reason.
6. Inspect cookie `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, `Partitioned`, expiry, and whether `JSESSIONID` or `SESSION` is used.
7. Check whether the request is a **top-level POST** or inside an **iframe**; same host in a different context can change behavior.
8. Compare normal browsers, Incognito/private, Firefox, Safari, and mobile devices.
9. Check safe Spring debug/audit signals: did the repository locate AuthnRequest? Did `InResponseTo` match? Was a new session created due to missing cookies?
10. For logout, verify `LogoutRequest`/`LogoutResponse` processing and whether the real session was invalidated.

**Identify specific cookie errors:** DevTools often reports "cookie blocked due to SameSite", "third-party cookie blocked", "Secure attribute required", or "partitioned". Do not lump them into one error. Record browser/version, URL/HTTP method, response/request cookie attributes **without secret values**, and test outcomes.

### `curl` Is Helpful Yet Limited

~~~bash
curl -I https://portal.example.com/
curl -i https://portal.example.com/saml2/authenticate/partner-b
~~~

`curl` shows response headers/statuses, yet **does not enforce browser third-party cookie/`SameSite` policies** like Chromium/Safari/Firefox and does not simulate full SAML Browser SSO. Use `curl` to verify basic `Set-Cookie`/redirects, **never treat a passing `curl` test as proof the browser flow works**.

If `Set-Cookie` appears before redirect yet `Cookie` is absent at the ACS, investigate browser policy; if the cookie is sent yet Spring still misses the request, check session IDs, repositories, load balancers, timeouts, concurrency/multi-tab, and filter chains.

## 17. Standalone Java 17: Simulating Basic Cookie Rules

The following Java 17 snippet **runs no browser and performs no SAML validation**. It illustrates part of `SameSite` rules across typical contexts: same-site requests, top-level cross-site GET, top-level cross-site POST, and cross-site iframe. It separates "`SameSite=None` permits" from "browser still blocks third-party context".

Create **`CookieContextDemo.java`**:

~~~java
public class CookieContextDemo {

    enum SameSite { STRICT, LAX, NONE }
    enum Context {
        SAME_SITE,
        CROSS_SITE_TOP_LEVEL_GET,
        CROSS_SITE_TOP_LEVEL_POST,
        CROSS_SITE_IFRAME
    }

    static boolean cookieSent(
            SameSite mode, boolean secure,
            Context context, boolean blockThirdParty) {

        if (mode == SameSite.NONE && !secure) {
            return false;
        }

        if (context == Context.CROSS_SITE_IFRAME
                && blockThirdParty) {
            return false;
        }

        return switch (mode) {
            case STRICT -> context == Context.SAME_SITE;
            case LAX -> context == Context.SAME_SITE
                    || context == Context.CROSS_SITE_TOP_LEVEL_GET;
            case NONE -> true;
        };
    }

    public static void main(String[] args) {
        System.out.println("Same-site Lax: " + cookieSent(
                SameSite.LAX, true, Context.SAME_SITE, true));

        System.out.println("Cross-site GET Lax: " + cookieSent(
                SameSite.LAX, true,
                Context.CROSS_SITE_TOP_LEVEL_GET, true));

        System.out.println("Cross-site POST Lax: " + cookieSent(
                SameSite.LAX, true,
                Context.CROSS_SITE_TOP_LEVEL_POST, true));

        System.out.println("Cross-site POST None Secure: " + cookieSent(
                SameSite.NONE, true,
                Context.CROSS_SITE_TOP_LEVEL_POST, true));

        System.out.println("Iframe None Secure with block: " + cookieSent(
                SameSite.NONE, true,
                Context.CROSS_SITE_IFRAME, true));

        System.out.println("Iframe None Secure with allow: " + cookieSent(
                SameSite.NONE, true,
                Context.CROSS_SITE_IFRAME, false));

        System.out.println("None without Secure: " + cookieSent(
                SameSite.NONE, false,
                Context.CROSS_SITE_TOP_LEVEL_POST, false));

        System.out.println("Strict cross-site GET: " + cookieSent(
                SameSite.STRICT, true,
                Context.CROSS_SITE_TOP_LEVEL_GET, false));
    }
}
~~~

Run on JDK 17 or later:

~~~bash
javac CookieContextDemo.java
java CookieContextDemo
~~~

**Exact stdout:**

~~~text
Same-site Lax: true
Cross-site GET Lax: true
Cross-site POST Lax: false
Cross-site POST None Secure: true
Iframe None Secure with block: false
Iframe None Secure with allow: true
None without Secure: false
Strict cross-site GET: false
~~~

**Why:**

- `Same-site Lax: true`: same-site request, unrestricted by cross-site rules.
- `Cross-site GET Lax: true`: top-level GET is safe navigation permitted by Lax.
- `Cross-site POST Lax: false`: SAML response POSTed from IdP to SP is blocked by explicit Lax.
- `Cross-site POST None Secure: true`: in a top-level model, None/Secure permits sending cookies even when 3PC blocking applies to iframes.
- `Iframe None Secure with block: false`: even with None/Secure, browser third-party blocking can still stop it.
- `Iframe None Secure with allow: true`: when unblocked and domain/path match, cookies can be sent.
- `None without Secure: false`: modern browsers require Secure for `SameSite=None`.
- `Strict cross-site GET: false`: Strict does not follow ordinary cross-site navigation.

**Intentional limitations:** this is strictly an HTTPS conceptual model. It **does not** model Domain/Path, expiry, public suffix lists, full schemeful-site rules, browser-specific Lax-by-default 2-minute exceptions, CHIPS partition keys, the Storage Access API, tracking protection policies, request redirects/POST replay, or session cookie rotation. **Never use this program** to make production security decisions; test against real browsers and Spring Security.

## 18. Diagnostic Table: Symptom → Cause → Non-Weakening Fix

| Symptom | Possible Cause | Non-Weakening Fix |
| --- | --- | --- |
| Safari iframe IdP prompts login again | IdP cookie blocked by third-party blocking | Use top-level redirects; do not rely on silent iframes |
| Firefox iframe IdP misses session from another SP | Total Cookie Protection partitions by top-level site | Design first-party IdP navigation/fallbacks |
| Normal Chrome works, Incognito fails | Third-party cookie blocking differs by mode | Test Incognito; remove iframe dependencies |
| SAML POST ACS lacks `JSESSIONID` | `SameSite=Lax/Strict` or Domain/Path/Secure | Inspect Set-Cookie and POST headers; configure `None; Secure` per policy when needed |
| ACS POST carries cookie yet reports odd `InResponseTo` | Session repo, request state, multi-tab, different load-balancer node | Check HttpSession repository/session sharing and correlation |
| Infinite login loop after ACS | Cookie not saved post-login, wrong host/path, bad session rotation | Check Set-Cookie, public host, and redirects |
| `SameSite=None` yet browser rejects cookie | Missing `Secure` or incompatible HTTP | Serve HTTPS, emit `Secure` properly |
| `None; Secure` still fails in iframe | Third-party cookie blocking not bypassed by None | Top-level flow or policy-governed storage access |
| SP logged out from IdP yet tab stays logged in | Front-channel iframe missed SP session | Check SLO messages/session mapping; do not assert global logout |
| RP logout to SP SLO fails correlation | SLO request repository lost session or `RelayState` mismatch | Check bindings, cookie policy, repository, and logout lifecycle |
| One tenant works, another fails | Different registrable domain, cookie Domain/Path, or IdP policies | Compare hostnames, schemes, and per-tenant registrations |
| Only mobile Safari fails | WebKit ITP, third-party blocking, different session persistence | Test real devices; prefer top-level redirects |
| Backend returns 403 at ACS | May be CSRF/filter or SAML validation, not just cookies | Classify errors via safe logs and filter chains |
| Increasing clock skew still fails | Real issue is cookie/session request correlation | Restore state; never drop timestamps or `InResponseTo` |
| Session exists yet wrong roles | Separate SAML principal/authorities mapping | Check local authorization; do not blame SameSite |

Note: a cookie being sent **does not** mean the SAML assertion is valid; a valid SAML assertion **does not** mean the user is authorized for data. Verify both authentication and authorization.

## 19. Cross-Browser Test Matrix

To prove resilience, set up a lab IdP and staging SP and test:

| Browser / Context | SP-initiated SSO (top-level redirect) | ACS cross-site POST | Embedded IdP login | RP/AP SLO |
| --- | --- | --- | --- | --- |
| Normal Chrome | Yes | Yes | Yes | Yes |
| Chrome Incognito | Yes | Yes | **Must test** | Yes |
| Chrome with manual third-party cookie block | Yes | Yes | **Must test** | Yes |
| Firefox Standard / Total Cookie Protection | Yes | Yes | **Must test** | Yes |
| Firefox Strict | Yes | Yes | **Must test** | Yes |
| Safari macOS / iOS | Yes | Yes | **Must test** | Yes |
| Edge with enterprise privacy policy | Yes | Yes | **Must test** | Yes |
| Mobile WebView / embedded apps | Yes, if product supports | Yes | Must test separately | Yes |

Cells marked "Yes" are **required test cases**, not assertions that every combination already PASSES. In each combination, verify:

1. **SSO start:** request session/`AuthnRequest` is saved properly.
2. **IdP session:** whether IdP cookies are sent in top-level/iframe per policy.
3. **ACS:** POST targets the right public URL, SP session cookie presence/absence, right correlation.
4. **Authentication:** issuer, signature, audience, recipient, timestamps, and `InResponseTo` verified.
5. **User session:** post-login access to protected pages works without looping.
6. **Local logout:** `POST /logout` with CSRF invalidates the SP session.
7. **RP SLO:** LogoutRequest/LogoutResponse signed/verified and `InResponseTo` valid.
8. **AP SLO:** IdP request hits the right SP and does not delete wrong sessions.
9. **Global/partial result:** other SPs verified logged out or partial status reported accurately.
10. **Security negatives:** blocked iframe cookies never lead to validation bypass or forced logout of another user.

**QA results must record browser/version/OS, top-level vs iframe context, cookie attributes (no secrets), HTTP methods, and verified SAML states.** Never file vague bugs like "Safari broken" without identifying which request dropped cookies.

## 20. Prioritized Architectural Improvement Plan

**Priority A — Keep SAML Login Secure in Modern Browsers**

1. Move IdP login from silent iframes to top-level redirects/navigation wherever possible.
2. Verify SP session cookies when the IdP POSTs to the ACS; configure `SameSite=None; Secure` only if required by flow and after CSRF review.
3. Maintain `HttpOnly`, HTTPS, stable public hostnames, and accurate `Path/Domain`.
4. Retain `HttpSessionSaml2AuthenticationRequestRepository` where appropriate; never drop correlation because cookies were blocked.
5. If state cannot rely on sessions, design a custom `Saml2AuthenticationRequestRepository` with binding/TTL/anti-replay and test login fixation.
6. Test Chrome/Firefox/Safari, normal + private modes, desktop + mobile.

**Priority B — Make Logout Honest and Resilient Against Iframe Failures**

1. Verify IdP/SP SLO metadata, bindings, and signatures.
2. Execute RP-initiated SLO via top-level redirects when supported.
3. Do not rely on hidden iframes to guarantee system-wide logout.
4. For AP-initiated SLO, verify LogoutRequest then resolve exact session/NameID/SessionIndex per supported capabilities; never treat raw NameID as an arbitrary delete command.
5. Record `LogoutResponse Status`, `PartialLogout`, timeouts, and each SP's session state.
6. Consider server-side session revocation/back-channel mechanisms per agreed protocol/IdP for high enterprise assurance, without claiming SAML POST/Redirect behaves that way automatically.

**Priority C — Reduce Operational Errors**

1. Add metrics for missing callback cookies, session mismatches, missing AuthnRequests, correlation failures, 3PC blocks, and SLO partials/failures.
2. Include browser/version + policy in error reports; never collect cookie values or raw SAMLResponses.
3. Monitor browser cookie policy changes and Spring/Boot dependency updates.
4. Maintain a cookie-attribute rollback runbook with matching security tests.
5. Train support to distinguish "no cookie at ACS" from "wrong IdP certificate" or "user lacks role".

## 21. Scenario Exercises to Test Understanding

### Scenario A — Chrome Login Works, Safari Iframe Fails

The SP embeds the IdP login page in an iframe. Normal Chrome logs in fine, while Safari reports the IdP cannot find a session.

**Explanation:** Safari ITP restricts third-party cookies when the IdP is embedded. `SameSite=None; Secure` does not guarantee bypassing blocking policies. A more durable approach is a top-level redirect to the IdP so it uses first-party cookies, then verifying the ACS POST at the SP.

### Scenario B — IdP Authenticates, Yet SP Reports Missing AuthnRequest

Before SSO, the SP issues `JSESSIONID` with `SameSite=Lax`. The IdP returns an HTTP POST `SAMLResponse` form to an ACS on a different site.

**Explanation:** Explicit Lax omits cookies on cross-site top-level POSTs, so the SP cannot retrieve the `HttpSession` holding `AuthnRequest`. Inspect DevTools `Cookie` headers and prior `Set-Cookie`; consider cookies compatible with cross-site POST while preserving CSRF/SAML correlation—never disable `InResponseTo`.

### Scenario C — Set None, Yet Logout Iframe Still Fails

An app changes its session cookie to `SameSite=None; Secure`, yet the IdP still sends LogoutRequest via a hidden iframe and the SP sees no session.

**Explanation:** Browsers block or partition third-party cookies even with `SameSite=None`. Find an SLO approach independent of third-party iframes; verify session mapping/correlation and provide honest fallbacks for partial logout.

### Scenario D — Returning Request Has Cookie Yet Wrong Registration

The SP integrates with IdP B and C; the SP cookie arrives, yet `InResponseTo` points to C's request while the Response came from B.

**Outcome:** must reject. This is a trust/correlation mismatch, not fixed by tweaking SameSite. Inspect registration mapping and the request repository.

### Scenario E — Same Enterprise Yet Different Origins

The SP is `https://app.company.example` and the IdP is `https://login.company.example`. Both share a registrable domain/scheme, yet the SP's `JSESSIONID` cookie is absent on requests to the IdP.

**Explanation:** Same-site does not mean cookies are shared between two hosts. An SP's host-only cookie goes only to the SP; the IdP has its own cookie. Do not widen `Domain` indiscriminately.

### Scenario F — Team Proposes Disabling CSRF App-Wide

Operations notices login works better with `SameSite=None` and `csrf.disable()`.

**Analysis:** If the failure actually came from CSRF at the ACS, fix matchers/exclusions **strictly for the required SAML endpoints**. Disabling CSRF across business forms increases risk and fails to solve third-party cookie blocking in iframes. SAML endpoints must still validate signatures, recipients, issuers, and request correlation.

### Scenario G — "Signed Out of All Systems" Yet Reports C Retains a Session

The IdP sends SLO to Portal A and Reports C; the iframe to Reports C has cookies blocked, so local session C survives.

**Outcome:** never report everything logged out based solely on an iframe's `HTTP 200`. Measure whether session C truly invalidated, check valid SAML LogoutResponses, and inspect IdP partial/failure states.

## 22. End-of-Lesson Checklist

- [ ] Distinguished *third-party cookie blocking* from `SameSite` on cross-site top-level POSTs.
- [ ] Identified whether `JSESSIONID` or `SESSION` is the SP's session cookie.
- [ ] Recognized that IdP cookies and SP cookies belong to separate origins/sites.
- [ ] Tested `SameSite=Strict`, `Lax`, and `None; Secure` across target browsers/contexts.
- [ ] Never relied on the brief Lax-allowing-unsafe exception for "accidental" login success.
- [ ] Verified `Secure`, `HttpOnly`, HTTPS, and accurate `Domain/Path`.
- [ ] Avoided widening parent-domain cookies or disabling CSRF system-wide to mask bugs.
- [ ] Maintained a secure AuthnRequest repository and `InResponseTo`/`RelayState` correlation.
- [ ] Rejected unsolicited Responses or client-supplied cache state lacking browser binding.
- [ ] Never implemented SAML parsing/XML signature verification in frontend JavaScript.
- [ ] Implemented a top-level redirect SSO flow independent of silent iframes.
- [ ] Tested Safari ITP, Firefox Total Cookie Protection, and Chrome normal/Incognito/block-3PC.
- [ ] Understood CHIPS/partitioning does not guarantee a shared IdP session across SPs.
- [ ] If using the Storage Access API, verified user consent/interaction and valid fallbacks.
- [ ] Signed/verified SAML SLO LogoutRequest/Response, Destination, InResponseTo, and SessionIndex.
- [ ] When logout iframes fail, avoided falsely claiming global logout succeeded.
- [ ] Checked reverse proxies, context paths, session replication, and cookie rotation.
- [ ] Tested top-level GET vs POST HTTP methods, embedded iframes, and logout paths.
- [ ] Added diagnostic telemetry without collecting raw cookies or SAML assertions.
- [ ] Maintained guidance and update policies as browsers, IdPs, and Spring evolve.

## 23. Official Sources for Self-Verification

1. [MDN — Set-Cookie / SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): `Strict`, `Lax`, `None; Secure`, top-level GET/POST, and short-lived Lax-by-default exceptions.
2. [MDN — Third-party cookies](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies): distinguishing browser third-party policies, privacy, and effects on embedded sites.
3. [MDN — Partitioned cookies / CHIPS](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies/Partitioned_cookies): `Partitioned` semantics per top-level site.
4. [WebKit — Tracking Prevention](https://webkit.org/tracking-prevention/): Intelligent Tracking Prevention, full third-party cookie blocking, and storage limits.
5. [Mozilla Firefox — Total Cookie Protection](https://www.firefox.com/en-US/features/total-cookie-protection/): partitioned cookie jars and impact on embedded content.
6. [Google Privacy Sandbox — Next steps (22/04/2025)](https://privacysandbox.google.com/blog/privacy-sandbox-next-steps): Chrome's third-party cookie choice policy and Incognito.
7. [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): `HttpSessionSaml2AuthenticationRequestRepository`, `CacheSaml2AuthenticationRequestRepository`, and login fixation warnings when looking up solely by `RelayState`.
8. [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): ACS, `Saml2AuthenticationTokenConverter`, and validation layers.
9. [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP-initiated SLO, request repositories, signatures, and response processing.
10. [Spring Boot 3.3 — Servlet SameSite Cookies](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): `server.servlet.session.cookie.same-site` in Servlet applications.
11. [Spring Boot 4.0 — Servlet SameSite Cookies](https://docs.spring.io/spring-boot/4.0/reference/web/servlet.html): configuration and supported scope in modern releases.
12. [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): `SameSite` does not replace CSRF defense layers and requires evaluating subdomains/embedded contexts.

**Key takeaway:** a valid SAML SSO flow requires both **session cookies/SP request correlation** and **verified SAML messages**. `SameSite=Lax` cookies can be dropped on **cross-site top-level POSTs at the ACS**; `SameSite=None; Secure` solves that case yet **does not force iframes past browser third-party cookie policies**. For SLO, cookie blocking/partitioning in front-channel iframes can leave sessions at some SPs unrevoked. Prefer top-level redirects, preserve mandatory SAML checks, and report logout status honestly.