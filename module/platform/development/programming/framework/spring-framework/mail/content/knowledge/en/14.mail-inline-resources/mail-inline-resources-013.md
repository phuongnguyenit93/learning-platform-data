# Protecting Resources from Unintended Data in Spring Framework Mail

HTML emails can contain logos, illustrations, icons, or confirmation graphics embedded directly into the message. In Spring Framework Mail, these resources are typically added using the **MimeMessageHelper.addInline(...)** method and referenced by HTML via Content-ID, such as **src="cid:brand-logo@example.com"**. This allows recipients to view images without downloading a separate image URL from an external server.

However, an inline resource is still data placed inside the email MIME. If an application takes images, paths, URLs, or filenames directly from requests and embeds them without controls, emails can carry spoofed content, malicious files, oversized resources, or references to internal systems. Fetching user-specified URLs can also introduce SSRF vulnerabilities. HTML emails can also cause recipients' mail clients to fetch images from external tracking servers, exposing open times or IP addresses.

Therefore, protecting inline resources must cover **data source, format, size, Content-ID, HTML generation, stream opening, and send timing**. Spring Mail handles packaging the resource; trust policies and data validation must be enforced by the application before calling the helper.

## 1. What is an inline resource?

An inline resource is a piece of data embedded inside a MIME message and referenced by another content part. The most common case is an image referenced by HTML via a URI with the **cid:** scheme.

HTML example:

~~~html
<html>
  <body>
    <h1>Your order is ready</h1>
    <img src="cid:brand-logo@example.com"
         alt="Shop Example"
         width="140">
  </body>
</html>
~~~

Adding the image part to the message:

~~~java
helper.addInline(
        "brand-logo@example.com",
        new ClassPathResource("mail/images/brand-logo.png"),
        "image/png");
~~~

The Content-ID value in MIME matches the string inside the cid URI. In the addInline call, pass the bare ID; only the HTML uses the cid: prefix. Do not pass the cid: string into the Content-ID argument and do not manually wrap the header in angle brackets.

A MIME message may be organized as follows:

~~~text
MimeMessage
└── multipart/related
    ├── text/html
    │   └── <img src="cid:brand-logo@example.com">
    └── image/png
        └── Content-ID: <brand-logo@example.com>
~~~

If the email also includes plain text, HTML, and attachments, MIME may nest multipart/alternative and multipart/mixed. The inline resource remains a part in the structure related to HTML; it is neither a public URL nor a regular attachment that the recipient opens separately.

### Distinguishing ways to include images in emails

| Reference method | Where does data reside? | Behavior and primary risks |
| --- | --- | --- |
| CID inline | Inside the MIME message | No need to fetch image from external host; increases email size |
| HTTPS URL | On a web server/CDN | Email client may fetch image when displayed; may expose access info |
| Data URI | Data string embedded in HTML | Uneven support, bloats HTML, and may be stripped by clients |
| File URI or local path | On the sender's machine | Not a valid path for recipients to access; never put in emails |
| Attachment | A standalone MIME part | Recipient downloads/opens file separately, not rendered inline in HTML |

For logos and graphics essential to the message body, CID from controlled resources is usually a good choice. For unnecessary decorative images, omit them to reduce payload size and processing surface.

## 2. How can unintended data enter inline resources?

Several common entry points:

1. A user uploads an image and asks the system to send that image in an email.
2. A request contains an image URL, and the application downloads the URL and embeds it in the message.
3. A request passes a filename or resource path, and the service uses it to build ClassPathResource/FileSystemResource.
4. User-supplied HTML content contains arbitrary img tags, styles, or URLs.
5. A template allows injecting unvalidated variables into src attributes or Content-IDs.
6. A file is read from storage, yet its contents changed after scanning.
7. A thumbnail/image-conversion library processes an oversized file or unsafe format.

Dangerous example:

~~~java
String imageUrl = request.imageUrl();
byte[] bytes = new URL(imageUrl).openStream().readAllBytes();
helper.addInline("image", new ByteArrayResource(bytes), "image/png");
~~~

This snippet trusts a request-supplied URL without restricting protocol, host, redirects, download timeout, byte size, or actual content type. It also assigns a hardcoded content type without verifying the data. If the URL points to an internal address, the application server can be abused to reach services external users are not permitted to call.

Another example:

~~~java
String path = request.resourcePath();
Resource image = resourceLoader.getResource(path);
helper.addInline("image", image, "image/png");
~~~

If path is influenced directly by the request, users may probe unexpected filesystem paths, classpath locations, or URLs. Using the Spring Resource API does not automatically make an untrusted location safe.

### Trust boundaries

