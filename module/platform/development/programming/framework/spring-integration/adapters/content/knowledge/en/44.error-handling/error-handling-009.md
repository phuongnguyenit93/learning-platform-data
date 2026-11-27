# NullChannel for Intentional Error Discarding in Spring Integration Adapters

> **Chapter:** Error handling  
> **Direct Topic:** NullChannel for intentional error discarding  
> **Module Scope:** Connecting external systems to **Spring Integration** via inbound/outbound adapters, gateways, pollers, and `MessageChannel`. Content connects File, SFTP, HTTP, JMS, AMQP, Kafka, and database flows; focusing on message contracts, errors, processing acknowledgments, durability, and connection lifecycles.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the nature of **NullChannel** as a **black hole** `MessageChannel` that accepts messages and intentionally discards their contents, distinct from error stores and retry engines.
2. Distinguish **discard message**, **ignore expected condition**, **swallow exception**, **acknowledge message**, **dead-letter**, and **recover business operation**.
3. Identify when an **ErrorMessage** may be sent to `nullChannel` after **intentional error classification**, instead of swallowing all errors.
4. Configure routes to **`nullChannel`** from an `IntegrationFlow`, **`Filter.discardChannel`**, or a controlled error-handling flow.
5. Understand the difference between **synchronous** and **asynchronous** error paths across `DirectChannel`, `ExecutorChannel`, `QueueChannel`, pollers, and containers.
6. Evaluate interactions with **`errorChannel` header, global `errorChannel`, `ErrorMessage`, `errorChannel` resolver, gateways, `RequestHandlerRetryAdvice`**, and recovery.
7. Design safe policies for File/SFTP, HTTP, JMS, AMQP, Kafka, and JDBC: **which errors may be discarded, which require DLQ/retry/rollback**.
8. Enforce **observability, auditing, idempotency, reason codes, ownership, measurement, and negative testing** before discarding messages.
9. Write decision matrices and tests proving **intentional, accurate discarding** without creating **silent data loss** or turning serious errors into "false success".

## 2. Problem Statement: Not Every Error Needs an Alert, Yet Not Every Error May Be Discarded

A system receiving files from SFTP, processing invoices, and sending results to an HTTP ERP can encounter:

- **Valid duplicate records**: the same business event was already processed successfully, so receiving it again needs no side effects.
- **Unrelated auxiliary files**: a partner drops a README or marker file in the same directory when the contract only processes `*.ready`.
- **A branch needing no reply**: a handler emits status info while the caller needs no response.
- **HTTP 503**: the ERP is temporarily down; must retry or save a job.
- **Schema-invalid payload**: needs quarantine and notification to fix data.
- **JMS consumer DB error**: needs rollback/redelivery or durable error storage.
- **Unprocessable Kafka record**: needs DLT/parking or an explicit policy—never silently drop and commit offset.
- **SFTP upload succeeded yet response lost**: outcome unknown; requires reconciliation, never auto-"ignore".

Some messages **should be discarded because they satisfy business contracts**. Yet dumping all errors into a black-hole channel just to keep dashboards "green" can make data vanish irrecoverably.

### The Most Important Question

> "Which verified condition proves **no further business action is needed**, and if we discard this message right now, will we lose the ability to reconcile or recover?"

**NullChannel can be a valid terminal point for a classified branch**, not a blanket answer for all errors.

## 3. What Is NullChannel?

In Spring Integration, **NullChannel** is a `MessageChannel` implementation that accepts a message and **discards the message** rather than passing it to a subscriber for business processing. It is commonly called a **black-hole channel**.

Spring Integration provides a standard channel named **nullChannel** for endpoints/flows configured appropriately. That name denotes a **message disposal sink**, not Java's **`null`** and not a channel returning a null value as a business response.

### Three Assertions to Remember

1. **A message sent to NullChannel ends that processing branch.** No downstream consumer receives the message to execute business work.
2. **NullChannel is not a DLQ, message store, retry scheduler, or error forwarding mechanism.** Never assume discarded messages can be replayed.
3. **A successful send to NullChannel does not prove business success.** It only proves the channel accepted the message for disposal per channel semantics.

### Comparison with Easily Confused Components

| Component | Behavior | Durable? | When to Use |
|---|---|---|---|
| **NullChannel** | Accepts and drops messages | No | Branch proven safe to discard |
| **DirectChannel** | Dispatches synchronously to handler | Not by default | Direct processing / error propagation needed |
| **ExecutorChannel** | Dispatches via executor | Not by default | Asynchronous processing boundary |
| **QueueChannel** | Buffers messages awaiting receipt | Depends on `MessageStore` | Decoupling producer/consumer |
| **PublishSubscribeChannel** | Broadcasts to multiple subscribers | Not by default | Fan-out; usable as error channel |
| **errorChannel** | Routes `ErrorMessage` per config | Not by default | Observing/coordinating errors |
| **DLQ/DLT/parking** | Retains failed messages with cause | Yes when target store is durable | Investigation, manual fixes, redrive |
| **Filter discard** | Drops messages failing predicate; may route to `discardChannel` | Depends on target | Dropping noise / out-of-scope records |

**A channel named `errorChannel` is not automatically durable error storage.** Conversely, `NullChannel` never intends to retain any message.

### Does NullChannel Log Errors?

When a message is an **`ErrorMessage`**, detailed logging behavior of `NullChannel` can depend on Spring Integration version and logging configuration. Never claim "every ErrorMessage vanishes without a trace", yet **never rely on default logging as a durable audit trail either**. When counting, recording reasons, and auditing are required, perform them **before sending to `nullChannel`** through a tested observability mechanism.

## 4. NullChannel Does Not "Fix Errors"

Distinguish three actions:

1. **Discard:** perform no downstream processing for that message.
2. **Recover:** execute compensation, a valid fallback, or persist the message where processing can resume.
3. **Retry:** re-execute the operation when the error can recover.

`NullChannel` only directly performs **discard**. If the system sends an **`ErrorMessage`** to `nullChannel`, that error message flow ends. This **does not roll back an earlier transaction**, **does not undo side effects already created**, and **does not automatically control broker acks**.

### A Common Mistake

~~~text
SFTP inbound -> HTTP POST create order
                      |
                      +-- response timeout
                             |
                             v
                         errorChannel
                             |
                             v
                         nullChannel

Observation:
    No more alerts.

Reality may be:
    HTTP POST failed -> lost order.
    Or POST succeeded -> outcome unknown.
    Or source already acked -> no message left to replay.
~~~

The configuration above is valid only when a **prior contract** defines that this timeout can truly be discarded and proof of preservation or business handling exists. Normally an order creation timeout **does not qualify**.

## 5. Four States to Separate Clearly Before Discarding Errors

| State | Meaning | Safe to Send to NullChannel? |
|---|---|---|
| **EXPECTED_IGNORE** | A message requiring no processing per contract, e.g., out-of-scope file type | Yes if classification is verified, with audit if required |
| **ALREADY_PROCESSED** | Duplicate business event verified as completely processed | Yes after valid dedupe/reconciliation |
| **RECOVERED_BY_POLICY** | Fallback/compensation or durable storage completed per contract | Can discard **secondary error notice** once consequences are handled |
| **UNRESOLVED/UNKNOWN** | Outcome unclear or pending work remains | **No**; requires retry, rollback, parking, or investigation |

A logged error is **not necessarily** `RECOVERED_BY_POLICY`. An error flow receiving a message **does not mean** the original work is safe.

### Pre-Define a "Discard Decision"

A discard decision can record:

- Stable business event ID or correlation ID.
- Source/adapter/endpoint.
- Error category or message type.
- Approved **reason code**.
- Evidence that it was processed / needs no processing.
- Classification timestamp.
- Rule/policy version.
- Owner and audit retention period.
- Terminal branch `DISCARDED_EXPECTED`.

Never place tokens, passwords, private keys, or full customer payloads into audit records merely to prove a valid discard.

## 6. Error-Handling Architecture: Classify First, NullChannel Last

~~~mermaid
flowchart TD
    S["Inbound adapter / gateway / poller"] --> H["Message handler / Integration Flow"]
    H -->|"Success"| OK["Business outcome"]
    H -->|"Exception"| E["ErrorMessage / error boundary"]
    E --> C["Classification + correlation + business-state check"]
    C --> Q{"Verified state?"}
    Q -->|"EXPECTED_IGNORE"| M["Metric + audit reason"]
    Q -->|"ALREADY_PROCESSED"| M
    Q -->|"RECOVERED_BY_POLICY"| M
    M --> N["nullChannel: drop concluded notice"]
    Q -->|"TRANSIENT_RETRYABLE"| R["Bounded retry / delayed retry"]
    Q -->|"PERMANENT_INVALID"| D["Quarantine / DLQ"]
    Q -->|"OUTCOME_UNKNOWN"| P["Reconcile / PARKED"]
    Q -->|"SECURITY / UNCLASSIFIED"| X["Alert + owner investigation"]
    R --> B["Durable state / source protocol"]
    D --> B
    P --> B
    X --> B
~~~

**Never wire the entire `errorChannel` straight to `nullChannel`** without a classifier and safety checks. Every terminal branch needs clear criteria for source ack/commit or request completion.

### Message Streams

- **Business messages:** primary payload, business side effects.
- **ErrorMessages:** payload representing exceptions and error metadata.
- **Audit events:** proof of classification and outcome, not necessarily holding full source data.
- **Recovery records:** payload or reference sufficient to retry, investigate, and replay.

Do not use `ErrorMessage` as a permanent store for original messages; it can contain sensitive exceptions and is not designed as durable storage.

## 7. Synchronous vs. Asynchronous Errors Differ

Spring Integration has **synchronous** and **asynchronous** execution paths. This decides whether an exception travels straight to the caller or turns into an `ErrorMessage` on a channel.

### DirectChannel

**DirectChannel** normally dispatches to handlers synchronously on the sender's thread. If a handler throws and no catch/error-handling mechanism sits at the right layer, the exception can **bubble back to the caller**.

Merely having a channel named `nullChannel` somewhere in the context **does not catch all synchronous exceptions**. There must be an explicit point catching/converting exceptions into `ErrorMessage` or a configured error flow.

### ExecutorChannel

**ExecutorChannel** creates an asynchronous boundary via an executor. Error propagation can pass through an **error channel** per framework context instead of returning to the initial caller.

If `ErrorMessage` routes to `NullChannel`, never assume the original request has durable retries or proper acks: inspect the source, transaction, and error handler.

### QueueChannel/Poller

A poller fetches messages via `QueueChannel` or `MessageSource` and runs handlers. Once a message is removed/claimed from the source, discarding the error does not automatically return the message to the queue. Verify transactions/rollbacks, `MessageStore`, and poller error handling.

### Request–Reply Gateways

A gateway may expect a **reply** or **error reply**. Pushing both results and errors into `nullChannel` can make the caller wait until **reply timeout** and fail differently. Never use `NullChannel` to evade returning a valid response.

| Boundary | On Error | Question About NullChannel |
|---|---|---|
| Synchronous `DirectChannel` | Can propagate exception | Does any flow actually catch and emit `ErrorMessage`? |
| Asynchronous `ExecutorChannel` | `ErrorMessage` may travel error path | Was the source acked/persisted? |
| `PollingConsumer` | Polling/error flow per config | Can the same message be polled again? |
| Request–reply gateway | Caller needs reply/error | If reply is dropped, will caller time out? |
| Broker listener | Container decides ack/nack/rollback | Does normal return from error flow trigger ack? |

## 8. `errorChannel` vs. `nullChannel`: Two Channels with Opposite Purposes

**`errorChannel`** transports `ErrorMessage`; **`nullChannel`** is a disposal sink. Both are familiar Spring Integration names, yet only one is meant to help you process errors.

Some Spring Integration setups provide a **global `errorChannel`** where async components send `ErrorMessage`s when no specific destination exists. It may have a logging handler by default. However:

- Not every exception enters global `errorChannel` automatically.
- Error channels can be specified via headers or endpoint config.
- An error channel has concrete subscribers and channel types, not necessarily durable storage.
- Global `errorChannel` is not a DLQ on its own.
- Pointing it to `nullChannel` can **blind system-wide error visibility**.
- Verify error channel precedence/resolution for your topology and version.

### The `errorChannel` Header

A message can carry a header specifying the error channel when the component/framework supports that path. The header can reference a channel in a supported format.

**Never misinterpret:** setting the `errorChannel` header to `nullChannel` does not automatically drop all Java exceptions in the flow. Behavior depends on the `ErrorMessage` publisher, sync/async flow, and whether the error channel is actually consulted.

### When Discarding Replies Is Valid

In some **one-way** flows, return results need no handling. `nullChannel` can serve as the sink for unneeded **reply messages**. That is **discarding a reply**, distinct from **discarding an `ErrorMessage`**. Never do this for gateways where callers expect return data.

## 9. Filter `discardChannel` Differs from Discarding Errors

A **Filter** in Spring Integration decides whether a message continues downstream. Messages failing the predicate can be dropped or routed to **`discardChannel`**.

Example where files are accepted only when matching the `.ready` contract suffix, while auxiliary files go to `NullChannel`:

~~~java
import java.io.File;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
class FileSelectionFlow {

    @Bean
    IntegrationFlow candidateFileFlow() {
        return IntegrationFlow.from("candidateFileChannel")
            .filter(File.class,
                file -> file.getName().endsWith(".ready"),
                endpoint -> endpoint.discardChannel("nullChannel"))
            .channel("acceptedFileChannel")
            .get();
    }
}
~~~

The condition in the example must match the **source contract**. Valid files using another extension must not vanish silently due to a buggy predicate. Unit-test **both accepted and rejected file sets**, plus metrics for discarded counts.

### Is This Exception Handling?

**No.** Filters drop messages **by data/contract**, not because an exception was thrown. If a developer catches a parser exception and turns it into `false` from a predicate to push broken files into `nullChannel`, data errors get hidden. Keep a dedicated `INVALID`/quarantine branch.

### Errors When the Filter Itself Throws

If a predicate throws a `RuntimeException`, that is an execution error requiring the corresponding error-handling path; **`discardChannel` does not automatically handle predicate exceptions**. It is for messages **rejected by filter evaluation**.

## 10. Controlled Routing of Messages to `nullChannel`

Another use case is classifying messages that need no processing per valid rules before forwarding.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
class ClassifiedMessageFlow {

    @Bean
    IntegrationFlow classifiedFlow() {
        return IntegrationFlow.from("classifiedInput")
            .route(
                String.class,
                payload -> payload.startsWith("INFO:") ?
                        "IGNORE" : "PROCESS",
                router -> router
                    .channelMapping("IGNORE", "ignoredAuditChannel")
                    .channelMapping("PROCESS", "businessChannel")
            )
            .get();
    }

    @Bean
    IntegrationFlow ignoredFlow() {
        return IntegrationFlow.from("ignoredAuditChannel")
            .handle((payload, headers) -> {
                // Record counters and audit with reason code before discarding.
                // Placeholder here; real instrumentation must be wired.
                return payload;
            })
            .channel("nullChannel")
            .get();
    }
}
~~~

