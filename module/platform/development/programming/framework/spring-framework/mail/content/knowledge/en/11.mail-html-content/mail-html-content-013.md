# Measuring HTML and image sizes before sending in Spring Framework Mail

An HTML email can contain markup, CSS, inline images, links, a plain-text fallback, and attachments. Looking only at the template's character count does not tell the application how heavy the email will be after packaging into MIME and transmitting over SMTP.

Measuring sizes before sending helps catch messages that exceed provider limits early, avoid building overly large messages, reduce transmission time, and control worker memory. In Spring Framework Mail, perform this step after rendering content and building all MIME parts, but before calling JavaMailSender.send(...).

Distinguish the measurements:

- **HTML size**: number of bytes of the HTML string after encoding, usually UTF-8.
- **Image size**: number of bytes of the PNG/JPEG/GIF file or embedded resource.
- **Image pixel dimensions**: width and height; not synonymous with file size.
- **MIME size**: includes headers, body, boundaries, transfer encoding, inline images, and attachments.
- **Size on the SMTP wire**: may differ from serialized MIME due to framing, line endings, dot-stuffing, and how the provider counts limits.

No single measurement answers every question. A good preflight pipeline measures each component, then measures the entire MIME message against the sending budget.

## 1. Why measure before sending?

Suppose the application creates an order confirmation email consisting of about 80 KB of HTML, a 120 KB inline PNG logo, a 900 KB JPEG product photo, a 2 MB attached PDF, and about 2 KB of plain text. Measuring only HTML might make the application think the email is very small. Yet the inline image and PDF are packaged into MIME; binary data can also be Base64-encoded, increasing transfer size.

Measuring beforehand helps:

1. Reject or replace over-limit content before opening an SMTP connection.
2. Resize/compress images before attaching.
3. Convert large files into download links with appropriate access control, if business rules permit.
4. Avoid workers holding multiple large buffers simultaneously.
5. Identify which templates produce abnormally large emails.
6. Reduce the risk of provider rejection due to over-limit messages.
7. Build alert thresholds and statistics by email type.

Providers may limit total message size, individual attachments, recipient count, or headers. Therefore, measuring total size is necessary yet does not replace checking component limits.

## 2. Distinguishing characters, bytes, and file size

A common mistake is using String.length() to measure HTML. That method returns the number of UTF-16 code units of the Java string, not the number of bytes the content takes when encoded for transmission. Vietnamese accented characters or emoji can use varying numbers of UTF-8 bytes.

Measuring HTML size in UTF-8:

~~~java
import java.nio.charset.StandardCharsets;

String html = "<p>Xin chào khách hàng!</p>";

int characterUnits = html.length();
int utf8Bytes = html.getBytes(StandardCharsets.UTF_8).length;

System.out.println("UTF-16 code units: " + characterUnits);
System.out.println("UTF-8 bytes: " + utf8Bytes);
~~~

When Spring Mail uses UTF-8, the UTF-8 byte count is a useful measurement for the HTML part before MIME packaging.

Examples with different strings:

~~~java
String ascii = "Order confirmed";
String vietnamese = "Đơn hàng đã xác nhận";
String emoji = "Đã giao hàng 📦";

System.out.println(ascii.length());
System.out.println(ascii.getBytes(StandardCharsets.UTF_8).length);

System.out.println(vietnamese.length());
System.out.println(vietnamese.getBytes(StandardCharsets.UTF_8).length);

System.out.println(emoji.length());
System.out.println(emoji.getBytes(StandardCharsets.UTF_8).length);
~~~

The principle is always the same: **measure bytes in the charset used**, do not compare character count against a provider's byte-based limit.

If HTML is very large, getBytes(UTF_8) creates an additional byte array in memory. For ordinary email templates, this is simple and clear. For extremely large content, encoders/streaming can be used to limit allocation, though you still have to account for the final message needing to be constructed and sent.

### MB and MiB

When displaying or configuring limits, state the unit clearly:

| Unit | Byte count |
| --- | ---: |
| 1 KB (decimal) | 1.000 |
| 1 MB (decimal) | 1.000.000 |
| 1 KiB | 1.024 |
| 1 MiB | 1.048.576 |

A provider stating a 25 MB limit may use decimal calculation per its documentation. The application should keep numbers internally as bytes (long) and only format as MB/MiB when displaying. Do not take a threshold of “25” without knowing whether it represents MB or MiB.

## 3. Measuring HTML after template rendering

HTML must be measured **after rendering all dynamic data**. The source template is only a skeleton; user names, order tables, URLs, notification content, and conditional sections can change final size substantially.

~~~java
import java.nio.charset.StandardCharsets;

public final class HtmlSize {
    private HtmlSize() {}

