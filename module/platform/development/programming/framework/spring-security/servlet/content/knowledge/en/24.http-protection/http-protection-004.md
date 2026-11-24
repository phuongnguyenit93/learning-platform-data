# X-Content-Type-Options: nosniff and Protection Against Content-Type Sniffing

## 1. Why do browsers "guess" content types?

When a server returns an HTTP resource, the `Content-Type` header describes the response's **media type (MIME type)**. For example: `text/html` for HTML, `text/css` for CSS, `text/javascript` for JavaScript, `application/json` for JSON, and `image/png` for PNG images.

In certain contexts and browsers, if the header is missing or misdeclared, the browser may inspect the leading bytes of the content and perform **MIME sniffing**: guessing the format to decide how to handle it instead of relying solely on `Content-Type`. Guessing helped misconfigured websites still render, but it blurred the boundary between **data** and **executable code**.

For example: a server intends to deliver a user-uploaded file as plain text data, but the contents contain JavaScript or HTML syntax. If the browser interprets the resource in an active context (script, HTML), an attacker can leverage the misconfiguration to run code or expose data under certain conditions.

The following response header tells browsers to respect the declared content type for resource destinations with strict MIME rules:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8
X-Content-Type-Options: nosniff

console.log("This is text, not an executable script");
~~~

`X-Content-Type-Options: nosniff` prevents treating the `text/plain` content above as an **executable script** when a page embeds it via `<script src="...">`. This is a **response header**, not a header the client sends. The standardized and supported value is **`nosniff`**; do not replace it with `deny`, `sameorigin`, or custom values.

**Distinguish the two roles:** `Content-Type` says "what type I am sending"; `X-Content-Type-Options: nosniff` tells the browser not to switch to certain dangerous types by guessing. If the server declares the wrong `Content-Type`, `nosniff` **does not automatically fix the MIME type**. The system needs **both**: declaring the right `Content-Type` **and** sending `nosniff`.

## 2. Which cases does nosniff actually affect?

### 2.1. Scripts and stylesheets: the two core cases

When a response is loaded for a `script` destination, the browser applies MIME type checks. With `nosniff`, a response lacking a valid JavaScript MIME type will not be executed as JavaScript. For a `style` destination, a response that is not `text/css` will not be applied as a stylesheet.

| Requesting page | Server returns Content-Type | Has nosniff | Expected modern browser behavior |
| --- | --- | --- | --- |
| `<script src="/assets/app.js">` | `text/javascript` | Yes | May execute if content is valid and other policies permit |
| `<script src="/files/readme.txt">` | `text/plain` | Yes | **Execution blocked** because MIME type is not JavaScript |
| `<script src="/api/data">` | `application/json` | Yes | **Blocked from execution** as script |
| `<link rel="stylesheet" href="/assets/app.css">` | `text/css` | Yes | May apply stylesheet |
| `<link rel="stylesheet" href="/files/data.txt">` | `text/plain` | Yes | **Stylesheet blocked** because MIME type is not CSS |
| `<script src="/uploads/evil.js">` | `text/javascript` | Yes | **Not blocked by nosniff merely for malicious code**: declared MIME is valid |

"May" in the table means the browser still enforces **CSP, CORS (when applicable), SRI, sandbox, and other policies**. `nosniff` is only a MIME check condition, not an execution grant.

Note: **module scripts** already enforce stricter MIME rules than classic scripts under modern browser standards; `nosniff` is not the only reason a module with a wrong MIME gets blocked. Supported JavaScript MIME types in browsers include `text/javascript`; applications should return the actual type of the resource.

HTML example trying to embed JSON data as a script:

~~~html
<script src="/api/profile"></script>
<link rel="stylesheet" href="/uploads/notes.txt">
~~~

If `/api/profile` returns `Content-Type: application/json` and `/uploads/notes.txt` returns `Content-Type: text/plain`, along with `X-Content-Type-Options: nosniff`, the browser will refuse to process those two responses as JavaScript/CSS. DevTools usually shows errors mentioning "MIME type" or "strict MIME type checking"; exact wording and network status may vary across browsers.

### 2.2. Contexts not unconditionally protected

**`nosniff` is not a global content-type validator or replacement.** You cannot infer from a response having this header that every image, video, document, navigation, or `fetch` request will be blocked if `Content-Type` is wrong.

