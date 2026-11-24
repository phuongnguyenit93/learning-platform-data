# Security headers and risk mitigation scope

## 1. What are security headers and why is HTTPS alone not enough?

An application may already use **HTTPS**, authenticate with Spring Security, authorize endpoints, and check CSRF, yet the browser still needs to know how to handle the **response content**. For example:
- May the page be embedded in an **iframe** on another website?
- May a file be interpreted as JavaScript even if the server declares a different MIME type?
- Which **origins** are allowed for scripts, styles, images, or connections?
- May the browser send a **Referer** containing the previous page's path to another site?
- May the page use the camera, microphone, or geolocation?
- May sensitive documents be stored in the browser's cache?
- Should the browser enforce HTTPS for future connections to the domain?

These decisions can be communicated to the browser using **HTTP response security headers**. For example:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
~~~

This is an **illustrative example for a single response**, not a list of headers present out of the box in every application. Some headers are added by Spring Security by default; some must be explicitly configured; and some only take effect under specific conditions.

**Important principle:** security headers are a **risk mitigation and defense-in-depth layer**, not a cure-all for every vulnerability. A good header does not replace Authentication, Authorization, CSRF protection, output encoding, input validation, dependency management, per-record permission checks, or TLS configuration.

### Learning objectives

After this lesson, you will be able to:
1. Explain that **security headers are response headers** and describe the browser's role.
2. Accurately distinguish between **Spring Security 6.x default headers** and **headers that must be explicitly enabled**.
3. State the risks mitigated by each header along with the risks **it does not solve**.
4. Design a Content-Security-Policy (CSP) compatible with real HTML, JavaScript, and services.
5. Understand HSTS, clickjacking, MIME sniffing, caching, Referrer-Policy, Permissions-Policy, and isolation headers.
6. Run a Spring Boot 3.x / Spring Security 6.x / Java 17+ example that adds CSP and verify headers via curl/MockMvc.
7. Distinguish security headers from cookie flags, CORS, CSRF, and Bearer authentication.
8. Audit reverse proxies/CDNs, redirects, 401/403/500 responses, static resources, and browser policies.

> Technical scope: examples use **Spring MVC/Servlet** and the Spring Security **6.x** configuration API. Spring WebFlux uses SecurityWebFilterChain and ServerHttpSecurity, rather than copying Servlet's HttpSecurity verbatim.

## 2. Who emits headers and who enforces them?

An HTTP response can pass through multiple components:

~~~text
Browser
   ^
   | HTTP response + security headers
   |
Reverse proxy / CDN / API gateway
   ^
   | Response from Spring Boot
   |
Spring Security FilterChainProxy / HeaderWriterFilter
   ^
   | Security headers added/modified per configuration
   |
Spring MVC Controller / static resource / error handler
~~~

**Spring Security** can write the relevant headers to the response. A **reverse proxy or CDN** can add, modify, remove, or overwrite those headers. The **browser** decides how to apply them: blocking iframes, enforcing CSP, preventing MIME sniffing, omitting Referer per policy, or upgrading HTTP to HTTPS per HSTS.

Therefore, you must inspect the response **actually reaching the browser**, not just read Java code:
- Are headers sent on the required **HTML, CSS/JS, API, and error responses**?
- Are headers correct over **HTTPS** behind the reverse proxy?
- Is any header written twice with conflicting policies?
- Is the header enforced by target browsers?
- Does CSP break legitimate scripts or styles in practice?

Not every HTTP client understands or enforces every security header. **curl** can display headers, but it does not enforce CSP or block iframes. Therefore, testing should combine HTTP-level assertions with browser DevTools/E2E tests.

### 2.1. Response headers differ from request headers

In an example, the browser sends:

~~~http
GET / HTTP/1.1
Host: app.example.com
Accept: text/html
Cookie: JSESSIONID=...
~~~

The server returns:

~~~http
HTTP/1.1 200 OK
Content-Security-Policy: default-src 'self'; script-src 'self'
X-Frame-Options: DENY
~~~

**Content-Security-Policy and X-Frame-Options are response headers.** They are not credentials, nor are they request headers for a client to self-declare "I am safe". An attacker sending a header named X-Frame-Options in a request does not cause the server to trust that the request is authenticated.

## 3. Default headers in Spring Security 6.x

Spring Security provides a default set of security response headers for **responses passing through the Spring Security filter chain**. Per the Spring Security 6.x documentation, the list typically includes:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
X-Frame-Options: DENY
X-XSS-Protection: 0
~~~

**Important exception:** Spring Security only writes **Strict-Transport-Security** for **requests recognized as HTTPS/secure**, and does not write HSTS as shown above on plain HTTP responses on localhost. Exact whitespace or formatting of header values may vary slightly across versions/servers, so test the semantic configuration rather than matching irrelevant whitespace strings.

Summary table:

| Default header | Mitigation goal | What cannot be inferred |
| --- | --- | --- |
| Cache-Control, Pragma, Expires | Restrict caching of sensitive responses | Cannot be treated as wiping data from every existing device or cache |
| X-Content-Type-Options: nosniff | Reduce the risk of the browser guessing the wrong MIME type, especially for scripts/styles | Does not auto-fix an incorrect Content-Type or prevent all XSS |
| Strict-Transport-Security | Help the browser remember to use HTTPS for the host after receiving a valid policy | Does not install TLS itself or eliminate all risks on the initial HTTP connection |
| X-Frame-Options: DENY | Prevent the page from being embedded in a frame where supported by the browser | Does not prevent all clickjacking if other flows remain vulnerable |
| X-XSS-Protection: 0 | Disable legacy XSS filters that are no longer trusted in modern browsers | **Does not enable an XSS protection filter** |

**Not included by default:** Spring Security does not pick a **CSP** suited to every website; **Referrer-Policy** and **Permissions-Policy** also need configuration when an application wants to use them. These policies depend on page structure, scripts/CDNs, features, and the specific threat model.

### 3.1. Do not disable all headers to fix one feature

The following snippet is an **anti-pattern** and should not be shipped to production just to make a page render:

~~~java
http.headers(headers -> headers.disable());
~~~

This disables **all** Spring Security header writers in that chain. When a specific header needs to change, configure **that header** or a specific URL group; there is no need to discard all default defenses.

### 3.2. permitAll differs from web.ignoring

For public static assets:

~~~java
.requestMatchers("/assets/**").permitAll()
~~~

