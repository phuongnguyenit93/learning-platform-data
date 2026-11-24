# X-Frame-Options, CSP frame-ancestors, and Clickjacking Protection

> **Scope:** Spring Security on the Servlet stack (Spring Boot 3.x, Spring Security 6.x, Java 17+). This lesson explains how to prevent untrusted websites from embedding your application's UI inside an `iframe`/`frame` to trick user actions, how to configure defensive HTTP response headers, and how to test them.

## 1. Objectives and real-world scenario

Suppose a financial application has a page `https://bank.example.test/confirm` with a **Confirm** button. The user is already logged into the bank in another tab. An attacker builds another page, places an almost transparent `iframe` containing the bank's confirmation page, and positions a "Claim Reward" button directly over the real button. When the victim tries to click "Claim Reward", the click lands on the embedded page's button.

This is a form of **clickjacking** (UI redressing): the attacker manipulates how UI is presented so the user inadvertently interacts with a different resource. Techniques can leverage layered layouts, opacity, cursor positioning, scrolling, or visual deception variants. Exploitability depends on how the application handles authentication, cookies, interactions, and browser behavior; not every embeddable page is automatically exploitable.

Key point: **same-origin policy (SOP)** typically prevents JavaScript on the attacker's page from reading the DOM of the bank `iframe`, but it does not necessarily prevent **displaying the page inside an iframe** or the user directly clicking its contents. **CORS** primarily controls whether JavaScript can read cross-origin responses, and does not replace anti-framing defenses.

After this lesson, you will know how to:

- Define the protection boundaries of `X-Frame-Options` (XFO) and `Content-Security-Policy: frame-ancestors ...`.
- Choose policies to **forbid embedding**, **allow same-origin only**, or **allow specific partner origins**.
- Configure response headers in Spring Security Servlet's `SecurityFilterChain`.
- Understand the relationship between XFO, CSP, SOP, CORS, CSRF, cookies, and Spring Security filters.
- Inspect HTTP headers, real iframe behavior, and common deployment mistakes.

## 2. How does clickjacking happen?

An illustrative flow:

```text
User is authenticated with application A
                  |
                  v
Opens page controlled by attacker (B)
                  |
                  v
B tries to embed A's sensitive action page in an <iframe>
                  |
                  v
B overlays / arranges UI to trick the user into misclicking
                  |
                  v
If the browser allows embedding and other conditions permit,
the action may be sent to A under the user's session context.
```

Unlike an attacker sending API requests directly, clickjacking often **borrows the user's own legitimate interaction**. Therefore, merely checking "is the user logged in?" or "is the user authorized to click this button?" may not be enough. A CSRF token is not a complete clickjacking defense either: an action genuinely submitted through the application's UI can carry a valid token.

The fundamental defense is **not letting untrusted origins embed sensitive documents**. The browser evaluates the policy in the **HTTP response of the page being embedded**, commonly called the *child document* or *framed document*. Framing permissions are declared by application A itself, not decided by page B.

Scope note: XFO and `frame-ancestors` block content from being embedded inside browsing contexts such as `iframe` or `frame`; they do not prevent users from visiting the page directly in a separate tab, do not fix XSS vulnerabilities, and do not replace server-side authorization.

## 3. X-Frame-Options: concise protection and legacy compatibility

`X-Frame-Options` is an HTTP **response header** declaring whether a document is allowed to be displayed inside a frame/iframe.

Values to remember:

| Value | Meaning | When to use |
|---|---|---|
| `X-Frame-Options: DENY` | Disallows embedding by any page, including same origin | Account, admin, payment, confirmation pages; good default when iframes are not needed |
| `X-Frame-Options: SAMEORIGIN` | Allows embedding within the same origin as supported by browsers | Applications genuinely needing internal same-origin iframes |
| `X-Frame-Options: ALLOW-FROM ...` | Historical value, **obsolete and inconsistently supported** | Do not use to allowlist partners |

Example of a response protecting a page:

```http
HTTP/1.1 200 OK
Content-Type: text/html
X-Frame-Options: DENY

<!doctype html>
<html lang="en"><body>Account management page</body></html>
```

The policy applies even when the page holds no secret content; for example, a payment initiation button rendered on a page can be a clickjacking target. Do not attach the header only on JSON APIs while omitting sensitive HTML responses.

**`SAMEORIGIN` uses the origin concept, not just the same domain name.** Relative to `https://app.example.test:443`, an iframe from `https://app.example.test:8443` or `http://app.example.test` is a **different origin** due to differing port or scheme. Do not use `SAMEORIGIN` if embedding is needed from `https://partner.example.test`: that is still a different origin.

