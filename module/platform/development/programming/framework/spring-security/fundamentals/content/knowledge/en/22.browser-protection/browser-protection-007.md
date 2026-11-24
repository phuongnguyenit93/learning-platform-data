# XSS still requires output encoding and context-aware data handling

> **Module:** Spring Security – fundamentals → **Browser Protection**. **Cross-Site Scripting (XSS)** is a class of vulnerabilities occurring when untrusted data enters a web page or DOM such that the browser interprets it as **active HTML/JavaScript/CSS** rather than plain text. **Spring Security does not automatically sanitize or escape every value rendered by a controller, template, or JavaScript.** The core defense is **context-aware output encoding** or using **safe DOM APIs**; if a product must render user-authored HTML, use **allowlist-based HTML sanitization**. Mechanisms like CSP, HttpOnly, SameSite, CSRF, and HTTP security headers only supplement—never replace—XSS defense where data enters the browser.

This lesson uses **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC**, covering HTML text, attribute, URL, JavaScript, CSS, DOM, and JSON contexts. It includes runnable examples with **OWASP Java Encoder**, JavaScript `textContent`, defense-in-depth CSP configuration, and MockMvc tests.

## 1. Why can an application using Spring Security still suffer from XSS?

A system may configure login, authorization, CSRF tokens, `HttpOnly` cookies, and many security headers yet still have a controller like:

```java
@GetMapping(value = "/hello", produces = "text/html")
@ResponseBody
String hello(@RequestParam String name) {
    // COUNTER-EXAMPLE: concatenating input directly into HTML.
    return "<h1>Hello " + name + "</h1>";
}
```

If `name` is a string containing markup controlled by someone else, the browser may parse it as HTML structure instead of text. For instance, input shaped like:

```text
<img src=x onerror=alert(1)>
```

This is a **harmless local test pattern** illustrating how an event attribute can become executable code. Never use attack payloads against systems you are not authorized to test. If the input is concatenated verbatim, the result is an `<img>` element in HTML—completely different from displaying the literal text `<img ...>`.

**The security decision must happen where data is output:** Controllers/APIs can receive and store data in many steps, but at the moment a value is embedded into **HTML, JavaScript, CSS, attributes, URLs, or the DOM**, you must know **which parser will read it**. An encoder for HTML text is not automatically valid for a JavaScript string, and a URL component encoder does not verify that a URL has a safe scheme.

A Spring Security `SecurityFilterChain` can:
- Require users to authenticate before accessing a route.
- Enforce roles/authorities, CSRF, and `SecurityContext`.
- Add HTTP headers such as `X-Content-Type-Options`, `X-Frame-Options`, or CSP when configured.
- Help limit certain consequences if code is injected into a page.

However, it **does not know which parser context each variable in Thymeleaf/React/JSP or each client `innerHTML` call sits in**. Escaping/sanitizing at output is the responsibility of the rendering/client layer and appropriate template libraries.

## 2. XSS classification and trust boundaries

| Type | Data flow | Typical example | Primary defense focus |
|---|---|---|---|
| **Reflected XSS** | Query/header/request input → immediate HTML response | `/search?q=...` rendering query as markup | Encode at render time, template autoescape, URL validation |
| **Stored XSS** | Comment/profile/DB content → another user's page | Comment containing unprocessed markup | Encode at every output or sanitize rich HTML when allowed |
| **DOM-based XSS** | URL hash, query, `postMessage`, API → browser DOM sink | JS assigning untrusted string to `innerHTML` | DOM `textContent`, safe APIs, URL allowlists, Trusted Types |
| **Markup/template injection** | Input becomes template/element/attribute syntax instead of data | Letting user pick raw template names or unescaped HTML | Never treat input as template source; keep trusted syntax fixed |

**Data paths matter:** attackers can control query parameters, request paths, form data, user profiles, comments, filenames, third-party data, WebSocket events, API responses, message buses, `localStorage`, or URL fragments. "Data comes from the DB" does not make it trusted; stored XSS is simply waiting to be rendered into another page.

### 2.1. Assets and impact

XSS executing under the application's origin can:
- Call same-origin APIs with browser auto-attached credentials.
- Read page/DOM contents and displayed user data.
- Alter the UI for phishing or tricking user actions.
- Submit requests carrying CSRF tokens that the page itself can read.
- Access tokens/secrets reachable by JavaScript, or interact with APIs inside the victim's session.

`HttpOnly` cookies stop scripts from reading cookie values directly, yet **do not stop scripts from sending same-origin requests with cookies attached by the browser**. CSRF tokens do not stop XSS either, since scripts running on the valid origin can read and submit tokens. Therefore, XSS must be blocked right at the sinks.

### 2.2. Input validation differs from output encoding

Validation checks data **against business rules**: username length, status enums, email format, quantities, file types. For instance, theme accepts only `dark` or `light`; `id` is a positive integer. This reduces meaningless or malformed data.

However, a legitimate comment can contain `<`, `>`, `"`, `'`, and `&`; you cannot ban those characters product-wide. Moreover, safely stored DB input may appear in multiple places:
- Inside `<p>` text.
- Inside a `title` attribute.
- Inside JSON passed to JS.
- Inside a URL query.
- Inside an exported email or PDF.

Each destination requires its own encoding rules. **There is no single "sanitize input" function that works correctly for every output.**

## 3. Most important rule: encode according to parser context

Suppose `comment` is a raw string from the DB. Parsers behave differently:

| Data destination | Example | Correct approach | Insufficient approach |
|---|---|---|---|
| HTML text node | `<p>comment</p>` | HTML entity encoding or `textContent` | URL encoding, or replacing only `<` |
| Normal quoted HTML attribute | `<input value="comment">` | Attribute encoding and **always quote** | Text-only HTML encoding, unquoted attributes |
| URL query component | `/search?q=comment` | Percent-encode the **component**, build URL from trusted parts | Encoding the whole URL as one value or substring checks |
| URL inside an HTML attribute | `<a href="/search?q=...">` | Component-encode → assemble trusted URL → HTML-attribute-encode | Percent-encoding only and dropping into an arbitrary attribute |
| JavaScript string in HTML `<script>` | `const x = "...";` | Avoid embedding; or use an encoder for **script-block strings** | HTML encoding only, or escaping quotes only |
| DOM text | `element.textContent = comment` | Use `textContent`/`createTextNode` | `innerHTML` with raw data |
| CSS value | `style="color: comment"` | Fixed property + value allowlist, CSSOM when appropriate | HTML-encoding raw CSS |
| User-authored rich HTML | WYSIWYG comment | HTML sanitizer with allowlist policy | `th:utext` with raw content |
| Event handler/script/HTML tag/attribute name | `onclick=...` or user-chosen tag | **Never place untrusted data in code positions** | Any generic string encoder |
| JSON response | API returns `{"message":comment}` | Standard JSON serializer, `Content-Type: application/json` | Manual JSON string concatenation or raw JSON embedded in HTML |

