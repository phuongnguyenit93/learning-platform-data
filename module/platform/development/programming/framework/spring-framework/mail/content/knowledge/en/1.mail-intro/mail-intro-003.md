# Roles of the Application, Mail Client, MTA, MDA, and Mailbox

When a Spring application sends a registration confirmation, password reset, or order notification email, the send statement in Java only initiates a process involving multiple components. For a message to appear in the recipient's mailbox, we must distinguish the **application**, **mail client**, **Mail Submission Agent (MSA)**, **Mail Transfer Agent (MTA)**, **Mail Delivery Agent (MDA)**, and **mailbox**. Each component has a different boundary of responsibility.

The goal of this lesson is to understand the flow of sending, relaying, delivering, and reading email; recognize the protocols at each hop; and determine precisely what **Spring Framework Mail** does in the system.

## 1. The Big Picture

Suppose an e-commerce application sends a message from `orders@shop.example` to `customer@example.net`:

```text
  SENDING SIDE                                           RECEIVING SIDE

 [Spring application]                                   [Mail client]
 [or mail client]                                     (mobile/webmail)
        |                                                    ^
        | 1. SMTP submission                                 | 6. IMAP/POP3
        v                                                    |
 [Sending MSA / MTA]                                  [Recipient mailbox]
        |                                                    ^
        | 2. DNS MX lookup, SMTP relay                       | 5. Store message
        v                                                    |
 [Recipient domain MTA] --- 3. Receive, route -----> [MDA / delivery service]
                                                     |
                                                     +-- 4. Filter, classify
```

The diagram depicts **logical roles**, not claiming that each box is a physical server. Several roles can run together in one product or be distributed across services. A message can also pass through multiple intermediate MTAs.

| Component | Other name | Primary responsibility | Stores final message? |
| --- | --- | --- | --- |
| **Application** | Application | Generates content, decides recipients, timing, and send request | Usually no |
| **Mail client** | Mail User Agent (MUA) | User interface to compose, send, read, and manage email | May keep a local copy, not necessarily the canonical store |
| **MSA** | Mail Submission Agent | Receives messages from an application/MUA, checks authentication and sending permissions | No |
| **MTA** | Mail Transfer Agent | Routes and relays emails between servers, manages queues and retries | Not the recipient's mailbox |
| **MDA** | Mail Delivery Agent | Performs final delivery into the mail store, may coordinate filtering and classification | Writes message into storage |
| **Mailbox** | Mailbox | Storage repository for emails and metadata of an account or destination | **Yes** |

Four actions need to be separated: **submission**, **transfer/relay**, **final delivery**, and **retrieval/access**. The phrase "sent successfully" may refer only to completing the first action.

## 2. Application: Where the Need to Send Email Originates

The application decides **why**, **when**, **to whom**, and **what content** to send. For example, a Spring service receives an order-confirmed event, determines the recipient address, builds the subject and plain-text/HTML body, and requests sending.

In Spring Framework Mail, the `JavaMailSender` interface helps the application construct and submit messages over a transport mechanism, typically **SMTP**. Here the application acts as an **automated mail client**: instead of a user clicking "Send", the program proactively dispatches the message.

Two common integration approaches:

- **SMTP submission:** the application connects to the organization's or email provider's SMTP server.
- **Provider HTTP API:** the application calls a mail-sending API; the provider handles delivery across the subsequent layers.

The application may store logs or send statuses in its own database for business purposes. Doing so does not turn the application's database into the recipient's mailbox. Similarly, an application can process incoming email if it additionally implements receiving/reading capabilities, but **email sending in Spring Mail does not by itself provide an MTA, MDA, or mailbox**.

## 3. Mail Client (MUA): The User Tool for Composing and Reading Mail

A **Mail User Agent (MUA)** is software such as Outlook, Thunderbird, a mobile Mail app, or a webmail interface. It allows users to compose messages, manage folders, search, reply, and read email.

