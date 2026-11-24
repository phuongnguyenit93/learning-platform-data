# Testing Across Different Mail Clients

An HTML email can be generated accurately in a Spring application and still render differently when the recipient opens it in Gmail, Outlook, Apple Mail, or a mobile mail app. A web browser generally supports HTML/CSS more broadly than email environments; therefore, opening an HTML file in Chrome and seeing it look good **does not prove the email will render the same way in an inbox**.

In **Spring Framework Mail**, applications typically use a template engine to generate HTML, `MimeMessageHelper` to build the MIME message, and `JavaMailSender` to send it over SMTP. Those steps determine the content and structure of the outgoing message. How a mail client interprets HTML, CSS, images, fonts, and dark mode depends on each client, version, platform, and recipient setting.

Testing across multiple mail clients is part of email development, helping uncover layout bugs, missing images, hard-to-tap links, missing content in the text version, Vietnamese encoding issues, and desktop-versus-mobile differences before sending to real users.

## 1. Why Can the Same Email Display Differently?

An HTML email passes through multiple layers:

```text
Spring Application
   |
   | Template engine renders HTML and text
   v
MimeMessageHelper
   |
   | MIME parts, charset, inline resources, attachments
   v
JavaMailSender / Jakarta Mail
   |
   | SMTP submission
   v
Mail server / mailbox
   |
   | Mail client receives and interprets message
   v
Gmail / Outlook / Apple Mail / mobile app
   |
   v
User sees the email
```

HTML emails are not rendered in a single uniform environment. Factors that can make results vary:

- **HTML/CSS support:** clients may ignore or alter how certain tags, attributes, selectors, or CSS properties are handled.
- **Rendering engine:** applications may use different engines; even Outlook versions on Windows do not necessarily behave identically to Outlook on the web or the new app.
- **MIME structure:** clients pick the text/HTML part in `multipart/alternative` and handle inline resources and attachments in their own ways.
- **Image policy:** images from external URLs may be blocked, loaded through a proxy, or shown only after user permission.
- **Dark mode:** clients or operating systems may swap background colors, text, and images to suit dark mode.
- **Viewport and fonts:** small screens, zoom levels, system fonts, and fallback fonts affect width, line wrapping, and height.
- **User settings:** text-only reading mode, image blocking, accessibility, zoom, or user preferences change the outcome.

Therefore, the goal of testing is to ensure **important content remains readable and primary actions remain executable** in the clients the product supports. Do not assume every pixel will look identical across all environments.

## 2. Which Mail Clients Should Be Included in the Test Matrix?

There is no fixed list that fits every product. Choose clients based on your actual recipient audience, devices, and email criticality.

A typical starting matrix includes:

| Client group | Environment example | What to watch |
| --- | --- | --- |
| Gmail web | Gmail in a desktop browser | Restricted/transformed CSS, external images, links, MIME structure |
| Gmail mobile | Gmail app on Android/iOS | Width, font size, buttons, long content |
| Classic Outlook on Windows | Traditional Outlook desktop version | HTML/CSS rendering differences, spacing, and tables |
| New Outlook / Outlook web | New Outlook or Outlook on the web | Does not automatically match classic Outlook; test separately |
| Apple Mail on macOS | Mail on Mac | Fonts, dark mode, inline images, and layout |
| Apple Mail on iPhone/iPad | Mail on iOS/iPadOS | Responsive layout, touch targets, fonts, and images |
| Yahoo Mail | Web or mobile if used by audience | CSS, images, and links |
| Other enterprise clients | e.g. organization-deployed clients | Security policies, image proxies, and custom display rules |

### Prioritize by Audience

For example, if most customers open mail on phones, prioritize Gmail mobile and Apple Mail iOS in the main test cycle. If the email serves enterprise employees, Outlook on Windows and Outlook web may carry higher priority.

One way to categorize:

- **Tier 1:** clients accounting for the majority of opens or affecting core business flows.
- **Tier 2:** clients used by a significant segment of recipients.
- **Tier 3:** rare clients or those tested only on major changes.

You do not need to run every client/OS/browser combination on every edit. However, whenever shared templates, CSS layouts, MIME structure, or inline images change, re-run affected environments.

## 3. Distinguishing HTML Checks, MIME Checks, and Real Rendering

An email can pass an HTML check and still fail when sent. Separate testing layers:

| Layer | Question | Tool / check method |
| --- | --- | --- |
| Template rendering | Are variables substituted right, is HTML structure valid? | Renderer unit tests, HTML output inspection |
| MIME composition | Are text/HTML parts, charset, CID, and attachments right? | Jakarta Mail inspection, SMTP capture |
| SMTP submission | Can the application submit to the SMTP server? | Integration tests, logs, and SMTP responses |
| Delivery | Does the mail server accept/deliver the message? | Provider events, bounces, delivery logs |
| Client rendering | How does the recipient see the email? | Real inboxes on target clients/devices |
| User interaction | Do links, buttons, images, and attachments work? | Click tests, download tests, flow checks |

