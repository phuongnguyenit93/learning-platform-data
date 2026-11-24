# Unit Testing Data Used to Build SimpleMailMessage

In Spring Framework Mail, **SimpleMailMessage** is the object used to describe a **plain-text** email: sender, recipients, Reply-To, CC, BCC, sent date, subject, and body. An application typically takes these values from business data and then calls **MailSender.send(SimpleMailMessage)** to send the email.

A data bug can appear even before the application connects to the SMTP server. For example: an email is sent to the wrong person, the subject contains the wrong order number, the body uses the wrong amount, Reply-To points to an unmanaged mailbox, or the recipient information is empty. If you only test by checking that "the email was sent," these bugs can be hard to detect and cause real-world consequences.

**Unit testing the data used to build SimpleMailMessage** verifies that, for a given business input, the application produces the right fields and the right email content. In most cases, **there is no need to run an SMTP server, no need for a real mail account, and no need to send emails externally**.

Common model:

~~~text
Business data / DTO
        |
        v
Validate and normalize
        |
        v
SimpleMailMessage factory / mapper
        |
        v
SimpleMailMessage
        |
        v
MailSender.send(...)
~~~

There are two complementary testing points:

1. **Testing the factory/mapper:** pass sample data in, receive a SimpleMailMessage, and directly assert the message properties.
2. **Testing the sending service:** mock MailSender, call the service, use ArgumentCaptor to capture the SimpleMailMessage passed to send, and inspect it.

These two test styles tell you that the data was built properly and that the service actually passed the right message to the sender; **they do not claim that SMTP accepted it or that the recipient received the email**.

## 1. What data does SimpleMailMessage contain?

SimpleMailMessage supports common fields:

| Field | Setter API | Getter API for assertion | Meaning |
| --- | --- | --- | --- |
| Sender | **setFrom(...)** | **getFrom()** | From address |
| Reply-To | **setReplyTo(...)** | **getReplyTo()** | Address to receive replies |
| Primary recipients | **setTo(...)** | **getTo()** | Array of To addresses |
| CC | **setCc(...)** | **getCc()** | Array of carbon-copy recipients |
| BCC | **setBcc(...)** | **getBcc()** | Array of blind carbon-copy recipients |
| Sent date | **setSentDate(...)** | **getSentDate()** | java.util.Date value |
| Subject | **setSubject(...)** | **getSubject()** | Email subject |
| Text body | **setText(...)** | **getText()** | Plain text body |

Example:

~~~java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage message = new SimpleMailMessage();

message.setFrom("orders@example.org");
message.setTo("an@example.net");
message.setReplyTo("support@example.org");
message.setSubject("Xác nhận đơn hàng ORDER-2026-001");
message.setText(
        "Xin chào Nguyễn An,\n\n"
      + "Đơn hàng ORDER-2026-001 đã được xác nhận."
);
~~~

This is an operation that creates a Java object. **There is no SMTP connection yet** until a MailSender actually sends the message.

### 1.1. SimpleMailMessage is plain text

SimpleMailMessage is not the right choice for building HTML, inline images, or attachments. If those MIME parts are needed, use **MimeMessage**, **MimeMessageHelper**, and **JavaMailSender**.

Testing SimpleMailMessage should focus on:

- From/To/Reply-To/CC/BCC values.
- Subject.
- Text content and line breaks.
- SentDate if the application sets it.
- Rules for building the message from the model.
- Behavior with valid and invalid inputs.

Do not expect HTML properties or attachments to appear in this object.

### 1.2. setTo(...) accepts one or more addresses

Even when setting a single address:

~~~java
message.setTo("an@example.net");
~~~

**getTo()** returns a **String[]** array. Therefore, the test should use:

~~~java
assertArrayEquals(
        new String[] {"an@example.net"},
        message.getTo()
);
~~~

Do not use assertEquals with a single String to compare directly against String[].

### 1.3. CC and BCC do not need to appear in every email

If the business logic does not require CC/BCC, you can verify that these fields **are not set**. With a newly created SimpleMailMessage where CC/BCC have not been set, the getters usually return null.

That is a valuable test case: avoiding accidentally sending extra information to an admin address or unintended recipients.

## 2. Define the data contract before writing tests

A unit test is only useful if you know what a **correct message** means.

Example business requirements for an order confirmation email:

| Source data | Mail field | Rule |
| --- | --- | --- |
| Customer address | To | A single normalized and syntax-validated address |
| System address | From | Fixed configuration, not taken from customer input |
| Support mailbox | Reply-To | Controlled support address |
| Order number | Subject and text | The same order number |
| Customer name | Text | Contains the name prepared in the DTO |
| Total amount | Text | Amount of the exact order, formatted consistently |
| Confirmation timestamp | SentDate | Deterministic value, independent of random time during tests |
| CC/BCC | None | Do not send extra copies outside requirements |

Sample valid input:

~~~text
recipientEmail = an@example.net
customerName   = Nguyễn An
orderNumber    = ORDER-2026-001
totalAmount    = 500000
confirmedAt    = 2026-11-12T08:30:00Z
~~~

Expected output:

~~~text
From: orders@example.org
To: an@example.net
Reply-To: support@example.org
Subject: Xác nhận đơn hàng ORDER-2026-001
SentDate: 2026-11-12T08:30:00Z

Xin chào Nguyễn An,

Đơn hàng ORDER-2026-001 đã được xác nhận.
Tổng tiền: 500000 VND.

Trân trọng,
Đội ngũ bán hàng
~~~

This format is chosen so the example tests remain **independent of the number separator conventions and locale of the runner machine**. In a real product, locale-based currency formatting may differ and requires a corresponding test contract.

## 3. Separate business data from the sending process

A service that simultaneously queries the database, checks the order, builds the message, and calls SMTP is harder to unit test:

~~~java
public void sendConfirmation(Long id) {
    Order order = orderRepository.findById(id).orElseThrow();
    SimpleMailMessage message = new SimpleMailMessage();

    // Query additional data, build text, get current date...
    mailSender.send(message);
}
~~~

Tests easily become coupled to the repository, the current time, mail configuration, and data outside the scope you want to verify.

Instead, split it into:

~~~text
OrderRepository / business service
                 |
                 v
         OrderMailData snapshot
                 |
                 v
      OrderMailMessageFactory
                 |
                 v
         SimpleMailMessage
                 |
                 v
         OrderMailService
                 |
                 v
          MailSender
~~~

Benefits:

- The factory/mapper can be tested with plain Java objects.
- MailSender can be mocked without opening a network connection.
- Data is snapshotted before sending, avoiding JPA lazy loading outside a transaction.
- When the plain-text template changes, factory tests show that the built values differ from before.
- Business errors and SMTP errors are not mixed in a single unit test.

## 4. Create a strongly typed input DTO

Java record example:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderMailData(
        String recipientEmail,
        String customerName,
        String orderNumber,
        BigDecimal totalAmount,
        Instant confirmedAt
) {}
~~~

These fields represent the data required to build a confirmation notification. There is no need to pass the entire Order or Customer entity into the mail factory.

### 4.1. Why use a DTO?

If tests read directly from a JPA entity, they can depend on:

- Persistence context and lazy associations.
- ORM constructors or configuration.
- Repository state.
- Calculation logic located in another service.
- The moment the data is loaded.

A DTO helps define a clear input and verify the message against a predictable **snapshot**.

### 4.2. A DTO does not automatically guarantee valid data

A Java record does not by default validate empty emails, negative amounts, or null dates. Therefore, validation rules can live in the DTO constructor, the factory, or the business layer.

More important than the exact location is that **the contract must be clear and testable**: which inputs are accepted, which inputs are rejected, and whether normalization is performed.

## 5. Write a factory to build SimpleMailMessage

Example factory responsible for creating the message, **without sending via SMTP**:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import java.math.BigDecimal;
import java.util.Date;
import java.util.Objects;
import org.springframework.mail.SimpleMailMessage;

public final class OrderMailMessageFactory {

    private static final String FROM =
            "orders@example.org";

    private static final String REPLY_TO =
            "support@example.org";

    public SimpleMailMessage create(OrderMailData data) {
        Objects.requireNonNull(data, "data");

        String recipient = validateRecipient(data.recipientEmail());

        String customerName =
                requiredSingleLine(data.customerName(), "customerName");

        String orderNumber =
                requiredSingleLine(data.orderNumber(), "orderNumber");

        BigDecimal total =
                Objects.requireNonNull(
                        data.totalAmount(),
                        "totalAmount"
                );

        if (total.signum() < 0) {
            throw new IllegalArgumentException(
                    "totalAmount must not be negative"
            );
        }

        Date sentDate = Date.from(
                Objects.requireNonNull(
                        data.confirmedAt(),
                        "confirmedAt"
                )
        );

        String text =
                "Xin chào " + customerName + ",\n\n"
              + "Đơn hàng " + orderNumber
              + " đã được xác nhận.\n"
              + "Tổng tiền: " + total.toPlainString()
              + " VND.\n\n"
              + "Trân trọng,\n"
              + "Đội ngũ bán hàng";

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(FROM);
        message.setReplyTo(REPLY_TO);
        message.setTo(recipient);
        message.setSubject("Xác nhận đơn hàng " + orderNumber);
        message.setText(text);
        message.setSentDate(sentDate);

        return message;
    }

    private static String requiredSingleLine(
            String input,
            String field
    ) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank"
            );
        }

        String value = input.trim();

        if (value.indexOf('\r') >= 0 ||
                value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(
                    field + " must be single-line"
            );
        }

        return value;
    }

    private static String validateRecipient(String input) {
        String value = requiredSingleLine(
                input,
                "recipientEmail"
        );

        try {
            InternetAddress address =
                    new InternetAddress(value, true);

            address.validate();

            if (!value.equals(address.getAddress())
                    || address.isGroup()) {
                throw new IllegalArgumentException(
                        "Expected a single mailbox address"
                );
            }

            return value;
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Invalid recipientEmail syntax",
                    ex
            );
        }
    }
}
~~~

This is an example factory. The From/Reply-To addresses are hardcoded for clarity; in a real application, a controlled configuration that is tested separately can be injected.

### 5.1. What the factory guarantees

- Data must not be null.
- Required fields must have values.
- Customer name and order number are single-line.
- Recipient has valid mailbox syntax within Jakarta Mail's validation capabilities.
- Amount is non-negative according to the example order rule.
- Sent date is not null.
- From and Reply-To are controlled by the system.
- To, Subject, and Text come from the same DTO.
- CC/BCC are not set.

### 5.2. What the factory does not guarantee

- That the mailbox actually exists.
- That the recipient owns the address.
- That the SMTP server accepts the message.
- That the email has been delivered or read.
- That syntax checking via InternetAddress covers all internationalized email/SMTPUTF8 policies.
- That a non-negative amount suits every business case (for example, refunds may have separate rules).

Do not turn a unit test into a claim that real-world mail delivery will succeed.

## 6. Test the factory without mocking MailSender

Because the factory only builds objects, tests can call it directly and assert with JUnit 5.

Example test suite:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;

class OrderMailMessageFactoryTest {

    private final OrderMailMessageFactory factory =
            new OrderMailMessageFactory();

    private static OrderMailData sample() {
        return new OrderMailData(
                "an@example.net",
                "Nguyễn An",
                "ORDER-2026-001",
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z")
        );
    }

    @Test
    void createsExpectedSimpleMailMessage() {
        SimpleMailMessage message = factory.create(sample());

        assertEquals("orders@example.org", message.getFrom());

        assertArrayEquals(
                new String[] {"an@example.net"},
                message.getTo()
        );

        assertEquals(
                "support@example.org",
                message.getReplyTo()
        );

        assertEquals(
                "Xác nhận đơn hàng ORDER-2026-001",
                message.getSubject()
        );

        assertEquals(
                "Xin chào Nguyễn An,\n\n"
              + "Đơn hàng ORDER-2026-001 đã được xác nhận.\n"
              + "Tổng tiền: 500000 VND.\n\n"
              + "Trân trọng,\n"
              + "Đội ngũ bán hàng",
                message.getText()
        );

        assertEquals(
                Date.from(Instant.parse("2026-11-12T08:30:00Z")),
                message.getSentDate()
        );

        assertNull(message.getCc());
        assertNull(message.getBcc());
    }
}
~~~

This unit test does not start the Spring context and does not call SMTP.

### 6.1. Why assert enough fields?

