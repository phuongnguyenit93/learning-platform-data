# Inline CSS and the support limits of mail clients

## 1. Why isn't HTML email like a web page?

In **Spring Framework Mail**, an application can use `JavaMailSender` and `MimeMessageHelper` to send `text/html` content. Syntactically, HTML email still has familiar tags such as `<table>`, `<p>`, `<a>`, and `<img>`. However, **a mail client is not a full web browser**: each email-reading application has a different rendering engine, security limits, and way of handling CSS.

An email may look great in Apple Mail but have misaligned columns in classic Outlook on Windows, lose some formatting in Gmail, or change colors in dark mode. Common symptoms:

- Background color, fonts, or spacing differ from the design.
- A layout written with `display:flex` or CSS Grid does not turn out as expected.
- A call-to-action (CTA) button loses its background or is hard to tap.
- Images are blocked from loading, are too wide, or are unclear in dark mode.
- Content looks good on desktop but overflows the mobile screen.
- One Outlook version displays differently from another Outlook version.
- HTML tags appear verbatim because the MIME part was assigned `text/plain` instead of `text/html`.

SMTP transports MIME messages, but it **does not determine how CSS is displayed**. HTML/CSS support depends on the client and on the actual email the recipient opens. Therefore, you must design by the principle of *broad compatibility, with fallbacks and conditional enhancement*.

> **Key idea:** Put essential styles directly on the HTML element (inline CSS), use table layout for the parts that need broad compatibility, ensure the content is still readable if CSS/images are restricted, and test on the target mail clients.

## 2. What is inline CSS?

**Inline CSS** is writing CSS rules in the `style` attribute of the element itself:

~~~html
<p style="color:#1f2937; font-family:Arial,sans-serif;
          font-size:16px; line-height:24px;">
  Your report is ready.
</p>
~~~

Comparing the declaration methods:

| CSS style | Example | Characteristics in email |
| --- | --- | --- |
| **Inline** | `<p style="color:#1f2937">...` | The rule is attached directly to the element; suitable for essential formatting |
| **Internal stylesheet** | `<style>.notice { color:#1f2937; }</style>` | Some clients support it, but may filter it, rewrite it, or drop some rules |
| **External stylesheet** | `<link rel="stylesheet" href="...">` | Unreliable; many clients do not load external CSS |
| **Legacy HTML attribute** | `<td align="center" bgcolor="#ffffff">` | Can serve as a fallback for some attributes in older renderers |

Example of writing a class in a stylesheet:

~~~html
<style>
  .notice {
    color: #1f2937;
    font-family: Arial, sans-serif;
    font-size: 16px;
    line-height: 24px;
  }
</style>
<p class="notice">The report is ready.</p>
~~~

When you put important styles directly on the element:

~~~html
<p class="notice"
   style="color:#1f2937; font-family:Arial,sans-serif;
          font-size:16px; line-height:24px;">
  The report is ready.
</p>
~~~

The email depends less on whether the client keeps the stylesheet or the `.notice` selector. **But inline CSS does not guarantee that every property is supported**: putting `display:grid` into `style=""` does not suddenly make a renderer that does not understand CSS Grid support that feature.

## 3. Limits of the email environment

### 3.1. HTML email is often filtered for security

A mail client may:

- Strip JavaScript, event handlers such as `onclick`, and some unsafe tags or attributes.
- Filter or adjust CSS, URLs, selectors, and special elements.
- Display content in an area isolated from the application's UI.
- Block loading of external images, or use a proxy/cache to fetch images.
- Change background/text colors when dark mode or accessibility settings are active.

Therefore, do not build an email that relies on JavaScript, complex interactive forms, CSS loaded from a CDN, or the assumption that web fonts will be loaded. The interface should mainly carry content and links to a secure website.

### 3.2. Groups of mail clients do not render the same way

| Mail client group | What to pay special attention to |
| --- | --- |
| **Gmail** web/mobile | Supports a lot of CSS, including some stylesheets and media queries under certain conditions, but still filters/transforms HTML and differs by environment |
| **Classic Outlook on Windows** | Many versions use a renderer based on Microsoft Word; strongly limited with flex/grid and some web CSS properties |
| **New Outlook and Outlook on the web** | A web-based rendering mechanism different from classic Outlook; do not assume every product named Outlook uses the same engine |
| **Apple Mail** macOS/iOS | Usually supports diverse CSS, but dark mode, remote content loading, and privacy protection still have an impact |
| **Android/other mobile apps** | Depends on the app, operating system, version, and view mode; test on representative devices |

This table describes **compatibility risk**, not a list guaranteeing 100% support for a property. Mail client versions change over time; do not apply a judgment about an old version to all new versions.

### 3.3. Content must be readable when CSS or images disappear

You should ensure:

- The reading order of the content is reasonable right in the HTML source.
- Important information appears as text, not only inside an image.
- Links and CTA buttons have meaningful text labels.
- Images have appropriate `alt`; decorative images can use `alt=""`.
- Text has enough contrast with the background in situations where colors are overridden.
- The email has a fallback `text/plain` version for when the client does not allow HTML to be displayed.

