# Post-login redirects and restricting trusted URL sources

After a user logs in successfully, applications typically send them to a dashboard or the page they were viewing before authentication was required. This is a **post-login redirect**. A small feature that can turn into an **open redirect** if the server reads a URL from a query parameter, cookie, header, or unvalidated request and writes it straight into the HTTP `Location` header.

The safety condition is not merely "login succeeded", but also: **the destination comes from an allowed source, belongs to an approved URL scope, matches the session/context, and does not bypass authorization checks at the resource**. In Spring Security Servlet, relevant components include `AuthenticationSuccessHandler`, `SavedRequestAwareAuthenticationSuccessHandler`, `RequestCache`, `defaultSuccessUrl`, and `RedirectStrategy`.

This lesson focuses on **restricting trusted URL sources when redirecting after login**, both defending against phishing/open redirects and preserving internal deep-link UX where legitimately needed. Java 17+ examples clearly separate standalone runnable programs from Spring Boot configurations.

## 1. Why do applications need post-login redirects?

Suppose an unauthenticated user opens an order page:

~~~http
GET /orders/123 HTTP/1.1
Host: shop.example.org
~~~

A typical flow:

~~~text
Browser: GET /orders/123
          |
          v
Spring Security sees unauthenticated
          |
          v
Save original request if RequestCache is enabled
          |
          v
302 -> /login
          |
          v
POST /login, credentials verified
          |
          v
AuthenticationSuccessHandler picks target
          |
          +--> /orders/123 (valid saved request)
          |
          +--> /dashboard (safe fallback)
          |
          v
Browser GETs target page in logged-in session
~~~

Returning the user to `/orders/123` improves UX, yet they must still hold permission for that order. Successful login **never automatically grants access** to every order, tenant, or role.

Three common destination types:

| Scenario | Suitable target selection | What needs protection |
| --- | --- | --- |
| Normal login | Fixed URL like `/dashboard` | Configured target does not come from client |
| Login after visiting a protected page | `SavedRequest` in the same session | Host/public origin, path, context |
| User selects an area after login | Route key like `destination=orders` | Fixed mapping, access permissions |
| Portal needs to jump to a partner | Allowlisted target key | HTTPS, host/port/path, and no token leakage |

UX needs **never** mean permitting an arbitrary `returnUrl`.

## 2. Open redirect: how a redirect URL becomes a vulnerability

An attacker-crafted request:

~~~text
https://shop.example.org/login?next=https://fake-login.example.net
~~~

Java counter-example:

~~~java
// Unsafe: client has full control over the destination.
response.sendRedirect(request.getParameter("next"));
~~~

After login, the server returns:

~~~http
HTTP/1.1 302 Found
Location: https://fake-login.example.net
~~~

Because the victim interacted with the real domain, they readily trust the subsequent navigation flow. The fake site can prompt to sign in again, harvest OTPs, trick the user into installing software, or exploit trust in a link starting with the official domain.

**Identity authentication does not make inputs trustworthy.** The `next` request parameter can be attached by the attacker in the link sent to the victim. Names like `returnUrl`, `continue`, `redirect`, `target`, `callback`, or `destination` carry similar risks if treated as arbitrary URLs.

Open redirects can also serve as links in OAuth attacks, phishing, redirect chaining, and hiding true link destinations. Control **every place that emits an HTTP redirect**, not just the login page.

## 3. Classifying URL sources by trust level

| Target source | Assessment | Recommended policy |
| --- | --- | --- |
| Backend constant path | Good if code-reviewed | Preferred |
| Server-side route key allowlist | Good if map is strictly server-managed | Safe flexible solution |
| `SavedRequest` created in login session | Conditional | Verify matching session and host/path source |
| Query parameter `next` or `returnUrl` | Untrusted | Never pass straight into redirect |
| `Referer` header | Untrusted, may be absent | Never use as default redirect source |
| Browser cookie/localStorage | Client-modifiable | Must revalidate or sign/bind context |
| `Host`, `Forwarded`, `X-Forwarded-Host` headers | Spoofable if proxy misconfigured | Trust only from authorized proxies |
| URL stored in database | Depends on record create/edit rights | Still enforce target allowlist |
| OAuth2/OIDC `redirect_uri` | Must be client-registered/validated at AS | Never conflate with post-login URL |

