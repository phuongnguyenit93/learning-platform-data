# Multi-Hop Delivery Path and Potential Failure Points

## 1. An Email Does Not Travel Straight from Spring to the Inbox

When an application calls **JavaMailSender.send(...)**, it is only submitting the message to the sending system. From there, the email typically passes through multiple servers, queues, and filters before appearing in the recipient's mailbox. Each hop has different responsibilities, success signals, and error-handling mechanisms.

In **Spring Framework Mail**, **MailSender** and **JavaMailSender** provide the email-sending contract for application code; **JavaMailSenderImpl** typically uses **Jakarta Mail** to communicate with an SMTP server. These interfaces do not replace the SMTP relay, DNS, receiving server, spam filter, or mailbox hosting service.

To troubleshoot issues accurately, separate three questions:

1. **Which hop is the message at?** Newly created, accepted by the SMTP relay, accepted by the destination server, or present in the mailbox?
2. **Who is responsible for forwarding it next?** The Spring application, the SMTP provider, the recipient's mail server, or the mail storage system?
3. **Under what conditions is a retry allowed?** Temporary errors, permanent errors, and cases where acceptance is unknown must each be handled differently.

## 2. Multi-Hop Path Diagram

~~~text
 [1] Business event (account signup, order, notification)
      |
      v
 [2] Spring application / EmailService
      |   Builds recipients, subject, text/HTML, attachments
      v
 [3] MailSender / JavaMailSender
      |   JavaMailSenderImpl -> Jakarta Mail -> SMTP
      v
 [4] SMTP submission server / Email Service Provider (ESP)
      |   Authenticates, accepts or rejects message, may enqueue
      v
 [5] One or more Mail Transfer Agents (MTAs)
      |   DNS/MX lookup, routing, forwarding via SMTP
      v
 [6] Recipient domain's mail server
      |   Policies, SPF/DKIM/DMARC, spam, virus, quota
      v
 [7] Mail Delivery Agent / mailbox storage
      |   Inbox, Junk/Spam, quarantine, or other folder
      v
 [8] Recipient reads via webmail, IMAP, or email client
~~~

This is a high-level diagram, not a fixed route. Real infrastructure may add relays, security gateways, internal routing services, forwarding servers, or post-SMTP filtering systems. Some steps may also be consolidated within a single service.

### Foundational Terms

| Concept | Role in the Path |
|---|---|
| **MUA (Mail User Agent)** | Application that creates/reads email; on the automated sending side, a Spring service plays the message-creation role. |
| **MSA (Mail Submission Agent)** | Receives mail from applications or email clients, typically over an SMTP submission port. |
| **MTA (Mail Transfer Agent)** | Transfers mail between email systems, typically via SMTP. |
| **MDA (Mail Delivery Agent)** | Places the message into the recipient's mailbox storage. |
| **MX record** | DNS record indicating the servers designated to receive mail for a domain. |
| **ESP (Email Service Provider)** | Email sending service provider, usually offering an SMTP relay or proprietary API, queues, and status reporting. |
| **IMAP/POP3** | Protocols for accessing stored mail, not how Spring Mail submits messages for sending. |

## 3. Hop 1: Business Logic and Message Creation

An event such as account registration, password reset, or payment confirmation triggers the intent to send an email. The application must determine recipients, subject, body, language, sender address, and attachments. With Spring Mail, simple plain-text messages can use **SimpleMailMessage**, while HTML or MIME messages typically use **MimeMessage** and **MimeMessageHelper**.

Example:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient, String orderCode)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name()
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Order confirmation " + orderCode);
        helper.setText(
                "Order " + orderCode + " has been recorded.",
                false
        );

        mailSender.send(message);
    }
}
~~~

The snippet assumes the application has configured a **JavaMailSender** bean and a valid sending account. This is a plain-text email using the MIME API to illustrate the starting point of the sending flow.

**Errors that can occur even before an SMTP connection:**

- **Invalid input data:** missing address, malformed syntax, wrong recipient passed, or broken template variable rendering.
- **Unable to build MIME:** exceptions while constructing the message, wrong encoding, or invalid HTML data per application checks.
- **Attachment failure:** file missing, unreadable, too large, or blocked by application rules.
- **Missing mail-sender bean:** Spring/Boot dependency or configuration is incomplete.
- **Disallowed sender address:** sometimes caught inside the application, sometimes blocked only at the SMTP server.

For data or configuration errors, retrying the exact unmodified payload is usually pointless. This stage is also where sending permissions must be checked, user data leaks prevented, and business tracking IDs attached.

