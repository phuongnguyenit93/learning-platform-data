# Testing Failures When Addresses or Resources Are Invalid

In Spring Framework Mail, an email can fail right at the **data-preparation step**, before the application ever connects to an SMTP server. A syntactically invalid recipient address, an address containing control characters, a missing attachment file, or a resource whose stream cannot be opened can all break message construction. If these cases go untested, incidents may surface only after deployment, when a queue worker runs or even when Jakarta Mail begins serializing the MIME message for sending.

**Unit testing failures when addresses or resources are invalid** has a clear goal: feed bad inputs in a controlled way, verify the application **rejects them or reports the right exception type**, and verify **no unintended email send operation occurs**.

Within the Spring Mail ecosystem, distinguish:

- **SimpleMailMessage:** primarily a data holder for plain-text emails; its setters are not a mailbox-verification or resource-checking service.
- **MimeMessage + MimeMessageHelper:** constructs a MIME message, can parse addresses via Jakarta Mail, and attaches files/inline resources.
- **Resource / InputStreamSource:** byte source for attachments or inline images; opening streams and reading full payloads is a separate responsibility from address validation.
- **JavaMailSender.send(...):** the side-effect boundary handing messages to SMTP transport.

Each boundary should be tested using **JUnit 5**, **Mockito**, real in-memory MIME objects, and fake/mock resources. **There is no need to send emails to real recipients** just to test input validation errors, missing files, or stream-read failures.

## 1. Why separate data errors from SMTP errors?

A typical processing pipeline:

~~~text
Business DTO / request
        |
        v
Validate mail addresses
        |
        v
Validate subject / filename / resource
        |
        v
Read or prepare resource bytes
        |
        v
Build SimpleMailMessage or MimeMessage
        |
        v
JavaMailSender.send(...)
        |
        v
SMTP connection / delivery attempt
~~~

Errors can occur at any step.

| Stage | Example error | What to test |
| --- | --- | --- |
| Input DTO | Null recipient, blank subject | Reject before calling sender |
| Address validation | Invalid syntax, multiple mailboxes where only one is allowed | Exception and no send |
| Header validation | CR/LF in Subject or filename | Never build headers from bad data |
| Resource lookup | Classpath file does not exist | Clear error; never treat missing file as valid empty attachment |
| Resource read | IOException, closed stream, missing permission | Classify read error, never call send |
| Resource content | Empty file, oversized, disallowed data type | Reject per application contract |
| MIME building | AddressException or MessagingException | Never confuse with SMTP provider error |
| SMTP transport | AUTH, TLS, RCPT TO, DATA, or timeout | Separate integration/transport test group |

A **data unit test** needs no network connection. What must be proven is that no send command is issued when required inputs fail checks.

## 2. The concept of an "invalid address" must be clearly defined

An address can be unsuitable at several levels:

1. **Null or blank:** no data supplied.
2. **Invalid syntax:** string does not represent a valid mailbox under application-supported rules.
3. **Contract mismatch:** string includes a display name, address group, or multiple addresses in a single-address field.
4. **Contains control characters:** CR/LF or control characters positioned where they can corrupt headers.
5. **Disallowed by business rules:** recipient is on a blocklist or a forbidden domain.
6. **Nonexistent mailbox:** requires an actual server signal or verification workflow; syntax checking alone never proves existence.

**InternetAddress.validate() does not prove a mailbox actually exists.** A unit test must never connect to an external domain's mail server just to decide whether an address can receive email.

### 2.1. Example addresses to reject under a single-mailbox contract

~~~text
null
""
"     "
"invalid-address"
"alice@@example.net"
"alice@example.net, bob@example.net"
"alice@example.net\r\nBcc: outside@example.net"
~~~

These strings test several distinct failure classes. Clarify whether tests target **application-imposed validation** or Jakarta Mail parsing behavior; do not assume every parser version handles every malformed string identically.

### 2.2. Avoid an overly simplistic ASCII regex

A regex such as:

~~~text
^[^@]+@[^@]+\.[^@]+$
~~~

can simultaneously accept bad inputs and reject valid addresses per email standards. For internationalized addresses, quoted local-parts, IDN, or SMTPUTF8, define an explicit support policy.

A sound approach for unit tests: **define the input contract the product actually supports**, use library parsers where appropriate, and enforce additional business rules. Parser behavior and product contracts are not identical.

## 3. SimpleMailMessage does not replace validation

For plain-text emails:

~~~java
SimpleMailMessage message = new SimpleMailMessage();

message.setFrom("notifications@example.org");
message.setTo("invalid-address");
message.setSubject("Notification");
message.setText("Content");
~~~

Calling setters to store strings in `SimpleMailMessage` is not an SMTP transaction and does not prove the address is syntactically valid. Errors may surface later at the sending layer, or providers may handle them differently.

Therefore, never write tests assuming every bad string immediately causes **SimpleMailMessage.setTo(...)** to throw an exception.

### 3.1. Validation should precede message creation

~~~text
Recipient input
      |
      v
Address validation
      |
      +-- Invalid -> reject
      |
      v
SimpleMailMessage.setTo(...)
      |
      v
MailSender.send(...)
~~~

A service can run a dedicated validator before building `SimpleMailMessage`.

### 3.2. Contract unit tests

For invalid inputs:

- Validator throws the defined exception.
- No send command is issued to `MailSender`.
- Bad recipients are never replaced with a dangerous default address.
- Invalid recipients are never silently dropped while sending to someone else.

For valid inputs:

- To/From/Reply-To fields hold the exact expected values.
- No extra CC/BCC addresses are added.
- Subject and body are not altered outside the contract.

## 4. MimeMessageHelper and Jakarta Mail can catch errors earlier

When using **MimeMessageHelper**:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        "UTF-8"
);

helper.setTo("alice@example.net");
~~~

Some helper APIs parse addresses and can throw **jakarta.mail.internet.AddressException**, which belongs to the **MessagingException** hierarchy.

However, **not every error fires immediately inside helper.set...**. In particular, attaching a `Resource` may merely register the data source; the actual payload is sometimes read only when the MIME part is serialized or sent.

Therefore, clarify which question the test is asking:

- Does the parser reject an address string?
- Does the application reject bad data before calling the helper?
- Can the resource be read?
- Can the attachment be read multiple times if transport requires it?
- When data is invalid, is calling `JavaMailSender.send` avoided?

These questions require tests at different boundaries.

## 5. What is a Resource in Spring Mail?

