# Do Not Fail Over to Another Provider for Unsendable Errors in Spring Framework Mail

When a system uses multiple email providers (multi-provider), a common impulse is: "If provider A returns an error, immediately switch to provider B." That helps when **one sending path is experiencing a temporary disruption**, yet can cause severe harm when the email actually **cannot be sent validly**: wrong recipient address, missing message data, policy-violating content, unsubscribed recipient, expired verification email, or an account lacking permission to send from the chosen domain.

In those cases, sending the same message through provider B does not make the message valid. The system merely amplifies errors, increases cost and spam-flag risk, and sometimes attempts to bypass provider A's rejection rules. Therefore, a safe Spring Framework Mail architecture must place **stop conditions** ahead of failover:

> **Never switch to another provider solely because one send failed. Permit switching only when the root cause can genuinely be solved by changing routes, payload and sending permissions remain valid, and the prior submission outcome is clear enough to avoid uncontrolled duplicates.**

This lesson focuses on the **no-failover rule for unsendable errors**, how to classify failures, organize multiple `JavaMailSender` instances, control retries/outbox, test, and operate. The policies and Java types in the examples are **application-designed components**; Spring Mail does not ship a complete multi-provider failover engine out of the box.

## 1. Distinguishing Retry, Failover, Resend, and Provider-Owned Retry

Concepts easily confused:

| Action | Meaning | Example |
| --- | --- | --- |
| Same-provider retry | Retrying submission over the same route after backoff | A temporarily drops connection before DATA |
| Provider failover | Shifting an unsuccessful submission to an eligible route B | A has an infrastructure outage; B is authorized for this mail type |
| Business resend | Creating a new send request via an authorized user action | User clicks "resend invoice" |
| Dead-letter replay | Reviewing and reprocessing a halted record after fixing root cause | Fixing a broken template and replaying per workflow |
| Provider-owned retry | Relay already accepted and is trying to deliver to remote MX | A emits DEFERRED events and retries downstream itself |

**Never automatically fail over when provider A already accepted a message and is retrying downstream.** If the application resends through B, the recipient may receive multiple copies while two relays both attempt delivery. Downstream delivery failures must be tracked via provider events/DSNs, not turned into a brand-new SMTP submission.

### A Decision Diagram

~~~mermaid
flowchart TD
    A["Submit via provider A"] --> B{"Outcome?"}
    B -- "Clearly accepted" --> C["SUBMITTED: monitor delivery events"]
    B -- "Unclear after DATA" --> D["SUBMISSION_UNKNOWN: reconcile"]
    B -- "Clearly rejected" --> E{"Nature of failure?"}
    E -- "Invalid payload / recipient / consent / policy" --> F["Stop: no failover"]
    E -- "Fixable via configuration" --> G["Hold for fix; no blind failover"]
    E -- "A-specific outage, proven not accepted" --> H{"B eligible and has budget?"}
    H -- "No" --> I["Bounded retry/defer"]
    H -- "Yes" --> J["Controlled failover to B"]
~~~

This is a conceptual flow: to decide, the application also needs outbox state, expiry, allowed addresses, provider eligibility, attempt counts, and duplicate-prevention rules.

## 2. What Is an "Unsendable Error"?

An **unsendable (non-sendable)** error means the current message or send request **fails a mandatory precondition**. Changing SMTP relays usually cannot fix that condition.

Groups that must stop:

1. **Invalid recipient:** malformed syntax, confirmed nonexistent mailbox, suppressed recipient, or unauthorized receiver.
2. **Invalid message:** template fails to render, missing data, malformed MIME, disallowed attachment, or payload violating business constraints.
3. **Time validity:** expired OTP/reset link; campaign window ended.
4. **Authorization and sending policy:** missing required consent, recipient unsubscribed/complained, unauthorized From identity, or content rejected under a policy route B must also honor.
5. **Uncertain outcome:** provider A may have received the message while the client lost the final reply. This is not "unsendable" in the bad-data sense, yet **is ineligible for immediate safe failover**.

### Three Questions to Answer Before Failover

**A. Is the payload still valid?** Not just email syntax, but also TTL, suppression, template, From, email category, tenant scope, and recipient limits.

**B. Is the incident truly specific to route A?** A DNS error for A's hostname or a provider A outage can improve by using B. A nonexistent mailbox will not be fixed simply by switching vendors.

**C. Did A already receive the email?** If yes or uncertain, sending through B can create duplicates. Reconciliation takes precedence over instant retry.

## 3. Do Not Equate SMTP 4xx and 5xx with Failover Policy

SMTP has common reply-code groups:

- **4xx:** temporary failure for the current transaction/command.
- **5xx:** permanent rejection for the current request.

However, **5xx does not automatically mean "unsendable by every provider,"** just as **4xx does not automatically mean "safe to switch providers."**

| Scenario | Severity and context | Typically appropriate decision |
| --- | --- | --- |
| `550 5.1.1` at RCPT TO, mailbox does not exist | Recipient-level permanent per concrete evidence | Stop; do not try B for the same recipient |
| `553` from disallowed From address | Sender identity/configuration | Stop to fix authorization; do not try to "work around" via B |
| `554 5.7.x` content rejected by policy | Content/policy; investigate cause | Do not auto-failover to B to evade policy |
| `552` size exceeds limit | Payload/size; check per provider and product requirements | No blind switch; adjust MIME/attachments or pick an approved route |
| `535` SMTP AUTH failure | A's credential/account failure, not recipient | Pause A, fix secret; B only if approved route and sender rights hold |
| `421` A temporarily unavailable pre-submit | Possibly route A outage | Conditional failover or retry later |
| `451` remote service temporary error | May be temporary recipient/domain/provider | Classify by phase and provider context; no blind switch |
| `452` resource limitation | Possibly capacity/quota | Throttle/backoff; switch to B only if permitted |
| Connection refused before SMTP session | Evidenced infrastructure outage on A | B may fit when payload is valid |
| DNS lookup of SMTP host A fails | Route A unreachable | B may fit if B's name and TLS are valid |
| Socket timeout after DATA, no final reply | Uncertain outcome | No immediate failover; reconcile |
| `JavaMailSender.send()` succeeds | Relay A accepted submission | Do not auto-failover just because delivered is not seen yet |

Reply values and enhanced status codes depend on the SMTP provider, command position (AUTH, MAIL FROM, RCPT TO, DATA), and implementation. Inspect **SMTP phase, reply/enhanced status, response reason, and provider contract**; never write `if (code >= 500) { tryProviderB(); }`.

### Example Distinguishing 5xx Across Stages

~~~text
AUTH -> 535 5.7.8 Authentication credentials invalid
    -> A's credentials wrong; does not make the customer's address invalid.

MAIL FROM -> 553 5.7.1 Sender not permitted
    -> Identity / sending permission invalid on the current route.

RCPT TO -> 550 5.1.1 User unknown
    -> Specific recipient permanently rejected.

DATA -> 554 5.7.1 Message rejected due to policy
    -> Investigate content/reputation/policy; do not blindly "route around."
~~~

Some providers return the same `550` code for multiple causes. Reading the three digits `550` alone is therefore insufficient to apply permanent suppression. When evidence is unclear, hold in **NEEDS_REVIEW** or classify conservatively instead of labeling the recipient invalid.

## 4. Why Switching Providers Can Make Things Worse

### 4.1. Increasing Send Attempts Without Increasing Success

If the mailbox does not exist, both A and B waste authentication, SMTP connections, quotas, and retries on an undeliverable message.

### 4.2. Causing Duplicates

If A accepted yet the `delivered` event arrives late, sending via B without sufficient evidence produces two copies. That is especially dangerous for OTPs, reset links, auditable invoices, or security alerts.

### 4.3. Evading Provider Policies

If A rejected content due to consent, abuse, or content policy, pushing it through B to get acceptance can violate policies, sending reputation, or legal requirements. Provider failover must serve **legitimate availability**, never bypass safeguards.

### 4.4. Polluting Suppression/Feedback

Hard bounces and complaints from A are signals that may need recipient-level enforcement system-wide. If suppression is stored only inside adapter A, route B may keep mailing users who already complained.

### 4.5. Exponential Error Amplification

If each provider retries three times and two providers sit in a loop, one message can generate many SMTP calls unreflected in outbox attempt counts. Never nest failover inside retries without a **global attempt budget**.

## 5. Multi-Provider Architecture: One Dispatch Gate, Multiple Adapters

Instead of business services calling A, catching exceptions, and calling B, build a centralized **mail dispatch gateway** deciding routes by policy.

~~~mermaid
flowchart LR
    A["Order / User event"] --> B["Transactional outbox"]
    B --> C["Mail dispatcher"]
    C --> D["Validate payload + eligibility"]
    D --> E["Route / failover policy"]
    E --> F["Rate + concurrency budget"]
    F --> G["Provider A adapter"]
    F --> H["Provider B adapter"]
    G --> I["SMTP / API A"]
    H --> J["SMTP / API B"]
    G --> K["Result normalizer"]
    H --> K
    K --> L["Outbox state + events + metrics"]
~~~

Key components:

| Component | Responsibility |
| --- | --- |
| Notification/outbox | Durably persists sending intent and idempotency key |
| Payload validator | Checks recipient, content, expiry, consent, template |
| Provider registry | Approved routes, capabilities, quotas, From identities |
| Router | Selects initial route by region, category, policy |
| Transport adapter | Calls `JavaMailSender` or provider API |
| Failure normalizer | Normalizes exceptions/SMTP replies into internal errors |
| Failover policy | Decides STOP/HOLD/RETRY/FAILOVER/RECONCILE |
| Rate/concurrency gate | Protects total rate and per-provider resources |
| Event processor | Ingests bounce, deferred, complaint, and delivery statuses |
| Audit/metrics | Records route decisions and reasons without exposing secrets |

Crucially, **validators and suppression checks must run before every attempt**, including the first attempt, same-provider retries, failovers, and manual replays. An email valid at enqueue time may have expired or had its recipient unsubscribe by dispatch time.

## 6. A Single Status Is Not Enough

Multi-provider mail must distinguish submission from delivery and business states.

| Illustrative status | Meaning | Auto-failover? |
| --- | --- | --- |
| `PENDING` | Valid send request not yet submitted | Can select route |
| `PROCESSING` | Worker holds lease | Prevent other workers from claiming |
| `RETRY_PENDING` | Temporary error, scheduled | Only when due and permitted by policy |
| `HOLD_FOR_CORRECTION` | Invalid data/From/content | No |
| `FAILED_PERMANENT` | Unsendable per current evidence | No |
| `SUPPRESSED` | Blocked by consent/complaint | No |
| `EXPIRED` | Message/token lifetime elapsed | No |
| `SUBMITTED` | Relay/provider accepted submission | No; monitor delivery |
| `SUBMISSION_UNKNOWN` | A may have received it; client lacks final confirmation | No blind failover |
| `NEEDS_REVIEW` | Conflicting/insufficient evidence to decide | Wait for reconciliation or audited decision |

`SUBMITTED` does not mean inbox-delivered. Bounces or complaints can arrive after acceptance. Never reset `SUBMITTED` back to `PENDING` merely because one poll saw no `delivered` event.

## 7. Error Matrix: Cases That Must Never Blindly Fail Over to B