**Limitations of XFO:** the only practical choices are `DENY` or `SAMEORIGIN`. XFO has no multi-origin allowlist. Ancestor checks across nested frames also varied historically across browsers. Consequently, modern applications typically use CSP `frame-ancestors` for clearer and finer-grained policies; XFO remains useful as a compatibility defense for older browsers when policies align.

## 4. CSP frame-ancestors: policy for who may embed the document

`frame-ancestors` is a directive of the `Content-Security-Policy` (CSP) HTTP header. It specifies **which origins are allowed to become ancestors** when embedding the document. Browsers check **every ancestor** in a nested frame chain: a single disallowed ancestor can cause embedding to fail even if the immediate parent iframe is on an allowed origin.

Policy patterns:

```http
# Disallow embedding anywhere, including the application itself
Content-Security-Policy: frame-ancestors 'none'

# Only pages sharing the same origin as the embedded document
Content-Security-Policy: frame-ancestors 'self'

# Allow embedding from same origin and a specific partner portal
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test

# Allow embedding from two specific origins
Content-Security-Policy: frame-ancestors https://portal.example.test https://reports.example.test
```

The lines above are **separate alternatives**, not one response carrying conflicting values. In practice, the server sends the appropriate CSP header for each endpoint; lines starting with `#` are illustrative comments, not HTTP header syntax.

Points to understand accurately:

1. `'none'` rejects all ancestors; `'self'` matches the origin of the **target document**, not the parent page's origin.
2. Sources like `https://portal.example.test` must be chosen deliberately; scheme, host, and port affect matching. Avoid broad wildcards like `*` or all subdomains unless genuinely trusted.
3. `frame-ancestors` controls **who can embed this page**. Conversely, `frame-src` / `child-src` (on the parent page) govern **which frames the parent page can load**. These two directions are independent and both may need to be satisfied.
4. `default-src` **is not a fallback** for `frame-ancestors`. If a CSP only has `default-src 'none'` without `frame-ancestors`, you have not declared any framing ancestor restriction.
5. `frame-ancestors` must be sent via an **HTTP response header**. Do not rely on `<meta http-equiv="Content-Security-Policy">` to set this directive: browsers do not support it via meta tags.
6. `Content-Security-Policy-Report-Only` serves testing/reporting per browser support; **to actually block embedding, deploy an enforcing policy in `Content-Security-Policy`** and test in browsers.
7. CSP can contain multiple directives, e.g., `default-src 'self'; script-src 'self'; frame-ancestors 'none'`. Adding only `frame-ancestors` does not mean the rest of the CSP protects against XSS.

CSP `frame-ancestors` lets you express specific partner embedding needs that XFO `SAMEORIGIN` cannot. However, any partner allowed to embed represents a **trust boundary**: if that origin suffers from XSS or compromise, it can become a platform for clickjacking. Allowlist only sources you control or have evaluated.

## 5. Sending X-Frame-Options and frame-ancestors together

In modern browsers supporting enforcing CSP `frame-ancestors`, that policy may **take precedence over** XFO for framing decisions. Older browsers may apply XFO without understanding `frame-ancestors`. Do not rely on contradictory combinations hoping browsers will pick the same winner.

| Requirement | X-Frame-Options | CSP frame-ancestors | Deployment meaning |
|---|---|---|---|
| No page may embed | `DENY` | `'none'` | Both headers align, protecting modern and many legacy browsers |
| Same-origin internal embedding only | `SAMEORIGIN` | `'self'` | Both policies align in intent |
| Allow specific partner origin | Cannot be expressed by XFO | `'self' https://portal.example.test` or partner-only | Do not configure XFO contradicting policy; weigh lack of protection/support on legacy browsers |
| No iframe needed | `DENY` | `'none'` | Default closed, open only with clear product requirements |

For **cross-origin partner** cases, the common configuration is **omitting XFO on the embeddable endpoint** and using CSP `frame-ancestors` with a precise allowlist. Trade-off: legacy browsers not supporting this directive may lack framing control. Evaluate your supported browser matrix; if legacy-browser safety is required, consider exposing dedicated embeddable data/widget paths without sensitive state-changing actions rather than opening the whole account page.

In Spring Security 6, default header configuration typically enables **X-Frame-Options: DENY**. Therefore, simply adding CSP for a partner may not be enough: default XFO still affects older browsers, causing inconsistent behavior. Whenever changing policy, inspect **actual HTTP responses** per endpoint and through proxies/CDNs.