There is no rule that "stored in session guarantees safety": if a session stores a URL from unvalidated input, reading it back must still enforce policy.

Questions to lock down before implementation:

1. Is a dynamic target needed, or is a fixed URL sufficient?
2. Is the allowed scope internal paths, a group of corporate domains, or partners too?
3. Who selects the target, via what mechanism, and when?
4. Is the target bound to the login session, tenant, and account?
5. If the target is invalid, where is the fallback?
6. What authorization checks does the target resource still need after login?

## 4. How does Spring Security decide the post-login URL?

In Spring Security Servlet, `AuthenticationSuccessHandler` runs after successful authentication. For form login, `SavedRequestAwareAuthenticationSuccessHandler` can return the user to the request blocked before login.

Per Spring Security 6.x/7.x Javadoc, this handler's selection order is essentially:

1. If `alwaysUseDefaultTargetUrl=true`: use `defaultTargetUrl`, ignoring any saved request.
2. If `targetUrlParameter` is configured and the request carries that parameter: use the parameter value, taking precedence over any saved request.
3. If `RequestCache` holds a `SavedRequest`: redirect to that request's URL.
4. Otherwise: fall back to the superclass default, typically `defaultTargetUrl`.

Diagram:

~~~text
Authentication successful
           |
           v
alwaysUseDefaultTargetUrl == true ?
       yes --> defaultTargetUrl
       no
           |
           v
targetUrlParameter has a value ?
       yes --> param value (must be trusted!)
       no
           |
           v
SavedRequest in RequestCache ?
       yes --> original request URL
       no
           |
           v
defaultTargetUrl
~~~

**Be careful with `targetUrlParameter`:** it lets a request value directly influence the redirect target. Never configure `setTargetUrlParameter("next")` unless the app wraps it with an appropriate validator/allowlist.

### Related APIs

- `SavedRequestAwareAuthenticationSuccessHandler`: uses the saved request when appropriate.
- `SimpleUrlAuthenticationSuccessHandler`: provides default URL/parameter/referer logic via its base class.
- `AbstractAuthenticationTargetUrlRequestHandler`: provides `setDefaultTargetUrl`, `setAlwaysUseDefaultTargetUrl`, `setTargetUrlParameter`, and `setUseReferer`.
- `HttpSessionRequestCache`: typically stores the original request in the session.
- `RedirectStrategy`: strategy executing the redirect; not a built-in external URL allowlist validator.

If a project overrides handlers or request caches, actual behavior may differ from defaults. Read the active config and test real `Location` responses.

## 5. Lowest-risk solution: fixed internal target

If returning to the previous page is unnecessary, pick a hardcoded post-login page:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .anyRequest().authenticated())
            .formLogin(form -> form
                    .defaultSuccessUrl("/dashboard", true))
            .build();
}
~~~

This is a **Spring Security Servlet configuration snippet**, requiring `@Configuration`, Bean/HttpSecurity/SecurityFilterChain imports, a Spring Boot main class, real routes, and a user store. It cannot run standalone with `javac` alone.

`defaultSuccessUrl("/dashboard", true)` means two things:

- `/dashboard` is the path chosen in server code.
- `true` sets "**always use default URL**", even when a `SavedRequest` exists.

Conversely, `defaultSuccessUrl("/dashboard")` with default settings continues prioritizing a saved request before falling back to dashboard. That is not inherently a vulnerability, yet you must understand product needs and request sources.

A fixed target fits small systems, internal apps with few areas, or high-security login flows. The trade-off is losing deep links after login.

## 6. Flexible solution: route keys instead of URLs

OWASP recommends preferring **short destination codes/names** mapped to server-approved URLs rather than letting clients submit arbitrary URLs.

Example:

~~~text
Login form sends: destination=orders
Server map:       orders -> /orders
Redirect:         /orders
~~~

