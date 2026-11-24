# Designing Cookies and Callback URIs When Deploying Spring Security Reactive Behind a Reverse Proxy

## 1. Objective

When deploying a **Spring WebFlux + Spring Security Reactive** application behind a reverse proxy, the browser may access `https://login.example.com` while the application actually receives requests at `http://127.0.0.1:8080`. Differences in scheme, host, port, and path easily break two parts of the login flow:

1. **OAuth2/OIDC callback URI** gets constructed with internal HTTP, the wrong hostname, or the wrong prefix compared to the URL registered at the Identity Provider (IdP). Consequence: `redirect_uri_mismatch`, redirect loops, `invalid_state` errors, or intermittent login failures.
2. **Session cookie** gets issued with inappropriate `Secure`, `Path`, `Domain`, or `SameSite` attributes. The browser fails to store/send the cookie on the callback return; the server cannot find the `WebSession` storing the prior OAuth2 request.

This lesson guides you through designing **public URLs, forwarded headers, callbacks, WebSession cookies, CSRF, and testing the actual request path**. The scope is **Reactive/WebFlux**: use `WebSession`, `WebSessionIdResolver`, and `SecurityWebFilterChain`; do not apply Servlet-only settings such as `server.servlet.session.cookie.*`, HttpSession's `CookieSerializer`, `HttpSecurity`, or `ForwardedHeaderFilter` to solve WebFlux issues.

After this lesson, you should be able to diagram a complete login flow, determine the exact browser-side URLs, configure each side accordingly, and verify via both response headers and a real browser.

## 2. Distinguishing the Three Address Perspectives

Consider a deployment without a path prefix:

| Component | URL/Address | Role |
| --- | --- | --- |
| Browser | `https://login.example.com` | Public origin, where cookies are stored and callbacks return |
| Reverse proxy (TLS termination) | `login.example.com:443` | Accepts HTTPS, validates Host, strips untrusted headers, forwards |
| WebFlux upstream | `http://127.0.0.1:8080` | Receives internal HTTP; must never advertise this URL to the browser |
| IdP | `https://idp.example.net` | Authenticates the user then redirects the browser back to the registered callback |

Standard flow with registration ID `corporate`:

```text
(1) Browser GET https://login.example.com/oauth2/authorization/corporate
    -> Proxy -> WebFlux (received public URL info via forwarded headers)
(2) WebFlux saves OAuth2AuthorizationRequest in WebSession;
    sends Set-Cookie for origin https://login.example.com
    and 302 Location: https://idp.example.net/...?
                  redirect_uri=https%3A%2F%2Flogin.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate
                  &state=<random value>
(3) Browser goes to IdP; completes authentication.
(4) IdP redirects browser back to:
    GET https://login.example.com/login/oauth2/code/corporate?code=...&state=...
(5) Browser sends the valid session cookie; WebFlux retrieves the authorization request,
    verifies state, exchanges code for tokens, completes authentication.
```

**Key takeaway:** the `redirect_uri` in the request sent to the IdP, the endpoint Spring Security listens on, the URL registered at the IdP, and the cookie the browser sends on callback must align as **one deployment contract**. The `state` value must be matched against the original request; never fix `invalid_state` by disabling state verification.

## 3. Forwarded Headers: Restoring the Public URL, While Trusting Only the Proxy

### 3.1. Meaning

The proxy can forward internal HTTP and supply the original metadata via `Forwarded` (RFC 7239 standard) or the `X-Forwarded-*` group:

| Header | Example | Purpose |
| --- | --- | --- |
| `X-Forwarded-Proto` | `https` | Original scheme at the browser |
| `X-Forwarded-Host` | `login.example.com` | Public host |
| `X-Forwarded-Port` | `443` | Public port |
| `X-Forwarded-Prefix` | `/portal` | Public prefix if the proxy rewrites paths |
| `X-Forwarded-For` | `203.0.113.10` | Proxy/client IP chain, for logging/rules once trust is established |
| `Forwarded` | `for=203.0.113.10;proto=https;host=login.example.com` | Standardized replacement for the X-Forwarded group |

When Spring understands these headers properly, self-referential URL generation, redirects, and OAuth2's `{baseUrl}` can use the public scheme/host/port/path.

In **Spring Boot 3.x with WebFlux**, the typical configuration is:

```yaml
server:
  forward-headers-strategy: framework
```