| Source | Default trust level | How to handle |
| --- | --- | --- |
| Static logo packaged in the app | Trusted if artifact and build pipeline are controlled | Use fixed resources, verify during build/deploy |
| Approved internal object storage image | Trusted per state and access permissions | Read exact object version, verify metadata and hash |
| User-uploaded image | Untrusted | Enforce limits, detect format, validate structure, and scan for malware |
| User-entered URL | Untrusted | Do not fetch directly; if fetching is mandatory, use a fetcher/proxy with allowlist and network controls |
| User-supplied HTML | Untrusted | Avoid rendering directly; if required by business, sanitize using a dedicated allowlist |
| Filename or resource path from request | Untrusted | Map through an allowlisted ID/key; never use as an arbitrary path |

**A resource is considered approved only when the application knows where it came from, which content was verified, and which exact version will be sent.**

## 3. Prefer static classpath resources for brand assets

Shared logos, icons, or illustrations rarely need to come from requests. Place them in the application's resource directory:

~~~text
src/main/resources/
└── mail/
    └── images/
        ├── brand-logo.png
        └── order-ready-banner.png
~~~

Load resources with ClassPathResource:

~~~java
Resource logo = new ClassPathResource(
        "mail/images/brand-logo.png");
~~~

Benefits:

- Path is controlled by the application.
- Content is packaged with the application release.
- No external URL fetch needed while sending email.
- Easy to review changes in the repository and inspect artifacts.
- Independent of the process working directory.

Never construct paths from user input and concatenate them onto a classpath prefix. If there are multiple logos by brand or tenant, use a validated key and map it to specific resources:

~~~java
enum Brand {
    SHOP_A,
    SHOP_B
}

private static final Map<Brand, String> LOGO_RESOURCES = Map.of(
        Brand.SHOP_A, "mail/images/shop-a.png",
        Brand.SHOP_B, "mail/images/shop-b.png");

Resource logoFor(Brand brand) {
    String path = LOGO_RESOURCES.get(brand);
    if (path == null) {
        throw new IllegalArgumentException("Unsupported brand");
    }
    return new ClassPathResource(path);
}
~~~

The Brand value must come from an authenticated, authorized tenant/account. Never accept raw strings such as ../../application.yml or file:/etc/... as resource locations.

### Classpath resources are not necessarily Files

When the application runs from an executable JAR, images may reside inside an archive rather than as standalone files. Therefore, do not rely on Resource.getFile() to read images. Spring resources can open streams:

~~~java
try (InputStream input = logo.getInputStream()) {
    // Read or pass data to the processing component.
}
~~~

With MimeMessageHelper, pass a suitable Resource/InputStreamSource so the helper can read data when building MIME. Never open a stream once, exhaust it, and pass that same closed stream to addInline.

## 4. Do not fetch arbitrary URLs to create inline resources

When HTML directly references an HTTPS URL, the recipient's email client usually fetches the image. When the application fetches a URL itself and embeds the image into MIME, **the application server acts as an HTTP client**. The two scenarios carry different risks.

### 4.1. Application fetching user-supplied URLs

This is a form of SSRF (Server-Side Request Forgery). Attackers may try to make the application access:

~~~text
http://127.0.0.1/
http://localhost:8080/actuator
http://169.254.169.254/
http://10.0.0.5/internal-service
file:///etc/passwd
~~~

These addresses are merely examples of destinations that must be forbidden. Real environments may have internal addresses, cloud metadata services, admin interfaces, or endpoints reachable only from the backend network.

Never use URLConnection, URL.openStream, or default HTTP clients on untrusted URLs and attach the result. Merely checking that a string starts with https:// is insufficient: redirects can point to another host, DNS can resolve to internal IPs, or public hosts can change DNS records.

### 4.2. Email clients fetching remote image URLs

If HTML contains:

~~~html
<img src="https://images.example.com/banner.png" alt="Banner">
~~~

then the email client may fetch the image from that host when the recipient opens the email or allows images. This can:

- Reveal to the external host when the recipient opened the email.
- Expose IP or connection details depending on the email client's proxy/cache behavior.
- Enable tracking pixels or behavioral tracking.
- Allow image content to change after sending.
- Fail to display if the client blocks remote images or the host goes down.

Some clients use image proxies/caches, so what data reaches the host varies. Still, remote images introduce an external dependency outside the email and can have privacy consequences.

### 4.3. Choosing the right approach

| Purpose | Recommended choice |
| --- | --- |
| Stable brand logo | CID from classpath or approved storage |
| Transaction-specific product photo | Fetch from internal storage by authorized ID, verify content, then embed via CID if needed |
| User-uploaded image | Quarantine, validate file type, scan for malware, and approve before embedding |
| Non-essential decorative image | Can omit the image |
| Image existing only at an external URL | Prefer avoiding arbitrary fetches; if business requires it, use a dedicated fetcher with allowlist and network controls |

