# Testing Subject, From, To, Cc, and Bcc

## 1. Goals of testing email addresses and subject

In an application using **Spring Framework Mail**, an email must not only be sent successfully over SMTP, it must also carry the right **Subject** and **From, To, Cc, Bcc** addresses according to business rules. Even a minor error when mapping data into headers can cause notifications to miss the intended recipient, be sent to the wrong group, or leak recipients.

For example:

- An order confirmation email must be sent **To** the customer who owns the order.
- **From** must be an address authorized for sending by the system, never taken arbitrarily from a request.
- **Cc** must contain only people allowed to know about the shared message.
- **Bcc** is used when additional recipients must receive the email without exposing that list to other recipients.
- **Subject** must state the right event, order code, and selected language.

Therefore, when unit testing the email-sending layer, you should verify **the exact data placed on the mail object before sending**, rather than merely checking that the send method was called once.

In Spring Framework Mail there are two common approaches:

1. **SimpleMailMessage** — suited for simple plain-text emails.
2. **MimeMessage** created via **JavaMailSender** and assisted by **MimeMessageHelper** — suited for emails with HTML, display names, multiple MIME parts, or attachments.

With both approaches, you can use **JUnit 5** and **Mockito** to intercept the send call and inspect the configured properties, **without needing a real SMTP connection**.

## 2. Understanding Subject, From, To, Cc, and Bcc

| Field | Role | What to verify in unit tests |
|---|---|---|
| **Subject** | Title seen by the recipient | Correct message, language, and business variables; not null/blank against policy |
| **From** | Displayed author/sender address | Correct authorized sending address |
| **To** | Primary recipients | Correct business recipient, count, and addresses |
| **Cc** | Public carbon-copy recipients | Exact list allowed to see one another |
| **Bcc** | Blind carbon-copy recipients | Present in the outbound recipient list, not mistakenly put in To/Cc |

Diagram:

~~~text
Business event / Notification request
               |
               v
      Notification service
               |
               +-- Subject = "Order ORD-101 delivered"
               +-- From    = "orders@example.com"
               +-- To      = ["buyer@example.net"]
               +-- Cc      = ["agent@example.com"]
               +-- Bcc     = ["audit@example.com"]
               |
               v
      SimpleMailMessage / MimeMessage
               |
               v
         JavaMailSender.send(...)
~~~

### A related distinction: From is not the SMTP envelope sender

**From** in an email is the display header, whereas **SMTP MAIL FROM** is the envelope sender used in the SMTP protocol to define the reverse-path/bounce address. Testing **MimeMessage.getFrom()** verifies the From header; it does **not** prove the transport will use that value for the MAIL FROM command. If business rules require a separate bounce address, test SMTP transport configuration or provider integration in a separate test layer.

### Bcc does not mean content encryption

Bcc only aims to prevent other recipients from seeing the Bcc address list. It does not encrypt email content, does not guarantee mailbox access control, and does not replace authorization checks. Bcc tests must also distinguish **the pre-send MimeMessage object** from **the actual MIME data during an SMTP session**.

## 3. Scope of a unit test

An ideal unit test checks the layer responsible for **creating email data**:

~~~text
JUnit 5 test
      |
      v
Real NotificationService
      |
      v
JavaMailSender mocked with Mockito
      |
      v
Captor captures SimpleMailMessage/MimeMessage
      |
      v
Assertions: Subject, From, To, Cc, Bcc
~~~

Unit tests can prove:

- The service picks the right recipients based on the passed data.
- The service sets headers and subject on the right message.
- The service does not place Bcc addresses into To/Cc.
- The service invokes JavaMailSender with the prepared object.
- Optional data such as Cc and Bcc are handled properly when empty.

Unit tests **do not prove**:

- Whether the SMTP server actually accepts the email.
- Whether the provider rewrites From or reverse-path.
- Whether the email lands in Inbox or is filtered as Spam.
- Whether the transport strips the Bcc list from header data delivered to recipients.
- That all clients render the Subject identically.

Those require **integration tests with an SMTP test server/ESP sandbox** or system tests in a permitted environment.

## 4. Dependencies for the examples

Spring Boot example with Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The mail starter provides Spring Mail/Jakarta Mail integration for implementation, while the test starter typically provides JUnit Jupiter, Mockito, and assertions used in the examples. If the project uses plain Spring Framework or manages dependencies separately, add the matching libraries for the version in use.

For Spring Boot 3 / Spring Framework 6 and above, examples use the **jakarta.mail** package instead of the older **javax.mail**.

### Testing components

- **JUnit 5**: runs tests and verifies results with assertEquals, assertArrayEquals, assertThrows...
- **Mockito**: mocks JavaMailSender, intercepts send calls, and provides ArgumentCaptor.
- **Jakarta Mail**: allows creating real in-memory MimeMessage instances to inspect headers.
- **No @SpringBootTest needed** for pure unit tests of a service using constructor injection.

## 5. Application example: sending plain-text email with SimpleMailMessage

First consider an email without HTML or attachments. In that case **SimpleMailMessage** is straightforward to build and test.

Input definition:

~~~java
import java.util.List;

public record PlainMailRequest(
        String subject,
        String from,
        List<String> to,
        List<String> cc,
        List<String> bcc,
        String body
) {
}
~~~

Message-building service:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class PlainMailService {

    private final JavaMailSender mailSender;

    public PlainMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(PlainMailRequest request) {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setSubject(request.subject());
        message.setFrom(request.from());
        message.setTo(request.to().toArray(String[]::new));

        if (!request.cc().isEmpty()) {
            message.setCc(request.cc().toArray(String[]::new));
        }
        if (!request.bcc().isEmpty()) {
            message.setBcc(request.bcc().toArray(String[]::new));
        }

        message.setText(request.body());

        mailSender.send(message);
    }
}
~~~

This service assumes the request has been validated and the lists are non-null. A real application must validate recipients, ensure the sender belongs to an allowed list, and handle data errors. The goal of this example is **testing field assignment**, not building a full email system.

SimpleMailMessage methods:

| Setter | Getter for testing |
|---|---|
| setSubject(String) | getSubject() |
| setFrom(String) | getFrom() |
| setTo(String...) | getTo() |
| setCc(String...) | getCc() |
| setBcc(String...) | getBcc() |
| setText(String) | getText() |

Recipient list getters can return **null** if the field has never been set. Keep this in mind when testing optional cases.

## 6. Test SimpleMailMessage with Mockito ArgumentCaptor

Unit test example with JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class PlainMailServiceTest {

    @Test
    void sendsCorrectSubjectAndAddresses() {
        JavaMailSender sender = mock(JavaMailSender.class);
        PlainMailService service = new PlainMailService(sender);

        PlainMailRequest request = new PlainMailRequest(
                "Order ORD-101 delivered",
                "orders@example.com",
                List.of("buyer@example.net"),
                List.of("agent@example.com"),
                List.of("audit@example.com"),
                "Order ORD-101 has been delivered."
        );

        service.send(request);

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender).send(captor.capture());

        SimpleMailMessage actual = captor.getValue();

        assertEquals(
                "Order ORD-101 delivered",
                actual.getSubject()
        );
        assertEquals(
                "orders@example.com",
                actual.getFrom()
        );
        assertArrayEquals(
                new String[] { "buyer@example.net" },
                actual.getTo()
        );
        assertArrayEquals(
                new String[] { "agent@example.com" },
                actual.getCc()
        );
        assertArrayEquals(
                new String[] { "audit@example.com" },
                actual.getBcc()
        );
        assertEquals(
                "Order ORD-101 has been delivered.",
                actual.getText()
        );
    }
}
~~~

### What does this test verify?

1. **The real service** executes.
2. **JavaMailSender** is mocked, so nothing is sent over the network.
3. **ArgumentCaptor** captures the exact SimpleMailMessage passed to the sender.
4. Assertions compare Subject, From, To, Cc, Bcc, and body.

Notably, **JavaMailSender.send** has multiple overloads. Using **ArgumentCaptor<SimpleMailMessage>** helps Mockito select the **send(SimpleMailMessage)** overload instead of confusing it with overloads for MimeMessage or message arrays.

## 7. Test optional Cc/Bcc in SimpleMailMessage

Not every email has Cc and Bcc. For example, a single-recipient notification only needs To:

~~~java
@Test
void leavesCcAndBccUnsetWhenListsAreEmpty() {
    JavaMailSender sender = mock(JavaMailSender.class);
    PlainMailService service = new PlainMailService(sender);

    service.send(new PlainMailRequest(
            "Verification code",
            "security@example.com",
            List.of("owner@example.net"),
            List.of(),
            List.of(),
            "Your verification code has been generated."
    ));

    ArgumentCaptor<SimpleMailMessage> captor =
            ArgumentCaptor.forClass(SimpleMailMessage.class);
    verify(sender).send(captor.capture());

    SimpleMailMessage actual = captor.getValue();

    assertArrayEquals(
            new String[] { "owner@example.net" },
            actual.getTo()
    );
    assertNull(actual.getCc());
    assertNull(actual.getBcc());
}
~~~

This example requires JUnit 5's static import **assertNull**. The two null assertions reflect that **the current PlainMailService implementation skips calling setCc/setBcc when the lists are empty**.

If a service chooses to call **setCc(new String[0])** or **setBcc(new String[0])**, the internal representation may be an empty array instead of null. Tests should enforce **the business rule** (no extra recipients) and the service contract rather than arbitrarily depending on one internal representation when it does not matter.

### Testing multiple To and Cc recipients

~~~java
assertArrayEquals(
        new String[] {
            "buyer@example.net",
            "co-owner@example.net"
        },
        actual.getTo()
);

assertArrayEquals(
        new String[] {
            "support@example.com",
            "manager@example.com"
        },
        actual.getCc()
);
~~~

If the application defines recipient order as meaningful, you can assert the ordered array as above. If the rule only requires **the set of recipients**, compare as a set so tests do not depend on ordering the business logic never promised.

## 8. When should you use MimeMessage instead of SimpleMailMessage?

**SimpleMailMessage** represents a plain-text email with common properties. When an application needs MIME formatting, sender display names with diacritics, HTML, inline images, or attachments, **MimeMessage** and **MimeMessageHelper** are usually required.

| Need | SimpleMailMessage | MimeMessage + MimeMessageHelper |
|---|---|---|
| Subject, From, To, Cc, Bcc | Yes | Yes |
| Plain text | Yes | Yes |
| HTML | Not designed for HTML MIME | Yes |
| Plain text + HTML alternative | No | Yes |
| Attachment | No | Yes |
| Inline resources | No | Yes |
| Unicode display name | No dedicated API like MimeMessageHelper | Yes |
| Complex MIME headers | Limited | Yes |

With MimeMessage, assertions should read **the actual MimeMessage object**, rather than looking for getters on MimeMessageHelper. The helper only assists with configuration; the fields are stored in the message.

## 9. Create a service using MimeMessageHelper

Illustrative input:

~~~java
import java.util.List;

public record MimeMailRequest(
        String subject,
        String from,
        List<String> to,
        List<String> cc,
        List<String> bcc,
        String body
) {
}
~~~

Service:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MimeMailService {

    private final JavaMailSender mailSender;

    public MimeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(MimeMailRequest request)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                StandardCharsets.UTF_8.name()
        );

        helper.setSubject(request.subject());
        helper.setFrom(request.from());
        helper.setTo(request.to().toArray(String[]::new));

        if (!request.cc().isEmpty()) {
            helper.setCc(request.cc().toArray(String[]::new));
        }
        if (!request.bcc().isEmpty()) {
            helper.setBcc(request.bcc().toArray(String[]::new));
        }

        helper.setText(request.body(), false);
        mailSender.send(message);
    }
}
~~~

Here:

- **createMimeMessage()** creates the MimeMessage object.
- **MimeMessageHelper** sets Subject and recipients in the message headers.
- The **false** parameter in the constructor indicates this example does not need multipart.
- **UTF-8** supports Vietnamese subjects and content.
- **setText(body, false)** creates plain-text content.
- **send(message)** invokes the SMTP abstraction layer.

