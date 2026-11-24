# One Message with Multiple Recipients and Multiple RCPT TO Commands

When a Spring application sends a notification to three email addresses, the SMTP server does not necessarily need to receive the entire message content three times. In a standard SMTP transaction, the sender can declare **one sender**, sequentially declare **multiple recipients with multiple RCPT TO commands**, and then transmit the **message content once via DATA** for the set of recipients the server accepted.

This is a foundational property of SMTP: **the number of recipients does not equal the number of messages that must be transmitted**, and the addresses SMTP uses for delivery do not completely match the address lists displayed in the To, Cc, and Bcc headers.

This lesson explains multi-recipient transactions from the SMTP protocol perspective, and then connects that to how Spring Framework Mail and Jakarta Mail send emails to a group of addresses.

## 1. Opening Scenario: One Notification for Three People

Suppose a Spring application needs to send a maintenance notice to:

- Lan: **lan@example.net** — primary recipient.
- Minh: **minh@example.net** — copied recipient.
- Audit team: **audit@example.net** — hidden recipient.

All three receive the same content:

> The system will undergo maintenance at 22:00. Please save your work before this time.

At the protocol level, an SMTP transaction might look like this:

~~~text
MAIL FROM:<notify@example.org>

RCPT TO:<lan@example.net>
RCPT TO:<minh@example.net>
RCPT TO:<audit@example.net>

DATA
From: notify@example.org
To: lan@example.net
Cc: minh@example.net
Subject: Maintenance notification

The system will undergo maintenance at 22:00.
Please save your work before this time.
.
~~~

The snippet above is abbreviated to emphasize structure. In a real exchange, the client must receive and handle server reply codes after commands; the message also needs appropriate headers and formatting rules. The line containing only a dot ends the SMTP data section and is **not part of the email content**.

Points to observe:

1. There is only **one MAIL FROM** starting the transaction.
2. There are **three RCPT TO commands**, each specifying one recipient address.
3. After the valid recipients have been accepted by the server, the client sends **one DATA** containing the shared headers and content.
4. The address **audit@example.net** is present in the delivery envelope but does not appear in To/Cc in the presented email content.

If the server accepts all three recipients, the same message is received for delivery processing to all three. The server may create multiple copies or multiple relay hops in downstream steps; that internal mechanism is independent of the application transmitting DATA only once in the transaction at hand.

## 2. Three Objects to Distinguish: Message, Envelope, and SMTP Transaction

In documentation or source code, the word **message** can refer to a Java object, an email with headers and a body, or a mail stored in an inbox. To understand multiple RCPT TO commands, three concepts must be separated.

### 2.1. Email Content: Internet Message

An **Internet message** has headers and a body, for example:

~~~text
From: notify@example.org
To: lan@example.net
Cc: minh@example.net
Subject: Maintenance notification
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

The system will undergo maintenance at 22:00.
~~~

These headers describe the displayed information and how to decode the content. They belong to the email structure under the Internet Message Format and MIME when needed.

### 2.2. SMTP Envelope: Envelope

The **SMTP envelope** specifies the addresses used in the transport step:

- **Envelope sender** is supplied in the **MAIL FROM** command.
- **Envelope recipients** are supplied one by one in the **RCPT TO** commands.

The envelope determines which recipients the SMTP server is being asked to handle the mail for. Envelope information is **not the From, To, or Cc lines inside DATA**.

An email can display To: lan@example.net while its envelope contains many addresses, including Bcc addresses, distribution list addresses, or another address per forwarding workflows. The SMTP server must process the envelope commands to know which addresses to deliver to, rather than relying solely on reading the To header.

### 2.3. SMTP Transaction: One Mail Delivery to a Set of Recipients

An SMTP mail transaction typically has the structure:

~~~text
MAIL FROM  -> sets envelope sender, starts transaction
RCPT TO    -> adds first recipient
RCPT TO    -> adds second recipient
RCPT TO    -> adds third recipient
DATA       -> begins transmitting shared message
...        -> headers and body
.          -> ends data, waits for final response
~~~

Multiple transactions can occur sequentially over **the same SMTP connection**. Therefore:

- **One SMTP connection** does not necessarily equal **one message**.
- **One SMTP transaction** can contain **multiple RCPT TO** commands.
- **One RCPT TO command** normally declares **one recipient path**, not a comma-separated list of multiple addresses.
- **One DATA** transmits the shared content for the envelope recipients accepted into that transaction.