Do not automatically download every URL in HTML to convert them to CIDs. Doing so can turn template rendering into an arbitrary URL-fetching service.

## 5. If fetching images from external sources is mandatory

Some business flows have valid reasons to fetch images from known providers or CDNs. In that case, never allow unrestricted URLs. Build an adapter/fetcher that accepts only **approved hosts, schemes, and paths**.

Minimum controls:

1. Allow only HTTPS and designated ports.
2. Allowlist exact hostnames; never rely on simple string suffix checks to validate hosts.
3. Disable automatic redirects or re-validate every redirect, including scheme, host, and target IP.
4. Resolve DNS and reject loopback, private, link-local, multicast, reserved, and metadata endpoint addresses.
5. Enforce network egress policies so the fetcher service cannot reach unnecessary internal networks.
6. Enforce connect timeouts, read timeouts, and total fetch duration limits.
7. Cap bytes while streaming; never load unbounded payloads onto the heap.
8. Check Content-Length if present while still counting actual bytes read.
9. Detect media type from content bytes rather than trusting response Content-Type alone.
10. Never forward user Authorization headers or cookies to external hosts.
11. Scan/validate content before embedding.
12. Store results by object ID/hash, not by arbitrary URLs.

**Single-pass DNS validation is insufficient if the HTTP client resolves DNS again afterward.** A secure design controls the actual IP address connected to or enforces network policy at the egress layer. Isolating fetching into a dedicated service is often a cleaner fit.

### Pseudocode for a constrained fetcher

~~~text
fetchApprovedImage(imageKey):
    config = allowlist.lookup(imageKey)
    if config is absent:
        reject

    resolve destination under controlled DNS policy
    reject private, loopback, link-local and reserved addresses
    connect to approved HTTPS host
    disable automatic redirects
    enforce connect/read/total timeout

    stream bytes with a hard maximum
    detect actual media type
    require media type in image allowlist
    validate dimensions and structure
    scan content according to policy

    return immutable approved resource
~~~

This is an architectural sketch, not a complete HTTP client. DNS/IP checks, redirect handling, and connection controls must be implemented according to your HTTP library and network environment.

### Do not allow arbitrary schemes

Do not accept schemes like file:, ftp:, jar:, data:, or internal protocols simply because an API can open them. For a remote image resource, normally only HTTPS to specific hosts is needed. For classpath resources, use ClassPathResource or application-defined locations.

## 6. Validating image format and content

A client-supplied file extension or Content-Type does not prove a file is a valid image. A file named logo.png could contain HTML, an executable, or other data.

An image validation pipeline should include:

- Allowlisting only actually needed formats, typically PNG/JPEG for email images.
- Detecting media type from byte content.
- Matching the file extension against the detected format.
- Validating structure using a proper image parser.
- Limiting file size and pixel dimensions.
- Scanning for malware per system policy.
- Considering decoding and re-encoding to a safe raster format if business logic needs normalization.
- Stripping unnecessary metadata such as EXIF/GPS when privacy requirements apply.

### Why avoid allowing all image formats?

SVG is an XML-based format capable of referencing external resources or containing complex content. SVG support across email clients is also inconsistent. When only a logo or illustration is needed, PNG/JPEG is usually easier to control.

GIFs can contain many frames/animations. If motion is unneeded, reject GIFs or convert them in a bounded pipeline. WebP and newer formats also require evaluating support across target email clients.

### Magic bytes and MIME types

Common signatures:

| Format | Common leading bytes | MIME type |
| --- | --- | --- |
| PNG | 89 50 4E 47 0D 0A 1A 0A | image/png |
| JPEG | FF D8 FF | image/jpeg |
| GIF | 47 49 46 38 | image/gif |
| SVG | XML/SVG text, no single fixed binary signature | image/svg+xml |

Magic bytes are an initial identification signal, not a complete parser and not proof of safe content. Some polyglot files can be interpreted under multiple formats. Use reliable detectors/parsers, restrict allowed formats, and scan for malware when data originates from users.

### Limit pixels, not just bytes

An image with a small file size can still declare huge width/height dimensions, causing decoding to consume massive memory. When processing images, limit:

- Upload size in bytes.
- Maximum width and height.
- Total pixel count.
- Frame count if the format supports animation.
- Decode/conversion time.
- Size after re-encoding.

Never call ImageIO.read on unbounded data inside a request thread. Use a worker/processor with timeouts, quotas, and appropriate memory limits.

