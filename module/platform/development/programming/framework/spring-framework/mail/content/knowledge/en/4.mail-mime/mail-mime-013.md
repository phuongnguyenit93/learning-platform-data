# Inspecting the MIME tree when diagnosing misrendered emails

## 1. Why can an email have the right content yet render wrongly?

An email can send successfully over SMTP and be accepted by the recipient's server, yet when opened in an email app display problems such as:

- HTML content displays as literal `<p>`, `<table>`, and `<img>` tags.
- Users see only the text version even though the email was designed with HTML.
- A logo image in the body shows a broken image icon or gets listed as an attachment.
- Part of the body appears twice or the email looks like multiple different messages.
- A PDF file is missing from the attachment list, or gets embedded inside the content.
- Vietnamese characters turn into `Ã¡`, `=?UTF-8?...?=`, or unreadable character sequences.
- Some mail apps render properly, while another app renders differently.

In those cases, checking only the input HTML string or the SMTP reply code is not enough. You need to inspect the **MIME tree**: the hierarchical structure of *parts* that make up an email message. **MIME (Multipurpose Internet Mail Extensions)** defines how a message holds multiple content formats, alternative versions, embedded images, and attachments.

With **Spring Framework Mail**, calls such as `MimeMessageHelper.setText(...)`, `addInline(...)`, and `addAttachment(...)` ultimately become a MIME tree inside `jakarta.mail.internet.MimeMessage`. When the tree has inappropriate ordering, parent–child relationships, or headers, the recipient's email app may pick a different part to render than the sender intended.

> **Diagnostic principle:** Read the MIME tree to identify **which part is the primary body, which is an alternative version, which is an embedded resource, and which is an attachment**. Then inspect each part's headers and actual payload before concluding whether the bug lies in Spring Mail, the SMTP server, or the email client.

## 2. What is a MIME tree?

A MIME tree is a **recursive** representation of an email. The root of the tree is usually `MimeMessage`. A node can hold single content (*leaf part*) or multiple child nodes (*multipart container*).

Example of an email having plain text, HTML, a logo image used in HTML, and a PDF file:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/alternative
    │   ├── text/plain; charset=UTF-8
    │   └── multipart/related
    │       ├── text/html; charset=UTF-8
    │       │   (HTML references src="cid:logo-mail")
    │       └── image/png
    │           Content-ID: <logo-mail>
    │           Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="report.pdf"
~~~

How to read it:

1. `multipart/mixed` combines contents with different roles, such as the primary body and attachments.
2. `multipart/alternative` holds **alternative representations of the same content**, here plain text and an HTML version with images.
3. `multipart/related` groups HTML with dependent resources referenced by HTML, such as the `cid:logo-mail` image.
4. `text/plain` and `text/html` are two representations of the main message section.
5. `image/png` with `Content-ID` is a resource usable inside HTML; `application/pdf` with `attachment` is a file for the user to download.

This is **one reasonable structure**, not the sole shape of every valid email. Depending on the library and multipart organization, another email may also contain `multipart/mixed → multipart/related → multipart/alternative`, with the inline image as a sibling of `multipart/alternative` inside `related`. What must be verified are **container semantics, part placement, and reference headers**.

### 2.1. Content-Types to recognize

| `Content-Type` | Common role | What to check when misrendered |
| --- | --- | --- |
| `text/plain` | Plain text body | `charset`, actual content, position in `alternative` |
| `text/html` | HTML body | `charset`, valid HTML, relationship with `related` |
| `multipart/alternative` | Multiple equivalent versions of one content | Order of options; whether they are truly alternatives |
| `multipart/related` | Root body alongside dependent resources | Root part, `Content-ID`, `cid:` references, `start`/`type` if present |
| `multipart/mixed` | Combines body with independent parts like attachments | Whether attachments sit outside the body group properly |
| `image/png`, `image/jpeg` | Images, either inline or attachment | `Content-ID`, `Content-Disposition`, and bytes/encoding |
| `application/pdf` | PDF file | `Content-Disposition: attachment`, filename, type, and content |
| `message/rfc822` | Another email attached or nested inside the message | Subtree must be treated as a separate message |

