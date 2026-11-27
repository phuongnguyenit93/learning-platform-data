# Token-Bearing Cookies, Token-Bearing Headers, and Their Risk Differences

In a web application using **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, an **OAuth 2.0 access token** can reach the API via an `Authorization: Bearer ...` header explicitly added by the Client, via a **cookie containing the token itself** automatically sent by the browser, or indirectly via a **Backend for Frontend (BFF)**: the browser holds a session cookie, while the BFF holds the access token server-side and calls the API with a Bearer header.

This difference **is not merely moving a token string from one place to another**. It determines **who can read the credential**, **whether the browser automatically sends the credential on a request**, and how threats like **Cross-Site Request Forgery (CSRF)**, **Cross-Site Scripting (XSS)**, **token theft**, and **session hijacking** are mitigated.

**Cookies** are a credential type that the browser can automatically attach to requests when domain, path, SameSite, and browser policies allow. Consequently, when an API **authenticates with cookies**, another website can attempt to make a victim's browser send requests carrying credentials: **CSRF** becomes a primary risk. A **Bearer header**, by contrast, must usually be added explicitly by JavaScript or an OAuth2 Client, so a cross-site HTML form does not automatically possess the access token to populate the header. However, if JavaScript holds the token, **XSS can still steal or misuse it**.

> **Principle:** An `HttpOnly` cookie restricts JavaScript from reading the cookie value, **not** malicious same-origin scripts from sending authenticated requests. A Bearer header reduces certain CSRF vectors that rely on auto-sent cookies, **not** XSS stealing tokens from JavaScript. **Whether a JWT is stateless does not determine whether CSRF protection is needed**: the deciding factor is whether the browser **automatically** attaches the credential to requests.

## 1. Three architectures to distinguish

Suppose the system consists of:

- **Identity Server:** Authorization Server / OIDC Provider.
- **Shop Web:** OAuth2 Client, web frontend, or SPA.
- **Orders API:** Spring Security Resource Server.
- **Order database:** stores owner, tenant, status, and business permissions.

| Model | What the browser holds | Credential on API requests | Core risks |
| --- | --- | --- | --- |
| **A. SPA sending headers** | Access token in memory or JS-readable storage | `Authorization: Bearer <access-token>` | XSS/token theft, token storage and lifecycle; CORS when cross-origin |
| **B. Access token in cookie** | Cookie holding **the OAuth2 access token itself**, possibly `HttpOnly` | `Cookie: ...`; API needs custom resolver/authentication | CSRF from auto-sent cookies, XSS acting on user's behalf, cookie scope |
| **C. BFF + session cookie** | Cookie holding **session ID**, not the access token | Browser calls BFF with session cookie; BFF calls API with Bearer header | Session CSRF, session hijacking, protecting server-side tokens |

**A cookie holding a JWT access token and a cookie holding a session ID are two different mechanisms.** A session ID typically references server-side state; an OAuth access token is an API-calling credential whose issuer/audience/scope/expiry must be verified. Putting a JWT into a cookie does not automatically turn it into a secure session; having a browser session cookie does not make a Resource Server automatically treat it as an access token.

### 1.1. Token transport does not replace token verification

Whether the token arrives via header or cookie, the Resource Server must verify:

1. For JWT: JWS signature with trusted keys, issuer, audience, `exp`/`nbf`, token type/profile, and other contract validators.
2. For opaque tokens: introspection from a trusted Authorization Server, `active`, and resource/audience binding.
3. Endpoint-appropriate scope/`GrantedAuthority`, e.g., `SCOPE_orders.read`.
4. Permissions on the actual order: owner, tenant, role/permission, state.

**An OIDC ID token is not an OAuth2 access token for the Orders API.** Never use an ID token in place of an access token simply because both contain `sub` or share the JWT format.

## 2. Token-bearing headers: Client explicitly attaches the credential

Typical Bearer request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...signed-access-token...
Accept: application/json
~~~

In an SPA, JavaScript can call:

~~~javascript
async function getOrder(orderId, accessToken) {
  const response = await fetch(
    "/api/orders/" + encodeURIComponent(orderId),
    {
      headers: {
        Authorization: "Bearer " + accessToken,
        Accept: "application/json"
      }
    }
  );
  if (!response.ok) {
    throw new Error("Unable to read order");
  }
  return response.json();
}
~~~

`fetch` does not automatically pull an OAuth token from login and add a Bearer header. **The application, OAuth2 Client, or SDK** must supply the token and explicitly set the header.

Another website that does not possess the user's access token cannot simply create an HTML form to make the browser insert:

~~~http
Authorization: Bearer <shop-web-access-token>
~~~

Therefore, a model that **only accepts explicitly attached Bearer headers** is less exposed to classical CSRF based on auto-sent cookies. Yet this conclusion carries an important condition: **the API must not simultaneously accept session cookies, token cookies, or other ambient credentials to authenticate that same request**.

### 2.1. Bearer headers still face XSS risks

If malicious script executes **within the SPA's own origin**, it can:

- Read tokens from `localStorage`, `sessionStorage`, or accessible JavaScript state.
- Hook the request pipeline or reuse the API client that already attaches the header.
- Issue requests on the user's behalf and read data returned to that origin.
- Tamper with the UI, alter form contents, or trick users into performing actions.

**The `Authorization` header does not create a "secret vault" shielding tokens from same-origin scripts.** The header changes how tokens are **sent**, without solving XSS as a whole.

### 2.2. Is passing tokens via query string safer?

