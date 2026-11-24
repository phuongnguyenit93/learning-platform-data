# Cookies, HTTPS, and Identity Configuration Behind a Reverse Proxy

## 1. The Problem: Users See HTTPS, but Spring Boot Receives HTTP

In real deployments, a Spring Boot/Spring Security application usually runs **behind a reverse proxy, load balancer, API gateway, or Kubernetes ingress**. The browser calls a public HTTPS address, while the proxy may perform *TLS termination* and forward plain HTTP to the internal backend.

~~~text
Browser
  GET https://login.example.test/login
  Cookie: __Host-SESSION=...
          |
          | HTTPS/TLS, public host login.example.test:443
          v
[Ingress / Reverse proxy / Load balancer]
          |
          | HTTP (protected internal network) or re-encrypted HTTPS
          | Host: app-auth:8080
          | Forwarded / X-Forwarded-* set by trusted proxy
          v
[Spring Boot :8080]
  request.scheme     may be http
  request.serverName may be app-auth
  request.isSecure()  may be false if proxy info is not handled
          |
          v
[Spring Security / Servlet session / OAuth2 Login / OIDC]
~~~

If the application does not know its **trusted public origin** or blindly trusts every header arriving from the network, several bugs can occur:

- Redirecting from `https://login.example.test` to `http://app-auth:8080` or generating the wrong OAuth2 callback URL.
- Session cookies missing `Secure` because the backend thinks the request is HTTP.
- The HSTS header not appearing as expected because the framework does not recognize the public request as HTTPS.
- OIDC `redirect_uri` not matching the URI registered with the IdP, causing `redirect_uri_mismatch` or state correlation errors.
- Password-reset/magic-link emails using a hostname influenced by an attacker.
- Spoofed `X-Forwarded-For` causing rate limiters/audits to record the wrong IP address, potentially bypassing login attempt limits.
- Cookies having inappropriate `Domain`, `Path`, or `SameSite`, causing session loss after SSO, CSRF false positives, or cookies being sent to another subdomain.

**Goal:** browsers always interact with a managed **HTTPS public origin**; the reverse proxy enforces the trust boundary; Spring Security and cookies/sessions/OIDC operate consistently with that origin.

This lesson focuses on **authentication operations**. Proxy configuration, Spring Boot, and security filters must be treated as one system, rather than changing a single `server.forward-headers-strategy` line and assuming the job is done.

## 2. Distinguishing Public Origin, Backend Address, and Account Identity

Key concepts:

| Concept | Example | Role |
|---|---|---|
| **Public origin** | `https://login.example.test` | Scheme + host + port that browsers and IdPs are allowed to use. |
| **External URL / callback** | `https://login.example.test/login/oauth2/code/corp` | URI called back by the IdP/OP or redirected to by the browser; must match registration. |
| **Backend destination** | `http://app-auth:8080` | Address the proxy connects to for the service; must not be exposed as the app origin. |
| **Request Host** | `Host: login.example.test` | Host in the HTTP request; still client-supplied data, so trust must be verified. |
| **Forwarded authority/scheme** | `X-Forwarded-Host`, `X-Forwarded-Proto` | Metadata constructed by a trusted proxy, not user authentication. |
| **Identity issuer** | `https://idp.example.test/realms/corp` | Identity issuer in ID Tokens/JWTs; not synonymous with the application's public origin. |
| **User identity** | `(iss, sub)` or internal user ID | Account identity; must never be inferred from IP, Host, or forwarded headers. |
| **Session identity** | Random session ID in cookie | Session lookup key; does not by itself prove MFA/roles are still valid. |

**Do not confuse `Host` or client IP with user identity.** `X-Forwarded-User`, `X-Remote-User`, or headers containing an email may only be trusted if there is **a genuine authenticating gateway** that strips client-supplied headers, secures the upstream connection, and enforces a verified identity contract. A regular reverse proxy only carries network routing metadata—it is **not an Identity Provider**.

### Two Threat Diagrams

~~~text
Wrong:
Internet user -> Host: attacker.test
              -> X-Forwarded-Proto: https
              -> X-Forwarded-Host: attacker.test
              -> Spring blindly trusts forwarded fields
              -> password reset URL, OAuth2 redirect or callback host is changed

Right:
Internet user -> trusted edge rejects unknown Host
              -> strips inbound Forwarded and X-Forwarded-*
              -> sets fixed/validated public scheme and host
              -> only private proxy-to-backend connection can reach app
              -> Spring consumes trusted metadata
              -> security-critical URLs constrained by canonical origin
~~~

Multiple domains/tenants can be supported, but each corresponding hostname must be **verified and placed in an authoritative allowlist/mapping**, rather than taking any `Host`/`X-Forwarded-Host` directly from the client.

## 3. TLS Termination: External HTTPS Does Not Mean Every Hop Is Encrypted

In the TLS-at-proxy model:

~~~text
Browser --TLS--> Edge --HTTP--> Backend
~~~

A `Secure` cookie protects **the browser sending the cookie over HTTPS** to the edge; it **does not encrypt** traffic between the edge and the backend if the internal hop is HTTP. If the internal network is considered untrusted, multi-tenant, shared, or crosses unprotected zones, use **re-encrypted HTTPS**, mTLS, or an approved network mechanism rather than treating a "private subnet" as an absolute guarantee.

Operational requirements:

1. Expose only HTTPS ports publicly for login/callback pages and credential-bearing APIs; restrict/enforce HTTP-to-HTTPS redirects at the edge.
2. Ensure TLS certificates match the hostname, are renewed and monitored; use TLS versions/ciphers per organizational policy.
3. Never allow Internet clients to connect directly to `app-auth:8080` or sensitive admin/actuator ports.
4. Restrict which network sources can send requests to the backend: only ingress/gateway or trusted service identities.
5. All `Forwarded`, `X-Forwarded-*`, and identity headers must be **reset at the trust boundary**.
6. For multi-hop proxy/mesh paths, understand where TLS terminates and which proxy owns the original metadata.
7. Check proxy request/response logs so Authorization headers, cookies, query tokens, and form bodies are not recorded.

