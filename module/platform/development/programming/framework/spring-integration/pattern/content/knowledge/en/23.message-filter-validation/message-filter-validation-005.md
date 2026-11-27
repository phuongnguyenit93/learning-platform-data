# Discard vs Exception on Validation Failure

A **Message Filter** in Spring Integration decides whether a message may continue forward. When the predicate returns `false`, three outcomes are common: **drop the message**, **send the message to `discardChannel`**, or **throw an exception**. The difference is not just a Java DSL setting—it affects business logic, reliability, retries, broker ACKs, observability, and how the sender receives feedback.

This lesson belongs to the **Message filter and validation** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module's goal is learning to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, along with testing and observing processing branches.

**Key takeaway:** Do not conflate *not selected by a Filter* with *invalid data*. For cases that are **valid but business-ineligible** (such as not qualifying for a promotional campaign), controlled discard is usually appropriate. For **data contract violations** or unacceptable actions (missing required IDs, wrong data types, unauthorized access), a clear error outcome is required: throw an exception, return a validation error, or route to an audited quarantine depending on the architecture. Never let critical contract failures disappear like an ordinary filtered-out message.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish a **Filter predicate returning false** from a **validator throwing an exception**.
2. Understand Spring Integration `MessageFilter` defaults when a message is rejected.
3. Configure `discardChannel`, `discardFlow`, and `throwExceptionOnRejection(true)`.
4. Explain the behavior when **both discard channel and throw exception are enabled**.
5. Choose handling for expected rejections, malformed messages, security rejections, transient dependency failures, and internal bugs.
6. Interpret `MessageRejectedException` properly compared to validator/handler exceptions.
7. Distinguish `discardChannel` from `errorChannel`; understand exceptions in `DirectChannel` vs async flows.
8. Write Java DSL clearly showing pre-Filter validation and both rejection handling strategies.
9. Write JUnit 5 unit tests and integration tests against real Spring channels.
10. Control retry/redelivery, poison messages, DLQ/quarantine, and idempotency.
11. Design reason codes, audits, metrics, traces, and alerts without leaking data.
12. Avoid losing business actions when a Filter rejects a part needed by an Aggregator.

## 2. The Problem: Two Kinds of "Not Moving Forward"

Suppose a system receives `InvoiceSubmission` and runs a promotional campaign applying only to eligible invoices.

~~~text
InvoiceSubmission
  requestId = REQ-1001
  tenantId = tenant-a
  invoiceId = INV-1001
  amount = 250000 VND
  campaignEligible = false
~~~

The message above **has a valid format**, valid amount, and existing identity; it is simply **not selected** for campaign processing. Skipping the campaign branch is **not an input error**.

Another message:

~~~text
InvoiceSubmission
  requestId = REQ-1002
  tenantId = tenant-a
  invoiceId = ""
  amount = -15000 VND
  campaignEligible = true
~~~

This message **violates the data contract**: missing invoice ID and negative amount. If you evaluate `campaignEligible=true` and send it straight to the handler, the system may crash or persist corrupt data. If you drop it silently, senders and operators will never know why the invoice was never processed.

~~~mermaid
flowchart TD
    IN["Inbound message"] --> VALID{"Contract validation"}
    VALID -->|"Invalid"| ERR["Reject with reason / quarantine"]
    VALID -->|"Valid"| FILTER{"Business eligibility Filter"}
    FILTER -->|"Accepted"| NEXT["Normal processing"]
    FILTER -->|"Not eligible"| DISC["Discard/audit branch"]
~~~

**Validation** asks: *does the message satisfy the constraints for the system to process it safely?* **Filter** asks: *should a valid message participate in this branch?* Both decisions can work together, yet the more cleanly they are separated, the easier testing and operations become.

## 3. What Is a Filter in Spring Integration?

A Message Filter is an endpoint backed by a `MessageSelector` or a boolean-returning method/predicate. For every incoming message:

- `true`: the message proceeds to the Filter's output channel.
- `false`: the message does not reach the normal output channel; the endpoint applies its **rejection policy**.
- Selector throws an exception: this is a **handler failure**, not a `false` outcome; the exception follows the flow's error handling.

~~~mermaid
flowchart LR
    IN["Message input"] --> F{"MessageFilter predicate"}
    F -->|"true"| PASS["outputChannel"]
    F -->|"false"| R{"Rejection policy"}
    R --> DROP["Drop"]
    R --> DISC["discardChannel"]
    R --> EX["MessageRejectedException"]
~~~

Each Filter output chooses **between pass and rejection**; a Filter does not route messages to arbitrary channels by payload like a content-based Router.

### 3.1. `false` Does Not Mean Exception

A pure predicate:

~~~java
public boolean eligible(InvoiceSubmission invoice) {
    return invoice.campaignEligible();
}
~~~

returns `false` when the invoice does not participate in the campaign. It **throws no error** and does not claim invalid data. The Filter's configuration decides whether `false` is dropped, discarded, or throws an exception.

### 3.2. Throwing Inside a Predicate Differs from `throwExceptionOnRejection`

~~~java
public boolean check(InvoiceSubmission invoice) {
    if (invoice.invoiceId() == null
            || invoice.invoiceId().isBlank()) {
        throw new IllegalArgumentException(
                "INVOICE_ID_REQUIRED");
    }

    return invoice.campaignEligible();
}
~~~

Here, the missing ID causes the predicate to **throw `IllegalArgumentException`** rather than return `false`. `throwExceptionOnRejection(true)` only governs the **rejection path when the selector returns false**; it does not convert arbitrary exceptions into `MessageRejectedException`.

## 4. Four Options for Handling Rejection

In Spring Integration, a Filter offers `discardChannel` and `throwExceptionOnRejection`. Combining both flags produces this table:

| `discardChannel` | `throwExceptionOnRejection` | When predicate returns false |
|---|---|---|
| Not configured | `false` (default) | Message is dropped, does not go to normal output |
| Set | `false` | Message is sent to discard channel, no rejection exception thrown |
| Not configured | `true` | Throws `MessageRejectedException` |
| Set | `true` | **Sent to discard channel, then throws exception** |

**Warning:** the last option does not mean "just log and never fail". The discard handler may execute a side effect and then the exception still triggers caller/broker retry; without idempotency, discard-branch side effects can repeat.

### 4.1. Default: Drop

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible)
~~~

If the selector returns `false` with no discard channel or throw configured, the message **never reaches the output channel**. Since Spring Integration 6.1, `MessageFilter` may emit a **warning log** on default drops; do not describe the behavior as "completely traceless" across all versions.

