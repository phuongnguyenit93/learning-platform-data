# When Synchronous Mail Sending Is Appropriate

In Spring Framework Mail, calling §JavaMailSender.send(...)§ usually performs SMTP sending directly on the calling thread. The method only returns after the transport sending process completes or an error occurs. This is **synchronous sending**: the caller waits for the result of the send operation before continuing its work.

Synchronous sending is appropriate when email volume is low, the operation is short, the caller needs to know immediately whether submitting the message to SMTP succeeded, and the wait time is acceptable in the current flow. Examples include an admin tool sending a manual notification, an internal application with few emails, or an operation that needs to report send errors immediately to an operator.

This approach has an important limitation: **SMTP accepting a message does not mean the email reached the inbox or the recipient read it**. It only indicates that the step of handing the message to the SMTP server achieved the result reported by the transport. In addition, the caller must hold the thread throughout the entire time spent connecting, authenticating, transferring data, and waiting for a response.

This lesson explains the semantics of synchronous sending, when to use it, how to integrate it with requests and transactions, error/timeout handling, load limits, idempotency, and signs that an application needs to move to a queue or transactional outbox.

## 1. What Does Synchronous Mail Sending Mean?

With synchronous sending, the code calls §JavaMailSender§ and waits for the call to finish:

§§§java
mailSender.send(message);

// The next line only runs after send returns
updateNotificationStatus();
§§§

The execution flow can be visualized as:

§§§text
Caller thread
    |
    v
Build MimeMessage
    |
    v
JavaMailSender.send(...)
    |
    +--> Connect to SMTP server
    |
    +--> Authenticate (if configured)
    |
    +--> Transfer message data
    |
    +--> Receive SMTP response
    |
    v
Return or throw MailException
    |
    v
Continue caller code
§§§

During this time, the calling thread is waiting. If this is a thread handling an HTTP request, that request also has to wait until sending finishes or times out.

Simple service example:

§§§java
@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("notice@example.org");
        helper.setTo(recipient);
        helper.setSubject("Notification");
        helper.setText("Your request has been processed.");

        mailSender.send(message);
    }
}
§§§

When §sendNotice§ returns normally, the sender's send operation has completed according to the result provided by the transport. If the SMTP server rejects the message or an error occurs while creating/sending it, Spring may throw an exception in the §MailException§ hierarchy.

### Synchronous Does Not Mean Instant Delivery

SMTP is a mail relay protocol. A successful response from an SMTP server usually means the server has accepted responsibility for processing the message according to the protocol. It does not confirm that:

- The message has been delivered to the final mailbox.
- The email was not blocked by a spam filter or provider policy.
- The recipient address is still active.
- The recipient has opened or read the message.

To track delivery, bounces, or complaints, you need to integrate events from the email provider or corresponding mail system. The return outcome of §JavaMailSender.send§ is only one part of the delivery lifecycle.

## 2. When Is Synchronous Sending the Right Choice?

Synchronous sending is appropriate when the benefit of immediate feedback outweighs the cost of holding a thread and depending on SMTP.

### 2.1. Low-Frequency Admin Tools or Manual Operations

Examples:

- An operations staff member clicks a button to resend a notification.
- An administrator sends an email to verify the SMTP configuration.
- An internal tool sends a small on-demand report.
- A support system manually sends a confirmation email on a case-by-case basis.

In these flows, request volume is low and the operator can wait for the result. If SMTP fails, the UI can report it immediately so the operator can handle it.

Manual send operations must be distinguished from bulk campaign sending. A button that sends a single message may suit synchronous sending; sending to thousands of recipients requires queuing, rate limiting, and per-recipient tracking.

### 2.2. Low-Load Internal Applications with Acceptable Wait Times

An internal application with a few users, where each action sends only a small email, can use synchronous sending if:

- The SMTP server is stable and close on the network.
- Timeouts are clearly configured.
- The application's request timeout is greater than the expected send time.
- The number of request-handling threads is sufficient for the wait time.
- Users understand that the operation may take a few extra seconds.

This is a simple operational choice for small systems. When traffic grows or SMTP becomes slow, re-measure before continuing to use it in the request path.

### 2.3. Needing Immediate Feedback on Whether SMTP Accepts or Rejects the Message

Some operations only make sense when the caller knows the send result immediately, for example:

- A mail server configuration testing tool.
- An admin page sending a test email to an entered address.
- A support tool sending a notification requested by staff.
- An internal workflow that must display SMTP configuration or authentication errors to an operator.

