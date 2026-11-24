# Setting From, To, Cc, Bcc, and Reply-To with MimeMessageHelper in Spring Framework Mail

When an application sends email, the body can be just a few lines of text, formatted HTML, or a MIME message containing file attachments. Whatever the content is, the application still needs to determine **who the sender is, who receives the message, who receives copies, and where replies should go**. With Spring Framework Mail, `MimeMessageHelper` provides clear methods for setting that information on a `MimeMessage`.

The commonly used fields include:

- **From**: the sender's address and name that the recipient sees.
- **To**: the primary recipients of the message.
- **Cc** (*carbon copy*): recipients of a public copy.
- **Bcc** (*blind carbon copy*): recipients of a hidden copy.
- **Reply-To**: the address suggested when the recipient chooses to reply.

These five fields have different roles. In particular, **`From` does not by itself decide which SMTP account logs in; `Reply-To` is not the address that receives bounces; `Bcc` must be handled correctly so that recipients are not exposed**. Understanding those boundaries matters just as much as remembering the setter names.

## 1. Where do the addresses sit in an email?

An email has two layers of information: the **message headers**, which live inside the message itself, and the **SMTP envelope**, which serves to transport the message to the destination mailboxes.

An illustrative example of message headers:

```text
From: "Cửa hàng Example" <orders@example.com>
To: "Khách hàng" <customer@example.net>
Cc: "Chăm sóc khách hàng" <support@example.com>
Reply-To: "Bộ phận hỗ trợ" <helpdesk@example.com>
Subject: Xác nhận đơn hàng
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Đơn hàng của bạn đã được tiếp nhận.
```

The body is below the first blank line. In an email actually sent, a header with a Vietnamese name will be encoded according to the MIME standard when necessary; the example above shows the human-readable meaning and does not aim to exactly simulate the bytes transmitted over SMTP.

The same message can be sent through the SMTP envelope as follows:

```text
MAIL FROM:<bounces@mailer.example.com>
RCPT TO:<customer@example.net>
RCPT TO:<support@example.com>
RCPT TO:<audit@example.com>
```

Here `audit@example.com` can be a Bcc recipient. A recipient in the SMTP envelope does not necessarily appear in the `To` or `Cc` of the message content. The address in `MAIL FROM` can belong to the bounce-handling system and differ from the displayed `From` address.

A table of distinctions:

| Information | Layer | Purpose |
| --- | --- | --- |
| `From` | Email header | The identity of the author/sender presented to the recipient |
| `To` | Email header | The list of primary recipients, usually shown publicly |
| `Cc` | Email header | The list of copy recipients, usually shown publicly |
| `Bcc` | Hidden recipient; handled according to MIME/SMTP | Delivers the message to hidden recipients without revealing them to others |
| `Reply-To` | Email header | The address suggested for the Reply action |
| `MAIL FROM` | SMTP envelope | The reverse-path address for handling undeliverable-message notifications |
| `RCPT TO` | SMTP envelope | The destination address to which the SMTP server receives the delivery command |
| `Return-Path` | Header usually added by the final delivery system | Records the reverse-path at the delivery hop; does not replace the `MAIL FROM` command |

`MimeMessageHelper` helps set the **message headers and recipient fields** on the `MimeMessage`. Spring/Jakarta Mail and the SMTP provider handle transporting the message over SMTP. You should not assume that `setFrom(...)` or `setReplyTo(...)` has finished configuring the SMTP envelope or the bounce policy.

## 2. Preparing JavaMailSender and MimeMessageHelper

In Spring Boot with Maven, the common dependency is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

With Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
```

Spring Boot usually auto-configures `JavaMailSender` when the dependency and the mail configuration meet the corresponding conditions. An example `application.properties`:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

The host, port, and TLS mode are examples; the actual configuration must follow the SMTP provider. The username/password should be taken from environment variables or a secret manager, avoiding committing credentials to the repository.

In the service, we create a new message with the sender and use the helper to set the fields:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Notification");
helper.setText("Your request has been received.", false);

mailSender.send(message);
```

The example uses the imports of Spring Framework 6+/Spring Boot 3+ with `jakarta.mail.*`. In an application using an older generation, the JavaMail package may be `javax.mail.*`; do not mix the two generations in one module.

Here:

- `mailSender.createMimeMessage()` creates a new message.
- `new MimeMessageHelper(message, "UTF-8")` allows setting headers/addresses and formatting the charset.
- `setText(text, false)` defines the plain-text body; for HTML you can use `setText(html, true)`.
- `mailSender.send(message)` performs the SMTP submission.

