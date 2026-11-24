# Choosing Synchronous vs. Asynchronous Sending Based on User Experience

In **Spring Framework Mail**, an architectural decision surfaces as soon as a product adds email sending: **should `JavaMailSender.send(...)` be invoked inside the user's request, or should the request accept the intent and send via an asynchronous worker?**

The answer does not depend solely on whether SMTP is slow or fast. What feedback must the user receive, what action are they waiting on, can they close the page, what happens if sending fails, and how truthfully can the UI report email status? Those are what drive the architecture.

For example, when a user registers an account, they usually want quick UI confirmation ("Verification request received"), while the email can be sent a few seconds later. Conversely, in an internal "Send test configuration email" tool, an operator may want to wait for SMTP's immediate result to see credential or connectivity errors. For login OTPs, the experience adds a key constraint: the email must arrive **early enough for the code to remain valid**, yet blocking the HTTP request on SMTP does not make the email arrive faster.

This lesson belongs to the **Architectural Decisions** chapter of **Spring Framework Mail**, explaining how to choose **synchronous, asynchronous, and hybrid models** based on user experience (UX), while preserving proper `JavaMailSender` semantics, transactions, outboxes, retries, API statuses, network errors, security, and monitoring.

One overarching principle:

**"The system accepted the request," "the SMTP relay accepted the email," and "the email reached the mailbox" are three distinct events.** Choosing synchronous or asynchronous must never cause the UI to conflate those three events.

## 1. What Do Synchronous and Asynchronous Actually Mean?

**Synchronous sending**: the request-handling thread makes a mail-sending call and waits for its result before returning a response.

~~~text
Browser / Mobile app
        |
        | POST /send-mail
        v
HTTP controller
        |
        v
JavaMailSender.send(...)
        |
        v
SMTP server interaction
        |
        v
Return or exception
        |
        v
HTTP response to user
~~~

**Asynchronous sending**: the request persists the send intent and returns a response before SMTP submission finishes. A worker or separate component performs transport later.

~~~text
Browser / Mobile app
        |
        | POST /send-mail
        v
HTTP controller
        |
        v
Persist mail request / durable outbox
        |
        v
COMMIT
        |
        v
HTTP 202 Accepted
        |
        +-------------------------+
                                  |
                                  v
                          Background worker
                                  |
                                  v
                          JavaMailSender.send(...)
                                  |
                                  v
                             SMTP relay
~~~

### 1.1. Synchronous Describes Wait Timing

Using `JavaMailSender` does not make the system "end-to-end synchronous" all the way to the mailbox. The `send` call finishes once the SMTP relay accepts the message, while downstream delivery still proceeds independently.

### 1.2. Asynchronous Has Multiple Levels

- Calling **`@Async`** inside the same process.
- Dispatching messages via **`ExecutorChannel`** or a local queue.
- Publishing to a broker with matching durability.
- Saving to a **transactional outbox** and letting a scheduled worker send.
- Calling an email provider's HTTP API with its own processing states.

Not every form of asynchronous execution survives restarts or process crashes.

### 1.3. Ask the Exact Right Question

Instead of asking "send email sync or async?", ask: **which milestone must the HTTP caller wait for, and what must we guarantee before confirming success to the user?**

## 2. Three Status Milestones the UI Must Never Conflate

Diagram:

~~~text
A. Request accepted / persisted
             |
             v
B. SMTP submission completed
   (relay accepted or send returned normally)
             |
             v
C. Downstream delivery status
   (delivered, bounced, deferred, unknown)
             |
             v
D. Recipient read/open, if measurable
~~~

### 2.1. A: Request Accepted

For example: the database transaction inserting the outbox event committed. The system has accepted responsibility to process the send intent per policy, yet the email may not have left the application.

### 2.2. B: Outcome of JavaMailSender.send

When **`JavaMailSender.send(...)`** returns normally, the application can record **client-observed SMTP submission completed**. This does not prove the email landed in the inbox.

If `send` throws an exception, not every failure proves the relay **did not** accept the message; a timeout after DATA is a crucial example.

### 2.3. C: Downstream Delivery

To learn whether a message bounced, deferred, or was delivered, the application generally needs provider-specific webhooks/APIs or bounce processing, with proper security and correlation. Spring Mail does not provide these signals itself.

### 2.4. D: Recipient Opened

Even tracking pixels or read receipts are unreliable across many email clients. Respect privacy constraints and avoid using "opened" as a critical workflow condition without an explicit contract.

## 3. Comparison by User Experience

| UX Question | Synchronous | Asynchronous |
| --- | --- | --- |
| Must the user wait for SMTP? | Yes, if `send` sits on the request path | Not necessarily |
| Can the API return the send result immediately? | Can return caller-observed result | Usually returns accepted/queued only |
| If the provider is slow, what happens to the UI? | Long loading spinner or request timeout | UI responds faster, though delivery is unfinished |
| Do requests suffer network variability? | Directly | Can be decoupled from the request |
| Is long-term retry hard? | Hard if holding threads | Better suited with durable queues/outboxes |
| Does it survive restarts automatically? | N/A; in-flight sends can lose context | Only with durable designs |
| Can progress/status be shown? | Usually waits at a single point | Needs a status resource/polling or push if truly needed |
| System complexity | Potentially fewer layers | Needs queues, workers, state, retries, monitoring |
| Guaranteed inbox placement? | No | No |

### 3.1. Synchronous Is Not Automatically Simple for Business Logic

If SMTP times out after DATA, the HTTP request may report an error even though the relay accepted the email. The user clicks "Resend" and creates a duplicate. Even when the `send` call looks simple, the experience can become tricky to handle.

### 3.2. Asynchronous Is Not Automatically Reliable

An **`@Async void`** without durable state can return success before the worker runs, then lose the job when the process crashes. Reliability requires deliberate design.

## 4. First Question: What Result Is the User Waiting For?

An email-sending action falls into one of three UX categories:

1. **Primary action**: the user is completing a core business action, and email is a secondary notification—for example, order confirmation.
2. **Email-dependent action**: the user needs the email to proceed to the next step—for example, account verification or OTP.
3. **Operational send action**: the user wants to test the sending operation itself—for example, an admin testing an SMTP connection/email.

### 4.1. Primary Actions Should Not Be Held Hostage by Non-Essential Email

If an order was saved successfully while the SMTP provider is slow, failing the checkout step because the confirmation email has not sent can make the user submit again and create duplicate orders.

### 4.2. Email-Dependent Actions Must Prioritize End-to-End Latency

For OTPs, if the email arrives too late, UX fails even if HTTP returned rapidly. Async is only one piece; you also need priority queues, provider performance, TTLs, and sensible resend rules.

### 4.3. Operational Actions Can Fit Synchronous Sending

A "Send test email to check mailbox" button can wait briefly for SMTP feedback so operators see AUTH/TLS errors right away. Still, state clearly that this is a **submission test**, not proof of inbox delivery.

## 5. Scenario Decision Matrix

| Scenario | Architectural Leaning | Appropriate UX Feedback |
| --- | --- | --- |
| Order placed successfully, confirmation email | Async via outbox | "Order confirmed; notification email is being processed" |
| Account registration and verification email | Durable async, high priority | "If the address is valid, we will send verification instructions" |
| Forgot password | Durable async, anti-enumeration security | Neutral message, never reveal account existence |
| Login OTP email | High-priority async or bounded sync per UX/SLO | Request status, countdown aligned with real code TTL |
| Admin SMTP test send | Bounded sync may fit | "SMTP accepted the test request" or config error |
| Sending PDF invoices | Async + content snapshot | "Invoice is being prepared/sent" |
| Periodic scheduled reports | Scheduled async | "Scheduled," track job status |
| Newsletter to tens of thousands of recipients | Async worker/broker | "Campaign queued," aggregate progress |
| Sensitive security alert | Durable async with priority + alerts | "Request recorded," never promise inbox |
| Simple internal send-and-wait tool | Sync with explicit timeout | Return caller-observed outcome and remediation guidance |

