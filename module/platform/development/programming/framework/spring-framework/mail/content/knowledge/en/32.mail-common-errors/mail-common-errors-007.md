# Creating HTML While Forgetting the Plain-Text Alternative

In **Spring Framework Mail** applications, sending HTML-formatted emails often starts very simply: build a string with **h1**, **p**, and **a** tags, then pass it to **MimeMessageHelper** with **html=true**. The email looks nice in some inboxes and the developer easily assumes they are done. Yet a common production mistake is **creating only the `text/html` part while omitting the equivalent `text/plain` part**.

An HTML-only email is not necessarily rejected by every mail client; many clients can still display it. The problem is that the application omitted an important fallback representation for recipients, automated tools, and environments that do not use or do not wish to render HTML. When HTML is blocked, broken, unsupported, or stripped by another processing system, the recipient may miss key content. Therefore, a professionally presented email should generally provide **both plain text and HTML** within the same MIME message.

In Spring Mail, the direct approach is:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setSubject("Registration confirmation");
helper.setText(
        "Hello,\n\nYour registration has been confirmed.\n\n"
                + "Details: https://app.example.test/account",
        "<p>Hello,</p><p>Your registration has been "
                + "<strong>confirmed</strong>.</p>"
                + "<p><a href=\"https://app.example.test/account\">"
                + "View details</a></p>"
);
~~~

Here the **setText(String plainText, String htmlText)** overload creates two representational variants packaged under **multipart/alternative** per the MIME structure the helper builds. This is **a single email**, not two separate emails.

> **Key point:** If the requirement is to send formatted email that remains readable when HTML is not displayed, generate **text/plain and text/html from the same business data** using the two-string overload of **MimeMessageHelper.setText(...)**. Plain text must contain **full content and critical actions**, not an empty string or a few words saying “please enable HTML”.

## 1. Symptoms of the HTML-Only Mistake

A commonly seen snippet:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setTo("recipient@example.test");
helper.setSubject("Order confirmed");
helper.setText(
        "<h1>Order placed successfully</h1>"
                + "<p>Order ORD-1528 has been confirmed.</p>",
        true
);
mailSender.send(message);
~~~

The **setText(String text, boolean html)** overload with **html=true** marks the input string as HTML. It **does not require the application to supply an equivalent `text/plain` part**.

### Scenarios Where Problems Arise

- Recipients open the message in a client that only supports plain text or is configured to read as plain text.
- An intermediary system has a policy extracting only the `text/plain` part for indexing/classification.
- Automated mail readers or test tools assume the message has plain text, yet that part does not exist.
- A client renders HTML incompletely, dropping tables, buttons, or links from the displayed version.
- Readers copy content into an environment that strips formatting or loses the URL hidden behind “Click here”.

This is a **compatibility and content-quality risk**, not a rule that “HTML-only emails always fail”. View the scope of impact accurately.

### Do Not Conclude “SMTP Failed” Just Because Plain Text Is Missing

An SMTP server can still accept an HTML-only message and return success. In that case **the issue lies in MIME content / downstream experience**, not a failure in SMTP connectivity, credentials, or `JavaMailSender.send()`.

## 2. Why Can an Email Have Multiple Representations?

Modern email uses MIME to describe different content types. Two key media types:

| MIME Type | Content | When Used |
| --- | --- | --- |
| **text/plain** | Text without HTML formatting | Text-only clients, text-processing pipelines, fallback |
| **text/html** | Content with markup, links, layout | Clients supporting HTML that are allowed to render it |

**text/plain** does not mean an email must look ugly or lack information. It can include headings, paragraphs, bullets, and raw URLs. **text/html** enables large headings, tables, CTA buttons, and images, yet must be built safely and tested across mail clients.

### Example of the Same Content

Plain version:

~~~text
ORDER CONFIRMATION

Hello customer,

Order ORD-1528 has been confirmed.
Total: 250.000 ₫.

View order:
https://app.example.test/orders/ORD-1528

If you did not make this transaction, please contact
support@example.test.
~~~

HTML version:

~~~html
<h1>Order confirmation</h1>
<p>Hello customer,</p>
<p>Order <strong>ORD-1528</strong> has been confirmed.</p>
<p>Total: <strong>250.000 ₫</strong>.</p>
<p><a href="https://app.example.test/orders/ORD-1528">
  View order
</a></p>
<p>If you did not make this transaction,
  please contact <a href="mailto:support@example.test">
    support@example.test</a>.</p>
~~~

The two versions can differ in **presentation**, yet must stay consistent in **business facts**: order code, amount, permitted actions, and contact address.

## 3. What Is MIME `multipart/alternative`?

**multipart/alternative** contains multiple representations of **the same logical content**. The client picks the version matching its capabilities and preferences. By MIME convention, parts are normally ordered **from simplest to richest**.

~~~text
MimeMessage
  Content-Type: multipart/alternative
  |
  +-- Part 1
  |     Content-Type: text/plain; charset=UTF-8
  |
  '-- Part 2
        Content-Type: text/html; charset=UTF-8
~~~

**Plain text first, HTML second** is the standard structure. The parts are **alternatives**, not two sections meant to be displayed sequentially to the same user.

### One Email, Not Two Notifications

An easy misconception:

~~~text
Wrong understanding:
  send(plainMessage)
  send(htmlMessage)
  -> recipient may receive two emails.

Right:
  one MimeMessage
    multipart/alternative
      text/plain
      text/html
  -> recipient receives one email with two representations.
~~~

Sending two separate emails can create duplicate notifications, skew metrics/consent, and confuse recipients. **multipart/alternative** is the solution inside a single MIME message.

### Do Not Use `multipart/mixed` to Simulate Two Alternatives

If two independent body parts are placed under **multipart/mixed**, clients may treat them as two additive content blocks, sometimes displaying both plain and HTML or showing one as an attachment. For two representations of the same content, use **multipart/alternative** (which can sit inside mixed/related when needed).

### Plain and HTML Must Carry the Same Meaning

Never let plain say:

~~~text
You have registered successfully.
~~~

while HTML says:

~~~text
Registration is incomplete. Verification required within 15 minutes.
~~~

Such divergence is not an “alternative” in presentation; it creates a business contradiction. Data sources and validation rules must be shared.

## 4. Easily Confused `setText()` Overloads

**MimeMessageHelper** has commonly used overloads:

~~~java
helper.setText("Plain text content");

helper.setText(
        "<strong>HTML content</strong>",
        true
);

helper.setText(
        "Plain text content",
        "<strong>HTML content</strong>"
);
~~~

### Comparison

| Call | Purpose | Has Plain Alternative? |
| --- | --- | --- |
| **setText(String text)** | Plain text only | The message itself is plain |
| **setText(String text, boolean html)** with false | Plain text | The message itself is plain |
| **setText(String text, boolean html)** with true | HTML only | **Does not auto-generate an equivalent plain part** |
| **setText(String plainText, String htmlText)** | Both plain and HTML | **Yes**, two alternatives |

For HTML emails requiring fallback support, choose the **two-String** overload. Do not see two parameters and confuse **(html, true)** with **(plain, html)**: in the second overload, the second argument is an **HTML String**, not a boolean.

### Do Not Swap Parameter Order

~~~java
// Wrong meaning: HTML will be placed as the plain part,
// plain text will be placed as the HTML part.
helper.setText(html, plain);
~~~

Pass them in order:

~~~java
helper.setText(plain, html);
~~~

### Do Not Call `setText` Twice

The following code is not a reliable way to create alternatives:

~~~java
helper.setText(plain);
helper.setText(html, true);
~~~

The second call can overwrite the helper's content setup depending on implementation; it is **not equivalent** to the two-String overload. Use the right call:

~~~java
helper.setText(plain, html);
~~~

## 5. Configuring `MimeMessageHelper` for Alternatives

For the helper to build a multipart structure with plain and HTML, initialize it in the appropriate **multipart mode**.

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class MailExample {

    private final JavaMailSender sender;

    public MailExample(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String recipient) throws Exception {
        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("notifications@example.test");
        helper.setTo(recipient);
        helper.setSubject("Account notification");

        String plain =
                "Hello,\n\nYour account has been activated.\n";
        String html =
                "<p>Hello,</p><p>Your account has been "
                + "<strong>activated</strong>.</p>";

        helper.setText(plain, html);
        sender.send(message);
    }
}
~~~

**new MimeMessageHelper(message, true, "UTF-8")** enables multipart and selects the encoding for the helper. The `text/plain` and `text/html` parts are generated by **setText(plain, html)**. SMTP host and credentials are configured on `JavaMailSender` outside this snippet.

### Is Multipart Needed When an Email Is Plain-Only?

Not necessarily:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
helper.setText("Plain text only.");
~~~

When there is no HTML or attachment, a single `text/plain` part is appropriate; the bug in this lesson **is not lacking multipart on every email type**, but **having HTML without providing a plain alternative when equivalent content support is needed**.

### Why UTF-8?

Vietnamese emails with diacritics need a suitable charset; **UTF-8** lets Subject/Body represent Unicode properly. However, charset does not generate plain text for you. **UTF-8 + HTML-only** is still HTML-only.

### Spring Boot Mail Starter Does Not Auto-Add Plain Text

Spring Boot configuring `JavaMailSender`/SMTP does not mean it auto-generates `text/plain` from HTML. The application must **prepare both bodies itself** before calling the helper. Do not expect the SMTP provider or Thymeleaf to do that silently.

## 6. Symptoms in Raw MIME and How to Detect Them

An HTML-only email may look like:

~~~text
From: notifications@example.test
To: customer@example.test
Subject: =?UTF-8?...?=
MIME-Version: 1.0
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<h1>Order successful</h1>
~~~