is usually preferable to excluding **/assets/** completely from Spring Security via **web.ignoring()**. With **permitAll**, the request still traverses the filter chain, so the chain's security headers can still be applied. With ignoring, the Spring Security filter chain does not run on that URL, so **HeaderWriterFilter cannot automatically add headers to the bypassed response**.

If using a CDN or static hosting outside Spring Boot, you must explicitly configure the corresponding security headers where the content is actually served. Do not assume Java config affects responses from an independent CDN.

## 4. Cache-Control: avoiding retention of sensitive data

Responses containing the following information should generally not be retained by browser/shared caches:
- Account pages, bank statements, personal contact details.
- APIs containing user data, internal reports, or administrative privileges.
- Responses containing session-sensitive information.
- Content that a logged-out user should not be able to easily view again via caching.

Spring Security uses these default cache-control headers:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

**no-store** is the directive instructing caches not to store the response; **no-cache** means not reusing content without revalidation, **not "do not store"**. The Pragma and Expires headers generally aid compatibility with older clients/caches. Compliance varies by browser, proxy, cache, and software version.

### 4.1. Headers do not replace logout and data deletion

Cache-Control does not guarantee that previously downloaded data will be erased from:
- Memory of an already open browser tab.
- Files or screenshots the user downloaded.
- LocalStorage or IndexedDB written by the application itself.
- Third-party memory, disks, or backups.
- Application-managed caches or service workers that do not follow simple assumptions.

For proper logout, you must still invalidate sessions/tokens where appropriate, clear client data by design, and test that no sensitive data is retained unintentionally.

### 4.2. Static CSS/JS typically need different caching from sensitive HTML

Spring Security's default Cache-Control is fairly conservative. However, a JavaScript bundle with a content-hashed filename, such as **app.a1b2c3.js**, can be cached long-term for performance.

You can design policies as follows:
- **HTML with personal data:** cache-control no-store.
- **Sensitive APIs:** no-store.
- **Versioned CSS/JS:** long-lived or immutable caching if the origin and deployment pipeline are appropriate.
- **Public images:** cache as needed, rather than using the same policy as private files.

Spring MVC resource handlers, a reverse proxy, or a CDN can set cache policies for assets. **Do not disable Spring Security's global cache-control just to cache a few CSS files.** For paths with private data, prefer a conservative policy.

## 5. X-Content-Type-Options: nosniff

The header:

~~~http
X-Content-Type-Options: nosniff
~~~

helps reduce **MIME sniffing** risk: browsers should not guess or interpret certain resources, particularly scripts and stylesheets, differently from the MIME type declared by the server.

Risk example: an uploaded file containing content could be interpreted as JavaScript if served with an inaccurate content type and sniffed by the browser. Forcing the browser to rely on the declared MIME type helps mitigate this class of attack.

### Key things to understand accurately

- **nosniff does not set the correct Content-Type by itself**. The backend must still return **text/javascript** (or an appropriate JavaScript MIME type) for scripts, **text/css** for stylesheets, **application/json** for JSON APIs, etc.
- Browsers may block loading scripts/styles if the MIME type is wrong, making the UI appear "broken" after enabling the header. The proper fix is to **fix the Content-Type**, not arbitrarily turn off nosniff.
- This header does not protect against every dangerous upload scenario. Uploads still require **file type validation**, storage isolation, access control, proper Content-Disposition headers, a separate domain when needed, and preventing execution of untrusted content.
- Never serve user-controlled uploaded files as same-origin scripts with full privileges.

### X-Content-Type-Options differs from Content-Type

~~~http
Content-Type: text/css
X-Content-Type-Options: nosniff
~~~

**Content-Type** states what type the resource is; **nosniff** tells the browser not to infer a different type from the declaration. The two headers complement each other.

## 6. X-Frame-Options and clickjacking

**Clickjacking** occurs when an untrusted page tries to place the real UI of a target application inside an iframe/layer and tricks the user into clicking a button or performing an unintended action. The browser may still send session cookies to the embedded application depending on cookie policy, making the action more dangerous.

By default, Spring Security typically sends:

~~~http
X-Frame-Options: DENY
~~~

Available options include:
- **DENY:** prevents the page from being embedded in a frame, even by the same origin.
- **SAMEORIGIN:** allows framing under same-origin conditions defined by the header mechanism.
- **ALLOW-FROM:** legacy syntax not reliably supported by modern browsers; should not be chosen as a modern origin allowlist solution.

**If the app legitimately needs a page embedded in an iframe**, do not open the entire system just to support one page:
1. Identify **which subpages may be embedded** and **which origins are allowed to embed them**.
2. Consider using the CSP **frame-ancestors** directive on the embedded page's response.
3. Adjust X-Frame-Options to be compatible with the design; do not leave default DENY conflicting with a valid embedding policy in target browsers.
4. Test for clickjacking, sensitive paths, and browser support.

### 6.1. CSP frame-ancestors is usually more flexible

For example:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.org
~~~

This directive declares **which origins are allowed to embed the current response**. It is **not** the same as **frame-src**, which controls **which frames the current page is allowed to load**. They control opposite directions.

For pages that must never be embedded:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

This pair of headers provides protection in browsers that support each mechanism. You must not infer that clickjacking is eliminated across all interactive UIs if the application still has permission, CSRF, UX, or browser-specific risks.

**Technical note:** CSP **frame-ancestors** is enforced via a response header; placing that directive in an HTML meta tag does not provide equivalent enforcement.

## 7. HSTS: forcing subsequent connections to use HTTPS

**HTTP Strict Transport Security (HSTS)** tells the browser that a host must be accessed over HTTPS for a specified duration.

For example:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Meaning:
- **max-age=31536000:** the browser remembers the policy for roughly one year.
- **includeSubDomains:** extends the scope to all corresponding subdomains.
- **preload:** signals eligibility for the HSTS preload list registration process; simply adding the word preload does not automatically add the domain to browser preload lists.

### 7.1. Spring Security only adds HSTS when the request is considered HTTPS

HSTS only takes effect from a response received **over a trusted HTTPS connection**. By default, Spring Security does not send HSTS when handling plain HTTP requests on localhost.

~~~text
Browser --HTTP--> Server
    An HSTS header over HTTP cannot be treated as a trusted policy

Browser --HTTPS--> Server
    Server can send HSTS
    Browser remembers the policy for subsequent visits
~~~

Therefore, running:

~~~bash
curl -i http://localhost:8080/
~~~

and not seeing **Strict-Transport-Security** is **normal** in an HTTP demo. This is not evidence that HSTS has been disabled.

### 7.2. HSTS does not replace TLS and HTTPS redirects

HSTS **does not install HTTPS/TLS itself**, generate certificates, or fix proxy misconfigurations. You still need to:
- Provision valid TLS certificates and maintain a renewal process.
- Redirect HTTP to HTTPS per policy.
- Protect traffic between the proxy and backend appropriately.
- Restrict mixed content.
- Avoid issuing cookies or credentials over HTTP.
- Test the application over real HTTPS.

If the browser has never received a valid HSTS policy and the domain is not on the preload list, the **very first HTTP request** remains an attack surface prior to redirection. HSTS preload can mitigate this case, but it is a long-term decision with strict prerequisites and its own registration process.

### 7.3. Risks from includeSubDomains and preload

Do not enable **includeSubDomains** or **preload** merely because a scoring tool recommends it:
- You must ensure **every subdomain in scope** supports HTTPS, including legacy hosts, internal services, or rarely used subdomains.
- A misconfigured HSTS policy with a large max-age can lock browsers out of an HTTP-only host until the policy expires or is properly resolved.
- Preload has broad impact and is hard to reverse quickly; you must verify requirements and full DNS/HTTPS ownership.
- Roll out cautiously in phases rather than applying a one-year policy across unaudited infrastructure.

### 7.4. A reverse proxy can break request.isSecure()

Common architecture:

~~~text
Browser -- HTTPS --> Load Balancer / Reverse Proxy
                            |
                            | Internal HTTP
                            v
                      Spring Boot
~~~

If Spring Boot does not accurately detect the **original HTTPS scheme** via trusted proxy information, Spring Security may think the request is HTTP and **omit HSTS**, even though the browser connected via HTTPS.

Spring Boot can be configured to support forwarded headers, for example via the **server.forward-headers-strategy** property depending on the environment. You must ensure the proxy **strips or overwrites untrusted forwarded headers from the Internet**, rather than letting clients spoof X-Forwarded-Proto.

**Verify headers at the public endpoint behind the proxy**, not just on internal HTTP localhost. HSTS can also be added at the edge; decide which component owns it to avoid duplicate or inconsistent policies.

## 8. Content Security Policy (CSP): content injection mitigation layer

**Content-Security-Policy** is one of the strongest proactive headers for reducing the impact of **XSS/content injection** and controlling where a page can load resources from.

For example:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

The goal is to instruct the browser:
- Load scripts only from the page's origin per policy.
- Load CSS only from the page's origin.
- Disallow loading legacy object/embed content.
- Restrict other resources by default.
- Disallow embedding the page in a frame.

**Spring Security does not generate a default CSP**, because the right policy depends precisely on how the page uses JS/CSS, images, CDNs, APIs, and third-party integrations.

### 8.1. CSP is not a filter that sanitizes XSS payloads

CSP is **defense-in-depth**, not the sole mechanism to prevent injection:
- You must still **escape HTML, JavaScript, URLs, and CSS for the proper output context**.
- Never render user-controlled HTML without sanitizing/encoding.
- Avoid DOM XSS such as passing untrusted data into **innerHTML**, **eval**, or dynamic script execution.
- Use template engines/frameworks with safe escaping mechanisms and review any bypass APIs.
- Do not use CSP as a substitute for authorization or CSRF protection.

If an attacker finds a way to execute scripts within the allowed policy (for example via an abusable trusted script source), CSP can still be bypassed. Policies containing **'unsafe-inline'** or **'unsafe-eval'** generally weaken the goal of mitigating XSS.

### 8.2. Common directives

| Directive | Controls | Practical notes |
| --- | --- | --- |
| **default-src** | Fallback for many undeclared fetch directives | Does not cover every category with a single directive |
| **script-src** | Script sources and certain script execution forms | Prefer controlled external scripts, or nonces/hashes when needed |
| **style-src** | Stylesheet/style sources | Inline CSS may be blocked; design policy to fit the UI |
| **img-src** | Image sources | Consider data: only if the app genuinely needs it |
| **connect-src** | URLs the page's fetch/XHR/WebSocket/EventSource... may connect to | **Does not replace CORS on the target server** |
| **font-src** | Web font sources | Font CDNs may require specific origins |
| **object-src** | Plugins/object/embed | For most modern sites, use **'none'** |
| **base-uri** | Restricts the HTML base URL | Reduces risk of redirecting relative resources via an untrusted base tag |
| **form-action** | Allowed targets for form submission | Useful for login/registration/checkout |
| **frame-ancestors** | Origins allowed to embed the current page | Different from frame-src; does not fall back to default-src |
| **frame-src** | Frames the current page is allowed to embed | Do not use it in place of frame-ancestors |
| **upgrade-insecure-requests** | Hints upgrading HTTP resource URLs to HTTPS | Must be tested with HTTPS-capable infrastructure |

**'self'** refers to the page's origin, not "same company" or "all subdomains". **'none'** blocks all sources for that directive. An overly permissive policy with wildcards can still leave injection paths open; an overly strict policy can break the UI.

### 8.3. CSP should be present on the HTML document

The CSP returned in an HTML response is the policy the browser uses to restrict resource loading and execution for **that HTML document**. A CSP header on a JSON API response **does not lock down scripts running in a document on another origin**.

For an SPA's main page, you must inspect the policy actually delivered on the **HTML entrypoint** from the CDN/server, even when JSON APIs are served by Spring Boot on another origin.

### 8.4. Restrictions on inline scripts and inline styles

Consider this HTML:

~~~html
<button onclick="save()">Save</button>
<script>
  function save() { console.log("saved"); }
</script>
~~~

Under the policy:

~~~text
script-src 'self'
~~~

modern browsers will block these forms of inline scripts and inline event handlers. This is **intentional protective behavior**, not necessarily a Spring Security bug.

Replace them with an external script and DOM APIs:

~~~html
<button id="save">Save</button>
<script src="/assets/app.js" defer></script>
~~~

~~~javascript
document.getElementById("save")
    .addEventListener("click", function () {
        console.log("saved");
    });
~~~

Some frameworks require inline bootstrap scripts or dynamic styles. In those cases, design **per-request/policy nonces or hashes** integrated with rendering, rather than adding **'unsafe-inline'** for the entire page by default.

**A nonce must have sufficient entropy and change per protected response**, not be a fixed hard-coded string in source code. A CSP nonce token is **different from a CSRF token**; never reuse one value for both mechanisms.

### 8.5. Test CSP with Report-Only before enforcing

During rollout:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'
~~~

The browser can **log/report violations without blocking resources under the report-only policy**. After reviewing logs/DevTools, updating valid resource sources, eliminating unsafe-inline, and testing thoroughly, switch to:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'
~~~

**Report-Only and enforce are two separate response headers.** Setting Report-Only alone does not mean the browser is blocking dangerous scripts. When collecting violation reports, limit sensitive data and log volume; reports can be noisy and are neither always complete nor proof of a successful attack.

### 8.6. CSP must be tested with the real product

Components commonly affected:
- CDN scripts/styles, web fonts, image proxies.
- Inline code generated by SSR or template engines.
- Analytics tools, tag managers, payment widgets, and support chat.
- Cross-origin WebSocket/API URLs via connect-src.
- WASM and code evaluation depending on technology stack.
- Embedded iframes and payment providers.
- Dev tooling/hot reload in development environments.

Do not copy another application's policy into production and mark it passed simply because a header is present. **The policy must be derived from the real asset graph and set of origins**, while trimming unnecessary permissions.

## 9. Referrer-Policy: reducing information leakage in Referer

Browsers can send a **Referer** request header indicating the previous page when navigating or loading resources. The previous page's URL sometimes contains sensitive information in the path or query, such as a poorly designed access token.

The response header:

~~~http
Referrer-Policy: no-referrer
~~~

can instruct the browser not to send Referer on relevant requests according to that policy.

Common choices:
- **no-referrer:** do not send Referer.
- **same-origin:** send Referer only when the target is same-origin per specification.
- **strict-origin-when-cross-origin:** typically sends the full URL for same-origin, trims down to the origin for secure cross-origin, and omits it on downgrade paths.
- **origin:** sends the origin instead of the full URL depending on context.

Choose the policy based on analytics, referral needs, product requirements, and sensitivity level. **Spring Security does not add Referrer-Policy by default**; configure it if the application wants a specific policy.

**Limitations:** the header does not erase previously leaked data, does not eliminate leaks from URLs shared directly, and cannot guarantee compliance by every client. A safer design is still to **never put access tokens, session IDs, or secrets into URL queries or paths**.

### Referrer-Policy is not CORS

CORS governs whether browser scripts can read cross-origin responses. Referrer-Policy governs what navigation/request source information is disclosed in Referer. Their goals and scopes are distinct.

## 10. Permissions-Policy: controlling permission to use browser features

The response header:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=()
~~~

can restrict a document and certain embedded contexts from using browser features such as camera, microphone, and geolocation, depending on the policy and browser support.

The **()** in the example means no origin is allowed to use the corresponding feature within the policy scope. An allowlist of permitted origins can be specified for particular use cases.

**This header does not replace user consent**: even if a feature is allowed by the policy, the browser may still prompt the user for permission and apply other conditions. Conversely, if the policy blocks a feature, the fact that the user previously clicked Allow does not let the page bypass the restriction.

Spring Security 6.x has DSL support for **permissionsPolicy(...)**, but it **cannot know which camera/microphone/geolocation features the app needs**, so the application must choose the policy. Browser support can vary across directives; test on target browsers.

## 11. Cross-Origin-Opener/Embedder/Resource Policy (COOP/COEP/CORP)

Beyond the basic headers, there are headers for **cross-origin isolation** and restricting how resources are embedded or shared:

| Header | Primary goal | Risk of blanket rollout |
| --- | --- | --- |
| **Cross-Origin-Opener-Policy (COOP)** | Control a page's browsing context relationship with cross-origin documents, reducing window/opener interaction risks | May break login popups, payment popups, and external integrations |
| **Cross-Origin-Embedder-Policy (COEP)** | Require conditions for embedding cross-origin resources using policies like require-corp/credentialless | May break third-party resources that do not send suitable CORS/CORP headers |
| **Cross-Origin-Resource-Policy (CORP)** | Let a resource producer restrict embedding of a resource in cross-origin/cross-site contexts for certain requests | May block legitimate shared CDNs or resources |

Illustrative header examples:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Resource-Policy: same-origin
~~~

**Do not treat this trio as something to enable by default on every site.** Cross-origin isolation may be needed for specialized browser APIs, but it requires coordination across all resources and popup/frame flows. If the system uses OIDC popups or third-party widgets, incompatible COOP/COEP can break functionality.

These headers **differ from CORS**: CORS is the browser mechanism allowing scripts to read cross-origin responses when permitted by the server; CORP/COEP/COOP add constraints on how resources and browsing contexts interact. Spring Security supports configuring them, but enable them only based on your threat model and compatibility testing.

## 12. Headers that are not recommended modern solutions

### 12.1. X-XSS-Protection: 0 does not mean enabling "XSS protection"

The default header:

~~~http
X-XSS-Protection: 0
~~~

explicitly **disables a legacy XSS filter** on browsers that still support it. Such filters have been removed or deprecated in many browsers and can introduce security or semantic issues if forcibly re-enabled.

Modern XSS handling consists of:
- Context-aware output encoding.
- Eliminating HTML/JavaScript injection and DOM XSS sinks.
- Strict CSP where compatible.
- Sanitization when rendering user-supplied HTML is truly necessary.
- Minimizing external script dependencies and keeping libraries updated.

Do not use **X-XSS-Protection: 1** as a claim of stronger XSS protection than the default policy.

### 12.2. HPKP (HTTP Public Key Pinning) should not be deployed anew

HPKP previously allowed pinning public keys in browsers, but browsers removed support for it and it carries the risk of locking users out of a site if keys are mismanaged. Spring Security 6.x still retains related historical docs/APIs, but **HPKP should not be used as a new hardening standard**.

For HTTPS, prioritize certificate management, appropriate HSTS, Certificate Transparency/infrastructure protection where needed, and a controlled key rotation process.

### 12.3. X-Frame-Options and CSP cannot fix backend authorization

Disallowing iframes does not stop an authenticated user from intentionally sending unauthorized POST requests; a strong CSP does not make a reporting API understand roles. Authentication and Authorization are still decided by backend/security policies. This is an important boundary when evaluating the effectiveness of security headers.

## 13. Spring Boot 3.x + Spring Security 6.x: complete demo

The demo includes:
- **GET /**: HTML page loading CSS/JS from the same origin.
- **GET /assets/site.css** and **GET /assets/app.js**: permitted static resources.
- **GET /api/public**: public JSON API.
- **GET /api/private**: requires HTTP Basic with a test account.
- Default Spring Security headers.
- **Application-configured CSP**, disallowing inline scripts and framing.
- **Referrer-Policy: no-referrer**.
- **Permissions-Policy** blocking camera/microphone/geolocation.

We intentionally **do not enable COOP/COEP/CORP across the board** because there is no cross-origin isolation requirement in the demo. We keep default HSTS unchanged: over localhost HTTP, HSTS is not emitted.

### 13.1. Create the project

Use Spring Initializr:
- **Java 17+**, **Spring Boot 3.x**, **Gradle**.
- Group **com.example**, artifact **demo**, package **com.example.demo**.
- Dependencies **Spring Web** and **Spring Security**.

Create the files:

~~~text
src/main/java/com/example/demo/SecurityHeadersDemoApplication.java
src/main/resources/static/assets/site.css
src/main/resources/static/assets/app.js
~~~

Use the Gradle wrapper and dependencies generated by Spring Initializr. If you initialize the artifact with a different name, make sure the **package** and **file paths** in the code match.

### 13.2. Complete Java backend

Put all the code below into **src/main/java/com/example/demo/SecurityHeadersDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter.ReferrerPolicy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityHeadersDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityHeadersDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityHeadersConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/", "/assets/**", "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/private")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .headers(headers -> headers
                // Keep header defaults, only add app-specific policies.
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "style-src 'self'; " +
                        "img-src 'self'; " +
                        "connect-src 'self'; " +
                        "object-src 'none'; " +
                        "base-uri 'self'; " +
                        "form-action 'self'; " +
                        "frame-ancestors 'none'"))
                .referrerPolicy(referrer -> referrer
                    .policy(ReferrerPolicy.NO_REFERRER))
                .permissionsPolicy(permissions -> permissions
                    .policy("camera=(), microphone=(), " +
                            "geolocation=()")))
            .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}demo123")
                .roles("USER")
                .build());
    }
}

@RestController
class DemoController {

    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    String page() {
        return """
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="UTF-8">
              <meta name="viewport"
                    content="width=device-width, initial-scale=1">
              <title>Security Headers Demo</title>
              <link rel="stylesheet" href="/assets/site.css">
              <script defer src="/assets/app.js"></script>
            </head>
            <body>
              <main>
                <h1>Security headers are being applied</h1>
                <p>JavaScript and CSS load from the same origin.</p>
                <button id="load">Read public API</button>
                <pre id="result">Click the button to load data.</pre>
              </main>
            </body>
            </html>
            """;
    }

    @GetMapping("/api/public")
    Map<String, String> publicData() {
        return Map.of("message", "public-data");
    }

    @GetMapping("/api/private")
    Map<String, String> privateData(Authentication auth) {
        return Map.of(
            "username", auth.getName(),
            "message", "authenticated-data");
    }
}
~~~

**Code explanation:**

1. The public class **SecurityHeadersDemoApplication** matches the filename; the other two classes are package-private in the same package and picked up by Spring component scan.
2. **@EnableWebSecurity** and SecurityFilterChain enable Spring Security Servlet. The public **permitAll** endpoints still traverse the filter chain; the private endpoint requires authentication.
3. **httpBasic** is used only to demonstrate that the server still verifies identity alongside security headers; **{noop}demo123** is solely for local learning and must never be used to store production passwords.
4. **headers(...)** does not call **defaultsDisabled()** or **disable()**, so default headers are retained while new policies are added.
5. **CSP** allows JS/CSS/images and connections only from the same origin; the demo's external JS/CSS comply with this policy. There are no inline event handlers or inline scripts.
6. Default **X-Frame-Options: DENY** and **frame-ancestors 'none'** both prevent page framing. Third-party embedding is not enabled.
7. **ReferrerPolicy.NO_REFERRER** instructs the browser not to disclose Referer per policy.
8. **Permissions-Policy** restricts three features unneeded by the demo.
9. **HSTS** remains managed by default and only appears if the request is marked HTTPS/secure; local HTTP 8080 does not include HSTS.
10. **CSRF** is not disabled because there are no state-changing POST/PUT/DELETE operations. If state-changing requests are added, CSRF must be designed according to the credential/browser threat model.

### 13.3. CSS in static/assets/site.css

Create **src/main/resources/static/assets/site.css**:

~~~css
body {
    margin: 0;
    padding: 32px;
    background: #f4f6fa;
    color: #263244;
    font-family: Arial, sans-serif;
}
main {
    background: white;
    padding: 24px;
    max-width: 560px;
    margin: auto;
    border-radius: 12px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.08);
}
button {
    padding: 10px 16px;
    cursor: pointer;
}
pre {
    white-space: pre-wrap;
    background: #eef1f5;
    padding: 12px;
}
~~~

With Spring Boot MVC's default static resource serving, the file path **static/assets/site.css** is served at URL **/assets/site.css** (without `/static` in the URL).