Allowlist table:

| Route key | Approved path | Policy |
| --- | --- | --- |
| `dashboard` | `/dashboard` | Fallback |
| `orders` | `/orders` | Requires permission to view orders |
| `profile` | `/account/profile` | Logged-in user |
| `https://evil.example` | No mapping | Fallback |
| `//evil.example` | No mapping | Fallback |
| `/admin/users` | Not a route key | Fallback |

### Standalone Java 17+ program: PostLoginRouteDemo.java

This program selects a target from a fixed route table and simulates an application permission. It does not run HTTP or Spring; it illustrates the rule that **clients must never supply raw destination URLs**.

~~~java
import java.util.Map;
import java.util.Set;

public class PostLoginRouteDemo {

    private static final String DEFAULT = "/dashboard";

    private static final Map<String, String> ROUTES = Map.of(
            "dashboard", "/dashboard",
            "orders", "/orders",
            "profile", "/account/profile");

    static String choose(String requestedRoute, Set<String> authorities) {
        String path = requestedRoute == null
                ? null
                : ROUTES.get(requestedRoute);

        if (path == null) {
            return DEFAULT;
        }

        if (path.equals("/orders")
                && !authorities.contains("ORDER_READ")) {
            return DEFAULT;
        }

        return path;
    }

    public static void main(String[] args) {
        Set<String> withOrders = Set.of("ORDER_READ");
        Set<String> withoutOrders = Set.of();

        System.out.println("Default = " + choose(null, withoutOrders));
        System.out.println("Known route = "
                + choose("orders", withOrders));
        System.out.println("Missing permission = "
                + choose("orders", withoutOrders));
        System.out.println("External URL = "
                + choose("https://evil.example", withOrders));
        System.out.println("Scheme-relative URL = "
                + choose("//evil.example", withOrders));
        System.out.println("Unknown route = "
                + choose("something-else", withOrders));
    }
}
~~~

Compile/run with JDK 17 or higher:

~~~bash
javac PostLoginRouteDemo.java
java PostLoginRouteDemo
~~~

Exact stdout:

~~~text
Default = /dashboard
Known route = /orders
Missing permission = /dashboard
External URL = /dashboard
Scheme-relative URL = /dashboard
Unknown route = /dashboard
~~~

The key `orders` translates to a fixed path. An attacker URL, even syntactically valid, matches no key and goes to dashboard. `ORDER_READ` here is illustrative: the real endpoint must still check authorization and per-order permissions.

**Never distort the allowlist pattern** into `"/" + requestedRoute` or accept a client-modifiable map. Doing so concatenates untrusted data right back into the URL.

## 7. Integrating route keys with AuthenticationSuccessHandler

In Spring Security Servlet, a route map can be placed inside a custom success handler:

~~~java
@Bean
AuthenticationSuccessHandler approvedDestinationHandler() {
    Map<String, String> routes = Map.of(
            "dashboard", "/dashboard",
            "orders", "/orders",
            "profile", "/account/profile");

    return (request, response, authentication) -> {
        String key = request.getParameter("destination");
        String path = key == null
                ? "/dashboard"
                : routes.getOrDefault(key, "/dashboard");

        // Path is a server-side constant, not a client-sent URL.
        response.sendRedirect(request.getContextPath() + path);
    };
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        AuthenticationSuccessHandler approvedDestinationHandler)
        throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .anyRequest().authenticated())
            .formLogin(form -> form
                    .successHandler(approvedDestinationHandler))
            .build();
}
~~~

Requires imports for `java.util.Map`, `org.springframework.context.annotation.Bean`, `org.springframework.security.web.authentication.AuthenticationSuccessHandler`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, and `org.springframework.security.web.SecurityFilterChain`, placed inside a Spring configuration class. This snippet needs form login, a user store, and application controllers; it is **not** a standalone Java `main`.

**Protective properties:**