### 5.1. Guidance, Not Rigid Laws

A tiny app may send low-risk alerts synchronously. A high-availability platform may need async even for a simple single email.

### 5.2. Prioritize by User Benefit

If the email is not required to complete the primary action, default to separating it from the critical path. If the email is the next step, optimize total time from request until the user can actually use the email.

## 6. Measure Actual Latency Before Choosing

Latency components:

~~~text
T_total = T_validate
        + T_transaction
        + T_render
        + T_mime_build
        + T_queue_wait
        + T_smtp_submit
        + T_downstream_delivery
~~~

This is a conceptual breakdown; components can overlap in concurrent architectures.

### 6.1. Sync Request Latency

When calling `JavaMailSender.send` on the request thread, user-visible request duration bears `T_smtp_submit`. That duration can include DNS, TCP, STARTTLS, SMTP AUTH, MIME serialization, attachment I/O, DATA, and server reply.

### 6.2. Async Request Latency

The HTTP response may only wait for validation and **committing the durable intent**. Yet the user's experience of receiving the email still bears queue delay, worker time, SMTP, and downstream delivery.

### 6.3. Separate p50, p95, and p99

SMTP can be fast at p50 yet very slow at p99 when providers stall or time out. Never choose sync based solely on a single 200 ms test email in development.

### 6.4. Tail Latency Matters to the UI

If 1% of requests wait 20 seconds, users see spinners or timeouts even when the mean looks great. Examine p95/p99, failure rates, request timeouts, and UX tolerance.

## 7. SLOs and User Wait Time

There is no single "standard number" for every product. Example target metrics:

| Illustrative Metric | Meaning | Sample Team-Chosen SLO |
| --- | --- | --- |
| API request acceptance | Until durable enqueue commit | p95 under 500 ms |
| SMTP submit-call | Duration per attempt | p95 under 3 seconds when provider healthy |
| Event-to-submit | From business event to submit success | p95 under 30 seconds |
| OTP usable time | From request until code can be entered | Vast majority before TTL expires |
| Queue oldest age | Wait age of oldest pending event | Alert above threshold |
| Manual SMTP test | Maximum caller wait | Bounded budget, e.g. a few seconds |

**These values are illustrative design examples**, not Spring Framework Mail defaults or guarantees.

### 7.1. API SLO Differs from Email SLO

A fast 202 API response meets UI responsiveness, yet an email stuck for 20 minutes is still a broken user experience. Track both.

### 7.2. Never Measure Inbox Delivery by SMTP Success

When real delivery matters, integrate provider webhooks/bounce feedback of adequate reliability. Never treat `JavaMailSender.send` duration as delivery latency.

### 7.3. Tie Deadlines to Business Semantics

An OTP expiring in 5 minutes should not sit in `RETRY_WAIT` for 30 minutes. Deadlines must govern retry policies and queue priority.

## 8. When Is Synchronous a Reasonable Choice?

Sync can work well when:

- The action is explicitly **"test mail transport."**
- The user needs immediate client-side submission results to fix configuration.
- Traffic is low, payloads are small, SMTP p99 is acceptable, and timeouts are bounded.
- No long-term retries or complex durability are required.
- The API does not hold a business transaction open while sending.
- The UI surfaces outcomes honestly and handles uncertain states properly.

### 8.1. Sync Has UX Costs

An SMTP outage slows or breaks requests. If the send button can be clicked repeatedly, idempotency or resend policies are required to prevent duplicates.

### 8.2. Sync Does Not Guarantee Every Error Means Unsent

A timeout after SMTP DATA can produce an unknown outcome. The API must never blindly return "not sent, try again immediately."

### 8.3. Sync Needs a Time Budget

**`mail.smtp.connectiontimeout`**, **`mail.smtp.timeout`**, and **`mail.smtp.writetimeout`** bound I/O waits per phase. They do not necessarily establish an overall deadline for the entire SMTP operation, so observe total elapsed time and cap it to fit the runtime environment.

## 9. Example of Synchronous JavaMailSender Usage in a Service

Example internal service whose caller permissions are already checked at the API layer:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class SmtpTestMailService {

    private final JavaMailSender sender;

    public SmtpTestMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void submitTestMail(String authorizedRecipient) {
        SimpleMailMessage mail =
                new SimpleMailMessage();

        mail.setFrom("operations@example.org");
        mail.setTo(authorizedRecipient);
        mail.setSubject("Email delivery connection check");
        mail.setText(
                "This is an SMTP test email from the system."
        );

        sender.send(mail);
    }
}
~~~

The controller can call this service and return **`SMTP_SUBMITTED`** when the call completes normally, or a classified error response on exception.

### 9.1. What the Code Guarantees

- Calls `send` on the current thread.
- If `send` returns normally, client-side submit-call success can be recorded.
- If `MailException` is thrown, inspect cause/phase and respond appropriately.

### 9.2. What the Code Does Not Guarantee

- That the recipient has a real mailbox.
- That the email lands in the inbox.
- That it passes spam filtering.
- That the recipient opened the email.
- That no duplicate occurred if the final reply was lost.

### 9.3. Do Not Create an Open Mail Relay

Never expose a public API letting arbitrary users set `To`/`From`. Enforce authorization, rate limiting, sender identity, and recipient policies before calling the service.

## 10. HTTP Responses in the Synchronous Model

When the request waits on SMTP:

~~~text
POST /admin/mail-test
       |
       v
Authenticate + authorize
       |
       v
Send through SMTP
       |
       +-- send returned normally
       |      -> 200 OK + status SMTP_SUBMITTED
       |
       +-- known configuration failure
       |      -> controlled error + support action
       |
       +-- ambiguous timeout after DATA
              -> outcome UNKNOWN; avoid blind resend
~~~

HTTP **200** here only means the endpoint completed its declared operation. When the API contract is "test SMTP submission," returning an explicit status field is clear and appropriate.

### 10.1. Never Return "Delivered" Just Because send Returned

Use wording like "Mail server accepted the request" instead of "Recipient received the email."

### 10.2. UX on Timeout Errors

When uncertain whether the email was accepted, display "Unable to confirm send result; please check status before resending" instead of urging an immediate retry click.

### 10.3. Never Expose Raw SMTP Errors to End Users

Provider reply text or stack traces may leak hosts, accounts, and internal metadata. Show user-friendly messages in the UI; keep technical details in access-controlled logs/runbooks.

## 11. When Is Asynchronous Better?

Async usually fits better when:

- Email is a notification following a committed business action.
- SMTP latency and failures should not degrade primary API responses.
- The system handles multiple email types, providers, or bursty load.
- Scheduling, retries, outboxes, batching, or worker scaling are needed.
- Send intents must survive process restarts.
- Error handling/reconciliation happens outside the request lifecycle.
- Users do not need immediate SMTP submit outcomes in the response.

### 11.1. Fast Async Responses Must Still Be Honest

If the API only committed an outbox event, the accurate state is **QUEUED/ACCEPTED**, not **SENT**.

### 11.2. Async Does Not Necessarily Mean "Delayed Sending"

With healthy worker capacity, events are picked up almost immediately after commit. Async can cut user-visible latency without noticeably delaying the email; measure in practice.

### 11.3. Async Does Not Automatically Mean Resilient

In-memory executors, local queues, or bare `@Async` do not survive crashes. Choose durability matching product requirements.