Or a nested MIME structure containing **text/html** without **text/plain**. The message root being multipart **does not prove** alternatives exist.

An email containing both:

~~~text
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="alternative-boundary"

--alternative-boundary
Content-Type: text/plain; charset=UTF-8

Order ORD-1528 has been confirmed.
View: https://app.example.test/orders/ORD-1528

--alternative-boundary
Content-Type: text/html; charset=UTF-8

<p>Order <strong>ORD-1528</strong> has been confirmed.</p>
<p><a href="https://app.example.test/orders/ORD-1528">View</a></p>

--alternative-boundary--
~~~

The boundaries and encoded headers are illustrative. Jakarta Mail can generate different boundaries and transfer encodings. When testing, parse the MIME tree and assert semantics rather than matching raw boundary strings.

### Do Not Guess Based on Root `Content-Type`

If there are attachments, the root can be **multipart/mixed**. With inline images, **multipart/related** can also appear. Thus a test like:

~~~java
assertTrue(message.getContentType().startsWith(
        "multipart/alternative"
));
~~~

can fail even when the message holds valid plain+HTML inside. Traverse the MIME tree structurally and locate the proper alternatives pair.

### Do Not Mistake Two Parts in MIME for Two Emails

**multipart/alternative** shares the same envelope recipient and the same notification business key. When sent, SMTP handles one message, not two independent emails.

## 7. Proper Architecture: Generate Both Contents from the Same Model

One way to prevent divergence between the two versions is using **the same finalized business data** and rendering two dedicated templates:

~~~text
OrderConfirmed event
        |
        v
Immutable notification model
  - customer name
  - order code
  - total/currency
  - trusted order URL
        |
        +--------------------+
        |                    |
        v                    v
Plain template          HTML template
        |                    |
        v                    v
Rendered plain          Rendered HTML
        |                    |
        +----------+---------+
                   |
                   v
            Validate consistency
                   |
                   v
             setText(plain, html)
                   |
                   v
              SMTP submission
~~~

### Using a Record for the Model

~~~java
import java.math.BigDecimal;
import java.net.URI;
import java.util.Currency;

public record OrderConfirmationModel(
        String customerDisplayName,
        String orderCode,
        BigDecimal totalAmount,
        Currency currency,
        URI orderUrl
) {
}
~~~

The model is built from an appropriate business snapshot rather than letting separate templates query the database for the order at different times.

### Renderer Returning Both Parts

~~~java
public record MailContent(
        String subject,
        String plainText,
        String html
) {
}

public interface OrderConfirmationRenderer {
    MailContent render(OrderConfirmationModel model);
}
~~~

The business service does not need to know **MimeMessageHelper** details. It builds the model and calls the renderer; the mail composer receives validated `MailContent`.

### Why Not Just Render HTML and Strip Tags?

HTML-to-text conversion can help when a system stores legacy HTML without a plain template, yet does not guarantee equivalent information. Common losses include:

- Text reads **“Verify account”** while the real URL sits in the **href** attribute.
- Tables with name/quantity/price columns collapse into an unreadable single line when tags are stripped.
- Images with important text or diagrams lack alt text.
- CSS hides/shows content depending on viewport or display rules.
- HTML entities and nested elements produce broken line breaks.
- Disclaimers/unsubscribe links in the footer get dropped by the converter.

**Two templates from the same model** are usually easier to control when an email serves a critical business function.

## 8. Plain Text Must Be Actionable and Complete

A good `text/plain` version answers:

- What **event** is this email about?
- What are the essential business facts?
- What must the recipient **do next**?
- If there is a link, can they use the full URL or an alternative?
- Are required contact info, expiry, warnings, or unsubscribe policies included?

### Bug Example: CTA Only in HTML

Bad plain:

~~~text
Your account requires verification.
Please open the HTML version to proceed.
~~~

HTML:

~~~html
<p>Your account requires verification.</p>
<a href="https://app.example.test/confirm?t=example-token">
  Verify account
</a>
~~~

The plain version contains no link; in a text-only client, the recipient cannot complete the action.

Better plain:

~~~text
ACCOUNT VERIFICATION

Your account requires verification.

Verification link:
https://app.example.test/confirm?t=example-token

This link is valid for 15 minutes.
If you did not request this, please ignore this email.
~~~

**Security note:** The token in this example is a placeholder. Real verification links must be issued by a trusted service, have an expiration, enforce single-use policy, and never have raw tokens logged. Plain and HTML should share the **same verified URL**; never generate two different tokens just because there are two parts.

### Anchor Links Are the Most Frequently Lost Detail

HTML can render:

~~~html
<a href="https://app.example.test/orders/ORD-1528">
  Track order
</a>
~~~

Plain must include the link:

~~~text
Track order:
https://app.example.test/orders/ORD-1528
~~~

A converter that only extracts text nodes outputs **“Track order”** and drops the URL. For critical CTAs, explicitly test the URL in both parts.

## 9. Plain Text Is Not Arbitrarily Tag-Stripped HTML

If plain text is generated via a simplistic operation:

~~~java
String plain = html.replaceAll("<[^>]+>", "");
~~~

this is an **unsuitable approach** for production email. This regex:

- Does not understand full HTML structure.
- Drops URLs inside `href`.
- Does not define line breaks for `p`, `br`, `li`, `tr`.
- Does not handle encoding/entities properly.
- Breaks on malformed markup.
- Guarantees nothing about readable formatting.

### A Converter Must Understand the HTML Document

If converting HTML to text is unavoidable, use a proper HTML parser, then handle:

1. Stripping non-visible sections like `script`/`style`/tracking per policy.
2. Converting headings, paragraphs, lists, and line breaks into plain-text structure.
3. Rendering URLs of key links in readable form.
4. Turning tables into labeled lines or an easy-to-read format.
5. Emitting alternative text for images when meaningful.
6. Decoding HTML entities and normalizing Unicode.
7. Bounding size and resources.
8. Verifying no disclaimers/CTAs are lost.

Even a good parser struggles to infer the **business meaning** of a layout. Therefore, a converter should be a **tested fallback**, never an assumption that “writing HTML automatically makes plain right”.

### Strategy Selection

| Strategy | Pros | Cons |
| --- | --- | --- |
| Two templates from one model | Control content and layout per channel | Two templates to maintain |
| HTML-to-text via parser | Automated, less initial authoring | Hard to preserve CTAs/tables/meaning |
| Plain text only | Simple, clear | No HTML presentation |
| HTML only | Least effort | No plain fallback representation |

For transactional/security emails, two tested templates are usually worth the effort. For simple emails, you can start from a **canonical text content** and wrap it in safe HTML, provided both stay semantically accurate.

## 10. Well-Structured Plain Text Content

`text/plain` still deserves readable formatting. You can use:

~~~text
ORDER CONFIRMATION
------------------

Hello customer,

Order:   ORD-1528
Status:  Confirmed
Total:   250.000 ₫

VIEW DETAILS
https://app.example.test/orders/ORD-1528

SUPPORT
If you have questions, please contact
support@example.test.
~~~

### Presentation Tips

- Keep it concise, clear, and broken into paragraphs.
- Avoid wide ASCII tables that break on narrow screens.
- Keep labels and values close together so they stay legible when clients wrap lines.
- Write out full URLs for important CTAs.
- Use bullets or numbered lists.
- Never rely on color or images to convey status.
- Preserve Vietnamese diacritics accurately using UTF-8.
- Do not embed raw HTML entities like **&amp;** in plain text if the goal is showing **&**.

### For Multi-Line-Item Emails

Plain:

~~~text
ORDER ORD-1528

Items:
- Java Book: 1 × 120.000 ₫ = 120.000 ₫
- Notebook: 2 × 65.000 ₫ = 130.000 ₫

Total: 250.000 ₫
~~~

HTML can display the same data in a table. Both representations must agree on quantities and totals; formatting can differ.

### On Line Length

Some clients/transports enforce line-length, wrapping, and transfer-encoding rules. JavaMail handles many MIME/transfer-encoding details. Applications should still produce plain text that wraps cleanly without relying on spaces to align wide columns. Never insert CRLFs into headers manually or hack raw MIME arbitrarily.

## 11. Plain Text for Security and Authentication Emails

**OTP, password reset, account verification, and login alert** emails must prioritize clarity:

~~~text
LOGIN VERIFICATION

Verification code: 482193
This code expires in 5 minutes.

Do not share this code with anyone.
If you did not request this login, please check your
account security via official channels.
~~~

The HTML version can highlight the code with typography, yet **plain text must also include the code** or an equivalent completion path per product requirements. Never put critical information only inside images or CSS pseudo-elements.

### Never Generate Separate OTPs for Each MIME Part

Wrong:

~~~text
HTML template calls generateOtp() -> 482193
Plain template calls generateOtp() -> 917201
~~~

This makes one representation show the wrong code. Instead, generate **one OTP in the business service**, store state/TTL properly, and pass the same model to both renderers.

### Token URLs Must Have Identical Semantics

HTML and plain must use the exact same validated URL from a trusted service. If the plain link differs from the HTML link, that is a **severe bug**, not a cosmetic issue.

### Do Not Log Tokens to Debug Rendering

When emails carry OTPs, password reset links, or payment codes, never log full rendered plain/HTML, because both contain secrets. Observe via opaque notification IDs, template revisions, render status, and error categories. Use fake tokens for previews/tests.

## 12. Marketing Emails and Mandatory Footers

For marketing emails, the plain version must not omit sections required by workflow or law, such as sender identity, contact information, and a proper **unsubscribe mechanism**.

Text example:

~~~text
PRODUCT UPDATES

We released new features this month.

Learn more:
https://app.example.test/updates

You received this email because you subscribed to updates.
Unsubscribe:
https://app.example.test/preferences/unsubscribe?token=sample
~~~

