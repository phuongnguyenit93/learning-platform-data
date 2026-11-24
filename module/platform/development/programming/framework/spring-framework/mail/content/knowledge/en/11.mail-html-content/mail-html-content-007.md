# Links, buttons, and readable content on small screens

## 1. The goal of HTML email on mobile devices

In **Spring Framework Mail**, an application can send HTML content using **JavaMailSender**, **MimeMessage**, and **MimeMessageHelper**. However, a successfully sent email is not necessarily easy to read on a phone. Narrow screens, user-adjusted font sizes, dark mode, blocked images, or differently supported HTML/CSS can all affect the experience.

An HTML email suited to small screens needs to meet three requirements:

1. **Immediately readable**: the main content is clear without having to zoom in or scroll horizontally.
2. **Accurate action tapping**: links and CTA buttons have easy-to-understand labels, a large enough touch target, and reasonable spacing.
3. **Fallback available**: if images are blocked, CSS is not applied, or the reader selects plain-text mode, the message remains complete.

For example, an order confirmation email may look nice on desktop but be difficult to use on a phone if it has a fixed 900 px layout, small 11 px font, and three buttons placed close together. The fix lies primarily in **HTML email design**, not in changing the SMTP host or changing the JavaMailSender type.

## 2. HTML email is not an ordinary web page

Email clients such as Gmail, Outlook, and Apple Mail handle HTML/CSS differently. Some strip scripts, forms, specific CSS, or alter markup structure. Therefore, do not copy an entire web page into an email and assume it will render as in a browser.

| Component | On a website | In HTML email |
|---|---|---|
| JavaScript | Usually can run | Usually blocked or stripped |
| Input forms | Broadly supported | Inconsistent support; should open the website to act |
| Flexbox/Grid | Usually works well | May be ignored or differ by client |
| Media queries | Common | Supported by many clients, though not all |
| External CSS | Usually loadable | Should not depend on external stylesheets |
| Webfonts | Commonly used | Need fallback system fonts |
| Images from URL | Browser loads with the page | Email client may block or proxy images |
| Buttons | May depend on script | Should use styled **a href** link tags |

The right strategy is **progressive enhancement**: the base layout stays readable with simple HTML and inline CSS; media queries only improve it when the client supports them.

## 3. Mobile-first layout: one column and flexible width

For transactional emails such as account confirmation, orders, or password resets, **one column** is usually easiest to read:

~~~text
Desktop (width-constrained content):

 +---------------------------------------+
 |                                       |
 |     +---------------------------+     |
 |     | Logo                      |     |
 |     |                           |     |
 |     | Heading                   |     |
 |     | Main content              |     |
 |     |                           |     |
 |     | [ View order ]            |     |
 |     |                           |     |
 |     | Fallback URL              |     |
 |     +---------------------------+     |
 |                                       |
 +---------------------------------------+

Mobile (content shrinks to screen):

 +--------------------+
 | Logo               |
 |                    |
 | Heading            |
 |                    |
 | Short content      |
 | wraps naturally    |
 |                    |
 | [ View order ]     |
 |                    |
 | Fallback link      |
 +--------------------+
~~~

**Practical tips:**

- The outer table uses **width="100%"** to make use of available space.
- The main content area can use **max-width around 560–640 px**; on mobile it still shrinks to the actual width.
- Leave **horizontal padding around 16–24 px** so text does not sit flush against the edge.
- Avoid multi-column tables containing lots of long data; on mobile you can switch to **label: value** pairs.
- Do not fix an image's width larger than the screen.
- Put important information and the primary action ahead of secondary details.

The dimension benchmarks are design guidelines, **not mandatory rules of Spring Mail**. They need to be adjusted to the content and tested on target email clients.

### Readable font sizes

| Content | Reference benchmark | Benefit |
|---|---|---|
| Body text | Font around **16 px** | Reduces the need to zoom on a phone |
| Line spacing | Line-height around **1.4–1.6** | Makes long paragraphs easy to read |
| Headings | Around **22–28 px** | Creates clear hierarchy |
| Text on CTA | Around **16 px** | Easier to recognize and tap |
| CTA padding | Around **12–14 px** top/bottom | Aims for a 44–48 px tall touch target |
| Paragraph spacing | Around **12–20 px** | Avoids overly dense content |

