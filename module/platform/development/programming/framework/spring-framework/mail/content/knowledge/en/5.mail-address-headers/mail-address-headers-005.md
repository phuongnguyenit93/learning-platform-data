# Subject and Unicode Subject Encoding

When a Spring application sends an email with the subject **“Xác nhận đơn hàng của Nguyễn An ✅”**, recipients normally see the Vietnamese diacritics and emoji as expected. However, when opening the **raw message source**, the subject field may look like an unreadable ASCII string, such as segments starting with `=?UTF-8?...?=`.

That is not necessarily an error. **`Subject` is an email header field**, and traditional email systems need a way to represent Unicode text so that diverse servers, mail processors, and email clients can exchange subjects safely. The standard approach is **MIME encoded-word per RFC 2047**. In Spring Framework Mail, this is typically handled by **Jakarta Mail** via `MimeMessage` or `MimeMessageHelper`.

Understanding this mechanism explains why an email can have a valid UTF-8 body yet a garbled subject, why `=?UTF-8?B?...?=` strings appear in headers, and why **body encoding** differs from **Subject header encoding**.

## 1. Where Does Subject Live in an Email?

An email consists of **headers** and a **body**, separated by a blank line. Example:

~~~text
From: notice@example.org
To: an@example.net
Date: Thu, 12 Nov 2026 08:00:00 +0000
Subject: Order A102 confirmed
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Order A102 has been confirmed.
~~~

In this example:

- `From` and `To` are headers describing the displayed sender and recipient.
- `Subject` is the **message subject**, typically shown by email clients in the inbox list, notifications, or message detail view.
- `Content-Type` describes the media type and character set of the **body**.
- Everything after the blank line is the email **body**.

A common misconception: **`charset=UTF-8` in the body's `Content-Type` does not automatically govern how the `Subject` field is encoded**. Headers have their own representation rules. An application can send a properly encoded UTF-8 body while still producing broken diacritics in the subject if the header is not constructed properly.

Additionally, `Subject` belongs to the **message content** transmitted inside SMTP `DATA`, not to the SMTP envelope. The `MAIL FROM` and `RCPT TO` commands handle routing; they do not carry the Subject header.

~~~mermaid
flowchart TD
    A["Email message"] --> B["Headers"]
    A --> C["Body"]
    B --> D["From / To / Date"]
    B --> E["Subject: title seen by reader"]
    C --> F["text/plain or text/html"]
    E --> G["Header encoding when needed"]
    F --> H["Body Charset and Content-Transfer-Encoding"]
~~~

## 2. Why Do Subjects with Vietnamese Diacritics Need Encoding?

Traditional email standards built header syntax mainly around **US-ASCII**. Vietnamese characters with diacritics such as `Đ`, `ă`, `ộ`, `ỹ` and many emojis cannot be represented directly as plain ASCII bytes.

Suppose an application wants to set:

~~~text
Subject: Chào bạn – Đơn hàng đã được xác nhận ✅
~~~

Semantically, this is a completely valid subject for readers. However, placing raw UTF-8 bytes onto a mail path that only expects traditional ASCII headers can cause intermediate software to misread, reject, or corrupt the text.

**MIME encoded-word** represents Unicode segments using ASCII characters in a format that declares the character set. The receiving client decodes those segments back into the original Unicode text.

Small example with the word “Café”:

~~~text
Subject: =?UTF-8?B?Q2Fmw6k=?=
~~~

Decoding that encoded-word produces:

~~~text
Café
~~~

In another example, the same text can use Q-encoding:

~~~text
Subject: =?UTF-8?Q?Caf=C3=A9?=
~~~

Both express the word “Café”. Which encoding is chosen depends on the library and input characteristics—not something the recipient needs to know or choose manually.

**Note on modern internationalized email:** RFC 6532 allows raw UTF-8 in certain headers when the mail transport environment supports SMTPUTF8 under RFC 6531. Therefore, not every modern Unicode email is forced to use encoded-words. Nevertheless, RFC 2047 remains essential and widely used to maintain broad compatibility with systems expecting traditional ASCII-formatted headers.

## 3. MIME Encoded-Word Syntax for Subject

An encoded-word has the form:

~~~text
=?charset?encoding?encoded-text?=
~~~

Components:

| Component | Meaning | Example |
| --- | --- | --- |
| `=?` | Delimiter marking the start of an encoded-word | `=?` |
| `charset` | Character set used to convert text into bytes | `UTF-8` |
| `encoding` | Method used to encode those bytes into an ASCII string | `B` or `Q` |
| `encoded-text` | The encoded payload | `Q2Fmw6k=` |
| `?=` | Delimiter marking the end of an encoded-word | `?=` |

Given the string:

~~~text
=?UTF-8?B?Q2Fmw6k=?=
~~~

we read it step by step:

1. `=?` signals the start of an encoded-word.
2. `UTF-8` specifies that the original text was converted to bytes using UTF-8.
3. `B` instructs the decoder to decode the payload using Base64.
4. `Q2Fmw6k=` is the Base64-encoded byte data.
5. `?=` closes the encoded-word.

After Base64-decoding back to bytes, the reader applies UTF-8 to restore the Unicode text “Café”.

The charset name is not a language name. `UTF-8` can represent Vietnamese, Japanese, Arabic, emojis, and many other scripts. There is no special “Vietnamese-only UTF-8” in this syntax.

### 3.1. B Encoding

The letter **B** denotes **Base64** encoding. Example:

~~~text
Text:        Café
UTF-8 bytes: 43 61 66 C3 A9
Base64:      Q2Fmw6k=
Encoded:     =?UTF-8?B?Q2Fmw6k=?=
~~~

B is often suited to subjects containing many non-ASCII bytes, such as dense Vietnamese diacritics or characters from other scripts. Still, a short subject may use Q if the library chooses it.

### 3.2. Q Encoding

The letter **Q** uses syntax similar to *quoted-printable*, though it is **not identical to body quoted-printable rules**. Some bytes remain as readable ASCII characters, while special bytes are represented as `=HH` (two hexadecimal digits).

Example:

~~~text
Text:        Café
Encoded:     =?UTF-8?Q?Caf=C3=A9?=
~~~

`=C3=A9` represents the two UTF-8 bytes of `é`. For spaces, **Q-encoding inside an encoded-word can use an underscore `_`**:

~~~text
Subject: =?UTF-8?Q?Ch=C3=A0o_b=E1=BA=A1n?=
~~~

After decoding, the subject is:

~~~text
Chào bạn
~~~

Inside a Q-encoded word, `_` represents a space. If the original text actually contains an underscore character, it must be hex-encoded to avoid ambiguity. Never replace all `_` characters in ordinary text with spaces; this rule applies **only inside Q encoded-words**.

### 3.3. Both B and Q Are Valid

| Aspect | `B` (Base64) | `Q` (Q-encoding) |
| --- | --- | --- |
| Representation | Encodes bytes as a Base64 string | Keeps certain ASCII characters; encodes other bytes as `=HH` |
| Human readability in raw email | Usually unreadable | Some ASCII segments remain recognizable |
| Text with many non-ASCII characters | Often more compact | Can become longer |
| Spaces inside encoded-word | Included in Base64 bytes | Usually represented as `_` |
| Result after proper decoding | Original Unicode string | Original Unicode string |

**Choosing B or Q is a representation detail** and should never drive business logic. Jakarta Mail can select an appropriate encoding automatically.

## 4. What Happens When a Subject Mixes ASCII and Unicode?

Real-world subjects often combine multiple character types:

~~~text
[Shop] Đơn hàng #A102 đã giao ✅
~~~

On the wire, the header may be represented by one or more encoded-words, possibly interspersed with plain ASCII segments. Conceptual illustration:

~~~text
Subject: [Shop] =?UTF-8?B?...?=
~~~

The `...` here is only a structural placeholder, **not a real Base64 string that can be decoded**. In real output, each encoded-word must contain valid encoded data, and decoding the full Subject must reconstruct the original text.

Important points:

- A Unicode subject does not have to fit inside a single encoded-word.
- Plain ASCII segments may stay unencoded while Unicode segments are encoded.
- Multiple encoded-words may appear consecutively to respect per-word length limits.
- Whitespace between adjacent encoded-words follows specific decoding rules; never rely on naive string concatenation to guess the displayed subject.
- Converting a Unicode string to UTF-8 bytes must preserve characters cleanly, including multi-byte characters and emojis.

Consequently, **the raw header can be much longer than the visible character count**. A diacritic character may take two or three UTF-8 bytes; an emoji may take four bytes; and Base64 or Q representation expands length further.

