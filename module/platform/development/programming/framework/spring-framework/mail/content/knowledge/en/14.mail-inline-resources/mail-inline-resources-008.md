# Inline Image Size and URL-Hosted Images

When designing HTML emails with Spring Framework Mail, images can be included in two common ways: **embedded directly as inline resources** or **referenced via an external URL**. Both approaches can display logos, charts, or illustrations inside the message body, yet they differ in message size, how images are loaded, privacy, reliability, and email client compatibility.

A good choice considers both **display dimensions** and **file size**. For example, a logo displayed at 160 pixels wide does not necessarily only need a 160-pixel source image; high-DPI screens may need a larger source image. Conversely, setting the width attribute in HTML does not shrink the number of bytes transmitted. If the source image is too large, the message still carries or fetches all of those bytes.

With inline resources, the image lives inside the MIME message and HTML references it by **Content-ID**:

~~~html
<img src="cid:companyLogo" alt="Company logo">
~~~

With URL-hosted images, HTML points to an external HTTPS address:

~~~html
<img
  src="https://assets.example.org/email/company-logo.png"
  alt="Company logo">
~~~

Spring Mail supports creating inline MIME parts with **MimeMessageHelper.addInline(...)**. External URL images are typically just an address inside the HTML; when the recipient opens the message, the email client decides whether to fetch the image from that server.

## 1. Two ways to include images in emails

### 1.1. Inline resources via Content-ID

An inline image is packaged inside the email itself as a MIME part. HTML references that part through a **cid:** URL.

~~~java
helper.setText(
        "<html><body>"
      + "<p>Welcome!</p>"
      + "<img src=\"cid:companyLogo\" alt=\"Company logo\">"
      + "</body></html>",
        true
);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

In this example, **mail/logo.png** resides on the classpath. **companyLogo** is the logical Content-ID, which must match **cid:companyLogo** in the HTML. Call **setText(...) before addInline(...)** as recommended by Spring Mail to improve compatibility when email clients interpret MIME parts.

Conceptual MIME structure:

~~~text
multipart/related
├── text/html
│   └── <img src="cid:companyLogo">
└── image/png
    ├── Content-ID: <companyLogo>
    └── Image data
~~~

Because the image data travels with the message, the recipient does not need to contact an external web server to fetch those image bytes. However, the client can still hide images based on its settings or display policies.

### 1.2. Images from an external URL

If the image is already hosted on a CDN or web server, the HTML can reference it directly:

~~~java
String html = """
        <html>
          <body>
            <p>Welcome!</p>
            <img
              src="https://assets.example.org/email/company-logo.png"
              alt="Company logo"
              width="160"
              height="48">
          </body>
        </html>
        """;

helper.setText(html, true);
~~~

In this case, no corresponding image MIME part is added via **addInline**. The message contains only the HTML string with the URL. When the recipient opens the email, the client may fetch the image over HTTPS if permitted.

**Sending an email does not mean the Spring server fetches the image URL itself.** When the application puts only a URL in the **src** attribute, the recipient's email client is normally what performs the request to fetch the image upon rendering.

### 1.3. Quick comparison

| Criterion | Inline resource (CID) | External URL image |
| --- | --- | --- |
| Image byte location | Inside the MIME message | On a web server/CDN |
| HTML reference | cid:contentId | Absolute URL, typically HTTPS |
| Email size | Increases with embedded image and MIME encoding | Usually smaller since no image bytes are carried |
| Network needed on open to fetch image | No need to contact external image host | Usually requires reaching the image host |
| Privacy | Does not make an image-fetch request to an external host for CID images | Image-fetch requests may reveal access metadata |
| Updating images | Each email carries the image snapshot from send time | Image at the URL can be replaced for subsequent loads |
| URL expiration | Independent of external image URLs | Image breaks if URL expires or changes |
| Remote image blocking | Not subject to HTTP image-fetch blocking in the same way, though clients can still hide content | Clients may block remote image loading |
| Version control | Image content stays tied to the sent message | Content can change with whatever the URL serves |
| Best suited for | Critical logos, images that must travel with specific content | Large images, independently updated visuals, updatable marketing content |

No single option is best for every email. Choose based on whether the image must stay fixed with the content as of send time, file size, privacy requirements, and remote hosting availability.

## 2. Image size encompasses two distinct concepts

When someone says "a 300-pixel-wide image," clarify whether that refers to **the pixel dimensions of the source file** or **the display dimensions inside the email**.

