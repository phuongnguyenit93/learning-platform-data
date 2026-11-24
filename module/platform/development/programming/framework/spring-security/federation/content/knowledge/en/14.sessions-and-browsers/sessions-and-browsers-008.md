# Multi-Tab Logins and Handling Multiple Pending Requests in Spring Security SAML 2.0

When a user opens **multiple tabs of the same Service Provider (SP) application** and logs in via **SAML 2.0 federation**, each tab can generate a different `AuthnRequest` before the Identity Provider (IdP) finishes returning a `SAMLResponse`. A particularly common scenario is when the **SP's HTTP session just expired**: all tabs simultaneously detect they are unauthenticated, redirect to the IdP almost at the same time, and create multiple *pending authentication requests*.

If the SP stores only one `AuthnRequest` in the same `HttpSession`, a later request can overwrite an earlier one. When the first tab's response returns, its `InResponseTo` no longer matches the request held by the repository: login fails even though the IdP authenticated properly. Conversely, if solving multi-tab issues relies solely on looking up requests by `RelayState` in a global cache **not bound to the browser**, the SP can open up **login CSRF / session swapping** risks.

**Goal of this article:** accurately understand the boundary between **tabs, browser sessions, SAML transactions, and SecurityContext**; design a secure store for **multiple pending transactions**; match each response with the **exact** request; handle out-of-order, duplicate, expired, and concurrent callbacks across multiple nodes; and configure/test with Spring Security **without disabling SAML verification**.

## 1. Four Concepts That Must Never Be Equated

| Concept | Actual Scope | Implications for Multi-Tab Login |
| --- | --- | --- |
| **Browser tab** | One UI context; may have its own `sessionStorage` state. | Two tabs can initiate **two** separate SSO flows. |
| **`HttpSession` / SP cookie** | Usually shared across same-origin tabs within **one browser profile**. | Two tabs usually share the **same** `JSESSIONID`, so a single-slot store is easily overwritten. |
| **SAML `AuthnRequest@ID` + `RelayState`** | **One** SP-initiated authentication transaction; must stay independent per initiation. | Tab A has `req-A`/`relay-A`; tab B has `req-B`/`relay-B`. |
| **Spring Security `Authentication` + `SecurityContext`** | Logged-in identity maintained by the SP in its HTTP session/persistence mechanism. | Once login succeeds, tabs sharing the session **share that same identity** on subsequent requests. |

**There is no "independent Spring Security login session per tab" merely because the user has two tabs.** If the browser sends the same session cookie to the SP, both tabs see the same authenticated account and the same logout/role state. To run two different accounts simultaneously, users generally need separate browser profiles, cookie containers, or genuinely isolated browser/session contexts—not merely adding a JavaScript variable named `tabSession`.

Also do not confuse `AuthnRequest@ID` with `SAMLResponse@ID`, `Assertion@ID`, `AuthnStatement@SessionIndex`, or `JSESSIONID`. They identify different objects.

## 2. Basic Failure Scenario: Two Tabs and One Request Slot

Suppose the user is on the same origin `https://sp.example.org`, and both tabs share browser session `S-100`:

~~~text
Time         Tab A                  SP / HttpSession S-100                Tab B
----------------------------------------------------------------------------------------
T0           GET /reports/42        Not logged in
T1           AuthnRequest req-A --> Save pending = req-A
             RelayState relay-A
             Redirect to IdP

T2                                                                        GET /settings
T3                                  Save pending = req-B  <-- OVERWRITE
                                    (req-A is gone)
                                                                          AuthnRequest req-B
                                                                          RelayState relay-B
                                                                          Redirect to IdP

T4           IdP returns Response-A:
             InResponseTo=req-A
             RelayState=relay-A
             POST to ACS
T5                                  Repository loads pending=req-B
                                    req-A != req-B
                                    => correlation FAIL

T6                                                                        Response-B hits ACS
T7                                  If req-B still exists and is valid,
                                    callback B may succeed
~~~

In **Spring Security 6.2.1**, a multi-tab issue with `HttpSessionSaml2AuthenticationRequestRepository` was publicly documented: `AuthnRequest` entries shared a single key in the session, so newer requests overwrote earlier ones; authors observed `InResponseTo` errors when callbacks returned out of order. A `RelayState`-based cache solution appeared later, accompanied by security caveats. **Do not assume from this example that every version or every custom repository behaves identically**; inspect the exact class/version you run.

### 2.1. Easily Observed Symptoms

- Tabs A and B both redirect to the IdP, yet one tab reports `InResponseTo mismatch` or "AuthenticationRequest not found".
- When sessions expire, reopening multiple tabs spikes errors while single-tab login still succeeds.
- Tab B's callback arrives before A; B logs in successfully, while A encounters rotated session/cookies from **session fixation protection**.
- User finishes logging in yet lands on the **other tab's** page because `SavedRequest`/target URL shares a single slot in the session.
- Two tabs intentionally use two different IdPs/tenants/accounts and callbacks arrive close together, leaving an unexpected identity in the shared SecurityContext.
- In multi-node production, the request is saved on node A yet the callback hits node B before the session store synchronizes.

Distinguish **correlation errors**, **cookie/session errors**, **SAML signature/condition errors**, **SecurityContext write races**, and **post-login redirect errors**. They can occur together yet require different fixes.

## 3. SAML 2.0 Flow Involving Multiple Pending Requests

### 3.1. Initiating AuthnRequest at the SP

A standard SP-initiated flow:

1. The browser opens an auth-protected resource at the SP; Spring Security sees the user has no valid `Authentication`.
2. `Saml2WebSsoAuthenticationRequestFilter` triggers `/saml2/authenticate/{registrationId}`.
3. `Saml2AuthenticationRequestResolver` builds an `AuthnRequest` with a unique `ID`, selects `RelyingPartyRegistration`, sets Destination to the IdP SSO endpoint, and generates `RelayState` per binding/profile.
4. `Saml2AuthenticationRequestRepository` saves the **pending transaction** before sending the browser to the IdP.
5. The browser is redirected to IdP SSO, typically via HTTP-Redirect binding (or POST when both sides configure support).

A pending request is more than an ID string. It must bind **registration, expected IdP issuer, SP entityID, ACS, timestamp, browser session, and navigation target**. Those SAML attributes are later used to validate the response message.

### 3.2. IdP Returns Response to the ACS

In SAML HTTP-POST binding, the IdP submits a form carrying `SAMLResponse` and optionally `RelayState` to the ACS `/login/saml2/sso/{registrationId}`. `Saml2WebSsoAuthenticationFilter` receives the request, the converter loads `RelyingPartyRegistration` and the pending transaction, and `AuthenticationManager`/the OpenSAML provider validates it.

Checks tied directly to one transaction:

| Response Input | Must Match |
| --- | --- |
| `Response@InResponseTo` in SP-initiated SSO | Previously issued **`AuthnRequest@ID`**, per profile/validator rules. |
| `SubjectConfirmationData@InResponseTo` (bearer) | **Original AuthnRequest ID**; never another request's ID in the same session. |
| `RelayState` | Value belonging to that exact **pending transaction** per binding, never an arbitrary redirect URL. |
| `Issuer` + signature | **Registered IdP/keys** for that transaction; never trust an IdP just because the XML claims an issuer. |
| `Destination` and `Recipient` | SP's **ACS URL** matching the registration and actual receiving endpoint. |
| `AudienceRestriction` | Exact **SP entityID**. |
| Conditions/SubjectConfirmation validity | Assertion validity window and profile; reject expired assertions. |
| Assertion/Response replay key | Unused previously per anti-replay mechanism. |

**Matching `RelayState` alone is not enough:** the response must still have valid signature/issuer/audience/destination/recipient/timestamps/correlation. **Matching `InResponseTo` alone is not enough either:** if a request ID can be fetched from a cache using only browser-sent data, the SP still may not know whether **this specific browser** initiated that login beforehand.

## 4. Expected Behavior When Two Valid Requests Exist

Suppose within the same session `S-100`, two independent transactions exist:

| Property | Tab A | Tab B |
| --- | --- | --- |
| AuthnRequest ID | `req-A` | `req-B` |
| RelayState | `relay-A` | `relay-B` |
| Registration | `corporate` | `corporate` |
| Desired post-login page | `/reports/42` | `/settings` |
| Status | Pending | Pending |

A multi-transaction store records:

~~~text
BrowserSession S-100:
  relay-A -> Pending(requestId=req-A, registration=corporate,
                     returnRoute=/reports/42, expiresAt=T+180s)
  relay-B -> Pending(requestId=req-B, registration=corporate,
                     returnRoute=/settings, expiresAt=T+180s)
~~~

If **Response-B arrives first**:

1. The SP verifies Response-B and locates **pending B** by transaction identifier **within session S-100**.
2. Compares `InResponseTo=req-B`, B's relay, and B's registration; ensures the assertion targets this SP.
3. Record B is **consumed exactly once**, while record A **remains**.
4. If Response-A arrives later while session/correlation remains valid, the SP can verify A against record A. Whether another `Authentication` is published depends on the **shared SecurityContext policy and the already-logged-in session from B**.

**Invariants:** B must never use `req-A` merely because they share a browser session, and completing B **must not bulk-delete A**. Never downgrade a response with a mismatched `InResponseTo` into an **IdP-initiated/unsolicited login** just to hide errors from users.

### 4.1. Which Tab Becomes the Logged-In Account?

Even though pending A/B are independent, their **`SecurityContext` may share the same `HttpSession`**. If A and B log into the **same local account**, the app may adopt a policy letting both finish while transactions remain valid; however, you must handle races in session persistence, session ID rotation, saved requests, and redirect logic.

If A and B log into **two different identities** (e.g., IdP A/tenant A and IdP B/tenant B), do not accidentally let "last callback wins" switch the active account on the other tab. A safe policy is typically **not to silently swap the principal of an already-authenticated session via an overlapping callback**, unless the user explicitly started a bound account-switch flow. You can keep the existing session or require logging out/logging in via a separate browser context. Policy choices must be uniform across all nodes.

**Same session cookie = same authentication boundary**, so Tab A's UI must never assume the user is still principal A if Tab B altered the session. Every API must verify identity/tenant and permissions for the current request on the server.

## 5. Designing a Pending Requests Store for Multiple Tabs

### 5.1. Structure of a Pending Transaction

~~~text
PendingSamlLogin:
  transactionKey = random opaque RelayState (32 or 43 ASCII bytes)
  authnRequestId = "_request-7ef"
  browserSessionBinding = hash(server-side session ID / secret)
  registrationId = "corporate"
  expectedIdpIssuer = "urn:example:idp:corporate"
  spEntityId = "urn:example:sp:portal"
  expectedAcs = "https://sp.example.org/login/saml2/sso/corporate"
  safeReturnRouteId = "reports:42"
  issuedAtUtc = "2026-11-07T03:00:00Z"
  expiresAtUtc = "2026-11-07T03:03:00Z"
  state = "PENDING"
  consumedAtUtc = null
~~~

Keep **one record per `AuthnRequest`**, never a single fixed attribute inside `HttpSession` when business cases need multiple pending requests. To store directly in the session, you can use a session-attached `Map<RelayState, PendingRequest>`, provided concurrency, persistence, and cleanup are addressed. When using Redis/DB, the lookup key must also bind to a **trusted browser session**, not just the relay value.

