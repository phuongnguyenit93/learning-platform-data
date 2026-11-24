# Referencing Images by Local File Paths

## 1. Symptom: Email Sends Successfully Yet Images Do Not Display

When building HTML emails with **Spring Framework Mail**, a very common mistake is placing **a file path from the machine running the application** directly into the `src` attribute of an `<img>` tag. For example:

~~~html
<html>
  <body>
    <h1>Welcome!</h1>
    <img src="C:\work\mail-assets\logo.png" alt="Company logo">
  </body>
</html>
~~~

Or:

~~~html
<img src="/opt/app/assets/logo.png" alt="Logo">
<img src="file:///opt/app/assets/logo.png" alt="Logo">
<img src="./images/banner.jpg" alt="Banner">
~~~

When viewing HTML on a development machine, the developer may still see the image in a browser or preview tool that can read local files. Yet once the email reaches Gmail, Outlook, Apple Mail, or another mail client, the image can:

- Show a broken-image icon or blank space.
- Show only the `alt` attribute.
- Fail to appear in the email even though the file still exists on the server.
- Appear in one mail client while failing in another.
- Send cleanly over SMTP with zero exceptions, while recipients cannot see the image.

The cause is not that `JavaMailSender` is broken. **The recipient's machine has no access to the sending server's filesystem**, and email clients typically block or do not support reading `file:` paths for security reasons.

> **Foundational rule:** An email is a document shipped to another device. A path like `C:\work\logo.png` or `/opt/app/logo.png` only has meaning inside a specific filesystem environment; it does not magically turn into image data attached inside the MIME message.

To display images in HTML email, there are generally three options:

1. **Inline images via Content-ID (CID):** embed image data in the MIME message and reference `cid:...` in HTML.
2. **Images over HTTPS:** host the image at an Internet-accessible URL per policy and reference that URL; mail clients may block remote images.
3. **Data URI/Base64:** embed image bytes directly in HTML as `data:image/...;base64,...`, though mail client compatibility varies widely; rarely the default choice.

This lesson focuses on **identifying and fixing local file path references** in Spring Framework Mail, especially with `JavaMailSender`, `MimeMessageHelper`, and MIME structures.

## 2. Why Can Server File Paths Not Serve as Email URLs?

Look at the actual journey:

~~~text
Spring Boot application
  Filesystem:
    /opt/app/assets/logo.png
               |
               v
  HTML generated:
    <img src="/opt/app/assets/logo.png">
               |
               v
       JavaMailSender.send(...)
               |
               v
         SMTP server
               |
               v
     Recipient mail server
               |
               v
     Gmail / Outlook / Mail app
               |
               v
    Tries to interpret image src
               |
               v
       NOT a portable URL
       NOT an embedded MIME part
       -> broken or blocked image
~~~

When sending HTML over SMTP, the HTML content is simply **one MIME body part**. The line:

~~~html
<img src="/opt/app/assets/logo.png">
~~~

does not instruct the SMTP server to hunt down `/opt/app/assets/logo.png` and embed it into the email. SMTP transport sends the message payload as constructed. If you want a file to become a MIME part, your code must explicitly add that part via `MimeMessageHelper.addInline(...)` or an equivalent API.

### 2.1. Local Paths Have No Global Meaning

| `src` Value | Where Does It Actually Point? | Issue |
| --- | --- | --- |
| `C:\app\images\logo.png` | File on Windows where that path exists | Recipient does not share the server's `C:` drive |
| `/var/app/logo.png` | File on Unix/Linux or origin-relative path in some web contexts | Email has no server HTTP origin |
| `file:///opt/app/logo.png` | File URI on the machine interpreting the URI | Mail client blocks it or lacks the file |
| `./logo.png` | Relative path within a document context | Email usually lacks a valid base URL |
| `classpath:mail/logo.png` | Spring Resource syntax used on the backend | Not an image URL understood by mail clients |
| `https://cdn.example.com/logo.png` | A public/authorized accessible web URL | Loadable remotely, though clients may block it |
| `cid:brandLogo` | Content-ID of a MIME part inside the email itself | Works when MIME part is valid and client supports it |

Key distinction: **a backend path for reading a file** and **a URL for a mail client to display an image** are two different kinds of data.

### 2.2. Sending the File as an Attachment Is Also Not Enough

Example:

~~~java
helper.addAttachment(
        "logo.png",
        new FileSystemResource("/opt/app/assets/logo.png"));
~~~

This creates an **attachment**. It does not automatically turn HTML like:

~~~html
<img src="file:///opt/app/assets/logo.png">
~~~

into an inline image. Some mail clients display attachment thumbnails, yet not at the `<img>` position inside the HTML.

To render an image inline at the right spot in HTML, use a **CID reference** paired with an **inline MIME part**, not just a regular attachment.

### 2.3. “Opens in a Browser” Does Not Prove Email Renders

An HTML page opened from disk or a web server has matching access permissions:

~~~text
Browser preview on developer machine:
  file:///C:/work/logo.png
  -> Browser may display

Email opened on recipient phone:
  file:///C:/work/logo.png
  -> File does not exist or is blocked
~~~

An IDE template preview or email preview tool may also map asset paths onto your local filesystem. When testing real email, inspect the **sent MIME** and **rendering in target mail clients**, not just pre-send HTML previews.

## 3. Distinguishing Image URLs, CIDs, and Source Files

A single image file can have three different “addresses” in a system:

~~~text
SOURCE PATH / RESOURCE
  /opt/app/assets/logo.png
  (where Spring reads bytes)
             |
             v
MIME INLINE CONTENT-ID
  Content-ID: <brandLogo>
  Content-Type: image/png
  (part stored inside the message)
             |
             v
HTML REFERENCE
  <img src="cid:brandLogo">
  (what the recipient client resolves)
~~~

With HTTPS:

~~~text
SOURCE IMAGE -> uploaded to a web-accessible object/CDN
                      |
                      v
URL: https://cdn.example.com/mail/logo.png
                      |
                      v
HTML: <img src="https://cdn.example.com/mail/logo.png">
                      |
                      v
Recipient's client requests URL
  (possibly proxied, cached, blocked or delayed)
~~~

**Changing `file:///...` to `cid:...` in HTML is not enough** unless the application also embeds the image bytes into the email as a MIME part with the matching Content-ID.

## 4. Recommended Solution for Fixed Logos/Banners: Inline CID

