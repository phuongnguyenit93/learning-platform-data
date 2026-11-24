# Adding Attachments and Inline Images from the Classpath

## 1. Objective of the Practice Project

In **Spring Framework Mail**, an email does not have to consist of just a few lines of text. Applications often need to send messages containing:

- **Plain-text content** so recipients can still read the message when their email client does not render HTML.
- **HTML content** with layout, colors, and links.
- **Inline images** such as a logo or illustration displayed *inside* the HTML rather than merely linking to an image on the Internet.
- **Attachments** such as a guide PDF, sample invoice, or form that the recipient can download.

This practice project **"Adding Attachments and Inline Images from the Classpath"** builds an email-sending service with the following structure:

~~~text
Spring Boot application
    |
    +-- src/main/resources/mail/images/brand-logo.png
    +-- src/main/resources/mail/attachments/welcome-guide.pdf
    |
    v
ClasspathResource
    |
    v
MimeMessage + MimeMessageHelper
    |
    +-- plain text
    +-- HTML <img src="cid:brandLogo">
    +-- inline PNG (Content-ID: brandLogo)
    +-- attached PDF
    |
    v
JavaMailSender
    |
    v
SMTP server / test inbox
~~~

After this lesson, learners should be able to:

1. Distinguish between an **attachment** and an **inline resource**.
2. Place files in the right **classpath** directory so they remain readable even when the application is packaged as a JAR.
3. Build MIME emails with **MimeMessageHelper** and configure an appropriate multipart mode.
4. Attach a PDF file from **ClassPathResource** using **addAttachment(...)**.
5. Embed a PNG image from **ClassPathResource** using **addInline(...)** and reference it in HTML via **cid:**.
6. Understand why **Content-ID**, **Content-Type**, the order of adding inline resources, and MIME structure affect rendering.
7. Structure the service, configure test SMTP, test MIME parts, and handle errors safely.
8. Recognize the limitations of the classpath example when moving to dynamically generated files or user-specific data.

In the examples, all domains and addresses use forms like **example.com/example.net** or local mock hosts. Do not send emails to real mailboxes while learning without authorization.

## 2. Distinguishing Attachments from Inline Images

Two resources may both be PNG/PDF files yet be represented differently in MIME.

| Criterion | Attachment | Inline Image |
|---|---|---|
| Purpose | Attached file to download/save/open | Resource displayed within the HTML body |
| Spring API | **MimeMessageHelper.addAttachment(...)** | **MimeMessageHelper.addInline(...)** |
| Typical MIME disposition | **attachment** | **inline** |
| Link with HTML | Not required | Via **Content-ID** and **cid:** |
| Example | welcome-guide.pdf | brand-logo.png |
| Display in mail client | Filename, download button | Image displayed inside the message if supported |
| Can appear in attachment list? | Yes | Possibly, depending on the email client |
| Embedded as base64 in HTML? | Not needed | No; the file is a separate MIME part |

HTML example:

~~~html
<h1>Welcome to the Application</h1>
<p>The logo is attached inside MIME and displayed right below:</p>
<img src="cid:brandLogo" alt="Logo" width="180">
<p>The user guide is sent as an attached PDF file.</p>
~~~

Where:

- **cid:brandLogo** references a MIME part with the matching **Content-ID**.
- The image is not fetched from a public URL like **https://.../logo.png**.
- The PDF file is an independent part with `Content-Disposition: attachment`.

**Common mistake:** an image added with **addAttachment("logo.png", ...)** will not automatically appear at **img src="cid:brandLogo"**. To use **cid:**, you must add an inline resource with the matching Content-ID.

## 3. What Is the Classpath in This Example?

In a standard Spring Boot project:

~~~text
src/main/resources/
    application.yml
    mail/
        images/
            brand-logo.png
        attachments/
            welcome-guide.pdf
~~~

Files inside **src/main/resources** are normally copied by the build tool onto the application's **classpath**.

When running in an IDE, resources may be accessed from the build classes directory:

~~~text
target/classes/mail/images/brand-logo.png
~~~

or:

~~~text
build/resources/main/mail/images/brand-logo.png
~~~

When packaged into a Spring Boot executable JAR, they reside inside the archive:

~~~text
BOOT-INF/classes/mail/images/brand-logo.png
BOOT-INF/classes/mail/attachments/welcome-guide.pdf
~~~

Therefore, **the classpath is not equivalent to a physical filesystem directory accessible via `java.io.File` in every environment**.

To access resources portably, use:

~~~java
import org.springframework.core.io.ClassPathResource;

ClassPathResource logo =
        new ClassPathResource("mail/images/brand-logo.png");

ClassPathResource guide =
        new ClassPathResource("mail/attachments/welcome-guide.pdf");
~~~

