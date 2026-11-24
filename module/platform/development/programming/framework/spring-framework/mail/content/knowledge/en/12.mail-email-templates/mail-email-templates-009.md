# Contextual Escaping for HTML, URLs, and Text

## 1. Why Escape According to Context?

In **Spring Framework Mail**, applications often take data from users or business systems and place it into email templates: recipient names, product names, order numbers, verification links, subjects, and notification bodies. Inserting dynamic data into HTML directly allows special characters to break email structure or turn data into unintended markup.

Example:

~~~java
String displayName = "<img src=x onerror=alert(1)>";
String html = "<p>Hello " + displayName + "</p>";
~~~

The `displayName` string was merely data, yet after concatenating it into HTML, it becomes an HTML tag. Mail clients often filter dangerous HTML, but **you must never rely on mail client filters to protect your email-generation system**.

Another example is URLs:

~~~java
String token = "abc&next=https://attacker.example";
String href = "https://accounts.example.com/verify?token=" + token;
String html = "<a href=\"" + href + "\">Verify</a>";
~~~

The `&` character in the token may be interpreted as a query parameter separator. If the URL is placed into the `href` attribute without HTML attribute escaping, quotes or special characters can alter the markup.

Therefore, you need to understand **contextual output encoding**: the same input value may require different handling depending on where it is placed:

- HTML text node: content between two tags.
- HTML attribute: value of `href`, `title`, `alt`, or another attribute.
- URL component: a path segment or a query parameter.
- Plain-text email: plain-text content, not HTML.
- Other contexts such as CSS or JavaScript: require their own rules; it is best to avoid putting untrusted data into these contexts.

> **Principle:** Identify where the data will appear, validate/normalize according to that location's rules, and then encode at the final output step. There is no single "escape everything" function safe for every context.

## 2. Distinguishing Escape, Encode, Validate, and Sanitize

| Concept | Purpose | Example |
| --- | --- | --- |
| **Escape / output encoding** | Represent data so the target context's parser does not mistake data for syntax | `<` to `&lt;` in HTML text |
| **URL component encoding** | Encode characters of a URL component per URI rules | Query value containing `&` is encoded so it does not create a new parameter |
| **Validation** | Check whether data falls within allowed values or policies | Accept only `https` links to approved domains |
| **Normalization** | Bring data to a canonical form per business requirements | Normalize line endings or order-code formatting |
| **Sanitization** | Remove or transform disallowed structures inside markup content | Allow a safe HTML subset when the product supports rich text |

URL-encoding a string does not mean that URL is safe to navigate to. `javascript:alert(1)` remains a disallowed scheme even if characters have been encoded in some way. Similarly, HTML-escaping an HTML snippet is not sanitization if the goal is allowing certain tags like `<strong>` and `<a>` to render.

### 2.1. Escape Data at Output Time

1. Store business data in normal raw data form; do not store an HTML-escaped version as the source data.
2. When rendering a template, identify the context of each variable.
3. Use a template engine or appropriate encoder to encode for the right context.
4. Do not escape again if the template engine already auto-escapes.

Raw data example:

~~~text
R&D <North>
~~~

When placed into HTML text, it can be serialized as:

~~~html
R&amp;D &lt;North&gt;
~~~

Recipients still see `R&D <North>`. Storing `R&amp;D &lt;North&gt;` as the source data easily leads to double escaping and makes it hard to reuse the same data in plain text, CSV, or other UIs.

## 3. Escaping HTML Text Nodes

An **HTML text context** is the content region between an opening tag and a closing tag:

~~~html
<p>Dynamic value appears here</p>
~~~

Key characters that must be represented safely:

| Data Character | Common HTML Representation |
| --- | --- |
| `&` | `&amp;` |
| `<` | `&lt;` |
| `>` | `&gt;` |
| Double quote `"` | Can be represented as `&quot;` |
| Single quote `'` | Can be represented as `&#39;` or a corresponding entity |

Example:

~~~text
Lan <Admin> & "Support"
~~~

