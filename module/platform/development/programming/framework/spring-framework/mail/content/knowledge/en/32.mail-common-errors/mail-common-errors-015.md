# Not Testing the Message in Real Mail Clients

A Spring Framework Mail application can call `JavaMailSender.send(...)` successfully, receive an acceptance code from the SMTP server, and pass unit tests checking `MimeMessage`, yet when recipients open the email in Outlook, Gmail, or a mobile mail app they see **broken layouts, missing images, tiny text, hard-to-tap buttons, overflowing tables, or truncated key content**. This is a common mistake when a development team only inspects raw HTML or previews it in a web browser without **testing the message in real mail clients**.

HTML emails do not behave like ordinary web pages. Every mail client has its own mechanisms for handling HTML, CSS, images, fonts, dark mode, links, attachments, and security. The exact same MIME message can render differently across Outlook versions on Windows, Gmail web, Gmail mobile, Apple Mail on iOS/macOS, or an enterprise webmail client. Even within the same application, settings such as **dark mode, blocked images, system font scaling, narrow reading panes, and forwarded messages** can alter the result.

This lesson in the **Common Errors** chapter of the **Spring Framework Mail** module focuses on the causes, symptoms, and prevention workflow for **“Not Testing the Message in Real Mail Clients”**. We will distinguish SMTP/MIME testing from rendering testing, build a mail client matrix, design compatible messages, check text/plain and HTML, handle CIDs/attachments, test multilingual content, dark mode, accessibility, links, tracking, and security. Examples use `JavaMailSender` and `MimeMessageHelper`, alongside techniques for testing against real test mailboxes instead of sending to production customers.

> **Core principle:** *SMTP accepted the email* does not mean *the user can read, understand, and act on the email properly*. To know the end experience, you must observe the message in mail clients representative of your recipients.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain why testing HTML in a browser is insufficient to confirm an email works.
2. Distinguish **unit tests**, **SMTP capture tests**, **MIME structure tests**, and **mail client rendering tests**.
3. Recognize common differences across web, desktop, and mobile clients as well as display modes.
4. Design `multipart/alternative`, `multipart/related`, and `multipart/mixed` properly in Spring Mail.
5. Verify plain text fallbacks, UTF-8 charsets, subjects, headers, inline images, and attachments.
6. Apply HTML/CSS using **progressive enhancement**, optimizing readability when styles or images are blocked.
7. Build a prioritized test matrix based on real users, templates, clients, devices, and networks.
8. Organize sending to allowlisted **test mailboxes** without using real data or bothering users.
9. Collect screenshots, raw MIME, and environment details sufficient to reproduce bugs.
10. Handle regressions and separate MIME build bugs, delivery errors, rendering bugs, and interaction bugs.

## 2. Why is email not like a website?

When opening a website, a browser receives HTML/CSS/JavaScript and executes them in a relatively capable browser environment. A mail client receives a **MIME email** from the mail system, then applies its own security and presentation rules.

```text
Spring application
      |
      v
MimeMessage
  - MIME headers
  - text/plain
  - text/html
  - inline image parts
  - attachment parts
      |
      v
SMTP provider / Receiving MTA
      |
      v
Receiving mail service
  - scanning
  - content filtering
  - link/image proxying (varies by system)
      |
      v
Mail client rendering engine
      |
      +-- Gmail web
      +-- Outlook desktop/web
      +-- Apple Mail desktop/mobile
      +-- Other Android/iOS clients
      |
      v
User views and interacts with the email
```

A mail client may:

- Strip or alter disallowed HTML tags and CSS rules.
- Lack support or offer only partial support for certain CSS properties.
- Block remote images until the user consents.
- Rewrite or proxy URLs.
- Alter colors when dark mode is active.
- Substitute fonts according to the operating system.
- Interpret `multipart/alternative` differently if the MIME structure is malformed.
- Display attachments/inline images differently than a browser.
- Re-quote content in its own way on Reply or Forward.
- Enlarge text or alter layout according to accessibility settings.

Do not apply a rigid list claiming “client X always supports CSS Y” across every version, as products change engines and policies over time. The reliable approach is **combining compatibility principles with testing on target client versions**.

## 3. Four independent testing layers

| Layer | Common tools | What it checks | What it does NOT prove |
| --- | --- | --- | --- |
| Unit test | JUnit, Mockito | Data mapping, escaping, routing, composer logic | Real clients will render cleanly |
| SMTP capture | GreenMail, Mailpit/MailHog, or test server | Message submitted, some MIME headers/parts | Gmail/Outlook/Apple Mail display cleanly |
| MIME inspection | Jakarta Mail parser, raw .eml | Part tree, content types, charsets, CIDs, filenames | Dark mode/responsive layout compatibility |
| Real mail client | Test mailboxes and real apps | Layout, usability, images, readability, links | Identical results across all users or versions |

The layers complement one another. If an email has the wrong `Content-Type`, MIME tests catch it earlier than manual client testing. If MIME is valid yet the CTA button is tiny in Outlook desktop, testing in a real client reveals it.

### An easily misunderstood case

```text
JUnit:        PASS
SMTP test:    PASS
HTML preview: PASS
Gmail mobile: CTA overflows screen edge
Outlook:      Pricing table loses columns
Apple Mail:   Logo disappears in dark mode
```

The first three PASS results are not “wrong”; they simply verify **different properties**. The mistake is skipping the rendering layer.

## 4. What does “sent successfully” mean?

`JavaMailSender.send(...)` not throwing an exception usually only indicates **SMTP submission** completed according to transport evidence. Afterward, the provider or remote server may accept, defer, bounce, or filter the message.

```text
Application composed message
          |
          v
SMTP SUBMITTED
          |
          v
REMOTE DELIVERED (if feedback exists)
          |
          v
Mailbox placement
          |
          v
Mail client renders
          |
          v
Recipient can understand and act
```

A **client rendering bug** does not automatically imply an **SMTP submission** failure. Conversely, if an email never arrives in the test mailbox, investigate delivery before tweaking CSS.

## 5. Typical signs you have not tested in real clients

Common user reports:

- “The email displays raw HTML tags verbatim.”
- “In Outlook the confirm button turned into plain blue text with no background.”
- “The order summary table overflows my phone screen.”
- “White text on a white background in dark mode.”
- “The logo is missing when image loading is off.”
- “The attachment opens in one app, yet shows a garbled name in another.”
- “Vietnamese diacritics in the subject or body are corrupted.”
- “Links wrap awkwardly and are hard to tap.”
- “I only see an image, with no notification text.”
- “Forwarding the email breaks the entire layout or turns documents into weird attachments.”
- “The email renders plain text even though HTML was sent.”
- “The OTP code is too small to read with larger system text enabled.”

Some issues stem from MIME/composer code, others from client rendering engines, content filtering, templates, or networks. **Classify before fixing.**

## 6. One email template can pass through many clients

A single user may read the same email on multiple devices:

```text
Recipient mailbox
      |
      +-- Webmail on laptop
      |
      +-- App on Android/iOS
      |
      +-- Desktop client via IMAP/Exchange
      |
      +-- Forwarded to another organization
```

Hence “testing once in Chrome” is never enough. Testing should follow **recipient client usage share**, notification type, and content criticality, rather than trying to test every client ever built.

## 7. Browser previews do not represent mail clients

When rendering HTML in a browser preview page:

```html
<html>
  <head>
    <style>
      .cta {
        display: flex;
        gap: 16px;
        background: #2463eb;
      }
    </style>
  </head>
  <body>
    <div class="cta">Confirm order</div>
  </body>
</html>
```

Browsers support `display:flex` and `gap` completely, whereas some mail clients strip styles or lack equivalent support. A clean browser preview never guarantees the email reads properly.

For critical transactional emails, prioritize:

- Logical reading order directly in HTML source.
- Simple layouts with fallbacks.
- Inline styles or techniques verified for target clients.
- Presentation tables when compatibility with constrained HTML clients is needed.
- Text/links remaining understandable if button styling disappears.
- Font sizes and spacing usable on mobile.
- Plain text alternatives giving users/clients another reading path.

## 8. Differences across mail client families

| Client family | What usually needs checking | Do NOT assume |
| --- | --- | --- |
| Gmail web | Sanitized HTML/CSS, images, clipping, mobile viewport | Same as a normal browser tab |
| Gmail mobile | Width, font sizing, dark mode, links | Same as Gmail desktop |
| Classic Outlook desktop | Tables, spacing, button backgrounds, fonts, images | Same as Outlook web or newer builds |
| Outlook web/newer clients | CSS/layout in the corresponding engine | Same across all Outlook versions |
| Apple Mail desktop | Retina images, typography, dark mode | Same as mobile clients |
| Apple Mail iOS | Dynamic text, viewport, tap targets, dark mode | Same as macOS |
| Enterprise clients | Proxies, security policies, attachment controls | Same as personal test accounts |
| Text-only/readers | Plain text, links, and reading order | HTML is always displayed |

This table describes **areas to inspect**, not a universal “CSS support” chart for every version. Systems behind compliance/DLP gateways can also alter emails before they reach the client app.

## 9. Classic Outlook and webmail can render differently

In many environments, traditional Outlook desktop versions use a different engine and layout behavior than Outlook web or newer clients. CSS choices such as positioning, complex backgrounds, forms, or certain responsive techniques can behave differently.

An email should be tested at least on:

1. The actual Outlook version used by the recipient organization.
2. Outlook web if recipient groups use it.
3. Outlook mobile if mobile share is significant.
4. Dark/light modes if colors carry meaning.
5. Image-blocked mode or narrow preview panes.

Never take a screenshot from generic “Outlook” and conclude all Outlook editions behave identically. When filing bugs, record **version, OS, account type, and rendering settings**.

## 10. Gmail web and mobile apps can differ

The same Gmail mailbox can render differently in webmail vs the mobile app. Beyond CSS, factors include:

- Whether images load directly or via proxy.
- Image loading turned off.
- Long content collapsed or clipped under certain conditions.
- Links rewritten/scanned.
- App/OS dark mode.
- Screen width and text scaling.

Thus a screenshot from Gmail desktop web is **one test case**, not a conclusion for the entire Gmail platform.

## 11. Apple Mail and devices with Dynamic Type

iOS/macOS users can increase text size, enable dark mode, or read on very narrow screens. When testing:

- Does content overflow when font size increases?
- Do buttons remain easy tap targets?
- Does text get squeezed inside narrow columns?
- Do logos or icons keep enough contrast when backgrounds change?
- Do links stay recognizable if colors shift?
- Are alt text and descriptive copy meaningful when images do not load?

Do not merely compare pixel-perfect screenshots at a single screen size. **Readability and usability** matter more than matching mockup colors within a few hex units.

## 12. Define “correct” before testing

An email does not have to look pixel-identical across every client. Define:

**Mandatory criteria:**

- The recipient sees the core information clearly and it reaches the right person.
- Subject and preheader are not misleading.
- Content, amounts, dates/times, and order IDs are accurate.
- CTAs have accurate labels, URLs, and behavior.
- Content remains readable with dark mode on and images off.
- No leaked Bcc, unnecessary tokens, or sensitive metadata.
- Mobile does not drop essential content.
- Attachments and alt text are appropriate.

**Acceptable differences:**

- Minor font fallback differences.
- Rounded borders disappearing in some clients.
- Shadows or animations not rendering.
- Slight spacing variations while layout remains easy to read.

These criteria keep testing focused on **functionality and accessibility**, rather than chasing impossible pixel perfection.

## 13. The more critical the template, the higher the testing bar

| Email type | Risk if misrendered | Priority checks |
| --- | --- | --- |
| OTP/password reset | User cannot authenticate | Code/link clarity, expiry, copy/paste |
| Payment confirmation | Misread amount/transaction | Number tables, currency, attachments |
| Invoice | Missing legal details/file | PDF/filename, tables, encoding |
| Security alert | User misses warning | Prominent text and CTA even without images |
| Marketing email | Conversion/brand, opt-out | Mobile, dark mode, unsubscribe |
| Scheduled report | Tables, charts, data | Fallbacks for chart images and key figures |
| Internal system email | Support/ops actions | Text-only, links, safe logging/tracking |

A marketing campaign might tolerate a missing drop shadow; an OTP email cannot tolerate an obscured code or low-contrast text.

## 14. Never send test emails to real customers

Mail client testing must use **test mailboxes** and synthetic data. If staging uses a production recipient list, a single test can bother users or leak information.

Rules:

1. Maintain an allowlist of approved test recipient addresses.
2. Separate test sender domains/accounts/subdomains where appropriate.
3. Never use production tokens, passwords, real invoices, or real Bcc recipients.
4. Prefix subjects clearly with `[TEST]` when appropriate.
5. Use synthetic customer/transaction IDs.
6. Never launch a wide campaign just to test one template.
7. Cap rates and quotas to protect domain reputation.
8. Track test email retention and clean up mailboxes per policy.
9. Ensure CTA links point to safe staging/test services.
10. Never attach screenshots containing real PII to issue trackers.

## 15. One passing mail client test does not prove system-wide deliverability

When a seed mailbox receives an email:

- It proves **that sending route and client** received and rendered the fixture under test conditions.
- It does not prove all production users receive emails.
- It does not establish Inbox placement rates across every domain.
- It does not confirm compatibility with every client version.
- It does not prove email URLs are secure if someone else holds the token.

Combine client tests with submission/delivery telemetry rather than substituting pretty screenshots for bounce or complaint monitoring.

## 16. Before checking visuals: MIME must be valid

An email is more than an HTML string. It contains:

```text
RFC-style mail headers
  From
  To / Cc
  Subject
  Date
  Message-ID
  MIME-Version
  Content-Type
  Content-Transfer-Encoding

Message body
  text/plain
  text/html
  inline resources
  attachments
```

If the MIME tree is wrong, a mail client may:

- Pick the wrong alternative.
- Display HTML as raw text.
- Fail to find CID images.
- Show inline images as attachments.
- Fail to decode expected filenames/charsets.
- Flag the email as having an attachment even when it is just an inline logo.

Therefore test **MIME structure** first before evaluating rendering results.

## 17. A multi-format MIME structure

For an email with text, HTML, an inline image, and a PDF:

```text
multipart/mixed
  |
  +-- multipart/related
  |     |
  |     +-- multipart/alternative
  |     |     +-- text/plain; charset=UTF-8
  |     |     +-- text/html; charset=UTF-8
  |     |
  |     +-- image/png; Content-ID:<brand-logo>
  |
  +-- application/pdf; Content-Disposition: attachment
```

This is an **illustrative valid structure**, not the sole MIME tree produced by every library. Actual nesting order must be parsed/verified against the generated message and client contracts.

Meaning:

- `multipart/alternative`: alternative representations of the same content; typically plain text and HTML.
- `multipart/related`: HTML body plus referenced resources such as CID images.
- `multipart/mixed`: combines content body with standalone attachments.

If assembled improperly by hand, opening in a single client may miss bugs: one client auto-corrects it while another renders broken output.

## 18. Sending text/plain and text/html together

In Spring Mail, `MimeMessageHelper` offers:

```java
helper.setText(plainText, htmlText);
```

This builds content in two alternative formats so the mail client chooses the suitable part.

Example:

```java
String plainText = """
    Hello,

    Order T-454 has been confirmed.
    View details: https://portal.example.org/orders

    Best regards.
    """;

String htmlText = """
    <html>
      <body>
        <p>Hello,</p>
        <p>Order <strong>T-454</strong>
           has been confirmed.</p>
        <p><a href="https://portal.example.org/orders">
           View details</a></p>
      </body>
    </html>
    """;

helper.setText(plainText, htmlText);
```

### Why must plain text never be forgotten?

- Some clients/user settings prefer text-only.
- Accessibility tools can extract content more reliably.
- Forward/reply/copy-paste may pick the plain text version.
- Core content remains usable when HTML is blocked or fails to parse.
- Some security gateways inspect the text alternative.

**Plain text must convey the same core business facts**, not just “Please enable HTML”. For OTP or confirmation-link emails, the text part also needs the relevant data and links.

## 19. Verify content parity between both alternatives

A bug:

```text
text/plain:
  Your order total is 150,000 VND.

text/html:
  Your order total is 1,500,000 VND.
```

If both versions are rendered from separate code paths, a business change can introduce contradictory content.

Solution:

1. Build a **validated template model**.
2. Use the exact same numbers, dates, and order IDs to render plain and HTML.
3. Unit test key fields across both representations.
4. Open the email in at least one text-only client or plain-text view mode.
5. Check links and CTA wording.

Formatting differences are normal; **transactional data discrepancies are critical bugs**.

## 20. Spring Boot example: building a test email with MimeMessageHelper

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailClientPreviewSender {

    private final JavaMailSender mailSender;

    public MailClientPreviewSender(
            JavaMailSender mailSender
    ) {
        this.mailSender = mailSender;
    }

    public void sendToAllowedTestRecipient(
            String testRecipient
    ) throws MessagingException {
        ensureRecipientIsAllowlisted(testRecipient);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("mail-test@example.org");
        helper.setTo(testRecipient);
        helper.setSubject("[TEST] Order T-454 confirmation");

        String plain = """
                Order T-454 confirmed.
                View details: https://portal.example.org/orders
                """;

        String html = """
                <html>
                  <body style="margin:0;padding:0">
                    <table role="presentation"
                           width="100%" cellpadding="0"
                           cellspacing="0" border="0">
                      <tr>
                        <td align="center">
                          <table role="presentation"
                                 width="600"
                                 cellpadding="0"
                                 cellspacing="0" border="0">
                            <tr><td style="padding:24px">
                              <img src="cid:brand-logo"
                                   alt="Brand"
                                   width="120" height="40"
                                   style="display:block">
                              <h1 style="font-size:24px">
                                Order confirmation
                              </h1>
                              <p>Order T-454
                                 confirmed.</p>
                              <a href="https://portal.example.org/orders">
                                View details
                              </a>
                            </td></tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </body>
                </html>
                """;

        // Main content before adding inline resources.
        helper.setText(plain, html);

        helper.addInline(
                "brand-logo",
                new ClassPathResource("mail/test-logo.png")
        );

        mailSender.send(message);
    }

    private void ensureRecipientIsAllowlisted(
            String email
    ) {
        // Minimal example: in a real system,
        // inject a verified test-recipient registry.
        if (!email.endsWith("@mail-test.example.org")) {
            throw new IllegalArgumentException(
                    "Recipient is outside test allowlist"
            );
        }
    }
}
```

This is a **teaching example**, not a complete production service. A simple `endsWith` check is **insufficient** if input has not been parsed/canonicalized into a valid mailbox address; in production, use an exact identity- and environment-scoped registry/allowlist rather than accepting arbitrary addresses. Host, URL, sender domain, and resource paths are illustrative values.

### What to test on this message

- `Content-Type` has the right multipart structure.
- `text/plain` and `text/html` hold equivalent core facts.
- Non-ASCII / Unicode subjects display cleanly.
- Clients load `cid:brand-logo` in supported cases.
- When images are blocked, text and CTA remain readable.
- HTML does not break on mobile screens.
- Layout remains sensible on Reply/Forward.

## 21. Why must inline resources be added after setText?

In `MimeMessageHelper`, how MIME parts get composed can depend on call order. When sending inline images, Spring Mail recommends **setting text first before adding inline resources**:

```java
helper.setText(plain, html);
helper.addInline("brand-logo", imageResource);
```

This habit avoids unwanted client discrepancies when MIME multipart structures end up poorly ordered.

Additionally:

- The `Content-ID` on the inline MIME part must match the `cid:...` reference.
- Do not inject extra angle brackets or malformed characters into CIDs arbitrarily.
- The resource should have a defined content type.
- Data must exist at send time; do not delete temp files before MIME serialization.
- Some clients may still display inline parts as attachments when MIME recognition differs.

Check both **MIME part metadata** and **actual image rendering in clients**, not merely the `addInline(...)` call.

## 22. Inline images vs remote images

Two approaches in HTML:

```html
<!-- Inline Content-ID -->
<img src="cid:brand-logo"
     alt="Brand logo">

<!-- HTTPS remote image -->
<img src="https://assets.example.org/mail/logo.png"
     alt="Brand logo">
```

| Characteristic | CID inline | HTTPS remote |
| --- | --- | --- |
| Image source | MIME part inside the same email | External server/CDN |
| MIME size | Grows with image size + encoding | Smaller, yet requires network fetch |
| Image blocking | May still be handled differently by clients | May be blocked/proxied |
| Ability to swap image post-send | MIME content is fixed | URL can serve updated assets |
| Caching/proxying | Client-dependent | Client/provider-dependent |
| Privacy risk | Payload delivered to recipient/provider | Image server receives request/metadata |

Never claim CID **always displays** or remote images **always load**. Individual clients enforce their own rules. Test both **images enabled** and **images blocked**.

## 23. Alt text is fallback content, not decoration

An email consisting solely of an image containing the words “Order has been delivered” conveys nothing if images are blocked.

Poor example:

```html
<img src="cid:important-news"
     alt="image">