**Do not assume the application itself must bind port 443** when HTTPS terminates at the gateway. Spring Boot can still listen on internal HTTP as long as the network path is protected and it receives the external scheme after verifying the proxy source.

## 4. Forwarded Headers to Recognize

**RFC 7239 `Forwarded`** is the standard format:

~~~http
Forwarded: for=192.0.2.20;proto=https;host=login.example.test
~~~

Common de facto headers:

~~~http
X-Forwarded-For: 192.0.2.20
X-Forwarded-Proto: https
X-Forwarded-Host: login.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /auth
~~~

Meaning:

- `for` / `X-Forwarded-For`: describes the client or chain of intermediary network hops. **Does not prove user identity**.
- `proto` / `X-Forwarded-Proto`: scheme of the request before the proxy, usually `https`.
- `host` / `X-Forwarded-Host`: public host controlled by the proxy.
- `X-Forwarded-Port`: public port, which may differ from backend `8080`.
- `X-Forwarded-Prefix`: external path prefix if the gateway rewrites URIs. Not always needed.

For example, a browser calls `https://login.example.test/auth/login`, the gateway strips `/auth`, and forwards `/login` to the backend. If the app constructs a redirect to `/login/oauth2/code/corp` without the prefix, the callback will miss `/auth`. However, **trusting an attacker-supplied prefix** can lead to redirect/path poisoning; use it only when normalized by the proxy and backed by an explicit app path contract.

### Do Not Leave Two Conflicting Header Families

Spring Framework can support both `Forwarded` and `X-Forwarded-*`. If the edge strips `X-Forwarded-Host` but forgets `Forwarded: host=attacker.test`, another component may read the other family and generate the wrong URL.

**The trust boundary must strip/overwrite both header families**, even if the product uses only one. Check for uncommon/legacy headers, duplicate headers, comma-separated multi-values, and how CDNs/LBs merge headers. Do not try to patch around this by "picking whichever header looks reasonable" in individual controllers.

## 5. How Spring Boot Handles Forwarded Headers

In Spring Boot 3.x, the property is:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Meaningful modes:

| Value | Behavior | When to Consider |
|---|---|---|
| `none` | Do not use forwarded headers as request origin information. | Backend is directly public or there is no trusted proxy metadata. |
| `native` | Use container/server support such as Tomcat's `RemoteIpValve`. | The proxy sends standard headers supported by the native server; trusted proxies must be restricted. |
| `framework` | Use Spring Framework's `ForwardedHeaderFilter` (Servlet) or `ForwardedHeaderTransformer` (reactive). | Need framework-level handling of forwarded host/proto/port/prefix. |

**`framework` does not verify that the header sender is a trusted proxy.** If clients can reach the backend directly or the edge does not strip client-supplied headers, enabling `framework` turns self-asserted client data into server-trusted scheme/host values.

With `native`, the container has its own proxy trust configuration and parsing rules. With Tomcat, inspect `server.tomcat.remoteip.*` properties, especially the internal/trusted proxies list. Never configure trusting all proxies just to make a test work; restrict it to the actual topology.

### Tip on Tomcat Context-Root Redirects

Per the Spring Boot embedded server docs, when TLS terminates at a proxy and Tomcat is used, there are cases where you should set:

~~~yaml
server:
  tomcat:
    redirect-context-root: false
~~~

This allows the forwarded proto to be processed before context-root redirects occur. Do not change this property blindly if you are not using Tomcat or the app does not exhibit context-root redirects; verify the request path and the order of valves/filters.

### Do Not Double-Register Filters

If you already use `server.forward-headers-strategy=framework`, you usually **do not need** to register a second `ForwardedHeaderFilter` bean/filter registration manually. If both native and framework process the same headers across multiple layers, results can become unpredictable. Pick one clear strategy and test the resulting request scheme/host/port and real redirects.

## 6. Trust Boundaries Matter More Than Properties in application.yml

Spring Framework documentation warns that there is no safe way for an application to know whether `Forwarded`/`X-Forwarded-*` were genuinely added by a proxy or sent by a client if the network boundary is uncontrolled. The root controls are:

1. **The edge gateway strips** inbound forwarded headers sent from the Internet by clients.
2. **The edge rewrites** trusted origin/IP values after validating the hostname and TLS listener.
3. Every intermediate proxy only accepts and forwards according to the topology contract, never letting clients prepend arbitrary values.
4. The backend opens network ingress only to authorized proxies.
5. The application still **constrains security-critical absolute URLs** against a canonical allowlist rather than relying solely on forwarded host headers.

A simple policy for a **single-domain login application**:

~~~text
publicScheme = https
publicHost   = login.example.test
publicPort   = 443

Edge:
  reject unknown Host/SNI
  X-Forwarded-Proto := https
  X-Forwarded-Host  := login.example.test
  X-Forwarded-Port  := 443
  Forwarded         := remove or trusted normalized value

Backend:
  reachable only from ingress
  Spring reconstructs external origin from sanitized headers
  security links generated from canonical configured origin
~~~

In a multi-tenant environment with custom domains, replace the fixed `publicHost` with a verified tenant-to-host mapping, not blind passthrough.

**Note:** `ForwardedHeaderFilter` can be used in `removeOnly` mode when you want to discard untrusted metadata instead of using it to construct requests, per Spring Framework docs. You do not need to write a custom regex Servlet filter just to parse `Forwarded`.

## 7. Nginx Ingress Example for a Public Login Origin

The following illustration assumes **Nginx directly receives HTTPS from the browser**, acts as the first trust boundary, serves a single host `login.example.test`, and proxies to backend internal hostname `app-auth`.

