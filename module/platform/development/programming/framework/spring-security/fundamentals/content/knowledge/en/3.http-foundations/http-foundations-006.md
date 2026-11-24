# Redirects, post-login return URLs, and unsafe redirect risks

Mai opens `/reports/42` while not logged in. The application redirects Mai to `/login`; after Mai authenticates successfully, the application brings her back to `/reports/42` instead of starting from the home page. This is a very common experience in web applications with Spring Security.

However, an important question is: **who decides the target URL after login?** If the application takes the raw `returnUrl`, `next`, or `redirect` value sent by the user and puts it directly into the `Location` header, a malicious actor can make a link on a trusted website redirect visitors to a spoofed website. That is an **open redirect**, also called an **unvalidated redirect**.

This lesson explains from HTTP foundations to Spring Security's mechanism for remembering the original request, how to control return URLs, and how to avoid turning login into a relay point to untrusted addresses.

## 1. What is a redirect? What does the browser actually do?

In HTTP, a redirect is a **response with a redirect status code and usually a `Location` header**. The client receives the response and can then send a **new** request to the specified address. A redirect differs from the server fetching data and returning it directly: the address in the browser can change, and the subsequent request is a separate HTTP round-trip.

Example:

~~~http
GET /reports/42 HTTP/1.1
Host: learning.example
~~~

~~~http
HTTP/1.1 302 Found
Location: /login
Cache-Control: no-store
~~~

The browser processes the response, then sends a new request:

~~~http
GET /login HTTP/1.1
Host: learning.example
~~~

The key here is that **`Location` specifies the redirect destination**; the status code indicates how to handle the redirect. `/login` is a relative path against the current origin, whereas a full URL like `https://other.example/login` can take the user to a different origin.

### Common status codes

| Code | Meaning | Things to remember |
| --- | --- | --- |
| `301 Moved Permanently` | Moved permanently | May be cached; historical differences exist in method handling after redirect for non-GET requests |
| `302 Found` | Temporary redirect | Commonly seen in login/form flows; browsers may change POST to GET depending on implementation |
| `303 See Other` | Redirect to a resource to GET | After POST, the next request uses GET; fits the Post/Redirect/Get pattern |
| `307 Temporary Redirect` | Temporary redirect preserving method | **Preserves the request method and body** when forwarding to the target |
| `308 Permanent Redirect` | Permanent redirect preserving method | **Preserves method and body**, while carrying permanent semantics |

For example, after receiving a form POST, if you want to display a result page without re-executing the POST on reload, `303` is the clear choice. Be especially careful when using `307` or `308` on requests containing passwords or sensitive data: they tell the client to resend the same method and body to the redirect destination. Never use an untrusted target URL in these cases.

**A redirect does not confirm identity or grant permissions.** The browser arriving at `/reports/42` after login is purely navigation; the server still must authenticate and authorize when handling the new request.

## 2. Why is a post-login return URL needed?

Someone might reach a page requiring authentication via a bookmark, a link from an email, or an internal menu. If not logged in, the application typically wants to:

1. Remember the page or action **requiring authentication**.
2. Redirect to the appropriate login screen.
3. Verify credentials when the user submits the login form.
4. After successful authentication, bring the user back to the resource they intended to open.
5. Evaluate access permissions for the **target resource** against the authenticated identity.

Example:

~~~text
Mai wants to view /reports/42
           |
           v
GET /reports/42  -> unauthenticated
           |
           v
Save original request via RequestCache mechanism (if enabled)
           |
           v
HTTP 302 Location: /login
           |
           v
Mai logs in successfully
           |
           v
HTTP redirect to /reports/42
           |
           v
GET /reports/42 (new request)
           |
           v
Check actual permission on report 42
           |
    +------+------+
    |             |
  Allow      Deny (e.g., 403)
~~~

This is proper behavior when the user is allowed to view the resource. If Mai logs in successfully yet **does not have permission to view report 42**, the application must still deny her at the final step. "Being returned to the original path" is completely different from "being granted permission to that path."

Another scenario is Mai intentionally opening `/login` from the home page when no request has been saved. After login, the application needs a sensible **default destination**, such as `/dashboard`.