HTML may use an “Unsubscribe” button, yet if `text/plain` is blank or lacks the link, text-only users struggle to opt out. Sync with server-side consent/suppression policies; a URL in the footer never substitutes for actually honoring opt-outs.

### `List-Unsubscribe` Headers

Some marketing emails also include **List-Unsubscribe** and/or **List-Unsubscribe-Post** via appropriate mechanisms. These headers cannot wholly replace unsubscribe text/instructions in the body when policy requires them. Nor does `text/plain` automatically add a `List-Unsubscribe` header.

### Do Not Accidentally Copy Unsubscribe Footers into Security Emails

Security/transactional messages serve a different purpose from marketing. Never paste a generic marketing footer with wrong unsubscribe semantics into password resets or mandatory security notices. **Template purpose** must dictate footer and policy, and both plain and HTML must reflect it accurately.

## 13. HTML and Plain Text Can Share One Template Model

In systems with many email templates, place the model in an application-created object, then render two versions:

~~~java
import java.math.BigDecimal;
import java.net.URI;
import java.util.Currency;
import java.util.Locale;

public record OrderMailModel(
        String customerDisplayName,
        String orderCode,
        BigDecimal totalAmount,
        Currency currency,
        URI orderUrl,
        Locale locale
) {
}
~~~

### Renderers Should Not Query Data Independently

Wrong:

~~~text
Plain renderer:
  find order total from database at 10:00:00

HTML renderer:
  find order total from database at 10:00:02
~~~

If data changes or a service returns a different result, the two parts diverge. Build a **model snapshot** first, validate it, and pass the exact same snapshot to both renderers.

### A Renderer Interface with Clear Contracts

~~~java
public interface MailContentRenderer<M> {

    MailContent render(M model);
}

public record MailContent(
        String subject,
        String plain,
        String html
) {
}
~~~

A service can do:

~~~java
MailContent content = renderer.render(model);

validateMailContent(content);

helper.setSubject(content.subject());
helper.setText(content.plain(), content.html());
~~~

This is illustrative code. **validateMailContent** is an application-defined function validating content/URLs/schema per policy; Spring does not provide this method automatically.

### Fields That Must Stay Consistent

| Field | Same Value in Plain and HTML? |
| --- | --- |
| Order code | Yes |
| Amount, currency | Yes |
| OTP code | Yes |
| Link expiration | Yes |
| Action instructions | Yes |
| Action destination link | Yes |
| Transaction status | Yes |
| Critical contact info | Yes |
| Font size, colors, HTML tags | No need to match |

### Avoid Inventing Copy in Two Separate Services

If the plain template lives in codebase A and the HTML template lives in codebase B owned by different teams, content drifts over time. A **versioned template registry** or shared release process keeps plain and HTML aligned under the same notification template revision.

## 14. Thymeleaf Example Rendering HTML and Plain Text

**Thymeleaf** can render both HTML and text templates when configured properly. It does not auto-create a plain alternative simply because HTML was rendered.

Example **order-confirmed.html** file:

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org" lang="vi">
<body>
  <h1>Order confirmation</h1>
  <p>Hello <strong th:text="${customerDisplayName}">customer</strong>,</p>
  <p>Order <span th:text="${orderCode}">ORD-000</span>
     has been confirmed.</p>
  <p>Total: <strong th:text="${formattedTotal}">0 ₫</strong></p>
  <a th:href="${orderUrl}">View details</a>
</body>
</html>
~~~

Example **order-confirmed.txt** file using Thymeleaf TEXT template mode:

~~~text
ORDER CONFIRMATION

Hello [[${customerDisplayName}]],

Order [[${orderCode}]] has been confirmed.
Total: [[${formattedTotal}]]

View details:
[[${orderUrl}]]
~~~

### Notes on Template Modes

**Thymeleaf HTML mode** works with `th:text`, `th:href`; **TEXT mode** uses the corresponding inline text syntax. If you only configure one `ClassLoaderTemplateResolver` for HTML, calling **process("order-confirmed.txt", context)** may fail to behave as expected if the template mode is not selected properly.

One design option:

~~~text
TemplateEngine HTML
  -> HTML resolver
  -> order-confirmed.html

TemplateEngine TEXT
  -> TEXT resolver
  -> order-confirmed.txt
~~~

You can use a single engine with multiple resolvers configured by suffix/pattern, provided you set **mode**, **resolver order**, and **cache key** accurately. No need to cram both into a single Java string.

### Shared Context

~~~java
import org.thymeleaf.context.Context;

Context context = new Context(model.locale());
context.setVariable(
        "customerDisplayName", model.customerDisplayName()
);
context.setVariable("orderCode", model.orderCode());
context.setVariable("formattedTotal", formattedTotal);
context.setVariable("orderUrl", model.orderUrl().toString());
~~~

**formattedTotal** should be computed by a locale/currency-controlled formatter shared across both parts. **orderUrl** must be generated/validated by a trusted application service, never taking an arbitrary user-supplied host.

### Render Before Sending

~~~java
String plain = textEngine.process(
        "order-confirmed.txt", context
);

String html = htmlEngine.process(
        "order-confirmed.html", context
);

helper.setText(plain, html);
~~~

**textEngine** and **htmlEngine** are two `TemplateEngine`s configured with matching resolvers; this illustrates architecture, not beans provided out of the box by `spring-boot-starter-mail` alone.

## 15. Spring Boot Example: Service Sending HTML with Plain

Below is an example using **JavaMailSender** and a separate class rendering both content variants. This example builds strings directly to keep the snippet self-contained, though larger projects can substitute Thymeleaf/a registry.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountNotificationMailService {

    private final JavaMailSender sender;

    public AccountNotificationMailService(
            JavaMailSender sender
    ) {
        this.sender = sender;
    }

    public void sendActivated(
            String recipient,
            AccountActivationMail model
    ) throws MessagingException {
        // 1. Validate recipient, sender, model, and URL at outer layer.
        // 2. Render both variants from the same model.
        String plain =
                "Hello " + model.displayName() + ",\n\n"
                + "Your account has been activated.\n\n"
                + "View account details:\n"
                + model.accountUrl() + "\n";

        String html =
                "<p>Hello " + model.escapedDisplayName()
                + ",</p>"
                + "<p>Your account has been "
                + "<strong>activated</strong>.</p>"
                + "<p><a href=\"" + model.escapedAccountUrl()
                + "\">View account details</a></p>";

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("accounts@example.test");
        helper.setTo(recipient);
        helper.setSubject("Account activated");
        helper.setText(plain, html);
        sender.send(mime);
    }
}
~~~

With illustrative record:

~~~java
public record AccountActivationMail(
        String displayName,
        String escapedDisplayName,
        String accountUrl,
        String escapedAccountUrl
) {
}
~~~

**escapedDisplayName** and **escapedAccountUrl** are assumed pre-encoded/validated for each HTML context by a trusted rendering layer, never blindly supplied by callers. In production, **do not concatenate HTML strings to render user data** as a primary pattern; use a context-aware auto-escaping engine and URI validator. This example illustrates only that **the same facts appear in both plain and HTML**, not a complete escaping framework.

### Limitations of This Example

- Lacks SMTP host/port/TLS/credentials; those belong in sender configuration.
- Lacks suppression/consent/sender policies.
- Lacks notification/outbox persistence for safe retries.
- Lacks Bean Validation or dedicated schema checks on the model.
- Lacks attachments, inline images, or multi-locale support.
- Lacks idempotency handling when the provider accepts yet the reply is lost.

Do not take a demo service as a complete production solution. Still, the core fix is present: **setText(plain, html)** instead of **setText(html, true)**.

## 16. MIME Tree with Attachments

When an email includes attachments, the MIME root can become **multipart/mixed**, holding `multipart/alternative` inside for the body.

~~~text
MimeMessage
  Content-Type: multipart/mixed
  |
  +-- multipart/alternative
  |     |
  |     +-- text/plain
  |     '-- text/html
  |
  '-- application/pdf (attachment)
~~~

Depending on the `MimeMessageHelper` mode, an intermediate **multipart/related** may also appear. What matters is not that the root equals **multipart/alternative**, but that the body holds **plain and HTML in a proper alternative relationship**.

### Example Adding an Attachment

~~~java
import org.springframework.core.io.ByteArrayResource;

MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setTo(recipient);
helper.setSubject("Order receipt");
helper.setText(plain, html);
helper.addAttachment(
        "receipt.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

sender.send(message);
~~~

**ByteArrayResource** suits small payloads already in memory; large attachments need size limits, storage/streaming, and resource lifecycle management to avoid holding raw bytes on the heap. Plain text can state “PDF receipt is attached”, never raw PDF bytes.

### An Attachment Is Not a Plain Alternative

A PDF attachment containing invoice details **does not substitute** for `text/plain` when an HTML body is the main content. The email still needs meaningful explanation/CTAs in plain text. Depending on the domain, full details may live in the attachment while the body explains how to access it.

### Do Not Mistake Two Alternatives for Attachments

If a test SMTP catcher shows two MIME parts, those may be normal representations. Never conclude “the recipient got two payloads” when the MIME tree is valid, nor delete a part just to make a test UI look tidier.

## 17. MIME Tree When HTML Has Inline CID Images

HTML emails can reference inline images:

~~~html
<p>Hello!</p>
<img src="cid:brand-logo" alt="Company logo">
~~~

With a typical structure:

~~~text
MimeMessage
  multipart/mixed
    |
    '-- multipart/related
          |
          +-- multipart/alternative
          |      |
          |      +-- text/plain
          |      '-- text/html
          |
          '-- image/png
                 Content-ID: <brand-logo>
~~~

Code:

~~~java
import org.springframework.core.io.ClassPathResource;

MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

String plain =
        "Hello!\n\nAccount details are available at:\n"
                + "https://app.example.test/account";
String html =
        "<p>Hello!</p>"
        + "<img src=\"cid:brand-logo\" alt=\"Company logo\">"
        + "<p><a href=\"https://app.example.test/account\">"
        + "View account</a></p>";

helper.setText(plain, html);
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
~~~

In this example, the resource must exist with an appropriate MIME type; `sender.send()` is omitted at the end to focus on composition. Per standard `MimeMessageHelper` guidance, **call `setText(...)` before `addInline(...)`** to preserve compatible behavior across mail clients.

### Plain Needs No Images, Yet Needs the Information

There is no need to turn a logo into ASCII art. Plain text can state the brand name, message, and link clearly. If an image carries important data (such as a promo code inside a banner), plain text must express that information in words.

### `alternative` and `related` Serve Different Roles

| Multipart | Relationship Between Parts |
| --- | --- |
| **alternative** | Different representations of the same content |
| **related** | Linked resources used to render a representation (CID) |
| **mixed** | Independent parts of the same email, e.g. attachments |

Never use **related** in place of **alternative**. An email using all three needs proper nesting; `MimeMessageHelper` modes support this, yet you must verify structure and target mail clients.

## 18. Plain Text and Accessibility

One reason to support plain text is helping some clients and text-reading workflows access content more easily. However, **having plain text does not automatically make an email accessible**, and conversely HTML with strong semantic markup also helps screen readers.

### Principles Useful in Both Versions

- Essential meaning must not rely solely on color.
- CTAs should use descriptive action labels, not just “Click here”.
- Images carrying important content need alt text / textual equivalents.
- Amounts, dates, codes, and links must be explicit.
- Avoid layout tables that scramble reading order.
- Use semantic headings/lists in HTML where appropriate.
- Plain text should have clear paragraphs, bullets, and complete links.
- Avoid dense decorative characters that trip up screen readers.

### Text-Only Does Not Replace Accessibility Testing

If a product has accessibility requirements, test rendered HTML with appropriate tools/clients and manually review plain text. There is no universal rule that every screen reader always reads `text/plain`; many screen readers read HTML rendered by the mail client.

## 19. Encoding, Line Endings, and MIME Headers

An email containing Vietnamese needs attention to:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Type: text/html; charset=UTF-8
~~~

When using **MimeMessageHelper(..., "UTF-8")**, the helper sets the proper charset for content. Jakarta Mail may choose a transfer encoding such as **quoted-printable** or **base64** depending on content/implementation.

### Do Not Assume Encoded HTML Bytes Are Plain Text

If raw source shows:

~~~text
Content-Transfer-Encoding: quoted-printable
~~~

that is **how bytes are encoded for MIME transport**, not a plain-text representation. Decoding `quoted-printable` HTML still yields HTML; it does not strip tags or add `text/plain`.

### Subject Uses Its Own Encoding

`Subject` is a header, typically encoded using MIME header encoding rules; the body is a MIME part. An email with a valid UTF-8 `Subject` can still lack a plain alternative.

### Header Injection

Never pass user-supplied variables containing CR/LF straight into `Subject`/`From`/`To`/`Reply-To`. Use Jakarta Mail/Spring Mail APIs for composition while still validating data per policy. Line breaks inside a plain-text body are normal; unintended CRLF injection inside **headers** creates header injection vulnerabilities.

### Plain and HTML Can Have Different Transfer Encodings

In raw MIME, one part may use `quoted-printable` while the other uses `base64`. Tests should use Jakarta Mail's parser to decode content rather than comparing raw bytes or requiring both parts to share a transfer encoding.

## 20. Email Deliverability: Do Not Overstate Plain Text's Role

Many guides claim “without `text/plain`, emails go to spam”. Separate reality from myth:

- Some spam filters and mail clients may factor MIME/content completeness into scoring.
- Having a plain alternative improves compatibility and makes content easier to extract in some systems.
- Yet **there is no guarantee that adding plain text puts email into the Inbox**, and no single formula across all providers.
- Deliverability also depends on SPF, DKIM, DMARC, sender reputation, consent, recipient engagement, content, and provider policies.

### Plain Text Is Content Quality, Not a Spam-Bypass Trick

Never stuff an empty plain part, meaningless keywords, or text diverging from HTML just to “trick spam filters”. That hurts trust and classification.

### End-to-End Verification Is Needed

A testing strategy:

1. Parse the MIME tree; verify proper plain/HTML alternatives exist.
2. Verify key content consistency.
3. Send through an SMTP fixture or test mailbox.
4. Check text-only/HTML rendering on supported clients.
5. Track accepted and delivered/bounced outcomes per provider when available.

**SMTP 250 accepted** does not equal **landed in Inbox**; adding `text/plain` does not change that rule.

## 21. How Do Email Clients Choose an Alternative?

With **multipart/alternative**, clients normally pick one representation they can render that matches user preferences. HTML is often preferred when supported, while plain serves as the alternative when HTML is unsuitable.

### Assumptions to Avoid

| Assumption | Issue |
| --- | --- |
| Clients always render both | Alternatives are not meant for cumulative display |
| Clients always pick HTML | Some clients/preferences pick plain |
| An empty `text/plain` is enough | Text-only users get blank content |
| Clients will strip HTML cleanly | Not guaranteed; links may vanish |
| MIME tree root is always `alternative` | Attachments/CID create nesting |
| Having plain means HTML needs no semantics | HTML still needs accessibility |
| HTML-only emails are always rejected | False across many clients/providers |

### When a Client Has a “View as Plain Text” Option

When the message includes **text/plain**, the receiving client can display that part directly. If the email is HTML-only, the client might auto-convert HTML to text or still display HTML depending on implementation. Never force recipients to rely on client conversion to complete critical CTAs.

### Multiple Content Parts

An email can contain an HTML body, inline images, attachments, and embedded emails. Clients render per MIME nesting and local policies; tests must inspect the real structure instead of searching raw MIME for the substring **"text/plain"** and declaring victory.

## 22. Writing a Function to Inspect Plain/HTML in the MIME Tree

With **Jakarta Mail**, you can traverse MIME parts to verify a message contains **multipart/alternative** with both `text/plain` and `text/html`.

To verify the **right relationship**, do not just count total parts:

~~~text
multipart/mixed
  +-- text/plain (a separate note)
  '-- text/html (attachment)
~~~

This example contains both MIME types, yet **they are not an alternative pair** for the same body.

### Recursive Inspector Focused on MIME Structure

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public final class AlternativeInspector {

    public record AlternativeInfo(
            boolean hasPlain,
            boolean hasHtml
    ) {
        public boolean complete() {
            return hasPlain && hasHtml;
        }
    }

    public static boolean hasCompleteAlternative(Part root)
            throws Exception {
        return inspect(root, 0);
    }

    private static boolean inspect(
            Part part,
            int depth
    ) throws Exception {
        if (depth > 20) {
            throw new IllegalArgumentException(
                    "MIME tree too deeply nested"
            );
        }

        if (!part.isMimeType("multipart/*")) {
            return false;
        }

        Multipart multipart = (Multipart) part.getContent();

        if (part.isMimeType("multipart/alternative")) {
            boolean plain = false;
            boolean html = false;

            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                plain |= child.isMimeType("text/plain");
                html |= child.isMimeType("text/html");
            }

            if (plain && html) {
                return true;
            }
        }

        for (int i = 0; i < multipart.getCount(); i++) {
            if (inspect(multipart.getBodyPart(i), depth + 1)) {
                return true;
            }
        }

        return false;
    }
}
~~~

This is an **illustrative inspector** for common trees where `text/plain` and `text/html` are direct children of `multipart/alternative`. Valid MIME messages may have nested `related` or more complex structures, in which case the inspector must be extended accordingly. Do not use this function as a security validator for arbitrary Internet MIME without bounding part counts, bytes, and execution time. In unit tests for emails **generated by your own application**, it is a helpful guard.

### Why Check `completeAlternative`?

Checking only:

~~~java
assertTrue(message.isMimeType("multipart/*"));
~~~

is not enough: an email with an attachment is also multipart yet may contain only HTML. Tests must inspect down to the **alternative relationship**.

### Do Not Hardcode Fixed Boundaries

Jakarta Mail generates boundaries that can differ across saves/sends; assertions on raw boundary strings become flaky. An inspector using MIME APIs is far more durable.

## 23. Unit Testing Without SMTP: Verifying MIME Alternatives

You can use **JavaMailSenderImpl** to build a `MimeMessage` without connecting to SMTP. The test verifies structure immediately after composition.

~~~java
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.junit.jupiter.api.Assertions.*;

class MailAlternativeTest {

    @Test
    void htmlMailAlsoProvidesPlainText() throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        MimeMessage message = sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("notifications@example.test");
        helper.setTo("customer@example.test");
        helper.setSubject("Registration confirmation");

        helper.setText(
                "Registration has been confirmed.",
                "<p>Registration has been <b>confirmed</b>.</p>"
        );

        message.saveChanges();

        assertTrue(
                AlternativeInspector.hasCompleteAlternative(message)
        );
    }
}
~~~

This test does not submit to SMTP; it checks the structure produced by the helper. If a team refactors to:

~~~java
helper.setText(html, true);
~~~

the test catches the missing plain part.

### Negative-Path Test to Avoid “Always Green” Tests

A control test:

~~~java
@Test
void htmlOnlyDoesNotPassAlternativeCheck() throws Exception {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

    helper.setText("<p>Hello</p>", true);
    message.saveChanges();

    assertFalse(
            AlternativeInspector.hasCompleteAlternative(message)
    );
}
~~~

