# Escape user data before putting it into HTML

HTML email lets a Spring application present notifications with headings, paragraphs, action buttons, and images. However, when the email content includes **data entered by users** — for example names, delivery notes, product names, or support replies — developers must ensure that data is interpreted as **text**, not as HTML syntax.

If you concatenate an untrusted string directly into an HTML body, characters such as `<`, `>`, `&`, and quotes can change the structure of the document. The result can be a broken layout, an unexpected link appearing, or user-entered content being presented as an official notice. **HTML escaping** is the step that turns characters that have meaning in HTML syntax into character references so that they stay in the role of data.

In **Spring Framework Mail**, `MimeMessageHelper.setText(html, true)` sets the content as HTML for the email. It **does not automatically escape, clean, or vet each piece of data merged into the HTML string**. If you use a template engine such as Thymeleaf, the application can let the template perform escaping at the output position. If you build the HTML string yourself, the developer must take on that step.

This article presents the principle, the different contexts, Spring Boot/`JavaMailSender` examples, handling of templates, URLs, and rich text, along with the limits that escaping cannot solve.

## 1. Why can dynamic data in HTML email be dangerous?

Consider a confirmation email template:

~~~html
<html>
  <body>
    <h2>Order received</h2>
    <p>Hello, An Nguyen!</p>
    <p>Your order has been confirmed.</p>
  </body>
</html>
~~~

In this HTML, the `<h2>`, `<p>`, and `<strong>` tags managed by the application are **trusted markup**. The name “An Nguyen” may come from the database, but its ultimate source is a user form.

A way of building HTML that is prone to errors:

~~~java
String name = request.customerName();

String html = "<p>Hello, " + name + "!</p>";
~~~

Suppose the user has entered the name:

~~~text
An</p><p>Order has been cancelled</p><p>
~~~

If concatenated verbatim, the message could become:

~~~html
<p>Hello, An</p>
<p>Order has been cancelled</p>
<p>!</p>
~~~

The line “Order has been cancelled” does not come from the order confirmation process. It is created because the data of a text field is treated by the HTML parser as **structure**.

Some email-reading applications block JavaScript and many forms of dangerous HTML. However, **do not treat the mail client having a filter as the primary protective measure**: filtering mechanisms differ by product, and distorting the displayed content can occur even when every script is blocked.

### The boundary between data and HTML

~~~mermaid
flowchart LR
    A["Name / note / content entered by the user"] --> B["String data"]
    B --> C["Escape at the HTML output context"]
    C --> D["Trusted HTML template"]
    D --> E["MimeMessageHelper"]
    E --> F["JavaMailSender"]
    F --> G["SMTP relay"]
~~~

The key point is the step that turns a **data string** into **the content of an HTML document**. Data coming from a database, an API, a queue, or a CSV file can still contain special characters; an intermediate source does not make it automatically become trusted HTML.

## 2. How does HTML escaping work?

Some characters have syntactic meaning in HTML. When we want them to appear as text, we represent them with an HTML entity or character reference.

| Original data | Common HTML representation | Meaning |
| --- | --- | --- |
| `&` | `&amp;` | Do not let the `&` character start an entity unintentionally. |
| `<` | `&lt;` | Do not let data create the symbol that begins a tag. |
| `>` | `&gt;` | Keep the character in the role of text. |
| `"` | `&quot;` | Keep the double quote when inserted into an attribute enclosed in quotes. |
| `'` | `&#39;` | Keep the single quote when inserted into an attribute enclosed in quotes. |

Example customer name:

~~~text
An <Bao> & Co.
~~~

Escaped for HTML text:

~~~html
An &lt;Bao&gt; &amp; Co.
~~~

And placed into the template:

~~~html
<p>Hello, An &lt;Bao&gt; &amp; Co.!</p>
~~~

When an email-reading application displays the HTML, the recipient will see:

~~~text
Hello, An <Bao> & Co.!
~~~

**Escaping does not lose the original content.** It only changes the representation so that the HTML parser does not treat data characters as markup commands.

### Unicode and escaping are two different problems

