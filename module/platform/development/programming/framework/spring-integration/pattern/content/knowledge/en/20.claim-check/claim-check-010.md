# Retrying messages with already-used claims

## 1. Scenario: a message is retried yet the claim is no longer usable

In an order flow, the initial payload holds extensive data such as order ID, line items, customer details, and shipping info. We do not want to pass the entire large or sensitive payload through every step, so we apply **Claim Check** — an Enterprise Integration Pattern (EIP):

1. Write the original payload/message to a **Message Store**.
2. Forward a small **claim check/token** referencing the stored data.
3. At the step needing the data, **claim-check out** to retrieve the payload/message.
4. Per storage policy, data may be retained or deleted once retrieved.

The problem surfaces when a message is resent (**retry/redelivery**) after the claim was already used or deleted.

~~~text
T0  Claim Check In:
    save Message<Order> into store, receive claimId=C-100

T1  Send ClaimToken(C-100) downstream

T2  Claim Check Out:
    fetch Order from C-100; configured to delete on read
    -> store no longer holds C-100

T3  Downstream calls payment service, times out

T4  Retry with same ClaimToken(C-100)
    -> Claim Check Out looks up C-100
    -> NOT_FOUND / ALREADY_CONSUMED
~~~

If retry is simply enabled around the entire flow, the request may repeat **claim-check out** with the same token even though the data was consumed on the first attempt. At that point, **retrying is no longer equivalent to re-running the previous attempt**: the needed data is gone.

~~~mermaid
flowchart TD
    I[Original Message] --> IN[Claim Check In]
    IN --> S[(Message Store)]
    IN --> T[ClaimToken C-100]
    T --> OUT[Claim Check Out]
    OUT --> S
    S -->|Payload found| P[Process Order]
    OUT -->|Remove-on-read| RM[Claim deleted]
    P -->|Transient error| RET[Retry same token]
    RET --> OUT
    OUT -->|Next attempt finds no claim| ERR[Claim missing / already consumed]
~~~

**Core question:** When a message can be retried, **is the claim retrieved once or multiple times**, and **when is it safe to mark completion/delete the original data**?

This lesson belongs to the **Claim check** chapter in the `SPRING_INTEGRATION_PATTERN` module. The module focuses on learning EIP implementation with Spring Integration to build loosely coupled, extensible message flows while practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, and testing/observing processing branches.

### Learning objectives

After this lesson, learners can:

1. Explain the **claim-in → token → claim-out → downstream → cleanup** lifecycle.
2. Distinguish **reading a claim**, **consuming a claim**, **confirming success**, and **deleting from the store**.
3. Predict the consequences of retrying with a removed, expired, revoked, or already-completed claim.
4. Choose **one-time claim**, **reusable until completion**, or **replay with a new claim** policies fitting business needs.
5. Design idempotency, correlation, transactions/outbox, completion states, and tombstones.
6. Write illustrative Java/Spring Integration flows and test retries, duplicates, timeouts, races, and missing/expired claims.
7. Handle security, TTL, message store persistence, downstream errors, and safe operations.

## 2. Concepts that must be separated

### 2.1. A Claim Check is a reference, not the payload

Example inbound message:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "C-007",
  "amountVnd": 8500000,
  "items": [
    {"sku": "SKU-A", "quantity": 2},
    {"sku": "SKU-B", "quantity": 1}
  ]
}
~~~

After claim-check in, the subsequent message might contain only:

~~~json
{
  "claimId": "C-100",
  "operationId": "PAY-ORD-1001"
}
~~~

A consumer receiving the token must **query an authoritative storage source** before using the original data. There is no basis to assume a token can reconstruct the entire payload on its own. Nor is a claim ID itself a safe **security capability**: if anyone knowing the ID can fetch the data, access control, tenant scoping, and lifetime limits are required.

### 2.2. States commonly confused with one another

| State | Exact meaning | Impact on retries |
|---|---|---|
| **STORED** | Payload was saved and assigned a claim ID. | Readable while unexpired and authorized. |
| **ISSUED** | Token was emitted toward consumers. | Not guaranteed the consumer received or processed it. |
| **READ** | A consumer retrieved the payload from the store. | Does not mean payment or business work succeeded. |
| **IN_PROGRESS** | A worker is currently processing the payload. | Must distinguish retries from duplicate processing. |
| **COMPLETED** | Business operation finished per contract. | Redelivery should return prior state/skip side effects. |
| **CONSUMED** | One-time policy no longer allows using the claim. | Reclaiming the same token may be rejected. |
| **EXPIRED** | Claim exceeded TTL/retention. | Must handle as expiration error, not transient timeout. |
| **DELETED** | Physical data was deleted. | Cannot restore from that store; needs another durable replay source to rerun. |
| **REVOKED** | Claim invalidated for security/business reasons. | Never mint a new token to bypass revocation. |

**Successful reading does not equal business completion.** If claim-check out deletes the payload immediately on read, a failure *after reading* still leaves retries without data.

### 2.3. Which layer owns the retry?

| Where does retry happen? | Example | Does claim-check out repeat? |
|---|---|---|
| **Downstream handler** | Retrying only HTTP payment after restoring payload. | Not necessarily, if payload stays in the execution context. |
| **Integration endpoint** | `RequestHandlerRetryAdvice` around claim-out and handler. | Possibly, depending on which endpoint the advice wraps. |
| **Broker redelivery** | Consumer crashes before ack and receives claim token again. | Usually yes if the flow restarts from the token. |
| **Gateway caller retry** | HTTP client resends the same operation. | May mint a new claim/token or reuse existing token, by design. |
| **Batch replay** | Operator replays messages from an event log. | May need to create a new claim from a trusted source. |
| **Scheduled recovery** | Error flow selects failed items to retry. | Depends on whether recovery payload still exists. |

You cannot answer “will retry work?” from the name Claim Check alone; you must know **where the retry loop starts, whether the token stays alive, and where the original payload is durably persisted**.

## 3. Claim usage policies

### 3.1. One-time claim: read once, then unreadable

A system wanting sensitive data accessed only once may design:

~~~text
AVAILABLE --(claim out succeeds)--> CONSUMED
CONSUMED --(claim out again)------> ALREADY_USED
~~~

Pros: reduces valid read count and can limit token reuse. Cons: if downstream fails after the data was consumed, **it cannot be restored using that same token** unless another replay mechanism was designed.

### 3.2. Reusable claim: keep payload until processing completes

~~~text
AVAILABLE --(read)--> AVAILABLE
AVAILABLE --(read again on retry)--> AVAILABLE
AVAILABLE --(business completion confirmed)--> COMPLETED
COMPLETED --(cleanup per policy)--> DELETED/TOMBSTONE
~~~

Pros: retries can re-read the payload when workers fail or brokers redeliver. Cons: requires **retention/security/idempotency** because multiple consumers/attempts may see the same payload.

**Re-reading the same payload must never duplicate side effects.** Reusable claims solve **data retrievability**, not exactly-once execution.

### 3.3. Replay from origin with a new claim

If the old claim is already consumed/deleted and business rules permit replay, you can:

~~~text
Original durable event / authorized archive
    -> verify permissions & prior operation state
    -> create new claim C-200
    -> keep matching business operationId or mint new version
    -> rerun per policy
~~~

**Never fabricate payloads by guessing** from tokens or leftover fields. Replay is valid only with **an intact, version-matched, authorized, unrevoked data source**.

### 3.4. Comparing the options

| Criterion | One-time claim | Reusable until completion | Replay/new claim |
|---|---|---|---|
| Retry same token after first read | Usually no. | Yes while unexpired/authorized. | No; uses a new claim. |
| Risk of losing payload before downstream success | Yes if consumed early. | Lower risk if cleaned up post-commit. | Needs replay source outside old store. |
| Risk of unintended token reuse | Lower after consumption. | Needs permission/TTL control. | Needs replay approval control. |
| Downstream idempotency needed | Still needed. | Practically mandatory under retries/redeliveries. | Mandatory if operation has side effects. |
| Complexity | Simple semantics, hard recovery. | More complex state/cleanup/dedup. | More complex workflow versioning/replay/authorization. |

**Recommended design for exercises:** use **reusable until completion**, separate “reading payload” from “marking completed,” and handle redeliveries with business idempotency. Also explicitly test one-time/expired claim error paths since real systems may pick other policies.

## 4. Spring Integration Claim Check and Message Store

### 4.1. Roles of components

In Spring Integration, the Claim Check pattern can be implemented with **Claim Check In Transformer**, **Claim Check Out Transformer**, and **Message Store**:

~~~mermaid
flowchart LR
    M["Message<Order>"] --> IN[Claim Check In]
    IN --> S[(Message Store)]
    IN --> ID["Message<ClaimId>"]
    ID --> RT[Router / Queue / Gateway]
    RT --> OUT[Claim Check Out]
    OUT --> S
    OUT --> REST["Restored Message<Order>"]
    REST --> H[Handler]
~~~

A claim-in transformer typically stores the original message in a `MessageStore` and forwards reference info; a claim-out transformer uses the reference to look up the message. **Whether the message is kept or deleted during claim-out must be explicitly controlled and verified against your running version's config**, never inferred from a method name.

### 4.2. Be careful with the remove-message option

Some Claim Check Out variants support a **remove-on-get/removeMessage** setting. Distinguish:

- **Lookup without remove:** claim can remain for retries (unless expired or removed by another process).
- **Lookup with remove:** claim becomes one-time per store mechanics; retrying the same token risks missing payload.
- **Manual deletion after processing:** requires knowing whether the handler truly finished and side effects committed.

**Do not assert that `removeMessage` defaults to true or false** without checking your project's docs/API/version; the key is documenting your flow's contract and testing behavior across two consecutive claim-outs.

### 4.3. Is the Message Store durable or not?

Stores carry different properties:

| Store | Advantage | Retry caveats |
|---|---|---|
| In-memory Message Store | Simple setup/testing, low latency. | Process crashes lose payloads. |
| JDBC-backed store | Can persist durably, supports configured transactions. | Needs schemas, serialization, cleanup, lock/transaction policies. |
| Supported distributed store | Accessible by multiple workers. | Races, availability, consistency, and TTL must be verified. |
| External object store + metadata record | Fits large payloads. | Must protect object refs, checksums, and dual-system lifecycles. |

**Saving into a `MessageStore` does not automatically provide production durability.** Verify transactions, consistency, broker acks, TTLs, serialization formats, encryption, and restart behavior.

### 4.4. Two IDs very easily confused

- **Claim ID:** key to look up the stored message. In a message-ID-based implementation, the token may correspond to the stored message's `MessageHeaders.ID`.
- **Operation ID:** business identity used to prevent duplicate side effects, e.g., `CHARGE:ORD-1001`.

If the same operation is replayed using a new claim, **`claimId` changes while `operationId` may stay the same** when the goal is retrying the exact same task. If business rules genuinely intend a new operation, enforce a transparent new operation ID policy. Never use claim ID as the sole idempotency key when claims can be re-created.

## 5. Java model for retryable claims

To clarify the difference between **reading a claim** and **consuming a claim**, let's build an illustrative Java 17 repository. This example **models the Claim Check pattern** without replacing Spring Integration's `MessageStore` class; framework code appears later.

### 5.1. Original payload and small ticket

~~~java
import java.math.BigDecimal;
import java.time.Instant;