```

Better example:

```html
<h1>Order has been delivered</h1>
<p>You can view the receipt in your account.</p>
<img src="cid:delivery-illustration"
     alt="Delivered package illustration">
```

**Important information should exist as real text**, not solely inside a bitmap. Alt text describes images appropriately, rather than replacing all business content.

When testing with images off:

- Is content still understandable?
- Does the CTA have text labels?
- Does the layout leave awkward blank gaps?
- Does alt text appear where the client supports it?
- Does a missing logo cause users to lose brand recognition?

## 24. Attachments must be tested as part of the user experience

A message with a PDF:

```java
helper.addAttachment(
        "hoa-don-T-454.pdf",
        new FileSystemResource(invoicePath.toFile())
);
```

Do not only assert `attachment != null`. Check in mailboxes/clients:

- Does the attachment show up properly as an attachment?
- Do Vietnamese/non-ASCII or spaced filenames display properly?
- Can the client preview the PDF?
- Does the file open without corrupted bytes?
- Does downloading on mobile behave cleanly?
- When opening/forwarding the email, does the attachment remain intact?
- Is an inline logo mistakenly shown as an extra attachment?
- Do oversized files get blocked or trigger warnings from providers/clients?

**Filename display and openability** are part of email quality, not just MIME-level correctness.

## 25. International filenames and charsets

A filename like `"Hóa đơn tháng 11.pdf"` can pass through different MIME parameter encodings across libraries and clients.

When testing:

- Read the decoded filename using a Jakarta Mail parser.
- Open in at least two representative clients.
- Test copying/downloading accented names on Windows/macOS/mobile.
- Verify the file extension and MIME type match.
- Never place sensitive data inside filenames.

For legacy or specialized mail clients, a safe ASCII fallback filename may be needed. However, you do not need to force every filename to ASCII if your target client base renders Unicode cleanly.

## 26. A broken multipart/alternative causes unpredictable symptoms

Example of a broken MIME tree:

```text
multipart/mixed
  +-- text/plain
  +-- text/html
  +-- image/png
```

Clients will not reliably choose HTML when plain and HTML sit as siblings inside mixed instead of grouped as alternatives. Some clients display both or pick the wrong representation.

Solution:

- Use `MimeMessageHelper` with the right constructor and multipart mode.
- For complex MIME, use Jakarta Mail APIs intentionally.
- Parse the MIME tree in integration tests.
- Send sample raw messages to test mailboxes.
- Never rely on client rendering as your sole detector for malformed MIME trees.

## 27. Content-Type must reflect real content

Cases to distinguish:

```text
text/plain; charset=UTF-8
text/html; charset=UTF-8
image/png
application/pdf
multipart/alternative
multipart/related
multipart/mixed
```

If an HTML `String` is sent using `SimpleMailMessage`, mail clients may render literal HTML tags because the message is plain text. CSS cannot fix that; you must send a `MimeMessage` with a proper `text/html` part.

For binary files, setting the wrong `Content-Type` or `Content-Disposition` can cause clients to mis-preview, mis-download, or mishandle the attachment.

## 28. Content-Transfer-Encoding is not security encryption

Emails may use:

```text
Content-Transfer-Encoding: quoted-printable
Content-Transfer-Encoding: base64
Content-Transfer-Encoding: 7bit
```

These encodings exist for **MIME/SMTP transport**, providing zero confidentiality. A text/html email encoded with quoted-printable or base64 is still decoded and displayed by clients.

When testing:

- Parse/read **decoded content**, rather than comparing raw SMTP bytes against UTF-8 source strings.
- Never confuse base64 attachments with encryption.
- Verify clients do not render artifacts like `=C3=...` or mojibake caused by mismatched charsets/encodings.

## 29. UTF-8 with Vietnamese text must be checked in multiple places

An email might contain:

- Subject: “Xác nhận thanh toán thành công”.
- Body: “Số tiền: 1.250.000 ₫”.
- Recipient display name: “Nguyễn Minh”.
- Attachment filename: “Hóa đơn tháng 11.pdf”.
- Link paths/queries containing Unicode characters if the app builds unencoded URLs.

**Setting `"UTF-8"` in `MimeMessageHelper` is essential**, yet you must also verify:

1. Source data and template files are saved in the right encoding.
2. Servlets/JSON/databases did not corrupt strings before rendering.
3. MIME Subjects and headers encode/decode properly.
4. Text/plain and text/html specify matching charsets.
5. Filenames render cleanly on target clients.
6. URLs are percent-encoded per standards.

Do not test solely with ASCII `"Hello world"` and assume Vietnamese emails are safe.

## 30. Dates, times, and currency amounts must be tested in mail clients

An email containing:

```text
Appointment: 09:00 on 12/11/2026
Payment: 1,250,000 VND
```

If the application renders in the wrong timezone or a price column wraps poorly, readers can misinterpret values. Always:

- State the explicit timezone when times involve recipients.
- Use consistent number/locale formatting across plain text and HTML.
- Check wrapping on long numbers.
- Avoid applying `white-space: nowrap` everywhere if it causes mobile overflow.
- Verify decimal/thousands separators and currency symbols are not swapped.

**Wrong business data from formatting** is a much severer bug than a missing drop shadow.

## 31. CSS in email: choose stability over visual effects

HTML email has different constraints than the web. Some clients handle `<style>` and media queries well; others strip, rewrite, or partially support them. Therefore:

- Never depend on JavaScript.
- Never design emails that only work when `display:grid`/`flex` is supported.
- Prefer simple layouts with fallbacks.
- Use inline CSS for critical properties where appropriate for target clients.
- Test tables, borders, padding, fonts, and backgrounds across common apps.
- Use email-specific CSS inlining/build tools if your pipeline supports them.

A simple example:

```html
<td
  style="
    font-family:Arial,Helvetica,sans-serif;
    font-size:16px;
    line-height:24px;
    color:#1f2937;
    padding:24px;
  ">
  Content that must stay readable across many mail clients.
</td>
```

There is no single CSS support list shared identically across all clients and versions. Use verified CSS compatibility references for your target clients and **test directly** before finalizing templates.

## 32. Inline CSS does not mean every property works

Example:

```html
<div style="
  display:flex;
  position:sticky;
  gap:24px;
  backdrop-filter:blur(8px);
">
  ...
</div>
```

The styles are inlined, yet these modern properties can still be unsupported by mail clients. CSS inlining only moves declarations onto elements; it does not change the rendering engine.

To improve compatibility:

1. Identify critical layout elements.
2. Pick an HTML structure readable even when CSS is stripped.
3. Inline styles for critical typography, spacing, and colors.
4. Provide fallbacks for newer features.
5. Test on SLA-critical clients.

## 33. Table-based layouts in email

A common pattern for compatible HTML email:

```html
<table role="presentation"
       width="100%"
       cellpadding="0"
       cellspacing="0"
       border="0"
       style="border-collapse:collapse;">
  <tr>
    <td align="center">
      <table role="presentation"
             width="600"
             cellpadding="0"
             cellspacing="0"
             border="0"
             style="width:100%;max-width:600px;">
        <tr>
          <td style="padding:24px;">
            <h1 style="font-size:24px;line-height:30px;">
              Order confirmation
            </h1>
            <p style="font-size:16px;line-height:24px;">
              Order T-454 confirmed.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
```

`role="presentation"` tells assistive technologies not to treat layout tables as data tables when the client supports those semantics. Some clients apply `max-width` differently, so testing on mobile and Outlook remains essential.

### Do not use presentation tables for everything

**True data tables** (invoice line items, transactions) need headings, reading order, and sensible scrolling/stacking. `role="presentation"` belongs strictly on **layout** tables, never to strip semantics from accessible data tables.

## 34. Responsive email differs from responsive websites

On the web, you can lean heavily on media queries. In email, media-query support varies.

Strategies:

- Single column for core content.
- Containers with relative width and `max-width`.
- Fluid images inside table cells.
- Buttons with ample tap targets.
- Avoid cramped multi-column data grids on mobile.
- Keep reading order logical even without responsive CSS.
- Never place CTAs solely in a sidebar/column that might collapse or hide.

Example:

```html
<img
  src="cid:product-photo"
  alt="Product photo"
  width="280"
  style="
    display:block;
    width:100%;
    max-width:280px;
    height:auto;
    border:0;
  ">
```

This is a fallback pattern, not a guarantee every client obeys identically. Testing across representative widths exposes overflows, stretched images, and squished table cells.

## 35. 600 px width is not a hard law

Many email templates use containers around 600 px, yet no single width fits every device and client.

A rigid wide template:

```html
<table width="900">
  ...
</table>
```

can force horizontal scrolling on phones. An overly narrow template makes numeric tables cramped on desktop.

Design approach:

1. Pick container width for the content type.
2. Use responsive/stacking behavior where target clients support it.
3. Decide how data tables present on mobile.
4. Test very narrow screens, zoom, and text scaling.
5. Do not rely solely on a viewport meta tag to fix layout.

## 36. Long text and long URLs can break layouts

Production data can exceed mockups:

```text
Long customer name
Order ID with many characters
URL with long query string
Long email recipient display name
Multi-line street address
```

Because CSS/word-wrapping differs across clients:

- Long links can push tables off-screen.
- Codes without spaces stretch columns too wide.
- Accented Unicode names can wrap unexpectedly.
- Special Unicode characters can introduce directionality glitches.

Test with **boundary fixtures**, not just clean short strings. If URLs carry tokens, never log or screenshot them in shared environments; use synthetic links pointing to staging domains.

## 37. CSS buttons and fallback links

A CTA styled as a button:

```html
<table role="presentation" border="0"
       cellpadding="0" cellspacing="0">
  <tr>
    <td bgcolor="#2058c9"
        style="border-radius:6px;
               background-color:#2058c9;">
      <a href="https://portal.example.org/orders"
         style="display:inline-block;
                padding:14px 24px;
                font-size:16px;
                font-family:Arial,sans-serif;
                color:#ffffff;
                text-decoration:none;">
        View order
      </a>
    </td>
  </tr>