Do not shrink the font to cram more information into one email. Trim the content, break it into paragraphs, and prioritize what the recipient needs to know.

## 4. Links in email: clear destination, adequate spacing, and HTTPS

An email link must have a **real href**:

~~~html
<a href="https://example.com/orders">View order details</a>
~~~

The link label should describe the destination. Avoid vague phrases:

~~~html
<a href="https://example.com/orders">Click here</a>
~~~

If a user uses a screen reader to list links, the label **“View order details”** still provides context, whereas “Click here” does not.

A good link usually has:

1. **An absolute HTTPS URL**, without relative paths like **/orders/123**.
2. **An honest label**, not leading users to think they are visiting another domain.
3. **An underline or visual cue**, especially for links inside paragraphs.
4. **Space between links**, avoiding multiple touch targets too close together.
5. **A valid and controlled destination** owned by the application, not pointing arbitrarily based on user data.
6. **A readable fallback URL** if the operation is very important.

### Special characters in href

If a URL has two parameters, in HTML you need to escape the ampersand:

~~~html
<a href="https://example.com/orders?status=ready&amp;source=email">
  View confirmed order
</a>
~~~

**URL encoding** and **HTML escaping** are two different operations. When building dynamic URLs, encode URL components by position (path, query), then escape the entire string when placing it into an HTML attribute. Do not concatenate unvalidated input directly into the **href** attribute.

## 5. A CTA button should be a styled `a` tag

**CTA (Call To Action)** is the primary action: “Confirm email address”, “View invoice”, “Track order”, or “Open support page”.

In email, prefer an **a tag with href** rather than a button tag dependent on JavaScript or forms. Use inline CSS to create a button-like appearance:

~~~html
<a
  href="https://example.com/orders"
  style="
    display:inline-block;
    padding:14px 24px;
    background-color:#174ea6;
    color:#ffffff;
    font:700 16px/22px Arial,sans-serif;
    text-decoration:none;
    text-align:center;
    border-radius:6px;">
  View order
</a>
~~~

**Why not use button onclick?** Most email clients do not allow JavaScript to run. When the `a` tag has a real `href`, the navigation action remains meaningful even when CSS is simplified.

### Large touch targets on phones

A button with only small text and no padding is hard to tap with a finger. In the example, a 22 px line-height and 14 px vertical padding create a CTA area about 50 px tall in clients that apply CSS as expected. Practical targets are usually around **44–48 px or larger**, though results must be tested because email clients may ignore some properties.

With multiple actions, have **one prominent CTA** and less prominent secondary links; avoid placing many small buttons side by side on a narrow screen.

### Table-based buttons for higher compatibility

Some email clients render table layouts more reliably than modern CSS layouts:

~~~html
<table role="presentation" border="0" cellpadding="0" cellspacing="0">
  <tr>
    <td
      align="center"
      bgcolor="#174ea6"
      style="background-color:#174ea6;border-radius:6px;">
      <a
        href="https://example.com/orders"
        style="
          display:inline-block;
          padding:14px 24px;
          font:700 16px/22px Arial,sans-serif;
          color:#ffffff;
          text-decoration:none;
          border-radius:6px;">
        View order
      </a>
    </td>
  </tr>
</table>
~~~

**role="presentation"** indicates this is a layout table, not a data table. The **bgcolor** attribute supports some older clients, while inline styles preserve clearer presentation. However, some desktop Outlook versions do not handle all padding or border-radius on anchors like a browser; if strict support is needed, test separately and consider dedicated button techniques.

**No HTML button is guaranteed to display identically across all email clients**. What matters is that the label and href stay clear, clickable, and have a fallback link.

## 6. Primary button and fallback link

A transactional message should place the primary action right after a short description:

~~~text
Order confirmed

We have received your order information.

        [ View order ]

If the button does not work, open the link:
https://example.com/orders

Need support? https://example.com/support
~~~

A fallback link is useful when a client displays the button unexpectedly or the user wants to copy the URL. Even so, an overly long URL with sensitive tokens can be hard to read and easy to expose via forwarding; path design must take security into account.

For emails containing important actions, ensure **the message body explains on its own what happened and what the user needs to do**, rather than having only an image or a button with an unclear destination.

## 7. Complete one-column responsive HTML template

