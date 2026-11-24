# Mail Clients Without Inline Support and Fallback Strategies

A Spring Boot application sends an HTML email containing a company logo, an order status illustration, and a "View details" link. The development team uses **inline resources** with Content-IDs (CIDs), so the HTML references images via `src="cid:company-logo"`. On some email clients, the logo displays properly; on others, the image is hidden, appears as a separate attachment, or does not render as intended.

This is an important characteristic of email: **the sending application can construct a valid MIME message, yet it cannot force every mail client to display content identically**. Each client has its own image-loading policy, MIME handling, HTML/CSS engine, and user interface. Inline resources package assets into the email and reference them from HTML; they do not guarantee the image will always appear in place on every device.

In **Spring Framework Mail**, `MimeMessageHelper.addInline(...)` is used to add inline resources. For content to remain useful when inline images fail to display, design **graceful fallbacks**: text must convey the message on its own, images need `alt` text, CTAs must be real links, a `text/plain` version should be included, and images should only be turned into attachments or remote resources when doing so adds value for the recipient.

## 1. How do inline resources work?

An inline image is typically placed inside a MIME message as a body part with a `Content-ID`. HTML references that part using a URL with the `cid:` scheme.

HTML example:

```html
<p>Welcome to our service.</p>
<img src="cid:company-logo" alt="Company logo">
```

The corresponding MIME section can be conceptualized as follows:

```text
Content-Type: multipart/related

--related-boundary
Content-Type: text/html; charset=UTF-8

<p>Welcome to our service.</p>
<img src="cid:company-logo" alt="Company logo">

--related-boundary
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <company-logo>
Content-Disposition: inline

[image bytes encoded in base64]
--related-boundary--
```

This is an illustrative diagram; Jakarta Mail generates the actual boundaries and headers. When an email client processes MIME, it looks up the body part with the matching Content-ID and can display the image bytes at the `cid:company-logo` position in HTML.

Components:

| Component | Role |
|---|---|
| `src="cid:company-logo"` | References the resource from HTML. |
| `Content-ID: <company-logo>` | Identifies the MIME part so the client can locate the resource. |
| `Content-Type: image/png` | Describes the byte format of the image. |
| `Content-Transfer-Encoding: base64` | Represents binary bytes in the MIME message. |
| `Content-Disposition: inline` | Hints that the content is intended for use within the message body. |
| `alt="Company logo"` | Alternative text when the image does not display or for assistive technology. |

**CID is a mechanism for linking MIME parts within the same email**, not a public URL on the Internet. Recipients do not need to download the logo from a website to view an inline image; the image data is already inside the message.

## 2. Why might a mail client fail to display inline images?

An email client may receive a valid MIME message yet present it differently. Common causes include:

| Symptom | Possible cause |
|---|---|
| Image does not appear | Client cannot find a matching CID, MIME structure is unexpected, part is filtered, or processing fails. |
| Broken image icon appears | Resource is missing, Content-ID mismatches, or image data cannot be read/decoded. |
| Image appears at the bottom as an attachment | Client chooses to present inline parts as downloadable attachments. |
| Remote image is hidden | Client blocks external image loading for privacy or security policy reasons. |
| Image is stretched/cropped | CSS, sizing attributes, or layout are not supported identically. |
| Only fallback text appears | Client does not load or render images; `alt` text may be shown. |
| HTML does not render properly | Client sanitizes markup, restricts CSS, or falls back to the text/plain version. |

These issues can stem from the client, gateway, image proxy, security filters, or the MIME structure built by the application. Therefore, when debugging, distinguish **whether the message has the right inline part** from **whether the client renders that part properly**.

### 2.1. Inline does not mean the image is always displayed

A CID image is already inside the email, so it does not depend on an outbound HTTP request like a remote image. Still, a client may:

- Not support or not properly handle a specific MIME structure.
- Hide images based on user preferences.
- Display images as attachments instead of embedding them in HTML.
- Sanitize HTML or strip unrecognized references.

Thus, CID is generally a good way to attach logos or small assets without fetching from external domains, but it is **not an absolute guarantee of display**.

### 2.2. Remote images can also be blocked

HTML can reference:

```html
<img src="https://static.example.com/mail/logo.png"
     alt="Company logo">
```

