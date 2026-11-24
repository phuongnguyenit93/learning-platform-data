# Limitations of Security Headers: Output Encoding and Input Validation Are Still Required

## 1. Objectives

In Spring Security **Servlet**, HTTP security headers help browsers apply defensive rules: restricting script sources, preventing framing, enforcing HTTPS, curbing MIME sniffing, or limiting referrer leakage. However, they **are not input filters** and **do not automatically encode strings output by controllers/templates**. An application with CSP, HSTS, and `nosniff` can still suffer from XSS, SQL injection, path traversal, open redirects, or broken authorization.

This lesson distinguishes three responsibilities:

1. **Security headers:** policies at the response/browser layer; valuable as *defense in depth*.
2. **Output encoding/sanitization:** ensuring untrusted data is interpreted as **data**, not code, when rendered into HTML, DOM, JavaScript, CSS, or URLs.
3. **Input validation and safe APIs:** ensuring data conforms to types, sizes, business rules, and access rights; using parameterized SQL, URL allowlists, and safe sink APIs.

Scope: **Spring Boot 3 / Spring Security 6 / Java 17+**, Servlet applications. Spring snippets belong inside a project with dependencies; section 5 includes a pure Java program runnable via `javac`/`java` to demonstrate escaping.

## 2. What do headers help with and what are their limits?

Example response:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Strict-Transport-Security: max-age=31536000; includeSubDomains
Cache-Control: no-store
```

These are distinct policies, not a "universal shield for all data". HSTS is only meaningful with HTTPS and browsers that have learned the policy under applicable conditions. CSP can block many script execution paths, but effectiveness depends on directives and frontend code. `Cache-Control: no-store` does not delete files saved locally by users, logs, or state held in an SPA.

| Header / mechanism | Purpose | Does not replace |
| --- | --- | --- |
| `Content-Security-Policy` | Restricts resources/scripts/frames; mitigates XSS impact | Does not replace escaping, safe DOM APIs, validation |
| `X-Content-Type-Options: nosniff` | Restricts MIME sniffing for certain resource requests | Does not validate file uploads, HTML output, or SQL |
| `X-Frame-Options` and CSP `frame-ancestors` | Reduces clickjacking via framing | Does not replace CSRF tokens or transaction confirmation |
| `Strict-Transport-Security` | Guides browsers to access the host over HTTPS | Does not filter input, check permissions, or escape output |
| `Referrer-Policy` | Limits URL data sent in referrer | Does not make putting secrets in URLs safe |
| `Cache-Control` | Controls response storage in HTTP caches | Does not replace authentication or wipe logs/downloads |
| `Permissions-Policy` | Restricts certain browser capabilities | Does not stop SQLi or SSRF |
| CORS response headers | Controls whether scripts on other origins can read responses via CORS | Not authentication/authorization or a general CSRF solution |
| `Secure`/`HttpOnly`/`SameSite` cookie attributes | Reduces unwanted cookie access or transmission | Does not replace input validation or stop all CSRF/XSS |

**The right questions:** What will the browser be allowed to do with the response? Was the data inside the response constructed safely? Is the caller authorized to receive that data? These are **three independent verification groups**.

### 2.1. A multi-layered defense flow

```text
Request/query/JSON/headers/DB/upstream (untrusted data)
    |
    +-- Enforce size, type, schema, and business semantics
    +-- Authentication, authorization, and owner/tenant checks
    +-- Use safe APIs: SQL parameters, path validation, URL allowlists
    |
    v
Controller / service / view model
    |
    +-- Context-aware rendering: HTML text/attribute, URL, JavaScript...
    +-- If rich HTML: allowlist-based sanitizer
    |
    v
HTTP response + security headers
    |
    v
