# Limitations of Plain Text When Formatting Is Needed

In **Spring Framework Mail**, the simplest way to send an email usually starts with **SimpleMailMessage**: choose the sender, recipient, subject, content, and then call **JavaMailSender.send(...)**. This approach suits notifications that only need clear text such as verification codes, system alerts, or confirming an action. But when an email needs large headings, colors, action buttons, layout tables, logos, or images placed right inside the content, **plain text can no longer express display requirements reliably**.

The point to understand is not that plain text is an "inferior" format, but that it has a **different display contract from HTML**. In plain text, the sender provides **characters and line breaks**; the mail-reading application decides the typeface, size, colors, and layout. Content like **<strong>Important</strong>** does not turn into bold text on its own. Likewise, Markdown asterisks do not automatically become formatting in a plain text email.

This lesson explains that limitation in the **Simple mail** chapter, showing when to keep **SimpleMailMessage**, when to switch to **MimeMessage** and **MimeMessageHelper**, and how to send both **plain text + HTML** so readers still have usable content when HTML is disabled or unsupported.

## 1. What actually is plain text in email?

An email with a plain text body is usually represented with **Content-Type: text/plain**. MIME may add a charset parameter, for example:

~~~text
MIME-Version: 1.0
From: notifications@example.test
To: learner@example.test
Subject: Notification
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!
~~~

The raw snippet above illustrates the content **"Xin chào!"** converted from characters to UTF-8 bytes, and then encoded with **quoted-printable** for transport. When the mail reader decodes it, the user sees normal text.

Three concepts must be distinguished:

| Concept | What does it specify? | Example |
| --- | --- | --- |
| **Content-Type** | Whether the data should be interpreted as plain text, HTML, or another content type | **text/plain**, **text/html** |
| **Charset** | Which character encoding maps bytes to characters | **UTF-8** |
| **Content-Transfer-Encoding** | How bytes are represented inside the MIME body for transport | **quoted-printable**, **base64**, **7bit** |

**UTF-8 does not turn plain text into HTML**, and **Base64 does not create bold/italic formatting**. Encoding mechanisms solve preserving characters/bytes, while content type determines how the mail reader interprets them.

### How does SimpleMailMessage relate to text/plain?

In Spring Mail, **SimpleMailMessage** is the object holding basic message properties:

- **From**, **Reply-To**, **To**, **Cc**, **Bcc**.
- **Subject**.
- **Sent date** if needed.
- **Text**: plain text content string.

When sending via **JavaMailSender** or a suitable implementation, the library prepares the email message needed to submit to the transport. **SimpleMailMessage has no API to select an HTML body, add inline MIME parts, or attach files** like **MimeMessageHelper** does.

Therefore, if you need an email whose body has a complex display structure, simply changing the string passed to **SimpleMailMessage.setText(...)** is usually not enough. You need to switch to the appropriate MIME message creation API.

## 2. What plain text does well

Plain text still holds great value because it is simple, easy to read, and depends very little on the email client's presentation.

For example, a notification can be written as:

~~~text
REGISTRATION CONFIRMATION

Hello Lan,

You have successfully registered for the course "Spring Boot Fundamentals".

Registration code: REG-1528
Time:              09:00 on 20/11/2026

To view details:
https://learning.example.test/registrations/REG-1528

If you did not make this request, please contact support.

Best regards,
The Learning Team
~~~

This content still has order, paragraph spacing, and text links. Recipients can read it even when their mail application restricts HTML, images, or CSS.

Presentation tools you can use safely in plain text include:

- **Paragraphs** separated by blank lines.
- **Text headings**, for example an uppercase line or adding divider characters.
- **Lists** numbered or bulleted as ordinary characters.
- **Labels and values**, such as **Order code: ORDER-125**.
- **Full links** with the **https://** protocol, convenient to copy.
- **Action steps** in a clear sequence.

However, the fact that characters appear accurately does not mean they will be presented with the same font, width, font size, or layout on every device.

### Plain text also supports Vietnamese and Unicode

Plain text is **not limited to ASCII** if the message uses an appropriate charset/transfer encoding. Content like:

~~~text
Hello,
Your verification code is: 482193
This code expires in 10 minutes.
~~~

can be sent in UTF-8. When a recipient sees corrupted diacritics, check the charset, input data encoding, and MIME headers, instead of concluding that plain text cannot contain Vietnamese.