**SMTP send success does not mean the email renders properly.** Likewise, a clean screenshot does not prove recipients, links, or attachments work.

### Do Not Use Browser Preview as the Sole Evidence

Opening a template in Chrome is useful for checking basic structure and content. Yet browsers do not fully simulate:

- How clients parse MIME.
- Selection of `text/plain` vs. `text/html`.
- How clients filter CSS/HTML.
- External image blocking policies.
- Mail app dark mode.
- Outlook rendering engine differences.
- Image proxying or caching.

Browser preview is an early check; you still must send the email over SMTP into a test mailbox and open it in real clients.

## 4. Preparing a Multi-Format Message in Spring Mail

To test across multiple clients, an email should have HTML content and a corresponding plain text version. `MimeMessageHelper.setText(plainText, htmlText)` creates alternative content in MIME.

### 4.1. Example Using `MimeMessageHelper`

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class PreviewMailService {

    private final JavaMailSender mailSender;

    public PreviewMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendPreview(String recipient)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("preview@example.org");
        helper.setTo(recipient);
        helper.setSubject("Testing email across multiple mail clients");

        String plain = """
                Hello,

                This email is used to test content across multiple mail clients.
                Reference code: PREVIEW-2026-001
                View details: https://app.example.org/preview/PREVIEW-2026-001
                """;

        String html = """
                <!doctype html>
                <html lang="en">
                <head>
                  <meta charset="UTF-8">
                  <meta name="viewport"
                        content="width=device-width, initial-scale=1.0">
                  <title>Email Test</title>
                </head>
                <body style="margin:0;padding:24px;font-family:Arial,sans-serif;">
                  <table role="presentation" width="100%"
                         cellspacing="0" cellpadding="0" border="0">
                    <tr>
                      <td align="center">
                        <table role="presentation" width="600"
                               cellspacing="0" cellpadding="0" border="0"
                               style="width:100%;max-width:600px;">
                          <tr>
                            <td style="padding:24px;background:#ffffff;">
                              <h1 style="font-size:24px;line-height:1.3;">
                                Hello
                              </h1>
                              <p>
                                This email is used to test across multiple
                                mail clients.
                              </p>
                              <p>
                                Reference code:
                                <strong>PREVIEW-2026-001</strong>
                              </p>
                              <p>
                                <a href="https://app.example.org/preview/PREVIEW-2026-001"
                                   style="display:inline-block;padding:12px 18px;
                                          background:#175cd3;color:#ffffff;
                                          text-decoration:none;">
                                  View details
                                </a>
                              </p>
                            </td>
                          </tr>
                        </table>
                      </td>
                    </tr>
                  </table>
                </body>
                </html>
                """;

        helper.setText(plain, html);
        mailSender.send(message);
    }
}
```

This is a structural example for testing. In real applications, content should be rendered by a template engine and URLs must be generated by the backend from a trusted domain. The sender address must belong to a domain authorized by the SMTP provider.

### 4.2. Why Is a Text Version Needed?

`multipart/alternative` lets a message carry multiple representations of the same content:

```text
MimeMessage
└── multipart/alternative
    ├── text/plain; charset=UTF-8
    │     Hello...
    │     View details: https://...
    │
    └── text/html; charset=UTF-8
          <h1>Hello</h1>
          <a href="https://...">View details</a>
```

Mail clients can choose the part suited to their capabilities or preferences. The text version should not be just a line saying "please view the HTML email"; it must convey key information and links so recipients can still complete the task.

If you only call `helper.setText(html, true)`, the message has an HTML body without an application-supplied alternative text version. For transactional emails, preparing both is usually advisable.

### 4.3. Inline Images and Attachments

If a template references an image with `cid:`, you must add the corresponding MIME part:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);

String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";
String html = renderTemplate(logoCid);

helper.setFrom("preview@example.org");
helper.setTo(recipient);
helper.setSubject("Email with inline image and attachment");
helper.setText(
        "Email contains a logo and an attached PDF file.",
        html
);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addAttachment(
        "guide.pdf",
        new ClassPathResource("mail/guide.pdf"),
        "application/pdf"
);

mailSender.send(message);
```

This snippet assumes `renderTemplate(logoCid)` is a function rendering HTML with the matching `cid:` reference and `recipient` has been validated. Call `setText` before `addInline` per normal `MimeMessageHelper` usage.

When testing, check separately:

- Whether the inline image displays or merely shows up as an attachment.
- Whether the CID in HTML matches the MIME part's `Content-ID`.
- Whether the PDF opens and its bytes are intact.
- Whether the client displays a sensible filename and media type.

## 5. Designing HTML Emails for Compatibility

HTML emails must be designed for the realistic capabilities of mail clients. Some modern web techniques may not be uniformly supported or may be stripped by clients.

### 5.1. Use Simple Layouts with Fallbacks

For emails needing broad client support, HTML table structures (`table`) are commonly used for the primary layout due to wide compatibility:

```html
<table role="presentation"
       width="100%"
       cellpadding="0"
       cellspacing="0"
       border="0">
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
            Email content
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
```

`role="presentation"` tells assistive technologies that the table is used for layout, not tabular data. When content genuinely represents tabular data, use proper table semantics instead of adding a presentation role.

This does not mean tables must be used for every element. Keep structures simple with minimal reliance on complex CSS, and test on target clients.

### 5.2. Inline CSS for Critical Styles

Some clients handle `<style>` blocks or CSS selectors differently. For core styles such as background color, font size, padding, and alignment, inline CSS is usually the practical choice:

```html
<p style="margin:0 0 16px 0;
          font-family:Arial,sans-serif;
          font-size:16px;
          line-height:24px;
          color:#344054;">
  Notification content
</p>
```

Do not rely on an external stylesheet or complex selectors for essential details. If using media queries for mobile adjustments, treat them as progressive enhancements and check whether target clients support them.

### 5.3. Width and Responsiveness

An email template typically uses a width-constrained container, such as around 600px, while shrinking with the viewport:

```html
<table role="presentation"
       width="100%"
       cellpadding="0"
       cellspacing="0"
       border="0">
  <tr>
    <td align="center">
      <table role="presentation"
             width="600"
             cellpadding="0"
             cellspacing="0"
             border="0"
             style="width:100%;max-width:600px;">
        ...
      </table>
    </td>
  </tr>
</table>
```

A 600px width is just a common starting point, not a strict limit. Verify:

- No horizontal scrollbar appears on mobile screens.
- Text is not scaled down excessively.
- Long data tables scroll or display sensibly.
- Action buttons are large enough to tap.
- Images do not exceed container width.
- Content remains readable when zoomed.

### 5.4. Font Fallbacks

Not every mail client can load web fonts or allow external fonts. Declare a font stack with fallbacks:

```html
<p style="font-family:Arial,Helvetica,sans-serif;">
  Email content
</p>
```

If a brand font fails to load, text can still render in a system font. Do not depend on a single font for essential information.

### 5.5. Buttons Should Be Real Links

An action button in an email is typically a styled anchor tag:

```html
<a href="https://app.example.org/orders/123"
   style="display:inline-block;
          padding:12px 18px;
          background-color:#175cd3;
          color:#ffffff;
          text-decoration:none;
          border-radius:4px;">
  View order
</a>
```

Do not use JavaScript, form submissions, or event handlers to perform actions inside emails. Mail clients normally restrict scripts and forms. A clear HTTPS anchor can open in a browser or app.

If the product requires pixel-accurate button shapes in certain desktop Outlook versions, specific compatibility techniques (such as VML for certain cases) may be needed. Add them only when the real client matrix demands it, and retest across all remaining clients.

## 6. Checking Content When Images Are Blocked

Many mail clients do not load external images immediately upon opening an email. Users can also deliberately disable image loading.

An email must not lose its entire meaning when images do not appear:

```html
<img src="https://cdn.example.org/mail/banner.png"
     alt="Special offer for your order"
     width="560"
     style="display:block;width:100%;max-width:560px;height:auto;"/>
```

Verify:

- `alt` describes the image meaningfully when the image is hidden.
- Confirmation codes, prices, or legal text are never placed solely inside images.
- Links/buttons do not depend on images for recipients to understand the action.
- Images are sized sensibly, avoiding oversized files.
- If using inline CID, the MIME part and Content-ID match.
- If using external URLs, verify HTTPS and reachability from recipient environments.

### CID Images vs. External URL Images

| Criterion | CID inline | HTTPS URL |
| --- | --- | --- |
| Image data | Embedded in the MIME message | Hosted on server/CDN |
| Separate image request needed | No web request needed to fetch CID image | Normally fetches URL, possibly via proxy/cache |
| Email size | Increases with image size and MIME encoding | Smaller email, but depends on external image |
| Privacy | Generates no request to image server when opening CID image | May trigger request or log when client fetches image |
| Blocking risk | Client may still omit displaying inline resources | Client may block external images |
| Image updates | Image in sent email does not change | Content at URL may change after sending |

Choose the approach fitting your goal and test on target clients. Regardless of which is used, essential information needs a text representation.

