# Diagnosing Redirect Loops, Lost Sessions, and Unsent Cookies in Spring Security WebFlux

## 1. Problem Statement and Diagnostic Goals

In **Spring Security reactive** (Spring WebFlux) applications, the following three symptoms often appear together yet can originate in completely different layers:

1. **Redirect loops:** the browser bounces from a protected page to `/login` and back to the protected page, or loops between the application and an Identity Provider (IdP), eventually failing with `ERR_TOO_MANY_REDIRECTS`.
2. **Lost sessions:** a user logs in successfully, yet the very next request is treated as anonymous; or succeeds once and then gets logged out after hitting another node, redeploying, or crossing a gateway.
3. **Cookies not sent:** the response includes `Set-Cookie`, yet subsequent requests omit `Cookie`; or the cookie is sent, yet the server cannot look up the right session.

**The goal** is to pinpoint whether the break occurs in **issuing the cookie, browser storage, browser sending, server session lookup, restoring `Authentication`, or computing the redirect target**. Never "fix" everything with `permitAll()`, disabling CSRF, turning off `Secure`, or opening CORS to every origin: those changes may hide the bug while weakening security.

Scope focuses on **Spring Boot 3.3 / Spring Security 6.x / WebFlux**. Servlet `HttpSession`, thread-local `SecurityContextHolder`, `HttpSecurity`, and Servlet `CookieSerializer` are not WebFlux's primary primitives. In WebFlux we inspect `WebSession`, `ServerSecurityContextRepository`, `ReactiveSecurityContextHolder`, `ServerHttpSecurity`, and `SecurityWebFilterChain`.

## 2. Visualizing the Login Flow

A valid **session-backed form login** flow typically proceeds as follows (status codes are illustrative; exact behavior depends on configuration):

```text
Browser                             Spring Security WebFlux
    | GET /private
    |------------------------------>|
    | 302 Location: /login          |  Unauthenticated; may store saved request
    |<------------------------------|
    | GET /login                    |
    |------------------------------>|
    | 200 login page + CSRF         |
    |<------------------------------|
    | POST /login (user, pass, CSRF, Cookie: SESSION=...)
    |------------------------------>|
    | 302 Location: /private        |  Auth OK, saves SecurityContext in WebSession
    | Set-Cookie: SESSION=...       |  Session ID may rotate against session fixation
    |<------------------------------|
    | GET /private; Cookie: SESSION=...
    |------------------------------>|
    | 200 protected content         |  Restores Authentication from session
    |<------------------------------|
```

**What must be proven:** the browser sends the right cookie **issued by the latest login**, the server finds that session, and `Authentication` is restored while handling `GET /private`. A `302` response does not by itself prove login succeeded. A cookie present on the request also does not prove the server-side session still exists.

With **OAuth2 Login/OIDC**, the flow differs: `/oauth2/authorization/{registrationId}` → IdP → `/login/oauth2/code/{registrationId}` → save authentication → target route. WebFlux typically uses the session to store the authorization request and `state` value to match callbacks. Losing the cookie at callback time restarts the login loop.

With a **Bearer-token-only Resource Server**, the policy is usually re-validating tokens per request with no form-login session needed. If an SPA redirects to login on every `401`, the bug likely lies in the `Authorization` header, token storage, or client-side redirect logic rather than `WebSession`.

## 3. Classifying Failures by Chain of Evidence

Never start by guessing "session timeout". Locate the **first broken link**:

| Evidence observed along a request sequence | Likely failing layer | Next question |
| --- | --- | --- |
| Login response lacks `Set-Cookie` even though session should be created | Session not initialized/saved; unexpected chain/login handler | Did login actually succeed? Was `SecurityContext` saved? |
| `Set-Cookie` present, yet DevTools reports **blocked/rejected** | Cookie attributes, HTTPS, or browser policy | Where are `Secure`, `SameSite`, Domain/Path/Expiry wrong? |
| Cookie stored in browser, yet next request **has no Cookie** | Cookie sending rules, cross-origin fetch, host-changing redirect | Does the target share host/path/scheme? Are `credentials` set? |
| Browser sends `Cookie: SESSION=...`, yet server creates a new session | Session store, load balancing, TTL, cookie name, or resolver | Which instance handled it? Is the session still in the store? |
| Session found, yet user remains anonymous | `SecurityContext` repository, custom filters, login flow, Reactor Context | Was `Authentication` saved/loaded? Is `NoOpServerSecurityContextRepository` active? |
| `Authentication` present, yet still `302`/`403` | Authorization, matchers, request cache, entry point | Which rule rejected it? Is the redirect target itself protected? |
| Fails only after IdP callback | OAuth2 `state`/redirect URI/session cookie | Did the callback carry the same session started before the IdP hop? |
| Fails only behind ingress/proxy or over HTTPS | Forwarded headers, scheme, host, path, cookie security | Is `Location` returning HTTP or an internal hostname? |

