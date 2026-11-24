# HTTPS, secure cookies, and protection against session hijacking in Spring Security

## 1. Objectives and threat model

For a web application with login, **session hijacking** is when an attacker takes over another user's session, typically by discovering, fixing, stealing, or abusing the **session identifier**. When the server treats a session cookie as proof of an authenticated account, anyone holding a valid cookie can send requests on the user's behalf unless additional protections exist.

Three defensive layers must be designed together:

1. **HTTPS/TLS across the entire lifecycle**: prevent cookies, credentials, and exchanged content from being exposed or modified in transit.
2. **Proper cookie/session policy**: securely generated session secrets, server-side storage, cookies constrained with `Secure`, `HttpOnly`, `SameSite`, `Path`, host-only domain, and TTL; rotate session ID after authentication; invalidate sessions on logout/revocation.
3. **Defenses against unauthorized use of an existing session**: prevent XSS and CSRF, enforce authorization, require additional authentication for sensitive actions, detect anomalies, and invalidate sessions when compromise is suspected.

No single mechanism solves everything: HTTPS does not fix XSS; `HttpOnly` does not stop malicious JavaScript from sending same-origin requests; `SameSite` does not replace CSRF tokens; rotating the session ID at login does not invalidate a **new session** stolen afterward.

### Typical attack scenarios

| Scenario | What the attacker has | Primary defensive layer |
| --- | --- | --- |
| Reading cookies over unencrypted HTTP | Ability to observe/intercept network traffic | HTTPS on all requests + `Secure` + HSTS |
| **Session fixation** | Session ID known before the victim logs in | Rotate session ID after login, reject client-supplied IDs |
| **Session hijacking** via logs or malware | Valid session ID of a user | Redact logs, endpoint controls, TTL, revocation, monitoring, MFA for sensitive actions |
| **XSS** | JavaScript running inside the app's origin | Output encoding, sanitization, CSP, avoid dangerous HTML; `HttpOnly` reduces direct cookie theft |
| **CSRF** | Forcing a logged-in browser to send unintended requests | CSRF tokens, appropriate SameSite, Origin/Fetch Metadata where applicable |
| **Subdomain cookie injection** | Control over a sibling host | Host-only cookies, `__Host-` prefix, avoid overly broad `Domain` |
| Overly long sessions or persisting after privilege revocation | Old cookie still valid | Idle + absolute timeouts, session invalidation, revalidation |
| Proxy/header spoofing | Ability to send self-asserted `X-Forwarded-*` | Trusted proxy boundary, strip/overwrite inbound forwarded headers |

The focus here is **Spring Security authentication in Servlet/Spring MVC applications** with `HttpSession`. The final sections distinguish WebFlux, bearer JWTs, and SPA architectures.

## 2. Where does the login session actually live?

In a typical session-based application:

```text
Browser                                         Spring MVC + Spring Security
  |                                                |
  | POST /login --username/password + CSRF token-> |
  |                                                | AuthenticationManager
  |                                                | verify credentials
  |                                                | SecurityContext + Authentication
  |                                                | HttpSession issued / ID rotated
  | <- Set-Cookie: __Host-SESSION=<random>; ... ----|
  |                                                |
  | GET /account                                    |
  | Cookie: __Host-SESSION=<random>                  |
  | ----------------------------------------------> |
  |                                                | container resolves HttpSession
  |                                                | SecurityContextRepository loads context
  |                                                | AuthorizationFilter checks permissions
  | <---------------------------------------------- |
```

**A session cookie is usually only a random reference identifier.** `Authentication`, `GrantedAuthority`, and session attributes live on the server side, in container memory or a shared session store. In Spring Security Servlet, `HttpSessionSecurityContextRepository` is an implementation that uses `HttpSession` to store/load `SecurityContext`; it does not mean all authentication data is stuffed directly into the cookie.

Depending on configuration, the app may use the cookie name `JSESSIONID` or another name; changing the cookie name **does not replace** real security. Spring Security also supports stateless mode or bearer token authentication, where session storage models differ.

### Responsibility boundaries

- **TLS terminator / reverse proxy / load balancer**: TLS certificates, HTTPS redirects/HSTS, managing trusted headers, restricting protocols/ciphers, and securing transport channels.
- **Servlet container or Spring Session**: generating IDs, storing sessions, `Set-Cookie`, handling timeouts/invalidation.
- **Spring Security**: authentication, session fixation protection, `SecurityContext`, CSRF, logout, authorization, and security headers.
- **Application**: business-data authorization, absolute session lifetime if needed, event-driven session revocation, MFA/step-up, and incident handling.

If the project uses SSO/OIDC, the **IdP session** and **local app session** are two distinct objects; the IdP's SSO cookie is not Spring MVC's session cookie.

## 3. Mandatory HTTPS/TLS across the entire session, not just the login page

Some systems only use HTTPS for `/login`, while loading `/account` or other resources over HTTP. In that case cookies can leak or requests can be tampered with on the network, regardless of whether the password was sent over TLS.

### Transport requirements

1. Serve all pages and APIs carrying login sessions exclusively over **HTTPS** with a trusted, valid, hostname-matching certificate. Prefer TLS 1.3, keep TLS 1.2 securely configured if needed; disable obsolete protocols/ciphers.
2. Redirect HTTP to HTTPS **before issuing any authentication cookie**; never create security-relevant sessions over HTTP.
3. Set `Secure` on every authentication cookie; compliant browsers will not send that cookie on insecure HTTP requests.
4. Use **HTTP Strict Transport Security (HSTS)** so browsers that have received the policy remember the host must use HTTPS. HSTS does not protect the very first visit without a cached policy or preload; `Secure` is still necessary.
5. Avoid mixed content and script resources loaded over HTTP. An untrusted script running in an HTTPS origin undermines transport protection.
6. Control TLS across hops between load balancer, ingress, proxy, and application server; if backend traffic crosses untrusted networks, use appropriate encryption/private channels. Never assume edge TLS termination automatically secures internal networks.

### What is HSTS?