The following template has a heading, a descriptive paragraph, a CTA, a fallback link, and a footer. The base layout is a 100%-wide table; the media query only enhances the UI in supporting clients.

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Order confirmed</title>
  <style>
    @media screen and (max-width:480px) {
      .mobile-pad { padding:20px 16px !important; }
      .mobile-title { font-size:23px !important; }
      .mobile-cta { display:block !important; text-align:center !important; }
    }
  </style>
</head>
<body style="margin:0;padding:0;background-color:#f3f5f8;">
  <div
    style="
      display:none;
      font-size:1px;
      line-height:1px;
      max-height:0;
      max-width:0;
      opacity:0;
      overflow:hidden;">
    Your order has been recorded. View details now.
  </div>

  <table
    role="presentation"
    width="100%"
    cellpadding="0"
    cellspacing="0"
    border="0"
    style="width:100%;border-collapse:collapse;background:#f3f5f8;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table
          role="presentation"
          width="100%"
          cellpadding="0"
          cellspacing="0"
          border="0"
          style="width:100%;max-width:600px;background:#ffffff;">
          <tr>
            <td class="mobile-pad" style="padding:32px 28px 24px;">
              <p
                style="
                  margin:0 0 12px;
                  font:700 14px/1.5 Arial,sans-serif;
                  color:#174ea6;">
                ORDER NOTIFICATION
              </p>

              <h1
                class="mobile-title"
                style="
                  margin:0 0 18px;
                  font:700 26px/1.3 Arial,sans-serif;
                  color:#18212f;">
                Order confirmed
              </h1>

              <p
                style="
                  margin:0 0 22px;
                  font:16px/1.55 Arial,sans-serif;
                  color:#27364a;">
                Hello! We have recorded your order.
                You can view the status and delivery information
                on your account page.
              </p>

              <table
                role="presentation"
                border="0"
                cellpadding="0"
                cellspacing="0">
                <tr>
                  <td
                    align="center"
                    bgcolor="#174ea6"
                    style="background:#174ea6;border-radius:6px;">
                    <a
                      class="mobile-cta"
                      href="https://example.com/orders"
                      style="
                        display:inline-block;
                        padding:14px 24px;
                        font:700 16px/22px Arial,sans-serif;
                        color:#ffffff;
                        text-decoration:none;
                        border-radius:6px;">
                      View order
                    </a>
                  </td>
                </tr>
              </table>

              <p
                style="
                  margin:24px 0 6px;
                  font:14px/1.5 Arial,sans-serif;
                  color:#42546a;">
                If the button does not work, open the link:
              </p>
              <p
                style="
                  margin:0;
                  font:14px/1.5 Arial,sans-serif;
                  overflow-wrap:anywhere;">
                <a
                  href="https://example.com/orders"
                  style="color:#174ea6;text-decoration:underline;">
                  https://example.com/orders
                </a>
              </p>
            </td>
          </tr>
          <tr>
            <td
              style="
                padding:20px 28px;
                background:#f8fafc;
                border-top:1px solid #e5eaf0;">
              <p
                style="
                  margin:0;
                  font:14px/1.5 Arial,sans-serif;
                  color:#42546a;">
                Need support?
                <a
                  href="https://example.com/support"
                  style="color:#174ea6;text-decoration:underline;">
                  Contact support
                </a>.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
~~~

The **example.com** URLs in the template are examples, not real destinations. Colors, fonts, and contrast must be adjusted to the application's design.

### Why is the template readable on small screens?

Even when the media query is ignored, the outer and inner areas both use **width=100%**, content is organized in one column, the font is not too small, and the CTA is a link with a real href. When the media query is applied, padding and headings can adjust to take up less space.

In some desktop Outlook versions, **max-width** may not work as expected. You can add hybrid/fluid table techniques or Outlook-specific conditional markup if the user base requires it. However, avoid trading away mobile readability just to maintain an overly complex desktop layout.

## 8. Building HTML email with Spring Framework Mail

With Spring Boot, the common dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Example SMTP submission configuration over STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: account@example.com
    password: REPLACE_WITH_SECRET
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
~~~

The SMTP host and account must be replaced with real configuration. In production, **passwords need to come from environment variables or a secret manager**, without putting secrets into repositories or logs. The SMTP port and TLS mode must follow the provider's guidance.

**Spring Boot** can create the JavaMailSender bean when classpath and configuration are appropriate. **Spring Framework Mail** provides the API to build and send MIME. Meanwhile, whether an email is easy to read on a phone depends on the **HTML/template** itself.

