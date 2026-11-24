# Sending Multiple Messages and Reusing the Sender

## 1. The Multi-Email Sending Problem in Spring Framework Mail

A Spring Boot application may need to send one order confirmation email, hundreds of result notifications, or a scheduled notification batch. If it creates new SMTP configuration and connections for **every single** email, the application wastes time on TCP/TLS handshakes, SMTP authentication, and connection overhead. If it lumps everything into one huge send call, the application may hit rate limits, memory pressure, and difficulty handling partial failures.

In **Spring Framework Mail**, distinguish two optimization techniques:

1. **Reusing JavaMailSender**: services share a single pre-configured Spring sender bean.
2. **Sending multiple messages in one call**: passing an array or varargs to `send` so the library has an opportunity to reuse the SMTP connection within the batch.

Reusing **the sender object** does not mean keeping an **SMTP connection** open forever. Conversely, batching multiple messages can save connections without requiring the application to manage Transport itself.

~~~text
Business logic / scheduled job / worker
                   |
                   v
          Spring Mail service
                   |
           List of messages
                   |
                   v
        JavaMailSender (Spring bean)
                   |
            send(message[])
                   |
                   v
        Jakarta Mail SMTP Transport
          |         |         |
         msg 1     msg 2     msg 3
          |         |         |
          +---------+---------+
                    |
               SMTP server
                    |
               SMTP queue / relay
                    |
            Recipient mail servers
~~~

Spring Mail acts as the application's **SMTP client**. It does not provide a durable queue by itself merely from sending multiple messages, and a successful `send` call is not proof that recipients opened the emails.

## 2. Overloads for Sending One or Multiple Messages

**JavaMailSender** extends the **MailSender** interface and supports MIME messages via Jakarta Mail.

| API | Data type | When to use? |
|---|---|---|
| **send(SimpleMailMessage message)** | One plain-text message | Text-only notification |
| **send(SimpleMailMessage... messages)** | Multiple plain-text messages | Batch sending text notifications |
| **send(MimeMessage message)** | One prepared MIME message | Emails with HTML, attachments, inline images |
| **send(MimeMessage... messages)** | Array of MIME messages | Sending multiple pre-built MIME messages |
| **send(MimeMessagePreparator preparator)** | Callback preparing one MIME message | Decoupling MIME construction from sending |
| **send(MimeMessagePreparator... preparators)** | Multiple MIME preparation callbacks | Building and sending multiple messages via callbacks |

Corresponding invocations:

~~~java
mailSender.send(firstSimpleMessage);
mailSender.send(firstSimpleMessage, secondSimpleMessage);

mailSender.send(firstMimeMessage);
mailSender.send(new MimeMessage[] {
        firstMimeMessage, secondMimeMessage
});

mailSender.send(firstPreparator, secondPreparator);
~~~

Because overloaded methods share the same name with different parameter types, declare variable types clearly to avoid ambiguity among SimpleMailMessage, MimeMessage, and MimeMessagePreparator.

### Multiple Recipients in One Message vs. Multiple Messages

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setTo("alice@example.net", "bob@example.net");
message.setSubject("Shared announcement");
message.setText("A shared message.");
mailSender.send(message);
~~~

This is **one message with two recipients**. On the other hand:

~~~java
SimpleMailMessage alice = new SimpleMailMessage();
alice.setTo("alice@example.net");
alice.setSubject("Hello Alice");
alice.setText("A message for Alice.");

SimpleMailMessage bob = new SimpleMailMessage();
bob.setTo("bob@example.net");
bob.setSubject("Hello Bob");
bob.setText("A message for Bob.");

mailSender.send(alice, bob);
~~~

These are **two independent messages**. They can be personalized, tracked individually for outcomes, and avoid exposing other recipients' addresses. Do not replace separate individual emails by putting everyone into To/CC when content or privacy requirements differ.

## 3. Sending Multiple SimpleMailMessages in a Single Call

For text notifications, you can build an array of **SimpleMailMessage** objects and send them together:

~~~java
import java.util.List;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class TextNotificationService {
    private final JavaMailSender mailSender;

    public TextNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotifications(List<Notice> notices) {
        SimpleMailMessage[] messages =
                new SimpleMailMessage[notices.size()];

        for (int i = 0; i < notices.size(); i++) {
            Notice notice = notices.get(i);
            SimpleMailMessage message = new SimpleMailMessage();
            message.setFrom("notifications@example.com");
            message.setTo(notice.recipient());
            message.setSubject("Account notification");
            message.setText(notice.body());
            messages[i] = message;
        }

        mailSender.send(messages);
    }

    public record Notice(String recipient, String body) {
    }
}
~~~

Each iteration creates **a new SimpleMailMessage**. Never reuse the same mutable message and place multiple references to it into the array:

~~~java
// Wrong in intent: both elements reference the exact same object.
SimpleMailMessage reused = new SimpleMailMessage();
SimpleMailMessage[] wrong = new SimpleMailMessage[2];

reused.setTo("alice@example.net");
wrong[0] = reused;
reused.setTo("bob@example.net");
wrong[1] = reused;

// Both wrong[0] and wrong[1] now hold the last recipient.
~~~

If messages share common content, you can use the copy constructor:

~~~java
SimpleMailMessage template = new SimpleMailMessage();
template.setFrom("notifications@example.com");
template.setSubject("Status update");

SimpleMailMessage aliceMessage = new SimpleMailMessage(template);
aliceMessage.setTo("alice@example.net");
aliceMessage.setText("Hello Alice.");

SimpleMailMessage bobMessage = new SimpleMailMessage(template);
bobMessage.setTo("bob@example.net");
bobMessage.setText("Hello Bob.");

mailSender.send(aliceMessage, bobMessage);
~~~

The template acts as a configuration source, while each copy holds independent content. Never mutate the template from multiple threads while using it to build batches.

## 4. Sending Multiple MimeMessages with HTML or Attachments

HTML emails and attachments use **MimeMessage** and are usually built with **MimeMessageHelper**. Each email needs its own MimeMessage.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class HtmlNotificationService {
    private final JavaMailSender mailSender;

    public HtmlNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcomeMessages(List<Recipient> recipients)
            throws MessagingException {
        MimeMessage[] messages = new MimeMessage[recipients.size()];

        for (int i = 0; i < recipients.size(); i++) {
            Recipient recipient = recipients.get(i);
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper = new MimeMessageHelper(
                    message, false, StandardCharsets.UTF_8.name());
            helper.setFrom("welcome@example.com");
            helper.setTo(recipient.email());
            helper.setSubject("Welcome!");
            helper.setText(
                    "<p>Welcome, " + escapeHtml(recipient.displayName())
                            + ".</p>",
                    true);

            messages[i] = message;
        }

        mailSender.send(messages);
    }

    private static String escapeHtml(String value) {
        return value
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }

    public record Recipient(String email, String displayName) {
    }
}
~~~

In this example, **false** in the MimeMessageHelper constructor means no multipart is needed for a simple HTML body. When attachments or multiple MIME parts are required, pick the appropriate multipart mode.

Example of a MIME message with an attachment:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("reports@example.com");
helper.setTo("recipient@example.net");
helper.setSubject("Monthly report");
helper.setText("Please find the attached report.");
helper.addAttachment(
        "report.pdf",
        new org.springframework.core.io.FileSystemResource(
                "/var/reports/report.pdf"));

mailSender.send(message);
~~~

To send multiple emails with attachments, construct each MimeMessage individually and add it to the array. Source resources or files must remain readable while Jakarta Mail serializes the emails. If one send call contains many large files, watch open file descriptors, memory usage, and I/O time.

**MimeMessage is a mutable object and must not be shared and mutated concurrently across threads.** JavaMailSender can be reused as the sending component, while message content must be created and managed per operation.

## 5. Using MimeMessagePreparator for Multiple Messages

**MimeMessagePreparator** is a callback configuring a MimeMessage supplied by the sender. This helps separate content-building logic from the send operation.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;
import org.springframework.stereotype.Service;

@Service
public class ReminderMailService {
    private final JavaMailSender mailSender;

