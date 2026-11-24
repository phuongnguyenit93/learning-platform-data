# Sending Frequency and Recipient Signals in Spring Framework Mail

A Spring application can build valid MIME, authenticate with SMTP successfully, and receive an acceptance response from the relay, yet emails can still land in Spam/Junk, get delayed, or be ignored by recipients. **Deliverability** is not only the outcome of calling `JavaMailSender.send(...)`. It also depends on sender reputation, list quality, content, **sending frequency**, and **recipient feedback signals**.

Repeatedly emailing one mailbox, blasting a large campaign without pacing, or continuing to mail someone who unsubscribed creates a poor experience and can negatively impact delivery capability. Conversely, sending for clear needs, at an appropriate cadence, respecting preferences, and reacting promptly to bounces/complaints form the foundation of healthy operations.

In Spring Framework Mail, `JavaMailSender` is responsible for transferring messages over SMTP. The library does not decide how many newsletters a person should receive per week, does not automatically know they unsubscribed, and has no universal algorithm to predict Inbox placement. Those parts belong to **application policies, notification workflows, and provider events**.

This lesson explains how to control per-recipient frequency, pace sending volume over time, interpret positive/negative signals cautiously, and integrate them into Spring applications via services, outboxes, rate limiters, and webhooks.

## 1. Distinguishing Frequency, Rate, and Deliverability

Several concepts are often lumped together:

| Concept | Primary Question | Example |
| --- | --- | --- |
| **Send rate** | How many messages does the system send per second/minute? | 20 SMTP submissions/second |
| **Recipient frequency** | How often and how far apart is one recipient contacted? | At most N marketing emails in a window |
| **Pacing** | How is a campaign distributed over time? | Split into small batches |
| **Deliverability** | Are messages accepted and delivered where they can be read? | Delivered, deferred, filtered |
| **Engagement** | Are there signals that recipients are interested? | Clicks, replies, in-product actions |
| **Negative signal** | Is there feedback showing mail is unwanted or undeliverable? | Bounces, complaints, unsubscribes |

An application can stay within the SMTP provider's rate limit yet still contact the same individual too frequently. Conversely, an application with a sensible frequency cap that blasts 50,000 emails in one minute can still exceed quotas or trigger deferrals.

**Send rate limits infrastructure; recipient frequency limits how often each person is bothered.** Both limits must be managed independently.

## 2. SMTP Submission Is Not Inbox Delivery

Basic flow:

~~~text
Business event / campaign
        |
        v
Consent + suppression + frequency policy
        |
        v
Outbox / queue
        |
        v
JavaMailSender / SMTP
        |
        v
SMTP relay accepts message
        |
        v
Downstream filtering / destination provider
        |
        +--> Delivered
        +--> Deferred
        +--> Bounced
        +--> Spam/quarantine
        |
        v
Recipient may engage
        |
        +--> Reply / click / unsubscribe / complaint
~~~

When `JavaMailSender.send(...)` returns normally, the transport usually completed submission per the library contract. You cannot infer that the email reached the Inbox or was read.

| Status | Meaning |
| --- | --- |
| `QUEUED` | Send request has been persisted or placed in a queue |
| `SUBMITTED` | Transport/SMTP relay accepted submission |
| `DELIVERED` | Delivery signal received from provider per its definition |
| `DEFERRED` | Downstream temporarily delayed delivery |
| `BOUNCED` | Undeliverable report received |
| `COMPLAINED` | Recipient spam-report signal received |
| `UNSUBSCRIBED` | Recipient requested stopping this mail type |
| `OPENED`/`CLICKED` | Tracking signal recorded; not necessarily human interaction |

Some SMTP relays do not provide delivery webhooks. Spring Mail does not generate `delivered`, `opened`, or `complained` events on its own; obtaining them requires integrating provider data sources or appropriate bounce/inbound systems.

## 3. Why Can Frequency Affect Deliverability?

Sending frequency relates to:

- **Recipient expectations:** subscribing to a weekly newsletter does not mean wanting promotions every hour.
- **Engagement:** too many emails cause users to ignore them or unsubscribe.
- **Complaints:** unwanted emails may be reported as spam.
- **Reputation:** receiving infrastructure can use sending history and negative signals to evaluate senders.
- **Quota:** burst volume can trigger throttling or temporary rejections.
- **Queue latency:** bursts of newsletters can delay OTPs or order confirmations if sharing a queue.

There is no single "best" frequency number across all industries, providers, and lists. A suitable schedule depends on email type, consent, content, engagement history, and operational limits.

The goal is not maximizing message count at any cost, but ensuring **every email has a clear purpose, matches real need, and stays within reasonable recipient expectations**.

## 4. Classify Emails Before Setting Frequency Caps

| Email Type | Example | Typical Policy Needed |
| --- | --- | --- |
| **Security** | OTP, login alert, password reset | Timely, anti-abuse, and dedicated rate limit |
| **Transactional** | Order confirmation, invoice | Tied to real events, deduplicated by event |
| **Operational** | Periodic reports, technical alerts | Digest batching, severity classification |
| **Lifecycle** | Onboarding, step completion reminders | Sensible spacing between steps |
| **Marketing** | Newsletters, offers | Consent, preferences, frequency cap, and unsubscribe |
| **Bulk campaign** | Mass sends to subscribed lists | Pacing, segmentation, and provider quotas |