### SimpleMailMessage or MimeMessage?

| Need | Common API |
|---|---|
| Plain-text-only email | **MailSender** + **SimpleMailMessage** |
| HTML email | **JavaMailSender** + **MimeMessageHelper** |
| Both plain text and HTML | **MimeMessageHelper.setText(plainText, htmlText)** |
| Inline images via CID | **MimeMessageHelper.addInline(...)** |
| File attachments | **MimeMessageHelper.addAttachment(...)** |

Because the email in this article has HTML and a styled CTA, using **MimeMessage** is the right choice.

## 9. Complete Java example: HTML + plain text with action URL

The service example below focuses on the email-building step. The HTML content is shorter than the template in section 7 while still preserving the one-column layout, inline CSS, and large CTA area.

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderEmailService {

    private final JavaMailSender mailSender;

    public OrderEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderAccepted(String recipient)
            throws MessagingException {
        String plainText = """
                Your order has been confirmed.

                We have recorded your order.
                View details: https://example.com/orders
                Support: https://example.com/support
                """;

        String htmlText = """
                <!doctype html>
                <html lang="en">
                  <head>
                    <meta charset="UTF-8">
                    <meta name="viewport"
                          content="width=device-width,initial-scale=1">
                  </head>
                  <body style="margin:0;padding:0;background:#f3f5f8;">
                    <table role="presentation" width="100%"
                           cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td align="center" style="padding:20px 12px;">
                          <table role="presentation" width="100%"
                                 cellpadding="0" cellspacing="0" border="0"
                                 style="max-width:600px;background:#ffffff;">
                            <tr>
                              <td style="padding:24px 20px;">
                                <h1 style="margin:0 0 16px;
                                           font:700 24px/1.3 Arial,sans-serif;">
                                  Order confirmed
                                </h1>
                                <p style="margin:0 0 22px;
                                          font:16px/1.5 Arial,sans-serif;">
                                  We have recorded your order.
                                </p>
                                <table role="presentation" border="0"
                                       cellpadding="0" cellspacing="0">
                                  <tr>
                                    <td bgcolor="#174ea6"
                                        style="background:#174ea6;">
                                      <a href="https://example.com/orders"
                                         style="display:inline-block;
                                                padding:14px 24px;
                                                font:700 16px/24px Arial,sans-serif;
                                                color:#fff;text-decoration:none;">
                                        View order
                                      </a>
                                    </td>
                                  </tr>
                                </table>
                                <p style="margin:22px 0 0;
                                          font:14px/1.5 Arial,sans-serif;">
                                  Or open:
                                  <a href="https://example.com/orders">
                                    https://example.com/orders
                                  </a>
                                </p>
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </body>
                </html>
                """;

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("orders@example.com");
        helper.setTo(recipient);
        helper.setSubject("Order confirmed");
        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }
}
~~~

This is illustrative code; the provider must allow the From address and the system needs a configured SMTP sender. The link is fixed so the lesson focuses on layout; in a real application, build **one business URL from trusted configuration** and render the same URL into both the HTML and plain-text versions.

### Steps to understand

1. **JavaMailSender** is injected into the service, usually from Spring Boot configuration.
2. **plainText** completely describes the content and the URL the recipient needs to open.
3. **htmlText** has a heading, paragraph, CTA, and fallback link.
4. **createMimeMessage()** creates the MIME object.
5. **MimeMessageHelper(..., true, UTF-8)** enables multipart and the appropriate encoding.
6. **setText(plainText, htmlText)** builds two alternative content representations.
7. **send(message)** submits the message to the SMTP transport.

**A successful send does not guarantee the email reached the Inbox or displayed perfectly in the email client**. You must distinguish mail delivery results from HTML quality on the recipient's side.

## 10. Plain-text version as a real fallback

When creating an HTML email with a CTA button, do not let the plain-text version say only “Please enable HTML to view”. Plain-text readers still need to know the content and have a copyable URL.

Example:

~~~text
Order confirmed

Hello!
We have recorded your order.

View details:
https://example.com/orders

Contact support:
https://example.com/support
~~~

In Spring Mail:

~~~java
helper.setText(plainText, htmlText);
~~~

This method differs from:

~~~java
helper.setText(htmlText, true);
~~~