Here, feedback should be phrased accurately as “SMTP accepted the message” or “failed to send to SMTP”, depending on the result. Do not display “recipient received the email” just because §send§ returned normally.

### 2.4. Email as a Direct Part of a Short Operation That Can Fail Clearly

Synchronous sending can be used if the business operation already requires the caller to wait for an external result and the system accepts failing the operation when SMTP is unavailable. For example, a tool that exports a report and then sends an email to the requester, where task completion is only confirmed once SMTP accepts the message.

It is necessary to decide clearly what happens if the report is generated successfully but sending the email fails. You can keep the file for download, mark the send attempt as failed, and allow manual retry. You should not assume an SMTP exception will automatically roll back side effects that already occurred.

### 2.5. Testing, Command-Line Tools, and Short Operational Tasks

In tests or a command-line utility, synchronous sending is usually straightforward: call the sender, wait, then assert the result or return an exit code. There is no need to build a queue system just to send a single message in a test or one-off tool.

For integration tests, use a mock SMTP server such as GreenMail or Mailpit. Tests verify that the test server received the message, rather than sending real emails to users.

## 3. When Should You Consider Another Approach?

Synchronous sending becomes inconvenient when sending is no longer a short operation or the caller does not need to wait for the SMTP result.

| Scenario | Why sync causes drawbacks | Better-suited approach |
|---|---|---|
| Sending emails to many people | Request holds the thread for a long time, easily exceeding timeout | Queue and worker |
| Email triggered after every high-volume order | Slow SMTP slows down the order creation flow | Transactional outbox |
| SMTP provider is frequently slow/intermittent | Caller absorbs all latency and errors | Queue, controlled retry, circuit breaker |
| Need retry after application restart | Caller request has already ended, no work remains to resume | Persist request durably in outbox |
| Need per-provider rate limiting | Many concurrent requests can exceed quota | Worker with concurrency/rate limit |
| Need audit trail of every send attempt and status | Status only lives in request logs | Delivery record and worker |
| Email must not fail the core business operation | SMTP errors can make the API fail even though data was committed | Outbox and background sending |
| Need to handle many large attachments | Serialization/data transfer time is long | Background job and appropriate storage |

Not every important email needs synchronous sending. Important emails usually need **reliability and retry capability**, which a queue/outbox can provide better.

## 4. Evaluating Latency Before Putting Send in the Request Path

A synchronous request has a response time made up of several parts:

§§§text
Request duration
  = business processing
  + template rendering
  + SMTP connect/authentication
  + message transfer
  + SMTP response wait
§§§

SMTP duration is not fixed. It depends on the network, DNS, TLS handshake, authentication, message size, provider, and server state. A mail-sending request may be fast under normal conditions but significantly slow when SMTP encounters issues.

Before choosing sync, measure:

- Average duration and high percentiles (p95/p99) of §send§.
- Exception rate by type.
- Connection time and message write time.
- Message size, especially with attachments/inline images.
- Number of concurrent mail-sending requests.
- Number of HTTP threads held while waiting for SMTP.

Do not look only at the average time. If most emails take 200 ms but a few take 20 seconds, those slow requests can still exhaust threads when load increases.

### Time Budget Example

Suppose an API has a target response time of 2 seconds. If business logic and the database already use 1.2 seconds, the mail-sending part only has about 800 ms left in that budget. If SMTP regularly takes several seconds, sending in the request path will make the target unstable.

These numbers are a planning example, not a Spring default limit. Use measurements from your actual environment and product SLA.

## 5. Synchronous Sending in an HTTP Request

A controller can call the mail-sending service directly:

§§§java
@RestController
@RequestMapping("/admin/mail")
public class AdminMailController {

    private final NotificationMailService mailService;

    public AdminMailController(NotificationMailService mailService) {
        this.mailService = mailService;
    }

    @PostMapping("/test")
    public ResponseEntity<String> sendTest(
            @RequestParam String recipient
    ) {
        mailService.sendTestMail(recipient);
        return ResponseEntity.ok("SMTP accepted the test message");
    }
}
§§§

This example fits an admin endpoint with controlled access, low frequency, and the goal of checking mail-sending connectivity.

In a real system, you must authenticate and authorize the caller, validate the recipient address against policy, apply rate limiting, prevent the request from arbitrarily setting From or SMTP headers, return a message that accurately reflects the meaning of the result, and handle §MailException§ into an appropriate response without leaking credentials or internal details.

