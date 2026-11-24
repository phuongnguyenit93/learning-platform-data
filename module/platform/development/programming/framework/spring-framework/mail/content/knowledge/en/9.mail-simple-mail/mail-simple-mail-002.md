# Setting From, To, Cc, Bcc, and Subject

When sending a simple text email with **Spring Framework Mail**, before worrying about the content, the application must decide **who the sender is**, **who receives the message**, **who receives a copy**, **who receives a blind copy**, and **what subject the recipient will see**. In Spring, this information is usually set through the `setFrom(...)`, `setTo(...)`, `setCc(...)`, `setBcc(...)`, and `setSubject(...)` methods of `SimpleMailMessage`.

Example:

~~~java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notifications@example.com");
mail.setTo("customer@example.net");
mail.setCc("account-manager@example.com");
mail.setBcc("audit@example.com");
mail.setSubject("Order A123 confirmation");
mail.setText("Your order A123 has been recorded.");

mailSender.send(mail);
~~~

The email above has only **plain text** content. However, the addresses and the subject still have operational meaning: `Cc` may expose addresses to other people, `Bcc` affects how recipients see the distribution list, and `From` may be rejected by the provider if the application is not allowed to use that address.

## 1. Understand the five fields before writing code

| Field | Question to answer | Shown in the email client | Spring Mail API |
| --- | --- | --- | --- |
| **From** | In whose name is the message sent? | Usually displayed clearly | `setFrom(String)` |
| **To** | Who are the primary recipients? | Usually shown to recipients | `setTo(String...)` |
| **Cc** | Who needs to know the information through a copy? | Usually shown to the other recipients | `setCc(String...)` |
| **Bcc** | Who needs to receive a blind copy? | Normally not shown to the other recipients | `setBcc(String...)` |
| **Subject** | What is the message about? | Shown in the message list and when opening the message | `setSubject(String)` |

These fields belong to the **email message**, not to a user management API or an authorization system. Setting `Cc` does not grant permission to view an order; setting `Bcc` does not encrypt the email; setting `From` does not by itself prove that the business owns the sending domain.

In the `SimpleMailMessage` class, the values of the fields are stored in a Java object. Only the call to `mailSender.send(...)` asks the application to submit the message to the configured transport system.

## 2. From: the sending address

`From` answers the question **"Who is the author/sender of this email?"**. For automated mail, this is usually a shared address of the application or of a department:

~~~java
mail.setFrom("no-reply@example.com");
~~~

Or:

~~~java
mail.setFrom("billing@example.com");
~~~

In the mailbox, recipients usually see `From` before opening the email. Therefore, the address should help them recognize the correct source of the notification.

### 2.1. From is not necessarily the account used to log in to SMTP

For example, the application has:

~~~yaml
spring:
  mail:
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

And the Java code:

~~~java
mail.setFrom("billing@example.com");
~~~

`spring.mail.username` is the account that **authenticates with the SMTP provider**, while `From` is the address displayed in the **email header**. They may be the same or different, depending on the provider's policy. A technical account may be allowed to send from multiple verified addresses in the same domain; another provider may only allow the account's own address.

You should not set `From: ceo@another-company.example` on your own and then expect the system to send successfully. The SMTP provider may reject it, replace the address, or flag the message as violating policy. Mechanisms such as SPF, DKIM, and DMARC also affect the authentication and trustworthiness of the message.

### 2.2. From differs from the address for delivery failures

In SMTP, the application or provider can use the **envelope sender** (`MAIL FROM`) to receive notifications of unsuccessful delivery (bounces). This is transport information and may differ from the `From` header that users see.

~~~text
SMTP envelope:
  MAIL FROM:<bounce-814@mailer.example.com>
  RCPT TO:<customer@example.net>

Message header:
  From: billing@example.com
  To: customer@example.net
  Subject: November invoice
~~~

`SimpleMailMessage.setFrom(...)` sets the From information of the message; you should not treat it as an API that controls the entire reverse-path or manages the provider's bounces. If you need to control bounces, the application must look at how to configure the SMTP envelope, the provider, and the corresponding DSN/webhook events.

### 2.3. From and display name

An email may display:

~~~text
From: "Customer Support" <support@example.com>
~~~