This is an illustrative service focused solely on header assignment. Input data must be validated at the appropriate boundary before calling the service. In a real application, **MessagingException** can be translated into an application or Spring Mail exception depending on design.

## 10. Mock JavaMailSender while using a real MimeMessage

When unit testing MimeMessage, a practical pattern is to **mock JavaMailSender** while returning **a real in-memory MimeMessage**:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);

when(sender.createMimeMessage()).thenAnswer(invocation ->
        new MimeMessage(
                Session.getInstance(new Properties())
        )
);
~~~

Reasons:

- **MimeMessageHelper** needs real MIME behavior to encode and store fields.
- If **MimeMessage** itself is mocked, internal setters/getters will not behave like a real message; tests end up needing unnecessary stubs.
- **Session.getInstance(new Properties())** does not open an SMTP connection on its own.
- The call to **send(message)** still goes to the mock; no real email is sent.

Only **MimeMessage** is a real object here; **JavaMailSender** is a mock.

## 11. Complete unit test for Subject, From, To, Cc, and Bcc of MimeMessage

Standalone test example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.mail.Address;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.util.Arrays;
import java.util.List;
import java.util.Properties;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class MimeMailServiceTest {

    @Test
    void sendsExpectedSubjectAndRecipientHeaders() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);

        when(sender.createMimeMessage()).thenAnswer(invocation ->
                new MimeMessage(
                        Session.getInstance(new Properties())
                )
        );

        MimeMailService service = new MimeMailService(sender);

        service.send(new MimeMailRequest(
                "Order ORD-101 delivered",
                "orders@example.com",
                List.of("buyer@example.net"),
                List.of("agent@example.com"),
                List.of("audit@example.com"),
                "The order has been delivered successfully."
        ));

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender).send(captor.capture());

        MimeMessage actual = captor.getValue();

        assertEquals(
                "Order ORD-101 delivered",
                actual.getSubject()
        );

        assertEquals(
                List.of("orders@example.com"),
                emailAddresses(actual.getFrom())
        );

        assertEquals(
                List.of("buyer@example.net"),
                emailAddresses(
                        actual.getRecipients(Message.RecipientType.TO)
                )
        );

        assertEquals(
                List.of("agent@example.com"),
                emailAddresses(
                        actual.getRecipients(Message.RecipientType.CC)
                )
        );

        assertEquals(
                List.of("audit@example.com"),
                emailAddresses(
                        actual.getRecipients(Message.RecipientType.BCC)
                )
        );
    }

    private static List<String> emailAddresses(Address[] addresses) {
        if (addresses == null) {
            return List.of();
        }

        return Arrays.stream(addresses)
                .map(address -> ((InternetAddress) address).getAddress())
                .toList();
    }
}
~~~

**emailAddresses(...)** is a test helper that converts **InternetAddress** instances into email strings for easier comparison. For typical Internet email headers, Address values are usually InternetAddress. If the application uses another address type, the helper should handle it appropriately rather than casting unchecked.

### Important note on overloads

**JavaMailSender** has different overloads for **MimeMessage** and **SimpleMailMessage**. In the test above, the captor is typed as **MimeMessage**, so **verify(sender).send(captor.capture())** targets the **send(MimeMessage)** call.

If production code calls **send(MimeMessage[])**, use an array captor or verify each element accordingly; this example test does not assert that all overloads are equivalent.

## 12. Why read MimeMessage.getRecipients instead of raw headers?

Jakarta Mail provides:

~~~java
actual.getFrom();
actual.getSubject();
actual.getRecipients(Message.RecipientType.TO);
actual.getRecipients(Message.RecipientType.CC);
actual.getRecipients(Message.RecipientType.BCC);
~~~

These are the semantically appropriate APIs for verifying addresses:

- **getFrom()** returns an Address array, not a single String.
- **getSubject()** returns the subject decoded by Jakarta Mail's mechanism.
- **getRecipients(...)** returns Address entries for To, Cc, or Bcc.
- Missing fields can return **null**.

Avoid only comparing:

~~~java
assertEquals(
        "buyer@example.net",
        actual.getHeader("To", null)
);
~~~

Raw header strings can vary with display-name encoding, folding, or multi-address formatting; comparing raw header strings directly makes tests brittle even for valid emails. **getRecipients(...)** reflects the address semantics far better.

However, if the goal is testing wire/header serialization, a low-level test can inspect encoded headers. That is a different goal from unit testing recipient-selection logic.

## 13. Test Vietnamese and Unicode Subjects

Subjects often contain user names, order codes, or Vietnamese messages with diacritics:

~~~text
Đơn hàng ORD-101 đã được xác nhận
Lịch hẹn của bạn đã thay đổi
Mã khôi phục tài khoản
~~~

When using MimeMessageHelper with UTF-8, unit tests should compare **the decoded value**:

~~~java
assertEquals(
        "Đơn hàng ORD-101 đã được xác nhận",
        actual.getSubject()
);
~~~

Benefits:

- Verifies the renderer/service chose the right content.
- Avoids coupling to specific MIME encoded-word syntax.
- Does not require knowing how Jakarta Mail folds long headers.

Do not write tests forcing the raw Subject to equal a fixed ASCII string such as:

~~~text
=?UTF-8?B?...?=
~~~

Headers can be encoded in multiple valid forms. Only when testing **serialization/transport** should you inspect low-level MIME formatting.

### Case where Subject contains business variables

~~~java
String expectedSubject =
        "Payment succeeded for order " + orderCode;

assertEquals(expectedSubject, actual.getSubject());
~~~

Ensure variables come from the exact business object and are not mixed with another event. Do not use time-dependent or random data in subject tests unless the time/ID source is controlled.

## 14. From with a display name: test both address and personal name

In a real application, users may see:

~~~text
From: Cửa hàng Ví dụ <orders@example.com>
~~~

To create this header, you can use:

~~~java
helper.setFrom(
        "orders@example.com",
        "Cửa hàng Ví dụ"
);
~~~

Unit tests can verify both components:

~~~java
InternetAddress senderAddress =
        (InternetAddress) actual.getFrom()[0];

assertEquals(
        "orders@example.com",
        senderAddress.getAddress()
);
assertEquals(
        "Cửa hàng Ví dụ",
        senderAddress.getPersonal()
);
~~~