If you want to send the same content twice independently, the client can run two separate MAIL FROM/RCPT TO/DATA transactions, even while reusing the connection.

## 3. Full SMTP Flow with Multiple RCPT TO Commands

The next example simulates an exchange between client **C** and server **S**. It intentionally omits STARTTLS/AUTH steps to keep focus on the transaction; real applications must use a secure channel and authentication as required by the provider.

~~~text
S: 220 smtp.example.org ESMTP ready

C: EHLO app.example.org
S: 250-smtp.example.org
S: 250 SIZE 52428800

C: MAIL FROM:<notify@example.org>
S: 250 2.1.0 Sender OK

C: RCPT TO:<lan@example.net>
S: 250 2.1.5 Recipient OK

C: RCPT TO:<minh@example.net>
S: 250 2.1.5 Recipient OK

C: RCPT TO:<audit@example.net>
S: 250 2.1.5 Recipient OK

C: DATA
S: 354 End data with <CRLF>.<CRLF>

C: From: notify@example.org
C: To: lan@example.net
C: Cc: minh@example.net
C: Subject: Maintenance notification
C:
C: The system will undergo maintenance at 22:00.
C: Please save your work before this time.
C: .

S: 250 2.0.0 Queued as Q12345

C: QUIT
S: 221 Bye
~~~

In the protocol transcript above, the **C:** and **S:** markers are only used to distinguish the two directions of exchange, not actual bytes sent in the SMTP session.

| Step | Meaning | Notes |
| --- | --- | --- |
| EHLO | Client introduces itself and receives the list of features advertised by the server | STARTTLS, AUTH, PIPELINING, SIZE, and extensions depend on the server |
| MAIL FROM | Starts the transaction and specifies the envelope sender | Not identical to the displayed From header |
| 1st RCPT TO | Requests the server to accept mail for Lan | Server replies individually for this address |
| 2nd RCPT TO | Requests to accept mail for Minh | Does not trigger a separate DATA |
| 3rd RCPT TO | Requests to accept mail for the audit team | Bcc address is still an envelope recipient |
| DATA | Requests switching to message content transfer mode | Server typically returns code 354 when ready to receive data |
| Headers + body + terminating dot | Transmits message content per SMTP rules | One DATA serves the set of accepted recipients |
| 250 after DATA | Server reports accepting the message for further processing | Does not yet prove the mail appeared in the inbox or was read |
| QUIT | Closes the SMTP session | Not mandatory immediately after every transaction |

### Why Repeat RCPT TO Instead of Repeating DATA?

A normal message has shared headers and body. SMTP lets the server know the target addresses upfront via a set of **RCPT TO** commands, and then receive the message content only once.

One way to visualize it:

~~~text
                MAIL FROM:<notify@example.org>
                             |
                +------------+------------+
                |            |            |
         RCPT TO Lan   RCPT TO Minh   RCPT TO Audit
                |            |            |
                +------------+------------+
                             |
                         Single DATA
                             |
                       Shared message
                             |
                 Server handles delivery
                     to each address
~~~

This reduces how many times the client must retransmit the same content, especially when the content is large. However, the server may limit the number of recipients per transaction, reject some addresses, or split processing into multiple sends internally in its infrastructure.

### When Is DATA Allowed to Start?

The client sends **DATA** after receiving replies for the RCPT TO commands according to the session's operating mode. When at least one recipient is accepted, the client can proceed to transfer the message for the accepted addresses, depending on client/library policy. If no recipient is accepted, the transaction cannot be used to deliver mail; the client usually aborts or ends the transaction appropriately.

The server signals **354** to ask the client to transmit data. Only after data ends with a dot on its own line does the server issue the final acceptance response for the message. **354 does not mean sending succeeded**; it only indicates the server is ready to receive DATA.

### Terminating Dot and Dot-Stuffing

SMTP delimits the end of content with the sequence **CRLF . CRLF**. If an actual content line starts with a dot, the client must prepend a dot when transmitting on the wire (dot-stuffing) so the server does not mistake it for the end marker. The mail-sending library handles this detail; Spring Mail developers do not manually insert dots into the body when creating a **SimpleMailMessage** or **MimeMessage**.

## 4. One RCPT TO Is One Envelope Recipient

In SMTP, the way to declare multiple recipients is to repeat the command:

~~~text
RCPT TO:<lan@example.net>
RCPT TO:<minh@example.net>
RCPT TO:<audit@example.net>
~~~

Do not write something like the following as a standard RCPT TO command containing two mailboxes:

~~~text
RCPT TO:<lan@example.net>,<minh@example.net>
~~~

Commas can appear in address lists of **To** or **Cc** headers according to header syntax, but each **RCPT TO** command takes one recipient path per SMTP protocol syntax.

The address in an RCPT TO command also does not necessarily equal the number of final people who receive the mail. One address can be:

- An individual mailbox.
- An alias routed by the server to another mailbox.
- A group/distribution list address expanded by the email system.
- An intermediate address forwarded according to provider rules.

For example, a single RCPT TO sent to group@example.net can cause downstream infrastructure to deliver the mail to many group members. Conversely, three RCPT TO commands do not guarantee three distinct final recipients, because alias/forwarding rules or deduplication depend on the system.

## 5. To, Cc, Bcc Are Headers or Display Concepts; RCPT TO Is a Transport Action

This is a common source of confusion when working with JavaMailSender.

| Component | Where does it live? | Role | Visible to regular recipients? |
| --- | --- | --- | --- |
| **MAIL FROM** | SMTP envelope | Sender address used for transport/delivery error reporting | Usually not displayed like the From header; may appear in Return-Path after delivery |
| **RCPT TO** | SMTP envelope | Specifies each recipient the server is asked to deliver the mail to | Not a directly visible header line in the message |
| **From** | Header inside DATA | Sender identity presented to the reader | Yes |
| **To** | Header inside DATA | Disclosed primary recipients | Usually yes |
| **Cc** | Header inside DATA | Disclosed copied recipients | Usually yes |
| **Bcc** | Blind carbon copy concept | Recipient still receives the mail via the envelope, but is not disclosed in To/Cc headers | Normally stripped from outgoing message headers |

### 5.1. To and Cc Both Become Envelope Recipients

If Java creates:

~~~text
To: lan@example.net
Cc: minh@example.net
~~~

then during normal sending, both Lan and Minh need to be declared for the SMTP server to process, for example:

~~~text
RCPT TO:<lan@example.net>
RCPT TO:<minh@example.net>
~~~

The server **does not distinguish delivery priority** based solely on whether a recipient is in To or Cc. Who is the primary recipient or copied recipient is header and application semantics.

### 5.2. Bcc Must Still Be Delivered Without Leaking in the Public List

If the application also sends to **audit@example.net** as Bcc, the SMTP client must still include that address in the recipient set via **RCPT TO** or the provider's equivalent mechanism.

The outgoing message normally will not contain a public Bcc line:

~~~text
From: notify@example.org
To: lan@example.net
Cc: minh@example.net
Subject: Maintenance notification
~~~

Readers of To/Cc cannot conclude from those headers that no other recipients exist. Protecting Bcc depends on the client/library removing or handling the Bcc header properly; never manually concatenate header lines and send a raw Bcc field as public content.

**Bcc protects the recipient list at the header display layer**, not as a tool guaranteeing absolute anonymity in every situation. Email systems can still record routing info in logs or operational metadata; a Bcc recipient can also expose themselves by clicking Reply All.

### 5.3. The To Header Is Not the Source of Truth for Recipient Count

It is possible to construct a message with:

~~~text
To: lan@example.net, minh@example.net
~~~

while the envelope contains only **RCPT TO:<lan@example.net>**. Without a separate delivery request for Minh, the To line by itself does not force the SMTP server to send mail to Minh.

Conversely, the envelope can contain a Bcc address that does not appear in headers at all.

Therefore, when verifying "who the mail was requested to be sent to", distinguish:

1. **The address list in the message object** that the application passed to the library.
2. **The RCPT TO commands actually sent** and the SMTP server's responses.
3. **Final delivery outcomes** from the email infrastructure.

These three datasets can differ.

### 5.4. MAIL FROM Does Not Need to Match From Either

An application can display:

~~~text
From: notifications@example.org
~~~

while the envelope uses a different address to receive delivery failure notifications:

~~~text
MAIL FROM:<bounces@example.org>
~~~

The envelope address is often tied to bounce/return-path handling. Sending domain verification, SPF, DKIM, DMARC, and provider policies can impose constraints on these identities. Do not alter the envelope sender arbitrarily just to hide the origin of the mail or bypass provider requirements.

