# Multi-Tenant Handling and Quota Isolation

## 1. The email-sending problem in multi-tenant applications

In a system using **Spring Framework Mail**, a single application may serve multiple **tenants** concurrently: companies, organizations, stores, customer groups, or data-isolated workspaces. Each tenant may own a different sender, domain, email template, recipient list, budget, and security policy.

When all tenants share **JavaMailSender** and the same SMTP provider, limit and performance failures can spread across tenants:

- Tenant A sends a large campaign and exhausts the quota, delaying Tenant B's OTP emails.
- One tenant continuously retries on SMTP 4xx errors, increasing pressure on the provider and affecting all remaining tenants.
- Workers picking jobs in creation order (FIFO) allow high-volume tenants to starve low-volume tenants.
- Sender configuration or **mail.smtp.from** is mutated on a singleton bean while handling another tenant, resulting in the wrong From/Return-Path.
- Requests submitting many large attachments exhaust memory, threads, or bandwidth across the entire service.
- Rate limits live only in one instance's memory and stop holding once the application scales out across multiple pods.
- An authentication error or locked account for Tenant A causes the entire shared mail worker pool to fail.

Therefore, **multi-tenant handling and quota isolation** is more than counting emails. It requires design across **tenant identification**, **authorization**, **quotas**, **scheduling**, **SMTP providers**, **system resources**, **retries**, and **monitoring**.

The goal of this article is to build an architecture that lets each tenant use its allocated capacity, prevents reading or misusing another tenant's resources, and still allows sharing mail-sending infrastructure efficiently.

## 2. A tenant is a boundary for permissions and resources

A tenant can be identified by a stable **tenantId**. However, `tenantId` is not simply a string read from an HTTP header and trusted blindly.

Example request flow:

~~~text
HTTP request / authenticated event
               |
               v
Authentication + authorization
               |
               v
Trusted tenant context
  tenantId = tenant-A
  permission = MAIL_SEND
               |
               v
Notification request
               |
               v
Outbox / quota / sender routing
               |
               v
SMTP submission
~~~

Principles:

1. `tenantId` must come from an **authenticated and authorized context**, not from a client-supplied `tenantId` field left unverified.
2. Every query for notifications, templates, sender configuration, and quotas must be scoped to the corresponding tenant.
3. A tenant must not arbitrarily select SMTP credentials, From domains, bounce addresses, or provider accounts belonging to another tenant.
4. Background workers must carry tenant identity **with the persisted job**, because the worker thread no longer has the original HTTP request context.
5. As a task moves across queues, databases, schedulers, and SMTP, `tenantId` must remain consistent so the wrong quota or template is never used.

**Isolating quotas without isolating data access permissions is not enough.** Conversely, proper authorization where all tenants share an uncoordinated quota can still cause cross-tenant performance impact.

## 3. Isolation layers in a mail system

A multi-tenant architecture can be divided into layers:

~~~text
                       APPLICATION
          +----------------+----------------+
          |                |                |
       Tenant A         Tenant B         Tenant C
          |                |                |
          +------- Authenticated API -------+
                           |
                           v
                  Notification Outbox
                 (tenant_id + event_id)
                           |
                           v
                 Quota + Admission Gate
                 /         |          \
            Per tenant  Per stream   Global limits
                 \         |          /
                           |
                           v
                    Fair Scheduler
                           |
                           v
                  Worker / In-flight Gate
                           |
                           v
              SMTP Sender / Provider Router
                 /         |          \
            Provider 1  Provider 2  Dedicated account
                           |
                           v
                      SMTP servers
                           |
                           v
                    Delivery feedback
                           |
                           v
             Per-tenant status and metrics
~~~

These layers address distinct goals:

| Layer | Responsibility |
|---|---|
| Authorization | Prevents a tenant from accessing or impersonating another tenant's resources |
| Admission/quota | Limits the number of notifications or resources allowed for use |
| Scheduler | Allocates processing time fairly when multiple tenants have pending work |
| In-flight gate | Caps concurrent connections/submissions |
| Sender routing | Selects valid SMTP account, domain, credentials, and provider |
| Retry policy | Prevents one tenant's failures from creating an infinite retry loop |
| Delivery feedback | Attributes bounces, deferrals, and deliveries back to the right tenant |
| Monitoring | Detects a tenant or provider consuming abnormal resources |

There is no **single `spring.mail` setting** that automatically solves all of this. **JavaMailSender** provides the mail-sending API; tenant/quota control is the responsibility of the application architecture or orchestration services around it.

## 4. Types of quotas to distinguish

The word "quota" is often used for several different limits. They are not equivalent.

| Type | Example | Meaning |
|---|---|---|
| **Daily volume** | 50,000 recipients/day | Caps total daily send volume |
| **Hourly volume** | 5,000 recipients/hour | Prevents a tenant from packing huge volume into one hour |
| **Rate** | 20 recipients/second | Limits average speed or short bursts |
| **Burst** | Up to 100 accumulated tokens | Allows short, bounded spikes |
| **Concurrency** | Max 4 concurrent SMTP submissions | Limits in-flight resources |
| **Payload bytes** | Total 200 MB MIME/day | Limits mail bandwidth/volume |
| **Per-message size** | Max 10 MB MIME/message | Prevents an oversized message |
| **Recipient count** | Max 50 recipients/message | Restricts fan-out and list exposure risk |
| **Pending backlog** | Max 10,000 waiting jobs | Prevents unbounded queue growth |
| **Retry budget** | Max 4 attempts/notification | Prevents retry storms |
| **Provider quota** | 100 messages/s on an account | Avoids exceeding ESP-enforced limits |

Many providers meter quotas by **recipient**, not by send call. One `MimeMessage` sent to 5 recipients may consume 5 quota units on that provider. Conversely, some limits count per message or API request. **Read the provider's quota contract and define the accounting unit in the application**; do not assume every SMTP server applies the same rule.

### Hard and soft quotas

- **Hard quota:** rejects further allocations once the budget is exhausted.
- **Soft quota:** allows exceeding up to a point while raising alerts or queuing.
- **Burst capacity:** permits high throughput briefly before requiring callers to wait for token refill.
- **Reserved capacity:** sets aside capacity for critical streams such as OTP/security.

A system may use all four, but accepted, deferred, and rejected states must be clearly defined so callers do not assume a message was sent when it was only queued.

## 5. Distinguishing quotas by tenant, stream, and provider

Suppose a tenant has both transactional and marketing email:

~~~text
Tenant A
    |
    +-- transactional: 1,000 recipients/hour
    +-- security:        500 recipients/hour
    +-- marketing:    10,000 recipients/day
    |
    +-- tenant total: 12,000 recipients/day

SMTP Provider P
    |
    +-- account-wide: 50 recipients/second
    +-- 5 concurrent SMTP sends

Mail service
    |
    +-- global CPU/thread/memory limit
~~~

A send proceeds only when **all applicable limits** are satisfied, for example:

~~~text
ALLOW_SEND =
    authorizedTenant
    AND tenantDailyBudget
    AND streamBudget
    AND providerRateBudget
    AND tenantConcurrencyAvailable
    AND globalConcurrencyAvailable
    AND messageSizeAllowed
~~~

Tenant quotas cannot substitute for provider quotas: each tenant may stay under its own threshold while the sum across all tenants still exceeds the ESP's rate limit.

### Why are per-stream quotas needed?

If marketing and security share a single tenant quota, a campaign can consume the entire send allowance and delay OTPs. One option is a **separate security budget** or reserved capacity, while still maintaining global system limits and anti-abuse controls.

This does not mean security emails bypass all quotas. Sensitive notifications still need protection against mass generation, abuse, and expiration.

## 6. Choosing the quota unit: message, recipient, or byte?

Consider an email:

~~~text
From: notices@example.com
To:   10 addresses
Cc:    2 addresses
Bcc:   3 addresses
Attachment: 4 MB
~~~

Consumption can be measured as:

| Accounting unit | Consumption in example |
|---|---:|
| SMTP message count | 1 |
| Recipient count | 15 |
| MIME transfer bytes | Message size after encoding, potentially larger than 4 MB |
| SMTP send attempts | 1 initially, increases on retry |
| Notification-recipient records | Could be 15, depending on business model |

If tenant quotas are defined per recipient, counting **one `JavaMailSender.send(...)` call** is insufficient. Count the actual requested recipients and split partial success/rejection results when the provider reports them.

For Bcc, recipients still count toward quotas. **Hiding addresses in headers does not exempt Bcc from provider charges or rate limits**.

### MIME size differs from raw file size

Attachments are typically Base64-encoded and add headers, boundaries, and line wrapping. Therefore, **a 4 MB file does not mean a 4 MB MIME email**. When enforcing size limits, you can:

1. Enforce source size limits before constructing MIME.
2. Estimate MIME size with a safety margin.
3. When exactness is required, measure serialized size or provider limits before submitting.

Avoid serializing a huge email repeatedly just to check quota if doing so causes memory or I/O pressure. For large attachments, consider object storage with secure download links instead of direct attachment.

## 7. Quota admission differs from retry throttling

Suppose a tenant is allowed 1,000 notifications/day. One notification is attempted three times due to SMTP 451:

~~~text
Notification N100
  |
  +-- Attempt 1: SMTP 451
  +-- Attempt 2: TCP timeout
  +-- Attempt 3: Accepted
~~~

There are two ways to account for this:

- **Business quota:** one notification (or its corresponding recipient count) is charged once upon acceptance into the system or confirmation of submission, depending on product terms.
- **Transport capacity:** three attempts consume SMTP rate/concurrency/system resources, because the servers and workers genuinely processed three attempts.

If you deduct **business quota** on every retry, a tenant could lose its entire budget solely due to provider glitches. Yet if attempts are uncapped, one job can hold workers and generate continuous load.

Therefore, separate them:

~~~text
Tenant business allowance
      |
      v
Notification accepted once
      |
      v
Outbox
      |
      +-- Retry 1
      +-- Retry 2   -> all subject to transport rate/concurrency
      +-- Retry 3
~~~

The quota policy must state clearly when quota is deducted, when it is refunded, and what defines a single notification. It must not be determined accidentally by where a `Counter.increment()` call happens to sit.

## 8. When to reject, when to queue?

When a tenant sends too fast, there are at least three options:

| Status | Meaning | When appropriate |
|---|---|---|
| **REJECTED_QUOTA** | Request exceeds hard quota and is not accepted | Budget exhausted or policy violated |
| **DEFERRED_RATE** | Valid request waiting for a slot/token | Short-term rate smoothing |
| **ACCEPTED_QUEUED** | Send intent persisted for later worker processing | Asynchronous sending within SLA |

Example API response:

~~~json
{
  "notificationId": "N-100",
  "status": "ACCEPTED_QUEUED",
  "tenantId": "tenant-A"
}
~~~

**ACCEPTED_QUEUED does not mean SMTP SUBMITTED**. If the application returns status to a UI, use explicit names and provide a status-lookup API.

When a daily quota is exhausted, queuing until the next day may be fine for marketing but useless for an OTP expiring in minutes. Decisions must account for **notification deadline/TTL**.

## 9. Tenant isolation does not mean every tenant gets a dedicated SMTP server

Several deployment models exist:

| Model | Characteristics | Trade-offs |
|---|---|---|
| **Shared SMTP account** | Multiple tenants share credentials/account | Low cost, but quota and reputation share the same account |
| **Per-tenant SMTP account** | Each tenant has dedicated credentials/account | Stronger quota/provider isolation, higher configuration and ops complexity |
| **Shared provider, dedicated pools** | Same ESP with separate pools/accounts/IPs/streams per group | Balances isolation and cost |
| **Multiple ESPs** | Router picks provider by tenant/stream | Redundancy and quota control, but complex bounces, DKIM, and reconciliation |

**Logical isolation** can stop tenants from hogging each other's workers/queues, yet a shared SMTP account still shares **physical limits and sender reputation**. Never promise "complete tenant independence" when the provider enforces account-wide limits.

When strict isolation is required (legal, compliance, reputation, customer-owned domains, dedicated quotas), dedicated accounts or dedicated pools may fit better.

## 10. Multi-tenant data model for email

A system should separate these entities:

~~~text
tenant
  id, status, plan, region
     |
     +-- mail_sender_profile
     |     tenant_id, provider_id, verified_from_domain,
     |     secret_ref, tls_policy, active_version
     |
     +-- mail_quota_policy
     |     tenant_id, stream, window, limit_units,
     |     max_inflight, max_message_bytes
     |
     +-- notification_outbox
           tenant_id, notification_id, event_id,
           stream, recipient_ref, status,
           next_attempt_at, expires_at
                    |
                    +-- mail_attempt
                    |     attempt_id, result, provider_id,
                    |     failure_category, created_at
                    |
                    +-- delivery_event
                          provider_event_id, recipient_ref,
                          delivered/bounced/deferred, event_at
~~~

Important keys and relationships:

- Every **notification_outbox** row needs an explicit `tenantId` and a stable business identifier.
- **Idempotency key** should be unique within the tenant and relevant notification kind, not necessarily globally across tenants.
- Sender profiles and quota policies must be fetched by authenticated `tenantId`.
- Retry attempts and delivery events must link back to the notification/recipient belonging to the proper tenant.
- Never use a notification code that can collide across tenants while omitting `tenantId` from queries.

Example unique constraint:

~~~sql
CREATE UNIQUE INDEX uq_notification_intent
ON notification_outbox (
    tenant_id,
    business_event_id,
    notification_kind,
    recipient_key
);
~~~

This is illustrative SQL; actual column and key names depend on how the system defines a notification. The goal is preventing **the same business event from creating multiple send intents** due to HTTP retries or event replays.

### Should recipient email be stored in the quota record?

Usually **no**. Quotas only need tenant, stream, window, and consumed count. Putting email addresses into quota keys increases sensitive data exposure, row counts, and errors in aggregate limit calculations.

## 11. Tenant context in requests and background workers

During an HTTP request, the application can obtain `tenantId` from an authenticated security context. However, **workers** execute later, possibly in another process without any request context.

Avoid:

~~~java
// Anti-pattern: async worker relies on the tenant stored
// in a previous HTTP request's ThreadLocal.
String tenantId = TenantContextHolder.getCurrentTenant();
sendOutboxEmail(tenantId);
~~~

Problems:

- Another thread does not have that `ThreadLocal`.
- Thread pools reuse threads and can leak stale context if not cleared.
- A scheduled job has no HTTP request at all.
- Tenant identity can shift between notification creation and worker execution.

Instead, store `tenantId` **in the outbox record** when recording the send intent and pass it explicitly:

~~~java
public record ClaimedNotification(
        String notificationId,
        String tenantId,
        String stream,
        String recipientRef,
        String businessEventId
) {
}
~~~

The worker queries profiles and quotas using **claimed.tenantId()** after verifying the record and processing permission. If parts of the system still carry a request security context, never allow it to silently override the outbox's `tenantId`.

### Tenant context is not just for logging

`tenantId` must genuinely participate in:

1. Querying the notification.
2. Loading the sender profile.
3. Resolving templates and From domains.
4. Reserving business quota.
5. Reserving concurrency/rate capacity.
6. Recording attempts and delivery status.

Adding a `tenantId` tag to logs while queries omit `tenantId` can still cause a **cross-tenant data leak**.

## 12. Selecting a sender safely per tenant

**JavaMailSender** is an interface. **JavaMailSenderImpl** can be configured with SMTP host, port, username, password, and Jakarta Mail properties.

In a multi-tenant application, you can design:

~~~java
public interface TenantMailSenderResolver {
    org.springframework.mail.javamail.JavaMailSender resolve(
            String tenantId,
            String stream
    );
}
~~~

An architecture:

~~~text
Outbox record (tenantId, stream)
        |
        v
TenantMailSenderResolver
        |
        +-- Load authorized sender profile
        +-- Validate active status and domain
        +-- Resolve secret reference
        +-- Select provider account
        +-- Return configured JavaMailSender
        |
        v
MailService builds MimeMessage
        |
        v
JavaMailSender.send(...)
~~~

Never take **providerId**, SMTP host, or credentials directly from a tenant's request if that tenant is not authorized to manage them. If customers are allowed to bring their own SMTP server, enforce domain/ownership verification, egress/SSRF protections, host allowlists or appropriate isolation, and strict secret management.

## 13. Creating sender configurations per tenant

An immutable profile can describe a sender:

~~~java
public record SmtpSenderProfile(
        String host,
        int port,
        String username,
        String password,
        String fromAddress,
        String bounceAddress,
        boolean implicitTls,
        boolean requireStartTls
) {
}
~~~

In production code, you may not want to hold passwords inside a long-lived in-memory record; depending on policy, you may keep only a **secret reference** and fetch credentials through a credential provider. The example below focuses on mapping Jakarta Mail properties:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SenderFactory {

    public JavaMailSender create(SmtpSenderProfile profile) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(profile.host());
        sender.setPort(profile.port());
        sender.setUsername(profile.username());
        sender.setPassword(profile.password());
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");
        props.put("mail.smtp.ssl.checkserveridentity", "true");

        if (profile.implicitTls()) {
            props.put("mail.smtp.ssl.enable", "true");
        } else if (profile.requireStartTls()) {
            props.put("mail.smtp.starttls.enable", "true");
            props.put("mail.smtp.starttls.required", "true");
        } else {
            throw new IllegalArgumentException(
                    "SMTP submission must use approved TLS"
            );
        }

        if (profile.bounceAddress() != null) {
            props.put("mail.smtp.from", profile.bounceAddress());
        }

        return sender;
    }
}
~~~

This example shows how to **select a TLS mode matching the endpoint**. In a real system, validate that the profile, allowed port, domain, and account are verified; never let users pick arbitrary ports or disable TLS at will.

### Why use an immutable profile?

A sender used for Tenant A must not unexpectedly switch host, credentials, or envelope sender when another thread starts processing Tenant B. Using immutable configuration or senders built per configuration version prevents **race conditions** and simplifies tracing.

## 14. Never mutate a singleton JavaMailSenderImpl per tenant

An anti-pattern:

~~~java
// A singleton bean shared across all tenants.
JavaMailSenderImpl sharedSender;

