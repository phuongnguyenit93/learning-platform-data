# A Common Abstraction for Multiple SMTP Providers

A Spring Framework Mail system may have to send email through multiple SMTP services: provider A dedicated to transactional email, provider B serving marketing, an internal relay for alerts, and a separate SMTP account for each enterprise customer. If each business feature chooses the host, username, port, and how to call `JavaMailSender` on its own, the code quickly becomes coupled to providers, hard to reroute, hard to measure, and prone to sending messages or credentials to the wrong place.

The solution is to design a **common abstraction for multiple SMTP providers**: business logic creates an email sending request with a stable structure; a routing component selects an approved profile; an adapter for each profile builds and submits MIME over SMTP; and retry, outbox, and tracking manage outcomes by **logical email**, not by arbitrary technical exceptions.

An important distinction: using a common interface does **not** mean all providers share the same limits, the same SMTP responses, the same bounce mechanisms, the same DKIM setup, or the same idempotency support. A good abstraction unifies the parts that share the same semantics while preserving differences that affect correctness and deliverability.

This lesson designs the model end to end with **Spring Boot, JavaMailSender, multi-SMTP profile configuration, provider registry, routing, controlled retry/failover, distinguishing SMTP submission from delivery**, tenant security, and a multi-provider test suite.

## 1. When Do You Need a Common Abstraction?

For example, a SaaS application has the following needs:

| Email source | Sending channel | Specific rules |
|---|---|---|
| Order confirmation | SMTP Provider A | Prioritize low latency, keep per-message audit |
| Newsletter | SMTP Provider B | Quota and suppression differ from transactional email |
| Operational alert | Internal relay | Only allow domains and recipients belonging to the organization |
| Email for enterprise tenant | Dedicated SMTP profile | Credentials, domain, and quotas isolated per tenant |
| Fallback during provider incident | Prepared Provider C | Switch only when submission has **not yet been accepted** or there is an explicit outcome-handling policy |

If business code is written directly as:

```java
if (transactional) {
    sendWithProviderA(...);
} else if (marketing) {
    sendWithProviderB(...);
} else {
    sendWithInternalRelay(...);
}
```

and that choice is repeated across dozens of services, the system will suffer from:
- hardcoding providers in business logic;
- inconsistent TLS and timeout configuration;
- lacking a central place to enforce rate limits, quotas, and policy;
- difficulty writing unit tests without a real SMTP server;
- difficulty tracking total attempts and outcomes per provider;
- risk of failover causing duplicate sends or wrong domain identity;
- changing providers requiring edits across many business classes.

**Goal:** business code requests "send this notification category under an allowed identity," not "connect to SMTP host X on port Y."

## 2. Four Layers of Responsibility to Separate

```text
OrderService / IdentityService / MarketingService
                 |
                 | EmailCommand (logical email)
                 v
       OutboundMailApplicationService
        - authorize recipient
        - idempotency / outbox
        - choose mail category
                 |
                 v
          ProviderRouter
        - policy / tenant
        - route / quotas
        - health eligibility
                 |
                 v
        MailSubmissionPort
        (provider-neutral interface)
                 |
       +---------+----------+
       |                    |
       v                    v
 SmtpAdapter A         SmtpAdapter B
 JavaMailSender A      JavaMailSender B
       |                    |
       v                    v
 Provider A SMTP       Provider B SMTP
       |                    |
       +---------+----------+
                 |
                 v
        Receiving mail systems
```

Each layer has a clear responsibility:

1. **Application/business service:** decides which email is sent, what content it has, who is allowed to receive it, and how many logical emails each action creates.
2. **Router/policy:** chooses the appropriate route among approved providers.
3. **Submission adapter:** turns content into MIME, connects to SMTP, and returns an outcome following the common contract.
4. **Outbox and delivery tracker:** persists attempts, retries, reconciliation, webhooks/bounces, and subsequent states.

Do not collapse these four responsibilities into one `MailUtil.sendAnything(...)` class with many optional parameters.

## 3. Identifying What Is Common and What Is Not

Parts that can be standardized:
- the application's message key;
- approved sender identity;
- recipient and notification category;
- subject, plain text, and HTML;
- non-sensitive metadata used for tracing;
- attempt ID and selected provider route;
- submission outcome at the level of `ACCEPTED`, `RETRYABLE_FAILURE`, `PERMANENT_FAILURE`, or `UNKNOWN`;
- requiring no unbounded retries;
- logs/metrics by message key and provider.

Points that must remain configurable or extensible:
- SMTP host/port and TLS mode;
- AUTH mechanisms: password, app password, OAuth2, or unauthenticated relay per policy;
- request limits, connection limits, and daily quotas;
- From/envelope sender and custom return-path;
- DKIM signing domain and domain verification;
- provider-specific SMTP errors/responses;
- support for provider message IDs, dashboards, webhooks, and suppression;
- attachment/message size limits;
- idempotency definition and retention window if using a provider HTTP API.

**A usable abstraction must not hide the `UNKNOWN` state or assume a capability that standard SMTP does not provide.**

## 4. Distinguishing Three Milestones in the Email Lifecycle

```text
Email request persisted
    |
    | API 202: queued in outbox
    v
Worker selects provider
    |
    | JavaMailSender.send(...)
    v
SMTP server accepts submission
    |
    | SMTP 250 at the applicable phase
    v
Provider queue / transfer
    |
    | provider retries delivery when deferred
    v
Receiving mail server
    |
    | delivery event if supported
    v
Application delivery status
```

- `QUEUED`: the application has persisted the request for processing.
- `SMTP_ACCEPTED`: the upstream SMTP/relay accepted the submission according to what the client observed.
- `DELIVERED`: there is appropriate evidence from the provider/receiver of delivery to the destination server, according to the provider's event definition.

A `send(...)` call that throws no exception **does not prove the email reached the Inbox or was opened**.

This matters when switching providers: if provider A already accepted the email and reports `deferred` during delivery, the application **should not send a new copy through provider B** just because B is healthy.

## 5. Designing a Common Data Model for a Logical Email

A request should not contain an SMTP password or allow callers to supply an arbitrary SMTP host.

Java 17+ model example:

```java
package com.example.mail;

public enum MailCategory {
    TRANSACTIONAL,
    SECURITY,
    MARKETING,
    INTERNAL_ALERT
}

public record EmailCommand(
    String messageKey,
    String tenantId,
    MailCategory category,
    String recipient,
    String subject,
    String plainText,
    String htmlText,
    String templateVersion
) {}
```

Meaning:
- `messageKey`: identifies **one logical email**, stable across attempts.
- `tenantId`: authorization and profile-selection boundary, never taken blindly from unverified data.
- `category`: routing policy based on notification type, not provider names hardcoded in business code.
- `recipient`: must be checked against permissions and mail-receiving policies.
- `subject/plainText/htmlText`: rendered content or a snapshot per business rules.
- `templateVersion`: supports tracing the exact content used.

A large system may store a reference or encrypted snapshot instead of the full body in the outbox. That depends on the data, audit requirements, retention, and retry strategy.