### 2.1. Pixel dimensions of the source image

This is the actual number of pixels stored in the file. Examples:

- 320 × 100 px.
- 640 × 200 px.
- 1200 × 400 px.

Pixel dimensions affect the level of detail that can be displayed and often correlate with file size, though they do not strictly determine file size. A 640 × 200 photograph can weigh more than a 1200 × 400 PNG logo if the photograph has rich detail and different compression.

### 2.2. Display dimensions in HTML

HTML can request rendering an image at dimensions different from the source pixel dimensions:

~~~html
<img
  src="cid:companyLogo"
  alt="Company logo"
  width="160"
  height="50">
~~~

If the source file is 640 × 200 px yet displayed at 160 × 50 CSS pixels, the client scales the image down when rendering. **The image's MIME size is still based on the 640 × 200 source file**, not automatically reduced by width/height attributes.

Similarly, if the source image is only 80 × 25 px yet scaled up to 320 × 100 CSS pixels, the image may look blurry or pixelated. HTML attributes cannot invent extra detail.

### 2.3. File size is measured in bytes

File size is measured in bytes, KB, or MB. It affects:

- The email size transmitted over SMTP.
- Send and receive time.
- Memory required when building messages.
- Download time for URL images over the recipient's network.
- Risk of exceeding the provider's message size limit.

**Pixels and bytes are two different metrics.** Two images with identical width/height can have vastly different file sizes due to format, compression level, colors, complexity, and metadata.

## 3. Choosing appropriate display dimensions

Display dimensions should follow the email layout, not merely the original file's dimensions.

Some reference sizes:

| Image type | Illustrative display size | Guidance |
| --- | --- | --- |
| Header logo | 120–200 px wide | Preserve aspect ratio, avoid excessive height |
| Small icon | 24–48 px | Can use a small raster image or supported character/icon |
| In-body illustration | 280–600 px wide | Depends on email column width |
| Banner | Width of content area, often 560–600 px in common layouts | Check on both mobile and desktop |
| Chart | Sized to reading area, typically around 400–600 px | Text and labels must remain legible when scaled down |

These are design reference ranges, not technical limits of Spring Mail or mandatory standards. Emails can use wider or narrower layouts, and clients render across varied viewports.

### 3.1. Preserving aspect ratio

If the source image has a 4:1 ratio, preserve that ratio when scaling down. For instance, display 640 × 160 at 160 × 40.

~~~html
<img
  src="cid:companyLogo"
  alt="Company logo"
  width="160"
  height="40"
  style="display:block;max-width:100%;height:auto;">
~~~

**height:auto** helps supporting browsers/email clients preserve aspect ratio when width shrinks. The width and height attributes supply expected dimensions, keeping layout more stable before images load.

Do not set width and height that mismatch the image aspect ratio unless intentionally cropping or stretching. Stretched images distort logos, faces, or charts.

### 3.2. Responsiveness for small screens

Emails may be opened on phones with narrow viewports. A basic pattern:

~~~html
<img
  src="https://assets.example.org/email/banner.jpg"
  alt="This month's offer"
  width="600"
  style="display:block;width:100%;max-width:600px;height:auto;border:0;">
~~~

In many email clients, inline CSS and the width attribute are better supported than modern web CSS techniques. Still, support is not uniform. Keep email layouts simple, test on target clients, and avoid depending on a single CSS property.

For emails needing broad compatibility, table-based layouts are still commonly used for content areas and image alignment. Do not assume every client fully supports Flexbox, Grid, object-fit, or media queries like modern browsers do.

### 3.3. Providing alt text

Always consider the **alt** attribute:

~~~html
<img
  src="cid:companyLogo"
  alt="ABC Company Logo"
  width="160"
  height="48">
~~~

Alt text helps when images are hidden, fail to load, or when recipients use assistive technology. If an image is purely decorative and adds no information, use **alt=""** to avoid reading redundant descriptions. Never put exclusive critical information inside an image without corresponding text.

## 4. Source images for high-DPI screens

Some screens have high pixel density (HiDPI/Retina). Images whose pixel dimensions match CSS display dimensions 1:1 can look soft or slightly blurry on these displays.

A common approach is preparing source images at roughly **2x the display dimensions**:

| Display dimensions | Suggested source image for 2x displays |
| --- | --- |
| 160 × 40 CSS px | 320 × 80 px |
| 300 × 150 CSS px | 600 × 300 px |
| 600 × 200 CSS px | 1200 × 400 px |

For instance, a logo displayed 160 px wide can use a 320 px wide source file:

~~~html
<img
  src="cid:companyLogo"
  alt="Company logo"
  width="160"
  height="40">
~~~

With CID images, the 320 × 80 file is embedded in the MIME message. With URLs, the client fetches the 320 × 80 file from the server and displays it at 160 × 40 CSS pixels.

### 4.1. 2x images are not always necessary

Larger source images can increase byte size substantially. For simple logos or charts that already look crisp at 1x, there is no need to automatically double every image's dimensions.

Balance:

- Sharpness on high-DPI displays.
- Byte size.
- Actual width of the content area.
- Scaling behavior on mobile.
- Email size quotas and load times.

Do not send a 2400 px image just to display it at 120 px when that extra detail adds no value.

### 4.2. srcset is not a uniform solution for email

Web HTML can use **srcset** so browsers pick images by pixel density or viewport size. Support for srcset across email clients is inconsistent. If broad compatibility is needed, pick one reasonably sized source image and declare explicit display dimensions rather than relying completely on advanced image-selection mechanisms.

## 5. Image size and impact on email size

With inline images, image bytes are packaged inside the MIME message. Binary data is typically encoded with **Base64** when transmitted in email.

Base64 converts every 3-byte group into 4 characters, so the encoded representation is usually around **4/3 the original data size**, before counting line breaks, MIME headers, and boundaries.

Illustrative estimates:

| Original image size | Approximate Base64 part, excluding overhead |
| --- | --- |
| 30 KB | 40 KB |
| 75 KB | 100 KB |
| 150 KB | 200 KB |
| 300 KB | 400 KB |
| 1 MB | About 1.33 MB |

These are planning estimates only. Total actual email size also includes body, headers, other attachments, and library encoding details.

### 5.1. Multiple inline images add up

If an email has 5 images of 200 KB each, raw image bytes total about 1 MB. The Base64 parts can exceed roughly 1.33 MB before adding the rest of the MIME structure.

For a campaign sending thousands of emails, repeating the same logo in every message increases total outbound traffic. Conversely, using an external URL shifts image transfer to when recipients open the mail and depends on the image host. Decisions must consider load on both sender and recipient sides.

### 5.2. Message size limits

SMTP providers typically enforce a message size limit. Limits often apply to the entire message after MIME encoding, not just the sum of original source files.

Therefore, if a provider allows up to a certain message size, do not spend that entire budget on images alone. Leave headroom for:

- Plain-text and HTML bodies.
- MIME headers and boundaries.
- Base64 overhead.
- PDF/CSV attachments.
- Recipients or forwarding systems with lower size caps.

Check your SMTP provider's documentation and receiving system limits. There is no single number that applies to every email service.

### 5.3. URL images do not inflate MIME message size by image bytes

If the HTML contains only:

~~~html
<img src="https://assets.example.org/email/banner.jpg" alt="Banner">
~~~

then the message carries no banner image bytes. It carries only the URL string and HTML markup. Email size stays smaller, though recipients must download the image over the network if their client permits it.

In return, the image may fail to show when clients block remote content, the recipient is offline, the image server errors out, or the URL becomes invalid.

## 6. Optimizing images before embedding or publishing to a URL

Optimizing images is usually far more effective than merely shrinking width/height in HTML.

### 6.1. Resize to actual required display dimensions

If a banner only renders 600 CSS pixels wide, consider a source image around 600 px, or 1200 px if 2x is needed. Do not use a 4000 px image just because the original camera file came at high resolution.

Resizing reduces actual pixel count, usually reducing both byte size and processing cost. Setting width="600" in HTML without resizing the file does not reduce the bytes transmitted.

### 6.2. Choose the right format

| Format | Commonly suited for | Email notes |
| --- | --- | --- |
| **PNG** | Logos, icons, charts, images with transparency or sharp edges | Widely supported, though photographs can be heavy |
| **JPEG** | Photographs and continuous-tone images | File size can be tuned via compression quality; no transparency support |
| **GIF** | Simple graphics or short animations | Animation support varies; some clients show only the first frame |
| **SVG** | Crisp vector graphics | Support and security policies vary; do not assume all clients render it |
| **WebP** | Web images needing efficient compression | Inconsistent support across email clients |

