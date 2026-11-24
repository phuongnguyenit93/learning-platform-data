# Default Security Headers in Spring Security Servlet and Mitigated Risks

**Module:** Spring Security – Servlet  
**Parent topic:** HTTP Protection

## 1. What are security headers and why are they needed?

**HTTP security headers** are headers in an **HTTP response** sent by the server to the browser. They instruct the browser to handle content according to safer rules: not guessing the MIME type on its own, restricting other websites from embedding the page in an iframe, remembering to require HTTPS, controlling caching, restricting where JavaScript can load resources from, and so on.

In a **Spring Security Servlet** application, common headers are written via **HeaderWriterFilter** and **HeaderWriter** implementations in the security filter chain. When using standard HTTP security configuration, Spring Security provides a default set of headers; you do not need to write a controller manually to attach each header. However, the configuration can vary depending on the **version**, whether the request is **HTTPS**, which filter chains are applied, and whether the application has already set a header earlier.

Three layers need to be distinguished:

- **TLS/HTTPS** encrypts and authenticates the connection; **security headers** add defensive behavior in the browser.
- **Authentication/authorization** verify identity and permissions; security headers do not grant or check permissions.
- **Input validation, output encoding, CSRF protection, and session management** remain mandatory. Headers reduce the attack surface or the impact of other flaws, but they do not automatically fix all application vulnerabilities.

A typical request:

~~~text
Browser --GET /account--> Servlet container
                            |
                            v
                       SecurityFilterChain
                       HeaderWriterFilter + other filters
                            |
                            v
                         Controller
                            |
          HTTP response <----+
          X-Content-Type-Options: nosniff
          X-Frame-Options: DENY
          Cache-Control: no-cache, no-store, ...
          ... depending on request and configuration
~~~

You should not assess security merely by seeing headers present: you must understand **which risk is mitigated**, **where the header applies**, and **what it does not solve**.

## 2. Default headers in Spring Security 6 Servlet

The following table describes the common default configuration of **Spring Security 6.x when HTTP headers have not been customized or disabled**. Actual values must be verified against the running application and version.

| Header | Common default value | Mitigated risk / role |
| --- | --- | --- |
| **X-Content-Type-Options** | `nosniff` | Prevents the browser from guessing a content type different from the Content-Type declared by the server; reduces the risk of mistakenly executing resources as script/style. |
| **X-Frame-Options** | `DENY` | Disallows embedding the page in a frame/iframe; reduces the risk of **clickjacking**. |
| **Cache-Control** | `no-cache, no-store, max-age=0, must-revalidate` | Restricts caching of sensitive content in protected responses. |
| **Pragma** | `no-cache` | Historical compatibility with legacy HTTP caching mechanisms. |
| **Expires** | `0` | Marks content as already expired for relevant caching mechanisms. |
| **Strict-Transport-Security** | `max-age=31536000 ; includeSubDomains` | **HSTS** instructs the browser to continue using HTTPS for a specified duration; helps prevent downgrading to HTTP on subsequent visits. **Only sent by Spring Security when the request is recognized as secure (HTTPS)**. |
| **X-XSS-Protection** | `0` | **Disables** the legacy XSS filter in some browsers because it is outdated and can introduce unsafe behavior. This is **not** a modern XSS defense header. |

Important notes:

1. The order of headers in a response is not significant; HTTP header names are case-insensitive. Whitespace in the HSTS value may vary slightly by implementation and does not affect meaning.
2. Spring Security usually **does not automatically overwrite cache headers that the application has explicitly set**. For example, static assets may have their own caching policy.
3. HSTS not appearing in an HTTP response is usually **expected behavior**, not an indication that the security filter is misconfigured.
4. If an endpoint does not pass through **SecurityFilterChain** (for example, excluded via `web.ignoring()`), security headers written by Spring Security may be absent.
5. Do not assume Content-Security-Policy, Referrer-Policy, or Permissions-Policy from this table by default; these are policies that need evaluation and usually explicit configuration.