Unicode characters or emojis can also be represented in text/plain. Yet how glyphs render still depends on fonts, operating systems, and email clients; do not rely on emojis as **the sole medium for conveying critical status**.

## 3. First limitation: no control over typeface and colors

Suppose the UI requirement is:

> The line "Payment successful" must be green, large font; the amount in bold; the warning at the bottom in red.

Putting the following string into SimpleMailMessage:

~~~text
<h1 style="color:green">Payment successful</h1>
Amount: <strong>350.000 VND</strong>
<p style="color:red">Do not share the transaction code.</p>
~~~

**does not turn it into HTML when the message is sent as text/plain**. Readers will usually see the **<**, **>**, attributes, and tags verbatim, like uninterpreted code.

A Markdown-style string does not create formatting on its own either:

~~~text
# Payment successful
**Amount:** 350.000 VND
~~~

When inside a **text/plain** body, **#** and **\*\*** characters remain literal characters. Some apps may apply custom display rules, yet there is no standard contract that every email client will render Markdown into headings and bold text.

**You should not expect recipients to use the same Markdown viewer or HTML preview tool as developers**. Email clients process content based on MIME type and rendering capability, not on how the developer intended to "format" a text string.

### Why can't ANSI escape codes be used?

Some terminal programs support ANSI control codes to change colors, bold text, or control the cursor. Email clients have no obligation to interpret those sequences in **text/plain**. Putting escape codes into email can cause strange characters to appear, harm readability, or create risks when data passes through logging/terminal systems.

Plain text is not an interactive terminal; console color tricks are not a reliable email formatting approach.

## 4. Second limitation: column alignment, tables, and layout drift easily

You can write a simple table using spaces:

~~~text
Product            Quantity    Amount
Spring Course      1           500.000
Extra Materials    2           100.000
-------------------------------------------
Total                          600.000 VND
~~~

It looks aligned in a **monospace** editor, yet is not guaranteed to display properly in email clients:

- Mail readers may use **proportional fonts**; the characters **i** and **W** have different widths.
- Mobile clients may wrap lines automatically because of a narrow viewport.
- Vietnamese characters, wide characters, combining marks, or emojis can occupy a different display column count than their character count.
- Users may enlarge text via accessibility settings.
- Some clients reinterpret line formatting or alter whitespace display.

Therefore, do not use space padding to guarantee that invoices, reports, or comparison tables keep their columns aligned across all devices.

### Alternative presentation when you still want plain text

Replace multi-column tables with labeled information blocks:

~~~text
ORDER #ORD-1528

1. Spring Course
   Quantity: 1
   Amount: 500.000 VND

2. Extra Materials
   Quantity: 2
   Amount: 100.000 VND

TOTAL: 600.000 VND
~~~

This approach usually holds up better on narrow screens because meaning does not depend on horizontal spacing. Yet if the requirement is genuinely **tables with borders, right-aligned amounts, alternating row backgrounds, and grouped rows**, you will need HTML content (or an attachment like PDF when you want a fixed layout).

### Line breaks are not absolute either

In Java strings, **\n** represents a logical line break; the transport library may normalize to **CRLF** per email rules. Email clients may wrap long lines to fit the viewport. **Sender-created line breaks** and **client-wrapped lines at display time** are two different things.

Plain text also has mechanisms like **format=flowed** to hint how text lines should be presented, yet you should not assume **SimpleMailMessage** produces that style of content or that every client applies it identically.

If you need to emphasize a warning, write it as a standalone, easy-to-read sentence instead of relying on spaces or column alignment.

## 5. Third limitation: links do not become intentional action buttons

In text/plain:

~~~text
View your order:
https://orders.example.test/order/1528
~~~

many email clients will **auto-detect the URL and turn it into a clickable link**, yet that is client behavior. The sender does not reliably control button labels, colors, clickable area, or hover states as in HTML.

Nor can you create a real button simply by writing:

~~~text
[ VIEW ORDER ]
~~~

