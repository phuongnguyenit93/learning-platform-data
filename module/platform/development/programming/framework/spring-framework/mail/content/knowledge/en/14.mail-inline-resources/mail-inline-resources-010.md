# Do Not Use Local File Paths in Outbound HTML with Spring Framework Mail

When building HTML emails in Spring Framework Mail, a common mistake is putting a server filesystem path into the `src` attribute of an `<img>` tag:

```html
<!-- These approaches are unsuitable for emails sent to others -->
<img src="C:\app\images\logo.png" alt="Logo">
<img src="file:///var/app/images/logo.png" alt="Logo">
<img src="/opt/application/assets/logo.png" alt="Logo">
<img src="../images/logo.png" alt="Logo">
```

Those paths only have meaning within a specific filesystem or context. Emails are delivered to recipients' mailboxes; the mail client on a recipient's device has no access to the Spring server's disks, directories, or containers. Therefore, the image usually renders as broken, even though the file exists on the machine running the application.

**Never put filesystem paths into email HTML.** If an image must travel with the message, embed it as a MIME inline resource and reference it with `cid:...`. If the image can be loaded from the web, use an absolute HTTPS URL controlled by your application. If a document needs to be downloaded separately, attach it using the attachment API.

This lesson explains the boundary between local server paths and email content, how to use `MimeMessageHelper.addInline(...)` with classpath, filesystem, or byte-array resources, how to use remote images, and how to manage resource lifecycles and security.

## 1. Why do local file paths fail in emails?

When a Spring application renders HTML, the HTML string is placed inside the email's MIME body. For example:

```html
<img src="C:\app\images\logo.png" alt="Logo">
```

The email contains only the **character string** `C:\app\images\logo.png`. It does not automatically transmit the file at that location. When the recipient opens the email, the mail reader tries to interpret the `src` value in its own environment. A Windows path on the sending server is not a path on the recipient's Windows machine, and a Linux path inside a container is not a path on a mobile phone.

Example:

```text
Spring server
  C:\app\images\logo.png
          |
          | HTML contains only the path string
          v
      SMTP message
          |
          v
Recipient's mail client
  No access to the Spring server's filesystem
```

A file may exist and be readable by the application's service account, yet that does not create a link the recipient can access. Email does not share filesystems between machines.

### Types of paths to distinguish

| Value type in `src` | Example | Outcome in email |
|---|---|---|
| Windows path | `C:\app\images\logo.png` | Meaningless on the recipient's machine |
| File URI | `file:///var/app/logo.png` | Points to client-side filesystem or is blocked by client; never points to sending server |
| Linux absolute path | `/opt/app/logo.png` | Not a web URL; no matching resource exists on the client |
| Relative path | `../images/logo.png` | No reliable filesystem/web base path exists in email |
| Absolute HTTPS URL | `https://static.example.org/logo.png` | Client can fetch from the web if policy permits |
| CID | `cid:brand-logo` | References a MIME part embedded inside the email itself |
| Data URI | `data:image/png;base64,...` | Blocked or unsupported by some clients; avoid as default approach |

### Local paths can leak internal information

Besides failing to display, paths like `/srv/apps/customer-prod/tenant-a/reports/secret.pdf` can expose directory names, deployment layout, or internal system details. Never include physical paths, drive letters, server usernames, or mount points in email HTML, subjects, or headers.

Even if some mail clients let a user click a `file://` link in special environments, do not rely on that behavior. Emails sent over the Internet require content that works independently of the sender's local filesystem.

## 2. Choosing how to include images in emails

For images in HTML emails, there are two common approaches:

1. **Remote image:** HTML points to a public HTTPS URL or an appropriately authorized URL.
2. **Inline resource:** image bytes are packaged inside the MIME message and HTML references it via Content-ID using `cid:`.

Example:

```html
<!-- Remote image: mail client fetches image from the web -->
<img src="https://static.example.org/mail/logo.png"
     alt="Example Logo" width="140">

<!-- Inline resource: image lives inside the same MIME message -->
<img src="cid:brand-logo"
     alt="Example Logo" width="140">
```

These two `src` values are not interchangeable. `https://...` requires the client to reach a web server; `cid:brand-logo` requires the email to carry a MIME part with the matching Content-ID.