### 5.1. A Request Is Not a Single Send Attempt

Example:

```text
messageKey = msg-1001
   |
   +-- attempt-1 -> provider-A -> TEMPORARY_FAILURE
   |
   +-- attempt-2 -> provider-A -> SMTP_ACCEPTED
                                   |
                                   +-- delivery deferred
                                   +-- delivery accepted
```

Even as attempts change, `messageKey` stays the same. If a user actively requests sending a new notification later, the application can create a new message key according to business policy.

### 5.2. Do Not Let the Domain Model Depend on SMTP Internals

Do not require the business layer to construct:
- `jakarta.mail.Session`;
- `MimeMessage`;
- `Transport`;
- `MessagingException`;
- `mail.smtp.ssl.enable`.

These concepts belong to the adapter. The business layer should only use value objects and outcomes meaningful within the system.

## 6. Common Submission Interface

The abstraction should reflect **submission**, not promise delivery:

```java
package com.example.mail;

import java.time.Instant;

public interface MailSubmissionPort {

    SubmissionReceipt submit(
        EmailCommand command,
        String providerKey,
        String attemptId
    );
}

public record SubmissionReceipt(
    String messageKey,
    String attemptId,
    String providerKey,
    Instant acceptedAt
) {}
```

`SubmissionReceipt` in this pattern means **SMTP submission observed by the client as successful**. For generic SMTP, a receipt is **not required** to contain a provider message ID because the protocol does not guarantee a uniform ID usable for status queries.

Possible extensions:

```java
public record ProviderMetadata(
    String rfcMessageId,
    String providerMessageId,
    String smtpQueueId
) {}
```

Fields must have clear meaning, be supported by the corresponding adapter/provider, and may be empty; do not automatically treat an RFC `Message-ID` as a provider queue ID.

### 6.1. Returning Errors with a Unified Taxonomy

```java
public enum FailureCategory {
    RETRYABLE,
    PERMANENT,
    UNKNOWN
}

public final class SubmissionFailure
        extends RuntimeException {

    private final FailureCategory category;
    private final String safeCode;
    private final String providerKey;

    public SubmissionFailure(
            FailureCategory category,
            String safeCode,
            String providerKey,
            Throwable cause) {
        super(safeCode, cause);
        this.category = category;
        this.safeCode = safeCode;
        this.providerKey = providerKey;
    }

    public FailureCategory category() {
        return category;
    }

    public String safeCode() {
        return safeCode;
    }

    public String providerKey() {
        return providerKey;
    }
}
```

`safeCode` is a normalized code such as `SMTP_451_BEFORE_DATA` or `AUTH_CONFIG_ERROR`, not the entire raw exception containing email addresses, sensitive SMTP replies, or tokens.

**Only cases proven safe to retry should be mapped to `RETRYABLE`.** Timeout errors where it is unclear whether the server received DATA must be marked `UNKNOWN` when there is no conclusive evidence.

### 6.2. A Common Interface Does Not Automatically Provide Exactly-Once

Even with `messageKey` and `attemptId`:
- SMTP does not deduplicate by custom headers by default.
- Two calls to `send(...)` can produce two emails.
- A send already accepted by the server cannot be rolled back by a database transaction.
- Failover after an unknown outcome can create a duplicate on the new provider.

The abstraction must let the application persist and handle this uncertainty, not hide it behind a `boolean success`.

## 7. Centralized Configuration for Multiple SMTP Providers

In Spring Boot, you can define a dedicated application namespace:

```yaml
app:
  outbound-mail:
    providers:
      primary:
        host: smtp-a.example.net
        port: 587
        username: ${SMTP_A_USERNAME}
        password: ${SMTP_A_PASSWORD}
        verified-from: receipts@example.com
        implicit-tls: false

      secondary:
        host: smtp-b.example.net
        port: 465
        username: ${SMTP_B_USERNAME}
        password: ${SMTP_B_PASSWORD}
        verified-from: receipts@example.com
        implicit-tls: true

      alerts:
        host: relay.internal.example
        port: 587
        username: ${SMTP_ALERT_USERNAME}
        password: ${SMTP_ALERT_PASSWORD}
        verified-from: alerts@example.com
        implicit-tls: false
```

**All hostnames, accounts, and domains above are examples.** Production profiles must use parameters issued by the provider/infrastructure, verified authorization to use the From domain, and protected secrets.

### 7.1. Binding Configuration with ConfigurationProperties

```java
package com.example.mail;

import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.outbound-mail")
public record MultiSmtpProperties(
    Map<String, SmtpAccount> providers
) {
    public record SmtpAccount(
        String host,
        int port,
        String username,
        String password,
        String verifiedFrom,
        boolean implicitTls
    ) {}
}
```

This is a Spring Boot 3 model using constructor binding on a record. When an application has more specific requirements, add validation:
- `host` is non-blank;
- `port` is within valid range;
- TLS mode is supported by the profile;
- credentials are supplied according to policy;
- From domain is verified;
- no duplicate provider keys or missing profiles.

Do not log the `MultiSmtpProperties` object because the record may contain passwords.

### 7.2. Creating a Preconfigured Sender Once per Profile

```java
package com.example.mail;

import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
@EnableConfigurationProperties(MultiSmtpProperties.class)
public class MultiSmtpConfiguration {

    @Bean
    ProviderRegistry providerRegistry(MultiSmtpProperties config) {
        Map<String, SmtpProviderBinding> bindings =
            new HashMap<>();

        config.providers().forEach((providerKey, account) -> {
            JavaMailSender sender = buildSender(account);

            bindings.put(
                providerKey,
                new SmtpProviderBinding(
                    providerKey,
                    account.verifiedFrom(),
                    sender
                )
            );
        });

        return new ProviderRegistry(bindings);
    }

    private static JavaMailSender buildSender(
            MultiSmtpProperties.SmtpAccount account) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(account.host());
        sender.setPort(account.port());
        sender.setUsername(account.username());
        sender.setPassword(account.password());
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();

        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        if (account.implicitTls()) {
            props.put("mail.smtp.ssl.enable", "true");
        } else {
            props.put("mail.smtp.starttls.enable", "true");
            props.put("mail.smtp.starttls.required", "true");
        }

        return sender;
    }
}
```

The snippet above illustrates a profile using SMTP AUTH with username/password. For OAuth2 or unauthenticated relays, the adapter/configuration factory needs to support a separate contract rather than assuming every SMTP provider authenticates with a password.

**Lifecycle note:** senders are created at startup and kept in a stable registry. Do not mutate `setHost`, `setUsername`, or `setPassword` on the same instance while multiple workers are sending.

### 7.3. An Immutable Registry to Avoid Selecting the Wrong Provider

```java
package com.example.mail;

import java.util.Map;
import org.springframework.mail.javamail.JavaMailSender;

public record SmtpProviderBinding(
    String providerKey,
    String verifiedFrom,
    JavaMailSender sender
) {}

public final class ProviderRegistry {

    private final Map<String, SmtpProviderBinding> providers;

    public ProviderRegistry(
            Map<String, SmtpProviderBinding> providers) {
        this.providers = Map.copyOf(providers);
    }

    public SmtpProviderBinding require(String providerKey) {
        SmtpProviderBinding binding =
            providers.get(providerKey);

        if (binding == null) {
            throw new IllegalArgumentException(
                "Unknown or disabled mail provider"
            );
        }

        return binding;
    }
}
```