With a **simple address**, `SimpleMailMessage.setFrom("support@example.com")` is a clear choice. If you need a display name with Vietnamese diacritics, or detailed management of headers and encoding, you should use Spring Mail's `MimeMessageHelper.setFrom(address, personalName)`:

~~~java
MimeMessage mime = javaMailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, false, "UTF-8");
helper.setFrom("support@example.com", "Support Team");
~~~

The `SimpleMailMessage` class only provides setters that accept an address string; it has no dedicated API to pass a display name and charset like the MIME helper. Switching to MIME is reasonable when the header has complex presentation requirements.

## 3. To: the primary recipients

`To` specifies one or more primary recipient addresses of the email.

Send to one person:

~~~java
mail.setTo("customer@example.net");
~~~

Send to several people:

~~~java
mail.setTo(
    "alice@example.net",
    "bob@example.net"
);
~~~

Or when the application already has an array:

~~~java
String[] recipients = {
    "alice@example.net",
    "bob@example.net"
};
mail.setTo(recipients);
~~~

`setTo(...)` accepts multiple values through Java varargs. This means a single message can be sent to multiple primary recipients without creating a separate `SimpleMailMessage` for each address.

### 3.1. Are multiple To addresses separate emails?

If you set:

~~~java
mail.setTo("alice@example.net", "bob@example.net");
mail.setText("Hello everyone.");
~~~

then the application is describing **one message with multiple recipients**. Basically, the two recipients get the same content and can see each other's addresses in the `To` header. This is not an appropriate approach if the content has personal data specific to each person.

In contrast:

~~~java
SimpleMailMessage forAlice = new SimpleMailMessage();
forAlice.setTo("alice@example.net");
forAlice.setText("Hello Alice.");

SimpleMailMessage forBob = new SimpleMailMessage();
forBob.setTo("bob@example.net");
forBob.setText("Hello Bob.");
~~~

these are **two separate messages**, whose sending status and content can be managed independently. In a system that sends transaction confirmations, invoices, or account-related notifications, the per-recipient model is usually more reasonable.

### 3.2. An address in To does not prove the user exists

A string such as `unknown@example.net` may look syntactically valid, but the actual mailbox may not exist, may be locked, or the destination server may not accept the mail. When sending, the SMTP server may reject it immediately or accept the mail and then generate a bounce later.

If users enter addresses through a form, the application needs to validate the data and business rules. For account-related addresses, a process to confirm ownership of the email may be necessary; merely checking for an `@` character is not enough.

## 4. Cc: send a copy and let everyone know

**Cc** stands for *Carbon Copy*. A person in `Cc` receives a copy of the email, usually meaning they are **kept informed** rather than bearing primary responsibility.

For example, the customer receives the notification and the responsible staff member receives a copy:

~~~java
mail.setTo("customer@example.net");
mail.setCc("account-manager@example.com");
~~~

Recipients in `To` usually see that `account-manager@example.com` was Cc'd, and Cc recipients usually also see the other To/Cc addresses. This can be useful in internal discussions but needs consideration when communicating with customers.

### 4.1. When should you use Cc?

Some reasonable cases:

- Send an email to the primary owner and Cc the project manager.
- Send processing results to a relevant group that needs to see the list of recipients together.
- Keep the participants of a business discussion in the same conversation thread.

Some cases where you **should not use Cc**:

- Sending personal notifications to hundreds of unrelated users.
- Sending order or account data that this recipient is not allowed to see.
- Cc'ing outsiders just to "keep a copy" when there is no clear business reason.

**Cc is not just a technical choice:** it is also a decision to share the email's addresses and content with other parties.

### 4.2. Cc and Reply All

If the email has:

~~~text
From: sender@example.com
To: alice@example.net
Cc: bob@example.net
~~~

when Alice clicks **Reply All**, Bob can usually be added to the recipient list of the reply. The exact way recipients are chosen depends on the email client. Therefore, putting someone in Cc can pull them into follow-up discussions, even when the original purpose was only to receive a notification.

## 5. Bcc: send a blind copy

**Bcc** stands for *Blind Carbon Copy*. The person whose address is in `Bcc` is added to the list of recipients, but information about them is **not shown to the other recipients in the delivered copy of the email** under normal sending.

~~~java
mail.setTo("customer@example.net");
mail.setBcc("archive@example.com");
~~~