**Crucial distinction:** HTML, JavaScript, CSS, and URL parsers interpret identical characters very differently. If a string passes through **two parsers**—for example a URL inside an HTML attribute—handle **both contexts**. If a value is later passed to a DOM sink, evaluate the client context as well.

### 3.1. Encode at the final output, do not unconditionally encode source data

In domain/service/database layers, store data **in its original semantic form** after business validation. Encode **when emitting to a specific parser**. Do not store `&lt;` in every DB field just because `<` must render on a web page: reusing it later in JSON, email, or plain text leads to double encoding or corrupted semantics.

If you need to store **sanitized** HTML, that is a separate choice: store rich text processed through a versioned policy (optionally keeping the raw original in a restricted store per business needs) and govern every place it is rendered. Sanitization does not mean "any processed HTML is safe for every parser."

### 3.2. Avoid double escaping

For example, HTML-encoding `<b>A&B</b>` once turns it into `&lt;b&gt;A&amp;B&lt;/b&gt;`. Encoding it a second time causes the browser to display literal `&lt;...` rather than the intended characters.

**Rule:** Assign encoding responsibility clearly at boundaries; if a template engine auto-escapes, do not manually run an HTML text encoder before passing the value to `th:text`. Test with both special characters and normal strings to catch double encoding.

## 4. HTML text context: between two tags

For untrusted data displayed between fixed tags:

```html
<p>Hello, USER_NAME</p>
```

HTML entity encoding is required so `<` cannot open an element, `&` cannot start an entity, and other special characters cannot alter syntax.

Examples:

| Raw character | Common HTML representation |
|---|---|
| `&` | `&amp;` |
| `<` | `&lt;` |
| `>` | `&gt;` |
| `"` | `&quot;` or numeric entity |
| `'` | `&#x27;` or numeric entity |

**Note:** A verified encoder may use numeric entities or another equivalent representation; tests should assert that **text remains text only** rather than hardcoding one exact escaping style.

Using a maintained Java library:

```java
import org.owasp.encoder.Encode;

String safe = Encode.forHtmlContent(userText);
String html = "<p>" + safe + "</p>";
```

This snippet **illustrates usage inside a method**, not a standalone runnable class. `Encode.forHtmlContent` performs encoding for **HTML text context**. If using a template engine that auto-escapes, prefer the engine's native rendering rather than stacking both a Java encoder and auto-escaping.

### 4.1. Browsers do not "self-protect" when seeing data in HTML

If the server returns `Content-Type: text/html`, the browser parses the body as HTML. A raw string concatenated into HTML does not become safe merely because it came from an API secured by Spring Security or from a database queried via prepared statements. SQL injection, authentication, and XSS are distinct boundaries.

### 4.2. Use DOM APIs instead of HTML strings whenever possible

If JavaScript is updating UI solely to display text:

```javascript
const message = new URLSearchParams(location.search).get("message") ?? "";
const output = document.querySelector("#message");
output.textContent = message;
```

`textContent` on a normal HTML element inserts the string as a text node **without HTML parsing**. Do not HTML-encode before assigning `textContent`; doing so makes users see `&lt;` instead of `<`. `createTextNode` or `insertAdjacentText` also work well. However, assigning `textContent` on `<script>` or `<style>` is a different context and can create executable code; always target trusted elements.

## 5. HTML attribute context: always quote and pick safe attributes

Example value inside an input attribute:

```html
<input name="displayName" value="USER_NAME">
```

You must **keep the attribute name fixed, keep quotes**, and encode the value for **HTML attribute context**:

```java
String html = "<input name=\"displayName\" value=\"" +
    Encode.forHtmlAttribute(userName) + "\">";
```

Without quotes:

```html
<!-- COUNTER-EXAMPLE: unquoted attribute -->
<input value=USER_NAME>
```

Whitespace can terminate an unquoted attribute value, allowing subsequent tokens to be parsed as new attributes. Therefore, never construct HTML via string concatenation with unquoted attributes. Even when quoted, the **attribute name** must be fixed and safe.

### 5.1. Not all attributes carry the same risk

Attributes such as `title`, `value`, or `alt` are generally text attributes. By contrast:
- `href` / `src` require **URL scheme + destination validation** in addition to attribute encoding.
- `style` involves **CSS parsing** and allowed property/value rules.
- `onclick`, `onerror`, and event-handler attributes put data directly into a **JavaScript execution context**.
- `srcdoc` contains an **HTML document** and must not receive raw user content.
- `data-*` carries data for JS, which must still handle it safely when writing to the DOM.

**There is no magic `forHtmlAttribute` that makes every attribute safe.** For event handlers, the solution is never embedding input in code; attach pre-written event listeners:

```javascript
const button = document.getElementById("save");
button.addEventListener("click", () => {
  saveDocument(); // trusted function
});
```

When setting text attributes from JavaScript:

```javascript
input.setAttribute("title", untrustedTitle);
input.value = untrustedValue;
```

DOM APIs set literal values on specific attributes/properties without needing prior HTML encoding. Never call `setAttribute("onclick", value)` or pass an unapproved dynamic attribute name; that API does not enforce safety policies on event/URL/CSS attributes.

## 6. URL context: encode query components, and validate URLs themselves

Suppose the app provides a search link:

```html
<a href="/search?q=QUERY">Search</a>
```

Do not concatenate raw input into a URL. Follow two steps:

1. Use a **server-defined base URL**, such as `/search?q=`, and percent-encode only the **value** of `q`.
2. When placing the assembled URL into `href` in HTML, apply **HTML attribute encoding** to the full URL.

Example:

```java
String url = "/search?q=" + Encode.forUriComponent(query);
String html = "<a href=\"" +
    Encode.forHtmlAttribute(url) + "\">Search</a>";
```

