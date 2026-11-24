# Referrer-Policy, Permissions-Policy, and Reducing Browser Data Leakage

## 1. Objectives and Context

When users access a secure page through a browser, data can leave the application along non-obvious paths: the previous page's URL is placed by the browser into the `Referer` header when navigating to the next page; scripts and iframes may request access to the camera, microphone, or location; third-party resources may collect information; caches, logs, and analytics tools may retain URLs containing sensitive query strings.

Two HTTP response headers help control parts of this surface:

- **`Referrer-Policy`**: tells the browser whether source-page information may be sent in the `Referer` request header, and if so, how much.
- **`Permissions-Policy`**: restricts which browser capabilities the document and embedded iframes may use, such as `geolocation`, `camera`, and `microphone`.

This lesson belongs to **Headers and HTTPS** in the **Spring Security - reactive** module. Examples target **Spring WebFlux**, Java 17+, Spring Boot 3.x, and Spring Security 6.5.x.

After this lesson, you can:

1. Accurately distinguish the **`Referrer-Policy` response header** from the **`Referer` request header**, including the historical misspelling in `Referer`.
2. Choose between `no-referrer`, `same-origin`, `strict-origin-when-cross-origin`, and other directives based on privacy requirements; predict cross-origin, same-origin, and HTTPS → HTTP behavior.
3. Distinguish the **browser default `strict-origin-when-cross-origin`** from **Spring Security WebFlux 6.5's default `Referrer-Policy: no-referrer`**, and know when reconfiguring weakens the policy.
4. Understand the syntax `Permissions-Policy: geolocation=(), camera=(), microphone=()`; the meanings of `()`, `(self)`, and origin lists.
5. Understand the interaction between the parent document header, iframe `allow` attribute, and user-granted permissions; never treat Permissions Policy as an authentication system.
6. Configure headers using `ServerHttpSecurity.headers(...)` and `SecurityWebFilterChain`, avoiding Servlet's `HttpSecurity`.
7. Run a Java 17+ WebFlux app emitting proper response headers, and write `WebTestClient` tests for public, authenticated, and denied paths.
8. Verify **actual behavior** using browser DevTools; understand why checking headers with curl/WebTestClient does not prove the browser blocked an API or omitted `Referer`.
9. Combine HTTPS/HSTS, CSP, CSRF, CORS, URL design, cache control, XSS prevention, and log redaction to reduce data leakage across layers.

**Scope:** response policies of an **inbound Spring WebFlux web application**. Never assume merely adding two headers stops all tracking, browser extensions, screenshots, malicious JavaScript, or data leaks via other request URLs.

## 2. How Does Data Leak from the Browser?

### 2.1. Example Page with a Sensitive URL

Suppose a user opens:

```text
https://app.example/account/recovery?ticket=SECRET_VALUE
```

Then that page links to or loads resources from:

```text
https://partner.example/help
https://cdn.example/widget.js
```

When the browser follows a link or fetches a resource, it may send a `Referer` header identifying the source page, depending on **Referrer-Policy**, request type, browser, and HTTPS context.

A dangerous `Referer` value when full path/query is included:

```http
GET /help HTTP/1.1
Host: partner.example
Referer: https://app.example/account/recovery?ticket=SECRET_VALUE
```

This is **HTTP illustrating the risk**, not what happens under every policy. A strong policy strips or truncates the source URL. More importantly, applications should not place **passwords, session IDs, access tokens, reset tokens, API keys, or PII** in URLs whenever safer alternatives exist, because Referrer-Policy does not remove data from browser history, server logs, or analytics.

### 2.2. Leakage Through Browser APIs

An ad, iframe, or script might attempt to call:

- `navigator.geolocation.getCurrentPosition(...)` to request location.
- `navigator.mediaDevices.getUserMedia({ video: true })` to request the camera.
- `navigator.mediaDevices.getUserMedia({ audio: true })` to request the microphone.
- Other features supported by the browser with corresponding Permissions Policy directives.

Permissions Policy lets a site define the **upper bound** of those capabilities per document/embedded context. Yet even when the policy permits geolocation, **user consent and secure-context requirements** may still apply. It does not grant camera/location access to scripts, and does not replace backend authorization controls.

### 2.3. Other Leak Paths Not Handled by These Two Headers

| Leak source | Example | Complementary control |
|---|---|---|
| URL sent directly to server | `GET /account?token=...` | Avoid secrets in URLs; control logs and caches |
| `Referer` to other origins | External links/resources carrying source URL | `Referrer-Policy`, `rel="noreferrer"`, URL design |
| Browser feature APIs | Iframe requesting camera/location | `Permissions-Policy`, `iframe allow`, user permissions |
| Third-party JavaScript | Script reads DOM and exfiltrates via fetch | CSP, supply-chain controls, avoid untrusted scripts, XSS prevention |
| Cookies readable by scripts | Session cookie missing HttpOnly | `HttpOnly`, `Secure`, `SameSite`, XSS prevention |
| Local/shared caches | Account page cached in browser/CDN | `Cache-Control: no-store`, cache partitioning |
| Logs, telemetry | Query/headers containing tokens | Field redaction/allowlisting, retention policies |
| Cross-origin response readable | CORS allowing untrusted origins | CORS allowlist, credentials policy |
| Unencrypted transport | HTTP and mixed content | HTTPS, HSTS, Secure cookies |
| Forged HTTP requests | Another site tricks browser into POSTing with cookies | CSRF protection and SameSite |

## 3. Referrer-Policy: Exact Name and Meaning

### 3.1. Two Headers Going in Opposite Directions

The **request header** is officially named `Referer` (missing an "r" in "referrer" due to a historical spelling error). Browsers may send it during navigations or resource loads.

The **response header** is `Referrer-Policy` (spelled correctly with two "r"s), sent by the source page or resource to instruct the browser how much referrer detail may be disclosed on subsequent requests originating from that page.

Example:

```http
HTTP/1.1 200 OK
Referrer-Policy: same-origin
Content-Type: text/html;charset=UTF-8
```

This response **does not strip or modify the `Referer` of the incoming HTTP request that already reached the server**. It instructs the user agent for subsequent related requests within the policy's scope. The browser computes `Referer` from the document, destination, referrer policy, and context.

Do not use `Referrer-Policy` as a server-side credential filter or write a WebFilter stripping client-sent Referer headers; those are different responsibilities.

### 3.2. What Is an "Origin"?

An **origin** comprises **scheme + host + port**. Example:

```text
https://app.example/account/profile?tab=security
               |                 |
               |                 +-- path + query: detailed URL info
               +-- origin: https://app.example

https://app.example:8443 is a different origin due to different port.
http://app.example is a different origin due to different scheme.
```