## 7. Never let user input control resource paths

Some applications select images by name:

~~~java
String path = request.getParameter("logo");
Resource resource = new ClassPathResource("mail/images/" + path);
~~~

Without restricting the logo value, requests can attempt path traversal, internal resource names, or unintended files. A safer approach maps a validated selection code:

~~~java
enum LogoVariant {
    DEFAULT,
    PREMIUM
}

private static final Map<LogoVariant, String> LOGOS = Map.of(
        LogoVariant.DEFAULT, "mail/images/brand-default.png",
        LogoVariant.PREMIUM, "mail/images/brand-premium.png");

Resource loadLogo(LogoVariant variant) {
    String path = LOGOS.get(variant);
    if (path == null) {
        throw new IllegalArgumentException("Unsupported logo variant");
    }
    return new ClassPathResource(path);
}
~~~

If the logo variant comes from a tenant, retrieve it from an authenticated, authorized tenant record. Never trust a user-submitted string merely because it looks like a valid filename.

### Resources from storage

For user-uploaded images, the API should accept an attachment ID or asset ID. The service checks:

1. Does the asset belong to the current user/tenant?
2. Is the asset approved and not revoked?
3. Does the scan result match the exact object version/hash?
4. Are content type and size within the allowlist?
5. Is the email recipient authorized to receive that content?

Only then open the approved object. Never accept raw bucket names, object keys, or filesystem paths directly from requests.

## 8. Protecting HTML templates and the src attribute

Even when an image resource is safe, how a template references it can still be manipulated. In particular, never concatenate untrusted strings into HTML attributes.

Unsafe example:

~~~java
String html = "<img src=\\"" + request.imageUrl() + "\\">";
~~~

The data could contain quotes, markup, or unexpected URL schemes. Where the template engine supports it, use escaped template expressions and supply an application-generated CID:

~~~html
<img src="cid:brand-logo@example.com"
     alt="Shop Example"
     width="140">
~~~

Here the CID must be generated by the application from a valid value, never taken from the request. When using Thymeleaf, avoid th:utext for inserting untrusted HTML. With other template engines, enable auto-escaping and use context-appropriate escaping APIs.

### HTML escaping does not replace URI validation

Escaping a string for an HTML attribute only stops characters from breaking markup structure. It does not turn a dangerous URL into a valid URL. For href or src attributes, enforce scheme, host, and resource policies separately.

For inline image src attributes, allow only CIDs generated from the approved resource list. Never let requests inject file:, javascript:, data:, http://127.0.0.1, or arbitrary URLs.

### What if users are allowed to author HTML?

If a product lets users compose HTML emails, escaping everything is impossible because formatting is required. In that case, use an HTML sanitizer with an element/attribute allowlist that strips scripts, event handlers, forms, iframes, objects, embeds, and disallowed URL schemes. Rules must cover src, href, CSS url(...), and other resource references.

Never write your own sanitizer with regex. Use a maintained library configured with a minimal email policy, and still render/preview in an isolated environment.

## 9. Content-ID: safe generation and usage

Content-ID is the MIME identifier for a body part. HTML uses URI form:

~~~html
<img src="cid:brand-logo@example.com" alt="Brand">
~~~

In Spring:

~~~java
helper.addInline(
        "brand-logo@example.com",
        logoResource,
        "image/png");
~~~

Rules to follow:

- Content-ID must be generated by the application, never taken verbatim from users.
- Use short, character-safe strings following a consistent convention.
- Each Content-ID must be unique within a single MIME message.
- Every CID referenced in HTML must have exactly one matching inline part.
- Never use CID to embed filesystem paths or URLs.
- Never manually assemble raw MIME headers; let MimeMessageHelper format headers properly.
- Never include CR/LF in Content-IDs.

### Fixed or random CIDs?

For static logos, a fixed CID like brand-logo@example.com per message is often sufficient because identifier scope is each MIME message. If one message contains multiple dynamic images or multiple resources of the same type, generate a separate ID for each part.

Example:

~~~java
String contentId = "asset-" + UUID.randomUUID()
        + "@mail.example.com";
String imageReference = "cid:" + contentId;
~~~

HTML must use the exact generated value. Never reuse the same CID for two different images in the same message, as email clients may resolve the wrong part.

### Never use CID as a secret or access control

Content-ID is a MIME identifier, not a security token. Recipients can view email source and read the CID. Never embed credentials, session IDs, or access tokens in CIDs.

## 10. Filenames and MIME headers

Inline resources usually do not need a display filename like attachments, yet if filename metadata is provided or a resource is added as an attachment, the name must still be normalized. User-submitted filenames may contain:

~~~text
../../secret.png
..\..\Windows\system.ini
image.png CRLF Bcc: victim@example.com
~~~

Never use raw filename strings as paths or manually concatenate Content-Disposition headers. Use Spring/Jakarta Mail APIs with normalized display names. Strip path separators and control characters, and cap length per policy.

For inline images, prefer fixed resources or approved object IDs; filenames do not need to participate in Content-IDs. Never use filenames as CIDs.

## 11. Size, count, and MIME resource budgets

Every inline image increases email size. Base64 encoding typically inflates binary data by roughly one-third, excluding MIME headers and boundaries. A template may hold a logo, banner, icons, and multiple product photos; total size can quickly exceed SMTP provider or mailbox limits.

Set limits:

| Limit | Purpose |
| --- | --- |
| Single image size | Aligned with actual template needs |
| Total inline resource bytes | Bounded per email |
| Number of inline parts | Only for genuinely needed images |
| Pixel dimensions | Cap width, height, and total pixels |
| Total MIME message size | Leave headroom for Base64 and body |
| Processing time | Cap decode, resize, scan, and MIME construction |

Do not pick arbitrary numbers and apply them blindly to every system. Choose thresholds based on provider limits, email type, recipient devices, and operational load. Check size after image processing, as converted images may be larger or smaller than originals.

### Do not use tracking pixels

A remotely hosted 1x1 image can be used to record email opens. This is a form of behavioral tracking and can have privacy implications or consent requirements. Never add tracking pixels by default simply because marketing template examples include them. If a product has email analytics, ensure legal/policy basis, clear disclosure, and appropriate recipient choices.

CID images embedded in the email do not make an HTTP request to a tracking server upon display, yet embedding images still exposes email contents to anyone with access to the message. Never treat CID as protection for sensitive data.

## 12. Scanning and approving user-uploaded images

If images are uploaded by users and later embedded inline, apply a pipeline similar to attachments:

~~~text
Upload
  |
  v
Size + filename validation
  |
  v
Quarantine storage
  |
  v
Detected image type + structural validation
  |
  v
Malware scan / safe image processing
  |
  v
Approved immutable object + hash
  |
  v
Mail service reads exact approved version
  |
  v
MimeMessageHelper.addInline(...)
~~~

Never send images in PENDING, SCANNING, ERROR, or UNKNOWN states. An unavailable scanner does not mean a file is clean. Use only content approved for the exact hash/object version.

### Re-encoding images

Some systems decode images and re-encode them to PNG/JPEG to strip metadata or normalize content. This can reduce certain risks and standardize formats, though it is not an absolute security guarantee:

- Parsers/decoders themselves can have vulnerabilities.
- Input images must still be size-bounded before decoding.
- Converted output is new byte content that must be validated and scanned per policy.
- Output dimensions and MIME format must stay accurate.
- If GPS metadata is unneeded, verify the pipeline actually strips it.

Never edit image file bytes manually using string operations or regex.

## 13. Reading resources safely and InputStreamSource lifecycle

Spring Mail provides overloads accepting InputStreamSource:

~~~java
helper.addInline(
        contentId,
        inputStreamSource,
        contentType);
~~~

InputStreamSource must supply an openable stream whenever the framework needs to read content. Never pass an already-exhausted or closed InputStream into a resource source that may be invoked again.

Example with a classpath resource:

~~~java
Resource logo = new ClassPathResource(
        "mail/images/brand-logo.png");

helper.addInline(
        "brand-logo@example.com",
        logo,
        "image/png");
~~~

Example with an approved byte array:

~~~java
ByteArrayResource logo = new ByteArrayResource(approvedImageBytes);

helper.addInline(
        "customer-logo@example.com",
        logo,
        "image/png");
~~~

With object storage, create an InputStreamSource that opens a fresh stream for the exact object version:

~~~java
InputStreamSource source = () ->
        approvedStorage.openStream(
                approvedAsset.objectKey(),
                approvedAsset.version());

helper.addInline(
        contentId,
        source,
        approvedAsset.contentType());
~~~

This snippet assumes approvedStorage is an internal API. Never open files by paths or keys taken straight from requests. Storage must guarantee object versions remain immutable after scanning.

### Do not close streams too early

Do not write:

~~~java
InputStream input = logo.getInputStream();
try (input) {
    helper.addInline("logo@example.com",
            new InputStreamResource(input),
            "image/png");
}
// Stream is already closed before the message is serialized.
~~~

In some code paths, the helper/Jakarta Mail reads content only when the message is written or sent. If the stream is closed before that point, MIME creation may fail or produce an empty resource. Use a Resource that can open new streams, ByteArrayResource for small payloads, or an InputStreamSource creating a fresh stream on each call.