Browser
```

One layer cannot "fully compensate" when another layer is skipped. For instance, broken authorization leaks Bob's invoice despite a flawless CSP; SQL string concatenation can be exploited on the server before the browser ever reads a response.

## 3. Why can XSS still occur even with CSP enabled?

**Cross-Site Scripting (XSS)** occurs when untrusted data enters a context where the browser interprets it as markup or code. Variants include reflected XSS (payload reflected from a request), stored XSS (payload persisted and served to others), and DOM-based XSS (frontend passes data into a dangerous sink).

Spring MVC anti-pattern:

```java
// DO NOT use: unencoded data concatenated into HTML.
@GetMapping(value = "/welcome", produces = "text/html")
@ResponseBody
String welcome(@RequestParam String name) {
    return "<h1>Welcome " + name + "</h1>";
}
```

If `name` contains HTML syntax, the browser parses the string as markup. A sufficiently strict CSP may block some script payloads, yet **must never be used as an excuse to keep unsafe HTML string concatenation**. CSP may be loosened by SDKs, same-origin scripts may contain bugs, injection behaviors may not manifest as inline JavaScript, or browsers may differ.

**Stop XSS where output is built**: use template auto-escaping for text content, DOM text APIs on the frontend, an HTML sanitizer when rich text is genuinely required, and CSP as an auxiliary layer.

### 3.1. Output must be handled according to exact context

| Data position | Appropriate mechanism | Common mistake |
| --- | --- | --- |
| HTML text node | Template auto-escaping / HTML text encoder | Concatenating raw input into HTML responses |
| Quoted HTML attribute | HTML attribute encoding from safe template/API | Inserting input into unquoted attributes; event attributes |
| JavaScript string/data | Context-appropriate serializer/encoding, prefer separate JSON | HTML-escaping and concatenating into `<script>` |
| DOM text | `textContent`, `createTextNode` | `innerHTML`, `outerHTML` with raw user input |
| URL query component | URL builder and URI component encoding | Using HTML escaping instead of URL encoding |
| URL destination/redirect | Validate scheme, origin, host/path against allowlist | Only URL-encoding and trusting any destination |
| CSS/style | Fixed CSS structure, value allowlists | Letting users build arbitrary `style`/`url(...)` |
| Rich HTML | HTML parser sanitizer allowlisting tags, attributes, protocols | Using regex to strip `<script>` |
| SQL | Prepared statements / parameter binding | HTML-escaping or blocking quotes to "stop SQLi" |
| File path | ID mapping, normalized paths, and read-permission checks | Concatenating raw filenames onto a root directory |

There is no single "universal encode function" covering every row above. Moreover, some **contexts should be avoided altogether** when handling untrusted input: `onclick`, `onerror`, `<script>` containing concatenated code, `javascript:` URLs, `eval`, `document.write`, or user-constructed CSS.

### 3.2. Stored XSS and data from databases

Never label data as "trusted" merely because it came from the database. A user may have saved a string via another endpoint, imported a partner batch, or an admin may have entered HTML into a CMS. When another page later uses `th:utext`/`innerHTML` to render it, XSS can trigger **days later**. Encode at **the exact point of rendering to the sink**, whether the data originates from the DB or a request.

## 4. Thymeleaf and Spring MVC: rendering escaped text

With `spring-boot-starter-thymeleaf`, the standard pattern is:

```html
<!-- src/main/resources/templates/profile.html -->
<section>
  <h1 th:text="${profile.displayName}">Display Name</h1>
  <p th:text="${profile.bio}">Bio</p>
</section>
```

`th:text` escapes text rather than rendering tags generated by data. If `profile.displayName` is `<strong>Alice</strong>`, the page displays those characters literally as text without creating a user-injected `strong` tag.

**Risky** pattern:

```html
<!-- Do not use with unsanitized data -->
<div th:utext="${profile.bio}"></div>
```

`th:utext` permits unescaped HTML, so it should only be used when the product **has an HTML data contract** and has sanitized it with an appropriate allowlist. `@Valid` or CSP does not automatically neutralize this content.

Controller example in a Spring Boot MVC project:

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class ProfilePageController {
    @GetMapping("/profile")
    String profile(Model model) {
        // Demo: real apps must load the profile for the
        // authenticated user and verify access permissions.
        model.addAttribute("profile",
            new ProfileView("Alice <Admin>", "My profile"));
        return "profile";
    }

    record ProfileView(String displayName, String bio) {}
}
```