Here, the audit handler **returns the payload** so the message continues to `NullChannel`. If the audit handler throws, never treat an audit failure as a successful discard when auditing is mandatory. Policy must define sync/durable auditing and failure behavior.

**The example uses a simple `String` payload to illustrate routing**, not as a complete solution for classifying `ErrorMessage`s. For errors, inspect exception type, source, operation, business state, and metadata instead of relying on string prefixes.

## 11. Classifying ErrorMessage: Which Error Types May Be Discarded?

An `ErrorMessage` represents an error during message processing. Its payload holds a `Throwable`; metadata may supply `failedMessage` and correlation depending on how the framework built the error.

**Never write a classifier based solely on exception class.** For instance, the same `IOException` could be a transient disconnect needing retry, or a completed operation whose response was lost requiring reconciliation.

### Decision Matrix

| Classification | Facts to Verify | Appropriate Action |
|---|---|---|
| Processed duplicate | Stable event ID has complete result, checksum/version match | Audit + `NullChannel` for duplicate message |
| Optional auxiliary notice | Contract permits ignoring, no mandatory side effects | Audit + `NullChannel` |
| Valid business no-op | Rule confirms action no longer needed, e.g., event older than committed version | Audit + `NullChannel` if consistent |
| HTTP 503 | Retryable, deadline/budget remaining | Short retry or durable retry |
| HTTP POST timeout | Outcome unknown | Remote query/idempotency/reconcile |
| Invalid JSON/schema | Unprocessable data | Quarantine/repair |
| Authentication failure | Expired/wrong credentials | Alert and fix config, do not discard |
| Authorization failure | Rejected role/scope | Security/owner triage |
| Incomplete SFTP transfer | Partial file or dropped session | Staging/transfer recovery |
| Broker ack/offset error | Message state unclear | Reconcile container/source |
| DB deadlock | Recoverable transaction failure | Retry fresh transaction properly |
| DLQ write failure | Message not preserved | Propagate/fail, no `NullChannel` |
| Unclassified exception | Insufficient evidence | Alert/parking, no `NullChannel` |

**Safe default:** unsure whether safe to discard → **do not discard**. Exceptions require clear rules, owners, and review deadlines.

## 12. Auditing Before NullChannel

Because the message will be discarded, reconciliation evidence must be created **beforehand**. You can design a minimal structure:

~~~json
{
  "eventId": "partner-X:order-312:v2",
  "correlationId": "corr-7001",
  "source": "sftp-inbound",
  "flowId": "order-import",
  "endpointId": "dedupe-filter",
  "decision": "DISCARD_EXPECTED",
  "reasonCode": "ALREADY_PROCESSED",
  "policyVersion": "dedupe-rules-7",
  "evidenceRef": "inbox/order-312-v2",
  "decidedAt": "2026-11-23T09:00:00Z",
  "owner": "integration-operations"
}
~~~

This is an illustrative schema, not a default `NullChannel` format.

**Principle:** if the business requires durable audits proving why a message was discarded, a single console log or metric counter is insufficient. You need an appropriate audit store, access controls, retention, correlation, and reconciliation with succeeded records.

### Do Not Conflate Measurement Units

- **discarded message count:** messages disposed of.
- **business events ignored:** business events confirmed as no-op or duplicate.
- **exception count:** times handlers threw exceptions.
- **source redelivery count:** times sources redelivered.

One business event can generate multiple `ErrorMessage`s or retries. **Do not count every error retry as a discarded business event**.

## 13. Never Turn Unknown Errors into "Ignored"

An exception can take four forms:

- **Transient:** recoverable via retry.
- **Permanent:** incompatible data/permissions/config.
- **Unknown outcome:** unclear if remote processed it.
- **Expected benign:** business confirms no further action needed.

Only the last form—or **an error already recovered with proof**—is a candidate for discarding `ErrorMessage`. If a classifier asks only "could this error go away by itself?" without checking business effects, it will misclassify.

### Example: Timeout After HTTP POST

~~~text
10:00:00  POST /orders
10:00:01  ERP creates order successfully
10:00:02  Response lost
10:00:03  Spring Integration receives timeout
10:00:03  ErrorMessage generated at error boundary
~~~

If `ErrorMessage` goes straight to `NullChannel`, the app may never know whether the order succeeded while the source message risks being acked. **Better:** check idempotency key or query ERP; only once the order is proven processed and local state synced may you mark the redundant error notice as a no-op.

## 14. Distinguish Discarding the Notice from Discarding the Source Work

**`ErrorMessage`** is a notification about an error. Discarding it is not equivalent to:

- Discarding the business event (was it executed or not?).
- Rolling back a transaction.
- Acking JMS/AMQP.
- Committing a Kafka offset.
- Deleting an SFTP file.
- Releasing a `CLAIMED` JDBC row.
- Replying to an HTTP request/reply with a valid result.

Track three parallel outcomes:

1. **Error handling outcome**: how was the error message classified and routed?
2. **Business operation outcome**: did side effects succeed, fail, or stay unknown?
3. **Source delivery outcome**: did the source ack, commit, or retry?

**A pipeline achieving "100% of errors routed to NullChannel" may just mean 100% loss of error visibility**, not 100% reliability.

## 15. NullChannel and RequestHandlerRetryAdvice

**RequestHandlerRetryAdvice** can wrap a handler to retry on exceptions. When `RetryPolicy` exhausts attempts, errors can propagate or use a `RecoveryCallback`.

### RecoveryCallback Returning Normally

~~~java
// Anti-pattern: can make caller/container think handler succeeded.
advice.setRecoveryCallback(context -> {
    audit("retry_exhausted", context.getLastThrowable());
    return null;
});
~~~

If auditing does not durably preserve the business message, swallowing the exception can cause the source to ack **before the message is safe**. Sending error info to `nullChannel` after the callback does not remove that risk.

### Safer RecoveryCallback When Parking Is Unavailable

~~~java
advice.setRecoveryCallback(context -> {
    // Message not yet preserved in recovery store => do not report success.
    throw new IllegalStateException(
        "Retry exhausted: delegate to source recovery",
        context.getLastThrowable());
});
~~~

This snippet illustrates **propagating the exception**; how containers react must still be verified per adapter.

### When Can Processing End at NullChannel After Recovery?

If recovery already persisted the failed message to a durable DLQ/parking store, confirmed persistence succeeded, updated business status per contract, and controlled source acking, then **the secondary informational `ErrorMessage`** may go to `NullChannel`. Even then, `NullChannel` is not where recovery happened.

## 16. Example Classification Policy: Discard Only With Evidence

Illustrative business-level policy:

~~~yaml
# Pseudocode policy: illustrative values, not Spring YAML.
error_handling:
  default: INVESTIGATE
  rules:
    - id: duplicate-processed
      when:
        category: DUPLICATE_DELIVERY
        completed_business_state_verified: true
        same_business_event_version: true
      action: AUDIT_THEN_DISCARD
      destination: nullChannel
    - id: informational-noop
      when:
        category: OPTIONAL_NOTIFICATION
        required_business_effect: false
        approved_owner: integration-operations
      action: AUDIT_THEN_DISCARD
      destination: nullChannel
    - id: retryable-dependency
      when:
        category: TRANSIENT_REMOTE_FAILURE
      action: RETRY_OR_PARK
    - id: unknown-outcome
      when:
        category: REMOTE_OUTCOME_UNKNOWN
      action: RECONCILE
    - id: invalid-message
      when:
        category: INVALID_PAYLOAD
      action: QUARANTINE
    - id: security-failure
      when:
        category: AUTHORIZATION_FAILURE
      action: ESCALATE