A mail client typically communicates in two directions:

1. **Sending path:** submits the message to a submission server, commonly over SMTP.
2. **Reading path:** accesses the mailbox via IMAP, POP3, or a webmail service's proprietary interface/API.

A mail client may keep copies of emails for offline reading. With IMAP, many clients commonly synchronize messages, folders, and read status with the mail store on the server. As a result, a user can switch from a phone to a browser and still see the same mailbox.

Comparing three cases:

| Case | Who issues the send command? | Who lets the recipient read the message? |
| --- | --- | --- |
| User sends via Outlook | Outlook, acting as an MUA | Outlook or another MUA |
| Spring website sends a confirmation link | Spring application, acting as an automated client | Recipient's mail client |
| User sends/reads via webmail | Webmail interface and backend services | Webmail interface |

An automated email-sending application **does not need** to implement a compose UI or IMAP just to send notifications.

## 4. MSA and MTA: Accepting and Relaying Messages

### 4.1. MSA Accepts Messages Submitted by Clients

A **Mail Submission Agent (MSA)** is the entry point for an application or mail client. It may require SMTP authentication, check the sender address, and enforce quotas and anti-abuse policies.

In configuration guides, an MSA is often referred to generally as an "SMTP server". Submission commonly uses **port 587 with STARTTLS**, or **port 465 with TLS established upon connection**. The actual provider dictates which port and authentication mechanisms are supported.

### 4.2. MTA Transports Messages Across Domains

A **Mail Transfer Agent (MTA)** receives a message and decides which system to relay it to. When sending to `customer@example.net`, the sending MTA typically:

1. Identifies the recipient domain `example.net` from the destination address.
2. Queries **MX (Mail Exchanger)** records in DNS to find the mail-receiving servers for that domain.
3. Connects via SMTP to the destination MTA, or an intermediate server according to configured routing.
4. Relies on SMTP responses to determine whether the message was accepted, must wait for retry, or was rejected.

An MX record specifies the **domain-level mail receiving destination**, not a personal folder path. SMTP between MTAs normally uses **port 25**. MSA and MTA can be two separate services or reside within the same system.

MTAs typically maintain a **queue**. On a temporary destination failure—such as being unreachable or returning a `4xx`-series SMTP code—the MTA can wait and retry according to policy. Permanent errors, usually in the `5xx` range, or expired retry limits may lead to a **bounce / Delivery Status Notification (DSN)**.

For example, Postfix and Exim can fulfill the MTA role; managed SMTP services also perform this transport role even though the user does not operate the servers.

**Core distinction:** an MSA accepts messages *from a client for outbound sending*; an MTA handles *transport between email systems*. An SMTP server responding "accepted" only indicates it accepted the message at that hop.

## 5. MDA: Final Message Delivery

After the recipient domain's MTA accepts a message, the receiving infrastructure must map the recipient address to a mail store. This role belongs to the **Mail Delivery Agent (MDA)** or an equivalent final-delivery service.

Depending on system architecture, an MDA may:

- Map the recipient address, aliases, and forwarding rules to the target mailbox.
- Coordinate spam filters, blocking policies, quarantine, and classification.
- Write the message along with metadata into the mail store, placing it in Inbox, Spam, or an appropriate folder.
- Report the result to the delivery system.

An MTA can hand off messages internally through local delivery or **LMTP (Local Mail Transfer Protocol)**. In many large systems, the MDA does not appear as a standalone process with that exact name: the delivery function is implemented across multiple services.

**The MTA answers "which server should this go to?", while the MDA answers "which mailbox should this be delivered to and how should it be stored?"**. A non-existent mailbox may be detected immediately by the MTA or later during local delivery, depending on how the system is built.

## 6. Mailbox: The Recipient's Mail Repository

A **Mailbox** is the logical repository of delivered messages, usually containing folders such as Inbox, Spam, Sent, Drafts, and Trash. It can also store read states, flags, labels, and metadata.