Do not apply a rigid marketing cap to genuinely necessary security emails. Yet do not allow unlimited sending merely by labeling something "transactional." For instance, a duplicate `OrderConfirmed` event published 100 times must be deduplicated via idempotency.

OTPs need anti-abuse per user, IP, or action. Marketing emails must rely on proper consent and preferences rather than bypassing rules by changing category labels.

## 5. Recipient Caps Must Count Across Campaigns

Suppose within a single day:

~~~text
08:00   Product newsletter
11:00   Personalized offer
16:00   Survey completion reminder
~~~

Each campaign may see that the recipient has not received an email from **that campaign**. Yet in total, the recipient still received three marketing emails.

~~~text
Campaign A ----+
Campaign B ----+--> Global marketing cap
Campaign C ----+           |
                          v
                     ALLOW / DEFER / SUPPRESS
~~~

Limits can be scoped by:

- Recipient and category.
- Recipient and campaign.
- Recipient and workflow/journey.
- Global marketing frequency.
- Tenant/account.
- Recipient domain.
- Provider/sender account.

Avoid creating too many caps without precedence rules, as one notification might be allowed by one cap and denied by another. Define what happens when one cap has no slots while another still has room.

## 6. Calendar Windows, Rolling Windows, and Minimum Gaps

Frequency caps can be expressed in multiple ways:

| Mechanism | Calculation | Notes |
| --- | --- | --- |
| Calendar day | Within a day in a defined time zone | Can burst around midnight |
| Calendar week | Within a week per locale/policy | Must define week start day |
| Rolling 24 hours | Trailing 24 hours from current time | Avoids midnight boundary bursts |
| Rolling 7 days | Trailing 7 days | Requires history or suitable counters |
| Minimum gap | At least X hours since most recent email | Does not cap weekly total volume |
| Token bucket | Average rate and burst allowance | Better suited for transport than consent cadence |

An illustrative configuration:

~~~yaml
app:
  mail:
    frequency:
      marketing:
        max-per-day: 1
        max-per-week: 3
      onboarding:
        minimum-gap-hours: 24
~~~

This is **neither a Spring default nor a fixed recommendation for every system**. It is an example of an application-built policy.

When calculating "per local day," use a full IANA time zone such as `Asia/Ho_Chi_Minh` or `Europe/Paris`. Do not assume adding 24 hours always equals "tomorrow at the same time" when daylight saving time applies.

## 7. Count at Enqueue or at Successful Send?

Clarify that frequency caps measure **logical notifications**, not necessarily SMTP invocation counts.

Possible milestones:

1. When the notification is approved and a **slot is reserved**.
2. When the notification is enqueued into the outbox.
3. When SMTP submission succeeds.
4. When the provider reports delivered.

If counters increment only after SMTP success, two concurrent campaigns can both read "slot available" and enqueue jobs exceeding the cap. Therefore, in concurrent systems, **reserve atomically before enqueueing**.

One notification may retry SMTP several times yet remains one logical email; retries should not consume extra recipient-frequency slots.

If a job is canceled before sending, the reservation may be released per policy. For `AMBIGUOUS` SMTP outcomes, be conservative since the server may have accepted it even if the worker does not know.

## 8. Consent and Preferences Come Before Frequency

A frequency cap does not replace permission to send.

~~~text
Send request arrives
      |
      v
Is recipient allowed to be contacted for this category?
      |
   +--+--+
   |     |
  No    Yes
   |     |
   v     v
Suppress  Has hard-bounce/complaint suppression?
             |
          +--+--+
          |     |
         Yes    No
          |     |
          v     v
       Suppress  Frequency cap?
                  |
              +---+----+
              |        |
            Full    Slot available
              |        |
              v        v
          Defer/skip   Reserve + enqueue
~~~

Someone who unsubscribed from marketing must not keep receiving marketing simply because a cap slot is free. Conversely, leaving marketing does not automatically stop legitimate security/transactional emails. Define preference and suppression scopes clearly.

### Re-Check Before Submitting

An email may be scheduled hours in advance:

~~~text
09:00 Campaign enqueued
10:00 User unsubscribes
11:00 Worker prepares to send
          |
          v
   Check current preference
          |
          v
       Suppress marketing
~~~

Checking consent only once at enqueue allows sends after the recipient asked to stop. For marketing mail, re-check suppression close to submission time.

## 9. Pacing to Avoid Bursts

A campaign with a large list does not have to send everything at the exact moment a button is clicked.

Pacing distributes sending across multiple batches or time intervals:

~~~text
Campaign approved
       |
       v
Eligible recipient segment
       |
       v
Set rate/concurrency budget
       |
       +--> Batch A
       +--> Batch B
       +--> Batch C
       +--> ...
       |
       v