The second overload marks a single body as HTML and **does not automatically create a complete plain-text version**. When both versions are present, the message usually contains **multipart/alternative**:

~~~text
MimeMessage
└── multipart/alternative
    ├── text/plain
    │    └── Full content and URL
    └── text/html
         └── Content and CTA <a href="...">
~~~

If inline images or attachments are also included, the structure may additionally nest **multipart/related** and **multipart/mixed**. The two plain-text/HTML versions are **two alternative expressions of the same message**, not two separate emails.

## 11. Template engines and dynamic data

When a message contains user names, order numbers, times, or personalized links, you should not copy long HTML into every Java service. You can use **Thymeleaf**, **FreeMarker**, or an equivalent email template rendering tool.

~~~text
Business event
      |
      v
Create validated notification data
      |
      +--> Plain text template --> plainText
      |
      +--> HTML template -------> htmlText
      |
      v
MimeMessageHelper.setText(plainText, htmlText)
      |
      v
JavaMailSender.send(message)
~~~

An HTML template can contain placeholders processed by the template engine:

~~~html
<h1>Order confirmed</h1>
<p>Hello, [RECIPIENT NAME]!</p>
<a
  href="[VALIDATED URL]"
  style="
    display:inline-block;
    padding:14px 24px;
    background-color:#174ea6;
    color:#fff;
    font:700 16px/24px Arial,sans-serif;
    text-decoration:none;">
  View order
</a>
~~~

The strings in square brackets are only illustrative placeholders, not Thymeleaf APIs. In real code, the engine replaces them with data from the model and escapes according to context.

**Separate two tasks:**

- **HTML escape** text and attributes so data containing angle brackets or quotes does not break markup.
- **Validate the URL** before rendering: allow only permitted domains/schemes, encode path/query properly, and do not accept malicious user-supplied links.

A template engine can assist with escaping, yet it does not turn an untrusted URL into a safe destination by itself. You need to verify business data and protect tokens in links.

### Keeping URLs consistent between both versions

If HTML uses a “View order” button pointing to a URL, the plain-text version must use **the same business URL**. Compute the URL once in a service or builder and render it into both templates to avoid drift when configuration changes.

## 12. Sensitive links and security

Emails containing account verification links, password resets, or access-controlled document links must be treated as part of the security workflow.

Fundamental principles:

- Use **HTTPS** and a trusted domain belonging to the application.
- Verify access rights on the server, not relying solely on the user possessing the URL.
- For verification/password-reset tokens, apply an expiration time, scope of effect, and the ability to revoke or invalidate when appropriate.
- Do not put tokens into unprotected logs or analytics tools.
- Avoid building links from an untrusted host taken directly from a request to reduce phishing or open redirects.
- Link labels must accurately reflect the action; do not impersonate another service's name.

### Email scanners may open links before the user does

Some email security gateways automatically visit URLs to check for malware/phishing. Therefore, **do not design an operation with serious consequences using just a GET when opening a link**.

Risky design example:

~~~text
GET /delete-account?token=...
    -> Immediately deletes the account without a confirmation step.
~~~

It is better to open an explanation page and then ask the user to confirm or authenticate as appropriate for the action. For one-click unsubscribe, there are separate standards and requirements; do not equate it with deleting an account or transferring money.

If the email has click tracking, understand how the provider rewrites URLs, the redirect steps, and what click counts mean. A visit may be generated by a scanner, not necessarily an active user action.

## 13. Accessibility and screen readers

An email that reads well on mobile also needs to suit users who increase font size or use assistive technology.

**Choices to prioritize:**

- Use meaningful headings, such as one clear **h1** for the main content.
- Declare **lang="en"** in HTML when appropriate.
- Buttons/links have accurately descriptive labels.
- Ensure **text and background contrast**; do not convey information solely through color.
- Important illustrations have **alt text**; decorative images can use empty alt depending on purpose.
- Tables used for layout have **role="presentation"**; tables holding real data still need meaningful structure.
- Keep a logical reading order even when CSS is ignored.
- Provide a complete **text/plain** version.

Example of a clearly labeled link:

~~~html
<a href="https://example.com/invoices">View your invoice</a>
~~~

Avoid buttons with only an icon or the word “Go” without context. If an important action is presented only inside an image, someone who cannot load images will not know what to do.

## 14. Dark mode and scalable images

