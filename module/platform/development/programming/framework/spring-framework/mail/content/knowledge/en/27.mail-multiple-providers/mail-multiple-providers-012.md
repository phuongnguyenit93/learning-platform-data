# Sender Source Reporting in Observability

When a Spring Framework Mail system sends email through **multiple SMTP providers**, the question "which source sent this email?" carries multiple meanings. An email may originate from a business service, use a brand's `From` address, route to a primary provider, and fail over to a backup provider after an error. Recording only "sent successfully" or a raw email count leaves operations unable to tell which system generated the load, which provider actually handled delivery, where failures happened, or how failover affected outcomes.

**Sender source reporting in observability** is the structured instrumentation of **business source**, **SMTP provider**, **account/route**, **send attempt**, **client-observed outcome**, and **final mail event state**. Its purpose is to support diagnostics, reliability evaluation, traffic balancing, provider incident detection, and retry reconciliation without exposing private information.

In this lesson, an email may flow through these stages:

~~~text
Order / Identity / Billing service
                 |
                 v
          Durable mail event
                 |
                 v
           Routing policy
              /       \
             /         \
     Provider A       Provider B
         |                 |
         v                 v
  JavaMailSender A    JavaMailSender B
         |                 |
         +---- attempt ----+
                 |
                 v
       Outcome and telemetry
                 |
                 v
      Outbox / retry / delivery
~~~

Core principles:

- Never equate **business source**, **provider**, and **`From` address**.
- Every **SMTP attempt** must record the exact provider and account actually used.
- Separate **route selected**, **send attempted**, **send returned successfully**, **failed**, and **unknown outcome**.
- On failover, preserve history for both the prior and subsequent providers.
- Separate **attempt metrics** from **unique mail events**.
- Use **metrics for aggregation**, **structured logs for individual events**, and **traces for execution flow**.
- Never put recipient email addresses, Subject, body, tokens, passwords, or event IDs into metric labels.
- A successful `send` call does not prove inbox delivery or user reading.
- Telemetry must inform operational decisions rather than merely filling dashboards.

## 1. What Concepts Can "Sender Source" Refer To?

In a multi-provider system, define each entity explicitly.

| Concept | Example | Question Answered |
| --- | --- | --- |
| **Logical source** | order-service, identity-service | Which business service requested sending? |
| **Mail kind** | order_confirmation, password_reset | Which category of notification is this? |
| **Provider identity** | smtp_provider_a, smtp_provider_b | Which SMTP provider executed it? |
| **Transport account** | provider_a_transactional | Which account/auth configuration was used? |
| **Route role** | primary, backup | What role did the provider serve at selection time? |
| **Endpoint/region** | apac_submission | Which region received the connection? |
| **Visible From** | orders@example.org | Which identity does the recipient see? |
| **Envelope sender** | Provider-issued bounce address | What does `MAIL FROM`/return-path serve? |
| **DKIM domain** | d=example.org | Which domain signs the email? |
| **Outbox worker** | mail-worker-pool | Which worker process executed the attempt? |

One logical source may send through multiple SMTP providers. One provider may serve multiple business sources, accounts, or `From` identities.

### 1.1. From Does Not Necessarily Reveal the Provider

~~~text
From: Orders <orders@example.org>
~~~

A message carrying this `From` header can be sent via either provider A or provider B when both are properly configured and authorized. Inspecting the `From` header alone cannot tell you which provider received the SMTP connection.

Likewise, the **`From` header**, **`MAIL FROM`**, SMTP AUTH username, and DKIM signing domain can all differ. Never collapse them into one ambiguous `sender` field.

### 1.2. Use at Least Two Attribution Fields

- **source_alias**: the business service creating the send intent.
- **provider_alias**: the SMTP provider actually receiving the attempt.

Extra fields like **account_alias**, **mail_kind**, **route_reason**, or **region_alias** should only be added when tied to concrete operational questions.

### 1.3. Provider Identity Differs From Route Role

Today provider A may be primary; tomorrow it may switch to backup. Using the string **`primary`** as a provider identity and later remapping it mixes historical metrics across two different providers.

Maintain both a **stable `provider_alias`** and a **`route_role`** such as `primary`/`backup`.

## 2. Why Must Each Attempt Be Tracked?

A mail event may go through:

~~~text
mailEventId = event-1842
source = order-service
kind = order_confirmation
          |
          v
Attempt 1: provider_a
          |
          +-- Read timeout
          |
          v
Evaluate retry/failover policy
          |
          v
Attempt 2: provider_b
          |
          +-- send() returns normally
~~~

Recording only the final provider erases provider A's failure from history. Recording only the first provider misattributes provider B's success.

**The fundamental measurement unit for SMTP transport is one attempt against a specific provider.** Every attempt must link back to the original mail event.

### 2.1. Event, Attempt, and Recipient Are Not Equivalent

- **Mail event** is the business send intent.
- **Attempt** is one transport execution.
- **Recipient** is a destination address in the SMTP envelope.
- **Provider selection** is a routing decision that might not yet produce an attempt.

One event can span multiple attempts. One attempt can address multiple recipients in batch or multi-recipient messages. Never take one `send` counter and label it unique emails.

### 2.2. Use Two Separate Identifiers

~~~text
mailEventId = mail-1842
attemptId   = mail-1842-attempt-02
provider    = smtp_provider_b
~~~

Event ID supports business reconciliation and retries. Attempt ID supports analyzing a single call. Both belong in access-controlled logs and traces, yet **must never be metric tags** because of extreme cardinality.

### 2.3. Do Not Erase Failed Attempts After Event Success

A business event may ultimately succeed via backup, yet provider A still produced a real failure. Eventual business success does not rewrite per-provider quality history.

## 3. Sending Architecture With Multiple JavaMailSenders

Spring provides the **`JavaMailSender`** interface to create `MimeMessage` instances and send over mail transport. In multi-provider applications, separate **`JavaMailSenderImpl`** beans exist with dedicated SMTP hosts, accounts, and security settings.

~~~text
Mail event
    |
    v
MailRouter.select(...)
    |
    +-- RouteDecision(provider A, account A)
    |
    +-- RouteDecision(provider B, account B)
    |
    v
Sender registry
    |
    +-- account A -> JavaMailSenderImpl A
    +-- account B -> JavaMailSenderImpl B
    |
    v
send selected MimeMessage
~~~

### 3.1. Do Not Mutate One Shared Sender Bean Host Per Send

Mutating properties on a shared singleton `JavaMailSenderImpl` across threads risks mixing providers and credentials. Configure independent senders and look them up through a registry instead.

### 3.2. Never Take SMTP Hosts Directly From Requests

Routers must select from a **managed allowlist of routes/providers/accounts**. Connecting to user-supplied hostnames creates SSRF risks or unintended infrastructure access.

### 3.3. Multiple Beans Require Explicit Injection Design

When a project defines multiple `JavaMailSender` beans, use explicit names, qualifiers, or a registry. Spring Boot conditionally auto-configures a single sender, but does not automatically wire your application's multi-provider router, failover, or metrics.

