# Limiting RelayState and Preventing Redirects to Untrusted Addresses

In **SAML 2.0 Web Browser SSO**, the Service Provider (SP) sends an `AuthnRequest` to the Identity Provider (IdP), the browser passes through the IdP login page and returns to the SP's Assertion Consumer Service (ACS) with a `SAMLResponse`. The SP often wants to remember which resource the user was trying to access before login so it can return them to the right page. SAML supports passing a **`RelayState`** value alongside the message to preserve this state.

The problem: a browser can send, alter, or replay `RelayState`. If the SP interprets it as a URL and redirects unchecked, a trusted login path can become an **open redirect** leading to a phishing site. If the SP relies solely on RelayState to decide which browser owns a transaction, an attacker can also cause **login CSRF/session swapping**. Therefore, this article explains **size limits**, **integrity protection and transaction correlation**, and **safe redirect target decision rules** together when customizing AuthnRequests in Spring Security.

## 1. What Is RelayState Really?

`RelayState` is a **SAML binding parameter** (e.g., HTTP-Redirect or HTTP-POST), **not** an attribute inside `AuthnRequest` or `Assertion`, and **not** a signature, access token, or authentication evidence. It is data the transaction initiator wants carried across the intermediate step, typically used for:

- Identifying a **pending authentication transaction** stored at the SP.
- Restoring navigation context, such as the reports page the user intended to view.
- Maintaining a short correlation key for application state already stored securely server-side.

If a request with `RelayState` is sent over a binding supporting this mechanism, the SAML responder should use a RelayState-capable binding for the response and **echo back the exact value received, unmodified**. Responsibility for **interpreting** that value and deciding redirects rests with the recipient per its own policy.

~~~text
Browser                    SP                       IdP
    |                       |                         |
    | GET /reports          |                         |
    |---------------------->|                         |
    |                       | store state:            |
    |                       |  handle -> /reports     |
    |                       |  session, requestId, TTL|
    |                       |                         |
    |<-- Redirect to IdP ---|                         |
    |    SAMLRequest=...    |                         |
    |    RelayState=H...    |                         |
    |-----------------------------------------------> |
    |                       |                    authenticate
    |<----------------------------------------------- |
    | form POST SAMLResponse=..., RelayState=H...     |
    |                       |                         |
    | POST to ACS           |                         |
    |---------------------->|                         |
    |                       | verify SAMLResponse,    |
    |                       | InResponseTo, session,  |
    |                       | then consume handle     |
    |<--- 302 /reports -----|                         |
~~~

In this model, **`H...` is only a random reference token**; the `/reports` URL resides in state already validated on the SP side. There is no arbitrary URL inside RelayState for a third party to substitute.

### 1.1. How Does RelayState Differ from InResponseTo and Session?

| Component | What Is It Used For? | What Does It Not Guarantee by Itself? |
| --- | --- | --- |
| `RelayState` | Carries a state value/reference key through the IdP and back to the SP. | Does not verify identity; does not prove the browser initiated login. |
| `AuthnRequest@ID` | Identifies the request created by the SP. | Does not authorize redirecting to a URL. |
| `Response@InResponseTo`, bearer `SubjectConfirmationData@InResponseTo` | Correlates response/assertion with the issued AuthnRequest. | Does not replace binding the pending request to the browser session. |
| SP's `HttpOnly`/`Secure` session cookie | Tells the SP which browser session is performing the callback. | Does not substitute for verifying SAMLResponse signature/audience/issuer. |
| Verified `SAMLResponse` | Lets the SP trust the authentication outcome and establish a principal. | Does not permit trusting arbitrary redirect targets from URLs/forms. |

**Invariant:** the SP restores the navigation destination only after it has **verified the SAML response**, **bound it to a transaction belonging to this session**, and **validated that destination against policy**. Never substitute `RelayState` for any of those steps.

## 2. The 80-Byte Limit on RelayState

