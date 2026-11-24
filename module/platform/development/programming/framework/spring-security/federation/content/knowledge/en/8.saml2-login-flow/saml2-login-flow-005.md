# RelayState and Restoring the Target Destination After SAML 2.0 Login

## 1. Why Remember the Target Destination?

A user directly opens a protected path, such as `https://app.example.org/portal/orders/42`, without an existing login session at the Service Provider (SP). Spring Security sends the browser to the Identity Provider (IdP) to log in. After the IdP authenticates the user and sends `SAMLResponse` back to the Assertion Consumer Service (ACS), the user expects to **return to order 42**, rather than always landing on the home page.

In SAML 2.0, **`RelayState`** is an optional parameter accompanying messages on browser bindings, allowing the transaction initiator to carry a context value across the SP → IdP → SP journey. In Spring Security Servlet, there is also the **`RequestCache` / `SavedRequest`** mechanism to remember the URL the user requested before being redirected to login. The two mechanisms are related yet **not identical**.

This lesson belongs to the **SAML2 Login Flow** topic of Spring Security federation. After completing it, you can:

- Explain accurately what `RelayState` is, how it appears in HTTP-Redirect/POST bindings, and when the IdP must echo the exact value back.
- Distinguish three states: **SAML protocol request correlation**, **RelayState**, and **the original target URL stored in RequestCache**.
- Trace SP-initiated SSO from the original resource URL, through `AuthnRequest`, IdP, and ACS, to post-login redirect.
- Use `SavedRequestAwareAuthenticationSuccessHandler` with Spring Security SAML 2.0 login on the Servlet stack.
- Handle direct visits to login, IdP-initiated login, session expiration, multiple tabs, or blocked cookies.
- Design safe target redirects preventing open redirects, login CSRF, and RelayState tampering; understand the specification's 80-**byte** length limit.
- Test a deep link properly and classify failures at the right layer.

Examples target **Java 17+ / Spring Boot 3.x / Spring Security 6.x, Servlet/MVC applications**. `.example.org` domains and identifier numbers in the lesson are illustrative. Spring Security APIs may change in newer releases; verify against documentation for your application's version.

## 2. Three Concepts Often Conflated into One

| Concept | What Does It Hold? | Who Creates and Stores/Checks It? | Goal |
| --- | --- | --- | --- |
| **`RelayState`** | Short opaque string accompanying `SAMLRequest`/`SAMLResponse` | Created by SP or IdP; used by receiver per agreement; IdP echoes exact value in SP-initiated flow | Preserve context/correlation across the browser round-trip |
| **`AuthnRequest ID / InResponseTo`** | SAML transaction ID, e.g., `_req123` in XML | SP issues request; SP checks matching value in Response and SubjectConfirmation per profile | Prevent mismatched responses/replay; bind response to request |
| **`SavedRequest` in RequestCache** | Original HTTP request data such as protected URL, method/headers depending on cache type | Spring Security at the **SP** saves on login trigger and reads after authentication | Restore the page the user intended to access |

**A RelayState can be a state-lookup key** without needing to embed the target URL. The SP can generate a random handle, store a server-side mapping to the original request, and receive that handle back via the IdP. In Spring Security's default setup, the original destination usually sits in **`HttpSessionRequestCache`**, while `AuthnRequest` is stored in **`HttpSessionSaml2AuthenticationRequestRepository`**; both often rely on the session, yet serve different purposes.

Do not assume:
- "Returning the right RelayState" means the user is authenticated.
- "A SavedRequest exists" means the SAML assertion has a valid signature.
- "Having `InResponseTo`" allows redirecting to any URL from the request.
- "RelayState always equals the original URL." That is just one design convention some systems use, not a SAML specification requirement.

## 3. How Is RelayState Carried Over HTTP?

In the **HTTP-Redirect binding**, the SP typically creates `AuthnRequest`, compresses it with DEFLATE, Base64-encodes, and URL-encodes it into the `SAMLRequest` parameter. `RelayState` travels in a **separate** query parameter:

~~~http
HTTP/1.1 302 Found
Location: https://idp.example.org/sso?SAMLRequest=COMPRESSED_BASE64_VALUE&RelayState=RANDOM_HANDLE
~~~

The browser sends a new GET to the IdP. When a Redirect-binding signature is present, the `RelayState` value is part of the signed query string alongside `SAMLRequest` and `SigAlg` per binding rules. However, without a valid binding signature, never assume RelayState has integrity merely because HTTPS is used.

In the **HTTP-POST binding**, the IdP typically returns an HTML form to the browser containing the Base64-encoded `SAMLResponse` and `RelayState` as another hidden input:

~~~html
<form method="post" action="https://app.example.org/login/saml2/sso/corp">
  <input type="hidden" name="SAMLResponse" value="BASE64_SAML_RESPONSE">
  <input type="hidden" name="RelayState" value="RANDOM_HANDLE">
  <button type="submit">Continue</button>
</form>
~~~

The browser sends:

~~~http
POST /login/saml2/sso/corp HTTP/1.1
Host: app.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=BASE64_SAML_RESPONSE&RelayState=RANDOM_HANDLE
~~~

The form above is purely illustrative and does not contain a signed Response. JavaScript auto-submitting the form is a browser detail; the SP never treats the form body as identity proof before **verifying the SAML Response and assertion**.