**Resource** is Spring's abstraction for accessing data via classpath, filesystem, URLs, or other sources. Many Resources also implement `InputStreamSource` so Jakarta Mail can read bytes.

Common types:

| Type | Typical role | What to watch out for |
| --- | --- | --- |
| **ClassPathResource** | File packaged inside the application | Missing path may surface only when opening the stream |
| **FileSystemResource** | File on the filesystem | File may be deleted, have permissions changed, or mutate after checks |
| **ByteArrayResource** | Byte payload already in memory | Can supply fresh streams from `byte[]` |
| **InputStreamResource** | Wraps an already-open `InputStream` | Usually unsuitable if transport needs to re-read the stream |
| **UrlResource** | Data from a URL | Can trigger network I/O; requires origin and SSRF controls |

Not every `Resource` is guaranteed to be **a real PDF file**, even if its filename ends in `.pdf`. An existing resource can also be empty, hold wrong content, or be unreadable.

### 5.1. Resources may be read lazily

Example:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);
~~~

This code describes an attachment via a data source. Depending on the overload and how Jakarta Mail serializes, stream reading may happen later than `addAttachment`.

Thus, **never assume every missing resource throws immediately at addAttachment**. If business rules require fail-fast behavior, inspect and read the data before allowing sending.

### 5.2. exists() is useful yet not absolute

~~~java
Resource resource = new ClassPathResource("mail/invoice.pdf");

if (!resource.exists()) {
    throw new IllegalArgumentException(
            "Attachment resource is unavailable"
    );
}
~~~

Checking `exists()` produces clearer errors. Yet opening the stream is still necessary because:

- Read permissions may be missing.
- The resource can change between check and read.
- Remote sources may fail despite metadata claiming existence.
- Different `Resource` implementations have varying `exists`/`isReadable` semantics.

**Actually reading the resource** is the decisive step when attachment contents must be prepared deterministically.

## 6. Testing architecture: separate preparation from sending

A clean organization:

~~~text
StatementMailRequest
       |
       v
MailInputValidator
       |
       +-- Address / subject / filename
       |
       v
ResourceLoader / ContentChecker
       |
       +-- exists / readable / bounded read
       |
       v
StatementMimeFactory
       |
       +-- MimeMessageHelper
       |
       v
StatementDeliveryService
       |
       v
JavaMailSender.send(...)
~~~

Benefits:

- Test validation without constructing MIME.
- Test resources using `byte[]` or fake streams.
- Test MIME construction in memory.
- Test that the service never calls `send` when data is invalid.
- Test exceptions when resource reading fails, without network dependencies.
- Easily distinguish data errors from transient SMTP errors.

The example below places validation and resource loading inside one factory for readability. In large projects, split them into separate classes while preserving clear responsibility boundaries.

## 7. Declare a request containing data and Resource

A simple Java DTO:

~~~java
import org.springframework.core.io.Resource;

public record StatementMailRequest(
        String recipient,
        String subject,
        String body,
        String attachmentFilename,
        Resource attachment
) {}
~~~

Expected fields:

- **recipient:** a single mailbox matching the contract.
- **subject:** single-line, non-blank.
- **body:** text content, non-blank.
- **attachmentFilename:** filename for the MIME header, not an arbitrary path.
- **attachment:** readable data source.

The record does not validate these fields automatically. The factory or validation layer must make explicit decisions before creating a `MimeMessage`.

## 8. Example fail-fast factory for addresses and attachments

The factory below accepts a request requiring a PDF attachment, validates inputs, reads the attachment with a size cap, and builds a **MimeMessage** in memory. It **never calls send**.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Objects;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class StatementMimeFactory {

    private static final int MAX_PDF_BYTES = 1_048_576;

    private final JavaMailSender mailSender;

    public StatementMimeFactory(JavaMailSender mailSender) {
        this.mailSender =
                Objects.requireNonNull(mailSender, "mailSender");
    }

    public MimeMessage prepare(StatementMailRequest request)
            throws MessagingException {

        Objects.requireNonNull(request, "request");

        String recipient = validateMailbox(
                request.recipient(),
                "recipient"
        );

        String subject = validateSingleLine(
                request.subject(),
                "subject"
        );

        String body = validateBody(request.body());

        String filename = validateFilename(
                request.attachmentFilename()
        );

        byte[] pdf = readPdf(request.attachment());

        MimeMessage mimeMessage =
                mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom("billing@example.org");
        helper.setReplyTo("support@example.org");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(body, false);

        helper.addAttachment(
                filename,
                new ByteArrayResource(pdf),
                "application/pdf"
        );

        return mimeMessage;
    }

    static String validateMailbox(
            String raw,
            String field
    ) {
        String value = validateSingleLine(raw, field);

        // Product rule: require a mailbox with local-part
        // and domain; local-name-only addresses are not supported.
        int at = value.indexOf('@');

        if (at <= 0 || at == value.length() - 1) {
            throw new IllegalArgumentException(
                    field + " must be a mailbox address"
            );
        }

        try {
            InternetAddress address =
                    new InternetAddress(value, true);

            address.validate();

            if (address.isGroup()
                    || !value.equals(address.getAddress())
                    || address.getPersonal() != null) {
                throw new IllegalArgumentException(
                        field + " must contain one mailbox only"
                );
            }

            return value;
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    field + " has invalid syntax",
                    ex
            );
        }
    }

    static String validateSingleLine(
            String raw,
            String field
    ) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank"
            );
        }

        String value = raw.trim();

        for (int i = 0; i < value.length(); i++) {
            if (Character.isISOControl(value.charAt(i))) {
                throw new IllegalArgumentException(
                        field + " contains a control character"
                );
            }
        }

        return value;
    }

    static String validateBody(String body) {
        if (body == null || body.isBlank()) {
            throw new IllegalArgumentException(
                    "body must not be blank"
            );
        }

        return body;
    }

    static String validateFilename(String raw) {
        String value = validateSingleLine(
                raw,
                "attachmentFilename"
        );

        if (value.equals(".") || value.equals("..")
                || value.indexOf('/') >= 0
                || value.indexOf('\\') >= 0) {
            throw new IllegalArgumentException(
                    "attachmentFilename must be a plain filename"
            );
        }

        if (!value.toLowerCase(java.util.Locale.ROOT)
                .endsWith(".pdf")) {
            throw new IllegalArgumentException(
                    "Only PDF attachment filenames are allowed"
            );
        }

        return value;
    }

    static byte[] readPdf(Resource resource) {
        if (resource == null) {
            throw new IllegalArgumentException(
                    "attachment must not be null"
            );
        }

        if (!resource.exists() || !resource.isReadable()) {
            throw new IllegalArgumentException(
                    "attachment resource is unavailable"
            );
        }

        try (InputStream input = resource.getInputStream()) {
            byte[] bytes = input.readNBytes(
                    MAX_PDF_BYTES + 1
            );

            if (bytes.length == 0) {
                throw new IllegalArgumentException(
                        "attachment resource is empty"
                );
            }

            if (bytes.length > MAX_PDF_BYTES) {
                throw new IllegalArgumentException(
                        "attachment exceeds allowed size"
                );
            }

            return bytes;
        } catch (IOException ex) {
            throw new UncheckedIOException(
                    "Cannot read attachment resource",
                    ex
            );
        }
    }
}
~~~