## 3. Analysis of each mechanism and risk

### 3.1. `X-Content-Type-Options: nosniff` — preventing MIME sniffing

The server needs to send the proper Content-Type, for example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Content-Type-Options: nosniff

{"status":"ok"}
~~~

Historically, some browsers tried to guess the MIME type of content if it was misdeclared. This is dangerous if uploaded data or user content could be interpreted by the browser as JavaScript or CSS. `nosniff` restricts the browser from processing resources in script/style contexts when the MIME type does not match, and is also applied by some browsers in other scenarios.

**Risk example:** an upload endpoint returns user-controlled data with an ambiguous MIME type; another page embeds that URL as an executable resource. Blocking sniffing is a mitigation layer.

**Limitations:** `nosniff` does not itself prevent XSS caused by the application intentionally inserting malicious HTML into a page. The server must still assign the correct `Content-Type`, contextually encode output, validate uploads, and use `Content-Disposition: attachment` when files should be downloaded rather than displayed.

**Common pitfall:** enabling `nosniff` causes scripts or stylesheets to fail to load because the backend returns `text/plain` or `text/html` for JavaScript/CSS files. The fix is to **fix the MIME type and resource path**, not to disable the header to hide the bug.

### 3.2. `X-Frame-Options: DENY` — mitigating clickjacking

**Clickjacking** occurs when an attacker's website places the real application inside an iframe and overlays a fake UI on top, tricking users into clicking sensitive buttons on the real page.

~~~text
Attacker site
+---------------------------------------+
| "Click to claim prize"                |
|    [fake button over real button]     |
|       iframe containing bank page     |
+---------------------------------------+
~~~

With `X-Frame-Options: DENY`, supporting browsers refuse to display the page in a frame, even from the same origin. If the application genuinely needs to be embedded **within the same origin**, `SAMEORIGIN` can be considered. If you want to allow embedding from selected origins, the modern and more flexible policy is **CSP `frame-ancestors`**.

Distinctions:

- `X-Frame-Options` and `Content-Security-Policy: frame-ancestors ...` control **who is allowed to embed the current page**.
- `Content-Security-Policy: frame-src ...` controls **which sources the current page is allowed to embed**.
- **CORS** controls whether JavaScript on another origin can **read the response**; CORS does not replace anti-clickjacking defenses.

In modern browsers that support CSP `frame-ancestors`, that policy can take precedence over X-Frame-Options. Do not use `ALLOW-FROM`: that value is not consistently supported across modern browsers.

### 3.3. `Cache-Control`, `Pragma`, `Expires` — restricting storage of sensitive content

Default response example:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

Distinct meanings of the directives:

- **`no-store`**: instructs caches not to store the response/request under caching rules; this is the critical directive when a page or API contains sensitive data.
- **`no-cache`**: does not mean "never store"; it requires caches to **revalidate** with the server before using stored content.
- **`max-age=0`**: sets the duration during which content is considered fresh to 0.
- **`must-revalidate`**: prevents reusing stale cached entries when revalidation cannot be performed under HTTP rules.
- **`Pragma: no-cache`**, **`Expires: 0`**: supplemental compatibility with legacy HTTP mechanisms.

**Risk:** a page containing a profile, transactions, or personal information remains in the browser cache or a shared proxy after the user logs out.

**Limitations:** these headers **do not erase data that has already leaked**, do not prevent users from taking screenshots, and do not replace frontend or server storage policies. For highly sensitive data, you must also evaluate browser back-forward cache, service workers, IndexedDB/localStorage storage, and gateway caches.

**Performance:** do not blindly apply `no-store` to all immutable resources. CSS/JS files with content hashes in their names can be cached long-term using an appropriate policy set by the application/CDN, while HTML/APIs containing private data should restrict caching. Do not strip all security headers just to fix caching.

### 3.4. HSTS — `Strict-Transport-Security`

Example returned by the server **over HTTPS**:

~~~http
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
~~~

Browsers supporting HSTS remember that this hostname must be accessed over HTTPS for **31,536,000 seconds (about one year)**. `includeSubDomains` extends the policy to matching subdomains. Subsequent visits over HTTP are automatically upgraded by the browser to HTTPS before sending the normal request.

HSTS helps reduce the risk of an attacker forcing users from HTTPS down to HTTP (**SSL stripping/downgrade**) after the browser has learned the policy.

**Three key points:**

1. HSTS **only takes effect when received over a valid HTTPS connection**. A forged header over HTTP does not establish a trusted HSTS policy. Standard HSTS **does not protect the first visit** of a browser that has never seen the domain before; HSTS preload is a separate mechanism and requires thorough evaluation before registration.
2. `includeSubDomains` should only be used if **every subdomain in scope serves valid HTTPS**. If any subdomain still runs HTTP-only, it may become unreachable from browsers that have remembered the policy.
3. Behind a reverse proxy/TLS terminator, the backend may receive internal HTTP requests with `request.isSecure() == false`; in that case Spring Security does not emit HSTS automatically. You must configure proper forwarded scheme recognition while **only trusting `Forwarded`/`X-Forwarded-Proto` attached by trusted proxies**, never blindly trusting them from the Internet.

HSTS does not configure TLS certificates, TLS versions, HTTP → HTTPS redirects, or protect clients that do not support HSTS. You should enforce mandatory HTTPS, valid certificates, and controlled redirects at the appropriate layer.

### 3.5. `X-XSS-Protection: 0` — disabling the legacy XSS filter

The header name is easily misunderstood: the value **`0` means disabling** the legacy XSS auditor/filter in some browsers. Those filters are obsolete and historically caused unintended behavior; modern browsers largely do not use them.

Therefore, **do not mark the application as XSS-protected just because this header exists**. Practical XSS prevention requires:

- Contextually escaping/encoding output for HTML, attributes, JavaScript, and URLs.
- Avoiding inserting unsanitized HTML via `innerHTML`; controlling template data.
- Verified sanitization when rendering user-supplied HTML is genuinely required.
- An appropriate **Content Security Policy (CSP)** as a defense-in-depth layer.
- Protecting cookies/sessions, keeping frontend libraries updated, and mitigating DOM XSS vulnerabilities.

Do not re-enable `X-XSS-Protection: 1; mode=block` expecting it to be a modern XSS solution.

## 4. Valuable headers that are **not enabled by default**

### 4.1. Content-Security-Policy (CSP)

CSP restricts the sources of resources, scripts, styles, frames, and certain behaviors a page can use. **Spring Security does not automatically pick a CSP suitable for every application**, because each system has different CDNs, SPAs, inline scripts, analytics, and embedding requirements.

Example of a relatively strict policy for a simple application:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Explanation:

- `default-src 'self'`: default value for resource groups that fall back to `default-src`.
- `script-src 'self'`: allows JavaScript from the same origin; avoids scripts from unapproved external sources.
- `object-src 'none'`: restricts embedding legacy plugin/object content.
- `base-uri 'self'`: restricts changing the base URL used to resolve relative paths.
- `frame-ancestors 'none'`: disallows other origins, or even the origin itself, from embedding this page.

**CSP reduces XSS risk but does not replace output encoding.** Do not carelessly add `'unsafe-inline'` or wildcards to `script-src` just to "silence errors" because it weakens script controls. For applications that need inline scripts, design an appropriate nonce or hash strategy. The policy above may also need adjustments for `connect-src`, `img-src`, `style-src`, `font-src`, or APIs/CDNs depending on the frontend.

You can roll out cautiously with **`Content-Security-Policy-Report-Only`** to observe violations before switching to enforcement. `frame-ancestors` must be sent via an **HTTP response header**; it does not work when only placed in an HTML `<meta http-equiv="Content-Security-Policy">` tag.

### 4.2. Referrer-Policy