**Setting From/To/Cc/Bcc/Reply-To does not require a particular multipart mode.** Only enable multipart when the content needs an alternate body, inline images, attachments, or a similar MIME structure.

## 3. Setting From: the displayed sender

`From` is the header that shows the author/sender of the message in many email clients. `MimeMessageHelper` has these commonly used setter forms:

```java
helper.setFrom("orders@example.com");
```

When you want to show a recognizable name:

```java
helper.setFrom("orders@example.com", "Cửa hàng Example");
```

The email client may display:

```text
Cửa hàng Example <orders@example.com>
```

The display name helps the recipient understand the source of the email, but it **does not replace the email address**, does not verify the right to send for the domain, and does not guarantee that the receiving mailbox will judge the message trustworthy.

### Why use the overload with a display name?

Do not concatenate the name and address yourself with an arbitrary string from the user:

```java
// Do not build a raw header yourself when the name contains untrusted data.
String from = displayName + " <orders@example.com>";
helper.setFrom(from);
```

A name can contain Vietnamese diacritics, quotes, commas, or characters that have syntactic meaning in a header. Use the `setFrom(address, personalName)` overload so that the library encodes and represents the name according to the email address rules:

```java
helper.setFrom("orders@example.com", "Dịch vụ Đặt hàng");
```

The overload that takes a display name may additionally declare `UnsupportedEncodingException` alongside the Jakarta Mail error. You can declare it in the method signature:

```java
import jakarta.mail.MessagingException;
import java.io.UnsupportedEncodingException;

public void sendMail() throws MessagingException, UnsupportedEncodingException {
    // ...
}
```

With the widely supported `UTF-8` charset, encoding errors are rare, but the exception signature must still comply with the API in use.

### From different from the SMTP account

For example:

```properties
spring.mail.username=mailer-account@example.net
```

but the message has:

```java
helper.setFrom("orders@shop.example.com", "Shop Example");
```

This can be valid if the SMTP account is allowed to send on behalf of `orders@shop.example.com` or the domain `shop.example.com` has been verified. If it does not have permission, the ESP may reject it, replace the `From`, or cause the SPF/DKIM/DMARC authentication process to fail the receiving side's policy.

Setting `From` with the helper only determines the message's header; the right to use the sending address must be configured with the SMTP provider.

## 4. Setting To: the primary recipients

`To` is the list of primary recipients of the email. With one recipient:

```java
helper.setTo("customer@example.net");
```

With multiple recipients:

```java
helper.setTo(
    "customer@example.net",
    "account-manager@example.net"
);
```

When you already have an array of addresses:

```java
String[] recipients = {
    "customer@example.net",
    "account-manager@example.net"
};

helper.setTo(recipients);
```

The `MimeMessageHelper` overloads also support Jakarta Mail's `InternetAddress` when the application already has an address object that was parsed/checked:

```java
import jakarta.mail.internet.InternetAddress;

InternetAddress recipient =
        new InternetAddress("customer@example.net", "Customer", "UTF-8");

helper.setTo(recipient);
```

`InternetAddress` allows representing an email address together with a personal name. However, successfully creating an address object does not prove that the mailbox exists or that the domain allows receiving mail.

### `setTo` and `addTo` are different

The method name expresses its purpose:

- `setTo(...)` **sets the To list**; if called again, the previous To value is replaced by the new value.
- `addTo(...)` **adds one To address** to the existing list.

For example:

```java
helper.setTo("alice@example.net");
helper.addTo("bob@example.net");
```

The result in terms of meaning:

```text
To: alice@example.net, bob@example.net
```

Conversely:

```java
helper.setTo("alice@example.net");
helper.setTo("bob@example.net");
```

The final To usually has only `bob@example.net` because the later `setTo` replaces the previous list.

This is especially important when a helper is passed through multiple methods: if the first class that builds the email sets To, but another class keeps calling `setTo` to “supplement” it, the earlier recipients may be lost. Choose clearly between **setting the whole list** and **adding one element**.

### Adding a To with a display name

If you need to store the recipient's name in the header:

```java
helper.setTo("customer@example.net");
helper.addTo("manager@example.net", "Account manager");
```

Some overloads accept a personal name and may raise `UnsupportedEncodingException`. For Unicode names, use the UTF-8 charset when creating the helper. Do not put the display name into the SMTP address by concatenating strings yourself when it is not necessary.

### Do not use To to express access rights

The To list is only delivery information. Having someone in To does not grant access to data behind a URL, an attached file, or the business system. If the email contains a link to view an order, the target backend still needs to authenticate and check the permissions of the person accessing it.

## 5. Setting Cc: a public copy

