# X-Content-Type-Options and content-type control in Spring Security

A web application serves a file ending in `.js` yet attaches `Content-Type: text/plain`. Should the browser guess that the body looks like JavaScript and execute it? If such "content guessing" (*MIME sniffing*) is allowed on a user-uploaded resource or a mislabeled response, the browser risks running unintended code in the website's context.

**`X-Content-Type-Options: nosniff`** is an HTTP response header instructing the browser to honor the MIME type declared by the server rather than inferring content type from the payload. For requests using a resource as a **script** or **stylesheet**, modern browsers refuse to load/execute it when the MIME type does not match. This header is an important defense layer against **MIME confusion** and certain **XSS** vectors, though it **does not fix an incorrect `Content-Type` itself and does not replace Content Security Policy (CSP), file upload validation, or output escaping**.

This lesson belongs to the **Browser Protection** section of **Spring Security - fundamentals**. Focus: distinguishing `Content-Type` from `X-Content-Type-Options`, understanding `nosniff`, its impact on JavaScript/CSS/HTML and uploaded files, how Spring Security Servlet configures it by default, testing on Java 17+, and diagnosing browser MIME errors. Main examples use **Spring Boot 3.3.x, Spring Security 6.3.x, Java 17+**.

## 1. What is a MIME type? Why doesn't a file extension decide everything?

A **MIME type** (media type) describes the data type the server claims to send in an HTTP response. Some examples:

| Resource | Common Content-Type | Notes |
| --- | --- | --- |
| HTML page | `text/html; charset=UTF-8` | Browser parses as HTML when appropriate |
| JavaScript | `text/javascript` | Standard JavaScript MIME type, widely used for scripts |
| CSS stylesheet | `text/css` | Standard type for CSS |
| JSON API | `application/json` | JSON data, not executable JavaScript merely because syntax looks similar |
| Plain text | `text/plain; charset=UTF-8` | Displayed as text |
| PNG image | `image/png` | Image data |
| PDF | `application/pdf` | Handled by browser or PDF viewer |
| Generic binary file | `application/octet-stream` | Does not claim to be script or HTML |

A response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=UTF-8
X-Content-Type-Options: nosniff

console.log("example");
~~~

indicates the server **intentionally** sends JavaScript. Conversely:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
X-Content-Type-Options: nosniff

console.log("example");
~~~

indicates the server sends **plain text**. If the second response is referenced by a page as a script, the browser should refuse to execute it as JavaScript.

**File extensions are not sole proof of MIME type:** `app.js` could be served with `text/html` because the request redirected to a login page; `report.txt` could contain strings resembling HTML; an extensionless endpoint can still return JavaScript or CSS if configured properly.

Thus, the decisive factor is the **`Content-Type` in the actual HTTP response**, not just the filename or URL.

### Content-Type is not X-Content-Type-Options

The two headers do two different jobs:

~~~http
Content-Type: text/css
X-Content-Type-Options: nosniff
~~~

- **`Content-Type`:** the server announces what type the content is.
- **`X-Content-Type-Options: nosniff`:** the server tells the browser **not to override the declared type by guessing from the bytes**.

**Nosniff does not turn `text/plain` into `text/javascript`.** If a resource is genuinely JavaScript, **fix the server to return the proper JavaScript MIME type**, rather than disabling `nosniff` so the browser tries to guess.

## 2. MIME sniffing and security risks

Historically, some browsers tried to "help" when a server omitted or misconfigured a MIME type: they inspected the leading bytes of the response and guessed whether it was HTML, script, CSS, or another format. While this helped legacy websites work despite server misconfiguration, it blurred the boundary between **data** and **executable code**.

Consider a hypothetical scenario:

1. A website allows users to upload a text or composite file.
2. The file content partially resembles HTML or JavaScript.
3. The server serves the file from a publicly readable URL, but `Content-Type` is missing or wrong.
4. Another page references that URL as an executable resource, or a user navigates directly to the file.
5. If the browser sniffs the file as executable content instead of data, an XSS or MIME confusion attack path can emerge.

This is a **threat model**, not a claim that every browser, context, and MIME mismatch leads to execution. Modern behavior is also governed by Fetch, module scripts, CSP, CORB/CORP, and other browser rules.

### Safe example of type confusion

HTML loading a script:

~~~html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>MIME demo</title></head>
<body>
  <script src="/assets/mislabeled.js"></script>
</body>
</html>
~~~

Server response for `/assets/mislabeled.js`:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
X-Content-Type-Options: nosniff

console.log("This is plain text data, not a valid script");
~~~

