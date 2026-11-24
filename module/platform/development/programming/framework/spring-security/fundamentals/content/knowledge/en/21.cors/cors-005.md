# Credentials, Cookies, and the Limits of Wildcard Origins in CORS

Suppose a frontend at `https://portal.example.test` calls an API at `https://api.example.test`. The user is already signed in with a cookie, yet the browser still reports a CORS error when the API returns `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Credentials: true`. **That combination of headers is invalid for a request with Fetch credentials mode `include`**: JavaScript can read the response only when the server confirms **a specific trusted origin** and allows credentials.

Three components must be understood separately:

- **CORS (Cross-Origin Resource Sharing)**: policy by which the browser decides whether a script from one origin can read responses from another origin.
- **Credentials**: cookies, HTTP authentication, TLS client certificates, and how the browser sends/receives them. With Fetch, `credentials` determines behavior.
- **Cookie policy**: `SameSite`, `Secure`, `Domain`, `Path`, `HttpOnly`, and policies blocking or partitioning third-party cookies. CORS allowance does not guarantee cookies are sent or stored.

In Spring Security Servlet, CORS must be integrated before authentication checks so preflight requests are not wrongly rejected, while preserving proper authentication, authorization, and CSRF policies for cookie-based APIs. This lesson focuses on evaluating, configuring, and fixing CORS issues involving **credentials, cookies, and wildcard origins**.

## 1. When are origins different?

An **origin** is defined by **scheme, hostname, port**. Differing in just one component makes it cross-origin:

| Frontend | API | Same origin? |
|---|---|---|
| `https://portal.example.test` | `https://portal.example.test/api` | Yes |
| `https://portal.example.test` | `https://api.example.test` | No — different hostname |
| `http://localhost:5173` | `http://localhost:8080` | No — different port |
| `http://app.example.test` | `https://app.example.test` | No — different scheme |
| `https://app.example.test` | `https://app.example.test:8443` | No — different port |

The request value is typically `Origin: https://portal.example.test`, **containing no path**. Do not configure `allowedOrigins` with a URL like `https://portal.example.test/dashboard` or omit the scheme. If multiple origins are allowed, the server selects **one matching origin** for the ACAO response header; do not put a comma-separated list in the same header.

**Same-origin differs from same-site.** `portal.example.test` and `api.example.test` may belong to the same *site* while remaining cross-origin. Hence `SameSite=Lax` may permit cookies on a same-site request, while cross-origin Fetch still requires `credentials: "include"`. Do not conclude from “same main domain” that CORS is unnecessary.

CORS is a browser-enforced mechanism for scripts and certain resources in cross-origin contexts. HTTP clients such as `curl`, Java `RestClient`, or typical backend services **do not enforce CORS like a browser**, so CORS is not an authentication/authorization layer protecting resources from every client.

## 2. CORS grants response-reading permission, not login permission

At the HTTP layer, an API may return:

```http
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

- `Access-Control-Allow-Origin` (ACAO) indicates the origin permitted to read the response. With credentials, the value must be a specific origin matching the request, not `*`.
- `Access-Control-Allow-Credentials` (ACAC) with the exact value `true` tells the browser the response may be used in credentials mode, provided other checks pass.
- `Vary: Origin` helps caches understand that the response/ACAO header can change based on request Origin. Important when CDN/proxy caching is present.

**CORS does not create cookies, authenticate users, grant business permissions, or protect endpoints from non-browser clients.** The API must still validate tokens/cookies, enforce access permissions, and avoid exposing another account's data.

It is also essential to distinguish **a sent request** from **a response read by JavaScript**. An HTML form POST is a simple request that can be sent by the browser to the server before the browser blocks the script from accessing the response due to CORS. If the server already updated data, a CORS error does not undo the side effect. This is why CORS **does not replace CSRF protection**.

## 3. Fetch credentials mode: omit, same-origin, include

Frontend code commonly calls APIs using `fetch`. The `credentials` field governs whether the browser sends cookies/HTTP credentials and processes cookies set in the response:

| Mode | Behavior |
|---|---|
| `omit` | Does not automatically send credentials and does not accept credentials from responses under Fetch rules |
| `same-origin` | Default; credentials are only sent and used for same-origin requests |
| `include` | Requests sending credentials even cross-origin, while the browser still enforces `SameSite`, third-party cookie limits, and CORS |

Example of a cross-origin frontend asking the browser to attach API cookies:

```javascript
const response = await fetch("https://api.example.test/api/me", {
  method: "GET",
  credentials: "include"
});