## 12. Three Asynchronous Tiers and Trade-Offs

| Model | HTTP Response | Durability | Complexity |
| --- | --- | --- | --- |
| **`@Async` in the same JVM** | Before send completes | Does not survive restarts by itself | Low |
| **In-memory `ExecutorChannel`/`QueueChannel`** | Before worker sends | Not durable without a message store | Medium |
| **Durable broker or transactional outbox** | After enqueue/commit | Can be durable per config/transaction | Higher |

### 12.1. @Async Fits Best-Effort Tasks

For low-priority emails where losing work on process shutdown is acceptable, `@Async` can trim wait times. Be explicit that request success does not guarantee the task was sent.

### 12.2. Local Queues Are Not Durable Queues

`ExecutorChannel` merely hands dispatch to an executor; a standard in-memory `QueueChannel` loses data on process crashes. When persistence is needed, configure an appropriate message store/broker/outbox.

### 12.3. Outboxes Fit Critical Emails

Order confirmations, invoice notices, security alerts, and auditable workflows usually benefit from durable events + explicit retry policies and ownership.

## 13. Example Using @Async and Its Limits

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class BestEffortMailWorker {

    private final JavaMailSender mailSender;

    public BestEffortMailWorker(
            JavaMailSender mailSender
    ) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public void sendLater(SimpleMailMessage mail) {
        mailSender.send(mail);
    }
}
~~~

The application must enable async support and configure **`mailExecutor`** with appropriate thread/queue bounds.

### 13.1. @Async Does Not Enforce Transaction Commit Ordering

Calling `sendLater` inside a `@Transactional` method before commit allows the worker to run while the business transaction is uncommitted or after it rolls back. Establish explicit after-commit/outbox boundaries.

### 13.2. Exceptions Do Not Propagate Back to HTTP Callers

An `@Async void` method can throw on the worker after the HTTP response already returned. Provide dedicated exception handling, logging, and state tracking.

### 13.3. Self-Invocation Is an AOP Trap

With Spring proxy-based async, calling an `@Async` method from another method **on the same instance** bypasses the proxy and runs synchronously. Call through a Spring bean proxy or use explicit dispatch.

### 13.4. Never Mutate SimpleMailMessage After Publishing

`SimpleMailMessage` has mutable setters. Producers must never modify the same object after handing it to an async worker; construct a separate instance per request.

## 14. Why a Transactional Outbox Is Usually the Right Starting Point for Business Email

Model:

~~~text
HTTP request
      |
      v
Business transaction
      |
      +-- Update order/account state
      +-- INSERT mail_outbox event
      |
      v
COMMIT
      |
      v
HTTP response: business success + email queued
      |
      v
Background scheduled worker
      |
      +-- Claim due outbox event
      +-- Render/build MIME
      +-- JavaMailSender.send(...)
      +-- Record result
      +-- Retry/reconcile if needed
~~~

### 14.1. Atomicity Inside the Database

Business state and the outbox intent commit inside the **same database transaction**. On rollback, neither exists in that transaction.

### 14.2. SMTP Runs Outside the Transaction

Workers send after commit. Never hold database transactions open across SMTP socket I/O.

### 14.3. Outbox Enables Recovery

When a worker crashes, the event stays in durable storage. Claim leases, retry/backoff, and terminal states handle recovery.

### 14.4. Outbox Does Not Create Exactly-Once SMTP

If the relay accepts the message and the worker crashes before recording `SENT`, the event can be reprocessed. Maintain idempotent business intents, attempt history, and an **`UNKNOWN_OUTCOME`** policy.

## 15. Outbox Schema Supporting UX Feedback and Workers

PostgreSQL example:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    business_key VARCHAR(200) NOT NULL,
    mail_kind VARCHAR(64) NOT NULL,
    user_ref VARCHAR(200) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'QUEUED',
    payload_ref TEXT NOT NULL,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    deadline_at TIMESTAMPTZ,
    provider_alias VARCHAR(64),
    last_error_category VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(business_key, mail_kind)
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox(status, next_attempt_at);
~~~

This schema is illustrative; claim ownership/versioning and an attempt-history table are added where multi-worker coordination and audits are needed.

### 15.1. business_key Prevents Duplicate Intents

If a client retries an HTTP request after a lost response, the application can match the same business key and return the existing event instead of creating another email.

### 15.2. user_ref Supports Access Control

Never let users query another user's email status merely by guessing a UUID. Status endpoints must authenticate and authorize against business resources/`user_ref`.

### 15.3. payload_ref Must Be Protected

Personalized emails can hold OTPs, reset URLs, invoices, or private data. Payload references and storage require matching encryption/retention/access policies.

### 15.4. UX States and Internal States Can Differ in Granularity

The UI might need only "Processing," "Handed to mail system," or "Retrying," while workers record `errorCategory`, `attemptCount`, leases, and providers.

## 16. Transactional Enqueue Example in Spring

An illustrative service:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderConfirmationUseCase {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderConfirmationUseCase(
            OrderRepository orders,
            MailOutboxRepository outbox
    ) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID confirmAndQueueMail(
            UUID orderId,
            String authorizedUserId
    ) {
        Order order =
                orders.getOwnedOrder(
                        orderId,
                        authorizedUserId
                );

        order.confirm();

        String businessKey =
                "order_confirmed:" + orderId;

        return outbox.insertOrGetExisting(
                businessKey,
                "order_confirmation",
                authorizedUserId,
                order.mailPayloadReference()
        );
    }
}
~~~

**`OrderRepository`, `MailOutboxRepository`, and `Order`** are application abstractions. The example emphasizes **updating business state and enqueueing in one transaction**, not built-in Spring Mail APIs.

### 16.1. Pick an Appropriate Business Key

If an order can validly be confirmed multiple times or emit distinct notification versions, include version/event type in the business key so new emails are not suppressed by mistake.

### 16.2. Never Call SMTP Inside the Transaction

The use case above **never calls `JavaMailSender.send`**. Workers process the event only after commit.

### 16.3. HTTP Response After Commit

Once the service returns and the transaction commits, the API can confirm the send intent was persisted. If the commit fails, never return 202 Accepted.

## 17. REST API 202 Accepted for Asynchronous Processing

Controller example:

~~~java
import java.net.URI;
import java.security.Principal;
import java.util.UUID;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderConfirmationController {

    private final OrderConfirmationUseCase useCase;

    public OrderConfirmationController(
            OrderConfirmationUseCase useCase
    ) {
        this.useCase = useCase;
    }

    @PostMapping("/{orderId}/confirm")
    public ResponseEntity<MailQueueReceipt> confirm(
            @PathVariable UUID orderId,
            Principal principal
    ) {
        UUID eventId = useCase.confirmAndQueueMail(
                orderId,
                principal.getName()
        );

        URI statusUri = URI.create(
                "/api/mail-requests/" + eventId
        );

        return ResponseEntity
                .accepted()
                .location(statusUri)
                .body(
                        new MailQueueReceipt(
                                eventId,
                                "QUEUED"
                        )
                );
    }
}

record MailQueueReceipt(
        UUID mailEventId,
        String state
) {}
~~~

This example assumes proper authentication and authorization on the order. Some applications should return **200/201** for the primary order-confirmation action and describe email as an enqueued side effect rather than forcing 202 merely because email runs asynchronously.

### 17.1. What Does 202 Mean?

In standard HTTP semantics, **202 Accepted** means the request has been accepted for processing, though processing has not necessarily finished. It fits best when the API action itself is asynchronous.

### 17.2. When Is 200 or 201 Better?

If the primary business operation (e.g., confirming an order) completed in the database, returning **200 OK** or **201 Created** per resource semantics can be more accurate. Email queueing is a secondary attribute that need not turn the entire HTTP action into 202.