**Specification echo rule:** when a SAML request is accompanied by RelayState, the SAML responder must place the **exact value received** into the response's RelayState parameter over a binding that supports it. "Exact" means not interpreting or modifying the opaque content. If an IdP accepts the request yet drops RelayState on return, the SP may fail to reconnect context even if the SAML assertion itself is valid.

## 4. The 80-Byte Limit and Integrity

The SAML 2.0 HTTP-Redirect and HTTP-POST binding specs stipulate **RelayState must not exceed 80 bytes** (not 80 Unicode characters). In UTF-8, a single Vietnamese character can take multiple bytes. For interoperability, good practice is a **short ASCII random token** or an opaque reference.

Size examples:

| Value | Notes |
| --- | --- |
| `RANDOM_HANDLE` | Opaque, short, contains no URL or personal data |
| Base64url of 18 random bytes | 24 ASCII characters, i.e., 24 bytes, well under 80 bytes |
| `/portal/orders/42` | Valid in size, yet requires target policy and should not be trusted blindly |
| Long URL with query/filters | Can exceed 80 bytes, prone to IdP/vendor differences |
| Entire JWT/cookie/JSON user profile | Unsuitable: too long, leaks data, hard to prove integrity |

In practice some IdPs/SPs relax the limit for product reasons; integrating with them requires testing and agreeing on interoperability. **New designs should respect the 80-byte limit** and not rely on vendor leniency.

Integrity:
- With a properly signed **HTTP-Redirect binding**, the query signature covers RelayState per SAML 2.0 errata.
- With **HTTP-POST**, RelayState sits outside the signed XML body; **the XML signature on `SAMLResponse` does not automatically protect the `RelayState` hidden input**. The SP should use an unpredictable token mapped to server-side state, or an appropriate independent integrity/authentication mechanism.
- Any browser-submitted field can be tampered with. The server must verify correlation before using state and targets.
- **Never store passwords, login tokens, sensitive identifiers, or permissions inside RelayState**.

A signature proves a message was not altered under its respective mechanism; it does not replace policy over **which URLs are allowed for post-login redirect**.

## 5. SP-initiated Flow: From Deep Link to Deep Link

Suppose an unauthenticated user opens:

~~~text
https://app.example.org/portal/orders/42?tab=history
~~~

A typical flow:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring Security SP
    participant I as IdP
    B->>SP: GET /portal/orders/42?tab=history
    SP->>SP: RequestCache saves SavedRequest of original URL
    SP-->>B: 302 to login page or endpoint
    B->>SP: GET /saml2/authenticate/corp
    SP->>SP: Create and save AuthnRequest, RelayState
    SP-->>B: Redirect to IdP?SAMLRequest=...&RelayState=h
    B->>I: GET to IdP SSO
    I-->>B: Login/MFA or reuse existing IdP session
    I-->>B: Form POST SAMLResponse + RelayState=h
    B->>SP: POST /login/saml2/sso/corp
    SP->>SP: Verify assertion + InResponseTo + session
    SP->>SP: Create Authentication and SP session
    SP->>SP: SuccessHandler retrieves SavedRequest
    SP-->>B: 302 /portal/orders/42?tab=history
    B->>SP: GET target page with SP session cookie
    SP-->>B: Order content if permitted
~~~

**Key step breakdown:**

1. `ExceptionTranslationFilter` detects the request requires authentication. Before invoking the authentication entry point, `RequestCache` may save the original request in HttpSession.
2. On SAML initiation, `Saml2WebSsoAuthenticationRequestFilter` issues `AuthnRequest`. `HttpSessionSaml2AuthenticationRequestRepository` saves the SAML request for correlation.
3. The browser visits the IdP and brings back `SAMLResponse` plus RelayState via form POST. **RelayState does not authenticate the user**, nor does it prove the SavedRequest is valid.
4. `Saml2WebSsoAuthenticationFilter` and the authentication provider verify signature/issuer/audience/destination/subject confirmation/time/correlation per configuration.
5. Upon successful authentication, Spring Security creates `Authentication`; the success handler chooses where to send the browser next. Configured with `SavedRequestAwareAuthenticationSuccessHandler`, the handler pulls SavedRequest and redirects to the original URL if present.
6. When the browser GETs the order page again, viewing that order still depends on **resource authorization**, not just SAML login.

**Easy-to-miss point:** if SavedRequest contains `?tab=history`, redirecting typically restores the full URL. However, **never use SavedRequest as a "replay any POST" mechanism**. For state-changing operations, design a GET page or safe draft storage, then require the user to confirm the POST after login. Never auto-replay a payment/order submission solely because the user just authenticated.

## 6. RequestCache Differs from Saml2AuthenticationRequestRepository

Both repositories may happily live inside the same HTTP session, yet they have different APIs and reasons to exist.

| Spring Security Mechanism | Stored Object | When Saving Starts | When Used |
| --- | --- | --- | --- |
| `RequestCache` | `SavedRequest`, e.g., GET `/portal/orders/42` | Protected request blocked as unauthenticated | After login to pick target URL, and when browser revisits that URL |
| `Saml2AuthenticationRequestRepository` | `AbstractSaml2AuthenticationRequest`, holding AuthnRequest/RelayState info | When building SAML AuthnRequest | When receiving ACS response to correlate transaction |
| `RelyingPartyRegistrationRepository` | SP–IdP registration, issuer, SSO URL, certs | App configuration, usually at startup | Building requests and verifying responses |
| HTTP session/SecurityContext repository | Principal and authenticated session details | After login is accepted | Subsequent requests requiring authentication |