The words `Nguyễn`, `Đặng`, the character `á`, and emoji are represented in Unicode, usually using **UTF-8** in MIME. HTML escaping mainly handles characters that have syntactic meaning; there is no reason to strip Vietnamese diacritics to avoid HTML injection.

Example:

~~~text
Original:  "Chào 🌷 <An> & Bình"
HTML:     "Chào 🌷 &lt;An&gt; &amp; Bình"
~~~

The MIME layer of Jakarta Mail will handle the charset; the HTML rendering layer decides which characters need to be escaped. **Correct UTF-8 does not mean safe HTML.**

### Encoding is not encryption

The data `&lt;` and `&amp;` can be decoded by any HTML reader for display. This is not secret encryption. An application using STARTTLS to protect the SMTP connection also does not replace the HTML escaping of the body.

## 3. Escape the data, not the whole template

A template whose structure is managed by the application:

~~~html
<h2>Order confirmed</h2>
<p>Customer: {{customerName}}</p>
<p>Note: {{customerNote}}</p>
~~~

Suppose two dynamic values:

~~~text
customerName = "Nguyen <An>"
customerNote = "Call after 17:00 & ask the front desk"
~~~

Escape only **the values put into the placeholders**. Result:

~~~html
<h2>Order confirmed</h2>
<p>Customer: Nguyen &lt;An&gt;</p>
<p>Note: Call after 17:00 &amp; ask the front desk</p>
~~~

Do not do the following:

~~~java
String completeHtml = "<p>Hello, " + safeName + "</p>";

// Wrong intent: the entire <p> tag also gets turned into text.
String visibleTags = escapeHtmlText(completeHtml);
~~~

If you escape the whole HTML, the `<` and `>` characters of the template itself also become `&lt;` and `&gt;`. The recipient may see the literal string `<p>` instead of a formatted paragraph.

An easy-to-remember rule: **the template decides the structure; dynamic data is escaped for the position where it is inserted**.

## 4. There is no single escape that works for every context

This is an important principle when handling HTML email. The same user string needs different measures if it is placed into **text**, an **attribute**, a **URL**, **CSS**, or **JavaScript**.

| Context | Example | How to handle |
| --- | --- | --- |
| HTML text node | `<p>data</p>` | HTML-escape the data. |
| Attribute enclosed in quotes | `<span title="data">` | Escape characters that are meaningful for attributes, and always use enclosing quotes. |
| URL attribute | `<a href="data">` | Check the scheme/host, build the URL properly, then escape in the attribute context. |
| CSS | `style="color: data"` | Select values only from an allowlist; do not insert arbitrary values. |
| JavaScript | `<script>data</script>` or `onclick="data"` | Avoid putting in dynamic data; HTML email should not depend on scripts. |
| Tag name / attribute name | `<data>` or `data="..."` | Do not use user data as syntax names. |

### 4.1. Text node

The most common position:

~~~html
<p>Hello, {{customerName}}!</p>
~~~

If the name contains `<` or `&`, the data needs to be HTML-escaped before replacing the placeholder. This is a case that a simple `escapeHtmlText(...)` function handles well.

### 4.2. HTML attributes

Example:

~~~html
<span title="{{customerName}}">View name</span>
~~~

With:

~~~text
An "VIP" & Co.
~~~

should produce:

~~~html
<span title="An &quot;VIP&quot; &amp; Co.">View name</span>
~~~

The double quotes in the value are escaped so they do not close the attribute early. **Do not create attributes without enclosing quotes** and then concatenate arbitrary data, because that context has additional delimiter characters.

### 4.3. A URL in href or src

Example:

~~~html
<a href="{{destination}}">View order</a>
~~~

Escaping only the `"` and `<` characters is not enough. If `destination` points to a spoofed host or uses a disallowed scheme, the link is still dangerous in meaning. For transactional email, you should use **HTTPS and a host controlled by the application**, build the path/query following URL syntax, and then escape the final value when putting it into the HTML attribute.

### 4.4. CSS, script, and event handlers