This test can sit in the same test class and reuse imports. When building a quality gate, ensure the inspector does not return true simply upon seeing a multipart root.

## 24. Inspect Actual Content, Not Just MIME Types

An email structured as:

~~~text
multipart/alternative
  text/plain: ""
  text/html: "<h1>Payment due</h1><a href=...>Pay</a>"
~~~

has two parts structurally yet lacks a useful plain fallback.

### Assertions to Add

- Plain is non-blank and not merely boilerplate.
- Plain contains mandatory business facts.
- HTML also contains those facts.
- CTA URLs in plain and HTML point to the same trusted source.
- Locale/currency/codes/timestamps are consistent.
- Any required unsubscribe/footer appears in both parts.
- Plain contains no raw HTML tags or unrendered placeholders.
- HTML does not display a token belonging to someone else.

### Separate MIME Inspection from Business Assertions

**MIME inspection** answers “does the message have the right alternative structure?”. **Content assertions** answer “do plain and HTML carry domain-equivalent information?”. Both are needed for critical messages.

### A Render-Level Test

~~~java
import static org.junit.jupiter.api.Assertions.*;

@Test
void plainContainsRequiredOrderFacts() {
    MailContent content = renderer.render(model);

    assertFalse(content.plain().isBlank());
    assertTrue(content.plain().contains("ORD-1528"));
    assertTrue(content.plain().contains(
            "https://app.example.test/orders/ORD-1528"
    ));
    assertTrue(content.html().contains("ORD-1528"));
}
~~~

**renderer** and **model** are application fixtures/test dependencies; the example omits their definitions to avoid mixing domain setup into MIME tests. In a real project, provide concrete fixtures for each template.

### Semantic Equivalence Beats Byte Equality

Never assert **plain.equals(stripHtml(html))**. Plain has different formatting from HTML by design; what matters is consistency of **business fields** and actionable links.

## 25. Integration Testing with an SMTP Fixture and Email Clients

Unit-testing `MimeMessage` is not enough to confirm both parts survive submission through the sender and receipt by a test server. You can use **GreenMail** or an isolated SMTP catcher.

~~~text
Spring service
   |
   v
Renderer returns plain + HTML
   |
   v
MimeMessageHelper
   |
   v
Local SMTP test server
   |
   v
Captured MimeMessage
   |
   +--> Verify multipart/alternative
   +--> Verify text/plain
   +--> Verify text/html
   '--> Verify subject/recipient/attachment
~~~

### GreenMail Integration Test Example

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.junit.jupiter.api.Assertions.*;

class AlternativeSmtpIntegrationTest {

    private GreenMail greenMail;

    @BeforeEach
    void start() {
        greenMail = new GreenMail(
                new ServerSetup(
                        0, "127.0.0.1",
                        ServerSetup.PROTOCOL_SMTP
                )
        );
        greenMail.start();
    }

    @AfterEach
    void stop() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }

    @Test
    void smtpDeliveryRetainsBothAlternatives()
            throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(greenMail.getSmtp().getPort());

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("sender@example.test");
        helper.setTo("recipient@example.test");
        helper.setSubject("Message with fallback");
        helper.setText(
                "This is plain text content.",
                "<p>This is <b>HTML</b> content.</p>"
        );

        sender.send(mime);

        assertTrue(greenMail.waitForIncomingEmail(5000, 1));
        MimeMessage received =
                greenMail.getReceivedMessages()[0];

        assertTrue(
                AlternativeInspector.hasCompleteAlternative(received)
        );
    }
}
~~~

This fixture runs on loopback and sends to no real recipient. Choose a GreenMail version supporting **Jakarta Mail** matching your Spring Boot/Jakarta Mail dependency graph; do not assume this code applies verbatim to legacy `javax.mail` without changing imports.

### Testing Through a Fixture Is Not Testing a Real Inbox

GreenMail confirms MIME was accepted over SMTP. It does not verify rendering in Gmail/Outlook or real-world deliverability. If a product targets specific mail clients, inspect rendering in managed test mailboxes without using customer data.

### Testing with Attachments and CID

Add scenarios:

- HTML + plain + PDF attachment.
- HTML + plain + CID logo.
- HTML + plain + CID + PDF.
- Plain body containing the URL when HTML uses a CTA button.
- Vietnamese charset and Unicode characters.

The MIME inspector must locate alternatives inside nested trees; never force the root to always be `multipart/alternative`.

## 26. Content Previews and Spotting Forgotten Plain Text

Teams that preview only HTML often fail to notice missing `text/plain`, because review screens also prioritize HTML. Provide **two preview modes**:

~~~text
Template preview
  |
  +-- HTML view
  |    + layout, fonts, links, images
  |
  '-- Plain-text view
       + heading and paragraphs
       + full URLs
       + required business facts
       + unsubscribe/contact text
~~~

### What to Check When Previewing Plain Text

| Area | Check |
| --- | --- |
| **Content** | Title, order code, amounts, and deadlines match HTML |
| **Links** | Exact URLs, no lost button targets |
| **Vietnamese text** | Diacritics, Unicode characters, line breaks |
| **Tables** | Fields remain readable when wrapped |
| **Images** | Important image info has text equivalents |
| **Footer** | Contact info and relevant policies |
| **Edge data** | Long names, many items, missing optional fields |
| **Variables** | No unrendered placeholders remain |
| **Security** | No real user tokens/PII inside previews |

### HTML-Only Previews Create a False Sense of Security

If an editor only renders HTML in a browser, reviewers see buttons, logos, and tables. Yet when MIME is built via **setText(html, true)**, the email still lacks a plain part. **UI previews do not replace MIME tree tests.**

### Template Registries Must Manage Both

A transactional email revision might include:

~~~yaml
templateKey: ORDER_CONFIRMED
revision: 18
locale: vi-VN
content:
  subject: order-confirmed.subject.txt
  plain: order-confirmed.txt
  html: order-confirmed.html
~~~

The manifest is an application-defined structure. Never allow publishing a revision with **html** yet missing **plain** if the template's delivery policy requires alternatives.

## 27. Fail Fast When Plain Text Is Missing

Do not wait for an SMTP provider or recipient to discover missing plain text. Validate before composing:

~~~java
public final class MailContentValidator {

    public void validate(MailContent content) {
        if (content == null) {
            throw new IllegalArgumentException(
                    "Mail content is missing"
            );
        }

        if (content.subject() == null
                || content.subject().isBlank()) {
            throw new IllegalArgumentException(
                    "Subject is missing"
            );
        }

        if (content.plain() == null
                || content.plain().isBlank()) {
            throw new IllegalArgumentException(
                    "Plain text alternative is required"
            );
        }

        if (content.html() == null
                || content.html().isBlank()) {
            throw new IllegalArgumentException(
                    "HTML body is missing"
            );
        }

        if (content.subject().contains("\r")
                || content.subject().contains("\n")) {
            throw new IllegalArgumentException(
                    "Subject contains line break"
            );
        }
    }
}
~~~

This is a policy **for templates requiring plain+HTML**. Never apply it blindly to plain-only notifications: if a template intentionally sends only `text/plain`, lacking HTML is not an error.

### Do Not Mask the Error with an Empty Fallback

Wrong:

~~~java
String plain = renderedPlain == null
        ? ""
        : renderedPlain;
helper.setText(plain, renderedHtml);
~~~

This merely hides a missing-template bug. An empty part conveys zero information to text-only clients.

### Not Every Render Error Is Retryable

If a plain template is missing or the model mismatches, repeating SMTP retries solves nothing. Classify as **TEMPLATE_INVALID**, **PLAIN_TEMPLATE_MISSING**, or **RENDER_MODEL_MISSING** and notify the owning team. Retries only make sense when a rendering dependency is temporarily unreachable and paired with backoff.

### Template Validation Is Insufficient Without Runtime Validation

A template may have a plain file on disk while runtime variables produce empty output (for example, all content sits inside an untriggered conditional). Runtime checks must validate **rendered output**, not just template file existence.

## 28. Versioning Plain and HTML Together

A subtle bug arises when only HTML gets updated:

~~~text
Template revision 18:
  plain -> "Promo code valid until 31/12"
  HTML  -> "Promo code valid until 30/11"
~~~

Both parts have valid structure yet inconsistent facts. Content versioning must therefore treat **subject + plain + HTML + assets** as a single approved bundle.

### Editing HTML Requires Checking Plain Impact

Changes that must stay synchronized:

- CTA destination URLs.
- Code/link expiration times.
- Legal terms, privacy notices, or footers.
- Prices, discounts, taxes/fees.
- Verification instructions.
- Contact info and support links.

Not every CSS tweak requires touching the plain body. Yet whenever **facts** change, review both under the same revision.

### Pin Revisions in the Notification Outbox

~~~text
notificationId = N-108
templateRevision = ORDER_CONFIRMED / vi-VN / rev18
modelSnapshot = {...}
retry 1 -> plain18 + html18
retry 2 -> plain18 + html18
~~~

If a retry picks HTML rev19 and plain rev18, a single notification carries conflicting content. The resolver should pin the revision once, and the renderer should fetch all parts from that revision.

### If Plain Was Missing in an Already-Published Revision

Instead of mutating rev18 in place, create rev19 with a proper plain part and send it through validation/approval. Unattempted notifications can migrate per audited policy; already-accepted notifications must never have history silently rewritten.

## 29. Relationship with Transactional Outbox and Retries

Missing plain text can be caught before or after SMTP submission:

~~~text
Business transaction
    |
    v
Outbox notification PENDING
    |
    v
Select pinned template revision
    |
    v
Render plain + HTML
    |
    v