## 4. Hop 2: From JavaMailSender to the SMTP Submission Server

When **send()** is called, the standard **JavaMailSenderImpl** uses Jakarta Mail to converse with the SMTP server in sequence:

1. Resolve the SMTP hostname via DNS.
2. Open a TCP connection to the configured port.
3. Establish TLS encryption, if required by policy.
4. Exchange SMTP greeting, EHLO, and server capability advertisement.
5. Authenticate using a mechanism supported by the server, if required.
6. Send **MAIL FROM**, one or more **RCPT TO** commands, then **DATA** containing the message.
7. Read SMTP responses to learn whether the current command was accepted or rejected.

Common ports:

| Port | Typical Purpose | Notes |
|---|---|---|
| **587** | SMTP submission from client/application | Usually uses STARTTLS per provider configuration. |
| **465** | SMTP submission with TLS upon connection | Requires corresponding implicit TLS configuration. |
| **25** | Server-to-server mail communication/relay | May be restricted by cloud environments or ISPs. |

**Common errors:** wrong SMTP hostname; DNS resolution failure; timeouts; firewall blocking the port; mismatched TLS/STARTTLS configuration; invalid TLS certificate; wrong username/password/token; account disallowed from SMTP AUTH; server refusing relay; rate limits exceeded; message size exceeding limits; disallowed recipient or sender address.

### Headers and the SMTP Envelope Are Not the Same Thing

An email has **headers** such as **From**, **To**, **Subject**, and **Reply-To** that readers can see. Meanwhile, SMTP transports the message according to the **envelope** via **MAIL FROM** and **RCPT TO**. The envelope sender can be where bounces go; Bcc can become an envelope recipient without being listed in the delivered message's headers.

This distinction matters during failure investigations because an SMTP relay may accept header syntax yet reject the envelope sender or recipient; domain authentication checks also look at more than a single address.

## 5. Hop 3: SMTP Relay Accepts and Queues the Message

In SMTP communication, a success response after **DATA** (usually code **250**) means the server the client just spoke to has **accepted the message at that hop for further processing**. It is not yet proof that the email has been stored in the recipient's Inbox.

After acceptance, the SMTP relay or ESP may:

- Place the email into a queue.
- Attempt delivery to the destination by priority and server availability.
- Defer temporarily when the receiving side is overloaded or rate-limiting.
- Retry over a duration defined by the sending infrastructure.
- Return a bounce if it later determines delivery is impossible.

### Interpreting SMTP Responses Properly

| Group | General Meaning | How to Handle |
|---|---|---|
| **2xx** | SMTP command at current hop succeeded | Record that the current server accepted the action; continue monitoring later hops if possible. |
| **4xx** | Temporary failure | May retry with limits and backoff while preserving error details. |
| **5xx** | Permanent failure for the current request | Usually requires fixing the address, policy, config, or content before sending again. |

For instance, **421** can indicate service temporarily unavailable; **450/451** usually relate to temporary conditions; **550** can indicate address or policy rejection. Do not draw conclusions from three digits alone: read the full SMTP reply text and any **enhanced status code** like **4.x.x** or **5.x.x** if present. Exact meaning depends on the exchange phase and server policy.

### Dangerous Scenario: Sent Without Receiving Confirmation

~~~text
Spring Application                 SMTP Relay
     | -------- DATA -------------> |
     |                              | Received and stored message
     | <----- 250 accepted ----X    | Connection dropped
     |
     +-- Application may see a timeout,
         even though the server accepted the email.
~~~

If the application sees an error and immediately resends, the recipient **may receive two copies**. Sending via SMTP does not form an atomic transaction across the application database, the Spring app, and the SMTP server. Result states must allow **UNKNOWN**, rather than treating every timeout as "not sent."

## 6. Hop 4: DNS, MX, and Transfer Servers

When an email is sent to an address like **person@company.example**, the delivery infrastructure must locate where mail for **company.example** is received. Typically it queries DNS **MX records** and attempts to contact the published mail servers.

A message may pass through multiple **MTAs**. In some setups, email passes through security gateways, intermediate relays, and queues before reaching the destination domain's server. DNS, networking, or relay systems at any hop can fail.

| Issue | Possible Symptoms | How to Identify |
|---|---|---|
| DNS failure or unresponsiveness | Destination not found, mail deferred | DNS queries, sending server logs |
| Misconfigured MX or unreachable destination server | Connection failed, timeout | MX records, target IP/hostname, connection responses |
| Relay denies forwarding | SMTP rejection | Relay policy responses or authentication details |
| Destination MTA temporarily overloaded | Deferred, multiple retries | Sender queues/logs, 4xx SMTP codes |
| Routing infrastructure has a loop or misconfiguration | Message travels abnormally, never arrives | `Received` headers, relay logs |