`Referer` typically excludes the `#section` fragment, whereas path and query may be included depending on policy. Sending only the origin avoids leaking detailed URLs, though it still discloses the source website. When the origin itself is sensitive, `no-referrer` is the stronger choice.

### 3.3. Comparison Table of Key Directives

Source example: `https://app.example/account?ticket=abc`.

| Policy | To same-origin HTTPS | To cross-origin HTTPS | From HTTPS to HTTP |
|---|---|---|---|
| `no-referrer` | Do not send Referer | Do not send | Do not send |
| `same-origin` | Send source URL (path/query may be included) | Do not send | Do not send (different origin) |
| `origin` | Origin only | Origin only | May send origin per this directive; avoid for secret-sensitive flows |
| `strict-origin` | Origin only | Origin only | Do not send |
| `strict-origin-when-cross-origin` | Source URL | Origin only | Do not send |
| `origin-when-cross-origin` | Source URL | Origin only | May send origin only on HTTP per directive |
| `no-referrer-when-downgrade` | Source URL | Source URL | Do not send |
| `unsafe-url` | Source URL | Source URL | May send source URL; very risky |

"Source URL" in the table means the URL the browser permits sending, excluding username/password, fragments, and parts stripped by browser rules. Never rely on weaker directives when the source contains reset tokens, auth codes, or PII.

**Recommendation:** for login, account, callback, recovery, and private workflows, choose `no-referrer` unless a referrer is genuinely required. When internal referrers are needed without disclosing to other origins, `same-origin` fits. When site-level referral analytics are needed across HTTPS origins, `strict-origin-when-cross-origin` is a compromise, though it still reveals the origin.

### 3.4. Browser Default Differs from Spring Security Default

MDN documents the modern browser default when **no policy is specified** as `strict-origin-when-cross-origin`. **However, the official Spring Security WebFlux 6.5 documentation states that Spring Security adds `Referrer-Policy: no-referrer` by default.**

These two facts do not contradict each other:

```text
Browser receives no Referrer-Policy:
  -> typically uses strict-origin-when-cross-origin (browser default)

Response passes through Spring Security WebFlux 6.5 default header setup:
  -> typically receives Referrer-Policy: no-referrer
  -> browser follows the stricter response policy
```

In **Spring Security Servlet**, defaults are documented differently; do not assume WebFlux rules apply across every stack or version. And when a reverse proxy/gateway alters or overwrites response headers, **the value the browser actually receives** is what must be checked.

References: [Spring Security 6.5 WebFlux Header Reference](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html) and [MDN Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy).

### 3.5. Choosing a Policy by Data Sensitivity

**Highest-sensitivity sites:**

```http
Referrer-Policy: no-referrer
```

Sends no Referer in policy-governed scenarios. Great for banking, patient portals, auth/reset pages, and confidential dashboards, though it may reduce Referer-based referral metrics/flows.

**Internal apps needing referrers for same-origin navigation:**

```http
Referrer-Policy: same-origin
```

Sends no Referer to external origins, while still sending detailed URLs between same-origin routes. **Never put secrets in internal URLs** just because `same-origin` is set.

**Informational/marketing sites needing external origin-level referral metrics:**

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Sends full URL on same-origin, origin only on cross-origin HTTPS, and nothing on HTTPS → HTTP downgrades. This matches typical browser defaults when no header is sent, yet is **less private than WebFlux Spring Security's default `no-referrer`**.

**Avoid:**

```http
Referrer-Policy: unsafe-url
```

This directive can leak paths and queries across origins and downgrades; it is almost never appropriate for apps handling sensitive data.

## 4. How Browsers Apply Referrer-Policy

### 4.1. Link Navigation

A source document receives a `Referrer-Policy` header. When a user clicks a link to another origin, the browser computes `Referer` using the source's policy.

Example with `same-origin`:

```text
Source page:
https://app.example/account/settings?tab=privacy

Click to:
https://app.example/help
-> Referer may include the same-origin source URL

Click to:
https://support.vendor.example/help
-> Referer omitted due to different origin
```

A `302`/`303` redirect or subresource-initiated request can involve policies from multiple responses; use Browser DevTools to verify actual behavior rather than over-extrapolating from a single intermediate response.

### 4.2. Loading Images, Scripts, Stylesheets, and Iframes

Referrer policy also affects subresource requests where applicable: `img`, `script`, CSS, `iframe`, and fetch. Cross-origin CSS has its own stylesheet referrer rules in certain scenarios; do not think only link clicks produce `Referer`.

Under a document's `no-referrer`, the browser omits referrers per that policy for in-scope requests. **That does not stop subresource requests from being sent**; tracking scripts can still call external endpoints if permitted. Reducing third-party contact requires CSP (e.g., `connect-src`, `img-src`, `script-src`) and dependency governance, not just Referrer-Policy.

### 4.3. Element-Level Overrides When Strictly Needed

HTML allows local controls:

```html
<!-- Sensitive link: prevent source URL from becoming Referer -->
<a href="https://outside.example/help"
   rel="noreferrer noopener">External help</a>

<!-- Local referrer directive for an image -->
<img src="https://images.example/banner.png"
     referrerpolicy="no-referrer"
     alt="Banner">

<!-- Referrer policy for a specific link -->
<a href="https://docs.example/"
   referrerpolicy="no-referrer">Documentation</a>
```

`rel="noreferrer"` omits `Referer` for that link; `noopener` restricts the target tab's access to `window.opener` in supporting browsers. For user-authored HTML containing links, you must still sanitize URLs, block `javascript:` injection, and open tabs safely.

An HTML document can set:

```html
<meta name="referrer" content="no-referrer">
```

However, **the HTTP response header is the easiest app-wide default to enforce**, because meta tags take effect only when and where the browser parses them. Do not use meta tags instead of a unified response policy when HTML embeds early-loading third-party resources.

### 4.4. JavaScript Fetch Has Its Own Option

```javascript
fetch("/api/account", {
  method: "GET",
  referrerPolicy: "no-referrer"
});
```

This is a browser-side JS snippet, not server code. It affects only that request's referrer behavior; **it does not replace CORS, cookies, authentication, authorization, or CSRF**. Web apps still need an appropriate default policy because you cannot assume every script calls fetch with the right options.

### 4.5. Never Use Referer as Authentication or Sole CSRF Guard

`Referer` can be legitimately omitted by browser policy or forged by non-browser clients; it is weak evidence of user identity. Use Spring Security authentication and CSRF protection aligned with your threat model. A missing `Referer` on the server is **not** enough to conclude a request is an attack, and a seemingly same-origin `Referer` **does not** prove the user is authorized.

## 5. Permissions-Policy: Restricting Document/Iframe Capabilities