### Call setText before addInline

When using MimeMessageHelper for HTML with CIDs, set the body first and then add inline resources:

~~~java
helper.setText(plainText, htmlText);
helper.addInline(
        "brand-logo@example.com",
        logoResource,
        "image/png");
~~~

This order lets the helper construct the related multipart structure compatible with many email clients. Do not manipulate the low-level MIME tree manually when the helper API already meets your needs.

## 14. Example service using controlled inline resources

The example below uses a static logo from the classpath. No request-supplied image URLs are used, and no resource paths are read from clients.

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.springframework.web.util.HtmlUtils;

@Service
public class OrderReadyMailService {

    private static final String LOGO_CID =
            "brand-logo@example.com";

    private final JavaMailSender mailSender;

    public OrderReadyMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            String customerName,
            String orderId) throws MessagingException {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException("Recipient is required");
        }
        if (customerName == null || customerName.isBlank()) {
            customerName = "there";
        }
        if (orderId == null || !orderId.matches("[A-Za-z0-9-]{1,40}")) {
            throw new IllegalArgumentException("Invalid order ID");
        }

        String safeName = HtmlUtils.htmlEscape(customerName);
        String safeOrderId = HtmlUtils.htmlEscape(orderId);

        String plainText = """
                Hello %s,

                Order %s is ready.
                Thank you for your purchase.
                """.formatted(customerName, orderId);

        String htmlText = """
                <!doctype html>
                <html lang="en">
                  <body>
                    <img src="cid:brand-logo@example.com"
                         alt="Shop Example"
                         width="140">
                    <h1>Your order is ready</h1>
                    <p>Hello <strong>%s</strong>,</p>
                    <p>Order ID: <strong>%s</strong></p>
                    <p>Thank you for your purchase.</p>
                  </body>
                </html>
                """.formatted(safeName, safeOrderId);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("notifications@example.com");
        helper.setTo(recipient);
        helper.setSubject("Order " + orderId + " is ready");
        helper.setText(plainText, htmlText);

        ClassPathResource logo = new ClassPathResource(
                "mail/images/brand-logo.png");
        helper.addInline(LOGO_CID, logo, "image/png");

        mailSender.send(message);
    }
}
~~~

This is an illustrative example for a controlled static resource inside the artifact. In a real application, recipient and From addresses must be validated per business rules and SMTP configuration; subjects must guard against control characters; names and dynamic data must enforce length limits. HTML escaping applies only to HTML content and does not replace recipient or subject validation.

A static logo does not need antivirus scanning on every send if the artifact and build pipeline control its source. However, validate resources at build/release time and enforce size limits. For uploaded images or mutable storage images, run an approval pipeline before use.

## 15. Protecting URLs in HTML links

Inline resources often appear alongside links. Although a link is not a CID image, it is still external data that can affect recipients.

Never concatenate arbitrary URLs:

~~~java
String html = "<a href=\\"" + userProvidedUrl + "\\">Open document</a>";
~~~

Instead:

- Build URLs from a trusted configured base URL.
- Encode path segments/query parameters using proper URI APIs.
- Allow only the HTTPS scheme for outbound links.
- Allowlist hosts or domains per business rules.
- Escape HTML attributes after the URL is constructed/validated.
- Avoid putting tokens, passwords, or sensitive data into URLs whenever possible.

In Thymeleaf, use th:href with application-normalized URL values. Do not treat HTML escaping as URL validation.

If a template contains both CIDs and hyperlinks, validate the two URI types separately: CIDs reference only inline parts within the same message; HTTPS leads to web resources. Never use the same arbitrary input field for both.

## 16. Observability and logging

When an inline resource is missing or fails to display, logs should help identify:

- Template key and version.
- Generated Content-ID.
- Internal resource key or asset ID.
- Detected media type and size.
- Scan status/hash/version if the resource came from an upload.
- Failure stage: resolve, read, MIME composition, or SMTP.

Never log byte payloads, URLs with tokens, personal document contents, or credentials. For external URLs, limit logging query strings because they may contain identifiers or secrets.

Structured log example:

~~~json
{
  "event": "mail_inline_resource_rejected",
  "notificationId": "order-ready-184",
  "resourceKey": "customer-logo",
  "contentType": "image/png",
  "sizeBytes": 48210,
  "reason": "SCAN_NOT_CLEAN",
  "scanStatus": "UNKNOWN"
}
~~~

This is an illustrative application-defined log schema, not auto-generated Spring output. Never include full email addresses or customer names if a notification ID suffices for lookup in an authorized system.

### Useful metrics