if (!response.ok) {
  throw new Error("API status: " + response.status);
}

const user = await response.json();
console.log(user);
```

If the frontend calls from `https://portal.example.test`, the browser needs a matching ACAO (such as that origin) and ACAC `true`. Even with correct CORS, cookies can still be **absent** if there is no cookie for the API hostname, or due to `Domain`/`Path`, `SameSite`, `Secure`, or third-party cookie blocking.

Do not mistake `credentials: "include"` for **creating a login cookie** or **forcing the browser to bypass cookie policies**. It is a JavaScript-side request option and does not guarantee a valid session or cookie on the server.

With `XMLHttpRequest`, the corresponding API is setting `xhr.withCredentials = true` before sending the request.

### What about a Bearer token in a header?

```javascript
await fetch("https://api.example.test/api/me", {
  headers: { Authorization: "Bearer EXAMPLE_ACCESS_TOKEN" }
});
```

An `Authorization` header set explicitly by a script normally makes a cross-origin request require **preflight**. However, the rule forbidding wildcard ACAO with credentials relates to **Fetch credentials mode `include`**, not merely the presence of the `Authorization` header: when mode is not include and no browser auto-sent cookies are involved, wildcard ACAO can be accepted by the browser if preflight/header policies match. The resource server must still validate the access token and enforce authorization.

When designing private APIs, allow only trusted origins when personal data or dedicated frontends are involved; do not treat wildcards as a defense against token theft via XSS.

## 4. Why can't origin `*` be used with credentials?

The following response is **invalid for JavaScript sending `credentials: "include"`**:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
Content-Type: application/json

{"name":"Demo","role":"member"}
```

The browser refuses to let the script read the response because ACAO is `*`. Setting ACAC to `true` **does not fix this**. In Spring Framework, configuring `allowedOrigins("*")` together with `allowCredentials(true)` is also treated as an invalid combination; the framework can throw `IllegalArgumentException` when validating the configuration.

**A syntactically valid CORS response**, assuming the request Origin is `https://portal.example.test`:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"name":"Demo","role":"member"}
```

This is only the condition for the browser to read the response under CORS. The API still requires login and authorization, the actual request must be sent, preflight (if any) must pass, and cookies must still be sent under their own rules.

The following matrix assumes all other conditions are valid:

| Fetch mode | ACAO | ACAC | Script reads response? |
|---|---|---|---|
| `include` | `*` | `true` | **No** |
| `include` | `https://portal.example.test` | `true` | **Yes** |
| `include` | `https://portal.example.test` | Missing | **No** |
| `include` | `https://another.example.test` | `true` | **No** |
| `omit` | `*` | Missing | **Yes**, if endpoint is public and other CORS checks pass |
| `same-origin` when calling cross-origin | `*` | Missing | **Yes**, though browser does not auto-send credentials under default mode |

**Do not write `Access-Control-Allow-Origin: https://a.example, https://b.example`.** The ACAO header is a single specific origin or `*` where permitted. The server must match `Origin` against an allowlist and return the single permitted origin.

Do not arbitrarily allow `Origin: null` with credentials on sensitive APIs. The `null` value can originate from opaque-origin contexts such as sandboxed iframes and does not prove the request source is trustworthy.

## 5. Preflight requests differ from actual requests

When the browser wants to send a cross-origin `POST` with `Content-Type: application/json`, `Authorization`, or a custom header like `X-CSRF-TOKEN`, it usually sends `OPTIONS` first:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://portal.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