No. For example:

~~~http
GET /api/orders/42?access_token=<secret>
~~~

Tokens can leak via browser history, referrers, access logs, reverse proxies, analytics, or observability tools. Spring Security has Bearer resolver options for alternative transports in specific cases, yet **URI query parameters should not be enabled for normal APIs**. Bearer headers are the standard choice per RFC 6750.

## 3. Token-bearing cookies: the browser can send credentials automatically

An application may place an access token inside a cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-access_token=<opaque-or-jwt-token>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

When the browser sends a matching request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Cookie: __Host-access_token=<opaque-or-jwt-token>
~~~

The browser **does not automatically turn a cookie into an `Authorization: Bearer` header**. Spring Security Resource Server does not read JWT/opaque tokens from cookies by default, so using this pattern requires a **custom `BearerTokenResolver`** or a dedicated authentication mechanism.

The security difference lies in **automatic attachment**: the browser can send cookies when a user navigates, submits a form, or another site triggers a request, provided cookie conditions and browser policies permit. An attacker does not need to **read the token** to attempt an authenticated state change.

### 3.1. Conditions for cookies to be sent

Cookies do not automatically appear on every request. Browsers evaluate multiple factors:

- Host and `Domain` attribute.
- URL path and `Path` attribute.
- HTTPS if the cookie is `Secure`.
- `SameSite` and same-site/cross-site context.
- Browser policies on third-party cookies.
- Fetch `credentials` mode for cross-origin JavaScript requests.
- `Max-Age`/`Expires` lifetime.

Thus "cookies are auto-sent by the browser" means **whenever these conditions allow**, not that any site can attach auth cookies to any URL.

### 3.2. Cookie auth does not make JWTs stateful

A stateless JWT stored in a cookie must still have its signature, issuer, audience, expiration, and permissions verified by Spring Security. Never treat a cookie named `access_token` as already authenticated. The cookie is merely the **transport wrapper** for the credential.

## 4. CSRF: why auto-sent cookies introduce extra risk

**CSRF (Cross-Site Request Forgery)** occurs when an attacker causes the browser of a user holding credentials to send an unwanted request to a target application, and the server accepts it because of **automatically attached credentials**.

Suppose an API exposes:

~~~http
POST /api/orders/42/cancel HTTP/1.1
Host: api.example.test
Cookie: __Host-access_token=<victim-access-token>
~~~

Another website could try to make the browser submit a form:

~~~html
<!-- Illustrates a request-triggering path, not recommended code. -->
<form action="https://api.example.test/api/orders/42/cancel"
      method="POST">
  <input type="hidden" name="confirm" value="yes">
</form>
~~~

If the browser sends the cookie on that request **and** the Orders API trusts the cookie alone with no CSRF defense, the server could cancel the order even though the user never initiated the action from Shop Web.

### 4.1. Why do Bearer headers change the threat model?

A cross-site HTML form cannot attach a Bearer header held by an SPA in JavaScript. The attacker's site **lacks the token**, so requests hitting a **header-only API** normally lack valid authentication.

However, if the same browser is logged in via a session cookie, or the API accepts both cookies and headers, an attacker can target the **cookie path**, even though the developer assumes the app "uses Authorization."

**Never declare CSRF gone just because JWT or Bearer appears somewhere in the architecture.** Check which credentials each protected request accepts.

### 4.2. Stateless does not exempt from CSRF

Fallacy:

~~~text
JWT in HttpOnly cookie
 + SessionCreationPolicy.STATELESS
 => no CSRF needed
~~~

**False.** CSRF depends on whether the browser automatically sends credentials, not on whether Spring creates an `HttpSession` or whether a JWT is stateless. A stateless API reading JWTs from cookies **still needs CSRF evaluation and protection**.

### 4.3. State-changing GET requests are even more dangerous

If a developer designs:

~~~http
GET /api/orders/42/cancel
~~~

browsers can issue GETs via links, navigations, or resource loads. A `SameSite=Lax` cookie may be sent on certain **top-level cross-site navigations using safe methods**, such as GET. Even with CSRF protection on POST, canceling via GET remains a design flaw.

**GET/HEAD/OPTIONS/TRACE must never have unsafe business side effects.** Never create/cancel orders, transfer funds, change passwords, or send sensitive emails via GET.

## 5. SameSite: a CSRF mitigation layer, not access control

| Attribute | General behavior | Limitations |
| --- | --- | --- |
| `SameSite=Strict` | Sends cookie only in same-site contexts | Can break OAuth/OIDC callbacks returning from another site |
| `SameSite=Lax` | Sends in same-site and some top-level cross-site safe-method navigations | Unsafe if GET mutates state; does not replace CSRF tokens |
| `SameSite=None; Secure` | Allows cross-site sending per browser policy | Requires HTTPS, CSRF; third-party cookies may be blocked by browsers |
| SameSite omitted | Browser applies version-dependent defaults/exceptions | Never rely on defaults as a security contract |

### 5.1. Same-site is not same-origin

Example:

~~~text
https://shop.example.com
https://api.example.com
~~~

These two URLs may be **same-site** yet are **two different origins**. SameSite governs when cookies are sent across sites; the Same-Origin Policy and CORS govern cross-origin JavaScript access.

This matters when an organization has **untrusted subdomains**. A page on another subdomain can be **same-site**, so `SameSite=Strict` is not enough to fully replace CSRF tokens or a request-origin policy. Never treat all subdomains on a site as equally trusted.

### 5.2. SameSite and OAuth/OIDC redirects