The path passed to **ClassPathResource(...)** is relative to the *classpath root*. Do not include the **src/main/resources/** prefix in the string.

## 4. Environment Preparation

An example project needs:

- A Java version supported by your Spring Boot version (e.g., Java 17+ in a Spring Boot 3.x project).
- Spring Boot and **spring-boot-starter-mail**.
- A test SMTP server / capture inbox.
- Two valid resources placed on the classpath: PNG and PDF.

Maven dependency when managing versions via Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
~~~

If you want to expose a demo REST endpoint:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Gradle Groovy DSL equivalent:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Note on Jakarta Mail:** Spring Framework 6 / Spring Boot 3+ projects use the **jakarta.mail.\*** packages. Older Spring 5 / Boot 2 projects may use **javax.mail.\***. Never mix MIME classes and dependencies from both ecosystems in the same project.

This exercise does not require generating a real PDF in Java or sending mail to a commercial provider. To try it out, place a valid PNG file and a valid PDF file at the corresponding resource paths.

## 5. Sample Directory Structure

~~~text
spring-mail-classpath-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/maildemo/
    │   │   ├── MailDemoApplication.java
    │   │   ├── mail/
    │   │   │   ├── MailAssetProperties.java
    │   │   │   ├── MailResourceLoader.java
    │   │   │   ├── WelcomeMailService.java
    │   │   │   └── MailDemoController.java
    │   └── resources/
    │       ├── application.yml
    │       └── mail/
    │           ├── images/
    │           │   └── brand-logo.png
    │           └── attachments/
    │               └── welcome-guide.pdf
    └── test/
        ├── java/com/example/maildemo/mail/
        │   └── WelcomeMailServiceTest.java
        └── resources/
~~~

In a real application, you do not have to mirror every single class in this diagram. What matters is keeping **email composition**, **resource loading**, **transport**, and **API authorization** clearly separated.

### Are Files in Resources Considered Runtime Data?

Classpath resources are generally appropriate for **static files bundled with an application release**, such as a brand logo and a default guide document.

Do not use the classpath to store:

- Dynamically generated PDF invoices per user.
- Files uploaded by users after deployment.
- Documents containing personal data subject to per-user deletion requests.
- Files that change frequently without wanting to rebuild/redeploy.

Those cases belong in a **database, object storage, or durable file storage** with proper access control and retention policies.

## 6. Choosing Consistent Resource Paths

Three common approaches:

~~~java
new ClassPathResource("mail/images/brand-logo.png");

resourceLoader.getResource(
        "classpath:mail/images/brand-logo.png"
);

new ClassPathResource(
        "/mail/images/brand-logo.png"
);
~~~

With **ClassPathResource**, prefer an explicit classpath-relative path without a leading slash. With **ResourceLoader**, the **classpath:** prefix specifies the resource protocol.

Avoid writing:

~~~java
new ClassPathResource(
        "src/main/resources/mail/images/brand-logo.png"
);
~~~

because **src/main/resources** is a source-tree folder, not part of the packaged classpath path.

Never construct paths by concatenating untrusted user input:

~~~java
new ClassPathResource(
        "mail/attachments/" + userProvidedFilename
);
~~~

This can lead to accessing unintended resources or leaking files not meant to be sent. Resources must be selected from an application-controlled **allowlist**.

## 7. What Is MIME Multipart?

Emails transmitted over SMTP using MIME can contain multiple body parts. A MIME message can have the structure:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   └── image/png
    │       Content-ID: <brandLogo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="welcome-guide.pdf"
~~~

This is the **conceptual structure** for an email with plain text, HTML, an inline image, and an attachment. Exact MIME tree details depend on helper settings, the Jakarta Mail implementation, and how the message is constructed.

Different multipart subtypes serve different roles:

- **multipart/mixed:** holds independent content parts and attachments.
- **multipart/related:** groups HTML with dependent resources, such as images referenced by Content-ID.
- **multipart/alternative:** supplies multiple representations of the same content, typically plain text and HTML.

If you only use **SimpleMailMessage**, there is no MIME multipart API to attach inline images and files this way. You need **MimeMessage**.

## 8. What Does MimeMessageHelper Provide?

Spring provides **MimeMessageHelper** in package:

~~~java
import org.springframework.mail.javamail.MimeMessageHelper;
~~~

It helps with:

- Setting `From`, `To`, `Cc`, `Bcc`, and `Subject`.
- Setting plain-text and HTML content.
- Setting the character encoding.
- Creating multipart messages.
- Adding attachments via **DataSource**, **File**, or **InputStreamSource**.
- Adding inline resources via **addInline(...)**.

A helper initialized with `MimeMessage` **without enabling multipart** is insufficient for this exercise.

Recommended usage:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

**MULTIPART_MODE_MIXED_RELATED** organizes bodies containing both inline resources and attachments. It is well-suited for HTML emails with logos and attached documents.

The constructor:

~~~java
new MimeMessageHelper(message, true, "UTF-8");
~~~

also enables multipart; however, using the **MULTIPART_MODE_MIXED_RELATED** constant makes the design intent explicit in this practice project.

## 9. Why Pair Plain Text with HTML?

Some recipients disable HTML, email clients vary in HTML support, or messages are read with assistive software. If only HTML is sent, recipients may struggle to read the message when it fails to render.

Spring supports:

~~~java
helper.setText(
        "Welcome! Please see the attached guide.",
        "<h1>Welcome!</h1>"
                + "<p>Please see the attached guide.</p>"
);
~~~

When passing two strings, **the first parameter is plain text**, and the second is HTML. The helper builds the appropriate **multipart/alternative** structure.

Do not confuse this with the overload:

~~~java
helper.setText(
        "<h1>Welcome</h1>",
        true
);
~~~

The second overload treats the string as **HTML-only content**, rather than providing both a plain-text and an HTML version.

Keep the core information equivalent across both versions; never fill plain text with generic filler while HTML carries distinct transactional details.

## 10. Complete Email-Sending Service

This is the centerpiece of the practice project. Create **WelcomeMailService**:

~~~java
package com.example.maildemo.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private static final String LOGO_CID = "brandLogo";

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcomeMail(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("welcome@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome to the application");

        String plainText = """
                Hello!

                Thank you for joining us.
                The getting-started guide is attached as a PDF file.
                """;

        String html = """
                <!doctype html>
                <html lang="en">
                <body>
                    <h1>Welcome!</h1>
                    <p>Thank you for joining us.</p>
                    <img src="cid:brandLogo"
                         alt="Application logo"
                         width="180">
                    <p>The getting-started guide is in the attached
                       <strong>welcome-guide.pdf</strong> file.</p>
                </body>
                </html>
                """;

        // Set body content before adding inline resources.
        helper.setText(plainText, html);

        ClassPathResource logo = new ClassPathResource(
                "mail/images/brand-logo.png"
        );

        helper.addInline(
                LOGO_CID,
                logo,
                "image/png"
        );

        ClassPathResource guide = new ClassPathResource(
                "mail/attachments/welcome-guide.pdf"
        );

        helper.addAttachment(
                "welcome-guide.pdf",
                guide,
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

Step-by-step summary:

1. **createMimeMessage()** creates a MIME message using `JavaMailSender`'s session.
2. **MimeMessageHelper(..., MULTIPART_MODE_MIXED_RELATED, "UTF-8")** enables multipart and UTF-8 encoding.
3. **setFrom, setTo, setSubject** configure core metadata.
4. **setText(plainText, html)** creates both content representations.
5. **addInline("brandLogo", logo, "image/png")** adds a MIME resource bound to a Content-ID.
6. **addAttachment("welcome-guide.pdf", guide, "application/pdf")** adds the PDF as an attachment.
7. **mailSender.send(message)** sends the message via SMTP transport.

In a real project, **recipients must be validated and authorized before sending**. This service stays concise to demonstrate MIME construction; it does not try to model every production policy.

## 11. Why Specify MIME Content-Type Explicitly?

The two calls:

~~~java
helper.addInline("brandLogo", logo, "image/png");

helper.addAttachment(
        "welcome-guide.pdf",
        guide,
        "application/pdf"
);
~~~

explicitly declare:

- PNG as **image/png**.
- PDF as **application/pdf**.

Without a `Content-Type`, other `MimeMessageHelper` overloads try to infer the media type from the filename or a file type map. With unusual filenames, missing extensions, or differing OS file type maps, inference can be wrong.

When you know the resource is a valid PNG or PDF, **specifying the media type explicitly** makes behavior consistent.

Common media types:

| File Type | Suggested Content-Type |
|---|---|
| PNG | **image/png** |
| JPEG | **image/jpeg** |
| GIF | **image/gif** |
| PDF | **application/pdf** |
| Plain text | **text/plain** |
| CSV | **text/csv** |

`Content-Type` is **metadata**; it does not verify the bytes inside. Never rename an untrusted file to `.png` and assume it is a safe PNG.

## 12. Content-ID Links HTML to Resources

In code:

~~~java
String cid = "brandLogo";
helper.addInline(cid, logo, "image/png");
~~~

In HTML:

~~~html
<img src="cid:brandLogo" alt="Application logo" width="180">
~~~

Both sides must match:

~~~text
HTML src:
    cid:brandLogo
          |
          v
MIME header:
    Content-ID: <brandLogo>
~~~

**MimeMessageHelper.addInline(...)** generates a **Content-ID** header wrapped in angle brackets per MIME convention; when calling the API, pass the ID string **without `<` and `>`**.

Do not mistakenly write:

~~~java
helper.addInline("<brandLogo>", logo);
~~~

and then reference:

~~~html
<img src="cid:brandLogo">
~~~

Including brackets in the API call can produce an unexpected header value.

### Does a CID Need to Look Like a Full Email Address?

In MIME, `Content-ID` follows **msg-id** syntax. Many examples use simple IDs like `brandLogo`, which email clients accept. For broader compatibility or managing multiple inline resources, you can use a unique ID such as:

~~~text
brandLogo.12345@mailer.example.com
~~~

HTML must then reference **cid:brandLogo.12345@mailer.example.com**, matching the value passed to the helper exactly. If the system generates CIDs dynamically, ensure uniqueness and proper encoding, and never inject untrusted input into headers.

For this practice project, **brandLogo** is easy to follow.

## 13. Call Order of setText and addInline

In the standard example:

~~~java
helper.setText(plainText, html);
helper.addInline("brandLogo", logo, "image/png");
~~~

This is the recommended order. Some MIME readers are sensitive to part ordering, and Spring documentation recommends calling **setText(...) before addInline(...)** so inline resources are parsed properly by clients.

Avoid:

~~~java
helper.addInline("brandLogo", logo, "image/png");
helper.setText(plainText, html);
~~~

Although some clients still display it, this can hurt compatibility.

Attachments can be added after inline resources:

~~~java
helper.setText(plainText, html);
helper.addInline("brandLogo", logo, "image/png");
helper.addAttachment("welcome-guide.pdf", guide, "application/pdf");
~~~

When rendering multiple resources, setting the HTML/plain text body first, followed by `addInline` and `addAttachment` calls grouped together, keeps the code clean.

## 14. Why Use ClassPathResource Instead of File?

These two snippets:

~~~java
ClassPathResource resource = new ClassPathResource(
        "mail/images/brand-logo.png"
);

resource.getInputStream();
~~~

and:

~~~java
File file = new File(
        "src/main/resources/mail/images/brand-logo.png"
);
~~~

are not equivalent.

**ClassPathResource** resolves resources on the classpath, working seamlessly when packaged inside a classpath/JAR. **File** with a relative path depends on the process's working directory.

When running:

~~~text
java -jar mail-demo.jar
~~~

the working directory might be **/opt/app**, which does not contain **src/main/resources**.

Therefore, calling:

~~~java
resource.getFile()
~~~

must never be assumed to succeed for files packaged inside a JAR. **getInputStream()** is the portable access method.