~~~nginx
# Architecture illustration; adjust certificates, limits, and networking
# for your deployment environment; do not copy verbatim to production.
server {
    listen 443 ssl;
    server_name login.example.test;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        # Single canonical external host:
        proxy_set_header Host              login.example.test;
        proxy_set_header X-Forwarded-Host  login.example.test;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port  443;

        # This Nginx is the first trusted edge:
        proxy_set_header X-Forwarded-For   $remote_addr;

        # Do not pass client-supplied Forwarded or prefix:
        proxy_set_header Forwarded          "";
        proxy_set_header X-Forwarded-Prefix "";

        proxy_pass http://app-auth:8080;
    }
}
~~~

This **is not a complete Nginx config**: it still needs default host/SNI rejection, HTTP→HTTPS redirect policy, TLS hardening, rate limits, request-size limits, log redaction, timeout/upstream health settings, and firewall controls. Nginx must have a default server block that prevents unknown `Host` headers from reaching the application. In topologies with a CDN/LB in front of Nginx, `$remote_addr` may be the CDN's IP rather than the browser's; configure `real_ip`/the trusted proxy chain properly and select the normalized client IP.

**Never use `proxy_set_header Host $http_host` or pass through `X-Forwarded-Host $http_x_forwarded_host`** at the edge before validation and allowlisting. They can hold client-supplied values. Even `$host` must be placed inside a server block with explicit unknown-host rejection.

If a deployment chooses RFC `Forwarded` instead of `X-Forwarded-*`, generate only a normalized value at the edge. Ensure intermediaries do not produce two conflicting sources of truth.

## 8. Illustrative Spring Boot Servlet Configuration

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
  servlet:
    session:
      timeout: 30m
      tracking-modes: cookie
      cookie:
        name: "__Host-JSESSIONID"
        secure: true
        http-only: true
        same-site: lax
        path: "/"

spring:
  application:
    name: login-portal
~~~

Explanation:

- `port: 8080` is the internal backend listener; it does not mean the public site is HTTP.
- `forward-headers-strategy: framework` reconstructs request scheme/host/port **after the proxy has sanitized headers**.
- `session.timeout` is typically an idle timeout; **it does not automatically enforce an absolute session lifetime**.
- `tracking-modes: cookie` avoids passing session IDs in URLs if the container supports rewriting; test with your actual Servlet container version.
- Cookie `__Host-JSESSIONID` has `Secure; Path=/` and **no Domain**; this satisfies the `__Host-` prefix rules in supporting browsers.
- `HttpOnly` prevents JS from reading the cookie directly, but **does not block CSRF or XSS acting on the user's behalf**.
- `SameSite=Lax` is a suitable example for many top-level GET web-login redirects; it is not automatically right for every OIDC/SAML flow.

**Example scope:** the properties above apply primarily to the embedded Servlet session cookie. If using **Spring Session** or a custom `CookieSerializer`, cookie emission may differ; see the dedicated section below. If the app runs behind a proxy path prefix `/auth` or multiple web apps share the same host, `__Host-...; Path=/` rules can cause cookie name collisions: design isolation with distinct hosts or names.

Do not enable these properties on a plain HTTP localhost environment and assume browsers will accept `Secure` cookies across all browsers; keep production and local profiles distinct.

## 9. Understanding `Set-Cookie` and the Effect of Each Attribute

Example post-login response:

~~~http
HTTP/1.1 302 Found
Location: /dashboard
Set-Cookie: __Host-JSESSIONID=s7R4X8p9; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

The cookie value above is a **dummy example**, not a real session ID.

| Attribute | What It Protects or Affects | What It Does Not Replace |
|---|---|---|
| `Secure` | Browser sends the cookie only over HTTPS (with localhost behavior exceptions). | Does not encrypt HTTP between proxy and backend; does not block JS without HttpOnly. |
| `HttpOnly` | `document.cookie` cannot read/write the cookie directly in supporting browsers. | Does not stop CSRF, authenticated XSS requests, or server-side session theft. |
| `SameSite=Strict` | Reduces cookie sending in many cross-site contexts. | Can break legitimate navigation/OIDC callbacks; does not replace all CSRF protection. |
| `SameSite=Lax` | Sends cookie in same-site and certain safe top-level cross-site navigations. | Does not guarantee the cookie is sent on cross-site POST callbacks/`form_post`. |
| `SameSite=None` | Allows cross-site cookie contexts in supporting browsers; requires `Secure`. | Does not bypass third-party-cookie blocking or browser privacy policies. |
| `Domain` | Allows the cookie for the specified host and valid subdomains. | Is not a boundary against XSS on sibling subdomains; widens scope. |
| `Path` | Sends cookie only for matching request paths. | **Not** a security isolation control preventing code on another path from reading/writing it. |
| `Max-Age`/`Expires` | Controls cookie persistence in the browser. | Does not revoke the server-side session or enforce an absolute session timeout. |
| `Partitioned` | Scopes cookies under partitioned storage in supporting browsers. | Not a universal SSO solution; requires `Secure` and compatibility testing. |

If `Domain` is omitted, browsers create a **host-only cookie**, which is usually more restrictive than `Domain=example.test`. For a dedicated login service, avoid sharing the session cookie across all of `*.example.test` unless the architecture and threat model genuinely require it.

**Never store tokens/passwords in a differently named cookie that acts like a session without controls.** A cookie value carrying a session identifier is still a credential; reverse-proxy access logs and error telemetry must never record raw `Cookie`/`Set-Cookie` headers.

## 10. `__Host-` and `__Secure-` Cookie Prefixes

MDN describes browser-supported cookie prefixes that enforce stricter binding:

- `__Secure-name`: must be set over HTTPS and include `Secure`.
- `__Host-name`: must be set over HTTPS, include `Secure`, `Path=/`, and **have no `Domain`**. This binds the cookie strictly to the issuing host across the root path.
- Newer prefixes such as `__Http-` or `__Host-Http-` add an `HttpOnly` requirement in supporting browsers; verify compatibility if chosen.

Valid example:

~~~http
Set-Cookie: __Host-SESSION=opaque123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**Invalid** examples:

~~~http
Set-Cookie: __Host-SESSION=opaque123; Domain=example.test; Path=/; Secure
Set-Cookie: __Host-SESSION=opaque123; Path=/auth; Secure
Set-Cookie: __Host-SESSION=opaque123; Path=/; HttpOnly
~~~

The three invalid lines fail respectively because of `Domain`, `Path` not equal to `/`, and missing `Secure`. Browsers may reject the cookie outright instead of "fixing it up". When an application logs users out repeatedly after deployment, check DevTools to see whether `Set-Cookie` is being rejected due to prefix rules.

**Do not use `__Host-` when `Path=/auth` or `Domain=...` is mandatory.** Either pick a different cookie name with an explicitly reviewed scope, or isolate the authentication origin onto its own hostname so the prefix rules can be applied safely.

## 11. Spring Session: Cookie Serializer and Multiple Replicas

With **Spring Session Redis/JDBC**, the session ID cookie is typically issued and managed by Spring Session. Depending on configuration, the default cookie name may be `SESSION` rather than servlet `JSESSIONID`. When using Spring Session, setting only `server.servlet.session.cookie.*` may **fail to produce the expected header** if Spring Session's serializer controls the cookie.

Example custom serializer in Spring Boot 3.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("__Host-SESSION");
        serializer.setCookiePath("/");
        serializer.setUseSecureCookie(true);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setSameSite("Lax");
        // Do not call setDomainName: keep the cookie host-only.
        return serializer;
    }
}
~~~

This is **integration code** requiring Spring Session dependencies/configuration, not a standalone Java program. Verify the Spring Session version, any other custom `CookieSerializer` beans, and the network environment. When using `__Host-SESSION`, browsers only accept the cookie if the response arrives over HTTPS with exact `Secure`, `Path=/`, and no `Domain`.

With multiple replicas:

- Use a shared session repository or session affinity as architected, though session affinity does not replace global revocation.
- Ensure every replica shares **the same cookie name, serializer policy, session store, and context path logic**.
- Logout cookies must clear the exact **name, Path, and Domain** used earlier; otherwise the browser retains the old cookie.
- Changing the cookie name abruptly can prevent old sessions from being found; plan migration and rollback carefully.
- Session store TTL, idle timeout, absolute expiry, and account/security epoch checks must be designed separately.

**A properly flagged cookie does not guarantee the server-side session cannot be hijacked or remain valid after a password reset.** You still need session rotation, logout/revocation, and authorization checks.

## 12. SameSite and OAuth2/OIDC/SAML Callbacks

A common issue: a user starts login at `https://login.example.test`, the application stores the OAuth2 authorization request and `state` in the HTTP session, and then redirects the browser to the IdP. When the IdP redirects back to the callback, the browser must send the matching session cookie so Spring Security can correlate the result.

~~~text
GET /oauth2/authorization/corp
  -> create state/nonce and store authorization request
  -> browser redirects to https://idp.example.test

IdP:
  -> authenticates user
  -> redirects back to https://login.example.test/login/oauth2/code/corp
       ?code=...&state=...

Browser:
  -> sends appropriate session cookie?
Spring OAuth2LoginAuthenticationFilter:
  -> finds matching authorization request/state
  -> validates flow / exchanges code
  -> creates local Authentication/session
~~~

**`SameSite=Lax`** usually works for callbacks using **top-level cross-site GET navigation**. However, if the flow uses `response_mode=form_post` or a SAML POST binding from the IdP, a `Lax` cookie may not be sent on the cross-site POST, causing state/relay-state errors or lost sessions. `SameSite=Strict` is usually even more restrictive.

If forced to use `SameSite=None; Secure` for specific federation cookies, evaluate:

1. Scope it only to the cookies that need cross-site behavior; do not widen all cookies automatically.
2. Ensure CSRF tokens/Origin checks and strong state/nonce protection cover the callback.
3. Check whether browser third-party cookie blocking policies still break the flow.
4. Verify whether the IdP actually uses GET redirects, form POSTs, iframes, or hybrid flows.
5. Evaluate cookie partitioning/first-party contexts and appropriate fallbacks.
6. Keep session cookies `HttpOnly` regardless of response mode; never lower security because of SSO errors.

**Do not disable CSRF application-wide to fix a SameSite error.** OAuth2 `state` and POST form CSRF tokens are related mechanisms with different purposes; understand the actual flow.

## 13. OIDC Redirect URIs Must Be Exact Public HTTPS URLs

Spring Security OAuth2 Login typically uses the redirect URI template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Example:

~~~text
External URL: https://login.example.test
Registration ID: corp
Redirect URI: https://login.example.test/login/oauth2/code/corp
~~~

IdPs usually require the registered URI to **match exactly** the redirect URI sent during the authorization code flow. If Spring builds `http://app-auth:8080/login/oauth2/code/corp` or `http://login.example.test/...`, login may be rejected immediately at the IdP.

This YAML snippet shows only the callback path; **it is not a complete client registration**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

A real application also needs client ID, client secret/appropriate client authentication mechanism, provider issuer/authorization/token endpoints, scopes, state, nonce, and PKCE according to client type and policy.

### Two Strategies for Forming the Public Base URL

**Approach A – trusted forwarded origin:** configure the edge to normalize headers, have Boot process forwarded metadata, and let Spring build `{baseUrl}` from the request. Suits solid topologies needing multiple hosts/prefixes.

**Approach B – configured canonical origin:** for a login service with a single hostname, use a statically configured public origin/redirect URI or allowlist. This reduces host-header poisoning risks for sensitive links.

The two approaches can complement each other. Even when `server.forward-headers-strategy=framework` is active, **password-reset links, email verification links, OAuth2 callbacks, and post-login redirects** should still enforce a verified origin policy instead of concatenating an arbitrary client header.

### Issuer Is Not Callback Origin

- Application public origin: `https://login.example.test`.
- IdP issuer: `https://idp.example.test/realms/corp`.
- API audience: resource server identifier per contract.