`Referrer-Policy` determines how much information from the originating page's URL is sent by the browser in the `Referer` header when navigating or loading resources. For example:

~~~http
Referrer-Policy: strict-origin-when-cross-origin
~~~

With this policy, the browser normally sends the full URL for same-origin requests, sends only the **origin** when transitioning to another origin over an appropriately secure connection, and sends no referrer when downgrading from HTTPS to HTTP. This reduces the risk of leaking paths/queries containing sensitive information to external websites.

**Limitations:** never put access tokens, passwords, or secrets into query strings in the first place; referrer policy is not a secret storage mechanism. Modern browsers may already use a similar default, but explicitly defining the policy keeps application behavior intentional.

### 4.3. Permissions-Policy

Restricts a page's or iframe's ability to access browser features, for example:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=()
~~~

This example denies camera, microphone, and geolocation for documents within policy scope. A custom allowlist can be designed if the application genuinely needs it. **Permissions-Policy does not grant or validate permissions on the server**, nor does it replace browser permission prompts.

### 4.4. Other optional policies based on needs

- **Cross-Origin-Opener-Policy (COOP)**: isolates browsing contexts to a certain degree; may affect OAuth login popups or payment flows.
- **Cross-Origin-Embedder-Policy (COEP)** and **Cross-Origin-Resource-Policy (CORP)**: control cross-origin embedding/resource loading, which may be needed when using cross-origin isolation. Misconfiguring them can easily break resources or iframes.
- **Clear-Site-Data**: can be used on appropriate responses, such as after logout, to ask the browser to clear certain types of data; requires understanding scope, browser support, and impact across multiple apps on the same origin.
- **CORS response headers** such as `Access-Control-Allow-Origin`: configure only when there is a legitimate cross-origin flow; never allow all origins together with credentials by default.

These policies **should not be attached as a "more is better" bundle**. Every header must correspond to a concrete threat model and compatibility requirement.

## 5. Runnable example: keeping defaults and adding CSP, Referrer-Policy, Permissions-Policy

The example uses **Java 17**, **Spring Boot 3.3.5 / Spring Security 6.x** with Spring MVC on the **Servlet stack**. The version here is used to reproduce the configuration; production projects must update to supported patched versions.

**Directory structure**

~~~text
header-demo/
├── pom.xml
└── src/
    ├── main/java/demo/HeaderDemoApplication.java
    └── test/java/demo/HeaderDemoApplicationTests.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>header-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/HeaderDemoApplication.java**

~~~java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HeaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HeaderDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            // Allow access to the demo endpoint to easily inspect response headers.
            // permitAll does NOT mean bypassing Spring Security filters.
            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
            .headers(headers -> headers
                // Default headers such as nosniff, DENY, cache, and HSTS
                // are still preserved when adding the headers below.
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; script-src 'self'; " +
                    "object-src 'none'; base-uri 'self'; " +
                    "frame-ancestors 'none'"
                ))
                .referrerPolicy(ref -> ref.policy(
                    ReferrerPolicyHeaderWriter.ReferrerPolicy
                        .STRICT_ORIGIN_WHEN_CROSS_ORIGIN
                ))
                .addHeaderWriter((request, response) ->
                    response.setHeader(
                        "Permissions-Policy",
                        "camera=(), microphone=(), geolocation=()"
                    )
                )
            );

        return http.build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/api/hello")
        Map<String, String> hello() {
            return Map.of("message", "ok");
        }
    }
}
~~~

**Why is this example properly scoped?**

- Declaring `SecurityFilterChain` ensures requests to `/api/hello` go through Spring Security. `permitAll()` allows anonymous reads to the endpoint while **still running HeaderWriterFilter**.
- The `.headers(...)` block **adds** CSP, Referrer-Policy, and Permissions-Policy without calling `defaultsDisabled()` or `.disable()`; default headers remain active.
- The CSP policy is an example suited to a JSON endpoint and pages that only load scripts from the same origin. When moving to a real SPA, you must inspect resources, inline scripts, fonts, CDNs, and APIs before applying it verbatim.
- HTTP GET does not require a CSRF token by default. **CSRF protection remains enabled** for state-changing methods; the example does not need to disable it.
- Permissions-Policy is added via a custom `HeaderWriter`; replacing it with the corresponding DSL is also fine if the version in use supports it and project requirements align.

