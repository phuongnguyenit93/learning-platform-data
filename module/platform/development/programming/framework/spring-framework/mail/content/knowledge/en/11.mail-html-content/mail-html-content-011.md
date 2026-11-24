# Testing rendered HTML with boundary data

In **Spring Framework Mail**, HTML email is usually built from a template and business data: user name, product quantity, amount, verification link, item list, or notifications. A template that looks right with sample data is not necessarily right after rendering with real data. A long name can break layout, Vietnamese can hit encoding errors, a string looking like HTML can be interpreted as markup, a URL containing `&` can break, or an empty list can leave a meaningless table.

**Testing rendered HTML with boundary data** means actively feeding values at valid boundaries, missing values, and error-prone inputs into the rendering process; then evaluating the **resulting HTML**, not just inspecting the template file. This lesson guides how to organize the rendering pipeline, design a boundary data set, verify escaping, content, URLs, images, MIME, layout in email clients, and create automated tests with Spring Boot.

## 1. Why test after rendering?

A template may contain Thymeleaf expressions:

```html
<p>Hello, <span th:text="${displayName}">friend</span>!</p>
<p>You have <strong th:text="${itemCount}">0</strong> items.</p>
```

After rendering with `displayName="An Nguyen"` and `itemCount=2`, the output may be:

```html
<p>Hello, <span>An Nguyen</span>!</p>
<p>You have <strong>2</strong> items.</p>
```

However, if `displayName` contains `<img src=x onerror=alert(1)>` and the application joins it directly via string concatenation, the data can become an HTML tag instead of text. Using `th:text` escapes content in the HTML text context. If `itemCount` is negative or missing data, the engine can still produce syntactically valid HTML that is **wrong in business meaning**.

Three testing layers to distinguish:

| Layer | Question | Example |
|---|---|---|
| **Data/model** | Are values valid, normalized, and properly formatted? | Non-negative item count, non-empty verification token. |
| **Rendered HTML** | Are content/markup/links right? | Data containing `<script>` does not create a script element. |
| **MIME and email client** | Is the message packaged, transmitted, and displayed properly? | HTML and text/plain share the same info, valid image CID, buttons do not overflow the frame. |

An SMTP server returning `250` after `DATA` usually only confirms it **accepted the message**. It does not prove HTML renders properly, the email reached the Inbox, or the recipient read it.

## 2. Building a boundary data matrix

Do not test only one dataset like “Van A Nguyen, 2 items, 100,000 VND”. A systematic dataset can include:

| Group | Test case | Expectation or what to watch |
|---|---|---|
| Missing value | `null` | Clear fallback or intentional error; do not print the literal string `null`. |
| Empty and whitespace | `""`, `"   "`, tab, newline | Does not produce an empty greeting or abnormal spacing. |
| Very long name | 200–500 characters, no spaces | Does not overflow layout; limit display if business rules allow. |
| HTML special chars | `A&B <C> "D"` | Escaped, preserving text meaning. |
| Exploit-like strings | `<script>alert(1)</script>`, `<img onerror=...>` | Does not become user-injected tags/attributes. |
| Vietnamese | `Nguyễn Thị Ánh`, `Đắk Lắk` | No diacritic or encoding corruption. |
| Other Unicode | `日本語`, `العربية`, `😊` | No lost characters, no splitting in the middle of surrogate pairs. |
| URLs | `&`, `#`, query with multiple parameters | Properly encoded in both URL and HTML attribute. |
| Untrusted URLs | `javascript:...`, `https://attacker.invalid` | Rejected or only permitted base URL used. |
| Numbers | `0`, negative, very large, decimals | Check constraints and formatting. |
| Dates and times | End of month, Feb 29, timezone boundaries | Display right timezone and locale. |
| Lists | `null`, empty, one item, hundreds of items | Has empty branch and content limits. |
| Images | Missing logo, mismatched CID | No confusing broken image or unrecognized preparation error. |
| Large content | Long HTML, many images/files | Watch mail size limits and client clipping behavior. |

**Not every edge case must be accepted.** Some cases need a fallback (blank display name); some must be rejected (missing verification token or invalid monetary value). What matters is that the system has predictable and testable behavior.

## 3. Render pipeline before SMTP sending