Avoid the following patterns when `data` is an arbitrary string:

~~~html
<div style="{{data}}">Content</div>
<button onclick="{{data}}">Click</button>
<script>var note = "{{data}}";</script>
<!-- {{data}} -->
~~~

HTML text escaping is not the right encoder for every CSS/JS/comment construct. Moreover, many mail readers disable JavaScript. For HTML email, keep the CSS, layout, behavior, and tags in **an approved template**; user data should appear only in suitable text positions.

## 5. Escaping text yourself in Java when not using a template engine

You can write a function that illustrates the HTML-escape principle. For a simple application, the following function converts common syntax characters into entities.

~~~java
public final class MailHtmlEscaper {

    private MailHtmlEscaper() {
    }

    public static String escapeHtmlText(String value) {
        if (value == null) {
            throw new IllegalArgumentException(
                    "Cannot escape a null value"
            );
        }

        StringBuilder out = new StringBuilder(
                value.length() + 16
        );

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);

            switch (c) {
                case '&'  -> out.append("&amp;");
                case '<'  -> out.append("&lt;");
                case '>'  -> out.append("&gt;");
                case '"'  -> out.append("&quot;");
                case '\'' -> out.append("&#39;");
                default   -> out.append(c);
            }
        }

        return out.toString();
    }
}
~~~

Example:

~~~java
String name = "An <Bao> & Co.";

String html = "<p>Hello, "
        + MailHtmlEscaper.escapeHtmlText(name)
        + "!</p>";
~~~

Result:

~~~html
<p>Hello, An &lt;Bao&gt; &amp; Co.!</p>
~~~

The illustrative function leaves other Unicode characters unchanged. It is **not a complete handler for every context**, does not check URLs, does not sanitize user HTML, does not handle data put into CSS/JS, and does not decide which tags are allowed.

When there are many email templates or rich text, you should use a **template engine with appropriate escaping** or a trusted HTML sanitization library instead of building a complete HTML processing system yourself.

### Spring's HtmlUtils

If the application has the `spring-web` module on the classpath, you can use:

~~~java
import org.springframework.web.util.HtmlUtils;

String safeName = HtmlUtils.htmlEscape(customerName);
~~~

`HtmlUtils.htmlEscape(...)` produces a string escaped for HTML. However:

- It does not validate `href`, domains, or URLs.
- It is not an HTML sanitizer with a tag/attribute policy.
- An application with only `spring-boot-starter-mail` does not necessarily have `HtmlUtils`, because this class belongs to `spring-web`.

You do not necessarily have to add the entire web starter just to escape one field if the template engine or utility already in the project meets the requirement.

## 6. Building HTML from escaped data

Suppose the system creates an email confirming that a support request has been received.

Data from the user:

~~~text
customerName = "An <Bao>"
customerNote = "Call before 17:00 & leave a message if you can't reach us"
~~~

How to build a small template in Java:

~~~java
String safeName =
        MailHtmlEscaper.escapeHtmlText(customerName);

String safeNote =
        MailHtmlEscaper.escapeHtmlText(customerNote);

String html = """
        <html>
          <body>
            <h2>Support request received</h2>
            <p>Hello, %s!</p>
            <p>Your note: %s</p>
            <p>We will reply in the application.</p>
          </body>
        </html>
        """.formatted(safeName, safeNote);
~~~

`formatted(...)` only replaces the `%s` placeholders with the prepared values. **It does not escape HTML by itself**. Here, the safety of the text node position comes from `safeName` and `safeNote` having been escaped before insertion.

The generated HTML:

~~~html
<html>
  <body>
    <h2>Support request received</h2>
    <p>Hello, An &lt;Bao&gt;!</p>
    <p>Your note:
       Call before 17:00 &amp; leave a message if you can't reach us</p>
    <p>We will reply in the application.</p>
  </body>
</html>
~~~

This is a meaningful structure: the `<h2>` and `<p>` elements are markup chosen by the developer; the name and note are only data, and cannot create additional tags from the `<` characters that have been escaped.

## 7. Spring Framework Mail: sending HTML does not mean sanitizing HTML