    public static long utf8Bytes(String html) {
        if (html == null) {
            throw new IllegalArgumentException("HTML must not be null");
        }
        return html.getBytes(StandardCharsets.UTF_8).length;
    }
}
~~~

Usage with a template engine:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("customerName", customerName);
context.setVariable("orderCode", orderCode);
context.setVariable("items", items);

String html = templateEngine.process("mail/order-confirmed", context);
long htmlBytes = HtmlSize.utf8Bytes(html);
~~~

This measurement covers the rendered HTML tags, inline CSS, escaped text, URLs, and hidden elements if the template still generates them. It **does not include** bytes of images loaded from HTTPS URLs, external CSS, or external fonts that the email client loads after receiving the message. It also does not yet include MIME headers, boundaries, and transfer encoding.

### Measuring both plain text and HTML

If sending multipart/alternative, record the size of each version:

~~~java
long plainBytes =
    plainText.getBytes(StandardCharsets.UTF_8).length;

long htmlBytes =
    htmlText.getBytes(StandardCharsets.UTF_8).length;

long bodySourceBytes = plainBytes + htmlBytes;
~~~

bodySourceBytes is only the sum of bytes of the two source strings. When packaged, MIME adds headers for each part, boundaries, and possibly transfer encoding. Do not use this sum in place of the final MIME size.

### Dedicated HTML limit

The application can set a threshold to block abnormal templates:

~~~java
long maxHtmlBytes = 300_000L; // Example: 300 KB decimal.

if (htmlBytes > maxHtmlBytes) {
    throw new IllegalArgumentException(
        "Rendered HTML exceeds the configured size limit");
}
~~~

The 300 KB threshold is only an internal example, not a universal email limit. Some email clients may clip HTML content at their own thresholds, yet clipping thresholds vary by client and calculation method. Set budgets based on the target client set and real testing.

## 4. Measuring image file size

For image files on the filesystem, Files.size(...) returns the file size in bytes:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

Path imagePath = Path.of("src/main/resources/mail/banner.jpg");
long imageBytes = Files.size(imagePath);

System.out.println("Image bytes: " + imageBytes);
~~~

If the file is on the classpath without a direct filesystem path, you can read the stream to count bytes:

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;

public final class ResourceSize {
    private ResourceSize() {}

    public static long countBytes(Resource resource) throws IOException {
        long total = 0L;
        byte[] buffer = new byte[8192];

        try (InputStream input = resource.getInputStream()) {
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
            }
        }

        return total;
    }
}
~~~

Example:

~~~java
Resource logo = new ClassPathResource("mail/logo.png");
long logoBytes = ResourceSize.countBytes(logo);
~~~

The stream-counting approach avoids holding the entire file in one byte array. However, when sending afterward, the application must be able to reopen the resource. ClassPathResource or FileSystemResource can usually create a new stream; an already-consumed stream or a one-shot resource is unsuitable for a workflow that both measures and sends.

### Why not use contentLength() for every Resource?

Resource.contentLength() is useful if the resource knows its size. Yet for some stream-based resources, remote sources, or dynamic data, the size might not be available or computing it may require reading the entire stream. When an exact number is needed, use Files.size for files or read the stream in a controlled way.

Do not call getContentAsByteArray() just to measure a large file if the application does not need to hold all content in memory. Doing so creates a byte array matching the entire file and can increase memory pressure when many emails are processed concurrently.

## 5. Image byte size differs from pixel dimensions

An image has two characteristics to pay attention to:

- **File size (bytes)**: number of bytes of the compressed/encoded file, affecting MIME size and transmission time.
- **Pixel dimensions (width × height)**: number of pixels to display/decode, affecting sharpness, scaling, and rendering memory.

| Image | File size | Pixel dimensions | Meaning |
| --- | ---: | ---: | --- |
| PNG logo | 90 KB | 600 × 200 | Small file yet sufficient resolution for the display area |
| JPEG product photo | 180 KB | 1200 × 1200 | Can be displayed at 300 × 300 |
| PNG banner | 1.8 MB | 2400 × 800 | May be too large for the display area |
| Animated GIF | 2.5 MB | 800 × 450 | Need to consider frame count and total file size |

A 2400 × 800 image has 1,920,000 pixels. If decoded to a 4-byte/pixel RGBA bitmap, the raw pixel buffer may require around 7.68 MB, not counting overhead and intermediate copies. Compressed JPEG file size might be only a few hundred KB while decoded memory is much larger.

Therefore, image preflight should check **both byte length and dimensions**, especially when images come from user uploads or batch processing systems.

### Reading width and height with ImageIO

For formats supported by ImageIO such as PNG, JPEG, and GIF, you can use ImageReader to read dimension metadata without decoding the entire image into a BufferedImage:

~~~java
import java.awt.Dimension;
import java.io.IOException;
import java.nio.file.Path;
import java.util.Iterator;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;

