# Alternative Content Must Express the Same Information

An HTML email can look polished with colors, tables, buttons, and a logo. However, not all mail reading applications render HTML the same way; recipients may use text-only mode, devices or software that restrict HTML, or mail client policies that choose another format. Therefore, transactional emails typically provide **two representations of the same content**: `text/plain` and `text/html`.

In Spring Framework Mail, `MimeMessageHelper.setText(plainText, htmlText)` helps create two alternative content parts in a multipart message. The key to this design is that **the plain text version and the HTML version must convey the same business information**. The two versions do not need identical layouts or wording, but one version must never omit an order code, amount, deadline, next step, or action link that is present in the other.

For example, if the HTML version has a "View invoice" button pointing to a URL, then the plain text version must also provide the URL or an equivalent way for the recipient to open the invoice. If payment status, due date, or amount appears only in HTML, a recipient reading the plain text version will receive an incomplete notification.

This lesson explains the meaning of `multipart/alternative`, how to design both versions from the same data source, how to send them with `MimeMessageHelper` and `JavaMailSender`, what information is commonly lost when converting from HTML to plain text, and how to test information equivalence.

## 1. Why Does an Email Need Both Plain Text and HTML?

An email may be displayed in many environments:

- Mail applications with full HTML support.
- Applications or devices that display only text.
- Mail clients that disable or restrict images, CSS, and HTML content.
- Archiving, forwarding, or email analysis systems that need to read the text part.
- Users actively choosing a simplified display mode.

If only HTML is sent, environments that do not process HTML adequately may fail to present the content as expected. If only plain text is sent, the application misses out on richer layout and formatting.

A multipart/alternative email allows a message to carry two representations:

~~~text
Email message
└── multipart/alternative
    ├── text/plain
    └── text/html
~~~

These two parts are **alternative choices for the same logical content**. The mail reader picks the representation that fits its capabilities or preferences. By MIME convention, the richer representation is normally placed after the simpler one; in this example, plain text first, HTML second.

### Not Two Separate Emails

When calling:

~~~java
helper.setText(plainText, htmlText);
~~~

the application does not send two messages to the recipient. It creates **one message** with two alternative body parts. Subject, From, To, Cc, Bcc, and other message headers remain shared across that message.

This differs from calling `mailSender.send(...)` twice, once per message:

| Sending approach | Result |
| --- | --- |
| One message with `multipart/alternative` | One email with two representations of the same content |
| One message with only `text/plain` | One email with only text content |
| One message with only `text/html` | One email with only HTML content |
| Two sends, each with one message | Two independent emails, potentially received as two separate messages |

## 2. What Does "Same Information" Mean?

Information equivalence does not require both versions to have the same line count, identical wording, or the same layout. It requires that **every important fact and action the recipient needs is present in both versions**.

Suppose an order confirmation email contains:

- Recipient: Nguyen An.
- Order code: `ORD-2048`.
- Status: Confirmed.
- Total amount: `1,250,000 VND`.
- Estimated delivery date: 18/11/2026.
- Action: view order details via a link.
- Support channel if there is an issue.

The HTML version can display them in a table and button. The plain text version can present them as lines:

~~~text
Hello Nguyen An,

Order ORD-2048 has been confirmed.

Status: Confirmed
Total: 1,250,000 VND
Estimated delivery: 18/11/2026

View order details:
https://app.example.org/orders/ORD-2048

If you need support, please reply to this email or contact support@example.org.
~~~

The HTML version can have a different layout:

~~~html
<h2>Order Confirmed</h2>
<p>Hello Nguyen An,</p>
<table>
  <tr><th>Order code</th><td>ORD-2048</td></tr>
  <tr><th>Status</th><td>Confirmed</td></tr>
  <tr><th>Total</th><td>1,250,000 VND</td></tr>
  <tr><th>Estimated delivery</th><td>18/11/2026</td></tr>
</table>
<a href="https://app.example.org/orders/ORD-2048">
  View order details
</a>
<p>Support: support@example.org</p>
~~~

The layout differs, but the key facts and corresponding actions are all present.

### Equivalence Does Not Mean HTML Must Be Stripped Into Identical Text

You should not generate the plain version by deleting all HTML tags from an HTML string. That approach can lose:

- The actual target address of a link.
- Relationships between headings and body content.
- Column names in tables.
- Information conveyed through images or icons.
- Instructional steps grouped in order.

Instead, build both versions from **the same dataset and the same business rules**.

## 3. Identify Required Information Before Building Both Versions

Before writing HTML or plain text, identify what the recipient needs to know and what they must do after reading the email.

A content table can help clarify requirements:

| Information group | Example | Needed in both versions? |
| --- | --- | --- |
| Notification identity | Order confirmation | Yes |
| Transaction identifier | Order code | Yes |
| Status | Confirmed / pending / failed | Yes |
| Key figures | Total amount, quantity, due date | Yes |
| Timing | Delivery date, confirmation deadline | Yes |
| Next action | View order, pay, confirm | Yes |
| Action target | URL or access instructions | Yes |
| Support | Email or contact channel | Yes if the recipient needs it |
| Decorative | Background colors, borders, icons | Not necessarily |
| Presentation effects | Rounded buttons, spacing, banners | No |

Decorative information can exist only in HTML. However, if an image contains a verification code, amount, or unique instructions, that data must be restated as text in both representations.

### Use Business Requirements as the Source of Truth

A common mistake is when a development team writes HTML first and then creates plain text by ad-hoc abbreviation. After several edits, the two versions can drift: HTML has the updated deadline while plain text keeps the old deadline.

Define **a canonical list of facts** and build both versions from that list. When business logic changes, the source data and rendering rules are updated once; both representations continue using the same values.

## 4. Use the Same View Model to Generate Plain Text and HTML

In a Spring application, you can define an object holding only the email information to present:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        BigDecimal totalAmount,
        String formattedTotal,
        LocalDate expectedDeliveryDate,
        String formattedDeliveryDate,
        String detailsUrl,
        String supportEmail) {
}
~~~

The view model is created from validated business data:

~~~java
OrderMailView view = new OrderMailView(
        customer.getDisplayName(),
        order.getCode(),
        "Confirmed",
        order.getTotalAmount(),
        moneyFormatter.format(order.getTotalAmount()),
        order.getExpectedDeliveryDate(),
        dateFormatter.format(order.getExpectedDeliveryDate()),
        orderDetailsUrl,
        "support@example.org"
);
~~~

This is a structural example; `moneyFormatter` and `dateFormatter` are formatters configured by the application according to locale and business rules.

**Do not query or recompute data independently for each version.** If plain text and HTML call two different data sources, status or amounts could change between the two renders. Create the view model once, then pass the same object to both renderers.

### Why Pre-Format Data?

Values such as currency, dates, and time zones need to be expressed consistently:

- Do not have HTML write `1.250.000 ₫` while plain text writes `1,250,000 VND` if two formats could confuse the same recipient.
- Do not put the date in HTML in local time while plain text uses UTC without stating the time zone.
- Do not compute remaining time separately in each renderer, as the two calculations could differ by a few seconds or cross a day boundary.

You can format values once in the view model or in a shared presentation layer. The two renderers are only responsible for laying out the presentation.

## 5. Example of Plain Text and HTML with the Same Information

Assume the data:

~~~java
OrderMailView view = new OrderMailView(
        "Nguyen An",
        "ORD-2048",
        "Confirmed",
        new BigDecimal("1250000"),
        "1,250,000 VND",
        LocalDate.of(2026, 11, 18),
        "18/11/2026",
        "https://app.example.org/orders/ORD-2048",
        "support@example.org"
);
~~~

### 5.1. Plain Text Version

~~~java
private String renderPlainText(OrderMailView view) {
    return """
            Hello %s,

            Order %s has been confirmed.

            Status: %s
            Total: %s
            Estimated delivery: %s

            View order details:
            %s

            If you need support, please contact %s.
            """.formatted(
            view.customerName(),
            view.orderCode(),
            view.statusLabel(),
            view.formattedTotal(),
            view.formattedDeliveryDate(),
            view.detailsUrl(),
            view.supportEmail()
    );
}
~~~

The plain text version needs no HTML tags. The URL is written on its own line so it can be copied or opened from a mail client. All key facts remain intact.