To send HTML via Spring Mail, the application usually creates a `MimeMessage` and uses `MimeMessageHelper`:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class SupportReceiptMailService {

    private final JavaMailSender mailSender;

    public SupportReceiptMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReceipt(
            String recipient,
            String customerName,
            String customerNote) throws MessagingException {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient address is required"
            );
        }

        String name = requireText(customerName, "Name");
        String note = requireText(customerNote, "Note");

        // Plain text: use the logical data, no HTML-escape.
        String plainText = """
                Hello, %s!

                The system has received the note:
                %s

                We will reply in the application.
                """.formatted(name, note);

        // HTML: escape each variable placed in a text node.
        String safeName =
                MailHtmlEscaper.escapeHtmlText(name);
        String safeNote =
                MailHtmlEscaper.escapeHtmlText(note);

        String htmlText = """
                <html>
                  <body>
                    <h2>Support request received</h2>
                    <p>Hello, %s!</p>
                    <p>Note: %s</p>
                    <p>We will reply in the application.</p>
                  </body>
                </html>
                """.formatted(safeName, safeNote);

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("support@example.org");
        helper.setTo(recipient);
        helper.setSubject("The system has received your request");
        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }

    private static String requireText(
            String value,
            String fieldName) {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " must not be blank"
            );
        }

        return value;
    }
}
~~~

The example assumes the `MailHtmlEscaper` class has been created as in the previous section. You need to configure SMTP, the account, and a From address that the provider allows. In a real application, you must also validate the recipient address, limit the length of the note, and control who is permitted to receive the email. Those are rules independent of HTML escaping.

### Why does plain text not need HTML escaping?

The same name `An <Bao>`:

| Where it is used | Representation |
| --- | --- |
| Original data in Java | `An <Bao>` |
| `text/plain` body | `An <Bao>` |
| String put into an HTML text node | `An &lt;Bao&gt;` |
| Content the reader sees in HTML | `An <Bao>` |

In a `text/plain` MIME part, the `<` and `>` characters do not carry HTML markup functionality. If you put an escaped string into the plain-text part, the recipient may see `&lt;Bao&gt;` instead of `<Bao>`.

### What does setText(plainText, htmlText) create?

With the helper in multipart mode, `setText(plainText, htmlText)` creates two representations of the same content:

~~~text
multipart/alternative
├── text/plain
└── text/html
~~~

Depending on the actual MIME structure, `multipart/alternative` may sit inside an outer container such as `multipart/mixed` or `multipart/related`. Each version needs to carry the same main content. The plain version uses logical data; the HTML version uses the template's markup and context-appropriate escaping.

**No step in `MimeMessageHelper` classifies which HTML string is “trusted”.** The method only sets the content, the MIME type, and the part structure.

## 8. Spring Boot configuration for the HTML sending example

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

An illustrative SMTP submission configuration:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

The hostname is for illustration and does not represent a specific SMTP service. Secrets need to be taken from the deployment environment or a secret store and avoided being written into Git.

The configuration above controls the **mail-sending connection**; it does not replace the step of escaping data in HTML. Similarly, sending over TLS correctly does not make an HTML string containing untrusted data safe by itself.

## 9. Thymeleaf: escaping at the template render point

If a system has many HTML email templates, concatenating Java strings by hand becomes hard to maintain. **Thymeleaf** is a template engine commonly used in Spring Boot applications; it provides a way to output variables into text nodes with appropriate escaping.

### 9.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
~~~

`spring-boot-starter-thymeleaf` is responsible for rendering, while `spring-boot-starter-mail` is responsible for the email-sending integration. The two functions do not replace each other.

### 9.2. HTML template

Create a file on the classpath:

~~~text
src/main/resources/templates/mail/support-receipt.html
~~~

Content:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
  <head>
    <meta charset="UTF-8">
    <title>Support request received</title>
  </head>
  <body>
    <h2>Support request received</h2>

    <p>
      Hello,
      <strong th:text="${customerName}">Customer name</strong>!
    </p>

    <p>Your note:</p>
    <p th:text="${customerNote}">Default note</p>

    <p>We will reply in the application.</p>
  </body>