### 8.1. Why validate before createMimeMessage()?

The factory intentionally validates address, subject, filename, and resource **before** calling **mailSender.createMimeMessage()**. That lets unit tests assert zero interactions with the mail sender when inputs are invalid.

This is a design choice for testability, not a Jakarta Mail requirement. Another factory might create the `MimeMessage` first and validate later; in that case, tests should assert **send was not called**, rather than forcing `createMimeMessage` not to have been called.

### 8.2. Why read the resource into byte[]?

**ByteArrayResource** supplies fresh streams from the same bytes, fitting cases where Jakarta Mail needs to read a part multiple times during preparation or serialization.

Pre-reading also catches early:

- `IOException` when opening/reading.
- Empty resources.
- Files exceeding application limits.
- Nonexistent or unreadable resources.

### 8.3. Bounded read size

Reading with:

~~~java
byte[] bytes = input.readNBytes(MAX_PDF_BYTES + 1);
~~~

detects oversized inputs by reading **at most one byte past the allowed limit**, rather than calling `readAllBytes()` on an unbounded source.

This is an example data limit, not a default Spring Mail limit. When handling large attachments, design appropriate memory limits, streaming, or external storage.

### 8.4. Checking extension does not prove a file is a PDF

Checking that a filename ends with `.pdf` **does not confirm the bytes are a valid PDF**. If business rules require genuine PDF documents, add content and format validation in a dedicated component. Never rely solely on file extensions or client-supplied MIME types.

### 8.5. Address validation is an example policy

The factory requires a string representing a single mailbox with `@`, disallowing display names in the recipient field. Systems supporting special email syntax or SMTPUTF8 may need a different policy. Do not treat `validateMailbox` as a complete implementation of all email standards.

## 9. Sending service separated from the factory

A service performing the side effect can be very short:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class StatementDeliveryService {

    private final StatementMimeFactory factory;
    private final JavaMailSender mailSender;

    public StatementDeliveryService(
            StatementMimeFactory factory,
            JavaMailSender mailSender
    ) {
        this.factory = factory;
        this.mailSender = mailSender;
    }

    public void send(StatementMailRequest request)
            throws MessagingException {

        MimeMessage message = factory.prepare(request);
        mailSender.send(message);
    }
}
~~~

**This ordering matters**:

~~~text
Factory.prepare(request)
      |
      +-- Invalid -> exception
      |               |
      |               v
      |            No send
      |
      +-- Valid -> MimeMessage
                       |
                       v
                JavaMailSender.send
~~~

If the resource cannot be read, the service never hands the message to transport. When sending itself fails, that is a separate error category from validation/resource preflight.

## 10. Test invalid addresses with JUnit 5 ParameterizedTest

JUnit 5 can run the same test across many bad inputs.

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class StatementAddressValidationTest {

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {
            " ",
            "invalid-address",
            "@example.net",
            "alice@@example.net",
            "alice@example.net, bob@example.net",
            "alice@example.net\r\nBcc: outside@example.net"
    })
    void rejectsInvalidMailbox(String address) {
        assertThrows(
                IllegalArgumentException.class,
                () -> StatementMimeFactory.validateMailbox(
                        address,
                        "recipient"
                )
        );
    }
}
~~~

This tests the **example application validator**. It sends no SMTP traffic and does not depend on whether real mailboxes exist.

### 10.1. Why use NullAndEmptySource and ValueSource?

- **@NullAndEmptySource**: tests `null` and the empty string.
- **@ValueSource**: tests whitespace, missing `@`, multiple `@`, out-of-contract address lists, and CR/LF.

If the product allows different syntax, update both the policy and the tests together.

### 10.2. Test valid addresses

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

@Test
void acceptsSupportedMailbox() {
    assertEquals(
            "an@example.net",
            StatementMimeFactory.validateMailbox(
                    "  an@example.net  ",
                    "recipient"
            )
    );
}
~~~

Testing positive cases is essential: a broken validator that rejects every address would still pass all negative tests.

### 10.3. Never test mailbox existence in unit tests

Never make unit tests query DNS or run SMTP VRFY against real domains. Unit tests only verify **whether data satisfies the contract**. Actual delivery outcomes belong to SMTP/providers and corresponding telemetry.

## 11. Test From, To, Reply-To, CC, and BCC

These address fields have distinct impacts.

| Field | Risk if invalid | What to test? |
| --- | --- | --- |
| **From** | Wrong/unauthorized sender | Comes from controlled config, valid syntax |
| **To** | Sent to wrong person or no recipient | Exact recipient, non-empty, no unexpected list injection |
| **Reply-To** | Replies go to unintended person | Exact value, not taken from arbitrary input |
| **CC** | Data exposed to carbon-copy recipients | Only authorized people, none added implicitly |
| **BCC** | Exposure via envelope or out-of-policy sends | Added only per business rules, no leftover stale values |

When a field accepts multiple addresses, define explicit policies for:

- Null array.
- Empty array.
- Null or blank element.
- Syntactically invalid element.
- Duplicate address.
- Same recipient appearing across To/CC/BCC.

### 11.1. Fail the whole message or drop invalid recipients?

Two policies differ markedly:

- **All-or-nothing:** if any address is invalid, do not send the message.
- **Application-level partial acceptance:** filter out bad recipients and send to the rest, requiring an explicit contract, recording who was dropped, and reviewing privacy implications.

Never silently drop a recipient in a transactional email if doing so loses a critical notice or sends data to the wrong group.

### 11.2. Bcc is not a substitute for validation

Even though Bcc is hidden from displayed headers, the SMTP server still receives the envelope recipient. A wrong or unintended Bcc still delivers the email to the wrong person.

### 11.3. Test misconfigured sender addresses

If From/Reply-To come from configuration, test config via a dedicated validator or factory. Never wait for SMTP to return 550 or 553 to discover a configured address has invalid syntax.