The server sends a response header, for example:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

HSTS-capable browsers remember the policy for the host for `max-age` seconds after receiving it over valid HTTPS. `includeSubDomains` should only be enabled when **every subdomain in scope** is HTTPS-ready; use `preload`/preload submission only after weighing long-term consequences and having a rollback plan.

**Spring Security Servlet 6.x enables HSTS headers by default for HTTPS requests** in its default security headers configuration; if a proxy terminates TLS and the app sees HTTP requests, verify the final headers actually sent by the edge or Spring Security. Never conclude HSTS is active merely by reading a config file.

### Edge HTTPS verification examples

```bash
curl -I https://app.example.org/login
curl -I http://app.example.org/login
```

On the HTTPS response, check `Strict-Transport-Security` (if policy applies) and redirect/cookie/cache headers. On HTTP, expect a redirect to HTTPS **without issuing an authentication session cookie** before redirecting. `curl` does not enforce HSTS like a browser with cached HSTS state; verify browser behavior separately.

## 4. Secure cookie attributes

Example of a **host-only session cookie**:

```http
Set-Cookie: __Host-SESSION=<random-unpredictable-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

`<random-unpredictable-id>` is an illustrative placeholder, **not a real cookie value**. Never print raw session IDs in logs or public examples.

| Attribute | Proper meaning | What it does not guarantee |
| --- | --- | --- |
| `Secure` | Browser only sends cookie over eligible HTTPS channels | Does not stop XSS, CSRF, malware, or server compromise |
| `HttpOnly` | JavaScript cannot directly read/modify the cookie via `document.cookie` | XSS can still issue same-origin requests using the cookie automatically |
| `SameSite=Strict` | Restricts sending cookie on cross-site requests | Can break some SSO/navigation flows; does not block all cross-origin same-site requests |
| `SameSite=Lax` | Allows cookie on safe top-level cross-site navigation, blocks many cross-site POSTs | Does not prevent all CSRF (especially state-changing GETs, same-site subdomains, and browser quirks) |
| `SameSite=None` | Allows cross-site cookies per browser policy | **Must include Secure**, may be blocked by third-party cookie restrictions |
| `Path=/` | Hints URL path scope where browser sends cookie | **Not** a security isolation boundary between applications |
| Omitted `Domain` | Host-only cookie; restricted to the issuing host | Host itself still needs protection; does not block XSS on that host |
| `Domain=example.org` | Shares cookie with the domain and matching subdomains | Widens attack surface if a sibling subdomain is compromised |
| `Max-Age` / `Expires` | Controls how long the browser retains the cookie | Does not replace server-side session timeout/revocation |
| `__Host-` name prefix | Supporting browsers enforce `Secure`, `Path=/`, and **no Domain** | Does not prove cookie contents are safe or user is authentic |

**Default recommendation for traditional session cookies:** host-only, `Secure`, `HttpOnly`, `SameSite=Lax` or `Strict` depending on the product, narrow domain/path, and no unnecessarily long Max-Age. For embedded iframes or cross-site POST/OIDC `form_post` flows, analyze carefully before choosing `SameSite=None`; never skip `state`, `nonce`, and CSRF just to fix cookie errors.

### Cookie prefixes and host-only

The name `__Host-SESSION` requires meeting these conditions in prefix-supporting browsers:

- Cookie is sent from a secure origin over HTTPS and carries the `Secure` attribute.
- `Path=/` is mandatory.
- **No `Domain` attribute**; only the issuing host controls that host-only cookie.

For applications running under a servlet context path such as `/portal`, verify how the container sets `Path`. If the cookie lacks `Path=/`, browsers will reject the `__Host-` prefix. Do not use a nice-looking prefix with invalid attributes.

`__Secure-` only requires `Secure`; it does not guarantee host-only or `Path=/` like `__Host-`. All cookie prefixes should be inspected in the target browser's Network/Storage devtools.

### Cookies and sessions have two separate lifecycles

`server.servlet.session.timeout: 20m` primarily configures the Servlet container's **idle session timeout**. A session cookie may remain in the browser after the server deletes the session, and conversely deleting a cookie in the browser does not guarantee server-side session data has expired.

- **Server-side timeout** determines whether the cookie ID can still retrieve a valid `HttpSession`.
- **Cookie Max-Age/Expires** determines how long the browser keeps the ID; some browsers also have session-restore features.
- **Absolute timeout** (e.g., max 8 hours even while active) usually requires additional app/store logic if policy demands it; it is not automatically included just by setting an idle timeout.
- On logout, the server must invalidate the session; deleting only the browser cookie **is insufficient** to stop reuse of a previously copied session ID.

## 5. Spring Boot 3.x configuration for session cookies (Servlet)

This is a **Spring Boot 3.x / Spring MVC / Servlet**, Java 17+ configuration with the session-cookie name `__Host-SESSION`. In `src/main/resources/application.yml`:

```yaml
server:
  servlet:
    session:
      timeout: 20m
      tracking-modes: cookie
      cookie:
        name: "__Host-SESSION"
        secure: true
        http-only: true
        same-site: lax
        path: /