`Encode.forUriComponent` ensures `&` in the query does not split into another parameter, `#` does not become a fragment, and quotes do not break HTML structure. Still, **URL encoding is not URL validation**.

### 6.1. User-supplied full URLs are a different problem

If a product lets users enter a "personal website link":

```text
javascript:alert(1)
data:text/html,...
//other-host.example/
https://trusted.example.attacker.net/path
```

You cannot just percent-encode the entire string and drop it into `href`. You must:
- Parse and canonicalize the URL properly.
- Allow only `https` (or `http` if explicitly approved).
- Restrict host/port/path when links target internal resources or security callbacks.
- Reject `javascript:`, `data:`, relative, or protocol-relative URLs unless explicitly part of the contract.
- Avoid naive whitelists like `contains("trusted.example")` or `endsWith("trusted.example")` lacking dot-boundary checks.
- After validation, still **HTML-attribute-encode** when rendering inside `href`.

**Assembling URLs from server-validated routes + IDs is usually safer and easier to audit than accepting arbitrary URLs.** For internal navigation, use an **alias allowlist** like `dashboard`/`report` so the server picks the target.

### 6.2. DOM URL attributes also require policies

In JavaScript:

```javascript
const url = new URL("/search", location.origin);
url.searchParams.set("q", rawQuery);
link.href = url.toString();
link.textContent = "Search";
```

This works well for a **trusted base URL** + query parameter. However, replacing `"/search"` with an arbitrary user string makes `new URL` merely parse/resolve without validating allowed destinations. With `link.href = untrustedUrl`, a scheme/host policy is still required.

## 7. JavaScript context: do not mix input with code

This context easily goes wrong even when HTML-escaped:

```html
<!-- COUNTER-EXAMPLE: input concatenated directly into JS source -->
<script>
  const message = "USER_INPUT";
</script>
```

The JavaScript parser handles quotes, backslashes, escape sequences, template literals, and expression syntax. Moreover, the HTML parser has special rules for `<script>` and sequences that close the script block. **HTML entity encoding is not JavaScript string encoding**; replacing only `"` with `\"` is also insufficient to protect an HTML block containing scripts.

### 7.1. Prefer avoiding inline script data

A safer, more maintainable pattern:
- Return data from the server as JSON with `Content-Type: application/json`.
- A separate JS file fetches the data via `fetch` and a JSON parser.
- When displaying it, JS uses `textContent`, `value`, or `createTextNode`.
- When manipulating URLs/styles, apply allowlists and appropriate APIs.
- CSP can apply `script-src 'self'`/nonces to restrict inline code.

Example:

```javascript
const response = await fetch("/api/display-name", {
  credentials: "same-origin"
});
const payload = await response.json();
document.getElementById("displayName").textContent = payload.name;
```

`JSON.parse`/`response.json()` parses data rather than executing it as JavaScript source. Never use `eval()` to "parse" JSON.

### 7.2. When embedding a string in a script block is unavoidable

Some legacy applications render values into `<script>`. In that case, use a documented encoder for **JavaScript strings inside an HTML script context**, never inserting input into variable names or control syntax:

```java
String encoded = Encode.forJavaScriptBlock(rawMessage);
String script = "<script>const message = \"" + encoded +
    "\";</script>";
```

This is a **snippet** using OWASP Java Encoder, not the default pattern for new designs. Use it only when the input sits **strictly inside a trusted quoted string literal** supported by the library/version. Never use it directly for expressions, dynamic JavaScript, HTML event handlers, or `${...}` template literal expressions. Do not confuse `Encode.forJavaScriptBlock` with `Encode.forJavaScriptSource` (meant for standalone JS source) or HTML attribute encoders.

For JSON embedded in HTML, `JSON.stringify`/JSON serializers **do not automatically make raw insertion into `<script>` safe**. If inline initial state is required, use a serialization strategy tailored to HTML script contexts paired with proper CSP; the simpler option is a separate JSON endpoint.

### 7.3. Dangerous DOM sinks

| Sink | Problem | Replacement |
|---|---|---|
| `element.innerHTML = raw` | Parses raw string as HTML | `element.textContent = raw` for plain text display |
| `element.outerHTML = raw` | Replaces DOM structure | `createElement` + `textContent` with fixed tags |
| `element.insertAdjacentHTML(..., raw)` | Parses markup | `insertAdjacentText` / append text node |
| `document.write(raw)` | Builds HTML from string | DOM APIs |
| `eval(raw)`, `new Function(raw)` | Turns data into code | `JSON.parse` / data-driven logic |
| `setTimeout(rawString, ...)` | Can execute string as code | Callback function |
| `location = rawUrl` | Navigates to untrusted URL | Validate redirect/target URL |
| `iframe.srcdoc = raw` | Parses HTML document | Avoid, or use sanitizer + strict sandbox policy |
| `dangerouslySetInnerHTML` / `v-html` | Bypasses framework default text escaping | Only sanitized rich HTML per policy |
| `createElement(untrustedTag)` | User chooses element name, can create special elements | Fixed tag or allowlist |

**Note:** `setAttribute()` or `textContent` is safe **when used on the right element/attribute types**. Setting `href` to `javascript:...` or setting `textContent` on `<script>` carries different semantics. Never turn a context-safe API into a blanket promise of "safe in all cases."

## 8. CSS context: do not let users write style source

CSS also has a parser and properties capable of loading resources or causing unintended behavior. Example:

```html
<!-- COUNTER-EXAMPLE: never concatenate freeform input into style -->
<div style="background-image: USER_INPUT">...</div>
```

Do not rely solely on HTML attribute encoding to accept arbitrary CSS strings. If a product lets users choose colors or themes, **switch from arbitrary values to an allowlist**:

```javascript
const themes = new Set(["light", "dark", "high-contrast"]);
const selected = themes.has(rawTheme) ? rawTheme : "light";
document.documentElement.dataset.theme = selected;
```

Real CSS stays static:

```css
:root[data-theme="light"] { --surface: #fff; --text: #111; }
:root[data-theme="dark"] { --surface: #111; --text: #fff; }
:root[data-theme="high-contrast"] { --surface: #000; --text: #ff0; }
```

If a CSS property must be set via JS, use a **fixed** property name and a value validated against that property's contract:

```javascript
const allowed = new Set(["red", "blue", "green"]);
const color = allowed.has(rawColor) ? rawColor : "blue";
element.style.setProperty("color", color);
```

Never allow arbitrary strings inside `background-image`, `url(...)`, CSS selectors, or `style` blocks without a policy. `style.setProperty` merely assigns a value; it **does not verify whether the value is security-safe**.

## 9. Rich text HTML: when output encoding breaks UX

Some features allow users to enter formatted HTML via a WYSIWYG editor: comments with bold text, bullet lists, links, tables. HTML text encoding turns every tag into literal text—**secure, but failing the rich-text requirement**.

When the product genuinely permits a limited set of HTML, use a **maintained HTML sanitizer** configured with an allowlist policy for tags, attributes, and protocols. Example with OWASP Java HTML Sanitizer:

```java
import org.owasp.html.PolicyFactory;
import org.owasp.html.Sanitizers;

PolicyFactory policy = Sanitizers.FORMATTING
    .and(Sanitizers.LINKS);
String safeHtml = policy.sanitize(userAuthoredHtml);
```

This is an illustrative snippet, not part of the runnable demo in Section 11. Add a compatible **OWASP Java HTML Sanitizer** dependency and review the concrete policy; the default `FORMATTING`/`LINKS` bundles are only starting points. If images, tables, embeds, iframes, or custom attributes are needed, **audit the exact policy** rather than opening up arbitrary HTML.

### 9.1. What must a sound sanitizer address?

- Which tags are allowed: `p`, `b`, `i`, `ul`, `li`, `a`? Are `style`, `svg`, or `math` needed?
- Which attributes are allowed **on which tags**; which protocols are permitted on `href`; are `javascript:`/`data:` blocked?
- How are HTML entities and URL decoding/canonicalization handled?
- Is `rel="noopener noreferrer"` added to external links per policy when needed?
- Should internal images be separated from external links?
- Does the sanitizer handle browser parser semantics, malformed HTML, and CSS URL syntax?
- Is the library actively patched and tested against an attack corpus?
- Is the HTML protected against **mutation after sanitization**? Later component/JS transformations can reintroduce vulnerabilities if raw strings are appended afterward.
- Are caches invalidated when the policy or sanitizer version changes?

Never build your own regex sanitizer like stripping `<script>` substrings. Browsers parse HTML, SVG/MathML, comments, entities, malformed tags, URL protocols, and nested contexts in subtle ways; regexes are not reliable HTML parsers. If rich HTML isn't needed, **escaping as text** is simpler and safer.

### 9.2. Client-side sanitizers

In browsers, OWASP commonly recommends `DOMPurify` for HTML sanitization needs. Example:

```javascript
const sanitized = DOMPurify.sanitize(untrustedHtml);
richTextContainer.innerHTML = sanitized;
```

Use only with a patched version of `DOMPurify`, a tight allowlist configuration, and no unsafe post-sanitization mutations. With CSP Trusted Types, policies may need to return `TrustedHTML` cleanly. Never use `innerHTML` just for convenient plain-text rendering.

## 10. Template engines and frontend frameworks

### 10.1. Thymeleaf: `th:text` vs `th:utext`

Thymeleaf in Spring MVC provides HTML-escaped text output by default:

```html
<!-- SAFE for plain text: variable is HTML-escaped -->
<p th:text="${comment.body}">Content</p>
<input th:value="${user.displayName}" value="">
```

If `comment.body` contains `<` and `>`, `th:text` renders them as literal characters instead of markup. With `th:value`, the engine escapes attribute syntax, though **URL/CSS/event-handler attributes still need their own policies**.

```html
<!-- WARNING: th:utext is unescaped HTML -->
<div th:utext="${comment.body}"></div>
```

`th:utext` is for when you already have properly **sanitized rich HTML** per policy. Passing raw user content causes the browser to parse it as markup. Inlining syntax also differs:
- `[[${comment.body}]]`: escaped text.
- `[(${comment.body})]`: unescaped text.

**Never "fix" escaped HTML characters appearing in the UI by switching `th:text` to `th:utext` everywhere.** If rich text is required, sanitize properly and use unescaped rendering only on reviewed components.

### 10.2. React, Vue, Angular

Modern frontend frameworks generally **escape plain text bindings** by default:

- React: `<div>{comment.body}</div>` renders as text in normal JSX; `dangerouslySetInnerHTML` is a risky escape hatch.
- Vue: `{{ comment.body }}` renders escaped text; `v-html` injects HTML and requires sanitization.
- Angular: `{{ comment.body }}` applies context-aware sanitization/escaping; bypass methods like `bypassSecurityTrustHtml` must be carefully reviewed.

Framework auto-escaping is insufficient if code drops down to dangerous DOM APIs, unvalidated URLs, arbitrary HTML rendering, or dynamic script execution. **Never trust data solely because it came from an authenticated backend.**

### 10.3. JSP and Java servlet string templates

In JSP/JSTL, use standard JSP/tag-library output escaping; if writing raw HTML strings via servlet `out.write`, encode per context. OWASP Java Encoder provides distinct APIs for HTML text, attributes, JavaScript strings, and URI components; prefer maintained libraries over hand-rolled `replace` functions.

### 10.4. Server-Side Rendering (SSR) and hydration

When SSR renders HTML and the frontend hydrates, the same data may be embedded:
- In an HTML text node: requires HTML text encoding.
- In initial JSON state inside `<script>`: requires handling **both JSON and HTML script context**, or moving to a separate JSON endpoint.
- In HTML attributes: requires attribute encoding and URL validation where applicable.
- In the client DOM after hydration: use safe sinks.

**A value protected at one boundary does not stay protected if handed off to a different parser.**

## 11. Runnable Spring Boot 3.x / Java 17+ example

Let's build a small Spring MVC application:
- `GET /demo?name=...` returns HTML rendering `name` in **HTML text context**, **quoted HTML attribute context**, and a **URL query component inside `href`**.
- A static JS file uses `textContent` to display the same query parameter without `innerHTML`.
- `GET /search?q=...` and `GET /api/display-name?name=...` return JSON via Jackson instead of concatenating JSON strings.
- Spring Security permits the demo GET routes, denies all other routes, and adds **defense-in-depth CSP** to restrict inline script execution. CSP is not the primary substitute for encoding.
- MockMvc verifies the browser does not receive user-injected markup directly and verifies CSP headers.