In the example, the system sends an email to the customer and adds one blind-copy recipient. The customer normally does not see `archive@example.com` in the header of the message delivered to them.

### 5.1. Bcc is not encryption and does not guarantee absolute secrecy

Bcc is a **mechanism for delivery and address display**; it does not encrypt the email content. A Bcc recipient can still:

- read all the content they received;
- forward the message or reveal on their own that they received it;
- inadvertently reply in a way that exposes their participation in the conversation;
- appear in the logs/metadata of the sending system, the provider, or where they receive mail.

Servers and email clients may handle the Bcc header in various standards-compliant ways, such as removing that header from the transmitted copy. Therefore, **do not rely on reading the `Bcc` header in the recipient's mailbox to verify the entire original Bcc list**.

If the goal is to control access to the content, authorization and data policies must be implemented at the application layer. Bcc does not prevent a recipient from forwarding the content that was sent to them.

### 5.2. Is Bcc suitable for sending bulk notifications?

A pattern you may see:

~~~java
mail.setFrom("events@example.com");
mail.setTo("events@example.com");
mail.setBcc(
    "participant1@example.net",
    "participant2@example.net",
    "participant3@example.net"
);
mail.setSubject("Next month's event schedule");
~~~

For a shared message, some systems use Bcc to avoid exposing the recipient list. However, **Bcc is not a substitute for a bulk mail platform or a controlled bulk sending mechanism**: you must also consider provider policies, quotas, recipient count limits, spam prevention, unsubscribe where relevant, and the ability to record status per address.

When you need personalization, separate bounce/retry handling, rate limiting, or to avoid data exposure, you should create **a separate message for each recipient** through a job/queue or an appropriate sending tool.

### 5.3. Example of Cc and Bcc in the same message

~~~java
mail.setTo("customer@example.net");
mail.setCc("account-manager@example.com");
mail.setBcc("audit@example.com");
~~~

The result in terms of intent:

| Address | Receives the content? | May appear to the other recipients? |
| --- | --- | --- |
| `customer@example.net` | Yes, a To recipient | Yes, through To |
| `account-manager@example.com` | Yes, a Cc recipient | Yes, through Cc |
| `audit@example.com` | Yes, a Bcc recipient | Normally not exposed in the copy delivered to other recipients |

At the protocol level, SMTP must deliver to the corresponding destination addresses, including addresses marked as Bcc. **The displayed headers and the list of destinations in the SMTP envelope are two different layers.**

## 6. Subject: the message subject

`Subject` lets the recipient know the main content of the email and is usually shown in the message list:

~~~java
mail.setSubject("Order A123 has been confirmed");
~~~

The subject should be specific enough to help recipients distinguish similar emails, but should not contain confidential information. For example:

| Unclear | More meaningful for the business |
| --- | --- |
| `Notification` | `Order A123 has been confirmed` |
| `Update` | `Status of support request #452 has changed` |
| `New report` | `The November revenue report is ready` |
| `Important!!!` | `Please confirm the email address for your account` |

Avoid putting passwords, authentication tokens, secret recovery codes, or sensitive personal data in the Subject. The subject may appear in lock-screen notifications, logs, and email history that other people can see.

### 6.1. Subject is a header, not HTML

If you set:

~~~java
mail.setSubject("<b>Order confirmed</b>");
~~~

then the `<b>` tags are characters of the subject, not instructions for the email client to render bold text. The Subject needs to be an appropriate text string, while HTML formatting (if needed) belongs to the **MIME body**, not the Subject header.

### 6.2. Vietnamese subjects and encoding

~~~java
mail.setSubject("Xác nhận lịch hẹn của bạn");
~~~

In Java, `String` represents Unicode text. When the email is built for sending, the mail library takes care of encoding the header according to the appropriate email rules. With Spring Boot, you should declare the encoding explicitly when sending content with diacritics:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8
~~~

If you open "View original / Show source" of the email, a Unicode subject may be displayed as an `encoded-word`, for example in this structure:

~~~text
Subject: =?UTF-8?B?<encoded-bytes>?=
~~~

The `<encoded-bytes>` part here is only an illustrative placeholder. The email client decodes the header to display Vietnamese. You should not convert the subject string to Base64 yourself before calling `setSubject(...)`; that may cause the message to be encoded twice or show an unwanted encoded string.

