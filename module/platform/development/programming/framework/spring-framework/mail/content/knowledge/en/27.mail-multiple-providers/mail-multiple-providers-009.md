# Contract Testing Each Provider

When a **Spring Framework Mail** application uses multiple mail providers, having every adapter implement a common interface like `MailSender` or `MailProvider` **does not mean they behave identically**. One provider may accept SMTP on port 587 via STARTTLS; another uses implicit TLS on port 465 or an HTTP API. One requires an app password, while another uses OAuth2, an API token, an IP allowlist, or permission to send on behalf of a verified address. Error reporting, rate limits, recipient handling, returned message IDs, and bounce notifications can also differ.

If you only write a unit test mocking `JavaMailSender.send(...)` to throw no exception, the app has not proven that its real adapter **complies with the sending contract**. During failover, provider changes, or deploying to another region, these differences can cause lost emails, duplicates, wrong state updates, dropped recipients, or misinterpreting `accepted` as `delivered`.

**Contract testing each provider** verifies the guarantees the application expects at the integration boundary: input data, provider capabilities, transport security, submission outcomes, errors and retries, message identifiers, delivery events, quotas, and access permissions. Shared tests protect common behavior; provider-specific tests verify differences; sandbox/staging tests verify reality beyond mocks.

This lesson covers designing the contract, building a capability matrix, structuring reusable JUnit 5 test suites, testing SMTP/API adapters, simulating errors and webhooks, testing routing/failover, managing credentials safely, and detecting contract drift after a provider changes policies.

## 1. What Is a Contract in Mail Integration?

Here, a **contract** is the set of agreed conditions and observable outcomes between two sides:

- **Application provides:** the provider receives a valid email for authorized recipients and senders.
- **Adapter guarantees:** accurate translation to SMTP/API without losing content or misaddressing recipients.
- **Provider responds:** accepted, rejected, or uncertain status per protocol.
- **Application interprets:** updates state, decides retries, and emits meaningful logs/metrics.
- **Provider notifies later:** may emit delivered, bounced, deferred, complaint, or other events; the contract covers only genuinely supported capabilities.

A contract test does not necessarily test the entire system. It tests **the boundary between two components** using well-defined examples and invariants.

### Distinguishing Four Contract Layers

| Layer | Example | Where to test? |
|---|---|---|
| **Domain contract** | One notification to the right recipient, template/locale | Service and renderer unit tests |
| **Provider-port contract** | `submit` returns accepted/rejected/unknown accurately | Shared suite across all adapters |
| **Protocol contract** | SMTP AUTH/TLS/MIME or HTTP method/header/body/error mapping | SMTP test server, HTTP mock server |
| **External/provider contract** | Sender rights, quotas, event schemas, real behavior | Controlled sandbox/staging/live canary |

A Mockito test verifies only Java method calls, not whether the provider accepts the data. A test against an SMTP test server verifies only part of the protocol, not real provider account policies.

### Most Important Goal

**Every provider must honor the application's common contract, yet never pretend every provider supports the same features.** When a feature is unsupported, the adapter must reject explicitly or pick an approved fallback behavior—never silently drop critical data.

## 2. Why Test Each Provider Individually?

A configuration that "works" today may not be equivalent on another provider.

Invoice-sending flow example:

```text
Business service
       |
       v
MailProviderPort.submit(invoice notification)
       |
       +--- SMTP Provider A
       |      - STARTTLS
       |      - username + app password
       |      - 4xx/5xx replies
       |
       +--- SMTP Provider B
       |      - implicit TLS
       |      - OAuth2/XOAUTH2
       |      - different limits
       |
       +--- HTTP API Provider C
              - bearer token
              - JSON payload
              - API request ID
              - async delivery webhook
```

Cases prone to divergence:

1. Provider A accepts a `From` address, while B requires a verified sender/domain.
2. A returns a temporary 4xx code, while B returns HTTP 429 with retry instructions.
3. One adapter returns a provider message ID, while another has no such ID over SMTP.
4. An API accepts recipients as a list, while SMTP can return partial acceptance.
5. A provider supports custom metadata via API yet does not guarantee preserving custom headers over SMTP.
6. A provider's `delivered` webhook means the destination server accepted it, not Inbox placement.
7. Provider A uses a real sandbox, while provider B's test mode only simulates acceptance.
8. Different timeout/connection-reuse settings alter attempt counts or latency.
9. A provider lacks support for inline MIME structures, large attachments, or internationalized addresses.
10. During failover, the same notification risks double submission if the first attempt's outcome is unclear.

If tests run only against the default provider, these issues surface right after deployment or during a production outage—precisely when fallback is expected to work.

## 3. Lock Down the Application Contract Before Writing Adapters

Separate **logical sending intent** from concrete protocol details.

An illustrative model:

```java
import java.time.Instant;
import java.util.List;

public record MailSubmissionCommand(
        String notificationId,
        String correlationId,
        String senderProfile,
        List<String> recipients,
        String subject,
        String plainText,
        String html,
        List<AttachmentRef> attachments,
        Instant expiresAt
) {
}

public record AttachmentRef(
        String id,
        String safeFilename,
        String mediaType,
        long contentLength
) {
}
```

`senderProfile` should be a managed internal configuration ID, not an arbitrary client-supplied `From` address. `AttachmentRef` is a reference to an authorized resource; loading actual bytes can live in a separate service.

Submission results should distinguish three situations:

```java
public enum SubmissionOutcome {
    ACCEPTED,
    REJECTED,
    UNKNOWN
}
```

```java
import java.time.Instant;

public record ProviderSubmissionResult(
        SubmissionOutcome outcome,
        String providerRoute,
        String providerMessageId,
        String errorCategory,
        boolean retryable,
        Instant observedAt
) {
}
```

In real code, constrain valid fields per outcome:

- `ACCEPTED`: provider/transport confirmed **submission**, not delivery.
- `REJECTED`: grounded evidence the provider did not accept the attempt.
- `UNKNOWN`: uncertain whether the message was accepted or not.

`providerMessageId` may be `null` if the SMTP path/adapter does not supply a meaningful ID. Never invent a provider ID from the notification ID and treat them as equivalent.

### Integration Boundary Interface

```java
public interface MailProviderPort {
    String routeId();

    ProviderCapabilities capabilities();

    ProviderSubmissionResult submit(
            MailSubmissionCommand command,
            String attemptId
    );
}
```

An SMTP adapter can use `JavaMailSender` or `JavaMailSenderImpl`; an HTTP API adapter uses an application-chosen HTTP client. Business services depend only on `MailProviderPort`.

Crucially, **contract tests run against every adapter**, not merely verifying the interface compiles.

## 4. Capability Matrix per Provider

Do not leave an unchecked set of booleans assuming every provider supports everything. Declare capabilities per route.

A hypothetical table (not describing any real commercial vendor):

| Capability | SMTP Route A | SMTP Route B | HTTP API Route C |
|---|---|---|---|
| Channel | SMTP | SMTP | HTTP API |
| Transport security | STARTTLS | Implicit TLS | HTTPS |
| Authentication | Username/app password | XOAUTH2 | API token |
| Plain text + HTML | Yes | Yes | Yes |
| Attachments | Yes, within limits | Yes, different limits | Yes, API limits |
| Inline CID | Needs MIME testing | Needs MIME testing | Per API contract |
| Sender identity | Permitted domain | Authorized mailbox | Verified sender |
| Multiple recipients | Possible | Possible | Per API contract |
| Immediate provider message ID | Not guaranteed | Not guaranteed | Usually API-dependent |
| Delivery webhooks | Service-dependent | Service-dependent | Plan/contract-dependent |
| Server-side idempotency | Not by default | Not by default | Only if documented by API |
| Quota/rate limit | Per SMTP account | Per mailbox/tenant | Per token/account |