    public ReminderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReminders(List<Reminder> reminders) {
        MimeMessagePreparator[] preparators = reminders.stream()
                .map(reminder -> (MimeMessagePreparator) mimeMessage -> {
                    MimeMessageHelper helper = new MimeMessageHelper(
                            mimeMessage,
                            false,
                            StandardCharsets.UTF_8.name());
                    helper.setFrom("reminders@example.com");
                    helper.setTo(reminder.recipient());
                    helper.setSubject("Upcoming deadline");
                    helper.setText(reminder.text(), false);
                })
                .toArray(MimeMessagePreparator[]::new);

        mailSender.send(preparators);
    }

    public record Reminder(String recipient, String text) {
    }
}
~~~

Advantages: no need to call createMimeMessage in the outer loop code; the callback works on a fresh message, making complex MIME assembly clean; multiple callbacks can be grouped into one send call.

However, **a callback is not a durable job queue**. It runs on the sending thread; if message preparation fails, Spring Mail may throw **MailPreparationException**. Data captured by the callback must remain stable until the callback runs. Never capture a reference to a mutable object being modified by another thread.
## 6. Reusing JavaMailSender in a Spring Container

Normally, an application configures one **JavaMailSender** as a **singleton Spring bean**. Different services use constructor injection to receive the same sender:

~~~text
                 Spring ApplicationContext
                            |
                   JavaMailSender bean
                      (SMTP config)
                       /        \
                      v          v
           InvoiceMailService   AlertMailService
                   |                 |
                   +--------+--------+
                            |
                     Same sender bean
~~~

Example Spring Boot configuration with SMTP submission and STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Here Spring Boot can auto-configure JavaMailSender when the mail dependency and matching configuration conditions are present. Username/password come from the environment or a secrets store; never hardcode real credentials in source code. Timeouts are in **milliseconds** and should match real infrastructure.

Two independent services can share the injected sender:

~~~java
@Service
public class InvoiceMailService {
    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
    // Invoice sending methods...
}

@Service
public class AlertMailService {
    private final JavaMailSender mailSender;

    public AlertMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
    // Alert sending methods...
}
~~~

Neither service needs to repeat Session initialization, hostname, username, or TLS logic. Sender configuration stays in **one consistent source**, easy to monitor and update.

### Can the Sender Be Reused Across Multiple Threads?

**JavaMailSenderImpl** is typically used as a singleton service with fixed configuration invoked across many requests/workers. However, that does not mean every underlying component is thread-safe if the application mutates them manually. During concurrent execution:

- **Do not call setHost, setUsername, setPassword, or mutate JavaMailProperties** on the same JavaMailSenderImpl while other threads are sending.
- **Do not share a mutable MimeMessage or SimpleMailMessage** across send operations with different content.
- **Do not share an open SMTP Transport** for multiple threads to call sendMessage manually without a verified synchronization and lifecycle design.
- **Do not assume a singleton sender acts as a global lock** or throttles concurrent connections automatically. Concurrency limits must be managed according to SMTP infrastructure capacity.

If the application needs multiple accounts or multiple SMTP providers, create **independently configured** senders and select the right sender per job. Avoid swapping username/password on a single singleton per recipient, as that invites race conditions, wrong sending permissions, and credential leakage across requests.

### Reusing the Bean Does Not Mean Holding a TCP Connection Forever

**JavaMailSenderImpl** uses **Jakarta Mail Session** and **Transport** to execute SMTP. On the typical send path, the implementation may reuse one Transport for multiple messages **within the same send(array) call**, provided the connection remains valid. When the method finishes, the Transport is normally closed. Independent send calls do not implicitly share an open SMTP socket.

~~~text
Singleton JavaMailSenderImpl
         |
         +-- send(batch A) --> SMTP connection A --> closed after call
         |
         +-- send(batch B) --> SMTP connection B --> closed after call
         |
         +-- send(single)  --> SMTP connection C --> closed after call
~~~

This is the conceptual model for typical SMTP implementations. When the server disconnects mid-batch or encounters an error, the client may need to reconnect. The actual number of sockets opened depends on the implementation, transport, and server. **Reusing JavaMailSender** mainly reuses configuration and API wiring; **sending an array** is what creates the opportunity to save connection round-trips within a single send.

## 7. Is One send(array) Always Better Than Multiple send() Calls?

Two approaches:

~~~java
// Multiple independent calls.
for (SimpleMailMessage message : messages) {
    mailSender.send(message);
}