Validate both parts
    |
    +-- Invalid -> TEMPLATE_FAILED / NEEDS_REVIEW
    |
    '-- Valid -> Compose MIME
                       |
                       v
                  SMTP submit
                       |
             +---------+---------+
             |         |         |
          ACCEPTED  PROVEN_FAIL  UNKNOWN
             |         |         |
             v         v         v
           Record    RETRY    Reconcile
~~~

### If Caught Before SMTP

Do not send an HTML-only message best-effort if policy requires a plain alternative. Transition the job to a template-failure state indicating content is not ready; keep the notification key unchanged when retrying after the template is fixed.

### If Caught After the Provider Accepted

The email may already have been delivered to the recipient as HTML-only. Never automatically resend the whole notification just because “plain was missing”, as that creates duplicate emails. If the mistake causes business harm, issue a separate **correction notice** per policy and audit rather than silent retries.

### If the SMTP Outcome Is `UNKNOWN`

A timeout after transmitting DATA does not prove the server never received the message. Do not combine “fix plain” with blind retries, because the recipient could receive both the original HTML-only email and the fixed one. Reconcile first or make a controlled business decision.

### Outboxes Do Not Generate Plain Text Automatically

A transactional outbox makes send intent durable; it does not replace renderers and MIME composition quality gates. A system with an excellent outbox can still fire thousands of HTML-only emails if the composer calls the wrong overload.

## 30. Common Mistakes When Fixing HTML-Only Emails

### Mistake 1 — Changing `setText(html, true)` to `setText(html)`

This turns the entire HTML markup into **text/plain**, so many clients display raw HTML tags. Not a solution.

~~~java
// Not a valid fix.
helper.setText("<p>Hello</p>");
~~~

**Right:** create meaningful plain text and call **setText(plain, html)**.

### Mistake 2 — Sending Two Separate Emails

**Wrong:** `sender.send(messagePlain); sender.send(messageHtml);`. Two messages may arrive separately, breaking notification/dedup logic.

**Right:** one message with `multipart/alternative`.

### Mistake 3 — Calling `setText` Twice

**Wrong:** calling **setText(plain)** then **setText(html, true)** assuming both calls combine into MIME.

**Right:** use the two-String overload.

### Mistake 4 — Swapping Plain and HTML Arguments

**Wrong:** `setText(html, plain)`.

**Right:** `setText(plain, html)`.

### Mistake 5 — Enabling Multipart Without Adding `text/plain`

**Wrong:** initializing the helper with `multipart=true`, then calling only `setText(html, true)`.

**Right:** multipart mode is a structural prerequisite; still pass both plain and HTML.

### Mistake 6 — Treating an Attachment as a Plain Alternative

**Wrong:** HTML + PDF with no `text/plain`.

**Right:** include a proper alternative body; attachments belong in a separate `mixed` relationship.

### Mistake 7 — Stripping HTML with Regex

**Wrong:** `replaceAll("<[^>]+>", "")` loses URLs and mashes text together.

**Right:** a plain template from the same model, or a parser with semantic tests.

### Mistake 8 — Plain Saying Only “View HTML Version”

**Wrong:** text-only users get no actionable content.

**Right:** plain includes key data and URLs.

### Mistake 9 — HTML Link Differs from Plain Link

**Wrong:** HTML button points to URL A while plain points to URL B.

**Right:** one trusted URL in the model, shared by both renderers.

### Mistake 10 — Only HTML Has the OTP

**Wrong:** plain is blank or missing the code.

**Right:** plain contains the OTP and instructions, matching HTML's code.

### Mistake 11 — Plain Lacks Unsubscribe

**Wrong:** marketing HTML has an unsubscribe button while plain offers no way out.

**Right:** both present the policy and appropriate link.

### Mistake 12 — Not Inspecting the MIME Tree

**Wrong:** unit test only asserts `helper.setText()` was invoked.

**Right:** parse the real `MimeMessage` and verify `multipart/alternative` contains both parts.

### Mistake 13 — Checking Only Root `Content-Type`

**Wrong:** requiring `root = multipart/alternative` even when the message has attachments/CIDs.

**Right:** traverse nested structure and verify alternatives.

### Mistake 14 — Hardcoding Assertions on Raw MIME Boundaries

**Wrong:** test matches `boundary="XYZ"` in raw output.

**Right:** use Jakarta Mail's parser and assert on body parts.

### Mistake 15 — Treating SPF/DKIM as a Replacement for `text/plain`

**Wrong:** email is DKIM-signed, so plain isn't needed.

**Right:** authentication and content alternatives solve completely different problems.

### Mistake 16 — Treating `text/plain` as an Inbox Guarantee

**Wrong:** adding plain will always bypass spam folders.

**Right:** plain improves compatibility; deliverability depends on many other factors.

### Mistake 17 — Logging Full Plain/HTML to Debug

**Wrong:** logs contain OTPs, tokens, or order data.

**Right:** log content status/size/hash (when appropriate), opaque notification IDs, and redacted errors.

### Mistake 18 — Skipping Plain During Template Approval

**Wrong:** reviewers only sign off on HTML screenshots.

**Right:** preview and sign off on subject/plain/HTML and actionable links together.

### Mistake 19 — Plain and HTML in Different Languages

**Wrong:** plain is English while HTML is Vietnamese outside policy.

**Right:** unified, verified locale/translation versions.

### Mistake 20 — Building Plain from a Different Model

**Wrong:** HTML renders live order total while plain renders an older snapshot.

**Right:** render both from the same verified business snapshot.

## 31. Distinguishing Content Errors from Transport Errors

An issue that wastes team time is misdiagnosis: **an email being unreadable in a text-only client** does not mean **SMTP failed**.

| Symptom | Layer to Inspect |
| --- | --- |
| Recipient sees raw HTML | Wrong MIME type/`setText` overload |
| Plain text lacks CTA URL | Wrong plain template/converter |
| HTML shows different amount from plain | Template model/revision mismatch |
| SMTP auth failed | Sender credentials/provider, not plain text |
| SMTP read timeout | Transport outcome/reconciliation |
| Mail accepted yet bounced | Downstream delivery/recipient |
| Client blocks HTML, email looks blank | Missing plain alternative or client behavior |
| PDF attachment fails to display | MIME `mixed`/attachment issue |
| CID image fails to load | MIME `related`/`Content-ID`/resource issue |
| Vietnamese diacritics garbled | Charset/encoding/template source |
| `text/plain` not found at root | May have nested MIME; inspect tree |

### Fix at the Right Boundary

If the bug is the composer calling the wrong **setText**, fix the composer and add a MIME regression test. If the bug is a plain template missing a link, fix the template/renderer and add content assertions. If the bug is an SMTP rejection, investigate transport; adding plain text will not necessarily resolve SMTP failures.

### Do Not Resend Just to “See How It Looks”

To investigate, re-render using a synthetic model and send to a **test fixture** or authorized mailbox. Never resend production transactional emails to real customers without a clear business justification.

## 32. Testing Checklist Before Releasing Templates

### MIME and Composer

- For HTML emails, helper uses **setText(plain, html)**.
- Helper is initialized in the proper multipart mode.
- MIME tree includes **multipart/alternative** with both part types.
- Plain is non-blank and not merely a placeholder.
- HTML is fully rendered with no leftover template expressions.
- Attachments/CID do not break the alternative structure.
- Both `text/plain` and `text/html` use charsets suitable for Vietnamese.
- Never issue two SMTP submissions for one notification just to “provide a fallback”.

### Business Content

- Subject, plain, and HTML share the same template revision/model snapshot.
- Order codes, amounts, currencies, deadlines, and statuses match.
- Plain and HTML CTA links use the same trusted URL.
- Contact/unsubscribe/warning instructions appear where required.
- Critical info is never hidden solely inside images or HTML buttons.
- Plain has readable headings/paragraphs/bullets.
- Plain and HTML locales match the recipient.
- Optional/default variables never wipe out content.

### Safety

- From/To/Reply-To/Subject are validated.
- Link tokens have TTLs; raw tokens are never logged.
- User input is never rendered into untrusted HTML/template sources.
- Context-aware HTML escaping and URL validation are enforced.
- No unauthorized tracking CSS/markup is injected.
- Test fixtures use dummy data, never copied real customer records.

### Send Quality

- Run MIME tree unit tests and render-level checks.
- Run SMTP fixture integration tests.
- Preview in both HTML and plain modes.
- Verify on real clients if the product has compatibility requirements.
- Monitor render errors and content policy violations.
- Never auto-resend production messages when an issue is found post-acceptance.

This checklist focuses on **missing plain-text alternatives**; it does not replace all security, consent, SMTP, or deliverability testing across the system.

## 33. Practice Scenarios

### Scenario A — HTML Looks Great Yet Text-Only Is Blank

The application calls:

~~~java
helper.setText(html, true);
~~~

**Q:** How do you fix it?

**A:** Build a complete plain version from the same model and use **helper.setText(plain, html)** with the right multipart mode. Inspect the MIME tree after composition, not just the HTML preview.

### Scenario B — Calling `setText` Twice

Developer writes:

~~~java
helper.setText(plain);
helper.setText(html, true);
~~~

**Q:** Does this reliably create two alternatives?

**A:** No. That is not the API contract for creating alternatives; use the two-String overload.

### Scenario C — Plain Says Only “Click here”

HTML has a button to a critical URL, while plain says only “Click here”.

**Q:** Is this a sufficient fallback?

**A:** No. Text-only clients cannot see the URL; include the full URL or an equivalent way to complete the action.

### Scenario D — Plain and HTML Have Two Different OTPs

Both renderers call `generateOtp()` independently.

**Q:** What must be fixed besides MIME?

**A:** Generate one OTP in the business service, share one model, and render both parts. Never generate new codes inside templates.

### Scenario E — Root Is `multipart/mixed`

