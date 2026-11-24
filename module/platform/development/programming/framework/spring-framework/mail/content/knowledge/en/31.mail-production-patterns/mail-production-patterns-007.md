# Provider Adapters and Fallback Strategies

## 1. The production problem: sending email without vendor lock-in

In a **Spring Framework Mail** application, the simplest way to send email is configuring one `JavaMailSender` and calling `send(...)`. However, as the system grows, a single SMTP endpoint can become a bottleneck:

- The provider suffers downtime or network outages.
- The account hits rate limits, quotas, or concurrent connection caps.
- Security emails require different priority than marketing emails.
- One provider offers rich feedback APIs/webhooks while another only supports SMTP/DSN.
- Customers/tenants have distinct data-residency, sender-domain, or contractual requirements.
- The system needs phased provider migrations, canary rollouts, or backup routes when the primary is unavailable.

If business code directly invokes a vendor SDK or `JavaMailSenderImpl` everywhere, every provider change requires touching many modules. Worse, writing `try { send(A); } catch (...) { send(B); }` without knowing A's submission outcome can deliver **two emails** to the recipient.

**Provider adapters** solve technical coupling: the application calls a stable contract, while each adapter knows how to speak SMTP or HTTP APIs with a specific provider.

**Fallback strategies** solve selection: when the chosen provider is unavailable, may the system switch providers, under what conditions, do data policies and sender identities still hold, and can it prove the prior path did not already accept the message?

~~~text
Business event / Notification service
                |
                v
          Durable mail outbox
                |
                v
           Routing policy
          (type/region/tenant)
                |
                v
       Provider capability filter
                |
                v
           Attempt planner
                |
           +----+------+
           |           |
           v           v
      SMTP adapter   HTTP API adapter
           |           |
           v           v
       Provider A    Provider B
           |           |
           +-----+-----+
                 |
                 v
       Normalized submission result
                 |
     +-----------+------------+
     |           |            |
     v           v            v
  ACCEPTED    REJECTED      UNKNOWN
                 |            |
                 v            v
          Retry/fallback    Reconcile
             if safe         before resend
                 |
                 v
      Attempt history + telemetry
~~~

> **Important limitation:** Adapters and fallbacks **do not create exactly-once delivery** for SMTP. A timeout after submitting a message can leave an unknown outcome; switching immediately to another provider can send duplicates. Production designs must model `UNKNOWN`, idempotency, and reconciliation rather than treating every exception as "not sent."

## 2. Distinguishing adapters, routers, fallbacks, and retries

These concepts are related but do not replace one another.

| Component | Responsibility | Example |
| --- | --- | --- |
| **Provider adapter** | Translates internal contract to specific SMTP or API; normalizes outcomes | `SmtpMailProviderAdapter`, `HttpMailProviderAdapter` |
| **Provider registry** | Looks up adapters and capabilities by provider ID | `smtp-vn-tx-a` → SMTP adapter |
| **Routing policy** | Determines the *permitted* provider set by category/region/tenant/identity | `SECURITY/EU` email → EU critical pool |
| **Selection policy** | Picks a provider from the eligible set by priority/weight/quota/health | Pick primary with remaining capacity |
| **Retry policy** | Decides whether to retry an operation after a temporary error | 30 s backoff, max 5 attempts |
| **Fallback policy** | Decides whether switching to another provider is permitted | A failed pre-submission, B is approved |
| **Circuit breaker** | Temporarily stops calling a degraded provider | A circuit open for a cooldown window |
| **Outbox/attempt store** | Persists send intents and per-attempt history | `PENDING`, `SENDING`, `ACCEPTED`, `UNKNOWN` |
| **Feedback adapter** | Normalizes delivery/bounce/complaint webhooks/DSNs from providers | `hard_bounce` → central suppression |

### 2.1. Retry differs from fallback

~~~text
Attempt #1 -> provider A -> DEFINITE_RETRYABLE_FAILURE

Retry:
  Attempt #2 -> provider A

Fallback:
  Attempt #2 -> provider B
~~~

Fallback **normally creates a new attempt**, so it still counts toward retry/deadline limits rather than bypassing `max_attempts` merely by switching providers.

### 2.2. Fallback differs from load balancing

**Load balancing** spreads *new messages* across multiple eligible providers to distribute load. **Fallback** reroutes after signals show the first provider cannot serve a specific request. A policy can combine both, provided it remains auditable:

~~~text
routeReason = PRIMARY_SELECTED
routeReason = WEIGHTED_SELECTION
routeReason = PRIMARY_CIRCUIT_OPEN
routeReason = APPROVED_FALLBACK_AFTER_PRE_SUBMISSION_FAILURE
~~~

Never lump every reason into `provider_used=B` and lose track of whether B ran due to load balancing or A's failure.

### 2.3. "Provider available" does not mean "provider eligible"

A provider may be online yet fail to satisfy:

- Approved regional data-processing requirements.
- Sender identity, From domain, and DKIM verification.
- Email category (`SECURITY`/`TRANSACTIONAL`/`MARKETING`).
- MIME message size, attachment types, and recipient count.
- Tenant permissions, contracts, and quotas.
- TLS/authentication, logging, and retention requirements.

**Right order:** determine the **allowed provider set** first, then evaluate health, quotas, and selection. Never let a circuit breaker or "cheapest route" algorithm override security policies.

## 3. Scenarios requiring extreme caution before fallback

### 3.1. Failures before sending DATA

~~~text
App -> SMTP A: connect
        X connection refused

No SMTP message submission occurred.
~~~

If proven that **no message was submitted** to A, the application can consider Provider B per policy, deadline, and capacity. However, JavaMail/Jakarta Mail exceptions may not always expose a normalized stage; adapters must state stage-detection confidence and emit `UNKNOWN` when uncertain.

### 3.2. SMTP 5xx recipient errors

~~~text
App -> SMTP A: RCPT TO:<invalid@example.net>
A   -> App: 550 user unknown
~~~

This is usually a permanent recipient error. Switching to B will not make an invalid address valid and may cause spam/suppression violations. Never auto-fallback on every 5xx error.

### 3.3. Timeout after SMTP DATA

~~~text
App -> SMTP A: DATA
App -> SMTP A: [complete MIME body]
A   -> App: [connection drops before final response]
~~~

The application **does not know** whether A accepted it. If B is called immediately:

~~~text
A may deliver email
B may also deliver email
          |
          v
        Duplicate
~~~

`Message-ID` helps correlation, yet there is no universal SMTP contract guaranteeing relays deduplicate by this header.

### 3.4. SMTP accepts, yet database commit fails

~~~text
A accepts message -> send(...) returns
                   |
                   v
DB update markAccepted fails
                   |
                   v
Outbox appears due after lease expires
                   |
                   v
Blind retry through A/B -> duplicate possible
~~~

A transactional outbox commits *send intent* alongside business data, yet creates no distributed transaction between DB and SMTP. You need reconciliation for "accepted but state unsaved" or equivalent uncertainty windows.

### 3.5. Provider HTTP APIs with idempotency keys

Some HTTP API providers support idempotency keys so repeating a request with the same key avoids creating a second submission, yet this is **specific to each API and contract**:

- How long is the key valid?
- How are same-key/different-payload requests handled?
- Is the key scoped by account, endpoint, or tenant?
- Does retrying after a timeout return the old provider message ID?

Never assume every HTTP provider supports this, or that API idempotency guarantees the email reached the inbox.

## 4. Define a shared contract before writing adapters

A good contract is generic enough to keep vendor details out of domain code without erasing critical differences between SMTP and HTTP APIs.

### 4.1. Business commands differ from wire requests

A use case may prepare:

~~~text
MailDeliveryCommand
  deliveryId
  tenantId
  category
  region
  recipient
  sendingIdentity
  templateKey + templateVersion
  renderedBody / immutable model reference
  attachments (durable references)
  businessDeadline
  idempotencyKey
~~~

This is validated, authorized business data—not an SMTP envelope or vendor-specific JSON. The adapter receives a **prepared, eligibility-checked request** and builds the matching wire message.

### 4.2. Keep business policies out of adapters

Do not scatter rules like "if the customer is in the EU, never send via US" inside individual vendor adapters. The router/policy layer owns data-residency rules, while adapters double-check technical capabilities and refuse requests that exceed clear limits.

If Adapter A allows a route Adapter B forbids, auditing full policy compliance becomes hard and fallbacks break unexpectedly.

### 4.3. Lifecycle of a delivery

~~~text
PREPARED
   |
   v
PENDING  ----> ROUTE_SELECTED
                 |
                 v
             ATTEMPTING
                 |
       +---------+----------+---------------+
       |                    |               |
       v                    v               v
     ACCEPTED           DEFINITE_FAIL     UNKNOWN
       |                    |               |
       v                    v               v
  Mark accepted       RETRY or FAILED   RECONCILE/HOLD
                            |
                            v
                     Approved fallback?
                       |          |
                      Yes         No
                       |          |
                       v          v
                  New attempt   Wait/terminal
~~~

In this model, `ACCEPTED` means the provider **accepted the submission**, not guaranteed delivered-to-inbox. Bounces, complaints, and delivery feedback are separate post-submission states.

## 5. Designing classifiable return results

Never return a `boolean sent`, because `false` cannot express the difference between permanent errors, temporary errors, and unknown outcomes.

Illustrative result types:

~~~java
package com.example.mail.provider;

import java.time.Instant;

public enum SubmissionOutcome {
    ACCEPTED,           // Provider accepted submission.
    DEFINITE_REJECTED,  // Provider definitely did not accept it.
    UNKNOWN             // Submission result cannot be proven.
}

public enum RejectionKind {
    TRANSIENT,
    PERMANENT,
    POLICY,
    CAPACITY,
    UNCLASSIFIED
}

public record ProviderSubmissionResult(
        String providerId,
        SubmissionOutcome outcome,
        RejectionKind rejectionKind,
        String safeCode,
        String providerMessageId,
        Instant observedAt) {
}
~~~

These are **application-designed types**, not built-in Spring Mail APIs. In Java, top-level `public` enums/records belong in separate source files.

Invariants enforceable in factories/constructors:

- `ACCEPTED` never carries `RejectionKind.PERMANENT`.
- `DEFINITE_REJECTED` is only used with proof the provider **did not accept the submission**.
- `UNKNOWN` is never collapsed into a transient error.
- `providerMessageId` may be `null`, especially for plain SMTP.
- `safeCode` comes from a bounded catalog, never raw exceptions or user bodies.

### 5.1. Submission outcomes and mailbox delivery status are two separate layers

~~~text
Submission:
  ACCEPTED by provider A
        |
        v
Provider later:
  delivered / deferred / hard-bounced / complained
~~~

Never set `outbox.status=FAILED` just because a `deferred` webhook arrives while the provider is still trying delivery. Separate submission history from downstream delivery feedback and apply proper event ordering/idempotency.

## 6. MailProviderAdapter interface and inputs

An internal interface can support both SMTP and HTTP APIs:

~~~java
package com.example.mail.provider;

public interface MailProviderAdapter {

    String providerId();

    ProviderCapabilities capabilities();

    ProviderSubmissionResult submit(
            PreparedMailSubmission request);
}
~~~

`PreparedMailSubmission` is **a single mail submission that has already passed routing and validation**. It never takes unverified input from an unauthorized HTTP request to pick a provider.

### 6.1. PreparedMailSubmission

Java 17 record example:

~~~java
package com.example.mail.provider;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record PreparedMailSubmission(
        UUID deliveryId,
        UUID attemptId,
        String recipient,
        String fromAddress,
        String replyToAddress,
        String subject,
        String plainText,
        String htmlText,
        String idempotencyKey,
        List<AttachmentRef> attachments,
        Instant deadline) {

    public PreparedMailSubmission {
        if (deliveryId == null || attemptId == null
                || recipient == null || recipient.isBlank()
                || fromAddress == null || fromAddress.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required prepared mail data");
        }
        attachments = attachments == null
                ? List.of()
                : List.copyOf(attachments);
    }
}

public record AttachmentRef(
        String displayName,
        String contentType,
        String storageKey,
        String versionId,
        long contentLength) {
}
~~~

Each `public` record needs its own Java file. The constructor above checks only basic invariants; production also validates email syntax with a proper parser, checks header injection, authorized recipient/tenant, sender identity, MIME content, max size, attachment access, and business deadlines.

### 6.2. Never pass open InputStreams through queues

For asynchronous sending with retries, commands must never hold `InputStream`, `MimeMessage`, or HTTP request `MultipartFile` objects:

~~~text
HTTP request uploads file
           |
           v
Secure storage
  object key + immutable version + checksum
           |
           v
Outbox contains attachment reference
           |
           v
Worker resolves source at send attempt
~~~

Request-scoped streams and temp files do not survive process restarts. `AttachmentRef` must point to content that stays **valid and re-readable** across the attempt/retry window. For large files, prefer `FileSystemResource` over an immutable snapshot or an `InputStreamSource` that opens a fresh stream per read; avoid materializing whole files onto the heap just to pass through adapters.

### 6.3. ProviderCapabilities

~~~java
package com.example.mail.provider;

import java.util.Set;

public record ProviderCapabilities(
        String providerId,
        Set<String> allowedRegions,
        Set<String> allowedMailCategories,
        Set<String> verifiedSendingIdentityIds,
        long maxMessageBytes,
        int maxRecipientsPerSubmission,
        boolean supportsIdempotentSubmit,
        boolean hasDeliveryFeedback) {
}
~~~

Capabilities are configured by operations/adapters **according to real provider contracts**. Never infer from a hostname like `smtp-eu.example.net` that data is always processed/stored in the EU. Region approval must reflect actual data-processing contracts and policies, including logs, backups, webhooks, and subprocessors where applicable.

### 6.4. Do not try to hide every provider difference

A misleading abstraction:

~~~java
boolean sendEmail(String to, String subject, byte[] bytes);
~~~

It cannot express:

- HTTP 202 accepted yet not delivered.
- SMTP timeout after DATA with `UNKNOWN` outcome.
- Partial recipient failures.
- Provider API idempotency keys and lifetimes.
- Feedback event correlation.
- Provider rejection due to unverified `From` identity.
- Quotas, attachment size caps, and regional restrictions.

Adapters can unify **primary inputs and outcomes**, while still exposing controlled metadata/capabilities.

### 6.5. Recipient identity and per-delivery sending

One `PreparedMailSubmission` should represent **one recipient** when the application needs accurate tracking and fallback. With multi-recipient messages:

~~~text
one MIME:
  To A, B, C
  SMTP relay accepts A, rejects B, defers C
~~~

The result is no longer a simple boolean. Spring Mail/Jakarta Mail may expose per-recipient failure details depending on exception/transport, yet adapters still have to normalize per recipient. A cleaner approach for critical notifications is creating three **delivery records** and handling each recipient independently.

## 7. SMTP provider adapter using JavaMailSender

An SMTP adapter built on `org.springframework.mail.javamail.JavaMailSender` decouples SMTP from domain code. Configuration creates **one sender per provider/identity as needed**, never mutating host/credentials on a singleton per send.

### 7.1. SMTP adapter skeleton

~~~java
package com.example.mail.provider.smtp;

import java.time.Clock;
import java.util.Objects;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import com.example.mail.provider.MailProviderAdapter;
import com.example.mail.provider.PreparedMailSubmission;
import com.example.mail.provider.ProviderCapabilities;
import com.example.mail.provider.ProviderSubmissionResult;
import com.example.mail.provider.RejectionKind;
import com.example.mail.provider.SubmissionOutcome;

public final class SmtpMailProviderAdapter
        implements MailProviderAdapter {

    private final String id;
    private final JavaMailSender sender;
    private final ProviderCapabilities capabilities;
    private final Clock clock;

    public SmtpMailProviderAdapter(
            String id,
            JavaMailSender sender,
            ProviderCapabilities capabilities,
            Clock clock) {
        this.id = Objects.requireNonNull(id);
        this.sender = Objects.requireNonNull(sender);
        this.capabilities = Objects.requireNonNull(capabilities);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public String providerId() {
        return id;
    }

    @Override
    public ProviderCapabilities capabilities() {
        return capabilities;
    }

    @Override
    public ProviderSubmissionResult submit(
            PreparedMailSubmission request) {

        if (request.deadline() != null
                && !clock.instant().isBefore(request.deadline())) {
            return new ProviderSubmissionResult(
                    id,
                    SubmissionOutcome.DEFINITE_REJECTED,
                    RejectionKind.POLICY,
                    "DELIVERY_DEADLINE_EXPIRED",
                    null,
                    clock.instant());
        }

        try {
            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");

            helper.setFrom(request.fromAddress());
            helper.setTo(request.recipient());
            if (request.replyToAddress() != null) {
                helper.setReplyTo(request.replyToAddress());
            }
            helper.setSubject(request.subject());

            if (request.htmlText() != null) {
                helper.setText(
                        request.plainText() == null
                                ? ""
                                : request.plainText(),
                        request.htmlText());
            } else {
                helper.setText(
                        request.plainText() == null
                                ? ""
                                : request.plainText());
            }

            // Minimal version supports text/html without attachments only.
            // Attachment adapters need multipart=true and must attach
            // resources resolved via storageKey/versionId.
            if (!request.attachments().isEmpty()) {
                return new ProviderSubmissionResult(
                        id,
                        SubmissionOutcome.DEFINITE_REJECTED,
                        RejectionKind.POLICY,
                        "ATTACHMENT_HANDLER_NOT_CONFIGURED",
                        null,
                        clock.instant());
            }

            sender.send(message);
            return new ProviderSubmissionResult(
                    id,
                    SubmissionOutcome.ACCEPTED,
                    null,
                    "SMTP_ACCEPTED",
                    null,
                    clock.instant());
        } catch (MessagingException ex) {
            // MIME build failed before calling send.
            return new ProviderSubmissionResult(
                    id,
                    SubmissionOutcome.DEFINITE_REJECTED,
                    RejectionKind.PERMANENT,
                    "MIME_PREPARATION_FAILED",
                    null,
                    clock.instant());
        } catch (MailException ex) {
            // A generic MailException alone is insufficient to
            // prove whether the relay accepted DATA.
            return new ProviderSubmissionResult(
                    id,
                    SubmissionOutcome.UNKNOWN,
                    RejectionKind.UNCLASSIFIED,
                    "SMTP_OUTCOME_UNCLASSIFIED",
                    null,
                    clock.instant());
        }
    }
}
~~~

**This illustrates the contract and safe classification**, not a complete production SMTP classifier. Here `catch(MessagingException)` wraps MIME construction *before* `send`; if an application puts post-submission operations in the same `try`, never treat every `MessagingException` as pre-send. `MailException` from `send` is conservatively treated as `UNKNOWN` until a reliable classifier inspects causes and protocol stages.

### 7.2. Building MIME with attachments requires multipart

A production adapter builds MIME after resolving attachment sources:

~~~java
MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");

helper.setFrom(identity.fromAddress());
helper.setTo(request.recipient());
helper.setSubject(request.subject());
helper.setText(request.plainText(), request.htmlText());

helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(immutableInvoicePath),
        "application/pdf");

sender.send(message);
~~~

`FileSystemResource` reads the file when MIME serialization needs it, avoiding eager `Files.readAllBytes`. The file must exist and stay unchanged until `send` finishes; for async jobs, never delete request-scoped temp files before workers send.

For remote sources, `InputStreamSource.getInputStream()` must open a **fresh stream on every call**, because Jakarta Mail may read it multiple times. An `InputStreamResource` wrapping a single-use stream is generally unsuitable for large re-readable attachments.

### 7.3. Separate SMTP configuration per adapter

Factory example for one SMTP endpoint:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost(smtpHost);
sender.setPort(587);
sender.setUsername(smtpUser);
sender.setPassword(smtpPassword);
sender.setDefaultEncoding("UTF-8");

Properties props = new Properties();
props.setProperty("mail.smtp.auth", "true");
props.setProperty("mail.smtp.starttls.enable", "true");
props.setProperty("mail.smtp.starttls.required", "true");
props.setProperty("mail.smtp.ssl.checkserveridentity", "true");
props.setProperty("mail.smtp.connectiontimeout", "5000");
props.setProperty("mail.smtp.timeout", "15000");
props.setProperty("mail.smtp.writetimeout", "20000");
sender.setJavaMailProperties(props);
~~~

Timeouts are in milliseconds; values are illustrative. For implicit TLS SMTP (commonly port 465), configure `mail.smtp.ssl.enable` and matching endpoint settings. Never disable certificate/hostname verification in production just to work around a config issue.

Credentials must come from a secret manager or runtime configuration, never printed to logs. For OAuth2 providers, implement the appropriate auth flow rather than assuming passwords.

### 7.4. Never mutate host/password per request

The following is dangerous under multi-threading:

~~~java
// Avoid: singleton sender shared by multiple workers.
sender.setHost(selectedProvider.host());
sender.setUsername(selectedProvider.username());
sender.setPassword(selectedProvider.password());
sender.send(message);
~~~

Workers A and B can interleave updates, sending messages through the wrong endpoint or credentials. Create a dedicated sender/adapter per provider identity, configure it once, and look it up via the registry.

### 7.5. Why doesn't the SMTP adapter return providerMessageId?

`JavaMailSender.send` has no standard API returning a **provider-assigned submission ID**. MIME `Message-ID` can be generated/saved for tracing, yet it is not a provider ID and does not guarantee deduplication. Some providers add headers, log IDs, or provide feedback APIs; adapters should populate `providerMessageId` only when backed by a concrete contract.

## 8. HTTP email API adapters: how they differ from SMTP

A provider may accept JSON over HTTPS, for example:

~~~text
POST /v1/messages
Authorization: Bearer <secret>
Idempotency-Key: <stable-business-key>   [only if supported]
Content-Type: application/json

{
  "from": "...",
  "to": ["..."],
  "subject": "...",
  "html": "..."
}
~~~

This is a **conceptual pattern**, not a specific vendor's endpoint or schema. Always consult each provider's official API documentation when building adapters.

### 8.1. Transport client abstraction

To test cleanly without coupling to vendor SDKs, define:

~~~java
package com.example.mail.provider.http;

import java.util.Map;

public interface ProviderHttpClient {

    ProviderHttpResponse postMail(
            String providerId,
            PreparedHttpMailRequest request);
}

public record PreparedHttpMailRequest(
        String from,
        String to,
        String subject,
        String html,
        String text,
        String idempotencyKey) {
}

public record ProviderHttpResponse(
        int statusCode,
        String safeProviderCode,
        String providerMessageId,
        Map<String, String> allowedMetadata) {
}
~~~

`ProviderHttpClient` is an **application-defined** API. When writing a real client, enforce:

- TLS and hostname validation.
- Per-provider-account credentials.
- Connection/read/write timeouts.
- Response size caps.
- HTTP client retry policies that **never auto-retry ambiguous POSTs**.
- `429`/`Retry-After` handling per provider contract.
- Checking what 2xx means: `202 Accepted` may merely mean queue accepted.
- Never logging request bodies or bearer tokens.

### 8.2. Never collapse every HTTP 5xx into "definitely not sent"

Suppose a client POST reaches the server, the server creates the submission, and then fails while replying:

~~~text
Client -> Provider: POST /messages
Provider: creates submission ID P1
Provider -> Client: timeout / connection reset
~~~

This is `UNKNOWN` without idempotency/reconciliation proving the result. An HTTP 502 from a proxy also does not prove whether upstream created the job. Like SMTP, adapters must distinguish:

| HTTP outcome | Safe interpretation |
| --- | --- |
| 200/201/202 per contract | Provider accepted submission/request; inbox delivery still unconfirmed |
| Definite 400 validation | May be `DEFINITE_REJECTED` if API guarantees non-acceptance |
| 401/403 | Permission/credential config error; do not retry blindly |
| 429 | Capacity/throttling; may retry per policy and provider semantics |
| 5xx | Potentially transient, yet submission outcome may be `UNKNOWN` |
| Network timeout/reset after POST | `UNKNOWN` unless idempotency/reconciliation proves otherwise |

Never treat `if (status >= 500) fallback(B)` as an absolute rule.

### 8.3. Minimal HTTP adapter skeleton

~~~java
package com.example.mail.provider.http;

import java.time.Clock;