### 5.1. Feature-Gating Mechanism

`Permissions-Policy` is an HTTP response header telling the browser **which feature APIs are permitted** in the document and embedded browsing contexts, by origin list. Example:

```http
Permissions-Policy: geolocation=(), camera=(), microphone=()
```

In browsers supporting those directives, this policy prevents the document and nested contexts from using geolocation, camera, or microphone. JavaScript calls to those APIs may receive errors like `PERMISSION_DENIED` or `NotAllowedError` instead of showing a permission prompt for a blocked feature.

This is **one restriction layer**. Browsers not supporting a directive may ignore it, and Permissions Policy does not directly control what data the backend returns, which fetch requests are sent, or what hardware the OS has.

### 5.2. Basic Syntax

A `Permissions-Policy` header contains **comma-separated** directives. Each directive maps to an allowlist:

```http
Permissions-Policy: geolocation=(), camera=(), microphone=()
```

| Allowlist | Meaning |
|---|---|
| `()` | Empty allowlist: blocks the feature for the document and eligible child contexts |
| `(self)` | Allows the current origin and matching same-origin contexts, subject to parent policy |
| `("https://maps.example")` | Specifies a permitted origin per policy/browser rules |
| `(self "https://maps.example")` | Combines same-origin and an explicitly named origin |
| `*` | Wildcard, broadly allowing; generally unnecessary for sensitive features |

Note: origins inside the allowlist are enclosed in **double quotes**; the `self` token is unquoted in HTTP header syntax. `()` is not an empty wildcard allowing everything—it means **deny the feature**.

A real-world example:

```http
Permissions-Policy: geolocation=(self), camera=(), microphone=()
```

This allows the app's own origin to use geolocation (still subject to user consent and secure context if required by the API) while blocking camera/microphone. Pick the narrowest scope the product requires.

### 5.3. Parent Policy and Iframe `allow`

Suppose the main page permits geolocation only for its own origin:

```http
Permissions-Policy: geolocation=(self)
```

An embedded page from another domain:

```html
<iframe src="https://maps.partner.example/"
        allow="geolocation">
</iframe>
```

**Do not assume the iframe gets geolocation.** The parent policy already restricted the allowed origin set. The iframe `allow` attribute cannot "widen" beyond the parent header's ceiling; policies apply by inheritance/intersection and browser support.

If a partner iframe truly needs a feature, you must:
1. Evaluate the partner origin's permissions and risk.
2. Configure the parent `Permissions-Policy` to include the partner origin in the allowlist.
3. Configure `iframe allow` accordingly.
4. Test on supported browsers, as directive/iframe behavior depends on the specific feature and platform.

Illustrative example:

```http
Permissions-Policy: geolocation=(self "https://maps.partner.example")
```

```html
<iframe src="https://maps.partner.example/"
        allow="geolocation">
</iframe>
```

Even when every policy permits it, the browser may still prompt for user consent. Never grant `*` if only one iframe needs the feature.

### 5.4. Different from the User Permission Prompt

Some browser APIs natively require user approval via a permission prompt. Permissions Policy **can only restrict** calling the API within the document; it never grants permission to bypass the prompt.

Example under `camera=()`:

```javascript
navigator.mediaDevices.getUserMedia({video: true})
  .then(stream => {
    // Only if browser permits and user granted permission does
    // stream exist. Policy camera=() normally blocks this.
    stream.getTracks().forEach(track => track.stop());
  })
  .catch(error => console.log(error.name));
```

In supporting environments, a policy-blocked camera can reject with `NotAllowedError`. Yet `NotAllowedError` can also result from user denial, missing HTTPS, browser settings, or other causes; to verify the policy itself, check response headers and browser diagnostics.

For geolocation:

```javascript
navigator.geolocation.getCurrentPosition(
  position => console.log(position.coords.latitude),
  error => console.log(error.code)
);
```

A blocking policy typically yields `PERMISSION_DENIED`. Do not collect real coordinates in demos or transmit location data over the network without consent.

### 5.5. Legacy Feature-Policy vs. Modern Permissions-Policy

Old header:

```http
Feature-Policy: geolocation 'self'; camera 'none'
```

New header:

```http
Permissions-Policy: geolocation=(self), camera=()
```

The two headers have **different syntax**. Never write `Permissions-Policy: geolocation 'none'` expecting the browser to enforce it. Unrecognized directives may be ignored. Some directives are supported only on certain browsers/versions; always check browser compatibility.

### 5.6. Permissions Policy Is Not Content Security Policy

- **Permissions Policy**: controls **browser features** (camera/microphone/geolocation, certain other APIs).
- **CSP**: controls **content/script/style/connect/img/frame sources** per policy.
- **CORS**: governs whether cross-origin JS can read responses or use credentials in applicable cases.
- **X-Frame-Options / frame-ancestors**: restricts who may embed your page.
- **Authentication/authorization**: enforces principal/role/resource permissions on the server.

For instance, `camera=()` does not stop a script from sending DOM data via `fetch`. To curb network exfiltration, you need CSP, XSS prevention, script governance, and keeping sensitive data away from untrusted third parties.

## 6. Policy Selection Strategy by Product Type

| Application type | Recommended Referrer-Policy | Example Permissions-Policy | Rationale |
|---|---|---|---|
| Sensitive account/customer pages | `no-referrer` | `geolocation=(), camera=(), microphone=()` | Minimizes origin/URL leakage and locks unused features |
| Internal admin portal needing intra-site referrer | `same-origin` | `geolocation=(), camera=(), microphone=()` | Allows same-origin URL referrers; sends nothing externally |
| Public site needing external origin-level referral metrics | `strict-origin-when-cross-origin` | Enable only strictly needed features | Balances analytics with hiding private paths/queries |
| Map app using location itself | `no-referrer` or `same-origin` | `geolocation=(self), camera=(), microphone=()` | Permits geolocation only for own origin |
| Video call app using camera/microphone | Policy matching data sensitivity | `camera=(self), microphone=(self)` | Does not break core functionality |
| App embedding trusted iframe needing specific feature | Policy per data classification | Explicit partner allowlist + `iframe allow` | Prevents arbitrary cross-origin capabilities |

These values are only **starting points**. Feature policies can break product features if overly strict. Test per use case, browser, CDN/reverse proxy, iframe, device, and accessibility. Browser support for individual directives is uneven.

## 7. Proper Configuration in Spring Security WebFlux

### 7.1. WebFlux Differs from Servlet

For an inbound **Spring WebFlux** app, use:

- `ServerHttpSecurity` builder.
- `SecurityWebFilterChain`.
- `@EnableWebFluxSecurity` or matching Spring Boot auto-configuration.
- Enum `org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy`.