| Error group | Example evidence | Why B does not solve it | Action |
| --- | --- | --- | --- |
| Malformed email address | Parser/address validation failed | Same address is still invalid | Fix input data |
| Confirmed nonexistent mailbox | RCPT 550 5.1.1, trusted hard bounce | Destination mailbox does not exist | Suppress/prompt address update |
| Recipient unsubscribed | Preference store updated | Permission to receive was withdrawn | SUPPRESSED |
| Spam complaint | Verified feedback loop | Sending via B is still unwanted | Suppress marketing; investigate |
| Expired OTP | `expiresAt` in the past | Content is no longer useful | EXPIRED, require new code |
| Template render failure | Missing template/null data/invalid expression | B receives the same broken body | Fix template/model before replay |
| Malformed MIME | Invalid multipart, address, encoding | Cannot build valid message | FIX_CONTENT |
| Invalid attachment | File too large/missing/disallowed | Changing routes does not fix the file | Shrink size/handle per policy |
| Content blocked by policy | Provider returned abuse/content policy rejection | Rerouting may evade safeguards | Investigate/fix content |
| Invalid From identity | Missing send-as/verified sender rights | B needs its own permission; not auto-valid | Fix permissions or approved route |
| Tenant barred from B | Jurisdiction/contract/region | Failover violates constraints | Hold/retry A per policy |
| B lacks feature support | Attachment size, encoding, category | B cannot guarantee fidelity | Do not select B |
| A already accepted | Final SMTP 250 or provider accepted | No submission needs retrying | Monitor downstream |
| A outcome unknown | Lost reply after DATA | B may create duplicates | Reconcile first |

For policy or compliance failures, avoid naming flags `fallbackAllowsPolicyBypass`. Routing must never be used to bypass unsubscribes, complaints, suppressions, or security checks.

## 8. Permanent Request Errors Differ from Provider-Specific Config Errors

Not every 5xx reply proves a message is "unsendable everywhere." Distinguish **failure scope**:

### 8.1. Permanent at Recipient or Business Scope

- A mailbox confirmed nonexistent.
- Invalid address that cannot be normalized.
- Missing consent/unsubscribed.
- Attachment banned by product policy.
- Expired OTP or reset token.

**Result:** stop sending the current content; do not choose B. The user or business workflow must fix the request before creating a new notification.

### 8.2. Permanent at Provider A Account Configuration Scope

- Provider A's SMTP username/password is invalid.
- Sender identity not yet verified with A.
- An A configuration lost sending permission.
- Tenant A ran out of contract quota or account is locked.

These errors may affect only **route A**, yet do not automatically prove B is safe. You can:

1. Pause lane A and fix configuration/credentials.
2. Verify B is **approved** for the email category, sender identity, tenant, country, data-storage policy, and quota.
3. Consider B only if the error is unrelated to consent/content/recipient and A definitely did not accept.
4. Keep an audit record for the route switch reason.

Therefore the sensible policy is usually **HOLD_FOR_OPERATOR** for under-classified account/config errors, rather than default `FAILOVER`. For a pre-handled incident where B is an approved standby route, an operator or policy may permit a controlled route switch.

### 8.3. Temporary at Provider A Infrastructure Scope

- Endpoint A's DNS fails to resolve.
- TCP connection refused/timed out pre-submit.
- Confirmed outage on provider A.
- Evidenced throttling or overloaded queue on A.

These are scenarios where B can improve availability, though you must still check eligibility, budget, duplicate risk, and business conditions before sending.

### 8.4. Unclassified Errors

If the adapter returns only `MailSendException` without knowing the cause, do not infer "A failed so use B." Instead:

- Save the sanitized original cause/SMTP phase.
- Temporarily classify as `UNCLASSIFIED`.
- Defer or hold under conservative policy.
- Reconcile if A might have received the message.
- Improve transport instrumentation before enabling automatic failover.

**Unknown error** differs from **unknown outcome**. Unknown error only means the failure wasn't classified; unknown outcome means you do not know whether the SMTP relay received the message. Neither qualifies for blind failover, though investigation paths differ.

## 9. SMTP Stage Determines Failover Risk

~~~text
Application                 SMTP relay A
    |                           |
    | --- TCP connect --------> |
    | <------ 220 -------------- |
    | --- EHLO / TLS / AUTH ---> |
    | --- MAIL FROM ----------> |
    | --- RCPT TO ----------->  |
    | --- DATA -------------->  |
    | <------ 354 ------------  |
    | --- headers/body -------> |
    | --- CRLF . CRLF --------> |
    |                           |
    | <------ final reply ----- |
~~~

### Before the Body Is Submitted

If connecting failed or the server rejected AUTH before DATA, this attempt could not have submitted the body to A. The concern then is **error classification and eligibility**, not duplicates from this attempt.

However, if the notification has **another prior attempt** accepted by A or marked `SUBMISSION_UNKNOWN`, still check the full history—never look only at the latest attempt.

### After A Returns Final Success

If the client received final SMTP 250 after DATA, A took protocol responsibility for processing the message. **Do not switch to B** simply because no `delivered` event arrived within seconds or minutes.

### After DATA with Lost Response

If the server received the end-of-body marker and the connection dropped before the final reply, the client does not know whether A accepted. Switching immediately to B can create duplicates. Use `SUBMISSION_UNKNOWN`, reconcile with provider IDs/logs if available, or follow a business resend workflow with auditing and approved risk acceptance.

### Server Returns Final 5xx After DATA

If the server replies with an explicit 5xx at the end of DATA, that is an explicit rejection of the SMTP transaction on A. It differs from "outcome unknown." However, **explicit rejection does not automatically make B valid**: if the cause is content, permission, or policy, fix the cause. Consider B only after classifying the issue as A-specific and verifying rerouting is permitted.

## 10. Provider-Neutral Transport Outcome Model

Applications should translate each provider's SMTP responses into a common model before deciding:

~~~java
package com.example.mail.routing;

public enum FailureKind {
    INVALID_RECIPIENT,
    INVALID_PAYLOAD,
    CONTENT_POLICY_REJECTED,
    SENDER_NOT_AUTHORIZED,
    SMTP_AUTH_REJECTED,
    PROVIDER_UNAVAILABLE,
    PROVIDER_THROTTLED,
    TEMPORARY_RECIPIENT,
    SUBMISSION_OUTCOME_UNKNOWN,
    UNCLASSIFIED
}
~~~

~~~java
package com.example.mail.routing;

public enum FailureScope {
    REQUEST,
    RECIPIENT,
    PROVIDER_ACCOUNT,
    PROVIDER_INFRASTRUCTURE,
    UNKNOWN
}
~~~

~~~java
package com.example.mail.routing;

public record NormalizedMailFailure(
        FailureKind kind,
        FailureScope scope,
        String providerKey,
        String smtpPhase,
        String smtpReplyCode,
        String enhancedStatusCode,
        boolean acceptedByTransport,
        boolean outcomeUnknown
) {
}
~~~

These are **internal models**, not built-in Spring Mail classes. Never rely solely on `MailException.getMessage()` to populate `smtpPhase` or `acceptedByTransport`. Rely on events the real adapter can observe and trust; when missing, leave state unknown rather than filling in convenient facts to force failover.

### Caution with Spring's `MailException`

`JavaMailSender.send(...)` does not return a provider message ID or a universal `delivered` status. Exceptions you may encounter:

| Spring/Jakarta Mail signal | What can be known | What still needs checking |
| --- | --- | --- |
| `MailAuthenticationException` | Authentication failed | Bad credentials, permissions, temporary provider glitch, or wrong AUTH mechanism? |
| `MailSendException` | One or more messages failed transport submission | Phase, reply code, failed messages, partial success |
| `MailParseException` | Message could not be parsed/prepared | What payload/template error? |
| `MailPreparationException` | Error preparing MIME/message | Bad input data or resource error? |
| Jakarta Mail `SMTPSendFailedException` | May carry a specific SMTP reply | Which command/stage did the reply belong to, and outcome? |
| Jakarta Mail `SMTPAddressFailedException` | May carry recipient-related failure | Were there multiple recipients/partial acceptance? |
| `SocketTimeoutException` in cause chain | Socket operation timed out | Timeout before or after end-of-DATA marker? |

A `MailSendException` can contain a map of failed messages and causes per message. Do not write identical handling for **single-recipient** and **multi-recipient** sends: when partial-send is enabled, some recipients may have been accepted while others were rejected.

### Preserve Provider Details Safely

While normalizing, keep controlled metadata:

- Provider key and account/route ID.
- SMTP command/phase if known.
- Three-digit reply and enhanced status.
- Normalized reason family.
- Provider-specific error key.
- Attempt ID and internal notification ID.
- Timestamp and trust level of the evidence source.

Raw SMTP text may include email addresses or sensitive data; enforce redaction and access controls. Never log passwords, access tokens, or full MIME bodies.

## 11. Stop Rules Before Making a Failover Decision

A policy should check **guardrails in order**, not just whether the provider errored.

~~~text
if notification has expired:
    STOP_EXPIRED

if recipient is suppressed or lacks required consent:
    STOP_SUPPRESSED

if payload/template/MIME is invalid:
    STOP_INVALID_CONTENT

if any previous attempt was accepted:
    NO_FAILOVER_ALREADY_SUBMITTED

if any relevant attempt has unknown submission outcome:
    RECONCILE_BEFORE_RETRY

if failure scope is RECIPIENT or REQUEST permanent:
    STOP_PERMANENT

if failure is content/policy or sender authorization:
    HOLD_FOR_CORRECTION

if failure is provider-specific infrastructure:
    evaluate eligible backup providers
else:
    HOLD or RETRY according to conservative policy

if backup is not approved or lacks capacity:
    RETRY_LATER / HOLD
else:
    schedule one controlled failover attempt
~~~

Some conditions (consent, expiry, suppression, provider capabilities) can change between decision time and when a worker actually submits, so workers must **recheck right before dispatch**, not only at enqueue time.

### Idempotency Keys Do Not Replace All Preconditions

A unique `notificationId` prevents enqueuing the same business action twice. Even if all adapters use the same `Message-ID`, SMTP does not guarantee every relay/mailbox deduplicates. A provider's idempotency API (if present) may offer additional guarantees; never assume `JavaMailSender` has exactly-once semantics.

## 12. A Small Java Policy to Block Bad Failover

The Java 17 example below separates **business decision logic** from socket calls:

~~~java
package com.example.mail.routing;

public enum RecoveryAction {
    STOP_PERMANENT,
    HOLD_FOR_CORRECTION,
    RETRY_SAME_PROVIDER_LATER,
    FAILOVER_TO_APPROVED_PROVIDER,
    RECONCILE_UNKNOWN
}
~~~

~~~java
package com.example.mail.routing;

public record CandidateProvider(
        String key,
        boolean approvedForNotification,
        boolean senderAuthorized,
        boolean recipientAndRegionAllowed,
        boolean supportsPayload,
        boolean hasCapacity
) {
    public boolean eligible() {
        return approvedForNotification
                && senderAuthorized
                && recipientAndRegionAllowed
                && supportsPayload
                && hasCapacity;
    }
}
~~~

~~~java
package com.example.mail.routing;

public final class MailFailoverPolicy {