### 6.3. Dynamic subjects from business data

~~~java
String orderId = "A123";
mail.setSubject("Order " + orderId + " has been confirmed");
~~~

When `orderId` or the information used to build the subject comes from external input, you need to limit the length, normalize according to business rules, and prevent invalid newline/control characters. Do not concatenate raw header lines from input. Spring/Jakarta Mail's high-level APIs help create correctly formatted headers, but validating input data remains the application's responsibility.

## 7. Complete example with `SimpleMailMessage`

### 7.1. Create a mail with From, To, Cc, Bcc, and Subject

~~~java
package com.example.mail.application;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationMailService {
    private final JavaMailSender mailSender;

    public OrderNotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmed(String customerEmail, String orderId) {
        SimpleMailMessage mail = new SimpleMailMessage();

        mail.setFrom("orders@example.com");
        mail.setTo(customerEmail);
        mail.setCc("account-manager@example.com");
        mail.setBcc("audit@example.com");
        mail.setSubject("Order " + orderId + " has been confirmed");
        mail.setText("""
                Hello,

                Your order %s has been confirmed.
                If you need support, please contact the customer care department.

                Best regards,
                Order Processing Team
                """.formatted(orderId));

        mailSender.send(mail);
    }
}
~~~

This is an example that illustrates the API. In a real system, you should not automatically Cc/Bcc internal addresses on every order unless there are corresponding data sharing and access rules. The From address should also come from configuration; the next section shows how.

### 7.2. Move the From and Cc addresses into configuration

Example `application.yml` in Spring Boot:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    order-from: ${ORDER_MAIL_FROM:orders@example.com}
    order-cc: ${ORDER_MAIL_CC:account-manager@example.com}
~~~

`spring.mail.*` is the group of SMTP settings supported by Spring Boot. `app.mail.*` is a set of properties **named by the application itself**, which must be read with `@Value` or `@ConfigurationProperties`. The SMTP password must be supplied by the runtime environment/secret manager and not stored directly in the repository.

The service snippet:

~~~java
package com.example.mail.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ConfiguredOrderMailService {
    private final JavaMailSender sender;
    private final String fromAddress;
    private final String ccAddress;

    public ConfiguredOrderMailService(
            JavaMailSender sender,
            @Value("${app.mail.order-from}") String fromAddress,
            @Value("${app.mail.order-cc}") String ccAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
        this.ccAddress = ccAddress;
    }

    public void sendConfirmation(String customerEmail, String orderId) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom(fromAddress);
        mail.setTo(customerEmail);
        mail.setCc(ccAddress);
        mail.setSubject("Order confirmation " + orderId);
        mail.setText("Order " + orderId + " has been confirmed.");
        sender.send(mail);
    }
}
~~~

When you change to a sending address that the provider has verified, or replace the copy recipient by department, the operations team can change the configuration without editing Java code. If there is no need for Cc, you should drop that field rather than always declaring an unrelated address.

## 8. One way to choose To, Cc, and Bcc by business case

Consider three situations:

### 8.1. Personal account confirmation email

~~~java
mail.setFrom("no-reply@example.com");
mail.setTo(userEmail);
mail.setSubject("Your account has been created");
// Do not automatically add Cc/Bcc.
~~~

Each user receives a separate message. This is usually the appropriate approach to avoid data exposure and to let the system know which person has been sent to.

### 8.2. Work discussion with someone who needs to follow along

~~~java
mail.setFrom("project@example.com");
mail.setTo("task-owner@example.com");
mail.setCc("teamlead@example.com");
mail.setSubject("Progress update for task A123");
~~~

The primary owner goes in To, and the person who needs to know goes in Cc. Because Cc is visible and can take part in Reply All, choose people who are actually relevant to the content.

### 8.3. Send a blind copy for an approved process

~~~java
mail.setFrom("system@example.com");
mail.setTo("recipient@example.net");
mail.setBcc("archive@example.com");
mail.setSubject("Request confirmation");
~~~

Bcc can serve a legitimate internal need such as keeping a copy in an approved mailbox, but you should not regard that mailbox as the only source of status. If you must audit every send, a log/job table with a business ID and a retention policy is usually more reliable.

## 9. SMTP and header rules: why To/Cc/Bcc are not the whole story