## 12. Test no send happens when recipient is invalid

This is an interaction test at the `JavaMailSender` boundary:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;

class StatementDeliveryServiceTest {

    @Test
    void doesNotUseMailSenderForInvalidRecipient() {
        JavaMailSender sender = mock(JavaMailSender.class);
        StatementMimeFactory factory =
                new StatementMimeFactory(sender);

        StatementDeliveryService service =
                new StatementDeliveryService(factory, sender);

        StatementMailRequest request = new StatementMailRequest(
                "invalid-address",
                "Statement notice",
                "Please see the attached file.",
                "statement.pdf",
                new ByteArrayResource(
                        "test-pdf".getBytes(StandardCharsets.UTF_8)
                )
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> service.send(request)
        );

        verifyNoInteractions(sender);
    }
}
~~~

Because the factory validates the recipient before calling `createMimeMessage`, zero calls reach the mock sender.

### 12.1. If architecture does not separate as in the example

Another factory might call `createMimeMessage` before validating. In that case, assert at minimum:

~~~java
verify(sender, never()).send(
        any(MimeMessage.class)
);
~~~

Do not force tests to match an internal call order outside the contract.

### 12.2. What this test does not claim

It does not prove the server will accept valid addresses. It only proves **inputs invalid under policy never trigger a send call**.

## 13. Test Subject containing control characters

Header injection is an input bug class with security impact.

Example input:

~~~text
November report
Bcc: outside@example.net
~~~

If an application builds raw headers from that string manually, data can be misinterpreted during serialization. Even though Jakarta Mail APIs have their own header handling, **single-line input validation remains valuable** when the contract forbids newlines in subjects.

Test example:

~~~java
@Test
void rejectsCarriageReturnOrNewlineInSubject() {
    String injected = "Statement\r\nBcc: outside@example.net";

    assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.validateSingleLine(
                    injected,
                    "subject"
            )
    );
}
~~~

### 13.1. Check other control characters

CR and LF are not the only ones. Other control characters can make logs and headers unreadable or ambiguous. The example factory uses **Character.isISOControl(...)** to enforce a strict single-line policy.

### 13.2. Body is a multi-line field

Do not apply the same single-line validator to the body. Plain-text emails normally require valid line breaks.

The goal is distinguishing:

- **Header-like fields:** single-line, checked for control characters.
- **Body:** multi-line allowed; still validate content and length per business rules.

### 13.3. Vietnamese Unicode data

Strings like **"Thông báo sao kê"** or **"Nguyễn Ánh"** are not control characters and must be processed properly. Never strip Vietnamese diacritics merely to avoid header bugs.

## 14. Test nonexistent Resources

A `ClassPathResource` can be instantiated even when the given path does not point to a real file.

~~~java
Resource resource =
        new ClassPathResource("mail/missing.pdf");
~~~

Constructing a `Resource` object does not mean a stream was opened or content verified. Tests should exercise **preflight** logic in the application.

### 14.1. Test with a mock Resource

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;

@Test
void rejectsMissingResource() {
    Resource resource = mock(Resource.class);

    when(resource.exists()).thenReturn(false);

    IllegalArgumentException ex = assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.readPdf(resource)
    );

    assertEquals(
            "attachment resource is unavailable",
            ex.getMessage()
    );

    verify(resource).exists();
    verify(resource, never()).getInputStream();
}
~~~

Mocking frees the test from depending on whether any specific file exists on the classpath.

### 14.2. When to use a real ClassPathResource?

An integration/resource-packaging test can verify a template or sample attachment is actually packaged on the classpath. That asks a different question: **does the build artifact contain the right resource?**

Unit tests for missing-resource error handling should use fakes/mocks to avoid coupling to whole-project packaging.

## 15. Test Resources that exist yet are unreadable

A resource can exist yet fail readability checks or lack permissions.

~~~java
@Test
void rejectsUnreadableResource() {
    Resource resource = mock(Resource.class);

    when(resource.exists()).thenReturn(true);
    when(resource.isReadable()).thenReturn(false);

    assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.readPdf(resource)
    );

    verify(resource, never()).getInputStream();
}
~~~

If `Resource` returns `isReadable=false`, the factory rejects before opening the stream.

### 15.1. Do not use OS permissions to test this branch

A test altering file permissions may behave differently across Windows, Linux, containers, or privileged runners. Mockito lets you simulate the exact condition portably across operating systems.

### 15.2. isReadable() does not replace getInputStream()

Even when `isReadable()` returns `true`, `getInputStream()` can still throw `IOException`. Test this branch separately.

## 16. Test IOException when opening a resource

For example, the resource claims to be readable yet fails when opening the stream:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.UncheckedIOException;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;

@Test
void wrapsIOExceptionWhenStreamCannotBeOpened()
        throws Exception {

    Resource resource = mock(Resource.class);

    when(resource.exists()).thenReturn(true);
    when(resource.isReadable()).thenReturn(true);

    when(resource.getInputStream())
            .thenThrow(new IOException("simulated read failure"));

    UncheckedIOException ex = assertThrows(
            UncheckedIOException.class,
            () -> StatementMimeFactory.readPdf(resource)
    );

    assertInstanceOf(IOException.class, ex.getCause());
}
~~~

This is a **resource-read error**, not an SMTP 4xx/5xx error. Retrying with the same data may help if the source suffered a transient outage, yet if the file was deleted or the path is wrong, data or system configuration must be fixed.

### 16.1. Preserve the cause

Wrapping `IOException` in `UncheckedIOException` gives callers a runtime exception preserving the original cause. Never swallow `IOException` and return an empty `byte[]`, or an email could be sent with a broken attachment.

### 16.2. Never log file contents on read failure

An `IOException` does not require dumping attachment bytes or sensitive paths. Log a valid resource identifier and error category according to policy.

## 17. Test empty files

A file can exist and be readable yet contain zero bytes. If business rules require non-empty PDF content, that is invalid input.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;

@Test
void rejectsEmptyAttachment() {
    ByteArrayResource empty =
            new ByteArrayResource(new byte[0]);

    assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.readPdf(empty)
    );
}
~~~

**ByteArrayResource** is very convenient for testing payloads without creating temporary files.

### 17.1. When can an empty file be valid?

It depends on the contract. A placeholder attachment might permit 0 bytes in some systems. In that case, tests must reflect the real rule rather than hardcoding the PDF example logic.

### 17.2. Empty differs from missing

- **Missing:** resource could not be found or accessed.
- **Empty:** resource exists yet has length 0.

