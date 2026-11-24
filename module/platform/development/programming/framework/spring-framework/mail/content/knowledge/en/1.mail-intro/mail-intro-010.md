# Limitations of Treating Email as a Simple Synchronous Call

When starting to learn **Spring Framework Mail**, we often write a few lines of code to build a message, call **JavaMailSender.send(...)**, and conclude: "The application sent the email." That snippet is enough to show how Spring integrates with an SMTP server, yet it easily leads to a flawed mental model: **a mail-sending call succeeding does not mean the recipient received the message**. Nor does it guarantee the send operation can be safely repeated, will not degrade API speed, or will stay consistent with newly saved data.

This lesson analyzes those limitations from a Spring application's perspective, helping clearly separate the responsibilities of mail-sending code, the SMTP server, the mail distribution system, and business flows. This is the foundation for deciding when direct sending is sufficient and when background processing, queues, or a more reliable sending mechanism is needed.

## 1. What Is a Synchronous Call Actually Waiting For?

Consider a simple Spring service class:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {
    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.test");
        message.setTo(recipient);
        message.setSubject("Welcome");
        message.setText("Your account has been created.");

        mailSender.send(message);
    }
}
~~~

This is a **synchronous call on the application side**: the thread executing the **sendWelcome** method must wait until sending through the configured mail mechanism finishes or throws an error. Under a typical SMTP setup, that work includes connecting to the server, conducting the protocol conversation, and transferring the message body to the accepting server.

However, the message still has its own journey after the application hands it to the SMTP server:

~~~text
HTTP request
    |
    v
Spring service
    |
    | JavaMailSender.send(...)
    v
SMTP server / email provider
    |
    | Queuing, routing, relaying, retrying...
    v
Receiving mail server
    |
    | Spam checks, policies, filters, mailbox rules...
    v
Inbox / Spam / rejected or bounced message
    |
    v
Recipient may open and read the message
~~~

**Boundary to remember:** a successful handoff to an SMTP server usually only indicates that the server **accepted responsibility for processing the message** at that stage. It does not prove the message arrived at the destination mailbox, landed in the Inbox, or was read by a human.

Even a successful SMTP response (such as a **2xx** code, typically **250** after the server accepts the message data) only reflects the outcome of that corresponding communication step. Downstream servers can continue relaying, defer, apply policies, or generate a non-delivery notification later. Detailed observability depends on the email service and confirmation mechanisms integrated into the system.

### Statuses That Should Not Be Conflated

| Milestone | Meaning | What can be concluded? |
| --- | --- | --- |
| Application creates message | Has recipient address, subject, and body | No mail-sending communication has occurred yet |
| Application writes send job to queue | Request persisted for later processing | Not necessarily contacted SMTP yet |
| SMTP server accepts message | Corresponding submission step succeeded | Does not confirm the message reached the Inbox |
| Provider reports delivered to receiving server | Infrastructure-level delivery signal exists | Does not guarantee the message sits in the Inbox |
| Recipient opens or reads | Interaction signal exists if the system collects it | Read signals may be missing or imprecise |

Therefore, status names such as **PENDING**, **SUBMITTED**, **DELIVERED**, or **FAILED** must be defined by **the evidence the application actually possesses**. Do not transition to **DELIVERED** merely because **send(...)** returned without throwing an exception.

## 2. Latency and Application Resource Limitations

If mail sending is invoked directly inside an HTTP API, the API response time includes business processing time **plus mail-system wait time**. During that wait, the request-handling thread in a typical Spring MVC application remains occupied.

Example of an account registration flow:

~~~text
POST /register
    -> validate input:           20 ms
    -> persist account:          40 ms
    -> call SMTP:             2,000 ms
    -> return HTTP response

Total time is around 2,060 ms, even though the core registration took only 60 ms.
~~~

The numbers are illustrative only; actual latency depends on network, server, timeout settings, and system load. As traffic increases, hundreds of requests waiting on SMTP simultaneously can exhaust the web server's thread pool, slowing down other requests as well. If the email provider suffers an outage, an auxiliary step like a welcome email can make the entire registration flow appear "broken".

The issue is not a bug in Spring Mail: **a network I/O operation with unpredictable completion time has been tied directly to the lifetime of an HTTP request**.