- `destination` is untrusted client input; used solely as a map lookup key.
- `routes` is server-constructed, and targets are approved paths.
- `getContextPath()` supports apps deployed under a Servlet context path while the path comes from an internal constant.
- Invalid destinations fall back to `/dashboard`.
- The destination endpoint must still enforce permissions; if routes carry distinct privileges, fallback selection can also consult verified `Authentication.getAuthorities()`.

Using a custom handler like this **replaces** the default `SavedRequestAware` handler behavior. If you want to keep deep links while preventing unintended stale cached requests, explicitly design the `RequestCache` lifecycle (clearing or continuing per flow); never accidentally mix two competing target selection mechanisms.

### Never grant privileges from routes or request parameters

Counter-example:

~~~java
// Wrong: client has no authority to self-declare ADMIN.
String claimedRole = request.getParameter("role");
if ("ADMIN".equals(claimedRole)) {
    response.sendRedirect("/admin");
}
~~~

Even when redirecting to `/admin`, the server must verify roles/resources at the endpoint; better yet, never pick the admin target if `Authentication` lacks the role. Route targets never decide roles.

## 8. Preserving deep links with SavedRequest without trusting spoofed Hosts

If you want to return users to the URL they tried accessing before login:

~~~text
GET /orders/123 (unauthenticated)
    -> save request in session
    -> login
    -> redirect back to /orders/123
~~~

Spring Security supports this via `RequestCache`. DSL example:

~~~java
http
    .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/error").permitAll()
            .anyRequest().authenticated())
    .formLogin(form -> form
            .defaultSuccessUrl("/dashboard"));
~~~

When a valid `SavedRequest` exists, the standard handler prioritizes it over the fallback. However, the original request can be influenced by **Host**, **scheme**, **port**, context path, and proxy headers. If the web server/proxy trusts forged headers from the Internet, the saved and reconstructed absolute URL could contain an out-of-scope host.

Suspicious request example:

~~~http
GET /orders/123 HTTP/1.1
Host: attacker.example
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
~~~

Exploitability depends on reverse proxy/container/framework configuration. **Do not claim every `SavedRequest` is open-redirect vulnerable by default**, yet always verify the inputs used to build URLs.

Policies to check:

1. Edge proxies only accept public `Host` values on an allowlist.
2. Proxies strip or overwrite `Forwarded`/`X-Forwarded-*` headers sent by Internet clients.
3. Backends trust forwarded headers only from authenticated/explicitly trusted proxy connections.
4. Prevent external network traffic from reaching the backend directly bypassing the proxy.
5. Verify HTTPS scheme, public port, and context path after SSL termination.
6. Restrict saved requests by appropriate scope/method; never cache login/logout/callback routes or URLs holding unnecessary secrets.
7. Authenticate user/tenant/resource after redirecting; never treat `SavedRequest` as authorization.

If users open multiple tabs or sign in with a different account, the request cache may hold an old target. Define clear strategies for multi-tab flows, session timeouts, and fallbacks.

## 9. Internal URLs do not mean any string starting with a slash is safe

When a product must support dynamic `returnUrl` paths, the validator must catch URL forms that browsers/proxies interpret differently from naive string checks.

| Input | Risk |
| --- | --- |
| `https://evil.example/path` | Absolute redirect to another domain |
| `//evil.example/path` | Scheme-relative URL, host is `evil.example` |
| `\\evil.example\path` | Backslash treated as separator by some stacks |
| `/%2F%2Fevil.example` | Encoded slashes change meaning once decoded |
| `/%252F%252Fevil.example` | Double decoding across multiple layers |
| `/../admin` | Path traversal/canonicalization |
| `https://shop.example.org.evil.net` | Misleading hostname prefix |
| `https://shop.example.org@evil.net` | Userinfo before `@`, actual host `evil.net` |
| `http://shop.example.org` | Downgrade from HTTPS |
| `javascript:...` or `data:...` | Unsuitable scheme for redirects |
| Strings with CR, LF, or control chars | Header/response splitting in weak stacks |
| `/orders?redirect=https://evil.example` | Redirect chain through another internal endpoint |

**Never** defend using `startsWith("https://shop.example.org")` or `endsWith("example.org")`. They ignore hostname boundaries, userinfo, ports, and canonicalization.