Do not replace the JWT issuer with the application's public host just because you fixed the proxy scheme. A resource server must validate issuer/signature/audience/expiry against the trusted IdP/AS. The `redirect_uri` chosen for the OIDC client is distinct from the `issuer-uri` for token validation.

## 14. Host Header Injection and Credential-Bearing Links

A severe vulnerability is building email links or redirects from an untrusted request host:

~~~java
// Pattern NOT to use for security-critical links:
String resetUrl = request.getScheme() + "://"
        + request.getServerName()
        + "/recovery/reset?token=" + rawToken;
~~~

If `getServerName()` is derived from an uncontrolled `Host` or forwarded host header, an attacker can make the email carry a real token while pointing to the attacker's domain. A safer approach is a **statically configured public origin** or a verified tenant-to-host mapping.

Example Spring component:

~~~java
import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PublicIdentityUrls {
    private final URI publicOrigin;

    public PublicIdentityUrls(
            @Value("https://login.example.test") String publicOriginText) {
        this.publicOrigin = URI.create(publicOriginText);
    }

    public URI recoveryPage() {
        return publicOrigin.resolve("/recovery/reset");
    }

    public URI oauth2Callback() {
        return publicOrigin.resolve("/login/oauth2/code/corp");
    }
}
~~~

This is an **integration snippet** that intentionally uses a constant origin for the example; production can externalize the value with startup validation. If a different OAuth2 registration redirect URI template is used, keep it synchronized with this policy.

**Never pass raw recovery tokens through an open redirect** or arbitrary `returnTo`. Never let a URL redirect to an attacker domain via a query parameter like `next=https://evil.test`. Validate against an exact origin and required path allowlist; prefer relative redirects when possible.

Even HTTPS does not prevent tokens from leaking into reverse-proxy access logs if a token appears in the request query string. Apply log redaction for recovery endpoints alongside dedicated lifetime/single-use policies.

## 15. HSTS, HTTPS Redirects, and Response Security Headers

**HTTP Strict Transport Security (HSTS)** instructs browsers to prefer HTTPS for the recorded host. Example:

~~~http
Strict-Transport-Security: max-age=31536000
~~~

Once all subdomains have been thoroughly evaluated:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Be careful with `includeSubDomains` and `preload`: they affect every subdomain, so ensure every related subdomain has stable HTTPS and a rollback plan. HSTS **takes effect only when received by the browser over a valid HTTPS response**; it does not protect the very first HTTP visit if the host is not yet preloaded/recorded.

Per Spring Security docs, HSTS is part of the security response headers mechanism, normally attached to HTTPS requests. When a reverse proxy terminates TLS while the backend sees the request as HTTP, HSTS may not be emitted as expected. You can handle it at the edge or configure trusted forwarded schemes so the framework sees `isSecure()` accurately.

**Do not overlap headers:** if both the proxy and Spring set HSTS with different policies, behavior becomes hard to control. Pick one clear owner and test the live response outside the edge.

Additional measures:

- Redirect HTTP→HTTPS at the edge for web login and callbacks; check redirect ordering and canonical URLs.
- Apply `Content-Security-Policy` to login/recovery pages to mitigate XSS; tailor to the frontend.
- Set an appropriate `Referrer-Policy` to limit sensitive tokens/URLs in `Referer`; recovery pages can use `no-referrer`.
- Use `Cache-Control: no-store` for pages/responses carrying sensitive data.
- Never disable all default security headers just to work around one HSTS/iframe issue.

## 16. CSRF, CORS, and Credentialed Cookies

In web apps using **session cookies**, browsers automatically attach cookies when a request matches scope. This opens **Cross-Site Request Forgery** risk if a state-changing endpoint does not verify user intent.

- `HttpOnly` **does not** block CSRF: the browser still attaches the cookie automatically.
- `Secure` protects HTTP transport; it is **not** a CSRF token.
- `SameSite` mitigates some cross-site cases but **does not replace** CSRF tokens and Origin/Referer checks per security policy.
- OAuth2 `state` protects correlation/cross-site request confusion in the login flow; it is not a universal CSRF token for all business endpoints.

An illustrative Spring Security Servlet configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        // Keep default CSRF; do not call csrf.disable().
        return http.build();
    }
}
~~~

This is an integration snippet requiring client registration and real endpoints. `oauth2Login()` does not automatically decide cookie `SameSite` or proxy trust. You must test real login callbacks and logout POSTs.

### Cross-Origin SPA Calling an API

If `https://app.example.test` uses JavaScript to call `https://api.example.test` with cookie authentication:

- `fetch(..., { credentials: "include" })` may be required.
- Server CORS must allowlist **specific origins**, never wildcard `*` with credentials.
- Browsers only accept/send cookies per Domain, Path, SameSite, and HTTPS policies.
- **CORS is not an authentication mechanism** and does not replace CSRF; an allowlisted origin does not imply the user is authorized.
- Cross-origin differs from cross-site: sharing the same eTLD+1 over HTTPS may be treated as same-site in certain scenarios, but browser policies and iframe/third-party contexts still require testing.

If the session cookie is only for the login host, avoid sharing it with the API via `Domain=.example.test` unless architecturally required after reviewing subdomain takeover and session fixation risks. A token-based API/BFF may be a better fit across separate origins.

## 17. Client IP, Rate Limiting, and Spoofed Forwarded Headers

Authentication apps often rate-limit login attempts by IP and account identifier. If you read:

~~~java
request.getHeader("X-Forwarded-For")
~~~

and take the first element as the true IP **without a trust boundary**, an attacker can send arbitrary IPs or comma-separated lists to bypass rate limiters and falsify audits.

A realistic chain:

~~~text
Browser IP A
   -> CDN IP B
   -> Load balancer IP C
   -> Nginx ingress IP D
   -> Spring Boot IP E
~~~

`X-Forwarded-For` can contain multiple IPs. Which entry counts as the client IP depends on **which proxies are trusted and their append/overwrite rules**. There is no single "always pick the first IP" rule that works across all proxy chains.