For emails needing wide compatibility, **PNG for logos/transparent graphics and JPEG for photographs** are usually pragmatic choices. If using SVG, WebP, or animated GIFs, test on the email clients recipients actually use and provide fallbacks.

### 6.3. Choose a sensible compression level

JPEG lets you adjust compression quality. Over-compression introduces artifacts and blurs small text or logos. Under-compression yields large files with negligible visual improvement.

Inspect images at their final display size, not merely as thumbnails. Text inside charts, QR codes, and fine details must stay sharp enough to read or scan.

### 6.4. Strip unnecessary metadata

Photographs can contain metadata such as EXIF, device info, or location depending on origin. If unneeded, strip metadata before sending or publishing. This reduces file size and avoids sharing unnecessary details.

Not every file contains sensitive metadata, but image-processing pipelines should enforce clear policies on uploaded assets.

### 6.5. Optimization must not degrade content

For logos with text, charts, and QR codes, reducing file size must not hurt legibility. If an image carries business data, verify content legibility after resizing/compressing before sending.

## 7. Using inline resources in Spring Mail

When choosing CID, Spring Mail builds the MIME part from a Resource or InputStreamSource.

Classpath logo example:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setTo("user@example.net");
helper.setSubject("Notification");

String html = """
        <html>
          <body>
            <h1>Welcome</h1>
            <img
              src="cid:companyLogo"
              alt="Company logo"
              width="160"
              height="48"
              style="display:block;max-width:100%;height:auto;border:0;">
          </body>
        </html>
        """;

helper.setText(html, true);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

mailSender.send(message);
~~~

### 7.1. Image from byte[] via ByteArrayResource

If the application generates images in memory:

~~~java
byte[] optimizedPng = imageService.createOptimizedLogo();

helper.setText(
        "<img src=\"cid:dynamicLogo\" alt=\"Logo\" width=\"160\">",
        true
);

helper.addInline(
        "dynamicLogo",
        new ByteArrayResource(optimizedPng),
        "image/png"
);
~~~

ByteArrayResource works well when the image is already available as a byte[]. The entire byte array sits on the heap, so bound both image size and concurrent email volume.

### 7.2. Image from a file on the filesystem

If the image was generated on disk:

~~~java
helper.addInline(
        "reportChart",
        new FileSystemResource(chartPath),
        "image/png"
);
~~~

The file source can be re-read by the library when building the message. Ensure the file exists, has the right type, and remains accessible throughout the send process.

### 7.3. Combining HTML, plain text, and inline images

If clients that do not render HTML must be supported:

~~~java
helper.setText(
        "Your report is ready. The logo and chart are in the HTML version.",
        """
        <html>
          <body>
            <h2>Monthly Report</h2>
            <img src="cid:reportChart"
                 alt="Revenue chart"
                 width="560"
                 style="max-width:100%;height:auto;">
          </body>
        </html>
        """
);

helper.addInline(
        "reportChart",
        new ByteArrayResource(chartBytes),
        "image/png"
);
~~~

**setText(plainText, htmlText)** supplies two representations of the same content. The image is referenced only in the HTML version; the plain-text version must still state essential information clearly.

## 8. Using external URL images in HTML emails

When choosing URLs, the application does not call **addInline**. It puts the absolute URL in **src**.

~~~java
String html = """
        <html>
          <body>
            <h1>New Announcement</h1>
            <img
              src="https://cdn.example.org/email/banner-2026.jpg"
              alt="November announcement"
              width="600"
              style="display:block;width:100%;max-width:600px;height:auto;border:0;">
          </body>
        </html>
        """;

helper.setText(html, true);
~~~

No image MIME part needs to be created for this URL. The email holds only the address and markup. Upon opening the email, the client may send an HTTP request to the CDN to fetch the image.

### 8.1. URLs must be absolute addresses

Do not use relative paths:

~~~html
<img src="/images/logo.png" alt="Logo">
~~~

Email clients have no base website of the Spring application to resolve **/images/logo.png**. Use a full URL:

~~~html
<img
  src="https://assets.example.org/images/logo.png"
  alt="Logo">
~~~

### 8.2. Prefer HTTPS

Use HTTPS to protect the image-fetch connection and avoid mixed content or policies blocking unencrypted HTTP. The image host's TLS certificate must be valid, and the URL must be reachable from the recipient's network.