Common consequences:

- **Higher latency:** users wait on the main operation solely because of SMTP waiting.
- **Reduced throughput:** many threads stay occupied waiting for network responses.
- **Cascading failures:** a slow or disrupted mail server drags down APIs whose core business work could still succeed.
- **Overlapping timeouts:** HTTP clients, reverse proxies, web servers, and SMTP have different wait limits; an outer layer may expire before the send outcome is known.

Moving sending to background processing reduces API wait times, but then a separate mechanism is needed to manage send jobs. Making the call "non-blocking to the request" **does not automatically make it more reliable**.

## 3. Error Limitations: Failures and Ambiguous Outcomes

From a Java perspective, we often categorize simply:

~~~java
try {
    mailSender.send(message);
    // Send call completed without reporting an error.
} catch (org.springframework.mail.MailException ex) {
    // An error occurred while preparing or sending the message.
}
~~~

**MailException** represents errors at the Spring Mail API layer. Depending on the cause, the error may involve configuration, authentication, addresses, connectivity, server responses, or the send operation. However, dividing outcomes into "method returned" and "method threw an error" is still insufficient to conclude for certain whether a specific email was received by the remote system.

Consider the following scenario:

1. The application sends the entire message payload to the SMTP server.
2. The SMTP server accepts the message and prepares to send a success response.
3. The network connection drops before the application reads the response.
4. The application sees an I/O error or timeout.

From the application's standpoint, the outcome is now **ambiguous**: the message may have been accepted for processing, or it may not. If the entire message is immediately resent, the recipient might receive two emails. If it is not resent, the recipient might receive none.

This is a classic problem in distributed systems: **losing the response does not prove the remote operation never happened**.

Additionally, a single send to multiple recipients can have different outcomes per address depending on the server, sending method, and configuration. Do not assume all recipients always succeed or fail together as an atomic transaction.

### Timeouts Help, but Do Not Solve the Whole Problem

In a Spring Boot application using SMTP configuration, actively set network wait limits, for example:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    properties:
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

The values above are in milliseconds and are only examples:

- **connectiontimeout:** limits wait time to establish a connection.
- **timeout:** limits wait time when reading data over the socket.
- **writetimeout:** limits wait time when writing data over the socket.

In real deployments, authentication, TLS encryption, and server details must also be configured per provider. Timeouts should be chosen based on operational requirements rather than mechanically copying sample numbers.

Setting timeouts prevents a request from hanging indefinitely, **yet it does not turn an SMTP operation into a guaranteed-delivery transaction**, nor does it eliminate cases where the server received the message while the application lost connectivity.

## 4. Database Consistency Limitations

Suppose account registration has two actions: **save the user** and **send a welcome email**. Many developers put both inside a **@Transactional** method:

~~~java
@Transactional
public void register(RegisterCommand command) {
    User user = userRepository.save(/* data from command */);
    welcomeMailService.sendWelcome(user.getEmail());
}
~~~

The snippet above illustrates the idea and is not a standalone compilable example. The key point is transaction scope: **a database @Transactional does not wrap sending an email over SMTP**.

Two classic scenarios:

**Scenario A — message is sent, data rolls back.**

The application calls SMTP successfully and then a subsequent database operation fails, causing the transaction to roll back. The user already received the "Account created" notification, yet no corresponding account exists in the database. Spring has no way to automatically "recall" an email that has left the system to roll it back alongside the data.

**Scenario B — data commits, message send fails.**

If the account is saved and committed first before sending mail, an SMTP failure cannot automatically revert the database to its prior state. The API may return an error even though the account already exists. The user retries, causing a duplicate-account error or triggering extra emails.

Therefore, define the **business source of truth** clearly: registration is considered complete according to database state, whereas email sending is a related task with its own lifecycle and failure modes. For tasks like email verification or password resets, a missing message can block the user from completing the next step; the system must provide a resend mechanism and appropriate status messaging.

Registering a post-commit callback to send mail (e.g., via transactional events or an after-commit hook) avoids sending before a rollback. However, if the process stops **after commit and before the callback finishes sending**, the send request can be lost. To recover work across restarts, job state must be persisted durably.

