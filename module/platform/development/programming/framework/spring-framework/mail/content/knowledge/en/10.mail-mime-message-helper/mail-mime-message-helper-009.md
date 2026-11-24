# Adding inline resources with Content-ID

When sending an HTML email with Spring Framework Mail, you may want the recipient to see a **logo, chart, or illustration right inside the message body**. A common approach is to package the image into the email message itself as a MIME part, assign that part a **Content-ID**, and reference it from HTML using an address starting with **cid:**.

In Spring, **MimeMessageHelper.addInline(...)** is the API that performs this operation. Instead of writing MIME headers, Content-ID, boundaries, and image encoding by hand, the application provides the identifier along with the data source; Spring Mail and Jakarta Mail build the message structure for SMTP transport.

Core example:

~~~html
<img src="cid:companyLogo" alt="Company logo">
~~~

~~~java
helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

The string **companyLogo** must match between the HTML and the addInline call. If they match, the email client can locate the MIME part containing the image and display it at the position of the img tag. This is a **relationship between the HTML content and a resource residing inside the same email**, not a public image address on the Internet.

This lesson explains Content-ID, the **multipart/related** structure, the multipart modes of MimeMessageHelper, a complete Java example, combining inline images with attachments, handling multiple images, and compatibility limits when sending real mail.

## 1. How does an inline resource differ from an attachment?

An email containing a message and an attached file is usually pictured like this:

~~~text
Email
├── Content: "Please see the report"
└── report.pdf (attached file)
~~~

The file **report.pdf** is a standalone document. The recipient can open or download it from the attachment list.

With an inline image, the intent is different:

~~~text
Email
└── HTML content
    ├── "Welcome!"
    ├── [Logo displayed here]
    └── "Thank you for registering."
~~~

The image is a **resource serving the display of the HTML content**, not merely a document sent along. At the MIME layer, the image is still data in a separate part, but the HTML knows how to find that part via Content-ID.

| Criterion | Inline resource | Attachment |
| --- | --- | --- |
| Goal | Display inside HTML at a specific position | Let the user view or download a separate file |
| Spring Mail API | **addInline(...)** | **addAttachment(...)** |
| Key link | **Content-ID** and **cid:** | Filename, MIME type, disposition |
| Common disposition | **inline** | **attachment** |
| Common MIME container | **multipart/related** | **multipart/mixed** |
| Example | Logo, QR image, chart in the message | PDF, CSV, ZIP |

An email client may still list inline images in the attachments area. That can be the client's own display choice. The distinction here is the **purpose and MIME structure** that the application creates.

## 2. How do Content-ID and cid: work?

**Content-ID** is a header field of a MIME part. It provides an identifier so that other content can reference that part.

Example of the image's MIME part:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-Disposition: inline
Content-ID: <companyLogo>

[base64-encoded-PNG-data]
~~~

The HTML has:

~~~html
<img src="cid:companyLogo" alt="Company logo">
~~~

When the client processes the HTML, it recognizes the **cid:companyLogo** URL and searches for the part with **Content-ID: <companyLogo>** in the message.

### 2.1. Why does Content-ID have angle brackets while cid: does not?

In MIME headers, Content-ID is usually represented by a value enclosed between **<** and **>**:

~~~text
Content-ID: <companyLogo>
~~~

But when calling the helper, you pass only the **logical identifier**:

~~~java
helper.addInline("companyLogo", resource, "image/png");
~~~

And in HTML:

~~~html
<img src="cid:companyLogo">
~~~

Spring Mail handles the required header formatting. **Do not pass angle brackets** into addInline's contentId parameter and let the library wrap another layer around them.

### 2.2. Content-ID is not a filename

Suppose the file resides at:

~~~text
src/main/resources/mail/brand-logo-2026.png
~~~

But you call:

~~~java
helper.addInline(
        "headerLogo",
        new ClassPathResource("mail/brand-logo-2026.png"),
        "image/png"
);
~~~

The HTML must use:

~~~html
<img src="cid:headerLogo" alt="Logo">
~~~

Not **cid:brand-logo-2026.png** unless you actually used that string as the Content-ID. The filename describes the source data; Content-ID is the linking key between the MIME part and the HTML section.

### 2.3. Does Content-ID need to be unique?

Each distinct image referenced in the same message should have **its own Content-ID**. If two different parts share the same identifier, the client may not know which part to display.

Short examples like **logo** or **chart** are commonly used in Spring guides. For systems needing identifiers with broader uniqueness scope, you can use a Content-ID value in valid message-id form, for example **logo.20261112@example.org**. In that case, the reference in HTML must use the exact identifier and URL-encode it if there are characters requiring percent-encoding.

Content-ID is readable metadata in the email, **not a secret token**, authentication mechanism, or access-control constraint.

### 2.4. cid: differs from HTTPS image URLs

Compare:

~~~html
<!-- Image resides inside the same MIME message -->
<img src="cid:companyLogo" alt="Logo">

<!-- Image stored on an external server -->
<img src="https://assets.example.org/images/logo.png" alt="Logo">
~~~

A **cid:** image is transported along with the email; an **https:** image requires the client to fetch it from another server when it decides to display it. Many email clients restrict loading remote content for privacy. However, that does not mean CID images are always displayed: the client can still block images or handle MIME differently.

## 3. Why do inline images need MIME multipart?

A message with only **text/html** does not automatically contain image data just because an img tag appears:

~~~html
<img src="cid:companyLogo">
~~~

If no MIME part with the matching Content-ID exists, the img tag has no resource to load.

MIME allows one message to contain multiple parts:

~~~text
MimeMessage
└── multipart/related
    ├── text/html
    │   └── <img src="cid:companyLogo">
    └── image/png
        ├── Content-ID: <companyLogo>
        ├── Content-Disposition: inline
        └── PNG data
~~~

Here:

- **text/html** is the main content.
- **image/png** is the related resource.
- **multipart/related** expresses the relationship between the two parts.
- **Content-ID** connects the image with the cid: reference in HTML.

### 3.1. multipart/related differs from multipart/mixed

**multipart/mixed** is usually used to combine independent components such as a message and attached files. **multipart/related** indicates that the parts together form a unified content, such as HTML and images.

If there are both an inline image and a downloadable PDF:

~~~text
multipart/mixed
├── multipart/related
│   ├── text/html
│   │   └── cid:companyLogo
│   └── image/png
│       └── Content-ID: <companyLogo>
└── application/pdf
    └── Content-Disposition: attachment
~~~

Thus, the logo is a resource of the HTML, whereas the PDF is a standalone attachment.

### 3.2. A message with multiple MIME parts is still one email

Calling **addInline** does not require creating an additional separate SMTP transaction for each image. The application builds **one MimeMessage** containing the body and parts, and then **JavaMailSender.send(...)** hands the entire message to the SMTP transport.

The number of MIME parts differs from the number of emails or recipients. One message can contain three inline images yet be sent to only one person; or contain one image yet be sent to multiple recipients per the SMTP envelope.

### 3.3. Base64 enables carrying binary data

PNG, JPEG, or GIF are binary data. When packaged as a MIME part, they are usually represented using **Content-Transfer-Encoding: base64**.

**Base64 is an encoding method to represent data for transport**, not security encryption. Anyone authorized to view the email content can decode it and obtain the image bytes.

Encoding increases the message size; therefore large inline images can push the email past SMTP limits or recipient filters.

## 4. Multipart modes of MimeMessageHelper

**MimeMessageHelper** supports these modes upon initialization:

| Mode | Main meaning |
| --- | --- |
| **MULTIPART_MODE_NO** | Multipart not enabled |
| **MULTIPART_MODE_MIXED** | Uses multipart/mixed root |
| **MULTIPART_MODE_RELATED** | Uses multipart/related root |
| **MULTIPART_MODE_MIXED_RELATED** | Mixed root with nested related branch |

For HTML emails containing inline images, **MULTIPART_MODE_RELATED** expresses the HTML–image relationship directly.

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        mimeMessage,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);
~~~

When an email has HTML, inline images, and attachments, the **MIXED_RELATED** mode is usually suitable:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        mimeMessage,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Shorter constructor:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, true, "UTF-8");
~~~

In Spring Framework, the **true** parameter activates multipart in the default mode **MULTIPART_MODE_MIXED_RELATED**. It does not merely mean “use pure multipart/mixed” as learners sometimes assume.

**MULTIPART_MODE_NO** is unsuitable for addInline, because a place is needed to hold separate MIME parts. A non-multipart message cannot represent HTML and an image as two related parts.

## 5. Complete example: welcome email with logo embedded from classpath

Suppose the project has the structure:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/mail/
    │       └── WelcomeMailService.java
    └── resources/
        ├── application.yml
        └── mail/
            └── logo.png
~~~

The **logo.png** file is placed in the application's resources and will be accessible from the classpath after building.

### 5.1. Dependency

In a Spring Boot project using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

The starter provides the Spring Mail/Jakarta Mail components to create and send messages. Host, port, TLS, and credentials are configured separately in application settings or the runtime environment.

### 5.2. Spring Mail Service

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("noreply@example.org");
        helper.setTo(recipient);
        helper.setSubject("Welcome");

        String plainText =
                "Welcome to the system!\n"
              + "Thank you for registering.";

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:companyLogo"
                         alt="Company logo"
                         width="160">
                    <h1>Welcome!</h1>
                    <p>Thank you for registering.</p>
                  </body>
                </html>
                """;

        // Set the content before adding inline images.
        helper.setText(plainText, htmlText);

        ClassPathResource logo =
                new ClassPathResource("mail/logo.png");

        helper.addInline("companyLogo", logo, "image/png");

        mailSender.send(message);
    }
}
~~~

The example assumes the **JavaMailSender** bean is already configured and the recipient address is validated per application policy. The HTML is fixed to make the structure clear; if putting user data into HTML, it must be escaped by context.

### 5.3. Step-by-step analysis

**Step 1 — Create MimeMessage.**

~~~java
MimeMessage message = mailSender.createMimeMessage();
~~~

Do not use **SimpleMailMessage** because this simple type has no API to build a MIME tree with inline images.

**Step 2 — Choose multipart mode.**

~~~java
new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

This mode allows HTML content, related resources, and standalone attachments if needed for future expansion. The UTF-8 charset is convenient when sending Vietnamese text.

**Step 3 — Set HTML with cid: reference.**

~~~html
<img src="cid:companyLogo" alt="Company logo">
~~~

This HTML specifies where the image is displayed inside the body.

**Step 4 — Call setText before addInline.**

~~~java
helper.setText(plainText, htmlText);
~~~

Spring Mail recommends setting the content before adding inline resources. This order increases compatibility across email clients in interpreting MIME part relationships.

**Step 5 — Point to the resource and add Content-ID.**

~~~java
ClassPathResource logo =
        new ClassPathResource("mail/logo.png");

helper.addInline("companyLogo", logo, "image/png");
~~~

The call adds the image part with the matching Content-ID. The last argument declares the resource's media type.

**Step 6 — Send the entire message.**

~~~java
mailSender.send(message);
~~~

At this point the transport processes the message containing the body and image. The send command does not guarantee the recipient will see the image, as email clients may hide it or handle it differently.

### 5.4. Logical resulting structure

~~~text
MimeMessage
└── multipart/mixed
    └── multipart/related
        ├── multipart/alternative
        │   ├── text/plain
        │   └── text/html
        │       └── <img src="cid:companyLogo">
        └── image/png
            └── Content-ID: <companyLogo>
~~~

This is a diagram describing the common content relationships of the mixed/related structure. The exact form of boundaries and MIME headers is generated by the library and may depend on the version and how the body is configured.

## 6. Why have both plain text and HTML?

In the example:

~~~java
helper.setText(plainText, htmlText);
~~~

Spring Mail creates two representations of the same message. Usually they are grouped with **multipart/alternative** semantics.

- The **text/plain** version does not depend on HTML tags or images.
- The **text/html** version has layout and a **cid:** link to the logo.
- An email client can choose the version suited to its display capabilities and user preferences.

If only HTML is needed, you can use:

~~~java
helper.setText(htmlText, true);
~~~

The **true** argument indicates the content is HTML. If set to **false**, the client may display the string of HTML tags as ordinary text.

Keep important information in text form. An order-confirmation email must still provide the order code and necessary details when the logo is not displayed.

## 7. Calling order of setText and addInline

One technical point that often causes confusion is the order of adding MIME parts.

Recommended order:

~~~java
helper.setText(html, true);
helper.addInline("logo", logoResource, "image/png");
~~~

Avoid reversing:

~~~java
helper.addInline("logo", logoResource, "image/png");
helper.setText(html, true);
~~~

Although the library may accept many operations on the message object, Spring Mail recommends **setText before addInline** because some clients are sensitive to how parts are arranged. This rule is simple and helps keep the structure clear.

If there is also an attachment, it can be added after the body and inline resources:

~~~java
helper.setText(html, true);
helper.addInline("logo", logoResource, "image/png");
helper.addAttachment("report.pdf", reportResource);
~~~

All calls are performed before **mailSender.send(message)**; you do not need to call send after each addInline/addAttachment.

## 8. Data sources for addInline

MimeMessageHelper has overloads for many data sources. Three common choices are **ClassPathResource**, **FileSystemResource**, and **ByteArrayResource**.

### 8.1. ClassPathResource — image packaged with the application

When the logo is a static resource:

~~~java
helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

The path is resolved relative to the **classpath**, not the current working directory. If the file is at **src/main/resources/mail/logo.png**, the usual runtime path is **mail/logo.png**.

Do not use the full source path:

~~~java
new ClassPathResource("src/main/resources/mail/logo.png");
~~~

because after JAR packaging, the **src/main/resources** directory may not exist as a physical path.

### 8.2. FileSystemResource — image already on disk

If the program generates a chart and saves it to a **Path**:

~~~java
import org.springframework.core.io.FileSystemResource;

FileSystemResource chart =
        new FileSystemResource(chartPath);

helper.setText(
        "<p>Chart:</p>"
      + "<img src=\"cid:salesChart\" alt=\"Chart\">",
        true
);

helper.addInline("salesChart", chart, "image/png");
~~~

The snippet assumes **chartPath** was determined by the application and the PNG file has already been created. You should control the source path, access permissions, and file lifecycle. If the file is deleted or modified before the transport reads the data, sending may fail or no longer contain the intended content.

### 8.3. ByteArrayResource — image created in memory

If the application already has image bytes:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] pngBytes = createPngBytes();

helper.setText(
        "<img src=\"cid:generatedImage\" alt=\"Illustration\">",
        true
);

helper.addInline(
        "generatedImage",
        new ByteArrayResource(pngBytes),
        "image/png"
);
~~~

**createPngBytes()** in the illustration snippet represents a function implemented by the application to produce valid PNG data.

ByteArrayResource suits small or medium images. For large images, consider memory cost and strategies for storing or transferring data.

### 8.4. Why shouldn't you arbitrarily use InputStreamResource?

During MIME building and sending, Jakarta Mail may need to access a part multiple times. A data source that can only be read once can cause errors or return an empty stream when the library needs to re-read.

**ClassPathResource**, **FileSystemResource**, and **ByteArrayResource** are easy-to-use choices because they can usually provide the data again. If you provide an **InputStreamSource** yourself, ensure it can open a fresh stream as required by the API, while properly managing resource lifecycles.

## 9. Content-Type must match the image format

The call:

~~~java
helper.addInline("logo", resource, "image/png");
~~~

does not turn the internal data into PNG. It declares to the client that the part contains PNG image data.

| Format | Common MIME type | Remarks |
| --- | --- | --- |
| PNG | image/png | Common for logos, charts, transparent-background images |
| JPEG | image/jpeg | Common for photographs |
| GIF | image/gif | Supported by many clients, though animation may differ |
| SVG | image/svg+xml | Compatibility and security policies vary |
| WebP | image/webp | Not every email client supports it well |

When requiring reliable display across many email clients, **PNG and JPEG** are usually the easy-to-control choices. Do not declare image/png for a file containing JPEG data just because the filename extension is png.

Overloads that do not pass Content-Type may rely on the library's file-type detection mechanism. When you know the data clearly, passing an explicit media type helps code readers understand the intent.

## 10. Adding multiple inline images in one message

A report email may have both a logo and a chart:

~~~html
<html>
  <body>
    <img src="cid:brandLogo" alt="Company logo">
    <h2>Revenue report</h2>
    <img src="cid:revenueChart" alt="Revenue chart">
  </body>
</html>
~~~

Java:

~~~java
helper.setText(html, true);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

helper.addInline(
        "revenueChart",
        new FileSystemResource(chartPath),
        "image/png"
);
~~~

Structure:

~~~text
multipart/related
├── text/html
│   ├── cid:brandLogo
│   └── cid:revenueChart
├── image/png  Content-ID: <brandLogo>
└── image/png  Content-ID: <revenueChart>
~~~

Each image has its own identifier. If using the same Content-ID for two different images, the reference becomes ambiguous.

Conversely, if **the same image** appears in two places in the HTML, you can use the same **cid:brandLogo** in both img tags. In that case, one MIME part for the logo is usually sufficient; no need to add the same data twice.

## 11. Adding an inline image together with a PDF attachment

When you want the HTML to have a logo and a PDF to download, choose **MIXED_RELATED** mode:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("reports@example.org");
helper.setTo("manager@example.net");
helper.setSubject("November report");

helper.setText(
        "<html><body>"
      + "<img src=\"cid:brandLogo\" alt=\"Logo\">"
      + "<p>Please see the attached PDF file.</p>"
      + "</body></html>",
        true
);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath),
        "application/pdf"
);

mailSender.send(message);
~~~

This example assumes **reportPath** is a Path variable passed to the method and the PDF file exists and is readable by the application.

Conceptual model:

~~~text
multipart/mixed
├── multipart/related
│   ├── text/html
│   └── image/png
│       └── Content-ID: <brandLogo>
└── application/pdf
    └── Content-Disposition: attachment
~~~

**addInline** creates an image part used for display in HTML; **addAttachment** creates a standalone file part. If you only call **addAttachment("logo.png", resource)**, HTML containing **cid:brandLogo** does not automatically have a part with a matching Content-ID.

Some clients may display even inline images in the attachment list. That is a presentation characteristic of the client and does not change the difference between the two APIs.

## 12. Raw MIME example to understand Content-ID

An HTML email with an embedded image can be represented at the protocol level as follows:

~~~text
From: noreply@example.org
To: user@example.net
Subject: Welcome
MIME-Version: 1.0
Content-Type: multipart/related; boundary="related-123"

--related-123
Content-Type: text/html; charset=UTF-8

<html>
  <body>
    <p>Welcome!</p>
    <img src="cid:welcomeLogo" alt="Logo">
  </body>
</html>

--related-123
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-Disposition: inline
Content-ID: <welcomeLogo>

[base64-image-data]

--related-123--
~~~

The line **[base64-image-data]** is only an illustrative marker, not a valid PNG. Real messages may use a different encoding for HTML, and MIME lines on the wire have CRLF terminators. The mail library handles those details automatically.

Points to note:

1. The root header declares **multipart/related**.
2. HTML and the image reside in two MIME parts.
3. The image's Content-ID header matches the identifier in the HTML's cid: URL.
4. The image is transported as encoded data, then decoded by the client.
5. Both parts still belong to the same MimeMessage.

**Content-ID does not need to match the filename.** For example, an image taken from brand-logo.png but having Content-ID **welcomeLogo** still works if the HTML also uses **cid:welcomeLogo**.

## 13. Common mistakes and causes

### 13.1. HTML uses one ID, addInline uses a different ID

Example:

~~~html
<img src="cid:logo" alt="Logo">
~~~

~~~java
helper.addInline("companyLogo", resource, "image/png");
~~~

Because **logo** and **companyLogo** differ, the client cannot resolve the reference as intended. Standardize on a single identifier.

### 13.2. Passing brackets into contentId beforehand

Example to avoid:

~~~java
helper.addInline("<logo>", resource, "image/png");
~~~

The parameter is the ID value, not the full header syntax. Pass **logo**, and let the helper create the appropriate Content-ID.

### 13.3. Creating the helper in non-multipart mode

Example:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
~~~

This configuration does not create an appropriate multipart structure for inline resources. Choose **MULTIPART_MODE_RELATED**, **MULTIPART_MODE_MIXED_RELATED**, or the **true** constructor in appropriate scenarios.

### 13.4. Calling addInline before setText

Recommended order:

~~~java
helper.setText(html, true);
helper.addInline("logo", resource, "image/png");
~~~

Some clients may be sensitive to the order and how parts are set up. Spring Mail recommends **setText before addInline**.

### 13.5. Setting HTML while using isHtml=false

If code has:

~~~java
helper.setText(
        "<img src=\"cid:logo\" alt=\"Logo\">",
        false
);
~~~

the content will be represented as plain text. The client may display the literal img tag syntax without rendering the image.

Use **setText(html, true)** or **setText(plainText, htmlText)**.

### 13.6. Resource does not exist

**new ClassPathResource("mail/logo.png")** only works when the resource actually exists on the runtime classpath. After JAR packaging, the path **src/main/resources** is no longer a file path to use in code.

With FileSystemResource, you must control the working directory, relative paths, read permissions, and when files are deleted.

### 13.7. Resource can only be read once

Jakarta Mail may ask to reopen the data source. An already-exhausted stream does not reopen itself. Use a re-accessible resource, or an InputStreamSource capable of supplying a fresh stream.

### 13.8. Wrong Content-Type or unsupported image format

A JPEG image declared as image/png can cause display errors. Likewise, SVG/WebP may not be well supported by some clients even if the MIME is built correctly.

### 13.9. Image exists only at an external URL while HTML uses cid:

If HTML uses **cid:logo**, there must be a MIME part with the matching Content-ID. An image file sitting on a web server but not added to the message with addInline will not automatically appear as an inline part.

### 13.10. Image data is too large

Inline images make messages heavier. With files of several MB, the base64 part and MIME headers increase the transport size. SMTP providers may cap message size; clients may also load or render slowly.

Optimize images before embedding and keep essential content in text form.

## 14. Email client compatibility

Some clients display inline images automatically; others apply their own policies.

| Situation | Possible consequence |
| --- | --- |
| Client chooses plain-text version | Does not render images in HTML |
| Client blocks images | Image does not appear even though MIME is correct |
| Client does not support image format | Part exists but is not rendered |
| Client presents every part as a file | Inline image may appear in the attachment list |
| Email CSS not fully supported | Image size/position displays differently than expected |
| HTML references wrong CID | Client cannot find the matching part |

Do not use images as the sole medium to convey verification codes, important content, or mandatory instructions. Provide **alt text**, a plain-text part, and full text content.

Simple HTML is usually more compatible:

~~~html
<img
  src="cid:companyLogo"
  alt="Company logo"
  width="160"
  style="display:block;max-width:100%;height:auto;">
~~~

However, email client CSS support can differ from web browsers; even simple HTML needs to be tested on target clients.

## 15. Security when putting resources into email

### 15.1. Do not use arbitrary user-supplied file paths

Do not do:

~~~java
String path = request.getParameter("path");
helper.addInline(
        "image",
        new FileSystemResource(path),
        "image/png"
);
~~~

If the path is directly controlled by the client, the application could read the wrong file or send unauthorized information.

Map a verified business ID to a resource inside a managed directory, or use static resources on the classpath.

### 15.2. Only embed authorized resources

A chart image may contain customer data or internal information. Because inline images reside inside the message, the recipient can extract the part's data. Do not treat embedded images as content that is hard to download or safer than attachments.

### 15.3. Check file type and size

Do not blindly trust file extensions supplied by users. If the application allows image uploads, check the actual media type, enforce size limits, and process data per policy.

### 15.4. Escape dynamic content in HTML

If the email template has:

~~~html
<p>Hello, {{displayName}}</p>
<img src="cid:companyLogo" alt="Logo">
~~~

then the **displayName** value must be escaped according to the HTML context. Content-ID does not protect the HTML section from users injecting unwanted markup.

### 15.5. Content-ID is not a secret

The ID value sits in MIME headers and HTML. Do not put passwords, access tokens, or sensitive authentication codes in Content-ID.

### 15.6. Base64 is not security encryption

Images are base64-encoded for transport, yet can be decoded directly. Content security depends on sending, receiving, and storage permissions, not the MIME encoding format.

## 16. When images do not display, what should you inspect?

When diagnosing an email that fails to render an image, separate into two layers: **message structure** and **receiving mail client behavior**.

At the MIME layer:

- Has the body been set to **text/html**?
- Does the HTML have the exact **cid:** string?
- Is there a MIME part with the matching **Content-ID**?
- Did the helper enable an appropriate multipart mode?
- Was **setText** called before **addInline**?
- Is the resource readable at send time?
- Does **Content-Type** match the data bytes?
- Is the message size within limits?

At the client layer:

- Did the client choose to display HTML or only plain text?
- Does the client block images or strip a media type?
- Does the client display the image as an attachment?
- Was the CSS or HTML layout altered?

**`send()` completing does not mean the recipient saw the image.** The SMTP server may accept the message while the final client still does not render a part as expected.

An email whose image fails in client A yet displays in client B may reflect differences in MIME compatibility or client policies. Changing the SMTP password will not solve a mismatched Content-ID issue.

When you need to inspect raw MIME in a development environment, use a controlled test mailbox or SMTP capture server. Avoid logging full real emails, addresses, and sensitive attachment data into production logs.

## 17. Applied scenarios

**Logo in a welcome email.** Use ClassPathResource for the static image, **helper.setText(plain, html)**, and **helper.addInline("companyLogo", logo, "image/png")**. Ensure HTML references **cid:companyLogo**.

**Daily report chart.** The application creates a PNG file or bytes, uses FileSystemResource or ByteArrayResource, sets a Content-ID like **dailyChart**, and references it from HTML.

**Notification with two images.** Add two MIME parts with two distinct Content-IDs. HTML contains two img tags with the exact corresponding references.

**Report email with logo and PDF.** Use **MULTIPART_MODE_MIXED_RELATED**. The logo is added via addInline; the PDF uses addAttachment.

**Needs to work even when the recipient does not view HTML.** Use **setText(plainText, htmlText)** and ensure the plain-text part contains enough information to understand the message.

## 18. Frequently asked questions

**Do I need to call send separately for each image?**

No. **addInline** adds a MIME part to the same message; once finished building, call send for the entire message.

**Is Content-ID a filename?**

No. It is an identifier for HTML to locate the MIME part. The resource may be **logo.png** while the Content-ID is **companyLogo**.

**Does HTML need to use src="cid:<companyLogo>"?**

With normal usage of **MimeMessageHelper**, no. HTML uses **src="cid:companyLogo"**; the helper creates the Content-ID header with angle brackets.

**Is MIXED_RELATED strictly required?**

No. **RELATED** fits HTML and inline resources. **MIXED_RELATED** is convenient when there are also standalone attachments.

**Can new MimeMessageHelper(message, true) be used?**

Yes. Spring Framework's boolean true constructor activates the default multipart mode **MIXED_RELATED**.

**Why should setText be called before addInline?**

Because clients may be sensitive to how parts are arranged. Spring Mail recommends setting the body before adding inline resources.

**Can JPEG images be added instead of PNG?**

Yes. Choose **image/jpeg** if the actual data bytes are JPEG. Do not declare the wrong MIME type.

**Are CID images guaranteed not to be blocked?**

No. Clients may hide images, choose the text version, or not support the format. Main content should still exist in text form.

**If one image appears multiple times, do I need multiple addInline calls?**

Usually not. Multiple img tags can all use **cid:companyLogo** to reference a single MIME part.

**Can an HTTPS URL be passed into addInline?**

addInline needs an appropriate resource/stream data source. If you want to embed an image fetched from the web, the application needs to download the data under an allowed policy and supply the byte source; or keep the HTTPS URL in HTML and accept that the client may block remote image loading.

## 19. Remembering Content-ID and MimeMessageHelper

**Content-ID** is the identifier of a MIME part. HTML references the part via a **cid:** URL. In Spring Framework Mail, the link is usually created with **helper.addInline("companyLogo", resource, "image/png")** and **src="cid:companyLogo"**.

To send HTML with inline images, create a **MimeMessage**, choose an appropriate multipart mode, call **setText** before **addInline**, and use a re-readable resource. When there are also standalone files to download, the **mixed/related** structure distinguishes related content from attachments.

One email can contain multiple inline images while remaining a single message. Final display capability depends on the MIME structure, data type, and email client; therefore include clear text, alt text, reasonable image sizes, and input resource control policies.