Observe results before increasing pace
~~~

Benefits:

- Reduces bursts against SMTP/providers.
- Spreads worker load.
- Gives an opportunity to spot rising bounces/complaints early.
- Prevents newsletters from delaying transactional emails.
- Adjusts to provider cooldowns.

Pacing controls **how volume is released**; recipient caps control **how much each person receives**. Neither replaces the other.

## 10. Warm-Up When a New Sender or Domain Increases Volume

A new domain, IP, or account may lack sending history with receiving systems. Sudden volume spikes are far more unstable than controlled ramps.

Warm-up should rely on:

- Consented lists with clean data.
- Content recipients expect.
- Volume scaled to real capacity.
- Active monitoring of bounces, deferrals, and complaints.
- Proper sender identity and authentication setup.
- Halting increases when negative signals appear.

There is no universal warm-up schedule guaranteeing Inbox placement across all mailbox providers. Reputation can involve accounts, IPs, domains, and other factors. Warm-up is not a trick to fool filters; it is responsible sending paired with observability.

## 11. Transport Limits Differ from Recipient Limits

Provider quotas can be enforced on:

- SMTP messages/second.
- Recipients/minute.
- Active connections.
- Daily quota per account.
- Domain-specific throttling.
- Message size and attachment limits.

These limits belong to the transport layer:

~~~text
Application:
  Consent + suppression + recipient frequency

Dispatcher:
  Provider rate + max concurrency + backoff

Transport:
  JavaMailSender + SMTP
~~~

A per-JVM limiter does not protect global quotas across multiple instances. If each instance allows 20 sends/second and there are 10 instances, total traffic can exceed provider limits. For global quotas, use a shared limiter/scheduler or controlled budget partitioning.

## 12. Recipient Signals and Reliability Levels

| Signal | Source | Meaning | Caution Needed |
| --- | --- | --- | --- |
| Hard bounce | Provider/DSN | Undeliverable with explicit error | Classify root cause properly |
| Soft bounce/deferred | Provider/SMTP | Temporarily undelivered | May recover |
| Spam complaint | Feedback event | Recipient reported spam | Coverage may vary across providers |
| Unsubscribe | Preference center/link | Request to stop mail | Must honor exact scope |
| Reply | Inbound mailbox/CRM | Engagement via reply | May be auto-reply/bounce |
| Click | Tracking/links | URL accessed | Bots/security scanners can click |
| Open | Tracking pixel | Image loaded | Proxies/caches/privacy protections |
| Conversion | In-product behavior | Target action completed | Attribution is uncertain |
| No observed engagement | Missing events | No evidence of interaction | Does not prove user did not read |

A "no-open" signal is far weaker than an explicit unsubscribe request. Never let an indirect engagement metric override recipient control.

## 13. Hard Bounces and Suppression Lists

Hard bounces are typically permanent delivery errors like nonexistent mailboxes, though provider labeling varies. Do not rely on code `550` alone to automatically conclude a recipient does not exist: some rejections stem from sender policy or content.

On a reliable hard bounce:

1. Correlate provider message ID, notification ID, and recipient.
2. Store the failure code and original event.
3. Suppress the address within an appropriate scope.
4. Stop sending the same mail type to the failing address.
5. Provide a flow to update/verify a new address.
6. Distinguish recipient errors from sender/provider policy errors.

If a user changes their email address, a hard bounce on the old address should not necessarily disqualify the new address. Scope suppression cleanly by email address, user, or category.

## 14. Soft Bounces, Deferrals, and Retries

Soft bounces or deferrals typically reflect temporary non-delivery, such as full mailboxes, busy providers, or traffic limits.

Distinguish:

- SMTP server **temporarily rejects submission** before accepting DATA: application workers may need to retry.
- SMTP relay **already accepted submission** and reports deferred downstream: the provider may be retrying delivery itself. The application must not immediately submit a duplicate copy.

When deferrals rise:

- Slow down sending to the affected provider/domain.
- Respect cooldown/throttling guidance.
- Check account quotas and sender reputation.
- Monitor provider delivery events.
- Do not hot-retry all messages.
- Do not permanently suppress without permanent failure evidence.

This is why `SUBMITTED` must be separated from `DELIVERED` in the application.

## 15. Spam Complaints Are a Strong Signal

Complaints occur when recipients report unwanted email via mailbox providers. Feedback availability varies by provider, yet on credible complaints the application must react fast.

A handling flow:

~~~text
Provider sends complaint event
           |
           v
Webhook verifies authenticity
           |
           v
Correlate recipient / notification
           |
           v
Deduplicate event
           |
           v
Suppress relevant marketing scope
           |
           v
Review cadence, list source, content
~~~

Spam complaints should not merely increment a reporting counter. If a campaign is still running, suppression must stop unsent emails.

A campaign with high clicks yet high complaints should not be considered a success based on click rate alone.

## 16. Unsubscribe and Preference Centers

Unsubscribe is a direct signal: the recipient wants to stop receiving a category of notifications. Systems should offer clear controls for:

- Leaving a specific newsletter.
- Leaving all marketing mail.
- Choosing lower frequency.
- Choosing topics of interest.
- Snoozing emails for a period if supported by the product.

For bulk marketing, systems typically include an easy-to-find unsubscribe link and may add `List-Unsubscribe` / `List-Unsubscribe-Post` headers per relevant standards and provider policies. Do not add headers while forgetting to build the endpoint that actually updates preferences.

Design secure, tamper-resistant unsubscribe links/tokens and check preference state when workers dispatch. Consent, retention, and unsubscribe laws vary by market; applications must meet applicable obligations rather than substituting a frequency cap.

## 17. Open Rate: An Indirect Signal with Heavy Noise

Open tracking typically embeds a pixel image in HTML; when loaded, the server logs a request and infers the email was opened.

However:

- Some email clients block images.
- Privacy proxies prefetch/cache images automatically.
- Emails can be read without loading pixels.
- Security scanners fetch assets.
- Multiple opens do not necessarily generate multiple requests.
- Plain-text messages have no pixel tracking.

Therefore:

- `OPENED` only means the system observed an image-load signal.
- `NOT_OPENED` only means no event was observed.
- Never use open rate alone to judge Inbox placement.
- Never drop recipients solely for lacking open events.
- Never ramp up marketing sends just because proxies inflated open rates.

Tracking also involves privacy. Collect only necessary data with proper legal/consent basis under applicable policies.

## 18. Click Rate: Better in Some Cases, Still Imperfect

Click events occur when a user or security system accesses a URL inside an email. Security gateways may open links automatically to scan for threats, producing click events even when no human clicked.

Therefore:

- Measure unique recipient clicks rather than raw click counts when tracking engagement.
- Filter bot/scanner traffic where reliable signals exist.
- Cross-check with real in-app actions.
- Never treat clicks as guaranteed conversions.
- Never measure "human read" solely by clicks.

### Links Must Not Trigger Dangerous Actions via GET

Security scanners fetch URLs automatically. Never design email links so a GET request automatically transfers funds, deletes accounts, or completes sensitive actions. Require confirmation steps, valid tokens, session/permission checks, and appropriate HTTP methods.

## 19. Replies and In-Product Behavior

Replies can signal interest, yet not every reply comes from a human.

Distinguish:

- Genuine user replies with content.
- Auto-replies/out-of-office notices.
- Bounce reports.
- Mailing list messages.
- System-generated support tickets.
- Replies containing complaints/unsubscribe requests.

With inbound mail integration, classify and route replies by purpose rather than feeding private message content wholesale into marketing analytics unnecessarily.

Business signals such as logging in after an email, completing onboarding, or using a feature can be helpful. Yet conversion attribution needs clear definitions: an event occurring after an email does not prove the email was its sole cause.

## 20. Signal Priority Order

A system should prioritize:

1. Suppression and unsubscribe/complaint requests.
2. Consent and recipient preferences.
3. Business validity (email still relevant, token unexpired).
4. Frequency caps and quiet hours.
5. Provider rate quotas/cooldowns.
6. Engagement-based optimization.

For example, someone who unsubscribed must not receive newsletters even if they clicked heavily in the past. A hard-bounced address must not receive more mail simply because an old open pixel exists.

Engagement data tunes experience; it is never an excuse to ignore explicit opt-outs.

## 21. Designing the Application Model

Email intent can be modeled independently of SMTP:

~~~java
public enum MailCategory {
    SECURITY,
    TRANSACTIONAL,
    OPERATIONAL,
    ONBOARDING,
    MARKETING
}
~~~

~~~java
public record MailIntent(
    UUID notificationId,
    String recipientId,
    String recipientAddress,
    MailCategory category,
    String templateKey,
    String campaignId,
    Instant requestedAt
) {}
~~~

Policy returns a decision:

~~~java
public enum EligibilityAction {
    ALLOW,
    DEFER,
    SUPPRESS
}
~~~

~~~java
public record MailEligibilityDecision(
    EligibilityAction action,
    Instant nextAllowedAt,
    String reason
) {}
~~~

Meaning:

| Action | Behavior |
| --- | --- |
| `ALLOW` | May reserve slot and enqueue |
| `DEFER` | Insufficient spacing/rate; schedule later while still relevant |
| `SUPPRESS` | Must not send within policy scope |

`MailIntent` and `MailEligibilityDecision` do not depend on `MimeMessage` or `JavaMailSender`. They live at the application boundary; the SMTP adapter handles transport only.

## 22. Eligibility Service in Spring

Ports:

~~~java
public interface RecipientPreferences {
    boolean permits(String recipientId, MailCategory category);
}
~~~

~~~java
public interface SuppressionService {
    boolean isSuppressed(
        String recipientAddress,
        MailCategory category
    );
}
~~~

~~~java
public interface FrequencyCapService {
    MailEligibilityDecision check(
        String recipientId,
        MailCategory category,
        Instant now
    );
}
~~~

Use case:

~~~java
public class MailEligibilityService {

    private final RecipientPreferences preferences;
    private final SuppressionService suppression;
    private final FrequencyCapService frequencyCap;
    private final Clock clock;