Many mail apps support dark mode or adjust colors automatically. A situation can happen where a button's text color is changed while its background color is not, reducing contrast.

How to handle:

- Pick color pairs that are already easy to read in light mode.
- Check both light and dark modes in important clients.
- Do not put a logo with dark text on a dark background without a display solution.
- Do not rely completely on dark-mode media queries because support is inconsistent.

### Images must not overflow the email off screen

Inline logo image example:

~~~html
<img
  src="cid:brandLogo"
  alt="Brand logo"
  width="160"
  style="
    display:block;
    width:160px;
    max-width:100%;
    height:auto;
    border:0;">
~~~

Banner example:

~~~html
<img
  src="https://static.example.com/email/banner.png"
  alt="Program announcement"
  width="560"
  style="
    display:block;
    width:100%;
    max-width:560px;
    height:auto;
    border:0;">
~~~

Images with **max-width:100%** and **height:auto** are designed to scale to the container in supporting clients. Avoid images with a rigid width larger than the screen, while keeping main content in text because email clients may block image display.

In Spring Mail, using CID images requires building a suitable multipart MimeMessage and calling **MimeMessageHelper.addInline(...)** with a Content-ID matching the value after **cid:**. If using remote images, the URL must be accessible under the email client's policy. Both approaches need a fallback plan.

## 15. Subject, preheader, and content near the top

In a mail list on a phone, recipients often see only part of the sender name, the **Subject**, and the first few characters of the body (preheader). Therefore, the message must be clear right from the opening lines:

~~~text
Subject: Order confirmed
Preheader: View status and delivery information in your account.
~~~

A preheader is usually a hidden snippet at the top of the HTML. Example:

~~~html
<div
  style="
    display:none;
    max-height:0;
    max-width:0;
    opacity:0;
    overflow:hidden;">
  View status and delivery information in your account.
</div>
~~~

Some clients may not honor this hiding technique or may pick another snippet as the preview. A preheader is a **content-design technique**, not a feature guaranteed by Spring Mail. The Subject also should not try to create a false sense of urgency; it should accurately describe the event.

The primary CTA button should come after a brief explanation. Do not force recipients to scroll past multiple banners before learning what action the email wants them to take.

## 16. Long content and data tables on small screens

If an email contains many steps or many details, divide it in order:

~~~text
1. What happened?
2. What does the recipient need to do?
3. Action CTA/link
4. Detailed information
5. Contact support
~~~

For order details, a label–value format is usually easier to read than a multi-column table:

~~~text
Order: ORD-123
Status: Confirmed
Estimated date: 20/11/2026

[ View order ]
~~~

Avoid tables with 6–8 columns, multiple long URLs, or fixed wide images. Strings without spaces can break the layout; CSS **overflow-wrap:anywhere** can help in some clients though not all. If a displayed URL is too long, design an appropriate presentation and do not turn it into a shortened link of unclear origin.

## 17. Common mistakes when building mobile-friendly HTML email

| Symptom | Common cause | How to handle |
|---|---|---|
| Must scroll horizontally on mobile | Table/image has too large a rigid width | Use a one-column layout, 100% width, max-width where appropriate |
| Text is too small | 10–12 px font, dense content | Prefer around 16 px body text, break into paragraphs |
| Button is hard to tap | Missing padding, buttons too close together | Increase touch area, separate CTAs |
| Button does not work | Used button/form/onclick | Use a real HTTPS anchor href |
| Link opens the wrong page | Relative URL, wrong domain, or wrong redirect | Check absolute URL and destination |
| Plain-text version lacks URL | Sent only HTML or text says to enable HTML | Use setText(plainText, htmlText) and add a real URL |
| Outlook renders differently from Gmail | Different CSS support/rendering engines | Table layout, inline CSS, test on target clients |
| Dark mode is hard to read | Text/background colors change inconsistently | Check contrast and dark mode |
| Image overflows screen | Fixed width, missing max-width | Use scalable images and alt text |
| Logo does not appear | Remote image blocked, wrong CID, unsupported client | Text fallback and check URL/Content-ID |
| Long URL breaks layout | String without spaces | CSS line wrapping where supported, design readable links |
| Vietnamese characters garbled | Unsuitable charset or MIME encoding | Use UTF-8 through MimeMessageHelper |
| Email goes to Spam | Sending/receiving policies, domain/IP reputation, SPF/DKIM/DMARC | Investigate SMTP and receiving system, don't just edit CSS |