An immutable registry prevents changing routing/credentials inside a business method. If hot reload is needed:
- build a new registry/senders from verified configuration;
- switch atomically to the new version at the service layer;
- have rules for handling active sends and disposing old resources;
- restrict configuration changes to authorized principals;
- test credential rotation and profile rollback.

Do not keep a singleton `JavaMailSenderImpl` and mutate the account per tenant/recipient.

## 8. SMTP Adapter Implementing the Common Interface

With the registry and model above, one adapter can use any SMTP provider as long as the profile is valid.

```java
package com.example.mail;

import java.time.Clock;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MultiSmtpSubmissionAdapter
        implements MailSubmissionPort {

    private final ProviderRegistry registry;
    private final MailFailureClassifier classifier;
    private final Clock clock;

    public MultiSmtpSubmissionAdapter(
            ProviderRegistry registry,
            MailFailureClassifier classifier,
            Clock clock) {
        this.registry = registry;
        this.classifier = classifier;
        this.clock = clock;
    }

    @Override
    public SubmissionReceipt submit(
            EmailCommand command,
            String providerKey,
            String attemptId) {

        SmtpProviderBinding binding =
            registry.require(providerKey);

        MimeMessage mime = binding.sender().createMimeMessage();

        try {
            MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom(binding.verifiedFrom());
            helper.setTo(command.recipient());
            helper.setSubject(command.subject());

            if (command.htmlText() == null
                    || command.htmlText().isBlank()) {
                helper.setText(command.plainText(), false);
            } else {
                helper.setText(
                    command.plainText(),
                    command.htmlText()
                );
            }

            mime.setHeader(
                "X-Application-Message-Key",
                command.messageKey()
            );
            mime.setHeader("X-Mail-Attempt-ID", attemptId);

        } catch (MessagingException ex) {
            throw new SubmissionFailure(
                FailureCategory.PERMANENT,
                "MIME_BUILD_ERROR",
                providerKey,
                ex
            );
        }

        try {
            binding.sender().send(mime);
        } catch (MailException ex) {
            throw classifier.classify(providerKey, ex);
        }

        return new SubmissionReceipt(
            command.messageKey(),
            attemptId,
            providerKey,
            clock.instant()
        );
    }
}
```

`MailFailureClassifier` is an application interface/service introduced in the next section. The adapter snippet illustrates:
- Selecting the sender from the **registry**, not from an arbitrary caller-supplied host.
- Setting From from the verified profile.
- Creating a separate `MimeMessage`/`MimeMessageHelper` per attempt.
- Attaching tracing headers that contain no secrets.
- Building the email before making network calls.
- Routing send errors through an SMTP-aware classifier.
- Returning `SubmissionReceipt` when the submission call completes without synchronous error.

For production use:
- Validate `EmailCommand` before it reaches the adapter, especially recipient, subject, plain text, and tenant permissions.
- Header fields must be constrained in length/characters to prevent header injection; IDs should be server-generated and validated values.
- If building MIME fails due to missing or malformed data, classify as permanent per contract; internal infrastructure errors like out-of-memory should be handled separately rather than lumping everything into user errors.
- If an exception occurs after SMTP begins, the classifier must **avoid asserting not-sent** when there is a chance the server already received the message.
- Do not store passwords or sensitive MIME details in logs.

### 8.1. Explicit Clock Bean

In the application, you can provide:

```java
@Bean
Clock mailClock() {
    return Clock.systemUTC();
}
```

In JUnit, replace it with `Clock.fixed(...)` to test receipt timestamps, retry schedules, and deadlines deterministically.

### 8.2. Why Not Return a Boolean?

`boolean sent` does not distinguish:
- connection never established;
- SMTP rejection before DATA;
- authentication error;
- TLS hostname mismatch;
- SMTP accepted;
- timeout after DATA, outcome unknown;
- email currently being retried for delivery by the provider.

A result or exception with a clear taxonomy helps downstream code make safer retry/failover decisions.

## 9. Classifying Errors by the Right Layer and Real Evidence

Classifier contract:

```java
package com.example.mail;

import org.springframework.mail.MailException;

public interface MailFailureClassifier {
    SubmissionFailure classify(
        String providerKey,
        MailException exception
    );
}
```

Error groups to distinguish:

| Group | Example | Suggested decision |
|---|---|---|
| **Pre-submission / build** | Invalid recipient format, MIME construction failure | Stop, fix data/template; do not blindly retry |
| **Configuration** | Wrong credentials, invalid certificate/TLS hostname | Alert and fix configuration; do not aggressively retry |
| **Transient before acceptance** | SMTP 421/451 at a stage confirmed not to have accepted the message | Retry with backoff and quota |
| **Permanent rejection** | SMTP 550/554 per clear response | Stop or handle per recipient/provider policy |
| **Outcome unknown** | Connection lost after DATA before final response | Reconciliation; do not resubmit immediately |
| **Delivery deferred** | Provider accepted and is waiting to deliver to destination | Do not retry SMTP submission in the application |

SMTP codes and exceptions must be interpreted in context:
- SMTP command `MAIL FROM`, `RCPT TO`, or `DATA`;
- 4xx/5xx response code and enhanced status;
- nested cause (socket, TLS, Jakarta Mail);
- whether partial recipient acceptance occurred;
- whether the server already accepted end-of-DATA;
- provider documentation and policies.

Do not write:

```java
catch (MailException ex) {
    // Wrong: every send error can be safely retried.
    retryThroughAnotherProviderImmediately();
}
```

Calling `JavaMailSender.send(...)` can throw `MailSendException`, `MailAuthenticationException`, or other errors. The outermost exception class name **is not enough to conclude that no recipient received the message**. In particular, a connection lost after the relay receives DATA can yield an `UNKNOWN` outcome.

## 10. ProviderRouter: Route by Policy, Not by Guesswork

Do not let every business service choose `providerKey` from an arbitrary string.

A router can accept verified metadata:

```java
package com.example.mail;

public record RouteContext(
    String tenantId,
    MailCategory category,
    String fromDomain,
    String region
) {}

public interface ProviderRouter {
    String choosePrimary(RouteContext context);
}
```

Some valid rules:
- `TRANSACTIONAL` → Provider A;
- `MARKETING` → Provider B;
- `INTERNAL_ALERT` → internal relay;
- enterprise tenant with dedicated contract → dedicated profile;
- region permitted for data processing → provider in the corresponding region;
- provider under maintenance → select fallback route **if the notification has not yet been submitted and policy permits**.

### 10.1. A Rule Table Is Easier to Govern Than Scattered If-Chains

| Input | Allowed providers | Priority |
|---|---|---|
| Transactional, standard tenant | A, C | A first |
| Marketing, opted-in | B | B |
| Internal alert | Internal relay | Internal |
| Enterprise tenant X | Dedicated X | Dedicated |
| Not authorized to send | No provider | Reject |