| Criterion | Remote image | Inline resource (CID) |
|---|---|---|
| Image data | On web server/CDN | Inside the MIME message |
| HTML `src` | Absolute HTTPS URL | `cid:content-id` |
| Requires `addInline` | No | Yes |
| Network needed when opening image | Usually yes, unless cached/proxied | No need to fetch that image from the web |
| Email size | Smaller | Increases with image size and MIME encoding |
| Depends on live URL | Yes | No |
| Image-blocking policy | May be blocked | Can also be restricted by clients |
| Best suited for | Banners, product photos, shared assets | Small logos, per-email charts, images that must travel with the message |

No method guarantees images will always display across every mail client. Add `alt` text, keep important information in text, and test with the mail apps your product supports.

## 3. The right way for images stored on the server: embed via CID

If the image file currently lives on the machine running the app and you want to send it with the email, read the file as a **MIME resource**. Do not write the local path into HTML. Instead:

1. Assign a Content-ID, such as `brand-logo`.
2. In HTML, use `src="cid:brand-logo"`.
3. Call `MimeMessageHelper.addInline("brand-logo", resource, "image/png")`.
4. Send the message after setting the body and inline resources.

Example:

```html
<img src="cid:brand-logo" alt="Store logo" width="140">
```

The HTML knows only the Content-ID. Reading the file from the classpath or filesystem is handled by Java code.

### Logical MIME structure

A message with HTML and an inline image can have the structure:

```text
MimeMessage
└── multipart/related
    ├── text/html; charset=UTF-8
    │   <img src="cid:brand-logo">
    └── image/png
        Content-ID: <brand-logo>
        Content-Disposition: inline
```

If the email also has plain text, the body section may contain `multipart/alternative` inside `multipart/related`. If there are standalone attachments, `multipart/mixed` can wrap the outside. `MimeMessageHelper` manages creating the MIME parts and boundaries; the application does not need to assemble raw MIME source manually.

### Content-ID must match the CID in HTML

With:

```java
helper.addInline("brand-logo", resource, "image/png");
```

the HTML must use:

```html
<img src="cid:brand-logo" alt="Logo">
```

In raw MIME source, the header may be formatted as `Content-ID: <brand-logo>`. When calling `addInline`, pass the string ID `brand-logo`; do not manually add angle brackets. Each image needs its own Content-ID that remains stable within that message.

**A CID is not a file path.** It is the identifier of a MIME part inside the email. The mail client looks up the image inside the current message rather than accessing the server's filesystem.

## 4. Using ClassPathResource for images packaged with the application

For shared logos, icons, or static images, place the files in resources:

```text
src/main/resources/
└── mail/
    └── images/
        └── logo.png
```

When the application is packaged as a JAR, resources may reside inside the JAR rather than as standalone physical files at a fixed path. Therefore, read via Spring's `Resource` abstraction instead of constructing a path like `src/main/resources/mail/images/logo.png`.

Example:

```java
import org.springframework.core.io.ClassPathResource;

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
```

`ClassPathResource` reads the resource from the classpath whether the app runs in an IDE or from a packaged JAR. The image content is placed into a MIME part when the email is sent.

### Complete Spring service with a classpath logo

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public WelcomeMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {

        String plainText = """
                Welcome to Example!

                Visit https://example.org to get started.
                If you need help, contact support@example.org.
                """;

        String htmlText = """
                <!doctype html>
                <html lang="en">
                  <body>
                    <p>
                      <img src="cid:brand-logo"
                           alt="Example Logo"
                           width="140">
                    </p>
                    <h2>Welcome to Example!</h2>
                    <p>
                      Visit
                      <a href="https://example.org">Example</a>
                      to get started.
                    </p>
                    <p>Need help? support@example.org</p>
                  </body>
                </html>
                """;

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Welcome to Example");
        helper.setText(plainText, htmlText);

        // Set HTML first, then add the MIME part referenced by the CID.
        helper.addInline(
                "brand-logo",
                new ClassPathResource("mail/images/logo.png"),
                "image/png");

        mailSender.send(message);
    }
}
```

Key points:

- `MimeMessageHelper(message, true, "UTF-8")` enables multipart so the message can hold multiple MIME parts.
- `setText(plainText, htmlText)` creates two alternative body representations.
- `src="cid:brand-logo"` references the image added via `addInline`.
- `ClassPathResource` reads the file from resources without exposing any local path in HTML.
- `mailSender.send(message)` dispatches a single message containing the content and image.

With Spring Boot, `JavaMailSender` is typically configured via `spring.mail.*`. The `From` address should come from verified sender configuration, never directly from user input.

### API call order

Follow this sequence:

1. Create `MimeMessage`.
2. Create `MimeMessageHelper` in multipart mode.
3. Set From, To, Subject, and the body with `setText(...)`.
4. Call `addInline(...)` for each image referenced by HTML.
5. Add any other attachments if needed.
6. Call `JavaMailSender.send(...)`.

Spring recommends calling `setText(...)` before `addInline(...)` to avoid compatibility issues in some mail clients and keep the MIME structure organized as expected by the helper.

## 5. Using FileSystemResource for images stored on disk

If an image is created or stored outside the classpath—such as a tenant logo, a chart exported to a file, or a document created in a temp directory—use `FileSystemResource`:

```java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;