**Never store sensitive data** such as passwords, tokens, plaintext assertions, cookies, or full reports in RelayState; values travel through the browser/IdP and may appear in logs. `RelayState` in SAML HTTP bindings is capped at **80 bytes**; prefer 24 random bytes → 32-byte unpadded Base64URL ASCII or 32 random bytes → 43 ASCII bytes.

### 5.2. Mandatory Data Invariants

1. **Unique per transaction:** each request gets a distinct SAML ID and RelayState, even within the same tab or cookie.
2. **No overwriting:** creating B must not lose A or replace any shared "current request" slot.
3. **Browser-scoped:** lookup must prove the transaction belongs to **the initiating session/browser** or an equivalent browser-binding proof.
4. **Federation-scoped:** registration, IdP issuer, SP entityID, and ACS must match the created request.
5. **TTL:** pending entries must expire quickly; expired callbacks are rejected.
6. **Single use:** transactions complete at most once via an **atomic compare-and-remove / PENDING → CONSUMED transition**.
7. **Replay protection:** the assertion/response replay store is a **separate layer** from consuming the pending request; enforce both.
8. **Memory bounded:** cap pending requests per session (e.g., 4–8 or product-appropriate); enforce session/IP rate limiting.
9. **Cleanup:** purge expired entries or invalidated sessions; never delete another tab's valid pending request by mistake.
10. **Fail closed:** if binding cannot be retrieved/verified or the state store is inconsistent, never treat the callback as valid by default.

Do not delete A merely because B succeeded. Yet also do not **keep old requests forever** or allow arbitrary `InResponseTo` values after logout or principal switches. Every piece of state needs an explicit lifecycle and invalidation policy.

### 5.3. When Should Creating More Requests Be Rejected?

If the same browser session already has multiple pending SSO flows, there are two product options:

- **Allow multiple independent transactions**, e.g., up to 5 transactions, each bound by ID/Relay/TTL/registration; monitor and handle cookie/session concurrency as noted.
- **Coalesce/coordinate login flows**, allowing only one active login per session while other tabs wait or join the shared login state. This can be simpler if the app does not need two IdPs or multiple return targets; it still must handle timeouts, reloads, failover, and avoid one tab deleting another tab's transaction.

If the product simply needs "the user logs in once for all tabs", **coalescing SSO initiation** can work better than piling up pending requests—yet **never auto-coalesce** requests with different registrations/tenants or pending flows without clear policy. Whichever path you choose, each callback still must be validated and correlated strictly.

## 6. Spring Security: Default Repository and Custom Options

### 6.1. Repository in the Standard Flow

Spring Security Servlet defines `Saml2AuthenticationRequestRepository<T extends AbstractSaml2AuthenticationRequest>` with operations:

- `saveAuthenticationRequest(request, httpRequest, httpResponse)`: saves the request before sending to the IdP.
- `loadAuthenticationRequest(httpRequest)`: loads the request matching a callback.
- `removeAuthenticationRequest(httpRequest, httpResponse)`: retrieves and removes a request when consuming the transaction.

`Saml2WebSsoAuthenticationRequestFilter` uses the repository to save requests, while `Saml2WebSsoAuthenticationFilter`/`Saml2AuthenticationTokenConverter` uses it when validating responses. A custom repository must integrate **the same logic and backing store in both directions**; never swap out the AuthnRequest-sending resolver while forgetting the callback converter.

Current Spring Security documentation notes **`HttpSessionSaml2AuthenticationRequestRepository`** is the default and stores `AbstractSaml2AuthenticationRequest` in `HttpSession`. In versions reported to use a single fixed session key, it can **overwrite pending requests** when multiple flows start. That is why you must test your exact runtime version and pick an appropriate repository.

### 6.2. `CacheSaml2AuthenticationRequestRepository` Does Not Automatically Prove Browser Binding

Starting in **Spring Security 6.5**, **`CacheSaml2AuthenticationRequestRepository`** allows looking up AuthnRequests via a RelayState-keyed cache without relying solely on `HttpSession`. This can reduce pending-request collisions and help when `SameSite=Strict` drops session cookies.

However, Spring Security documentation highlights a **security tradeoff**: this cache proves a request was **created by the application**, not automatically that it was created **by the same browser submitting SAMLResponse to the ACS**. Looking up a global cache solely by `InResponseTo` or `RelayState` lets an attacker start a transaction in their own browser and feed the response to a victim's browser, causing **login fixation / login CSRF / session swapping** in affected configurations.

**Do not treat "switching to `CacheSaml2AuthenticationRequestRepository`" as a risk-free fix.** Supporting both multiple tabs and login CSRF defense requires a **browser-bound multi-request store**: multiple keys per transaction, where lookup/consumption still proves linkage to the browser session/pre-established proof and defends against attacker-controlled relay values.

### 6.3. Common Spring Security Configuration Pattern

Example `SecurityFilterChain` for a Spring Boot Servlet app with a valid `RelyingPartyRegistration`:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is a **Spring Boot configuration**, not a program compilable with plain `javac` without Spring Security, IdP metadata, and credentials. It enables SAML login yet **does not by itself solve multiple requests in one session**; verify the configured repository.

With a custom repository, register a **`Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>` bean** per your version's DSL/API:

~~~text
@Bean authenticationRequestRepository():
    return BrowserBoundMultiRequestRepository(
        sharedPendingStore,
        sessionBindingPolicy,
        transactionTtl,
        idpRegistrationPolicy)

The BrowserBound... classes here are architectural models,
NOT built-in classes in Spring Security.
~~~

Ensure both the request-sending filter and callback-processing converter share the same repository, handling correlation along the official framework path. If custom code "loads request by RelayState" before Spring validates the response, **registration routing** could rely on untrusted input, so preserve binding/trust checks. Never build an `Authentication` directly from NameID without running the OpenSAML validator.