## 4. Routing Decisions Need a Reason

Provider selection can depend on:

- Email category: security, transactional, marketing.
- Tenant/branding and authorized `From` domain.
- Geographic region.
- Provider health.
- Quotas or rate limits.
- Cost/capacity policies.
- Manual overrides during incidents.
- `SMTPUTF8` support or attachment size limits.
- Retry policy following a classified failure.

A route decision can be modeled as:

~~~java
public record MailRouteDecision(
        String sourceAlias,
        String providerAlias,
        String accountAlias,
        String fromAddress,
        String routeRole,
        String routeReason,
        String policyVersion
) {}
~~~

### 4.1. routeReason Must Be a Stable Code

Examples:

~~~text
tenant_default
kind_policy
region_policy
provider_unhealthy
rate_limit_fallback
capacity_policy
manual_override
failover_after_transient_error
~~~

Never use raw exception messages or user input strings as `routeReason`.

### 4.2. policyVersion Explains Historical Choices

The route chosen today may differ after a policy update. Storing **`policyVersion`** in structured logs or attempt records lets operators audit what drove the decision at execution time instead of reverse-engineering from current configuration.

### 4.3. Selected Route Does Not Guarantee Invocation

If the router selects provider A but message preparation fails due to a missing resource or invalid address, no SMTP attempt occurs. Report **route selection** separately from **send invocation**.

## 5. Distinguish Observability Milestones

A system can record milestones such as:

~~~text
MAIL_EVENT_CREATED
        |
        v
ROUTE_SELECTED
        |
        v
MIME_PREPARING
        |
        v
MIME_READY
        |
        v
SMTP_ATTEMPT_STARTED
        |
        +-- SUBMIT_RETURNED_OK
        |
        +-- SUBMIT_FAILED
        |
        +-- UNKNOWN_OUTCOME
        |
        v
OUTBOX_STATE_UPDATED
~~~

This is an illustrative state schema, **not built-in enums provided by Spring Mail**.

### 5.1. Selected Differs From Attempted

Validation or rendering failures can occur after route selection and before sending. Counting attempts at selection time overstates actual transport calls.

### 5.2. Attempted Differs From Accepted

Calling `JavaMailSender.send(...)` does not guarantee the SMTP server accepted the message. Record the result only after the call finishes or throws.

### 5.3. Send Returned Normally Differs From Delivered

`JavaMailSender.send` returns `void` when the call finishes normally. This typically signals transport submission completed per SMTP replies. It **does not** confirm Inbox placement, absence of spam filtering, or recipient opens.

### 5.4. Exceptions Can Yield Unknown Outcomes

If a connection drops after `DATA`, the server may have accepted the message while the client never received the reply. Model **`UNKNOWN_OUTCOME`** explicitly rather than assuming "unsent".

## 6. Three Complementary Observability Layers

| Layer | Goal | Examples |
| --- | --- | --- |
| **Metrics** | Counts, ratios, trends, latency, SLOs | Attempts by provider/outcome |
| **Structured logs** | Investigating a specific event/attempt | Event ID, attempt ID, route decision |
| **Traces** | Understanding relationships and step timings | Business → outbox → route → SMTP |

### 6.1. Metrics Answer Aggregate Questions

For example: which provider has a high failure ratio, what is p95 submit-call duration, or has failover rate climbed?

### 6.2. Logs Answer Who, When, and Why

Structured logs connect an event to its attempt, provider, and error code—without printing email bodies, recipients, or credentials.

### 6.3. Traces Link Synchronous and Asynchronous Steps

In an outbox, workers may run minutes after the originating request. Propagate trace context or correlation appropriately; do not expect tracing to cross a database queue automatically.

## 7. Log Schema for Route Selection

JSON example:

~~~json
{
  "event": "mail.route.selected",
  "mailEventId": "mail-1842",
  "attemptId": "mail-1842-2",
  "sourceAlias": "order-service",
  "mailKind": "order_confirmation",
  "providerAlias": "smtp_provider_b",
  "accountAlias": "backup_transactional",
  "routeRole": "backup",
  "routeReason": "failover_after_transient_error",
  "policyVersion": "v7"
}
~~~

Field names are illustrative conventions; establish one consistent schema across logs, traces, outbox records, and dashboards.

### 7.1. Omit Recipients From Route Logs Unless Necessary

To inspect the recipient, use `mailEventId` against an access-controlled store. Email addresses are often personal data and expand retention/compliance scope for log collectors.

### 7.2. Separate Business Source and Provider

Logging `source=order-service` without the provider hides which SMTP provider handled it. Logging only the provider hides which traffic flow caused errors.

### 7.3. Never Log Passwords or Tokens

An account alias is a logical identifier, not a credential. Secrets stay in secret managers/runtime configuration, never in metrics or logs.

## 8. Log Schema When an Attempt Finishes

~~~json
{
  "event": "mail.smtp.attempt.finished",
  "mailEventId": "mail-1842",
  "attemptId": "mail-1842-2",
  "sourceAlias": "order-service",
  "mailKind": "order_confirmation",
  "providerAlias": "smtp_provider_b",
  "accountAlias": "backup_transactional",
  "phase": "smtp_submit",
  "outcome": "success",
  "durationMs": 910,
  "errorCategory": "none"
}
~~~

A failed attempt can log:

~~~json
{
  "event": "mail.smtp.attempt.finished",
  "mailEventId": "mail-1842",
  "attemptId": "mail-1842-1",
  "sourceAlias": "order-service",
  "providerAlias": "smtp_provider_a",
  "accountAlias": "primary_transactional",
  "phase": "after_data",
  "outcome": "failure",
  "errorCategory": "timeout_unknown",
  "durationMs": 10025
}
~~~

### 8.1. Be Careful With Phase

Not every exception reveals the exact SMTP stage. Without reliable evidence, record **`phase=unknown`** rather than guessing `after_data` solely from timeout duration.

### 8.2. Caller-Observed Result

Set **`outcome=success`** when `send` returns normally and **`outcome=failure`** when it throws. When outcome certainty is ambiguous, persist **`deliveryUncertainty=unknown`** or a separate outbox **`UNKNOWN_OUTCOME`** state.

### 8.3. Never Use Full Exception Messages as Tags

Provider diagnostic text can include recipients, hosts, policies, or unbounded strings. Stick to a bounded **`errorCategory`** and sanitized SMTP reply/enhanced codes.

## 9. Core Metrics for Multiple Providers

| Illustrative Metric | Type | Useful Labels | Purpose |
| --- | --- | --- | --- |
| **mail.route.selections** | Counter | source, provider, reason | Count routing decisions |
| **mail.smtp.submit.attempts** | Counter | source, provider, outcome | Count completed `send` calls |
| **mail.smtp.submit.call.duration** | Timer | provider, kind, outcome | Measure caller-side latency |
| **mail.smtp.submit.failures** | Counter | provider, error_category | Classify failures |
| **mail.smtp.failovers** | Counter | from_provider, to_provider, reason | Count route switches |
| **mail.message.prepare.failures** | Counter | source, kind, category | Pre-SMTP failures |
| **mail.outbox.pending** | Gauge | priority/kind | Backlog size |
| **mail.outbox.queue.delay** | Timer | source/kind | Worker queue wait latency |
| **mail.event.terminal_failures** | Counter | source, kind | Permanently failed send intents |
| **mail.event.submit_completed** | Counter | source, final_provider | Events finishing submission |