This table is a **template for your team to populate with official vendor data**, not a claim about any provider's traits. When properties are unverified, mark `UNKNOWN` and keep dependent features off.

Capabilities can be modeled in code:

```java
public record ProviderCapabilities(
        boolean supportsHtml,
        boolean supportsAttachments,
        boolean supportsInlineImages,
        boolean supportsDeliveryEvents,
        boolean supportsProviderIdempotency,
        int maxRecipientsPerSubmission,
        long maxMimeBytes
) {
}
```

Add fields as needed, yet never mix local config values with provider guarantees. For example, max MIME size can depend on account, plan, or environment and change over time.

### When a Capability Is Missing

If a command includes an attachment yet the provider route lacks attachment support:

- Reject before calling the provider with an explicit error code.
- Or route to another provider **that has the capability** and is permitted by policy.
- Never silently strip the attachment and send an incomplete email.

If a message contains HTML and a provider supports only plain text, fall back to plain text only if the product approved that fallback. Contract tests should confirm there is no silent degradation.

## 5. Cataloging Behaviors That Need Testing

Every route needs a test suite covering at least:

| Area | Contract question |
|---|---|
| Configuration | Do host/base URL/port/credentials/sender profile match the environment? |
| Security | Is proper TLS enforced without falling back to plaintext connections? |
| Identity | Are From, Reply-To, envelope sender, and Send As rights valid? |
| Data fidelity | Are Subject, plain, HTML, recipients, Unicode, and attachments preserved intact? |
| Transport | Is the send operation invoked once per attempt? |
| Success | Are accepted responses mapped accurately without equating to delivery? |
| Failure | Are 4xx/5xx/429/auth/timeouts classified properly? |
| Unknown | Is a lost final response reflected as uncertain? |
| Limits | Are recipient counts, byte sizes, and quotas/rate limits enforced? |
| Idempotency | Do retries/failovers avoid wrongly spawning new notifications? |
| Events | Are webhook schemas, signatures, duplicates, and out-of-order events handled? |
| Observability | Can correlation/notification/attempt IDs be traced? |
| Privacy | Are secrets, tokens, raw MIME, and out-of-policy PII kept out of logs? |
| Operational | Are config rotation, provider outages, route disabling, and recovery tested? |

Not every adapter needs to test every feature by sending real emails. Splitting into **pure application tests**, **protocol simulation**, **sandbox tests**, and **controlled live canaries** is safer and more effective.

## 6. Splitting Tests by Layer and Goal

### Unit Contract Tests

Targets:

- Mapping commands → SMTP MIME/API payloads.
- Mapping responses → `ProviderSubmissionResult`.
- Capability and sender-profile validation.
- Error classification, retryability, and unknown outcomes.
- Never sending when validation fails.

Benefits: fast, no network needed, easy to inject rare errors.

### Protocol Tests

Targets:

- SMTP test server for STARTTLS/AUTH and supported MIME behaviors.
- HTTP mock server for method/path/headers/body/status codes.
- Timeouts, disconnects, malformed errors or responses.
- Webhook verification and idempotent handling.

Mock servers confirm **the adapter speaks the simulated protocol accurately**—they do not replace real provider policies.

### Sandbox/Staging Provider Verification

Targets:

- Credentials and sending permissions issued by the provider.
- Domain/sender verification.
- API versions and supported auth mechanisms.
- Quotas and how the provider actually emits errors.
- Event/webhook schemas in the test environment.
- ID mappings and capabilities needing real confirmation.

Use only authorized accounts/tenants/sandboxes. Sandboxes may not actually deliver to the public Internet, so know their simulation depth.

### Controlled Production Canary

When a capability cannot be confirmed in sandbox, use an operationally governed check: allowlisted test mailboxes, low rates, synthetic content, provider monitoring, and KPIs separated from business mail.

**Never automatically send real tests to arbitrary recipients in CI or health endpoints.**

## 7. Test Architecture: One Shared Suite, Multiple Adapters

The goal is catching two classes of bugs:

1. **Shared contract violations:** adapter emails the wrong recipient, returns `DELIVERED` on submission acceptance, swallows errors...
2. **Provider-specific violations:** wrong SMTP TLS mode, ignoring HTTP `Retry-After`, skipping webhook signature checks...

Model:

```text
                         Shared contract suite
                         /        |         \
                        v         v          v
                   SMTP A      SMTP B      HTTP C
                    tests       tests       tests
                      |           |           |
                      v           v           v
                 Protocol     Protocol    Mock HTTP
                  server       server       server
                      \           |           /
                       \          |          /
                        Provider-specific tests
                                  |
                                  v
                         Staging verification
```

Do not copy-paste whole test classes and rename them. A **shared contract** verifies requirement changes across every route; dedicated tests describe only genuine differences.

## 8. A JUnit 5 Contract Test Interface

You can define a test interface and have each adapter implement it. The example below uses a test-harness abstraction; each concrete adapter test provides setup, transport simulation, and submission inspection.

```java
public interface ProviderContractHarness
        extends AutoCloseable {

    MailProviderPort provider();

    MailSubmissionCommand validCommand();

    void simulateAcceptedSubmission();

    int submissionCount();

    CapturedMail lastSubmittedMail();

    @Override
    void close() throws Exception;
}

public record CapturedMail(
        String subject,
        String plainText,
        String html,
        java.util.List<String> recipients
) {
}
```

Shared contract test:

```java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

public interface MailProviderContract {

    ProviderContractHarness newHarness() throws Exception;

    @Test
    default void acceptedSubmissionDoesNotMeanDelivered()
            throws Exception {

        try (ProviderContractHarness harness = newHarness()) {
            harness.simulateAcceptedSubmission();

            MailSubmissionCommand command =
                    harness.validCommand();

            ProviderSubmissionResult result =
                    harness.provider().submit(
                            command,
                            "attempt-001"
                    );

            assertThat(result.outcome())
                    .isEqualTo(SubmissionOutcome.ACCEPTED);

            assertThat(result.providerRoute())
                    .isEqualTo(
                            harness.provider().routeId()
                    );

            assertThat(harness.submissionCount())
                    .isEqualTo(1);
        }
    }

    @Test
    default void retainsCoreMessageData()
            throws Exception {

        try (ProviderContractHarness harness = newHarness()) {
            harness.simulateAcceptedSubmission();

            MailSubmissionCommand command =
                    harness.validCommand();

            harness.provider().submit(command, "attempt-002");

            CapturedMail captured =
                    harness.lastSubmittedMail();

            assertThat(captured.subject())
                    .isEqualTo(command.subject());

            assertThat(captured.recipients())
                    .containsExactlyElementsOf(
                            command.recipients()
                    );
        }
    }
}
```

This is a skeleton: `ProviderContractHarness` must be implemented separately for SMTP A/B and API C. Tests make no Internet calls because the harness uses fake/test transports.

A concrete class:

```java
class SmtpProviderAContractTest
        implements MailProviderContract {

    @Override
    public ProviderContractHarness newHarness()
            throws Exception {
        return SmtpProviderATestHarness.create();
    }
}
```

Using a test interface is not mandatory; abstract base classes or factory-based parameterized tests also work. What matters is **running the same assertions against every provider implementation**.

## 9. Common Invariants for the Shared Contract

Fundamental invariants:

- Do not send when required `notificationId`, recipients, or sender profiles are invalid.
- Every recipient in the command is mapped accurately per contract without silent drops.
- Subject, plain text, and HTML carry exact content or approved fallbacks.
- Unicode values are not corrupted during mapping.
- `submit` never claims `DELIVERED` upon mere SMTP/API acceptance.
- One synchronous invocation starts **one transport attempt** per contract; automatic retries must be modeled separately.
- Never return `ACCEPTED` after transport actually rejects.
- When outcome is unclear, never classify as definitely rejected.
- Error codes in results belong to the normalized error-category set.
- Never return provider credentials in caller-facing log fields.
- Unsupported capabilities produce clear failures or use an approved alternate route.
- Retries never morph into creating a brand-new notification.
- Never send through a disabled or unconfigured provider.

Tests must not demand every route return the same `providerMessageId`, since some providers do not emit one at submit time.

## 10. Sender and Recipient Contracts

`From`, `Reply-To`, and SMTP envelope sender addresses are not identical.

Email example:

```text
From: Notifications <notifications@example.org>
Reply-To: support@example.org
To: customer@example.net
Subject: Order confirmed
```

SMTP may use a different envelope sender:

```text
MAIL FROM:<bounce-route@example.org>
RCPT TO:<customer@example.net>
```

Providers can enforce policies on Header From, sender domain, or envelope sender. Other adapters set bounce addresses automatically.

Contract tests should verify:

1. Sender profile is drawn from the authorized catalog.
2. `From` header matches the approved address.
3. `Reply-To` presence/value matches requirements.
4. Envelope sender/return path follows route policy where configurable.
5. Callers cannot arbitrarily spoof domains.
6. `To`/`Cc`/`Bcc` recipients are never swapped or leaked unintentionally.
7. Provider rejections for sender authorization map accurately.
8. During failover, backup routes hold permission to send under that sender identity.

### Per-Recipient Contract

Some providers process multiple recipients in one submission; outcomes can vary per recipient. If the application requires per-person status, define **one logical notification per recipient** or a `RecipientSubmissionOutcome` model.

Never collapse all recipients into a single accepted status if the provider returns partial acceptance. Include test cases where one recipient is accepted and another is rejected—on transports that support that behavior.

## 11. MIME Contract: Subject, HTML, Plain Text, and Charset

For SMTP providers, `JavaMailSenderImpl` uses Jakarta Mail to assemble messages. In tests, inspect MIME structure in memory without real sending.

Example:

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message =
        new JavaMailSenderImpl().createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Order #102 confirmation 🎉");
helper.setText(
        "Order #102 has been confirmed.",
        "<p>Order <strong>102</strong> has been confirmed.</p>"
);

message.saveChanges();
```

Assertions should check:

- `message.getSubject()` returns the exact Unicode string.
- Both `text/plain` and `text/html` exist when required by contract.
- Multipart mode/MIME tree matches attachments/inline resources.
- `To`, `Cc`, `Bcc`, and `Reply-To` are accurate.
- Charset on text parts is configured properly.
- No raw header injection via subject or filename.
- Template data has proper HTML escaping in the renderer layer.

**Do not rely on fixed multipart part indexes.** Traverse the MIME tree by content type and disposition because `multipart/mixed` and `multipart/related` can nest.

### SMTP Does Not Prove Client Rendering

Valid MIME structure does not guarantee Outlook, Gmail, and other mail clients render identically. When visual fidelity matters, run separate preview/visual tests. Provider contract tests focus on **submitted data and format**, not inbox screenshots across every client.

## 12. Attachments and Inline Content: Testing Fidelity

Fields to check when an adapter supports attachments:

| Data | Invariant to verify |
|---|---|
| Filename | Safe display name, policy-compliant encoding/Unicode |
| Content type | Exact permitted MIME type |
| Bytes | After decoding, bytes match the approved source |
| Size | Within provider/route limits |
| Disposition | Accurate `attachment` or `inline` |
| CID | HTML `cid:...` matches the inline part's `Content-ID` |
| File count | No dropped, duplicated, or swapped files |
| Access | Reads only authorized storage keys/attachment IDs |

Fixtures to include:

- Small PDF file from test bytes.
- Filename with Vietnamese or Unicode characters.
- Empty attachment if policy allows/rejects it.
- File right near the size ceiling.
- An inline image with `Content-ID`.
- A filename containing CR/LF rejected before building MIME.

Never use real user attachments in contract tests. Run data checks in controlled environments; logs record only attachment IDs or sizes, never contents.

### Size Limits Must Be Tested per Route

Providers may cap total MIME size rather than raw file bytes. Base64-encoded binary attachments expand payload size. If capabilities declare `maxMimeBytes`, tests must enforce the limit as actually measured or with headroom rather than only checking `Files.size(...)` per file.

## 13. Transport Contract: STARTTLS, Implicit TLS, and AUTH

For SMTP, test **transport configuration** separately per provider.

STARTTLS example:

```yaml
mail:
  providers:
    route-a:
      host: smtp-a.example.org
      port: 587
      transport: starttls
      auth: password
```

Implicit TLS example:

```yaml
mail:
  providers:
    route-b:
      host: smtp-b.example.org
      port: 465
      transport: implicit-tls
      auth: oauth2
```

This is application-model YAML, **not default Spring Boot properties**. The adapter must map it to accurate Jakarta Mail configuration for each route.

STARTTLS typically requires:

```properties
mail.smtp.auth=true
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
```

Implicit TLS typically requires:

```properties
mail.smtp.auth=true
mail.smtp.ssl.enable=true
```

Properties must match the chosen provider and transport. Never enable both modes out of habit or disable `starttls.required` to bypass a TLS error in production.

### Operational Checks to Verify

- Connections target the exact hostname/port.
- STARTTLS is enforced when policy requires it.
- Credentials are never sent over an unprotected channel.
- TLS certificate/hostname verification obeys chosen policy.
- Username format is right; credentials come from a secret source.
- Appropriate `PLAIN`/`LOGIN`/`XOAUTH2` mechanism.
- Connection and authentication timeouts are bounded.
- Credentials or tokens are never printed to SMTP debug logs.

Config tests checking property values alone do not prove the live endpoint has valid certificates and login rights. That requires controlled staging/sandbox verification.

## 14. OAuth2/XOAUTH2 Needs a Token-Lifecycle Contract

An SMTP route may use tokens instead of passwords. The contract is then more than "set `mail.smtp.auth.mechanisms=XOAUTH2`."

Verify:

1. The app acquires tokens with the right SMTP scopes/permissions.
2. Tokens belong to the right mailbox/tenant under provider policy.
3. Expired tokens refresh safely before use.
4. Revoked or under-scoped tokens are classified clearly.
5. Never keep retrying with the same broken token.
6. Never log access tokens or refresh tokens.
7. Concurrent refreshes do not storm the identity provider.
8. Rotating secrets/certificates causes the route to pick up new credentials.

Example test of token-supplier logic:

```java
@Test
void refreshesExpiredTokenBeforeSubmission() {
    TokenSupplier supplier = fakeTokenSupplier(
            expiredToken(),
            freshToken()
    );

    MailProviderPort provider =
            createOauthSmtpProvider(supplier);

    provider.submit(
            validCommand(),
            "attempt-token-001"
    );

    assertThat(supplier.refreshCount()).isEqualTo(1);
}
```

Types/helpers `TokenSupplier`, `fakeTokenSupplier`, `expiredToken`, and `createOauthSmtpProvider` are illustrative fixtures, not built-in Spring APIs.

Also test that a failed token refresh does not make the adapter send requests with a stale token outside policy.

## 15. SMTP Contract: Accepted Does Not Mean Delivered

During SMTP submission:

```text
EHLO
STARTTLS / AUTH
MAIL FROM
RCPT TO
DATA
MIME body
Server: 250 queued/accepted
```

A success reply after DATA usually means the **next-hop SMTP server accepted the message for processing**. It does not prove the destination MX accepted it, it landed in the inbox, or the user read it.

Provider contract tests must verify this mapping:

```text
SMTP transport returns normally
       -> SubmissionOutcome.ACCEPTED