In the Authorization Code flow, the browser navigates to the AS and returns to the Client's redirect URI. The Client's login/state cookie may need to be sent on this callback.

`SameSite=Strict` can block cookies when callbacks return from a different AS site. `SameSite=Lax` usually works with top-level GET redirects, whereas `form_post` response modes or iframes have different requirements. **Test with real browsers on the real OIDC flow**; do not pick Strict merely because the name sounds stronger.

### 5.3. Third-party cookie restrictions

When frontend and API live on completely different **sites**:

~~~text
https://shop.example.com
https://api.example.net
~~~

cross-site cookies normally require `SameSite=None; Secure` and `credentials: "include"` on cross-origin fetch, yet browsers may still block third-party cookies. That is why cross-site cookie auth architectures must be tested in target browsers rather than relying solely on MockMvc.

## 6. What do cookie attributes protect?

### 6.1. `Secure`

~~~http
Set-Cookie: __Host-access_token=<token>; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

`Secure` ensures browsers send the cookie only over secure connections per their rules. End-to-end HTTPS/TLS and reverse-proxy/log protection are still required. `Secure` does not prove the token has the right issuer or audience.

### 6.2. `HttpOnly`

`HttpOnly` prevents normal JavaScript from **reading the auth cookie via `document.cookie`**. This closes one token-theft vector under XSS.

However, `HttpOnly` **does not stop the browser from sending the cookie**. If malicious script runs inside the **legitimate origin**, it can still attempt:

~~~javascript
// Illustrates the principle: the browser can attach a valid cookie.
await fetch("/api/orders/42/cancel", { method: "POST" });
~~~

This request remains subject to CSRF tokens, scopes, and policies; calling it does not guarantee success. Nevertheless, it proves **a script does not need to read raw cookies to exercise browser-auto-sent credentials**.

### 6.3. `Domain` and `Path`

Host-only cookies (omitting `Domain`) are normally sent only to the cookie-issuing host. Setting `Domain=example.com` exposes the cookie to more subdomains than necessary, widening the attack surface. `Path` restricts which request paths receive the cookie, yet **is not a security sandbox against same-origin JavaScript**.

### 6.4. The `__Host-` prefix

A `__Host-access_token` cookie requires `Secure`, `Path=/`, and **no `Domain`** for supporting browsers. This mitigates cookie shadowing/injection across subdomains. Still, it **does not** replace CSRF, XSS defense, or access-token validation.

### 6.5. `Max-Age` and token expiration

~~~text
Cookie Max-Age = 60 minutes
JWT exp        = 10 minutes
~~~

After 10 minutes, the Resource Server must still reject the expired JWT even though the cookie remains. Deleting a cookie on logout **is not equivalent to revoking the access token** if it was already stolen; revocation, introspection, or appropriate token lifetimes are needed.

## 7. XSS: how can tokens in JavaScript be stolen?

An SPA sending Bearer headers normally needs the token somewhere JavaScript can use it.

| Storage location | Convenience | Risks |
| --- | --- | --- |
| **SPA memory** | Does not persist across reloads by default | XSS can still call APIs, hook requests, or read state if reachable |
| **`sessionStorage`** | Persisted per tab/session by browser | Readable by same-origin scripts; not `HttpOnly` |
| **`localStorage`** | Survives reloads/restarts | XSS can read/exfiltrate; token persists longer |
| **IndexedDB** | Stores structured data | Readable by same-origin JavaScript per browser rules |
| **`HttpOnly` cookie** | Web scripts cannot read raw cookie directly | CSRF and XSS acting on user's behalf remain possible |
| **Server-side BFF** | Browser holds no access token if designed properly | Server must protect tokens/sessions; web still faces CSRF/XSS |

**`sessionStorage` is not XSS-proof secret storage.** Memory reduces persistent exposure without making XSS safe.

### 7.1. Malicious scripts can do more than read tokens

If XSS runs inside the Shop Web origin, an attacker can:

- Read/modify DOM contents and data returned to the app.
- Issue API commands as the user through requests the app is allowed to send.
- Intercept functions/SDKs that attach Bearer headers.
- Extract tokens from storage or at the moment of use.
- Trick users into confirming unintended transactions.

Therefore you need **output encoding, avoiding dangerous DOM injection sinks, properly deployed CSP, Trusted Types where appropriate, dependency and third-party script governance, minimal scopes, and server-side resource checks**. Never pick cookies or headers as a substitute for fixing XSS vulnerabilities.

### 7.2. Does a BFF reduce XSS risk?

If the BFF never sends access tokens to the browser, XSS cannot directly read a token **that is not in the browser**. That is a real benefit. Still, XSS can send requests over the session to the BFF and read valid data returned by the BFF. A BFF **reduces token exposure**, rather than stopping all XSS actions.

## 8. CORS is not CSRF protection

**CORS** governs whether cross-origin JavaScript can issue certain requests and **read responses** under browser policy. **CSRF** is the risk of an attacker triggering a request with auto-attached credentials to cause side effects.

A frontend at `https://shop.example.com` calls an API at `https://api.example.com`:

~~~javascript
await fetch("https://api.example.com/api/orders/42", {
  headers: { Authorization: "Bearer " + accessToken }
});
~~~

`Authorization` is a non-safelisted request header, so the browser may send a **CORS preflight**. The API must allow the origin, method, and header if the browser frontend needs to read the response.

### 8.1. Cross-origin fetch with cookies