## 5. Retry, Duplicate Send, and Idempotency Limitations

"If sending fails, retry" is a natural instinct, yet an uncontrolled retry policy can cause further trouble:

- Retrying immediately while a provider is overloaded can worsen the overload.
- A non-existent address or permanently rejected message generally should not be resent forever.
- Ambiguous SMTP outcomes can cause an already-accepted email to be sent again.
- If a user resubmits an HTTP request after a timeout, the application might create another send job for the same business event.

Distinguish **retrying an existing send job** from **creating a new job**. For example, the business event "send welcome email for registration ID 123" can carry a unique key such as **WELCOME:123**. Thanks to a unique constraint in the database, repeated handling of the same request will not accidentally spawn multiple send jobs.

However, this key primarily **prevents creating duplicate jobs on the application side**. It cannot guarantee the recipient receives only one email in all scenarios: if the provider accepted the message and the connection dropped before the application recorded the result, a retry can still produce a duplicate. The practical property of many designs is **at-least-once processing**, accepting the possibility of duplicate sends and mitigating their impact.

An operable retry mechanism generally needs:

1. Recording attempt count, last attempt time, error, and next attempt schedule.
2. Distinguishing recoverable errors (temporary connection loss, rate limiting) from non-recoverable errors (invalid address/config, permanent rejection) based on information actually provided by the vendor.
3. Using **exponential backoff** and optionally jitter so multiple workers do not retry simultaneously.
4. Capping maximum attempts or total processing window, then moving to a status requiring investigation instead of looping forever.
5. Rate-limiting outbound traffic and avoiding concurrent processing of the same unlocked job.

For emails containing one-time links, verification codes, or short-lived information, consider **expiration time**: resending a message that is no longer usable worsens user experience.

## 6. Delivery and Result-Observability Limitations

Even when SMTP operates reliably, reaching the recipient still depends on the email ecosystem:

| Factor | What can happen | What the application should consider |
| --- | --- | --- |
| Provider limits | Rate limits, quotas, or temporary throttling | Throttle traffic, retry per provider policy |
| Domain/IP reputation | Messages flagged as suspicious | Configure and operate sender identity properly |
| Email authentication | Misconfigured SPF, DKIM, DMARC | Verify DNS and sending domain authentication policies |
| Recipient mailbox | Full quota, non-existent, rejection policy | Track bounces or return signals when available |
| Filters and formatting | Lands in Spam or hidden | Never promise messages will appear in Inbox |
| Delivery time | Messages delayed across intermediate hops | Design status notices and resend capability |

Spring Mail provides an API to create and send messages; a single **JavaMailSender.send(...)** call is not a complete lifecycle observability system. To know whether an email was processed by the provider, delivered, bounced, or marked as spam, the application may need reports, webhooks, events, or dedicated APIs from the email service.

When using webhooks, verify event origin, handle duplicate or out-of-order events, and correlate them back to the exact send job. Not every provider exposes the same set of statuses, and an "email opened" signal is not absolute proof a real person read the content.

## 7. A Better-Suited Model When Email Is a Background Task

A resilient design separates **recording the send request** from **attempting communication with the provider**:

~~~text
Registration request
    |
    v
Spring service
    |
    | Single database transaction
    +----> Save user
    +----> Save outbox event "WELCOME_EMAIL_REQUESTED"
    |
    v
COMMIT -> Return appropriate response

Background worker
    |
    +----> Fetch pending job
    +----> Build email and call SMTP/provider
    +----> Save outcome of each attempt
    +----> Succeeded / awaiting retry / needs manual intervention
~~~

This is the idea behind the **transactional outbox**: when the primary business change and the send-request record are saved in the **same database transaction**, if the transaction commits, the send request is also preserved for later processing. A worker reads incomplete jobs and resumes after application restarts.

A logic sketch:

~~~text
register(command):
    begin database transaction
    user = saveUser(command)
    saveOutbox(
        eventType = "WELCOME_EMAIL_REQUESTED",
        businessKey = "WELCOME:" + user.id,
        recipient = user.email,
        status = "PENDING"
    )
    commit
    return registration result