## 6. Runnable example: Spring Security Servlet blocking all iframes

### 6.1. Project and file structure

Minimal example using Spring Boot 3.3.x, Spring Security 6.x, and Java 17. Requires the project's Gradle Wrapper; sample `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create two Java classes in package `demo.frame`.

**File `src/main/java/demo/frame/FrameDemoApplication.java`:**

```java
package demo.frame;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FrameDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FrameDemoApplication.class, args);
    }

    @GetMapping(value = "/protected-ui", produces = MediaType.TEXT_HTML_VALUE)
    public String protectedUi() {
        return """
                <!doctype html>
                <html lang="en">
                <head>
                  <meta charset="utf-8">
                  <title>Frame protection demo</title>
                </head>
                <body>
                  <h1>Protected page</h1>
                  <button type="button">Demo button</button>
                </body>
                </html>
                """;
    }
}
```

**File `src/main/java/demo/frame/SecurityHeadersConfig.java`:**

```java
package demo.frame;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityHeadersConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/protected-ui").permitAll()
                .anyRequest().denyAll())
            .headers(headers -> headers
                // XFO protects on supporting browsers.
                .frameOptions(frame -> frame.deny())
                // CSP explicitly states: no origin may embed the page.
                .contentSecurityPolicy(csp ->
                    csp.policyDirectives("frame-ancestors 'none'")));

        // Do not alter CSRF, session, or authentication to configure headers.
        return http.build();
    }
}
```

**Code explanation:** Servlet's `SecurityFilterChain` is invoked through the security filter chain before generating the response. `headers(...)` configures security header emission. `frameOptions(...deny())` sets `X-Frame-Options: DENY`; `contentSecurityPolicy(...)` sends `Content-Security-Policy: frame-ancestors 'none'`. Endpoint `/protected-ui` is `permitAll()` only so anyone can load the page and observe header effects. Blocking framing **does not depend** on whether a page requires login; authenticated pages should also receive appropriate headers. `anyRequest().denyAll()` is only for the demo so no other endpoints are accidentally exposed.

When integrating into a real system, **keep existing working authentication, authorization, session, and CSRF rules intact**; only modify the header configuration in the appropriate `SecurityFilterChain`. If the app has multiple chains or a reverse proxy, check which chain actually handles the sensitive page's URL.

### 6.2. Running and inspecting headers

In a project with Gradle Wrapper:

```bash
./gradlew bootRun
```

In another terminal:

```bash
curl -s -D - -o /dev/null http://localhost:8080/protected-ui
```

In the response headers, you should see **lines equivalent to**:

```http
HTTP/1.1 200
X-Frame-Options: DENY
Content-Security-Policy: frame-ancestors 'none'
Content-Type: text/html
```

These are key extracted lines, **not the exact complete response**; the server may emit additional headers and different ordering. `curl` confirms the server sends the headers, but `curl` **does not enforce** anti-framing policies like a browser.

### 6.3. Testing with a browser

Create `frame-test/index.html` outside the application:

```html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Iframe test</title></head>
<body>
  <h1>Iframe embed test page</h1>
  <iframe
    src="http://localhost:8080/protected-ui"
    title="Protected UI"
    width="600"
    height="300"></iframe>
</body>
</html>
```

You can serve the file on port 5173 using a local static server, for instance with Python 3 installed:

```bash
cd frame-test
python -m http.server 5173
```

Open `http://localhost:5173`. Modern browsers will **refuse to display `/protected-ui` content inside the iframe** and typically log a message in DevTools Console stating the frame was refused due to CSP `frame-ancestors` or XFO. The Network tab may still show a **200** response from the server: that is not a contradiction, because the browser declines to **render** the document inside the iframe based on the received headers.

To confirm `DENY` truly forbids **same-origin embedding too**, use a test page served from `http://localhost:8080` in a test environment and embed `/protected-ui`: it must still be blocked. Avoid drawing conclusions from a CORS error on `fetch`; iframe navigation and CORS are distinct mechanisms.

### 6.4. Automated testing with MockMvc

File `src/test/java/demo/frame/SecurityHeadersTest.java`:

```java
package demo.frame;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersTest {
    @Autowired
    MockMvc mvc;

    @Test
    void protectedPageDeclaresAntiFramingHeaders() throws Exception {
        mvc.perform(get("/protected-ui"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy", "frame-ancestors 'none'"));
    }
}
```

Run:

```bash
./gradlew test
```

The test verifies the **response header contract** of Spring Security Servlet. It is not a real browser, so clickjacking defense acceptance still requires the browser iframe check from section 6.3.