public final class ImageDimensions {
    private ImageDimensions() {}

    public static Dimension read(Path path) throws IOException {
        try (ImageInputStream input =
                 ImageIO.createImageInputStream(path.toFile())) {

            if (input == null) {
                throw new IOException("Cannot open image input");
            }

            Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw new IOException("Unsupported image format");
            }

            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                return new Dimension(width, height);
            } finally {
                reader.dispose();
            }
        }
    }
}
~~~

Then check the limits:

~~~java
Dimension dimensions = ImageDimensions.read(imagePath);
long pixels = (long) dimensions.width * dimensions.height;

if (dimensions.width > 2400
        || dimensions.height > 2400
        || pixels > 4_000_000L) {
    throw new IllegalArgumentException(
        "Image dimensions exceed the configured limit");
}
~~~

The numbers 2400 pixels and 4 million pixels are only budget examples. The application should choose based on email design, display dimensions, and processing resources.

ImageReader.getWidth(0) and getHeight(0) usually describe the first frame of a multi-frame image. For animated GIFs, you must also consider frame count, animation duration, and total file size; do not inspect only the first frame and assume the entire GIF is lightweight.

For formats without a built-in reader in the JDK, a supporting library or conversion in the upload pipeline is needed. Do not assume ImageIO can always read every format a browser can display.

## 6. Distinguishing remote images, inline images, and attachments

Not every image appearing in HTML counts the same way toward email size.

### Images from HTTPS URLs

~~~html
<img src="https://static.example.com/email/logo.png"
     width="120" height="40"
     alt="Example logo">
~~~

The email contains only the URL and referencing markup. The image file's bytes **are not inside the MIME message** if the image is loaded from an external server. The email client downloads the image after receiving the message, if client policy permits.

- HTML size includes the URL length and img tag attributes.
- MIME size does not add all bytes of the remote image file.
- Remote images still affect display time, privacy, caching, and likelihood of being blocked.
- The URL must be reachable from the email client/proxy; do not rely on website login cookies.
- A URL with a long query string still increases HTML size.

If the image is on a CDN, measure and optimize it in the **asset build/upload pipeline**. Do not download an arbitrary user-supplied URL right before sending just to measure it, because that can create SSRF or internal resource access.

### Inline images via Content-ID

An inline image is packaged as a MIME part and HTML references it with cid:

~~~html
<img src="cid:brandLogo" alt="Example logo" width="120">
~~~

In Spring Mail:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
    message,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
);

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Notification");

String plain = "Notification from Example.";
String html = """
    <html><body>
      <img src="cid:brandLogo" width="120" alt="Example logo">
      <h1>Notification</h1>
    </body></html>
    """;

