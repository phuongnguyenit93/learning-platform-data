# Bounce and Unsubscribe Handling Policies

## 1. Why does a production email system need a dedicated policy?

In a **Spring Framework Mail** application, sending email usually starts with **JavaMailSender**, **MimeMessageHelper**, and an SMTP provider. However, a successful send call does not prove the email reached the recipient's inbox, and the fact that an address once received email does not mean it consents to every future email type.

A real system must handle two distinct groups of signals:

- **Bounce:** feedback that an email could not be delivered or was delayed. Signals can arrive from SMTP responses, Delivery Status Notifications (DSNs), Email Service Provider (ESP) webhooks, or reconciliation APIs.
- **Unsubscribe:** a recipient's request to stop receiving one or more email categories. Requests can arrive from preference pages, in-body links, **`List-Unsubscribe`** headers, **one-click unsubscribe** mechanisms, or verified support requests.

A weak policy can cause:

1. Continuing to send to addresses proven invalid, hurting list quality and sender reputation.
2. Sending marketing emails after the recipient unsubscribed.
3. Mistakenly blocking all critical emails due to a single temporary SMTP error.
4. Automatically suppressing recipients based on a spoofed bounce.
5. Sending the wrong **MAIL FROM/Return-Path**, breaking bounce correlation.
6. Double-counting states when an ESP redelivers the same webhook.
7. Letting a link scanner's GET request accidentally trigger an unsubscribe.
8. Skipping suppression checks right before sending, letting already-scheduled emails go out after user opt-out.
9. Mixing bounces, spam complaints, unsubscribes, and SMTP config errors into one status, causing wrong retries.

This lesson aims to build **a policy explicit enough to enforce, test, and operate**: every event has a trusted source, impact scope, state, change permissions, re-enablement rules, and an audit trail.

## 2. Bounces and unsubscribes are two different concepts

| Aspect | Bounce | Unsubscribe |
|---|---|---|
| Origin | Delivery system / ESP / receiving server | Recipient or authenticated action on recipient's behalf |
| Question answered | Could the message be delivered? | Does the recipient want to keep receiving this mail type? |
| Scope | Can apply to an attempt, message, or recipient | Usually per tenant, brand, list, or topic |
| Timing | Often arrives asynchronously after SMTP acceptance | Effective per policy once recorded |
| Common action | Retry, hold temporarily, or suppress unusable address | Stop emails within the chosen scope |
| Self-recoverable? | Soft bounces may clear; hard bounces need verification | Never auto-resubscribe without valid opt-in intent |
| Evidence to store | Provider event ID, recipient, error code, timestamp | Scope, timestamp, method, choice evidence |

**A hard bounce is not an unsubscribe.** The user may still want your emails while their mailbox was deleted or misspelled.

**An unsubscribe is not a hard bounce.** The address still exists and accepts mail, yet the recipient does not want a specific category of mail.

Both events can apply to the same recipient, so keep **contact deliverability state** and **subscription preference** independent, then compute send eligibility via a combined policy.

## 3. Distinguishing three easily confused email addresses

Suppose a message has:

~~~text
Header From:    news@brand.example
Header Reply-To: support@brand.example
SMTP MAIL FROM: bounce+N100@returns.brand.example
SMTP RCPT TO:   customer@example.net
~~~

Each address serves a role:

| Address | Role |
|---|---|
| **Header From** | Sender identity displayed inside the email |
| **Reply-To** | Address receiving ordinary reader replies |
| **SMTP MAIL FROM** | Envelope sender / reverse-path where mail systems typically send non-delivery reports |
| **RCPT TO** | Recipient address in the SMTP envelope; may include To, Cc, Bcc |
| **Return-Path** | Header typically added upon final delivery reflecting the reverse-path used |

A common mistake is seeing "bounce address" and confusing:

1. **The bouncing recipient address**, e.g. `customer@example.net`; versus
2. **The address receiving bounce reports**, e.g. `bounce+N100@returns.brand.example`.

They are completely different. **Suppression policies** act on the **bouncing recipient address**, not disabling the organization's bounce-receiving mailbox.

### Never set the Return-Path header yourself to override the SMTP envelope

~~~text
message.setHeader("Return-Path", "bounces@example.com")
~~~

is not a portable way to control **SMTP MAIL FROM**. Receiving mail servers normally set or rewrite `Return-Path` on delivery; ESPs may manage custom `MAIL FROM` via account/domain settings.

With Jakarta Mail SMTP transport, **`mail.smtp.from`** can set the envelope sender when supported by the implementation. When multiple tenants share one **`JavaMailSenderImpl`** bean, never mutate that property per request while other threads are sending: you easily leak bounce addresses or credentials across tenants. Use dedicated authorized sender profiles per account/tenant or official provider APIs to set envelope senders.

## 4. Timeline of SMTP submission and bounces

A typical lifecycle:

~~~text
09:00:00 Spring JavaMailSender.send(...)
           |
           v
09:00:01 ESP SMTP endpoint returns 250 Accepted
           |
           v
09:00:02 Application records SUBMITTED
           |
           v
09:02:00 ESP attempts delivery to destination mail server
           |
           +-- Destination temporarily returns 451 -> deferred/retry
           |
           v
09:20:00 Destination returns 550 -> failure
           |
           v
09:20:05 ESP emits bounce webhook or DSN
           |
           v
09:20:06 Inbound event handler marks recipient BOUNCED
           |
           v
09:20:07 Policy updates suppression based on confidence level
~~~

The **`send(...)`** call succeeded at 09:00:01, yet delivery failed later. There is no contradiction:

- **SUBMITTED/ACCEPTED** describes the observed SMTP submission hop.
- **DELIVERED** from a provider means the provider recorded a delivery event, not necessarily that the user read it or it landed in the primary inbox.
- **BOUNCED** is a non-delivery outcome at a later hop.
- **DEFERRED** is an unfinished state, not yet a permanent bounce.
- **OPEN/CLICK** events, if offered by an ESP, are also not infallible proof of delivery due to privacy protections and automated link scanners.

Because bounces are usually **asynchronous**, merely catching **`MailSendException`** in Java is insufficient to build an accurate suppression list.

## 5. Classifying bounces before taking action

| Group | Example | Reference handling |
|---|---|---|
| **Hard bounce / invalid mailbox** | Provider confirms recipient does not exist | Stop sending to recipient; request address fix/verification |
| **Soft bounce / temporary** | Mailbox full, server temporarily unavailable, 4xx reply | Let provider retry/backoff; optionally temporary hold |
| **Policy rejection** | Sender domain/reputation/SPF/DKIM/DMARC rejected | Investigate sender/provider; do not assume recipient is bad |
| **Content/size rejection** | Message exceeds limits or content blocked | Fix content/attachments/config |
| **Provider throttling** | Rate/quota limit exceeded | Back off and throttle throughput; do not suppress recipient |
| **Unknown/ambiguous** | Insufficient detail or conflicting outcomes | Keep event and reconcile |
| **Spam complaint** | Recipient reports spam via feedback loop | Stop scoped emails, prioritizing marketing blocks |

Never apply a naive formula:

~~~text
SMTP 5xx = delete recipient
SMTP 4xx = always retry immediately
~~~

Reasons:

- SMTP 5xx can reflect **sender policies**, authentication, size, or reputation rather than a vanished recipient mailbox.
- SMTP 4xx is usually temporary, yet aggressive retries worsen issues or blow quotas.
- ESPs define their own taxonomies: **hard**, **soft**, **suppressed**, **blocked**, **deferred**, **complaint**. Normalize them while keeping raw provider codes for investigation.

In production policies, classify **error code + event source + context** before suppressing.

## 6. Reading SMTP enhanced status codes in context

Codes you may encounter:

~~~text
550 5.1.1 User unknown
451 4.2.2 Mailbox temporarily full
550 5.7.1 Message rejected by policy
421 4.7.0 Rate limit / temporary deferral
~~~

Operational meaning:

- **5.1.1** usually indicates a nonexistent recipient/mailbox.
- **4.2.2** usually indicates a temporary mailbox limit.
- **5.7.1** can relate to policy or security—insufficient to prove the recipient address is invalid.
- **4.7.x** usually indicates temporary security/policy/throttling.

These are illustrative interpretations: wording, enhanced codes, subcodes, and provider specifics vary.

An event schema should hold:

~~~json
{
  "provider": "primary-esp",
  "providerEventId": "evt-901",
  "notificationId": "N100",
  "recipientRef": "R12",
  "eventType": "bounce",
  "classification": "invalid_recipient",
  "smtpCode": "550",
  "enhancedStatus": "5.1.1",
  "occurredAt": "2026-11-12T09:20:00Z"
}
~~~

This object is an **application normalized schema**, not a mandatory webhook format across all ESPs.

## 7. When to suppress immediately vs observe further

No single threshold fits all providers and mail types. A policy can start with:

| Event | Initial action |
|---|---|
| Hard bounce with strong evidence recipient doesn't exist | Suppress recipient for relevant sending streams |
| Single soft bounce | Record, rely on backoff/ESP retries, do not permanently suppress |
| Repeated soft bounces within a window | Place recipient on temporary hold and re-evaluate per policy |
| Provider-wide throttling | Throttle sender/account instead of suppressing recipients |
| Policy rejections across multiple domains | Inspect sender reputation and DNS/authentication |
| Credible spam complaint | Block scoped marketing stream immediately per policy |
| Valid unsubscribe | Apply recipient choice to specified scope |
| Spoofed or uncorrelated bounce | Quarantine/ignore policy mutation; record audit |

**Never purge an address from every tenant's lists just because it hard-bounced in one tenant.** Isolation depends on account models, legal boundaries, consent, and source trustworthiness.

Conversely, when multiple tenants share a provider account and the vendor places an address on **account-level suppression**, the app needs awareness of that shared block to avoid repeatedly sending into rejections.

## 8. Unsubscribe is a scoped choice

A user may wish to:

- Stop the **weekly newsletter**, while keeping invoices.
- Stop all **marketing** emails from one brand.
- Stop all optional emails from one tenant.
- Reduce digest frequency instead of full opt-out.
- Mute reminders for a specific event type.

Therefore do not store only:

~~~text
email_unsubscribed = true
~~~

for every situation.

A clearer model:

~~~text
tenant_id = tenant-A
recipient_key = R12
scope_type = LIST
scope_key = weekly-newsletter
decision = UNSUBSCRIBED
effective_at = 2026-11-12T09:00:00Z
source = ONE_CLICK_POST
~~~

Or:

~~~text
scope_type = STREAM
scope_key = MARKETING
decision = UNSUBSCRIBED
~~~

**Explain the scope clearly in the UI and inside emails.** Users clicking "Unsubscribe from weekly newsletter" must not accidentally lose invoices, nor should "Stop all marketing emails" be interpreted as opting out of one tiny campaign only.

## 9. Email streams and precedence rules

A useful taxonomy:

| Stream | Example | Preference policy |
|---|---|---|
| **Marketing/promotional** | Promotions, newsletters, offers | Must honor applicable consent/unsubscribes |
| **Product updates** | Product news or periodic digests | Follow matching preference policy |
| **Transactional** | Order confirmations, invoices, transaction updates | Send only when genuinely required by business and authorized |
| **Security/account** | OTPs, login alerts, password changes | Dedicated policy for TTLs and security risks |
| **Operational/legal notice** | Mandatory notices under contracts/regulations | Verify legal basis and actual content |

You cannot rely on a code-assigned **`TRANSACTIONAL`** label to exempt everything from rules. A promotional email does not become transactional merely because it goes out after a purchase.

Even genuinely mandatory emails need product/legal-approved rules. **A verified hard-bounced address still cannot receive mail merely by setting `type=SECURITY`.** Use fallback channels or prompt the user to update their address.

## 10. Order of eligibility checks before SMTP

A **send eligibility service** should combine multiple gates rather than checking only a suppression list:

~~~text
Notification intent
        |
        v
Authenticated tenant and sender profile
        |
        v
Business event still relevant?
        |
        v
Recipient address valid and verified as required?
        |
        v
Consent and unsubscribe for this stream/list?
        |
        v
Bounce suppression or temporary hold?
        |
        v
Spam complaint / abuse policy?
        |
        v
Deadline + campaign window + quota?
        |
        v
Final admission before JavaMailSender.send(...)
~~~

A **deny** can stem from multiple causes. For instance, a recipient unsubscribed from marketing and also hard-bounced; record **both reasons**, even if an API surfaces one primary reason code.

A precedence policy might be:

1. Invalid tenant/sender authorization: deny immediately.
2. Active unsubscribe in current scope: do not send that stream.
3. Applicable complaint/suppression: do not send per policy.
4. Business event obsolete or notification expired: skip/expire.
5. Quota or provider unavailable: defer if still within deadline.
6. Only when all pass, create an SMTP attempt.

**Exact ordering is a product decision**, yet priority bugs must never bypass an unsubscribe due to quotas or because the email was queued earlier.

## 11. What is the List-Unsubscribe header for?

**List-Unsubscribe** is an email header supporting list opt-out mechanisms. Some mail clients/providers surface an unsubscribe action near sender details based on these headers and other signals.

Example:

~~~text
List-ID: Weekly Offers <offers.brand.example>
List-Unsubscribe: <mailto:unsubscribe+abc@brand.example>,
 <https://mail.brand.example/u/opaque-token>
~~~

Meaning:

- **mailto:** lets the recipient or mail client email an unsubscribe handler address.
- **HTTPS URL:** supplies an endpoint or preference management page.
- **List-ID:** identifies the list; not a security key.

Not every provider/mail client renders the same unsubscribe button. Including the header **does not guarantee** the mailbox UI exposes a specific widget; providers apply their own policies on reputation, signing, and traffic type.

### Headers do not replace in-body links

For promotional emails, still provide a visible **unsubscribe or preference center** link inside the message body per applicable policies and regulations. Headers serve mail clients, while footers let readers act even when clients ignore `List-Unsubscribe`.

## 12. One-click unsubscribe and RFC 8058

**One-click unsubscribe** lets mail providers send an **HTTP POST** to a designated HTTPS endpoint to opt out of the corresponding list without opening a page requiring further confirmation.

Two typical headers:

~~~text
List-Unsubscribe: <https://mail.brand.example/u/TOKEN>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

When supported by clients/providers, the request looks like:

~~~http
POST /u/TOKEN HTTP/1.1
Host: mail.brand.example
Content-Type: application/x-www-form-urlencoded

List-Unsubscribe=One-Click
~~~

**TOKEN** represents an appropriately scoped opaque capability, never the recipient's raw email.

Principles:

- **HTTPS** to protect tokens in transit.
- **POST** performs the unsubscribe state change.
- **GET must never auto-unsubscribe**, because security link scanners fetch URLs via GET.
- Endpoint must be fast, idempotent, and require neither login nor confirmation forms.
- Never demand CAPTCHAs or logins to complete a properly triggered provider one-click action.
- Avoid mandatory HTTP redirects on one-click POSTs; process directly.
- One-click headers must be paired with proper **DKIM signing**. Under RFC 8058, a valid DKIM signature must cover `List-Unsubscribe` and `List-Unsubscribe-Post`.

**JavaMailSender only builds/sends MIME; it does not ensure valid DKIM signing.** Signing is normally handled by the ESP/gateway or a dedicated tested signing component.

## 13. Why must GET never mutate state?

Some mail clients, antivirus gateways, or anti-phishing scanners automatically fetch links before a user clicks.

If an endpoint behaves like:

~~~text
GET /unsubscribe?email=customer@example.net
   -> set subscribed=false
~~~

a link scanner touching the URL unsubscribes the recipient without their intent.

Safer design:

~~~text
GET /preferences/TOKEN
    -> display preference page
    -> no state change

POST /u/TOKEN
    -> one-click unsubscribe
    -> update list/stream authorized by token
~~~

Footer links can open the preference page via GET and ask for an explicit user click. However, **one-click POSTs from mail providers must complete the unsubscribe without a second interaction**.

Never use the same side-effecting GET URL for both email footers and `List-Unsubscribe`.

## 14. Unsubscribe tokens must be narrowly scoped capabilities

A URL must not be:

~~~text
https://mail.example.com/u?email=person@example.net
~~~

because addresses are guessable, appear in logs, and do not prove the caller is authorized to opt out that recipient's list.

Instead use an **opaque random token**:

~~~text
https://mail.example.com/u/6xf...opaque...n2
~~~

The token maps backend-side to:

~~~text
tenant_id       = tenant-A
recipient_key   = R1001
list_id         = weekly-offers
scope_type      = LIST
purpose         = ONE_CLICK_UNSUBSCRIBE
issued_at       = ...
revoked_at      = null
~~~

Design principles:

1. Generate tokens with a **cryptographically secure random generator** and sufficient entropy, never sequential IDs.
2. Narrow scope: unsubscribe only the specified list/stream without altering unrelated preferences.
3. No readable emails, sensitive tenant IDs, or personal data in URLs.
4. Store **token hash/HMAC** instead of plaintext tokens when possible to limit DB leak blast radius.
5. Set lifetimes and revocation policies matching real email behavior: users may open older emails weeks or months later.
6. Restrict token capabilities: valid for unsubscribe only, never account access or reading recipient profiles.
7. Keep full URLs/tokens out of access logs and third-party analytics.
8. Support **idempotency**: repeated clicks or provider retries do not create duplicate side effects.

An unsubscribe token is a **bearer capability**: anyone holding the URL can opt out within its scope. That suits one-click flows, provided scope stays tight and tokens never grant elevated privileges.

## 15. Example schema for tokens and subscription preferences

PostgreSQL example:

~~~sql
CREATE TABLE mail_unsubscribe_token (
    id               UUID PRIMARY KEY,
    tenant_id        VARCHAR(120) NOT NULL,
    recipient_key    VARCHAR(240) NOT NULL,
    scope_type       VARCHAR(30) NOT NULL,
    scope_key        VARCHAR(160) NOT NULL,
    token_hash       BYTEA NOT NULL UNIQUE,
    issued_at        TIMESTAMPTZ NOT NULL,
    expires_at       TIMESTAMPTZ,
    revoked_at       TIMESTAMPTZ,
    CHECK (scope_type IN ('LIST', 'STREAM', 'BRAND'))
);

CREATE TABLE mail_subscription_preference (
    tenant_id        VARCHAR(120) NOT NULL,
    recipient_key    VARCHAR(240) NOT NULL,
    scope_type       VARCHAR(30) NOT NULL,
    scope_key        VARCHAR(160) NOT NULL,
    decision         VARCHAR(30) NOT NULL,
    decision_at      TIMESTAMPTZ NOT NULL,
    decision_source  VARCHAR(50) NOT NULL,
    version          BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (
        tenant_id, recipient_key, scope_type, scope_key
    ),
    CHECK (
        decision IN ('SUBSCRIBED', 'UNSUBSCRIBED')
    )
);
~~~

This is an illustrative application schema, not default Spring Mail tables. **`token_hash`** can be an HMAC-SHA-256 of the token using a protected key. For high-entropy random tokens, plain cryptographic hashes may also work, subject to threat modeling and key rotation.

**Never let a single preference row erase consent history.** Keep a **`mail_subscription_audit`** table recording state transitions, sources, and timestamps for reconciliation.

### Why have both scope type and scope key?

One recipient may have:

~~~text
LIST  weekly-offers -> UNSUBSCRIBED
LIST  product-news  -> SUBSCRIBED
STREAM MARKETING    -> UNSUBSCRIBED
~~~

Combined policies must let **broader-scope blocks** override narrower scopes. In this example, `MARKETING=UNSUBSCRIBED` blocks both `weekly-offers` and `product-news`, even though `product-news` says `SUBSCRIBED`.

## 16. Spring MVC example handling one-click POST

An illustrative controller:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/mail/unsubscribe")
public class OneClickUnsubscribeController {

    private final UnsubscribeService service;

    public OneClickUnsubscribeController(
            UnsubscribeService service
    ) {
        this.service = service;
    }

    @PostMapping(
        path = "/{token}",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Void> unsubscribe(
            @PathVariable String token,
            @RequestParam("List-Unsubscribe") String action
    ) {
        if (!"One-Click".equals(action)) {
            return ResponseEntity.badRequest().build();
        }

        // Service handles idempotently within the token's scope only,
        // ignoring any caller-supplied recipientId/listId.
        service.unsubscribeByOneClickToken(token);
        return ResponseEntity.ok().build();
    }
}
~~~

**`UnsubscribeService`** is application-defined. It must:

- Hash the token and look up an unrevoked/unexpired record per policy.
- Derive tenant/recipient/scope solely from the token record.
- Persist **`UNSUBSCRIBED`** preference and audit atomically in a transaction.
- Handle repeated POSTs without altering outcomes or writing endless audit rows.
- Handle invalid/expired tokens cleanly per API contract.
- Keep tokens out of error logs, URL tracing, and analytics.

**Never require session cookies or logins** on the one-click endpoint intended for mailbox providers. The scoped token is the capability; protect it with entropy, HTTPS, validation, throttling, and audits.

### Spring Security and CSRF

With default Spring Security CSRF protection, POSTs lacking a CSRF token are rejected. Configure a **narrow CSRF exception limited strictly to the one-click endpoint**, rather than disabling CSRF application-wide. This is sound only because the endpoint **does not authenticate via browser cookies/sessions**, relies on no user session, and authorizes solely via the scoped URL token.

Ordinary logged-in/cookie-based preference endpoints must retain full CSRF protection and authorization.

## 17. Attaching unsubscribe headers when building MimeMessage

Spring Mail example:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MarketingMailComposer {

    private final JavaMailSender sender;

    public MarketingMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public MimeMessage compose(
            String approvedFrom,
            String recipient,
            String subject,
            String htmlBody,
            String oneClickUrl,
            String mailtoAddress
    ) throws Exception {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, "UTF-8"
        );

        helper.setFrom(approvedFrom);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(htmlBody, true);

        message.setHeader(
                "List-Unsubscribe",
                "<" + oneClickUrl + ">, <mailto:"
                        + mailtoAddress + ">"
        );
        message.setHeader(
                "List-Unsubscribe-Post",
                "List-Unsubscribe=One-Click"
        );

        return message;
    }
}
~~~