The server may respond:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PUT, DELETE
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN
Access-Control-Max-Age: 1800
Vary: Origin
```

Once preflight succeeds, the browser sends the **actual request** according to Fetch/cookie policies. Preflight **does not send session authentication cookies of the actual request under Fetch rules**. Therefore Spring Security should handle CORS before authentication; requiring cookies on `OPTIONS` can result in `401 Unauthorized` even when the user's actual request has a valid cookie.

`Access-Control-Allow-Methods` lists **methods of the actual request**, and does not have to include `OPTIONS` merely because preflight uses OPTIONS. The Spring CORS filter recognizes preflight when properly integrated.

For credentialed requests, explicitly restrict **methods** and **headers** rather than defaulting to wildcards. The CORS standard places limits on wildcards in `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and `Access-Control-Expose-Headers` for credentialed requests. Spring Framework may handle wildcard allowed methods/headers by echoing the requested method/header; even so, an explicit allowlist is easier to audit and limits risk.

**A non-preflighted request is not harmless.** An HTML form can submit a POST with `application/x-www-form-urlencoded` and the browser will still attach cookies; CORS may block reading the response, yet it will not necessarily stop the server from performing state changes.

## 6. Cookies: sending conditions remain independent of CORS

| Cookie policy | Meaning | What not to assume |
|---|---|---|
| `Domain` and host-only cookies | Host/scope where cookie is sent | A cookie created by the portal does not automatically apply to a different API hostname |
| `Path` | Request path must fall within cookie scope | Not a policy replacing API access control |
| `Secure` | Restricts sending cookie to HTTPS per browser | Does not authenticate users or prevent CSRF |
| `HttpOnly` | Ordinary scripts cannot read cookie via `document.cookie` | The browser can still send the cookie automatically |
| `SameSite=Strict` | Strongly restricts cross-site cookie sending | Does not mean blocking every cross-origin yet same-site request |
| `SameSite=Lax` | Restricts many unsafe cross-site requests, with browser navigation/default exceptions | Not a CSRF token |
| `SameSite=None; Secure` | Allows cookies in cross-site contexts when other conditions align | Does not bypass third-party cookie restrictions |
| Third-party cookie blocking/partitioning | Browsers may block or partition cookies from third-party sites | ACAO and ACAC do not override privacy policies |

Two easily confused cases:

**A. Cross-origin, same-site:** Frontend `https://portal.example.test` and API `https://api.example.test` have different hosts so they are cross-origin, yet may be same-site. `SameSite=Lax` usually still permits properly scoped cookies in same-site requests. Even so, Fetch needs `credentials: "include"` because they are cross-origin.

**B. Cross-site:** Frontend `https://client.other.test` calls API `https://api.example.test`. When cookies are needed cross-site, `SameSite=None; Secure` is typically required, yet browsers may still block third-party cookies. Even when ACAO, ACAC, and Fetch are all correct, the cookie may still not arrive.

**HttpOnly does not prevent cookies from being sent in fetch.** It stops JavaScript from reading the cookie directly, yet the browser still sends it according to policy. This protects cookie confidentiality against certain XSS vectors reading `document.cookie`, while proper XSS/CSRF defenses remain necessary.

### Are cookies from responses saved?

`Set-Cookie` is managed by the browser according to Fetch and cookie policies. With cross-origin Fetch, `credentials: "include"` governs whether the browser considers accepting cookies from the response; after that, Domain, Path, Secure, SameSite, and third-party policies still apply. `Access-Control-Allow-Credentials: true` does not automatically create or force saving cookies.

One key point: **`Set-Cookie` is a forbidden response-header name**, so JavaScript cannot read it via `response.headers.get("Set-Cookie")` even if the server tries adding `Access-Control-Expose-Headers: Set-Cookie`. Inspect Network/Storage in Developer Tools to verify.

Returning ACAO `*` is not a solution for credentialed cookie flows; the browser rejects the CORS response and will not handle cookies as the frontend expects.

## 7. Spring Security: configuring trusted origins with credentials