## 3. How does Spring Security remember the original request?

In a **servlet** application with login-page-based authentication, Spring Security has notable components:

- **`ExceptionTranslationFilter`**: detects situations where a request hits a resource needing authentication or is denied, coordinating with `AuthenticationEntryPoint` and request-saving mechanisms.
- **`AuthenticationEntryPoint`**: directs unauthenticated users into the login process; with form login this typically leads to a redirect to the login page.
- **`RequestCache`**: abstraction for saving/reading the request to return to, such as `HttpSessionRequestCache` storing info in the HTTP session.
- **`SavedRequest`/`DefaultSavedRequest`**: represents the saved request, containing info to restore the destination.
- **`AuthenticationSuccessHandler`**: handles post-authentication success, which can redirect to the chosen target.
- **`SavedRequestAwareAuthenticationSuccessHandler`**: a success handler supporting retrieving the URL from SavedRequest to return to where the user intended to go.

The request cache mechanism depends on **actual configuration**. Not every unauthenticated request is saved; a stateless API application might not use sessions/request cache, or might return `401 Unauthorized` instead of redirecting to an HTML page. The above describes the common servlet flow, not a guarantee for every authentication method.

### RequestCache is not simply a `next` string in the URL

With `HttpSessionRequestCache`, the application can store the original request server-side tied to the session, and reuse it after login. This differs from placing `?next=https://... ` decided by the client and immediately trusting that value.

Simulated example:

~~~text
GET /private/report/42 (unauthenticated)
    -> ExceptionTranslationFilter detects authentication needed
    -> RequestCache saves original request URL
    -> redirect /login

POST /login (authentication succeeds)
    -> AuthenticationSuccessHandler finds SavedRequest
    -> redirect /private/report/42

GET /private/report/42 (authenticated)
    -> Spring Security checks Authentication and permissions
    -> succeeds or denies per policy
~~~

A remembered URL can contain the path and query string of the original request; therefore do not put passwords, verification codes, or other secrets in URLs. Data in queries can appear in history, logs, monitoring tools, or referrer headers in certain situations.

### Target selection order in SavedRequestAwareAuthenticationSuccessHandler

With the documented behavior of `SavedRequestAwareAuthenticationSuccessHandler` (when using the corresponding default configuration), target selection has these main branches:

| Condition | Selected target |
| --- | --- |
| `alwaysUseDefaultTargetUrl=true` | Always use `defaultTargetUrl`; any saved SavedRequest is cleared |
| `targetUrlParameter` is configured and the request sends a valid parameter value per handler conditions | Use the parameter value as target; SavedRequest is cleared |
| Neither of the above and SavedRequest exists | Return to the URL of SavedRequest |
| No suitable SavedRequest exists | Use base class behavior, typically `defaultTargetUrl` |

This order is useful when diagnosing "after logging in, it didn't return to the page just opened." For instance, `alwaysUseDefaultTargetUrl=true` intentionally ignores the saved request; a custom success handler can also completely override default behavior.

**Security note:** if enabling target extraction from a request parameter, never assume a client-supplied parameter is safe simply because it sits inside a Spring Security flow. Navigation targets need a clear source-validation policy. The simplest approach is letting the server choose from predefined destinations.

## 4. Configuring Spring Security servlet for a default page

The following example illustrates a `SecurityFilterChain` in a Spring Boot application with Spring Security. This is a code snippet belonging to a Spring application; running it requires web config, users/providers, and appropriate dependencies.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/dashboard", false)
                .permitAll()
            );

        return http.build();
    }
}
~~~

Explanation:

- `/login` and static resources are permitted before logging in. When choosing `loginPage("/login")`, the application is responsible for providing the GET `/login` page and an appropriate form.
- `/admin/**` requires role `ADMIN`; redirecting to this URL does not grant admin rights by itself.
- `defaultSuccessUrl("/dashboard", false)` sets a default destination without **forcing SavedRequest to be ignored**. If a suitable original request was saved, the default flow can return there.
- Changing it to `defaultSuccessUrl("/dashboard", true)` means **always navigating** to `/dashboard` after success, even if an original request was saved.
- `permitAll()` on form login allows login-serving endpoints to be used while unauthenticated; it does not open all private resources.