helper.setText(plain, html);
helper.addInline(
    "brandLogo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

mailSender.send(message);
~~~

The logo file is placed into the message as a part with Content-ID. **Inline image bytes increase MIME size**, even though the HTML tag contains only a very short cid string.

### Attachments

Attachments are added via addAttachment:

~~~java
helper.addAttachment(
    "invoice.pdf",
    new FileSystemResource(invoicePath)
);
~~~

Attachments also increase MIME size. Filenames, MIME headers, transfer encoding, and binary data all contribute to the final message.

| Component | Inside HTML? | Inside MIME? | What to measure? |
| --- | --- | --- | --- |
| Remote HTTPS image | URL and img attributes | Does not contain image bytes | HTML bytes and CDN asset bytes |
| Inline CID image | cid string | Has image part | File bytes, dimensions, serialized MIME |
| Image attachment | Not necessarily | Has attachment part | File bytes and serialized MIME |
| Inline CSS | Yes | Inside HTML part | HTML UTF-8 bytes |
| External CSS/image URL | Reference URL | Usually does not contain external bytes | HTML bytes and external asset host |
| Plain-text alternative | Not inside HTML | Separate MIME part | Plain-text bytes and MIME size |

If the goal is to reduce message size, replacing CID images with HTTPS images can make MIME lighter. However, you must consider that external images may be blocked, tracking/privacy, and CDN reliability. Do not change based solely on a single number while ignoring recipient experience.

## 7. Base64 increases image and attachment size

Binary parts in MIME are usually transmitted using Content-Transfer-Encoding: base64. Base64 represents each group of 3 bytes as 4 characters, so base size grows by roughly one third.

Base64 formula before line breaks:

~~~text
encodedLength = 4 × ceil(originalBytes / 3)
~~~

Example 900,000-byte image file:

~~~text
Base64 characters ≈ 4 × ceil(900,000 / 3)
                  = 1,200,000 bytes (ASCII)
~~~

MIME usually wraps Base64 data into length-limited lines (commonly 76 characters), so there are extra CRLF bytes too. In addition there are headers, boundaries, and other MIME parts.

You can estimate Base64:

~~~java
public static long base64EncodedLength(long inputBytes) {
    if (inputBytes < 0) {
        throw new IllegalArgumentException("Negative size");
    }
    return 4L * ((inputBytes + 2L) / 3L);
}
~~~

If you want to also estimate line breaks at 76 characters:

~~~java
public static long base64WithCrlfEstimate(long inputBytes) {
    long encoded = base64EncodedLength(inputBytes);
    long lines = (encoded + 75L) / 76L;

    // Estimate 2 CRLF bytes between lines, excluding trailing CRLF.
    long lineBreaks = Math.max(0L, lines - 1L) * 2L;
    return encoded + lineBreaks;
}
~~~

This is an **estimate for Base64 data**, not the exact MIME size. The library may pick a different transfer encoding per part; headers and boundaries also have overhead. Do not use this function to assert a provider will count a message under an exact limit.

Not every part is Base64:

- Text content may be transmitted as 7bit, quoted-printable, or Base64 depending on charset and library.
- HTML with Vietnamese diacritics may be encoded to ensure proper transmission.
- Unicode Subject headers or display names may be MIME-encoded.
- Binary images/PDFs usually need Base64 or an appropriate encoding.
- MIME boundaries and each part's headers also occupy bytes.

Therefore, measuring individual files helps locate bloat sources, while measuring serialized MIME is closer to the packaged message size.

## 8. Measuring the entire MIME message after building the helper

Once the MimeMessage is created and text, HTML, inline images, and attachments are added, you can serialize the message to an output stream that only counts bytes.

MimeMessage.writeTo(OutputStream) writes headers and MIME parts to the stream. Using an OutputStream that only counts without retaining data measures serialized size without allocating another byte array as large as the entire message.

### CountingOutputStream

~~~java
import java.io.OutputStream;

public final class CountingOutputStream extends OutputStream {
    private long count;

    @Override
    public void write(int value) {
        count++;
    }

    @Override
    public void write(byte[] buffer, int offset, int length) {
        if (length < 0) {
            throw new IndexOutOfBoundsException();
        }
        count += length;
    }

    public long getCount() {
        return count;
    }
}
~~~

This is a stream that discards data after counting; it does not store bytes. Measurement function:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;

public final class MimeSize {
    private MimeSize() {}

    public static long serializedBytes(MimeMessage message)
            throws MessagingException, IOException {
        message.saveChanges();

        CountingOutputStream output = new CountingOutputStream();
        message.writeTo(output);

        return output.getCount();
    }
}
~~~

Calling saveChanges() before serializing finalizes headers and MIME metadata managed by Jakarta Mail. Then writeTo writes the message according to the generated MIME structure.

### Limitations of serialized MIME measurement

This figure is the **serialized message size at the time of measurement**, useful for preflight, yet it does not always equal the exact byte count the provider counts when receiving SMTP DATA:

- SMTP has framing, DATA termination, and dot-stuffing for certain lines starting with a period.
- The transport may add or modify headers during sending.
- Providers may calculate quotas by message size, attachment size, or their own method.
- The server may enforce separate limits for headers, recipients, attachments, or content.
- Some DataSource/Resource implementations can only be read once.
- If the message is modified after measurement, the result no longer represents the final message.

Therefore, comparing against provider limits needs a **safety margin** and must follow the provider's documentation. If the provider has a validation API or contract stating size in advance, use their official mechanism.

### Be careful when measuring messages with stream attachments

writeTo needs to read the content of MIME parts to serialize. If an attachment uses a one-shot source, the measurement operation may consume the stream and leave subsequent sending unable to read it.

Prefer sources that can open a fresh stream each time such as FileSystemResource, ClassPathResource, or a properly implemented InputStreamSource. Avoid holding an already-open InputStream and passing it to both the measurement step and the sending step.

## 9. Preflight example before calling send()

The example below measures HTML, logo, and the MIME message. Thresholds are illustrative configuration and must be replaced per application/provider policy.

~~~java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class CampaignMailer {

    private static final long MAX_HTML_BYTES = 300_000L;
    private static final long MAX_LOGO_BYTES = 500_000L;
    private static final long MAX_MIME_BYTES = 8_000_000L;

    private final JavaMailSender mailSender;

    public CampaignMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient, String html, String plainText)
            throws MessagingException, IOException {

        // 1. Measure string after rendering.
        long htmlBytes =
            html.getBytes(StandardCharsets.UTF_8).length;

        if (htmlBytes > MAX_HTML_BYTES) {
            throw new IllegalArgumentException(
                "HTML content exceeds configured limit");
        }

        // 2. Measure inline file before creating the message.
        ClassPathResource logo =
            new ClassPathResource("mail/logo.png");

        long logoBytes = ResourceSize.countBytes(logo);
        if (logoBytes > MAX_LOGO_BYTES) {
            throw new IllegalArgumentException(
                "Logo exceeds configured limit");
        }

        // 3. Create the message and MIME parts.
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            StandardCharsets.UTF_8.name()
        );

        helper.setFrom("news@example.com");
        helper.setTo(recipient);
        helper.setSubject("New newsletter");
        helper.setText(plainText, html);
        helper.addInline("brandLogo", logo, "image/png");

        // 4. Measure serialized MIME after adding all parts.
        long mimeBytes = MimeSize.serializedBytes(message);

        if (mimeBytes > MAX_MIME_BYTES) {
            throw new IllegalArgumentException(
                "Email message exceeds configured size limit");
        }

        // 5. Only send after preflight meets requirements.
        mailSender.send(message);
    }
}
~~~