The `profile.html` template itself performs escaping. If you use `@RestController` returning a raw HTML string directly, Thymeleaf **does not automatically run** to escape that string.

### 4.1. When rich text is genuinely needed

If the product permits `<p>`, `<strong>`, links, etc. in articles, **sanitize HTML** with a library built for that purpose instead of writing custom regexes.

Java example using jsoup (requires the `org.jsoup:jsoup` dependency):

```java
import org.jsoup.Jsoup;
import org.jsoup.safety.Safelist;

public final class RichTextPolicy {
    private RichTextPolicy() {}

    public static String sanitize(String rawHtml) {
        return Jsoup.clean(rawHtml, Safelist.basic());
    }
}
```

`Safelist.basic()` is only **illustrative**. Select tags, attributes, and URL protocols based on product requirements; keep the library updated and test edge-case HTML, including SVG, event attributes, malformed markup, and link schemes. If sanitized HTML is placed into **another context** such as JavaScript or a URL, it needs controls for that new context. If you only need plain text display, **prefer escaping over an HTML sanitizer**.

Never treat `replace("<script>", "")` or regex filters for `onerror` as an HTML sanitizer: browser parsers have far too many rules and alternate syntaxes.

## 5. Pure Java 17: directly runnable HTML text escaping

This program illustrates the principle: special characters from input become HTML entities when emitted into an **HTML text node**. It is **not a production encoding library** and must not be used to escape JavaScript, CSS, URLs, or differently structured HTML attributes.

File `HtmlTextEscapeDemo.java`:

```java
public final class HtmlTextEscapeDemo {
    private static String htmlText(String value) {
        StringBuilder out = new StringBuilder();
        for (char ch : value.toCharArray()) {
            switch (ch) {
                case '&' -> out.append("&amp;");
                case '<' -> out.append("&lt;");
                case '>' -> out.append("&gt;");
                case '"' -> out.append("&quot;");
                case '\'' -> out.append("&#39;");
                default -> out.append(ch);
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        String input = "<b>Alice & Bob</b> 'hello'";
        System.out.println("raw=" + input);
        System.out.println("htmlText=" + htmlText(input));
    }
}
```

Compile and run:

```bash
javac HtmlTextEscapeDemo.java
java HtmlTextEscapeDemo
```

Exact stdout:

```text
raw=<b>Alice & Bob</b> 'hello'
htmlText=&lt;b&gt;Alice &amp; Bob&lt;/b&gt; &#39;hello&#39;
```

In HTML text, `&lt;b&gt;` renders as the literal characters `<b>`, **without creating an HTML tag**. Yet if that same string is placed into a JavaScript template, CSS, redirect, or SQL, safety **is not guaranteed**.

In real Java web apps, prefer template auto-escaping or a dedicated library like **OWASP Java Encoder** with matching APIs, such as `Encode.forHtml(...)` for HTML text, `Encode.forHtmlAttribute(...)` for attributes, and `Encode.forJavaScript(...)` for certain JS contexts. These are **external library** APIs not built into the JDK; select the right function and read documentation for the target context. Even with an encoder, injecting arbitrary data into `onclick` or `eval` must not be treated as safe practice.

## 6. Frontend JavaScript: textContent instead of innerHTML

DOM XSS anti-pattern:

```javascript
const name = new URLSearchParams(location.search)
  .get("name") ?? "";

// DO NOT use: browser will parse data as HTML.
document.querySelector("#welcome").innerHTML = name;
```

Safe text rendering:

```javascript
const name = new URLSearchParams(location.search)
  .get("name") ?? "";

// Render as text without parsing markup.
document.querySelector("#welcome").textContent = name;
```