void send(String tenantId, MimeMessage message) {
    sharedSender.setUsername(loadUsername(tenantId));
    sharedSender.setPassword(loadPassword(tenantId));
    sharedSender.getJavaMailProperties().put(
            "mail.smtp.from",
            loadBounceAddress(tenantId)
    );
    sharedSender.send(message);
}
~~~

When multiple requests run concurrently:

~~~text
Thread A: sets Tenant A's credentials
Thread B: sets Tenant B's credentials
Thread A: sender.send(...) -> may use Tenant B's credentials
~~~

The consequence is not merely sending from the wrong account or exceeding quota; it can also cause **tenant information leaks**, broken SPF/DMARC alignment, and messy bounce reconciliation.

Alternatives:

- Maintain **separate senders per tenant/profile version**.
- Use a **sender factory** that constructs a fully configured object before sending.
- If caching senders, key by **tenantId + configVersion** and never mutate fields while sending.
- Manage TTL/eviction and secret rotation explicitly.
- If the provider supports per-message envelope senders, use the proper API instead of mutating shared properties across threads.

**Never treat the fact that `JavaMailSenderImpl` can be called from multiple threads as license to mutate its configuration during sends.**

## 15. Managing sender lifecycle and credential rotation

If you have thousands of tenants, pre-creating a `JavaMailSender` for every tenant can waste memory, increase secret-lookup costs, and complicate configuration updates. Conversely, recreating every object/profile per notification can overload the database or secret manager.

A sensible mechanism:

~~~text
Tenant + Stream
       |
       v
Sender registry
       |
       +-- Check active config version
       +-- Cache bounded by size and inactivity
       +-- Resolve secret via controlled credential provider
       +-- Create sender if missing
       |
       v
Configured sender
~~~

When credentials rotate:

1. Persist the new profile version and update the secret.
2. Invalidate the cache key for the old version.
3. Let in-flight sends using the old version finish or fail according to policy.
4. Dispatch new jobs with the new profile.
5. Monitor AUTH failures during the transition window.

Depending on the environment, some SMTP transports retain connections or sessions beyond a single `send` call. Inspect real transport lifetimes when implementing caching/pooling rather than assuming every API provides a safe built-in connection pool.

### Never use Spring profiles as the sole tenant selector

**`spring.profiles.active=production`** only distinguishes environment configurations. It does not represent thousands of tenants running inside the same process. Tenant routing should rely on authenticated data, a sender registry, and runtime policies.

## 16. Isolating From, Reply-To, and Return-Path per tenant

Example:

~~~text
Tenant A:
  From:     billing@brand-a.example
  Reply-To: support@brand-a.example
  MAIL FROM: bounces@bounces.brand-a.example

Tenant B:
  From:     billing@brand-b.example
  Reply-To: support@brand-b.example
  MAIL FROM: bounces@bounces.brand-b.example
~~~

The **From** address is the display header. **Reply-To** receives user replies. **MAIL FROM** is the envelope sender used for reverse-path/bounce routing.

In Spring:

~~~java
MimeMessage message = sender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        false,
        "UTF-8"
);

helper.setFrom(approvedTenantFrom);
helper.setReplyTo(approvedTenantReplyTo);
helper.setTo(recipient);
helper.setSubject(subject);
helper.setText(body, false);

sender.send(message);
~~~

**approvedTenantFrom**, **approvedTenantReplyTo**, and **recipient** are values validated by the application against tenant permissions. Configuring **mail.smtp.from** on the sender can request the envelope sender, though the ESP may restrict or rewrite that address.

If tenant domains lack proper SPF/DKIM/DMARC alignment, messages can still be rejected or land in Spam even when `JavaMailSender` succeeds. Tie sender profiles to **domain ownership and DNS verification** status per provider.

## 17. Designing durable quota windows

For a fixed limit such as **5,000 recipients in one UTC hour**, usage can be persisted per window:

~~~sql
CREATE TABLE tenant_mail_quota_window (
    tenant_id     VARCHAR(120) NOT NULL,
    stream        VARCHAR(50)  NOT NULL,
    window_start  TIMESTAMP WITH TIME ZONE NOT NULL,
    used_units    BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, stream, window_start),
    CHECK (used_units >= 0)
);
~~~

Example:

~~~text
tenant_id = tenant-A
stream = marketing
window_start = 2026-11-12 10:00:00 UTC
used_units = 3800
limit_units = 5000
~~~

If 1,300 more recipients need to be sent, the system cannot allocate the entire batch because it would exceed **5,100**. Depending on policy, it can reject the whole batch, split out the allowed portion, or schedule for the next window.

### Standardizing window boundaries

If using an hourly window:

~~~text
10:00:00 UTC <= event time < 11:00:00 UTC
~~~

All application instances must compute the exact same `window_start`. Using consistent clocks and UTC avoids drift from time zones and Daylight Saving Time.

**Fixed windows allow boundary bursts:** a tenant can consume nearly its entire quota at 10:59 and consume a full fresh quota at 11:00. If smoother pacing is needed, combine with a **token bucket/sliding window** or provider rate limiter.

## 18. Atomic quota allocation in PostgreSQL

A common bug:

~~~text
Thread A: SELECT used = 4900
Thread B: SELECT used = 4900
Thread A: if +100 <= 5000 then UPDATE used = 5000
Thread B: if +100 <= 5000 then UPDATE used = 5000

Result: two requests were permitted,
        yet the database only recorded used = 5000.
~~~

This is a **check-then-act race**. Instead of separate read and write steps, use an atomic conditional operation.

PostgreSQL example:

~~~sql
INSERT INTO tenant_mail_quota_window (
    tenant_id,
    stream,
    window_start,
    used_units
)
SELECT
    :tenantId,
    :stream,
    :windowStart,
    :units
WHERE :units > 0
  AND :units <= :limitUnits
ON CONFLICT (tenant_id, stream, window_start)
DO UPDATE
SET used_units =
    tenant_mail_quota_window.used_units + EXCLUDED.used_units
WHERE tenant_mail_quota_window.used_units
      + EXCLUDED.used_units <= :limitUnits
RETURNING used_units;
~~~

Meaning:

- If no row exists yet, insert it when requested units are valid and within limit.
- If a row already exists, increment only when **used + requested <= limit**.
- If allocation fails, the query returns no rows.
- PostgreSQL resolves conflicts and updates the row under concurrency control, preventing two workers from reading the same `used` value and over-allocating.

### An important caveat

**:limitUnits** in the example is loaded from policy and verified for that tenant/stream. If the quota plan changes concurrently, define policy versioning and how existing reservations are handled. Never accept an arbitrary **limitUnits** from the client.

When checking **tenant total**, **stream quota**, and **daily quota** in one operation, allocate the related budgets **in the same transaction** and roll back if any level fails. Never allocate stream quota and commit stream usage when the tenant total fails.

## 19. Quota reservations must be tied to notification intent

Suppose the application:

1. Deducts quota.
2. Crashes before inserting into the outbox.

The tenant lost budget without any notification sent.

Conversely:

1. Inserts into the outbox.
2. Crashes before deducting quota.

A worker may send a notification that was never counted against budget.

For hard business quotas, perform **quota reservation and outbox insertion in one database transaction** when both live in the same transactional store:

~~~text
BEGIN TRANSACTION
    |
    +-- Check idempotency key / notification intent
    |
    +-- Reserve tenant + stream quota
    |
    +-- INSERT notification_outbox
    |      tenant_id, event_id, status=PENDING
    |
COMMIT
~~~

If quota is insufficient or insertion fails, roll back everything. If the same request is retried, the unique idempotency key returns the existing notification instead of deducting budget again.

Across multiple data stores or a separate quota service without shared ACID transactions, design explicit **reservation IDs, expiry, reconciliation, and idempotency** rather than assuming steps always succeed together.

## 20. When to refund quota and when not to

Refund rules should not depend merely on whether an exception occurred.

| State | Reference business quota handling |
|---|---|
| Request rejected before acceptance | Do not deduct |
| Notification accepted and queued | Keep reservation |
| User cancels before SMTP submission | May refund per policy |
| Message preparation fails permanently | May release reservation once confirmed unsent |
| Clear SMTP rejection, not accepted | May refund if contract bills on accepted |
| Timeout after DATA, outcome UNKNOWN | Hold pending reconciliation; do not blindly refund |
| SMTP accepted | Count/commit quota per contract |
| Delivery bounce after acceptance | Usually still consumes transport/provider capacity; business refund depends on contract |

If quota is billed as **send attempts**, an SMTP failure may still consume budget; if quota is **accepted notifications**, the policy differs. What matters is **defining it clearly and enforcing it consistently**.

### Why not refund immediately on timeout?

If the SMTP server accepted the email but the final response was lost, the application receives `SocketTimeoutException`. Immediately refunding quota and re-sending can deliver two messages to the provider while the application only counts one.

For **UNKNOWN** state, query the provider, record the attempt, and decide whether to retry or reconcile based on notification type.

## 21. Fixed window, sliding window, and token bucket

A mail-sending system typically has two classes of limits needing different algorithms:

- **Periodic budget:** total units allowed within an hour or a day.
- **Short-term rate:** rate accepted by SMTP/ESP, such as 20 recipients/second with a burst of 40.