In the example:

- MAX_HTML_BYTES controls the source HTML part.
- MAX_LOGO_BYTES controls the independent inline asset.
- MAX_MIME_BYTES controls the serialized message after building MIME.
- The logo is reused via a resource that can open a fresh stream; the counting and sending steps read the resource separately.
- If there are attachments, call helper.addAttachment(...) before calling MimeSize.serializedBytes(message) so the measurement includes attachments.

In production, move thresholds into ConfigurationProperties, throw appropriate domain exceptions, and record metrics/correlation IDs instead of hardcoding them inside the service.

## 10. Measuring multiple images and summing the resource budget

A template may reference multiple inline images. Maintain an asset list containing name, MIME type, file size, and dimensions.

Example data structure:

~~~java
public record EmailImageAsset(
    String contentId,
    String resourcePath,
    String contentType,
    long maxBytes,
    int maxWidth,
    int maxHeight
) {}
~~~

Declaring assets per template:

~~~java
List<EmailImageAsset> assets = List.of(
    new EmailImageAsset(
        "brandLogo",
        "mail/logo.png",
        "image/png",
        500_000L,
        1200,
        400
    ),
    new EmailImageAsset(
        "productImage",
        "mail/product.jpg",
        "image/jpeg",
        800_000L,
        1600,
        1600
    )
);
~~~

When processing each asset:

1. Open the resource and measure bytes.
2. Check the file size limit.
3. Read width/height using the image metadata reader.
4. Check pixel dimensions and allowed file types.
5. Add the inline part with a unique Content-ID.
6. Record bytes per asset to explain which email is heavy.

Example of summing original file sizes:

~~~java
long totalInlineImageBytes = 0L;

for (EmailImageAsset asset : assets) {
    ClassPathResource resource =
        new ClassPathResource(asset.resourcePath());

    long bytes = ResourceSize.countBytes(resource);

    if (bytes > asset.maxBytes()) {
        throw new IllegalArgumentException(
            "Image exceeds limit: " + asset.resourcePath());
    }

    totalInlineImageBytes += bytes;
}
~~~

totalInlineImageBytes is the total bytes of the **original files**, not the MIME size increase after Base64. If final size control is required, you still must measure the entire serialized message.

### Budget per template

| Email group | HTML budget | Total inline image budget | MIME budget |
| --- | ---: | ---: | ---: |
| OTP / short notification | 50 KB | 0 | 200 KB |
| Order confirmation | 150 KB | 300 KB | 2 MB |
| Newsletter with banner | 300 KB | 1 MB | 4 MB |
| Invoice with PDF | 150 KB | 300 KB | 8 MB |

These are only **illustrative internal budgets**, not official limits of Gmail, Outlook, or SMTP providers. Each email type has different needs; OTP emails usually need no images, whereas newsletters may need banners. The final threshold must sit far enough below the provider's actual limit to leave room for encoding and other MIME parts.

## 11. Display image size and optimization methods

A 2400 × 800 pixel image may be displayed at 600 × 200 CSS pixels to keep sharpness on high-pixel-density screens. However, a 2x image also has larger file size and decoding memory. Do not load an overly large image and just set width="300" in HTML thinking the size has decreased.

Ways to reduce size:

- **Actually resize** the image to an appropriate size before sending or uploading to a CDN.
- Choose the right format: JPEG is usually efficient for photographs; PNG suits graphics needing transparency or sharp edges; GIF is used only when animation is needed and frame count is controlled.
- Compress images at an appropriate quality, balancing sharpness and bytes.
- Strip unnecessary metadata such as EXIF when processing assets.
- Use smaller image variants for email instead of original files from the upload system.
- Limit large background images and avoid placing important content solely inside images.
- For remote images, optimize assets on the CDN and set display dimensions in HTML.

| Format | Suitable for | Notes |
| --- | --- | --- |
| JPEG | Photographs, colorful product images | No transparency; compression quality affects size |
| PNG | Logos, icons, graphics needing transparency | Files can be large for photographs |
| GIF | Simple animations, low-color graphics | Size grows with frame count; some clients show only the first frame |
| SVG | Crisp logos/vectors | Inconsistent embedding/display support; needs raster fallback |
| WebP/AVIF | Modern web assets | Inconsistent email client support; test on target clients |