Distinguishing these two errors clarifies operational alerts and prevents fixing the wrong problem.

## 18. Test resource size limits

An abnormally large resource can exhaust memory or cause the SMTP provider to reject the message due to size.

The example factory enforces a 1 MiB limit:

~~~java
private static final int MAX_PDF_BYTES = 1_048_576;
~~~

Test:

~~~java
@Test
void rejectsAttachmentLargerThanLimit() {
    byte[] oversized = new byte[1_048_577];

    ByteArrayResource resource =
            new ByteArrayResource(oversized);

    assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.readPdf(resource)
    );
}
~~~

### 18.1. Bounded reads avoid memory spikes

For uploaded files or remote resources, avoid calling `readAllBytes()` without an upper size bound. A huge input can spike memory usage inside a worker.

### 18.2. Outbound MIME size can exceed raw bytes

Binary attachments are normally Base64-encoded in MIME, inflating transmitted size beyond the original byte count. Therefore, application limits on raw files must leave headroom for the provider's total message size limit.

### 18.3. Test exact thresholds

If the contract permits up to `1_048_576` bytes, include both a case at the exact threshold (accepted) and one byte over (rejected). This is boundary-value testing.

## 19. Test invalid filenames

The filename used in `Content-Disposition` is recipient-visible metadata. If derived from inputs, reject inappropriate values.

Examples to reject under the sample factory:

~~~text
null
""
" "
"../invoice.pdf"
"..\\invoice.pdf"
"folder/invoice.pdf"
"invoice.pdf\r\nBcc: someone@example.net"
"invoice.exe"
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

@ParameterizedTest
@ValueSource(strings = {
        "../invoice.pdf",
        "..\\invoice.pdf",
        "folder/invoice.pdf",
        "invoice.pdf\r\nBcc: someone@example.net",
        "invoice.exe"
})
void rejectsUnsafeAttachmentFilename(String filename) {
    assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.validateFilename(filename)
    );
}
~~~

### 19.1. Filename is not a resource path

Never concatenate a user-supplied filename straight into a file-reading path:

~~~java
// Avoid:
new FileSystemResource(
        uploadDirectory + "/" + userProvidedFilename
);
~~~

That can introduce **path traversal** bugs or read files outside the allowed directory.

In a safe design, resolve a system-verified resource by internal ID; the displayed filename is separate, controlled metadata.

### 19.2. Checking the .pdf extension alone is not enough

A filename ending in `.pdf` does not prove the content is a PDF. If format verification is required, run byte validation or an appropriate parser in a separate layer and test spoofed content types.

### 19.3. Unicode filenames

A name like **"Hóa đơn tháng 11.pdf"** may be a valid requirement. Validation should block control/path characters rather than stripping all Vietnamese characters.

## 20. ByteArrayResource and re-readable streams

Jakarta Mail may need to open a MIME part's stream more than once, for instance when computing or serializing content. Therefore, an `InputStreamSource` used for attachments must supply consistent data per the overload's contract.

**ByteArrayResource** usually fits well when bytes are already in memory:

~~~java
byte[] bytes = ...;

ByteArrayResource resource = new ByteArrayResource(bytes);

helper.addAttachment(
        "invoice.pdf",
        resource,
        "application/pdf"
);
~~~

### 20.1. Test reading the stream multiple times

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;

@Test
void byteArrayResourceCanBeReadRepeatedly()
        throws Exception {

    byte[] expected = new byte[] {1, 2, 3, 4};
    ByteArrayResource resource =
            new ByteArrayResource(expected);

    byte[] first;
    byte[] second;

    try (InputStream in = resource.getInputStream()) {
        first = in.readAllBytes();
    }

    try (InputStream in = resource.getInputStream()) {
        second = in.readAllBytes();
    }

    assertArrayEquals(expected, first);
    assertArrayEquals(expected, second);
}
~~~

### 20.2. Handle InputStreamResource with caution

**InputStreamResource** typically wraps an already-open stream and does not guarantee creating a fresh stream once consumed. Some `MimeMessageHelper` overloads even reject such single-use sources because Jakarta Mail may need to re-read.

Never write tests expecting `InputStreamResource` to be repeatable in all cases. If the original source allows only one read, buffer into a size-bounded `byte[]` or store in managed temporary storage providing a repeatable `InputStreamSource`.

### 20.3. Never retry a consumed stream

If a send fails and a worker retries, never reuse an exhausted `InputStream`. You need a re-openable data source or a stable byte snapshot.

## 21. Test a real MimeMessage without SMTP

**JavaMailSenderImpl.createMimeMessage()** can construct an in-memory `MimeMessage` without opening an SMTP connection. Use it to verify MIME output.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class StatementMimeFactoryTest {

    @Test
    void buildsExpectedMimeWithoutSmtp() throws Exception {
        JavaMailSenderImpl sender =
                new JavaMailSenderImpl();

        StatementMimeFactory factory =
                new StatementMimeFactory(sender);

        byte[] pdfBytes =
                "PDF fixture".getBytes(StandardCharsets.UTF_8);

        StatementMailRequest request =
                new StatementMailRequest(
                        "an@example.net",
                        "Sao kê tháng 11",
                        "Xin chào Nguyễn An, xem file đính kèm.",
                        "statement.pdf",
                        new ByteArrayResource(pdfBytes)
                );

        MimeMessage message = factory.prepare(request);
        message.saveChanges();

        InternetAddress from =
                (InternetAddress) message.getFrom()[0];

        InternetAddress to =
                (InternetAddress) message.getRecipients(
                        Message.RecipientType.TO
                )[0];

        assertEquals(
                "billing@example.org",
                from.getAddress()
        );
        assertEquals(
                "an@example.net",
                to.getAddress()
        );
        assertEquals(
                "Sao kê tháng 11",
                message.getSubject()
        );

        MimeMultipart mixed =
                (MimeMultipart) message.getContent();

        assertEquals(2, mixed.getCount());

        assertTrue(
                mixed.getBodyPart(0).getContentType()
                        .toLowerCase(java.util.Locale.ROOT)
                        .startsWith("text/plain")
        );

        assertEquals(
                "statement.pdf",
                mixed.getBodyPart(1).getFileName()
        );

        byte[] actualPdf;

        try (InputStream in =
                     mixed.getBodyPart(1).getInputStream()) {
            actualPdf = in.readAllBytes();
        }

        assertArrayEquals(pdfBytes, actualPdf);
    }
}
~~~

### 21.1. What is this test verifying?