Strategy:

1. Have the edge/gateway normalize client IP from peer/network data and the trusted proxy chain.
2. Strip/overwrite inbound `Forwarded`/`X-Forwarded-For` so browsers cannot supply fake chains.
3. Configure `RemoteIpValve`/trusted proxies in the container if using `native`.
4. Have the app rate limiter consume the contractually trusted IP alongside user/tenant/global limits.
5. Enforce quotas on both existing and non-existent identifiers to avoid account enumeration.
6. Never treat IP as identity: NAT, VPNs, IPv6 privacy addresses, mobile networks, and proxies change.

**A misconfigured forwarded header does not just break redirects; it can directly neutralize login rate limits and corrupt audit records.**

## 18. Path Prefixes, Multi-App Hosts, and Callback URLs

Suppose the public app lives at `https://login.example.test/auth`, while the gateway strips `/auth` before forwarding to the backend:

~~~text
Browser: GET /auth/oauth2/authorization/corp
Proxy:   GET /oauth2/authorization/corp to backend
Backend: wants to redirect to /auth/login/oauth2/code/corp
~~~

If Spring does not know the prefix, it may generate a callback missing `/auth`. If `X-Forwarded-Prefix` can be altered by an attacker, redirects can be poisoned. Check:

- Does the gateway actually strip the prefix, or does it forward the path intact?
- Does the Spring app have its own `server.servlet.context-path`?
- Is `X-Forwarded-Prefix` set and sanitized by the edge?
- Does the OIDC registration redirect URI at the IdP already include the exact prefix?
- Does the session cookie `Path` cover the callback path?
- If using `__Host-SESSION`, the cookie requires `Path=/`, which can collide with other apps on the same host; consider isolating onto a separate subdomain.
- Do relative redirects and absolute redirects follow the same public base URL policy?
- Do Spring Security filter-chain matchers cover **the rewritten backend path**?

**Do not configure both context path and the same forwarded prefix if that produces a doubled prefix** (`/auth/auth/...`). Verify with a real browser request through the edge and inspect the exact `Location` header.

## 19. WebFlux and Forwarded Headers

With **Spring WebFlux reactive**, instead of Servlet `ForwardedHeaderFilter`, Spring Framework uses `ForwardedHeaderTransformer`. Spring Boot property `server.forward-headers-strategy=framework` configures the corresponding support for the stack.

Reactive cookies also have `server.reactive.session.cookie.*` properties depending on the Spring Boot version. Do not copy `server.servlet.session.cookie.*` and assume they control WebFlux sessions.

Model example:

~~~yaml
server:
  forward-headers-strategy: framework
  reactive:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

This snippet configures **reactive session cookies** and does not reuse the Servlet session config from section 8. If the app adds Spring Session reactive or the gateway issues cookies itself, inspect the actual serializer/response.

In WebFlux, filters and authorization `WebFilter`s differ from a Servlet `SecurityFilterChain`. Yet **the core principles remain unchanged**: trusted proxy boundaries, HTTPS public origin, cookie flags, canonical redirect URIs, issuer validation, and CSRF/cross-site compatibility.

## 20. Testing Cookies and HTTPS Through a Reverse Proxy

A test that only calls a controller directly on localhost **is insufficient**; you need end-to-end tests from the public domain through the proxy, alongside in-app filter/config tests.

### Critical Test Matrix

| Case | Expectation |
|---|---|
| `https://login.example.test/login` | TLS certificate matches hostname; no mixed content; valid page. |
| Public HTTP request | Redirects per policy to canonical HTTPS; never leaks backend URL. |
| Login success via edge | `Set-Cookie` has `Secure; HttpOnly` and right `SameSite`, appropriate Domain/Path. |
| `__Host-SESSION` cookie | Has Secure, Path=/, no Domain; accepted by browser. |
| Backend sees only HTTP | Reconstructed request scheme becomes https if trusted strategy is configured properly. |
| Unknown `Host: attacker.test` | Edge rejects or routes to safe default; never reflected in absolute redirects. |
| Forged `X-Forwarded-Host: attacker.test` | Edge strips/overwrites; `Location` still uses allowed host. |
| Forged `Forwarded: proto=http;host=attacker.test` | Edge strips; app ignores spoofed values. |
| Forged `X-Forwarded-For` | Audit/rate limiter never accepts client-fabricated IP. |
| OAuth2 redirect | `redirect_uri` matches exact registered public HTTPS callback. |
| OIDC top-level GET callback | Session correlation/`state` succeeds under SameSite policy. |
| OIDC/SAML form POST callback | Cookie sent/blocked per designed policy; do not assume Lax suffices. |
| Callback with wrong state/nonce | Authentication rejected; no new session created. |
| Expired user session | Old cookie does not resurrect server-side session. |
| POST without CSRF token | Rejected per web session policy. |
| Session cookie with SameSite=None without Secure | Browser may reject; test must catch this. |
| Multiple replicas | Cookie/session store behaves consistently; logout/revocation works cross-node. |
| HSTS on HTTPS | Header present on public response with a single owner. |
| Path-prefix routing | `Location`, callback, cookie Path, and backend handlers all align. |
| Proxy upstream unavailable | No redirect loop; controlled error response without leaking internal topology. |
| Access logs | Contain no Cookies, Authorization headers, raw tokens/OTPs, or host poisoning strings. |

### External `curl` Checks

~~~bash
# Check TLS/headers at the edge. Do not use -k in production tests.
curl -I https://login.example.test/login

# Check HTTP -> HTTPS; do not follow redirects automatically:
curl -I http://login.example.test/login

# Send forged forwarded host to verify edge sanitization:
curl -I https://login.example.test/login \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'Forwarded: for=192.0.2.200;proto=http;host=attacker.example.test'
~~~

Only run these commands against hostnames you are authorized to test. Tests must not leak real cookies/tokens; use test accounts and avoid dumping Authorization headers into CI logs. With `curl -I` (HEAD), not every login flow handles HEAD identically to GET/POST; to inspect OAuth2 authorize redirects, use safe GET requests with test fixtures and a controlled cookie jar.