A URL reachable only inside an internal network, over a VPN, or from the application host may be unreachable from external email clients.

### 8.3. Do not require cookies or application login

Email images should be hosted at addresses accessible under the policies email clients use. A URL requiring website session cookies, SSO login, or custom Authorization headers will likely fail to load inside email clients.

Never put passwords, bearer tokens, or secrets into an image URL's query string. URLs can appear in email HTML, logs, proxies, and analytics systems.

If an image must be protected per user, consider a purpose-built authenticated download mechanism or appropriate inline resources. Expiring signed URLs can work, though emails opened after expiration will fail to load the image.

### 8.4. URLs must stay stable long enough

An email may be reopened days or months after it was sent. If an image uses a temporary URL, an expired token, or a changed path, the image may disappear when the recipient reopens the email.

For transactional content, decide whether the image must stay unchanged as of send time. If consistency is needed, CID may fit better because the image snapshot travels inside the message. If using URLs, establish versioning and retention policies.

## 9. Privacy when using URL images

When an email client loads an image from an external server, the image server may receive request metadata depending on how the client and proxy behave:

- Timestamp of the fetch.
- IP address of the client or proxy.
- User-Agent or similar metadata, if sent.
- URL path and query string.
- Details about how the resource was requested.

Thus, URL images can be used to infer email open times or track engagement. This is why some clients block remote images, show warnings, or fetch images through their own proxies/caches.

### 9.1. Image proxies and caching

Some email providers fetch images through their proxy servers, cache the result, and serve it to users. This can:

- Hide the recipient's real IP from the image host.
- Cause requests to occur at times different from when the user actually views the message.
- Cache the same URL so updated images are not immediately reflected.
- Make image-based open-rate tracking inaccurate.

Do not assume every user email open generates a direct request to the origin server. Behavior depends on the provider, client, settings, and privacy policies.

### 9.2. Tracking pixels and responsible usage

A 1×1 pixel image from a URL can be used to log requests when clients load images. This is a tracking technique, not a technical requirement for rendering email content.

If the system uses tracking, evaluate transparency notices, consent, and privacy regulations applicable to recipients. Do not treat image-fetch requests as definitive proof a user read the content, since proxies, caches, and image blocking skew results.

### 9.3. CID is not an open-tracking mechanism

CID images are packaged inside the email and need no request to an external image host to fetch data. Thus, they do not generate the same kind of HTTP signal as URL images. Likewise, using CID provides no proof that the recipient opened or read the email.

## 10. Possibility of URL images being blocked

Many email clients withhold remote images until the recipient allows them. Some clients fetch through proxies, some display warnings, or disable images via administrative policy.

Common causes:

- Client blocks remote images by default to protect privacy.
- Recipient chooses not to load external images.
- URL returns 403, 404, or 5xx errors.
- Image host requires login or cookies.
- Invalid HTTPS certificate.
- Corporate firewall or proxy blocks the domain.
- URL expired or image was deleted.
- Image uses a format unsupported by the client.

Therefore, URL images must have **alt text**, and email content should not depend solely on images.

### 10.1. Alt text for remote images

~~~html
<img
  src="https://cdn.example.org/email/sale-banner.jpg"
  alt="November promotion: discounts on eligible orders"
  width="600">
~~~

If the image fails to load, the client can show alt text or pass it to assistive technology. Alt text should convey the image's meaning rather than merely saying "image" or "picture."

### 10.2. Do not put all content inside banners

If a banner is the only place showing an offer deadline, promo code, or key instructions, recipients lose that information when images are blocked. Repeat essential information as text in the body.

## 11. Choosing between CID and URL by email type

| Scenario | Typically suitable choice | Reason |
| --- | --- | --- |
| Small brand logo in transactional email | CID or stable URL | CID keeps image inside message; URL reduces size |
| Chart generated specifically for each report | CID | Image is tied to the report's data and generation time |
| Large marketing banner | URL/CDN | Reduces message size and lets assets be updated |
| Image that must render without external host access | CID | Image bytes reside inside the email |
| Frequently updated image | URL with versioning/cache policy | Asset can be updated on the server |
| Image with sensitive or recipient-specific info | Consider CID or protected download channel | Avoids public URLs exposing data |
| Email with many high-resolution images | URL or download link | Keeps message size bounded |
| Email needing exact imagery preserved as of send time | CID or immutable versioned URL | Prevents unintended image changes |