| Metric | Purpose |
| --- | --- |
| Rejected inline resources by reason | Identify invalid data patterns |
| Scan ratio CLEAN/INFECTED/ERROR | Monitor scanner health and upload quality |
| Total inline bytes per email | Detect oversized emails |
| Resource/InputStream open failures | Detect missing files or storage errors |
| CIDs missing a matching part | Detect template and MIME mismatches |
| Fetch/scan/transform duration | Detect slow dependencies or resource-heavy processing |

## 17. Testing resources before sending

No real SMTP server is needed to test most resource rules. You can verify:

1. Resource keys are chosen from an allowlist.
2. Classpath resources exist and are readable.
3. Detected media types match policy.
4. Byte size and pixel dimensions stay within limits.
5. Scanner returns CLEAN for the exact hash/object version.
6. CIDs are generated and appear only once per inline part in the message.
7. HTML contains the matching cid src.
8. Streams are opened at the right time and not reused after closing.
9. No disallowed external URLs exist in templates.
10. The MIME tree contains the inline part with the expected Content-ID and Content-Type.

### Testing classpath resources

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

class MailInlineResourceTest {

    @Test
    void brandLogoIsPackaged() {
        ClassPathResource logo = new ClassPathResource(
                "mail/images/brand-logo.png");

        assertTrue(logo.exists());
        assertTrue(logo.isReadable());
    }
}
~~~

This test confirms the resource is on the test classpath. If the build artifact uses custom resource filtering or packaging rules, inspect the built executable JAR to ensure the file actually ships inside the artifact.

### Testing allowlist decisions

~~~java
@Test
void rejectsUnsupportedMediaType() {
    assertThrows(
            IllegalArgumentException.class,
            () -> attachmentPolicy.requireAllowed(
                    "image.svg",
                    "image/svg+xml"));
}
~~~

This is an example testing an application-defined policy. It does not test real antivirus detection capability.

### Testing fail-closed scanning

~~~java
when(malwareScanner.scan(any(InputStream.class)))
        .thenReturn(new ScanResult(ScanStatus.ERROR, "test", "v1", null));

assertThrows(
        IllegalStateException.class,
        () -> attachmentService.approve(upload));

verifyNoInteractions(mailSender);
~~~

This test illustrates that scanner ERROR is never treated as CLEAN and the mail sender is never called. Adapt exception types, services, and mocks to your project's actual code.

### Testing MIME messages

You can build a MimeMessage in memory, call setText and addInline, and traverse MIME parts to verify:

- A text/html part exists.
- An inline image part exists.
- Content-ID matches the CID in HTML.
- Content-Type is an approved type.
- Part contents match the verified resource.

When real rendering checks are needed, send to an SMTP capture/test server and inspect raw MIME in a controlled environment. Successful SMTP submission does not prove every email client will load or render all images identically.

## 18. Common mistakes

### 18.1. Embedding user-submitted URLs straight into HTML

The URL can point to a malicious host, internal endpoint, or tracking server. Never let requests control src arbitrarily. Use CIDs from approved resources or a host allowlist with clear policies.

### 18.2. Fetching URLs with URL.openStream()

This API does not enforce SSRF, redirect, timeout, or byte-size policies on its own. Never use it with untrusted URLs. If fetching is required, use a service with egress controls, allowlists, and strict limits.

### 18.3. Trusting client-declared Content-Type

Clients can send image/png for non-image payloads. Detect format from byte content, verify structure, and scan for malware per policy.

### 18.4. Trusting .png or .jpg extensions

Filenames do not prove contents. Cross-check extensions against detected media types and allowlists.

### 18.5. Using arbitrary SVGs as inline logos

SVG has an XML structure capable of complex resource references; support across email clients is uneven. When unnecessary, use validated PNG/JPEG instead.

### 18.6. Passing request resource paths into ResourceLoader

This can enable path traversal or access to unintended files/URLs. Use allowlisted resource keys rather than accepting arbitrary locations.

### 18.7. Reusing a closed InputStream

MimeMessage may read the resource during serialization/sending. Use a Resource or InputStreamSource that opens fresh streams; never pass a consumed stream.

### 18.8. Calling addInline before setText

With MimeMessageHelper, set the body first and then add inline resources in the recommended order so the helper constructs the proper MIME structure.

### 18.9. Using client-supplied Content-IDs

CIDs are part of MIME headers. Generate CIDs on the application side, restrict characters, and ensure uniqueness within the message.

### 18.10. Assuming CID is a security mechanism

A CID is just a MIME part identifier; it does not encrypt content or enforce read permissions. Recipients can inspect email source.

### 18.11. Failing to bound image dimensions