    public RecoveryAction decide(
            NormalizedMailFailure failure,
            CandidateProvider candidate,
            boolean hasPriorAcceptedAttempt,
            boolean hasUnknownAttempt,
            boolean attemptsAvailable) {

        // Safety guard must run before any consideration of route B.
        if (hasPriorAcceptedAttempt || hasUnknownAttempt
                || failure.outcomeUnknown()
                || failure.acceptedByTransport()) {
            return RecoveryAction.RECONCILE_UNKNOWN;
        }

        if (!attemptsAvailable) {
            return RecoveryAction.STOP_PERMANENT;
        }

        return switch (failure.kind()) {
            case INVALID_RECIPIENT,
                 INVALID_PAYLOAD,
                 CONTENT_POLICY_REJECTED ->
                    RecoveryAction.STOP_PERMANENT;

            case SENDER_NOT_AUTHORIZED,
                 SMTP_AUTH_REJECTED ->
                    RecoveryAction.HOLD_FOR_CORRECTION;

            case PROVIDER_UNAVAILABLE,
                 PROVIDER_THROTTLED ->
                    candidate != null && candidate.eligible()
                        ? RecoveryAction.FAILOVER_TO_APPROVED_PROVIDER
                        : RecoveryAction.RETRY_SAME_PROVIDER_LATER;

            case TEMPORARY_RECIPIENT ->
                    RecoveryAction.RETRY_SAME_PROVIDER_LATER;

            case SUBMISSION_OUTCOME_UNKNOWN ->
                    RecoveryAction.RECONCILE_UNKNOWN;

            case UNCLASSIFIED ->
                    RecoveryAction.HOLD_FOR_CORRECTION;
        };
    }
}
~~~

**Limitations of this illustrative code:**

- `attemptsAvailable` is only one guard; the application must also check deadlines and combined budget across A+B.
- `STOP_PERMANENT` on attempt exhaustion here means **ending automatic retries**, not asserting the recipient does not exist. Persistence should distinguish `DEAD_LETTER` (budget exhausted) from `FAILED_PERMANENT` (unsendable error).
- `RECONCILE_UNKNOWN` is also returned here for `hasPriorAcceptedAttempt`; production should have a distinct `ALREADY_SUBMITTED` result so it does not look like every accepted attempt needs reconciliation.
- Classifiers must distinguish real provider throttling from temporary recipient errors; never map every 4xx to `PROVIDER_THROTTLED`.
- `candidate.eligible()` is only a snapshot. Workers must re-run eligibility checks right before sending.

In production, split `DeliveryTerminalReason` into **business/permanent failures** and **automatic retry budget exhausted**. Never suppress a recipient solely because a provider's retry budget ran out.

### Never Write a Catch Loop Trying All Providers

~~~java
// DO NOT DO THIS:
for (JavaMailSender sender : allSenders) {
    try {
        sender.send(message);
        return;
    } catch (MailException ignored) {
        // Every error is treated as eligible to try the next provider.
    }
}
~~~

That snippet has no idea:

- Whether the error was `INVALID_RECIPIENT` or `CONTENT_POLICY`.
- Whether the previous provider already accepted the message.
- Whether consent, From permission, or data residency holds.
- Whether the `MimeMessage` is compatible/prepared properly for the next provider's session.
- Whether attempts exceed budgets and rate limiters.

**Catching errors more broadly does not make a system more available.** Unclassified catching can push invalid requests down multiple routes with hard-to-control fallout.

## 13. Unsendable Errors Occurring Before Opening an SMTP Connection

Some cases must stop **before building messages and invoking senders**:

### Invalid Email Addresses

At the business boundary, validate syntax/required fields; you can use an email-address library or Jakarta Mail `InternetAddress` to check structure, though valid syntax **does not prove a mailbox exists**.

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public final class RecipientSyntax {
    public static boolean isValid(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }
        try {
            InternetAddress address = new InternetAddress(value, true);
            address.validate();
            return value.equals(address.getAddress());
        } catch (AddressException exception) {
            return false;
        }
    }
}
~~~

This is only syntax validation per library/normalized strings; it does not replace EAI/internationalized address handling or product policies where required. If `InternetAddress` returns a normalized address differing from input, use an explicit normalization flow instead of raw string equality as in the example.

### Missing Template Data

If Thymeleaf/FreeMarker or another engine fails to render due to missing model variables or broken templates, changing providers solves nothing. A `render` stage should finish before `selectProvider` or before SMTP submit:

~~~text
Notification input
   -> Validate recipient, consent, expiry
   -> Render subject/body from trusted template
   -> Validate MIME/attachment
   -> Choose approved provider
   -> Submit
~~~

If rendering fails, record `HOLD_FOR_CORRECTION` or `FAILED_PERMANENT` per policy—never generate two SMTP attempts just because two providers exist.

### Expired Messages

An email carrying an expired verification code must stop. Accepting delivery through provider B after A failed produces a useless notification, confuses users, and can mislead them into thinking the code is still valid.

## 14. Recipient Suppression Must Be a Shared Policy

If A receives a hard bounce, complaint, or unsubscribe, that must not update only A's private list. The sending system needs a unified suppression source matching policy scope.

~~~text
Provider A -- hard bounce / complaint -->
                 Suppression store
                         |
                         v
               Shared pre-send check
                 /             \
                v               v
           Provider A       Provider B
~~~

### Suppression Scope

A suppression record should contain:

- Recipient identity or normalized email address.
- Tenant/account scope.
- Reason: `HARD_BOUNCE`, `COMPLAINT`, `UNSUBSCRIBE`, `ADMIN_BLOCK`, etc.
- Message category scope: marketing, transactional, security, etc.
- Source provider/event ID.
- `createdAt` and optional expiry/review status.
- Audit trail of application or removal.

Do not use one immutable global boolean across all mail types. For instance, newsletter unsubscribe differs from a security verification email; yet a mailbox confirmed nonexistent is not a good target for OTP attempts either. Exact policy must follow legal, consent, product, and recipient-verification rules.

### Avoid Suppressing on Untrusted Signals Alone

Bounce/complaint webhooks must have signatures verified and provider/account/recipient correlated. Never let a spoofed HTTP request block sending across all providers.

### Complaints Must Never Be Bypassed

If a recipient complained about marketing email, **switching to provider B to keep sending marketing defeats the purpose of suppression**. Sending across every provider must share the exact same pre-send eligibility check.

## 15. Provider B Is Eligible Only When All Route Requirements Are Met

"Having a backup provider" does not mean "every email can be sent through backup."

Route B is eligible only if:

| Condition | Question to answer |
| --- | --- |
| Provider contract | Is B authorized for this message category? |
| Tenant/region/data residency | Is B allowed to process this tenant's and region's data? |
| Sender authorization | Is B authorized for the intended `From` or envelope sender? |
| Domain authentication | Are DKIM/SPF/DMARC alignment and bounce domain/return-path configured properly? |
| Recipient permissions | Are consent/suppression shared or reliably synchronized? |
| MIME compatibility | Does B support the content, attachment size, and encoding? |
| Tracking requirements | Does B supply events/correlation required for audits/SLAs? |
| Quota/rate budget | Does B have headroom for urgent mail and failover volume? |
| Provider health | Is B free of outages or similar throttling? |
| Security | Does B use valid TLS, credentials, and policy-compliant secret handling? |
| Idempotency | Is there risk A already received the message? Does B have a dedup API if using HTTP? |
| Business constraints | Has the email expired, been cancelled, or belonged to a closed campaign? |

### Provider B Has Not Verified From

If A fails due to networking, yet B has not verified the sending domain, sending through B can fail at `MAIL FROM` or get rejected by remote receivers after submission. That is an **ineligible route**, not an extra retry opportunity.

### Provider B Has Different Quotas

If B is provisioned only for OTP/security, never dump the entire marketing backlog onto B after an A outage. The router must inspect category and reserved capacity before picking B.

### Provider B Is Outside the Permitted Region

A tenant requiring email data to be processed only within a specific region may be barred from using B even when B is healthy and faster. Treat this as a **hard eligibility constraint**, not a ranking weight retries can override.

### Different Providers, Different Recipient Policies

When B maintains its own suppression list, the application must never assume B knows every unsubscribe/complaint received by A. Enforce application-layer suppression synced per provider requirements, with a final pre-dispatch check.

## 16. Designing Multiple JavaMailSender Beans in Spring

`JavaMailSender` is Spring's mail-sending abstraction; `JavaMailSenderImpl` is the Jakarta Mail–based SMTP implementation. A multi-provider system can declare multiple sender beans, though standard Spring Boot Mail auto-configuration **does not build a router/failover policy** across all providers.

Example application-owned per-provider configuration:

~~~yaml
mail:
  routes:
    primary:
      host: smtp-a.example.net
      port: 587
      username: app-a
      tls-mode: starttls
    secondary:
      host: smtp-b.example.net
      port: 587
      username: app-b
      tls-mode: starttls
~~~

Real credentials must come from a secret manager/env injection, never placed in source control. The YAML above is an illustrative application-defined namespace, **not Spring Boot's default multi-provider schema**.

### Creating Independent Senders

~~~java
package com.example.mail.routing;

import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpSenderFactory {

    public static JavaMailSenderImpl forStartTls(
            String host,
            int port,
            String username,
            String password) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties props = new Properties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "3000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");

        sender.setJavaMailProperties(props);
        return sender;
    }
}
~~~

This configures transport for SMTP submission using STARTTLS and does not apply verbatim to providers using implicit TLS, OAuth2/XOAUTH2, or REST APIs. `password` is supplied as a runtime secret; never log `JavaMailSenderImpl` or sensitive fields.

### Separate Beans and Registry

~~~java
package com.example.mail.routing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;

@Configuration
public class MultiProviderMailConfig {

    @Bean("primaryMailSender")
    JavaMailSender primaryMailSender(
            PrimarySmtpSecrets secrets) {
        return SmtpSenderFactory.forStartTls(
                secrets.host(),
                secrets.port(),
                secrets.username(),
                secrets.password());
    }

    @Bean("secondaryMailSender")
    JavaMailSender secondaryMailSender(
            SecondarySmtpSecrets secrets) {
        return SmtpSenderFactory.forStartTls(
                secrets.host(),
                secrets.port(),
                secrets.username(),
                secrets.password());
    }
}
~~~

`PrimarySmtpSecrets` and `SecondarySmtpSecrets` are application interfaces/types or secret-manager adapters, not built into Spring. When injecting two senders, use `@Qualifier` or an explicit registry to avoid picking the wrong bean. Never mutate username/password on a sender shared across threads during rotation; restart or build a new candidate and swap safely.

### SMTP Adapter Does Not Decide Failover Itself

~~~java
package com.example.mail.routing;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class SmtpProviderAdapter {

    private final String key;
    private final JavaMailSender sender;

    public SmtpProviderAdapter(
            String key, JavaMailSender sender) {
        this.key = key;
        this.sender = sender;
    }

    public void submit(SimpleMailMessage message) {
        sender.send(message);
    }

    public String key() {
        return key;
    }
}
~~~

The adapter sends over a single route. It does not catch exceptions to try another adapter. An outer layer must normalize errors, check state/eligibility, and decide actions. `SimpleMailMessage` suits only basic plain-text emails; for HTML/attachments, use `MimeMessage` built properly for the matching sender/session.

## 17. Retries/Failover Must Not Run Inside an Unbounded Synchronous Loop

This pattern is typically dangerous inside a web request:

~~~java
try {
    primary.send(message);
} catch (MailException failure) {
    secondary.send(message);
}
~~~

Problems:

1. B gets called even for `MailParseException`, `MailAuthenticationException`, and permanent recipient errors.
2. No backoff time, attempt cap, or quota control.
3. Unclear whether A already accepted the message before the exception occurred.
4. HTTP transactions can block for a long time across two network calls.
5. No audit of the route-switch reason.
6. No recheck of consent/expiry/suppression when B sends.