`multipart/*` is a **container**: its `Content-Type` usually carries a `boundary` parameter to separate parts when serialized onto the wire. `text/*` and `application/*` are usually **leaves**. MIME can nest multiple levels, so you must traverse the tree rather than reading only the root `Content-Type`.

## 3. Three key containers: alternative, related, and mixed

### 3.1. multipart/alternative: choosing one suitable version

Example:

~~~text
multipart/alternative
├── text/plain; charset=UTF-8
│   "Weekly report is ready."
└── text/html; charset=UTF-8
    "<p>Weekly report is <strong>ready</strong>.</p>"
~~~

The two parts are **not two independent contents to display sequentially**. They are different choices representing the same information. Under standard MIME ordering, parts are ordered **from least rich to most preferred representation**; `text/plain` typically precedes `text/html`. The email client selects the last version it supports and is permitted to render, and may also apply its own policies.

A common mistake is:

~~~text
multipart/mixed
├── text/plain
└── text/html
~~~

If the goal is supplying two alternative versions, the structure above fails to express the *alternative* relationship. Some clients may render both parts, treat the HTML part as an attachment, or apply custom heuristics.

Another structure to watch out for:

~~~text
multipart/alternative
├── text/html
└── text/plain
~~~

This ordering conflicts with preferring HTML in many cases: clients following the rule of choosing the last supported version may pick `text/plain`, making the sender think “HTML disappeared”.

### 3.2. multipart/related: HTML and inline images must link properly

Suppose HTML contains:

~~~html
<p>Hello, here is the logo:</p>
<img src="cid:logo-mail" alt="Logo">
~~~

A workable structure:

~~~text
multipart/related
├── text/html
│   <img src="cid:logo-mail">
└── image/png
    Content-ID: <logo-mail>
    Content-Disposition: inline
~~~

`cid:logo-mail` in HTML references `Content-ID: <logo-mail>` on the image part. Angle brackets `<...>` are part of `Content-ID` header syntax; the string in `cid:` omits those brackets. In practice there may be long, address-like Content-IDs, yet both sides must match accurately per the linking rules.

When inspecting, check:

- Does the HTML part actually contain the intended `cid:...` reference?
- Is there a corresponding image part inside the same related content group?
- Was `Content-ID` assigned to the right image? Are there bracket mismatches, typos, or duplicate IDs?
- Is the image's `Content-Type` sensible, such as `image/png` for PNG?
- Can the image part be decoded, or were bytes corrupted during creation/transfer?
- Which part is the root of `multipart/related`? If a `start` parameter exists, does it point to the root's `Content-ID`?

In `multipart/related`, the root part is normally the first part when `start` is absent; if `start` is present, the part carrying the matching Content-ID is identified as root. The `type` parameter, if present, should reflect the root's MIME type. Do not rely solely on `Content-Disposition: inline` to decide which part is the main body.

### 3.3. multipart/mixed: attachments independent of the body

An email with a body and a PDF report usually has the tree:

~~~text
multipart/mixed
├── text/plain or a body multipart tree
└── application/pdf
    Content-Disposition: attachment; filename="report.pdf"
~~~

`mixed` expresses parts combined into one message. Mail readers normally find the body in the appropriate section and offer attachments as downloadable files.

If an attachment is placed inside `multipart/alternative` as an “alternative option” for the body:

~~~text
multipart/alternative
├── text/html
└── application/pdf
~~~

then the tree semantics are broken: the PDF is marked as an alternative version of the same content. Depending on the client, it may replace the body, make the body disappear, or render strangely. If the PDF is an independent attached file, group it with the body in `multipart/mixed` at the appropriate position.

## 4. How to read each part's headers?

Diagnosing a MIME tree is not based solely on node names. **Each part's** headers dictate how it is decoded and how mail applications view it.