If permitting internal return paths:

1. Prefer **route keys** or an explicit router allowlist before parsing URLs yourself.
2. When parsing is required, use a maintained URL/URI library aligned with the redirect API and browsers, never a one-line regex.
3. Bound length; reject control characters, backslashes, and ambiguous formats.
4. Reject scheme/authority/userinfo, unnecessary fragments, and paths starting with two slashes.
5. Canonicalize and decode exactly once under one contract; never validate first and decode again later.
6. Block dot segments, double encoding, and paths outside allowed routes.
7. Apply a path allowlist and user/tenant/resource authorization.
8. Fall back safely on validation failure; never try to "sanitize" an attacker URL and redirect anyway.

`java.net.URI` helps inspect scheme/authority/path, yet **does not guarantee every browser/proxy parses strings identically to Java `URI`**. Never write an ad-hoc validator just to save a few lines of code.

## 10. External URLs: host allowlists and canonical origins

If the app must redirect to an approved partner website, keep a backend-managed lookup table:

~~~text
destination=partnerPortal
    -> https://portal.partner.example/approved/home
~~~

That is still a route key, only mapping to a fixed absolute HTTPS URL. If external URLs must vary dynamically for business needs, the validator must check much more:

| Property | Policy |
| --- | --- |
| Scheme | `https` only barring approved exceptions |
| Host | Exact canonical hostname match in allowlist |
| Port | Approved valid ports only; forbid arbitrary ports |
| Userinfo | Reject |
| Path | Restrict defined paths/prefixes with proper boundary checks |
| Query | Required parameters only, containing no secrets |
| Fragment | Usually unnecessary in server-redirect flows |
| IDN/punycode | Explicit canonicalization to avoid lookalike hosts |
| Redirect chain | External endpoints may redirect further; consider warnings |
| Permissions/tenant | Never send tenant-specific targets to another tenant |

Never use wildcards like `*.example.org` if subdomains can belong to users, third-party services, or become unmanaged. A host in "the same organization" is not automatically safe for all login data.

**Redirecting to a partner site is not a way to pass login sessions.** Never attach session cookies, access tokens, OAuth authorization codes, reset tokens, or API secrets in URLs. For federation, use OAuth2/OIDC/SAML flows with tightly registered callback/redirect URIs.

## 11. OAuth2/OIDC redirect_uri and post-login targets are different

OAuth2 login involves at least two distinct steps:

~~~text
RP App -> Authorization Server
       -> Callback /login/oauth2/code/{registrationId}
       -> Authenticate and create Authentication
       -> Post-login redirect to application page
~~~

- **OAuth2 `redirect_uri`**: callback from the authorization server back to the client; must be pre-registered or policy-verified at the authorization server. Never turn it into an arbitrary browser-supplied value.
- **Post-login redirect**: the website choosing which page the user sees after callback authentication finishes, such as a dashboard or saved request.

If using Spring Security `oauth2Login()` with a custom success handler, that handler remains subject to the target allowlist. OAuth `state`/`nonce` bind the login/authorization protocol exchange—they **do not** make an arbitrary `next` parameter safe.

With SAML, `RelayState` typically carries correlation/state; never take an untrusted value as an arbitrary redirect URL after processing `SAMLResponse`. All identity assertions must be verified before performing business redirects.

## 12. SPAs, deep links, and browser storage

SPAs often want to return to the active route after login:

~~~text
/checkout/confirm -> show login -> sign in -> /checkout/confirm
~~~

Browsers may store the intended route in `sessionStorage`, router state, or URL parameters. Because browser storage is client-controlled, **it is not a trust anchor**. When navigating in the frontend:

- Allow only internal routes present in the router allowlist.
- Never execute `window.location = untrustedNextUrl`.
- If a route includes an order ID, validate the identifier, encode path segments properly, and keep path templates fixed.
- Backend must check order/tenant permissions at the API endpoint.
- Never put login tokens, authorization codes, or secrets into route URLs.
- Clear intended state after use and handle multiple tabs deliberately.

