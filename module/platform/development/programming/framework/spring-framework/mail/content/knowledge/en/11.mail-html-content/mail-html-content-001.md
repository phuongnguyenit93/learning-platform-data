# How does HTML email differ from browser HTML?

An HTML page that runs well in Chrome or Firefox does not necessarily display correctly when sent by email. For example, the same markup using `display: flex`, fonts loaded from the web, and buttons with hover effects may look great in a browser, yet turn into a misaligned column of text, lose its fonts, or lose its buttons in some mail readers.

The reason is that **HTML email is not processed like an ordinary web page**. Email passes through SMTP servers, security filters, storage systems, and many email clients that render it in different ways. Clients may strip JavaScript, restrict CSS, block external images, adjust links, or transform colors on their own in dark mode. Some versions of Outlook on Windows even use a rendering engine that differs from modern browsers.

In Spring Framework Mail, `MimeMessageHelper#setText(html, true)` marks the message content as HTML, but it **does not automatically make that HTML compatible with every email client**. The application must still design the markup, CSS, resources, and plain-text part to suit the email environment.

## 1. Web pages and HTML emails have different goals

A web page is an application that the browser actively loads; it can keep calling APIs, run JavaScript, change the DOM, and interact with the user. An email is a **message that has been packaged and delivered to a mail reader**, where the recipient may only see static content.

| Aspect | HTML page in a browser | HTML in an email |
| --- | --- | --- |
| Where it is displayed | The browser in which the user opens the page | Gmail, Outlook, Apple Mail, mobile apps, webmail, preview gateways... |
| Rendering engine | A relatively modern browser engine | Varies greatly between clients and versions |
| JavaScript | Usually can run according to web policy | Blocked or stripped by most email clients |
| CSS | Broad support, updated with web standards | Inconsistent support; may be filtered or rewritten |
| Layout | Flexbox, Grid, positioning, responsive CSS | HTML tables and inline CSS are usually safer |
| Images | Can be loaded with the page or on request | Remote images are often subject to blocking/proxy/cache policies |
| Fonts | Web fonts and system fonts | Web fonts are inconsistent; a fallback is needed |
| Forms and interaction | Forms, event handlers, APIs, SPAs | Do not rely on forms/scripts inside an email |
| Changing content | Can re-render when data is updated | A sent email usually does not update along with the application |
| Security | Web sandbox, CSP, origin... | Sanitization, link scanning, anti-phishing, blocking of active content |
| Test environment | Browser + main devices | Must be tested on the target email clients |

A correct strategy for email prioritizes **clear and stable content delivery**: readable headings, call-to-action buttons that work as links, a layout that does not break when images are missing, and a plain-text fallback. Complex interactivity should live on a website or application after the recipient clicks a link.

## 2. Email clients can modify or strip HTML

When a browser loads a page, developers usually control most of the HTML/CSS that is sent. With email, the markup can pass through many layers:

```text
Spring Service
    |
    | render template -> HTML string
    v
MimeMessage / MimeMessageHelper
    |
    | Content-Type: text/html; charset=UTF-8
    | or multipart/alternative
    v
SMTP relay / Email Service Provider
    |
    | tracking URL, anti-abuse, DKIM, provider policy
    v
Receiving MTA / security gateway
    |
    | anti-phishing, content filtering, URL rewrite
    v
Email client
    |
    | sanitize HTML, process CSS, block/proxy images,
    | adjust light/dark mode, decide how to display
    v
What the user sees
```

Not every client performs every step in the same way. An email may display differently between the browser webmail version and the desktop application of the same brand. A product name is also not enough to determine the engine: Outlook versions on Windows have different rendering behaviors, especially between the classic and new versions.

### Why not use JavaScript?

The following HTML snippet works like a web page but is **not a reliable email**:

```html
<button onclick="confirmOrder()">Confirm order</button>
<script>
  async function confirmOrder() {
    await fetch("/api/orders/123/confirm", { method: "POST" });
  }
</script>
```

In email, `script` tags, event attributes such as `onclick`, or browser APIs are usually stripped/disabled. The URL `/api/orders/...` is also a relative path, with no stable origin context in the message.

Replace it with an absolute HTTPS link leading to a page managed by the application:

```html
<a href="https://example.com/orders/123">
  View and confirm the order
</a>
```

The destination page will handle login, permission checks, and the confirmation action. Do not perform a sensitive action directly on the GET of a URL, because the security system's link scanner may visit the link before the recipient does.

