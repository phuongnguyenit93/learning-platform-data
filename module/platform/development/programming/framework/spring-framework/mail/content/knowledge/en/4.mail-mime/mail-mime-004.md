# multipart/alternative for plain text and alternative HTML

## 1. What problem does multipart/alternative solve?

Modern emails often have two representations of the same content:

- **Plain text**: unformatted text, without HTML tags or complex styling. Readers can still see the content in text-only email clients, when HTML rendering is disabled, or in certain mail inspection tools.
- **HTML**: content with headings, paragraphs, links, layout, colors, and formatting, suited for HTML-capable email clients.

If you send only HTML, clients that do not support or prefer not to render HTML may find the message inconvenient to read. If you send only plain text, the application misses out on rich visual presentation. The **MIME (Multipurpose Internet Mail Extensions)** standard solves this need with the **multipart/alternative** content type.

An email with **multipart/alternative** contains multiple parts (*body parts*) that are **alternative representations of the same message**. The most common case is two parts: **text/plain** and **text/html**. The email client chooses one suitable representation to display; the recipient should not interpret these as two separate emails or two sections to be read sequentially.

In **Spring Framework Mail**, we typically build this kind of email using **JavaMailSender** and **MimeMessageHelper**. An especially important method overload is **MimeMessageHelper.setText(plainText, htmlText)**: it supplies the two corresponding payloads so the helper constructs the alternative MIME parts.

## 2. MIME is the content representation layer, not the transport protocol

It is important to distinguish:

| Component | Role |
|---|---|
| **SMTP** | Transfers messages from the client to the sending server and between mail servers. |
| **MIME** | Describes email content structure: media type, encoding, multiple parts, attachments, and relationships among them. |
| **text/plain** | Represents content as plain text. |
| **text/html** | Represents content using HTML. |
| **multipart/alternative** | Groups *mutually alternative* versions of the same content. |
| **JavaMailSender** | Spring interface for sending email messages, including MimeMessage. |
| **MimeMessageHelper** | Spring utility that helps construct MimeMessage structure and MIME parts. |

A Spring application builds a **MimeMessage**, while whether the email passes through the SMTP server successfully is a separate transport concern. A message with valid MIME structure can still be rejected by SMTP, hit domain authentication errors, or land in Spam.

### Why is it called alternative?

Imagine an account confirmation notification. The content might look like this:

**Plain text version**

~~~text
Hello!

Your account has been created successfully.
Please visit https://example.com/account to view your details.

Best regards,
Support Team
~~~

**HTML version**

~~~html
<!doctype html>
<html lang="en">
  <body>
    <h2>Hello!</h2>
    <p>Your account has been created successfully.</p>
    <p>
      Please visit your
      <a href="https://example.com/account">account page</a>
      to view your details.
    </p>
    <p>Best regards,<br>Support Team</p>
  </body>
</html>
~~~

The two versions carry **the same core information**; only the presentation differs. When an email client supports HTML, it usually chooses the HTML version; when it does not, it can choose the plain text version.

This is **not a mechanism that detects broken HTML and automatically falls back to fix HTML**. Selection depends on the email client, user preferences, and MIME support. If the HTML has rendering bugs, many clients may still pick the HTML part. Therefore, both versions must be authored completely and remain usable independently.

## 3. MIME structure of multipart/alternative

Example of an email with two content options, shown in raw MIME form:

~~~text
From: no-reply@example.com
To: user@example.net
Subject: Account notification
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="alt_001"

--alt_001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Your account is ready.
Open https://example.com/account to view it.

--alt_001
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<html>
  <body>
    <p>Your account is ready.</p>
    <p><a href="https://example.com/account">View your account</a></p>
  </body>
</html>

--alt_001--
~~~

The example uses ASCII content to illustrate **Content-Transfer-Encoding: 7bit**. For Vietnamese or other Unicode characters, the sending library can choose an appropriate transfer encoding, such as quoted-printable or base64, along with UTF-8 charset. You should not manually set 7bit for content containing non-ASCII UTF-8 bytes.