    public MailEligibilityService(
            RecipientPreferences preferences,
            SuppressionService suppression,
            FrequencyCapService frequencyCap,
            Clock clock) {
        this.preferences = preferences;
        this.suppression = suppression;
        this.frequencyCap = frequencyCap;
        this.clock = clock;
    }

    public MailEligibilityDecision evaluate(MailIntent intent) {
        if (suppression.isSuppressed(
                intent.recipientAddress(),
                intent.category())) {
            return new MailEligibilityDecision(
                EligibilityAction.SUPPRESS,
                null,
                "Recipient is suppressed"
            );
        }

        if (!preferences.permits(
                intent.recipientId(),
                intent.category())) {
            return new MailEligibilityDecision(
                EligibilityAction.SUPPRESS,
                null,
                "Recipient preference disallows this category"
            );
        }

        return frequencyCap.check(
            intent.recipientId(),
            intent.category(),
            clock.instant()
        );
    }
}
~~~

The code above illustrates **policy evaluation flow**, without handling race conditions yet. A standalone check is insufficient when two requests compete for the last slot. Atomic reservation inside an appropriate transaction is required.

## 23. Atomic Frequency Reservation

Suppose a recipient has one marketing slot left:

~~~text
Worker A: check used=0 -> ALLOW
Worker B: check used=0 -> ALLOW
Worker A: enqueue
Worker B: enqueue
~~~

Both read before updating, easily exceeding the cap. The fix is **atomic reservation** via a database/shared store using transactions, conditional updates, and unique constraints.

PostgreSQL table example for counting caps per window:

~~~sql
CREATE TABLE mail_frequency_usage (
    recipient_id VARCHAR(120) NOT NULL,
    category VARCHAR(40) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    used_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (recipient_id, category, window_start)
);
~~~

Illustrative reservation operation:

~~~sql
INSERT INTO mail_frequency_usage (
    recipient_id, category, window_start, used_count
)
VALUES (
    :recipientId, :category, :windowStart, 1
)
ON CONFLICT (
    recipient_id, category, window_start
)
DO UPDATE
SET used_count = mail_frequency_usage.used_count + 1
WHERE mail_frequency_usage.used_count < :limit
RETURNING used_count;
~~~

Assume `limit` is a validated positive integer. When no row is returned (cap reached), the application can DEFER or SUPPRESS. This is a **single fixed window** example; rolling windows, minimum gaps, and multiple concurrent caps require more detailed design.

**Reservation and outbox insertion should occur in the same database transaction** to avoid holding a slot without creating the notification job:

~~~text
BEGIN TRANSACTION
   Check preference and suppression
   Atomic reserve slot
   Insert mail_outbox
COMMIT
~~~

When daily, weekly, and campaign caps coexist, ensure all reservations commit together or roll back if any cap lacks capacity.

## 24. A Retry Is Not a New Marketing Email

A notification that reserved a slot can fail SMTP and retry:

~~~text
Notification N-123
     |
     +--> Attempt 1: timeout
     +--> Attempt 2: temporary reject
     +--> Attempt 3: SUBMITTED
~~~

For frequency capping, this remains **one logical notification**, not three separate marketing emails. Counters should tie to the unique notification ID; attempts are tracked separately.

If a worker gets an ambiguous SMTP outcome, do not rush to release the slot because the server may have accepted the email. If the job is canceled before the first send, policy may release the reservation consistently.

Never generate a new notification with a different ID on each retry, which would bypass deduplication and frequency caps.

## 25. Combining Outbox, Worker, and Rate Limiter

A deployment architecture:

~~~text
Business event / campaign
          |
          v
Eligibility + consent + suppression
          |
          v
Atomic recipient frequency reservation
          |
          v
Durable outbox
          |
          v
Dispatcher / TaskExecutor
          |
          +--> Provider rate budget
          +--> Per-domain pacing
          +--> Concurrency limit
          +--> Retry/backoff
          |
          v
MailDeliveryPort / JavaMailSender
          |
          v
SMTP relay
          |
          v
Submission status + provider events
          |
          v
Suppression / preference / metrics
~~~

`JavaMailSender` handles transport. Eligibility, reservation, outbox, rate limiting, and event handling are logic built inside the application or notification platform.

Do not treat an in-memory `@Async`/`TaskExecutor` queue as a durable queue. For important emails, an outbox enables recovery after process restarts. Workers should claim batches sized to executor capacity rather than letting thousands of `PROCESSING` records expire their leases while waiting for threads.

### SMTP Configuration

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000

app:
  mail:
    dispatch:
      batch-size: 20
      poll-delay-ms: 1000
    frequency:
      marketing:
        max-per-day: 1
~~~

The `app.mail.*` properties are **application-defined policies**, not built-in Spring Boot frequency-cap flags you just switch on.

### Rate Limiter Before Transport

~~~java
public interface MailRateLimiter {
    boolean tryAcquire(
        String providerAccount,
        String recipientDomain
    );
}
~~~