### 4.2. Intentional Discard

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible,
        spec -> spec.discardChannel("campaign.rejected"))
~~~

On `false`, the message goes to `campaign.rejected`. This is a **business branch** for auditing, counting rejections, or signaling "not eligible". Do not automatically treat it as an error channel.

### 4.3. Exception on Rejection

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible,
        spec -> spec.throwExceptionOnRejection(true))
~~~

On `false`, the Filter throws `org.springframework.integration.MessageRejectedException`. Therefore, **avoid enabling this flag for normal business rules** when not being selected is a valid outcome and upstream callers do not expect an exception.

### 4.4. Both Discard and Exception

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible,
        spec -> spec
                .discardChannel("campaign.rejected")
                .throwExceptionOnRejection(true))
~~~

The message can pass through the discard branch **and then** raise an exception. If the discard branch calls an email API while the broker retries the message, duplicate emails can be sent. Only use this when you truly want to **audit/quarantine and then fail the attempt**, with idempotency, ACK, and retry contracts clearly defined.

## 5. When to Choose Discard vs When to Choose Exception?

| Situation | Nature | Usually appropriate handling | Why |
|---|---|---|---|
| Invoice not eligible for promotion | Expected business skip | Discard/explicit skip outcome | Not an error |
| Event too old, skipped by policy | Expected stale message | Audited/metered discard | Avoids useless retries |
| Duplicate message already processed | Expected idempotent no-op | Dedup discard or cached result | Prevents re-running side effects |
| Missing required invoice ID | Contract violation | Validation exception or quarantine | Cannot process safely |
| Negative amount outside contract | Contract violation | Exception/reject with reason | Producer must fix |
| Wrong payload schema/type | Contract violation | Reject, non-retryable | Retrying verbatim is futile |
| Unauthorized user | Security/authorization failure | Deny + audit, possibly exception | Must not reach handler |
| Payment API timeout | Transient dependency failure | Exception + bounded retry/reconciliation | Not a business filter false |
| DB deadlock | Infrastructure failure | Retry per policy | Must not be dropped as invalid |
| Invoice canceled before promo run | Domain policy | Discard or explicit state transition | Depends on SLA/contract |
| Foreign-key reference not found | Could be temporary or permanent | Reconcile/bounded retry or reject | Needs error source classification |

**There is no universal mapping** where "invalid = always retry". Exceptions require **error classification**: deterministic data errors should go to non-retryable rejection or quarantine, not infinite broker retries.

## 6. Discard Channel Is Not Error Channel

The two channels have different sources and purposes:

| Property | `discardChannel` | `errorChannel` |
|---|---|---|
| Input source | Selector `false` with discard configured | Exceptions published by error infrastructure |
| Typical payload | **Original rejected message** | `ErrorMessage` wrapping a `Throwable` |
| Trigger condition | Business/validation predicate rejection | Handler/poller/async exception |
| Reason details | No automatic detailed reason codes | `Throwable`/cause chain |
| Implies retry? | No | Depends on error handler/adapter |
| Can attach audit? | Yes | Yes |
| Guarantees ACK? | Not automatically | Not automatically |

Example:

~~~text
Filter returns false
  -> discardChannel: Message<InvoiceSubmission>

Filter throws MessageRejectedException in async task
  -> errorChannel (if routed by error handler):
     ErrorMessage(Throwable)
~~~

**Never randomly send an original message to `errorChannel` expecting downstream to receive an `ErrorMessage`.** Their payload contracts are different.

### 6.1. Discard Does Not Mean Business Success

A `MessageFilter` sending a message to a discard channel only indicates it **did not traverse normal output**. If an outbound broker requires an ACK or a Gateway expects a reply, your separate contract determines whether that counts as "completed" or "unprocessed".

### 6.2. Discard Loses Reason Details Unless Designed

A rejected message arriving at `discardChannel` is usually the **original message**. It does not automatically carry a `validationReason` header or constraint failure list.

If reasons are required:

- Compute and validate in a step prior to the Filter.
- Attach only **safe reason codes** after classification.
- Or let the discard flow run a pure classifier on the payload to build a `RejectionRecord`.
- Never copy full PII-containing payloads into logs/metrics.
- Be cautious if a predicate reads live database state: when the discard flow re-evaluates it, the result may have changed.

## 7. Classifying Validation Failures: Structural, Business Rules, and Infrastructure

The word "validation" covers several distinct concerns:

1. **Structural validation**: missing IDs, out-of-range amounts, incompatible schemas.
2. **Business invariant validation**: invoice belongs to another tenant, invalid transition, missing mandatory stock.
3. **Eligibility check**: well-formed, yet outside the campaign's target segment.
4. **Authentication/authorization**: sender lacks permission on the resource.
5. **Infrastructure availability**: database, broker, or external API is down.

A single Java method returning `boolean` for all five makes it hard to separate **valid skips**, **fixable errors**, **retryable errors**, and **security violations**.

### 7.1. Deciding Based on Recoverability

~~~mermaid
flowchart TD
    X["Message rejected or processing error"] --> Q{"Is this a valid business outcome?"}
    Q -->|"Yes"| D["Discard + audit/metric or explicit result"]
    Q -->|"No"| R{"Can retrying the exact message succeed?"}
    R -->|"No"| N["Reject + non-retryable quarantine/feedback"]
    R -->|"Yes"| T["Exception + bounded retry/backoff"]
    R -->|"Unsure"| U["Reconciliation/UNKNOWN state"]
~~~

Do not turn a validation failure into `false` **just to avoid an exception** if upstream callers need to know why the data was rejected.

## 8. Java 17 Model Used in the Examples

Example invoice submission:

~~~java
import java.math.BigDecimal;

public record InvoiceSubmission(
        String requestId,
        String tenantId,
        String invoiceId,
        BigDecimal amount,
        boolean campaignEligible
) {}
~~~

The record may hold invalid data; for clear testing, we **do not block invalid inputs in the constructor** in this example. At ingress, `SubmissionValidator` checks the fields.

### 8.1. Reason Code Enum

~~~java
public enum ValidationCode {
    REQUEST_ID_REQUIRED,
    TENANT_ID_REQUIRED,
    INVOICE_ID_REQUIRED,
    AMOUNT_REQUIRED,
    AMOUNT_MUST_BE_POSITIVE
}
~~~

### 8.2. Domain Validation Exception

~~~java
import java.util.List;