- `MimeMessage` has the expected From and To.
- Subject preserves Unicode content.
- Both text body and an attachment exist.
- Filename is exact.
- Attachment bytes match after reading from the MIME part.

### 21.2. The test does not check an SMTP server

There is no `send(...)` call. Therefore, the test needs no host, username, password, or network.

### 21.3. MIME structure depends on the helper mode

The example intentionally uses **MULTIPART_MODE_MIXED** to keep the tree simple for the test. If the application uses **MULTIPART_MODE_MIXED_RELATED** or inline resources, MIME can nest multiparts. Assertions must then follow the actual structure rather than assuming body part 1 is always the attachment.

## 22. Verify resource errors do not call send using Mockito

This test pairs a real factory with a mock `JavaMailSender` to confirm the service fails fast before transport.

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;

@Test
void missingAttachmentDoesNotTriggerSend() {
    JavaMailSender sender = mock(JavaMailSender.class);

    StatementMimeFactory factory =
            new StatementMimeFactory(sender);

    StatementDeliveryService service =
            new StatementDeliveryService(factory, sender);

    Resource resource = mock(Resource.class);
    when(resource.exists()).thenReturn(false);

    StatementMailRequest request =
            new StatementMailRequest(
                    "an@example.net",
                    "Statement",
                    "Notification content.",
                    "statement.pdf",
                    resource
            );

    assertThrows(
            IllegalArgumentException.class,
            () -> service.send(request)
    );

    verifyNoInteractions(sender);
}
~~~

This test demonstrates **no connection, no message sent** when resource data is invalid.

If an implementation creates the `MimeMessage` before checking the resource, the test may simply assert:

~~~java
verify(sender, never()).send(any(MimeMessage.class));
~~~

What must be protected is **no send side effect**, not always forbidding Java object creation.

## 23. Verify the positive path via ArgumentCaptor

Negative tests alone are insufficient. If the factory always threw an exception, every bad-input test would still pass.

For valid data, confirm the service submits the built message.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.util.Properties;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;

@Test
void validRequestPassesMimeMessageToSender()
        throws Exception {

    JavaMailSender sender = mock(JavaMailSender.class);

    MimeMessage message =
            new MimeMessage(Session.getInstance(new Properties()));

    when(sender.createMimeMessage()).thenReturn(message);

    StatementMimeFactory factory =
            new StatementMimeFactory(sender);

    StatementDeliveryService service =
            new StatementDeliveryService(factory, sender);

    StatementMailRequest request =
            new StatementMailRequest(
                    "an@example.net",
                    "Statement",
                    "Please see the report.",
                    "statement.pdf",
                    new ByteArrayResource(new byte[] {1, 2, 3})
            );

    service.send(request);

    ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);

    verify(sender, times(1)).send(captor.capture());

    assertEquals("Statement", captor.getValue().getSubject());

    verify(sender, times(1)).createMimeMessage();
    verifyNoMoreInteractions(sender);
}
~~~

Mockito only simulates the `JavaMailSender` boundary. It sends no real emails.

### 23.1. Why is a captor useful?

It shows the service did not merely call `send` generically, it passed a `MimeMessage` holding the expected data.

### 23.2. No need to assert every MIME part in service tests

The MIME factory test already verified detailed content. Service tests only need to confirm the right object was built and submitted the right number of times, avoiding redundant assertions.

## 24. Resource errors can occur during serialization or sending

Not every codebase performs preflight reads like the example factory.

~~~text
helper.addAttachment(resource)
       |
       v
MimeMessage holds DataHandler/DataSource
       |
       v
message.writeTo(...) or transport send
       |
       v
getInputStream() is called
       |
       +-- IOException
~~~

Consequently, a test that only calls `addAttachment` and asserts no exception **does not guarantee the attachment can be sent**.

### 24.1. How to catch errors before SMTP

Two approaches:

1. **Preflight the resource:** open and check the stream before sending, as in the example factory.
2. **Serialize MIME into a test buffer:** call `message.writeTo(OutputStream)` in tests to force reading data without connecting to SMTP.

Example for small MIME messages in tests only:

~~~java
ByteArrayOutputStream out =
        new ByteArrayOutputStream();

message.saveChanges();
message.writeTo(out);

assertTrue(out.size() > 0);
~~~

Serialization can expose stream errors occurring lazily. For large attachments, never implement production preflight by serializing the entire email into unbounded memory.

### 24.2. Distinguish MIME serialization from SMTP transport

A message that serializes into a buffer is not guaranteed to be accepted by the SMTP provider. Conversely, a resource error during serialization is not an SMTP 4xx/5xx reply.

### 24.3. One error may be wrapped in another exception

An `IOException` from a `Resource` may be wrapped in `MessagingException` or Spring's `MailException` as it crosses layers. When testing a factory that reads streams directly, assert `UncheckedIOException` directly. When testing transport, inspect the cause chain and avoid assuming the outermost exception is identical across all versions.

## 25. Test inline resources

Inline images use a mechanism similar to attachments while adding a **Content-ID** for HTML references.

Example:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setText(
        "<html><body><img src=\"cid:companyLogo\"></body></html>",
        true
);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Test cases:

- Image resource does not exist.
- Opening the resource stream fails.
- Empty image bytes if disallowed.
- Declared MIME type is mismatched.
- Content-ID used in HTML does not match the added ID.
- Resource is not re-readable.
- Image exceeds size limit.
- Inline resource was mistakenly added as an attachment or vice versa.

### 25.1. Content-ID is not a filename

HTML references **cid:companyLogo**. It must match the inline part's Content-ID, regardless of the filename on the classpath.

### 25.2. Ordering when adding inline resources

When using `MimeMessageHelper`, typically set the HTML body first and call `addInline` afterward to avoid compatibility issues in some mail clients.

### 25.3. Never use inline Resources to fetch arbitrary URLs

A user-supplied URL can lead to SSRF or internal infrastructure access. If the application supports images from URLs, use a dedicated downloader with allowlists, timeouts, byte caps, and network policies; unit tests must cover rejected URLs.

## 26. Test errors from path traversal and untrusted sources

A request may contain:

~~~text
attachmentPath = ../../private/secret.pdf
~~~

If the system passes this path straight into `FileSystemResource` unchecked, the application can read files outside permitted boundaries.

Better architecture:

~~~text
Request attachmentId
        |
        v
Authorization check
        |
        v
Lookup trusted metadata
        |
        v
Resolve resource in approved storage
        |
        v
Read with size/type policy
~~~

Unit tests should verify:

- Attachment ID the user is unauthorized to access → rejected.
- Path escaping the allowed root → rejected.
- URL pointing to an internal/forbidden address → rejected when source is a URL.
- Filename containing separators → rejected per policy.
- Empty or oversized file content → rejected.
- Nonexistent resource → raises error, no mail sent.

Do not rely on validating **attachmentFilename** alone if code also accepts a separate **resource path**. Display filename and file-reading location are two distinct inputs that must be controlled separately.

## 27. Resources are byte payloads, not mandatory UTF-8 strings

PDFs, PNGs, and binary attachments must be handled as raw bytes.

Do not do:

~~~java
String text = new String(
        pdfBytes,
        StandardCharsets.UTF_8
);

byte[] converted = text.getBytes(
        StandardCharsets.UTF_8
);
~~~

Decoding binary files as text corrupts the data.

Right:

~~~java
helper.addAttachment(
        "statement.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

For CSV or TXT, charset matters when converting text content into bytes. Tests can verify UTF-8 if that is the contract for text attachments.

### 27.1. MIME type is part of the contract

Tests can verify an attachment declares **application/pdf** for PDFs and **image/png** for PNGs. Yet declaring a MIME type does not prove the file actually has that format.

### 27.2. Truncated data also needs checking

For documents with a checksum, exact length, or valid signature, test byte/size preservation before sending. Never assert merely that `InputStream` returns at least one byte.

## 28. Do application error tests need an SMTP mock?

For bad addresses, missing resources, or stream `IOException`s, **no SMTP mock server is needed**. Unit tests can use:

- JUnit 5.
- Mockito mock `Resource`.
- `ByteArrayResource`.
- Mock `JavaMailSender`.
- `JavaMailSenderImpl` to construct an in-memory `MimeMessage`.

An SMTP capture server or fake transport is useful in integration tests when you need to know:

- The message serializes and transmits over transport.
- SMTP returns 550 at `RCPT TO`.
- AUTH/TLS are configured properly.
- The provider exhibits partial-recipient acceptance.
- Connections can time out after `DATA`.

Never confuse **syntactically invalid addresses** (unit tests) with **nonexistent mailboxes** (server/provider signals that may arrive after submission).

## 29. Classify errors to choose a retry policy

A system using an outbox or worker can classify:

| Error | Category | Typically appropriate action |
| --- | --- | --- |
| Null or blank To | Invalid input | Fix data, never retry as-is |
| AddressException during preparation | Invalid input/MIME | Inspect source, never retry blindly |
| Subject with out-of-contract CR/LF | Invalid header input | Reject and fix |
| Wrong attachment path | Resource config/data | Fix path, never retry with same data |
| Missing file | Resource unavailable | Check source; retry only if contract expects delayed availability |
| Permission denied | Resource access | Fix permissions, never hammer with retries |
| Transient stream break | Resource I/O | Bounded retries possible if source can recover |
| Empty/truncated file | Invalid content | Fix/reconcile file |
| Oversized file | Policy violation | Never retry with same bytes |
| AUTH 535 | SMTP account/config | Stop blind retries, fix credentials |
| Transient SMTP 421/450 | Transport transient | Backoff and bounded retries |
| Timeout after DATA | Unknown outcome | Consider duplicate risk and reconcile |

Never lump all `IllegalArgumentException`, `UncheckedIOException`, `MessagingException`, and `MailException` into one **retryable** bucket.

### 29.1. Fail-fast validation reduces wasted retries

If an outbox job holds a bad file path, retrying 100 times will not conjure the file into existence. That signals bad config or invalid data, not a transient SMTP outage.

### 29.2. Resources disappearing after commit

If an outbox stores only a path to a temporary file, the file may be cleaned up before the worker runs. Decide whether to persist byte snapshots, durable storage objects, or references with sufficient retention.

Unit tests for missing files expose the error branch, yet storage/retention design solves the systemic root cause.

## 30. Ensure tests never leak data

To test errors safely:

- Use recipients in example domains such as `example.net`.
- Use dummy PDF/PNG bytes, never real customer documents.
- Never include real passwords or tokens in fixtures.
- Never log entire MIME messages just to inspect errors.
- Never expose paths containing sensitive data in broad-access logs.
- Never call real URLs or real SMTP servers unnecessarily.
- When using temporary files, ensure test cleanup deletes them without leaving unnecessary copies.

### 30.1. Exception messages should be helpful without containing secrets

Reasonable example:

~~~text
attachment resource is unavailable
~~~

Instead of:

~~~text
Cannot open C:\private\users\customer-42\statement.pdf
~~~

when real paths are sensitive data. Log an internal resource reference instead of raw paths.

### 30.2. Never print raw recipients in validation logs

In many systems, email addresses are personal data. A unit test does not need to assert that an exception message contains a real email; assert the exception type and rejected field name instead.

## 31. Comprehensive test matrix for addresses and resources

| Group | Input | Expected outcome |
| --- | --- | --- |
| Recipient | null | Reject, no send |
| Recipient | empty/blank | Reject, no send |
| Recipient | missing local-part or domain | Reject per policy |
| Recipient | multiple addresses in single field | Reject or handle per contract |
| Recipient | control character/CRLF | Reject, no send |
| Recipient | supported Unicode address | Accept per application policy |
| From/Reply-To | misconfigured | Reject before send |
| CC/BCC | contains invalid element | Never silently send to remaining recipients |
| Subject | blank | Reject |
| Subject | contains CR/LF | Reject |
| Body | null or blank | Reject if contract requires text |
| Resource | null | Reject |
| Resource | `exists=false` | Reject |
| Resource | `isReadable=false` | Reject |
| Resource | `getInputStream()` throws `IOException` | Propagate/wrap, no send |
| Resource | 0 bytes | Reject if content required |
| Resource | exact size limit | Accept |
| Resource | 1 byte over limit | Reject |
| Resource | non-repeatable `InputStream` | Keep out of contracts requiring re-reads |
| Resource | valid bytes | `MimeMessage` holds exact bytes |
| Filename | path separator or CRLF | Reject |
| Filename | valid Unicode | Accept if product supports it |
| Content type | outside allowed types | Reject/adjust per policy |
| Inline image | CID mismatches HTML | Caught by structure/content tests |
| Service | invalid input | Never calls `JavaMailSender.send` |
| Service | valid input | Calls `send` once with expected message |

This matrix is a design guide for **test inputs and expected behavior**. Policies like whether empty files are valid, byte limits, and IDN/SMTPUTF8 support must match application needs.

## 32. Common anti-patterns

### 32.1. Only asserting message != null

~~~java
assertNotNull(message);
~~~

A message with the wrong recipient, blank Subject, or missing attachment is still non-null. Assert specific fields or test fail-fast behavior.

### 32.2. Assuming setTo always validates addresses

**SimpleMailMessage.setTo(...)** mostly stores data. Never rely on it to verify mailbox existence or catch all syntax errors.

### 32.3. Calling addAttachment and concluding the resource is readable

Stream reading may be deferred. To be sure before sending, preflight the resource or serialize in tests.

### 32.4. Retrying every IOException

A bad file path or permanent permission denial will not be cured by a quick retry.

### 32.5. Using an already-consumed InputStreamResource

A single-use source can fail when Jakarta Mail re-reads it. Use `ByteArrayResource` or a source able to open fresh streams.

### 32.6. Using real files in every unit test

Filesystem-coupled tests are slow, less portable, and environment-sensitive. Prefer mock `Resource` and `ByteArrayResource` in unit tests.

### 32.7. Ignoring nulls inside recipient arrays

A list of three recipients where one is null needs explicit policy handling. Never silently send to the rest if business rules forbid partial sends.

### 32.8. Using display filenames as filesystem paths

This creates path traversal risks. Separate display filenames from authorized internal resource references.

### 32.9. Mocking everything, including the object under test

If you want to know whether `MimeMessage` has the right addresses and attachments, construct a real in-memory `MimeMessage`. Mock only the boundary you need to isolate.

### 32.10. Running real SMTP in unit tests

That ties tests to network, accounts, providers, and risks emailing real users. Data unit tests should remain independent of SMTP.

## 33. Frequently asked questions

**1. Why does testing address errors matter if SMTP would reject them anyway?**

Because catching errors early avoids side effects, cuts wasted retries, and produces clear error messages. SMTP can reject for many reasons unrelated to application input validation.

**2. Does `SimpleMailMessage.setTo("bad-address")` always throw an exception?**

Never assume so. `SimpleMailMessage` is a plain-text data holder. Syntax checks belong in the application or an appropriate transport layer.

**3. Does `InternetAddress.validate()` know whether a mailbox exists?**

No. It checks API syntax only, without verifying mailbox ownership or whether a provider will accept mail.

**4. When should I use MimeMessageHelper instead of SimpleMailMessage?**

When you need HTML, multipart, attachments, inline resources, or rich MIME features. `SimpleMailMessage` fits plain-text emails.

**5. Why might `addAttachment` not immediately throw on a missing file?**

Some Jakarta Mail paths store the data source on the MIME part and open the stream only during serialization/send. For fail-fast checks, read and validate beforehand.

**6. What are the advantages of ByteArrayResource for unit tests?**

It holds bytes in memory, avoids real files, and provides fresh `InputStream` instances for repeated reads.

**7. Should InputStreamResource be used for attachments?**

Use caution because an already-open stream is typically single-use; some helper overloads reject non-repeatable sources. When repeated reads are needed, use a repeatable source.

**8. When `resource.exists()` returns true, can I skip testing `getInputStream()`?**

No. The resource can still fail to read due to permissions, network issues, or state changes. Test stream open/read failures separately.

**9. Should empty files be tested as errors?**

Yes, if the contract requires non-empty content. If the product permits 0-byte files, expected behavior must differ accordingly.

**10. Should size limits be tested?**

Yes, when the system or provider enforces limits. Testing at the exact limit and one byte over is good practice.

**11. Should `.pdf` file extensions be checked?**

It can serve as a display rule, yet extensions never verify file content is PDF. Add content validation separately when business rules require it.

**12. Why test CR/LF in Subject and filenames?**

To keep out-of-contract control characters out of header fields and prevent injection or malformed headers.

**13. Do MimeMessage unit tests need an SMTP account?**

No. Use `JavaMailSenderImpl.createMimeMessage()` or `new MimeMessage(Session.getInstance(...))` to build messages in memory.

**14. How do I verify the service does not send when a resource is missing?**

Mock `JavaMailSender`, call the service with a missing `Resource`, assert the exception, and verify `sender.send` was never called.

**15. Can permission failures be simulated without changing real file permissions?**

Yes. Mock `Resource.isReadable()` to return `false` or `Resource.getInputStream()` to throw `IOException`.

**16. Is a single-read attachment sufficient?**

Not always. MIME providers may re-read it. Use a repeatable source or byte snapshot when design requires it.

**17. Do MIME serialization tests replace SMTP integration tests?**

No. They test message construction/serialization, not authentication, TLS, `RCPT TO`, or SMTP server replies.

**18. Can nonexistent mailboxes be unit tested?**

You can unit test **handling logic** when a provider returns a user-unknown signal using a fake, yet you cannot confirm a real mailbox exists solely by unit testing the address.

**19. What if an attachment changes between validation and sending?**

That is a read-timing and source-durability issue. Byte snapshots or versioned/checksummed storage objects keep payloads consistent.

**20. Should resource failures be retried?**

It depends on the cause. Transient failures can have bounded retries; missing files, bad paths, empty payloads, or oversized files typically require fixing data or configuration first.

## 34. Key takeaways on testing invalid addresses and resources

**Testing invalid address and resource failures means testing input boundaries before emails are sent.** In Spring Framework Mail, never rely on `SimpleMailMessage` setters to validate mailboxes; define an explicit address policy, check null/blank/syntax, distinguish single recipients from lists, control From/To/Reply-To/CC/BCC, and reject control characters in headers.

For attachments or inline resources, **an existing `Resource` is not guaranteed to be readable**. Files may be missing, unreadable, empty, oversized, or backed by an already-consumed `InputStream`. Test `exists`, `isReadable`, `getInputStream`, `IOException`, byte length, filename, content type, and re-readability independently. When fail-fast behavior is needed, perform bounded reads and use `ByteArrayResource` or repeatable sources before handing MIME to transport.

Use **JUnit 5, Mockito, fake `Resource`s, `ByteArrayResource`, and real in-memory `MimeMessage`s** to cover both valid and invalid paths. Negative tests must verify **`JavaMailSender.send(...)` is never called** when data is rejected; positive tests must verify the message is built properly and handed to the sender the exact number of times. Do not turn these into SMTP integration tests, do not blindly retry permanent data bugs, and never put real user data in fixtures.

**Successfully preparing a message differs from SMTP accepting it, and SMTP acceptance differs from the recipient receiving or reading the email.** Keeping these boundaries separate makes tests fast, deterministic, and able to catch data errors before sending side effects occur.
