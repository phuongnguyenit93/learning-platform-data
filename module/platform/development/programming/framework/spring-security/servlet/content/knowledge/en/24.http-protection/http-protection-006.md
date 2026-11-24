# Content-Security-Policy: Resource Sources, Nonces, and Report-Only Mode in Spring Security Servlet

## 1. What problem does CSP solve?

**Content Security Policy (CSP)** is a browser security mechanism declared by a website primarily through the `Content-Security-Policy` HTTP **response header**. The policy specifies which types of resources the browser is permitted to load or execute: JavaScript, CSS, images, fonts, `fetch` connections, iframes, and so on. CSP can also restrict framing of the page, form submission targets, and `<base>` usage.

For example: an application has an input field that renders comments. If an attacker injects content like `<script>...</script>` and that data is improperly rendered as executable HTML, **CSP can block certain unauthorized script execution paths**. This mechanism is **defense in depth** against XSS impacts, malicious script loading, and resource injection. You must still contextually encode/escape output, validate input, secure templates, and prevent DOM XSS; CSP does not replace those controls.

An HTML response may return:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html;charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Meaning: most resource types default to **same origin** only; scripts may only load from same origin; plugin objects are forbidden; `<base>` is restricted and other sites are forbidden from framing the page. The browser enforces these checks and blocks operations violating the policy.

This lesson focuses on three skills: **choosing resource sources accurately by directive**, **issuing random nonces for legitimate inline scripts**, and **using Report-Only mode to observe violations before enforcing**. Examples target **Spring Security Servlet / Spring MVC**, which differs from Reactive WebFlux configuration.

## 2. Where does the browser enforce CSP?

CSP is applied primarily based on the **response** containing the document, not on whether the user is authenticated. For an HTML page:

~~~text
Browser GET /demo
      |
      v
Servlet filters / Spring Security
      |
      v
Spring MVC controller + template
      |
      v
HTML response + Content-Security-Policy header
      |
      v
Browser stores policy applied to document
      |
      +-- Load <script src="...">? Check script-src
      +-- Execute inline <script>? Check nonce/hash/script-src
      +-- Load CSS? Check style-src
      +-- fetch("...")? Check connect-src
      +-- Display image/font? Check img-src/font-src
      +-- Embed document in iframe? Check frame-ancestors
~~~

Server-side **authentication/authorization** decides whether the caller may access an endpoint. **CORS** decides whether JavaScript from another origin may access a cross-origin response within browser rules. **CSP** decides which sources a document may load or execute content from. An endpoint can return 200 with valid CORS and still have scripts blocked by CSP; conversely, CSP allowing `fetch` to another URL **does not** bypass CORS.

A policy can be declared with `<meta http-equiv="Content-Security-Policy" ...>`, but this approach has limitations, including **no support for Report-Only** and **no enforcement of `frame-ancestors`**. For Servlet applications, prefer an **HTTP header** returned by the server/gateway. If multiple enforcing CSP response headers are sent, the browser enforces **all** of them; a broader policy does not relax a stricter one.

## 3. Syntax: directives and source expressions

CSP is a list of directives separated by `;`. Each directive has a name and valid sources for the corresponding resource group:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' https://static.example.com; img-src 'self' data:; object-src 'none'
~~~

Common **source expressions**:

| Value | Meaning and notes |
| --- | --- |
| `'self'` | Same origin as the document (scheme, host, port per CSP rules); not all subdomains or all ports. |
| `'none'` | Allows no sources for that directive; use standalone rather than combining with allowed sources. |
| `https://cdn.example.com` | Allows a specific HTTPS source; you must still evaluate trust and content from the CDN. |
| `https:` | Allows sources over the HTTPS scheme, much broader than a specific hostname. |
| `data:` | Allows data URLs; often considered for images, but very dangerous if carelessly opened for scripts. |
| `blob:` | Allows blob URLs within supporting directives; weigh workers, media, and dynamic code carefully. |
| `*` | Broad wildcard, usually weakens CSP. Do not use as a fix when sources have not been identified. |
| `'nonce-BASE64'` | Allows inline elements whose `nonce` attribute matches the header value; value changes per response. |
| `'sha256-BASE64'` | Allows inline content whose hash matches the exact hashed bytes per CSP rules. |
| `'unsafe-inline'` | Opens unsafe inline execution paths under matching policies/mechanisms; avoid using as a shortcut. |
| `'strict-dynamic'` | Depending on browser/policy, trusts scripts dynamically loaded by scripts bearing a valid nonce/hash; requires compatibility testing and understanding transitive trust. |