public final class InvalidSubmissionException
        extends RuntimeException {

    private final List<ValidationCode> codes;

    public InvalidSubmissionException(
            List<ValidationCode> codes) {
        super("INVALID_INVOICE_SUBMISSION");
        this.codes = List.copyOf(codes);
    }

    public List<ValidationCode> codes() {
        return codes;
    }
}
~~~

### 8.3. Pure Validator with Structured Error List

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public final class SubmissionValidator {

    public List<ValidationCode> validate(
            InvoiceSubmission submission) {

        if (submission == null) {
            return List.of(ValidationCode.REQUEST_ID_REQUIRED);
        }

        List<ValidationCode> failures = new ArrayList<>();

        if (blank(submission.requestId())) {
            failures.add(ValidationCode.REQUEST_ID_REQUIRED);
        }
        if (blank(submission.tenantId())) {
            failures.add(ValidationCode.TENANT_ID_REQUIRED);
        }
        if (blank(submission.invoiceId())) {
            failures.add(ValidationCode.INVOICE_ID_REQUIRED);
        }
        if (submission.amount() == null) {
            failures.add(ValidationCode.AMOUNT_REQUIRED);
        }
        else if (submission.amount()
                .compareTo(BigDecimal.ZERO) <= 0) {
            failures.add(ValidationCode.AMOUNT_MUST_BE_POSITIVE);
        }

        return List.copyOf(failures);
    }

    public boolean isValid(InvoiceSubmission submission) {
        return validate(submission).isEmpty();
    }

    public InvoiceSubmission requireValid(
            InvoiceSubmission submission) {

        List<ValidationCode> failures = validate(submission);
        if (!failures.isEmpty()) {
            throw new InvalidSubmissionException(failures);
        }

        return submission;
    }

    private boolean blank(String input) {
        return input == null || input.isBlank();
    }
}
~~~

This is **payload content validation**. Verifying that `tenantId` matches the authenticated principal is a separate responsibility at the security boundary. Do not treat `campaignEligible` as a structural validity condition, since a non-participating invoice is still valid.

### 8.4. Why Separate `requireValid` from `isValid`?

- `isValid` fits boolean Filters when only a true/false decision is needed.
- `requireValid` throws an exception rich in reason codes, convenient for producer feedback or non-retryable error handling.
- `validate` is pure logic reusable in unit tests, quarantine classifiers, and API validation.

A Filter with `throwExceptionOnRejection(true)` only yields `MessageRejectedException` because the selector returned false; it does not inherently carry the full `ValidationCode` list. When reasons are needed, prefer an explicit validator or an adapter adding reason metadata.

## 9. Option A: Reject via Discard Channel When Business-Ineligible

Flow illustrating **validation first, eligibility filter second**:

~~~text
Inbound InvoiceSubmission
  -> requireValid (invalid: exception)
  -> campaignEligible?
       true  -> accepted output
       false -> discard channel
~~~

### 9.1. Java DSL Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class DiscardOnBusinessSkipConfig {

    @Bean
    public SubmissionValidator submissionValidator() {
        return new SubmissionValidator();
    }

    @Bean(name = "campaign.discard.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "campaign.accepted")
    public PollableChannel accepted() {
        return new QueueChannel();
    }

    @Bean(name = "campaign.discarded")
    public PollableChannel discarded() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow campaignFilterFlow(
            SubmissionValidator validator) {

        return IntegrationFlow
                .from("campaign.discard.in")
                .transform(
                        InvoiceSubmission.class,
                        validator::requireValid)
                .filter(
                        InvoiceSubmission.class,
                        InvoiceSubmission::campaignEligible,
                        f -> f.discardChannel("campaign.discarded"))
                .channel("campaign.accepted")
                .get();
    }
}
~~~

This is a **synchronous flow on a `DirectChannel`** with output queues for testing. For valid-but-ineligible messages, the endpoint does not throw a rejection exception; it routes the message to `campaign.discarded`. For invalid messages, `requireValid` throws `InvalidSubmissionException` **before the Filter**, without invoking the discard branch.

### 9.2. Why Not Filter Directly on `invoiceId`?

If you write:

~~~java
.filter(InvoiceSubmission.class,
        invoice -> invoice.invoiceId() != null)
~~~

a message missing an ID may be **default-dropped** with no reason returned to the producer. For important data, **classify** and return explicit contract outcomes instead of using silent filters.

### 9.3. The Discard Branch Has Business Meaning

When a campaign does not apply, the discard branch can emit a `CampaignNotEligible` event or record a `SKIPPED` status. However, it should not blindly delete the invoice from the entire system: the Filter here only governs the **campaign branch**, not whether the invoice exists.

## 10. Option B: Throw Exception When the Selector Rejects Validation

The example below illustrates `throwExceptionOnRejection(true)`. It fits when the selector **performs validation only** and the caller needs to know the data failed the contract.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class ThrowOnInvalidConfig {

    @Bean
    public SubmissionValidator strictValidator() {
        return new SubmissionValidator();
    }

    @Bean(name = "strict.validation.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "strict.validation.accepted")
    public PollableChannel accepted() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow strictValidationFlow(
            SubmissionValidator validator) {

        return IntegrationFlow
                .from("strict.validation.in")
                .filter(
                        InvoiceSubmission.class,
                        validator::isValid,
                        f -> f.throwExceptionOnRejection(true))
                .channel("strict.validation.accepted")
                .get();
    }
}
~~~

When `isValid` returns false:

- The message **does not** go to `strict.validation.accepted`.
- The Filter throws a `MessageRejectedException`.
- With a synchronous `DirectChannel`, the exception can propagate back to the caller of `send()`.
- There is no `discardChannel` in this flow.
- The exception may be wrapped by endpoints/call stacks; inspect the cause chain in tests.

### 10.1. When Detailed Reasons Are Needed

`MessageRejectedException` expresses that the **Filter selector rejected**, yet it does not automatically carry `ValidationCode.INVOICE_ID_REQUIRED` or `AMOUNT_MUST_BE_POSITIVE`. If the API must return reason codes, use `requireValid` as an upstream Transformer/Service Activator and map `InvalidSubmissionException` into the proper response or error flow.

### 10.2. Do Not Throw for Every Business False

If a single Filter combines contract validation with `campaignEligible`:

~~~java
.filter(InvoiceSubmission.class,
        invoice -> validator.isValid(invoice)
                && invoice.campaignEligible(),
        f -> f.throwExceptionOnRejection(true))
~~~

then a valid invoice that simply does not participate in the campaign also raises `MessageRejectedException`, which is usually **semantically wrong**. Separate validation and eligibility filtering as in section 9.

## 11. Option C: Default Drop and `nullChannel`

When neither discard nor throw is configured, the Filter drops rejected messages:

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible)
~~~