## 7. Choosing a different policy when legitimate embedding is needed

Do not ban iframes mechanically if the product genuinely includes embedded screens. Clearly identify **which page is embedded**, **from which origins**, and **the trust level of those origins**.

### 7.1. Same-origin embedding only

Replace the `headers(...)` portion of the example with:

```java
.headers(headers -> headers
    .frameOptions(frame -> frame.sameOrigin())
    .contentSecurityPolicy(csp ->
        csp.policyDirectives("frame-ancestors 'self'")))
```

This snippet is **only a replacement configuration inside `HttpSecurity` for the project in section 6**, not a standalone Java file. Pages on the same origin as `/protected-ui` can then embed it, while pages on other origins are rejected.

For example, `https://app.example.test/reports` and `https://app.example.test/details` share the same origin, whereas `https://dashboard.example.test` is not same-origin despite sharing a top-level domain.

### 7.2. Allowing a cross-origin partner portal

Suppose you need to embed **a dedicated report page** at `/embed/report` inside `https://portal.example.test`. With CSP:

```http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test
```

Spring Security 6 configuration for a **separate chain applying only to `/embed/**`** can use:

```java
.headers(headers -> headers
    // XFO cannot list a cross-origin partner origin.
    // Disable only on the controlled embedding chain/scope.
    .frameOptions(frame -> frame.disable())
    .contentSecurityPolicy(csp -> csp.policyDirectives(
        "frame-ancestors 'self' https://portal.example.test")))
```

This is a **configuration replacement snippet**, not a complete application. To use it, design `securityMatcher("/embed/**")` and clear chain ordering (when multiple chains exist); ensure chains for `/account/**`, `/admin/**`, and `/payment/**` still enforce anti-framing policies. Do not weaken XFO system-wide just to display one widget.

**Mandatory trade-off:** disabling XFO on the embed endpoint may leave legacy browsers that do not support CSP `frame-ancestors` unprotected. For sensitive content, consider an architecture providing **restricted data/widgets** instead of allowing full state-changing pages to be embedded.

Even when a partner is allowed to embed, the API/page must still check sessions, authorization, and permitted actions. If the embedded page relies on login cookies, browsers may restrict **third-party cookies** or enforce `SameSite`; CSP allowing embedding **does not guarantee** the login session works.

### 7.3. Nested frames and trusted sources

Suppose `A` embeds `B`, and `B` embeds sensitive page `C`. If `C` only allows ancestor `B` but **does not allow `A`**, `C`'s `frame-ancestors` can still block it. Do not allowlist only the immediate outer iframe's origin; consider the entire designed ancestor chain.

Frame restrictions via CSP also affect partner integrations, dashboards, reports, and automated screenshot jobs; verify legitimate needs as well. However, never permit broad origins just to fix a framing error in a test environment.

## 8. What these headers do not replace

| Mechanism | Primary protection | Difference from anti-framing |
|---|---|---|
| XFO / CSP `frame-ancestors` | Restricts who may embed a document | Directly reduces clickjacking risk via iframes |
| Same-origin policy | Restricts DOM/data access across origins in the browser | Does not always stop another page from visually embedding UI |
| CORS | Conditionally allows scripts to read cross-origin responses | Does not prevent clickjacking via iframes |
| Authentication | Establishes user identity/session | An authenticated user can still be tricked into misclicking |
| Authorization | Checks action/resource permissions | An authorized user can still be deceived into acting |
| CSRF protection | Defends against forged requests relying on browser sessions | A click on the real UI can still submit a valid token |
| Cookie `SameSite` | Restricts when browsers send cookies based on site relationship | Cross-origin is not always cross-site; cookie policy is not a complete anti-framing control |
| CSP `script-src` / XSS defense | Restricts script execution and injection | Does not replace `frame-ancestors` |
| CSP `frame-src` | Restricts which frames **this page** may load | Does not govern who may embed **this page** |

Do not rely on JavaScript checking `window.top !== window.self` and redirecting (*frame-busting*) to defeat clickjacking: scripts can fail to run, be sandboxed, or be bypassed; browser-enforced HTTP headers are the primary defense. Likewise, an iframe `sandbox` attribute on the parent page restricts some child capabilities, but does not replace **the target page controlling its own ancestors**.

Sensitive UIs also benefit from re-authentication where appropriate, clear transaction summaries, backend permission checks, rate limiting, XSS defenses, and comprehensive CSP. XFO/`frame-ancestors` is one layer of HTTP protection.

## 9. Verifying in environments with Spring Security, reverse proxies, or CDNs