```text
Business event
      |
      v
Validate required data
      |
      v
Normalize/format (fallback, locale, timezone, limits)
      |
      v
Template engine -> rendered HTML + plain text
      |
      v
Check output on boundary data
      |
      v
MimeMessageHelper.setText(plain, html)
      |
      v
addInline(...) / addAttachment(...) if needed
      |
      v
JavaMailSender.send(...) -> SMTP relay
```

**Separate the renderer from the sender**. The renderer returns HTML/text without network connections; the sender builds MIME and sends. Thanks to that, dozens of boundary data cases can be executed at the unit/integration test level without sending real emails.

## 4. Complete example with Spring Boot and Thymeleaf

The example is based on Spring Boot 3.x, Spring Framework 6.x, and Java 17+. Thymeleaf is used to produce the HTML string for the email; no HTTP request is needed.

### 4.1. Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

### 4.2. Template HTML

File `src/main/resources/templates/mail/account-confirmation.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Verify account</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;">
  <table role="presentation" cellpadding="0" cellspacing="0"
         style="width:100%;background:#f5f5f5;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" cellpadding="0" cellspacing="0"
               style="width:100%;max-width:600px;background:#fff;">
          <tr>
            <td style="padding:24px;font-family:Arial,sans-serif;">
              <h1 style="font-size:24px;line-height:1.3;">
                Hello, <span th:text="${displayName}">friend</span>!
              </h1>

              <p style="line-height:1.6;">
                Please verify your account to complete registration.
              </p>

              <p>
                <a th:href="${verificationUrl}"
                   style="display:inline-block;padding:12px 20px;
                          background:#174ea6;color:#fff;
                          text-decoration:none;">
                  Verify account
                </a>
              </p>

              <p th:if="${hasNotifications}">
                You have
                <strong th:text="${notificationCount}">0</strong>
                pending notifications.
              </p>

              <p th:unless="${hasNotifications}">
                There are currently no notifications to view.
              </p>

              <p style="font-size:13px;line-height:1.5;">
                If you did not request to create an account,
                you can ignore this email.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

Here:
- `th:text` inserts data into text areas and escapes HTML according to context.
- `th:href` sets the link attribute; **the URL must still be validated or built from a trusted base URL**.
- `th:if` and `th:unless` choose content based on the notification count.
- `lang="en"`, UTF-8, and table/inline styles layout help guide email rendering, though testing on target clients is still required.

### 4.3. Renderer result

```java
package com.example.mail;

public record RenderedEmail(
    String plainText,
    String htmlText
) {}
```

The model returns both content versions together so they can be checked immediately after rendering. Do not attach SMTP to the renderer's API.

### 4.4. Renderer: validate, normalize, render

```java
package com.example.mail;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.springframework.stereotype.Component;
import org.thymeleaf.context.Context;
import org.thymeleaf.spring6.SpringTemplateEngine;

@Component
public class AccountEmailRenderer {
    private static final int MAX_NAME_CODEPOINTS = 80;

    private final SpringTemplateEngine templateEngine;