Do not pick a format just because browsers support it well. Email clients have different filtering policies and display capabilities; PNG/JPEG are usually more compatible choices for important images.

## 12. Images from external URLs still need measuring

Remote images do not directly increase MIME size, yet they still need their own budget. If an email references 12 CDN images, the recipient may have to download many MB of resources after opening the message.

Measure remote images in the asset pipeline to control display speed, CDN cost, pixel dimensions, format, and compatibility. An asset manifest may record:

~~~json
{
  "name": "newsletter-banner",
  "url": "https://static.example.com/email/banner.jpg",
  "contentType": "image/jpeg",
  "bytes": 182400,
  "width": 1200,
  "height": 400,
  "displayWidth": 600,
  "displayHeight": 200
}
~~~

This is data provided by the asset upload/build pipeline. The mail-sending application does not need to download user-supplied URLs again itself just to get dimensions. If checking a remote URL is mandatory, allow only trusted domains, limit redirects, download time, response size, and block IP/private network access to avoid SSRF.

Image URLs can also make HTML larger:

~~~html
<img src="https://cdn.example.com/image?id=123&signature=..."
     alt="Banner">
~~~

Image bytes are not inside MIME, yet long URLs still increase HTML. Do not embed long-lived access tokens or secrets into URLs; if an image URL must be signed, limit scope and lifetime, while considering that images may be proxied/cached by email clients.

## 13. Avoid reading the entire image into memory just to measure

The following short snippet can cause issues:

~~~java
byte[] bytes = resource.getInputStream().readAllBytes();
long size = bytes.length;
~~~

This snippet also lacks stream-closing management. More importantly, it holds the entire file in one byte array. When sending hundreds of emails concurrently with large images, many copies can cause heap pressure or OutOfMemoryError.

To measure, read the stream in a buffer:

~~~java
long count = 0L;
byte[] buffer = new byte[8192];

try (InputStream input = resource.getInputStream()) {
    int read;
    while ((read = input.read(buffer)) != -1) {
        count += read;
    }
}
~~~

If the asset is a local file, Files.size(path) is usually more efficient because the filesystem provides metadata.

### Resources must be re-readable

A measure-then-send workflow usually reads a resource at least twice:

~~~text
Pass 1: measure size
    Resource -> InputStream -> count bytes -> close

Pass 2: serialize MIME or send
    Resource -> fresh InputStream -> read data -> close
~~~

Therefore, attachment sources should be able to open a fresh stream each time. Avoid passing an already-open stream into a lambda and returning that same stream multiple times:

~~~java
// Do not: this stream can be consumed only once.
InputStream input = Files.newInputStream(path);
InputStreamSource source = () -> input;
~~~

Instead:

~~~java
InputStreamSource source = () -> Files.newInputStream(path);
~~~

Ensure the file is not modified between measurement and sending. If the file might change, store a snapshot/version or re-check size/hash before sending to avoid preflight measuring one file while MIME contains different content.

## 14. Measuring MIME does not mean measuring every resource a client downloads

An email may contain:

~~~html
<link rel="stylesheet" href="https://static.example.com/email.css">
<img src="https://static.example.com/logo.png">
<img src="cid:productPhoto">
<a href="https://example.com/order">View order</a>
~~~

When packaged:

- HTML strings and URLs are stored in the HTML part.
- productPhoto is placed into MIME as an inline part.
- logo.png from HTTPS is not inside MIME.
- External CSS is not attached if only referenced by URL.
- Destination links are not fetched when sending, yet URLs still occupy bytes in HTML.
- Gateways may rewrite URLs, changing message size after processing.

Serialized MIME is a good measurement for **the message built by the application**, yet not the total bytes the recipient downloads when opening the email. To optimize the experience, remote assets must also be managed separately.

### Budget model

~~~text
HTML UTF-8 bytes
+ Plain text UTF-8 bytes
+ Inline image bytes
+ Attachment bytes
+ MIME headers / boundaries / encoding overhead
-----------------------------------------------
= Estimated serialized MIME bytes

Remote images / CSS / fonts:
  = Separate asset delivery budget, not added directly to MIME
~~~

Do not add remote image files to the MIME budget, yet do not omit them from the asset budget either.

## 15. Limits of SMTP providers and email clients

Providers may limit total message size, individual attachments, attachment count, recipient count, header size, sending rate, or total daily/monthly volume. Limits differ across ESPs, SMTP relays, and mailbox providers. Some return an SMTP error when a message exceeds the limit, while some APIs return a validation error.