Never copy Servlet's `HttpSecurity`/`SecurityFilterChain` into WebFlux. Even if a WebFlux app uses `WebClient`, inbound security depends on the framework handling incoming HTTP requests.

### 7.2. DSL for Configuring Referrer Policy

Per Spring Security 6.5 WebFlux docs:

```java
// Snippet inside @Bean SecurityWebFilterChain:
return http
    .headers(headers -> headers
        .referrerPolicy(referrer -> referrer
            .policy(ReferrerPolicy.SAME_ORIGIN)))
    .build();
```

Import `ReferrerPolicy` from `org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy`.

With `SAME_ORIGIN`, browsers can send full internal URLs in `Referer`, making this a **less strict customization than Spring Security WebFlux 6.5's `no-referrer` default**. Choose it only if analytics/UX requires intra-site referrers and pages contain no sensitive URL secrets.

To maintain high privacy:

```java
.referrerPolicy(referrer -> referrer
    .policy(ReferrerPolicy.NO_REFERRER))
```

This corresponds to `Referrer-Policy: no-referrer`. While WebFlux 6.5 defaults already emit `no-referrer`, declaring it explicitly helps keep the policy visible in code reviews and independent of future default changes.

### 7.3. DSL for Configuring Permissions Policy

Spring Security WebFlux **does not add Permissions-Policy by default**. Declare:

```java
// Snippet inside @Bean SecurityWebFilterChain:
return http
    .headers(headers -> headers
        .permissionsPolicy(permissions -> permissions
            .policy("geolocation=(), camera=(), microphone=()")))
    .build();
```

`policy(String)` accepts the **header value syntax**. Spring Security emits that header value; **it does not guarantee every browser supports or honors every directive**. Do not paste old Feature-Policy syntax or accidentally replace commas with semicolons between directives.

### 7.4. Combining Both Policies While Keeping Other Default Security Headers

```java
// Configuration snippet inside SecurityWebFilterChain
.headers(headers -> headers
    .referrerPolicy(referrer -> referrer
        .policy(ReferrerPolicy.SAME_ORIGIN))
    .permissionsPolicy(permissions -> permissions
        .policy("geolocation=(), camera=(), microphone=()")))
```

This DSL adds/customizes the relevant writers **without calling `headers.disable()`**. Calling `headers(headers -> headers.disable())` strips other defaults like `X-Content-Type-Options`, HSTS (on HTTPS), `X-Frame-Options`, and cache controls; avoid disabling all headers just to adjust one directive.

### 7.5. Which Security Chains Own the Policy?

With multiple `SecurityWebFilterChain` beans, a request passes only through the chain selected by `securityMatcher` and chain order. Putting headers solely in a chain matching `/api/**` leaves an HTML page `/account` in another chain without that policy. At gateways/CDNs, response headers may also be added, stripped, or overwritten outside the app.

Inspect **the final response the browser receives**, not just Java configuration classes. Error pages, static resources, redirects, and gateway-generated responses also need appropriate policies. Never assume responses outside Spring Security inherit the same headers.

## 8. Runnable Java 17+ Spring Boot Example

We build an application with:

- Public `GET /` and `GET /public`.
- `GET /features` returning HTML to test browser feature policies.
- `GET /account` requiring HTTP Basic and displaying the principal.
- Default deny for undeclared URLs/HTTP methods.
- Response headers `Referrer-Policy: same-origin` and `Permissions-Policy: geolocation=(), camera=(), microphone=()`.

**Why choose `same-origin` in the demo?** To illustrate customizing away from Spring Security WebFlux 6.5's default. For especially sensitive pages like recovery/identity portals, use `NO_REFERRER` as in section 7.2. Never put secrets in queries even with `same-origin`.

### 8.1. Project Initialization

