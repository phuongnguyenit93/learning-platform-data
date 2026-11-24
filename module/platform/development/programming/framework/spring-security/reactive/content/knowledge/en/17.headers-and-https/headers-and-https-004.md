# X-Frame-Options, CSP frame-ancestors, and Clickjacking Protection

## Learning Objectives

This lesson belongs to **Headers and HTTPS** in **Spring Security reactive (Spring WebFlux)**. After this lesson, you can:

- Explain **clickjacking/UI redressing** and the role of embedding sensitive pages via `<iframe>`, even when the attacker cannot read the iframe's DOM.
- Clearly distinguish `X-Frame-Options: DENY`, `X-Frame-Options: SAMEORIGIN`, and the `Content-Security-Policy: frame-ancestors ...` directive.
- Know that `frame-ancestors` controls **who may embed your page**, unlike `frame-src` (which frames your page may load); understand nested iframes, origins, and precedence when both headers are present.
- Safely configure `ServerHttpSecurity.headers(...)` in Spring Security WebFlux, keeping `DENY` by default for sensitive pages and creating controlled exceptions for pages that genuinely require embedding.
- Understand that `frame-ancestors` cannot be set via HTML `<meta>` and that `default-src` does not provide a fallback; distinguish **enforcing** CSP policies from **Report-Only**.
- Build a **Java 17 + Spring Boot WebFlux** example using multiple `SecurityWebFilterChain` beans to separate embeddable pages from non-embeddable pages; run `curl`, `WebTestClient`, and **browser** checks.
- Identify the limitations of XFO/CSP against XSS, CSRF, CORS, third-party cookies, reverse proxies, and older browsers; avoid "fixing iframe errors" by disabling all security headers.

> **Use reactive APIs only.** WebFlux uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and `XFrameOptionsServerHttpHeadersWriter.Mode`. Do not copy Servlet's `HttpSecurity.headers().frameOptions().sameOrigin()` because the DSL and APIs differ.

## 1. Clickjacking: Users Click a Real Interface by Mistake

**Clickjacking** occurs when an attacker places a **real page** from a victim application inside an `iframe` or other embeddable container, then uses CSS/overlays so the user clicks a spot they think belongs to the attacker's UI, while actually clicking a button on the victim's page.

Conceptual example:

~~~text
User's browser
  |
  +-- Attacker's page: https://untrusted.example.test
         |
         +-- Displays a game / "Claim Prize" button
         |
         +-- Transparent / positioned iframe:
               https://bank.example.test/settings
                    |
                    +-- Real button "Enable fund transfers"
                        ^
                        |
              User clicks here by mistake
~~~

The bank page remains a **different origin** from the attacker. The Same-Origin Policy (SOP) normally blocks the attacker's JavaScript from reading the iframe's DOM, yet SOP **does not prohibit embedding** the page and **does not prevent users from clicking** embedded content. If the browser automatically sends session cookies to the iframe under its cookie policy, the real page can render under the logged-in user's identity.

That is why you must control the **embeddability** of pages with sensitive actions. Variants include hidden/overlaid buttons, deceptive navigation, mobile touch actions, or drag-and-drop; it is not limited to an `iframe` with `opacity:0`.

### 1.1. Conditions Creating Risk

A clickjacking scenario typically involves multiple factors:

1. The target page can render inside a frame on an untrusted origin.
2. The user can interact with the target UI, sometimes with an existing session/cookie.
3. The attacker tricks the user into interacting in a way that lands on the frame area.
4. The action has consequences and lacks an appropriate additional confirmation layer.

Not every iframe is dangerous: public pages, preview cards, or partner widgets designed for embedding can be legitimate use cases. For admin, payment, contact-update, permission-grant, or transaction-confirmation pages, **forbidding embedding by default** is the safe choice.

### 1.2. Where Do XFO and CSP Operate?

Both `X-Frame-Options` and `CSP frame-ancestors` are **HTTP response headers on the page being embedded**, not headers on the parent page. The browser checks the iframe's response to decide whether to render that document under the current frame tree.

~~~text
GET https://app.example.test/account/settings
        |
        v
HTTP response from app.example.test:
  X-Frame-Options: DENY
  Content-Security-Policy: frame-ancestors 'none'
        |
        v
Browser refuses to render the page inside an iframe
hosted by an attacker on another origin
~~~

This diagram shows expected behavior in compliant browsers; `curl` only shows whether headers are emitted and does not enforce framing rules. Full verification requires testing in supported browsers.

## 2. X-Frame-Options: Few Choices, High Impact

`X-Frame-Options` (XFO) is an HTTP response header dedicated to preventing embedding/clickjacking. Recommended values:

~~~http
X-Frame-Options: DENY
~~~

or:

~~~http
X-Frame-Options: SAMEORIGIN
~~~

| Value | Meaning | When to use |
|---|---|---|
| `DENY` | Page cannot be embedded, **even by same-origin frames**. | Admin, transactions, settings, API/web UIs that never need iframes. |
| `SAMEORIGIN` | Allows embedding when ancestor frames satisfy **same-origin** rules as applied by modern browsers. | Apps that genuinely use internal same-origin iframes. |
| `ALLOW-FROM uri` | **Obsolete**, unsupported by many modern browsers; browsers may ignore XFO completely. | **Do not use.** Use CSP `frame-ancestors` for partner origins. |

### 2.1. DENY Does Not Only Block Unknown Sites