~~~java
public class RateLimitedMailDispatcher {

    private final MailRateLimiter limiter;
    private final MailDeliveryPort delivery;

    public DispatchResult dispatch(
            String account,
            String recipientDomain,
            OutgoingMail mail) {

        if (!limiter.tryAcquire(account, recipientDomain)) {
            return DispatchResult.DEFERRED;
        }

        delivery.send(mail);
        return DispatchResult.SUBMITTED;
    }
}
~~~

`MailDeliveryPort`, `DispatchResult`, and `OutgoingMail` are illustrative contracts, not built-in Spring Framework Mail classes. When `delivery.send` throws an exception, the worker must classify it and persist retry/failed state. Never catch it and report SUBMITTED anyway.

Rate limits should use shared coordination when multiple sender instances share provider quotas. Retries must also be subject to rate limits.

## 26. Scheduling by Time Zone and Quiet Hours

If the system knows recipient time zones and preferences, it can avoid sending marketing at inconvenient times.

A model:

~~~java
public record RecipientDeliveryPreference(
    String recipientId,
    ZoneId timeZone,
    LocalTime quietFrom,
    LocalTime quietUntil
) {}
~~~

Edge cases to handle:

- Quiet hours can span midnight.
- The recipient's time zone may differ from the server's.
- Daylight saving time makes certain local times repeat or not exist.
- An email with a business deadline may lose value after quiet hours.
- OTP/security emails need dedicated rules instead of default marketing deferrals.

Use IANA time zones where needed (e.g., `Asia/Ho_Chi_Minh`, `Europe/Paris`) rather than fixed offsets. Store actual execution schedules in `Instant`/UTC while computing recipient local hours via `ZoneId` if policy requires.

## 27. Provider Webhooks for Delivery and Engagement Signals

Spring Mail does not include delivered/opened/clicked events. A provider integration can normalize payloads into an application model:

~~~java
public enum MailProviderEventType {
    ACCEPTED,
    DELIVERED,
    DEFERRED,
    HARD_BOUNCE,
    SOFT_BOUNCE,
    COMPLAINED,
    UNSUBSCRIBED,
    OPENED,
    CLICKED
}
~~~

~~~java
public record MailProviderEvent(
    String provider,
    String providerEventId,
    String providerMessageId,
    String notificationId,
    String recipientId,
    MailProviderEventType type,
    Instant occurredAt
) {}
~~~

This is an illustrative internal schema. Providers differ in event names, field names, and level of support.

### Webhook Authentication

Never trust an Internet payload simply because it claims to be a complaint from the provider. Handlers must:

1. Verify signatures/authentication per provider protocol.
2. Validate timestamps/replay windows if supported.
3. Validate schema and enforce request size limits.
4. Correlate with provider message ID/notification ID.
5. Deduplicate events.
6. Persist events durably when reliability is needed.
7. Update suppression/status/metrics within the proper scope.
8. Avoid logging unnecessary PII/secrets.

A forged complaint webhook can cause the system to suppress valid customers; verifying event authenticity is a security requirement.

## 28. Webhook Idempotency and Out-of-Order Events

Providers may resend webhooks after timeouts, or one event may arrive later than another.

Illustrative PostgreSQL table:

~~~sql
CREATE TABLE mail_provider_event (
    provider VARCHAR(100) NOT NULL,
    provider_event_id VARCHAR(255) NOT NULL,
    notification_id VARCHAR(120),
    event_type VARCHAR(60) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider, provider_event_id)
);
~~~

If a provider does not supply stable event IDs, design a suitable deduplication scheme while guarding against accidentally merging distinct events.

A duplicate `COMPLAINED` must not increment complaint counts twice. A late-arriving `DELIVERED` must not blindly overwrite a bounce status without checking the exact recipient/attempt/message. Keeping event history supports investigation.

### Illustrative Signal Handler

~~~java
public class MailSignalHandler {

    private final MailEventRepository events;
    private final SuppressionService suppression;

    @Transactional
    public void handle(MailProviderEvent event) {
        if (!events.insertIfAbsent(event)) {
            return;
        }

        switch (event.type()) {
            case HARD_BOUNCE -> suppression.suppressAddress(
                event.recipientId(), "HARD_BOUNCE");

            case COMPLAINED -> suppression.suppressMarketing(
                event.recipientId(), "SPAM_COMPLAINT");

            case UNSUBSCRIBED -> suppression.suppressMarketing(
                event.recipientId(), "UNSUBSCRIBED");

            default -> {
                // Update delivery/engagement events separately.
            }
        }
    }
}
~~~

Repositories/services in the example are application-defined contracts. The handler assumes the webhook has already been verified, the event mapped, and the recipient ID authenticated. Suppression scope should be decided cleanly by email address, user, and category.

## 29. Metrics for Reading Signals Accurately