is inserted into HTML as:

~~~html
<p>Lan &lt;Admin&gt; &amp; &quot;Support&quot;</p>
~~~

Mail clients display the original characters as text; they are no longer parsed as HTML tags or syntax.

### 3.1. Using Thymeleaf for Automatic Text Escaping

If emails are rendered with Thymeleaf, prefer `th:text` for text data:

~~~html
<p th:text="${displayName}">
  Recipient name
</p>
~~~

`th:text` replaces the element's content with the HTML-escaped value. If `displayName` is `<img src=x onerror=alert(1)>`, that string is displayed as text instead of creating an image tag.

Template example:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <p>Hello <strong th:text="${displayName}">there</strong>,</p>
  <p>
    Order
    <span th:text="${orderNumber}">A-100</span>
    has been confirmed.
  </p>
</body>
</html>
~~~

This is appropriate for names, order numbers, and ordinary business strings. Do not call an escape function in Java and then pass the result into `th:text`, as that can cause **double escaping**.

### 3.2. Using an Explicit Encoder When Building HTML Manually

If Java code must concatenate an HTML snippet, use a dedicated encoder library. Example with **OWASP Java Encoder**:

~~~java
import org.owasp.encoder.Encode;

String displayName = "<img src=x onerror=alert(1)>";
String safeText = Encode.forHtml(displayName);
String html = "<p>Hello " + safeText + "</p>";
~~~

`Encode.forHtml(...)` is for HTML text context. Do not write your own function replacing a few characters with `String.replace(...)` and treat it as a complete encoder: replacement order, quote characters, Unicode, and differing contexts are easily missed.

## 4. Escaping HTML Attributes

An **HTML attribute context** occurs when data is placed inside an attribute value:

~~~html
<a href="...">Open link</a>
<img src="..." alt="...">
<td title="...">...</td>
~~~

Attribute values should always be quoted. If data contains double quotes and is concatenated directly:

~~~java
String title = "\" onmouseover=\"alert(1)";
String html = "<a title=\"" + title + "\">View</a>";
~~~

the string can terminate the `title` attribute early and inject another attribute. Encode for **HTML attribute context**:

~~~java
String safeTitle = Encode.forHtmlAttribute(title);
String html = "<a title=\"" + safeTitle + "\">View</a>";
~~~

The encoder represents quotes and special characters with appropriate entities. Always wrap attribute values in quotes even when current data appears alphanumeric.

### 4.1. Thymeleaf Automatically Escapes Ordinary Attributes

~~~html
<a th:title="${displayTitle}">View details</a>
<img th:alt="${imageDescription}" src="/mail/logo.png">
~~~

Thymeleaf handles attribute values via the template engine's escaping mechanism. Do not concatenate strings into HTML attributes in Java if you can use a template engine with safe binding.

### 4.2. HTML Attribute Encoding Does Not Replace Validation

~~~html
<a href="...">...</a>
<div style="...">...</div>
<button onclick="...">...</button>
~~~

`href` has URL navigation semantics; `style` is CSS; `onclick` is JavaScript. Each context has its own parser and risks. A string encoded for an HTML attribute can still carry an unsafe scheme in `href` or dangerous CSS values in `style`. Never put untrusted data into event handlers or dynamic styles.

## 5. URL Encoding: Encoding Each Component

A URL has a structure consisting of scheme, authority/host, path, query, and fragment. When dynamic data appears in a URL, determine whether it is a **path segment** or a **query parameter value**.

~~~text
https://accounts.example.com/verify?token=abc123
                                      ^^^^^^
                                      query parameter value
~~~

If the token has characters like `&`, `=`, `+`, spaces, or Unicode, direct string concatenation can change the URL's meaning. Encode the **component** using a URI builder API:

~~~java
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;

String token = "abc&next=hello world";

String verificationUrl = UriComponentsBuilder
        .fromUriString("https://accounts.example.com/verify")
        .queryParam("token", "{token}")
        .encode()
        .buildAndExpand(Map.of("token", token))
        .toUriString();