### 5.2. HTML Version

~~~java
private String renderHtml(OrderMailView view) {
    String customerName = escapeHtml(view.customerName());
    String orderCode = escapeHtml(view.orderCode());
    String status = escapeHtml(view.statusLabel());
    String total = escapeHtml(view.formattedTotal());
    String deliveryDate = escapeHtml(view.formattedDeliveryDate());
    String detailsUrl = escapeHtml(view.detailsUrl());
    String supportEmail = escapeHtml(view.supportEmail());

    return """
            <!doctype html>
            <html lang="en">
              <body>
                <h2>Order Confirmed</h2>
                <p>Hello %s,</p>

                <table>
                  <tr>
                    <th>Order code</th>
                    <td>%s</td>
                  </tr>
                  <tr>
                    <th>Status</th>
                    <td>%s</td>
                  </tr>
                  <tr>
                    <th>Total</th>
                    <td>%s</td>
                  </tr>
                  <tr>
                    <th>Estimated delivery</th>
                    <td>%s</td>
                  </tr>
                </table>

                <p>
                  <a href="%s">View order details</a>
                </p>

                <p>Support: %s</p>
              </body>
            </html>
            """.formatted(
            customerName,
            orderCode,
            status,
            total,
            deliveryDate,
            detailsUrl,
            supportEmail
    );
}
~~~

The `escapeHtml` method here is an HTML text/attribute escaping utility provided by the application or a suitable library. In production code, validate URLs for scheme/host before inserting into `href`; HTML escaping alone does not verify the link destination. With a template engine such as Thymeleaf, you can use escaped output for text values instead of manual string formatting.

### 5.3. Comparing the Two Versions

| Information | Plain text | HTML |
| --- | --- | --- |
| Customer | `Nguyen An` | `Nguyen An` |
| Order code | `ORD-2048` | `ORD-2048` |
| Status | `Confirmed` | `Confirmed` |
| Total | `1,250,000 VND` | `1,250,000 VND` |
| Delivery date | `18/11/2026` | `18/11/2026` |
| Action | URL displayed directly | Link labeled "View order details" |
| Support | Support email | Support email |

The two versions differ in form, yet **neither is missing important facts present in the other**.

## 6. Sending Both Representations with MimeMessageHelper

After preparing both strings, use the two-parameter overload of `setText`:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmation(
            String recipient,
            OrderMailView view) throws MessagingException {

        String plainText = renderPlainText(view);
        String htmlText = renderHtml(view);

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("orders@example.org");
        helper.setTo(recipient);
        helper.setSubject(
                "Order " + view.orderCode()
                        + " has been confirmed"
        );

        // One message contains both text/plain and text/html.
        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }

    // renderPlainText, renderHtml, and escapeHtml are defined
    // in the service or separate presentation components.
}
~~~

Key points:

1. `renderPlainText(view)` and `renderHtml(view)` receive **the same view model**.
2. `new MimeMessageHelper(message, true, "UTF-8")` enables multipart to support multiple content formats.
3. `setText(plainText, htmlText)` sets the two alternative representations.
4. `JavaMailSender.send(message)` sends a single message over SMTP.

If sending only a plain text body, you can use `setText(plainText)`. If sending only HTML, use `setText(htmlText, true)`. When both representations are wanted, use the two-string overload with the helper in an appropriate multipart mode.

### Do Not Call send Twice to Send Two Formats

Do not do this:

~~~java
helper.setText(plainText, false);
mailSender.send(message);

MimeMessage anotherMessage = mailSender.createMimeMessage();
// Build HTML and send a second time...
~~~

This creates two separate emails. Recipients may see both messages, the sending system may count quota twice, and delivery state tracking becomes complicated. `multipart/alternative` is designed to carry both content formats inside **a single message**.

## 7. Information Commonly Lost When Creating the Plain Text Version

When converting an email from HTML to plain text, presentation elements need to be re-expressed. This is where discrepancies easily arise.

### 7.1. Buttons Must Have a Corresponding URL

HTML:

~~~html
<a href="https://app.example.org/orders/ORD-2048">
  View order
</a>
~~~

Plain text should not merely say:

~~~text
View order
~~~

Because the reader has no button or hyperlink to click. Instead write:

~~~text
View order:
https://app.example.org/orders/ORD-2048
~~~

If the URL is long, you can use an application-controlled shortened URL, but the action target must match the HTML version.

### 7.2. Tables Must Retain Field Names and Values

HTML can use a two-column table. Plain text should clearly state label/value pairs:

~~~text
Order code: ORD-2048
Status: Confirmed
Total: 1,250,000 VND
Estimated delivery date: 18/11/2026
~~~

Do not just concatenate values in order while dropping field names. Without borders and columns, the reader may not know which number is the amount and which is the order code.

### 7.3. Informative Images Need Corresponding Text

If HTML displays a banner:

~~~html
<img src="cid:payment-status" alt="Payment successful">
~~~

then the plain text version should include a line:

~~~text
Payment status: Successful.
~~~

Do not leave status, verification codes, due dates, or important instructions only inside an image. `alt` is helpful for HTML, but it does not replace a separate plain text representation.

### 7.4. Lists Must Keep All Items

HTML:

~~~html
<ul>
  <li>Verify the delivery address.</li>
  <li>Ensure someone is available to receive the package.</li>
  <li>Have the order code ready when contacting support.</li>
</ul>
~~~

Plain text:

~~~text
Preparation steps:
- Verify the delivery address.
- Ensure someone is available to receive the package.
- Have the order code ready when contacting support.
~~~

Do not trim plain text to the point of dropping an important step.

### 7.5. Conditionally Shown or Hidden Content Must Be Consistent

If HTML uses a condition to show a warning, the plain text version must apply the same condition and data. For example, a `PENDING` payment status must show awaiting-payment details in both versions; never leave plain text hardcoded to "Paid".

**Do not evaluate conditions separately in each renderer.** Decide the business state up front, put it in the view model, and let both renderers present that value.

## 8. Actions and Links Must Be Equivalent

Emails often ask the recipient to perform a step:

- Confirm an email address.
- Pay an invoice.
- Reset a password.
- View order status.
- Confirm an appointment.
- Download a document.

The HTML version may have a large button, but the plain text version must provide **the same destination and the same action meaning**.

| HTML | Corresponding plain text |
| --- | --- |
| "Confirm email" button | "Confirm email: URL" |
| "Pay now" button | "Pay at: URL" |
| "View invoice" link | "View invoice: URL" |
| "Change password" link | "Change password: URL" |
| QR code opening confirmation page | URL or alternative instructions |

### Avoid Leaving the URL Only Inside href

A common mistake:

~~~html
<a href="https://app.example.org/pay/INV-12">Pay now</a>
~~~

Plain text:

~~~text
Pay now.
~~~

The plain text reader knows they must pay, but does not know where to go. Provide the URL or clear instructions.

### Tokens and Sensitive Paths

For password reset or account confirmation links, the URL may contain a token. If the same URL appears in both representations, the recipient retains the same ability to act, but the application must protect tokens according to policy: expiration, scope, single use, no logging, and avoiding sending to the wrong recipient.

Content equivalence **does not mean** exposing additional sensitive data. If a URL is not permitted in plain text by product security requirements, provide an alternative instruction accomplishing the same goal, such as signing in to the official website and opening the confirmation section.

## 9. Subject and Headers Are Shared, Not Two Alternative Bodies

In a multipart/alternative message, Subject is set only once:

~~~java
helper.setSubject("Invoice INV-12 is ready");
helper.setText(plainText, htmlText);
~~~

There is no separate Subject for `text/plain` and separate Subject for `text/html`. Both representations belong to the same message and share the same headers.

If you want the heading content to appear inside the body, such as "Invoice is ready", ensure both plain text and HTML have an appropriate opening. However, repeating the Subject verbatim is not strictly required if the message is already clear.

Likewise, From, To, Cc, Bcc, Reply-To, and other headers are not alternative bodies. They apply at the message level.

## 10. Plain Text Should Be Readable, Not Just Complete

A plain text version with complete information formatted as one long string is still hard to read. Organize the content using:

- Short paragraphs.
- Blank lines between groups.
- Clear labels for important data.
- Bulleted lists.
- URLs on their own lines.
- Step-by-step instructions.
- A signature or support info at the end.