| Metric | Interpretation | Caveat |
| --- | --- | --- |
| Submission success rate | Successful submissions / attempts | Not delivery rate |
| Delivery rate | Delivered / accepted messages per provider | Provider semantics vary |
| Hard bounce rate | Hard bounces / defined denominator | Bounce classification must be accurate |
| Deferral rate | Deferrals / messages or attempts | One message can defer multiple times |
| Complaint rate | Complaints / delivered or sent per source | May only observe a subset |
| Unsubscribe rate | Unique unsubscribes / delivered marketing | Must filter duplicate events |
| Unique click rate | Recipients with clicks / delivered | Scanners/bots introduce noise |
| Open rate | Observed opens / delivered or sent | Privacy proxies skew results |
| Frequency distribution | Emails/recipient/rolling window | Spots over-contacted cohorts |
| Queue age p95 | Wait time before submission | Reflects saturation |
| Retry/throttle rate | Transient errors / submission attempts | Inspect per provider/domain |
| Conversion | Business outcomes / cohort | Attribution requires clear definition |

**Always state the denominator.** "Complaint rate per sent" and "complaint rate per delivered" cannot be compared directly. For unique engagement, deduplicate per recipient/message/event semantics.

Segment by campaign, category, provider, sending domain, recipient domain, or cohort. Avoid putting raw emails/notification IDs into metric labels due to data exposure and high cardinality.

## 30. Using Signals to Adjust Cadence

Example segmentation:

| Group | Signals | Response |
| --- | --- | --- |
| Clearly engaged | Consent, meaningful clicks/conversions, no complaints | Maintain cadence, still capped |
| Unclear engagement | No opens/clicks seen, no complaints | Do not assume disinterest; review content/preferences |
| Negative feedback | Complaints/unsubscribes/hard bounces | Suppress within appropriate scope |
| Provider throttled | Frequent temporary deferrals | Reduce rate, honor cooldowns |
| Incomplete workflow | User has not taken next step | Limited reminders; honor deadlines and quiet hours |

Do not increase cadence over a single click. Nor delete an entire list because open rates dropped after an email client privacy change.

A healthy feedback loop:

~~~text
Send small batches
       |
       v
Observe provider + business signals
       |
       v
Negative signals rise?
       |
    +--+--+
    |     |
   Yes    No
    |     |
    v     v
 Reduce  Maintain or cautiously increase
 cadence within consent and quota
       |
       v
Continue monitoring
~~~

Cadence experiments should run on clearly defined cohorts with controlled changes and without violating consent.

## 31. Sender Reputation Has No Universal Formula

Mailbox providers may consider volume history, IP/domain reputation, sender authentication, recipient feedback, and many other factors. Exact formulas are not fully public and can change.

Therefore:

- No fixed warm-up schedule can guarantee Inbox placement everywhere.
- SPF/DKIM/DMARC are vital foundations yet do not guarantee placement.
- A campaign with low bounces can still land in Spam.
- Inflating open rates does not improve real deliverability.
- When volume/complaints/deferrals shift, inspect per provider/domain.
- Senders must respect recipient reality rather than optimizing "tricks" to mask list quality.

Deliverability should be measured from trustworthy sources and managed long-term, not inferred from an SMTP `250` reply.

## 32. Common Diagnostic Scenarios

| Symptom | Possible Cause | Investigation |
| --- | --- | --- |
| A domain returns many `421/4xx` | Throttling, busy server | Reduce pacing and check provider logs |
| Hard bounces rise | List contains invalid addresses | Audit consent sources, list hygiene |
| Complaints rise | Over-sending, unexpected content | Reduce cadence, fix preferences/unsubscribe |
| Unsubscribes rise | Wrong frequency/topics | Review recipient expectations |
| Open rate drops suddenly | Privacy/pixel-loading changes | Do not immediately assume placement dropped |
| Clicks spike right after send | Scanner/bot prefetching | Cross-check conversions and human behavior |
| High submissions, low delivered | Downstream filtering/deferrals | Provider delivery events |
| Queue backlog | Insufficient pool/rate quota | Outbox age, worker throughput |
| Security mail delayed by campaign | Shared queue/priority | Separate budgets/queues |
| High AUTH/TLS errors | Credentials or transport config | Fix infrastructure, do not increase retries |

Diagnosis must separate **pre-SMTP-acceptance errors**, **post-submission status**, and **lack of engagement signals**. Do not collapse everything into a single "deliverability score."

## 33. Testing Frequency Policies

Use an injectable `Clock`:

~~~java
Clock clock = Clock.fixed(
    Instant.parse("2026-11-12T08:00:00Z"),
    ZoneOffset.UTC
);
~~~

Test cases:

1. Recipient has free slot → ALLOW.
2. Recipient hits cap → DEFER/SUPPRESS per policy.
3. Multiple campaigns sharing a global cap.
4. Retrying the same notification ID does not increment cap usage.
5. Unsubscribing after enqueue but before submit → do not send marketing.
6. Complaints/hard bounces update suppression.
7. Transactional/security do not mistakenly consume marketing caps.
8. Rolling windows at day/week boundaries.
9. Time zones and DST when applying local schedules.
10. Two workers competing for the last slot yield only one successful reservation.

### Concurrent Reservation Test

~~~text
used_count = limit - 1