The **OASIS SAML 2.0 Bindings** specification, in the `RelayState` sections for **HTTP-Redirect (3.4.3)** and **HTTP-POST (3.5.3)**, sets the limit **MUST NOT exceed 80 bytes**. This is **80 bytes**, not 80 Unicode characters, not 80 Java `String.length()` characters, and not an 80-byte limit for the whole SAMLRequest/SAMLResponse.

Examples:

| Value | Length to Watch | Remarks |
| --- | --- | --- |
| 24 random bytes encoded as **unpadded Base64URL** | **32 ASCII characters = 32 UTF-8 bytes**. | Short, unpredictable; suitable as a handle. |
| 32 random bytes encoded as unpadded Base64URL | **43 ASCII characters = 43 bytes**. | Still well under 80 bytes. |
| Full URL `https://sp.example.org/reports?... ` | Depends on total byte count of the string. | Easily exceeds 80 bytes; also risks open redirect and data leakage. |
| String containing Vietnamese diacritics, emoji | Contains multi-byte UTF-8 characters. | `String.length()` is insufficient to measure transmitted bytes. |

In Java, when measuring UTF-8 byte length, use:

~~~java
int bytes = relayState.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length;
if (bytes > 80) {
    throw new IllegalArgumentException("RelayState exceeds 80 bytes");
}
~~~

The example above illustrates only the length calculation, as a **code snippet inside a method**. When implementing a specific binding, you also need to understand wire encoding/decoding rules; the limit must be checked consistently on the **chosen RelayState value**, without confusing it with the URL-encoded length of the entire HTTP query.

**Do not rely on a current IdP accepting values longer than 80 bytes** as spec-compliant behavior. Some products have interoperability exceptions, whereas others may warn, truncate, or reject. To build a portable and easily testable SP, keep RelayState **well below the limit**, such as a 32- or 43-byte Base64URL handle.

### 2.1. Do Not Put Full URLs or Session Data in RelayState

Avoid stuffing data like the following into RelayState:

- Absolute addresses to the page the user will visit, especially URLs to third-party hosts.
- JSON containing user ID, tenant, groups, permissions, profile, cookies, tokens, passwords, email, or sensitive info.
- Very long routing payloads, many query parameters, long self-issued JWTs, or an entire saved request.
- Values that could leak via browser history, proxy logs, Referer, IdP records, or monitoring systems.

RelayState passes through the browser and partner, so **never treat it as secret**. If you need to store multiple context fields, store them in a server-side session/cache with TTL and put only a **random opaque handle** in RelayState.

## 3. Integrity Protection: Exact Echoing Is Not Enough

According to OASIS Bindings, RelayState **should be integrity-protected**. Errata clarifies that with **HTTP-Redirect**, when a binding query-string signature is present, the signature covers the exact sequence of `SAMLRequest` or `SAMLResponse`, `RelayState`, and `SigAlg` in the prescribed order. With **HTTP-POST**, the XML signature of SAMLResponse **does not automatically** sign the `RelayState` form parameter outside the XML; independent protection is needed if that value is used.

Common safe options:

1. **Opaque random handle + server-side stored state**: handle with sufficient randomness, unique per transaction, short TTL, single-use. This is the simplest and usually easiest-to-control option.
2. **MAC/signature on a self-contained value**: if forced to transmit state client-side, use a MAC/signature from an SP-managed key, with expiration, audience/tenant, transaction/session binding, and format version. After Base64URL encoding, ensure total bytes still fit under the limit; sensitive data may require encryption, making this more complex.
3. **Protection at the binding layer**: when using signed HTTP-Redirect, properly verify the query signature covering RelayState per spec; you must still validate the **redirect target** and **browser session** separately.

**A plain unkeyed hash** does not prove origin; an attacker can compute hashes for new values. **HTTPS** protects transit between hops but does not make browser/partner-supplied input unconditionally trustworthy. Likewise, never assume a valid SAMLResponse signature already protects the RelayState value.

### 3.1. Limiting Replay

The same handle must not grant redirect or new login rights infinitely many times. State requires:

- **Creation timestamp and expiration**, e.g., a few minutes' TTL matching SSO timeout.
- **Session binding**: the handle must belong to the browser session that initiated the AuthnRequest.
- **Request binding**: bound to the AuthnRequest ID, IdP/registration, and correlation values verified in SAMLResponse.
- **Single use**: consumed once atomically; concurrent callbacks must not both succeed.
- **Cleanup**: purge expired pending transactions to prevent cache bloat and state leaks.

Use Spring Security's `Saml2AuthenticationRequestRepository` to preserve AuthnRequest linkage. **Do not build custom authorization or authentication solely from the handle**: the handle only assists transaction and navigation management.

## 4. Open Redirect: Why RelayState Is Dangerous When Turned into a URL

An **open redirect** occurs when a legitimate application sends the browser to an externally controlled destination without an allowlist policy. Example of a flawed design:

~~~text
GET /saml2/authenticate/corporate?returnUrl=https://attacker.example/phishing

SP puts returnUrl into RelayState.
IdP logs in user then echoes RelayState.
After callback, SP executes:
  sendRedirect(request.getParameter("RelayState"));
~~~

An attacker can lure a victim to a URL on the SP's real domain to begin login, then redirect them to a spoofed site afterward. Harms include **phishing**, bypassing domain checks, abusing login flows, leaking tokens/codes in misconfigured integrations, and complicating session defense.

**Never pass `RelayState` directly into `sendRedirect`, `RedirectStrategy.sendRedirect`, the `Location` header, or Spring MVC's `redirect:`** without policy enforcement and state verification.

### 4.1. Strings to Reject When Allowing Only Internal Redirects

| Untrusted Input | Risk |
| --- | --- |
| `https://attacker.example/login` | Absolute URL to a different domain. |
| `http://attacker.example/` | Sends users to an untrusted site and may downgrade HTTPS. |
| `//attacker.example/login` | *Protocol-relative* URL; browser uses the current scheme with an external host. |
| `javascript:alert(1)` | Scheme can lead to code execution in unsafe handling contexts. |
| `data:text/html,...` | Scheme leads to an attacker-controlled document. |
| `https://trusted.example.attacker.example/` | Naive `startsWith("https://trusted.example")` host check is bypassed. |
| `https://trusted.example@attacker.example/` | Uses `userinfo@` to make the URL look like a trusted host. |
| `/\\attacker.example/` or `\\attacker.example` | Backslashes may be interpreted inconsistently by browsers/proxies. |
| `%2f%2fattacker.example` or double-encoded strings | Slashes decoded once or multiple times alter URL interpretation. |
| `/app/../admin` | Path normalization can escape permitted route boundaries. |
| CR/LF, tabs, control characters, `%0d%0a` | Risk of header injection, parser differentials, or validator bypass. |

These are **input families to guard against**, not a claim that every Java servlet handles them identically. Java parsers, reverse proxies, and browsers normalize differently, so **test at the actual redirect point**, after your system's exact decoding and normalization order.

### 4.2. Best Allowlist Model: Route ID → Fixed Internal Path

Instead of arbitrary URLs, store a **route ID** on the server:

| Accepted Route ID | Server-Chosen Path |
| --- | --- |
| `dashboard` | `/dashboard` |
| `reports` | `/reports` |
| `profile` | `/profile` |
| Any other value | `/dashboard` (safe fallback) |

Advantage: **no need to parse user-supplied URLs**, while also avoiding hostname parsing and URL-encoding ambiguities. When deep linking is needed, store a **validated resource ID** and generate the path from a safe route template. For example, route `report` and a valid numeric ID resolve to `/reports/42` after checking user authorization.

If the product genuinely must redirect to a **partner domain**, maintain a strict allowlist of **HTTPS scheme, canonicalized hostname, port, and purpose-specific path**; compare using a trusted URI/URL parser on the hostname component, never `startsWith`, `contains`, or simple suffixes. Handle IDN/punycode, mixed case, trailing dots, `@` credentials, backslashes, and multiple decoding passes consistently. Redirecting to an external domain must be a separately governed decision, potentially showing confirmation; never treat arbitrary URLs carried in RelayState as valid.