| Header or parameter | Meaning | Error symptoms |
| --- | --- | --- |
| `Content-Type` | Content type; may include `charset` and `boundary` | HTML labeled as `text/plain`; multipart missing boundary or wrong boundary |
| `charset` | Character encoding of text content | UTF-8 mislabeled as ISO-8859-1, Vietnamese renders wrongly |
| `Content-Transfer-Encoding` | Wire representation of bytes, e.g., `base64`, `quoted-printable`, `7bit` | Part fails to decode properly, raw encoded string leaks |
| `Content-Disposition` | Presentation hint `inline` vs. `attachment` | Body treated as downloadable file, inline image listed as attachment |
| `Content-ID` | Identity of a part, commonly used with `cid:` | Image fails to match ID in HTML |
| `Content-Location` | Identifies resource by relative/absolute location in some messages | Client fails to resolve resource reference |
| `filename` / `name` | File name, usable in disposition/type | File appears unnamed or with garbled encoding |
| `boundary` | String separating members of a `multipart` | Parser fails to split parts properly |
| `MIME-Version` | Announces MIME structure, usually `1.0` at message level | Missing or unusual values can affect compatibility |

**Content-Type**, **Content-Transfer-Encoding**, and **charset** are three separate concepts. For example:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

means the payload after **quoted-printable decoding** must be interpreted as **HTML text with UTF-8 charset**. Applying them in the wrong order or assigning a charset mismatched with the original bytes turns text into garbage characters. Similarly, `base64` on a part does not automatically mean the content is an attachment; HTML text can also be transmitted in base64.

`Content-Disposition` is likewise a presentation signal, **not a mandatory command all email clients must obey identically**. Some clients decide rendering themselves based on MIME type, part position, filename, security policy, and other signals.

## 5. Reading a raw MIME message and reconstructing the tree

Suppose you obtain the original message in `.eml` format. The top headers might look like:

~~~text
From: Reports <reports@example.com>
To: lan@example.net
Subject: Weekly report
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mix-71"
~~~

The MIME body below is split by boundaries:

~~~text
--mix-71
Content-Type: multipart/alternative; boundary="alt-71"

--alt-71
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Weekly report is ready.
--alt-71
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<p>Weekly report is <strong>ready</strong>.</p>
--alt-71--
--mix-71
Content-Type: application/pdf; name="report.pdf"
Content-Disposition: attachment; filename="report.pdf"
Content-Transfer-Encoding: base64

[Base64 data omitted in example]
--mix-71--
~~~

This is a structural illustration; placeholder base64 has been omitted for readability, so it is not a complete `.eml` template for live sending.

Tree-reconstruction rules:

1. Read root `Content-Type`, identifying `multipart/mixed` and `boundary="mix-71"`.
2. Each `--mix-71` line starts a direct child part under root; `--mix-71--` closes that container.
3. The first part is `multipart/alternative` with its own boundary `alt-71`; descend inside.
4. Inside `alt-71`, `text/plain` and `text/html` are options for the same body.
5. Returning to `mix-71`, the next part is the PDF with `Content-Disposition: attachment`.

Do not search for `Content-Type: text/html` anywhere in text and conclude “the email has HTML so it must render HTML”. The part's location inside containers and how the client selects alternatives determine that.

### 5.1. Boundaries must match exactly

With the header:

~~~text
Content-Type: multipart/alternative; boundary="abc"
~~~

parts are separated by `--abc` and the container ends with `--abc--`. If a system concatenates MIME strings manually yet uses the wrong boundary name, drops hyphens, inserts unexpected data after the closing marker, or breaks CRLF borders, parsers may:

- Merge multiple parts into one;
- Treat child part headers as body text;
- Fail to find the HTML or attachment part;
- Report parse errors or ignore an invalid part.

With Spring Mail, the safe approach is letting `MimeMessageHelper`/Jakarta Mail construct MIME instead of concatenating boundary strings manually.

## 6. A repeatable diagnostic workflow

When receiving a report that “the email renders wrongly”, move from **the symptom** to **the actually received message**, avoiding blind HTML edits first.

### Step 1 — Record the symptom and the failing client

Gather enough context to reproduce:

- Which client hits the bug: Outlook desktop, Gmail web, a mobile mail app, or a custom reader?
- Does it fail on all clients or only one specific client?
- Only one email or every email sent from the same template?
- Is text, HTML, CID image, attachment, or font/character encoding broken?
- Did the email pass through forwarding, a mailing list, a gateway, a content scanner, or a mail security system?

Only when the same message is opened across different clients can you separate **MIME structure bugs** from rendering-software limits/policies.

### Step 2 — Capture the original received message

Prefer exporting **Show original / View source / Download original** as `.eml` from the mailbox or test inbox tool. Preserve full MIME headers and body; screenshots do not reveal boundaries or Content-IDs. If you need to compare changes along the pipeline, also save the `MimeMessage` right before calling `JavaMailSender.send(...)` in a test environment.

Email content can hold personal data, secrets, and URL tokens. Store only in diagnostic environments with proper access controls; mask or strip sensitive data before sharing logs/docs. Never rely on screenshots to deduce the tree.

### Step 3 — Inspect the MIME tree, not just root Content-Type

List depth-first:

~~~text
root: multipart/mixed
  0: multipart/related
    0.0: multipart/alternative
      0.0.0: text/plain
      0.0.1: text/html
    0.1: image/png [inline] Content-ID=<logo-mail>
  1: application/pdf [attachment] filename=report.pdf
~~~

Each node should record at minimum: **tree path, Content-Type, Content-Disposition, Content-ID, filename**, and when needed, size or encoding. There is no need to dump full bodies or attachment payloads to logs just to inspect structure.

### Step 4 — Identify the primary body and alternatives

First, locate `text/plain` and `text/html`. Two versions of the same content should have an appropriate `multipart/alternative` relationship. Verify:

- Are they inside the same `alternative` group?
- Does ordering allow clients to prefer HTML when supported?
- Is HTML labeled `text/html` or mislabeled `text/plain`?
- Was the plain version authored to be readable when HTML is disabled?
- Was the main body accidentally given `Content-Disposition: attachment`?

### Step 5 — Check image references and related resources

For every `src="cid:..."` in HTML, find the part with the matching `Content-ID` and verify whether it sits under the right `related` container. Check image content type, encoding, image data, and root/`start` if present. If HTML uses remote URLs, a client blocking Internet images is **not** a MIME tree bug; it is a remote-content loading policy.

### Step 6 — Check attachments and charset/encoding

If a file is mistaken for the body, verify whether it is properly organized in `multipart/mixed` with suitable disposition/filename. For Vietnamese character issues, compare raw bytes, `charset`, and `Content-Transfer-Encoding` of **that specific part**, not just top-level headers.

### Step 7 — Compare before and after transport

If the MIME built by the application is correct yet the recipient's `.eml` has a different structure, an intermediary system may have added disclaimers, scanned content, rewritten links/images, or re-packaged MIME. Compare versions at observable hops. If both versions are identical and only one mail client renders wrongly, investigate that client's HTML/CSS support, CID image support, and security policies.

## 7. Reading the MIME tree with Jakarta Mail in Java

In applications using **Spring Framework 6 / Jakarta Mail**, you can load an `.eml` message and walk containers recursively. The example below prints **structural metadata only**; it intentionally avoids reading text/HTML bodies or printing attachment bytes.

~~~java
package com.example.maildiagnostics;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

public final class MimeTreeInspector {

    private MimeTreeInspector() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: MimeTreeInspector <path-to-message.eml>");
        }

        Session session = Session.getInstance(new Properties());

        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            MimeMessage message = new MimeMessage(session, input);
            walk(message, "root", 0);
        }
    }

    private static void walk(Part part, String path, int depth)
            throws MessagingException, IOException {

        String indentation = "  ".repeat(depth);
        String disposition = part.getDisposition();
        String fileName = part.getFileName();
        String contentId = first(part.getHeader("Content-ID"));
        String transferEncoding =
                first(part.getHeader("Content-Transfer-Encoding"));

        // Use only on sample emails authorized for analysis.
        // Redact sensitive file names and Content-IDs when sharing results.
        System.out.printf(
                "%s%s type=%s, disposition=%s, filename=%s, cid=%s, cte=%s%n",
                indentation,
                path,
                part.getContentType(),
                disposition,
                fileName,
                contentId,
                transferEncoding);

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    walk(multipart.getBodyPart(i), path + "." + i, depth + 1);
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nestedMessage) {
                walk(nestedMessage, path + ".message", depth + 1);
            }
        }
    }

    private static String first(String[] headers) {
        return (headers == null || headers.length == 0)
                ? "-"
                : headers[0];
    }
}
~~~