    public AccountEmailRenderer(SpringTemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    public RenderedEmail render(
            String rawName,
            String verificationToken,
            int notificationCount) {

        if (verificationToken == null || verificationToken.isBlank()) {
            throw new IllegalArgumentException(
                "Missing verification token"
            );
        }
        if (notificationCount < 0) {
            throw new IllegalArgumentException(
                "notificationCount must not be negative"
            );
        }

        String name = normalizeName(rawName);
        String url = "https://accounts.example.com/verify?token="
            + URLEncoder.encode(
                verificationToken, StandardCharsets.UTF_8
            );

        Context context = new Context(Locale.forLanguageTag("en"));
        context.setVariable("displayName", name);
        context.setVariable("verificationUrl", url);
        context.setVariable("notificationCount", notificationCount);
        context.setVariable(
            "hasNotifications", notificationCount > 0
        );

        String html = templateEngine.process(
            "mail/account-confirmation", context
        );

        String plain = "Hello, " + name + "!\n"
            + "Please verify your account at:\n"
            + url + "\n"
            + (notificationCount > 0
                ? "You have " + notificationCount
                    + " pending notifications.\n"
                : "There are currently no notifications to view.\n")
            + "If you did not request registration, you can ignore this message.";

        return new RenderedEmail(plain, html);
    }

    private static String normalizeName(String raw) {
        if (raw == null || raw.isBlank()) {
            return "friend";
        }
        String name = raw.strip();
        int count = name.codePointCount(0, name.length());
        if (count <= MAX_NAME_CODEPOINTS) {
            return name;
        }
        int end = name.offsetByCodePoints(0, MAX_NAME_CODEPOINTS);
        return name.substring(0, end) + "…";
    }
}
```

Several design points:

1. **Empty tokens** do not generate a fake `#` link; the renderer rejects missing required data.
2. Negative notification counts are treated as data errors rather than displaying negative numbers.
3. Blank names become `"friend"`. Limiting by Unicode code points avoids splitting a surrogate pair in half; if you need to slice exact **grapheme clusters** of complex emoji, use an appropriate segmentation mechanism.
4. The URL is built from a fixed HTTPS base and the token is encoded in the query. Do not accept an entire arbitrary URL destination from users.
5. Thymeleaf escapes the `name` variable when placed in `th:text`; the renderer does not blindly trust input data as markup.
6. URLs containing tokens are sensitive data. Do not write URLs or entire rendered HTML to production logs.

### 4.5. Building MIME after rendering

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountVerificationMailService {
    private final AccountEmailRenderer renderer;
    private final JavaMailSender sender;

    public AccountVerificationMailService(
            AccountEmailRenderer renderer,
            JavaMailSender sender) {
        this.renderer = renderer;
        this.sender = sender;
    }

    public void send(
            String recipient,
            String displayName,
            String token,
            int notificationCount) throws MessagingException {

        RenderedEmail rendered = renderer.render(
            displayName, token, notificationCount
        );

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message, true, "UTF-8"
        );
        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Verify account");
        helper.setText(
            rendered.plainText(), rendered.htmlText()
        );

        sender.send(message);
    }
}
```

Clear order: **validate → render → finalize MIME → send**. For inline images, call `addInline(...)` after `setText(...)` and ensure the CID matches HTML. When the template fails, SMTP sending has not started yet. When SMTP fails, attempts can be managed in a separate outbox/queue.

## 5. String and Unicode boundary data

### 5.1. Null, empty strings, and whitespace-only

Test in turn:

```text
null
""
" "
"   "
"\t"
"\n"
```

For an optional display name, expected HTML:

```html
<h1>Hello, <span>friend</span>!</h1>
```

Distinguish **optional** values that can use a fallback from **required** values that must raise an error. Do not mechanically replace every `null` with `"-"` : a verification email missing a token must stop, whereas a missing display name can use a general salutation.

### 5.2. Special characters and markup-like content

Test input set:

```text
A&B
<Dear customer>
"Special offer" & 'Promotion'
<script>alert(1)</script>
<img src=x onerror=alert(1)>
</td><td>Inject content
```

Output must keep these strings as **text data**. For example, `<Dear customer>` in the HTML source should appear in an equivalent form `&lt;Dear customer&gt;` when going through `th:text`.

**Escaping differs from sanitization:**
- *Escaping* turns special characters into appropriate entities to display text.
- *Sanitization* allows a small markup subset after stripping dangerous tags and attributes, when the business genuinely needs rich text.
- *URL validation* controls link schemes and hosts.
- *Header validation* controls data placed into `Subject`, `From`, and MIME headers.

Do not use `th:utext` directly with uncontrolled user content. Even though mail clients usually strip scripts, do not depend on client behavior as the primary protective layer.

### 5.3. Multi-byte characters and writing direction

Test `Nguyễn Thị Ánh`, `Đắk Lắk`, `Café`, `日本語`, `العربية`, `😊`, and multi-component emoji.

Three different length concepts:
- `String.length()` counts UTF-16 code units;
- `codePointCount(...)` counts Unicode code points;
- one user-perceived character can be a **grapheme cluster** consisting of multiple code points.

For content with Arabic text combined with numbers and URLs, test RTL behavior on target email clients too. CSS and writing-direction attribute support are not completely identical across mail clients.

### 5.4. Very long strings

Test 300-character names, words without spaces, long order codes, or long query tokens. Check **display logic** (intentional truncation/limiting) and **actual layout** (CTA buttons, tables, cells on small screens). Do not automatically truncate business identifiers that must be shown in full; another presentation or a view-details link may be needed.

## 6. Rendered URLs: not just HTML escaping

Example:

```html
<a th:href="${verificationUrl}">Verify account</a>
```

The template escaping the attribute value **does not make every URL trustworthy**. The following values must be blocked or handled by policy:

```text
javascript:alert(1)
data:text/html,...
http://accounts.example.com/verify
https://attacker.invalid/login
//attacker.invalid/path
${unresolved-placeholder}
```

For verification links, build the URL from an application-managed HTTPS base and do not let users pick the host. Check rendered HTML:
- `href` is non-empty, with no leftover template placeholders.
- Absolute URL using HTTPS where protection is needed.
- Host belongs to a trusted allowlist.
- Query parameters are encoded properly; when parsed as HTML, `&` characters do not break the attribute.
- Token is not truncated and does not go where logs are written.
- Link does not accidentally point to `localhost` or staging during a production release.
- If there is an unsubscribe link, the endpoint must actually handle unsubscribing and corresponding permissions, not just be an illustrative URL.

For tokens containing special characters such as `+`, `/`, `=`, encode them for the query context. Do not concatenate raw tokens arbitrarily without considering reserved URL characters. For HTML attributes, let the template engine handle escaping after the URL is validly constructed.

## 7. Numbers, dates/times, and lists at boundaries

### 7.1. Quantities and monetary amounts

Cases to test include `0`, `1`, negative numbers, very large numbers, money with decimal parts, missing values, and locale-based number formats. A value valid in one business case may be an error in another: a count of `0` is valid for “no notifications”, yet an order confirmation email with an empty order may need to be rejected.

Example of formatting by locale before putting values into the template:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat formatter =
    NumberFormat.getCurrencyInstance(Locale.forLanguageTag("en-US"));

String amountText =
    formatter.format(new BigDecimal("1234567.89"));
```