## 5. Secure Design Pattern for SP-Initiated Login

### 5.1. Before Redirecting to the IdP

1. User tries to open `/reports`; SP determines it is a valid internal resource and records the route in **unauthenticated** session state.
2. SP builds an `AuthnRequest` with a unique ID and selects a trusted `RelyingPartyRegistration`.
3. SP generates a **random RelayState** (e.g., 24 random bytes → 32-character Base64URL).
4. Store a server-side record with `handle`, `AuthnRequest ID`, `registrationId`, browser session, internal route, expiration time, and consumed flag.
5. SP sends `AuthnRequest` and RelayState to the IdP via the configured binding. Never place external target URLs in SAMLRequest or RelayState for automatic redirecting.

### 5.2. When SAMLResponse Returns to the ACS

1. Read `SAMLResponse` and RelayState from the form through the configured SAML processor. **Never grant a session just because a form POST arrived.**
2. Verify signature, issuer, `Destination`/ACS, `AudienceRestriction`, Conditions, `SubjectConfirmation`, response status, and replay protection.
3. For SP-initiated login, match `InResponseTo` against the **pending AuthnRequest of that exact browser session**. Confirm the IdP/registration matches the transaction.
4. Validate RelayState format, byte length, handle existence, TTL, and session/request binding; **consume once atomically**.
5. Once authentication succeeds and the application account is permitted to operate, choose the destination from the **SP-side stored and validated route**, not from callback parameters.
6. If the route is invalid, expired, or permissions were revoked, redirect to a **fixed same-origin fallback path**, such as `/dashboard`, or return an error/re-login prompt depending on the error.
7. Enforce authorization on the target page: `/reports` still checks tenant, role, and data permissions. A successful redirect **does not prove** permission to view the resource.

**Verification order matters:** if the SAMLResponse is forged or invalid, **never use** RelayState to establish a successful login or open sensitive resources. Return a fixed safe error page; never send users externally just because RelayState holds a plausible URL.

## 6. Java 17: Short Handle, Session Binding, TTL, and Redirect Allowlist Example

The standalone runnable example below simulates **the SP's RelayState and return-route management**, not a SAML processor. It **does not verify signatures, issuer, audience, `InResponseTo`, or create a Spring Authentication**. In a real app, invoke destination restoration only after the SAML library authenticates the Response, and obtain the session ID from a trusted cookie/HttpSession rather than **a user-submitted parameter**.

File `RelayStateDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class RelayStateDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String FALLBACK = "/dashboard";
    private static final ConcurrentMap<String, Pending> STORE =
            new ConcurrentHashMap<>();

    private record Pending(String browserSession, String returnPath,
                           Instant expiresAt) {}

    private static String allowedRoute(String route) {
        if (route == null) {
            return FALLBACK;
        }
        return switch (route) {
            case "reports" -> "/reports";
            case "profile" -> "/profile";
            default -> FALLBACK;
        };
    }

    static String begin(String browserSession, String route, Instant now) {
        byte[] randomBytes = new byte[24];
        RANDOM.nextBytes(randomBytes);
        String handle = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(randomBytes);
        STORE.put(handle, new Pending(
                browserSession, allowedRoute(route), now.plusSeconds(180)));
        return handle;
    }

    static String finish(String browserSession, String relayState,
                         Instant now) {
        if (relayState == null ||
                relayState.getBytes(StandardCharsets.UTF_8).length > 80) {
            return FALLBACK;
        }

        Pending pending = STORE.get(relayState);
        if (pending == null ||
                !pending.browserSession().equals(browserSession) ||
                !now.isBefore(pending.expiresAt())) {
            return FALLBACK;
        }

        // remove(key, value) ensures concurrent callbacks consume only once.
        return STORE.remove(relayState, pending)
                ? pending.returnPath()
                : FALLBACK;
    }

    public static void main(String[] args) {
        Instant t0 = Instant.parse("2026-11-07T03:00:00Z");
        String handle = begin("session-A", "reports", t0);

        System.out.println(
                handle.getBytes(StandardCharsets.UTF_8).length);
        System.out.println(finish(
                "session-B", handle, t0.plusSeconds(1)));
        System.out.println(finish(
                "session-A", handle, t0.plusSeconds(2)));
        System.out.println(finish(
                "session-A", handle, t0.plusSeconds(3)));

        String malicious = begin(
                "session-A", "https://attacker.example/", t0);
        System.out.println(finish(
                "session-A", malicious, t0.plusSeconds(4)));

        String expired = begin("session-A", "profile", t0);
        System.out.println(finish(
                "session-A", expired, t0.plusSeconds(181)));
    }
}
~~~

Compile/run with Java 17 or later:

~~~bash
javac RelayStateDemo.java
java RelayStateDemo
~~~

**Deterministic** output, independent of specific random values:

~~~text
32
/dashboard
/reports
/dashboard
/dashboard
/dashboard
~~~

Line-by-line explanation:

1. 24 random bytes encoded as unpadded Base64URL yield **32 ASCII bytes**, below SAML's 80-byte limit.
2. A handle from **session-A** does not let **session-B** retrieve the route.
3. First use in session-A before TTL retrieves `/reports`.
4. Reusing an already consumed handle returns the fallback.
5. An unallowlisted route (`https://attacker.example/`) is sanitized to the fallback **at state creation time**, preventing open redirects.
6. A handle expired after 180 seconds is rejected.