# Use ONLY when deployed behind a TRUSTED proxy:
# server:
#   forward-headers-strategy: framework
```

Explanation:

- `secure: true` ensures the `Secure` attribute is emitted **even** when the app sits behind a proxy sending HTTP to the backend; client-facing HTTPS must still be verified at the edge.
- `http-only: true` prevents JS from reading the session cookie. Do not confuse this with a CSRF token cookie that sometimes **must be readable by JavaScript** in an SPA.
- `same-site: lax` is a pragmatic policy for many web apps and top-level login redirects. `Strict` may fit better if UX/SSO permits; test actual cross-site callbacks.
- `path: /` and **no `cookie.domain` configured** so the `__Host-` prefix is valid. Ensure containers/proxies do not inject Domain or alter Path.
- `tracking-modes: cookie` prevents session tracking via URL rewriting; verify containers and link generation do not append `;jsessionid=...`.
- `timeout: 20m` is just an example idle timeout and must match security policy and product requirements.
- Never set `cookie.max-age: 30d` and assume it is safe; session cookies should typically live for the browser session while the server enforces expiration/revocation.

### When using a TLS-terminating proxy/ingress

`server.forward-headers-strategy: framework` lets Spring Boot read scheme, host, and port from forwarded headers in appropriate environments. **Enable it only when a trusted reverse proxy strips/overwrites `Forwarded` and `X-Forwarded-*` values coming from untrusted clients.** Otherwise, attackers can forge host/scheme to manipulate redirect URLs, absolute links, or security checks.

Distinguish clearly:

1. Browser ↔ ingress uses HTTPS with a valid certificate.
2. Ingress ↔ backend traverses a private network or HTTPS if the trust boundary requires it.
3. Backend determines the original request via **controlled** forwarded headers.
4. Outermost response received by the browser truly carries a `Secure` cookie and proper HSTS.
5. Do not expose the backend port directly to the Internet if it is meant to be called only by ingress.

**Never hardcode** trusting `X-Forwarded-Proto: https` from arbitrary sources. Never use `server.forward-headers-strategy` as a substitute for TLS.

## 6. Spring Security 6.5 Servlet: authentication, session fixation, and logout

Below is a **usable configuration class in a Spring Boot MVC application** with `spring-boot-starter-web` and `spring-boot-starter-security`. You must supply a proper user/credential source for the app; default `formLogin` is enabled to illustrate the browser login path.

File `src/main/java/demo/security/WebSecurityConfig.java`:

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation -> fixation
                                .changeSessionId()))
                .logout(logout -> logout
                        .invalidateHttpSession(true)
                        .clearAuthentication(true))
                .build();
    }
}
```

This configuration:

- Enforces authentication on every path outside `/public/**`; it does not imply resource-ownership authorization is already present.
- Uses `changeSessionId()` to **rotate the ID upon successful authentication**, preventing victims from logging into an attacker-fixed session ID.
- Preserves **default CSRF protection** for browser forms/sessions; never call `csrf.disable()` arbitrarily.
- Supports logout: invalidates the HTTP session and clears authentication; Spring Security includes suitable logout handling by default. With CSRF enabled, standard logout is `POST /logout` with a CSRF token.
- Does not replace the cookie settings in `application.yml`; framework security and container cookie configuration complement each other.

**Version note:** this example targets Spring Boot 3.x / Spring Security 6.5 Servlet. For Spring Security 7.x / Boot 4.x or WebFlux apps, check the matching version docs and test compatibility before adopting.

### When is the configuration above not enough?

- Does not yet define DB users/credential hashing, password policies, MFA, rate limiting, or forgot-password.
- Does not yet set absolute TTLs, multi-device session management, or a distributed session store.
- Does not yet implement a policy to log out all devices after password reset or account revocation.
- Does not yet prevent XSS in dynamic HTML content rendered by the application.
- Does not yet guarantee ingress/HSTS/backend TLS and CSP match actual pages.
- Does not yet cover external components such as remember-me, OAuth2 authorized client/refresh tokens, or WebSocket sessions.

Never rely on one illustrative `SecurityFilterChain` to claim the application is "completely immune to hijacking".

## 7. Session fixation: why rotate the ID after login?

**Session fixation** differs from post-login hijacking. In fixation, the attacker knows or forces the browser to use an ID **before** the victim logs in. If the server keeps using that same ID after authentication, the attacker can reuse the known ID.

```text
Before login
  Attacker knows session ID = old-id
  Victim sends old-id to the app (due to fixation flaw)
                       |
                       v
Victim logs in successfully
                       |
       [ID unchanged]  |  [ID rotated properly]
            |          |        |
 old-id becomes        |  new-id randomly generated
 authenticated         |  old-id is no longer valid
            |          |        |
 Attacker accesses     |  Attacker with old-id cannot
 using old-id          |  access the new session
```

Spring Security Servlet on modern Servlet containers **prevents session fixation by default using `changeSessionId()`** upon successful authentication. Available strategies:

| Strategy | Behavior | Notes |
| --- | --- | --- |
| `changeSessionId` | Changes the existing session's ID via Servlet API | Default on Servlet 3.1+; usually appropriate |
| `newSession` | Creates a clean new session, retaining certain Spring Security data | May drop non-whitelisted state |
| `migrateSession` | Creates a new session and copies attributes from the old session | Watch out for untrusted or stale attributes |
| `none` | Disables session fixation protection | **Do not use** |

Rotating the ID **at login** only stops fixation at the authentication boundary. If an attacker obtains the **current new ID** via XSS, logs, malware, or an unprotected endpoint, they can still use it. Thus other defensive layers must be combined.

### Do not reimplement weaker rotation yourself

Do not build a custom `sid` cookie and leave the old ID valid after login, or "rotate" merely by renaming the cookie. If forced to build a custom session store, revoke the old ID mapping on the server and verify new IDs are generated with a CSPRNG. With Spring Security, prefer the tested framework/container fixation protection.

For **step-up** or elevating to admin privileges, policy may require additional rotation/re-authentication, especially when the security context changes assurance level. Clarify whether the system uses browser sessions, bearer JWTs, SSO, or API keys to apply controls in the right place.

## 8. Session hijacking: session ID leak sources to block

### 8.1. Network and proxies

- Never allow clients to send authentication cookies over HTTP; enforce HTTPS, `Secure`, and HSTS.
- Never configure load balancers/edge servers to log full request headers including `Cookie` or `Authorization`.
- Never reflect cookies/tokens into `Location`, URL queries, HTML/JS error pages, or crash reports.
- Never embed session IDs in paths/queries: `/profile;jsessionid=...`, `?sid=...` easily end up in browser history, Referer headers, and proxy/CDN logs.
- Never pass session secrets as headers to third-party analytics or monitoring SaaS.

### 8.2. XSS and client-side scripts

