# Safe Data Escaping, URL Links, and Forms in Spring Boot Server Interfaces

## 1. Objectives and Scope

Server-rendered UIs commonly use **Spring MVC + Thymeleaf** to transform data from controllers, databases, and users into HTML. If untrusted data is placed improperly into HTML, URLs, JavaScript, or forms, the browser can interpret data as code or perform unintended actions. This lesson covers safe rendering, link construction, and form handling in the **Spring Boot web runtime**, focusing on Thymeleaf 3.x, Spring MVC, and Spring Security.

After completing this lesson, you should be able to:

1. Distinguish plain data from HTML/JavaScript code and choose **output-context-appropriate escaping**.
2. Use `th:text`, `th:value`, `th:field`, `th:href="@{...}"`, and `th:action="@{...}"` instead of manual HTML and URL string concatenation.
3. Explain why **HTML escaping alone is not enough to validate a URL**, and why external links must be checked for scheme, host, and destination.
4. Design POST forms with **server-side validation**, **CSRF protection**, authorization, and proper feedback flows.
5. Write tests verifying that strings containing HTML tags render as text, URLs are encoded, invalid inputs are rejected, and POST requests without CSRF tokens are denied.

The core principle: **data must remain data**. At every output boundary sent to the browser, know whether the browser will parse it as **HTML text**, an **HTML attribute**, a **URL**, **JavaScript**, **CSS**, or another context. No single escaping function is safe for every context.

## 2. Threat Model: Where Can Untrusted Data Enter the UI?

Untrusted data sources go beyond `@RequestParam`. They also include: database fields, user comments, external API responses, imported file contents, queue payloads, callback URLs, upload metadata, validation errors, or previously stored data (*stored XSS*).

For example, suppose a user enters:

```text
<img src=x onerror=alert(1)>
```

If treated as **text**, the page should render the exact string as plain text. If concatenated directly into HTML without proper encoding, the browser can create an `img` tag and execute the event handler. XSS also occurs in attributes, URL schemes, JavaScript code, CSS, and client-side DOM APIs.

Another example:

```text
javascript:alert(1)
```

This string may already be **HTML-attribute-escaped** safely with respect to quotes yet remain a dangerous URL if assigned to `href`. That means **syntactic escaping** and **semantic validation / destination allowlisting** are two distinct steps.

| Output Context | Preferred Handling | Common Mistake |
| --- | --- | --- |
| Text content of an HTML element | `th:text` or `[[...]]` in HTML templates | `th:utext` or `[(...)]` with user data |
| Standard HTML attributes | `th:value`, `th:title`, `th:attr` with controlled values | Building entire markup strings via concatenation |
| App-generated URL paths/queries | `th:href="@{/path(...)}"`, `th:src="@{...}"` | Concatenating `"?q=" + query` or inserting full client-supplied URLs |
| JavaScript literals | Keep data out of scripts; if needed, `th:inline="javascript"` and `[[...]]` | Concatenating into JS strings or using `[(...)]` |
| CSS | Prefer fixed CSS classes from an allowlist | Injecting arbitrary CSS declarations or `url(...)` from users |
| Form body | `th:field` + server-side Bean Validation + CSRF | Relying on browser `required`/`maxlength` or disabling CSRF |

**Escaping does not replace validation and authorization.** Even when output is safely displayed, the application still needs to validate business rules, stop one account from modifying another user's resources, and protect state-changing requests.

## 3. Thymeleaf: `th:text` Instead of `th:utext`

In Thymeleaf templates, the simplest way to output untrusted text is `th:text`:

```html
<p th:text="${userComment}">Sample content</p>
```

If `userComment` is `<strong>Hello</strong>`, the generated HTML contains escaped characters, such as:

```html
<p>&lt;strong&gt;Hello&lt;/strong&gt;</p>
```

The browser displays the literal text `<strong>Hello</strong>` rather than rendering bold markup.

Escaped inlining `[[${userComment}]]` is semantically equivalent to `th:text` in HTML template text context:

```html
<p>Comment: [[${userComment}]]</p>
```

**Do not pass untrusted content to `th:utext` or `[(...)]`**, as both emit unescaped HTML:

```html
<!-- ANTI-PATTERN: do not use for user-entered comments -->
<div th:utext="${userComment}"></div>
<div>[(${userComment})]</div>
```

If business requirements genuinely support user-authored rich text (such as text with `<b>` and `<i>`), use an **allowlist-based HTML sanitizer** to retain only permitted tags/attributes and strip scripts, event handlers, and dangerous URL schemes. Only then render the sanitized output through a dedicated mechanism, backed by security tests and a Content Security Policy. Never pass raw HTML from the database into `th:utext`, and never build an HTML sanitizer with regular expressions.

**Avoid double escaping:** if the server calls a function that converts `<` to `&lt;` before passing the value to `th:text`, the `&` can be escaped again into `&amp;`, showing literal entity strings to users. Keep raw text in the model and let the template engine escape at the output boundary.

## 4. Attribute Encoding and Dangerous Contexts

Processors like `th:value`, `th:title`, and `th:alt` insert data into attributes formatted per template rules. For example:

```html
<input type="text" th:value="${displayName}">
<img th:src="@{/images/logo.svg}" th:alt="${imageDescription}">
```

When `displayName` contains quotes or special characters, Thymeleaf encodes the attribute properly. Never construct HTML strings in Java:

```java
// ANTI-PATTERN: building HTML directly from input, do not use.
String html = "<input value=\"" + userValue + "\">";
```

However, quoting and escaping an attribute **does not make every value semantically safe**:

- `th:href="${externalUrl}"` can accept `javascript:...` or phishing URLs if the value comes freely from the client.
- `th:onclick`, `th:onload`, and JavaScript event-handler attributes are **code execution contexts**; never put arbitrary user content in them.
- `th:style` and dynamic CSS can cause unintended behavior; prefer selecting from a fixed list of CSS classes.
- `th:attr` can assign dynamic attributes, so letting user input control attribute names creates an unsafe surface; keep attribute names fixed on the server.
- Encoded `data-*` attributes can pass data to JavaScript **via DOM APIs**, then assigned with `textContent`. Avoid `innerHTML` with unsanitized data.

If data must be embedded into inline JavaScript, use the proper Thymeleaf mode:

```html
<script th:inline="javascript">
  const displayName = [[${displayName}]];
  console.log(displayName);
</script>
```

Here `[[...]]` in **JavaScript inlining mode** produces a JavaScript-encoded literal including quotes. Do not wrap extra quotes around the expression, do not use `[(...)]`, and do not build script blocks from user input. In stricter apps, prefer separate script files with an appropriate **CSP**, passing data via DOM/data attributes or JSON endpoints; handle every context in alignment with your CSP and template rendering mode.

## 5. Safe URL Links: Construction, Encoding, and Destination Limits

### 5.1. Never Concatenate Query Strings Manually

Suppose a search receives `q = a&b with spaces`. The following pattern breaks easily:

```html
<!-- ANTI-PATTERN: confuses & inside data with & query parameter separator -->
<a th:href="|/search?q=${q}|">Search</a>
```

The safer approach is a **link expression** `@{...}`:

```html
<a th:href="@{/search(q=${q})}">Search</a>
```

Thymeleaf constructs the URL relative to the context path and **encodes query parameters** properly. The value `a&b` becomes a single `q` parameter containing an encoded ampersand (typically `q=a%26b`) instead of splitting into extra parameters. When multiple query parameters exist, parameter-separating `&` characters in HTML source are also HTML-attribute-escaped, which is a separate step from percent-encoding parameter data.

Example with two parameters:

```html
<a th:href="@{/search(q=${q},page=${page})}">Next page</a>
```

`page` still needs server-side validation (positive integer, upper bound); URL encoding does not validate business rules.

### 5.2. Encoding Path Variables Instead of Concatenating Full URLs

```html
<a th:href="@{/products/{id}(id=${productId})}">Details</a>
```

`productId` is substituted by Thymeleaf into the placeholder. It should be a **validated ID or slug** (such as a numeric ID or allowlisted slug), not an arbitrary client-supplied path. URL encoding protects syntax and parameter transport; it **does not replace object-level authorization for the ID** and does not automatically block path segments like `..` or separators from triggering unexpected routing in proxies or containers.

If a link must navigate to an external URL, never pass an unvalidated `next` or `returnUrl` query parameter directly:

```html
<!-- ANTI-PATTERN: unvalidated full URL could use a malicious scheme -->
<a th:href="${returnUrl}">Go back</a>
```

Appropriate policy: prefer server-chosen relative routes, or parse the URL and **allowlist the `https` scheme, target hostname/port, and intended purpose**. Never use `startsWith("https://trusted.com")` to validate a host, because `https://trusted.com.attacker.example` bypasses string prefix checks. For post-form or post-login redirects, allow only **internal relative destinations or registered redirect URIs** to prevent *open redirects* and phishing. `Location` headers must likewise be constructed under strict validation.

For links opening in a new tab:

```html
<a href="https://example.org/docs"
   target="_blank"
   rel="noopener noreferrer">External Documentation</a>
```

`rel="noopener noreferrer"` mitigates certain opener-window and referrer risks; it **does not verify the trustworthiness of the destination**.

### 5.3. Browser URLs, HTTP Client URLs, and File Paths Are Different Things

Do not confuse URL output encoding with:

- **SSRF:** the server requests a user-supplied URL, potentially reaching internal IPs or metadata endpoints. Require destination allowlists, redirect/DNS checks, and network policies.
- **Path traversal:** the user controls a file or static resource path. Enforce root-containment checks and authorization; URL encoding does not protect the filesystem.
- **IDOR/BOLA:** the user alters an ID in the URL to access another user's resource. Enforce object-level authorization checks.
- **Open redirect:** the server sends users to an unintended external URL. Restrict redirect targets strictly.

## 6. Safe Forms: From HTML to Server-Side Validation

A well-designed form combines **browser input UX** with **authoritative server-side checks**. HTML `required`, `maxlength`, and `type=email` give users early feedback, yet they are trivially bypassed via DevTools or `curl` and therefore are never a trust boundary.

In Spring MVC:

1. `@GetMapping` creates a form object and adds it to the `Model`.
2. Thymeleaf uses `th:object` and `th:field` to bind form fields to `input`/`textarea` elements.
3. `@PostMapping` binds the form via `@ModelAttribute` and runs `@Valid` with Jakarta Bean Validation.
4. `BindingResult` must sit **immediately after the validated parameter** so the controller catches errors and re-renders the form rather than treating invalid input as success.
5. Error messages are rendered via `th:errors`/`th:text`, never concatenated HTML.
6. After a valid submission, use **Post/Redirect/Get** (PRG) so refreshing the page does not easily resubmit the POST; PRG **does not make** the POST operation idempotent on its own.

Binding example:

```html
<form th:action="@{/feedback}" th:object="${feedbackForm}" method="post">
  <label for="name">Name</label>
  <input id="name" th:field="*{name}" type="text" required maxlength="80">

  <p th:if="${#fields.hasErrors('name')}"
     th:errors="*{name}">Name error</p>

  <button type="submit">Submit</button>
</form>
```

`th:field` repopulates submitted values on validation failure and applies appropriate output encoding. **Never trust hidden fields:** prices, `userId`, `role`, `tenantId`, `status`, or permissions submitted in a form can all be tampered with by clients. Enforce authorization on the server and bind only fields users are allowed to change. Prevent **mass assignment / over-posting** by using dedicated form DTOs instead of binding entities with sensitive fields directly.

### CSRF: A Separate Problem from XSS

**CSRF (Cross-Site Request Forgery)** occurs when another site tricks a logged-in user's browser into sending an unintended state-changing request. HTML escaping protects outputs against XSS; it **provides no CSRF protection**. For cookie/session-authenticated apps, Spring Security protects unsafe HTTP methods like POST/PUT/PATCH/DELETE with tokens by default (unless disabled).

With **Spring MVC + Thymeleaf + Spring Security**, `th:action` on a POST form integrates with Spring's `RequestDataValueProcessor`: when default CSRF protection is active, Thymeleaf **automatically injects a hidden input carrying the CSRF token** into the rendered HTML. The token is not a static string; never hardcode a sample token.

Example of rendered HTML (token shown is illustrative):

```html
<form method="post" action="/feedback">
  <input type="hidden" name="_csrf" value="token-generated-for-this-request">
  <!-- form fields -->
</form>
```

When forms use another template engine or send AJAX requests, pass the CSRF token per Spring Security's configuration (such as a form field or HTTP header). In Spring Security 6+, account for **deferred tokens / XOR masking** and handle tokens per your version's documentation; never read a masked token and compare or transform it manually in application code.

**Never disable CSRF globally just to silence a 403 error on a form.** First check whether the template uses `th:action`, verify the `SecurityFilterChain`, cookies/sessions, and whether the token is actually submitted. Use `SameSite` cookies and `Origin`/`Referer` checks as defense in depth where appropriate, without treating them as a full replacement for CSRF tokens. For REST APIs authenticated exclusively via manually sent bearer tokens, the threat model differs; evaluate your actual authentication mechanism before deciding CSRF policy.

## 7. Runnable Sample Project: Spring Boot 3.x + Thymeleaf + Validation + Security

This hands-on project uses **Java 17+**, **Spring Boot 3.x**, Spring MVC, Thymeleaf, Jakarta Validation, and Spring Security. It demonstrates all three safeguards: **text escaping**, **URL query encoding**, and **validated/CSRF-protected POST forms**.

Generate the project via Spring Initializr with dependencies:

- `spring-boot-starter-web`
- `spring-boot-starter-thymeleaf`
- `spring-boot-starter-validation`
- `spring-boot-starter-security`
- `spring-boot-starter-test` (`test` scope)
- `org.springframework.security:spring-security-test` (`test` scope, to call `csrf()` in MockMvc)

If using Maven with the Spring Boot parent/BOM, add inside `pom.xml` (`<dependencies>`):

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

### 7.1. Startup Class

**`src/main/java/com/example/demo/SafeUiApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeUiApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeUiApplication.class, args);
    }
}
```

### 7.2. Security Configuration

**`src/main/java/com/example/demo/WebSecurityConfig.java`**

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/feedback", "/feedback/**").permitAll()
            .anyRequest().denyAll()
        );
        // Keep Spring Security's default CSRF protection enabled.
        return http.build();
    }
}
```

This is a **public demo application**; `permitAll` allows visiting the feedback page and submitting the form, while **CSRF is still enforced on POST**. For account, order, or private document forms, require authentication and per-user/object authorization instead of `permitAll`.

### 7.3. Controller with a Dedicated Form DTO

**`src/main/java/com/example/demo/FeedbackController.java`**

```java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class FeedbackController {

    private static final String SAFE_SLUG = "huong-dan";

    @GetMapping("/feedback")
    public String feedbackPage(
            @RequestParam(name = "q", defaultValue = "") String q,
            Model model) {
        return renderForm(q, model);
    }

    @GetMapping("/feedback/{slug}")
    public String feedbackPageForSlug(
            @PathVariable String slug,
            @RequestParam(name = "q", defaultValue = "") String q,
            Model model) {
        if (!SAFE_SLUG.equals(slug)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return renderForm(q, model);
    }

    private String renderForm(String q, Model model) {
        if (!model.containsAttribute("feedbackForm")) {
            model.addAttribute("feedbackForm", new FeedbackForm());
        }
        // q may contain HTML/URL special characters: let the template escape it.
        model.addAttribute("query", q);
        model.addAttribute("safeSlug", SAFE_SLUG);
        return "feedback";
    }

    @PostMapping("/feedback")
    public String submit(
            @Valid @ModelAttribute("feedbackForm") FeedbackForm form,
            BindingResult errors,
            Model model,
            RedirectAttributes redirect) {
        if (errors.hasErrors()) {
            model.addAttribute("query", "");
            model.addAttribute("safeSlug", SAFE_SLUG);
            return "feedback";
        }

        // Only illustrates valid submission flow; does not persist to a database.
        // User input passes through flash attributes and is rendered escaped.
        redirect.addFlashAttribute("submittedName", form.getName());
        return "redirect:/feedback";
    }

    public static class FeedbackForm {
        @NotBlank(message = "Name must not be blank")
        @Size(max = 80, message = "Name must be at most 80 characters")
        private String name;

        @NotBlank(message = "Message must not be blank")
        @Size(max = 500, message = "Message must be at most 500 characters")
        private String message;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getMessage() {
            return message;
        }

        public void setMessage(String message) {
            this.message = message;
        }
    }
}
```

Key takeaways:

- `@Controller` returns the template name `feedback`, **unlike** `@RestController`, which serializes return values into the response body.
- `q` goes straight into the model **without manual escaping in Java**; Thymeleaf's output boundary handles encoding.
- `safeSlug` is chosen by the server in this example. URL parameters must never substitute for route authorization.
- `FeedbackForm` exposes only the two fields users are permitted to enter. Never bind an entity containing `role`, `admin`, `price`, or `ownerId`.
- `BindingResult` sits immediately after `@Valid @ModelAttribute`; on error, the template re-renders with validation messages.
- Valid POSTs use **PRG** and flash attributes. In real applications, persist or dispatch business work first before redirecting, and consider idempotency keys for side-effecting actions.

### 7.4. Thymeleaf Template

**`src/main/resources/templates/feedback.html`**

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Safe Feedback</title>
</head>
<body>
  <h1>Feedback Form</h1>

  <h2>Escaped Data</h2>
  <p id="echo" th:text="${query}">User text</p>
  <input id="query-attribute" type="text" readonly
         th:value="${query}">

  <h2>Links Generated by Thymeleaf</h2>
  <a id="query-link"
     th:href="@{/feedback(q=${query})}">Reopen with query</a>
  <a id="path-link"
     th:href="@{/feedback/{slug}(slug=${safeSlug},q=${query})}">
    Guide page
  </a>

  <p id="thanks"
     th:if="${submittedName != null}"
     th:text="|Received feedback from ${submittedName}.|">
    Thank you!
  </p>

  <h2>Send Feedback</h2>
  <form id="feedback-form" method="post"
        th:action="@{/feedback}"
        th:object="${feedbackForm}">
    <div>
      <label for="name">Name</label>
      <input id="name" type="text" th:field="*{name}"
             required maxlength="80" autocomplete="name">
      <small th:if="${#fields.hasErrors('name')}"
             th:errors="*{name}">Name error</small>
    </div>
    <div>
      <label for="message">Message</label>
      <textarea id="message" th:field="*{message}"
                required maxlength="500"></textarea>
      <small th:if="${#fields.hasErrors('message')}"
             th:errors="*{message}">Message error</small>
    </div>
    <button type="submit">Submit</button>
  </form>
</body>
</html>
```

Notes:

- `th:text="${query}"` inserts `query` into **HTML text** with escaping.
- `th:value="${query}"` inserts `query` into an **attribute value** with proper encoding.
- `th:href="@{/feedback(q=${query})}"` and the `{slug}` placeholder construct context-aware links and encode values.
- `th:field="*{name}"` / `*{message}` bind form inputs, preserving input values and displaying errors when invalid.
- `th:action="@{/feedback}"` on the POST form enables Spring Security + Thymeleaf integration to add the hidden CSRF field automatically when active; **never hardcode a token** in the template.
- `submittedName` came from a prior input, yet `th:text` still escapes it on display. **PRG does not make user input trustworthy.**

This example intentionally omits JavaScript, CSS, and user-supplied rich HTML. When rich text is required, design a sanitizer and permission model separately.

## 8. Running and Observing Output

From the project directory containing the Maven Wrapper, run:

```bash
java -version
./mvnw spring-boot:run
```

On Windows use `mvnw.cmd spring-boot:run`. There is no **fixed stdout** for Spring Boot because versions, profiles, ports, and log formats vary; check that the server listens on `http://localhost:8080` if `server.port` is unchanged.

Visit:

```text
http://localhost:8080/feedback
http://localhost:8080/feedback?q=a%26b
http://localhost:8080/feedback/huong-dan?q=a%26b
```

Expected results: the page displays the form; when `q` is `a&b`, the page displays that exact text; the link built by `th:href` keeps the full `a&b` inside a **single** query parameter.

Send a string containing HTML-like markup:

```bash
curl -G -i --data-urlencode "q=<img src=x onerror=alert(1)>" \
  http://localhost:8080/feedback
```

Bash/Unix supports `\` line continuations as shown; in PowerShell put the command on one line or use PowerShell's line continuation syntax. In the HTML response, the `<img ...>` supplied by the query appears as escaped text (such as `&lt;img ...&gt;`); it does not become an executable HTML element. Inspecting the DOM in DevTools shows `#echo` contains only text and no `img` element created from input.

Open the form in a browser and submit a valid name and message. With Spring Security + Thymeleaf integration, the form renders with a hidden CSRF token; a valid POST returns a redirect (typically HTTP **302**) to `/feedback`, and the name is rendered back with `th:text`. Since the demo has no database or persistence, this verifies validation, redirecting, and escaping.

If you send a direct POST **without a CSRF token**:

```bash
curl -i -X POST http://localhost:8080/feedback \
  -d "name=An" -d "message=Hello"
```

With Spring Security CSRF enabled, this request is rejected (typically **HTTP 403**), regardless of whether the data passes Bean Validation. This is the expected behavior of the CSRF protection layer. To simulate a valid POST via `curl`, you must obtain the token and matching session/cookie from the server; never invent a dummy token value.

## 9. Automated Testing with MockMvc

Use `spring-boot-starter-test` and `spring-security-test` in `test` scope. Write tests confirming that **dangerous values do not become HTML**, URL queries are encoded, CSRF is enforced, and validation executes.

**`src/test/java/com/example/demo/SafeUiApplicationTest.java`**

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeUiApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void escapesUntrustedText() throws Exception {
        String attack = "<img src=x onerror=alert(1)>";

        mvc.perform(get("/feedback").param("q", attack))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("&lt;img src=x onerror=alert(1)&gt;")
            ))
            .andExpect(content().string(
                not(containsString(attack))
            ));
    }

    @Test
    void encodesQueryParameterInsideLink() throws Exception {
        mvc.perform(get("/feedback").param("q", "a&b"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("q=a%26b")
            ));
    }

    @Test
    void rejectsPostWithoutCsrfToken() throws Exception {
        mvc.perform(post("/feedback")
                .param("name", "An")
                .param("message", "Hello"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validatesInputOnServer() throws Exception {
        mvc.perform(post("/feedback")
                .with(csrf())
                .param("name", "")
                .param("message", "Valid message"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("Name must not be blank")
            ));
    }

    @Test
    void validFormPostRedirects() throws Exception {
        mvc.perform(post("/feedback")
                .with(csrf())
                .param("name", "An")
                .param("message", "Hello"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/feedback"));
    }
}
```

Run:

```bash
./mvnw test
```

With the exact files and dependencies described above, **five tests are expected to pass**. This is the designed outcome for learners to run themselves, not a claim that tests were executed in an existing repository. If tests fail, check the Spring Boot 3.x version, `spring-security-test` scope, validation starter, template name, and that `th:action` on the form is processed by Thymeleaf.

Additional tests to add in production deployments: quotes inside attributes, Unicode, queries with `&`/`?`/`#`, URL path encoding, oversized form values, Bean Validation edge cases, safe redirects, malicious link schemes, user/object authorization, file uploads, duplicate form submissions, session cookies, and behavior when CSRF tokens expire.

## 10. How Validation, Sanitization, Escaping, and CSRF Differ

| Safeguard | Purpose | Example | Does Not Replace |
| --- | --- | --- | --- |
| **Validation** | Ensures data meets input rules | `@NotBlank`, `@Size`, type/format/allowlist | Escaping, authorization checks |
| **Sanitization** | Strips/limits dangerous markup when HTML is explicitly allowed | Allowlist-based rich HTML filter | CSRF, authorization |
| **Output escaping/encoding** | Ensures the browser treats data as data in the current context | `th:text`, `th:value`, `@{...}` | Validation, URL destination checks |
| **Authentication/authorization** | Determines who can view or modify which data | Spring Security, owner/tenant checks | XSS/CSRF |
| **CSRF token** | Blocks forged state-changing requests via credentialed browsers | Hidden token in POST forms | XSS, access control |
| **CSP/security headers** | Reduces likelihood and impact of certain injections | `script-src`, blocking unauthorized inline scripts | Proper escaping, URL validation |

A **valid string** in terms of length and format can still contain `<script>`. An **HTML-escaped string** can still be a disallowed `javascript:` URL. A request **carrying a valid CSRF token** can still access another user's data if the backend lacks authorization.

### Form Submission and Transaction Safety

In real-world applications:

- Never modify important resources with **GET**. GET links can be followed by crawlers, browser previews, or prefetchers; state-changing operations require appropriate HTTP methods and CSRF protection when using cookie authentication.
- For POSTs creating payments or orders, CSRF + PRG **do not guarantee exactly-once processing**. Use idempotency keys, database transactions, and duplicate-submission protection.
- Use input DTOs and field allowlists; in services, enforce authentication, authorization, and server-derived tenant/owner checks to prevent mass assignment.
- Validation error messages can echo user input; render them as escaped text and keep secrets out of error messages and logs.
- Configure `Content-Type`, request size limits, field counts, multipart upload sizes, and rate limits appropriately; browser validation does not protect the backend.
- With cookie-based sessions, configure `HttpOnly`, `Secure`, and `SameSite` according to your architecture and HTTPS setup; they complement CSRF and XSS defenses.

## 11. Common Mistakes and Fixes

**Mistake 1 — Using `th:utext` just to keep line breaks or formatting.** If you only need line breaks, apply CSS `white-space: pre-wrap` on an element using `th:text`. When rich HTML is needed, use a well-defined sanitizer; never expose raw HTML to arbitrary user input.

**Mistake 2 — Escaping on the server, then escaping again in the template.** This can output `&amp;lt;` instead of `&lt;`. Keep plain text in the model and escape once at the output boundary.

**Mistake 3 — Treating URL encoding as authorization or scheme validation.** `th:href` encodes parameters, yet it does not check whether the user is allowed to view `/orders/123` and does not block redirects to untrusted domains. Add authorization and allowlists.

**Mistake 4 — Building links by string concatenation like `"/search?q=" + q`.** `&`, `#`, spaces, and Unicode can corrupt URLs or alter query structure; use parameterized URL expressions.

**Mistake 5 — Relying solely on HTML `required`.** Users can send POSTs via scripts, `curl`, or modified browser DOM. Enforce `@Valid`/Bean Validation and service-layer business rules.

**Mistake 6 — Misplacing `BindingResult`.** In an MVC controller, place it immediately after the corresponding `@Valid @ModelAttribute` parameter to capture validation errors. Otherwise Spring may throw an exception or return an error page instead of re-rendering the form.

**Mistake 7 — Disabling CSRF globally to fix a 403.** Inspect the Spring Security filter chain, `th:action`, hidden token, and session/cookies; exempt CSRF only on endpoints and architectures explicitly evaluated for it.

**Mistake 8 — Embedding user input into `onclick` or inline scripts.** HTML attribute escaping is not a safe way to construct JavaScript code. Use separate JS files, event listeners, and DOM `textContent`.

**Mistake 9 — Trusting hidden form inputs.** `role`, `userId`, and `totalPrice` in hidden fields can all be modified by clients; values governing permissions and payments must be resolved and verified on the server.

**Mistake 10 — Allowing arbitrary `returnUrl` links.** This enables open redirects, `javascript:` XSS schemes, or phishing. Restrict redirects to internal paths or registered target URIs, parsing and comparing URL components properly.

**Mistake 11 — Escaping HTML and then assigning to `innerHTML`.** Using a DOM sink that parses HTML can reintroduce risks if strings are decoded or transformed later. Prefer `textContent`, or apply intentional sanitization if HTML is truly needed.

**Mistake 12 — Using `|${name}|` arbitrarily inside `th:action` or URLs.** Literal substitution does not separate path/query components or percent-encode values. Use `@{...}` for links/actions and proper data binding for forms.

## 12. Server-Rendered UI Review Checklist

- [ ] Data from users, databases, or external APIs is rendered as text via `th:text`/`[[...]]`.
- [ ] No `th:utext`/`[(...)]` is used for data that has not passed a proper rich-HTML sanitizer.
- [ ] Inputs inside HTML attributes use appropriate Thymeleaf processors; no raw HTML string concatenation.
- [ ] No unvalidated user-supplied full URLs are assigned to `href`, `src`, redirects, or form actions.
- [ ] Link paths/queries use `@{...}` with explicit parameters; IDs are still validated and authorized.
- [ ] Scripts/CSS never interpolate untrusted data directly; use proper context escaping or avoid dynamic code.
- [ ] Forms use dedicated DTOs, `@Valid`, `BindingResult`, and escaped error messages.
- [ ] Cookie/session-authenticated POST/PUT/PATCH/DELETE endpoints are CSRF-protected; tested that POST without token returns 403.
- [ ] `role`, `owner`, `tenant`, `price`, and `status` never trust hidden or request fields; services verify from trusted sources.
- [ ] Tests cover reflected/stored XSS, URL encoding, invalid input, session/CSRF, authorization, and redirects.
- [ ] HTTPS, cookie/security headers, and CSP are configured appropriately for the threat model.
- [ ] Spring Boot, Thymeleaf, and Spring Security versions are maintained and patched.

## 13. Self-Check Questions

**Question 1.** How do `th:text="${comment}"` and `th:utext="${comment}"` differ?  
**Answer:** `th:text` escapes HTML text, whereas `th:utext` inserts unescaped content; never use `th:utext` for unsanitized user content.

**Question 2.** For query `q=a&b`, should you build the link with `th:href="|/search?q=${q}|"` or `th:href="@{/search(q=${q})}"`?  
**Answer:** Use `@{/search(q=${q})}` so Thymeleaf handles URL parameter encoding.

**Question 3.** Is `th:href="${externalUrl}"` safe merely because Thymeleaf escapes quotes?  
**Answer:** No. URLs still require scheme, destination, and permission validation; `javascript:` does not become safe from HTML escaping alone.

**Question 4.** Is HTML `required` sufficient for a form?  
**Answer:** No. Re-validate with `@Valid` and business rules on the server.

**Question 5.** With Spring Security enabled, what happens when a Thymeleaf POST form lacks a CSRF token?  
**Answer:** When CSRF protection is active, the request is typically rejected with HTTP 403; inspect `th:action` integration and token/cookie handling.

**Question 6.** Does `@Valid` prevent a user from submitting `isAdmin=true` into an entity if the controller binds the entire entity?  
**Answer:** No. Use a DTO containing only allowed fields and enforce authorization in the service.

**Question 7.** After a valid POST, does redirecting to a GET prevent duplicate orders?  
**Answer:** Not by itself. PRG reduces accidental resubmission on refresh; critical logic still needs idempotency and transactions.

## 14. Official Documentation

- Thymeleaf 3.1, *Using Thymeleaf*: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html
- Thymeleaf 3.1, *Thymeleaf + Spring*: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
- Spring Security, *CSRF Protection*: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Framework, *Spring MVC Validation*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework, *View Technologies*: https://docs.spring.io/spring-framework/reference/web/webmvc-view.html
- Spring Boot, *Servlet Web Applications*: https://docs.spring.io/spring-boot/reference/web/servlet.html
- OWASP, *Cross Site Scripting Prevention Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- OWASP, *Cross-Site Request Forgery Prevention Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP, *Unvalidated Redirects and Forwards Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

**Conclusion:** For Spring Boot server-rendered UIs, apply **context-appropriate escaping**, build links with `@{...}`, use DTOs and Bean Validation for forms, keep CSRF enabled where needed, restrict URL/redirect targets, and always enforce authorization on the server. Safe configuration must be verified with tests using both malicious inputs and valid requests, because a page that "looks right" can still hide XSS, open redirects, mass assignment, or CSRF vulnerabilities.