public final class HttpApiMailProviderAdapter
        implements MailProviderAdapter {

    private final String providerId;
    private final ProviderHttpClient client;
    private final ProviderCapabilities capabilities;
    private final Clock clock;

    public HttpApiMailProviderAdapter(
            String providerId,
            ProviderHttpClient client,
            ProviderCapabilities capabilities,
            Clock clock) {
        this.providerId = providerId;
        this.client = client;
        this.capabilities = capabilities;
        this.clock = clock;
    }

    @Override
    public String providerId() {
        return providerId;
    }

    @Override
    public ProviderCapabilities capabilities() {
        return capabilities;
    }

    @Override
    public ProviderSubmissionResult submit(
            PreparedMailSubmission mail) {

        PreparedHttpMailRequest payload =
                new PreparedHttpMailRequest(
                        mail.fromAddress(),
                        mail.recipient(),
                        mail.subject(),
                        mail.htmlText(),
                        mail.plainText(),
                        capabilities.supportsIdempotentSubmit()
                                ? mail.idempotencyKey()
                                : null);

        try {
            ProviderHttpResponse response =
                    client.postMail(providerId, payload);

            if (response.statusCode() == 202) {
                return new ProviderSubmissionResult(
                        providerId,
                        SubmissionOutcome.ACCEPTED,
                        null,
                        "HTTP_ACCEPTED",
                        response.providerMessageId(),
                        clock.instant());
            }

            // Remaining statuses must be mapped explicitly
            // per the specific provider's API contract.
            return new ProviderSubmissionResult(
                    providerId,
                    SubmissionOutcome.UNKNOWN,
                    RejectionKind.UNCLASSIFIED,
                    "HTTP_UNMAPPED_RESPONSE",
                    response.providerMessageId(),
                    clock.instant());
        } catch (RuntimeException ex) {
            // Cannot assert the provider did not receive the POST.
            return new ProviderSubmissionResult(
                    providerId,
                    SubmissionOutcome.UNKNOWN,
                    RejectionKind.UNCLASSIFIED,
                    "HTTP_OUTCOME_UNCLASSIFIED",
                    null,
                    clock.instant());
        }
    }
}
~~~

This snippet uses `202` as an **example of a hypothetical contract**. Real implementations need request validation, timeout classification, vendor-specific 2xx/error bodies, attachment handling, idempotency semantics, and security policies. Never copy a generic `HTTP_UNMAPPED_RESPONSE` directly into final retry decisions without a dedicated adapter mapping.

### 8.4. HTTP APIs and SMTP can coexist in the registry

Sharing an interface does not mean every adapter behaves identically. `capabilities.supportsIdempotentSubmit()` is a key signal for the orchestrator: retrying the same provider via an idempotent API on `UNKNOWN` can be safer than retrying SMTP, **provided** the key is still valid and the provider contract guarantees that behavior.

## 9. Provider registry: managing adapters by stable ID

With multiple providers, avoid injecting concrete adapters into every business service:

~~~java
// Hard to scale:
public OrderService(SmtpProviderA a, HttpProviderB b) {
    ...
}
~~~

Instead, a registry maps `providerId` to its adapter:

~~~java
package com.example.mail.provider;

import java.util.Collection;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public final class MailProviderRegistry {

    private final Map<String, MailProviderAdapter> byId;

    public MailProviderRegistry(
            Collection<MailProviderAdapter> adapters) {

        this.byId = Map.copyOf(
                adapters.stream().collect(Collectors.toMap(
                        MailProviderAdapter::providerId,
                        Function.identity())));

        if (byId.isEmpty()) {
            throw new IllegalStateException(
                    "No configured mail providers");
        }
    }

    public MailProviderAdapter require(String providerId) {
        MailProviderAdapter adapter = byId.get(providerId);
        if (adapter == null) {
            throw new IllegalArgumentException(
                    "Unknown providerId");
        }
        return adapter;
    }
}
~~~

`Collectors.toMap` rejects duplicate provider IDs when no merge function is supplied, catching duplicate config at startup. `Map.copyOf` prevents workers from accidentally mutating a shared map.

### 9.1. Registry bean with Spring

~~~java
@Configuration
public class ProviderRegistryConfiguration {

    @Bean
    MailProviderRegistry mailProviderRegistry(
            List<MailProviderAdapter> adapters) {
        return new MailProviderRegistry(adapters);
    }
}
~~~

Adapters can be individual `@Bean` definitions. With dozens of endpoints, build adapters from `@ConfigurationProperties` or a validated versioned config service. For credential rotation, consider **swapping adapter/sender instances by config version** while draining in-flight attempts, rather than mutating fields on a live sender concurrently.

### 9.2. Separate provider ID from identity ID

~~~text
providerId = smtp-eu-a
identityId = eu-transactional
From       = receipts@example.com
DKIM d=    = example.com
~~~

One provider can serve multiple sending identities; one identity can be verified on multiple providers. If an SMTP endpoint uses an envelope sender or account configured per identity, you may need distinct adapter instances or transport configs per provider–identity pair.

Never let public APIs accept an arbitrary `providerId` to access any provider's credentials. Provider selection must go through internal policies verifying tenant, region, and category.

## 10. Routing policy: building the allowed provider set

A production policy should not be an if/else chain checking only provider health. First build the **candidate allowlist** from approved constraints.

### 10.1. Matrix example

| Region | Mail category | Primary | Approved secondary | Notes |
| --- | --- | --- | --- | --- |
| VN | SECURITY | `smtp-vn-security-a` | `smtp-vn-security-b` | Deadline priority, dedicated quota |
| VN | TRANSACTIONAL | `smtp-vn-tx-a` | `api-vn-tx-b` | Same verified sender identity |
| VN | MARKETING | `api-vn-bulk-a` | None by default | Consent, campaign window |
| EU | SECURITY | `smtp-eu-security-a` | `api-eu-security-b` | Residency policy before health |
| EU | TRANSACTIONAL | `api-eu-tx-a` | `smtp-eu-tx-b` | Size, DKIM, feedback support |
| EU | MARKETING | `api-eu-bulk-a` | `api-eu-bulk-b` | Quota/bounce suppression |

These names are **illustrative logical IDs**, not endorsements of any vendor's real processing location. Add providers to the table only after evaluating contracts, sender identities, region/data policies, API/SMTP limits, and operability.

### 10.2. Policy model

~~~java
package com.example.mail.routing;

import java.util.List;

public enum MailCategory {
    SECURITY,
    TRANSACTIONAL,
    MARKETING
}

public enum DeliveryRegion {
    VN,
    EU,
    OTHER
}

public record RoutingContext(
        String tenantId,
        MailCategory category,
        DeliveryRegion region,
        String sendingIdentityId,
        long estimatedMessageBytes) {
}

public record ApprovedRoute(
        String policyVersion,
        String primaryProviderId,
        List<String> approvedFallbackIds,
        String reason) {
}
~~~

Java requires each `public` top-level type in its own file. This is an application model; routes can add priority, cost tiers, feedback requirements, tenant/account restrictions, and channels.

### 10.3. Determine region from trusted data

Do not use:

~~~text
recipient.endsWith(".eu") -> route EU
recipient.endsWith(".com") -> route US
~~~

Email domains do not prove recipient location. Trustworthy data comes from tenant residency policies, verified addresses, deployment regions, or customer contracts.

If region is unknown or sources conflict, hold the delivery for verification or use an **approved** default; never pick the cheapest or healthiest provider outside data boundaries.

### 10.4. Candidate eligibility filter

A provider is eligible only if:

~~~text
providerId is in approved route policy
AND tenant is permitted to use provider/account
AND region is allowed for the full data path
AND category is supported
AND sending identity is verified
AND required TLS/auth/capabilities are available
AND estimated message size <= allowed provider limit
AND recipient count is within limit
AND provider has capacity and acceptable health
~~~

For SMTP sizes, a 10 MiB input can produce a substantially larger MIME message due to Base64, headers, and multipart boundaries. Estimate **post-encoding** size with safety headroom instead of comparing raw binary size against total message limits.

### 10.5. Policy evaluation order

Illustrative sequence:

~~~text
1. Validate business command and recipient
2. Check consent, suppression, deadline
3. Resolve trusted region, category, tenant
4. Validate identity and contractual eligibility
5. Build approved provider candidate set
6. Apply capability/size constraints
7. Consider circuit, quota, capacity and priority
8. Select provider and persist decision
9. Call selected adapter
~~~

Never select a provider by latency first only to discover later that it cannot process that region or lacks From-domain verification.

## 11. Safe fallback strategy

Never define fallback as `catch(anyException) => try secondary`. A policy must simultaneously answer:

1. **Is the secondary provider permitted for this delivery?**
2. **Is the previous attempt definitely unaccepted?**
3. **Is this failure a type that switching providers actually helps?**
4. **Is the delivery still within deadline, unsuppressed, and within quota?**
5. **How many attempts remain, and what is the duplicate risk?**
6. **Does the secondary adapter support the required sender identity and attachments?**

### 11.1. Decision matrix

| Primary outcome | Error type | Immediate fallback? | Recommended behavior |
| --- | --- | --- | --- |
| Connect failed, definitely not submitted | Transient network | Possible | Pick eligible secondary, record new attempt |
| Circuit breaker open *before* calling primary | No submission | Possible | Pick secondary from allowlist |
| Provider out of quota before submission | Capacity | Possible | Eligible secondary with quota or reschedule |
| Recipient permanently rejected | Permanent | No by default | `FAILED`/suppress per policy |
| Unverified sender identity | Policy/config | No automatically | Fix config; use B only if B is valid and permitted |
| Message exceeds provider size limit | Permanent/capability | Never blindly | Pick B only if B supports same content and route is valid |
| SMTP accepted | Accepted | No | Record accepted, await feedback |
| Timeout after SMTP DATA | Unknown | Never blindly | Reconcile; evaluate duplicate tolerance |
| HTTP POST timeout | Unknown | Never blindly | If idempotency contract exists: retry same provider/key or query status |
| DB failed to save accepted state | Unknown local state | No | Reconcile before resending |
| Mass SMTP auth failures | Configuration | No by default | Alert, rotate secrets/credentials |

### 11.2. Stop cleanly when no eligible secondary exists

~~~text
Primary A unavailable
        |
        v
Approved secondary B?
       / \
     Yes  No
      |    |
      v    v
Eligible? HOLD / RETRY / alert
     / \
   Yes No
    |   |
    v   v
 Check prior  NO_ELIGIBLE_PROVIDER
 outcome      (not cross-region fallback)
    |
    v
 Safe to resubmit?
    |          |
   Yes         No
    |          |
    v          v
 Attempt B   UNKNOWN / reconciliation
~~~

**Failing closed is not a security bug:** if a delivery requires EU processing and all EU providers are down, holding the delivery is safer than routing through an unapproved external region.

### 11.3. Fallback only with pre-submission evidence

Not every timeout is `UNKNOWN`: a connection refused or open circuit **before sending payload** provides evidence of non-submission. Yet the adapter must supply trustworthy evidence or stage classification; catching a bare `MailSendException` without stage info should default to caution.

An adapter API can expose `FailureStage`:

~~~java
public enum SubmissionStage {
    PREPARE,
    CONNECT,
    AUTHENTICATE,
    ENVELOPE,
    DATA,
    PROVIDER_RESPONSE,
    PERSIST_RESULT,
    UNDETERMINED
}
~~~

Stages are only useful when genuinely observed from transport/SDKs. Never label every `IOException` as `CONNECT` just to unlock fallback.

### 11.4. Never switch providers to bypass suppression

If A rejects due to complaints or suppression, sending via B is not "outage recovery." Maintain an **application-level suppression policy** spanning all providers usable by the same recipient/tenant.

For marketing, check consent/unsubscribes before picking a provider. For transactional/security mail, also enforce policies for invalid addresses, blocklists, or regulatory restrictions. A suppression event from A may need to block B as well.

### 11.5. Pin routes or re-evaluate per attempt?

Two models:

**Pin provider/route on delivery:**

~~~text
delivery D1 -> route V1 -> provider A
retry #2   -> same provider A
~~~

Pros: simple audit trail; prevents unintended provider switches. Cons: needs an explicit fallback mechanism during prolonged outages on A.

**Re-evaluate on each attempt:**

~~~text
delivery D1 -> attempt #1 -> route V1, provider A
retry #2    -> route V2 -> provider B
~~~

Pros: adapts when configs or quotas change. Cons: must record **policy version and reason per attempt**, ensuring the new route still respects consent, region, and identity. Never randomly switch providers without explanation.

### 11.6. Failover vs failback

**Failover** shifts traffic from A to B when A is unusable. **Failback** shifts new traffic back to A after recovery. Prevent flapping when health fluctuates:

- Use cooldowns and stable health windows.
- Route only a canary fraction back to primary first.
- Verify quotas have recovered.
- Keep Provider B webhook/feedback ingestion active for emails sent before failback.
- Never switch providers for already-`ACCEPTED` deliveries just because primary recovered.

## 12. Attempt planner and policy engine

A dedicated component should decide provider selection for **a new attempt**. It performs no network I/O and can be tested with table-driven inputs.

Example data types:

~~~java
public record PreviousAttempt(
        String providerId,
        SubmissionOutcome outcome,
        RejectionKind rejectionKind,
        SubmissionStage lastObservedStage) {
}

public record AttemptDecision(
        String providerId,
        String policyVersion,
        String reason) {
}
~~~

### 12.1. Testable logic skeleton

~~~java
public final class FallbackPlanner {

    public AttemptDecision selectNext(
            ApprovedRoute route,
            PreviousAttempt previous,
            Set<String> currentlyEligible,
            int attemptsRemaining) {

        if (attemptsRemaining <= 0) {
            throw new IllegalStateException("Attempts exhausted");
        }

        if (previous == null) {
            String primary = route.primaryProviderId();
            if (currentlyEligible.contains(primary)) {
                return new AttemptDecision(
                        primary, route.policyVersion(), "PRIMARY");
            }

            // Primary was not attempted; eligible secondary allowed.
            return firstEligibleFallback(route, currentlyEligible);
        }

        if (previous.outcome() == SubmissionOutcome.ACCEPTED
                || previous.outcome() == SubmissionOutcome.UNKNOWN) {
            throw new IllegalStateException(
                    "Cannot blindly resubmit ambiguous or accepted mail");
        }

        if (previous.rejectionKind() == RejectionKind.PERMANENT
                || previous.rejectionKind() == RejectionKind.POLICY) {
            throw new IllegalStateException(
                    "Permanent or policy rejection blocks fallback");
        }

        return firstEligibleFallback(route, currentlyEligible);
    }

    private AttemptDecision firstEligibleFallback(
            ApprovedRoute route,
            Set<String> eligible) {

        return route.approvedFallbackIds().stream()
                .filter(eligible::contains)
                .findFirst()
                .map(id -> new AttemptDecision(
                        id, route.policyVersion(), "APPROVED_FALLBACK"))
                .orElseThrow(() -> new IllegalStateException(
                        "No eligible fallback provider"));
    }
}
~~~

This is a **condensed policy skeleton**; it omits retry deadline checks, whether switching providers actually helps a given transient failure, quotas, circuits, tenants, identities, idempotency guarantees, and SMTP stages. `currentlyEligible` must be a set **policy-checked by the router**, never a list supplied by callers or HTTP requests.

In larger systems, return a decision object (`HOLD`, `RETRY_SAME`, `FALLBACK`, `FAILED`, `RECONCILE`) rather than throwing `IllegalStateException` for every case; exceptions above simply highlight **never choosing B after `ACCEPTED`/`UNKNOWN`**.

### 12.2. Prevent unbounded retries inside SDKs

If an HTTP SDK auto-retries POST three times, Spring Retry advice retries twice, and the outbox worker retries five times, one delivery can fire far more submissions than intended. Define:

~~~text
durable_attempt_count = number of provider submission attempts
network_retries_per_attempt = tightly controlled
max_attempts = global business policy
~~~

If an SDK hides HTTP retries, consult its docs to disable or tune them; otherwise DB attempt audits will mismatch actual requests received by providers.

## 13. Transactional outbox and per-provider attempt history

Fallback is a correctness-critical decision. If the first provider is called yet routing is only recorded after `send(...)` returns, a crash erases which provider received the email.

For important mail, combine a **durable outbox** with **attempt history**:

~~~text
Business service
      |
      v
BEGIN DB transaction
   - save business change
   - insert outbox delivery PENDING
COMMIT
      |
      v
Worker claims due delivery
      |
      v
Resolve policy + select eligible provider
      |
      v
BEGIN DB transaction
   - record provider attempt STARTED
   - set delivery PROCESSING + claim token
COMMIT
      |
      v
Provider adapter.submit(...)
      |
      v
BEGIN DB transaction
   - record normalized outcome
   - mark ACCEPTED / RETRY / FAILED / UNKNOWN
COMMIT
~~~

Network calls occur **outside row-locking transactions**; workers use leases/claim tokens to protect state across long calls.

### 13.1. Delivery schema

~~~sql
CREATE TABLE mail_delivery (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    business_key VARCHAR(180) NOT NULL,
    recipient_address VARCHAR(320) NOT NULL,
    category VARCHAR(30) NOT NULL,
    data_region VARCHAR(30) NOT NULL,
    identity_id VARCHAR(100) NOT NULL,
    template_key VARCHAR(150) NOT NULL,
    template_version VARCHAR(80),
    body_reference VARCHAR(500),
    attachment_manifest_reference VARCHAR(500),
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deadline_at TIMESTAMPTZ,
    selected_provider_id VARCHAR(120),
    route_policy_version VARCHAR(100),
    claim_token UUID,
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    smtp_accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, business_key)
);

CREATE INDEX ix_mail_delivery_due
    ON mail_delivery(status, next_attempt_at);

CREATE INDEX ix_mail_delivery_lease
    ON mail_delivery(status, lease_until);
~~~

`business_key` represents a **business-generated delivery intent**, scoped by recipient and operation. If one order needs two legitimate distinct notifications, the key must distinguish them; if a worker retries the same notification, the key must stay stable.

Body/attachment references must point to data durably retrievable across worker restarts; encrypt, restrict access, and enforce retention if containing PII. Never store vendor credentials or secrets in the outbox.

### 13.2. Attempt history schema

~~~sql
CREATE TABLE mail_delivery_attempt (
    id UUID PRIMARY KEY,
    delivery_id UUID NOT NULL REFERENCES mail_delivery(id),
    attempt_no INT NOT NULL,
    provider_id VARCHAR(120) NOT NULL,
    sending_identity_id VARCHAR(120) NOT NULL,
    policy_version VARCHAR(100) NOT NULL,
    selection_reason VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(250),
    outcome VARCHAR(30) NOT NULL DEFAULT 'STARTED',
    rejection_kind VARCHAR(40),
    failure_stage VARCHAR(60),
    safe_error_code VARCHAR(100),
    provider_message_id VARCHAR(250),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE(delivery_id, attempt_no)
);

CREATE INDEX ix_mail_attempt_provider
    ON mail_delivery_attempt(provider_id, started_at DESC);
~~~

For every attempt, track:

- Which provider was chosen and under which route version.
- Whether fallback eligibility applied and why.
- Whether the network was called or rejected in preflight.
- Submission state: `STARTED`, `ACCEPTED`, `DEFINITE_REJECTED`, `UNKNOWN`.
- Provider message ID if provided by contract.
- Failure stage and safe error code.

If you need to distinguish "attempt selected before calling provider" from "call started", add `transport_started_at` or `PREPARED`/`IN_FLIGHT` states. This aids crash reconciliation:

~~~text
Record STARTED committed
    |
    +-- crash before HTTP/SMTP call
    |     -> no submission actually happened
    |
    +-- crash during HTTP/SMTP call
          -> submission may or may not have been accepted
~~~

You cannot look solely at a `STARTED` row after a crash and conclude with certainty whether the provider received it.

### 13.3. Atomic claim

PostgreSQL example:

~~~sql
WITH due AS (
    SELECT id
    FROM mail_delivery
    WHERE status IN ('PENDING', 'RETRY')
      AND next_attempt_at <= now()
      AND (deadline_at IS NULL OR deadline_at > now())
    ORDER BY next_attempt_at, created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_delivery AS m
SET status = 'PROCESSING',
    claim_token = :claim_token,
    lease_owner = :worker_id,
    lease_until = now() + INTERVAL '2 minutes',
    attempt_count = m.attempt_count + 1,
    updated_at = now()
FROM due
WHERE m.id = due.id
RETURNING m.id, m.attempt_count, m.tenant_id,
          m.data_region, m.category, m.identity_id;
~~~

Claim inside a short transaction, insert the attempt row with the incremented `attempt_no`, and commit before the network call. `SKIP LOCKED` keeps multiple workers from blocking on the same locked row; tune indexes and concurrency policies accordingly.

### 13.4. Fencing tokens when saving outcomes

After an adapter returns `ACCEPTED`:

~~~sql
UPDATE mail_delivery
SET status = 'ACCEPTED',
    smtp_accepted_at = now(),
    claim_token = NULL,
    lease_owner = NULL,
    lease_until = NULL,
    selected_provider_id = :provider_id,
    route_policy_version = :policy_version,
    updated_at = now()
WHERE id = :delivery_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;
~~~

If the update count is 0, the worker lost its lease or another worker reclaimed it. **Never force-overwrite the row** merely because the earlier network call succeeded. Record/investigate the state conflict, as the email may already have been accepted.

Update attempt history and delivery state in the same transaction whenever possible. For `UNKNOWN`, do not automatically flip back to `RETRY`; reconcile or apply duplicate-aware retry policies.

### 13.5. What does lease expiry mean?

~~~text
T0 worker A claims
T1 worker A starts SMTP send
T2 lease expires due to long timeout
T3 worker B claims same delivery
T4 worker A receives SMTP accepted
~~~

Fencing tokens stop A from overwriting B's DB state, yet **do not prevent two SMTP sends**. Combine:

- Worker concurrency and lease timeouts sized above max send duration.
- Heartbeats/lease extensions verified by claim token.
- Never blindly reclaiming messages with uncertain attempt outcomes.
- Business idempotency and provider reconciliation where supported.
- Monitoring expired leases to adjust timeouts/capacity.

### 13.6. Never hold transactions open across network I/O

Avoid:

~~~text
BEGIN transaction
  SELECT FOR UPDATE
  JavaMailSender.send (may take 30 seconds)
  UPDATE delivery
COMMIT
~~~

This holds connections/locks too long, increases deadlocks, and hurts scalability. Use short transactions to claim and persist outcomes, keeping SMTP/API calls outside.

## 14. Fallback is a controlled state transition

State diagram:

~~~text
PENDING
   |
   v
PROCESSING (attempt A)
   |
   +--> ACCEPTED --------------------> terminal submission success
   |
   +--> DEFINITE_REJECTED
   |        |
   |        +--> permanent/policy --> FAILED
   |        |
   |        +--> transient/capacity
   |                 |
   |                 v
   |              ROUTE_REEVALUATION
   |                 |
   |           +-----+------+
   |           |            |
   |           v            v
   |       eligible B      no eligible B
   |           |            |
   |           v            v
   |         RETRY        HOLD/RETRY/FAILED
   |           |
   |           v
   |      PROCESSING (attempt B)
   |
   +--> UNKNOWN ---------------------> RECONCILE/HOLD
~~~

Never spawn attempt B inside a `catch` block without persisting attempt A's durable record first. If the JVM crashes right after A throws and before B sends, the database must reflect that **attempt A happened** and whether B was scheduled.

### 14.1. Retry scheduling

Illustrative policy:

\[
d_n=\min(d_{\mathrm{max}},d_0 2^{n-1})
\]

With `d_0=30 seconds`, 15-minute cap, and jitter:

| Failed attempt | Base delay before next attempt |
| --- | --- |
| 1 | 30 s |
| 2 | 60 s |
| 3 | 120 s |
| 4 | 240 s |
| 5 | Stop if `max_attempts=5` |

This is not a Spring Mail default. Email type dictates deadlines: password resets may be useless once tokens expire; newsletters can wait until the next campaign window.

### 14.2. Retry the same provider or fall back to another?

| Scenario | Retry same | Fallback |
| --- | --- | --- |
| A temporarily rate-limited, B has capacity and is eligible | Possible after `Retry-After` | Possible if definitely unaccepted |
| DNS/connect to A unavailable | Possible after backoff | Can pick B immediately or after delay |
| B shares A's provider account/quota | Likely futile | Unlikely to help |
| A invalid recipient | No | No |
| A timeout after DATA | Duplicate risk | Even more caution needed |
| API A has valid idempotency token | Can retry same key | Switching to B loses A's idempotency token |
| A already `ACCEPTED` | No | No |

### 14.3. Retry-After does not prove no message was created

For HTTP providers, `429 Too Many Requests` is normally a capacity response; still respect endpoint contracts, proxies, and how providers handle requests. Read `Retry-After`, cap total attempts, and never assume retry-eligible automatically means fallback-safe.

## 15. Idempotency boundaries and duplicate risk

Idempotency is not a single toggle. Multiple layers exist:

1. **Business idempotency:** one order event/recipient creates one delivery intent.
2. **Outbox claim idempotency:** multiple workers never update the same row together.
3. **Provider submission idempotency:** repeating an API request creates no extra submissions, *if the provider supports it*.
4. **Recipient delivery uniqueness:** recipient sees one email; plain SMTP **has no exactly-once guarantee**.
5. **Feedback event idempotency:** webhook redeliveries do not apply state/suppression updates twice.

### 15.1. Business-operation idempotency keys

Example:

~~~text
tenant=T1
order=O42
recipient=U99
notification=ORDER_CONFIRMED
version=1

businessKey = "T1:O42:U99:ORDER_CONFIRMED:v1"
~~~

This format is illustrative. Never place sensitive IDs or raw emails in public headers/logs; production may use UUIDs or managed opaque/hashed keys.

If the same order later needs a different notification, the key must differ. If retrying an existing delivery, the key must stay unchanged.

### 15.2. HTTP adapters with idempotency

When supported by the provider, an HTTP adapter can send:

~~~text
Idempotency-Key: stable-key-for-delivery-D1
~~~

On timeout, **retrying the same account/provider with the same key** may return the prior outcome instead of creating a duplicate message. However, this is only safe within the TTL and endpoint contract, and the key does not carry over when switching to Provider B.

### 15.3. SMTP and Message-ID

MIME header:

~~~text
Message-ID: <opaque-delivery-D1@mail.example.com>
~~~

helps locate emails in logs or threads, yet SMTP servers are not required to deduplicate by `Message-ID`. Adapters may also lack full control over headers rewritten by libraries or relays. Never claim "same `Message-ID` = duplicate impossible."

### 15.4. Unknown-state reconciliation

An `UNKNOWN` work item should carry:

~~~text
deliveryId
attemptId
providerId
providerMessageId (if available)
idempotencyKey (if provider supports)
lastKnownStage
requestStartedAt
errorCode
reconciliationDeadline
~~~

Process:

1. Check whether the adapter/provider offers status lookup or submission logs.
2. If confirmed accepted, update submission state and await feedback.
3. If confirmed unaccepted, schedule retry/fallback.
4. If still `UNKNOWN`, decide per business tolerance: wait for operator, retry same key per contract, or accept duplicate risk with auditing.

Never equate `UNKNOWN` with `FAILED` just to keep dashboards "clean", and never automatically resend all `UNKNOWN` items on every scheduler tick.

## 16. Per-provider circuit breakers, rate limiters, and bulkheads

Fallback only works well when the system **stops hammering** a failing provider. Three mechanisms work together:

- **Circuit breaker:** temporarily stops calling a provider with high error rates.
- **Rate limiter/quota manager:** bounds messages, recipients, requests, or bytes per contract.
- **Bulkhead:** isolates worker/connection capacity so one slow provider cannot starve others.

~~~text
Due mail delivery
        |
        v
Eligible candidates by policy
        |
        v
Per-provider circuit breaker
        |
        +--> OPEN -> do not call
        |
        v
Rate limiter / quota reservation
        |
        +--> No capacity -> schedule later or eligible alternative
        |
        v
Bulkhead / concurrency permit
        |
        +--> Exhausted -> backpressure
        |
        v
Adapter.submit(...)
        |
        v
Normalized outcome + metrics
~~~

### 16.1. Circuit breaker open is not proof an email failed

When Provider A's circuit opens, the system **decides not to attempt A** for now. A new delivery can route to B because A was never called, if B is eligible. Do not increment A's `provider_submission_attempts` as if an SMTP call occurred, and do not mark an email `FAILED` solely because a circuit is open.

If A's circuit opens between attempts, check the prior attempt's outcome before picking B. A previous `UNKNOWN` attempt on A still needs reconciliation; an open circuit **does not prove** A missed the earlier message.

### 16.2. Configure circuits by error type

Not every `4xx` or `5xx` indicates a provider outage:

| Error | Count toward provider circuit? |
| --- | --- |
| Connect timeout/network failure | Yes, possible |
| SMTP relay 421 service unavailable | Yes, possible |
| Surging HTTP 5xx | Yes, per contract |
| Invalid recipient (`550 user unknown`) | No; do not trip global circuit |
| Template missing variable | Not a provider failure |
| Attachment too large | Capability/policy error |
| Account-wide invalid credentials | Handle config/alert; may disable route |
| Caller missing consent | Unrelated to provider health |

Counting every invalid recipient toward the circuit breaker lets a bad mailing list convince the system the SMTP provider is down and unnecessarily shift traffic to B.

### 16.3. Per-provider rate limits

A provider might specify:

~~~text
max 100 messages/minute
max 5 concurrent connections
max 20 MiB per MIME message
max 50 recipients per message
~~~

These numbers are **illustrative only**. Running 20 concurrent workers calling `submit` will not increase throughput if provider quotas are lower.

Rate limiters must match the actual quota dimensions:

- Requests per second.
- Recipients per minute.
- Emails per account/day.
- Connection concurrency.
- Message size.
- Dedicated rates per region, domain, or IP pool.

If primary and secondary share **one provider account/quota**, switching to a secondary hostname may add zero capacity.

### 16.4. Reserved capacity for critical emails

Suppose the system has 100 send tokens/minute while a marketing campaign queues 10,000 jobs. If marketing consumes all tokens, OTPs and password resets stall. Separate them:

~~~text
Critical / security queue -> reserved capacity
Transactional queue       -> normal reserved / weighted
Marketing queue           -> bulk capacity, pausable
~~~

Splitting queues without splitting provider quotas may not suffice. Use separate provider accounts/IP pools or a priority-aware shared limiter depending on the provider.

### 16.5. Jitter prevents retry storms

During an SMTP outage, thousands of deliveries can enter `RETRY` together. If all retry after exactly 30 seconds, the recovering provider gets slammed immediately:

~~~text
Without jitter:
  10,000 jobs retry at 12:00:30

With jitter:
  jobs spread across permitted retry window
~~~

Use exponential backoff, bounded random jitter, and per-provider concurrency caps. Never let retries across SDKs, circuits, workers, and schedulers multiply unchecked.

## 17. Sender identity: more than swapping SMTP endpoints

A provider adapter typically works with one or more verified **sending identities**. Failing over to a provider unauthorized for the message's `From`/DKIM domain causes rejections or SPF/DKIM/DMARC failures.

### 17.1. Different address concepts

An email involves several identities:

| Field | Role |
| --- | --- |
| Header `From` | Identity shown to the recipient |
| `Reply-To` | Where replies are directed |
| Envelope `MAIL FROM` | Bounce/DSN return path and SPF identity |
| `Return-Path` | Usually recorded by receivers from envelope sender |
| DKIM `d=` | Signing domain authenticating content/headers |
| Sender provider account | Authorized credentials/API key |

`MimeMessageHelper.setFrom(...)` sets the `From` header, without guaranteeing the SMTP envelope sender or `Return-Path` matches what you expect. With Jakarta Mail SMTP transport, `mail.smtp.from` affects the envelope sender—but never mutate properties on a singleton transport per request while multiple workers share it.

### 17.2. Identity/provider matrix

| Provider | Identity | From domain | Verified? | Eligible fallback? |
| --- | --- | --- | --- | --- |
| `smtp-vn-a` | `vn-security` | `example.com` | Yes | Primary |
| `api-vn-b` | `vn-security` | `example.com` | Yes | Possible |
| `smtp-us-c` | `vn-security` | `example.com` | Yes | No if region policy forbids |
| `api-vn-bulk` | `vn-security` | `example.com` | No | No |

A verified sender domain is only **one prerequisite**. Region, category, tenant, quota, and content policies must still pass.

### 17.3. SPF, DKIM, and DMARC during failover

Before enabling Provider B as a backup:

1. Verify `From` header domains are supported on Provider B.
2. Configure DKIM keys/selectors per B's instructions.
3. Verify SPF if B uses an envelope identity in your organization's domain.
4. Check DMARC alignment against the Header `From`.
5. Configure bounce domain/`Return-Path` if required.
6. Send test emails to a test mailbox and inspect authentication results.
7. Verify complaint/bounce routing on B.

Never just run `JavaMailSender.testConnection()` or HTTP `/health` and assume sender identity is ready. Connecting successfully does not mean the provider authorizes your domain.

### 17.4. Tenant isolation

In multi-tenant applications:

- Tenant A must never use Tenant B's provider account or `From` domain.
- Adapter registries must never leak API keys or SMTP passwords via public requests.
- Routing contexts must be validated from controlled domain data.
- Fallbacks must never switch tenant identities silently.
- Feedback webhooks must map events to the right tenant/delivery/attempt.
- Audits and metrics enforce appropriate RBAC.

If one provider serves multiple tenants, isolate identities, suppressions/quotas, and data access by policy.

## 18. Feedback adapters: bounces, delivery events, and complaints

Provider submission acceptance is only one phase. Later the provider may emit events:

- `QUEUED` or `ACCEPTED`.
- `DELIVERED` / receiving server accepted.
- `DEFERRED` / temporary delivery delay.
- `HARD_BOUNCE` or final failure.
- `SPAM_COMPLAINT`.
- `UNSUBSCRIBE` in marketing flows.

The **feedback adapter** layer translates vendor-specific payloads into a normalized internal schema.

### 18.1. Normalized event model

~~~java
package com.example.mail.feedback;

import java.time.Instant;
import java.util.UUID;

public enum DeliveryFeedbackKind {
    PROVIDER_ACCEPTED,
    RECEIVER_ACCEPTED,
    DEFERRED,
    HARD_BOUNCE,
    SOFT_BOUNCE_FINAL,
    COMPLAINT,
    UNKNOWN
}

public record NormalizedProviderFeedback(
        String providerId,
        String providerEventId,
        String providerMessageId,
        UUID deliveryId,
        UUID attemptId,
        String recipient,
        DeliveryFeedbackKind kind,
        String safeCode,
        Instant eventTime) {
}
~~~

These are custom types. Not every provider supplies `providerMessageId`, and one provider can emit multiple events for the same submission.

### 18.2. Correlation needs multiple ID layers

| ID | Issued by | Purpose |
| --- | --- | --- |
| `deliveryId` | Application | One send intent to a recipient |
| `attemptId` | Application | One submission attempt via one provider |
| `providerId` | Registry | Provider namespace |
| `providerMessageId` | Provider (if supported) | Links feedback to an attempt |
| `providerEventId` | Provider | Deduplicates webhook events |
| RFC `Message-ID` | MIME | Auxiliary tracing/threading; not idempotency proof |

When falling back from A to B, preserve **two separate attempt records**. Never overwrite A's `providerMessageId` with B's ID. Events from A may arrive late after B was chosen; correlate by provider and attempt.

### 18.3. Webhook verification

A webhook handler should follow:

~~~text
HTTP request
    |
    v
Verify provider signature + timestamp
    |
    v
Enforce request/attachment size
    |
    v
Normalize with provider-specific adapter
    |
    v
Resolve delivery + attempt + recipient
    |
    v
Persist event idempotently
    |
    v
Update delivery feedback projection
~~~

Never trust external payloads self-declaring provider, account, or tenant without signature/credential verification and approved mappings.

### 18.4. Out-of-order events

Example:

~~~text
12:01 provider emits delivered
12:02 provider emits deferred for an earlier attempt
12:03 application receives delivered
12:04 application receives delayed deferred
~~~

Never let an older `DEFERRED` event overwrite `DELIVERED` when provider contracts and timestamps show it occurred earlier. Maintain event history and state projections with explicit transition rules.

### 18.5. Cross-provider suppression

If A reports `HARD_BOUNCE` for recipient R, a central policy can block future sends to R across both A and B where appropriate. Relying solely on A's local suppression list lets fallback B keep emailing bad addresses or violating complaint rules.

### 18.6. SMTP DSNs differ from provider API webhooks

With plain SMTP, the app may need a bounce-receiving mailbox via envelope sender/`Return-Path`. DSNs can use MIME `multipart/report` and `message/delivery-status`. No single Spring Mail API handles multi-provider bounce correlation out of the box; build inbound adapters, parsers, validation, and policy-driven delivery mappings.

## 19. Phased provider migration strategies (migration/canary)

Emergency outage fallback and **planned provider migration** are two distinct workflows:

~~~text
Current provider A
       |
       v
New provider B approved (identity + feedback + region)
       |
       v
Route policy V2: 5% of eligible new deliveries -> B
       |
       v
Observe health/delivery feedback
       |
       v
Increase 5% -> 25% -> 50% -> 100%
       |
       v
Keep A webhook/DSN ingestion for prior sends
~~~

### 19.1. Sticky routing

New deliveries should be assigned providers via a stable key:

~~~text
bucket = stableHash(deliveryId) % 100

0..4   -> provider B
5..99  -> provider A
~~~

If each retry picks randomly, one delivery can hit multiple providers unintentionally and become hard to reconcile. Sticky routing keeps selection stable, while **fallback** is an explicitly logged decision for a valid failure.

When canarying by tenant, confirm the tenant satisfies permissions/regions so tests never accidentally breach data boundaries.

### 19.2. Criteria to ramp traffic

Monitor:

- Submission acceptance rate per provider.
- p95/p99 latency and timeout rates.
- SMTP 4xx/5xx or HTTP response taxonomy.
- Throttle/quota hits and circuit breaker transitions.
- Complaints, hard bounces, and sender reputation.
- Feedback webhook completeness and event lag.
- Queue age/SLOs for security and transactional mail.
- Cost and support responsiveness.

Never increase traffic merely because Provider B returns `202` fast; deliverability can be poor despite quick API responses.

### 19.3. Safe rollback

When rolling back from B to A:

- Route **new deliveries** under the old/rollback policy version.
- Never resubmit emails B already accepted.
- Reconcile any `UNKNOWN` attempts on B.
- Keep B credentials/webhook endpoints active long enough to ingest delayed bounce/delivery feedback.
- Record policy version and selection reason per attempt.
- Verify A still has quota and verified identities before shifting bulk volume back.

A rollback plan that cuts off feedback ingestion blinds the system to whether B-sent emails later bounced or delivered.

## 20. Observing adapters and fallbacks in production

When multiple adapters run in production, dashboards must answer:

- How many submissions is each provider receiving?
- Why are fallbacks rising, and from which primary to which secondary?
- Are attempts failing definitely or landing in `UNKNOWN`?
- Which providers are hitting rate limits or open circuits?
- Which queues are lagging, and are emails missing business deadlines?
- Does Provider B show higher bounce/complaint rates than A during a canary?
- How many emails await reconciliation due to ambiguous submission outcomes?

### 20.1. Recommended metrics

| Logical metric | Type | Meaning |
| --- | --- | --- |
| `mail_provider_attempts_total` | Counter | Attempts that actually started sending |
| `mail_provider_outcomes_total` | Counter | Accepted/definite rejected/unknown per provider |
| `mail_provider_send_duration_seconds` | Timer/Histogram | Transport call latency |
| `mail_route_selections_total` | Counter | Provider selections by category/region/reason |
| `mail_fallback_decisions_total` | Counter | Approved/blocked fallbacks and reasons |
| `mail_provider_rate_limited_total` | Counter | Throttles/capacity refusals |
| `mail_provider_circuit_open` | Gauge | Circuit breaker state per provider |
| `mail_provider_inflight` | Gauge | In-flight submissions |
| `mail_outbox_due` | Gauge | Due deliveries not yet sent |
| `mail_outbox_oldest_due_age_seconds` | Gauge | Age of oldest due delivery |
| `mail_submission_unknown_current` | Gauge | Attempts currently awaiting reconciliation |
| `mail_feedback_events_total` | Counter | Bounce, complaint, and delivered events |
| `mail_feedback_lag_seconds` | Histogram | Lag from submission to feedback |
| `mail_state_commit_failures_total` | Counter | SMTP/API outcome received yet DB commit failed |

### 20.2. Micrometer instrumentation

~~~java
package com.example.mail.ops;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class MailProviderMetrics {

    private final MeterRegistry registry;

    public MailProviderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordOutcome(
            String providerId,
            SubmissionOutcome outcome,
            String normalizedCode) {

        Counter.builder("mail.provider.outcomes")
                .tag("provider", providerId)
                .tag("outcome", outcome.name())
                .tag("code", normalizedCode)
                .register(registry)
                .increment();
    }
}
~~~

`normalizedCode` must come from a **bounded catalog**, such as `SMTP_PRE_SUBMISSION_CONNECT_ERROR`, `SMTP_UNKNOWN`, or `HTTP_RATE_LIMIT`; never use raw exception messages or HTTP response bodies as metric labels.

### 20.3. Never put PII or arbitrary IDs in tags

Avoid:

~~~text
mail_provider_outcomes_total{
  recipient="alice@example.com",
  deliveryId="uuid-every-message",
  error="Raw exception stack..."
}
~~~

Such labels create a new time series per message, blowing up metric storage and leaking user data. Stick to bounded provider IDs, regions, categories, outcomes, and safe codes. Internal delivery IDs belong in protected structured logs/traces.

### 20.4. Structured logging for routes and attempts

~~~json
{
  "event": "mail.provider.attempt.completed",
  "deliveryId": "opaque-delivery-uuid",
  "attemptId": "opaque-attempt-uuid",
  "providerId": "smtp-vn-tx-a",
  "routePolicyVersion": "routing-v4",
  "routeReason": "PRIMARY",
  "category": "TRANSACTIONAL",
  "region": "VN",
  "outcome": "UNKNOWN",
  "safeCode": "SMTP_RESPONSE_TIMEOUT",
  "elapsedMillis": 12345
}
~~~

Never log credentials, raw email recipients, subjects, bodies, attachments, or secret tokens. If region/tenant is sensitive per policy, restrict log access and retention.

### 20.5. Prometheus and dashboards

With Spring Boot Actuator and the Micrometer Prometheus registry:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      show-details: when-authorized
~~~

The endpoint is typically exposed at `/actuator/prometheus` when security permits. Never expose management endpoints containing internal metrics to the public Internet.

Illustrative PromQL (matching actual exported names/labels):

~~~promql
# Attempt outcomes by provider over 5m
sum by (provider, outcome) (
  rate(mail_provider_outcomes_total[5m])
)

# Unknown submissions awaiting reconciliation
max(mail_submission_unknown_current)

# Oldest due backlog age
max(mail_outbox_oldest_due_age_seconds)
~~~

If every replica queries the same database and exports a global backlog gauge, **never `sum` them** or you multiply the count by replica count. Use one authoritative collector or proper aggregation, plus metric freshness checks to distinguish an empty queue from a broken query.

### 20.6. Impact-based alerts

| Alert | What to check |
| --- | --- |
| Security email past deadline | Quotas, queue age, primary/secondary providers |
| Abnormal fallback spike | Primary health, circuit breaker, credentials |
| Rising `UNKNOWN` outcomes | SMTP timeouts after DATA, HTTP POST timeouts, DB commit errors |
| Secondary also throttled | Pool-wide capacity shortage; pause bulk traffic |
| Verified sender rejected | DKIM/From/account config, secret rotation |
| Feedback webhooks missing | Signatures, provider endpoints, replay/queues |
| Post-migration bounce/complaint spike | Deliverability, domain reputation, consent |
| No eligible providers left | Policy version, region restrictions, tenant permissions |

Never alert on queue depth alone: factor in job age, throughput, and error rates. A queue of 500 marketing emails may be normal, whereas 10 password-reset emails past deadline is an outage.

## 21. Security and data protection in provider adapters

Provider adapters sit at a privileged boundary: they access SMTP credentials/API tokens and see full email content. Production designs must enforce:

### 21.1. Credential handling

- Each provider/account uses its own secret reference; never store secrets in the mail outbox.
- Inject credentials via a secret manager or runtime configuration.
- Never log `JavaMailSenderImpl` configurations if logs contain passwords.
- Rotate keys/passwords with testing and clean instance turnover.
- Never let HTTP request parameters select vendor credentials directly.
- Apply least privilege to API keys: grant send permissions needed, never broad admin rights unnecessarily.

### 21.2. TLS and endpoint verification

SMTP requires mandatory STARTTLS or implicit TLS per endpoint with hostname/certificate verification enabled. HTTPS APIs must verify certificates and bound redirects, request sizes, and timeouts. Never disable TLS verification in production just because staging had a bad certificate; fix the trust/certificate.

### 21.3. Sender spoofing and header injection

`From`, `Reply-To`, and recipients must resolve from application-authorized identities rather than trusting arbitrary user-supplied addresses. Validate header fields against CR/LF injection and permit only verified sender domains.

### 21.4. End-to-end data residency

A route named `eu-provider-a` does not prove data stays in the EU. Verify:

- Where the provider processes bodies and attachments.
- Where their logs and backups live.
- Which regions store/transmit webhooks and feedback.
- Involved data processors and subprocessors.
- Your own outbox DB, object storage, metrics, and logs.
- Data processing agreements and support access policies.

Falling back across regions can violate compliance even when external endpoints look healthy. When no compliant route exists, **`HOLD` and alert** rather than bypassing residency.

### 21.5. Attachments, size caps, and data exposure

If adapters fetch attachments from object storage, use only **immutable authorized references** scoped to the tenant/delivery. Never fetch arbitrary URLs supplied by requests (SSRF risk). Cap total bytes, MIME depth, attachment types, and timeouts. For temp files, use a dedicated directory with quotas/ACLs and clean up after synchronous sends finish.

Never put raw MIME or attachment bytes into exceptions, retry queues, DLQs, traces, or metric tags. When replay is needed, use encrypted durable payload references with retention and authorization.

### 21.6. Quota abuse

If a public API lets callers pick `SECURITY` category or arbitrary provider IDs, attackers can exhaust priority quotas or send from unauthorized identities/regions. Derive categories from trusted use cases and enforce quotas per tenant and business operation.

### 21.7. Operator redrive permissions

Viewing status does not automatically grant resend authority. A redrive action must check:

1. Operator authentication/authorization.
2. Tenant, message type, and region scope.
3. Suppression/consent and business deadlines.
4. Whether prior attempts were `UNKNOWN` or `ACCEPTED`.
5. Whether payload/attachments remain authorized and within retention.
6. Audit actor, reason, timestamp, and policy version.

Never let a "Retry all FAILED" button resend expired password-reset tokens or `UNKNOWN` SMTP emails.

## 22. Testing adapters independently of vendors

Because adapters share a common contract, most routing/fallback logic can be tested with **fake adapters** returning deterministic outcomes without opening real SMTP sockets in every unit test.

### 22.1. Controllable fake adapter

~~~java
public final class FakeMailProviderAdapter
        implements MailProviderAdapter {

    private final String id;
    private final ProviderCapabilities capabilities;
    private final ProviderSubmissionResult nextResult;
    private int submitCalls;

    public FakeMailProviderAdapter(
            String id,
            ProviderCapabilities capabilities,
            ProviderSubmissionResult nextResult) {
        this.id = id;
        this.capabilities = capabilities;
        this.nextResult = nextResult;
    }

    @Override
    public String providerId() {
        return id;
    }

    @Override
    public ProviderCapabilities capabilities() {
        return capabilities;
    }

    @Override
    public ProviderSubmissionResult submit(
            PreparedMailSubmission request) {
        submitCalls++;
        return nextResult;
    }

    public int submitCalls() {
        return submitCalls;
    }
}
~~~

This fake is for **single-threaded unit tests** only. For concurrency tests, use thread-safe counters and record outcomes per attempt rather than drawing production concurrency conclusions from an unsynchronized mutable fake.

### 22.2. Unit testing no fallback on UNKNOWN

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class FallbackPlannerTest {

    @Test
    void refusesToFallbackAfterUnknownSubmission() {

        ApprovedRoute route = new ApprovedRoute(
                "routing-v4",
                "smtp-a",
                List.of("smtp-b"),
                "TRANSACTIONAL_VN");

        PreviousAttempt previous = new PreviousAttempt(
                "smtp-a",
                SubmissionOutcome.UNKNOWN,
                RejectionKind.UNCLASSIFIED,
                SubmissionStage.DATA);

        FallbackPlanner planner = new FallbackPlanner();

        assertThatThrownBy(() -> planner.selectNext(
                route, previous,
                Set.of("smtp-a", "smtp-b"), 3))
                .isInstanceOf(IllegalStateException.class);
    }
}
~~~

This test highlights a core invariant: **an unknown outcome never turns into permission to resend via B**. For production APIs returning a decision object, assert `RECONCILE` instead of an exception.

### 22.3. Unit testing approved fallback

~~~java
@Test
void choosesApprovedSecondaryWhenPrimaryWasNotAttempted() {

    ApprovedRoute route = new ApprovedRoute(
            "routing-v4",
            "smtp-a",
            List.of("smtp-b"),
            "TRANSACTIONAL_VN");

    FallbackPlanner planner = new FallbackPlanner();
    AttemptDecision next = planner.selectNext(
            route,
            null,
            Set.of("smtp-b"),
            3);

    assertThat(next.providerId()).isEqualTo("smtp-b");
    assertThat(next.reason()).isEqualTo("APPROVED_FALLBACK");
}
~~~

Here primary was **never called**, so there is no risk of double submission from attempt A. Tests should also verify providers missing from allowlists, in wrong regions/identities, or out of quota **are never chosen**.

### 22.4. Testing one delivery with two workers

With PostgreSQL/Testcontainers:

1. Insert a `PENDING` delivery.
2. Have two workers claim simultaneously.
3. Assert only one worker acquires the row with a valid lease.
4. Assert `attempt_count=1` and exactly one `STARTED` attempt record.
5. Worker A records `ACCEPTED` using the current claim token.
6. Worker B/stale worker tries writing with a different token → update count 0.

Testing with H2/mock repositories cannot accurately prove PostgreSQL `FOR UPDATE SKIP LOCKED`, isolation, and row locking.

### 22.5. Testing network success followed by state commit failure

Scenario:

~~~text
Fake provider A returns ACCEPTED
          |
          v
DB markAccepted throws
          |
          v
Expected:
  - no immediate submit through B
  - record/alert state-commit ambiguity
  - preserve provider A attempt metadata
  - reconcile before any resend
~~~

This failure window differs from provider-returned `UNKNOWN`, yet carries similar duplicate risk. Suites testing only adapter `submit` exceptions will miss it.

### 22.6. Testing SMTP adapters with a fake SMTP server

Use GreenMail, Mailpit, or a programmable SMTP test server to verify:

- Connections and STARTTLS/AUTH per test setup.
- MIME HTML/plain bodies and attachments.
- `From`/`Reply-To` and header encoding.
- Successful SMTP acceptance.
- Recipient 5xx, temporary 4xx, and connection drops.
- Post-DATA timeouts leading to uncertain outcomes.

Mailpit/GreenMail work well for inspecting received MIME, yet may not inject faults at every protocol phase; when testing post-DATA timeouts or varied 4xx/5xx replies, use a fake SMTP server with programmable responses.

### 22.7. Testing HTTP adapters against a fake server

Cases to cover:

| Simulated response | Expectation |
| --- | --- |
| API accepted with provider ID | `ACCEPTED` outcome, external ID saved |
| Definite HTTP 400 non-submission | `DEFINITE_REJECTED`, safe code |
| HTTP 401/403 | Config/auth incident, no infinite retries |
| HTTP 429 with `Retry-After` | Bounded scheduling per contract |
| HTTP 5xx after server created submission | `UNKNOWN` outcome without contrary evidence |
| HTTP POST timeout | No blind fallback; check idempotency |
| Replay with same idempotency key | Matches mocked provider contract |
| Body containing tokens/PII | Logs/metrics never expose payload |

When testing vendor SDKs, verify whether they auto-retry POSTs. If so, assertions must count total actual HTTP requests emitted, not just adapter `submit` invocations.

### 22.8. Testing policies and security

Minimum test matrix:

- VN security never auto-routes to US when region policy forbids it.
- EU marketing never uses another tenant's verified identity.
- Healthy Provider A lacking category support remains ineligible.
- Fallback B lacking DKIM/`From` verification is blocked.
- Messages exceeding provider size limits are not submitted.
- Suppressed recipients are not emailed via another provider.
- Expired deadlines do not fall back.
- Already-`ACCEPTED` attempts are never resent.
- `UNKNOWN` attempts require reconciliation per policy.
- No eligible provider → `NO_ELIGIBLE_PROVIDER`/`HOLD`, never an arbitrary default.

### 22.9. Testing webhook feedback

- Provider A webhooks fail Provider B's verifier.
- Replayed provider event IDs persist only one event.
- Late-arriving events still correlate to attempt A even after switching routes to B.
- `DEFERRED` never overwrites `DELIVERED`.
- Verified hard bounces update central suppression within the right scope.
- Marketing complaints are never misclassified as HTTP submission failures.

Never use production SMTP or public recipient addresses to trigger errors in automated tests.

## 23. Runbook: primary provider outage

Suppose the application sends VN transactional notifications via SMTP A, with B as an approved backup HTTP provider.

~~~text
09:00  SMTP A connection failure increases
09:01  Circuit breaker begins rejecting new calls to A
09:02  New unsubmitted work routes to eligible B
09:03  Pre-submission definite failures from A may fallback to B
09:04  Existing A UNKNOWN attempts remain for reconciliation
09:05  B quota usage grows, bulk traffic may be paused
09:10  A starts recovering
09:20  Controlled failback canary begins
~~~

### 23.1. Step 1 — Verify the incident type

Check:

- Network/TLS/DNS/SMTP auth or provider 4xx/5xx?
- Is primary failing for one region/account or the whole provider?
- Were there recent deploys, secret rotations, or route policy changes?
- Are adapters returning `DEFINITE_REJECTED` or `UNKNOWN`?
- Which deliveries were already accepted before the circuit opened?

Never switch providers instantly upon seeing a few timeouts without knowing whether A already received SMTP DATA.

### 23.2. Step 2 — Verify B is eligible

Confirm:

1. B is allowlisted for the exact category, tenant, and region.
2. `From`/DKIM/`Return-Path` are verified on B.
3. B supports required MIME/attachment sizes and recipient counts.
4. B has quota and concurrency headroom.
5. B delivery feedback and webhook signatures are configured.
6. B's data policy and retention are approved.

If B fails these checks, **`HOLD` and alert** beats violating policy.

### 23.3. Step 3 — Separate new work from old attempts

| Group | Action |
| --- | --- |
| `PENDING` work, no provider called | Pick B if eligible |
| Attempt A definite failure pre-submission | May create attempt B per retry/fallback policy |
| Attempt A accepted | Never submit to B |
| Attempt A unknown | Reconcile; never blind-send to B |
| A connection/auth config broken | Fix config while routing to B if policy allows |
| Delivery past deadline or recipient suppressed | Stop per policy; do not send late |

### 23.4. Step 4 — Manage capacity

Watch B's in-flight counts, throttles, send durations, quotas, and error rates. If B lacks headroom for both marketing and security, pause bulk mail or rely on contracted reserved capacity. Never raise worker pools from 8 to 80 when B allows only 10 connections: 429/421 errors will surge.

### 23.5. Step 5 — Confirm recovery

Never declare "resolved" just because A's TCP port responds again. Do:

- Send a canary through A using the right identity.
- Watch acceptance, latency, 4xx/5xx, and DKIM/auth results.
- Verify queue age and backlogs shrink.
- Confirm B stops hitting throttles.
- Keep ingesting B webhooks for accepted emails.
- Reconcile and triage remaining `UNKNOWN` attempts.
- Record the incident timeline and related routing decisions.

## 24. Runbook: rising UNKNOWN rate

`UNKNOWN` is one of the hardest states because **client exceptions alone cannot tell whether the recipient may have received the email**.

### 24.1. Find the root cause

Common symptoms:

- SMTP timeouts/resets while sending DATA.
- Provider HTTP POST disconnects after server accepted the request.
- Adapter processes killed mid-network call.
- DB result commit failures after submission acceptance.
- Hidden SDK retries firing multiple requests while the app records one attempt.

### 24.2. Isolate by provider and stage

~~~text
UNKNOWN count rising
        |
        v
Group by provider / transport / observed stage
        |
        +--> HTTP API with idempotency
        |        |
        |        v
        |    Query status / retry same key within contract
        |
        +--> SMTP after DATA
        |        |
        |        v
        |    Provider logs/DSN if available
        |
        +--> DB commit failure
                 |
                 v
             Inspect attempt history + provider evidence
~~~

Never blindly switch to B on a `MailSendException`. If evidence shows A accepted, update state and await feedback; if the provider confirms no submission, retry/fallback; if unverifiable, act according to business duplicate tolerance and audit the decision.

### 24.3. Why email category shapes the decision

Password resets and OTPs have tight deadlines; late retries risk delivering expired tokens. Invoices might permit a guarded resend or portal download, yet duplicate invoices confuse customers. Marketing risks spam complaints on duplicates. Never apply one blanket `UNKNOWN` resend rule to everything.

### 24.4. Closing the incident

Before closing, verify:

- How many `UNKNOWN` items resolved to `ACCEPTED`.
- How many resolved to definite failures.
- How many remain unresolved and their follow-up policy.
- Whether duplicate recipients were confirmed.
- Whether timeouts/leases, SDK retries, or DB availability need tuning.

## 25. Runbook: provider switched, yet deliverability drops

An HTTP API provider can return `202 Accepted` rapidly while inbox placement lags the old provider. The cause often lies in **sender identity, DNS, content, reputation, or feedback handling** rather than the network adapter.

### 25.1. Investigation checklist

1. Do SPF/DKIM/DMARC pass and align with Header `From`?
2. Are bounce domain/`Return-Path` configured properly on Provider B?
3. Are B's feedback webhooks arriving and verifying cleanly?
4. Were suppressions/consents synced between A and B?
5. Were B's domain and IP pools warmed up per operational policy?
6. Are transactional and marketing sharing reputation or quotas?
7. Did attachment/MIME encoding change across adapters?
8. Is B seeing elevated spam/complaint or hard-bounce rates on specific recipient domains?

### 25.2. Never "fix" it by resending everything

If B already accepted the message while feedback lags, resending via A creates duplicates. Verify feedback ingestion, provider status, and event lag first.

When rolling back, route only **new deliveries** back to A per policy; already-accepted attempts on B keep their history and webhook paths open until feedback/retention windows expire.

## 26. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `catch(Exception)` then send via B right away | Duplicates when A accepted then timed out | Normalize definite/unknown; reconcile |
| Single `boolean send()` across transports | Loses rejection/unknown/feedback detail | Typed submission results |
| Router checks only provider health | Wrong region, tenant, or `From` | Eligibility before health |
| `.eu` email domain → EU region | Wrong source for residency | Trusted tenant/residency policy |
| Mutating host/password on singleton sender | Race conditions, wrong accounts | Per-provider/identity adapter instances |
| Assuming HTTP 5xx means no message created | Duplicate POST requests | Idempotency / status lookup / `UNKNOWN` |
| Assuming SMTP `Message-ID` guarantees once-only | Duplicate sends | Treat as correlation, not dedup guarantee |
| Fallback after SMTP already accepted | Sends two emails | Terminal submission success; await feedback |
| Retrying all 5xx/permanent recipient errors | Wasted retries, damaged reputation | Classify stage/error/recipient |
| Secondary lacking DKIM/`From` verification | Provider rejections or DMARC failures | Pre-approve identities |
| Picking out-of-region fallback because it's healthy | Data-residency violation | Fail-closed region/tenant constraints |
| Treating multiple endpoints sharing one quota as independent | Throttles keep rising | Model account-level quotas/pools |
| SDK + advice + outbox retrying simultaneously | Runaway attempt counts | Single retry policy owner, total caps |
| Recording route only after `send` | Crash erases which provider was called | Persist attempt before network call |
| Holding DB transactions across SMTP | Long locks, deadlocks, low throughput | Short claim/commit and outcome/commit |
| Claim tokens without idempotent side effects | Stale workers can still duplicate sends | Leases + reconciliation + provider guarantees |
| Auto-flipping `UNKNOWN` straight to `RETRY` | Duplicate risk | Hold/reconcile |
| Not storing provider IDs per attempt | Cannot correlate webhooks post-fallback | Immutable attempt history |
| Disabling B webhooks immediately on rollback | Loses delayed bounce/delivery feedback | Keep feedback ingress open per retention |
| Sending marketing through security pool | Slow OTPs, polluted reputation/quotas | Reserved capacity, separate identities |
| Logging raw API responses/attachments | Token/PII exposure | Sanitize, use safe error codes |
| Redriving entire DLQ | Sends expired tokens or accepted emails | Authorization, eligibility, audits |
| Summing global DB gauges across all replicas | Dashboards multiply backlog counts | Proper aggregation / single collector |
| Testing happy path with one provider | Misses failover/race bugs | Fake providers + SMTP/API fault tests |

### 26.1. Where should "unknown outcomes" be handled?

Never let each adapter silently retry/fallback until `ACCEPTED`. Adapters report evidence-backed outcomes; the **orchestrator/reconciliation service** decides next steps using mail type, region, attempt count, duplicate tolerance, and business history.

### 26.2. When Provider B lacks delivery feedback

A route may still work for low-tracking emails, yet must not be selected for workflows **requiring bounce/complaint compliance** without an alternative. Capabilities must expose that limitation; never assume `JavaMailSender` supplies delivery statuses on its own.

### 26.3. When one email has multiple recipients

SMTP may partially accept recipients. If one `PreparedMailSubmission` carries multiple recipients, outcomes must track per-recipient acceptance/rejection and fallbacks must not resend to already-accepted addresses. For critical notifications, **one delivery per recipient** is simpler and easier to audit.

## 27. Frequently asked questions

**"Does Spring Framework Mail include provider adapters and fallback out of the box?"**  
`JavaMailSender` provides an email-sending abstraction, yet Spring Mail does not build multi-provider routing or fallback systems on its own. Applications must implement policies, registries, attempt states, and feedback integration.

**"Can we configure two `JavaMailSender` beans?"**  
Yes. Use `@Qualifier` or a registry to look up senders by provider ID. Separate host/credential configurations and never mutate a shared sender per request.

**"Is a provider adapter the Strategy Pattern?"**  
You can combine the **Adapter Pattern** to hide SMTP/HTTP transport details with the **Strategy Pattern** to select algorithms/providers. Pattern names alone do not solve races, exactly-once limits, quotas, or data compliance.

**"How do fallback and retry differ?"**  
Retry is a new attempt; fallback switches to another provider per policy. Fallbacks usually still count toward total attempts rather than bypassing `max_attempts`.

**"Should we fall back whenever `MailSendException` occurs?"**  
Never rely solely on the exception class. Know which stage failed and whether the provider could have accepted. When uncertain, classify as `UNKNOWN` and reconcile.

**"Does SMTP accepted mean inbox delivered?"**  
No. Relay acceptance does not mean inbox placement. Bounces, filtering, and provider feedback happen downstream.

**"If a timeout happens after DATA, is it definitely unsent?"**  
No. The SMTP relay may have accepted the message before the final response was lost. Resending via B can create duplicates.

**"Does HTTP 202 mean the recipient received the email?"**  
Not necessarily. Usually it means the provider accepted/queued the request per contract—not that the recipient's server accepted it.

**"Do HTTP API idempotency keys guarantee once-only delivery forever?"**  
No. Keys have scopes, TTLs, and provider-specific semantics. Once expired or when switching providers, that guarantee may no longer apply.

**"Can Provider B back up Provider A just because both use the same `From`?"**  
Only if B is authorized for that identity and satisfies SPF/DKIM/DMARC, envelope sender, tenant, region, and quota requirements. Having the same `From` string does not grant permission.

**"Should we switch to B immediately when A's circuit opens?"**  
For **new unsubmitted deliveries**, yes if B is eligible. For deliveries with a prior `UNKNOWN` attempt on A, an open circuit does not erase duplicate risk.

**"Should we route by recipient TLD?"**  
No. `.com`/`.vn` do not prove physical location or residency obligations. Use verified region/tenant data.

**"Should we load balance 50/50 to keep backups warm?"**  
Viable if both A and B are eligible and have sufficient quotas, identities, feedback, and reputation. Weighted routing should be versioned with sticky bucketing rather than re-randomizing on retries.

**"Does using A and B that share one quota help?"**  
It can add endpoint/network redundancy, yet will not raise account-level quota ceilings. Know which resources are truly independent.

**"When should retries stop?"**  
When attempts or deadlines expire, errors are permanent, payloads/sources are invalid, or no provider is eligible. For `UNKNOWN`, apply dedicated reconciliation/duplicate-risk policies.

**"Does a transactional outbox guarantee exactly-once?"**  
Not with plain SMTP. An outbox commits send intents atomically with business state, yet cannot join an atomic transaction with SMTP/API providers.

**"Should we store the route version?"**  
Yes for auditing. When routing policies evolve, every attempt needs to show which provider and policy version produced the decision.

**"Should we store raw vendor responses?"**  
Only with clear need and data protections. Responses may contain recipients, bodies, tokens, or PII; prefer safe error codes, validated provider message IDs, and retention-bound traces.

**"Are `ProviderMessageId` and MIME `Message-ID` the same?"**  
Not necessarily. `ProviderMessageId` is issued by the provider, whereas MIME `Message-ID` is an email header; adapters should store them separately and never assume SMTP returns a provider ID.

**"How should delayed webhooks after fallback be handled?"**  
Map by provider ID and attempt ID, preserving immutable history; never overwrite attempt A with B's outcome. Enforce event ordering and idempotency.

**"Should we auto-resend when a webhook reports `deferred`?"**  
Not by default. The provider may still be retrying delivery internally; sending another submission risks duplicates.

**"Should a hard bounce from A block B?"**  
Usually yes via central suppression backed by verified feedback. Keeping blocklists isolated inside A lets B keep sending to invalid addresses.

**"Can we store `MailProviderAdapter` in the database?"**  
Never store Java objects or raw credentials directly as config rows. Store provider IDs, policy versions, capability metadata, and secret references; the registry instantiates runtime adapters from controlled config.

**"Should we pick adapters using a `providerId` from HTTP requests?"**  
Not unless authorized. The router decides from validated business context, tenant, category, and region; callers must not bypass policy with a string parameter.

**"What if Provider B doesn't support large attachments?"**  
Never fall back blindly. Capability filters must exclude B pre-submission; business policy can substitute a secure download link or hold/fail explicitly.

**"Should rate limiting be per provider or per category?"**  
Match the provider's real quota layers while reserving capacity per category if needed. A category-only limiter fails when all categories share one account quota.

**"Should every error go into a DLQ?"**  
No. Transient errors within deadlines/attempts retry; permanent errors go terminal; `UNKNOWN` needs reconciliation; quarantine needs dedicated permissions. DLQs are typically for items stopped from auto-retrying.

**"How do we test fallbacks without sending real emails?"**  
Use fake adapters returning typed outcomes; unit-test the planner, then integration-test SMTP/HTTP against fake servers. Never send to public recipients.

## 28. Production readiness checklist

### Provider contracts and adapters

1. Define `MailProviderAdapter` taking prepared requests with no unauthorized data.
2. Use `ProviderSubmissionResult` separating `ACCEPTED`, `DEFINITE_REJECTED`, and `UNKNOWN`.
3. Never use a `boolean sent` that hides uncertain results.
4. Keep `providerMessageId` separate from MIME `Message-ID`.
5. Give SMTP and HTTP API adapters tailored error classifiers rather than a `catch-all retry`.
6. Normalize provider IDs, safe error codes, and stages for logs/metrics.
7. Instantiate credentials/transports per provider/sending identity; never mutate shared senders per request.
8. Prevent HTTP clients/SDKs from auto-retrying POSTs uncontrollably.

### Routing policy

9. Derive category, tenant, region, identity, and deadlines from trusted sources.
10. Build the **allowed provider set** before checking health/latency/cost.
11. Define primaries and approved fallbacks explicitly.
12. Never route by email TLD or user-supplied provider IDs.
13. Check verified identities, DKIM/From domains, TLS, sizes, capabilities, and quotas.
14. When no eligible provider remains, HOLD/alert rather than routing outside policy.
15. Version, audit, and matrix-test routing policies.

### Fallback and retry

16. Fall back only when the prior provider **definitely did not accept** or business policy explicitly governs the risk.
17. Never fall back when already `ACCEPTED`.
18. Never blindly fall back on `UNKNOWN` after SMTP DATA or HTTP POST timeouts.
19. Never retry permanent invalid recipients, suppressions, or expired tokens.
20. Enforce max attempts, deadlines, backoff, jitter, and capacity controls.
21. Never stack unbounded retries across provider SDKs, Spring advice, and outboxes.
22. Distinguish initial routing, load balancing, fallback, and failback in selection reasons.
23. Keep attempt IDs, provider IDs, and route versions immutable in history.

### Durable state and idempotency

24. Persist one durable delivery intent per business operation and recipient.
25. Write `STARTED` attempt/provider records before network calls.
26. Never hold DB transactions/row locks during SMTP/API network I/O.
27. Claim atomically using leases and fencing tokens.
28. Handle the crash window where transport accepted yet DB commit failed.
29. Implement `UNKNOWN` and reconciliation workflows.
30. When provider APIs support idempotency, pass stable keys within contract/TTL bounds.
31. Never claim plain SMTP guarantees exactly-once delivery.

### Feedback and security

32. Ingest and verify webhooks/DSNs per provider.
33. Correlate feedback by provider + attempt/delivery + recipient.
34. Deduplicate provider events and handle late/out-of-order arrivals.
35. Maintain central suppression on bounces and complaints.
36. Protect PII in mail bodies, attachments, logs, and DLQs.
37. Tenant-authorize every storage key and attachment reference.
38. Enforce credential rotation, TLS/hostname validation, and RBAC/redrive audits.
39. Keep feedback ingestion running across provider rollbacks.

### Operations and testing

40. Instrument metrics for provider attempts/outcomes, fallbacks, quotas, circuits, `UNKNOWN`, and outbox age.
41. Alert on delayed security mail, `UNKNOWN` spikes, and `no eligible provider`.
42. Test SMTP/HTTP adapters in isolated mock environments without sending real mail.
43. Test the `category × region × tenant × identity` policy matrix.
44. Test post-DATA/HTTP POST timeouts and post-`ACCEPTED` DB commit failures.
45. Test concurrency, claim/lease mechanics, stale outcomes, and duplicate guards.
46. Test webhook redeliveries, bounces, and post-fallback correlation.
47. Maintain runbooks for primary outages, `UNKNOWN`, failed migrations, and redrives.
48. Use route versions and sticky assignments for canaries and rollbacks.

## 29. Summary architecture diagram

~~~text
                         Business events
                       order / account / billing
                                 |
                                 v
                        Notification service
                                 |
                                 v
                        Durable mail outbox
                                 |
                                 v
                      Worker atomic claim
                                 |
                                 v
                    Business and security policy
                   consent / tenant / data region
                                 |
                                 v
                        Provider router
                    eligible set + route version
                                 |
                                 v
                      Provider selection
                  priority / health / quota / cost
                                 |
                                 v
                    Persist STARTED attempt
                                 |
                +----------------+------------------+
                |                                   |
                v                                   v
        SMTP provider adapter                 HTTP API adapter
        JavaMailSender                        Vendor API client
                |                                   |
                v                                   v
            SMTP relay                          API endpoint
                |                                   |
                +----------------+------------------+
                                 |
                                 v
                    Normalized submission result
                                 |
                 +---------------+------------------+
                 |               |                  |
                 v               v                  v
              ACCEPTED     DEFINITE_REJECTED      UNKNOWN
                 |               |                  |
                 |               v                  v
                 |         Failure classifier   Reconciliation
                 |               |                  |
                 |        +------+-------+          |
                 |        |              |          |
                 |        v              v          |
                 |     RETRY          FAILED/HOLD    |
                 |        |              |          |
                 |        v              |          |
                 |   Fallback policy      |          |
                 |        |              |          |
                 |        v              |          |
                 |   Approved new attempt |          |
                 |        |              |          |
                 +--------+--------------+----------+
                                 |
                                 v
                    Attempt history + durable state
                                 |
             +-------------------+------------------+
             |                   |                  |
             v                   v                  v
         Monitoring          Audit/ops          Feedback adapter
       SLO, metrics,         redrive            webhook/DSN
        alerting                |                  |
                                |                  v
                                |          Bounce/complaint events
                                |                  |
                                +------------------+
                                           |
                                           v
                                    Central suppression
~~~

### Core principles

- **Adapters** encapsulate transport details, **routers** determine eligible providers, and **fallback policies** decide whether switching after failure is allowed.
- A **healthy** provider is not automatically **permitted** to handle a delivery.
- `ACCEPTED` only means the provider accepted the submission, not inbox delivery.
- `UNKNOWN` must be treated as carrying duplicate risk, not a simple retryable failure.
- Valid fallbacks must record a **new attempt with explicit provider, policy, and reason**.
- **Transactional outboxes do not create exactly-once SMTP**; you still need idempotency, leases, and reconciliation.
- **Circuit breakers and limiters** protect capacity without overriding region, tenant, or identity policies.
- **Feedback webhooks/DSNs** must survive provider switches so bounce and complaint tracking is never lost.
- **Protecting email data and credentials** is part of adapter design, not an afterthought.

## Conclusion

**Provider adapters and fallback strategies** form an essential production pattern for Spring Framework Mail applications needing multiple SMTP relays or hybrid HTTP email APIs. A solid architecture decouples mail contracts from vendor SDKs, manages adapters through a registry, applies versioned routing policies, and records every attempt in a durable outbox.

The difference between code that merely runs and a system reliable enough to operate lies in **decision quality during failures**: the system must know which errors happened pre-submission, when a provider already accepted, when outcomes are indeterminate, and when switching providers risks duplicates or policy violations. Combined with idempotency, rate limiting, circuit breakers, verified sender identities, feedback correlation, observability, and audited redrives, fallback becomes a controlled recovery mechanism rather than a blind resend command.