**Limitations of the demo:** `ConcurrentHashMap` works in a single process only and does not evict expired entries automatically; production needs a cache with TTL/eviction, capacity limits, multi-node support, and atomic consumption. The demo binds handles to a simulated session string, whereas production must also bind `AuthnRequest ID`, IdP registration, `InResponseTo` matching, and library SAML checks. Also avoid using a single session ID alone as the key if the app must support multiple concurrent SSO tabs; each transaction needs its own handle.

## 7. Configuring with Spring Security SAML 2.0

Spring Security Servlet provides built-in components to reduce manual transaction management:

- **`Saml2WebSsoAuthenticationRequestFilter`**: creates/sends AuthnRequest to the IdP.
- **`Saml2AuthenticationRequestResolver`**: determines AuthnRequest config and data, including RelayState via the version-appropriate resolver mechanism.
- **`Saml2AuthenticationRequestRepository`**: stores pending requests. Default is typically **`HttpSessionSaml2AuthenticationRequestRepository`**, providing browser-session binding.
- **`Saml2WebSsoAuthenticationFilter`** and converter: receive SAMLResponse and fetch request/registration info for the authentication provider.
- **OpenSAML authentication provider**: verifies Response/assertion before issuing `Saml2Authentication`.
- **Authentication success handler**: decides where the user goes after successful authentication.

### 7.1. Choosing the Safest Easy Option: Keep Defaults and a Fixed Target

If the business only needs users returned to a dashboard without deep-link preservation, use a **success handler with a fixed same-application path**. Configuration example in a Spring Boot project with `spring-security-saml2-service-provider` and valid IdP registrations:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SafeSamlLoginConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml.successHandler(
                (request, response, authentication) ->
                    response.sendRedirect(
                        request.getContextPath() + "/dashboard")));
        return http.build();
    }
}
~~~

This is **Spring Boot configuration code, not standalone-compilable with `javac`** without dependencies and real registrations. This configuration redirects logged-in users to the app's own `/dashboard`; it never reads `returnUrl`, `RelayState`, or `Referer` from the callback to choose the destination. `/dashboard` must still have an endpoint and proper authorization checks.

If you want to return users to their initial **saved request**, you can retain the default `SavedRequestAwareAuthenticationSuccessHandler` when appropriate; the saved request must belong to a trusted session and proxy HTTP host/forwarded headers must be configured accurately. Do not carelessly enable `targetUrlParameter` or `useReferer`: they can take destinations from untrusted parameters/headers.

### 7.2. Customizing RelayState in the AuthnRequest Resolver