### 11.1. Dependencies

Use Spring Initializr to create a Java 17+, **Spring Boot 3.x**, Gradle project with **Spring Web** and **Spring Security**. In the generated `build.gradle`, place this dependencies block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.owasp.encoder:encoder:1.6.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is a **dependencies block**, not the entire `build.gradle`: keep your project's plugins, repositories, Java version, and BOM. `org.owasp.encoder` is **OWASP Java Encoder**; version `1.6.0` is an official release from October 2026. If your project uses a custom BOM or security updates, pick a compatible patched version and test.

### 11.2. Application Java file

Create `src/main/java/example/xss/XssEncodingApplication.java`:

```java
package example.xss;

import java.util.Map;

import org.owasp.encoder.Encode;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class XssEncodingApplication {
    public static void main(String[] args) {
        SpringApplication.run(XssEncodingApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/demo", "/search", "/api/display-name",
                    "/js/**").permitAll()
                .anyRequest().denyAll())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "object-src 'none'; " +
                        "base-uri 'self'; " +
                        "frame-ancestors 'none'")))
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping(value = "/demo",
                produces = MediaType.TEXT_HTML_VALUE)
    String demo(@RequestParam(defaultValue = "") String name) {
        String safeHtmlText = Encode.forHtmlContent(name);
        String safeAttribute = Encode.forHtmlAttribute(name);
        String searchUrl =
            "/search?q=" + Encode.forUriComponent(name);
        String safeHref = Encode.forHtmlAttribute(searchUrl);

        return """
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="UTF-8">
              <title>Context-aware XSS encoding</title>
            </head>
            <body>
              <h1>Hello, %s</h1>
              <label>Raw value displayed safely:
                <input readonly value="%s">
              </label>
              <p><a href="%s">Search this name</a></p>
              <p id="domText"></p>
              <script src="/js/demo.js" defer></script>
            </body>
            </html>
            """.formatted(
                safeHtmlText, safeAttribute, safeHref);
    }

    @GetMapping("/search")
    Map<String, String> search(
            @RequestParam(defaultValue = "") String q) {
        return Map.of("query", q);
    }

    @GetMapping("/api/display-name")
    Map<String, String> displayName(
            @RequestParam(defaultValue = "") String name) {
        return Map.of("name", name);
    }
}
```

**Reading the code:**

1. `Encode.forHtmlContent(name)` handles the raw value placed inside `<h1>...`. Browsers display special characters as text without creating arbitrary elements.
2. `Encode.forHtmlAttribute(name)` handles input placed inside a **quoted** `value` attribute. Input is never used to choose element or attribute names.
3. `Encode.forUriComponent(name)` encodes only the `q` query value; `/search?q=` is fixed by the server. `Encode.forHtmlAttribute(searchUrl)` protects the URL when inserted into `href`.
4. `Map.of("name", name)` is serialized to JSON by Spring MVC/Jackson with the proper JSON MIME type via auto-configuration. It returns data rather than rendering HTML. If a frontend takes this JSON and passes it to `innerHTML`, the frontend can still cause XSS.
5. `SecurityFilterChain` only grants access to the demo GET routes; it does not escape input itself. `contentSecurityPolicy(...)` adds an HTTP response protection layer; encoders and safe DOM APIs remain mandatory.
6. `default-src 'self'` and `script-src 'self'` allow scripts from the same origin, which is not the strictest possible CSP for every app. CSP designs should consider nonces/hashes, third-party resources, reporting, `strict-dynamic`, Trusted Types, and compatibility.
7. The demo uses no DB, login page, or sessions for public GET requests. If adding login or user-generated content, also audit authorization and storage.

### 11.3. Standalone JavaScript file, no inline code

Create `src/main/resources/static/js/demo.js`:

```javascript
"use strict";

const params = new URLSearchParams(window.location.search);
const name = params.get("name") ?? "";
const target = document.getElementById("domText");

if (target) {
  // Data becomes plain text, not parsed as HTML.
  target.textContent = name;
}
```

Runs under CSP `script-src 'self'` because the file is served from the same origin. `textContent` does not need pre-applied HTML encoding; pass the raw string to the DOM text API. Never replace it with `target.innerHTML = name`.

The demo's CSP **does not include `'unsafe-inline'`**, so JavaScript runs from a static file rather than an inline `<script>...`. Never use `onclick`/`onerror` event attributes in production code.

### 11.4. Running and manual verification

In the project with Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Open locally:

```text
http://localhost:8080/demo?name=Alice
```

Expectations:
- The page displays `Hello, Alice`.
- The readonly input contains `Alice`.
- The link points to `/search?q=Alice`.
- The static script renders `Alice` in the `domText` paragraph.

To test special characters, let the browser URL-encode the query parameter (for example via DevTools or browser URI component encoding). **Never test attack payloads on real systems without explicit authorization.** Inspect the element tree: the string must appear as text, with no extra `<img>` or `<script>` elements created from the input.

### 11.5. Integration tests with MockMvc

Create `src/test/java/example/xss/XssEncodingApplicationTest.java`:

```java
package example.xss;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class XssEncodingApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void untrustedMarkupIsDisplayedAsHtmlText()
            throws Exception {
        String raw = "<img src=x onerror=alert(1)>";

        mvc.perform(get("/demo").param("name", raw))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.TEXT_HTML))
            .andExpect(result -> {
                String html = result.getResponse()
                    .getContentAsString();
                assertThat(html).contains("&lt;img");
                assertThat(html)
                    .doesNotContain("<img src=x onerror=");
            });
    }

    @Test
    void quotesCannotBreakQuotedAttribute() throws Exception {
        String raw = "\"><svg onload=alert(1)>";

        mvc.perform(get("/demo").param("name", raw))
            .andExpect(status().isOk())
            .andExpect(result -> {
                String html = result.getResponse()
                    .getContentAsString();
                assertThat(html)
                    .doesNotContain("value=\"\"><svg");
                assertThat(html).contains("value=\"");
            });
    }

    @Test
    void urlQueryComponentIsEncoded() throws Exception {
        mvc.perform(get("/demo").param("name", "a&b"))
            .andExpect(status().isOk())
            .andExpect(result -> {
                String html = result.getResponse()
                    .getContentAsString();
                assertThat(html)
                    .contains("/search?q=a%26b");
            });
    }

    @Test
    void jsonEndpointReturnsDataNotHtml() throws Exception {
        String value = "<img src=x onerror=alert(1)>";

        mvc.perform(get("/api/display-name")
                .param("name", value))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.name").value(value));
    }

    @Test
    void cspHeaderAddsDefenseInDepth() throws Exception {
        mvc.perform(get("/demo").param("name", "Alice"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; " +
                "object-src 'none'; base-uri 'self'; " +
                "frame-ancestors 'none'"));
    }

    @Test
    void maliciousPostIsNotAnAllowedRoute()
            throws Exception {
        mvc.perform(get("/unexpected"))
            .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Test matrix explanation:**

| Test | Expectation | Inferred limitation |
|---|---|---|
| Raw markup placed in HTML text | Status 200, contains `&lt;img`, lacks raw `<img ...>` | Proves server-side text encoding in the sample |
| Input starting with quote then markup | Attribute value is not broken out via raw quote | Proves quoted attribute encoding in the sample |
| Input containing `&` in query | `%26` in the link | Proves URL query component does not split into another parameter |
| JSON containing markup string | JSON preserves exact data, MIME `application/json` | Does not prove frontend handles JSON safely; frontend still needs safe DOM sinks |
| CSP header | Policy header present | Only proves header config, not that all XSS is blocked |
| Undeclared endpoint | 403 | Path denied; unrelated to XSS escaping |

**Note:** These tests do not replace browser security testing, static analysis, dependency audits, sanitizer fuzzing, system-wide CSP policy, or auditing all render points. If you change the OWASP Java Encoder version, exact entity representations may vary; focus on verifying **no executable markup is produced**. The code was statically reviewed against Spring Boot 3 / Security 6 conventions; run builds/tests in a real project to confirm exact version behavior.

## 12. CSP: a supplementary layer, not a replacement for escaping

**Content Security Policy (CSP)** is a response header instructing browsers to restrict script, style, object, frame, and certain other sources/behaviors. Example:

```http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
```

Without `'unsafe-inline'`, browsers can block many inline scripts and event handlers, reducing the impact of certain XSS payloads. However:
- A policy with just `script-src 'self'` still permits scripts from the same origin, which can be too broad if that origin hosts user-uploaded JS files.
- A misconfigured, missing, or overly permissive CSP can be bypassed depending on application conditions.
- CSP does not fix injected HTML syntax; attackers may still alter page content, links, or forms within browser limits.
- CSP does not replace sanitization when rendering rich HTML, nor does it replace URL protocol validation.
- Spring Security **does not generate a suitable CSP for every application**; developers must choose, implement, and test the policy.

For large apps, explore policies first with `Content-Security-Policy-Report-Only`, test, and then enforce; evaluate nonces/hashes, `strict-dynamic`, `object-src 'none'`, `base-uri`, and `frame-ancestors` per browser support. Never add `'unsafe-inline'` to silence errors without understanding the trade-off.

### 12.1. Trusted Types

In browsers supporting **Trusted Types**, the CSP directive `require-trusted-types-for 'script'` requires dangerous DOM sinks to receive typed values produced by an approved policy. This helps constrain `innerHTML` and certain HTML injection sinks. Yet a permissive policy that blindly returns raw strings negates the benefit; Trusted Types do not sanitize automatically. Check browser support and migration effort before broad rollout.

### 12.2. Remaining HTTP response headers

`X-Content-Type-Options: nosniff` reduces MIME sniffing in certain contexts. `X-Frame-Options` and `frame-ancestors` relate to clickjacking and framing. `Referrer-Policy` affects info sent in `Referer`. These headers are helpful, yet none turns raw user text into safe HTML text.

**Do not confuse legacy `X-XSS-Protection` with modern XSS defense**: legacy browser XSS filters are obsolete and not recommended as a primary strategy. The core remains contextual encoding, sanitization when needed, safe DOM APIs, and supplementary CSP.

## 13. XSS and CSRF differ, yet interact with each other

| Control | Goal | Limitation relative to XSS |
|---|---|---|
| Contextual output encoding | Prevent untrusted data from becoming active code in output | Must match exact context and cover all sinks |
| HTML sanitizer | Permit a restricted set of rich HTML | Policy must be maintained; post-sanitization edits can introduce bugs |
| CSP | Reduce execution/loading of unauthorized scripts/resources | Does not fix raw HTML rendering flaws |
| `HttpOnly` cookie | Restrict JS from reading cookie values directly | XSS scripts can still send requests carrying cookies |
| `SameSite` cookie | Limit some cross-site cookie requests | Does not block scripts running on the legitimate origin |
| CSRF token | Defend against forged cross-site requests with auto-sent credentials | Same-origin XSS can read and submit tokens |
| CORS | Control whether cross-origin browser JS reads responses | Does not prevent same-origin XSS |
| Input validation | Enforce valid format/business rules | Does not replace output encoding |
| Authorization | Whether a user may access a specific resource | XSS can act within the victim's granted permissions |
| Prepared statements | Prevent SQL injection | Do not encode data for HTML/JS |

**Consequence:** If a page has XSS, an attacker can invoke endpoints and submit the page's CSRF token as a valid request. Enabling CSRF does not make XSS disappear. Conversely, escaping output reduces XSS risk, but does not replace CSRF protection for cookie-authenticated unsafe browser requests.

## 14. Security review for special locations

### 14.1. URLs in `href`/`src`

If a value is an absolute URL, **verify both scheme and destination**. When inserting into HTML source, still attribute-encode after validation. For user-submitted links, perhaps allow only `https`; for image sources, perhaps allow only trusted CDNs. Watch out for URLs starting with `//`, backslashes, protocol-relative URLs, and multi-pass URL decoding if proxies/rewriters sit in front.

### 14.2. DOM data attributes

`data-id` may hold a properly attribute-encoded untrusted string, yet if JavaScript reads `dataset.id` and passes it into `innerHTML`, a **new sink** appears. Data does not stay "immune" just because it previously sat safely inside an attribute.

### 14.3. SVG, MathML, templates, and iframes