`false` in the method above opts into the return-to-original-page experience. Applications wanting a fixed screen after every login can use `true`. Choose intentionally per business requirements rather than being surprised by default behavior.

### Custom success handlers change behavior

A custom `AuthenticationSuccessHandler` can decide `Location` itself after authentication. It can also **bypass SavedRequest logic** if it does not invoke or re-implement request cache usage. Thus when debugging, locate the actual handler configured for the login mechanism.

Do not write code like this in a real application:

~~~java
// UNSAFE EXAMPLE: returning the raw client-specified URL.
String target = request.getParameter("next");
response.sendRedirect(target);
~~~

The `next` value comes from the user or a link crafted by someone else. Without validation, this snippet can redirect to an untrusted domain. The issue is not limited to `sendRedirect`: placing that value into the `Location` response header by any means creates the same risk.

## 5. Open redirect: an untrusted destination slips into Location

Suppose an application has an endpoint:

~~~text
https://learning.example/login?next=/dashboard
~~~

The `/dashboard` target is an internal page. But if the `next` parameter is accepted unconditionally, a malicious actor can share a URL whose starting domain looks just like the real website yet after login leads to a different website:

~~~text
https://learning.example/login?next=https%3A%2F%2Foutside.example%2Ffake-login
~~~

After the user sees `learning.example` and interacts, the browser may receive:

~~~http
HTTP/1.1 302 Found
Location: https://outside.example/fake-login
~~~

The next page belongs to `outside.example`, which can mimic the UI to trick the user into re-entering their password, one-time password, or personal information. This is a classic phishing scenario via open redirect.

**Do not infer that `learning.example`'s session cookie is automatically sent to `outside.example`.** Browsers still enforce cookie/domain scope. The direct risk of an open redirect is routing to an untrusted destination; it can also be a link in other vulnerability chains when combined with loosely designed authentication, callback, or token flows.

### Why are naive string checks not enough?

Suppose the application only checks:

~~~java
// WRONG EXAMPLE: startsWith does not prove a trusted host.
if (next.startsWith("https://learning.example")) {
    response.sendRedirect(next);
}
~~~

The string `https://learning.example.outside.test/path` also has the prefix `https://learning.example`, yet **the real host is `learning.example.outside.test`**.

Input forms to watch out for:

| User input | Problem when used as navigation target |
| --- | --- |
| `https://outside.example/login` | External absolute URL |
| `//outside.example/login` | URL starting with two slashes, which can use an external host under the current scheme |
| `https://learning.example.outside.test/x` | Different host despite matching prefix with trusted host |
| `https://learning.example@outside.example/x` | Part before `@` is user-info; actual host is after `@` |
| `/../admin` or encoded path variants | Risk of path normalization diverging from check intent; does not replace authorization |
| Values with backslashes, control characters, or multiple layers of percent-encoding | May be interpreted or normalized differently by clients/frameworks/redirect handlers |

Checking `startsWith("/")` alone is also not enough to prove a path is internal because of the `//host` case. Rejecting only `http` strings is also insufficient due to scheme-relative URLs and variants. Do not write a short regex yourself and conclude it handles all ways browsers parse URLs.

Open redirect flaws also relate to using a redirect as a **trusted intermediary page**. Another system might allow callback/return URIs pointing to your domain; if that domain allows unconditional external redirects, it can break security assumptions of the integration flow. Hence OAuth/OIDC callback and redirect URI design must be strict, even though this lesson focuses on standard post-login redirects.

## 6. Principles for choosing a safe return URL

Priority order in practical design should be:

1. **Do not accept arbitrary URLs** if the business flow only needs a few known screens. Use a route key like `orders`, `profile`, `dashboard` and map it server-side to an internal path.
2. When needing to return to a pre-login request, use an appropriate **SavedRequest/RequestCache** mechanism controlled by the application, while also protecting host config, proxies, and how URLs enter the system.
3. If a client-supplied URL must be accepted, use a **standard parser**, an explicit destination policy, normalization compatible with how redirect components/browsers interpret it, and only use the **verified value** to construct the response.
4. For external URLs genuinely required by the business, use an allowlist of host/scheme/port and path as required; consider an interstitial page warning users they are leaving the site.
5. If input is malformed/invalid/disallowed, **reject it or fall back to a fixed default target**. Do not try to sanitize a suspicious string and hope it becomes safe.