If a test only checks:

~~~java
assertNotNull(message);
~~~

then a message with the wrong From, wrong To, or empty Subject can still pass. The goal is the **data contract**, so fields with business meaning must be asserted.

### 6.2. Test the complete text or individual parts?

Both approaches have distinct value:

- **assertEquals on the full text:** protects exact wording, whitespace, and line breaks, well suited for transactional emails with stable content.
- **assertTrue with contains:** checks specific facts when layout or wording is allowed to change.

If the contract requires a fixed notification text, comparing the full text catches even spacing and line-break bugs. If copywriting changes frequently, you can verify required facts and leave editorial content checking to another layer.

## 7. Test each field: From, To, Reply-To, CC, and BCC

Email addresses are data that directly affect **who receives the information**. Therefore, these assertions are just as important as the body.

### 7.1. From must come from controlled configuration

~~~java
assertEquals(
        "orders@example.org",
        message.getFrom()
);
~~~

If the application accepts user input, do not take From directly from an arbitrary profile field. From may need to match the sending account or a domain authorized by the provider.

### 7.2. To must match the business recipient

~~~java
assertArrayEquals(
        new String[] {"an@example.net"},
        message.getTo()
);
~~~

If the service accidentally takes an admin's email instead of the customer's, the test can catch it before an incident happens.

### 7.3. Reply-To differs from From

~~~java
assertEquals(
        "support@example.org",
        message.getReplyTo()
);
~~~

Reply-To determines where replies go in many email clients; it can differ from From. Do not mistakenly set Reply-To to the recipient's email or an unmonitored address.

### 7.4. CC/BCC do not appear unless required

~~~java
assertNull(message.getCc());
assertNull(message.getBcc());
~~~

This is a **data-leak prevention** test: a customer's order email must not silently send an extra copy to an out-of-contract address.

### 7.5. When the business case truly requires multiple recipients

Example:

~~~java
message.setTo(
        "an@example.net",
        "binh@example.net"
);
message.setCc("accounting@example.org");
~~~

Test:

~~~java
assertArrayEquals(
        new String[] {"an@example.net", "binh@example.net"},
        message.getTo()
);

assertArrayEquals(
        new String[] {"accounting@example.org"},
        message.getCc()
);
~~~

If recipient order does not matter under the contract, you can check set membership and length; if order is meaningful in the generated output, assertArrayEquals detects order changes.

Note: sending one message to multiple people can expose addresses in To/CC to other recipients. If privacy protection or independent per-recipient retry is needed, consider one mail message per recipient.

## 8. Test Subject and dynamic data

The Subject often combines a fixed prefix with a business identifier.

~~~java
message.setSubject(
        "Xác nhận đơn hàng " + data.orderNumber()
);
~~~

Tests should verify:

- The prefix is correct.
- The order number is correct.
- It does not pick up another order's number.
- There are no unexpected control newlines.
- Vietnamese Unicode is preserved.
- Subject is not empty.

Example:

~~~java
@Test
void subjectContainsCorrectOrderNumber() {
    SimpleMailMessage message = factory.create(sample());

    assertEquals(
            "Xác nhận đơn hàng ORDER-2026-001",
            message.getSubject()
    );
}
~~~

### 8.1. Test a different input to catch hard-coding bugs

If every test only uses ORDER-2026-001, a developer who accidentally hard-codes that value in the factory might go undetected.

Add another case:

~~~java
@Test
void subjectChangesWithOrderData() {
    OrderMailData another = new OrderMailData(
            "binh@example.net",
            "Trần Bình",
            "ORDER-2026-999",
            new BigDecimal("120000"),
            Instant.parse("2026-11-13T09:00:00Z")
    );

    SimpleMailMessage message = factory.create(another);

    assertEquals(
            "Xác nhận đơn hàng ORDER-2026-999",
            message.getSubject()
    );
}
~~~

### 8.2. Test that Subject does not contain unnecessary information

Do not concatenate passwords, OTPs, tokens, or sensitive data into the subject just for readability. A unit test can verify that the subject only contains components allowed by the contract.

## 9. Test plain-text body, Unicode, and line breaks

With SimpleMailMessage, the body is a text string. Common bugs:

- Missing an important paragraph.
- Wrong customer name.
- Wrong amount or currency unit.
- Content pulled from the wrong data.
- A literal null string replacing a missing value.
- Wrong newlines or spacing making the email hard to read.
- Vietnamese characters replaced due to byte conversion at an earlier layer.

### 9.1. Verify the complete text

~~~java
assertEquals(
        "Xin chào Nguyễn An,\n\n"
      + "Đơn hàng ORDER-2026-001 đã được xác nhận.\n"
      + "Tổng tiền: 500000 VND.\n\n"
      + "Trân trọng,\n"
      + "Đội ngũ bán hàng",
        message.getText()
);
~~~

This test protects both Vietnamese diacritics and newline positions.

### 9.2. Unicode is intentional test data

Do not test only:

~~~text
Hello John
~~~

Real emails may contain:

~~~text
Xin chào Nguyễn Ánh,
Đơn hàng đã được xác nhận.
~~~

Characters like **ă, â, đ, ê, ô, ơ, ư** and tone marks help detect issues when data is mangled before calling setText.

However, testing a String in SimpleMailMessage **is not testing MIME charset or SMTP encoding on the wire**. That is the responsibility of integration testing with the transport, such as JavaMailSender/MimeMessage in a separate step.

### 9.3. Text content is not HTML

If the body contains:

~~~text
<strong>Đơn hàng đã xác nhận</strong>
~~~

SimpleMailMessage sends that snippet as plain text without asking email clients to render it in bold.

If the test expects HTML to be rendered, MimeMessageHelper with text/html must be used instead of SimpleMailMessage.

### 9.4. Newlines according to the contract

If the text uses \n, you can compare directly in unit tests. Do not force every test to use System.lineSeparator(), because the result may differ between Linux and Windows while the content contract must stay stable.

During MIME serialization, the mail library may handle line endings according to protocol standards. Do not use a SimpleMailMessage unit test to infer the final CRLF bytes on the SMTP wire.

## 10. Test SentDate deterministically

An anti-pattern is calling:

~~~java
message.setSentDate(new Date());
~~~

and then asserting against the current time within a very narrow window. Such tests tend to be flaky due to execution timing, scheduling, and clock differences.