## 6. Each RCPT TO Has Its Own Response: Not All Succeed Together

An important point when sending to multiple recipients is that **the SMTP server can accept one address and reject another within the same transaction**.

Example:

~~~text
C: MAIL FROM:<notify@example.org>
S: 250 2.1.0 Sender OK

C: RCPT TO:<lan@example.net>
S: 250 2.1.5 Recipient OK

C: RCPT TO:<minh@example.net>
S: 550 5.1.1 User unknown

C: RCPT TO:<audit@example.net>
S: 450 4.2.0 Mailbox temporarily unavailable
~~~

For the same message, the outcomes at the RCPT step are:

| Recipient | Response | Interpretation in the current transaction |
| --- | --- | --- |
| Lan | **250** | Server accepted this address at the RCPT step |
| Minh | **550** | Server rejected this address, permanent error category |
| Audit | **450** | Server temporarily rejected; may need retry per retry policy |

Commonly seen codes:

- **2xx:** success response at the current step.
- **4xx:** temporary failure; can be retried at an appropriate time.
- **5xx:** permanent failure or policy rejection; should not be retried infinitely with an unchanged request.
- **354:** server agrees to move to the DATA receiving stage, not the final outcome yet.
- **250 after DATA:** server accepted the message for subsequent delivery processing.

Exact codes and accompanying descriptions depend on the server. For instance, 550 can reflect a non-existent mailbox or a policy rejection, so you cannot look at 550 alone and assert a single certain cause.

### 6.1. What Happens When Only Some Recipients Are Accepted?

There are two layers of decision:

**SMTP server layer:** the server reported acceptance or rejection for each RCPT. If the client proceeds to send DATA successfully, the message is accepted for the valid recipients in the transaction per SMTP semantics.

**SMTP client/library layer:** the client can be configured to:

- **Continue sending to valid recipients**, while reporting errors for the rejected ones.
- **Abort or fail to complete the transaction** if any recipient is rejected, depending on sending policy and library capabilities.

These two behaviors produce different outcomes. You cannot see **250** for one RCPT and conclude the email was sent to that address: the client must still send DATA and the server must accept that phase.

An example of continuing:

~~~text
MAIL FROM -> 250
RCPT Lan  -> 250
RCPT Minh -> 550
RCPT Audit-> 450

Client chooses to continue with Lan:
DATA      -> 354
...content...
.         -> 250 queued

Result: Lan was accepted by the server for further processing;
        Minh and Audit were not accepted in this transaction.
~~~

If the client decides not to send when someone is rejected, it can abort the transaction with **RSET** and then handle the error or retry per policy. Therefore, do not infer specific client behavior solely from a sequence of RCPT codes.

### 6.2. Success at RCPT Differs from Success at DATA and Final Delivery

Three milestones must be distinguished:

1. **RCPT TO returns 250:** the server agrees to accept the address as a recipient for the transaction.
2. **DATA completes and returns 250:** the server receives the message content and takes responsibility for further processing per SMTP semantics.
3. **Mail reaches the mailbox:** the email infrastructure completes the corresponding delivery step. Forwarding, delays, bounce errors, or provider filtering may occur before the recipient actually sees the mail.

Errors arising after DATA acceptance may be reported via non-delivery notifications (bounce/DSN) or the email service's status channel, rather than appearing in the immediate response at send time.

In standard SMTP, the final response to DATA normally applies to the server **accepting the transaction's message**, not an independent per-recipient delivery report at a later point.

## 7. Practice in Spring Framework Mail: One Send, Multiple Addresses

**Spring Mail** provides APIs to build messages and send them via a transport. Developers usually declare the recipient list; the underlying mail library handles the SMTP session and RCPT TO commands.

In a Spring Boot application using SMTP, you can add the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Example configuration using **application.yml**:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

In a real environment, configure credentials via environment variables or a secrets system, such as **SPRING_MAIL_USERNAME** and **SPRING_MAIL_PASSWORD**, and verify against the provider's TLS/authentication guide. Domain names and addresses in examples are illustrative data only.

### 7.1. SimpleMailMessage: Multiple To, Cc, Bcc

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceMailService {

    private final JavaMailSender mailSender;

    public MaintenanceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void notifyMaintenance() {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setFrom("notify@example.org");
        message.setTo("lan@example.net");
        message.setCc("minh@example.net");
        message.setBcc("audit@example.net");
        message.setSubject("Maintenance notification");
        message.setText(
                "The system will undergo maintenance at 22:00.\n"
              + "Please save your work before this time."
        );

        mailSender.send(message);
    }
}
~~~