**Diagnose chronologically**, not from the final response alone. If the browser follows eight `302` hops, a final `ERR_TOO_MANY_REDIRECTS` error will not tell you which initial redirect was wrong.

## 4. Using DevTools to Spot Redirects and Blocked Cookies

In Chrome/Edge/Firefox, open Developer Tools and perform:

1. Go to **Network**, enable **Preserve log**, and reproduce the issue from a clean tab. Start recording before clicking Login; if using an incognito window, remember cookie/privacy policies may differ.
2. Filter by `Doc`/`Fetch/XHR` and statuses `301`/`302`/`303`/`307`/`308`. For each hop, record **method, request URL (redact sensitive queries), status, `Location`, host, scheme, and path**.
3. On the response that initiates/updates the session, inspect `Set-Cookie`; on the next request, inspect `Cookie`. Do not rely on the Storage table alone: a stored cookie is not necessarily attached to every request.
4. Under **Application/Storage → Cookies** and **Network → Cookies**, inspect `Name`, `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, and `Expires/Max-Age`. Some browsers display a **Blocked Reason** explaining why a cookie was rejected or omitted.
5. For cross-origin requests, also inspect `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, and `OPTIONS` preflights. Check whether JS `fetch`/XHR enables credentials.
6. Compare before and after redirects: is the browser switching from `https://app.example.org` to `http://app.example.org`, to `internal-service:8080`, to another domain, or losing an `/app` prefix?

**Never paste raw `Cookie`, `Set-Cookie`, `Authorization`, `code`, `state`, `id_token`, or full HAR files into tickets or chat.** Session cookies are credentials; OAuth2 callback URLs contain sensitive short-lived values. When sharing evidence, replace values with markers like `<redacted>` while preserving attribute names, domains, paths, statuses, and hop order.

### 4.1. Minimal Event Log Table

Build an empirical table for a single login attempt:

| Hop | Method & route | Status → Location (redact query) | Set-Cookie? | Cookie sent? | Instance/store |
| --- | --- | --- | --- | --- | --- |
| 1 | `GET /private` | `302 /login` | maybe | no | node A |
| 2 | `GET /login` | `200` | yes/no | yes/no | node A |
| 3 | `POST /login` | `302 /private` | usually yes/ID may rotate | yes | node A |
| 4 | `GET /private` | `200` expected | optional | yes | node A/B |

This is an **expected log template**, not fixed HTTP output. If failure happens at hop 4, compare session IDs **via securely hashed server fingerprints** and which instance handled the request; never print real cookie values. Spring Security may rotate the session ID after authentication to prevent session fixation—that change is normal, so always verify the browser uses the **latest** cookie issued by the server.

### 4.2. Observing HTTP with curl

You can inspect the first redirect response without following redirects automatically:

```bash
# Inspect response headers only; substitute your test host.
curl -sS -D - -o /dev/null --max-redirs 0 \
  https://app.example.org/private
```

Use a cookie jar when simulating browser session retention (the jar file holds sensitive data—use only on test machines and delete securely afterwards):

```bash
# Start session and save cookies issued by the server.
curl -sS -D - -o /dev/null -c session-cookies.txt \
  https://app.example.org/private

# Subsequent request sends back matching cookies per curl policy.
curl -sS -D - -o /dev/null \
  -b session-cookies.txt -c session-cookies.txt \
  https://app.example.org/private
```

These commands **do not perform login**; when unauthenticated, `302` is normal. For form login, you must fetch a valid CSRF token from the HTML/form and POST username/password with the cookie over TLS; otherwise `403` may be a CSRF rejection rather than a lost session. `curl` does not fully emulate browser `SameSite`, CORS, third-party cookie, or redirect policies. Therefore, **curl working while browsers fail** is a strong clue pointing to browser/cross-site behavior.

Never pass `curl -k` to "fix" TLS during real troubleshooting; certificate errors may be the exact reason browsers refuse the flow.

## 5. Understanding WebFlux Cookies Correctly

A `WebSession` cookie normally carries only a **session identifier**, not the entire `Authentication`; the server looks up the session by that ID. The default name is typically `SESSION` in WebFlux/Spring Session, yet you **must check real responses** because an app can customize it via `WebSessionIdResolver` or Boot properties.