**`approvedFrom`**, **`oneClickUrl`**, and **`mailtoAddress`** must come from **verified sender/list profiles**, never arbitrary user strings injected into headers. URIs must use HTTPS with properly encoded tokens and allowlisted domains.

At send time, the system must also:

- Re-check consent/unsubscribes before SMTP.
- Select the right tenant SMTP profile and `MAIL FROM`.
- Include an unsubscribe link in the body footer when required by message type.
- Ensure the ESP/gateway **DKIM-signs** required headers without stripping or altering them afterward.
- Verify mail providers preserve headers and one-click UI works on real test messages.

**`MimeMessageHelper` neither generates `List-Unsubscribe`, manages preferences, nor guarantees providers render one-click UIs.**

## 18. In-body unsubscribe links and preference centers

A marketing email might contain:

~~~text
You received this email because you subscribed to product updates.

Unsubscribe from this newsletter: https://brand.example/preferences/TOKEN
Manage notification preferences: https://brand.example/preferences/TOKEN
~~~

A preference center can let users:

1. Unsubscribe from the current list.
2. Unsubscribe from all marketing.
3. Choose topics of interest.
4. Lower digest frequency.
5. View saved choices and effective timestamps.

Avoid dark patterns like hiding links, forcing users to re-type their known email address, or making them click through unnecessary pages to opt out.

GET pages should only render state/forms; mutations should use authenticated POST/PUT actions. **Preference pages may include a user confirmation step**, whereas the **one-click HTTP POST** endpoint for mail providers must never depend on that confirmation step.

## 19. Unsubscribing via mailto

Some systems support:

~~~text
List-Unsubscribe:
 <mailto:unsubscribe+opaque-token@lists.brand.example>
~~~

When an email arrives at that address, the inbound service:

1. Polls the designated mailbox/route.
2. Extracts the **opaque token** from the destination address using a strict parser.
3. Maps the token to recipient/list/scope.
4. Records the unsubscribe idempotently.
5. Sends a confirmation reply only if policy requires, guarding against mail loops.

**Never trust the `From` header of an unsubscribe email as sole proof**, since `From` can be spoofed. Use narrowly scoped tokens with abuse protection and appropriate verification per action.

Never treat an arbitrary reply with Subject "unsubscribe" as authorization to opt out all lists for another address without verification.

## 20. Preference center webhooks and email events must share one policy

Users can opt out through several channels:

~~~text
Email one-click POST ----------+
Preference center ------------+---> SubscriptionPolicyService
Inbound mailto unsubscribe ---+             |
Customer support verified ----+             v
                                Durable preference + audit
                                              |
                                              v
                                  Eligibility before send
~~~

Never let **HTTP endpoints** write to one table, **support CRMs** write to another, and **schedulers** read only one of them.

All sources must normalize into a single send-eligibility decision capturing:

- Scope.
- Effective timestamp.
- Source and trust level.
- Idempotency key.
- Actor or automation source.
- Audit trail and policy version.

If preferences exist across multiple systems, define the **source of truth**, synchronization mechanism, and conflict rules. Never assume worker caches reflect an unsubscribe instantaneously.

## 21. Receiving bounces via ESP webhooks

Many production systems consume ESP webhooks for:

~~~text
SMTP accepted
      |
      v
ESP delivery pipeline
      |
      +-- delivered
      +-- deferred
      +-- bounced
      +-- complained
      |
      v
Application webhook endpoint
      |
      v
Verify -> dedup -> persist -> normalize -> policy
~~~

A pipeline should:

1. Verify the **webhook signature or auth scheme** per provider contract.
2. Verify timestamps/replay windows when supported.
3. Cap request sizes and validate schemas/field types.
4. Trust **`providerEventId`** and **message mappings** only after verification.
5. Store raw/normalized events safely per retention rules.
6. Deduplicate via stable event IDs or designed fallback keys.
7. Correlate provider message IDs and recipients to sent notification attempts.
8. Apply state transitions and suppression policies accordingly.
9. Return consistent HTTP responses so providers retry when needed.

Never accept a header like:

~~~text
X-Provider-Event: hard_bounce
~~~

as trustworthy proof if external Internet callers can forge it.

### Verifying signatures over raw HTTP bodies

When providers compute HMAC over **raw request bytes**, preserve the raw body intact for verification. Parsing JSON and re-serializing before hashing can change whitespace or key ordering and break signatures. Verification and secret rotation must follow provider contracts.

If webhook verification fails, never use its payload to mutate suppressions or unsubscribes.

## 22. Receiving DSNs via a bounce mailbox

When an ESP lacks webhooks or reconciliation is needed, read **Delivery Status Notifications** from a dedicated bounce mailbox via **IMAP/POP3**.

A standard DSN has the structure:

~~~text
multipart/report; report-type=delivery-status
  |
  +-- text/plain
  |
  +-- message/delivery-status
  |
  +-- message/rfc822-headers (optional)
~~~

The `delivery-status` part may include:

~~~text
Final-Recipient: rfc822; customer@example.net
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
~~~

Never parse DSNs merely by checking:

~~~text
Subject contains "Undelivered Mail"
~~~

because Subjects are easily spoofed. Inspect the **MIME report structure**, DSN fields, and correlation to outbound notifications. Many DSNs omit fields or vary across mail servers.

A pipeline:

~~~text
Bounce mailbox
     |
     v
IMAP/POP3 receiver
     |
     v
MIME/DSN parser with size limits
     |
     v
Correlation token / recipient matching
     |
     v
Event dedup + durable store
     |
     v
Bounce classification + suppression policy
~~~

Do not treat every email arriving in the bounce mailbox as a hard bounce. Bounce addresses can receive spam or backscatter; emails resembling DSNs that match no outbound notification should be quarantined/ignored per policy.

### VERP and correlation

**Variable Envelope Return Path (VERP)** encodes an identifier in the `MAIL FROM` address:

~~~text
bounce+tenantA.N100.R12@returns.brand.example
~~~

When a DSN returns, the system maps the token back to **notification-recipient**. Tokens should be opaque/signed to resist spoofing and contain no readable PII. Never accept a DSN solely because it contains a token-like string; combine source, structure, and mapping checks.

When using an ESP, the provider may manage `MAIL FROM`/VERP itself, so do not assume the application controls `Return-Path` arbitrarily on every message.

## 23. Idempotency when webhooks or DSNs redeliver

A provider may resend the same webhook if:

~~~text
T0   Provider POSTs event E100
T1   App verifies and commits DB
T2   HTTP response times out on network
T3   Provider retries POST event E100
~~~

If every HTTP request increments bounce counts or inserts a new suppression, metrics double-count. Distinguish:

- **Webhook request count:** every incoming HTTP request.
- **Unique verified provider events:** only distinct valid event IDs.
- **Unique bounced notification-recipients:** notification-recipients determined bounced per policy.
- **Active suppressed recipients:** recipients currently blocked within scope.

These metrics are not interchangeable.

Unique key example:

~~~sql
CREATE TABLE mail_provider_event (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id          VARCHAR(100) NOT NULL,
    provider_account_id  VARCHAR(120) NOT NULL,
    provider_event_id    VARCHAR(300) NOT NULL,
    provider_message_ref VARCHAR(500),
    recipient_key        VARCHAR(240),
    event_type           VARCHAR(80) NOT NULL,
    event_at             TIMESTAMPTZ,
    ingested_at          TIMESTAMPTZ NOT NULL,
    normalized_category  VARCHAR(100),
    raw_event_ref        TEXT,
    UNIQUE (
        provider_id, provider_account_id, provider_event_id
    )
);
~~~

Not every provider supplies durable event IDs. When missing, design a **dedup fingerprint** per provider event contract with bounded windows and false-positive/negative review. Never treat two emails sharing a timestamp or diagnostic string as the same event.

### Handling duplicate events

On unique constraint conflict during insert:

1. Confirm it is a previously ingested event.
2. Do not re-apply policy side effects if already committed.
3. Return an HTTP response that stops endless provider retries.
4. If the prior run persisted the event yet crashed before applying policy, a worker reading the **durable event inbox** finishes processing instead of relying on webhook retries.

## 24. Persisting events and updating policies in proper transactions

A safe pattern:

~~~text
Verified webhook
     |
     v
BEGIN DB TRANSACTION
  INSERT provider event (unique ID)
  INSERT processing_work_item
COMMIT
     |
     v
Policy worker
     |
     v
BEGIN DB TRANSACTION
  Check event not applied
  Update recipient delivery state
  Apply suppression if warranted
  Mark event applied
COMMIT
~~~

This approach enables:

- Fast webhook responses avoiding provider timeouts.
- Application-level retries after process crashes.
- Classifying provider errors outside HTTP request paths.
- Auditing when suppression policies change.

Even when webhook ingestion and business updates share a database transaction, never call external APIs inside long transactions. If events live in one DB and suppressions in another service, use **idempotent commands + reconciliation** rather than assuming cross-service ACID.

**Never return success before critical events are durably accepted**, unless provider contracts and queue architectures guarantee persistence beforehand.

## 25. Data model separating suppressions from preferences

To avoid mixing "what the recipient wants" with "whether the recipient can receive mail", separate two sources:

~~~text
mail_subscription_preference
    tenant, recipient, scope, subscribed/unsubscribed

mail_suppression
    tenant, recipient, scope, reason,
    active, started_at, expires_at
~~~

Example schema:

~~~sql
CREATE TABLE mail_suppression (
    tenant_id        VARCHAR(120) NOT NULL,
    recipient_key    VARCHAR(240) NOT NULL,
    scope_type       VARCHAR(30) NOT NULL,
    scope_key        VARCHAR(160) NOT NULL,
    reason           VARCHAR(60) NOT NULL,
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    started_at       TIMESTAMPTZ NOT NULL,
    expires_at       TIMESTAMPTZ,
    source_event_id  BIGINT,
    version          BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (
        tenant_id,
        recipient_key,
        scope_type,
        scope_key,
        reason
    )
);
~~~

Example:

~~~text
Tenant A / recipient R12:

Preference:
  MARKETING -> UNSUBSCRIBED

Suppression:
  RECIPIENT / HARD_BOUNCE -> active
  MARKETING / SPAM_COMPLAINT -> active
~~~

A recipient can be simultaneously unsubscribed and suppressed. Resolving a hard bounce with a new email address must never erase a prior marketing unsubscribe.

### Scope policies

**`scope_type`** can be `RECIPIENT`, `LIST`, `STREAM`, `BRAND`, `PROVIDER_ACCOUNT`, or `TENANT` depending on your model. Govern scopes explicitly:

- Invalid-recipient suppressions may apply broadly across all streams using that address.
- Newsletter unsubscribes usually affect only the list or marketing stream.
- Spam complaints may require broader scopes depending on ESP policies.
- Provider account-level suppressions can impact multiple tenants sharing an account.

Spring Mail defines no default rules for these scopes; they must be tested domain policies.

## 26. A summary status table alone is insufficient for audits

If you only store:

~~~text
recipient R12 -> SUPPRESSED
~~~

it becomes hard to answer:

- Why was it suppressed?
- Bounce, complaint, or admin action?
- Was it merely a single soft bounce?
- Which provider and attempt produced the event?
- Is the suppression time-bound or permanent until verification?
- Had the user already unsubscribed earlier?
- Who is authorized to clear the status?

Retain:

1. **Immutable event ledger**: inbound/outbound events and evidence.
2. **Current effective state**: fast lookup state for workers before sending.
3. **Policy version**: version of the rule deciding state transitions.
4. **Actor/source**: provider webhook, consent endpoint, support action.
5. **Audit transitions**: before/after values and reasons.

This is why a suppression service is more than a `HashSet` of email addresses.

## 27. Attaching events accurately to notification-recipient pairs

A message may have multiple recipients:

~~~text
MimeMessage M100:
  To: a@example.net
  Cc: b@example.net
  Bcc: c@example.net
~~~

Providers can report a bounce solely for **`b@example.net`**, while `a` and `c` were accepted.

Avoid:

~~~text
if any recipient bounced:
    mark entire message as undeliverable
    suppress all recipients
~~~

A better model:

~~~text
Notification N100
    |
    +-- Recipient R1 -> DELIVERED
    +-- Recipient R2 -> BOUNCED
    +-- Recipient R3 -> UNKNOWN/DEFERRED
~~~

Provider events must correlate:

- Provider account and message ID.
- Matching notification and attempt.
- Normalized recipient key.
- Tenant/stream/list under which the message was sent.
- Event type and timestamp.

When uncertain correlation occurs, **quarantine the event** instead of updating suppression on unverified payload addresses.

### Bcc still has its own delivery outcome

Bcc addresses are omitted from headers seen by other recipients, yet still pass through SMTP **`RCPT TO`**. Deliverability tracking must store envelope recipients securely without leaking Bcc addresses to other recipients.

## 28. Events can arrive out of order

Example:

~~~text
09:00  ESP accepts message
09:01  "deferred" event occurs
09:02  "delivered" event occurs
09:03  "delivered" webhook reaches application
09:05  "deferred" webhook reaches application (delayed)
~~~

If the application simply runs:

~~~text
delivery_status = newest_HTTP_request.eventType
~~~

then after 09:05 the status regresses from `DELIVERED` back to `DEFERRED` even though deferral happened earlier.

Solutions:

- Store **provider event time**, ingestion time, and event ID.
- Define **state transition rules** per provider/event type.
- Never rely purely on HTTP arrival order.
- Never let an older transient event overwrite a terminal outcome.
- Flag conflicting states for reconciliation when providers report anomalies.

Crucially, **a delivery status** and **a suppression decision** are two distinct things. A message can be marked delivered and later draw a spam complaint; blocking future marketing does not require erasing the fact that the earlier message was reported delivered.

## 29. Per-recipient state machine

Suggested model:

~~~text
SCHEDULED
     |
     v
SUBMITTED
     |
     +-- DEFERRED -> still pending provider outcome
     |
     +-- DELIVERED
     |
     +-- BOUNCED
     |
     +-- DELIVERY_UNKNOWN

Independent contact policy:
     |
     +-- CONTACT_OK
     +-- TEMPORARY_HOLD
     +-- SUPPRESSED_HARD_BOUNCE
     +-- SUPPRESSED_COMPLAINT
     +-- UNSUBSCRIBED_LIST
     +-- UNSUBSCRIBED_MARKETING
~~~

For a provider, a `DELIVERY` event can follow `DEFERRED`; however, a **spam complaint** is not simply a mutually exclusive delivery branch of that message.

Never design a single enum:

~~~text
SENT | BOUNCED | UNSUBSCRIBED
~~~

to represent both message history and user preference. A `DELIVERED` email can later trigger an unsubscribe, and both facts must coexist.

## 30. Soft bounces: temporary holds instead of permanent deletion

Example:

~~~text
Recipient R12:
  2026-11-01 -> temporary mailbox full
  2026-11-03 -> temporary mailbox full
  2026-11-04 -> delivered
~~~

A single soft bounce does not prove an address is dead. Use a policy:

1. Record soft bounces by recipient/provider and time window.
2. Let the ESP retry on its schedule or throttle retries in the app without stacking both.
3. If crossing a defined threshold, set **`TEMPORARY_HOLD`**.
4. Set **`hold_until`** rather than permanent suppression.
5. After hold expiry, allow limited probe sends when consent and business intent remain valid.
6. Upon successful delivery, re-evaluate deliverability state.

Illustrative policy example:

~~~text
3 temporary delivery failures in 7 days
  -> HOLD 24 hours

After HOLD:
  -> Permit controlled retry for eligible emails

No further soft bounces:
  -> Lift hold per rule
~~~

Numbers are illustrative, not universal standards. Thresholds depend on ESP behavior, streams, recipient domains, and real list quality.

### Never retry a message that has lost its value

An OTP expiring in 5 minutes should not go out after a 24-hour temporary hold. **Provider retry policies** and **business deadlines** must align so stale content is never sent.

## 31. Hard bounces: verifying and recovering addresses

A verified hard-bounced recipient, e.g., nonexistent mailbox, typically stops sends to **the current address**.

Workflow:

~~~text
Verified invalid-recipient bounce
      |
      v
Set suppression for recipient address
      |
      v
Cancel/defer applicable pending messages
      |
      v
Notify account owner through approved channel
      |
      v
User updates/validates contact address
      |
      v
Create a new verified contact identity
      |
      v
Re-evaluate consent/eligibility
~~~

Never auto-lift hard suppressions merely after N days without evidence the address was fixed or re-verified.

If a user switches from **`old@example.net`** to **`new@example.net`**, version contact identities properly rather than pretending the old address never bounced; history stays valuable for audits.

### When 5xx codes are not trustworthy enough

If multiple domains simultaneously report policy `5.7.1` right after misconfiguring DKIM, suppressing thousands of recipients would be a mistake. Distinguish **recipient-invalid** from **sender-policy** before applying bulk hard suppressions.

## 32. Spam complaints are a distinct signal

A recipient can mark an email as spam, and the provider emits a complaint event via a feedback loop or webhook.

You should:

- Verify the complaint event comes from a trusted source.
- Link it to the right recipient and message/list/brand.
- Stop sending marketing within policy scope.
- Record **`SPAM_COMPLAINT`** separately from **`HARD_BOUNCE`** and **`UNSUBSCRIBED`**.
- Audit list sources, consent, and send frequency.
- Never send another marketing email to "confirm the complaint" if that violates user choice.

Not every spam report in a feedback loop maps cleanly to a recipient, as some providers redact identifying info. Maintain a policy for **aggregated complaint signals** rather than inventing a recipient when data is redacted.

### Why complaints do not equal bounces

The email was delivered, the user saw it, and marked it spam. The address still accepts mail. Suppression stems from **recipient objection / anti-abuse policy**, not technical mailbox failure.

## 33. Normalizing email addresses without merging distinct recipients

A policy must identify recipients consistently across:

- Outbound SMTP envelopes.
- Provider webhooks.
- DSN `Final-Recipient`.
- Unsubscribe tokens.
- Subscription databases.
- CRM/contact records.

Yet **email address normalization** has traps:

- The **domain** part is case-insensitive in DNS; canonicalize domains per rules and IDN standards where appropriate.
- The **local-part** cannot safely be lowercased universally across all mail servers per protocol.
- Never blindly strip dots or **`+tag`** suffixes just because some providers alias them; other domains treat them as distinct mailboxes.
- Never use display names to identify contacts.
- Unicode/IDN addresses require proper libraries and `SMTPUTF8` support when providers allow it.
- Users change addresses, so contact identities and address versions should not collapse into one history-less string.

Example:

~~~text
Contact ID: C100
  Address version 1: user.old@example.net
  Address version 2: user.new@example.net

Suppression:
  Address version 1 -> HARD_BOUNCE

Preference:
  Marketing topic -> UNSUBSCRIBED
~~~

When a user changes addresses, a hard bounce on the old address need not block the new one. However, **contact-level marketing unsubscribes** may still apply depending on recorded consent scope.

A sound model separates:

1. **Contact/person key**.
2. **Deliverable address identity/version**.
3. **Subscription preference scope**.
4. **Suppression reason scope**.

## 34. Precedence order combining subscription, bounce, and complaint

Suppose recipient R12 has:

~~~text
Subscription:
  LIST weekly-newsletter = SUBSCRIBED
  STREAM MARKETING       = UNSUBSCRIBED

Deliverability:
  ADDRESS = TEMPORARY_HOLD until tomorrow

Complaint:
  LIST weekly-newsletter = SUPPRESSED_COMPLAINT
~~~

When sending the weekly newsletter, the outcome must be **DENY**, despite `LIST=SUBSCRIBED`. The broader `STREAM MARKETING` is unsubscribed, and a complaint suppression also applies.

Conceptual formula:

~~~text
allow =
    senderAuthorized
    AND messageStillRelevant
    AND consentPolicyAllows(tenant, recipient, stream, list)
    AND NOT applicableUnsubscribe
    AND NOT applicableComplaint
    AND NOT applicableHardBounce
    AND NOT applicableTemporaryHold
    AND recipientAddressUsable
    AND scheduleDeadlineAllows
~~~

This is a conceptual expression. A **legitimate mandatory email** may not rely on marketing opt-in, yet still must pass deliverability, policy, sender authorization, and relevance checks. Never exempt a stream from every gate just because its enum says `TRANSACTIONAL`.

### DENY decisions should carry a reason

Example:

~~~text
DENY_UNSUBSCRIBED_MARKETING
DENY_LIST_UNSUBSCRIBED
DENY_SPAM_COMPLAINT
DENY_HARD_BOUNCE
DEFER_TEMPORARY_BOUNCE_HOLD
DEFER_PROVIDER_THROTTLE
DENY_BUSINESS_OBSOLETE
DENY_EXPIRED
ALLOW_SEND
~~~

Reasons must belong to a bounded enum. Never use raw exception text as policy outcomes, as it may expose PII and break aggregation.

## 35. Spring send-decision service example

An abstraction:

~~~java
public record SendRequest(
        String tenantId,
        String recipientKey,
        String notificationType,
        String stream,
        String listId
) {
}

public enum DecisionCode {
    ALLOW,
    UNSUBSCRIBED,
    COMPLAINT_SUPPRESSED,
    HARD_BOUNCE_SUPPRESSED,
    TEMPORARY_HOLD,
    NOT_AUTHORIZED,
    NOT_ELIGIBLE
}