~~~javascript
await fetch("https://api.example.com/api/orders/42", {
  credentials: "include"
});
~~~

`credentials: "include"` lets the browser send credentials cross-origin **if cookie policies permit**. It does not bypass SameSite, third-party cookie restrictions, or CSRF validation.

The API may return:

~~~http
Access-Control-Allow-Origin: https://shop.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Never combine `Access-Control-Allow-Origin: *` with `Access-Control-Allow-Credentials: true` expecting browsers to allow credentialed responses. Use an explicit origin allowlist.

### 8.2. Why doesn't CORS block all CSRF?

An HTML form can submit a request under web protocol rules **without needing to read the response**. If the server already altered data, the browser blocking the attacker from reading the response body **does not undo the side effect**.

~~~text
Other site -> triggers request
Browser    -> may auto-send cookie per cookie policy
Server     -> if relying solely on cookies without CSRF defense
           -> may process the unintended action
Attacker   -> needs no response visibility
~~~

Hence distinguish **CORS: cross-origin fetch/response-read permission** from **CSRF: validity of an action arriving from a browser with ambient credentials**.

## 9. Where does Spring Security read Bearer tokens by default?

With `oauth2ResourceServer().jwt()` or `opaqueToken()`, Spring Security Servlet normally uses `DefaultBearerTokenResolver` to read the token from:

~~~http
Authorization: Bearer <access-token>
~~~

**It does not read `access_token` or `__Host-access_token` cookies by default.** Cookies can hold locales, sessions, CSRF tokens, or other data; Spring cannot guess which cookie is an OAuth credential.

### 9.1. Header-only JWT Resource Server