The email has plain+HTML+PDF; the test only accepts a `multipart/alternative` root.

**Q:** Is the test right?

**A:** No. The root can be `mixed`/`related`; locate the nested alternative and verify both body parts.

### Scenario F — HTML Has Images Blocked

HTML shows status only inside a banner image; plain omits status.

**Q:** How does plain help?

**A:** Plain must state the status in words. HTML should also include alt text/semantic content; never use plain as an excuse to skip HTML accessibility.

### Scenario G — HTML-Only Email Accepted by SMTP

The server returns 250 OK, while QA reports text-only content is missing.

**Q:** Is this an SMTP error or a content error?

**A:** A content/MIME composition error. SMTP acceptance does not validate MIME alternative quality.

### Scenario H — HTML Link Replaced After Retry

The first attempt used URL X; on retry, plain got URL Y because the service regenerated the token.

**Q:** What is the risk?

**A:** Inconsistency within the same notification, or even two links with differing TTLs/permissions. Pin revision/model/link policies and classify outcomes before retrying.

### Scenario I — Vietnamese Subject Correct but Body Diacritics Garbled

The helper sets UTF-8 on the subject, yet HTML/plain sources are read using another charset.

**Q:** Is changing `Content-Transfer-Encoding` alone enough?

**A:** No. Control charsets across template files, renderers, and MIME parts; transfer encoding only transports bytes and cannot repair mis-decoded text.

### Scenario J — Email with PDF Invoice

HTML body says “Invoice attached”, while plain is empty.

**Q:** Does the PDF replace plain text?

**A:** No. Plain should explain the message type, order code, how to open the attachment, and support contact info. The PDF is a separate `mixed` attachment.

### Scenario K — Unsubscribe Footer Only Inside HTML

A marketing email lacks the unsubscribe URL in plain text.

**Q:** What needs fixing?

**A:** Include proper instructions/links in plain text, enforce consent/suppression policies on the server, and check dedicated unsubscribe headers if applicable.

### Scenario L — Plain Generated by Regex

HTML has an `<a>` tag with a URL in `href`; the converter outputs “Track order” without the link.

**Q:** Does replacing regex with a parser automatically make it right?

**A:** A parser helps handle structure, yet you still need rules to emit `href`s and content tests. For critical CTAs, a plain template from the same model is usually better.

### Scenario M — Plain Generated from an Older HTML Version

HTML rev19 says “7 days”, while plain rev18 says “14 days”.

**Q:** Is this a MIME error?

**A:** MIME alternatives may be structurally valid yet semantically wrong. Pin and review subject/plain/HTML under the same revision and test business facts.

### Scenario N — User Prefers Text-Only

The product still sends HTML-only emails.

**Q:** Can you rely on the client auto-converting?

**A:** Some clients do, yet conversion is not guaranteed to keep links/tables. Proactively providing a plain alternative is far more reliable.

### Scenario O — Test Checks `multipart=true`

A unit test asserts the root is MIME multipart without inspecting parts.

**Q:** Can this catch HTML-only emails?

**A:** No. Multipart can come from attachments or related resources. Tests must inspect alternatives and content.

### Scenario P — Empty Plain Text

Developer writes:

~~~java
helper.setText("", html);
~~~

**Q:** Does this count as fixed?

**A:** No. An empty part is not a useful alternative. Runtime validators must reject it when policy requires plain text.

### Scenario Q — HTML Present, Plain Contains Raw Markup

Plain is the exact same HTML string passed into the `plain` argument.

**Q:** What is wrong?

**A:** The `text/plain` MIME type makes clients render raw tags as literal text rather than an edited text representation. Generate clean text free of unnecessary markup.

### Scenario R — Emails Already Accepted with Missing Plain

Thousands of emails were submitted to SMTP before the team realized `text/plain` was missing.

**Q:** Should all of them be auto-resent?

**A:** No. Resending risks duplicates and annoys recipients. Assess impact, distinguish accepted/`UNKNOWN`, and decide whether a separate correction notice is needed or only fix future notifications.

### Scenario S — Plain and HTML Show Different Contact Addresses

Plain lists `support-old@example.test`; HTML lists `support@example.test`.

**Q:** What should be checked?

**A:** Share one contact configuration/model and template revision, and test business-meaningful fields rather than merely checking part presence.

### Scenario T — HTML-Only Suspected of Causing Spam Placement

The team sees deliverability drop and notices plain text is missing.

**Q:** Does fixing plain text guarantee Inbox recovery?

**A:** No. Adding plain improves MIME quality, yet you still must check authentication, reputation, bounces/complaints, consent, content, and provider policies.

## 34. Runbook for Fixing HTML-Only Issues in Production

### Step 1 — Define Scope

Gather:

~~~text
templateKey:
templateRevision:
mailPurpose:
affectedLocale:
affectedTenant:
firstAffectedAt:
numberCreated:
numberSubmitted:
numberPending:
numberUnknown:
~~~

Never print plain/HTML containing PII or link tokens into logs just to count them.

### Step 2 — Pinpoint Where It Broke

- Renderer did not produce plain text?
- Renderer returned blank plain text?
- Composer called the wrong overload?
- Composer called only `setText(html, true)`?
- Adding attachments/CID broke the MIME tree?
- Plain template version drifted from HTML?
- SMTP adapter re-rendered content with a different template?

A **synthetic/test** MIME sample reveals what is missing without resending to real customers.

### Step 3 — Fix at the Right Layer

~~~text
Plain template missing
  -> Create reviewed plain template

Renderer output empty
  -> Fix variable/conditional/schema

Wrong helper overload
  -> Use setText(plain, html)

Nested MIME broken
  -> Adjust multipart mode and addInline/addAttachment order

Plain/HTML facts mismatch
  -> Shared model snapshot / revision validation
~~~

### Step 4 — Test Before Release

Run tests:

- MIME tree unit tests, both positive and negative.
- Render-level content assertions for codes, links, and amounts.
- MIME integration tests against an SMTP fixture.
- Plain/HTML previews using synthetic data.
- Cases with attachments/CIDs/multiple locales.

This is a suggested workflow for production systems. Within the scope of authoring this STEP 4 lesson, only documentation is written, **without running content QA or Gradle**.

### Step 5 — Handle Pending Notifications

If the system uses a template registry/outbox:

- Notifications with **no SMTP attempt yet** can be fixed/migrated per content policy.
- Notifications **IN_FLIGHT/UNKNOWN** must not have content swapped and be blindly retried.
- Notifications **ACCEPTED** are already with the provider; do not rewrite history to pretend they had plain text.
- Notifications **RENDER_FAILED before submission** can retry once the template is fixed if policy permits.

### Step 6 — Monitor After Release

- Rate of messages containing both plain+HTML per composer tests/observability.
- Render failures and missing-plain errors.
- Pending jobs not climbing due to invalid templates.
- Provider accepted/bounced rates if correlated.
- Feedback from text-only clients and any content mismatches.

### Step 7 — Prevent Recurrence

Add a **quality gate** at template publish/renderer time: if an email purpose requires HTML+plain, block publishing or submission when plain is missing. This guard beats manual reminders sitting in a checklist.

## 35. Observing with Metrics and Logs

A production system can define dedicated metrics for render quality:

| Logical Metric | Type | Meaning |
| --- | --- | --- |
| **mail_content_render_total** | Counter | Render count by outcome |
| **mail_content_missing_plain_total** | Counter | Missing/blank plain detected |
| **mail_content_alternative_validation_total** | Counter | Two-part validation outcomes |
| **mail_content_mime_compose_total** | Counter | MIME composer success/failure |
| **mail_content_render_seconds** | Timer | Render duration |
| **mail_content_template_schema_error_total** | Counter | Template/model mismatches |
| **mail_content_cta_mismatch_total** | Counter | CTA URL mismatches caught by test/policy |
| **mail_content_pending_due_template** | Gauge | Pending notifications blocked on template error |

These are **application-designed metrics**, not built-in `JavaMailSender` metrics. With Prometheus, counters may export with the **_total** suffix; verify exact names in your registry.

### Safe Tags

~~~text
purpose=security|transactional|marketing
result=success|missing_plain|template_invalid
renderer=thymeleaf|custom
locale=vi-VN|en-US|other
~~~

Never put recipient email, OTP, token, order ID, or raw Subject/HTML into metric labels. With many template revisions, inspect per-revision stats via controlled logs/audits instead of high-cardinality labels.

### Structured Log Example

~~~text
event=mail_content_validation_finished
notification_id=opaque-N-108
template_key=ORDER_CONFIRMED
template_revision=18
has_plain=true
has_html=true
plain_chars=420
html_chars=1038
validation_result=SUCCESS
~~~

Part length cannot replace content semantic checks; a long plain-text body can still miss a URL. Still, metadata catches widespread blank-body regressions without storing sensitive payloads.

### Never Monitor Content via Raw Logs

If a team needs to inspect a real email reported by a customer, use a separate authorized workflow with auditing, retention limits, and PII/token redaction. Never turn on SMTP protocol debug or dump raw MIME uncontrollably in production.

## 36. Migrating Legacy HTML-Only Systems to Include Plain Text

A long-running system may have dozens of HTML-only templates. Fixing one `setText` line in the composer **is not enough** if the renderer has no plain content to pass.

### Migration Steps

~~~text
Inventory existing templates
       |
       v
Classify: security / transactional / marketing
       |
       v
Identify critical facts and CTA links
       |
       v
Create plain templates from canonical models
       |
       v
Version and review subject/plain/HTML together
       |
       v
Update composer to setText(plain, html)
       |
       v
Add MIME + semantic regression tests
       |
       v
Canary deployment / verify SMTP fixture
       |
       v