With a transactional outbox, a safer flow:

~~~text
Business transaction
    -> Persist notification + outbox
    -> Commit

Worker claims due record
    -> Validate business prerequisites
    -> Choose provider A
    -> Reserve provider-specific budget
    -> Attempt submit A
    -> Normalize outcome
    -> Persist outcome + next action

If eligible for B:
    -> Persist scheduled failover attempt
    -> Release lease
    -> Worker later claims due attempt B
    -> Revalidate + reserve B budget
    -> Submit B once
~~~

Scheduling B **does not mean waiting minutes** during a real outage; some systems allow fast failover. Every call must still enter attempt history and obey quotas. Processing via durable workers normally controls concurrency and duplicates far better than synchronous catch loops.

## 18. State Machine for Multiple Providers

One business message can have multiple attempts across different routes, yet only one **durable sending request**.

~~~text
PENDING
   |
   v
CLAIMED
   |
   v
ATTEMPT_A
   |
   +-- Accepted --------------------> SUBMITTED
   |
   +-- Unknown ---------------------> SUBMISSION_UNKNOWN
   |
   +-- Invalid/Policy --------------> HOLD / FAILED_PERMANENT
   |
   +-- Provider temporary ----------> RETRY_PENDING / FAILOVER_SCHEDULED
                                         |
                                         v
                                      ATTEMPT_B
                                         |
                                         +--> SUBMITTED
                                         +--> RETRY_PENDING / DEAD_LETTER
                                         +--> HOLD / UNKNOWN
~~~

Never create a *new* outbox record on each provider failure if that breaks idempotency linkage to the original notification. Keep one notification ID and multiple provider-attempt IDs.

### Recommended Attempt Statuses

| Attempt status | Meaning |
| --- | --- |
| `READY` | Planned, transport not yet called |
| `SENDING` | Claimed and actively using route |
| `ACCEPTED` | Relay accepted submission |
| `REJECTED_TEMPORARY` | Received temporary rejection response |
| `REJECTED_PERMANENT` | Received permanent rejection response per phase |
| `FAILED_BEFORE_SUBMISSION` | Transport never reached submitting the body |
| `OUTCOME_UNKNOWN` | Provider may have accepted |
| `CANCELLED` | Attempt invalidated/superseded by another decision |

Notification-level aggregate projection must evaluate **all attempts**, not just the latest attempt. If attempt A was ACCEPTED, never let attempt B send because A's webhook arrived late or another retry scheduler read stale state.

## 19. Database: Persisting Stop Reasons and Tried Routes

A conceptual schema:

~~~sql
CREATE TABLE mail_notification (
    id                   VARCHAR(100) PRIMARY KEY,
    idempotency_key      VARCHAR(250) NOT NULL UNIQUE,
    recipient_key        VARCHAR(100) NOT NULL,
    category             VARCHAR(100) NOT NULL,
    status               VARCHAR(50) NOT NULL,
    created_at           TIMESTAMP NOT NULL,
    expires_at           TIMESTAMP,
    next_attempt_at      TIMESTAMP,
    stop_reason          VARCHAR(100)
);

CREATE TABLE mail_provider_attempt (
    id                   VARCHAR(100) PRIMARY KEY,
    notification_id      VARCHAR(100) NOT NULL,
    provider_key         VARCHAR(100) NOT NULL,
    attempt_number       INTEGER NOT NULL,
    status               VARCHAR(50) NOT NULL,
    smtp_phase           VARCHAR(100),
    reply_code           VARCHAR(20),
    failure_kind         VARCHAR(100),
    created_at           TIMESTAMP NOT NULL,
    finished_at          TIMESTAMP,
    FOREIGN KEY (notification_id)
        REFERENCES mail_notification(id),
    UNIQUE (notification_id, attempt_number)
);

CREATE TABLE mail_route_decision (
    id                   VARCHAR(100) PRIMARY KEY,
    notification_id      VARCHAR(100) NOT NULL,
    from_provider        VARCHAR(100),
    to_provider          VARCHAR(100),
    action               VARCHAR(100) NOT NULL,
    normalized_reason    VARCHAR(100) NOT NULL,
    decided_at           TIMESTAMP NOT NULL
);
~~~

Abbreviated schema; production needs tenant scope, recipient-level tracking, attempt ownership/leases, event storage, indexes, constraints, and retention/auditing. `provider_key` is an internal identifier, not a credential.

### Why Persist Stop Reasons Too?

Example:

~~~text
notification: notif-1042
status: FAILED_PERMANENT
stopReason: INVALID_RECIPIENT
attempts:
  - provider=A, smtpPhase=RCPT_TO, replyCode=550
routeDecision:
  - STOP_PERMANENT, not routed to B
~~~

Operators need to prove **why the system did not fail over**, not merely see that an email did not arrive. Stop reasons distinguish recipient errors from outages and guide proper investigation.

### Do Not Increment Attempts Before Calling Transport

If a worker detects an invalid payload, suppressed recipient, or insufficient quota on provider B **before sending**, that is a validation/deferred decision, not a new SMTP attempt. Metrics and attempt history should reflect actual transport calls.

## 20. Controlling Multiple Workers with Leases and Fencing

If two replicas both see A fail and both pick B, they can send duplicates. You need atomic claiming:

1. Select due `PENDING` or `RETRY_PENDING` notifications.
2. Assign `PROCESSING`, `leaseOwner`, `leaseUntil`, and generation inside a transaction.
3. Commit the claim.
4. Execute SMTP send outside the database transaction.
5. Persist the outcome only if lease owner/generation remain valid.

With PostgreSQL, part of the query:

~~~sql
SELECT id
FROM mail_notification
WHERE status IN ('PENDING', 'RETRY_PENDING')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, created_at
LIMIT 20
FOR UPDATE SKIP LOCKED;
~~~

In that same transaction, the worker must UPDATE status/leases on the selected IDs before committing; a bare SELECT **does not create a durable claim by itself**. Other databases have different locking/CAS mechanisms.

### Leases Do Not Create Exactly-Once SMTP

If worker A submitted successfully yet died before writing `SUBMITTED`, the lease can expire and another worker may reclaim it. Therefore:

- Never blindly reset every expired-lease `PROCESSING` row back to `PENDING`.
- Record reliable phase/attempt outcomes when available.
- Use `SUBMISSION_UNKNOWN` and reconciliation for uncertain windows.
- Enforce fencing tokens so stale workers cannot overwrite newer state.

Fencing tokens protect database state; **they cannot recall emails that already left the application**.

## 21. Multi-Recipient: Do Not Fail Over the Whole Message If Only One Address Fails

One MIME message with multiple To/Cc/Bcc addresses may be accepted by SMTP relay A for some recipients and rejected for others. Partial-send behavior depends on Jakarta Mail provider/SMTP configuration, such as `mail.smtp.sendpartial` in many implementations.

Example:

~~~text
RCPT TO: alice@example.org  -> 250 accepted
RCPT TO: bob@example.org    -> 550 5.1.1 user unknown
DATA                        -> may or may not proceed
~~~

If a service sees `MailSendException` and resends **the entire message** via B, Alice gets a second copy while Bob still does not exist.

### Design Guidance

- For personalized transactional mail, prefer **one recipient per notification/submission** where appropriate.
- If multiple recipients are mandatory, store status at the **recipient-attempt level**.
- Distinguish accepted, temporarily rejected, and permanently rejected per recipient.
- Never fail over already-accepted recipients.
- Never fail over permanently invalid recipients merely because other recipients hit temporary errors.
- Never rely on a single `allFailed` boolean when transport supports partial acceptance.

An integration test using a fake SMTP server returning 250 for the first recipient and 550 for the second verifies how `JavaMailSenderImpl` and the adapter record results under your project settings.

## 22. Provider A Reports Hard Bounce After Accepting

After A accepts a message, the relay may retry delivery to the remote MX and later receive a final bounce. This differs from an immediate submission error.

~~~text
Spring Mail -> Provider A SMTP: 250 accepted
     |
     v
Notification = SUBMITTED
     |
     v
Provider A -> Recipient MX: 550 5.1.1
     |
     v
Provider event: HARD_BOUNCE
     |
     v
Suppress recipient / mark downstream delivery failed
     |
     X
No automatic Provider B resend
~~~

A reliable hard bounce confirming a nonexistent mailbox is a reason to **stop sending to that recipient**, not a signal to use B.

### Provider Deferred

If A reports `DEFERRED`, A normally owns retrying toward the remote MX. Never create a new send via B without a signal that A ended/relinquished delivery responsibility and a separate business decision authorizing a resend.

### Complaints

If A emits a `COMPLAINED` event, enforce suppression in the shared layer before any new sends via B. Never use provider switching to evade feedback loops.

### Webhooks Can Arrive Late or Duplicated

Provider events can arrive out of order. Verify signatures, persist events durably, deduplicate scoped provider event IDs, and correlate by provider message ID, attempt ID, and recipient. Never update notification status simply from the last event received.

## 23. Separate "Retries Exhausted" from "Permanently Invalid Recipient"

A system can stop sending for very different reasons:

| Case | Operational outcome | Suppress recipient? |
| --- | --- | --- |
| RCPT `550 5.1.1` confirming nonexistent mailbox | `FAILED_PERMANENT` or `BOUNCED` per stage | Possibly, per policy and trusted source |
| Template failed to render | `HOLD_FOR_CORRECTION` | No |
| MIME exceeded product limits | `HOLD_FOR_CORRECTION` | No |
| Campaign expired | `EXPIRED` | Not necessarily |
| User unsubscribed from marketing | `SUPPRESSED` | Yes, per category |
| A outage, attempts exhausted | `DEAD_LETTER` / `RETRY_BUDGET_EXHAUSTED` | No |
| A accepted | `SUBMITTED` | No |
| Final reply lost | `SUBMISSION_UNKNOWN` | No |
| Account A locked | `HOLD_FOR_PROVIDER_RECOVERY` | No |

If you use one `FAILED` status and suppress every failed address, a provider outage can block valid recipients. If you treat every `FAILED` as a cue to try B, you might mail unsubscribed recipients. Therefore store **stop reason** alongside status and evaluate it in policy.

### Policy Must Express Two Axes

1. **Is another submission attempt permitted?**
2. **Is using another provider permitted?**

For instance, a temporary `451` may allow retrying later, yet if the tenant is restricted to provider A, **failover is disallowed**. Conversely, if A is unavailable and B is approved, the system can choose B without wasting many retries on A.

### Decisions That Must Never Be Overridden by Urgency

An OTP email is critical, yet invalid once expired. A security alert needs speed, yet cannot bypass legal suppressions or send via a provider barred from processing tenant data. Priority allocates quota **within valid routes**—it never turns an invalid request into a valid one.

## 24. Capping Send Budgets at the Notification Level

Running multiple providers raises the risk of multiplying attempts:

~~~text
Outbox retry limit:        5
Provider A adapter retry:  3
Provider B adapter retry:  3
Broker redelivery:         May occur
~~~

If every layer retries independently without coordination, actual transport calls can far exceed expectations. Enforce a **global attempt budget** per notification alongside per-provider/route caps.

### Count Physical Submissions Accurately

An attempt should be recorded when transport actually begins an SMTP/API call. The following **must not count as SMTP attempts**:

- Validation rejecting a recipient.
- Template rendering failing pre-send.
- Suppression check rejecting.
- No rate tokens available.
- Provider B lacking permissions or quota.
- Route policy returning `HOLD`.