By the same principle, `document.createTextNode` or a framework's default escaped interpolation is the right choice for plain text. Do not enable a framework's unescaped HTML mechanism when unnecessary.

### 6.1. JSON data is not HTML-safe everywhere

An API returning JSON through Spring's serializer produces valid JSON responses, yet the frontend can still introduce XSS if it writes:

```javascript
// ANTI-PATTERN even when profile comes from a JSON endpoint:
document.querySelector("#profile-name").innerHTML =
  profile.displayName;
```

Replace with:

```javascript
document.querySelector("#profile-name").textContent =
  String(profile.displayName ?? "");
```

If embedding JSON directly inside `<script>` in HTML, you need escaping that **understands the HTML script context**; simply calling `JSON.stringify` and concatenating into a script element is not a universal solution. Prefer a dedicated `application/json` endpoint, `fetch`, and rendering text via DOM APIs.

### 6.2. Attribute href requires URL validation

`element.setAttribute("href", value)` or `link.href = value` does not verify URL safety. `javascript:` URLs, cross-origin phishing links, or unintended redirect targets are **semantic problems**, not solved by HTML escaping alone.

Example allowing only same-origin HTTPS links:

```javascript
function allowedLocalUrl(raw) {
  try {
    const u = new URL(raw, location.origin);
    return u.protocol === "https:" &&
           u.origin === location.origin;
  } catch {
    return false;
  }
}
```

This is only an illustrative policy for a site running on HTTPS, not a general-purpose URL sanitizer. If linking to other domains is allowed, allowlist schemes/origins and handle redirects and lookalike domains. Never use an ambiguous `endsWith("example.com")` check to validate hostnames.

## 7. Input validation: matching contract and semantics

**Input validation** rejects data unacceptable to the application, but does not replace escaping.

Validation categories:

- **Schema/types:** JSON body types, required fields, valid numbers/dates/enums.
- **Size/range:** name length, item counts, file upload limits, page size, request body size.
- **Business semantics:** positive amounts, valid order status transitions, start date before end date.
- **Relationships/authorization:** whether the caller is allowed to edit that specific order/profile/tenant.
- **Allowlists for structural control values:** sort key names, file type choices, redirect targets, template names.
- **Intentional canonicalization:** Unicode, domains/URLs, and filesystem paths must be normalized/checked at the proper layer; avoid inconsistent decoding across layers.

Do not globally ban every `<`, `>`, `'`, or `;`. A valid display name or article may contain those characters. When the contract permits them, **store the data faithfully and escape when rendering**.

### 7.1. Spring Boot DTO with Jakarta Validation

Java 17 record example `ProfileRequest.java`:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9_-]{3,32}")
    String handle
) {}
```

Illustrative endpoint:

```java
import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileApiController {
    @PostMapping("/api/profile")
    ResponseEntity<Map<String, String>> update(
            @Valid @RequestBody ProfileRequest request) {

        // Real apps must verify permission to edit the profile,
        // check handle uniqueness, persist, and audit.
        return ResponseEntity.ok(Map.of(
            "displayName", request.displayName(),
            "handle", request.handle()));
    }
}
```

Requires `spring-boot-starter-web` and `spring-boot-starter-validation` or equivalent dependencies. `@Valid` checks constraint annotations; it does not check whether the caller may edit another user, does not escape HTML, and does not stop SQL injection inside services. `displayName` can contain `<b>` since only length is bounded; **it remains safe if frontend/templates display it using proper text APIs**.

**Validation and authorization are separate layers:** ID `123` is valid by pattern yet the caller might lack permission to access resource 123. The backend must check ownership and tenant boundaries.

## 8. SQL injection: parameterized queries

HTTP headers cannot fix backend SQL code. Anti-pattern:

```java
// DO NOT use: user input concatenated into SQL structure.
String sql = "SELECT id FROM accounts WHERE handle = '" +
             handle + "'";
```

Use binding:

```java
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;

public final class AccountLookup {
    private final JdbcTemplate jdbc;