</html>
~~~

`th:text` puts the variable into the **text content of the element** and performs appropriate escaping. If `customerName` is `An <Bao>`, the data is represented so that the recipient sees the text `An <Bao>`, without creating a new tag.

To preserve Vietnamese text content, you only need correct Unicode data and an appropriate charset. There is no need to use unescaped output.

### 9.3. Render and send

~~~java
import java.util.Locale;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class TemplateSupportMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;

    public TemplateSupportMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine) {

        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
    }

    public void send(
            String recipient,
            String customerName,
            String customerNote) throws MessagingException {

        Context context =
                new Context(Locale.forLanguageTag("en-US"));

        // Pass the logical data, not yet HTML-escaped, into the template.
        context.setVariable("customerName", customerName);
        context.setVariable("customerNote", customerNote);

        String html = templateEngine.process(
                "mail/support-receipt",
                context
        );

        String plainText = """
                Hello, %s!

                The system has received the note:
                %s
                """.formatted(customerName, customerNote);

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("support@example.org");
        helper.setTo(recipient);
        helper.setSubject("The system has received your request");
        helper.setText(plainText, html);

        mailSender.send(message);
    }
}
~~~

This example focuses on the HTML rendering part; in a real system you need to add checks for `null` values, length, recipient permission, and an appropriate mail-sending configuration.

**Why pass the original data into the template?** Because `th:text` is already the place responsible for escaping. If the backend itself replaces `&` with `&amp;` before passing it into the variable, the template may escape the `&` character again and produce double-escaped data.

## 10. Distinguishing th:text from th:utext

The two syntaxes have different meanings:

~~~html
<!-- Use for untrusted text -->
<p th:text="${customerNote}">Note</p>

<!-- Output content as unescaped HTML -->
<p th:utext="${customerNote}">Note</p>
~~~

- **`th:text`**: outputs data as text, with escaping according to the template context.
- **`th:utext`**: outputs *unescaped text*, which may be interpreted as HTML markup.

If `customerNote` contains `<strong>Priority</strong>`, `th:text` correctly displays the string the user entered as text. `th:utext` may make the word “Priority” become a bold HTML element.

The unescaped approach is **not a suitable choice for customer names, notes, comments, or free-text fields**.

In Thymeleaf HTML inlining, the escaped syntax such as `[[...]]` and the unescaped syntax such as `[(...)]` also need to be distinguished. Do not switch to unescaped output just because you see a special character in the data; if you need to display the text verbatim, escaped output still does that.

### When can unescaped HTML be used?

Sometimes the application genuinely wants to let users compose **rich text**: bold passages, lists, links, or limited formatting. In that case, escaping all the data would turn the tags into text, with no formatting left.

The solution is not to put arbitrary HTML straight into `th:utext`. You need **allowlist-based HTML sanitization** before rendering: accept only approved tags, attributes, and URLs, remove unwanted structure, and ensure the output uses the correct context.

These are two different problems:

| Case | Method |
| --- | --- |
| A name or note that must appear as text | HTML escaping, for example `th:text` |
| HTML created and controlled by the application | Keep the markup in the template |
| Rich HTML from an external source, where some tags need to be kept | A trusted sanitizer with an allowlist policy |
| Arbitrary HTML supplied by a user | Do not put it straight into the email as unescaped output |

**Do not write your own regex that only removes `<script>`** to serve as a sanitizer. HTML has many kinds of tags, attributes, character-encoding methods, and parser situations; you need a parser and a policy that are properly maintained.

## 11. Escaping is not enough when the data is in a URL

An email often has a “View details” button:

~~~html
<a href="https://app.example.org/orders/A102">
  View order
</a>
~~~

Here there are two contexts:

1. **The displayed text of the link** can be escaped like HTML text.
2. **The link's destination in `href`** is a URL; it must have the correct scheme, host, and parameter encoding, and only then be escaped to sit inside an HTML attribute.