In Spring Boot 3 / Spring Security 6 (Servlet + Spring MVC), the standard approach is registering a `UrlBasedCorsConfigurationSource` and enabling `http.cors(...)`. Example for organization-controlled portal/admin frontends:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CredentialedCorsSecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
                "https://portal.example.test",
                "https://admin.example.test"
        ));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"
        ));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .anyRequest().authenticated())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

This is **configuration code inside a Spring Boot application with Spring Web MVC and Spring Security**, not a standalone Java class. `example.test` is an illustrative domain; for real execution you must register actual origins, configure an authentication mechanism, controllers, and CSRF token issuance/validation.

Explanation:

1. `setAllowedOrigins` is an explicit origin allowlist. Do not pass `List.of("*")` when `allowCredentials=true`.
2. `setAllowedMethods` limits methods on actual requests; `setAllowedHeaders` specifies headers allowed at preflight. If the real API uses `Authorization`, add that header to the allowlist under controlled policy.
3. `setAllowCredentials(true)` lets browsers use credentialed CORS when the Origin is permitted; **it does not create cookies or sessions**.
4. `registerCorsConfiguration("/api/**", cors)` limits the policy to API paths. Other endpoints must be evaluated separately.
5. `http.cors(Customizer.withDefaults())` ensures CORS is handled before security authentication in the appropriate chain.
6. `csrf(Customizer.withDefaults())` preserves CSRF protection for browser cookie scenarios. Design corresponding token delivery/handlers for SPAs.
7. `setMaxAge(1800L)` lets browsers cache preflight results up to the policy maximum, not cookie or session lifetime.

When Spring MVC already configures CORS and no separate `CorsConfigurationSource` exists, Spring Security can integrate the MVC configuration. If there are multiple sources and multiple `SecurityFilterChain` beans, assign the source explicitly to the appropriate chain. Avoid overlapping `@CrossOrigin`, global MVC CORS, gateway CORS, and custom `CorsFilter` without verifying actual responses.

## 8. Wildcard origins and `allowedOriginPatterns` in Spring

The following example is a **broken** configuration for credentialed requests:

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true);
```

Spring can throw `IllegalArgumentException` because `allowedOrigins` contains a wildcard while `allowCredentials` is true. Manually adding HTTP response `Access-Control-Allow-Origin: *` does not help because the browser still blocks credentialed responses.

Spring Framework supports:

```java
cors.setAllowedOriginPatterns(List.of("https://*.example.test"));
cors.setAllowCredentials(true);
```

When the pattern matches, Spring can return the **specific matched origin** in ACAO, making it syntactically valid under CORS unlike `ACAO: *`. Yet **syntactic validity does not guarantee security**: a broad pattern can include untrusted subdomains, other tenants, test environments, taken-over hostnames, or areas where external users manage content.

In particular, `allowedOriginPatterns("*")` combined with `allowCredentials(true)` can cause the application to reflect nearly any Origin and allow scripts on arbitrary websites to read user data if the browser sends cookies. That is over-permissive exposure, not a “wildcard workaround”.

**Do not echo `Origin` arbitrarily**. First match the origin against a trusted list; then return a single specific value and add `Vary: Origin` when responses may be cached. Prefer listing explicit origins over wildcard patterns when the set of frontends is finite.

`@CrossOrigin(origins = "*", allowCredentials = "true")` is likewise not a valid choice for credentialed CORS; if using the annotation, configure a controlled list of origins or patterns.

## 9. When can `Access-Control-Allow-Origin: *` be used?

**Yes**, for example on endpoints serving public non-credentialed information where the product intentionally allows scripts from any origin to read responses. When Fetch mode is not `include`, ACAO `*` can be valid if methods/headers/preflight align.

Example public catalog:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Content-Type: application/json

{"items":["book","pen"]}
```

However:

- User-specific private data still requires authentication and authorization.
- `Access-Control-Allow-Origin: *` does not mean everyone bypasses server login.
- Backend-to-backend requests do not need CORS; changing to a wildcard will not fix token/TLS/network errors in a Java service.
- Cross-origin requests containing a JavaScript-set `Authorization` header may still require preflight even without cookies.
- When a frontend needs session cookies, **do not switch to wildcard ACAO** to “avoid errors”.