worker():
    item = claimPendingMailSafely()
    try:
        submitMailToProvider(item)
        markSubmitted(item)
    catch retryable error:
        scheduleNextAttemptWithBackoff(item)
    catch permanent error:
        markFailed(item)
~~~

This is **pseudocode illustrating separation of responsibilities**, not complete runnable code. In a real implementation, claiming jobs must prevent two workers from processing the same record; business keys, transactions, retry scheduling, and state management must be designed consistently. If the application needs to track delivery after SMTP submission, it must also update status from provider feedback.

An outbox prevents losing **send intent** after commit, yet does not make SMTP atomic with the database and does not completely eliminate duplicate sends. After the provider accepts the message but before the worker marks it sent, the process can still crash. The design must therefore tolerate or minimize ambiguous retry cases.

### So Is Just Using @Async Enough?

Annotating a mail-sending method with **@Async** (with Spring async execution properly configured) can move the SMTP call onto another executor, preventing the HTTP request from waiting directly for the result. This is an improvement in **request latency**.

However, tasks sitting in an in-memory executor can be lost when the process stops; the executor can also fill up, and background task exceptions must be handled/observed separately. **@Async does not by itself provide durable persistence, retries, idempotency, or delivery status tracking.** If losing a send request has significant consequences, consider a durable queue, an outbox, or a dedicated mail-job service.

### Choosing an Approach Based on Requirements

| Approach | Suitable when | Main limitation |
| --- | --- | --- |
| Call send(...) directly | Internal tools, testing, low volume where callers accept waiting/errors | SMTP latency and failures are coupled directly to the request |
| @Async / in-process executor | Want to reduce request wait and can tolerate task loss on process stop | Does not guarantee job durability or recovery |
| Durable queue or outbox + worker | Mail tied to critical business events, needing retries and clear state | Must operate workers, duplicate policies, and monitoring |
| Email provider with API, queues, events | Need throttling, analytics, or post-submission tracking | Still must handle network errors, async states, and provider policies |

Options can be combined: for instance, writing an outbox record in a transaction, having a worker pick up jobs, and using JavaMailSender or a provider API to send. The sending tool and the job-durability mechanism are **two distinct responsibilities**.

## 8. Designing API Responses and Business States Faithfully

When a user clicks "Register", the application completing account creation and the email being delivered do not happen at the same instant. Therefore:

- If the transaction creating the account and writing the outbox committed, the response can state **account created and email send request recorded**.
- If an API solely accepts an email send request for background processing, **HTTP 202 Accepted** can be used when aligned with the API contract; this code does not promise the email has reached the recipient.
- If the email serves verification, the UI should clearly state **awaiting verification**, with an appropriate resend option and anti-abuse limits.
- If displaying status is needed, distinguish at least **PENDING**, **SUBMITTING**, **SUBMITTED**, **FAILED**; add **DELIVERED** only when there is reliable signal at that level.
- Never include SMTP credentials, private data, or sensitive tokens in error logs, and never return raw provider exceptions to end users.

Measure pending job ratios, time from event creation to first attempt, send failure rates, retry counts, aged backlog items, and bounce signals when available. These metrics reveal how the mail system affects business operations rather than merely logging a line saying "send succeeded".

## 9. Reasoning Through a Scenario

A user registers an account. Data is saved successfully. While sending the verification email, the connection times out. The user sees an error screen and clicks "Register" again.

With a **synchronous send and no persisted send state**, we cannot reliably answer: was the first account created, did the provider receive the message, how many emails will arrive, and did the second click spawn extra work? Participating systems completed different parts of the work, yet the application represented the entire journey with a single HTTP outcome.

With a **design separating business state and send jobs**, we can confirm the account was saved, locate the exact send record by event key, inspect attempt history, schedule a retry if appropriate, and give the user a suitable next action. Final delivery outcome still depends on the email ecosystem, but the application has the data needed to manage that uncertainty.

**The core insight when learning Spring Framework Mail:** **JavaMailSender.send(...)** is a single point-in-time operation to submit a message through mail infrastructure, not a promise that the entire chain "save data → submit message → deliver to mailbox → recipient reads" will complete synchronously, exactly once, and succeed together. A sound application model starts by placing accurate boundaries around this call, then designing timeouts, transactions, retries, and states according to the reliability your business requires.