For complex deep links needing strong assurance, the server can issue a **random flow ID** and store the approved intended path in session/Redis with TTL and account/session binding. The browser submits the flow ID after login and the server looks up the target; the flow ID is not a URL.

### Referer is not proof of a valid target

The `Referer` header can be stripped by browser privacy policies, come from external sites, or be forged by non-browser clients. Do not enable `setUseReferer(true)` for redirect targets without controls. Turning it on blindly opens another untrusted target vector.

## 13. Checking the URL and checking permissions are two separate steps

A URL can be **internal yet forbidden for the user**. For example, after login `user:lan` lacks admin rights, yet the session holds `/admin/users`. Even though `/admin/users` is same-origin, the resource must return 403 or the app must fall back.

Conversely, a user holding `ROLE_ADMIN` must never be redirected to a phishing site. Two layers exist:

1. **Redirect target allowlist**: are the target source and URL valid?
2. **Authorization**: does the user have permission for that endpoint, tenant, and resource?

Scenario:

~~~text
Current principal: user:lan (tenant A)
Saved URL:         /tenants/B/invoices/123

Target policy: path may belong to the app
Resource policy: user lacks tenant B permission
Decision: reject/fallback per product, never grant B access
~~~

Merely succeeding at login does not enforce tenant isolation. Enforce checks in services/repositories/queries, not just in login success handlers.

If the app uses multi-stage MFA/step-up, never redirect to a sensitive action while treating "valid password" as completing all authentication factors.

## 14. Concerns involving sessions, CSRF, and reverse proxies

**SecurityContext:** use only `Authentication` verified by a provider; never grant roles from query params, self-asserted role claims, or route keys. Redirects do not replace authorization filters.

**Session fixation:** Spring Security enforces session protection on login; if caching a target before login, decide whether the request cache remains valid after session rotation. Avoid letting a saved target from an old flow/user apply to a new account.

**CSRF:** with form login/session cookies, enforce browser-model CSRF protection. Never treat "`POST /login` succeeded" as a reason to disable CSRF across endpoints.

**Trusted forwarded headers:** SSL termination/proxies can make the backend see `http://internal:8080` while the public URL is `https://shop.example.org`. Configure proxy header trust and a public domain allowlist. Never infer base redirect URLs from unvetted Internet headers.

**Sensitive queries:** never place passwords, access tokens, session IDs, or password-reset tokens in `Location`. Avoid logging redirect targets carrying secrets or PII; log route IDs and correlation IDs for auditing when possible.

**Redirect loops:** never select login, logout, callback, or recovery endpoints as the default target; test for loops when a target triggers the authentication entry point again.

## 15. Testing Location instead of checking only 302

A test suite must inspect the **final `Location` response** of auth success. Asserting status 302 alone misses external redirects.

| Case | Expected |
| --- | --- |
| Normal login without target | `/dashboard` |
| Valid `destination=orders` | `/orders` |
| Unknown route key | Safe fallback |
| Target `https://evil.example` | Must not appear in `Location` |
| Target `//evil.example` | Must not appear in `Location` |
| Backslash/encoded slash/double encoding | Reject/fallback |
| Forged `Host`/`Forwarded` | Must not redirect to attacker host |
| Valid saved request from same session | Returns to valid path |
| Saved request from old session/tenant | Must not be used against policy |
| User lacking admin rights | No access to admin resource |
| Valid URL but resource belongs to another tenant | 403/404 or fallback per policy |
| Auth failure | Does not invoke success redirect |
| OAuth2/SAML callback | Rejects untrusted `next` URLs |
| URL with control chars | Causes no header injection |
| HTTP scheme on external target | Rejected if HTTPS-only |
| SPA route carrying token in query | Never leaks token into `Location`/logs |
| Proxy deployed under context path | Redirect uses right public path/host |

### MockMvc test snippet

In Spring Boot Servlet with Spring Security Test and a configured test user:

~~~java
var response = mockMvc.perform(
        post("/login")
                .param("username", "lan")
                .param("password", "correct-password")
                .param("destination", "https://evil.example")
                .with(csrf()))
        .andReturn()
        .getResponse();