// One batch send call.
mailSender.send(messages);
~~~

With **JavaMailSenderImpl** and common SMTP transport, a batch call is usually more efficient when sending many consecutive messages through the same server and authenticated identity, because it can reduce connection setups, TLS handshakes, and SMTP AUTH exchanges. Still, the improvement depends on network latency, SMTP speed, rate limits, and server stability.

Conceptual comparison:

| Criterion | Loop of send(single) | Single send(array) |
|---|---|---|
| API call count | N calls | 1 call |
| Opportunity to reuse SMTP connection inside call | Low across independent calls | Yes, depending on implementation and live connection |
| Per-message status tracking | Can catch errors per iteration | Must handle partial errors and message correlation |
| Pre-call memory | Can build one message at a time | Typically holds the batch list/array |
| Send-rate control | Easy to add per-item delay/backoff | Chunk batches and throttle at the worker layer |
| Best suited for | Few emails, strict per-message tracking | Many small emails, infrastructure supporting pipelined/sequential sends |

A bigger batch is not automatically better: SMTP providers may cap messages/minute, recipients/day, concurrent connections, message sizes, or consecutive sends per connection. Pushing batch size too high prolongs connection hold time, increases memory footprint, and complicates failure recovery.

### Splitting Batches into Reasonable Chunk Sizes

Instead of creating an array of 100,000 MimeMessages, process chunks of a capped size, such as **50 messages per chunk**. The number 50 is illustrative; tune it according to throughput, provider limits, memory, and operational requirements.

~~~java
import java.util.List;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class BatchMailSender {
    private final JavaMailSender sender;
    private final int batchSize;

    public BatchMailSender(JavaMailSender sender, int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException(
                    "batchSize must be positive");
        }
        this.sender = sender;
        this.batchSize = batchSize;
    }

    public void submit(List<SimpleMailMessage> messages) {
        for (int start = 0; start < messages.size(); start += batchSize) {
            int end = Math.min(start + batchSize, messages.size());
            SimpleMailMessage[] batch = messages
                    .subList(start, end)
                    .toArray(SimpleMailMessage[]::new);

            sender.send(batch);
        }
    }
}
~~~

The snippet above illustrates **how to split an array into send chunks**, not a complete production solution. If one batch fails and the exception exits `submit`, subsequent batches will not run; some messages inside the failed batch may still have been accepted by the server. Add state persistence, retries, and throttling at the business layer if reliable bulk sending is required.

When data volumes are very large, it is better to **paginate from a database/job store** and build messages per batch, rather than loading every recipient, rendered template, and attachment into RAM at once.

## 8. Partial Failure: A Batch Is Not an Atomic Transaction

Suppose three emails are sent in a single call:

~~~text
JavaMailSender.send([A, B, C])
      |
      +-- A: SMTP accepted
      +-- B: SMTP rejected
      +-- C: SMTP accepted or not yet attempted
~~~

Sending a batch of emails **is not an ACID transaction**. If B fails, you cannot assume email A is rolled back or that every recipient failed. Conversely, if a connection drops mid-way, C's outcome may be unknown. Resending the entire batch in every case risks creating duplicate emails for A.

**MailSendException** provides **getFailedMessages()**, returning a map of failed message objects and their corresponding causes when the implementation can supply that info. Other exceptions like **MailAuthenticationException** or **MailPreparationException** carry different semantics. Do not infer that "every message absent from failedMessages reached the Inbox": that info reflects only the processing scope observed by the transport.

Example of inspecting errors in a batch call:

~~~java
import java.util.Map;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public class ObservableMailBatch {
    private final JavaMailSender mailSender;

    public ObservableMailBatch(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void submit(SimpleMailMessage[] batch) {
        try {
            mailSender.send(batch);
            // Record SMTP_SUBMISSION_ACCEPTED event for the batch.
            // Do not record MAILBOX_DELIVERED just because send() returned.
        } catch (MailAuthenticationException ex) {
            // Check credentials, permissions, or SMTP AUTH configuration.
            // Do not rapidly retry with the same invalid credentials.
            throw ex;
        } catch (MailSendException ex) {
            Map<Object, Exception> failures = ex.getFailedMessages();
            // Correlate each key in failures with a business ID.
            // Messages lacking a reliable result need status
            // UNKNOWN/REQUIRES_RECONCILIATION before retrying.
            recordTransportFailures(failures);
            throw ex;
        } catch (MailException ex) {
            // Record batch-level submission error.
            throw ex;
        }
    }

    private void recordTransportFailures(
            Map<Object, Exception> failedMessages) {
        // Illustrative example: integrate event-logging/monitoring system.
        // Store only identifiers and sanitized error codes,
        // avoiding full message content or credentials.
    }
}
~~~

In real systems, correlate **businessMailId**, **recipient**, and the message object via application-managed metadata/records. A MIME preparation failure before transport is invoked does not necessarily produce per-message results like an SMTP transfer failure. When high retry precision is required, design state and work boundaries **per individual email**, rather than relying solely on a batch-level boolean result.

### SMTP Accepted Differs from Delivered

Even when every message in a batch is processed cleanly by **send()**, all the application usually knows is that the SMTP submission server accepted those messages. Downstream lie MTA queues, SMTP relays, and mailbox delivery. Final delivery events may arrive via DSN, provider events/webhooks, or mail server logs, depending on the setup.

A state sequence that can be designed:

~~~text
PENDING
   |
   v
PREPARING
   |
   v
SUBMITTING
   +----> SUBMISSION_UNKNOWN (timeout or lost reply)
   |
   +----> SUBMISSION_FAILED (confirmed rejection)
   |
   v
SMTP_ACCEPTED
   |
   +----> DEFERRED / BOUNCED (infrastructure feedback)
   |
   v
DELIVERED_TO_KNOWN_BOUNDARY (only when evidence exists)
~~~

These state names are suggested business-model states, not built-in Spring Mail enums. Not every SMTP provider supplies enough events to track all the way to mailbox delivery.
## 9. Asynchronous Sending: Reusing the Sender with an Application Queue

If a single HTTP request immediately sends dozens of emails, the request can be slowed down by TLS handshakes, the SMTP server, the network, or timeouts. Offloading the work to a worker lets the HTTP API respond early and throttle sending more cleanly.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant A as Spring API
    participant D as Database / Outbox
    participant W as Mail Worker
    participant S as SMTP Server
    U->>A: Request to send multiple emails
    A->>D: Persist request and PENDING items
    D-->>A: Commit
    A-->>U: 202 Accepted + requestId
    W->>D: Claim a batch of items
    W->>W: Create an independent message per item
    W->>S: JavaMailSender.send(batch)
    S-->>W: SMTP submission confirmation / error
    W->>D: Save per-item result per observed data
~~~

You can use an internal queue, a broker, a database queue, or a **transactional outbox**. Which one to choose depends on durability, recovery needs, and existing infrastructure. **`@Async`** can also move calls onto a thread pool, yet by itself it **does not provide a queue durable across restarts**, does not solve database–SMTP transactions, and does not track delivery outcomes automatically.

### Why Is a Transactional Outbox Useful?

For instance, when an order is confirmed, the application must save both the order state and the email-send request. If SMTP is called inside the same transaction and SMTP accepts the email before the transaction rolls back, the customer may receive an email for an unsaved order. If the database commits first and sending happens afterward, the application can crash in the gap between the two steps.

With an outbox, **business changes and send-request records** are saved in the same database transaction. After commit, a worker reads the records and calls JavaMailSender. This reduces lost jobs from crashes, though it still does not guarantee exactly-once sending:

~~~text
Worker calls SMTP
       |
       v
SMTP returns 250 accepted
       |
       v
Worker crashes before updating status in DB
       |
       v
Worker restarts and may send the same email again
~~~

Thus you need a **businessMailId**, per-item states, bounded retries, stale-lease recovery, and duplicate handling suited to the business. A MIME `Message-ID` can assist tracing, yet SMTP servers are not required to deduplicate automatically based on that ID.

### Should You Automatically Retry the Whole Batch?

Do not blindly resend an entire batch whenever a MailException occurs. Some messages may already have been accepted by the SMTP server before the error. In particular, losing the connection after the client finishes transmitting DATA but before receiving the reply leaves an **uncertain state of received vs. not received**. Blind retries risk sending duplicate emails.

A sound workflow records per-item status, separating clearly rejected items, retry-eligible items, and items needing reconciliation. If the provider offers idempotency keys or event IDs, use them strictly within the guarantees documented by the provider; standard SMTP provides no end-to-end exactly-once guarantee.

## 10. Controlling Concurrency, Throughput, and SMTP Limits

Batching does not mean spawning unlimited threads. SMTP infrastructure typically enforces limits on concurrent connections, emails per time window, recipients, total size, and sometimes per-account quotas.

Variables to monitor and tune:

| Parameter | When too low | When too high |
|---|---|---|
| **batchSize** | Opens connections too often, high overhead | Long single sends, high RAM usage, harder per-item error recovery |
| **workerConcurrency** | Queue grows rapidly under heavy load | Too many SMTP connections, throttled or resource exhaustion |
| **rateLimit** | Notifications are delayed | SMTP server returns 4xx/5xx or policy blocks |
| **connectionTimeout** | Fails easily on legitimately slow networks | Threads may hang too long |
| **socketReadTimeout** | Times out easily on slow SMTP servers | Increases stuck-job duration |
| **retryBackoff** | Retries hammer an overloaded server | Extends time to finish email delivery |

There is no single optimal **batchSize** for every SMTP server. Start with small batches and low worker concurrency, then observe queue latency, send times, error rates, and provider limits. Increase batch size or workers only when metrics show improvement.

### Throttling with a Worker Pool

Example organization:

~~~text
Database mail_outbox (many pending items)
               |
         Bounded claim
               |
       +-------+-------+
       |               |
    Worker 1        Worker 2
       |               |
    Batch A          Batch B
       |               |
       +-------+-------+
               |
     Shared JavaMailSender bean
               |
      SMTP submission server
~~~

Workers can share a single fixedly configured singleton JavaMailSender, while **each worker builds its own messages**. Worker count is a concurrency decision, not a promise that the sender itself caps total open sockets. To stop two workers from grabbing the same job, database/broker claiming must be concurrency-safe; each item needs a proper identity and lease/claim state.

If the provider returns transient overload errors like **4xx**, slow down the send rate and retry per policy. If the account is rejected for invalid secrets or prohibited relaying, increasing retries only makes things worse. Classify errors by specific response rather than attempt count alone.

## 11. When Multiple SMTP Accounts or Providers Are Needed

Reusing **one** sender makes sense when emails go through one SMTP endpoint/account. However, an application may have two routes:

- Transactional notifications through an email delivery service.
- Internal emails through an organizational SMTP relay.

In that case, declare **two separate JavaMailSenderImpl beans** and use **@Qualifier** to choose:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.mail.javamail.JavaMailSender;

@Service
public class TransactionalMailService {
    private final JavaMailSender transactionalSender;

    public TransactionalMailService(
            @Qualifier("transactionalSender") JavaMailSender sender) {
        this.transactionalSender = sender;
    }
    // Business messages use transactionalSender.
}
~~~

In this case, the bean named **transactionalSender** must be configured separately in the Spring context, such as with a **@Bean** method constructing JavaMailSenderImpl with the hostname, account, TLS, and timeouts for that route. Values come from configuration/secrets management.

**Never mutate password, hostname, or properties on a singleton JavaMailSenderImpl right before each call** to switch accounts. Doing so causes race conditions under concurrent sends and risks sending from the wrong account. Sender reuse should only happen **within a single consistent SMTP configuration**.

### Reusing Shared Content Differs from Reusing an SMTP Sender

A shared email template does not have to be a pre-built MimeMessage. Use a DTO or template engine to render **subject, text, and HTML** per recipient, then create each new MimeMessage from scratch. That preserves control over personalization, Message-ID, attachments, destination addresses, and per-message headers. Sharing template data is far safer than sharing a mutable MimeMessage object.

## 12. Common Design Mistakes

**Creating a new JavaMailSenderImpl on every request.** This duplicates configuration and complicates security, timeout, metric, and routing management. When the application shares an SMTP endpoint, inject a stably configured bean into services.

**Assuming a singleton sender keeps an SMTP socket open forever.** The Spring bean typically lives as long as the application, yet Jakarta Mail's Transport has its own connection lifecycle. Varargs batches encourage connection reuse within a call; do not assume independent calls share one permanently open socket.

**Reusing one SimpleMailMessage for multiple recipients.** Because the object is mutable, an array holding multiple references to the same message leaves every element with the final address/body. Create distinct messages or copy from a fixed template.

**Sharing a MimeMessage across multiple threads.** A MimeMessage being edited is not an immutable content object. Create a new one per email and avoid mutating after handing it off to send.

**Sending one message to many people instead of a personalized batch.** This can expose recipients via To/CC and prevents per-recipient subjects/bodies. Pick the model matching data and privacy requirements.

**Assuming send(batch) is an atomic transaction.** Some messages may already be accepted before another fails. Throwing an exception in Java does not roll back SMTP; persist per-item state and reconcile.

**Retrying the entire batch on timeout.** If the reply after DATA was lost, the server may have stored the message. Unconditional retries easily cause duplicates; separate confirmed failures from uncertain states.

**Holding attachments for thousands of emails in RAM at once.** This spikes heap usage, stresses GC, and risks exhausting resources. Chunk batches, use suitable resources, and paginate jobs.

**Spinning up many workers to "go faster" without checking provider quotas.** The SMTP provider may throttle, reject, or block sending; worker concurrency and rate limits must work together.

**Only logging "mail sent" for the whole batch.** When a few messages fail, an aggregate log cannot explain which message needs reconciliation. Use request IDs, recipient/job IDs, and per-stage events, avoiding logging bodies and credentials.

## 13. Observing Performance and Send Success Rates

A system sending many messages should measure not only JavaMailSender call counts, but also:

| Metric | Meaning |
|---|---|
| **messagesPrepared** | How many messages finished content construction |
| **messagesSubmitted** | How many messages were attempted against the transport |
| **smtpAccepted** | How many messages have evidence of submission-server acceptance |
| **submissionUnknown** | How many messages have indeterminate results due to timeout/disconnect |
| **batchDuration** | Processing time of one send(array) call |
| **queueDepth** | Number of jobs waiting in the application |
| **oldestJobAge** | Delay of the oldest unprocessed job |
| **retryCount** | Retry count per item |
| **providerResponseClass** | Rate of transient/permanent failures by SMTP response |

Attach a **businessMailId** to each send request and store any provider message ID or queue ID returned by infrastructure. MIME **Message-ID** helps with correlation, yet is not guaranteed unique across all systems; the same email can receive different queue IDs across MTAs.

To diagnose slowness, separate timings into: queue wait time, template/MIME construction, TLS/AUTH handshake, per-message transmission, and SMTP response wait. Some SMTP providers also continue queuing messages after the client receives success. Do not aggregate everything as "email delivered time" when you only have submission data.

When benchmarking, use a test SMTP server or authorized test account with appropriate volume and content. The best measurements focus on **connection counts, batch duration, and error rates** under controlled conditions. Those metrics inform `batchSize` and concurrency choices; no fixed formula is optimal for every organization.

## 14. Choosing an Implementation Matching Send Volume

| Need | Typically suitable organization |
|---|---|
| One short text notification | Send a single SimpleMailMessage |
| A few dozen text notifications with individual recipients | Build a SimpleMailMessage array and call send(array) |
| Multiple HTML or attachment notifications | Create a separate MimeMessage per email or use MimeMessagePreparator |
| Many email waves across the same application | Inject a fixedly configured singleton JavaMailSender |
| Thousands of emails needing restart recovery | Database/broker/outbox + worker + small batches + per-item status |
| Multiple SMTP providers or accounts | Multiple separately configured sender beans with explicit routing |
| Tracking actual delivery to domain/mailbox | Combine events/DSN/provider webhooks rather than relying only on send() |

In Spring Framework Mail, **reusing the sender** centralizes configuration and cuts component initialization; **sending multiple messages via varargs overloads** optimizes SMTP steps within a batch. Both techniques belong alongside **creating independent messages, bounded batch chunking, per-email status persistence, and partial-failure handling**.

Always keep the responsibility boundary clear: **a successful send() reflects transport-level SMTP submission**, whereas delivering into a mailbox, landing in the Inbox, or being read by the recipient are downstream stages requiring separate evidence.