`Cc` (carbon copy) is usually used to additionally notify people who are involved. The recipients in To and Cc can usually see the Cc list in the header section that the email client displays.

For example:

```java
helper.setTo("customer@example.net");
helper.setCc("account-manager@example.com");
```

If there are multiple Cc recipients:

```java
helper.setCc(
    "account-manager@example.com",
    "support-lead@example.com"
);
```

Or add after the initial list has been set:

```java
helper.setCc("support@example.com");
helper.addCc("teamlead@example.com");
```

Like To, `setCc(...)` resets the Cc list, while `addCc(...)` adds a recipient to the current list.

### When should you use Cc?

Cc is appropriate when:

- A primary recipient is responsible for replying, but another person needs to be aware.
- An internal discussion email needs a manager to receive a copy.
- A support process has a main owner and a person who needs to follow progress.

Cc is **not appropriate** when the recipients must not know each other's addresses, for example private notices to multiple independent customers. In that case, send separate emails or use a bulk-sending mechanism with recipient isolation.

One design mistake is putting hundreds of customer addresses into Cc just for configuration convenience. The impact can be exposing the email list, creating unintended reply-all, and causing privacy problems.

## 6. Setting Bcc: a hidden copy

`Bcc` (blind carbon copy) adds recipients whose information is **not disclosed in the copy delivered to the other recipients**. For example:

```java
helper.setTo("customer@example.net");
helper.setBcc("audit@example.com");
```

Or:

```java
helper.setBcc(
    "audit@example.com",
    "archive@example.com"
);
```

Adding one Bcc address:

```java
helper.addBcc("compliance@example.com");
```

**Bcc is a feature for managing a hidden recipient list, not a kind of content encryption.** Bcc recipients still receive the email content; SMTP/gateway administration systems can observe recipients at the transport layer or in logs, and a forwarded/reply-all message can cause additional unintended risks.

### How does Bcc work?

A conceptual diagram:

```text
Application creates the message:
    To: customer@example.net
    Cc: manager@example.com
    Bcc: audit@example.com
              |
              v
Jakarta Mail / SMTP transport:
    RCPT TO:<customer@example.net>
    RCPT TO:<manager@example.com>
    RCPT TO:<audit@example.com>
              |
              v
Copy of the message delivered to ordinary recipients:
    To: customer@example.net
    Cc: manager@example.com
    (Bcc: audit@example.com not disclosed)
```

Jakarta Mail/SMTP transport and the relays involved handle the recipient list. When checking Bcc, you need to distinguish the **`MimeMessage` object that is still inside the application** from the **final email at the recipient's mailbox**. A local object can still contain Bcc information because the library needs to know where to send; you should not log/display that raw message externally.

If you build raw MIME/SMTP yourself or use a special gateway, you must confirm that the pipeline's Bcc mechanism still removes or properly handles the hidden-recipient information. Absolutely avoid copying the Bcc list into `To`, `Cc`, the body, or a custom header.

### Is Bcc suitable for bulk sending?

For simple notifications sent to a small group with shared content, Bcc can be useful. However, **Bcc does not by itself turn an email into a safe bulk mail system**.

The limitations:

- Providers usually have recipients-per-message limits and rate limits.
- All recipients receive nearly the same body, with no individual personalization.
- Tracking delivery/bounces per recipient may be harder depending on the ESP.
- If the content has a verification code, a private link, or personal data, sending it jointly via Bcc is not appropriate.
- Some email clients or mail gateways handle the Bcc header and sending traces differently.

For personalized transactional email, you should create **one delivery per recipient** or use a bulk-sending API that supports recipient isolation and per-recipient metadata.

## 7. Setting Reply-To: where will replies go?

`Reply-To` specifies one or more mailboxes that the mail-reading program can use when the recipient chooses **Reply**. With `MimeMessageHelper`, the common case:

```java
helper.setFrom("no-reply@example.com");
helper.setReplyTo("support@example.com");
```

The recipient sees the sender as `no-reply@example.com`, but when choosing reply, the email client usually proposes `support@example.com` as the destination address.

If you need a display name:

```java
helper.setReplyTo("support@example.com", "Support team");
```

The method with a personal name allows the library to represent the name per the email header standard and may additionally declare an encoding exception.

### When is Reply-To useful?

- Sending notifications from an automated address but wanting to receive replies in a support mailbox.
- Sending invoices from `billing@example.com` but the recipient should contact `accounts@example.com`.
- Sending mail from a multi-tenant platform where each tenant has its own support mailbox.
- Sending campaigns from a release address but collecting replies to the corresponding handling team.

For example:

```java
helper.setFrom("notifications@example.com", "Example Platform");
helper.setReplyTo("helpdesk@example.com", "Support team");
helper.setTo("customer@example.net");
```

The expected experience:

```text
From: Example Platform <notifications@example.com>
To: customer@example.net
Reply-To: Support team <helpdesk@example.com>
```

### Reply-To is not Return-Path

It is very easy to confuse these two concepts:

- `Reply-To`: receives replies **created by users** in the email client.
- `Return-Path`/SMTP `MAIL FROM`: takes part in handling **bounces or undeliverable notifications** per SMTP.

If you want bounces to go to a separate address, you need to look at the **envelope sender** mechanism and the provider's policy. Only setting:

```java
helper.setReplyTo("bounces@example.com");
```

does not mean SMTP will use `MAIL FROM:<bounces@example.com>`, and it also does not guarantee that bounces are sent there.

### Reply-To does not have to be the same as From

Some providers have a policy of checking the relationship between the sender and the reply address to prevent abuse/phishing, but in protocol terms the two fields can differ. When setting Reply-To to a different domain, you need to ensure that the address is truly managed by the organization and does not cause confusion or make the message be judged suspicious.

Do not use a Reply-To address entered arbitrarily by the user if the application could be exploited to send email that looks like it comes from the organization but leads replies to someone else. For a contact-form kind of case, you can set `From` to the application's verified sender and `Reply-To` to the user's address **after verification/with an appropriate policy**, instead of forging the user's `From`.

## 8. A complete Spring Service example

Suppose the system sends an order-completion confirmation email. The buyer is To, the support department receives Cc, the archive mailbox receives Bcc, and all replies should go to the helpdesk.

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.UnsupportedEncodingException;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationMailService {

    private final JavaMailSender mailSender;

    public OrderNotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderCompleted(
            String customerEmail,
            String orderCode)
            throws MessagingException, UnsupportedEncodingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message, StandardCharsets.UTF_8.name());

        // The displayed sender.
        helper.setFrom("orders@example.com", "Example Store");

        // The primary recipient.
        helper.setTo(customerEmail);

        // The public copy recipient.
        helper.setCc("support@example.com");

        // The hidden copy recipient.
        helper.setBcc("archive@example.com");

        // The mailbox that receives replies when the customer chooses Reply.
        helper.setReplyTo("helpdesk@example.com", "Support team");

        helper.setSubject("Your order has been completed");

        String body = """
                Hello,

                Your order has been completed.

                Order code: %s

                If you need support, please reply to this email.

                Thank you!
                """.formatted(orderCode);

        helper.setText(body, false);
        mailSender.send(message);
    }
}
```

The structure equivalent in meaning:

```text
From: Example Store <orders@example.com>
To: <customerEmail>
Cc: support@example.com
Reply-To: Support team <helpdesk@example.com>
Subject: Your order has been completed

Body: text announcing the order completion

Recipient hidden during delivery: archive@example.com
```

**Do not put Bcc into the body string or the To header to “remember” the archiver.** When you want to keep a business trace, use a notification ID and a database/log with controlled access.

This example uses plain text. If the business wants to send both HTML and a fallback text version, you can replace the helper/body-creation part with multipart mode without changing the meaning of From/To/Cc/Bcc/Reply-To.

## 9. Replacing plain text with HTML still uses the same address setters

`MimeMessageHelper` manages both the address part and the building of the MIME body. The two groups of functions can be combined independently.

An example of sending HTML and plain text:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
    message,
    true,
    "UTF-8"
);

helper.setFrom("notifications@example.com", "Example Service");
helper.setTo("customer@example.net");
helper.setCc("account-manager@example.com");
helper.setReplyTo("support@example.com");

helper.setSubject("Account update");

String plainText = """
    Your profile has been updated.

    View details: https://example.com/account
    """;

String htmlText = """
    <html lang="en">
      <body>
        <h1>Profile updated</h1>
        <p>View details at
          <a href="https://example.com/account">your account</a>.
        </p>
      </body>
    </html>
    """;

helper.setText(plainText, htmlText);
mailSender.send(message);
```

In this case, the constructor with `multipart=true` makes it possible to use `setText(plainText, htmlText)`, creating two versions of the content in one email. The address setters are still `setFrom`, `setTo`, `setCc`, and `setReplyTo`, just as when sending text.

If you want to add a PDF, choose an appropriate MIME multipart mode and then use `helper.addAttachment(...)`. Do not interpret Cc/Bcc as a “part” of the body: they belong to the recipient information and are unrelated to `multipart/alternative` or `multipart/mixed`.

## 10. Use set or add for To, Cc, and Bcc?