~~~

`{token}` is a URI template variable. `encode()` and `buildAndExpand(...)` encode the variable value using component-appropriate rules rather than letting `&` in the token become a new query parameter.

For data inside a path, use a path segment instead of concatenating onto the path:

~~~java
String documentId = "report/2026 & final";

String documentUrl = UriComponentsBuilder
        .fromUriString("https://files.example.com")
        .pathSegment("documents", "{id}")
        .encode()
        .buildAndExpand(Map.of("id", documentId))
        .toUriString();
~~~

`pathSegment` treats the value as a single segment; a `/` inside the data is not turned into a new path level.

### 5.1. URL Encoding Does Not Verify a Safe Destination

Examples of values to examine:

~~~text
javascript:alert(1)
https://trusted.example/path
https://trusted.example.attacker.invalid/path
//attacker.invalid/path
data:text/html,...
~~~

Merely URL-encoding **does not** decide which URLs are allowed. If the application sends emails with links, enforce **validation/allowlisting** for destinations:

- Accept only allowed schemes, usually `https`; allow `http` only if explicitly required.
- Validate the exact hostname against an allowlist; never use substring checks like `contains("trusted.example")`.
- Consider port, user-info, fragment, and protocol-relative URLs if they affect policy.
- If a link must point to the system's domain, build it from a trusted base URL in configuration rather than accepting an entire URL from clients.
- Disallow schemes such as `javascript:`, `data:`, or `file:` as link targets.

Example validating a parsed URL:

~~~java
import java.net.URI;
import java.util.Set;

private static final Set<String> ALLOWED_HOSTS =
        Set.of("accounts.example.com", "www.example.com");

static URI requireAllowedHttpsUrl(String value) {
    URI uri = URI.create(value);
    String scheme = uri.getScheme();
    String host = uri.getHost();

    if (!"https".equalsIgnoreCase(scheme)
            || host == null
            || !ALLOWED_HOSTS.contains(host.toLowerCase())) {
        throw new IllegalArgumentException("URL destination is not allowed");
    }
    if (uri.getUserInfo() != null) {
        throw new IllegalArgumentException("URL user-info is not allowed");
    }
    return uri;
}
~~~

This is a minimal allowlist for HTTPS links with a fixed host. A real system also needs port, path, redirect, and internationalized domain policies matching business rules. URL validation in an email application primarily prevents sending links to unintended destinations; if the application **fetches URLs from the server**, SSRF risks and separate DNS/IP/redirect checks must also be handled.

### 5.2. URL Encoding and HTML Attribute Encoding Are Two Distinct Steps

When building links in an HTML email:

1. **Validate destination**: are the scheme/host/path allowed?
2. **Build URL**: place each value into the right path/query component with a URI builder.
3. **HTML attribute encode**: when placing the complete URL into `href`, encode it for HTML attribute context.

Example using OWASP Java Encoder:

~~~java
String url = verificationUrl; // Trusted base URL, query param already encoded.
String safeHref = Encode.forHtmlAttribute(url);
String html = "<a href=\"" + safeHref + "\">Verify account</a>";
~~~

**URL component encoding** handles URL structure; **HTML attribute encoding** protects markup syntax. One step does not replace the other.

### 5.3. Do Not Arbitrarily HTML-Escape First and URL-Encode Afterward

~~~text
token = abc&next=home
~~~

If you HTML-escape the string first, you get `abc&amp;next=home`. Passing that into a query builder can make the URL carry `&amp;` instead of the original `&`. The right order is to **build/encode the URL from raw data first**, then HTML-attribute-encode the resulting URL when embedding it into markup.

In template engines that handle URL expressions and HTML attributes automatically, let the template engine perform both steps via its API; do not pre-encode variables and pass them into another URL expression.

## 6. Using URL Expressions in Thymeleaf Email Templates

Thymeleaf provides **link expressions** to construct URLs and attach parameters:

~~~html
<a th:href="@{https://accounts.example.com/verify(token=${token})}">
  Verify account