Remote images depend on URL reachability and client policy. Clients may prompt the user before loading, block them completely, or fetch them via a proxy. Some systems also cache/proxy images, preventing the application from observing original access behavior.

Therefore, replacing CID with remote images is **not a more reliable fallback**. For mandatory information, express it in text; images should only enhance the experience.

## 3. Creating inline resources with Spring MimeMessageHelper

### 3.1. Basic example

```java
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendWelcomeMail(JavaMailSender mailSender)
        throws Exception {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            "UTF-8");

    helper.setFrom("notifications@example.com");
    helper.setTo("customer@example.net");
    helper.setSubject("Welcome");

    String html = """
            <html>
              <body>
                <p>Welcome to our service.</p>
                <img src="cid:company-logo" alt="Company logo"
                     width="160">
              </body>
            </html>
            """;

    // Set the body before adding inline resources.
    helper.setText("Welcome to our service.", html);
    helper.addInline(
            "company-logo",
            new ClassPathResource("mail/images/company-logo.png"),
            "image/png");

    mailSender.send(message);
}
```

In this example:

- `MULTIPART_MODE_RELATED` suits a message whose HTML body references inline resources.
- `setText(plain, html)` creates two representations of the content.
- `src="cid:company-logo"` must match the ID passed to `addInline("company-logo", ...)`.
- `ClassPathResource` is used for a logo packaged with the application.
- `image/png` describes the actual format of the source image.

**Call `setText(...)` before `addInline(...)`.** Spring documentation recommends this order to ensure the message structure is built properly for inline resources.

### 3.2. Using multipart mode when attachments are also present

If the email has text/plain, HTML, an inline logo, and also a downloadable PDF, you can use:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
```

Then:

```java
helper.setText(plainText, html);
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/company-logo.png"),
        "image/png");
helper.addAttachment(
        "invoice-DH1024.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf");
```

`MIXED_RELATED` mode represents related content (HTML and inline resources) alongside regular attachments. The nested MIME structure is created by the helper/provider; do not assume parts sit at fixed indices in tests.

### 3.3. Content-ID must match exactly

If the HTML uses:

```html
<img src="cid:brand-logo" alt="Logo">
```

then the helper must add:

```java
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
```

If the HTML references `cid:brand-logo` while the code adds ID `company-logo`, the client cannot map the resource properly.

Do not add angle brackets to the ID when passing it to the helper if the API expects a logical string content ID. Spring/Jakarta Mail handles formatting the `Content-ID` header. In raw MIME, IDs typically appear inside angle brackets, such as `<brand-logo>`.

### 3.4. IDs should be unique within a message

When an email has multiple inline resources, each CID must be distinct:

```java
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

helper.addInline(
        "status-icon",
        new ClassPathResource("mail/images/status.png"),
        "image/png");
```

HTML:

```html
<img src="cid:company-logo" alt="Company logo">
<img src="cid:status-icon" alt="Confirmed status">
```

Never use the same Content-ID for two different resources in one message. To avoid collisions when templates are reused or multiple modules contribute resources, namespace IDs by message/template.

## 4. Designing content that remains usable when images do not display

The first fallback strategy is not adding another image-loading mechanism. It is **making sure the email still conveys its full meaning when all images are removed**.

### 4.1. Use meaningful alt text

Avoid:

```html
<img src="cid:status-icon" alt="">
```

if the image carries important information.

Prefer:

```html
<img src="cid:status-icon"
     alt="Order has been confirmed"
     width="24" height="24">
```

If a client does not show images, `alt` can help recipients understand the content. However, not all clients display alt text the same way; some only show a broken-image icon or omit the fallback text.

Therefore, **never keep important information only inside alt text**. Include a standalone sentence:

```html
<p><strong>Status: Order has been confirmed.</strong></p>
<img src="cid:status-icon"
     alt="Confirmation icon"
     width="24" height="24">
```

If the image disappears, the status sentence remains.

### 4.2. Logos need a text brand name

If the logo does not display, recipients still need to know which brand sent the email. You can write:

```html
<p style="font-size:20px; font-weight:bold;">
  Example Company
</p>
<img src="cid:company-logo" alt="Example Company Logo"
     width="160">
```

Never place the entire brand name, heading, or contact information inside a single image.

### 4.3. CTAs must be real links

Do not use a button image as the only way to open a page:

```html
<!-- Do not use an image alone as a CTA -->
<img src="cid:confirm-button.png" alt="">
```

Replace it with an anchor containing text:

```html
<p>
  <a href="https://accounts.example.com/verify">
    Verify account
  </a>