On the reactive stack, the `FRAMEWORK` strategy uses `ForwardedHeaderTransformer`; do not use Servlet's `ForwardedHeaderFilter`. `NATIVE` can handle some headers at the web server level, but prefix handling and interpretation vary across servers; verify in practice if choosing that option. Avoid simultaneously creating a custom transformer that re-processes the same headers when Boot already configures it.

### 3.2. Trust Boundary Is a Security Prerequisite

Suppose an arbitrary client sends:

```http
GET /oauth2/authorization/corporate HTTP/1.1
Host: login.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example
Forwarded: host=attacker.example;proto=https
```

If the upstream blindly trusts headers coming from the Internet, it may construct `redirect_uri` or absolute URLs using the attacker's host. Therefore:

- The **trusted edge** proxy must strip/overwrite all client-supplied `Forwarded` and `X-Forwarded-*` headers before forwarding upstream, even if the app intends to read only one variant. Multi-hop setups must clearly define which hop is trusted and who is responsible for normalization.
- Upstream must only be reachable from the proxy via a private network, firewall, or service policy; do not expose the internal port to the Internet for clients to bypass.
- The proxy accepts only valid `Host` values; do not reflect an unvalidated host into `X-Forwarded-Host`. For login callbacks, consider an exact allowlist of public domains.
- Do not enable `server.forward-headers-strategy: framework` on a public-facing upstream without a trust boundary. Enabling header processing is only safe when the header source is controlled.

### 3.3. Illustrative Nginx Configuration Without a Prefix

The `location` block below assumes TLS is already configured in a `server` block running `listen 443 ssl` with `server_name login.example.com`, and Nginx is the trusted reverse proxy at the edge. This is a location snippet, **not a complete standalone Nginx file**:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;

    # Explicitly set public host/scheme after the proxy has validated the host.
    proxy_set_header Host login.example.com;
    proxy_set_header X-Forwarded-Host login.example.com;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;

    # Nginx is the edge in this example: do not accept a client-supplied XFF chain.
    proxy_set_header X-Forwarded-For $remote_addr;

    # Strip other variants that a client could inject.
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Prefix "";
}
```

If TLS terminates at a load balancer in front of Nginx, `https` above is only valid when **the load balancer truly guarantees the original connection was HTTPS**; design an appropriate trust chain and block misrouted HTTP access rather than blindly taking `$http_x_forwarded_proto` from the Internet. A real configuration also requires certificates, HTTP→HTTPS rules, invalid-Host rejection, and upstream access restrictions.

## 4. Designing the OAuth2/OIDC Callback

### 4.1. Default Endpoints

Spring Security Reactive uses the initiation endpoint:

`GET /oauth2/authorization/{registrationId}`

And the default callback:

`/login/oauth2/code/{registrationId}`

The default `redirect-uri` template for OAuth2 Login is:

`{baseUrl}/login/oauth2/code/{registrationId}`

In the example, `{baseUrl}` must be `https://login.example.com`, not `http://127.0.0.1:8080`. Register the exact URL at the IdP:

`https://login.example.com/login/oauth2/code/corporate`

`redirect_uri` is the address **where the IdP sends the code**, distinct from the "post-login landing page" and distinct from the IdP's OAuth2 `authorization-uri`/`token-uri`. Do not alter `redirect_uri` just to send users to a landing page after login; use a success handler/saved request as business logic requires.

### 4.2. Sample Spring Boot Configuration

`application.yml` file (WebFlux application config snippet, assuming an IdP with valid OIDC discovery):

```yaml
server:
  port: 8080
  forward-headers-strategy: framework

spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corporate:
            issuer-uri: https://idp.example.net/realms/corporate
```

`client-id` and `client-secret` here are environment variables; never write real secrets into YAML or Git. `issuer-uri` must be replaced with the real issuer published by the IdP and must match actual metadata/certificates exactly. Only include `openid` when the IdP supports OIDC.

Minimal Security class, independent of IdP details:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/actuator/health").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

`pathMatchers("/actuator/health")` is only illustrative for a health endpoint if the app uses Actuator; verify your actual policy before making routes public. When using session-cookie-based login, Spring Security's default CSRF protection must remain enabled for state-changing requests.

### 4.3. If You Truly Must Change the Callback Path

For example, if you want the callback `/auth/callback/{registrationId}` **inside the application**. You must change **both** the OAuth2 Login matcher and the registration together:

```java
.oauth2Login(oauth2 -> oauth2
    .authenticationMatcher(
        new PathPatternParserServerWebExchangeMatcher(
            "/auth/callback/{registrationId}")))
```

with import:

```java
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
```

and in YAML:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
```

Then register `https://login.example.com/auth/callback/corporate` at the IdP. Both snippets above are **incremental changes to an existing configuration**, not a standalone program. If you change `redirect-uri` but forget the matcher, the callback will hit a path that Spring Security does not handle as an authorization response.

## 5. Choosing Safe WebSession Cookies for Browsers

A WebFlux session cookie holds the **session ID**, not by default the entire `Authentication` or IdP tokens. Session data is managed server-side; when deploying multiple instances, store/share sessions appropriately—such as with Spring Session Reactive + Redis—rather than assuming every request returns to the exact same pod.

### 5.1. Cookie Attributes and Effects

| Attribute | Recommendation for top-level GET redirect login | Why |
| --- | --- | --- |
| `Secure` | `true` on public HTTPS | Browser sends cookie only over HTTPS; must align with public scheme |
| `HttpOnly` | `true` | JavaScript cannot read the session ID via `document.cookie` |
| `SameSite` | Usually `Lax`, verify specific IdP flow | Allows cookie on top-level GET navigation returning from IdP; mitigates many CSRF cases |
| `Path` | `/` when app is at root, or narrower public prefix when appropriate | Browser sends cookie only to matching paths; callback must lie within scope |
| `Domain` | **Omit** if single public host | Host-only cookie, reduces risk of sharing across subdomains |
| `Max-Age`/`Expires` | Choose per login lifecycle; session cookie is an option | Cookie lifetime differs from server-side session timeout |
| Cookie name | Pick a distinct name, control collisions | Prevents other apps on the same host from overwriting the cookie |

`SameSite=Strict` typically causes the cookie **not to be sent** when the user navigates from the IdP site to the callback; OAuth2 may lose the authorization request/state. `SameSite=Lax` fits standard **top-level GET** redirect callback flows. With a **cross-site POST** callback response mode (such as OIDC `form_post`), `Lax` typically blocks the cookie; `SameSite=None; Secure` may be needed, but requires additional assessment of CSRF, browser third-party-cookie policies, and **the specific integration's POST handling capability**. Do not switch to `None` just for a quick login fix.

**Name `__Host-APP_SESSION`:** browsers supporting cookie prefixes require `Secure`, `Path=/`, and **no `Domain`. This prefix fits root-path applications on a single public domain very well. For cookies with `Path=/portal`, do not use `__Host-` (which violates `Path=/`); you can choose `__Secure-APP_SESSION` while still omitting `Domain`.

### 5.2. Java 17+: Cookie Configuration for WebFlux

File `src/main/java/example/security/SessionCookieConfig.java`:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration(proxyBeanMethods = false)
public class SessionCookieConfig {

    @Bean
    public WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver = new CookieWebSessionIdResolver();
        resolver.setCookieName("__Host-APP_SESSION");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax"));
        return resolver;
    }
}
```

This runs in Spring WebFlux when the configuration bean is component-scanned or imported. It does not require `javax.servlet.http.Cookie`, `jakarta.servlet.http.HttpSession`, or a Servlet cookie filter. **Local HTTP environment:** `Secure` cookies may prevent tests over `http://127.0.0.1` from preserving sessions (browser localhost policies vary); use local HTTPS or a controlled separate test profile rather than removing `Secure` from production config.

Expected HTTPS response (ID value is illustrative):