## 5. Length Limits and Line Folding for Subject

Traditional email headers have line-length rules. RFC 5322 sets a hard limit of **998 characters per header line** (excluding CRLF), while recommending lines stay under **78 characters** for easier processing.

Under RFC 2047, **a single encoded-word must not exceed 75 characters**, including `=?`, charset, encoding, encoded payload, and `?=`.

This leads to two easily confused mechanisms:

1. **Splitting into multiple encoded-words:** if a Unicode subject is long, the library can break it into multiple valid encoded-words.
2. **Header folding:** a long header can be wrapped onto the next line using `CRLF` followed by one or more spaces or tabs.

Example illustrating header folding:

~~~text
Subject: =?UTF-8?B?...encoded-word-1...?=
 =?UTF-8?B?...encoded-word-2...?=
~~~

Each string with `...` above is an **illustrative placeholder**, not a decodable encoded-word. In a valid email, the continuation line begins with whitespace (space or tab) so parsers recognize it as **the same `Subject` field**, not a new header.

When processing a folded header, parsers perform **unfolding** per header rules before interpreting the content. For adjacent encoded-words, RFC 2047 also defines how separating whitespace is handled so stray spaces are not injected into decoded text.

### Why Not Split at Arbitrary Byte Offsets?

A Vietnamese character or emoji can span multiple UTF-8 bytes. Slicing a byte sequence mid-character produces invalid UTF-8. Splitting an encoded-word at an arbitrary offset breaks the `=?...?=` structure.

The MIME library must split subjects at valid boundaries and emit valid encoded-words. **Never manually slice a Base64 string by character count and wrap pieces into encoded-words** unless you fully implement Unicode and RFC 2047 rules.

End users never need to see folding: the goal is rendering a clean, readable subject line in the UI.

## 6. Unicode Subjects in Spring Framework Mail

At the application level, Spring Framework Mail offers two common ways to create emails:

- `SimpleMailMessage` for simple plain-text emails.
- `MimeMessage` with `MimeMessageHelper` for MIME messages, HTML, attachments, and explicit encoding options.

When Unicode subjects matter, **`MimeMessageHelper` with an explicit `UTF-8` charset** is clear and easy to maintain.

### 6.1. Adding the Spring Boot Starter

For a Gradle project using Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Then configure the SMTP connection according to your provider. Example:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

`smtp.provider.example` is only an example. Environment variables must be supplied at runtime; never put real passwords into source code. This configures the **mail-sending connection**; it is independent of MIME Subject encoding logic.

### 6.2. Sending a Plain-Text Email with a Unicode Subject

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationMailService {

    private final JavaMailSender mailSender;

    public OrderConfirmationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient, String orderCode)
            throws MessagingException {

        MimeMessage mimeMessage = mailSender.createMimeMessage();

        // UTF-8 applies when helper builds MIME fields requiring encoding.
        MimeMessageHelper helper =
                new MimeMessageHelper(mimeMessage, false, "UTF-8");

        helper.setFrom("notice@example.org");
        helper.setTo(recipient);
        helper.setSubject(
                "Order confirmation " + orderCode + " ✅"
        );
        helper.setText(
                "Order " + orderCode + " has been confirmed.",
                false
        );

        mailSender.send(mimeMessage);
    }
}
~~~

Here:

1. `createMimeMessage()` creates a Jakarta Mail message object.
2. `new MimeMessageHelper(mimeMessage, false, "UTF-8")` sets the default charset when the helper operates on the message. `false` indicates this example does not need a multipart structure.
3. `setSubject(...)` accepts a **normal Unicode Java String**, such as one with diacritics or emojis.
4. The helper/Jakarta Mail prepares the proper header representation when building the message.
5. `send(...)` dispatches the email via the application's SMTP configuration.

The core idea: **business code only supplies the Subject content**, while converting it to a proper MIME representation is handled by the library. There is no need to Base64-encode before passing the subject to `setSubject`.

For `orderCode`, the example assumes a valid order code controlled by business logic. When data comes from external sources, validate it before placing it in the subject; in particular, reject newline or control characters that could corrupt header structure.

### 6.3. Using the Jakarta Mail API Directly

If you prefer not to use the helper, call `MimeMessage.setSubject(String, String)` to declare the charset explicitly:

~~~java
MimeMessage message = mailSender.createMimeMessage();
message.setFrom("notice@example.org");
message.setRecipients(
        jakarta.mail.Message.RecipientType.TO,
        "recipient@example.net"
);
message.setSubject(
        "Notification: Order has been confirmed ✅",
        "UTF-8"
);
message.setText("This is the email body.", "UTF-8");

mailSender.send(message);
~~~

`setSubject(subject, "UTF-8")` is the key call: it gives the library the charset needed to build the Subject header from a Unicode string. For complex emails, `MimeMessageHelper` is usually more convenient for HTML, multipart, and attachments.

### 6.4. What About SimpleMailMessage?

Short example:

~~~java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("notice@example.org");
message.setTo("recipient@example.net");
message.setSubject("Your order has been confirmed");
message.setText("Thank you for your order.");
mailSender.send(message);
~~~

`SimpleMailMessage` accepts Java strings, so it can hold Unicode in Subject. However, how a simple message maps to MIME and its default charset depends on the sending configuration and implementation. When you need **explicit UTF-8 to avoid environment-dependent behavior**, building a `MimeMessage` via `MimeMessageHelper(..., "UTF-8")` or calling `setSubject(..., "UTF-8")` makes your intent unambiguous.

Never pre-encode a Subject using `MimeUtility.encodeText(...)` and pass the encoded result back into `helper.setSubject(...)`. Doing so easily causes **double encoding** or unexpected raw headers.

## 7. Does an HTML Email Subject Differ?

No. An HTML email may require `Content-Type: text/html; charset=UTF-8` for the **body**, while `Subject` still follows header encoding rules.

Example:

~~~java
MimeMessage mail = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(mail, false, "UTF-8");

helper.setTo("recipient@example.net");
helper.setFrom("notice@example.org");
helper.setSubject("November special offer 🎁");
helper.setText(
        "<h1>Hello!</h1><p>This is an HTML email.</p>",
        true
);

mailSender.send(mail);
~~~

The `true` argument in `setText(..., true)` marks the body as HTML. It is **not a switch to "enable Unicode for Subject"**. Header and MIME body charsets are handled independently by the library at their respective layers.

If an email is sent successfully with a **correct Vietnamese body but a garbled Subject**, inspect how the Subject/header was constructed; fixing only the body's `Content-Type` will not resolve it.

Similarly, `Content-Transfer-Encoding: base64` or `quoted-printable` on a body/part does not mean headers are encoded under the same rule. **Header encoded-word `B`/`Q`** and **body `Content-Transfer-Encoding`** are mechanisms with different scopes.

## 8. Reading Encoded Subjects in Raw Emails

A mail program may store the Subject on the wire as:

~~~text
Subject: =?UTF-8?Q?Ch=C3=A0o_b=E1=BA=A1n?=
~~~

When the recipient opens the email in a mail client, the client decodes and displays:

~~~text
Chào bạn
~~~

There are three perspectives on the same subject:

| Perspective | Observed Data |
| --- | --- |
| Application code | `"Chào bạn"` as a Java String |
| Raw MIME header | `=?UTF-8?Q?Ch=C3=A0o_b=E1=BA=A1n?=` |
| Mailbox UI | `Chào bạn` |

When reading messages with the Jakarta Mail API, `MimeMessage.getSubject()` normally returns the **decoded value** (or an interpreted string from the header). To inspect the raw header value for diagnostics, read `getHeader("Subject", null)`.

Development example using a message **created purely for testing**, avoiding sensitive email contents:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("notice@example.org");
helper.setTo("recipient@example.net");
helper.setSubject("Chào bạn");
helper.setText("Sample message body.", false);

// Prepare MIME object headers before inspecting.
message.saveChanges();

String rawSubject = message.getHeader("Subject", null);
String decodedSubject = message.getSubject();

System.out.println("Raw Subject: " + rawSubject);
System.out.println("Decoded Subject: " + decodedSubject);
~~~

`rawSubject` may contain encoded-words and folded header lines. `decodedSubject` is the application-friendly subject string. **Do not depend on a specific exact raw string**, because Jakarta Mail may choose B or Q and split encoded-words differently across versions or encoding conditions.

### Why Can the Raw Source Contain Multiple Encoded-Words?

A long Subject can span multiple segments:

~~~text
Subject: =?UTF-8?Q?Ch=C3=A0o_b=E1=BA=A1n?=
 =?UTF-8?Q?_Caf=C3=A9?=
~~~

This is an **illustrative example of consecutive encoded-words**. An email client must interpret the entire header field per RFC 2047, including whitespace handling between encoded-words. Never write a naive string helper that "splits on spaces and decodes word by word," as it can yield wrong output.

When working with an existing raw MIME message, use Jakarta Mail's decoding utility instead of rolling your own:

~~~java
import jakarta.mail.internet.MimeUtility;

String decoded = MimeUtility.decodeText(rawSubject);
~~~

When a raw line includes the header name like `Subject:` or folding, extract the **header field value** properly before passing it in. On a valid `MimeMessage`, simply use `getSubject()`.

## 9. Subject, Sender Name, and Email Address Are Three Separate Concerns

Displayed headers extend beyond Subject. Example:

~~~text
From: Nguyễn An <nguyen.an@example.org>
To: Minh <minh@example.net>
Subject: Appointment confirmation 📅
~~~

There are at least three distinct data types here:

- **Subject:** a free-text field that may require encoded-words.
- **Display name** such as `Nguyễn An`: may also require header encoding according to appropriate rules.
- **Actual address** such as `nguyen.an@example.org`: follows email address syntax; using Unicode in the local-part or domain involves internationalized email standards and infrastructure support.

When using Jakarta Mail APIs to set a display name with diacritics, supply a dedicated charset:

~~~java
import jakarta.mail.internet.InternetAddress;

InternetAddress sender = new InternetAddress(
        "notice@example.org",
        "Customer Support Team",
        "UTF-8"
);

helper.setFrom(sender);
helper.setSubject("Appointment confirmation 📅");
~~~

`InternetAddress` handles address and display-name data. `setSubject` handles the message subject. Never pass a full `Subject: ...` or `From: ...` string into `setSubject`; it expects only the **Subject value**, not a complete header block.

For internationalized email addresses, `SMTPUTF8` support is a separate topic requiring checks across both the SMTP server and relay path. **Having a Unicode Subject does not mean recipient addresses can freely use Unicode before `@`.**

## 10. Direct UTF-8 in Modern Headers

RFC 6532 extends header syntax to allow direct UTF-8 when protocols and mail paths support internationalization, typically tied to **SMTPUTF8** under RFC 6531.

Conceptually, you may encounter headers like:

~~~text
Subject: Xác nhận đơn hàng ✅
~~~

carrying raw UTF-8 bytes in the header rather than converting all Unicode into ASCII encoded-words.

However, when building a standard Spring mail-sending application, distinguish between:

| Representation | Characteristics |
| --- | --- |
| RFC 2047 encoded-word | Represents Unicode segments as ASCII strings like `=?UTF-8?B?...?=` or `=?UTF-8?Q?...?=`, broadly compatible with traditional MIME systems. |
| RFC 6532 direct UTF-8 | Permits Unicode directly in headers provided the internationalized SMTP environment supports transmitting and processing it. |

These are **two header representations**, not two Subject types for users to pick in a UI.

An application must not assume that enabling UTF-8 in a Java setting means every SMTP relay and hop supports SMTPUTF8. If internationalized email addresses are specifically required, evaluate the entire delivery path and provider support.

For standard Unicode subjects via `JavaMailSender`, the most maintainable approach is **passing Unicode strings to `MimeMessage`/`MimeMessageHelper` APIs with an explicit charset** and letting the library choose the appropriate header encoding.

## 11. Common Mistakes When Encoding Unicode Subjects

### 11.1. Question Marks, Replacement Characters, or Mojibake

For example, recipients see:

~~~text
Ch?o b?n
~~~

or:

~~~text
ChÃ o báº¡n
~~~

The cause may be text passing through an incompatible character encoding at some step before or during email creation. One classic case is **mojibake**: UTF-8 bytes interpreted under a different code page, producing corrupted characters.

If the Java string is **already corrupted before calling** `setSubject`, the MIME library simply encodes that corrupted string; specifying `UTF-8` at the end cannot recover the original text.

Trace the full data path: source from database/API, constructed Java String, charset passed to the MIME API, and header value on the wire.

### 11.2. Double-Encoded Headers

If a string was already encoded via `MimeUtility.encodeText(...)` and then passed to an API that encodes automatically, the received email may show literal `=?UTF-8?...?=` text or unexpected output.