</a>
~~~

Thymeleaf builds the URL from the expression and encodes parameters via its URL expression mechanism. The value is then written into the HTML attribute via the template engine's escaping mechanism. This is better than concatenating URL strings inside the template.

For a URL already built and validated by the backend, you can use:

~~~html
<a th:href="${verificationUrl}">Verify account</a>
~~~

Thymeleaf still escapes the attribute value when rendering, but **does not replace destination validation**. If `verificationUrl` comes from untrusted data, the backend must validate scheme/host and link policy before putting it into the model.

### 6.1. Complete Template Example

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <p>
    Hello
    <strong th:text="${displayName}">there</strong>,
  </p>
  <p>Your verification request has been created.</p>
  <p>
    <a th:href="@{https://accounts.example.com/verify(token=${token})}">
      Verify account
    </a>
  </p>
</body>
</html>
~~~

`displayName` is text so `th:text` is used. `token` is placed into the query parameter via a URL expression. The host `accounts.example.com` is a fixed domain determined by the trusted application, not an arbitrary user-supplied URL.

If the email has both HTML and plain text, generate two semantically equivalent versions. The plain version can print the full URL, while the HTML version uses a labeled link:

~~~text
Hello Lan,

Verify your account at:
https://accounts.example.com/verify?token=...
~~~

Do not send only HTML and let clients auto-generate the text version; automatic conversion may strip context or important link labels.

## 7. Text in Plain-Text Emails: Do Not HTML-Escape

A `text/plain` email is not parsed as HTML. Therefore, if the user content is:

~~~text
R&D <North> "Support"
~~~

the plain-text version should keep it verbatim:

~~~text
R&D <North> "Support"
~~~

Do not turn it into:

~~~text
R&amp;D &lt;North&gt; &quot;Support&quot;
~~~

In Spring Mail:

~~~java
helper.setText(plainText, false);
~~~

`false` declares the body as plain text. There is no need to call `Encode.forHtml(...)` for `plainText`.

### 7.1. Generating Plain Text and HTML from the Same Data

~~~java
String displayName = "Lan <Admin>";
String verificationUrl = trustedVerificationUrl;

String plainText = """
        Hello %s,

        Verify your account at:
        %s
        """.formatted(displayName, verificationUrl);
~~~

For plain text, `<` in a user's name is just a character. The URL still needs to be constructed/validated at the URL layer; plain text does not need HTML attribute encoding.

The HTML part must be encoded separately:

~~~java
String html = "<p>Hello "
        + Encode.forHtml(displayName)
        + "</p><p><a href=\""
        + Encode.forHtmlAttribute(verificationUrl)
        + "\">Verify account</a></p>";
~~~

`verificationUrl` is assumed to be built from a trusted base URL with query parameters already encoded. `Encode.forHtmlAttribute` only handles embedding the URL into the HTML attribute.

### 7.2. Handling Newlines in User Content

Plain text preserves newlines according to business content. HTML collapses consecutive whitespace by default display rules, so controlled conversion is needed:

~~~java
String normalized = userMessage
        .replace("\r\n", "\n")
        .replace('\r', '\n');

String escaped = Encode.forHtml(normalized);
String htmlBody = "<p style=\"white-space:pre-wrap;\">"
        + escaped
        + "</p>";
~~~

`white-space:pre-wrap` is used to preserve line breaks and spaces in supporting clients. If broader compatibility is needed, you can convert newlines to `<br>` **after escaping the text**, or create separate `<p>` paragraphs. Do not replace newlines with HTML first and then escape everything, because `<br>` tags created by the application would also turn into literal text.

Another pipeline:

~~~java
String normalized = userMessage
        .replace("\r\n", "\n")
        .replace('\r', '\n');
String escaped = Encode.forHtml(normalized);
String htmlBody = "<p>" + escaped.replace("\n", "<br>") + "</p>";
~~~

`<br>` is fixed markup created by the application; the user text was escaped beforehand. This is how line breaks are represented, not permission for users to supply HTML.