</table>
```

Some clients do not render button backgrounds, border radius, or padding like browsers. Check:

- Is the text label still readable if the background disappears?
- Is the link still clickable/tappable?
- Does the button split across multiple lines?
- Does text color keep contrast in dark mode?
- Does the URL point to the right staging/production domain?
- Is keyboard/screen-reader interaction comfortable?

For critical emails, you can include a **clear text URL** below the button, while avoiding printing sensitive bearer tokens in screenshots or forwarded emails.

## 38. Do not build CTAs solely from background images

Poor example:

```html
<a href="https://portal.example.org/confirm">
  <img src="cid:confirm-button"
       alt="">
</a>
```

If images are blocked, the user has no idea where the link goes. Better example:

```html
<a href="https://portal.example.org/confirm">
  Confirm request
</a>
```

or use an HTML text button as shown earlier. Primary functionality must work independently of decorative graphics.

## 39. Dark mode changes more than one background color

A mail client may:

- Preserve inline CSS colors unchanged.
- Automatically invert backgrounds and text.
- Invert only partial elements.
- Apply user theme overrides.
- Ignore browser-style color-scheme CSS media queries.

Result:

```text
Light mode: black text on white background -> clear
Dark mode:  background turns black,
            yet part of text stays black -> unreadable
```

With dark logos, dark mode can make the logo vanish into the background. Test:

1. Desktop light mode.
2. Desktop dark mode where supported.
3. Common mobile clients in dark mode.
4. Images blocked combined with dark mode.
5. Logos, CTAs, pricing tables, warnings, and footers.

Never check one dark-mode screenshot from a single client and assume every client applies the same color-inversion rules.

## 40. Color contrast and accessibility

A good email should ensure:

- Core content meets your organization’s accessibility contrast targets.
- Never rely solely on red/green color to convey status.
- Important icons include text labels.
- Links use descriptive anchor text.
- Base font size is legible with comfortable line-height.
- Content follows a logical reading order.
- No distracting flashing/animations or reliance on animation for comprehension.

Example:

```html
<!-- Avoid having only a red icon -->
<p>🔴</p>

<!-- Prefer having a text label -->
<p><strong>Payment failed.</strong>
   Please update your payment method.</p>
```

In dark mode, a color compliant on light backgrounds can become illegible when the client changes the background. Check **post-render contrast**, not just hex values in HTML source.

## 41. Font fallbacks and line height

Not every mail client downloads web fonts or honors custom fonts like browsers. Choose a resilient font stack:

```html
<p style="
  font-family:Arial,Helvetica,sans-serif;
  font-size:16px;
  line-height:24px;
">
  Vietnamese diacritics text: Hóa đơn đã thanh toán.
</p>
```

When a font is unavailable:

- Lines can grow longer or shorter.
- CTAs may wrap onto multiple lines.
- Tables may widen.
- Vietnamese diacritics must still render intact.
- User-enlarged text sizes can make containers taller.

Avoid setting fixed heights on blocks holding variable text. Test with fallback fonts and large text sizes.

## 42. Preheaders and preview text

Many mail clients show a preview snippet next to the subject. This snippet can be pulled from early message content or an intentionally crafted HTML preheader element.

Example:

```html
<div style="
  display:none;
  font-size:1px;
  line-height:1px;
  color:transparent;
  max-height:0;
  max-width:0;
  opacity:0;
  overflow:hidden;
">
  Order T-454 has been confirmed.
</div>
```

**This is only a common technique, not implemented identically across all clients.** If a preheader renders visibly at the top of the body or gets ignored, the user experience shifts.

When testing:

- Does preview text show the intended copy?
- Does it leak tokens/OTPs/PII on lock-screen notifications?
- Is preview text accidentally pulled from CSS, alt text, or footers?
- Is text cut mid-word in an awkward or sensitive way?
- Do subject/preheader differ between web and mobile?

Preheaders are part of UX and privacy, not merely a marketing detail.

## 43. Subject and From are critical UI

An email with sleek layout yet a vague subject:

```text
Subject: Notification
```

makes it hard for recipients to judge urgency. A specific subject:

```text
Subject: [TEST] Order T-454 confirmed
```

helps distinguish test vs production mail.

When testing in mail clients:

- Are the From display name and address sensible?
- Does the Subject preserve Unicode cleanly?
- Does mobile truncate the Subject before key details appear?
- Does Reply-To route to the right support mailbox?
- Could `[TEST]` accidentally appear in production mail?
- Does the From header align with the route’s domain authentication?

Rendering tests are not just about the HTML body; the **mailbox list UI** matters too.

## 44. Overly long emails can get clipped

Some mail clients collapse or clip long email bodies depending on product/version thresholds. If key elements like:

- CTAs,
- Verification codes,
- Payment details,
- Support links,
- Required unsubscribe links,

sit buried at the bottom of a huge email, users may miss them right away.

Mitigations:

- Place critical information near the top.
- Trim redundant markup.
- Avoid repeating identical CSS/HTML blocks unnecessarily.
- Never embed base64 attachments directly in the HTML body.
- Test realistic long emails in target clients.
- Keep footers and support info easy to reach.

Never rely on one memorized clipping byte threshold across all Gmail/client versions; test with realistic product payloads.

## 45. HTML emails must not depend on JavaScript

A web page might use:

```html
<button onclick="confirmOrder()">
  Confirm
</button>
```

However, mail clients routinely block or strip scripts and event handlers for security. CTAs should be HTTPS links into the application:

```html
<a href="https://portal.example.org/orders/confirm">
  Confirm in app
</a>
```

The destination must enforce authentication, authorization, CSRF protection, or one-time tokens by design; never turn clicking an email link into an unprotected sensitive action.

### Do not rely on HTML email forms as mandatory controls

Input/form support inside emails varies widely. Many clients disable or distort them. Whenever users must enter codes, update cards, or approve transactions, send them to a protected HTTPS page—it is far easier to test and much safer.

## 46. Link tracking and redirects can affect UX

Providers or security gateways may rewrite links:

```text
https://portal.example.org/orders/123
        |
        v
https://tracking-or-security-gateway/...
        |
        v
Destination URL
```

This can affect:

- Link redirects inside mobile apps.
- Deep links and universal links.
- Load latency.
- URL encoding.
- One-time tokens/expiry.
- Security scanner prefetching.
- Authentication/cookie state.

When testing, **click the link inside a real mail client** and verify the final destination, rather than just reading `href` in raw HTML. Never put real user data or production tokens in screenshots/test links.

## 47. Click scanners can trigger links before the user

Some security systems scan URLs in incoming mail. If an HTTP GET link immediately performs a destructive or state-changing action (canceling orders, verifying tokens, resetting passwords), scanners can cause unintended side effects.

Safer design:

1. GET links open a confirmation page rather than auto-completing sensitive actions.
2. State changes execute only after explicit user action with proper protection.
3. One-time tokens follow strict lifecycle validation and stay out of logs.
4. Replay/CSRF protections match action sensitivity.
5. Test with scanning gateways/mailboxes if enterprise customers use them.

This is a **post-open interaction** hazard that static HTML snapshots cannot catch.

## 48. Disabled remote images: a mandatory test case

Clients may block external images by default or by corporate policy. Test both states:

```text
Image loading:
  [ ] Enabled
  [ ] Disabled / Ask before loading
```

With images off, check:

- Primary content still appears.
- CTAs have text independent of images.
- Logos/illustrations have helpful alt text.
- No giant confusing whitespace gaps remain.
- Prices, due dates, and OTPs are never trapped inside images.
- Missing background images do not destroy text contrast.

### Why not test only online images?

Inline CID images can behave differently from external images. Clients may also proxy, cache, or rewrite URIs. Always test **the exact image delivery mechanism your template uses**.

## 49. Blocked images are not a Spring Mail bug

If the MIME part has a valid `Content-ID` and raw HTML references it properly, yet user settings block images, that is client security behavior. Fixing it does not necessarily mean changing backend SMTP code; make the email **readable without images**.

Conversely, if the CID part is missing or MIME nesting is broken, that is a composition bug. Proper classification avoids changing the wrong code.

## 50. HTML sanitization and unsuitable tags

Mail clients may strip:

- `<script>` and script/event handlers.
- Form components.
- Embedded media.
- External CSS or certain style rules.
- Iframes.
- Some SVGs and dynamic content.
- Resources blocked by security policy.

Never use those elements to carry essential information.

An email should have a clean semantic core:

```html
<h1>Payment complete</h1>
<p>Amount: 1,250,000 VND</p>
<p>Reference: T-454</p>
<p>
  <a href="https://portal.example.org/receipts">
    View receipt in your account
  </a>
</p>
```

Visual polish enhances the experience, while the core message must survive aggressive HTML sanitization.

## 51. Web CSS resets can cause side effects in email

Web CSS frameworks commonly assume:

- Global `box-sizing`.
- Flex/grid support.
- Pseudo-selectors.
- Custom properties.
- Modern layout primitives.
- Unscoped styles on `html`, `body`, or selectors restricted by clients.

Copying SPA CSS straight into email:

```text
Browser preview: looks great
Mail client: many styles stripped or defaults differ
```

Build a dedicated **email design system** or use an email-template toolchain producing compatible output—and still test in real clients. Do not embed a huge web CSS bundle assuming minification solves compatibility.

## 52. Dark mode needs fault-tolerant design

To avoid disappearing logos:

- Give logos an appropriate backing/border when needed.
- Check light/dark variants without relying entirely on media queries.
- Avoid dark transparent images over surfaces that may turn black.
- Include text brand labels if brand identity is mandatory.
- Keep CTA labels high-contrast even when clients invert colors.

Example:

```html
<img
  src="cid:brand-logo"
  width="120"
  height="40"
  alt="Support team"
  style="
    display:block;
    background-color:#ffffff;
    padding:8px;
  ">
```

Even `background-color:#ffffff` can be altered by some clients. Treat this as a mitigation and verify the rendered result visually.

## 53. Image-heavy emails can hurt accessibility

A design consisting of one tall graphic:

```html
<img src="https://assets.example.org/promo-all-in-one.png">
```

creates multiple issues:

- Appears nearly blank when images are blocked.
- Screen readers lack semantic content.
- Text baked into images does not scale with user settings.
- Large images load slowly.
- Single images cannot cleanly express multiple distinct links/actions.
- Recipients cannot copy text content.

Use HTML text for information and images for illustration. When infographics are unavoidable, summarize the key points in text and link to an accessible web page.