**Example specific to Spring Security 6.x with OpenSAML 4** (check your exact version before use). `OpenSaml4AuthenticationRequestResolver` provides **`setRelayStateResolver`** to generate RelayState; this example only customizes **how the handle is created**, without putting a URL directly in the parameter.

File `src/main/java/example/federation/SamlRelayStateResolverConfig.java`:

~~~java
package example.federation;

import java.security.SecureRandom;
import java.util.Base64;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml4AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;

@Configuration
public class SamlRelayStateResolverConfig {

    private static final SecureRandom RANDOM = new SecureRandom();

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {
        RelyingPartyRegistrationResolver relyingParties =
                new DefaultRelyingPartyRegistrationResolver(registrations);
        OpenSaml4AuthenticationRequestResolver resolver =
                new OpenSaml4AuthenticationRequestResolver(relyingParties);

        resolver.setRelayStateResolver(request -> {
            byte[] randomBytes = new byte[24];
            RANDOM.nextBytes(randomBytes);
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(randomBytes);
        });
        return resolver;
    }
}
~~~

`24` random bytes equal 192 bits of entropy; the unpadded Base64URL value is **32 ASCII bytes**, comfortably within the RelayState limit. Spring Security still needs to store `AbstractSaml2AuthenticationRequest` in the repository and validate the matching callback; **do not assume** that replacing the resolver as above automatically implements return-path mapping, extra session binding, TTL, or custom redirect logic.

If storing state keyed by handle in a separate cache, connect it consistently with the AuthnRequest in the repository and session/trust model. A **`CacheSaml2AuthenticationRequestRepository` looking up by RelayState** can aid multi-node deployments yet loses session binding if transactions are retrieved solely by public handle: official Spring Security docs warn of login fixation risks when trusting RelayState/`InResponseTo` without knowing which browser initiated login. You must add session binding or an equivalent design rather than treating a handle-keyed cache as sole proof.

**Version note:** in Spring Security 7.x, class/constructor names or OpenSAML configuration may differ (e.g., using `OpenSaml5AuthenticationRequestResolver`). Do not copy OpenSAML 4 code into a newer release assuming it compiles; use the official API matching your deployed dependencies.

### 7.3. If Deep-Link Redirects Are Required

A safer approach than raw `RelayState` is:

1. When starting SSO, receive `/reports/42` and verify it is a **storable internal route**; if it contains an ID, validate/type-check the ID.
2. Store that route in the session or a session-bound pending login store, alongside `AuthnRequest ID`, registration, TTL, and handle.
3. Keep Spring Security's `Saml2AuthenticationRequestRepository`/correlation and validators intact.
4. After `Saml2Authentication` is created successfully, the success handler reads the route only from the **validly consumed server-side state**.
5. If no valid state exists or the route is no longer permitted, use an internal fallback or fail explicitly.
6. When the user lands on the reports page, verify **authorization** for report 42 and tenant before rendering.

Even with a random handle and valid session, **never accept an unvalidated return path just because it was stored in the session**. If the SP previously saved an attacker-supplied `returnUrl` without validation, “storing on the server” merely delays the open redirect.

## 8. Special Contexts

### 8.1. IdP-Initiated / Unsolicited SSO

When the IdP proactively emits a SAMLResponse without a prior SP AuthnRequest, there may be **no** SP-initiated RelayState or `InResponseTo` to correlate against. If the product supports IdP-initiated SSO, establish a dedicated policy: verify full signature/issuer/audience/recipient/validity window, decide explicitly whether unsolicited login is permitted, and redirect only to a **fixed destination/SP-managed allowlist**. Never use a RelayState containing an IdP/browser-supplied URL to grant arbitrary redirects.

If SP-initiated correlation fails, **never silently downgrade** to IdP-initiated just to let login succeed.

### 8.2. Multiple IdPs or Multiple Tenants

Each pending login must know its `registrationId`, IdP entityID, SP entityID, ACS, and verified tenant context. A handle from IdP A must never complete a session for IdP B or another tenant. Do not select an IdP trust anchor/certificate based on an unverified issuer/tenant string in RelayState. Switching IdPs mid-login requires a new SSO transaction under the right registration.