In multi-layered systems, headers can be added, modified, or stripped at servlet filters, gateways, reverse proxies, or CDNs. Never read a config file and assume headers are always right.

Practical verification steps:

1. **Identify HTML page URLs requiring protection** and all routes serving equivalent UIs (login pages, action screens, HTML error endpoints, admin apps). For SPAs, the HTML entry point is typically the primary response needing anti-framing.
2. **Inspect the final response over the real domain** using `curl -D -` or DevTools Network; verify XFO/CSP on 200, and 302/401/403 per design as well as sensitive HTML content. Headers on a redirect response do not replace headers on the final document.
3. **Test framing from a disallowed origin** in a real browser; confirm the page does not render and inspect the console. Then test an allowed origin (if policy is not `'none'`) to avoid breaking legitimate features.
4. **Check multiple `SecurityFilterChain` beans**. Rules in one chain do not automatically apply to another. For partner-embedded content, confirm that chain is actually selected for that URL, and the default chain still locks down sensitive pages.
5. **Compare headers emitted across layers**. Divergent policies can yield unexpected behavior across browsers. Do not let a proxy overwrite a strict CSP with a permissive CSP, drop XFO, or emit two conflicting XFO values.
6. **Test nested frames and cookies/sessions** if the product uses multi-tier portals. Distinguish "CSP blocked the frame" from "embedded but missing login cookies" or other application errors.

### Acceptance matrix

| Scenario | Expected XFO/CSP | Browser result |
|---|---|---|
| Account page needing no iframe | `DENY` + `frame-ancestors 'none'` | Embedding from any origin is blocked |
| Report page for internal iframe only | `SAMEORIGIN` + `frame-ancestors 'self'` | Same origin allowed; cross-origin blocked |
| Widget page for one partner | Exact origin CSP allowlist on dedicated endpoint | Partner origin/`'self'` only if declared; all ancestors must match |
| User opens document directly in new tab | Any valid anti-framing header | Page opens normally; headers affect framing only |
| Embedded via chain A → B → C | C's CSP `frame-ancestors` allowlist | One disallowed ancestor prevents C from being embedded |
| Reverse proxy adds extra CSP | Inspect final response | No unintended policy widening, override, or conflict |

## 10. Common mistakes and fixes

**1. Setting only `frame-src 'none'` and thinking embedding is blocked.** `frame-src` states where **your** page can load embedded content from. You must use `frame-ancestors` on **the page you want to prevent others from embedding**.

**2. Putting `frame-ancestors` in a `meta` tag.** This directive is ignored when declared in HTML meta tags; an HTTP response header must be used.

**3. Using `ALLOW-FROM` to allow a partner.** That value is obsolete; use CSP `frame-ancestors` with explicit origins and a clear browser compatibility plan.

**4. Adding CSP for a partner while forgetting Spring Security's default XFO.** Across browsers with differing support, framing outcomes may diverge. Inspect actual response headers, pick policies intentionally, and omit XFO only on the exact embeddable pages when needed.

**5. Configuring protection on the parent iframe instead of the child HTML.** Anti-framing headers must be on the response of the **embedded** document. The parent page also has its own policy limiting which frame sources it loads.

**6. Dropping XFO and opening `frame-ancestors *` site-wide to fix one broken iframe.** Accidentally creates a broad clickjacking surface. Open only endpoints with an embedding business requirement and keep protections elsewhere.

**7. Using only `curl`, seeing 200, and assuming protection failed.** The HTTP response can still succeed; it is the browser that refuses to **render inside the iframe**. Browser testing is mandatory.

**8. Assuming XFO/CSP replace CSRF, access control, or XSS defense.** They are complementary layers. Maintain authentication, authorization, CSRF, and cookie security per your threat model.

## 11. Takeaways

- **Clickjacking** tricks users into clicking embedded or overlaid UI; SOP and CORS do not automatically stop this attack class.
- **`X-Frame-Options`:** `DENY` to forbid embedding, `SAMEORIGIN` for same-origin embedding; do not use obsolete `ALLOW-FROM`.
- **CSP `frame-ancestors`:** `'none'`, `'self'`, or an explicit origin allowlist; checks all ancestors and only takes effect via HTTP response headers.
- When iframes are unnecessary, **`DENY` + `frame-ancestors 'none'`** is the consistent choice. When cross-origin partners are needed, use a CSP allowlist on a dedicated endpoint and understand the trade-off for legacy browsers.
- In **Spring Security Servlet**, manage these headers via `SecurityFilterChain.headers(...)`; verify on real HTTP responses and inside browser iframes.