**getPersonal()** returns the decoded display name when supported by Jakarta Mail. In tests, do not merely inspect **getFrom()[0].toString()**, because that string can contain encoded-words or quotes depending on valid representation rules.

An email can technically have multiple authors in the From header per mail standards, yet most transactional application emails should use a single approved From address. If the service enforces a single-From rule, assert the exact count.

## 15. Compare To, Cc, and Bcc lists as sets when appropriate

A service might be allowed to change recipient order without changing business meaning. In that case, asserting ordered arrays unnecessarily makes tests brittle.

Example:

~~~java
import java.util.Set;

Set<String> recipients = Set.copyOf(
        emailAddresses(
                actual.getRecipients(Message.RecipientType.CC)
        )
);

assertEquals(
        Set.of(
                "sales@example.com",
                "support@example.com"
        ),
        recipients
);
~~~

**Note on duplicates:** converting a List to a Set loses count information and duplicate elements. If business rules require **no duplicate recipients**, check the count or deduplication rules separately. Do not compare only a Set and assume there are no duplicates.

### Testing when there is no Cc/Bcc

With MimeMessage:

~~~java
assertEquals(
        List.of(),
        emailAddresses(
                actual.getRecipients(Message.RecipientType.CC)
        )
);

assertEquals(
        List.of(),
        emailAddresses(
                actual.getRecipients(Message.RecipientType.BCC)
        )
);
~~~

The test helper converts null to List.of() to clearly express **no recipients of that type**, avoiding coupling to null versus empty arrays.

## 16. Test Bcc properly: recipient present, not placed in To or Cc

Bcc requires special testing because a data bug can expose blind recipients to other recipients.

At the **MimeMessage preparation unit-test level**, you can verify:

~~~java
List<String> to = emailAddresses(
        actual.getRecipients(Message.RecipientType.TO)
);
List<String> cc = emailAddresses(
        actual.getRecipients(Message.RecipientType.CC)
);
List<String> bcc = emailAddresses(
        actual.getRecipients(Message.RecipientType.BCC)
);

assertEquals(
        List.of("customer@example.net"),
        to
);
assertEquals(
        List.of("manager@example.com"),
        cc
);
assertEquals(
        List.of("audit@example.com"),
        bcc
);

assertFalse(to.contains("audit@example.com"));
assertFalse(cc.contains("audit@example.com"));
~~~

This example requires JUnit 5's **assertFalse** import. The assertions confirm **audit@example.com** is classified under Bcc and not in To or Cc.

### Pre-send Bcc header differs from post-transport Bcc header

A common mistake is writing:

~~~java
// Wrong target for a MimeMessage being prepared.
assertNull(actual.getRecipients(Message.RecipientType.BCC));
~~~

If **helper.setBcc(...)** was called, on the **pre-send MimeMessage object**, the Bcc list must remain accessible so the mail transport knows who to deliver to. A unit test inspecting the pre-send object should **expect Bcc to be present**, not remove it merely to pass a "no leak" assertion.

The real privacy rules to check at the transport stage are:

- Bcc addresses are used as valid recipients in the **SMTP envelope**.
- To/Cc and Bcc recipients do not see the Bcc list in **the delivered email's headers**.
- Nowhere in the **body, Subject, or custom headers** is the Bcc list accidentally copied.

Bcc header behavior on the wire depends on the transport, message construction, and sending infrastructure. Therefore, to verify Bcc is not exposed in actual MIME DATA, you must test against an **SMTP test server** and inspect the transmitted message, rather than only reading the pre-send object.

## 17. Integration tests to verify Bcc privacy

A test can use an SMTP sandbox or local SMTP test server accepting connections:

~~~text
Spring service
       |
       | RCPT TO:<customer@example.net>
       | RCPT TO:<audit@example.com>
       |
       | DATA:
       |   From: orders@example.com
       |   To: customer@example.net
       |   Subject: Order confirmation
       |   (audit@example.com not exposed)
       v
SMTP test server
       |
       +--> stores envelope recipients
       +--> stores actual MIME DATA
~~~

What to assert:

1. The SMTP envelope contains **customer@example.net** and **audit@example.com**.
2. The MIME DATA received by recipients does not expose the Bcc list.
3. No To/Cc header accidentally contains audit@example.com.
4. If the service uses custom headers with internal IDs, those headers do not leak unauthorized data.

Some test servers store message and envelope separately, while others capture the raw SMTP session. Choose a tool capable of observing **both envelope and DATA**, because inspecting only the headers of a pre-send MimeMessage does not provide sufficient evidence.

Never use real recipient accounts or production SMTP just to test Bcc secrecy.

## 18. To/Cc/Bcc and authorization policy

An email can be syntactically valid yet still be sent to the wrong person.

For example, an order belongs to customer A, yet the service accidentally uses customer B's email:

~~~text
Order owner: A
Expected To: a@example.net
Actual To: b@example.net
~~~

The MimeMessage is completely valid syntactically. Unit tests must verify **business mapping**, not merely that an address contains an @ sign.

Prepare test data that clearly distinguishes roles:

~~~text
ownerEmail      = owner@example.net
otherUserEmail  = other@example.net
supportEmail    = support@example.com
auditEmail      = audit@example.com
~~~

Assertions should point to the exact role:

~~~java
assertEquals(
        List.of("owner@example.net"),
        emailAddresses(
                actual.getRecipients(Message.RecipientType.TO)
        )
);
~~~

In multi-tenant applications, tests should also verify:

- Admins of another tenant are not added to Cc.
- A From address belonging to another brand/tenant is not used.
- Users cannot specify an arbitrary Bcc bypassing authorization.
- Tenant A's data is never accidentally sent to tenant B's recipients.

These are **authorization and data-routing** bugs, not SMTP bugs. Application-layer tests can use fake repositories or in-memory data instead of needing a real database.

## 19. Verify From does not depend on untrusted input

Example API receiving an email send request:

~~~json
{
  "orderId": "ORD-101",
  "requestedFrom": "attacker@outside.example"
}
~~~

