# Content-Security-Policy and its limits against XSS attacks

**Content-Security-Policy (CSP)** is a security policy sent by an application to the browser to restrict the sources and ways certain types of content—especially **JavaScript**—may be loaded or executed. CSP helps **reduce the likelihood and impact of many forms of Cross-Site Scripting (XSS)**, but it **does not replace** proper input/output handling and does not guarantee prevention of every XSS type.

For example, if a vulnerability lets user input inject `<script>...</script>` into HTML, a sufficiently strict CSP can refuse to execute that injected script. However, if the application's own trusted JavaScript can be abused as a "gadget", or if the CSP permits a risky script source, an attacker can still trigger unintended actions.

This lesson focuses on: how CSP works in browsers, the difference between **allowlist CSP** and **nonce/hash-based strict CSP**, configuring the header with Spring Security Servlet, rolling out incrementally with `Report-Only`, CSP's limits against XSS/DOM XSS, and a practical testing checklist.

## 1. What is XSS, and where does CSP participate?

**XSS (Cross-Site Scripting)** occurs when untrusted data enters a context where the browser can interpret it as active **JavaScript or executable content**, rather than displaying it strictly as text.

Three common categories:

- **Reflected XSS:** Data from a request is echoed immediately into the page without context-appropriate handling—for instance, a query parameter rendered as HTML.
- **Stored XSS:** A payload is saved in a database, comment, profile, or CMS and rendered when another user opens the page.
- **DOM-based XSS:** The page's JavaScript reads untrusted data (URL, hash, `postMessage`, API, etc.) and passes it straight into a **dangerous DOM sink**, such as `innerHTML`, enabling unintended execution.

When XSS succeeds, an attacker can send requests with the user's privileges, alter the DOM, read page data accessible to scripts, and steal unprotected information. An `HttpOnly` cookie limits script access via `document.cookie`, yet **does not stop a same-origin script from issuing requests that the browser automatically attaches cookies to**.

**CSP participates as a browser-side control layer**: before a script/style/resource is loaded or executed, the browser checks it against the active policy. If disallowed, the browser blocks it and can log a violation. CSP **does not sanitize bad input, remove payloads from HTML, or replace encoding/sanitization**.

A proper defense chain typically looks like:

```text
Untrusted data
        |
        v
Validate input per business rules
        |
        v
Context-aware output encoding / HTML sanitization if HTML must be allowed
        |
        v
Avoid dangerous DOM sinks (innerHTML, eval, document.write...)
        |
        v
Browser enforces CSP (script sources, nonces/hashes, navigation/frames...)
        |
        v
Monitor violations + perform XSS testing
```

**Principle:** Fixing the script injection flaw is the primary defense; CSP is **defense in depth** to raise exploitation cost and limit blast radius when another layer fails.

## 2. How browsers receive CSP

CSP is typically returned in an **HTTP response header** on HTML documents:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
```

An application can send **multiple CSP policies**. When a browser receives multiple enforced policies, every policy is evaluated and the combined effect is **stricter**, rather than "the later policy overwrites the earlier one." Duplicate headers from a reverse proxy, CDN, or Java filter can therefore cause confusing asset-loading failures.

Two important headers exist:

| Header | Purpose | Are violations blocked? |
|---|---|---|
| `Content-Security-Policy` | **Enforce**: browser enforces the policy | Yes, for directives supported by the browser |
| `Content-Security-Policy-Report-Only` | Observe and measure the impact of an experimental policy | **No** by the Report-Only policy alone; reporting/console depends on support |

Example enabling trial mode:

```http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; report-uri /csp-report
```

With Report-Only, content flagged as a violation by the trial policy **still runs**; never cite it as proof that the application is protected. A page can carry both a current enforced policy and a report-only policy to test a tighter one.

CSP can also be declared via `<meta http-equiv="Content-Security-Policy" ...>` in some cases, yet it **does not support all directives** and only applies after the browser parses that tag. Directives such as `frame-ancestors` and `Report-Only` mode do not take effect via meta CSP the way HTTP headers do. **Prefer HTTP headers** for formal security configuration.

## 3. Essential directives to master

A CSP consists of **directives** and **source expressions**. Different directives govern different types of loading and execution:

| Directive | Function | Guidance |
|---|---|---|
| `default-src` | Fallback for many resource-loading directives when omitted | Start strict, e.g., `'none'` or `'self'` per app |
| `script-src` | Controls JavaScript sources and execution modes | Most critical for XSS; consider nonces/hashes |
| `script-src-elem` | Specific policy for `<script>` elements | When declared, takes precedence over `script-src` fallback for elements |
| `script-src-attr` | Specific policy for inline event handlers | Avoid `onclick="..."` and similar |
| `style-src` | CSS sources and inline styles | Externalize CSS; avoid `unsafe-inline` if possible |
| `img-src` | Image sources | Allow only sources actually used |
| `font-src` | Font sources | Usually `'self'` and trusted CDNs if needed |
| `connect-src` | Destinations scripts may connect to (Fetch/XHR/WebSocket/EventSource...) | List exact APIs; check browser scheme/WS handling |
| `object-src` | `<object>`, `<embed>` | Usually set to `'none'` |
| `base-uri` | Restricts `<base href="...">` values | Usually `'none'` or `'self'` |
| `form-action` | Restricts target URLs for form submissions | Lock down form destinations per business flow |
| `frame-ancestors` | Who may embed the page in a `frame`/`iframe` | Anti-clickjacking, e.g., `'none'` |
| `frame-src` | Where the current page may load frames from | Different from `frame-ancestors` |
| `upgrade-insecure-requests` | Asks browser to upgrade HTTP subresource requests to HTTPS | Does not replace HTTPS/HSTS configuration |
| `report-uri` / `report-to` | Violation report destinations, per browser/CSP reporting support | Implement and secure report payload handling |

**Not every directive inherits `default-src`.** `frame-ancestors`, `base-uri`, and `form-action` are key examples that **do not fall back to `default-src`**. If you require protection for these behaviors, specify them explicitly.

Example baseline resource policy for a site serving JavaScript/CSS from its own origin:

```http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