To understand this precisely, you need to distinguish between:

- **Message headers:** `From`, `To`, `Cc`, `Subject` are header contents that the email client uses for display.
- **SMTP envelope recipients:** `RCPT TO` tells the server which mailboxes should receive the message during the SMTP protocol exchange.

Example:

~~~text
SMTP envelope:
  MAIL FROM:<bounce@example.com>
  RCPT TO:<alice@example.net>
  RCPT TO:<manager@example.com>
  RCPT TO:<audit@example.com>

Message headers:
  From: orders@example.com
  To: alice@example.net
  Cc: manager@example.com
  Subject: Order confirmation
~~~

The address `audit@example.com` is a transport destination listed in the SMTP envelope, but it **does not need to appear in the To/Cc headers** of the copy that other people receive. This is why Bcc works.

In Spring, `JavaMailSender` and the Jakarta Mail provider handle converting the recipient data from the message into the appropriate sending operation. The application does not need to assemble `RCPT TO` commands itself when using `SimpleMailMessage`.

### 9.1. To/Cc/Bcc may succeed or fail differently

If an email has multiple recipients, the SMTP provider may accept some addresses and reject others. Depending on the provider and the Jakarta Mail configuration, the sender may throw an exception, a partially successful send may occur, or a failure notice may arrive after the message has been accepted.

Therefore, a call such as:

~~~java
mailSender.send(mail);
~~~

is **not a transaction guaranteeing that all recipients have received the message**. If the business needs to know the status for each customer, manage the send requests per address and track events from the provider when supported.

### 9.2. Reply-To does not replace From

Besides the five fields in this lesson, there is also the `Reply-To` header:

~~~java
mail.setFrom("notification@example.com");
mail.setReplyTo("support@example.com");
~~~

`From` is the sender; `Reply-To` suggests where replies go when the user clicks Reply. It does not change the To/Cc/Bcc addresses and does not replace the envelope sender that handles bounces.

## 10. Validate address data before sending

An internal mail-sending API may receive customer emails from a database or a form. Even though Spring provides simple setters, the application must still control the data:

1. **Addresses must come from a trustworthy source:** for example, the email of a verified account or an approved recipient.
2. **Syntax must be valid:** check/parse with an appropriate tool, but correct syntax does not guarantee the mailbox exists.
3. **Do not allow From to be changed freely:** an endpoint should not accept an arbitrary From string from outside users.
4. **Do not accept uncontrolled Cc/Bcc:** this may lead to information leakage or abuse of the system as a mail relay.
5. **Do not put raw input into headers:** limit the length, remove invalid control characters such as CR/LF, and let the mail library create the headers.
6. **Limit exposure of information in logs:** avoid logging all email recipients, Subject, and body when not necessary.

Example of parsing an address with Jakarta Mail in a Boot 3.x application:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public static String parseSingleMailbox(String value)
        throws AddressException {
    InternetAddress[] parsed = InternetAddress.parse(value, true);
    if (parsed.length != 1) {
        throw new AddressException("Expected exactly one email address");
    }
    parsed[0].validate();
    return parsed[0].getAddress();
}
~~~

This snippet checks some syntax rules and requires exactly **one** address, which is useful when you do not want an input field to turn into a recipient list. It does **not** verify that the domain has an MX record, that the mailbox exists, or that the person entering it has the right to use the address. Depending on requirements, you may also need normalization, domain constraints, email confirmation, or anti-abuse policies.

When building the Subject from business data, you also need to limit characters and avoid putting confidential information in the subject.

## 11. Testing the setting of From, To, Cc, Bcc, and Subject

Because `SimpleMailMessage` is a Java object, the application can check the fields that were set without actually connecting to SMTP.

### 11.1. Check the getters

~~~java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("orders@example.com");
mail.setTo("alice@example.net", "bob@example.net");
mail.setCc("manager@example.com");
mail.setBcc("audit@example.com");
mail.setSubject("Order A123 confirmation");
mail.setText("The order has been recorded.");

String from = mail.getFrom();
String[] to = mail.getTo();
String[] cc = mail.getCc();
String[] bcc = mail.getBcc();
String subject = mail.getSubject();
~~~

The getter results tell you the state of the **Java object**. They do not prove that the mail sender actually sent successfully or that the provider accepted every recipient.