## 3. CSS in email: inconsistent support

On a web page, developers usually write:

```html
<link rel="stylesheet" href="/styles/app.css">
<section class="layout">
  <aside>Information</aside>
  <main>Content</main>
</section>
```

```css
.layout {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 24px;
}
```

In email, an external CSS link may be blocked or ignored by the client. Grid and Flexbox properties, pseudo-classes, complex selectors, or CSS variables have inconsistent levels of support. Some email clients keep and apply `<style>` in `<head>`; others may filter all or part of it. Therefore **do not treat email as a miniature modern CSS application**.

### Inline CSS is the foundational choice

For example:

```html
<p style="font-family: Arial, Helvetica, sans-serif;
          font-size: 16px;
          line-height: 24px;
          color: #222222;
          margin: 0 0 16px 0;">
  Your order has been received.
</p>
```

Placing important styles directly on the element increases compatibility with clients that do not keep the stylesheet as expected.

However, **inline CSS does not guarantee that every property is supported**. A client may ignore `box-shadow`, `position: fixed`, or some CSS values even when they appear in the element's `style`.

An email should be designed so that **it remains readable even when some effects are lost**.

### Relative support table

| CSS/technique | Compatibility | Approach |
| --- | --- | --- |
| `font-family`, `font-size`, `color` | Relatively widespread | Inline on `td`, `p`, or `a` |
| `padding` on table cells | Usually stable | Preferred for main spacing |
| `background-color` | Fairly widespread, but some clients transform it in dark mode | Set on containers and cells as needed |
| `border` on tables/buttons | Usually usable | Provide a text/link fallback |
| `border-radius` | Inconsistent, especially in some Outlook versions | Accept square corners when unsupported |
| `max-width` | Inconsistent in some engines | Combine with `width` and table structure |
| `display: flex`, `display: grid` | Should not be the foundation of an email layout | Use table layout |
| `position: absolute/fixed` | Limited support | Avoid for main content |
| `:hover`, `::before`, `::after` | Inconsistent | Do not depend on them to convey information |
| `@media` responsive | Many clients support it partially, but not all | Design a fallback that does not need media queries |
| `@font-face` | Unstable support | Use a system font stack |

The table describes **conservative design choices to increase compatibility**; it is not a claim that every client always supports or never supports a feature. When a specific technique is needed, test it on the clients and versions that recipients actually use.

## 4. Why does email still use HTML tables for layout?

On a modern website, using `<table>` purely for layout is generally discouraged. But in HTML email, **tables remain a common layout tool**, because mail-reading engines support table structures relatively consistently.

For example, instead of using Flexbox:

```html
<div style="display: flex; gap: 24px;">
  <div style="width: 50%;">Order information</div>
  <div style="width: 50%;">Shipping information</div>
</div>
```

You can use two table-based columns:

```html
<table role="presentation"
       cellpadding="0" cellspacing="0" border="0"
       width="100%" style="border-collapse: collapse;">
  <tr>
    <td width="50%" valign="top"
        style="padding: 12px; font-family: Arial, sans-serif;">
      Order information
    </td>
    <td width="50%" valign="top"
        style="padding: 12px; font-family: Arial, sans-serif;">
      Shipping information
    </td>
  </tr>
</table>
```

`role="presentation"` helps assistive technologies not treat a layout table as a data table to be read by row/column, when the client keeps this attribute. If it is a **real data table**, such as an invoice detail table, do not add `role="presentation"`: use appropriate data-table semantics.

### An email container with a stable width

Many email templates choose a centered content block with a maximum width of about 600–640px (a reference design value, not a mandatory standard):

```html
<table role="presentation" width="100%"
       cellpadding="0" cellspacing="0" border="0"
       style="width:100%; border-collapse:collapse;
              background-color:#f3f4f6;">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600"
             cellpadding="0" cellspacing="0" border="0"
             style="width:100%; max-width:600px;
                    background-color:#ffffff;
                    border-collapse:collapse;">
        <tr>
          <td style="padding:32px 24px;
                     font-family:Arial,Helvetica,sans-serif;
                     font-size:16px;line-height:24px;color:#222222;">
            <h1 style="font-size:26px;line-height:32px;margin:0 0 16px 0;">
              Order confirmed
            </h1>
            <p style="margin:0;">
              Thank you for your purchase.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
```

Here:

- The outer table takes the full width and provides the background and padding.
- The inner table creates a reading area with a limited width.
- `cellpadding="0"`, `cellspacing="0"`, `border="0"` help reduce default differences in some clients.
- The `width` HTML attribute combined with CSS `width`/`max-width` increases compatibility.
- Main spacing is placed on `td` so it depends less on the default margin behavior of `div` and `p`.

This technique still needs to be tested on small screens. A fixed 600px table may overflow on clients that do not honor `max-width`; responsive email patterns usually combine a flexible container, columns that can stack, and media queries as an additional enhancement layer.

### Does every email need tables?

No. An email with just a paragraph of text or extremely short content can use minimal HTML. Tables are useful when you need a **controlled layout** and support for many clients; they are not a mandatory requirement of MIME.

## 5. Responsive design for phones differs from web responsive design

A web page can change its layout using media queries and Flex/Grid. Email has additional difficulties:

- Many email clients display content in an area smaller than the full screen.
- Some clients do not fully apply `@media` or strip stylesheets.
- Font scaling, auto-fit, dark mode, and viewport handling differ between applications.
- Recipients may enlarge text or enable accessibility options.

For email, **design a readable one-column version first**, then add two columns or advanced layouts if the content truly needs them.

An advanced responsive CSS snippet you can use:

```html
<style>
  @media screen and (max-width: 600px) {
    .mobile-full-width {
      width: 100% !important;
      display: block !important;
    }
    .mobile-padding {
      padding: 20px 16px !important;
    }
  }
</style>
```

But the classes above only take effect in clients that allow `<style>` and the corresponding media queries. The content must still be readable if these rules are ignored.

### Width, buttons, and touch targets

- Place the main content in one column; avoid long text running right up to the screen edge.
- Choose readable fonts and line-height, for example body 16px/24px as a starting point.
- Make CTAs large enough for phone users to tap easily.
- Do not place two important links too close together.
- Avoid fixed-width images with no way to shrink.
- Make important information text; do not put all the information in a single image.

These are experience-design principles, not mandatory specifications of every email client.

## 6. A button in email is usually really a link

The HTML `<button>` may be unsuitable because form/event handling is restricted. A CTA in email is usually an `<a>` styled to look like a button:

```html
<table role="presentation" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td align="center" bgcolor="#1457a4"
        style="background-color:#1457a4; border-radius:6px;">
      <a href="https://example.com/orders"
         style="display:inline-block; padding:14px 22px;
                font-family:Arial,Helvetica,sans-serif;
                font-size:16px;line-height:20px;
                font-weight:bold;color:#ffffff;
                text-decoration:none;">
        View order
      </a>
    </td>
  </tr>
</table>
```

Even when a client ignores `border-radius`, the CTA is still a clickable link. In engines that restrict `display:inline-block` or padding on `<a>`, you may need a button variant for Outlook or a table/conditional-comments structure. What matters is that **the link remains visible and meaningful when the decoration is lost**.

It is usually advisable to add the link as full text in the plain-text part:

```text
View order: https://example.com/orders
```

Do not depend on hover effects or JavaScript to display the URL.

## 7. Images: remote, inline, and embedded are different approaches

On a website, images usually use `<img src="/assets/logo.png">`. Email does not have the same origin as a web page, so relative paths may not work.

### 7.1. Images from an HTTPS URL

```html
<img src="https://static.example.com/email/logo.png"
     width="120" height="40"
     alt="Example logo"
     style="display:block; width:120px; height:40px; border:0;">
```

Advantages: the email does not need to contain the image bytes, and it is easy to distribute through a CDN. Limitations: the client may **block, load through a proxy, cache, or defer** remote images; the URL must be publicly accessible or accessible through a mechanism suitable for email, and it cannot rely on the website's login cookies.

Some clients process image URLs through a proxy or block them entirely to protect privacy; therefore the IP of the image request is not reliable for determining the location or the person who opened the email.

### 7.2. Inline images using Content-ID (CID)

An image can also be a MIME part with a `Content-ID` and be referenced through `cid:...`:

```html
<img src="cid:brandLogo" width="120" height="40"
     alt="Example logo">
```

In Spring Mail:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
    message,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
);

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Welcome");

String plainText = "Hello! Your account is ready.";
String htmlText = """
    <html><body>
      <img src="cid:brandLogo" width="120" height="40"
           alt="Example logo">
      <h1>Welcome!</h1>
      <p>Your account is ready.</p>
    </body></html>
    """;