Applications must **explicitly instrument** these metrics. Do not assume adding Spring Boot Actuator automatically produces full multi-provider routing metrics.

### 9.1. Do Not Attach Every Label to Every Metric

Giving every metric `source`, `provider`, `account`, `tenant`, `kind`, `region`, `reason`, `outcome`, and `errorCategory` explodes time-series combinations across their Cartesian product. Keep only labels that answer each metric's specific question.

### 9.2. Attempts and Unique Events Have Different Denominators

An event retried three times produces three attempts. Unique send intents must be measured via outbox state or dedicated completion counters, never inferred from attempts.

### 9.3. Health Needs Its Own Signal

Proclaiming a provider "healthy" requires real probes, rolling error rates, or circuit breaker states. Merely having a `JavaMailSender` bean does not prove the endpoint or SMTP AUTH works.

## 10. Configuring Multiple JavaMailSenderImpl Beans

Example configuring two SMTP STARTTLS senders:

~~~java
import java.util.Properties;

import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SenderFactory {

    public JavaMailSenderImpl startTlsSender(
            String host,
            int port,
            String username,
            String password
    ) {
        JavaMailSenderImpl sender =
                new JavaMailSenderImpl();

        sender.setHost(host);
        sender.setPort(port);
        sender.setProtocol("smtp");
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties props = new Properties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(props);

        return sender;
    }
}
~~~

The application creates independent instances from injected configuration and secrets:

~~~java
JavaMailSender senderA =
        factory.startTlsSender(
                primaryHost,
                primaryPort,
                primaryUsername,
                primaryPassword
        );

JavaMailSender senderB =
        factory.startTlsSender(
                backupHost,
                backupPort,
                backupUsername,
                backupPassword
        );
~~~

`primaryHost`, `primaryPort`, and username/password come from runtime configuration, never hardcoded in source.

### 10.1. Implicit TLS Providers Need the Matching Mode

The snippet above targets a STARTTLS endpoint. When a provider uses implicit TLS on the appropriate submission port (commonly 465), configure **`mail.smtp.ssl.enable=true`** properly rather than enabling conflicting modes indiscriminately.

### 10.2. Build a Registry With Clear Account Aliases

~~~java
Map<String, JavaMailSender> sendersByAccount =
        Map.of(
                "primary_transactional", senderA,
                "backup_transactional", senderB
        );
~~~

The router returns an account alias, and the adapter looks up the sender. The application owns this mapping—never accept arbitrary account selection from requests.

### 10.3. Keep Account Names Stable

One provider can serve multiple accounts (transactional, security, marketing). An AUTH error on one account does not prove the entire provider is down.

## 11. Mail Job and Route Decision DTOs

Data definitions:

~~~java
public record OutboundMailJob(
        String mailEventId,
        String sourceAlias,
        String mailKind,
        String recipient,
        String subject,
        String plainText
) {}

public record MailRouteDecision(
        String sourceAlias,
        String providerAlias,
        String accountAlias,
        String fromAddress,
        String routeReason
) {}
~~~

**`mailEventId`** identifies one send intent. **`MailRouteDecision`** captures the decision for one attempt. Do not bind a fixed provider when creating the event if retries/failover can switch providers.

### 11.1. From Must Be an Authorized Configuration

Arbitrary requests must not specify arbitrary `From` domains or SMTP accounts. Routing and validation must ensure the chosen route is authorized to send for that identity.

### 11.2. Never Pass Entire DTOs to a Logger

`OutboundMailJob` contains `recipient`, `subject`, and `plainText`. Logging the whole object risks leaking sensitive business content.

### 11.3. One Event May Reuse the Same Content Snapshot Multiple Times

In an outbox, payload content should follow a snapshot policy. Failing over to another provider should not necessarily re-render templates while content remains valid.

## 12. Sending Adapter Recording Accurate Provider Attribution

An illustrative adapter using **`MeterRegistry`** and `JavaMailSender` per attempt:

~~~java
import java.util.Map;
import java.util.Objects;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MultiProviderMailSubmitter {

    private static final Logger log =
            LoggerFactory.getLogger(
                    MultiProviderMailSubmitter.class
            );

    private final Map<String, JavaMailSender> senders;
    private final MeterRegistry registry;

    public MultiProviderMailSubmitter(
            Map<String, JavaMailSender> senders,
            MeterRegistry registry
    ) {
        this.senders = Map.copyOf(senders);
        this.registry = Objects.requireNonNull(registry);
    }

    public void submit(
            OutboundMailJob job,
            MailRouteDecision route,
            String attemptId
    ) {
        JavaMailSender sender =
                senders.get(route.accountAlias());

        if (sender == null) {
            throw new IllegalArgumentException(
                    "Unknown SMTP account alias"
            );
        }

        MimeMessage message =
                sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message,
                            false,
                            "UTF-8"
                    );

            helper.setFrom(route.fromAddress());
            helper.setTo(job.recipient());
            helper.setSubject(job.subject());
            helper.setText(job.plainText(), false);

        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Cannot prepare mail message",
                    ex
            );
        }

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            sender.send(message);
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.smtp.submit.call.duration",
                            "source", route.sourceAlias(),
                            "provider", route.providerAlias(),
                            "account", route.accountAlias(),
                            "outcome", outcome
                    )
            );

            registry.counter(
                    "mail.smtp.submit.attempts",
                    "source", route.sourceAlias(),
                    "provider", route.providerAlias(),
                    "account", route.accountAlias(),
                    "outcome", outcome
            ).increment();

            log.info(
                    "mail.smtp.attempt.finished eventId={} attemptId={} "
                  + "source={} provider={} account={} outcome={}",
                    job.mailEventId(),
                    attemptId,
                    route.sourceAlias(),
                    route.providerAlias(),
                    route.accountAlias(),
                    outcome
            );
        }
    }
}
~~~

### 12.1. Instrumentation Placement Matters

- The sender is resolved by the route's account alias.
- The MIME message is created by that exact sender.
- The timer starts immediately before `send`.
- The counter increments whether `send` returns or throws.
- The provider tag reflects the **actual sender's provider**.
- Preparation failures before `send` are not counted as SMTP attempts.

### 12.2. Logs and Metrics Serve Different Goals

Structured logs carry **`eventId`/`attemptId`** to trace individual sends. Metrics use only bounded aliases and `outcome` for aggregation—never add `eventId` to `registry.timer` or counters.

### 12.3. Recording Caller Outcome Is Not Root-Cause Classification