### 7.3. Text Body Differs from Email Headers

Do not confuse a plain-text body with header fields such as `Subject`, `From`, `To`, or `Reply-To`. Headers have their own syntax and can be affected by newline characters.

For subjects taken from user data:

- Limit length per business rules.
- Strip or reject CR/LF control characters if disallowed.
- Use `MimeMessageHelper.setSubject(...)` or Jakarta Mail APIs instead of concatenating raw header lines.
- Never put arbitrary strings into `addHeader(...)` without validating header name and value.

~~~java
static String requireSingleLineSubject(String value) {
    if (value == null || value.length() > 180
            || value.indexOf('\r') >= 0
            || value.indexOf('\n') >= 0) {
        throw new IllegalArgumentException("Invalid email subject");
    }
    return value;
}

helper.setSubject(requireSingleLineSubject(subject));
~~~

This is example validation; length limits and content rules must be tuned for the product. Jakarta Mail performs its own header encoding and syntax checks, yet validating business data before placing it into headers remains essential.

## 8. Do Not Put Untrusted Data into CSS or JavaScript

Escaping HTML text or HTML attributes does not automatically make a value safe CSS or JavaScript. Avoid examples like:

~~~java
String html = "<div style=\"color:" + userColor + "\">Notification</div>";
String html2 = "<button onclick=\"" + userAction + "\">Open</button>";
~~~

`userColor` is placed into a **CSS value context**; `userAction` is placed into a **JavaScript context**. Merely HTML-escaping these two strings does not adequately address CSS/JavaScript parsers.

### 8.1. Use an Allowed Set of Values Instead of Dynamic CSS

~~~java
enum StatusStyle {
    SUCCESS("color:#166534; background-color:#dcfce7;"),
    WARNING("color:#92400e; background-color:#fef3c7;"),
    ERROR("color:#991b1b; background-color:#fee2e2;");

    private final String inlineStyle;

    StatusStyle(String inlineStyle) {
        this.inlineStyle = inlineStyle;
    }

    public String inlineStyle() {
        return inlineStyle;
    }
}
~~~

The application parses the input value into a valid enum and picks a style controlled by code. If the value does not match the enum, use a safe fallback or reject the request.

In templates, you can pick a fixed class:

~~~html
<p th:classappend="${status == 'SUCCESS'} ? 'status-success' : 'status-neutral'"
   th:text="${statusLabel}">
  Status
</p>
~~~

`statusLabel` remains text and uses `th:text`. The CSS class is chosen from application-defined branches rather than accepting arbitrary CSS strings directly.

### 8.2. Avoid Event Handlers and JavaScript in Emails

Do not build emails relying on:

~~~html
<a href="#" onclick="doSomething()">Click here</a>
<script>...</script>
~~~

Many mail clients strip scripts/event handlers. Emails should use HTTPS links to a web page that performs the action after appropriate user authentication. Do not put dynamic data into scripts, event handlers, or CSS properties trying to create interactivity.

## 9. When Should HTML Be Sanitized Instead of Escaped?

There are two distinct requirements:

**Requirement A — Display data as text.** If a user enters `<strong>Hello</strong>` and the product only wants to display that literal string, use HTML text escaping. Recipients see the tag characters as part of the text.

**Requirement B — Allow a rich-text subset.** If the product allows users to format bold text, links, or lists, full HTML escaping destroys the intended markup. In that case, an **allowlist-based HTML sanitizer** is needed to keep only allowed tags/attributes/protocols.

A rich-text policy might allow:

- Simple tags such as `p`, `strong`, `em`, `ul`, `ol`, and `li`.
- `a` links only with a validated `href` attribute.
- Certain necessary formatting attributes.
- Only allowed URL schemes, usually `https` or `mailto` as required.

Strip scripts, event handlers, iframes, objects, forms, arbitrary CSS, and unnecessary attributes. Libraries such as **OWASP Java HTML Sanitizer** or **jsoup Safelist** can help build allowlists; configure explicit policies rather than enabling a mode that allows all HTML.