In this practice project, `MimeMessageHelper` accepts **ClassPathResource** directly because it implements **InputStreamSource**.

## 15. InputStreamSource and Re-Readability

**ClassPathResource** can open a fresh `InputStream` whenever requested, making it suitable for attachments and inline content while the message is constructed and written over SMTP.

Example:

~~~java
ClassPathResource guide = new ClassPathResource(
        "mail/attachments/welcome-guide.pdf"
);

helper.addAttachment(
        "welcome-guide.pdf",
        guide,
        "application/pdf"
);
~~~

Some Jakarta Mail APIs may read the stream more than once—for instance, to compute size, prepare MIME encoding, and perform transmission. Therefore, **never wrap an already-opened InputStream** as a single-use `InputStreamSource`.

Error-prone example:

~~~java
InputStream once = guide.getInputStream();

// Never pass a source that returns the same single-use stream
// across multiple getInputStream() calls.
~~~

For classpath files, pass **ClassPathResource** directly. For dynamically generated bytes, use a repeatable source like **ByteArrayResource**, while keeping memory and size limits in mind.

### What If a Resource Is Too Large?

Do not load tens of megabytes of attachments onto the heap just for convenience. Consider streaming from file/object storage or sending an authorized download link instead, depending on SMTP limits and data policies.

## 16. Specifying Attachment Filenames

In the API call:

~~~java
helper.addAttachment(
        "welcome-guide.pdf",
        guide,
        "application/pdf"
);
~~~

**"welcome-guide.pdf"** is the filename shown to the recipient, not the classpath path.

You can retrieve the filename from `ClassPathResource`:

~~~java
String filename = guide.getFilename();
~~~

However, because `getFilename()` can return `null` on some `Resource` implementations and applications often want a custom display filename, specifying it explicitly is useful.

For example, reusing the same PDF resource:

~~~java
helper.addAttachment(
        "Huong-dan-bat-dau.pdf",
        guide,
        "application/pdf"
);
~~~

Attachment filenames must never contain CR/LF, path separators, control characters, or raw user-supplied strings. Sanitize display filenames and apply proper charset encoding, as mail clients vary in how they handle Unicode filenames.

## 17. Multiple Inline Images in One Message

Example with a logo and a help icon:

~~~java
ClassPathResource logo =
        new ClassPathResource("mail/images/brand-logo.png");

ClassPathResource helpIcon =
        new ClassPathResource("mail/images/help-icon.png");

String html = """
        <html><body>
            <img src="cid:brandLogo" alt="Logo">
            <p>Contact support:
                <img src="cid:helpIcon" alt="Support" width="20">
            </p>
        </body></html>
        """;

helper.setText("Contact support through the app.", html);
helper.addInline("brandLogo", logo, "image/png");
helper.addInline("helpIcon", helpIcon, "image/png");
~~~

Each inline image has **its own Content-ID**, and the HTML references the exact ID.

Never reuse the same CID for two different resources in one message, as clients may pick an unexpected part.

If the same logo appears multiple times in the HTML, you can reference **the same CID** repeatedly without adding the resource again:

~~~html
<img src="cid:brandLogo" alt="Header logo">
<img src="cid:brandLogo" alt="Footer logo">
~~~

## 18. Sending Multiple Attachments in One Email

One message can carry multiple static files:

~~~java
helper.addAttachment(
        "welcome-guide.pdf",
        new ClassPathResource("mail/attachments/welcome-guide.pdf"),
        "application/pdf"
);

helper.addAttachment(
        "terms.pdf",
        new ClassPathResource("mail/attachments/terms.pdf"),
        "application/pdf"
);
~~~

For a small fixed set, explicit calls are easy to read. When attachments vary by template, maintain an **allowlist catalog** mapping logical asset names to paths, content types, and display filenames.

Example:

~~~text
Asset ID: WELCOME_GUIDE
  path: mail/attachments/welcome-guide.pdf
  contentType: application/pdf
  displayName: welcome-guide.pdf

Asset ID: BRAND_LOGO
  path: mail/images/brand-logo.png
  contentType: image/png
  cid: brandLogo
~~~

Never allow external callers to pass arbitrary path lists to automatically attach anything readable from the classpath.

## 19. PDF Attachments and Inline Images Are Not Interchangeable

Example:

~~~html
<p>Please see the attached PDF guide.</p>
<img src="cid:welcomeGuide">
~~~

If you attach a PDF via **addAttachment(...)**, an **img** tag cannot render a PDF like a PNG/JPEG image. To display a thumbnail for the PDF, you must:

- Prepare a separate PNG/JPEG thumbnail file on the classpath; or
- Generate a thumbnail via an appropriate pipeline and attach it as an inline image.

The PDF itself is still sent as an attachment:

~~~text
HTML -> thumbnail image via cid:guidePreview
Attachment -> welcome-guide.pdf
~~~

Never attach an entire PDF as the `Content-ID` of an `img` tag and expect email clients to display it.

## 20. Configuring SMTP for Safe Testing

With Spring Boot, **JavaMailSender** is typically auto-configured when the mail starter and required properties are present.

Example configuring a local SMTP capture server on a development machine:

~~~yaml
spring:
  mail:
    host: localhost
    port: 1025
    properties:
      mail.smtp.auth: false
      mail.smtp.starttls.enable: false
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

This configuration is **strictly for an unauthenticated SMTP test server in an isolated local environment**. Never use no-TLS/no-auth settings to send production traffic over the Internet.

When using authenticated SMTP:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Environment variables must be supplied by a secret manager or secure configuration. Verify the exact host, port, TLS mode, and provider policies; never assume all servers share identical settings.

**MailHog/Mailpit/GreenMail** are common choices for test environments. Startup commands, SMTP ports, and web UI ports depend on the installation; **localhost:1025** above is illustrative and should match your SMTP test server.

## 21. Running the Spring Boot Application

Startup class:

~~~java
package com.example.maildemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MailDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MailDemoApplication.class, args
        );
    }
}
~~~

Once Spring Mail dependencies and SMTP properties are configured, **WelcomeMailService** receives an appropriate `JavaMailSender` bean from Spring.

In this exercise, you can invoke the service from:

- A **CommandLineRunner** when testing sending a single sample email locally.
- An **integration test**.
- A protected **internal endpoint**.

Never configure a production application to send real emails automatically on every startup, because pod restarts or scaling would generate duplicate emails.

Example runner activated only under the `mail-demo` profile:

~~~java
package com.example.maildemo;

import com.example.maildemo.mail.WelcomeMailService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class DemoMailRunner {

    @Bean
    @Profile("mail-demo")
    CommandLineRunner sendOneExample(
            WelcomeMailService service
    ) {
        return args -> service.sendWelcomeMail(
                "student@example.net"
        );
    }
}
~~~

Enable the **mail-demo** profile only against an SMTP capture server or an authorized test address. If used in a production-like environment, guard the runner so it never resends or creates unintended emails.

## 22. Checking Resource Existence Before Creating an Email

When a path is wrong, the error might not surface until Jakarta Mail actually reads the resource to write MIME/SMTP `DATA`.

A simple helper:

~~~java
import org.springframework.core.io.ClassPathResource;

public final class MailResourceLoader {

    public ClassPathResource required(String path) {
        ClassPathResource resource =
                new ClassPathResource(path);

        if (!resource.exists() || !resource.isReadable()) {
            throw new IllegalStateException(
                    "Required mail resource is missing: " + path
            );
        }

        return resource;
    }
}
~~~

In this example, **path is an application constant or controlled value**, not a path passed directly by callers. If paths come from users or tenant configuration, never log or read them arbitrarily; use an allowlisted catalog ID.

Service usage example:

~~~java
MailResourceLoader resources = new MailResourceLoader();

ClassPathResource logo = resources.required(
        "mail/images/brand-logo.png"
);

ClassPathResource pdf = resources.required(
        "mail/attachments/welcome-guide.pdf"
);
~~~

**exists()** and **isReadable()** are early checks; they do not guarantee the file is error-free in every case. An `IOException` or `MailException` can still occur while streaming or sending, so error handling at the transport boundary remains necessary.

## 23. Missing Resources at Startup: Fail Fast or Fail on Send?

Suppose the application requires a logo and a PDF in every welcome email:

~~~text
Build succeeds
JAR is missing welcome-guide.pdf
Application starts
When a new user registers -> send fails
~~~