Hard-to-read example:

~~~text
Hello An order ORD-2048 confirmed total 1250000 delivery 18/11 view https://app.example.org/orders/ORD-2048 need support support@example.org.
~~~

Readable example:

~~~text
Hello An,

Order ORD-2048 has been confirmed.

Total: 1,250,000 VND
Estimated delivery: 18/11/2026

View details:
https://app.example.org/orders/ORD-2048

Need support? Contact support@example.org.
~~~

Do not try to build overly complex ASCII tables if the content may be displayed on narrow screens. Plain text formatting should prioritize readability and copyability.

## 11. HTML Can Be Richer, But Must Not Hold Exclusive Facts

HTML can add:

- Colors to emphasize status.
- Logos and decorative images.
- Tables to group data.
- Styled action buttons.
- Spacing and heading hierarchy.
- Icons to aid navigation.

These elements improve presentation. However, HTML must not be the sole place holding essential information.

For example, if HTML uses green to indicate "Paid", do not rely on color alone—include the text `Paid`. Readers may not see colors if the client strips CSS or if the user has color vision deficiency.

Similarly, if HTML has a warning icon, include text such as "Payment required before..." so the meaning does not depend on the image.

### Accessibility Helps Both Representations

The HTML version should use meaningful structure:

- Sequential headings.
- Clear text labels.
- Tables with proper field headers.
- Links with action-descriptive text.
- Images with appropriate alt text.
- Never conveying status through color alone.

The plain text version should also maintain reading order and data labels. Both serve one goal: the recipient understands the notification and knows what to do next.

## 12. Multilingual Content Must Also Be Equivalent

If emails support Vietnamese and English, ensure **both formats in the same message use the same locale**.

Vietnamese example:

~~~text
Đơn hàng ORD-2048 đã được xác nhận.
Tổng tiền: 1.250.000 ₫
Giao dự kiến: 18/11/2026
~~~

The Vietnamese HTML version must also have the corresponding facts. Do not leave plain text defaulting to English while HTML renders in Vietnamese simply because the two renderers use two different message bundle sources.

Choose the locale once, construct the view model for that locale, and pass the same formatted data to both renderers.

### Dates, Times, and Time Zones

If an email states an appointment at 09:00 on 20/11 Vietnam time, both plain and HTML must express the same instant and time zone. Avoid having one version use local time and the other use UTC without stating it explicitly.

You can store the canonical timestamp as an instant, then format it once for the recipient's timezone:

~~~java
ZonedDateTime localTime =
        appointmentInstant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String formattedTime =
        DateTimeFormatter.ofPattern(
                "HH:mm dd/MM/yyyy z",
                Locale.forLanguageTag("vi-VN")
        ).format(localTime);
~~~

Both representations use `formattedTime`. If the product supports multiple time zones, the timezone must be determined by recipient policy and stated clearly in the email.

### Currency and Decimals

Use the same formatter to prevent HTML and plain text from unexpectedly having different separators or currency symbols. If multiple converted currencies need to be shown, values and applied exchange rates must come from the same business snapshot.

## 13. Handling Dynamic Data: Plain Text and HTML Differ

Dynamic data must be included in both versions, but encoding depends on the format:

- **Plain text:** use business-validated text values; normalize newlines and control characters according to policy.
- **HTML:** escape data in the appropriate text-node or attribute context; validate URLs before placing them in href.
- **Subject:** set via the header API, do not use HTML entities to handle Unicode.
- **URL:** build from a trusted source, encode path/query components, then represent safely when placing in an HTML attribute.

For example, suppose the recipient name is:

~~~text
An <Bao> & Co.
~~~

Plain text:

~~~text
Hello An <Bao> & Co.
~~~

HTML source:

~~~html
<p>Hello An &lt;Bao&gt; &amp; Co.</p>
~~~

HTML readers will also see `An <Bao> & Co.`. Do not put HTML-escaped strings into the plain text version, because recipients would see `&lt;` and `&amp;`.

### Do Not Double-Escape the Same String

If the backend escapes the name to `An &lt;Bao&gt;` and then the template engine escapes it again, recipients may see literal entities. Pick one place responsible for HTML escaping; plain text always uses the logical value, never the HTML-escaped string.