### 6.4. Version Cross-Check

| Component / Behavior | What to Verify |
| --- | --- |
| `HttpSessionSaml2AuthenticationRequestRepository` | Which session/attribute it uses; does your **actual dependency** support multiple pending requests? |
| `CacheSaml2AuthenticationRequestRepository` | Available in **6.5+**; cache/lookup behavior, TTL, and browser-binding limits. |
| `OpenSaml4AuthenticationProvider` | Found in Spring Security 6.x using OpenSAML 4 (depending on release). |
| `OpenSaml5AuthenticationProvider` | Found in newer release docs using OpenSAML 5. |
| `Saml2AuthenticationTokenConverter` | How it locates `RelyingPartyRegistration` and pending requests when ACS URLs omit `registrationId`. |
| `SessionAuthenticationStrategy` / `SecurityContextRepository` | Session ID rotation, persistence, and handling two parallel callbacks after one succeeds. |

Do not assume upgrading dependencies alone solves all **session concurrency, return URL, and multi-account** concerns. Integration-test on your actual version and container.

## 7. Runnable Java 17: One Session with Multiple Pending AuthnRequests

The following program simulates a **browser-bound pending request store**, using `ConcurrentHashMap` and `SecureRandom` to demonstrate multi-tab flows, out-of-order callbacks, session mismatches, TTLs, and single-use consumption. It **does not parse SAML, verify signatures, or create Spring Authentication**; in a real flow, `complete` must only be called **after SAMLResponse is verified by the official provider** and issuer/registration/`InResponseTo` are matched.

File **`PendingSamlRequestsDemo.java`**:

~~~java
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class PendingSamlRequestsDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    record Pending(String authnRequestId, String registrationId,
                   String safeReturnRoute, Instant expiresAt) {}

    static class Store {
        private final ConcurrentMap<String, ConcurrentMap<String, Pending>>
                byBrowserSession = new ConcurrentHashMap<>();

        private static String allowRoute(String candidate) {
            return switch (candidate) {
                case "/reports", "/settings", "/dashboard" -> candidate;
                default -> "/dashboard";
            };
        }

        String begin(String browserSession, String authnRequestId,
                     String registration, String route, Instant now) {
            ConcurrentMap<String, Pending> pending =
                    byBrowserSession.computeIfAbsent(
                        browserSession, ignored -> new ConcurrentHashMap<>());
            Pending entry = new Pending(authnRequestId, registration,
                    allowRoute(route), now.plusSeconds(180));

            String relay;
            do {
                byte[] bytes = new byte[24];
                RANDOM.nextBytes(bytes);
                relay = Base64.getUrlEncoder()
                        .withoutPadding().encodeToString(bytes);
            } while (pending.putIfAbsent(relay, entry) != null);

            return relay;
        }

        String complete(String browserSession, String relayState,
                        String verifiedInResponseTo,
                        String verifiedRegistration, Instant now) {
            ConcurrentMap<String, Pending> pending =
                    byBrowserSession.get(browserSession);
            if (pending == null || relayState == null) {
                return "DENY";
            }
            Pending entry = pending.get(relayState);
            if (entry == null
                    || !Objects.equals(entry.authnRequestId(),
                                       verifiedInResponseTo)
                    || !Objects.equals(entry.registrationId(),
                                       verifiedRegistration)
                    || !now.isBefore(entry.expiresAt())) {
                return "DENY";
            }
            // remove(key, value) is atomic: only one callback consumes.
            return pending.remove(relayState, entry)
                    ? entry.safeReturnRoute() : "DENY";
        }

        int pendingCount(String browserSession) {
            ConcurrentMap<String, Pending> pending =
                    byBrowserSession.get(browserSession);
            return pending == null ? 0 : pending.size();
        }
    }

    public static void main(String[] args) {
        Store store = new Store();
        Instant t = Instant.parse("2026-11-07T03:00:00Z");

        String relayA = store.begin(
                "browser-1", "req-A", "corporate", "/reports", t);
        String relayB = store.begin(
                "browser-1", "req-B", "corporate", "/settings", t);

        System.out.println(relayA.length());
        System.out.println(store.pendingCount("browser-1"));

        // Another browser cannot consume browser-1's request.
        System.out.println(store.complete(
                "browser-other", relayA, "req-A", "corporate",
                t.plusSeconds(1)));

        // Response-B arriving before Response-A still matches the right transaction.
        System.out.println(store.complete(
                "browser-1", relayB, "req-B", "corporate",
                t.plusSeconds(2)));
        System.out.println(store.complete(
                "browser-1", relayA, "req-A", "corporate",
                t.plusSeconds(3)));

        // Replay B must fail.
        System.out.println(store.complete(
                "browser-1", relayB, "req-B", "corporate",
                t.plusSeconds(4)));

        String relayC = store.begin(
                "browser-1", "req-C", "corporate",
                "/dashboard", t);
        System.out.println(store.complete(
                "browser-1", relayC, "req-C", "corporate",
                t.plusSeconds(181)));

        System.out.println(store.pendingCount("browser-1"));
    }
}
~~~

Compile/run on Java 17 or later:

~~~bash
javac PendingSamlRequestsDemo.java
java PendingSamlRequestsDemo
~~~

**Exact stdout** (random RelayState values are not printed):

~~~text
32
2
DENY
/settings
/reports
DENY
DENY
1
~~~

Explanation:

1. 24 random bytes, unpadded Base64URL, yields **32 ASCII characters / 32 bytes**, well under SAML's 80-byte RelayState limit.
2. Two tabs created **two pending entries** under the same `browser-1`.
3. `browser-other` cannot use another session's RelayState.
4. Response B arriving first still matches `req-B`, retrieving `/settings`.
5. Response A arriving later still exists and matches `req-A`, retrieving `/reports`.
6. Replaying Response B cannot consume pending B a second time.
7. Response C arriving past the 180-second TTL is rejected.
8. C remains in the map in an expired state, so the entry count is 1: production **must have TTL eviction/cleanup**; this example intentionally omits memory cleanup.

**Example boundaries:** the `complete` method does not validate parameters labeled "verified" itself; it only demonstrates state-store logic. Production must extract those facts **after SAML verification**, include issuer/SP entityID/ACS/audience in the binding, use a consistent/TTL/capacity-bounded multi-node store, and never let attackers supply `browserSession` as an HTTP string. The session value in the demo models a server-side `HttpSession`, not a query-parameter token. The example above tests two callbacks sequentially; **it does not by itself solve two callbacks concurrently writing SecurityContext**.

### 7.1. Why Use `remove(key, value)`?

With two concurrent requests carrying the same `RelayState`, both might read a valid `entry`. Calling `get` then `remove(key)` and **always accepting** risks both treating it as the first consumption. `ConcurrentMap.remove(key, value)` lets **only one callback** consume that exact entry within one JVM. In Redis/SQL, use an equivalent **atomic compare-and-delete / state transition** on the shared store.

### 7.2. Do Not Rely on `sessionStorage` or `tabId` for Security

Browser `sessionStorage` can record **per-tab UI intent**, such as "this tab wants reports", yet is not a trusted source for `issuer`, `InResponseTo`, access permissions, or server-side session binding. SAML HTTP-POST ACS is a navigation through the IdP: tab JavaScript state may survive or vanish depending on the flow, while the server still requires a **protected pending request**. A client-claimed `tabId` does not prove the caller is using the initiating browser.

## 8. Return URL: Preventing Tab A from Landing on Tab B's Page

After successful authentication, Spring Security can use **`SavedRequestAwareAuthenticationSuccessHandler`** and `RequestCache` to return to the pre-login resource. Because tabs normally share a session, **the saved request in the session can be overwritten by another tab** if the workflow has only one destination slot.

Example:

~~~text
Tab A wants /reports/42  -> session.savedRequest=/reports/42
Tab B wants /settings    -> session.savedRequest=/settings
Tab A finishes login     -> sent to /settings   (wrong tab)
~~~

Do not "fix" this by setting `RelayState` to an arbitrary absolute URL and calling `sendRedirect(RelayState)`, due to **open redirects** and the 80-byte limit. Store `safeReturnRoute` **individually inside each pending transaction** after route/tenant allowlist validation, restoring the route only after **SAML validation + transaction consumption**. If no route is found, use a **fixed internal fallback** such as `/dashboard` or return a transaction error; never trust `Referer` or URLs supplied by the IdP/browser.

Note: **a valid target route does not mean the user is authorized for the resource**. If A requested `/reports/42` belonging to another tenant, backend authorization must still deny it even when AuthnRequest and RelayState are valid.

### 8.1. Route Mapping Example Instead of Raw URLs

| Data Permitted Before Login | SP Path Generated After Login |
| --- | --- |
| `route=dashboard` | `/dashboard` |
| `route=settings` | `/settings` |
| `route=report; id=42` with valid report ID | `/reports/42` |
| External URL or non-allowlisted route | `/dashboard` or deny |

Never store secrets, tokens, sensitive search queries, or SAMLResponse in RelayState. If deep-links with query parameters are needed, validate/encode every component per application policy before storing server-side state.

## 9. Cookies, SameSite, and Session Fixation: Three Distinct Failure Sources

### 9.1. SameSite When the IdP POSTs to the ACS

SAML **HTTP-POST binding** is often a **cross-site POST from the IdP to the SP**. In many browsers, `SameSite=Lax` cookies are omitted on ordinary cross-site POSTs; `SameSite=Strict` is even stricter. A pending request stored in `HttpSession` can become **not found** at the ACS because the browser withheld the cookie.

Environment-dependent remedies include configuring a compatible cookie policy (e.g., `SameSite=None; Secure` for appropriate cookies over HTTPS, subject to browser support), or designing a separately protected **transaction binding cookie**. Assess CSRF and tracking policies; never slap `SameSite=None` onto every cookie without risk review. Spring Security provides a CSRF exception specifically for the **ACS endpoint** on SAML POSTs; never disable CSRF site-wide.

**Crucially:** using a RelayState-only cache to bypass dropped cookies **does not automatically recreate a secure link to the initiating browser**. You still need verifiable binding proof when the callback arrives, rather than dropping correlation.

### 9.2. Session Fixation Protection Rotates the Session ID After Login

Spring Security typically protects against session fixation by rotating the session ID upon successful authentication, e.g., `changeSessionId` on modern Servlet containers. If Response B succeeds first, the session cookie may rotate; Response A still returning from the IdP may send the **old cookie**, or a concurrent request may hold a pre-rotation snapshot of the session.

At that point the issue is not merely "the repository overwrote"; it may be:

- Pending A was stored under the old session ID yet callback A arrived after rotation.
- Node A/B concurrently committed `SecurityContext`, session strategies, or cookies.
- The browser received two `Set-Cookie` responses close together and the last applied order did not match request order.
- One callback authenticated one principal while another wanted to switch principal/tenant.

**Do not disable session fixation protection** just to make multi-tab stop failing. Design a policy to preserve/migrate pending transactions safely across session ID rotation per the framework while keeping browser-bound evidence valid. For flows whose evidence was lost, fail safely with a clear error and start a fresh transaction.

### 9.3. Different Profiles / Incognito Browsers