### Do Not Let Requests Wait Indefinitely

SMTP timeouts must be configured. Without appropriate limits, a hung connection can hold a thread longer than expected.

Spring Boot configuration example:

§§§yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      "mail.smtp.connectiontimeout": 5000
      "mail.smtp.timeout": 5000
      "mail.smtp.writetimeout": 5000
§§§

The values in the example are in milliseconds and must be tuned according to the provider, network environment, and SLA. The three timeouts control different stages:

- §connectiontimeout§: time to wait for establishing a connection.
- §timeout§: time to wait for reading a response.
- §writetimeout§: time to wait for writing data.

These property names belong to JavaMail SMTP configuration; if using a different transport or provider, check the corresponding properties. You also need to align timeouts with reverse proxies, load balancers, and HTTP clients so requests are not cut off before the application finishes processing.

## 6. Error Handling in Synchronous Sending

§JavaMailSender§ throws exceptions in the §MailException§ hierarchy when sending fails. Errors can occur at multiple stages:

- Incorrect host/port configuration.
- DNS or network connection failure.
- Unsuccessful TLS handshake.
- SMTP authentication rejected.
- Recipient address or message rejected by the server.
- Error serializing MIME parts or reading attachments.
- SMTP server not responding within the timeout.

A service can handle errors at an appropriate boundary:

§§§java
import org.springframework.mail.MailException;
import org.springframework.stereotype.Service;

@Service
public class SynchronousNotificationService {

    private final JavaMailSender mailSender;

    public SynchronousNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public SendResult send(MimeMessage message) {
        try {
            mailSender.send(message);
            return SendResult.smtpAccepted();
        } catch (MailException exception) {
            // Log message ID and error type; avoid logging credentials/payload.
            return SendResult.smtpFailed(classify(exception));
        }
    }

    private String classify(MailException exception) {
        return exception.getClass().getSimpleName();
    }
}
§§§

§SendResult§ is an illustrative application data type. In practice, you can keep the cause for internal diagnostics, while the response sent to the client should only contain safe messages and stable error codes.

### Do Not Swallow Exceptions and Report Success

Dangerous pattern:

§§§java
try {
    mailSender.send(message);
} catch (MailException exception) {
    log.warn("Mail failed", exception);
}

return "Email sent successfully";
§§§

The code above turns an SMTP failure into a false success. If the business logic needs to know whether sending succeeded, return an explicit status or throw an exception for the calling layer to handle.

### Distinguishing Transient and Permanent Errors

Some errors can be retried later, such as a temporary timeout or an unavailable SMTP server. Some errors require fixing data or configuration, such as an invalid recipient or rejected authentication.

Do not retry every §MailException§ the same way. With synchronous sending, you can return the error to the caller and allow a manual resend after identifying the cause. For systems with automatic retries, classify errors, set retry limits, backoff, and idempotency.

### Watch Out for Uncertain Outcomes

A situation can occur where the application has transmitted the message and the SMTP server has received it, but the connection drops before the application receives the final response. The caller sees a timeout or exception and cannot be sure whether the server received it.

If retried immediately, the recipient may receive a duplicate email. This is a form of *ambiguous outcome* in network communication. For notifications where duplicates have significant impact, you need a business message ID, delivery record, and appropriate idempotency or deduplication mechanisms.

## 7. Do Not Send via SMTP Inside a Long Database Transaction

Sending email is a side effect on an external system. A database transaction cannot roll back a message that the SMTP server has already accepted.

Example of what not to do:

§§§java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(create(command));

    mailService.sendConfirmation(order);

    return order;
}
§§§

There are two risky scenarios:

1. SMTP accepts the email, and then the database transaction rolls back. The recipient has received a notification about an order that was not committed.
2. The database has performed several operations and is holding locks, while SMTP is slow or fails. The transaction is prolonged, increasing contention and wait times for other requests.

### If You Still Need Synchronous Sending, Send After Transaction Commit

You can separate saving data and sending mail:

§§§java
public Order createOrder(CreateOrderCommand command) {
    Order order = transactionTemplate.execute(status ->
            orderRepository.save(create(command))
    );

    mailService.sendConfirmation(order);
    return order;
}
§§§

In this example, the transaction saving the order completes before sending mail. If SMTP fails, the order still exists. The calling layer must decide the response and how operators can resend.

Another option is §@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)§ to run a listener after commit:

§§§java
@Component
public class OrderMailListener {