This is fault-tolerant design: **CSS is a presentation layer, and should not be the only place that holds business information**.

## 4. Which CSS deserves priority?

No table is absolutely correct for every mail client, but the following group of techniques helps build better compatibility:

| Property or technique | How to use it | Risk |
| --- | --- | --- |
| `font-family` with system fonts | Inline on text and main cells | Always include a fallback such as `Arial, Helvetica, sans-serif` |
| `font-size`, `line-height`, `color` | Inline to keep readability | The client may apply accessibility settings |
| `background-color` | Set on the container/cell; consider `bgcolor` | May be changed by dark mode |
| `padding` on `td` | Basic content spacing | Usually more reliable than depending entirely on margin |
| `border` and `border-collapse` | Borders for tables/cells | Need to check the result in the target Outlook |
| `width` and HTML `width` | A frame with a size and a fallback | Avoid making the email overflow narrow screens |
| `max-width` | Limits the horizontal extent in supporting clients | Some older renderers need a fallback solution |
| `display:block` for `img` | Avoids whitespace below images in many layouts | The image can still be blocked from loading |
| `border-radius`, `box-shadow` | Decorating buttons or cards | May not be rendered; the content must still be usable |
| `@media` query | Responsive enhancement where supported | The default version must still be easy to read |
| `display:flex`, CSS Grid | Avoid as the foundation of a broadly compatible layout | Many clients/render engines do not fully support them |
| `position:fixed/absolute` | Should not be relied on for the main layout | Easily overlaps or is ignored |
| CSS variables, pseudo-selectors | Use only for enhancement | Some clients do not support them/strip them |
| Animation, transition, filter | Do not use for essential content | Fragmented support |
| Web font via `@font-face` | Conditional decoration | Must provide a fallback system font |

### 4.1. Fonts, font size, and text color

~~~html
<td style="font-family:Arial,Helvetica,sans-serif;
           font-size:16px; line-height:24px;
           font-weight:400; color:#1f2937;
           padding:16px 24px;">
  Your account has been verified.
</td>
~~~

The font stack creates a fallback. For Vietnamese content, the font must have suitable glyphs; the MIME `charset=UTF-8` helps decode characters, but it **does not choose the font and does not fix CSS errors**.

### 4.2. Spacing in table cells

~~~html
<table role="presentation" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td style="padding:24px 28px;">
      <p style="margin:0; font-size:16px; line-height:24px;">
        Notification content.
      </p>
    </td>
  </tr>
</table>
~~~

Putting the frame spacing on `td` helps avoid depending entirely on the margins of `div`/`p`, which may be rendered differently. This does not mean every kind of margin is prohibited, but the structural part should use a more stable technique.

### 4.3. Background color and dark mode

~~~html
<td bgcolor="#ffffff"
    style="background-color:#ffffff; color:#1f2937;
           font-family:Arial,sans-serif;">
  Your order information.
</td>
~~~

`bgcolor` is a traditional HTML fallback in suitable clients; `background-color` helps clients that support CSS. However, dark mode may transform colors, so you still need to check contrast. Do not set white text relying only on a dark background image: when the image is blocked, the text may be unreadable.

## 5. Why is table layout still common in email?

On websites, flexbox and CSS Grid are usually the modern choice. In email that needs broad compatibility, **table-based layout** is still useful because many mail clients, including older renderers, handle table structures relatively consistently.

A basic email frame:

~~~html
<table role="presentation" width="100%" cellpadding="0"
       cellspacing="0" border="0"
       style="width:100%; border-collapse:collapse;">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="100%"
             cellpadding="0" cellspacing="0" border="0"
             style="width:100%; max-width:600px;
                    border-collapse:collapse;">
        <tr>
          <td style="padding:24px; font-family:Arial,sans-serif;
                     font-size:16px; line-height:24px;">
            Hello! The weekly report is ready.
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
~~~

Characteristics:

1. The outer table is `100%` wide and has one cell that centers the content.
2. The inner table has `width:100%; max-width:600px` to avoid being too wide on the many clients that support it.
3. `padding` on `td` creates spacing around the text.
4. The HTML attributes `width` and `align` create a fallback for some renderers.
5. `role="presentation"` signals that this is a **layout table**, not a data table. This helps assistive technologies avoid reading the rows/columns as business data.

If the email contains a **real data table** such as columns of date, status, and amount, use markup with the corresponding table semantics such as `<th>` and headings. Do not put `role="presentation"` on a data table just because you want it to be easy to style.

### 5.1. max-width and classic Outlook

Some classic Outlook renderers do not handle `max-width` like a web browser. When you need to keep content at a specific width in these versions, you can apply a **hybrid layout** or conditional markup for Microsoft Office (MSO).

Example of a container with a fallback for Outlook using the Word engine:

~~~html
<!--[if mso]>
<table role="presentation" width="600" cellpadding="0"
       cellspacing="0" border="0">
  <tr><td>
<![endif]-->