Beyond providers, email clients also have their own HTML rendering/clipping limits. A small MIME email is not necessarily displayed in full if HTML is too long or the client applies clipping. Conversely, fairly long HTML with no attachments may still fit within SMTP message limits.

### Setting an internal threshold below the provider limit

If the provider publishes a maximum message limit, the application should use a **lower safety threshold** to leave room for MIME encoding, headers, gateway transformations, and differences in calculation.

For example, assuming a provider has a 10 MB decimal limit, the application might set an 8 MB MIME budget to leave a margin. Exact numbers must be based on provider documentation and real testing; do not treat this example as a default.

If an over-limit error is received, do not retry the exact same unchanged message. Reduce image/attachment size, convert files to secure download links, or split content by business logic if appropriate.

## 16. Recording measurements to diagnose oversized emails

Preflight logs should contain measurements and correlation IDs, without storing full HTML or files:

~~~json
{
  "deliveryId": "d-123",
  "template": "order-confirmed",
  "htmlUtf8Bytes": 84210,
  "plainUtf8Bytes": 1840,
  "inlineImageBytes": 122880,
  "attachmentBytes": 1048576,
  "serializedMimeBytes": 1684200,
  "imageCount": 1,
  "attachmentCount": 1,
  "preflightResult": "accepted"
}
~~~

These fields help answer which email grew abnormally in size, which template contains too much markup, which image takes most of the size, and whether attachments pushed the message over budget.

Do not log raw HTML, Base64 images, personal data, or sensitive invoice contents just to track sizes. You can log bytes, asset counts, template version, MIME types, and hashes if reconciliation is needed without storing content.

Useful metrics:

- email_html_bytes histogram by template.
- email_inline_asset_bytes by asset type.
- email_attachment_bytes by file type.
- email_serialized_mime_bytes by email type/provider.
- email_preflight_rejected_total by reason.
- email_send_duration and provider size-rejection rate.

Use percentiles (p50/p95/p99) to spot abnormally large messages instead of looking only at averages.

## 17. A reusable preflight class

When multiple services send emails, do not duplicate measurement logic inside each service. You can build an infrastructure component responsible for computing the budget.

~~~java
public record MailSizeReport(
    long htmlBytes,
    long plainTextBytes,
    long inlineAssetBytes,
    long attachmentBytes,
    long serializedMimeBytes
) {}
~~~

A policy:

~~~java
public record MailSizeLimits(
    long maxHtmlBytes,
    long maxInlineAssetBytes,
    long maxAttachmentBytes,
    long maxSerializedMimeBytes
) {}
~~~

A validator class:

~~~java
public class MailSizePolicy {

    private final MailSizeLimits limits;

    public MailSizePolicy(MailSizeLimits limits) {
        this.limits = limits;
    }

    public void validate(MailSizeReport report) {
        if (report.htmlBytes() > limits.maxHtmlBytes()) {
            throw new MailSizeLimitException("HTML is too large");
        }

        if (report.inlineAssetBytes() > limits.maxInlineAssetBytes()) {
            throw new MailSizeLimitException(
                "Inline assets exceed the configured limit");
        }

        if (report.attachmentBytes() > limits.maxAttachmentBytes()) {
            throw new MailSizeLimitException(
                "Attachments exceed the configured limit");
        }

        if (report.serializedMimeBytes()
                > limits.maxSerializedMimeBytes()) {
            throw new MailSizeLimitException(
                "Serialized email exceeds the configured limit");
        }
    }
}
~~~

MailSizeLimitException is an application-defined domain exception. You can use ConfigurationProperties to bind limits from configuration:

~~~yaml
app:
  mail:
    size:
      max-html-bytes: 300000
      max-inline-asset-bytes: 1000000
      max-attachment-bytes: 5000000
      max-serialized-mime-bytes: 8000000
~~~

Values are examples. Determine them based on provider limits and operational targets.

Architecture:

~~~text
Template renderer
      |
      v
Rendered HTML + plain text
      |
      v
Asset resolver / image metadata
      |
      v
MimeMessage builder
      |
      v
Size estimator + policy
      |
      +---- over budget ----> reject / optimize / download link
      |
      v
JavaMailSender.send(message)
~~~

The policy layer does not need to know SMTP hosts or credentials. It only receives the size report and decides whether the message stays within the internal budget.

## 18. Optimizing when an email exceeds budget

When an email exceeds the threshold, there are several ways to handle it depending on content:

### 18.1. Resize or compress images

If a banner has dimensions 3000 × 1000 yet displays at 600 × 200, create a 1200 × 400 asset or another reasonable size before embedding. Choose an appropriate format and compression level.

### 18.2. Use images from a CDN instead of CID

If an image is not required to travel with the email, reference an HTTPS URL. This reduces MIME size, though images may be blocked or fail to load. Keep alt and do not put core information solely inside images.

### 18.3. Convert large attachments into download links