## 54. Test with screen readers and keyboard navigation

Modern rendering QA goes beyond screenshots:

1. Open the email in a client with supported screen readers or accessibility tools.
2. Verify reading order.
3. Check that headings make logical sense.
4. Check links have descriptive text (not just “Click here”).
5. Ensure decorative images do not create excessive noise.
6. Confirm data tables remain understandable.
7. Verify key actions do not rely solely on color or spatial position.
8. Navigate links via keyboard where supported.

**Never rely on a single automated accessibility score** to declare an email accessible. Real results depend on the mail client and assistive technology.

## 55. Plain text is a content fallback, not an HTML clone

In HTML:

```html
<a href="https://portal.example.org/orders">
  View order
</a>
```

In plain text:

```text
View order:
https://portal.example.org/orders
```

Full URLs must be present so text-only users can still act. If the link holds a magic-link token, safeguard it during testing, forwarding, and logging.

When HTML has a table:

```text
Item: Book
Qty: 2
Unit price: 120,000 VND
Total: 240,000 VND
```

A key-value plain-text representation is often far easier to read than trying to draw wide ASCII tables.

## 56. Reply and Forward can transform content

Users do not only read once; they may Reply or Forward:

- Clients may reformat HTML.
- CID images can be dropped or re-referenced.
- CSS styles get stripped.
- Attachments may split or change presentation.
- Repeated quote history lengthens the email.
- Link tracking preserves rewritten URLs.
- Forward recipients may use completely different clients.

If an email is meant to be forwarded in business workflows (tickets, booking confirmations, reports), test **forwarding across at least one representative client pair**.

### Never rely on forwarding to share credentials

OTPs, reset tokens, identity data, or sensitive attachments must not be designed assuming anyone who forwards them is authorized to use them. Enforce business authorization on the destination page.

## 57. Test replying (Reply-To)

Example:

```java
helper.setReplyTo("support@example.org");
```

Check in clients:

- Does hitting Reply address the right support mailbox?
- Could replies accidentally go to `no-reply`?
- How do users see the From display name and Reply-To?
- Are unwanted internal addresses exposed?
- For threaded emails, does it group into the right conversation?

Do not merely assert the header exists—actually test hitting Reply in a test mailbox.

## 58. Threading and conversation views

Some clients group multiple emails into conversations/threads using Subject, Message-ID, or headers like In-Reply-To/References depending on their logic.

Sometimes distinct emails share identical Subjects:

```text
Subject: Notification
Subject: Notification
Subject: Notification
```

Clients may collapse them together, making messages hard to find. Conversely, reusing the same `Message-ID` across distinct emails can cause erratic behavior.

When testing multi-email flows:

- Do subjects carry enough distinguishing details?
- Does threading match real intent?
- Are Message IDs generated per contract?
- Do replies land in the intended conversation if required?

Never hardcode `Message-ID` as a trick to “avoid duplicate sends”; it does not guarantee SMTP deduplication and makes client behavior unpredictable.

## 59. Mail clients also alter URL detection

Some clients automatically link phone numbers, addresses, dates, or URLs:

```text
Phone: 0900 000 000
Appointment: 12/11/2026
Order ID: 123456
```

On mobile, phone numbers and dates can turn into interactive links, altering color/underlining or causing accidental taps.

Test when:

- Order IDs look like phone numbers.
- Addresses contain punctuation and line breaks.
- Dates use ambiguous locale formats.
- Long account strings need exact copying.

If auto-linking causes confusion, adjust content formatting compatibly rather than injecting arbitrary invisible characters that break copy/paste.

## 60. Bidirectional text and address formatting

Emails may combine recipient names, addresses, or right-to-left (RTL) text alongside numbers and URLs. Test:

- Ordering of numbers and currency symbols.
- Character ordering inside URLs.
- Sentence and table directionality.
- Copy/paste of verification codes.
- Screen reader pronunciation.

Do not test only English with short names. For multilingual products, build locale-matched fixtures and test them in representative clients.

## 61. Blocked images and dark mode must be tested together

Independent checks:

```text
Dark mode OFF, images ON  -> PASS
Dark mode ON,  images ON  -> PASS
Dark mode OFF, images OFF -> PASS
```

still miss the combined case:

```text
Dark mode ON, images OFF  -> logo absent,
                            white text invisible?
```

You do not need every combination on every device, yet for sensitive/critical templates include representative **pairwise test cases** instead of varying only one dimension at a time.

## 62. Large font sizes combined with narrow viewports

A user enabling large system font sizes can cause:

- Buttons growing taller.
- Two-column tables becoming cramped.
- Different line breaks.
- Footers pushed far down.
- Fixed-height containers clipping text.

When testing mobile:

1. Open at normal viewport width.
2. Increase text size where the client supports it.
3. Rotate portrait/landscape.
4. Inspect CTAs and core content.
5. Verify no zoom or horizontal scroll is needed to read the main message.

## 63. Pricing tables and multi-column data need special care

A data table:

```text
Item | Qty | Unit price | Tax | Discount | Total
```

may fit desktop yet overflow on mobile.

Solutions ranked by priority:

- Show summary and total upfront.
- Present each item as a stacked card/block on narrow screens.
- Offer a PDF or portal link for detailed tables when permitted.
- Never sacrifice essential data or accuracy.
- Use semantic table markup for genuine tabular data.

If using HTML tables alone, test on at least one mobile client to catch horizontal overflow and clipped columns.

## 64. Mail client test matrix: start from your audience

Never pick a test matrix purely by developer preference. Ask:

- How many recipients use Gmail/Outlook/Apple Mail vs corporate systems?
- What is the mobile vs desktop share?
- Are groups using classic Outlook or older devices?
- Do strict environments restrict attachments/links?
- Which email types carry the highest impact if broken?
- Which OS/app versions are officially supported?

An **illustrative** sample matrix, not a rigid standard:

| Client | Environment | Modes | Priority |
| --- | --- | --- | --- |
| Gmail web | Desktop browser | Light, images on/off | High |
| Gmail mobile | Android or iOS | Light/dark, narrow screen | High |
| Outlook desktop (in use) | Windows | Reading pane, images blocked | High for enterprise users |
| Outlook web | Desktop browser | Light/dark | Medium/high |
| Apple Mail | iPhone | Light/dark, larger text | High with heavy iOS share |
| Apple Mail | macOS | Light/dark | Medium |
| Enterprise mail client | Desktop/mobile | Security gateway, attachment restrictions | Per enterprise needs |
| Text-only mail reader | Test mode | text/plain | High for transactional mail |

**Adapt** this matrix using actual product usage data and client support policies.

## 65. Each test dimension has multiple conditions

A test case can be identified by:

```text
Template: payment-receipt v7
Fixture: multiple-items-vnd
Client: Outlook desktop
OS: Windows
App version: recorded
Theme: dark
Images: disabled
Viewport: narrow reading pane
Locale: vi-VN
```

Multiplying every variable explodes test count. Use **risk-based selection**, pairwise coverage, and template criticality to pick sensibly.

## 66. Test by risk tier rather than every combination

A tiered approach:

**Smoke tests** for every template change:

- Plain text and HTML MIME.
- Popular web client.
- One mobile client.
- CTA, core content, and links.

**Regression tests** before release:

- Supported client groups.
- Light/dark modes.
- Images on/off.
- Attachments.
- Long-text/locale fixtures.

**Extended tests** on major changes:

- New mail client or OS versions.
- New template layouts.
- Multi-column or dynamic content.
- SMTP provider or security gateway changes.
- Specialized accessibility setups.

Never claim “tested 100% of clients”; report **exactly which conditions were tested and what limitations remain**.

## 67. Using seed test accounts

A seed mailbox is a controlled mailbox provisioned to receive template and client test mail. It differs from mailing real customers.

Process:

1. Provision test mailboxes across authorized representative services/tenants.
2. Document login/management securely without exposing credentials in public docs.
3. Register recipients on an allowlist.
4. Connect to approved test/staging SMTP providers.
5. Use synthetic fixtures and staging links.
6. Attach run ID/template version metadata appropriately.
7. Send one copy per selected mailbox.
8. Open messages in real apps according to the test matrix.
9. Capture evidence/screenshots and test status.
10. Clean up mailboxes/evidence per retention policy.

Respect service terms and organizational approvals for test accounts. Avoid using employees’ personal accounts when project-managed accounts are available.

## 68. Inbox placement testing differs from rendering testing

Seed accounts may receive mail in:

```text
Inbox
Spam/Junk
Promotions/Other
Quarantine
Not found in account
```

Landing in Spam points toward deliverability/reputation or content filtering. Once you open the message, you can still inspect HTML rendering, while recording:

- Which folder the message arrived in.
- Whether the client blocked images/links/attachments due to folder/risk policies.
- Whether moving it from Spam to Inbox alters rendering behavior.
- Whether warning banners change the user experience.

Never treat “missed Inbox” as proof CSS is wrong. Likewise, never extrapolate one seed account’s placement to all recipients.

## 69. Distinguish provider submission tests from client rendering tests

A pipeline should separate:

```text
Test template model
      |
      v
Generate MIME in test context
      |
      v
Parse/check MIME structure
      |
      v
Submit via approved test route
      |
      v
Seed mailboxes
      |
      v
Open with supported clients
      |
      v
Record screenshots + interactions
```

If submission fails with an SMTP authentication error, you cannot conclude anything about client rendering yet. If MIME parsing fails, fix the composer before testing dark mode.

## 70. Naming test runs and template versions

To reproduce a visual bug reliably, you must know **the exact version that rendered the email**.

Example:

```text
testRunId = mail-render-454-20261112
templateKey = order-confirmation
templateVersion = 7
fixtureId = long-vietnamese-name
buildCommit = abc1234
senderRoute = staging-smtp
```

Avoid putting commit hashes, run IDs, or fixture keys into public SMTP headers unnecessarily. Keep them in the test harness/evidence store and use a `[TEST]` subject with a short opaque ID to locate mail without leaking secrets.

## 71. Collecting structured evidence

A test record:

```yaml
runId: mail-render-454-demo
template: order-confirmation
templateVersion: 7
fixture: multiple-items-vnd
clientFamily: Outlook
clientVersion: recorded-in-test
osVersion: recorded-in-test
theme: dark
images: blocked
viewport: narrow-reading-pane
result: FAIL
symptom: CTA label has insufficient contrast
rawMimeRef: restricted-artifact-reference
screenshotRef: restricted-artifact-reference
```