Path logoPath = Path.of("/var/app/private-mail/tenant-a/logo.png");

helper.addInline(
        "tenant-logo",
        new FileSystemResource(logoPath),
        "image/png");
```

The HTML still contains only:

```html
<img src="cid:tenant-logo" alt="Company logo">
```

`FileSystemResource` is the byte source used by the application to construct the MIME part. The string `/var/app/private-mail/tenant-a/logo.png` **must not be put into HTML**. When the email is sent, the image is read from the server-side filesystem and packaged into the message.

### Filesystem paths must be controlled by the application

Never accept an arbitrary absolute path from a request and pass it directly into `FileSystemResource`. Unsafe example:

```java
// Never use an arbitrary path supplied by the user.
Path path = Path.of(request.getParameter("imagePath"));
helper.addInline("image", new FileSystemResource(path), "image/png");
```

A user could supply a path pointing outside the permitted image directory, depending on the application process's permissions. Instead, accept a validated asset ID and resolve the file within a configured directory:

```java
Path allowedRoot = Path.of("/var/app/mail-assets").toRealPath();
Path candidate = allowedRoot.resolve(assetRecord.storageName()).normalize();

if (!candidate.startsWith(allowedRoot)) {
    throw new SecurityException("Asset path is outside allowed directory");
}

Path realFile = candidate.toRealPath();
if (!realFile.startsWith(allowedRoot)) {
    throw new SecurityException("Resolved asset escapes allowed directory");
}

helper.addInline(
        "tenant-logo",
        new FileSystemResource(realFile),
        "image/png");
```

This example assumes `assetRecord.storageName()` is a system-managed filename. Checking both the normalized path and the canonical real path defends against certain forms of path traversal and symlink escapes; combine with filesystem permissions, dedicated upload directories, and content-type verification. Never let users dictate arbitrary Content-IDs or access another tenant's assets.

### When the file is temporary

If an image is generated into a temporary directory, ensure the file remains intact until the mail library finishes sending:

```java
Path imagePath = Files.createTempFile("mail-chart-", ".png");
try {
    chartGenerator.writePng(chartData, imagePath);

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");
    helper.setFrom(fromAddress);
    helper.setTo(recipient);
    helper.setSubject("Report chart");
    helper.setText(
            "The chart is embedded in the HTML body.",
            "<p>Chart:</p><img src=\"cid:chart-image\" alt=\"Chart\">");
    helper.addInline(
            "chart-image",
            new FileSystemResource(imagePath),
            "image/png");

    mailSender.send(message);
} finally {
    Files.deleteIfExists(imagePath);
}
```

This is a synchronous pattern: the file is deleted after `send` completes or throws. If sending is queued for a worker to run later, **do not delete the file immediately upon enqueuing**. The worker needs to read the resource at send time; store durable artifacts or manage temp files according to job state and cleanup retention.

## 6. Using ByteArrayResource for in-memory generated images

If the image already exists as a `byte[]` (such as a chart rendered from data, a QR code, or a thumbnail), use `ByteArrayResource`:

```java
import org.springframework.core.io.ByteArrayResource;

byte[] chartPng = chartGenerator.renderPng(chartData);

helper.setText(
        "Your report is ready.",
        """
        <h2>Report</h2>
        <p>Revenue chart:</p>
        <img src="cid:sales-chart" alt="Revenue chart">
        """);

helper.addInline(
        "sales-chart",
        new ByteArrayResource(chartPng),
        "image/png");