`HttpOnly` prevents `document.cookie` from reading the session cookie in supporting browsers, yet **does not stop same-origin XSS scripts from firing requests that the browser automatically attaches cookies to**. For instance, attacker JavaScript on a user's page can invoke business endpoints directly instead of stealing the cookie value.

Apply:

- Encode output properly for HTML/attribute/JS/URL contexts; never concatenate user data into `innerHTML` without proper sanitization.
- Restrict dangerous DOM APIs; review template engines and markdown/HTML viewer libraries.
- Deploy a meaningful **Content Security Policy (CSP)**, such as nonce/hash policies and avoiding `unsafe-inline` per project needs. CSP is defense-in-depth, **not a replacement for output encoding**.
- Maintain dependency hygiene, review third-party scripts, use SRI where appropriate, and restrict JavaScript origins.
- Avoid storing bearer tokens or session IDs in `localStorage`/`sessionStorage` in apps where JS does not need to hold them.
- For high-risk operations, re-check current permissions and enforce step-up MFA/transaction confirmation, since browsers still send `HttpOnly` cookies automatically.

### 8.3. Browser extensions and compromised devices

Cookie flags do not stop an attacker who has compromised the machine or can read the browser profile from extracting session data. Risks also exist on shared computers, malicious extensions, and insecure backups/profile sync. Countermeasures here are bounded TTLs, revocation, monitoring, device sign-out, and MFA for critical actions—not just adding another cookie attribute.

## 9. CSRF: SameSite does not replace CSRF tokens

**Cross-Site Request Forgery (CSRF)** occurs when an attacker-controlled site causes a victim's browser to send a request carrying valid session cookies to the application. `Secure` and `HttpOnly` cookies do not stop browsers from automatically attaching cookies.

### Why is SameSite only a supplemental layer?

- `SameSite=Lax` still sends cookies on many **top-level cross-site GETs**. GET endpoints **must never have side effects** such as changing email or making payments.
- Subdomains under the same registrable domain can count as **same-site** despite having different **origins**; a compromised subdomain can issue requests SameSite does not block as expected.
- Browser policies and OAuth/OIDC callbacks have nuances; never rely on every browser behaving identically.
- `SameSite=None; Secure` is often needed in certain cross-site flows, making CSRF/state/nonce protection even more critical.

With **Spring Security Servlet**, CSRF is enabled by default for browsers/sessions. State-changing operations (POST/PUT/PATCH/DELETE) must supply a valid CSRF token, including login/logout when required by the flow. Never use `GET` for mutations.

### Proper logout form

Example fragment in a server-rendered HTML template carrying Spring Security's CSRF model:

```html
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="...CSRF_TOKEN_FROM_SERVER...">
  <button type="submit">Log out</button>
</form>
```

`...CSRF_TOKEN_FROM_SERVER...` is only an **illustrative placeholder**; the template engine/Spring Security library must inject the real CSRF token, never hardcode it. With Thymeleaf integrated with Spring Security, the framework can generate the appropriate hidden input automatically per configuration.

In Spring Security 6.5, `GET /logout` by default typically renders a confirmation page; `POST /logout` performs logout when CSRF is enabled. Never create a state-changing `GET /logout-all` endpoint that skips CSRF and re-authentication.

### SPAs and CookieCsrfTokenRepository

In an SPA sending same-origin requests with an `HttpOnly` session cookie, a common pattern is having the browser read the **CSRF token** from a cookie or protected endpoint and send it back in a dedicated header.

```java
// Spring Security Servlet configuration snippet; not a standalone class.
http.csrf(csrf -> csrf
        .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse()));
```

Spring Security handles tokens by version, including deferred token loading, XOR/BREACH protection, and refresh flows after login/logout; when configuring an SPA with `CookieCsrfTokenRepository`, consult the SPA CSRF guide for your exact version. **`withHttpOnlyFalse()` applies only to the CSRF token cookie** so JavaScript can read it if needed; **never set `HttpOnly` to false on the session cookie**.

For pure bearer-token APIs stored outside browser cookies without automatic credential attachment, the CSRF threat model differs. Never copy the conclusion "CSRF is unnecessary" to a session-cookie app merely because the frontend calls JSON APIs.

### CORS is not a CSRF defense

CORS primarily governs whether JavaScript at another origin can read responses or send certain preflighted requests; it **does not replace CSRF tokens** for requests that automatically attach cookies. With `Access-Control-Allow-Credentials: true`, never grant wildcard origins carelessly, especially on sensitive endpoints. Multi-frontend setups must use explicit origin allowlists and accurately test `SameSite` cookies.

## 10. Logout, timeouts, and session revocation

Three distinct events are not synonymous:

1. Browser **deletes the cookie**.
2. Server **invalidates the session**.
3. Identity Provider **terminates the SSO session** if logged in via OIDC/SAML.

For logout in an MVC application:

```text
POST /logout + CSRF token
    -> LogoutFilter
    -> SecurityContextLogoutHandler
       + clear SecurityContext
       + invalidate HttpSession
    -> clear/update CSRF/remember-me data per handlers
    -> respond /login?logout or configured success handler
```

Spring Security 6.5's default logout clears authentication, context, and invalidates the session. `logout.deleteCookies(...)` or `Clear-Site-Data` can help remove browser cookies, yet **cookie deletion must never substitute for server-side invalidation**. When cookie name, Path, or Domain differ, a delete-cookie directive can fail to match, so test on a real container.

### Choosing TTLs and revocation mechanisms

| Mechanism | What it stops | Limitations |
| --- | --- | --- |
| **Idle timeout** | Inactive sessions expire after a period | An active attacker can keep the session alive indefinitely without an absolute TTL |
| **Absolute timeout** | Stops indefinite session use despite activity | Users may need to log in/reauthenticate again; requires storing `createdAt` separately |
| **Session ID rotation** | Prevents fixation and invalidates some older IDs | Does not stop an attacker using a stolen **current** ID |
| **Invalidate on logout** | Rejects the old ID server-side | Other sessions on other devices remain unless revoked |
| **Event-driven revocation** | Password change, account disable, compromise detection | Requires a session registry/account index and cross-node propagation |
| **Step-up MFA** | Increases assurance for sensitive actions | Does not by itself invalidate a stolen session, especially if attacker controls the second factor |
| **Concurrent session control** | Limits active session count | Must not assume one session equals one verified device |