```http
Set-Cookie: __Host-APP_SESSION=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Do not add `Domain=.example.com`, as that violates `__Host-` rules and widens cookie scope. Verify `Secure`/**`HttpOnly`**/`SameSite` using the **actual header sent to the browser**, not just by inspecting Java annotations.

### 5.3. Session Cookie Differs from CSRF Cookie

Spring Security Reactive stores the expected CSRF token in `WebSession` by default via `WebSessionServerCsrfTokenRepository`. If the frontend needs to read the CSRF token from a cookie to send in a header, you can configure `CookieServerCsrfTokenRepository`; `withHttpOnlyFalse()` for the CSRF cookie is a **special case** so JavaScript can read the token—**never use it for the session ID cookie**.

```java
// Snippet only when the frontend actually needs the cookie CSRF model.
.csrf(csrf -> csrf.csrfTokenRepository(
    CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
```

Requires importing `org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository`. Do not rely on `SameSite` as the sole CSRF defense; always keep token validation for side-effecting operations, define origin/cross-origin policies, and apply state/nonce/PKCE as required by the protocol. An `HttpOnly` session cookie does not stop the browser from automatically sending the cookie to the server.

## 6. Public Prefixes and Path Matching Rules

Another deployment has public URL `https://login.example.com/portal`, where the reverse proxy **strips `/portal`** before forwarding to the WebFlux root:

| Hop Point | URL |
| --- | --- |
| Browser starts login | `https://login.example.com/portal/oauth2/authorization/corporate` |
| Proxy forwards to application | `http://127.0.0.1:8080/oauth2/authorization/corporate` |
| Proxy headers | `X-Forwarded-Proto: https`, `X-Forwarded-Host: login.example.com`, `X-Forwarded-Prefix: /portal` |
| Public callback to register | `https://login.example.com/portal/login/oauth2/code/corporate` |
| Path app receives behind proxy | `/login/oauth2/code/corporate` |

`{baseUrl}` must reflect the public prefix when the transformer and proxy are aligned. If the app itself already has base path `/portal` and the proxy preserves that path, **do not accidentally double the prefix** by both setting base path and rewriting/forwarding prefix without testing.

If you set the cookie path to `/portal`, the browser sends the cookie back for `/portal/login/oauth2/code/corporate`, but not for `/login/oauth2/code/corporate`. The difference is that **the browser evaluates the public URL**, unaware of the upstream path. A path-restricted cookie configuration can use:

```java
// Replace only the WebSessionIdResolver bean in section 5; do not declare a second bean.
resolver.setCookieName("__Secure-APP_SESSION");
resolver.addCookieInitializer(cookie -> cookie
        .path("/portal")
        .secure(true)
        .httpOnly(true)
        .sameSite("Lax"));
```

This is an **alternative** to `__Host-APP_SESSION` when `Path=/portal` is needed; do not use both names simultaneously. If multiple apps share a host under different prefixes, consider distinct cookie names/paths to prevent session collisions; a host-only cookie does not isolate apps by path if `Path=/` is used.

## 7. Server-Side Sessions, Multiple Replicas, and Logout

WebSession may hold correlation state for the OAuth2 Authorization Code flow. With multiple instances behind a load balancer:

- After step 1, the callback request can land on a **different replica**. If the session lives only in the first instance's memory, the callback fails even with a valid cookie and exact redirect URI.
- Use Spring Session Reactive + a shared session store when login must not depend on stickiness; define TTL, encryption/network access, session serialization/versioning, and revocation.
- A cookie is a "session lookup ticket," not a guarantee that session data lives forever. A cookie `Max-Age` longer than the server-side TTL results in stale cookies pointing to expired sessions.
- Upon logout, invalidate the session and clear the corresponding cookie (matching name, path, and domain where applicable); re-verify in the browser. For OIDC logout, distinguish local logout from IdP logout/post-logout callbacks.
- Mitigate session fixation using standard session/authentication management and session ID rotation policies appropriate to your version/config; never derive session IDs from usernames or store sensitive tokens inside cookie values.

When debugging post-callback failures, always check **whether the same session ID was set and sent back**, then inspect the session store/state. Never log raw session IDs, authorization codes, ID tokens, access tokens, client secrets, or raw cookies.

## 8. Proving the Flow Works with Multi-Level Tests

### 8.1. Unit Tests: Forwarded URLs and Cookie Attributes

JUnit 5, Java 17+ example, running with compatible Spring Boot 3.x/Spring Framework. Uses the exact `SessionCookieConfig` from section 5 to test the defined contract. File `src/test/java/example/security/ProxyCookieContractTest.java`:

```java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseCookie;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

import static org.junit.jupiter.api.Assertions.*;

class ProxyCookieContractTest {

    @Test
    void forwardedRequestCarriesPublicOrigin() {
        ServerHttpRequest upstream = MockServerHttpRequest
                .get("http://127.0.0.1:8080/oauth2/authorization/corporate")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "login.example.com")
                .header("X-Forwarded-Port", "443")
                .build();

        ServerHttpRequest publicView =
                new ForwardedHeaderTransformer().apply(upstream);

        assertEquals("https", publicView.getURI().getScheme());
        assertEquals("login.example.com", publicView.getURI().getHost());
        assertEquals("/oauth2/authorization/corporate",
                publicView.getURI().getPath());
        assertFalse(publicView.getHeaders().containsKey("X-Forwarded-Host"));
    }

    @Test
    void webSessionCookieHasRequiredBrowserAttributes() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("https://login.example.com/").build());

        new SessionCookieConfig().webSessionIdResolver()
                .setSessionId(exchange, "test-opaque-id");

        ResponseCookie cookie = exchange.getResponse().getCookies()
                .getFirst("__Host-APP_SESSION");

        assertNotNull(cookie);
        assertTrue(cookie.isSecure());
        assertTrue(cookie.isHttpOnly());
        assertEquals("Lax", cookie.getSameSite());
        assertEquals("/", cookie.getPath());
        assertNull(cookie.getDomain());
    }
}
```

This is a **unit** test verifying the transformer and cookie resolver handle expected inputs; it **cannot prove** Nginx stripped spoofed headers or the IdP accepted the callback. `ForwardedHeaderTransformer()` does not authenticate header origin: the trust boundary still belongs to the proxy/network. Newer Spring Framework versions may change constructors/header-variant selection modes; consult Javadoc matching your build version.

Typical Gradle Groovy dependencies to add to an existing build:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Run:

```bash
./gradlew test --tests 'example.security.ProxyCookieContractTest'
```

On Windows use `gradlew.bat`. Unit tests are expected to **PASS**, with no mandatory application stdout; tests fail if attributes/URLs mismatch. Real issuer/secret configs are only needed for integration runs of the app, not for the unit test above.

### 8.2. HTTP Verification from Outside the Proxy

From a machine with public HTTPS and DNS reachability, use GET to inspect the redirect **without following it automatically**:

```bash
curl -sS -D - -o /dev/null \
  https://login.example.com/oauth2/authorization/corporate
```

Depending on configuration, the response is typically a 302 to the IdP. Check:

1. `Location` points to the exact IdP authorization endpoint and has a URL-decoded `redirect_uri` of exactly `https://login.example.com/login/oauth2/code/corporate`. No `localhost`, `127.0.0.1`, internal HTTP, port `8080`, or wrong path.
2. `Set-Cookie` when the application creates a session has the expected name/path/`Secure`/`HttpOnly`/`SameSite`. Do not assume every response always issues a cookie; inspect the response that actually creates the session.
3. Test with a real browser through the login flow; check DevTools → Network/Cookies to see whether the cookie is **accepted** when `Set-Cookie` is emitted and **sent back** on the callback request. Record the reason if the browser blocks the cookie (wrong path, SameSite, Secure, blocked third-party cookie).
4. Callback succeeds and the landing page authenticates the right user. Use two independent browser profiles to catch session/cookie scope collisions.
5. If running multiple replicas, repeat login when the callback lands on another replica; verify shared session store, TTL, and invalidation.

Notably, `curl` **does not fully simulate browser cross-site cookie/redirect policies**. Never use a passing `curl` check to conclude `SameSite=Strict` won't fail.

### 8.3. Security Test with Spoofed Forwarded Headers

Send a request to the **public proxy**, intentionally adding `X-Forwarded-Host: attacker.invalid` and `Forwarded: host=attacker.invalid;proto=http`. Expect the application to still produce a redirect URI to the allowed domain, or the proxy to reject the request; never generate a callback to the attacker. Run only in authorized test environments, and never send real OAuth2 data to non-allowlisted hostnames. If the upstream is directly reachable, test the network rules blocking that first.

## 9. Scenarios to Verify Before Production

| Scenario | Expected Observation |
| --- | --- |
| Public HTTPS → upstream HTTP | `Location`/`redirect_uri` uses public HTTPS; session cookie has `Secure` |
| Cross-site GET callback from IdP | `SameSite=Lax` cookie is still sent on top-level navigation; `state` matches |
| Cross-site POST callback / `form_post` | Dedicated design: browser cookie policy + Spring Security POST handling + CSRF/state |
| Public path `/portal` stripped by proxy | `redirect_uri` contains `/portal` exactly once; cookie `Path` covers public callback |
| Two different public hosts | Each host has its registered callback; host-only cookie by default, no leak across hosts |
| Two apps on the same host | Non-conflicting cookie names/paths; no cross-session mixup |
| Two replicas | Callback hitting a different replica still reads the authorization request via shared session store |
| Client-spoofed headers | Proxy strips or overwrites them; generated URLs are never attacker-controlled |
| Session expires mid-flow | Login fails cleanly without bypassing `state` or creating an invalid authenticated session |
| Logout after login | Session is destroyed and cookie can no longer access old resources |
| CORS/cross-origin SPA | Cookie `SameSite`, `Secure`, credentials, and CORS policy align; CSRF remains enforced |
| Refresh/relogin | No redirect loops; session lifecycle/callback remains stable |

For SPAs calling APIs via cross-origin `fetch`, `credentials: "include"` alongside CORS `Access-Control-Allow-Credentials` and an explicit origin list may be required; however, **cross-origin** and **cross-site** are distinct concepts. Never use `Access-Control-Allow-Origin: *` with credentials. This is a separate problem from OAuth2 top-level redirects.

## 10. Symptom-Based Troubleshooting

| Symptom | Cause to Check First | Right Direction to Fix |
| --- | --- | --- |
| IdP reports `redirect_uri_mismatch` | Wrong scheme/host/port/prefix; registered URI mismatch | Inspect decoded `Location`/`redirect_uri` and align proxy/registration together |
| Redirect returns `http://127.0.0.1:8080` | Upstream not processing forwarded headers | Check proxy sends proper headers, `forward-headers-strategy`, and trust boundary |
| `invalid_state` or login callback loops back to login | Browser not sending cookie / lost session / replicas not sharing store | Check `Set-Cookie`, Request Cookie, SameSite, Path, TTL, and session store |
| Cookie appears in header but browser won't save it | `Secure` on HTTP mismatch, `__Host-` wrong Path/Domain, browser policy | Check DevTools blocked reason, HTTPS config, and cookie attributes |
| Fails only when `/portal` is present | Prefix mismatch, double prefix, cookie path, or IdP redirect URI | Diagram public ↔ upstream mapping for both start and callback; apply prefix once |
| After login, redirects back to IdP in a loop | Session cookie missing after redirect or security state not persisted | Compare cookies sent/received and inspect response chain/session ID |
| Logging into app B drops app A's session | Two apps share cookie name with overlapping path/domain | Use distinct names/Paths or separate hosts |
| Fails only when scaling to multiple pods | Local in-memory `WebSession` | Use Spring Session Reactive + shared session store, check rollout |

Never fix these by **skipping `state` checks, disabling CSRF, setting `SameSite=None` on every cookie, unconditionally setting `Domain=.example.com`, or trusting all forwarded headers**. Those shortcuts may mask configuration bugs while widening security exposure.

## 11. Deployment Checklist and Acceptance Criteria

- [ ] Document **public scheme/host/port/path** and internal scheme/host/port/path for every route.
- [ ] Reverse proxy enforces a Host allowlist, TLS, upstream firewall, and strips/overwrites both `Forwarded` and `X-Forwarded-*` from clients.
- [ ] Spring WebFlux processes forwarded headers per framework version; no Servlet filter mistakenly added.
- [ ] Client `redirect-uri` and callback listener match the URL registered at the IdP completely, including prefix and `registrationId`.
- [ ] Session cookie is verified from actual responses: `Secure`, `HttpOnly`, `SameSite`, `Path`, no unintended `Domain`.
- [ ] Browser sends the cookie back on the OAuth2 callback in the actual response mode; `state`/nonce/PKCE and session correlation remain verified.
- [ ] CSRF protection for state-changing requests remains enabled; distinguish the CSRF token cookie from the session cookie.
- [ ] Replicas share sessions if required by deployment; verify TTL, logout, cookie clearing, and rollover.
- [ ] Unit tests, public proxy tests, browser tests, spoofed forwarded-host tests, and multi-replica tests all produce expected outcomes.
- [ ] Logs capture request IDs, normalized public URLs, and sanitized authentication failure reasons; never log raw `code`, tokens, cookies, client secrets, or session IDs.

## Official References

- [Spring Boot 3.3 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.configure-behind-a-proxy).
- [Spring Security Reactive — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html).
- [Spring Security Reactive — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html).
- [Spring Security Reactive — OAuth2 Client Authorization Grants / Authorization Request Repository](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html).
- [Spring Security Reactive — CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html).
- [Spring Session — WebFlux Custom Cookie](https://docs.spring.io/spring-session/reference/3.2/guides/boot-webflux-custom-cookie.html) and [WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html).
- [Spring Framework — CookieWebSessionIdResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html).
- [MDN — Set-Cookie, SameSite, Secure, HttpOnly, and cookie prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).