This table is only a guide. A single email can combine both approaches: small logo via CID, large illustration via URL. When combining them, account for the possibility that one image renders while the other is blocked.

## 12. Combining CID images and URL images in the same HTML

An email does not have to use only one method. Example:

- Company logo is a small asset that should travel with the sent email: use CID.
- Large campaign banner managed on a CDN: use an HTTPS URL.

~~~java
String html = """
        <html>
          <body>
            <img
              src="cid:companyLogo"
              alt="Company logo"
              width="150">
            <h1>November Announcement</h1>
            <img
              src="https://cdn.example.org/campaign/november-banner.jpg"
              alt="November campaign banner"
              width="600"
              style="max-width:100%;height:auto;">
            <p>Program details are outlined below.</p>
          </body>
        </html>
        """;

helper.setText(html, true);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

In the message, the logo is packaged as a MIME part. The banner has only a URL in HTML. When a client opens the message, it may display the CID logo while blocking the external banner.

Thus, text content must remain complete and independent of both images loading.

## 13. Turning a URL image into an inline resource

Sometimes a system stores images in object storage or a CDN, yet the email needs to carry the image snapshot at send time. The application can then **download the image bytes from an authorized source**, and add them via addInline or addAttachment.

Conceptual flow:

~~~text
Controlled Image URL
       |
       v
HTTP client / storage SDK
       |
       v
byte[] image
       |
       v
ByteArrayResource
       |
       v
MimeMessageHelper.addInline(...)
       |
       v
CID part inside email
~~~

Example MIME attachment after downloading:

~~~java
byte[] imageBytes = imageClient.download(approvedImageUri);

helper.setText(
        "<img src=\"cid:productImage\" alt=\"Product\">",
        true
);

helper.addInline(
        "productImage",
        new ByteArrayResource(imageBytes),
        "image/jpeg"
);
~~~

**imageClient.download(...)** is an illustrative application-defined API. It must return valid image bytes with timeouts and size limits. **approvedImageUri** must come from a controlled source, never an unvalidated user-submitted URL.

### 13.1. Validating URLs to prevent SSRF

If the Spring server actively fetches a user-supplied URL, it is no longer the email client loading a remote image. The backend is making an HTTP request on the user's behalf. Guard against **Server-Side Request Forgery (SSRF)**:

- Allow only configured domains or storage buckets.
- Validate scheme, host, port, and resolved IP addresses after DNS lookup.
- Block loopback, link-local, private networks, and disallowed metadata endpoints.
- Control redirects; never allow redirects to forbidden hosts.
- Enforce connect/read timeouts.
- Enforce response size limits before materializing into byte[].
- Verify actual MIME type and file format.
- Never send internal cookies, tokens, or headers to untrusted hosts.

If the goal is simply for the email client to load an image from a public URL, the Spring server usually does not need to download that image first.

### 13.2. Verifying Content-Type and actual data

Do not blindly trust the Content-Type header returned by an external server. An endpoint could return an HTML error page with an unexpected status or media type, and the app would label those bytes as image/jpeg.

Check HTTP status, size limits, and actual data format before embedding. If download fails, decide whether to render without the image, fall back to a default asset, or fail the task per business rules.

## 14. Avoid embedding images with Base64 data URLs in HTML

Some HTML allows representing images like:

~~~html
<img src="data:image/png;base64,iVBORw0KGgo...">
~~~

This is a **data URL**. It differs from CID:

- A data URL embeds image data directly inside the HTML attribute.
- A CID references a separate MIME part inside the message.
- An HTTPS URL references an external resource.

Email clients do not support data URLs uniformly; many clients strip or block this embedding style. It also bloats the HTML part and increases message size.

With Spring Framework Mail, when embedding images in a structured MIME way, use **MimeMessageHelper.addInline(...)** instead of stuffing Base64 into HTML. For external images, use HTTPS URLs.

## 15. Caching and versioning URL images

URL images may be cached by browser proxies, email providers, or CDNs. This reduces load and speeds delivery, but means a new image will not necessarily appear immediately if you overwrite a file at the same URL.

### 15.1. Use versioned URLs

Example:

~~~text
https://cdn.example.org/email/logo-v3.png
~~~

When the logo changes, publish a new versioned URL rather than overwriting content at the same URL if you want to avoid stale caches. This lets new messages reference the new asset while older messages continue referencing the old version if the server keeps that URL active.

### 15.2. Cache-Control