Spring Security uses `HttpSessionSaml2AuthenticationRequestRepository` as the default implementation for storing AuthnRequests in Servlet versions described in the docs. Cache/distributed repository options exist, yet do not switch just to save one cookie without evaluating login fixation and CSRF.

### When the Session Holds Multiple States

In a simplified view:

~~~text
Browser's HTTP Session:
  SavedRequest:
    originalUrl = /portal/orders/42?tab=history
  SAML authentication request:
    requestId = _request-abc
    relayState = opaque-handle
    registrationId = corp
  After success:
    SecurityContext -> authenticated principal
~~~

This diagram only explains the concept. **Do not claim these are the exact internal session keys/objects of a specific Spring Security version**; never write integrations relying on internal key names or formats.

When "RelayState not found" and "SavedRequest missing" errors occur, inspect **two separate storage paths**.

## 7. What Does SavedRequestAwareAuthenticationSuccessHandler Do?

`SavedRequestAwareAuthenticationSuccessHandler` is Spring Security's success handler that uses `RequestCache` to return users to their original resource. It is useful not only for SAML, but across many Servlet stack authentication mechanisms.

After success, the handler fundamentally chooses:

1. If **`alwaysUseDefaultTargetUrl=true`** is configured, ignore SavedRequest and go to the default target.
2. If **`targetUrlParameter`** is configured and the request carries that parameter, it may prioritize the parameter-supplied target. **Do not enable this with arbitrary browser-supplied targets** without strict validation.
3. If a SavedRequest exists in `RequestCache`, redirect back to the original URL.
4. If no SavedRequest exists, fall back to `SimpleUrlAuthenticationSuccessHandler`'s default target selection, e.g., `/portal` if configured.

Thus, changing `defaultTargetUrl` alone is not enough to force every login to the home page; `alwaysUseDefaultTargetUrl` and SavedRequest state matter. Conversely, forcing the default always disables deep-link restoration.

**Difference from RelayState:** the success handler does not need to decode RelayState into a URL to redirect. An SP can keep RelayState opaque purely for SAML correlation while using SavedRequest separately to know the original URL.

### Browser-Originated Data Requires a Trust Policy

Even SavedRequest should only be created from **real requests to application-managed resources** with proper proxy/host configuration. If hostnames/forwarded headers are wrongly trusted, an unwanted absolute URL can sneak into the cache. Never turn login success into a license to redirect to an arbitrary host.

## 8. Spring Security Servlet Example: Restoring a Saved Destination

The following example belongs to a **Spring Boot 3.x project with Spring Security SAML2 SP** and a valid `RelyingPartyRegistrationRepository`. File:

`src/main/java/com/example/federation/SamlLoginConfiguration.java`

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;

@Configuration
public class SamlLoginConfiguration {

    @Bean
    RequestCache requestCache() {
        return new HttpSessionRequestCache();
    }

    @Bean
    SavedRequestAwareAuthenticationSuccessHandler samlSuccessHandler(
            RequestCache requestCache) {
        var handler = new SavedRequestAwareAuthenticationSuccessHandler();
        handler.setRequestCache(requestCache);
        handler.setDefaultTargetUrl("/portal");
        handler.setAlwaysUseDefaultTargetUrl(false);
        return handler;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            RequestCache requestCache,
            SavedRequestAwareAuthenticationSuccessHandler samlSuccessHandler)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**", "/error").permitAll()
                        .anyRequest().authenticated())
                .requestCache(cache -> cache.requestCache(requestCache))
                .saml2Login(saml -> saml.successHandler(samlSuccessHandler))
                .build();
    }
}
~~~

**This is Spring configuration**, not a standalone Java program with `main`. It compiles/runs only inside a Boot project with compatible dependencies and real IdP metadata. There is no fixed stdout; observable outcomes are HTTP responses and redirect URLs.

Explanation:

- `HttpSessionRequestCache` stores the intercepted resource request; this is the source of the restored URL.
- `handler.setRequestCache(requestCache)` and `.requestCache(cache -> cache.requestCache(requestCache))` make the filter chain and handler share the same cache.
- `setDefaultTargetUrl("/portal")` serves as fallback when no SavedRequest exists (e.g., user initiated login directly).
- `setAlwaysUseDefaultTargetUrl(false)` allows prioritizing saved deep links.
- `.saml2Login(saml -> saml.successHandler(...))` attaches the handler upon SAML 2.0 login success; it **does not replace SAML verification**.
- `anyRequest().authenticated()` protects all other URLs; real projects need business authorization policies and must ensure login/public pages are permitted to avoid redirect loops.
- `targetUrlParameter` is omitted because a target parameter can be altered by the browser and requires strict open-redirect controls.

In many Spring Security projects, the default success handler already supports saved requests. This example **makes the mechanism explicit** and shows where to configure it so behavior stays consistent when multiple authentication mechanisms coexist. Do not override the handler if your project already works properly.

### What Dependencies Are Needed?

In a Boot Servlet application module, core dependencies typically include:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