Spring Boot 3 / Spring Security 6 example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HeaderBearerApiSecurity {

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**The reason CSRF is disabled in this example is a very specific architectural assumption**: `/api/**` authenticates solely via Bearer tokens **explicitly sent in the header** by the Client, without session cookies, access token cookies, or ambient HTTP credentials. **It is not because "JWT is stateless so CSRF can be disabled."**

Issuer, audience, JWT validators, and token profile settings are still needed outside the transport focus of this example. Furthermore, `securityMatcher("/api/**")` does not protect URLs outside `/api/**`; the application needs a fallback chain or matching policy.

### 9.2. Do not enable query tokens merely for convenience

`DefaultBearerTokenResolver` includes options for tokens in form bodies or URI parameters under specific constraints. For general APIs, avoid passing access tokens in query strings because queries easily appear in logs, history, and referrers. Transport decisions must follow an explicit contract rather than enabling multiple credential sources casually.

## 10. If you must accept access tokens from cookies

**Token-in-cookie is a viable architecture, yet requires CSRF defense.** One clear way to understand the mechanics is providing a `BearerTokenResolver` that reads only a cookie named `__Host-access_token`.

### 10.1. Cookie-only resolver

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;

public final class CookieBearerTokenResolver
        implements BearerTokenResolver {

    private static final String TOKEN_COOKIE = "__Host-access_token";

    @Override
    public String resolve(HttpServletRequest request) {
        Cookie[] cookies = request.getCookies();
        if (cookies == null) {
            return null;
        }

        String found = null;
        for (Cookie cookie : cookies) {
            if (!TOKEN_COOKIE.equals(cookie.getName())) {
                continue;
            }

            String value = cookie.getValue();
            if (found != null || value == null || value.isBlank()) {
                throw new OAuth2AuthenticationException(
                    BearerTokenErrors.invalidRequest(
                        "Invalid or duplicate bearer cookie"));
            }
            found = value;
        }
        return found;
    }
}
~~~

Conventions:

- Read only **one fixed cookie name**; never read tokens from query/body.
- If the cookie is absent: no Bearer credential from the cookie source.
- Duplicate/empty auth cookies are rejected to prevent cookie shadowing/credential ambiguity.
- Do not silently fall back to a Bearer header if the cookie is absent. Each endpoint/chain should have **one explicit credential source contract**.
- The token value must still pass **`JwtDecoder` or opaque introspection**; a matching cookie name is not proof of a valid token.

The request's `Cookie` header **does not transmit `Secure`, `HttpOnly`, `Domain`, or `SameSite`** to the server; those attributes belong to `Set-Cookie` and browser policy. Thus the resolver cannot "re-verify" from the request `Cookie` header alone that a cookie was marked `HttpOnly`.

### 10.2. A cookie-only filter chain must enable CSRF

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;

@Configuration
class CookieBearerApiSecurity {

    @Bean
    SecurityFilterChain cookieApi(HttpSecurity http) throws Exception {
        CsrfTokenRequestAttributeHandler csrfHandler =
                new CsrfTokenRequestAttributeHandler();

        return http
            .securityMatcher("/cookie-api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    CookieCsrfTokenRepository.withHttpOnlyFalse())
                .csrfTokenRequestHandler(csrfHandler))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/cookie-api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(new CookieBearerTokenResolver())
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**This example illustrates the mechanism, not a complete production configuration.** It highlights that:

1. The Resource Server reads credentials **from a cookie** using a custom resolver.
2. CSRF **remains enabled** even though the session policy is `STATELESS`.
3. `CookieCsrfTokenRepository.withHttpOnlyFalse()` creates an `XSRF-TOKEN` cookie that JavaScript **is allowed to read** and send in the `X-XSRF-TOKEN` header. **The CSRF cookie is not the access token cookie.**

For SPAs on Spring Security 6, account for **deferred CSRF tokens**, **XOR masking/BREACH handling**, and rotating tokens after login/logout. The example uses `CsrfTokenRequestAttributeHandler` to accept raw tokens from headers SPA-style; match handler/CSRF token delivery choice to your exact version and threat model. **The CSRF cookie must be generated and delivered before unsafe requests**, rather than letting the browser send its first POST before the frontend has a CSRF token.

Beyond CSRF, apply cookie hardening, appropriate Origin/Referer checks, and untrusted subdomain checks. If an attacker can plant a CSRF cookie of the same name, an unbound double-submit cookie can be weak; consider session-bound/signed tokens or properly configured framework strategies.

### 10.3. Issuing access token cookies with safe attributes

~~~java
import java.time.Duration;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;

// Illustrates only after an already-valid authentication flow.
ResponseCookie cookie = ResponseCookie.from(
        "__Host-access_token", accessToken)
    .path("/")
    .secure(true)
    .httpOnly(true)
    .sameSite("Lax")
    .maxAge(Duration.ofMinutes(10))
    .build();

response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
~~~

This snippet runs **inside a server response**, with `response` and `accessToken` supplied by a secure OAuth flow. Never take an arbitrary token string from a query parameter and turn it into a cookie. The `__Host-` prefix requires `Secure`, `Path=/`, and no `Domain`.

If frontend and API reside on two different **sites**, `SameSite=Lax` may block cross-site cookie delivery; switching to `SameSite=None` must pair with `Secure`, CSRF/CORS design, and third-party cookie restriction testing. Never treat one cookie example as universal for all architectures.

### 10.4. Cookie auth and Authorization header appearing together

A request might contain:

~~~http
Authorization: Bearer <token-A>
Cookie: __Host-access_token=<token-B>
~~~

If the server accepts both, define **credential precedence**, conflict handling, and CSRF policy. If code says "if header is invalid, fall back to cookie," the request might authenticate as a **different principal** than the token the Client thought it used. Prefer separating header-only and cookie-only endpoints/chains, or rejecting multi-source ambiguity per contract.

## 11. BFF: browser holds only a session cookie, API receives a Bearer header

The **Backend for Frontend** architecture moves OAuth access tokens out of the browser:

~~~mermaid
sequenceDiagram
    actor U as User
    participant B as Browser
    participant W as Shop BFF (OAuth2 Client)
    participant AS as Authorization Server
    participant API as Orders API

    U->>B: Initiate login
    B->>W: GET /oauth2/authorization/shop
    W->>AS: Authorization Code flow
    AS-->>W: Authorization code via callback
    W->>AS: Exchange code for access token server-side
    AS-->>W: Access token
    W-->>B: HttpOnly Secure session cookie
    B->>W: GET /orders/42 + session cookie
    W->>W: Look up server-side authorized client/token
    W->>API: Authorization Bearer access token
    API-->>W: Order per scope + policy
    W-->>B: Application data/HTML
~~~

Benefits:

- The browser **never needs to hold OAuth access tokens** in JavaScript or cookies when the BFF is designed properly.
- The BFF manages refresh, token rotation, and logout/session revocation.
- Downstream Resource Servers still receive standard Bearer headers.
- UI and BFF can share a single origin, reducing CORS complexity.

Trade-offs:

- The BFF must manage **session state**, authorized client storage, TTL, HA, and scaling.
- The session cookie remains an **ambient credential**: CSRF defense is mandatory.
- XSS within the Shop origin can still call the BFF as the user.
- The BFF must prevent arbitrary URL/host proxying or letting Clients inject unverified credentials downstream.

### 11.1. Spring Security OAuth2 login/session configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ShopBffSecurity {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**",
                                 "/login/**",
                                 "/oauth2/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

This is the **BFF application's** configuration, not a JWT Resource Server chain. Configure `ClientRegistration`, issuer/provider, redirect URI, and appropriate authorized client persistence. The BFF should call the Orders API with tokens server-side, **without returning access tokens in HTML/JSON or cookies to the browser**.

### 11.2. BFF session cookie

In Spring Boot Servlet:

~~~yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

This example fits HTTPS and an OIDC login flow using top-level GET callbacks. If the AS uses `form_post` response mode or iframe/cross-site flows, re-test SameSite. `csrf(Customizer.withDefaults())` also requires proper CSRF token integration in forms/fetch; cookie settings do not replace CSRF.

Not every BFF needs Spring Session, yet multi-replica deployments usually need a clear session persistence/availability strategy. **A session cookie is not an access token**, though a stolen session ID still lets an attacker hijack the session until invalidated.

## 12. CSRF token: a JS-readable cookie is not an auth cookie

To let a browser submit POSTs under cookie-based authentication, an application may require a CSRF header:

~~~http
POST /cookie-api/orders/42/cancel HTTP/1.1
Host: api.example.test
Cookie: __Host-access_token=<auth-token>; XSRF-TOKEN=<csrf-token>
X-XSRF-TOKEN: <csrf-token>
Content-Type: application/json

{"reason":"customer-request"}
~~~

Here there are **two values with different purposes**:

- `__Host-access_token`: the authenticating Bearer credential, which should be `HttpOnly` and verified by the Resource Server.
- `XSRF-TOKEN`/`X-XSRF-TOKEN`: the CSRF token proving the request originated from the intended application context, JS-readable by design and verified by the server.

**A CSRF token does not grant `orders.cancel` permission.** The auth token must still carry the scope, role/permission, and rights to Order 42.

### 12.1. Why can a CSRF cookie be non-HttpOnly?

If the frontend must read the CSRF token from a cookie to attach it to a custom header, the CSRF cookie is **JS-readable** by design. That differs from session/access-token cookies that must be shielded from JavaScript reading. Never copy `withHttpOnlyFalse()` onto an **auth cookie** just because you saw CSRF code doing it.

### 12.2. CSRF tokens do not replace XSS defenses

A malicious same-origin script can read the CSRF token that frontend code can read, or piggyback on the application's request-sending pipeline. Thus CSRF protection prevents **cross-site request forgery**, without stopping scripts that have already compromised the origin.

### 12.3. CSRF and filter order affect status codes

On a `POST` request missing both authentication and a CSRF token, Spring Security may return **403 due to CSRF** before reaching Bearer authentication. Never assume every POST missing a Bearer token must return 401 across all configurations.

~~~text
Protected GET + no token -> typically 401
POST with cookie auth + missing CSRF -> typically 403
POST with cookie auth + wrong CSRF -> typically 403
POST with cookie auth + valid CSRF, missing scope -> 403 per authorization
POST with cookie auth + valid CSRF, sufficient scope, wrong tenant -> denied per policy
~~~

What matters most is verifying **no protected action executes** whenever any condition fails.

## 13. Comparing credential transports against attacks

### 13.1. Requests from another website

**Header-only:**

~~~text
Attacker site -> submits form to Orders API
Browser does not auto-attach Shop SPA's Bearer token
Orders API reads only Authorization: Bearer
=> no valid authentication
~~~

**Cookie-token:**

~~~text
Attacker site -> triggers request to Orders API
Browser may send auth cookie if cookie policy allows
Orders API reads cookie as Bearer credential
=> needs CSRF defense before state-changing operations
~~~

**BFF session:**

~~~text
Attacker site -> triggers request to BFF
Browser may send session cookie
BFF might call API using server-held token
=> BFF needs CSRF defense and business policy
~~~

### 13.2. XSS inside the Shop origin

**Header-only with JS-readable token:** access token may be exfiltrated and/or API called on the user's behalf.

**HttpOnly auth cookie:** hard to read raw cookie via `document.cookie`, yet scripts can still exercise the cookie via requests.

**BFF session:** browser holds no server-side access token for direct extraction, yet scripts can still send requests to the BFF using the session cookie.

### 13.3. Token leakage via logs

**Header-only:** avoid logging full `Authorization` headers.

**Cookie-token/session:** avoid logging full `Cookie` or `Set-Cookie` headers, session IDs, unnecessary CSRF tokens, and credentials.

**Both:** never place tokens in query strings, redirect URLs, analytics payloads, or error responses.

## 14. Testing: prove transport, token validation, and policy

To verify the system, separate:

1. **Credential transport:** does Spring read tokens from headers or cookies? Are duplicate/mixed credentials handled properly?
2. **Token verification:** are JWT signatures/issuer/audience/time checked? Do opaque tokens introspect properly?
3. **CSRF:** with cookie auth, are unsafe requests with missing/wrong CSRF tokens blocked?
4. **Authorization:** are scopes, roles, owners, tenants, and business actions enforced?
5. **Browser behavior:** do SameSite, CORS, cookie flags, and OAuth callbacks behave as expected?

### 14.1. Sample test matrix

| Test case | Header-only API | Cookie-token API | BFF |
|---|---|---|---|
| Protected GET without credentials | Typically 401 | Typically 401 | Redirect/401 per session policy |
| GET with cookie token only | **Does not authenticate** | Authenticates if cookie token valid | Session authenticates if cookie is valid session ID |
| GET with Authorization Bearer only | Authenticates valid token | Does not read header if resolver is cookie-only | Does not necessarily accept browser Bearer |
| POST with cookie auth, missing CSRF | Not applicable if cookies are not auth | **Deny** | **Deny** |
| POST with cookie auth, wrong CSRF | Not applicable | **Deny** | **Deny** |
| Valid CSRF yet missing scope | 403 when Bearer token lacks scope | 403 | Denied by BFF/downstream policy |
| JWT invalid signature or aud | **Deny** | **Deny** | Denied by downstream Resource Server |
| Expired token while cookie still lives | Rejects expired token | **Deny** | BFF handles token lifecycle |
| Sufficient role/scope, wrong tenant owner | **Denied at data policy** | **Denied at data policy** | **Denied at data policy** |
| Cross-site form request | No auto-attached Bearer header | Check SameSite/CSRF | Check SameSite/CSRF |

**Exact HTTP status codes can vary with filter order and exception handling**, especially on POSTs missing both CSRF and authentication. Tests should prove **no side effect occurred** and pinpoint which layer blocked the request.

### 14.2. Unit testing `CookieBearerTokenResolver`

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;

class CookieBearerTokenResolverTest {

    private final CookieBearerTokenResolver resolver =
            new CookieBearerTokenResolver();

    @Test
    void noCookieMeansNoBearerToken() {
        assertNull(resolver.resolve(new MockHttpServletRequest()));
    }

    @Test
    void readsOnlyDesignatedCookie() {
        var request = new MockHttpServletRequest();
        request.setCookies(
            new Cookie("theme", "dark"),
            new Cookie("__Host-access_token", "test-token"));

        assertEquals("test-token", resolver.resolve(request));
    }

    @Test
    void rejectsDuplicateAuthCookies() {
        var request = new MockHttpServletRequest();
        request.setCookies(
            new Cookie("__Host-access_token", "token-A"),
            new Cookie("__Host-access_token", "token-B"));

        assertThrows(OAuth2AuthenticationException.class,
            () -> resolver.resolve(request));
    }

    @Test
    void headerDoesNotBecomeCookieCredential() {
        var request = new MockHttpServletRequest();
        request.addHeader("Authorization", "Bearer header-token");
        assertNull(resolver.resolve(request));
    }
}
~~~

This test only exercises the resolver and **does not prove JWT/token validity**. Add separate integration tests with signed JWTs or mock introspection.

### 14.3. MockMvc CSRF test

Spring Security Test provides `csrf()` to simulate a valid CSRF token:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

// Illustrative test body: MockMvc, controller,
// SecurityFilterChain, and test decoder/introspector are already configured.

mockMvc.perform(post("/cookie-api/orders/42")
        .cookie(new Cookie("__Host-access_token", "valid-test-token")))
    .andExpect(status().isForbidden());

// With CSRF: only passes the CSRF filter;
// authentication, scope, and owner/tenant must still be checked.
mockMvc.perform(post("/cookie-api/orders/42")
        .cookie(new Cookie("__Host-access_token", "valid-test-token"))
        .with(csrf()));
~~~

`csrf()` **does not fully simulate real browser CSRF cookie creation/reading**, and `valid-test-token` must be accepted by the test fixture's decoder/introspector. To verify the end-to-end flow, use a mock AS/JWKS and a real browser.

### 14.4. `jwt()` does not test token transport

~~~java
mockMvc.perform(get("/api/orders/42")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read"))));
~~~

Spring Security Test's `jwt()` **mocks a `JwtAuthenticationToken`**. It is useful for testing HTTP authorization, yet **does not prove** the Bearer header/cookie resolver works, nor does it **verify real signatures, issuers, or audiences**.

### 14.5. Browser E2E tests

MockMvc does not fully simulate:

- SameSite and third-party cookie policies.
- Cross-origin fetch, CORS preflights, and credentials modes.
- OIDC redirect/`form_post` callbacks.
- Trailing slashes/rewrites through gateways.
- Cookie clearing on logout or expiry in the browser.

Use browser E2E tests to verify cookie flags, actual request headers, CSRF from untrusted origins, CORS, and login callbacks. On rejected requests, **verify no database/event side effects occurred**.

## 15. Choosing the right model for the Client

### Mobile and machine-to-machine

**Bearer Authorization headers** usually fit best. Non-browser clients do not auto-send cookies the way browsers do, so CSRF is not a central threat; still guard against token theft/replay, wrong audiences, overly broad permissions, and credential leakage.

### SPA calling the API directly

You can use **Authorization Code + PKCE** for a public OAuth2 Client and send access tokens in headers. Never embed a Client secret in JavaScript. Consider in-memory storage, short-lived access tokens, and refresh/reauthorization per real AS/SDK guidance; `localStorage` creates high token-extraction risk under XSS.

### Web frontend and backend controlled by the same team

A **BFF/session cookie** is worth considering if you want to keep OAuth access tokens out of the browser. In exchange, you must manage sessions/CSRF, server-side token storage, scaling, and lifecycles.

### Wanting auth cookies so JavaScript cannot read tokens

You can use an `HttpOnly` cookie holding the token, **but you must enable CSRF**, control cookie domain/SameSite/CORS, and customize `BearerTokenResolver`. Never copy header-only `csrf.disable()` onto a cookie chain.

### Frontend and API on completely different sites

Cross-site cookies can be tricky due to `SameSite=None; Secure` and third-party cookie restrictions. Bearer headers or a same-origin BFF may be simpler depending on the system. Base the decision on target browsers and the real threat model.

## 16. Common misconceptions

**"JWT is stateless so CSRF is not needed."** Incorrect if the JWT sits in an auto-sent browser cookie.

**"HttpOnly cookies stop XSS completely."** No. They block direct cookie reading by JavaScript, yet XSS can still act through authenticated requests.

**"Bearer headers ensure access tokens can never leak."** No. If JavaScript holds the token, XSS/supply-chain compromises can read or misuse it.

**"sessionStorage is safer than localStorage against XSS."** Not against malicious same-origin scripts; both are JS-readable.

**"CORS blocks all CSRF."** No. Attackers may only need to trigger side effects without reading responses.

**"SameSite=Strict completely replaces CSRF tokens."** No. Same-site subdomains, browser nuances, and OAuth callbacks remain boundaries to account for.

**"Spring Resource Server automatically reads access tokens from cookies."** Not by default; a custom resolver/authentication is required.

**"A cookie named `__Host-access_token` is a valid credential."** Cookie names do not prove JWT signature/issuer/audience/expiry or opaque active status.

**"A valid CSRF token means permission to cancel orders."** No. CSRF defense does not replace OAuth scopes or owner/tenant permissions.

**"BFFs have no risk because tokens live on the server."** Session hijacking, CSRF, XSS acting on the user's behalf, and server-side token storage risks still exist.

**"Cookie Max-Age can extend a JWT's lifetime."** No. Expired tokens must still be rejected.

**"Just disable CSRF for REST JSON."** No. CSRF decisions depend on ambient credentials, not on the REST/JSON label.

**"Putting access tokens in URLs is convenient for debugging."** Do not do it; query strings are easily logged and leaked.

**"Same-site means same-origin."** No. SameSite and CORS/Same-Origin Policy enforce different boundaries.

**"The API has a CORS allowlist, so curl or other servers cannot call it."** CORS is a browser mechanism, not authentication; the API still needs token and permission checks.

## 17. Sample deployment contracts

### A. Header-only Orders API

~~~yaml
# Contract documentation, not auto-read Spring configuration.
resource_server: orders-api
token_format: jwt
authentication_transport: authorization_bearer_header_only
cookie_authentication: not_accepted
trusted_issuer: https://identity.example.test/realms/shop
expected_audience: orders-api
csrf: disabled_for_this_chain_only_because_no_ambient_auth
authorization:
  GET_orders: SCOPE_orders.read
  POST_orders: SCOPE_orders.write
  data_policy: owner_and_tenant
tests:
  - missing_header_denied_even_if_cookie_present
  - signed_jwt_validated
  - wrong_issuer_or_audience_denied
  - insufficient_scope_denied
~~~

### B. Cookie-token Orders API

~~~yaml
# Contract documentation, not auto-read Spring configuration.
resource_server: cookie-orders-api
authentication_transport: "__Host-access_token cookie only"
cookie:
  secure: true
  http_only: true
  same_site: lax
  path: /
  domain: omitted_host_only
token_validation: jwt_signature_issuer_audience_exp
csrf:
  enabled: true
  required_on_unsafe_methods: true
  token_delivery: dedicated_csrf_cookie_or_endpoint
  expected_header: X-XSRF-TOKEN
  origin_policy: controlled
authorization:
  GET_orders: SCOPE_orders.read
  POST_orders: SCOPE_orders.write
  data_policy: owner_and_tenant
tests:
  - missing_or_invalid_csrf_denied
  - valid_csrf_but_insufficient_scope_denied
  - duplicate_auth_cookie_denied
  - bearer_header_does_not_override_cookie_contract
  - cross_site_browser_behavior_tested
~~~

A BFF application will have a third contract: **the browser sends a session ID**, the BFF stores OAuth tokens server-side and checks CSRF/sessions, and the downstream Orders API still receives a **Bearer header**.

## 18. Practice scenarios

**A.** A JWT is placed in an `HttpOnly` cookie, the server uses `STATELESS`, and CSRF is disabled. Is it safe?

**Not yet.** The cookie is still auto-sent. Statelessness does not remove CSRF risk; an appropriate CSRF strategy is required.

**B.** An SPA stores its token in `localStorage` and calls the API with a Bearer header. If the page has XSS, can the token be stolen?

**At risk.** Same-origin scripts can read `localStorage` or hijack the request-sending path.

**C.** Cookie is `HttpOnly`, so XSS attackers cannot read `document.cookie`. Can they still call the API as the user?

**Possibly.** The browser may still attach the cookie when a same-origin script triggers requests; CSRF/authority/policies still govern whether it succeeds.

**D.** `SameSite=Lax` and a GET URL deletes data. Is there an issue?

**Yes.** Top-level cross-site GETs can carry Lax cookies. GET must never have dangerous side effects.

**E.** CORS blocks an attacker's origin from reading responses. Is CSRF still needed when the API authenticates via cookies?

**Yes.** The attacker may only need to trigger a side-effecting request without reading the response.

**F.** A client sends a cookie named `access_token` to a Spring Resource Server configured only with `oauth2ResourceServer().jwt()`. Will it authenticate automatically?

**Not by default.** The Resource Server normally looks for `Authorization: Bearer`; cookies require a custom resolver.

**G.** A BFF gives the browser only a session cookie and never sends OAuth access tokens. Does that eliminate XSS/CSRF?

**No.** It reduces access token exposure, yet the session remains an ambient credential and same-origin scripts can still act on the user's behalf.

**H.** Cookie auth + valid CSRF header, yet the token only has `orders.read` and the request tries to cancel an order. Is it allowed?

**No.** CSRF does not grant OAuth scopes or object rights. `orders.cancel` and owner/tenant/state checks still apply.

**I.** A header-only API suddenly accepts both cookies and headers after a resolver change. What must be reviewed?

**Credential precedence, CSRF, chain selection, and tests rejecting implicit cookies.** Never silently fall back to an auto-sent browser credential.

**J.** Frontend and API have different origins yet are same-site. Does `SameSite=Lax` mean browser JS can read responses?

**No.** SameSite governs cookie transmission, while CORS governs cross-origin JavaScript response reading.

---

## Conclusion

**Token-bearing cookies** and **token-bearing Authorization headers** differ because **cookies can be automatically sent by the browser**, whereas Bearer headers are normally attached explicitly by an OAuth2 Client or JavaScript. Hence **cookie auth must address CSRF**, even when the cookie holds a stateless JWT; **header-only SPAs must pay close attention to XSS and JavaScript token storage**. `HttpOnly` helps limit cookie theft via reading, without blocking all XSS actions; `SameSite`, `Secure`, and CORS are complementary layers, not replacements for CSRF or authorization.

In Spring Security Resource Server, `jwt()`/`opaqueToken()` **accept `Authorization: Bearer` by default** and do not read cookies automatically. When intentionally accepting tokens in cookies, you need a **dedicated `BearerTokenResolver`, cookie hardening, and CSRF defense for unsafe requests**; `SessionCreationPolicy.STATELESS` does not alter that requirement. For web systems wanting to keep OAuth tokens out of the browser, a **BFF using session cookies and sending Bearer headers from server to API** is a strong option, yet still requires CSRF, XSS defenses, and session protection. Regardless of credential transport, the Resource Server must always verify tokens, scopes/authorities, and permissions on the **actual owner, tenant, and resource** before executing protected actions.