Instead of attaching a large PDF, the application can send a URL to a document download page. The link needs HTTPS, access control checks, expiration, or an appropriately scoped token. Do not create long-lived public URLs if the document contains private data.

### 18.4. Trim markup and CSS

Remove unused HTML, duplicate CSS, unnecessary build comments, and purposeless hidden content. Keep fallbacks and readable markup; do not minify to the point of being hard to maintain without a controlled pipeline.

### 18.5. Move long content to the website

The email can summarize important information and lead to a details page. There is no need to put an entire multi-page report inside HTML if recipients only need to know the outcome and where to view more.

### 18.6. Split messages by business logic

If multiple separate documents need to be sent, send independent emails or create one page to download multiple files. Do not split emails arbitrarily if recipients need a unified message; each message needs a clear ID, subject, and context.

## 19. Common mistakes when measuring sizes

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Using String.length() against byte limits | Counts UTF-16 code units, not UTF-8 bytes | getBytes(UTF_8).length |
| Measuring only HTML and ignoring CID images | Inline images live inside the MIME message | Measure assets separately and serialized MIME |
| Adding remote images into MIME size | Remote image bytes are not inside the message | Track remote asset budget separately |
| Summing original files as MIME size | Base64, headers, boundaries increase size | Serialize MimeMessage to estimate |
| Measuring only pixels, not bytes | Images can have many pixels yet compress small or vice versa | Track both bytes and dimensions |
| Measuring only bytes, not dimensions | Small file size yet huge decoded memory | Limit width, height, and pixel count |
| Reading the entire file into byte[] to count | Increases memory, easily causes heap pressure | Files.size or stream counting |
| Measuring a stream then reusing the consumed stream | Sending cannot read the resource | Resource must be able to open a fresh stream |
| Measuring MIME before adding attachments | Count misses important parts | Measure after building full MIME |
| Modifying the message after measurement | Measurement no longer represents the final message | Measure after the final build step |
| Assuming serialized MIME equals exact SMTP wire size | Transport adds framing/dot-stuffing and provider policies | Use as preflight estimate with margin |
| Using one size threshold for all email types | Newsletters, OTPs, and PDFs have different needs | Budget per template/use case |
| Immediately resending when provider rejects as too large | Unchanged message will still be rejected | Optimize content before resending |

## 20. Preflight workflow before sending email

An implementation workflow can go as follows:

1. **Render the template** with actual recipient data.
2. **Measure HTML and plain text** in UTF-8 bytes.
3. **Check each image**: byte length, MIME type, width, height, pixel count; for GIFs also check animation.
4. **Check attachments**: size, permitted formats, and business limits.
5. **Create MimeMessage** and add all parts via MimeMessageHelper.
6. **Serialize the message to measure** total MIME bytes with a counting stream.
7. **Compare against internal budget** and provider limit with margin.
8. If exceeded, **optimize or reject with a clear reason**; do not send non-compliant messages.
9. If within budget, call JavaMailSender.send(message).
10. **Record metrics and delivery ID** to reconcile provider errors.

~~~text
Render template
     |
     v
Measure HTML / plain text bytes
     |
     v
Inspect image and attachment assets
     |
     v
Build complete MimeMessage
     |
     v
Serialize and count MIME bytes
     |
     v
Within application/provider budget?
     |
   +--+--+
   |     |
  No    Yes
   |     |
   v     v
Optimize, reject,   JavaMailSender.send()
or create link             |
                           v
                   Record submission result
~~~

Preflight is a pre-send check; it does not replace actual SMTP responses. Providers may still reject due to quota, policy, sender authentication, recipient, or non-size-based limits.

## 21. Takeaways

When measuring HTML and image sizes before sending, use the right units and measure the right data layer:

- **HTML**: use UTF-8 byte count after rendering, not String.length().
- **Images**: measure file bytes and pixel dimensions; the two metrics serve two different goals.
- **Remote images**: URLs sit in HTML yet image bytes are not counted in the MIME message; manage a separate asset budget.
- **CID images and attachments**: packaged in MIME, usually increasing in size when Base64-encoded.
- **Entire message**: build all MIME parts then serialize MimeMessage into a counting stream for a preflight figure close to the sent message.
- **Resources**: must be re-readable if measurement and sending access the same asset; avoid holding large files entirely in heap just to count.
- **Limits**: use separate budgets for HTML, images, attachments, and total MIME; leave margin below providers and test target clients.
- **Operations**: record sizes and template/delivery IDs to pinpoint large messages without logging sensitive content.

In Spring Framework Mail, MimeMessageHelper helps build email content and resources, while size measurement should be organized as a preflight step before JavaMailSender.send(...). When knowing clearly which parts take up space, the application can optimize images, trim HTML, or move documents to download links before the SMTP provider rejects the message.