### 11.2. Unit test example with Mockito

If the service injects `JavaMailSender`, you can capture the argument passed to `send`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class OrderNotificationMailServiceTest {

    @Test
    void usesExpectedAddressesAndSubject() {
        JavaMailSender sender = mock(JavaMailSender.class);
        OrderNotificationMailService service =
                new OrderNotificationMailService(sender);

        service.sendOrderConfirmed("customer@example.net", "A123");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals("orders@example.com", sent.getFrom());
        assertArrayEquals(
                new String[]{"customer@example.net"},
                sent.getTo());
        assertArrayEquals(
                new String[]{"account-manager@example.com"},
                sent.getCc());
        assertArrayEquals(
                new String[]{"audit@example.com"},
                sent.getBcc());
        assertEquals("Order A123 has been confirmed", sent.getSubject());
    }
}
~~~

This unit test confirms the configuration of the fields and the call to the sender. It does not verify that Bcc is hidden in the transmitted copy or that the Subject is encoded correctly in SMTP/MIME. Those behaviors need integration tests at the mail transport layer.

### 11.3. SMTP test server and raw message

You can use Mailpit or GreenMail in a local/test environment to receive test mail, and then:

- View the `From`, `To`, `Cc`, `Subject` headers in the message.
- Check the recipients that were sent via SMTP, including Bcc, if the test tool provides envelope data.
- Observe whether the `Bcc` header is removed from the copy delivered to other recipients.
- Confirm that a Vietnamese Subject is displayed and decoded correctly.
- Try an email with multiple To/Cc/Bcc to understand how the provider handles valid and invalid addresses.

When evaluating the privacy of Bcc, you need to look at **the copy delivered to each recipient** or the SMTP server's behavior, not only at the `SimpleMailMessage` object before sending.

## 12. Common mistakes and misunderstandings

| Symptom / misunderstanding | Possible cause | How to handle |
| --- | --- | --- |
| `From` looks valid but SMTP rejects it | The address/domain has not been authorized by the provider | Check the sender identity, SMTP credentials, and sending permissions |
| Sending to multiple To addresses exposes the customer list | One message is used for many unrelated people | Send to each person separately when privacy/personalization is required |
| Recipients see an internal address in Cc | Cc is designed to be visible | Only Cc people who really need to be present in the conversation |
| Thinking Bcc secures the content | Bcc only limits the display of the recipient list | Control access and content at the source |
| Bcc is not visible in the recipient's raw message | That may be normal behavior of the mail transport | Look at the sending data/envelope when verification is needed |
| Vietnamese Subject displays incorrectly | Encoding/header is handled inappropriately | Configure UTF-8 and check the raw message |
| Putting HTML in the Subject and expecting bold | Subject is header text | Use a text subject and format in the MIME body |
| `To` is valid but nothing is in the Inbox | The downstream SMTP/server may reject or return it later | Check the provider result, bounces, and delivery status |
| Cc is added on Reply All | Email clients usually keep people in Cc when replying to all | Consider recipients from the start; do not use Cc as logging |
| Multiple recipients but only some succeed | SMTP may accept/reject each address | Track results per recipient; do not assume all-or-nothing |
| Want to change the bounce address with `setFrom` | Confusing the From header with the SMTP envelope | Configure the reverse-path/bounce at the transport or provider |
| Sharing one `SimpleMailMessage` across multiple threads | The mutable object is overwritten | Create a new message for each send |

### 12.1. Avoid sharing mutable objects

Do not:

~~~java
// One instance shared across many requests can have To/Subject overwritten by each other.
private final SimpleMailMessage shared = new SimpleMailMessage();

public void send(String recipient, String subject) {
    shared.setTo(recipient);
    shared.setSubject(subject);
    sender.send(shared);
}
~~~

Instead:

~~~java
public void send(String recipient, String subject) {
    SimpleMailMessage mail = new SimpleMailMessage();
    mail.setFrom("no-reply@example.com");
    mail.setTo(recipient);
    mail.setSubject(subject);
    mail.setText("Notification content.");
    sender.send(mail);
}
~~~

If you need to reuse common fields, `SimpleMailMessage` also supports a copy constructor: create a stable template object and then produce a **new copy** for each send. Avoid modifying the template object concurrently with copying.