public record SendDecision(
        boolean allowed,
        DecisionCode code
) {
    public static SendDecision allow() {
        return new SendDecision(true, DecisionCode.ALLOW);
    }

    public static SendDecision deny(DecisionCode code) {
        return new SendDecision(false, code);
    }
}
~~~

Illustrative policy service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class RecipientEligibilityService {

    private final SenderAuthorization senderAuthorization;
    private final SubscriptionRepository subscriptions;
    private final SuppressionRepository suppressions;
    private final NotificationBusinessPolicy businessPolicy;

    public RecipientEligibilityService(
            SenderAuthorization senderAuthorization,
            SubscriptionRepository subscriptions,
            SuppressionRepository suppressions,
            NotificationBusinessPolicy businessPolicy
    ) {
        this.senderAuthorization = senderAuthorization;
        this.subscriptions = subscriptions;
        this.suppressions = suppressions;
        this.businessPolicy = businessPolicy;
    }

    public SendDecision evaluate(SendRequest request) {

        if (!senderAuthorization.maySend(request)) {
            return SendDecision.deny(DecisionCode.NOT_AUTHORIZED);
        }

        if (!businessPolicy.isRelevant(request)) {
            return SendDecision.deny(DecisionCode.NOT_ELIGIBLE);
        }

        if (subscriptions.isUnsubscribedFor(request)) {
            return SendDecision.deny(DecisionCode.UNSUBSCRIBED);
        }

        if (suppressions.hasSpamComplaint(request)) {
            return SendDecision.deny(
                    DecisionCode.COMPLAINT_SUPPRESSED
            );
        }

        if (suppressions.hasHardBounce(request)) {
            return SendDecision.deny(
                    DecisionCode.HARD_BOUNCE_SUPPRESSED
            );
        }

        if (suppressions.hasTemporaryHold(request)) {
            return SendDecision.deny(
                    DecisionCode.TEMPORARY_HOLD
            );
        }

        return SendDecision.allow();
    }
}
~~~

**`SenderAuthorization`, `SubscriptionRepository`, `SuppressionRepository`, and `NotificationBusinessPolicy`** are application-defined interfaces. This snippet illustrates a decision pipeline and omits business deadlines/quotas/leases, caching, transactions, and concurrent updates.

In real implementations, distinguish **DENY** from **DEFER**:

- `UNSUBSCRIBED` or `HARD_BOUNCE` usually stops a new notification permanently.
- `TEMPORARY_HOLD` can reschedule if the message hasn't expired and policy permits.
- Sender authorization failures should never turn into infinite SMTP retries.

Do not return only a boolean and discard the reason; reasons are vital for audits and operations.

## 36. Scheduled outboxes must check suppression right before sending

Example:

~~~text
08:00  Campaign creates email N100 for recipient R12
09:00  N100 scheduled
08:45  R12 performs one-click unsubscribe
09:00  Worker picks up N100
~~~

If the worker reads a consent flag snapshotted in the payload at 08:00, N100 still goes out against the user's new choice.

The flow should be:

~~~text
Outbox PENDING
      |
      v
Claim by worker with token
      |
      v
Load current subscription + suppression
      |
      +-- UNSUBSCRIBED -> SKIPPED with reason
      +-- HARD_BOUNCE -> SKIPPED with reason
      +-- TEMP_HOLD   -> DEFER if deadline allows
      |
      v
Check tenant, business relevance, deadline
      |
      v
Transition to SENDING with claim token
      |
      v
JavaMailSender.send(...)
~~~

**An outbox entry can be validly created before an unsubscribe yet become ineligible by send time.** Eligibility must be evaluated at execution time, not solely when scheduled.

### Business skips differ from SMTP failures

A notification suppressed pre-send should not create a fake SMTP attempt:

~~~text
status = SKIPPED
reason = RECIPIENT_UNSUBSCRIBED
attempt_count = 0
~~~

Recording `FAILED`/`SMTP_ERROR` distorts transport-error alerts and tricks schedulers into bad retries.

## 37. Race between an unsubscribe and an in-flight SMTP send

A tricky case:

~~~text
09:00:00.000  Worker checks subscription: still opted in
09:00:00.050  Worker transitions state to SENDING
09:00:00.100  One-click POST writes UNSUBSCRIBED
09:00:00.120  Worker streams SMTP DATA
~~~

**There is no shared ACID transaction between the preference database and an SMTP server.** Thus a pre-send check cannot guarantee an unsubscribe stops an attempt already entering the send phase.

Mitigations:

- Send only after a **final eligibility check** close to the network call.
- Use snapshot versions or optimistic locking on policy and outbox state transitions.
- For strict streams, use an **admission coordinator** or short transaction locking required records before marking `SENDING`.
- When a one-click unsubscribe succeeds, halt/cancel related `PENDING`/`RETRY_WAIT` jobs.
- Never claim an already-`SUBMITTED` email can be recalled.
- Record **unsubscribe `effective_at`**, **`attempt_started_at`**, and **`submitted_at`** to investigate boundary races.

Even when the DB guards `SENDING`, **SMTP submission can proceed after the DB transaction commits**. Stronger guarantees require dispatch/provider-level coordination while acknowledging already-committed external side effects.

### Never hold preference locks across SMTP sends

Holding a subscription row lock for seconds during SMTP stalls unsubscribe requests or deadlocks other workflows. Keep transactions short with clear boundaries rather than trying to use long locks to guarantee an email hasn't left the system.

## 38. Conditionally updating notifications on policy decisions

Suppose a worker holds a claim on N100. If the recipient unsubscribed, update:

~~~sql
UPDATE email_outbox
SET
    status = 'SKIPPED',
    outcome_reason = 'RECIPIENT_UNSUBSCRIBED',
    finished_at = statement_timestamp(),
    claim_token = NULL,
    lease_until = NULL,
    version = version + 1
WHERE id = :notificationId
  AND status = 'CLAIMED'
  AND claim_token = :claimToken
RETURNING id;
~~~

The status/token guard prevents an old worker from overwriting a new worker's outcome or `SUBMITTED` state. If 0 rows return, re-read state and follow the state machine—never drop the `WHERE` clause to "force the write."

In multi-tenant systems, **`tenant_id`** should also appear in `WHERE` or be enforced via authorization and verified job ownership. Never accept a raw `notificationId` from a client without checking ownership.

For temporary holds:

~~~text
if hold_until < notification_expires_at:
    RETRY_WAIT until hold_until
else:
    SKIP_OR_EXPIRE under business policy
~~~

Do not poll and retry every tick while an active hold is still in effect.

## 39. Updating preferences idempotently in a single transaction

An unsubscribe service should run:

~~~text
BEGIN TRANSACTION
    |
    +-- Lookup token hash and validate scope
    |
    +-- Lock/update preference for tenant+recipient+scope
    |
    +-- If already UNSUBSCRIBED: no-op
    |
    +-- Else record UNSUBSCRIBED and audit
    |
    +-- Insert internal preference-changed event
    |
COMMIT
~~~

To stop concurrent POSTs from causing duplicate side effects, use:

- A unique key on **`tenant + recipient + scope`**.
- Atomic **`INSERT ... ON CONFLICT DO UPDATE`** or database-equivalent conditional update.
- An event ledger with idempotency keys.
- An outbox event to notify workers/caches durably.

Conceptual PostgreSQL example:

~~~sql
INSERT INTO mail_subscription_preference (
    tenant_id, recipient_key,
    scope_type, scope_key,
    decision, decision_at, decision_source, version
)
VALUES (
    :tenantId, :recipientKey,
    :scopeType, :scopeKey,
    'UNSUBSCRIBED',
    statement_timestamp(),
    'ONE_CLICK_POST',
    1
)
ON CONFLICT (
    tenant_id, recipient_key, scope_type, scope_key
)
DO UPDATE SET
    decision = 'UNSUBSCRIBED',
    decision_at = statement_timestamp(),
    decision_source = 'ONE_CLICK_POST',
    version = mail_subscription_preference.version + 1
WHERE mail_subscription_preference.decision
      IS DISTINCT FROM 'UNSUBSCRIBED'
RETURNING tenant_id, recipient_key;
~~~

If no row returns because the preference was already `UNSUBSCRIBED`, treat the HTTP POST as an idempotent success. If a row returns, the transaction can emit a single audit transition/outbox event per policy.

**Never use this query for resubscribes.** Re-subscribing requires a dedicated flow with fresh consent evidence, never arbitrary mutation by webhooks or unverified callers.

## 40. Syncing caches and ESP suppression lists

An architecture may have multiple layers:

~~~text
Preference DB (source of truth)
           |
           +-- Application cache
           |
           +-- Sending workers
           |
           +-- ESP provider suppression list
~~~

Challenges:

- DB shows `UNSUBSCRIBED` while cache still holds stale `SUBSCRIBED`.
- A provider suppression event arrives yet the app hasn't synced.
- App lifted a temporary hold while the provider retains an account-level suppression.
- ESP sync API fails, leaving app and provider out of sync.

Principles:

1. Define the **source of truth** for app-managed consent and suppression.
2. Use **policy-change events/outbox** to invalidate caches and sync providers.
3. Never let long cache TTLs defeat a freshly committed unsubscribe.
4. If the policy service is unreachable, **fail closed** for marketing rather than sending unchecked.
5. Run **reconciliation** jobs against provider suppression APIs when supported.
6. Never automatically remove provider-side suppressions without understanding why the provider set them.

**Syncing does not mean the provider will immediately allow sends**: an ESP may reject a recipient at account level even if the app allows it. Record such rejections in logs/metrics and handle per policy.

## 41. Resubscribing after unsubscribing

Someone who unsubscribed may change their mind. Yet **resubscribing must be a fresh decision backed by valid evidence**, never a side effect of:

- Syncing a CRM.
- An ESP reporting delivered.
- A soft-bounce hold expiring.
- An admin importing a recipient CSV.
- Changing an email address.
- A user merely opening the preferences page.

A workflow:

~~~text
Recipient previously UNSUBSCRIBED
        |
        v
User explicitly opts in again
        |
        v
Validate scope and identity
        |
        v
Optional double opt-in verification
        |
        v
Record new consent evidence and timestamp
        |
        v
Re-evaluate hard-bounce/complaint suppressions
        |
        v
Eligible for applicable future email
~~~

If the contact still carries **`SUPPRESSED_HARD_BOUNCE`**, flipping preference to `SUBSCRIBED` is insufficient to resume sending to an unproven address.

### Where is double opt-in helpful?

For newsletter signups or contact address changes, the app can:

1. Accept the signup request.
2. Send a verification email to the new address per allowed policy.
3. Have the recipient confirm via a secure token.
4. Persist timestamp, scope, and proof.
5. Only then allow sending the requested stream.

Verification flows must also resist abuse—never let attackers repeatedly trigger "verification" emails to someone who opted out. Enforce rate limits, TTLs, and dedicated data protections.

## 42. How are hard bounces cleared?

A recovery rule may require:

| State | Clearance condition |
|---|---|
| **TEMPORARY_HOLD** | Hold expired, positive signals, quotas/policies met |
| **HARD_BOUNCE** | User updates address or re-verifies deliverability |
| **SPAM_COMPLAINT** | Only via verified re-permission workflow compliant with ESP policy |
| **UNSUBSCRIBED** | User explicitly opts back in |
| **PROVIDER_ACCOUNT_SUPPRESSED** | Provider allows removal and root cause resolved |

Never run:

~~~sql
DELETE FROM mail_suppression
WHERE started_at < statement_timestamp() - INTERVAL '30 days';
~~~

to wipe every suppression after 30 days. Temporary holds, invalid mailboxes, and spam complaints carry different meanings and cannot share automatic expiry.

**Mark inactive with an audit record** instead of deleting history needed for investigations. When clearing one suppression, verify consent and any other active suppression scopes still pass.

## 43. Subscriptions and unsubscribes in multi-tenant systems

One email address may appear across multiple workspaces simultaneously:

~~~text
customer@example.net
   |
   +-- Tenant A: subscribed to product-news
   |
   +-- Tenant B: unsubscribed from marketing
   |
   +-- Tenant C: bounced due to provider policy
~~~

The system must never assume:

~~~text
Tenant B unsubscribe -> all tenants must unsubscribe
~~~

When products represent distinct brands/organizations, consent can be scoped per tenant or brand. However, if a shared **provider account** enforces account-level suppressions, one provider event can technically affect multiple tenants.

Define clearly:

1. **Consent owner:** tenant, brand, or platform?
2. **List owner:** who can add/remove recipients?
3. **Provider account scope:** are quotas/suppressions shared?
4. **Data locality:** which region stores events and PII?
5. **Authorization:** Tenant A users cannot read/edit Tenant B preferences.
6. **Auditing:** who may clear hard bounces or complaints?

Never take `tenantId` from unverified raw MIME headers or webhook fields to modify a tenant's suppressions. Derive tenant identity via trusted account/provider mappings and notification correlation.

## 44. Legal compliance and unsubscribe user experience

Obligations around consent, marketing, unsubscribes, processing deadlines, sender verification, and proof retention **vary by jurisdiction, mail type, and organizational role**.

Production policies should therefore:

- Classify **marketing** vs **transactional/service** mail by actual content/substance, not enum names.
- Provide clear opt-out mechanisms for applicable streams.
- Enforce unsubscribes promptly, prioritizing immediate updates on valid requests.
- Never demand unnecessary info or force login to finish one-click opt-outs.
- Keep minimal audits of choice scope and effective timestamps.
- Honor personal data rights and retention under valid policies.
- Check the latest mail provider requirements before deploying bulk sending.

**Do not treat examples in this guide as legal advice or specific statutory compliance deadlines.** Scopes, deadlines, and consent flows must be aligned with legal/compliance teams for your operating jurisdictions.

### Should an unsubscribe confirmation email be sent?

Not necessarily. Automatically firing "You have unsubscribed" emails or demanding click-to-confirm undermines one-click goals and adds unwanted traffic.

If confirmation is needed, the HTTP response and preference page are usually enough. Send a confirmation email only for valid business/policy reasons, guarding against mail loops and respecting suppressions/deliverability.

## 45. Deliverability: SPF, DKIM, DMARC, and bounce alignment

Some bounce spikes are not caused by recipients:

~~~text
Deploy new From configuration
        |
        v
Wrong or missing DKIM signing domain
        |
        v
Receiving domains reject by policy
        |
        v
Bounces/policy rejections spike across domains
~~~

To investigate:

- **SPF:** is the sender/provider authorized for the envelope domain in DNS?
- **DKIM:** does the message carry a valid signature matching the signing domain?
- **DMARC:** how does Header `From` align with authenticated domains?
- **MAIL FROM/Return-Path:** is the ESP using the configured, verified domain?
- **Reputation:** is one sending source or campaign driving complaints?
- **Sender profiles:** are tenants, accounts, and domains getting mixed across scaled workers?

Never "fix" a DMARC alignment failure by suppressing every recipient returning `5.7.x`. Fix the sending route/ESP config and assess blast radius.

### DKIM issues with one-click

If the app adds **`List-Unsubscribe-Post`** yet the ESP signs DKIM before an intermediary gateway modifies headers, the signature breaks. Inspect the **final message after provider processing**, not just the JVM's `MimeMessage` object.

Conversely, having valid DKIM does not replace ensuring the one-click endpoint processes POSTs safely and within scope.

## 46. Responsibility boundaries of Spring components

In a typical Spring application:

| Component | Responsibility |
|---|---|
| **JavaMailSender** | Create/send SMTP messages |
| **MimeMessageHelper** | Set From/To/Subject/body/attachments |
| **Jakarta Mail** | MIME/header/envelope transport depending on provider |
| **Spring MVC** | Handle one-click HTTP POSTs and preference requests |
| **Spring Security** | Protect admin/user APIs and narrowly expose public endpoints |
| **Spring JDBC/JPA** | Persist preferences, suppressions, events, outbox, and audits |
| **Spring Scheduling** | Poll outbox, retries, soft-hold expirations, reconciliation |
| **Spring Integration Mail** | Ingest DSNs/`mailto` unsubscribes from mailboxes if needed |
| **Micrometer/Actuator** | Record metrics and expose monitoring endpoints |

No method on **`JavaMailSender`** automatically:

- Exposes a one-click endpoint.
- Decides consent by tenant/list.
- Parses bounce webhooks.
- Converts hard bounces into suppression policies.
- Stops workers from sending scheduled emails post-unsubscribe.
- Updates provider suppression lists.
- Guarantees exactly-once when final SMTP replies drop.

So build **domain services** for preferences and deliverability, keeping Spring Mail at the **transport boundary**.

Deployment diagram:

~~~text
                   Recipient actions
            +-------------+-------------+
            |                           |
        Preference UI             One-click endpoint
            |                           |
            +-------------+-------------+
                          |
                          v
                 Subscription Service
                          |
                          v
              Preference/Audit database
                          |
                     Policy events
                          |
                          v
Outbox jobs ------> Eligibility gate -----> JavaMailSender
                          ^                       |
                          |                       v
                    Suppression DB           SMTP Provider
                          ^                       |
                          |                       v
                  Bounce policy worker <---- Webhook/DSN
~~~

## 47. Metrics: measure messages, recipients, and policy outcomes separately

Useful logical metrics:

| Metric | Meaning |
|---|---|
| **`mail_submitted_total`** | Unique notification-recipients accepted by SMTP/ESP |
| **`mail_attempts_total`** | Total attempts, including retries |
| **`mail_provider_bounce_events_total`** | Verified provider events reporting bounces |
| **`mail_bounced_recipients_total`** | Unique notification-recipients determined bounced |
| **`mail_deferred_events_total`** | Delivery deferral events |
| **`mail_complaints_total`** | Verified spam complaint events |
| **`mail_unsubscribe_requests_total`** | One-click/UI/`mailto` requests received |
| **`mail_unsubscribe_applied_total`** | Unique successful subscription transitions |
| **`mail_policy_blocked_total`** | Outbox attempts blocked by policy pre-SMTP |
| **`mail_suppression_active`** | Active suppression records by type/scope |
| **`mail_webhook_signature_failures_total`** | Webhooks rejected on verification |
| **`mail_webhook_unmatched_total`** | Events unable to correlate to notifications |
| **`mail_policy_sync_lag_seconds`** | Propagation lag from preference commit to sender/provider |
| **`mail_policy_reconciliation_failures_total`** | Errors reconciling state sync |

Never equate **webhook requests** with **unique bounces**: providers retry the same event multiple times.

Never treat **unsubscribe requests** as new unique opt-outs: users click multiple times or hold multiple subscription scopes.

### Defining the denominator

Example:

~~~text
In one day:
  1,000 unique submitted recipients
     20 confirmed bounced
     50 deferred events
     15 spam complaint events
     30 unsubscribe requests
~~~

These numbers may belong to different message cohorts because delivery feedback arrives late. Never blindly compute "20/1000 = 2% bounce rate today" if those 20 bounces came from yesterday's sends.

**Operational arrival rates** spot sudden spikes; **cohort ratios** anchored to submission time and maturity windows measure deliverability accurately.

## 48. Cohort bounce rates and late-arriving events

Example:

~~~text
Cohort A:
  2026-11-10: 5,000 recipient submissions accepted
  2026-11-11: 100 bounce reports arrive
  2026-11-12: 25 more bounce reports arrive
~~~

Dividing bounce events received on Nov 12 by submissions sent on Nov 12 can be wildly wrong.

A sound measurement:

~~~text
Mature-cohort bounce ratio =
    unique bounced recipient-submissions in cohort
    /
    unique accepted recipient-submissions in cohort
~~~

Define:

- **Cohort time** as `submitted_at`/`accepted_at`.
- **Observation window** long enough for provider feedback.
- **Outcomes** per recipient and attempt, ignoring webhook retries.
- **Hard/soft/policy bounces** separately when diagnosing causes.
- **`UNKNOWN`** and pending feedback reported as immature data.
- **Provider-specific delays** so fresh cohorts are not compared against settled ones.

### Arrival-event alerts are only proxies

An alert for "unique hard-bounce events spiked in 15 minutes" works for sudden anomalies, yet does not replace cohort ratios. If a campaign just sent a huge batch, absolute bounces rise due to volume, not worse list quality.

At low volumes, require a **minimum sample**. One bounce out of one submission is 100%, yet proves no widespread infrastructure outage.

## 49. Monitoring unsubscribes and user experience

A one-click endpoint can return HTTP 200 yet fail to stop new emails if:

- Preferences hit cache only without committing to the database.
- Workers read stale data.
- Tenant/list scopes were mapped wrongly.
- Provider sync APIs failed.
- A campaign pre-built a frozen recipient list snapshot.

Therefore monitor:

1. **POST success rate** of the one-click endpoint.
2. **Time-to-effective-unsubscribe** from preference commit until send eligibility observes the new state.
3. Count of **`mail_policy_blocked_total{reason=UNSUBSCRIBED}`**.
4. Notifications submitted **after unsubscribe `effective_at`** within blocked scopes, distinguishing in-flight races.
5. Invalid/expired one-click token rates.
6. `mailto` unsubscribe backlogs.
7. Provider suppression API sync rates.
8. Repeated requests / idempotency outcomes.

An important check:

~~~text
POST processed at 10:00
Preference committed at 10:00:01
Worker attempts marketing send at 10:01
~~~

When a worker starts an attempt after the preference took effect in a blocked scope, sending is a **policy enforcement defect** requiring investigation. If SMTP started before commit and accepted afterward, analyze it as a race rather than judging purely by `submitted_at`.

## 50. Alerting and distinguishing bounce spike causes

When bounces rise:

| Symptom | Initial hypothesis | Do not do immediately |
|---|---|---|
| `5.1.1` rises on a newly imported list | List quality / address validation | Hammer retries or raise SMTP timeouts |
| `5.7.1` rises across multiple domains | DKIM/DMARC/reputation/policy | Suppress all recipients |
| `4xx`/deferred rises on one domain | Receiving domain throttling | Hard-suppress everyone |
| Repeated bounces with same provider event ID | Webhook retry/dedup bug | Count each HTTP POST as a new bounce |
| Hard bounce spike after config rotation | Wrong sender profile or changed provider policy | Treat every email as invalid |
| Complaint rate climbs during campaign | Consent/content/frequency issue | Swap providers to dodge reputation policies |
| Webhook events suddenly drop to zero | Receiver/signature parser/backlog broken | Assume bounces dropped to zero |

Do not watch SMTP success rates alone; deliverability failures surface **after** SMTP accepted thousands of messages.

### Example alert groups

- **PolicyRejectSurge:** policy-group rejection rate rises across multiple receiving domains.
- **InvalidRecipientBounceHigh:** confirmed invalid recipients rise within a sufficient-volume cohort.
- **ComplaintRateHigh:** verified complaints rise relative to sent cohorts.
- **UnsubscribeEndpointErrors:** one-click POST 5xx/timeouts.
- **UnsubscribePropagationLag:** preferences committed yet workers/providers still out of sync.
- **BounceWebhookOutage:** provider emits events while ingestion fails or backlogs grow.
- **BounceCorrelationFailures:** verified events fail to map back to notifications.

Attach **runbooks** and explicit owners. Never use the failing SMTP provider as the **sole alerting channel** for its own outage.

## 51. Unit testing policies: one action, one clear decision

Because **policy** is the core of this problem, design test cases independent of SMTP:

| Input | Mail type | Expected outcome |
|---|---|---|
| Recipient unsubscribed `LIST=news` | Newsletter for same list | `DENY_UNSUBSCRIBED` |
| Recipient unsubscribed `LIST=news` | Different list with valid consent | Continue evaluating; do not block just for `news` |
| Recipient unsubscribed `STREAM=MARKETING` | Any marketing list in stream | `DENY_UNSUBSCRIBED` |
| Recipient unsubscribed marketing | Valid invoice | Evaluate under transactional policy; do not assume deny/allow |
| Hard bounce verified recipient invalid | Notification to same address | `DENY_HARD_BOUNCE` |
| Single soft bounce | Still-valid notification | Retry/defer per policy; do not hard suppress |
| Active temporary hold | Newsletter | `DEFER`, or `SKIP` if past deadline |
| Temporary hold expired, consent withdrawn | Newsletter | `DENY_UNSUBSCRIBED` |
| Verified complaint | Marketing in same scope | `DENY_COMPLAINT` |
| Bounce `5.7.1` from sender auth | Recipient address | Do not auto hard-suppress |
| Webhook event without valid signature | Any | No suppression changes |
| Duplicate `providerEventId` event | Any | Do not double-increment unique events/outcomes |
| User re-opts into list A | List A | Allow only if no broader block remains and deliverability is valid |
| Provider account suppression | All tenants sharing account | Operational policy reflects account-level block |
| Tenant A unsubscribes | Tenant B (separate scope) | Tenant B unchanged |
| Job scheduled before unsubscribe | Still-`PENDING` marketing job | `SKIPPED` before SMTP |
| Unsubscribe arrives after SMTP accepted | Old message | Keep accepted history; block future sends |
| Recipient changes address | Newly verified email | Evaluate contact preferences and suppressions for new address |

### Test precedence across simultaneous reasons

Suppose a recipient has:

~~~text
UNSUBSCRIBED_MARKETING = true
TEMPORARY_BOUNCE_HOLD = true
~~~

Policy may return primary reason **`UNSUBSCRIBED_MARKETING`**, while audits/state preserve the temporary hold so expiring the hold later does not accidentally allow sending.

Assert both the **decision code** and expected side effects (no attempt created, no unintended consent change)—not just boolean `false`.

## 52. Testing the one-click HTTP endpoint

Cases to verify:

1. Valid POST with Content-Type **`application/x-www-form-urlencoded`** and body **`List-Unsubscribe=One-Click`**.
2. First POST creates `UNSUBSCRIBED` preference for the exact tenant/list.
3. Second POST is **idempotent** without creating duplicate audit side effects.
4. GET on the same URL **never alters preferences**.
5. POST missing the marker or with wrong marker never applies silently.
6. Invalid/expired/revoked tokens behave per contract without leaking contact existence.
7. Tenant A's token cannot alter Tenant B's rows.
8. `LIST A` token cannot unsubscribe `LIST B` or the whole account.
9. Endpoint requires no browser session cookies, login, or CSRF token.
10. Endpoint can be rate-limited without disrupting legitimate recipients.
11. Link scanner issuing only GET leaves preferences untouched.
12. HTTPS domain, certificates, and redirect behavior comply with one-click requirements.
13. Tokens never appear in logs/traces or uncontrolled `Referrer` headers.
14. DKIM signature on final emails covers both required unsubscribe headers.

Conceptual example using **Spring MockMvc**:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OneClickUnsubscribeWebTest {

    @Autowired
    MockMvc mvc;

    @Test
    void postSupportsOneClickPayload() throws Exception {
        String token = createValidTestToken();

        mvc.perform(post("/mail/unsubscribe/{token}", token)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .content("List-Unsubscribe=One-Click"))
                .andExpect(status().isOk());

        // Additional assertion: exact scope is UNSUBSCRIBED;
        // messages in other scopes remain unaffected.
    }

    @Test
    void getMustNotUnsubscribe() throws Exception {
        String token = createValidTestToken();

        mvc.perform(get("/mail/unsubscribe/{token}", token))
                .andExpect(status().isMethodNotAllowed());

        // Additional assertion: preference in DB is unchanged.
    }

    private String createValidTestToken() {
        // Test fixture: generate token and row for test tenant/list.
        throw new UnsupportedOperationException("Fixture required");
    }
}
~~~

This is an **illustrative skeleton**: implement the fixture method in your test project and configure Spring Security to allow valid public POSTs strictly on this endpoint. Never use this test to claim DKIM is signed; verify that on real emails after ESP/gateway processing.

### Testing the endpoint alone is not enough

Asserting HTTP 200 without checking the database and worker misses bugs like:

~~~text
POST -> HTTP 200
DB -> UNSUBSCRIBED
Worker cache -> still SUBSCRIBED
SMTP -> still sends marketing
~~~

An integration test should schedule a job before the POST, run the unsubscribe, then execute the worker and assert **zero new SMTP attempts**.

## 53. Testing bounce and feedback ingestion

Use mocked webhook fixtures, DSN MIME fixtures, a test database, and an SMTP capture server.

### Webhook integration tests

| Case | Outcome |
|---|---|
| Valid signature, new event ID | Store event and apply matching policy |
| Invalid signature | Reject; no suppression changes |
| Same event ID sent twice | Single unique event/transition |
| Event from another provider account | Never mis-map tenant |
| Correlated `5.1.1` hard bounce | Suppress recipient per rules |
| Policy reject `5.7.1` | Investigate sender; no hard suppression until recipient-invalid proven |
| Soft bounce `4.2.2` | Record transient/hold; never auto-permanent |
| `Delivered` arrives before older `deferred` | Stale event does not reverse status |
| Complaint with recipient mapping | Apply complaint policy |
| Complaint lacking recipient identity | Record aggregate signal; never fabricate recipient |
| Missing provider event ID | Use contract/fingerprint fallback or quarantine |
| Webhook handler crashes after DB commit | Provider retry deduplicates; worker continues |
| New event while provider API down | Persist for retry; never drop |
| One message with multiple recipients | Update only the affected recipient |
| Unmatched event | Quarantine/reconcile; never suppress blindly |

### DSN integration tests

A DSN with:

~~~text
multipart/report; report-type=delivery-status
Final-Recipient: rfc822; user@example.net
Action: failed
Status: 5.1.1
~~~

must parse into a structured event and **correlate to a notification-recipient**. A normal email spoofing Subject "Mail delivery failed" must never trigger hard suppression.

Additional tests:

- DSNs with multiple `Final-Recipient` sections.
- DSNs missing `Message-ID` yet carrying a VERP token.
- Malformed or oversized DSN MIME payloads.
- Duplicate DSNs after IMAP reconnect.
- DSNs with mismatched account/tenant.
- DSNs containing sensitive original email excerpts never logged raw.

### SMTP tests

With a test SMTP server like GreenMail/Mailpit:

- When the recipient is unsubscribed, **`JavaMailSender.send(...)` is never called**.
- While a temporary hold is active, do not resend before the next allowed time.
- **`List-Unsubscribe`** and **`List-Unsubscribe-Post`** headers appear on eligible messages.
- Transactional messages never accidentally leak tokens or headers from another tenant.
- Shared `JavaMailSenderImpl` singletons are never mutated per account across threads, avoiding wrong `MAIL FROM`s.

These tests verify app-generated MIME only. Verify final DKIM, `Return-Path`, provider suppression behavior, and end-to-end webhooks via sandboxes/providers where possible.

## 54. Runbook when hard bounces spike abnormally

A **`HardBounceSurge`** alert must trigger root-cause investigation rather than blindly clearing or deleting batches of recipients.

### Step 1 — Verify whether numbers are real

- Are webhook requests rising because the provider is retrying the same events?
- Are unique provider event IDs and unique bounced notifications rising proportionally?
- Did schemas, parsers, or webhook sources change?
- Is delayed delivery feedback arriving from an older campaign?
- Are you looking at bounce arrival rate or mature-cohort bounce ratio?

### Step 2 — Identify scope

- One ESP account or all providers?
- One tenant/list/campaign or system-wide?
- One recipient domain or many domains?
- One sender domain/`MAIL FROM` profile or all profiles?
- Any recent SPF/DKIM/DMARC changes?
- Any newly imported lists or changed consent acquisition flows?

### Step 3 — Classify the error

| Rising category | Investigation focus |
|---|---|
| **`invalid_recipient`** | Data/address quality, validation, stale contacts |
| **`policy_rejection`** | SPF/DKIM/DMARC, reputation, content, sender policy |
| **`mailbox_full`** | Temporary holds, provider retries, recipient domain |
| **`provider_throttle`** | Rates/quotas/backpressure; never hard suppress |
| **`unknown/malformed`** | Parsers, correlation, webhook versions |
| **`complaint`** | Consent, frequency, content, list hygiene |

### Step 4 — Mitigate impact

- If many recipients are confirmed invalid, stop further sends to those addresses.
- If sender authentication failed, fix domain/account config or pause the broken sending route; never bulk hard-suppress recipients.
- If provider throttling, slow rates, back off, and protect critical streams.
- If complaints rise, audit the campaign and consider pausing marketing per procedure.
- If webhooks are spoofed or fail signatures, block policy updates from that source and check secrets/configs.
- Never switch providers to evade anti-spam policy blocks.

### Step 5 — Reconcile and recover