If an internal adapter has built-in retries, count/observe real transport calls, not just `dispatcher.dispatch()` invocations.

### Budget Example

Suppose a notification allows **at most 4 real submissions**:

~~~text
Attempt 1: Provider A -> TCP refused
Attempt 2: Provider A -> TCP refused
Attempt 3: Provider B -> SMTP 421
Attempt 4: Provider B -> SMTP 250 accepted

Total physical attempts = 4
Final submission state = SUBMITTED
~~~

If B returns `550 5.1.1` for nonexistent mailbox on attempt 3, **there is no attempt 4** just because 1 budget unit remains. A permanent error stops the loop regardless of unused quota.

### Retry Budgets and Deadlines

Do not rely solely on attempt counts. Add:

- `expiresAt` or `maxAge`.
- `nextAttemptAt` and backoff.
- Max attempts per provider.
- Global messages/second and per-recipient/day caps if policy requires.
- Permission to use provider B by category/tenant.

An OTP may still have attempts left yet expire in TTL before reaching B. That case must become `EXPIRED`.

## 25. Backoff, Jitter, and Circuit Breakers for Retryable Failures

During a real outage on A, eligible requests may fail over to B. However, **rerouting must not break load limits**.

### Exponential Backoff

A common formula:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1})
\]

Where:

- `n`: number of completed failures.
- `d0`: base delay.
- `dmax`: maximum delay.
- Jitter spreads out retries so thousands of jobs do not come due at once.

Never use jitter as a substitute for a global rate limiter. When backlogs are huge, even jittered retries must stay within B's actual quota.

### Per-Provider/Account Circuit Breakers

A breaker can open when A suffers a broad outage:

~~~text
Provider A:
  CLOSED -> OPEN -> HALF_OPEN -> CLOSED

Provider B:
  Independent health/budget, not affected by A's state alone
~~~

Never open a provider-wide breaker because one recipient returned `550 5.1.1`. Permanent recipient errors are not signals of an A infrastructure outage.

When A is OPEN, that does not mean shifting every email to B. The router still checks eligibility, preferences, expiry, sender identity, and B capacity. If B also has an outage, hold in the outbox instead of ping-ponging A→B→A.

### Do Not Pick B When B Lacks Quota

For example, B has a limited budget reserved for security emails. When A goes down, a marketing backlog can be thousands of times larger than normal traffic. Routing marketing through B can delay new OTPs. You need per-category quotas and reserved capacity—not merely "B healthy."

## 26. Never Use Failover to Evade Rate Limits or Complaint Policies

Some failures reflect service limits rather than address errors:

- Provider A throttles for exceeding quota.
- A slows down due to sending too much to one recipient domain.
- A temporarily blocks an account for spam complaints.

Distinguish:

**Legitimate capacity failover:** B is an approved backup provider with compatible quotas, sender identities, and recipient policies. Extra traffic can be distributed within contractual limits.

**Invalid policy circumvention:** A blocks for abuse/complaints yet the system tries pushing similar content through B to dodge filters. Stop and investigate root cause instead of sending elsewhere.

### SMTP 4xx Does Not Always Mean "Switch Providers"

A `451` at RCPT TO may be a temporarily unavailable mailbox; changing providers may not help because the remote MX is the same. If the issue sits at the recipient domain, B may receive the same error, doubling requests to the remote domain and making things worse.

Only when there is A-route-specific evidence and B is authorized is failover a grounded decision.

## 27. Per-Provider Eligibility Configuration

In a real system, conditions should not be hardcoded as scattered `if (provider.equals("A"))` checks. Model them explicitly:

~~~java
public record ProviderCapabilities(
        String providerKey,
        boolean supportsHtml,
        boolean supportsAttachments,
        long maxMessageBytes,
        boolean supportsDeliveryEvents,
        boolean verifiedSender,
        boolean eligibleForTransactional,
        boolean eligibleForMarketing
) {
}
~~~

When evaluating a notification:

1. Is the email category approved for this provider?
2. Does the content contain attachments, and does B support them?
3. Does estimated MIME size stay within `maxMessageBytes`?
4. Are From/envelope sender permitted by B?
5. Does B support result tracking needed for audits/SLAs?
6. Are region, tenant, and sensitive data allowed to be processed by B?

**Do not infer `maxMessageBytes` from raw file size alone.** MIME encoding, Base64, and headers can make messages noticeably larger than raw attachments; measure or estimate with safety headroom per provider.

### Changing Providers Can Change MIME

With two SMTP senders, messages should be built from **one verified domain notification/payload**. From/Reply-To/Return-Path/DKIM settings can vary by route and must be prepared properly.

Never secretly alter content inside adapter B to bypass A's policy. If shrinking an attachment or changing a template is needed, that is a **new content decision** requiring verification, not an automatic retry of the same payload.

## 28. Preserving Notification Meaning Across Providers

A business message may carry:

~~~text
notificationId:     notif-9001
businessKey:        ORDER_PAID:order-800:recipient-42
category:           TRANSACTIONAL
recipient:          recipient-42
payloadVersion:     order-receipt-v3
expiresAt:          optional
preferredProvider:  A
eligibleFallback:   B
~~~

The router can pick a different route, yet:

- Never generate a new idempotency key that severs linkage to the original request.
- Never generate a new OTP/token just because A failed; if a new code is needed, business logic must issue a new notification.
- Never resend an invoice with stale data after an order was modified, unless policy explicitly specifies.
- Never swap From domains in ways that mislead recipients or break domain authentication.
- Never strip attachments or trim content to fit B if doing so alters business meaning without approval.

Equivalence between two routes is not just "same text"; it includes sending permissions, content, data handling, and authentication/audit tracking.

## 29. Typical Scenario: Recipient 550 Error

Suppose the app sends an invoice:

~~~text
Notification: receipt-184
Recipient: buyer@example.org
Provider A:
  MAIL FROM  -> 250
  RCPT TO    -> 550 5.1.1 User unknown
~~~

**Decision:**

1. Record that A's attempt was rejected at RCPT TO.
2. Normalize to `INVALID_RECIPIENT` when reply/provider evidence is trustworthy.
3. Transition the notification to `FAILED_PERMANENT` or equivalent.
4. Update suppression/prompt customer to fix email per policy.
5. **Do not send via B.**
6. Keep audit history explaining why the email was not sent.

If a staff member updates the recipient address after verification, the system can create a **new notification** or a business-controlled replay task—never simply shift A→B with the already-rejected address.

## 30. Scenario: Content Violates Policy

Suppose A rejects an email carrying a policy-violating attachment:

~~~text
Provider A:
  DATA -> 554 5.7.1 Content rejected

Provider B:
  available and accepts same MIME type
~~~

**Do not** treat "B can accept it" as a reason to try. If the cause is a content policy that must be honored (such as dangerous payloads, phishing links, or banned attachments), pushing through B increases risk.

Instead:

1. Pause the message.
2. Record code/phase and sanitized reason.
3. Separate technical limits (e.g., B supports a larger size) from genuine content-policy rejections.
4. Fix content or sending permissions through an authorized workflow.
5. Verify the new request still has consent/validity.
6. Replay over an eligible route only after resolving the root cause.

### Are Oversized Attachments an Exception?

Suppose A caps messages at one size, B has a higher cap, and the product **permits** B to handle this content. That is a **pre-send capability-based routing** problem, not letting A reject first and falling back to B.

If A already rejected due to message size and B can validly accept it, a controlled route correction may fit **after verification**. Still, the default policy should not be endlessly probing providers to find one that accepts any payload.

## 31. Scenario: Provider A Outage Pre-Submit

~~~text
Provider A:
  DNS lookup smtp-a.example.net -> timeout

Provider B:
  Verified sender, correct TLS, healthy quota
  Approved for notification category/tenant
~~~

Handling steps:

1. Record `PROVIDER_UNAVAILABLE` on A; do not mark recipient invalid.
2. Verify notification has not expired, is not suppressed, and has no prior accepted/unknown attempt.
3. Confirm B is eligible and has rate budget.
4. Schedule one B attempt while preserving the original idempotency key.
5. Record route decision A→B with reason `A_ENDPOINT_UNAVAILABLE`.
6. Monitor B's submission result without running A in parallel.

This is a case where failover **genuinely improves availability**. It is completely different from nonexistent mailboxes or banned content.

## 32. Scenario: Provider A SMTP AUTH Failure

Suppose A returns `535`:

~~~text
Provider A:
  SMTP AUTH -> 535 invalid credentials
Provider B:
  independent credential, healthy
~~~

An AUTH failure only proves account A failed authentication—not that the notification is bad. Yet **you should not always switch to B**:

- A might be the only contractually authorized provider.
- B may lack a verified From domain.
- AUTH errors might stem from a shared misconfigured TLS setting.
- If A was compromised, security incident response may require halting dispatch.
- B might hold a protected quota dedicated to OTPs.

Recommended policy: `HOLD_FOR_CORRECTION` on account A, alert the secret owner, and handle rotation. If B is an approved standby route with an explicit failover runbook, an operator/automation can enable failover **after checking every precondition**. Never let `catch (MailAuthenticationException)` flip every message to B automatically.

## 33. Scenario: Timeout After DATA While B Is Healthy

~~~text
Provider A:
  DATA body sent
  final response lost

Provider B:
  healthy
~~~

In this case, the proper initial state is usually `SUBMISSION_UNKNOWN`, **not** `PROVIDER_UNAVAILABLE_SAFE_TO_FAILOVER`.

Handling approach:

1. Do not send via B right away.
2. Persist attempt ID, Message-ID, provider route, and timestamp.
3. Query provider event APIs/relay queue logs if available.
4. If evidence confirms A accepted, update to `SUBMITTED`.
5. If evidence confirms A definitely rejected/never received, consider retry/failover per policy.
6. If unknowable, apply an audited, business-risk-based resend decision.

Never claim exactly-once SMTP delivery. Even with the same `Message-ID`, receiving systems are not required to drop duplicates.

## 34. Policy Unit Tests: Proving Permanent Errors Never Pick B

To prevent regressions when adding new providers, tests must assert the **stop** scenarios, not just happy-path failover.

Using the enums, records, and `MailFailoverPolicy` above, with JUnit 5:

~~~java
package com.example.mail.routing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

class MailFailoverPolicyTest {

    private final MailFailoverPolicy policy =
            new MailFailoverPolicy();

    private static CandidateProvider approvedB() {
        return new CandidateProvider(
                "B",
                true,  // notification category approved
                true,  // sender verified
                true,  // tenant/region/recipient allowed
                true,  // payload supported
                true); // capacity available
    }

    private static NormalizedMailFailure failure(
            FailureKind kind,
            FailureScope scope) {
        return new NormalizedMailFailure(
                kind,
                scope,
                "A",
                "RCPT_TO",
                "550",
                "5.1.1",
                false,
                false);
    }

    @ParameterizedTest
    @EnumSource(value = FailureKind.class, names = {
            "INVALID_RECIPIENT",
            "INVALID_PAYLOAD",
            "CONTENT_POLICY_REJECTED"
    })
    void neverFailsOverPermanentRequestFailures(
            FailureKind kind) {
        var event = failure(kind, FailureScope.REQUEST);

        var decision = policy.decide(
                event, approvedB(),
                false, false, true);

        assertEquals(
                RecoveryAction.STOP_PERMANENT,
                decision);
    }