Example hypothetical policy: idle = 20 minutes, absolute = 8 hours, require extra authentication within 5 minutes before changing MFA. These three values are designed **independently**; there is no "one safe TTL for every app".

### Revoking all sessions of a user

On password reset, account lock, or detected session compromise:

1. Resolve the trusted account ID from the user system.
2. Locate active sessions via the session registry or Spring Session index.
3. Invalidate them in the shared session store.
4. Review refresh tokens, remember-me tokens, API keys, mobile sessions, and IdP sessions **system by system**; invalidating a servlet session does not automatically revoke OAuth access tokens.
5. Log an audit record and notify the user per policy without putting raw session IDs in emails/logs.

If `Authentication` holds an authorities snapshot from login time, permission changes in the DB may **not immediately reflect** in active sessions. Revalidate/invalidate or enforce a permission-version check before sensitive actions.

## 11. Multi-instance: Spring Session, Redis, and consistency

In Kubernetes or load-balanced deployments, keeping per-instance session maps causes requests routed to another pod to lose context, or logout on pod A not to take effect immediately on pod B.

**Spring Session** can replace the `HttpSession` store with Redis or another suitable backend shared across instances. Even so:

- Configure TTLs, keyspaces/indexes, serializers, and a compatible Spring Session version.
- Restrict Redis access permissions, use TLS if crossing trust boundaries, and never expose Redis directly to the Internet.
- Design cluster-wide invalidation/revocation, avoiding node-local caches retaining sessions after revocation.
- Test the distinction between **session idle TTL** and **absolute TTL** yourself if policy requires both.
- Avoid storing bearer/refresh tokens or excessive PII inside session attributes.
- Never treat sticky sessions as an excuse to skip shared storage/invalidation when scaling or failover is required.
- Never replace a session ID with a frontend-chosen UUID and trust it.
- For WebSockets and server-sent events, check connection lifetimes, revocation propagation, and re-authorization; HTTP logout does not necessarily sever already-open channels immediately.

Conceptual multi-device example:

```text
Account alice
  session S1 (laptop) -> lastSeen, createdAt, device label
  session S2 (mobile) -> lastSeen, createdAt, device label
  session S3 (shared computer) -> lastSeen, createdAt, device label

User clicks "Log out all devices"
  -> invalidate S1, S2, S3 in the shared session store
  -> revoke remember-me / refresh-token families per product
  -> force re-auth on next request
```

Device labels and IPs are UX/audit hints only; **they do not prove device identity**.

## 12. Standalone Java 17 example: rotation, Secure cookie, timeout, and logout

The example below **illustrates a state machine** and **does not replace** a container's `HttpSession` or enforce real HTTPS/CSRF. In real Spring Security apps, prefer framework-tested implementations. This is a pure Java SE 17 program requiring no Spring; copy it into `SessionCookieDemo.java`.

Goals:

- Session IDs are generated from **32 bytes of `SecureRandom`** and Base64URL-encoded (256 bits of entropy).
- The store keys entries solely by the SHA-256 digest of the session ID; raw session IDs are never printed to console.
- Before login, an anonymous session is not an authenticated session.
- After "successful authentication" (simulated by a call from trusted code), the app **discards the old ID and issues a new ID**.
- Idle timeout and absolute timeout are enforced server-side; logout deletes state.
- Cookie output demonstrates the `__Host-` prefix and protective attributes.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class SessionCookieDemo {
    record Session(String userId, Instant idleUntil, Instant absoluteUntil) {}

    static final class TestClock extends Clock {
        private Instant current;

        TestClock(Instant start) {
            current = start;
        }

        @Override public Instant instant() {
            return current;
        }
        @Override public ZoneId getZone() {
            return ZoneOffset.UTC;
        }
        @Override public Clock withZone(ZoneId zone) {
            return Clock.fixed(current, zone);
        }

        void advance(Duration duration) {
            current = current.plus(duration);
        }
    }

    static final class SessionStore {
        private static final Duration IDLE = Duration.ofMinutes(15);
        private static final Duration ABSOLUTE = Duration.ofHours(8);

        private final ConcurrentHashMap<String, Session> sessions =
                new ConcurrentHashMap<>();
        private final SecureRandom random = new SecureRandom();
        private final Clock clock;

        SessionStore(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        String anonymous() {
            return issue(null);
        }

        // Call ONLY AFTER credentials/IdP are genuinely verified.
        // This program does not verify passwords itself.
        String afterVerifiedLogin(String anonymousId, String userId) {
            if (userId == null || userId.isBlank() ||
                    anonymousId == null || anonymousId.isBlank()) {
                throw new IllegalArgumentException("Invalid login context");
            }

            Session old = sessions.remove(digest(anonymousId));
            Instant now = clock.instant();
            if (old == null || old.userId() != null ||
                    !now.isBefore(old.idleUntil()) ||
                    !now.isBefore(old.absoluteUntil())) {
                throw new SecurityException(
                        "Unknown or expired anonymous session");
            }
            return issue(userId); // new random ID; old ID invalid
        }

        boolean authenticated(String rawId) {
            if (rawId == null || rawId.isBlank()) {
                return false;
            }
            AtomicBoolean allowed = new AtomicBoolean(false);
            sessions.computeIfPresent(digest(rawId), (key, old) -> {
                Instant now = clock.instant();

                if (!now.isBefore(old.idleUntil()) ||
                        !now.isBefore(old.absoluteUntil())) {
                    return null;
                }
                if (old.userId() != null) {
                    allowed.set(true);
                }

                // Sliding idle timer, never extend absolute lifetime.
                return new Session(
                        old.userId(), now.plus(IDLE), old.absoluteUntil());
            });
            return allowed.get();
        }

        void logout(String rawId) {
            if (rawId != null) {
                sessions.remove(digest(rawId));
            }
        }

        private String issue(String userId) {
            while (true) {
                byte[] bytes = new byte[32];
                random.nextBytes(bytes);
                String raw = Base64.getUrlEncoder()
                        .withoutPadding().encodeToString(bytes);
                Instant now = clock.instant();

                Session data = new Session(
                        userId, now.plus(IDLE), now.plus(ABSOLUTE));

                if (sessions.putIfAbsent(digest(raw), data) == null) {
                    return raw;
                }
            }
        }

        private static String digest(String value) {
            try {
                byte[] hash = MessageDigest.getInstance("SHA-256")
                        .digest(value.getBytes(StandardCharsets.UTF_8));
                return HexFormat.of().formatHex(hash);
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    static String cookieHeader(String rawSessionId) {
        return "__Host-SESSION=" + rawSessionId
                + "; Path=/; Secure; HttpOnly; SameSite=Lax";
    }

    public static void main(String[] args) {
        TestClock clock = new TestClock(
                Instant.parse("2026-01-01T00:00:00Z"));
        SessionStore store = new SessionStore(clock);

        String anonymousId = store.anonymous();
        System.out.println("anonymousAuthenticated="
                + store.authenticated(anonymousId));

        String loggedInId = store.afterVerifiedLogin(
                anonymousId, "alice");
        System.out.println("oldIdAccepted="
                + store.authenticated(anonymousId));
        System.out.println("newIdAccepted="
                + store.authenticated(loggedInId));

        String cookie = cookieHeader(loggedInId);
        System.out.println("cookieHasSecure="
                + cookie.contains("; Secure"));
        System.out.println("cookieHasHttpOnly="
                + cookie.contains("; HttpOnly"));
        System.out.println("cookieHasLax="
                + cookie.contains("; SameSite=Lax"));

        clock.advance(Duration.ofMinutes(15));
        System.out.println("atIdleTimeoutAccepted="
                + store.authenticated(loggedInId));

        String anotherAnonymousId = store.anonymous();
        String anotherLoginId = store.afterVerifiedLogin(
                anotherAnonymousId, "alice");
        store.logout(anotherLoginId);
        System.out.println("afterLogoutAccepted="
                + store.authenticated(anotherLoginId));
    }
}
```

Run from the directory containing the file with JDK 17+:

```bash
javac SessionCookieDemo.java
java SessionCookieDemo
```

**Verified stdout:**

```text
anonymousAuthenticated=false
oldIdAccepted=false
newIdAccepted=true
cookieHasSecure=true
cookieHasHttpOnly=true
cookieHasLax=true
atIdleTimeoutAccepted=false
afterLogoutAccepted=false
```

### Exact analysis of demo limitations

1. `SecureRandom` produces unpredictable IDs; hashing session IDs in the map does not replace HTTPS or stop ID exposure in the browser. Raw IDs are still held and sent by the browser on every request.
2. `SessionStore` is a single-JVM simulation. Spring MVC production should use the Servlet container/Spring Security/Spring Session store and fixation strategy rather than a custom map like this.
3. `afterVerifiedLogin` **does not verify passwords**, because the program only exercises lifecycle transitions. In a real app, only code running **after authentication succeeds** may call rotation/markAuthenticated.
4. `cookieHeader` only **constructs a sample Set-Cookie string**; it does not serve HTTPS, emit HTTP responses, or prove browser acceptance. Integration tests with TLS and real browsers are required.
5. `authenticated()` extends the idle timeout on valid requests without extending `absoluteUntil`. Once expired, the map entry is removed.
6. `logout()` deletes the server-side session without emitting a cookie-clearing response; in Spring Security, logout filters/containers handle the rest per configuration.
7. The example models one server without CSRF, XSS, account roles, password reset, MFA, session registries, or multi-node revocation.
8. `TestClock` enables deterministic testing; production must use reliable clocks and monitor clock skew across nodes.
9. Checking attributes via `String.contains` only verifies the string **the program just built**; it is not a cookie parser or browser security test.

The key takeaway is that **after login, the old ID is unusable** and **after logout or TTL expiration, the server rejects remaining IDs**, even if the browser still holds the cookie.

## 13. OIDC/SSO, iframes, and cross-site cookies

Applications using `oauth2Login()` may receive authorization codes via top-level redirects from an IdP, using `state`/`nonce` and internal session/cookies to correlate callbacks. `SameSite` choices cannot be decided merely by the slogan "Strict is always safest".

| Flow | Needed cookie behavior | Approach |
| --- | --- | --- |
| Direct browser login at app | Host-only `Lax` or `Strict` usually fits | Enable CSRF, TLS, and rotation |
| OIDC top-level redirect GET callback | `Lax` is usually compatible with top-level cross-site safe navigation | Verify state/nonce/callback, test in practice |
| OIDC `form_post` callback | Cross-site POST may omit `Lax` cookies | Design suitable state/cookie flow, consider `SameSite=None; Secure` only for required cookies |
| App embedded in another site's iframe | Third-party cookie policies may block | Avoid third-party cookie reliance, evaluate CHIPS/Storage Access per browser |
| Cross-domain logout | Separate IdP cookie, RP cookie, and multiple sessions | RP-initiated/back-channel logout if supported; never assume automatic cascading logout |

Be careful with `SameSite=None` cookies: modern browsers increasingly restrict third-party cookies, and `Secure` is mandatory; cookies may **still fail** inside iframes even with valid attributes. Never widen `Domain=.example.org` to "fix SSO" if that exposes session cookies to unrelated applications.

**SSO logout differs from local logout:** invalidating App A's `HttpSession` does not necessarily log out of the IdP or App B. Conversely, deleting the IdP cookie does not automatically invalidate every Relying Party's local app sessions. Integrate official IdP-aligned logout flows.

## 14. Bearer JWTs, SPAs, and browser sessions differ

Two models are frequently confused:

### Model A — server session + HttpOnly cookie

- Browser receives a session ID cookie and attaches it automatically per domain/path/SameSite rules.
- Server stores `Authentication`/SecurityContext and can invalidate sessions immediately.
- When using cookie authentication, CSRF protection must be taken seriously.
- `HttpOnly` cookies reduce the risk of JS reading raw IDs, yet XSS can still perform actions inside the session.

### Model B — stateless API + Authorization bearer token

- Client sends `Authorization: Bearer ...` per request; server validates JWT or opaque tokens per policy.
- Access tokens typically do not live in `HttpSession`; revocation depends on TTL/introspection/denylists.
- If an SPA stores access tokens in `localStorage`, XSS can read raw tokens directly. Moving tokens into an `HttpOnly` cookie makes browsers auto-attach them and changes the CSRF threat model.
- Do not configure `sessionCreationPolicy(STATELESS)` for browser form login while expecting `HttpSession` to retain logins across requests.
- Enforce HTTPS and never log bearer tokens in either architecture.

Do not confuse Spring MVC `HttpSecurity` with WebFlux `ServerHttpSecurity`/`WebSession`. Spring Boot configures reactive cookies under a separate namespace such as `server.reactive.session.cookie.*`; the earlier `WebSecurityConfig` code **does not apply verbatim to WebFlux**.

## 15. Anomaly assessment and responding to suspected session theft

Even with HTTPS, cookie flags, and CSRF configured properly, attackers can compromise browser profiles, extract tokens from past leaked logs, or exploit XSS. Applications should have an active response path:

1. **Receive signals:** session appears on a new device, abrupt geography/IP shift, repeated MFA failures, abnormal activity rates, token reused after revocation.
2. **Assess risk:** do not treat an IP or User-Agent change alone as definitive proof of compromise; mobile networks, VPNs, carrier NAT, and browser updates alter these signals.
3. **Temporary containment:** require re-auth/step-up for high-risk actions, temporarily narrow permissions, or block the session per policy.
4. **Revoke:** invalidate the suspicious session and related sessions; if credential compromise is plausible, force password change/credential rotation and revoke refresh/remember-me tokens.
5. **Keep safe audits:** log event time, access-controlled account ID, session correlation ID (**never raw session secrets**), action, and policy decision.
6. **Notify users:** state anomalous activity and safe recovery steps, without putting session IDs or verification codes into notification emails.
7. **Prevent recurrence:** fix the leak root cause across logs, XSS, proxy config, cookie domain, or TLS; flipping a cookie flag alone does not remediate already-leaked secrets.

**Binding sessions to IP/UA** can serve as a fraud-detection signal, though hard-failing every IP change locks out legitimate users and can still be spoofed. Never treat IP addresses as standalone authentication factors.

## 16. Common configuration mistakes and fixes

**1. Cookies missing `Secure` in production.** Browsers may send IDs over HTTP, especially on misdirected redirects or internal links. Set `secure:true`, enforce HTTPS, and inspect cookies past ingress.

**2. Setting `HttpOnly=false` on the session cookie so SPAs can read it.** JS can grab the ID directly if XSS occurs. Keep session cookies `HttpOnly`; if the SPA needs to read a CSRF token, configure a **dedicated CSRF cookie** properly.

**3. Setting `SameSite=None` without `Secure`.** Modern browsers may reject it. When cross-site is truly needed, use `None; Secure` with CSRF/state/nonce; never relax all cookies indiscriminately.

**4. Assuming `SameSite=Lax` stops all CSRF.** It still allows certain top-level GETs, and subdomains can be same-site. Keep CSRF tokens enabled, avoid state-changing GETs, and check Origin/Fetch Metadata where appropriate.

**5. Using `Domain=.example.org` for `app.example.org` auth cookies.** Sibling subdomains share/overwrite broad cookies, increasing risk. Prefer host-only and `__Host-` prefix.

**6. Naming `__Host-SESSION` with cookie Path `/app`.** Browsers may reject the cookie. `Path=/`, `Secure`, and no `Domain` are mandatory.

**7. HTTPS only for `/login`.** Cookies leak on other requests over HTTP; enforce HTTPS app-wide with HSTS.

**8. Enabling `includeSubDomains`/HSTS preload before legacy subdomains support HTTPS.** Can make secondary services unreachable. Audit hostnames/subdomains first.

**9. App behind proxy receives HTTP and drops `Secure` or skips HSTS.** Force `secure` cookies explicitly, configure trusted proxies properly, and inspect final Internet-facing responses.

**10. Trusting any client-sent `X-Forwarded-Proto` or `Forwarded`.** Attackers spoof scheme/host; the edge must strip/rewrite headers and restrict backend connection sources.

**11. Not rotating session ID after login.** Session fixation remains possible. Use `changeSessionId()`/framework protection and test before–after login.

**12. Only deleting the browser cookie on logout.** Copied IDs remain valid on the server. Invalidate server-side.

**13. Setting only cookie `Max-Age=15m` without a server timeout.** Sessions stay alive in the backend; browser and server timeouts diverge.

**14. Unlimited sliding expiration.** Attackers keep sending requests to keep sessions alive forever. Enforce absolute max age and step-up for sensitive actions.

**15. Cookies appearing in access logs or APM traces.** Anyone reading logs can impersonate users. Redact `Cookie`, `Set-Cookie`, `Authorization`, and URL secrets.

**16. Not checking disabled accounts after login.** Cached `Authentication` snapshots in sessions can remain valid. Invalidate sessions and revalidate privileges when needed.

**17. Allowing `;jsessionid` session identifiers in URLs.** Leaks via history/Referer/logs. Enforce cookie-only tracking and test with cookies disabled.

**18. Reading `HttpOnly` cookies in JS to "check login state".** Unnecessary and impossible as intended. Call a server-provided auth-status endpoint (minimal metadata only), avoiding exposing session secrets.

**19. Confusing cookie `SameSite` with CORS origins.** Two different mechanisms; cross-site and cross-origin do not match identically. Test exact hosts, schemes, browsers, and HTTP methods.

**20. Storing sessions only in one pod's RAM across multiple replicas.** Sporadic login/logout failures and inconsistent revocation. Use Spring Session or an appropriate shared store.

**21. Calling `csrf.disable()` because the frontend is an SPA.** If browsers automatically attach session cookies, state-changing requests carry CSRF risk. Disable only after verifying the architecture is truly stateless with no ambient credentials.

**22. Using CSP while still rendering unsanitized HTML.** CSP is supplemental defense; XSS bugs can still bypass depending on policy/gadgets. Fix context-aware output encoding and sanitization.

## 17. Testing matrix across browsers, proxies, and backend

| Test | How to verify | Expected outcome |
| --- | --- | --- |
| HTTP access to protected page | Request `http://app.example.org` | Redirects to HTTPS before session; no auth cookie issued over HTTP |
| HTTPS response | Browser Network/`curl -I` | Valid TLS, HSTS per policy |
| `Set-Cookie` after login | Browser devtools | Correct `Secure`, `HttpOnly`, `SameSite`, `Path=/`, no `Domain` if host-only |
| `__Host-` prefix | Inspect response/browser cookie store | Accepted when valid; not broken by wrong path/domain |
| Raw cookie in JS | `document.cookie` in test environment | `HttpOnly` session cookie not visible |
| Anonymous -> authenticated | Capture cookie IDs pre/post-login in protected test env | ID changes; old ID loses access |
| Old cookie after logout | Replay old ID from HTTP test client | 401/login redirect or rejected per endpoint |
| Idle timeout | Clock simulation/integration test | Session expires after inactivity |
| Absolute timeout | Keep session continuously active | Expires once absolute TTL hits per policy |
| Missing/invalid CSRF token | POST session-based endpoint | Rejected per policy, typically 403 |
| Cross-site form POST | Browser test from another domain | Unauthorized change blocked |
| XSS payload | Test HTML/JS/DOM contexts | Malicious script does not execute |
| Wrong tenant/role | Authenticated user lacking permission | 403, no data leaked |
| Reverse proxy spoof | Send forged `X-Forwarded-*` from Internet | Edge sanitizes; safe redirects/issuer/host preserved |
| HSTS `includeSubDomains` | Test all affected subdomains | Does not break non-HTTPS-ready services |
| OIDC GET callback login | Real redirect via IdP | Valid `state`, `nonce`, and session correlation |
| OIDC `form_post` callback | Cross-site POST via browser | Cookie/state flow works without disabling security controls |
| Password reset / disable account | User holding multiple sessions | Required sessions revoked in proper scope |
| Multi-node | Login pod A, request pod B, logout pod C | Shared store and consistent revocation |
| Log/trace scan | Inspect sanitized logs | No session cookies, JWTs, passwords, or refresh tokens |
| Log out all devices | Sign in with 2–3 clients | All target IDs rejected |
| Cookie deletion | Log out in browser | Cookie cleared/expired per matching Path/Domain; server session also invalid |
| Separate API bearer & browser session | Compare security chains | Cookies and bearers create no bypasses or stray sessions |
| Existing stolen session | Replay stolen ID in controlled test | Detected/revoked and step-up enforced as designed |

Do not only test `200` on a valid request. Negative tests (replay, CSRF, URL session IDs, cookie attributes, cross-replica logout) are essential to prove security.

### How to test without exposing secret IDs

Automated tests can read session IDs to compare before/after, but must keep them strictly in test-runner memory and never print them to CI logs or public videos/screenshots. In reports, log `oldIdChanged=true` or an irreversible/short-lived hash instead of raw session IDs.

Use `curl` to inspect headers; use **real browsers** to verify cookie prefixes, `SameSite`, redirects, iframes, and HSTS because those rules are enforced by browsers, not just HTTP test clients.

## 18. Concise implementation checklist

1. All authentication/session traffic uses HTTPS; modern TLS, valid certificates, HTTP redirects, and HSTS verified at the edge?
2. Session cookies carry `Secure`, `HttpOnly`, and `SameSite=Lax/Strict` per use case; host-only, proper `Path`, and not shared with sibling subdomains?
3. If using `__Host-`, does the cookie have **Secure + Path=/ + no Domain** and do browsers accept it?
4. Spring Boot sets `server.servlet.session.cookie.*` properly for Servlet; proxy headers trusted only from controlled ingress?
5. Session IDs generated by CSPRNG and rotated after login/privilege change?
6. URL session tracking disabled and `Cookie`/`Set-Cookie`/`Authorization` excluded from logs?
7. CSRF remains enabled for browser sessions; forms/login/logout/POST mutations use valid tokens and policies?
8. XSS prevented via encoding/sanitization/CSP; untrusted third-party scripts barred from running same-origin?
9. Idle timeout and absolute timeout separated properly; logout invalidates server-side?
10. Password changes, account disablement, privilege changes, and hijacking incidents revoke **all relevant sessions** in the shared store?
11. Multi-instance and WebSocket deployments handle session consistency/revocation?
12. Sensitive actions require step-up/re-authentication and ownership/tenant authorization?
13. SSO/OIDC callbacks, browser cross-site flows, and iframes tested with realistic `SameSite` without over-broadening domains/cookies?
14. Test matrix covers old ID after login, replay after logout, wrong CSRF, browser cookie flags, and proxy spoofing?
15. Logs/metrics support investigation without keeping raw secrets; session revocation and incident notification runbooks ready?

### Official references

- Spring Security 6.5 — Session Management and Session Fixation: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Security HTTP Response Headers / HSTS: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html
- Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Boot 3.5 — Servlet Web Applications / SameSite Cookies: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Session — Documentation: https://docs.spring.io/spring-session/reference/
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Transport Layer Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html
- OWASP — Cross Site Scripting Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- OWASP — Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Conclusion:** only when **HTTPS/TLS is sound**, cookies are safely scoped, session IDs are **rotated after login** and **revoked server-side**, CSRF/XSS/authorization are enforced, and multi-node deployments share consistent session/revocation state does an application meaningfully reduce session theft and abuse risks. Cookie flags matter, yet they cannot substitute for end-to-end session security from browser to backend.