If one service hosts both public endpoints and private cookie endpoints, apply CORS policies per path or per `SecurityFilterChain`. Do not apply `allowedOriginPatterns("*") + allowCredentials(true)` to the entire API.

## 10. CORS and CSRF: two different decisions

**CORS** controls **script permission to read cross-origin responses**. **CSRF** protects state-changing requests from being triggered by an external page using browser auto-sent credentials.

Suppose a user holds a login cookie for `https://api.example.test`. An external page can submit a form POST to `/api/account/change-email`. The browser will not necessarily allow the attacking page to read the response via CORS, yet if the cookie is sent and the API checks no CSRF token, the email change can still execute.

With cookie/session APIs, CSRF defenses such as a token in a header/form field are normally required, alongside SameSite, Origin checks, or Fetch Metadata as appropriate. `HttpOnly` does not prevent cookies from being auto-sent. A CORS allowlist **is not a CSRF token**.

A truly **Bearer-only** API accepting only `Authorization: Bearer` explicitly attached by the client, with no cookies or other browser-managed authentication, can evaluate disabling CSRF for that exact API scope. That conclusion depends on **how credentials are transported**, not merely because it is `REST`, `JSON`, or `SessionCreationPolicy.STATELESS`.

### Same-site SPA does not mean same-origin

`https://portal.example.test` and `https://api.example.test` can be same-site so SameSite cookies are sent, yet cross-origin for CORS. A compromised subdomain can belong to the same site. Relying solely on `SameSite=Strict` without reviewing request origin and CSRF is therefore insufficient for many designs.

## 11. Distinguishing CORS, cookie, authentication, and CSRF errors

| Symptom | What to check |
|---|---|
| Wildcard ACAO rejected with credentials | `credentials: "include"`, whether the server returns a specific ACAO or `*` |
| Browser reports missing `Access-Control-Allow-Credentials` | Whether the API actually accepts credentialed requests for that origin |
| `OPTIONS` returns 401 | Whether CORS is processed before Spring Security, and whether mappings/sources match |
| Browser reports disallowed header | Whether `Access-Control-Allow-Headers` includes `Content-Type`, `X-CSRF-TOKEN`, `Authorization` as needed |
| Browser gets 401, cookie absent | Fetch mode, cookie host/path, SameSite, Secure, third-party blocking |
| POST reached server yet frontend sees CORS error | Side effect may have run; check network/server logs and CSRF defenses |
| Browser reports CORS error while `curl` works | `curl` does not enforce SOP/CORS; must test with a browser |
| `Set-Cookie` appears yet cookie is not stored | Cookie attributes, Fetch mode, third-party policies, browser Issues |
| 403 on POST when cookie is present | Could be missing CSRF token or insufficient user permissions; must distinguish |
| Only another localhost port fails | Origin includes scheme, hostname, and port; need exact allowlist e.g. `http://localhost:5173` |
| Two ACAO headers or duplicate values | Proxy/gateway and Spring both adding headers; consolidate responsibility |
| API changes origin yet cache serves stale ACAO | `Vary: Origin` or cache configuration needs fixing |

A CORS error may surface as `TypeError: Failed to fetch` even though Network already recorded a response status. The browser prevents the script from inspecting the response body, which does not necessarily mean the server failed to process the request. Check Network and credential-redacted logs.

## 12. Layer-by-layer testing approach

In an authorized test environment:

1. Identify the frontend's **Origin** and the API's full Request URL, including port/scheme.
2. Check the `fetch` call: is `credentials` set to `omit`, `same-origin`, or `include`? Is there an `Authorization` or custom header triggering preflight?
3. For `OPTIONS` preflight, inspect `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`, and response `Access-Control-Allow-*`.
4. Check the actual response: is ACAO a **single exact origin** or wildcard, is ACAC true needed, and is `Vary: Origin` appropriate for caching?
5. In Developer Tools under **Application/Storage → Cookies**, verify cookies applying to the API host, Domain/Path/Secure/HttpOnly/SameSite, and browser Issues.
6. Verify whether the actual request really sends the cookie and how the API authenticates the user.
7. For state-changing requests with cookies, verify that requests with **missing or invalid CSRF tokens** are rejected **before mutating data**.
8. Test one allowed origin and one rejected origin; never reflect arbitrary Origins.
9. With multiple security filter chains, verify path matching and chain ordering so preflight is handled properly by CORS.
10. Never include real session IDs, access tokens, or cookies in shared screenshots/logs.

Illustrative `curl` command **sending preflight-like headers** to inspect server responses:

```bash
curl -i -X OPTIONS "https://api.example.test/api/orders" \
  -H "Origin: https://portal.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

`example.test` is a domain placeholder and must be replaced with a real test endpoint. `curl` only reads HTTP responses and **does not simulate cookie policies, third-party restrictions, or browser CORS decisions**; final verification still requires a browser.

## 13. Standalone Java 17 example: wildcards and credentialed responses

The following example is a **simplified model** of a portion of the CORS ACAO/ACAC rules. It performs no HTTP requests and does not simulate preflight, cookie policy, CSRF, or authentication; use it strictly to learn the difference between a wildcard and a specific origin.

Create `CredentialedCorsDemo.java`:

```java
public class CredentialedCorsDemo {

    static boolean mayReadResponse(
            String requestOrigin,
            String allowedOrigin,
            boolean allowCredentialsHeader,
            boolean includeCredentials) {
        boolean originMatches = "*".equals(allowedOrigin)
                || requestOrigin.equals(allowedOrigin);

        if (!originMatches) {
            return false;
        }
        if (includeCredentials) {
            return allowCredentialsHeader && !"*".equals(allowedOrigin);
        }
        return true;
    }