// Set up the body before adding inline resources.
helper.setText(plainText, htmlText);
helper.addInline(
    "brandLogo",
    new ClassPathResource("mail/brand-logo.png"),
    "image/png"
);

mailSender.send(message);
```

The example assumes that `org.springframework.core.io.ClassPathResource`, `org.springframework.mail.javamail.MimeMessageHelper`, and the necessary types have been imported; the file `mail/brand-logo.png` must be on the classpath, for example `src/main/resources/mail/brand-logo.png`.

`cid:brandLogo` in the HTML must match the ID passed to `addInline("brandLogo", ...)`. Some clients may still block or not display CID images correctly; therefore `alt` and text content are still needed.

### 7.3. Base64 data URI in src

A web page can use:

```html
<img src="data:image/png;base64,iVBORw0KGgo...">
```

But many email clients do not support this consistently, or may filter data URIs due to security policies. Do not rely on this approach to display an important logo/CTA.

### Image comparison

| Image embedding method | Advantages | Limitations |
| --- | --- | --- |
| HTTPS URL | Smaller MIME, CDN easy to manage | Images may be blocked/proxied/cached; the URL must be accessible |
| CID inline | The image travels with the MIME message | Increases message size; display support varies by client |
| Data URI | No external URL needed | Email clients may strip it/not display it |
| Regular image attachment | Users can download the file | Does not automatically become an image in the body |

**Do not let an important message exist only in an image.** For example, if a “Pay” button is just a PNG image, when the image is blocked the recipient may not know what to do. Use text and real links to ensure the content works when images are missing.

## 8. Fonts and Vietnamese

In browsers, using web fonts via `@font-face` or Google Fonts is common. In email, web fonts may not load or may be ignored by the client. You should set a font stack with fallbacks:

```html
<p style="font-family: Arial, Helvetica, sans-serif;
          font-size:16px;line-height:24px;color:#222222;">
  Your order has been confirmed.
</p>
```

If you use a brand font:

```css
font-family: 'Brand Font', Arial, Helvetica, sans-serif;
```

then you need to make sure the text remains readable when the client picks Arial or another system font. The layout should not depend rigidly on the exact width of a single font.

### UTF-8 encoding in Spring Mail

HTML with Vietnamese diacritics should come with the correct encoding:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng");
helper.setText(
    "Đơn hàng của bạn đã được tiếp nhận.",
    "<html><body><h1>Đơn hàng đã được tiếp nhận</h1></body></html>"
);

mailSender.send(message);
```

With multipart and charset UTF-8, the helper creates MIME parts for the right purposes, and Jakarta Mail handles the message transfer encoding. You can also configure `spring.mail.default-encoding=UTF-8` in Spring Boot. Do not manually edit MIME headers or manually encode Vietnamese into arbitrary bytes if you are already using the helper.

## 9. Dark mode can change email colors

Many email clients have a dark mode. However, the way they process HTML is not the same as a browser: some clients keep the declared colors, some convert the background/text or change only part of it, and some support dark-mode meta/CSS to different degrees.

For example, an email declares a white background and black text:

```html
<td style="background-color:#ffffff; color:#111111;">
  Notification content
</td>
```

On some clients, colors may be adjusted; if a logo is only black on a transparent background, it may lose contrast when the background becomes dark.

How to design:

- Keep the contrast between text and background clear enough in both light and dark mode.
- Use a logo with a background area or an appropriate variant when needed.
- Avoid placing important text directly on a background image.
- Check borders, CTAs, and links when colors are changed by the client.
- Do not assume `prefers-color-scheme` always works in email.

Some clients support declarations such as:

```html
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
```

and CSS:

```css
@media (prefers-color-scheme: dark) {
  .email-card {
    background-color: #161616 !important;
    color: #ffffff !important;
  }
}
```

But these are **client-specific enhancements**, not a uniform guarantee. All content must still be readable if the client drops the meta, does not run the media query, or changes the colors in its own way.

## 10. Forms, video, animation, and interactive content

Web pages can contain forms, iframes, video players, complex animations, and JavaScript code. Email needs careful handling:

| Website feature | In HTML email | Alternative approach |
| --- | --- | --- |
| `<script>` and event handlers | Usually blocked or stripped | Move the action to an HTTPS page |
| `<form>` with inputs | Unstable; many clients restrict it | A CTA leading to a form on the website |
| `<iframe>` | Usually blocked | Link to a page/video |
| `<video>` | Support varies by client | Poster image + link to the video viewing page |
| Animated GIF | Some clients show only the first frame, others show the animation | The first frame must contain meaningful content |
| CSS animation | Unstable | Static content must still provide enough information |
| SVG | Display/embedding support is inconsistent | A suitable PNG/JPEG, with alt |
| CSS background image | Support varies | Background color and content that does not depend on the image |

For example, replace a video player with an image that has a clear invitation:

```html
<a href="https://example.com/tutorials/getting-started">
  <img src="https://static.example.com/email/tutorial-poster.jpg"
       alt="Watch the getting started tutorial video"
       width="560"
       style="display:block;max-width:100%;height:auto;border:0;">
</a>
```

If the image is blocked, there should be a separate text link in the paragraph below so the recipient can still open the video.

## 11. Email size and processing limits

A website can load many assets on demand. HTML email is packaged into the message content, and an overly long HTML part can increase load time or cause some clients to clip/truncate the displayed portion.

Factors that make an email heavier:

- HTML containing repeated markup and many nested tables.
- Inline CSS on every element.
- Large data URIs or inline images.
- Too much hidden content used to adjust responsiveness.
- Large attachments.
- HTML content containing many variants that have not been trimmed down.

Content clipping thresholds and size limits depend on the email client and provider, and may change over time. Do not hard-code a fixed clipping number as the standard for every customer.

Appropriate practices:

1. Put the important message and the main CTA near the top of the email.
2. Avoid building an HTML email as a full copy of a long web page.
3. Compress images, limit the MIME size, and consider a download link for documents when files are large.
4. Remove unused CSS/markup when building the template, if doing so does not break the fallback.
5. Use a few short paragraphs, with links to a detail page if the content is too long.

Sending just enough content also reduces the risk of the message being judged abnormal by filters and helps mobile users read faster.

## 12. Don't send HTML only: use multipart/alternative

An ordinary web page does not need a plain-text version of itself. Email is different: some users view mail in text mode, some clients restrict HTML, and some assistive technologies or automated processing systems care only about the plain-text part.

With Spring Mail, you can send **a single email containing two versions**:

```text
multipart/alternative
├── text/plain; charset=UTF-8
└── text/html; charset=UTF-8
```