record OrderPayload(
        String orderId,
        String customerId,
        BigDecimal amountVnd) {
    OrderPayload {
        if (orderId == null || orderId.isBlank()
                || customerId == null || customerId.isBlank()
                || amountVnd == null
                || amountVnd.signum() <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER_PAYLOAD");
        }
    }
}

record ClaimTicket(
        String claimId,
        String operationId,
        String tenantId) {
    ClaimTicket {
        if (claimId == null || claimId.isBlank()
                || operationId == null || operationId.isBlank()
                || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("INVALID_CLAIM_TICKET");
        }
    }
}

record StoredClaim(
        ClaimTicket ticket,
        OrderPayload original,
        Instant expiresAt) {
    StoredClaim {
        if (ticket == null || original == null
                || expiresAt == null) {
            throw new IllegalArgumentException("INVALID_STORED_CLAIM");
        }
    }
}
~~~

`ClaimTicket` carries enough fields to verify **claim ID, business operation, and tenant**, yet those fields **do not replace authentication/authorization**. Over the wire, protect the token as a reference leading to sensitive data.

### 5.2. Repository with explicit read and delete contracts

~~~java
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

interface ClaimRepository {
    void put(StoredClaim claim);
    Optional<StoredClaim> find(String claimId);
    Optional<StoredClaim> take(String claimId);
    boolean delete(String claimId);
}

final class InMemoryClaimRepository implements ClaimRepository {
    private final ConcurrentMap<String, StoredClaim> items =
            new ConcurrentHashMap<>();

    @Override
    public void put(StoredClaim claim) {
        if (items.putIfAbsent(
                claim.ticket().claimId(), claim) != null) {
            throw new IllegalStateException("DUPLICATE_CLAIM_ID");
        }
    }

    @Override
    public Optional<StoredClaim> find(String claimId) {
        return Optional.ofNullable(items.get(claimId));
    }

    @Override
    public Optional<StoredClaim> take(String claimId) {
        // Simulates single-use: retrieve and delete in one map operation.
        return Optional.ofNullable(items.remove(claimId));
    }

    @Override
    public boolean delete(String claimId) {
        return items.remove(claimId) != null;
    }
}
~~~

The `find`, `take`, and `delete` operations are intentionally **distinct**:

| Method | Data after successful call | Can retry same claim? |
|---|---|---|
| `find` | Remains in repository. | Yes, while unexpired/unrevoked. |
| `take` | Deleted immediately upon retrieval. | Not from this repository. |
| `delete` | Deleted without returning payload. | Not from this repository. |

`ConcurrentHashMap.remove` gives the **single-JVM demo** atomic get-and-remove at the map-operation level. It **does not represent** atomic consumption capabilities of every persistent `MessageStore`, nor does it create a transaction spanning remote payments.

### 5.3. Error codes distinguishing root causes

~~~java
enum ClaimFailureCode {
    NOT_FOUND,
    EXPIRED,
    ACCESS_DENIED,
    ALREADY_CONSUMED,
    INVALID_TICKET,
    STORE_UNAVAILABLE
}

final class ClaimAccessException extends RuntimeException {
    private final ClaimFailureCode code;

    ClaimAccessException(ClaimFailureCode code) {
        super(code.name());
        this.code = code;
    }

    ClaimFailureCode code() {
        return code;
    }
}
~~~

A store returning `null`/empty **does not tell you** whether a claim was consumed, expired, deleted, or never existed. To distinguish accurately, keep **state/tombstone or audit metadata**. Hence `NOT_FOUND` is the observable error when no record exists; `ALREADY_CONSUMED` is used only when the system has evidence of consumed state.

### 5.4. Service reading a claim multiple times without deleting

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

final class RetryableClaimService {
    private final ClaimRepository repository;
    private final Clock clock;

    RetryableClaimService(
            ClaimRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    ClaimTicket issue(
            String operationId,
            String tenantId,
            OrderPayload original,
            Duration ttl) {
        Objects.requireNonNull(original, "original");
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("INVALID_CLAIM_TTL");
        }
        ClaimTicket ticket = new ClaimTicket(
                UUID.randomUUID().toString(),
                operationId,
                tenantId);
        repository.put(new StoredClaim(
                ticket,
                original,
                Instant.now(clock).plus(ttl)));
        return ticket;
    }

    OrderPayload restore(
            ClaimTicket ticket,
            String authenticatedTenantId) {
        if (ticket == null) {
            throw new ClaimAccessException(
                    ClaimFailureCode.INVALID_TICKET);
        }
        if (!ticket.tenantId().equals(authenticatedTenantId)) {
            throw new ClaimAccessException(
                    ClaimFailureCode.ACCESS_DENIED);
        }

        StoredClaim stored = repository.find(ticket.claimId())
                .orElseThrow(() -> new ClaimAccessException(
                        ClaimFailureCode.NOT_FOUND));

        if (!stored.ticket().equals(ticket)) {
            throw new ClaimAccessException(
                    ClaimFailureCode.ACCESS_DENIED);
        }
        if (!Instant.now(clock).isBefore(stored.expiresAt())) {
            throw new ClaimAccessException(
                    ClaimFailureCode.EXPIRED);
        }
        return stored.original();
    }

    boolean cleanupAfterConfirmed(ClaimTicket ticket) {
        // Call only after authoritative business confirmation.
        return repository.delete(ticket.claimId());
    }
}
~~~

**Pay attention to the ordering:**

1. Verify tenant against **authenticated context**, never trusting an arbitrary caller-modified claim token.
2. Look up claim by `claimId`.
3. Verify the stored record matches the **entire ticket**, preventing using one ID with swapped metadata.
4. Check TTL at read time.
5. Return payload **without deleting** — downstream errors can retry the claim.
6. Cleanup is considered only with proof of business completion and compliant retention policies.

This example **does not yet** support revocation, real multi-tenant authorization, auditing, encryption, retention management, rate limiting, or multi-node consistency. Separating `authenticatedTenantId` from `ticket.tenantId` is necessary, yet production must derive tenant context from a principal/trust boundary rather than an external request body.

### 5.5. Example of two restores of the same claim

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;

ClaimRepository store = new InMemoryClaimRepository();
RetryableClaimService claims =
        new RetryableClaimService(store, Clock.systemUTC());

OrderPayload order = new OrderPayload(
        "ORD-1", "C-7", new BigDecimal("8500000"));
ClaimTicket ticket = claims.issue(
        "PAY-ORD-1", "TENANT-A", order,
        Duration.ofMinutes(15));

OrderPayload firstRead = claims.restore(ticket, "TENANT-A");
OrderPayload secondRead = claims.restore(ticket, "TENANT-A");

// firstRead.equals(secondRead) == true
// store.find(ticket.claimId()).isPresent() == true
~~~

Two restores still return the same data because **there is no remove-on-read**. That does not mean **charging twice** is allowed. We still need operation and business-outcome management.

## 6. Idempotency when claim retries succeed or fail

### 6.1. A business operation must have a stable ID

Suppose the payment operation has ID `PAY-ORD-1`. When the producer resends the claim token, downstream must know this **is not a new charge request**.

~~~text
Attempt 1:
  claimId=C-100
  operationId=PAY-ORD-1
  charge succeeded, reply lost

Attempt 2 (redelivery):
  claimId=C-100
  operationId=PAY-ORD-1
  must look up completed result
  do not charge a second time
~~~

If the old claim was already cleaned up, idempotency status **still needs enough lifespan** to handle late retry messages within the replay horizon. Never delete the claim and wipe all processed traces simultaneously while the broker can still redeliver.

### 6.2. Receipts and an idempotent gateway

~~~java
record OperationReceipt(
        String operationId,
        String externalReference,
        String status) {}

interface IdempotentPaymentGateway {
    OperationReceipt charge(
            String operationId,
            OrderPayload order);
}
~~~

A production implementation must guarantee that **the same `operationId`** is recognized right at the side-effect boundary. If the remote payment API supports idempotency keys, pass `operationId` on that request and inspect responses/reconcile. Otherwise, build an inbox/operation state machine and status-query mechanism before retrying; a `HashMap` in the calling process loses validity on restart.

### 6.3. Fake implementation strictly for unit tests

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

final class FakeIdempotentPaymentGateway
        implements IdempotentPaymentGateway {

    final AtomicInteger committedOperations =
            new AtomicInteger();
    private final ConcurrentMap<String, OperationReceipt> ledger =
            new ConcurrentHashMap<>();

    @Override
    public OperationReceipt charge(
            String operationId,
            OrderPayload order) {
        return ledger.computeIfAbsent(operationId, id -> {
            committedOperations.incrementAndGet();
            return new OperationReceipt(
                    id,
                    "PAYMENT-" + id,
                    "SUCCESS");
        });
    }
}
~~~

`computeIfAbsent` simulates **single-JVM deduplication**. This is **not** guidance to execute real HTTP calls or DB transactions inside a map computation. A real gateway must manage uniqueness, concurrency, remote timeouts, and commits within actual transactions/systems.

### 6.4. Retry workflow retaining the claim until cleanup is safe

~~~java
final class ClaimPaymentWorkflow {
    private final RetryableClaimService claims;
    private final IdempotentPaymentGateway payments;

    ClaimPaymentWorkflow(
            RetryableClaimService claims,
            IdempotentPaymentGateway payments) {
        this.claims = claims;
        this.payments = payments;
    }

    OperationReceipt handle(
            ClaimTicket ticket, String authenticatedTenant) {
        OrderPayload original = claims.restore(
                ticket, authenticatedTenant);

        // At the side-effect boundary, pass the stable operation ID.
        return payments.charge(ticket.operationId(), original);
    }
}
~~~

The demo workflow **does not delete the claim** inside `handle`: retries can re-read the payload. In production, after durably recording completion, a separate lifecycle manager cleans up per retention. Never place `repository.delete` in a `finally` block inside `handle` — because `finally` runs **even when payment fails**.

### 6.5. Is post-commit cleanup truly atomic?

Examine an adverse sequence:

~~~text
T1 Payment service commits SUCCESS
T2 Process crashes before caller saves OperationReceipt
T3 Broker redelivers claim
T4 Caller does not know payment committed, risking a second charge
~~~

If the payment service supports idempotency keys, the second call can receive the prior receipt instead of creating a new charge. Otherwise, **reconcile** with the target system before executing another side effect.

Another sequence:

~~~text
T1 Caller records SUCCESS receipt
T2 Caller deletes claim
T3 Broker ACK is lost
T4 Broker redelivers token
~~~

At that point the claim is gone. If the consumer **checks the completion receipt before claim-out**, it can return `ALREADY_COMPLETED` or the saved receipt without restoring the payload. If logic always runs claim-out first, it will report `NOT_FOUND` even though the operation completed — an unnecessary false alarm.

**Design conclusion:** the order and timing of checking **idempotency record → claim retrieval → side effect → completion record → cleanup** is part of the retry contract, not merely an optimization detail.

## 7. Completion-aware workflow handling redelivery after cleanup

### 7.1. Why check status before reading the claim?

Right after an operation finishes and claim data is legitimately deleted per policy, the broker may still redeliver the token due to a lost ack. At that moment, **do not immediately error “missing claim”** if durable evidence exists that the matching operation finished.