The browser can log a message such as "Refused to execute script ... MIME type text/plain ... strict MIME type checking" and **refuse to run JavaScript from this response**. The purpose of this example is controlling data type interpretation, not proving the server authenticated the user or prevented every XSS class.

## 3. Header syntax and the meaning of nosniff

Primary syntax:

~~~http
X-Content-Type-Options: nosniff
~~~

`nosniff` is the directive supported by browsers for this header. There is no list of "safer" values like `deny`, `strict`, `on`, or `nosniff=true` to substitute for it. `DENY` belongs to **`X-Frame-Options`**, not `X-Content-Type-Options`.

According to the Fetch/MDN specification, two consequences must be clear:

1. **For requests whose destination is script or style:** the browser blocks the response if the MIME type is not a valid JavaScript MIME type or `text/css`, respectively.
2. **For other response types, including certain document navigations:** the browser does not use MIME sniffing to transform the content into another type; for example, content declared as `text/plain` should not automatically be interpreted as `text/html` just because the body looks like HTML.

Do not think of `nosniff` as "the browser blocks every file with the wrong extension." For scripts/styles, the decision depends on **request destination and MIME type**, not merely the filename extension.

### Comparing scenarios

| Usage context | Response Content-Type | Has nosniff | Expected modern browser behavior |
| --- | --- | --- | --- |
| `<script src="...">` | `text/javascript` | Yes | May load and execute if other policies allow |
| `<script src="...">` | `text/plain` | Yes | Refused as a script |
| `<script src="...">` | `text/html` | Yes | Refused as a script |
| `<link rel="stylesheet" ...>` | `text/css` | Yes | May apply if other conditions are valid |
| `<link rel="stylesheet" ...>` | `text/plain` | Yes | Refused as a stylesheet |
| Navigation to a text file | `text/plain` | Yes | Does not sniff text into HTML |
| `fetch("/api/data")` | `application/json` | Yes | Handled as a data response per fetch/CORS policies, not auto-treated as script |
| `.js` file returning login HTML | `text/html` | Yes | Does not use that HTML response as a script |

"May load" **does not guarantee success**: the URL can still fail due to 404, 401, CORS/CSP, integrity checks, network errors, or invalid JS/CSS syntax.

### Module scripts also enforce strict MIME checks

~~~html
<script type="module" src="/assets/main.js"></script>
~~~

Module scripts perform strict MIME type checking; a response without an appropriate JavaScript MIME type will not be executed as a module. **Do not argue that "modules are already safe enough so we can drop nosniff"**: `nosniff` remains a general defensive header active in other contexts.

## 4. Three necessary layers: right type, nosniff, and data management

A solid mental model:

~~~text
Correct Content-Type?
       |
       +--> No -> fix server / static resource / controller config
       |
       +--> Yes
             |
             v
Has X-Content-Type-Options: nosniff?
       |
       +--> No -> higher chance of browser MIME sniffing depending on context
       |
       +--> Yes
             |
             v
Data and executable content protections in place?
       |
       +--> Upload validation, HTML escaping, CSP,
       |    Content-Disposition, access control,
       |    separate domain for untrusted files...
       |
       v
Test response headers and real browser behavior
~~~

The `nosniff` header is a **defense layer**; it does not replace upload input validation, filtering dangerous content on render, XSS prevention, or file access authorization.

For example, an endpoint returning `Content-Type: text/html` and `X-Content-Type-Options: nosniff` that directly interpolates untrusted HTML into the page body is still vulnerable to XSS. Seeing the header **does not mean the browser will reject an HTML page legitimately declared by the server**. You must escape or sanitize untrusted data according to context.

## 5. Spring Security adds X-Content-Type-Options by default

In a Servlet application with a standard Spring Security filter chain, Spring Security 6.x adds by **default**:

~~~http
X-Content-Type-Options: nosniff
~~~

It is one of the default security response headers alongside headers such as cache control and frame options (the exact header set can vary by version/protocol).

With a simple configuration:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().permitAll()
        );
    return http.build();
}
~~~

Spring Security still writes `nosniff` for responses **handled by the chain**, even though `permitAll()` means the page requires no login. **`permitAll()` does not mean disabling security headers.**

To configure this header explicitly in the DSL:

~~~java
http.headers(headers -> headers
    .contentTypeOptions(Customizer.withDefaults())
);
~~~

This is a configuration snippet placed inside a method receiving `HttpSecurity`, importing `org.springframework.security.config.Customizer`. In standard applications, specifying it explicitly is usually **unnecessary** because `nosniff` is already enabled by default.

### Do not disable all security headers to fix JS/CSS errors

The following configuration is an **example of what NOT to do as a MIME fix**:

~~~java
// DO NOT apply just to fix MIME errors:
http.headers(headers -> headers.disable());
~~~

It disables the entire security header writer suite, potentially stripping unrelated defense layers. Similarly:

~~~java
// Illustrates syntax to disable nosniff alone — not a recommended solution:
http.headers(headers -> headers
    .contentTypeOptions(options -> options.disable())
);
~~~

If the browser reports a script was blocked due to `Content-Type: text/html` or `text/plain`, inspect **what the server actually returns at that script URL** rather than rushing to remove `nosniff`.

### Resources bypassed from the filter chain

In Spring Security, configuring `web.ignoring()` for a set of resources causes requests to **skip the security filter chain**, meaning headers added by Spring Security may also disappear. For public static resources, prefer:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**", "/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

rather than bypassing the Spring Security filter chain completely just to let browsers load CSS/JS. With multiple `SecurityFilterChain` beans, verify that static asset paths are handled by a chain containing the header writers.

**Important:** this header belongs to the **HTTP response**, not a `@PreAuthorize` rule or authentication flag. Users do not need to log in for browsers to receive `nosniff`; the server should emit the header on protected responses, including public assets.

## 6. Distinguishing resource MIME from upload request MIME

`Content-Type` can appear in both **requests** and **responses**, with different purposes:

~~~http
POST /api/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=ExampleBoundary
~~~

This is a **request Content-Type**: the client describes the payload it is sending.

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
X-Content-Type-Options: nosniff
~~~

This is a **response Content-Type**: the server describes the returned data for the browser to handle.

`X-Content-Type-Options` is a **response header**. It does not perform file upload validation and does not force the server to check whether an uploaded file really is `image/png` as claimed by the client. An attacker can send `Content-Type: image/png` with arbitrary bytes; the server must validate the actual format per policy and may need to re-encode or isolate files.

Checks to consider for uploads:

1. Allowlist of permitted file types/extensions by business requirement.
2. Verify actual media type (do not trust client headers alone).
3. Enforce size limits, file counts, and safe storage paths.
4. Scan for malicious content / safely unpack based on file type and risk level.
5. Serve files from a separate domain without application session cookies when isolation is needed.
6. Set the accurate `Content-Type` when serving files.
7. Use `Content-Disposition: attachment` unless inline rendering is specifically justified.
8. Consider CSP/sandboxing for user-controlled HTML/SVG content.
9. Enforce authorization for viewing/downloading files and prevent path traversal.

**No single header turns arbitrary uploaded files into safe content for inline rendering on the application's origin.**

## 7. Small Java 17+ program to understand MIME rules by destination

The standalone `MimePolicyDemo.java` below uses minimal educational rules for scripts and stylesheets. It **does not reimplement the full Fetch/MIME Sniffing Standard**, and ignores JavaScript MIME aliases and special browser rules. Its goal is to show that **request destination** determines how MIME is evaluated.

~~~java
import java.util.Locale;

public class MimePolicyDemo {

    static boolean matchesDestination(String destination, String contentType) {
        if (contentType == null) {
            return false;
        }

        String mime = contentType.split(";", 2)[0]
                .trim()
                .toLowerCase(Locale.ROOT);

        return switch (destination) {
            case "script" ->
                    mime.equals("text/javascript")
                    || mime.equals("application/javascript");
            case "style" -> mime.equals("text/css");
            default -> true; // Demo: other types not modeled.
        };
    }