CDNs can configure cache headers based on asset lifecycle. For frequently changing campaign images, balance caching between speed and update propagation. For stable logos, long cache lifetimes can work well.

Email clients may run their own proxies/caches and do not necessarily honor every header the way standard browsers do. Test on target providers.

### 15.3. Do not delete images right after a campaign if emails are still reopened

Old emails may be opened by recipients after a campaign ends. If the image URL is deleted, banners will stop rendering. Define asset retention at least matching how long emails are expected to be viewed.

If immutable content is required, use CID or versioned URLs retained per policy.

## 16. URL images and expiring signed URLs

A signed URL typically contains a token or signature in its query string and remains valid only for a limited window. This helps restrict download access, yet poses a challenge for email:

~~~text
Send date: URL is valid
Later date when recipient reopens email: URL has expired
Result: image fails to load
~~~

If using signed URLs in emails, expiration must align with the email's usage lifecycle. Avoid granting overly broad permissions or excessively long lifetimes unnecessarily. Signed URLs can also end up in logs or be forwarded with the email; treat them as access credentials that require protection.

For sensitive documents, rather than using public image URLs, consider authenticated download channels, controlled expiring links, or embedded data if policy permits. Never put secrets inside image URLs solely to avoid attachments.

## 17. URL images can change after an email is sent

A key difference between CID and URL:

- CID binds specific image bytes to the sent email.
- A URL binds the email to an address; content at that address can change later.

For example, suppose a campaign email is sent today with:

~~~html
<img src="https://cdn.example.org/promo/current-banner.jpg">
~~~

If the CDN replaces the file at that same URL next week, recipients reopening the old email may see the new banner, depending on caching. That can be inappropriate if the email states prices, deadlines, or promotion terms as of send time.

If content must reflect the exact moment of issuance, use **CID** or immutable versioned URLs. If an image needs continuous updates like a system logo, a URL may fit better.

## 18. Accessibility and fallback content

Whether using CID or URLs, emails should contain useful text when images fail to display.

~~~html
<img
  src="cid:paymentStatus"
  alt="Payment completed"
  width="240"
  height="80">
<p>Payment for order ORD-1001 is complete.</p>
~~~

If the image is blocked, the recipient can still read the status as text.

For decorative images:

~~~html
<img src="cid:decorativeDivider" alt="" width="600">
~~~

An empty alt attribute is appropriate when an image conveys no information and should be skipped by screen readers.

Key principles:

- Alt text describes meaning; it does not need to repeat filenames.
- Never embed exclusive critical text inside banners.
- Use colors and images as aids, never the sole information channel.
- Test the email with images disabled.
- Ensure the plain-text body conveys the core message when included.

## 19. Testing inline and URL images in development

You can use an SMTP capture server to inspect raw messages and verify MIME structure before sending to real mailboxes.

### 19.1. For CID

Verify:

- HTML contains src="cid:...".
- The message has an image MIME part.
- The part's Content-ID matches the value in HTML.
- Content-Type matches the image bytes.
- Multipart mode is right.
- setText is called before addInline.
- The file/resource is readable at send time.

### 19.2. For URLs

Verify:

- src is an absolute URL.
- HTTPS is used.
- The URL is reachable from external networks matching recipients.
- No website-specific cookies/sessions are required.
- The URL does not expire before the email is opened.
- The image returns the right media type and status.
- The host has valid TLS and sufficient capacity for traffic.

A successful test request from a developer machine does not prove every email client can fetch it. Corporate networks, proxies, recipient settings, and image proxies can produce different results.

### 19.3. Testing multiple screen sizes

Inspect the email on at least one desktop screen and one mobile viewport. Check:

- Images do not overflow the content area.
- Image aspect ratios are preserved.
- Text in charts remains legible.
- Banners are not overly tall.
- Alt text is meaningful when images are disabled.
- Layout does not depend on CSS supported by only a few clients.

### 19.4. Do not test solely in a browser

An HTML email may look great in a web browser yet render differently in Gmail, Outlook, Apple Mail, or enterprise clients. Web browsers do not represent every email rendering engine and security policy.