This is only the `dependencies` block in a Gradle project **already configured with the Boot BOM and appropriate OpenSAML/Shibboleth repositories**. Do not pin Spring Security versions against the BOM. Real IdP metadata and registration are required to run SAML; you cannot test login merely by adding these three dependencies.

### Illustrative IdP Configuration

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp.xml"
~~~

Place **verified** metadata XML at `src/main/resources/saml/corp-idp.xml` and register the SP entity ID/ACS on the IdP. Never invent an XML file with an arbitrary certificate and treat it as a trusted IdP.

## 9. Flow When There Is No SavedRequest

There are several ways login can begin:

**A. User opens a deep link while unauthenticated:** Spring saves `SavedRequest` and returns to that URL after login. This is the desired flow for `/portal/orders/42`.

**B. User clicks "Log in" on a public page:** the browser goes straight to `/saml2/authenticate/corp` with **no prior protected request** to save. After login, the success handler uses `defaultTargetUrl("/portal")`.

**C. User opens an IdP bookmark or enters SSO from a corporate portal:** **IdP-initiated SSO** may occur, where the browser POSTs `SAMLResponse` to the ACS without the SP having created an AuthnRequest beforehand. There is no SavedRequest from a protected resource and likely no standard request correlation. Accept unsolicited responses only if **SP policy permits** and the provider/version handles it safely; the target should be the default or chosen from an allow-list agreed with the IdP.

**D. User is already logged in to the SP:** visiting `/portal/orders/42` goes directly to the controller if authorized, needing no new RelayState or SavedRequest.

**Do not treat RelayState from an IdP-initiated response as a safe redirect URL directive.** For logins without a correlated request, it is lower-trust input and must be governed by explicit policy/contracts.

## 10. How to Design Putting Destinations in RelayState If Needed?

Some systems must preserve context across complex multi-step or multi-IdP business flows and cannot rely solely on request cache. A safe design:

1. When the user opens a valid SP URL, extract an **application-owned path** or business identifier, validate it, and store it server-side.
2. The SP generates a sufficiently unpredictable **opaque random handle** (e.g., 128–192 bits), under 80 bytes when ASCII-encoded.
3. Store the mapping `handle -> {registrationId, requestId, sessionBinding, localDestination, createdAt, expiresAt, consumed=false}` in a store with a short TTL. Never store raw off-domain URLs or sensitive info as RelayState.
4. Put **only the handle** into RelayState when building AuthnRequest via the resolver/API supported by your Spring Security version.
5. When `SAMLResponse` hits the ACS, **verify SAML first**: signature, issuer, audience, destination, validity window, `InResponseTo`, and conditions.
6. After verification, look up the handle in the server-side store, **bound to the browser/session/requestId transaction**; verify TTL, registration, and single-use status.
7. Consume/mark the handle **atomically** and retrieve the approved destination. If any check fails, discard the handle and use a safe fallback (or reject the transaction depending on risk).
8. Redirect only to an **internal path** or strict official allow-list; the user still needs authorization to view the resource.

This is a **custom architecture**, not a description of how Spring Security stores fields by default. Some APIs let you build authentication requests and set RelayState via a resolver; without a special need, **using the default RequestCache** is usually simpler and less error-prone.

### Why Must It Be Bound to the Browser Session?

Suppose an attacker initiates login for **their own account** and sends the callback/RelayState to a victim's browser. If the SP uses a global store keyed solely by RelayState or InResponseTo to locate requests and accept responses, the victim can be logged in to the attacker's account (**login CSRF / login fixation**). Merely having a random handle does not prove the victim's browser initiated that request.

Spring Security stores AuthnRequest in **HttpSession** by default because the browser session provides a crucial binding: a response from another transaction normally lacks a matching request in that session. If replacing it with a global distributed cache, re-evaluate login fixation defenses and design additional binding; never treat any response that "finds a key" as safe enough.

## 11. Storing AuthnRequest in Session or Distributed Cache?

Spring Security provides the `Saml2AuthenticationRequestRepository` interface. By default it uses `HttpSessionSaml2AuthenticationRequestRepository`. Recent documentation also describes `CacheSaml2AuthenticationRequestRepository` to store AuthnRequests in a distributed cache keyed by RelayState.

| Storage Choice | Benefits | Risks / Things to Check |
| --- | --- | --- |
| **Default session** | Binds SAML request to browser session, helpful against login fixation | Session cookie must return to ACS; requires SameSite/replica/session persistence policies |
| **Distributed cache by RelayState** | Can look up requests when session is unavailable; convenient across nodes | Must design/assess login fixation defenses, session binding, and replay/TTL yourself |
| **Custom repository** | Custom multi-tenant, tracing/correlation, storage | Larger failure surface: race conditions, stale state, key collisions, cleanup, and security |

In Spring Security 7.x you can expose a `CacheSaml2AuthenticationRequestRepository` bean per official docs; check availability and constructor/config against your exact **version**. **Do not change the repository just to customize post-login URLs**: that choice primarily governs SAML state, whereas original URLs belong to `RequestCache`.

If running multiple replicas with per-node in-memory sessions, callbacks hitting another node can lose state. Sticky sessions or distributed Spring Session may be needed; that does not mean RelayState should carry session tokens.

## 12. SameSite Cookies Causing POST-to-ACS Callbacks to Lose State