<table role="presentation" width="100%" cellpadding="0"
       cellspacing="0" border="0"
       style="width:100%; max-width:600px;">
  <tr>
    <td style="padding:24px;">Email content</td>
  </tr>
</table>

<!--[if mso]>
  </td></tr>
</table>
<![endif]-->
~~~

Conditional comments `<!--[if mso]>...<![endif]-->` are a technique used in email to serve some classic Outlook versions; other clients usually treat them as comments. You need to check the target Outlook version and ensure the open–close pairs of table/tr/td are exact. **Do not add MSO branches when there is no real compatibility need**, because they make the markup hard to maintain.

### 5.2. A two-column layout does not mean responsive

~~~html
<table role="presentation" width="100%"
       cellpadding="0" cellspacing="0" border="0"
       style="width:100%; border-collapse:collapse;">
  <tr>
    <td width="50%" valign="top"
        style="width:50%; padding:12px;">
      <p style="margin:0; font-family:Arial,sans-serif;">
        Order number: A102
      </p>
    </td>
    <td width="50%" valign="top"
        style="width:50%; padding:12px;">
      <p style="margin:0; font-family:Arial,sans-serif;">
        Status: Confirmed
      </p>
    </td>
  </tr>
</table>
~~~

This is two columns at a 50/50 ratio; it **does not automatically turn into one column on a narrow screen**. The content may get squeezed and wrap onto many lines. To make mobile easy to read, prefer a one-column structure as the default, or use a hybrid/fluid layout combined with media queries that have been tested on the target client group. Do not rely entirely on CSS Grid to arrange columns if you need compatibility with classic Outlook.

## 6. CSS inlining: turning CSS classes into styles on each element

Writing all the inline CSS in the template up front gives compatibility but creates a lot of repetition. A common workflow is to **write a maintainable template first, and then inline the CSS in a processing step**:

1. Create the HTML template and define the classes in CSS.
2. Render the business data into the template using an appropriate escaping mechanism.
3. Use a **CSS inliner** tool to put the essential declarations into the `style` of the corresponding elements.
4. You can keep some `@media` rules in `<style>` as a responsive enhancement.
5. Send the processed HTML through Spring Mail.

~~~mermaid
flowchart LR
    A["HTML template + stylesheet"] --> B["Render data safely"]
    B --> C["CSS inliner"]
    C --> D["HTML with inline style"]
    D --> E["MimeMessageHelper"]
    E --> F["JavaMailSender / SMTP"]
    F --> G["Mail clients"]
~~~

### 6.1. Example before and after inlining

**Before processing:**

~~~html
<style>
  .card-title {
    color: #172554;
    font-size: 24px;
    line-height: 30px;
    font-family: Arial, sans-serif;
  }
  .description {
    color: #334155;
    font-size: 16px;
    line-height: 24px;
  }
</style>

<h1 class="card-title">Weekly report</h1>
<p class="description">The report was generated successfully.</p>
~~~

**After inlining CSS:**

~~~html
<h1 class="card-title"
    style="color:#172554; font-size:24px; line-height:30px;
           font-family:Arial,sans-serif;">
  Weekly report
</h1>
<p class="description"
   style="color:#334155; font-size:16px; line-height:24px;">
  The report was generated successfully.
</p>
~~~

A CSS inliner must take into account the **cascade**, specificity, inheritance, `!important`, declaration order, and any existing inline styles. Blindly copying all the declarations can get the CSS priority wrong. Therefore, choosing an appropriate HTML email processing tool and checking the **output after the transform** is necessary.

### 6.2. Not every rule can go into style=""

~~~css
@media screen and (max-width: 600px) {
  .content { padding: 16px !important; }
}

.button:hover {
  background-color: #1e40af;
}
~~~

`@media` depends on viewport conditions; `:hover` depends on interaction state. They are **not equivalent to a static style** at all times. An inliner tool may keep, drop, or handle these rules separately depending on its configuration. For email, treat them as supplementary, not as a condition for the main content to be readable.

### 6.3. JavaMailSender does not inline CSS automatically

~~~java
helper.setText(html, true);
mailSender.send(message);
~~~

`setText(..., true)` only marks the content part as **HTML**. `MimeMessageHelper` and `JavaMailSender` **do not automatically turn the entire `<style>` or an external stylesheet into inline CSS**. If you need automatic inlining, there must be a processing step before the `setText` call, or you must use a template that already has inline styles.

Similarly, a template engine such as Thymeleaf helps render data into HTML; **template rendering and CSS inlining are two steps with different responsibilities**, unless the project's own pipeline deliberately integrates an inliner as well.

## 7. Responsive email when media queries are unreliable

For a web page, responsive layout usually relies on CSS `@media`. In email, the level of media query support changes by mail client. So a practical strategy is **mobile-friendly by default**, then adding media queries as an enhancement.

Example:

~~~html
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    @media screen and (max-width: 600px) {
      .mobile-padding {
        padding-left: 16px !important;
        padding-right: 16px !important;
      }
      .mobile-full {
        width: 100% !important;
        display: block !important;
      }
    }
  </style>