### Explaining each part

1. **MIME-Version: 1.0** announces that the message uses MIME structure.
2. **Content-Type: multipart/alternative** states that the body consists of alternative representations.
3. **boundary="alt_001"** defines the string separating the parts. In real emails, the library usually generates a unique boundary automatically; the example just uses a readable name.
4. **--alt_001** opens each part.
5. Each part has its own **Content-Type**, such as text/plain or text/html.
6. **--alt_001--** with two trailing hyphens closes the multipart.

You should not build MIME strings via manual text concatenation in production. Jakarta Mail and Spring libraries handle boundaries, encoding, headers, and nested structures more reliably.

### Order of parts matters

By MIME convention for **multipart/alternative**, parts are ordered from the **least preferred representation to the most preferred representation**; when multiple options can be rendered, the client usually picks **the last supported part**.

Thus, the common pair has the order:

~~~text
multipart/alternative
├── text/plain    (basic representation)
└── text/html     (richer representation, usually preferred)
~~~

This does not force every email client to always display HTML: some clients or users may prefer plain text for accessibility, safety, or personal policy. The key design point is that **both parts must contain the same main information and preserve the actions the reader needs to take**.

## 4. Comparing multipart/alternative with mixed and related

Three subtypes commonly appearing in multi-part emails:

| MIME type | Relationship between parts | Example |
|---|---|---|
| **multipart/alternative** | Parts are **alternative versions** of the same content. | text/plain and text/html of a notification email. |
| **multipart/mixed** | Parts are **components that belong together**, typically a body and attachments. | Email body with report.pdf. |
| **multipart/related** | Parts have a **referential relationship**, typically used for HTML and inline resources. | HTML email referencing a logo image via Content-ID (cid). |

Choosing the right subtype helps email clients interpret the message structure:

- Use **alternative** when the recipient should pick **one of several ways to present the same message**.
- Use **mixed** when the message consists of primary content **and** one or more attachments.
- Use **related** when the HTML part needs associated resources, such as images embedded inline.

A complex email can **nest multiple subtypes** rather than picking a single subtype for the entire message.

## 5. Creating plain text + HTML with Spring Framework Mail

Spring Mail provides a direct helper method:

~~~java
MimeMessageHelper.setText(String plainText, String htmlText)
~~~

The method is called on the helper object; the two strings must represent the same content. This is a different overload from **setText(String text, boolean html)**, which only specifies whether a single content part is plain text or HTML.

### Complete example using JavaMailSender

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class AccountNotificationMailService {

    private final JavaMailSender mailSender;

    public AccountNotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAccountReady(String recipient) throws MessagingException {
        String plainText = """
                Hello!

                Your account is ready.
                Visit https://example.com/account to view your details.

                Best regards,
                Support Team
                """;

        String htmlText = """
                <!doctype html>
                <html lang="en">
                  <body>
                    <h2>Hello!</h2>
                    <p>Your account is ready.</p>
                    <p>
                      <a href="https://example.com/account">
                        Visit your account page
                      </a>
                      to view your details.
                    </p>
                    <p>Best regards,<br>Support Team</p>
                  </body>
                </html>
                """;

        MimeMessage mimeMessage = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your account is ready");
        helper.setText(plainText, htmlText);

        mailSender.send(mimeMessage);
    }
}
~~~

The example uses a Java text block (compatible with Java 21) and assumes the application has configured a **JavaMailSender** bean and an outgoing mail server.

### Why pay attention to each line?

**mailSender.createMimeMessage()**: creates a MIME message using JavaMailSender's configuration.

**new MimeMessageHelper(mimeMessage, true, "UTF-8")**: enables multipart mode so the helper can construct multiple content parts. In this constructor, **true** requests multipart; the encoding parameter allows handling Vietnamese Unicode text appropriately.