Source keywords such as `'self'`, `'none'`, and `'nonce-...'` **require single quotes** in the header. Hostnames and schemes like `https:` or `data:` do not use single quotes.

A nonce or hash applies to inline scripts/styles under the relevant directive, **not** as a license for arbitrary content types or APIs. The CSP header is a browser-enforced policy; it is not an `Authorization` header and is not checked like a login token in controllers.

## 4. Essential directives for HTTP protection

| Directive | Governs | Example |
| --- | --- | --- |
| `default-src` | Fallback source for many resource-fetch types when specialized directives are absent. | `default-src 'self'` |
| `script-src` | Script sources, inline scripts, and certain JavaScript behaviors; related to `script-src-elem`, `script-src-attr`. | `script-src 'self' 'nonce-...'` |
| `script-src-elem` | Controls `<script>` elements; falls back to `script-src` then `default-src` if absent. | `script-src-elem 'self'` |
| `script-src-attr` | Controls inline event handlers like `onclick`; configure to block handler attributes. | `script-src-attr 'none'` |
| `style-src` | Stylesheet sources and inline styles; has `style-src-elem` / `style-src-attr`. | `style-src 'self'` |
| `img-src` | Images from URLs or `data:` when permitted. | `img-src 'self' data:` |
| `font-src` | Fonts loaded via CSS, such as `@font-face`. | `font-src 'self'` |
| `connect-src` | Connections from JS: `fetch`, XMLHttpRequest, WebSocket, EventSource, etc. | `connect-src 'self' https://api.example.com` |
| `frame-src` | Sources of frames/iframes that the current page **loads**. | `frame-src https://player.example.com` |
| `frame-ancestors` | Which origins may **embed the current page in a frame**. | `frame-ancestors 'none'` |
| `object-src` | Plugin resources such as `<object>` and `<embed>`. | `object-src 'none'` |
| `base-uri` | URLs usable by the `<base>` element. | `base-uri 'self'` |
| `form-action` | URLs to which forms on the page may submit. | `form-action 'self'` |
| `worker-src` | Sources of Workers/Service Workers depending on fallback rules. | `worker-src 'self'` |
| `report-uri`, `report-to` | Configures where browsers can send CSP violation reports. | `report-uri /csp-report` |

**Fallbacks to understand correctly:** If `img-src` is omitted, the browser can use `default-src` to check image sources. If `script-src-elem` is omitted, the browser looks at `script-src` and then `default-src`. However, `frame-ancestors`, `form-action`, and `base-uri` **do not simply inherit `default-src`**; declare them explicitly if you want to restrict those behaviors.

Compare two easily confused directives:

- `frame-src`: **whose content your page may embed**.
- `frame-ancestors`: **who may embed your page**. This helps defend against clickjacking, related to `X-Frame-Options` though CSP `frame-ancestors` is more flexible.

Example of a website loading JavaScript from same-origin, images from a CDN, and calling APIs on a separate domain:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https://images.example.com; connect-src 'self' https://api.example.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

`connect-src https://api.example.com` lets the browser **attempt** connections from the document. If the API is cross-origin, the API must still satisfy appropriate **CORS**. CSP permitting a connection target does not automatically grant request authorization or server acceptance.

## 5. Spring Security's default CSP and static policy configuration

In Spring Security Servlet, core security response headers are enabled by default, but **CSP is not automatically enabled with a one-size-fits-all policy**. Developers must identify script, CSS, CDN, and API sources before declaring one.