The router must use tenant identity from the verified context, never trusting a `tenantId` arbitrarily supplied by the client.

### 10.2. Route Selection Should Be Stable for an Attempt

Persist the chosen `providerKey` alongside the attempt. If a job retries, the router may re-evaluate policy, but must record clearly:
- which provider the previous attempt used;
- why it is switching;
- whether there is evidence of non-acceptance;
- whether From/domain and recipient policies remain valid;
- whether the new account/quota allows it.

Do not pick a different provider every time solely because a list happened to change order.

## 11. Load Balancing Differs from Failover

Two strategies that are often conflated:

**Load balancing:** distributing **different logical emails** across multiple providers to use quotas or spread load.

**Failover:** when an attempt runs into trouble, considering switching **the same logical email** to another provider.

Example:

```text
Load balancing
  msg-100 -> A
  msg-101 -> B
  msg-102 -> A

Failover
  msg-100 attempt-1 -> A (not accepted, verified)
          attempt-2 -> B (SMTP_ACCEPTED)
```

Load balancing usually carries lower duplicate risk because each email has an active primary route. Failover requires verifying the outcome of the previous send attempt.

### 11.1. Do Not Fail Over Immediately After an Unknown-Outcome Timeout

A scenario:

```text
Application                    Provider A
   |---- SMTP DATA ------------>|
   |---- end-of-DATA ----------->|
   |                             | accepted to queue
   |<---- response lost ---------X
   |
   | timeout -> sends to Provider B
   v
Provider B accepts another copy
```

The recipient may receive **two emails**. If the classifier does not know whether A received it, save `UNKNOWN` and query provider logs/API/webhooks if available, or handle according to an approved risk-acceptance policy.

A common interface cannot turn generic SMTP into exactly-once.

### 11.2. When Can Failover Be Reasonable?

Cases that can be considered:
- Provider A is detected unavailable **before opening submission**.
- Connecting to A fails cleanly before transferring content/executing SMTP DATA.
- A returns an explicit rejection for the relevant recipient/stage, and policy allows sending through B.
- A is disabled by route policy before the job starts.
- The provider/API supports idempotency/reconciliation per contract and guarantees safe handling.

Still required:
- limit the number of fallback routes;
- check sender domain and data permissions;
- rate limits/quotas of provider B;
- do not automatically retry permanent errors such as invalid recipient;
- store attempt history;
- alert on abnormal failover.

### 11.3. Provider Accepted but Delivery Deferred

If A already accepted and provider A is retrying delivery because the receiver temporarily returned an error, **do not automatically resend via B**. Deferred is a provider downstream state, not a signal that application submission failed.

If you want to design a backup delivery channel for mission-critical emails, you need an explicit policy on duplicates, deadlines, recipient consent, and reconciliation capability—do not treat it as a default retry.

## 12. Outbox and Idempotency Across Multiple Providers

One way to organize it:

```text
Business event
   |
   v
DB transaction:
  business update
  email_outbox(messageKey, PENDING, category, templateVersion)
   |
   v
Outbox dispatcher
   |
   v
Claim email job
   |
   v
Route policy -> providerKey
   |
   v
mail_send_attempt(
    messageKey,
    attemptId,
    providerKey,
    status=SENDING
)
   |
   v
Submission adapter
   |
   +--> SMTP_ACCEPTED
   +--> RETRY_WAIT
   +--> FAILED_PERMANENT / DEAD_LETTER
   +--> UNKNOWN
```

### 12.1. Reference Schema

```sql
CREATE TABLE email_outbox (
    message_key         VARCHAR(64) PRIMARY KEY,
    business_event_key  VARCHAR(160) NOT NULL,
    tenant_id           VARCHAR(80) NOT NULL,
    category            VARCHAR(40) NOT NULL,
    status              VARCHAR(32) NOT NULL,
    next_attempt_at     TIMESTAMP NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

CREATE TABLE email_send_attempt (
    attempt_id          VARCHAR(64) PRIMARY KEY,
    message_key         VARCHAR(64) NOT NULL,
    provider_key        VARCHAR(80) NOT NULL,
    attempt_number      INTEGER NOT NULL,
    started_at          TIMESTAMP NOT NULL,
    finished_at         TIMESTAMP,
    outcome             VARCHAR(32) NOT NULL,
    safe_error_code     VARCHAR(120),
    provider_message_id VARCHAR(255),
    CONSTRAINT fk_attempt_message
        FOREIGN KEY (message_key)
        REFERENCES email_outbox(message_key),
    CONSTRAINT uq_attempt_number
        UNIQUE (message_key, attempt_number)
);
```

If the application needs delivery tracking:
- store provider events in a separate table;
- enforce uniqueness on an appropriate provider event ID;
- handle duplicate and out-of-order webhooks;
- map provider message ID/custom metadata back to the message key.

### 12.2. One Request Creates One Logical Email

When a client retries an HTTP request due to a timeout:
- use an `Idempotency-Key` and a unique constraint;
- do not create two outbox items if it is the same action;
- keep the same message key across all attempts;
- do not depend on whether A/B has SMTP-side idempotency.

If a **brand-new email** must be sent from a valid user request, create a new message key per business policy rather than treating it as a retry.

### 12.3. Claim and Lease

Two workers must never send the same outbox row concurrently. Use atomic claim/lease or appropriate broker visibility semantics. Fencing tokens prevent stale workers from overwriting DB state, but cannot retract an SMTP submission that already happened when a worker lost its lease.

Design timeouts/leases, retry budgets, and the `UNKNOWN` state together. Do not reset every expired-lease `SENDING` job back to `PENDING` for retransmission without a reconciliation policy.

## 13. SPF, DKIM, DMARC, and From Identity When Switching Providers

This is an often-overlooked failure: Provider B may accept SMTP AUTH successfully yet **not be authorized to send on behalf of the organization's domain**.

Example:
- Header From: `receipts@example.com`.
- Provider A signs DKIM with `d=example.com`.
- Provider B signs DKIM with `d=provider-b.example` by default.
- Provider B uses an envelope sender belonging to its own domain.

When sending via B, SPF and DKIM may pass for **the provider's domain**, but fail to align with Header From's `example.com`. DMARC may fail.

### 13.1. Before Activating a Fallback Provider

Verify:
1. The From domain is verified in account B.
2. SPF/return-path/bounce domain used on B is appropriate.
3. B's DKIM signer uses an aligned domain or another setup that makes DMARC pass.
4. DMARC policy is tested against real received emails.
5. Bounce/suppression/unsubscribe sync follows policy.
6. Emails are permitted to be sent from B's IPs/region under security policy.
7. B is authorized to send the right email category and has matching throughput limits.

**Successful SMTP login does not equate to sufficient domain authentication or deliverability.**

### 13.2. Header From Differs from Envelope MAIL FROM

In Spring:

```java
helper.setFrom("receipts@example.com");
```