| Attribute | When browsers reject or omit it | How to verify and fix |
| --- | --- | --- |
| `Domain` | Set to an invalid domain or mismatches request host | Check real host behind proxy; prefer host-only cookies when serving a single host. |
| `Path` | A `Path=/app` cookie is not sent to `/login/oauth2/code` outside `/app` | Check paths of *every* callback and API request; set the right path scope. |
| `Secure` | `Secure` cookies travel only over HTTPS (with some browser exceptions for localhost) | Use proper HTTPS from browser to reverse proxy; local plain HTTP needs profile-specific test settings. |
| `HttpOnly` | `document.cookie` cannot read it, yet browsers **still send it automatically** | Intended protection for session cookies; never disable just to debug. |
| `SameSite=Strict` | Blocks cookies across many cross-site navigations, including cross-site OAuth2 callbacks | Analyze navigation/callback flows; `Lax` fits top-level GETs, though not every POST/iframe flow. |
| `SameSite=Lax` | Cross-site `fetch` or iframes usually do not receive the cookie | Distinguish top-level navigation from XHR; configure per real flow. |
| `SameSite=None` | Modern browsers require `Secure`; still subject to third-party cookie blocking | Use HTTPS and check browser policies; never treat `None` as bypassing all privacy restrictions. |
| `Expires`/`Max-Age` | Cookie expired, `Max-Age=0` deletes it, or client clock skew | Watch for cookies *overwritten/deleted* in later responses too. |
| Cookie name | Two apps sharing a name on the same host/path overwrite each other | Inspect every `Set-Cookie` and Domain/Path scope; use distinct names/paths. |
| Size/limits | Oversized cookies or total headers rejected by browser/proxy | Measure header sizes; avoid storing large tokens/claims in session cookies. |

**Site does not mean origin.** `https://app.example.org` and `https://api.example.org` are different origins yet usually the same site under schemeful-site rules; they still require CORS for cross-origin JavaScript, while `SameSite` treats them differently from `https://another-company.org`. Conversely, switching `http` to `https` can change how browsers classify site boundaries. Verify **directly in DevTools** rather than guessing from similar domain names.

### 5.1. Configuring Cookies Under the Right Spring Boot WebFlux Namespace

Example for production serving browsers over HTTPS with same-site session cookies:

```yaml
# application.yml - example for a trusted HTTPS environment
server:
  reactive:
    session:
      timeout: 30m
      cookie:
        name: SESSION
        path: /
        http-only: true
        secure: true
        same-site: lax
```

Keys to remember: `server.reactive.session.cookie.name`, `path`, `domain`, `secure`, `http-only`, `same-site`, and `server.reactive.session.timeout`. **Never use** `server.servlet.session.cookie.same-site` in a WebFlux app, because Servlet properties do not control reactive cookies.

Set `secure: true` for HTTPS production. When running plain HTTP locally, browsers may refuse to send `Secure` cookies; isolate local test settings by profile and never ship test settings to production.

Avoid setting `domain: .example.org` out of habit if the app lives on a single hostname; sharing cookies across subdomains widens the scope receiving credentials. Domain cannot arbitrarily name a domain outside the host setting the cookie.

### 5.2. Customizing with `CookieWebSessionIdResolver` When Needed

You can customize how WebFlux writes cookies via a `WebSessionIdResolver` bean (class-level standalone snippet for a Spring WebFlux project with dependencies present):

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
public class SessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();
        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .httpOnly(true)
                .secure(true)
                .sameSite("Lax"));
        return resolver;
    }
}
```

This configuration is for HTTPS; **do not simultaneously declare a second resolver** with conflicting name or path settings. In apps using Spring Session WebFlux, the resolver also governs how session cookies are read and written. Pick **one** canonical source for cookie settings (Boot properties or an appropriate resolver bean) and inspect real `Set-Cookie` headers because custom beans can alter auto-configuration behavior.

## 6. Diagnosing Form-Login Redirect Loops

For a protected page `/private`, expected behavior is redirecting anonymous users to `/login` and then logging in. Classic bugs:

### 6.1. Login Page Itself Is Protected

Buggy rule example:

```java
// WRONG: the login page itself requires authentication.
http.authorizeExchange(rules ->
        rules.anyExchange().authenticated())
    .formLogin(form -> form.loginPage("/signin"));
```

If `GET /signin` also requires authentication and the entry point redirects to `/signin`, the chain loops `/signin → /signin → ...`. Proper configuration:

```java
// Snippet inside a WebFlux @Bean SecurityWebFilterChain.
return http
        .authorizeExchange(rules -> rules
                .pathMatchers("/signin", "/assets/**", "/public/**")
                .permitAll()
                .anyExchange().authenticated())
        .formLogin(form -> form.loginPage("/signin"))
        .build();