If the application takes **requestedFrom** directly to call **helper.setFrom(...)**, a user could attempt to spoof a sender or break domain authentication.

Design the service to take From from application-controlled configuration:

~~~java
public final class CustomerNotificationService {

    private final JavaMailSender sender;
    private final String approvedFrom;

    public CustomerNotificationService(
            JavaMailSender sender,
            String approvedFrom
    ) {
        this.sender = sender;
        this.approvedFrom = approvedFrom;
    }

    // When building the message:
    // helper.setFrom(approvedFrom);
}
~~~

A unit test can pass a request containing a spoofed **requestedFrom** and verify the resulting message still uses **approvedFrom**. If the application supports choosing among multiple From addresses by tenant or product line, test the selection policy and the list of verified domains.

Do not hard-code a fixed sending address solely for ease of testing. You can inject configuration/ports and verify they are used properly, keeping sender selection in the appropriate business layer.

## 20. Test duplicate recipients across To, Cc, and Bcc

A recipient might accidentally appear in multiple fields simultaneously:

~~~text
To:   customer@example.net
Cc:   support@example.com
Bcc:  customer@example.net
~~~

The consequence depends on the mail transport and provider: the recipient may receive duplicates or display behavior may violate intent. If the business rule is that **each address appears in only one group**, test this before sending.

Example when building the model:

~~~java
Set<String> all = new HashSet<>();

for (String recipient : to) {
    assertTrue(all.add(recipient));
}
for (String recipient : cc) {
    assertTrue(all.add(recipient));
}
for (String recipient : bcc) {
    assertTrue(all.add(recipient));
}
~~~

This illustrates duplicate checking for normalized test data. In a real product, email comparison rules must be clearly defined:

- Email domains are case-insensitive per DNS.
- Local-parts per email standards should not be assumed always case-insensitive, even though many providers treat them that way.
- Dots and plus addressing can carry different meanings across providers.

Do not strip dots, drop suffixes after a plus sign, or lowercase the entire address using one provider's rules to invent a deduplication algorithm for all domains.

## 21. Test Subject is non-empty and not mis-mapped

Depending on business requirements, an email may be required to have a meaningful subject. For instance, a delivered order should never have:

~~~text
Subject: null
Subject: ""
Subject: "Untitled"
~~~

With a validating service, you can test:

~~~java
@Test
void rejectsBlankSubjectBeforeSending() {
    JavaMailSender sender = mock(JavaMailSender.class);
    ValidatingMailService service = new ValidatingMailService(sender);

    IllegalArgumentException exception = assertThrows(
            IllegalArgumentException.class,
            () -> service.send(requestWithSubject("   "))
    );

    assertEquals(
            "Subject must not be blank",
            exception.getMessage()
    );
    verifyNoInteractions(sender);
}
~~~

**ValidatingMailService** and **requestWithSubject(...)** are example application components to implement; they are not default Spring Mail APIs. The test is only meaningful if the service contract genuinely specifies that Subject cannot be blank and validation occurs before interacting with the mail sender.

When Subject content contains user-supplied data, also account for newline characters, invalid data, or signs of header injection. Validate inputs at the boundary and use proper MIME-building APIs instead of concatenating raw SMTP headers manually.

## 22. Test when To is missing or there are no valid recipients

One situation requiring an explicit policy is an email without **To**, yet with Cc or Bcc. At the SMTP level, recipients can be supplied through various address fields. However, **many business applications require at least one primary recipient** to avoid routing mistakes.

Policy example:

~~~text
Business rule:
    To must not be empty for order confirmation emails.

Input:
    To  = []
    Cc  = ["agent@example.com"]
    Bcc = ["audit@example.com"]

Expected:
    Reject request before sending.
~~~

If the system allows Bcc-only emails, do not enforce a blanket "must have To" rule. Instead, require at least one **SMTP recipient** and test the recipient-visibility policy for that email type.

Tests should also verify **mailSender.send(...) is not called when the request is invalid**, avoiding side effects before validation completes.

## 23. Test null inputs and immutable lists

For records containing Lists, decide how null is handled:

- **Null**: data was not provided or there is a caller bug.
- **Empty list**: an intentionally empty recipient list.

If the contract specifies that lists are never null, you can create defensive snapshots:

~~~java
import java.util.List;
import java.util.Objects;

public record SafeMailRequest(
        String subject,
        String from,
        List<String> to,
        List<String> cc,
        List<String> bcc
) {
    public SafeMailRequest {
        subject = Objects.requireNonNull(subject);
        from = Objects.requireNonNull(from);
        to = List.copyOf(Objects.requireNonNull(to));
        cc = List.copyOf(Objects.requireNonNull(cc));
        bcc = List.copyOf(Objects.requireNonNull(bcc));
    }
}
~~~

**List.copyOf** creates an unmodifiable copy and rejects null elements. To leave Cc/Bcc empty, callers must pass **List.of()**. The service is unaffected if the caller mutates an ArrayList after constructing the request.

If the product prefers defaulting null to an empty list, that alternative can also be reasonable, provided it is explicit in the constructor and unit tests. Do not let a NullPointerException at **request.cc().isEmpty()** be the sole way invalid data is reported.

## 24. Test multiple recipients without manually joining addresses

**MimeMessageHelper** has overloads accepting address arrays:

~~~java
helper.setTo(new String[] {
        "primary@example.net",
        "second@example.net"
});

helper.setCc(new String[] {
        "support@example.com",
        "manager@example.com"
});

helper.setBcc(new String[] {
        "audit@example.com",
        "compliance@example.com"
});
~~~

The advantage is that each address is processed by the corresponding API. Avoid manually concatenating a multi-address header string when dedicated recipient APIs already exist.

Test:

~~~java
assertEquals(
        Set.of(
                "primary@example.net",
                "second@example.net"
        ),
        Set.copyOf(
                emailAddresses(
                        actual.getRecipients(Message.RecipientType.TO)
                )
        )
);
~~~

If the list can contain duplicates, add a separate count assertion so Set does not hide them.

A recipient test should never only assert **getAllRecipients().length**. Two messages can have the same total recipient count yet completely different To/Cc/Bcc mappings with very different business consequences.

## 25. Verify send count and avoid side effects in unit tests