typically sets the From header. The SMTP envelope sender can be controlled via Jakarta Mail's `mail.smtp.from` or configured automatically by the provider using a custom return-path/bounce domain. Do not manually add a `Return-Path` header thinking that changes SMTP `MAIL FROM`.

A common profile should store and validate:
- verified Header From;
- envelope sender policy;
- DKIM signing domain;
- allowed sender identities.

### 13.3. Suppression and Recipient Consent

If provider A has suppressed a recipient due to a hard bounce or spam complaint, switching to B must not be used to **bypass suppression**. The application needs a cross-provider policy/registry aligned with legal requirements, consent, and reputation protection.

For marketing, user opt-out must be enforced **before routing**, regardless of which provider is available.

## 14. Security in Multi-Provider and Multi-Tenant Systems

When using multiple profiles, the biggest risks are:
- choosing the wrong SMTP account;
- sending From using an unverified domain;
- leaking credentials across tenants;
- sending tenant A's data to an unapproved provider/region;
- SSRF from user-controlled SMTP hostnames;
- writing logs containing body, API tokens, or passwords;
- allowing failover to a service not approved by contract/consent.

### 14.1. Do Not Let HTTP Clients Specify Arbitrary SMTP Hosts

Do not expose an API like:

```json
{
  "smtpHost": "arbitrary-host.example",
  "smtpPort": 25,
  "smtpPassword": "client-supplied-secret",
  "recipient": "someone@example.net"
}
```

where the application trusts it directly and opens a connection. Beyond spam abuse, it can turn the server into an SMTP proxy/SSRF channel.

Instead:
- the caller selects a **business function**;
- the backend authenticates tenant and policy;
- the router picks a **provider key from an internal allowlist**;
- accounts/secrets are configured only by authorized admins;
- enforce DNS/IP/egress controls when dynamic SMTP hosts are required.

### 14.2. Tenant and Sender Profile Boundaries

A tenant may only use profiles associated with that tenant. Even when two tenants use the same provider brand, they can still have:
- different credentials;
- different From domains;
- different quotas and billing;
- different regions/data residency;
- different suppression lists.

Tests should cover scenarios where tenant X tries to request tenant Y's profile and is rejected before the adapter sends.

### 14.3. Secrets and TLS

For each SMTP profile:
- retrieve credentials from a protected environment/secret manager;
- keep `STARTTLS required` or implicit TLS matching the endpoint;
- enable hostname verification;
- trust valid CAs; do not use `ssl.trust=*`;
- configure socket timeouts;
- maintain a rotation procedure;
- do not log raw SMTP AUTH, passwords, or MIME bodies.

Do not weaken security just to speed up failover.

## 15. Provider Capability Model: Avoid Assuming Uniformity

Some systems need to distinguish what a provider supports:
- which SMTP AUTH methods;
- how far batch size/connection reuse goes;
- custom MAIL FROM;
- SMTPUTF8;
- message size limits;
- provider message ID;
- delivery webhooks;
- status lookup API;
- HTTP Email API idempotency key;
- differing throttling or quotas.

Verified capabilities can be described in config:

```java
public record ProviderCapabilities(
    boolean customEnvelopeSender,
    boolean supportsSmtpUtf8,
    boolean deliveryWebhook,
    boolean statusLookup,
    boolean apiIdempotency,
    long maxMessageBytes
) {}
```

**Note:** `apiIdempotency` pertains to a specific provider HTTP API; it does not mean the provider's generic SMTP transport automatically deduplicates. `statusLookup` and `deliveryWebhook` are likewise meaningful only when the account, metadata, and API permissions are properly configured.

Do not turn capability flags into guessed values. Govern them against real documentation/contracts and integration tests.

### 15.1. When Not to Force Every Provider Into the Same Adapter

If provider C supports sending via an HTTPS API with template IDs, batch jobs, and idempotency tokens, while A/B only have SMTP, you can still use a **common application port** while needing two adapter types:

```text
OutboundMailPort
    |
    +--> SmtpSubmissionAdapter
    |      -> JavaMailSender
    |
    +--> HttpEmailApiAdapter
           -> Provider API client
```

The application does not need to know the protocol in the business flow, but differing response/error mappings must be kept inside the adapter. Do not assume an email API has the same semantics as SMTP `250`, or that SMTP has every characteristic of an API.

## 16. Managing Timeouts, Quotas, Concurrency, and Backpressure

A provider may enforce:
- concurrent SMTP connection limits;
- messages/second limits;
- daily quotas;
- attachment limits;
- separate policies for transactional vs. marketing;
- rate limits by IP, account, or tenant.

If workers scale threads without bounds, the result can be:
- surges of `421`/`451`;
- piled-up TLS/AUTH handshakes;
- retry storms;
- heap growth from MIME attachments;
- duplicate deliveries to recipients after timeouts;
- other profiles impacted by one overloaded provider.

### 16.1. Limit Per Provider Rather Than One System-Wide Limit

Coordination example:

```text
Durable email outbox
       |
       v
Provider router
       |
       +--> Queue A -> A concurrency limit -> SMTP A
       |
       +--> Queue B -> B concurrency limit -> SMTP B
       |
       +--> Queue Internal -> Internal limit -> relay
```

Each provider has:
- concurrency semaphore/worker allocation;
- rate limiter;
- retry policy;
- circuit breaker/health signal;
- backlog/latency metrics;
- quota reservation or budget.

With multiple pods, a semaphore in one JVM only limits **a single instance**. Enforcing an account/provider-wide limit requires cross-instance coordination or explicit quota partitioning.

### 16.2. Retries Must Not Amplify Incidents

A provider unavailable for 5 minutes can cause huge numbers of jobs to become due at once. Use:
- exponential backoff with jitter;
- retry budgets by attempt count and elapsed time;
- circuit breakers or route disabling;
- concurrency limits;
- dead-lettering after budget exhaustion;
- `UNKNOWN` reconciliation instead of immediately sending via another provider.

Routing health should be a signal guiding decisions **before submission**, not treated as proof that a message in flight at another provider was definitely not received.

### 16.3. Timeouts and Leases Must Coordinate

For example, a 30-second socket read timeout with a 10-second worker lease can cause the job to be reclaimed before the old attempt finishes. If the new worker sends via another provider, duplicate risk rises.

Design:
- appropriate connect/read/write timeouts;
- leases long enough or heartbeats;
- fencing when writing DB results;
- handling of stale/unknown attempts;
- no retries when it is unknown whether upstream received the message.

## 17. Reusing JavaMailSender Without Sharing MIME Messages

A sender/profile can be shared across multiple services once configured. However, each email/attempt should create:
- a new `MimeMessage`;
- a new `MimeMessageHelper`;
- headers per message key and attempt ID;
- controlled data/attachment sources.

Do not keep a `MimeMessage` in a singleton field and mutate recipient/body per request. Doing so can cause misdirected emails and cross-tenant data leaks.

### 17.1. Reusing a Bean Does Not Mean Reusing a TCP Connection

`JavaMailSenderImpl` can hold a long-lived Jakarta Mail `Session` and configuration, yet **does not guarantee reusing the same SMTP socket across all `send(...)` calls**. Generic SMTP connection pooling does not magically appear just from having a singleton bean.