Web SSO flows typically start at the SP, transition to an IdP on another site, and then the IdP returns an HTTP POST form to the SP's ACS. The browser may withhold SP cookies then depending on `SameSite`:

- `SameSite=Strict`: cookies are not sent on cross-site requests. For federated login, this very easily loses sessions on return steps.
- `SameSite=Lax`: usually sends cookies on cross-site top-level navigations using **safe methods like GET**, so Lax cookies cannot be relied upon for normal cross-site POSTs.
- `SameSite=None; Secure`: allows sending cookies in many cross-site contexts over HTTPS, yet requires solid CSRF/login-CSRF defenses.
- Browsers also block third-party cookies in embedded iframes; top-level login differs from embedded login. Temporary browser exceptions for cookies omitting SameSite should never be relied upon as a design.

**Symptom:** the IdP authenticated the user and the form POSTed `SAMLResponse` to the right ACS, yet the SP cannot find `AuthnRequest` in the session. The outcome is usually a correlation/unsolicited error, not necessarily a signature error.

Investigation steps:
1. Check whether the browser's ACS POST request includes a `Cookie` header with the right session.
2. Compare `Set-Cookie` before redirect with cookies sent at ACS: SameSite, Secure, Domain, Path, expiry.
3. Check whether proxy/TLS offloading and public host cause cookies to be misclassified as insecure or cross-site.
4. Check session store/sticky sessions in multi-node deployments.
5. Only adopt cookie/session/request-repository alternatives after assessing login CSRF; never drop `InResponseTo` to bypass the error.

**Distinction:** losing the **AuthnRequest session** can cause the SAML Response to be rejected; losing **SavedRequest** may let login succeed while sending the user to the fallback page. Both cases require inspecting different parts.

## 13. Open Redirect: Dangerous Vulnerability When Using RelayState as a URL

An unsafe approach:

~~~text
POST /login/saml2/sso/corp
RelayState=https://attacker.example.org/phishing

After SAML login succeeds:
302 Location: https://attacker.example.org/phishing
~~~

If the SP redirects the browser to **any URL taken directly from RelayState**, an attacker can abuse the SP domain's reputation to send users to a phishing site or launch follow-on attacks. Even with a valid assertion, **the redirect target can be attacker-controlled**.

Never accept unapproved targets such as:

- Off-domain absolute URLs: `https://evil.example.org`.
- Scheme-relative URLs: `//evil.example.org/path`.
- Dangerous/unexpected schemes: `javascript:`, `data:`.
- Multi-layer encodings or backslashes parsed differently by libraries/browsers: `/%2F%2Fevil...`, `\\evil.example.org`.
- Hosts tampered via untrusted `Host`/`X-Forwarded-Host` headers, poisoning SavedRequest or absolute redirect URLs.

**Preference:** redirect to an **allow-listed local path** retrieved from server-side state bound to the exact transaction. If that cannot be guaranteed, use a safe fallback. Checking only `startsWith("/")` is too weak: `//evil.example.org` also starts with a slash.

### Practical Rules

1. Targets retrieved from an **SP-controlled RequestCache** are the baseline choice for SSO deep links.
2. If clients may suggest a target, translate it into a **route ID** against an allow-list routing table stored server-side.
3. Never use raw `Referer` to pick the post-login page; the header may be absent or altered.
4. Never enable `setTargetUrlParameter("redirect")` without strict validation of origin, path, encoding, and authorization.
5. Never treat `RelayState` as access permission: even for a valid target, the route must still enforce per-user authorization.

## 14. Standalone Java 17: Selecting Targets from an Allow-List

This example shows how **not to trust an externally supplied path**, while generating a short ASCII RelayState. It is a **standalone** Java 17 program using the JDK Standard Library; it **does not perform SAML login or create real server sessions**.