Algorithms:

| Algorithm | Idea | Best for |
|---|---|---|
| **Fixed window counter** | Counts per fixed hour/day boundary | Periodic quotas, simple to implement |
| **Sliding window** | Counts over a rolling window from now | Curbing boundary bursts across windows |
| **Token bucket** | Accumulates tokens at a rate; each send spends tokens | Provider rate limits and controlled bursts |
| **Leaky bucket / paced queue** | Smooths outbound processing rate | Steadily pacing SMTP submissions |
| **Semaphore** | Caps concurrent operations | In-flight SMTP connections/worker load |

**A rate limiter does not replace a concurrency limiter.** A request with a huge attachment can hold a socket open for a long time even at a low average rate.

**A concurrency limiter does not replace a rate limiter.** One worker can send 100 messages quickly if each takes 10 ms, even with only one message in flight at a time.

You usually need both, plus hourly/daily budgets when the product limits total volume.

## 22. Token bucket for a tenant

For a single bucket:

- **capacity**: maximum tokens that can accumulate.
- **refill rate**: tokens added per second.
- **tokens available**: current tokens, capped at capacity.
- **cost**: tokens consumed by one operation, such as recipient count.

Example:

~~~text
Tenant A
capacity = 30 recipient tokens
refill = 10 tokens / second

t = 0:
  available = 30
  send 20 recipients -> remaining 10

t = 1s:
  add 10 tokens -> available 20
  send 25 recipients -> insufficient, must wait

t = 2s:
  add 10 tokens -> available 30
  send 25 recipients -> remaining 5
~~~

If there is no traffic for 10 seconds, the bucket still accumulates at most **30 tokens**, not 100 tokens. **Capacity** bounds burst size.

### Conceptual formula

~~~text
elapsed = max(0, now - lastRefillTime)
tokens = min(capacity, tokens + elapsed * refillRate)

if tokens >= requestedCost:
    tokens = tokens - requestedCost
    ALLOW
else:
    WAIT_OR_REJECT
~~~

This is conceptual logic. Across multiple instances, reading and updating tokens must occur **atomically in a shared data store** or via a consistent rate-limiting service.

An **in-memory `RateLimiter` per pod** only limits that pod. With 6 pods each allowing 20 recipients/s, the system can emit up to 120 recipients/s even when the intended tenant quota is 20.

## 23. Distributed rate limiting with Redis

Redis is commonly used to store token bucket or sliding window state because of atomic scripts, TTLs, and low latency. One design:

~~~text
Worker A ----------+
Worker B ----------+--> Redis quota state
Worker C ----------+        |
                             +-- tenant:<tenant>:<stream>
                             +-- provider:<provider>:rate
                             +-- global:rate
                                      |
                                      v
                             ALLOW / WAIT
~~~

Requirements:

1. **Keys are namespaced** by tenant, stream, provider, and relevant policy version.
2. **Refill + consume must be atomic**, preventing two workers from spending the last token simultaneously.
3. Use a consistent clock, such as time managed by the rate-limit service; do not let clock skew between instances cause conflicting refills.
4. Set sensible TTLs so state for inactive tenants is not retained forever.
5. Handle Redis restarts/failovers according to the required quota guarantee level.
6. When Redis is unreachable, enforce **fail-closed** or an approved degraded mode; never default to unlimited sending for all tenants.

### Redis is fast, but does not equal an absolute hard quota

If the system requires **billing or legal limits** that must never be exceeded under any condition, evaluate the durability and state-loss characteristics of a Redis cluster using async replication/failover carefully. When strict accuracy is required, place **hard business quotas in a transactional database** and use Redis for **soft operational rate limiting**.

Never use Redis keys like:

~~~text
quota:customer@example.com
~~~

because this leaks personal data and enforces limits across the wrong boundary. Use opaque tenant IDs, streams, and normalized dimensions.

## 24. Limiting concurrency with a semaphore

**`JavaMailSender.send(...)`** in typical setups is a **blocking** call when speaking SMTP. Allowing too many workers to call it concurrently increases:

- Open sockets.
- Threads blocked waiting on network/TLS.
- CPU pressure from MIME/attachment encoding.
- Temporary memory for bodies and attachments.
- Provider connection counts triggering rate limits.

Inside a single JVM, a **Semaphore** can act as a local gate:

~~~java
import jakarta.mail.internet.MimeMessage;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import org.springframework.mail.javamail.JavaMailSender;

public final class InProcessSmtpGate {

    private final Semaphore slots;
    private final JavaMailSender sender;

    public InProcessSmtpGate(
            JavaMailSender sender,
            int maxConcurrentSends
    ) {
        if (maxConcurrentSends < 1) {
            throw new IllegalArgumentException(
                    "maxConcurrentSends must be positive"
            );
        }
        this.sender = sender;
        this.slots = new Semaphore(maxConcurrentSends, true);
    }

    public boolean submit(
            MimeMessage message
    ) throws InterruptedException {

        if (!slots.tryAcquire(200, TimeUnit.MILLISECONDS)) {
            return false;  // caller reschedules
        }

        try {
            sender.send(message);
            return true;
        } finally {
            slots.release();
        }
    }
}
~~~

This illustrates **a gate within one JVM**, not a complete multi-tenant solution. If **`sender.send(...)`** throws `MailException`, `finally` still releases the permit. The caller must classify the error and update the outbox/attempt externally rather than treating every exception as "not sent".

### Semaphores and scaling

If each pod allows 5 concurrent sends and there are 10 pods, total in-flight sends can reach **50**. When the provider only allows 20 connections, you need:

- A safely designed **distributed lease/semaphore**; or
- Fixed slot allocation per pod based on max replicas; or
- An SMTP dispatch service tier with controlled aggregate concurrency.

With distributed leases, you need TTLs, heartbeats, and **fencing/ownership tokens** so a stale worker cannot keep writing state after losing ownership. Lease expiration does not guarantee the old SMTP call has actually stopped; a connection limit cannot be treated as absolute if a worker hangs past lease expiry.

## 25. Hierarchy of in-flight limits

An email should proceed to SMTP only when capacity remains at all relevant levels:

~~~text
Global limit: 40 sends in-flight
   |
   +-- Provider P: 20
   |      |
   |      +-- Tenant A: 4
   |      +-- Tenant B: 4
   |      +-- Tenant C: 2
   |
   +-- Provider Q: 20
          |
          +-- Tenant D: 8
          +-- Tenant E: 2
~~~

For example, if Tenant A still has 2 slots available but Provider P is out of slots, Tenant A must wait. Conversely, if Provider P has 10 slots free but Tenant A already reached 4, Tenant A must also wait.

### Avoiding deadlocks when holding multiple slots

If Worker A acquires a global slot and waits for a provider slot while Worker B acquires a provider slot and waits for a global slot, the system can deadlock.

Solutions:

- Establish a **consistent acquisition order**.
- Use `tryAcquire` with timeouts and release already-acquired slots if the next level lacks capacity.
- Never hold quota reservations or DB transactions open during long network waits.
- For distributed limits, use a reservation service/protocol with explicit timeouts and rollback.

Never let one tenant hold a global slot for minutes just waiting for its provider rate tokens. **Rate waiting** should occur before acquiring expensive in-flight resources, or through a scheduler that reschedules execution time.

## 26. Fair scheduling: preventing one tenant from hogging the queue

A shared FIFO queue can cause **head-of-line blocking**:

~~~text
Queue:
  A A A A A A A A A A A A A A A B C

Worker pulls FIFO:
  processes many A jobs before reaching B/C
~~~

Tenant B has only a single OTP email yet sits behind thousands of marketing emails from Tenant A.

One improvement is maintaining **logical queues per tenant/stream**, or indexing eligible jobs per tenant and applying a fair scheduler:

~~~text
Tenant A:  A1 A2 A3 A4 ...
Tenant B:  B1
Tenant C:  C1 C2
             |
             v
       Fair Scheduler
             |
       A1 -> B1 -> C1 -> A2 -> C2 ...
~~~

In practice, combine:

- Each tenant's rate/quota.
- Stream priority.
- Number of waiting jobs.
- Deadline/TTL.
- Available provider/global slots.
- Retry state and `next_attempt_at`.

**Fairness does not mean every tenant always gets identical speed.** A tenant paying for higher capacity can receive higher weight, while still preventing starvation of smaller tenants.

## 27. Round-robin and weighted fair queueing

### Simple round-robin

~~~text
Tenants A, B, C all have jobs

Turn 1: A
Turn 2: B
Turn 3: C
Turn 4: A
...
~~~

The advantage is simplicity. The drawback: a 1-recipient message and a 500-recipient message do not consume the same resources.

### Weighted fair scheduling

Suppose:

~~~text
Tenant A: weight 4
Tenant B: weight 2
Tenant C: weight 1
~~~

The scheduler can give A proportionally more service opportunities than B/C when all have backlogs, without exceeding tenant/provider quotas.

In systems with widely varying email sizes or recipient counts, define **job cost** using recipient count, bytes, or a composite cost estimate so the scheduler does not treat every job as equal.

Algorithms you can use:

- **Weighted Round Robin** for jobs with roughly uniform cost.
- **Deficit Round Robin** when jobs vary in size.
- **Weighted Fair Queueing** when allocating by both weights and wait time.

You do not need a complex algorithm from day one. Start with **per-tenant queues + round-robin + per-tenant concurrency limits**, then measure queue wait times before upgrading.

## 28. Preserving priority for critical notifications

A tenant may send:

~~~text
security:      OTP, login alert
transactional: receipt, order update
marketing:     campaign, newsletter
~~~

With a single queue, marketing can overwhelm OTPs. Define **priority classes**:

| Stream | Characteristics | Strategy |
|---|---|---|
| **security** | Short TTL, delay ruins value | Reserved capacity, deadline-aware scheduling |
| **transactional** | Business-driven, stability required | Steady quota, controlled retries |
| **marketing** | Often large batches, easily deferred | Separate rate cap, fair scheduling, pausable |

Strict unbounded priority for security can also starve marketing if the security stream is abused. Enforce **within-class fairness** and abuse protection on priority streams.

### TTL and deadlines

If an OTP expires at 10:05, a job dispatched at 10:10 has no value:

~~~text
now > expiresAt  ->  EXPIRED_NOT_SENT
~~~

Check deadlines before consuming quota/rate tokens and before sending. Do not share the same retry schedule between OTPs and invoice emails if business semantics differ.

## 29. Backpressure when tenants create jobs faster than sending capacity

An unbounded queue only shifts the bottleneck from SMTP to database/queue storage.

Example:

~~~text
Tenant A creates: 5,000 jobs/minute
System processes: 1,000 jobs/minute

Backlog grows: ~4,000 jobs/minute
After 60 minutes: ~240,000 pending jobs
~~~

Countermeasures:

- Cap **outstanding jobs/tenant** and total queue size.
- Return meaningful **throttled/deferred/rejected** statuses.
- Return HTTP **`Retry-After`** when appropriate for the API and policy; do not confuse this with the SMTP protocol.
- Bound batch ingestion and payload sizes.
- Apply deadlines/TTLs, dropping notifications that expired per business rules.
- Apply backpressure to producers or delay campaign scheduling.
- Monitor **oldest due age** rather than queue depth alone.

In multi-tenant systems, ensure **Tenant A cannot fill the entire queue storage** and block Tenant B from creating urgent notifications.

### API response when quota is exceeded

If an HTTP endpoint rejects directly due to rate/quota, HTTP 429 can fit rate-limiting policies, whereas hard-plan quota or validation errors may use different business error codes.

Example body:

~~~json
{
  "code": "MAIL_TENANT_RATE_EXCEEDED",
  "status": "DEFERRED_RATE",
  "retryAfterSeconds": 30
}
~~~

This is an application-defined API contract, not a built-in Spring Mail HTTP response. Once a notification has been accepted into the outbox, do not return 429 as if it were rejected; return a status/response clearly reflecting acceptance.

## 30. Global quota, provider quota, and the lowest binding limit

With multiple tenants, a single send may draw from several limits simultaneously:

~~~text
Tenant A quota: 1,000 recipients/hour remaining
Tenant A security stream: 100 recipients/hour remaining
Provider P quota: 50 recipients/hour remaining
Global limit: 500 recipients/hour remaining

Request = 80 recipients
~~~

The request exceeds **Provider P**'s remaining capacity even though Tenant A, the stream, and the global limit have enough headroom.

The system can:

1. Defer until Provider P regains capacity.
2. Split the batch into smaller chunks if the contract allows independent recipient/data handling.
3. Route to another approved provider with matching sender identity and domain verification.
4. Reject with a provider-quota reason if the SLA cannot be met.

**Never automatically fail over to another SMTP account solely because the primary account ran out of quota.** Any fallback account must be authorized to send for that tenant, use a verified domain, and maintain appropriate bounce handling and reputation.

## 31. Retry budgets must be isolated per tenant

One tenant can suffer continuous email failures because:

- That tenant's SMTP provider is unavailable.
- Credentials were revoked or expired.
- A domain is not verified.
- The SMTP server returns transient 421/451 errors.
- A regional network path is degraded.

If workers retry without limits:

~~~text
Tenant A: 2,000 failing notifications
          each retried 20 times

=> 40,000 attempts pressuring workers/SMTP
=> Tenants B/C suffer even though their emails are valid
~~~

Retry policies should set bounds at multiple levels:

| Level | Example | Effect |
|---|---|---|
| **Per-notification attempts** | Max 5 attempts | Stops a single job from retrying forever |
| **Per-tenant retry rate** | Max 10 attempts/s | Stops a failing tenant from monopolizing SMTP |
| **Provider retry rate** | Cap total attempts to one ESP | Prevents retry storms during ESP incidents |
| **Max notification age** | Do not send after 24 hours or specific TTL | Avoids stale emails |
| **Consecutive-failure threshold** | Pause account with repeated AUTH errors | Prevents misconfigurations from creating load |
| **Global retry budget** | Reserve capacity for healthy new jobs | Protects the overall service |

A retried notification still consumes **transport resources** even when business quota was charged only once. Schedulers should fairly balance both **new jobs** and **retry jobs**.

### Exponential backoff and jitter

~~~text
baseDelay = min(maxDelay, initialDelay * 2^(attemptNumber - 1))
actualDelay = baseDelay + jitter
~~~

For example, initial 30 seconds, multiplier 2, max 30 minutes, plus random jitter. Exact values must match each stream's characteristics and ESP policies.

**Do not place unbounded `@Retryable` around an entire business operation** if the method handles payment, inserts into the outbox, and sends email. Retries should only wrap steps designed to be safely repeatable.

## 32. UNKNOWN after SMTP DATA and quota reservation

Suppose Tenant A sends an email:

~~~text
Attempt N100
    |
    +-- SMTP connection OK
    +-- MAIL FROM / RCPT TO OK
    +-- DATA transmitted
    +-- Final reply lost due to socket timeout
    |
    v
Result = UNKNOWN
~~~

The server may already have accepted the email. If the worker retries immediately, the recipient may receive duplicates.

At this point:

1. Preserve **UNKNOWN** state with the associated attempt ID, phase, and provider.
2. Do not blindly refund the **business quota reservation**.
3. Query provider traces/message IDs if available.
4. Choose a policy — **reconcile, manual review, or retry accepting duplicate risk** — depending on email type.
5. Do not throw the notification into a tight hot-retry loop on every worker poll.
6. Once confirmed accepted or rejected, update quota and state per policy.

**Outbox rows and idempotency keys do not magically turn SMTP into exactly-once delivery.** They mainly govern intent creation and prevent application-side duplicates. Final-hop response loss still requires reconciliation.

## 33. Handling partial recipients when one MIME targets multiple addresses

A `MimeMessage` can carry multiple To/Cc/Bcc recipients. In SMTP, individual recipients may be accepted or rejected differently.

Example:

~~~text
Message M100:
  RCPT TO customer-A -> accepted
  RCPT TO customer-B -> rejected
  RCPT TO customer-C -> accepted
~~~

If you retry the entire `MimeMessage` just because recipient B failed, A and C can receive duplicates.

To simplify tenant quota and delivery tracking, you can choose:

- **One notification-recipient per email transaction** on critical flows.
- Build **valid batches** while tracking per-recipient mappings and partial outcomes.
- When Jakarta Mail throws **`SendFailedException`** or Spring throws **`MailSendException`**, inspect the recipient/message failure details actually provided by the implementation.
- Never assume the entire batch failed just because an exception occurred.

Providers vary in how they meter quota when some recipients are accepted. Reconcile billed recipient counts against the ESP's contract rather than assuming the request's address count is final.

### Why does one-recipient-per-email aid isolation?

It increases SMTP message count and overhead, yet makes it easier to:

- Count quota unambiguously per recipient.
- Personalize content without exposing other recipients' addresses.
- Manage bounces and suppression per recipient.
- Retry selectively without duplicating deliveries to already-accepted recipients.

Measure throughput trade-offs against provider capabilities and batching support. No single strategy fits every email category.

## 34. Per-tenant/provider circuit breakers

If an SMTP account keeps returning authentication errors, throwing thousands more jobs at it will not fix anything:

~~~text
Tenant A -> Account A -> AUTH rejected
Tenant B -> Account B -> Healthy

Desired:
  Pause/throttle Tenant A account
  Keep Tenant B processing
~~~

Combine **circuit breakers** with rate limiting:

| State | Behavior |
|---|---|
| **CLOSED** | Allows normal sends, tracks failure statistics |
| **OPEN** | Skips SMTP calls for the failing route, defers jobs |
| **HALF_OPEN** | Probes with a few requests to confirm recovery |

Circuit breakers need the right **key**:

- **Per tenant account** when failures stem from tenant-specific credentials or configuration.
- **Per provider endpoint** when all tenants sharing an ESP hit an outage.
- **Per stream** if one content category is policy-blocked.

Do not trip a global circuit breaker just because one tenant entered invalid credentials. Conversely, during a shared provider outage, avoid letting every tenant hot-retry independently under isolated per-tenant breakers.

### Classify failures before tripping a breaker