    @Test
    void providerOutageMayFailOverToApprovedB() {
        var event = failure(
                FailureKind.PROVIDER_UNAVAILABLE,
                FailureScope.PROVIDER_INFRASTRUCTURE);

        assertEquals(
                RecoveryAction.FAILOVER_TO_APPROVED_PROVIDER,
                policy.decide(
                        event, approvedB(),
                        false, false, true));
    }

    @Test
    void providerOutageCannotUseIneligibleB() {
        var unapproved = new CandidateProvider(
                "B", false, true, true, true, true);
        var event = failure(
                FailureKind.PROVIDER_UNAVAILABLE,
                FailureScope.PROVIDER_INFRASTRUCTURE);

        assertEquals(
                RecoveryAction.RETRY_SAME_PROVIDER_LATER,
                policy.decide(
                        event, unapproved,
                        false, false, true));
    }

    @Test
    void authFailureIsNotAutomaticFailover() {
        var event = failure(
                FailureKind.SMTP_AUTH_REJECTED,
                FailureScope.PROVIDER_ACCOUNT);

        assertEquals(
                RecoveryAction.HOLD_FOR_CORRECTION,
                policy.decide(
                        event, approvedB(),
                        false, false, true));
    }

    @Test
    void unknownSubmissionOutcomeBlocksFailover() {
        var event = new NormalizedMailFailure(
                FailureKind.SUBMISSION_OUTCOME_UNKNOWN,
                FailureScope.UNKNOWN,
                "A",
                "DATA_FINAL_REPLY",
                null,
                null,
                false,
                true);

        assertEquals(
                RecoveryAction.RECONCILE_UNKNOWN,
                policy.decide(
                        event, approvedB(),
                        false, false, true));
    }

    @Test
    void previousAcceptedAttemptBlocksAnotherSubmission() {
        var event = failure(
                FailureKind.PROVIDER_UNAVAILABLE,
                FailureScope.PROVIDER_INFRASTRUCTURE);

        assertEquals(
                RecoveryAction.RECONCILE_UNKNOWN,
                policy.decide(
                        event, approvedB(),
                        true, false, true));
    }

    @Test
    void recipientTemporaryFailureDoesNotForceProviderB() {
        var event = failure(
                FailureKind.TEMPORARY_RECIPIENT,
                FailureScope.RECIPIENT);

        assertEquals(
                RecoveryAction.RETRY_SAME_PROVIDER_LATER,
                policy.decide(
                        event, approvedB(),
                        false, false, true));
    }

    @Test
    void unclassifiedFailureNeverTriggersBlindFailover() {
        var event = failure(
                FailureKind.UNCLASSIFIED,
                FailureScope.UNKNOWN);

        assertEquals(
                RecoveryAction.HOLD_FOR_CORRECTION,
                policy.decide(
                        event, approvedB(),
                        false, false, true));
    }
}
~~~

The tests above verify the illustrative **decision function**. Because `NormalizedMailFailure` takes raw SMTP codes, the helper intentionally used the same dummy code across groups to prove the policy decides on *normalized failure kind*; **never map 550 to a provider outage in a real classifier**. In a real system, add classifier tests mapping reply codes/phases → `FailureKind` accurately.

### Guardrails to Test in a Layer Ahead of Policy

~~~text
notification.expiresAt < now
    => EXPIRED, no transport call

recipient is unsubscribed from marketing
    => SUPPRESSED, no A/B call

template cannot render
    => HOLD_FOR_CORRECTION, no A/B call

notification already SUBMITTED
    => no new attempt
~~~

If you only unit-test `MailFailoverPolicy` without testing pre-send validation, bugs can still slip through: the router picks an eligible B while the worker fails to check that the recipient just unsubscribed.

## 35. Integration Test: Provider A Rejects, Provider B Is Never Called

Policy unit tests do not prove real application wiring calls the right sender. Integration tests must observe both routes.

### Scenario

1. Start SMTP test servers A and B on two different loopback ports.
2. Have A return `550 5.1.1` at `RCPT TO`.
3. Have B accept messages while counting connections/commands.
4. Dispatcher sends the notification through A.
5. Wait for outcome processing and final state.
6. Verify A received RCPT TO and B **received zero attempts**.

### Expected Result

~~~text
A.receivedConnections = 1
A.receivedRCPT        = 1
A.reply              = 550 5.1.1

B.receivedConnections = 0
B.receivedDATA        = 0

notification.status   = FAILED_PERMANENT
notification.reason   = INVALID_RECIPIENT
routeDecisions        = STOP_PERMANENT
~~~

This is the expected test result, not live execution output. It holds only when the adapter/classifier maps `550 5.1.1` and phase `RCPT TO` per fixture to invalid recipient.

### Add a Content-Error Test

Give a message missing a required attachment or failing template rendering **before SMTP submission**:

- A is never called.
- B is never called.
- Notification is held for data correction or moved to terminal state per policy.
- Validation-failure metric increments.
- Zero physical attempts created.

If code blindly does `catch(Exception)` and tries B, this test catches it immediately even when B is healthy.

## 36. Integration Test: Route A Outage Permitted to Switch to B

A control test is needed to prove the system **does not block failover in all cases**.

### Test Setup

- A is an unreachable test SMTP endpoint, or a fake server returning a temporary failure mapped by the classifier as route-A outage.
- B is an SMTP test server accepting DATA, marked approved/verified, and with available quota.
- Notification is unexpired, valid, and has no prior accepted/unknown attempt.

### Expectation

~~~text
attempt[1]: provider=A
            status=FAILED_BEFORE_SUBMISSION
            reason=PROVIDER_UNAVAILABLE

decision:   FAILOVER_TO_APPROVED_PROVIDER

attempt[2]: provider=B
            status=ACCEPTED

notification:
            status=SUBMITTED
            attempts=2
~~~

Also assert connection counts to A/B, physical SMTP attempt counts, duration, and released resources. Do not require `DELIVERED` if fake B only returns final SMTP 250; this is a submission test.

### B Ineligible

Re-run the test with B configured as disallowed for the notification category. Result:

- A fails.
- B receives zero connections.
- Notification waits to retry A or enters hold per policy.
- Route decision states `CANDIDATE_INELIGIBLE`.

This is a vital test because the system must honor contracts **even during an A outage**.

## 37. Testing When A Accepted Yet Worker Is Uncertain

A scripted SMTP server can receive the body up to `CRLF . CRLF`, then **close the socket before the final reply**.

Assertions:

1. Client may receive `MailSendException` or a connection-error wrapper.
2. If the adapter is instrumented for phase tracking, result should be `SUBMISSION_OUTCOME_UNKNOWN`.
3. Outbox transitions to `SUBMISSION_UNKNOWN`.
4. B is not called automatically even though B is healthy.
5. Attempt history still records provider A and correlation metadata.
6. A reconciliation worker can inspect provider logs/events if available.

**Limitation:** relying solely on `JavaMailSender`'s public API may not tell you whether the socket finished sending DATA. Without enough evidence, pick the conservative classification; never assert A definitely did not receive the email just because an exception occurred.

### Testing Database Loss After A Accepted

Another scenario:

~~~text
A SMTP -> final 250 received
Worker -> database update SUBMITTED fails
Worker process terminates
~~~

When the worker restarts, the outbox may still show `PROCESSING` or an expired lease. If recovery logic automatically switches to B, the message risks duplication. Tests must verify state reconciliation/attempt ledgers and policy when outcome cannot be determined.

## 38. Testing Provider Downstream Bounces and Complaints

Do not test only SMTP submission exceptions. For provider events:

### Hard Bounce

~~~text
1. A accepted -> notification SUBMITTED.
2. Event A: hard bounce recipient invalid.
3. Consumer verifies signature and correlates event.
4. Recipient-level suppression updated.
5. B is healthy.
6. Assert no B submission is scheduled for same notification.
~~~

### Deferred

~~~text
1. A accepted.
2. Event A: deferred / provider retry in progress.
3. Assert no new B attempt.
4. Wait for delivered/bounced outcome from A.
~~~

### Complaint

~~~text
1. A accepted/delivered.
2. Event A: complained from recipient.
3. Suppression policy marks marketing as blocked.
4. A new marketing notification selects B.
5. Shared suppression check blocks the B attempt.
~~~

Webhooks must defend against spoofing and duplicate delivery. Tests should count unique events by provider event ID/recipient, not just increment handler call counts.

## 39. Full Test Matrix

| ID | Failure/condition | A | B | Result to assert |
| --- | --- | --- | --- | --- |
| F01 | Malformed email address | Not called | Not called | Validation failure |
| F02 | Confirmed recipient hard bounce | Do not resend | Do not resend | Properly scoped suppression |
| F03 | RCPT 550 5.1.1 user unknown | Rejected | Not called | `FAILED_PERMANENT` |
| F04 | RCPT 451 temporary recipient | Temporary | No auto-switch | Retry per policy |
| F05 | Template missing | Not called | Not called | Hold/fix template |
| F06 | MIME invalid | Not called | Not called | No multiplied attempts |
| F07 | Attachment violates policy | Not called or rejected | Not called | Content correction |
| F08 | A content rejection 554 | Rejected | Not called | Audit policy |
| F09 | A From not authorized | Rejected | No blind switch | Fix sender permissions |
| F10 | A SMTP AUTH 535 | Rejected | No auto-failover | Hold credentials, alert |
| F11 | A TCP refused pre-submit | Unavailable | Allowed if eligible | One controlled B attempt |
| F12 | A DNS endpoint fails | Unavailable | Allowed if eligible | Do not suppress recipient |
| F13 | B disallowed for tenant | Unavailable | Not called | Hard eligibility stop |
| F14 | B From unverified | Unavailable | Not called | Do not bypass identity |
| F15 | B over quota | Unavailable | Not called | Defer, no tight loop |
| F16 | Provider A throttling | Temporary | Policy-dependent | Backoff/budget and honor provider |
| F17 | A final SMTP 250 | Accepted | Not called | SUBMITTED |
| F18 | A loses final reply after DATA | Unknown | Not called | Reconcile |
| F19 | A accepted then downstream hard bounce | Accepted → bounce | Not called | Delivery failed/suppression |
| F20 | A deferred then delivered | Accepted/deferred | Not called | No duplicate |
| F21 | A complaint after delivered | Delivered/complaint | Do not send marketing | Shared suppression |
| F22 | OTP expired between attempts | Temporary | Not called | EXPIRED |
| F23 | User unsubscribes before B attempt | Temporary | Not called | SUPPRESSED |
| F24 | Two workers pick B concurrently | Temporary | One attempt | Atomic claim/lease |
| F25 | Broker redelivers same notification | Multiple events | No multiplied sends | Idempotency key |
| F26 | Nested A and B retries | Temporary | Possible | Physical attempt budget |
| F27 | Exhausted maxAttempts | Repeated failures | No extra created | DEAD_LETTER with right reason |
| F28 | B accepted then late provider event | Accepted | No new route created | Submission/delivery separated |
| F29 | Unclassified MailException | Unclear | Not called | Hold/triage |
| F30 | A and B outage simultaneously | Unavailable | Unavailable | Durable outbox, no hot loop |
| F31 | Operator replay after fixing recipient | Right route | Only if permitted | New audited request |
| F32 | Provider A received yet DB update failed | Accepted | Not called | Unknown/reconciliation |
| F33 | A rejected partial multi-recipient | Mixed | Do not resend whole message | Recipient-level outcomes |
| F34 | Provider B region-restricted | Unavailable | Not called | Residency policy |
| F35 | Retry after provider recovery | Pending | Per route policy | Drain within quota |

### Key Testing Principles