This adapter records only caller-observed **`success`/`failure`**. Orchestration layers must inspect exception chains, SMTP replies, phases, and unknown outcomes to decide retries/failover. Catching `RuntimeException` alone never proves whether the relay accepted the message.

### 12.4. Watch Out for Runtime Errors During Render/Prepare

If `helper` throws before `Timer.start`, no SMTP attempt runs. That matches defining the metric around `send` calls; track preparation failures in a separate counter.

### 12.5. Does Not Replace Transactions/Outbox

The adapter does not persist event states, orchestrate retries, or prevent duplicates; those responsibilities belong to the outbox/coordination service.

## 13. Metrics for Route Selection

A router can record:

~~~java
MailRouteDecision decision =
        router.choose(
                job.sourceAlias(),
                job.mailKind()
        );

registry.counter(
        "mail.route.selections",
        "source", decision.sourceAlias(),
        "provider", decision.providerAlias(),
        "reason", decision.routeReason()
).increment();
~~~

**`router`** is an application-built component.

### 13.1. Route Selection Count Differs From Attempt Count

- Router picks a provider, then validation fails → selection rises while attempts stay unchanged.
- Worker stops before calling `send` → selected without an attempt.
- Retry re-evaluates routing → one event yields extra selections.
- Batches send multiple messages → `send` calls and events can diverge.

Never force both counters to stay equal.

### 13.2. Never Treat Selected Provider as Final Provider

During failover, the initially selected provider differs from the final one. Persist decision history instead of overwriting one field.

### 13.3. routeReason Must Come From an Allowlist

Setting reason to `exception.getMessage()` spawns unbounded metric series and leaks sensitive details. Keep a small taxonomy and log details on access-restricted channels.

## 14. Attribution During Failover

Suppose:

~~~text
mailEventId=mail-1842

Attempt #1
  source=order-service
  provider=smtp_provider_a
  account=primary_transactional
  result=failure
  category=temporary_smtp

Attempt #2
  source=order-service
  provider=smtp_provider_b
  account=backup_transactional
  routeReason=failover_after_transient_error
  result=success
~~~

Counts:

~~~text
SMTP attempts provider A, failure: +1
SMTP attempts provider B, success: +1
Failover A -> B: +1
Unique mail event submit completed: +1
~~~

### 14.1. Never Credit Two Successes

Eventual success via B does not convert A's failed attempt into a success. Provider quality reporting must reflect each attempt accurately.

### 14.2. Do Not Lose the Initial Provider

If the outbox only keeps `lastProviderAlias`, maintain an attempts table or durable structured logs for history. `lastProviderAlias` helps current status queries yet is insufficient for failure analysis.

### 14.3. Record Failover Reasons

Example codes:

~~~text
connection_failure
provider_unhealthy
rate_limit
timeout_before_data
manual_override
quota_exhaustion
~~~

These reason codes are application-defined. Never allow failover purely because a category contains `timeout`; evaluate the SMTP phase and duplicate risk first.

## 15. Unknown Outcomes After DATA

A hazardous scenario:

~~~text
Client                           SMTP relay
  |--- MAIL FROM -------------------->|
  |<-- 250 ---------------------------|
  |--- RCPT TO ---------------------->|
  |<-- 250 ---------------------------|
  |--- DATA / message bytes -------->|
  |       connection lost            |
  |      final reply unknown         |
~~~

The relay may have accepted the message while the client never received the reply. Automatically switching to provider B and resending can deliver **two identical emails**.

### 15.1. Do Not Default Failures to Unsent

An exception only tells you the sender call did not finish normally—it does not prove the server refused the message.

### 15.2. Outbox States Must Reflect Certainty

Use **`UNKNOWN_OUTCOME`** or a dedicated flag for attempts that may have succeeded. Reconcile or apply cautious retry policies.

### 15.3. Dedicated Metric for Unknown Outcomes

An illustrative counter:

~~~text
mail.smtp.submit.unknown_outcomes{
  provider="smtp_provider_a"
}
~~~

Avoid lumping everything into a generic failure rate and triggering blind failover.

### 15.4. Exactly-Once Is Not Guaranteed by Cache or Outbox

An outbox preserves send intents durably and coordinates business idempotency, yet SMTP submission and database commits cannot share one atomic transaction. A duplicate window exists.

## 16. Which Failures Are Safe to Route to Backup?

| Failure Category | Example | Automatic Failover? |
| --- | --- | --- |
| **Connection failure** | Provider unreachable | Possibly, once proven unsent |
| **TLS configuration** | Certificate hostname mismatch | Halt and fix config; never bypass TLS |
| **AUTH 535** | Wrong credentials/account | Fix account; backup only if authorized |
| **SMTP 421/450** | Temporarily unavailable | Possibly with backoff/policy |
| **Rate limit** | Quota/throttling | Throttle back or shift under control |
| **Invalid recipient** | Nonexistent mailbox | Usually pointless to switch providers |
| **From not authorized** | Unverified sender identity | Fix domain/account authorization |
| **Policy/content rejection** | Content rejected | Never switch solely to evade policy |
| **Timeout after DATA** | Unknown outcome | Must handle duplicate risk |
| **Missing attachment** | Content preparation bug | Not a provider failure |

### 16.1. Do Not Blame All SMTP 5xx Errors on Provider Outages

A `550` can indicate a nonexistent recipient or sender policy rejection. Inspect SMTP enhanced status codes and provider context before assessing route health.

### 16.2. Never Switch Providers to Bypass Policy

Failover is not a workaround for anti-spam policies, sender verification, or security rules. Backup routes must be legitimately authorized for the `From` domain, email category, and tenant.

### 16.3. Retries and Failover Differ

Retries may reuse the same provider after backoff, while failover switches to another provider. Observability should separate **`retry_count`** and **`failover_count`**.

## 17. Classifying Errors by SMTP Phase and Category

A taxonomy can include:

~~~text
prepare_invalid_address
prepare_missing_resource
connect
tls
auth
rate_limit
temporary_smtp
permanent_smtp
recipient_rejected
timeout_unknown
unexpected
~~~

### 17.1. The Outermost Exception Is Often Not Enough

Spring may wrap Jakarta Mail `MessagingException` or `SendFailedException` inside `MailException`. Reliable classification inspects the cause chain, nested exceptions, and structured SMTP codes.

### 17.2. Never Guess the Phase

Without reliable proof of whether failure happened before or after `DATA`, use **`phase=unknown`**. Never assume `after_data` merely because a timeout felt long.

### 17.3. Log Only Essential Error Codes

SMTP reply codes (`421`, `535`, `550`) and enhanced codes aid diagnosis. Raw reply text, however, can expose recipients, accounts, or internal hosts, so omit it from general logs and metrics.

## 18. Partial-Recipient Failures Complicate Attribution

One message can target multiple recipients:

~~~text
RCPT TO alice@example.net -> accepted
RCPT TO bob@example.net   -> rejected
RCPT TO carol@example.net -> accepted
~~~

Depending on provider and Jakarta Mail settings, partial acceptance may occur and `SendFailedException` can list valid vs. invalid addresses.