**Running the application**

~~~bash
mvn spring-boot:run
~~~

Inspect the response (Linux/macOS uses `curl`; on PowerShell you can use `curl.exe`):

~~~bash
curl -i http://localhost:8080/api/hello
~~~

For example, the body is:

~~~json
{"message":"ok"}
~~~

Observe the actual response headers: on **HTTP localhost**, expect `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, the cache headers, `X-XSS-Protection: 0`, and the three newly added policies. **Do not expect HSTS** because the HTTP request is not secure. Do not assert header ordering or extra headers added by the container.

In a real HTTPS environment or when simulating a secure request in tests, additionally verify HSTS. Do not take results from `http://localhost` and conclude that HSTS is broken.

## 6. Automated header testing with MockMvc

**src/test/java/demo/HeaderDemoApplicationTests.java**

~~~java
package demo;

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
class HeaderDemoApplicationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void defaultAndAddedHeadersOnHttp() throws Exception {
        mockMvc.perform(get("/api/hello"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; " +
                "object-src 'none'; base-uri 'self'; " +
                "frame-ancestors 'none'"
            ))
            .andExpect(header().string(
                "Referrer-Policy", "strict-origin-when-cross-origin"
            ))
            .andExpect(header().string(
                "Permissions-Policy",
                "camera=(), microphone=(), geolocation=()"
            ))
            .andExpect(header().doesNotExist("Strict-Transport-Security"));
    }

    @Test
    void hstsOnlyWhenRequestIsSecure() throws Exception {
        mockMvc.perform(get("/api/hello").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().exists("Strict-Transport-Security"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expected:** both tests PASS: the HTTP test has no HSTS, and the secure test has HSTS. This is the expected outcome of the example, not a copied real execution log. If `SecurityFilterChain` is modified later, these tests help catch accidental loss of headers.

To verify thoroughly in deployment environments, also test **200, 302, 401, 403, and 404** responses, API endpoints and important static pages, HTTPS through load balancers/proxies, as well as chains using different `securityMatcher` rules. Headers can be added, removed, or overwritten downstream at gateways/CDNs; check responses **outside** the proxy as well.

## 7. When to modify defaults and how to modify them?

### 7.1. Intentionally allowing same-origin iframes

For example, an internal tool must embed its own pages inside an iframe. Change inside the `.headers(...)` block:

~~~java
.frameOptions(frame -> frame.sameOrigin())
~~~

**This is an illustrative configuration snippet placed inside the headers DSL, not a standalone Java class.** When also using CSP, `frame-ancestors 'none'` will still deny iframes; to allow same-origin embedding, synchronize it to `frame-ancestors 'self'`. Only do this after assessing clickjacking risks on pages containing sensitive actions.

### 7.2. Optimizing caching for public content

For static resources with hashed filenames, set an appropriate `Cache-Control` at the resource handler/CDN (for example, `public, max-age=31536000, immutable`). For HTML or APIs containing personal data, maintain a strict caching policy. **Do not use `headers.disable()` as a way to fix caching**, as it disables the other protections.

### 7.3. Services behind a reverse proxy

If HTTPS terminates at the gateway, verify `request.isSecure()` and the HSTS header on **the response received by the client**. Spring Boot supports a forwarded headers handling strategy, such as the following configuration after trusted infrastructure strips spoofed client forwarded headers:

~~~properties
server.forward-headers-strategy=framework
~~~

Depending on the container/cloud, proxy-native configuration may be more appropriate. This is an **environment configuration snippet**, to be used only after validating the proxy trust boundary. Blindly trusting forwarded headers can cause bugs in origin/scheme detection, redirects, or cookies.

### 7.4. Multiple `SecurityFilterChain` beans

An application can declare multiple chains with `@Order` and `securityMatcher`. Each request uses **the first matching chain**. If a separate chain disables headers or fails to match, some endpoints may lack headers even while other endpoints behave properly.

The right approach is to inspect the chains applied to each URL set, preferring **`permitAll()`** for public resources that still need filters, rather than completely excluding URLs from Spring Security with `web.ignoring()` without a clear reason.

## 8. Common misconceptions

| Misconception / symptom | Correct explanation and handling |
| --- | --- |
| "Having X-XSS-Protection means XSS is blocked." | A value of `0` **disables** the legacy filter. Use proper escaping/sanitization and CSP. |
| "HSTS must appear on HTTP localhost." | Spring Security only writes HSTS when the request is considered secure. Test over HTTPS or MockMvc `.secure(true)`. |
| "HSTS makes HTTPS work even if the server has not configured TLS." | HSTS only tells the browser to use HTTPS; the server must still have valid TLS/certificates. |
| "X-Frame-Options DENY blocks all other sites from calling APIs." | It blocks **framing**, and does not replace CORS, CSRF, or authorization. |
| "`no-cache` means do not store." | `no-cache` requires revalidation; `no-store` is the directive that prevents storing in HTTP caches. |
| "Adding CSP with `unsafe-inline` is good enough." | It can weaken script controls. Design sources, nonces/hashes, and verify real violations. |
| "Adding a `<meta>` CSP is enough for `frame-ancestors`." | `frame-ancestors` requires CSP in an HTTP response header. |
| "The controller returns headers, so every response has them." | Redirects, exceptions, static resources, gateways, or other chains may handle them differently. Inspect actual responses. |
| "`permitAll()` removes security headers." | `permitAll()` still runs the filter chain. `web.ignoring()` is what bypasses Spring Security for matching requests. |
| "Disable all HTTP headers to allow iframes or static caching." | Adjust only the specific frame policy/cache policy needed; keep the other security headers. |
| "Enable `includeSubDomains` everywhere." | Only safe when all subdomains in scope serve proper HTTPS. |
| "Having headers is enough to stop CSRF or SQL injection." | CSRF requires proper CSRF protection; SQL injection requires parameterized queries and least-privilege DB permissions. |

## 9. Process for evaluating HTTP protection in a real project

1. **Inventory endpoints and filter chains:** HTML/SPA, JSON APIs, downloads, static assets, error pages, and redirects; determine which chain handles each.
2. **Observe real responses:** use DevTools Network or `curl -i` over both HTTP and HTTPS, across key status codes, and through proxies/CDNs. Do not rely on HEAD as sole evidence if the system handles HEAD differently from GET.
3. **Map to risks:** MIME sniffing → nosniff; clickjacking → DENY/frame-ancestors; sensitive caching → no-store; HTTPS downgrade → HSTS; malicious script loading → CSP and encoding; referrer leakage → Referrer-Policy; browser feature APIs → Permissions-Policy.
4. **Verify compatibility:** business iframes, login popups, OAuth redirects, CDNs, analytics, inline scripts, images, fonts, service workers, and subdomains. CSP Report-Only can be used before enforcing the policy.
5. **Write regression tests:** assert critical headers per chain and HSTS present/absent behavior. Do not rely solely on security scanner scores.
6. **Monitor gateway changes:** nginx, ingress, and CDNs may rewrite headers, create duplicate headers, or drop a policy. Verify the response seen by the end user.

**Remember:** Spring Security Servlet provides a useful default HTTP protection layer against **MIME sniffing, clickjacking, sensitive data caching, and HTTPS downgrade**. The `X-XSS-Protection: 0` header only **disables** an obsolete mechanism. **CSP, Referrer-Policy, and Permissions-Policy** usually need to be added as required. HSTS is only sent for secure requests, and **no header replaces core server-side or frontend controls**.