~~~mermaid
flowchart TD
    T[ClaimTicket on retry queue] --> AUTH{Verify tenant + token?}
    AUTH -->|No| DENY[ACCESS_DENIED]
    AUTH -->|Yes| L{Operation completion ledger}
    L -->|Valid receipt exists| OLD[Return old receipt / skip side effect]
    L -->|None yet| R[Restore claim]
    R -->|Available| PAY[Idempotent business action]
    R -->|Missing/expired/consumed| Q[Quarantine / reconcile / replay policy]
    PAY --> COMMIT[Record completion]
    COMMIT --> CLEAN[Cleanup per retention]
~~~

**A receipt may be returned before reading the claim** only when receipt lookup is **authorized** and bound to the right tenant, operation, and request. Never let a forged token specify an arbitrary `operationId` and fetch someone else's result.

### 7.2. An illustrative ledger

~~~java
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

record OperationKey(String tenantId, String operationId) {}

interface CompletionLedger {
    Optional<OperationReceipt> find(OperationKey key);
    void record(OperationKey key, OperationReceipt receipt);
}

final class InMemoryCompletionLedger implements CompletionLedger {
    private final ConcurrentMap<OperationKey, OperationReceipt> done =
            new ConcurrentHashMap<>();

    @Override
    public Optional<OperationReceipt> find(OperationKey key) {
        return Optional.ofNullable(done.get(key));
    }

    @Override
    public void record(OperationKey key, OperationReceipt receipt) {
        done.putIfAbsent(key, receipt);
    }
}
~~~

`InMemoryCompletionLedger` only clarifies status-check logic; it **is not durable across restarts** and does not stop two processes from starting side effects concurrently. In production, the ledger needs verified constraints/locking/transaction policies tied to actual operations in the target system.

### 7.3. Workflow handling duplicates before restoring

~~~java
final class CompletionAwareClaimWorkflow {
    private final RetryableClaimService claims;
    private final IdempotentPaymentGateway payments;
    private final CompletionLedger ledger;

    CompletionAwareClaimWorkflow(
            RetryableClaimService claims,
            IdempotentPaymentGateway payments,
            CompletionLedger ledger) {
        this.claims = claims;
        this.payments = payments;
        this.ledger = ledger;
    }

    OperationReceipt handle(
            ClaimTicket ticket, String authenticatedTenant) {

        if (ticket == null
                || !ticket.tenantId().equals(authenticatedTenant)) {
            throw new ClaimAccessException(
                    ClaimFailureCode.ACCESS_DENIED);
        }

        OperationKey key = new OperationKey(
                authenticatedTenant, ticket.operationId());

        OperationReceipt previous = ledger.find(key)
                .orElse(null);
        if (previous != null) {
            // Production must also validate claim-to-operation binding
            // or principal permission to view the receipt.
            return previous;
        }

        OrderPayload payload = claims.restore(
                ticket, authenticatedTenant);

        OperationReceipt result = payments.charge(
                ticket.operationId(), payload);

        ledger.record(key, result);
        return result;
    }
}
~~~

**Intentional limitation:** the example does not present a distributed exactly-once algorithm. Between `ledger.find` and `payments.charge`, **two workers** could both observe no completion and call payment concurrently. Therefore `IdempotentPaymentGateway` must be genuinely idempotent at the side-effect target, or the workflow needs a **claim operation → `IN_PROGRESS` → `COMMITTED`** mechanism with fenced locks/leases and valid recovery.

A completion ledger keyed by `operationId` must also bind **request fingerprint, tenant, owner, and claim provenance**; if two different payloads share the same operation ID, never silently treat the second operation as a valid duplicate.

### 7.4. Business state machine to design explicitly

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> IN_PROGRESS: attempt claim
    IN_PROGRESS --> COMPLETED: side effect confirmed
    IN_PROGRESS --> RETRYABLE: transient failure
    RETRYABLE --> IN_PROGRESS: retry with same operation
    IN_PROGRESS --> UNKNOWN: reply lost after possible commit
    UNKNOWN --> COMPLETED: reconcile confirmed
    UNKNOWN --> RETRYABLE: reconcile confirmed not committed
    CREATED --> CANCELLED: authorized cancel
    RETRYABLE --> CANCELLED: stop retry
    COMPLETED --> [*]
    CANCELLED --> [*]
~~~

A standout state is **UNKNOWN**: a timeout does not prove the operation failed. Before retrying an operation with side effects, query/reconcile by idempotency key or receipt at the target system.

## 8. Unit tests for reusable and one-time claims

### 8.1. Reading a reusable claim twice preserves data

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RetryableClaimServiceTest {

    private static final Clock FIXED = Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC);

    private final ClaimRepository repository =
            new InMemoryClaimRepository();
    private final RetryableClaimService service =
            new RetryableClaimService(repository, FIXED);

    @Test
    void sameClaimCanBeReadAgainBeforeCompletion() {
        OrderPayload original = new OrderPayload(
                "ORD-1", "C-1", new BigDecimal("8500000"));
        ClaimTicket token = service.issue(
                "PAY-1", "TENANT-A", original,
                Duration.ofMinutes(10));

        assertEquals(original,
                service.restore(token, "TENANT-A"));
        assertEquals(original,
                service.restore(token, "TENANT-A"));
        assertTrue(repository.find(token.claimId()).isPresent());
    }
}
~~~

This test proves **data remains after reading** in a reusable implementation. It does not yet prove no double charges occur when a handler runs twice.

### 8.2. One-time consumption makes retrying the same token fail

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ClaimConsumedRetryTest {

    @Test
    void oldTokenCannotRestoreAfterOneTimeTake() {
        ClaimRepository store = new InMemoryClaimRepository();
        RetryableClaimService service =
                new RetryableClaimService(store, Clock.systemUTC());

        ClaimTicket ticket = service.issue(
                "PAY-2",
                "TENANT-A",
                new OrderPayload(
                        "ORD-2", "C-2",
                        new BigDecimal("1000000")),
                Duration.ofMinutes(5));

        assertTrue(store.take(ticket.claimId()).isPresent());

        ClaimAccessException error = assertThrows(
                ClaimAccessException.class,
                () -> service.restore(ticket, "TENANT-A"));

        assertEquals(ClaimFailureCode.NOT_FOUND, error.code());
    }
}
~~~

Why does the test expect `NOT_FOUND` instead of `ALREADY_CONSUMED`? Because `take` **deleted the record completely**, and the demo repository has no tombstone distinguishing “already used” from “never existed.” If a business contract requires returning `ALREADY_CONSUMED`, persist state traces elsewhere.

### 8.3. Unreadable after TTL

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ClaimExpirationTest {

    @Test
    void expiredTokenCannotBeUsedEvenIfRecordStillExists() {
        Instant start = Instant.parse("2026-01-01T00:00:00Z");
        Clock issueClock = Clock.fixed(start, ZoneOffset.UTC);
        Clock laterClock = Clock.fixed(
                start.plus(Duration.ofMinutes(11)),
                ZoneOffset.UTC);

        ClaimRepository store = new InMemoryClaimRepository();
        RetryableClaimService issuer =
                new RetryableClaimService(store, issueClock);
        RetryableClaimService reader =
                new RetryableClaimService(store, laterClock);

        ClaimTicket token = issuer.issue(
                "PAY-3", "TENANT-A",
                new OrderPayload(
                        "ORD-3", "C-3",
                        new BigDecimal("1000000")),
                Duration.ofMinutes(10));

        ClaimAccessException error = assertThrows(
                ClaimAccessException.class,
                () -> reader.restore(token, "TENANT-A"));

        assertEquals(ClaimFailureCode.EXPIRED, error.code());
    }
}
~~~

**Never use `Thread.sleep(11 * 60 * 1000)`** to test TTL. Injecting `Clock` makes tests deterministic and fast. When a store's native TTL **physically deletes the record** before reading, you may observe only `NOT_FOUND` unless separate tombstones/metadata exist; test against your actual production store's behavior.

### 8.4. Block another tenant from retrieving payload

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ClaimAuthorizationTest {
    @Test
    void differentTenantCannotRestoreClaim() {
        RetryableClaimService service =
                new RetryableClaimService(
                        new InMemoryClaimRepository(),
                        Clock.systemUTC());

        ClaimTicket token = service.issue(
                "PAY-4", "TENANT-A",
                new OrderPayload(
                        "ORD-4", "C-4",
                        new BigDecimal("1000000")),
                Duration.ofMinutes(5));

        ClaimAccessException error = assertThrows(
                ClaimAccessException.class,
                () -> service.restore(token, "TENANT-B"));

        assertEquals(
                ClaimFailureCode.ACCESS_DENIED, error.code());
    }
}
~~~

**Security note:** this code only demonstrates tenant checking inside a service method. Production must verify **real principals, tenant ownership, permissions, message integrity, and audits**, never taking `authenticatedTenant` directly from an external request body.

### 8.5. Retry after transient failure: first attempt fails, second succeeds

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ClaimRetryAfterFailureTest {

    @Test
    void retryCanReadSameClaimAfterTransientFailure() {
        ClaimRepository store = new InMemoryClaimRepository();
        RetryableClaimService claims =
                new RetryableClaimService(store, Clock.systemUTC());
        ClaimTicket ticket = claims.issue(
                "PAY-5", "TENANT-A",
                new OrderPayload(
                        "ORD-5", "C-5",
                        new BigDecimal("1500000")),
                Duration.ofMinutes(10));

        AtomicInteger attempts = new AtomicInteger();
        IdempotentPaymentGateway flaky = (operationId, order) -> {
            if (attempts.incrementAndGet() == 1) {
                throw new IllegalStateException(
                        "TRANSIENT_PAYMENT_UNAVAILABLE");
            }
            return new OperationReceipt(
                    operationId, "PAYMENT-5", "SUCCESS");
        };

        ClaimPaymentWorkflow workflow =
                new ClaimPaymentWorkflow(claims, flaky);

        assertThrows(IllegalStateException.class, () ->
                workflow.handle(ticket, "TENANT-A"));

        OperationReceipt recovered =
                workflow.handle(ticket, "TENANT-A");

        assertEquals("SUCCESS", recovered.status());
        assertEquals(2, attempts.get());
    }
}
~~~

In the test, failure happens **before the fake payment commits**, so retrying is safe in this illustrative scenario. If the first call committed yet lost the reply, idempotency/reconciliation as in sections 6–7 is required; never infer from an exception that no side effect occurred.

### 8.6. Two redeliveries produce no duplicate side effect in fake

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ClaimRedeliveryIdempotencyTest {
    @Test
    void sameOperationReturnsSameReceipt() {
        RetryableClaimService claims =
                new RetryableClaimService(
                        new InMemoryClaimRepository(),
                        Clock.systemUTC());
        FakeIdempotentPaymentGateway payments =
                new FakeIdempotentPaymentGateway();
        ClaimPaymentWorkflow workflow =
                new ClaimPaymentWorkflow(claims, payments);

        ClaimTicket token = claims.issue(
                "PAY-6", "TENANT-A",
                new OrderPayload(
                        "ORD-6", "C-6",
                        new BigDecimal("750000")),
                Duration.ofMinutes(10));

        OperationReceipt first =
                workflow.handle(token, "TENANT-A");
        OperationReceipt repeated =
                workflow.handle(token, "TENANT-A");

        assertEquals(first, repeated);
        assertEquals(1, payments.committedOperations.get());
    }
}
~~~

This is a **fake gateway unit test** verifying a simulated contract. It does **not** prove an external merchant/payment processor supports exactly-once or idempotency like the fake; adapter/system tests against the real target system are required.