This is an **illustrative allowlist policy**, not a universal CSP for every site. If an application needs Google Fonts, CDNs, WebSockets, SSO, external images, or iframes, review and adjust each directive accordingly. Assess scope before allowing `data:` for images; never casually add `data:` to `script-src`. Never copy and enforce a policy without measuring its impact on the live pages.

## 4. Understanding source expressions accurately

Common values:

| Source expression | Meaning |
|---|---|
| `'none'` | Allow no sources for that directive |
| `'self'` | Allow resources from the document's own origin |
| `https://cdn.example.test` | Specific source identified by scheme/host |
| `https:` | Allow across many HTTPS origins—fairly broad |
| `*` | Very broad allowance; generally unsuitable for protecting scripts |
| `'nonce-...'` | Allow specific scripts/styles carrying a matching valid nonce |
| `'sha256-...'` / `'sha384-...'` / `'sha512-...'` | Allow inline scripts/styles with a matching hash |
| `'strict-dynamic'` | Let scripts trusted via nonce/hash propagate trust to dynamically loaded scripts per CSP3 rules |
| `'unsafe-inline'` | Relaxes blocking of inline scripts/styles; typically weakens XSS defense |
| `'unsafe-eval'` | Allows string-to-code evaluation such as `eval()`; increases risk |

Single quotes in CSP are **part of the syntax** for keywords, hashes, and nonce expressions. `script-src self` is not equivalent to `script-src 'self'`. Preserve the single quotes accurately when constructing Java strings.

Misconceptions to avoid:

- `'self'` **does not automatically mean a safe source** if the origin hosts user-uploaded scripts, an endpoint returning executable content, or existing JS containing XSS gadgets.
- Allowing `https:` or a broad CDN **is not equivalent** to allowing only reviewed scripts.
- `'unsafe-inline'` enables running inline scripts and event handlers under many policies and forfeits much of CSP's XSS mitigation.
- `'unsafe-eval'` permits evaluating strings as code. Do not enable it merely for an incompatible library; prefer refactoring or adjusting build settings.
- Nonces/hashes only help if attackers **cannot obtain a valid value to attach to their payload**, and trusted scripts cannot be abused.

## 5. Allowlist CSP: easy to start, but limited

Example:

```http
Content-Security-Policy: script-src 'self' https://cdn.example.test; object-src 'none'; base-uri 'none'
```

The browser can load scripts from the same origin or the allowed CDN. This is better than having no CSP, especially when eliminating `unsafe-inline` and blocking object embedding. Yet allowlist CSP has practical limitations:

1. A CDN can host **many resources of varying trust levels**. If an attacker can serve a script on a path covered by the allowlist, CSP may accept it.
2. Same-origin resources are not inherently safe if the app has endpoints reflecting user data in a way browsers treat as JavaScript.
3. Maintaining an accurate host list in large apps becomes complex; developers tend to add wildcards or blanket `https:` just to "make errors go away".
4. An allowed script may contain DOM XSS bugs, load external resources, or mishandle untrusted data.
5. Not every XSS issue can be blocked by a domain list alone, especially trusted code writing unsafely to sinks.

**Therefore, a strict CSP based on nonces or hashes is usually recommended for controlling script execution**, after evaluating compatibility.

## 6. How does nonce-based strict CSP work?

A **nonce** is an unpredictable random value generated **fresh for every HTML response** and placed identically into both the CSP header and the legitimate `<script>` tags emitted by the server.