### 17.3. Never Return 202 Before Durable Enqueue Succeeds

If the outbox `INSERT` has not committed when the API returns accepted, users may assume their request was saved even if it rolls back afterward.

### 17.4. Location Headers Can Help

A GET status endpoint at the returned URI lets the UI check progress. Enforce authorization; never rely solely on hard-to-guess IDs.

## 18. Status-Read API and UI Mapping

A status endpoint might return:

~~~json
{
  "mailEventId": "a14d9009-20b9-4983-bdef-340074d410dc",
  "state": "PROCESSING",
  "lastUpdatedAt": "2026-11-12T09:05:00Z",
  "canRequestResend": false
}
~~~

Internal states:

~~~text
QUEUED
PROCESSING
RETRY_WAIT
SMTP_SUBMITTED
FAILED
UNKNOWN_OUTCOME
CANCELLED
~~~

### 18.1. Do Not Expose Raw Internal States If Misleading

The UI can map:

| Internal State | UX Message |
| --- | --- |
| QUEUED | Request has been received |
| PROCESSING | Processing email delivery |
| RETRY_WAIT | Sending is delayed; the system will retry if eligible |
| SMTP_SUBMITTED | Email was handed off to the mail system |
| FAILED | Could not complete sending; see next steps |
| UNKNOWN_OUTCOME | Outcome unconfirmed; please verify |
| CANCELLED | Send request canceled if not yet executed |

### 18.2. SMTP_SUBMITTED Is Not DELIVERED

If the UI says "Sent," clarify via tooltip/copy that this reflects submission. When business needs actual delivery confirmation, integrate downstream events separately.

### 18.3. canRequestResend Must Be a Server-Side Policy

Do not enable the button based solely on client state. The backend must decide whether resends are permitted with proper rate limits, deadlines, and idempotency.

## 19. Accurate UX Copy per Milestone

Concrete messages:

| Actual State | Recommended Copy | Avoid Saying |
| --- | --- | --- |
| Durable queued | "Send request has been recorded" | "Email has reached your inbox" |
| SMTP returned OK | "Email handed off to sending server" | "Recipient read the email" |
| Retry scheduled | "Temporary interruption; we will retry" | "Permanently failed" |
| Permanent failure | "Unable to send; please check the address or contact support" | "Keep retrying until it works" |
| Unknown after DATA | "Unable to confirm send result" | "Definitely not sent; click again now" |
| Provider delivered event | "Provider reported delivery" | "Recipient definitely read it" |

### 19.1. No Endless Spinners

Bound UI waiting; let users close the page, check back later, or receive alternative feedback instead of holding a connection open indefinitely for SMTP.

### 19.2. Status Should Serve User Decisions

If the user has no follow-up action, showing "Request recorded" and continuing the main flow is usually better than a multi-step progress screen.

### 19.3. Never Promise What Cannot Be Verified

Even a provider delivery webhook may only reflect destination-server acceptance. Avoid phrasing stronger than what the data actually proves.

## 20. UX for Forgot Password and Anti-Enumeration

A forgot-password API must never return:

~~~text
404 "This email is not registered"
~~~

while returning "Sent" for existing emails, because that difference allows account enumeration.

### 20.1. Neutral Response

Suggested message:

~~~text
If this email address is associated with an account,
we will send password reset instructions.
~~~

HTTP timing, rate limiting, and error behavior must also minimize side-channel leaks.

### 20.2. Enqueue Async Only for Existing Accounts

The request validates input, applies abuse controls, and creates an outbox intent when appropriate. The UI never reveals whether an intent was created.

### 20.3. Never Let Retries Send Expired Tokens

Mail jobs need deadlines tied to the token lifecycle. If an SMTP outage outlasts the TTL, stop and let the user initiate a fresh request.

### 20.4. Throttle Resends

"Resend" buttons need server-side cooldowns/limits and rules preventing bursts of simultaneous tokens/emails.

## 21. UX for OTPs: Fast Does Not Mean Synchronous

For email OTPs, users expect codes quickly. Two approaches:

**Option A: sync/bounded wait**

~~~text
User requests OTP
      |
      v
Generate and store challenge
      |
      v
Try SMTP submission during request
      |
      v
Return submission outcome if within budget
~~~

**Option B: durable async**

~~~text
User requests OTP
      |
      v
Persist challenge + outbox intent
      |
      v
Return accepted quickly
      |
      v
High-priority worker submits
      |
      v
User receives code later
~~~

### 21.1. Decide Using End-to-End Measurable SLOs

If high-priority async workers stay consistently fast, async can beat sync because the API does not hang when providers time out. If the product must surface config errors immediately, choose accordingly. Measure **request → usable code** time, not just HTTP latency.

### 21.2. Align TTL with the Right Starting Point

If an OTP expires 2 minutes after creation and queue delay is 90 seconds, the user gets very little time left. Consider controlled challenge issuance or skipping expired OTPs before submission.

### 21.3. Prevent Unbounded Resend Races

Rate-limit by account, address, or risk profile, deduplicate challenges properly, and never claim the prior attempt was not sent if its outcome is unknown.

### 21.4. Never Expose OTPs in Status APIs

Status responses should show only progress and non-sensitive metadata. Never put OTPs or signed reset URLs into status responses, logs, or traces.

## 22. UX for Order Confirmation

A successful checkout normally has two milestones:

1. Order state committed.
2. Confirmation email processed.

If calling SMTP synchronously inside the transaction:

~~~text
BEGIN database transaction
    |
    +-- Save confirmed order
    |
    +-- SMTP send
    |
    +-- Database commit fails
    |
    v
Customer may receive an email
for an order that was rolled back
~~~

### 22.1. Transactional Outbox

Instead, commit the order and outbox event in the same transaction. The API confirms the primary business action, and email is handled afterward.

### 22.2. Layer UX Feedback

For instance, "Order confirmed. We will send details to your registered email address." Never turn a transient SMTP error into "Order failed."

### 22.3. Prevent Duplicates from Client Request Retries

If the order-confirmation request times out before the client receives a response, the client may retry. Implement idempotent order confirmation and an outbox business key so duplicate mail intents are not created.

## 23. UX for Invoices and Large Attachments

A PDF invoice may require:

- Reading business data.
- Rendering the PDF.
- Storing the file with access control.
- Building MIME multipart.
- Transferring the attachment over SMTP.
- Retrying on transient provider errors.

### 23.1. Async Usually Fits Best

Users can be directed to the invoice page or download the PDF directly in the web app while the email sends asynchronously. There is no need to block the HTTP request on file reads, rendering, and SMTP.

### 23.2. Attachments Can Be Read Lazily

When passing a resource to `MimeMessageHelper.addAttachment`, bytes may be read during serialization/sending. Send-call duration includes file I/O, not just network latency.

### 23.3. Snapshots Keep Retries Consistent

If the invoice mutates after the first attempt, retrying from live data can emit altered content. Define an explicit version/snapshot policy.

### 23.4. Large Files Require Capacity Planning

Govern message size, quotas, memory, streaming, and attachments; never assume `@Async` solves provider limits.

## 24. Status UI: Polling, SSE, WebSocket, or None Needed?

An async API can return `eventId` and a status URI. The UI can choose:

- **No tracking**: when email is purely a secondary notification.
- **Polling GET status**: when simple updates suffice.
- **Server-Sent Events (SSE)**: when one-way server push is needed.
- **WebSocket**: when the app already needs bidirectional real-time channels.
- **Push/in-app notification**: when the user may leave the page.

### 24.1. Do Not Add WebSockets Just for Async Email