## 9. Retrying after claim cleanup when operation already finished

### 9.1. Prior outcome can resolve duplicates without payload

This differs from “retry because payment failed”:

~~~text
Attempt #1:
  claim C-100 -> restore Order
  charge PAY-100 -> SUCCESS
  completion ledger records SUCCESS
  cleanup claim C-100
  broker ack lost

Attempt #2:
  broker redelivers C-100
  check completion ledger: PAY-100 already SUCCESS
  -> return old receipt / acknowledge duplicate
  -> NO need to restore C-100
  -> NO extra charge
~~~

A flow can resolve duplicates **even after the claim was deleted**, because the operation completed and has independent evidence. Yet if the ledger is untrusted or the token is not properly bound to the operation/tenant, **never guess** that a missing claim implies success.

### 9.2. Unit test for completion-aware workflow

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ClaimAlreadyCompletedTest {
    @Test
    void redeliveryAfterCleanupUsesVerifiedReceipt() {
        ClaimRepository store = new InMemoryClaimRepository();
        RetryableClaimService claims =
                new RetryableClaimService(store, Clock.systemUTC());
        FakeIdempotentPaymentGateway payment =
                new FakeIdempotentPaymentGateway();
        CompletionLedger ledger =
                new InMemoryCompletionLedger();
        CompletionAwareClaimWorkflow workflow =
                new CompletionAwareClaimWorkflow(
                        claims, payment, ledger);

        ClaimTicket token = claims.issue(
                "PAY-100", "TENANT-A",
                new OrderPayload(
                        "ORD-100", "C-100",
                        new BigDecimal("5000000")),
                Duration.ofMinutes(15));

        OperationReceipt first =
                workflow.handle(token, "TENANT-A");
        claims.cleanupAfterConfirmed(token);

        assertFalse(store.find(token.claimId()).isPresent());

        // Retry need not read claim when ledger recorded completion.
        OperationReceipt duplicate =
                workflow.handle(token, "TENANT-A");

        assertEquals(first, duplicate);
        assertEquals(1, payment.committedOperations.get());
    }
}
~~~

Test results match **the demo implementation**. With a durable completion ledger and remote payments, still verify transaction/commit semantics: **ledger and store are not necessarily updated atomically with the payment**. When two workers run concurrently, locks or target-side idempotency are required.

### 9.3. What if the claim is missing without a completion receipt?

~~~text
ClaimToken C-404
  -> ledger has no COMPLETED
  -> store has no C-404
  -> CLAIM_NOT_FOUND
~~~

This is an **uncertain state requiring investigation**, neither proving payment succeeded nor proving it definitely never ran. Possibilities:

- Claim was consumed on a prior attempt and downstream failed afterward.
- TTL cleanup deleted the data.
- In-memory Message Store lost state after restart.
- Token targeted the wrong store/shard/tenant.
- Token is invalid or forged.
- Claim was never durably saved before the token was emitted.
- Completion ledger was lost while remote payment committed.

The right response is **classifying, reconciling by `operationId`, and replaying only from a trusted origin**, instead of blindly retrying or synthesizing fake payloads.

## 10. Java DSL: Claim Check retries across two IntegrationFlows

### 10.1. Why separate issue and process into two flows?

For clear testing, we split:

~~~mermaid
flowchart LR
    A["ClaimSubmission"] --> I["Claim In / store"]
    I --> T["ClaimTicket"]
    T --> Q[(Token queue / transport)]
    Q --> W["Completion-aware workflow"]
    W -->|Incomplete| OUT["Claim Out / restore payload"]
    OUT --> PAY["Idempotent Payment"]
    PAY --> REC["Completion ledger"]
    W -->|Already complete| OLD["Existing receipt"]
    REC --> R["OperationReceipt"]
    OLD --> R
~~~

The example uses **Transformer/service endpoints** to implement the Claim Check pattern and precisely control **read-without-remove**. Spring Integration also provides **dedicated Claim Check In/Out Transformers**; when using native components, verify `MessageStore` and remove behavior for your running version.

### 10.2. Input DTOs for Gateway

~~~java
record ClaimSubmission(
        OrderPayload original,
        String operationId,
        String tenantId) {}

record ClaimAttempt(
        ClaimTicket ticket,
        String authenticatedTenantId) {}
~~~

The `authenticatedTenantId` field here merely represents **context simulated by an adapter**. In production HTTP/broker systems, derive it from a principal/trusted security context, never an arbitrary string chosen by an external caller.

### 10.3. Spring Integration configuration

~~~java
import java.time.Clock;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@MessagingGateway
interface ClaimPaymentGateway {
    @Gateway(requestChannel = "claims.issue.input",
            replyTimeout = 5000)
    ClaimTicket issue(ClaimSubmission submission);