## 7. Testing Dark Mode

Dark mode is a major source of visual differences. A mail client may:

- Preserve original colors.
- Invert light backgrounds into dark backgrounds.
- Invert or adjust text colors.
- Alter link colors.
- Handle background images or logos differently from text colors.

A design that looks clean in light mode can lose contrast when clients automatically adjust colors. For instance, a logo with white text on a transparent background may vanish if the client turns the surface white or light.

### What to Check

| Component | Risk in dark mode | How to design / test |
| --- | --- | --- |
| Body background | Client changes background, removing visual separation | Check both original and transformed backgrounds |
| Text | Text color shifts or lacks contrast | Use legible colors, never convey meaning by color alone |
| Logo | Transparent or monochrome logo disappears | Prepare suitable variants or contrasting backdrop |
| Button | Background and text adjusted independently | Verify text and background remain clearly distinct |
| Border/divider | Separators become too faint | Avoid overly faint colors for critical structure |
| Link | Link color changes or becomes hard to spot | Include underline or non-color visual cues |
| Background image | May be ignored or altered | Provide fallback background color and content |

### Dark Mode CSS

Some clients support media queries like `prefers-color-scheme`, though support levels and application rules vary. For example:

```html
<style>
  @media (prefers-color-scheme: dark) {
    .email-card {
      background-color: #1f2937 !important;
      color: #f9fafb !important;
    }
  }
</style>
```

This is an enhancement for supporting clients; not all clients honor this rule or keep declared colors intact. Base background and text styles still need testing when the media query is not applied.

Do not assume you can force every mail client to stay in light mode using a meta tag or CSS rule. Check actual behavior and ensure content stays readable after client color adjustments.

## 8. Checking the Plain Text Version

With `multipart/alternative` emails, inspect the `text/plain` part separately, not only HTML.

Content checklist:

- Subject and email-identifying details are clear.
- Recipient name, reference code, and primary facts are present.
- Important links appear in full and can be copied.
- No leftover HTML tags like `<p>`, `<table>`, `<a>`.
- Links are not broken or joined with trailing punctuation that makes them hard to open.
- Information order makes sense without visual layout.
- Contact/support info is included when required by the business flow.
- Content does not rely on colors, icons, or images.

Example of text that should read naturally:

```text
Hello Nguyen An,

Order ORD-2026-001 has been confirmed.
Total: 1,250,000 VND

View order:
https://app.example.org/orders/ORD-2026-001

Best regards,
Support Team
```

Avoid creating the text version by mechanically stripping HTML tags if that breaks reading order or drops URLs. Creating a dedicated plain-text template or building text content intentionally is better.

## 9. Testing Vietnamese, Unicode, and Localization

Emails must be tested with realistic content rather than only simple ASCII strings.

Example test data:

```text
Name: Nguyễn Thị Ánh
Address: 12 Đường số 8, Phường An Khánh
Code: DH-2026-001
Amount: 1.250.000 ₫
Note: Giao hàng buổi chiều – gọi trước khi đến.
```

Verify:

- HTML body has an appropriate `charset=UTF-8`.
- Text version has an appropriate charset.
- Subject and From/To display names with diacritics are encoded properly.
- Currency symbols, en-dashes, curly quotes, and emojis render properly.
- No replacement characters like `` or unintended question marks appear.
- Dates, times, numbers, and currencies match the locale.
- Long content or multi-word names do not break layout.

`spring.mail.default-encoding=UTF-8` configures the default charset for the Spring Boot-created sender. However, it cannot repair strings already decoded with the wrong encoding from a database, file, or API prior to template rendering.

### Long Content and Translations

A template may look fine in English yet break when translated into Vietnamese, German, or languages with longer strings. Test with:

- Long recipient names.
- Long order codes.
- Long addresses.
- Long email subjects.
- Links with query strings.
- Translated copy longer than the source text.
- Empty/null values and optional fields.

Do not fix the height of text containers when content length can vary. Allow line wrapping and verify long words or URLs do not overflow containers.

## 10. Checking Links and Recipient Actions

A well-styled email still fails if an action button leads to the wrong URL or a link gets truncated.

Check every link:

1. Is the scheme HTTPS where appropriate?
2. Does the host/domain belong to the application or a trusted provider?
3. Are path and query components encoded properly?
4. Does the link work when opened on both desktop and mobile?
5. Does the recipient have access permissions after signing in?
6. Does any token have an expiration and stay out of logs?
7. Does the link still work if the mail client adds configured redirects/tracking?
8. Does the displayed link text accurately describe the destination?

Do not check only the main button. Emails may contain logo links, support links, unsubscribe links, or terms links. Each link should be verified against its purpose.