~~~

Conditions like **`completed_business_state_verified`** and **`same_business_event_version`** require verifying real persisted state rather than trusting sender-supplied headers. If proof is missing or mismatched, fall back to `INVESTIGATE`.

### Verification Order

1. Validate the message and authenticate the source.
2. Identify `businessEventId`, tenant, operation, and version.
3. Classify actual error and processed state.
4. Verify authorization/owner/approved no-op contract.
5. Write audit/metrics before discarding.
6. Send to `NullChannel` only if no incomplete business work remains.
7. If mandatory auditing or state lookup fails, **do not discard**.

## 17. Why Are Specific Reason Codes Necessary?

A reason code like **`EXPECTED_ERROR`** is too vague. It fails to explain why business work no longer needs processing.

| Reason Code | When Valid | What Must Be Proven |
|---|---|---|
| ALREADY_PROCESSED | Redelivery of completed business event | Durable inbox/result and event version |
| OUT_OF_SCOPE_FILE | File outside import contract | Contract allows ignoring that type |
| OPTIONAL_REPLY | Reply unneeded in one-way flow | No waiting caller |
| SUPERSEDED_EVENT | Event older than already-committed business version | Accurate ordering/version check |
| NOOP_BUSINESS_RULE | Action skippable per business rule | Rule/owner and audit |
| RECOVERY_RECORDED | Error durably persisted elsewhere for handling | Durable storage reference and ack contract |
| IGNORE_BY_DEFAULT | **Never use** | Lacks evidence and hides bugs |

**Each reason code must have a definition, owner, monitoring baseline, and tests.** Never allow operations teams to add exception classes to an ignore list without review.

## 18. File Inbound/Outbound: Which Files to Discard, Which Never to Discard?

File adapters typically use pollers and file filters to select messages. Separate **filtering out-of-scope files** from **discarding file-processing errors**.

### File Inbound — Cases Safe to Discard

~~~text
/inbound/orders-20261123.csv.ready
/inbound/README.txt
/inbound/.upload-lock
/inbound/orders-20261123.csv.part
~~~

If the partner contract defines only **`.ready`** files as data, `README` and lock markers are **out of scope** and should not become errors. Reject them at the source filter or route matching messages to `NullChannel` **after verifying the rule**.

A **`.part`** file is not "meaningless noise"; it is an incomplete file. Instead of marking it processed and discarding permanently, **skip it on the current poll** and allow processing once published ready.

### File Inbound — Cases Never to Discard

| Incident | Why Not NullChannel Directly? | Solution |
|---|---|---|
| CSV invalid schema | Record not validly processed | Quarantine + reason code |
| Corrupted file checksum | Data loss risk | Quarantine/alert partner |
| Permission denied | Infrastructure fault persists | Alert + fix ACL |
| Unreadable due to process lock | Recoverable | Re-poll / bounded retry |
| Downstream ERP error | File data not yet completed | Durable message state/retry |
| App restart after accept-once | File may not reappear | Persistent metadata + business idempotency |
| File archived before commit | Hard to replay or risks duplicates | Fix archive/transaction ordering |

### File Outbound

Mid-write failures can leave **partial** files. Retrying the same name without checking state can overwrite data. Use temporary outputs, stable final names, checksums/manifests, or atomic publishing rules per filesystem capability.

**`NullChannel` does not make file writes atomic.** Never discard outbound write `ErrorMessage`s without knowing whether the file completed.

## 19. SFTP: Discard Controlled Noise, Never Transfer Errors

SFTP inbound/outbound has many failure points: opening sessions, authentication, listing remote files, download/upload, rename, delete, and closing sessions.

| Scenario | Safe to Ignore? | Explanation |
|---|---|---|
| Duplicate remote file matching `DONE` in durable inbox for same event/version | Yes after check | Duplicate delivery/no-op |
| Marker or out-of-contract file | Yes at source filter | Not a business record |
| Temporary SFTP network outage | No | Retry/reconnect, preserve source |
| Host-key mismatch | No | Security/trust issue |
| Permission denied | No | Fix permissions/paths |
| Download leaves local partial file | No | Incomplete file |
| Upload finished yet response lost | Outcome unknown | Verify remote state/checksum |
| Rename timeout | No | Command may have completed |
| Remote file delete failed | No if retention/delete obligation exists | Controlled retry/reconciliation |

### Transfer and Metadata Semantics

Remote accept-once filters may mark files seen or processed depending on adapter/config; this data **does not replace** business success proof. Subsequent polls may not re-fetch the file if filters or metadata stores recorded it.

~~~text
SFTP remote file ready
   -> local staging
   -> verify checksum/manifest
   -> derive stable business event ID
   -> inbox / processing state
   -> downstream operation
   -> mark DONE or PARKED
   -> archive/remove source per contract
~~~

If an error occurs **before creating a message**, downstream `NullChannel` never sees it. The source needs reconnect/error handling. If downstream received the message and failed, you need a message store or durable replay mechanism.

A host-key mismatch must be investigated. Never catch the exception and send to `nullChannel` to ignore host verification; that hides misconfiguration or untrusted server risks.

## 20. HTTP Inbound/Outbound: Reply to Caller or Discard Error?

HTTP has a request–response contract, making "silently drop errors to stay quiet" especially dangerous.

### HTTP Inbound Gateway

~~~text
Client -> HTTP inbound gateway -> business flow
                               -> success response / error response
~~~

If downstream exceptions go to `ErrorMessage` then `NullChannel` without a valid reply, clients can wait until **reply timeout**, get generic errors, or retry requests blindly. If the operation has side effects, client retries cause duplicates.

**Never use `NullChannel` to dodge returning a contract-compliant HTTP status.** If a webhook request is already a valid no-op, return an **intentional success response** per contract and log a dedupe audit rather than leaving the caller hanging.

### HTTP Outbound Gateway

| Scenario | Handling Approach | Why |
|---|---|---|
| Secondary GET endpoint where contract permits loss | Approved fallback/no-op possible | Does not affect primary task |
| POST creating payment timed out | `OUTCOME_UNKNOWN` | Remote may have committed |
| HTTP 503 | Retry/delayed retry | Transient error |
| HTTP 429 | Backoff/rate-limit | Do not spam requests |
| 400 invalid payload | Quarantine | Fix data |
| 401/403 | Security/config handling | Do not retry forever |
| 409 already processed with proof | Dedupe possible | Verify business key/payload |
| 404 | Depends on domain | Permanent or eventual consistency |

**Never equate 409 with success:** a conflict might belong to another resource. Cross-check business key, payload/version, and result.

### HTTP POST with Idempotency Key

~~~mermaid
sequenceDiagram
    participant I as Integration Flow
    participant P as Partner ERP
    participant D as ERP Database
    I->>P: POST order + Idempotency-Key
    P->>D: Commit order
    D-->>P: OK
    Note over I,P: Response lost
    I->>I: Classify OUTCOME_UNKNOWN
    I->>P: Query status / retry same key if contract allows
    P-->>I: Order already processed
    I->>I: Sync state, audit dedupe
    Note over I: Discard secondary ErrorMessage only after business completion
~~~

Discarding `ErrorMessage` **after verifying the outcome** is completely different from discarding immediately upon a read timeout.

## 21. JMS: Discarding ErrorMessage Can Affect Rollback/Ack

JMS involves transacted sessions, acknowledgment modes, broker redelivery, and DLQs per listener/container config.

### Dangerous Scenario