In this example:

- **setTo** specifies the primary recipient.
- **setCc** specifies the public copied recipient.
- **setBcc** specifies the hidden recipient.
- **send(message)** asks the library to send **one message object** to the declared set of recipients.

When using the SMTP transport in the standard way, the mail library extracts the appropriate recipients and declares them to the SMTP server via multiple RCPT TO commands within one transaction, if server policy and capabilities allow.

**Developers do not need to write three RCPT TO commands manually** or call **send** three times just because there are three recipients. Calling **send** three times can create three separate transactions and increase content transmissions, differing from the intent of sending one shared notification.

For multiple recipients with the same role, the APIs support declaring an array or multiple addresses:

~~~java
message.setTo(
        "lan@example.net",
        "minh@example.net"
);

message.setCc(
        "team-lead@example.net",
        "audit@example.net"
);
~~~

When reading this code, do not confuse **setTo** with the number of SMTP commands. Setting the To group once can result in multiple recipients in the envelope.

### 7.2. MimeMessageHelper: Same Principle for HTML and Attachments

When MIME/HTML or attachments are needed, Spring Mail provides **MimeMessageHelper**:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class HtmlAnnouncementService {

    private final JavaMailSender mailSender;

    public HtmlAnnouncementService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAnnouncement() throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, "UTF-8"
        );

        helper.setFrom("notify@example.org");
        helper.setTo(new String[] {
                "lan@example.net",
                "minh@example.net"
        });
        helper.setBcc("audit@example.net");
        helper.setSubject("Maintenance notification");
        helper.setText(
                "<p>The system will undergo maintenance at <b>22:00</b>.</p>",
                true
        );

        mailSender.send(message);
    }
}
~~~

What differs in **MimeMessage** is that the content can have multiple MIME parts, HTML, attachments, or inline resources. **The envelope rules remain the same:** SMTP needs to know who the recipients are via RCPT TO, while content is sent via DATA.

Note when using MIME and Bcc: let **Jakarta Mail/Spring Mail** manage recipient fields and header formatting. Manually concatenating header lines can leak Bcc or produce a malformed message.

### 7.3. Does JavaMailSender Return a Success Status per Person?

Spring Mail's **send** method is not a per-address final delivery tracking API. If the library detects an error during the send session, it may throw an exception in the **MailException** family, such as **MailSendException**. However, simply having no exception is not enough to assert that every recipient received or read the mail.

The outcome when some RCPTs are rejected also depends on the SMTP provider and Jakarta Mail sending options. For example, some Jakarta Mail implementations support the **mail.smtp.sendpartial** property to decide whether to continue sending to valid recipients when another recipient fails. You need to verify the behavior of the specific library version and server when implementing a partial-send policy; do not assume a complete per-recipient report is automatically produced in every case.

If the business requirement demands knowing which addresses were accepted, which were rejected, and which bounced later, the application must design an appropriate **feedback collection and status tracking mechanism**, possibly through SMTP errors, the provider's event/bounce API, or a dedicated sending system.

## 8. One Message with Multiple RCPT TO vs. Multiple Separate Messages?

Both choices start with the same initial group of recipients, but their practical impacts differ.

### 8.1. One Shared Message Sent to Multiple Recipients

~~~text
Transaction 1:
MAIL FROM:<notify@example.org>
RCPT TO:<lan@example.net>
RCPT TO:<minh@example.net>
RCPT TO:<audit@example.net>
DATA
Shared notification
.
~~~

Characteristics:

- Shared headers/body for the recipient group in the transaction.
- Reduces repeated content transmission from client to SMTP server.
- Shares the same subject, attachments, and message.
- Requires handling partial acceptance or server recipient limits.
- Risks exposing a public list if multiple addresses are placed in To/Cc when recipients should not see each other.

### 8.2. Multiple Messages, One Recipient per Message

~~~text
Transaction 1:
MAIL FROM:<notify@example.org>
RCPT TO:<lan@example.net>
DATA
Hello Lan, ...
.

Transaction 2:
MAIL FROM:<notify@example.org>
RCPT TO:<minh@example.net>
DATA
Hello Minh, ...
.
~~~