There are two options:

**Fail fast at startup**

- Verify required resources inside a startup validation service.
- Catch packaging or configuration errors early.
- Appropriate when the resources are essential to the mail flow.

**Check at compose time**

- A mistake in a rarely used template does not block the entire application from starting.
- Appropriate when supporting many campaigns or optional resources.
- Requires dedicated observability and failure states per notification.

Startup validator example:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

@Configuration
public class MailAssetValidationConfiguration {

    @Bean
    ApplicationRunner verifyRequiredMailAssets() {
        return args -> {
            require("mail/images/brand-logo.png");
            require("mail/attachments/welcome-guide.pdf");
        };
    }

    private void require(String path) {
        ClassPathResource resource =
                new ClassPathResource(path);
        if (!resource.exists() || !resource.isReadable()) {
            throw new IllegalStateException(
                    "Missing mail asset: " + path
            );
        }
    }
}
~~~

Separate mandatory and optional resources under a clear policy. Never apply fail-fast startup checks to files generated dynamically after startup.

## 24. Organizing an Asset Catalog with Types and CIDs

As the practice project expands to multiple templates, hardcoded paths can be consolidated into a catalog:

~~~java
public enum MailAsset {

    BRAND_LOGO(
            "mail/images/brand-logo.png",
            "image/png",
            "brandLogo"
    ),

    WELCOME_GUIDE(
            "mail/attachments/welcome-guide.pdf",
            "application/pdf",
            null
    );

    private final String path;
    private final String mediaType;
    private final String contentId;

    MailAsset(
            String path,
            String mediaType,
            String contentId
    ) {
        this.path = path;
        this.mediaType = mediaType;
        this.contentId = contentId;
    }

    public String path() {
        return path;
    }

    public String mediaType() {
        return mediaType;
    }

    public String contentId() {
        return contentId;
    }
}
~~~

Usage:

~~~java
MailAsset logoAsset = MailAsset.BRAND_LOGO;

helper.addInline(
        logoAsset.contentId(),
        new ClassPathResource(logoAsset.path()),
        logoAsset.mediaType()
);
~~~

Benefits:

- Never takes paths supplied by recipients.
- Reduces mistakes with media types.
- Makes updating assets across template versions easy.
- Allows validating the entire catalog at build/deploy time.

In multi-tenant production systems, the catalog can reference assets managed per tenant/template version, with explicit authorization before loading.

## 25. Separating Compose and Send Steps

To make testing easier, you can extract a component solely responsible for **composing MIME**:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class WelcomeMimeComposer {

    public void compose(
            MimeMessage message,
            String approvedFrom,
            String recipient
    ) throws MessagingException {

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom(approvedFrom);
        helper.setTo(recipient);
        helper.setSubject("Welcome");

        String text = "Hello! Please see the attached PDF file.";
        String html = """
                <html><body>
                <h1>Hello!</h1>
                <img src="cid:brandLogo"
                     alt="Application logo"
                     width="180">
                <p>Please see the attached PDF guide.</p>
                </body></html>
                """;

        helper.setText(text, html);

        helper.addInline(
                "brandLogo",
                new ClassPathResource(
                        "mail/images/brand-logo.png"
                ),
                "image/png"
        );

        helper.addAttachment(
                "welcome-guide.pdf",
                new ClassPathResource(
                        "mail/attachments/welcome-guide.pdf"
                ),
                "application/pdf"
        );
    }
}
~~~

Sending via a separate service:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailDispatcher {

    private final JavaMailSender sender;
    private final WelcomeMimeComposer composer;

    public WelcomeMailDispatcher(
            JavaMailSender sender,
            WelcomeMimeComposer composer
    ) {
        this.sender = sender;
        this.composer = composer;
    }

    public void send(String approvedRecipient)
            throws MessagingException {

        MimeMessage message = sender.createMimeMessage();

        composer.compose(
                message,
                "welcome@example.com",
                approvedRecipient
        );

        sender.send(message);
    }
}
~~~

This is a **separated-responsibilities variant** of the initial `WelcomeMailService`, not a requirement to use both services together for the same email. It makes testing MIME composition easy without invoking SMTP.

## 26. Never Send via an Unprotected Public Endpoint

A controller like:

~~~java
@PostMapping("/send-email")
public void send(@RequestParam String email) {
    welcomeMailService.sendWelcomeMail(email);
}
~~~

without authentication/authorization, validation, and rate limiting turns the server into a mass-mailing abuse vector.

In this exercise, prefer:

- A **CommandLineRunner** active only in the `local` profile; or
- A dedicated **test SMTP server**; or
- An internal endpoint protected by Spring Security and an allowlisted recipient scope.

If adding a production controller:

1. Callers must be authenticated.
2. Only authorized mail types may be sent.
3. Recipients must fall within allowed scope.
4. Apply idempotency and rate limits.
5. Never let callers override **From/Reply-To/SMTP host** arbitrarily.
6. Report honest send states; never claim "delivered" merely because `send()` returned.

## 27. Handling Prepare vs. Send Exceptions Differently

Two phases:

~~~text
Prepare:
  create MimeMessage
  build HTML/plain text
  load ClassPathResource
  addInline/addAttachment

Transport:
  JavaMailSender.send(...)
  connect/auth/TLS/SMTP DATA/final reply
~~~

**MessagingException** usually relates to MIME/Jakarta Mail operations. **MailException** is Spring Mail's hierarchy of unchecked exceptions across sending, preparation, and transport.

Example:

~~~java
import jakarta.mail.MessagingException;
import org.springframework.mail.MailException;

public void deliver(String recipient) {
    try {
        dispatcher.send(recipient);
    } catch (MessagingException ex) {
        // Do not retry SMTP endlessly:
        // could be a MIME/header/content composition bug.
        throw new MailCompositionFailure(ex);
    } catch (MailException ex) {
        // Classify auth, provider 4xx/5xx, timeout,
        // or unknown outcome by phase.
        throw new MailTransportFailure(ex);
    }
}
~~~

**MailCompositionFailure** and **MailTransportFailure** are illustrative application exceptions.

A missing resource may raise an `IOException` or be translated into a `MailException` when MIME is written out to SMTP. Never assume every `MailException` is the server's fault; inspect the cause chain and phase.

If SMTP `DATA` transmission started and the final reply never arrived, the outcome may be **UNKNOWN**. Automatic retries can produce duplicate emails.

## 28. Do Not Hold a Database Transaction Open While Sending SMTP

An anti-pattern:

~~~java
@Transactional
public void createUserAndSendMail(...) {
    saveUser();
    welcomeMailService.sendWelcomeMail(...);
}
~~~

Reasons:

- SMTP can take several seconds and unnecessarily hold DB transactions and locks.
- A database rollback cannot recall an email already accepted by SMTP.
- If mail transport fails, user creation may roll back even though the email was only a secondary notification.

When the application must guarantee **the intent to send is never lost** after user creation, consider:

~~~text
Business transaction:
    saveUser()
    insertNotificationOutbox()
COMMIT
       |
       v
Worker:
    compose from classpath resources
    JavaMailSender.send(...)
~~~

Classpath files are still used to compose emails inside the worker, provided the worker artifact includes the same resources. When workers run as separate deployments or versions, ensure template and asset compatibility between producers and consumers.

## 29. Testing MIME Composition Without Real SMTP

Because **WelcomeMimeComposer** only operates on `MimeMessage`, you can instantiate a Jakarta Mail `Session` in tests without network connectivity.

JUnit example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class WelcomeMimeComposerTest {

    private final WelcomeMimeComposer composer =
            new WelcomeMimeComposer();

    @Test
    void preparesSubjectAndMultipartMessage()
            throws Exception {

        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);

        composer.compose(
                message,
                "welcome@example.com",
                "student@example.net"
        );

        message.saveChanges();

        assertEquals("Welcome", message.getSubject());
        assertNotNull(message.getContent());
    }
}
~~~

This is a **baseline test** for message construction. Because the practice project focuses on attachments and inline images, add assertions checking the MIME tree and `Content-ID`, not just the Subject.

### Why Not Check Raw Messages with Simple `contains`?

HTML and attachments may be MIME-encoded (quoted-printable/base64), `Content-Type` includes parameters, and headers may fold across lines. Therefore:

~~~java
message.toString().contains("cid:brandLogo")
~~~

is not a reliable way to verify MIME structure.

Instead, use **Part.getContent()**, **MimeMultipart**, **BodyPart**, and per-part headers to inspect the generated structure.

## 30. Traversing MIME Parts to Locate Attachments and Inline Resources

A test helper can walk the multipart tree:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.util.ArrayList;
import java.util.List;

public final class MimePartCollector {

    private MimePartCollector() {
    }

    public static List<Part> collect(Part root) throws Exception {
        List<Part> results = new ArrayList<>();
        walk(root, results);
        return results;
    }

    private static void walk(
            Part part,
            List<Part> results
    ) throws Exception {

        results.add(part);

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int index = 0;
                 index < multipart.getCount();
                 index++) {

                BodyPart bodyPart = multipart.getBodyPart(index);
                walk(bodyPart, results);
            }
        }
    }
}
~~~

This function takes a **Part** and collects all nested parts, including multipart containers. Use it to locate:

- A part with **Content-ID: `<brandLogo>`**.
- A part with **image/png**.
- A part with **application/pdf**, the expected filename, and attachment disposition.
- A **text/html** part referencing **cid:brandLogo**.
- A **text/plain** part containing the equivalent text.

### Assertion Example

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.List;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class WelcomeMimeContentTest {

    @Test
    void includesInlineLogoAndPdfAttachment()
            throws Exception {

        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties())
        );

        new WelcomeMimeComposer().compose(
                message,
                "welcome@example.com",
                "student@example.net"
        );
        message.saveChanges();

        List<Part> parts = MimePartCollector.collect(message);

        assertTrue(parts.stream().anyMatch(part -> {
            try {
                String[] ids = part.getHeader("Content-ID");
                return ids != null
                        && ids.length > 0
                        && ids[0].contains("brandLogo")
                        && part.isMimeType("image/png");
            } catch (Exception ex) {
                return false;
            }
        }));

        assertTrue(parts.stream().anyMatch(part -> {
            try {
                return part.isMimeType("application/pdf")
                        && "welcome-guide.pdf"
                                .equals(part.getFileName());
            } catch (Exception ex) {
                return false;
            }
        }));
    }
}
~~~

These assertions verify the two **required parts**. They do not prove every mail client will render the image properly, as clients apply image-blocking policies, alter layouts, or use custom MIME parsers.

### Why Use `isMimeType`?

A part with Content-Type:

~~~text
image/png; name="brand-logo.png"
~~~

fails plain string equality against **image/png** due to extra parameters. **Part.isMimeType("image/png")** checks the media type per MIME semantics.

## 31. Testing That the Service Calls JavaMailSender Exactly Once

You do not need an open SMTP connection to verify that the dispatcher invokes the sender with the composed message.

Mockito example:

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.times;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.mail.javamail.JavaMailSender;

class WelcomeMailDispatcherTest {

    @Test
    void sendsComposedMimeOnce() throws Exception {

        JavaMailSender sender =
                Mockito.mock(JavaMailSender.class);

        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage()).thenReturn(message);

        WelcomeMailDispatcher dispatcher =
                new WelcomeMailDispatcher(
                        sender,
                        new WelcomeMimeComposer()
                );

        dispatcher.send("student@example.net");

        verify(sender, times(1)).send(message);
    }
}
~~~

**Mockito verification** confirms the invocation. It does not prove:

- That the SMTP server received the message.
- That the provider accepted `RCPT TO`/`DATA`.
- That the message reached the inbox.
- That the attachment bytes are intact.
- That DNS, TLS, and authentication worked.

Those belong in integration tests or appropriate end-to-end tests.

## 32. Testing Attachment and Inline Image Bytes

Checking only the filename and `Content-Type` is not enough. A PDF attachment could be **0 bytes** if a resource is broken and the code fails to catch it early.

For deterministic test files, you can:

1. Read the expected resource from the classpath.
2. Locate the matching body part in the MIME tree.
3. Read the part's content input stream.
4. Compare bytes or SHA-256 hashes against the expected resource.

Reading the resource:

~~~java
import org.springframework.core.io.ClassPathResource;

byte[] expectedPdf = new ClassPathResource(
        "mail/attachments/welcome-guide.pdf"
).getInputStream().readAllBytes();
~~~

Reading the body part:

~~~java
byte[] actualPdf;
try (var input = pdfPart.getInputStream()) {
    actualPdf = input.readAllBytes();
}
~~~

where **pdfPart** is the **Part** located by the MIME traversal helper from the previous section. Compare them:

~~~java
org.junit.jupiter.api.Assertions.assertArrayEquals(
        expectedPdf, actualPdf
);
~~~

This tests **attachment content**, not merely its filename.

For large files, tests do not need to load all bytes into RAM if they stream and compare hashes; this exercise uses small files for convenience.

## 33. Integration Testing with an SMTP Capture Server

After testing MIME composition, verify sending through an SMTP capture server. Example architecture:

~~~text
JUnit / Spring Boot test
        |
        v
WelcomeMailService
        |
        v
JavaMailSender configured to test SMTP
        |
        v
Mailpit / GreenMail / equivalent SMTP capture
        |
        v
Read received message
        |
        +-- Subject
        +-- To/From
        +-- HTML with cid
        +-- Inline PNG
        +-- PDF attachment
~~~

A test flow:

1. Start the SMTP test server in an isolated environment.
2. Configure the Spring test profile to point `JavaMailSender` to that server.
3. Call **sendWelcomeMail("student@example.net")**.
4. Retrieve the message from the test server.
5. Verify recipients, MIME tree, `Content-ID`, and attachment bytes.
6. Ensure the test cleans up the mailbox/server afterward.

**Never use a production SMTP account as a test server**, especially when attachments are documents not cleared for external sending.

### What Still Needs Manual Inspection?

Mail clients such as Gmail, Outlook, Apple Mail, and corporate webmail render emails differently. An SMTP capture server normally shows raw MIME and an HTML preview; it does not fully represent every client.

When multi-client support is required, perform real rendering checks in an authorized **test inbox**, especially for emails with inline images and attachments.

## 34. Inspecting Raw MIME Structure When Troubleshooting

If an image fails to display, one diagnostic step is inspecting the raw MIME source:

~~~text
Content-Type: multipart/mixed; boundary="outer"

--outer
Content-Type: multipart/related; boundary="inner"

--inner
Content-Type: text/html; charset=UTF-8

<img src="cid:brandLogo">

--inner
Content-Type: image/png
Content-ID: <brandLogo>
Content-Disposition: inline

[encoded PNG bytes]

--outer
Content-Type: application/pdf
Content-Disposition: attachment; filename="welcome-guide.pdf"

[encoded PDF bytes]
~~~

Actual raw MIME contains additional headers and encoding boundaries; the diagram above omits details intentionally.

Verify:

- Does the HTML have the exact **cid:brandLogo**?
- Does the MIME image part have **Content-ID: `<brandLogo>`**?
- Is the part's `Content-Type` set to `image/png`?
- Does the image part contain valid bytes?
- Does the attachment have `Content-Disposition: attachment` and a filename?
- Are multipart boundaries generated cleanly?

If a particular email client struggles with a certain structure, try a more compatible MIME mode rather than assuming Spring Mail has a bug.

## 35. Issue: Image Appears as an Attachment Instead of Inside HTML

Some email clients display inline images in the attachment list as well. That **does not necessarily** indicate broken code; the client's UI decides how to present parts.

Check the causes:

1. Did you use **addInline(...)** rather than **addAttachment(...)**?
2. Does HTML reference the exact **cid:...** ID?
3. Was **setText(...)** called before **addInline(...)**?
4. Does MIME have **multipart/related** grouping HTML and the resource compatibly?
5. Is the client blocking images or stripping `img` tags via sanitization?
6. Is the file truly a valid PNG/JPEG?
7. Are there duplicate `Content-ID` headers?

Do not fall back to base64 data URIs in HTML by default. Many email clients limit or strip **data:image/...;base64,...**, whereas **cid:** is the standard mechanism for inline MIME resources.

## 36. Issue: ClassPathResource Cannot Find the File

Example:

~~~text
FileNotFoundException:
class path resource [mail/images/brand-logo.png]
cannot be opened because it does not exist
~~~

Common causes:

- File placed in **src/test/resources** instead of **src/main/resources**, so it exists in tests but is missing in production.
- Path passed to `ClassPathResource` includes **src/main/resources/**.
- Case mismatch between Windows and Linux.
- File not committed or packaged into the artifact.
- Maven/Gradle resource filtering or build config excludes the extension.
- Worker running an older JAR lacking the resource.
- Resource path built from tenant config pointing to the wrong location.

Resolution:

1. Check the physical file in the source project.
2. Inspect the built artifact to confirm the path exists under the classpath root.
3. Verify exact filename and casing.
4. Use **ClassPathResource.exists() / isReadable()** for early detection.
5. Use **getInputStream()** or pass the `Resource` to the helper rather than requiring a physical `File`.

**Never add a workaround** that reads from a relative working-directory path when deploying a Spring Boot JAR. That only works accidentally in an IDE and fails after deployment.

## 37. Issue: Image Shows in IDE but Disappears After Building a JAR

In an IDE, resource directories may resolve as real files, making code like this seem fine:

~~~java
File logo = new File(
        "src/main/resources/mail/images/brand-logo.png"
);
~~~

Once packaged into a JAR, **src/main/resources/...** is no longer a runtime filesystem path. Replace it with:

~~~java
ClassPathResource logo = new ClassPathResource(
        "mail/images/brand-logo.png"
);
~~~

and:

~~~java
helper.addInline("brandLogo", logo, "image/png");
~~~

To inspect an archive without running it, list the JAR entries using your build environment's tools. In a Spring Boot executable JAR, resources normally live under **BOOT-INF/classes/**; with other packaging layouts, paths may differ.

Never open the archive with OS-specific paths and extract resources to a fixed folder just to send emails; that adds deployment complexity, cleanup burdens, and concurrency bugs.

## 38. Issue: Logo Does Not Appear Even with a Matching CID

It can happen that:

~~~text
cid:brandLogo  = valid
Content-ID     = <brandLogo>
Image bytes    = valid
Yet the email client still hides the image
~~~

Causes outside the classpath include:

- The email client's **remote/inline image display policy**.
- HTML sanitizer removing or rewriting the tag.
- Differing client support for MIME multipart.
- Message flagged as suspicious or sent from an unauthenticated domain.
- CSS/layout giving the image zero size or hiding it.
- `Content-Type` mismatching the actual bytes.
- Corrupted image or unsupported format in that client.
- `img` tag using a broken URL or unencoded characters in the CID.

To investigate, separate the layers:

1. **Resource loading:** were the PNG bytes actually loaded?
2. **MIME composition:** are `Content-ID` and the `image/png` part right?
3. **SMTP submission:** did the provider receive the message intact?
4. **Mail rendering:** does a specific client display the image?

Never glance at a single Gmail/Outlook screen and conclude the Spring code is broken.

## 39. Why Do Some Clients Prefer multipart/related?

An email with HTML:

~~~html
<img src="cid:brandLogo">
~~~

needs resources linked to the HTML. **multipart/related** expresses related content parts, signaling to clients that the image is referenced by the body.

When the email also carries an independent PDF attachment, **multipart/mixed** typically wraps the HTML/inline content.

Spring supports several multipart modes:

- **MULTIPART_MODE_NO:** no multipart.
- **MULTIPART_MODE_MIXED:** plain `multipart/mixed`.
- **MULTIPART_MODE_RELATED:** `multipart/related`.
- **MULTIPART_MODE_MIXED_RELATED:** combines `mixed` with `related`.

For this exercise combining **both inline PNG and PDF attachment**, **MULTIPART_MODE_MIXED_RELATED** intentionally groups them properly.

If special compatibility with legacy clients is required, inspect the generated MIME and select an appropriate mode rather than switching modes blindly just because one client displays attachments unexpectedly.

## 40. Designing HTML for Emails with Inline Images

Email HTML should be simple and resilient when clients strip part of the CSS.

Example:

~~~html
<!doctype html>
<html lang="en">
<body style="margin:0;padding:16px;font-family:Arial,sans-serif">
  <table role="presentation"
         cellpadding="0"
         cellspacing="0"
         style="max-width:600px;width:100%">
    <tr>
      <td>
        <img src="cid:brandLogo"
             width="180"
             alt="Application logo"
             style="display:block;border:0">
      </td>
    </tr>
    <tr>
      <td>
        <h1>Welcome</h1>
        <p>We have attached the
           welcome-guide.pdf document to help you get started.</p>
      </td>
    </tr>
  </table>
</body>
</html>
~~~

Guidelines:

- Provide meaningful **alt text** when images are blocked.
- Keep logos small with explicit display dimensions.
- Avoid depending on JavaScript or complex CSS; many clients block them.
- Important information must exist as text, not solely inside images.
- Include a **plain-text alternative** for clients where HTML is disabled.
- Never insert unescaped/unsanitized user-controlled HTML into the body.

**Inline images never replace essential content:** if the logo is hidden, the email must still convey the core message.

## 41. Escaping User Content When Building HTML

Suppose the service receives a customer name:

~~~text
customerName = <img src=x onerror=...>
~~~

If concatenated directly:

~~~java
String html = "<p>Hello " + customerName + "</p>";
~~~

the HTML contains untrusted input. Even though many mail clients sanitize HTML, applications must never rely on client-side sanitization to protect recipients.

Better approach:

- Use a template engine with proper **HTML escaping**.
- Separate controlled HTML markup from user-supplied text.
- Validate content and lengths before rendering.
- Prevent user input from injecting CIDs, remote image URLs, scripts, or event handlers.
- Restrict allowed schemes when building links.

With **Thymeleaf**, distinguish escaped expressions from unescaped expressions. In emails, render user-supplied text as escaped by default.

Template example:

~~~html
<p th:text="'Hello ' + ${customerName}">
  Hello!
</p>
<img src="cid:brandLogo" alt="Application logo">
~~~

**th:text** inserts text with escaping. Only use unescaped HTML from trusted sources sanitized under an explicit policy.

## 42. Does Using a Template Engine Change How addInline Works?

No. A template engine only renders the **HTML string**, while **MimeMessageHelper** still builds the CID-linked MIME part.

Flow:

~~~text
Thymeleaf/Freemarker/template renderer
       |
       v
HTML String with src="cid:brandLogo"
       |
       v
MimeMessageHelper.setText(plainText, html)
       |
       v
MimeMessageHelper.addInline("brandLogo", ClassPathResource)
       |
       v
MimeMessageHelper.addAttachment("welcome-guide.pdf", ClassPathResource)
       |
       v
JavaMailSender.send(...)
~~~

A common mistake in templates is writing:

~~~html
<img src="/mail/images/brand-logo.png">
~~~

That is a relative **web page** path, not a classpath path or CID that email clients understand. When opened outside your web app, the client has no website base URL.

Use:

~~~html
<img src="cid:brandLogo">
~~~

for MIME inline images, or an application-chosen public HTTPS URL when using remote images.

## 43. Inline CID vs. Remote HTTPS Images from a CDN

| Criterion | CID Inline | HTTPS Remote Image |
|---|---|---|
| Image inside MIME? | Yes | No |
| Requires client network fetch on open? | Usually no external fetch needed | Yes, if client permits |
| Email size | Increases by image bytes | Smaller, holds only URL |
| Can client block/hide it? | Yes | Yes |
| Updating image after send | Hard, bytes are embedded | URL content can change, subject to caching |
| Open tracking | Not a tracking mechanism | Affected by proxy/privacy caching |
| Access management | Resource travels inside sent email | Requires managing remote hosting/URL |

No approach guarantees images always render. For small logos and this practice project, **CID** teaches MIME multipart and avoids external CDN dependencies.

For marketing emails with many large assets, remote images reduce email size, but require weighing privacy, caching, reachability, and provider policies.

## 44. Attachment Sizes and SMTP Limits

Example PDF file:

~~~text
Original PDF: 10 MB
Base64 MIME transport: larger than original bytes
Additional headers/boundaries: extra overhead
~~~

MIME encoding significantly inflates total message size. Provider limits apply to the **entire message**, not just the raw file.

Best practices:

1. Enforce file size limits before composing.
2. Limit total attachment count and total message size.
3. Never assume every SMTP server accepts a 25 MB file across all domains.
4. For large documents, consider an **authorized HTTPS download link** instead of an attachment.
5. When using expiring links, pick an expiration window matching recipient needs.
6. Never split a sensitive file across multiple emails as a default workaround.

Checking a classpath file's size:

~~~java
ClassPathResource guide = new ClassPathResource(
        "mail/attachments/welcome-guide.pdf"
);

long bytes = guide.contentLength();
long maxBytes = 5L * 1024 * 1024;

if (bytes > maxBytes) {
    throw new IllegalStateException(
            "Welcome guide is larger than configured limit"
    );
}
~~~

**contentLength()** may open a stream depending on the resource implementation. This is an example limit, not a built-in Spring Mail limit.

## 45. Charset, Unicode, and Vietnamese Filenames

Vietnamese content requires a consistent charset:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

This ensures Vietnamese Subjects and bodies are encoded cleanly. Accented filenames such as:

~~~text
Hướng dẫn bắt đầu.pdf
~~~

may be encoded using MIME parameters or encoded-words depending on Jakarta Mail's implementation and configuration.

Because mail clients do not all handle Unicode filenames uniformly, if broad compatibility is required, use an ASCII display filename:

~~~text
Huong-dan-bat-dau.pdf
~~~

The HTML and plain-text bodies can still use normal Unicode Vietnamese text.

Never pre-encode the Subject manually with Base64 before calling **helper.setSubject(...)** unless you understand Jakarta Mail's encoding behavior, as that risks double-encoding.

## 46. Do Not Confuse Inline Resources with Embedded Base64 HTML

Two distinct techniques:

**CID inline MIME**

~~~html
<img src="cid:brandLogo" alt="Logo">
~~~

Matched with a separate part:

~~~text
Content-Type: image/png
Content-ID: <brandLogo>
Content-Disposition: inline
~~~

**Data URI**

~~~html
<img src="data:image/png;base64,iVBORw0...">
~~~

Here the image bytes sit inside the HTML attribute and **do not** reference a `Content-ID` part.

Many email clients strip or refuse to render data URIs. Since this lesson covers adding classpath resources with Spring Mail, use **addInline(...) + cid:** instead of manually base64-encoding images into HTML.

## 47. Static Resources and Versioning

When deploying a new release of the application, the file:

~~~text
mail/images/brand-logo.png
~~~

may change. Already-sent emails retain the old MIME bytes; unsent emails will use the asset bundled in the current worker artifact.

If a notification is enqueued before deployment and sent afterward:

~~~text
Day 1:
  Outbox N100 created
  logo v1 in app artifact

Day 2:
  Deploy new app
  logo v2 in worker artifact

Day 2:
  N100 gets sent with logo v2
~~~

This is fine for a generic brand logo, but for legal/contract documents or auditable files, you must **pin the asset version**:

~~~text
asset_id = welcome-guide
asset_version = 2026-11
asset_ref = immutable storage ref
~~~

Never expect the **current JAR's** classpath to carry static assets from every historical version if long-term replay is required.

## 48. When Should You Not Use the Classpath for Attachments?

To keep scope clear, evaluate each case:

| File to Send | Classpath Suitable? | Recommendation |
|---|---|---|
| Default logo bundled with the app | **Yes** | Versioned PNG/JPEG |
| Public guide sent to all recipients | **Yes** | Static PDF, updated via deploy |
| Product-version installation guide | **Conditionally** | Track document versions clearly |
| Invoice with customer name/prices | **No** | Generate + separate durable storage |
| User-uploaded file | **No** | Object storage + validation |
| Confidential file changing frequently | **No** | Secure storage, authorization, retention |
| Document subject to per-user deletion | **No** | Record-managed data store |
| Campaign email with per-user QR code | **No** | Generate bytes per user, use repeatable resource |

For dynamic bytes:

~~~java
byte[] generatedPdf = invoiceGenerator.render(invoiceId);

helper.addAttachment(
        "invoice.pdf",
        new org.springframework.core.io.ByteArrayResource(generatedPdf),
        "application/pdf"
);
~~~

This shows **ByteArrayResource** fits small-to-medium dynamic byte arrays, not holding hundreds of large files in heap. Furthermore, **invoiceGenerator** and `invoiceId` must be authorized per tenant; the snippet only demonstrates passing the resource to the helper.

For large files or async sends, use a **storage reference** with clear authorization and lifecycle management.

## 49. Data Security in Attachments and Inline Images

Not every file on the classpath belongs in an email.

Resources that must never be attached simply because they sit on the classpath:

- **application.yml** containing secrets or config.
- Private keys or TLS certificates.
- Credential or service-account JSON files.
- Internal documents not intended for recipients.
- Sample resources containing real personal data.
- Draft templates or debug fixtures.

Applications should use **allowlisted mail assets**:

~~~text
WELCOME_LOGO
WELCOME_GUIDE
SUPPORT_ICON
TERMS_PDF_V1
~~~

Then map IDs to developer-controlled classpath paths. Never let HTTP requests pass raw filenames or paths into `ClassPathResource`.

### Resources Sent Externally Leave Your Control

Once an email is accepted, recipients can save, forward, or extract attachments and inline images. **Never put sensitive secrets into an image just because it is "inline" rather than an attachment.**

If document access must be revocable later, send a link to a service enforcing authentication, authorization, and expiration instead of attaching permanent bytes.

## 50. Protecting Sender, Recipients, and HTML Content

A minimal production flow requires:

1. **Sender address** within an authorized domain/profile list.
2. **Recipient** validated per business rules; never build an open relay.
3. Subject and display filenames free of CR/LF or malicious characters.
4. User-supplied text HTML-escaped.
5. HTML links using HTTPS with scheme/domain validation as needed.
6. Inline resources and attachments bounded in count and size.
7. Raw bodies, attachments, signed URLs, and SMTP credentials excluded from regular logs.
8. Consent and suppression policies enforced per email type.
9. Post-transaction notifications suppressed if the business transaction rolled back or became invalid.
10. Accurate MIME content types; never label an untrusted file as "image/png" by filename alone.

**ClassPathResource is not a security boundary**. It merely accesses resources; the application remains responsible for send permissions and data exposure.

## 51. Observability and Troubleshooting

For emails with attachments and inline images, log useful metadata such as:

~~~text
notification_id: N100
message_kind: WELCOME
template_version: v3
asset_catalog: WELCOME_LOGO,WELCOME_GUIDE
asset_version: 2026-11
smtp_provider: test-smtp
attempt: 1
outcome: SUBMITTED
~~~

Do not log:

~~~text
plaintext recipient email (unless required and access-controlled)
full HTML
attachment bytes
base64 MIME
SMTP password
auth token
secret links
~~~

When investigating **RESOURCE_MISSING**, log the **asset ID**, **artifact version**, and controlled static path. Never log user-supplied paths.

Useful metrics:

| Logical Metric | Purpose |
|---|---|
| **mail.compose.success** | Messages whose MIME was composed successfully |
| **mail.compose.failure** | MIME/resource preparation failures |
| **mail.asset.missing** | Missing required asset occurrences |
| **mail.attachment.size** | Attachment size distribution |
| **mail.smtp.submission.duration** | Latency submitting to SMTP |
| **mail.smtp.attempts** | Attempts broken down by outcome |
| **mail.smtp.unknown** | Attempts with unknown SMTP acceptance |

Never use **recipient**, **notificationId**, or arbitrary attachment filenames as metric labels, as that causes high cardinality and information leakage.

### Do Not Conflate Preparation Errors with Provider Outages

A missing classpath file is a **composition/configuration failure** requiring a build or deployment fix. SMTP provider outages typically require retries, backoff, or failover per policy.

When using an outbox, distinguish:

~~~text
PREPARATION_FAILED / RESOURCE_NOT_FOUND
RETRY_WAIT / SMTP_451
FAILED / SMTP_REJECTED_PERMANENT
UNKNOWN / FINAL_REPLY_NOT_RECEIVED
SUBMITTED / SMTP_ACCEPTED
~~~

Never let a worker rapidly retry forever when the JAR is missing **welcome-guide.pdf**: every retry will fail to locate the same missing resource.

## 52. Practical Troubleshooting Table

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| `ClassPathResource.exists()` is false | Wrong path/casing or not packaged | Check `src/main/resources` and build artifact |
| Works in IDE, fails in JAR | Relative `File` or `getFile()` used | Switch to `ClassPathResource`/`InputStream` |
| HTML renders, image blank | Wrong CID, broken image, client blocking | Check HTML `src`, `Content-ID`, and image part |
| Image appears as attachment | Client UI behavior or MIME mode | Check `multipart/related` and `addInline` |
| PDF missing | Forgot `addAttachment` or missing source | Check MIME parts and resource |
| Received PDF is 0 bytes | Non-repeatable stream source | Use repeatable `InputStreamSource`/bytes |
| Garbled filename characters | Encoding/filename handling | UTF-8, MIME parameters, try ASCII filename |
| Broken Vietnamese Subject | Inconsistent charset config | Helper charset UTF-8 |
| Oversized email rejected | MIME overhead / attachment size limit | Measure total message size; use download link |
| SMTP 535 authentication failed | Wrong credentials or provider policy | Verify secrets and SMTP config |
| Temporary SMTP 451 | Temporary provider/recipient error | Backoff within deadline |
| SMTP 550 5.7.x | Policy, auth, or reputation rejection | Do not immediately assume invalid recipient |
| Timeout after `DATA` | Uncertain acceptance | `UNKNOWN` and reconciliation |
| Assets differ across pods | Mismatched deployed artifact versions | Pin asset versions, check rollout |
| Tenant A logo sent to Tenant B | Wrong sender/template mapping | Tenant-scoped assets and authorization |
| Attachment contains secrets | Missing allowlist or path injection | Restrict asset catalog; run incident response |

### When Troubleshooting, Identify the Layer First

~~~text
Is the file in the source tree?
        |
        v
Is the resource on the artifact classpath?
        |
        v
Did MimeMessageHelper create the right parts?
        |
        v
Did the SMTP server accept it?
        |
        v
Does the email client display it properly?
~~~

Layering prevents confusing packaging bugs with SMTP errors, or email client rendering quirks with `ClassPathResource` failures.

## 53. Extended Exercise: Welcome Email with Two Images

Add a file:

~~~text
src/main/resources/mail/images/help-icon.png
~~~

Requirements:

1. Keep the logo displayed at the top of the email.
2. Add the help icon next to the guide link.
3. Give the two resources distinct CIDs.
4. Keep HTML readable even if images are hidden.
5. Keep both the plain-text alternative and the PDF attachment.

Hint:

~~~java
helper.setText(plainText, html);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/images/brand-logo.png"),
        "image/png"
);

helper.addInline(
        "helpIcon",
        new ClassPathResource("mail/images/help-icon.png"),
        "image/png"
);
~~~

HTML:

~~~html
<img src="cid:brandLogo" alt="Logo">
<p>
  See the guide
  <img src="cid:helpIcon" alt="Help" width="20">
</p>
~~~

Open the SMTP capture inbox and inspect the MIME tree: there should be **two image parts** with **two `Content-ID` headers**.

## 54. Extended Exercise: Multiple Versioned Attachments

Add:

~~~text
src/main/resources/mail/attachments/terms-v1.pdf
src/main/resources/mail/attachments/security-guide.pdf
~~~

Requirements:

- Specify the **application/pdf** media type.
- Use clear display filenames.
- Avoid duplicate files from broken template mappings.
- Never accept arbitrary paths from REST requests.
- Keep total message size under the configured cap.
- Record the asset versions when composing the email.

Hint:

~~~java
helper.addAttachment(
        "terms-v1.pdf",
        new ClassPathResource(
                "mail/attachments/terms-v1.pdf"
        ),
        "application/pdf"
);

helper.addAttachment(
        "security-guide.pdf",
        new ClassPathResource(
                "mail/attachments/security-guide.pdf"
        ),
        "application/pdf"
);
~~~

In this exercise, files are sample documents without sensitive data. In real business flows, verify the recipient is authorized to receive each document.

## 55. Extended Exercise: Selecting Inline Images by Template

Suppose there are two templates:

~~~text
WELCOME:
  brandLogo -> mail/images/brand-logo.png
  attachment -> welcome-guide.pdf

SECURITY_TIPS:
  shieldIcon -> mail/images/shield.png
  attachment -> security-guide.pdf
~~~

One design approach:

~~~text
TemplateKind
       |
       v
Trusted asset catalog
       |
       +-- allowed inline resource IDs
       +-- allowed attachments
       +-- content types
       +-- display filenames
       |
       v
MimeMessageHelper
~~~

Never let callers pass:

~~~text
template=SECURITY_TIPS
attachmentPath=application-prod-secrets.yml
~~~

and forward the raw path directly into `ClassPathResource`. **Template kinds and asset IDs must come from an allowlist** or strictly authorized, validated administrative config.

## 56. Practice Project Completion Checklist

**Project Setup**

1. Is **spring-boot-starter-mail** added?
2. Are you using the right namespace (**jakarta.mail** vs. **javax.mail**) for your Spring version?
3. Are the PNG and PDF placed under **src/main/resources/mail/**?
4. Is resource path casing exact?
5. Does the SMTP test profile point to a capture server rather than production recipients?

**MIME Construction**

6. Are you using **MimeMessage**, not just `SimpleMailMessage`?
7. Is multipart enabled with a mode suitable for related + attachments?
8. Is charset set to **UTF-8**?
9. Are both plain-text alternative and HTML body included?
10. Is **setText(...)** called before **addInline(...)**?
11. Does HTML have **src="cid:brandLogo"**?
12. Does **addInline("brandLogo", ClassPathResource, "image/png")** use the exact same CID?
13. Does **addAttachment(..., ClassPathResource, "application/pdf")** assign the right filename?
14. Did you avoid prefixing **src/main/resources/** onto `ClassPathResource` paths?
15. Did you avoid **getFile()** when running from an executable JAR?
16. Are resources re-readable if MIME needs multiple passes?

**Security and Operations**

17. Are sender and recipients properly authorized?
18. Are asset paths allowlisted?
19. Is user-supplied HTML escaped?
20. Are attachment sizes and counts bounded?
21. Do logs omit raw bodies, tokens, and attachment bytes?
22. Are SMTP credentials stored in secret management?
23. Are automatic emails on application restart prevented unless explicitly intended?

**Testing**

24. Do unit tests verify Subject, HTML, and MIME parts?
25. Are the inline image's `Content-ID` and `Content-Type` checked?
26. Are the PDF attachment and its bytes checked?
27. Did you test sending through an SMTP capture server when appropriate?
28. Did you inspect raw MIME to verify `multipart/related` and `mixed`?
29. Did you test running the packaged JAR rather than only inside the IDE?
30. Did you check representative clients if Gmail/Outlook support is required?

## 57. Summary

In the **"Adding Attachments and Inline Images from the Classpath"** project, three key pieces work together:

~~~text
Classpath resources
    |
    +-- brand-logo.png
    +-- welcome-guide.pdf
    |
    v
MimeMessageHelper
    |
    +-- setText(plainText, html)
    +-- addInline("brandLogo", ClassPathResource, "image/png")
    +-- addAttachment("welcome-guide.pdf",
    |                 ClassPathResource, "application/pdf")
    |
    v
JavaMailSender.send(MimeMessage)
~~~

Key takeaways:

1. **ClassPathResource** provides portable access to resources packaged with the app, even when running from a JAR.
2. **Attachments** are downloadable files; **inline images** are MIME resources linked to HTML via **Content-ID / cid:**.
3. **MULTIPART_MODE_MIXED_RELATED** structures HTML, inline images, and attachments with clear intent.
4. **setText before addInline** is the recommended call order for broad email client compatibility.
5. **Specify `Content-Type` and charset explicitly** instead of relying on filename detection and platform defaults.
6. **Never call `getFile()` for resources inside a JAR**, and never pass a single-use stream when APIs may read multiple times.
7. **Separate MIME composition from SMTP transport** so you can test part structures without sending real mail.
8. **Clients render differently**; verify MIME correctness first before diagnosing client display quirks.
9. **The classpath is for static assets**, not personal data stores, dynamically generated invoices, or user uploads.
10. **Send permissions, secrets, exception handling, and delivery semantics** remain the application's responsibility even when the helper API looks simple.

**The expected outcome is an email with both plain-text and HTML content, a logo embedded inside the body via CID, a PDF delivered as a separate attachment, and both resources loaded from the classpath independently of the host machine's filesystem paths.**