    private final NotificationMailService mailService;

    public OrderMailListener(NotificationMailService mailService) {
        this.mailService = mailService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        mailService.sendConfirmation(event.orderId());
    }
}
§§§

By default, the listener runs synchronously on the event-publishing thread after commit, unless configured to be asynchronous. This avoids sending before the transaction commits, but **provides no durability guarantee** if the process stops after commit and before the listener finishes sending. If the email must be sent reliably, use an outbox or durable job storage mechanism.

## 8. Do Not Confuse Synchronous Sending with @Async

§@Async§ allows Spring to execute a method on another executor thread when called through an appropriate Spring proxy. This is thread-level asynchronous sending:

§§§java
@Async
public void sendLater(MimeMessage message) {
    mailSender.send(message);
}
§§§

The caller can continue before sending finishes. However, this differs from a durable queue:

| Characteristic | Synchronous sending | In-process §@Async§ | Durable queue/outbox |
|---|---|---|---|
| Caller waits for SMTP | Yes | Usually no | No |
| Work survives process stop | No separate queue | Usually no, depends on executor | Yes if stored durably |
| Retry after restart | Caller must perform again | Needs custom mechanism | Worker can resume from record |
| Status observability | Immediate result in call | Needs Future/callback/status | Has delivery/job record |
| Suitable for | Short tasks, low load, immediate result needed | Simple in-process background tasks | Business emails needing reliability and retry capability |

§@Async§ also has limitations:

- Calling an async method from another method in the same object may bypass the proxy, so it will not run asynchronously as expected.
- The executor needs bounded threads and queue capacity.
- Exceptions in a method returning §void§ are not automatically thrown back to the caller.
- A process restart can lose queued or in-flight work.
- There is no exactly-once guarantee when sending via SMTP.

Therefore, if you only want the caller not to wait, §@Async§ can fit low-importance notifications where losing work on a process crash is acceptable. If you need a guarantee that the send request is saved and resumed after a restart, use a queue or outbox.

## 9. How Synchronous Sending Can Exhaust Threads

In a web server, each request typically uses a thread for a period of time. If a request calls SMTP synchronously, that thread is held while waiting on the network.

Suppose an application has 100 request-handling threads and many concurrent requests are waiting on SMTP. Once all 100 threads are held, new requests may have to wait in the server's queue or be rejected according to configuration.

§§§mermaid
flowchart TD
    A["HTTP requests"] --> B["Request thread pool"]
    B --> C["Request 1 waits for SMTP"]
    B --> D["Request 2 waits for SMTP"]
    B --> E["Request 3 waits for SMTP"]
    B --> F["Other request threads"]
    C --> G["SMTP provider"]
    D --> G
    E --> G
    G --> H["SMTP response"]
    H --> I["Threads become available"]
§§§

This can create a cascading effect:

1. Slow SMTP causes requests to hold threads longer.
2. The thread pool gradually fills up.
3. Requests unrelated to email also slow down due to thread starvation.
4. Client retries increase load.
5. The system becomes even harder to recover while SMTP remains unstable.

If you still use sync, limit concurrent send operations, configure timeouts, monitor the thread pool, and apply rate limits to endpoints that can trigger mail sending.

## 10. Limiting Rate and Volume of Synchronous Emails

A bulk-sending loop:

§§§java
for (String recipient : recipients) {
    mailSender.send(buildMessage(recipient));
}
§§§

executes sequentially. Total duration can approach the sum of each individual send duration. If sent in parallel using multiple threads, duration may decrease, but this creates more connections and load on the SMTP provider.

With synchronous sending, you should set limits:

- Maximum number of recipients per request.
- Number of messages sent within a time window.
- Maximum concurrent sends.
- Maximum message and attachment size.
- Connect/read/write timeouts.
- Alert thresholds when latency or errors rise.

Do not use synchronous requests to send newsletters or large campaigns. Those workloads need queues, batching, suppression lists, unsubscribe policies, rate limits, and delivery tracking.

### One Request Sending to Multiple Recipients Can Create Privacy Risks

If multiple recipients are placed in the same §To§ or §Cc§ field, addresses can be exposed to other recipients. When individual delivery is needed, create an appropriate message per recipient or use a bulk-sending mechanism with personalization management. Grouping many addresses into one message also makes it harder to determine which recipient was rejected.

## 11. Idempotency and Duplicate-Send Risks