~~~text
JMS listener receives message
    -> DB update fails
    -> ErrorMessage routed to nullChannel
    -> error path ends normally
    -> container may treat delivery as handled
    -> message gets acked/committed

Risk: database not updated, message gone from source.
~~~

Without a DLQ copy or rollback, messages risk **vanishing** even though the database was never updated.

### Mandatory Questions

1. Is the listener/session transacted?
2. Does the exception actually propagate to the container?
3. Which signal drives container ack/commit/rollback?
4. At which layer is `ErrorMessage` emitted, and does it affect callbacks?
5. What are the broker redelivery limits/DLQ?
6. Are prior DB/HTTP side effects idempotent?
7. Where are poison messages classified and routed?

If a duplicate delivery is verified complete by a **durable inbox**, the handler can perform a no-op and finish normally per business rules. Then acking is **intentional**, and any secondary informational `ErrorMessage` can be discarded after auditing. Never use `NullChannel` as a shortcut for deduplication.

## 22. AMQP/RabbitMQ: Requeue, DLQ, and Already-Processed Cases

For AMQP inbound:

- Propagating exceptions can trigger source policies.
- A `RecoveryCallback` returning normally can make the container treat the message as handled.
- Sending `ErrorMessage` to `NullChannel` does not automatically trigger nack or DLQ routing.
- Unbounded immediate requeue causes **hot loops**; use delayed retry/TTL/DLX or appropriate strategies.
- Prefetch/concurrency determines how many deliveries occupy worker slots.

### Duplicate Delivery

~~~text
AMQP message eventId=invoice-882-v3
    -> inbox checks eventId + version
    -> DONE state exists, result matches
    -> write audit ALREADY_PROCESSED
    -> finish message processing
~~~

This is a **valid business no-op**. There is no need to throw an exception just to send `ErrorMessage` to `NullChannel`. Any secondary informational event afterward may end at `NullChannel`.

### Outbound AMQP

If publishing to the broker succeeded while the client missed the confirm, retrying sends can duplicate messages. Use outbox/stable event IDs/consumer dedupe. **Publisher confirms do not prove consumers processed business work.**

Never send publish-failure `ErrorMessage`s to `NullChannel` when outbox state is wrong. Writing to another broker's DLQ and acking the source **is not automatically atomic**.

## 23. Kafka: Discarding ErrorMessage Does Not Commit/Seek Offsets

Kafka has records, partitions, offsets, and consumer groups. Spring Integration's Kafka inbound adapter turns records into messages; Kafka listener/container error handlers manage retries, seeks, commits, or DLTs per config.

| Component | Responsibility |
|---|---|
| Kafka consumer/client | Poll, heartbeat, consumer group |
| Container/error handler | Ack/commit, retry/seek/DLT per config |
| Spring Integration adapter/channel | Brings record into message flow |
| Business handler | Produces side effects and business outcome |
| `ErrorMessage`/error flow | Expresses occurred failure |
| `NullChannel` | Drops messages sent to it |

**NullChannel is not a Kafka DLT, does not seek offsets, and does not control commits.**

### Ordering Example

~~~text
Partition P:
    offset 100: order-created
    offset 101: order-updated
    offset 102: order-cancelled
~~~

If offset 100 hits a DB error, discarding `ErrorMessage` while committing the offset can let offsets 101/102 run against invalid state. If sending failed records to a DLT while advancing, **business ordering** must also be designed.

An event older than an already-committed business version **may** be marked superseded, provided you check by key/aggregate/version—not timestamp alone. Once verified inapplicable, the handler can ack per contract; `NullChannel` is only for dropping secondary notices.

Exactly-once semantics inside Kafka do not guarantee exactly-once across partner HTTP calls and separate database transactions. Never use `NullChannel` to paper over gaps needing inbox/outbox.

## 24. JDBC Inbound/Outbound: Row State Does Not Vanish with ErrorMessage

JDBC polling may select rows in state `NEW`. If a row was claimed and a downstream handler fails:

- Discarding `ErrorMessage` does not reset the row's lease/state.
- Rows can get stuck in `PROCESSING`.
- Marking `DONE` too early loses data.
- Re-claiming after remote success causes duplicates.

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                  |
                  +-> RETRY_WAIT -> PROCESSING
                  |
                  +-> INVALID / PARKED
~~~

Maintain stable event IDs, atomic claims/transactions, lease owner/expiry, attempt counts, and `nextAttemptAt` durable across restarts.

| Error | Handling Approach |
|---|---|
| Connection pool temporarily exhausted | Backoff/bulkhead/monitor |
| Deadlock/serialization conflict | Roll back, retry new transaction |
| Constraint violation | Verify duplicate vs. invalid data |
| Schema mismatch | Fix migration/SQL |
| Timeout after unclear commit | Query by business ID, reconcile |
| Transaction rollback-only | Do not continue inside broken transaction |

A unique constraint violation **may** be an already-processed duplicate or a genuine conflict. Never catch all `DataIntegrityViolationException`s and send them to `NullChannel`.

If the database update is mandatory, unresolved failures must propagate or move to `PARKED`/retry. A discarded `ErrorMessage` does not prove a row is `DONE`.

## 25. Gateways and replyChannel: Dropping Replies Can Leave Callers Waiting

Using `NullChannel` as a **reply channel** can fit one-way messages where nobody wants a result. For request–reply gateways:

- Callers expect a reply/error.
- Replying to `NullChannel` can time out the caller.
- Sending error replies to `NullChannel` erases root-cause details.
- Callers retrying after timeouts can duplicate side effects.
- Never discard replies to disguise errors as success.

| Flow | Reply Needed? | Recommendation |
|---|---|---|
| One-way event notification written to outbox | No | Can drop secondary reply |
| HTTP GET gateway returning status | Yes | Do not discard reply |
| POST gateway creating an order | Yes or ack per contract | Do not discard if outcome unknown |
| Fire-and-forget metric event | Maybe not | Discard acceptable per policy |
| Financial transaction event | Yes | Durable state and explicit response |

**No response does not equal success.** Define fire-and-forget explicitly per business case.

## 26. Recovery and NullChannel After Retries Are Exhausted

~~~text
A. Handler fails
   -> RetryPolicy exhausted
   -> RecoveryCallback rethrows
   -> container/caller handles error/rollback

B. Handler fails
   -> RetryPolicy exhausted
   -> recovery durably writes PARKED successfully
   -> source acks per contract
   -> secondary ErrorMessage audited then NullChannel
~~~

If `RecoveryCallback` only logs and returns `null` **before persisting a recovery record**, case B is not guaranteed. `NullChannel` does not fix that.

A recoverer sending `ErrorMessage` to an error channel can be helpful, yet verify that the error flow persists durably and check **how the recoverer's return value affects the handler/container**. Recovery success is measured by **processed or durably preserved business state**, not a send to a channel.

## 27. Discard Policies Need Owners, Scope, and Review Cycles

| Attribute | Example |
|---|---|
| `policyId` | `ignore-duplicate-v7` |
| `scope` | `partner-X`, `order-import`, `schema version>=2` |
| `reasonCode` | `ALREADY_PROCESSED` |
| `predicate` | inbox `DONE` and hash/version match |
| `allowedSource` | authenticated inbound service account |
| `impact` | no new order created |
| `auditRequired` | `true` |
| `owner` | Integration Operations |
| `approver` | Application Owner; Security if needed |
| `reviewDate` | organization-defined review cadence |
| `expiry` | set when rule is temporary |
| `metrics` | `discarded_total`, `unknown_total`, `false_discard_incidents` |
| `fallback` | `PARKED` when evidence is insufficient |