When you have a recipient list from several sources (the customer, the manager, the archive system), you should distinguish **setting the whole list** from **adding individual addresses**.

| Group | Set the list | Add one address | Note |
| --- | --- | --- | --- |
| To | `setTo(...)` | `addTo(...)` | Usually at least one business recipient |
| Cc | `setCc(...)` | `addCc(...)` | Public to the recipients |
| Bcc | `setBcc(...)` | `addBcc(...)` | Do not put into To/Cc or the body |
| From | `setFrom(...)` | Not handled like the To list | Usually a single clearly representative mailbox |
| Reply-To | `setReplyTo(...)` | Not treated as adding a recipient | The address used for replying |

An example of combining two departments receiving the notification:

```java
helper.setTo("owner@example.net");
helper.addTo("delegate@example.net");

helper.setCc("support@example.com");
helper.addCc("supervisor@example.com");

helper.setBcc("archive@example.com");
helper.addBcc("audit@example.com");
```

An erroneous example:

```java
helper.setTo("owner@example.net");
helper.setTo("delegate@example.net"); // Overwrites the previous To list.
```

If you already have a full array of recipients, you should call `setTo(recipients)` **once**, or if you need to build up the recipients one by one, use `addTo`. Do not let two service layers arbitrarily overwrite To without an ownership rule.

### Sending multiple emails is not the same as adding multiple To addresses

```java
helper.setTo("alice@example.net", "bob@example.net");
```

sets two recipients for the **same message**. Conversely, when you need two emails with separately personalized content:

```text
Email A:
  To: alice@example.net
  Body: Hello Alice, your verification code is...

Email B:
  To: bob@example.net
  Body: Hello Bob, your verification code is...
```

you must create **two separate `MimeMessage` objects** or use the provider's personalized bulk-send mechanism. Do not create one shared message with two To addresses and Alice's OTP code, because Bob would see data that does not belong to him.

## 11. Checking addresses: correct syntax does not mean deliverable

`MimeMessageHelper` has the `setValidateAddresses(true)` option to require validating the addresses set through the helper using Jakarta Mail's `InternetAddress.validate()` mechanism:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

// Enable address syntax checking when using the setters.
helper.setValidateAddresses(true);

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setReplyTo("support@example.com");
```

Enabling this option can help detect some syntactically wrong addresses early when creating the message. However, **it does not check DNS/MX, does not query whether the mailbox exists, does not prove the user owns the address, and does not guarantee the message will be accepted by the SMTP server**.

### Different layers of checking

| Check | Who performs it | The question it answers |
| --- | --- | --- |
| Basic syntax | `InternetAddress`/helper, the application's validation layer | Does the string have a suitable mail address form? |
| Business rules | Service/application | Is this domain or recipient allowed to receive this kind of mail? |
| DNS/SMTP policy | Sending system/provider | Can the message be transferred to the domain/recipient? |
| Delivery | SMTP relay/MX on the receiving side | Does the receiving server accept the message? |
| Ownership verification | The application's token-confirmation flow | Does the user control this mailbox? |

For a registration form, you need to check the input address, but the decision “the user owns the email” must rely on a verification flow with a token, an expiry, and a confirmation action controlled by the backend.

### Avoid header injection and abnormal values

Fields such as `From`, `To`, `Reply-To` are structured data. You should not build raw headers by concatenating strings from the request:

```java
// Do not take an untrusted string as-is to build a header manually.
String unsafeHeader =
    "To: " + userInput + "\r\nSubject: " + subject;
```

If the data contains CR/LF and another header-name part, concatenating it yourself risks header injection or a syntax error. Use the setters designed for addresses; at the same time, at the application layer you should reject unnecessary control characters, set limits on length and number of recipients, and control the permitted domains/addresses per use case.

You should not rely absolutely on a simple regex to “validate every valid email”: the email address standard has many special cases; accepting an address by syntax is also different from the provider being able to deliver successfully. You can use `InternetAddress` and per-use-case validation, adding an ownership-verification step when the business requires it.

## 12. Vietnamese, display names, and internationalized addresses

An email can contain three kinds of data that are easily confused about encoding:

1. **Body content**: Vietnamese in plain text or HTML.
2. **Display name**: “Bộ phận hỗ trợ”, “Nguyễn Văn An” sitting in the name part of `From`/`To`/`Reply-To`.
3. **Email address**: the local part and domain in `user@example.com`.

For the body and display name, using `UTF-8` is a common choice:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("support@example.com", "Trung tâm hỗ trợ");
helper.setTo("customer@example.net");
helper.setReplyTo("helpdesk@example.com", "Nhóm chăm sóc khách hàng");
helper.setSubject("Xác nhận yêu cầu");
helper.setText("Chúng tôi đã tiếp nhận yêu cầu của bạn.", false);
```