SMTP explicitly rejects before acceptance
       -> SubmissionOutcome.REJECTED

Connection lost at uncertain stage
       -> SubmissionOutcome.UNKNOWN
```

Never map submission success to `DELIVERED`. If a provider emits a `delivered` webhook later, that is a **separate contract**.

### Testing SMTP Response Codes

| Simulated scenario | Expected classification |
|---|---|
| AUTH 535 | Rejected/authentication; usually fix credentials/permissions |
| Clear recipient 550 | Rejected/recipient or policy depending on context |
| Temporary 421/451 | Temporarily rejected or transient per confirmed stage |
| SMTP 250 after DATA | Accepted by next-hop SMTP |
| Timeout before connect | Typically proven message was not submitted |
| Timeout after transmitting DATA, no final reply | Unknown outcome without conclusive evidence |
| Some recipients accepted, others rejected | Partial outcome per transport and contract |
| Server lacks required AUTH mechanism | Configuration/protocol failure |

Do not collapse every `MessagingException` or `MailException` into one outcome. Inspect causes and the stage where failure occurred.

## 16. HTTP API Contract: Method, Headers, Payload, and Response

An HTTP API provider might expect:

```http
POST /v1/messages
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: <key-if-supported>

{
  "from": "notifications@example.org",
  "to": ["customer@example.net"],
  "subject": "Order confirmed",
  "text": "Your order is confirmed",
  "html": "<p>Your order is confirmed</p>"
}
```

This is a hypothetical example, not a specific vendor's schema.

Protocol tests should verify:

- Exact HTTP method/path/API version.
- Authorization header sent over HTTPS and never leaked to logs.
- Exact Content-Type and JSON encoding.
- Recipient list never reordered, dropped, or augmented.
- Exact plain/HTML mapping.
- Custom metadata sent only if supported by the API.
- Proper attachment encoding and size limits.
- Request IDs/idempotency keys used strictly per published contract.
- HTTP success never interpreted beyond response semantics.

### Response Mapping Must Follow Provider Contracts

Suppose the API returns:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "messageId": "provider-message-801",
  "status": "queued"
}
```

The application should map this to **provider accepted/queued** per contract, never straight to delivered.

HTTP 200/201/202 do not mean the same thing across all providers; the payload may report some recipients rejected even when the HTTP request succeeded. When required, classifiers must inspect both status and response body.

### Error Messages Are Not Metric Labels

APIs can return detailed errors containing email addresses or request IDs. Never use raw error messages as `errorCategory` or Micrometer tags. Map into bounded categories such as `auth`, `rate_limit`, `invalid_sender`, `recipient_rejected`, `timeout`, `unknown`.

## 17. WireMock or HTTP Mock Server for Provider APIs

An HTTP mock server returns deterministic responses and captures/inspects adapter requests without touching the Internet.

Example using WireMock against a hypothetical API:

```java
import static com.github.tomakehurst.wiremock.client.WireMock.*;

@Test
void mapsAcceptedApiResponseWithoutClaimingDelivery() {
    wireMockServer.stubFor(
            post(urlEqualTo("/v1/messages"))
                .withHeader(
                        "Content-Type",
                        containing("application/json")
                )
                .willReturn(
                        aResponse()
                            .withStatus(202)
                            .withHeader(
                                    "Content-Type",
                                    "application/json"
                            )
                            .withBody(
                                    "{\"messageId\":\"provider-801\","
                                  + "\"status\":\"queued\"}"
                            )
                )
    );

    ProviderSubmissionResult result =
            apiProvider.submit(
                    validCommand(),
                    "attempt-api-001"
            );

    assertThat(result.outcome())
            .isEqualTo(SubmissionOutcome.ACCEPTED);

    assertThat(result.providerMessageId())
            .isEqualTo("provider-801");
}
```

`wireMockServer`, `apiProvider`, and `validCommand()` are fixtures initialized in real tests. The example only illustrates structure; WireMock packages/APIs depend on project version and test dependencies.

Extend tests for:

- `401/403`: authentication/authorization errors.
- `429` with retry hints if supported by the provider.
- `400` invalid payload or sender.
- `5xx` from the provider.
- Malformed JSON responses.
- Empty bodies.
- Connection dropped before reading the response.
- Duplicate requests on retry.
- API version changing required fields.

### Do Not Hardcode Retries from HTTP Status Alone

HTTP 429 usually indicates rate limiting, yet retry policy also depends on provider, idempotency, retry hints, deadlines, and whether the attempt may have been processed. HTTP 5xx does not always prove the request wasn't received—especially if the connection dropped after provider processing.

For uncertain states, map to `UNKNOWN` or choose policy-driven reconciliation rather than asserting definite rejection.

## 18. Testing Retry Hints and Rate Limits

Each provider enforces different limits:

- Requests/second.
- Messages/second.
- Recipients/second.
- Concurrent connections.
- Daily quotas.
- Attachment sizes.
- Quotas per account/tenant/sender domain.

Contracts must interpret throttling signals from providers accurately, such as SMTP 4xx or HTTP 429 and retry-guidance headers/bodies.

Case example:

```text
Given provider responds:
  HTTP 429
  Retry-After: 30

Then adapter:
  - classifies as RATE_LIMITED
  - does not immediately resend in a hot loop
  - exposes retry hint to scheduler when supported
  - keeps notification in durable queue
  - preserves notificationId
  - creates new attemptId on actual retry
```

`Retry-After` can be seconds or an HTTP-date per standard; if a provider uses a custom field, write a dedicated parser. Tests should cover missing, invalid, huge, and past timestamps.

**Retry hints are not commands overriding business TTL.** If an OTP expires before the retry time, transition the job to expired per policy rather than sending a useless code.

### System-Wide Limits

If multiple replicas share one provider quota, a unit test of a limiter inside one JVM does not prove aggregate send rate stays under quota. Test coordination or run multi-instance tests with fake clocks, fake providers, and a shared budget.

## 19. Idempotency Scope Differs by Provider

An HTTP API may support an idempotency key, yet verify:

- Within what scope does the provider consider the key unique?
- How long is its retention window?
- What happens when retrying the same key with a different body?
- Does the provider return the same message ID on repeated requests?
- Does the key cover one recipient or an entire batch?
- Does idempotency work in both sandbox and production?

If a provider does not document support, **never assume an `Idempotency-Key` header works**.

With SMTP, resending the same MIME `Message-ID` is not a deduplication guarantee honored by every server. Local outbox idempotency prevents creating duplicate logical notifications, yet duplicates can still happen if a worker disconnects after SMTP acceptance.

### Contract Test for APIs with Idempotency

```text
Attempt A:
  idempotencyKey = notification-001
  response lost after provider accepted

Attempt B (retry):
  idempotencyKey = notification-001
  same logical payload

Expected:
  follow provider's documented deduplication result
  record the returned provider ID/evidence
```

Do not label two retries "idempotent" if the adapter mints a fresh key each time while the provider expects a stable key. Conversely, never reuse one key for **two different notifications**.

## 20. Delivery Webhooks Are a Separate Post-Submission Contract

Some providers emit events:

```text
accepted
processed
deferred
delivered
bounced
complaint
suppressed
open
click
```

Event lists and naming vary by provider. Not every provider supports every event; even identically named events can carry **different semantics**.

Example:

```text
Provider X "delivered":
    recipient MX accepted message

Provider Y "delivered":
    event follows provider-specific handoff rule

Neither necessarily means:
    message landed in inbox
    recipient actually read the content
```

The contract should specify for each event:

- Origin and schema version.
- Provider message ID/recipient identifier fields.
- Event timestamp vs. receipt timestamp.
- Webhook authentication requirements.
- Deduplication mechanism.
- Possibility of out-of-order delivery.
- Handling of unknown event types.
- State-transition rules or event history.
- Level of evidence the event actually provides.