- Persistent auth/certificate errors: alert and fix configuration rather than probing at high frequency.
- SMTP 4xx/throttling: apply policy-driven backoff and optionally reduce throughput temporarily.
- DNS/TCP outages: check scope across instance, region, and provider.
- MIME/template bugs: fix data/code instead of opening a provider circuit breaker as if the ESP were down.

## 35. Provider failover must preserve tenant identity

A router may have two ESPs:

~~~text
Tenant A
  |
  +-- Primary ESP P
  |
  +-- Secondary ESP Q
~~~

Before shifting a tenant to Q, confirm:

1. Q is authorized to send on behalf of Tenant A.
2. The From domain is verified on Q.
3. DKIM signing domains and SPF/DMARC alignment match.
4. Q's bounce addresses/webhooks map accurately back to the right tenant and notification.
5. Q has available quota and capacity.
6. Q operates in a region/jurisdiction permitted for that tenant's data.
7. Events and provider message IDs from P and Q never collide.
8. Failures from P are **confirmed unaccepted** or reconciled before replaying via Q.

**Failover does not grant exactly-once semantics.** If P already accepted DATA and the response was lost, resending via Q creates a duplicate that is even harder to reconcile across two providers.

### Never use failover to evade provider enforcement

If a provider restricts an account for spam complaints, reputation damage, or policy violations, shifting all traffic to another provider to bypass the block can worsen the issue and breach contracts. Failover must respect compliance rules, consent, and incident root causes.

## 36. Multi-tenant worker orchestrator

An ideal worker calls SMTP only after passing all condition gates:

~~~text
Acquire eligible job
    |
    v
Validate tenant status, stream and deadline
    |
    v
Resolve authorized sender profile
    |
    v
Verify business quota reservation
    |
    v
Check tenant/provider circuit breakers
    |
    v
Reserve short-term rate tokens
    |
    v
Acquire tenant/provider/global in-flight slots
    |
    v
Create MimeMessage from tenant-owned template
    |
    v
JavaMailSender.send(...)
    |
    +-- ACCEPTED --> SUBMITTED
    +-- TRANSIENT --> RETRY_WAIT
    +-- PERMANENT --> FAILED
    +-- AMBIGUOUS --> UNKNOWN
    |
    v
Release slots and persist result
~~~

### Example coordination skeleton

~~~java
public final class MultiTenantMailWorker {

    private final SenderProfileResolver profileResolver;
    private final MailCapacityGate capacityGate;
    private final NotificationMessageFactory messageFactory;
    private final MailAttemptService attemptService;

    public MultiTenantMailWorker(
            SenderProfileResolver profileResolver,
            MailCapacityGate capacityGate,
            NotificationMessageFactory messageFactory,
            MailAttemptService attemptService
    ) {
        this.profileResolver = profileResolver;
        this.capacityGate = capacityGate;
        this.messageFactory = messageFactory;
        this.attemptService = attemptService;
    }

    public void process(ClaimedNotification notification) {
        SenderRoute route = profileResolver.resolve(
                notification.tenantId(),
                notification.stream()
        );

        // Admission must rely on quota reserved when the
        // notification was recorded, never deducting twice on retries.
        if (!capacityGate.tryReserve(notification, route)) {
            attemptService.deferForCapacity(notification);
            return;
        }

        try {
            // Selected sender creates MimeMessage and builds
            // content matching the authorized tenant/profile.
            attemptService.submit(
                    notification,
                    route,
                    messageFactory
            );
        } finally {
            capacityGate.release(notification, route);
        }
    }
}
~~~

**SenderProfileResolver**, **SenderRoute**, **MailCapacityGate**, **NotificationMessageFactory**, and **MailAttemptService** are application abstractions, not built-in Spring classes. This example illustrates responsibility boundaries, **not a complete production-ready implementation**.

A real implementation requires:

- **Claim tokens/leases** so one worker cannot overwrite another worker's outcome.
- Recording attempts before/after SMTP in appropriate transactions.
- Never holding database transactions open while waiting on SMTP.
- Classifying exceptions and partial outcomes.
- Releasing capacity by ownership token even when exceptions occur.
- Handling errors even if writing the outcome back to the DB fails.
- Timeouts and a watchdog for stuck `PROCESSING` jobs.

### Pay attention to rendering vs. reservation order

If CPU-heavy MIME construction or attachment loading runs before capacity checks, thousands of jobs may render simultaneously and overload workers. Conversely, holding SMTP slots while rendering large files wastes provider slots.

One option splits it into:

~~~text
Validate/prepare cheap metadata
       |
       v
Admission + limited render pool
       |
       v
Render/prepare MIME
       |
       v
Short-lived SMTP capacity reservation
       |
       v
Submit
~~~

The exact boundary requires real-world measurement and depends on attachment strategy. You can apply **two separate semaphores/pools**: one for rendering/storage I/O and one for SMTP submission.

## 37. Spring @Async is not quota isolation

Spring lets you run tasks asynchronously with **`@Async`** and an executor:

~~~java
@Async("mailTaskExecutor")
public void sendLater(NotificationJob job) {
    // ...
}
~~~

However, simply adding `@Async` does not guarantee:

- Per-tenant rate limits.
- Fairness across tenants.
- Persistent quotas across restarts.
- Exactly-once semantics or idempotency.
- Staying within provider account quotas.
- Ensuring jobs are not lost on process crash.

If the executor queue is unbounded, a high-volume tenant can inflate memory filled with jobs. If the executor uses a bounded queue, you need a **rejection/backpressure policy** and clear response statuses.

For business-critical email, a **durable outbox/queue** is typically the primary coordinator. `@Async` can be an execution detail, not the source of delivery guarantees.

## 38. Never hold a database transaction while sending SMTP

A seemingly convenient snippet:

~~~java
@Transactional
public void createInvoiceAndSendMail(Invoice invoice) {
    invoiceRepository.save(invoice);
    mailSender.send(...);
}
~~~

can create two problems:

**Holding database resources too long.** SMTP sending includes DNS, TCP, TLS, AUTH, and DATA; any step can lag or time out. Throughout that time, the transaction remains open, extending lock durations and pressuring the connection pool.

**No cross-system rollback.** The SMTP server may already accept the email while the database transaction rolls back afterward. An email cannot be un-sent automatically.

Outbox pattern:

~~~text
BEGIN DB TRANSACTION
  save invoice
  reserve notification quota
  insert tenant-scoped outbox intent
COMMIT
        |
        v
Worker later:
  claim notification
  resolve tenant sender/limits
  send SMTP outside business transaction
  persist result in short DB transaction
~~~

Note: if the initial database transaction manages the invoice while quota lives in an external service, you need a reservation protocol and reconciliation; there is no automatic ACID guarantee across two systems.

If SMTP accepts the message yet updating the `SUBMITTED` status fails, recover/reconcile the outcome instead of automatically re-sending simply because the database returned an error.

## 39. Isolating memory, attachments, and bandwidth

Message-count quotas are insufficient if a tenant can send emails with huge attachments:

~~~text
Tenant A: 100 messages, each 25 MB
Tenant B: 100 messages, each 10 KB
~~~

Same message count, vastly different CPU, disk, network, and memory costs.

Control points:

- **Max attachment size** and **max total message MIME size**.
- Maximum attachments per message.
- Total in-flight bytes across workers.
- Open file descriptors / `InputStream` handles.
- Attachment sources access-controlled per tenant.
- Concurrent download limits from object storage.
- Maximum template rendering / stream reading duration.
- Queue batch sizes to avoid loading all binary payloads into RAM at once.

### InputStreamSource and repeatable streams

**`MimeMessageHelper.addAttachment(...)`** may need to read content while preparing/serializing the message. For data in memory or on disk, you can use **`ByteArrayResource`**, **`FileSystemResource`**, or **`ClassPathResource`** as appropriate.

If you use an **`InputStreamResource`** wrapping a single-use stream, MIME serialization can fail when it needs to reopen the stream. An attachment source should supply a **fresh `InputStream` per read** whenever the contract requires it.

For data fetched from object storage, verify tenant ownership and object version/snapshot. Never allow Tenant A to specify arbitrary object paths belonging to Tenant B.

### Should all attachment bytes be stored inside the outbox?

Usually not for large files. Store a reference instead:

~~~text
attachment_reference:
  tenantId: tenant-A
  objectKey: opaque-storage-key
  objectVersion: immutable-version
  declaredContentType: application/pdf
  sizeBytes: ...
~~~

The worker reads the file at send time with appropriate permissions. Handle cases where the object was deleted, its version changed, or access permissions became invalid.

## 40. Security and preventing tenant abuse

Quota isolation is part of abuse prevention, not the whole solution.

A tenant may attempt to:

- Send emails to a massive recipient list.
- Mix another tenant's recipients into the payload.
- Choose a From domain or SMTP account it does not own.
- Generate duplicate notifications to bypass business quotas.
- Fire parallel request bursts to bypass limits if allocation is not atomic.
- Use oversized attachments or remote URLs to exhaust resources.
- Set `priority=security` to bypass marketing limits.
- Intentionally trigger `UNKNOWN` events to force replay across fallback providers.

Guardrails:

1. **Tenant authorization** independent of quotas.
2. **Sender/domain ownership verification**.
3. **Idempotency** per business event and notification purpose.
4. **Atomic quota reservation** before accepting a job.
5. **Per-tenant/stream rate and concurrency limits**.
6. **Payload/attachment size limits** and object ownership checks.
7. **Controlled priority mapping**; callers cannot self-upgrade streams.
8. **Authenticated bounce/webhook events** before changing state/suppression.
9. **Audit trail** for quota policy, sender profile, and secret rotation changes.
10. **Circuit breakers** to stop retry storms from failing accounts.

Never treat a client-supplied **`tenantId`** or an arbitrary JWT claim as proof of authority to use an SMTP sender; verify authorization against the application's security model.

### Multi-tenant SMTP is a sensitive data boundary

`From`, `To`, `Cc`/`Bcc`, `Subject`, attachment filenames, bounce addresses, and delivery events can contain personal data. Link all of them to the right tenant and protect them in logs, exports, and dashboards.

## 41. Metrics and dashboards for multi-tenant systems

Measure these categories:

| Category | Logical metric | Interpretation |
|---|---|---|
| Submission | **mail_attempts_total** | Attempts accepted/failed/unknown |
| Per-tenant quota | **tenant_mail_quota_remaining** | Remaining business quota capacity |
| Rate limit | **mail_rate_limit_denied_total** | Times rate tokens could not be acquired |
| Concurrency | **mail_inflight_sends** | Active concurrent SMTP attempts |
| Fairness | **mail_queue_wait_seconds** | Time an eligible job waits for its turn |
| Outbox | **mail_pending_jobs** | Number of pending notifications |
| Outbox age | **mail_oldest_due_age_seconds** | Age of the oldest due job |
| Retry | **mail_retry_attempts_total** | Attempts caused by retries |
| Delivery | **mail_bounced_notifications_total** | Unique bounced notification-recipients |
| Resource | **mail_attachment_bytes_total** | Processed bytes under the chosen definition |
| Provider | **mail_provider_throttled_total** | Throttle/rate-limit errors from the ESP |
| Security | **mail_sender_policy_rejected_total** | Requests violating sender/domain permissions |

Segment by bounded dimensions: **provider, stream, result, region, and error category**.

### Tenant ID in Prometheus labels: weigh carefully

With 50 tenants, putting `tenantId` on a few metrics may be manageable. With 500,000 tenants, every `tenantId`/provider/stream/result combination can explode into millions of time series.

Alternatives:

- Aggregate dashboards by provider/stream/region.
- Per-tier or per-plan metrics instead of per-tenant.
- Analytics or quota database queries for tenant-specific inspection.
- Traces/logs with `tenantId` or opaque correlation IDs under proper access control and retention.
- Export per-tenant metrics only for a controlled allowlist of tenants when operational needs genuinely justify it.

**Never put recipient emails, subjects, notification IDs, or tokens into metric labels.** When placing `tenantId` in logs, enforce tenant-level authorization controls.

## 42. Distinguishing quota metrics from accounting truth

For example, a Redis token bucket shows remaining tokens while the database may hold unsent reservations. If the application crashes:

~~~text
Quota reservation committed
    |
    X process crash before SMTP send
    |
Metric counter not flushed
    |
Outbox still PENDING
~~~

This can make metrics diverge from accounting numbers.

Define the source of truth:

| Data type | Typical authoritative source |
|---|---|
| Reserved/committed hard business quota | Transactional quota ledger/database |
| Observed worker attempts | Micrometer metrics/logs |
| Current rate tokens | Redis/rate-limit service |
| Notification intent | Outbox database |
| Provider acceptance | SMTP result + provider logs/IDs |
| Delivery/bounce | Verified provider events/DSNs |

Use metrics for **monitoring and alerting**; for billing, invoicing, or hard policy enforcement, rely on durable, reconcilable ledgers/records.

### Accuracy and time windows

In a distributed system, application clocks, database clocks, Redis time, and provider timestamps can diverge. Define clearly:

- When does a quota window start and end?
- Is UTC or tenant timezone used?
- Is a notification billed by **`created_at`**, **`accepted_at`**, or **`submitted_at`**?
- Does a retry across a day boundary consume additional business quota?
- Do late provider events adjust an older ledger or only append delivery state?

For commercial quotas, the contract shown to tenants must match the real algorithm. Never let a UI show "0/1000 used" just because an in-memory metric counter reset after a restart.

## 43. Quota and fairness test scenarios

Essential unit and integration tests:

| Scenario | What to prove |
|---|---|
| Tenant A exhausted quota | A is rejected/deferred per policy; B keeps operating |
| Two concurrent requests near quota limit | Exactly up to the limit succeed; no double allocation |
| Quota write succeeds, outbox insert fails | Transaction rolls back quota |
| Same event submitted twice | Does not create two notifications or charge quota twice |
| Worker retries one notification | Business quota is not deducted repeatedly if billed once |
| Rate limiter across multiple pods | Tenant aggregate rate stays within design limits |
| Global limit exhausted | Workers do not bypass global limiter |
| Tenant A large backlog, B one OTP | B does not wait behind A's entire queue |
| Tenant A invalid credentials | Only A errors/trips breaker; B uses the right sender |
| Sender profile updated mid-flight | In-flight message does not use the wrong tenant/new credentials |
| Timeout after DATA | Status `UNKNOWN`; no blind refund or blind retry |
| SMTP batch partial success | Outcomes and quotas recorded per recipient |
| Attachment owned by another tenant | Send blocked before SMTP |
| Email exceeds max size | Not sent to SMTP; error properly categorized |
| Job past `expiresAt` | Transitioned to `EXPIRED` per policy, not sent |
| Provider P out of quota, Q has quota | Failover only if tenant/domain/permissions allow |
| Duplicate bounce webhook | Only one valid delivery transition recorded |

### Testing race conditions at the quota boundary

Suppose only **10 units** remain and **20 threads** each request 1 unit. The only correct result is **at most 10 successful reservations**, regardless of thread interleaving.

Do not mock with an in-memory `HashMap` and conclude SQL reservation is safe. Run concurrency quota tests against a **database and transaction isolation level matching production**, or test containers running the same database engine.

A test can:

1. Initialize a tenant quota window with 10 units remaining.
2. Use a barrier so 20 requests arrive near-simultaneously.
3. Have each request invoke the real reservation service.
4. Count allowed responses.
5. Verify `used_units` in the database never exceeds the limit.

### Fairness tests must measure wait time

If you enqueue 1,000 A jobs and 1 B job, verify B is picked within a bounded number of turns or time under the scheduler algorithm. Never assert merely "eventually B runs", because B might wait for hours.

## 44. Testing multi-tenancy with a mock SMTP server

To test Spring Mail integration, use **GreenMail**, **Mailpit**, **MailHog**, or an appropriate SMTP capture server.

Test scenario:

~~~text
Tenant A -> profile A -> SMTP test mailbox A
Tenant B -> profile B -> SMTP test mailbox B

Inject:
  A From: tenant-a@example.com
  B From: tenant-b@example.com
  A recipient: customer-a@localhost
  B recipient: customer-b@localhost

Assert:
  A message contains no From/To/Bcc from B
  B message contains no From/To/Bcc from A
  A quota usage updates only A
  B quota usage updates only B
  provider routing and bounce mapping are not swapped
~~~

If two tenants share the same SMTP test server, verify **sender profiles/credentials** using a test double or a server supporting authentication and per-session logging. Seeing messages arrive in one shared SMTP inbox alone does not prove `JavaMailSender` used the right credentials for each tenant.

### Not every test needs real SMTP

- Unit tests for policy/quota arithmetic.
- Database integration tests for atomic reservations and idempotency.
- Concurrency tests for race conditions.
- Scheduler tests for fairness and TTL.
- SMTP integration tests for sender selection and MIME/envelope handling.
- Provider sandbox tests for custom `MAIL FROM`/quota webhooks where permitted.

Never run your whole test suite through production SMTP or real external addresses on the Internet. That is both flaky and risks emailing real people by mistake.

## 45. Runbook when one tenant consumes too much capacity

When dashboards alert on rising queue delay or provider throttling:

**Step 1 — Identify the bottleneck layer**

- Is the tenant daily quota exhausted?
- Are stream rate tokens depleted?
- Is the provider throttling or hitting connection caps?
- Are global JVM threads/memory saturated?
- Is database outbox claiming/polling slow?
- Is object storage or attachment rendering slow?

**Step 2 — Determine the blast radius**

- One tenant or the entire provider?
- Only the marketing stream or also transactional/security?
- One region/pod or all instances?
- Was there a recent deployment or quota policy change?

**Step 3 — Check impact on other tenants**

- Is queue wait rising for Tenants B/C?
- Are OTP/security emails breaching TTL?
- Are small tenants starving?
- Is the cross-pod shared rate limiter working properly?

**Step 4 — Choose mitigations**

- If one tenant is bursting: lower its rate/queue cap per policy without shutting down the whole service.
- If provider quota is exhausted: throttle aggregate throughput rather than cutting per-tenant limits alone.
- If one account has auth/TLS errors: pause that account and fix configuration.
- If large attachments saturate workers: reduce concurrent rendering and enforce size limits.
- If FIFO causes starvation: enable fair scheduling and reserved capacity.
- If outbox backlog surges: apply producer backpressure.