    public static void main(String[] args) {
        String origin = "https://portal.example.test";

        System.out.println("Wildcard + credentials: " +
                mayReadResponse(origin, "*", true, true));
        System.out.println("Exact origin + credentials: " +
                mayReadResponse(origin, origin, true, true));
        System.out.println("Missing ACAC: " +
                mayReadResponse(origin, origin, false, true));
        System.out.println("Wildcard + no credentials: " +
                mayReadResponse(origin, "*", false, false));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CredentialedCorsDemo.java
java CredentialedCorsDemo
```

Exact output:

```text
Wildcard + credentials: false
Exact origin + credentials: true
Missing ACAC: false
Wildcard + no credentials: true
```

When `includeCredentials=true`, the method permits reading the response only if the origin matches specifically and ACAC is enabled. In real applications, preflight, cookies, third-party policies, authorization, and CSRF must also be checked. Do not use this program in place of browser origin verification or Spring's `CorsConfiguration`.

## 14. Practical scenarios

**Scenario A — Localhost React calling localhost Spring Boot.** Frontend `http://localhost:5173` and backend `http://localhost:8080` are cross-origin. If using cookies, the frontend needs `credentials: "include"`, and the server allowlists `http://localhost:5173` with ACAC true. Also verify localhost cookie policies and CSRF; do not copy HTTP dev settings into production.

**Scenario B — Public catalog.** A GET endpoint returning a non-personalized public catalog. `Access-Control-Allow-Origin: *` can make sense if the goal is letting any origin read the response without credentials. Authentication and rate limiting remain independent API choices.

**Scenario C — Portal and admin calling a private API.** Use two explicit trusted origins and ACAC true when cookies are required. Even with a valid origin, a user lacking the admin role must still be denied at admin endpoints; CORS does not replace business permissions.

**Scenario D — Frontend and API are cross-site, cookies blocked.** Even with specific ACAO, ACAC true, `SameSite=None; Secure` cookies, and Fetch `include`, the browser may block third-party cookies. Adjust the cookie/BFF architecture or adopt a suitable solution rather than widening wildcards.

**Scenario E — Requests through a reverse proxy.** The proxy adds ACAO while Spring also adds ACAO. The browser may report errors due to duplicate headers or a cache serving stale ACAO. Assign clear ownership of CORS enforcement and verify both preflight and actual responses.

**Scenario F — Java backend calling an API.** A Java client is not governed by browser SOP/CORS; if a request fails, inspect network/TLS/auth/permissions rather than modifying ACAO to make backend calls work.

## 15. Reasoning mistakes to avoid

- **“ACAC true will force the browser to send cookies.”** False. Fetch mode, cookie attributes, and third-party policies decide this.
- **“ACAO '*' and ACAC true together will allow every frontend.”** False for credentialed Fetch; the browser blocks reading the response.
- **“Echoing Origin fixes every CORS error.”** Dangerous when APIs hold user data and credentials; you must allowlist genuinely trusted origins.
- **“HttpOnly cookies do not go through fetch.”** False. HttpOnly only prevents JavaScript from reading the cookie.
- **“SameSite=Lax blocks all cross-origin requests.”** False because cross-origin can still be same-site.
- **“A CORS error guarantees data was not modified.”** False: simple requests can already execute on the server before the response is blocked.
- **“Preflight must carry session cookies.”** False under Fetch rules; process CORS before authentication.
- **“A Bearer-token-only REST API must also set allowCredentials true.”** Not necessarily; depends on Fetch mode and whether browser-managed credentials are present.
- **“Set-Cookie can be read if the header is exposed.”** False. `Set-Cookie` is a forbidden response header for scripts.
- **“CORS protects the API from all clients.”** False. Backends/curl do not obey SOP; the server must enforce authentication and authorization.
- **“allowedOriginPatterns('*') is always safe because Spring returns a single specific origin.”** False: an overly broad pattern still lets any origin read authenticated data.
- **“Enabling proper CORS removes the need for CSRF protection.”** False: the two mechanisms address different threats.

## 16. Self-check

1. **Why can't `Access-Control-Allow-Origin: *` be used with `credentials: "include"`?** Because browsers require ACAO to be a specific matching origin and ACAC true for scripts to read credentialed responses.
2. **Does Fetch send cookies to another origin by default?** No, under the default `same-origin` mode. `include` is required, yet cookie policy can still block them.
3. **Why does Spring Security need CORS before authentication?** Preflight typically carries no credentials; requiring login before CORS can cause the server to reject OPTIONS.
4. **Does successful CORS prove the user is logged in?** No; authentication and authorization are separate responsibilities.
5. **Can allowedOriginPatterns be used with credentials?** Syntactically yes if it reflects the matched origin, yet patterns must be restricted to trusted origins and never overly broad.
6. **Do SameSite and CORS check the same concept?** No. SameSite relates to the cookie's site, while CORS relates to origin and script permission to read responses.
7. **Why does curl work while the browser cannot read the response?** Curl does not enforce SOP/CORS and usually does not apply browser cookie policies.
8. **Can an API using session cookies and form POST skip CSRF just because ACAO is restricted?** No; forms/requests can be sent and cause side effects even if an attacking script cannot read the response.

**Remember:** When a frontend must send cross-origin cookies, the right configuration is typically **Fetch `credentials: "include"` + server ACAO set to a trusted origin + ACAC `true`**, while also satisfying cookie and CSRF policies. The `*` wildcard is invalid for scripts reading credentialed responses. In Spring Security, process CORS before authentication, restrict origins carefully, and protect resources with independent authentication/authorization.

## References

- [Spring Security — CORS (Servlet)](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS before Security, `CorsConfigurationSource`, filter chains, and preflight.
- [Spring Framework — Spring MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `allowedOrigins`, `allowedOriginPatterns`, `allowCredentials`, and wildcards.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, credentialed requests, wildcards, third-party cookies.
- [MDN — Fetch Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials): `omit`, `same-origin`, `include`.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): cookie attributes and browser restrictions.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): distinguishing CSRF from origin policies and controlling cookie-based requests.