Notable points:

- `MimeMessage` is the root message and is itself a `Part`; `Multipart` holds child body parts.
- `getContentType()` returns both the MIME type and parameters such as `boundary` or `charset`.
- `getDisposition()`, `getFileName()`, and `getHeader("Content-ID")` help identify the part's role.
- `part.isMimeType("multipart/*")` detects containers; `getContent()` then usually returns a `Multipart` iterable via `getBodyPart(i)`.
- `message/rfc822` is a nested message, so the example recurses when the decoded content is a `Message`.
- The example avoids calling `getContent()` on `text/html` or `application/pdf` leaves, avoiding reading bodies or attachments just to inspect structure.

The code assumes the message is parseable. On severely malformed MIME, `getContent()` may still throw exceptions or parsers may behave with varying tolerances; in such cases inspect the raw `.eml` and boundaries. Tree traversal can also trigger data reads/I/O to parse multiparts; do not assume it is free on huge emails. Bound source size and run diagnostics in an appropriate place.

**Version note:** Spring Framework 6 uses the `jakarta.mail.*` package. Legacy Spring applications may use `javax.mail.*`; do not mix the two package families in the same code.

### 7.1. Using the newly built MimeMessage right before sending

In Spring Mail, you can build a `MimeMessage` and inspect its structure in a test environment before calling `send(...)`:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("reports@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Weekly report");
helper.setText(
        "Weekly report is ready.",
        "<p>Weekly report is <strong>ready</strong>.</p>");

// After configuring the message, serialize it to
// observe the MIME structure in a test environment:
message.saveChanges();
try (OutputStream output = Files.newOutputStream(Path.of("sample.eml"))) {
    message.writeTo(output);
}

mailSender.send(message);
~~~

This snippet is placed where `mailSender` and required imports are available; inside a Java method you must import `java.io.OutputStream`, `java.nio.file.Files`, and `java.nio.file.Path`, and handle declared exceptions. Choose a controlled directory for test files and ensure sensitive email contents are not accidentally written to public folders.

The message serialized **before sending** reveals which parts Spring/Jakarta Mail constructed. The version **actually received by the recipient** still needs separate inspection because mail infrastructure can add or alter headers/bodies during processing.

## 8. Building the right MIME tree with MimeMessageHelper

Suppose you need to send a notification containing two body versions, an inline logo, and a PDF report file. With Spring Framework Mail, instead of creating boundaries manually, use `MimeMessageHelper`:

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WeeklyReportMailer {

    private final JavaMailSender mailSender;

    public WeeklyReportMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient, Resource logoPng, Resource reportPdf)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Weekly report");

        // Provide two alternative versions of the same body.
        helper.setText(
                "Weekly report is ready. See the attached PDF file.",
                "<p>Weekly report is ready.</p>"
                        + "<img src=\"cid:weekly-logo\" alt=\"Logo\">"
                        + "<p>See the attached PDF file.</p>");

        // Declare inline after setText so the HTML part already exists.
        helper.addInline("weekly-logo", logoPng, "image/png");

        // PDF file is an attachment independent of the body.
        helper.addAttachment("report.pdf", reportPdf);

        mailSender.send(message);
    }
}
~~~