```

With a **custom** login page, the app must serve `GET /signin` itself and ensure the form POST targets the right **login processing endpoint** with credentials and a CSRF token. The DSL snippet above is **illustrative configuration** and does not generate the `/signin` controller or HTML. If you want Spring Security's default generated login page, use `formLogin(Customizer.withDefaults())` and verify `GET /login`.

### 6.2. Wrong Entry Point or Wrong Security Chain Matched

When multiple `SecurityWebFilterChain` beans exist, a higher-priority `@Order` chain wins if its `securityMatcher(...)` matches. An API chain expecting `401` can be caught by a browser chain issuing `302` redirects, or login/callback URLs can fall into the wrong chain.

Compare the **two matcher levels**:

- `securityMatcher(...)` selects **which chain** handles the request.
- `authorizeExchange(...).pathMatchers(...)` selects **rules inside** the already-selected chain.

Placing `anyExchange().authenticated()` ahead of `pathMatchers("/login").permitAll()` can swallow public routes or make rules unreachable. Order specific matchers ahead of `anyExchange`, and ensure catch-all chains never sit ahead of specialized chains.

### 6.3. Login Succeeds, Yet Redirect Loops Back to Login

When `POST /login` succeeds, Spring Security may redirect to the saved request (the URL requested before login) via `ServerRequestCache`, such as `WebSessionServerRequestCache`. If the cookie/session does not travel on the subsequent request or `SecurityContext` was not saved, the protected endpoint still sees an anonymous user and redirects back to `/login`.

Separate the diagnosis into steps:

1. Did `POST /login` actually succeed, or did it return `/login?error`? Did the browser receive the new cookie if the session ID rotated?
2. Did `GET /private` after the redirect send the right cookie?
3. Did the backend locate the corresponding `WebSession`?
4. Does `ReactiveSecurityContextHolder` contain an authentication on the new request?
5. Does the saved request/redirect target point to a moved URL, different host, misprotected route, or `/login` itself?

A `POST /login` returning `403` usually points to **CSRF tokens** before assuming session loss. In particular, custom login pages must include the token and preserve session cookies on POST. Never disable CSRF globally to make the flow "appear to work".

### 6.4. HTTP ↔ HTTPS or Host Redirects Behind a Proxy

A chain like `https://app.example.org/... → http://app.example.org/... → https://...` usually means the reverse proxy/ingress omitted original scheme info. If redirects emit `Location` with `http://10.x.x.x:8080` or an internal hostname, the proxy may not be passing forwarded headers or the server is not configured to trust them. See Section 9 to fix this at the right layer.

## 7. Distinguishing `WebSession` from `SecurityContext`

In WebFlux, keep these concepts separate:

- `WebSession` stores data tied to a session ID, typically looked up via the `SESSION` cookie.
- `WebSessionIdResolver` extracts session IDs from requests and writes/expires cookies on responses.
- `WebSessionServerSecurityContextRepository` saves/loads `SecurityContext` in `WebSession`, and can rotate the session ID on authentication to mitigate **session fixation**.
- `ServerSecurityContextRepository` is the SPI for persisting/restoring `SecurityContext` across requests. `NoOpServerSecurityContextRepository` intentionally **persists nothing**—ideal for stateless APIs, but wrong as a casual replacement in form-login apps.
- `ReactiveSecurityContextHolder` accesses `SecurityContext` inside the pipeline's **Reactor Context**, not Servlet-style ThreadLocal by default.
- `WebSessionServerRequestCache` holds the saved request for post-login redirects. It does not replace storing `Authentication`.

A session can **exist without containing a valid `SecurityContext`**. Conversely, a Bearer JWT request can hold `Authentication` in Reactor Context **without any session cookie**—which is expected in stateless designs.

### 7.1. Bug Where Custom Authentication Only Attaches Temporary Context

A custom `WebFilter` might create an `Authentication` and attach it to Reactor Context for the current request without **saving** it to `ServerSecurityContextRepository`. The next request loses authentication. If session-backed browser login is required, use Spring Security's built-in auth mechanisms or fully implement context persistence; never build a "fake login" `WebFilter`.