Characteristics:

- Can personalize each message's name, link, language, or attachment.
- Easy to attach a separate business delivery status to each address.
- Uses more transactions and content transfers.
- Enables individual control over retries and data policies per recipient.

A bulk-mailing application typically chooses a group or individual strategy depending on the problem, privacy policy, service limits, and tracking capabilities. For emails containing private information, personal login links, or confirmation tokens, **never use a single shared content for everyone** just to reduce the number of transactions.

### 8.3. Comparison Table

| Criterion | One message, multiple RCPT TO | Multiple messages or multiple transactions |
| --- | --- | --- |
| Number of DATA transfers | Usually once in the transaction at hand | Each transaction has its own DATA |
| Content for recipients | Shared | Can vary |
| Personalized information | Limited | Flexible |
| Privacy | Must design To/Cc/Bcc carefully | Easy to avoid exposing recipient list via headers |
| Error at RCPT | Only a subset of recipients might be rejected | Can handle per transaction |
| Business observability | Requires tracking status per recipient | Usually easier to tie each send request to each recipient |
| Suitable use cases | Internal general announcements or groups permitted to see each other | OTPs, verifications, personal documents, personalized notifications |

Sending the same content multiple times does not guarantee "one transaction per person" if the library or provider API applies batching. When exact behavior is required, verify the contract of the transport or provider.

## 9. Practical Limits When Increasing Recipient Count

A message can have multiple RCPT TO commands, but **that does not mean you can declare unlimited recipients**.

### 9.1. Server Recipient Limits

An SMTP server can enforce recipient limits per message, per sending session, per account, or per time window. When exceeding the threshold, the server may temporarily reject some RCPT TO commands, return a code such as **452**, or apply another throttling policy.

Example:

~~~text
C: RCPT TO:<user1@example.net>
S: 250 OK
C: RCPT TO:<user2@example.net>
S: 250 OK
C: RCPT TO:<user3@example.net>
S: 452 Too many recipients
~~~

In this case, do not arbitrarily infer a universal limit number for all SMTP servers. Read the documentation and actual responses of the service being used. Some servers require the client to complete the message for the accepted batch and then open another transaction for the rest.

### 9.2. PIPELINING Does Not Change the Meaning of RCPT TO

If the server advertises the **PIPELINING** extension, the client can send several commands back-to-back without waiting for an individual reply after each command under the extension's rules. This reduces round-trip latency.

However, at the semantic level there are still **multiple distinct RCPT TO commands** and the server still needs to provide corresponding responses. PIPELINING does not turn multiple recipients into a single address string in one command, nor does it strip meaning from each recipient's reply.

### 9.3. One Large DATA Still Must Obey Size Limits

If the mail has a large attachment, one DATA serving multiple recipients can help reduce data sent from the client. Yet the server still enforces a message size limit, such as advertised via the **SIZE** extension. Multiple recipients do not multiply DATA size exponentially on the sending side, but neither do they exempt the message from any message size limit, quota, or content filtering.

### 9.4. Batching When Sending in Large Volumes

If you need to send to many addresses, the application can split them into small batches fitting service quotas. When batching, each batch is usually a separate SMTP transaction; each batch can fail or be accepted at different times.

Application design should persist:

- The intended recipient list.
- Message ID or business event ID.
- Recipients accepted by the transport or provider.
- Recipients temporarily rejected, permanently rejected, or with unknown outcomes.
- Retry info and downstream delivery feedback if available.

Do not update all recipients to **Sent** status just because the initial message object contained multiple addresses and the send method was called.

## 10. Handling Retries Without Inadvertently Sending Duplicates

Suppose the server accepted the message for Lan and Minh, but the connection dropped before the client received the **250 after DATA** response. The client cannot be certain whether the server accepted the message. Automatically resending to the entire recipient set risks generating duplicate emails.

SMTP does not provide applications with a general guarantee that every message arrives exactly once per recipient.

Useful design principles:

1. **Distinguish known from unknown outcomes:** having received an RCPT/DATA reply differs from losing connection before receiving a reply.
2. **Record status per recipient:** avoid collapsing the whole group into a single simplistic state.
3. **Selective retry:** temporarily rejected recipients can be retried with backoff; permanently rejected recipients need root-cause inspection before retrying.
4. **Do not treat code 250 as proof the recipient read the mail:** bounces or downstream infrastructure filtering can still happen.
5. **Include a business correlation ID:** use an event/batch ID to reconcile logs and service responses. The Message-ID header is helpful for locating mail, but on its own it does not make SMTP idempotent.
6. **Bound resends:** apply durable queues, processing state, and retry policies; if the provider supports its own idempotency mechanism, follow its contract.