**helper.setText(plainText, htmlText)**: creates two alternative representations. The helper builds the appropriate MIME structure, including a **multipart/alternative** for these two payloads.

**mailSender.send(mimeMessage)**: sends the prepared message to the mail infrastructure. A successful return from this call does not guarantee the message lands in the Inbox; subsequent delivery steps are the responsibility of the email ecosystem.

**Note on the actual MIME tree:** When creating MimeMessageHelper with **multipart=true**, Spring may create an outer wrapping multipart structure (such as mixed/related) and place the alternative section inside. Therefore, you should not require the **root Content-Type** to always be multipart/alternative. What to look for is **having both text/plain and text/html parts grouped under an alternative relationship**.

### Easily confused setText overloads

| Call | Expected result |
|---|---|
| **helper.setText("Hello")** | A single plain text content part. |
| **helper.setText("<p>Hello</p>", true)** | A single HTML content part; does not auto-generate a full plain text version. |
| **helper.setText(plainText, htmlText)** | Two alternative representations, typically placed inside multipart/alternative. |

To use the two-string overload, the helper must be initialized in **multipart mode**. Creating the helper in single-part mode and calling this overload can fail because there is no multipart structure to hold the alternatives.

## 6. Configuration in Spring Boot

For a Spring Boot application, the commonly used dependency is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Depending on the SMTP provider, you can configure **application.yml**:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: account@example.com
    password: REPLACE_WITH_SECRET
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
~~~

This is an illustrative configuration, not a real server address or account. In a real application, credentials must come from environment variables or a secrets manager; **never commit SMTP passwords to a repository**.

Spring Boot helps wire the mail-sending bean from appropriate configuration. The **multipart/alternative** structure, however, is a property of **MimeMessage content**, created when constructing the email, not an SMTP host or network port option.

## 7. When does the MIME structure become nested?

Suppose the application sends an invoice containing plain text, HTML, and a PDF file. The two content representations remain alternative, while the PDF is an accompanying attachment:

~~~text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
└── application/pdf (attachment)
~~~

If the HTML references a logo image embedded directly in the email, the relationship between HTML and the image may require **multipart/related**. A typical structure:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html (references cid:brandLogo)
│   └── image/png (inline, Content-ID: brandLogo)
└── application/pdf (attachment)
~~~

The exact structure depends on how the message is constructed and the library's compatibility policies. The diagram shows **semantic relationships**: plain text and HTML are alternatives; the inline image depends on HTML; the attachment accompanies the whole email.

### Spring Mail example adding an attachment

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.io.File;
import java.nio.charset.StandardCharsets;

public void sendInvoice(
        JavaMailSender sender,
        String recipient,
        File invoicePdf
) throws Exception {
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("billing@example.com");
    helper.setTo(recipient);
    helper.setSubject("Your invoice");
    helper.setText(
            "Hello! The PDF invoice is attached to this email.",
            "<p>Hello!</p><p>The PDF invoice is attached to this email.</p>"
    );

    helper.addAttachment("invoice.pdf", invoicePdf);
    sender.send(message);
}
~~~

The example assumes **invoicePdf** is an existing PDF file permitted to be sent. In real code, enforce file size limits, handle file errors with specific exception types, and avoid including sensitive files without corresponding protection mechanisms.

For inline images, you can use **helper.addInline(contentId, resource)** after preparing HTML content referencing **cid:contentId**. Inline resources belong to the **related** relationship, not as a third text alternative.

## 8. When exact multipart/alternative at the root level is needed

**MimeMessageHelper** is optimized for building common emails and may create outer wrapping multipart layers. When a specific requirement demands that the exact **root Content-Type be multipart/alternative**, Jakarta Mail lets you build the MIME tree manually.

Example using Jakarta Mail types:

~~~java
import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;
import org.springframework.mail.javamail.JavaMailSender;

public void sendExactAlternative(
        JavaMailSender sender,
        String recipient
) throws Exception {
    MimeMessage message = sender.createMimeMessage();
    message.setFrom(new InternetAddress("no-reply@example.com"));
    message.setRecipient(
            Message.RecipientType.TO,
            new InternetAddress(recipient)
    );
    message.setSubject("Notification", "UTF-8");

    MimeBodyPart plainPart = new MimeBodyPart();
    plainPart.setText("Hello! Your account is ready.", "UTF-8");

    MimeBodyPart htmlPart = new MimeBodyPart();
    htmlPart.setContent(
            "<html><body><p>Hello! Your account is ready.</p></body></html>",
            "text/html; charset=UTF-8"
    );

    MimeMultipart alternatives = new MimeMultipart("alternative");
    alternatives.addBodyPart(plainPart);
    alternatives.addBodyPart(htmlPart);

    message.setContent(alternatives);
    sender.send(message);
}
~~~

Here the parts are added in the order **plain first, HTML second**, and **message.setContent(alternatives)** attaches multipart/alternative directly as the main content. This example serves to understand MIME; unless there is a special structural requirement, prefer **MimeMessageHelper** to reduce manual code.

## 9. Writing two versions so they are equivalent

A common content mistake is having full information in HTML while plain text only says “Please enable HTML to view this email”. That defeats the purpose of **alternative**: users who choose plain text cannot complete the necessary task.

The two versions should have:

- **The same main message**: result, notification, status, or transaction details.
- **The same important actions**: if HTML has a confirmation button, plain text must have the corresponding URL or instructions.
- **The same required information**: order ID, deadline, support contact, key terms if relevant.
- **Independent readability**: plain text has clear line breaks, whitespace, and layout; HTML uses clean headings, paragraphs, and links.
- **No conflicting information**: prices, quantities, expiration dates, tokens, and URLs must not differ between the two versions.

Confirmation email example:

| Content to preserve | Plain text | HTML |
|---|---|---|
| Greeting | “Hello” line | p or h2 tag |
| Description | Text lines | p paragraphs |
| Confirmation button | Full copyable URL | Anchor link with descriptive label |
| Contact info | Clear email address or URL | mailto link or support page |
| Deadline | Clear sentence | Sentence with optional emphasis formatting |

Do not assume plain text content can use Markdown syntax and have the email client convert it to HTML automatically. Asterisks, hyphens, and Markdown link syntax usually appear as literal characters inside a **text/plain** part.

### Handling dynamic data and content safety

If an email contains user names or data from untrusted sources, **escape data when inserting into HTML** to prevent unwanted tags/attributes from breaking the message structure. Encode and construct URLs properly, especially URLs containing tokens. When building HTML from templates, use the template engine's escaping mechanism or equivalent rules; never concatenate user data directly into HTML attributes.

Many email clients strip JavaScript and unsupported CSS, so email HTML should be simple, clearly structured, and not depend on scripts to render important content. Images can be blocked; provide **alt text** and never put essential information inside images alone.

If an email contains verification codes, password-reset tokens, or personal data, both versions must be protected accordingly. Do not log full MIME bodies in production logs, and do not let URLs with tokens appear in unprotected error reports.

## 10. Charset, Content-Transfer-Encoding, and Vietnamese

Two frequently confused concepts:

**charset** in Content-Type, such as **charset=UTF-8**, tells how to interpret bytes into characters. This is why applications need UTF-8 to display accented Vietnamese accurately.

**Content-Transfer-Encoding**, such as **quoted-printable** or **base64**, specifies how content bytes are encoded to fit the email transport wire. This is not a “security encryption” method or a way to hide content from anyone with access.

For example, a plain text part may have headers:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

Jakarta Mail usually chooses a suitable transfer-encoding mechanism when writing the message. At the application layer, focus on supplying valid Unicode strings, declaring the right charset, and letting the library handle MIME encoding. Manually crafting a raw email with Vietnamese text while declaring **7bit** improperly can cause sending/receiving systems to render incorrectly.

Beyond the body, a **Subject** containing Vietnamese must also be validly encoded according to email header standards; use Jakarta Mail or MimeMessageHelper APIs instead of concatenating raw headers manually.

## 11. Common errors when building alternative in Spring

| Symptom | Common cause | How to resolve |
|---|---|---|
| Email only shows HTML; plain text readers lack proper content | Only called **setText(html, true)** | Create plain text and call the **setText(plain, html)** overload. |
| HTML appears as raw tag characters | HTML content was placed in text/plain | Use **setText(html, true)** for a single HTML part or the two-string overload for alternative. |
| Error when calling the two-string overload | Helper was not initialized in multipart mode | Create **MimeMessageHelper** with multipart=true or an appropriate multipart mode. |
| Vietnamese text has broken accents | Wrong charset or manual raw MIME construction | Use UTF-8 and MIME APIs to encode content. |
| Email with attachment renders two content parts strangely | MIME tree fails to distinguish alternative from mixed/related | Keep plain and HTML in alternative, attachments in mixed, and inline images in related. |
| Plain text lacks action link | Content was written only for HTML | Add the corresponding URL and instructions to plain text. |
| HTML renders differently across clients | CSS/HTML not uniformly supported, images blocked | Use simple email HTML, complete plain text, and test on target clients. |
| SMTP returns errors or mail goes to Spam | Authentication, DNS, policy, reputation, or transport issues | Investigate SMTP/ESP and receiving systems; alternative only concerns content representation. |

An easily overlooked point: **multipart/alternative is not a mechanism for sending an email twice**. There is only one MIME message containing multiple representation choices inside. If a recipient receives two separate emails, check send invocations, queues, retries, or duplicate business events rather than blaming the creation of both plain and HTML.

## 12. How to inspect an alternative email

In development, you can send to an SMTP test inbox or test mail server and open **raw message / show original** to inspect the MIME. An email built with a multipart helper may show a nested tree; look for **multipart/alternative** along with the two branches **text/plain** and **text/html**.

Things to examine when investigating:

1. Whether **Content-Type** has the right semantics across parts.
2. **Order**: text/plain appears before text/html inside alternative.
3. **Charset**: Vietnamese strings display properly.
4. **Content equivalence**: both versions carry the same essential information and URLs.
5. **Attachments and inline**: reasonable mixed/related relationships, not mistaken for alternative versions.
6. **Client behavior**: renders HTML properly and remains readable in plain text when the client prefers plain text.

Inspecting raw MIME should be restricted to test environments or data-protected tools, since raw messages can contain recipient addresses, tokens, and personal data.

### Email client decision diagram

~~~text
            Receive a MimeMessage
                     |
                     v
       Read multipart/alternative structure
                     |
             +-------+-------+
             |               |
    Supports/prefers HTML?  Selects plain text only?
             |               |
             v               v
      Display text/html    Display text/plain
             |               |
             +-------+-------+
                     |
                     v
        User sees the same core information
~~~

The diagram is a simplified visualization. In practice, clients choose based on supported formats, MIME preference order, and user settings; there is no guarantee that all clients follow identical rendering rules.

## 13. Conclusion

**multipart/alternative** is the MIME mechanism for delivering **plain text and HTML as two alternative representations of the same email**. In typical usage, order **text/plain first, text/html second**, keep essential content equivalent, and let the email client pick the appropriate option.

With Spring Framework Mail, **JavaMailSender** creates/sends MimeMessage and **MimeMessageHelper.setText(plainText, htmlText)** builds the alternative parts. When attachments or inline images are present, combine **multipart/mixed** and **multipart/related** properly at nested levels. Treat plain text as a complete, independently usable version—not merely a sentence telling the recipient to turn on HTML.