SVG/MathML have distinct syntax and attributes that can involve scripting and foreign content. Never insert raw user SVG into the DOM. `iframe.srcdoc` is an HTML document context; `sandbox` can restrict privileges but does not replace content sanitization. For email templates, PDF/HTML renderers, and Markdown-to-HTML converters, enforce each renderer's own policy and defend against HTML injection.

### 14.4. File uploads and filenames

Filenames can be client-controlled; if displayed in an HTML table, encode them. If users can upload HTML/SVG served from the same origin as app session cookies, other users can view active content from a trusted origin. Enforce content-type, `Content-Disposition`, a separate asset origin/sandbox, file scanning, and download policies. Filtering characters in filenames at upload time does not protect every place filenames get rendered.

### 14.5. HTML in API errors and log viewers

Error messages can echo request paths or parameters. If an error page concatenates messages into HTML or an admin log viewer uses `innerHTML` to display logs, XSS can still occur. Treat error pages, audit dashboards, analytics, email previews, Markdown renderers, and backoffice tools as full output sinks.

### 14.6. Localization and rich content

Text from localization bundles is generally treated as team-managed trusted data, yet **interpolated parameter values** (usernames, comments) remain untrusted. If a team-authored message contains HTML, only the untrusted parameter variables inside it need context-appropriate encoding; avoid enabling unescaped rendering across the entire message containing raw parameters.

### 14.7. Caching and multi-tenancy

A page with user-specific data stored in a shared cache can leak information even when properly escaped; that is a separate flaw from XSS. Still, when caching rendered HTML fragments, ensure values are encoded for the exact target context and keyed properly by tenant/user. Never take an HTML-encoded fragment and embed it into JavaScript source merely because it was "already safe earlier."

## 15. Debugging XSS by source, path, and sink

### Step 1: Identify data sources

Does data arrive from query/body/headers, DB, files, third-party APIs, `postMessage`, `localStorage`, or URL fragments? Do not rely on field names like `safeContent`. Even an admin-saved comment can hold unintended HTML.

### Step 2: Identify the final parser/sink

Is the content:
- Concatenated into an HTML response?
- Passed to `th:text` or `th:utext`?
- Assigned to `innerHTML`/`textContent`?
- Placed in `href`, `src`, `style`, or an event handler?
- Placed inside an inline `<script>` or JSON?
- Rendered by a Markdown/WYSIWYG plugin?

**Choose the encoder/sanitizer based on the sink, not based on the source data.**

### Step 3: Verify the encoding's effect

If only plain text is needed, `<tag>` must display literally as text and **never create a new `tag` DOM element**. For attributes, quotes in input must never create new attributes. For URLs, input must not alter destination or scheme. For JS, input must not alter script structure. For CSS, input must not break out of the restricted property/value.

### Step 4: Inspect both SSR and client updates

The initial SSR response might be properly escaped, while client JS later fetches data and passes it to `innerHTML`. Use browser DevTools, source review, lint rules, DOM sink scanning, and security tests to inspect the final sink. Never conclude "server HTML is safe so all state updates are safe."

### Step 5: Evaluate defense-in-depth

Check whether CSP headers are complete, whether `unsafe-inline` is present, whether Trusted Types fit, how cookie flags and authorization are designed, and whether uploaded HTML/SVG is served on the same origin. These reduce risk, yet never replace fixing sinks.

## 16. Common mistakes and fixes

| Anti-pattern | Actual flaw | Replacement |
|---|---|---|
| `"<p>" + input + "</p>"` | Raw input becomes HTML markup | `Encode.forHtmlContent` or template-escaped text |
| `<input value=...>` unquoted | Easy to inject extra attributes | Keep quoted value + attribute encoding |
| `th:utext` with user comment | Parses raw HTML | `th:text` or sanitized rich HTML |
| `innerHTML = input` for plain text | DOM XSS | `textContent = input` |
| `eval(JSON)` | Data executed as JavaScript | `response.json()` / `JSON.parse` |
| Only `replace("<", "&lt;")` | Ignores parser/context rules | OWASP Java Encoder / autoescape |
| Component-encoding a full URL without validation | Allows dangerous URL schemes/destinations | Parse/allowlist scheme/host, encode components |
| HTML-escaping data inside inline JS | Wrong parser context | Avoid inline JS or use appropriate JS block encoder |
| HTML-escaping data before `textContent` | Displays double-escaped entities | Pass raw data to safe DOM text sinks |
| Regex sanitizer | Fails on malformed HTML/parsers | OWASP Java HTML Sanitizer or DOMPurify |
| CSP as the sole defense | Can be bypassed, DOM still alterable | Encode/sanitize + CSP |
| `HttpOnly` or CSRF token instead of XSS defense | Same-origin scripts can still act | Fix output sinks |
| Adding `unsafe-inline` to make app work | Weakens CSP | Refactor to static JS / nonces / hashes |
| Trusting all data from authenticated APIs | APIs can carry stored XSS | Encode at frontend render time |
| Checking "input has no `<script>`" | Misses event handlers, SVG, attributes | Contract validation + contextual encoding |
| Serving JSON as `text/html` | Browser may misinterpret context | Standard serializer + proper MIME type |
| Uploading HTML/SVG and serving same-origin | Active content runs on trusted origin | File validation, isolated origin / download policy |
| Single `escapeHtml` helper for JS/CSS/URL | Wrong parser contexts | Dedicated APIs per sink |
| Testing only visible text on page | Misses injected DOM elements | Inspect DOM and run negative browser tests |

## 17. Checklist for code review and CI

### HTML/templates

- [ ] Every display of user-generated text uses escaped output or safe DOM APIs.
- [ ] No raw `th:utext`/`dangerouslySetInnerHTML`/`v-html` on unsanitized untrusted content.
- [ ] Normal text attribute values are always quoted and encoded for attribute context.
- [ ] URL attributes undergo scheme/destination validation before HTML attribute encoding.
- [ ] Untrusted input is never used as element names, attribute names, event handlers, or script sources.
- [ ] HTML sanitizers are used only when rich text is needed, with explicit policies and maintained libraries.
- [ ] Input validation enforces business rules rather than being mistaken for XSS encoding.

### JavaScript/DOM