### Avoid Truncated or Hard-to-Copy URLs

In the text version, place URLs on their own line and avoid attaching punctuation immediately after a token if it could cause confusion. In HTML, use anchors with clear text. If a link is very long, use a backend-generated URL in a stable format rather than assembling complex query strings inside templates.

### Do Not Rely on JavaScript in Emails

Action buttons should be real links. An email is not a web page running in a browser; scripts, forms, and event handlers may be stripped or disabled. Actions requiring authentication/authorization should execute on the website or app after the user opens the link.

## 11. Checking Attachments and Inline Resources

When an email has multiple formats, check not only the HTML part but also other MIME parts.

| Component | What to check |
| --- | --- |
| `text/plain` | Complete content, no HTML markup, readable links |
| `text/html` | Renders properly, structure and CSS cause no errors |
| Inline image | CID matches, image displays, alt text is meaningful |
| PDF attachment | Opens cleanly, right filename, intact content |
| CSV attachment | Encoding, delimiters, header row, and data |
| Unicode filename | Filenames with diacritics display sensibly on target clients |
| Content-Type | Matches the payload bytes |
| Content-Disposition | Inline/attachment matches intent |

### Inspecting MIME Source

When a client fails to show an image or attachment, open the raw email source and look for:

```text
Content-Type: multipart/mixed
...
Content-Type: multipart/related
...
Content-Type: text/html; charset=UTF-8
...
Content-Type: image/png
Content-ID: <logo-...@mail.example.org>
Content-Disposition: inline
...
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
```

This is an illustrative structure; actual nesting and boundaries depend on the MIME message. Confirm:

- The HTML part has the right `Content-Type` and charset.
- Inline CIDs in HTML match part Content-IDs.
- Attachments have the right filename, media type, and bytes.
- `Content-Transfer-Encoding` is generated appropriately.
- No two distinct parts share the same CID.

Do not patch raw MIME by replacing header strings after the helper has built the message. Fix the message construction logic or resource source instead.

## 12. Tools and Testing Environments

No single tool replaces every testing layer. You can combine:

| Tool / tool category | Purpose | Limitations to understand |
| --- | --- | --- |
| Template renderer unit tests | Verify data renders properly with no missing variables | Does not simulate mail clients |
| Jakarta Mail inspection | Verify MIME parts, charset, CID, attachments | Does not verify visual rendering |
| GreenMail | Test SMTP server and inspect messages in integration tests | Does not render like Gmail/Outlook |
| Mailpit or MailHog | Capture emails in local/staging environments and view messages | Preview does not replace real clients |
| Real mailbox test accounts | Send to real Gmail/Outlook/Apple Mail | Requires managing test accounts and test data |
| Email rendering preview service | Preview across many clients/versions | Depends on service, plan, and simulation environment |
| HTML validator/linter | Catch basic markup errors | Valid HTML does not guarantee identical rendering across clients |
| Link checker | Verify URLs and responses | Must also test permissions and business flow |

### 12.1. Local SMTP Capture

During development, never send test emails to real customers. Configure the application to send to a local SMTP server such as Mailpit or MailHog. These tools capture messages to inspect:

- Subject, From, To.
- HTML and text versions.
- Raw MIME.
- Inline images and attachments.

This catches structural bugs before sending to real mailboxes. However, a capture tool's preview UI does not represent all mail clients.

### 12.2. Integration Tests with GreenMail

GreenMail can act as an SMTP server in tests to receive messages sent by `JavaMailSender`. Tests can then verify recipient, subject, MIME multiparts, and content.

Conceptual example:

```java
@Test
void sendsHtmlAndPlainTextAlternatives() throws Exception {
    // Arrange:
    // - Start the test SMTP server.
    // - Configure JavaMailSender to point to that server.
    // - Call the email sending service.

    // Assert:
    // - Exactly one message was received.
    // - text/plain and text/html parts exist.
    // - Plain text includes the action URL.
    // - HTML contains rendered content.
    // - Inline CID points to a part with matching Content-ID.
}
```

This is a test skeleton rather than a complete test class, since GreenMail configuration depends on version and project setup. The key habit is automatically verifying **MIME structure**, rather than only asserting the send method throws no exception.

### 12.3. Sending to Real Mailboxes

To test rendering, send emails to test mailboxes signed into target clients. You can maintain dedicated test addresses for:

- Gmail web.
- Gmail mobile.
- Classic Outlook on Windows.
- Outlook web or new app.
- Apple Mail on macOS/iOS.
- Yahoo or other clients matching your audience.

Each send should carry a unique preview ID to locate the exact email and correlate it with the template version.

## 13. Building a Repeatable Test Matrix

A good matrix records client, device, mode, and scenarios to check—never just "tested on Gmail".