Multiple `MimeMessage` instances can be sent in one `send(messages...)` call to reduce part of the connect/TLS/AUTH overhead on supporting implementations, though partial failures must be handled per message. Do not batch multiple providers/tenants into one sender call.

### 17.2. Attachments and Inline Resources

For emails with attachments:
- validate file type/size and access permissions;
- distinguish plain/HTML/inline resources;
- use an `InputStreamSource` that can reopen the stream when needed;
- do not cache MIME emails containing one tenant's personal data for reuse by another tenant;
- bound heap and concurrency by message size.

If rerouting to another provider, ensure attachments still exist and business content still matches the approved snapshot. Providers may enforce different MIME size limits.

## 18. Cross-Provider Tracking: Use Application Identifiers

Do not use a provider message ID as the **sole key** of a logical email because:
- providers use different formats;
- a provider may not return an ID over generic SMTP;
- failover creates a new attempt;
- webhooks can arrive late or be incomplete;
- an email with multiple recipients needs separate tracking.

Recommendation:

```text
Application messageKey: msg-1001
  |
  +-- attempt att-A
  |      provider: A
  |      outcome: RETRYABLE_FAILURE
  |
  +-- attempt att-B
         provider: B
         outcome: SMTP_ACCEPTED
         providerMessageId: optional
         |
         +-- delivery event: deferred
         +-- delivery event: delivered
```

### 18.1. Tracing Headers

The adapter can add:

```java
mime.setHeader(
    "X-Application-Message-Key",
    command.messageKey()
);
mime.setHeader(
    "X-Mail-Attempt-ID",
    attemptId
);
```

They help reconciliation when the provider preserves headers, but recipients can inspect raw headers. Do not include:
- secrets;
- tenant authentication tokens;
- sensitive data;
- internal database IDs if they expose structure or security details.

This is **tracing**, not SMTP-level idempotency.

### 18.2. Webhooks Differ from SMTP Receipts

One provider may emit `delivered`, `bounced`, `deferred`; another may offer no webhooks at all. Normalize events when data is available:

```java
public enum DeliveryEventType {
    DEFERRED,
    DELIVERED,
    BOUNCED,
    DROPPED,
    COMPLAINT
}
```

Still store raw provider events/references in an appropriately protected area for diagnostics. Do not infer `DELIVERED` when the provider only returned `SMTP_ACCEPTED`.

### 18.3. Webhooks Must Handle Duplicates and Out-of-Order Delivery

- Verify signatures/provider authentication.
- Deduplicate by provider-supplied event ID.
- Link provider-specific IDs back to message key/attempt.
- Keep event history.
- Do not let a late-arriving deferred event overwrite a confirmed delivered state.
- Do not let a webhook from provider A mutate the state of an attempt on B.
- Protect recipients and bounce reasons from unauthorized access.

## 19. Testing the Common Abstraction with Unit Tests

Unit tests should isolate the router, adapter, and orchestration. No real SMTP server is needed to test provider selection logic.

### 19.1. Testing Routing

Example of a simple policy router:

```java
public final class StaticProviderRouter
        implements ProviderRouter {

    @Override
    public String choosePrimary(RouteContext context) {
        return switch (context.category()) {
            case TRANSACTIONAL, SECURITY -> "primary";
            case MARKETING -> "secondary";
            case INTERNAL_ALERT -> "alerts";
        };
    }
}
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class StaticProviderRouterTest {

    @Test
    void routesTransactionalMailToPrimary() {
        ProviderRouter router = new StaticProviderRouter();

        RouteContext context = new RouteContext(
            "tenant-test",
            MailCategory.TRANSACTIONAL,
            "example.com",
            "allowed-region"
        );

        assertThat(router.choosePrimary(context))
            .isEqualTo("primary");
    }
}
```

In a real system, the router needs to enforce tenant/profile allowlists, category policies, and regions. `StaticProviderRouter` only illustrates separating routing from SMTP transport.

### 19.2. Testing the Adapter Using a Mock Sender and Real MIME

```java
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.Properties;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class MultiSmtpAdapterTest {

    @Test
    void choosesExpectedSenderAndBuildsMessage() {
        JavaMailSender primary = mock(JavaMailSender.class);

        MimeMessage mime = new MimeMessage(
            Session.getInstance(new Properties())
        );
        when(primary.createMimeMessage()).thenReturn(mime);

        ProviderRegistry registry = new ProviderRegistry(
            Map.of(
                "primary",
                new SmtpProviderBinding(
                    "primary",
                    "receipts@example.com",
                    primary
                )
            )
        );

        Clock fixedClock = Clock.fixed(
            Instant.parse("2026-11-12T08:00:00Z"),
            ZoneOffset.UTC
        );

        MailFailureClassifier classifier =
            (providerKey, ex) -> new SubmissionFailure(
                FailureCategory.UNKNOWN,
                "SMTP_UNKNOWN",
                providerKey,
                ex
            );

        MailSubmissionPort port =
            new MultiSmtpSubmissionAdapter(
                registry, classifier, fixedClock
            );

        EmailCommand command = new EmailCommand(
            "msg-1001",
            "tenant-test",
            MailCategory.TRANSACTIONAL,
            "customer@example.net",
            "Order confirmation",
            "Hello Nguyen Thi Anh.",
            "<p>Hello Nguyen Thi Anh.</p>",
            "v1"
        );

        SubmissionReceipt receipt =
            port.submit(command, "primary", "att-1");

        verify(primary).send(mime);

        assertThat(receipt.providerKey())
            .isEqualTo("primary");
        assertThat(receipt.messageKey())
            .isEqualTo("msg-1001");

        assertThat(mime.getSubject())
            .isEqualTo("Order confirmation");
    }
}
```

This example verifies:
- the adapter retrieves the right sender;
- builds MIME in memory;
- sends through the mock without an SMTP connection;
- records the right provider/message key in the receipt.

The test can be extended to capture `From`, `To`, text/plain, text/html, charset, and headers. It **does not prove a real SMTP provider accepted the message**.

### 19.3. Testing Isolation Between Providers

With two mock senders, tests should assert:
- primary route invokes only sender A;
- secondary route invokes only sender B;
- an unauthorized tenant causes **no sender to be invoked**;
- a non-existent route is rejected;
- From/credentials of another profile are never altered.

A single happy-path route test is insufficient when the system has multiple tenants or sensitive categories.

## 20. Integration Tests with Two SMTP Endpoints

To prove the abstraction works across two SMTP profiles, use **two SMTP sandbox instances** or a test harness capable of observing messages independently.

```text
Integration test
       |
       v
ProviderRouter + MultiSmtpAdapter
       |
       +--> JavaMailSender A -> SMTP test server A
       |
       +--> JavaMailSender B -> SMTP test server B
```