Here the `Resource`s for logo and PDF must point to readable content (and satisfy the library's re-readability requirements when needed); calling code must verify permissions, file types, sizes, and data sources. The `addInline` call uses Content-ID `weekly-logo`; HTML must write `src="cid:weekly-logo"`. **The order `setText(...)` before `addInline(...)`** matters for how `MimeMessageHelper` organizes body parts.

When choosing `MULTIPART_MODE_MIXED_RELATED`, Spring typically organizes body/image/attachment as:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   └── image/png
    │       Content-ID: <weekly-logo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="report.pdf"
~~~

This is the **typical shape** of the chosen mode, separating body and attachments. The exact tree depends on helper operations, versions, and serialization; to know what real mail was produced, still inspect the `MimeMessage`.

Other multipart modes can generate different structures:

| `MimeMessageHelper` mode | Structural idea | When to pay attention |
| --- | --- | --- |
| `MULTIPART_MODE_NO` | Does not build multipart structure for inline/attachments | Use for simple messages needing no multipart |
| `MULTIPART_MODE_MIXED` | One `multipart/mixed` container | Some clients may behave differently when rendering inline resources |
| `MULTIPART_MODE_RELATED` | One `multipart/related` container | How clients interpret attachments may vary |
| `MULTIPART_MODE_MIXED_RELATED` | Outer `mixed` and inner `related` for body/resources | Usually appropriate when having both inline images and attachments |

Mode selection must be driven by the content to send and target client compatibility; do not switch modes merely to make the tree look “shorter”.

## 9. Diagnostic table: symptom → where to look in the tree

| Symptom | MIME clue to check | Likely appropriate fix |
| --- | --- | --- |
| Raw `<html>`, `<p>` tags visible | HTML body labeled as `text/plain`; HTML part not on chosen branch | Produce proper `text/html`, use `setText(html, true)` or plain+HTML overload |
| Only plain version visible | `multipart/alternative` missing HTML or HTML in wrong order; client avoids HTML | Build proper alternative, check client policy and HTML capability |
| Body repeated twice | Plain and HTML are siblings in `multipart/mixed` instead of `alternative` | Put both versions of the same content inside `multipart/alternative` |
| HTML treated as attachment | `Content-Disposition: attachment` on HTML; body in wrong place | Fix disposition and body grouping |
| Logo shows broken image | `cid:` mismatches `Content-ID`, missing inline part, wrong content type or bytes | Fix reference and image part; inspect `related` |
| Inline image shows in file list | Image not in proper related group, confusing disposition/filename headers | Use suitable multipart mode; verify on target clients |
| PDF disappears | Attachment placed in `alternative`, missing disposition, broken multipart/boundary | Place PDF in `mixed` group, check headers and bytes |
| Attachment name has garbled characters | Filename/name header encoding unsuitable or client decodes wrongly | Use library APIs and inspect how file names are encoded |
| Vietnamese becomes garbage characters | Wrong `charset`, wrong CTE, or double-encoded data | Compare bytes and charset of the text part |
| Broken on only one client | Valid MIME yet client restricts CSS/HTML, remote images, or related handling | Test on target client; simplify HTML rather than assuming MIME is corrupt |

This table is for **narrowing down** causes, not asserting a symptom has only one cause. The same broken image can stem from unsupported HTML/CSS, an email gateway modifying content, non-standard MIME, or client security policies.

## 10. Analyzing specific scenarios

### 10.1. Body appears twice after adding HTML

**Wrong tree for sending two alternative versions:**

~~~text
multipart/mixed
├── text/plain: "Hello"
└── text/html: "<p>Hello</p>"
~~~

Two independent parts inside `mixed` may both be rendered. When they are two versions of one body, the tree should be:

~~~text
multipart/alternative
├── text/plain: "Hello"
└── text/html: "<p>Hello</p>"
~~~

In Spring, use `helper.setText(plainText, htmlText)` to create two options, rather than adding two sibling body parts into `mixed`.

### 10.2. CID image exists in email yet does not show

Suppose HTML has `<img src="cid:logo-2026">`. Inspecting the tree reveals:

~~~text
multipart/related
├── text/html
└── image/png
    Content-ID: <logo-2025>
~~~

The IDs mismatch; the client cannot find the referenced image part. Fix Content-ID/HTML to point to the same resource. If the IDs match yet rendering still fails, check whether image bytes decode and open properly, whether `Content-Type` is right, and whether the client blocks that resource type.

Do not confuse `https://...` URL images with `cid:...` images: remote images may be blocked automatically by clients until the user allows loading them, even when the email MIME is valid.

### 10.3. Plain text is fine yet HTML has broken Vietnamese accents

Suppose `text/plain; charset=UTF-8` reads cleanly, while the HTML branch declares `charset=ISO-8859-1` even though its bytes are actually UTF-8. The bug sits on **the HTML part**, not the root multipart. Construct the content using the right charset and let the library handle content-transfer encoding accordingly.

Do not patch it by guessing replacement characters inside HTML; first inspect bytes before/after transfer decoding and the headers of the matching part. If content was already corrupted before entering `MimeMessageHelper`, fix the source/template instead of altering MIME headers to mask the bug.

### 10.4. PDF sits in the alternative branch and hides the body

~~~text
multipart/alternative
├── text/html
└── application/pdf
~~~

This states that the PDF is an **alternative choice** to HTML, contradicting the intent to send the PDF as an independent file. Separate them properly:

~~~text
multipart/mixed
├── text/html
└── application/pdf
    Content-Disposition: attachment
~~~

If plain text and inline images are also needed, the first branch's body can itself be a separate `alternative`/`related` subtree.

### 10.5. Email is right when built in Spring yet wrong in the target mailbox

If the tree at `message.writeTo(...)` differs from the tree in the `.eml` exported by the recipient, places to investigate include the mail-sending service, file-scanning filters, relays, mail gateways, mailing lists, or systems appending signatures/disclaimers. Do not alter `setText(...)` before establishing evidence of that transformation. Conversely, if before/after trees match and only one mail client renders wrongly, focus on client behavior and HTML/CSS content.

## 11. Special MIME situations

**Attached message (`message/rfc822`).** A part may contain an entire other email. Walk it as a separate subtree; do not automatically treat all `text/html` parts found inside a nested message as the outer email's primary body.

**Digitally signed or encrypted emails (S/MIME).** You may encounter `multipart/signed`, `application/pkcs7-mime`, or other protected content forms. Encrypted emails cannot have their inner plaintext tree inspected without valid decryption. For signed emails, altering parts/boundaries can invalidate signature verification. Inspect and transform only within permitted bounds.

**Valid MIME structure yet incompatible HTML.** Email clients can strip JavaScript, complex CSS, forms, and remote images. A valid tree does not guarantee every HTML attribute renders like a web browser. Design simple email HTML, include plain text, and test on target clients.

**MIME parsers tolerate malformed messages to varying degrees.** One client may tolerate a bad boundary or non-standard header while another does not. When encountering discrepancies, preserve the raw `.eml` and inspect both library parsing behavior and raw source.

**File names and Content-IDs are not harmless data.** They can contain project info, email addresses, or identifying strings. When sharing debug trees, redact sensitive data while preserving structural elements needed for comparison, such as using consistently renamed ID pairs.

## 12. How to state the root cause after inspecting the tree

A useful conclusion should describe **the symptom, the evidence from the MIME tree, and the required change**, rather than merely saying “HTML is broken”.

Example:

> In the received `.eml`, the `multipart/mixed` root contains two sibling `text/plain` and `text/html` parts. They are two versions of one content yet are not wrapped inside `multipart/alternative`. One client is displaying both. The body must be built via `MimeMessageHelper.setText(plain, html)` to express the alternative relationship properly, then re-verify the tree on a test email.

Another example:

> The HTML part references `cid:logo-a` while the image part has `Content-ID: <logo-b>`. The image does not render because the reference cannot find a matching resource. Use the same Content-ID in HTML and `addInline(...)`, ensure the image sits inside the related MIME group, and re-test on the target client.

Through both examples, **the MIME tree serves as structural evidence** connecting Spring Mail code to how the email client displays the message. An effective diagnostic workflow is reading the actual email, walking from root to each part, verifying `mixed`/`alternative`/`related` relationships, checking headers and references, and comparing against the intended message construction in Spring. That separates bugs across MIME structure, part payload data, transport paths, and mail client limitations.