Never use normal return from `JavaMailSender.send` to fabricate a delivered event.

## 21. Testing Webhook Verification and Replay

Webhooks can be replayed when endpoints time out. They can also be forged if the app skips origin verification.

Tests must cover:

1. Validly signed payloads are accepted.
2. Payloads modified by a byte after signing are rejected.
3. Missing or invalid signatures are rejected.
4. Out-of-window timestamps are rejected when the provider uses timestamps.
5. Duplicate event IDs are not applied twice.
6. Provider A's events never write onto provider/route B.
7. Events about another recipient never update the wrong notification.
8. Unmapped events can be stored for reconciliation per policy without leaking data.
9. Oversized or schema-invalid payloads are rejected/bounded.
10. Out-of-order events never clobber existing data.

### Signatures Must Be Computed Over the Exact Data Defined by the Provider

Many webhooks compute signatures over **raw request body bytes**, sometimes combined with timestamps/headers. If code deserializes JSON and re-serializes before checking signatures, whitespace or field order can change and break verification.

Use the provider's documented algorithm and canonicalization rules. Never invent "compare a token in the query string" when the provider requires HMAC or asymmetric signatures.

### Correlating Webhooks Back to Notifications

A mapping table might hold:

| Field | Role |
|---|---|
| `notificationId` | Internal logical email |
| `attemptId` | Specific submission attempt |
| `providerRoute` | Route used to send |
| `providerMessageId` | Provider-assigned ID |
| `recipientRef` | Logical recipient |
| `providerEventId` | Event deduplication key |
| `eventType` | Provider-reported status |
| `occurredAt` | Timestamp recorded by provider |
| `receivedAt` | Timestamp received by our system |

If an SMTP provider returns no ID at submission, verify what guaranteed correlation mechanism it offers. Do not assume a custom `X-Correlation-ID` header always comes back in webhooks.

## 22. Out-of-Order Events: Test State Machines Instead of Last-Write-Wins

Example:

```text
12:00 Provider emits DELIVERED
12:01 Webhook DELIVERED received
12:02 Older DEFERRED webhook received
```

If handlers always take the latest-received event to overwrite status, the system can wrongly regress `DELIVERED` back to `DEFERRED`.

Contract test:

- Send a delivered event.
- Send an older deferred event arriving later.
- Verify event history preserves both.
- Verify derived state follows policy.
- `receivedAt` must never overwrite `occurredAt`.

Some providers can emit bounce/complaint after delivered; avoid overly rigid linear assumptions when contracts allow it. Prefer storing full provider event history and computing derived state from published business rules.

## 23. Error and Retryability Contracts

Define a shared error taxonomy, then map each provider's responses into it.

Example:

```java
public enum ProviderErrorCategory {
    AUTHENTICATION,
    AUTHORIZATION,
    INVALID_SENDER,
    INVALID_RECIPIENT,
    INVALID_MESSAGE,
    RATE_LIMITED,
    TEMPORARY_UNAVAILABLE,
    CONNECTION,
    TLS,
    QUOTA_EXCEEDED,
    UNKNOWN
}
```

Do not map every 4xx status to retryable and every 5xx to permanent when mixing SMTP and HTTP:

- **SMTP 4xx** usually indicates temporary failures, yet inspect command and extended code.
- **SMTP 5xx** usually indicates permanent rejection in that operation's context.
- **HTTP 4xx** usually indicates client errors, yet HTTP 429 can be retried after a delay.
- **HTTP 5xx** usually indicates server errors, yet does not guarantee the request wasn't processed.
- **Timeouts** can occur before or after the provider received the message.
- **OAuth token errors** may require refresh, permission updates, or halting the route.

### Simulated Mapping Table

| Signal | Suggested outcome | Error category | Retry |
|---|---|---|---|
| SMTP 535 AUTH reject | REJECTED | AUTHENTICATION | Do not endlessly retry same credential |
| SMTP 550 invalid recipient | REJECTED | INVALID_RECIPIENT | Usually no auto-retry |
| SMTP 421 pre-submission | Temporarily REJECTED | TEMPORARY_UNAVAILABLE | With backoff when appropriate |
| HTTP 429 with retry hint | Per contract | RATE_LIMITED | Defer per policy |
| HTTP 400 invalid sender | REJECTED | INVALID_SENDER | Fix config/permissions |
| HTTP connect timeout before transmitting request | Usually unsubmitted, if evidenced | CONNECTION | Classify by stage |
| Connection lost after uploading body | UNKNOWN if no evidence | UNKNOWN | Reconcile/controlled retry |
| SMTP 250 after DATA | ACCEPTED | None | Do not resend merely because webhook is missing |

These are directional rules; tests must rely on **real provider responses in context**, never mapping codes mechanically.

## 24. Simulating Failures Right at Network Boundaries

Mock transports should be able to simulate:

- Connect refused.
- DNS failures.
- TLS handshake failures.
- AUTH rejections.
- Slow greetings or response timeouts.
- Timeouts while sending request bodies.
- Connection drops before receiving final acceptance.
- Response accepted while local DB update fails.
- API 429/5xx with varying headers and bodies.
- Provider returning invalid JSON or missing required fields.

A critical test:

```text
Given:
  provider may have accepted message
  transport loses final response

When:
  adapter.submit(command)

Then:
  result is UNKNOWN
  notificationId remains unchanged
  attempt history stores uncertainty
  no automatic claim of definitive delivery
  retry policy considers duplicate risk
```

Not every failure needs simulation over real networks. Adapter-layer unit tests can inject fake transports throwing exceptions representing each stage; protocol integration tests cover trickier cases.

## 25. Provider Contracts and Processing Deadlines

Some providers exhibit high latency or notable webhook lag. Contracts should define clear time budgets:

- Connection timeout.
- Read/write timeout.
- Total submission deadline if the HTTP client supports it.
- Provider retry policy.
- Queue wait SLO.
- Notification TTL.
- Webhook delivery window.
- API polling/reconciliation interval.

For instance, an OTP email expires in 5 minutes while the provider retries for 15 minutes. The business contract must decide whether the job may still send. Never ignore `MailSubmissionCommand.expiresAt`.

### Do Not Equate Timeouts with Failed

When an adapter reports a timeout, record the stage if known. A request timing out **after provider processing** is completely different from failing to open a TCP connection at the start.

Tests must distinguish both cases, especially before enabling automatic failover.

## 26. Routing and Failover Also Have Contracts

With multiple providers, route selection commonly considers:

- Notification type (transactional, security, bulk).
- Sender domain/profile.
- Permitted tenant or region.
- Capabilities (attachments, HTML, metadata, event support).
- Availability/circuit breakers.
- Rate limits/quotas.
- Cost or operational goals.
- Data residency and data policies.

A router might use:

```java
public interface MailProviderRouter {
    MailProviderPort choose(
            MailSubmissionCommand command
    );
}
```

Router contract tests must verify:

1. Right route for the notification type.
2. Route has capabilities matching the message.
3. Disabled routes are never picked.
4. Sender profile is authorized on the route.
5. Data-residency policies are never breached.
6. When primary is unavailable, an eligible secondary is picked if policy allows.
7. Fallback never drops attachments/metadata.
8. No duplicate sends when primary state is UNKNOWN.
9. Retries preserve notification ID and generate a new attempt ID.
10. Every attempt records the exact provider route for webhook correlation.

### Failover Should Not Always Be Automatic

```text
Primary -> explicit reject before accepting
       -> eligible for fallback depending on policy

Primary -> accepted
       -> no failover just because delivery webhook is late

Primary -> unknown after request body
       -> reconcile or controlled policy; duplicate risk
```