Never create wildcard rules like "discard all errors from adapter X". Narrowly scoped rules ensure new error types on that adapter still get investigated.

### Rule Change Process

1. Compare before/after case sets.
2. Test errors that must still retry/alert.
3. Measure newly discarded message volume.
4. Verify owner and review date.
5. Prepare rollback/feature flags if silent loss is detected.
6. Record `policyVersion` in audits.

## 28. Observability: Even When Discarding, Know Why

Once `NullChannel` receives a message, downstream branches typically stop. Therefore, measure **discard decisions before sending to the channel**, rather than treating zero `ErrorMessage`s as proof of system health.

| Metric | Definition | Meaning |
|---|---|---|
| **`discard_decisions_total`** | Discard decisions by `reasonCode`/flow | Detects abnormal spikes |
| **`verified_discard_rate`** | Discards with valid evidence ÷ total discards | Prevents treating unknown as valid |
| **`error_route_to_null_total`** | `ErrorMessage`s actually sent to `nullChannel` by policy | Separates from Filter discards |
| **`unexpected_errors_total`** | Errors lacking a valid ignore policy | Prioritizes triage |
| **`quarantined_messages_total`** | Invalid messages held for correction | Do not lump into discarded |
| **`parked_messages_total`** | Messages with pending obligations waiting | Track by age and severity |
| **`dlq_backlog_age_seconds`** | Max/percentile age of unresolved errors | Prevents forgotten backlogs |
| **`business_events_completed_total`** | Work truly `DONE` | Must not increment just because `NullChannel` accepted a message |
| **`source_redeliveries_total`** | Broker/source redeliveries | Separates retries from discards |
| **`duplicate_effect_total`** | Verified duplicate side effects | Measures business damage |
| **`ack_without_outcome_total`** | Acks/commits lacking valid `DONE`/`PARKED`/no-op | Alerts on silent loss |
| **`unknown_outcome_total`** | Remote outcomes still unknown | Must never default to discard |

**Never use `eventId`/`orderId`/`correlationId` as metric labels** due to high cardinality. Put them in logs/traces; keep metric labels bounded to `flow`, `errorCategory`, `reasonCode`, and `outcome`.

### Signs Errors Are Being Masked

If the day after routing global `errorChannel` to `NullChannel`, the dashboard shows **0 errors** while `DONE` orders drop, source input rises, and DLQs receive nothing, you likely have **silent data loss**. Reconcile source business event counts against `DONE`, `PARKED`, `QUARANTINED`, DLQ, and evidenced no-op decisions.

## 29. Minimal Auditing and Information Security

Every significant discard decision should retain:

- Stable `businessEventId`/`correlationId`;
- Source/flow/endpoint and message type;
- Error category, `reasonCode`, and policy version;
- Evidence reference (inbox `DONE`, state/version check, no-op contract);
- Error timestamp, classification timestamp, discard timestamp;
- Responsible service/owner identity;
- Source ack/commit outcome if verified;
- Final outcome: `DISCARDED_EXPECTED`, `NOOP_CONFIRMED`, or `RECOVERY_RECORDED`.

~~~json
{
  "auditId": "discard-20261123-0104",
  "businessEventId": "partner-X:order-312:v2",
  "correlationId": "corr-7001",
  "source": "amqp-inbound",
  "flowId": "order-import",
  "reasonCode": "ALREADY_PROCESSED",
  "decision": "DISCARD_EXPECTED",
  "policyVersion": "ignore-duplicate-v7",
  "evidenceRef": "inbox/order-312-v2",
  "sourceOutcome": "ACK_AFTER_NOOP_CONFIRMED",
  "decidedAt": "2026-11-23T10:15:00Z",
  "owner": "integration-operations"
}
~~~

This schema is illustrative only. **Never log** passwords, bearer tokens, refresh tokens, session cookies, SFTP private keys, `Authorization` headers, or full customer records. If payloads must be retained for replay, use an encrypted, access-controlled, retention-bounded message store and log payload references.

`NullChannel` logging of `ErrorMessage`s can depend on version/config. Never treat default logging as a durable audit. When auditing is mandatory, **persist successfully before discarding** and define behavior if the audit store fails.

## 30. Java: Guardrail Before NullChannel

The following example illustrates a **service activator that only forwards `ErrorMessage`s backed by valid evidence**. `DiscardPolicy`, `DiscardDecision`, and `DiscardAuditStore` are application-defined types; this is not a standalone compilable file as-is.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;

public class ExpectedErrorDiscardHandler {
    private final MessageChannel nullChannel;
    private final DiscardPolicy policy;
    private final DiscardAuditStore audit;

    public ExpectedErrorDiscardHandler(
            @Qualifier("nullChannel") MessageChannel nullChannel,
            DiscardPolicy policy,
            DiscardAuditStore audit) {
        this.nullChannel = nullChannel;
        this.policy = policy;
        this.audit = audit;
    }

    @ServiceActivator(inputChannel = "classifiedErrorMessages")
    public void handle(ErrorMessage error) {
        DiscardDecision decision = policy.evaluate(error);

        if (!decision.isVerifiedExpected()) {
            throw new IllegalStateException(
                    "Error is not safe to discard");
        }

        // Assumes persist guarantees durable write per contract.
        audit.persist(decision);

        boolean accepted = nullChannel.send(error);
        if (!accepted) {
            throw new IllegalStateException(
                    "NullChannel did not accept message");
        }
    }
}
~~~

### Remaining Limits and Responsibilities

- Policy must evaluate **business state**, not just exception class.
- Without evidence, **never** call `nullChannel`.
- Classifier/audit errors must route to a safe branch, avoiding **error loops** back into `classifiedErrorMessages`.
- Durable audit before discard still **does not prove** the source acked properly; check transactions/containers.
- A `true` return from `send` does not mean the business event is `DONE`.
- If the error flow is async, preserve messages **before the source ack boundary** when at-least-once is required.
- Never replace global `errorChannel` with this handler; use a dedicated classified channel so other errors are not swallowed.

## 31. Runbook When Discards Spike Abnormally

Signals:

- `discard_decisions_total` jumps multiple times above baseline;
- `business_events_completed_total` drops while inbound volume stays steady;
- `ALREADY_PROCESSED` rises yet durable inbox lacks matching `DONE` entries;
- DLQ/parking is abnormally empty;
- Sources acked despite missing business outcomes.

### Response Steps

1. **Isolate** by flow, endpoint, `reasonCode`, `policyVersion`, and recent change timestamp.
2. **Assess impact** using source event IDs and affected critical record counts.
3. **Disable/roll back** suspect ignore rules, routing unknowns to `INVESTIGATE`/`PARKED`.
4. **Preserve sources**: broker retention, Kafka offsets, file staging, JDBC leases, inbox/outbox.
5. **Reconcile** inbound IDs against `DONE`/`PARKED`/`QUARANTINED`/DLQ and remote outcomes.
6. **Controlled replay** using stable `eventId`, idempotency, rate limits, and proper ordering.
7. **Re-test** duplicate/no-op cases and non-discardable errors.
8. **Postmortem** with regression tests, owner/expiry review, and policy versioning.

Never fix incidents by adding wildcard ignores, purging DLQs, blindly resetting offsets, or logging full secrets to find root causes.

## 32. Test Matrix for NullChannel and Error Handling

Every test must specify **input, error category, expected destination, business outcome, source ack/commit, and audit evidence**.