For `Set-Cookie`, inspect DevTools **Network/Application** tabs to see why a cookie was rejected: Domain mismatch, SameSite=None missing Secure, `__Host-` prefix violation, HTTPS/HTTP mismatch, or browser storage policy. **Reading the server response header alone does not prove the browser stored the cookie.**

## 21. Standalone Java 17: Trusted Public Origin and Cookie Flags

The following example **runs on the JDK 17 Standard Library** without Spring and illustrates two things:

1. Building a callback URL from a **canonical public origin**, unaffected by spoofed request `Host`/`X-Forwarded-Host` values.
2. Formatting a sample session cookie with `Secure; HttpOnly; SameSite=Lax; Path=/` and no `Domain`.

The program only illustrates **origin policy and header formatting**; it is not an HTTP server, reverse-proxy parser, production cookie serializer, or OAuth2 provider.

~~~java
import java.net.URI;

public class ProxyIdentitySafetyDemo {
    private static final URI PUBLIC_ORIGIN =
            URI.create("https://login.example.test");

    record IncomingRequest(
            String host, String forwardedHost, String forwardedProto) {}

    static String callback(IncomingRequest ignoredUntrustedRequest) {
        // Security-critical URL uses a configured, trusted origin.
        return PUBLIC_ORIGIN
                .resolve("/login/oauth2/code/corp")
                .toString();
    }