### 9.1. Escaping and Sanitization Produce Different Outputs

Input:

~~~html
<p>Hello <strong>Lan</strong></p>
<script>alert(1)</script>
~~~

If **fully escaped** for HTML text, recipients see the literal tag syntax as text. If **allowlist-sanitized**, the output can preserve:

~~~html
<p>Hello <strong>Lan</strong></p>
~~~

while removing scripts. The second approach is only appropriate when business logic intentionally permits rich text. Sanitized data must still be placed into **the proper HTML body context**, not reused as attribute values, URLs, CSS, or JavaScript.

### 9.2. Thymeleaf th:text and th:utext

In Thymeleaf:

- `th:text` escapes text content.
- `th:utext` inserts **unescaped** content (unescaped text).

~~~html
<p th:text="${comment}">Comment content</p>
<div th:utext="${sanitizedRichText}"></div>
~~~

`th:utext` may only be used if `sanitizedRichText` was processed by a sanitizer with an appropriate policy and was not modified after sanitization. Never use `th:utext` with arbitrary user-entered comments.

**Sanitization does not replace output encoding in other contexts.** An HTML snippet safe in the body does not automatically become a safe URL in `href` or safe CSS in `style`.

## 10. Integrating Templates Safely with JavaMailSender

An email-sending service can divide responsibilities into:

1. **Business layer** determines recipients, data, and permissions to perform the action.
2. **URL layer** builds links from a trusted base URL and encoded components.
3. **Template engine** places data into the right context and automatically escapes HTML text/attributes.
4. **Spring Mail** creates the MIME message and sends HTML together with plain text.

Example service using Thymeleaf:

~~~java
package com.example.mail;

import java.util.Locale;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class VerificationEmailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;

    public VerificationEmailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
    }

    public void send(
            String recipient,
            String displayName,
            String verificationUrl) throws MessagingException {

        // URL must be built from a trusted base URL, encoded query,
        // and validated destination.
        Context context = new Context(Locale.forLanguageTag("vi"));
        context.setVariable("displayName", displayName);
        context.setVariable("verificationUrl", verificationUrl);

        // Template uses th:text and th:href; do not use th:utext
        // for arbitrary text data.
        String html = templateEngine.process(
                "mail/verification", context);

        String plainText = """
                Hello %s,

                Verify your account at:
                %s
                """.formatted(displayName, verificationUrl);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Verify your account");
        helper.setText(plainText, html);
        mailSender.send(message);
    }
}
~~~

The example requires configuring `TemplateEngine`, template resources, sender, and sender addresses per application. `verificationUrl` must be built/validated before entering the context; `displayName` is untrusted text so the template uses `th:text`. `MimeMessageHelper` does not sanitize templates or validate destination URLs on its own.

### 10.1. Corresponding Thymeleaf Template

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <p>
    Hello
    <strong th:text="${displayName}">there</strong>,
  </p>
  <p>Please verify your email address.</p>
  <p>
    <a th:href="${verificationUrl}">Verify account</a>
  </p>
</body>
</html>
~~~

Here `th:text` escapes `displayName` in the HTML text node; `th:href` writes the URL into the HTML attribute via the template engine's escaping mechanism. The URL must already have been constructed and validated by the backend. If you want to build the URL directly in the template, use a link expression `@{...}` with parameters as shown earlier.

### 10.2. Do Not Pre-Escape Variables Before Passing to the Template

Do not do this:

~~~java
context.setVariable("displayName", Encode.forHtml(displayName));
~~~

and then use:

~~~html
<span th:text="${displayName}"></span>
~~~

Because `th:text` already escapes HTML, the output can get double-escaped and recipients see `&lt;` or `&amp;`. Pass **raw data** into the context and let the template engine escape at the exact output point.

Only when concatenating HTML manually should you call the appropriate encoder, and ensure the value is encoded once for the final context.

## 11. Choosing the Right Libraries and APIs