This line is just characters. Readers can understand the meaning, yet there is no URL attached to a display region defined by **text/plain**. Markdown syntax like **[View order](https://orders.example.test/order/1528)** is likewise not guaranteed to become a nicely labeled link in plain text email.

When you need a **call-to-action** (CTA) such as a "Reset password", "Confirm email", or "View invoice" button, HTML can represent a link element with a clear label and presentation style:

~~~html
<a href="https://orders.example.test/order/1528">
  View order
</a>
~~~

However, HTML itself has varying CSS support across email clients. **The HTML link is the functional element**, while making it look like a neat button must be designed and tested against target clients.

For the plain text fallback, provide a full, easy-to-copy URL. Avoid instructions like "click the green button below" when there is actually no button in the plain text part.

## 6. Fourth limitation: images, attachments, and multipart content

**SimpleMailMessage.setText(...)** accepts only a text string. If you pass an image path:

~~~text
Logo: /assets/brand-logo.png
~~~

the mail reader does not automatically access files on the server's disk to render the logo. Similarly, inserting **PDF bytes** or a Base64 string into the text body does not create an attachment automatically.

In email, these contents are different **MIME parts**:

| Requirement | Common representation |
| --- | --- |
| Simple text | **text/plain** |
| Content with headings, HTML lists, colors, labeled links | **text/html** |
| Two equivalent content versions plain + HTML | **multipart/alternative** |
| Image referenced by HTML via **cid:** | **multipart/related** with an image having a **Content-ID** |
| Attached PDF, CSV, or ZIP file | MIME part with **Content-Disposition: attachment**; usually inside **multipart/mixed** |

**MIME is the packaging mechanism**, while **HTML** is one content type inside MIME. Having an attachment does not necessarily mean the email must have an HTML body; an email can still have a text/plain body part and an attached PDF.

When you need these MIME parts in Spring, **JavaMailSender** together with **MimeMessage** and **MimeMessageHelper** is more suitable than **SimpleMailMessage**.

## 7. Sending plain text with SimpleMailMessage

Here is a complete example at the Spring service level showing how to send a text notification:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class RegistrationPlainMailService {

    private final JavaMailSender mailSender;

    public RegistrationPlainMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendRegistrationNotice(
            String recipient,
            String registrationCode
    ) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("notifications@example.test");
        mail.setTo(recipient);
        mail.setReplyTo("support@example.test");
        mail.setSubject("Registration confirmation");

        String body = """
                REGISTRATION CONFIRMATION

                Hello,

                Your registration request has been recorded.
                Registration code: %s

                If you need support, please reply to this email.

                Best regards,
                The Learning Team
                """.formatted(registrationCode);

        mail.setText(body);
        mailSender.send(mail);
    }
}
~~~

Key points in the snippet:

- **setSubject(...)** sets the email subject; it is not an HTML heading inside the body.
- **setText(...)** sets the plain text content. Line breaks and characters in the text block are part of the content string.
- **setReplyTo(...)** directs where users send replies; it does not turn the body into HTML.
- **send(mail)** submits the message over the configured transport. It does not guarantee the message has been delivered to the Inbox.

The example uses the **example.test** domain for illustration. In a real application, **registrationCode** must be generated and controlled by business logic; addresses, SMTP settings, and sending permissions must be valid per provider.

### What if you put HTML into setText?

Example:

~~~java
mail.setText("""
        <h1>Registration successful</h1>
        <p><strong>Registration code:</strong> REG-1528</p>
        """);
~~~

This is still a **text string**. There is no parameter on **SimpleMailMessage.setText(...)** to declare that the body is **text/html**. Thus, recipients may see the raw tags instead of seeing a bold heading and rendered paragraph.

**Do not fix this by setting Content-Type manually where no proper MIME API exists.** Use **MimeMessage** when you truly need HTML and manage the MIME part types properly.

## 8. Switching to HTML with MimeMessageHelper

If the requirement is an email with HTML headings, styled paragraphs, and link buttons, use **MimeMessageHelper.setText(html, true)**.

Example:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RegistrationHtmlMailService {

    private final JavaMailSender mailSender;

    public RegistrationHtmlMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("notifications@example.test");
        helper.setTo(recipient);
        helper.setSubject("Registration confirmation");

        String html = """
                <html>
                  <body>
                    <h1 style="color: #17653a;">Registration successful</h1>
                    <p>Your request has been recorded.</p>
                    <p>
                      <a href="https://learning.example.test/account"
                         style="background: #17653a;
                                color: white;
                                padding: 12px 20px;
                                text-decoration: none;">
                        View account
                      </a>
                    </p>
                  </body>
                </html>
                """;

        helper.setText(html, true);
        mailSender.send(message);
    }
}
~~~

The **true** parameter in **setText(html, true)** indicates that this string is **HTML** content. The library can then create a MIME part of type **text/html** with the corresponding charset. If set to **false**, the same HTML characters will be treated as plain text.