Monitor render failures and user feedback
~~~

### Start with Critical Templates

Prioritize:

1. Account verification / password reset / OTP.
2. Receipts, invoices, order confirmations.
3. Security changes or deadline notices.
4. Support emails with critical CTAs or attachments.
5. Marketing/newsletters.

Exact order also depends on recipient volume, business risk, and compliance requirements; the common thread is keeping key facts accessible when clients do not render HTML.

### What If Dozens of Plain Templates Cannot Be Written Immediately?

You can adopt an **HTML-to-text converter backed by an HTML parser** with rules preserving links, lists, and tables for the transition phase. Still:

- Never accept empty converter output.
- Test against real templates, especially CTAs.
- Never treat the converter as a semantic guarantee.
- Plan to author reviewed plain templates for critical emails.

Never convert with a simplistic regex and declare the problem solved.

### Classify Legacy Email State

The system may already have sent HTML-only messages to recipients. Migration cannot retroactively change sent MIME. Never resend historical records just to add plain text. Issue a correction notice only if a real user-impacting problem exists and business stakeholders approve.

## 37. Policy by Notification Type: Do Not Force One Rule on Every Email

Different email types have different requirements:

| Type | Core Content | Suitable Policy |
| --- | --- | --- |
| **Plain-only system alert** | Short text, no styling needed | Single `text/plain`, HTML not required |
| **HTML transactional** | Order code, link, price, status | Require `text/plain` + `text/html` |
| **Security/OTP with HTML** | Code/token/TTL and warnings | Require full fallback, verify consistency |
| **Marketing HTML** | Promotional content, CTA, unsubscribe | Require complete plain, review footer/consent |
| **HTML + attachment** | Explanation and file | Alternative pair for body; separate attachment |
| **HTML + CID images** | Image-rich content | Alternative pair + related resources |
| **Raw MIME forward** | Forwarding an existing message | Dedicated MIME handling/preservation policy; do not alter blindly |

### Design Explicit Content Policies

~~~java
public enum MailBodyPolicy {
    PLAIN_ONLY,
    HTML_WITH_PLAIN_ALTERNATIVE
}

public record MailTemplatePolicy(
        String templateKey,
        MailBodyPolicy bodyPolicy
) {
}
~~~

Renderer/composer branches on policy:

~~~text
PLAIN_ONLY
  -> setText(plain)

HTML_WITH_PLAIN_ALTERNATIVE
  -> validate plain nonblank
  -> validate html nonblank
  -> setText(plain, html)
~~~

This avoids the opposite mistake: fixing HTML-only bugs by forcing every trivial system alert to generate HTML needlessly.

### Enforce Policy at a Standardized Boundary

If every developer chooses which `setText` overload to call inside business services, bugs creep back in. Centralize around a shared **MailComposer** accepting a **RenderedMailContent** object and enforcing policy in one place.

### Rejecting Differs from Falling Back

If policy requires both parts and plain is missing, never fall back automatically to HTML-only just to “keep sending”. A clearer choice is to **fail validation** before SMTP, move the notification into a fixable state, and alert. Use another fallback policy only if explicitly defined and reviewed.

## 38. Example Composer Enforcing Policy and Pre-Send Validation

The example below centralizes the MIME body decision in one class instead of letting services call overloads directly:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class PolicyAwareMailComposer {

    private final JavaMailSender sender;

    public PolicyAwareMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(
            String verifiedFrom,
            String recipient,
            MailContent content,
            MailBodyPolicy bodyPolicy
    ) throws MessagingException {
        requireText(verifiedFrom, "from");
        requireText(recipient, "recipient");
        requireText(content.subject(), "subject");
        requireText(content.plain(), "plain text");

        if (content.subject().contains("\r")
                || content.subject().contains("\n")) {
            throw new IllegalArgumentException(
                    "Subject must be a single line"
            );
        }

        MimeMessage mime = sender.createMimeMessage();

        if (bodyPolicy == MailBodyPolicy.PLAIN_ONLY) {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mime, false, "UTF-8"
            );
            setEnvelope(helper, verifiedFrom, recipient,
                    content.subject());
            helper.setText(content.plain());
        } else if (bodyPolicy
                == MailBodyPolicy.HTML_WITH_PLAIN_ALTERNATIVE) {
            requireText(content.html(), "HTML body");
            MimeMessageHelper helper = new MimeMessageHelper(
                    mime, true, "UTF-8"
            );
            setEnvelope(helper, verifiedFrom, recipient,
                    content.subject());
            helper.setText(content.plain(), content.html());
        } else {
            throw new IllegalArgumentException(
                    "Unsupported mail body policy"
            );
        }

        sender.send(mime);
    }

    private static void setEnvelope(
            MimeMessageHelper helper,
            String verifiedFrom,
            String recipient,
            String subject
    ) throws MessagingException {
        helper.setFrom(verifiedFrom);
        helper.setTo(recipient);
        helper.setSubject(subject);
    }

    private static void requireText(
            String value,
            String fieldName
    ) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing " + fieldName
            );
        }
    }
}
~~~

This snippet uses **MailContent** and **MailBodyPolicy** defined earlier. It illustrates **guarding against missing plain text**; it does not replace recipient validation, verified sender identity, URL validation, consent/suppression, outboxes, SMTP timeouts, or send-outcome classification. **sender.send(...)** can throw runtime `MailException` besides `MessagingException`; production workers must classify outcomes and avoid blind retries when SMTP outcomes are unknown.

### Why Centralize the Right Overload Inside the Composer?

All HTML-capable flows go through one branch:

~~~java
helper.setText(content.plain(), content.html());
~~~

With one shared standard, MIME unit tests live on the composer class rather than repeating them across hundreds of business services. Business services still need tests for their specific content/URLs.

### Testing Plain-Only Policy

A plain-only email:

~~~java
MailContent content = new MailContent(
        "Server recovered",
        "Service is operational again.",
        null
);

composer.send(
        "ops@example.test",
        "admin@example.test",
        content,
        MailBodyPolicy.PLAIN_ONLY
);
~~~

This is not an HTML-only bug because HTML was never requested. Validation must fit the purpose.

### Testing HTML+Plain Policy

~~~java
MailContent content = new MailContent(
        "Order ORD-1528 confirmation",
        "Order ORD-1528 has been confirmed.\n"
                + "View: https://app.example.test/orders/ORD-1528",
        "<p>Order <b>ORD-1528</b> has been confirmed.</p>"
                + "<p><a href=\"https://app.example.test/orders/"
                + "ORD-1528\">View details</a></p>"
);

composer.send(
        "orders@example.test",
        "customer@example.test",
        content,
        MailBodyPolicy.HTML_WITH_PLAIN_ALTERNATIVE
);
~~~

If plain is an empty string, the composer stops before SMTP submission per policy.

## 39. Decision Flowchart When Sending HTML Email

~~~text
                   Prepare email
                         |
                         v
                   HTML required?
                   |           |
                  No          Yes
                   |           |
                   v           v
              Plain body   Render from shared model
                   |           |
                   v           +---------+---------+
               Validate        |                   |
                   |           v                   v
                   v       text/plain          text/html
              setText(plain)   |                   |
                   |           +---------+---------+
                   |                     |
                   |                     v
                   |              Validate consistency
                   |                     |
                   |              +------+------+
                   |              |             |
                   |           Invalid         Valid
                   |              |             |
                   |              v             v
                   |         Reject/Review   setText(plain, html)
                   |                            |
                   +-------------+--------------+
                                 |
                                 v
                           Compose MimeMessage
                                 |
                                 v
                        Optional CID/attachments
                                 |
                                 v
                          Inspect MIME policy
                                 |
                          +------+------+
                          |             |
                       Invalid         Valid
                          |             |
                          v             v
                      Fix/review      SMTP submit
                                        |
                                        v
                                Track provider outcome
~~~

**MIME policy inspection** can serve as a test quality gate and runtime validator depending on cost/architecture. You do not need to re-parse every message in production if the composer enforces a strict contract with thorough tests, yet you must have a way to catch regressions.

## 40. Summary Cheat Sheet

~~~text
setText(html, true)
    -> HTML body, does not auto-generate plain alternative

setText(plain, html)
    -> requests creating text/plain + text/html alternatives

multipart/alternative
    -> multiple representations of the same content

multipart/mixed
    -> independent components, e.g. attachments

multipart/related
    -> linked resources to render HTML (CID images)

One mail with alternatives
    != sending two separate emails

Plain part exists
    != useful plain part if content is empty

HTML-to-text regex
    != guaranteed preservation of URLs and business meaning

Shared model snapshot
    -> keeps codes, amounts, OTPs, deadlines, and links consistent

Rendered content validator
    -> blocks missing plain text before SMTP

MIME tree test
    -> confirms proper alternative relationship

Plain text
    -> helps text-only clients and downstream tools

Plain text
    != guaranteed Inbox placement

SMTP accepted
    != recipient received/read

Content bug after SMTP accepted
    != reason to auto-resend
~~~

**Creating HTML while forgetting the plain-text alternative** is a common bug because emails still look fine in some clients and SMTP still accepts the message. Fixing it takes more than passing a dummy string for the second parameter: the application must supply a **meaningfully equivalent `text/plain` version** alongside **`text/html`**, especially for verification codes, amounts, deadlines, URLs, and mandatory instructions. In Spring Framework Mail, **MimeMessageHelper.setText(plainText, htmlText)** is the direct way to build alternatives in one MIME message; with CID images or attachments, parts must remain nested under proper **alternative / related / mixed** relationships. For production systems, render both from one validated model/template revision, add quality gates and MIME tests, preview in text-only mode, and separate content bugs from transport errors. That way emails look great while still offering a clean reading and processing path when HTML is not displayed.