This is an **example schema**, not a STEP 4 metadata file. Artifact pointers must reference systems with proper access controls and retention, especially if screenshots show email addresses or tokens.

## 72. Screenshot tests: benefits and limits

Screenshots help compare layout, spacing, colors, and visibility. However:

- Font rendering varies by OS and scaling.
- Anti-aliasing and subpixel rendering cause false pixel diffs.
- Dynamic content changes line counts.
- Client chrome, warning banners, and promo bars shift.
- A screenshot never verifies link click-through.
- Images cannot evaluate screen readers.
- A screenshot with images enabled does not cover images disabled.

Use screenshot regression as a **supporting signal**, not the sole gatekeeper. For critical bugs, check real interactions and content.

## 73. What test automation helps?

Automation can:

1. Render plain and HTML from the same fixture.
2. Build `MimeMessage` and parse headers/parts.
3. Send to an SMTP capture server.
4. Dispatch automatically to allowlisted seed mailboxes.
5. Collect test IDs and provider statuses.
6. Capture/compare screenshots using authorized tooling when available.
7. Verify URLs target expected origins.
8. Generate reports grouped by template/version/client.

Things you **must not assume automation already covers sufficiently**:

- Layout variations in clients outside the test matrix.
- Real-world screen reader experience.
- Whether emails reach every user’s Inbox.
- Whether users interpret link wording properly.
- External security gateway interventions.
- Readability under enlarged system text.

## 74. Using an SMTP capture server for structural tests

An SMTP test server such as GreenMail or a capture server lets you receive messages **without mailing real inboxes**. Use it to verify:

- Subject and From/To.
- `multipart/alternative`.
- HTML/plain text content.
- CID and attachment MIME parts.
- Encoding.
- File bytes.

However, a capture server’s built-in mail viewer **does not share the same rendering engine** as Gmail, Outlook, or Apple Mail. A good preview there does not prove compatibility in real clients.

## 75. Integration test example with GreenMail

This example **sends strictly to a local test SMTP server**, never onto the Internet:

```java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.junit.jupiter.api.Assertions.*;

class MailComposerSmtpTest {

    @Test
    void receivesHtmlAndPlainTextMessage() throws Exception {
        GreenMail server = new GreenMail(
                new ServerSetup(0, "127.0.0.1", "smtp")
        );
        server.start();

        try {
            JavaMailSenderImpl sender = new JavaMailSenderImpl();
            sender.setHost("127.0.0.1");
            sender.setPort(server.getSmtp().getPort());

            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(
                    message, true, "UTF-8"
            );
            helper.setTo("recipient@example.net");
            helper.setFrom("mail-test@example.org");
            helper.setSubject("Order T-454 confirmation");
            helper.setText(
                    "Order T-454 confirmed.",
                    "<p>Order <b>T-454</b> confirmed.</p>"
            );

            sender.send(message);

            assertTrue(server.waitForIncomingEmail(5000, 1));

            MimeMessage received = server.getReceivedMessages()[0];
            assertEquals(
                    "Order T-454 confirmation",
                    received.getSubject()
            );
            assertTrue(received.isMimeType("multipart/*"));
        } finally {
            server.stop();
        }
    }
}
```

The test requires a GreenMail dependency compatible with your project’s Jakarta Mail version. Asserting `multipart/*` is a coarse check; production tests should **walk the MIME tree** to verify text/plain, text/html, and exact content. Never run real SMTP in CI where disallowed.

## 76. Why not match raw MIME text with plain string checks?

A raw email may encode Vietnamese text with quoted-printable or base64. If a test searches verbatim for:

```text
"Đơn hàng đã xác nhận"
```

in raw bytes, it may not appear even though mail clients decode it cleanly.

Use a Jakarta Mail parser to read **decoded content**, content types, filenames, and Content-IDs, then assert business fields. Raw MIME remains useful for inspecting RFC header/part boundaries, yet should not be your sole way to read messages.

## 77. Walk the MIME tree to inspect parts

Simple test helper example:

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;

static void visitMimeParts(Part part) throws Exception {
    if (part.isMimeType("multipart/*")) {
        Multipart multi = (Multipart) part.getContent();
        for (int i = 0; i < multi.getCount(); i++) {
            visitMimeParts(multi.getBodyPart(i));
        }
        return;
    }

    if (part.isMimeType("text/plain")) {
        String text = (String) part.getContent();
        assertTrue(text.contains("T-454"));
    }

    if (part.isMimeType("text/html")) {
        String html = (String) part.getContent();
        assertTrue(html.contains("T-454"));
    }
}
```

This snippet illustrates recursion. In real tests, collect parts into lists and assert **the exact expected count per type**, content, and structure; if no text part exists, an `assertTrue` inside an `if` branch never runs and can falsely pass. For unusual MIME trees, distinguish nested `message/rfc822` or `text/plain` attachments by disposition and context.

## 78. Verify attachments by bytes, not just filename

For a PDF:

1. Find the body part with `Content-Disposition: attachment`.
2. Decode the filename via the API.
3. Read decoded bytes as a stream.
4. Compare against expected SHA-256 or fixture bytes.
5. Verify content type and reasonable size.
6. Try opening the downloaded file in a real client.

Never store or log PDFs containing real customer data in test outputs. Use synthetic fixtures and cap sizes so tests do not fill disks or heaps.

## 79. Use test mailboxes with multiple message versions

A series of runs in the same mailbox:

```text
[TEST] order-confirmation v7 runA
[TEST] order-confirmation v8 runB
[TEST] order-confirmation v8 dark-mode-case
```

lets testers compare versions side by side. However, conversation grouping can collapse similar subjects and make messages harder to spot; use distinct run IDs or dedicated evidence storage rather than abusing Message-ID spoofing.

## 80. Verify URLs through real interaction

A password-reset email test:

1. Send to a test mailbox.
2. Open in target clients.
3. Click the link from the real UI.
4. Verify navigation to a valid staging domain.
5. Check redirects, consent, and token expiry.
6. Confirm GET scanners cannot auto-complete sensitive actions.
7. Verify expired links display helpful UI errors.
8. Never capture tokens in screenshots or shared logs.

Asserting only `href` in raw HTML leaves client and security-gateway link handling untested.

## 81. Classify errors by stage to avoid fixing the wrong thing

A bug report saying “email looks wrong” can span multiple layers:

| Symptom | First stage to inspect | Evidence |
| --- | --- | --- |
| Email missing from test mailbox | SMTP/delivery/spam placement | Provider logs, bounces, mailbox folders |
| HTML tags appear as literal text | MIME `Content-Type`/composer | Raw headers and decoded parts |
| Only plain text appears | `multipart/alternative`/client setting | MIME tree + client mode |
| Broken CID image | Part mapping/CID/related tree | Content-ID, src, client screenshot |
| Remote image fails to load | Client image policy/CDN/network | URL, proxy logs, settings |
| CSS table breaks in one client | Rendering compatibility | Template version + screenshot |
| Garbled Vietnamese subject | Charset/header encoding | Decoded subject + client |
| Wrong PDF filename | MIME filename encoding/Content-Disposition | Parsed filename + client |
| CTA opens wrong URL | Link generation/rewriting/deep links | Destination, redirects, test click |
| Text disappears in dark mode | Theme/style handling | Light/dark screenshots |
| Missing content after Forward | Client behavior/MIME resource refs | Original vs forwarded message |
| OTP expired when link opens | Business token lifetime/timing | IssuedAt/expiry, client behavior |

Never swap SMTP hosts just because border-radius disappeared, and never tweak CSS to fix a message missing an HTML part.

## 82. Triage workflow for a rendering bug

```text
User reports rendering issue
           |
           v
Identify notification + template version
           |
           v
Confirm SMTP/delivery and mailbox received
           |
           v
Inspect decoded MIME structure
           |
           +-- Invalid MIME -> fix composer/encoding
           |
           v
Reproduce on same client/version/settings
           |
           +-- Client-specific -> improve fallback
           |
           v
Compare baseline and new screenshot
           |
           v
Test representative other clients
           |
           v
Release/regression checks
```

If the message holds personal data, triage using a **synthetic fixture** matching the template and boundary values instead of forwarding raw production MIME to a developer group.

## 83. Bug reports must carry reproduction details

A genuinely helpful ticket:

```text
Template: order-confirmation
Template version: 7
Fixture: long-customer-name
Client: Outlook desktop
Client version: recorded
OS: Windows
Theme: dark
Images: disabled
Viewport: narrow reading pane
Symptom: CTA label appears dark on dark background
Expected: readable CTA text with working URL
Actual: label has insufficient contrast
Evidence: restricted screenshot + sanitized MIME reference
```

Avoid vague tickets like:

> Email is broken in Outlook.

which omit version and reproduction conditions.

## 84. Reproduce from matching inputs instead of guessing from screenshots

Production screenshots may use dynamic data absent from staging. To reproduce:

1. Grab the template version and code commit.
2. Build a synthetic fixture with matching shape (long names, amounts, many items).
3. Render with the same composer/MIME mode.
4. Send along a test route with comparable content processing.
5. Open in the matching client version and settings.
6. Compare MIME and screenshots.

**You do not need to copy a real customer’s entire email to reproduce a padding bug.** Keep only the relevant data characteristics.

## 85. Client updates can introduce regressions

Code changes are not the only source of bugs. Mail clients update rendering behavior or security policies, affecting emails that previously passed.

Therefore:

- Keep baseline fixtures.
- Schedule retests on key clients after major updates.
- Record client versions alongside results.
- Never assume a newly deployed template caused a failure if a client update triggered it.
- When caused by uncontrollable client behavior, strengthen fallbacks and reduce reliance on fragile features.

## 86. Email providers can rewrite messages

Between Spring Mail and the mailbox:

```text
Spring-generated MIME
        |
        v
SMTP provider
        |
        +-- DKIM signing
        +-- Headers additions
        +-- Link tracking, if enabled
        +-- Security or policy processing
        |
        v