A test that verifies headers without verifying that the service actually called JavaMailSender can miss control-flow bugs.

Example:

~~~java
ArgumentCaptor<MimeMessage> captor =
        ArgumentCaptor.forClass(MimeMessage.class);

verify(sender, times(1)).send(captor.capture());
~~~

If the service must send exactly one email, **times(1)** states that contract clearly. By default Mockito also treats **verify(sender).send(...)** as expecting one call for the specified invocation.

For invalid requests:

~~~java
verify(sender, never()).send(any(MimeMessage.class));
~~~

The example above requires static imports for **times**, **never**, and **any**. When a service might construct a message before detecting an error, decide whether calling **createMimeMessage()** is acceptable; the most important thing is usually **not calling send** when validation fails.

### Do not assert meaningless ordering

A test does not need to assert that **setSubject** was called before **setTo** if setter order does not affect the outcome or contract.

Good tests prioritize:

- Correct final Subject.
- Correct From header.
- Correct To/Cc/Bcc lists.
- Exact number of send calls.
- No send when data is invalid.

Only assert method ordering when that order actually produces significant behavior.

## 26. Test MIME creation errors separately from SMTP send errors

When creating a **MimeMessage**, errors such as invalid addresses or MIME handling can throw **MessagingException**. When calling **JavaMailSender.send(...)**, the Spring Mail layer can throw **MailException** depending on the send failure.

Distinguish two phases:

~~~text
PREPARE
  Create MimeMessage
  Set Subject / From / To / Cc / Bcc
  Set MIME body
      |
      v
SUBMIT
  JavaMailSender.send(...)
~~~

A unit test can simulate a send failure using Mockito:

~~~java
import org.springframework.mail.MailSendException;

doThrow(new MailSendException("SMTP unavailable"))
        .when(sender)
        .send(any(MimeMessage.class));
~~~

Then execute the service and verify how the application handles the error per contract: propagating the exception, translating it into a business error, or recording a retry notification. Never blindly retry every send call on MailSendException; some SMTP failures have ambiguous outcomes and can cause duplicate sends.

### Do not confuse header tests with retry tests

The focus here is **Subject/From/To/Cc/Bcc**. If the service also handles retries, write separate tests for the retry policy instead of mixing unrelated behaviors into one test.

For example, a header test should configure the mock sender only as a collaborator recording the call, without spinning up an SMTP server or testing connection timeouts.

## 27. Test when Subject/recipients come from templates

In many applications, the Subject is not a literal string but rendered from a template and business data:

~~~java
String subject = subjectRenderer.render(
        "order.shipped.subject",
        Map.of(
                "orderCode", order.getCode(),
                "customerName", order.getCustomerName()
        )
);
~~~

When using a separate renderer, there are two ways to test:

**Test the resolver/template separately:** verify the template key, data, and language produce the expected subject.

**Test the mail-sending service:** supply a pre-rendered subject or a fake renderer and verify the value actually placed on the MimeMessage.

Example:

~~~java
when(subjectRenderer.render(
        eq("order.shipped.subject"),
        anyMap()
)).thenReturn("Order ORD-101 has shipped");
~~~

After the service runs:

~~~java
assertEquals(
        "Order ORD-101 has shipped",
        actual.getSubject()
);
~~~

**subjectRenderer** in the example is an application-specific interface, not a default Spring Mail component. Use Mockito to keep tests scoped to selecting and assigning the Subject, rather than depending on a real template file system.

### Locale-formatted data

If the application supports multiple languages, include cases such as:

~~~text
locale=vi-VN -> Subject: Đơn hàng đã được xác nhận
locale=en-US -> Subject: Your order is confirmed
~~~

Unit tests must verify the same event with different locales still preserves the **correct recipients and From**. Never change recipients simply because the content language changed.

## 28. Test with JUnit 5 parameterized tests

When multiple notification types share the same From/To/Cc/Bcc rules, parameterized tests help avoid duplicating similar test methods.

Example testing notification types and subjects:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class MailSubjectPolicyTest {

    @ParameterizedTest
    @CsvSource({
        "ORDER_PAID, Payment recorded",
        "ORDER_SHIPPED, Order is out for delivery",
        "ORDER_CANCELLED, Order has been cancelled"
    })
    void mapsEventToCorrectSubject(
            String eventType,
            String expectedSubject
    ) {
        String result = subjectPolicy.subjectFor(eventType);

        assertEquals(expectedSubject, result);
    }
}
~~~

This is an illustrative skeleton: **subjectPolicy** must be an object initialized in the test according to the application's implementation, not a built-in JUnit variable. This snippet focuses on mapping events to subjects.

If you want to verify the entire message at once, use **@MethodSource** to supply test data including:

- Event type.
- Expected Subject.
- Expected From.
- To list.
- Cc list.
- Bcc list.

When there are many test cases, name them clearly so failures immediately pinpoint which event and recipient policy broke.

## 29. Test with multiple senders or multiple brands

A system may use multiple SMTP accounts:

~~~text
Transactional sender:
  From: receipts@example.com

Security sender:
  From: security@example.com

Support sender:
  From: support@example.com
~~~

Each email type must use the right From and the right sender bean. When a service receives **JavaMailSender** via constructor or **@Qualifier**, each service can be tested separately with a mock of its corresponding sender.

Example:

~~~java
JavaMailSender transactionalSender = mock(JavaMailSender.class);
JavaMailSender securitySender = mock(JavaMailSender.class);

// Create the service using the application's constructor.
// Execute sending the security email.

verify(securitySender).send(any(MimeMessage.class));
verify(transactionalSender, never())
        .send(any(MimeMessage.class));
~~~

This is a conceptual structure; define the service and stub **createMimeMessage()** if the sending path creates a MimeMessage. It helps prevent a sensitive notification from accidentally going through a marketing sender or another brand's From address.

### Multi-tenant testing

If each tenant has its own From address, use at least two distinct tenants:

~~~text
Tenant A:
  From = a-notifications@a.example
  To   = user-a@customer.example

Tenant B:
  From = b-notifications@b.example
  To   = user-b@customer.example
~~~