    public static void main(String[] args) {
        System.out.println(matchesDestination(
                "script", "text/javascript; charset=UTF-8"));
        System.out.println(matchesDestination(
                "script", "text/plain"));
        System.out.println(matchesDestination(
                "style", "text/css"));
        System.out.println(matchesDestination(
                "style", "text/html"));
        System.out.println(matchesDestination(
                "script", "application/javascript"));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac MimePolicyDemo.java
java MimePolicyDemo
~~~

Deterministic stdout:

~~~text
true
false
true
false
true
~~~

Explanation: a valid JavaScript MIME type works as a script; `text/plain` does not; CSS requires `text/css`; `text/html` does not work as a stylesheet. **This method is an educational illustration of MIME matching, not a production content-validation system.**

## 8. Spring Boot example: returning proper Content-Type with default nosniff

The following Spring MVC example demonstrates both **properly MIME-typed resources** and **deliberately mislabeled resources** so you can observe browser rejection. JavaScript/CSS bodies are harmless strings and require no database.

The project uses **Java 17+, Spring Boot 3.3.x, and Spring Security 6.3.x**.

### 8.1. Directory structure

~~~text
mime-security-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/example/mimesecurity/
│   ├── MimeSecurityApplication.java
│   ├── SecurityConfig.java
│   └── ResourcesController.java
└── src/test/java/example/mimesecurity/
    └── MimeSecurityTest.java
~~~

### 8.2. settings.gradle and build.gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'mime-security-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
~~~

When integrating into an existing Spring Boot project, add only the needed dependencies; avoid duplicate plugin/version declarations.

### 8.3. MimeSecurityApplication.java

`src/main/java/example/mimesecurity/MimeSecurityApplication.java`:

~~~java
package example.mimesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MimeSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MimeSecurityApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig.java

`src/main/java/example/mimesecurity/SecurityConfig.java`:

~~~java
package example.mimesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/private").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .headers(headers -> headers
                .contentTypeOptions(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Although `.contentTypeOptions(Customizer.withDefaults())` is shown explicitly for clarity, Spring Security **already enables `nosniff` by default** when security headers are not disabled. We require authentication on `/private` to show that 401 responses inside the filter chain also carry the header; other URLs are public yet **still pass through the chain**.

Because this demo has no write endpoints and only uses GET, it does not adjust CSRF. If adding POST/PUT/DELETE or browser sessions, apply authorization and CSRF per real architecture.

### 8.5. ResourcesController.java

`src/main/java/example/mimesecurity/ResourcesController.java`:

~~~java
package example.mimesecurity;

import java.util.Map;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ResourcesController {

    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    public String index() {
        return """
                <!doctype html>
                <html lang="en">
                <head>
                  <meta charset="UTF-8">
                  <link rel="stylesheet" href="/assets/style.css">
                  <link rel="stylesheet" href="/assets/mislabeled.css">
                </head>
                <body>
                  <h1>MIME demo</h1>
                  <script src="/assets/app.js"></script>
                  <script src="/assets/mislabeled.js"></script>
                </body>
                </html>
                """;
    }

    @GetMapping(value = "/assets/app.js", produces = "text/javascript")
    public String script() {
        return "console.log('correct JS MIME');";
    }

    @GetMapping(value = "/assets/mislabeled.js",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String mislabeledScript() {
        return "console.log('MIME mismatch');";
    }

    @GetMapping(value = "/assets/style.css", produces = "text/css")
    public String style() {
        return "body { color: navy; }";
    }

    @GetMapping(value = "/assets/mislabeled.css",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String mislabeledStyle() {
        return "body { color: navy; }";
    }

    @GetMapping(value = "/api/info",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> info() {
        return Map.of("message", "json data");
    }

    @GetMapping("/uploads/example.txt")
    public ResponseEntity<String> download() {
        String textWithHtml = "<html><body>Just text</body></html>";

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename("example.txt")
                                .build()
                                .toString())
                .body(textWithHtml);
    }

    @GetMapping("/private")
    public String privatePage() {
        return "private data";
    }
}
~~~

Notes:

- `/assets/app.js` declares the proper JavaScript MIME type, so browsers can execute it.
- `/assets/mislabeled.js` has a `.js` extension and JavaScript body, yet the server **deliberately** returns `text/plain`. With `nosniff`, browsers must refuse to run it as a script.
- `/assets/style.css` returns `text/css`, whereas `/assets/mislabeled.css` returns `text/plain`. Browsers will not mistakenly apply `text/plain` as CSS in a stylesheet context.
- `/api/info` returns JSON to distinguish data responses from scripts.
- `/uploads/example.txt` deliberately contains an HTML-like string while returning `text/plain` and `Content-Disposition: attachment`. This demonstrates serving a **download** rather than rendering inline in the application's origin.
- `@RestController` returns the body directly, while `produces`/`ResponseEntity.contentType(...)` determines the media type; URL extensions do not override them.
- `/private` is protected by the security chain. No username/password is configured here since login isn't the focus; unauthenticated requests typically receive 401 from the HTTP Basic entry point.
- The sample performs no real upload or file content validation and must not be used directly as a production upload handler.

**Copy-paste note:** Java 17 supports `"""` text blocks in `index()`. The Java snippets above are complete standalone files with package/import declarations, requiring neither JSP nor Thymeleaf.

## 9. Testing headers and MIME with MockMvc

MockMvc checks **the actual response headers produced by Spring Security and Spring MVC**, but **does not run a browser's JavaScript/CSS execution engine**. Thus, we verify the server emits the conditions enabling `nosniff`, without claiming a MockMvc test observed the browser refusing execution.

`src/test/java/example/mimesecurity/MimeSecurityTest.java`:

~~~java
package example.mimesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MimeSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void htmlIsServedAsHtmlWithNosniff() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_HTML))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void javascriptIsServedWithCorrectMime() throws Exception {
        mvc.perform(get("/assets/app.js"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.parseMediaType("text/javascript")))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void cssIsServedWithTextCss() throws Exception {
        mvc.perform(get("/assets/style.css"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.parseMediaType("text/css")))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void mislabeledScriptIsStillPlainText() throws Exception {
        mvc.perform(get("/assets/mislabeled.js"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void mislabeledStyleIsStillPlainText() throws Exception {
        mvc.perform(get("/assets/mislabeled.css"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void jsonHasApplicationJsonAndNosniff() throws Exception {
        mvc.perform(get("/api/info"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void untrustedTextIsAttachmentNotHtml() throws Exception {
        mvc.perform(get("/uploads/example.txt"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        containsString("attachment")))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void publicAssetStillGetsSecurityHeader() throws Exception {
        mvc.perform(get("/assets/style.css"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }
}
~~~

Run command:

~~~bash
./gradlew test --tests '*MimeSecurityTest'
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "*MimeSecurityTest"
~~~

**Expected result:** 9 tests pass with the stated dependencies and versions. This is an **expectation based on the code**, not an actual test execution report from this environment.

What the tests prove:

1. The `nosniff` header is attached to public HTML, CSS, JS, JSON, text download, and protected responses.
2. `Content-Type` properly separates valid JavaScript/CSS from deliberately mislabeled resources.
3. Public resources traversing `SecurityFilterChain` still receive security headers.
4. MockMvc **does not** test whether browsers execute `app.js` or reject `mislabeled.js`. Real browser verification follows next.

## 10. Verifying in a real browser

Use the sample project from Section 8. With a compatible Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Open `http://localhost:8080/` and Developer Tools → Network/Console.

Observe:

1. `GET /` returns `text/html` and `X-Content-Type-Options: nosniff`.
2. `GET /assets/app.js` returns `text/javascript` and `nosniff`. Console shows the log from the properly typed script.
3. `GET /assets/mislabeled.js` returns `text/plain` and `nosniff`. The browser refuses to execute it as a script; exact console wording varies by browser.
4. `GET /assets/style.css` returns `text/css` and is applied.
5. `GET /assets/mislabeled.css` returns `text/plain`, so the browser ignores it as a stylesheet.
6. `GET /uploads/example.txt` has `text/plain` and `Content-Disposition: attachment`, typically handled as a download per browser policy.

**Do not disable nosniff to create the demonstration.** The `mislabeled` endpoints deliberately use wrong MIME types to test browser rejection. Production systems must **fix the returned MIME type**.

### When the browser reports a strict MIME checking error

Example generic log:

~~~text
Refused to execute script because its MIME type ("text/html")
is not executable, and strict MIME type checking is enabled.
~~~

The usual cause is **not a corrupted script file**, but that the request to `/assets/app.js` received **HTML** from the server:

- Wrong script URL, leading to an HTML 404 error page.
- User is not logged in, server redirects to `/login` and returns login HTML.
- Reverse proxy/cache returns an SPA HTML fallback page for the `.js` path.
- Spring Security filter chain blocks loading static assets, returning an error page.
- Static resources built/deployed to the wrong path or wrong server MIME mapping.

How to check: open **Network → the JS file request → Status, Redirect chain, Response headers, Preview/Response body**. If the body is a login/404 page, fix routing/authorization. Do not look only at the `.js` extension and turn off `X-Content-Type-Options`.

### When CSS files fail to apply

If `<link rel="stylesheet" href="/assets/style.css">` is blocked, check request status, `Content-Type: text/css`, `X-Content-Type-Options`, response body, browser console, and CSP. An endpoint returning CSS as `application/octet-stream` or `text/plain` is not equivalent to `text/css`. Returning the right MIME type is the primary fix.

## 11. Static resources, Spring MVC, and proxy servers

Spring Boot/Spring MVC normally serves static resources from default locations such as:

~~~text
src/main/resources/static/
src/main/resources/public/
src/main/resources/resources/
src/main/resources/META-INF/resources/
~~~

For example, placing `src/main/resources/static/assets/app.js` causes Spring MVC's resource handler to serve `/assets/app.js` per configuration. In the full demo above, resources are returned by a Controller to showcase `produces` explicitly; **do not add static files at the same paths** in that project to avoid competing mappings.

If static content is served **outside the Spring Security filter chain**, such as by Nginx or a CDN, Spring Security's default headers **do not automatically propagate to CDN-generated responses**. Verify headers at the **point where users actually receive responses**, not only on local backend ports.

Items to verify:

- Spring Security permits assets with `permitAll`, keeping the filter chain involved.
- Controllers declare accurate `produces` or `ResponseEntity.contentType(...)`.
- Static resource handlers resolve accurate MIME types from file mappings.
- Reverse proxies do not overwrite `Content-Type` or strip `X-Content-Type-Options`.
- CDNs and caches do not serve an HTML error page for `.js`/`.css` URLs.
- HTTP 200/304/401/403/404 statuses are configured consistently; never assume responses outside the filter chain carry headers.
- Check gzip/brotli and `Content-Encoding` separately from `Content-Type`: compression does not turn CSS into JavaScript.

### Content-Encoding differs from Content-Type

Example:

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript
Content-Encoding: gzip
X-Content-Type-Options: nosniff
~~~

`Content-Type` describes the media type after decoding content codings, while `Content-Encoding` describes how the bytes are compressed/encoded for transfer. **Do not fix MIME errors by changing gzip settings or extensions.** Ensure both media type and compression are configured correctly and independently.

## 12. Controlling file uploads and user-generated resources

File uploads are sensitive because the bytes are **not fully under server control**. If a site accepts `avatar.svg`, `report.html`, or complex file formats, browsers may treat them in unexpected ways on direct navigation, embedding, or download.

Layers of defense to combine:

| Layer | Action required |
| --- | --- |
| Input validation | Validate permitted file types, magic bytes, size, and structure |
| Storage | Rename files to prevent path traversal, restrict execute permissions |
| Response MIME | Attach `Content-Type` matching the verified file type |
| Nosniff | Send `X-Content-Type-Options: nosniff` |
| Download policy | Use `Content-Disposition: attachment` for files not meant for inline rendering |
| Domain isolation | Serve untrusted content from a separate origin without app session cookies |
| CSP/sandbox | Restrict how user-controlled HTML/SVG can execute scripts or embed frames |
| Authorization | Verify who is allowed to view/download the file |
| Audit | Log metadata safely without exposing sensitive files or credentials |

Example of an endpoint returning a text file containing HTML strings:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Disposition: attachment; filename="report.txt"
X-Content-Type-Options: nosniff

<html><body>Untrusted text</body></html>
~~~

The browser is instructed to treat it as a download rather than an application HTML page. Still, **Content-Disposition does not replace scanning/validating files**, and other clients may handle it differently. Never rely solely on the filename `report.txt` to assume data is safe.

### Should all uploaded files live under the same hostname as the application?

If untrusted files can be interpreted as active content (like HTML/SVG), serving them from a **separate** origin without the application's login cookies is a worthwhile defense. It limits blast radius if a browser or MIME config handles content unexpectedly. Pair this with proper CORS/CORP policies and download authorization rather than moving origins and leaving sensitive files public.

## 13. X-Content-Type-Options does not replace CSP, CORS, or CORP

Different headers/policies serve distinct purposes:

| Mechanism | Primary function | Does NOT replace |
| --- | --- | --- |
| `Content-Type` | Declares the response media type | Verifying that source data is trustworthy |
| `X-Content-Type-Options: nosniff` | Stops MIME guessing; blocks mismatched script/style MIME | CSP, file upload validation, XSS escaping |
| `Content-Security-Policy` | Restricts allowed load/execution sources, inline scripts, and content types | Setting the proper Content-Type |
| `Cross-Origin Resource Sharing (CORS)` | Controls whether cross-origin JS in browsers can read responses | Authentication, CSRF, MIME checks |
| `Cross-Origin-Resource-Policy (CORP)` | Restricts certain cross-origin/no-cors resource loads/embeds | Authorization and Content-Type |
| `Content-Disposition` | Hints inline vs download and filename | Malicious file/content inspection |
| `X-Frame-Options` / CSP `frame-ancestors` | Prevents unauthorized framing | Script MIME protection |
| `Strict-Transport-Security` | Tells browsers to use HTTPS for the declared host | Preventing XSS or MIME confusion |

**CORS and nosniff can appear together** on JSON APIs, yet that does not make a response safe if the server returns sensitive HTML to an untrusted origin. Each header addresses its own threat model.

### Avoid misconceptions about cross-origin data

Some browsers enforce cross-origin response protections like CORB/ORB, and `nosniff` can interact with content classification. Do not generalize that "nosniff blocks all cross-origin fetches" or "nosniff replaces CORS." With `fetch`, JS still obeys SOP/CORS and request mode/credentials rules; MIME type is only one part of response handling.

## 14. WebFlux has similar headers but a different API

In Spring WebFlux, security uses `ServerHttpSecurity` and `SecurityWebFilterChain`, **not** Servlet's `HttpSecurity`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges ->
                        exchanges.anyExchange().permitAll())
                .build();
    }
}
~~~

This is an **illustrative reactive configuration** meant for a Spring WebFlux app rather than the Servlet project in Section 8. Spring Security WebFlux also supports security response headers, including `X-Content-Type-Options` by default where applicable. Just as in Servlet, you must still declare the proper MIME type on actual responses; returning `Mono<String>` or `Flux<DataBuffer>` does not automatically turn payloads into properly typed JavaScript/CSS.

## 15. Quick troubleshooting table

| Issue | What to check | Fix direction |
| --- | --- | --- |
| JS reported with `text/html` MIME | Login redirect, SPA HTML fallback, 404/500 page | Fix URL/routing/filter chain and JS MIME |
| JS reported with `text/plain` MIME | Wrong controller `produces` or static mapping | Return `text/javascript` |
| CSS reported with `application/octet-stream` | Wrong web server MIME mapping | Return `text/css` |
| Script blocked despite right Content-Type | CSP, CORS for modules, integrity, JS errors | Inspect Console and Network |
| Missing `X-Content-Type-Options` | Request skipped Spring filter, headers disabled, proxy/CDN | Keep filter chain or configure header at actual source |
| `nosniff` present yet uploaded file is risky | Active content allowed to render on app origin | `Content-Disposition`, separate origin, CSP, validation |
| Browser blocks reading API response | CORS or authentication, not necessarily MIME | Check Origin, CORS, HTTP status |
| MIME right locally, wrong on CDN | Proxy/CDN rewrite/cache, deploy version | Inspect public response headers |
| Confused request vs response `Content-Type` | Looking at wrong panel/header | Check Response Headers for the resource URL |
| `nosniff` disabled to fix assets | JS/CSS actually had wrong declared type | Restore `nosniff`, fix `Content-Type` |
| 404 JSON lacks header | Skipped chain or separate error dispatch | Check the entire security response path |
| 401/login HTML on `.js` URL | Script requires auth, assets not public | Use `permitAll` for appropriate assets, don't drop filter chain |

A quick curl check:

~~~bash
curl -i http://localhost:8080/assets/app.js
curl -i http://localhost:8080/assets/mislabeled.js
curl -i http://localhost:8080/assets/style.css
curl -i http://localhost:8080/uploads/example.txt
~~~

Inspect `Content-Type` and `X-Content-Type-Options` on each response. **Curl does not execute JavaScript or enforce browser policies**, so a 200 status from curl does not prove the browser will accept the asset.

## 16. Mistakes to avoid

1. **"With nosniff enabled, we don't need to set Content-Type."** False. Browsers need accurate MIME types to recognize scripts/CSS.
2. **"Files ending in .js always execute."** False. A `text/plain` response with `nosniff` is blocked for script destinations.
3. **"Nosniff converts text/plain into JavaScript."** False. It tells the browser to respect the declared type.
4. **"Nosniff fixes XSS inside HTML."** False. XSS still occurs when untrusted HTML is rendered as valid HTML.
5. **"With nosniff, arbitrary file uploads are safe."** False. Validation, isolation, download policies, and CSP are still needed.
6. **"Disable the header to make the page work."** That merely hides server MIME mistakes and weakens protection.
7. **"Only authenticated URLs need security headers."** Public static assets should also pass through the header writer.
8. **"`web.ignoring()` is the same as `permitAll()`."** False; ignoring skips the entire filter chain and loses headers.
9. **"Every response ending in .css is a valid stylesheet."** False if the server returns HTML or `text/plain`.
10. **"`X-Content-Type-Options` validates upload request inputs."** False. It is a response header for browsers.
11. **"CORS failed because of nosniff."** These can be two independent failures; read Network and Console.
12. **"CSP and nosniff replace each other."** They complement rather than replace each other.
13. **"JSON can run as JS because it looks like an object."** Never use data MIME types for scripts; browsers check MIME per destination.
14. **"`Content-Encoding: gzip` determines the media type."** False. That is compression/transfer encoding.
15. **"MockMvc tests prove the browser refused to run the script."** False. MockMvc only observes server responses.
16. **"If the local server works, the CDN automatically has the headers."** Not guaranteed. Verify the final response reaching users.
17. **"`nosniff` filters incoming requests like a firewall."** False. It guides browser response handling, not inbound server request blocking.
18. **"HTTP status 200 proves the script loaded."** Browsers may still reject it due to MIME/CSP/module rules.

## 17. Self-check questions

**Question 1.** Does `X-Content-Type-Options: nosniff` change `Content-Type: text/plain` into `text/javascript`?

**Answer:** No. `nosniff` instructs the browser to respect the declared `Content-Type` and refrain from sniffing.

**Question 2.** A page loads `/assets/app.js`; the response is 200 but has `Content-Type: text/html` with `nosniff`. Why does the browser refuse it?

**Answer:** The request expects a script resource yet receives HTML; the MIME type is not JavaScript. Causes include a wrong URL, 404/login fallback, or server misconfiguration.

**Question 3.** `/assets/style.css` returns `Content-Type: text/plain`. What should be fixed?

**Answer:** Fix the server to return `text/css` and keep `nosniff`. Do not disable the header to make browsers guess CSS.

**Question 4.** An API returns JSON with `application/json` and `nosniff`. Does that mean the API authenticated the user?

**Answer:** No. MIME types and `nosniff` do not replace authentication or authorization.

**Question 5.** A user uploads HTML and the server serves it with `Content-Type: text/html` on the same origin. Is `nosniff` enough to stop XSS?

**Answer:** No. The server declared it as HTML; untrusted content must be handled with validation, isolation, `Content-Disposition`, CSP/sandboxing, and proper policies.

**Question 6.** Why can `web.ignoring()` drop `nosniff` on static resources?

**Answer:** Because requests skip the Spring Security filter chain, which contains the component that adds security headers.

**Question 7.** MockMvc confirms status 200, `Content-Type: text/plain`, and `nosniff` for `/assets/mislabeled.js`. Does that prove a real browser blocked the script?

**Answer:** Not yet. MockMvc verifies server-side headers; to confirm browser enforcement, check Network/Console in a real browser.

**Question 8.** Do `X-Content-Type-Options` and `Content-Security-Policy` do the same thing?

**Answer:** No. `nosniff` prevents MIME guessing; CSP restricts allowed resource sources and execution/content rules per policy. They complement each other.

**Question 9.** Does the header belong to requests or responses?

**Answer:** `X-Content-Type-Options` is a **response header**. `Content-Type` can appear in either requests or responses with its corresponding meaning.

**Question 10.** When a `.js` file redirects to an HTML login page, should we configure `Content-Type: text/javascript` on the login page?

**Answer:** No. Fix asset access paths, `permitAll`/routing, and redirects properly; never label login HTML as JavaScript.

**Question 11.** Why do module scripts typically require a proper JavaScript MIME type even if a browser has legacy sniffing behaviors?

**Answer:** Module scripts enforce strict MIME checking. That is not a reason to drop `nosniff` protection in other contexts.

## 18. Pre-deployment checklist

- Do all HTML, JavaScript, CSS, JSON, image, and download responses have accurate `Content-Type` headers?
- Do browsers receive `X-Content-Type-Options: nosniff` on all relevant responses?
- Do public resources traverse the Spring Security filter chain or receive security headers from the edge server?
- Have JS/CSS responses returning HTTP 200 with browser MIME errors been inspected in the Network tab?
- Are login redirects or SPA fallbacks accidentally returning HTML for `.js`/`.css` URLs?
- Is upload request MIME validation clearly separated from download response MIME handling?
- For file uploads, are validation, size limits, `Content-Disposition`, and origin isolation in place?
- Are CSP, CORS, CORP, CSRF, and authorization designed independently per threat model?
- Have final headers been checked behind reverse proxies/CDNs rather than only on local backend ports?
- Have important status/error pages been checked both inside and outside the filter chain?
- Are MockMvc tests in place for HTML, JS, CSS, JSON, mislabeled resources, and unauthorized responses?
- Has a real browser test confirmed that mislabeled resources **are not executed**?

**Conclusion:** `X-Content-Type-Options: nosniff` prevents browsers from **"re-guessing" the media type** declared by the server, specifically blocking scripts and stylesheets with mismatched MIME types. In Spring Security 6.x, this header is **enabled by default** for responses going through the filter chain. The right approach is to **keep `nosniff`, serve accurate `Content-Type` headers, govern user-uploaded content, and verify actual responses in real browsers**.

## References

- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): default `nosniff` and rationale for preventing MIME sniffing.
- [Spring Security — Servlet Security Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): header writers and configuration DSL.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `headers(...contentTypeOptions(...))` in modern configuration.
- [MDN — X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options): script/style destinations and browser MIME handling.
- [MDN — MIME type verification](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/MIME_types): proper MIME requirements for JS/CSS.
- [MDN — Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type): media types in requests and responses.
- [OWASP — HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): recommendations for `nosniff` and accurate Content-Type.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): defense layers for untrusted upload content.