### 18.1. One Attempt Does Not Equal One Recipient

Recording only attempt failure loses track of which recipients the relay already accepted. When business workflows require per-recipient reconciliation, persist recipient-level state in access-controlled storage.

### 18.2. Avoid Retrying the Entire Group

Resending to every recipient through provider B after partial failure creates duplicates for already-accepted addresses. Retry only the unaccepted subset.

### 18.3. For Personalized Emails, Consider One Event Per Recipient

One message per recipient simplifies privacy, retries, and attribution. The trade-off is connection/transport overhead and quotas—measure and design to fit workload needs.

## 19. Reporting Performance by Provider

A **`Timer`** wrapping `JavaMailSender.send` measures latency from caller invocation until return or exception:

~~~java
Timer.Sample sample = Timer.start(registry);

try {
    selectedSender.send(message);
} finally {
    sample.stop(
            registry.timer(
                    "mail.smtp.submit.call.duration",
                    "provider", selectedProviderAlias
            )
    );
}
~~~

### 19.1. Name Submit-Call Timers Accurately

A `send` call spans DNS, TCP connect, TLS handshake, SMTP AUTH, MIME serialization, attachment I/O, `DATA` transfer, and server reply—it is not purely server request processing time.

### 19.2. Do Not Blame Every High Latency on the Provider

If provider B predominantly sends large PDFs, its `send` duration naturally rises with bytes transferred and lazy resource reads. Segment by mail kind/size bucket and instrument resource loading separately if needed.

### 19.3. Measure by Outcome

Timeout failures take far longer than normal sends. A blended p95 across both groups misleads; inspect p95/p99 alongside success rates and error categories.

### 19.4. Measure Queue Delay Separately

If an outbox item waits 10 minutes before a worker sends it in 300 ms, the bottleneck is queue backlog, scheduling, or retry policy—not a 10-minute SMTP call.

## 20. Controlling Metric Cardinality

| Tag | Example Value | Should You Use It? |
| --- | --- | --- |
| **source** | order-service | Yes, if bounded |
| **provider** | smtp_provider_a | Yes |
| **kind** | order_confirmation | Yes, if allowlisted |
| **outcome** | success/failure | Yes |
| **error_category** | auth/tls/timeout | Yes |
| **route_role** | primary/backup | Conditionally |
| **account_alias** | primary_transactional | Conditionally |
| **region** | apac | Conditionally |
| **tenant_id** | tenant UUID | Usually no when tenants are numerous |
| **mail_event_id** | unique UUID | No |
| **attempt_id** | unique UUID | No |
| **recipient** | user@example.net | No |
| **subject** | arbitrary content | No |

### 20.1. Series Multiply Across Tag Combinations

For example, 5 sources × 3 providers × 8 mail kinds × 3 outcomes × 7 error categories already multiplies into many potential series before factoring in region or account.

Avoid putting every dimension on every metric. A failover counter may only need `from_provider`, `to_provider`, and `reason`; latency timers may only need `provider`, `kind`, and `outcome`.

### 20.2. Account Aliases Can Explode in Multi-Tenant SaaS

If every tenant owns a dedicated SMTP account, `account_alias` is no longer bounded. Aggregate metrics at provider/account-tier level and look up specific accounts via access-controlled logs or tables.

### 20.3. Never Use Arbitrary Hostnames as Provider Labels

Provider aliases should come from a static registry. Raw hostnames can churn or expose internal infrastructure.

## 21. Structured Logs Must Stay Secure

A log sufficient for diagnostics:

~~~text
eventId=mail-1842
attemptId=mail-1842-2
source=order-service
provider=smtp_provider_b
account=backup_transactional
routeReason=failover
phase=smtp_submit
outcome=success
durationMs=910
~~~

Data that should never be broadly logged:

- SMTP passwords, OAuth tokens, AUTH payloads.
- Unnecessary recipient email addresses.
- Full Subjects, bodies, or HTML.
- Attachment bytes.
- Password-reset links, OTPs, signed URLs.
- Raw `MimeMessage` dumps.
- Unsanitized provider replies.

### 21.1. SMTP Debug Is Not a Default Production Setting

Jakarta Mail **`mail.debug`** outputs protocol transcripts containing envelope senders/recipients, SMTP replies, and metadata—and some auth modes carry even higher risks. Never leave debug logging enabled permanently just to collect provider metrics.

### 21.2. TLS Does Not Protect Already-Logged Data

STARTTLS and implicit TLS protect the wire between application and SMTP server; they do not encrypt or restrict access to stdout, log files, collectors, or trace backends.

### 21.3. Lookup by eventId Still Requires Access Control

An `eventId` can link back to users or orders via other tables. Apply auditing, retention, access controls, and export policies accordingly.

## 22. Tracing Sending Flows and Failover

An illustrative trace:

~~~text
business.order.confirm
       |
       v
outbox.enqueue
       |
       v
mail.worker.process
       |
       +-- mail.route.select
       |      provider=smtp_provider_a
       |
       +-- mail.mime.prepare
       |
       +-- mail.smtp.submit
       |      provider=smtp_provider_a
       |      outcome=failure
       |
       +-- mail.route.select
       |      provider=smtp_provider_b
       |
       +-- mail.smtp.submit
              provider=smtp_provider_b
              outcome=success
~~~

### 22.1. One Span Per Attempt

Each SMTP attempt needs its own span or log event. Merging attempts into one span tagged with only the final provider loses latency and error visibility for earlier providers.

### 22.2. Clear Attribute Naming

Custom attributes such as **`mail.source_alias`**, **`mail.provider_alias`**, **`mail.account_alias`**, **`mail.route_reason`**, and **`mail.submit.outcome`** work well as application conventions, not assumed standard OpenTelemetry semantic attributes.

### 22.3. Async/Outbox Flows Need Proper Correlation

Workers may run minutes after the originating request. Propagate trace context safely in events, or use span links with a business correlation ID—never rely on a trace ID as the sole durable business identifier.

### 22.4. High-Cardinality Trace Attributes Still Carry Risk

Never dump tokens, recipients, or email contents into traces just because traces differ from metric labels. Backends still persist and expose traces according to access permissions.

## 23. Outbox Storing Provider Attempt History

A conceptual schema:

~~~text
mail_outbox
  mail_event_id
  source_alias
  mail_kind
  payload_reference
  status
  created_at
  next_attempt_at
  attempts
  last_provider_alias

mail_attempt
  attempt_id
  mail_event_id
  attempt_number
  provider_alias
  account_alias
  route_reason
  policy_version
  started_at
  finished_at
  outcome
  error_category
  smtp_reply_code
  elapsed_ms
~~~

This is an application model, not a schema auto-created by Spring Mail.

### 23.1. lastProviderAlias Alone Is Insufficient History

An outbox row may store `lastProviderAlias` for quick lookups, yet an attempts table or durable structured logs are still needed to know which earlier provider failed.

### 23.2. Keep Full MIME Payloads Out of Telemetry Tables