Example showing **read-only access** inside a reactive controller:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> authenticatedUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
```

This is a method fragment, not a standalone program; it emits a value only when the subscriber has a valid `SecurityContext`. Never conclude "session lost" because `SecurityContextHolder.getContext()` returned anonymous/null on another thread: that may simply be calling the wrong API in WebFlux.

### 7.2. Sessions Expiring or Disappearing Across Multiple Instances

If logging in on node A works, yet the next load-balanced request hitting node B sees an anonymous user, inspect the session store:

- With in-memory application sessions, node B cannot see sessions created on node A. Sticky sessions only mask the symptom and fail across restarts, scaling, or failovers.
- With **Spring Session reactive + Redis/MongoDB**, instances can share sessions, provided you verify `ReactiveSessionRepository` is genuinely wired, store connectivity works, namespaces/TTLs match, and serialization/eviction errors do not occur.
- Session timeout differs from **cookie expiry**: a cookie still present in the browser whose Redis record expired produces an anonymous request.
- Logout invalidates sessions; logout flows or cookie deletions from another response can look like "lost sessions" unrelated to timeout.
- Session ID rotation after login defends against session fixation. When tracing, inspect the latest ID returned to the browser rather than expecting it to match the pre-login ID.

Spring Boot 3.3 includes reactive Spring Session auto-configuration for Redis/MongoDB when matching dependencies and connection factories exist; do not confuse it with Servlet `@EnableRedisHttpSession`. Example adding dependencies when intentionally using shared reactive Redis sessions:

```groovy
dependencies {
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
}
```

This is a **dependency snippet for an existing Spring Boot/BOM Gradle build**, not a complete build file. Verify actual `ReactiveSessionRepository`/`WebSessionManager` beans at runtime, check Redis settings, and test switching instances. With Spring Session, `spring.session.timeout` controls repository timeout per Boot configuration; with default WebFlux sessions, `server.reactive.session.timeout` is the corresponding property. Check which one is active at runtime rather than editing one key and assuming sessions were extended.

## 8. Small WebFlux Example to Reproduce and Inspect Redirects

This example uses **Spring Boot 3.3 + Java 17+ + Gradle with the Spring Boot plugin/dependency management**. It is a minimal app with form login, `WebSession`, and a protected route. No external IdP is needed to learn how to observe `302`/cookies.

### 8.1. Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Avoid pulling in `spring-boot-starter-web` at the same time when targeting WebFlux, because Spring Boot normally prioritizes the MVC stack when both exist.

### 8.2. File `src/main/java/demo/SessionDiagnosticsApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SessionDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionDiagnosticsApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(rules -> rules
                        .pathMatchers("/public/**", "/login").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetails() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}local-demo-password")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @RestController
    static class DemoRoutes {

        @GetMapping("/public/ping")
        Mono<String> ping() {
            return Mono.just("pong");
        }

        @GetMapping("/private/whoami")
        Mono<String> whoami() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(ctx -> "hello " +
                            ctx.getAuthentication().getName());
        }
    }
}
```

This is a **complete Java file inside a Spring Boot project with the dependencies declared above**. The public class name must match the filename. `{noop}` is a plaintext password encoder for local demos; never use it in real environments. Keep CSRF protection enabled; with default form login, Spring Security generates both the form and the required CSRF token.

Run from project root:

```bash
./gradlew bootRun
```

Test in the browser:

1. Visit `http://localhost:8080/public/ping` → body `pong`.
2. Visit `http://localhost:8080/private/whoami` while logged out → redirects to the login page.
3. Submit `learner` / `local-demo-password` on the default login form.
4. After login, `/private/whoami` returns `hello learner`. Inspect `Set-Cookie` responses and `Cookie` requests in Network.
5. Delete **only localhost's session cookie** in DevTools and reload the protected route → redirects back to login. This intentionally reproduces "lost session state", not a security bug.
6. If you change `server.reactive.session.cookie.path` to a path that excludes `/private`, or enable `secure: true` over local HTTP, use DevTools to observe the browser omitting the cookie. Test only on a local profile and revert to avoid locking out real sessions.

Note: Spring Security may only create/set a cookie once a session is actually used or saved. Every `GET /login` response need not carry `Set-Cookie`; inspect **the entire sequence** rather than expecting a cookie on every hop.

### 8.3. Integration-Level HTTP Test

File `src/test/java/demo/SessionDiagnosticsApplicationTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SessionDiagnosticsApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousRequestRedirectsButLoginPageIsReachable() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");

        client.get().uri("/private/whoami")
                .exchange()
                .expectStatus().is3xxRedirection();

        client.get().uri("/login")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Run `./gradlew test`. The test verifies the public route, redirect on the protected route, and reachability of the login page. **It does not yet prove session persistence after form submission.** To test real persistence issues, add an end-to-end test preserving a cookie jar, valid CSRF token, POST login, GET protected route, and (where applicable) execution behind an ingress/multi-instance setup. Never use `mockUser` as proof that cookies are persisted: `mockUser` helps test authorization, not real login/session flows.

## 9. Reverse Proxies, Ingress, and Forwarded Headers

An app behind a gateway may receive plain internal HTTP while users connect over public HTTPS:

```text
Browser: https://app.example.org/private
      |
      v HTTPS
Ingress / Load balancer (TLS termination)
      |
      v HTTP
Spring WebFlux: http://service:8080/private
```

If the backend believes its base URL is `http://service:8080`, redirect URLs or OAuth2 `redirect_uri` values can use the wrong scheme, host, or path. Symptoms:

- `Location` points to an internal host, port `8080`, or `http`.
- OIDC callbacks emit HTTP instead of HTTPS, causing the IdP to reject `redirect_uri` or send users to the wrong host.
- `Secure` cookies are omitted on an HTTP hop because the **browser** actually switched to HTTP; note that browsers still send `Secure` cookies when the **public URL is HTTPS**, even if the **proxy → backend** hop uses HTTP.
- Inconsistent ingress prefix rewriting for `/app`: the browser requests `/app/login`, yet the backend emits `Location: /login`, breaking path/cookie alignment.

Spring Boot supports reading forwarded headers (enable only when a trusted ingress/proxy manages them properly):

```yaml
server:
  forward-headers-strategy: framework
```