Received MIME
```

Exact behavior varies by provider/config. If Spring generates clean raw MIME yet the received copy has altered links/headers, inspect the **actual received message** and provider settings.

An internal SMTP capture server bypassing the provider may miss those rewrites. That is why real-client tests through the **corresponding test route** are so valuable.

## 87. Why third-party preview screenshot services are not enough either

Rendering preview services quickly supply many client screenshots, useful for regression checks. Still:

- Their versions may differ from your users’ environments.
- Enterprise security policies/gateways may not match test accounts.
- Link clicks, forwarding, and replies are not fully exercised.
- Messages may traverse a different provider than your production route.
- Uploading raw email fixtures can pose data risks if unauthorized.

Use such tools to **supplement** your test matrix, not replace 100% of testing on supported mail clients/devices.

## 88. Never upload real emails to public preview services

Raw emails can contain:

- To/Cc/Bcc.
- OTPs/reset links.
- Sensitive invoices/documents.
- Tracking identifiers.
- Account IDs.
- Attachment bytes.

When using preview tools:

1. Use synthetic fixtures exclusively.
2. Verify tool permissions and data-retention policies.
3. Never use live one-time links belonging to real people.
4. Never share unredacted `.eml` files in public tickets.
5. Restrict who can view screenshots and test artifacts.
6. Delete artifacts per retention policy.

Test data safety is part of release quality, not an optional cleanup step after a leak.

## 89. Template release workflow

A pipeline might run:

```text
PR changes HTML/template
        |
        v
Render approved synthetic fixtures
        |
        v
Unit tests on business fields
        |
        v
MIME structure/encoding tests
        |
        v
SMTP capture test
        |
        v
Seed mailbox dispatch (approved)
        |
        v
Real client matrix
        |
        v
Review screenshots + interactions
        |
        v
Versioned release + rollback plan
```

Not every punctuation edit requires re-shooting the entire matrix, yet changes to layout, CSS, MIME, or CTAs should trigger at least the tests at risk of regression.

## 90. Prioritizing rendering bugs

| Severity | Examples | Action |
| --- | --- | --- |
| Critical | Wrong customer data, link to wrong tenant, unreadable OTP | Block release, check security/business logic |
| High | Unusable CTA on a major client; truncated amount | Block/review per release criteria |
| Medium | Missing logo while core content stays intact | Fix per priority and client scope |
| Low | Border radius/shadow differs from mockup | Accept if visual policy allows |

Never set severity solely by pixel diff counts. Evaluate **user impact and share of affected clients**.

## 91. Design for fallbacks, not only the “best case”

A robust email:

```text
Images ON, CSS full:    Crisp and easy to read
Images OFF:             Content still clear
CSS limited:            Simple layout, still usable
Mobile narrow:          CTA and numbers intact
Dark mode:              Sufficient contrast
Plain text:             Equivalent facts and links
Forward:                Key information preserved
```

This is a far more realistic goal than “every pixel matches the design”.

## 92. Testing dynamic templates: ugly data beats pretty sample data

Build fixtures such as:

| Fixture | What it tests |
| --- | --- |
| 1-character name | Whitespace, salutation |
| Very long name | Wrapping/overflow |
| Vietnamese accented name | UTF-8, font fallback |
| Multilingual name | Unicode/RTL |
| Zero items | Empty state |
| 1 item | Short layout |
| 50 items | Email length/clipping |
| Huge price | Number column, line wrapping |
| Long accented filename | Attachment filename |
| Long URL | Wrapping/tap targets |
| Missing optional field | Placeholders/fallbacks |
| Images disabled | Content independent of images |

Never use a single “John Doe / 1 item / $10” fixture to represent all emails.

## 93. Dynamic emails need proper escaping

Suppose a user enters a name:

```text
An <script>alert(1)</script>
```

Never concatenate directly into HTML:

```java
String html = "<p>Hello " + userName + "</p>";
```

Mail clients usually block scripts, yet HTML injection can still break markup, inject fake links, or distort display. Use a template engine with context-aware HTML escaping, input validation, and URL/HTML allowlists where needed.

**HTML escaping tests** belong at the unit/integration layers, alongside opening a special-character fixture in a mail client to confirm strings render as text rather than unintended markup.

## 94. HTML links need scheme and host validation

If a URL comes from user input:

```java
helper.setText(
    "<a href='" + userUrl + "'>View details</a>",
    true
);
```

the template may get an unwanted URL injected or break on unescaped quotes.

Always:

- Construct URLs from approved base URLs.
- Validate HTTPS scheme/host/path per use case.
- Encode query parameters properly.
- Let the template engine escape attribute values.
- Disallow `javascript:` or inappropriate schemes.
- Test click-through in real clients.

Never rely on mail client sanitization in place of application-side input validation and access control.

## 95. Unsubscribe links and footers must work in clients

For emails requiring an unsubscribe mechanism per policy:

- The link must be visible and easy to tap.
- The URL must not render broken.
- Do not force manually copying a huge token.
- Backend opt-out rules must enforce suppression even when mailed through another provider.
- Avoid leaking extra recipient data inside unnecessary link parameters.

When testing, click unsubscribe in a seed account and confirm only test data changes. Never modify real users during tests.

## 96. An application may use multiple SMTP providers

The same template can pass through:

```text
Template T-454
    |
    +-- Provider A -> recipient client
    |
    +-- Provider B -> recipient client