### 8.3. Reverse Proxies, SameSite Cookies, and Multiple Instances

When an IdP POSTs cross-site to the ACS, the SP's cookie can be blocked under `SameSite` policy. This causes the pending request in `HttpSession` to be lost. Design cookies/sessions properly with HTTPS, `Secure`, `HttpOnly`, `SameSite` policy, and trusted reverse proxy settings.

If a distributed cache is used, preserve **browser session binding + transaction + TTL + single-use** via a reliable mechanism. Do not disable `InResponseTo`/session verification just because a callback hits another node. On success, avoid redirecting to URLs containing internal hostnames or hosts taken from uncontrolled `Host`/forwarded headers.

### 8.4. Logging and Data Security

Log only internal correlation IDs (optionally hashed/masked), error categories, timestamps, and configured registrations. Never log raw `SAMLResponse`, assertions, cookies, secrets, routes containing sensitive data, or full RelayState values carrying personal info. To investigate 80-byte errors, log the **byte count**, binding type, and active endpoint instead of printing the entire RelayState string.

## 9. Mandatory Security Tests for RelayState

| Scenario | Expected Result |
| --- | --- |
| 32-byte ASCII handle, valid SAML request, matching session and AuthnRequest. | Login accepted and redirected to the stored internal route. |
| RelayState exceeds 80 bytes. | Rejected / never emitted by the system per spec; clear error without arbitrary truncation. |
| RelayState has Unicode, Java String length under 80 chars yet UTF-8 exceeds 80 bytes. | Checked by **byte count**; rejected when exceeding binding limit. |
| Callback from a different session with the same handle. | Handle cannot be used to redirect or establish login for the other session. |
| Replaying the same handle after consumption. | Rejected without recreating state. |
| RelayState altered by 1 character despite valid SAMLResponse signature. | Fails state lookup or integrity check; never used as a URL. |
| `RelayState=https://attacker.example/`. | No external redirect; fallback or error. |
| `RelayState=//attacker.example/` or `javascript:...`. | Rejected as redirect destination. |
| `https://trusted.example.attacker.example/` / `userinfo@` URLs. | Blocked by strict hostname allowlist. |
| Percent-encoded/double-encoded and backslash payloads. | Does not bypass validation after browser/proxy normalization. |
| RelayState/return URL missing or past TTL. | Uses safe fallback route; if SAML transaction is lost, authentication fails. |
| `InResponseTo` mismatches AuthnRequest in the same session. | Login rejected even if RelayState exists. |
| Route `/reports/42` valid, yet user lacks permission for report 42. | May reach destination, yet **authorization denies data access**. |
| IdP-initiated SSO with no pending request. | Applies dedicated unsolicited policy; never trusts external URLs via RelayState. |

Clearly separate **authentication tests** (signature, IdP, audience, InResponseTo, replay), **state tests** (byte length, TTL, session, single-use), and **redirect target tests** (internal route/allowlist, parser/canonicalization). Passing one group does not prove the other two are safe.

## 10. Common Mistakes and Fixes

| Wrong Approach | Why It Is Dangerous | Right Approach |
| --- | --- | --- |
| Setting RelayState to an absolute URL from `returnUrl`. | Easily exceeds 80 bytes and enables open redirects. | Opaque handle; store allowlisted internal route server-side. |
| Checking `relayState.length() <= 80`. | Java code-unit count does not equal UTF-8 byte count. | Count bytes per binding encoding; keep handles short ASCII. |
| `sendRedirect(request.getParameter("RelayState"))`. | Users can alter the redirect destination themselves. | Redirect only to a route ID/target derived from trusted state. |
| Checking `url.startsWith("https://trusted.example")`. | Spoofed host `trusted.example.attacker.example` bypasses it. | Parse and match canonical scheme/host/port, or use an internal route allowlist. |
| Assuming XML signatures protect RelayState. | RelayState sits outside XML; protection depends on binding/design. | Protect integrity independently or use opaque handle; verify binding signature when present. |
| Looking up cache by RelayState alone and treating callback as valid. | Unknown whether this browser initiated the AuthnRequest. | Bind transaction to browser session, verify InResponseTo, and consume once. |
| Disabling `InResponseTo` checks because SameSite dropped the cookie. | Opens login CSRF/session swapping vulnerabilities. | Fix session/cookies and correlation store per SSO requirements. |
| Trusting arbitrary `targetUrlParameter`/Referer URLs after login. | Can cause open redirects or route to unintended pages. | Fixed success handler, trusted saved request, or vetted allowlist. |
| Accepting any RelayState on IdP-initiated login. | Lacks originating transaction and risks external redirects. | Dedicated policy, fixed/allowlisted redirect, restrict unsolicited SSO. |
| Storing tokens/PII inside RelayState. | RelayState traverses browsers, IdPs, proxies, and logs. | Transmit only a short handle; protect state on the server. |