## 20. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Inline image makes email too large | High-resolution or oversized source image | Resize and compress file before addInline |
| Image looks blurry | Small source file scaled up | Generate source image with enough pixels for display size |
| Small width set yet message stays large | HTML only changes display size, not image bytes | Optimize the actual image file |
| URL image does not appear | Client blocks remote images or broken URL | Provide alt text, check URL, and keep text copy |
| URL works locally but fails in email client | Internal URL, needs VPN/cookie, or blocked by firewall | Use a host reachable by recipients |
| Old image still appears after update | CDN or client caches the URL | Version URLs and configure cache headers properly |
| Old emails lose their banner | URL expired or image deleted | Retain assets for email lifecycle or use CID |
| URL image triggers unexpected tracking | Host logs requests or tracking pixels | Review privacy, proxies, and consent |
| Inline image does not show | CID mismatch or missing MIME part | Check addInline and HTML |
| SVG/WebP does not display | Client lacks support or blocks format | Supply PNG/JPEG instead |
| Mobile causes image overflow | Fixed dimensions or unsuitable CSS | Use sensible width, max-width, and height:auto |
| Server-side image download causes security flaw | User-controlled URL without SSRF checks | Allowlist hosts, check redirects/IPs, timeouts, and size |

## 21. Frequently asked questions

**1. Does a 600 px wide image mean the file must weigh 600 KB?**

No. Pixels describe image dimensions, while KB/MB measure data size. Two images with identical pixel dimensions can differ hugely in byte size.

**2. Does setting width="160" make an inline image smaller inside the email?**

It instructs supporting clients to render the image 160 pixels wide. It does not reduce the bytes of the embedded file. To shrink file size, resize or compress the source file first.

**3. Should I use 1x or 2x source images?**

If sharpness on high-DPI displays matters, a 2x source image relative to display dimensions can help. However, it increases data size. Choose based on actual detail needs and message limits.

**4. Do URL images make emails smaller?**

Usually yes, because the message carries only the URL instead of image bytes. Recipients must download the image from an external host when clients permit.

**5. Why does a URL image fail to appear in email clients even though it opens in a browser?**

The email client may block remote images, lack required cookies/sessions, use a different proxy, or the URL may be unreachable from the recipient's network.

**6. Are CID images guaranteed to display more reliably than URLs?**

CID avoids fetching image bytes from an external host, yet clients can still hide images or handle messages unexpectedly. Test on target clients.

**7. Can CID be used for large banners?**

Technically yes, though the image will bloat the message. For large banners, URL/CDN usually cuts email size; CID fits when the image must stay fixed to the message at send time.

**8. Can CID and URLs be combined in the same email?**

Yes. For example, logo via CID and large banner via HTTPS URL. Ensure content stays complete when remote images are blocked.

**9. Can a URL image change after the email is sent?**

Yes. If the server replaces content at the same URL, someone reopening the email may see the new image, subject to caching. Use versioned URLs or CID if immutable content is required.

**10. Should data:image/png;base64 be used in HTML emails?**

Do not rely on it for emails needing broad compatibility. Many clients handle data URLs inconsistently. Use CID for embedded images or HTTPS for external images.

**11. Can SVG or WebP be used?**

In some clients yes, though support is uneven. PNG/JPEG are generally more practical when wide compatibility is needed.

**12. When a Spring server downloads a URL image to embed via CID, what should be watched?**

Download only from controlled sources; validate hosts and redirects, block disallowed internal addresses, enforce timeouts and byte limits, and verify actual media type and format. Because this is a backend request, SSRF protections are required.

**13. Can remote images tell whether a user opened an email?**

Image-fetch requests can yield access signals, but proxies, caches, and image blocking make the data inaccurate. If using tracking, evaluate privacy and legal requirements.

## 22. Takeaways for choosing inline image size and URL images

**Display size**, **source pixel dimensions**, and **file size** are three distinct concepts. Width/height attributes in HTML control presentation, not the image's byte count. To keep emails lighter, resize and compress source files, pick suitable formats, limit image counts, and account for MIME/Base64 size growth.

**Inline resources via CID** carry image bytes inside the message, fitting when visuals must stay tied to the content as of send time or external image hosts should be avoided. **HTTPS URL images** keep messages smaller and enable independent asset management, yet depend on network access, remote-image blocking policies, caching, URL lifecycles, and privacy.

In Spring Framework Mail, use **addInline(...)** for images referenced by HTML via **cid:**; if using only external images, put the absolute URL in **src** and skip creating image MIME parts. Whichever approach you choose, preserve aspect ratio, declare sensible display dimensions, provide alt text, avoid putting essential info solely in images, and test on target email clients.