### Do Not Let User Data Become Markup

If a user enters `<strong>Priority</strong>` in a note field, determine the business intent:

- If the note is plain text, plain text keeps the string as-is and HTML escapes it so the tags display as text.
- If rich text is allowed, sanitize HTML against an allowlist before putting it in the HTML body; plain text needs an equivalently meaningful representation, such as "Priority".

Do not use `setText(html, true)` as a sanitization mechanism. The helper only packages the MIME body.

## 14. Combining Inline Images and multipart/alternative

A message can contain plain text, HTML, and inline images referenced by HTML via CID. The MIME structure typically has nested layers, for example:

~~~text
multipart/related
├── multipart/alternative
│   ├── text/plain
│   └── text/html
│       └── <img src="cid:brand-logo">
└── image/png
    └── Content-ID: <brand-logo>
~~~

Plain text does not need `cid:brand-logo` because it does not render images via HTML. However, **any meaningful content carried by the image must be expressed in text**.

For example, a purely decorative brand logo may not need a long description in plain text. But if the image is a payment QR code, plain text needs the equivalent payment URL or instructions. Never leave a QR code as the only way to complete an action.

When using `MimeMessageHelper`, create the helper in the appropriate multipart mode, call `setText(plainText, htmlText)` first, and then add inline resources with `addInline(...)`. The CID name in HTML must match the Content-ID added to the message by the helper.

## 15. Attachments Are Not Alternative Representations

An attachment such as an invoice PDF or spreadsheet is not a third version of the alternative body. It is a separate MIME part that can reside in a `multipart/mixed` structure wrapping the body.

Conceptual example:

~~~text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
└── application/pdf
    └── invoice.pdf
~~~

If the email says "The invoice is attached", both plain and HTML should say so. If HTML has a link to download the invoice online while plain text lacks it, plain text users lose that action; provide the URL or equivalent instructions.

Having a PDF does not exempt the body from providing key facts such as invoice code, amount, and due date. Attachments may fail to open or be blocked by receiving systems.

## 16. Common Design Mistakes

### 16.1. Plain Text Is Just a Shortened Sentence Missing Facts

HTML has order code, total, and payment deadline; plain text only says "You have a new order". Plain text readers lack sufficient information.

**How to handle:** list required facts and share one view model across both renderers.

### 16.2. HTML Has a Button, Plain Text Has No URL

Plain text readers know they should click "Pay", but have no destination.

**How to handle:** include the URL or equivalent access instructions in the plain text version.

### 16.3. Plain Text Generated by Stripping HTML Tags

A tag-stripping regex can lose URLs, labels, table structure, and attribute information.

**How to handle:** build plain text separately from business data or use a controlled HTML-to-text converter, and still verify the output.

### 16.4. Two Renderers Query Data Separately

Order status or amount could change between two reads, causing differing representations.

**How to handle:** create a view model/snapshot once and pass it to both renderers.

### 16.5. Different Date/Time or Currency Formatting

HTML and plain text may show seemingly different values due to locale or timezone.

**How to handle:** format once from the same value and timezone/locale.

### 16.6. HTML Holds Information Only in an Image

A banner says "Pay before 20/11", yet plain text has no deadline.

**How to handle:** include that information as text in both versions; images only supplement presentation.

### 16.7. HTML Link and Plain URL Point to Different Targets

A copy/paste mistake could make the HTML button open order A while the plain text URL opens order B.

**How to handle:** construct the URL once in the view model and use the same value for both representations.

### 16.8. Subject Differs from Alternative Bodies

Subject is a shared header, yet body content might omit details and mislead readers. Ensure Subject and both bodies reflect the same business event without showing conflicting statuses.

### 16.9. Using HTML-Escaped Data in Plain Text

Plain text shows `&lt;` or `&amp;` because the application reused strings escaped for HTML.

**How to handle:** keep the raw logical data and encode separately per representation.

### 16.10. Sending Two Messages Instead of multipart/alternative

Recipients may receive two similar emails, causing confusion and doubling send volume.

**How to handle:** use `setText(plainText, htmlText)` to create one message with two alternative body parts.

### 16.11. Testing Only HTML