Clearly define currency, decimal digits, and rounding rules per business logic. Do not let the template decide the meaning of a monetary amount on its own. Inspect the **final rendered string** to avoid bugs like `null $`, wrong separators, or overflowing price columns.

### 7.2. Dates, times, and time zones

Test times near 23:59/00:00, end of month, Feb 29 in a leap year, different time zones, or missing timestamps. If storing events as `Instant`, format them to the recipient's time zone before rendering:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Instant eventTime = Instant.parse("2026-11-12T08:30:00Z");

String formattedTime = DateTimeFormatter
    .ofPattern("dd/MM/yyyy HH:mm", Locale.forLanguageTag("en-US"))
    .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
    .format(eventTime);
```

If the message relates to an appointment, clarify the time zone so users do not misunderstand. Avoid unconsciously using the system time at render time because the same job might display a different time on retry.

### 7.3. Empty, single-element, and very long lists

| Data | Behavior to design |
|---|---|
| `items == null` | Normalize or raise an error depending on the data contract. |
| `items.isEmpty()` | Display an empty notice, do not leave a meaningless table. |
| One item | No extra commas, prefixes, or wrong singular/plural phrasing. |
| Multiple items | Rows have data and proper escaping. |
| Hundreds of items | Limit the list, summary + link to view all. |
| Product name containing HTML | Render as text, do not create new elements. |

Thymeleaf example:

```html
<p th:if="${itemsEmpty}">
  There are no products to display.
</p>

<table th:unless="${itemsEmpty}" role="presentation">
  <tr th:each="item : ${items}">
    <td th:text="${item.name}">Product name</td>
    <td th:text="${item.formattedPrice}">$0.00</td>
  </tr>
</table>
```

To avoid creating emails with thousands of rows, limit data before rendering per policy and provide a link to the details page.

## 8. Checking HTML structure after rendering

When meaningful assertions are needed, you can use an **HTML parser**, such as Jsoup in the test environment, and then inspect the DOM instead of comparing whole HTML strings.

Commonly useful conditions:

- Contains `html`/`body` content, heading, and required business content.
- CTA is an `a` tag with the right `href` and an easy-to-understand label.
- No unrendered `th:text`, `th:href`, `${...}`, or `{{...}}` placeholders remain where they should have been processed.
- No dangerous elements or attributes created by user data.
- Only the conditional content branch matching the data appears.
- Images have meaningful `alt` and `src`.
- Links use permitted hosts, without switching to a test environment by mistake.
- Important text is not empty or truncated due to processing bugs.

**Distinguish HTML source from parsed text content.** The string `A&B` may appear in source as `A&amp;B`, yet after parsing the reader sees `A&B`. To check escaping, look at source; to check content the user sees, read text nodes; to check structural safety, check which elements/attributes are actually present.

Searching only for `"<script>"` in a string is not a complete proof of safety. Context-aware escaping, URL validation, controlled templates, and allowlist sanitization when rich HTML is required are all needed.

## 9. Testing the renderer with JUnit

With `spring-boot-starter-test`, you can execute real templates in tests **without sending SMTP**. The goal is to test rendering logic separately, then have MIME/client tests at other levels.

### 9.1. ParameterizedTest for multiple inputs

Example of a test class using the renderer from section 4:

```java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.mail.host=localhost",
    "spring.mail.port=1025"
})
class AccountEmailRendererTest {