**Count actual sends.** Asserting only final state `FAILED_PERMANENT` is insufficient if the adapter secretly tried B before writing state. Fake SMTP B or a mock/spy of B must confirm **zero submissions** when policy says stop.

**Never test with only one worker.** Races across instances, lease recovery, and broker redelivery can send the same notification through both providers.

**Never test only with exception mocks.** For SMTP RCPT/DATA cases, include integration tests using a real `JavaMailSenderImpl` against a programmable fake SMTP server controlling reply codes and phases. Mocks suit business guards yet do not verify exact transport mapping.

## 40. Eventual Consistency and Provider Event Ordering

Multi-provider systems easily encounter late-arriving events:

~~~text
09:00  A accepted notification N
09:00  Worker DB update temporarily fails
09:02  A webhook ACCEPTED arrives
09:03  Recovery worker reads stale outbox state
09:04  B is considered healthy
~~~

Reading stale state and failing over risks duplicates. You need:

- Durable event inbox and idempotent correlation.
- Projection updates per attempt/recipient.
- `SUBMISSION_UNKNOWN` state and terminal/accepted guards.
- State checks inside the transaction before claiming a B attempt.
- Never rely on webhook timeouts as proof "A did not send."

### Do Not Infer Delivery Failure from Silence

If no `delivered` arrives within 2 minutes, the provider may be queuing, webhooks may be delayed, or the remote MX may be deferring. **Never use absence of events as a trigger to auto-resend via B** once A accepted.

## 41. Data Controls and Privacy When Switching Providers

A notification can contain PII, addresses, order numbers, documents, or security links. Switching to B exposes content to an additional processor. Policy must check:

- Is provider B on the approved-vendor list?
- Do tenant/region rules permit transferring data to B?
- Is there a valid legal basis and sending purpose?
- Do B's credentials/transport enforce proper TLS?
- Does B meet retention/observability requirements?
- Are there content-category restrictions (marketing, OTP, invoices)?
- Are there differences between A's and B's From/domain authentication?

**Never trade off data policies for higher send rates.** An ineligible route must be rejected even during a P1 outage; when needed, activate an approved alternate channel rather than sending through an out-of-scope provider.

## 42. When to Pick Route B Up Front Instead of Trying A Then Failing Over

If B has a capability A lacks (message size, category, region, sender domain), **the router should pick B before calling A**. Do not generate a permanent failure on A just to discover B is the right fit.

Example:

~~~text
Notification type: INVOICE_WITH_ATTACHMENT
Estimated MIME size: 15 MiB

Provider A limit: 10 MiB
Provider B limit: 25 MiB
Both providers allowed by policy

Router -> choose B initially
No A attempt is needed
~~~

Limits and sizes are illustrative. Computing MIME size must include encoding/headers; providers enforce different size caps.

### Benefits

- Fewer rejected attempts and noisy logs.
- No wasted quota.
- Reduced reputation risk on A.
- Cleaner tracking and less retry complexity.
- Better transparency of routing decisions.

This is **capability-based routing**, not "failover on unsendable errors."

## 43. Logging Decisions Not to Fail Over

An operations team must be able to answer two questions:

1. Why was the message not sent?
2. Why did the system **not try provider B**, even though B is configured as backup?

Without decision logs, operators may mistake safe behavior for a router bug and flip on an "always fallback" flag.

### Illustrative Structured Log

~~~json
{
  "event": "mail_route_decision",
  "notificationId": "notif-1042",
  "attemptId": "attempt-a-1",
  "sourceProvider": "A",
  "candidateProvider": "B",
  "smtpPhase": "RCPT_TO",
  "failureKind": "INVALID_RECIPIENT",
  "smtpReplyCode": "550",
  "action": "STOP_PERMANENT",
  "fallbackAttemptCreated": false
}
~~~

Never write raw message bodies, OTPs, full recipient addresses, secrets, access tokens, or full SMTP transcripts into regular logs. When investigation needs details, use record IDs and a diagnostic/event store with access control, retention, and masking.

### Decisions Worth Recording Distinctly

- `FAILOVER_ALLOWED`: passed all eligibility checks, clear A outage.
- `FAILOVER_BLOCKED_PERMANENT`: recipient/content/permission error.
- `FAILOVER_BLOCKED_SUPPRESSION`: recipient not allowed to receive.
- `FAILOVER_BLOCKED_EXPIRED`: message expired.
- `FAILOVER_BLOCKED_UNKNOWN`: A may have accepted.
- `FAILOVER_BLOCKED_ROUTE`: B not eligible.
- `FAILOVER_BLOCKED_BUDGET`: B out of permits/quota.
- `FAILOVER_SKIPPED_ALREADY_ACCEPTED`: no further submission needed.
- `HOLD_FOR_REVIEW`: insufficient evidence to decide safely.

The names above are an application taxonomy, not built-in Spring Mail values.

## 44. Metrics to Detect Wrong Failover

If a system only measures "how many failovers succeeded," it can miss thousands of unnecessary sends to B. Track:

| Suggested metric | Goal |
| --- | --- |
| `mail_submission_attempts_total` | Count physical attempts per provider |
| `mail_failover_decisions_total` | Counts of ALLOW/STOP/HOLD/RECONCILE decisions |
| `mail_failover_executed_total` | Attempts that actually switched routes |
| `mail_failover_blocked_total` | Blocks broken down by reason family |
| `mail_permanent_failures_total` | Recipient/payload/policy errors |
| `mail_outcome_unknown_total` | Failures needing reconciliation |
| `mail_provider_auth_failures_total` | Distinguish account errors from recipient errors |
| `mail_provider_unavailable_total` | Measure per-route outages |
| `mail_provider_throttled_total` | Track capacity/provider policies |
| `mail_outbox_pending` | Backlog |
| `mail_outbox_oldest_age_seconds` | Age of oldest waiting message |
| `mail_suppression_decisions_total` | Send blocks by category/reason |
| `mail_duplicate_suspected_total` | Suspected duplicate submission events |
| `mail_rate_limiter_denied_total` | Denied permits, not SMTP failures |
| `mail_provider_delivery_events_total` | Delivered/deferred/bounced/complained if available |

These are suggested metric names for Micrometer/Actuator or your observability stack. They are **not provided completely out of the box by Spring Mail**.

### Actionable Alerts

| Signal | What may be wrong | Action |
| --- | --- | --- |
| B attempts rise alongside A hard bounces | Router may be failing over permanent errors | Pause auto-failover, inspect classifier |
| B attempts roughly match A 550s | May be trying B for invalid recipients | Inspect audit and suppression |
| A accepted yet B also sent same notification | Duplicate/unknown outcome guard broken | Isolate router, reconcile |
| Failover to B causes heavy B throttling | Backup quota insufficient | Throttle down, protect critical categories |
| B attempts despite tenant restriction | Route eligibility bug | Halt route B, investigate data handling |
| A AUTH errors trigger B flood | Broken account-level failure policy | Pause A, check secret and breaker |
| A complaint followed by marketing via B | Shared suppression bypassed | Block marketing, fix suppression pipeline |
| `UNCLASSIFIED` rises | Adapter losing error details or provider changed response | Investigate transport mapping before opening fallback |

### Do Not Use Recipients as Metric Labels

Full email addresses, notification IDs, and provider message IDs have huge cardinality and can leak PII. Use bounded labels such as `provider`, `category`, `failureKind`, `action`, and `region`; query specific messages via access-controlled logs.

## 45. Runbook: Discovering the System Auto-Retried B on Permanent Errors

An incident may surface via rising bounces, rising complaints, rapidly draining B quota, or customers reporting duplicate emails.

### Step 1 — Stop the Bleeding

1. Pause the **misbehaving automatic failover rule** without halting all transactional mail if isolatable by provider/category.
2. Keep the outbox intact so valid send requests are not lost.
3. Do not bulk-replay messages that already went through A/B.
4. Protect B's quota for remaining valid critical emails.
5. If consent or data-residency violations appear, trigger the corresponding security/compliance workflow.

### Step 2 — Scope the Incident

- Since when did the router begin creating B attempts?
- Did any deployment alter SMTP 550/554/535 mappings?
- Did a provider API change alter error schemas?
- Did a rule change `catch MailException` into unconditional fallback?
- Was a shared `status=FAILED` used for both permanent recipient and temporary provider errors?
- Are there notifications with `SUBMITTED` on A that also have B attempts?
- Did late A webhooks corrupt business state?
- Were specific categories/tenants disproportionately affected?

### Step 3 — Classify and Fix Root Cause

| Group | Where to fix |
| --- | --- |
| Invalid recipient | Validation/classifier/suppression |
| Template/MIME error | Render pipeline/data quality |
| Policy violation | Content, consent, compliance |
| AUTH/From permission | Secret/provider configuration |
| A accepted, B also sent | Outcome/attempt ledger, lease, router guard |
| Unknown outcome | Reconciliation/protocol instrumentation |
| Provider B ineligible | Route catalog/policy gating |
| B overload | Rate budget/reserved capacity |

### Step 4 — Handle Already-Sent Messages

Emails already SMTP-accepted cannot be reliably recalled. You must:

- Count attempts and accepted submissions per notification.
- Reconcile A/B provider events and recipient deliveries where available.
- Identify duplicates or unauthorized sends that occurred.
- Mark appropriate suppressions/complaints for future sends.
- Separate messages needing resend after address correction from already-accepted messages.
- Notify/remediate per business policy if recipients were impacted.

### Step 5 — Re-Enable Only After Evidenced Tests

Run fixtures for permanent recipient/content, accepted/unknown, provider outage, and B ineligible; confirm B is **not invoked** on blocked branches. Verify rate limiters and audits. Roll out via canary before opening cluster-wide traffic.

## 46. Runbook: Provider A Outage Yet B Receives No Emails

Not every case where B isn't called is a bug. Check the stop reason:

1. Was the notification `EXPIRED` or `SUPPRESSED`?
2. Did A have a prior accepted or unknown attempt?
3. Does B have sender/tenant/region permissions?
4. Is B healthy and within quota?
5. Was A's error truly a provider outage rather than permanent recipient/content?
6. Were `maxAttempts`/global budget exhausted?
7. Is A's circuit breaker OPEN or policy in HOLD?
8. Is an operator approval gate required before failing over this email category?

If B is ineligible, the path forward is **fixing route conditions/waiting for A** or using an approved channel—never stripping eligibility checks to rescue one message.

### Reducing Latency Without Bypassing Policy

Especially urgent notifications can:

- Use a pre-configured, periodically tested provider B.
- Route to B from the start under a high-priority policy.
- Have reserved throughput.
- Use an alternate channel such as in-app notifications if the product allows.

These should be designed **before an outage**. Never create an "emergency bypass" around consent, TLS, data residency, or provider account security mid-incident.

## 47. Common Design Mistakes

### 47.1. Catching Every MailException and Calling the Next Provider

Erases the distinction among recipient, content, credential, network, and unknown outcomes. Replace with a failure normalizer and decision policy.

### 47.2. Treating Every 5xx as Provider A Infrastructure Failure

Many 5xx codes indicate the current request is invalid. You need the SMTP command and enhanced status.

### 47.3. Treating Every 4xx as Safe for Failover

A 4xx may reflect throttling on the remote recipient domain; switching providers may not help and can increase load.

### 47.4. Sending via B After Not Seeing a Delivered Event

Provider A may have accepted and be queuing; absence of events does not prove failure.

### 47.5. Lacking a SUBMISSION_UNKNOWN State