- [ ] No `innerHTML`/`outerHTML`/`insertAdjacentHTML` with raw user strings.
- [ ] Prefer `textContent`, `createTextNode`, and safe property assignments for data.
- [ ] Never use `eval`/`new Function` to parse JSON or user input.
- [ ] Data embedded in `<script>` is eliminated or encoded for JS block + enclosing HTML context.
- [ ] Dynamic CSS styles use fixed properties + allowlisted values only.
- [ ] SPA/SSR/hydration are treated as multiple boundaries rather than one-time escaping.
- [ ] Trusted Types policies do not blindly pass through raw strings when enabled.

### Defense-in-depth

- [ ] CSP is configured for the real app with testing/reporting, without relying on `unsafe-inline`.
- [ ] `HttpOnly`, `Secure`, `SameSite` cookies are properly set, recognizing they do not block same-origin XSS.
- [ ] CSRF protection remains active for cookie-based unsafe browser requests.
- [ ] Role/tenant/ownership authorization does not depend on HTML escaping.
- [ ] Uploaded active content never runs on the app's primary origin.
- [ ] JSON uses proper Content-Type and the frontend never parses JSON as code.
- [ ] Logs, error pages, admin dashboards, and rich text views are all reviewed.

### Testing

- [ ] MockMvc tests verify raw tags like `<img>` do not become executable markup.
- [ ] Tests verify quotes cannot break out of attribute values.
- [ ] Tests verify `&` and `#` in URL queries do not alter URL structure.
- [ ] Tests verify JSON serializers return proper data/MIME without string concatenation.
- [ ] Browser DOM tests verify query/hash/`postMessage` inputs create no injected elements.
- [ ] Sanitizer tests cover malformed HTML, SVG/MathML, URL protocols, and HTML entities.
- [ ] Tests verify CSP headers on HTML responses alongside production policies in browsers.
- [ ] Tests cover both plain strings and Unicode/emoji to detect double encoding.
- [ ] Regression tests run after upgrading templates, frameworks, encoders, or sanitizers to catch semantic changes.

## 18. Self-check exercises

**Question 1.** A controller requires login and checks `hasAuthority('DOC_READ')`, yet concatenates `comment.body` into an HTML string without escaping. Has Spring Security prevented XSS?

**Answer:** No. Login/authorization govern who calls the endpoint, whereas how data is rendered into HTML is controlled by the template/controller. Escape for HTML text context or sanitize if rich HTML is required.

**Question 2.** Input `<b>hello</b>` is passed to `th:text` vs `th:utext`. What is the difference?

**Answer:** `th:text` escapes so browsers display `<b>hello</b>` literally as text; `th:utext` passes markup to the browser to parse. Use `th:utext` with user HTML only after an appropriate sanitizer.

**Question 3.** Does `element.textContent = rawValue` need `Encode.forHtmlContent` called first?

**Answer:** No. On standard HTML text elements, `textContent` creates a text node directly. Pre-encoding causes the UI to display literal `&lt;` instead of `<`.

**Question 4.** `Encode.forHtmlAttribute` was applied to an `href` containing `javascript:...`. Is the link automatically safe?

**Answer:** No. Attribute encoding protects HTML syntax, not dangerous URL schemes. Validate the scheme/destination first, then attribute-encode at render time.

**Question 5.** A username variable was JSON-serialized and then concatenated directly into an inline `<script>`. Is that safe?

**Answer:** Not necessarily. A JSON serializer produces JSON, while the browser parses an **HTML script context**. Handle both contexts properly or move to a dedicated `application/json` endpoint fetched by JS.

**Question 6.** Why don't `SameSite` or `HttpOnly` replace XSS protection?

**Answer:** XSS running on the app's own origin can manipulate the DOM, read UI data, and issue requests carrying browser-attached cookies. Cookie flags mitigate some impacts but do not prevent script injection.

**Question 7.** A product needs users to enter bold text and links. Escaping all HTML breaks formatting. What should be done?

**Answer:** Use an allowlist-based sanitizer for tags/attributes/protocols such as OWASP Java HTML Sanitizer or DOMPurify, and render rich HTML only at reviewed sites; never write regexes to strip dangerous tags.

**Question 8.** The CSP header has `script-src 'self'` without `unsafe-inline`. Can we stop encoding output?

**Answer:** No. CSP is defense-in-depth; the application must still encode/sanitize at output. Policy effectiveness also depends on the whole origin, external scripts, browser support, and specific configurations.

**Question 9.** The same raw string goes into an HTML `<p>` and a URL query. Can one escaping function serve both?

**Answer:** No. `<p>` requires HTML text encoding, whereas the query requires percent-encoding for the **component** followed by HTML attribute encoding if placed inside `href`.

**Question 10.** The database stores a comment after running an HTML encoder, and the frontend then uses `textContent`. Is this right?

**Answer:** Encoding too early for one context and then passing to a safe DOM sink can cause double encoding. Prefer storing raw domain data with business validation and encoding at the respective output boundary.

## 19. Official references and practice standards

- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): HTML/attribute/JavaScript/CSS/URL contexts, HTML sanitization, safe sinks, and supplementary defenses.
- [OWASP — DOM based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html): DOM sources/sinks, parser contexts, and APIs to avoid.
- [OWASP Java Encoder — Contextual Output Encoding](https://owasp.org/projects/java-encoder): `forHtmlContent`, `forHtmlAttribute`, `forUriComponent`, `forJavaScriptBlock`, and context notes.
- [OWASP Java HTML Sanitizer](https://owasp.org/projects/java-html-sanitizer): `PolicyFactory`, `Sanitizers`, and allowlist policies.
- [Thymeleaf 3.1 — Tutorial: Escaped vs Unescaped Text](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html): `th:text`, `th:utext`, `[[...]]`, and `[(...)]`.
- [Spring Security — HTTP Security Response Headers / CSP](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): CSP and the boundaries of HTTP response headers.
- [MDN — Element.textContent](https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent): DOM text sink and differences from `innerHTML`.
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP): directives, browser behavior, and script sources.
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): deploying CSP as defense-in-depth.

**Remember:** For untrusted data, ask **"Which parser does this value enter?"** before choosing a defense. HTML text → HTML text encoding or safe DOM text APIs. HTML attribute → quotes + attribute encoder. URL → build from a trusted base, encode each component, validate scheme/host, then attribute-encode if rendered in HTML. JavaScript/CSS → avoid raw insertion, use controlled APIs. Rich HTML → allowlist-based sanitizer. Spring Security and CSP provide mitigation support, yet **never replace context-aware output handling**.