| Concept | Example | Meaning |
| --- | --- | --- |
| **Email address** | `customer@example.net` | Routing identity used by the sender |
| **User account** | Mail service login account | Permission to access email resources |
| **Mailbox** | Mail store with Inbox/Spam/… | Where delivered messages and their states are stored |

An email address and a mailbox should not be assumed to be one-to-one. Multiple **aliases** can point to one mailbox; a group address can distribute to many people; a forwarding address might not have its own mailbox.

**A mailbox is not a mail client:** a mailbox is the storage place; a mail client is the access tool. Switching phones or mail-reading apps does not automatically make the mailbox on the server disappear.

## 7. Which Protocols Sit at Each Hop?

| Protocol | Common connection | Function | Common ports |
| --- | --- | --- | --- |
| **SMTP submission** | Application/MUA → MSA | Submit messages for sending | 587 (STARTTLS), 465 (implicit TLS) |
| **SMTP relay** | MTA → MTA | Relay messages between servers | 25 |
| **LMTP** | MTA → delivery service | Deliver messages into storage system | Implementation-dependent |
| **IMAP** | MUA → mailbox service | Read and synchronize messages/folders/states | 143 (optional STARTTLS), 993 (TLS) |
| **POP3** | MUA → mailbox service | Download messages in a simpler model than IMAP | 110 (optional STARTTLS), 995 (TLS) |
| **HTTP(S) API / webmail** | App → provider; browser → webmail | Submit messages via API or use webmail | Usually 443 |

**SMTP handles sending/relaying; IMAP and POP3 handle accessing stored messages.** Spring Mail with `JavaMailSender` primarily supports the sending side.

**STARTTLS** upgrades an existing connection to TLS; **implicit TLS** establishes TLS immediately upon connecting. TLS protects each corresponding transport hop and does not automatically guarantee end-to-end encryption between two users.

## 8. Detailed Journey of an Email

Consider an "Order confirmed" email from `orders@shop.example` to `customer@example.net`.

**Step 1 – Create the message.** The application determines recipients, subject, body, and optionally HTML/attachments. **MIME** supports representing multipart messages and attachments; MIME describes content formatting and is not responsible for delivery.

**Step 2 – Submit to the MSA.** `JavaMailSender` connects to the configured submission server, authenticates if required, and submits the message over SMTP. If submission succeeds, that server takes responsibility for further processing; there is not yet proof that the email reached the recipient.

**Step 3 – MTA relays.** The MTA routes based on the recipient address, typically using DNS MX. The message may pass through multiple hops or queues upon transient errors.

**Step 4 – Receiving system processes.** The destination MTA checks receiving policies, addresses, anti-spam filters, and other conditions. The message may be accepted or rejected.

**Step 5 – MDA delivers.** The final delivery service maps the address to a mailbox and stores the message, potentially placing it in Inbox or Spam. If undeliverable, the system may generate an error response or bounce depending on when it was detected.

**Step 6 – Mail client reads.** The recipient opens a phone, desktop app, or webmail. This access may occur via IMAP/POP3 or internal APIs and is a separate process from the SMTP session executed by the application.

```text
Application creates message
         |
         v
Submit to SMTP server ---- connection/auth error ---> application handles send failure
         |
         v
Sending server accepts
         |
         +---- temporary relay error --------> MTA queue / retry
         |
         +---- permanent error --------------> bounce / DSN (if any)
         |
         v
Receiving system delivers to mailbox
         |
         v
Recipient views via mail client
```

Because steps span multiple systems, one cannot infer **delivered**, **landed in Inbox**, **opened**, or **read** merely from a send method returning normally. If delivery tracking is needed, use delivery/bounce statuses and events provided by the infrastructure.

## 9. SMTP Envelope vs. Message Headers

SMTP has **envelope** information for routing, whereas email content has **message headers** and a **body** for the reader.