Example with three recipients:

~~~text
recipient                 known status at application
--------------------------------------------------------
lan@example.net           DATA accepted (if response received)
minh@example.net          RCPT rejected: 550
audit@example.net         RCPT temp rejected: 450
~~~

The application can put Audit into the retry list, handle Minh's rejection reason, and avoid resending to Lan just because Audit failed. However, if Lan's outcome is truly indeterminate due to a connection drop, the design must have a policy for resolving uncertain situations and accept that duplicate risk remains.

## 11. Practical Observation: What to Look For in SMTP Logs?

In a development environment or test SMTP system, protocol conversation logs can help understand why a message has multiple recipients. When inspecting at the protocol layer, identify:

~~~text
MAIL FROM: ...
RCPT TO: ...
RCPT TO: ...
RCPT TO: ...
DATA
354 ...
...
250 ...
~~~

Notes on reading logs:

- **How many RCPT TO commands?** This is the number of recipient declaration commands in the observed transaction, not necessarily the total final recipients after alias/list expansion.
- **What reply did each RCPT receive?** 250 at RCPT differs from 250 after DATA.
- **Was there DATA or did the client abort?** An RCPT returning 250 is not enough to conclude a message was handed over.
- **Is there a new transaction?** A subsequent MAIL FROM command can start a new message on the same connection.
- **Does Bcc appear in headers?** In a normal send flow, Bcc addresses should appear via the envelope without being exposed in headers of the received message.

SMTP debug logs can contain addresses, metadata, and sometimes sensitive content or authentication data if logging is configured insecurely. Only enable debug mode when needed, protect logs, mask sensitive data, and disable it after diagnosis.

### Common Misconceptions

**Misconception 1: "An email with three recipients requires calling send three times."**

Not necessarily. One SMTP transaction can declare three RCPT TO commands and share one DATA.

**Misconception 2: "Adding three addresses in the To header means the server will send to all three."**

No. The server is instructed to deliver via envelope recipients; To/Cc headers have separate display semantics.

**Misconception 3: "If Bcc is not in the header, there is no Bcc recipient."**

No. A Bcc recipient must be declared in the envelope even though their identity is not disclosed in headers seen by recipients.

**Misconception 4: "If one RCPT fails, all recipients fail."**

That cannot be concluded. SMTP replies individually for each RCPT; the client decides whether to finish sending for the valid set or abort the transaction, depending on configuration and policy.

**Misconception 5: "The SMTP server returned 250 so every recipient can read the mail."**

No. 250 is acceptance at one protocol stage; final delivery and reading behavior are separate outcomes.

**Misconception 6: "You can put a comma-separated address list into one RCPT TO."**

That is invalid standard RCPT TO syntax. Use one command per recipient path or let the mail-sending library handle the address list.

## 12. Putting This Knowledge in the Spring Framework Mail Context

When writing a feature to send a notification to multiple people in a Spring application, the mental model can be:

~~~text
Business input
    |
    v
Determine recipient group and address visibility
    |
    +--> To/Cc: can be disclosed in message headers
    |
    +--> Bcc: needs delivery without disclosure in headers
    |
    v
Create SimpleMailMessage or MimeMessage
    |
    v
JavaMailSender.send(...)
    |
    v
Jakarta Mail / SMTP transport
    |
    +--> MAIL FROM
    +--> RCPT TO for recipient 1
    +--> RCPT TO for recipient 2
    +--> RCPT TO for recipient N
    +--> DATA containing shared content
    |
    v
SMTP server accepts/rejects step by step
    |
    v
Track send and delivery outcomes per application requirements
~~~

For general announcements, one message with multiple recipients is the natural choice. For personalized content or requirements to isolate visibility, consider creating separate messages per person. In both cases, Spring Mail helps build and send the message, while server acceptance, rejection, deferral, or delivery must be understood through the corresponding SMTP milestones.

A multi-recipient message is the classic example of the boundary between **message content** and **transport envelope**: **one DATA can serve multiple RCPT TO commands**, each RCPT is checked individually, and message acceptance is only one step in the email delivery process.