Two tabs normally share cookies, whereas a different Chrome profile, different Firefox container, incognito window, or separate browser has a **separate cookie jar**. When sessions differ, having the same user at the IdP does not mean the SP should accept the same RelayState/callback across them. Never use email/NameID to drag a transaction from session A into session B. If the business goal is syncing "logged in across devices", that is an IdP SSO/session-management topic, **different** from multiple pending AuthnRequests within one browser session.

## 10. Multi-Node Clusters and Shared Memory

An SP running behind a load balancer can create an AuthnRequest on **node A** and receive the ACS callback on **node B**. With local `HttpSession`, node B lacks the pending request. With a distributed cache keyed solely by RelayState, node B finds the pending entry yet **risks losing browser binding** if poorly designed.

~~~text
Browser (two tabs, same cookie)
       |
       v
   Load Balancer
   /           \
Node A          Node B
begin req-A     begin req-B / callback A, B
   \            /
    \          /
    Shared HttpSession + Pending Transaction Store
       key: browser-session-binding + RelayState
       value: AuthnRequest ID, IdP registration,
              ACS, trusted return route, TTL
       atomic consume: once per transaction
~~~

**Operational guarantees to enforce:**

- Reliable shared/replicated session store; persist rotated session IDs per Servlet/Spring Session support.
- Pending requests keyed by browser/session **and** transaction, never a single static key.
- Atomic insert/consume on concurrent callbacks; at most one side wins a given request.
- Short TTLs for pending entries; policy-driven cleanup and per-session pending caps.
- Keys namespaced by app/environment/IdP so two tenants never collide.
- Do not prematurely evict valid pending requests under memory pressure without a safe fallback.
- On store timeouts/partitions, **fail closed** instead of accepting uncorrelated responses by default.
- Consider **strong consistency**/failover if a transaction must never be consumed twice.
- Emit logs/metrics free of SAMLResponses or cookies to distinguish duplicates, expirations, wrong browsers, wrong request IDs, and node mismatches.

**Sticky sessions** can reduce random session misses, yet cannot replace proper safeguards for rolling deployments, failovers, two-request tabs, and cross-node callbacks.

## 11. SecurityContext Write Races: Critical Beyond the Pending Store

Storing multiple pending requests separately solves `AuthnRequest` overwriting, yet **does not by itself solve** multiple concurrent callbacks **simultaneously writing `SecurityContext` in one browser session**.

### 11.1. Types of Races

| Scenario | Risk | Recommended Policy |
| --- | --- | --- |
| A and B share the same local principal, callbacks arrive seconds apart. | Session ID/cookie rotates, saved request/redirect hits wrong tab. | Coalesce/make idempotent per policy; test session persistence and per-transaction URLs. |
| A is account X, B is account Y, sharing one cookie. | One callback overwrites the other's `Authentication`. | **Never silently switch principals**; require explicit account-switch flows or reject conflicting callbacks. |
| A uses IdP tenant A, B uses tenant B. | IdP mix-up or user silently shifted to unintended tenant. | Pin registration/issuer/tenant to pending request; reject mismatches. |
| B already logged in, A is a late callback from before logout. | Old session could be unintentionally resurrected. | Revocation/epoch/transaction generation; reject pending entries from logged-out or identity-switched sessions. |
| B created a new session, A carries the old cookie. | Pending entry missing or wrong session recreated. | Session-rotation-aware binding; fail closed if transaction cannot be proven. |
| Client retries B's POST ACS. | Creates Authentication/session twice from the same assertion. | Single-use pending entries + assertion replay protection. |

Maintain a **login generation** or epoch per browser/session to invalidate pending requests belonging to **revoked session generations** if business rules allow only the latest login. Note that if an epoch causes stale callback A to be rejected, that is an **intentional decision**; do not claim A will always succeed independently in every setup. Clearly prioritize between "multi-tab all succeed" UX and "one authentication at a time" security policy.

### 11.2. Optimizing When Five Tabs Expire Simultaneously

An application can adopt **single-flight login**: instead of all tabs firing SAML simultaneously, one tab acts as "leader" initiating AuthnRequest while others wait for a signal or re-poll auth status once complete. `BroadcastChannel`, `storage` events, or server state can coordinate UX, provided leader-tab closures and timeouts are handled. **These client signals are not authentication proofs**; the server must still verify SAMLResponses and sessions.

When only one tab actually runs SSO, fewer pending requests and fewer races occur. Still, never rely solely on leader logic: browsers can drop messages, disable JS, or open fresh tabs. The backend must remain safe when multiple requests arrive anyway.

## 12. Mandatory Tests: Scenarios and Expected Results

| Scenario | Safe Outcome |
| --- | --- |
| One tab initiates req-A and receives response A on time. | Verify SAML, consume A, create authentication per policy. |
| Two tabs on same session create A/B; response B arrives before A. | Each response matches its own `InResponseTo`/RelayState; no cross-pending mix-up. |
| Three tabs A/B/C; C times out while A/B stay valid. | C is rejected; A/B are not arbitrarily deleted. |
| Response A carries `InResponseTo=req-B`. | **Reject**; never pick any arbitrary pending request to "patch" a mismatch. |
| Response A has the right ID yet B's RelayState. | **Reject**; must not pick another request. |
| Response A arrives with a different browser session. | **Reject** even if the request exists in a global cache. |
| Response A re-submitted after already consumed. | **Reject replay**; do not create a new session. |
| Replaying a validly signed assertion whose request ID is no longer pending. | Reject; do not fall back to IdP-initiated. |
| A used IdP-X yet callback carries issuer IdP-Y. | Reject; registration is pinned to the transaction. |
| Two callbacks race with the same claim/relay on two nodes. | At most one callback passes the atomic gate. |
| Two different callbacks for the same principal arrive concurrently. | Handled per session generation policy; no random overwrite errors. |
| Two callbacks for different principals share one cookie. | Never silently swap principals; reject or enforce explicit account switch. |
| B logs in successfully, A calls back after logout. | A does not resurrect the revoked session. |
| Session cookie blocked by SameSite. | Do not downgrade correlation; diagnose cookies, apply safe binding, or require fresh login. |
| Callback hits a different node after a rolling deployment. | Locates shared state for the right session if available, or fails closed. |
| Tab B's SavedRequest overwrites A's. | Per-transaction return route or internal fallback; no open redirects. |
| RelayState tampered to `https://evil.example/`. | Never used as redirect `Location`. |
| RelayState exceeds 80 bytes. | Never created/accepted per binding policy, never silently truncated. |
| 100 requests on the same session within seconds. | Rate-limited/pending-capped; no RAM/Redis exhaustion. |
| Logout occurs while pending requests remain. | Invalidate/cancel related pending entries per policy so old callbacks cannot log back in. |