| Component | Example | Role |
| --- | --- | --- |
| SMTP `MAIL FROM` | `bounce@shop.example` | Return address when the message cannot be delivered |
| SMTP `RCPT TO` | `customer@example.net` | Recipient address that SMTP needs to deliver to |
| Header `From:` | `Shop <orders@shop.example>` | Sender displayed in the email |
| Header `To:` | `customer@example.net` | Recipient displayed in the email |
| Header `Subject:` | `Order confirmed` | Subject line |
| Body / MIME parts | Text, HTML, attachment | Content of the message |

These two groups of addresses are related, but not always identical. **Bcc** recipients may appear in the SMTP envelope without appearing in the displayed recipient headers. The `Return-Path` header typically reflects the envelope sender after the message is delivered.

Simplified example:

```text
SMTP envelope:
  MAIL FROM:<bounce@shop.example>
  RCPT TO:<customer@example.net>

Message:
  From: Shop <orders@shop.example>
  To: customer@example.net
  Subject: Order confirmed
  MIME-Version: 1.0
  Content-Type: text/plain; charset=UTF-8

  Your order has been confirmed.
```

From this distinction, sender-domain verification mechanisms can be understood at a high level: **SPF** checks whether the sending server is authorized for the relevant SMTP identity; **DKIM** verifies a cryptographic signature over signed parts of the message; **DMARC** relies on authentication results and domain alignment with the `From` header to apply policy. They help reduce spoofing, though they do not guarantee every valid message will land in the Inbox.

## 10. Where Does Spring Framework Mail Sit?

```text
Business service
       |
       | Build content, choose recipients
       v
JavaMailSender (Spring Framework)
       |
       | Jakarta Mail + SMTP configuration
       v
SMTP submission (MSA)
       |
       v
MTA  -->  MDA  -->  Mailbox  -->  Recipient mail client
```

`JavaMailSender` is Spring's mail-sending API. `SimpleMailMessage` is used for simple plain-text messages; `MimeMessage` with `MimeMessageHelper` supports HTML, multipart content, and attachments.

### Example: Sending a Plain-Text Email with Spring Boot

Add the dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

In `application.yml`, for an SMTP server supporting STARTTLS on 587:

```yaml
spring:
  mail:
    host: ${MAIL_HOST}
    port: ${MAIL_PORT:587}
    username: ${MAIL_USERNAME}
    password: ${MAIL_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM_ADDRESS}
```

The environment variables are supplied by the deployer. Port, TLS, and authentication configuration must match the actual provider; do not store real passwords in source code.

Service using `JavaMailSender`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {
    private final JavaMailSender mailSender;
    private final String fromAddress;

    public OrderMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendOrderConfirmed(String recipient, String orderId) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom(fromAddress);
        mail.setTo(recipient);
        mail.setSubject("Order confirmed");
        mail.setText("Order " + orderId + " has been confirmed.");

        mailSender.send(mail);
    }
}
```

When `mailSender.send(mail)` finishes without throwing an exception, the application knows its interaction with the configured sending mechanism has completed. It **does not confirm** that the MDA has written to the Inbox or that the user has read the message.

The snippet above uses **Spring Boot**, where `spring-boot-starter-mail` and `spring.mail.*` properties create the bean via auto-configuration. If using **plain Spring Framework**, you need to declare a `JavaMailSender` implementation along with the Jakarta Mail dependency and configure the corresponding bean.

### When HTML and Attachments Are Needed

`SimpleMailMessage` is suitable for text content. For HTML, create a `MimeMessage`:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendHtml(JavaMailSender sender, String from, String to)
        throws MessagingException {
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
    helper.setFrom(from);
    helper.setTo(to);
    helper.setSubject("Welcome");
    helper.setText("<h1>Welcome!</h1><p>Account created.</p>", true);
    sender.send(message);
}
```

To add attachments, you can use a `MimeMessageHelper` constructor with multipart mode enabled and then call `addAttachment(...)`. Even though the content is more complex, **the SMTP/MTA/MDA/mailbox transport path remains unchanged**.