This is one of the most important contracts in multi-provider systems. If an adapter drops outcome details, the router can fail over wrongly and create two emails.

## 27. Data Contracts When Switching Providers

Providers can impose different formatting requirements for:

- Sender display name and Reply-To.
- Unicode subject encoding.
- Custom headers or metadata.
- Attachment content types and filenames.
- Inline images/CIDs.
- Provider-side vs. application-side template rendering.
- Tracking, unsubscribe, and category fields.
- Recipient personalization.
- DKIM signing and sender domains.
- Return-Path/bounce handling.

If the app **pre-renders and sends MIME** over SMTP, adapters receive rendered content. If a provider API supports template IDs and variables, adapters can pass a **template reference** instead of HTML. Those two modes have very different contracts.

### Choose One Source of Truth for Content

Across multiple providers, it is often cleaner for the application to render subject/plain/HTML once and pass them to adapters. That reduces the risk of providers rendering differently.

If provider-side templates must be used:

- Version templates per provider.
- Persist mappings from logical template → provider template ID.
- Test missing variables, locales, fallbacks, and placeholder syntax.
- Test output previews if the API allows.
- Never assume two providers share identical Mustache/Handlebars semantics.
- Plan for failover when secondary lacks the matching template version.

**Never automatically swap from one provider template ID to another** without a verified mapping or equivalent rendered output.

## 28. Observability and Correlation Across Providers

Each attempt should record:

```text
correlationId = corr-801
notificationId = notif-601
attemptId = attempt-601-02
providerRoute = smtp-secondary
transport = SMTP
submissionOutcome = ACCEPTED
providerMessageId = null (if unavailable)
```

Later provider events may carry:

```text
providerRoute = smtp-secondary
providerEventId = evt-921
providerMessageId = provider-msg-204
eventType = delivered
```

When contract-testing, verify IDs stay within their **proper scope**:

- `correlationId`: business workflow.
- `notificationId`: logical notification.
- `attemptId`: one send trial.
- MIME `Message-ID`: protocol email header.
- `providerMessageId`: provider-issued ID.
- `providerEventId`: callback event ID.

Never assume one ID can substitute for another. Mappings must be stored durably whenever webhooks may arrive hours later.

### Metrics for Provider Tests

Useful meters:

```text
mail.provider.submission.attempt
mail.provider.submission.accepted
mail.provider.submission.rejected
mail.provider.submission.unknown
mail.provider.throttled
mail.provider.event.received
mail.provider.event.rejected
mail.provider.event.duplicate
```

Tags should come from bounded sets such as `route`, `transport`, `outcome`, and `errorCategory`. Never use notification IDs, recipients, or raw exceptions as metric tags due to high cardinality and PII risks.

## 29. Contract Testing in CI Without Production Credentials

A recommended pipeline:

```text
Pull request
    |
    +--> Unit contract suite (all adapters)
    +--> SMTP protocol tests with local server
    +--> HTTP API tests with mock server
    +--> Webhook signature/schema tests
    +--> Routing/failover tests
    |
    v
Merge / release candidate
    |
    +--> Provider sandbox verification (approved secrets)
    +--> Contract schema compatibility checks
    |
    v
Controlled deployment
    |
    +--> Low-rate synthetic canary if authorized
    +--> Metrics + webhook monitoring
```

Safeguards:

- Pull request CI from untrusted code must never access production credentials.
- Sandbox credentials have minimal permissions.
- SMTP test servers only capture test mail without relaying to the Internet.
- HTTP mock servers run only on local/test networks.
- Never send to arbitrary contributor-chosen recipients.
- Never log tokens, passwords, raw AUTH commands, or presigned attachment URLs.
- Keep tests isolated with cleanup; avoid shared mailboxes prone to interference.

### Naming Tests by Nature

Use a naming convention:

```text
SmtpProviderAContractTest
SmtpProviderAProtocolTest
SmtpProviderAStagingVerificationTest

ApiProviderCContractTest
ApiProviderCProtocolTest
ApiProviderCStagingVerificationTest

ProviderRoutingContractTest
ProviderWebhookContractTest
```

Staging verification should run only when authorized secrets/sandboxes are present; otherwise report SKIPPED per test framework or pipeline policy—never silently report "provider contract passed" when only mocks ran.

## 30. Contract Drift: Provider Changes Policy or Responses

Even when your code does not change, a provider can:

- Drop support for legacy AUTH mechanisms.
- Change quotas, size limits, or recipient limits.
- Require new sender/domain verification.
- Add or remove JSON fields.
- Change webhook signature schemes or event schemas.
- Change status codes or retry advice.
- Split API endpoints by region.
- Ban an attachment type.
- Change how provider message IDs are issued.
- Launch a new API version or deprecate an old one.

This is **contract drift**: the external environment no longer matches assumptions encoded in your adapter.

Mitigations:

1. Explicitly record supported API/protocol versions.
2. Track changelogs and deprecation deadlines.
3. Schedule approved schema/provider verification tests.
4. Monitor new error categories and unknown responses.
5. Maintain versioned contract fixtures.
6. When changing provider/API versions, run both shared and provider-specific suites.
7. Support disabling a route via config when a contract breaks.
8. Never auto-failover to a route lacking required capabilities.

**Never let an always-green mock test fool you into believing the live provider is still compatible.** Mocks only know scenarios your team already modeled.

## 31. Versioning Contract Fixtures

A fixture set might look like:

```text
contracts/
  smtp/
    accepted-response.txt
    auth-rejected-response.txt
    temporary-failure-response.txt
  api-provider-c/
    v1/
      accepted.json
      rate-limited.json
      invalid-sender.json
      webhook-delivered.json
      webhook-bounced.json
    v2/
      accepted.json
      webhook-delivered.json
```

This is a reference layout, not a mandatory project directory structure.

When updating fixtures:

- Record provider and version.
- Record approved collection source/conditions.
- Strip tokens, real emails, and PII.
- Never copy responses containing customer data into the repo.
- Keep fixtures reproducible in CI.
- When schemas change, review impact on mappings and event stores.

Updating snapshots/fixtures to turn tests green is not enough; verify **the new response semantics** do not corrupt business states.

## 32. Sandbox Testing: What Must Really Be Verified

Sandboxes may use separate credentials and behave differently from production. A checklist:

| Area | Check |
|---|---|
| Authentication | Credentials/scopes valid, token refresh, API/SMTP rights |
| Sender | Verified sender/domain and permission to use From |
| Transport | DNS, endpoint, TLS, port, certificates |
| Submission | Accepted response, message ID, status/body |
| Content | Unicode, HTML/plain, attachments if supported by sandbox |
| Limits | Some limits differ from production — document clearly |
| Webhooks | Event schema, signatures, IDs, duplicate handling |
| Failures | Failures that can be intentionally simulated in sandbox |
| Monitoring | Logs/metrics tagged with exact route and attempt |
| Isolation | No real mail sent outside allowlist; no production data |

Sandbox tests **do not need to brute-force credentials** or try locking provider accounts. Errors like 401/429/5xx belong in protocol tests; sandboxes confirm permitted and viable behaviors.

Some sandboxes return success without performing real delivery. Never mark those tests "confirmed delivered." Record `SANDBOX_ACCEPTED` or an equivalent milestone.

## 33. Testing Failover with Failing Providers

Scenario example:

```text
Notification N
  |
  +-- Attempt A1 at Provider A
  |      -> known rejection (temporary)
  |
  +-- Policy checks Provider B capabilities
  |
  +-- Attempt B1 at Provider B
         -> accepted
```

Assertions:

- Notification ID unchanged.
- Attempt ID A1 differs from B1.
- Logs and DB record the exact route per attempt.
- Provider B supports the right sender, attachments, recipients, and region.
- Acceptance from B is not mistaken for delivered.
- No extra send occurs on A after B accepted just because a retry scheduler still had a job.
- A1 is never marked delivered when B1 receives a webhook.
- Error reasons use a stable taxonomy.

Another scenario:

```text
Provider A accepts request but response is lost
  -> outcome UNKNOWN

Router:
  -> must not blindly submit to B as though A definitely rejected
```

Depending on policy, apply reconciliation, deferral, or controlled retries acknowledging duplicate risk.

### Sender Identity During Failover

A domain verified on A is not automatically verified on B. Contract tests must verify backup routes have matching sender/DKIM/SPF/DMARC configs before taking traffic. This is not merely an HTTP 200 or SMTP 250 concern—it affects deliverability and security policy.

## 34. Multi-Provider Testing in Multi-Tenant Environments

If the application selects providers by tenant or region, tests must confirm:

- Tenant A cannot use tenant B's credentials/sender profile.
- Route selection reads tenant from security context or verified records, never trusting unverified input.
- Outbox records persist needed route/policy context.
- Workers on other replicas reconstruct the exact sender profile.
- Provider webhooks update only notifications belonging to the matching route/tenant.
- Cross-region failover honors data residency.
- Recipient addresses never leak into metric labels or raw debug logs.
- Config rotation does not cause in-flight requests to use the wrong tenant token.

Avoid using raw unbounded `tenantId` as a Micrometer metric tag when tenant counts are large. For per-tenant monitoring, use durable storage and access-controlled query systems.

## 35. Matrix-Driven Test Case Suite

| Scenario | Shared contract | Provider-specific |
|---|---|---|
| Valid text-only email | Yes | Check transport/response |
| HTML and plain text | Yes | Check encoding/MIME/API mapping |
| Invalid recipient | Yes | Specific error code and policy |
| Unapproved sender | Yes | Real From/domain permissions |
| Unicode subject | Yes | Header encoding or API JSON |
| Attachment near size limit | Yes | Per-provider limit/encoding |
| Inline CID | Only when capability supported | Dedicated MIME/API contract |
| SMTP AUTH reject | N/A for API tokens | SMTP-specific |
| Expired API token | N/A for SMTP passwords | API-specific |
| HTTP 429 Retry-After | Common taxonomy | API-specific parsing |
| SMTP 4xx temporary | Common taxonomy | SMTP-specific |
| Timeout after request body | Unknown outcome | Specific mock transport |
| Provider accepted | Never map to delivered | Response-specific |
| Duplicate webhook | Shared dedupe | Signature/event schema |
| Out-of-order events | Shared state policy | Timestamp/ID semantics |
| Fallback route | No duplicates, keep logical ID | Capabilities/identity |
| Provider-specific quota | Shared bounds | Per-route quotas/hints |
| Credential rotation | No secret leaks, failure handling | Auth lifecycle |
| Missing capability | Fail cleanly or valid route | Capability matrix |
| Malformed response | Controlled unknown/protocol error | Schema parser |
| Sandbox accepted/no delivery | Never claim delivered | Sandbox traits |

This matrix is not an identical mandatory list for every product. Run tests meaningful to each provider's capabilities; for unsupported features, include a test proving **the application rejects explicitly** instead of skipping silently.

## 36. Boundary-Data Test Scenarios

Beyond response codes, test data boundaries:

- `null`, empty, whitespace-only, and malformed recipient addresses.
- Single recipient, multiple recipients, and duplicate recipients.
- Unicode subjects, emojis, quotes, CR/LF, or overly long strings.
- Empty body, plain-only, HTML-only, plain+HTML.
- HTML containing escaped user data.
- Empty attachments, multiple attachments, and near-limit sizes.
- Filenames with accents, control characters, or path separators.
- Nonexistent or disabled sender profiles.
- Expired timestamps in the past.
- Template versions absent on a provider-side route.
- Missing, oversized, or schema-invalid provider IDs.
- Webhook payloads with duplicate event IDs and anomalous timestamps.

When required fields are missing, the adapter must make zero network calls. Example:

```java
@Test
void rejectsMissingRecipientBeforeCallingTransport() {
    MailSubmissionCommand invalid =
            commandWithRecipients(java.util.List.of());

    assertThatThrownBy(() ->
            provider.submit(invalid, "attempt-invalid")
    ).isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(transportClient);
}
```

`commandWithRecipients`, `provider`, and `transportClient` are fixtures; if the app uses a validation-result type instead of exceptions, assertions must follow that contract.

## 37. Testing Correct Provider Configuration Wiring

When using multiple `JavaMailSenderImpl` beans, guard against injecting the wrong bean.

Example Spring configuration with explicit names:

```java
@Configuration
public class MailProvidersConfiguration {

    @Bean("primaryMailSender")
    public JavaMailSenderImpl primaryMailSender(
            PrimarySmtpProperties properties
    ) {
        return configureSender(properties);
    }

    @Bean("backupMailSender")
    public JavaMailSenderImpl backupMailSender(
            BackupSmtpProperties properties
    ) {
        return configureSender(properties);
    }
}
```

`PrimarySmtpProperties`, `BackupSmtpProperties`, and `configureSender` are illustrative application components.

In the adapter:

```java
public SmtpBackupAdapter(
        @Qualifier("backupMailSender")
        JavaMailSender sender
) {
    this.sender = sender;
}
```

Contract/component tests must ensure:

1. Primary adapter uses primary sender; backup adapter uses backup sender.
2. Credentials never mix across configurations.
3. TLS/auth properties match each bean.
4. Sender profile/From mapping matches the route.
5. When a bean is missing, the app fails configuration explicitly instead of falling back silently.
6. Secrets never appear in `toString()`, health details, or logs.
7. Never use `@Primary` as a shortcut causing every adapter to share one sender.

Apply the same checks to custom HTTP clients for base URLs and provider-specific authentication.

## 38. Never Run Real Sends Inside Health Indicators

A mail provider may offer connection tests or health endpoints. Yet health checks must never invoke `submit` and send real emails on every scrape.

Levels to separate:

- Adapter config has valid required fields.
- SMTP connect/auth via `JavaMailSenderImpl.testConnection()` when permitted.
- HTTP provider health/status API if available and documented.
- Worker/queue/outbox health.
- Intentional synthetic E2E sends on a schedule to allowlisted recipients.

A sandbox contract test may send test emails because it is **an approved test**, not a periodic health probe.

With multiple providers, running connection tests across all routes on every `GET /actuator/health` can cause excessive AUTH calls, slow responses, or trigger rate limits. Use caching, background probes, and proper health groups.

## 39. Reducing Flaky Tests and Environment Coupling

Contract tests turn flaky easily when relying on:

- Real email providers in every unit test.
- Unfixed current time via `Instant.now()`.
- Shared test mailboxes across multiple pipelines.
- Retries using `Thread.sleep(...)` with fragile timings.
- Untracked random IDs in assertions.
- API rate limits shared across concurrent CI jobs.
- Async webhooks without deterministic waiting/correlation.
- Public DNS/Internet conditions outside project control.

Remedies:

1. Mock protocols for unit tests.
2. Use injectable clocks/ID suppliers in fixtures.
3. Use fake retry schedulers to assert scheduled times instead of real sleeping.
4. Bind random local ports/servers whenever possible.
5. Namespace notification IDs per test run.
6. Set finite timeouts and clean up all resources.
7. Separate sandbox verification from pull-request checks.
8. Log failures with attempt/provider route, without secrets.
9. When external tests fail, distinguish **provider unavailable** from **contract violated**.
10. Never auto-retry failing tests repeatedly to mask real contract bugs.

### Test Reporting Must Be Honest