Illustrative example (dummy nonce only to show mechanics; never hardcode in production):

```http
Content-Security-Policy: script-src 'nonce-DEMO_NONCE_NOT_FOR_PRODUCTION' 'strict-dynamic'; object-src 'none'; base-uri 'none'
```

```html
<script nonce="DEMO_NONCE_NOT_FOR_PRODUCTION" src="/assets/main.js"></script>
```

When the browser sees a script whose nonce matches the policy, it permits execution per CSP rules. An attacker-injected script **lacking a valid nonce** is normally blocked. The example above illustrates syntax, not a secure setup, because the nonce is a predictable constant string.

### Requirements to follow

1. **Fresh per response:** Generate the nonce with a cryptographic random generator such as `SecureRandom`, with sufficient entropy (typically 128 bits or more), and never reuse a static nonce across pages or users.
2. **Same value within one response:** The CSP header and the `nonce` attribute on trusted scripts must match. Multiple legitimate scripts on the **same response** can share that response's nonce.
3. **Server-generated:** Never take a nonce value from query parameters, request headers, or user-controlled data.
4. **Never attach to untrusted content:** If user-controlled HTML could acquire a valid nonce, an attacker could exploit it.
5. **Prevent caching from reusing stale response nonces:** Cached HTML served via proxies/CDNs needs a consistent strategy for generating/attaching headers and markup so the same static nonce isn't reused broadly across responses.
6. **Do not treat nonces like user passwords:** Nonces appear in valid HTML and are observable in page context; they prevent *guessing/injecting scripts into responses before browser execution*, not hiding values from already-permitted JavaScript.

### What is `strict-dynamic`?

In CSP3, `'strict-dynamic'` lets trust granted via nonce/hash on a **root script** extend to certain scripts dynamically loaded by that script—such as `<script>` elements created via DOM APIs and appended to the document. When `strict-dynamic` is active in `script-src`, host/scheme allowlists like `'self'`, `https:`, and `'unsafe-inline'` are ignored per browser support rules.

**This does not mean any script "called" by a trusted script is automatically safe.** If a root script reads an attacker-controlled URL and creates a script tag from it, `strict-dynamic` can allow loading that malicious script. Even with CSP, you must validate URLs, data, and application dependencies.

A strict CSP can take the form:

```http
Content-Security-Policy: script-src 'nonce-<random-value-per-response>' 'strict-dynamic'; object-src 'none'; base-uri 'none'
```

This is a **descriptive template**, not a string to copy literally into production. Other directives like `connect-src`, `style-src`, `img-src`, `form-action`, and `frame-ancestors` must also be tailored to the app. Older browsers may support different CSP feature subsets; verify against your supported browser matrix.

## 7. Hash-based CSP: suited for immutable inline scripts

Instead of a per-response nonce, for **unchanging** inline scripts the server can place the SHA-256/SHA-384/SHA-512 hash of the **exact script contents** into `script-src`.

Example structure:

```http
Content-Security-Policy: script-src 'sha256-<Base64-of-SHA-256-script-content>'; object-src 'none'; base-uri 'none'
```

An inline script is permitted when the browser hashes its content and matches a source expression in the policy. Changing **even a single space** alters the input bytes and changes the hash; build/template changes can break execution.

**Do not confuse CSP hashes with Subresource Integrity (SRI):**

- A CSP hash source can authorize an inline script with exact content.
- SRI uses the `integrity` attribute on resource-loading elements to verify the content of an external resource. The two mechanisms have related goals but do not fully replace each other.
- For built assets whose hashes change, update the CSP alongside the deployed artifacts.

**Prefer nonces for dynamically generated HTML**, and hashes for small, stable inline script snippets. With SPA builds and bundlers, avoiding inline JavaScript simplifies policy, though a plain `'self'` allowlist is still weaker than strict CSP in some threat models.

### Standalone Java 17 example: hash changes when content changes

Create `CspHashDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

public class CspHashDemo {
    static String cspHash(String script) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(
                script.getBytes(StandardCharsets.UTF_8));
        return "sha256-" + Base64.getEncoder().encodeToString(digest);
    }

    public static void main(String[] args) throws Exception {
        String original = "console.log('ok');";
        String same = "console.log('ok');";
        String changed = "console.log('ok'); ";

        System.out.println("Same content: " +
                cspHash(original).equals(cspHash(same)));
        System.out.println("Extra space changes hash: " +
                !cspHash(original).equals(cspHash(changed)));
        System.out.println("CSP hash prefix: " +
                cspHash(original).startsWith("sha256-"));
    }
}
```

Compile and run with JDK 17+:

```bash
javac CspHashDemo.java
java CspHashDemo
```

Exact output:

```text
Same content: true
Extra space changes hash: true
CSP hash prefix: true
```

This example uses standard Java only and illustrates the byte sensitivity of CSP hashes. In practice, hash the **exact inline script content in the final rendered HTML** per browser rules, not the `<script>` tags or text differing from rendered output.

## 8. Inline scripts, event handlers, and `eval`

The following patterns often break when adopting a strict CSP:

```html
<script>alert("inline script")</script>
<button onclick="submitForm()">Submit</button>
<a href="javascript:submitForm()">Submit</a>
```

With a proper `script-src` disallowing unsafe inline code, these direct execution forms are normally blocked unless explicitly authorized via nonce/hash or related mechanisms. **A nonce on a `<script>` tag does not automatically authorize `onclick` attributes**; refactor event handlers into JavaScript via `addEventListener`.

Fixed example:

```html
<button id="submit-button" type="button">Submit</button>
<script src="/assets/form.js"></script>
```

```javascript
document.querySelector("#submit-button").addEventListener("click", () => {
    // Invoke an allowed action per application logic.
    console.log("Clicked");
});
```

This example requires policy permission for `/assets/form.js` (such as a valid nonce on the script tag in strict CSP, or an allowed source in an allowlist CSP) and an actual `/assets/form.js` file. It illustrates HTML/JS patterns, not a standalone runnable Java program.

`eval(userInput)`, `new Function(userInput)`, and APIs that turn strings into executable code heighten risk. CSP normally blocks them unless `'unsafe-eval'` or a specialized mechanism is permitted. Never turn on `unsafe-eval` as a "quick fix" for framework/bundler errors without analyzing the consequences and production build setup.

**CSP helps block execution**, yet if user data is still interpolated improperly into HTML/JavaScript, the root vulnerability remains. Encode properly for context, eliminate dangerous sinks, and sanitize when user-supplied HTML is genuinely permitted.

## 9. Does Spring Security Servlet enable CSP by default?

**No.** Spring Security provides several HTTP security response headers out of the box, but **does not add a default CSP** because it cannot know each application's script/style sources and requirements. Developers must declare the policy themselves. Thus, "we added the Spring Security dependency" **does not prove** responses carry a CSP.