For a confirmation email, users rarely need live progress. Adding real-time infrastructure introduces unnecessary complexity.

### 24.2. Polling Needs Limits and Backoff

Do not let tens of thousands of clients poll status every 100 ms endlessly. Use moderate intervals, stop on terminal states, and stop when users leave the flow.

### 24.3. SSE/WebSocket Still Need a Durable Source

If a server restarts, push events can be missed. A database-backed status endpoint lets clients resynchronize.

### 24.4. Progress Must Reflect Real Milestones

Never show "90% delivered" just because the SMTP socket transmitted 90% of bytes. Email delivery has no standard percentage bar like file uploads.

## 25. Hybrid Model: Fast Response with Bounded Wait

Some products want fast feedback if SMTP finishes within a small budget, yet refuse to block requests when the provider is slow.

A **bounded wait** pattern:

~~~text
HTTP request
     |
     v
Durable enqueue and commit
     |
     v
Trigger worker
     |
     v
Wait briefly for recorded submit status
     |
     +-- worker finishes within budget
     |       -> return observed submit status
     |
     +-- still processing
             -> return accepted + status URL
~~~

### 25.1. Persist Durably Before Waiting

If the request times out while waiting for the worker, the outbox event remains intact and continues processing. Avoid losing intents when callers disconnect.

### 25.2. Never Wait via Busy Polling

For bounded wait, use a completion signal/future with a timeout or bounded polling. Never spin against the database continuously.

### 25.3. Handle Races and Disconnects

The worker may finish right after the HTTP wait budget expires. After the API returns 202, the client can still GET status to observe `SMTP_SUBMITTED`.

### 25.4. Bounded Wait Is More Complex Than Either Extreme

This pattern adds state coordination and edge cases; adopt it only when UX genuinely benefits from immediate submit results when fast.

## 26. HTTP Status Codes Must Reflect the Endpoint Contract

A practical table:

| HTTP Outcome | When Potentially Appropriate | Notes |
| --- | --- | --- |
| **200 OK** | Business action completed or sync op has a result | Define clearly what completed |
| **201 Created** | New resource created per REST contract | May be a `mail-request` resource |
| **202 Accepted** | Request accepted for async processing | Does not claim SMTP finished |
| **400 Bad Request** | Invalid input per public contract | Avoid account enumeration |
| **401/403** | Unauthenticated/unauthorized | Prevent endpoint becoming an open relay |
| **409 Conflict** | Action conflicts with current state | Do not use for every duplicate retry |
| **429 Too Many Requests** | API rate limit | Distinct from SMTP provider throttling |
| **5xx** | System failed to accept/process per contract | Does not automatically mean unsent |

### 26.1. 202 Should Have Trackability or Clear Semantics

HTTP 202 does not mandate a status endpoint in every protocol usage, yet for user-facing UX, a **`Location`/status URL** prevents users from guessing.

### 26.2. SMTP 421 Is Not HTTP 421

SMTP and HTTP codes belong to separate protocols. Never map SMTP reply codes `421`/`450`/`550` verbatim to HTTP status codes with the same numbers.

### 26.3. HTTP Timeouts Also Have Ambiguous Results

Clients can time out after the server already committed the outbox. When the client retries, the backend must use idempotency/business keys to return the existing event instead of creating a new intent.

## 27. Idempotency for APIs and Email Intents

Suppose a user clicks "Send invoice," the browser drops the response, and automatically retries:

~~~text
Request 1:
    Server commits mail event E
    HTTP response lost

Request 2:
    Same business operation
    Without dedup -> mail event F
~~~

Without idempotency, the system may send two emails for one user intent.

### 27.1. Business Keys

You can use:

~~~text
invoice_send:invoice-1001:version-2:recipient-42
~~~

to represent the exact same send intent. A unique index in the outbox prevents duplicate inserts for that event.

### 27.2. Client Idempotency Keys

Some APIs accept a client `Idempotency-Key`; the server stores key-to-result/request mappings. Bind them to identity, scope, and TTL so a client cannot reuse a key for a different action.

### 27.3. Idempotent Enqueue Does Not Create Exactly-Once SMTP

It prevents duplicate intents at the API layer. Workers may still retry transport after crashes and cause duplicate side effects when outcomes are unknown.

## 28. Resend UX: When Should Re-Clicking Be Allowed?

A "Resend" button is helpful yet easily causes duplicates, spam, and abuse.

### 28.1. Client-Side Cooldowns Alone Are Insufficient

Disabling a button for 30 seconds in the UI does not stop scripts from firing repeated requests. Enforce server-side rate limits and policies.

### 28.2. Distinguish Resending from Retrying

- **Background retry**: continues the same event per policy.
- **Manual resend**: user explicitly triggers a new intent or attempt under contract and audit.
- **Unknown result**: may require reconciliation before allowing.

### 28.3. Warn Users When Prior Outcomes Are Uncertain

For example: "Unable to confirm the previous send result. Check status before resending to avoid duplicate emails."

### 28.4. Never Allow Resending Expired Tokens

If an old reset/OTP token is invalid, the business flow should issue a fresh challenge in a controlled way rather than requeueing a useless old email.

## 29. Transaction Boundaries: Emails Do Not Roll Back with Databases

An anti-pattern:

~~~java
@Transactional
public void placeOrder(OrderCommand command) {
    orderRepository.save(command.toEntity());
    javaMailSender.send(
            buildConfirmationMail(command)
    );
}
~~~

If the SMTP relay accepts the message and the database commit fails, the user receives confirmation for a nonexistent order. If SMTP fails and rolls back the transaction, the order may be lost even when business rules do not require email.

### 29.1. Separate Commit Timing

With a transactional outbox, business state and mail intent commit together; SMTP send runs afterward.

### 29.2. AFTER_COMMIT Listeners Are a Lightweight Option

**`@TransactionalEventListener(phase = AFTER_COMMIT)`** avoids sending before commit within one process, yet is not durable against a crash between commit and listener completion.

### 29.3. Async Does Not Automatically Fix Transaction Semantics

Marking the sender call `@Async` can still cause the email to send **before** commit or vanish on restart. The core issue is the boundary between business commit and durable intent, not merely threads.

## 30. Durable Outbox and Worker State Machine

A state machine:

~~~text
QUEUED
   |
   v
PROCESSING (claimed)
   |
   +-- submit returned normally -> SMTP_SUBMITTED
   |
   +-- known retryable failure -> RETRY_WAIT
   |
   +-- permanent failure -> FAILED
   |
   +-- ambiguous after DATA -> UNKNOWN_OUTCOME
   |
   +-- worker crash -> recovery by lease/policy
~~~

### 30.1. Retries Must Classify Failures

- Invalid address: usually stop and fix data.
- AUTH/TLS misconfiguration: usually requires operator/config fix.
- Temporary SMTP 4xx: can back off.
- Provider throttling: cap throughput and apply provider-aware delays.
- Timeout after DATA: requires unknown/reconciliation policy.

### 30.2. Retry Budgets and Deadlines

Configure **`maxAttempts`, exponential backoff, jitter, `nextAttemptAt`, and deadlines** per `mailKind`. Never retry endlessly after users no longer need the email.

### 30.3. One Send Attempt Is Not One Delivery

Count SMTP attempts separately from unique mail events. One event may have two attempts: one failure followed by one success.

## 31. Multi-Worker and Distributed Coordination

When deploying multiple instances:

~~~text
Application A @Scheduled ----+
                             |
                             v
                         mail_outbox
                             ^
                             |
Application B @Scheduled ----+
~~~

Using `@Scheduled` alone does not prevent both from reading the same `PENDING` rows.

### 31.1. Atomic Claiming