A domain lacking an MX record is not enough to conclude all emails to that domain are undeliverable: under SMTP rules there is fallback to A/AAAA address records, or a domain may publish a mechanism refusing email. Inspect actual DNS records and received error codes.

These issues lie **beyond Spring's message-creation layer**. Editing an HTML template or switching from **SimpleMailMessage** to **MimeMessage** cannot fix an MX error or inter-server network failure.

## 7. Hop 5: Destination Server Checks and Acceptance Decision

Receiving mail systems must balance delivering legitimate mail against blocking spam, spoofing, phishing, malware, and storage abuse. Thus a destination server may accept, defer, reject, or quarantine a message per its policies.

### Key Inspection Layers

| Mechanism | Purpose | Visible Failure/Impact |
|---|---|---|
| **SPF** | Checks whether the sending source is authorized by the domain tied to the SMTP identity | Affects accept/spam decisions per policy. |
| **DKIM** | Verifies the cryptographic signature on the message | Invalid signatures reduce trust signals. |
| **DMARC** | Checks alignment between the `From` header domain and matching SPF/DKIM, enforcing domain policy | May cause quarantine/reject depending on policy and auth results. |
| **Reputation** | Evaluates IP/domain reputation, sending behavior, complaint rates | Messages may be throttled, deferred, or blocked. |
| **Anti-spam/anti-malware** | Inspects content, links, attachments, phishing indicators | May land in Spam, quarantine, or be rejected. |
| **Recipient/quota policy** | Checks recipient validity, storage quota, organizational rules | May be rejected at SMTP time or generate a bounce later. |

**SMTP authentication** with the application's account and **SPF/DKIM/DMARC** are two separate concerns. Logging into SMTP successfully does not guarantee the sending domain is properly authenticated. Nor does Spring Boot mail starter create DNS records or sign DKIM for every provider. Operators must configure domains, SMTP/ESP services, and DNS policies per specific requirements.

An email can be **accepted by the destination server at the SMTP layer** and then routed by downstream filters into **Spam/Junk** or quarantine. That is why users say "I didn't get it" even while the application recorded a successful send.

## 8. Hop 6: Delivery to Mailbox and Recipient Access

After being accepted by the destination server, the email may be handed to the delivery agent (**MDA**) to store in the mailbox. Users then view it via webmail, IMAP, POP3, or a mobile app.

Common sources of misunderstanding:

- The email is in **Spam/Junk**, a rule-routed folder, or a secondary mailbox.
- Enterprise administration placed the message in **quarantine**, or an internal rule deleted/forwarded it.
- The mailbox is full, the account is suspended, or the storage service has an outage.
- The message is on the server, yet the mail client has not synced yet.
- The recipient created an automatic rule moving messages to another address or folder.

A **delivered** status published by an ESP usually means the destination server accepted the handoff; exact definitions vary by provider. It **does not guarantee** the message landed in the Inbox, appeared on the device, or was opened and read by the user.

### Distinguishing Success Milestones

~~~text
CREATED -> SUBMITTED -> SMTP ACCEPTED -> REMOTE ACCEPTED -> VISIBLE/READ
   |          |              |                 |              |
Created    Request sent  Sending relay   Destination      Inbox/Spam and
in app     to mail       accepted        system accepted  user opens
           server        message         message          message
~~~

The Spring application cannot see all the milestones on the right by itself. You need ESP logs, bounce/DSN reports, webhooks, or data provided by the receiving side. Often it is impossible to assert "landed in Inbox" with certainty from the sending system alone.

## 9. Hop-by-Hop Failure Isolation Table

| Hop | Symptom | Typical Causes | Where to Gather Evidence |
|---|---|---|---|
| **In-app content creation** | Exception before **send()** | Input/template, MIME, attachment, bean configuration | Application exceptions/logs |
| **SMTP connection** | Connect timeout, TLS handshake failure | DNS, port, firewall, TLS, certificates | Connection logs and SMTP config |
| **SMTP authentication** | Authentication rejected | Wrong credentials/token, missing send permissions | AUTH response, provider console |
| **Submission** | Sender/recipient/DATA rejected | Relay policy, address, quota, size | Full SMTP reply on the corresponding command |
| **Sender's queue** | Send succeeded yet mail is delayed | Throttling, deferral, overloaded destination server | ESP/MTA queues and delivery logs |
| **DNS/MX lookup and relay** | Fails only for one domain | Bad MX, DNS failure, route/relay policy | DNS queries, SMTP logs on MTA |
| **Destination checks** | Bounce, spam, policy rejection | SPF, DKIM, DMARC, reputation, recipient | Bounce codes, destination server notices |
| **Mailbox/client** | Reported delivered yet missing from Inbox | Junk/Spam, quarantine, rules, sync | Recipient/mailbox administrator |