Test that tenant A's flow never contains tenant B's recipients or From. Do not use identical test data across tenants, or tests will fail to catch tenant mix-ups.

## 30. Test when the sender receives an array of messages

Spring Mail supports sending multiple **SimpleMailMessage** or **MimeMessage** instances in one call. When batching is an actual service requirement, verify each element:

~~~java
ArgumentCaptor<MimeMessage[]> captor =
        ArgumentCaptor.forClass(MimeMessage[].class);

verify(sender).send(captor.capture());

MimeMessage[] batch = captor.getValue();
assertEquals(2, batch.length);
~~~

Then read **getSubject()**, **getFrom()**, and **getRecipients(...)** for each message matched by notification ID/test fixture.

If batch ordering is not guaranteed by contract, do not assume message[0] is always type A. Instead, match by unique ID or subject in the test data, as long as sensitive info is not logged.

### Bcc in batches

A dangerous bug is reusing one MimeMessage and only swapping To across loop iterations while forgetting to clear old Cc/Bcc. Recipients from the previous email then bleed into the next email.

Tests should create two notifications with **completely different recipient lists**, then verify:

- Message A contains only A's recipients.
- Message B contains only B's recipients.
- No address from B appears in A's To/Cc/Bcc and vice versa.

If the service is designed to create a **new MimeMessage per notification**, tests can assert the two elements are distinct objects and each has its own headers.

## 31. Should headers be tested with text snapshots?

A snapshot like:

~~~text
From: orders@example.com
To: buyer@example.net
Cc: agent@example.com
Bcc: audit@example.com
Subject: =?UTF-8?...?=
~~~

may look convenient, yet has drawbacks:

- Display names can be encoded with different valid MIME methods.
- Header order can vary.
- Long headers can be folded across multiple lines.
- MIME boundaries and other parameters can vary.
- Storing raw Bcc and recipient data in snapshots can create information-exposure risks.

For unit testing email routing logic, **semantic API assertions** are usually clearer and more resilient:

~~~java
actual.getSubject();
actual.getFrom();
actual.getRecipients(Message.RecipientType.TO);
actual.getRecipients(Message.RecipientType.CC);
actual.getRecipients(Message.RecipientType.BCC);
~~~

If snapshots are needed, snapshot only normalized stable fields and use non-sensitive dummy test data.

## 32. Keep tests independent, fast, and repeatable

An email unit test should:

- Not send real SMTP traffic.
- Not read production data or real email accounts.
- Not depend on system time if the subject includes dates; inject a Clock or pass a fixed timestamp.
- Not depend on ordering not promised by business rules.
- Not boot the full Spring application context when testing a single constructor-injected service.
- Not print sensitive email addresses to test logs.
- Use addresses in example domains, not real users' addresses.

### Use Clock if the subject includes dates/times

Example subject with a date:

~~~text
Notification for 12/11/2026
~~~

If code calls **LocalDate.now()** directly, tests may fail on another day. Inject **java.time.Clock**:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-12T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

When the renderer uses this Clock, the date in the Subject is completely predictable. Note that the Instant in the example corresponds to different calendar dates depending on timezone; tests must specify the notification's timezone explicitly.

## 33. Use MockitoExtension and @Mock when there are many dependencies

In the earlier examples, mocks were created manually:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
~~~

For services with multiple dependencies, you can use JUnit Jupiter's Mockito extension:

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class MimeMailServiceWithExtensionTest {

    @Mock
    private JavaMailSender sender;

    private MimeMailService service;

    @BeforeEach
    void setUp() {
        when(sender.createMimeMessage()).thenAnswer(invocation ->
                new MimeMessage(
                        Session.getInstance(new Properties())
                )
        );

        service = new MimeMailService(sender);
    }

    @Test
    void usesExpectedSender() throws Exception {
        service.send(new MimeMailRequest(
                "Account notification",
                "security@example.com",
                java.util.List.of("owner@example.net"),
                java.util.List.of(),
                java.util.List.of(),
                "There was a change related to your account."
        ));

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender).send(captor.capture());

        MimeMessage actual = captor.getValue();
        assertEquals(
                "Account notification",
                actual.getSubject()
        );
    }
}
~~~

The example requires static import **assertEquals** from JUnit Jupiter. **MockitoExtension** initializes mocks and manages Mockito's lifecycle in the test class. It does not start a Spring context or open SMTP connections.

If different tests create multiple messages or follow different sending paths, structure setUp appropriately. Avoid stubbing calls unused in a specific test when using strict stubbing; keep test behavior explicit rather than sprinkling lenient stubs everywhere.

## 34. Separate responsibilities between resolvers and mail transport

A testable design often looks like:

~~~text
OrderEvent
   |
   v
MailRecipientResolver
   -> returns To, Cc, Bcc per business rules
   |
   v
MailSubjectRenderer
   -> returns Subject per locale/event
   |
   v
MailMessageFactory
   -> creates SimpleMailMessage / MimeMessage
   |
   v
JavaMailSender
~~~

With this split, you can test by layer:

| Test target | Main focus |
|---|---|
| **RecipientResolverTest** | Who goes into To, Cc, Bcc for an event? |
| **SubjectRendererTest** | Subject by event, locale, and business data |
| **MessageFactoryTest** | Mapping Subject/From/To/Cc/Bcc onto the mail object |
| **NotificationServiceTest** | Calling factory and sender the right number of times with the right mail type |
| **SMTP integration test** | How transport handles envelope, Bcc, MIME, and submission |

There is no need to split a tiny application into five classes. Yet as rules grow, packing recipient selection, content rendering, MIME, and retries into one service makes unit tests both long and hard to diagnose.

## 35. Example test scenario table by email type

Suppose the system has these notification types:

| Email | Expected Subject | Expected From | To | Cc | Bcc |
|---|---|---|---|---|---|
| Order placement confirmation | Order ORD-101 created | orders@example.com | buyer@example.net | None | audit@example.com |
| Payment confirmation | Payment received for ORD-101 | billing@example.com | buyer@example.net | None | finance-audit@example.com |
| Security alert | Account security notice | security@example.com | owner@example.net | None | None |
| Support request | Support request T-202 | support@example.com | agent@example.com | supervisor@example.com | None |