- Compare provider exports/APIs against the event ledger.
- Inspect notifications accepted prior to the bounce surge.
- Verify new suppressions have accurate scopes and recipients.
- If misclassified, use a **controlled, audited correction workflow** without erasing error trails.
- Watch subsequent cohorts post-fix to confirm deliverability recovers.

## 55. Runbook when a user says they unsubscribed yet still received email

Prioritize this scenario as it may indicate a policy defect and erodes user trust.

### Step 1 — Confirm the unsubscribe event

- Did the user use **one-click**, the preference page, or `mailto`?
- Did an HTTP POST reach the right endpoint?
- What status code did it return? Did CSRF/security filters block it?
- Which tenant, recipient, and list did the token resolve to?
- When did the preference commit?
- Did the user opt out of one list or all marketing?

Never ask users to paste full tokens into public support channels. Support staff should look up via authorized internal IDs without exposing bearer capabilities.

### Step 2 — Inspect the subsequent email

- Was it a **marketing email inside the canceled scope**?
- When was the notification created, claimed, SMTP-started, and accepted?
- Had the provider already accepted the email before opt-out and merely delivered it to the inbox later?
- Was it genuinely a transactional/security email?
- Was it sent by a different tenant or brand?

An email arriving in an inbox after unsubscribe does not automatically prove the app **started submission after `effective_at`**. It may have sat in the provider's delivery queue earlier. Still, reconcile carefully and explain honestly.

### Step 3 — Check policy propagation

~~~text
Unsubscribe endpoint
      |
      +-- DB decision?
      +-- Audit event?
      +-- Cache invalidation?
      +-- Outbox pending jobs?
      +-- Eligibility final gate?
      +-- ESP provider suppression sync?
~~~

If workers read stale caches, fix invalidation/consistency rather than merely tweaking TTLs or manually canceling one job.

### Step 4 — Stop further sends and remediate

1. Confirm `UNSUBSCRIBED` preference in the right scope is durably persisted.
2. Cancel matching `PENDING`/`RETRY_WAIT` notifications.
3. If needed, pause the offending campaign or route to stop further sends.
4. Never flip `SUBMITTED` to `CANCELLED` as if the sent mail was recalled.
5. Review provider history, application attempts, and exact timestamps.
6. Document the incident, root cause, and preventive controls.

### Step 5 — Verify the fix

Create a test notification in a staging/test environment under the same policy/scope. Confirm the **eligibility gate returns `DENY`**, **SMTP is not called**, and no side effects violate user choice.

Never send another marketing email "to test whether unsubscribe works" to the person who asked to opt out.

## 56. Common anti-patterns

| Mistake | Consequence | Better approach |
|---|---|---|
| Treating `JavaMailSender.send` success as delivered | Misses asynchronous bounces | Separate submission from delivery feedback |
| Treating every `MailSendException` as a hard bounce | Wrongly suppresses on DNS/TLS/auth errors | Distinguish transport vs delivery errors |
| Treating every SMTP 5xx as nonexistent mailbox | Deletes valid lists on sender policy errors | Parse enhanced codes and context |
| Treating every 4xx as hard bounce after one failure | Blocks temporarily full recipients | Retries, backoff, temporary holds |
| Using the bounce-receiving address as recipient suppression key | Blocks the wrong entity | Distinguish `MAIL FROM` vs `RCPT TO` |
| Setting `Return-Path` header to control envelope | DSNs misroute or providers rewrite it | Configure `MAIL FROM`/provider properly |
| Mutating singleton `JavaMailSenderImpl` per tenant | Leaks credentials and `MAIL FROM` | Immutable sender profiles and routing |
| Trusting bounce emails by Subject alone | Spoofed DSNs trigger suppressions | Structured DSN parsing and correlation |
| Trusting unsigned webhooks | Outsiders mutate recipient states | Raw-body signature verification |
| Counting every webhook request as a bounce | Inflates counts on provider retries | Unique event ledger |
| Using HTTP arrival time to overwrite delivery state | Stale deferred events regress state | Event timestamps and transition rules |
| One combined `SENT/BOUNCED/UNSUBSCRIBED` enum | Loses delivery and consent history | Separate message, contact, and preference states |
| Suppressing an entire domain on one `5.1.1` | Blocks valid recipients at that domain | Recipient-scoped evidence |
| Auto-purging suppressions after 30 days | Resends to invalid/complaint addresses | Reason-specific clearance policies |
| Resubscribing when ESP reports delivered | Ignores user opt-out | Explicit new consent |
| GET links executing unsubscribes | Link scanners trigger unwanted opt-outs | One-click HTTPS POST |
| One-click requiring login or confirmation | Breaks RFC 8058 one-click flows | Scoped tokens + idempotent POST |
| URLs containing plaintext email addresses | PII leaks and enumeration | Opaque tokens |
| Tokens able to opt out any tenant/list | Privilege escalation | Tokens scoped by recipient/list/tenant |
| Unsubscribe endpoint requiring session CSRF | Provider POSTs fail with 403 | Narrow CSRF exemption, token authorization |
| Disabling CSRF app-wide to fix one-click | Exposes user sessions | Exempt only the dedicated endpoint |
| Sending marketing from enqueue-time consent snapshots | Sends after opt-out | Final eligibility check right before SMTP |
| Caching preferences without invalidation | Workers act on stale data | Durable source + propagation |
| Skipping suppression whenever labeled `TRANSACTIONAL` | Keeps emailing invalid addresses | Distinct policy yet still check deliverability |
| Merging recipients across tenants by raw address | Cross-tenant suppression leaks | Explicit tenant/brand/provider scopes |
| Using raw emails as metric labels | PII leaks and high cardinality | Bounded dimensions and authorized traces |
| Using unsubscribe request count as unique opt-outs | Double-counts retries | Distinct transitions |
| Retrying whole batch when one recipient bounces | Resends to already-delivered recipients | Per-recipient outcomes/policies |
| Blindly clearing provider suppressions | Violates account policy, raises complaints | Reconcile and fix root causes |

## 57. Production readiness checklist

**Domain design**

1. Are **bouncing recipients** distinguished from **`MAIL FROM`/bounce mailboxes**?
2. Is there a taxonomy for hard, soft, policy, complaint, and unknown?
3. Are **subscription preferences** separated from **deliverability suppressions**?
4. Are scope policies defined per tenant, brand, stream, and list?
5. Are transactional and marketing emails classified by actual content?
6. Are separate clearance rules defined for soft holds, hard bounces, and complaints?

**Sending path**

7. Do workers re-check consent/suppression close to send time?
8. Are `PENDING` jobs blocked after unsubscribe or hard bounce?
9. Is idempotency enforced for notification-recipients and retries?
10. Are SMTP accepted, delivered, and `UNKNOWN` clearly separated?
11. Are per-recipient outcomes tracked for multi-recipient To/Cc/Bcc messages?
12. Are sender profiles, `From`, `MAIL FROM`, DKIM, and tenant ownership verified?

**One-click unsubscribe**

13. Do eligible emails include **`List-Unsubscribe`** and **`List-Unsubscribe-Post`**?
14. Does the HTTPS one-click endpoint accept form POSTs matching the contract?
15. Is GET strictly forbidden from mutating preferences?
16. Is the endpoint idempotent without requiring login or confirmation?
17. Do tokens have sufficient entropy, narrow scope, and zero PII?
18. Are token lifetimes and revocation policies set for older emails?
19. Is the CSRF exemption restricted solely to the token-based endpoint?
20. Are one-click headers DKIM-signed and preserved through the ESP?
21. Is there a clear opt-out/preference link in the email body per policy?

**Bounce/DSN feedback**

22. Do webhooks verify signatures over raw request bodies?
23. Are provider event IDs deduplicated and durably stored?
24. Are events mapped to provider accounts, tenants, and notification-recipients?
25. Are out-of-order events handled properly?
26. Does the DSN parser inspect `multipart/report` and status fields?
27. Are spoofed DSNs/backscatter and unmatched events quarantined?
28. Are provider taxonomies/raw codes retained for investigation?

**State and data**

29. Are preference transitions atomic and audited?
30. Do re-opt-ins require fresh proof without clearing unrelated suppressions?
31. Are caches and provider suppressions synced with lag monitoring?
32. Does reconciliation handle failed webhooks/APIs?
33. Are PII, tokens, raw DSNs, and retention bounded?
34. Is Tenant A prevented from reading/modifying Tenant B's data?

**Testing and operations**

35. Have repeated one-click POSTs, side-effect-free GETs, and wrong-scope tokens been tested?
36. Have invalid-signature, duplicate, and out-of-order webhooks been tested?
37. Have hard vs soft bounces and `5.7.x` sender policies been tested?
38. Have unsubscribes occurring after job enqueue been tested?
39. Have stale caches and provider sync failures been tested?
40. Are mature-cohort bounce ratios and unique unsubscribe transitions metered?
41. Are alerts active for policy-rejection surges and one-click endpoint outages?
42. Do runbooks exist for bounce spikes and complaint/unsubscribe incidents?

This checklist does not mean adding a few MIME headers automatically satisfies all deliverability or legal requirements. Provider configs, verification workflows, consent records, and applicable regulations must all be clarified before operating.

## 58. Takeaways

A **bounce and unsubscribe handling policy** in Spring Framework Mail must solve both **deliverability** and **recipient consent/choice** in parallel, never collapsing them into a sourceless `"sendAllowed"` flag.

Most important principles:

1. **Bounces and unsubscribes differ:** bounces concern delivery, unsubscribes concern preference, and spam complaints are a separate signal.
2. **`MAIL FROM`/`Return-Path` is not the bouncing recipient.** Configure bounce routing and correlation accurately.
3. **Hard bounces should suppress only with proof the recipient is unusable; soft bounces usually call for retries/holds; policy rejections call for sender investigation.**
4. **`List-Unsubscribe` and RFC 8058 one-click** require an HTTPS POST endpoint that actually executes opt-out, side-effect-free GETs, narrowly scoped tokens, and properly signed headers.
5. **Subscriptions and suppressions are independent data sources:** clearing a bounce does not resubscribe, and a fresh opt-in does not validate an invalid address.
6. **Webhooks/DSNs are external inputs:** verify, deduplicate, correlate by notification-recipient, and handle out-of-order arrivals.
7. **Outbox workers must check policy right before SMTP;** an email scheduled before an unsubscribe may still need to be `SKIPPED`.
8. **SMTP shares no rollback transaction with the database;** once an email is sent or `UNKNOWN`, never claim an unsubscribe/cancellation recalled the earlier message.
9. **Isolate tenants, tokens, and personal data**, while auditing transitions, syncing caches/providers, and observing effective policies.
10. **Measure the right units and investigate by cohort/reason**, rather than counting webhook retries or every SMTP 5xx as a hard bounce.

**The goal of a strong policy is not merely lowering bounce rates or adding an unsubscribe button—it is ensuring every decision to send or withhold mail rests on verified evidence, exact scope, right timing, and full explainability, testability, and safe recovery.**