Jakarta Mail will handle encoding the headers when needed. Do not use a string like `=?UTF-8?...?=` yourself and concatenate it into `setFrom` unless you clearly understand the library's encoding API; double or non-standard encoding can create a broken display name.

### International domains and SMTPUTF8 addresses

An address with a domain that uses non-ASCII characters may need the domain represented as **IDNA/Punycode** in specific email-transport contexts. For example, Java has `java.net.IDN` for the domain part. But the **non-ASCII local part** (before the @ sign) has its own SMTPUTF8 requirements and support in relay systems; it cannot be “fixed” by encoding each display name.

Therefore, if the application is expected to support internationalized email addresses, you need to check the capabilities of Jakarta Mail, the SMTP provider, and the destination system with respect to `SMTPUTF8`, along with the authentication/validation policy. A helper using `UTF-8` for the personal name is **not enough** to ensure that an address with a Unicode local part will be delivered.

## 13. From, Reply-To, Sender, and Return-Path in provider policy

When debugging mail sending, the five displayed/recipient addresses are not the whole story.

Suppose:

```text
SMTP account:   smtp-transactional@mailer.example.net
MAIL FROM:      bounce@mailer.example.net

Message:
From:          "Shop Example" <orders@shop.example.com>
To:            customer@example.net
Reply-To:      support@shop.example.com
```

In this situation:

- The SMTP account provides the right to connect and send through the relay.
- `MAIL FROM` serves the SMTP reverse-path/bounce.
- `From` represents the nominal sender at the header layer.
- `Reply-To` routes the recipient's manual replies.
- `To` sits in the header, while `RCPT TO` determines the transport recipients.

Authentication and anti-spoofing mechanisms (such as SPF, DKIM, DMARC) use identities at different layers. `DMARC` is closely tied to the domain of `From` and the alignment of SPF/DKIM. Therefore it can happen that the SMTP login succeeds but the message is not judged valid with respect to the `From` that the application set.

`Sender` is also a header different from `From`, used in situations where an agent that actually transmits/sends on behalf of the message's author, per the email format semantics. In most transactional emails with one clear sender, you only need to set a suitable `From` and let the provider handle the other headers per policy. If the business needs a separate `Sender`, you must understand the RFC rules and the ESP policy rather than arbitrarily adding it through `setHeader`.

Do not assign a raw `Return-Path` yourself to change the bounce address. Some Jakarta Mail SMTP transport configurations use the `mail.smtp.from` property to set the envelope sender, but the ESP may require its own bounce domain or rewrite `MAIL FROM`. Configuring the envelope sender is the job of the SMTP/provider layer, different from the call `MimeMessageHelper#setFrom(...)`.

## 14. Controlling privacy when sending to multiple people

To, Cc, and Bcc are easily regarded as simple recipient classification types, but a wrong choice can expose data:

- **To/Cc**: multiple addresses may be displayed to each other; sharing an email must have a business basis.
- **Bcc**: hides hidden recipients from the headers issued to the other recipients; you still need to protect the data from logs and administration systems.
- **One email per person**: appropriate when the content, links, tracking tokens, access rights, or personal data differ.
- **Large email lists**: need management of suppression, recipient/rate limits, unsubscribe, and bounces per mail-type policy; the setters do not provide those functions by themselves.

An example that is wrong for privacy:

```java
// An account-verification email must not use one shared token
// for multiple different recipients.
helper.setTo("alice@example.net", "bob@example.net");
helper.setText("Alice's verification code: 123456", false);
```

A better design:

```text
delivery #1: To alice@example.net, Alice's own token
delivery #2: To bob@example.net, Bob's own token
```

In each delivery, the application service creates a new message, attaches its own correlation ID, and stores the sending status. When there is an ESP webhook, the delivered/bounced result can differ between recipients, even though they were initially in one message.

### Bcc should not be used as the default archive system

Some applications put `audit@example.com` in Bcc to keep a copy of all emails. This approach can be appropriate under a restricted policy, but you need to weigh capacity, personal data, archive access rights, retention regulations, and the risk of accidentally containing an OTP or sensitive content. When you only need the sending history, storing **delivery metadata** in a database is usually better controlled than sending copies of sensitive content to another mailbox.

## 15. Handling many concurrent requests

`JavaMailSender` is usually used as a singleton bean in Spring. That lets services share the SMTP configuration. But `MimeMessage` and `MimeMessageHelper` are **mutable objects holding the state of a single send**; you should not create one instance and then modify To/Bcc/Reply-To across multiple concurrent requests.