**Pinpoint the failing hop first, then decide what to fix.** Do not guess at Java code edits when evidence shows the destination server is deferring or blocking by policy.

## 10. How Does Spring Mail Report Errors?

Spring Framework Mail uses the **MailException** family for mail-sending errors at the Spring layer. Some common types:

| Exception | General Meaning | How to Investigate |
|---|---|---|
| **MailAuthenticationException** | Authentication with the sending server failed | Check account, password/token, SMTP permissions. |
| **MailSendException** | Failure while sending | Inspect root cause, server responses, and delivery state. |
| **MailPreparationException** | Error while preparing the message | Check data/template/callback. |
| **MailParseException** | Error parsing or preparing message properties | Check content, MIME structure, and cause. |

With MIME emails, message-building operations can also throw **jakarta.mail.MessagingException** during preparation. Catching a single exception class and retrying every case is insufficient: different errors call for fixing data, fixing configuration, waiting and retrying, or investigating an unknown state.

Example separating error responsibilities in Java code:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class MailAttempt {

    private final JavaMailSender sender;

    public MailAttempt(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String recipient) throws MessagingException {
        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(message);
        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Notification");
        helper.setText("Message body.");

        try {
            sender.send(message);
        } catch (MailAuthenticationException ex) {
            // Review SMTP configuration and access permissions.
            throw ex;
        } catch (MailException ex) {
            // Store safe diagnostic info at the orchestration layer.
            // Do not auto-retry without classifying the cause.
            throw ex;
        }
    }
}
~~~

In Spring Boot, configuration typically lives under **spring.mail**; for example SMTP host, port, username, password, **mail.smtp.auth**, **mail.smtp.starttls.enable**, and timeouts. Real credentials must come from environment variables or a secret store, never committed to a repository or written to logs.

## 11. Three Outcome Categories When Sending Email

### A. Temporary Failure

Examples include an overloaded server, 4xx SMTP codes, brief network drops, or throttling. You can retry using **exponential backoff + jitter** with a max attempt count, bounded duration, and final-failure recording. Avoid firing large batches of retries simultaneously, which spikes load or harms reputation.

### B. Permanent Failure for the Current Request

Examples include invalid recipient, locked account, wrong credentials, disallowed sender address, message exceeding limits, or 5xx policy rejections. Retrying verbatim rarely helps; data or configuration must be fixed. However, response codes must be read alongside the detailed message and context; not every 5xx code describes the same root cause.

### C. Unclear Whether the Server Accepted the Request

Examples include a timeout right after **DATA**, losing the connection before reading the success response, or a worker crashing mid-send. In those cases, the application cannot assert the email was definitely not sent, and retrying risks duplicates. Record **UNKNOWN**, reconcile with logs/provider message IDs if available, and then decide how to proceed.

There is no end-to-end "exactly once" guarantee across the application, SMTP, and mailbox simply by calling **JavaMailSender.send()**.

## 12. Database Transactions and Duplicate-Send Risk

Suppose a business flow must write an order to the database and then send a confirmation email. Database commit and SMTP acceptance **do not share an atomic transaction**:

- Email sent, yet database transaction rolls back: the user receives confirmation for a nonexistent order.
- Database commits successfully, yet SMTP fails: the order exists without a notification sent.
- SMTP accepted the message, worker crashes before saving status: re-running may send a duplicate.

A common design pattern is the **transactional outbox**:

~~~text
      Database transaction
  +-----------------------------+
  | Write order                 |
  | Write outbox "send email"   |
  +-----------------------------+
                |
              COMMIT
                |
                v
        Worker reads outbox
                |
                v
       JavaMailSender.send()
                |
      +---------+-----------+
      |                     |
  ACCEPTED              FAILED/UNKNOWN
      |                     |
  Record status         Conditional retry /
                        reconcile / investigate
~~~

An outbox keeps business data consistent with the **intent to send mail**. It does not by itself eliminate all possibility of double sending: a worker can still die after SMTP receives the message but before marking the outbox processed. You need a stable notification ID, processing/status locks, and ESP idempotency if supported. With plain SMTP, you should not claim duplicates can be completely eliminated.

## 13. Cross-Hop Observability and Diagnostics