**Step 5 — Post-incident reconciliation**

- Are any notifications stuck in `UNKNOWN`?
- Have any jobs expired and need `EXPIRED` status?
- Are any quota reservations dangling?
- Does provider acceptance differ from database outcomes?
- Did any recipients get duplicates from retries or failover?

**Step 6 — Verify recovery**

Monitor accepted rate, error categories, retry backlog, oldest due age, concurrency usage, and latency across each critical stream.

## 46. Common misconceptions and anti-patterns

| Mistake | Why it is dangerous | Right approach |
|---|---|---|
| Using one shared send quota | High-volume tenant starves everyone else | Per-tenant quotas plus provider/global limits |
| Running a local rate limiter per pod | Total rate scales up with replica count | Distributed limiter or controlled per-pod allocation |
| Using `Semaphore` to limit recipients/s | Semaphores limit concurrency, not rate over time | Combine rate limiter and concurrency gate |
| Rate limiter only, no in-flight cap | Slow sends hold too many sockets/threads | Add a concurrency cap |
| Deducting quota on every retry | Provider glitches drain tenant business budget | Separate business quota from transport attempt budget |
| Not counting retries against transport budget | Retry storms saturate SMTP capacity | Rate/circuit breakers for retries |
| Unconditional `SELECT` then `UPDATE` for quota | Race condition over-allocates beyond limit | Atomic conditional update/transaction |
| Using unverified request `tenantId` | Accesses another tenant's sender/quota | Tenant identity from auth + authorization |
| Mutating username on a singleton sender | Cross-tenant races and credential leaks | Immutable sender profiles and safe routing |
| Relying on `ThreadLocal` tenant context in workers | Thread pools drop or leak stale context | Explicit `tenantId` stored in outbox |
| Treating 1-recipient and 100-recipient emails identically | Breaches recipient quotas/provider rules | Contract-aligned quota accounting unit |
| Metering email count while ignoring attachments | Exhausts memory, I/O, and bandwidth | Cap bytes, sizes, and render concurrency |
| Shared FIFO without fairness | Small tenants starve | Per-tenant queues/fair scheduling |
| Unbounded strict priority for security | Abusable; starves other streams | Reserved capacity + anti-abuse controls |
| No limit on `PENDING` jobs | Unbounded queue growth | Backpressure and backlog quotas |
| Treating SMTP accepted as delivered to Inbox | Wrong delivery semantics | Separate submission from delivery feedback |
| Treating timeout after DATA as unsent | Produces duplicate emails | `UNKNOWN`/reconcile |
| Failing over to any arbitrary provider | Mismatched domains/credentials/permissions | Approved tenant-provider routing |
| Retrying whole batch after partial failure | Accepted recipients get duplicates | Per-recipient outcomes and targeted retry |
| Putting `tenantId`/recipients in all metric labels | High cardinality and privacy risk | Aggregate metrics + tenant-scoped logs/ledger |
| Treating Micrometer counters as quota ledger | Counters reset and aren't atomic with DB | Durable quota ledger |
| Holding DB transaction open during SMTP send | Long locks and un-rollbackable emails | Outbox + short transactions |
| Testing only on a single instance | Misses races and global oversubscription | Concurrency/distributed integration tests |

## 47. Step-by-step rollout roadmap

Not every system needs a complex distributed quota platform on day one. Roll out by maturity stage:

### Stage 1 — Right tenant, never cross-send

1. Obtain a trusted `tenantId` and enforce authorization at the request/event boundary.
2. Add `tenantId` to every notification, template, sender profile, and delivery event.
3. Use controlled **`From`/`Reply-To`** headers and verified domains.
4. Never mutate a singleton sender while sending.
5. Use distinct per-tenant test fixtures to catch leaks.

In this stage, priority one is **correct data and correct sender** before optimizing throughput.

### Stage 2 — Hard quotas and durable processing

1. Pick the quota unit: recipient, notification, bytes, or a combination.
2. Design policy, reservation, and outbox tables.
3. Use **atomic conditional reservations** inside transactions.
4. Add idempotency keys for event replay.
5. Distinguish rejected, queued, submitted, and unknown.
6. Bound retries and guard against duplicates.

### Stage 3 — Performance isolation

1. Rate-limit per tenant/stream and per provider.
2. Cap concurrency per tenant, provider, and globally.
3. Add fair scheduling or per-tenant queues to prevent starvation.
4. Apply backpressure when queues grow rapidly.
5. Cap attachment bytes and rendering I/O.
6. Reserve capacity for critical streams.

### Stage 4 — Multi-provider and operations

1. Version sender/credential profiles and bound caches.
2. Route providers according to tenant policies and permissions.
3. Scope circuit breakers to match failure domains.
4. Correlate bounces and delivery feedback by tenant.
5. Build dashboards by provider, stream, errors, quotas, and queue wait.
6. Write runbooks for recovering reservations, `UNKNOWN`, and partial successes.

### Stage 5 — Scale and cost optimization

- Analyze provider costs by recipient and bytes.
- Apply weighted fairness if tenants belong to different service tiers.
- Tune batch sizes and connection reuse within provider limits.
- Verify distributed rate limits under pod autoscaling.
- Separate MIME rendering and SMTP I/O compute pools if one starves the other.
- Compare p95/p99 latency, throughput, and resource usage per stream.

Each stage should have **tests and metrics proving impact** before raising concurrency. Raising threads or pods while provider quotas stay fixed often just increases throttling errors.

## 48. Production design checklist

Before running a high-volume multi-tenant Spring Mail system, verify you can answer:

**Identity and authorization**

- Does `tenantId` come from a trusted source?
- Do workers propagate `tenantId` across outbox, queues, and retries?
- Are sender profiles, domains, templates, and attachments checked for ownership?
- Can one tenant override another tenant's `From`, `Reply-To`, or `MAIL FROM`?

**Quotas**

- Is quota metered by message, recipient, attempt, or bytes?
- Are limits enforced per tenant, stream, provider, and globally?
- Are reservations atomic across threads and pods?
- Are admission and outbox persisted durably without losing or over-charging on crashes?
- Are quota refunds and `UNKNOWN` handling clearly defined?
- Are time windows and timezones consistent?

**Performance**

- Are rate limiters and concurrency limiters separated?
- Under pod scale-out, does aggregate rate stay within policy?
- Does fair scheduling protect low-traffic tenants?
- Do critical streams have reserved capacity and TTLs?
- Do queues enforce backpressure and size caps?
- Do payloads, attachments, and downloads have resource limits?

**SMTP and reliability**

- Do sender profiles enforce TLS and hostname verification?
- Are singleton credentials never mutated?
- Are finite connection/read/write timeouts configured?
- Do retries classify errors and cap max attempts?
- Are post-DATA errors marked `UNKNOWN` for reconciliation?
- How is partial recipient success handled?
- Does provider failover respect domains, permissions, regions, and duplicate risk?

**Observability and testing**

- Are attempts, rate denials, in-flight counts, backlog age, and bounces metered?
- Can every attempt for a notification be traced by tenant and trace ID?
- Do metric labels avoid high cardinality and PII?
- Were quota boundaries tested with concurrent requests against a real database?
- Was it verified that Tenant A cannot delay Tenant B past SLA?
- Were secret rotation, bad credentials, and provider outages tested?
- Were duplicate webhooks, queue crash recovery, and `UNKNOWN` tested?

A system does not need every advanced feature immediately, yet it must clearly document **which limits are hard guarantees versus best effort** and which tenants can be affected when a shared provider degrades.

## 49. Key takeaways

**Multi-tenant handling and quota isolation in Spring Framework Mail** protects each tenant's **identity, data, budget, and processing capacity**. No single **`spring.mail`** property or **`JavaMailSender.send(...)`** call solves this on its own.

Core principles:

1. **Tenant identity must be trustworthy** and travel with each notification across requests, outbox, workers, sender routing, and delivery feedback.
2. **Business quota, transport rate, and concurrency are three distinct limits.** A retried notification can consume multiple SMTP attempts yet only one business intent.
3. **Hard quotas must be allocated atomically** alongside idempotent outbox reservations. Distributed rate limits must account for multiple pods, failover, and consistent timekeeping.
4. **Fair scheduling, reserved capacity, and backpressure** prevent one large tenant from slowing down or exhausting resources for others.
5. **Never mutate `JavaMailSenderImpl` configuration across concurrent tenant requests.** Use authorized, version-immutable sender profiles and secure credential handling.
6. **Retries, partial successes, and `UNKNOWN` outcomes** must be handled per notification-recipient using SMTP evidence to avoid duplicates or wrong quota refunds.
7. **Provider quotas and reputation can remain shared resources** even when application logic is isolated. Use dedicated accounts/pools and domain verification when strict isolation is required.
8. **Measure and test** the right units: quota ledgers, attempts, unique notifications, queue wait, bytes, bounces, and cross-tenant impact.

**The ultimate goal is not merely stopping a tenant from exceeding its email allowance, but ensuring that when one tenant sends heavily or encounters errors, all other tenants continue receiving service according to their permissions, quotas, and SLAs.**