Starting in Spring Integration **6.1**, a default drop (no discard channel and no throw) may be logged as a warning by `MessageFilter`. When intentionally discarding messages without warning logs, you can route rejected messages to the built-in `nullChannel`:

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible,
        f -> f.discardChannel("nullChannel"))
~~~

**Use only for messages allowed to be dropped by contract**, such as stale telemetry events or an inapplicable promotional branch. Never use `nullChannel` for financial commands, auditable data, or cases where producers expect feedback.

### 11.1. Silent Drop Is Not a Fallback

A dropped message does not automatically move to another subscriber on the input channel to "find a better handler". When multiple selective consumers share a point-to-point channel, the interaction between dispatcher and handler rejection must be designed and tested separately; `throwExceptionOnRejection` can affect dispatch strategy, but never abuse default drops to simulate a Router.

## 12. When Both Discard and Throw Are Configured: Double Side Effects

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant F as MessageFilter
    participant D as Discard handler
    participant E as Error handling

    P->>F: InvoiceSubmission
    F->>F: predicate=false
    F->>D: Send original message to discardChannel
    D-->>F: Discard branch handled
    F--xP: Throw MessageRejectedException
    P->>E: May retry/reject per transport
~~~

A discarded message may already have been logged, written to a DB, or published to a broker **before** the exception triggers a retry. If the discard handler has non-idempotent side effects:

~~~text
Attempt 1:
  discard -> sends rejection email
  exception -> broker retries

Attempt 2:
  discard -> sends rejection email a second time
  exception -> retries again
~~~

Only enable both when you genuinely want **audit/quarantine followed by failure**, with deduplication and retry classification properly designed. Even if the discard branch only writes logs/metrics, those can still be duplicated; metrics must clarify whether they count attempts or unique rejected messages.

### 12.1. `discardWithinAdvice`

Spring Integration supports `discardWithinAdvice` (defaulting to true) to decide whether discard/exception happens **inside or outside the Filter's advice chain**. With retry advice:

- Discarding inside advice can cause **the discard handler as well** to be retried upon failure.
- Throwing inside advice can cause retry advice to retry the rejection unless classified.
- `discardWithinAdvice(false)` alters the advice boundary, yet does not solve retry semantics by itself.

Test the exact topology whenever transaction advice, retry advice, Wire Taps, or discard-channel handlers are present. Never use this option to mask data errors.

## 13. XML and Annotations: Equivalent Semantics

### 13.1. XML Filter with Discard Channel

~~~xml
<int:filter
    id="campaignFilter"
    input-channel="campaignInput"
    output-channel="campaignAccepted"
    ref="eligibilitySelector"
    method="eligible"
    discard-channel="campaignRejected"/>
~~~

### 13.2. XML Filter with Exception

~~~xml
<int:filter
    id="strictValidationFilter"
    input-channel="strictInput"
    output-channel="strictAccepted"
    ref="validationSelector"
    method="isValid"
    throw-exception-on-rejection="true"/>
~~~

The XML snippets assume the `int` namespace is declared and the referenced beans and channels exist. They illustrate the corresponding policies rather than standalone runnable XML documents.

### 13.3. `@Filter` Annotation

~~~java
import org.springframework.integration.annotation.Filter;

public final class EligibilitySelector {

    @Filter(
        inputChannel = "campaignInput",
        outputChannel = "campaignAccepted",
        discardChannel = "campaignRejected")
    public boolean eligible(InvoiceSubmission invoice) {
        return invoice.campaignEligible();
    }
}
~~~

Annotation endpoints must be discovered/registered in the Spring context with valid channel names. Do not simultaneously declare both an annotation endpoint and a Java DSL endpoint **listening to the same input** when only a single consumer is intended.
## 14. Unit Tests: Validation and Expected Skips Are Two Different Things

Before testing channels, test `SubmissionValidator` in isolation. Tests must prove that **a valid invoice that is ineligible for the campaign still passes validation**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class SubmissionValidatorTest {

    private final SubmissionValidator validator =
            new SubmissionValidator();

    @Test
    void validButNotEligibleStillPassesValidation() {
        InvoiceSubmission input = new InvoiceSubmission(
                "REQ-1001", "tenant-a", "INV-1001",
                new BigDecimal("250000"), false);

        assertTrue(validator.isValid(input));
        assertFalse(input.campaignEligible());
        assertSame(input, validator.requireValid(input));
    }

    @Test
    void invalidReportsMultipleReasonCodes() {
        InvoiceSubmission input = new InvoiceSubmission(
                "REQ-1002", "tenant-a", "",
                new BigDecimal("-100"), true);

        assertEquals(
                List.of(
                    ValidationCode.INVOICE_ID_REQUIRED,
                    ValidationCode.AMOUNT_MUST_BE_POSITIVE),
                validator.validate(input));

        InvalidSubmissionException error = assertThrows(
                InvalidSubmissionException.class,
                () -> validator.requireValid(input));

        assertEquals(2, error.codes().size());
    }

    @Test
    void amountNullIsInvalidWithoutNullPointer() {
        InvoiceSubmission input = new InvoiceSubmission(
                "REQ-1003", "tenant-a", "INV-1003",
                null, false);

        assertEquals(
                List.of(ValidationCode.AMOUNT_REQUIRED),
                validator.validate(input));
    }
}
~~~

These unit tests do not prove Spring channel routing or broker ACKs. They only test the **data contract** and reason codes.

## 15. Integration Test: Pass, Discard, Validation Exception

`DiscardOnBusinessSkipConfig` in section 9 uses a `DirectChannel` at input and two `QueueChannel`s at output. The test below verifies all three cases against real endpoints.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = DiscardOnBusinessSkipConfig.class)
class CampaignDiscardFlowTest {

    @Autowired @Qualifier("campaign.discard.in")
    MessageChannel input;

    @Autowired @Qualifier("campaign.accepted")
    PollableChannel accepted;

    @Autowired @Qualifier("campaign.discarded")
    PollableChannel discarded;

    private InvoiceSubmission input(
            String id, boolean eligible) {

        return new InvoiceSubmission(
                "REQ-" + id, "tenant-a", id,
                new BigDecimal("250000"), eligible);
    }