Large images bloat emails after Base64 encoding, increase processing time, and risk exceeding provider limits. Cap bytes, pixels, count, and total size.

### 18.12. Treating scanner timeouts as CLEAN

Timeouts, unsupported files, or encrypted archives must resolve as ERROR/UNKNOWN. Never send resources that have not been verified clean.

### 18.13. Stripping metadata without re-checking the output

After resizing/re-encoding, the content has changed. Validate and re-scan the final version before embedding.

### 18.14. Using remote tracking pixels without a policy

Remote images can track email opens. Never add tracking pixels by default; follow privacy policies and recipient choices.

## 19. Safe inline resource processing workflow

A practical workflow can be structured as follows:

1. Identify the resource by an application-permitted template key or asset ID.
2. Verify user/tenant authorization for the asset.
3. Open the resource from the classpath or controlled internal storage.
4. Validate size, actual format, and structure.
5. If data came from users, scan for malware and hold in quarantine until cleared.
6. If images are transformed, re-validate the output and record the new hash.
7. Generate an application-controlled Content-ID unique within the message.
8. Render HTML with a trusted template; escape dynamic data for the right context.
9. Set the body via setText before calling addInline.
10. Attach the resource with the approved byte content, MIME type, and Content-ID.
11. Check total message size and send with JavaMailSender.
12. Log status safely and clean up temporary data per retention policy.

### Quick decisions by source

| Resource source | Ready for immediate use? | Conditions |
| --- | --- | --- |
| Reviewed classpath logo | Yes, per policy | Resource is inside artifact; format/size controlled |
| Internal object storage | Not by default | Authorization, immutable version, type/size, and scan state |
| User upload | No | Quarantine, detection, validation, malware scan, and approval |
| Request-supplied URL | No | Only via dedicated fetcher with allowlist and network controls if strictly needed |
| HTML with arbitrary src | No | Sanitize/allowlist; better to generate CIDs from approved resources |

## 20. Self-check questions

**1. How are inline resources in Spring Mail typically referenced by HTML?**

Using a URI with the cid: scheme matching the Content-ID of the MIME part added via MimeMessageHelper.addInline(...).

**2. Can a resource path sent by a request be passed directly to ResourceLoader?**

No. The location could point to unintended files or URLs. Use an allowlisted key and map it to an application-controlled resource.

**3. Is a CID a security token?**

No. It is simply the identifier of a MIME part inside the email and can be read from the source by recipients.

**4. Why avoid downloading arbitrary image URLs to embed in emails?**

Because the application could suffer SSRF or download oversized or malicious payloads. If the email client fetches a remote URL itself, that host may also receive access data and track open times.

**5. Do magic bytes prove an image is safe?**

No. They provide preliminary format identification; parser validation, resource limits, and malware scanning are still needed for untrusted sources.

**6. Why prefer PNG/JPEG over arbitrary SVG?**

PNG/JPEG are generally easier to control for logos and raster graphics; SVG has an XML structure, complex references, and inconsistent email client support.

**7. If the scanner is unavailable, can the image be sent?**

No, if policy requires scanning. Keep the file in pending/error state or reject it; never treat timeouts as CLEAN.

**8. Why bind scan results to a hash/version?**

To guarantee the transmitted bytes are the exact bytes that were inspected. If the file changes, it must be re-scanned.

**9. Should an already-read InputStream be reused when calling addInline?**

No. The stream may already be at EOF or closed. Use a Resource/ByteArrayResource or an InputStreamSource that opens a fresh stream.

**10. Should setText or addInline be called first?**

With MimeMessageHelper, set the content with setText first and then add inline resources.

**11. Why bound image pixel dimensions in addition to byte size?**

A small file can still declare huge width/height dimensions, causing decoding to consume excessive memory or CPU.

**12. Does CID inline prevent all privacy issues?**

No. It avoids remote image-fetch requests upon display, but the email content can still be read, forwarded, or archived; sensitive data still needs protection.

## Conclusion

**Protecting inline resources begins with controlling sources and contents before placing them into a MIME message.** For static resources, prefer ClassPathResource with fixed paths in the artifact. For user-supplied images, enforce format allowlists, content detection, byte/pixel limits, structural checks, malware scanning, quarantine, and approval bound to hash/object version. Never fetch arbitrary URLs or resource paths; URL fetching can introduce SSRF, while remote images in HTML can expose recipient access details. Generate Content-IDs in the application, escape dynamic HTML, use Resource/InputStreamSource capable of opening streams on time, and call setText before addInline. **MimeMessageHelper only packages the resource; the application must guarantee the embedded data comes from the right source, has valid content, and is authorized to be sent.**