```

`ByteArrayResource` provides a fresh `InputStream` from the same byte array whenever requested. This helps because the mail library may read the resource while constructing/sending the MIME message. There is no need to write the byte array to a local path just to reference that path in HTML.

For large files, byte arrays hold the entire payload on the heap. Bound sizes and concurrency; consider `FileSystemResource` or object storage for large resources.

### Comparing common Resources

| Resource | Data source | When suitable |
|---|---|---|
| `ClassPathResource` | Assets packaged in classpath/JAR | Application logos and static images |
| `FileSystemResource` | Files on the server filesystem | Tenant images, dynamic files, or temp files |
| `ByteArrayResource` | In-memory byte array | Dynamically generated or pre-loaded images |
| `InputStreamResource` | An InputStream | Specialized stream sources; watch re-readability |

An `InputStreamSource` passed to the helper should supply a fresh stream each time the library requests it. An `InputStreamResource` wrapping an already-opened and exhausted stream cannot be reused; prefer resources with clear lifecycles.

## 7. Remote images: use absolute HTTPS URLs

If the image lives on a website/CDN and is meant to be fetched over the Internet, put an absolute HTTPS URL in HTML:

```html
<img src="https://static.example.org/mail/brand-logo.png"
     alt="Example Logo"
     width="140"
     style="display:block;max-width:100%;height:auto">
```

Do not use:

```html
<!-- Not valid web URLs for recipients -->
<img src="/assets/logo.png">
<img src="../assets/logo.png">
<img src="file:///var/app/assets/logo.png">
```

Relative URLs lack a stable base URL inside emails. When using remote images:

- Use an absolute HTTPS hostname.
- Ensure the endpoint is reachable from recipients or their mail client proxies.
- Do not require internal login cookies if external recipients must view the image.
- Keep the URL active for as long as the email needs to be viewed.
- Never put secret tokens or sensitive personal data in query strings.
- Add `alt` text and keep important information in text.

Some mail clients block or proxy external images to protect privacy. Thus, a remote image may fail to show even though the URL works in a web browser. If a logo must travel with the message without depending on a web URL, consider CID inline.

## 8. Do not use data URIs as a default substitute

Another option is embedding base64 directly in HTML:

```html
<img src="data:image/png;base64,iVBORw0KGgoAAA..." alt="Logo">
```

This is a **data URI**, not a local path. However, support for data URIs across email clients is inconsistent; some clients strip or refuse to render them. It also inflates the HTML body and makes templates harder to manage.

If you want to carry image bytes inside the email, use a MIME inline resource:

```html
<img src="cid:brand-logo" alt="Logo">
```

and:

```java
helper.addInline(
        "brand-logo",
        new ByteArrayResource(imageBytes),
        "image/png");
```

The CID approach represents images in proper MIME structure, fitting Spring Mail's inline resource API cleanly. Do not convert whole files into base64 strings inside HTML unless you have a specifically verified compatibility requirement.

## 9. Distinguishing inline resources and attachments

An image can be sent as an inline resource or as a regular file attachment. These two approaches serve different purposes:

| API | Purpose | HTML reference |
|---|---|---|
| `helper.addInline(contentId, resource, contentType)` | Supplies a resource referenced by HTML | `src="cid:..."` |
| `helper.addAttachment(filename, resource, contentType)` | Places a file in the attachment list | Does not create a `src` in HTML |

Example of an email with an inline logo and a PDF attachment:

```java
helper.setText(
        "Your invoice is ready.",
        """
        <p><img src="cid:invoice-logo" alt="Logo"></p>
        <p>Your invoice is ready. Please see the attached PDF file.</p>
        """);

helper.addInline(
        "invoice-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoicePdfBytes),
        "application/pdf");
```

The logo image is referenced by HTML via CID; the PDF appears as a downloadable file. Calling only `addAttachment` does not automatically render the image at a spot inside the HTML.

## 10. Multiple inline images in one email

Each resource requires its own Content-ID:

```java
helper.setText(
        "The monthly report is ready.",
        """
        <h2>Monthly Report</h2>
        <p><img src="cid:brand-logo" alt="Example Logo"></p>
        <p>Revenue:</p>
        <img src="cid:revenue-chart" alt="Revenue chart">
        <p>Orders:</p>
        <img src="cid:orders-chart" alt="Orders chart">
        """);

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
helper.addInline(
        "revenue-chart",
        new ByteArrayResource(revenueChartPng),
        "image/png");
helper.addInline(
        "orders-chart",
        new ByteArrayResource(ordersChartPng),
        "image/png");