    @Autowired
    AccountEmailRenderer renderer;

    static Stream<Arguments> edgeNames() {
        return Stream.of(
            Arguments.of((Object) null),
            Arguments.of(""),
            Arguments.of("   "),
            Arguments.of("Nguyễn Thị Ánh"),
            Arguments.of("日本語 😊"),
            Arguments.of("A&B <Dear customer>"),
            Arguments.of("<script>alert(1)</script>"),
            Arguments.of("A".repeat(300))
        );
    }

    @ParameterizedTest
    @MethodSource("edgeNames")
    void renderSupportsBoundaryNames(String name) {
        RenderedEmail result = renderer.render(
            name, "safe-test-token", 0
        );

        String html = result.htmlText();

        assertThat(html).contains("<html");
        assertThat(html).contains("Verify account");
        assertThat(html).doesNotContain("<script>alert(1)</script>");
        assertThat(html).doesNotContain("th:text=");
        assertThat(html).doesNotContain("th:href=");
        assertThat(html).contains(
            "https://accounts.example.com/verify"
        );
        assertThat(result.plainText()).contains(
            "Please verify your account"
        );
    }
}
```

Here Spring creates `SpringTemplateEngine` and the renderer; `AccountVerificationMailService.send(...)` is not called so no real SMTP server is needed. Fake token values are used only in tests.

### 9.2. Testing fallbacks and escaping separately

The methods below can be placed in the same `AccountEmailRendererTest` class:

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

@Test
void blankNameUsesFallback() {
    RenderedEmail result = renderer.render(
        "  ", "demo-token", 0
    );

    assertThat(result.htmlText())
        .contains("<span>friend</span>");
    assertThat(result.plainText())
        .contains("Hello, friend!");
}

@Test
void htmlLikeNameIsEscaped() {
    RenderedEmail result = renderer.render(
        "<script>alert(1)</script>", "demo-token", 1
    );

    assertThat(result.htmlText())
        .doesNotContain("<script>alert(1)</script>");
    assertThat(result.htmlText())
        .contains("&lt;script&gt;");
}
```

The test above only illustrates a few specific assertions; for rich HTML content add DOM checks. Do not rely solely on a single escaped string because multiple entity representations can be equivalent in content.

### 9.3. Testing invalid required data

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.junit.jupiter.api.Test;

@Test
void missingTokenIsRejected() {
    assertThatThrownBy(
        () -> renderer.render("An", "", 0)
    ).isInstanceOf(IllegalArgumentException.class);
}

@Test
void negativeNotificationCountIsRejected() {
    assertThatThrownBy(
        () -> renderer.render("An", "demo-token", -1)
    ).isInstanceOf(IllegalArgumentException.class);
}
```

Thus, boundary data can be tested in two groups: **valid inputs that are hard to render** and **invalid inputs that must be rejected**.

### 9.4. Snapshots, DOM assertions, and visual tests

| Strategy | Where is it strong? | Limitations |
|---|---|---|
| Assert text/DOM/link | Right content, escaping, and structure | Need to define the important conditions. |
| HTML snapshot/golden file | Detects major template changes | Easily noisy from whitespace, timestamps, and dynamic tokens. |
| Screenshot diff | Detects layout shifts | Needs a stable renderer/display environment. |
| Email-client preview/test inbox | Evaluates Gmail/Outlook/mobile compatibility | More effort; may need dedicated tools. |

If using snapshots, fix the clock, locale, timezone, fake tokens, and inputs so results are reproducible. Do not save snapshots containing personal information or real tokens into the repository.

## 10. Checking MIME after rendering

String-valid HTML still needs to be packaged properly by Jakarta Mail:

- `Content-Type: text/html; charset=UTF-8` for the HTML part.
- `text/plain` as an adequately informative alternative.
- `multipart/alternative` holding plain and HTML when sending the same content in two forms.
- `multipart/related` for HTML referencing inline resources via `cid:...`.
- `multipart/mixed` when independent attachments are present.
- Message size after MIME encoding must fit SMTP limits.

Example:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
    message, true, "UTF-8"
);

helper.setFrom("no-reply@example.com");
helper.setTo(recipient);
helper.setSubject("Confirmation");
helper.setText(plainText, htmlText);

mailSender.send(message);
```