Example:

| Test ID | Client | Device / mode | What to verify |
| --- | --- | --- | --- |
| C01 | Gmail | Web, desktop, light | Layout, fonts, links, images |
| C02 | Gmail | Android, light | Responsiveness, touch targets, line wrapping |
| C03 | Gmail | iOS, dark | Colors, buttons, images |
| C04 | Classic Outlook | Windows, light | Tables, padding, buttons, fonts |
| C05 | Outlook web | Browser, dark | CSS, images, links |
| C06 | New Outlook | Desktop, light | Differences from classic/web |
| C07 | Apple Mail | macOS, light | Layout, CID, fonts |
| C08 | Apple Mail | iPhone, dark | Responsiveness, dark mode, text |
| C09 | Yahoo Mail | Web/mobile if in audience | CSS and images |
| C10 | Text-only view | Client supporting text mode | Text version and URLs |

This is an example matrix; substitute the clients matching your product's actual recipient base.

### Content Cases to Include in Each Test Cycle

- Normal data.
- Long names and addresses.
- Missing optional values.
- Vietnamese diacritics, currency symbols, and special characters.
- Long multi-paragraph content.
- Images blocked.
- Dark mode.
- Narrow screens.
- Primary and secondary links.
- Attachments with long or Unicode filenames.
- Text-only email if the application has a text-only sending path.

### Recording Results Clearly

Each result should record:

| Field | Example |
| --- | --- |
| Template version | `order-confirmation/v4` |
| Test data ID | `preview-case-long-name-02` |
| Client | Gmail mobile |
| Platform/version | Android, app version recorded at test time |
| Mode | Dark |
| Result | Pass / Fail / Needs review |
| Finding | Button overflows width on small screens |
| Screenshot/reference | Internal artifact path or ID |
| Retest | Date/commit/template version fixed |

Recording client and template versions keeps results interpretable. Screenshots without metadata often make it impossible to tell which template version produced them.

## 14. Testing Workflow from Local to Production

A practical pipeline can be divided into steps:

```text
1. Build mail model and render templates
          |
          v
2. Unit test HTML + plain text
          |
          v
3. Verify MIME structure
          |
          v
4. Send to local SMTP capture
          |
          v
5. Send from staging to test mailboxes
          |
          v
6. Open on target clients/devices
          |
          v
7. Click links, download attachments, verify content
          |
          v
8. Record findings, fix, and retest
          |
          v
9. Release template
```

### Step 1 — Prepare Representative Data

Do not use only a user named `John`. Create fixtures with:

- Vietnamese names with diacritics.
- Very long names.
- Order codes and monetary amounts.
- Null/optional values.
- Text data containing `&`, `<`, `>`.
- Valid URLs with query parameters.
- Dates and times in supported time zones and locales.

### Step 2 — Render Templates

Verify the template engine substitutes variables properly, evaluates display conditions correctly, and leaves no stray expressions like `th:text` in the final output. Verify escaping for user data and that URLs come from a trusted source.

### Step 3 — Verify MIME

Ensure the message has `text/plain` and `text/html` if required. Verify charset, Content-ID, attachment filename, media type, and multipart structure.

### Step 4 — SMTP Capture

Send to Mailpit/MailHog/GreenMail or equivalent to inspect the message built by the application. Never send real sensitive data into local environments.

### Step 5 — Real Mailboxes

Send staging messages to test accounts. Use a distinct subject or preview ID to avoid mixing them up with other emails.

### Step 6 — Check Visuals and Interactions

Open the email on each client. Check primary links, support links, images, attachments, text-only view, and dark mode.

### Step 7 — Log and Retest

Capture screenshots of bugs, note client/version/template version, fix the template or model, then resend the same fixture to confirm.

## 15. Common Issues and How to Address Them

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| HTML looks good in browser, breaks in Outlook | CSS/layout unsupported by client like a browser | Use email-compatible structure and test real Outlook |
| Content overflows horizontally on mobile | Container or table has fixed width | Use fluid layout, test narrow viewports |
| Button loses background or padding | Clients style anchor tags differently | Use real links, simple styles; consider dedicated fallback if needed |
| Images fail to show | External images blocked or CID mismatches | Check image policy, MIME part, Content-ID, and alt text |
| Logo disappears in dark mode | Transparent/monochrome image lacks contrast | Prepare suitable logo variant or backdrop |
| Dark text on dark background | Client automatically adjusts colors | Test dark mode, maintain contrast |
| Font differs from design | Web font blocked or unsupported | Use font stack with fallbacks |
| Paragraph spacing differs | Margins/CSS interpreted differently | Check spacing on target clients, use simple markup |
| Text version lacks URL | Plain text built too sparsely or merely stripped HTML | Author an intentional text template |
| Vietnamese diacritics garbled | Input charset or MIME inconsistent | Verify UTF-8 from source through MIME |
| Attachment fails to open | Bad bytes, wrong media type/encoding | Inspect source bytes and MIME part |
| CID shows as link or text | HTML uses wrong scheme or part does not exist | Use `src="cid:..."` and matching `addInline` |
| Email arrives but link fails | Wrong URL, expired token, or missing permission | Check backend flow and actual URL |
| One client shows image, another does not | Differences in CID/remote image support | Check raw MIME and client policy; keep text content |
| Email shows duplicated content | MIME alternative/HTML built wrong | Check `multipart/alternative` structure |