    @Test
    void passesEligibleMessage() {
        InvoiceSubmission submitted = input("INV-2001", true);

        assertTrue(input.send(
                MessageBuilder.withPayload(submitted).build()));

        Message<?> message = accepted.receive(1000);
        assertNotNull(message);
        assertEquals(submitted, message.getPayload());
        assertNull(discarded.receive(0));
    }

    @Test
    void discardsValidButNotEligibleMessage() {
        InvoiceSubmission submitted = input("INV-2002", false);

        assertTrue(input.send(
                MessageBuilder.withPayload(submitted).build()));

        Message<?> message = discarded.receive(1000);
        assertNotNull(message);
        assertEquals(submitted, message.getPayload());
        assertNull(accepted.receive(0));
    }

    @Test
    void validationFailureThrowsBeforeFilter() {
        InvoiceSubmission invalid = new InvoiceSubmission(
                "REQ-2003", "tenant-a", "",
                new BigDecimal("-10"), false);

        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> input.send(
                    MessageBuilder.withPayload(invalid).build()));

        assertTrue(ErrorCauseChecks.contains(
                error, InvalidSubmissionException.class));
        assertNull(accepted.receive(0));
        assertNull(discarded.receive(0));
    }
}
~~~

Because the Spring messaging layer may wrap exceptions, inspect the cause chain rather than hardcoding a specific wrapper:

~~~java
public final class ErrorCauseChecks {

    private ErrorCauseChecks() {}