**MimeMessageHelper(message, false, "UTF-8")** in the example has **false** meaning only **do not create a multipart structure upfront**; it does not mean the helper can create only plain text. To distinguish properly, look at **the two flags in two different places**:

| Call | Meaning |
| --- | --- |
| **new MimeMessageHelper(message, false, "UTF-8")** | Create a non-multipart helper for a single main body |
| **helper.setText(html, true)** | The given body is HTML |
| **helper.setText(text, false)** | The given body is plain text |
| **new MimeMessageHelper(message, true, "UTF-8")** | Enable multipart structure support, which may be needed for complex content |

This is an easy point of confusion when moving from SimpleMailMessage to MIME: **multipart** and **HTML** are not synonyms. A simple HTML email can use a single text/html part; an email with a PDF can use multipart while its body is text/plain.

### HTML does not guarantee every design looks identical

The code above illustrates syntax, not an email template compatible with every client. In practice, mail applications support CSS differently; some may strip properties or alter layout. For production templates, test the clients, devices, and dark mode settings your users actually use.

In particular, an HTML email is not a regular interactive web page. JavaScript, complex forms, and certain CSS may be blocked or unsupported; do not build core functionality assuming the email client will run such code.

## 9. A good solution for formatted emails: multipart/alternative

When users need HTML content yet must still have a readable plain text version, a common option is creating **two equivalent versions** in the same message:

~~~text
MIME message
    |
    '-- multipart/alternative
          |
          +-- text/plain; charset=UTF-8
          |     "Registration confirmation. Visit https://..."
          |
          '-- text/html; charset=UTF-8
                <h1>Registration confirmation</h1>
                <a href="https://...">View account</a>
~~~

These are **two alternative representations of the same content**, not two different emails sent to the recipient. The mail reader picks the part suited to its capabilities or settings.

### Spring example: setText(plainText, htmlText)

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RegistrationAlternativeMailService {

    private final JavaMailSender mailSender;

    public RegistrationAlternativeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(
            String recipient,
            String code
    ) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                "UTF-8"
        );

        helper.setFrom("notifications@example.test");
        helper.setReplyTo("support@example.test");
        helper.setTo(recipient);
        helper.setSubject("Registration confirmation");

        String plainText = """
                REGISTRATION CONFIRMATION

                Registration code: %s

                View your account at:
                https://learning.example.test/account
                """.formatted(code);

        String htmlText = """
                <html>
                  <body>
                    <h1>Registration confirmation</h1>
                    <p>Registration code: <strong>%s</strong></p>
                    <p>
                      <a href="https://learning.example.test/account">
                        View account
                      </a>
                    </p>
                  </body>
                </html>
                """.formatted(code);

        helper.setText(plainText, htmlText);
        mailSender.send(message);
    }
}
~~~

**helper.setText(plainText, htmlText)** is the overload for two content versions. With this call, the helper needs to be in **multipart mode** to build the appropriate MIME structure. In the example, the constructor with **true** satisfies that requirement.

Notable characteristics:

- **Plain text** has the key information: registration code and the address to view the account.
- **HTML** has the same information, using headings, strong tags, and a labeled link.
- Both versions describe **one event**. Do not let them have different amounts, statuses, or URLs.
- JavaMailSender and Jakarta Mail handle creating the MIME structure and appropriate transfer encoding; the application does not have to Base64-encode the two text parts itself.

In the example, the **code** variable is system-generated data with a controlled format. If inserting arbitrary user data into **htmlText** via string interpolation, perform an **HTML escaping** step; the next section explains how.

### Not every HTML email has to have images or attachments

A message containing only plain text and HTML can already use **multipart/alternative** with no attachment needed. Conversely, a message with an inline logo or PDF usually needs nested MIME structures such as **multipart/related** and **multipart/mixed**. **MimeMessageHelper** helps build that structure without manually assembling boundaries.

## 10. Keep the plain fallback meaningful, not just a line saying "please enable HTML"

A quality plain text version needs to convey **all essential content**, rather than only:

~~~text
Please enable HTML to view this notification.
~~~

That line is unhelpful if the recipient uses a text-only mail reader, or if HTML is blocked in their access environment.

Suppose the HTML version has:

~~~html
<h2>Password reset request</h2>
<p>The link is valid for 15 minutes.</p>
<a href="https://accounts.example.test/reset/xyz">
  Reset password