| ID | Scenario | Result to Verify |
|---|---|---|
| N1 | Message intentionally sent to `NullChannel` | Branch terminates, no downstream side effects |
| N2 | Duplicate `ErrorMessage` with inbox `DONE` | Audited + discarded |
| N3 | Same event ID with different payload/version | Never blindly discarded |
| N4 | Out-of-contract README file | Filter discards properly |
| N5 | Incomplete `.part` file | Never permanently marked processed |
| N6 | Schema-invalid `.ready` file | Quarantined |
| N7 | SFTP connection reset | Budgeted retry/reconnect |
| N8 | SFTP host-key mismatch | Security alert, never ignored |
| N9 | Lost SFTP upload ACK | Reconcile remote state |
| N10 | HTTP 503 | Retry/delayed retry |
| N11 | HTTP 401/403 | Auth/config remediation |
| N12 | POST committed yet response lost | `OUTCOME_UNKNOWN`, idempotency/query |
| N13 | HTTP gateway needing reply | Never discarded causing timeout |
| N14 | One-way informational reply | Discarded per contract |
| N15 | JMS DB error, error flow swallows error | Test catches ack lacking outcome |
| N16 | JMS duplicate already `DONE` | Evidenced no-op/ack |
| N17 | Repeated AMQP requeue | Delayed retry/DLQ, no hot loop |
| N18 | Lost AMQP publish confirm | Unknown never discarded |
| N19 | Kafka record DB error | Offset never committed against policy |
| N20 | Old Kafka event lacking version proof | `INVESTIGATE`, never discarded |
| N21 | Verified superseded Kafka event | Audited no-op |
| N22 | JDBC deadlock | Retry fresh transaction |
| N23 | JDBC row stuck `PROCESSING` | Lease/recovery activates |
| N24 | Async error channel lacks subscriber | Recovery not counted complete |
| N25 | Error flow lacks durable store | `PARKED` never reported succeeded |
| N26 | Mandatory audit fails to write | Never discarded silently |
| N27 | `RecoveryCallback` returns normally | Verify ack/commit/persistence |
| N28 | `RetryAdvice` exhausts then rethrows | Container/caller handles properly |
| N29 | Restart before `NullChannel` | Source/state stay consistent |
| N30 | Restart after DLQ before ack | No loss, duplicate deduped |
| N31 | Broken wildcard ignore policy | Regression test fails |
| N32 | One event redelivered multiple times | Counts only one `DONE` business event |
| N33 | Unclassified error | `INVESTIGATE` |
| N34 | Error count suddenly hits 0 | Never inferred as everything succeeding |
| N35 | `ErrorMessage` contains token | Secret redacted |
| N36 | `DirectChannel` throws exception | Does not go to global `errorChannel` by default |
| N37 | `ExecutorChannel` emits error | Proper error path and source guarantee |
| N38 | Side effect happened before discard | Discard never treated as rollback |
| N39 | Compliance-critical event marked optional | Rule rejected |
| N40 | Burst of errors congests queue | Use backpressure, never delete errors |
| N41 | Dedupe evidence store unavailable | No `NullChannel` |
| N42 | Gateway reply routed to `NullChannel` | Test detects timeout |
| N43 | `ErrorMessage` logged, payload not durable | Not considered replayable |
| N44 | Message dropped before audit | Test detects missing evidence |
| N45 | Expired ignore policy | Must not discard |
| N46 | Global `errorChannel` has multiple subscribers | Logging/monitoring not accidentally disabled |

### Crash-Point Tests

Kill the process:

1. After receiving message, before inbox;
2. After remote commit, before response;
3. After classifier confirms duplicate, before audit;
4. After writing DLQ, before ack;
5. After ack, before metrics.

Each crash point must determine whether the event is **`DONE`/`PARKED`/`UNKNOWN`/needs redelivery**, not merely verify `NullChannel` did not throw.

## 33. Case Study Exercise: Reducing Noise Without Losing Orders

### Context

An enterprise runs the flow:

~~~text
SFTP inbound adapter + poller
    -> staging
    -> parse / validate
    -> HTTP outbound gateway ERP
    -> JDBC order status
    -> AMQP notification
~~~

Swamped by `ErrorMessage`s, operations wants to point **all of `errorChannel` to `nullChannel`**. During the day, these happen:

| Time | Event |
|---|---|
| 08:00 | Order A resent with same ID/version |
| 08:02 | Durable inbox has A as `DONE`, checksum matches |
| 08:05 | Order B JSON fails schema |
| 08:10 | ERP returns HTTP 503 for 15 minutes |
| 08:12 | POST order C committed, response lost |
| 08:14 | JDBC update D deadlocks |
| 08:18 | AMQP broker temporarily down |
| 08:20 | File E SFTP transfer drops mid-way |
| 08:30 | Kafka receives `order-updated` older than committed version |
| 09:00 | Error dashboard hits 0 after routing change |

### Tasks

1. Classify each scenario into `EXPECTED_IGNORE`, `INVALID`, `TRANSIENT`, `OUTCOME_UNKNOWN`, or another category.
2. Which scenarios can conclude at `NullChannel` **after evidence is verified**?
3. Why is routing the entire global `errorChannel` to `NullChannel` dangerous?
4. Design classifiers/recovery for each group.
5. If the source is JMS/AMQP/Kafka, what must be verified before a handler returns normally?
6. Why must an HTTP gateway needing a reply never discard its reply?
7. Pick 6 metrics to detect false discards.
8. Propose 8 negative tests protecting the rules.

### Reference Solution

**A — duplicate DONE:** durable inbox verifies matching business ID/version and checksum, writing audit `ALREADY_PROCESSED`. Can no-op and finish per contract; secondary notices can go to `NullChannel`.

**B — invalid:** quarantine with `reasonCode`, payload reference, and fix/replay path; never discard.

**ERP 503:** short backoff retries, then delayed retry if prolonged; no `NullChannel`.

**C — remote outcome unknown:** query ERP by business ID, use idempotency contract or move to `PARKED`/`OUTCOME_UNKNOWN`; never drop just because it timed out.

**D — JDBC deadlock:** roll back and retry a fresh transaction without resending the already-succeeded HTTP call.

**AMQP outage:** use an outbox to preserve notifications after DB commit and retry publishing when the broker recovers; never discard errors if notification is mandatory.

**SFTP E:** retry transfer and manage local partial/remote metadata; never mark the file complete.

**Kafka superseded event:** no-op only if business state/version checks prove the older event need not apply and contract permits; otherwise `INVESTIGATE`.

**General flaw:** global `errorChannel` aggregates many error sources; `nullChannel` stores no errors, performs no proper ack or DLQ, and therefore cannot replace triage.

**Metrics:** `discard_decisions_total`, `verified_discard_rate`, `unexpected_errors_total`, `unknown_outcome_total`, `ack_without_outcome_total`, and `business_events_completed_total`; plus age of parking/DLQ.

**Negative tests:** invalid JSON, auth failure, HTTP POST timeout after commit, dedupe lacking evidence, audit store down, required HTTP reply, restart after DLQ-before-ack, and Kafka missing version proof.

### Target Architecture

~~~mermaid
flowchart TD
    S["Inbound message / ErrorMessage"] --> V["Validate + classify + query business state"]
    V --> C{"Safe outcome?"}
    C -->|"VERIFIED_NOOP / DUPLICATE"| A["Audit reason + metric"]
    A --> N["nullChannel"]
    C -->|"INVALID"| Q["Quarantine"]
    C -->|"TRANSIENT"| R["Retry bounded / delayed retry"]
    C -->|"OUTCOME_UNKNOWN"| P["Reconcile / PARKED"]
    C -->|"SECURITY / UNCLASSIFIED"| X["Alert + investigate"]
    Q --> B["Durable store + owner"]
    R --> B
    P --> B
    X --> B
    B --> F["Replay / close after verified resolution"]