    public static boolean contains(
            Throwable thrown,
            Class<? extends Throwable> expected) {

        Throwable current = thrown;
        while (current != null) {
            if (expected.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
~~~

`ErrorCauseChecks` lives in its own test source file. To avoid shared queue contamination when tests reuse a cached context, drain outputs after each test or isolate contexts; do not mix with tests having incomplete groups/queues.

**What the test proves:** valid/eligible messages go to normal output; valid/not-eligible go to discard; invalid messages throw an exception **before** the business Filter. It does not prove broker ACK/NACK, as the example flow only uses local channels.

## 16. Integration Test: `throwExceptionOnRejection(true)`

Testing `ThrowOnInvalidConfig` from section 10:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.MessageRejectedException;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = ThrowOnInvalidConfig.class)
class StrictValidationFlowTest {

    @Autowired @Qualifier("strict.validation.in")
    MessageChannel input;

    @Autowired @Qualifier("strict.validation.accepted")
    PollableChannel accepted;

    @Test
    void invalidInputCausesMessageRejectedException() {
        InvoiceSubmission invalid = new InvoiceSubmission(
                "REQ-3001", "tenant-a", "",
                new BigDecimal("-100"), true);

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> input.send(
                    MessageBuilder.withPayload(invalid).build()));

        assertTrue(ErrorCauseChecks.contains(
                thrown, MessageRejectedException.class));
        assertNull(accepted.receive(0));
    }

    @Test
    void validButNotEligiblePassesStrictValidation() {
        InvoiceSubmission valid = new InvoiceSubmission(
                "REQ-3002", "tenant-a", "INV-3002",
                new BigDecimal("100"), false);

        assertTrue(input.send(
                MessageBuilder.withPayload(valid).build()));

        Message<?> result = accepted.receive(1000);
        assertNotNull(result);
        assertEquals(valid, result.getPayload());
    }
}
~~~

Note: `throwExceptionOnRejection` applies when the selector **returns false**. If the selector itself throws another exception, that is an error from the selector's code; do not assume `MessageRejectedException` is in the cause chain.

Do not test with `MessageBuilder.withPayload(null)`, as the builder rejects null before the message reaches the Filter. To test missing data, supply null/blank fields inside the DTO, or test decoding at the inbound adapter.

## 17. Integration Test: Discard and Still Throw

Enabling **both discard and throw** risks repeated side effects on retry. Sample flow:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class BothPoliciesConfig {

    @Bean(name = "both.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "both.accepted")
    public PollableChannel accepted() {
        return new QueueChannel();
    }

    @Bean(name = "both.discarded")
    public PollableChannel discarded() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow bothPoliciesFlow() {
        return IntegrationFlow.from("both.in")
                .filter(
                    InvoiceSubmission.class,
                    InvoiceSubmission::campaignEligible,
                    spec -> spec
                            .discardChannel("both.discarded")
                            .throwExceptionOnRejection(true))
                .channel("both.accepted")
                .get();
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.MessageRejectedException;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = BothPoliciesConfig.class)
class BothPoliciesFlowTest {

    @Autowired @Qualifier("both.in")
    MessageChannel input;

    @Autowired @Qualifier("both.discarded")
    PollableChannel discarded;

    @Autowired @Qualifier("both.accepted")
    PollableChannel accepted;

    @Test
    void rejectedMessageIsDiscardedAndExceptionStillThrown() {
        InvoiceSubmission excluded = new InvoiceSubmission(
                "REQ-4001", "tenant-a", "INV-4001",
                new BigDecimal("100"), false);

        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> input.send(
                    MessageBuilder.withPayload(excluded).build()));

        assertTrue(ErrorCauseChecks.contains(
                error, MessageRejectedException.class));

        Message<?> message = discarded.receive(1000);
        assertNotNull(message);
        assertEquals(excluded, message.getPayload());
        assertNull(accepted.receive(0));
    }
}
~~~

When the caller or broker retries because of the exception, the discard handler **may process the same message again**. If the discard branch inserts an audit row or sends a notification, use a stable idempotency key (`requestId` or scoped `eventId`), not `MessageHeaders.ID`, since redelivery may construct a new message instance.

## 18. Synchronous vs Asynchronous Exceptions

A Filter throws `MessageRejectedException`, yet where that exception is observed depends on the topology.

### 18.1. `DirectChannel`: Exception Can Return to Caller

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant D as DirectChannel
    participant F as MessageFilter
    C->>D: send(message)
    D->>F: handleMessage
    F--xC: MessageRejectedException
~~~

`DirectChannel` invokes handlers on the sender thread. Thus a synchronous caller can catch the exception. If the flow is exposed via HTTP/Gateway, mapping exceptions to status codes is the **adapter/gateway's responsibility**, not an automatic feature of the Filter.

### 18.2. `ExecutorChannel`/Poller: Async Error Handling Needed

~~~mermaid
sequenceDiagram
    participant C as Producer
    participant E as ExecutorChannel
    participant F as MessageFilter
    participant H as Error handler

    C->>E: send(message)
    E-->>C: Dispatched/accepted
    E->>F: handleMessage on worker thread
    F--xH: MessageRejectedException
    H->>H: ErrorMessage per configuration
~~~

If the handler runs on a task thread, the producer may already have returned and **cannot catch the exception on the original call stack**. A `MessagePublishingErrorHandler` or adapter error mechanism can send an `ErrorMessage` to the `errorChannel` header or the global `errorChannel`.

**Do not claim every synchronous exception automatically goes to `errorChannel`.** Explicitly identify the executor, poller, inbound adapter, and error handler in use.

### 18.3. `ErrorMessage` Payload Differs from Discard

~~~text
Filter predicate=false
  -> discardChannel:
     Message<InvoiceSubmission>

Async handler exception
  -> errorChannel (if routed):
     ErrorMessage<Throwable>
~~~

If a discard handler tries to cast to `ErrorMessage` or an error handler tries to cast the payload to `InvoiceSubmission`, secondary errors occur. Write each consumer according to its channel's contract.

## 19. Discard, Quarantine, DLQ, and Error Channel

| Mechanism | Typical contents | When to use |
|---|---|---|
| `discardChannel` | Original rejected `Message` | Expected business rejections |
| Application quarantine | Envelope with reason code/source/tracking | Data needing repair/investigation |
| Broker DLQ | Message undeliverable per broker policy | Retries exhausted or non-requeued reject |
| `errorChannel` | `ErrorMessage` with `Throwable` | Handler/poller/async exceptions |
| Audit stream | Outcome and safe metadata | Observability/compliance |

**A discard channel does not automatically become a DLQ.** Publishing to a broker requires separate outbound adapter, ACK/NACK, and retention configuration.

Example quarantine record:

~~~java
import java.time.Instant;
import java.util.List;

public record RejectedEnvelope(
        String requestId,
        String tenantId,
        List<ValidationCode> validationCodes,
        String source,
        Instant rejectedAt
) {}
~~~

This is an **application-constructed record**, not metadata auto-attached by the Filter. If storing raw payloads, apply encryption, masking, access control, and an appropriate TTL.

### 19.1. Discard Reasons Are Not Automatic

When a predicate returns false, Spring Integration does not turn it into `ValidationCode.INVOICE_ID_REQUIRED`. To preserve reasons:

1. Run a pure classifier/validator to compute codes before the Filter.
2. Put safe codes into an application outcome/envelope.
3. Or throw a typed exception carrying the list of codes.
4. Never use raw exception text containing PII as a taxonomy.
5. Never re-call an unstable API in the discard branch just to "guess the reason".

### 19.2. Non-Retryable vs Transient

A payload missing `invoiceId` is a **deterministic** failure; retrying the exact payload repeatedly is futile. A database timeout or network glitch is **transient** and may succeed after backoff. Both can throw exceptions, yet retry/quarantine paths must be **classified**.
## 20. Retry, ACK, and Poison Messages

### 20.1. Successful Discard Can Count as a Completed Attempt

When a Filter returns false, sends the message to `discardChannel`, and **throws no exception**, many inbound adapters treat the handler invocation as finished and ACK per configuration. However, this is **adapter/transaction-dependent behavior**, not a universal guarantee of `discardChannel`.

Verify in practice:

- Is the consumer auto-ack or manual-ack?
- Does ACK happen before or after the discard branch finishes?
- Does the discard branch run in its own transaction?
- Are outbound broker messages durably persisted before ACK?
- If the discard handler fails, does the exception propagate back to the listener?
- When reprocessing from quarantine, is the idempotency key stable?

Even `MessageChannel.send()` returning true does not by itself prove business side effects committed.

### 20.2. Exceptions Can Cause Message Redelivery

With a broker adapter, an exception may trigger rollback/NACK/requeue per configuration. If the input is permanently invalid:

~~~text
Malformed message
  -> throwExceptionOnRejection(true)
  -> redelivery
  -> same validation failure
  -> endless redelivery
~~~

This is a **poison message loop**. Solutions:

1. Mark deterministic validation errors as **non-retryable**.
2. Move to quarantine or DLQ per broker contract.
3. Avoid infinite requeuing; use max attempts/backoff for transient errors.
4. Reprocess only once data is fixed or the contract changes.
5. Record event source, stable event ID, and reason codes for diagnosis.

### 20.3. DB Timeout Is Not Filter False

Anti-pattern example:

~~~java
// Anti-pattern: DB outage becomes "not eligible".
try {
    return invoiceRepository.existsById(invoiceId);
}
catch (RuntimeException ignored) {
    return false;
}
~~~

When the DB does not respond, you cannot conclude the invoice definitely does not exist. Returning false and dropping could **permanently lose** a valid message. Separate infrastructure exceptions from business ineligibility.

### 20.4. Do Not Infinitely Retry Data Errors via Default Advice

If a Filter has retry advice while `throwExceptionOnRejection(true)`, returning false for invalid data may get retried **even though the message has not changed**. Configure a classifier/non-retryable exception list or push validation to the adapter boundary ahead of retrying handlers, with tracked error outcomes.

## 21. Gateway, Request-Reply, and Silent Drop

A Gateway typically expects a reply. When a Filter default-drops a request, downstream handlers never run and may never send a reply:

~~~text
Gateway request
   -> Filter returns false
   -> drop
   -> Gateway waits
   -> reply timeout
~~~

If the caller needs to know why an invoice was not accepted:

- Return a typed validation error or a `RejectedOutcome` with a reason.
- For expected skips, return `SKIPPED` per the API contract.
- For security denials, return a limited-detail response per security policy.
- For DB/network failures, return a temporary error or appropriate async tracking state.
- Never expect `nullChannel` to produce an HTTP 400/422 automatically.

### 21.1. Example Reply DTO

~~~java
public enum SubmissionStatus {
    ACCEPTED,
    SKIPPED,
    INVALID
}

public record SubmissionReply(
        String requestId,
        SubmissionStatus status,
        String reasonCode
) {}
~~~

This is a **business model**, not the default output of `MessageFilter`. You need an explicit endpoint/route to construct and send `SubmissionReply` to the Gateway's `replyChannel` or HTTP adapter.

### 21.2. HTTP Status Is Decided by the Adapter

A `MessageRejectedException` in Spring Integration **does not automatically mean HTTP 400**. The application must map: invalid contract → 400/422 per API, authorization denial → 403 per security layer, transient errors → 5xx or async retry response. Choose consistent response semantics so clients do not endlessly retry unrecoverable errors.

## 22. A Filter After Splitter Can Stall an Aggregator

A Splitter emits four messages with sequence metadata:

~~~text
part #1: sequenceNumber=1, sequenceSize=4
part #2: sequenceNumber=2, sequenceSize=4
part #3: sequenceNumber=3, sequenceSize=4
part #4: sequenceNumber=4, sequenceSize=4
~~~

If a Filter drops part #2 while leaving `sequenceSize=4` on the other parts:

~~~text
Aggregator receives: #1, #3, #4
Missing:             #2
Expected:            4
~~~

A release strategy waiting for all parts can **wait forever or until expiry**. The Filter "did its job" per its predicate, yet the overall flow cannot finish.

Solutions:

1. **Filter the collection before Splitter** so Splitter knows the exact post-filter part count.
2. Emit a **skipped marker** at position #2 if downstream has a contract for skipped parts.
3. Use a custom release strategy aware that parts may be intentionally omitted.
4. If one invalid part invalidates the entire batch, reject/reconcile the whole group.
5. Configure timeouts/expiry and incomplete group policies.
6. Preserve correlation ID/sequence headers and track rejected part counts.

### 22.1. Resequencer Is Also Affected

If a Resequencer receives 1, 3, and 4 without 2, it may hold subsequent parts due to the gap. Choosing discard or exception in a Filter **before** a Resequencer affects not only that message, but also the ordering and latency of the entire sequence.

### 22.2. Do Not Use Sequence Metadata as a Validation Key

`sequenceNumber` and `sequenceSize` are sequence metadata, not replacements for business identity or content validation. If parts are dropped by a Filter without updating sequence size, do not randomly rewrite the size on remaining messages; establish an explicit protocol across Splitter, Filter, and Resequencer/Aggregator.

## 23. Security: Do Not Mask Authorization Failures as Discards

If a message declares a `tenantId` belonging to another tenant or carries an invalid token, it is not merely "ineligible for the campaign".

- Authenticate the source before trusting headers/payloads.
- Authorize resource access before business side effects.
- Never leak another tenant's data in error messages or discard queues.
- Audit security denials.
- Never catch authorization errors and return false just to avoid throwing exceptions.
- Never let untrusted input dictate internal channel names.
- Never send raw payloads to unprotected logs or quarantines.

**Security checks must reside at the proper trust boundary**, not in a Filter buried deep in the flow after data has already passed multiple endpoints.

## 24. Observability: Measure Outcomes by True Meaning

| Metric | Contents | Appropriate labels |
|---|---|---|
| `filter_received_total` | Incoming messages | flow/source |
| `filter_accepted_total` | Passed messages | flow |
| `filter_discarded_total` | Expected business skips | reason/category |
| `filter_invalid_total` | Contract violations | validation code |
| `filter_exception_total` | Rejection exceptions | error class |
| `filter_retry_total` | Retry attempts | flow/reason |
| `filter_quarantine_total` | Quarantined messages | source/reason |
| `filter_dlq_total` | Messages sent to DLQ | flow/reason |
| `filter_async_error_total` | `ErrorMessage`s from async tasks | error class |
| `filter_gateway_timeout_total` | Gateways missing replies | flow |

A structured log:

~~~text
flow=invoice-campaign
requestId=REQ-1001
outcome=DISCARDED_EXPECTED
reasonCode=NOT_ELIGIBLE
source=invoice-submission
traceId=trace-1001
~~~

Never use invoice IDs, request IDs, trace IDs, or customer IDs as **high-cardinality metric labels**. Use access-controlled, retention-bounded logs/traces when tracing a specific request.

### 24.1. Distinguish Valid Skips from Producer Bugs

If a campaign only accepts 5% of invoices, 95% `filter(false)` is normal—do not fire 95% error alerts. Conversely, if blank `invoiceId` errors are treated as "expected discards", producers could send broken data for days unnoticed.

At a minimum, separate:

~~~text
ACCEPTED
DISCARDED_EXPECTED
REJECTED_INVALID
FAILED_RETRYABLE
~~~

For remote actions where execution state is unclear, consider an `UNKNOWN`/reconciliation state rather than using discard as a fake outcome.

### 24.2. Durable Auditability

Warning logs on default drops in Spring Integration 6.1+ do not replace a **durable audit record**. If policy requires proof of why a message was rejected, persist an event/record with reason codes and identity; test rollback/ACK if auditing must be transactional.

## 25. Common Anti-Patterns

| Mistake | Consequence | Solution |
|---|---|---|
| Treating every Filter false as an error | Business skips trigger unnecessary retries/alerts | Separate validation and eligibility |
| Default-dropping invalid data | Messages lost with no feedback | Typed error/quarantine |
| Assuming Filter false throws by default | No exception raised | `throwExceptionOnRejection(true)` |
| Assuming discard receives `ErrorMessage` | Wrong payload cast | Discard receives original message |
| Assuming `throwExceptionOnRejection` wraps all errors | Selector's own exceptions go unclassified | Inspect cause chain |
| Enabling discard + throw unintentionally | Discard side effect followed by retry | Define explicit outcome/idempotency |
| Using `nullChannel` for financial commands | Lost work | Only drop disposable messages |
| Catching DB exceptions and returning false | Masks transient failures | Throw + bounded retry |
| Retrying invalid broker messages forever | Poison loop | Non-retryable/DLQ |
| Assuming discard = automatic DLQ | No broker policy | Configure outbound/adapter |
| Silent drop inside a Gateway | Timeout instead of response | Explicit reply/error |
| Filtering parts after Splitter | Aggregator/Resequencer missing parts | Pre-filter/marker/release |
| Not checking retry advice with `discardWithinAdvice` | Discard side effects retried | Test advice boundary |
| Quarantine storing sensitive payloads | Data leakage | Masking/retention/access control |
| Not testing sync vs async exceptions | Wrong error-path expectations | Topology-accurate integration tests |
| Using warning logs as audit | Missing durable proof | Audit/outcome record |
| Counting duplicate attempts as unique rejects | Skewed metrics | Stable idempotency key |

## 26. Practice Exercises

**Exercise 1 — Classification:** Given an ineligible invoice, blank `invoiceId`, negative amount, DB timeout, unauthorized tenant, and already-processed event, choose discard/exception/quarantine/retry with explanations.

**Exercise 2 — Unit validator:** Run `SubmissionValidatorTest`; verify that a valid-but-ineligible invoice still passes validation.

**Exercise 3 — Discard flow:** Send two valid invoices (eligible/not eligible) into `DiscardOnBusinessSkipConfig` and inspect the accepted/discarded channels.

**Exercise 4 — Invalid before Filter:** Send blank `invoiceId` and negative amount into the flow above; assert the exception and that both output channels remain empty.

**Exercise 5 — Throw filter:** Send invalid input into `ThrowOnInvalidConfig`; assert the cause chain contains `MessageRejectedException`.

**Exercise 6 — Both policies:** Enable discard and throw together; assert discard receives the original message even though the caller still receives an exception.

**Exercise 7 — Duplicate discard side effect:** Replace `QueueChannel` with an audit handler, simulate a retry, then add idempotency.

**Exercise 8 — Async error:** Use an `ExecutorChannel` or poller with an error handler; test `ErrorMessage` instead of catching exceptions directly from `send()`.

**Exercise 9 — Poison message:** Redeliver an invalid event via a broker, configure max attempts/non-retryable policy and DLQ.

**Exercise 10 — Gateway:** Compare silent drop causing reply timeout against explicit invalid reply/error mapping.

**Exercise 11 — Aggregator gap:** Split four parts then discard part 2; observe release behavior, then design a pre-filter or skipped marker.

**Exercise 12 — Headers:** Verify appropriate correlation/trace headers survive on accepted/discarded routes while security secrets are not leaked outward.

**Exercise 13 — Quarantine:** Create `RejectedEnvelope` and define reason codes, retention, encryption, and access controls.

**Exercise 14 — Observability:** Add metrics for accepted, expected discard, validation fail, and retryable error using labels free of personal IDs.

**Exercise 15 — Reprocessing:** Pull a message from quarantine after fixing data; use a stable business key to prevent duplicate side effects.

### Self-Check Questions

1. What do Filter returning true and false mean?
2. Why is Filter false not always a validation failure?
3. When neither discard nor throw is configured, where does a rejected message go?
4. What might Spring Integration 6.1+ log on a default drop?
5. Does `discardChannel` typically receive the original message or an `ErrorMessage`?
6. What exception type does `throwExceptionOnRejection(true)` produce?
7. If the selector throws `IllegalArgumentException`, is that a `MessageRejectedException`?
8. What happens if both discard and throw are enabled?
9. Why does a discard branch with side effects need idempotency on retry?
10. Why is `nullChannel` unsuitable for financial data?
11. How does structural validity differ from business eligibility?
12. When are validation reason codes needed instead of a boolean?
13. On a `DirectChannel`, where do exceptions go?
14. On an `ExecutorChannel`, can the caller always catch the error?
15. Do `errorChannel` and `discardChannel` share the same payload contract?
16. Should a DB timeout be treated as Filter false?
17. Why can a malformed event trigger a poison retry loop?
18. Is discard synonymous with broker ACK?
19. Why can a Filter after Splitter stall an Aggregator?
20. What happens to a Gateway waiting for a reply when a Filter silently drops?
21. Can a security denial be discarded like a non-eligible item?
22. How do you structure metrics so expected skips are not mistaken for errors?
23. How can `discardWithinAdvice` affect retry scope?
24. Which test proves discard and throw occur together?

## 27. Implementation Checklist

- [ ] Classified **invalid**, **not eligible**, **transient failure**, and **security denial**.
- [ ] Validation runs before critical business side effects.
- [ ] Filter checks eligibility on already-validated payloads.
- [ ] Understood `MessageFilter` default drop and 6.1+ warning behavior.
- [ ] `discardChannel` configured when an expected reject branch is needed.
- [ ] `throwExceptionOnRejection` enabled only when rejection truly requires an error.
- [ ] Did not enable discard + throw simultaneously without accounting for retries/idempotency.
- [ ] Stable reason codes exist for invalid data.
- [ ] Validation exceptions are separated from infrastructure exceptions.
- [ ] Non-retryable errors are not requeued infinitely.
- [ ] Transient failures have bounded retries/backoff and DLQ policies.
- [ ] Discard consumer expects original messages; error consumer expects `ErrorMessage`.
- [ ] Sync/async error paths tested against real topologies.
- [ ] `nullChannel` is never used for business operations that cannot be lost.
- [ ] Gateways/APIs have explicit replies or error mappings on rejection.
- [ ] Filters after Splitter do not break release/sequence contracts.
- [ ] Correlation and trace headers preserved or stripped appropriately at trust boundaries.
- [ ] Quarantine enforces retention, masking, encryption, auditing, and access control.
- [ ] ACK/NACK behavior verified with the actual inbound adapter.
- [ ] Unit and integration tests cover pass/discard/throw.
- [ ] Tests cover both discard and throw together, plus retried side effects.
- [ ] Metrics separate accepted, expected discard, invalid, and retryable outcomes.
- [ ] No PII or high-cardinality IDs in metric labels.
- [ ] Reprocessing from quarantine uses a stable idempotency identity.

## 28. Summary

**Discard vs exception on validation failure** is a **semantic** choice for the message flow, not merely a flag. If a message is **valid yet belongs outside this branch**, intentional discard is a normal business outcome. If a message **violates the contract**, it needs an error response or quarantine with reason codes. If an infrastructure failure occurs, raise an exception and apply controlled retry—never disguise it as Filter false.

In Spring Integration, when a selector returns false, a Filter **drops** by default. `discardChannel` routes the **original rejected message** to a separate branch, while `throwExceptionOnRejection(true)` throws `MessageRejectedException`. Enabling both sends the message to the discard branch **and still throws an exception**, risking duplicate side effects when callers retry. Synchronous `DirectChannel` exceptions usually propagate back to callers; async flows require understanding `ErrorMessage` and error handlers.

In **SPRING_INTEGRATION_PATTERN**, separating validation from business-rule Filters, aligning retries/ACKs with failure categories, preserving correlation, testing Gateways/Aggregators, and observing true outcomes ensure integration systems **never lose tasks due to silently ignored data errors**.

### References

- Spring Integration Reference — Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration API — MessageFilter: https://docs.spring.io/spring-integration/api/org/springframework/integration/filter/MessageFilter.html
- Spring Integration API — FilterEndpointSpec: https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/FilterEndpointSpec.html
- Spring Integration API — MessageRejectedException: https://docs.spring.io/spring-integration/api/org/springframework/integration/MessageRejectedException.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Handler Advice: https://docs.spring.io/spring-integration/reference/handler-advice.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