</head>
<body>
  <table role="presentation" width="100%"
         cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td class="mobile-padding"
          style="padding:24px; font-family:Arial,sans-serif;">
        Content must be readable even when the media query is dropped.
      </td>
    </tr>
  </table>
</body>
~~~

`<meta name="viewport">` helps many mobile clients handle width, but not every email client keeps/honors it. `@media` can change padding on a narrow screen, but the **base style** must still be easy to read. Do not set the font size too small and then expect the media query to always increase it.

### 7.1. Responsive principles with fallbacks

- Set a container with a reasonable maximum width and allow shrinking on narrow screens when the renderer supports it.
- Prefer one column for the main content; limit multi-column layouts with long text.
- Use a font around 16px for body text as a readable starting point, then adjust according to design and testing.
- Create CTAs with enough padding to be tapped on touch screens.
- Use images with an appropriate `width` and `style="max-width:100%; height:auto;"` when the client supports it; have a fallback based on the design dimensions.
- Avoid overly long unbroken strings such as raw URLs in narrow areas; put links behind a text label instead of printing the whole URL.
- Ensure the email remains reasonable when media queries are stripped.

### 7.2. The hybrid/fluid technique

**Hybrid email** combines flexible layouts, size limits, and (when needed) fallbacks for older renderers so that an email does not depend completely on media queries. For example, you can use an outer 100%-wide table, an inner container with `max-width`, and then consider conditional tables for classic Outlook.

This is a layout strategy, not a single CSS property. Good compatibility depends on **the entire markup, cell order, fallbacks, and the target clients**; you cannot just add `max-width` and claim the email will be responsive on every app.

## 8. Dark mode: inline colors can still be changed

Many mail clients support dark mode and may:

1. Keep the inline colors unchanged.
2. Partially change background/text colors.
3. Invert or transform colors according to the client's algorithm.
4. Apply certain changes only to specific header/body sections.

Therefore, `style="background-color:#ffffff; color:#111827;"` **does not guarantee** the background will always be white and the text always dark.

Points to follow:

- Choose colors with good contrast in both light and dark contexts.
- If a logo has a transparent background, check whether it is still clear on a dark background; sometimes a logo variant or an appropriate light/dark border is needed.
- Avoid text inside images when possible, so that text remains readable when images are blocked.
- Do not rely on a background image as the sole source of contrast for text.
- Check CTAs and links in light/dark mode on representative clients.
- You can add support hints such as `color-scheme`, `supported-color-schemes`, or `@media (prefers-color-scheme: dark)` when clients support them, but treat them as enhancements and test on each client group.

Example of a supplementary rule:

~~~css
@media (prefers-color-scheme: dark) {
  .surface {
    background-color: #111827 !important;
    color: #f9fafb !important;
  }
}
~~~

This rule does not replace inline CSS, and not every client keeps or honors `prefers-color-scheme`. Some clients adjust colors independently of media queries; the design must still accept different rendering behaviors.

## 9. HTML email template with inline CSS for business notifications

The following self-contained example uses a table layout, inline styles, fallback fonts, and a text link button. These elements are chosen to reduce dependence on JavaScript, external images, or complex CSS selectors.

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Weekly report is ready</title>
</head>
<body style="margin:0; padding:0; background-color:#f1f5f9;">
  <table role="presentation" width="100%" cellpadding="0"
         cellspacing="0" border="0"
         style="width:100%; border-collapse:collapse;
                background-color:#f1f5f9;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="100%" cellpadding="0"
               cellspacing="0" border="0"
               style="width:100%; max-width:600px;
                      border-collapse:collapse;
                      background-color:#ffffff;">
          <tr>
            <td bgcolor="#ffffff"
                style="padding:32px 28px; background-color:#ffffff;">
              <h1 style="margin:0 0 16px; color:#0f172a;
                         font-family:Arial,Helvetica,sans-serif;
                         font-size:24px; line-height:30px;
                         font-weight:700;">
                Weekly report is ready
              </h1>
              <p style="margin:0 0 18px; color:#334155;
                        font-family:Arial,Helvetica,sans-serif;
                        font-size:16px; line-height:24px;">
                You can open the latest report from the link below.
              </p>
              <table role="presentation" cellpadding="0"
                     cellspacing="0" border="0">
                <tr>
                  <td bgcolor="#1d4ed8" align="center"
                      style="background-color:#1d4ed8;
                             padding:14px 22px;">
                    <a href="https://example.com/reports"
                       style="color:#ffffff; text-decoration:none;
                              font-family:Arial,Helvetica,sans-serif;
                              font-size:16px; line-height:20px;
                              font-weight:700; display:inline-block;">
                      View report
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:20px 0 0; color:#475569;
                        font-family:Arial,Helvetica,sans-serif;
                        font-size:14px; line-height:21px;">
                If the button does not work, open the reports page
                from your application.
              </p>
            </td>
          </tr>
          <tr>
            <td bgcolor="#e2e8f0"
                style="padding:16px 28px; background-color:#e2e8f0;
                       color:#334155; font-family:Arial,sans-serif;
                       font-size:12px; line-height:18px;">
              This is an automated system notification.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