If HTML uses:

```html
<img src="cid:brand-logo" alt="Brand logo">
```

Then the inline part needs to be added **after** setting the text:

```java
helper.setText(plainText, htmlText);
helper.addInline(
    "brand-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
```

A MIME tree usually looks like:

```text
multipart/related
├── multipart/alternative
│   ├── text/plain
│   └── text/html (src="cid:brand-logo")
└── image/png (Content-ID: <brand-logo>)
```

MIME boundary cases include missing logos, mismatched CIDs, JPEG images with the wrong Content-Type, one-shot `InputStream` sources, overly large files, or calling `setText(...)` a second time after `addInline(...)`.

**SMTP accepting an email does not mean inline images render properly.** When errors occur, view the raw MIME of the received message and compare `Content-ID` against `cid:...` in the HTML.

## 11. Checking rendering on email clients

An HTML parser can confirm a document is valid, yet Gmail, Outlook, or mobile apps still display it differently. Situations to inspect:

| Situation | What to observe |
|---|---|
| Desktop and mobile | Tables, text blocks, and CTAs are not clipped/overflowing. |
| Narrow screens 320–375px | Long names and long links do not cause unreasonable horizontal scrolling. |
| Images blocked | Main message remains readable, `alt` is meaningful. |
| Dark mode | Text/background contrast, logo does not disappear. |
| Enlarged font size | No content area overlaps buttons. |
| Plain-text only | Links and business information remain complete. |
| RTL languages | Punctuation, numbers, and URLs do not make the message confusing. |
| Restricted CSS | Tables, inline styles, and fallbacks still work reasonably. |
| Long content | CTAs or mandatory notices are not hidden behind a clipped area. |

To increase compatibility:
- Prefer simple HTML email, table structures where appropriate, and deliberate inline CSS.
- Do not depend on JavaScript.
- Set `alt` on images; do not put important information solely inside images.
- Use a complete `text/plain` version.
- Test on the mail clients actually popular with the product's recipients.

No string unit test fully simulates the rendering engine of all mail clients.

## 12. HTML size and operational limits

Boundary data also includes **volume**:
- 1,000 products creating thousands of `tr` tags;
- 20 inline images increasing MIME size considerably;
- a description or URL thousands of characters long;
- user content up to hundreds of KB.

Consequences can include slow rendering, high RAM usage, emails exceeding SMTP limits, clipping by clients, or users missing an important CTA.

How to design:
1. Limit the number of items passed into the template per business requirements.
2. Summarize long lists and provide a link to view in full.
3. Optimize images, attachments, and MIME part sizes.
4. Do not embed huge Base64 images directly into HTML when clients may not support them well.
5. Separate timeouts/retries for the data-fetching step and the SMTP-sending step.
6. Measure size **after MIME encoding**, not just HTML character count.

Do not strip mandatory information to reduce message size; choose a compact layout and an appropriate view-details link.

## 13. Classifying errors by layer

| Symptom | Layer to inspect first | Direction to investigate |
|---|---|---|
| Literal `null` or placeholders in email | Model/template | Fallbacks, bindings, and display conditions. |
| Data creates abnormal HTML tags | Escaping/security | `th:text`, avoid `th:utext` with untrusted input. |
| CTA points to wrong host | URL construction | Base URL, allowlist, query encoding. |
| Vietnamese text is corrupted | Render/MIME | UTF-8, Content-Type, template encoding. |
| Inline image does not appear | MIME/client | CID, Content-ID, resource, multipart mode. |
| Table overflows on mobile | HTML/CSS/client | Width, long strings, layout. |
| SMTP AUTH fails | Transport/secret | Credentials, port, and TLS. |
| SMTP returns message too large error | MIME/transport | Total size of images/attachments. |
| SMTP accepted yet not seen in Inbox | Delivery | Provider events, bounces, spam filtering. |

Identify **which layer the error lies in** before making changes. Fixing an SMTP password will not solve an HTML escaping bug; changing a template will not solve a network error.