### HTML errors and mail-sending errors are not the same

**JavaMailSender.send(...)** may fail due to SMTP AUTH, TLS, DNS, timeout, policy, or rejected recipient. That is not a responsive HTML error. Conversely, if SMTP accepted the message yet a client shows tiny fonts or an ugly button, check the template and email client.

Some exceptions at the Spring Mail layer include **MailAuthenticationException**, **MailSendException**, and **MailPreparationException**. For MIME, **MessagingException** may occur when building the message. Inspect the specific cause before applying retries; resending will not fix an HTML template that renders poorly.

## 18. Testing process across multiple email clients

Before using an HTML template in production, send a test to an SMTP sandbox or test inbox and open it on target clients.

1. Confirm the **Subject**, preheader, and opening content are easy to understand.
2. Test reading on a narrow screen around **320–400 px**, on desktop, and with enlarged font sizes.
3. Test on the clients users actually use, such as Gmail, Outlook, or Apple Mail where applicable.
4. Turn off images to check alt text and fallback content.
5. View light and dark themes.
6. Tap every CTA/link: check touch targets, domain, final URL, access rights, and redirects.
7. Read the plain-text version: it must have complete content and action URLs.
8. Use long user names, long order numbers, Vietnamese characters, and long URLs to check line wrapping.
9. If needed, inspect raw MIME to confirm Content-Type, charset, and alternative parts.

A browser displaying HTML nicely is not enough to prove the email will render properly in every mail app. Testing on **real email clients or dedicated preview tools** is what catches significant differences.

Do not send test emails to production customers. If a raw message contains tokens, recipient emails, or private data, store and share it only within permitted boundaries.

## 19. Designing reusable templates

When an application has many email templates, you can split them into shared blocks:

~~~text
Business event
     |
     v
Notification model
     |
     v
Template renderer
     +--> Header / Logo
     +--> Main content
     +--> Link-style CTA
     +--> Fallback link
     +--> Footer
     |
     +--> Plain text alternative
     |
     v
MimeMessageHelper
     |
     v
JavaMailSender.send(...)
~~~

Each CTA block should receive a **validated URL** and a **clear label**; do not accept arbitrary markup from user requests. A template engine helps keep fonts, spacing, colors, and mobile behavior consistent across transactional and other notification emails.

For marketing emails, beyond design, you also need to manage recipient opt-in consent, unsubscribe mechanisms, and related operational policies. **MimeMessageHelper does not automatically handle subscriber list rules**.

## 20. Pre-send design checklist

| Group | Question to answer |
|---|---|
| Content | Does the reader understand the event within the first few lines? |
| Responsive | Is it readable on a small screen without horizontal scrolling? |
| Font | Is the text large enough and the line-height easy to read? |
| CTA | Wide touch target, clear label, one prominent primary action? |
| Links | Absolute HTTPS URL, right destination, right permissions, and not misleading? |
| Fallback | Is there a text link and a complete plain-text version? |
| Images | If images do not load, is the message still understandable? |
| Accessibility | Reasonable headings, alt text, contrast, and reading order? |
| Dark mode | Are text, buttons, and logos still clearly visible? |
| Dynamic data | Text/attributes escaped; URLs/tokens controlled? |
| MIME | Proper UTF-8, text/plain, and text/html? |
| Compatibility | Tested on the critical email clients? |

These are **HTML email design and operations** criteria, not a built-in automated check mechanism in Spring Framework Mail.

## 21. Summary

In **Spring Framework Mail**, sending HTML emails with links and CTAs is done with **JavaMailSender** and **MimeMessageHelper**. But for recipients to read and act on small screens, the content needs a **flexible one-column layout, readable typography, links that clearly describe their destination, CTA buttons built as `a` tags with real hrefs and large enough touch targets**, and fallbacks when CSS or images do not display.

Use simple layout tables and inline CSS as the foundation, add media queries when needed, and then test on critical email clients. When sending from Java, use **MimeMessageHelper.setText(plainText, htmlText)** to provide two equivalent content representations; control URLs and dynamic data, and do not depend on JavaScript or forms inside the email.

**An email looking good on desktop is not enough: a message is only truly useful when the recipient can understand it, find the right action, and perform the operation reliably on a phone.**