Verify simultaneously:

- **Scheme**: only `https` for external targets when security requires it; forbid `javascript:`, `data:`, or exotic schemes.
- **Host**: exact match on normalized host, no ambiguous prefix or suffix comparisons.
- **Port**: evaluate effective port per policy; do not treat every port on a host as your own application.
- **User info**: reject confusing `user@host` forms when unneeded.
- **Path**: restrict to allowed routes; check variants where percent-encoding, slashes/backslashes, and normalization might interfere.
- **Query/fragment**: do not let secrets or a "nested inner URL" loop around to another address unchecked.
- **Host trust source**: do not concatenate unverified `request.getHeader("Host")` or `X-Forwarded-Host` from outside reverse proxies to construct return URLs.

An **internal** URL is not necessarily a URL the user **has permission to open**. After redirecting, the server must still enforce authorization as usual. For example, an employee without an admin role is still denied at `/admin`, even if that target is on a list of internal paths.

## 7. Standalone Java 17+ example: server-side route key mapping

This example **does not implement a login mechanism**; it isolates the target URL selection decision. The user may only send a *route key*, while the list of valid target paths is defined by the application. All other inputs fall back to the default page. As a result, the application never directly inserts a query-supplied URL into `Location`.

Create file `SafeReturnDestinationDemo.java`:

~~~java
import java.util.Map;

public class SafeReturnDestinationDemo {

    private static final Map<String, String> ROUTES = Map.of(
            "dashboard", "/app",
            "orders", "/app/orders",
            "profile", "/app/profile");

    static String destination(String routeKey) {
        if (routeKey == null) {
            return ROUTES.get("dashboard");
        }
        return ROUTES.getOrDefault(
                routeKey, ROUTES.get("dashboard"));
    }

    public static void main(String[] args) {
        String[] supplied = {
                "orders",
                "profile",
                "https://outside.example/fake-login",
                "//outside.example",
                "../admin"
        };

        for (String key : supplied) {
            System.out.println(key + " -> " + destination(key));
        }

        System.out.println("null -> " + destination(null));
    }
}
~~~

With JDK 17 or higher, from the same directory as the created file, run:

~~~bash
javac SafeReturnDestinationDemo.java
java SafeReturnDestinationDemo
~~~

Exact output:

~~~text
orders -> /app/orders
profile -> /app/profile
https://outside.example/fake-login -> /app
//outside.example -> /app
../admin -> /app
null -> /app
~~~

Explanation: `orders` and `profile` are valid route keys defined by the server, so they map to their corresponding paths. The remaining values are not in `ROUTES` and all fall back to `/app`. There is no parsing or "sanitizing" of external URLs because the application **does not allow free-form URL input in the first place**.

This is a technique to prevent open redirects at destination selection, **not an authorization system**: users still must have permissions checked when accessing `/app/orders` or `/app/profile`. If routes include resource IDs, a document's `documentId` or `tenantId` must also undergo separate permission checks; you cannot simply put arbitrary URLs in `ROUTES` and consider that safe enough.

## 8. Integrating route keys into a success handler when truly needed

For a website needing only three predefined landing pages, a route key can be selected after login in a custom success handler. The snippet below goes **inside the `formLogin` configuration of a Spring Security servlet application**, not a standalone Java program:

~~~java
.formLogin(form -> form
    .successHandler((request, response, authentication) -> {
        String key = request.getParameter("destination");

        String path = switch (key == null ? "" : key) {
            case "orders" -> "/app/orders";
            case "profile" -> "/app/profile";
            default -> "/app";
        };

        response.sendRedirect(request.getContextPath() + path);
    })
)
~~~

The targets in `switch` are server-controlled constants. Users cannot pass `destination=https://outside.example` to make the code select an external host. In production code, protect data sources, apply URL/context paths, and follow appropriate logging policies.