## 14. Sample test case suite before putting a template into use

| Data | Action | Expectation |
|---|---|---|
| Normal name and full fields | Render | Content, CTA, and text are right. |
| Null/empty name | Render | Fallback instead of `null` or blank greeting. |
| Name containing `<script>` | Render + inspect DOM | Data escaped, no script created. |
| Vietnamese/emoji | Render + MIME/test inbox | No lost characters. |
| 300-character name | View on mobile | Does not overflow frame or cover buttons. |
| Count = 0 | Render | Right empty-notice branch. |
| Count = -1 | Call renderer | Rejects invalid data. |
| Token containing `+`, `/`, `=` | Render + parse href | Query encoded properly, preserves value. |
| Empty list | Render | Does not create a meaningless empty table. |
| Long list | Render + test inbox | Intentional limit/summary. |
| Mismatched CID | MIME inspection | Detects unlinked resource. |
| Images blocked | View received email | Message remains understandable. |
| Plain-text only view | View `text/plain` | Has required content and link. |

You can save test snapshots/screenshots **only with fake data** and compare when templates change. Do not put real emails, URLs with real tokens, or customer info into shared test artifacts.

## 15. Common misconceptions

**“If the template renders without error, the email is right.”** No. HTML can be syntactically valid yet miss mandatory data, have wrong links, or have an unusable layout.

**“Escaping HTML is enough to make URLs safe.”** No. URLs must be built from trusted destinations or have scheme/host validated, in addition to attribute escaping.

**“Data from the database is safe to use with th:utext.”** No. Databases can hold user data and external sources, and do not automatically become trusted HTML.

**“Adding UTF-8 to the template is enough.”** Not necessarily. Both rendering and the MIME charset/encoding part must be checked.

**“Testing in a browser matches every email client.”** No. Email clients have their own HTML/CSS policies.

**“JavaMailSender not throwing errors means HTML looks great.”** No. SMTP sending and recipient-side rendering are different stages.

**“Matching yesterday's snapshot means everything is safe.”** No. Snapshots must go alongside checks of content meaning, URLs, DOM, and boundary cases.

## 16. Practice exercises

### Exercise 1: Display name fallback
Test `null`, `""`, `"   "`, and `"An Nguyen"`. Write assertions confirming empty values become `"friend"` and valid names display properly after rendering.

### Exercise 2: Escaping
A template uses `th:utext` with user name data. Pass `<img src=x onerror=alert(1)>` into the model, then replace with `th:text` and explain why user names must be displayed as text.

### Exercise 3: Checking the CTA
The fake token is `a+b/c==`. Render the URL from a fixed HTTPS base, parse the `href` attribute, and verify query encoding is right. Do not log real tokens.

### Exercise 4: Numbers at boundaries
Test `notificationCount=0`, `1`, `100`, and `-1`. Confirm the right notification branch and that negative numbers are rejected.

### Exercise 5: Unicode and length
Test Vietnamese, Japanese, emoji, and 300-character names. Compare `String.length()` and `codePointCount(...)`; state why slicing by code points can still split a complex grapheme cluster.

### Exercise 6: Lists and tables
When the product list is empty, display a message instead of a table. When there is one product named `A&B <C>`, display the escaped name and properly formatted price.

### Exercise 7: MIME/CID
HTML uses `src="cid:receipt-logo"` yet the helper calls `addInline("company-logo", ...)`. Fix the ID and explain why checking HTML strings is not enough and MIME parts must also be checked.

### Exercise 8: Test matrix
Design a test suite for an order email covering cases for name, price, timezone, empty/long lists, injection, URLs with special characters, and blocked images. For each case specify **input, expected output, and inspection layer** (model, rendered HTML, MIME, or client).

## 17. Summary

**Testing rendered HTML with boundary data** uncovers bugs that viewing templates or sending a single sample email cannot detect: missing values, wrong escaping, broken Unicode, invalid URLs, overflowing layouts, overly large lists, or unlinked inline MIME parts.

With Spring Framework Mail, **separate the renderer from the sender**: validate data → normalize/format → render HTML and plain text → check output → build `MimeMessage` → send via `JavaMailSender`. Combine **JUnit for rendering logic**, **an HTML parser for DOM/URLs**, **MIME inspection for encoding and CIDs**, and **test inboxes for display on target clients**. That is how to control email content quality before SMTP begins transporting the message.