If a user supplies a URL that starts with an unexpected scheme or a spoofed host, HTML-escaping the `<`/`"` characters does not make it safe. **Syntactic escaping does not replace validating the meaning of the URL.**

### Building a URL from a trusted base

For a transactional email, you should let the application control the base URL. For example, an order code used as a query parameter:

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String codeParam = URLEncoder.encode(
        orderCode,
        StandardCharsets.UTF_8
);

// The host is managed by the application; do not take it directly from input.
String orderUrl = "https://app.example.org/orders?code="
        + codeParam;

// Escape once more when putting the URL into an HTML attribute.
String href = MailHtmlEscaper.escapeHtmlText(orderUrl);

String html = "<a href=\"" + href
        + "\">View order</a>";
~~~

`URLEncoder` in the example is meant for **a query parameter value**, not a way to encode an entire URL or every path segment. If the URL has many complex components, you should use an appropriate URI builder.

In Thymeleaf, you can put a URL that has already been built and validated into the template:

~~~html
<a th:href="${orderUrl}">View order</a>
~~~

The template handles the attribute representation, but it **does not replace the decision about which URLs may be used**. The application still needs to control the HTTPS scheme, host, path, and access rights as required.

### Rules for URLs supplied from outside

If you must use a URL from outside, you need a validation policy: allowed schemes, allowed hostnames and domains, unusual ports, control characters, redirects, links containing sensitive tokens, and misleading URL forms. For an email with an official action button, **building the link from a domain owned by the application itself** is usually easier to manage.

## 12. How to preserve line breaks from user notes

A note field may contain:

~~~text
Deliver to lobby A
Call before arriving
If no one is there, leave a message
~~~

In HTML, a newline in a text string usually does not create three lines the way plain text does. If you want to keep the line breaks, you can create `<br>` tags **after escaping the data**:

~~~java
String note = """
        Deliver to lobby A
        Call before arriving
        """;

String escaped = MailHtmlEscaper.escapeHtmlText(note);

String htmlFragment = escaped
        .replace("\r\n", "\n")
        .replace('\r', '\n')
        .replace("\n", "<br>");

String html = "<p>" + htmlFragment + "</p>";
~~~

Order:

1. Escape all the input data as text.
2. Normalize the newline styles.
3. Replace newlines with the `<br>` created by the **application**.
4. Insert the result into the trusted template.

If you replace newlines with `<br>` and only then escape everything, the line-break tag turns into text. If you let users type `<br>` themselves and treat it as trusted markup, the application unintentionally opens the door to other tags that are not permitted.

Some clients support CSS such as `white-space: pre-line`, but the level of CSS support in email is not uniform. For important content, using paragraphs or line-break tags built by the server can be more predictable.

## 13. Escape at input time or at output time?

Suppose a customer enters:

~~~text
Buy shirt "A & B"
~~~

If you store the data directly into the database after HTML escaping:

~~~text
Buy shirt &quot;A &amp; B&quot;
~~~

then the data has been bound to an **HTML display format**. When exported to plain text, JSON, CSV, or logs, these entities may become unwanted parts of the text. If the template engine escapes again, the content may be double-escaped.

A process that is easier to maintain:

1. **Receive and validate the original data** according to business needs.
2. **Store the logical Unicode string**, without converting it to HTML entities before you know where it will be used.
3. **When rendering HTML**, escape for the correct output position.
4. **When creating the plain-text version**, use the logical text.
5. **When exporting JSON/CSV or another context**, use that format's own rules.

~~~mermaid
flowchart TD
    A["Original Unicode string"] --> B["Data / business layer"]
    B --> C["Text/plain: keep the text content"]
    B --> D["HTML email: escape at render"]
    B --> E["JSON: serialize JSON"]
    B --> F["CSV: CSV rules"]
~~~

This is the principle of **context-based output encoding**. It helps the same value be represented correctly across many channels.

### What is double escaping?

Start with:

~~~text
An & Binh
~~~

First escape:

~~~html
An &amp; Binh
~~~

Second escape:

~~~html
An &amp;amp; Binh
~~~