**What is the trade-off?** A custom handler like above **does not automatically restore SavedRequest**. A user visiting a private page before login will not be returned to that page if the handler only looks at the route key. If the application wants both features, a clear precedence order must be designed: for example, valid server-saved SavedRequest first, then verified route key, and finally the default target. Do not carelessly mix target sources that lack the same trust level.

### Why not just use Referer as the return URL?

The `Referer` header may be absent, restricted by `Referrer-Policy`, or come from a context the application cannot trust as an authoritative source. If `Referer` is used as a UX signal, it still must pass the same destination validation policy. **Do not use raw `Referer` as a redirect URL merely because it is present in the request.**

### How does OAuth2/OIDC login differ?

OAuth2/OIDC mechanisms also involve a redirect URI between the application and the identity provider. `redirect_uri` in the protocol must be registered/validated per provider and application rules. The URL **returning the user to an internal page after login completes** is a separate decision from the protocol's callback URI.

Do not use an arbitrary `next` to alter the callback URI, and do not send authorization codes, access tokens, ID tokens, or session credentials to a user-specified URL. Separating these two target types helps avoid bugs combining open redirects with federated login flows.

## 9. Common pitfalls when testing login

### 9.1. Reaching the login page directly differs from being intercepted at a private page

- User opens `/reports/42` while unauthenticated: RequestCache can remember that request; after success returns to `/reports/42`.
- User visits `/login` directly: there may be no SavedRequest; handler uses the default target.
- If still redirected to an old page even after clicking login from the home page, check the session's SavedRequest and session clearing/rotation policy.
- If `alwaysUseDefaultTargetUrl=true`, SavedRequest may be intentionally ignored.

### 9.2. A pre-login POST request does not mean automatic replay

Do not assume an intercepted POST form will have its body replayed intact after authentication. Browser redirect flows depend on status codes, request caches, request types, and business design. For write operations, handle authentication explicitly first, save valid drafts if needed, control CSRF, and perform the write after sufficient permissions are confirmed. **Do not ask the user to log in and then auto-replay a side-effecting operation without verification.**

### 9.3. APIs typically need different responses than HTML pages

A browser navigating to an HTML page understands a 302 to `/login`. However, REST APIs/SPAs may need `401` or `403` per state and API contract, so the client can proactively render a login screen. If an API redirects to HTML automatically, the client may receive a login page instead of JSON, causing response parsing errors. Choose `AuthenticationEntryPoint` and success handlers to fit the client type.

### 9.4. Wrong paths, loops, and expired sessions

When `/login` also requires authentication, the configuration can create a redirect loop. When SavedRequest points to a URL that no longer exists, the browser may receive 404 after login. When the session holding SavedRequest is lost, the application no longer has return info and usually falls back to the default target. When configuration changes context paths/reverse proxies, the target URL may get an unexpected scheme, host, port, or path.

These bugs must be inspected step by step via Network, not fixed by unconditionally trusting a `next` parameter from the client.

## 10. Testing procedure in browser and HTTP

You can use DevTools → Network (enable Preserve log to see the 302 chain) to trace the flow. Inspect **status**, **`Location`**, cookies/sessions, and new requests; do not look only at the final page.

The test suite should include:

| Scenario | Expected behavior |
| --- | --- |
| Unauthenticated user opens `/reports/42` | Enters authentication flow when needed; original request may be saved |
| Successful login with valid SavedRequest present | Returns to `/reports/42` if policy allows |
| Opening `/login` directly and logging in successfully | Goes to appropriate default page |
| Configured `defaultSuccessUrl("/dashboard", true)` | Always returns to `/dashboard` per config |
| Logged-in user without permission for `/reports/42` | Still denied when the new request is processed |
| `destination=orders` with allowed route key | Only redirects to `/app/orders` |
| `destination=https://outside.example` | Rejected/fallback; does not redirect to external host |
| `destination=//outside.example` | Rejected/fallback; does not treat `//` as internal path |
| `destination=https://learning.example.outside.test` | Rejected/fallback; does not rely on hostname prefix check |
| Target requires admin rights while regular user logs in | Redirect does not elevate privileges; target must deny |
| No SavedRequest left due to expired session | Uses default target; does not rely on stale state |
| Browser/URL with query containing sensitive token | Never leak tokens into history, logs, or external Location |