Instead of:

~~~java
// Avoid pre-encoding before calling helper.setSubject(...).
// String preEncoded = MimeUtility.encodeText(subject, "UTF-8", "B");
// helper.setSubject(preEncoded);
~~~

use:

~~~java
helper.setSubject("Notification: Order confirmed ✅");
~~~

The helper API expects the plain text to display. If you are building raw byte-level messages at a lower layer, follow that layer's encoding rules; never mix both approaches.

### 11.3. Overly Long Subjects or Unusual Line Wrapping

Some mail UIs truncate subjects in the inbox list; that is a **UI limit**. Separately, MIME headers have technical line limits, so the library may fold a header across multiple lines during serialization.

When seeing multiple lines for Subject in a raw email, verify they are proper continuation lines starting with a space or tab. Do not blindly strip raw CRLFs without understanding folding rules.

If a Subject includes user-provided input, block CR/LF characters in that input. If input can be arbitrarily long, pick a sensible display limit at the business layer and truncate using **Unicode-safe operations** to avoid splitting surrogate pairs or combining character clusters.

### 11.4. UTF-8 Body Works Yet Subject Is Corrupted

Possible reasons:

- Calling `setText(..., "UTF-8")` without setting the Subject with a suitable charset.
- Subject data already suffered encoding corruption before email construction.
- Middleware or another system overwrote the header.
- The mail-reading client mishandled the header.

Isolate the stage by inspecting **the Subject value before sending**, **the serialized raw Subject**, and **the decoded Subject at the receiver**. Each layer pinpoints where corruption occurred.

### 11.5. Seeing `=?UTF-8?...?=` in Raw Source and Assuming It Is a Bug

Encoded-words are normal representations in raw MIME. Distinguish clearly:

- **Raw source** shows encoded-words: usually completely normal.
- **Email client** displays the Unicode subject cleanly: expected result.
- **Email client** displays literal encoded-words in the Inbox list: the header decoder may have failed or the header syntax was malformed.

Merely seeing Base64 in the raw source is **not evidence** of a broken email.

### 11.6. Subjects Containing Newlines from Untrusted Input

Data like customer names or product titles may be interpolated into Subject. Allowing control characters such as `CR` or `LF` into raw header construction can cause **header injection** or message rejection.

Validate inputs, enforce length bounds, and use Jakarta Mail's structured header APIs. Avoid building messages by concatenating `"Subject: " + userInput + "\r\n"`. Even when libraries include safeguards, business logic should still control what a Subject may contain.

## 12. Subject and Privacy

Email subjects are visible in many places outside the message body: inbox lists, mobile push notifications, previews, and mail service logs.

Therefore, subjects should never contain unnecessary confidential data, such as:

- Passwords, OTP codes, or recovery links containing sensitive tokens.
- Detailed financial or personal data when not needed to identify the message.
- Information recipients would not want exposed on a lock screen.

**RFC 2047 Base64 is not security encryption.** Any system reading the header can decode an encoded-word; it is merely a **character representation**. STARTTLS also protects only the corresponding SMTP hop—it does not keep Subject confidential across intermediate servers.

When sending private information, keep the Subject generic—such as **“You have a new notification”**—and place sensitive details behind an appropriately access-controlled workflow.

## 13. Tips for Writing Readable Vietnamese Subjects

Proper encoding ensures characters render; **clear Subject phrasing** helps recipients understand the email. Guidelines:

1. Put key information first: `Xác nhận đơn hàng A102` is usually clearer than a long introductory sentence.
2. Write Vietnamese with proper diacritics normally; avoid stripping accents out of fear of SMTP. MIME libraries support Unicode properly.
3. Use emojis selectively; do not rely solely on an emoji to convey meaning since rendering varies across devices.
4. Avoid ALL CAPS, repeated exclamation marks, or keyword stuffing.
5. Include non-sensitive reference codes when recipients need to look up records: `Lịch hẹn #A102 đã được xác nhận`.
6. For multilingual content, localize the Subject from a locale-specific template and pass the final Unicode string to `setSubject`; never hand-craft per-language encodings.

Example of a service preparing a Subject from controlled templates:

~~~java
String subject = switch (locale.getLanguage()) {
    case "vi" -> "Đơn hàng " + orderCode + " đã được xác nhận";
    case "en" -> "Order " + orderCode + " has been confirmed";
    default -> "Order confirmation: " + orderCode;
};