For small images essential to the email (such as a template's built-in logo), the usual steps are:

1. Create a `MimeMessage` from `JavaMailSender`.
2. Create a `MimeMessageHelper` in an appropriate multipart mode.
3. Call `setText(plainText, htmlText)` with HTML containing `cid:logo`.
4. Call `addInline("logo", resource, "image/png")` to embed image bytes into MIME.
5. Send the message with the same `JavaMailSender`.

### 4.1. Complete Example with a File on Disk

~~~java
package com.example.mail;

import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(
            String recipient,
            Path logoPath) throws MessagingException {

        if (!Files.isRegularFile(logoPath)
                || !Files.isReadable(logoPath)) {
            throw new IllegalArgumentException(
                    "Configured mail logo is unavailable");
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome");

        String plainText = """
                Welcome!
                Thank you for signing up.
                """;

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:brandLogo"
                         alt="Company"
                         width="140">
                    <h1>Welcome!</h1>
                    <p>Thank you for signing up.</p>
                  </body>
                </html>
                """;

        // Set HTML first, then addInline.
        helper.setText(plainText, htmlText);

        FileSystemResource logoResource =
                new FileSystemResource(logoPath);
        helper.addInline(
                "brandLogo",
                logoResource,
                "image/png");

        mailSender.send(message);
    }
}
~~~

**Core takeaways:**

- `logoPath` is used **only on the server** for Spring to read bytes.
- `cid:brandLogo` is what goes into **HTML sent to the recipient**.
- `helper.addInline("brandLogo", ...)` creates a MIME part with the matching Content-ID.
- `MULTIPART_MODE_MIXED_RELATED` builds a structure compatible with HTML, inline images, and optional independent attachments.
- `setText(plainText, htmlText)` builds both `text/plain` and `text/html` parts for clients that do not render HTML.
- `image/png` is the proper MIME type for a PNG file; never set an arbitrary content type mismatching the actual bytes.

Remember to import `java.nio.file.Path` and match your project's Java version. Text blocks require Java 15+, which fits Java 17 commonly used in Spring Boot 3. On older Java versions, replace text blocks with regular strings.

### 4.2. Why Must Content-ID Match Exactly?

HTML:

~~~html
<img src="cid:brandLogo" alt="Company">
~~~

MIME:

~~~text
Content-ID: <brandLogo>
Content-Type: image/png
Content-Disposition: inline
Content-Transfer-Encoding: base64
~~~

`MimeMessageHelper.addInline("brandLogo", ...)` handles writing the `Content-ID` header; HTML references `brandLogo` **without** angle brackets `<...>` inside `cid:`.

If you write:

~~~html
<img src="cid:logo">
~~~

while calling:

~~~java
helper.addInline("brandLogo", logoResource, "image/png");
~~~

the client cannot find a MIME part with ID `logo`. The result is a broken image even though the PNG file is embedded in the email.

### 4.3. Why Should `addInline` Run After `setText`?

Spring `MimeMessageHelper` recommends adding inline resources **after setting text** to prevent some mail clients from mis-resolving the MIME tree when parts are added in an incompatible order.

Simple order:

~~~java
helper.setText(plainText, htmlText);
helper.addInline("brandLogo", resource, "image/png");
mailSender.send(message);
~~~

Not every MIME parser is equally sensitive to ordering, yet keeping a clean structure and order cuts down issues across Gmail, Outlook, Apple Mail, and older clients.

### 4.4. File Exists at Check Time Yet Vanishes Before `send`

The check:

~~~java
Files.isReadable(logoPath)
~~~

inspects only **a single instant**. If the job runs asynchronously and the file is deleted between validation and `send`, sending fails when MIME serialization reads the resource:

~~~text
T1: request uploads logo -> /tmp/logo-123.png
T2: queue background mail job
T3: request ends -> temp file deleted
T4: mail worker invokes addInline + send
T5: resource cannot be read
~~~

For async/retry jobs, use a durable resource (classpath, static asset, versioned object storage, durable staged file) and clean up only when permitted by the lifecycle.

## 5. Images in Spring Boot `resources`: Use `ClassPathResource`

Many projects place logos in:

~~~text
src/
  main/
    java/
      com/example/mail/...
    resources/
      mail/
        images/
          brand-logo.png
          welcome-banner.jpg
~~~

Here, images are typically **packaged into the JAR** at build time. Do not try to locate them as a physical file on disk:

~~~java
// Breaks easily once packaged as an executable JAR:
Path path = Paths.get(
        "src/main/resources/mail/images/brand-logo.png");
~~~

The path `src/main/resources` matches only the development source layout. After building and running from a JAR/container, that directory may no longer exist.

### 5.1. Reading Resources Properly via Classpath

~~~java
import org.springframework.core.io.ClassPathResource;

ClassPathResource logo =
        new ClassPathResource("mail/images/brand-logo.png");

helper.setText(
        "Welcome!",
        """
        <html>
          <body>
            <h1>Welcome!</h1>
            <img src="cid:companyLogo" alt="Company logo">
          </body>
        </html>
        """);

helper.addInline("companyLogo", logo, "image/png");
~~~

`ClassPathResource` opens an `InputStream` to classpath data even inside a JAR. You do not need to know whether the file sits in a build directory, inside a JAR, or at a specific OS path.

**Never put `classpath:mail/images/brand-logo.png` into HTML.** That is a backend resource lookup syntax, not an address a mail client can read.

### 5.2. Avoid Forcing a Classpath Resource into a `File`

A common bug:

~~~java
File logoFile = new ClassPathResource(
        "mail/images/brand-logo.png").getFile();
~~~

When the resource lives inside a JAR, `getFile()` fails because the resource **does not exist as a standalone file on the filesystem**. With `MimeMessageHelper.addInline`, pass `ClassPathResource` directly:

~~~java
helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/images/brand-logo.png"),
        "image/png");
~~~

Spring opens the stream when needed, provided the resource remains available and repeatable throughout message construction and sending.

### 5.3. Is Bundling Assets Inside the JAR Appropriate?

**Suitable** when:

- Logos/images are small and do not vary per user.
- Images belong to the deployed template version.
- Assets do not need updates without redeploying the app.
- Every worker instance can open the resource from the classpath.

**Unsuitable** when:

- Each tenant uploads its own logo and updates it frequently.
- Images are large or contain personal data.
- Files must be deleted under separate retention rules.
- Campaign banners need updating without redeploying.

In those cases, use object storage or an asset management service with explicit access control.

## 6. `FileSystemResource`, `PathResource`, `ByteArrayResource`, and `InputStreamSource`

All image sources can be turned into MIME bytes by Spring, yet their **lifecycles and repeatability** differ.

| Source | When to Use | Pros | Caveats |
| --- | --- | --- | --- |
| `ClassPathResource` | Assets bundled in app/JAR | Portable across deploy environments | Updating assets requires redeploy |
| `FileSystemResource` | Files existing on disk at send time | Avoids pre-loading whole file onto heap | File must exist, be readable, and stay intact |
| `PathResource` | Files via `java.nio.file.Path` | Convenient with NIO | Shares path/lifecycle caveats |
| `ByteArrayResource` | Images already in memory as small `byte[]` | Repeatable reads, no external file dependency | Bytes live on the heap |
| Custom `InputStreamSource` | Assets from object storage/database | Can stream from backend | Every call must open a **fresh**, stable stream |
| `InputStreamResource` | An already-open `InputStream` | Works for some single-use pipelines | Generally **unsuitable** for inline MIME needing re-reads |

### 6.1. `ByteArrayResource` for Small Logos

If the image is already generated or fetched as bytes:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] logoBytes = imageService.loadSmallBrandLogo(tenantId);

helper.setText(
        "Hello",
        "<html><body><img src=\"cid:brandLogo\"></body></html>");

helper.addInline(
        "brandLogo",
        new ByteArrayResource(logoBytes),
        "image/png");
~~~

`imageService` is an illustrative application service. For small logos, this is clear and easy to test. Still, many concurrent emails with large images create heap pressure:

~~~text
200 concurrent messages
x 8 MiB image bytes each
= ~1.6 GiB image buffers
(excluding MIME, object, and thread overhead)
~~~

Do not pick `ByteArrayResource` solely out of convenience when images are large or worker concurrency is high.

### 6.2. Custom `InputStreamSource` Opening Fresh Streams

Some mail libraries read a resource multiple times—for instance, once to inspect metadata and again during content serialization. With object storage, an adapter can provide a repeatable source:

~~~java
import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.InputStreamSource;

public final class VersionedImageSource
        implements InputStreamSource {

    private final ImageObjectStore store;
    private final String objectKey;
    private final String versionId;

    public VersionedImageSource(
            ImageObjectStore store,
            String objectKey,
            String versionId) {
        this.store = store;
        this.objectKey = objectKey;
        this.versionId = versionId;
    }

    @Override
    public InputStream getInputStream() throws IOException {
        // Every invocation must open a NEW stream.
        return store.openVersion(objectKey, versionId);
    }
}
~~~

Then:

~~~java
helper.addInline(
        "brandLogo",
        new VersionedImageSource(store, objectKey, versionId),
        "image/png");
~~~

`ImageObjectStore` is an application abstraction, not a Spring Mail class. Object keys/versions must be **authorized per tenant and message** with proper size, timeout, and retention controls. If the stream can only be opened once or the object changes between reads, MIME can break or carry inconsistent image data.

### 6.3. Why Is `InputStreamResource` Usually Unsuitable?

~~~java
InputStream oneShot = Files.newInputStream(path);

helper.addInline(
        "brandLogo",
        new InputStreamResource(oneShot),
        "image/png");
~~~

`InputStreamResource` wraps an already-opened stream. If the sending library invokes `getInputStream()` more than once, subsequent reads may fail or hit EOF. Practical rule of thumb:

- File on disk: use `FileSystemResource` or `PathResource`.
- Classpath image: `ClassPathResource`.
- Small in-memory bytes: `ByteArrayResource`.
- Remote storage: custom `InputStreamSource` opening a fresh stream each time for a fixed version.

### 6.4. MIME Type Must Be Accurate

Examples:

| File | Content-Type to Use |
| --- | --- |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| GIF | `image/gif` |
| SVG | `image/svg+xml`, though rendering/security support varies by mail client |
| WebP | `image/webp`, support varies by mail client |

For emails targeting diverse mail clients, PNG/JPEG are generally simpler and more reliable than modern formats or SVG. Never trust a user-supplied file extension as proof the content is actually PNG; for uploaded assets, verify format and dimensions on the backend.

## 7. MIME `multipart/related` Is What Links HTML to Images

To see why `addInline` solves the problem, look at how HTML/inline-image emails are packaged.

A message with plain text, HTML, and an inline image uses **MIME multipart**, with the HTML part referencing the image part's Content-ID.

### 7.1. Simple Structure

~~~text
multipart/related
  |
  +-- multipart/alternative
  |     |
  |     +-- text/plain; charset=UTF-8
  |     |
  |     +-- text/html; charset=UTF-8
  |           <img src="cid:brandLogo">
  |
  +-- image/png
        Content-ID: <brandLogo>
        Content-Disposition: inline
        Content-Transfer-Encoding: base64
        [image bytes]
~~~

Depending on the `MimeMessageHelper` multipart mode and library, the actual MIME tree may wrap another `multipart/mixed` layer to hold attachments. What matters is not just the root name, but that **HTML and inline resources sit in a MIME relationship mail clients understand**.

### 7.2. When Attachments Are Also Present

~~~text
multipart/mixed
  |
  +-- multipart/related
  |     |
  |     +-- multipart/alternative
  |     |     +-- text/plain
  |     |     +-- text/html
  |     |           <img src="cid:brandLogo">
  |     |
  |     +-- image/png
  |           Content-ID: <brandLogo>
  |           Content-Disposition: inline
  |
  +-- application/pdf
        Content-Disposition: attachment
        filename="invoice.pdf"
~~~

When using `MULTIPART_MODE_MIXED_RELATED`, Spring builds a mixed/related tree supporting both inline resources and attachments; exact part names, ordering, and nesting can vary by implementation/version.

### 7.3. Distinguishing `addInline` and `addAttachment`

~~~java
// Image referenced directly inside HTML:
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

// File for the recipient to download or open as an attachment:
helper.addAttachment(
        "invoice.pdf",
        invoiceResource,
        "application/pdf");
~~~

| `addInline` | `addAttachment` |
| --- | --- |
| Sets `Content-ID` for `cid:...` references | Sets `Content-Disposition: attachment` |
| Intended for inline display inside HTML | Intended as a standalone attached file |
| Should be referenced from HTML via CID | Requires no HTML reference |
| Some clients may still list it in attachments | Some clients may preview images, yet not as inline CID |

Do not try to turn an attachment into an inline HTML image by putting the attachment's filename into `src`:

~~~html
<!-- Wrong reference mechanism -->
<img src="logo.png">
~~~

`logo.png` does not map automatically to a MIME attachment of that name. You need `cid:<content-id>` or a valid web URL.

### 7.4. Why Is `setText(html, true)` Alone Insufficient?

This snippet:

~~~java
helper.setText(
        "<img src=\"file:///opt/app/logo.png\">",
        true);
mailSender.send(message);
~~~

only marks the body as HTML without adding any image part. `HTML email` and `MIME inline resources` are related yet distinct features.

### 7.5. The `multipart=false` Mistake

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        false,
        "UTF-8");

helper.setText(html, true);
helper.addInline("brandLogo", resource, "image/png");
~~~

In non-multipart mode, adding inline resources is invalid and can throw `IllegalStateException` or fail during MIME assembly. For inline images, use a multipart helper:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

**Do not blindly flip `false` to `true` on the wrong method.** `setText(html, true)` means “this body is HTML”; `MimeMessageHelper(message, true, "UTF-8")` means “this helper supports multipart”. The two booleans on the two APIs mean completely different things.

## 8. Multiple Inline Images in the Same Email

If a template includes a logo, banner, and contact icon:

~~~html
<table role="presentation">
  <tr>
    <td>
      <img src="cid:companyLogo"
           alt="Company"
           width="140">
    </td>
  </tr>
  <tr>
    <td>
      <img src="cid:welcomeBanner"
           alt="Welcome"
           width="600">
    </td>
  </tr>
  <tr>
    <td>
      <p>Contact us:</p>
      <img src="cid:supportIcon"
           alt=""
           width="20">
    </td>
  </tr>
</table>
~~~

Java code:

~~~java
helper.setText(plainText, htmlText);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

helper.addInline(
        "welcomeBanner",
        new ClassPathResource("mail/images/banner.jpg"),
        "image/jpeg");

helper.addInline(
        "supportIcon",
        new ClassPathResource("mail/images/support.png"),
        "image/png");
~~~

**Each image has its own Content-ID**, and the CID string in HTML matches the ID argument to `addInline`. Never reuse the same ID for images with different bytes. When an asset appears in multiple places in the same template, you may reuse one CID to avoid embedding duplicate copies, depending on client compatibility and MIME assembly.

### 8.1. Define an Explicit CID Mapping

Example:

| Role | CID | Backend Resource |
| --- | --- | --- |
| Logo | `companyLogo` | `mail/images/logo.png` |
| Banner | `welcomeBanner` | `mail/images/banner.jpg` |
| Icon | `supportIcon` | `mail/images/support.png` |

If a template engine renames a placeholder, update the mapping together with it. Never derive CIDs from unvalidated filenames or filenames containing special characters.

### 8.2. Set `alt` Text and Dimensions

Some mail clients block images or data-saver modes skip loading them. Include:

~~~html
<img src="cid:companyLogo"
     alt="Company"
     width="140"
     height="48"
     style="display:block;border:0;max-width:100%;">
~~~

`alt` helps readers understand content even when images do not display. Purely decorative icons can use `alt=""`; banners carrying important messages should never convey information solely in pixels—include corresponding HTML text.

Never assume modern CSS or SVG behaves uniformly across all email clients. Test email templates against your target clients.

## 9. Errors That Surface Only After Deploying to Docker or Kubernetes

A scenario:

~~~text
Development laptop:
  C:\projects\my-app\logo.png -> exists

Container image:
  /app/application.jar
  /app/logo.png              -> may not exist

Mail recipient:
  has neither file
~~~

There are **two distinct error layers**:

1. **Backend cannot read the image source:** the file path is misconfigured after deployment; `addInline`/`send` cannot find the resource.
2. **Backend can read the image, yet HTML still references the file path:** MIME lacks the matching Content-ID, so images break in mail clients even though sending succeeds.

Separating these two layers avoids fixing the wrong thing.

### 9.1. Relative Paths Depend on the Working Directory

Example:

~~~java
Path imagePath = Paths.get("assets/mail/logo.png");
~~~

This relative path resolves against the Java process's **current working directory**, not automatically from the project root or `src/main/resources`.

Running from an IDE:

~~~text
working directory = C:\dev\project
assets/mail/logo.png may exist
~~~

Running in Docker:

~~~text
working directory = /app
assets/mail/logo.png may not exist
~~~

Fix:

- Bundled assets: `ClassPathResource`.
- Externally mounted assets: configure an operator-managed **absolute path** and construct `FileSystemResource`.
- Uploaded assets: store in object storage/durable files and pass only validated resource references.

Never interpolate filesystem paths directly into HTML.

### 9.2. Mounting a Volume Properly Is Still Not Enough for HTML

Docker example with a mount:

~~~yaml
services:
  mail-worker:
    image: example/mail-worker:latest
    volumes:
      - /srv/mail-assets:/app/mail-assets:ro
~~~

The application can read:

~~~text
/app/mail-assets/logo.png
~~~

yet recipients still **cannot** read:

~~~html
<img src="/app/mail-assets/logo.png">
~~~

A Docker volume only solves the application's file-read access. You still must use `addInline(..., resource, ...)` or a public HTTPS URL.

### 9.3. Source Files Do Not Exist Across All Replicas

In Kubernetes:

~~~text
Pod A handles upload
  /tmp/logo-100.png
       |
       v
Mail task enqueued
       |
       v
Pod B consumes task
  /tmp/logo-100.png -> missing
~~~

A `Path` existing only on Pod A's local filesystem is not a durable job payload. In multi-worker systems, use:

- Identical classpath assets across replicas for static assets.
- Authorized, versioned object storage/buckets for uploads.
- Reliable shared filesystems if required by architecture.
- Durable staging and controlled cleanup.

If the same message is retried after a restart, image data must remain **retrievable and consistent**, never tied to a destroyed container's temp directory.

### 9.4. File Read Permissions Differ by JVM OS User

Developers often run apps under privileged accounts, while containers run under unprivileged users:

~~~text
File exists: true
File readable by application user: false
~~~

Check ownership/ACLs, volume read permissions, and SELinux/AppArmor policies if active. Never run the entire app as root just to read a logo; grant least-privilege read access on the asset directory instead.

### 9.5. Windows Path Separators Are Not URL Separators

A Windows path:

~~~text
C:\assets\logo.png
~~~

is not a valid web URL for mail clients. Even calling:

~~~java
path.toUri().toString()
~~~

yields:

~~~text
file:///C:/assets/logo.png
~~~

which still does not grant recipient access. Converting a `Path` to a `URI` neither uploads the file to a public server nor embeds its bytes into MIME.

## 10. Using HTTPS URLs for Email Images

Not every image needs inline CID. For frequently updated banners or marketing campaigns, you can serve images from an HTTPS CDN/asset server.

~~~html
<img
  src="https://cdn.example.com/email/assets/welcome-banner.png"
  alt="Welcome"
  width="600">
~~~

The recipient's mail client requests the URL directly or through an image proxy; some clients block remote images by default or prompt the user before displaying them.

### 10.1. Pros of HTTPS

- No need to embed image bytes into every MIME email.
- Smaller emails, especially with large banners.
- CDNs cache and serve optimized images.
- Artwork can be updated independently of application builds.
- Less load on `JavaMailSender` during bulk sends.

### 10.2. Cons of HTTPS

- Images depend on external infrastructure: DNS, TLS, CDN, and URL uptime.
- Some mail clients block remote images for privacy protection.
- Offline recipients cannot see uncached images.
- URLs can expire; emails saved for months show broken images.
- URLs carrying personal identifiers raise privacy/tracking concerns.
- Not all web authentication mechanisms work inside email clients.

### 10.3. Never Use `localhost` or Internal IP Addresses

Examples **unsuitable for emails sent over the Internet**:

~~~html
<img src="http://localhost:8080/logo.png">
<img src="http://127.0.0.1:8080/logo.png">
<img src="http://192.168.1.10/assets/logo.png">
<img src="http://internal-service:8080/logo.png">
~~~

`localhost` on the recipient's side **means the recipient's device**, not your sending server. Internal IPs or Kubernetes service hostnames do not resolve from the Internet, and embedding internal addresses can also leak infrastructure details.

### 10.4. Short-Lived URLs Break Emails Later

Example:

~~~html
<img src="https://storage.example.com/private/logo.png?expires=3600&signature=...">
~~~

If a signed URL expires after one hour, a recipient reopening the email days later sees a broken image. Furthermore, signed URLs act like bearer credentials: if the email is forwarded or cached, others can access the asset while the URL stays valid.

If the image contains sensitive data, consider:

- Avoiding sensitive data inside emails/remote images.
- Sending a link to an authenticated portal instead of trying to show a thumbnail.
- If business rules require inline embedding, embed only data authorized for that specific recipient.
- Designing matching retention and revocation policies.

### 10.5. HTTP 200 Is Not Enough If `Content-Type` Is Wrong

A URL might return:

~~~text
HTTP/1.1 200 OK
Content-Type: text/html

<html>login required</html>
~~~

The mail client expects a PNG yet gets a login page, so the image breaks. When debugging an image URL, confirm it loads **without the developer's cookies/session** (for public assets), returning the right content type and actual image bytes.

A URL relying on an admin browser's login cookie does not prove recipients have access. Conversely, never make sensitive images public just so “the email displays them”.

### 10.6. Mail Proxy Caching

Some email providers fetch images through proxies and cache them, so:

- Request timestamps do not necessarily match when the user opened the email.
- Request IPs belong to the proxy.
- Caching can prevent users from seeing updated assets immediately.
- Personal tracking query parameters may be handled differently across clients.

Never build critical business logic assuming “image loaded” proves the user read or understood the email. Open tracking does not prove comprehension or viewing.

## 11. Data URI/Base64 in HTML: Possible, Yet Not Recommended as Default

Some developers try replacing file paths with:

~~~html
<img
  src="data:image/png;base64,iVBORw0KGgoAAA..."
  alt="Company">
~~~

A Data URI embeds image bytes directly inside the HTML attribute, **completely different from Content-ID**:

~~~text
cid:brandLogo
  -> refers to a separate MIME body part

data:image/png;base64,...
  -> embeds image bytes inside HTML attribute
~~~

### 11.1. Limitations

- Data URI support varies widely across email clients; several strip or ignore it.
- HTML body size balloons due to Base64 overhead.
- Reusing an image multiple times repeats bytes inside HTML.
- HTML sanitizers or security filters often block the `data:` URI scheme.
- Base64-encoding large images raises heap usage.

Therefore, for HTML emails needing broad compatibility, **CID or HTTPS** is usually easier to control than Data URIs.

### 11.2. Base64 in MIME Is Not a Data URI

When `addInline` builds an `image/png` MIME part, the library may select:

~~~text
Content-Transfer-Encoding: base64
~~~

to transport the image over SMTP. Meanwhile, HTML still uses:

~~~html
<img src="cid:brandLogo">
~~~

Seeing Base64 in raw MIME does not mean HTML must contain `data:image/png;base64,...`. They are two distinct mechanisms.

## 12. Comparing CID, HTTPS, and Data URI

| Criterion | CID Inline | HTTPS URL | Data URI |
| --- | --- | --- | --- |
| Image data inside email | Yes, separate MIME part | No | Yes, inside HTML |
| Network needed when opening | No URL fetch needed after email arrives | Usually yes, unless cached | No if client supports it |
| Mail client compatibility | Good across many clients, still varies | Broad, though remote images may be blocked | Inconsistent |
| Email size | Increases by bytes/Base64 | Lighter | Increases sharply inside HTML |
| Update image after sending | No | Possible, though proxy/cache affects it | No |
| Lifecycle management | Resource must exist at send time | URL must stay alive at open time | Bytes already sit in HTML |
| Privacy impact | No CDN fetch needed to display | May trigger remote requests/tracking | No remote request needed |
| Offline support | Yes once email is downloaded | Depends on cache | Yes if client supports it |
| Sensitive data protection | Bytes live in email; recipient can forward | Requires access control/tokens | Bytes live in HTML email |

**Selection tips:**

- Small, static, important logos: prefer **CID**.
- Large, non-sensitive marketing banners managed independently: **HTTPS CDN** can fit well.
- Sensitive images or assets needing per-view auth: usually **use a portal link** instead of inline embedding.
- Data URI: use only after verifying your exact target email client list accepts it.

Never assume one option is perfect across every client. Decide based on **compatibility, data sensitivity, size, privacy, and resource lifecycle**.

## 13. HTML Template Engines and File Path Interpolation

A template may be rendered with Thymeleaf, FreeMarker, Mustache, or a custom renderer:

~~~html
<!-- Initial template -->
<img src="{{logoUrl}}" alt="Company">
~~~

If code passes:

~~~text
logoUrl = /opt/app/assets/logo.png
~~~

the renderer merely substitutes the string; it **does not automatically read the file, create a MIME part, or convert the path into an HTTPS URL**.

### 13.1. Separate “Image Source” from “HTML Reference”

Never put a raw `Path` into the model for templates to interpolate as a URL:

~~~java
model.put("logoUrl", logoPath.toString());
~~~

Instead:

~~~java
model.put("logoSrc", "cid:brandLogo");
~~~

And the mail-sending service ensures:

~~~java
helper.setText(plainText, renderedHtml);
helper.addInline("brandLogo", logoResource, "image/png");
~~~

Here:

- The template model knows the **CID or HTTPS URL**.
- The mail builder knows the **resource source/bytes and MIME type**.
- The provider adapter sends the prepared message.

### 13.2. Do Not Auto-Convert Arbitrary `img src` Values

A helper that “automatically scans all `<img src=...>` and downloads/loads images” carries major risks:

- Fetching arbitrary user-supplied URLs → **SSRF** into internal networks.
- Reading arbitrary file paths → **path traversal / leaking secret files**.
- Parsing HTML with regex breaks easily on quoting, entities, inline CSS, and responsive markup.
- Assigning inconsistent CIDs.
- Downloading huge images, infinite redirects, or non-image files.

For trusted email templates, it is better to **declare inline assets explicitly**. If dynamic HTML must be transformed, use a proper HTML parser with source/host allowlists, byte limits, redirect caps, content-type validation, timeouts, image count limits, tenant authorization, and snapshots.

### 13.3. Template Asset Registry Example

~~~java
public record InlineAsset(
        String contentId,
        String contentType,
        org.springframework.core.io.InputStreamSource source) {
}
~~~

Mail builder:

~~~java
helper.setText(plainText, renderedHtml);

for (InlineAsset asset : inlineAssets) {
    helper.addInline(
            asset.contentId(),
            asset.source(),
            asset.contentType());
}
~~~

`inlineAssets` must come from an application-controlled registry, never an arbitrary user-supplied file/URL list. CIDs must be unique within the message, content types must be accurate, and sources must be repeatable.

## 14. Diagnosing Broken Images by Inspecting Actual MIME

To troubleshoot missing images, you must inspect **the sent HTML** and **whether the image MIME part exists**. Reading a log saying “SMTP sent successfully” answers neither.

### 14.1. First Three Questions

1. What `src` is actually in the email's HTML? `file:`, relative path, `cid:`, or HTTPS?
2. If HTML uses `cid:foo`, does raw MIME contain a part with `Content-ID: <foo>`?
3. Does that MIME part contain valid image bytes, the right `Content-Type`, and sit in the proper multipart relationship?

~~~text
Inspect HTML <img src>
         |
         +-- src is local file path
         |       |
         |       v
         |   Root cause found:
         |   not a portable email resource
         |
         +-- src is cid:logo
         |       |
         |       v
         |   Check MIME Content-ID <logo>
         |       |
         |       +-- missing -> call addInline
         |       +-- mismatch -> align CID strings
         |       +-- exists -> inspect MIME type/structure/data
         |
         +-- src is https://...
                 |
                 v
             Check URL availability,
             Content-Type, TLS, client blocking
~~~

### 14.2. Reading the Raw Message

For a test email sent to a test mailbox, inspect the raw MIME source:

~~~text
MIME-Version: 1.0
From: no-reply@example.com
To: test@example.net
Subject: Test logo
Content-Type: multipart/related; boundary="related-1"

--related-1
Content-Type: text/html; charset=UTF-8

<html><body>
  <img src="cid:brandLogo" alt="Brand">
</body></html>

--related-1
Content-Type: image/png
Content-ID: <brandLogo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

iVBORw0KGgo...

--related-1--
~~~

This is a **simplified MIME diagram**. When both `text/plain` and HTML, or attachments, are present, the real structure adds boundaries and multipart layers. Raw MIME must be parsed per MIME rules rather than merely grepping for `Content-ID` somewhere in the text.

### 14.3. Error Clues

| Clue in Raw MIME | Likely Cause | Fix Direction |
| --- | --- | --- |
| HTML contains `file:///...` | Local path never converted to CID/HTTPS | Use `cid:...` + `addInline` |
| HTML contains `C:\...` | Template interpolated Windows path | Separate backend path from HTML |
| HTML has `cid:logo`, no `Content-ID` | `addInline` omitted or build failed | Add inline part |
| `Content-ID` is `brandLogo` while HTML has `cid:logo` | Mismatched IDs | Use exact same ID string |
| HTML uses `cid:<logo>` | Wrong reference syntax | Use `cid:logo` |
| `Content-Type: application/octet-stream` | Mail client does not recognize image | Set exact image content type |
| Part has `Content-Disposition: attachment` | Added as attachment instead of inline | Use `addInline` |
| Empty/invalid MIME base64 | Resource unreadable or corrupted bytes | Check source/lifecycle |
| `multipart/related` not linked to HTML | Wrong MIME tree | Use proper multipart mode and helper |
| HTML and MIME match, yet client hides image | Client policy/compatibility | Test target client, check remote/inline settings |
| Test image is huge | Provider/client limits or HTML layout | Shrink image or choose another strategy |

### 14.4. A Valid `Content-Type` Alone Is Not Enough

A MIME part having:

~~~text
Content-Type: image/png
Content-ID: <logo>
~~~

whose body bytes are HTML or a corrupt file still fails to render. For uploaded sources, validate **magic bytes/actual format** and size limits rather than trusting file extensions or uploader-declared `Content-Type`.

### 14.5. Inline Resources Showing Up as Attachments

Some email clients list inline images in the attachments tray even while rendering HTML properly, because they are genuine MIME parts. That **does not necessarily mean MIME construction was wrong**.

Conversely, if the image appears only as an attachment while `<img>` stays broken, check CID mapping and the MIME tree. Distinguish *client presentation* from *message data structure*.

### 14.6. Why Backend HTML Previews Easily Mislead

If a preview service injects local file paths or data URLs on the fly, it builds HTML different from what is actually emailed:

~~~text
Preview path:
  template -> preview asset resolver -> browser

Email path:
  template -> MimeMessageHelper -> SMTP -> mail client
~~~

To avoid divergence, use the exact same renderer and CID asset mapping for both live sends and MIME preview tests. Browser HTML previews check only basic layout; checking `Content-ID` requires inspecting the MIME message.

## 15. Writing Tests for Inline Images Without Real SMTP

A unit test can build a `MimeMessage` with `JavaMailSenderImpl` **without calling `send`**, then inspect the built HTML and MIME parts.

### 15.1. Example Building a `MimeMessage`

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

JavaMailSenderImpl mailSender = new JavaMailSenderImpl();
mailSender.setDefaultEncoding("UTF-8");

var message = mailSender.createMimeMessage();
var helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("test@example.net");
helper.setSubject("Test inline logo");
helper.setText(
        "Company logo",
        "<html><body><img src=\"cid:brandLogo\"></body></html>");

byte[] samplePng = testResources.loadPngBytes("mail/logo.png");
helper.addInline(
        "brandLogo",
        new ByteArrayResource(samplePng),
        "image/png");

message.saveChanges();

ByteArrayOutputStream output = new ByteArrayOutputStream();
message.writeTo(output);
byte[] mimeBytes = output.toByteArray();
~~~

`testResources` is an application-defined test-suite helper. This test constructs MIME without configuring an SMTP host because `send` is not called.

For small tests you can inspect raw bytes, yet **never rely solely on `new String(mimeBytes, UTF_8).contains(...)`** as proof that the image part is valid. MIME can involve complex encoding/boundaries, header folding, and Base64; parse MIME with Jakarta Mail or a dedicated utility.

### 15.2. Parsing MIME to Locate `Content-ID`

Example recursive helper over multipart:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public static Part findPartByContentId(
        Part node,
        String wantedContentId)
        throws Exception {

    String[] headers = node.getHeader("Content-ID");
    if (headers != null) {
        for (String value : headers) {
            String normalized = value == null
                    ? ""
                    : value.trim();
            if (normalized.startsWith("<")
                    && normalized.endsWith(">")) {
                normalized = normalized.substring(
                        1, normalized.length() - 1);
            }
            if (wantedContentId.equals(normalized)) {
                return node;
            }
        }
    }

    Object content = node.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            BodyPart child = multipart.getBodyPart(i);
            Part match = findPartByContentId(
                    child, wantedContentId);
            if (match != null) {
                return match;
            }
        }
    }
    return null;
}
~~~

This is an **illustrative test helper** for small controlled MIME fixtures. For untrusted emails, parsers must bound recursion depth, part counts, total bytes, and safely handle nested `message/rfc822` parts.

### 15.3. Asserting Content Type and Bytes

~~~java
Part imagePart = findPartByContentId(
        message, "brandLogo");

assertThat(imagePart).isNotNull();
assertThat(imagePart.isMimeType("image/png")).isTrue();

byte[] actualImage;
try (var in = imagePart.getInputStream()) {
    actualImage = in.readAllBytes();
}
assertThat(actualImage).containsExactly(samplePng);
~~~

Key point: assert the actual bytes embedded inside the MIME part, not merely a Mockito verification that `helper.addInline(...)` was called. This unit test also catches empty resources.

### 15.4. Asserting HTML Contains CID and No Local Paths

A test can parse the `text/html` part and assert:

~~~text
Expected:
  <img src="cid:brandLogo">

Forbidden local-path patterns:
  file:///
  C:\
  /opt/app/assets/
  src/main/resources/
~~~

Do not rely on blacklisting a few strings if HTML templates can be edited by users. For managed templates, parse all `img[src]` attributes with an HTML parser and allow only `cid:` mapped in the inline registry or `https:` on an application allowlist.

### 15.5. Testing Multiple Images

For HTML containing:

~~~html
<img src="cid:logo">
<img src="cid:banner">
~~~

Test:

1. A part exists with `Content-ID` `logo` and exact PNG bytes.
2. A part exists with `Content-ID` `banner` and exact JPEG bytes.
3. The two Content-IDs do not collide when bytes differ.
4. HTML leaks no local paths.
5. Plain-text alternative contains useful content.
6. Any attachment remains an independent attachment without breaking inline CIDs.

### 15.6. Testing Attachments and Inline Together

~~~java
helper.setText(
        "Invoice attached",
        "<html><body>"
                + "<img src=\"cid:companyLogo\" alt=\"Company\">"
                + "<p>Invoice attached.</p>"
                + "</body></html>");

helper.addInline(
        "companyLogo",
        logoResource,
        "image/png");

helper.addAttachment(
        "invoice.pdf",
        invoiceResource,
        "application/pdf");
~~~

After building, tests should verify:

- CID image part exists with proper content disposition.
- PDF attachment has the right filename and content type.
- HTML part still references the CID.
- `text/plain` part still has its content.

If `logoResource` or `invoiceResource` is single-read only, serializing multiple times in tests helps surface repeatability bugs.

## 16. Integration Testing with a Simulated SMTP Server

MIME unit tests are necessary yet do not prove the message transmits intact over transport. For integration tests, use Mailpit, GreenMail, or a suitable test SMTP server to capture emails in a test environment.

~~~text
Spring Boot test
       |
       v
WelcomeMailService
       |
       v
JavaMailSender
       |
       v
Fake SMTP server
       |
       v
Captured MIME
       |
       v
Assert:
  HTML cid
  Content-ID
  image bytes
  content type
  multipart layout
~~~

### 16.1. Test SMTP Configuration

Sample test configuration:

~~~yaml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail:
        smtp:
          auth: false
          starttls:
            enable: false
~~~

This is strictly for an **internal SMTP sink requiring no auth/TLS**. Never use it for production SMTP or over the Internet.

When running a fake SMTP server in Testcontainers, the host/port is usually the **mapped port** assigned by the container runtime rather than always 1025 on the host machine. Read the host and mapped port from the test container fixture.

### 16.2. Inspecting via SMTP Test UI

After sending, many SMTP test tools let you inspect:

- HTML preview.
- `text/plain`.
- Raw MIME.
- Inline attachments list.
- Attachment filenames.

Inspect **raw MIME** before blaming a mail client for rendering bugs. If `Content-ID` is absent, the bug is in message construction. If MIME is valid and only one client fails, the cause likely lies in compatibility or that client's policy.

### 16.3. Tests Must Not Depend on Real Providers

Never use production email addresses, public accounts, or real providers for continuous automated tests:

- Increases spam complaints.
- Consumes quotas or incurs costs.
- Makes tests flaky due to network/anti-spam rules.
- Risks leaking sample content, attachments, or internal info.

Keep tests local/isolated; afterward, run an authorized staging smoke test to verify client compatibility against approved test mailboxes.

### 16.4. Why SMTP Tests Still Do Not Guarantee Gmail/Outlook Render Identically

MIME structure can be verified at the protocol layer, yet email clients have differing HTML engines and security policies. An SMTP sink test confirms the message transmitted the right data; **it does not prove every recipient client renders it identically**. For critical templates, test on the specific client/version matrix supported by your product.

## 17. Differences Across Mail Clients in Displaying Images

Even when MIME is valid, image rendering still depends on the mail app, user settings, and organizational policies.

### 17.1. Remote Images May Be Blocked

With HTML:

~~~html
<img src="https://cdn.example.com/email/logo.png" alt="Logo">
~~~

Some clients may:

- Block remote image loading by default.
- Load only after the user clicks “display images”.
- Route fetches through an image proxy/cache to limit IP and user tracking.
- Block disallowed domains or schemes.
- Block mixed content or insecure HTTP.

Therefore, an image not showing **does not automatically prove** the URL is broken or Spring Mail failed.

### 17.2. Inline CIDs Also Have Differences

CID works well across many clients, yet edge cases exist:

- A client lacks support or sanitizes parts of HTML.
- MIME tree structure clashes with the client's parser.
- Duplicate `Content-ID`s cause the parser to pick the wrong part.
- Forwarding/rewriting alters the MIME structure.
- The client lists inline images under attachments.
- A mail security gateway rewrites or strips HTML content.

Thus, when pixel-accurate rendering matters, test real clients and inspect MIME **after passing through any gateway** when possible.

### 17.3. Some Clients Strip CSS Background Images

Do not confuse:

~~~html
<img src="cid:banner">
~~~

with:

~~~html
<div style="background-image:url('cid:banner')">
  ...
</div>
~~~

Email client support for CSS background images differs from `<img>` tag support; several email rendering engines restrict CSS or require specialized markup. When an image conveys key information, using `<img>` with alt text and HTML text fallbacks is far easier to control.

### 17.4. SVG, WebP, and Animated GIFs

Formats carry differing support and security policies:

| Format | Characteristics | Email Notes |
| --- | --- | --- |
| PNG | Supports alpha/transparency; great for logos | File sizes can get large for photos |
| JPEG | Suited for photos/banners | No transparency support |
| GIF | Supports animation | Some clients show only the first frame |
| SVG | Vector, compact size | Many clients strip or block for security |
| WebP | Efficient compression | Older clients may lack support |

When an asset must render broadly, export appropriately sized PNG/JPEG files. Never embed user-uploaded SVGs straight into emails without security inspection.

### 17.5. Dark Mode and Image Sizing

In dark mode, a logo with a transparent background can become unreadable if the text/logo is dark. Some clients invert background colors while leaving images untouched:

~~~html
<img src="cid:companyLogo"
     alt="Company"
     width="160"
     style="display:block;border:0;">
~~~

Setting explicit dimensions or table layouts keeps images from blowing up on mobile. You may need dark-mode-friendly logos or neutral backing plates in tested templates, without relying solely on CSS media queries since support varies.

### 17.6. When Mail Is Forwarded

Forwarding may:

- Preserve MIME and CID parts intact.
- Wrap the email as a `message/rfc822` attachment.
- Extract only part of the HTML and drop inline resources.
- Rewrite `Content-ID`s or assets per gateway rules.

The sending app cannot control every client's forwarding behavior. To keep content meaningful, never put core facts solely inside images; include matching HTML text and plain text.

## 18. Security When Handling Local Image Paths

File path bugs are not merely cosmetic; loading files from untrusted paths can let the app read sensitive files or leak system internals.

### 18.1. Never Use User-Supplied File Paths Directly

Dangerous API example:

~~~json
{
  "recipient": "customer@example.net",
  "logoPath": "../../secrets/app-config.yml"
}
~~~

If the backend executes:

~~~java
Path path = Paths.get(request.logoPath());
helper.addInline("logo", new FileSystemResource(path), "image/png");
~~~

an attacker can try reading files outside the intended asset directory. Content-Type `image/png` is just a label; it **does not stop the library from reading bytes** of another file and emailing them out.

Better solution: the API accepts only an authorized **asset ID**:

~~~json
{
  "templateId": "welcome-v3",
  "brandAssetId": "tenant-asset-opaque-id"
}
~~~

The backend maps the ID to the tenant's object/file and validates permissions, version, content type, and size before sending.

### 18.2. Canonical Paths and Symlinks

If files must live on disk under a shared directory, defend against path traversal and symlinks:

~~~text
allowedRoot = /srv/mail-assets/tenants/T1
candidate   = /srv/mail-assets/tenants/T1/../../secrets
~~~

Calling only `candidate.normalize().startsWith(allowedRoot)` may not cover **symlinks** or concurrent filesystem races. For sensitive assets:

1. Use system-generated resource IDs/object keys, never user-supplied paths.
2. Restrict root directories and OS permissions.
3. On filesystems, resolve/canonicalize properly, account for symlinks, and verify regular files.
4. Open streams with least privilege.
5. Pin content or versions so files cannot swap after validation.

Never let a worker read arbitrary host paths simply because a caller has permission to send email.

### 18.3. SSRF When Auto-Fetching Images from URLs

If a feature accepts an `imageUrl` from a user, downloads it, and embeds it:

~~~text
User provides imageUrl = http://127.0.0.1:8080/admin
                       = http://169.254.169.254/...
                       = http://internal-service/secret
~~~

that creates **Server-Side Request Forgery**. Never let an unconstrained HTTP client fetch arbitrary URLs and attach their responses to emails.

Safer design:

- Allow only allowlisted asset servers/hosts.
- Reject private, loopback, link-local, and metadata IPs.
- Validate DNS resolution and actual socket connections, not just the initial host string.
- Cap redirects, timeouts, total bytes, and content types.
- Never forward internal `Authorization`/`Cookie`/secrets on image fetch requests.
- Prefer fetching assets via a trusted object storage SDK using authorized keys.

Any “auto-convert remote images to inline” tool needs matching security boundaries.

### 18.4. `file:` URIs Can Expose Internal Structure

An HTML email containing:

~~~html
<img src="file:///home/service-account/private/logo.png">
~~~

leaks directory names, internal usernames, OS types, or deployment layout to recipients. While not always directly exploitable alone, it is unnecessary and has no place in public HTML.

In addition, mail clients and security filters may flag or strip `file:` due to local file access risks.

### 18.5. Images May Contain Sensitive Data

Even when fixed with CID, if an image is an invoice, ID card, login QR code, or personal document, it becomes **data attached inside the email**. Recipients can:

- Forward it.
- Save raw MIME.
- Save the image to disk.
- Sync the email across third-party services/devices.

Never use CID to “hide” sensitive data: an inline image is a MIME part carrying real bytes. When access control or revocation is needed, a link to an authenticated portal with expiry and auditing fits far better.

### 18.6. Never Turn an External Path into Access Rights

For instance, a `brandAssetId` should resolve scoped to the tenant:

~~~java
InlineAsset asset = assetService.resolveAuthorized(
        authenticatedTenantId,
        brandAssetId);
~~~

`resolveAuthorized` is an application-defined API enforcing tenant ownership, asset status, file type, size, and version. Two files sitting in the same bucket does not mean every tenant may use both.

### 18.7. Logging and Observability

Never log raw:

~~~text
email HTML
image bytes
signed storage URL
local secret path
raw MimeMessage
~~~

in production just to debug images. Log low-sensitivity metadata instead:

~~~json
{
  "event": "mail.inline_asset_added",
  "deliveryId": "opaque-id",
  "assetType": "BRAND_LOGO",
  "contentId": "brandLogo",
  "mimeType": "image/png",
  "sizeBytes": 4821
}
~~~

If `contentId` comes from untrusted input or has high cardinality, never use it as a metric label. For file path errors, use error codes like `INLINE_ASSET_NOT_FOUND`, `INLINE_ASSET_UNREADABLE`, `MIME_INLINE_CID_MISMATCH`; keep paths and customer names out of tags.

## 19. Async Sending: Image Exists at Enqueue Time Yet Disappears by Send Time

This is a very common production variant of the file path bug.

### 19.1. Wrong Example: Task Holding a Request's Local `Path`

~~~java
public void submitWelcome(
        String recipient,
        MultipartFile uploadedLogo) throws IOException {

    Path temp = Files.createTempFile("logo-", ".png");
    uploadedLogo.transferTo(temp);

    asyncMailQueue.submit(
            new WelcomeMailJob(recipient, temp.toString()));

    Files.deleteIfExists(temp);
}
~~~

The worker may execute after the file was deleted. In systems with durable queues, the task can also be picked up by **another replica** that never had the file.

### 19.2. Fix: Persist Assets Durably Before Enqueueing

~~~text
HTTP upload / asset lookup
           |
           v
Validate tenant / content / size
           |
           v
Persist image to authorized object storage
  - immutable object key
  - version / checksum
  - retention sufficient for retries
           |
           v
Commit mail outbox job with asset reference
           |
           v
Async worker resolves image source
           |
           v
Build MIME with cid + addInline
           |
           v
JavaMailSender.send
           |
           v
Mark job outcome + cleanup by policy
~~~

If the file lives on the fixed classpath, there is no need to re-upload per email. Simply ensure **every worker** runs an application version carrying the right asset.

### 19.3. When Staging to a Temporary File Is Unavoidable

Some mail APIs or imaging libraries work more easily with local files. A worker can:

1. Download the exact object version into a dedicated staging directory.
2. Enforce total byte and filesystem capacity limits.
3. Verify checksums/content types if required.
4. Pass `FileSystemResource` to `addInline`.
5. Call `mailSender.send` while the file remains present.
6. Clean up inside `finally` **after transport completes**.

~~~java
Path staged = stageAuthorizedImage(assetRef);

try {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setSubject("Notification");
    helper.setText(
            "Your notification",
            "<html><body>"
                    + "<img src=\"cid:brandLogo\">"
                    + "</body></html>");

    helper.addInline(
            "brandLogo",
            new FileSystemResource(staged),
            "image/png");

    mailSender.send(message);
} finally {
    Files.deleteIfExists(staged);
}
~~~

`stageAuthorizedImage(...)` is an application abstraction enforcing size, storage, tenant ownership, and timeouts. If `Files.deleteIfExists` fails in `finally`, production code should log the cleanup error for a sweeper without masking the primary SMTP error. Never use `finally` to delete the durable source object still needed for retries.

### 19.4. Crash Before Cleanup

`finally` never runs if the process is killed abruptly or the node loses power. For production staging, run a **sweeper** keyed off age and job ownership, enforce disk quotas/monitoring, and restrict OS permissions.

Never delete files solely by age in a shared staging directory if another worker might still be using them. Attach lease/lifecycle metadata or isolate staging paths per attempt for safe cleanup.

### 19.5. Retries Need the Same Content, Not Just the Same Filename

Suppose a banner at `/assets/current-banner.png` gets replaced between attempt 1 and attempt 2:

~~~text
Attempt 1 -> logo version V1
Attempt 2 -> logo version V2
~~~

Two emails for the same business delivery end up with different artwork. For notifications requiring auditability/reproducibility, store an **immutable asset version** or checksum so retries send identical content. If business rules intentionally fetch the latest asset on retry, make that an explicit policy rather than an accidental file overwrite.

### 19.6. SMTP Accepted Is Not a Reason to Delete All Source Data

When `send` returns normally, the SMTP relay accepted the submission from the client's perspective. Yet if marking `SENT` in the database fails, the app may need reconciliation or retry policies. Tie asset retention to the full delivery/outbox lifecycle, not merely `send` returning. Avoid deleting logo/banner snapshots before durably recording outcomes.

## 20. Email Size, Base64, and the Cost of Inline Images

Inline CID fixes broken local file paths, yet is not free in bandwidth or message size.

### 20.1. Base64 Inflates Transmitted Size

A 300 KiB PNG encoded as Base64 grows by roughly one third before adding headers, CRLFs, and MIME boundaries.

~~~text
Raw PNG bytes
     |
     v
MIME Base64 encoding (~4/3)
     |
     v
SMTP message bytes
     |
     v
Provider message SIZE limit
~~~

This is why providers reject emails with multiple inline images/attachments even when individual files look small on disk. Limits apply to the **final MIME message**, not just raw file sizes.

### 20.2. Using One Logo Across 100,000 Emails

Embedding a 100 KiB logo in each email transmits the image bytes 100,000 times across separate messages, before overhead:

~~~text
100 KiB x 100,000 messages
= ~9.5 GiB raw image bytes
~~~

After MIME/Base64 and framing overhead, total SMTP bytes are even higher. For huge campaigns, a public HTTPS image on a CDN reduces per-message size, at the trade-off of clients possibly blocking remote images.

### 20.3. Optimize Images Before Embedding

Principles:

- Resize to actual display dimensions in the email; never embed a 4000px image to render at 150px.
- Choose PNG for crisp logos/icons and JPEG for photos/banners.
- Pre-compress in the asset pipeline instead of re-encoding/resizing on every mail attempt needlessly.
- Cap combined inline asset and attachment bytes per email type.
- Cap inline image counts and MIME part counts.
- Reuse one CID across multiple occurrences of the same image when client compatibility and templates allow.
- Estimate final MIME size before picking an SMTP provider with tight `SIZE`/quota limits.

### 20.4. Do Not Run Heavy Image Processing on SMTP Threads

If each email downloads a logo, resizes, hashes, and converts formats inside the SMTP send thread, throughput drops and timeouts get muddied:

~~~text
Mail worker:
  remote download
  -> resize
  -> format convert
  -> MIME build
  -> SMTP send
~~~

For static assets, pre-build image variants and cache appropriately. For per-tenant assets, bound caches with tenant scoping, versioning, and memory caps; never cache unbounded bytes from arbitrary uploads.

### 20.5. Resource Repeatability vs. Memory

Two common performance mistakes:

**Mistake 1:** loading every image into huge `byte[]` arrays out of fear `FileSystemResource` won't work.

~~~java
byte[] all = Files.readAllBytes(bigImagePath);
helper.addInline(
        "hero",
        new ByteArrayResource(all),
        "image/jpeg");
~~~

This creates large heap spikes when sending many messages concurrently.

**Mistake 2:** creating a single-use stream to “save memory”:

~~~java
InputStream once = remoteStore.open(objectKey);
helper.addInline(
        "hero",
        new InputStreamResource(once),
        "image/jpeg");
~~~

This breaks whenever the library re-reads the stream. The right design is a **repeatable source with explicit lifecycle and byte limits**, without forcing all bytes into RAM.

### 20.6. Separate Asset Prep Time from SMTP Time

Metric table:

| Stage | Suggested Metric |
| --- | --- |
| Resolve asset metadata | `mail_asset_resolve_duration` |
| Load/stage image | `mail_asset_load_duration` |
| Build MIME | `mail_mime_build_duration` |
| SMTP submission | `mail_smtp_submit_duration` |
| Inline asset bytes | `mail_inline_asset_bytes` |
| Asset source failures | `mail_inline_asset_failures_total` |
| Staging disk usage | `mail_staging_bytes` |

In Micrometer, keep tags bounded (`asset_kind`, `source_type`, `error_code`) instead of putting raw filesystem paths, tokenized URLs, or recipient emails in labels.

## 21. Common Error Diagnostic Table

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Only alt text appears | `src` uses local path/file URI or image blocked | Inspect raw HTML; switch to CID/HTTPS |
| Image shows in IDE but vanishes in email | Preview can read local files | Inspect actual MIME |
| Sends OK yet image broken in all clients | Missing CID part in HTML or unreachable URL | Check `Content-ID` and raw MIME |
| HTML has `cid:logo`, part has `<brandLogo>` | Mismatched IDs | Align mapping |
| Inline image shows as attachment | Client lists inline parts as files | Check if HTML renders; may be client behavior |
| `logo.png` attached yet HTML broken | Used `addAttachment` instead of `addInline` | Use `addInline` and `cid:` |
| `IllegalStateException` on `addInline` | Helper not in multipart mode | Create multipart helper first |
| Image breaks only after JAR packaging | Used `src/main/resources` or `getFile()` | Use `ClassPathResource` |
| Image breaks only inside container | Different path or unmounted/unreadable volume | Check runtime asset; still must use CID |
| Another pod cannot read image | Job stored old pod's local temp path | Use durable object/version reference |
| Flaky display under async | File cleaned up or overwritten before `send` | Keep snapshot until send completes |
| Image resource stream error | Single-use `InputStreamResource` | Use repeatable source |
| `FileNotFoundException` on send | File missing at send time | Fix source/lifecycle |
| `AccessDeniedException` | OS user/ACL lacks read permission | Grant minimal read permissions |
| Image renders wrong format | Mismatched `Content-Type` or bytes | Validate format, set accurate MIME type |
| Huge PNG rejected by SMTP | Total MIME/Base64 exceeds limit | Resize/compress/use HTTPS or link |
| HTTPS image loads in browser, not in mail | URL needs cookie/auth or client blocks remote images | Test public unauthenticated request; check privacy settings |
| `http://localhost:8080/logo.png` broken | URL points to recipient's machine | Use public HTTPS or CID |
| Signed URL works only on day one | Link expired | Use stable public asset or CID |
| Data URI missing in Outlook/some clients | Client lacks support or strips `data:` | Use CID/HTTPS appropriately |
| CSS background image missing | Client strips/ignores CSS | Use `<img>` and HTML text fallback |
| SVG blocked | Mail client/security sanitizer | Use vetted PNG/JPEG |
| CID part exists yet image still broken | MIME tree, bytes, content type, or CID parser | Inspect raw MIME and decoded image |
| Dark logo vanishes in dark mode | Client flips background without flipping image | Use high-contrast assets/templates |
| Image shows yet mail flagged as spam | Not necessarily CID; content, domain, size, reputation | Review auth/deliverability |
| Logs leak local paths | Template put filesystem path into HTML/logs | Isolate asset IDs, sanitize logs |
| Retry sends different image | Source file overwritten between attempts | Pin asset version/checksum |
| Reading user-provided image URL hits internal endpoints | SSRF | Use allowlists / trusted object storage |

### 21.1. Prioritize Diagnostics in Order

Do not start by swapping SMTP providers or raising timeouts when the email arrived and only an image is broken:

~~~text
1. Inspect HTML src
2. Inspect MIME Content-ID + Content-Type
3. Inspect actual image bytes
4. Check multipart layout
5. Check backend resource lifecycle
6. Check recipient client rendering behavior
7. Check URL/provider/security gateways if relevant
~~~

If a local file path is still sitting in HTML, the bug is at **content preparation**, not proof of an SMTP network issue.

## 22. Runbook: Images Break After Deployment

### Scenario

On a developer's machine, the welcome email shows the logo; after deploying to containers, recipients see only a broken image.

### Step 1 — Inspect `src` in the Real Email

If you see:

~~~html
<img src="src/main/resources/mail/logo.png">
~~~

switch immediately to `cid:companyLogo` or a proper HTTPS URL. Having the image in the source tree matters only to the build process.

If you already see:

~~~html
<img src="cid:companyLogo">
~~~

proceed to the MIME step.

### Step 2 — Check the `Content-ID` Part

In raw MIME, look for:

~~~text
Content-ID: <companyLogo>
Content-Type: image/png
~~~

If missing, verify whether `helper.addInline` executed, whether the helper was multipart, and whether you sent **the exact `MimeMessage` you built**.

### Step 3 — Check the Source Resource When the Worker Runs

For classpath:

~~~java
ClassPathResource resource =
        new ClassPathResource("mail/logo.png");
~~~

If the classpath asset is missing from the build artifact, fix packaging. Never call `resource.getFile()` when the image may reside inside a JAR.

For filesystems:

~~~text
Configured path: /app/assets/logo.png
Does it exist in container?
Is it readable by JVM user?
Is it the correct PNG file?
~~~

Never hardcode a developer workstation path in production.

### Step 4 — Inspect MIME Bytes

If the part has `Content-ID` yet bytes are empty/corrupt:

- Check for zero-byte/corrupt files.
- Check resource read exceptions.
- Check whether the file was modified/cleaned up mid-send.
- Check whether `Content-Type` matches the actual format.
- Check whether a custom `InputStreamSource` opens a fresh stream each time.

### Step 5 — Diagnose per Client

If MIME is valid on the SMTP test server yet one client hides it:

- Check if the client blocks remote images.
- Check content type/format and MIME tree.
- Check CSS/background image usage.
- Check gateway or image proxy policies.
- Ensure logos have alt text and core info is never solely inside pixels.

### Step 6 — Fix and Monitor

Once the proper reference is deployed:

1. Send to a test mailbox, never to a production recipient list for bulk testing.
2. Inspect raw MIME and supported clients.
3. Monitor `INLINE_ASSET_NOT_FOUND`/`MIME_PREPARATION_FAILED`.
4. With async queues, confirm retries keep using the right asset version.
5. Keep minimal logs/correlation IDs for incident auditing.

## 23. Practical Example: Fixing a Welcome Email with a Broken Logo

Suppose an app has a welcome template for new users. Initially, code built HTML by inserting a local path directly into `src`.

### 23.1. Wrong Implementation

~~~java
@Service
public class WrongWelcomeMailService {

    private final JavaMailSender mailSender;

    public WrongWelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient) throws MessagingException {
        Path logo = Path.of(
                "/opt/app/assets/brand-logo.png");

        String html = """
                <html>
                  <body>
                    <img src="%s" alt="Brand">
                    <h1>Welcome!</h1>
                  </body>
                </html>
                """.formatted(logo);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome!");
        helper.setText(html, true);
        mailSender.send(message);
    }
}
~~~

**Why it fails:**

- `formatted(logo)` only turns `Path` into a string; it does not read the file.
- HTML contains `<img src="/opt/app/assets/brand-logo.png">`.
- The helper creates no `image/png` part.
- Recipients have neither the server's origin nor filesystem paths.
- `MimeMessageHelper(message, "UTF-8")` here is not configured as multipart, leaving no way to add inline assets.

SMTP still succeeds because HTML is just text. This is a textbook example of **email sent successfully yet rendered broken**.

### 23.2. Fixed Implementation with Logo on Classpath

If the static logo lives at:

~~~text
src/main/resources/mail/images/brand-logo.png
~~~

fix it to:

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

    public void send(String recipient) throws MessagingException {
        String plainText = """
                Welcome!
                Thank you for joining us.
                """;

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:brandLogo"
                         alt="Brand"
                         width="160"
                         style="display:block;border:0;">
                    <h1>Welcome!</h1>
                    <p>Thank you for joining us.</p>
                  </body>
                </html>
                """;

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome!");

        helper.setText(plainText, htmlText);

        helper.addInline(
                "brandLogo",
                new ClassPathResource(
                        "mail/images/brand-logo.png"),
                "image/png");

        mailSender.send(message);
    }
}
~~~

The HTML **contains no filesystem paths**. It references only the CID supplied by the MIME part in the same message. When the logo is packaged inside a JAR, `ClassPathResource` still opens its stream cleanly.

### 23.3. If Logos Vary per Tenant

Never build arbitrary folders from input:

~~~java
Path logo = Paths.get(
        "/assets/", request.getTenantId(), request.getLogoName());
~~~

Instead, a trusted service resolves an asset reference:

~~~java
BrandAssetRef asset = brandAssets.requireAuthorizedLogo(
        authenticatedTenantId);

InlineAsset logo = brandAssets.openVersionedAsset(
        asset.objectKey(), asset.versionId());
~~~

Then:

~~~java
helper.setText(plainText, renderedHtmlWithCidBrandLogo);
helper.addInline(
        "brandLogo",
        logo.source(),
        logo.contentType());
~~~

`BrandAssetRef` and `brandAssets` are application abstractions. Enforce tenant ownership, immutable versions, size/format checks, and repeatable reads. Backing storage can be object storage or a filesystem; recipients never need to know.

### 23.4. If Using HTTPS Instead of CID

When a non-sensitive marketing banner lives on a CDN:

~~~java
String approvedBannerUrl =
        assetCatalog.requirePublicMailImageUrl("welcome-banner");

String html = """
        <html>
          <body>
            <img src="%s"
                 alt="Welcome"
                 width="600">
          </body>
        </html>
        """.formatted(escapeHtmlAttribute(approvedBannerUrl));
~~~

`assetCatalog` and `escapeHtmlAttribute` are illustrative application APIs; escaping must encode safely for HTML attribute contexts. URLs must come from a trusted catalog/allowlist, use HTTPS, remain live long enough for email lifespans, and require no developer browser session.

For HTTPS images, **do not call `addInline`** unless intentionally sending a separate image part. Mail clients fetch over the network when policy allows.

### 23.5. Outcomes to Verify

| Before Fixing | After Fixing with CID |
| --- | --- |
| HTML has `src="/opt/app/assets/logo.png"` | HTML has `src="cid:brandLogo"` |
| MIME has only `text/html` | MIME has `text/html` and inline `image/png` |
| No `Content-ID` | Has `Content-ID: <brandLogo>` |
| Recipient needs server file | Image bytes sit inside MIME message |
| Breaks across IDE/Docker/K8s | Uses runtime-safe classpath/asset source |
| No asset lifecycle management | Source stays alive through build/send with cleanup policy |

## 24. Frequently Asked Questions

**“Why does the image display on a web page yet not in an email?”**  
Web pages have an HTTP origin and can fetch images via web server URLs/paths. Emails are read on another device/app with no base URL or filesystem access to the sending server. Use inline CID or an appropriate HTTPS URL.

**“Does Spring Mail automatically load files when it sees `<img src="/path">`?”**  
No. HTML is plain text payload. You must explicitly call `MimeMessageHelper.addInline` or use an accessible web URL.

**“If the absolute path is right on the server, why is the image still broken?”**  
A valid path only helps the **backend** find the file. Recipients still cannot see or read that file. You must turn the bytes into a MIME part or a public HTTPS asset.

**“Is changing `C:\logo.png` to `file:///C:/logo.png` enough?”**  
No. `file:` still points to the filesystem of whichever machine parses the URI, and mail clients normally block reading it. Changing syntax neither uploads nor embeds the image.

**“Can we use `src="./logo.png"`?”**  
Do not rely on relative paths in email. MIME HTML generally has no HTTP base URL, and attachment filenames do not resolve as URLs automatically.

**“If we attach a file with `addAttachment`, will `<img>` display it?”**  
Not automatically. `addAttachment` creates an attachment; `<img>` needs `cid:<id>` pointing to an inline part added with `addInline`, or an HTTPS URL.

**“Must `Content-ID` and filename be identical?”**  
No. CID identifies the MIME part; filename is merely file metadata. You can use CID `brandLogo` for a file named `logo-v3.png`. HTML must match the CID, not the filename.

**“Why does `addInline` take a similar ID string?”**  
The method accepts a content ID and an image source. `addInline("logo", resource, "image/png")` creates a part with ID `logo`, and HTML uses `cid:logo` to reference that part.

**“Do we write angle brackets in the HTML CID?”**  
No. For a `Content-ID` header `<brandLogo>`, HTML uses `cid:brandLogo`, not `cid:<brandLogo>`.

**“Is `multipart=true` required to use CID?”**  
Yes. Inline images require a separate MIME part, so the helper must be initialized in multipart mode. `MULTIPART_MODE_MIXED_RELATED` is a suitable choice supporting both inline resources and attachments.

**“Is `setText(html, true)` enough?”**  
No. It marks the body as HTML without adding an inline image part. You need a multipart helper and `addInline`.

**“Should `setText` or `addInline` be called first?”**  
Set text/HTML with `setText` before calling `addInline`, as recommended by `MimeMessageHelper` to avoid compatibility quirks in some mail clients.

**“If the file is in `src/main/resources`, can `FileSystemResource` be used?”**  
In an IDE it might locate the file, yet after JAR packaging that source path usually vanishes. For packaged assets, use `ClassPathResource` to read via the classpath.

**“Why does `ClassPathResource.getFile()` fail after deployment?”**  
Resources inside a JAR do not exist as standalone files on disk. Pass `ClassPathResource` directly into `addInline` or open its stream instead of converting to `File`.

**“Do images placed in Spring Boot's `static` folder automatically become email URLs?”**  
Not automatically. If your app serves images over HTTP, you can construct a public HTTPS URL, yet `/static/logo.png` or a local classpath path in email HTML does not magically become an Internet URL.

**“Can we use a `localhost` URL when the app and SMTP server share the same machine?”**  
Not for external recipients. When the mail client loads the image, `localhost` points to **the recipient's machine** or proxy, not your backend.

**“Can a Dockerized app read files from the host?”**  
Only if packaged or mounted with proper read permissions. Even when the backend can read them, HTML still must use CID/HTTPS, never container paths.

**“What if the file is in `/tmp` and sent with `@Async`?”**  
The file may be deleted before the worker sends, or the job may run on a different replica. Use durable asset references/snapshots, retain files until sending completes, and enforce cleanup and retry policies.

**“Can `InputStreamResource` be used for inline images?”**  
Not by default, because it wraps a single-use stream. If the MIME encoder reads more than once, it can fail. Use `FileSystemResource`, `ClassPathResource`, `ByteArrayResource`, or a custom repeatable `InputStreamSource`.

**“What if we only have a `byte[]` of the image?”**  
`ByteArrayResource` fits small images already in RAM. For large images and high concurrency, prefer repeatable streams from files/object storage to avoid heap spikes.

**“Does `Content-Type: image/png` guarantee the mail client shows a PNG?”**  
No. Image bytes must be genuinely valid, the MIME tree and CID must match, and the client must support rendering without gateway/client blocking. `Content-Type` is only one prerequisite.

**“Can JPEG/WebP/SVG be passed to `addInline`?”**  
At the MIME level you can attach resources with matching content types, yet display depends on clients. PNG/JPEG offer better compatibility; SVG is often blocked for security.

**“Why did an inline image show up in the attachments section?”**  
Because the image is still a MIME body part. Some clients list it as an attachment even while rendering HTML fine. If HTML fails to show it, inspect `Content-ID` and MIME structure.

**“Should every image be converted to `data:image/png;base64`?”**  
Not by default, because email client support varies, HTML grows large, and sanitizers often strip it. CID or HTTPS usually offers cleaner trade-offs.

**“Are Base64 in raw MIME and Data URIs the same?”**  
No. MIME Base64 is a transfer encoding for a separate image part; Data URIs embed bytes inside an HTML attribute. CID uses `Content-ID` to link HTML to a MIME part.

**“Does CID work when the recipient is offline?”**  
Once the email and its MIME parts are downloaded to the device, inline images can display without fetching from a CDN. Exact behavior depends on the mail client and message sync settings.

**“Is HTTPS always better than CID?”**  
No. HTTPS shrinks email size and suits public/CDN assets, yet clients may block remote images, URLs can expire, and privacy concerns arise. CID grows MIME size yet needs no external fetch at render time.

**“Can signed URLs be used as `img src`?”**  
Be cautious. URLs can expire and break emails later; tokens in URLs can be forwarded or cached. For sensitive images, prefer an authenticated portal link or transmit data only as policy permits.

**“Can images be blocked by the mail client?”**  
Yes. Clients may block remote images or restrict formats, CSS, and MIME handling. Inspect raw MIME and test target clients to separate message-build bugs from rendering policies.

**“Is a logo missing in dark mode a CID bug?”**  
Not necessarily. The image may exist yet lack contrast against a dark background. Choose appropriate assets/templates or padded backgrounds with tested contrast.

**“Should OTPs or transaction terms be placed only inside an image?”**  
No. If images are blocked, users miss vital information. Place core content in HTML text and plain text, using images only as complements.

**“If we replace an image on the server after sending, will recipients see the new image?”**  
With CID, bytes are embedded in the email and never change. With HTTPS, the URL may serve the new image, though caches/proxies may hold the old copy. Pick the behavior matching business needs.

**“Does `Content-ID` prevent recipients from forwarding images?”**  
No. Inline images are data inside the email and can be saved or forwarded. CID is neither DRM nor access control.

**“Is letting an HTML template take `logoPath` from a user dangerous?”**  
Yes. Arbitrary file paths allow path traversal/unintended file reads. Use tenant-checked asset IDs and an approved source registry.

**“What if we auto-download every URL to convert to CID?”**  
You must defend against SSRF, private IP/DNS rebinding, redirects, oversized downloads, and MIME spoofing. Better to use trusted object storage/catalogs rather than fetching arbitrary URLs.

**“How do we know Spring Mail actually embedded the image?”**  
Check raw MIME for the matching `Content-ID`, accurate `Content-Type`, and valid image bytes. Unit/integration tests can parse the message and verify the part.

**“Is it normal for SMTP send to return success while images still break?”**  
Yes. SMTP only delivers the constructed message; transport never evaluates whether HTML `img[src]` points to an asset viewable on the client.

**“Do we need to test on Gmail/Outlook or is an SMTP sink enough?”**  
An SMTP sink verifies MIME was built and sent properly. To guarantee rendering on target clients, add real-client testing or an authorized rendering-test service.

**“Can we retry sending if an image failed to render in a client?”**  
Never automatically. Once SMTP accepted, resending creates duplicates. Fix the template/asset mapping for new deliveries, and handle already-sent emails per business and communications policies.

## 25. Checklist for Embedding Images in HTML Emails with Spring Mail

### HTML Template Checks

1. No `src="C:\..."`, `src="/opt/app/..."`, `src="file:///..."`, or `src="./logo.png"` in outgoing emails.
2. With CID, every `<img src="cid:...">` has a matching inline asset.
3. CID strings in HTML match the ID passed to `addInline`.
4. No angle brackets `<...>` inside `cid:` values in HTML.
5. Attachment filenames are never confused with `Content-ID`s.
6. When using HTTPS, URLs have valid schemes/domains and are approved public per policy.
7. When images may be blocked, `alt` text exists and critical text does not depend on images.
8. HTML size and markup suit target mail clients.

### `MimeMessageHelper` Checks

9. Messages are created via `JavaMailSender.createMimeMessage()`.
10. Helpers are initialized in multipart mode when using inline images.
11. `setText(plainText, htmlText)` is called to provide plain-text fallbacks where appropriate.
12. `addInline` is called **after** `setText`.
13. Accurate content types like `image/png` or `image/jpeg` are used.
14. Never call `addAttachment` alone and expect HTML to reference it by filename.
15. Send the exact `MimeMessage` that received inline parts rather than accidentally sending another instance.
16. When mixing attachments and inline images, verify the mixed/related MIME tree is valid.

### Image Source Checks

17. JAR-packaged assets are read with `ClassPathResource`.
18. No runtime reliance on `src/main/resources` existing on disk.
19. `ClassPathResource.getFile()` is never called when resources may sit inside a JAR.
20. External files use explicitly configured paths and `FileSystemResource`/`PathResource`.
21. Files are readable by the JVM/container OS user.
22. Images have valid actual formats, not just `.png` extensions.
23. Resources remain repeatable during MIME serialization.
24. Never use single-use `InputStreamResource` for assets read multiple times.
25. Assets are not deleted or overwritten before sending completes.
26. With multiple replicas, never put one pod's local path into another pod's job.

### Security and Lifecycle Checks

27. Never allow callers to supply arbitrary filesystem paths.
28. Asset lookups are scoped by tenant/permissions.
29. When fetching images from URLs, enforce trusted sources/allowlists and SSRF protections.
30. Enforce max image bytes, total MIME bytes, MIME part counts, and concurrency limits.
31. Per-tenant/campaign assets use immutable versions or checksums when retries need consistency.
32. Never log raw MIME, file bytes, signed URLs, or local secret paths.
33. Staging directories have ACLs, quotas, cleanup, and a crash sweeper.
34. Asset retention covers unfinished outbox/retry lifecycles.
35. Sensitive image data is sent only when policy allows; CID never replaces authorization.

### Sending and Rendering Checks

36. Sent raw HTML uses valid CID/HTTPS with zero local paths.
37. Raw MIME carries `Content-ID`, `Content-Type`, and valid image bytes.
38. Plain-text alternatives still carry essential facts.
39. Test against fake SMTP/sinks; never blast production SMTP for debugging.
40. Test at least one real client from the target user group for important templates.
41. Accept that some clients block remote images or restrict formats.
42. Once accepted, never auto-retry merely because one client hid an image.
43. Metrics/alerts exist for asset-not-found, MIME preparation failures, and staging quotas.
44. A runbook exists distinguishing local path bugs, MIME mismatches, backend resource failures, and client rendering quirks.

## 26. Decision Diagram: Choosing How to Embed Images in Email

~~~text
                     Need image in an email?
                               |
                               v
                  Is image essential to content?
                     |                   |
                    Yes                 No
                     |                   |
                     v                   v
              Keep HTML/plain text   Consider whether
              meaning without image  image is necessary
                     |
                     v
               Is image sensitive?
                 |          |
                Yes         No
                 |          |
                 v          v
         Should it require    Is it a small,
         authenticated view?  stable brand asset?
           |          |           |           |
          Yes         No          Yes         No
           |          |           |           |
           v          v           v           v
        Secure     Consider CID  Use CID    Consider HTTPS
        portal     if sending    inline     for public/CDN
        link       bytes is      from a     images
                   authorized    resource      |
                      |           |            v
                      v           v       URL still reachable?
               Prepare durable   cid +      No auth cookie?
               resource snapshot addInline  Size/privacy OK?
                      |           |            |
                      +-----------+------------+
                                  |
                                  v
                       Build MIME + validate
                                  |
                                  v
                         Fake SMTP/MIME test
                                  |
                                  v
                          Send to recipient
~~~

### Common Choice Scenarios

| Content | Usually Reasonable Choice | Reason |
| --- | --- | --- |
| Static company logo in welcome email | CID + `ClassPathResource` | No external URL dependency, bundled with app |
| Tenant logo stored in object storage | CID + repeatable/versioned source | Loads the exact authorized asset |
| Large public marketing banner | HTTPS CDN | Cuts per-message payload size |
| User-uploaded image sent to one recipient | CID or attachment as needed | Durable payload, format and auth checks |
| Image holding personal data needing revocation | Secure portal link | Retains access control after sending |
| Image existing only in request `/tmp` | Never use path directly | Stage durably or build MIME while file lives |
| `<img src="file:///...">` in template | Never use | Not portable to recipients |
| Logo in `src/main/resources` after packaging | `ClassPathResource` + CID | Readable inside JAR |

## 27. Summary of Wrong vs. Right Flows

### Wrong Approach

~~~text
Local file path
    |
    v
Path.toString()
    |
    v
HTML <img src="/opt/app/logo.png">
    |
    v
JavaMailSender.send
    |
    v
Recipient client cannot read server filesystem
    |
    v
Broken image
~~~

### Right Approach with CID

~~~text
Local/classpath/authorized remote image
                 |
                 v
        Spring Resource / repeatable source
                 |
                 v
      MimeMessageHelper multipart mode
                 |
          +------+-------+
          |              |
          v              v
  HTML <img src=      addInline(
   "cid:brandLogo">      "brandLogo",
                        resource,
                        "image/png")
          |              |
          +------+-------+
                 |
                 v
         MimeMessage content
            - HTML part
            - image/png inline part
              Content-ID: <brandLogo>
                 |
                 v
        JavaMailSender.send
                 |
                 v
          Recipient client
            resolves cid
                 |
                 v
          Image can render
~~~

### Right Approach with HTTPS URL

~~~text
Authorized public image asset
                 |
                 v
          HTTPS CDN endpoint
                 |
                 v
 HTML <img src="https://cdn.example.com/logo.png">
                 |
                 v
          JavaMailSender.send
                 |
                 v
 Mail client may request image via HTTPS
       (can be blocked/cached)
~~~

## 28. Conclusion

**Referencing images by local file paths** happens when an application embeds a path from **the mail-sending machine** into HTML without supplying image data in a way mail clients understand. `C:\...`, `/opt/app/...`, `file:///...`, `classpath:...`, or relative paths only have meaning in specific local contexts; they **do not create an image resource accessible to recipients**.

In Spring Framework Mail, the standard fix for logos and small images is using `MimeMessageHelper` in multipart mode, setting HTML `<img src="cid:brandLogo">`, and calling `addInline("brandLogo", resource, "image/png")`. For assets inside a JAR, use `ClassPathResource`; for files on disk, use `FileSystemResource`; for object storage, use a repeatable stream source with pinned versions. If choosing HTTPS images, ensure URLs truly work for mail clients and accept that remote images may be blocked.

In production, never check only that a file “exists” or SMTP “send succeeded”. Distinguish **backend paths**, **HTML references**, **MIME Content-IDs**, **asset lifecycles**, **access permissions**, **mail client compatibility**, and **email size limits**. When those boundaries are clear, emails embed images reliably without depending on the sender's filesystem, leaking internal paths, or breaking across JARs, Docker, Kubernetes, or async workers.