Key cases:
1. Route A sends one email; only SMTP server A receives it.
2. Route B sends one email; only SMTP server B receives it.
3. From, Reply-To, and envelope sender follow account policy.
4. STARTTLS/implicit TLS matches the endpoint if the SMTP test harness supports it.
5. Invalid certificates or hostnames are rejected without plaintext fallback.
6. Provider A returns a transient error before DATA: the workflow records controlled retry/failover.
7. Provider A disconnects after DATA: outcome is `UNKNOWN`, not automatically sent via B.
8. Provider B is rate-limited: workers cap concurrency/retries.
9. Batch with partial failure: accepted messages are not retried.
10. App restarts do not lose outbox/provider attempt history.

### 20.1. SMTP Sandboxes Cannot Always Simulate Every Error

GreenMail, Mailpit, or another fake SMTP server can verify the happy path, MIME, and routing. However, not all of them support:
- 451 response at RCPT TO;
- 421 response at connect;
- disconnecting right after the end-of-DATA marker;
- partial recipient acceptance;
- server timeouts/mTLS.

To test errors at each phase, an appropriate **fault-injecting SMTP server** is needed. Never trigger outages on a production provider just to prove retries.

### 20.2. Database Integration Tests Need a Real Backend

If the goal is testing atomic claims, unique constraints, outbox durability, and dead-lettering, use the production-equivalent PostgreSQL/MySQL (for example via Testcontainers) rather than mocking the repository and calling it an integration test.

SMTP sandboxes test transport; database Testcontainers test persistence; provider E2E tests delivery/events against authorized sandbox accounts.

## 21. Failover Test Cases Must Be Especially Strict

A guiding matrix:

| Scenario on Provider A | Can send immediately via B? | Why |
|---|---|---|
| Router selects B before A is called | Yes, if B is permitted | No submission to A occurred. |
| A is disabled before attempt with no side effects | Yes | No copy is being processed by A. |
| TCP connect to A definitely failed, no DATA sent | Possible | Still must check retry budget and B policy. |
| A returns explicit 451 before acceptance | Possible after backoff/policy | Transient error, but avoid retry storms. |
| A permanently rejects recipient | Not automatically | May be an address/policy error; B must not be used to bypass it. |
| A accepted SMTP submission | No | A has taken responsibility for handing off the message. |
| A accepted then reported deferred | No | Provider is retrying delivery. |
| Timeout after end-of-DATA, no reply seen | **Not automatically** | `UNKNOWN` outcome, duplicate risk. |
| A returns authentication failure | Not just because B is alive | Must evaluate secret/config and account-switching authorization. |
| B lacks aligned DKIM/verified From | No | Can cause DMARC failure or violate domain policy. |
| Recipient already hard-bounced/opted out | No | Must not bypass suppression via another provider. |

Tests should assert not only "whether B was called," but also:
- attempt count;
- provider route history;
- status in outbox;
- retry due time;
- error category;
- log/audit events;
- suppression and authorization checks.

## 22. Operations and Observability Per Provider

A common abstraction needs logs/metrics detailed enough to isolate per-provider failures.

| Metric | Meaning |
|---|---|
| `mail_submit_attempts_total{provider,outcome}` | Attempt counts by provider and outcome |
| `mail_submit_duration_seconds{provider}` | Submission latency |
| `mail_route_selected_total{provider,category}` | Traffic distribution |
| `mail_provider_failover_total{from,to,reason}` | Failover count and reason |
| `mail_provider_circuit_state{provider}` | Circuit breaker state |
| `mail_provider_active_connections{provider}` | Active connections if genuinely measurable |
| `mail_outbox_age_seconds{category}` | Backlog/latency |
| `mail_unknown_total{provider}` | Outcomes requiring reconciliation |
| `mail_dead_letter_total{reason}` | Jobs stopped automatically |
| `mail_delivery_events_total{provider,type}` | Delivered/deferred/bounced/complaint if provider supports |

The metrics above use illustrative names. Not every provider exposes accurate active SMTP connection counts, because `JavaMailSender` does not expose a uniform connection pool metric.

### 22.1. Structured Logging

```json
{
  "event": "mail.submission_attempt",
  "messageKey": "msg-1001",
  "attemptId": "att-2",
  "providerKey": "secondary",
  "category": "TRANSACTIONAL",
  "outcome": "SMTP_ACCEPTED",
  "durationMs": 821,
  "routeReason": "approved-failover"
}
```

Avoid logging:
- SMTP usernames/passwords or OAuth access tokens;
- raw MIME bodies/attachments;
- recipient emails unless necessary and protected;
- verification/reset tokens;
- secret IDs or sensitive connection properties.

### 22.2. Actionable Alerts

- Provider A has a sudden spike in 4xx or TLS failures.
- Quota is running low or rate limits are hit repeatedly.
- Failover rises unexpectedly.
- `UNKNOWN` backlog lingers without reconciliation.
- Provider B loses DKIM alignment or domain verification expires.
- Hard bounces/complaints climb on a route.
- Outbox backlog exceeds SLA.
- A tenant uses the wrong SMTP identity.
- Provider delivery webhooks stop arriving.

Alerts should answer "which route broke, which logical emails are affected, do we need a config fix or to wait," rather than merely saying "mail service unavailable."

## 23. Process for Adding a New Provider

A practical rollout checklist:

### 23.1. Provisioning and Security

- [ ] Create an SMTP account following least privilege.
- [ ] Verify SMTP host/port, TLS mode, and AUTH.
- [ ] Store secrets in a secret manager, never hardcode.
- [ ] Enable hostname verification/valid trust chain.
- [ ] Configure socket timeouts and quota/concurrency settings.
- [ ] Restrict where workloads are allowed to connect to the provider.

### 23.2. Domain and Deliverability

- [ ] Verify authorization to use the From domain.
- [ ] Configure envelope sender/custom bounce domain per provider.
- [ ] Configure DKIM signing with an aligned domain.
- [ ] Verify SPF/DKIM/DMARC using a test mailbox.
- [ ] Synchronize suppression/unsubscribe/complaint policies.
- [ ] Separate transactional vs. marketing reputation/traffic.

### 23.3. Application Integration

- [ ] Add the profile to the registry without hardcoding in business services.
- [ ] Declare tenant/category/region permissions.
- [ ] Test that the router picks the right route.
- [ ] Test submission and MIME through an SMTP sandbox.
- [ ] Test the classifier on realistic provider errors.
- [ ] Confirm retry/failover does not duplicate in `UNKNOWN` cases.
- [ ] Persist provider key on every attempt.
- [ ] If webhooks/APIs exist, protect ID mapping and event ingestion.

### 23.4. Rollout

- [ ] Run a smoke test to an authorized mailbox.
- [ ] Roll out controlled low-volume traffic.
- [ ] Monitor latency, 4xx/5xx, bounces, and complaints.
- [ ] Confirm rate limits and quotas.
- [ ] Have a kill switch to disable the provider/roll back routing.
- [ ] Do not fail over the entire backlog while submission states are unknown.
- [ ] Document the profile owner, incident runbook, and secret rotation.

## 24. Common Design Mistakes

### "One common interface means all providers behave identically"

No. A common interface holds only semantics that are genuinely equivalent. Credentials, bounces, quotas, webhooks, and idempotency can differ; the abstraction must expose capabilities or adapter-specific handling appropriately.