**Do not:**

```java
@Service
public class UnsafeMailer {
    private final JavaMailSender sender;
    private final MimeMessage sharedMessage;

    public UnsafeMailer(JavaMailSender sender) {
        this.sender = sender;
        this.sharedMessage = sender.createMimeMessage();
    }

    public void send(String recipient) throws Exception {
        MimeMessageHelper helper =
            new MimeMessageHelper(sharedMessage, "UTF-8");
        helper.setTo(recipient);
        helper.setFrom("no-reply@example.com");
        helper.setText("Content");

        sender.send(sharedMessage);
    }
}
```

If request A sets `To: alice@example.net` and then request B replaces it with `bob@example.net` before A finishes sending, a wrong send can occur. Bcc information and the body can also be mixed up.

**Do:** create a new `MimeMessage` and helper in each method that handles one delivery:

```java
public void send(String recipient) throws Exception {
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setText("Content");

    sender.send(message);
}
```

A stably configured sender can be used by multiple services. Do not change the host, username, password, or properties of `JavaMailSenderImpl` per request while running in parallel. If a multi-tenant application has several SMTP accounts, create a separate sender profile/bean or a per-tenant transport management mechanism instead of modifying a shared singleton.

## 16. Testing addresses without sending real SMTP

The logic that sets From, To, Cc, Bcc, and Reply-To can be tested at the MIME-object level, with no network needed. Below is an example of testing a **local message** with Jakarta Mail and `MimeMessageHelper`:

```java
package example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;

class AddressHeaderTest {

    @Test
    void setsRecipientsAndReplyTo() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);

        MimeMessageHelper helper =
                new MimeMessageHelper(message, "UTF-8");

        helper.setFrom("orders@example.com", "Cửa hàng Example");
        helper.setTo("customer@example.net");
        helper.setCc("support@example.com");
        helper.setBcc("archive@example.com");
        helper.setReplyTo("helpdesk@example.com");

        // Do not call send(): only observe the local message.
        InternetAddress from =
                (InternetAddress) message.getFrom()[0];
        InternetAddress to =
                (InternetAddress) message.getRecipients(
                        Message.RecipientType.TO)[0];
        InternetAddress cc =
                (InternetAddress) message.getRecipients(
                        Message.RecipientType.CC)[0];
        InternetAddress bcc =
                (InternetAddress) message.getRecipients(
                        Message.RecipientType.BCC)[0];
        InternetAddress replyTo =
                (InternetAddress) message.getReplyTo()[0];

        assertEquals("orders@example.com", from.getAddress());
        assertEquals("Cửa hàng Example", from.getPersonal());
        assertEquals("customer@example.net", to.getAddress());
        assertEquals("support@example.com", cc.getAddress());
        assertEquals("archive@example.com", bcc.getAddress());
        assertEquals("helpdesk@example.com", replyTo.getAddress());
    }
}
```

This local test verifies the fields set on the `MimeMessage`. It **does not prove that Bcc will be hidden in every gateway**, does not check the real SMTP envelope, and does not confirm that the recipient addresses exist. Those requirements need integration tests with an SMTP test server and/or checking the message after it passes through the ESP.

A production service can be unit-tested with a mock/fake `JavaMailSender` and a separate method that builds the message. When checking a Vietnamese display name, you should look at the decoded value through `InternetAddress#getPersonal()` rather than directly comparing the raw bytes of the MIME-encoded header.

### Some cases to include in the test scenarios

- Only one To recipient.
- Multiple To and Cc using `set...` or `add...`.
- Bcc appears in the local message for sending, but is not exposed in the raw email on the receiving side.
- Reply-To differs from From and is the desired address.
- A display name containing Vietnamese, a comma, or characters that need encoding.
- An invalid address blocked by business validation.
- Two concurrent sends do not mix To/Body.
- Changing providers does not lose the designed To/Cc/Bcc/Reply-To behavior.