## 11. When an Error Occurs, Which Component Should You Inspect?

| Symptom | Where to check | Meaning |
| --- | --- | --- |
| Cannot connect to SMTP | Application ↔ MSA | Host, port, network, TLS, or server |
| SMTP rejects authentication | MSA | Account, sending permissions, or authentication method |
| Send command succeeds, but message is missing | MTA, filters, MDA, and mailbox | Queue, retry, bounce, Spam, or receiving-side block |
| Recipient address reported invalid | Receiving-side MTA/MDA | Mailbox does not exist, wrong address, or blocked by policy |
| Webmail shows message, but phone does not | Mail client/IMAP/sync | Issue accessing stored messages |
| One notification is sent multiple times | Application and retry mechanism | Possible duplicate sending on retry without state control |

At least two observation milestones should be distinguished: **the submission server accepted the message** and **the receiving system confirmed delivery or rejection**. If the provider supports message IDs, delivery events, or bounce events, they can be correlated with each business request.

In real operations, pay attention to:

- Keep credentials in secrets or environment variables; use TLS according to the configuration supported by the SMTP server.
- Only use authorized sender addresses; configure SPF/DKIM/DMARC according to provider guidelines.
- Design bounded retries, duplicate-send prevention, and status tracking if business requirements demand reliability.
- Consider a business queue so HTTP requests are not prolonged by slow or disrupted SMTP.
- Respect sending rate limits and anti-spam policies of the email service.

## 12. Common Misconceptions

**"Spring sending mail means Spring is a mail server."** Spring Mail provides an API to construct and submit messages. MSA/MTA/MDA/mailbox infrastructure still has to exist somewhere.

**"MTA and MDA are the same thing."** They may reside in the same product, but an MTA relays between systems; an MDA performs final delivery into a mail store.

**"An email address is the mailbox itself."** An address is used for routing. Aliases, groups, and forwarding can cause multiple addresses to point to the same mailbox or one address to distribute to multiple destinations.

**"SMTP is used to view the Inbox."** SMTP handles sending/relaying; reading normally uses IMAP/POP3 or a webmail service.

**"SMTP returning success means the recipient has read it."** A success response only confirms acceptance at that SMTP hop. Receiving, classifying, displaying, and reading are separate steps.

**"An application needs to connect directly to port 25 on every destination server."** An application normally submits messages to an authorized submission endpoint; the sending infrastructure handles subsequent routing and relaying.

## 13. Self-Check Scenarios

**Scenario A:** A user clicks "Forgot password". Spring calls `send()` successfully, but the email is not visible yet. What can be concluded?

> The application has completed submission through the configured mechanism. Next, check MTA transfer status, bounces, receiving-side filters, Spam, and mail client synchronization. It cannot yet be claimed that the email reached the Inbox.

**Scenario B:** A user switches from Outlook to webmail and still sees their messages. Why?

> A mail client is an access tool, whereas the mailbox is normally stored on the server system. Multiple clients can access the same mailbox.

**Scenario C:** The receiving domain has an active MTA, but the recipient address does not exist. Who detects this?

> The MTA can reject it during the SMTP session if it performs address verification. In other systems, the final delivery service/MDA detects it after the MTA accepts the message, leading to an error state or bounce depending on the mechanism.

## 14. Remember by Responsibility Boundaries

When analyzing any email feature in Spring, ask in turn:

1. **Application/mail client:** what email does it create, for whom, and where does it submit?
2. **MSA:** does it accept the send request and authenticate the sender?
3. **MTA:** how does it route, relay, and retry?
4. **MDA:** which mailbox does it deliver to and what storage policies does it apply?
5. **Mailbox/mail client:** how does it store and display the message to the recipient?

Separating these five boundaries helps you use `JavaMailSender` in its proper role and accurately explain the difference between "message submitted", "delivered to mailbox", and "recipient read it".