### 12.1. Practical Test Harness for Spring Boot

Use a **test IdP** (or validly signed SAMLResponses against a test trust anchor), a running Spring Boot app, and a browser with DevTools. Recommended steps:

1. Set a short session timeout in the **test environment** (do not copy verbatim to production).
2. Open 3–5 same-origin tabs and navigate all of them to login-protected resources.
3. Coordinate tabs to emit AuthnRequests nearly simultaneously and record **only redacted request IDs/RelayState**; never log real assertions or cookies.
4. Intentionally make the IdP return responses in order B → A → C.
5. Verify each response matches only one pending entry without overwriting; expired ones are rejected.
6. Repeat with **two Spring Boot instances** sharing a session/pending store.
7. Test cases where the browser omits cookies on POST ACS, session fixation rotation, per-tab redirects, and account conflicts.
8. If using a custom repository, write unit tests for atomic remove/expiry/caps and integration tests proving Spring filters/converters invoke that repository.

**Never disable signature, audience, recipient, InResponseTo, or replay validators in tests just to claim multi-tab works safely.** Storage-only unit tests do not prove the full SAML login flow is sound.

## 13. Quick Troubleshooting Table

| Symptom | Possible Cause | Inspection / Fix |
| --- | --- | --- |
| `InResponseTo` fails only during multi-tab logins. | Repository keeps only the last request, or callback matches wrong relay. | Count pending entries per session, requestId/RelayState; check version/impl and multi-entry store. |
| Authentication request not found after cross-site POST. | `SameSite` cookie dropped session, or session ID rotated. | Inspect cookies sent to ACS, SessionRepository, and session fixation strategy. |
| Tab A gets redirected to Tab B's page. | Shared `SavedRequest` overwritten, redirect pulled from global state. | Store safe route per transaction; bound success-handler redirects. |
| One SAML request authenticates twice. | Non-atomic consumption, missing replay store. | Enforce single-use pending entries and assertion replay markers. |
| Multi-node only lets node A log in. | Local session/request store lacking replication. | Shared session/store, atomic semantics, consistency. |
| Logged into unintended user/tenant. | Two callbacks wrote shared SecurityContext, or IdP mix-up. | Pin registration/issuer/tenant, coordinate account switches, check principal before commit. |
| Old callback logs back in after logout. | Outstanding requests not canceled by session generation. | Revoke pending entries and bump session epoch at logout. |
| After enabling RelayState cache, login CSRF test passes. | Cache lacks browser binding. | Restore browser/session proof; fail closed when absent. |
| Tab still shows "not logged in" even though browser logged in. | Stale UI state, unrefreshed JS/SPA, or old request. | Re-check server session; fix UX refresh, never change security principal from JS. |
| RelayState valid yet signature fails. | Wrong SAML trust/key/issuer; separate from storage. | Check SAML provider validators, metadata, certificate rotation. |
| Spring returns 403 when IdP POSTs ACS. | Mismatched ACS path/filter chain/CSRF exclusion. | Compare metadata ACS and runtime matchers; never disable CSRF site-wide. |

**Debugging order:** (1) did the request enter the right filter → (2) was the cookie/browser session preserved → (3) does the repo hold the right pending ID/relay/registration → (4) what did the SAML provider validate → (5) was there a session persistence/rotation race → (6) which transaction owns the redirect target → (7) does business authorization permit the target resource.

### 13.1. Minimal Logs/Metrics

For production monitoring, suggested **custom metrics** (not built-in framework metrics):

~~~text
saml_pending_created_total{registration}
saml_pending_count_per_session_histogram
saml_pending_expired_total
saml_pending_not_found_total
saml_pending_browser_mismatch_total
saml_pending_inresponse_to_mismatch_total
saml_pending_replay_total
saml_multitab_concurrent_callback_total
saml_auth_session_rotation_conflict_total
saml_return_route_fallback_total
saml_pending_store_latency
~~~

For audit logs, record `correlationId`, configured registration, shortened/hashed requestId, node, error category, UTC timestamp, and pending count. Avoid logging full `SAMLRequest`, `SAMLResponse`, NameIDs, session cookies, assertions, private keys, or RelayStates holding sensitive data. In particular, when cookies are missing due to `SameSite`, **never log raw cookies** for "quick debugging".

## 14. Common Bad Fixes