When the HTML is read, the latter string may be displayed as `An &amp; Binh` rather than `An & Binh`.

Therefore, settle on **a single place responsible for escaping**: either escape the variable yourself before inserting it, **or** pass the original data to a template engine with escaped output. Do not do both without clearly understanding the structure of the data being passed.

## 14. HTML escaping does not replace other layers of protection

### 14.1. Access rights and the correct recipient

An email that is correctly escaped can still expose data if person A's invoice is sent to person B. The application must ensure the email's data belongs to the right subject and that the recipient address is permitted.

### 14.2. Controlling the Subject and headers

`Subject` is a MIME header, not an HTML text node. It should be set through:

~~~java
helper.setSubject("Your request has been received");
~~~

If the Subject contains dynamic data, you need to limit its length, check for control characters, and avoid assembling raw headers with `\\r\\n` yourself. Do not use HTML escaping as the method for encoding headers; Jakarta Mail has its own mechanism for representing Unicode in headers.

### 14.3. Rich content and external resources

HTML has inline `cid:` images, remote images, CSS, and links. These components need their own policy on resource sources and privacy. For example, a `src` that a user enters arbitrarily could load resources from an unwanted server; HTML escaping cannot control the connection destination.

### 14.4. The mail client's HTML filter

Email readers may remove scripts, event handlers, or certain CSS. But that should not be used as a basis for believing that user-supplied HTML content is safe. The client's filtering functionality does not replace **server-side output escaping or sanitization**.

### 14.5. Logs and sensitive content

HTML entities do not hide personal data. Do not write the entire raw MIME, secret links, recipient information, or attachments into production logs just to debug a template. You should log the send-request ID, the failing step, and the minimum necessary metadata.

## 15. Common mistakes

### Mistake 1 — Concatenating the user's name straight into HTML

~~~java
String html = "<p>Hello " + name + "</p>";
helper.setText(html, true);
~~~

You need to escape `name` for the text node position or use a template with escaped output. `setText(html, true)` does not recognize on its own that `name` is user data.

### Mistake 2 — Escaping the entire HTML string

~~~java
String html = "<p>Hello " + safeName + "</p>";
String wrong = MailHtmlEscaper.escapeHtmlText(html);
~~~

The result may display the `<p>` tag as text. Escape only the dynamic data, not the markup created by the application.

### Mistake 3 — Using th:utext for free-form notes

`th:utext` is intended to output unescaped HTML. Replace it with `th:text` for text data, or truly sanitize if the application allows rich HTML.

### Mistake 4 — Using HTML escaping for a plain-text body

If the body is `text/plain`, the data `<An>` can be displayed verbatim. Converting it to `&lt;An&gt;` and putting it into plain text makes the reader see the entity instead of the original characters.

### Mistake 5 — Escaping the data twice

The backend calls `HtmlUtils.htmlEscape(name)` and then the template uses `th:text` again. Choose one escaping mechanism at the output point, and avoid `&amp;amp;`.

### Mistake 6 — HTML-escaping a URL and considering it safe

A URL string may contain no HTML syntax characters and still carry a disallowed scheme or host. You must control the URL before escaping it into the attribute.

### Mistake 7 — Filtering HTML yourself with regex

Removing `<script>` does not guarantee handling every unsafe piece of HTML. For rich HTML data, use a sanitizer with a parser and an allowlist policy instead of assembling regexes yourself.

### Mistake 8 — Inserting arbitrary data into style, onclick, or script

This is not an HTML text node. It is better to keep the CSS/markup fixed in the template and not let user data decide control content.

### Mistake 9 — Removing every < and > character

Removing characters can corrupt the name `An <Bao>` or the text `5 < 10`. Escaping preserves the original value when displaying instead of discarding information.

### Mistake 10 — Believing STARTTLS handles the HTML problem

TLS protects the negotiated SMTP connection and does not change the meaning of the tags in the email. These are two independent layers of responsibility.

## 16. Practice scenarios

**Scenario A.** A user enters the name `An <Bao> & Co.`. Put it into the HTML fragment:

~~~html
<p>Hello, {{name}}</p>
~~~

The result should be:

~~~html
<p>Hello, An &lt;Bao&gt; &amp; Co.</p>
~~~

The recipient sees exactly `An <Bao> & Co.`.

**Scenario B.** A note contains `Deliver before 17:00 & call the front desk`. How should the `&` character be represented in a text node?

~~~html
<p>Deliver before 17:00 &amp; call the front desk</p>
~~~

**Scenario C.** A name field has a double quote: `An "VIP"`. If it is put into the `title` attribute with double quotes, you need to escape the quote so it does not end the attribute early:

~~~html
<span title="An &quot;VIP&quot;">View name</span>
~~~

**Scenario D.** A note has the content `<strong>Priority</strong>`. If the business defines the note as **text**, the reader should display the tag characters as text too, without bolding the word on its own.

~~~html
<p>&lt;strong&gt;Priority&lt;/strong&gt;</p>
~~~

If the business allows rich text, a separate sanitization process must be applied.

**Scenario E.** The backend has escaped `An & Binh` into `An &amp; Binh` and passed it into a template that uses `th:text`. Why might the recipient see `An &amp; Binh`?

Because the data may have been **double-escaped**. Pass the original logical data to the template and let `th:text` take care of escaping.

**Scenario F.** You want to keep three lines of a note in HTML. Can you let users type `<br>` themselves?

You should not treat a tag string typed by the user as trusted markup. Escape the data first, and then convert newlines into line-break tags created by the application.

**Scenario G.** A path sent by a user contains no `<` or `"`. Is it certain to be allowed into `href` after HTML escaping?

No. HTML escaping does not check the scheme, host, or access rights. You need a URL policy and processing based on the URL structure first.

**Scenario H.** The email body uses:

~~~java
helper.setText(customerNote, false);
~~~

Do you need to replace `<` with `&lt;` before sending?

Not for display in `text/plain`. What matters is to keep the logical text intact and validate the data according to business rules. HTML escaping belongs to the HTML body context, not to every email string.

## 17. A mental model to remember

Treat an HTML email as a combination of a **structured template** and **dynamic data**:

~~~mermaid
flowchart TD
    A["User data"] --> B["Business validation / access control"]
    B --> C{"Where does the data go?"}
    C -->|"HTML text"| D["Escape HTML or th:text"]
    C -->|"HTML attribute"| E["Escape the attribute, use quotes"]
    C -->|"URL attribute"| F["Control the URL, then escape the attribute"]
    C -->|"Plain text"| G["Keep the logical string"]
    C -->|"Allowed rich HTML"| H["Sanitize using an allowlist"]
    D --> I["Trusted HTML template"]
    E --> I
    F --> I
    H --> I
    I --> J["MimeMessageHelper.setText(html, true)"]
    G --> K["MimeMessageHelper: text/plain"]
    J --> L["JavaMailSender.send"]
    K --> L
~~~

Seven things to remember:

1. **`MimeMessageHelper.setText(html, true)` does not escape data by itself.**
2. **Escape at the HTML output position**, rather than escaping the entire template or storing all data in the database as HTML entities.
3. **Text nodes, attributes, URLs, CSS, and JavaScript are different contexts**; a single text-escape function does not handle all of them.
4. **Use the template engine's escaped output**, such as Thymeleaf `th:text`, when putting untrusted strings into HTML text.
5. **Use an allowlist HTML sanitizer** if you need to keep some markup from rich-text input; do not use arbitrary unescaped output.
6. **The plain-text version uses logical data**, not entities meant only for HTML.
7. **Escaping does not replace authentication, authorization, TLS, URL control, or secret protection.**

In Spring Framework Mail, the application is responsible for preparing the HTML content **in the correct context**; `MimeMessageHelper` and Jakarta Mail are responsible for representing it as MIME, and `JavaMailSender` performs the send over the configured SMTP. When these responsibilities are clearly separated, names, notes, and user text still display as intended without accidentally becoming the structure or behavior of the HTML email.