| Tool/API | Purpose | Notes |
| --- | --- | --- |
| Thymeleaf `th:text` | HTML text output encoding | Use for ordinary text strings |
| Thymeleaf `th:href` / link expression `@{...}` | Place URLs into link attributes and build URLs with parameters | Still requires destination validation when URLs come from untrusted data |
| OWASP Java Encoder `Encode.forHtml` | Encode for HTML text context | Do not use instead of URL validation |
| OWASP Java Encoder `Encode.forHtmlAttribute` | Encode for HTML attribute context | Does not replace URL component encoding |
| Spring `UriComponentsBuilder` | Build URIs from path/query components | Encodes each variable in the right position |
| Java `URI` | Parse and inspect URI structure | Requires separate allowlist policy |
| OWASP Java HTML Sanitizer / jsoup Safelist | Sanitize rich HTML per allowlist | Only use when business logic truly needs to accept HTML |
| `MimeMessageHelper` | Build plain/HTML bodies and MIME parts | Does not automatically inline CSS, sanitize HTML, or validate URLs |
| `JavaMailSender` | Send MIME messages | Does not guarantee identical client rendering |

If you need to use OWASP Java Encoder directly, add the corresponding dependency to the project and manage its version via dependency management. Do not write your own encoder using a few replace calls.

## 12. Common Mistakes and How to Fix Them

| Error | Why It Happens | How to Fix |
| --- | --- | --- |
| User name breaks HTML | Concatenating data directly into HTML text | Use `th:text` or `Encode.forHtml` |
| Quotes create extra attributes | Not encoding values in HTML attributes | Use proper `th:attr`/`th:href` or `Encode.forHtmlAttribute`; always quote attributes |
| Link gets unexpected query parameters | Concatenating token containing `&`/`=` | Use a URI builder and encode query components |
| Link points to unfamiliar domain | URL-encoding only without checking scheme/host | Use an allowlist; prefer trusted base URLs |
| Link has `javascript:` | HTML attribute encoding does not check scheme | Validate scheme and destination before rendering |
| HTML displays `&lt;strong&gt;` | Data was escaped twice | Pass raw data to the template engine; escape only at the final sink |
| Rich-text tags appear literally | Using text escaping when the product wants rich HTML | Sanitize against an allowlist first, then insert with an appropriate unescaped API |
| Rich HTML contains event handlers/scripts | Trusting mail clients to filter them | Sanitize server-side and restrict tags/attributes/protocols |
| Plain text displays `&amp;` | Using an HTML encoder on a plain-text body | Do not HTML-escape `text/plain` content |
| Subject allows line injection | Using uncontrolled input in headers | Validate CR/LF, use `setSubject` and mail APIs |
| CSS gets injected values | Putting untrusted data into `style` | Use fixed enum/allowlist styles |

### 12.1. Do Not Use One Escape Function Everywhere

~~~java
String safe = Encode.forHtml(untrusted);
String html = "<a href=\"" + safe + "\">Open</a>";
~~~

`Encode.forHtml` is designed for HTML text nodes. Do not use it as a universal solution for URLs/attributes. When placing a URL into `href`, construct/validate the URL first and then use an **HTML attribute encoder** for the final value.

### 12.2. Do Not Encode the Entire HTML Template

If you encode the entire template after building it, valid tags like `<p>`, `<a>`, and `<table>` also turn into text. Encode **data variables**, not trusted markup.

~~~java
String html = "<p>Hello "
        + Encode.forHtml(displayName)
        + "</p>";
~~~

The `<p>` markup controlled by the application is preserved; only dynamic data is encoded.

## 13. Testing Contextual Escaping

Tests should focus on **the exact output context**, not merely asserting that an escape function was called. Prepare sample data:

| Input | Output Location | What to Observe |
| --- | --- | --- |
| `Lan <Admin> & Support` | HTML text | Special characters display as text; no tags generated |
| `" onmouseover="...` | Quoted attribute | Does not create a new attribute or close quotes |
| `abc&next=home` | Query parameter | Remains a single token value; does not create extra query parameters |
| `report/2026` | Path segment | Slash inside data does not create an unexpected path level |
| `javascript:...` | URL destination | Rejected by policy before creating link |
| `<strong>Lan</strong>` | Plain text | Displays literal string without HTML escaping |
| `<strong>Lan</strong>` | Rich HTML | Only renders if sanitizer policy permits |
| String with CR/LF | Subject/header | Cannot create extra headers or new header lines |
| Text with Vietnamese diacritics | HTML/plain body | Content displays properly with UTF-8 charset |

### 13.1. Checking Template HTML Output

A template test can render with special values and verify output:

~~~java
Context context = new Context();
context.setVariable("displayName", "<img src=x onerror=alert(1)>");
String html = templateEngine.process("mail/verification", context);

// Verify rendered HTML contains entities rather than tags created by input.
assertThat(html).contains("&lt;img");
assertThat(html).doesNotContain("<img src=x");
~~~

This is an illustrative example; imports and assertions depend on your project's test framework. For URLs, also check that the URL was built with the right query/path components and that scheme/host were accepted by the allowlist.

### 13.2. Checking Raw MIME and Client Rendering

After template rendering:

1. Inspect rendered HTML, verifying text variables and attributes are escaped.
2. Inspect serialized `MimeMessage`, verifying body is `text/html` and charset is appropriate.
3. Inspect the `text/plain` part if sending alternatives.
4. Send to an SMTP sink to view the received email.
5. Open on target mail clients to observe rendering and link behavior.

Do not log verification tokens or real email content in shared test output. Use dummy tokens and test domains to verify encoding.

## 14. Checklist by Context

| Context | Before Output | Encoder/Measure |
| --- | --- | --- |
| HTML text | Value is ordinary text data | `th:text` or `Encode.forHtml` |
| HTML attribute | Attribute is defined and quoted | `th:attr`/`th:href` or `Encode.forHtmlAttribute` |
| URL query | Query parameter and value are defined | `UriComponentsBuilder`/URI component encoding |
| URL path | Each path segment is defined | `pathSegment` or path segment encoder |
| URL destination | Scheme, host, port, redirect policy defined | Validation/allowlist; encoding does not replace validation |
| Plain-text body | Text string, reasonable line endings | Do not HTML-escape; set via `setText(text, false)` |
| Subject/header | No CR/LF or arbitrary header syntax | Validate and use Jakarta Mail/Spring Mail APIs |
| Rich HTML | Allowed tags/attributes/protocols defined | Allowlist sanitizer, then use proper HTML body context |
| CSS | Value belongs to allowed set | Enum/allowlist; avoid arbitrary CSS strings |
| JavaScript | Do not embed data in scripts/event handlers | Avoid JavaScript in emails |

## 15. Takeaways When Creating Emails with Spring Framework Mail

A safe workflow can be described as:

~~~text
Business data source
        |
        v
Validate per business rules (recipient, subject, token, URL destination)
        |
        +--> Build URL: encode path/query component
        |
        v
Template engine
        |
        +--> HTML text: th:text / HTML text encoder
        |
        +--> HTML attribute: th:href / attribute encoder
        |
        +--> Rich HTML: allowlist sanitizer if truly needed
        |
        +--> Plain text: preserve text, no HTML escaping
        |
        v
MimeMessageHelper.setText(plainText, html)
        |
        v
JavaMailSender.send(message)
~~~

`JavaMailSender` and `MimeMessageHelper` are responsible for creating/transporting MIME messages. They do not decide which data is allowed into links, do not sanitize rich HTML automatically, and do not escape every string by context. That responsibility belongs to the content/template generation layer.

When placing data into **HTML text**, use HTML text encoding; when placing into **HTML attributes**, use attribute encoding; when placing into **URLs**, encode each component and validate the destination; for **plain text**, do not apply HTML escaping. If rich HTML is permitted, sanitize against an allowlist. Placing these steps in the right spots preserves business data, prevents broken markup, and reduces the risk of dynamic content being interpreted as unintended syntax.