Synchronous sending does not guarantee that one HTTP request creates exactly one email. Users may double-click, browsers may retry, gateways may retry requests, or clients may resend after a timeout.

Example:

1. The API receives an email send request.
2. SMTP accepts the message.
3. The application times out before returning the response.
4. The client does not know the outcome and resends the request.
5. A second email is created and sent.

To reduce duplicates, an idempotency key can be used:

§§§java
public SendResult sendOnce(
        String idempotencyKey,
        MailCommand command
) {
    SendRecord existing = sendRecordRepository
            .findByIdempotencyKey(idempotencyKey)
            .orElse(null);

    if (existing != null) {
        return existing.toResult();
    }

    // Requires a unique constraint and appropriate claim/locking mechanism
    // to handle two concurrent requests using the same key.
    return performAndRecordSend(idempotencyKey, command);
}
§§§

This is a sketch; simply querying then inserting is not enough to prevent races when two concurrent requests use the same key. You need a unique constraint, transactions, and explicit conflict/claim handling.

Application-level idempotency also does not turn SMTP into exactly-once. If the server received the email but the application failed to record the outcome, the record may remain in an uncertain state. Define statuses such as §PENDING§, §SUBMITTING§, §ACCEPTED_BY_SMTP§, §FAILED§, and §UNKNOWN§ if the business logic needs to distinguish uncertain outcomes.

## 12. Tracking Status and Logs in Synchronous Sending

Even when sending directly, you should still have an internal message ID to correlate logs and requests.

Structured log example:

§§§text
messageId=mail-2026-001
notificationType=ADMIN_TEST
recipientDomain=example.net
durationMs=842
smtpOutcome=ACCEPTED
errorType=none
§§§

On error:

§§§text
messageId=mail-2026-002
notificationType=ADMIN_TEST
durationMs=5000
smtpOutcome=FAILED
errorType=MailSendException
§§§

Fields to consider:

- Internal message ID.
- Notification type.
- Start/end timestamps and duration.
- SMTP outcome with accurate semantics.
- Exception type and classified error code.
- Masked/hashed recipient or domain-only logging when appropriate.
- Template version and locale if traceability is needed.

Do not log SMTP passwords, authentication tokens, full MIME sources, or sensitive payloads. Log enough to investigate without copying private data into logging systems.

### Useful Metrics

Monitor:

- mail_send_total by outcome and notification type.
- mail_send_duration histogram/percentiles.
- mail_send_failure_total by exception type.
- Number of requests currently waiting on SMTP.
- Timeout rate.
- Number of manual retries or resends.
- Duplicate-send rate if the system detects it.

If sending synchronously in web requests, correlate mail-sending metrics with HTTP latency and thread pool utilization to understand the impact on the entire application.

## 13. How to Return Results to the Caller

Do not return an ambiguous boolean if the caller needs to handle multiple states. You can define a result type:

§§§java
public record SendResult(
        String messageId,
        Status status,
        String errorCode
) {
    public enum Status {
        SMTP_ACCEPTED,
        FAILED,
        UNKNOWN
    }

    public static SendResult accepted(String messageId) {
        return new SendResult(messageId, Status.SMTP_ACCEPTED, null);
    }

    public static SendResult failed(String messageId, String errorCode) {
        return new SendResult(messageId, Status.FAILED, errorCode);
    }
}
§§§

This is an illustrative model. If §send§ returns normally, you can return §SMTP_ACCEPTED§. If it fails clearly before the server receives the message, return §FAILED§. If a timeout occurs when the outcome is uncertain, consider §UNKNOWN§ so blind retries are not encouraged.

At the HTTP layer, map the result according to the API contract. For example, an SMTP test endpoint can return §200§ when SMTP accepts, or §502§ or §503§ when the sending service is unavailable, depending on the design. Do not turn SMTP errors into a §500§ without a useful error code or expose credential details.

## 14. Combining Synchronous Sending with Critical Business Logic

Determine what role the email plays in the business outcome.

### Email Is Only a Secondary Notification

For example, a user creates an order and the email is only for confirmation. If SMTP fails, the order is still valid. In this case, sending synchronously and throwing an exception can make the API report an error even though the order was saved. The user may retry creating the order and create duplicate orders.

A better design is:

- Commit the order.
- Write the email request to an outbox in the same transaction.
- A worker sends it later.
- If sending fails, retry according to policy.
- The API returns the order creation result independently of SMTP status.

### Email Is the Primary Result of the Operation