~~~

If the error flow runs asynchronously and the source already acked before classification, the diagram's reliability is incomplete; **preserve the message before the ack boundary** or adjust transaction/source recovery per adapter semantics.

## 34. Common Anti-Patterns

| Anti-Pattern | Risk | Fix |
|---|---|---|
| Routing global `errorChannel` to `nullChannel` | Lost monitoring and error recovery | Narrow classification, default `INVESTIGATE` |
| Dropping all `ErrorMessage`s because they were logged | Silent data loss | Business evidence + durable audit |
| Treating `NullChannel` as a DLQ | Impossible to replay messages | Real parking/DLQ |
| Catching every exception and returning success | Wrong acks | Propagate or durable recovery |
| Filter-discarding all failing files | Valid data lost | Separate out-of-scope from invalid |
| Deduping by `MessageHeaders.ID` | Unstable across redeliveries | Business event ID |
| Dropping HTTP timeouts after POST | Unknown side effects, duplicates | Idempotency/reconcile |
| Ignoring auth/host-key errors | Masks security issues | Security triage |
| Committing Kafka offsets before completion | Lost records or wrong ordering | Container error handler + DLT |
| Acking JMS/AMQP before parking | No source left to replay | Proper transaction/ack boundaries |
| Missing `reasonCode` | Unaudiable discards | Policy and audit |
| Logging secrets inside `ErrorMessage` | Credential leaks | Redaction |
| KPI counting only errors | "False green" | Business `DONE`, backlog, unknown |
| Ignore rules lacking owner/review | Exception list grows unchecked | Governance/expiry |
| Discarding when audit write fails | Lost evidence | Fail safe |
| Dropping replies of request–reply gateways | Caller timeouts | Reply/error contracts |
| Using `NullChannel` to shrink backlogs | Masks lost data | Backpressure/bulkhead/durable retry |

## 35. Safe NullChannel Design Checklist

- [ ] Identify whether the message being discarded is a business message, `ErrorMessage`, or secondary reply.
- [ ] Discard policy specifies scope, `reasonCode`, owner, evidence, and review cadence.
- [ ] Unclassified errors default to `INVESTIGATE`.
- [ ] Never route all of global `errorChannel` to `nullChannel`.
- [ ] Transient, invalid, unknown, and security errors go to proper retry/quarantine/parking/alerts.
- [ ] Durable inbox/state verifies duplicate/superseded events.
- [ ] Audits/metrics are recorded **before discarding** when required by contract.
- [ ] `NullChannel` is never used as a DLQ/retry scheduler/message store.
- [ ] Tested `DirectChannel`/`ExecutorChannel`/poller/`errorChannel` according to topology.
- [ ] Request–reply HTTP gateways return contract-compliant responses.
- [ ] JMS/AMQP ack/rollback/DLQ tested when error flows return normally.
- [ ] Kafka offset/seek/DLT and ordering controlled independently.
- [ ] File/SFTP uses ready markers, transfer states, metadata, and replay.
- [ ] JDBC uses row leases, transaction rollbacks, and clear `DONE`/`PARKED` states.
- [ ] `RecoveryCallback` never reports success before recovery is preserved.
- [ ] Idempotency/reconciliation/outbox protects external non-DB side effects.
- [ ] Metrics cover discards, unexpected errors, `ack_without_outcome`, and business `DONE`.
- [ ] Unnecessary tokens/private keys/passwords/PII are never logged.
- [ ] Negative tests cover invalid/auth/timeout-after-commit/missing evidence/audit failure.
- [ ] Crash tests cover DLQ-before-ack, restarts, and duplicates.
- [ ] Runbooks exist to roll back ignore rules and reconcile data.

## 36. Glossary and References

| Term | Meaning |
|---|---|
| **NullChannel** | `MessageChannel` that accepts and intentionally drops messages |
| **Black-hole channel** | Sink that forwards no messages to business processing |
| **ErrorMessage** | Message carrying `Throwable`/error context |
| **errorChannel** | Channel routing `ErrorMessage` per configuration |
| **discardChannel** | Channel receiving messages rejected by a `Filter` |
| **No-op** | Valid action requiring no state change |
| **Idempotency** | Repeating the same business event causes no extra side effects |
| **Unknown outcome** | Unclear whether remote committed |
| **DLQ/DLT/parking** | Storage holding failed messages for recovery |
| **Ack/commit** | Source progress marker |
| **Redelivery** | Broker/source delivering a message again |
| **Quarantine** | Isolating invalid messages for correction |
| **RecoveryCallback** | Callback executed when retries exhaust |
| **DirectChannel** | Synchronous dispatch channel |
| **ExecutorChannel** | Executor-backed dispatch channel |
| **Policy version** | Auditable version of classification rules |

### Further Reading

- **Spring Integration Reference — Message Channels:** `NullChannel`, `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and `PublishSubscribeChannel`.
- **Spring Integration Reference — Error Handling:** `ErrorMessage`, `errorChannel`, error handling flows.
- **Spring Integration Reference — Filters / Routers:** filter predicates, `discardChannel`, and routers.
- **Spring Integration Reference — Message Handler Advice:** `RequestHandlerRetryAdvice` and recovery.
- **Spring Integration Reference — File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC adapters/gateways:** per-source/target semantics.
- **Spring Retry Reference:** `RetryTemplate`, `RetryPolicy`, `BackOffPolicy`, `RecoveryCallback`.
- **Spring AMQP / Spring for Apache Kafka Reference:** nack/requeue, retries, offsets, DLQ/DLT.
- **Enterprise Integration Patterns:** Invalid Message Channel, Dead Letter Channel, Idempotent Receiver, Message Store, Guaranteed Delivery.

### Self-Check Questions

1. How does `NullChannel` differ from `errorChannel` and a DLQ?
2. Does `Filter.discardChannel` automatically catch all exceptions from a filter predicate?
3. Why does discarding an `ErrorMessage` not prove JMS rolled back?
4. Why must an HTTP gateway needing a reply never send its reply to `NullChannel`?
5. What conditions permit discarding a duplicate?
6. Why does a POST timeout after commit require reconciliation?
7. Does `NullChannel` automatically commit Kafka offsets?
8. What details must a valid ignore rule specify?
9. What might an error dashboard dropping to 0 after a routing change indicate?
10. When a mandatory audit store is down, should discarding continue?

### Short Answers

1. `NullChannel` destroys messages; `errorChannel` routes errors; a DLQ retains errors for investigation/replay.
2. No; `discardChannel` is for messages rejected by the predicate, not arbitrary execution exceptions.
3. Ack/rollback is governed by the container/transaction and exception path.
4. The caller can time out and retry, creating ambiguous state.
5. Durable inbox/state proving the exact same business event/version is already `DONE`, with auditing.
6. The remote side may have created side effects; use idempotency/status queries.
7. No; offsets belong to the consumer/container.
8. Scope, `reasonCode`, predicate, evidence, owner, review/expiry, audit, and fallback.
9. Errors may be getting swallowed; reconcile business `DONE`/backlog against sources.
10. No if durable auditing is mandatory; retain the error to handle per policy.

**Key takeaway:** **NullChannel does not fix errors; it is only an intentional message disposal sink.** In Spring Integration Adapters, send `ErrorMessage`s or unneeded messages to `NullChannel` **only after classification, verification of business outcomes, and fulfillment of audit/recovery obligations**. Whenever processing obligations remain, evidence is lacking, or the source risks mis-acking/committing, **preserve the error, retry, roll back, quarantine, or DLQ/park** instead of creating irrecoverable silence.