### "Successful SMTP AUTH means any From domain can be used"

No. A provider may only accept verified senders; receiving MTAs also check SPF/DKIM/DMARC. Domain authentication must be verified on **every intended route**.

### "On any exception, immediately try Provider B"

No. If A already received DATA while the app lost the response, B can create a duplicate. An `UNKNOWN` outcome needs reconciliation or a documented risk-acceptance decision.

### "Just swap host/username on a singleton before each request"

No. Mutable configuration can get mixed across threads and tenants. Use stable profiles, a registry, or an explicit lifecycle design.

### "Using the same RFC Message-ID on A and B makes SMTP dedupe automatically"

No. RFC Message-ID and custom message keys are not an idempotency protocol guaranteed by SMTP.

### "Provider deferred means switch providers"

No. After SMTP accepted, the provider can retry delivery itself. Deferred does not mean submission failed.

### "One outbox status is enough"

Not really. You need attempt history with provider key and error category to know where a message was sent, whether it was accepted or unknown, and whether replaying is safe.

### "Every provider receives an equal share of load"

No. Quotas, reputation, regions, categories, SLAs, and actual health differ. The router must follow policy, not mere randomness.

### "Spinning up more workers optimizes throughput"

No. Increasing workers can exceed quotas, trigger 4xx responses, and cause retry storms. Rate limiters, concurrency limits, backlog metrics, and benchmarks matter more than raw thread counts.

### "Unit testing with a mock sender is enough to test multi-provider"

No. Unit tests validate policy/adapter logic, whereas routing across two SMTP endpoints, TLS, partial failures, and database outboxes require dedicated integration tests.

## 25. Practice Exercises

### Exercise 1 — Design a Common Port

Create `EmailCommand`, `MailSubmissionPort`, `SubmissionReceipt`, and `SubmissionFailure`. Clearly explain why the receipt only represents SMTP submission accepted, not delivered.

### Exercise 2 — Two SMTP Profiles

Configure two providers in `application.yml`, one with STARTTLS on port 587 and one with implicit TLS on port 465. Build an immutable `ProviderRegistry` and verify a non-existent provider key cannot be selected.

### Exercise 3 — Adapter Using JavaMailSender

Write an adapter that looks up the sender from the registry, creates a fresh `MimeMessage`, and attaches message key and attempt ID. Unit test with Mockito without calling a real SMTP server.

### Exercise 4 — Router by Email Category

Route `TRANSACTIONAL` to A, `MARKETING` to B, and `INTERNAL_ALERT` to the relay. Test every case with JUnit.

### Exercise 5 — Tenant Permissions

A tenant may only use its own sender profile. Write a test proving another tenant cannot force the router to select this tenant's credentials/account.

### Exercise 6 — Domain Verification

Provider A has DKIM `d=example.com`, while Provider B uses `d=vendor.example`. With Header From `receipts@example.com`, analyze why switching to B can fail DMARC and how to configure provider B validly.

### Exercise 7 — SMTP 451 Error

Have A return a confirmed transient error before DATA. Test a retry policy with backoff and attempt limits; if policy allows failover, verify B is used only when conditions are met.

### Exercise 8 — Timeout After DATA

Simulate A possibly receiving DATA while the client times out. Test that the job moves to `UNKNOWN`, **B is not invoked**, and a reconciliation record is created.

### Exercise 9 — Provider Deferred

After A accepted, receive a deferred webhook. Test that no second submission is created through B. Then receive delivered and update the delivery status properly.

### Exercise 10 — Outbox Attempts

Design SQL to store two attempts with the same message key but different providers. Verify uniqueness on `(message_key, attempt_number)`, preserving history even after the job completes.

### Exercise 11 — Rate and Concurrency

Assume A has lower limits than B. Design a dispatcher with per-provider concurrency/rate limits; explain why a semaphore inside each pod does not limit the whole cluster.

### Exercise 12 — Secret Rotation

Rotate provider A's credentials while multiple workers are sending. Propose how to build a new sender/profile and shift traffic in a controlled way without mutating a singleton.

### Exercise 13 — SMTP Integration with Two Servers

Use two SMTP test servers. Route email A to endpoint A and B to endpoint B; confirm each server receives only messages routed to it.

### Exercise 14 — System-Wide Suppression

Provider A flags a hard bounce/complaint. Prove the router does not let marketing email switch to B to bypass suppression if the recipient is no longer eligible.

### Exercise 15 — Provider HTTP API

Add an HTTP Email API adapter under the same application port. Identify capabilities only the HTTP API can support such as idempotency key, provider ID, and status lookup; do not force them onto generic SMTP.

### Exercise 16 — Out-of-Order Webhooks

Simulate a `delivered` event followed by a late older `deferred` event from A. Design event history, deduplication, and a state machine so state never regresses.

### Exercise 17 — Incident Recovery

A suffers an outage, B has domain verification ready, and there are 2,000 queued jobs and 30 `UNKNOWN` jobs. Plan shifting **only unsubmitted jobs** to B within quota while keeping `UNKNOWN` jobs for reconciliation instead of resending everything.

### Exercise 18 — Performance Observability

Design metrics/dashboards separating A, B, and internal relay: queue age, submit p95, 4xx/5xx, failover rate, unknown count, and provider delivery events.

## 26. Summary

**A common abstraction for multiple SMTP providers** lets Spring Framework Mail separate business decisions from provider configuration, protocols, and quirks. Its purpose is not to hide every difference, but to **standardize the right shared parts while keeping visible the differences that determine email-sending safety**.

Key principles:

1. The business layer creates a **logical email** with a message key; it does not directly touch `JavaMailSenderImpl` or SMTP credentials.
2. `ProviderRouter` determines routing by tenant, category, domain, region, and policy; `ProviderRegistry` holds safely configured sender profiles.
3. `MailSubmissionPort` standardizes submission outcomes; the Spring adapter uses `JavaMailSender` and creates a fresh `MimeMessage` per attempt.
4. **Reuse sender profiles, but never mutate a singleton during concurrent sends**, nor share a mutable `MimeMessage` across emails.
5. Do not confuse `SMTP_ACCEPTED` with `DELIVERED`. After acceptance, the provider may still be retrying delivery.
6. **Fail over only when safe.** Timeouts with unclear outcomes must stay `UNKNOWN` for reconciliation; sending immediately through provider B can cause duplicates.
7. Every fallback provider must have **verified From, SPF/DKIM/DMARC alignment, suppression policy, TLS, and quotas** prepared before receiving traffic.
8. Outbox, idempotency, attempt history, and provider-specific IDs enable tracing, retries, and operations across routes.
9. Test policy/adapters with mocks and in-memory MIME; test multiple SMTP endpoints, TLS, database persistence, and failure injection in an integration suite.
10. Measure per provider, set rate/concurrency limits, and maintain an incident runbook; **never assume adding a provider automatically increases throughput or deliverability**.

When the boundaries are designed properly, you can swap providers, add tenant profiles, or open fallback routes without rewriting every business service, while still preserving control over domain identity, email states, and duplicate-send risk.