</a>
~~~

The corresponding plain text version should be:

~~~text
PASSWORD RESET REQUEST

The password reset link is valid for 15 minutes.

Visit:
https://accounts.example.test/reset/xyz

If you did not request a password reset, please ignore this email.
~~~

In both versions, the user receives the same information about **purpose**, **expiration**, and **action URL**. The difference lies only in presentation. For tokenized links, generate a secure, expiring token per business logic and avoid unnecessary logging; having two MIME parts does not mean creating two different tokens.

### Should you automatically strip all HTML tags to create plain text?

A simple approach is stripping all HTML tags from a string and using the result as plain text. Yet that approach often loses:

- **Real link labels and URLs**: readers see only "View account" without the link.
- **Paragraph/list boundaries**: elements can run together.
- **Content carried by descriptive attributes**, such as informative alt text on images.
- **Table semantics**: column values can lose their relationship.

For important content, **author the plain text version deliberately** or use an HTML-to-text converter with clear rules, verified against real received messages. Both versions should be produced from the same **notification data model** to prevent divergence.

## 11. HTML content needs character escaping and URL validation

When switching to HTML, a new class of risk appears: data once treated as plain text can now be **interpreted as markup**.

Suppose the user's name is:

~~~text
Lan <Manager>
~~~

If placed directly into HTML:

~~~html
<p>Hello Lan <Manager></p>
~~~

the string **<Manager>** may be treated as a tag by the HTML processor, causing the content to display differently from intended. Likewise, data received from forms can contain special characters such as **&**, **"**, **<**, or **>**.

Spring provides the **HtmlUtils** class to escape text used as HTML content:

~~~java
import org.springframework.web.util.HtmlUtils;

String displayName = "Lan <Manager>";
String safeDisplayName = HtmlUtils.htmlEscape(
        displayName,
        "UTF-8"
);

String html = "<p>Hello " + safeDisplayName + "</p>";
~~~

When rendering HTML, the text is processed so special characters display as data rather than being interpreted as HTML structure. The **HtmlUtils** class belongs to Spring Web; if the application lacks that module, use an escaping solution suited to your template library.

**Do not call HtmlUtils.htmlEscape on an entire completed HTML template**, as doing so would cause even **<p>** and **<a>** tags to display literally. Escape **dynamic values** at the insertion point in HTML, or use a template engine with context-aware escaping.

### Escaping text differs from validating URLs

For an HTML link, care not only about visible text but also control **href**:

~~~html
<a href="https://accounts.example.test/confirm">Confirm email</a>
~~~

If a URL is constructed from user-entered data, restrict the scheme and domain per business rules, encode URL components properly, and escape HTML attribute values. **HTML escaping does not by itself turn a dangerous URL into a trustworthy URL**. Avoid letting recipients be redirected to arbitrary domains from uncontrolled data sources.

For transactional emails, using an HTTPS URL with a clear domain alongside an equivalent plain text version is usually easier to verify than building dynamic links via uncontrolled string concatenation.

## 12. If the email needs a logo or PDF, switch to multipart

When formatting requirements go beyond ordinary HTML, an email may need multiple MIME parts. A common structure is:

~~~text
multipart/mixed
 |
 +-- multipart/related
 |    |
 |    +-- multipart/alternative
 |    |    +-- text/plain
 |    |    '-- text/html
 |    |
 |    '-- image/png (inline, Content-ID)
 |
 '-- application/pdf (attachment)
~~~

This is a **conceptual diagram**; the exact multipart structure is determined by how the MIME message is built and library support. It shows the parts having distinct roles:

- **text/plain** is the readable content version when HTML is not used.
- **text/html** holds markup for the email client to render when supported.
- **image/png** can be a logo referenced by HTML via **cid:**.
- **application/pdf** is a file attached to the message, not text sitting in the body.