assertEquals("/dashboard", response.getRedirectedUrl());
~~~

This is a **test snippet**, requiring static imports `post`, `csrf`, `assertEquals`, plus MockMvc, Spring Security chain, and valid login credentials setup. It tests the route-key handler config presented earlier; it does not run standalone with `javac`.

Under a different context path, expected redirects may carry a prefix. For OAuth2/SAML, test real callback flows; form-login tests do not prove every handler is safe.

### Non-HTTP-status test properties

- Verify `Location` with a URL parser and exact expected host/path.
- Test forged `Host` or `Forwarded` headers right at the reverse proxy in test environments.
- Check resource permissions after following the redirect.
- Test saved request lifecycles, concurrent tabs, and session timeouts.
- Write tests for logins where the user switches accounts/tenants in the same browser.

## 16. Common pitfalls and fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Always goes to dashboard instead of deep link | `alwaysUseDefaultTargetUrl=true` | Decide UX; update config if saved requests are desired |
| Redirects to foreign domain | Untrusted `next`/Referer/Host/forwarded headers | Switch to route keys and fix proxy trust |
| Target parameter ignored | Handler prioritizes default/saved request | Check handler ordering and active config |
| Deep link lost after login | `RequestCache` disabled, session state lost | Inspect `RequestCache`/session lifecycle |
| 403 right after login | Target is valid yet lacks permissions | Check resource authorization; do not loosen permissions |
| HTTPS downgraded to HTTP | Wrong base URL/proxy scheme | Fix trusted forwarded headers |
| Redirect loop | Target also requires auth, cookie dropped | Check sessions, security matchers, targets |
| App under context path hits 404 | Wrong path/context concatenation | Use Servlet context path; test public URLs |
| Client bypasses with encoded URLs | Regex/repeated decoding | Use route keys only or strict parser/allowlist |
| Another tenant receives deep link | Saved state ignores tenant | Revalidate user/tenant/resource |
| Logout/OAuth callback set as target | Routes unrestricted | Exclude sensitive endpoints from allowlists |

When debugging, log the target selection source (default, saved request, route key), approved route name, and allow/deny decision. Never write unescaped raw attacker URLs, session cookies, or token-bearing queries into unprotected logs.

## 17. Pre-implementation design checklist

1. Can **one fixed internal URL** be used after login?
2. If multiple pages are needed, are **server-side mapped route keys** used instead of client-sent URLs?
3. If using `SavedRequest`, have session binding, scheme/host/port origin, request method, and tenant/account been verified?
4. Were `targetUrlParameter` or `setUseReferer(true)` accidentally enabled without an allowlist?
5. If real `returnUrl` is supported, are scheme-relative, userinfo, prefix-host, backslash, double encoding, and scheme downgrade blocked?
6. Are both target policy and resource access permissions enforced?
7. Are spoofed `Host`/`Forwarded` blocked at proxies and direct backend bypasses restricted?
8. Are tokens/credentials/secrets kept out of `Location` and audit logs?
9. Are CSRF/session fixation/step-up policies preserved properly?
10. Have `Location` and resource access been tested across form login and OAuth2/SAML (if used) with both valid and malicious inputs?

**Conclusion:** Post-login redirects should go only to **URLs within the server's trusted policy**. Prefer fixed URLs; use route keys when choices are needed; manage `SavedRequest` and verify host/session origin when deep links are required; and allowlist scheme/host/port/path whenever external URLs are unavoidable. Spring Security manages authentication and redirect flows, yet the application remains accountable for every permitted target and destination-page permissions.

### References

- Spring Security — Form Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html
- Spring Security — AbstractAuthenticationTargetUrlRequestHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationTargetUrlRequestHandler.html
- Spring Security — RequestCache: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/savedrequest/RequestCache.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OWASP — Unvalidated Redirects and Forwards Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html
- CWE-601 — URL Redirection to Untrusted Site: https://cwe.mitre.org/data/definitions/601.html