### 12.2. One message with multiple recipients differs from multiple messages

~~~java
// One message; the primary recipients can see each other:
mail.setTo("alice@example.net", "bob@example.net");
sender.send(mail);
~~~

Compared with:

~~~java
SimpleMailMessage alice = new SimpleMailMessage();
alice.setFrom("no-reply@example.com");
alice.setTo("alice@example.net");
alice.setSubject("Notification for Alice");
alice.setText("Hello Alice.");

SimpleMailMessage bob = new SimpleMailMessage();
bob.setFrom("no-reply@example.com");
bob.setTo("bob@example.net");
bob.setSubject("Notification for Bob");
bob.setText("Hello Bob.");

sender.send(alice, bob);
~~~

A call that sends multiple `SimpleMailMessage` objects is an API convenience, **not a transaction** guaranteeing that both messages succeed or fail together. Critical systems must manage the results and retries per request.

## 13. When do you need to switch to `MimeMessageHelper`?

`SimpleMailMessage` directly provides the five fields we are learning and the text content. However, if you need a **display name with a chosen encoding**, HTML content, file attachments, images, or complex headers, use `MimeMessage` with `MimeMessageHelper`.

Equivalent example for an HTML message:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, false, "UTF-8");

helper.setFrom("orders@example.com", "Order Department");
helper.setTo("customer@example.net");
helper.setCc("account-manager@example.com");
helper.setBcc("audit@example.com");
helper.setSubject("Order A123 has been confirmed");
helper.setText(
    "<html><body><h1>Order confirmation</h1></body></html>",
    true
);

mailSender.send(mime);
~~~

`MimeMessageHelper` still has similar operations to set From/To/Cc/Bcc/Subject, but works with Jakarta Mail's MIME message. The example above may raise `MessagingException` or an encoding exception from the related methods; real code needs to declare/handle these according to the API signatures and the application's error handling policy.

For a simple text-only message, there is no need to switch to MIME just because of Cc or Bcc. `SimpleMailMessage` already supports these two fields.

## 14. Combined scenario: choosing the right recipients for a notification

Suppose a business has an application that sends **service booking confirmation notifications**. The people who need to receive it are the customer, the staff member in charge of the file, and an internal archive group.

Desired format:

~~~text
From: bookings@example.com
To: customer@example.net
Cc: account-manager@example.com
Subject: Booking confirmation BK-2048

Hello,

Booking BK-2048 has been confirmed.
Please contact the support department if you need to make changes.
~~~

A blind copy can be sent to `archive@example.com` if there is an approved business requirement; this address does not need to appear in the To/Cc headers that the customer sees.

The application can do the following:

1. **Obtain the recipient** from the service booking information, making sure the address belongs to the right customer.
2. **Choose From** from the configuration of a domain that is allowed to send through the provider.
3. **Choose Cc** for the staff member who truly needs to take part in the discussion; if there is none, do not set it.
4. **Add Bcc only** when there is a clear rule on purpose and access rights.
5. **Build the Subject** containing a non-sensitive booking code, clear to the recipient.
6. **Create a new `SimpleMailMessage`**, set the text content, and send it through `JavaMailSender`.
7. **Record the message submission** and track status separately if you need to verify delivery or handle failures.

The key point of this lesson is not just remembering the names of the setters. When you use `From`, `To`, `Cc`, `Bcc`, and `Subject` correctly, you are describing **the identity of the message, the scope of sharing, and the context of the recipients**. Choosing fields accurately makes the mail-sending module easier to use, reduces unnecessary exposure of addresses, and clarifies the responsibility of each participant in the conversation.

### References

- **Spring Framework API — `SimpleMailMessage`:** `setFrom`, `setTo`, `setCc`, `setBcc`, `setSubject`, `setText`, and the corresponding getters.
- **Spring Framework API — `MailSender` and `JavaMailSender`:** send email objects from an application service.
- **Spring Framework API — `MimeMessageHelper`:** create MIME messages with headers, display names, HTML, and attachments.
- **RFC 5322 — Internet Message Format:** the role of header fields such as `From`, `To`, `Cc`, `Bcc`, and `Subject`.
- **RFC 5321 — Simple Mail Transfer Protocol:** distinguishes the message header from the SMTP envelope and the actual recipients during transport.