## 17. Common errors and misunderstandings

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Recipients reply to the `no-reply` address | `Reply-To` not set or set wrongly | Use `helper.setReplyTo(...)` and check the email on the receiving side |
| The earlier To is lost after supplementing recipients | `setTo` was called a second time | Use `addTo` or set a To array once |
| Bcc is accidentally exposed to recipients | Bcc inserted into To/Cc/body yourself, raw message logged, or a gateway handles it wrongly | Use the dedicated API, check the delivery pipeline and logs |
| Cannot send even though From looks valid | The From domain/address has not been verified by the ESP | Check the sender policy, SMTP permissions, and SPF/DKIM/DMARC |
| Vietnamese display name has broken diacritics | Inconsistent header encoding | Use the helper with UTF-8, the overload with a personal name |
| Message rejected because of the recipient address | Wrong syntax, domain does not accept mail, mailbox does not exist, or server policy | Validate input, look at the SMTP reply and ESP events |
| `setValidateAddresses(true)` is enabled but the mail still bounces | Syntax checking does not verify the mailbox | Distinguish syntax validation from delivery verification |
| Wanting bounces to go to Reply-To but not receiving them | Confusing Reply-To with the envelope `MAIL FROM` | Configure the provider's bounce domain/envelope sender |
| Several customers see each other's email | Putting everyone in To/Cc | Send to each person separately or use a safe bulk API |
| Some recipients receive it, some do not | Each recipient has a different SMTP/delivery result | Track results per recipient, avoid marking the whole batch successful |
| Email sent to the wrong person under concurrency | Reusing a mutable `MimeMessage` or helper | Create new ones for each delivery |
| `setReplyTo` does not change the From header | The two fields have different functions | Set each field for its purpose |
| Only setting From but thinking the SMTP account was chosen | Confusing the header with SMTP authentication | Configure a separate `JavaMailSender`/ESP |
| SMTP accepted but the email does not reach the inbox | Spam filtering, delayed bounce, receiving restrictions, or other policy | Track webhooks and authenticate the domain; do not infer from `send()` |

### Exceptions when creating or sending

The setters on the helper can throw `MessagingException` when operating on the `MimeMessage`, and overloads with a personal name can throw `UnsupportedEncodingException`. When sending, Spring can throw `MailException`, for example `MailSendException` or an authentication error from the SMTP layer.

You should not handle every error by retrying immediately. Invalid addresses, an unauthorized sender, or wrong authentication configuration usually need data/configuration fixes. A timeout after the client has finished transmitting the content but has not received `250` can be an **uncertain result**; retrying without reconciliation can cause duplicate sends.

## 18. Choosing recipients by business policy

Suppose the support system has three kinds of email:

**A. Notifying the customer about a new ticket**

```text
From: Support Team <support@example.com>
To: customer@example.net
Reply-To: helpdesk@example.com
Cc: (not needed)
Bcc: (not needed)
```

Use when the recipient needs to reply directly to the helpdesk, with no reason to publicly reveal other people's addresses.

**B. Ticket update for an internal group**

```text
From: Workflow Bot <workflow@example.com>
To: owner@example.com
Cc: manager@example.com
Reply-To: team-inbox@example.com
Bcc: (only if there is an appropriate retention policy)
```

Cc lets the manager know the same message. The recipients are public according to internal collaboration rules.

**C. Sending personal notices to multiple customers**

```text
Email 1:
  To: customer-a@example.net
  Body: A's own request code

Email 2:
  To: customer-b@example.net
  Body: B's own request code
```

Do not use one shared `MimeMessage` for two people with different data. Separating the deliveries also helps track bounces/retries and audit each recipient more precisely.

A good rule for an email-sending system is that the **business layer decides the To/Cc/Bcc/Reply-To lists**, while the infrastructure layer uses `MimeMessageHelper` to turn that decision into a correctly structured message. That way, the rules about who receives and who gets replies are not scattered across many pieces of MIME-building code.

## 19. Things to remember when using MimeMessageHelper

The core operations:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("no-reply@example.com", "Example System");
helper.setTo("customer@example.net");
helper.addTo("delegate@example.net");

helper.setCc("support@example.com");
helper.addCc("manager@example.com");

helper.setBcc("archive@example.com");

helper.setReplyTo("helpdesk@example.com", "Support team");
helper.setSubject("Notification");
helper.setText("Message content.", false);

mailSender.send(message);
```

When developing a mail feature, you need to answer clearly:

1. **From**: who should the recipient recognize as the sender, and has the sender domain been allowed by the provider?
2. **To**: who are the primary recipients, and are they allowed to see each other?
3. **Cc**: who needs to know the information publicly?
4. **Bcc**: is a hidden copy really needed, and is there an appropriate privacy/retention policy?
5. **Reply-To**: which mailbox should the user's replies go to?
6. **SMTP envelope**: where are bounces and routing configured, and are they being confused with the displayed headers?
7. **Validation and concurrency**: are the addresses checked appropriately, and is the message created separately for each send?

In Spring Framework Mail, `MimeMessageHelper` helps create the address headers properly and combine them with plain-text, HTML, or complex MIME content. Its value lies in **expressing clearly the role of each address**, so that mail is sent to the right people, replies reach the right place, and the privacy of the recipients is upheld throughout the entire email-sending process.