If proxies are configured, test requests with `Host` and forwarded headers as permitted by the deployment environment. Server-generated URLs must be based on trusted origins, not unverified arbitrary headers. When integrating OAuth2/OIDC, separately test callback redirect URIs against the registered URI list.

## 11. Common mistakes

1. **"Successful login means allowed into the return URL."** False: the target request still requires authorization.
2. **"`returnUrl` is our app's parameter so it's always trustworthy."** False: outsiders can edit queries, forms, or shared URLs.
3. **"A URL starting with our domain name is safe."** False: `learning.example.outside.test` has a different host.
4. **"A string starting with `/` is definitely internal."** False: `//outside.example` is a URL form with an external host.
5. **"Just block `http://`."** False: there are `https://`, `//`, other schemes, and formatting variants.
6. **"SavedRequest means Spring Security authorizes the target."** False: SavedRequest remembers the request; authorization still runs on the new request.
7. **"Setting `defaultSuccessUrl` always ignores SavedRequest."** Not quite: the `alwaysUse` argument controls this.
8. **"Redirecting with 307 after POST login is the same as 303."** False: 307 preserves method and body; 303 requires GET.
9. **"An open redirect definitely leaks session cookies to another host."** False regarding default cookie mechanics; the primary risk is unintended redirection and related attack chains.
10. **"Hiding external links on the frontend is enough."** False: the server still must control `Location`.
11. **"Allowing redirect to `/admin` means the user has admin permissions."** False: permissions must be checked at the target endpoint.
12. **"Seeing no redirect in controller code means there isn't one."** Not necessarily: security filters, authentication entry points, and success handlers can also issue redirects.

## 12. Self-check thinking questions

**Question 1.** Mai opens `/reports/42` while not logged in. After logging in, the browser opens `/reports/42`. Which Spring Security components may have been involved?

*Answer:* In a standard servlet flow, `ExceptionTranslationFilter` coordinates with `AuthenticationEntryPoint` and `RequestCache` to save the request; after success, `SavedRequestAwareAuthenticationSuccessHandler` picks the URL from SavedRequest. The new request still goes through authorization.

**Question 2.** Why might `defaultSuccessUrl("/dashboard", false)` not send the user to `/dashboard`?

*Answer:* Because a valid SavedRequest may still exist; in that case the handler uses the original URL. With `true`, the default target is chosen even if a saved request exists.

**Question 3.** A URL parameter is `//outside.example/path`. Why should it not be allowed through a `startsWith("/")` condition?

*Answer:* Double slashes `//` can denote the authority/host of a scheme-relative URL; the browser may navigate to another website.

**Question 4.** How can a system with only three post-login landing pages avoid handling free-form URLs?

*Answer:* Have the client send a defined route key, let the server map the key to one of the three fixed paths, and fall back to the default page. Targets still must be authorized.

**Question 5.** A logged-in user is redirected to `/admin` yet receives `403`. Is this a redirect bug?

*Answer:* Not necessarily. The redirect took the browser to the exact URL; the authorization policy at `/admin` then denied access due to missing permissions.

**Question 6.** Why is using `307` to redirect a login POST to a suspicious external URL more dangerous than a regular GET redirect?

*Answer:* `307` tells the client to preserve method and body; the POST data can be sent to the new target. Never use untrusted targets, especially for requests containing credentials.

**Question 7.** Can you take the raw `Referer` of a login request and use it as `Location` after success?

*Answer:* You should not. Referer may be missing or untrustworthy and must be checked against the same target policy as any other untrusted input.

When building login flows, separate three decisions: **(1) is the user authenticated, (2) which URL is permitted as the post-authentication destination, and (3) does the user have permission to access the resource at that destination.** Succeeding at authentication does not answer the latter two questions automatically.

### References

- [Spring Security — SavedRequestAwareAuthenticationSuccessHandler](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html)
- [Spring Security — RequestCache](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/savedrequest/RequestCache.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [MDN — Redirections in HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Redirections)
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html)