Suppose `https://app.example.test/internal/report` returns:

~~~http
X-Frame-Options: DENY
~~~

Then both parent `https://evil.example.test` **and** parent `https://app.example.test` cannot embed this document in an iframe (in browsers enforcing XFO properly).

Do not choose `DENY` if your system genuinely uses a same-origin iframe for a required screen; identify requirements first. Conversely, do not relax the entire application to `SAMEORIGIN` when only one route needs an iframe.

### 2.2. SAMEORIGIN Means Same Origin, Not Same Site

An origin consists of **scheme + hostname + port**:

| Child page | Parent page | Same-origin? |
|---|---|---|
| `https://app.example.test/page` | `https://app.example.test/dashboard` | Yes |
| `https://app.example.test/page` | `https://admin.example.test` | No (different subdomain) |
| `http://localhost:8080/page` | `http://localhost:3000` | No (different port) |
| `https://app.example.test/page` | `http://app.example.test` | No (different scheme) |

Do not confuse cookie `SameSite` (**same-site**) with XFO/CSP **same-origin**. Two subdomains under one registrable domain can be same-site while still rejected by `SAMEORIGIN`.

### 2.3. ALLOW-FROM Is Not a Solution for Partners

The following is an **anti-example**:

~~~http
X-Frame-Options: ALLOW-FROM https://partner.example.test
~~~

Many modern browsers **do not understand** the `ALLOW-FROM` directive; some ignore XFO entirely, leaving the page embeddable more broadly than intended. Never use XFO as a partner allowlist. Use CSP:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://partner.example.test
~~~

When compatibility with old browsers lacking CSP support is needed, consider a **fail-closed** policy (keep XFO `DENY`/`SAMEORIGIN` and accept that old browsers cannot embed it) or a separate public widget design. Never drop controls just so an iframe works on every browser.

### 2.4. XFO Must Be an HTTP Response Header

Wrong:

~~~html
<meta http-equiv="X-Frame-Options" content="DENY">
~~~

Browsers **do not enforce XFO from meta tags**. The header must be sent by the application, gateway, or web server in the actual response. If a route returns a redirect to another HTML page, verify headers on the **final HTML response** and all sensitive routes, not just the initial redirect.

## 3. CSP frame-ancestors: More Flexible Embedding Policy

CSP (Content Security Policy) supports the `frame-ancestors` directive to specify which **ancestor origins may embed the current document** via `frame`/`iframe`/`object`/`embed`.

Three important configurations:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

~~~http
Content-Security-Policy: frame-ancestors 'self'
~~~

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test
~~~

| Directive | Meaning |
|---|---|
| `frame-ancestors 'none'` | Forbids iframe embedding from all origins, including itself. |
| `frame-ancestors 'self'` | Allows only same-origin ancestors. |
| `frame-ancestors 'self' https://portal.example.test` | Allows same-origin ancestors **or** the listed portal. |
| `frame-ancestors https://widget-host.example.test:8443` | Allows an explicit scheme/host/port origin, not other origins. |
| No `frame-ancestors` | No embedding restriction **from this directive**; XFO or another policy may still block. |

### 3.1. 'none' and 'self' Require Single Quotes

Two key keywords must be written with exact syntax:

- `'none'`: no ancestors permitted.
- `'self'`: ancestors sharing the document's origin.

Writing `frame-ancestors none` or `frame-ancestors self` **is incorrect syntax** for keywords; if the browser fails to parse the source expression, the policy may not behave as intended. Follow standard CSP syntax and test the actual response string.

### 3.2. default-src Does Not Fall Back to frame-ancestors

This is a particularly dangerous mistake:

~~~http
Content-Security-Policy: default-src 'none'
~~~

`default-src 'none'` restricts **many subresource types**, yet **provides no fallback for frame-ancestors**. A response lacking `frame-ancestors` can still be embedded by other websites unless XFO or another embedding policy is present.

To forbid embedding, write explicitly:

~~~http
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
~~~

Similarly, `script-src 'none'`, `object-src 'none'`, and `base-uri 'none'` do not substitute for `frame-ancestors`, even though they are valid parts of an overall CSP.

### 3.3. frame-ancestors Differs from frame-src and child-src

Two directions of control:

~~~text
Document A (parent)
  |
  +-- <iframe src="https://B.example.test/page">

Response of A:
  frame-src https://B.example.test
  -> May A load B as a child frame?

Response of B:
  frame-ancestors https://A.example.test
  -> Does B allow A to embed it?
~~~

| Directive | Set on? | Question answered |
|---|---|---|
| `frame-src` | **Parent** response | Which sources may the parent load into iframes? |
| `child-src` | **Parent** response (CSP fallback) | Allowed child browsing contexts/workers per CSP rules. |
| `frame-ancestors` | **Child** response being embedded | Which ancestors are permitted to embed the child page? |

Setting `frame-src 'self'` on the child page **does not stop** another website from embedding the child. If both parent and child define policies, **both sides** must permit it for the iframe to render.

### 3.4. Nested Iframes: Every Ancestor Is Checked

Suppose:

~~~text
Top-level: https://partner.example.test
  |
  +-- iframe: https://shell.example.test
          |
          +-- iframe: https://app.example.test/embed/card
~~~

If `app.example.test/embed/card` has:

~~~http
Content-Security-Policy: frame-ancestors https://partner.example.test
~~~