### 15.1. CSS Layout Issues

Do not resolve every discrepancy by piling on CSS overrides. First identify which element causes the bug:

- Container width.
- Table cell padding.
- Heading/paragraph margins.
- Line-height.
- Image width/height.
- Font fallback.
- CSS selectors ignored by the client.

Prefer fixing the structure or simplifying styles as much as possible, then retest on affected clients.

### 15.2. Image Issues

Distinguish between:

- External URL images failing to load due to policy or URL.
- CID images lacking a matching part.
- Matching CID yet MIME part has wrong bytes or media type.
- Client displaying the image while CSS dimensions hide or overflow it.

Raw MIME confirms whether the part exists; real clients show how it renders.

### 15.3. Delivery Failures Are Not Rendering Bugs

If the SMTP server rejects, the recipient is invalid, or the message bounces, the issue lies in submission/delivery. Do not edit CSS to fix an SMTP error. Track responses, bounces, and provider events separately from visual test results.

## 16. Accessibility and Readability

Cross-client testing should also consider accessibility:

- Use headings in a logical hierarchy.
- Use meaningful `alt` text for informative images.
- Use `alt=""` for purely decorative images when appropriate.
- Never convey status solely through color.
- Use action-descriptive link text; avoid having multiple links all reading "Click here".
- Maintain sufficient text/background contrast.
- Ensure font size and line-height are readable on small screens.
- Structure data tables properly; do not use layout tables as content tables.
- Plain text version still conveys core content.

Example of a meaningful link:

```html
<a href="https://app.example.org/orders/123">
  View details for order ORD-2026-001
</a>
```

This link text is much clearer than:

```html
<a href="https://app.example.org/orders/123">Click here</a>
```

If an image is a logo, `alt` should describe the brand/organization name when that is useful information. If the logo merely duplicates the company name already written right beside it, choose appropriate alt text to avoid redundant reading.

## 17. Deliverability Differs from Rendering

An email can render flawlessly and still land in spam or fail to deliver. Conversely, a successfully delivered email can suffer layout bugs.

| Concern | Handling layer |
| --- | --- |
| SPF, DKIM, DMARC | Domain authentication and sending policy |
| SMTP AUTH/TLS | Connection and authentication with mail server |
| Bounces, quotas, rate limits | Delivery/provider |
| Spam filtering / reputation | Deliverability |
| HTML/CSS, dark mode, responsiveness | Client rendering |
| MIME alternative/CID/attachments | Message composition and client parsing |

Do not use "received in test inbox" to conclude all recipients will receive the mail. Test environments can differ in reputation, domain, content, and filtering policies from production.

When testing in staging, use controlled domains/subdomains and mailboxes while following provider sending policies. Separate deliverability tests from visual tests so you know which layer owns an issue.

## 18. Saving Screenshots and Managing Regressions

After each test cycle, save screenshots using a consistent convention:

```text
email-preview/
  order-confirmation/
    template-v4/
      gmail-web-light.png
      gmail-android-light.png
      outlook-classic-windows.png
      outlook-web-dark.png
      apple-mail-iphone-dark.png
```

When a template changes:

1. Render the same fixture dataset.
2. Resend to the same test mailboxes.
3. Compare new screenshots against approved baselines.
4. Document intentional changes and regressions.
5. Store results alongside the commit/template version.

Screenshot comparison can help catch layout shifts, though differences in fonts, anti-aliasing, timestamps, animations, or client versions create noise. Do not rely solely on automated pixel diffs to decide pass/fail; perform visual inspection and behavioral checks.

## 19. Pre-Release Checklist

### Content and Formatting

- [ ] Subject, From, To, and main content are accurate.
- [ ] `text/plain` version exists if the email supports multiple formats.
- [ ] Text version includes links and key information.
- [ ] HTML contains no unrendered template variables or placeholders.
- [ ] Dynamic data is escaped according to context.
- [ ] Vietnamese diacritics, currency, dates/times, and locale display properly.

### Layout and Images