```

IDs must match the HTML exactly and never collide within the same message. Never reuse one Content-ID for two different images because clients may render the wrong asset.

For charts, do not convey figures exclusively through images. Also provide a table or paragraph summarizing key values in both HTML and plain text so readers still understand when images are hidden or when using assistive tools.

## 11. Security when reading local files to embed in emails

Omitting local paths from HTML is not enough to guarantee safety. The application must still control which files it reads and packages into messages.

### Never accept arbitrary paths from users

Avoid APIs like:

```java
public void sendImage(String recipient, String localPath) {
    // Never read an arbitrary path supplied by the client.
}
```

An arbitrary path could point to configuration files, secrets, or documents belonging to another tenant if the process has read access. Use validated asset IDs and resolve paths inside a permitted storage area.

### Verify tenant and access permissions

If logos or images are stored per tenant:

- Determine the tenant from the authenticated context.
- Look up the asset within that tenant's scope.
- Verify the asset is active and permitted for email use.
- Prevent users from submitting another tenant's asset ID.
- Verify the recipient is authorized to view the content represented by the image.

### Verify actual file types

Never trust file extensions blindly. A file named `logo.png` might not be a PNG. For dynamic images or uploaded files, check actual file signatures/formats, enforce size limits, and decode using a suitable library before embedding in emails.

The MIME type passed to `addInline` must match the payload, such as `image/png` or `image/jpeg`. Never declare a JPEG image as `image/png` just because its filename ends in `.png`.

### Enforce size limits

Set byte limits per image and for the total MIME message. Large images can push emails over provider quotas or inflate memory usage during batch sending. If an image is too large, resize/compress it or use an HTTPS URL to an authorized page/asset.

### Exercise caution when the backend fetches URLs to create CIDs

There are two distinct behaviors:

- HTML contains an HTTPS URL: the mail client may fetch the image after the recipient opens the email.
- Backend fetches the URL itself and embeds a CID image: the Spring server performs an HTTP request before sending.

If the backend accepts a user-supplied URL and downloads its content, guard against SSRF: restrict scheme/host/port, verify DNS and resolved IP addresses, handle redirects safely, enforce timeouts and byte limits, and block internal networks/metadata endpoints per policy. Never turn an "embed image from URL" feature into an arbitrary proxy into the server's network.

### Do not put paths or sensitive data into logs

Logs should record asset IDs, MIME types, sizes, mail job IDs, and file-read outcomes. Avoid logging file contents, tokens, paths containing usernames, or sensitive internal directories unnecessarily.

## 12. Managing resource lifecycles

A common bug in asynchronous email sending is creating a temporary file, enqueuing the job, and immediately deleting the file. By the time the worker picks up the job, the resource is gone.

### Synchronous sending

With a synchronous flow:

```text
Create temp file
   |
   v
Create MimeMessage
   |
   v
addInline(FileSystemResource)
   |
   v
send(message) completes
   |
   v
Delete temp file
```

The file must exist until the mail library finishes reading the resource. You can use `try/finally` to clean up after `send` completes.

### Asynchronous sending

With a queue:

```text
Request thread
  -> generate artifact
  -> store artifact durably
  -> enqueue artifact ID

Mail worker
  -> read artifact
  -> create MimeMessage
  -> addInline(...)
  -> send(...)
  -> update status
  -> clean up per retention
```

Do not pass a path pointing to a temp file that gets deleted when the request finishes. Store the file in object storage or a managed directory with a TTL, and let the worker read it by an authorized artifact ID.

### Resources must be re-readable

An API accepting `InputStreamSource` may be asked by the mail library to open streams while building or sending content. Thus, the resource source should create a fresh stream whenever needed. `ClassPathResource`, `FileSystemResource`, and `ByteArrayResource` are generally more convenient than an `InputStreamResource` wrapping a single already-open stream.

## 13. Spring Boot configuration and application example

A Spring Boot app can include the mail starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Example SMTP configuration with port 587 and STARTTLS:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true

app:
  mail:
    from: ${MAIL_FROM}
```

The environment variables are examples; supply them via deployment configuration or a secret manager. If the provider uses port 465 with implicit TLS, configure per provider requirements, typically using `mail.smtp.ssl.enable` instead of STARTTLS. Using CID does not change how SMTP connections work.

### Separating asset resolution from the mail service

When an application sends many emails, encapsulate image lookup in a dedicated component:

```java
package com.example.mail;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class MailImageCatalog {

    public Resource brandLogo() {
        return new ClassPathResource("mail/images/logo.png");
    }

    public String brandLogoContentId() {
        return "brand-logo";
    }

    public String brandLogoContentType() {
        return "image/png";
    }
}
```

The mail service uses the catalog:

```java
helper.setText(plainText, htmlText);
helper.addInline(
        imageCatalog.brandLogoContentId(),
        imageCatalog.brandLogo(),
        imageCatalog.brandLogoContentType());
```

The HTML template must reference `cid:brand-logo` accurately. The catalog manages only application-trusted assets; if logos vary by tenant, the component should accept the authenticated tenant and look up authorized resources rather than reading arbitrary paths from templates.

## 14. Testing emails with inline resources

Do not merely assert that `addInline` throws no exceptions. Verify that the constructed MIME message contains the image part and a Content-ID matching the HTML.

### Inspecting with an SMTP sink

In development, point Spring to an SMTP sink such as Mailpit. Send a test email and view its raw source to verify:

```text
Content-Type: multipart/related

Content-Type: text/html; charset=UTF-8
...
<img src="cid:brand-logo">

Content-Type: image/png
Content-ID: <brand-logo>
Content-Disposition: inline
...
```

The actual MIME tree may nest `multipart/alternative` or `multipart/mixed`. Inspect the image part inside the structure rather than checking only root headers.

### Scenarios to test

| Scenario | What to verify |
|---|---|
| Classpath image | Resource is inside the JAR and loads when running from the artifact |
| Filesystem image | Path is inside a permitted area and file exists at send time |
| Byte-array image | Byte payload is non-empty and resource is re-readable |
| CID | HTML and Content-ID match exactly |
| Multiple images | Each image has its own Content-ID |
| HTML + plain text | Both bodies contain required business information |
| Inline + attachment | Image shows in body while the other file stays attached |
| Wrong MIME type image | App detects or rejects improperly formatted assets |
| Oversized file | Rejected/bounded before building/sending message |
| Queue | Worker reads the artifact after the initial request finishes |

There is no need to send test emails to real customer inboxes to verify MIME structure. Use a mock sender or SMTP sink in tests; test environments must never use production credentials.

## 15. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Image shows broken image icon | HTML contains a local path | Use CID or an absolute HTTPS URL |
| `file://` image fails to display | Mail client cannot access sender filesystem or blocks file URIs | Never use file URIs in email HTML |
| Relative image fails to display | Emails lack a stable filesystem/web base path | Use absolute HTTPS or CID |
| CID cannot locate image | `addInline` not called or IDs mismatch | Match `cid:...` with Content-ID |
| Image appears as an attachment | Mail client lists inline MIME parts | Inspect MIME structure and target clients |
| File works in IDE but missing in JAR | Using filesystem path to `src/main/resources` | Use `ClassPathResource` |
| Temp file unreadable | Deleted before mail library read the resource | Keep file until send completes or store durable artifact |
| Empty attachment/inline resource | Single-read or already-consumed stream | Use a resource that can open fresh streams |
| Wrong colors or decode error | MIME type mismatches data or file is corrupt | Check file signatures and content type |
| Email too large | Many inline images or high-res images | Resize, compress, cap total bytes, or use remote URLs |
| HTML exposes internal path | Template takes filesystem path directly | Pass only Content-ID or HTTPS URL to templates |
| User can read files outside image dir | Path taken directly from request | Use asset IDs, root allowlist, and canonical path checks |
| Remote image fails to load | Client blocks images, proxy/CDN error, or non-public URL | Check URL and display policies; add alt/fallbacks |
| Wrong tenant's image sent | Asset lookup not scoped to tenant | Verify tenant and permissions before reading resource |

### Distinguishing resource-read errors from SMTP errors

- If `ClassPathResource` or `FileSystemResource` fails to open, the error happens while preparing MIME resources.
- If the MIME message builds yet SMTP rejects it, check network, TLS, AUTH, quotas, and provider rules.
- If SMTP accepts it yet images do not appear, check MIME source, CID, content type, and mail client policies.

A successful `send(...)` does not guarantee the mail client rendered the images. Diagnose at the right layer to avoid tweaking SMTP settings when the real issue is HTML referencing a local path.

## 16. Principles to follow