Java example:

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountNoticeMailer {

    private final JavaMailSender sender;

    public AccountNoticeMailer(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendNotice(String recipient) throws MessagingException {
        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Account activated");

        String plain = """
            Hello,

            Your account has been activated.
            Log in: https://example.com/login
            """;

        String html = """
            <!doctype html>
            <html lang="en">
              <body>
                <h1>Account activated</h1>
                <p>You can log in at the
                  <a href="https://example.com/login">login page</a>.
                </p>
              </body>
            </html>
            """;

        helper.setText(plain, html);
        sender.send(message);
    }
}
```

The overload `setText(plainText, htmlText)` requires the helper to be in multipart mode. The two strings are **two ways of presenting the same message**, not two different emails. The client can choose the appropriate version.

Distinguishing the overloads:

| Method | Meaning |
| --- | --- |
| `helper.setText(text, false)` | A single plain-text message body |
| `helper.setText(html, true)` | A single HTML message body; does not automatically create plain text |
| `helper.setText(plainText, htmlText)` | Two alternative versions; requires multipart |

### Plain-text content must be written deliberately

Do not simply strip all HTML tags and treat the result as a complete plain text. If the HTML uses a “Confirm” button with a URL hidden in `href`, just removing the tags can **lose the URL**.

For example:

```html
<a href="https://example.com/confirm">Confirm account</a>
```

The text version must contain:

```text
Confirm account:
https://example.com/confirm
```

Both versions should contain the same important business information: the recipient, the action, the deadline, the conditions, the link, and warning content. Do not let the HTML and plain-text versions contradict each other.

## 13. HTML templates: don't merge user data into raw markup

On a website, dynamic data is usually escaped by the framework according to context. When building HTML email in Java, if you directly concatenate the customer's name into an HTML string, the application may produce display errors or injection risks:

```java
// Avoid concatenating untrusted data directly into HTML:
String html = "<p>Hello " + displayName + "!</p>";
```

If `displayName` contains the characters `<`, `>`, `&`, or an HTML fragment, the result may differ from the intended content. In an email client, many scripts may be blocked, but that **does not replace escaping and controlling data on the server**.

### Using Thymeleaf for HTML email

You can use Thymeleaf to render content specifically for email, for example by adding the Spring Boot dependency:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

Template `src/main/resources/templates/mail/order-confirmed.html`:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<body style="margin:0;padding:0;background-color:#f3f4f6;">
  <table role="presentation" width="100%" cellpadding="0"
         cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="600" cellpadding="0"
               cellspacing="0" border="0"
               style="width:100%;max-width:600px;background:#ffffff;">
          <tr>
            <td style="padding:28px;font-family:Arial,sans-serif;
                       font-size:16px;line-height:24px;color:#222222;">
              <h1 style="font-size:24px;margin:0 0 16px 0;">
                Order confirmed
              </h1>
              <p>Hello <strong th:text="${customerName}">Customer</strong>,</p>
              <p>Order
                <strong th:text="${orderCode}">ORD-000</strong>
                has been received.
              </p>
              <p><a th:href="${orderUrl}">View order</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

Java template rendering:

```java
import java.util.Locale;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

Context context = new Context(Locale.forLanguageTag("en-US"));
context.setVariable("customerName", customerName);
context.setVariable("orderCode", orderCode);
context.setVariable("orderUrl", "https://example.com/orders");

String html = templateEngine.process("mail/order-confirmed", context);
```

`th:text` escapes characters in text content, preventing the data from being interpreted as markup. With `th:href`, you need to **control the destination URL**: escaping an HTML attribute does not by itself guarantee a safe URL. In transactional business flows, build links from a configured base URL, restrict the domain/scheme, and allow only valid paths/tokens.

Next, create a `MimeMessageHelper` with multipart and then call `setText(plain, html)`. The template engine helps separate email presentation from business logic, and also makes it easier to manage multiple languages and styles.

### CSS inlining can be a build step

A development team can write templates with CSS in `<style>` for easier maintenance, and then use a **CSS inliner** tool to convert the important rules into `style` attributes on each element before sending.

Example before inlining:

```html
<style>
  .body-copy { font-size:16px; line-height:24px; color:#222222; }
</style>
<p class="body-copy">Confirmation content.</p>
```

After inlining:

```html
<p style="font-size:16px;line-height:24px;color:#222222;">
  Confirmation content.
</p>
```

Inlining does not automatically fix CSS features that the client does not support. Responsive media queries may also need to stay in `<style>` for clients that support them. If you use an inliner, you need to define the processing order of templating, inlining, sanitizing, and MIME packaging so that the content is not transformed incorrectly.

## 14. A realistic HTML email: a safer structure

The following example is an HTML message body with a table container, a main content section, a link-style button, a fallback URL, and a footer. It uses only techniques that are relatively familiar in HTML email:

```html
<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background-color:#f3f4f6;">
    <table role="presentation" width="100%" border="0"
           cellpadding="0" cellspacing="0"
           style="width:100%;border-collapse:collapse;background-color:#f3f4f6;">
      <tr>
        <td align="center" style="padding:24px 12px;">
          <table role="presentation" width="600" border="0"
                 cellpadding="0" cellspacing="0"
                 style="width:100%;max-width:600px;border-collapse:collapse;
                        background-color:#ffffff;">
            <tr>
              <td style="padding:32px 24px 16px 24px;
                         font-family:Arial,Helvetica,sans-serif;">
                <h1 style="margin:0;font-size:24px;line-height:30px;
                           color:#1f2937;">
                  Order confirmed
                </h1>
              </td>
            </tr>
            <tr>
              <td style="padding:0 24px;
                         font-family:Arial,Helvetica,sans-serif;
                         font-size:16px;line-height:24px;color:#374151;">
                <p style="margin:0 0 16px 0;">
                  Thank you. We have received your order.
                </p>
                <p style="margin:0 0 20px 0;">
                  All updates will be shown in your account.
                </p>
                <table role="presentation" border="0"
                       cellpadding="0" cellspacing="0">
                  <tr>
                    <td bgcolor="#1457a4" align="center"
                        style="background-color:#1457a4;border-radius:6px;">
                      <a href="https://example.com/orders"
                         style="display:inline-block;padding:14px 22px;
                                font-family:Arial,Helvetica,sans-serif;
                                font-size:16px;font-weight:bold;
                                color:#ffffff;text-decoration:none;">
                        View order
                      </a>
                    </td>
                  </tr>
                </table>
                <p style="margin:20px 0 0 0;font-size:13px;line-height:20px;">
                  If the button does not work, open the link:
                  <a href="https://example.com/orders"
                     style="color:#1457a4;text-decoration:underline;">
                    https://example.com/orders
                  </a>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 24px;
                         font-family:Arial,Helvetica,sans-serif;
                         color:#6b7280;font-size:12px;line-height:18px;">
                This is a notification email from Example.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
```

This layout is designed so that the content remains when images, advanced CSS, or JavaScript are removed. You still need to test in practice on the target clients, especially the container width, the button color in dark mode, the spacing, and line wrapping on small screens.

For production, user data and personalized URLs must go through an escaped template and should not be concatenated directly into this static HTML fragment.

## 15. Security and privacy issues specific to HTML email

### Link tracking and URL scanning systems

An ESP may rewrite:

```text
https://example.com/orders/123
```

into a redirect URL to measure clicks. The receiving-side gateway may then replace that URL with a link from an anti-phishing system. Users or automated systems may visit the link before the recipient actually clicks it.

Therefore:

- Do not treat a `clicked` event as definitive proof that the user took action.
- Do not trigger sensitive security actions from just a GET request to an email link.
- The destination page must authenticate and require an appropriate confirmation action.
- If you use a link with a token, limit its purpose and lifetime, and avoid exposing sensitive information in the URL.
- Do not depend on the displayed URL string being exactly identical to the original URL, because some gateways may rewrite it.

### Tracking pixels and open events

HTML email can contain a 1×1 image to measure loads:

```html
<img src="https://track.example.com/o/opaque-id"
     width="1" height="1" alt="">
```

But the client may not load images, or a proxy/privacy feature may preload them. Therefore an “opened” event is a **resource-load signal**, not proof that the recipient has read the email. Spring `MimeMessageHelper` does not generate a tracking pixel by itself; if you enable tracking at the ESP, you need to understand the service's data policy and measurement limits.

### Secrets and HTML

Do not put long-lived access tokens, sensitive payment information, SMTP secrets, or unnecessary internal content into the HTML or a custom tracking URL. An email can be forwarded, stored in many mailboxes, or scanned by intermediate security systems.

HTML email is not a trusted zone for executing programs, storing tokens securely, or deciding access rights. Authentication and authorization decisions must live on the server.

## 16. Accessibility in HTML email

Email may be read with a screen reader, with enlarged fonts, in high-contrast mode, or as plain text. If you focus only on the appearance in one client, other recipients may run into difficulty.

Some principles:

- Write a **clear subject and headings**; do not use all uppercase or lots of symbols in place of content.
- Use headings in a logical order; do not use a heading tag just for its text size.
- Attach meaningful `alt` text to images that convey information; if an image is purely decorative, you can use `alt=""`.
- Use meaningful link text such as “View order” instead of many links that all say “Click here”.
- Keep contrast good enough; do not rely solely on color to indicate error/success.
- Use layout tables with `role="presentation"` where appropriate, and data tables with header structure when there is genuinely tabular data.
- Avoid text inside images; users who turn off images or use a screen reader may lose information.
- Provide a plain-text alternative for the HTML content.
- Do not require hover or mouse-only interaction to view content.

Example of a functional image:

```html
<img src="https://static.example.com/email/status-success.png"
     width="28" height="28"
     alt="Status: success"
```

If the adjacent paragraph already says “Order successful”, the image can be purely decorative with `alt=""` to avoid the screen reader reading it twice. The decision about alt depends on the actual role of the image.

## 17. Rendering, testing, and compatibility

There are three different levels of testing:

| Level | What it checks | What it does not prove |
| --- | --- | --- |
| Server-side HTML template check | Data is rendered and escaped, URLs are correct | Email clients display it the same as the browser |
| MIME/SMTP check | The email has `text/html`, `multipart/alternative`, and correct inline images/attachments | The inbox displays it exactly as desired |
| Real email client check | Layout, colors, images, links, responsive, dark mode | All future versions will be the same too |

A practical working strategy:

1. **Identify the target clients** according to the recipients, for example Gmail web/mobile, Outlook desktop/web, or Apple Mail.
2. **Design a text version and a one-column layout** to make sure the main content does not depend on complex CSS.
3. **Render the template on the server** with fake data and check escaping, links, and Unicode.
4. **Send a test email to an SMTP test server** to observe the MIME, headers, and the text/HTML parts; do not accidentally send the email to real people.
5. **Send to test mailboxes** on the target clients and check in practice with images on/off, small screens, and dark mode.
6. **Check links** after the gateway/ESP rewrites them, authenticate the destination page, and verify the behavior of link scanners.
7. **Observe results after deployment**: recipient feedback, display errors, bounce rate, and tracking within the privacy limits already mentioned.

Don't just open the `.html` in Chrome and conclude the email is compatible. Chrome does not go through the SMTP/MIME/email gateway pipeline and usually supports CSS/JS much more broadly than many email clients.

### Some tools and approaches

- An SMTP test server in the development environment helps receive emails, view the MIME, and avoid sending out to the Internet.
- Use HTML email testing services across many clients if the project needs high compatibility.
- Capture screenshots of the email in the target clients after the message has actually been delivered to evaluate images, dark mode, and fallbacks.
- If you have an email design system, you can use email-specific templates/frameworks to produce table layouts and inline CSS; you still need to check the output and its maintainability.

No tool guarantees that all current and future clients will look the same 100%. The most important criterion is that **the main content and action are not lost** when a client drops some styles or resources.

## 18. Common mistakes when converting web HTML to email

| Symptom | Cause to check | How to handle |
| --- | --- | --- |
| The email shows the literal `<h1>`, `<p>` | HTML was sent as text/plain | `helper.setText(html, true)` or `setText(plain, html)` |
| Flex/Grid is misaligned | The client does not support CSS layout like a browser | Move the main layout area to tables |
| CSS has no effect | An external stylesheet, `<style>`, or selector was filtered | Inline the important CSS, use simple properties |
| The button cannot be clicked | `<button>` and JavaScript were used | Use a real `<a href="https://...">` |
| The logo disappears | The remote image is blocked, the URL is relative, or the CID is wrong | Use an absolute URL/correct CID and add alt |
| The image becomes an attachment | MIME packaging/`addInline` is incorrect | Use an appropriate `multipart/related`, with a matching `cid` |
| Vietnamese diacritics are broken | Charset/encoding is inconsistent | UTF-8 in the helper, template, and mail config |
| An image with text loses its meaning when the image is blocked | The content exists only in the image | Put the main information in text |
| The email is very wide on mobile | Fixed tables, large images, text that does not wrap | Flexible container, test responsive/fallback |
| Text/buttons lose contrast in dark mode | The client transforms colors on its own | Check both modes, add a reasonable background/border |
| Some Outlook versions display differently | The engine or CSS features differ from the browser | Use compatible email techniques, test by version |
| User content in the template breaks the layout | HTML data is not escaped | Use a template engine with escaping |
| A link is clicked without any user action | A security gateway scans the URL on its own | Do not trigger sensitive operations on GET |
| Only HTML, no text version | `setText(html, true)` is used | Add plain text and use multipart/alternative |
| The end of the email is clipped | Long HTML or client policy | Trim the markup, put important information at the top |
| Sent successfully but the mail is not seen | SMTP accepted is not the same as delivered/inbox | Check provider events, policy, SPF/DKIM/DMARC |

## 19. Decision flow when writing HTML email in Spring

Before creating a template, you can ask yourself:

```text
Does the email need HTML?
   |
   +-- No --> Plain text with SimpleMailMessage
   |
   +-- Yes
       |
       v
Need a stable layout across many clients?
       |
       +--> Table layout + important inline CSS
       |
       v
Has images?
       |
       +--> Absolute HTTPS URL or CID inline
       +--> alt + fallback when images are blocked
       |
       v
Has an action?
       |
       +--> Link <a href="https://...">
       +--> Confirm/authorize on the website
       |
       v
Has an equivalent plain-text version?
       |
       +--> multipart/alternative
       |
       v
Render with an escaping template
       |
       v
MimeMessageHelper + JavaMailSender
       |
       v
Test on an SMTP test server and the target email clients
```

Choosing `MimeMessageHelper` solves the **packaging of HTML email into a MIME message**. Designing HTML email also requires attention to the client's engine, limited CSS, table layout, blocked images, dark mode, accessibility, and consistency between HTML and plain text.

If you need to hold on to one main principle: **HTML email is a document to be read in a highly restricted environment, not a web page that can run like an application**. Build content that is meaningful even when images do not load, advanced CSS is dropped, and JavaScript does not exist at all; then add nicer presentation for the clients that support it.