    public AccountLookup(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Long> findIds(String handle) {
        return jdbc.queryForList(
            "SELECT id FROM accounts WHERE handle = ?",
            Long.class,
            handle
        );
    }
}
```

This is a class inside a Spring application with `spring-jdbc`, a datasource, and a matching schema. `?` binds **values**, keeping data separate from SQL structure. Never apply HTML escaping to values to defend against SQL injection.

For column/table names or `ORDER BY`, placeholders generally cannot replace SQL identifiers: map user-supplied keys to allowed literals in code.

```java
static String sortableColumn(String key) {
    return switch (key) {
        case "created" -> "created_at";
        case "name" -> "display_name";
        default -> throw new IllegalArgumentException("Unknown sort key");
    };
}
```

Never concatenate `sortColumn` directly from the request.

## 9. HTML sanitizers, path traversal, redirects, and uploads

### 9.1. Sanitization vs. encoding

- **Encoding:** keeps data as text rather than code in the output context.
- **Sanitization:** when business needs real HTML, permits a subset of tags/attributes/protocols after parsing and cleaning.
- **Validation:** rejects contract-invalid data, not an HTML transformation.
- **Authorization:** decides which user can act on which resource.

For example, when rendering user-authored Markdown: parse Markdown with an appropriate library, generate HTML, then **sanitize the output HTML** and render in a surface designed for rich text. Do not merely run a regex stripping `<script>`.

### 9.2. File uploads

`nosniff` alone is insufficient for safe uploads. Restrict size and file types, scan/parse as needed, inspect bytes/content rather than trusting client-supplied extensions/MIME types, use server-generated filenames, store outside executable directories, authorize downloads, and serve with proper `Content-Type`/`Content-Disposition`. User files hosted on the same origin and served as active HTML create risk even with CSP enabled.

### 9.3. Path traversal

Do not turn `?file=../../secret` into a path by string concatenation. Use server-managed resource IDs, canonicalize paths, and verify they remain inside the allowed directory/tenant; account for symbolic links, encoded separators, and proxy/container path normalization. CSP/HSTS do not protect the filesystem.

### 9.4. Open redirects

Input `next=https://attacker.example.test` must not go straight into an HTTP `Location` header. Allow only validated relative redirects or exact allowlists of scheme/host/path. HTML escaping the `next` parameter does not ensure a safe redirect target.

### 9.5. SSRF and shell injection

- SSRF: a service fetches a client-provided URL; restrict destinations, DNS/IPs, redirects, and egress networking.
- Shell injection: prefer programmatic APIs over shells; if invoking processes is unavoidable, pass controlled argument arrays rather than building shell commands from raw user input.

Those are **backend sinks**; response security headers do not protect them.

## 10. Configuring HTTP headers in Spring Security Servlet

Spring Security provides helpful default headers such as `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, cache-control for dynamic responses, and HSTS for HTTPS where applicable. **CSP is not generated automatically by Spring Security from the dependency alone.** The final header set depends on version, filter chains, and application/edge configuration.

File `WebSecurityConfig.java` in Spring Boot 3 / Spring Security 6:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "object-src 'none'; " +
                        "base-uri 'self'; " +
                        "frame-ancestors 'none'"))
                .referrerPolicy(ref -> ref
                    .policy(ReferrerPolicyHeaderWriter.ReferrerPolicy
                        .STRICT_ORIGIN_WHEN_CROSS_ORIGIN))
                .frameOptions(frame -> frame.deny()));
        return http.build();
    }
}
```

This configuration works **inside a complete Spring Boot project**, not as a standalone Java file compiled with `javac` without dependencies. Key points:

1. `permitAll()` still traverses the security filter chain and receives headers; `web.ignoring()` can bypass Spring Security filters and headers.
2. This CSP is an example baseline: script sources restricted to same origin, `object-src 'none'` forbids plugin objects, `base-uri 'self'` restricts base URLs, `frame-ancestors 'none'` forbids framing. Products with other resources must design policies accordingly.
3. Do not copy an overly rigid CSP that breaks the app and then broadly turn on `'unsafe-inline'`/`'unsafe-eval'`. Fix the violating code/templates and relax selectively under control.
4. `X-Frame-Options` and `frame-ancestors` can complement each other across different browsers.
5. HSTS is written by Spring Security when the request is considered HTTPS; do not expect it on plain HTTP requests.
6. **Nothing in the bean above escapes data in HTML/JavaScript or validates request DTOs.**

### 10.1. CSP helps but does not replace output encoding

A good CSP can block many injected inline scripts. However:
- Allowed same-origin scripts can still contain DOM XSS.
- CSP loosened with `unsafe-inline`/`unsafe-eval` loses effectiveness.
- Nonces/hashes are useful when implemented properly: nonces must be random, scoped per response, never hardcoded.
- Advanced policies like `strict-dynamic` or Trusted Types require checking browser support, script architecture, and UI libraries.
- CSP report-only measures violations during rollout but **does not block**; zero violation reports does not certify the app is free of XSS.

Prioritize fixing input-to-output flows and frontend sinks even while CSP is active.

### 10.2. HSTS and proxy environments

If TLS terminates at a reverse proxy, Spring Security's detection of secure requests and emission of HSTS depends on forwarded headers and trusted proxy configuration. Never let clients control `X-Forwarded-Proto`/`Forwarded` and have the backend trust them unconditionally. HSTS protects browser transport, and does not replace proper TLS at the edge.

### 10.3. CORS and CSRF

CORS is not authorization; the server must still protect every resource. If browsers automatically attach credentials via cookies/sessions/HTTP Basic, evaluate CSRF even when CSP or HSTS is present. For APIs accepting only bearer tokens explicitly sent in headers by clients, the CSRF threat model differs; decide based on **how credentials are accepted**, not whether the API returns JSON.

## 11. Testing the defensive layers

### 11.1. MockMvc testing response headers

A demo endpoint:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }
}
```

Test `SecurityHeadersTest.java` inside a Spring Boot project with `spring-boot-starter-test` and security filters:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicPageHasSecurityHeaders() throws Exception {
        mvc.perform(get("/public/ping").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("object-src 'none'")))
            .andExpect(header().string(
                HttpHeaders.STRICT_TRANSPORT_SECURITY,
                containsString("max-age=")));
    }
}
```