</p>
```

If there is a decorative button graphic, treat it as supplementary. Text links must remain usable when images are hidden or CSS is stripped.

## 5. Fallback strategies by content type

Not every inline resource needs the same fallback. Identify the **purpose of each image**:

| Resource type | When inline fails to display | Appropriate strategy |
|---|---|---|
| Brand logo | No visual brand mark | Show brand name as text and meaningful alt text. |
| Decorative icon | Decorative detail is lost | Omit the image; keep text content and status. |
| Status icon | Recipient might miss the status | State the status in a sentence, not solely via color/icon. |
| Critical chart or diagram | Visual data is lost | Summarize figures in text/tables; attach PDF or link to details when appropriate. |
| Product photo | Recipient cannot see the product | Include product name, description, and a link to view the item. |
| Image-based CTA button | Cannot act on it | Use text anchor/HTML button-style link with a real URL. |
| Signature or stamp | Verification visual is lost | Provide verification details as text and a validation link; do not rely solely on images. |

**Fallbacks should preserve business meaning**, not necessarily the exact visual layout. An icon can vanish harmlessly if text already states the status; an important chart needs a text summary or alternative document.

## 6. The text/plain part is an essential fallback layer

When an email has HTML, consider sending a `text/plain` part alongside it via `multipart/alternative`. The text part contains no inline images and does not depend on HTML/CSS.

Example:

```text
EXAMPLE COMPANY

Order DH1024 has been confirmed.

Status: CONFIRMED
Total: 1,250,000 VND

View details:
https://accounts.example.com/orders/DH1024

If you did not make this request, please contact support.
```

The text version must retain core information:

- Who sent the notification.
- What event/status occurred.
- Required reference codes.
- Monetary amounts/dates if applicable.
- Action links or instructions.
- How to contact support if there is a problem.

Never send just `"Your email client does not support HTML"`. The text version is a complete representation of the message, not an error page.

### 6.1. Creating text and HTML with Spring

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8");

helper.setFrom("notifications@example.com");
helper.setTo(recipient);
helper.setSubject("Order DH1024 has been confirmed");

String plain = """
        EXAMPLE COMPANY

        Order DH1024 has been confirmed.
        Status: CONFIRMED
        Total: 1,250,000 VND

        View details:
        https://accounts.example.com/orders/DH1024
        """;

String html = """
        <html>
          <body>
            <p><strong>EXAMPLE COMPANY</strong></p>
            <p>Order <strong>DH1024</strong> has been confirmed.</p>
            <p>Status: CONFIRMED</p>
            <p>Total: 1,250,000 VND</p>
            <p>
              <a href="https://accounts.example.com/orders/DH1024">
                View order details
              </a>
            </p>
            <img src="cid:company-logo"
                 alt="Example Company Logo" width="160">
          </body>
        </html>
        """;

helper.setText(plain, html);
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/company-logo.png"),
        "image/png");

mailSender.send(message);
```

In this example, `MULTIPART_MODE_RELATED` is used for HTML and inline resources. The helper builds the alternative and related sections per the multipart mode. If regular attachments are also included, use `MULTIPART_MODE_MIXED_RELATED` to combine them.

## 7. Should inline images be turned into attachments?

You can, but understand that **regular attachments and inline resources serve different purposes**.

### 7.1. Inline resource

```java
helper.addInline(
        "chart-image",
        new FileSystemResource(chartPath),
        "image/png");
```

HTML:

```html
<img src="cid:chart-image" alt="Monthly revenue chart">
```

The goal is to display the image directly inside the HTML portion of the message.

### 7.2. Regular attachment

```java
helper.addAttachment(
        "revenue-report.png",
        new FileSystemResource(chartPath),
        "image/png");
```

The goal is to provide a file for the recipient to open or download. Clients may show the file in the attachment area, often with a paperclip icon or file list.

### 7.3. When to use both?

For an important chart, a product might:

- Include the image inline for quick viewing.
- Provide a downloadable attachment for archiving.
- Include a text summary of the numbers.

However, sending the same image twice makes the email larger and shows a redundant attachment in clients. Do this only when recipients genuinely need to download the file. If the content contains rich data, a PDF or an access-controlled report page may be more suitable.