In WebFlux, the `framework` strategy uses `ForwardedHeaderTransformer`; the proxy must supply accurate `Forwarded` or `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`, and when relevant `X-Forwarded-Prefix`. `native` can be used when the server and environment fully support it; inspect actual redirect outputs rather than applying keys blindly.

**Trust boundary:** the application must never trust raw forwarded headers from the Internet. The reverse proxy must strip or overwrite client-supplied headers before inserting trusted proxy headers; otherwise attackers can spoof hosts and redirects. Change the strategy only after verifying deployment architecture and testing scheme/host/prefix under the real ingress.

## 10. OAuth2 Login/OIDC: State, Callbacks, and Sessions

An Authorization Code flow typically involves:

```text
GET /oauth2/authorization/oidc
  -> saves OAuth2AuthorizationRequest + state in WebSession
  -> 302 to IdP /authorize

User logs in at IdP and browser redirects back to:
GET /login/oauth2/code/oidc?code=<redacted>&state=<redacted>
  -> browser sends previous session cookie
  -> app verifies state and exchanges code for tokens
  -> saves Authentication / SecurityContext
  -> 302 to protected page
```

Default paths can vary by `ClientRegistration` and login/callback configuration. In Spring Security WebFlux, a key implementation is `WebSessionOAuth2ServerAuthorizationRequestRepository`, which stores the authorization request inside `WebSession`. Consequently, an **OAuth2 callback arriving with a different session** will not find the initial authorization request and may fail with state/correlation errors. Never disable `state` validation to bypass this; `state` provides CSRF protection for OAuth2 authorization.

Check in order:

1. Did the request initiating OAuth2 login create/have a session, and did the browser store its cookie?
2. Does the IdP redirect to the **exact** `https://<public-host>/login/oauth2/code/{registrationId}` with matching route, prefix, and registration ID?
3. On the callback request, did the browser attach the earlier session cookie? If not, check `SameSite`, `Secure`, Domain/Path, and redirect type: top-level GET differs from `response_mode=form_post`.
4. If the callback carries the cookie yet still fails, check whether the backend locates the session and authorization request/`state`; across multiple instances, inspect the shared session store.
5. After the IdP callback succeeds and redirects back into the app, inspect the **post-login** cookie (which may rotate) and then verify `SecurityContext` on the next request.

`SameSite=Lax` generally allows cookies on top-level cross-site **GET navigations** (such as standard IdP GET redirect callbacks), yet can omit them on cross-site **POST callbacks** or inside iframes. `SameSite=None; Secure` may be needed in genuinely cross-site architectures, though third-party cookie blocking still applies; never switch broadly without browser evidence.

Another common bug: the frontend repeatedly executes `window.location.assign("/oauth2/authorization/oidc")` whenever an API returns `401`, even on login callbacks or public routes. That is a **client-side redirect loop** requiring navigation guards/route allowlists on the frontend, not backend cookie changes.

## 11. SPAs, CORS, and `fetch(credentials)`

Suppose a frontend at `https://app.example.org` calls a session-backed API at `https://api.example.org`. These are **cross-origin**, even if same-site. For browsers to send cookies on cross-origin `fetch`, both client and server must be configured properly.

Frontend:

```javascript
const response = await fetch(
  "https://api.example.org/private/whoami",
  {
    method: "GET",
    credentials: "include"
  }
);

if (response.ok) {
  console.log(await response.text());
}
```

With `fetch`, the default `credentials: "same-origin"` **does not send cookies to another origin**. `credentials: "include"` opts into cookie transmission, yet **does not override Domain, Path, Secure, SameSite, or browser privacy policies**. With Axios, the corresponding option is `withCredentials: true` on requests needing cookies.

The WebFlux backend must explicitly allow the origin and credentialed CORS. Example when this API genuinely serves the frontend above:

```java
package demo;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration policy = new CorsConfiguration();
        policy.setAllowedOrigins(
                List.of("https://app.example.org"));
        policy.setAllowedMethods(
                List.of("GET", "POST", "OPTIONS"));
        policy.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        policy.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", policy);

        return new CorsWebFilter(source);
    }
}
```

This class compiles in a project with `spring-boot-starter-webflux`. If CORS is already configured on the security chain, `WebFluxConfigurer`, or gateway, check that **two layers are not emitting conflicting headers**.

Mandatory checks:

- `Access-Control-Allow-Origin` must name explicit origins—**never use `*` with `Access-Control-Allow-Credentials: true`**.
- `OPTIONS` preflights typically carry no session or authentication. They must be processed by CORS before auth policies inadvertently reject them.
- Browsers forbid JavaScript from reading the `Set-Cookie` response header; `response.headers.get("Set-Cookie")` returning `null` **does not prove the server omitted the cookie**. Inspect DevTools Network/Storage.
- An OK CORS response **does not guarantee the browser will send cookies**; `credentials` and valid cookie attributes are still required.
- If the SPA uses session cookies on state-changing methods, design and test **CSRF tokens** and token delivery; `credentials: "include"` does not replace CSRF protection.
- In third-party contexts, browsers may block cookies even when both `SameSite=None; Secure` and CORS are valid. Evaluate same-site architecture, browser policies, and top-level navigation designs rather than weakening security globally.