Worker A -----+
              +--> atomic reserve
Worker B -----+

Expected:
  Exactly one reservation succeeds.
~~~

Test concurrency against a real database/transaction semantics, not only single-threaded unit tests.

## 34. Testing Provider Signals

- Invalid webhook signatures must be rejected.
- Duplicate events must not increment counters twice.
- Hard bounces apply suppression to the right scope.
- Complaints/unsubscribes block subsequent marketing.
- Out-of-order events do not lose state.
- Bot opens/clicks are not automatically treated as conversions.
- Unknown notification IDs are stored for reconciliation.
- Provider outages do not lose critical events if durability is required.
- SMTP submission success is never labeled DELIVERED merely because a test fake returned success.

An SMTP test server like GreenMail/Mailpit verifies MIME and acceptance, yet does not fully simulate real spam filtering across all mailbox providers. Webhooks and signals should have dedicated contract tests/fixtures.

## 35. Anti-Patterns to Avoid

| Anti-Pattern | Consequence | Better Approach |
| --- | --- | --- |
| Setting only SMTP rate limits | One person still receives too much | Recipient frequency cap |
| Separate caps per campaign only | Overlapping campaigns stack up | Global/category cap |
| Sharing one FIFO queue for OTP and newsletters | Security mail delayed | Separate priorities/queues |
| Sending a whole campaign at once | Bursts/throttling | Pacing, batches |
| Not checking unsubscribe before submit | Sends after recipient opted out | Recheck suppression |
| Treating open as guaranteed read | Proxies/pixels add noise | Use multiple signals |
| Treating non-open as guaranteed disinterest | Drops valid recipients | Understand tracking limits |
| Treating every click as human | Bots/scanners cause false positives | Classify and verify |
| Retrying accepted messages deferred downstream | Risk of duplicates | Follow provider delivery/retries |
| Not suppressing hard bounces/complaints | Harmful repeat sends | Prompt suppression |
| Suppressing all `550` codes | May block valid emails | Inspect failure reason |
| Counting SMTP retries against recipient cap | Wastes cap slots | Count logical notifications |
| In-memory counters across instances | Races/cap overruns | Atomic shared reservation |
| Not verifying webhooks | Spoofed signals | Signature/auth + dedup |
| Enabling tracking without privacy review | Privacy risk | Collect only needed data |
| Treating SMTP success as Inbox | Misreports deliverability | Separate submission/delivery |
| Metric labels containing personal emails | PII leak and high cardinality | Cohort/category/provider |

## 36. Implementation Checklist in Spring Applications

1. **Classify emails** into transactional/security and marketing/lifecycle.
2. **Build preference, consent, and suppression models**.
3. **Define frequency caps** by recipient/category/campaign.
4. **Implement atomic reservation** in the same transaction creating outbox rows.
5. **Decouple application policy from SMTP adapters** via ports.
6. **Throttle rate/concurrency/pacing** per provider quotas.
7. **Keep jobs durable** for retries/restarts rather than relying on in-memory queues.
8. **Integrate provider webhooks** to ingest delivered/bounce/complaint/unsubscribe events.
9. **Verify and deduplicate events**, updating suppression promptly.
10. **Monitor multi-layer metrics** segmented by domain/campaign/cohort.
11. **Use opens/clicks with caveats**, without inferring human reads.
12. **Adjust cadence gradually** based on feedback and provider cooldowns.
13. **Test concurrency, time zones, unsubscribe races, and event duplication**.
14. **Periodically audit privacy, retention, and sender authentication**.

## 37. Key Takeaways

- **Send rate** is transport speed; **recipient frequency** is how often one person is contacted.
- An application can stay within SMTP quotas yet still send too frequently.
- Consent and suppression always come before marketing frequency caps.
- Do not apply a marketing cap to essential security/transactional emails.
- Atomic reservation prevents two workers from both taking the last slot.
- Retrying the same notification ID is not a new logical marketing email.
- Pacing and warm-up allow controlled volume growth yet do not guarantee Inbox placement.
- Transport rate limiters differ from recipient caps and minimum gaps.
- Credible hard bounces and complaints require serious handling.
- Soft bounces/deferrals must distinguish submission failures from downstream delays.
- Unsubscribes must affect emails still waiting in queues.
- Open pixels do not prove humans read; clicks can come from scanners.
- `JavaMailSender` does not provide engagement events out of the box; provider integration is required.
- Webhooks must be authenticated, deduplicated, and persisted accurately.
- Delivery, complaint, and open rates are comparable only with explicit denominators.
- Do not conflate `SUBMITTED`, `DELIVERED`, and `OPENED`.
- Protect recipient data and avoid personal info in logs or metric labels.

**Most important principle:** sustainable deliverability does not come from sending as much as possible as fast as possible. Systems should send to the **right person, for the right purpose, at the right frequency**, honoring opt-out signals and tracking evidenced feedback. When Spring Framework Mail sits behind consent policies, frequency caps, an outbox, rate limiters, and provider event handlers, applications can regulate sending proactively without overloading infrastructure or bothering recipients unnecessarily.