## 11. Checklist for Real-World Integration

1. **Scope:** decide whether your system uses RelayState for correlation, routing, or both; never make it a freeform redirect URL.
2. **Capacity:** enforce a 80-byte maximum per SAML HTTP bindings; prefer 32- or 43-byte ASCII Base64URL handles.
3. **Integrity:** use random handles bound to server-side state or proper MAC/signatures; verify protection per Redirect/POST binding.
4. **Session:** prove request and response belong to the same browser session, registration, and `AuthnRequest`; never look up by RelayState alone.
5. **Lifecycle:** short TTL, single-use atomic consumption, cleanup, and controlled multi-tab/multi-node handling.
6. **SAML:** verify signature, issuer, status, destination, audience, conditions, subject confirmation, `InResponseTo`, and replay.
7. **Redirects:** allow fixed internal routes or very narrow origin/URI allowlists; reject protocol-relative URLs, exotic schemes, spoofed hosts, double-encoding, and control characters.
8. **Spring Security:** retain `Saml2AuthenticationRequestRepository` and OpenSAML validators; customize resolvers/success handlers only at version-supported extension points.
9. **Authorization:** enforce business permissions when accessing the destination; never treat SAML login as authorization for every resource.
10. **Monitoring:** log error reasons and RelayState byte lengths safely without tokens/PII; test real browsers, SameSite cookies, proxies, and different IdPs.

## 12. Knowledge Self-Check

1. **Is the RelayState limit 80 characters or 80 bytes?** — **80 bytes** under SAML Bindings HTTP-Redirect and HTTP-POST rules.
2. **If the IdP echoes RelayState verbatim, can you put it straight into HTTP Location?** — **No**; echoing validates neither redirect safety nor session origin.
3. **How long is unpadded Base64URL of 24 random bytes?** — **32 ASCII characters / 32 bytes**.
4. **Is RelayState part of the XML Signature on SAMLResponse?** — **Not by default**; it is a binding parameter protected separately by binding/design.
5. **Does looking up cache solely by `InResponseTo` or RelayState prove the callback came from the same browser?** — **No**; session binding or an equivalent proof mechanism is required.
6. **Is `//attacker.example` a harmless local path?** — **No**; it can act as a protocol-relative URL to an external host.
7. **Why store `reports` instead of an arbitrary URL in state?** — Because the server can map the route ID to a fixed permitted path and prevent open redirects.
8. **Does a valid SAML login permit viewing every report?** — **No**; resource/tenant permissions must be checked independently.

## References

- [OASIS — SAML 2.0 Bindings, RelayState (HTTP-Redirect §3.4.3, HTTP-POST §3.5.3)](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf)
- [OASIS — SAML 2.0 Errata 05, RelayState protection and URL/CSRF/XSS warnings](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html)
- [OASIS — SAML 2.0 Web Browser SSO Profile](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
- [Spring Security — Producing AuthnRequests, RelayState and AuthenticationRequestRepository](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security API 6.3.5 — OpenSaml4AuthenticationRequestResolver.setRelayStateResolver](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.html)
- [Spring Security API — AbstractAuthenticationTargetUrlRequestHandler, controlling redirect targets](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationTargetUrlRequestHandler.html)
