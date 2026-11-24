# Restricting Dynamic Content, HTML Escaping, and XSS Risks in Spring MVC View Rendering

## 1. Objectives and Context

Spring MVC frequently places data from a database, request parameters, or forms into a `Model`, then passes that model to Thymeleaf or JSP to render HTML. Data such as names, comment text, product descriptions, or user-entered URLs can contain characters with special meaning to the browser. **If untrusted content is rendered as executable HTML or JavaScript, the browser can execute it**: that is the root of Cross-Site Scripting (XSS) vulnerabilities.

After this lesson, you will be able to:

1. Distinguish **plain text data** from **HTML allowed to render**, and explain why data inside `Model` is not automatically safe.
2. Use Thymeleaf `th:text`, `th:value`, `th:href`, escaped inline expressions, and DOM `textContent` appropriately; recognize the risks of `th:utext`, unescaped inlining, and `innerHTML`.
3. Apply **context-aware output encoding** for HTML text, HTML attributes, URLs, JavaScript, and CSS; understand when encoding alone is insufficient and structural/allowlist checks are required.
4. Restrict dynamic content (length, format, visibility permissions, allowed URL lists), sanitize rich HTML when genuinely required, and configure CSP as an extra defense layer.
5. Build a **Spring Boot 3.x + Thymeleaf + Java 17+** example and test that payloads containing `<`, `>`, quotes, or HTML-like markup are displayed as text without becoming executable tags or attributes.

**Scope:** Spring Framework 6.x, Spring MVC on the Servlet stack, and server-rendered HTML pages. Many principles also apply to SPA frontends; however, Spring MVC does not automatically protect DOM updates performed by browser-side JavaScript.

## 2. Where Does XSS Arise in the View Rendering Flow?

A form accepts a display name or comment:

~~~http
GET /pages/preview?message=Hello HTTP/1.1
Host: localhost:8080
~~~

Data reaches the controller:

~~~java
@GetMapping("/preview")
public String preview(@RequestParam String message, Model model) {
    model.addAttribute("message", message);
    return "preview";
}
~~~

This is an **illustrative snippet inside a `@Controller`**, requiring annotation imports and a class declaration. `Model` holds the exact value sent by the client; `model.addAttribute(...)` **is not a sanitizer**.

Next, the view uses the `message` attribute. If the template lets the browser interpret that data as **HTML source**, tags and attributes can alter the DOM structure and trigger XSS. Example benign test string to observe the difference:

~~~text
<img src=x onerror=alert(1)>
~~~

The string above is only a **test payload**. When escaped and rendered as text, the browser displays the literal character sequence. When injected directly into the HTML parser, it creates an `img` tag with an event handler, creating a JavaScript execution risk.

Three points require control:

- **Untrusted data sources:** request parameters, forms, cookies, headers, user-generated database content, third-party feeds, Markdown/HTML from a CMS. Data already stored in the database can still trigger **stored XSS** when displayed again.
- **Injection points into the response:** Thymeleaf/JSP templates, `ResponseEntity<String>` returning hand-built HTML, inline JavaScript embedded in the page, `href` attributes, CSS, `iframe`, or post-load DOM updates.
- **Target parser context:** HTML text, HTML attribute, JavaScript code/string, URL, CSS, or DOM API. **Each context requires different rules**; no single "universal escape function" protects every sink.

**Reflected XSS** happens when request input is reflected unsafely into the response; **stored XSS** happens when persisted content is rendered unsafely; **DOM-based XSS** involves client-side JavaScript feeding data into DOM sinks capable of interpreting code or markup. These forms can combine.

## 3. How Does Escaping Differ from Sanitization and Validation?

| Operation | Problem Solved | Example |
| --- | --- | --- |
| **Output encoding / escaping** | Converts special characters into safe representations for the **exact output context** | In HTML text, `<` becomes `&lt;` |
| **Input validation** | Verifies data meets contract/business rules (length, structure, value set) | Name at most 200 characters |
| **HTML sanitization** | Strips or replaces dangerous markup while keeping a safe HTML subset | Allow only `<b>`, `<em>`, and safe links |
| **Authorization** | Confirms the viewer is permitted to receive the data | Exclude private emails from public models |
| **CSP / Trusted Types** | Restricts certain script execution and DOM injection paths | `Content-Security-Policy` blocks unauthorized inline scripts |

**Output must normally be escaped at the rendering point**, even after input passes validation. Validation cannot replace encoding: a valid product title might contain `<`, `&`, or quotes. Conversely, HTML escaping does not enforce length limits, check permissions, or turn a malicious URL into a trusted URL.

An example of escaped HTML text:

~~~html
<!-- Source in the response -->
<p>&lt;img src=x onerror=alert(1)&gt;</p>
~~~

The browser displays the exact string `<img src=x onerror=alert(1)>`; it **does not create an `img` child element** from that string. The browser decodes the entities into text inside the DOM, and text nodes are not re-parsed as HTML.

Do not escape when writing to the database and then escape a second time in the view if the storage contract expects raw text: that can produce `&amp;lt;` and render incorrectly. A sustainable approach is to **store canonical text**, validate against business rules, and encode **at each specific output sink**.

## 4. Thymeleaf: `th:text` Is Safe for HTML Text, `th:utext` Is a Dangerous Escape Hatch

### 4.1. `th:text`: Escapes HTML by Default

~~~html
<p id="comment" th:text="${comment}">Comment</p>
~~~

If `comment = "<b>Hello</b>"`, Thymeleaf renders:

~~~html
<p id="comment">&lt;b&gt;Hello&lt;/b&gt;</p>
~~~

The browser **displays** the characters `<b>Hello</b>` as text instead of creating a bold tag. Whenever you want to display user-entered content strictly as text, this is the right choice.

In Thymeleaf 3.1, inline expressions using **double brackets** `[[...]]` correspond to escaped text:

~~~html
<p>Note: [[${comment}]]</p>
~~~

### 4.2. `th:utext` and `[(...)]`: Unescaped HTML

~~~html
<!-- DO NOT use directly with user-supplied comments -->
<p th:utext="${comment}">Comment</p>
<p>[(${comment})]</p>
~~~

`th:utext` stands for *unescaped text*. If `comment` contains HTML tags, the browser parser can interpret them. The inline expression `[(...)]` also outputs unescaped content. Thymeleaf 3.1 enforces some expression evaluation restrictions to protect the template engine, yet it **is not an HTML output sanitizer**.

Consider unescaped HTML only when the business genuinely requires rich formatted HTML and you have built a sanitization pipeline with an explicit allowlist policy. Never assume "data from the database" or "admin-only input" is automatically safe: admin accounts can be compromised or content imported from external sources.

### 4.3. HTML Attributes Are a Different Context

~~~html
<input type="text" th:value="${comment}">
<span th:title="${comment}">Hover to view</span>
<div th:attr="data-comment=${comment}"></div>
~~~

Thymeleaf evaluates attribute expressions, encodes appropriate characters, and preserves attribute structure in standard cases. **You must still use fixed, purpose-appropriate attributes.** Manually concatenating HTML strings, omitting quotes around attributes, or using user input as attribute names sharply increases injection risk.

A value containing quotes such as `" autofocus onfocus="...` must never "break out" of an attribute properly encoded by the framework. For hand-built HTML, use an encoder designed for quoted HTML attributes and always quote values.

**Do not confuse this with event-handler attributes** such as `onclick` or `onerror`: their values are JavaScript. Standard HTML attribute encoding **does not turn JavaScript code into inert data** once the browser decodes HTML entities. Avoid injecting user data into `th:onclick` or any `on*` attribute.

## 5. Output Encoding Must Match the Context

| Data placement | Proper approach | What to avoid |
| --- | --- | --- |
| Text inside HTML tags | Thymeleaf `th:text` / `[[...]]` | `th:utext`, `[(...)]` with raw input |
| Quoted HTML text attribute | `th:value`, `th:title`, `th:attr` with fixed attribute names | Concatenating tag strings, unquoted attributes, dynamic attribute names |
| Query parameter in `href` | Thymeleaf URL link expression with parameters; encode URL component and HTML attribute per context | Concatenating `?q=` directly and rendering raw |
| Full user-supplied URL | Parse/validate scheme and destination; allowlist before rendering | Trusting a URL merely because it is HTML-escaped |
| JavaScript string inside HTML | Context-aware JavaScript serializer inlining, or pass via `data-*` attribute and read in DOM | Injecting template expressions straight into JS code/event handlers |
| CSS property value | Finite validated/allowlisted values, fixed CSS property names | Letting input act as selectors, property names, or raw `style` |
| DOM text update | `textContent` | `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` with raw input |
| User-authored HTML | Strict allowlist HTML sanitizer, then render per contract | Parsing/rendering raw user HTML directly |

**There is no single "HTML escape function" that works across JavaScript, CSS, URLs, and HTML attributes.** Browsers run multiple parsers in sequence. An HTML-encoded string can still be dangerous if subsequently interpreted as JavaScript or an executable URL scheme.

### 5.1. URLs: Encode Parameters and Control Schemes

For a fixed internal route, Thymeleaf supports:

~~~html
<a th:href="@{/pages/search(q=${comment})}">Search</a>
~~~

`@{...}` is a link expression; parameter `q` is processed as a URL parameter and the resulting value is placed into the HTML attribute. `&`, spaces, or `?` inside `comment` will not be concatenated raw to alter query structure.

**However**, if the input is an entire URL, encoding HTML characters alone **does not block** a value starting with `javascript:` or an unauthorized external domain. When business requirements allow user-supplied links, you must **parse the URI, verify the `http`/`https` scheme and host/destination against an allowlist**, and then render via a safe attribute mechanism. Avoid validating URLs with a naive `startsWith("https")`, because syntax validation and edge-case parsing still matter.

If the frontend constructs URLs in JavaScript, `encodeURIComponent(value)` only encodes **a single component** such as a query parameter; it does not validate the safety of an entire URL. Use `new URL(...)` and a scheme/host policy for dynamic URLs.

### 5.2. JavaScript Embedded in HTML

Do not use:

~~~html
<!-- Unsafe: dynamic value concatenated directly into JavaScript source -->
<script>
  const message = '/* RAW_USER_INPUT_CONCATENATED_HERE */';
</script>
~~~

Input containing quotes, backslashes, or sequences resembling a closing script tag can break out of context if escaping is inadequate. The preferred approach is **not generating inline scripts from user data**: place text in a template-escaped attribute, then use a static JavaScript file that reads `dataset` and updates the UI via `textContent` (practical example in Section 7).

If a Thymeleaf-rendered script is unavoidable, `th:inline="javascript"` mode with **escaped inlining** `[[...]]` lets Thymeleaf's serializer emit a JavaScript literal including quotes and escaping. Illustrative form:

~~~html
<script th:inline="javascript">
  const message = /*[[${comment}]]*/ "default";
</script>
~~~

**Do not switch to** `[(...)]` to disable escaping. Nor should you construct raw JavaScript statements, event-handler code, or variable names from untrusted input. Inline script safety must account for both the **HTML script element** context and the **JavaScript string** context; test special inputs like quotes, `<`, and script-closing sequences. Using external JS + escaped DOM attributes is usually easier to lock down with CSP.

### 5.3. CSS and Dangerous Contexts

Never place arbitrary input into CSS selectors, property names, entire `style` blocks, or `url(...)` syntax. If users may pick a background color, constrain it to a fixed set of values:

~~~java
Set<String> allowedColors = Set.of("red", "blue", "green");
String chosen = allowedColors.contains(color) ? color : "blue";
~~~

The snippet above is illustrative inside a Java method with `color` and `Set` imported. A better pattern is mapping business values to **fixed CSS classes** on the server or frontend instead of concatenating style text. Dynamic data inside HTML comments, tag names, attribute names, raw JavaScript, or raw style blocks are also **dangerous contexts**; do not try to patch them by escaping a handful of characters.

## 6. Restricting Dynamic Content Across Multiple Layers

"Restricting" means more than truncating strings. A secure view exposes **only the necessary data in the permitted format**:

1. **Length limits:** for example, preview comments capped at 200 characters or post bodies capped per business rules. Limits control UX, rendering cost, response size, and resource abuse; they **do not eliminate XSS by themselves**.
2. **Field and data exposure limits:** controllers put only attributes needed for display into `Model`. Never pass password hashes, access tokens, internal error details, or entire entities carrying sensitive fields into templates.
3. **Schema validation:** data types, ranges, enums, IDs, ownership, length; do not strip `<` or `&` arbitrarily when they are valid business characters.
4. **Markup subset limits:** if rich text is allowed, support only a required HTML subset; never use regexes in place of a parser-based sanitizer.
5. **URL/media limits:** validate schemes, hosts, MIME/file types, resource paths, and view permissions; an escaped link can still direct users to a phishing site.
6. **Browser script and resource limits:** configure CSP, avoid inline scripts, and govern third-party scripts deliberately. CSP complements template escaping; it does not replace it.
7. **Access-time limits:** authorization verifies the viewer is allowed to fetch the data before putting it into the model.

For plain text displayed from a database, storing and passing it as a regular string and rendering with `th:text` is almost always better than building HTML strings. For multi-line content, apply fixed CSS `white-space: pre-wrap` to the text container; there is no need to convert `\n` to `<br>` using `th:utext`.

## 7. Runnable Spring Boot 3.x Example: Safe Text Rendering

Create a project via Spring Initializr: **Java 17+**, **Spring Boot 3.x**, **Maven**, dependencies **Spring Web**, **Thymeleaf**, and **Spring Boot Starter Test**. In Maven, the starters are `spring-boot-starter-web`, `spring-boot-starter-thymeleaf`, and `spring-boot-starter-test`. Package is `com.example.demo`.

File structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/SafeViewController.java
src/main/resources/templates/preview.html
src/main/resources/static/js/preview.js
src/test/java/com/example/demo/SafeViewControllerTest.java
~~~

### 7.1. Startup File

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.2. Controller: Length Limit and Putting Plain Text in Model

**`src/main/java/com/example/demo/SafeViewController.java`**

~~~java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.server.ResponseStatusException;

@Controller
@RequestMapping("/pages")
public class SafeViewController {

    @GetMapping("/preview")
    public String preview(
            @RequestParam(defaultValue = "Hello") String message,
            Model model) {

        return render(message, model);
    }

    @GetMapping("/search")
    public String search(@RequestParam("q") String q, Model model) {
        return render(q, model);
    }

    private String render(String message, Model model) {
        if (message.length() > 200) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Text is too long");
        }

        model.addAttribute("message", message);
        return "preview";
    }
}
~~~

**Explanation:**

- Both endpoints use **`@Controller`** and return the logical view `"preview"` so Thymeleaf generates HTML.
- `message` or `q` parameters may carry browser-entered text. `render` rejects inputs longer than 200 UTF-16 code units per `String.length()`; this limit is **only a UX/resource example**, not an XSS safety boundary.
- The value stored in the model **remains raw text**; Thymeleaf performs encoding when emitting HTML.
- The app includes no database or authorization system; production apps must check permissions and data exposure when showing private data.

### 7.3. Template: Safe Text, Attributes, URLs, and Data Attributes

**`src/main/resources/templates/preview.html`**

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Content Preview</title>
  <script th:src="@{/js/preview.js}" defer></script>
</head>
<body>
  <h1>Preview</h1>

  <!-- HTML text context: Thymeleaf escapes the data. -->
  <p id="safe-text" th:text="${message}">Preview text</p>

  <!-- HTML attribute context: keep fixed attribute names. -->
  <label for="input-preview">Data</label>
  <input id="input-preview" type="text" th:value="${message}">

  <!-- URL parameter context, fixed /pages/search destination. -->
  <a id="search-link" th:href="@{/pages/search(q=${message})}">
    View search results
  </a>

  <!-- Pass encoded data via attribute, do not inject into JS source. -->
  <div id="client-data" th:attr="data-message=${message}"></div>
  <p id="client-text"></p>
</body>
</html>
~~~

**Why is this template safe for the data it handles?**

- `th:text` renders data as escaped HTML text.
- `th:value` and `th:attr` place data inside **fixed-name attributes** with quoting/encoding handled by the template engine.
- `th:href="@{/pages/search(q=${message})}"` uses a server-chosen internal path; user data only sits in a query parameter.
- There is no `th:utext`, no inline JavaScript interpolating input, no full dynamic `href` URL, and no HTML assembled by concatenating user input.

### 7.4. External JavaScript: Using `textContent`

**`src/main/resources/static/js/preview.js`**

~~~javascript
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const source = document.getElementById("client-data");
  const output = document.getElementById("client-text");

  if (!source || !output) {
    return;
  }

  const text = source.dataset.message ?? "";
  output.textContent = text;
});
~~~

`dataset.message` reads the value already parsed by the browser from the HTML attribute. `textContent` creates a **text node** without parsing HTML inside the data string.

**Do not replace with:**

~~~javascript
// UNSAFE for untrusted data:
output.innerHTML = text;
~~~

`innerHTML` tells the browser to parse text as HTML source, which can create dangerous elements or attributes. APIs like `outerHTML`, `insertAdjacentHTML`, and `document.write` also require strict control. To build structured DOM nodes, use `document.createElement`, set fixed attributes, and assign text via `textContent`.

### 7.5. Running and Observing the Payload

From the Maven project directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `mvnw.cmd spring-boot:run`. Without Maven Wrapper, use `mvn spring-boot:run` if Maven is installed.

Send a test string containing an HTML tag using `curl`:

~~~bash
curl -G -i "http://localhost:8080/pages/preview"   --data-urlencode 'message=<img src=x onerror=alert(1)>'
~~~

The line above uses single-line arguments (or `\` in Linux/macOS/Git Bash). On Windows PowerShell, use `curl.exe` on one line with PowerShell-compatible quoting.

**What to observe:**

- Status 200, `Content-Type` is HTML.
- The HTML response around `id="safe-text"` contains the corresponding escaped entities, such as:

~~~html
<p id="safe-text">&lt;img src=x onerror=alert(1)&gt;</p>
~~~

- In the browser, that text renders **literally as characters**, with no `img` element created from user input.
- The external JavaScript also assigns the string to `#client-text` via `textContent`, creating no new HTML elements.
- The `/pages/search?q=...` link has its query parameter properly encoded while keeping the destination a fixed internal path.

Limitation of this example: `String.length()` counts UTF-16 code units rather than visible grapheme clusters (such as Vietnamese diacritics or emoji). Production systems enforcing limits by user-perceived characters or wire bytes must define explicit rules and use appropriate counters.

## 8. Testing Rendered HTML with MockMvc

Testing `model().attribute("message", input)` alone is **not enough** to confirm HTML is escaped; the controller may bind properly while the template still uses `th:utext`. The tests below run **the whole application plus Thymeleaf templates** via `@SpringBootTest` and `@AutoConfigureMockMvc`.

**`src/test/java/com/example/demo/SafeViewControllerTest.java`**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeViewControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void untrustedMarkupIsRenderedAsText() throws Exception {
        String payload = "<img src=x onerror=alert(1)>";

        String html = mockMvc.perform(get("/pages/preview")
                        .param("message", payload))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        assertTrue(html.contains(
                "&lt;img src=x onerror=alert(1)&gt;"));
        assertFalse(html.contains(
                "<img src=x onerror=alert(1)>"));
    }

    @Test
    void quotesStayInsideInputAttribute() throws Exception {
        String payload = "\" autofocus onfocus=\"alert(1)";

        String html = mockMvc.perform(get("/pages/preview")
                        .param("message", payload))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        // Quotes inside data do not become a new attribute.
        assertFalse(html.contains(
                "value=\"\" autofocus onfocus="));
        assertTrue(html.contains("id=\"input-preview\""));
    }

    @Test
    void rejectsExcessiveInputLength() throws Exception {
        mockMvc.perform(get("/pages/preview")
                        .param("message", "a".repeat(201)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void searchUsesSameSafeView() throws Exception {
        mockMvc.perform(get("/pages/search")
                        .param("q", "<b>Hello</b>"))
                .andExpect(status().isOk());
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

These assertions verify the HTML response by **rendering the real template** in a MockMvc integration test. The first test asserts that `<img...>` is escaped in HTML, the second checks that data containing quotes does not break out into a new attribute, and the third verifies the length limit.

**Testing limitation:** MockMvc does not execute browser JavaScript. To verify DOM-based XSS resistance and absence of script execution, add browser integration/security tests with special inputs in an isolated environment. HTML parser-based DOM assertions (rather than substring matching) can prove no element or event handler was created from user input. Source testing is an important signal, yet XSS defense must cover every sink and data path.

## 9. When Rich Text Truly Needs HTML: Sanitize with an Allowlist

A WYSIWYG editor may need to allow **bold, italics, lists, and links**. Applying `th:text` would display tags as literal text rather than formatting. In that scenario, the solution is **HTML sanitization** prior to unescaped rendering, using a maintained library and a strict allowlist policy.

**Standalone illustrative example** using [OWASP Java HTML Sanitizer](https://github.com/OWASP/java-html-sanitizer) (you must add the dependency matching your project version):

~~~java
import org.owasp.html.PolicyFactory;
import org.owasp.html.Sanitizers;

public class RichTextSanitizer {
    private static final PolicyFactory POLICY =
            Sanitizers.FORMATTING.and(Sanitizers.LINKS);

    public static String sanitize(String input) {
        return POLICY.sanitize(input == null ? "" : input);
    }
}
~~~

The built-in policies here merely introduce the API: `FORMATTING` and `LINKS` permit a defined markup set while filtering according to library rules. In production, **design an explicit allowlist** of required tags, attributes, and protocols, typically disallowing scripts, event-handler attributes, and disallowed URL schemes. Test links, SVG, MathML, nested tags, and complex parser edge cases, and keep the library patched regularly.

After sanitization:

~~~java
String safeHtml = RichTextSanitizer.sanitize(rawHtml);
model.addAttribute("safeHtml", safeHtml);
~~~

Only once `safeHtml` has passed a trusted policy may the template intentionally render:

~~~html
<div th:utext="${safeHtml}"></div>
~~~

**Important:** `th:utext` remains a sensitive sink here; it is suitable only when the incoming value has been properly sanitized. Never allow another code path to feed `rawHtml` into the same attribute. Never concatenate untrusted raw HTML **after** sanitization. Never treat HTML sanitization as sufficient if the data is later placed into JavaScript, CSS, or URLs; every output context keeps its own rules.

For most pages showing product names, addresses, plain-text comments, statuses, or notices, **`th:utext` is unnecessary**. Keeping data as text and rendering with `th:text` is safer and easier to maintain.

## 10. JSP, Spring `HtmlUtils`, and Other Rendering Paths

If a project uses JSP/JSTL, one way to render escaped text is:

~~~jsp
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<p><c:out value="${comment}" /></p>
~~~

This example targets Jakarta Tags 3.x/JSP compatible with Spring Boot 3 with dependencies and taglibs configured. `c:out` with its default XML escaping renders data safely as text in many simple HTML text contexts. Do not use text/XML escaping to assemble JavaScript source, CSS, or executable URLs.

Spring Framework also provides `org.springframework.web.util.HtmlUtils.htmlEscape(String)`, for example in Java:

~~~java
String escaped = HtmlUtils.htmlEscape("<b>Hello</b>");
System.out.println(escaped);
~~~

When `HtmlUtils` is imported and run in a project with Spring Web, stdout will conceptually be:

~~~text
&lt;b&gt;Hello&lt;/b&gt;
~~~

This is **HTML escaping for text**; it does not replace JavaScript encoding, URL validation, or a sanitizer. You generally do not need to call `HtmlUtils.htmlEscape` before Thymeleaf `th:text`, as that can cause **double-encoding**.

If returning HTML manually from a REST controller:

~~~java
return ResponseEntity.ok()
        .contentType(MediaType.TEXT_HTML)
        .body("<p>" + untrusted + "</p>");
~~~

This is an **anti-pattern**: concatenation can inject `untrusted` directly into HTML source. Prefer Thymeleaf, or apply context-appropriate encoder APIs when truly constructing HTML. Never escape arbitrarily at one point and reuse the encoded string across different contexts.

## 11. CSP, Cookie Flags, and Trusted Types

Output encoding and HTML sanitization address the direct cause. Other mechanisms add extra control layers:

### Content Security Policy (CSP)

**Conceptual policy example**, to be tested against your application's actual resources:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

This policy restricts scripts to the current origin, blocks objects/plugins, and constrains base URIs and framing. For applications needing inline scripts, CDNs, required iframes, or broader browser compatibility, adjust the policy, use nonces/hashes as needed, and roll out gradually via report-only mode.

**CSP is not a "silver bullet for XSS"**: overly permissive rules like `unsafe-inline` weaken its value; scripts from allowed origins or buggy DOM logic can still be dangerous. Verify template escaping first; CSP is defense in depth.

### Trusted Types

Chromium-based browsers support **Trusted Types** paired with CSP `require-trusted-types-for 'script'`, controlling how plain strings enter dangerous DOM sinks like `innerHTML`. If adopted, prepare reviewed policies and a compatibility plan for frontend libraries. Trusted Types do not replace authorization, input checks, or output encoding.

### Cookie Flags

`HttpOnly`, `Secure`, and `SameSite` are useful cookie flags for session management and limiting certain attack impacts. They **do not stop malicious JavaScript from executing on the page** once XSS occurs. Never assume `HttpOnly` cookies remove the need to escape rendered HTML.

## 12. Systematic XSS Testing

Build a **source → sink** matrix for every dynamic value that actually appears:

| Source | Sink | Key Check |
| --- | --- | --- |
| Query parameter `message` | Thymeleaf `th:text` | Strings with tags create no new elements |
| Form field `name` | `input th:value` | Quotes cannot break out of the attribute |
| Search text | `th:href` with query param | Path stays fixed; parameter is encoded |
| Data from DB | Comments/lists in templates | Stored markup displays safely as text |
| Data in `data-*` | DOM `textContent` | `innerHTML` is never used after reading |
| WYSIWYG rich text | Controlled `th:utext` region | Sanitizer retains only the defined HTML subset |
| User-supplied URL | Dynamic `href` | Scheme, host, and redirect target are allowlisted |
| Data passed to scripts | JS serializer or external JS | Quotes, slashes, closing script tags, and context are handled |

In application QA, combine:

1. **Unit tests** for validators, URL allowlists, and rich-text sanitizers.
2. **MockMvc / integration tests** rendering real Thymeleaf templates with `<`, `>`, `&`, quotes, and markup-like strings; assert DOM structure or output encoding.
3. **Browser tests** covering DOM sinks, navigation links, and CSP in a real browser.
4. **Code reviews** focused on `th:utext`, `[(...)]`, `innerHTML`, `outerHTML`, `document.write`, raw HTML concatenation, dynamic `href`, event-handler attributes, and template injection.
5. **Dependency updates** for template engines, sanitizers, and frontend libraries, especially when handling rich text.

Do not test a single fixed payload and declare XSS eliminated. Every new data path, particularly user-generated content features, must be checked against its output context.

## 13. Common Mistakes

### Mistake 1. Thinking `Model` Automatically Strips HTML

`model.addAttribute("comment", untrusted)` only stores the attribute in the model. **Thymeleaf `th:text`** is what encodes the value for HTML text at render time. If the template uses `th:utext`, the result is completely different.

### Mistake 2. Using `th:utext` to Preserve Line Breaks

If the goal is merely preserving newlines, use text escaping and CSS:

~~~html
<p class="comment" th:text="${comment}">Comment</p>
<style>
  .comment { white-space: pre-wrap; }
</style>
~~~

There is no need to convert text to `<br>` via an HTML string. This CSS is fixed, not user-supplied.

### Mistake 3. HTML-Escaping Before Inserting into a JavaScript String

HTML entity encoding does not secure a JavaScript context. Use a serializer designed for JS literals and HTML script contexts, or an external script reading data from the DOM and applying `textContent`.

### Mistake 4. Assuming Escaping `href` Is Enough

A URL with a malicious scheme or pointing to a phishing site remains dangerous even when the attribute is validly HTML-escaped. **Validate URLs by scheme and host**, allowing only business-approved destinations.

### Mistake 5. Sanitizing HTML with Regular Expressions

HTML involves nested markup, attribute encoding, namespaces, URL schemes, and intricate parser quirks. Regexes rarely model browser parsers accurately. Use a maintained sanitizer with an allowlist and a rich-text test suite.

### Mistake 6. Passing Text from an API Response to `innerHTML`

Even when an API response is JSON (`application/json`) and comes from your own server, strings inside it can still contain dangerous HTML. **`textContent`** or safe DOM APIs ensure it renders as data. JSON does not automatically sanitize browser sinks.

### Mistake 7. Pre-Encoding and Re-Encoding

Storing `&lt;b&gt;` in the DB and then rendering with `th:text` can display literal `&lt;b&gt;` due to double encoding. Keep raw data, sanitized HTML, and context-specific encoded output clearly separated in your data contracts.

### Mistake 8. Truncating Strings Thinking It Stops XSS

A 200-character limit helps UX and resource control, yet many dangerous payloads are very short. Length validation **complements** context-specific output encoding; it does not replace XSS defenses.

### Mistake 9. Relying Solely on CSP or a WAF

CSP is defense in depth; a WAF can miss DOM XSS or novel payloads. Controlling output encoding/sanitization, data sources, and DOM sinks remains primary.

### Mistake 10. Testing Only the Model While Skipping the Template

MockMvc `model().attribute("comment", payload)` only proves the controller passed the data. Testing XSS in server-rendered views requires **rendering the template** and inspecting the response/DOM output. That is why the example uses `@SpringBootTest` + `@AutoConfigureMockMvc`.

## 14. Review Questions

**1. Why is `th:text` generally better than `th:utext` for user comments?**

Because `th:text` HTML-encodes and displays data characters as text, whereas `th:utext` lets the HTML parser interpret markup. When rich text is needed, sanitize it with a trusted allowlist first.

**2. If an input is at most 20 characters long, is it guaranteed free of XSS?**

No. Length limits are UX/resource rules; XSS depends on whether data is interpreted as code/markup in its output context.

**3. Does Thymeleaf's link expression `@{/search(q=${query})}` eliminate all URL risks?**

No. It safely builds URL parameters for a fixed path. If the entire `href` is a user-controlled URL, you must validate scheme/host/redirect policy.

**4. Why is `output.textContent = value` appropriate when displaying plain text?**

Because it sets the **text content** of a DOM node without asking the HTML parser to parse the string as HTML, unlike `innerHTML`.

**5. When is a sanitizer required?**

When a product genuinely allows users to submit a rendered subset of HTML, such as a formatted editor. A parser-based sanitizer must enforce an allowlist policy and stay maintained; ordinary plain text should simply be escaped in the view.

**6. Do `HttpOnly` cookies eliminate XSS?**

No. They prevent JavaScript from reading cookies marked `HttpOnly`, yet do not prevent JS injection or protect page actions from being hijacked.

## 15. Pre-Production UI Checklist

1. Inventory every dynamic field from requests, databases, and third parties along with the **final context** where it renders.
2. For HTML text use `th:text`/`[[...]]`; for attributes use Thymeleaf attribute processors with quotes; never concatenate raw HTML from input.
3. Avoid event-handler attributes, `th:utext`, `[(...)]`, and DOM HTML sinks for untrusted data.
4. For URLs, validate scheme/host/destination first, then encode parameters and attributes per context.
5. For JavaScript, prefer external scripts + escaped DOM data with `textContent`; if inlining is required, use proper serialization and test the HTML script context.
6. For rich text, apply a tested allowlist HTML sanitizer, control where sanitized values flow, and keep dependencies updated.
7. Restrict input and model contents per business rules, while **still escaping output** and enforcing authorization.
8. Enable an appropriate CSP and consider Trusted Types for complex frontend DOMs, treating them as additional layers.
9. Test actual HTML templates, browser DOMs, special characters, and unauthorized access cases rather than testing only controllers and models.

## Official Documentation and Security References

- [Thymeleaf 3.1 — Using Thymeleaf: escaped/unescaped text, attributes, JavaScript inlining](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html)
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [OWASP — DOM Based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html)
- [OWASP — HTML Sanitization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML_Sanitization_Cheat_Sheet.html)
- [Spring Framework 6.2 — View Technologies](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-view.html)
- [Spring Framework Javadoc — HtmlUtils](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/util/HtmlUtils.html)
- [OWASP Java HTML Sanitizer](https://github.com/OWASP/java-html-sanitizer)