helper.setSubject(subject);
~~~

This example assumes `locale` (`java.util.Locale`) and `orderCode` have already been validated by the application. **Text templating** and **MIME encoding** are two separate steps: first prepare the exact display sentence, then let the library represent it in the header.

## 14. Diagnostic Flow When a Unicode Subject Renders Incorrectly

You can trace the issue step by step:

~~~mermaid
flowchart TD
    A["Subject string in application"] --> B{"Is Unicode intact before sending?"}
    B -->|"No"| C["Check data source / charset before sending"]
    B -->|"Yes"| D["Build MIME with explicit UTF-8"]
    D --> E["Inspect raw Subject"]
    E --> F{"Valid encoded-word / UTF-8 header?"}
    F -->|"No"| G["Check header-building API and MIME config"]
    F -->|"Yes"| H["Check reading/decoding on receiving side"]
    H --> I["Compare displayed Subject"]
~~~

Each layer has a distinct responsibility:

| Layer | Question to Answer |
| --- | --- |
| Data source | Does the original Java String have intact diacritics, characters, and emojis? |
| Email-building code | Are you using `MimeMessageHelper` or `MimeMessage.setSubject` with the right charset? |
| MIME serialization | Does the raw header follow valid encoded-word, folding, or supported UTF-8 header syntax? |
| SMTP / relay | Did intermediate infrastructure alter or fail to support the chosen header format? |
| Email client | Did the header decoder restore the Unicode text properly? |

Do not automatically blame DNS, SMTP AUTH, STARTTLS, or HTML body content for garbled characters. Those govern **transport hops**, **connection authentication**, or the **body**; Unicode Subject issues almost always trace back to the **source string and header representation**.

## 15. Practice Questions

**Q1.** An email has these headers:

~~~text
Content-Type: text/html; charset=UTF-8
Subject: =?UTF-8?Q?Ch=C3=A0o_b=E1=BA=A1n?=
~~~

What is the displayed Subject? **“Chào bạn”**. `Content-Type` describes the HTML body; the encoded-word in `Subject` follows its own decoding rules.

**Q2.** Can these two strings represent the same content?

~~~text
=?UTF-8?B?Q2Fmw6k=?=
=?UTF-8?Q?Caf=C3=A9?=
~~~

**Yes.** Both represent **“Café”**; one uses Base64 and the other uses Q-encoding.

**Q3.** Does `=?UTF-8?B?...?=` in an email's raw source mean the message is securely encrypted? **No.** It is character encoding that anyone can publicly decode.

**Q4.** In Spring, do you need to call Base64 manually before `helper.setSubject("Xin chào")`? **No.** Pass the original Unicode string to the helper with the appropriate charset.

**Q5.** Why might a Subject span two encoded-words across two lines? Are there two Subjects? **No.** It can be a single header that was folded or split into multiple encoded-words to satisfy standard length limits.

**Q6.** If a Subject contains emojis while recipient addresses are purely ASCII, is an SMTPUTF8 address required? **Not just for the Subject.** Unicode headers can be represented via RFC 2047. Unicode email addresses and SMTPUTF8 are a separate requirement.

## 16. Mental Model

In Spring Framework Mail, `Subject` flows from **the application's Unicode string** into **the email's MIME header** and is then **decoded by the email client for display**.

~~~mermaid
flowchart LR
    A["Java String: Chào bạn"] --> B["MimeMessageHelper / Jakarta Mail"]
    B --> C["Subject: RFC 2047 encoded-word"]
    C --> D["SMTP relay and receiving server"]
    D --> E["Email client decodes"]
    E --> F["Displays: Chào bạn"]
~~~

Keep four distinctions in mind:

- **`Subject` is a header**, with Unicode representation rules independent of the body.
- **`=?UTF-8?B?...?=` or `=?UTF-8?Q?...?=` is an encoded-word**, decodable back into the original text.
- **`MimeMessageHelper.setSubject(...)` takes the display string**, while the library handles encoding and header folding.
- **Encoding is not encryption**: converting Unicode to Base64 or Q does not make the subject secret.

Understanding these boundaries lets developers build Vietnamese subjects with diacritics and emojis without manipulating raw bytes, while also knowing how to inspect raw headers when a subject renders unexpectedly.