~~~

**Design decisions in the example:**

- Uses `table` with `role="presentation"` for layout. Does not use CSS Grid/Flexbox.
- Essential colors, fonts, padding, and line-height are directly in `style`.
- `bgcolor` on some `td`s acts as a fallback alongside `background-color`.
- The CTA button is a real `<a>` link with meaningful text.
- Does not rely on images to convey “Weekly report is ready”.
- Sets `width:100%; max-width:600px` for the content frame, which may need a separate fallback for classic Outlook.
- The link is a sample URL. In a real application, the URL must be taken from trusted configuration or business logic and only permitted domains may be used.

**Limitations of the template:** This is a starting point for an email that reads well, not a pixel-perfect guarantee across every client. Some older Outlook versions may handle width, buttons, and margins differently; dark mode may change colors; mobile app versions may reflow content. If a CTA needs special display capability in classic Outlook, you can consider a button approach with a VML fallback, though that solution needs dedicated design and testing for the actual client set.

### 9.1. Why not put the entire CTA in an image?

If the CTA is only an image with the text “View report”, when the image is not loaded, the user may lose the primary action completely. An `<a>` containing meaningful text can still be clicked when styles are restricted. If an image is purely decorative, keep important actions and content as HTML text.

### 9.2. Image width should be considered

If the email adds a logo:

~~~html
<img src="https://static.example.com/mail/logo.png"
     width="160" height="48"
     alt="Service logo"
     style="display:block; width:160px; max-width:100%;
            height:auto; border:0;">
~~~

The reason for declaring `width` and `height` is to provide expected dimensions, limiting layout shift in compliant clients. `style="max-width:100%; height:auto;"` helps prevent the image from exceeding the frame in supporting clients. However, many clients **block loading remote images**; using `alt` cannot replace all image content. The URL `https://static.example.com/...` is only an example address, not a resource that must be reachable for the lesson to work.

## 10. Creating and sending HTML with inline CSS using Spring Framework Mail

Spring Mail **does not render CSS and does not check whether a client supports a given property**. It takes the prepared HTML string, sets the right MIME content type, and sends it through the transport.

### 10.1. Example service sending HTML and plain text

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportEmailService {

    private final JavaMailSender mailSender;

    public ReportEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReportNotice(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Weekly report is ready");

        String plainText = "Weekly report is ready. "
                + "Open https://example.com/reports to view.";

        String html = """
                <!doctype html>
                <html lang="en">
                <body style="margin:0; padding:0;">
                  <table role="presentation" width="100%"
                         cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="padding:24px; font-family:Arial,sans-serif;
                                 color:#1f2937; font-size:16px;
                                 line-height:24px;">
                        <h1 style="font-size:24px; line-height:30px;
                                   margin:0 0 16px;">
                          Weekly report is ready
                        </h1>
                        <p style="margin:0 0 20px;">
                          You can view the latest report.
                        </p>
                        <a href="https://example.com/reports"
                           style="color:#ffffff; background-color:#1d4ed8;
                                  padding:12px 20px; text-decoration:none;">
                          View report
                        </a>
                      </td>
                    </tr>
                  </table>
                </body>
                </html>
                """;

        // Two content versions: text/plain and text/html.
        helper.setText(plainText, html);

        mailSender.send(message);
    }
}
~~~

The example uses Java text blocks (Java 15 and later; Spring Framework 6 requires Java 17). This is illustrative code creating **static and trusted** content; in a real system, paths, sender addresses, and content must come from controlled configuration/business logic.

Points to understand:

1. `mailSender.createMimeMessage()` creates the MIME message, **without sending it yet**.
2. `new MimeMessageHelper(message, true, "UTF-8")` enables multipart capability and selects UTF-8.
3. `helper.setText(plainText, html)` creates **two alternative versions of the same content**, allowing the client to use `text/plain` when it does not display HTML.
4. In `html`, important display styles have already been placed inline.
5. `mailSender.send(message)` performs the send via Jakarta Mail/SMTP with the system's configuration.

If sending only a single HTML body, the helper also supports:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
helper.setFrom("reports@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Notification");
helper.setText("<p style=\"color:#1f2937;\">Hello!</p>", true);
mailSender.send(message);
~~~

In `setText(html, true)`, the `true` parameter specifies an **HTML body**. It does not automatically add a plain-text part. Meanwhile, `true` in the constructor `MimeMessageHelper(message, true, "UTF-8")` is the **flag enabling multipart**. The two `true` positions have different meanings.

### 10.2. At which step should CSS be inlined?

An email-sending pipeline with templates can be organized as:

~~~text
Business logic determines recipient / content
             |
             v
Template engine renders safely escaped data
             |
             v
CSS inliner turns essential rules into style=""
             |
             v
Create equivalent text/plain version
             |
             v
MimeMessageHelper.setText(plainText, htmlWithInlineCss)
             |
             v