1. **"Keep only the newest AuthnRequest; treat older responses as new logins."** Wrong: never skip `InResponseTo`; maintain per-transaction state or an explicit single-flight policy.
2. **"Put every AuthnRequest in Redis keyed by RelayState and you're done."** Wrong: without browser binding, this can open login CSRF/session swapping.
3. **"Each tab with a `tabId` is an independent session."** Wrong: tabs sharing cookies share `HttpSession`/SecurityContext.
4. **"Having the right RelayState means the XML is verified."** Wrong: RelayState is neither a signature nor a credential.
5. **"Response-A matches request-B because it's the same user."** Wrong: `InResponseTo` must match the issued AuthnRequest's exact ID.
6. **"Allow reusing a pending entry if a POST retry fails."** Wrong: enforce single-use/idempotency and assertion replay protection.
7. **"When B succeeds, wipe all pending entries including A silently."** Wrong if the product supports multi-request flows; define clear policy and sensible UX notices.
8. **"Let the browser decide the post-login return URL."** Wrong: risks open redirects; use server-side safe routes per transaction.
9. **"Turn off SameSite/CSRF/session fixation to make things easy."** Wrong: pick properly scoped cookie settings and ACS exclusions while keeping CSRF and fixation defenses.
10. **"Sticky sessions mean no shared state is needed."** Wrong: fails on failover and does not stop two requests overwriting each other on the same node.
11. **"Whichever callback arrives last gets to switch the user."** Wrong: enforce an explicit account-switch policy, especially across different IdPs/tenants.
12. **"If A expired, accept B with a similar ID."** Wrong: IDs and RelayState are strictly per-transaction with no fallback guessing.
13. **"Unit-testing `Map<RelayState, Request>` is enough."** Wrong: must test Spring filters/converters/providers, cookies, proxies, and two nodes.
14. **"After logout, old pending entries can still succeed."** Wrong: bind pending entries to session generation/revocation policies.
15. **"Lax session cookies always accompany SAML POSTs."** Wrong: many cross-site POSTs omit Lax cookies; test in real browsers.

## 15. Production Design Checklist

1. Are **browser HTTP session**, UI tab, each AuthnRequest, and SecurityContext clearly distinguished?
2. Are **separate request ID + opaque RelayState** generated per transaction, keeping RelayState ≤80 bytes?
3. Can the repository hold **multiple pending entries** in the same browser session without overwriting?
4. Do lookup/consumption **bind to browser session**, registration, issuer, ACS, and exact `InResponseTo`?
5. Are **TTLs, pending caps, cleanup, atomic consumption, and replay protection** enforced?
6. Is silently downgrading SP-initiated flows to IdP-initiated on lost pending entries prohibited?
7. Are return routes controlled per transaction with open redirects blocked?
8. Was SameSite tested in real browsers when the IdP sends HTTP-POST to the ACS?
9. Are session fixation rotation and multiple concurrent callbacks writing SecurityContext accounted for?
10. Is there a policy when two callbacks carry different principals/IdPs/tenants in the same browser session?
11. Across multiple nodes/regions, does the shared store satisfy consistency and fail-closed on failover?
12. On logout/account revocation, are pending entries for the old session canceled per policy?
13. Are out-of-order, duplicate, timed-out, wrong-browser/issuer, concurrent-tab, and IdP-error cases tested?
14. Are logs/metrics safe, never leaking assertions, cookies, SAMLResponses, or personal data?

## 16. Knowledge Self-Check

1. **Do two same-origin tabs usually have two different `JSESSIONID`s?** — No; they normally share cookies/the SP HTTP session within the same browser profile.
2. **Why do multiple AuthnRequests cause `InResponseTo` errors?** — If the repository stores only one request per session, a later request overwrites an earlier one.
3. **Should you store one or multiple pending entries when supporting multiple tabs?** — Multiple pending entries keyed by **transaction ID/RelayState** with browser binding; or deliberate single-flight login coordination.
4. **Can you use RelayState alone to look up a global cache and accept the response?** — No; that lacks proof the callback belongs to the initiating browser.
5. **Does Response-B arriving before Response-A invalidate A?** — Not necessarily in a multi-transaction store; however, session generation and security policies may still block A.
6. **What is `InResponseTo` compared against?** — The `AuthnRequest@ID` of the exact initiating transaction.
7. **If `SameSite=Strict` drops the cookie at the ACS, is dropping session binding okay?** — No; an alternative browser-proof mechanism is needed, or fail safely.
8. **Can two callbacks in the same session for different users silently follow last-wins?** — No; an explicit account-switching policy is required.
9. **Why might `SavedRequest` send Tab A to Tab B's page?** — Because the return target may be shared state inside HttpSession.
10. **Once pending A is consumed, can SAMLResponse A be reused?** — No; single-use consumption and assertion replay protection are required.
11. **Why not disable session fixation protection to stop cookies from rotating?** — Because that weakens session security; instead, design handling for session rotation/concurrency.
12. **If the user already logged out and stale Response-A arrives late, should re-login be allowed?** — Enforce session generation/revocation policy; never resurrect a terminated session.

## References

- [Spring Security — Producing AuthnRequests; HttpSessionSaml2AuthenticationRequestRepository and CacheSaml2AuthenticationRequestRepository](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML Responses and Saml2AuthenticationTokenConverter](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security API — Saml2AuthenticationRequestRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationRequestRepository.html)
- [Spring Security API — HttpSessionSaml2AuthenticationRequestRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/HttpSessionSaml2AuthenticationRequestRepository.html)
- [Spring Security API — CacheSaml2AuthenticationRequestRepository (6.5+)](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/CacheSaml2AuthenticationRequestRepository.html)
- [Spring Security — Authentication Persistence and SecurityContextRepository](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Session Management / Session Fixation Protection](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security GitHub #14793 — Multi-tab SAML request overwrite case, design tradeoffs](https://github.com/spring-projects/spring-security/issues/14793)
- [OASIS SAML 2.0 Profiles — Web Browser SSO, InResponseTo, SubjectConfirmation](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
- [OASIS SAML 2.0 Bindings — RelayState and HTTP-POST/Redirect](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf)