Create a project from [Spring Initializr](https://start.spring.io/) with Java 17+, Spring Boot 3.5.x, Gradle Groovy DSL, and dependencies:

- Spring Reactive Web: `spring-boot-starter-webflux`.
- Spring Security: `spring-boot-starter-security`.
- Spring Boot Starter Test, Spring Security Test.

Keep the plugins, repositories, toolchain, and Gradle wrapper generated by Initializr. The `dependencies` block in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is a **Gradle block**, not a standalone build file. Do not add `spring-boot-starter-web` when targeting inbound WebFlux: when both MVC and WebFlux starters are present, Spring Boot 3.x typically defaults to Servlet MVC.

Structure:

```text
src/main/java/demo/browserheaders/
  BrowserHeadersApplication.java
  SecurityConfig.java
  PagesController.java
src/test/java/demo/browserheaders/
  BrowserHeadersTests.java
```

### 8.2. BrowserHeadersApplication.java

```java
package demo.browserheaders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BrowserHeadersApplication {
    public static void main(String[] args) {
        SpringApplication.run(BrowserHeadersApplication.class, args);
    }
}
```

### 8.3. SecurityConfig.java

```java
package demo.browserheaders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    public static final String PERMISSIONS =
        "geolocation=(), camera=(), microphone=()";

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/", "/public", "/features").permitAll()
                .pathMatchers(HttpMethod.GET, "/account")
                    .authenticated()
                .anyExchange().denyAll())
            .headers(headers -> headers
                .referrerPolicy(referrer -> referrer
                    .policy(ReferrerPolicy.SAME_ORIGIN))
                .permissionsPolicy(permissions -> permissions
                    .policy(PERMISSIONS)))
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }
}
```

Configuration analysis:

1. `@EnableWebFluxSecurity` with `ServerHttpSecurity` protects inbound WebFlux.
2. Three GET routes are public; `GET /account` requires authentication. All other requests are denied under the demo policy.
3. `ReferrerPolicy.SAME_ORIGIN` emits `Referrer-Policy: same-origin`.
4. `permissionsPolicy(...policy(PERMISSIONS))` emits the exact string `geolocation=(), camera=(), microphone=()`.
5. HTTP Basic provides an easy-to-test authentication method; `formLogin` is disabled so APIs do not redirect to HTML on missing credentials.
6. Default CSRF is not disabled; the demo has no business POST endpoints. If adding forms/POSTs, design tokens and cookies properly.
7. User `alice` with password `alice-pass` is for learning only, hashed by `DelegatingPasswordEncoder`; **never** store passwords like this in production source.
8. HTTP Basic sends base64 credentials in `Authorization`, unencrypted. Production must use HTTPS.
9. Both response headers are **browser policies**, not substitutes for backend authorization: unauthenticated users still cannot access `/account`.

### 8.4. PagesController.java

```java
package demo.browserheaders;

import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PagesController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/account")
    public Mono<String> account() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context ->
                "account:" + context.getAuthentication().getName());
    }

    @GetMapping(value = "/features",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> features() {
        return Mono.just("""
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="utf-8">
              <title>Permissions Policy test</title>
            </head>
            <body>
              <h1>Browser feature permission test</h1>
              <button id="geo">Try geolocation</button>
              <button id="camera">Try camera</button>
              <pre id="result">Ready</pre>
              <script>
                const output = document.getElementById("result");
                document.getElementById("geo").addEventListener(
                  "click", () => {
                    if (!navigator.geolocation) {
                      output.textContent = "Geolocation unavailable";
                      return;
                    }
                    navigator.geolocation.getCurrentPosition(
                      pos => output.textContent = "Position granted",
                      err => output.textContent =
                        "Geolocation error code: " + err.code
                    );
                  });
                document.getElementById("camera").addEventListener(
                  "click", async () => {
                    try {
                      const stream =
                        await navigator.mediaDevices.getUserMedia(
                          { video: true });
                      stream.getTracks().forEach(t => t.stop());
                      output.textContent = "Camera granted";
                    } catch (err) {
                      output.textContent =
                        "Camera error: " + err.name;
                    }
                  });
              </script>
            </body>
            </html>
            """);
    }
}
```

`/features` is strictly a **feature-policy test page**. In browsers supporting `geolocation=()`/`camera=()`, those calls are normally blocked, though exact error details depend on browser, device, secure context, and user settings. Never invoke location/camera APIs automatically on page load: only test after a user button click.

By default Spring Security adds other headers such as `X-Frame-Options: DENY`; this page does not demonstrate iframes. If a product needs to embed trusted iframes, design both the framing policy and Permissions Policy rather than merely adding `allow`.

### 8.5. Running the Demo

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Inspect response headers with curl:

```bash
curl -i http://localhost:8080/public
```

Expected highlights:

```http
HTTP/1.1 200 OK
Referrer-Policy: same-origin
Permissions-Policy: geolocation=(), camera=(), microphone=()
Content-Type: text/plain;charset=UTF-8

public
```

Header ordering, casing, Content-Type charset, and other default security headers may vary by server/version; this **illustrates the key values**, not a byte-for-byte copy of the entire response.

Check the authenticated resource:

```bash
curl -i http://localhost:8080/account
curl -i -u alice:alice-pass http://localhost:8080/account
```

Expected:
- No credentials: typically **401 Unauthorized** due to HTTP Basic challenge.
- Valid credentials: **200 OK**, body `account:alice`, and both policy headers.

Never use real passwords on the command line, in shell histories, or in logs. Localhost HTTP curl commands are for demo use only; production requires HTTPS and secure cookie settings.

## 9. WebTestClient Integration Tests

These tests **verify that the server emits the expected response headers** on routes protected by `SecurityWebFilterChain`. They do not verify that a browser enforces the referrer or camera policies as expected; section 10 covers real browser testing.

Create `src/test/java/demo/browserheaders/BrowserHeadersTests.java`:

```java
package demo.browserheaders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BrowserHeadersTests {

    @Autowired
    WebTestClient client;

    private void expectHeaders(
            WebTestClient.ResponseSpec response) {
        response.expectHeader()
            .valueEquals("Referrer-Policy", "same-origin");
        response.expectHeader()
            .valueEquals("Permissions-Policy",
                SecurityConfig.PERMISSIONS);
    }

    @Test
    void homeIncludesPolicyHeaders() {
        var response = client.get().uri("/").exchange()
            .expectStatus().isOk();

        expectHeaders(response);
        response.expectBody(String.class).isEqualTo("home");
    }

    @Test
    void publicPageIncludesBothHeaders() {
        var response = client.get().uri("/public").exchange()
            .expectStatus().isOk();

        expectHeaders(response);
        response.expectBody(String.class).isEqualTo("public");
    }

    @Test
    void htmlFeaturesPageIncludesPolicies() {
        var response = client.get().uri("/features").exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_HTML);

        expectHeaders(response);
        response.expectBody(String.class)
            .value(body ->
                org.junit.jupiter.api.Assertions.assertTrue(
                    body.contains("Try geolocation")));
    }

    @Test
    void accountWithoutCredentialsNeedsAuthentication() {
        client.get().uri("/account")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedAccountStillGetsBothHeaders() {
        var response = client.get().uri("/account")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk();

        expectHeaders(response);
        response.expectBody(String.class).isEqualTo("account:alice");
    }

    @Test
    void authenticatedUnknownRouteIsDenied() {
        client.get().uri("/unknown")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void incomingRefererIsNotAuthorizationCredential() {
        var response = client.get().uri("/public")
            .header("Referer",
                "https://outside.example/page?hint=demo")
            .exchange()
            .expectStatus().isOk();

        expectHeaders(response);
        response.expectBody(String.class).isEqualTo("public");
    }
}
```

Explanation:

- `expectHeaders` checks **the two response headers**, not incoming request headers.
- `homeIncludesPolicyHeaders` and `publicPageIncludesBothHeaders` confirm public pages still emit the policies.
- `htmlFeaturesPageIncludesPolicies` verifies the HTML document receives the headers; feature-restriction effectiveness requires browser tests.
- `accountWithoutCredentialsNeedsAuthentication` proves policy headers do not grant authentication.
- `authenticatedAccountStillGetsBothHeaders` confirms protected pages with a real principal include the headers.
- `authenticatedUnknownRouteIsDenied` confirms default-deny remains active.
- `incomingRefererIsNotAuthorizationCredential` illustrates that clients can supply arbitrary `Referer` headers to the server; response `Referrer-Policy` does not mean trusting that header for authorization.

These tests call the `RANDOM_PORT` server via `WebTestClient`, checking actual responses produced by the Spring Security chain. Header behavior on 401/403 should also be checked through proxies/gateways in staging, rather than assuming error responses from another layer carry identical headers.

Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**7 test methods** are designed for the project above. This is an **expectation from the code**, not a statement that Gradle tests were actually executed. If a test fails, check dependency versions, web stack type, security chain matching, actual headers, and browser/gateway policies before changing expected values.

### 9.1. Why Not Test Referer with WebTestClient?

`WebTestClient` is an HTTP test client, not a browser engine. It can:
- Send a `Referer` header defined by the test.
- Verify the server returns `Referrer-Policy`.
- Verify the server returns `Permissions-Policy`.

It **does not perform browser navigation, compute `Referer` from document policy, or block camera/geolocation**. Therefore, a test that manually attaches `Referer: https://outside.example/...` and sees that header arrive **does not** prove `Referrer-Policy` failed: the server merely received a client-crafted header.

## 10. Verifying with Browser DevTools

### 10.1. Referrer Policy

An effective test requires two origins (e.g., the app and a request-receiving page you control), a real browser, and appropriate HTTPS. Never put real customer data into URLs.

1. Open the demo app in Chrome/Firefox/Edge and open DevTools → Network.
2. Select the `GET /features` response or target HTML page and check `Response Headers` for `Referrer-Policy: same-origin`.
3. On a page with an internal or external **test environment** link, follow the link and inspect the **request headers of the destination request**. With `same-origin`, referrer is sent on same-origin requests per browser policy and omitted on cross-origin requests per that policy.
4. Change the configuration to `NO_REFERRER`, reload, and verify neither same-origin nor cross-origin requests send `Referer`.
5. Switch to `STRICT_ORIGIN_WHEN_CROSS_ORIGIN` in a test environment and verify HTTP→HTTPS, HTTPS→HTTPS, HTTPS→HTTP, and origin-only vs. full URL where applicable.
6. Use network logs from test endpoints you own; **never use real URLs containing reset tokens, payment codes, or personal emails**.

When checking redirect chains and stylesheet resources, inspect individual requests; browser caches may prevent requests from being re-sent if assets are served from cache.

### 10.2. Permissions Policy

Open `http://localhost:8080/features` in a browser. Localhost is usually treated as a secure context by browsers for APIs requiring one, though this varies by browser/setup. Click "Try geolocation" and "Try camera".

In browsers supporting the policy:
- `geolocation=()` typically causes the callback to report a permission error, often `PERMISSION_DENIED`.
- `camera=()` typically causes `getUserMedia` to reject, often with `NotAllowedError`.
- Do not expect a permission prompt to appear and allow the feature when the policy forbids it.
- If an API is unavailable on the browser/device or the page is not in a secure context, distinguish lack of support from policy denial.

In the DevTools Console, some browsers expose:

```javascript
document.permissionsPolicy?.allowsFeature("geolocation")
```

A `false` return value (if this API is supported and the directive name is active) indicates the feature is blocked by policy. Do not rely solely on this API because support varies and it may be `undefined`. Check response headers, actual API calls, browser console diagnostics, and compatibility tables.

### 10.3. Iframe Cases

If the product uses iframes, test:
- Parent header policy with `geolocation=()` and child iframe with `allow="geolocation"`.
- Parent header `geolocation=(self "https://maps.partner.example")` and matching iframe `allow`.
- A different/unmatched child origin.
- Browsers lacking support for the directive/feature.

Never run iframe tests outside environments where you control the origin and user consent, especially with real camera/microphone/location APIs.

## 11. HTTPS, HSTS, and Reverse Proxies

### 11.1. Response Headers Do Not Replace HTTPS

`Referrer-Policy` controls only one type of source-page disclosure; `Permissions-Policy` restricts browser features. They do not encrypt connections or stop on-path attackers from tampering with responses over insecure HTTP. **Production must use HTTPS** with proper TLS configured at the gateway/reverse proxy.

### 11.2. Conditional HSTS

Spring Security WebFlux provides HSTS by default on **HTTPS responses**, while typically omitting HSTS on insecure HTTP requests. Never test with `curl -i http://localhost` and conclude production HSTS is missing; test real HTTPS endpoints and responses through the proxy.

HSTS does not replace Referrer Policy. HSTS tells the browser to connect only over HTTPS within the policy duration; it does not block the camera API or scrub secret query parameters from URLs.

### 11.3. TLS Termination and Forwarded Headers

If TLS terminates at a load balancer while Spring WebFlux sees an internal HTTP connection, scheme, redirect URLs, and HSTS/cookie security behavior can be affected. Only trust `Forwarded` or `X-Forwarded-*` from trusted reverse proxies, and configure Spring Boot/Framework to match your real infrastructure.

Proxies/CDNs can also overwrite `Referrer-Policy` or `Permissions-Policy`. In staging, compare:
- Headers at the application.
- Headers at the gateway.
- Final headers received by the browser.
- Browser behavior across redirects, static assets, and error pages.

### 11.4. Mixed Content and External Endpoints

An HTTPS page loading insecure HTTP scripts or images may be blocked by the browser or expose other risks. Keep resources on HTTPS, apply suitable CSP (such as `upgrade-insecure-requests` where appropriate), govern third-party dependencies, and avoid tokens in URLs. A strong Referrer Policy does not by itself fix mixed content or JavaScript exfiltration.

## 12. Layered Data-Leakage Controls That Must Work Together

### 12.1. Never Put Secrets in URLs

Avoid:
- `/reset?token=LONG_SECRET` in flows that do not strictly require link tokens; if a link is required, use short-TTL single-use tokens, exchange and clean the URL, set `no-referrer`, and prevent caching/logging.
- `/api?access_token=...`, `/login?password=...`.
- Session IDs placed in URL paths or queries.
- Unnecessary PII in queries, such as full names, national IDs, or medical record numbers.

In OAuth2 Authorization Code flows, callbacks normally receive `code` in the query per standard flow; protect it with `state`/PKCE, process short-lived codes safely, minimize log/referrer exposure, and never confuse `code` with an access token. After processing, redirect to a clean URL so codes do not linger in the address bar longer than necessary.

### 12.2. Cache Control

Account pages and sensitive responses typically use:

```http
Cache-Control: no-store
```

Spring Security WebFlux provides default cache-control headers on responses in the chain, though static resources, gateways, or custom controllers can alter them. Partition cached data by identity/tenant and strictly avoid unpartitioned shared caching. `Referrer-Policy` does not stop browsers/caches from storing URLs or response bodies.

### 12.3. CSP and XSS Prevention

`Permissions-Policy: camera=()` does not stop scripts from reading DOM text and sending it via `fetch`. To limit script execution and exfiltration:
- Use a strict CSP, considering `script-src` nonces/hashes, `connect-src`, `img-src`, `frame-src`, and `frame-ancestors` per use case.
- Escape/sanitize output and never inject untrusted HTML/JS into the DOM.
- Limit third-party scripts and monitor supply-chain/SRI where suitable.
- Avoid writing credentials/tokens into `localStorage` or the DOM unnecessarily, limiting script exposure.

Spring Security cannot guess an appropriate CSP for every app, so CSP is not added universally by default; define explicit policies and test real features.

### 12.4. Cookie Flags and CSRF

`HttpOnly` reduces the chance of JavaScript reading session cookies; `Secure` requires HTTPS; `SameSite` restricts certain cross-site requests. These **complement** but do not replace CSRF tokens. `Referer` is not proof of user authorization, so never use `Referrer-Policy` or incoming `Referer` as an authentication/authorization mechanism.

If an app uses session cookies, unsafe methods still need CSRF protection per the threat model. A `Referrer-Policy` of `no-referrer` legitimately causes some requests to omit `Referer`; never build a custom CSRF guard requiring `Referer` to always be present.

### 12.5. Never Trust Browser Feature Restrictions at the Backend

Permissions Policy does not replace:
- Roles/authorities in Spring Security.
- Tenant/resource permissions at the service/database layer.
- Rate limiting and abuse prevention.
- Server-side endpoint access control.
- Form input validation or API authorization.

Non-browser clients can ignore Permissions Policy. Therefore the backend must protect data independently, never assuming "microphone is blocked in the browser so nobody can upload audio."

### 12.6. Observability and Redaction

Never write full URLs containing secrets into logs, traces, span attributes, or analytics. Design an allowlist:
- HTTP method and normalized route template, never raw sensitive queries.
- Status code, latency, and request ID.
- Security policy version and non-sensitive header names/values for auditing.
- Normalized origin only if genuinely required by business logic.

Mask or strip `Authorization`, `Cookie`, `Set-Cookie`, query credentials, reset codes, and session IDs before logging—including at gateways, APMs, and CDNs.

## 13. Pitfalls and Debugging Scenarios

| Symptom | Possible cause | Resolution |
|---|---|---|
| Curl sees `Referrer-Policy`, yet browser still sends query URL | Browser got different header on source page, policy overridden, same-origin permits full URL, or gateway altered response | Check source document, destination network request, and effective policy |
| Browser sends no Referer cross-origin | `same-origin` or `no-referrer` is active | Expected behavior, not a navigation bug |
| Browser still sends origin cross-origin | Using `strict-origin-when-cross-origin` | That policy permits origin on HTTPS cross-origin; pick `same-origin`/`no-referrer` if stricter privacy is needed |
| Analytics loses referral data | `no-referrer` is too strict for marketing needs | Evaluate requirements; use PII-free campaign IDs, never open `unsafe-url` |
| Camera browser API is not blocked | Browser/feature lacks directive support, header never reached document, or invalid syntax | Verify compatibility, response headers, and document/iframe context |
| Iframe cannot use geolocation despite `allow` | Parent policy does not allowlist the origin | Update parent policy with trusted origin and retest |
| `Permissions-Policy` header missing | Spring Security does not add by default, or request hit another chain | Configure `headers(...permissionsPolicy(...))` on the right chain |
| Policy `camera 'none'` has no effect | Used legacy Feature-Policy syntax | Use `camera=()` in `Permissions-Policy` |
| User still gets a permission prompt | Feature/policy applied improperly, or different API called | Verify supported browsers, headers, secure context, and document |
| WebTestClient tests always pass, yet browser fails to block | Tests only assert header strings | Add manual/automated browser tests on supported browsers |
| HSTS absent on `http://localhost` | HSTS only applies to secure requests per Spring defaults | Test HTTPS through a trusted proxy |
| Security headers missing on 404/gateway responses | Response bypassed chain/writer or overwritten by proxy | Inspect final response; configure at the appropriate boundary |
| `Referrer-Policy` stops server from receiving Referer | Server sees requests **already sent by clients**; response policy governs subsequent browser behavior | Never try to modify incoming headers using a response policy |
| Header is set, yet tokens still leak in server logs | Referrer Policy does not scrub request URLs/logs | Fix URL design and log redaction |
| CSP blocks camera while Permissions Policy does not | CSP does not govern all feature APIs like Permissions Policy | Use the right mechanism for each goal |
| Camera blocked, yet data still sent via fetch | Permissions Policy is not a network exfiltration firewall | Enforce CSP, XSS prevention, data protection, and authorization |
| Multiple duplicate/overwriting response headers | App and gateway both configure them | Define precedence, unify policy, test final values |

### 13.1. Debugging Along the Response Path

```text
ServerHttpSecurity.headers(...) configures writers
       |
       v
SecurityWebFilterChain processes request
       |
       v
Application / gateway / CDN writes response
       |
       v
Browser receives Referrer-Policy + Permissions-Policy
       |
       v
Browser enforces policies by context and support level
       |
       v
Subsequent request / feature API call
       |
       v
Observe actual Referer or feature API error
```

Do not inspect one server log line and conclude browsers obeyed the policy. To verify referrer behavior, inspect the **subsequent request generated by the browser**. To verify Permissions Policy, observe actual browser feature gating inside the exact top-level document or iframe.

## 14. Exercises with Answers

### Exercise 1 — Two Header Names

An engineer adds `Referrer-Policy: same-origin` and sends `Referer: https://outside.example/path` via curl. The server still sees the incoming `Referer`. Is the config broken?

**Answer:** No. `Referrer-Policy` in responses only guides browsers on sending `Referer` in subsequent requests. Curl sends whatever header the caller specifies and does not enforce browser document policies.

### Exercise 2 — Sensitive URLs and strict-origin-when-cross-origin

Source page `https://app.example/reset?ticket=abc` navigates to `https://docs.example/help`. Under `strict-origin-when-cross-origin`, what does a typical browser send?

**Answer:** Origin only (`https://app.example/`), omitting path and query on cross-origin HTTPS. Still, avoid secrets in URLs because browser history, logs, and same-origin links can still see them.

### Exercise 3 — Does same-origin Hide All Queries?

Page `https://app.example/account?token=abc` navigates to `https://app.example/help` under `same-origin`. Can the token travel in `Referer`?

**Answer:** Yes, because the policy permits sending the source URL on **same-origin** requests. If queries contain secrets, use `no-referrer` and redesign the URL so it carries no secrets.

### Exercise 4 — Browser Default vs. Spring Security Default

Why might a site not using Spring Security send cross-site origins, whereas WebFlux 6.5 defaults send no `Referer`?

**Answer:** Browsers typically default to `strict-origin-when-cross-origin` when no header is received. Spring Security WebFlux 6.5 documents emitting `Referrer-Policy: no-referrer` by default, enforcing a stricter policy.

### Exercise 5 — Geolocation in an Iframe

The parent response sends `Permissions-Policy: geolocation=()`. A child iframe has `allow="geolocation"`. Can the iframe grant itself location access?

**Answer:** No. Iframe `allow` cannot override a restrictive parent policy. To allow a trusted iframe to use geolocation, the parent policy must allowlist its origin alongside matching iframe `allow`, plus user consent and browser support.

### Exercise 6 — Permissions Policy Parentheses

Is `Permissions-Policy: microphone 'none'` valid modern syntax?

**Answer:** No. That resembles legacy `Feature-Policy` syntax. The modern header uses `Permissions-Policy: microphone=()` to disable it.

### Exercise 7 — Does Omitting the Header Block the Camera by Default?

**Answer:** No. Each directive has its own default allowlist and browser support varies. Camera and geolocation often default to `self` in browsers; declare the policy explicitly if you want them locked down.

### Exercise 8 — `camera=()` Is Set, Yet JS Reads Account Balances

Does Permissions Policy prevent JavaScript-based exfiltration?

**Answer:** No. It restricts the camera feature, not arbitrary network requests or DOM access. You need CSP, XSS defense, authorization, data minimization, and avoiding untrusted scripts alongside sensitive data.

### Exercise 9 — What Must Be Tested Beyond Header Strings?

**Answer:** Browser request `Referer` across same/cross-origin, HTTPS downgrade behavior, blocked API calls, iframe delegation, supported browsers, redirects/gateways/static resources, and error responses. `WebTestClient` checks response headers only.

### Exercise 10 — Policy for a Web Video-Calling App

If an app genuinely provides video calling, should it set `camera=(), microphone=()`?

**Answer:** No. That breaks the core feature. Use `camera=(self), microphone=(self)` or a verified origin allowlist if iframes are needed, and test real permission prompts/user consent.

### Exercise 11 — Why Not Use Referer for Authentication?

**Answer:** `Referer` can be legitimately omitted by browsers and arbitrarily forged by clients. It verifies neither identity nor permissions. Use properly designed Spring Security authentication, authorization, and CSRF protection.

### Exercise 12 — Why Keep Secrets Out of URLs Even with no-referrer?

**Answer:** `Referrer-Policy` controls only one header sent by browsers. Secrets in URLs can still end up in logs, browser history, extensions, crash reports, screenshots, analytics, and caches.

### Exercise 13 — No HSTS Over HTTP

Curling `http://localhost` shows no `Strict-Transport-Security`. Should you disable headers to "fix" it?

**Answer:** No. HSTS is normally emitted only on secure requests and only has meaning over HTTPS. Check staging/production HTTPS, proxy TLS termination, and forwarded headers first.

### Exercise 14 — Is Same-Origin Telemetry Worth It?

An app has many internal same-origin documents and analytics wants source page paths. Can `same-origin` be chosen over `no-referrer`?

**Answer:** Yes when business needs justify it and URLs carry no sensitive data, accepting that same-origin paths/queries may be sent. For recovery/auth/payment flows, keep `no-referrer` or split policies for sensitive areas, checking proxy overrides and consistency across responses.

### Exercise 15 — Iframe Feature vs. Backend Role

An iframe is allowed geolocation by policy, while the server HTTP API requires role `ADMIN`. Can the iframe automatically access the admin API?

**Answer:** No. Browser feature permissions do not create an `Authentication` or `ROLE_ADMIN`. The backend must still authenticate and authorize independently.

## 15. Production Deployment Checklist

- [ ] Classify sensitive pages/URLs; avoid credentials/PII in paths and queries.
- [ ] Know both the browser default referrer policy and what Spring Security WebFlux actually emits.
- [ ] Choose `no-referrer` for sensitive pages unless clearly justified; never use `unsafe-url`.
- [ ] If using `same-origin`, accept that same-origin source URLs including paths/queries may be sent.
- [ ] Verify `Referrer-Policy` appears on target HTML documents/responses, including through proxies/CDNs.
- [ ] Pick Permissions Policy matching product features without breaking required camera/location features.
- [ ] Use modern syntax `feature=()`, `feature=(self)`, `feature=("https://trusted...")`, comma-separated.
- [ ] Ensure parent policies and `iframe allow` align consistently without unnecessary wildcards.
- [ ] Test browser compatibility and user permission prompts; header support is uneven.
- [ ] Never confuse Permissions Policy with CSP, CORS, authentication, or CSRF.
- [ ] Use WebFlux's `ServerHttpSecurity.headers(...)`/`SecurityWebFilterChain`, not Servlet APIs.
- [ ] Never disable all default security headers when only adding/adjusting one directive.
- [ ] Configure HTTPS, HSTS, TLS termination/forwarded headers, and Secure cookies per environment.
- [ ] Implement CSP, XSS prevention, third-party script limits, and `frame-ancestors` per threat model.
- [ ] Apply appropriate cache control on private account/data pages; prevent shared CDN caching of sensitive data.
- [ ] Redact queries, `Authorization`, `Cookie`, and tokens in logs/traces/analytics.
- [ ] Never treat incoming `Referer` as a credential or sole CSRF verification.
- [ ] Write unit/integration tests for server header values and browser tests for actual behavior.
- [ ] Inspect redirects, 401/403, 404, static assets, multiple security chains, and gateway error responses.
- [ ] Review changes whenever relaxing/tightening policies to prevent broken features or privacy regressions.

## 16. Technical Summary

```text
Referrer-Policy (response header):
  Controls the Referer (request header) that the browser creates next.

no-referrer:
  Does not disclose source page via Referer.

same-origin:
  Allows internal same-origin Referer; sends nothing cross-origin.

strict-origin-when-cross-origin:
  Full URL same-origin, origin-only cross-origin HTTPS,
  nothing on HTTPS -> HTTP downgrade.

Browser default:
  typically strict-origin-when-cross-origin if no policy is present.

Spring Security WebFlux 6.5 default:
  documented as Referrer-Policy: no-referrer.

Permissions-Policy:
  geolocation=()     -> blocked
  camera=()          -> blocked
  microphone=()      -> blocked
  geolocation=(self) -> allowed for app's own origin within policy bounds

Spring WebFlux config:
  ServerHttpSecurity.headers(...)
    .referrerPolicy(...policy(...))
    .permissionsPolicy(...policy("..."))

Do not assume:
  Header emitted == browser enforced every directive.
  No Referer == legitimate / illegitimate request.
  Permissions Policy == backend authentication/authorization.
  Header policy == no URL/log/DOM/script leaks.
```

**Core message:** `Referrer-Policy` limits disclosure of **source-page information**, while `Permissions-Policy` restricts access to **browser capabilities**. Both are pieces of defense-in-depth: HTTPS/HSTS, secret-free URLs, CSP, XSS prevention, cookie flags, cache control, log redaction, and Spring Security authorization must be designed together.

## 17. Official References

- [Spring Security 6.5 — WebFlux Security Response Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html)
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — HeaderSpec Referrer Policy](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.ReferrerPolicySpec.html)
- [Spring Security — HeaderSpec Permissions Policy](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.PermissionsPolicySpec.html)
- [Spring Security 6.5 — ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/header/ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy.html)
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy)
- [MDN — Referer request header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referer)
- [MDN — Permissions-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy)
- [MDN — Permissions Policy Guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy)
- [MDN — Geolocation directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/geolocation)
- [MDN — Camera directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/camera)
- [OWASP — Secure Headers Project](https://owasp.org/www-project-secure-headers/)
- [OWASP — HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