JavaMailSender.send(message)
~~~

Placing inlining **before calling `setText`** makes it clear that JavaMailSender receives **already processed HTML**. An inliner tool should not blindly run on uncontrolled user content; the render/escape step must follow the template's data contract.

If the template is pre-built into an HTML resource with CSS already inlined, the runtime can also just read that template and render the appropriate dynamic variables. Which approach to choose depends on whether the system needs to update templates via deployment or via a data store, but it must consistently preserve the order **render → inline → MIME → send** or an explicitly designed equivalent order.

### 10.3. Inline CSS and MIME charset are two different issues

An email part may carry:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

`charset=UTF-8` describes how characters are decoded; `Content-Transfer-Encoding` describes how bytes are represented in transit. Inline CSS is content inside the HTML:

~~~html
<p style="font-size:16px; color:#1f2937;">Hello!</p>
~~~

If Vietnamese text has garbled characters, check the charset, transfer encoding, and input data. If the text is correct but the layout is misaligned, check CSS, HTML, and the mail client. Changing the encoding of `MimeMessageHelper` will **not** make Outlook support CSS Grid.

## 11. Inline CID images, external images, and CSS

In HTML email, there are two common groups of images:

**Images loaded from a URL:**

~~~html
<img src="https://static.example.com/mail/banner.png"
     width="560" alt="Report information"
     style="display:block; width:100%; max-width:560px;
            height:auto; border:0;">
~~~

This type of image can be blocked from loading or accessed via a proxy by the mail client. That is not necessarily an HTML or CSS bug.

**Images attached inline and referenced by Content-ID:**

~~~html
<img src="cid:report-logo"
     width="160" alt="Report logo"
     style="display:block; width:160px; max-width:100%;
            height:auto; border:0;">
~~~

With Spring Mail, you can create an image MIME part with the corresponding ID:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom("reports@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Notification with logo");

String html = "<p style=\"font-family:Arial,sans-serif;\">"
        + "The report is ready.</p>"
        + "<img src=\"cid:report-logo\" alt=\"Report logo\""
        + " width=\"160\" style=\"display:block;width:160px;\">";

// Set the HTML before adding inline resources.
helper.setText("The report is ready.", html);
helper.addInline("report-logo", logoResource, "image/png");

mailSender.send(message);
~~~

The snippet assumes there is a `logoResource` of type `org.springframework.core.io.Resource` containing a valid, readable PNG image. `cid:report-logo` in the HTML must correspond to `Content-ID: <report-logo>` on the MIME image part; `MimeMessageHelper.addInline(...)` helps create that link.

**Limitations:** CID images may be displayed differently by mail clients, or even listed as attachments in some circumstances. Inline CSS cannot by itself fix mismatched IDs, broken MIME content, or image-blocking policies. When diagnosing, inspect `multipart/related`, `Content-ID`, and the actual received email.

## 12. Differences to pay attention to by mail client

### 12.1. Gmail: has CSS but still has an HTML filtering step

Gmail can display inline CSS and supports CSS rules in `<style>` in many situations. However, Gmail can also reprocess HTML, strip disallowed attributes, and apply its own rules to certain kinds of content.

Therefore:

- Do not depend on Gmail loading `<link rel="stylesheet">` from the Internet.
- Do not place essential styles only in complex selectors or rules outside the message.
- Check the content **inside an actual Gmail inbox**, not just a browser preview.
- Consider the HTML email size. Gmail may clip displayed content for large HTML emails; this also affects styles/elements near the end of the message.
- Do not assume the rendering capability of Gmail web and every Gmail mobile app is identical.

Truncated content or a transformed stylesheet can make the design look very different from the preview even though SMTP accepted the message.

### 12.2. Classic Outlook: need to distinguish the Word engine

For many versions of classic Outlook on Windows:

- Table structures and explicit dimensions are usually more reliable than CSS flex/grid.
- Margin, padding, or background properties may be handled differently from browsers.
- `border-radius` and background images may lack support or need fallbacks.
- CTA buttons may not have the right shape if relying only on CSS of the `<a>` tag.
- Conditional MSO markup or VML can be used in templates that require a dedicated Outlook UI, though it increases maintenance cost.

Note that **new Outlook and Outlook on the web do not necessarily use the same Word renderer**. When reporting a bug, identify the **version name and platform** rather than just writing generically “Outlook bug”.

### 12.3. Apple Mail: better CSS support does not mean identical to a browser

Apple Mail usually renders modern CSS better than many other clients, but:

- Dark mode can cause colors to change.
- Mail Privacy Protection or remote content loading policies affect how images are loaded and how metrics are measured.
- Web fonts, media queries, or CSS effects should not be the sole condition for understanding the message.
- Results in Apple Mail do not prove the HTML is compatible with classic Outlook.

### 12.4. Mobile mail clients: one email must handle many viewports

Users may open emails in apps, webviews, split view, or narrow windows. Even when desktop looks good, elements with fixed `width="600"`, unbreakable URLs, or overly large images can overflow the screen. Mobile-friendly design must be considered from **content readability** first and then graphic arrangement.