Save as `SafeRelayStateDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Set;

public class SafeRelayStateDemo {

    private static final Set<String> ALLOWED_PATHS = Set.of(
            "/portal",
            "/portal/orders",
            "/portal/profile"
    );

    static String safeTarget(String proposed) {
        return ALLOWED_PATHS.contains(proposed) ? proposed : "/portal";
    }

    static String newRelayState() {
        byte[] random = new byte[18];
        new SecureRandom().nextBytes(random);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(random);
    }

    public static void main(String[] args) {
        String relay = newRelayState();
        System.out.println("RelayState bytes: "
                + relay.getBytes(StandardCharsets.US_ASCII).length);
        System.out.println("RelayState URL-safe: "
                + relay.matches("[A-Za-z0-9_-]+"));

        System.out.println("Known path: "
                + safeTarget("/portal/orders"));
        System.out.println("External URL: "
                + safeTarget("https://evil.example.org/phishing"));
        System.out.println("Protocol-relative URL: "
                + safeTarget("//evil.example.org"));
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac SafeRelayStateDemo.java
java SafeRelayStateDemo
~~~

**Exact stdout** (the random token is not printed):

~~~text
RelayState bytes: 24
RelayState URL-safe: true
Known path: /portal/orders
External URL: /portal
Protocol-relative URL: /portal
~~~

Explanation:
- 18 random bytes → 24 unpadded Base64url characters → **24 ASCII bytes**, under the 80-byte limit.
- `SecureRandom` is appropriate over `Math.random()` for generating unpredictable handles.
- `Set.contains` permits only **explicitly approved paths**, avoiding general URL-parser pitfalls. The example intentionally omits dynamic query/path parameters; to support `/portal/orders/42`, store a **server-validated route ID and order ID**, then use a framework URI builder to construct the internal path.
- A RelayState token needs server-side mapping with TTL, session/request binding, and one-time consumption. **Generating random tokens as in the example does not alone protect against login CSRF or replay.**
- This code has no Spring dependencies. Never use `newRelayState()` alone as a substitute for a SAML authentication request repository.

## 15. What Happens When Multiple Tabs Request Login Simultaneously?

Scenario:

- Tab A opens `/portal/orders/42`, creating SavedRequest A and AuthnRequest A.
- Tab B opens `/portal/profile`, creating SavedRequest B and AuthnRequest B.
- The user finishes logging in on tab A, yet the application's session/request repository or RequestCache stores a single slot/state without distinguishing tabs.
- After callback, the user may land on tab B's page or hit a correlation error, depending on storage and version.

**Do not assert Spring Security always breaks multi-tab**: actual results depend on repository, session, configuration, and request order. Still, this scenario must be tested because SavedRequest and SAML requests are separate states that can overwrite each other or expire.

Design mitigations:
- Do not rely on "one original URL across all tabs" if the product requires parallel login flows.
- If storing destinations under an opaque RelayState, the mapping must distinguish **transaction**, `requestId`, session/browser binding, and timestamp—not a single global property.
- Enforce expiration, one-time consumption, and stale cleanup; use atomic operations on response arrival.
- Complex cases may require customizing `RequestCache`/SAML request repository or UX allowing users to pick where to return rather than silently replaying.
- Always enforce authorization on the final route.

## 16. Edge Cases Affecting Destination Restoration

| Scenario | Reasonable Behavior | What to Check |
| --- | --- | --- |
| User opens protected URL then logs in | Returns to original URL | SavedRequest saved and success handler uses same RequestCache |
| User starts login from public page | Goes to configured fallback | No SavedRequest exists |
| IdP returns a RelayState differing from SP's sent value | Reject/ignore tampered state per policy; never redirect on forged data | Correlation, integrity, and redacted logs |
| Valid SAMLResponse yet SavedRequest lost | Can go to fallback; **never build URL from untrusted RelayState** | Session/RequestCache, timeout, cookies |
| Invalid SAMLResponse | Do not treat as successful login; never navigate to protected target with new Authentication | Signature, issuer, audience, time, destination, InResponseTo |
| Session lost before callback | Login may fail due to missing AuthnRequest; do not skip validation | SameSite cookies, distributed sessions |
| SP session expires mid-flow | Usually restart login or show recoverable error | TTL, session state, IdP session |
| User opens multiple tabs | May mix targets/correlation if state is shared | Per-transaction RequestCache and SAML repository |
| User submits protected POST/PUT link | Do not replay side-effecting action | Design GET/resume flow and re-confirmation |
| Post-login URL has query containing tokens | Avoid writing tokens to URLs/logs; use dedicated token management | RequestCache logging, redirect strategy |
| Proxy produces `http://internal:8080` URL | Restored URL/ACS may be wrong | Trusted forwarded headers, base URL, HTTPS |
| User logs out of SP and visits new deep link | Re-authenticate if no session; never reuse stale RelayState | Session invalidation, one-time handles |
| IdP-initiated login without request | Accept only under explicit policy, using fallback/allow-list | Unsolicited response/login fixation risks |

When "login succeeded yet wrong page" occurs, check `RequestCache`/success handler first. When "SAMLResponse rejected" occurs, check `AuthnRequest`/RelayState/correlation and ACS validations first.

## 17. Login CSRF, Session Fixation, and Replay

### Login CSRF

This occurs when a victim's browser receives a login result that the victim **did not appropriately initiate**, potentially logging the victim in under an attacker's identity. Therefore, verify the links among browser, AuthnRequest, SAML Response, and session before accepting.

Checking only "Response carries IdP signature" may not prove the response belongs to a login requested by that browser. Properly enforce `InResponseTo`, request repository, session binding, and IdP-initiated/unsolicited policies.

### Session Fixation

After successful authentication, ensure sessions follow Spring Security's session fixation protection policy. If using custom authentication filters, response handlers, or `SessionAuthenticationStrategy`, never bypass default steps that rotate the session ID and initialize `SecurityContext`.

### Replay

A RelayState already used to resolve a destination should generally not be infinitely reusable. With custom cached state:
- Attach a short TTL per login transaction.
- Consume once via atomic operations.
- Compare request ID and tenant/registration.
- Grant no privileges from the token itself.
- Clean up on logout, timeout, or authentication failure.

For SAML responses, validity-window checks, subject confirmation, and anti-replay **cannot be replaced** by a simple RelayState counter.

## 18. Securing Post-Login Redirects in Spring Security

`SavedRequestAwareAuthenticationSuccessHandler` can restore the original URL, yet the application must decide how to handle queries/hosts in reverse-proxy environments:

1. Configure the application's **public canonical URL**, trusting `Forwarded`/`X-Forwarded-Host` only from trusted reverse proxies.
2. Validate accepted hosts at ingress/application; never allow a spoofed `Host` header to build absolute redirect URLs.
3. If using a custom success handler, allow redirects only to internal paths or strictly normalized allow-listed URLs.
4. Never rely on browser `Referer` or an unvalidated `?returnUrl=` query to override SavedRequest.
5. Never write raw authorization codes, `SAMLResponse`, assertions, RelayState, cookies, or private keys to production logs.
6. Protect the destination page with post-login authorization; e.g., a user who does not own order 42 still gets 403/404 even though SavedRequest sent them back to that path.
7. Be cautious with custom "always redirect to dashboard" rules that break deep-link UX without adding real security.

If business requirements demand redirecting to **another application**, use a dedicated integration contract, a fixed-origin destination allow-list, or an SSO flow into that app; never accept arbitrary cross-origin URLs from RelayState.

## 19. How to Test Using Browser and HTTP Traces

**Setup:** a test SP with a protected URL, a configured test IdP, and an isolated browser. Never test with real SAML assertions on public sharing tools.

### Test A: Pre-login Deep Link

1. Clear/reset the test SP session, open browser Network → Preserve log.
2. Open `https://app.example.org/portal/orders/42?tab=history`.
3. Observe the unauthenticated SP response: redirect to login/SAML start, session cookie, and initiation URL.
4. Observe `GET /saml2/authenticate/corp`, followed by the IdP request carrying `SAMLRequest` and possibly `RelayState`.
5. After IdP login, observe the browser POSTing `SAMLResponse` to the exact SP ACS along with the RelayState echoed by the IdP.
6. Only once the SP verifies successfully does the browser receive a redirect back to `/portal/orders/42?tab=history`.
7. Refresh the target page: no re-login while SP session is valid; verify the user's authorization for order 42.

**Expectation:** original URL restored, no redirects to unknown domains, no failed SAML requests, and protected content shown only after valid login.

### Test B: Direct Login

Open `/saml2/authenticate/corp` from a public page with no SavedRequest. After login, land on the `/portal` fallback per config example—not an arbitrary URL from RelayState.

### Test C: Tampering with RelayState

Using a controlled test harness, replace inbound RelayState with a nonexistent value, another flow's value, or an overly long string. **Secure outcome:** never use tampered input as a redirect URL, never disable SAML/Request ID validation. Depending on repository/policy, authentication must be rejected or custom target discarded for a safe fallback, never bouncing to an arbitrary website.

### Test D: Callback Missing Session

Reproduce by withholding the SP cookie on the ACS POST or expiring the server session. Verify missing-request-correlation errors appear; never accept unsolicited responses just to make the test pass. Record `SameSite` on the cookie and store state.

### Test E: Replay

An already-used response or RelayState must not be reused to create an unsolicited login or navigate to targets saved from another session. Verify one-time consumption logic if using a custom server-side store.

### Test F: Multiple Tabs

Open two different deep links in the same browser, initiate two logins close together, and finish them in different orders. Verify the app routes to the right tab/URL or displays an appropriate correlation error without leaking or mixing sensitive state.

### Test G: Proxy/Host

Repeat over a public HTTPS domain behind a reverse proxy. Ensure `Location`, ACS, and cookies use the right scheme/host; no internal URLs like `http://localhost:8080` may appear.

**Never include in public reports:** raw `SAMLResponse`, session cookies, real RelayState, SAML assertions, tokens, or URLs with personal data. For HAR/logs, redact sensitive values and keep only method, sanitized path, status, timestamp, and host.

## 20. Quick Diagnostic Table

| Symptom | Likely Error Area | Action to Take |
| --- | --- | --- |
| Login succeeds yet always lands on `/portal` | No SavedRequest, or handler forces default | Check `alwaysUseDefaultTargetUrl`, RequestCache, and how login started |
| Login succeeds yet lands on another tab's URL | SavedRequest overwritten in multi-tab | Inspect per-session/transaction storage and test callback ordering |
| Login succeeds yet URL has wrong host/protocol | Host/forwarded headers | Check trusted proxies and canonical URL |
| IdP does not return RelayState | IdP/binding/integration | Compare request/response and IdP config; never fabricate values |
| RelayState truncated/shortened | IdP length limit, encoding | Check **byte** length (80 bytes per spec), ASCII/URL encoding |
| Altered RelayState still redirects off-domain | Unvalidated custom handler | Remove direct target handling; use opaque handle + allow-list |
| SAMLResponse has no matching request | Lost session, IdP-initiated, or correlation failure | Check `InResponseTo`, repository, SameSite session cookies |
| Validly signed response causes login fixation | Accepted response for flow not owned by browser | Enforce session/request binding, unsolicited policy, distrust global cache keys |
| ACS POST returns 403 | Filter chain/CSRF or validation | Distinguish CSRF from authentication failure; never disable globally |
| Deep-link page returns 403 after login | Authorization denies user | Fix resource permissions; never tweak RelayState |
| Original URL query parameters vanish | Success handler/custom redirect drops query | Use SavedRequest URL/URI building properly; test queries |
| Redirect loop after login | Session cookie not saved, chain misses Authentication | Compare cookie/SP session, host/path/secure, login success |
| `TargetUrlParameter` abused | Open redirect | Disable arbitrary parameter or validate against strict allow-list |
| RelayState missing after timeout | TTL too short, cache evicted | Expiration policy/prompt fresh login; never drop checks |
| SAML data appears in access logs | Overly broad logging | Redact or disable raw query/body logging containing sensitive data |