**Do not automatically convert every inline image into an attachment assuming clients lack CID support.** Many clients do handle inline images; converting them to attachments alters the user experience and does not guarantee recipients will open the file.

## 8. Using remote images as an alternative?

Remote images can work for public logos or decorative graphics, but should not be treated as a foolproof fallback.

Example:

```html
<img src="https://static.example.com/email/logo.png"
     alt="Example Company Logo"
     width="160">
```

### 8.1. Advantages

- Does not increase MIME message size with image bytes.
- Allows updating the image on the server without modifying email templates.
- Many clients support HTTPS images when the user allows loading them.
- Can use a CDN to serve public assets.

### 8.2. Limitations and risks

- Clients may block external images or prompt the recipient to enable loading.
- The URL must be reachable from the recipient's network without internal cookies or sessions.
- Remote assets may be proxied or cached, making load timing uncontrollable.
- Per-recipient URLs can create tracking and impact privacy.
- Assets can change after the email was sent, causing older emails to render differently.
- If the URL expires or the domain goes down, the image vanishes.

### 8.3. When to use remote images?

Consider them for public logos or low-priority decorative images if:

- The URL uses HTTPS.
- The domain is managed by your organization.
- No cookies or internal permissions are required.
- Content has alt text and fallback text information.
- Privacy policies allow loading external images.
- There is a clear presentation when clients block images.

Never put OTPs, tokens, private data, or invoice details in image URL query strings. Never use remote images as the sole container of critical content.

## 9. Why not use data URI/base64 in src instead of CID?

A common idea is embedding images inline directly:

```html
<img src="data:image/png;base64,iVBORw0KGgo...">
```

This is a **data URI**, not a CID. Support across email clients is inconsistent; many clients strip or refuse to render this source format. It also bloats HTML, increases size, and complicates content management.

For HTML emails, prefer:

1. CID inline resources for small images that must travel with the message.
2. HTTPS remote images for public assets when client blocking is acceptable.
3. Regular attachments when recipients need to download files.
4. Text/tables/links as alternatives for important information.

Do not manually base64-encode images into HTML expecting broader compatibility than CID.

## 10. Avoid relying on CSS background images

Some email templates use:

```html
<td style="background-image: url('https://static.example.com/banner.png');">
  <h1>Special Offer</h1>
</td>
```

CSS background images may fail to render in some clients or be stripped in reader modes. If the banner contains critical information like an expiration date or discount rate, recipients lose that information when images are blocked.

Better design:

- Make headings and offer details real text.
- Treat background images purely as decoration.
- Provide fallback background colors and layout.
- Never place unique business conditions or values inside images.
- Test on target clients.

For emails, table layouts and simple inline CSS are usually more compatible than modern web layouts using complex selectors. Even so, real-client testing remains essential.

## 11. Avoid sniffing email clients to send different content versions

An application might try detecting Gmail, Outlook, or Apple Mail from user agents or headers to pick an image-embedding method. For email, this is rarely reliable:

- Emails can be forwarded or viewed across multiple clients.
- Gateways/proxies may alter requests and metadata.
- One person may use multiple devices/clients.
- The sending app typically receives no reliable signal of how each recipient renders mail.
- Branching per client creates multiple templates and error cases to maintain.

**Designing for graceful degradation** is usually far more resilient: complete text content, supporting images, real links, and valid MIME. If a product has specific requirements for a particular email platform, test and document support for that client rather than guessing clients from unreliable data.

## 12. Verify the MIME message before concluding the client lacks inline support

Before switching solutions, confirm the message was constructed properly.

### 12.1. Check Content-ID and MIME type

Compare:

```html
<img src="cid:company-logo" alt="Company logo">
```

with:

```java
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/company-logo.png"),
        "image/png");
```

Verify:

- The CID in HTML matches the ID passed to the helper.
- The resource exists and is readable.
- The MIME type matches the actual bytes.
- The image uses a format widely supported by target email clients, such as PNG/JPEG.
- No two resources share the same CID within one message.
- The helper was created in the appropriate multipart mode.
- `setText` was called before `addInline`.

### 12.2. Inspect raw MIME in a test environment

An email with inline resources typically has a related multipart structure. You can inspect the created message with Jakarta Mail:

```java
Object content = message.getContent();
if (!(content instanceof Multipart multipart)) {
    throw new IllegalStateException("Expected multipart message");
}

System.out.println("Part count: " + multipart.getCount());
```

With mixed/related/alternative structures, multiparts can nest several levels deep. Tests should traverse `BodyPart` entries recursively and verify:

- A `text/plain` part exists.
- A `text/html` part exists.
- An inline part exists with the matching `Content-ID`.
- `Content-Type` and `Content-Disposition` are appropriate.
- Image bytes are read completely.

Do not assume the inline image is always at part index 1 or that attachments are always at the last index.

### 12.3. Using an SMTP catcher

An SMTP catcher such as GreenMail, Mailpit, or MailHog can help:

- Receive messages without sending externally.
- Inspect headers and MIME structure.
- Download image parts to verify bytes.
- Confirm Content-ID and HTML references match.
- Inspect text/plain and text/html bodies.

An SMTP catcher **does not accurately simulate every email client**. If MIME is valid yet Outlook/Gmail/Apple Mail still render differently, test directly on those clients or use a dedicated email preview service.

### 12.4. Verify image data independently

Before investigating clients, confirm the image file:

- Exists and is readable.
- Is not an empty file.
- Has the right format.
- Has reasonable pixel dimensions.
- Is not excessively large in file size.
- Was not corrupted during generation/copying.

If the image cannot be decoded, changing MIME modes or clients cannot fix a broken image source.

## 13. Complete example: HTML with inline logo and text fallback

The following example uses Spring Mail with HTML content, plain text, and a CID logo. Essential information remains visible even if the logo does not appear.

```java
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationMailer {

    private final JavaMailSender mailSender;

    public OrderNotificationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmed(String recipient, String orderCode)
            throws Exception {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_RELATED,
                "UTF-8");

        helper.setFrom("orders@example.com");
        helper.setTo(recipient);
        helper.setSubject("Order " + orderCode + " has been confirmed");

        String plain = """
                EXAMPLE COMPANY

                Order %s has been confirmed.

                View order details:
                https://accounts.example.com/orders/%s

                If you did not make this request, please contact support.
                """.formatted(orderCode, orderCode);

        String html = """
                <html>
                  <body>
                    <p><strong>EXAMPLE COMPANY</strong></p>
                    <img src="cid:company-logo"
                         alt="Example Company Logo"
                         width="160">
                    <h1>Order Confirmed</h1>
                    <p>Order code: <strong>%s</strong></p>
                    <p>
                      <a href="https://accounts.example.com/orders/%s">
                        View order details
                      </a>
                    </p>
                    <p>If you did not make this request,
                       please contact support.</p>
                  </body>
                </html>
                """.formatted(orderCode, orderCode);

        helper.setText(plain, html);
        helper.addInline(
                "company-logo",
                new ClassPathResource("mail/images/company-logo.png"),
                "image/png");

        mailSender.send(message);
    }
}
```

This example illustrates call order and MIME structure. In a real application:

- `orderCode` must be validated for characters and length before use in URLs/HTML.
- URLs should be constructed via a trusted URL builder from a configured base URL, never concatenated from untrusted input.
- Dynamic data in HTML should be rendered through a template engine with escaping rather than direct string concatenation.
- The logo must be an application-controlled resource.
- Recipients and sending permissions must be authorized per business rules.

### 13.1. If a PDF attachment is also included

Change the multipart mode:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
```

After `setText` and `addInline`:

```java
helper.addAttachment(
        "invoice-" + orderCode + ".pdf",
        new FileSystemResource(invoicePath),
        "application/pdf");
```

The inline logo and PDF attachment serve different purposes: the logo aids recognition inside the body, while the PDF provides a downloadable document. If the logo fails to render, the text and links remain useful; if the PDF is mandatory and unreadable, handle the attachment error per business policy.

## 14. Testing graceful degradation when inline fails to display

Do not test only "does the image appear in one client". Also test what happens when images are stripped.

### 14.1. Testing the HTML version without images

A simple test is to render the template, strip `img` tags from the test HTML, and verify the remaining content is still complete:

```java
String htmlWithoutImages = Jsoup.parse(html)
        .select("img")
        .remove()
        .toString();

assertThat(htmlWithoutImages)
        .contains("Order Confirmed")
        .contains("DH1024")
        .contains("View order details");