- **Direct navigation to a URL**: if the server returns HTML with `Content-Type: text/html`, the browser can render/run the HTML; `nosniff` does not "disable HTML". For user-controlled uploads, allowing HTML to render on a trusted origin remains very dangerous.
- **JSON via fetch/XHR**: `nosniff` does not replace authentication, authorization, CORS, or verifying how the client parses content. Same-origin browser scripts can generally still read `application/json` responses if access is permitted.
- **Images and other resource types**: browsers have destination-specific rules; do not rely on `nosniff` as a PNG/JPEG magic-byte validator or to neutralize all active content.
- **Cross-origin responses**: `nosniff` can participate in browser cross-origin data protections (such as CORB in some browsers; modern implementations also feature Opaque Response Blocking). Scope and behavior vary by browser and response type. This is **not a guarantee against information leaks** and does not replace CORS, CORP, COEP, authentication, or access control.

Key takeaway: **receiving HTTP 200 on the network does not mean the browser will execute the script/style**. MIME-based blocking happens in the browser; `curl` does not execute JavaScript and cannot be used alone to conclude whether browsers will block it.

## 3. Attack scenarios and defensive scope

### Scenario A: User-uploaded file invoked as JavaScript

Suppose the system lets users upload `avatar.txt` containing JavaScript code, which is then accessible at `/uploads/avatar.txt`. Another page or feature embeds that URL in a script tag:

~~~html
<script src="/uploads/avatar.txt"></script>
~~~

If the server returns `Content-Type: text/plain` **and** `nosniff`, modern browsers refuse to execute it as a script. If the server omits the header, legacy MIME sniffing behaviors or specific configurations could enable misinterpretation. However, **if the server mistakenly returns `text/javascript`**, `nosniff` does not help because the MIME is declared as JavaScript.

Proper defense: determine trusted content types reliably, never let users dictate MIME solely via filename or upload header, use allowlists and content inspection, prevent the server from serving untrusted files with executable MIME types, and consider serving user files from a **separate origin**. For downloads that need not render inline, use `Content-Disposition: attachment`.

### Scenario B: Untrusted HTML/SVG served inline

An `evil.html` file or an SVG with active content returned with `Content-Type: text/html` or `image/svg+xml` can create XSS or script execution risks depending on usage context, origin, CSP, and browser. **`nosniff` does not neutralize active content served with a valid MIME type.**

Protect by disallowing inline rendering of dangerous file types on the application origin, switching to attachment downloads where appropriate, using a separate origin without auth cookies, applying CSP/sandboxing, and enforcing strict file allowlists. Never trust file extensions or client-supplied upload `Content-Type`.

### Scenario C: Data responses embedded cross-origin

Another website might try embedding resources via HTML elements. Browsers have specific protections to reduce leaks of HTML/XML/JSON responses through inappropriate resource tags. `nosniff` helps some of these mechanisms make decisions based on the declared type, but it **does not** protect public content from direct reading, does not fix overly permissive CORS configurations, and does not replace checking whether the user is authorized to view the data.

### Distinguishing from other controls

| Mechanism | Primary objective | Can nosniff replace it? |
| --- | --- | --- |
| Accurate `Content-Type` | Declares the media type of the data | No; `nosniff` relies on this information |
| `Content-Security-Policy` (CSP) | Restricts sources and execution of active content | No |
| `Content-Disposition: attachment` | Encourages downloading the file rather than inline rendering | No |
| File/upload validation, separate origin | Reduces risk of untrusted files running on the app origin | No |
| CORS | Controls cross-origin JavaScript reading of responses per browser policy | No |
| CSRF defense | Prevents unwanted state-changing requests via auto-sent credentials | No |
| `X-Frame-Options` / CSP `frame-ancestors` | Restricts embedding pages inside frames | No |

## 4. How does Spring Security Servlet send X-Content-Type-Options?

### 4.1. Spring Security defaults

In a typical **Spring Security Servlet** configuration, when a request passes through `SecurityFilterChain` and HTTP security headers have not been disabled, Spring Security adds by default:

~~~http
X-Content-Type-Options: nosniff
~~~

The component responsible for writing security headers resides in Spring Security's `HeaderWriterFilter`/`HeaderWriter` pipeline; the Content-Type Options writer provides `nosniff`. Thus many Spring Boot apps with `spring-boot-starter-security` already include this header even without explicit custom configuration.

**However, actual responses must be verified**: the header can be missing when requests bypass the security chain, the application disabled headers, another filter/proxy interferes, or errors are returned directly by another layer. Static resource headers also need inspection, not just JSON controllers.

### 4.2. Configuring Spring Security 6+ with Java 17