Losing the final reply after DATA can cause duplicates if every exception is treated as "not submitted."

### 47.6. Lacking Shared Suppression

Complaints or hard bounces on A fail to stop B from continuing to send, harming sender reputation and recipient privacy.

### 47.7. Bounding Attempts Only Inside Each Adapter

Outbox × A retries × B retries × broker redelivery multiplies SMTP calls unexpectedly. Enforce a global attempt budget.

### 47.8. Not Persisting Route Decisions

Impossible to explain why failover occurred, why sending stopped, or prove a message did not go through a disallowed provider.

### 47.9. Not Revalidating Before B Sends

While A failed, an OTP may expire or a recipient may unsubscribe. Checking only at enqueue is insufficient.

### 47.10. Provider B Lacking From Authorization

AUTH with B may succeed while MAIL FROM gets rejected; verify identity/DMARC alignment.

### 47.11. Letting B Process Disallowed Data

Data-processing rights and regions are hard constraints, not soft router preferences.

### 47.12. Failing Over When B Lacks Quota

During an A outage, B can get buried by thousands of jobs and fail too; rate limiters/reserved budgets must apply across all routes.

### 47.13. Conflating Account Errors with Recipient Errors

SMTP AUTH 535 on A does not prove every recipient address is bad. Never suppress customers because of a credential failure.

### 47.14. Conflating Recipient Errors with Provider Outages

RCPT 550 5.1.1 must not open A's circuit breaker or shift the whole message to B.

### 47.15. Ignoring Partial Acceptance

With multi-recipient messages, one recipient may already be accepted; resending the whole message via B causes duplicates.

### 47.16. Confusing Bounce Events with Submit Failures

A downstream hard bounce after acceptance is not a `JavaMailSender.send()` failure to retry on B.

### 47.17. Switching Providers to Bypass Content Policy

Can violate provider rules and abuse policies; fix content/consent instead of hunting for workarounds.

### 47.18. Using `Message-ID` as an Exactly-Once Guarantee

Message-ID helps correlation, not guaranteeing every mailbox drops duplicates.

### 47.19. Replaying Every FAILED Job After Fixing a Route

`FAILED` may mix permanent recipient, expired, and unknown failures. Filter and reconcile before replaying.

### 47.20. Putting Raw SMTP Exceptions and Recipients into Metric Labels

Can leak PII/secrets and blow up cardinality. Normalize and sanitize.

## 48. Pre-Deployment Failover Design Checklist

### Data and Business Rules

- [ ] Notification has a durable idempotency key.
- [ ] Recipient is canonicalized and validated before submit.
- [ ] Consent, unsubscribes, and complaints are checked from trusted sources.
- [ ] Suppression applies across all providers.
- [ ] Template/MIME/attachments are verified before dispatch.
- [ ] Expiry of OTPs/reset links/campaigns is rechecked before every attempt.
- [ ] Separate rules exist for marketing, transactional, and security emails.

### Transport and Policy

- [ ] Clear boundary between A accepted, A refused, and A outcome unknown.
- [ ] Classifier uses SMTP phase/enhanced status when present, not message strings alone.
- [ ] Permanent recipient/content failures lead to stop/hold, never choosing B.
- [ ] Provider account failures are held/investigated; no automatic catch-all fallback.
- [ ] Switch to B only when the fault is route-specific and B is eligible.
- [ ] B is approved for From, category, tenant, region, content, and quota.
- [ ] Never retry once A accepted or when outcome is unknown and unreconciled.
- [ ] Never switch to B to bypass content-policy/complaints/suppression.

### Workers, Transactions, and Resources

- [ ] Business transaction persists durable outbox before sending.
- [ ] Claim uses transactions/leases so no two workers send the same notification.
- [ ] Every SMTP attempt records provider and status.
- [ ] Retry/failover shares a global attempt budget and deadline.
- [ ] Backoff+jitter, rate limiters, and max concurrent SMTP sends are enforced.
- [ ] Never sleep inside database transactions or maintain unbounded executor queues.
- [ ] Replay/dead-letter passes through the same pre-send checks and limiters.
- [ ] `SUBMISSION_UNKNOWN` has a defined reconciliation workflow.

### Observability and Operations

- [ ] Log decisions not to fail over with normalized reasons.
- [ ] Metrics separate physical attempts, route decisions, and permanent errors.
- [ ] Provider event processor prevents duplicates/out-of-order regressions.
- [ ] Alert when B attempts climb alongside A permanent failures.
- [ ] Runbooks exist for A outages/B ineligibility/account failures.
- [ ] Canary and rollback/roll-forward plans exist.
- [ ] Never leak secrets/PII via logs, metrics, or provider debug traces.
- [ ] Tests prove B is **not** called on stop branches.

A checklist is a set of design criteria. Checking a box in documentation never replaces testing or auditing the live system.

## 49. Phased Rollout Process

An engineering team can introduce the new policy in order:

1. **Inventory sending paths:** web requests, outbox workers, retry schedulers, manual resends, campaigns, bulk imports, and legacy provider fallbacks.
2. **Define failure taxonomy:** recipient, payload, policy, provider account, provider infrastructure, unknown outcome.
3. **Normalize transport adapters:** both A and B emit `NormalizedMailFailure` without losing phase/provider metadata.
4. **Add pre-send guards:** expiry, consent, suppression, MIME, sender/tenant eligibility.
5. **Persist state and decision audits:** one notification, multiple attempts, route decisions, and stop reasons.
6. **Update router:** remove catch-all failover; switch to decision policy.
7. **Add unit tests:** permanent failures, A outage, B ineligible, accepted, and unknown.
8. **Add integration tests:** fake SMTP A returning 550/451/554, B counting connections, outbox database, and multi-worker races.
9. **Roll out to canary:** initially observe only "would fail over" without real sends, then enable policy in a controlled scope.
10. **Monitor metrics:** stop/permanent rates, B attempts, backlog, latency, suspected duplicates, and complaints.
11. **Expand rollout:** gradually widen approved tenant/category scopes.
12. **Standardize runbooks:** on-call engineers know when to stop, fix, retry, reroute, and reconcile.

### Do Not Use Dry-Run to Send Two Copies

"Shadow evaluation" should run only the **route decision function** and log `wouldFailover=true/false`, without calling B for real. If shadow mode actually sends via B, that is a real send carrying duplicate risk. Pay special attention when testing new rules.

### Safe Feature Flags

An `enableFailover` flag should only govern whether failover runs on **eligible** branches. It must never disable hard guards. For example:

~~~text
if validation fails:
    STOP  // applies even if enableFailover=true

if accepted or outcome unknown:
    STOP / RECONCILE

if provider-specific temporary failure:
    if enableFailover and backupEligible:
        schedule backup
    else:
        defer or retry primary safely
~~~

Never build `forceFailoverIgnoringPolicy=true` as a generic incident-rescue switch.

## 50. Self-Check Questions

**1. Why shouldn't you catch every `MailException` and send via provider B?**

Because `MailException` wraps very different failures: nonexistent recipient, bad template, bad credentials, TLS/DNS outage, or uncertain submission outcome. Only certain A-specific infrastructure faults can be improved by switching routes.

**2. What if A returns `550 5.1.1` mailbox does not exist while B is healthy?**

Do not send via B. Record invalid recipient per evidence, stop sending, and apply suppression/address verification per policy.

**3. Should you switch to B when A returns `535` SMTP AUTH?**

Not automatically. Check A's credentials/account, security incidents, and B's preconditions. If B is a valid approved standby route, a controlled policy switch may occur; by default, hold to fix configuration.

**4. Is 4xx always safe for failover?**

No. A 4xx can reflect a downstream recipient/domain issue that B will also hit. Classify phase and root cause.

**5. Is 5xx always permanent across all providers?**

No. Some 5xx replies reflect A-specific account/configuration issues; yet they do not automatically authorize B either. Distinguish scope and check route eligibility.

**6. If A accepted yet no `delivered` event arrived, should you use B for speed?**

No. A may be queuing or the remote MX may be deferring. No `delivered` event yet does not prove the relay never received the message.

**7. Why not fail over after losing the final SMTP response at DATA?**

Because A may have accepted; sending via B creates duplicates. Use `SUBMISSION_UNKNOWN` and reconcile.

**8. Can the same `Message-ID` guarantee two providers won't create duplicates?**

No. `Message-ID` helps tracing, yet SMTP provides no exactly-once guarantee based on that header.

**9. Should a hard bounce from A trigger retrying on B?**

No for a reliable hard bounce confirming a nonexistent mailbox. Handle recipient cleanup and suppression instead of rerouting.

**10. Does a `deferred` event from A mean the app must send a new copy via B?**

Normally no: A already accepted and may be retrying to the remote MX itself. Wait for outcome/downstream status.

**11. Can you switch to B to get around content blocked by A's policy?**

No. Failover serves availability for **valid** requests, not evading content/abuse policies.

**12. Must consent be rechecked before attempt B?**

Yes. The recipient may have unsubscribed or complained between A's failure and B's attempt.

**13. What if B has a higher quota and supports larger attachments than A?**

Select B via capability-based routing before sending, provided content is valid and B is approved—do not intentionally fail on A just to probe providers one by one.

**14. Should each SMTP adapter keep its own isolated suppression list?**

Insufficient. The application needs a shared decision policy with proper scope so complaints/hard bounces are not bypassed when routes change.

**15. If a worker dies after A accepted yet before updating the database, can B send?**

Not automatically. You need an attempt ledger, unknown-outcome state, and reconciliation to avoid duplicates.

**16. Should `maxAttempts` count both A and B?**

Keep a combined budget at the notification level alongside per-provider caps. Count physical SMTP/API submissions, not merely dispatcher calls.

**17. Why must tests verify B receives zero connections?**

Because a test asserting only final `FAILED_PERMANENT` can miss that the adapter secretly tried B before writing status. Observe real transport calls.

**18. When A's SMTP AUTH fails due to secret rotation, what should happen?**

Halt A retry storms, verify secret version/credentials, update the sender, and canary-test. Consider B only if fully eligible under a valid routing decision.

**19. A tenant bars using B while A has an outage—can the region constraint be dropped?**

No. Data residency/contracts are hard constraints, never automatically voided by outages.

**20. What criteria confirm failover is safe?**

Failure is genuinely route-specific, A never accepted, no unknown outcomes exist, notification remains valid, B is authorized/healthy/has quota, attempts stay within budget, and every decision is audited.

## Conclusion

**Not failing over to another provider on unsendable errors is a foundational rule for safe multi-provider email systems.** Spring Framework Mail submits email via `JavaMailSender`, yet the application itself must normalize SMTP/Jakarta Mail errors, check notification states, decide routes, and enforce retry caps. Invalid recipients, broken payloads/templates/MIME, withdrawn consent, expired messages, or policy/content rejections do not become valid by switching from A to B. Conversely, a genuine infrastructure outage on A can justify using B **only when** B is approved, has sender permissions, matches data boundaries, has quota, and the previous attempt definitely did not accept.

Separate submission from delivery; distinguish explicit refusals from `SUBMISSION_UNKNOWN`; store one notification with multiple attempt records; enforce shared suppression, transactions/leases, and a global attempt budget. Tests must prove **B is never called** for permanent errors, accepted/unknown outcomes, and eligibility failures, while still allowing controlled failover when A is genuinely unavailable. With clear logs, metrics, and runbooks, systems gain availability **without duplicating emails, bypassing policies, or endlessly retrying ineligible messages**.