## 13. Distinguishing CSS errors, MIME errors, and resource-loading errors

Not every email that displays incorrectly is caused by CSS. When diagnosing, distinguish:

| Symptom | Where to look | How to handle |
| --- | --- | --- |
| The recipient sees `<p>Hello</p>` verbatim | `Content-Type` of the MIME body | Use `setText(html, true)` or `setText(plain, html)` appropriately |
| The text “Sent” becomes garbled characters | `charset`/transfer encoding and source data | Check UTF-8, MIME parts, and duplicate encoding |
| HTML has content but loses font size/color | Inline styles, `<style>`, and how the client filters CSS | Inline essential declarations |
| Two columns stack or misalign in Outlook | CSS flex/grid, table structure | Use suitable table/hybrid fallbacks |
| Logo does not display | Image URL blocked or `cid:` does not match `Content-ID` | Distinguish remote images from MIME inline images |
| CTA button loses color but the link remains | CSS background/border on `<a>`/`td` | Use cell background as fallback, check in Outlook |
| Colors are inverted in dark mode | Mail client's color transformation | Check contrast, logo, and fallbacks |
| Font differs from mockup | Font missing, web font failed to load | Use fallback system fonts |
| HTML is clipped at the end | Content size or client display mechanism | Reduce redundant markup, inline selectively |
| Email has HTML but only displays text | `multipart/alternative`, part order, or client settings | Check the MIME tree and HTML display capability |
| Email “failed to send” | SMTP AUTH/TLS/recipient/data | Analyze exceptions and SMTP responses, don't just fix CSS |

### 13.1. How to gather evidence

If a recipient reports an email display issue:

1. Record the affected mail client, platform, version, dark mode setting, and device.
2. Obtain the **Show original / View source / Download original (.eml)** copy of the actually received email if permitted.
3. Identify `Content-Type`, the `text/html` and `text/plain` parts, and the multipart relationship.
4. Read the HTML part after decoding transfer encoding, and check whether the actual styles are in the `style` attribute.
5. Check whether styles were stripped by the client, and compare with the HTML before sending.
6. Check whether external images were blocked or a CID part is broken.
7. If the MIME/HTML is correct and only one client is wrong, focus on that client's renderer.

A screenshot only shows the *symptom*. The `.eml` file and MIME headers show the **actual content** received; combining both kinds of data helps distinguish errors at the template creation, inlining, MIME, and display-application steps.

### 13.2. Inspecting a Spring-created message before sending

When you need to observe the MIME in a test environment, `MimeMessage` can be serialized:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("reports@example.com");
helper.setTo("test@example.net");
helper.setSubject("Preview");
helper.setText("Text version.", "<p style=\"color:#1f2937;\">HTML version.</p>");

message.saveChanges();
try (java.io.OutputStream output = java.nio.file.Files.newOutputStream(
        java.nio.file.Path.of("preview.eml"))) {
    message.writeTo(output);
}
~~~

The snippet assumes it is placed in a method that handles/declares `MessagingException` and `IOException`. It only creates the file `preview.eml`, and **does not send the email** because `mailSender.send(message)` has not been called. Use fake data, save to a permitted location, and do not expose message content containing sensitive information.

## 14. Security when building HTML email and inline CSS

HTML email is data sent to the recipient's software, so two issues must be distinguished:

**Recipient-side protection:** clients usually filter dangerous elements, but the application must not rely on that filter to process untrusted input. Do not try to insert JavaScript, event handlers, or interactive embeds requiring inappropriate privileges.

**Sending-system protection:** if the email content contains user names, product codes, URLs, or dynamic notifications, you must escape values according to the HTML text or HTML attribute **context**. Do not concatenate uncontrolled data directly into HTML/CSS structures.

Unsafe example:

~~~java
String html = "<p>Hello " + userDisplayName + "</p>";
~~~

If `userDisplayName` contains `<`, `>`, quotes, or an HTML snippet, the content may be interpreted as markup. Use a template engine with default escaping for text, or a reliable HTML escape function before inserting data into the appropriate context. Text escaping is different from safety control of **URL** or **CSS** values.

Essential principles:

- Only build links to domains/paths permitted by the application; do not construct `href` from arbitrary URLs provided by untrusted users.
- Do not embed long-lived access tokens or secret data directly into email URLs.
- Do not use CSS as a way to hide important content or deceive the recipient.
- Do not let users arbitrarily supply raw HTML/CSS unless the business requires it. If so, a properly maintained whitelist-based content sanitizer is needed.
- Do not treat a **CSS inliner** tool as an **HTML sanitizer** tool. Inlining and content safety checking are two different steps.
- For images/attachments, control the data source, file type, and size before sending.

## 15. Process for testing HTML email UI

Because support for every client cannot be inferred from a single browser, testing needs to cover the system's **real customer base**. It can be organized into levels:

### Level 1 — Preview templates in the development environment