## 21. Self-Check Exercises

**Exercise 1.** An unauthenticated user opens `/portal/orders/42`. After a valid SAML response, the SP redirects them to `/portal`. Name two mechanisms to inspect first.

**Answer:** (1) Did `RequestCache` save `SavedRequest` when accessing the protected URL? (2) Does `SavedRequestAwareAuthenticationSuccessHandler` use the same cache, or is `alwaysUseDefaultTargetUrl=true` configured? RelayState does not necessarily hold the original URL.

**Exercise 2.** Request to IdP carried `RelayState=xyz`, response returned `RelayState=abc`. When may the SP use "abc" as a destination?

**Answer:** Never use it directly as a URL because it was not the value issued for the transaction. Handle the mismatch per security policy and correlation; the SAML response must be verified independently. With a custom opaque store, failing to find the matching handle yields no valid target.

**Exercise 3.** IdP returns the right RelayState and a signed `SAMLResponse`, yet the SP cookie is absent from the ACS POST. Is login guaranteed to succeed?

**Answer:** No. The Spring SP may fail to find the AuthnRequest session to check `InResponseTo`. Valid signature and RelayState do not prove the browser has a matching request in session; inspect SameSite, session store, and request repository.

**Exercise 4.** A user supplies `https://evil.example.org` in `?returnUrl=`, and the system redirects there after SAML login. What vulnerability is this?

**Answer:** **Open redirect**. Never trust external URLs supplied by users or RelayState; use route allow-lists/opaque server-side state and enforce origin controls.

**Exercise 5.** Should we pack JSON with email, role, JWT, URL, and browser cookies into RelayState to avoid needing sessions?

**Answer:** No. RelayState has a byte limit, passes through the browser, can be inspected/modified, and is not an authentication store. Keep a short opaque handle, store minimal data server-side, and protect credentials at the proper layer.

**Exercise 6.** Distinguish two failures: (A) `SAMLResponse` rejected due to missing request in repository, and (B) SAML login succeeds yet the original URL is lost.

**Answer:** (A) Missing or mismatched **AuthnRequest/SAML correlation**—investigate session/`Saml2AuthenticationRequestRepository`; (B) Lost **SavedRequest** or success handler/`RequestCache` config—investigate post-login navigation.

**Exercise 7.** A user initiates SAML login via a button on the homepage and lands on `/portal`. Is this a RelayState bug?

**Answer:** No. Without visiting a protected deep link beforehand, there is no SavedRequest; `/portal` is the expected fallback.

**Exercise 8.** RelayState is 36 ASCII characters and the assertion is sent via POST. Does the XML signature on the assertion automatically guarantee RelayState was not modified?

**Answer:** No. RelayState is a separate form field; state must be protected independently and correlated with the transaction. In a signed Redirect binding query, RelayState can be covered by the query signature per spec/errata, but do not assume the same for POST.

## 22. Deployment Checklist

- [ ] Deep-link URLs to restore and route authorization rules are identified.
- [ ] Team clearly distinguishes RelayState, AuthnRequest/InResponseTo, and SavedRequest.
- [ ] `RelayState` is short, opaque, under **80 bytes**, containing no secrets or user info.
- [ ] IdP echoes RelayState verbatim in SP-initiated flows.
- [ ] SAML Response/Assertion verifies signature, issuer, audience, recipient/destination, validity window, and correlation before creating Authentication.
- [ ] `RequestCache` stores the original request on protected URL access; success handler is configured to restore destinations.
- [ ] Safe fallback exists for direct login or missing SavedRequest.
- [ ] Target URL parameters and reading raw Referer/RelayState for off-domain redirects are disabled.
- [ ] If using a custom token store, session/browser binding, TTL, one-time consume, registration/request ID correlation, and replay controls are enforced.
- [ ] IdP-initiated login and unsolicited responses are evaluated separately; never implicitly trust non-browser-initiated requests.
- [ ] Cookies/sessions support cross-site POST ACS, SameSite/Secure, and multi-node deployments.
- [ ] Tested multi-tab, timeouts, failed logins, query paths, authorization, and Host/proxy headers.
- [ ] Redacted `SAMLResponse`, assertions, cookies, RelayState, and personal data from logs/HARs.

## 23. Key Takeaways

**RelayState carries SAML flow context across the IdP; RequestCache holds the original HTTP request; AuthnRequest/InResponseTo binds the response to the SAML transaction.** After SAML verification succeeds, the success handler can pull SavedRequest to send the browser back to the deep link. To preserve post-login URLs safely, **never turn RelayState into an arbitrary browser-controlled redirect URL**.

### Technical References

- Spring Security — Producing SAML AuthnRequests, HttpSessionSaml2AuthenticationRequestRepository, and CacheSaml2AuthenticationRequestRepository: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Servlet Architecture / Saving Requests Between Authentication: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security API — SavedRequestAwareAuthenticationSuccessHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html
- Spring Security API — RequestCache: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/savedrequest/RequestCache.html
- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- OASIS — SAML 2.0 Bindings, Sections 3.4.3 and 3.5.3 RelayState: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OASIS — SAML 2.0 Approved Errata E1 (RelayState in Redirect query signature): https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0-cd-02.html