1. **Never write local paths into `src`.** HTML emails do not share a filesystem with the sending server.
2. **Use CID for images that must travel with the message.** Reference `cid:...` and add the resource via `addInline`.
3. **Use ClassPathResource for static assets.** Avoid hard-coding deployment directories or IDE paths.
4. **Use FileSystemResource for controlled dynamic files.** Validate paths, permissions, tenant scope, and file lifecycles.
5. **Use ByteArrayResource for byte arrays.** Suitable for in-memory generated images with fresh-stream support.
6. **Use absolute HTTPS URLs for remote images.** Account for mail clients potentially blocking external images.
7. **Call setText before addInline.** Follow Spring's recommended order for creating content and resources.
8. **Provide alt text and keep critical information as text.** Emails stay meaningful when images do not display.
9. **Enforce file sizes and actual types.** Prevent oversized messages or mismatched MIME types.
10. **Manage resources by job lifecycle.** Files must persist until the mail library finishes reading them.

## 17. Frequently asked questions

**Why doesn't `C:\images\logo.png` display in an email?** Because the email only contains that path string. The recipient's mail client has no access to the sending server's C: drive.

**Can `file:///var/app/logo.png` be used?** No. A file URI does not point to the Spring server's filesystem from the recipient's device, and many mail clients block file URIs anyway.

**If a file is in `src/main/resources`, should I use the path `src/main/resources/...`?** No. When packaged, resources may live inside a JAR. Use `ClassPathResource` to read it.

**What if the image is in a server upload directory?** Use `FileSystemResource` as the MIME source for `addInline`, after validating the asset and path. HTML contains only `cid:...`.

**Does `addInline(...)` automatically replace local paths in HTML with CIDs?** No. You must put `src="cid:content-id"` in the HTML and call `addInline` with that same Content-ID.

**Can `ByteArrayResource` be used?** Yes. It is convenient when the image is already in a `byte[]`, such as a freshly generated QR code or chart.

**Why should `setText(...)` be called before `addInline(...)`?** That is Spring's recommended order to build the body first and then attach resources referenced by HTML, improving mail client compatibility.

**Is a CID a public URL?** No. A CID references a MIME part inside the same email message; it is not an HTTP endpoint and needs no DNS.

**Do CID images require a running web server when the recipient opens the email?** No web request is needed for the CID image itself because its bytes are already inside the received message. However, any other remote images in the email still depend on network access and client policies.

**Should base64 data URIs be used in HTML?** Avoid them as a default because mail client support is uneven and HTML grows larger. Use CID inline if you want to package images inside the email.

**Can a file be attached and also displayed inside the HTML?** You can create an inline MIME part referenced by CID; regular attachments are added via `addAttachment`. The two serve different display purposes.

**Can a user-supplied image path be embedded directly?** Never accept arbitrary filesystem paths. Accept an asset ID, verify permissions, and read files only from permitted storage areas.

**Does asynchronous sending affect resources?** Yes. Resources must remain available until the worker sends. Never delete temp files immediately after enqueuing a job; store durable artifacts or regenerate them in the worker.

**What if SMTP sending succeeds yet the image fails to show?** SMTP only confirms submission. Inspect the MIME part, Content-ID, MIME type, and mail client behavior; never conclude images rendered from `send()` returning.

## 18. Related technical documentation

- **Spring Framework Mail — `MimeMessageHelper`:** `addInline(...)`, `addAttachment(...)`, `setText(...)`, and multipart modes.
- **Spring Core Resources:** `ClassPathResource`, `FileSystemResource`, `ByteArrayResource`, and `InputStreamSource`.
- **Jakarta Mail:** `MimeMessage`, `MimeMultipart`, `Content-ID`, and `Content-Disposition`.
- **RFC 2045–2049 — MIME:** content representation and multipart structures in email.
- **RFC 2387 — Multipart/Related:** relationship between an HTML body and related resources.
- **RFC 2392 — Content-ID and Message-ID URLs:** referencing resources via `cid:`.
- **Spring Boot Mail:** configuring `JavaMailSender` via `spring.mail.*`.

---

**Remember:** the sending server's filesystem is not shared with mail clients. Never put `C:\...`, `/var/...`, relative paths, or `file://...` into email HTML. For images that must travel with the message, use `src="cid:..."` and `MimeMessageHelper.addInline(...)` with `ClassPathResource`, `FileSystemResource`, or `ByteArrayResource`. For web-hosted images, use absolute HTTPS URLs. Always validate resources, keep files intact until sending completes, enforce size limits, and provide plain-text alternatives.