A minimal test suite can use these scenarios as fixtures. Each test verifies:

1. Subject belongs to the right email type.
2. From matches an allowed account or domain.
3. To matches the owner of the notification.
4. Cc is present only when rules require it.
5. Bcc is not leaked into To/Cc.

The values above are examples only; they are not mandatory policies of Spring Framework Mail.

### Why use distinct addresses?

If To, Cc, and Bcc all use **test@example.com**, code that swaps lists can still pass loose assertions. Fixtures should use distinct addresses with distinct roles so tests catch mis-mapped fields.

## 36. Common testing mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Only using verify(sender).send(any()) | Unknown whether Subject/From/To/Cc/Bcc are right | Use ArgumentCaptor and assertions |
| Mocking MimeMessage too | MIME setters/getters do not reflect real behavior without manual stubbing | Use a real in-memory MimeMessage |
| Asserting raw encoded-word Subject | Tests couple to MIME representation | Use MimeMessage.getSubject() |
| Comparing raw To/Cc headers | Brittle due to display names and header folding | Use getRecipients(...) |
| Not checking Bcc | Blind recipients may be placed in To/Cc by mistake | Assert the Bcc list separately |
| Asserting Bcc must be null before send | Breaks valid prepared blind recipients | Read pre-send Bcc; test secrecy at transport |
| Using getAllRecipients() to check roles | Fails to catch To/Cc/Bcc swaps | Assert by RecipientType |
| Comparing only a Set of recipients | Misses duplicates | Check count if required |
| Always requiring non-null Cc/Bcc | Couples tests to unset representation | Normalize null to empty list if appropriate |
| Sharing email fixtures across all tenants | Fails to catch cross-tenant recipient leaks | Use distinct role-specific addresses |
| Starting real SMTP in unit tests | Slow, flaky, causes side effects | Mock JavaMailSender |
| Using @SpringBootTest for simple services | Increases runtime and environment coupling | Constructor injection with JUnit/Mockito |
| Not checking From | May send under wrong brand or identity | Assert From and sender-selection policy |
| Checking recipient count without addresses | Misses sending to the wrong person | Compare specific addresses |
| Assuming send without exception means delivered | Confuses submission with delivery | Integration/provider events for delivery |
| Using pre-send tests to claim Bcc is hidden in SMTP DATA | Testing the wrong layer | SMTP test server checking envelope and DATA |

## 37. Troubleshooting when a header test fails

Common symptoms:

### Actual Subject is null

Check whether the service calls **setSubject(...)** and whether the renderer returned null. If the test reads raw MIME headers, switch to the **getSubject()** API for semantic assertions.

### From differs from expected

Check sender configuration, per-tenant From mapping, or whether requests are allowed to override From. For MimeMessage with a display name, read **InternetAddress.getAddress()** and **getPersonal()** separately.

### To and Cc are swapped

Check the mapping between **request.to()** and **helper.setTo(...)** and between **request.cc()** and **helper.setCc(...)**. Use fixtures with clearly distinct addresses.

### Bcc is missing in pre-send MimeMessage

Check whether the service calls **helper.setBcc(...)** with a non-empty list. If Bcc is optional, check whether the policy actually selected a blind recipient. Do not confuse pre-send checks with checking headers transmitted over SMTP.

### Mock sender records no invocation

Check whether the service calls **send(SimpleMailMessage)**, **send(MimeMessage)**, or an array overload. ArgumentCaptor must match the exact type. If multiple sender beans exist, verify which mock was actually injected.

### Unicode test fails

Check the charset used when constructing MimeMessageHelper. Avoid comparing raw encoded-words if the goal is the user-visible Subject. Ensure test source files are saved as UTF-8.

### Test expects empty list but gets null

Check whether the service skips Cc/Bcc setters when the list is empty. If that is intentional behavior, assert "no recipients" instead of requiring the field to be an empty array.

## 38. Recommended testing workflow

When writing unit tests for a new email, you can follow this sequence:

1. Identify the **business event** triggering the email.
2. Identify the **expected Subject** by event and locale.
3. Identify the **authorized From**.
4. Identify the exact **To**, **Cc**, and **Bcc** lists.
5. Prepare fixtures with distinct addresses, avoiding unintended role overlap.
6. Mock **JavaMailSender**; if using MIME, return a **real in-memory MimeMessage**.
7. Invoke the service under test.
8. Use **ArgumentCaptor** to capture the message passed to the sender.
9. Assert Subject, From, each RecipientType, and send invocation count.
10. Add cases for absent Cc/Bcc, multiple recipients, and invalid inputs when policy requires.
11. Keep separate transport tests for **Bcc privacy, SMTP envelope, MIME serialization, and delivery**.

This is a practical workflow for software engineers designing tests, not a substitute for real SMTP verification.

## 39. Key takeaways

To test **Subject, From, To, Cc, and Bcc** in Spring Framework Mail, start by choosing the right object:

- For **SimpleMailMessage**, use **Mockito ArgumentCaptor<SimpleMailMessage>**, then read **getSubject(), getFrom(), getTo(), getCc(), getBcc()**.
- For **MimeMessage**, mock **JavaMailSender.createMimeMessage()** to return a **real in-memory MimeMessage**, then capture the send call. Read **getSubject(), getFrom()**, and **getRecipients(Message.RecipientType.TO/CC/BCC)**.
- For **From with a display name**, assert **InternetAddress.getAddress()** and **getPersonal()** separately.
- For **Unicode Subjects**, compare the decoded value rather than raw MIME headers.
- For **empty Cc/Bcc**, test according to business rules; do not assume null and empty arrays always mean different things.

In particular, **Bcc must be tested at two layers**: unit tests verify that Bcc addresses are prepared properly and never placed in To/Cc; integration tests verify that the transport does not expose Bcc in delivered content/headers to out-of-scope recipients. Never use unit tests on a pre-send MimeMessage to claim secrecy on the wire has been verified.

**A good email test must prove exactly who receives the message, who can see whom, and which subject and sender recipients will see.** Mockito lets you verify those decisions quickly and independently of SMTP; integration tests add evidence of how the mail transport actually forwards the message.