Example in a **Servlet-based Spring Boot 3 / Spring Security 6 project**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CspSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        String policy = "default-src 'none'; "
                + "script-src 'self'; "
                + "style-src 'self'; "
                + "img-src 'self' data:; "
                + "font-src 'self'; "
                + "connect-src 'self'; "
                + "object-src 'none'; "
                + "base-uri 'self'; "
                + "form-action 'self'; "
                + "frame-ancestors 'none'";

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp
                                .policyDirectives(policy)))
                .build();
    }
}
```

This is a **framework integration configuration** example, not compilable standalone via `javac`. It requires Spring Boot, Spring Security, controllers, security config, and corresponding assets. The illustrative `script-src 'self'` policy is **not a strict nonce-based policy**; it illustrates the Spring API and must be reviewed against your real app before enabling.

When using multiple `SecurityFilterChain` beans, verify `securityMatcher` and chain order. The CSP header must be applied to **appropriate HTML responses**; never configure it solely on a chain for `/api/**` and assume `/dashboard` browser pages receive CSP.

### Observing first: `Report-Only`

Spring Security supports configuring a policy in reporting mode instead of enforcing:

```java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; script-src 'self'; "
            + "object-src 'none'; base-uri 'none'; "
            + "report-uri /csp-report")
        .reportOnly()))
```

This is a **fragment inside `HttpSecurity`**, not a complete class; `reportOnly()` is the appropriate Servlet API per Spring Security 6 documentation. If your project/version differs, check its exact Javadoc. In Report-Only mode, browsers do not block violations caused by that policy. `/csp-report` is an illustrative endpoint; collecting reports requires implementing a properly secured endpoint.

**Never leave `Report-Only` permanently as a substitute for enforcement** when the goal is XSS mitigation via CSP. The standard workflow is observe → fix compatibility → enforce → continue monitoring.

### Generating dynamic nonces with Spring Security

For a **nonce-based strict CSP**, you cannot write a fixed `policyDirectives("script-src 'nonce-ABC'")` for all requests: the nonce value must change for every HTML response. A request/response component must securely generate the nonce, pass it to templates, and put the **same nonce** into the CSP header.

Architectural flow:

```text
Request for HTML page
     |
     v
Server generates fresh random nonce via SecureRandom
     |
     +--> request attribute / template model: cspNonce
     |
     +--> response header: script-src 'nonce-<cspNonce>' ...
     |
     v
Template renders trusted scripts with matching nonce
     |
     v
Browser only accepts scripts satisfying CSP
```

When using a Servlet Filter, consider **when the header is written**, filter scope, and preventing Spring Security or Gateway CSP configs from unexpectedly overwriting or adding duplicate policies. Never attach both a static CSP and a dynamic CSP across multiple layers without inspecting the actual final response.

Java helper illustrating **only nonce generation**, not a full filter setup:

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class CspNonceGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String newNonce() {
        byte[] bytes = new byte[16]; // 128 random bits
        RANDOM.nextBytes(bytes);
        return Base64.getEncoder().encodeToString(bytes);
    }
}
```

In real usage, call `newNonce()` **on every HTML response**, apply the result to both the header and trusted `<script nonce="...">` tags on that response, never store it as a constant, and never accept a nonce from user input. This snippet is a compilable Java helper without `main`; see Section 7 for the standalone runnable Java example.

## 10. What can CSP protect against, and what can it NOT?

### Where CSP helps reduce harm

- An injected inline `<script>` payload **lacking a valid nonce/hash** can be blocked.
- `onerror=...`, `onclick=...`, or `javascript:` URLs can be restricted when inline scripts are disallowed.
- Scripts from origins outside the allowed list/policy can be blocked.
- `object-src 'none'` and `base-uri 'none'` mitigate attack vectors via `<object>` and `<base>` elements.
- `frame-ancestors 'none'` or origin framing limits help reduce clickjacking (a separate goal from XSS).
- `form-action` can restrict form submission targets; `connect-src` restricts certain script network destinations.
- Violation reports help spot suspicious activity or broken assets during rollout.

### What CSP cannot guarantee

1. **Does not replace context-aware output encoding.** Inserting data into HTML bodies, attributes, JS strings, URLs, and CSS each requires distinct escaping/sanitization rules.
2. **Does not automatically eliminate DOM XSS.** Trusted scripts can still pass unsafe data into DOM sinks.
3. **Does not prevent all unauthorized requests caused by XSS.** If trusted JavaScript is manipulated, attackers can abuse behavior already permitted to it, including calling APIs with user privileges.
4. **Does not hide tokens/cookies from running code.** `HttpOnly` hides cookies from `document.cookie`, yet same-origin scripts can still issue requests that send cookies automatically. CSP does not replace session/CSRF/access-control design.
5. **Does not replace CSRF tokens.** CSP can curb certain execution/exfiltration paths, but does not verify user intent on cookie-authenticated requests.
6. **Does not replace authorization.** Pages/APIs must check access permissions per resource rather than relying on browser policy to protect the server.
7. **Does not automatically block all data exfiltration.** `connect-src` does not cover every exfiltration channel; executing XSS can abuse allowed endpoints or legitimate app behavior.
8. **Not all browsers support all directives uniformly.** Check target browsers, extensions, WebViews, and CSP level compatibility.
9. **Does not stop server-side vulnerabilities.** SQL injection, SSRF, authorization logic flaws, and file upload handling are separate issues.
10. **Does not make trusted third-party scripts unconditionally safe.** If an allowlisted CDN or dependency is compromised, the policy may still accept that resource.

**CSP is valuable only when the policy matches trust boundaries and is properly enforced by browsers.** "Having a CSP header" is insufficient to claim effective XSS protection.

## 11. Why do `unsafe-inline`, `unsafe-eval`, and wildcards weaken CSP?

A policy like:

```http
Content-Security-Policy: default-src * data: blob:; script-src * 'unsafe-inline' 'unsafe-eval' data: blob:
```

may let everything work, yet it **drops critical blocking layers against many XSS vectors**. It does not become a strong defensive CSP simply because the browser receives the header.

Common consequences:

- `'unsafe-inline'`: inline payloads and event handlers have far more opportunities to run.
- `'unsafe-eval'`: code can convert untrusted strings into executable JavaScript.
- Broad `*`/`https:`: unreviewed scripts can still be loaded from many origins.
- `data:` or `blob:` in script sources: opens extra script-loading vectors; use only with a clear model and controls.
- Allowlisted third-party scripts: trusted by browsers under policy even if the dependency itself has bugs or gets compromised.

**Do not judge a policy by header length.** A long header packed with wildcards and `unsafe-*` can be less protective than a concise strict CSP using nonces/hashes and disabling objects.

Furthermore, when `'strict-dynamic'` is active, host/scheme allowlists in the same `script-src` can be **ignored** on CSP3 browsers, so developers must understand the semantics before "adding a domain" to fix errors. Avoid mixing policies from multiple CSP generations without verifying target browser behavior.

## 12. DOM XSS and Trusted Types

Even when every `<script>` is authorized by a nonce, valid application JavaScript can still contain unsafe code:

```javascript
const value = new URLSearchParams(location.search).get("message");
document.querySelector("#message").innerHTML = value ?? "";
```

This feeds untrusted URL data straight into the HTML parser via `innerHTML`. CSP might block certain scripts generated from that data, yet **the flaw is using an unsafe DOM sink**.

If only plain text display is needed, a safer approach is:

```javascript
const value = new URLSearchParams(location.search).get("message");
document.querySelector("#message").textContent = value ?? "";
```

`textContent` inserts content as text without parsing it as HTML. This fixes the root bug independently of CSP.

If a feature genuinely needs to render user-supplied HTML, use a **verified, properly configured HTML sanitizer**; never pass arbitrary raw HTML into `innerHTML`.

### What are Trusted Types?

In supporting browsers, **Trusted Types** help govern dangerous DOM XSS sinks by requiring typed objects created via approved policies instead of arbitrary strings. CSP provides directives like:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-policy
```

This illustrative policy requires Trusted Types for applicable sinks and can restrict which Trusted Types policy names may be created. However:

- Trusted Types require **correct application code and sound sanitizer policies**; they do not magically make arbitrary input safe.
- `trusted-types app-policy` does not mean data passing through the policy is safe if the implementation returns unsanitized strings.
- **Browser support varies**; verify target browsers/embedded WebViews and fallback strategies.
- Trusted Types also **do not replace** server-side encoding/sanitization, authorization, and CSP script policies.

Combining sink-safe code, Trusted Types where supported, and strict CSP is generally far stronger than an allowlist CSP header alone.

## 13. Report-Only, violation reports, and rollout workflow

Immediately enforcing a strict CSP on a large site can break features: form validation, analytics, images/fonts, WebSockets, SPA bootstrap code, or template-generated inline tags.

A practical workflow:

1. **Inventory:** Map HTML routes, loaded scripts/styles, inline scripts, inline event handlers, API/WS origins, iframes, form targets, CDNs, and third-party integrations.
2. **Eliminate relaxation triggers:** Move inline handlers to `addEventListener`, avoid `eval`, remove unneeded external script loads, categorize assets.
3. **Choose a model:** Nonce/hash-based strict CSP if feasible, or a narrow allowlist as a transitional step.
4. **Enable `Content-Security-Policy-Report-Only`:** Collect console violations and reporting endpoint telemetry without breaking production right away.
5. **Filter false positives:** Browser extensions, bots, intentionally blocked assets, cached stale builds; correlate against real pages/requests.
6. **Add automated tests:** Verify CSP headers on HTML routes, verify valid scripts still run, verify unauthorized inline scripts are blocked, and test auth/checkout flows.
7. **Roll out enforcement in controlled stages:** Once the policy is measured and clean, switch to `Content-Security-Policy` and keep monitoring violations.
8. **Maintain:** CI/asset pipelines, dependency upgrades, new frontend domains, and new pages must account for CSP; never add wildcards just to "silence errors".

### Violation reports are not definitive proof of an attack

Browser CSP violation reports can come from un-allowlisted legitimate code, browser extensions, or malicious scripts. Conversely, an attack does not necessarily generate a report if the browser lacks reporting support, the network blocks the report, no endpoint is configured, or the attacker uses an allowed flow.

A report collection endpoint must:

- Handle untrusted payloads safely with size limits, rate limiting, and proper storage.
- Avoid over-logging secrets, session cookies, queries containing private data, or unnecessary raw payloads.
- Never treat JSON violation reports as authenticated client evidence.
- Be protected against abuse/DoS; never expose unfiltered report details on public dashboards.

`report-uri` has long existed and remains widely used; `report-to`/Reporting API support varies across browsers. Test in real browsers rather than assuming every violation is reliably delivered to an endpoint.

## 14. CSP across SPAs, CDNs, reverse proxies, and caching

When the frontend is a separately built SPA, a working policy must align the **HTML entrypoint**, script bundles, and runtime:

- **Nonce-based:** The HTML response must be generated or transformed in a controlled way so the header and nonce attributes share a fresh per-response value. Caching HTML at a CDN without properly updating nonces/headers can reuse tokens or cause mismatches.
- **Hash-based:** Stable inline scripts can use build-generated hashes, though changing a single byte requires updating the CSP.
- **External scripts:** With allowlist CSP, `'self'` permits same-origin bundles; with strict CSP, understand how root scripts trusted by nonce/hash load dynamic chunks.
- **Stylesheets:** `style-src` can block CSS-in-JS, style attributes, or framework runtimes; handle via nonces/hashes or refactoring rather than blindly adding `unsafe-inline`.
- **APIs/WebSockets:** `connect-src` must permit real endpoints, though do not treat it as a firewall blocking every type of network request.
- **Fonts/Images:** `font-src` and `img-src` should follow least privilege; review static assets, data URLs, and privacy.
- **Iframes:** `frame-src` defines which pages can be embedded, while `frame-ancestors` defines who may embed your page. They control opposite directions.

If configuring CSP across **Spring Security, reverse proxies, CDNs, and frontend servers** simultaneously, establish one policy owner, avoid unintended duplicate headers, and verify the **final response received by the browser**. Never judge by Java code alone because proxies can add, strip, or alter CSP headers.

For **JSON-only APIs**, a CSP header on a JSON response generally does not protect the main HTML page because browsers enforce CSP bound to the **HTML document** hosting the scripts. Place CSP where browsers render documents and run scripts; do not merely add CSP to `/api/**` and assume the browser UI is protected.

## 15. Comparing CSP with related security layers

| Mechanism | Primary protection | Does NOT replace |
|---|---|---|
| **Context-aware output encoding** | Prevents data from being interpreted as unintended code/markup | Authentication, authorization |
| **HTML sanitization** | Permits a restricted HTML subset, stripping dangerous constructs | Encoding in other contexts, other security policies |
| **CSP** | Restricts load/execution sources, reducing content injection impact | Fixing root XSS flaws, authz, CSRF |
| **Trusted Types** | Mitigates DOM XSS on supported sinks via input type checks | Proper sanitizers/policies and browser coverage |
| **HttpOnly cookies** | Stops scripts from reading auth cookies directly | XSS issuing requests; CSRF |
| **SameSite cookies** | Restricts automatic cookie sending in certain cross-site contexts | XSS, all CSRF forms, authz |
| **CSRF tokens** | Defends against forged cross-site state changes with auto-sent credentials | XSS, output injection |
| **HSTS / HTTPS** | Protects transport connections and prevents downgrades per policy | XSS inside legitimate pages |
| **`frame-ancestors` / X-Frame-Options** | Mitigates clickjacking where supported by browsers | XSS, missing authorization |
| **CORS** | Governs whether cross-origin scripts can read responses | XSS, CSRF, authentication |

Typical case: `Content-Security-Policy: script-src 'self'` may block an attacker-injected inline script, yet if the app itself writes user data to `innerHTML`, you still must fix the DOM sink and validate data. Likewise, a site with a strong CSP but missing backend authorization still suffers from business data exposure.

## 16. Troubleshooting CSP issues in Spring Security

| Symptom | Possible cause | Resolution |
|---|---|---|
| CSP header missing on HTML response | `.headers().contentSecurityPolicy` not configured, chain mismatch, or proxy stripped header | Inspect final Network response and `SecurityFilterChain` |
| Inline script blocked | Missing valid nonce/hash or still using inline handlers | Add matching nonce to trusted scripts, refactor event handlers |
| Script with nonce still blocked | Nonce mismatches header, proxy/cache altered HTML, or blocked by a second policy | Compare response header and script tag within the exact same request |
| External JS blocked | Source missing from `script-src` or `strict-dynamic` changed host allowlist semantics | Adjust trust policy; do not open `*` |
| API fetch blocked despite server 200 | Endpoint missing from `connect-src` or separate CORS error | Inspect console for CSP violations vs CORS errors |
| CSS/Fonts fail to load | `style-src` or `font-src` too restrictive | Audit asset sources, refactor or update specific directive |
| `iframe` fails to render | Parent `frame-src` or child `frame-ancestors` rejected it | Check both directions and both responses |
| Report-Only logs violations yet page still works | Expected Report-Only behavior | Fix violations, then switch to enforce when ready |
| Blank SPA screen after enforcing | Bootstrap inline script blocked, wrong nonce, stale hash after build, stale cache | Test deployments per asset version; perform controlled rollback of broken policy |
| XSS still discovered despite CSP | Weak policy, trusted script gadget abused, unsupported browser, or other flaw | Fix root XSS and audit nonces/hashes/trust boundaries |
| Some pages have different headers | Multiple filter chains, proxy, CDN, or separate frontend server | Audit CSP per HTML route and response layer |
| Violation reports contain sensitive data | Unfiltered logging or URI containing private data | Redact/filter reports and fix URL design |

**Never "fix" issues by immediately adding `'unsafe-inline' 'unsafe-eval' *`.** Those choices defeat CSP's defensive purpose. Identify the exact failing directive and fix the code or trusted sources instead of opening everything globally.

## 17. Testing CSP protection and limits

A safe testing process in an environment you control:

1. **Read the actual headers:** Use Developer Tools → Network, select the **HTML document**, and inspect `Content-Security-Policy` or `Content-Security-Policy-Report-Only`.
2. **Verify syntax:** Check directives have single quotes on `'self'`/`'none'`, contain no overly broad sources, and have no unintended duplicate headers.
3. **Verify valid scripts:** Load pages and run real flows: login, menus, form validation, search, frontend bundles, and approved analytics.
4. **Verify disallowed scripts:** On **your app's own test page**, create an inline script **without a nonce/hash** and confirm it is blocked in enforce mode—not merely logging a Report-Only warning.
5. **Verify nonces/hashes:** With strict CSP, nonces must be fresh per response and match valid scripts; with hashes, changing one byte must cause blocking due to mismatch.
6. **Verify each source type:** Test `form-action`, iframes, fonts, images, and `connect-src` across routes using those features.
7. **Verify supported browsers:** Test target desktop/mobile browsers and WebViews, noting differences in CSP3, Trusted Types, and reporting.
8. **Verify root fixes:** Review how user input flows into HTML/JS/DOM sinks; never treat "CSP blocked a sample payload" as proof that no XSS exists.
9. **Verify proxies/caches:** Compare HTML response nonces with CSP headers on the exact same request through CDNs/reverse proxies.
10. **Verify reporting/telemetry:** Ensure report endpoints do not leak secrets and cannot be abused with excessive spam.

Example command to inspect headers on **your own website or authorized test environment**:

```bash
curl -I https://portal.example.test/
```

The domain `example.test` is illustrative only; replace it with a real endpoint. `curl` can read HTTP headers yet **does not enforce CSP like a browser**; actual CSP enforcement must be verified in a browser.

### Pre-production review questions

- Are there any inline scripts without a nonce or hash? If so, why can't they move to external files or use nonces/hashes?
- Is the nonce generated with sufficient randomness **per response** and placed identically in both header and template?
- Are `unsafe-inline`, `unsafe-eval`, `https:`, `data:`, `blob:`, or `*` present in `script-src`? Is there a reviewed security justification?
- Does the policy rely on a CDN or same-origin user uploads that CSP could inadvertently trust?
- Do `object-src 'none'`, `base-uri`, and `frame-ancestors` meet requirements?
- Are any auth, form, or API paths broken by `form-action` or `connect-src`?
- Are multiple CSP headers being emitted from different infrastructure layers?
- Is user data properly encoded/sanitized before rendering?
- Is there a plan for handling violation reports, frontend changes, and browser support?

## 18. Self-check questions

**1. Does CSP prevent every XSS attack?** No. It reduces certain unauthorized script execution and resource loading vectors; abused trusted code, overly broad policies, or out-of-scope flaws can still cause harm. Incorrect output/DOM sinks must still be fixed.

**2. Why doesn't Spring Security enable CSP by default?** Every application uses different script/style/frame/API sources, so no single strict policy fits all; developers must define it.

**3. How do `Content-Security-Policy` and `Content-Security-Policy-Report-Only` differ?** The first enforces and blocks according to policy; the second monitors violations without blocking solely due to that Report-Only policy.

**4. Is `script-src 'self'` always a strict CSP?** No. It is an origin allowlist and remains risky if the same origin serves unsafe scripts. Strict CSP typically uses nonces/hashes with additional directives.

**5. How often should a nonce be generated?** Fresh for each HTML response using a cryptographic random generator, with the same value placed in that response's header and scripts.

**6. Does a CSP nonce automatically permit inline event handlers?** No. `onclick`/inline handlers must be refactored or governed by dedicated policy mechanisms rather than being allowed just because another script has a nonce.

**7. What does `strict-dynamic` mean?** In CSP3, trust from a nonce/hash can propagate to scripts dynamically loaded by a root script, while host/scheme allowlists are ignored in that directive. It does not fix vulnerabilities in the root script.

**8. Does `frame-ancestors` fall back to `default-src`?** No; it must be declared explicitly if you want to restrict who may embed your page.

**9. Does CSP replace CSRF tokens, authentication, or authorization?** No. They address different responsibilities.

**10. If a page shows zero CSP violation warnings, is it free of XSS?** Not necessarily. The policy might be ineffective, reporting might be absent, browsers might lack support, or an exploit might not trigger a violation.

**Conclusion:** **CSP is a complementary browser defense layer, not a patch for every XSS flaw.** Prioritize fixing output encoding and DOM sinks, then design a tight CSP with appropriate nonces/hashes, eliminate `unsafe-inline` and `unsafe-eval` where feasible, roll out via `Report-Only` → enforce, and continue real-world testing.

## References

- [Spring Security — Security HTTP Response Headers (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): CSP configuration, Report-Only, and security headers.
- [Spring Security — Security HTTP Response Headers (Features)](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): CSP mitigates content injection/XSS; does not replace input/output handling.
- [MDN — Content Security Policy (CSP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): directives, nonces, hashes, strict-dynamic, and testing.
- [MDN — Content-Security-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy): syntax, fallback behavior, and source expressions.
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): building defense-in-depth CSP and rollout roadmap.
- [OWASP — Cross-Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): output encoding, sanitization, DOM XSS, and CSP limits.