Conditional database `UPDATE`s or **`SELECT ... FOR UPDATE SKIP LOCKED`** (PostgreSQL) let workers claim disjoint rows in short transactions.

### 31.2. Leases and Stale Owners

Store `claimOwner`, `claimUntil`, and token/version; when updating `SMTP_SUBMITTED`/`RETRY_WAIT`, verify ownership still holds. Stale workers must never overwrite state once their lease expires.

### 31.3. Never Hold Row Locks During SMTP Calls

Claim and commit first, send second; never hold database transactions open across network calls.

### 31.4. Locks Do Not Guarantee Exactly-Once SMTP

If the relay accepted DATA right before the worker crashed, a new worker may resend. Fencing protects database state; it does not force SMTP servers to reject duplicate messages.

## 32. What Happens When the HTTP Client Leaves the Page?

With sync:

~~~text
Client disconnects
      |
      v
Server may still be in SMTP send
      |
      v
Result may complete or fail later
~~~

With durable async:

~~~text
Client disconnects
      |
      v
Outbox event remains durable
      |
      v
Worker continues
~~~

### 32.1. Client Disconnect Is Not SMTP Cancellation

Closing a tab does not automatically cancel an active send call. Once DATA is transmitted, even attempting cancellation risks an ambiguous outcome.

### 32.2. Async Decouples Users from Long Tasks

Users can keep using the application while the send intent continues processing. This is a major UX advantage for emails that do not require synchronous blocking.

### 32.3. If Offering Cancellation

Promise cancellation only before SMTP submission starts, or where the system holds strict control. Canceling during `PROCESSING` races; "cancel requested" differs from "cancel completed."

## 33. Queue Depth, Priority, and Fairness Affect UX

Async can return HTTP quickly while a deep backlog still delays critical emails.

### 33.1. Separate Priorities

Example:

~~~text
High: password reset / login verification
Medium: order confirmation / invoice
Low: marketing newsletter / digest
~~~

This is an illustrative priority policy, not a mandatory ordering for all products.

### 33.2. Avoid Starvation

If workers always drain the high queue and security traffic surges, medium/low streams may starve indefinitely. Use fair scheduling/weighted queues and deadlines.

### 33.3. Isolate Provider Quotas

Different providers have different rate limits. Tune worker concurrency and routing policies to quotas rather than just raising threads.

### 33.4. Queued-State UX Should Reflect Backlogs

If the system knows emails are backed up, surface "Processing, this may take a bit longer" or use an alternative notification channel when justified.

## 34. Why You Must Never Use Async to Hide Errors

A poor design:

~~~text
POST /send
    |
    v
Enqueue to in-memory task
    |
    v
HTTP 200 "Email sent"
    |
    v
Worker throws exception
    |
    v
Task lost, no status, no retry, no alert
~~~

The UI looks snappy, yet the promise made to the user is false.

### 34.1. Choose Honest Statuses

HTTP responses on enqueue must never claim "email delivered." The backend must persist async failures to the outbox, DLQ, or error handlers.

### 34.2. Even Without a Status Endpoint, Monitoring Is Mandatory

Even when users do not track progress, operations still needs pending/retry/failed counters, alerts, and runbooks.

### 34.3. Do Not Hide Failures Behind Infinite Retries

A wrong AUTH password will not fix itself after 10,000 retries. Policies need failure classification, limits, and terminal states.

## 35. UX and Security of Email Send Status

Status APIs can inadvertently leak sensitive information:

- Whether an email address is linked to an account.
- Whether a user performed a transaction.
- Recipient addresses or Subjects.
- Reset tokens or verification URLs.
- Internal providers/accounts.
- Specific security event types.

### 35.1. Authorization by Resource Owner

An unguessable `requestId` is **not enough** to grant read access. Status GET APIs must authenticate and verify ownership/context or use narrowly scoped, short-lived access tokens.

### 35.2. Account Enumeration

For forgot-password, never return statuses distinguishing "no account" from "real email enqueued" to unauthenticated callers.

### 35.3. Never Put Secrets into Logs or SSE

Mail bodies, signed links, OTPs, credentials, or attachment content must never enter status events, logs, or traces just because the UI wants progress updates.

### 35.4. From/Recipient Validation

An email-sending endpoint must enforce recipient controls, sender identity, tenant/domain authorization, and rate limits so it cannot become a spam tool.

## 36. Observability: Measure Both Requests and Email Lifecycle

A suggested metric set:

| Metric | What It Measures |
| --- | --- |
| **`mail.api.accept.duration`** | HTTP request to durable acceptance |
| **`mail.outbox.queue.delay`** | Time event waited before worker start |
| **`mail.smtp.submit.call.duration`** | `JavaMailSender.send` duration |
| **`mail.event.to.submit.duration`** | Event creation to SMTP submitted |
| **`mail.event.terminal.failures`** | Business intents that could not submit |
| **`mail.smtp.submit.attempts`** | Actual transport attempts |
| **`mail.smtp.unknown.outcomes`** | Uncertain relay outcomes |
| **`mail.outbox.ready.count`** | Due events |
| **`mail.outbox.oldest.pending.age`** | Age of oldest waiting event |
| **`mail.outbox.retry.wait.count`** | Events in backoff |
| **`mail.worker.active`** | Active worker concurrency |
| **`mail.api.resend.requests`** | User-triggered resend requests |
| **`mail.delivery.events`** | Provider downstream events if integrated |

### 36.1. Never Substitute API p95 for Email SLO

A 100 ms HTTP 202 followed by a 5-minute queue wait is terrible UX for OTPs.

### 36.2. Never Substitute SMTP p95 for Inbox Delivery

Fast SMTP submit calls do not guarantee fast mailbox delivery. To measure delivery, integrate provider signals and document their limits.

### 36.3. Low-Cardinality Labels

Use `mailKind`, `providerAlias`, `outcome`, `priority`. Never use recipient email, `mailEventId`, tokens, or raw Subjects as tags.

## 37. Structured Logging and Tracing Across Three Milestones

Log on durable enqueue:

~~~json
{
  "event": "mail.request.accepted",
  "mailEventId": "event-42",
  "mailKind": "order_confirmation",
  "state": "QUEUED"
}
~~~

Log when an SMTP attempt completes:

~~~json
{
  "event": "mail.smtp.attempt.finished",
  "mailEventId": "event-42",
  "attemptId": "attempt-2",
  "providerAlias": "smtp-primary",
  "outcome": "success",
  "durationMs": 950
}
~~~

Log when the provider reports downstream delivery:

~~~json
{
  "event": "mail.delivery.status.updated",
  "mailEventId": "event-42",
  "providerAlias": "smtp-primary",
  "deliveryState": "delivered"
}
~~~

### 37.1. Three Events Are Not Equivalent

A queued event might never submit. A submitted event might bounce. A delivered webhook must be verified/authenticated per provider contract.

### 37.2. Tracing Across the Outbox

Request traces and worker traces may be minutes apart. Use trace context/span links and `mailEventId` to correlate, never treating trace IDs as the sole durable business key.

### 37.3. Protect Content

Logs/traces should carry only permitted metadata. Never dump `MimeMessage` payloads or SMTP AUTH transcripts.

## 38. Scenario: User Clicks the Button Twice

A user submits a request, watches a spinner, sees no response yet, and clicks again.

### 38.1. Sync Can Send Twice

Request A is waiting on SMTP while Request B also invokes the sender. Both can succeed, leaving the recipient with two emails.

### 38.2. Async Can Also Create Two Intents

If the API blindly enqueues on every POST, two requests create two outbox rows.

### 38.3. Solutions

