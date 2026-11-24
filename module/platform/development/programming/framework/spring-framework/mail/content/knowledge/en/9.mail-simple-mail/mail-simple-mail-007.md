# One Message for Multiple Recipient Addresses

## 1. How can one email be sent to many people?

In **Spring Framework Mail**, a **SimpleMailMessage** object can hold **multiple recipient addresses**. Instead of creating a separate message for each person, the application sets the list of recipients in the **To**, **Cc**, or **Bcc** field, and then calls **MailSender.send(message)** once.

Example:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("notifications@example.com");
message.setTo(
        "an@example.net",
        "binh@example.net",
        "chi@example.net"
);
message.setSubject("System maintenance schedule");
message.setText("The system will undergo maintenance at 22:00 tomorrow.");

mailSender.send(message);
~~~

At the API level, this is **one message object** with **three To addresses**, passed to the sender with **one send() call**. The SMTP system will process the list of recipient addresses to deliver the message. Recipients can receive deliveries of the same message content; it should not be understood that only one mailbox receives the message.

Points to remember:

- **One message**: one subject, one content, one shared group of headers.
- **Multiple recipients**: multiple addresses in To/Cc/Bcc, corresponding to delivery destinations.
- **One send() call**: the application submits a request to send one message through the Spring Mail layer.
- **Does not mean everyone received it successfully**: the SMTP side may reject some recipients, or errors may appear at later hops.

This lesson focuses on **simple mail**, that is, **plain text** messages using **SimpleMailMessage**. If you need HTML, file attachments, or a complex MIME structure, use **JavaMailSender** and **MimeMessageHelper**.

## 2. Related Spring Mail components

| Component | Role |
|---|---|
| **SimpleMailMessage** | An object representing a simple email: sender, recipients, subject, text content, and some related headers. |
| **MailSender** | A Spring interface providing methods to send one or more SimpleMailMessage objects. |
| **JavaMailSender** | An interface that extends MailSender and also supports MimeMessage messages. |
| **JavaMailSenderImpl** | A common implementation that uses Jakarta Mail to send messages over SMTP. |
| **To** | The primary recipients; the list is usually visible to the other recipients. |
| **Cc** | Public carbon copy recipients; addresses are usually also displayed. |
| **Bcc** | Hidden carbon copy recipients; the addresses are still used for delivery but are usually not disclosed in the headers of the message delivered to others. |

A typical flow:

~~~text
       Controller / Scheduled Job / Business Service
                           |
                           v
                     EmailService
                           |
                           v
                  SimpleMailMessage
                   /      |       \
              To: A,B   Cc: C    Bcc: D
                   \      |       /
                    \     |      /
                           v
                MailSender.send(message)
                           |
                           v
                  JavaMailSenderImpl
                           |
                           v
                Jakarta Mail / SMTP
                           |
                           v
                 SMTP server / relay
                           |
                           v
               Receiving mail systems
~~~

**Spring Mail abstracts the submission of mail from the application**, while the delivery to each mailbox depends on the SMTP relay, the destination mail servers, and the policies of the parties involved.

## 3. The setTo(String...) API accepts one or more addresses

**SimpleMailMessage** provides setter methods to set recipients. For the To list, you can pass one address or several addresses:

~~~java
// One primary recipient.
message.setTo("an@example.net");

// Multiple primary recipients via varargs.
message.setTo(
        "an@example.net",
        "binh@example.net",
        "chi@example.net"
);
~~~

In Java, the **String...** syntax is *varargs*: the caller can pass multiple String arguments or a pre-built **String[]**.

~~~java
String[] recipients = {
        "an@example.net",
        "binh@example.net",
        "chi@example.net"
};

message.setTo(recipients);
~~~

This is the appropriate approach when the recipient list is built dynamically from a database, configuration, or a business processing layer.

### setTo sets the list; it does not accumulate

A common mistake:

~~~java
message.setTo("an@example.net");
message.setTo("binh@example.net");
~~~

**Do not expect the two calls above to combine two recipients on their own**. The setter sets the value of the To field; the later call replaces the earlier list. If you need two recipients, pass both in the same call or assemble the array first:

~~~java
message.setTo("an@example.net", "binh@example.net");
~~~

### Do not assume a comma-containing string will be split correctly at every layer

Do not treat the following call as a clear way to express a list:

~~~java
message.setTo("an@example.net, binh@example.net");
~~~

When using **SimpleMailMessage**, representing multiple recipients as **separate String elements** matches the API contract directly and avoids depending on some layer interpreting a string containing commas. If the input data is CSV or a list string, parse and validate it at the application layer before calling setTo.

## 4. Complete example: one notification message for multiple staff

Suppose the application needs to announce a shared maintenance schedule to three staff members. All three will receive the **same subject and the same content**, so a single SimpleMailMessage with multiple To addresses is a concise option.

~~~java
package com.example.notification;

import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceMailService {

    private final MailSender mailSender;

    public MaintenanceMailService(MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void announceMaintenance() {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("operations@example.com");
        message.setTo(
                "an@example.net",
                "binh@example.net",
                "chi@example.net"
        );
        message.setSubject("Maintenance notice");
        message.setText("""
                Hello,

                The system will undergo maintenance from 22:00 to 23:00 tomorrow.
                Please save your work before this time.

                Operations Team
                """);

        mailSender.send(message);
    }
}
~~~

**Steps:**

1. **MaintenanceMailService** receives the MailSender interface via constructor injection.
2. **SimpleMailMessage** holds the information from the sender address to the subject and body.
3. **setTo(...)** declares the three recipients.
4. **send(message)** submits the message to the mail sending system; a normal synchronous call waits for the submission or throws an exception.

The example assumes the application has configured a suitable MailSender, usually **JavaMailSenderImpl** through Spring Boot mail auto-configuration or manual configuration. The addresses are for illustration; in practice, From must be allowed by the SMTP account or provider.

### Minimal configuration with Spring Boot

For a Spring Boot application with the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

A typical SMTP submission configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: sender@example.com
    password: REPLACE_WITH_SECRET
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

This is only an example configuration. In a real application, the password must be loaded from an environment variable or a secret management system and not committed into source code. The host, port, TLS, and authentication mechanism must match the real SMTP server. The SimpleMailMessage layer only describes the message and does not create an SMTP server on its own.

## 5. Combining To, Cc, and Bcc in the same message

A SimpleMailMessage can have all three recipient groups. Each group carries a different communication meaning, even though all of them are destinations that need delivery.

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("project@example.com");
message.setTo(
        "owner@example.net",
        "developer@example.net"
);
message.setCc(
        "team-lead@example.net",
        "reviewer@example.net"
);
message.setBcc("audit@example.org");
message.setSubject("Progress report");
message.setText("The project progress report has been updated.");

mailSender.send(message);
~~~

| Address | Group | Meaning |
|---|---|---|
| owner@example.net | To | Primary recipient, responsible for following up. |
| developer@example.net | To | Primary recipient who also takes part in handling. |
| team-lead@example.net | Cc | Receives a copy to stay informed. |
| reviewer@example.net | Cc | Receives a public copy. |
| audit@example.org | Bcc | Receives a copy hidden from the public recipient list under normal handling. |

### Each group can contain multiple addresses

The setters support arrays or varargs:

~~~java
String[] to = {"first@example.net", "second@example.net"};
String[] cc = {"manager@example.net", "supervisor@example.net"};
String[] bcc = {"archive@example.org", "observer@example.org"};

message.setTo(to);
message.setCc(cc);
message.setBcc(bcc);
~~~

**Cc is not read-only mode**: Cc recipients still see the content and attachments (if any, in other message types). **Bcc does not encrypt the content**: Bcc recipients can still read the message like the other recipients.

There is no separate SMTP sending flow for To, Cc, and Bcc just because they have different names. The grouping mainly serves display and communication conventions, while the actual recipient list is used at the transport layer.

## 6. Email headers differ from the SMTP recipient list

This is the most important technical point when discussing **one message for multiple recipient addresses**.

An email has **headers** that describe the message to the reader, for example:

~~~text
From: operations@example.com
To: an@example.net, binh@example.net
Cc: team-lead@example.net
Subject: Maintenance notice
~~~

But the SMTP server usually receives the list of destinations through the **SMTP envelope**, with equivalent commands:

~~~text
MAIL FROM:<bounces@example.com>
RCPT TO:<an@example.net>
RCPT TO:<binh@example.net>
RCPT TO:<team-lead@example.net>
RCPT TO:<audit@example.org>
DATA
... message content, including the From/To/Cc headers ...
.
~~~

In the example, **audit@example.org** is a Bcc recipient. This address needs to be in the envelope so the sending system knows the delivery path, but it normally does not appear in the To/Cc headers of the message seen by other recipients.

Three things must be distinguished:

- **The From header** is the displayed sender address; it may differ from the **envelope MAIL FROM** used for delivery/bounces.
- **The To/Cc headers** show the public recipients; they are not the only list the server may deliver to.
- **Bcc** is a real recipient in the delivery mechanism, but the Bcc header is usually removed/adjusted when the message is sent to avoid disclosing this list.

With SimpleMailMessage, Spring/Jakarta Mail handles converting the recipient information into the message and the SMTP requests at the sending layer. The application should not assemble raw SMTP strings itself or arbitrarily add fake headers to achieve a similar result.

## 7. How does one message differ from many messages?

The following two implementations have different meanings.

### Approach A: One message, multiple recipients

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("notice@example.com");
message.setTo("an@example.net", "binh@example.net");
message.setSubject("General notice");
message.setText("The system will undergo maintenance tonight.");

mailSender.send(message);
~~~

**Characteristics:** same subject, same body; the To addresses may be seen by the other recipients. This is **one message** submitted to be delivered to multiple addresses.

### Approach B: One message per recipient

~~~java
SimpleMailMessage first = new SimpleMailMessage();
first.setFrom("notice@example.com");
first.setTo("an@example.net");
first.setSubject("General notice");
first.setText("The system will undergo maintenance tonight.");

SimpleMailMessage second = new SimpleMailMessage();
second.setFrom("notice@example.com");
second.setTo("binh@example.net");
second.setSubject("General notice");
second.setText("The system will undergo maintenance tonight.");

mailSender.send(first, second);
~~~

In approach B, **two different SimpleMailMessage objects** are passed to the varargs overload of **MailSender.send(SimpleMailMessage...)**. Each message has only one primary recipient. This is not the same thing as one message with two To addresses.

| Criterion | One message with multiple To | Multiple messages, one To each |
|---|---|---|
| Number of message objects | One | Several |
| Number of final recipients | Possibly many | Total can be many |
| To header | A shared recipient list | Usually contains only each person's address |
| Subject and content | One copy for everyone | Can be the same or personalized |
| Address privacy | To/Cc usually see each other | Easy to isolate addresses between recipients |
| Per-recipient status tracking | Need to track each recipient within one message | Easy to attach separate status to each message |
| Changing content per recipient | Not suitable | Suitable |
| Transport efficiency | May reduce the number of message submissions in some configurations | Creates many messages; cost depends on the transport/ESP |

**A Java call with multiple messages does not necessarily correspond to one atomic SMTP transaction.** If you call send(first, second), the first message succeeding does not guarantee the second succeeds too.

## 8. Sending to a dynamically built recipient list

In a real application, recipients usually come from a business service or a database. You should **consolidate and validate the list** before setting up the SimpleMailMessage.

Example of a service that receives a list of addresses already permitted by the application layer:

~~~java
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

@Service
public class GroupNoticeService {

    private final MailSender mailSender;

    public GroupNoticeService(MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(List<String> selectedRecipients) {
        Objects.requireNonNull(selectedRecipients, "recipients");

        Set<String> unique = new LinkedHashSet<>();
        for (String address : selectedRecipients) {
            if (address == null || address.isBlank()) {
                throw new IllegalArgumentException(
                        "The recipient list contains an empty address"
                );
            }
            unique.add(address.trim());
        }

        if (unique.isEmpty()) {
            throw new IllegalArgumentException(
                    "At least one recipient is required"
            );
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.com");
        message.setTo(unique.toArray(String[]::new));
        message.setSubject("Group notice");
        message.setText("The notice content is sent to the group as a whole.");

        mailSender.send(message);
    }
}
~~~

**LinkedHashSet** here preserves order and removes address strings that match exactly. This is just a simple deduplication approach for the example; it does not mean email addresses have been fully normalized according to each system's rules. Do not arbitrarily convert every local-part to lowercase or transform addresses with rules that have not been confirmed.

The application still needs to check the **address syntax**, **the right to receive information**, and the **limit on the number of recipients** before calling send(). SimpleMailMessage is a data object, not a service that verifies a mailbox exists. A syntactically valid address can still be rejected by the destination server or have no real recipient.

### If the initial data is a customer list

When the list consists of unrelated customers, what matters is not just converting from List to String[]. You need to determine whether they are allowed to know each other's addresses or read the content together. If not, **each customer needs a separate message** or an appropriate delivery mechanism that protects the addresses.

## 9. Use Bcc when you want to hide public addresses

For an identical notification sent to a small group, Bcc can help limit the public disclosure of the recipient list in the headers:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("announcement@example.com");
message.setTo("announcement@example.com");
message.setBcc(
        "member-a@example.net",
        "member-b@example.net",
        "member-c@example.net"
);
message.setSubject("General notice");
message.setText("The content applies to all members.");

mailSender.send(message);
~~~

The example sets a **To** address that the organization actually manages so the message has a clear public recipient; this address also receives the message, so it must have a legitimate purpose and right of use. Do not use someone else's address as To just to hide the list.

### Limits of Bcc

- A Bcc address usually does not appear in the headers copy of the To/Cc recipients, but **the SMTP server and the sending provider still know it** because they need to deliver the message.
- Bcc **does not encrypt** the subject, content, or attachments and does not control whether recipients forward the message.
- A Bcc recipient may reveal on their own that they received the message when replying or forwarding.
- How the Bcc copy is produced may differ by sending system; do not expect every client or provider to display exactly the same header form.
- Bcc does not by itself solve recipient quotas, spam filters, or personalization requirements.

If each person has a confirmation URL, token, temporary password, amount, or other private data, **do not combine them into one Bcc message**: all recipients will receive the same content, leading to the risk of information exposure.

## 10. When to send a shared message and when to split it

### Send one shared message when

- The content sent to everyone is **completely identical** and contains no one individual's private data.
- The recipient list is small, determined, and allowed to receive the information.
- Disclosing addresses in To/Cc is appropriate for the group, or Bcc is used deliberately.
- You do not need separate send status, separate URLs, or separate content per person.
- The SMTP server/ESP recipient quota allows it.

Suitable examples: an internal coordination email among people working on the same task, or a small group notification that contains no private data.

### Send separate messages when

- The message contains an OTP code, a password reset link, account data, an invoice, order data, or private information.
- Each person needs a different greeting name, deadline, language, link, or content.
- Recipients should not know each other's email addresses.
- The application needs to record status, bounces, retries, and statistics for each person.
- The list is large and needs batching, rate limiting, consent management, or unsubscribe.

Example of what not to combine:

~~~java
// Not suitable: everyone will see the same resetLink.
SimpleMailMessage message = new SimpleMailMessage();
message.setTo("user-a@example.net", "user-b@example.net");
message.setSubject("Password reset");
message.setText("Visit: " + resetLink);
mailSender.send(message);
~~~

For password reset, the application needs to generate a **request/token appropriate for each account**, with an expiration and access control, and then send a separate message to the right recipient.

## 11. Limits on the number of recipients and the message size

**SimpleMailMessage.setTo(String...)** does not define a universal number such as "at most 100 addresses" for every environment. The real limits come from many places:

- The SMTP server or ESP limits **recipients per message**.
- The sending account has limits on **the number of messages, recipients, and sending rate** per hour/day.
- The provider or gateway has a limit on **email size**.
- The SMTP relay may defer, rate-limit, or reject when the quota is exceeded.
- The receiving mail server has policies filtering the number of recipients, frequency, or sender reputation.

Therefore, even though the API allows declaring a long list, **you should not make a message with thousands of To addresses the default for every bulk sending task**.

If you need to send to a large list, you can split it into groups (*batch*) to control the number of recipients in each submission. However, splitting into multiple batches creates **multiple separate messages**, which changes tracking behavior and may affect headers/message IDs. Better still, when you need to protect addresses and track each person's statistics, send each message through a worker or a bulk email service designed for that purpose.

### A batch is not a magical send() call

Suppose the system has 500 addresses and the provider accepts at most 50 recipients per message. You may need 10 groups, each a separate SimpleMailMessage; but the limit number must come from the real provider, not a guess.

Other business requirements to consider:

1. Is a group allowed to be resent if that group fails?
2. If one recipient is rejected, can sending continue for the others?
3. If a group is resent after a timeout, could recipients receive two copies?
4. Do you need to track who received, bounced, or unsubscribed?

Grouping helps control load, but does not by itself answer all the questions above.

## 12. What does the send() result mean when there are multiple recipients?

In common usage, Spring Mail calls the SMTP transport to submit the message. SMTP exchanges with the envelope sender address and the recipient addresses, and may check each recipient at the **RCPT TO** command.

A simple flow:

~~~text
Spring application                       SMTP submission server
        |                                           |
        | --- MAIL FROM --------------------------> |
        | <------------------------------ response |
        | --- RCPT TO: an@example.net ------------> |
        | <------------------------------ response |
        | --- RCPT TO: binh@example.net ----------> |
        | <------------------------------ response |
        | --- DATA -------------------------------> |
        | <------------------------------ response |
        |                                           |
    send() returns or throws an exception           |
~~~

The server may accept one recipient but reject others, depending on policy. Jakarta Mail and the SMTP transport have behavior related to continuing to send when some recipients are invalid; configuration such as **mail.smtp.sendpartial** can also affect how this is handled. Therefore:

- **Do not assume that one failing recipient means all the remaining people definitely were not sent to.**
- **Do not assume that send() not throwing an exception means everyone reached the Inbox.**
- **Do not automatically retry the entire list when you do not clearly know which group has been accepted**, because it can create duplicate messages.
- When you need exact results per address, you must use detailed error information, SMTP/ESP logs, or the provider's own tracking mechanism.

### SMTP accepted differs from delivered

The first SMTP server may accept the message for further processing. After that there are still the DNS/MX hops, relays, spam filtering systems, mailboxes, and email clients. Therefore a message with multiple recipients can have a final result that **differs for each address**, even though the application called send() only once.

~~~text
                    One SimpleMailMessage
                              |
                     MailSender.send()
                              |
                    SMTP relay accepts
                        /     |      \
                       v      v       v
                   Recipient A B       C
                       |      |       |
                  Received  Defer   Bounce
                       |
                      Inbox / Spam / other folder
~~~

States such as Defer, Bounce, or Delivered at later hops are usually not reported directly through the return value of **send()**. ESP infrastructure may provide logs, webhooks, delivery events, or bounce reports.

## 13. Handling exceptions when sending one shared message

Spring Framework Mail uses the **MailException** family to represent mail sending errors. For example:

| Exception | Common situation | Direction for investigation |
|---|---|---|
| **MailAuthenticationException** | SMTP AUTH failed | Check credentials, account permissions, authentication mechanism. |
| **MailSendException** | An error in transport or sending the message | Look at the root cause, the SMTP response, and the scope of affected recipients. |
| **MailParseException** | An invalid message/address during conversion | Check address values, headers, and error information. |

Example for letting the dispatching layer distinguish a clear authentication error from general sending errors:

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.MailSender;

public final class GroupMailDispatcher {

    private final MailSender sender;

    public GroupMailDispatcher(MailSender sender) {
        this.sender = sender;
    }

    public void dispatch(SimpleMailMessage message) {
        try {
            sender.send(message);
        } catch (MailAuthenticationException ex) {
            // The credential or SMTP sending permission needs to be fixed.
            throw ex;
        } catch (MailException ex) {
            // The outer layer records the error type, the message/attempt ID,
            // and decides whether to investigate or retry conditionally.
            throw ex;
        }
    }
}
~~~

The code only illustrates the **error handling boundary** and has not implemented a complete retry policy. For a message with multiple recipients, you need to find out **the scope already accepted by the SMTP server** before retrying the whole thing. **MailSendException** can hold failure information at the message level; this does not replace the SMTP provider's recipient/delivery logs.

### Temporary, permanent, and unknown-result errors

**Temporary:** an overloaded server, unstable connection, SMTP 4xx responses. You can retry with backoff, a limit on attempts, and result tracking.

**Permanent:** invalid address, the sending account rejected, policy not allowing relay, content blocked by rules. Fix the data or configuration before sending again.

**Unknown:** the connection drops after the client has submitted DATA but has not read the acceptance response. The server may have received the email; sending again may cause recipients to receive a second copy. You should record the **UNKNOWN** status and reconcile when the provider supports it.

## 14. Privacy, security, and responsibility toward recipients

**Sending one message to multiple To addresses may reveal the email list** to the members in the same email, because the To and Cc headers are normally seen by recipients. This can be perfectly reasonable within a project group, but is not appropriate when sending data to unrelated customers.

Points to control:

1. **Right to receive information:** are people in the group allowed to see the entire shared content?
2. **Right to know addresses:** is it allowed to disclose To/Cc addresses among recipients?
3. **Personalization:** is there a token, order number, amount, private link, or user data in the content?
4. **Additional recipients:** do Cc and Bcc have the same right to read the content, and has the access policy been considered?
5. **Log data:** do not write the entire address list, OTPs, or sensitive content into logs if not necessary.
6. **Consent and unsubscribe:** if it is marketing mail, you must respect subscription/opt-out and related policies.

### Bcc is a display limitation, not end-to-end security

Bcc helps avoid displaying addresses in the headers under normal handling. However, SMTP systems must still know the destinations, Bcc'd people still receive the content, and they can forward or Reply All and reveal their participation. If you need to protect private data for each person, **sending each message separately** is the more appropriate design.

### Recipient names or data from a request

Do not accept an arbitrary email list from an API and then send mail to every address without verifying the right to perform the operation. You may need to authenticate the caller, check that each recipient belongs to a permitted group, limit the count, and prevent abuse of the mail sending endpoint.

SimpleMailMessage manages simple text content; it does not perform these business control steps itself.

## 15. One message for multiple people does not mean asynchronous sending

In normal usage, **mailSender.send(message)** performs the send synchronously on the calling thread. Having five or ten recipients does not turn the call into an automatic background job.

For a web request that needs a fast response, or when the system must send a large volume, you can separate mail sending into a worker:

~~~text
Business event / HTTP request
             |
             v
     Record the intent to send a notification
             |
             v
      Queue / Outbox record
             |
             v
          Mail worker
             |
             v
    Build SimpleMailMessage
             |
             v
       MailSender.send()
             |
             v
           SMTP/ESP
~~~

If you decide to send **one message to many people**, the job record must keep the recipient list and the shared data at a valid point in time. If you decide to send **a separate message to each person**, you can create a job or send status per recipient for more accurate retry and monitoring.

**A queue or transactional outbox does not by itself guarantee exactly-once delivery.** If a worker finishes sending but dies before updating the status, a retry may cause duplicates. When one message has multiple recipients, the risk of repetition affects the whole group, so managing attempts and the ability to reconcile is even more necessary.

## 16. Observing and testing behavior at the application layer

When testing a shared-sending service, you can use a mock **MailSender** to observe one send() call and the To/Cc/Bcc lists that were set. This is a test at the application layer and needs no real SMTP connection.

Illustrative example with JUnit 5 and Mockito:

~~~java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.mockito.Mockito.*;

class MaintenanceMailServiceTest {

    @Test
    void sendsOneMessageToThreeRecipients() {
        MailSender sender = mock(MailSender.class);
        MaintenanceMailService service = new MaintenanceMailService(sender);

        service.announceMaintenance();

        ArgumentCaptor<SimpleMailMessage> captured =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captured.capture());

        SimpleMailMessage actual = captured.getValue();
        assertArrayEquals(
                new String[] {
                        "an@example.net",
                        "binh@example.net",
                        "chi@example.net"
                },
                actual.getTo()
        );
    }
}
~~~

The example assumes the project has JUnit 5 and Mockito. It illustrates how to verify that **one SimpleMailMessage** contains **three recipient addresses** and is handed to the MailSender. To test that the SMTP server receives the message, you can use an SMTP test server or the provider's sandbox; those tests belong to a different integration scope.

In real operation, you should monitor:

| Information | Purpose |
|---|---|
| **Notification ID** | Identifies the intent to send a notification. |
| **Attempt ID** | Distinguishes resubmissions of the message. |
| **Recipient count** | Know the number of destinations in one message, detect exceeding limits. |
| **SMTP response / exception type** | Diagnose errors at the submission hop. |
| **Provider message ID** | Look up status at the ESP/MTA. |
| **Bounce, deferred, delivered events** | Observe results at later hops if the provider supports it. |

Do not assume there is only one common final status for every recipient. In practice, some people may receive the message successfully while others are delayed, rejected, or placed in Spam.

## 17. Common errors

| Symptom | Typical cause | How to handle |
|---|---|---|
| Only the last person receives the message | Called setTo several times and overwrote the list | Gather the addresses into a single setTo call or one String[]. |
| A string with multiple addresses is handled wrongly | Passed one String containing commas and expected it to split itself | Parse into individual addresses and pass them via varargs/String[]. |
| No recipients | The array/list is empty or the data was all filtered out | Check the list before creating the message. |
| The email is rejected at SMTP | One or more recipients are invalid, relay is forbidden, or limits are exceeded | Look at the SMTP response and the provider's policy. |
| Users see other people's emails | Put the customer list in To/Cc | Send separately to each person or consider Bcc with shared content. |
| A Bcc recipient is exposed when replying | The recipient deliberately Reply Alls or forwards | Understand the limits of Bcc; choose another sending flow if high security is needed. |
| Everyone receives the same link/token | Used one message for content that needs personalization | Create a separate token and message for each account. |
| Many people receive duplicates after a retry | The earlier send result was unclear but the entire list was resent | Track attempts, reconcile status, and then retry conditionally. |
| Shared sending is limited | Exceeded the recipient/message quota or rate limit | Reduce the group size, use a worker, and a sending strategy suited to the provider. |
| send() succeeds but the recipient does not see the message | The message is still in a queue, bounced late, or went to Spam | Check ESP logs, DNS/receiving policy, and the mailbox. |

### Errors caused by duplicate lists across fields

If the same address appears in both To and Cc, or repeats in an array, the actual sending behavior depends on the processing layer and the mail server. Do not rely on the sending system to deduplicate absolutely. The business layer should have clear rules: which address is To, which is Cc, and whether duplicates between groups need to be removed.

If a person needs to be hidden in Bcc, do not also put them in To/Cc; otherwise, the address may be exposed through a public field.

## 18. Rules for choosing the right design

When faced with the requirement "send to multiple addresses", you can decide in this order:

1. **Is the content completely identical?** If each person has their own content, use multiple messages.
2. **Are recipients allowed to know each other's emails?** If so and they are working together, To/Cc may be reasonable; if not, send separately or use Bcc for a small shared notification.
3. **Do you need to track each person's result separately?** If so, sending separately makes the status system easier to design.
4. **How many recipients per message does the provider allow?** Respect the real limit, and do not rely on the storage capacity of String[].
5. **If one person is rejected or the send status is unclear, what will retry do?** Determine the policy before implementation.

For a small group that works together and receives the same notification, **one SimpleMailMessage with multiple To/Cc addresses** is a simple, fit-for-purpose approach. For independent users and personal data, **multiple SimpleMailMessage objects, each with one recipient**, is usually the choice that is easier to protect data and track.

## 19. Takeaways

**SimpleMailMessage.setTo(String...)** lets you put multiple recipient addresses into **one message**. You can set **setCc(String...)** and **setBcc(String...)** similarly, and then call **MailSender.send(message)** to submit the message to the SMTP system. One message contains one subject and one shared body; the addresses are multiple delivery destinations of that same message.

Do not confuse **one message with multiple recipients** with **multiple messages sent through one send(...) call**. The first suits general notices and a group that is allowed to know each other; the second suits personalized content, privacy, and per-person send status. When designing, always consider SMTP limits, the possibility of partial failure, the risk of duplicate sends, and the exact meaning of the **send()** result.