For a page using only external JavaScript/CSS from the same origin, a static configuration in `HttpSecurity` can look like this. This is a **configuration snippet inside a `SecurityFilterChain` factory method**, not a standalone Java program:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "img-src 'self'; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "frame-ancestors 'none'"
        )
    )
);
~~~

Spring Security integrates CSP via a **response header writer**. For a static policy, this is straightforward. You can enable report-only mode with `.reportOnly()` on the CSP DSL, for example:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("default-src 'self'; script-src 'self'; report-uri /csp-report")
        .reportOnly()
    )
);
~~~

In that mode, the response uses `Content-Security-Policy-Report-Only`. By contrast, the example in this lesson demonstrates a **nonce that changes per response**, so a static string in `policyDirectives` is **not sufficient**. In particular, never generate a nonce once at application startup and reuse it forever in static configuration.

If you have already configured CSP via a header writer or gateway, check **how many policies are actually sent**. Independent enforced policies apply simultaneously, so a second policy can still block scripts even if the first permits a nonce. Avoid manually calling `setHeader` in a filter while also declaring a conflicting policy in Spring Security.

## 6. What is a nonce and when is it needed?

A nonce is a **number used once**: a sufficiently random, unpredictable value generated **fresh by the server for each HTML HTTP response**, placed in two locations:

1. In the CSP header, such as `script-src 'self' 'nonce-f8Wm...'`.
2. In the `nonce` attribute of **the exact `<script>` or `<style>` elements permitted to run**.

Illustrative example (the nonce below is only a sample; do not use it in real code):

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-WjRrMkVzbmZTaW53U3pvaA=='; object-src 'none'
~~~

~~~html
<script nonce="WjRrMkVzbmZTaW53U3pvaA==">
  document.getElementById("status").textContent = "Allowed by nonce";
</script>
<script>
  console.log("Without nonce: blocked in enforcement mode");
</script>
~~~

Under this policy, the browser can run the first script and blocks the second. A nonce cannot be derived from a username, date, session ID, or fixed string. The practical generation method is taking **at least 128 random bits from a cryptographically secure RNG** and Base64-encoding them; for example, `SecureRandom` in Java.

**A nonce is not the same as a CSRF token.** A CSRF token verifies state-changing requests under certain auth models; a CSP nonce identifies inline script/style elements authorized by the document author. Nor is a nonce a secret credential for granting API access.

Important details:

- A nonce only helps when the server controls nonce generation **and** attaches the nonce only to trusted scripts/styles; never attach a nonce to user-supplied HTML or untrusted scripts.
- Inline event handlers like `onclick="..."`, `javascript:` URLs, and `eval(...)` are not automatically allowed just because one `<script>` tag on the page has a nonce. Refactor event handlers to `addEventListener`.
- If inline scripts are unnecessary, prefer moving JavaScript into static files and using `script-src 'self'`; not every SPA needs nonces.
- When using hashes, **changing even a single character of script content** breaks the hash match; hashes suit fixed inline snippets, whereas nonces suit SSR templates generating dynamic pages.
- Never inject untrusted data into attribute positions capable of altering markup/tags; auto-escaping and context-aware output encoding remain essential.
- Nonces do not stop all XSS: if malicious JavaScript already executes on the origin or a trusted script is abused, attack paths still exist. Consider stricter CSP, `'strict-dynamic'`, Trusted Types, and library governance if your threat model requires it.

For dynamic HTML containing a nonce, **never publicly cache a nonced response and reuse it across multiple users or multiple visits**. Use an appropriate caching policy; for instance, `Cache-Control: no-store` for the demo page.

## 7. Runnable example: Spring Boot 3, Java 17, and per-response nonce

We will create a `GET /demo` page rendered with Thymeleaf and a `POST /csp-report` endpoint receiving violation reports. The server:

- Generates 16 bytes using `SecureRandom` when handling each HTML response, Base64-encoded into a nonce.
- Stores the nonce in a **request attribute**, which the controller passes into the template.
- Sets the CSP header containing the **same nonce** before rendering HTML.
- Allows `script-src 'self'` and the `nonce` for trusted inline scripts, blocks `object-src`, and restricts `base-uri` and `frame-ancestors`.
- Switches between **enforce** and **report-only** via the `demo.csp.report-only` property.
- Keeps Spring Security and default CSRF enabled for other endpoints; only the **report endpoint** is exempted from CSRF because browser-sent reports do not carry application form CSRF tokens.

Structure:

~~~text
csp-nonce-demo/
├── pom.xml
├── src/main/java/example/csp/CspDemoApplication.java
├── src/main/resources/templates/demo.html
└── src/test/java/example/csp/CspDemoApplicationTests.java
~~~

### 7.1. Maven and JDK

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>csp-nonce-demo</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

### 7.2. Servlet filter, security chain, and controller

**src/main/java/example/csp/CspDemoApplication.java**:

~~~java
package example.csp;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.security.SecureRandom;
import java.util.Base64;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class CspDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CspDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/demo", "/csp-report").permitAll()
                        .anyRequest().authenticated())
                .csrf(csrf -> csrf.ignoringRequestMatchers("/csp-report"))
                .build();
    }

    @Bean
    FilterRegistrationBean<NonceCspFilter> nonceCspFilter(Environment env) {
        boolean reportOnly =
                env.getProperty("demo.csp.report-only", Boolean.class, false);

        FilterRegistrationBean<NonceCspFilter> registration =
                new FilterRegistrationBean<>(new NonceCspFilter(reportOnly));

        // Apply CSP only to the lab's /demo HTML page.
        registration.addUrlPatterns("/demo");

        // Run early so the controller sees the nonce and header is set before response.
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }

    @Controller
    static class DemoController {

        @GetMapping("/demo")
        String demo(HttpServletRequest request, Model model) {
            model.addAttribute("cspNonce", request.getAttribute("cspNonce"));
            return "demo";
        }

        @PostMapping("/csp-report")
        ResponseEntity<Void> receiveReport() {
            // Demo intentionally discards report content; real systems must
            // process/rate-limit/redact sensitive data.
            return ResponseEntity.noContent().build();
        }
    }

    static final class NonceCspFilter extends OncePerRequestFilter {
        private final SecureRandom random = new SecureRandom();
        private final boolean reportOnly;

        NonceCspFilter(boolean reportOnly) {
            this.reportOnly = reportOnly;
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain filterChain
        ) throws ServletException, IOException {
            byte[] bytes = new byte[16]; // 128 bits
            random.nextBytes(bytes);
            String nonce = Base64.getEncoder().encodeToString(bytes);

            request.setAttribute("cspNonce", nonce);

            String policy =
                    "default-src 'self'; " +
                    "script-src 'self' 'nonce-" + nonce + "'; " +
                    "script-src-attr 'none'; " +
                    "style-src 'self'; " +
                    "img-src 'self' data:; " +
                    "connect-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "form-action 'self'; " +
                    "frame-ancestors 'none'; " +
                    "report-uri /csp-report";

            String headerName = reportOnly
                    ? "Content-Security-Policy-Report-Only"
                    : "Content-Security-Policy";

            response.setHeader(headerName, policy);
            response.setHeader("Cache-Control", "no-store");
            filterChain.doFilter(request, response);
        }
    }
}
~~~

Notes:

1. `NonceCspFilter` is a **Servlet filter** running before the controller; `FilterRegistrationBean` registers the filter specifically for `/demo`. `Ordered.HIGHEST_PRECEDENCE` ensures the filter runs early in the servlet chain. Spring Security filters still handle authentication and authorization as usual.
2. Spring Security **does not automatically provide a dynamic nonce API for templates** merely by writing a static `policyDirectives(...)`. Here, a custom filter sets both the header and a request attribute, and Thymeleaf reads the exact nonce. In real multi-page apps, you can design a shared nonce/header component or a `HeaderWriter` paired with a nonce-generating filter.
3. This example **does not** additionally declare CSP via `http.headers(...contentSecurityPolicy(...))` to avoid unintentionally stacking two enforced policies. Other default Spring Security headers can still be configured separately.
4. The report-receiving endpoint is `permitAll` and CSRF-exempt because violation reports are automatic browser requests. This is an **exception for one exact path**; do not disable CSRF application-wide. Production setups must limit body size, rate-limit, validate format, and handle data that may contain private information.
5. The example registers CSP only for the **`/demo` HTML document**. Other HTML routes in a real app need their own policy or appropriate filter registration; a document's CSP governs the resources that document requests.

### 7.3. Template with nonced script

**src/main/resources/templates/demo.html**:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>CSP nonce demo</title>
</head>
<body>
    <h1>Content Security Policy with nonce</h1>
    <p id="status">Script has not run yet</p>

    <script th:attr="nonce=${cspNonce}">
        document.getElementById("status").textContent =
            "Inline script with nonce has run";
    </script>
</body>
</html>
~~~

Thymeleaf replaces `th:attr="nonce=..."` with a `nonce="..."` attribute in the returned HTML. The nonce in the header is generated on the **same request** and passed to the controller via a request attribute. When the browser loads `/demo`, the script is permitted and the paragraph displays **"Inline script with nonce has run"**.

Note: special characters in templates are handled by Thymeleaf when rendering attributes; never concatenate user input directly into markup. If you add an inline `<script>` **without a nonce** to the template, in enforce mode the browser will refuse to execute that script (unless another allowed source applies). In Report-Only mode, it is recorded as a violation but **not blocked by that policy**.

### 7.4. Running and observing HTTP

In the `csp-nonce-demo` directory, with Maven and JDK 17+ installed, run:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/demo
~~~

The headers will contain `Content-Security-Policy: ... 'nonce-<base64-value>' ...`. The HTML body will contain `<script nonce="<same-base64-value>">`. On a new GET request, the nonce will normally **differ** because the server generates a random value per response.

Operational check: open `http://localhost:8080/demo` in a browser, inspect **Network → /demo → Response Headers**, verify the CSP header, and check that the page displays **"Inline script with nonce has run"**. Then temporarily add an unnonced inline script to observe the CSP error in DevTools Console during practice; in enforce mode it does not execute.

Switch to **Report-Only** by stopping the app and running:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.csp.report-only=true
~~~

The response will then carry `Content-Security-Policy-Report-Only` instead of the enforced header from the demo filter. The browser **reports** policy violations without blocking because the policy is report-only. Nonced scripts still run; unnonced scripts can also run if no other enforced policy blocks them. Depending on the browser, `/csp-report` may receive POST violation reports.

A production environment can simultaneously serve **a stable enforced policy** and **a stricter new report-only policy** to measure compatibility before tightening enforcement. Using a new report-only policy **does not mean** existing enforced policies stop taking effect.

## 8. Automated testing of headers, nonces, and report-only mode

The exercise below uses a **real HTTP server** on a random port, via `@SpringBootTest`, to test both the Servlet filter registered via `FilterRegistrationBean` and the HTML rendered by Thymeleaf. It needs no extra MockMvc configuration.

**src/test/java/example/csp/CspDemoApplicationTests.java**:

~~~java
package example.csp;