When workflows retain rendered content for retries, store it in storage governed by dedicated access and retention policies. Never turn `mail_attempt` into a dump of bodies, tokens, and attachments.

### 23.3. Durable State and Metrics Can Diverge

A worker might increment a metric and crash before committing state, or vice versa. Metrics track trends, whereas durable outbox state remains the source of truth for business execution.

## 24. Success Rates: Choosing the Right Denominator

One definition:

\[
\text{Attempt success rate}
=
\frac{\text{Attempts where send returned normally}}
{\text{Total completed attempts with an outcome}}
\]

You must still decide how **`UNKNOWN_OUTCOME`** is counted. If excluded from the denominator, display unknown counts alongside it so risk is never hidden.

### 24.1. Provider A's Success Rate Must Not Use Final Business Outcome

An event completed via backup counts toward business success while still leaving a failure on provider A. Evaluate each provider using attempts attributed to that provider.

### 24.2. Mail Event Success Rate Is a Separate Measure

One mail event can retry across three providers before succeeding. Event completion rates use **unique events**, not attempts.

### 24.3. Always Inspect Volume

2/2 successes does not prove a provider is more reliable than 99,900/100,000 successes. Display windows, counts, and event mixes side by side.

## 25. Prometheus: Attempt Rate by Provider

Assuming an exporter emits the counter:

~~~text
mail_smtp_submit_attempts_total{
  provider="smtp_provider_a",
  outcome="success"
}
~~~

Attempt rate:

~~~promql
sum by (provider) (
  rate(mail_smtp_submit_attempts_total[5m])
)
~~~

### 25.1. Attempt success ratio

~~~promql
sum by (provider) (
  rate(
    mail_smtp_submit_attempts_total{
      outcome="success"
    }[5m]
  )
)
/
sum by (provider) (
  rate(mail_smtp_submit_attempts_total[5m])
)
~~~

Guard against zero denominators and align outcome sets. This query does not measure inbox delivery.

### 25.2. Error categories

~~~promql
sum by (provider, error_category) (
  rate(mail_smtp_submit_failures_total[5m])
)
~~~

When a failures metric exists, every category must come from a bounded enum—never from raw exception messages.

### 25.3. Read Semantics Correctly

A retried event creates multiple attempts. Attempt rate is not equivalent to unique customers receiving emails per second.

## 26. Prometheus: Latency by Provider

With a histogram-backed Timer, series may include:

~~~text
mail_smtp_submit_call_duration_seconds_count
mail_smtp_submit_call_duration_seconds_sum
mail_smtp_submit_call_duration_seconds_bucket
~~~

Exact metric names depend on the Micrometer/Prometheus registry and configuration; buckets appear only when histogram/SLO publishing is enabled.

### 26.1. p95 of Successful Send Calls

~~~promql
histogram_quantile(
  0.95,
  sum by (provider, le) (
    rate(
      mail_smtp_submit_call_duration_seconds_bucket{
        outcome="success"
      }[5m]
    )
  )
)
~~~

### 26.2. Never Average p95 Across Nodes

Percentiles are not linearly additive. Aggregate histogram buckets properly instead of averaging per-instance p95 values.

### 26.3. Interpret Latency Alongside Size and Traffic Mix

A provider primarily handling 5 MB PDFs naturally exhibits higher send latency than one handling tiny OTPs. Segment by mail kind, size buckets, and client preparation time to avoid flawed comparisons.

## 27. Minimum Dashboard for Multiple Providers

| Panel Area | Metrics / Charts |
| --- | --- |
| **Route distribution** | Selection counts by source/provider/reason |
| **Actual usage** | Attempts/second by provider/account |
| **Submission outcome** | Success, failure, unknown by provider |
| **Latency** | p50/p95/p99 send-call latency by outcome |
| **Error breakdown** | Auth, TLS, connect, recipient, throttling |
| **Failover** | A→B transition counts, reasons, trends |
| **Outbox** | Pending, oldest age, retries, deadline misses |
| **Business mail events** | Unique completed vs. terminal failed |
| **Capacity** | Worker saturation, provider rate limits/quotas |
| **Downstream** | Bounce/delivery webhooks if integrated |

### 27.1. Chart Both Selected and Attempted

If provider A's traffic drops, you need to know whether the router stopped picking A or picked A only for preparation to fail before `send`.

### 27.2. Filter by Source and Mail Kind

Suppose `identity-service` suffers AUTH failures while `order-service` runs cleanly. That points to a specific account/security route bug rather than a full SMTP provider outage.

### 27.3. Show Counts Alongside Ratios

A 50% failure rate across two samples means something very different from 50% across 100,000 samples. Dashboards should tame noise with proper windows and minimum sample thresholds.

## 28. Operational Alerts per Provider

Actionable alerts:

- **Auth failures rising on an account alias:** verify secrets/permissions and stop aggressive retries.
- **TLS failures rising:** inspect hostnames, certificate chains, and endpoint modes.
- **Timeout rate rising:** separate connect, read, write, and unknown outcomes.
- **SMTP 421/450 rising:** inspect provider throttling and backoff.
- **Failover frequency rising:** check primary health and backup headroom.
- **Backup traffic approaching quota:** rebalance routes and curb non-urgent load.
- **Oldest pending outbox item exceeds SLO:** inspect queues, workers, and retries.
- **Unknown outcomes rising:** reconcile duplicate risk.
- **Provider A receives zero attempts while still primary:** inspect router, circuit breakers, and config.

### 28.1. Never Declare a Provider Down From One Recipient Error

An SMTP `550` on `RCPT TO` may simply mean a nonexistent mailbox, not a full provider outage.

### 28.2. Circuit Breakers Need Dedicated Metrics

When a circuit breaker is OPEN, a provider receives no new attempts; seeing zero or tiny error counts does not mean it recovered. Instrument breaker state and routing suppressions by reason.

### 28.3. Tune Alerts to Traffic Volume

A provider handling a few attempts per hour requires different alerting thresholds than one handling tens of thousands of attempts per minute to avoid overreacting to noise.

## 29. Provider Health Does Not Equal Delivery Health

Some applications run `JavaMailSenderImpl.testConnection()` or TCP/TLS probes.

Keep in mind:

- Probes verify connectivity and login only to a certain extent.
- They do not replace real sending and MIME serialization.
- They do not verify `From`-domain authorization for every account.
- They do not prove inbox delivery.
- They do not prove every recipient will be accepted.

### 29.1. Do Not Call testConnection Before Every Message

Calling `testConnection()` before every email adds network round-trips, consumes connection limits, and hurts throughput. Probe on a measured cadence alongside live traffic metrics.

### 29.2. Health at Both Provider and Account Levels

A provider's endpoint may be up while one account is suspended. Maintain fine-enough attribution dimensions to spot problems at the right level.

### 29.3. Probes Also Need Outcome Telemetry

A health check hitting a TLS failure or timeout must be logged and instrumented under its provider alias, yet never mixed into business SMTP submit attempts.

## 30. Configuration Changes and Historical Attribution

When route configuration changes:

~~~text
10:00 account=transactional -> provider A
10:30 operator changes mapping
11:00 account=transactional -> provider B
~~~

If history only stores `account` alias and dashboards join against today's mapping, earlier attempts get misattributed to provider B.

### 30.1. Store Provider Identity at Attempt Time

Each attempt should record the actual `provider_alias` and config/policy version when needed.

### 30.2. Never Turn Primary Into Provider Identity

Primary/backup are roles that shift over time. Provider aliases must outlive route role changes.

### 30.3. Audit Manual Overrides

Manual route overrides must record timestamp, reason, and operator per audit policy. Never embed free-text tickets or sensitive identities into metric labels.

### 30.4. Do Not Snapshot Credentials

To investigate config changes, store aliases, versions, and non-sensitive settings only—never dump passwords or OAuth tokens into logs.

## 31. Testing Attribution With Mockito and Micrometer

Unit tests can mock two `JavaMailSender` instances, build an in-memory `MimeMessage`, and verify the exact provider receives the call.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Map;
import java.util.Properties;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class MultiProviderMailSubmitterTest {

    @Test
    void recordsActualProviderForSelectedAttempt() {
        SimpleMeterRegistry metrics =
                new SimpleMeterRegistry();

        JavaMailSender primary =
                mock(JavaMailSender.class);

        JavaMailSender backup =
                mock(JavaMailSender.class);

        MimeMessage mime = new MimeMessage(
                Session.getInstance(new Properties())
        );

        when(primary.createMimeMessage())
                .thenReturn(mime);

        MultiProviderMailSubmitter submitter =
                new MultiProviderMailSubmitter(
                        Map.of(
                                "primary_transactional", primary,
                                "backup_transactional", backup
                        ),
                        metrics
                );

        OutboundMailJob job =
                new OutboundMailJob(
                        "mail-1842",
                        "order-service",
                        "order_confirmation",
                        "an@example.net",
                        "Order confirmation",
                        "Your order has been confirmed."
                );

        MailRouteDecision route =
                new MailRouteDecision(
                        "order-service",
                        "smtp_provider_a",
                        "primary_transactional",
                        "orders@example.org",
                        "tenant_default"
                );

        submitter.submit(job, route, "mail-1842-attempt-1");

        verify(primary, times(1))
                .send(any(MimeMessage.class));

        verifyNoInteractions(backup);

        Counter counter = metrics
                .find("mail.smtp.submit.attempts")
                .tag("provider", "smtp_provider_a")
                .tag("outcome", "success")
                .counter();

        assertNotNull(counter);
        assertEquals(1.0, counter.count(), 0.0001);

        assertNull(
                metrics.find("mail.smtp.submit.attempts")
                        .tag("provider", "smtp_provider_b")
                        .counter()
        );
    }
}
~~~

### 31.1. What Does This Test Prove?

- The primary account's sender is invoked.
- The backup sender is untouched.
- Metrics record `smtp_provider_a`, not another provider.
- No real SMTP connection opens.
- No real recipient address is emailed.

### 31.2. Test Failure Paths Separately

Make `primary.send` throw `MailSendException`; verify A's **`outcome=failure`** rises while `success` does not. Separately unit-test the router/retry policy to verify failover to B when errors are classified as safe for failover.

### 31.3. Test Invalid Routes

If an account alias is absent from the registry, fail with a configuration error—never silently fall back to a default sender while tagging metrics with the originally requested provider.

## 32. Testing Failover Without Skewing Counts

Scenario:

~~~text
attempt A -> failure
policy decides failover
attempt B -> success
~~~

Expected behavior:

1. A is invoked exactly once.
2. B is invoked exactly once when policy allows.
3. Counter `A/failure` increments by one.
4. Counter `B/success` increments by one.
5. Failover counter `A→B` increments by one.
6. Unique event completed count increments once when the event reaches terminal success, not on every attempt.
7. Attempt history retains both providers.
8. Logs exclude credentials, full messages, and unnecessary recipients.

### 32.1. Test Unknown Outcomes

If a post-DATA error leaves acceptance uncertain, policy must not automatically switch to B. Tests should verify `UNKNOWN_OUTCOME`, reconciliation, or approved business handling.

### 32.2. Test Partial Recipients

For multi-recipient messages, verify accepted recipients are not blindly re-sent.

### 32.3. Avoid Unnecessary Re-Rendering

When a mail event holds a rendered content snapshot and failover preserves content, switching providers need not re-run Thymeleaf. Though independent of attribution, test that content does not diverge between attempts.

## 33. Scenario: Provider A AUTH Failure

Suppose telemetry shows:

~~~text
source=identity-service
kind=password_reset
provider=smtp_provider_a
account=security_primary
phase=auth
smtpReplyCode=535
errorCategory=auth
~~~

Interpretation:

- Account `security_primary` was used.
- Failure happened during SMTP AUTH.
- Passwords are not needed in logs to diagnose this.
- Causes may be wrong credentials, disabled account, or changed AUTH policy.
- Do not declare the entire provider down if other accounts send normally.
- Tight retries will never fix an invalid password.
- Backup can only be used if the account, `From` domain, and email category are authorized and allowed by policy.

Track **per-account** metrics or authorized lookups when errors cluster on one account.

## 34. Scenario: Provider Throttling

Suppose the SMTP server returns a temporary reply under rate limits:

~~~text
source=order-service
provider=smtp_provider_a
errorCategory=rate_limit
routeReason=tenant_default
~~~

The system may need to:

- Apply bounded backoff.
- Reduce concurrency/rate.
- Monitor quotas.
- Tune outbox pacing.
- Shift providers if policy and quotas permit.
- Protect deadlines for urgent emails.

Dashboards show how many attempts hit throttling, how much traffic shifted to backup, and whether backlog keeps climbing.

### 34.1. Do Not Classify Every 4xx as Throttling

SMTP `4xx` has many causes. Map categories accurately using reply/enhanced status codes and provider guidance.

### 34.2. Avoid Cascading Overload on Backup

Shifting 100% of A's traffic to B can overwhelm B's quota. Check B's capacity and policies before switching.

## 35. Scenario: Same From Domain, Two Providers

~~~text
Visible From: billing@example.org

Provider A:
  account=primary_transactional
  host=smtp-a.example.net

Provider B:
  account=backup_transactional
  host=smtp-b.example.net
~~~

Both can send under the same visible `From` once domains and providers are properly authorized.

### 35.1. Separate From Identity and Provider

Logs/metrics can record:

~~~text
fromIdentityAlias=billing_domain
providerAlias=smtp_provider_b
~~~

Matching `From` addresses never imply identical transport providers.

### 35.2. SPF/DKIM/DMARC Matter but Do Not Replace Attribution

When switching providers, verify SPF, DKIM, DMARC, envelope return paths, and alignment. Those validate domain authority, not which provider Spring Mail picked.

### 35.3. Never Infer Deliverability From Send Success

Even when `sender.send` returns cleanly, downstream filtering can occur. If a provider exposes delivery/bounce webhooks, build a separate ingestion flow linking back via `mailEventId`/`providerMessageId` where available.