    static boolean allowedOrigin(String value) {
        try {
            URI uri = URI.create(value);
            String scheme = uri.getScheme();
            String host = uri.getHost();
            String path = uri.getRawPath();

            return scheme != null
                    && "https".equalsIgnoreCase(scheme)
                    && host != null
                    && "login.example.test".equalsIgnoreCase(host)
                    && uri.getPort() == -1
                    && uri.getRawUserInfo() == null
                    && uri.getRawQuery() == null
                    && uri.getRawFragment() == null
                    && (path == null || path.isEmpty()
                        || "/".equals(path));
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    static String sessionCookie(String demoValue) {
        if (!demoValue.matches("[A-Za-z0-9_-]{16,64}")) {
            throw new IllegalArgumentException("invalid demo value");
        }
        return "__Host-SESSION=" + demoValue
                + "; Path=/; Secure; HttpOnly; SameSite=Lax";
    }

    public static void main(String[] args) {
        IncomingRequest forged = new IncomingRequest(
                "attacker.example.test",
                "attacker.example.test",
                "http");

        System.out.println("callback: " + callback(forged));
        System.out.println("canonical origin allowed: "
                + allowedOrigin("https://login.example.test"));
        System.out.println("evil host allowed: "
                + allowedOrigin("https://login.example.test.evil.test"));
        System.out.println("http origin allowed: "
                + allowedOrigin("http://login.example.test"));

        String cookie = sessionCookie("demoSessionId_123456");
        System.out.println("cookie attributes: "
                + cookie.substring(cookie.indexOf(';') + 2));
    }
}
~~~

Save as `ProxyIdentitySafetyDemo.java` and run on JDK 17+:

~~~bash
javac ProxyIdentitySafetyDemo.java
java ProxyIdentitySafetyDemo
~~~

**Exact stdout:**

~~~text
callback: https://login.example.test/login/oauth2/code/corp
canonical origin allowed: true
evil host allowed: false
http origin allowed: false
cookie attributes: Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Even though `IncomingRequest` contains spoofed values, the callback remains unchanged because the public origin is explicitly configured. `allowedOrigin` is a minimal validator demonstrating **a single fixed root origin**, not a comprehensive URL normalization library: production apps need contracts for port 443, IDNA/hostname normalization, tenant mappings, paths, suffix bypasses, redirect URIs, and URL encoding per the threat model.

`sessionCookie()` only formats a sample header; **a demo session ID is not strong enough as a production credential**. In real apps, let the Servlet container or Spring Session generate session IDs via CSPRNG and manage cookies/serialization. Do not copy this method to replace an authentication/session framework.

## 22. Symptom-Based Troubleshooting

| Symptom | Possible Cause | How to Verify / Fix |
|---|---|---|
| Login redirects to `http://app-auth:8080` | Forwarded proto/host not applied or proxy misconfigured. | Inspect `Location` at the edge, trusted headers, and Boot strategy. |
| OAuth2 `redirect_uri_mismatch` | Callback URL has wrong scheme/host/port/prefix. | Compare exact URI in authorize request against IdP registration. |
| SSO returns with state not found | Session cookie not sent on callback, wrong Path/SameSite, or unshared session store. | DevTools Cookies, `SameSite` vs response mode, session repository. |
| Browser drops cookie | Missing `Secure`, `__Host-` prefix with Domain/Path error, HTTP origin, or browser policy. | Check DevTools cookie rejection reason. |
| HSTS missing | Backend sees HTTP or edge does not set it; header config disabled. | Test real HTTPS response, forwarded strategy, and HSTS owner. |
| Login redirect loop | Scheme/port mismatch, session cookie not retained, conflicting proxy redirect rules. | Trace `Location` chain, inspect edge TLS and cookies. |
| CSRF `403` after login | Session/CSRF cookie mismatch, proxy path rewrite, cross-site POST. | Inspect token repository, SameSite, method, POST origin. |
| Rate limit bypassed | Trusting client-supplied `X-Forwarded-For`. | Test forged IP through edge; configure trusted proxies. |
| Magic-link points to attacker host | Host-header/Forwarded host poisoning. | Enforce canonical origin and request host validation. |
| Multi-replica app drops logins | Local sessions, mismatched cookie serializers, broken sticky sessions. | Use shared store/proper topology and integration tests. |
| Subdomain reads/injects session cookie | Overly broad `Domain` or compromised subdomain. | Use host-only/`__Host-` and isolate the login origin. |
| Cookie persists after logout | Mismatched name/Domain/Path on delete or server-side session not invalidated. | Compare logout `Set-Cookie` and session store state. |
| CORS enabled but cookie not sent | Wrong credentials mode/SameSite/Domain or wildcard origin. | Check browser network logs, explicit origins, and CSRF plan. |
| External callback missing `/auth` | Proxy strips prefix, Boot unaware of forwarded prefix. | Compare browser URL, backend URI, and IdP callback. |
| Internal hostname exposed in HTML/email | Self URL built from internal request scheme/host. | Configure canonical base URL and test absolute links. |

When diagnosing, collect data **safely**: scheme/host/port, route template, status, header names/flags, request ID, and proxy trace; **never** log full session cookies, authorization codes, access tokens, passwords, or OTPs. If reproducible tests are needed, use fake accounts/test tokens in an isolated environment.

## 23. Production Readiness Checklist

### Edge / Network / TLS

- [ ] Public login origin serves HTTPS with a valid certificate; HTTP is handled per policy.
- [ ] Backend accepts connections only from trusted proxies/services; proxy→backend hop is secured.
- [ ] Edge proxy strips/overwrites **both `Forwarded` and `X-Forwarded-*`** from clients.
- [ ] Unknown Host/SNI is rejected or routed to a safe default, never reaching the auth app.
- [ ] CDN/LB/ingress chain has a clear policy on who is trusted and who sets client IP, host, proto, port, and prefix.
- [ ] Logs never record cookies, Authorization headers, raw recovery tokens, or sensitive query/body data.
- [ ] HSTS owner and scope (`includeSubDomains`/`preload`) are approved.

### Spring Boot / Spring Security

- [ ] `server.forward-headers-strategy` matches topology: `none`, `native`, or `framework`.
- [ ] If a Tomcat TLS-terminating proxy hits a context-root redirect issue, verify `server.tomcat.redirect-context-root=false`.
- [ ] No duplicate `ForwardedHeaderFilter`/`RemoteIpValve` registrations without explicit justification.
- [ ] Security-critical absolute URLs use a canonical origin or validated allowlist.
- [ ] OIDC `redirect_uri` matches public scheme/host/port/prefix; IdP issuer/audience are validated separately.
- [ ] Security filter chain cannot be bypassed via proxy path rewrites.
- [ ] Actual session cookies include Secure, HttpOnly, SameSite, and Path/Domain per policy.
- [ ] `__Host-` cookies omit Domain, use Path=/, and set Secure; verified accepted by real browsers.
- [ ] With Spring Session, `CookieSerializer` and session store config are verified directly.
- [ ] Session rotation, timeout, logout/revocation, and MFA freshness are not bypassed.

### Browser / Federation / CSRF

- [ ] Test OIDC top-level GET and all supported `form_post`/SAML POST callbacks.
- [ ] `SameSite=Lax`/`Strict`/`None` chosen per request context, not out of habit.
- [ ] Session/CSRF cookies have distinct policies when an SPA must read the CSRF token.
- [ ] CSRF protection is never disabled blanket-wide due to callback issues.
- [ ] CORS allowlists specific origins when credentials are used; CORS is never treated as authentication.
- [ ] Cookies are not shared broadly across other subdomains unnecessarily.
- [ ] Login/recovery pages carry appropriate CSP, Referrer-Policy, and `no-store`.

### Testing / Monitoring

- [ ] Test forged Host, Forwarded, and X-Forwarded-* through the **public edge**.
- [ ] Test redirects, session cookies, HSTS, OAuth2 callbacks, logout, and multiple replicas.
- [ ] Test rate-limit IP after trusted proxy normalization; never trust self-reported client IPs.
- [ ] Test host/prefix changes across CDN/ingress and multiple browser versions.
- [ ] Audits include correlation ID, policy version, and outcome without storing credentials.
- [ ] Recovery runbooks exist for cookie flag, proxy header, or redirect URI changes.

## 24. Conclusion

**Deploying Spring Security safely behind a reverse proxy requires separating two truths:** browsers talk to a **public HTTPS origin**, while Spring Boot may sit on an HTTP backend and should only consume **forwarded metadata produced by a trusted proxy**.

Three control groups must work together:

1. **Trust boundary:** the edge validates Host/SNI, strips spoofed headers, sets proto/host/port/IP, and restricts backend ingress.
2. **Cookies/sessions:** `Secure`, `HttpOnly`, `SameSite`, host-only/`__Host-`, and proper scope/Path; server-side session revocation, CSRF, and session stores remain separate layers.
3. **Identity and redirects:** OIDC/OAuth2 callbacks, login/recovery links, and any credential-bearing URLs must use a controlled public HTTPS origin; IdP issuer and identity claims must never be inferred from proxy headers.

A single line of `server.forward-headers-strategy=framework` may fix a redirect, but **it is not a proxy authentication mechanism**. The right approach is to treat **proxy, Spring Security, browser cookies, and IdP** as one continuous chain of trust, testing from the Internet edge to the backend rather than relying solely on controller unit tests.

## References

- [Spring Boot 3.5 — Embedded Web Servers / Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): forwarded headers, NATIVE/FRAMEWORK, and Tomcat redirect context root.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `server.forward-headers-strategy` and Servlet/Reactive session cookie properties.
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): trust boundaries, stripping, forwarded headers, and removeOnly.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): HSTS, security headers, and default behavior.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): client registration, authorization endpoint, and redirect URI.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF in web session flows.
- [Spring Session — API and CookieSerializer](https://docs.spring.io/spring-session/reference/api.html): Spring Session cookie serialization and multi-node sessions.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure, HttpOnly, SameSite, Domain, Path, cookie prefixes, and Partitioned.
- [MDN — Using HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): cookie scope, security prefixes, and browser behavior.
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security): HSTS scope, HTTPS, and browser behavior.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html): syntax and semantics of `Forwarded`.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html): foundational cookie model.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0-final.html): issuer/redirect URI/state/nonce and ID Token semantics.