**That is insufficient** if `shell.example.test` is also an ancestor and missing from the allowlist. `frame-ancestors` checks **all ancestor frames**; if any ancestor fails to match, the browser aborts rendering the child page.

If nesting is genuinely required, list all authorized origins explicitly:

~~~http
Content-Security-Policy: frame-ancestors https://partner.example.test https://shell.example.test
~~~

Even then, rendering is not guaranteed if the parent has a blocking `frame-src`, the browser blocks mixed content, or cookies/sessions are unavailable. Review **the entire ancestor chain**, not just the top-level page.

### 3.5. frame-ancestors Does Not Work in Meta Tags

Wrong:

~~~html
<meta http-equiv="Content-Security-Policy"
      content="frame-ancestors 'none'">
~~~

The `frame-ancestors` directive **is not supported** in CSP meta tags; the browser needs this policy early when deciding whether to create/render the frame. Always emit it via an **HTTP response header** on the protected document.

Just like XFO, you cannot embed the policy inside HTML after the frame has already been created and expect it to block rendering.

### 3.6. CSP Enforcement vs. Report-Only

CSP has two headers:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

and:

~~~http
Content-Security-Policy-Report-Only: script-src 'self'; report-uri /csp-report
~~~

- `Content-Security-Policy` is an **enforced** policy.
- `Content-Security-Policy-Report-Only` supports **collecting reports** for compatible policies and **does not block** violations instead of an enforced policy.

Specifically, `frame-ancestors` is a navigation control and has report-only limitations across browsers/specs; **never expect report-only frame-ancestors to prevent clickjacking**. For protection, enable the enforcing header and test in a real browser. When trialing new script/style CSP rules in Report-Only, do not accidentally move **anti-framing rules** to Report-Only alone.

## 4. When Both X-Frame-Options and frame-ancestors Exist

Spring Security WebFlux **sends `X-Frame-Options: DENY` by default**. The framework **does not add CSP automatically**, since CSP depends on application requirements. When you configure `frame-ancestors`, responses may include **both**:

~~~http
X-Frame-Options: DENY
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test
~~~

Per the CSP standard and **modern browser** behavior supporting enforcing `frame-ancestors`, this CSP directive **takes precedence**, and XFO is ignored for framing decisions on that response. Thus the listed portal can embed the page in modern browsers **even though XFO remains DENY**.

Meanwhile, **older browsers** that do not understand `frame-ancestors` fall back to XFO, resulting in **blocking embedding**. This is *fail closed*: the partner might not see the widget in legacy browsers, but you never open the site to arbitrary origins.

### 4.1. Common Combinations

| X-Frame-Options | CSP frame-ancestors (enforcing) | Modern browser | Legacy XFO-only browser |
|---|---|---|---|
| `DENY` | Absent | Blocks all frames | Blocks all frames |
| `SAMEORIGIN` | Absent | Same-origin only | Same-origin only per implementation |
| `DENY` | `'none'` | Blocks all frames | Blocks all frames |
| `DENY` | `'self'` | Allows same-origin | Blocks all frames |
| `DENY` | `'self' https://portal.example.test` | Allows listed ancestors | Blocks all frames |
| No XFO | `'self' https://portal.example.test` | Allows listed ancestors | May have **no protection** |
| `ALLOW-FROM https://...` | Absent | Unreliable | Varies across browsers |

**Risk-based recommendation:** For security-critical pages, use `DENY` and `frame-ancestors 'none'`. For widgets that genuinely require external embedding, use a **specific, minimally scoped** CSP allowlist, retain XFO as a fail-closed fallback on old browsers, or provide an alternative if legacy compatibility is mandatory.

### 4.2. Should XFO Be Disabled When Using CSP?

There is no rule saying "adding CSP requires disabling XFO." Disabling XFO:

~~~java
// Only a configuration snippet for a chain requiring careful review:
http.headers(headers -> headers
    .frameOptions(frame -> frame.disable())
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "frame-ancestors 'self' https://portal.example.test")));
~~~

can leave legacy browsers without CSP support **with zero framing protection**. Choose this only after evaluating browser support, endpoint scope, frame data sensitivity, and business requirements. Never disable `headers(...)` globally just to make one partner iframe work.

### 4.3. Multiple Content-Security-Policy Headers

If both a CDN/gateway and Spring Security emit `Content-Security-Policy`, modern browsers typically **enforce multiple policies simultaneously**; policies combine to be **no more permissive**. Example:

~~~http
Content-Security-Policy: frame-ancestors 'none'
Content-Security-Policy: frame-ancestors https://portal.example.test
~~~

You cannot assume the second header "overrides" the first to allow the portal; the first policy still blocks it. Establish clear single-source ownership/coordination between gateway and application to avoid conflicting duplicate CSP headers. Likewise, inconsistent duplicate XFO headers can yield unpredictable browser behavior.

### 4.4. Do Not Rely on the Parent's Response to Mask Risk

A parent setting `frame-src 'self'` does not prevent an attacker on another origin from embedding your child page. To prevent clickjacking, set **`frame-ancestors` on the child page's response**. Managing only the parent cannot ensure external child pages protect themselves properly.

## 5. Spring Security Reactive: Which Headers to Configure?

In Spring Security WebFlux, the relevant configuration lives in:

~~~java
ServerHttpSecurity http = ...; // builder provided by Spring
http.headers(headers -> headers
    .frameOptions(frameOptions -> frameOptions
        .mode(XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN))
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("frame-ancestors 'self'")));
~~~

This is an **illustrative DSL snippet**. Import the enum:

~~~java
import org.springframework.security.web.server.header
    .XFrameOptionsServerHttpHeadersWriter;
~~~

In Java, the `import` statement must be on **one continuous line** when pasted into a file:

~~~java
import org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter;
~~~

### 5.1. Keep Default DENY When Embedding Is Not Required

Spring Security WebFlux emits XFO `DENY` by default. If your app needs no iframes, you often **do not need to change XFO**; you can add CSP for defense in depth:

~~~java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("default-src 'self'; frame-ancestors 'none'")))
~~~

Here `default-src 'self'` is a minimal subresource policy; `frame-ancestors 'none'` is what prevents embedding. In real applications, design a **complete CSP** covering scripts, styles, images, connect, fonts, etc. Never copy `default-src 'self'` expecting every SPA to work without exceptions.

### 5.2. When Same-Origin Iframes Are Needed

You can set:

~~~java
.headers(headers -> headers
    .frameOptions(frame ->
        frame.mode(XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN))
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("frame-ancestors 'self'")))
~~~

In WebFlux, the method is `mode(...)`; do not use Servlet's `sameOrigin()`. Test both parent and child: if the parent has `frame-src 'none'`, embedding still fails even when the child allows it.

### 5.3. When One Specific Page Must Be Embedded by a Partner

Rather than loosening the whole site, create a dedicated policy for `/embed/**`:

~~~java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; " +
            "frame-ancestors 'self' https://portal.example.test")))
~~~

This is a snippet, not a full security chain. Default XFO `DENY` may still be sent; modern browsers follow the CSP allowlist, while old browsers fail closed. Always **review embedded pages to ensure they contain no sensitive actions**, even when the partner is trusted.

### 5.4. Why Multiple SecurityWebFilterChain Beans Are Useful

The first matching `SecurityWebFilterChain` bean wins; without splitting chains, configuring a broad CSP everywhere makes it easy to accidentally expose login, admin, or payment pages to iframes. When you want **different response headers per path**, multiple chains with `securityMatcher(...)` and `@Order` keep configuration readable.

Structure:

~~~text
GET /embed/card
    -> chain @Order(1), matcher /embed/**
    -> CSP frame-ancestors 'self' http://localhost:3000
    -> public demo widget

GET /public/page or /api/me
    -> chain @Order(2), catch-all
    -> CSP frame-ancestors 'none'
    -> default X-Frame-Options DENY
~~~

**Warning:** Each request uses only the first matching chain. The `/embed/**` chain must define its own appropriate authorization—never apply `permitAll()` to confidential data just to allow framing. In the demo, `/embed/card` is a stateless public resource with no sensitive operations.

## 6. Runnable Java 17 Demo: Blocked Frame vs. Partner-Allowed Frame

The example uses **Java 17**, **Spring Boot 3.5.16**, Spring WebFlux, and Boot-managed Spring Security. Spring Boot 3.5.16 is the final OSS release on the 3.5 line; the demo pins this stable release so learners can reproduce the exercise consistently. **Production apps should stay on a supported, security-patched line** (e.g., Spring Boot 4.x with corresponding API updates) rather than staying on the demo version indefinitely.

Goals:

- `GET /public/page` returns public HTML, yet **forbids iframes from everywhere**.
- `GET /embed/card` returns widget HTML **containing no sensitive data**, embeddable by **the backend's own origin** and the demo frontend origin `http://localhost:3000`.
- `GET /api/me` requires HTTP Basic login and returns the username (verifying the security chain still protects APIs).
- Responses keep **default XFO DENY on both chains**; each chain's CSP differs. CSP-capable browsers prioritize `frame-ancestors`; legacy browsers may block the widget too — failing closed.
- Page `ui/index.html` runs on port 3000 to show which iframe renders. You can also test port 3001 to simulate an unauthorized origin.

### 6.1. Project Structure

~~~text
webflux-frame-security-demo/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/java/example/FrameSecurityDemo.java
│   └── test/java/example/FrameSecurityIntegrationTest.java
└── ui/
    └── index.html
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'webflux-frame-security-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Requires JDK 17+ and Gradle/Wrapper compatible with Spring Boot 3.5. Do not add Servlet `spring-boot-starter-web` to the demo since this lesson uses reactive security. In your IDE, keep `package example` aligned with the folder path.

### 6.2. Complete WebFlux Application

File `src/main/java/example/FrameSecurityDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class FrameSecurityDemo {

    public static void main(String[] args) {
        SpringApplication.run(FrameSecurityDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Local demo only; never use {noop} passwords in production.
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(learner);
    }

    // Only /embed/** carries the policy allowing partner iframes.
    @Bean
    @Order(1)
    SecurityWebFilterChain embedChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/embed/**"))
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().permitAll())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; " +
                    "frame-ancestors 'self' http://localhost:3000")))
            .build();
    }

    // Catch-all still requires login for non-public URLs.
    @Bean
    @Order(2)
    SecurityWebFilterChain defaultChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; frame-ancestors 'none'")))
            .build();
    }

    @RestController
    static class Pages {

        @GetMapping(value = "/public/page",
                    produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> blockedPage() {
            return Mono.just(
                "<!doctype html><html lang=\"en\">" +
                "<head><meta charset=\"UTF-8\">" +
                "<title>Non-embeddable page</title></head>" +
                "<body><h1>This page cannot be embedded</h1></body>" +
                "</html>");
        }

        @GetMapping(value = "/embed/card",
                    produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> embedCard() {
            return Mono.just(
                "<!doctype html><html lang=\"en\">" +
                "<head><meta charset=\"UTF-8\">" +
                "<title>Public card</title></head>" +
                "<body><h2>Demo card allowed to be embedded</h2>" +
                "<p>No sensitive actions.</p></body></html>");
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "username", principal.getName()));
        }
    }
}
~~~

**Analyzing the key lines:**

1. `@EnableWebFluxSecurity` and two `SecurityWebFilterChain` beans let Spring Security choose the chain by URL.
2. `@Order(1)` with `PathPatternParserServerWebExchangeMatcher("/embed/**")` is a **specific** matcher; it applies only to the widget. The `@Order(2)` bean has no matcher and acts as a **catch-all**.
3. `embedChain` uses `anyExchange().permitAll()` **only because all `/embed/**` demo content is designed to be public with no side effects**. If `/embed/**` contains user data, do not copy this policy.
4. `defaultChain` exposes only `/public/**`; `/api/me` requires HTTP Basic authentication.
5. `.headers(...contentSecurityPolicy(...))` sets an **enforcing CSP**, not `reportOnly()`. One chain specifies `frame-ancestors 'none'`, the other `'self' http://localhost:3000`.
6. Spring Security reactive **still emits XFO DENY by default** because `frameOptions` is not disabled. Modern browsers apply CSP `frame-ancestors` over XFO; old browsers reading only XFO may block the widget too.
7. `default-src 'self'` protects subresource loading in the demo; `frame-ancestors` itself decides whether the page can be embedded.
8. Both HTML pages use no inline JS/CSS or third-party resources, so they work under `default-src 'self'`. Real applications must craft a full CSP rather than pasting this and breaking script/style dependencies.
9. `/api/me` uses the Spring Security principal, never trusting a client-supplied user header. Basic credentials `learner:demo-pass` are only for local HTTP testing without TLS.
10. The critical outputs are the **actual HTTP headers**; the code does not render a "blocked" page when embedding fails, as the browser makes that decision.

### 6.3. Iframe Test Page on Origin http://localhost:3000

File `ui/index.html`:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport"
        content="width=device-width, initial-scale=1">
  <title>Test frame-ancestors</title>
</head>
<body>
  <h1>Clickjacking Protection Test</h1>
  <p>Parent: check the current origin in the address bar.</p>

  <h2>Widget allowed from localhost:3000</h2>
  <iframe
    title="Allowed widget"
    src="http://localhost:8080/embed/card"
    width="520" height="140"></iframe>

  <h2>Page blocked from embedding on any origin</h2>
  <iframe
    title="Blocked page"
    src="http://localhost:8080/public/page"
    width="520" height="140"></iframe>

  <p>Check DevTools Console/Network to see the
     frame-ancestors error on the blocked page.
     The failed iframe may show blank or a browser notice.</p>
</body>
</html>
~~~

The parent page **sets no `frame-src` CSP of its own** so the demo focuses on verifying the policy emitted by the backend on port 8080. In production, the parent should also define a `frame-src` CSP restricting allowed child frames.

### 6.4. Running the Application

Terminal 1, in the project directory:

~~~bash
gradle bootRun
~~~

If using a Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

Terminal 2, in the `ui/` directory, with Python 3:

~~~bash
python -m http.server 3000
~~~

Open:

~~~text
http://localhost:3000/
~~~

**Expected in modern browsers:**

- The first frame loads `/embed/card` and displays "Demo card allowed to be embedded".
- The second frame requests `/public/page` but **does not render the document** due to CSP `frame-ancestors 'none'` (and default XFO DENY).
- Browser Console logs a frame rejection message referencing CSP/XFO; exact wording varies across browsers.
- Do not expect Chrome/Firefox/Safari to display the exact same error UI; what matters is **refusing to render the protected page**.

To test an **unauthorized** origin, stop the Python server in the UI terminal and run:

~~~bash
python -m http.server 3001
~~~

Open `http://localhost:3001/`: now the parent origin is **localhost:3001**, which is not in `/embed/card`'s `frame-ancestors 'self' http://localhost:3000`. Expect **both iframes to be blocked** in CSP-supporting browsers. No backend change is required for this test; the **different port** makes it a different origin.

### 6.5. Inspecting Headers with curl

With the backend running on `localhost:8080`:

~~~bash
# Default page blocks all embedding.
curl -i http://localhost:8080/public/page

# Widget has an exception for origin localhost:3000.
curl -i http://localhost:8080/embed/card

# API still requires authentication, unaffected by embedChain's permitAll.
curl -i http://localhost:8080/api/me

# Valid Basic credentials for /api/me.
curl -i -u learner:demo-pass http://localhost:8080/api/me
~~~

Use `curl.exe` in Windows PowerShell if `curl` is aliased. `-u` contains demo credentials only; never put real passwords in command lines/shell history or send Basic auth over unencrypted networks.

**Expected header excerpt from `/public/page`:**

~~~http
HTTP/1.1 200 OK
Content-Type: text/html
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
~~~

**Expected header excerpt from `/embed/card`:**

~~~http
HTTP/1.1 200 OK
Content-Type: text/html
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; frame-ancestors 'self' http://localhost:3000
~~~

Both excerpts show only the relevant lines, not the entire HTTP response. `Content-Type` may include a charset, and HTTP protocol version/Date/Cache-Control/other system headers vary by runtime. XFO `DENY` on the widget **does not contradict the CSP intent** in modern browsers: enforced CSP takes precedence; in legacy browsers, the widget may not render.

**You cannot conclude browsers block clickjacking from curl alone.** Curl does not render iframes or enforce CSP/XFO; it only confirms the backend emits the headers.

## 7. Testing Spring WebFlux with WebTestClient

File `src/test/java/example/FrameSecurityIntegrationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FrameSecurityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicPageBlocksAllEmbedding() {
        client.get().uri("/public/page")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_HTML)
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY")
            .expectHeader().valueContains(
                "Content-Security-Policy",
                "frame-ancestors 'none'");
    }

    @Test
    void embedCardAllowsOnlyNamedAncestorsInCsp() {
        client.get().uri("/embed/card")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_HTML)
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY")
            .expectHeader().valueContains(
                "Content-Security-Policy",
                "frame-ancestors 'self' http://localhost:3000");
    }

    @Test
    void privateApiStillChallengesAnonymous() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(
                HttpHeaders.WWW_AUTHENTICATE)
            .expectHeader().valueContains(
                "Content-Security-Policy",
                "frame-ancestors 'none'");
    }

    @Test
    void authenticatedApiIsStillFrameProtected() {
        client.get().uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("learner", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY")
            .expectHeader().valueContains(
                "Content-Security-Policy",
                "frame-ancestors 'none'")
            .expectBody()
            .jsonPath("$.username").isEqualTo("learner");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

If the project uses a wrapper, run `./gradlew test` or `gradlew.bat test`. With the configuration provided, all four tests **are expected to pass**. These are integration tests confirming **response headers and HTTP authorization**, not browser rendering tests; real iframe behavior must be verified per section 6.4 on supported browsers.

### 7.1. Why Assert XFO on the Embeddable Page?

It highlights an easily misunderstood behavior: even though `/embed/card`'s CSP allows `http://localhost:3000`, Spring Security still sends default XFO `DENY`. The test confirms this is an intentional **fail-closed policy for legacy browsers**, not an oversight. If requirements mandate supporting old browsers, write acceptance tests and a compatibility matrix and design an alternative solution rather than blindly dropping headers.

### 7.2. Additional Tests Needed in Real Projects

- Browser automation with **allowed** and **disallowed** parent origins to verify frame rendering.
- `SAMEORIGIN` tests when routes use internal iframes.
- Parent `frame-src` tests if the app uses CSP restricting child frames.
- Nested iframe tests: an intermediate ancestor missing from the allowlist must trigger blocking.
- Header checks across login, admin, payment, error pages, static HTML, final redirects, and gateway-served pages.
- Multiple-CSP checks when reverse proxies/CDNs emit headers; ensure a second `frame-ancestors 'none'` doesn't unintentionally block a widget.
- Browser tests with third-party cookies blocked: the iframe may render yet show a logged-out UI.
- Regression checks after upgrading Spring Security/Boot or adding a new `SecurityWebFilterChain`.

## 8. HTTPS, HSTS, Cookies, and Clickjacking

### 8.1. frame-ancestors Enforces Scheme

`https://portal.example.test` **is a different origin** from `http://portal.example.test`. A CSP allowlist for an HTTPS portal does not permit the unencrypted HTTP version to embed the page. In production, use HTTPS for both parent and embedded page to avoid mixed-content blocking and cookie leaks.

If the parent is HTTPS and the iframe URL is HTTP, browsers may block the iframe for **mixed content** even when `frame-ancestors` permits it. That is a different error from "Refused to frame because it violates frame-ancestors." Never fix it by loosening the policy to HTTP; fix the URL/TLS.

### 8.2. HSTS Serves a Different Role

HSTS `Strict-Transport-Security` instructs browsers to use HTTPS for an announced domain, while XFO/CSP governs embedding. Spring Security configures HSTS by default for HTTPS responses. Do not assume having `Strict-Transport-Security` prevents clickjacking, nor that `frame-ancestors` guarantees transport encryption.

In the local HTTP demo, HSTS will not appear as it does in HTTPS production. To test HSTS, run real HTTPS and inspect headers on HTTPS responses.

### 8.3. An Allowed Iframe Might Still Lack a Session

If `https://partner.example.test` embeds `https://app.example.test/embed/card`, the browser may treat the app's cookies as **third-party/cross-site**. `SameSite=Lax` or `Strict` cookies are generally not sent in cross-site iframes. `SameSite=None; Secure` cookies may be needed for an authenticated embed design, though many browsers restrict third-party cookies as well. Browser policies evolve; never work around this by stripping `Secure` or `HttpOnly` from session cookies.

**Security note:** An iframe allowed by CSP still needs proper Authentication and Authorization. Never turn a transactional screen public just because a partner wants to embed it. Consider read-only widgets, minimally scoped tokens, out-of-iframe confirmation UIs, or top-level redirects instead of embedding sensitive actions.

### 8.4. CORS Does Not Control Iframe Embedding

CORS `Access-Control-Allow-Origin` determines whether JavaScript from another origin may **read responses via Fetch/XHR** in applicable cases. Iframe navigation/embedding is a separate mechanism. You cannot "fix a CSP-blocked iframe" merely by adding:

~~~http
Access-Control-Allow-Origin: https://partner.example.test
~~~

Similarly, permitting a partner in `frame-ancestors` **does not grant** the partner's JavaScript access to read the iframe's DOM under SOP. If both sides need to exchange messages, design `window.postMessage` carefully checking exact `event.origin` and `targetOrigin`; never send secrets to arbitrary origins.

## 9. Common Real-World Mistakes

**Mistake 1 — Believing CORS alone prevents clickjacking.**

CORS does not control whether another site can embed your HTML page. You need XFO or CSP `frame-ancestors` on the embedded page's response.

**Mistake 2 — Writing `frame-src 'none'` to block other sites from embedding you.**

`frame-src` is the **parent's** policy, not the list of allowed parents. Use `frame-ancestors 'none'`.

**Mistake 3 — Setting only `default-src 'none'`.**

`frame-ancestors` **does not fall back** to `default-src`. Declare the embedding directive explicitly.

**Mistake 4 — Putting XFO or frame-ancestors in HTML meta tags.**

`X-Frame-Options` has no effect in meta tags. `frame-ancestors` is unsupported in CSP meta tags. Use HTTP response headers only.

**Mistake 5 — Using XFO ALLOW-FROM for partners.**

Obsolete directive that modern browsers may ignore. Use an enforcing CSP allowlist and verify browser support.

**Mistake 6 — Dropping all security headers so an iframe works.**

`headers(headers -> headers.disable())` can remove HSTS, nosniff, cache control, referrer policy, and other defaults. Modify only the specific directive/route needed instead of disabling the entire protection suite.

**Mistake 7 — Applying a relaxed policy to every page.**

If only one widget needs partner embedding, do not let partner iframes embed login, settings, payment, and admin pages. Use per-path chains/matchers or clear route-specific policies.

**Mistake 8 — Confusing SAMEORIGIN with same root domain.**

Different subdomains, schemes, or ports produce different origins. SameSite cookies and same-origin framing are not equivalent.

**Mistake 9 — Forgetting intermediate ancestors.**

Nested iframes: `frame-ancestors` checks **every ancestor**; allowlisting only the top-level parent may fail. Audit the full frame tree.

**Mistake 10 — Using `Content-Security-Policy-Report-Only` thinking it blocks framing.**

Report-Only does not enforce blocking. You need an enforced `Content-Security-Policy`, and for `frame-ancestors` you must test real iframes.

**Mistake 11 — Enabling CSP without frame-ancestors.**

Spring Security does not add CSP by default; having only `script-src`/`style-src` does not block embedding.

**Mistake 12 — Disabling XFO when adding CSP without checking legacy browsers.**

Modern browsers follow CSP; older browsers may not. Turning off XFO removes the fallback for legacy clients, potentially allowing broader embedding than expected.

**Mistake 13 — Sending conflicting CSP headers from app and CDN.**

Enforcing policies combine restrictively; a proxy's `frame-ancestors 'none'` can prevent the app's allowlist from ever working. Verify actual headers along the deployment path.

**Mistake 14 — Making the allowlist overly broad.**

`frame-ancestors *` or opening every subdomain allows an attacker controlling any subdomain to become a parent, increasing clickjacking risk. Specify exact origins and audit ownership.

**Mistake 15 — Displaying sensitive transactional screens inside iframes.**

Even with a trusted partner, UI redressing risk remains from the partner or a compromised origin. Prefer read-only widgets, step-up confirmation, or top-level site redirects for high-risk actions.

**Mistake 16 — Testing headers with curl and declaring browsers safe.**

Curl does not enforce CSP/XFO. Run browser smoke tests on both allowed and disallowed origins, including mobile/embedded webviews as applicable.

**Mistake 17 — Placing the header on the parent instead of the child page.**

`frame-ancestors` must be on the response of the **document being embedded**. The parent uses `frame-src` if restricting which child frames it loads.

**Mistake 18 — Overlooking HTTPS/mixed content.**

An HTTPS CSP allowlist does not allow HTTP; an HTTPS parent may block an HTTP child before `frame-ancestors` is even evaluated. Use proper TLS.

**Mistake 19 — Thinking clickjacking defense replaces CSRF/XSS defense.**

XFO/CSP limits iframe embedding; it neither validates intent on state-changing POSTs nor blocks script injection. You still need CSRF protection, output encoding, script CSP, and authorization.

**Mistake 20 — Disabling cookie SameSite/Secure because an iframe login broke.**

Browsers may restrict third-party cookies. Re-examine your auth model/cookie policy; never remove `Secure`/`HttpOnly` or widen CORS to treat the wrong root cause.

## 10. Pre-Deployment Checklist

1. **Inventory sensitive pages:** admin, payment, settings, token/consent, and transactions; deny embedding by default.
2. **Choose policy:** No iframes needed → `X-Frame-Options: DENY` + `frame-ancestors 'none'`.
3. **Internal iframes:** Same-origin needed → consider `SAMEORIGIN` + `frame-ancestors 'self'`.
4. **Partner embeds:** Scope strictly to widget routes; `frame-ancestors` with trusted partner origins, never XFO `ALLOW-FROM`.
5. **All ancestors:** For nested frames, both intermediate and top-level origins must be permitted.
6. **Actual responses:** Headers must be present on the target HTML document response; never rely on meta tags.
7. **Enforcing CSP:** Anti-framing requires enforced `Content-Security-Policy`, not Report-Only alone.
8. **Default headers:** Never disable all of `ServerHttpSecurity.headers(...)` just to fix one iframe.
9. **Chain selection:** `@Order`/`securityMatcher` cover the exact routes, with a catch-all protecting the rest.
10. **AuthZ:** `permitAll` only for public resources; sensitive widgets must still enforce real authorization.
11. **No conflicting policies:** Check whether gateway/CDN/app emit conflicting XFO/CSP headers.
12. **Browser compatibility:** Have a fail-closed plan for legacy browsers lacking `frame-ancestors` support.
13. **Parent CSP:** If you own the parent, ensure `frame-src` also permits valid child frames.
14. **Cookies:** Cross-site iframes may omit session cookies; keep `Secure`/`HttpOnly` and evaluate SameSite/third-party policies.
15. **HTTPS:** Parent/child both use HTTPS in production; verify HSTS and mixed-content behavior.
16. **CSRF/XSS:** Frame protection does not replace those layers; never expose state-changing GET endpoints.
17. **CORS:** Never rely on CORS to govern iframe embedding or fix `frame-ancestors`.
18. **Privacy:** Partner iframes should not leak sensitive info, credentials, or admin UIs.
19. **Testing:** Test headers with `WebTestClient`, and test rendering in browsers from allowed and untrusted origins.
20. **Regression:** Re-test every security chain after upgrading Spring Security, changing proxies, or editing CSP.
21. **Logging:** CSP violation logs are useful, but avoid logging cookies, Authorization headers, or unnecessary user data.
22. **Policy review:** Whenever adding a partner origin, verify ownership, HTTPS, permission scope, and a revocation plan.

## 11. Self-Assessment Questions

**1.** Can a page with `X-Frame-Options: DENY` be embedded in an iframe on its own domain?

**Answer:** No. `DENY` forbids all ancestors, including same-origin ones.

**2.** Does `X-Frame-Options: SAMEORIGIN` allow `https://admin.example.test` to embed `https://app.example.test`?

**Answer:** No; different hosts create different origins, even though the two subdomains may be same-site for cookies.

**3.** Is XFO `ALLOW-FROM https://partner.example.test` recommended?

**Answer:** No. It is an obsolete directive not reliably supported by modern browsers; use CSP `frame-ancestors`.

**4.** Does `Content-Security-Policy: default-src 'none'` stop all websites from embedding the page?

**Answer:** Not automatically. `frame-ancestors` does not fall back to `default-src`; it must be declared explicitly or paired with XFO.

**5.** How do `frame-src 'self'` and `frame-ancestors 'self'` differ?

**Answer:** `frame-src` restricts which iframe sources the current document may load; `frame-ancestors` restricts which parent origins may embed the current document.

**6.** Does CSP `frame-ancestors 'self' https://partner.example.test` check intermediate ancestors?

**Answer:** Yes. All ancestors must match; an unlisted intermediate ancestor causes the browser to cancel rendering.

**7.** If a response includes XFO `DENY` and CSP `frame-ancestors` allowing a partner, what does a modern browser do?

**Answer:** Per specification, browsers supporting enforced `frame-ancestors` prioritize the CSP directive and ignore XFO for that decision; legacy browsers understanding only XFO may block the partner.

**8.** Is setting `frame-ancestors` only via `<meta http-equiv="Content-Security-Policy">` sufficient?

**Answer:** No. The directive is not supported in meta tags; use HTTP response headers.

**9.** Can `curl -i` output serve as proof that iframes are blocked?

**Answer:** No. Curl only inspects HTTP headers and does not render iframes. Browser testing is required.

**10.** Why don't CSP `frame-ancestors` replace CSRF tokens and authorization?

**Answer:** It only controls document framing, not identity verification, business permissions, or the intentionality of state-changing requests.

**11.** Only one widget route needs partner embedding. Should you switch the entire app to `SAMEORIGIN`/a broad allowlist?

**Answer:** No. Configure policies per route/chain; unrelated pages should remain denied.

**12.** Embedding is allowed, yet the iframe has no session. Is `frame-ancestors` broken?

**Answer:** Not necessarily. Cookie `SameSite`/`Secure`/third-party blocking and login flows can leave an iframe unauthenticated even when framing is permitted.

## Official Documentation

- Spring Security 6.5 — Security HTTP Response Headers for WebFlux (X-Frame-Options default/mode, CSP): https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html
- Spring Security — `ServerHttpSecurity.HeaderSpec.FrameOptionsSpec` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.FrameOptionsSpec.html
- Spring Security — `XFrameOptionsServerHttpHeadersWriter.Mode` (DENY, SAMEORIGIN): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/header/XFrameOptionsServerHttpHeadersWriter.Mode.html
- Spring Security — Configuring Multiple SecurityWebFilterChain: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- MDN — X-Frame-Options (DENY/SAMEORIGIN/ALLOW-FROM): https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options
- MDN — CSP frame-ancestors (nested ancestors, meta limitation, no default-src fallback): https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors
- MDN — CSP Guide, enforcement and Report-Only: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP
- OWASP — Clickjacking Defense Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html
- Spring Boot 3.5.16 release (last OSS 3.5.x): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