- Render the template with sample data: Vietnamese text, long strings, monetary amounts, lists with many items, and empty fields.
- Check basic content, reading order, and links.
- Check the HTML after the CSS inlining step, not just the source template.

Previewing in Chrome/Firefox is only valuable at this stage; it **does not replace** mail client testing.

### Level 2 — Send via an SMTP sink or test mailbox

- Use an isolated SMTP sink such as Mailpit/MailHog locally to view the generated email.
- Check the `text/plain` and `text/html` MIME parts, UTF-8 encoding, and inline resources.
- Open the raw `.eml` to confirm essential CSS has been inlined.
- Do not use real customer addresses for content tests.

### Level 3 — Test on target clients

Example test matrix:

| Platform | Things to check |
| --- | --- |
| Gmail on the web | Inline styles, spacing, links, external images, clipping |
| Gmail on mobile | Width, fonts, CTA tappability, images |
| Classic Outlook Windows | Table widths, cell padding, buttons, images, MSO fallback |
| New Outlook/web | Layout compared to classic Outlook, dark mode, and images |
| Apple Mail macOS/iOS | Responsive, fonts, dark mode, images |
| Other clients with high user share | Specific features that the customer group needs |

It is not necessary to support every client on the market. Identify the priority group, define acceptable UI differences, and ensure important functions (content, links, documents) work.

### Level 4 — Test degraded cases

Try:

- Turning off remote image loading.
- Using dark mode.
- Increasing font size via accessibility settings.
- Opening the message on a narrow screen.
- Viewing the plain-text version.
- Testing emails with long subjects/text and dynamic content with Vietnamese diacritics.
- Viewing forwarded messages, because forwarding systems may modify HTML/MIME.

**The goal is not pixel-perfect:** more importantly, the email is always readable, CTAs are clear, and numbers and links are not lost or misunderstood.

## 16. Frequently asked questions

**“Is inline CSS supported by every mail client?”**  
Inline CSS is generally one of the most compatible options for important styles, but support for **individual CSS properties** still varies. There is no guarantee that flex/grid/animation will work just because it was inlined.

**“Does Gmail support style tags?”**  
Gmail supports many CSS styles and can process `<style>` under certain conditions; one should not claim Gmail always removes all stylesheets. For essential formatting, inline CSS remains worth considering because the email is also opened in other clients.

**“Should Bootstrap be used in email?”**  
Do not depend on a Bootstrap stylesheet from a CDN or website CSS/JavaScript components. You can borrow spacing and color ideas, but email needs an HTML layout and CSS designed/inlined specifically with appropriate fallbacks.

**“Why does HTML look good in a browser but break in Outlook?”**  
Classic Outlook may use the Microsoft Word renderer instead of a modern browser engine. Techniques like flex/grid or margins may not be supported as expected. You need to choose table layouts, fallbacks, and test on the exact version.

**“Does using Spring MimeMessageHelper automatically fix CSS issues?”**  
No. The helper builds the MIME message and marks the body `text/html`; it does not automatically convert web CSS into CSS compatible with all mail clients.

**“If images do not appear, is the inline CSS wrong?”**  
Not necessarily. The client may be blocking external images, the URL may have expired, `cid:`/`Content-ID` may not match, the MIME image part may be broken, or dark mode may make the image hard to see. Identify the image type and inspect the actual email.

**“Do we have to use @media for responsive email?”**  
You can, but do not depend on it completely. Use a base layout that is good enough for mobile and let media queries improve it where supported.

**“Does using inline CSS keep emails out of Spam?”**  
There is no such guaranteed relationship. Spam classification depends on many other factors such as sender domain authentication, sender reputation, content, recipient list, and provider policies. Inline CSS mainly serves **rendering display**.

**“Can plain-text emails have CSS?”**  
No. `text/plain` is plain text; CSS only has meaning when the mail client renders the HTML part. With `multipart/alternative`, the client can choose the plain or HTML version depending on capability/settings.

## 17. Takeaways for HTML email in Spring Framework Mail

A reliable pipeline should clearly separate responsibilities:

~~~text
Business data
   |
   v
Template render (escape data)
   |
   v
HTML + CSS designed for email
   |
   v
CSS inlining for essential styles
   |
   v
Plain-text alternative + HTML MIME part (UTF-8)
   |
   v
MimeMessageHelper / JavaMailSender
   |
   v
SMTP transport -> Mail client render
~~~

At the **template** layer, use inline styles with fallbacks, table structure when broad compatibility is needed, and ensure content stays clear when CSS/images are restricted. At the **Spring Mail** layer, use `MimeMessageHelper.setText(plain, html)` to create two content versions, set the appropriate charset, and do not confuse the MIME sending step with the CSS processing step. At the **display testing** layer, inspect the actual email on important clients, especially classic Outlook, Gmail, mobile, and dark mode.

Conclusion: **Inline CSS is a core technique to increase the reliability of HTML email UI, not an absolute compatibility switch**. Success comes from combining structured markup, simple CSS, reasonable fallbacks, accessible content, and testing on the exact mail clients the application needs to serve.