For example, an admin tool “Send test email” only completes when SMTP accepts the message. Synchronous sending fits because sending itself is the goal of the operation. If it fails, the user needs to know immediately to fix the configuration or try again.

### Email Has Security Impact or Time Sensitivity

Password reset emails, verification codes, or security alerts may require low latency, while also needing anti-spam protection, rate limiting, idempotency, and token protection. Do not choose sync just because an email is “important”. Evaluate requirements for latency, reliability, retries, and impact when SMTP is temporarily unavailable.

## 15. An Example of Bounded Synchronous Sending with Error Handling

The example below is for an admin endpoint that sends a test email. It creates a message, sends immediately, and returns the SMTP-level result:

§§§java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailTestService {

    private final JavaMailSender mailSender;

    public MailTestService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public TestMailResult sendTest(String recipient) {
        String messageId = "test-" + java.util.UUID.randomUUID();

        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");

            helper.setFrom("admin@example.org");
            helper.setTo(recipient);
            helper.setSubject("SMTP configuration test");
            helper.setText(
                    "The application successfully submitted a test message."
            );

            mailSender.send(message);

            return new TestMailResult(
                    messageId,
                    TestMailResult.Status.SMTP_ACCEPTED,
                    null
            );
        } catch (MessagingException | MailException exception) {
            // Record the exception internally; the response does not contain secrets.
            return new TestMailResult(
                    messageId,
                    TestMailResult.Status.FAILED,
                    "MAIL_SUBMISSION_FAILED"
            );
        }
    }
}
§§§

Result type:

§§§java
public record TestMailResult(
        String messageId,
        Status status,
        String errorCode
) {
    public enum Status {
        SMTP_ACCEPTED,
        FAILED
    }
}
§§§

This example illustrates the handling structure. In a real application, you must validate the recipient, authorize the endpoint, apply rate limits, record duration, and classify timeouts/unknown outcomes. If you want the caller to receive an exception for an upper layer to handle, the service can throw a classified error instead of converting all errors into a single result.

## 16. Checklist for Deciding to Use Synchronous Sending

Before calling §JavaMailSender.send§ in a business flow or HTTP request, answer:

| Question | If the answer is “Yes” |
|---|---|
| Is the number of emails per operation low and bounded? | Sync may be appropriate. |
| Does the caller need to know immediately whether SMTP accepted or rejected? | Sync has a clear advantage. |
| Is the send duration within the measured latency budget? | You can continue evaluating sync. |
| Are SMTP and HTTP timeouts configured? | Wait times can be controlled. |
| Can SMTP errors be represented clearly without corrupting business state? | Sync is easier to integrate. |
| Is retry after a process restart unnecessary? | A durable queue may not be needed. |
| Is the number of concurrent requests bounded? | Reduces the risk of thread exhaustion. |
| Is sending avoided inside long database transactions? | Avoids holding locks while waiting on the network. |

If most answers are “No”, consider a queue/outbox. In particular, if the email is a side effect of an important transaction and must be retried after a failure, an outbox is usually the better choice.

## 17. Key Takeaways

- Synchronous sending means the caller waits for §JavaMailSender.send(...)§ to complete or throw an error.
- A successful result usually only confirms that SMTP accepted the message; it does not prove the email reached the inbox or was read.
- Sync is suitable for few, short emails, manual/admin operations, low-load internal apps, and cases where the caller needs immediate SMTP feedback.
- Do not use synchronous requests for campaigns, bulk sending, or high-volume triggered notifications.
- Measure p95/p99 latency, timeouts, concurrent requests, and thread usage before putting SMTP in the request path.
- Configure connect/read/write timeouts; handle §MailException§ explicitly and do not report false success.
- Avoid sending via SMTP inside long database transactions. If sending after commit, remember that a synchronous listener still provides no durability guarantee when the process stops.
- §@Async§ only offloads work to an executor thread; it does not replace a durable queue/outbox.
- Handle timeouts with uncertain outcomes and duplicate-send risks using message IDs, idempotency, and appropriate delivery records.
- For emails that are side effects of critical business logic, a transactional outbox persists the send request in the same transaction and lets a worker retry later.
- Monitor send duration, SMTP outcomes, error types, and impact on HTTP latency; do not log credentials or sensitive payloads.

Choose synchronous sending when waiting on SMTP is an acceptable part of the operation and the caller needs the submission result immediately. When emails must be sent durably, retried after failures, or must not slow down the main business flow, persist the send request and process it with a worker.