The HTML template may be correct while plain text is outdated or missing a URL.

**How to handle:** test both renderers and the shared facts.

### 16.12. Assuming Prettier HTML Means More Complete

Good layout cannot make up for missing data. Every representation must tell the recipient what happened and what to do next.

## 17. Testing Information Equivalence

You do not need to assert that the two strings are identical. You need to verify that **important facts appear in both versions**.

Suppose the view model is:

~~~java
OrderMailView view = ...;
String plain = renderPlainText(view);
String html = renderHtml(view);
~~~

Some simple assertions:

~~~java
assertTrue(plain.contains(view.orderCode()));
assertTrue(html.contains(view.orderCode()));

assertTrue(plain.contains(view.formattedTotal()));
assertTrue(html.contains(view.formattedTotal()));

assertTrue(plain.contains(view.formattedDeliveryDate()));
assertTrue(html.contains(view.formattedDeliveryDate()));

assertTrue(plain.contains(view.detailsUrl()));
assertTrue(html.contains(view.detailsUrl()));
~~~

In HTML, URLs may be escaped inside attributes, so more thorough tests should parse the HTML or verify attribute values after HTML decoding rather than always comparing raw strings.

### 17.1. Semantic Checklist Verification

A fact table helps development teams define requirements:

| Assertion | Plain text | HTML |
| --- | --- | --- |
| Has order code | Yes | Yes |
| Has status | Yes | Yes |
| Has total and currency unit | Yes | Yes |
| Has due/delivery date | Yes | Yes |
| Has next action | Yes | Yes |
| Has corresponding link target | URL/instructions | href |
| Has support channel | Yes | Yes |
| Does not leak unauthorized data | Yes | Yes |

These checks should be updated whenever business rules change. They verify the content the recipient needs, not how HTML is serialized to bytes.

### 17.2. Verifying MIME Structure

You can use a test SMTP server or read back the `MimeMessage` in unit/integration tests to verify the message has:

- One `text/plain` part.
- One `text/html` part.
- Both inside an appropriate `multipart/alternative` structure.
- Attachments or inline resources inside appropriate containers if present.

Do not assume HTML is always at a fixed part index in the outermost multipart, because the structure may nest `multipart/related` or `multipart/mixed`. Traverse the MIME tree by Content-Type.

### 17.3. Checking Mail Client Experience

After checking MIME, send to a test environment and open on target clients. Verify:

- HTML renders properly.
- Plain text is readable standalone.
- URLs open and point to the same destination.
- Images do not hold exclusive facts.
- Important information does not rely on color or CSS.
- No lines or tables are clipped on narrow screens.

## 18. Example Using a Template Engine

If the application uses Thymeleaf, you can keep two separate templates:

~~~text
templates/mail/order-confirmed.html
templates/mail/order-confirmed.txt
~~~

The HTML template can use markup:

~~~html
<h2>Order Confirmed</h2>
<p>Hello, <span th:text="¤{mail.customerName}">Customer</span>.</p>
<p>Order code: <span th:text="¤{mail.orderCode}">ORD-2048</span></p>
<p>Total: <span th:text="¤{mail.formattedTotal}">1,250,000 VND</span></p>
<a th:href="¤{mail.detailsUrl}">View details</a>
~~~

The text template can use text mode syntax or a template mechanism suited for plain text:

~~~text
Hello, [customerName].

Order [orderCode] has been confirmed.
Total: [formattedTotal]

View details:
[detailsUrl]
~~~

Placeholders in the plain example are illustrative; exact syntax depends on how the application configures the template engine for text mode. What matters is that **both templates receive the same view model** and are rendered with the same locale.

Java example:

~~~java
Context context = new Context(locale);
context.setVariable("mail", view);

String html = templateEngine.process(
        "mail/order-confirmed",
        context
);

String plain = plainTextRenderer.render(view, locale);

helper.setText(plain, html);
~~~

Do not use an HTML template as the source and strip tags with regex to create text if the content contains tables, links, or complex conditions. An explicit plain text renderer is usually easier to audit for completeness.

## 19. When Can the Two Versions Differ?

The two representations can differ in **presentation**, while keeping the same business meaning.

Acceptable differences:

- HTML has a button, plain text shows the URL.
- HTML has a table, plain text has labels and data lines.
- HTML has a decorative logo, plain text has no logo.
- HTML uses color for emphasis, plain text uses words like "Warning".
- HTML has spacing and typography, plain text uses blank lines and bullets.

Unacceptable differences:

- HTML says paid, plain text says pending.
- HTML has a deadline, plain text omits the deadline.
- HTML has a confirmation button, plain text lacks a URL or alternative instructions.
- HTML shows a tax-inclusive total, plain text shows a pre-tax total without explanation.
- HTML uses dates in one timezone, plain text uses dates in another timezone.
- HTML shows one transaction ID, plain text shows another ID.

### Can Different Levels of Detail Be Provided?

If HTML has extra decorative content or non-essential supplemental guidance, plain text does not need to reproduce every detail. However, if that content could affect the recipient's decision, rights, obligations, or actions, it must be expressed in the plain text version.

## 20. Practice Questions

**Q1.** Why send both `text/plain` and `text/html` in one email?

So the mail client can choose an appropriate representation. Recipients still have readable content when HTML is unsupported or restricted.

**Q2.** Does `setText(plainText, htmlText)` create two separate emails?

No. It creates two alternative body parts within a single `multipart/alternative` MIME message.

**Q3.** HTML has a "View invoice" button, while plain text only says "View invoice". Are they equivalent?

No. Plain text needs the URL or equivalent instructions so the recipient can perform the action.

**Q4.** Should plain text be created by removing all HTML tags with a regex?

You should not rely on that approach for complex templates. It can lose URLs, table labels, image content, and structure. Build plain text from the same business data.

**Q5.** Can plain text and HTML use two separate database queries?

No. Two queries could return different statuses or values. Build the view model/snapshot once and pass it to both renderers.

**Q6.** Recipient name data contains `<`. Do plain text and HTML represent it the same way?

Not necessarily. Plain text uses the raw string; HTML source must escape characters according to context. When displayed, both convey the same name.

**Q7.** A QR code containing a payment URL appears in HTML. What does plain text need?

It needs the payment URL or equivalent payment instructions. Never leave a QR code as the only way to take action.

**Q8.** Can different Subjects be used for the two alternative bodies?

No. Subject is a shared message header. The two alternatives are only body representations.

**Q9.** HTML has a CID logo, plain text has no image. Does this violate equivalence?

Not necessarily. If the logo is purely branding, plain text does not need to recreate the image. If the image carries business information or an action, that content must have a text representation.

**Q10.** Does testing both bodies require the HTML and plain text strings to be identical?

No. You need to verify that key facts and actions are present and consistent in both versions; layout and formatting may differ.

## 21. Mental Model

A multi-format email should be built following this workflow:

~~~mermaid
flowchart TD
    A["Validated business data"] --> B["Shared view model"]
    B --> C["text/plain renderer"]
    B --> D["text/html renderer"]
    C --> E["MimeMessageHelper.setText(plain, html)"]
    D --> E
    E --> F["One multipart/alternative MIME message"]
    F --> G["JavaMailSender.send"]
    G --> H["Mail client selects appropriate representation"]
~~~

Remember:

1. **Plain text and HTML are two alternative representations of the same content**, not two separate emails.
2. **All important information and actions must exist in both versions**: codes, statuses, amounts, times, instructions, URLs, and support channels.
3. **Use the same view model or data snapshot** to avoid mismatched statuses, amounts, dates/times, and URLs.
4. **HTML may be richer in presentation**, but must not contain exclusive facts inaccessible to plain text.
5. **HTML links must have corresponding URLs/instructions in plain text**; tables and informative images must be expressed as text.
6. **Encode per format**: plain text uses logical text, HTML escapes by context, URLs are validated separately.
7. **Use `MimeMessageHelper.setText(plainText, htmlText)`** with a multipart helper to create one message with two representations.
8. **Test semantic parity**, not exact string equality; confirm key facts and actions are present and consistent.

When the application builds both plain text and HTML from the same data source, recipients receive a complete message regardless of which display mode their mail client chooses. `MimeMessageHelper` packages both representations into the MIME message, and `JavaMailSender` sends a single message over the configured SMTP transport.