- Temporarily disable the UI button to curb accidental double-clicks.
- Enforce backend idempotency/business keys against duplicate requests.
- Apply cooldowns and rate limits for resends.
- Provide clear status URLs so users check progress instead of re-clicking.
- Distinguish intentional resends from automatic retries.
- When outcomes are unknown, never automatically spawn another send.

### 38.4. Frontend Is Not the Sole Guarantee

Disabling buttons does not stop network retries, multiple tabs, or scripts. Idempotency belongs on the server.

## 39. Scenario: Provider Outage During Peak Traffic

Suppose:

~~~text
1000 users place orders in one minute
SMTP provider temporarily unavailable
~~~

**Sync design coupling email to checkout:**

- HTTP requests block waiting on SMTP timeouts.
- Many users assume checkout failed.
- Users retry, risking duplicate orders.
- Database connections and request threads exhaust faster.

**Async outbox design:**

- Order transactions commit and APIs respond cleanly.
- Outbox holds confirmation emails.
- Workers classify the provider outage, back off, and throttle.
- Dashboards alert on retry backlogs; emails send once the provider recovers per policy.

### 39.1. Async Does Not Eliminate Sending Responsibility

Operations still needs alerts on oldest pending age, terminal failures, and SLOs. Never let backlogs grow silently.

### 39.2. Never Flush the Entire Backlog at Once on Recovery

Rate limiters, bounded worker concurrency, and retry jitter prevent retry storms.

### 39.3. When Email Is the Core Product Feature

An email marketing platform may need explicit scheduling/dispatch semantics and accurate progress tracking rather than just saying "sent" upon queueing.

## 40. Scenario: Admin Wants to "Send Test Email" Immediately

An admin configures SMTP host, credentials, and STARTTLS, then clicks "Send test."

### 40.1. Sync Surfaces Config Errors Directly

The app can invoke `JavaMailSender.send` inside a bounded request and show "SMTP submission succeeded" or "Authentication failed"/"TLS certificate mismatch."

### 40.2. Never Make Admins Wait Indefinitely

Configure timeouts and an overall request budget/UX fallback. If a timeout leaves post-DATA status uncertain, never report "definitely not sent."

### 40.3. TestConnection and Send Test Differ

A connection test can partially verify connectivity/login, yet does not prove permission for a specific `From` or relay acceptance of a MIME message. A test send is a separate operation with side effects.

### 40.4. Do Not Mandate Inbox Arrival as Synchronous Feedback

Even when SMTP submission succeeds, inbox arrival takes time afterward. The UI can guide admins to check the mailbox and inspect logs/provider status if needed.

## 41. Testing Sync/Async Architecture Around UX

Test groups:

| Group | Scenario | Expected Behavior |
| --- | --- | --- |
| Sync | Sender returns normally | API returns `SMTP_SUBMITTED`, never claims delivered |
| Sync | AUTH invalid | Technical failure classified, no secrets leaked |
| Sync | SMTP timeout | Honest response regarding uncertainty |
| Sync | Slow provider | Timeout/budget and proper UX fallback |
| Async | Durable enqueue succeeds | API returns accepted and status URL |
| Async | Enqueue transaction rolls back | API never returns accepted |
| Async | Worker succeeds | Event transitions `QUEUED` → `SMTP_SUBMITTED` |
| Async | Worker temporary failure | `RETRY_WAIT` with `nextAttemptAt` |
| Async | Worker permanent failure | `FAILED` + actionable reason |
| Async | Timeout after DATA | `UNKNOWN_OUTCOME`, no blind retry |
| Async | Worker crashes | Event remains durable; recovers |
| Async | Client disconnects | Committed intent continues processing |
| UX | Double-click/resend | Server-side idempotency/cooldowns |
| UX | Forgot-password | Does not leak account existence |
| UX | OTP expired | Does not send expired codes |
| Multi-worker | Concurrent claim | Never two concurrent active owners |
| Observability | Fast API, slow queue | Both latency metrics distinct |
| Security | Another user's status GET | Forbidden/not found per policy |

### 41.1. Unit Tests Do Not Need Real SMTP

Mock `JavaMailSender` to test service/controller/worker decisions. Use a fake `Clock` and stub outbox repository for timeout/deadline states.

### 41.2. Integration Tests Need a Real Database When Relying on Locks

If production uses PostgreSQL `FOR UPDATE SKIP LOCKED`, use a PostgreSQL test engine (e.g., via Testcontainers) to test concurrent claims; mocks cannot prove DB locking semantics.

### 41.3. SMTP Capture Servers

Use an SMTP capture server in test environments to verify MIME content and submission mechanics without sending production emails.

## 42. Example Test for Async Response Before SMTP Sends

Illustrative controller unit test with Mockito:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.security.Principal;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class OrderConfirmationControllerTest {

    @Test
    void returnsAcceptedAfterDurableEnqueue() {
        OrderConfirmationUseCase service =
                mock(OrderConfirmationUseCase.class);

        UUID orderId = UUID.randomUUID();
        UUID mailEventId = UUID.randomUUID();

        when(service.confirmAndQueueMail(
                eq(orderId),
                eq("user-42")
        )).thenReturn(mailEventId);

        OrderConfirmationController controller =
                new OrderConfirmationController(service);

        Principal principal = () -> "user-42";

        var response = controller.confirm(
                orderId,
                principal
        );

        assertEquals(
                HttpStatus.ACCEPTED,
                response.getStatusCode()
        );

        assertNotNull(response.getBody());
        assertEquals(
                "QUEUED",
                response.getBody().state()
        );

        verify(service).confirmAndQueueMail(
                orderId, "user-42"
        );
    }
}
~~~

### 42.1. What Does the Test Prove?

The controller returns 202 and `QUEUED` per service contract without opening an SMTP connection. It does not prove outbox durability—transaction persistence needs a separate integration test.

### 42.2. Test Absence of Immediate Sends at the Right Layer

If the controller does not inject `JavaMailSender`, it has no direct send dependency. Integration tests can verify workers process after commit using a fake sender and matching outbox states.

### 42.3. Test Rollbacks

If outbox insertion fails/rolls back, the request must never return accepted. Use a real-database transaction integration test rather than just mocking service returns.

## 43. Quick Decision Matrix

When evaluating a new feature, answer:

| Question | If "Yes" | Direction to Consider |
| --- | --- | --- |
| Is email only a side effect after a primary business action? | Yes | Durable async |
| Does the user need immediate SMTP submit results? | Yes | Bounded sync or bounded wait |
| Does provider p99 exceed UX budgets? | Yes | Async or explicit fallback |
| Must emails survive restarts? | Yes | Durable outbox/broker |
| Does the email have a short deadline/TTL? | Yes | High-priority async + SLO or considered sync |
| Are there thousands of recipients? | Yes | Async workers/batching |
| Can retries exceed request timeouts? | Yes | Outbox `nextAttemptAt` |
| Are there multi-node workers? | Yes | Atomic claims/leases |
| Is progress visibility needed? | Yes | Status resource/polling/push |
| Is there an account enumeration risk? | Yes | Neutral UX response |
| Are duplicate emails harmful? | Yes | Idempotency + unknown-outcome policy |
| Must admins fix SMTP errors right away? | Yes | Sync diagnostic workflow |
| Does the UI not need send completion? | Yes | Accepted copy + ops monitoring only |

### 43.1. Avoid Mechanical Answers

Not every email must be async; not every OTP must be sync. Decisions must start from **users, tolerable wait times, reliability, and genuinely verifiable states**.

### 43.2. Choices Can Differ Within the Same Product

One system can use sync for admin SMTP tests, durable async for order confirmations, high-priority async for OTPs, and campaign queues for newsletters.

## 44. Anti-Patterns in Sync/Async Decisions