```

Providers can inject headers, rewrite links, or apply distinct policies. If production uses two real routes, run **test cases through both routes**, rather than only testing directly from a local SMTP server.

That does not mean sending two copies to the same real customer to compare. Use dedicated **test mailboxes** and test IDs to avoid spamming real users.

## 97. Regressions can come from template engine or mail library upgrades

When upgrading Spring Framework, the Jakarta Mail implementation, or the template engine:

- Content-Type/multipart nesting can shift if composition code differs.
- Charset/filename behavior needs re-checking.
- Header encoding/line folding may change.
- Resource lifecycle or serialization timing can shift.
- Template auto-escaping/rendering may change.

Therefore, after upgrades affecting the mail layer, re-run MIME tests and representative real-client fixtures. Never assume “we did not touch the HTML file, so rendering is guaranteed identical”.

## 98. Minimal checklist for every template release

### Content and privacy

- [ ] Subject, From, and Reply-To are accurate.
- [ ] Business facts match across plain text and HTML.
- [ ] No production data used in tests.
- [ ] No OTPs/tokens/PII leaked in preheaders or screenshots.
- [ ] Links point to valid domains.
- [ ] No accidental recipients or Bcc leaks.

### MIME

- [ ] HTML part has `text/html` and right charset.
- [ ] Plain text part holds complete core content.
- [ ] `multipart/alternative` and part structure are sound.
- [ ] Inline CIDs match and images carry alt text.
- [ ] Attachment filenames/types/bytes are exact.
- [ ] No temp files deleted before serialization.

### Client rendering

- [ ] At least one key webmail and one key mobile client tested.
- [ ] Outlook/enterprise client checked if in audience.
- [ ] Dark mode and blocked images reviewed.
- [ ] Long-text/UTF-8/boundary fixtures checked.
- [ ] CTAs stay functional under restricted CSS.
- [ ] No critical content clipped or overflowing.
- [ ] Reply/Forward tested if required by use case.
- [ ] Baseline accessibility observed.

### Operations

- [ ] Test run logs template version and client metadata.
- [ ] Screenshots/evidence stored in authorized locations.
- [ ] Severity classification and rollback plan documented.
- [ ] No raw MIME or tokens logged.
- [ ] No mass sending to real users.

## 99. Runbook: “Literal HTML tags show up in Gmail”

A user reports seeing:

```text
<h1>Xin chào</h1><p>Đơn hàng xác nhận</p>
```

instead of rendered headings and paragraphs.

**Steps:**

1. Confirm client/version and exact received email.
2. Read the body part’s `Content-Type` with a MIME parser.
3. Check whether `SimpleMailMessage` sent HTML as `text/plain`.
4. If using `MimeMessageHelper`, check `setText(html, true)` or `setText(plain, html)`.
5. Inspect raw multipart structure.
6. Re-send a synthetic fixture through test SMTP and seed mailboxes.
7. Check results in at least one additional client.

**Never try to fix MIME content types by editing CSS.**

## 100. Runbook: “Inline image shows as an attachment”

Symptom: the logo shows up as a separate attachment or does not appear inline in HTML.

Check:

- Does HTML use `src="cid:brand-logo"`?
- Does the MIME part have a matching `Content-ID: <brand-logo>`?
- Is the content type valid (`image/png`/`image/jpeg`)?
- Does the part sit inside a proper `multipart/related` structure?
- Was `helper.setText(...)` called before `addInline(...)`?
- Did the image resource stay alive until serialize/send?
- Does the client enforce special rules for inline images?

If MIME is valid yet a client still shows an attachment, weigh fallback text/remote images per policy and client matrix; do not try to “hide every attachment” with non-standard metadata.

## 101. Runbook: “Button background disappears in Outlook”

1. Record the exact Outlook version, OS, and reading pane mode.
2. Inspect HTML and rendered appearance via real screenshots.
3. Check whether the button relies on unsupported CSS backgrounds/properties.
4. Ensure the text label and `href` still work.
5. Test an email-compatible button pattern with fallbacks.
6. Re-check other clients to prevent regressions.
7. Do not insist every client match border-radius/shadows if UX stays solid.

A fix that looks good in Outlook yet breaks Gmail mobile is incomplete.

## 102. Runbook: “Text disappears in dark mode”

Symptom:

```text
Light: white button text on blue background
Dark:  white button text on lightened/white background
```

Workflow:

- Reproduce with the exact template, client, and theme.
- Inspect text/background regions altered by the client.
- Set sensible text/background fallbacks and avoid brittle color pairings.
- Check transparent logos/images.
- Test with images enabled and disabled.
- Check CTAs under enlarged text and contrast tools where possible.

Never design a fix relying solely on a dark-mode media query if target clients ignore it or apply proprietary color-inversion algorithms.

## 103. Runbook: “Email reads fine on desktop, overflows on mobile”

Common causes:

- Large fixed container/table widths.
- Long unbroken URLs.
- Data rows with too many columns.
- Fixed image widths/heights.
- `white-space: nowrap` on text.
- Buttons with excessive padding/width.
- Enlarged fonts inside fixed-height containers.

Fixes:

1. Isolate the overflowing element using a minimal fixture.
2. Switch to single-column or stacking layouts.
3. Allow images to scale within containers.
4. Shorten display link text while preserving the right `href`.
5. Summarize wide tables and link to a portal when appropriate.
6. Test narrow viewports and large text.

Do not shrink all fonts down to 10 px just to “fit the screen”; that creates new accessibility failures.

## 104. Runbook: “Vietnamese text in subject or filename is garbled”

1. Verify the original string before template rendering is intact.
2. Check source file, template, and database encodings.
3. Check `MimeMessageHelper` charset.
4. Read decoded Subject and filename via Jakarta Mail APIs.
5. Inspect MIME `Content-Type` headers and filename parameters.
6. Send a synthetic fixture with accented characters over a test route.
7. Open in at least two representative mail clients.

Never “fix” encoding issues by stripping all Vietnamese diacritics when the product requires Vietnamese text. Find the real encoding bug.

## 105. Runbook: “Link in email opens the wrong page”

1. Inspect the source link rendered by the template.
2. Check HTML attribute escaping and URL encoding.
3. Check provider redirect/tracking/security rewrites.
4. Click the link inside a real client.
5. Verify scheme, hostname, destination, and tenant access.
6. Test mobile deep-link behavior if applicable.
7. Check token timeouts and security scanner prefetching.
8. Log error category, never raw tokens or sensitive URLs.

Do not blame the client if the application generated the wrong source `href`.

## 106. Runbook: “Attachment missing in certain clients”

1. Check raw MIME to confirm the attachment part exists.
2. Parse `Content-Disposition`, `Content-Type`, and filename.
3. Compare decoded file bytes against the fixture.
4. Check resource lifecycle and size limits.
5. Check whether the provider/gateway blocks that file type.
6. Check whether the client app or OS applies security blocks.
7. Open from the test mailbox in another client.
8. If necessary, switch to an authorized portal download.

An attachment stripped by a security gateway **differs** from a `helper.addAttachment(...)` bug in Spring.

## 107. Runbook: “Email never appears in Inbox”

A bug report might say “email layout not showing” when the test mailbox never received the email at all.

Investigation order:

1. Did the producer/outbox create the notification?
2. Was `JavaMailSender.send(...)` called and what was the outcome?
3. Did SMTP/provider accept or reject?
4. Was there deferred, bounce, or suppression feedback?
5. Is the message sitting in Spam/Other/Quarantine?
6. Are From domain, SPF/DKIM/DMARC, and account routing right?
7. Only once the message arrives should you evaluate rendering.

Never modify HTML/CSS blindly in response to a “missing email” bug without checking delivery first.

## 108. Testing security emails: OTP

Mandatory observations:

```text
Subject: Verification code
Preheader: Do not leak too much on lock screens
Body: Code large enough, easy to copy
Plain: Code and expiration present
CTA: Valid domain link, never auto-activates
Dark: Code preserves contrast
Images off: Code still visible
Mobile: Code never clipped
```

A practical checklist:

- [ ] Code is not trapped inside an image.
- [ ] Code is not padded with spaces or invisible characters that break copying.
- [ ] Plain text and HTML display the same code.
- [ ] Expiration period is stated clearly.
- [ ] Expired OTPs are not accidentally resent using stale content.
- [ ] Tokens are never leaked in screenshots or public test artifacts.
- [ ] Security scanners cannot auto-complete verification.

## 109. Testing invoice emails

Check:

- Subject and order ID are accurate.
- Monetary totals, taxes, and discounts are accurate.
- Tables remain readable on mobile.
- Plain text content does not contradict HTML.
- PDF attachment has exact bytes, filename, and charset.
- Re-download links enforce proper permissions.
- No unnecessary financial details leak in the Subject.
- Forwarded copies retain required info if the use case expects forwarding.

An invoice email with a broken table and obscured total is a business bug even if decorative artwork looks great.

## 110. Testing marketing emails

Check:

- Meaningful preheader.
- Logo, headline, and CTA stay visible in dark mode and with images blocked.
- Single-column mobile layout is readable.
- Unsubscribe is accessible and functions per policy.
- Key promotional details are not trapped solely inside images.
- No broken or malformed tracking links.
- Clipping does not cut off terms/disclosures.
- Suitable plain text alternative exists.

No real mailing list is needed for testing; seed accounts and synthetic campaign fixtures catch most template and interaction bugs.

## 111. Exercise 1 — Browser preview passes, Outlook shows a white button

You have HTML using `border-radius` and CSS backgrounds for a CTA. Browser previews look great, while Outlook desktop renders a white button with white text.

**Task:** Identify the failure layer and design a test plan.

**Hint:** check client rendering, switch to a button with compatible background/text fallbacks, reproduce in that specific Outlook version, and test dark mode/Gmail/mobile to prevent regressions.

## 112. Exercise 2 — HTML and plain text show different amounts

HTML shows 120,000 VND, while `text/plain` shows 12,000 VND.

**Hint:** render both representations from the exact same validated template model. Add unit assertions and open in a text-only client rather than checking HTML alone.

## 113. Exercise 3 — CID image missing on mobile

Raw HTML uses `cid:logo`, yet the helper generated a different Content-ID. In one client the image loads, in another it does not.

**Hint:** parse the MIME tree, check Content-ID/references and nesting; send fixtures to seed mailboxes and test images on/off. Never treat one client’s auto-recovery as a universal contract.

## 114. Exercise 4 — Email truncated at the bottom

The template is long, and the footer and support link at the end fail to appear cleanly in a client.

**Hint:** trim repetitive markup, move key content higher, test a long-content fixture, and observe client clipping behavior. Never rely on one fixed HTML size threshold across all clients.

## 115. Exercise 5 — Downloaded invoice filename is garbled

`MimeMessageHelper.addAttachment("Hóa đơn 2026.pdf", ...)` was called, yet one client displays an encoding-corrupted filename.

**Hint:** inspect UTF-8 source, MIME-encoded filename parameters, decoded parser output, and client-specific behavior; consider an ASCII fallback filename if legacy clients require it.

## 116. Exercise 6 — Link opened automatically by a scanner

An email uses a GET link to confirm a transaction immediately, and a security gateway visits it before the user.

**Hint:** have the link open a page with a protected confirmation step; never trigger sensitive side effects on GET alone. Test end-to-end against a representative gateway environment.

## 117. Exercise 7 — Images blocked, blank email

The entire announcement is one infographic. Gmail mobile blocks images, leaving the recipient unable to read anything.

**Hint:** convert key info into HTML text + plain text, use images for illustration with alt text, and test with images disabled.

## 118. Exercise 8 — Staging test mailed real customers

A developer swapped `To` for addresses from the production database to see if real emails looked right.

**Hint:** risk of accidental delivery and PII leakage. Enforce allowlisted seed recipients, synthetic fixtures, test sender domains, and staging URLs; enforce a policy blocking any non-allowlisted recipient right before SMTP.

## 119. Exercise 9 — Screenshot tests pass, yet link points to the wrong account

Screenshots match the mockup, yet “View order” navigates to another user’s account.

**Hint:** screenshots do not test click behavior or authorization. Verify URLs, recipient bindings, tenant scoping, and browser destination; classify this as a severe security/logic bug.

## 120. Exercise 10 — Testing only one Outlook edition

The team tested Outlook web and assumed classic Outlook desktop renders identically.

**Hint:** you cannot extrapolate that. Use a client usage matrix, record version/OS, and test at least the supported editions used by your audience.

## 121. Exercise 11 — Forwarding drops the logo

The originally received email contains a CID image, yet forwarding it from another client drops the graphic.

**Hint:** test the forward workflow with the same fixture, inspect the forwarded message’s MIME structure, and decide whether the logo is essential or decorative. Ensure key text never depends on images.

## 122. Exercise 12 — Very long names overflow the screen

The template was tested with “An”, then hit multi-word long names in production; tables and CTAs stretched off-screen.

**Hint:** use boundary fixtures, responsive text wrapping, avoid inappropriate fixed widths or `nowrap`, and test narrow mobile screens with enlarged text.

## 123. Core principles to remember

1. **SMTP submission does not prove an email renders properly.**
2. **A browser preview is not a mail client test.**
3. **MIME structure and client rendering are two separate testing layers**.
4. **Plain text and HTML must share core business facts**.
5. **CIDs/attachments need valid Content-IDs, dispositions, charsets, and lifecycles**.
6. **Email HTML should favor progressive enhancement and fallbacks**, without relying on scripts or modern CSS.
7. **Dark mode, disabled images, and mobile widths must be intentional test conditions**.
8. **Accessibility outweighs pixel perfection** when the two conflict.
9. **CTAs must be clickable and reach the right destination**, not merely have nice background colors.
10. **Test matrices must reflect real users, client versions, and template criticality**.
11. **Seed mailboxes and synthetic fixtures let you test safely** without bothering customers.
12. **SMTP capture tests transport/MIME**, never replacing real-client rendering.
13. **Screenshots are only one form of evidence**; pair them with interactions and raw MIME when needed.
14. **Breakage can come from provider/security-gateway rewrites**, not necessarily Spring.
15. **Template releases need versioning, regression tests, and reproducible triage**.

## 124. References for further reading

- Spring Framework — Email Integration: https://docs.spring.io/spring-framework/reference/integration/email.html
- Spring Boot — Sending Email: https://docs.spring.io/spring-boot/reference/io/email.html
- Jakarta Mail API: https://jakarta.ee/specifications/mail/
- W3C — Web Content Accessibility Guidelines: https://www.w3.org/WAI/standards-guidelines/wcag/

Spring and Jakarta Mail documentation help verify MIME construction. They **cannot replace** opening emails in the real clients your product supports. HTML/CSS support across Gmail, Outlook, Apple Mail, and other clients must be checked against real versions and features rather than treating an outdated support table as the sole truth.

## 125. Conclusion

**Not testing messages in real mail clients** is a process gap that lets an email pass SMTP and MIME checks yet still fail in the user experience: unreadable text, invisible CTAs, misformatted amounts, missing graphics, broken links, or unopenable attachments. Spring Framework Mail helps build and submit emails, yet **cannot simulate every rendering engine, security policy, and recipient device**.

To prevent this mistake, build emails with **plain text fallbacks, well-structured HTML/MIME, defensive CSS with fallbacks, clean UTF-8 data, text/CTAs independent of images, and support for mobile and dark mode**. After unit tests and SMTP/MIME inspection, send **synthetic messages over approved test routes** to seed mailboxes, open them across a representative client/OS/theme matrix, check copy, links, attachments, and legibility, and record evidence/versions so regressions stay reproducible.

The goal is not an email identical down to every pixel on every screen, but one that is **accurate, safe, readable, and actionable** under the real conditions your recipients use. Once mail client verification becomes part of template releases, teams catch defects before customers report them—and cleanly separate MIME composition, sending, client rendering, and business-logic bugs.