```

This example requires the jsoup dependency in tests. It checks content after image removal and does not fully simulate how every client handles MIME or alt text.

### 14.2. Testing plain text

```java
assertThat(plainText)
        .contains("Order DH1024 has been confirmed")
        .contains("https://accounts.example.com/orders/DH1024");
```

The text version needs equivalent information and links. If the HTML version uses an image button while plain text omits the URL, users on text-only clients cannot complete the action.

### 14.3. Testing CID mapping

Verify:

```java
assertThat(html).contains("cid:company-logo");
assertThat(inlineContentIds).contains("company-logo");
```

`inlineContentIds` is the set of CIDs extracted from MIME parts in a test helper; traverse nested multiparts to collect all of them. Do not check only the HTML string while skipping whether the resource was actually added to the message.

### 14.4. Testing on real clients

For critical emails, test at minimum on the clients supported by your product. Check:

- Does the CID logo render?
- Does hiding images cause any loss of information?
- Is alt text helpful?
- Are buttons/anchors still usable when CSS is stripped?
- Does the plain-text version contain full content?
- Is the inline image unexpectedly presented as an attachment?
- Do dark mode and mobile make text hard to read?

Valid MIME is a necessary condition; client testing confirms the real user experience.

## 15. Choosing fallbacks by image importance

You can group images as follows:

### 15.1. Decorative images

For example, dividers, colored backgrounds, decorative icons. The best strategy is usually **no complex fallback needed**. If the image disappears, the content stays intact. You can omit the image entirely on unsupported clients.

### 15.2. Brand-identification images

For example, company logos. Use CID if you want to avoid external image requests; pair with the brand name in text and meaningful alt text. Remote HTTPS is another option when the organization wants centralized asset management and accepts that clients may block loading.

### 15.3. Data-conveying images

For example, charts, workflow diagrams, or evidence screenshots. **Do not rely solely on the image**:

- Summarize findings in text.
- Include an HTML/text data table if suitable.
- Attach a PDF/CSV when recipients need to save or analyze data.
- Provide a link to an access-controlled report page.

### 15.4. Action-related images

For example, "Pay", "Confirm", or "Reset password" buttons. Use real anchors with text labels and HTTPS URLs; images should only be decorative. Never use image maps or make an image the sole clickable region.

## 16. Privacy and security of image strategies

### 16.1. CID does not require fetching images from external domains

Because image bytes are attached inside the email, CID generally avoids an HTTP request to an image server when the client renders. This can reduce certain forms of remote-image tracking. However, it **does not make the entire email strictly private**: mail providers, gateways, and recipients can still access the message.

### 16.2. Remote images can expose metadata

An image-loading request can let a server or proxy observe timestamps, URLs, and certain metadata depending on the client. Never use remote images as tracking pixels without evaluating privacy requirements, consent, and applicable policies.

### 16.3. Never store secrets in image URLs or CIDs

CIDs are not a place to store authentication tokens. Remote image URLs should also never carry:

- OTPs or password-reset tokens.
- Unnecessary personal data.
- Guessable invoice numbers or secret codes.
- Identifiers that can be used to access documents.

If private documents must be shown, use protected access mechanisms and enforce server-side authorization checks.

### 16.4. Use only suitable image formats

For emails, PNG and JPEG are usually the most widely compatible choices. Avoid relying on inline SVG or poorly supported image formats unless tested on target clients. Images must be checked for size and origin; never embed untrusted files without a verification workflow.

## 17. Common errors when using inline resources

### 17.1. CID in HTML mismatches addInline

HTML uses `cid:logo` while Java adds `company-logo`. Use the exact same ID.

### 17.2. Calling addInline before setText

This order can prevent the helper from building the multipart structure as expected. Call `setText` first, then `addInline`.

### 17.3. Using an unsuitable multipart mode

Inline resources require a related structure. If the email also has regular attachments, choose `MULTIPART_MODE_MIXED_RELATED`.

### 17.4. Assuming Content-Disposition inline forces clients to render inside HTML

`inline` is MIME metadata; final presentation still depends on the client. CID mapping and MIME structure must also be valid.

### 17.5. Image-only email with no text

When clients block images, recipients see no content. Add text copy, alt attributes, and a plain-text version.

### 17.6. Treating remote images as a guaranteed fallback

Remote images can also be blocked. Use text as the core fallback.

### 17.7. Using data URIs to avoid CID

Data URIs lack consistent support across email clients. Prefer CID, controlled remote HTTPS, or attachments depending on purpose.

### 17.8. Converting every inline image to an attachment

Attachments can clutter the UI, add bloat, and offer no guarantee recipients will open them. Use them only when files have download value.

### 17.9. Putting mandatory info in CSS backgrounds

Background images may fail to render. Put important content into real text.

### 17.10. Using an image as the sole CTA

Images can disappear or fail to behave as clickable links as expected. Use meaningful anchor text and real URLs.

### 17.11. Thinking an SMTP catcher proves proper rendering

An SMTP catcher confirms MIME was delivered to a test server, not how every email client renders it. Test on target clients.

### 17.12. Reusing one CID for multiple resources

CIDs must be unique within a message to avoid mis-mapping.

## 18. Practice exercises

### Exercise 1 — Checking CID

HTML has `src="cid:brand-logo"` while code calls `addInline("logo", ...)`. Explain why the image does not display and fix the ID.

### Exercise 2 — MIME multipart

An email has plain text, HTML, an inline logo, and a PDF attachment. Choose the right multipart mode and explain the difference between `MULTIPART_MODE_RELATED` and `MULTIPART_MODE_MIXED_RELATED`.

### Exercise 3 — Fallback when images are hidden

Design an order confirmation email with a logo, status icon, and "View details" button. Write HTML so that if all images are stripped, the recipient still knows the status and can open the order page.

### Exercise 4 — Remote image or CID?

A public logo needs frequent updates. Compare CID and HTTPS remote images in terms of message size, updatability, privacy, and risk of being blocked. Recommend a choice based on product requirements.

### Exercise 5 — Critical chart

A report email features a revenue chart as its main content. Propose fallbacks using text/data tables, a PDF attachment, or a report link; explain when to use each option.

### Exercise 6 — Text-only

Write a `text/plain` version for an email that has an HTML button and an inline logo. Ensure the recipient still has all required URLs and details to take action.

### Exercise 7 — Testing

Design a test checking that MIME has CIDs matching HTML, images have the right MIME type, and plain text is complete. Then describe how to test on real email clients.

### Exercise 8 — Privacy

A team wants to use a remote tracking pixel to know who opened an email. Analyze reliability limits of the signal, metadata that may be collected, and privacy considerations.

## 19. Takeaways and references

When **mail clients do not support inline or fail to display inline resources properly**, you should:

1. Use `MimeMessageHelper.addInline` with CIDs matching exactly between HTML and the MIME part.
2. Choose the right multipart mode; when regular attachments are present, consider `MULTIPART_MODE_MIXED_RELATED`.
3. Call `setText` before `addInline` so the helper builds the MIME structure properly.
4. Check image bytes, MIME type, Content-ID, and multipart structure before blaming the client.
5. Keep critical information in real text; never place statuses, amounts, or CTAs solely inside images.
6. Provide meaningful alt text and a complete `text/plain` version.
7. Use attachments when recipients need to download documents; use remote HTTPS when client image-blocking is acceptable; do not treat data URIs as a universal fallback.
8. Test on target email clients; an SMTP catcher only checks MIME, not final rendering.
9. Consider privacy when loading remote images and never put secrets in image URLs.

Recommended technical references:

- **Spring Framework API — `MimeMessageHelper`:** `addInline`, multipart modes, `setText`, and attaching resources.
- **Spring Framework Reference — Email:** creating MIME messages, inline resources, and attachments.
- **Jakarta Mail API — `MimeMessage`, `MimeMultipart`, `MimeBodyPart`:** multipart structure and body-part handling.
- **RFC 2387 — The MIME Multipart/Related Content-type:** relationship between the primary content part and related resources.
- **RFC 2392 — Content-ID and Message-ID Uniform Resource Locators:** referencing resources via `cid:` in MIME content.
- **RFC 2045–2049 — MIME:** content types, transfer encoding, and multimedia email structure.

**Inline resources are a way of packaging assets inside an email, not a guarantee of client presentation.** A reliable email must still convey complete information when images are hidden: use real text, real links, meaningful alt text, and a plain-text version. Designed by that principle, emails stay useful even when clients handle CIDs, CSS, or remote images differently.