import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CspDemoApplicationTests {

    private static final Pattern NONCE =
            Pattern.compile("'nonce-([A-Za-z0-9+/=]+)'");

    @Autowired
    TestRestTemplate client;

    @Test
    void nonceInHeaderMatchesHtmlAndChangesForNextResponse() {
        ResponseEntity<String> first =
                client.getForEntity("/demo", String.class);
        ResponseEntity<String> second =
                client.getForEntity("/demo", String.class);

        assertThat(first.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(second.getStatusCode()).isEqualTo(HttpStatus.OK);

        String firstPolicy =
                first.getHeaders().getFirst("Content-Security-Policy");
        String secondPolicy =
                second.getHeaders().getFirst("Content-Security-Policy");

        assertThat(firstPolicy).contains("script-src");
        assertThat(firstPolicy).contains("object-src 'none'");
        assertThat(first.getHeaders().getFirst(
                "Content-Security-Policy-Report-Only")).isNull();

        String firstNonce = nonceFrom(firstPolicy);
        String secondNonce = nonceFrom(secondPolicy);

        assertThat(first.getBody())
                .contains("nonce=\"" + firstNonce + "\"");
        assertThat(second.getBody())
                .contains("nonce=\"" + secondNonce + "\"");
        assertThat(firstNonce).isNotEqualTo(secondNonce);
    }

    private static String nonceFrom(String policy) {
        Matcher matcher = NONCE.matcher(policy);
        assertThat(matcher.find()).isTrue();
        return matcher.group(1);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The test verifies that **the HTTP header and actual HTML share the matching nonce** in the same response, and confirms two consecutive requests produce different nonces. The probability of two 128-bit random nonces colliding by chance is negligible, making the test suitable for verifying real behavior.

To specifically test report-only mode, you can add a second test in the same package, **src/test/java/example/csp/CspReportOnlyTests.java**:

~~~java
package example.csp;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "demo.csp.report-only=true"
)
class CspReportOnlyTests {

    @Autowired
    TestRestTemplate client;

    @Test
    void usesReportOnlyHeader() {
        ResponseEntity<String> response =
                client.getForEntity("/demo", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getHeaders().getFirst(
                "Content-Security-Policy-Report-Only"))
                .contains("script-src");
        assertThat(response.getHeaders().getFirst(
                "Content-Security-Policy")).isNull();
    }
}
~~~

HTTP tests verify headers in both modes. **The browser is the component that enforces CSP**, so to verify script blocking or violation reporting, you must still test with a real browser and DevTools; checking an endpoint's 200 status does not prove the CSP policy is properly enforced.

## 9. How do Enforce and Report-Only differ?

The two response header names serve different purposes:

| Header | Browser enforcement | Violation collection | When to use |
| --- | --- | --- | --- |
| `Content-Security-Policy` | **Blocks** actions violating supported directives. | Can report if reporting is configured. | Primary policy after legitimate sources are verified. |
| `Content-Security-Policy-Report-Only` | **Does not block** solely due to this Report-Only policy. | Can log to console/report when a receiver exists. | Observe impact of a new policy before turning on enforcement. |

Example policy under evaluation:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'nonce-ABC'; object-src 'none'; report-uri /csp-report
~~~

If the page contains an unnonced inline script, Report-Only can emit a report, yet the script still runs if **no other enforced policy blocks it**. Do not assume "Report-Only blocks but only shows a warning"; it **does not enforce its own policy**.

Both headers can be sent simultaneously, for example:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'nonce-ABC'; object-src 'none'; report-uri /csp-report
~~~

In this case, the first enforced policy still blocks actions it forbids; the second report-only policy observes its own violations. For nonce testing, do not use a static `ABC` outside illustrative snippets; issue a secure nonce per response. And if the enforced policy also restricts scripts, Report-Only has no power to relax that restriction.

**Phased rollout of CSP to production:**

1. Inventory resources: HTML/templates, inline scripts/styles, CDNs, images, fonts, WebSockets, APIs, iframes, analytics.
2. Draft a minimal-source candidate policy. Never set `script-src *` or `'unsafe-inline'` just to silence warnings.
3. Run the policy in **Report-Only**, inspect DevTools and actual reports across functional flows, browsers, and auth states.
4. Remove untrusted inline scripts, move scripts to external files or issue proper nonces/hashes; add sources only with evidence of application need and source trustworthiness.
5. Promote the stabilized policy to **enforce**; keep a new Report-Only policy if testing stricter constraints.
6. Monitor violations post-deployment and update when features or trusted domains change.

## 10. Violation reporting: report-uri, report-to, and received data

For browsers to send reports, CSP can use `report-uri` (older mechanism, still useful for compatibility) or integrate with the Reporting API via `report-to` paired with an endpoint header such as `Reporting-Endpoints`. **Support varies across browsers**; do not rely exclusively on one mechanism without testing target applications.

Example using `report-uri`:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; report-uri /csp-report
~~~

A browser may POST to `/csp-report` with `Content-Type: application/csp-report` and a body resembling:

~~~json
{
  "csp-report": {
    "document-uri": "https://app.example.com/demo",
    "effective-directive": "script-src-elem",
    "blocked-uri": "inline",
    "disposition": "report",
    "original-policy": "default-src 'self'; script-src 'self'; report-uri /csp-report"
  }
}
~~~

With the modern Reporting API, payloads typically have a different report structure, potentially an array containing fields like `type`, `url`, `body.effectiveDirective`, `body.blockedURL`; parse according to `Content-Type` and the browser-supported specification. Never assume every report shares the same JSON shape.

A modern reporting setup may require:

~~~http
Reporting-Endpoints: csp-endpoint="https://app.example.com/csp-report"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; report-to csp-endpoint
~~~

Some deployments combine `report-to` and `report-uri` to support older browsers. When both are declared, browsers supporting `report-to` may prefer it. Re-verify with target browsers because reporting has notable compatibility differences.

**Reports are not completely trustworthy data**: senders can spoof POSTs, payloads can contain URLs or sensitive info, traffic can be noisy, and delivery of all violations is not guaranteed. For report-receiving endpoints:

- Limit body size, rate, and request volume; protect against spam/DoS.
- Never treat report payloads as proof of user authentication or a trusted source.
- Strip or minimize URLs, queries, referrers, and sensitive content per privacy policy.
- Store/group by `effectiveDirective`, `blocked-uri`, `document-uri`, `disposition`, browser, or version (after privacy scrubbing).
- Carefully vet before adding an origin to an allowlist; a blocked third-party script or feature is not automatically trustworthy.

In the section 7 demo, `/csp-report` deliberately returns 204 and discards the payload to avoid turning the lab into a data collector. If telemetry is needed, build a dedicated collection endpoint with proper format validation and operational safeguards.

## 11. Common mistakes when applying CSP in Servlet

**Mistake 1 — Configuring CSP alone and thinking Spring Security stops all XSS.** CSP is a browser-side execution restriction layer. You still need output encoding, validation of values inserted into HTML/JS/URLs, and safe templates. An overly broad CSP policy can become nearly ineffective.

**Mistake 2 — Legitimate scripts blocked by `script-src 'self'`.** Inline scripts without a nonce/hash are blocked even if the HTML came from the same origin. `'self'` permits same-origin resource URLs; **it does not automatically permit all inline scripts**. Move scripts to external files or attach random nonces properly.

**Mistake 3 — Generating the nonce once at app startup.** A static nonce defeats the purpose of blocking injected inline scripts. Generate a nonce **per response** via `SecureRandom` and use that exact value in both the header and the response template.

**Mistake 4 — Nonce in header and HTML do not match.** If the controller generates a different nonce or a proxy overwrites the header, the browser blocks the script. Inspect response headers and the `nonce` attribute in the HTML response. In modern browsers, `nonce` attributes hide their value when read via certain DOM APIs; inspect raw responses or `.nonce` on the element when debugging.

**Mistake 5 — Multiple conflicting CSP headers.** If a gateway adds `script-src 'none'` while the app allows nonced scripts, enforced policies apply simultaneously; the app's header cannot relax restrictions imposed by the gateway. Identify every header-emitting layer and unify policies.

**Mistake 6 — Using `default-src 'self'` and thinking everything is protected.** `frame-ancestors`, `form-action`, and `base-uri` require separate consideration. Add targeted directives instead of wrongly relying on fallbacks.

**Mistake 7 — Seeing violations in Report-Only and thinking the browser blocked them.** Reporting and enforcement are separate modes. Check the header name and `disposition` in reports; only an enforced policy blocks on its own behalf.

**Mistake 8 — CSP allows `connect-src` yet `fetch` still fails CORS.** CSP is only one condition. Cross-origin APIs must still handle CORS and may require authentication/authorization. Conversely, an API permitting CORS is not automatically allowed by the page's CSP.

**Mistake 9 — Allowing `'unsafe-inline'`, all `https:`, or wildcards just to make the page work.** That can overly weaken the policy. Instead identify the violated directive and actual source, and replace with external scripts, nonces/hashes, or specific origins.

**Mistake 10 — Testing only one URL.** SSR documents, error pages, login routes, server-rendered views, JavaScript bundles, dynamic imports, WebSockets, fonts, and iframes may need tailored policies. Place policies on the right HTML responses and test real functional paths.

**Mistake 11 — CDN caching HTML containing a nonce.** If HTML with the same nonce is served from a public cache, the "fresh nonce per response" property is broken from the user's perspective. Verify cache/CDN, templates, edge responses, and synchronized caching of response headers and body.

**Mistake 12 — Trusting violation reports 100%.** Reports have no delivery guarantee and may be missing, duplicated, spoofed, or contain sensitive data. Combine with DevTools, functional tests, and safe server telemetry.

## 12. Knowledge check exercises

**Exercise 1.** Does the policy `default-src 'self'; script-src 'self'` allow an inline script `<script>alert(1)</script>`? **Not by default**, because `'self'` does not grant permission to inline scripts. You can move it to a same-origin file or issue a valid nonce/hash.

**Exercise 2.** Does `img-src https://img.example.com` allow `fetch("https://img.example.com/api")`? **You cannot infer that.** `fetch` belongs to `connect-src`, which has its own fallback if omitted. Allowing an image source does not mean allowing JS connections.

**Exercise 3.** Page A needs to be embedded inside an iframe on portal B. Should you check `frame-src` or `frame-ancestors` on A's response? **`frame-ancestors`** decides who may embed A; `frame-src` on page B governs where B may load iframes from.

**Exercise 4.** Two GET requests return HTML with the same nonce due to a fixed string in `policyDirectives`. Does this satisfy the nonce principle? **No.** A nonce must be generated fresh from a cryptographically random source for each non-cached/non-replayed response.

**Exercise 5.** A page executes an unnonced script when only `Content-Security-Policy-Report-Only: script-src 'nonce-ABC'` is present. Is this a browser bug? **No.** The policy is report-only and does not block scripts itself.

**Exercise 6.** A response has two enforced CSPs: one header allows scripts from `'self'` and another has `script-src 'none'`. Does a same-origin script run? **No**, because **all** enforced policies must be satisfied.

**Exercise 7.** The browser reports CSP refused a `fetch` to an API domain, while the server has CORS enabled. What do you inspect? Inspect `connect-src` in the document's policy first, then verify the API's CORS, credentials, and authentication as independent mechanisms.

**Exercise 8.** The report endpoint receives thousands of `application/csp-report` POSTs from unauthenticated clients. Should all contents be trusted? **No.** CSP reports can be forged; apply rate limiting, data minimization, and validation.

## 13. Summary for implementation

- **CSP is a response header enforced by browsers per document**; Spring Security Servlet must be configured with an appropriate policy, as no single default CSP fits every app.
- **Directives govern resource groups**: `script-src`, `style-src`, `img-src`, `connect-src`, `font-src`, `frame-ancestors`, `form-action`, `base-uri`. Do not confuse `frame-src` with `frame-ancestors` or assume every directive falls back to `default-src`.
- **Nonces must be sufficiently random and generated fresh per response**, appearing consistently in the CSP header and the `nonce` attribute of trusted inline scripts/styles. For HTML needing no inline scripts, policies using external files can be simpler.
- **Enforce** uses `Content-Security-Policy` to block violations; **Report-Only** uses `Content-Security-Policy-Report-Only` to observe before enforcing. Both can be used concurrently for different goals.
- **CSP, CORS, CSRF, authentication, and authorization do not replace one another.** CSP strengthens defense against untrusted content/scripts, while the server remains responsible for protecting data and access rights.