- [ ] No horizontal overflow on mobile.
- [ ] Headings, paragraphs, and tables are readable.
- [ ] Buttons and links can be tapped/clicked.
- [ ] Images have sensible dimensions and alt text.
- [ ] Email remains understandable when images are blocked.
- [ ] Dark mode does not make text or logos disappear.
- [ ] Font fallbacks work.

### MIME and Attachments

- [ ] MIME alternative has proper text/HTML parts.
- [ ] Charset matches content bytes.
- [ ] CIDs in HTML match Content-IDs.
- [ ] Attachments have the right filenames and media types.
- [ ] Files open cleanly and are not corrupted.
- [ ] No duplicate or unnecessary malformed MIME parts exist.

### Clients and Interactions

- [ ] Opened on Tier 1 clients.
- [ ] Tested on desktop and mobile according to audience.
- [ ] Tested in light and dark modes if supported.
- [ ] Primary and secondary links work.
- [ ] Recipients have access permissions after opening links.
- [ ] Screenshots and results are saved with the template version.

### Delivery

- [ ] Staging SMTP submission succeeded.
- [ ] No bounce or invalid-recipient errors in tests.
- [ ] Sending domain and authentication setup verified per environment.
- [ ] Logs record notification/template version without leaking sensitive data.

This checklist is for release workflows; it does not replace specialized testing for emails with legal, security, or special business requirements.

## 20. A Practical Team Workflow

To keep testing repeatable, teams can standardize inputs and outputs:

**Inputs:**

- Template key and version.
- Data schema version.
- Representative fixture.
- Locale.
- Tier 1/Tier 2 client list.
- MIME configuration (text, HTML, inline, attachments).

**Outputs:**

- Rendered HTML and plain text.
- Raw MIME of the staging message.
- Screenshots by client/device.
- Link/attachment test results.
- Findings and retest status.
- Approved version/commit.

A change affecting only the subject or plain text may not require re-capturing the entire visual matrix. Changes to layout, CSS, inline images, MIME structure, or fonts require re-running affected clients. When changing a shared template, assess the impact across every email sharing that component.

## 21. Practice Scenarios

### Scenario A: Email Looks Good in Gmail Web but Breaks in Classic Outlook

**How to handle:** pinpoint the broken region (width, table, padding, font, or button), check raw MIME to verify the message has no structural errors, update HTML/CSS to compatible features, and retest classic Outlook along with another client to avoid regressions.

### Scenario B: Banner Image Does Not Show on Mobile

**How to handle:** determine whether the image is a CID or external URL. For URLs, check image-loading policies and HTTPS URL; for CIDs, match `src` and `Content-ID`. Check image dimensions, `width`, `height`, `max-width`, and alt text.

### Scenario C: Email Renders Well in Light Mode, Text Vanishes in Dark Mode

**How to handle:** check whether the client auto-inverts colors or applies media queries; adjust background/text colors and inspect buttons, logos, and borders. Do not assume dark-mode CSS is supported by every client.

### Scenario D: Recipient Enables Text-Only Reading Mode

**How to handle:** verify `text/plain` has full information and URLs. Never rely on HTML to deliver verification codes or critical actions.

### Scenario E: SMTP Test Succeeds, Customer Reports Missing Attachment

**How to handle:** inspect raw MIME to verify the part exists with the right `Content-Disposition`, filename, media type, and bytes. Then test on the target client. If the part is missing in the raw message, the bug is in message construction; if present yet the client hides it, investigate client handling.

### Scenario F: New Template Causes Vietnamese Translation to Overflow

**How to handle:** use fixtures with long strings, allow text wrapping, avoid fixed heights, and test on mobile. Do not test only with short English strings.

### Scenario G: Email Delivered, Button Leads to Unauthorized Page

**How to handle:** verify the URL is generated with the right domain/path, right recipient, valid token or session, and backend authorization checks. This is a business/link-flow bug, not a rendering bug.

## 22. Conclusion

Testing emails across different mail clients confirms that content generated by Spring remains usable when interpreted in recipients' real environments. HTML templates, text versions, MIME structure, SMTP submission, delivery, and client rendering must each be checked separately. A browser preview or a single successful send cannot replace all those steps.

With Spring Framework Mail, generate appropriate `text/plain` and `text/html` using `MimeMessageHelper`, verify CIDs/attachments in raw MIME, and send staging messages to mailboxes on clients used by your audience. Use simple HTML/CSS, font fallbacks, alt text, clear HTTPS links, and content that does not depend on images. Your test matrix should include desktop/mobile, light/dark modes, Vietnamese data, and image-blocked scenarios. Save screenshots alongside template versions and retest affected clients after every change. That way, your team can catch regressions early and deliver more consistent emails to users.