### 13.4. JavaScript in static/assets/app.js

Create **src/main/resources/static/assets/app.js**:

~~~javascript
"use strict";

const button = document.getElementById("load");
const result = document.getElementById("result");

button.addEventListener("click", async function () {
    try {
        const response = await fetch("/api/public");
        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }
        const data = await response.json();
        result.textContent = data.message;
    } catch (error) {
        result.textContent = "Error: " + error.message;
    }
});
~~~

**textContent** displays text without parsing API data as HTML. This aligns with DOM XSS prevention principles; never switch to **innerHTML** merely for convenience when inserting untrusted content.

Because there is no inline JavaScript, CSP **script-src 'self'** allows loading app.js. If you replace the script with inline JS, DevTools will report a CSP violation.

### 13.5. Running the application

In the Gradle project root:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

By default it is accessible at **http://localhost:8080** unless `server.port` is changed.

Open a browser at **http://localhost:8080**:
1. The HTML page renders.
2. CSS loads from /assets/site.css.
3. JS loads from /assets/app.js.
4. Click the **Read public API** button: the script fetches /api/public and displays **public-data**.
5. Open DevTools > Network > select the **/** document request and inspect the **Response Headers** tab.
6. Open DevTools > Console and verify there are no CSP violations from the sample code.

**This is expected behavior from the source code**, not observed output from running the application in your environment.

## 14. Testing security headers with curl

### 14.1. Inspecting headers on the HTML page

~~~bash
curl -i http://localhost:8080/
~~~

Per the configuration, the response is **HTTP 200** and typically includes:
- **X-Content-Type-Options: nosniff**.
- **X-Frame-Options: DENY**.
- **X-XSS-Protection: 0**.
- **Cache-Control** containing **no-store**.
- **Content-Security-Policy** containing **script-src 'self'** and **frame-ancestors 'none'**.
- **Referrer-Policy: no-referrer**.
- **Permissions-Policy** containing **camera=(), microphone=(), geolocation=()**.
- No **Strict-Transport-Security** on HTTP localhost under default behavior.

Even with these headers, curl still prints the HTML. **curl does not enforce CSP or block iframe embedding**; only browsers enforce those rules.

### 14.2. Checking that static assets are protected by headers

~~~bash
curl -i http://localhost:8080/assets/app.js
curl -i http://localhost:8080/assets/site.css
~~~

Both are expected to return **200**. Because `/assets/**` uses **permitAll** instead of ignoring, Spring Security header writers still run. With this configuration, asset responses receive similar security headers, though each header's effect depends on the resource and context. Ensure the JS/CSS Content-Type is accurate so **nosniff** does not block browser loading.

### 14.3. CORS/authorization cannot be replaced by headers

~~~bash
# Unauthenticated:
curl -i http://localhost:8080/api/private

# With demo Basic credentials:
curl -i -u reader:demo123 \
  http://localhost:8080/api/private
~~~

Expectations:
- Without credentials: **HTTP 401**, the endpoint does not expose data.
- With valid credentials: **HTTP 200**, JSON containing username reader.

This checks **Authentication**, independent of CSP/XFO/nosniff. The fact that a 401 response carries security headers does not mean unauthenticated users are authorized to call the API.

### 14.4. HSTS must be tested in a real HTTPS environment

To test real HSTS, deploy over **HTTPS with a trusted certificate**, then run:

~~~bash
curl -I https://your-real-test-host.example/
~~~

The URL above is a **placeholder address that must be replaced with a real test host**, not an existing live site. Do not use **curl -k** to claim a TLS deployment is secure, since `-k` skips certificate verification. When using HEAD, note that servers/gateways may handle it differently from GET; use **curl -i** for GET if you need to be certain.

HSTS is only remembered by browsers after receiving a valid HTTPS response, or via the preload list. If behind a proxy, confirm that the public HTTPS request's original scheme is recognized by the backend/gateway and that the policy is present in the final response.

### 14.5. CSP Report-Only is not the same as enforced CSP

For phased rollout, you can configure report-only mode:

~~~java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; script-src 'self'; object-src 'none'")
        .reportOnly()))
~~~

This is a **configuration fragment** replacing the corresponding enforced CSP block, not a standalone program. With reportOnly, the response uses **Content-Security-Policy-Report-Only**; unless another enforced CSP is present, the browser will not block sources that only violate this report-only policy.

Once all legitimate violations are resolved, switch to an enforced policy and verify again. Do not treat a dashboard with few violation reports as proof that no XSS exists.

## 15. Automated testing with Spring Security Test + MockMvc

Write tests for **header presence**, **correct header configuration**, **HTTP vs HTTPS behavior**, and **still-working authorization**.

Add dependencies in **build.gradle** if not already present:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a Gradle Groovy DSL fragment; Spring Initializr usually already includes `starter-test`, so avoid duplicate declarations.

Create **src/test/java/com/example/demo/SecurityHeadersDemoApplicationTest.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPageKeepsDefaultsAndAddsSelectedHeaders()
            throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "X-XSS-Protection", "0"))
            .andExpect(header().string(
                "Cache-Control", containsString("no-store")))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("script-src 'self'")))
            .andExpect(header().string(
                "Referrer-Policy", "no-referrer"))
            .andExpect(header().string(
                "Permissions-Policy",
                containsString("geolocation=()")));
    }

    @Test
    void httpRequestDoesNotReceiveHstsByDefault()
            throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"));
    }

    @Test
    void simulatedHttpsRequestReceivesHsts()
            throws Exception {
        mvc.perform(get("/").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=31536000")));
    }

    @Test
    void anonymousIsStillDeniedPrivateApi()
            throws Exception {
        mvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "X-Frame-Options", "DENY"));
    }

    @Test
    void validHttpBasicAuthenticatesPrivateApi()
            throws Exception {
        mvc.perform(get("/api/private")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

**Why does the HSTS test use .secure(true)?** MockMvc does not establish a real TLS connection; **secure(true)** simulates a request considered secure by the Servlet container, allowing you to test the header writer. This test **does not replace** verifying HTTPS infrastructure, certificates, and forwarded headers behind a load balancer.

**Why is testing headers alone insufficient?** MockMvc can assert that the CSP string is accurate, but it does not run a browser to test blocking inline scripts, iframe clickjacking, or permission prompts. Add browser DevTools/Playwright/Selenium tests when the product depends on those behaviors.

### 15.1. Expected results table for the demo

| Test | Expected result | Meaning |
| --- | --- | --- |
| GET / over HTTP | 200 + CSP, nosniff, DENY | Header config is applied |
| GET / over HTTP | No HSTS | Matches HTTPS-only rule |
| GET / with MockMvc secure(true) | HSTS with max-age | Header writer reacts to secure request |
| GET /assets/app.js | 200 + proper script Content-Type | Asset traverses the chain and is not blocked by nosniff |
| GET /api/private without credentials | 401 | Headers do not replace Authentication |
| GET /api/private with valid Basic auth | 200 | Authentication policy works |
| Open page in browser | Same-origin JS/CSS run, inline script blocked if added in testing | CSP takes effect in the browser |
| Embed / in another site's iframe | Browser expected to block | XFO/CSP frame-ancestors mitigate clickjacking |

These statuses are **expectations from the example configuration**, not Gradle or browser logs collected in this document.

## 16. When do headers fail to appear or take effect?

### 16.1. The response does not go through the Spring Security filter chain

If a URL is excluded by **web.ignoring**, or served by a separate static host, gateway, or CDN, **the Spring Boot application's HeaderWriterFilter cannot directly modify that response**. You must verify policies at the component actually returning the response.

Although **permitAll** allows public URLs, the Spring Security filter chain still runs, giving it the opportunity to write headers. **Bypassing the security chain to optimize CSS** can inadvertently drop security headers too.

### 16.2. A different SecurityFilterChain is matched than expected

When multiple chains exist:
- One chain matches `/api/**`.
- One chain matches `/admin/**`.
- A default chain handles other resources.

Header configuration applies per **chain handling the request**, not as an immutable global list. If an endpoint lacks the right CSP or cache-control, check **securityMatcher**, chain ordering, and active filters. Do not configure headers in chain A and assume they will appear in chain B.

### 16.3. An error occurs at the proxy before reaching Spring

301, 302, 404, 429, 500, 502, or 503 responses can be generated by:
- Reverse proxy, load balancer, or API gateway.
- CDN/cache edge.
- Container/servlet error handling.
- Spring Boot app and Spring Security.

If a response is generated **before reaching Spring**, HeaderWriterFilter cannot add headers. Configure the edge/server appropriately, especially for HSTS on public HTTPS hosts and CSP on CDN-served HTML.

### 16.4. Headers are overwritten or duplicated

A site might configure CSP in Spring Security, nginx, and a CDN simultaneously. **Multiple CSP policies can be enforced concurrently by browsers**, making the page more restricted than expected. Conversely, a proxy might overwrite CSP with a looser value unbeknownst to the app team.

HSTS, cache-control, and other policies can also become inconsistent across layers. Designate a clear **owner** for each header and verify the actual response after all middleware.

### 16.5. Security headers still require framework vulnerability patching

Even when code uses the right configuration, older framework versions can have bugs causing headers not to be written in certain scenarios. For example, Spring Security 6.5 versions prior to patch **6.5.9** were affected by a 2026 advisory regarding HTTP headers not being written under some conditions. This highlights that **both proper configuration and version updates matter**.

For production apps, monitor **Spring Security Advisories**, Spring Boot's BOM, and run header regression tests on the deployed version. Never assume an old README or configuration from years ago guarantees current runtime behavior.

## 17. Security headers and other security mechanisms

| Mechanism | What does it solve? | What is it not? |
| --- | --- | --- |
| **Security response headers** | Mitigate certain risks in how browsers handle responses | Authentication/Authorization |
| **HTTPS/TLS** | Protect transport and authenticate the server via PKI | CSP or clickjacking prevention |
| **HSTS** | Help browsers prefer HTTPS for a host on future visits | TLS certificates or vulnerability patching |
| **CSP** | Restrict script/resource sources and execution | Output encoding or API authorization |
| **CORS** | Allow cross-origin scripts to read responses per policy | Checking who is authorized to access data |
| **CSRF protection** | Defend against forged state-changing requests with auto-sent credentials | X-Frame-Options or CORS |
| **SameSite / HttpOnly / Secure cookies** | Constrain sending/reading cookies in the browser | Replacement for CSRF or user login |
| **AuthorizationManager / method security** | Decide which principal can invoke which endpoint/operation | CSP, HSTS, or cache-control |
| **Input validation / output encoding** | Reduce injection and safely handle untrusted data | Provided automatically just by setting Content-Security-Policy |
| **Dependency updates** | Patch framework/library vulnerabilities | Headers automatically detecting and patching CVEs |

### 17.1. CORS headers are not the same as CSP connect-src

CORS answers: does the **target server** allow scripts at origin A to read its response?  
CSP **connect-src** answers: does the **source document** allow its scripts to connect to URL B?

A cross-origin fetch can be blocked by CSP connect-src right at the document side; if connect-src allows it, the browser can still block reading the response if the target server rejects CORS. Neither replaces Authentication.

### 17.2. CSP frame-ancestors does not replace CSRF tokens

Blocking iframes helps mitigate one type of clickjacking, but cannot stop another website from sending simple form requests under all conditions. **State-changing POST requests using session cookies** still require CSRF protection per the threat model, even with `X-Frame-Options: DENY`.

### 17.3. Headers do not grant permissions

For example, an API returns:

~~~http
HTTP/1.1 403 Forbidden
Content-Security-Policy: default-src 'self'
X-Content-Type-Options: nosniff
~~~

HTTP 403 still means the request was denied by the corresponding mechanism. CSP does not "promote" a user to admin or let a client bypass `hasAuthority`. Security headers protect responses; authorization is an access decision made on the server.

## 18. Roadmap for hardening a real web application

### Step 1: Identify content types and origins

List:
- Server-rendered HTML, SPA `index.html`.
- JSON APIs and HTML error pages.
- CSS/JS/images/font assets, file uploads/downloads.
- CDNs, reverse proxies, gateways, and static hosts.
- Login/logout/admin endpoints, checkout UIs, and pages with private data.

Do not assume every response comes from a single SecurityFilterChain.

### Step 2: Verify default headers are actually present

At the **staging public endpoint**:
- GET HTML pages.
- GET protected endpoints after logging in.
- Unauthenticated GET leading to 401/302.
- GET static resources and error pages.
- Verify HSTS on HTTPS responses.
- Do not expect HSTS as mandatory over plain HTTP.

Use **curl -i** and browser DevTools Network. For missing headers, investigate the security chain, static hosting, and gateway before changing code.

### Step 3: Design CSP from the asset graph

Collect all valid script/style/connect/frame endpoints. Start with a report-only policy on staging if needed, inspect violation reports, and narrow down gradually. Do not add **'unsafe-inline'** or broad wildcards just to silence errors.

If inline scripts are mandatory, use **properly managed nonces/hashes**, never a fixed hard-coded nonce. Avoid leaking secrets into CSP logs/reports.

### Step 4: Finalize Referrer-Policy and Permissions-Policy

Select Referrer-Policy based on privacy and analytics requirements; sensitive dashboards may prefer **no-referrer**. Block browser features the application does not use. Verify browser support and embedding use cases.

### Step 5: Verify HTTPS and HSTS behind the proxy

Verify the public host, TLS certificate, HTTPS redirects, trusted forwarded headers, `includeSubDomains`/`preload`, and domain scope. Roll out HSTS carefully; never enable preload before auditing every subdomain.

### Step 6: Test real browsers and HTTP-level assertions

At a minimum:
- CSP blocks test inline scripts without breaking legitimate scripts.
- Iframe embedding is blocked per policy.
- Content-Type is accurate and nosniff does not break assets.
- Referrer and browser features obey policy.
- HSTS is present on public HTTPS.
- 401/403/500 responses do not accidentally omit required security headers.
- Authentication, Authorization, and CSRF are still verified properly.

### Step 7: Monitor versions and regressions

Keep Spring Security/Spring Boot dependencies patched. Every gateway/CDN change or multi-SecurityFilterChain migration requires retesting response headers, especially CSP/Cache-Control/HSTS. Scanner reports are only signals; verify via actual browser behavior.

## 19. Common issues and troubleshooting table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| HTTP localhost lacks Strict-Transport-Security | HSTS is only added for secure requests | Test over real HTTPS or MockMvc `secure(true)` |
| Public HTTPS has HSTS but backend lacks it | Gateway/CDN is emitting HSTS | Confirm header owner and final response |
| Public HTTPS is missing HSTS | Proxy not forwarding/trusted for original scheme or header stripped | Check forwarded headers, edge config, and header writer |
| Browser rejects CSS/JS after enabling nosniff | Incorrect Content-Type | Fix the MIME type instead of disabling nosniff |
| CSP breaks button clicks | Code uses `onclick`/inline script | Move to external JS and `addEventListener`; use nonce/hash if needed |
| CDN assets blocked by CSP | CDN origin missing from the appropriate allowlist | Review asset graph and add minimal trusted sources |
| CSP Report-Only logs violations but JS still runs | Report-only does not enforce | Switch to enforced mode after QA |
| CSP is on JSON API but SPA still runs external scripts | API CSP does not govern a frontend document on another host | Place CSP on the actual HTML entrypoint |
| Set `frame-src 'none'` yet site can still be embedded | `frame-src` controls child frames, not who can embed this page | Use `frame-ancestors` on the embedded page's response |
| XFO DENY blocks legitimate iframe widget | Embedding policy is too restrictive | Design a `frame-ancestors` allowlist and align XFO accordingly |
| Security headers missing on static CSS | File served by CDN or bypassed by `web.ignoring` | Configure headers where served; prefer `permitAll` for app assets |
| Cache-Control blocks caching public images | Security-optimized defaults do not differentiate assets | Customize caching by URL, avoid disabling global headers |
| Data remains visible after logout | Open browser tab, client storage, or custom cache | Combine logout/session invalidation with cache and client-storage policies |
| Spring returns different headers from gateway | Configured across multiple layers or overwritten | Assign header ownership, standardize, and test public responses |
| Permissions-Policy breaks camera access | Feature blocked intentionally | Allow camera only where needed and verify browser support |
| COOP breaks login popups | Cross-origin isolation conflicts with popup flows | Evaluate policy against architecture, do not blindly copy snippets |
| JWT API still accessed without authorization despite CSP | CSP is not authorization | Fix Authentication/Authorization, ownership, and scopes |
| Using `X-XSS-Protection: 1` for XSS protection | Legacy unreliable mechanism | Use output encoding + proper CSP |
| Third-party script in CSP allowlist is still dangerous | Partner compromised or script has same-origin privileges | Minimize trust, monitor supply chain, use SRI where applicable |
| Headers appear on 200 but disappear on 500 | Error generated at gateway/container or different chain | Inspect error pipeline and proxy/edge headers |
| Scanner flags missing CSP on JSON API | CSP mainly applies to loaded documents | Evaluate endpoint/content type and threat model rather than fixing mechanically |

## 20. Self-assessment questions

1. Are security headers **request headers** or **response headers**? Which party usually enforces the policies?
2. Which headers does Spring Security 6.x add by default? Does HSTS appear on plain HTTP?
3. Does **X-XSS-Protection: 0** enable a new XSS protection filter?
4. How does **nosniff** differ from **Content-Type**? Why might CSS with the wrong MIME type be blocked?
5. What risk does **X-Frame-Options: DENY** mitigate? How does it differ from CSP **frame-ancestors**?
6. If a page needs to be embedded by a portal in the same company on a different origin, which policies should be considered?
7. Why does **Cache-Control: no-cache** not mean "do not store", and why is **no-store** better suited for sensitive content?
8. What operational risks can **HSTS includeSubDomains** and **preload** introduce?
9. If the browser connects via HTTPS to a load balancer while the backend receives HTTP, what must be verified so HSTS is sent properly?
10. Why does Spring Security not apply a default CSP for every page?
11. How does the policy **script-src 'self'** treat inline `onclick` handlers vs external `/assets/app.js`?
12. How does **Content-Security-Policy-Report-Only** differ from an enforced CSP header?
13. Is **frame-src** used to stop others from embedding your page? Why or why not?
14. What information leak does **Referrer-Policy: no-referrer** reduce?
15. Does **Permissions-Policy** replace browser user permission prompts?
16. When do **COOP/COEP/CORP** require extra careful testing due to the risk of breaking integrations?
17. Why is **permitAll** generally preferable to **web.ignoring** for static resources needing security headers?
18. If the HTML entrypoint is served by a CDN while the API is served by Spring, where should CSP be checked?
19. Why do complete security headers still not replace CSRF, Authentication, Authorization, and per-resource permission checks?
20. With MockMvc, what does `secure(true)` prove and what does it fail to prove about production TLS?

**Remember:** Security headers help **browsers reduce the attack surface when handling responses**, but they do not turn an application lacking authorization or containing XSS into a secure one. **Spring Security 6.x provides a default set of headers** (cache-control, nosniff, XFO, HSTS over HTTPS, X-XSS-Protection: 0); **CSP/Referrer-Policy/Permissions-Policy** must be tailored to the application. Always inspect headers on actual responses behind proxies/CDNs, test in browsers, and keep authentication, authorization, CSRF, output encoding, and TLS working together.

## 21. Official references

- Spring Security 6.5 — Security HTTP Response Headers (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html
- Spring Security 6.5 — Security HTTP Response Headers (features, defaults, and scope): https://docs.spring.io/spring-security/reference/6.5/features/exploits/headers.html
- Spring Security 6.5 — HTTP/HTTPS and Proxy Configuration: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/http.html
- Spring Boot — Running Behind a Front-end Proxy: https://docs.spring.io/spring-boot/reference/how-to/webserver.html
- MDN — HTTP Headers Reference: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers
- MDN — Content Security Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP
- MDN — Strict-Transport-Security: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security
- MDN — X-Frame-Options: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options
- MDN — X-Content-Type-Options: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options
- MDN — Referrer-Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy
- MDN — Permissions-Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy
- OWASP — HTTP Security Response Headers Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- Spring Security Advisory, March 2026 — Under Some Conditions HTTP Headers Are Not Written (CVE-2026-22732): https://spring.io/security/cve-2026-22732/