An example adding an attachment with Spring Mail:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class InvoiceMailSender {
    private final JavaMailSender sender;

    public InvoiceMailSender(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(String recipient, Path invoicePdf)
            throws MessagingException {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("billing@example.test");
        helper.setTo(recipient);
        helper.setSubject("Invoice");

        helper.setText(
                "The invoice is attached. Please see invoice.pdf.",
                "<p>The invoice is attached.</p>"
                    + "<p>Please see <strong>invoice.pdf</strong>.</p>"
        );

        helper.addAttachment(
                "invoice.pdf",
                new FileSystemResource(invoicePdf.toFile())
        );

        sender.send(message);
    }
}
~~~

In this example, **FileSystemResource** supplies PDF bytes from an actual file. The mail layer builds the MIME part for the attachment; **there is no need to convert the PDF to a Base64 string and put it in setText**.

When adding inline images, the helper has an **addInline(...)** method to associate a resource with a **Content-ID** referenced in HTML via **cid:**. With this API, you should normally set the HTML via **setText(...)** before calling **addInline(...)**, and match the CID between HTML and the name used in the helper.

Attachments increase total message size due to MIME encoding, headers, and multipart boundaries. A very large file may exceed SMTP/provider limits even if the file itself on disk is smaller than the threshold the user expects. For very large files, consider sending a **download link with access control and expiration** instead of embedding the file in every email.

## 13. HTML can format more, yet does not give absolute control

Moving from plain text to HTML expresses presentation intent more clearly. However, email clients are not full web browsers and do not share an identical rendering contract across every platform.

| Formatting need | Plain text | HTML email |
| --- | --- | --- |
| Paragraphs, character lists | Yes | Yes |
| Large headings, bold text, colors | Cannot control reliably | Can describe, but CSS support varies |
| Links with custom labels | Usually needs raw URL; auto-link depends on client | Uses **a** tag |
| Visual CTA buttons | Only simulated with characters | Can be styled with links and presentation rules |
| Multi-column tables | Space alignment drifts easily | Use HTML table structure if clients support it |
| Logos and images in body | Cannot embed directly | Can reference remote images or inline images |
| File attachments | Not via SimpleMailMessage | Needs MIME attachment; usable with plain text/HTML |
| Layout on small screens | Client wraps lines automatically | Can design responsively, though testing is needed |
| Complex JavaScript interactivity | No | Most email clients forbid running scripts like web pages |

When authoring HTML emails, consider:

- **Images may be blocked**: core content must not be placed solely inside an image.
- **Dark mode may alter colors**: check contrast when clients invert or adjust background/text colors.
- **CSS support varies**: do not treat Chrome output as proof the email will look identical everywhere.
- **Link buttons must have clear labels**: users must understand what they are opening.
- **Font size and spacing must remain readable** on small screens, when zoomed, and with accessibility tools.
- **Messages containing sensitive data** must comply with security policy; HTML does not make email content more confidential.

In other words, HTML **describes formatting intent**; the recipient still uses an email client that holds final authority over how it is rendered.

### Plain text is not necessarily less effective than HTML

For short notifications, OTP codes, or technical instructions, a clean and clear plain text email sometimes delivers a better experience than a heavy HTML template. It reduces template maintenance and depends less on CSS/images.

There is no universal rule that "sending HTML always lands in the Inbox better" or "sending plain text always avoids spam". Deliverability depends on many other factors such as sender reputation, domain authentication, recipient list, content, and provider policies. Choose HTML or plain text primarily based on **content and experience needs**, not using Content-Type as a trick to guarantee inbox placement.

## 14. Design content first, choose format second

A common design mistake is writing HTML first, and then trying to cram HTML into SimpleMailMessage when reusing a mail-sending function. A cleaner approach is separating them:

~~~text
Business event
   |
   v
Validated notification data
   |  recipient, title, orderId, total, targetUrl
   v
Render content
   |
   +-- Plain renderer -> text/plain
   |
   '-- HTML renderer  -> text/html
   |
   v
Mail sender
   |
   +-- Text only -> SimpleMailMessage or MIME text/plain
   |
   '-- HTML / alternative / attachment -> MimeMessage
   |
   v
SMTP provider
~~~

This way, **format does not dictate business data**. An order notification with total amount, order ID, deadline, and URL is produced once from business data; renderers merely present them differently.

### Example of the same data, two display forms

Input data:

~~~text
orderId = ORD-1528
total = 600.000 VND
url = https://orders.example.test/ORD-1528
~~~

Plain text:

~~~text
ORDER HAS BEEN CONFIRMED

Order ID: ORD-1528
Total: 600.000 VND

View order:
https://orders.example.test/ORD-1528
~~~

HTML:

~~~html
<h2>Order has been confirmed</h2>
<p><strong>Order ID:</strong> ORD-1528</p>
<p><strong>Total:</strong> 600.000 VND</p>
<p>
  <a href="https://orders.example.test/ORD-1528">
    View order
  </a>
</p>
~~~

Both displays convey the exact same content. When updating status or amount, changing the shared data prevents inconsistencies between the two versions.

### Do not put mandatory information solely in images or CSS

If an HTML email uses a green icon to convey "success", plain text users or email clients blocking images may miss the status. Instead of relying solely on an icon, write explicitly:

~~~text
Status: PAYMENT SUCCESSFUL
~~~

Similarly, to convey an error, do not rely only on red text. Use a label such as **"Failed"**, along with the reason and required next step. Both versions should use wording that makes sense independently of color.

## 15. Testing email must reflect how clients receive MIME

Because plain text and HTML have different display mechanisms, merely printing **mail.getText()** to the console does not prove the email will be received and rendered properly. A testing process can include:

1. **Inspect the message actually produced** through a controlled SMTP test sink or mail capture, never using real customer addresses.
2. **Check the MIME structure**: is the message plain text only, or does it contain **multipart/alternative**, **text/html**, inline images, and attachments as expected?
3. **Read the plain text part**: does the user have enough content, URLs, and action steps without HTML?
4. **Open the HTML part** on target clients, including small screens and image-blocking settings.
5. **Check Vietnamese/Unicode**: charset and transfer encoding must preserve diacritics accurately without showing literal QP or Base64 codes.
6. **Check links, alt text, and contrast**: users must understand and reach the primary action.
7. **Check size limits** when HTML, images, and attachments make the message larger.

To view the raw email, look for headers such as:

~~~text
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="alt-example"

--alt-example
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xem t=C3=A0i kho=E1=BA=A3n: https://learning.example.test/account

--alt-example
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xem t=C3=A0i kho=E1=BA=A3n:
<a href=3D"https://learning.example.test/account">M=E1=BB=9F</a></p>

--alt-example--
~~~

This is a **abbreviated example** to illustrate multipart and quoted-printable. Compliant mail readers decode each part and choose the version to display. The **=3D** in raw HTML is the **=** character encoded in quoted-printable; it does not mean the HTML is broken.

In real content, MIME parts may be ordered/nested differently when attachments or inline images are present. Let Jakarta Mail generate boundaries and content transfer encoding, avoiding assembling raw MIME manually via string concatenation.

## 16. Common misconceptions when moving from simple mail

### Misconception 1: "Putting HTML tags in setText makes the email look nicer"

With **SimpleMailMessage**, **setText** creates plain text. HTML tags are literal characters displayed to the reader, not elements for the client to render. To use HTML, create a MimeMessage and call **MimeMessageHelper.setText(html, true)**.

### Misconception 2: "To get bold text, use Markdown"

Emails with MIME type **text/plain** have no standard mechanism to turn **\*\*** into bold text. When emphasis is needed, use clear wording and structure in plain text; when real typography is needed, use HTML.

### Misconception 3: "Just add newlines and spaces to get a neat table"

Space-based column alignment depends on fonts, screen width, and how clients wrap lines. For content that must be laid out in columns, use a compatibility-tested HTML table or an appropriate attachment; do not rely on ASCII tables to guarantee layout.

### Misconception 4: "An image path in text will get embedded into the email"

A local file path or URL is just a string of characters when put into text/plain. For inline images, you need MIME/HTML and image resources referenced in a way email clients support. Even then, recipients may block image loading.

### Misconception 5: "Enabling multipart automatically gives HTML"

Multipart describes a **multi-part structure**; it does not decide on its own that the content is HTML. **MimeMessageHelper.setText(html, true)** or the **setText(plain, html)** overload expresses the intent to create an HTML body.

### Misconception 6: "If you use HTML, you don't need plain text"

An HTML version can display fine on many clients, yet having an equivalent plain text version helps text-limited readers or users who prefer plain text still access the content. In emails with mandatory actions, the plain fallback should include a working URL and instructions.

### Misconception 7: "HTML always looks as good as a web page"

Email clients may block images, strip certain CSS, or alter colors. Templates must be built for the email environment and tested on target clients. Do not depend on JavaScript, complex CSS, or web-like interactive effects.

### Misconception 8: "Sending with MimeMessage means the user definitely viewed the HTML"

MimeMessage only describes and sends the content. Email clients may select the plain part, block HTML/images, or apply custom policies. A successful **JavaMailSender.send(...)** likewise reflects only the sending status at the application/transport layer, not proof that the email was rendered or read.

## 17. Choosing a solution by requirement

| Business requirement | Suitable approach | Reason |
| --- | --- | --- |
| OTP code, short notice, character-only content | **SimpleMailMessage** | Minimal structure, easy to read |
| Message with a few paragraphs, labels, and full URL | **SimpleMailMessage** or MIME plain text | No complex markup needed yet |
| Branded message with headings, colors, labeled CTA | **MimeMessage** containing **text/html** | Needs HTML semantics to express presentation styling |
| HTML message that must remain readable when HTML is unavailable | **multipart/alternative** via MimeMessageHelper | Provides equivalent plain + HTML |
| Inline logo inside HTML | MIME with **related** parts and Content-ID | Image is a separate resource |
| Attached PDF, CSV, document | MIME with **attachment** | File is bytes/resource, not a text string |
| Invoice table needing fixed layout for saving/printing | PDF attachment or link to document | Keeps document layout independent of the email client |
| Email carrying very large data | Controlled download link instead of embedding all | Avoids size limits and MIME overhead |

Options can be combined. For example, an invoice email can have **plain + HTML** in the body and a **PDF attachment**. When only a simple notification is needed, using SimpleMailMessage remains completely reasonable.

## 18. Self-check with scenarios

**Scenario A — The user must see a red heading and bold amount.**  
Does SimpleMailMessage meet this directly?

No. It uses text/plain. You can express emphasis using readable labels in text, yet expressing color/bold intent requires HTML MIME, while still accepting differences across email clients.

**Scenario B — The message contains Markdown: \*\*Important\*\*.**  
Is it guaranteed to display in bold?

No. In text/plain, asterisks are ordinary characters. Do not rely on a mail client having a custom Markdown renderer.

**Scenario C — Need to send a PDF file while keeping the body plain text.**  
Is an HTML body mandatory?

No. Using a multipart MimeMessage with a **text/plain** part and an **application/pdf** attachment part is sufficient. MIME attachments do not require the body to be HTML.

**Scenario D — Since we already have nice HTML, make plain text say only "please enable HTML".**  
Is this a good fallback?

No. The plain fallback should contain the essential information and actions. For a confirmation button in HTML, the plain version needs the full URL and clear instructions.

**Scenario E — A URL in plain text does not automatically become a clickable link.**  
Did Spring send it wrongly?

Not necessarily. Auto-detecting URLs to turn them into links is email client behavior. In plain text, show the full URL; if you need a link with a specific label and layout, use HTML.

**Scenario F — An HTML email renders fine in a browser but breaks on mobile.**  
Where should you fix it?

Inspect the HTML email template, CSS support, and responsive rules of target clients. Do not infer web-like HTML email compatibility from a Chrome preview.

**Scenario G — Using MimeMessageHelper.setText(html, false).**  
Why do recipients see literal HTML tags?

The **false** parameter of **setText** tells the helper that the body is plain text. To use HTML, pass **true** or use the **plainText, htmlText** overload in multipart mode.

**Scenario H — Switching Vietnamese content to HTML to fix corrupted diacritics.**  
Is changing Content-Type like that enough?

Not necessarily. If the bug is in the charset or input bytes, HTML can still render incorrectly. Check UTF-8, MIME headers, and the data conversion pipeline; **having HTML** and **having valid Unicode** are two separate issues.

## 19. Principles to remember

~~~text
Email needs only characters, paragraphs, lists, clear URLs?
    -> SimpleMailMessage / text/plain

Need headings, colors, bold text, labeled CTAs, tables?
    -> MimeMessage + text/html

Need both a readable version and a formatted version?
    -> MimeMessage + multipart/alternative
       text/plain + text/html

Need inline images or file attachments?
    -> MimeMessage + appropriate MIME parts

Content contains Vietnamese?
    -> Use an appropriate charset, usually UTF-8
       Do not confuse encoding with formatting capability

Need a guaranteed document-like layout for printing/saving?
    -> Consider PDF or a separate downloadable document
~~~

**The core limitation of plain text is that it conveys content through characters and does not carry a rich layout description language like HTML.** With Spring Framework Mail, **SimpleMailMessage** is the right tool for simple, clear messages. When presentation requirements exceed what text/plain can do, use **MimeMessage/MimeMessageHelper** to produce HTML, multipart/alternative, and attachments semantically, while keeping a useful plain text version for accessibility and compatibility.