## 12. Using Logs and Metrics to Pinpoint the Exact Failing Layer

In test environments, you may temporarily enable:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.web.server.session: DEBUG
```

Exact log lines vary by version and logger; enabling `TRACE` or full request/response dumps can accidentally log sensitive data. Never log raw Cookies, Authorization headers, form passwords, OAuth2 codes/`state`, or session IDs. To correlate between gateway and backend, use credential-free request/tracing IDs. If comparing session IDs, store only hashed/HMAC fingerprints under strict security and retention policies.

Example of a **temporary diagnostic `WebFilter`** logging only route buckets, whether a `SESSION` cookie exists, status, and Reactor signal without reading or printing the cookie value:

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.server.WebFilter;

@Configuration
class SafeSessionProbeConfig {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeSessionProbeConfig.class);

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter sessionProbe() {
        return (exchange, chain) -> {
            String path = exchange.getRequest().getPath().value();

            // Group routes into fixed buckets; never log raw paths/queries containing PII.
            String bucket = path.startsWith("/login")
                    ? "login" : path.startsWith("/oauth2")
                    ? "oauth2" : path.startsWith("/private")
                    ? "private" : "other";

            boolean hasSessionCookie =
                    exchange.getRequest().getCookies()
                            .containsKey("SESSION");

            return chain.filter(exchange).doFinally(signal -> {
                var status = exchange.getResponse().getStatusCode();
                LOG.debug(
                        "bucket={} status={} sessionCookiePresent={} signal={}",
                        bucket,
                        status == null ? "unset" : status.value(),
                        hasSessionCookie,
                        signal);
            });
        };
    }
}
```

Explanation:

1. `@Order(Ordered.HIGHEST_PRECEDENCE)` lets the probe observe early; ensure it mutates neither responses nor authentication.
2. `doFinally` runs when the reactive request completes, errors, or cancels. If status is unset or the response aborted, info may be incomplete; correlate with proxy access logs.
3. `sessionCookiePresent=true` only means a cookie **of that name** was present; it does not prove the session ID is valid, the session exists, or `SecurityContext` was restored.
4. Fixed buckets reduce PII leakage from dynamic paths. Remove the probe once investigation ends; never turn it into a log containing user IDs or session IDs.
5. If your app customizes the cookie name, update the probe to match the actual name in `Set-Cookie`.

Across backend and gateway, collect metrics: redirect counts by normalized source/target, `401`/`403` rates, login success/failure, session creation/expiration/eviction, Redis or session-repository errors, traffic distribution across instances, percentage of requests carrying session cookies, and OAuth2 `state` mismatches. Multiple `302`s in a single trace flag an issue, though counting redirects alone cannot pinpoint the cause without cookie/session context.

## 13. Reproduction Matrix to Separate Root Causes

Pick one authorized test account/client, one public route, one protected route, and a clean browser profile, holding the environment constant (localhost, HTTPS staging, or gateway staging). Key scenarios:

| Scenario | Expected outcome | If different, inspect |
| --- | --- | --- |
| Anonymous `GET /private` | Redirect to login page or `401` per entry point | Chain order, authentication entry point, route policy |
| Anonymous `GET /login` | Displays login page cleanly | Login route protected, missing controller for custom page |
| Valid login with CSRF token | Login succeeds; redirects and saves context | Auth failure, CSRF, saved request, `SecurityContext` repo |
| Next request in same browser | Latest cookie sent; access succeeds | Domain/Path/Secure/SameSite, request mode, session store |
| Delete session cookie and reload | Returns to anonymous state per policy | Verify test truly uses session vs. another Bearer token |
| Open another tab on same origin | Session reused when cookie is valid | Browser profile, partitioned storage, tab-local tokens |
| Redirect from IdP to GET callback | `state` verified, authentication succeeds | Callback cookie, redirect URI, `state` repo, shared store |
| Cross-site POST OAuth2 callback (if used) | Cookie policy fits flow, `state` still valid | `SameSite=Lax/Strict`, browser third-party policy |
| SPA calls API cross-origin | Request sends cookie when allowed; CORS valid | `credentials: include`, CORS `allowCredentials`/`allowedOrigins` |
| Switching between node A and node B | Session stays valid with shared store | Node-local memory sessions, TTL, namespace, serialization |
| After deliberate timeout | Session expires and prompts re-login | Mismatched repo vs. cookie timeouts, eviction |
| HTTPS behind proxy, `/app` prefix | Redirects and cookies preserve host/scheme/prefix | `X-Forwarded-*` and `Location`/Path rewriting |
| Form POST missing CSRF | Rejected per security policy | Do not call this a lost session when GET still works |