## 36. Scenario: Multi-Tenant Applications

A multi-tenant platform may run many accounts on one provider. Using each tenant's UUID as `accountAlias` in every metric label causes massive time-series growth.

Tiered approach:

- Aggregate metrics by provider, region, mail kind, and outcome.
- Group accounts into small tiers where helpful.
- Look up specific accounts/tenants via access-controlled structured logs or databases.
- Audit access on tenant-specific dashboards.
- Exclude raw tenant/customer IDs from broad metric labels.

### 36.1. Account Alias Is Not Provider

One provider holds many accounts; bad credentials on one account do not mean the provider is down. Controlled account dimensions help isolate the issue.

### 36.2. Tenant Isolation

Observability must preserve tenant isolation. One customer must never view another customer's mail events, recipients, or accounts just because they share an SMTP provider.

## 37. Implementation Checklist for Sender Source Reporting

A practical workflow:

1. Define **`source_alias`**, **`provider_alias`**, **`account_alias`**, **`route_role`**, and **`mail_kind`**.
2. Build a stable alias registry rather than using raw hostnames or credentials as labels.
3. Separate event IDs from attempt IDs.
4. Record route decisions with reason and policy version.
5. Increment SMTP attempt metrics only when actually calling `send`.
6. Tag the actual provider/account used at attempt time, never inferred from current config.
7. Wrap `JavaMailSender.send` with a timer covering both normal return and exceptions.
8. Separate caller success, failure, and unknown outcomes.
9. Retain attempt history across retries and failover.
10. Track unique event completions separately from attempts.
11. Assign error categories from exception cause chains and verified SMTP phases.
12. Never automatically fail over every 4xx/5xx or timeout.
13. Track partial-recipient results when using batch or multi-recipient sends.
14. Enforce low-cardinality metric tags.
15. Keep recipients, Subjects, bodies, passwords, and tokens out of logs.
16. Create per-attempt spans when tracing is enabled.
17. Measure queue delay, retry wait, and end-to-end duration separately.
18. Build dashboards for route distribution, actual usage, latency, and errors.
19. Alert on account, provider, rate-limit, and unknown-outcome spikes.
20. Maintain runbooks for TLS, AUTH, and failover incidents.
21. Verify backup capacity and `From` authorization beforehand.
22. Test attribution with Mockito and fake transports.
23. Verify historical integrity when route policies change.
24. Reconcile metrics periodically against durable outbox state to catch drift.

## 38. Frequently Asked Questions

**1. Should "sender source" reporting track From or the provider?**

Track at least two fields: business source and actual provider. `From` identity is a separate dimension and never replaces transport attribution.

**2. How do we know which provider was actually used?**

Record metrics/logs right inside the adapter invoking the selected `JavaMailSender`. Never infer the provider from the originating event when routes can change.

**3. Does a mail event retried three times count as three emails?**

It is not three unique business events. It creates three attempts; duplicates might occur during uncertain failure windows, yet attempt count does not prove how many mailboxes received mail.

**4. Does successful failover erase the first provider's error?**

No. The first provider still has a failed attempt and the second has a successful attempt, while the business event finishes as completed.

**5. Should SMTP usernames be included in metrics?**

No. Use managed account aliases, and never record passwords or tokens.

**6. Does Spring Mail automatically return a provider message ID?**

Standard `JavaMailSender` does not guarantee returning a provider-specific message ID from `send`. Some providers expose separate APIs or webhooks for downstream correlation.

**7. Does send returning normally mean delivered?**

No. It confirms transport submission completed. Inbox delivery, bounces, and user opens are separate milestones.

**8. Does a timeout prove the email was not sent?**

No. Timeouts after `DATA` can occur after the relay already accepted the message. Use unknown outcomes and explicit reconciliation/retry policies.

**9. Should every SMTP 5xx trigger failover?**

No. A `5xx` may stem from recipient, sender authorization, or content policies; switching providers may not help and can violate policy.

**10. Why avoid recipient addresses as metric tags?**

Recipients are PII and cause extreme cardinality. Use correlation IDs in access-controlled logs instead.

**11. Can p95 be compared across providers the same way automatically?**

Only with identical Timer scopes, outcome filtering, and awareness of mail mix/payload size; otherwise comparisons mislead.

**12. Do health probes replace live sending metrics?**

No. Probes test connectivity and AUTH, but cannot prove all MIME payloads will be accepted or delivered.

**13. What happens when a provider switches roles from primary to backup?**

Keep provider identity stable and track `route_role` separately. Record the actual provider on each attempt so history stays accurate.

**14. Should full SMTP transcripts be stored for accurate attribution?**

Usually no. Route decisions, attempt outcomes, error codes, and correlation suffice in most scenarios; raw debug logs carry data-exposure risk and should be tightly restricted.

**15. Can attribution be tested without a real SMTP server?**

Yes. Mock multiple `JavaMailSender` beans, use `SimpleMeterRegistry`, and assert the exact sender invocation and provider/outcome counter tags.

**16. Can tenant IDs be placed on metrics?**

When tenant count is high or sensitive, exclude them from broad metric labels. Aggregate by provider/tier and inspect tenant details in access-controlled stores.

**17. Should route selection and actual attempts be tracked separately?**

Yes. Routing may pick a provider before message preparation fails and prevents `send`. Two counters answer two distinct questions.

**18. What risks come with multi-recipient SMTP messages?**

Partial acceptance, trickier per-recipient retries, and To/CC address exposure. Track recipient-level outcomes when business requirements demand it.

**19. Does OpenTelemetry standardize semantic conventions for all these fields?**

Do not assume so. Use clear custom attributes and check existing conventions to avoid naming collisions.

**20. If provider A fails but events succeed via B, is the SLA completely fine?**

Business SLAs may survive, yet provider A still needs investigation; failover can also increase cost, latency, and duplicate risk.

## 39. Key Takeaways on Sender Source Reporting in Observability

**In multi-provider Spring Framework Mail systems, "sender source" must be separated into business source, actual SMTP provider/account, and visible email identity.** A selected provider does not always yield an attempt; a started attempt is not always accepted by the relay; and a successful `send` return never proves inbox delivery.

**Attribution belongs on every attempt, not only the final event state.** Across retries and failover, preserve both earlier and later providers, classify error categories, record duration, and flag post-DATA uncertainty. Count **SMTP attempts** separately from **unique mail events** so business volume stays accurate.

Use **Micrometer counters/timers** for aggregation, **structured logs** with `eventId`/`attemptId` for reconciliation, and **tracing** across business → outbox → route → SMTP. Keep metric labels bounded and allowlisted; keep recipients, Subjects, bodies, attachments, passwords, tokens, and event IDs out of time series.

Solid sender source reporting lets operations see **who created the send intent, which provider was actually tried, which attempt succeeded or failed, when to fail over, and how certain the final outcome is**. It forms the foundation for operating multi-SMTP systems reliably, securely, and auditably.