| Anti-Pattern | Problem | Remedy |
| --- | --- | --- |
| Calling SMTP inside `@Transactional` checkout | Email can send before rollback | Business commit + outbox |
| Returning 200 "Email delivered" on `send` return | False semantics | `SMTP_SUBMITTED` |
| Returning 202 before queue commit | Promise lacks durability | Commit then respond |
| `@Async void` ignoring exceptions | Email lost silently | Error states/monitoring |
| Calling an in-memory queue durable | Tasks lost on restart | Durable store/broker |
| Picking async solely for fast HTTP | Hides backlogs/provider outages | End-to-end SLOs |
| Picking sync because "email is important" | Slow requests, failure coupling | UX/latency/reliability analysis |
| Waiting synchronously for inbox delivery | No such guarantee | Separate downstream lifecycle |
| Unbounded spinners | Stuck UX | Bounded wait + status resource |
| Polling status every 100 ms | Wastes load | Backoff/bounded polling |
| Letting clients decide resends freely | Spam, duplicates | Backend policies/idempotency |
| Double-click creating two outbox rows | Duplicate emails | Unique business intents |
| Retrying every timeout | Unknown-after-DATA duplicates | Reconciliation policy |
| `@Async` running before transaction commit | Wrong-data notifications | After-commit/outbox |
| Worker marking `SENT` on enqueue | No SMTP submit yet | Accurate milestone states |
| Status GET without authorization | Leaks personal data | Resource access control |
| Forgot-password reporting account missing | Account enumeration | Neutral copy |
| No OTP retry deadline | Sends expired codes | TTL-aware policies |
| Using HTTP 429 arbitrarily for internal SMTP throttles | Wrong API semantics | Separate API limits and provider limits |
| Measuring request p95 only | Misses queue delays | Event-to-submit metrics |
| Logging/tagging recipients or OTPs | PII/secret leaks | Safe telemetry |
| Multi-node `@Scheduled` without claims | Two workers double-send | Atomic ownership |
| Ignoring unknown outcomes | Duplicates on retry | Explicit `UNKNOWN_OUTCOME` |

## 45. Frequently Asked Questions

**1. Is sending an email inside a controller always wrong?**

No. A low-traffic internal SMTP test tool can use sync reasonably. Placing mail on the critical path of core business actions, however, increases coupling and latency.

**2. If we use @Async, is the email guaranteed to be sent?**

No. `@Async` only switches execution threads per config; it does not provide durable storage or retries across restarts.

**3. Is async always faster?**

API responses are usually faster when waiting only for enqueue, yet emails can arrive late if backlogs grow. Measure end-to-end times.

**4. Does JavaMailSender.send returning normally mean the inbox received it?**

No. That is submit-call success, not proof of downstream delivery or reading.

**5. Why does HTTP 202 not equal SMTP success?**

202 generally means the server accepted the request for processing while work remains unfinished. APIs must reflect their exact contracts.

**6. When should you return 200 instead of 202?**

When the primary business operation completed, returning 200 can be right even if email is queued in the background. A background async side effect does not mandate 202.

**7. If a request times out, should the user click again?**

Not automatically. The server may have committed the outbox or SMTP may have accepted. Provide idempotency keys/status endpoints to inspect outcomes.

**8. Does every email need a status endpoint?**

No. If email is just a secondary alert, the UI may skip progress tracking. Still keep monitoring and durable state when reliability matters.

**9. Should OTPs be sync or async?**

Depends on end-to-end SLOs, worker priority, time budgets, and UX. High-priority durable async often fits well, provided time-to-usable-code and TTLs are measured.

**10. Should forgot-password report whether an email was actually sent?**

Use neutral messaging to prevent account enumeration regardless of whether an intent was created.

**11. Does a transactional outbox completely prevent duplicates?**

No. It makes intents durable and separates business commits, yet cannot create an atomic transaction between the database and an SMTP relay.

**12. Should JavaMailSender be called inside a @Transactional method?**

Technically possible but risky: SMTP side effects never roll back when the DB rolls back. Outbox/after-commit fits better when consistency matters.

**13. Is @TransactionalEventListener(AFTER_COMMIT) enough?**

It prevents firing before commit in-process under proper conditions, yet does not protect against a crash after commit before the listener finishes. Outboxes are stronger for durability.

**14. If the provider is down for 20 minutes while the API returns 202, is that still success?**

API acceptance succeeded, yet the email SLO may still fail. Track retry backlogs, oldest pending age, and terminal failures separately.

**15. Is a WebSocket required for email status updates?**

No. Polling or no progress display often suffices; add SSE/WebSockets only when UX genuinely needs real-time updates.

**16. Does sync reduce duplicates?**

Not automatically. HTTP timeouts and user retries still trigger multiple submissions. Idempotency and unknown-outcome policies are still required.

**17. Should confirmation emails and marketing newsletters share one queue?**

They can share infrastructure, yet priorities, quotas, deadlines, and fairness should be isolated so marketing never delays critical emails.

**18. Can we display "100% sent successfully" when outbox pending hits zero?**

No. Some events may be `FAILED`/`UNKNOWN_OUTCOME`, and SMTP submitted does not mean downstream delivered. Define denominators and milestones clearly.

**19. What if an admin needs immediate confirmation of SMTP credentials?**

A bounded synchronous test send can fit, with timeouts, access controls, and copy asserting only the submission result.

**20. Should emails be resent immediately on SocketTimeoutException?**

Not without knowing the phase. Timeouts after DATA can indicate ambiguous acceptance; use `RECONCILE`/`UNKNOWN_OUTCOME`.

**21. Why not use an in-memory queue?**

Because process restarts lose pending work. Choose a durable outbox/broker whenever users are promised later processing.

**22. Can delivery be tracked with JavaMailSender?**

No standard `JavaMailSender` API guarantees downstream delivery status. Integrate provider-specific events if required.

**23. Should users be allowed to cancel an in-flight email?**

Confirm cancellation only before transport submission begins; once `PROCESSING` or transmitting DATA, races and uncertain outcomes exist.

**24. When should a bounded-wait hybrid be used?**

When users benefit if SMTP finishes rapidly yet must not wait past a tight budget. Combine durable enqueueing with a status endpoint for the remainder.

**25. Can UX be measured with HTTP latency alone?**

No. For email-dependent flows, measure event-to-submit/delivery indicators plus user resend/abandon rates, not just API p95.

## 46. Takeaways on Choosing Sync vs. Async by User Experience

**Deciding between synchronous and asynchronous email must start from user needs and the system's response contract, not technical preference.** Sync lets the request wait for the caller-observed SMTP submission result, fitting config diagnostics or bounded internal tools. Async lets the API respond once the system **durably persists the request**, fitting emails that are side effects, need retries/scheduling, or must not block critical HTTP paths.

**Never conflate three milestones**: durable request accepted, SMTP submission completed, and downstream delivered. HTTP 202 usually means "accepted for processing," not "finished sending"; `send` returning normally does not prove inbox receipt. UIs must use truthful statuses/copy and add polling/SSE/WebSockets only when users genuinely need tracking.

For critical workflows, commit **business state + transactional outbox intent** in the same transaction, then let workers claim and send after commit. Enforce retries/backoff, `maxAttempts`, deadlines, idempotency, leases, and state tracking; treat **`UNKNOWN_OUTCOME`** after SMTP DATA carefully to avoid duplicates. Never rely on `@Async` or in-memory queues as a durability guarantee without backing storage.

Finally, **measure both HTTP response time and event-to-SMTP-submission latency**, monitoring backlogs/age and downstream signals where integrated. A sound architecture does more than make screens feel faster—it gives users truthful feedback, prevents repetitive clicks, and provides clear remediation paths when emails are delayed or fail.