The example below is a **configuration class inside a Spring Boot 3.x / Spring Security 6+ project**, using `spring-boot-starter-web` and `spring-boot-starter-security`. This snippet is not a standalone Java program run via `javac`; the Spring container provides `HttpSecurity` and builds `SecurityFilterChain`.

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**", "/api/status", "/download/**")
                .permitAll()
                .anyRequest().authenticated())
            .headers(headers -> headers
                .contentTypeOptions(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

`contentTypeOptions(Customizer.withDefaults())` here **makes intent explicit**; when default headers have not been disabled, calling it explicitly is optional. Security headers **do not grant endpoint access** and do not replace authentication/authorization in `authorizeHttpRequests`.

Avoid this style of configuration without a clear reason:

~~~java
// Should not be used just to "simplify":
// http.headers(headers -> headers.disable());
~~~

That call disables the entire suite of HTTP security headers managed by Spring Security, not only `nosniff`. If there are multiple `SecurityFilterChain` beans, inspect which chain matches each URL and whether headers appear on responses from every chain. Configuring one chain does not automatically ensure responses handled by another chain carry the same headers.

**Especially for static assets:** prefer `permitAll()` for public URLs that still need security headers. If you exclude assets from Spring Security via `WebSecurityCustomizer.ignoring()`, requests may skip `HeaderWriterFilter` and lose defensive headers; in that case, the web server/CDN must take responsibility for adding them. Likewise, responses served directly by nginx/gateway/CDN may never reach Spring Security.

### 4.3. Proper MIME types per endpoint

The `nosniff` header is only effective when the server declares sensible media types. For Spring MVC:

- CSS resources return `Content-Type: text/css`.
- JS resources return a valid JavaScript MIME type, typically `text/javascript` or another browser-accepted compatible type. Do not force every file to `text/plain` to "be safe" if the browser genuinely needs to load scripts/styles.
- JSON returns `application/json`; plain text uses `text/plain; charset=utf-8`; HTML uses `text/html` only for trusted content.
- Downloadable files should use the MIME type matching the data and, when inline rendering is unnecessary, include `Content-Disposition: attachment`.
- When serving resources through proxies, object storage, or CDNs, verify the actual `Content-Type` downstream of those layers.

The controller below illustrates a JSON API and a CSV download endpoint, keeping content types explicit. Each public class resides in a matching file inside the Spring Boot project; the snippet below is **file `ResourceController.java`**:

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ResourceController {
    public record StatusResponse(String status) {}

    @GetMapping(path = "/api/status",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public StatusResponse status() {
        return new StatusResponse("ok");
    }

    @GetMapping("/download/report")
    public ResponseEntity<byte[]> download() {
        byte[] csv = "name,score\nLan,90\n"
            .getBytes(StandardCharsets.UTF_8);

        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("text/csv"))
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"report.csv\"")
            .body(csv);
    }
}
~~~

With Jackson via `spring-boot-starter-web`, `GET /api/status` returns JSON like `{"status":"ok"}` with media type `application/json`. For the CSV download endpoint, the server returns `Content-Type: text/csv`, `Content-Disposition: attachment; filename="report.csv"`, and the CSV body. The `X-Content-Type-Options: nosniff` header is added at the filter layer by Spring Security if the request traverses the configured chain.

For static resources, place `app.js` in `src/main/resources/static/assets/app.js` and inspect the actual response of `GET /assets/app.js`. Spring Boot may determine MIME types from the servlet container mapping or resource configuration, so do not assume one fixed header value across every environment.

### 4.4. A note on HTTP and caching

Caches/CDNs can store both bodies and headers; misconfiguration can cause a valid JS resource to be served with `text/plain` or without `nosniff`. After fixing it, purge affected caches and verify responses through the CDN, not just directly from the app. Do not emit two conflicting `Content-Type` headers between proxy and application.

Every response should have one unambiguous MIME interpretation and one consistent `nosniff` value. A server can return HTTP status 200 while the browser still blocks the resource due to a wrong MIME type; that is a signal to **fix the `Content-Type` configuration**, not to delete `nosniff` to "make the error go away".

## 5. Practical verification

### 5.1. Inspecting HTTP headers

Run the Spring Boot app and check the endpoints:

~~~bash
curl -i http://localhost:8080/api/status
curl -I http://localhost:8080/download/report
curl -I http://localhost:8080/assets/app.js
~~~

These commands are examples; the final static endpoint only exists if you created `app.js`. For `/api/status` with the sample configuration, the key parts of the response are **expected** to look like:

~~~http
HTTP/1.1 200
Content-Type: application/json
X-Content-Type-Options: nosniff

{"status":"ok"}
~~~

Some servers add charset, `Content-Length`, other headers, or reorder headers; this is an **abbreviated sample**, not verbatim output from a run. `curl -I` sends HEAD; Spring MVC handles HEAD for many GET mappings, though custom endpoints might require testing with GET. For the CSV file, also verify `Content-Disposition`.

Value check: if a response has `nosniff` yet JavaScript is still blocked because `Content-Type: text/plain`, the mechanism is doing its job; **fix the content type provided by the server**, do not disable the header.

### 5.2. Spring Security integration testing

With standard Spring Boot/Spring Security test dependencies, you can place `SecurityHeaderTest.java` in the test directory under the same package as the application:

~~~java
package com.example.demo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeaderTest {
    @Autowired
    MockMvc mvc;

    @Test
    void jsonEndpointHasNosniffAndCorrectMime() throws Exception {
        mvc.perform(get("/api/status"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(content()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.status").value("ok"));
    }
}
~~~

This test verifies that the response inside the application context has the header and proper JSON type; **it does not simulate the browser's MIME-blocking algorithm**. The test also requires the `SecurityFilterChain` and controller configuration from the previous section along with actual Spring Boot dependencies. It can be extended to test static assets, 401/403/404 routes, file downloads, and other chains if the app uses them.

### 5.3. Checking in the browser

1. Open DevTools → **Network**; select responses for CSS, JS, JSON, and uploaded files and observe `Content-Type`/`X-Content-Type-Options`.
2. Create a test page embedding a `text/plain` file as `<script src="...">` in a test environment; modern browsers should block execution when the response carries `nosniff`.
3. Check **Console** for messages about MIME/strict MIME type checking, and verify stylesheets are served with `text/css`.
4. Test real traffic paths through reverse proxies/CDNs, error states, and static responses; they can differ from `MockMvc`.
5. Never conclude "secure" from headers alone: continue checking uploads, CSP, access controls, accepted file types, and whether untrusted content can run on the same origin.

## 6. Troubleshooting common issues

| Symptom | Causes to check | Remediation |
| --- | --- | --- |
| Browser reports "Refused to execute script … MIME type text/html/text/plain" | JS URL points to an error page, login page, or server declares wrong `Content-Type` | Inspect URL, 200/302/404, body, and `Content-Type`; serve real JS with a JS MIME type |
| Stylesheet is not applied; strict MIME check | CSS is returned as `text/html` or `text/plain` | Fix resource server/mapping to return `text/css` |
| API returns `application/json` but someone suggests removing `nosniff` to embed via `<script>` | Wrong mechanism used to load JSON | Use `fetch`/XHR with proper authentication and CORS; do not turn JSON into JavaScript |
| Some URLs have `nosniff`, others do not | Multiple `SecurityFilterChain` beans, `web.ignoring()`, CDN/proxy, or different error handlers | Identify which layer returns the response and add the header at the right layer |
| Browser still runs untrusted HTML | HTML is served with valid `text/html`, so `nosniff` is not an XSS barrier | Separate origins, attachment/sandbox, CSP, and upload rules |
| `curl` returns HTTP 200 but browser reports blocked MIME | Browser performs separate execution/MIME checks | Use DevTools, fix `Content-Type`; do not treat 200 as proof a script executes |
| Header is present yet malicious JavaScript still runs | Server or app served that content under a valid JavaScript MIME type | Control script sources, uploads, CSP, and permissions; `nosniff` does not analyze whether code is malicious |

### Production deployment checklist

- [ ] Protected responses, including **JS, CSS, JSON, and untrusted resources**, return accurate and consistent `Content-Type`.
- [ ] Responses traversing Spring Security Servlet include `X-Content-Type-Options: nosniff`; headers are not accidentally disabled or chains bypassed.
- [ ] Responses emitted by **CDNs, reverse proxies, storage, web servers, and error handlers** are also verified; do not test only controllers.
- [ ] User-controlled HTML/SVG/scripts are not allowed to run on origins holding sensitive privileges; control downloads, MIME types, and CSP appropriately.
- [ ] Do not rely on `nosniff` to handle **CORS, CSRF, XSS, authorization, or upload validation**.
- [ ] Both HTTP header tests and browser/DevTools tests exist; when scripts/styles are blocked, fix the resource's MIME type instead of disabling `nosniff`.

**Conclusion:** `X-Content-Type-Options: nosniff` is an important barrier helping browsers refuse to treat certain MIME-mismatched responses as **JavaScript or CSS**, while also supporting browser-specific cross-origin protections. In Spring Security Servlet, this header is typically enabled by default. Its effectiveness depends on **accurate `Content-Type`, the real path through filters/proxies, and how untrusted content is stored and served**; `nosniff` is not a comprehensive defense for all forms of resource loading.