### 10.1. Pass the timestamp into the DTO

The sample factory uses:

~~~java
message.setSentDate(Date.from(data.confirmedAt()));
~~~

Test:

~~~java
Instant confirmedAt =
        Instant.parse("2026-11-12T08:30:00Z");

OrderMailData data = new OrderMailData(
        "an@example.net",
        "Nguyễn An",
        "ORDER-2026-001",
        new BigDecimal("500000"),
        confirmedAt
);

SimpleMailMessage message = factory.create(data);

assertEquals(
        Date.from(confirmedAt),
        message.getSentDate()
);
~~~

The value comes from a known input, so the test does not depend on the CI timezone or current clock.

### 10.2. Use Clock when the current time must be read

If the business logic needs **the message creation time** instead of the order confirmation time, you can inject java.time.Clock:

~~~java
public final class TimestampedMailFactory {

    private final Clock clock;

    public TimestampedMailFactory(Clock clock) {
        this.clock = clock;
    }

    public SimpleMailMessage create() {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("system@example.org");
        message.setTo("user@example.net");
        message.setSubject("Notification");
        message.setText("Content");
        message.setSentDate(Date.from(clock.instant()));
        return message;
    }
}
~~~

Test:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-12T08:30:00Z"),
        ZoneOffset.UTC
);

TimestampedMailFactory factory =
        new TimestampedMailFactory(fixed);

assertEquals(
        Date.from(Instant.parse("2026-11-12T08:30:00Z")),
        factory.create().getSentDate()
);
~~~

### 10.3. Not every email needs setSentDate

SimpleMailMessage allows the application to set this field, but depending on the architecture, the sent timestamp may be handled at the transport layer. If the system does not require setSentDate, tests should verify the state defined by the contract rather than forcing unnecessary data creation.

## 11. Test validation: empty or null inputs

A factory must clearly define how missing data is handled. Do not let a message contain:

~~~text
To: null
Subject: Xác nhận đơn hàng null
Body: Xin chào null
~~~

Example test:

~~~java
@Test
void rejectsNullData() {
    assertThrows(
            NullPointerException.class,
            () -> factory.create(null)
    );
}

@Test
void rejectsBlankRecipient() {
    OrderMailData data = new OrderMailData(
            "   ",
            "Nguyễn An",
            "ORDER-2026-001",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    assertThrows(
            IllegalArgumentException.class,
            () -> factory.create(data)
    );
}
~~~

The exception types promised by the contract must be consistent. If a validation framework such as Bean Validation is used, tests can verify constraint violations at the appropriate layer instead of catching these exact illustrative exceptions.

### 11.1. Test each required field

Cases to include:

- null data.
- null, empty, or blank recipientEmail.
- null or blank customerName.
- null or blank orderNumber.
- null totalAmount.
- null confirmedAt.
- negative totalAmount if the domain disallows it.
- syntactically invalid recipientEmail.
- subject input containing CR or LF.

Crucially, **no email must be sent when the factory fails to build valid data**.

## 12. Parameterized tests for invalid data

JUnit 5 supports ParameterizedTest to avoid repeating many similar tests.

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class OrderMailValidationTest {

    private final OrderMailMessageFactory factory =
            new OrderMailMessageFactory();

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "   ", "not-an-email", "@example.net"})
    void rejectsInvalidRecipient(String recipient) {
        OrderMailData data = new OrderMailData(
                recipient,
                "Nguyễn An",
                "ORDER-2026-001",
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z")
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> factory.create(data)
        );
    }
}
~~~

This tests the rules of the illustrative factory. It does not mean every email system must reject the exact same input set if product contracts differ.

### 12.1. NullAndEmptySource differs from blank

**@NullAndEmptySource** checks null and the empty string. Strings like one or three spaces must be added to **@ValueSource** if you want to test blank values.

### 12.2. Test internationalized addresses separately

If the product supports internationalized addresses, a dedicated test matrix matching SMTPUTF8 and the provider is needed. Do not use a custom ASCII regex to claim that every valid address worldwide is supported.

### 12.3. Syntax validation does not prove a mailbox exists

For example, **InternetAddress.validate()** checks syntax according to the API. It does not perform actual mailbox verification.

Do not write a unit test checking whether an address exists on a real provider. That goes beyond the scope of a SimpleMailMessage factory and introduces network dependencies.

## 13. Test whitespace normalization

Input data often has leading or trailing whitespace from user entry or integrations.

The example factory explicitly calls **trim()**:

~~~java
OrderMailData data = new OrderMailData(
        "  an@example.net  ",
        "  Nguyễn An  ",
        "  ORDER-2026-001  ",
        new BigDecimal("500000"),
        Instant.parse("2026-11-12T08:30:00Z")
);

SimpleMailMessage message = factory.create(data);

assertArrayEquals(
        new String[] {"an@example.net"},
        message.getTo()
);

assertEquals(
        "Xác nhận đơn hàng ORDER-2026-001",
        message.getSubject()
);

assertTrue(
        message.getText().startsWith("Xin chào Nguyễn An,")
);
~~~

However, not every field should be trimmed. Passwords, verification codes, or digitally signed data may need to be preserved verbatim. In a transactional mail factory, only normalize fields with a clear contract.

### 13.1. Avoid silently mutating source data

The factory should build the message from the DTO without mutating the DTO or source entity. Java records limit mutation on the record object itself, though fields referencing mutable objects still need careful management.

## 14. Prevent newline injection in headers

When concatenating untrusted data into Subject or addresses, CR/LF characters can corrupt header formatting or create header injection risks if downstream layers handle them unsafely.

Example dangerous input:

~~~text
ORDER-123
Bcc: attacker@example.net
~~~

The sample factory requires the order number to be single-line:

~~~java
if (value.indexOf('\r') >= 0 ||
        value.indexOf('\n') >= 0) {
    throw new IllegalArgumentException(
            "Header field must be single-line"
    );
}
~~~

Test:

~~~java
@Test
void rejectsNewlineInOrderNumber() {
    OrderMailData data = new OrderMailData(
            "an@example.net",
            "Nguyễn An",
            "ORDER-123\r\nBcc: someone@example.net",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    assertThrows(
            IllegalArgumentException.class,
            () -> factory.create(data)
    );
}
~~~

### 14.1. Why reject instead of arbitrarily stripping?

If you silently remove newlines without control, the order number value could turn into a different code or break audit reconciliation. For identifiers, **rejecting out-of-contract input** is usually clearer.

### 14.2. Do not manually build raw SMTP headers

SimpleMailMessage lets the application use setter APIs instead of concatenating raw MIME headers manually. Even so, business data still requires validation and should not rely solely on the library to strip every invalid value.

## 15. Test monetary amounts and locale

Amounts must come from the exact source data and must not change unexpectedly when converted to a String.

The sample factory uses:

~~~java
data.totalAmount().toPlainString()
~~~

for a simple format like **500000 VND**.

### 15.1. Why use BigDecimal?

BigDecimal fits many monetary calculations because it avoids certain floating-point rounding issues. In tests, construct data as:

~~~java
new BigDecimal("500000")
~~~

instead of using double when exact decimal precision must be preserved.

### 15.2. When formatting by locale

Illustrative code example:

~~~java
NumberFormat format =
        NumberFormat.getCurrencyInstance(
                Locale.forLanguageTag("vi-VN")
        );

String formatted = format.format(amount);
~~~

Results can depend on locale/CLDR data and the JDK version. If the contract mandates a specific format, control the formatter, locale, currency, and rounding policy, or test a standardized formatter abstraction.

### 15.3. Do not hard-code incorrect amount strings

Tests should include different amount values to detect if a builder always uses a fixed value. For example, 500000 and 120000 must not produce the same total amount in the body.

## 16. Test that other customers' data is not leaked

A severe bug is using the wrong DTO or caching messages between requests, causing person A's name/recipient to be paired with person B's order number.

Test with two independent DTOs:

~~~java
@Test
void createsIndependentMessagesForDifferentOrders() {
    OrderMailData first = new OrderMailData(
            "an@example.net",
            "Nguyễn An",
            "ORDER-101",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    OrderMailData second = new OrderMailData(
            "binh@example.net",
            "Trần Bình",
            "ORDER-202",
            new BigDecimal("120000"),
            Instant.parse("2026-11-13T09:30:00Z")
    );

    SimpleMailMessage firstMessage = factory.create(first);
    SimpleMailMessage secondMessage = factory.create(second);

    assertNotSame(firstMessage, secondMessage);

    assertArrayEquals(
            new String[] {"an@example.net"},
            firstMessage.getTo()
    );

    assertArrayEquals(
            new String[] {"binh@example.net"},
            secondMessage.getTo()
    );

    assertTrue(
            firstMessage.getText().contains("ORDER-101")
    );

    assertTrue(
            secondMessage.getText().contains("ORDER-202")
    );

    assertFalse(
            secondMessage.getText().contains("Nguyễn An")
    );
}
~~~

### 16.1. Do not reuse a mutable SimpleMailMessage singleton

Do not keep a single SimpleMailMessage that is mutated back and forth across concurrent requests. If multiple threads share this mutable object, recipient or body data can get mixed up.

A factory that creates **a new message per call** is a safer and more testable design.

### 16.2. Verify no state is retained between sends

This is not only about thread safety; a message reused sequentially can also retain old CC/BCC/Reply-To values if the code forgets to clear them.

## 17. The sending service only receives a built message

The service layer can be very thin:

~~~java
import org.springframework.mail.MailSender;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final MailSender mailSender;
    private final OrderMailMessageFactory factory;

    public OrderMailService(
            MailSender mailSender,
            OrderMailMessageFactory factory
    ) {
        this.mailSender = mailSender;
        this.factory = factory;
    }

    public void sendConfirmation(OrderMailData data) {
        SimpleMailMessage message = factory.create(data);
        mailSender.send(message);
    }
}
~~~

Here **MailSender** is a sufficient abstraction for SimpleMailMessage. There is no need to use JavaMailSender if the service only sends plain-text messages, even though JavaMailSender also extends MailSender and can be injected in a real environment.

### 17.1. Dependency injection makes testing easier

Tests can supply:

- A real factory to verify content.
- A mock MailSender to avoid network connections.

No SMTP host, port, username, or password configuration is needed in unit tests.

## 18. Use Mockito ArgumentCaptor to verify the sent message

This testing approach is especially useful when the SimpleMailMessage object is created **inside the service** and passed directly to MailSender.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

class OrderMailServiceTest {

    @Test
    void sendsMessageBuiltFromBusinessData() {
        MailSender sender = mock(MailSender.class);
        OrderMailMessageFactory factory =
                new OrderMailMessageFactory();

        OrderMailService service =
                new OrderMailService(sender, factory);

        OrderMailData data = new OrderMailData(
                "an@example.net",
                "Nguyễn An",
                "ORDER-2026-001",
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z")
        );

        service.sendConfirmation(data);

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender, times(1)).send(captor.capture());
        verifyNoMoreInteractions(sender);

        SimpleMailMessage sentMessage = captor.getValue();

        assertEquals(
                "orders@example.org",
                sentMessage.getFrom()
        );

        assertArrayEquals(
                new String[] {"an@example.net"},
                sentMessage.getTo()
        );

        assertEquals(
                "support@example.org",
                sentMessage.getReplyTo()
        );

        assertEquals(
                "Xác nhận đơn hàng ORDER-2026-001",
                sentMessage.getSubject()
        );

        assertTrue(
                sentMessage.getText().contains("Nguyễn An")
        );

        assertTrue(
                sentMessage.getText().contains("500000 VND")
        );

        assertNull(sentMessage.getCc());
        assertNull(sentMessage.getBcc());
    }
}
~~~

Mockito captures the object passed to **MailSender.send(...)**. Because sender is a mock, **no email is sent externally**.

### 18.1. What does ArgumentCaptor verify?

It verifies **the interaction at the boundary**:

~~~text
OrderMailService.sendConfirmation(data)
                  |
                  v
         MailSender.send(message)
                  |
                  v
         Mockito captures message
                  |
                  v
           Assertions on fields
~~~

If the service fails to call send, or calls it twice unexpectedly, verify will catch it.

### 18.2. Captor does not replace factory tests

Captor is useful for confirming that the service passes the right object to MailSender. Dedicated factory tests are valuable because mapping bugs are isolated, easy to read, and require no Mockito.