If sandbox tests did not run due to missing tokens, report **SKIPPED** in that pipeline stage; never present mock results as real provider verification.

If staging is in an outage, record it as a verification blocker; never relax assertions to go "green" before understanding the semantics.

## 40. Testing Workflow When Onboarding a New Provider

A practical workflow:

1. **Gather official documentation:** SMTP/API endpoints, authentication, sender policies, payloads, error models, quotas, webhooks.
2. **Create a capability profile:** clearly mark supported/unsupported/unknown.
3. **Define mapping to the common port:** notification, recipient, content, attachments, outcomes.
4. **Build the adapter:** isolate mapping and transport from business services.
5. **Run the shared contract suite:** invariants across all providers.
6. **Write provider-specific protocol tests:** AUTH/TLS or HTTP schemas/headers/status codes.
7. **Test failure classification:** 4xx/5xx/429, timeouts, partial acceptance, missing IDs.
8. **Test webhooks:** signatures, deduplication, mapping, out-of-order events.
9. **Test routing/failover:** sender capabilities, policies, unknown outcomes.
10. **Sandbox verification:** real credentials/senders/responses within permitted limits.
11. **Controlled canary if needed:** synthetic mailboxes, low rate, close monitoring.
12. **Monitor post-rollout:** accepted rates, unknown errors, throttling, bounces, and contract drift.
13. **Version the contract:** when the provider updates APIs or policies, update fixtures/tests under review.

If a provider lacks an important feature, deliberately update route policies or product contracts—never simply delete assertions to push the provider into production.

## 41. Runbook When a Provider Breaks Contract

### Case A: SMTP AUTH Suddenly Gets Rejected

- Identify affected routes and instance counts.
- Check secret/token rotation, AUTH policies, endpoints, and TLS.
- Stop endlessly retrying the same credentials.
- Run bounded connectivity checks.
- If failing over, confirm secondary has sender rights and data eligibility.
- Document which contract assumption changed.

### Case B: API Emits a New JSON Field or Drops an Old One

- Record response version/status and safe parser failure.
- Capture raw responses under access controls if policy permits; strip PII/secrets.
- Without clear acceptance evidence, never report success.
- Update fixtures and mappings against provider docs.
- Re-run protocol tests and staging verification.

### Case C: Delivered Webhook Fails to Map to a Message

- Verify signature/schema/provider route.
- Inspect provider message ID and recipient mapping.
- Check for events from old attempts or failovers.
- Never update notifications by correlation ID alone.
- Route unmapped events to investigation/reconciliation so data is not lost.

### Case D: Provider Throttling Spikes After Adding Replicas

- Check aggregate send rate across all instances.
- Check quotas at account/region/sender level, not only local limiters.
- Reduce concurrency/rate; enable backoff and jitter.
- Never replay the entire backlog at once.
- Re-test retry hints and fairness before scaling up again.

### Case E: Mock Tests Pass Yet Sandbox Fails

- Verify mocks accurately modeled the provider documentation.
- Compare API versions and sandbox account permissions.
- Separate test-environment limits/policies from production.
- Never assume sandbox success proves delivery.
- Update capability profiles and add controlled regression fixtures.

## 42. Testing Checklist Before Enabling a Provider

| Question | Expected |
|---|---|
| Is the common provider-port contract documented? | Yes |
| Does the shared contract suite run against the new adapter? | Yes |
| Is the capability profile verified and versioned? | Yes |
| Are unsupported attachments/recipients rejected rather than silently dropped? | Yes |
| Is the sender profile authorized on the route? | Yes |
| Are Auth/TLS configured properly without leaking credentials over weak channels? | Yes |
| Are Subject, HTML/plain, Unicode, and MIME mappings accurate? | Yes |
| Is accepted kept distinct from delivered? | Yes |
| Are rejected and unknown clearly distinguished? | Yes |
| Can provider ID be null and handled cleanly? | Yes |
| Are error taxonomy and retryability tested? | Yes |
| Are rate limits/quotas enforced at the right scope? | Yes |
| Are webhooks authenticated and deduplicated if supported? | Yes |
| Do late/out-of-order events preserve correct state? | Yes |
| Does failover avoid blind duplicates when primary is UNKNOWN? | Yes |
| Are multi-tenant/region data policies verified? | Yes, if applicable |
| Do protocol mocks and sandbox tests serve separate goals? | Yes |
| Does CI avoid production credentials and arbitrary recipients? | Yes |
| Is there a runbook for contract drift? | Yes |
| Are logs/metrics tagged by provider route and attempt? | Yes |

## 43. Common Misconceptions

| Misconception | Reality |
|---|---|
| "Same interface means providers are 100% interchangeable" | Capabilities, policies, quotas, and event semantics differ. |
| "Mock send succeeded means the provider works" | Mocks only prove your code matches your own simulation. |
| "SMTP 250 means the recipient read the email" | Usually only next-hop SMTP acceptance at that step. |
| "Provider returned HTTP 202 means delivered" | HTTP 202 usually means accepted/queued per contract. |
| "Timeout definitely means not sent" | The provider may have processed it before the response dropped. |
| "All 4xx errors retry the same way" | SMTP and HTTP have different semantics; classify by stage/provider. |
| "Setting an idempotency header is enough" | Only works if the provider supports it with matching scope/keys. |
| "Every provider has delivered webhooks" | Some lack them or restrict them by plan/config. |
| "Custom email headers always come back in webhooks" | Provider-dependent; no universal guarantee. |
| "Failover to provider B is always safe" | Requires capabilities, sender identity, data policy, and primary's outcome. |
| "One sandbox test suffices for production" | Sandboxes can differ in limits/simulation and may not deliver for real. |
| "Adding workers beats rate limits" | Can worsen throttling and retry storms. |
| "Updating fixtures to make tests pass means done" | You must understand semantic changes and business-state impacts. |

## 44. Key Takeaways

- **Each provider's contract** covers supported capabilities, authentication/TLS, content mapping, sender/recipient policies, response semantics, quotas, webhooks, and errors.
- A common provider port decouples business services from SMTP/APIs, yet never implies all providers are identical.
- Use **shared contract tests** for universal invariants and **provider-specific tests** for real differences.
- Test SMTP protocols with test servers, HTTP providers with mock servers, and use sandbox/staging to verify live permissions and behavior.
- `JavaMailSender.send(...)` succeeding or HTTP API acceptance **does not prove inbox delivery**.
- Separate `ACCEPTED`, `REJECTED`, and `UNKNOWN` so blind retries/failovers do not cause duplicates.
- Never assume every provider supplies message IDs, idempotency, or delivery webhooks.
- Webhooks must be verified, deduplicated, mapped to the exact provider/recipient/attempt, and tolerant of out-of-order delivery.
- Unsupported capabilities must fail explicitly or route to a compatible provider—never silently drop data.
- Rate limits and quotas are finite resources, often shared across replicas.
- Keep notification IDs stable; generate a separate attempt ID per trial and record the attempt's provider route.
- Test credentials and sender permissions in approved environments; never use production credentials in unit/PR tests.
- Providers can change contracts even when your code stays still; maintain versioned fixtures, sandbox verification, and runbooks.
- Health probes must never auto-send real emails; synthetic delivery tests need dedicated schedules, mailboxes, and permissions.
- During failover, it is critical **not to alter the email's business meaning** and never assert an outcome transport has not proven.

**Conclusion:** In a multi-provider Spring Framework Mail system, reliability does not come from adding a new adapter and watching `send` return normally. It comes from **explicitly written contracts, a shared test suite applied to every adapter, dedicated protocol tests, and controlled verification against real providers**. When every route proves its capabilities, responses, limits, and delivery events, the application can switch routes, fail over, and upgrade integrations without sacrificing content accuracy, state integrity, or recipient data protection.