`secure(true)` simulates an HTTPS request to verify HSTS. This test **only proves headers are present** in the test environment; it does not prove the application is free of XSS/SQLi/IDOR.

Commands:

```bash
mvn -Dtest=SecurityHeadersTest test
# For the corresponding Gradle project:
./gradlew test --tests SecurityHeadersTest
```

### 11.2. Testing XSS on real output

Use values like `<b>Alice</b>`, strings with quotes/ampersands, Unicode, and unexpected markup. Render the page using the real template, then verify the string appears as text without creating user-controlled HTML nodes. On the frontend, component tests should confirm `textContent`/escaped interpolation is used rather than `innerHTML`.

If the product supports rich HTML, test sanitization for both allowed and rejected tags/attributes/protocols. Never treat "CSP is present" as a substitute for escaping tests.

### 11.3. Testing validation, SQL, and permissions

- Empty/overlong `displayName` and regex-failing `handle` must be rejected per DTO rules.
- `handle` containing quotes must not alter SQL structure when using parameter binding.
- Authenticated callers attempting to edit another user's `userId` must be rejected by authorization/ownership checks.
- Redirect URLs outside allowlists and file paths escaping the root must be rejected.
- Invalid upload sizes/types must be handled properly.
- Pages/endpoints with personal data should carry `no-store` per policy, while still requiring access control.

### 11.4. Verification matrix