A good test suite can combine **factory unit tests** with **a few service tests using a captor**, without repeating every assertion in both places.

## 19. Test the number of send invocations

A bug can cause the service to send duplicates during retries or loop the wrong number of times.

~~~java
verify(sender, times(1))
        .send(any(SimpleMailMessage.class));
~~~

If the logic requires not sending when data is invalid:

~~~java
verifyNoInteractions(sender);
~~~

If the workflow intentionally sends N notifications to N people, the test must assert the exact invocation count according to the contract. Do not merely test that at least one email was sent.

### 19.1. Test fail-fast before calling MailSender

~~~java
@Test
void invalidDataDoesNotInvokeSender() {
    MailSender sender = mock(MailSender.class);

    OrderMailService service = new OrderMailService(
            sender,
            new OrderMailMessageFactory()
    );

    OrderMailData invalid = new OrderMailData(
            "not-an-email",
            "Nguyễn An",
            "ORDER-2026-001",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    assertThrows(
            IllegalArgumentException.class,
            () -> service.sendConfirmation(invalid)
    );

    verifyNoInteractions(sender);
}
~~~

This verifies a very important constraint: **data is rejected before producing the email-sending side effect**.

### 19.2. Do not confuse validation errors with transport errors

If the factory rejects an invalid address, the test should assert the validation exception. There is no need to mock an SMTP 550 response just to test the validation logic itself.

## 20. Mock the factory when testing only service orchestration

Some tests only need to verify that the service calls the factory and passes the resulting object to the sender, without caring about content structure.

~~~java
@Test
void servicePassesFactoryResultToSender() {
    MailSender sender = mock(MailSender.class);
    OrderMailMessageFactory factory =
            mock(OrderMailMessageFactory.class);

    SimpleMailMessage prepared = new SimpleMailMessage();
    prepared.setTo("an@example.net");
    prepared.setText("Test content");

    OrderMailData data = new OrderMailData(
            "an@example.net",
            "Nguyễn An",
            "ORDER-2026-001",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    when(factory.create(data)).thenReturn(prepared);

    OrderMailService service =
            new OrderMailService(sender, factory);

    service.sendConfirmation(data);

    verify(factory).create(data);
    verify(sender).send(prepared);
}
~~~

**Example design note:** for Mockito to mock a class, the project needs Mockito configured appropriately for the version in use; if you prefer not to mock concrete classes, use a factory interface or pass a real factory. If a class is declared **final** as in the factory example above, mocking final classes depends on the Mockito mock maker/version.

### 20.1. When should you not mock the factory?

If the test's goal is to verify To/Subject/Text, mocking the factory bypasses the logic under test. In that case, use a real factory or test the factory directly.

### 20.2. When should you mock the factory?

If you want to test the service's own workflow, such as "the factory builds the message and then the service sends it exactly once," mocking the factory can help narrow the test scope.

## 21. Test exception handling from MailSender

A unit test can mock the sender throwing **MailException** to verify how the service reacts. Example:

~~~java
import org.springframework.mail.MailSendException;

@Test
void propagatesMailSendFailure() {
    MailSender sender = mock(MailSender.class);

    OrderMailService service = new OrderMailService(
            sender,
            new OrderMailMessageFactory()
    );

    OrderMailData data = new OrderMailData(
            "an@example.net",
            "Nguyễn An",
            "ORDER-2026-001",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    doThrow(new MailSendException("Simulated SMTP failure"))
            .when(sender)
            .send(any(SimpleMailMessage.class));

    assertThrows(
            MailSendException.class,
            () -> service.sendConfirmation(data)
    );

    verify(sender, times(1))
            .send(any(SimpleMailMessage.class));
}
~~~

This test only proves that the service does not swallow the error in the current example. It does not test SMTP connectivity or real server responses.

### 21.1. If the service has retries

If the application adds retries, tests must verify:

- Which errors are retried.
- Number of attempts.
- Timing/backoff using a fake clock/scheduler.
- No retries on permanent data errors.
- No unintended re-execution of business logic.
- Handling ambiguous outcomes that carry a risk of duplicate sending.

Do not turn on retries for all MailException types merely to make a "send eventually succeeds" test pass.

## 22. Test sensitive content and privacy

Do not only test data that must be present. Also test data that **must not appear**.

For example, a DTO might travel alongside other request information, yet SimpleMailMessage should only contain fields required for the email.

Assertions can include:

~~~java
assertFalse(message.getText().contains("internal-secret"));
assertFalse(message.getSubject().contains("password"));
assertNull(message.getBcc());
~~~

These strings are illustrative only; it is better to test with a fixture containing a dummy secret intentionally placed in the input and verify the factory does not use it.

### 22.1. Never let customer A's data appear in customer B's mail

Testing two independent snapshots is a simple way to guard against shared mutable objects or wrong field mappings.

### 22.2. Do not send secrets in the Subject

The Subject can appear in notification previews and many mail-processing systems. Avoid putting OTPs, access tokens, or confidential information in it unless there is a special requirement whose risk has been evaluated.

### 22.3. Verify BCC complies with policy

BCC is actual recipient data sent at the envelope level, even though the address may not appear in headers visible to recipients. An unintended BCC is still a privacy incident; unit tests should verify the application's rule.

## 23. Test data with a case matrix table

A test table helps show the scope of data to cover:

| Case | Input | Expected result |
| --- | --- | --- |
| Basic valid | One recipient and complete DTO | Message has correct From/To/Subject/Text |
| Unicode | Name Nguyễn Ánh | Text preserves Vietnamese diacritics |
| Recipient with leading/trailing whitespace | Trimmable data | To is normalized |
| Empty recipient | Blank string | Exception, no send |
| Invalid recipient syntax | Missing @ | Exception, no send |
| Subject input contains CR/LF | Order number with newline | Exception, no send |
| Different order number | ORDER-999 | Subject/text change with data |
| Different total amount | 120000 instead of 500000 | Body has the new value |
| Negative total amount | -100 per example rule | Exception |
| Different date | Different Instant | SentDate matches |
| Multiple message creations | Two different DTOs | Two independent messages |
| No CC/BCC per contract | Valid DTO | CC/BCC are not set |
| MailSender failure | Mock throws MailSendException | Service handles per contract |
| No duplicate sends | Call service once | verify sender send exactly once |

The table is a test data plan, not a default definition from Spring. Rules such as "non-negative amount" must follow the specific business contract.

## 24. Fixtures and test data builders

When testing many cases, repeating the DTO constructor can make tests verbose. A fixture helper can be used:

~~~java
public final class MailTestData {

    private MailTestData() {
    }

    public static OrderMailData validOrder() {
        return new OrderMailData(
                "an@example.net",
                "Nguyễn An",
                "ORDER-2026-001",
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z")
        );
    }

    public static OrderMailData withRecipient(String recipient) {
        OrderMailData base = validOrder();

        return new OrderMailData(
                recipient,
                base.customerName(),
                base.orderNumber(),
                base.totalAmount(),
                base.confirmedAt()
        );
    }
}
~~~

Tests become clearer:

~~~java
@Test
void rejectsBlankEmail() {
    assertThrows(
            IllegalArgumentException.class,
            () -> factory.create(
                    MailTestData.withRecipient(" ")
            )
    );
}
~~~

### 24.1. Do not make fixtures overly smart

A test builder that automatically normalizes data or fixes invalid recipients can hide factory bugs. Fixtures should create the exact input the test asks for without replacing production logic.

### 24.2. Keep data fake yet meaningful

Using example domains such as example.org or example.net avoids accidental sending and clearly shows this is test data. Do not use real user emails or passwords in unit tests.

## 25. Separate unit tests from integration tests

The two test levels answer two different questions.

### 25.1. Unit tests

Goals:

- Business data is mapped properly into SimpleMailMessage.
- Validation works.
- MailSender receives the right message.
- send is called the right number of times.
- No network side effects.

Tools:

- JUnit 5.
- Mockito.
- Real or fake DTO and factory.
- Fixed Clock if needed.

### 25.2. Integration tests

Different goals:

- Does the mail transport create/serialize the message and send it to a test SMTP server successfully?
- Do host/port/AUTH/STARTTLS settings work?
- Do addresses and content pass through the provider properly?
- Are wire encoding and MIME behavior appropriate?

Tools:

- Controlled SMTP capture server or test server.
- Spring integration tests when needed.
- No real recipient mailboxes unless required.

### 25.3. Why not use a real SMTP server for unit tests?

Tests will:

- Be slow and hard to run in parallel.
- Depend on DNS, network, and credentials.
- Risk sending unintended emails.
- Be affected by rate limits/provider outages.
- Be hard to reproduce failures.
- Create a risk of leaking test data to external environments.

Factory unit tests and Mockito captors already verify most of the data contract without needing SMTP.

## 26. Some common anti-patterns

### 26.1. Only verifying send(any())

~~~java
verify(sender).send(any(SimpleMailMessage.class));
~~~

This proves send was called, but tells nothing about **whether the recipient, subject, and body are right**. Add a captor/assertions or factory unit tests.

### 26.2. Comparing arrays with assertEquals

~~~java
assertEquals(
        new String[] {"an@example.net"},
        message.getTo()
);
~~~

This is inappropriate for comparing String[] contents; use **assertArrayEquals**.

### 26.3. Tests depending on System.currentTimeMillis()

If asserting that the sent date is close to the current time with a very tight threshold, tests can be flaky. Use a fixed Clock or fixed Instant.

### 26.4. Using production data

Tests do not need real email addresses, real phone numbers, real OTPs, or real tokens. Use synthetic data with verification value.

### 26.5. Mocking the very object under test

If the goal is to check what Subject/Text a SimpleMailMessage has, yet you mock the entire message, the test only proves mock behavior. Create a real SimpleMailMessage and assert its getters.

### 26.6. Testing SMTP inside unit tests

Do not make unit tests wait for an SMTP provider. Isolate MailSender behind an interface and mock/fake at the boundary.

### 26.7. Asserting too little content

Checking that text is not null will not detect a wrong amount or wrong customer name. Assert the important business values.

### 26.8. Asserting every unnecessary editorial detail

Conversely, if the contract only requires the order number and status, locking down all whitespace and phrasing can make tests break constantly on copywriting edits. Choose the assertion level based on actual requirements.

### 26.9. Swallowing errors by catching Exception and ignoring it

If data is invalid, code must not silently send an empty email or substitute a dangerous default recipient. Tests should verify fail-fast behavior or a clearly specified fallback.

## 27. Example of a concise complete unit test suite

The following suite illustrates the core requirements:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

class OrderMailContractTest {

    private final OrderMailMessageFactory factory =
            new OrderMailMessageFactory();

    private OrderMailData data(
            String recipient,
            String customer,
            String orderNumber
    ) {
        return new OrderMailData(
                recipient,
                customer,
                orderNumber,
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z")
        );
    }

    @Test
    void mapsAllRequiredFields() {
        SimpleMailMessage message = factory.create(
                data(
                        "an@example.net",
                        "Nguyễn An",
                        "ORDER-001"
                )
        );

        assertAll(
                () -> assertEquals(
                        "orders@example.org",
                        message.getFrom()
                ),
                () -> assertEquals(
                        "support@example.org",
                        message.getReplyTo()
                ),
                () -> assertArrayEquals(
                        new String[] {"an@example.net"},
                        message.getTo()
                ),
                () -> assertEquals(
                        "Xác nhận đơn hàng ORDER-001",
                        message.getSubject()
                ),
                () -> assertTrue(
                        message.getText().contains("Nguyễn An")
                ),
                () -> assertTrue(
                        message.getText().contains("500000 VND")
                ),
                () -> assertEquals(
                        Date.from(Instant.parse(
                                "2026-11-12T08:30:00Z"
                        )),
                        message.getSentDate()
                ),
                () -> assertNull(message.getCc()),
                () -> assertNull(message.getBcc())
        );
    }

    @Test
    void doesNotSendInvalidRecipient() {
        MailSender sender = mock(MailSender.class);
        OrderMailService service =
                new OrderMailService(sender, factory);

        assertThrows(
                IllegalArgumentException.class,
                () -> service.sendConfirmation(
                        data(
                                "invalid-address",
                                "Nguyễn An",
                                "ORDER-001"
                        )
                )
        );

        verifyNoInteractions(sender);
    }

    @Test
    void sendsCorrectPreparedMessageOnce() {
        MailSender sender = mock(MailSender.class);
        OrderMailService service =
                new OrderMailService(sender, factory);

        service.sendConfirmation(
                data("an@example.net", "Nguyễn An", "ORDER-001")
        );

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender, times(1)).send(captor.capture());

        SimpleMailMessage captured = captor.getValue();

        assertArrayEquals(
                new String[] {"an@example.net"},
                captured.getTo()
        );
        assertEquals(
                "Xác nhận đơn hàng ORDER-001",
                captured.getSubject()
        );
        assertTrue(
                captured.getText().contains("ORDER-001")
        );

        verifyNoMoreInteractions(sender);
    }
}
~~~

The test suite uses real objects to verify data and mocks only at the mail-sending boundary. No Spring context or real SMTP server is needed.

## 28. How to organize test code in a project

An illustrative layout:

~~~text
src/
├── main/java/
│   └── example/mail/
│       ├── OrderMailData.java
│       ├── OrderMailMessageFactory.java
│       └── OrderMailService.java
└── test/java/
    └── example/mail/
        ├── OrderMailMessageFactoryTest.java
        ├── OrderMailServiceTest.java
        └── MailTestData.java
~~~

Common dependencies in a Spring Boot application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is an example Gradle declaration for a project using Spring Boot; versions are managed according to the current build configuration. Only use JUnit/Mockito APIs compatible with the installed dependency versions.

### 28.1. @SpringBootTest is not needed for every test

The factory does not depend on the Spring context. Instantiating it directly:

~~~java
new OrderMailMessageFactory()
~~~

and calling create is enough. Starting the entire Spring context for every mapping test slows down tests and can pull in unnecessary configuration.

### 28.2. When is @SpringBootTest needed?

When you want to test wiring, auto-configuration, or integration with an SMTP capture server, SpringBootTest can be appropriate. However, that is a different level from SimpleMailMessage data unit testing.

## 29. Verify future contract changes

As the application evolves, the factory may gain:

- CC for the accounting department.
- Brand-specific Reply-To.
- User-specific locale.
- Multiple Subject templates.
- Reminder or warning content.
- Per-tenant email footers.

Each change can affect the sent data. When adding a field:

1. Document the data rule.
2. Add sample input.
3. Assert the new field and fields that must remain unchanged.
4. Add missing or invalid data cases.
5. If recipient count changes, verify privacy.
6. Keep the sender mocked so real emails are not sent.
7. Verify inputs from two tenants are not mixed.

There is no need to turn unit tests into a full duplicate of business logic; the goal is to protect risky data boundaries.

## 30. Frequently asked questions

**1. Do I need an SMTP server to test SimpleMailMessage?**

No. SimpleMailMessage is a Java object. You can create it via a factory and assert its getters. To verify that a service calls send, mock MailSender.

**2. Should I use JavaMailSender or MailSender in unit tests?**

If the service only sends SimpleMailMessage, the MailSender interface is enough. JavaMailSender is useful when handling MimeMessage/HTML/attachments.

**3. How do I verify To was set properly?**

Use **message.getTo()** and **assertArrayEquals(...)** because the return type is String[].

**4. How do I check that the service passed the right message to send?**

Use Mockito **ArgumentCaptor<SimpleMailMessage>**, verify sender.send(captor.capture()), and then assert the captured message's fields.

**5. Why do tests assertNull on CC and BCC?**

To catch unintended carbon-copy recipients. For transactional emails containing private data, this is an important constraint.

**6. Should I test Subjects containing Vietnamese text?**

Yes, if the product sends Vietnamese. Unit tests verify the exact String; MIME encoding on the wire should be tested in a separate integration test.

**7. Should I call System.currentTimeMillis() in tests?**

Not if deterministic results are needed. Use a fixed Instant or Clock.fixed.

**8. Can SimpleMailMessage send HTML?**

It uses plain text. If HTML is needed, use MimeMessage with MimeMessageHelper and test MIME according to the corresponding API.

**9. Does InternetAddress.validate() know whether a mailbox exists?**

No. It checks syntax, not ownership or actual deliverability.

**10. Is testing one valid message enough?**

You should add another input, invalid inputs, Unicode, optional fields, and check two independent messages to catch hard-coding or shared state.

**11. Should I use assertEquals for the entire text?**

Yes, if the content is fixed by contract. If copywriting changes often, you can assert required facts and leave phrasing review to another process.

**12. Why use a DTO instead of a JPA entity?**

A DTO keeps tests independent of the database/persistence context and avoids lazy loading errors when building mail outside a transaction.

**13. If MailSender throws MailSendException, what should be tested?**

Verify the service handles it per contract: propagate, persist the error, or retry. Unit tests do not prove a real SMTP provider responds the same way.

**14. Should I check the number of send calls?**

Yes, especially when preventing duplicate sends. Mockito verify times(1) verifies that one service call does not trigger two unexpected send calls.

**15. Should I send real emails in CI to ensure data is right?**

Not for unit tests. Use a test SMTP server/capture for integration tests when you want to verify transport.

**16. Which content should be checked as excluded from an email?**

You can check unintended CC/BCC, secrets/tokens, other customers' data, and sensitive values outside the email contract.

## 31. Key takeaways on unit testing SimpleMailMessage data

**Unit testing SimpleMailMessage data means testing the contract that transforms business data into a plain-text email.** Instead of waiting for SMTP to send mail, pass a deterministic DTO into a factory, receive a SimpleMailMessage, and explicitly assert **From, To, Reply-To, CC, BCC, Subject, Text, and SentDate** as required.

**Separating the factory from MailSender** enables network-free testing. In service tests, use **Mockito ArgumentCaptor** to capture the message passed into send and inspect its fields; use **verify(times(1))** to check the call count and **verifyNoInteractions** when data is rejected. For To/CC/BCC address arrays, use **assertArrayEquals**, never compare arrays with assertEquals.

Test data should cover **Vietnamese text, missing or blank fields, syntactically invalid addresses, whitespace, CR/LF in headers, amounts/locale, fixed timestamps, and multiple independent DTOs**. These tests protect sending to the right person, with the right content, and without unintended data leaks. Even when all unit tests pass, keep them distinct from SMTP/MIME integration tests: **a properly built message does not mean the provider accepted it, delivered it, or that the recipient read the email**.