For each case, inspect **the initial request**, **the callback/login POST**, and **the first post-login request**, comparing cookies and authenticated users across hops. Run integration tests through the same ingress to catch TLS/forwarded-header issues missed on localhost.

## 14. Verified Troubleshooting Workflow

**Step 1 — Identify the login flow type.** Confirm whether this is session form login, OAuth2/OIDC browser login, a session-cookie SPA, or a Bearer-token API. Document protected routes, login/callback URLs, and entry point policies.

**Step 2 — Capture the full redirect chain.** Use DevTools Preserve log to trace statuses and `Location`; locate the very first request with a wrong scheme, host, prefix, route, or auth state.

**Step 3 — Verify cookies across three stages.** Did the server emit `Set-Cookie`? Did the browser store it? Did the next request send it? If not sent, find the exact cause in Domain/Path/Secure/SameSite/credentials/privacy policies and apply the smallest fix.

**Step 4 — Inspect the session backend.** If the cookie is present, verify the resolver matches the name, the session store finds the record, and the session has not expired. Check nodes, Redis/MongoDB vs. local memory, timeouts, logouts, and rotation.

**Step 5 — Inspect `SecurityContext`.** If the session exists yet the user is anonymous, check the login flow and `ServerSecurityContextRepository`; audit custom filters, `NoOpServerSecurityContextRepository`, and Reactor Context.

**Step 6 — Inspect policies and security chains.** If authentication is valid yet still redirects, check `@Order`, `securityMatcher`, `pathMatchers`, public login/callback endpoints, and `401`/`403` handlers.

**Step 7 — Reconcile proxy/IdP settings.** If it fails only outside localhost, fix `Forwarded` headers at the trusted proxy, `server.forward-headers-strategy`, public redirect URIs, and cookie Path/Domain. If it fails only on IdP callbacks, inspect `state`/session correlation before loosening policies.

**Step 8 — Re-test the entire behavior.** Fresh login, reload, second tab, logout, expiration, instance switch, OAuth2 redirect, and cross-origin requests; verify statuses, cookies, and authentication at every hop. After each change, re-run the targeted scenario and expand regression tests; avoid changing multiple variables simultaneously.

## 15. "Quick Fixes" That Make Things Worse

- **Disabling CSRF application-wide** because form login POST returns `403`: hides token issues and widens attack surface for cookie-backed apps.
- **Putting `permitAll()` on protected endpoints** to stop redirect loops: removes access control instead of fixing the root cause.
- **Turning off `Secure` in HTTPS production** merely because backend-to-proxy traffic uses HTTP: `Secure` depends on the protocol seen by the browser, not the internal hop after TLS termination.
- **Setting `SameSite=None` everywhere** without `Secure`/HTTPS and browser third-party policy review: browsers may reject the cookie and cookie transmission scope widens.
- **Setting `Access-Control-Allow-Origin: *` with `Access-Control-Allow-Credentials: true`:** browsers reject credentialed CORS, and misconfiguration can over-expose origins.
- **Checking `document.cookie` to conclude a session cookie is missing:** `HttpOnly` deliberately blocks JS from reading it.
- **Adding Spring Session without verifying the active bean/store:** a dependency alone does not guarantee requests use a properly configured shared reactive repository.
- **Reading thread-local `SecurityContextHolder` in WebFlux:** yields false negatives across thread switches; use Reactor Context.
- **Logging full request headers or HAR files to debug:** leaks session IDs, OAuth2 `state`/codes, and credentials.
- **Disabling OAuth2 `state` checks or logging codes/tokens in debug URLs:** breaks CSRF defenses and invites attacks.
- **Relying on `curl` to prove browser `SameSite`/CORS behavior:** `curl` does not enforce full browser policies.
- **Expecting pre-login and post-login session IDs to match:** Spring Security may intentionally rotate IDs against session fixation.

## 16. Completion Criteria and Further Reading

Conclude an investigation is resolved only with **complete evidence**: valid login request, expected redirect, latest cookie accepted by the browser, next request sends the cookie with the right host/path/scheme, server locates the session, `SecurityContext` is restored, protected routes return expected results, and the flow stays stable through real HTTPS/ingress/multi-instance setups. For OAuth2, prove callbacks validate `state`; for SPAs, prove credentialed CORS and CSRF both work. Intentional session ID rotation must not be treated as a bug.

Official references for APIs and configuration:
- [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html)
- [Spring Security — Reactive OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html)
- [Spring Security — WebSessionServerSecurityContextRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Boot 3.3 — Common Application Properties (reactive session)](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
- [Spring Framework — CORS in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html)
- [Spring Boot 3.3 — Spring Session reactive](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html)
- [Spring Session — WebSession integration](https://docs.spring.io/spring-session/reference/web-session.html).