For traceability, the system should maintain a link between a business notification and SMTP submission attempts:

| Data to Track | Purpose |
|---|---|
| **Notification ID / business event ID** | Identifies which event triggered the email. |
| **Attempt ID, timestamp, and status** | Distinguishes the initial send from retry attempts. |
| **MIME Message-ID** | Correlates the message across mail headers when available. |
| **Provider/SMTP message ID** | Looks up ESP/MTA logs, queues, bounces, and delivery events. |
| **SMTP response and failure reason** | Identifies acceptance/rejection step or temporary error. |
| **Bounce, deferred, delivered, complaint** | Observes asynchronous outcomes if provided by the sending service. |

**The header Message-ID and the provider's internal ID may differ.** When using webhooks, verify event origin/signatures and handle duplicate or out-of-order webhook deliveries. Do not assume every provider exposes the same event set or uses the same definition of delivered.

To protect data, avoid logging SMTP passwords, tokens, OTPs, password-reset links, message bodies, or attachments in standard logs. Email addresses are also personal data; keep only what operations require and mask where appropriate.

### Some Real-World Scenarios

**Application returns HTTP 200 yet the recipient does not see the email.** First determine whether HTTP 200 meant SMTP was called or merely that a job was enqueued. Next check whether SMTP/ESP accepted it, whether there were deferrals/bounces, and then check Junk/Spam, quarantine, and recipient rules.

**Only emails to one domain fail.** Check DNS/MX for that domain, SMTP responses from the destination MTA, and relevant policies/reputation. If other domains work normally, the issue may lie in inter-domain networking or a policy specific to the receiving domain.

**After a retry, the recipient receives two copies.** Check whether the first attempt may have been accepted before the application timed out. Correlate attempt IDs with provider logs and improve UNKNOWN-state handling.

**SMTP authentication succeeds yet mail lands in Spam.** Succeeding at sending-server login does not replace SPF/DKIM/DMARC, reputation, or receiving-side content filters. Investigate domain authentication and receiving policies.

## 14. Investigation Workflow for a Failed Email

When receiving a report that "the email wasn't sent", follow this sequence:

1. **Was there an actual send request?** Locate the business notification ID, recipient, and trigger timestamp.
2. **Was the message constructed?** Check exceptions around input data, MIME, attachments, and templates.
3. **Did the SMTP connection succeed?** Check SMTP host DNS, port, TLS, credentials, and timeouts.
4. **How did the sender's relay respond?** Read status at MAIL FROM, RCPT TO, and DATA.
5. **Is the message queued, forwarded, or bounced?** Inspect ESP/MTA logs and provider message IDs.
6. **Did the destination server accept it?** Check DNS/MX, responses, SPF/DKIM/DMARC, and spam policies.
7. **Where is the message located?** Check Inbox, Junk/Spam, quarantine, forwarding rules, or sync errors.
8. **Is it safe to resend?** Distinguish temporary, permanent, and unknown outcomes; assess duplicate-send risk.

### Reference State Model for Applications

~~~text
PENDING -> PREPARING -> SUBMITTING
                            |
          +-----------------+------------------+
          |                 |                  |
       ACCEPTED           FAILED            UNKNOWN
          |                 |                  |
   QUEUED/DEFERRED   Classify error        Reconcile
          |
   REMOTE_ACCEPTED
          |
  May enter Inbox / Spam / quarantine
          |
  May receive delivery/bounce events later
~~~

This is a **business model for design and operations**, not a state machine automatically provided by Spring Mail. Plain SMTP only exposes certain boundaries to the application; downstream states depend on tracking capabilities of the provider and destination server.

## 15. Takeaways When Designing Email Architecture with Spring

- **The path is a chain of handoffs of responsibility.** Success at one hop does not prove success at all subsequent hops.
- **Spring Mail abstracts submitting email from the application.** SMTP relays, DNS, receiving systems, and mailbox storage can continue operating or fail afterward.
- **Interpret evidence per hop.** An application's HTTP response, SMTP 250, bounces, and delivered status each carry different meanings.
- **Retries require policy.** Distinguish temporary errors, permanent errors, and unknown outcomes; apply backoff, attempt caps, and reconciliation when needed.
- **Design observability from the start.** Link notification IDs, attempt IDs, message IDs, and provider responses; keep logs safe and protect recipient data.

Once you understand each hop clearly, the question "why didn't the email arrive?" narrows down to a concrete issue: **the app failed to build the message, SMTP didn't accept it, the relay couldn't deliver it, the destination server rejected it, or the mailbox isn't showing it**. That is the foundation for effective email error handling in systems using Spring Framework Mail.