| Scenario | Defensive layer to verify |
| --- | --- |
| Browser receives wrong or missing CSP | Header integration test |
| User input rendered into HTML text | Template escaping |
| User input rendered into HTML attribute | Attribute encoding and proper URL validation |
| URL query assigned to `innerHTML` | DOM sink review/test; use `textContent` |
| Rich HTML containing event handlers | Sanitizer allowlist |
| JavaScript data embedded in script element | Context-aware serialization/escaping or JSON endpoint |
| SQL containing control chars/quotes | Prepared statements and business validation |
| Dynamic sort column | Server allowlist mapping |
| Profile ID belonging to another tenant | Authorization/ownership tests |
| Uploaded file with forged MIME | File validation, isolation, proper headers |
| Redirect to attacker domain | Redirect allowlist |
| Cookie-authenticated unsafe POST | CSRF protection |
| Public assets and private APIs | Sensitivity-based cache policy |
| Responses through CDN/reverse proxy | Final headers and cache behavior on live path |

## 12. Common implementation mistakes

1. **"CSP is enabled so escaping is unnecessary."** False: CSP is a mitigation layer and does not make raw HTML concatenation safe.
2. **"`@Valid` prevents XSS."** False: business-valid data must still be encoded when rendered.
3. **"Removing `<script>` with regex is a sanitizer."** False: HTML parsing and DOM sinks are far too complex.
4. **"Escape once on input then store in DB."** Causes double-encoding and fails across differing output contexts. Encode on output per context.
5. **"HTML escaping is enough for JavaScript/URL/SQL."** False: each sink has distinct semantics.
6. **"JSON serializer automatically prevents DOM XSS."** False if the frontend passes JSON values into `innerHTML`.
7. **"`nosniff` replaces file upload validation."** False: you still need content checks, safe filenames, isolation, and authorization.
8. **"CORS replaces authentication/CSRF."** False: CORS is not backend access control.
9. **"HSTS stops SQL injection."** False: HSTS is a browser transport policy.
10. **"`'self'` means every same-origin script is safe."** False: same-origin scripts can still contain vulnerabilities.
11. **"With all headers present, endpoints cannot leak others' data."** False: authorization bugs still leak data.
12. **"Zero CSP reports means zero XSS."** False: violation reporting does not replace code review and testing.
13. **"Disable the security filter chain for static assets to enable caching."** Can lose headers; tune cache policies narrowly instead of bypassing the whole chain.
14. **"Testing 200 is enough."** You must test headers, rendering, rejected inputs, and per-resource permissions.

## 13. Final checklist

- [ ] Distinguish HTTP security headers from validation, authorization, and output encoding.
- [ ] Enable appropriate headers in Spring Security Servlet and inspect final responses through proxies/CDNs.
- [ ] Design CSP around actual resource sources; do not broadly enable `unsafe-inline` by default.
- [ ] HTML/Thymeleaf uses auto-escaping (`th:text`), never `th:utext` on raw input.
- [ ] Frontend uses `textContent` or escaped interpolation; avoid `innerHTML`/`eval`.
- [ ] Rich HTML is processed by an allowlist-based sanitizer, never regex.
- [ ] Use matching encoders for HTML text/attribute, JavaScript, and URLs; avoid inherently dangerous contexts.
- [ ] DTOs enforce schema/type/size/business validation; do not ban characters globally as a substitute for escaping.
- [ ] SQL uses parameter binding; sort keys/identifiers map from server-side allowlists.
- [ ] File paths/redirects/URLs/SSRF are validated at corresponding backend sinks.
- [ ] Backend verifies permissions and object ownership independently of headers.
- [ ] CORS, cookies, sessions, and CSRF are evaluated against how credentials are actually sent.
- [ ] Both header tests **and** output/input/authorization tests exist; do not treat header tests alone as sufficient.
- [ ] Never place secrets, raw bearer tokens, or personal data in URLs or logs.

**Conclusion:** Spring Security helps emit valuable HTTP security headers such as CSP, `nosniff`, HSTS, and frame policies, but **does not encode output for your application or validate business data for your services**. The right defense is **contract-based validation → resource-level authentication/authorization → safe APIs → context-aware output encoding → defense-in-depth security headers**, with testing at every layer.