    @Gateway(requestChannel = "claims.process.input",
            replyTimeout = 5000)
    OperationReceipt process(ClaimAttempt attempt);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class ClaimRetryFlowConfiguration {

    @Bean(name = "claims.issue.input")
    MessageChannel issueChannel() {
        return new DirectChannel();
    }

    @Bean(name = "claims.process.input")
    MessageChannel processChannel() {
        return new DirectChannel();
    }

    @Bean
    Clock claimClock() {
        return Clock.systemUTC();
    }

    @Bean
    ClaimRepository claimRepository() {
        return new InMemoryClaimRepository();
    }

    @Bean
    RetryableClaimService retryableClaims(
            ClaimRepository repository, Clock claimClock) {
        return new RetryableClaimService(
                repository, claimClock);
    }

    @Bean
    FakeIdempotentPaymentGateway paymentGatewayFake() {
        return new FakeIdempotentPaymentGateway();
    }

    @Bean
    CompletionLedger completionLedger() {
        return new InMemoryCompletionLedger();
    }

    @Bean
    CompletionAwareClaimWorkflow completionAwareWorkflow(
            RetryableClaimService claims,
            FakeIdempotentPaymentGateway payments,
            CompletionLedger ledger) {
        return new CompletionAwareClaimWorkflow(
                claims, payments, ledger);
    }

    @Bean
    IntegrationFlow issueClaimFlow(RetryableClaimService claims) {
        return IntegrationFlow.from("claims.issue.input")
                .transform(ClaimSubmission.class, submission ->
                        claims.issue(
                                submission.operationId(),
                                submission.tenantId(),
                                submission.original(),
                                Duration.ofMinutes(15)))
                .get();
    }

    @Bean
    IntegrationFlow retryClaimFlow(
            CompletionAwareClaimWorkflow workflow) {
        return IntegrationFlow.from("claims.process.input")
                .handle(ClaimAttempt.class, (attempt, headers) ->
                        workflow.handle(
                                attempt.ticket(),
                                attempt.authenticatedTenantId()))
                .get();
    }
}
~~~

**How to read it:**

1. `ClaimPaymentGateway.issue` receives the original payload and returns a ticket.
2. `issueClaimFlow` writes the payload to the repository and returns `ClaimTicket` via the Gateway's reply path.
3. `ClaimPaymentGateway.process` receives an attempt containing the ticket.
4. `retryClaimFlow` checks the completion ledger; if incomplete, it restores the payload **without deleting**.
5. The fake payment uses a stable operation ID to prevent duplicates in tests.
6. Once completed and cleaned up, the remaining receipt can resolve redeliveries.

**Important:** this example is a synchronous/in-memory flow for learning mechanics. Never use it as a production implementation without adding **a persistent store, trusted tenant context, transactional claim publishing, secure token format, durable completion ledger, error channels, bounded retries, monitoring, and remote idempotency**.

### 10.4. How to use native Claim Check In/Out?

When choosing dedicated Claim Check transformers over a custom service, the architecture is:

~~~text
input
  -> Claim Check In Transformer (store original Message)
  -> claim token channel
  -> Claim Check Out Transformer
       lookup message by claim token
       preserve-or-remove per configuration
  -> business handler
~~~

When checking Java DSL against your exact Spring Integration dependency, verify:

- **Token type:** Message ID/UUID or another ID type?
- **Store:** do Claim Check In/Out use the exact same `MessageStore` instance/logical backing store?
- **Remove behavior:** does Claim Check Out keep messages for retries or delete on read?
- **Header merge:** how are original headers and token-envelope headers combined?
- **Error behavior:** what exception or status does a missing claim raise?
- **Transaction:** do claim-out and downstream join the same transaction when needed?
- **TTL/persistence:** do claims survive restarts and the retry horizon?

Never mix a native `ClaimCheckOutTransformer` with a service expecting a differently shaped `ClaimTicket` without an adapter mapping. Demo tokens and framework tokens **are not automatically compatible**.

## 11. Integration tests for the Spring Integration flow

### 11.1. Issue → Process → Redeliver same token

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(ClaimRetryFlowConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ClaimRetryIntegrationTest {

    @Autowired
    ClaimPaymentGateway gateway;

    @Autowired
    FakeIdempotentPaymentGateway payments;

    @Test
    void retrySameClaimReturnsSameBusinessReceipt() {
        ClaimTicket ticket = gateway.issue(
                new ClaimSubmission(
                        new OrderPayload(
                                "ORD-7", "C-7",
                                new BigDecimal("8500000")),
                        "PAY-ORD-7",
                        "TENANT-A"));

        ClaimAttempt attempt = new ClaimAttempt(
                ticket, "TENANT-A");

        OperationReceipt first = gateway.process(attempt);
        OperationReceipt retry = gateway.process(attempt);

        assertEquals(first, retry);
        assertEquals("SUCCESS", retry.status());
        assertEquals(1, payments.committedOperations.get());
    }
}
~~~

The test traverses **Gateway → Spring Integration Transformer/Handler → claim repository → fake payment**. It is stronger than unit testing the service alone, yet **does not cross a broker or native Claim Check Transformer**. Dedicated adapter integration tests are needed for those components.

### 11.2. Claim cleaned up after completion; duplicates can still return receipt

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringJUnitConfig(ClaimRetryFlowConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ClaimCleanupRedeliveryIntegrationTest {

    @Autowired
    ClaimPaymentGateway gateway;

    @Autowired
    RetryableClaimService claims;

    @Autowired
    ClaimRepository store;

    @Autowired
    FakeIdempotentPaymentGateway payments;

    @Test
    void completedOperationCanAnswerAfterClaimDeleted() {
        ClaimTicket ticket = gateway.issue(
                new ClaimSubmission(
                        new OrderPayload(
                                "ORD-8", "C-8",
                                new BigDecimal("2000000")),
                        "PAY-ORD-8",
                        "TENANT-A"));

        ClaimAttempt attempt = new ClaimAttempt(
                ticket, "TENANT-A");
        OperationReceipt first = gateway.process(attempt);

        claims.cleanupAfterConfirmed(ticket);
        assertFalse(store.find(ticket.claimId()).isPresent());

        OperationReceipt repeated = gateway.process(attempt);
        assertEquals(first, repeated);
        assertEquals(1, payments.committedOperations.get());
    }
}
~~~

**Why `@DirtiesContext`?** The repository, ledger, and fake payment keep state in Spring beans. Each test needs an isolated context or explicit reset; otherwise tests depend on run order or bleed state into one another.

### 11.3. Negative integration test: claim taken away before completion

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(ClaimRetryFlowConfiguration.class)
class ClaimLostBeforeCompletionIntegrationTest {

    @Autowired
    ClaimPaymentGateway gateway;

    @Autowired
    ClaimRepository store;

    @Test
    void consumedClaimWithoutReceiptMustNotCharge() {
        ClaimTicket ticket = gateway.issue(
                new ClaimSubmission(
                        new OrderPayload(
                                "ORD-9", "C-9",
                                new BigDecimal("1000000")),
                        "PAY-ORD-9",
                        "TENANT-A"));

        store.take(ticket.claimId());

        assertThrows(RuntimeException.class, () ->
                gateway.process(
                        new ClaimAttempt(ticket, "TENANT-A")));
    }
}
~~~

An integration endpoint may wrap exceptions in `MessageHandlingException` or another messaging exception type; thus the example catches `RuntimeException` to avoid coupling to one specific wrapper. A thorough test should check **the cause chain contains `NOT_FOUND`** and verify the fake payment **was never called**.

## 12. Placing retries in the wrong spot can invalidate the claim

### 12.1. Retrying *only* downstream vs retrying the whole flow

Compare two designs:

~~~text
Option A:
  claim out (remove=true)
    -> keep payload in memory for this execution
    -> retry HTTP request 3 times

Option B:
  retry( claim out(remove=true) -> HTTP request )
    -> attempt 1: claim out deletes payload, HTTP times out
    -> attempt 2: claim out reports NOT_FOUND
~~~

In **Option A**, HTTP retries within **the same execution context** can keep using the restored payload even though the store no longer holds the claim. Yet if the process crashes or the broker redelivers, the in-memory payload is lost too; recovery can still fail.

In **Option B**, the retry re-runs claim-out itself and hits “claim already used” immediately. The two options **are not equivalent**, even though both mention “retry 3 times.”

### 12.2. Retry boundaries must be designed

| Retry scope | Repeats claim-out? | Risk |
|---|---|---|
| Only HTTP/payment client after restore | No within one attempt. | Crash loses payload if claim was consumed. |
| Advice around payment handler | No if claim-out sits in an earlier endpoint. | Needs proper handler transactions/acks. |
| Advice around claim-out transformer | Yes. | One-time claims can be consumed on the very first attempt. |
| Broker redelivery from token topic | Can rerun the whole chain. | Missing claim after removal; needs completion/restore policy. |
| Gateway request retry from original input | Can mint a new claim. | Duplicate business operation/side effects without idempotency. |

**`RequestHandlerRetryAdvice`** is one Spring Integration option for retrying a corresponding endpoint, though exact configuration must match framework version and endpoint semantics. Before attaching advice, identify **which method it wraps**, **which exceptions are retryable**, and **which side effects may already have committed**.

### 12.3. Distinguishing retryable errors

| Error code or situation | Retry same token immediately? | Action |
|---|---|---|
| Payment service temporarily unavailable; reusable claim exists | Yes, bounded. | Backoff + idempotency + deadline. |
| Claim store temporarily unavailable | Yes once store recovers. | Never misclassify as missing claim. |
| `NOT_FOUND` after one-time consumption | Usually useless. | Check completion, tombstones, replay source. |
| `EXPIRED` | Not with old token. | Reauthorize/reissue if policy allows. |
| `ALREADY_CONSUMED` with tombstone | Not with same claim. | Query operation state; new replay if permitted. |
| `ACCESS_DENIED` | No. | Halt; audit/security response. |
| `INVALID_TICKET` or malformed payload | Never retry infinitely. | Quarantine/producer validation error. |
| Charge committed yet reply lost | Never blindly charge twice. | Reconcile/idempotency key. |
| Gateway reply timeout | Does not prove downstream did not process. | Query status/reconcile before retrying. |
| Store full / DB deadlock | Possibly transient. | Bounded retry, backpressure, and alerts. |

**Never retry by catching every `RuntimeException` and looping indefinitely.** Classify errors first, set max attempts/deadlines, inspect operation state, and provide a recovery path.

### 12.4. Recovery must never fabricate success

A recovery flow may return one of these states:

~~~text
CLAIM_RETRY_SCHEDULED
CLAIM_ALREADY_COMPLETED
CLAIM_REPLAY_AUTHORIZATION_REQUIRED
CLAIM_EXPIRED
CLAIM_NOT_FOUND
CLAIM_REVOKED
CLAIM_QUARANTINED
OPERATION_OUTCOME_UNKNOWN
~~~

**None of these states defaults to `PAYMENT_SUCCESS`.** Only an authoritative payment source/completion ledger can confirm the operation completed.

## 13. Transactions: saving claim, publishing token, and acknowledging

### 13.1. Dual-write at claim-in

Creating a claim involves two logical steps:

~~~text
1. Persist original Message in Claim Store
2. Publish ClaimToken to message broker
~~~

Failure windows exist:

| Crash timing | Consequence |
|---|---|
| Before saving payload | No claim/token exists. |
| After saving payload, before publishing token | Leaves an **orphan claim** nobody receives. |
| Token published yet store write not durable | Consumer receives token yet cannot find payload. |
| After publish, before producer receives ack | Producer may republish token, creating duplicates. |

If the database and broker do not share an appropriate transaction, **never assume the two steps are atomic**. A common option is the **transactional outbox**:

~~~mermaid
flowchart LR
    A[Receive original] --> TX[DB Transaction]
    TX --> S[(Stored Claim)]
    TX --> O[(Outbox token record)]
    O --> RELAY[Outbox Publisher]
    RELAY --> B[(Broker)]
    B --> C[Claim Consumer]
~~~

When both the claim record and outbox record are written in one **DB transaction**, a crash may cause the publisher to resend, yet **never emits a token pointing to an uncommitted claim** per the outbox contract. Consumer deduplication is needed since the outbox relay may publish duplicates.

### 13.2. Transactions at claim-out

With one-time consumption, ideally you might want:

~~~text
begin transaction
  read and mark claim used
  process downstream
  record completion
commit
~~~

Yet not every HTTP payment or Kafka broker joins the same transaction. **A claim store commit cannot roll back an external payment already committed.** With multiple resource managers, use idempotency, sagas/compensation, or reconciliation; never treat transaction annotations as an atomic promise across external services.

### 13.3. Deleting the claim after completion can also fail

Suppose payment succeeds, then `delete(claimId)` fails because the DB is unavailable. Never **mark the payment failed and charge again** just because cleanup failed.

A better design:

~~~text
Payment outcome: SUCCESS, durable receipt
Cleanup job:     PENDING_DELETE

If cleanup fails:
  retry cleanup by job ID
  keep business receipt SUCCESS
  never charge again
~~~

Cleanup is a separate lifecycle action with its own retries and monitoring. If sensitive data requires timely deletion, alert and recover stuck cleanups—never let deletion status overturn a confirmed business outcome.

### 13.4. Atomic consumption does not equal atomic business processing

A repository may support **atomic read-and-delete**, ensuring only one worker gets the payload. However:

~~~text
Worker A: atomic take succeeds
Worker A: crashes before payment
Worker B: retries and sees claim is gone
~~~

Atomic consumption only stops **two workers from taking the same claim**; it does not fix **payload loss after a worker crash**. For safer at-least-once processing, consider **leases**:

~~~text
AVAILABLE -> LEASED(to worker A, until T)
LEASED -> COMPLETED (payment committed)
LEASED -> AVAILABLE (lease expired, recovery approved)
~~~

Yet leases also require **fencing tokens/attempt generations** so a stalled old worker cannot commit after the lease was reassigned to a new worker. Never equate lease timeout with certainty that Worker A has stopped.

## 14. Concurrency: two workers retrying the same claim

### 14.1. Race between two consumers

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant S as Claim Store
    participant P as Payment API
    A->>S: restore C-100
    B->>S: restore C-100
    S-->>A: Order payload
    S-->>B: Order payload
    A->>P: charge PAY-100
    B->>P: charge PAY-100
    Note over P: Must recognize stable idempotency key
~~~

A reusable claim lets both workers read the payload — which is what enables retries — yet **does not prevent concurrent payment calls on its own**.

### 14.2. Picking the locking point by operation

Components can coordinate via:

1. **Durable operation ledger** with unique key `(tenantId, operationId)`.
2. **Operation fingerprint** preventing reuse of the same ID for different payloads.
3. **In-progress lease** coordinating workers for a bounded period.
4. **Fencing/versioning** blocking a stale-lease worker from overwriting state after a newer worker.
5. **Payment idempotency key** right at the external side-effect boundary.
6. **Reconciliation** with the external service when commit status is uncertain.
7. **Cleanup** only after the final outcome is known, with sufficiently aged tombstones.

Even a standalone distributed lock can lose exclusivity during GC pauses or network partitions; never skip fencing/idempotency.

### 14.3. Two different payloads for the same operation ID

If Worker A holds `amount=5_000_000` while Worker B receives a new claim with the same `operationId` yet amount `8_000_000`, never blindly “deduplicate as success.” A completion ledger should store a **payload fingerprint** and reject requests carrying the same operation ID with differing business content.

~~~text
key = (TENANT-A, PAY-ORD-1)
storedFingerprint = sha256(canonical business payload v1)

retry request:
  same operation key
  same fingerprint -> may return previous receipt
  different fingerprint -> OPERATION_CONFLICT
~~~

When hashing payloads, define **canonicalization** first (schema version, numbers, timezones, field order, Unicode) rather than relying on a Java object's `toString()`. Never use fingerprints in place of authorization.

## 15. TTL, retention, and tombstones after claim-out

### 15.1. Claim TTL must not be accidentally shorter than the retry horizon

~~~text
Claim TTL:        5 minutes
Broker max retry: 30 minutes
Error recovery:   2 hours
~~~

If the claim is deleted after 5 minutes, a retry at minute 15 lacks data. Address this by:

- Increasing TTL to cover the **retry horizon** and security rules.
- Separating **active claim retention** from **replay archive retention**.
- Allowing authorized reissue from a durable source instead of stretching TTLs forever.
- When a claim nears expiry, making an explicit decision: **controlled extension** or halt retries/quarantine.

### 15.2. Do not keep every claim forever

Reusable claims help retries, yet keeping everything forever creates cost and data risk:

| Issue | Measure |
|---|---|
| Payload contains PII | Encryption, minimization, access control, retention. |
| Orphan claim never published token | Scan overdue records and check outbox/recovery. |
| Completed claim | Clean up after retention/audit window. |
| Revoked claim | Block reads immediately, clean up per policy. |
| Active claim with no consumer | Backlog/claim-age alerts, admission control. |
| Claim still in use when TTL ends | Explicit in-progress/lease/deadline states. |
| Store runs out of space | Capacity alerts and backpressure; never drop silently. |

### 15.3. Tombstones are not original data

To distinguish `ALREADY_USED` from `NOT_FOUND`, keep minimal metadata after deleting the payload:

~~~json
{
  "claimId": "C-100",
  "operationId": "PAY-ORD-1",
  "tenantId": "TENANT-A",
  "state": "COMPLETED",
  "completedAt": "2026-01-01T00:00:00Z"
}
~~~

This is an **illustrative application-designed schema**, not a record auto-generated by Spring Integration `MessageStore` in every setup.

Tombstones help:

- Identify used/closed claims.
- Stop a late token from reviving an already-finished group.
- Locate operation receipts without retaining full payloads.
- Apply separate retention policies to large payloads vs metadata.

Yet a tombstone **is not enough to rerun business logic** once the original payload is deleted. If the data is gone, you need another valid replay source or must return an unrecoverable status.

### 15.4. Token revocation is a distinct state

When Claim Check restricts access to sensitive data, a claim marked **REVOKED** for fraud/security must not be reissued merely because a consumer requested a retry. Reissue policies must inspect the revocation reason and current permissions; this is completely different from a claim **EXPIRED** due to time.

## 16. Combining Claim Check with Enterprise Integration Patterns

### 16.1. Filter after claim-in can create orphan claims

~~~mermaid
flowchart LR
    P[Original payload] --> C[Claim In]
    C --> F{Filter token}
    F -->|Accepted| Q[(Queue)]
    F -->|Rejected| D[Discard]
    C --> S[(Claim Store)]
    D -.-> O[Orphan claim without cleanup]
~~~

If a Filter rejects a token **after** the payload was saved, no consumer may ever fetch the claim. This is not a Claim Check Out bug, yet it creates unused data lingering until TTL.

Options:

- Place **validation/eligibility Filters before claim-in** whenever required fields already exist on the original.
- If filtering must happen on token metadata, design cleanup on the rejected branch with proper auditing.
- Track claims issued whose tokens were never accepted/processed.
- Use outbox/state machines to spot orphan claims after crashes.

Never delete a claim immediately when one Filter drops a token if **other branches still need the same claim**; token ownership policies must be clear.

### 16.2. Router selecting branches does not make a token multi-use

A Content-Based Router can steer the same claim through different handlers by `orderType` or `region`:

~~~text
ClaimToken C-100
  -> Router
      -> domestic handler
      -> international handler
~~~

If the Router picks **one** branch, a one-time claim may fit a single-consumer contract. Yet if a branch fails and gets rerouted, or the same token is sent to multiple recipients, check whether the claim can be read again.

**Router does not guarantee the original data remains available**, and Claim Check does not pick routes; the two patterns have separate responsibilities.

### 16.3. Scatter–Gather and Recipient List: one claim, multiple readers

This is a classic design trap:

~~~mermaid
flowchart TD
    C["ClaimToken C-100"] --> S{Scatter}
    S --> I[Inventory check]
    S --> F[Fraud check]
    I --> OI[Claim Out]
    F --> OF[Claim Out]
    OI --> STORE[(Message Store)]
    OF --> STORE
    OI -->|First read-and-remove| OK[Inventory gets payload]
    OF -->|Reads after removal| FAIL[Fraud missing claim]
~~~

If two recipients share **the same one-time token**, only one branch gets the original under a read-and-remove design. Valid approaches:

1. **Reusable claim** while recipients and retries still need to read, cleaning up after Gather/operation completion.
2. **Separate claim per recipient** when branches should not share retrieval rights; each claim gets its own scope/TTL.
3. **Restore before Scatter**, then distribute payloads per recipient contract and permissions (mind security and payload size).
4. **Extract per-recipient projections** at a trusted source instead of letting everyone read full sensitive data.

Never assume placing one `claimCheckOut` on each branch is safe without testing concurrent readers and removal policies.

### 16.4. Splitter/Aggregator and small claims per child

A large batch may be split into items, each checked in separately:

~~~text
Batch ORD-1
  -> Splitter
      -> Item #1 -> claim C-1
      -> Item #2 -> claim C-2
      -> Item #3 -> claim C-3
  -> per-item retry
  -> Aggregator
~~~

If `C-2` was already consumed yet handler #2 fails, per-item retries must still be able to restore #2 or use a replay source. Meanwhile the Aggregator needs:

- Batch `correlationId`.
- `sequenceNumber`/`sequenceSize` or business item identity.
- Outcomes for every item, including rejected/failed ones per contract.
- Timeout rules if a claim cannot be restored.
- Distinction between a duplicate item reply and a missing item.

**Never let a deleted claim cause an Aggregator to wait forever without an error/timeout outcome.**

### 16.5. Resequencer buffering tokens too long can expire claims

~~~text
T0 Claim In: C-1, C-2, C-3 (TTL 5 minutes)
T1 Token C-3 arrives at Resequencer first, buffered
T2 Token C-2 missing, group waits > 5 minutes
T3 C-2 arrives, Resequencer releases C-2 and C-3
T4 Claim Out on C-3 -> EXPIRED
~~~

The Resequencer **fulfilled its ordering duty**, yet Claim Check Out still fails to restore the payload because of TTL. When pairing these patterns:

- Estimate buffer/gap/retry times relative to claim TTL.
- Size retention to acceptable worst-case delays or maintain a durable replay source.
- Handle **expired while buffered** states with a quarantine path.
- Never keep claims forever just to dodge timeouts.
- Never assume proper release order guarantees original data is still there.

### 16.6. Content Enricher and mutated claim data

If a Content Enricher fetches the original and adds customer details, never overwrite the data stored under the old claim with a brand-new payload lacking version/provenance:

~~~text
Stored original at Claim C-100
  original order payload

Enrichment result
  {original: ..., profile: ..., enrichedAt: ...}
~~~

Keep **original** and **enrichment** separate or create a new claim/version per contract. For retries, decide whether to reuse **the prior attempt's enriched snapshot** or re-look up current state.

### 16.7. Gateway timeout does not mean the claim was cleaned up

An HTTP/Gateway caller may hit `replyTimeout` while a broker worker keeps processing the claim:

~~~text
Caller -> Gateway -> Token C-100 -> queue
Gateway timeout at 3s
Worker completes payment at 7s
~~~

When the caller resends:

- Never create a new charge if the prior operation already committed.
- Check the completion ledger before restoring payload/issuing a new claim.
- Return `PENDING`/`COMPLETED`/`UNKNOWN` or the receipt per API contract.
- If the claim was consumed, distinguish consumed from operation failed.

## 17. Headers, correlation, and serialization when restoring messages

### 17.1. Original payload differs from original message

Claim Check can store a **Spring `Message<?>`** with both payload and headers; a custom implementation may store only **the payload** and selected metadata. The two options are not equivalent.

Example original:

~~~text
payload: OrderPayload
headers:
  traceId: T-100
  correlationId: ORD-1
  replyChannel: (internal MessageChannel)
  errorChannel: (internal MessageChannel)
~~~

After claim-in, the token message may receive a new **`MessageHeaders.ID`**, and after claim-out the framework may reconstruct/restore the message with headers per specific semantics. Verify **which headers are preserved, merged, overridden, or dropped**, especially across multiple adapters.

### 17.2. Never reuse a dead JVM's replyChannel

`replyChannel`/`errorChannel` in Spring Integration can hold internal channel references. They are not wire-portable addresses for Kafka/JMS/HTTP. If a message is stored long-term and read back in another JVM:

- Do not serialize and expect an old `MessageChannel` object to keep working.
- Design transport-appropriate **reply destinations** and error routes.
- Keep `requestId`/`correlationId` as portable metadata, not object pointers.
- Test header mapping across serialization/deserialization and version upgrades.
- If tokens change identity, never confuse the original message ID with the claim ID or current retry delivery ID.

### 17.3. Correlation when minting a new claim

If an operator reissues claim `C-200` from `C-100`'s source:

~~~text
business orderId = ORD-1
operationId      = PAY-ORD-1
old claimId      = C-100
new claimId      = C-200
replayAttemptId  = A-2
~~~

Each ID has its own role:

| ID | Meaning | Keep or change on replay? |
|---|---|---|
| `orderId` | Original order. | Keep for the same business order. |
| `operationId` | Operation with side effects to deduplicate. | Keep when retrying same operation; change only for genuinely new operation. |
| `claimId` | Store payload lookup key. | Change if reissuing a new claim. |
| `replayAttemptId` | Retry/replay attempt. | Change per intentional attempt. |
| `traceId` | Observes one call chain. | May be new, yet linked to old operation. |
| `correlationId` | Groups messages in flow. | Per group contract; never randomize arbitrarily. |

### 17.4. How should raw data be stored?

If business rules demand **byte-for-byte replay**, storing a parsed `OrderPayload` DTO may fall short: converters can alter whitespace, unknown fields, timezones, or numeric scales. Define:

- **Exact raw-event replay:** store wire payload with integrity hash and schema version.
- **Semantic replay:** store canonical DTO/business fields plus policy/lookup versions.
- **Event-sourced replay:** rebuild state from verified event logs.

Each option carries different retention, cost, and data-access profiles; never assume a tiny claim token automatically preserves a “byte-exact original request.”

## 18. Claim security during retries

### 18.1. Claim tokens must be protected like data references

A predictable claim ID like `C-1, C-2, C-3` invites **enumeration** if the claim-out endpoint lacks access control. In the code example, `UUID.randomUUID` makes IDs harder to guess, yet **is not enough to replace authentication/authorization**.

Measures:

1. Use high-entropy tokens/IDs with minimal scope.
2. Verify tenant/owner/permissions from an **authenticated principal**.
3. Enforce TTLs, revocation, and rate limits.
4. Encrypt data at rest and in transit per policy.
5. Keep sensitive tokens out of URL queries, logs, and uncontrolled analytics.
6. Prevent unnecessary recipients from reading the full original.
7. On retries, **re-verify permissions at re-read time**, not only at claim-in.
8. Audit accesses using reference/masked IDs rather than raw tokens.

### 18.2. Retries must not bypass access controls

Suppose an employee loses permission to view order data after the first claim-out. A retry running with the same old token **must not use that token to bypass updated permission policies** if reauthorization is required.

Likewise, for authenticated machine-to-machine retries, track which worker/tenant is authorized to process the claim. A revoked token cannot be “fixed” by copying data from a private cache and minting another token.

### 18.3. Tokens and metadata in error channels

`ErrorMessage` can carry `Throwable` and details about the failed message depending on execution context. If the failed message carries a claim token, logging the full exception chain can leak the ID used to access the payload.

Prefer logging:

~~~text
event=CLAIM_RESTORE_FAILED
  operationRef=PAY-ORD-1
  claimRefHash=...
  tenantScope=TENANT-A
  code=EXPIRED
  retryable=false
~~~

This is a suggested log schema, not Spring Integration's default log output. If retention/forensics require storing more, restrict access and never dump sensitive payloads recklessly.

## 19. Observability: distinguishing used claims from completed operations

### 19.1. Milestones to observe

~~~text
event=CLAIM_ISSUED
  operationId=PAY-ORD-1 claimRefHash=...
  ttlSeconds=900

event=CLAIM_RESTORED
  operationId=PAY-ORD-1 attempt=1
  removeOnRead=false

event=BUSINESS_ACTION_STARTED
  operationId=PAY-ORD-1 attempt=1

event=BUSINESS_ACTION_OUTCOME_UNKNOWN
  operationId=PAY-ORD-1 reason=REMOTE_REPLY_TIMEOUT

event=CLAIM_RESTORED
  operationId=PAY-ORD-1 attempt=2
  removeOnRead=false

event=BUSINESS_ACTION_RECONCILED
  operationId=PAY-ORD-1 status=COMPLETED

event=CLAIM_CLEANUP_COMPLETED
  operationId=PAY-ORD-1 claimRefHash=...

event=CLAIM_REDELIVERED
  operationId=PAY-ORD-1 attempt=3
  handling=RETURN_EXISTING_RECEIPT
~~~

**These are suggested application events**, not framework-provided log lines. They separate the **claim lifecycle** from the **business operation lifecycle**.

### 19.2. Layered metrics

| Illustrative metric | What does it measure? |
|---|---|
| `claim_issued_total` | Newly created claims. |
| `claim_restore_total{result}` | Successful/failed restores by error code. |
| `claim_consumed_total` | Claims consumed under one-time mode. |
| `claim_expired_total` | Expired claims detected. |
| `claim_missing_total` | Claims missing in store. |
| `claim_reissued_total` | Approved new claims minted for replay. |
| `claim_cleanup_pending` | Claims awaiting cleanup. |
| `claim_cleanup_failed_total` | Cleanup errors potentially violating retention. |
| `claim_payload_bytes` | Payload sizes stored/read. |
| `claim_store_latency_seconds` | Store read/write latency. |
| `claim_store_errors_total{reason}` | DB timeouts, unavailability, capacity, serialization... |
| `operation_completed_total` | Business operations confirmed complete. |
| `operation_duplicate_prevented_total` | Retries/redeliveries handled without repeating side effects. |
| `operation_outcome_unknown_total` | Executions needing reconciliation. |
| `claim_retry_exhausted_total` | Retries exhausted without recovery. |
| `claim_orphan_age_seconds` | Age of claims lacking consumers/outcomes. |

These metric names are **suggestions**. Check Spring Integration/Micrometer default meters for your version to avoid double-counting semantics. Never use `claimId`, `operationId`, or `customerId` as high-cardinality metric labels; use access-controlled logs/traces.

### 19.3. How to interpret a signal

| Signal | What can be concluded | What cannot yet be concluded |
|---|---|---|
| Claim issued | Attempted to create a reference. | Token was successfully delivered by broker. |
| Claim restored | Payload found and validated/authorized per contract. | Payment committed. |
| Claim consumed | Token is no longer readable per policy. | Business operation succeeded. |
| Completion ledger shows SUCCESS | Receipt exists per ledger contract. | Remote side effect definitely never repeated if ledger is untrusted. |
| Cleanup succeeded | Payload deleted from target store. | All replicas/caches/backups cleared retention. |
| Broker ack succeeded | Transport recorded ack per configured semantics. | Zero duplicates across the whole system. |

### 19.4. Message History and provenance

Spring Integration Message History can show which Claim Check In/Out, Transformer, Router, Gateway, or handler a message passed through when tracking is enabled. Yet it **does not by itself tell you**:

- Whether the claim was actually deleted from `MessageStore`.
- Whether the target system committed the payment.
- Whether the completion ledger matches the remote side effect.
- Whether the claim was read by another tenant.
- Which retry reused an old claim vs reissued a new claim per policy.

Therefore combine **claim metadata, operation ledgers, transport status, structured logs, traces/correlation, and audit stores** instead of relying on Message History alone.

## 20. Test matrix for already-used claims and retries

| ID | Scenario | Expected outcome | What must never happen |
|---|---|---|---|
| CC-01 | Valid original claim-in | Store holds original, valid token returned. | Token pointing to missing record. |
| CC-02 | First reusable claim-out | Exact payload returned, record retained. | Premature deletion. |
| CC-03 | Second reusable claim-out | Same data returned per contract. | Unexpected `NOT_FOUND`. |
| CC-04 | First one-time `take` | Payload returned and consumed. | Two callers both getting payload from atomic store. |
| CC-05 | Retry token after one-time consume | `NOT_FOUND`/`ALREADY_USED` per metadata. | Fabricating a new payload. |
| CC-06 | Downstream error before commit, reusable claim intact | Retry restores payload again. | Claim deleted in `finally`. |
| CC-07 | Downstream committed, reply lost | Reconcile/idempotency returns prior receipt. | Blindly charging twice. |
| CC-08 | Claim cleaned up post-completion, broker redelivers | Completion ledger returns existing result. | Attempting restore then charging again. |
| CC-09 | Claim missing, no receipt | Fail closed/reconcile/quarantine. | Groundlessly declaring SUCCESS. |
| CC-10 | Token expired while record still exists | `EXPIRED`, no payload returned. | Bypassing TTL on retry. |
| CC-11 | Store TTL already deleted record | `NOT_FOUND` or tombstone-specific status. | Treating error as payment success. |
| CC-12 | Revoked token | Access denied per policy. | Reissuing to bypass revocation. |
| CC-13 | Another tenant uses token | `ACCESS_DENIED`. | Leaking original payload. |
| CC-14 | Valid claim ID with swapped `operationId` | Detect mismatch. | Using claim to run a different operation. |
| CC-15 | Malformed claim data | Validation failure. | Sending corrupt payload to payment. |
| CC-16 | Claim Store temporarily unavailable | Retryable infrastructure error. | Converting to permanent `NOT_FOUND`. |
| CC-17 | Claim Store full | Backpressure/alerts/recovery. | Silently dropping tokens or payloads. |
| CC-18 | Claim-in persisted yet token unpublished | Orphan detection/outbox recovery. | Retaining forever with no owner. |
| CC-19 | Token published yet claim uncommitted | Outbox/transaction prevents contract violation. | Consumer receiving dangling token. |
| CC-20 | Outbox relay publishes same token twice | Consumer idempotency works. | Two side effects. |
| CC-21 | Two workers concurrently use reusable claim | Operation idempotency/fencing. | Two independent charges. |
| CC-22 | Two workers atomic-take one-time claim | At most one worker gets payload. | Both consuming. |
| CC-23 | Worker atomic-takes then crashes before commit | Recovery marks claim consumed/outcome unknown. | Declaring success. |
| CC-24 | Two different claims with same `operationId` | Deduplicate/reconcile by operation. | Two business charges. |
| CC-25 | Two claims sharing `operationId` with different payloads | `OPERATION_CONFLICT`. | Reusing receipt from different payload. |
| CC-26 | Gateway retry hits timeout | Query operation status. | Assuming worker canceled. |
| CC-27 | Filter drops token after claim-in | Cleanup/orphan handling. | Keeping claim forever. |
| CC-28 | Scatter to two recipients with same one-time claim | Flawed design detected; change policy. | Only fastest branch gets payload yet all report success. |
| CC-29 | Splitter with 3 items, one claim consumed | Outcome/error lets Aggregator release properly. | Waiting forever for missing part. |
| CC-30 | Resequencer buffers token past TTL | Expiration/quarantine/reissue per policy. | Releasing stale token and claiming success. |
| CC-31 | Header mapping across broker | Claim identity, correlation, tenant policy preserved. | Serializing JVM `replyChannel` or losing IDs. |
| CC-32 | Group/operation restart after crash | Durable store + ledger recover cleanly. | Silent data loss. |
| CC-33 | Cleanup job fails after business SUCCESS | Retry cleanup separately. | Charging again due to cleanup failure. |
| CC-34 | Oversized claim / too many claims | Size/capacity controls. | OOM or store exhaustion. |
| CC-35 | Redelivery after tombstone retention | Replay horizon policy defined. | Treating late token as brand-new operation. |
| CC-36 | Retry after tenant permissions revoked | Reauthorization from trusted principal. | Fetching payload via old token. |
| CC-37 | Test same claim across two JVMs | Real consistent store & idempotency. | Trusting only an in-memory fake map. |
| CC-38 | Parallel retry where one attempt fails late | State machine/versioning protects completed outcome. | Stale error overwriting SUCCESS. |
| CC-39 | Completion ledger stale or unavailable | Never auto-create duplicate charge. | Guessing success/not-found. |
| CC-40 | Backups/replicas retain payload post-cleanup | Proper retention/data-deletion policy. | Assuming data is erased everywhere. |

### 20.1. Which layer to test at?

| Test level | Value | Insufficient to prove |
|---|---|---|
| **Claim repository/service unit test** | Restore, take, TTL, tenant, missing errors. | Real DB/transport, survival across restarts. |
| **Workflow/ledger unit test** | Retry behavior and fake idempotency. | Real remote API duplicate handling. |
| **Spring Integration test** | Gateway, Transformer, reply/error paths, channels. | Broker ack/redelivery if no broker is used. |
| **Adapter integration test** | Store/broker headers, serialization, retry advice scope. | Real remote payment if mocked. |
| **System/recovery test** | Crash windows, replay, outbox, cleanup, reconciliation. | Un-tested production failure modes. |
| **Security test** | Tenant authorization, token guessing, expiry, revocation. | All access risks without trust-boundary review. |

Include at least one test at every layer **your production guarantees truly depend on**. Never feel fully confident just because an in-memory `ConcurrentHashMap` deduplicates one operation inside one JVM.

## 21. Diagnostic runbook: retry reports “claim not found”

A consumer logs:

~~~text
CLAIM_RESTORE_FAILED
  operationId=PAY-ORD-1
  code=NOT_FOUND
  deliveryAttempt=2
~~~

Investigate systematically:

1. **Validate token:** are `claimId`, operation ID, and tenant/group ID right? Did an adapter alter the message?
2. **Check operation status:** does the completion ledger or remote service hold a success receipt? If so, handle as duplicate instead of recharging.
3. **Inspect claim lifecycle:** when was the token issued; was it consumed, revoked, or expired?
4. **Check remove-on-get:** did Claim Check Out delete on the first read? Which segment is retrying?
5. **Check Message Store:** is it pointing to the right datasource/schema/shard/node? Is the store in-memory and did the process just restart?
6. **Check outbox/commit:** was the token published before the original record committed?
7. **Check TTL:** is retry delay + queue backlog + group buffering longer than retention?
8. **Check races:** did another worker take/delete the claim or did cleanup purge early?
9. **Check error handling:** was a store-unavailable error mis-mapped to `NOT_FOUND`?
10. **Check data origin:** is there an authorized, schema-versioned, checksum-verified replay source?
11. **Pick recovery:** return existing receipt, retry restore once store recovers, reissue per policy, quarantine, or investigate manually.
12. **Add regression test:** reproduce the exact failure window and monitor missing/consumed/replay metrics.

### 21.1. Distinguishing three commonly conflated cases

~~~text
Case A:
  claim missing + operation completed
  -> duplicate success acknowledgement / existing receipt

Case B:
  claim missing + operation unknown + replay source trusted
  -> reconcile, authorize, possibly reissue

Case C:
  claim missing + operation unknown + no replay source
  -> blocked/quarantine/manual action
  -> NEVER fabricate fake success
~~~

Never fix a `NOT_FOUND` error merely by bumping retry counts: once a claim is permanently deleted, retrying 100 times will never make the record reappear. Find the root cause and a valid recovery source.

## 22. Common pitfalls

| Pitfall | Consequence | Proper design |
|---|---|---|
| “Claim Check Out succeeded means payment succeeded.” | Deletes payload before downstream commits. | Separate read, completion, and cleanup. |
| “One-time claims can still retry the same token endlessly.” | Next attempt lacks payload. | Pick reusable or explicit replay source. |
| “Just wrap the whole flow in retry advice.” | Repeats claim-out after removal and hits `NOT_FOUND`. | Scope retries to the right endpoint. |
| “Claim ID and operation ID are the same thing.” | Minting a new claim bypasses deduplication. | Use a stable business idempotency key. |
| “Unpredictable claim ID needs no authorization.” | Data leak if token leaks/guessed/misrouted. | AuthN/AuthZ, tenant, scope, TTL. |
| “In-memory Message Store is durable.” | Restarts lose payloads even when tokens were emitted. | Persistent store/ack/recovery when needed. |
| “Read-and-remove is a payment transaction.” | Crash after consume kills retries. | Use idempotency/leases/reconciliation. |
| “Timeout means payment did not commit.” | Retries can double-charge. | Query remote status/idempotency. |
| “Writing completion ledger after charge is always safe.” | Crash between the two leaves state `UNKNOWN`. | Remote idempotency + reconcile/outbox/inbox. |
| “With a ledger, no need to check payload.” | Two different payloads share one operation key. | Operation fingerprints/conflict detection. |
| “Two workers can read the claim but cannot process together.” | Two concurrent side effects. | Operation states + remote idempotency/leases. |
| “Once claim is deleted on success, all retries must error.” | Valid duplicates wrongly fail. | Check completion before claim-out. |
| “`NOT_FOUND` always means `CONSUMED`.” | Masks store/shard/issue bugs or forged tokens. | Tombstones and typed state classification. |
| “Expired claims just need automatic extension.” | Violates current retention/authorization. | Reauthorize/reissue per policy. |
| “Revocation can be ignored on retry.” | Violates access control. | Block and audit; never reissue blindly. |
| “Same one-time token works for multiple Scatter recipients.” | Only the first reader gets the original. | Reusable or separate scoped claims. |
| “Resequencer releasing token means claim is unexpired.” | Token may expire while buffered. | Align TTL with gap/retry horizon. |
| “Filter dropping token needs no cleanup.” | Orphan claims hoard useless data. | Cleanup/TTL/orphan monitoring. |
| “Cleanup job failure requires rerunning payment.” | Causes duplicate side effects. | Retry cleanup independently. |
| “Deleting from primary erases every copy.” | Backups/caches still hold data. | Retention/replica/data-deletion policies. |
| “Having `errorChannel` repairs all missing claims.” | Poison tokens retry endlessly. | Coded recovery policies and durable replay sources. |
| “Message History tells us whether claim was deleted.” | History does not replace DB lifecycles. | Separate claim/ledger audits. |
| “All original `MessageHeaders` are safe to send to another JVM.” | `replyChannel`/`errorChannel` stale or non-serializable. | Intentional header mapping and wire metadata. |
| “Happy-path integration test is enough.” | Misses consume-before-failure/restart races. | Tests for failure windows and duplicates. |

## 23. Practice exercises

1. **One-time consume:** create a claim, call `take`, simulate downstream failure, try restoring the same ticket. Explain why `NOT_FOUND` occurs.
2. **Reusable read:** switch to `find`, call restore twice within TTL, and verify the original payload remains intact.
3. **Completion-aware:** process successfully, clean up claim, resend token, and return the old receipt from the ledger without recharging.
4. **Transient payment error:** fake payment throws on first call before commit, succeeds on second. Verify claim still restores on the second attempt.
5. **Commit-but-reply-lost:** fake payment records success yet caller hits timeout. Design reconciliation and test no second side effect occurs.
6. **TTL:** use `Clock.fixed` to mint a 10-minute TTL token, read at minute 11, and assert `EXPIRED` without sleeping.
7. **Tombstone:** add claim status table `AVAILABLE/CONSUMED/COMPLETED/EXPIRED` to distinguish errors once payload records are deleted.
8. **Cross-tenant:** try restoring `TENANT-A`'s token with `TENANT-B` principal; confirm `ACCESS_DENIED` and zero data returned.
9. **Forged ticket:** keep `claimId` yet swap `operationId`; verify the service rejects tickets mismatched with stored records.
10. **Revocation:** add revoked state; verify retries and replays cannot bypass permissions.
11. **Idempotency conflict:** same `operationId` with different amount; add fingerprints and return `OPERATION_CONFLICT`.
12. **Concurrent readers:** have two threads restore a reusable claim simultaneously; prove both read it while fake payment executes only one operation.
13. **Lease/fencing:** simulate Worker A pausing past deadline while Worker B takes a new lease. Block A from committing with a stale fencing token.
14. **Native Spring Claim Check:** build a flow using Claim Check In/Out Transformers and a `MessageStore` matching your version. Test retain/delete across two reads.
15. **Retry scope:** place advice around payment only vs around claim-out + payment. Explain outcomes under remove-on-read.
16. **Broker redelivery:** send the same token across transport twice; verify one business receipt, not merely two received messages.
17. **Transactional outbox:** simulate crash after saving claim before publishing; verify outbox relay emits the token after recovery.
18. **Orphan claim:** have Filter reject after claim-in; write a cleanup/TTL job with audits and metrics.
19. **Scatter–Gather:** have Inventory and Fraud share one one-time claim; reproduce the failure, then fix with a reusable claim or two separate claims.
20. **Resequencer:** hold a token past TTL; verify late claim-out returns expired and triggers a recovery policy.
21. **Splitter/Aggregator:** split a batch into three claims, delete one claim early, and emit an error outcome instead of hanging the group forever.
22. **Gateway timeout:** let a remote worker finish after caller timeout; test retrying the operation without creating a new side effect.
23. **Restart:** swap in-memory store for persistent store, simulate restart between issue and claim-out; verify token still resolves.
24. **Serialization:** pass tokens through JSON/Kafka/HTTP adapters; inspect `claimId`/`operationId`/correlation and strip non-wire-portable internal `replyChannel`.
25. **Observability:** log `CLAIM_ISSUED`, `CLAIM_RESTORED`, `OPERATION_OUTCOME_UNKNOWN`, `CLAIM_CLEANUP_COMPLETED`; build dashboards for missing, completed, and orphan claims.
26. **Security:** enforce payload size caps, rate-limit restore endpoints, and protect tokens in logs, tracing, and dead-letter queues.
27. **Data deletion:** verify claim data is purged from primary, caches, and backups per approved retention policy.
28. **Recovery runbook:** document explicit handling flows for `NOT_FOUND+COMPLETED`, `NOT_FOUND+UNKNOWN`, `EXPIRED`, `ACCESS_DENIED`, and `STORE_UNAVAILABLE`.

### Exercise completion criteria

A sound implementation should answer:

- Can claims be **re-read after claim-out**? Was behavior tested against actual remove settings?
- At which step do message retries begin, and do they repeat claim-out?
- After an operation commits and the claim is deleted, how are **duplicate tokens** handled?
- Can a store-unavailable error be mistaken for a missing claim?
- If the payload is gone, is there an authorized, versioned replay source?
- Are claim ID, operation ID, tenant, and attempt ID clearly distinguished?
- Do retries create duplicate side effects under concurrency/crashes?
- Are TTL, capacity, cleanup, tombstones, and revocation policies defined?
- Can a message be traced from claim-in through business outcome to cleanup?
- Were the exact broker/store/payment boundaries used in production tested?

## 24. Self-check questions

**Question 1:** Claim Check Out read the payload the first time using `remove-on-get`; payment timed out. Will retrying the same claim ID definitely retrieve the payload again?

**No.** If the claim was removed, retries may receive `NOT_FOUND`/`ALREADY_CONSUMED`. You must check completion and replay policies or design read-without-remove.

**Question 2:** If claim-out does not remove, can two retries cause two charges?

**Yes.** A reusable claim only preserves data; operation-level idempotency at the side-effect boundary is still required.

**Question 3:** Why does “restore succeeded” not equal “payment succeeded”?

Because restore only fetches the payload from the store. Downstream can still time out, throw, or fail to commit.

**Question 4:** Claim was deleted, broker redelivers token, completion ledger shows `SUCCESS`. What should happen?

If the receipt is authenticated/authorized and matches the operation, return the existing receipt or acknowledge the duplicate without calling payment again.

**Question 5:** Claim does not exist, and completion ledger has nothing either. Can we assume the claim already succeeded?

**No.** `NOT_FOUND` has many causes. Investigate/reconcile, or replay from a valid source when permitted.

**Question 6:** `claimId` may change when an operator reissues, but what about `operationId`?

If retrying the same business operation, `operationId` should remain stable for deduplication. If truly creating a new operation, define a clear contract and new ID.

**Question 7:** Why is retrying the entire flow different from retrying only the payment endpoint?

Retrying the whole flow can repeat claim-out after first-attempt deletion; retrying payment alone within the same attempt can reuse the already-restored payload without hitting the store again.

**Question 8:** Claim was saved successfully yet token publication failed. What happens?

An orphan claim can be created. Outbox/recovery/cleanup prevents lost tokens or unbounded data retention.

**Question 9:** Payment committed yet the response was lost. May the retry charge again by default?

**No.** Use an idempotency key or query/reconcile status before executing another side effect.

**Question 10:** Is a one-time claim sufficient when both Inventory and Fraud recipients need the data?

**Not by default.** One recipient can consume first and leave the other unable to retrieve it. Consider reusable or separate scoped claims.

**Question 11:** Claim TTL is 5 minutes, Resequencer buffers tokens for 10 minutes. Does Resequencer release prove the claim still exists?

**No.** Token messages may release in order while payloads already expired; align retention with gap/retry policies.

**Question 12:** Does `ConcurrentHashMap.computeIfAbsent` in fake payment guarantee exactly-once across multiple JVMs and real HTTP payments?

**No.** It illustrates only single-process deduplication; distributed side effects need proper idempotency/transaction boundaries and recovery.

**Question 13:** Why shouldn't the claim be deleted inside the payment handler's `finally` block?

Because `finally` runs even when the handler throws; the payload could vanish before retries get a chance to restore it.

**Question 14:** Can a revoked claim be reissued immediately simply because a retry request arrived?

**No.** Reissuing must inspect the revocation reason and current permissions without bypassing security.

**Question 15:** If the Message Store already stores data durably, is idempotency still needed?

**Yes.** The store protects payloads, whereas idempotency protects side effects when messages/redeliveries are processed repeatedly.

**Question 16:** Should an `ErrorMessage` containing a claim token be logged in full?

Not by default. A claim ID can lead to sensitive data; use masked/hashed references and proper logging policies.

**Question 17:** Are completion records and cleanup records the same state?

**No.** Payment finished while the claim awaits deletion is a valid state; cleanup failure does not mean business failure.

**Question 18:** If the same operation ID arrives with two different payloads, may the old receipt be returned for the new payload?

**Not by default.** Verify operation fingerprints/provenance and return a conflict when data mismatches.

## 25. Summary

**Retrying messages with already-used claims** is a problem of **data lifecycles and business outcomes**, not merely increasing retry counts. With Claim Check, payloads are stored separately from in-flight messages and retrieved by token. If claim-out **consumes/deletes the claim before downstream finishes**, retrying the same token can lose data; if keeping claims readable again, you must still prevent **duplicate side effects** when brokers redeliver or multiple workers run concurrently.

In Spring Integration, carefully inspect **Claim Check In/Out Transformers, Message Store, remove-on-read behavior, retry advice scope, Gateway timeouts, error channels, header mapping, and transaction boundaries**. For critical business operations, prefer a resilient design: **persist payloads durably, issue tokens under control, restore without premature deletion, use stable `operationId`/idempotency, record authoritative completions, and clean up afterward**. Once a claim is consumed, expired, or revoked, recovery must rely on completions/tombstones and authorized replay sources — never guessing success or fabricating data.

When combining Claim Check with Router, Filter, Splitter, Aggregator, Scatter–Gather, Resequencer, Transformer, and Gateway in `SPRING_INTEGRATION_PATTERN`, verify **how many times each branch may retrieve the original, whether tokens stay valid across retry/buffer horizons, and where business outcomes are confirmed**. A sound design keeps message flows loosely coupled, extensible, traceable, recoverable after failures, and never reports “success” simply because a claim was read.
