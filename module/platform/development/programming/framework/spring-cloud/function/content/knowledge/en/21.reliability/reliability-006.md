# Avoiding Duplicate Side Effects When Data Is Resent

## 1. Lesson Objectives

An order creation event can arrive **twice** even when the sender created only **one business request**. An HTTP client resends a `POST` after a timeout; a message broker redelivers an event before receiving an acknowledgement; a serverless platform reinvokes a failed invocation; or an operator replays a message from a dead-letter queue. If the same `Consumer` sends an email, deducts money, grants access, or inserts another record on every call, data loses consistency.

In the **SPRING_CLOUD_FUNCTION** module, logic is organized using `Supplier`, `Function`, and `Consumer`, registered in `FunctionCatalog`, and composable into pipelines independent of whether they are triggered via HTTP, events, or serverless. Protocol independence **does not** make inputs arrive only once; the **side-effect boundary itself** must be designed to tolerate replays.

This lesson belongs to the **Reliability** chapter and focuses on **avoiding duplicate side effects when data is resent**. After this lesson, you will be able to:

- Explain why retries, redeliveries, replays, and reinvocations can repeat **one logical request**.
- Distinguish pure functions, business idempotency, and deduplication mechanisms.
- Choose a stable processing identifier, distinguishing `eventId`, `requestId`, `orderId`, and `operationVersion`.
- Detect when the same idempotency key arrives with a different payload rather than silently overwriting.
- Organize pure `Function` steps ahead of a side-effecting `Consumer` via `FunctionCatalog`.
- Use unique constraints and transactions to prevent two instances from processing the same event concurrently.
- Design transactional inbox/outbox tables, understand publish/ack guarantees, and handle post-commit errors.
- Verify HTTP, message binder, serverless, and Reactor behavior when inputs are re-invoked.
- Write unit tests, integration tests, and concurrency/crash-window tests.

> **Guiding Principle:** Never treat "the framework retried" or "the message has a delivery guarantee" as proof that side effects run only once. Define **once in business terms**, use stable keys, store state durably, and verify scenarios where commit success is uncertain.

## 2. Why Can a Message Be Processed Multiple Times?

Consider an event sent to a Function:

~~~json
{
  "eventId": "evt-778",
  "orderId": "ORD-42",
  "sku": "SKU-7",
  "quantity": 2
}
~~~

A common failure sequence:

~~~text
Broker delivers event evt-778
       |
       v
Consumer receives and calculates quote
       |
       v
Database COMMIT succeeds
       |
       v
Process crashes before ACK
       |
       v
Broker does not know processing succeeded
       |
       v
Broker redelivers evt-778
       |
       v
Consumer runs all logic again
~~~

If the Consumer executes an unconstrained `INSERT` or unconditionally sends an email, a single request can produce multiple side effects.

### 2.1. Different Entry Paths, Same Risk

| Invocation Source | Why Does Data Repeat? | What the Application Must Tolerate |
|---|---|---|
| HTTP/SDK | Client times out and resends `POST` | Same request key creates no duplicate business effect |
| Kafka/RabbitMQ/broker | Missing ack, rebalance, processing error, at-least-once delivery | Redelivery of the same event |
| Serverless | Invocation retries, timeouts, event source redeliveries | One event hits multiple invocations/instances |
| Scheduler/poller | Re-scans records not yet marked complete | Re-picks the same work |
| Operator replay | Replays from a DLQ or earlier offset | Historical events reappear |
| Reactor | `retry` or a new subscriber re-triggers a cold Publisher | Side-effecting callbacks re-run |

Not every adapter retries the same way by default. For example, Spring Cloud Function's HTTP web adapter does not make every request arrive only once; client timeouts and resends live at another boundary. Always check the actual binder, trigger, and version.

### 2.2. Post-Commit Failure Is the Highest-Priority Scenario

There are three failure points:

1. **Before side effects:** validation fails; nothing was written.
2. **Inside a transaction before commit:** the transaction can roll back.
3. **After commit but before ack/response:** side effects succeeded while the caller sees an error.

The third case is why "catch exception and retry" is dangerous. **A timeout does not prove the transaction failed to commit.**

## 3. Purity, Idempotency, Deduplication, and Exactly-Once

These four concepts are easily conflated:

| Concept | Meaning | Example |
|---|---|---|
| Pure function | Same input yields same output, no external mutation | Computing `total = quantity * unitPrice` |
| Business idempotency | Repeating the same request adds no unintended effect | Saving the same Quote twice leaves one record |
| Deduplication | Recognizing repeated deliveries of the same request/event | Checking `eventId` in a processed table |
| Exactly-once | A processing scope with defined guarantees against repeated effects | Depends on transactions and the scope considered |

For instance, `Function<Integer,Integer> addOne = x -> x + 1` is pure, yet not mathematically idempotent (`f(f(x))=f(x)`). Conversely, a `Consumer<Quote>` is impure yet idempotent if the same key is stored once.

**Never claim "Spring Cloud Function guarantees exactly-once"** merely because you use `FunctionCatalog`, `Consumer`, or a binder. Some technologies offer transactional/exactly-once semantics within a **bounded scope**—such as certain Kafka topic-to-topic operations—but that does not automatically extend to a separate database, email provider, REST API, or payment gateway.

### 3.1. When Is Deduplication Not Enough?

Suppose a Consumer checks a `processed_events` table and writes to a `quotes` table in two separate transactions:

~~~text
Mark event processed  → COMMIT
Save Quote            → fails
~~~

Next delivery sees the event marked processed and skips it. Outcome: **no Quote exists** even though the event was marked complete.

Reverse the order:

~~~text
Save Quote            → COMMIT
Mark event processed  → process dies
~~~

Next delivery sees no marker and saves the Quote again. Outcome: **duplicate write possible**.

Therefore, safe deduplication must pair with **transaction boundaries and a business definition of completion**, not just a set of seen keys.

## 4. Defining What Counts as "The Same Request"

Picking the wrong key can make the system wrongly drop a valid operation or double-process an old one.

| Key | Meaning | Risk If Misused |
|---|---|---|
| `eventId` | A specific published event instance | If retries mint a new event ID, the same business operation goes unrecognized |
| `requestId` / `Idempotency-Key` | One logical call from a client | If the client mints a new key per retry, deduplication fails |
| `orderId` | One aggregate / order | May block valid subsequent updates to the same order |
| `tenantId + orderId` | Tenant-scoped business key | Prevents ID collisions across tenants |
| `orderId + operation + version` | A specific action at a given version | Fits when the same order undergoes multiple actions over time |
| `payloadHash` | Content fingerprint | Two distinct operations may share identical payloads |

Essential rules:

1. **Resending the same request must keep the same key.**
2. Keys must represent the right business scope, not just an HTTP connection or delivery attempt.
3. Same key, same payload: treat as a replay of the same operation.
4. Same key, different payload: report **conflict**; never silently overwrite or pretend success.
5. If a new operation on the same entity is valid, it must have a distinct key or operation version.

### 4.1. Illustrating Event ID vs. Order ID

~~~text
evt-101: CreateOrder(ORD-42, quantity=2)
evt-101: CreateOrder(ORD-42, quantity=2)  ← redelivery, must dedupe

evt-102: ChangeQuantity(ORD-42, quantity=3)
                                          ← different business op, valid if version matches

evt-103: CreateOrder(ORD-42, quantity=2)
                                          ← possible logical duplicate with a new eventId
~~~

Deduplicating only by `eventId` misses `evt-103`. Deduplicating only by `orderId` risks blocking `ChangeQuantity`. You need both **event identity** to recognize redeliveries and **business constraints/versions** to protect aggregate invariants.

### 4.2. Should You Use Payload Hash as the Key?

Use hashes to compare payloads sharing **the same key**, not as the sole operation identifier by default. Two distinct legitimate requests can carry identical payloads and still require independent processing.

When computing a fingerprint:

- Define a canonical payload after valid normalization.
- Include business-meaningful fields, excluding per-delivery timestamps or mutable transport headers.
- Use deterministic serialization, stable field ordering, and consistent number/locale/timezone formatting.
- Use a suitable hash algorithm and compare within the key/tenant scope.
- Avoid logging raw sensitive payloads or using hashes as proof of caller identity.

## 5. Choosing the Deduplication Boundary in a Pipeline

A clean pipeline separates the pure core from the I/O layer:

~~~text
Input event / HTTP request
           |
           v
Transport adapter (parse, auth, schema)
           |
           v
normalizeOrder            Function<OrderCommand, OrderCommand>
           |
           v
validateOrder             Function<OrderCommand, ValidatedOrder>
           |
           v
calculateQuote            Function<ValidatedOrder, Quote>
           |
           v
recordQuoteOnce           Consumer<Quote> + persistent dedupe
           |
           v
DB transaction / outbox / response-ack
~~~

**Computation Functions need no side effects.** Yet placing a Consumer at the end is not enough by itself. The Consumer must perform an **idempotent** write protected by storage.

### 5.1. Clear Boundaries Enable Reuse

- HTTP can invoke `normalize|validate|calculate` to preview a quote without writing.
- Message Consumers can invoke the same core followed by `recordQuoteOnce`.
- Serverless handlers can invoke the same functions when triggered.
- Retries of pure Functions are easy to verify, while write retries are protected by keys and transactions.
- Adapters decide HTTP statuses, acks, and DLQs without embedding them in `calculateQuote`.

### 5.2. Do Not Equate Consumer with "Runs Exactly Once"

`Consumer<T>` only defines `accept(T) -> void`. It does not compel Java or Spring to remember processed items. A Consumer calling `repository.save` twice can write twice unless its implementation and storage prevent it.

Likewise, `FunctionCatalog.lookup("validateOrder|calculateQuote|recordQuoteOnce")` composes names, **without creating dedupe tables, transactions, or unique constraints**.

## 6. Sample Data and Business Rules

We receive a quote request:

~~~json
{
  "eventId": "evt-778",
  "tenantId": "shop-a",
  "orderId": "ORD-42",
  "sku": "SKU-7",
  "quantity": 2
}
~~~

Business rules:

- `eventId` stays stable when the same message is redelivered.
- `tenantId` scopes `orderId` and idempotency.
- `orderId` identifies a specific order's quote.
- `sku` matches the expected pattern; `quantity` is 1 to 100.
- Illustrative unit price is fixed at `125_000 VND`.
- Same `tenantId + eventId` with the same content is a replay.
- Same key with different content must report a conflict.
- Same `tenantId + orderId` must not create two inconsistent quotes.

### 6.1. Java 17 Data Types

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderCommand(
            String eventId,
            String tenantId,
            String orderId,
            String sku,
            Integer quantity) {}

    public record ValidatedOrder(
            String eventId,
            String tenantId,
            String orderId,
            String sku,
            int quantity) {}

    public record Quote(
            String eventId,
            String tenantId,
            String orderId,
            String sku,
            int quantity,
            long totalVnd) {}
}
~~~

A distinct `ValidatedOrder` type tells downstream steps that validation already ran. Records do not stop arbitrary code from calling constructors directly; in production, use invariant-checking factories/constructors or control construction paths.

### 6.2. Error Types

~~~java
package example.functions;

public final class OrderErrors {

    private OrderErrors() {}

    public static class InvalidOrderException
            extends RuntimeException {
        public InvalidOrderException(String message) {
            super(message);
        }
    }

    public static class DuplicateConflictException
            extends RuntimeException {
        public DuplicateConflictException(String message) {
            super(message);
        }
    }

    public static class TransientStoreException
            extends RuntimeException {
        public TransientStoreException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Distinct error types let adapters tell bad requests, key-with-different-payload conflicts, and transient infrastructure failures apart. Never convert all database exceptions into `TransientStoreException`, since unique violations, conflicts, and bugs do not heal through retries.

## 7. Pure Functions in Spring Cloud Function

Declare `Function` beans:

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderCommand;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@Configuration
public class OrderFunctions {

    private static String canonical(String raw) {
        return raw == null
                ? null
                : raw.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<OrderCommand, OrderCommand> normalizeOrder() {
        return input -> {
            if (input == null) {
                throw new InvalidOrderException(
                        "OrderCommand must not be null");
            }

            return new OrderCommand(
                    input.eventId() == null
                        ? null : input.eventId().trim(),
                    input.tenantId() == null
                        ? null : input.tenantId().trim(),
                    canonical(input.orderId()),
                    canonical(input.sku()),
                    input.quantity());
        };
    }

    @Bean
    public Function<OrderCommand, ValidatedOrder> validateOrder() {
        return input -> {
            if (input == null
                    || input.eventId() == null
                    || input.eventId().isBlank()
                    || input.tenantId() == null
                    || input.tenantId().isBlank()
                    || input.orderId() == null
                    || !input.orderId().matches("ORD-[0-9]+")
                    || input.sku() == null
                    || !input.sku().matches("SKU-[0-9]+")
                    || input.quantity() == null
                    || input.quantity() < 1
                    || input.quantity() > 100) {
                throw new InvalidOrderException(
                        "Invalid OrderCommand");
            }

            return new ValidatedOrder(
                    input.eventId(),
                    input.tenantId(),
                    input.orderId(),
                    input.sku(),
                    input.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> new Quote(
                order.eventId(),
                order.tenantId(),
                order.orderId(),
                order.sku(),
                order.quantity(),
                Math.multiplyExact(
                    (long) order.quantity(), 125_000L));
    }
}
~~~

The fixed unit price highlights deterministic computation. Fetching prices from a database or API on every retry could yield different totals for the same `OrderCommand`. For consistent historical reprocessing, embed a price/rule snapshot in the input or store the applied version.

### 7.1. Why Separate normalize and validate?

Inputs may arrive as `" ord-42 "` and `" sku-7 "`. Normalization brings them to canonical form before regex validation. Never auto-repair invalid business values into valid ones; normalization must apply only transformations allowed by the contract.

### 7.2. Order Matters More Than Bundling Everything into One Function

~~~text
normalize → validate → calculate → record
~~~

If an input lacks an event ID or has quantity `0`, `validateOrder` rejects it **before any write Consumer runs**. Validation does not replace deduplication, yet prevents bad writes on every attempt.

## 8. Composing the Core by Name with FunctionCatalog

Look up the pure pipeline:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.OrderCommand;
import example.functions.OrderModels.Quote;

@Service
public class QuotePreviewService {

    private final FunctionCatalog catalog;

    public QuotePreviewService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Quote preview(OrderCommand request) {
        Function<OrderCommand, Quote> core = catalog.lookup(
                "normalizeOrder|validateOrder|calculateQuote");

        if (core == null) {
            throw new IllegalStateException(
                    "Quote pipeline not found");
        }

        return core.apply(request);
    }
}
~~~

Overall contract: `Function<OrderCommand,Quote>`. Given the same request, the pure functions produce the same `Quote` without persisting anything.

When appending `Consumer<Quote> recordQuoteOnce` at the end, the chain:

~~~text
normalizeOrder|validateOrder|calculateQuote|recordQuoteOnce
~~~

has the expected contract `Consumer<OrderCommand>`. Composition and runtime adaptation support for each function shape must be verified with integration tests on your Spring Cloud Function version; string names do not replace type and runtime checks.

### 8.1. Configuring definition Does Not Enable Deduplication

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrder|validateOrder|calculateQuote|recordQuoteOnce"
~~~

`spring.cloud.function.definition` selects the function combination for an adapter. It **does not enable** idempotency-key storage, unique constraints, retries/DLQs, or transactions. HTTP, Stream, and serverless require proper transport configuration.

## 9. A Port for the Idempotent Write Boundary

Instead of letting `calculateQuote` call a repository directly, define a port expressing **the intent to write once per business operation**:

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteRecorder {
    void recordOnce(Quote quote);
}
~~~

The `Consumer` bean delegates to this port:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.Quote;

@Configuration
public class QuoteRecordingFunctions {

    @Bean
    public Consumer<Quote> recordQuoteOnce(
            QuoteRecorder recorder) {
        return recorder::recordOnce;
    }
}
~~~

Benefits:

- `calculateQuote` knows nothing about databases, brokers, retries, or transactions.
- Writing has a clean interface to enforce an idempotency policy.
- The same pure Functions serve previews, tests, and real write workflows.
- An in-memory `QuoteRecorder` can be swapped for JDBC/JPA without touching pricing logic.

**A port is only a contract:** Naming a method `recordOnce` does not make implementations idempotent. Storage guarantees and concurrent/replay tests are required.

### 9.1. When the Same Key Repeats with Different Data

A proper Recorder must never be written as:

~~~java
if (alreadyProcessed(eventId)) {
    return; // Insufficient if current payload differs from previous payload.
}
~~~

If an attacker or bug reuses `eventId` with different content, silently ignoring it masks inconsistent data. The required rule is:

~~~text
eventId does not exist
    → process atomically and store fingerprint

eventId exists + matching fingerprint
    → valid duplicate: produce no new side effect

eventId exists + different fingerprint
    → conflict: reject and alert/investigate
~~~

Fingerprints should be computed over **canonical business-meaningful fields**, excluding redelivery headers, receipt timestamps, or mutable transport offsets.

## 10. In-Memory Recorder to Illustrate Semantics Clearly

Before introducing a real database, we can model both constraints inside **one JVM**:

1. One `tenantId + eventId` must not be processed with two different payloads.
2. One `tenantId + orderId` must not produce two conflicting quotes.

To avoid race conditions across the two maps inside one process, the example uses a `synchronized` method. This is **not a multi-instance production design** and has no durability.

~~~java
package example.functions;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.DuplicateConflictException;

@Profile("demo")
@Component
public class InMemoryQuoteRecorder implements QuoteRecorder {

    public record EventKey(String tenantId, String eventId) {}
    public record OrderKey(String tenantId, String orderId) {}

    private final Map<EventKey, Quote> handledEvents =
            new HashMap<>();
    private final Map<OrderKey, Quote> quotes =
            new HashMap<>();

    @Override
    public synchronized void recordOnce(Quote quote) {
        if (quote == null
                || quote.eventId() == null
                || quote.tenantId() == null
                || quote.orderId() == null) {
            throw new IllegalArgumentException(
                    "Quote and identity must not be null");
        }

        EventKey eventKey = new EventKey(
                quote.tenantId(), quote.eventId());
        OrderKey orderKey = new OrderKey(
                quote.tenantId(), quote.orderId());

        Quote sameEvent = handledEvents.get(eventKey);

        if (sameEvent != null) {
            if (!sameEvent.equals(quote)) {
                throw new DuplicateConflictException(
                        "Event key reused with different payload");
            }
            return;
        }

        Quote sameOrder = quotes.get(orderKey);

        if (sameOrder != null) {
            if (!sameBusinessQuote(sameOrder, quote)) {
                throw new DuplicateConflictException(
                        "Order already has a different Quote");
            }

            // New event ID but same Quote creation operation in business terms.
            // Do not create a second Quote record.
            handledEvents.put(eventKey, quote);
            return;
        }

        // Within one JVM: both maps share the same lock.
        quotes.put(orderKey, quote);
        handledEvents.put(eventKey, quote);
    }

    private static boolean sameBusinessQuote(Quote a, Quote b) {
        return Objects.equals(a.tenantId(), b.tenantId())
                && Objects.equals(a.orderId(), b.orderId())
                && Objects.equals(a.sku(), b.sku())
                && a.quantity() == b.quantity()
                && a.totalVnd() == b.totalVnd();
    }

    public synchronized Quote find(
            String tenantId, String orderId) {
        return quotes.get(new OrderKey(tenantId, orderId));
    }

    public synchronized int quoteCount() {
        return quotes.size();
    }

    public synchronized int handledEventCount() {
        return handledEvents.size();
    }

    public synchronized void clear() {
        quotes.clear();
        handledEvents.clear();
    }
}
~~~

`sameBusinessQuote` omits `eventId` because two distinct event IDs can represent **the same Quote creation request** re-emitted by an upstream producer with a new ID. That is **this example's rule**, not a claim that every new event ID on an order is a duplicate. In an application supporting Quote updates, separate operations/versions and never apply this rule to ignore legitimate updates.

### 10.1. Behavior Table

| Call | Quote Count | Recognized Event IDs | Behavior |
|---|---:|---:|---|
| `evt-778, ORD-42, quantity=2` (first time) | 1 | 1 | Saves |
| Redelivery of `evt-778`, same payload | 1 | 1 | No-op |
| `evt-778` with quantity=3 | 1 | 1 | Conflict |
| `evt-779, ORD-42` same business op | 1 | 2 | Quote no-op, stores new event |
| `evt-780, ORD-42` with quantity=3 | 1 | 2 | Conflict |
| `evt-781, ORD-43`, quantity=2 | 2 | 3 | Saves another Quote |

All of this holds only inside a single JVM instance. With two replicas, each replica holds its own `HashMap`; on process death, state disappears. Never use this class as production idempotency proof.

### 10.2. In-Process Atomicity Does Not Replace Transactions

`synchronized` protects threads within one JVM, yet does not protect:

- Two separate instances.
- Crashes or restarts between durable changes.
- Email or broker calls outside the maps.
- Database commits vs. message acknowledgements.

To survive restarts and multiple replicas, move the deduplication boundary to **shared transactional storage**.

## 11. Designing Inbox, Quote, and Outbox Tables in the Database

In event-driven systems, a **transactional inbox** records processed event markers in the same transaction as the database side effect. If events must also be published, a **transactional outbox** records publish intent in that same transaction.

Illustrative PostgreSQL schema:

~~~sql
CREATE TABLE processed_event (
    tenant_id       VARCHAR(80) NOT NULL,
    event_id        VARCHAR(120) NOT NULL,
    payload_hash    CHAR(64) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id)
);

CREATE TABLE order_quote (
    tenant_id       VARCHAR(80) NOT NULL,
    order_id        VARCHAR(80) NOT NULL,
    sku             VARCHAR(80) NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    total_vnd       BIGINT NOT NULL CHECK (total_vnd >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE outbox_event (
    outbox_id       UUID PRIMARY KEY,
    tenant_id       VARCHAR(80) NOT NULL,
    order_id        VARCHAR(80) NOT NULL,
    event_type      VARCHAR(80) NOT NULL,
    payload         JSONB NOT NULL,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

This schema highlights key constraints:

- `processed_event` has unique key `(tenant_id,event_id)` to deduplicate identical messages.
- `payload_hash` detects **same key with different content**.
- `order_quote` has unique key `(tenant_id,order_id)` to protect Quote creation invariants.
- `outbox_event` carries a stable `outbox_id` for downstream deduplication.

This is a learning schema; production needs query-aligned migrations/indexes, retention policies, access controls, PII considerations, and suitable outbox status columns.

### 11.1. Claiming an Event ID Atomically

In PostgreSQL:

~~~sql
INSERT INTO processed_event (
    tenant_id,
    event_id,
    payload_hash
)
VALUES (:tenantId, :eventId, :payloadHash)
ON CONFLICT (tenant_id, event_id) DO NOTHING
RETURNING event_id;
~~~

If the statement returns a row, the current transaction **claimed the event key**. If it returns no row, the key already exists and the application must read the stored `payload_hash` to distinguish a valid replay from a conflict.

**Watch concurrency behavior:** In PostgreSQL, an insert colliding on a unique key held by another uncommitted transaction can block waiting for that transaction to commit or roll back before resolving the conflict. Configure timeouts and map database errors per policy. Never replace a unique constraint with an unlocked `SELECT` before `INSERT`.

### 11.2. Why Inbox and Quote Must Commit Together

Run inside a single database transaction:

~~~text
BEGIN TRANSACTION

1. Claim (tenantId,eventId) via UNIQUE INSERT
2. If duplicate:
     - compare payload hash
     - return prior result or conflict
3. If newly claimed:
     - verify order business constraints
     - INSERT Quote if new operation
     - INSERT OutboxEvent if event must be published
4. COMMIT

Only after COMMIT: ACK or return response per adapter
~~~

If the transaction rolls back due to an error writing Quote or outbox, the `processed_event` claim rolls back too; a subsequent redelivery can retry processing.

If everything commits and the process dies before ACK, the next delivery finds the inbox row and **creates no new Quote or outbox record**.

### 11.3. When Events Have Different IDs for the Same Order

The inbox recognizes only identical `eventId`s. If a producer re-emits the same operation with a new `eventId`, `processed_event` treats it as a new event. The unique constraint on `order_quote` then prevents a second Quote for the same `tenantId+orderId`.

The service must decide:

- Existing Quote matches **in business content**: treat as a duplicate of the create operation and record the new event as processed.
- Existing Quote **differs**: conflict; do not overwrite.
- Event is a **new-version update operation**: process under a separate update/version contract rather than create-only rules.

Never rely solely on event IDs to protect aggregate invariants.

## 12. @Transactional Boundaries in Spring

Conceptual service for a database transaction:

~~~java
package example.functions;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.DuplicateConflictException;

@Profile("prod")
@Service
public class TransactionalQuoteRecorder implements QuoteRecorder {

    private final ProcessedEventStore inbox;
    private final QuoteTable quotes;
    private final OutboxTable outbox;
    private final QuoteFingerprint fingerprint;

    public TransactionalQuoteRecorder(
            ProcessedEventStore inbox,
            QuoteTable quotes,
            OutboxTable outbox,
            QuoteFingerprint fingerprint) {
        this.inbox = inbox;
        this.quotes = quotes;
        this.outbox = outbox;
        this.fingerprint = fingerprint;
    }

    @Override
    @Transactional
    public void recordOnce(Quote quote) {
        String hash = fingerprint.of(quote);

        boolean claimed = inbox.insertIfAbsent(
                quote.tenantId(), quote.eventId(), hash);

        if (!claimed) {
            String stored = inbox.getFingerprint(
                    quote.tenantId(), quote.eventId());

            if (!hash.equals(stored)) {
                throw new DuplicateConflictException(
                        "Event key with different payload");
            }
            return; // Already committed this operation on a previous attempt.
        }

        // Check/create by unique key (tenantId, orderId).
        QuoteTable.InsertResult result =
                quotes.insertOrCompare(quote);

        if (result == QuoteTable.InsertResult.CONFLICT) {
            throw new DuplicateConflictException(
                    "Order already has a different Quote");
        }

        if (result == QuoteTable.InsertResult.CREATED) {
            outbox.insertQuoteCreated(quote);
        }

        // If an exception occurs, roll back all writes above.
        // If committed, inbox + quote + outbox take effect together.
    }
}
~~~

Here `ProcessedEventStore`, `QuoteTable`, `OutboxTable`, and `QuoteFingerprint` are **ports/repositories that must be implemented** with real SQL and transactions; this example shows flow and decision points, not a runnable app without those adapters.

Ensure:

- All three tables share **the same datasource and transaction manager** at this boundary.
- `insertIfAbsent` performs an atomic write backed by a unique constraint.
- `insertOrCompare` protects the business key under concurrency; never use unconstrained `SELECT` then `INSERT`.
- `@Transactional` actually runs through a Spring proxy (do not bypass it via `this.recordOnce(...)`).
- Exceptions trigger rollback per transaction policy; in default Spring config, unchecked exceptions trigger rollback.
- Never invoke a remote service mid-transaction assuming it rolls back along with the DB.

### 12.1. An Important Issue with Uncommitted Duplicates

If a second event arrives while the first event **is still processing**, you cannot return "already succeeded" just because an early "in-progress" marker exists. You may need to wait for the first transaction to finish, return `IN_PROGRESS`, or use a recoverable claim/lease design.

In the unique-key transaction pattern, concurrent operations rely on database locking and wait for commit or rollback. If a design splits `RECEIVED/PROCESSING/DONE` states across multiple transactions, add lease timeouts and crash recovery when workers die mid-flight.

### 12.2. Transactions Do Not Make Remote Side Effects Atomic

If `recordOnce` also calls an email API:

~~~java
@Transactional
public void recordOnce(Quote quote) {
    inbox.insert(...);
    quotes.insert(...);
    emailClient.send(...); // Remote API sits outside DB transaction.
}
~~~

This is conceptual code showing **what not to assume**. If the email sends and the DB rolls back, the email went out while the inbox recorded nothing. On retry, the email can send again.

Instead, record the send intent in an outbox table or pass an idempotency key to the provider if supported, depending on requirements. `@Transactional` does not create distributed transactions across arbitrary external systems.

## 13. Transaction Ports and Payload Fingerprints

In `TransactionalQuoteRecorder`, dependencies must be implemented by JDBC/JPA adapters. Sample contracts:

~~~java
package example.functions;

public interface ProcessedEventStore {
    // INSERT by unique key (tenantId,eventId).
    // Returns true when insert succeeds in the transaction.
    boolean insertIfAbsent(
            String tenantId, String eventId, String payloadHash);

    // Read the stored fingerprint for the same key.
    String getFingerprint(String tenantId, String eventId);
}
~~~

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteTable {

    enum InsertResult {
        CREATED,
        ALREADY_PRESENT,
        CONFLICT
    }

    InsertResult insertOrCompare(Quote quote);
}
~~~

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface OutboxTable {
    void insertQuoteCreated(Quote quote);
}
~~~

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteFingerprint {
    String of(Quote quote);
}
~~~

These interfaces describe boundaries. **They do not provide SQL or transactions themselves**; real database implementations must enforce the constraints.

### 13.1. Fingerprints Must Be Deterministic and Versioned

Never use `UUID.randomUUID()` as a fingerprint. Hash a canonical structure containing stable business fields, for example:

~~~java
record QuoteFingerprintInput(
        String tenantId,
        String orderId,
        String sku,
        int quantity,
        long totalVnd,
        String ruleVersion) {}
~~~

Implementations can serialize canonically and apply SHA-256. Standardize field ordering, number formatting, timezone handling, and normalization rules.

Distinguish three concepts:

- **Command fingerprint:** incoming event data, to catch the same event ID with a different payload.
- **Business fingerprint:** business outcome, to catch the same order with a different Quote.
- **Event identity:** emission identifier, to recognize redeliveries.

When pricing rules change across deployments, replaying an old event can compute a new total if recalculated. For accurate replays, persist rule versions/price snapshots or check command-key duplicates **before re-running mutable calculation steps**.

### 13.2. Keep the Two Uniqueness Layers Distinct

~~~text
(tenantId,eventId)             → detects redelivered events
(tenantId,orderId,operation)   → protects business invariants
~~~

A new event ID may be a re-sent create operation. A valid update operation on the same order should not be blocked simply because the order exists: use appropriate operations and versions.

### 13.3. Activate Only One QuoteRecorder Implementation

`InMemoryQuoteRecorder` and `TransactionalQuoteRecorder` are two **alternative implementations**. If Spring registers both, dependency injection becomes ambiguous.

Mark each class with `@Profile("demo")` and `@Profile("prod")` or conditional beans so only one implementation is active at a time.

~~~java
// Illustrative annotation to place on the existing class:
@Profile("demo")
@Component
public class InMemoryQuoteRecorder implements QuoteRecorder {
    // Class body in section 10.
}

@Profile("prod")
@Service
public class TransactionalQuoteRecorder implements QuoteRecorder {
    // Class body in section 12.
}
~~~

This snippet shows **where to place the annotations**, not an instruction to duplicate both classes side by side. Enable the `demo` profile or supply a mock bean in tests, and use the database implementation in production.

## 14. An Outbox Can Still Publish Duplicates

A transactional outbox prevents **losing publish intent** after a DB commit. It does not by itself guarantee the broker receives only one message.

~~~text
COMMIT Quote + OutboxEvent
            |
            v
Worker reads unpublished events
            |
            v
Publish to broker
            |
            v
Receive confirmation
            |
            v
Mark outbox record published
~~~

If the worker dies after publishing yet before updating the status, another worker can publish the same event again. Downstream must tolerate duplicates using a stable event ID and its own deduplication/idempotency.

### 14.1. Locks and Leases Do Not Eliminate the Crash Window

When multiple workers poll the outbox, use row locks, leases, or `FOR UPDATE SKIP LOCKED` on supported databases. That prevents concurrent contention, yet **does not eliminate** the window between successful publish and recording the status update.

### 14.2. Email and External APIs Are Outside the DB Transaction

~~~java
@Transactional
public void saveAndNotify(Quote quote) {
    repository.save(quote);
    emailClient.sendQuote(quote);
}
~~~

This exemplifies a false assumption. The email may send while the transaction rolls back. On retry, the email may send again. Record send intent in an outbox or pass an idempotency key if the provider supports one. `@Transactional` does not fuse two external systems into one atomic transaction.

## 15. When Should an Event Be Marked DONE?

Completion milestones depend on business requirements:

| Requirement | Completion Point |
|---|---|
| Calculate preview | Calculated and Quote returned |
| Save Quote | Inbox + Quote transaction commits |
| Save and emit event | Quote + outbox commits; publishing is a separate step |
| Send email | Distinguish queued, provider accepted, delivered |
| Grant access or charge payment | Requires business state and provider idempotency |

### 15.1. PROCESSING Is Not DONE

An idempotency table sometimes tracks states:

~~~text
RECEIVED → PROCESSING → DONE
                  |
                  +----> FAILED_RETRYABLE
                  |
                  +----> FAILED_FINAL
~~~

If `PROCESSING` commits separately and the worker dies, lease/timeout/recovery handling is required. When a duplicate request sees `PROCESSING`, never assume completion; wait, return an in-progress status, or schedule a recheck.

If both the inbox marker and Quote commit in a single short transaction, multiple durable intermediate states may not be needed. Pick the design based on I/O latency and recovery needs.

### 15.2. Replaying After Rules Change

If `evt-778` replays after a deployment raised prices, recomputing the same command can yield a different Quote. For stability:

1. Check command identity/fingerprint before processing.
2. If already processed, return the stored outcome instead of recalculating under new rules.
3. For new events, record the rule version or price snapshot used.
4. Distinguish replays from genuinely new create/update operations.

Because the simple Recorder in this example receives the Quote **after calculation**, production systems may move deduplication ahead of calculation or embed an immutable rule snapshot in the input. Preventing duplicate writes must go hand in hand with reproducible results.

## 16. Consumer Errors and Duplicates Have Different Meanings

A trailing `Consumer<Quote>` can:

- Finish normally after saving for the first time.
- Finish normally because the same key and payload were already committed.
- Throw `DuplicateConflictException` for the same key with a different payload.
- Throw an infrastructure error if the database is temporarily unavailable.
- Land in an **uncertain commit state** if connectivity drops.

Do not write:

~~~java
Consumer<Quote> unsafe = quote -> {
    try {
        recorder.recordOnce(quote);
    } catch (Exception ignored) {
        // Wrong: the adapter may assume it succeeded.
    }
};
~~~

If the binder relies on the Consumer outcome to ACK, swallowing errors can drop unprocessed events. Meanwhile, valid duplicates should finish normally (no-op) rather than being treated as transient errors needing infinite retries.

### 16.1. Do Not Launch Async Work and Ignore Its Outcome

~~~java
Consumer<Quote> unsafeAsync = quote -> {
    asyncGateway.save(quote); // Ignores completion/failure.
};
~~~

When `asyncGateway.save` returns a `CompletableFuture` or Publisher, the Consumer may return before the side effect completes. Use async contracts supported by the adapter, or track completion and failure properly within the framework; never call `subscribe()` fire-and-forget and discard the result.

## 17. HTTP: Idempotency-Key When Clients Resend POST

An API may receive:

~~~http
POST /quotes HTTP/1.1
Content-Type: application/json
Idempotency-Key: req-3af9

{"orderId":"ORD-42","sku":"SKU-7","quantity":2}
~~~

The `Idempotency-Key` header is **an application-defined contract**, not an automatic Spring Cloud Function feature. The server must scope the key by tenant/principal/operation, verify fingerprints, and store the outcome to serve resends.

### 17.1. Three Branches of a Request

~~~text
New key
    → validate → build Quote → COMMIT key + Quote
    → return initial response

Existing key, same fingerprint
    → do not write again
    → read/return stored outcome

Existing key, different fingerprint
    → conflict
    → do not overwrite and emit no side effect
~~~

Depending on the API, the server may return `201` on creation, `200` when returning stored results, or replay the original response; async work may use `202`. Define statuses explicitly in your API contract rather than assuming defaults from Spring Cloud Function.

### 17.2. Post-Commit Before Response

~~~text
Client                      Server
    |                         |
    | POST key=K              |
    |------------------------>|
    |                         | COMMIT
    |       response lost    X|
    |                         |
    | POST key=K              |
    |------------------------>|
    |                         | Look up committed key
    |<------------------------|
    | receives stored result  |
~~~

Without idempotency, an HTTP client resend can insert a second record or send another notification. Storing only the key without the response data avoids duplicate writes yet may fail to return a meaningful reply. Persist needed response state inside the same commit boundary when required.

### 17.3. Keys Do Not Replace Security

One client must never read another tenant's result merely by guessing a key. Enforce authorization independently; scope keys by tenant, operation, or trusted identity per business rules. Enforce size/format limits and avoid logging sensitive keys per policy.

### 17.4. Updates Are Different Operations

`POST CreateQuote(ORD-42)` and `PUT UpdateQuote(ORD-42,version=2)` are distinct operations. Do not let a create marker accidentally block valid updates. Use separate keys/versions and overwrite protection.

## 18. Messaging: ACK Only After Safe Persistence

With Spring Cloud Stream, a synchronous Consumer bean can orchestrate the pure Functions and write port:

~~~java
package example.functions;

import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderCommand;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

@Configuration
public class OrderMessageHandler {

    @Bean
    public Consumer<OrderCommand> receiveOrder(
            @Qualifier("normalizeOrder")
            Function<OrderCommand, OrderCommand> normalize,
            @Qualifier("validateOrder")
            Function<OrderCommand, ValidatedOrder> validate,
            @Qualifier("calculateQuote")
            Function<ValidatedOrder, Quote> calculate,
            QuoteRecorder recorder) {

        return raw -> {
            OrderCommand input = normalize.apply(raw);
            ValidatedOrder valid = validate.apply(input);
            Quote quote = calculate.apply(valid);
            recorder.recordOnce(quote);
        };
    }
}
~~~

This bean illustrates explicit orchestration while reusing the business Functions. In apps using name-based composition, an equivalent expression can be used, verified against your framework version.

### 18.1. Illustrative Binding

~~~yaml
spring:
  cloud:
    function:
      definition: receiveOrder
    stream:
      bindings:
        receiveOrder-in-0:
          destination: order-commands
          group: quote-service
~~~

You still need binder, converter, retry, DLQ, and acknowledgement configuration matching your broker and version. `definition` and `bindings` do not create database deduplication on their own.

### 18.2. Completion Order

~~~text
Broker delivers message
       |
       v
Deserialize and validate
       |
       v
DB transaction: inbox + Quote + outbox
       |
       v
COMMIT succeeds
       |
       v
ACK per binder policy
~~~

If ACK happens before commit and the process crashes, work can be lost. If ACK happens after commit and ACK fails, the broker can redeliver; inbox and unique constraints handle it without new side effects.

Do not assume every binder ACKs this way. Integration-test against your real Kafka/RabbitMQ setup, consumer type, delivery semantics, and configuration.

### 18.3. Valid Duplicates Finish Successfully

When an old event arrives again with the same fingerprint and prior data already committed, the Recorder finishes normally without writing again. Thus redelivery counts as handled, avoiding retry loops on already-completed events.

If the same key arrives with a different payload, that is a conflict to report or quarantine per policy—**never** silently ACK it as a normal duplicate.

### 18.4. Poison Messages Differ from Transient Failures

| Failure | Reference Policy |
|---|---|
| Permanently invalid JSON/schema | Adapter may reject / route to DLQ |
| Quantity 0 | Do not retry indefinitely |
| DB connection timeout | Bounded retry with idempotency |
| DB committed then ACK lost | Redelivery, inbox no-op |
| Different payload with same event ID | Conflict, observe and investigate |

DLQ, requeue, retry, ack, and error-channel behavior depend on binder and version. Consumer groups or partitions do not replace transactions and uniqueness on redelivery.

## 19. Serverless: Reinvocation on a New Instance

A serverless platform can reinvoke an event after a timeout or failure, and the second call may land on a different instance.

~~~text
Event evt-778
    |
    v
Invocation 1 (instance A)
    |
    +-- DB COMMIT
    +-- timeout before response
    |
    v
Platform reinvokes event
    |
    v
Invocation 2 (instance B)
    |
    +-- reads shared inbox
    +-- valid duplicate → no-op
~~~

Static fields or a `HashMap` in instance A cannot protect instance B. Shared durable storage and stable idempotency keys are required.

### 19.1. Event Identity and Business Identity

A trigger may supply its own event ID; inspect the real schema. If a producer republishes the same business operation with a fresh event ID, event-ID deduplication is not enough. Unique keys on tenant, order, and operation/version remain necessary.

### 19.2. Nested Retries and Deadlines

An application may retry I/O within one invocation, while the cloud trigger may reinvoke the whole handler. Never pick backoff intervals longer than remaining execution time; bound total attempts and deadlines. Idempotency covers both internal retries and fresh invocations.

### 19.3. Never Report Success Before Side Effects Complete

Catching all exceptions and returning success can lose uncommitted work. Conversely, if commit succeeded while the response failed, reinvocations should look up the key and return the stored outcome rather than writing again.

## 20. Reactor: Resubscription Can Repeat Side Effects

A pure Function can run inside a `Flux`:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

import example.functions.OrderModels.OrderCommand;
import example.functions.OrderModels.Quote;

Function<OrderCommand, Quote> core = catalog.lookup(
        "normalizeOrder|validateOrder|calculateQuote");

if (core == null) {
    throw new IllegalStateException("Missing core");
}

Function<Flux<OrderCommand>, Flux<Quote>> quoteStream =
        flux -> flux.map(core);
~~~

Here `catalog` is an injected dependency. The mapper usually runs when a subscription receives elements, not when the pipeline is constructed.

If you add a side effect:

~~~java
Flux<Quote> withWrite = inputFlux
        .map(core)
        .doOnNext(recorder::recordOnce);
~~~

With a cold Publisher, resubscribing or retrying can call the Recorder again. `doOnNext` here illustrates the hazard; never rely on it as a durable persistence transaction mechanism.

### 20.1. Whole-Flux Retry Re-Emits Elements Before the Error

~~~java
Flux<Integer> values = Flux.just("1", "bad", "3")
        .map(Integer::parseInt)
        .retry(1);
~~~

A subscriber can receive:

~~~text
onNext(1)
onNext(1)
onError(NumberFormatException)
~~~

`retry(1)` resubscribes to the entire upstream. If a Consumer already persisted `1`, the retry can persist it again.

### 20.2. Per-Inner-Publisher Retries

~~~java
Flux<Quote> result = inputEvents
        .concatMap(command ->
            service.process(command)
                .retryWhen(retryPolicy));
~~~

`inputEvents`, `service.process`, and `retryPolicy` are illustrative dependencies. Placing retry inside the inner Publisher retries only the current command without re-emitting earlier items of the outer Flux.

Still, the same command can be retried after committing if confirmation was lost, so `service.process` still requires idempotency. If an inner Publisher exhausts retries and errors, decide whether to terminate the whole stream or isolate that message.

### 20.3. Do Not Swallow Errors Arbitrarily with Mono.empty

Putting `onErrorResume(error -> Mono.empty())` on every error can make the adapter treat a message as handled even though the DB never committed. Return empty only when business rules allow skipping and transport handles quarantine/ack properly.

### 20.4. Self-Subscribing Async Consumers Return Too Early

~~~java
Consumer<Flux<Quote>> unsafe = flux -> {
    flux.subscribe(recorder::recordOnce);
};
~~~

If `accept` returns while the Publisher is still running, the binder may miss async errors when deciding ACK/retry. Follow the adapter's reactive contract and lifecycle.

### 20.5. Reactive Transactions Differ from JDBC Transactions

With R2DBC, reactive transaction managers attach to the Publisher context. With blocking JDBC, imperative transactions normally rely on threads and proxies. Never assume `@Transactional` on a `Mono`-returning method covers JDBC calls running on another scheduler; verify the datasource, transaction manager, proxy, and actual subscription.

## 21. Even Bounded Retries Still Require Idempotency

Even a single retry can write twice if the first attempt commits and the response is lost:

~~~text
Attempt 1: COMMIT succeeds → timeout
Attempt 2: reprocesses same key
~~~

If storage has an inbox or unique constraint, attempt 2 recognizes the replay and finishes as a no-op. Without it, retrying with short or long backoff can still create a duplicate side effect.

### 21.1. Classify Errors Before Retrying

| Error | Action |
|---|---|
| Invalid input | Reject, do not retry same payload |
| Same key with different payload | Conflict, do not overwrite |
| Transient DB disconnect | Bounded retry if idempotent |
| Uncertain commit state | Look up key or perform idempotent retry |
| Already-completed duplicate | No-op and finish |
| Programming bug | Do not mask failures with retries |

### 21.2. Retrying Only the Recorder Operation in Reactor

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.retry.Retry;

Mono<Void> persisted = Mono.<Void>fromRunnable(
        () -> recorder.recordOnce(quote))
    .subscribeOn(Schedulers.boundedElastic())
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(error ->
                error instanceof OrderErrors.TransientStoreException));
~~~

Here `recorder` and `quote` are provided dependencies. `Retry.backoff(2, ...)` allows up to two additional retries; `boundedElastic` isolates blocking calls without making JDBC non-blocking.

The filter excludes validation and conflict errors. Nevertheless, retries can still invoke `recordOnce` after an unconfirmed commit, making storage-level idempotency mandatory.

### 21.3. Do Not Retry an Entire Event-Publishing Chain

If a workflow has `recordQuoteOnce` and `publishQuoteCreated`, retrying at the end can call both again. The Quote may be deduplicated while the message still publishes twice. Use an outbox and downstream deduplication when needed, rather than assuming composition spans two systems transactionally.

## 22. Failure Windows That Must Be Tested

| Failure Point | Expected State | Required Verification |
|---|---|---|
| Before validation | No side effects | No DONE marker |
| After validation, before transaction | Nothing written | Retries do not repeat side effects |
| After inbox claim, before Quote (uncommitted) | Transaction rolls back | Claim rolls back too |
| After Quote insert, before outbox (uncommitted) | Transaction rolls back | No orphaned Quote |
| After commit, before ACK | Inbox, Quote, outbox present | Redelivery is a no-op |
| After publish, before marking outbox | Broker may already have message | Publisher resends same event ID |
| Two workers with same event ID | Unique constraint race | One winner, no extra Quote |
| Two event IDs for same create op | Inbox does not match | Business uniqueness protects |
| Same event ID, different payload | Conflicting data | Conflict, no overwrite |
| Replay after rule update | Recalculated price differs | Snapshot or stored result returned |
| Worker dies in PROCESSING | Marker not DONE | Lease/recovery prevents permanent stall |

### 22.1. Transactions Must Match the Completion Milestone

If the inbox marker commits in transaction A and the Quote writes in transaction B, crashing between commits leaves inconsistent state. Ensure changes that must succeed together share one appropriate transaction.

### 22.2. Not Every Side Effect Can Roll Back

A sent email, an accepted payment gateway call, or a published broker event will not automatically roll back when the DB fails. Such steps need provider idempotency, outboxes, sagas, or compensating actions per business requirements.

### 22.3. Duplicates Are Not Always Operational Failures

A redelivered event that already succeeded is expected under at-least-once delivery. Measure duplicates and handle them as no-ops. Sudden spikes in duplicates still help diagnose lost ACKs, retry storms, or producer bugs.

## 23. Retention, TTL, and Historical Replays

`processed_event` cannot grow forever without a retention strategy, yet purging markers too early causes old events to be processed as new.

### 23.1. Keep Keys Long Enough

Retention must consider:

- Maximum broker redelivery window.
- How long events sit in DLQs/quarantine before manual replay.
- How long clients can resend requests with the same idempotency key.
- Audit, legal, and data-protection policies.
- Whether producers might replay historical events much later.

If markers expire after one hour and an event replays seven days later, the inbox treats it as new. Business unique constraints may still block duplicate Quotes, yet other side effects must be protected independently.

### 23.2. Business-Key Deduplication May Outlive Event Markers

For `CreateQuote`, the `(tenantId, orderId)` unique key typically lives alongside the Quote record across its business lifecycle, while event markers may carry a TTL. That adds defense in depth for very late replays.

For updates/deletes, keep versions or sequence numbers and sufficient history to tell new operations apart from stale replays. Never assume every event on an order is a duplicate.

### 23.3. Marker Cleanup Must Also Be Controlled

Cleanup jobs must avoid deleting markers active in transactions or incomplete workflows. When using status tables, distinguish `DONE`, `FAILED_FINAL`, and `IN_PROGRESS` before archiving. Never delete markers simply because a transient error occurred.

### 23.4. Securing Deduplication Data

Store only necessary fingerprints and metadata; do not keep personal payloads longer than policy allows. Hashing alone does not anonymize low-entropy inputs. Apply access controls, encryption, restricted logging, and proper retention.

## 24. Unit Tests: Redelivered Events Do Not Write Twice

The following JUnit 5 tests use `InMemoryQuoteRecorder` to verify business rules. They **do not** prove production database transactions, yet quickly catch regressions that break deduplication semantics.

### 24.1. Recording the Same Event Twice

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;

class QuoteRecorderIdempotencyTest {

    @Test
    void sameEventIsRecordedOnlyOnce() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        Quote quote = new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L);

        recorder.recordOnce(quote);
        recorder.recordOnce(quote);

        assertEquals(1, recorder.quoteCount());
        assertEquals(1, recorder.handledEventCount());
        assertEquals(
                quote,
                recorder.find("shop-a", "ORD-42"));
    }
}
~~~

This test shows that retrying/redelivering **the same event ID and same payload** is a no-op on the second call.

### 24.2. Same Event ID with Different Payload Is a Conflict

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.DuplicateConflictException;

class ConflictingEventTest {

    @Test
    void sameEventIdWithDifferentPayloadIsRejected() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        Quote original = new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L);

        Quote conflicting = new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                3, 375_000L);

        recorder.recordOnce(original);

        assertThrows(DuplicateConflictException.class,
                () -> recorder.recordOnce(conflicting));

        assertEquals(1, recorder.quoteCount());
        assertEquals(1, recorder.handledEventCount());
        assertEquals(
                original,
                recorder.find("shop-a", "ORD-42"));
    }
}
~~~

Same key alone does not imply a valid replay. If the payload changes, never silently skip or overwrite.

### 24.3. New Event ID, Same Business Operation

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;

class NewEventSameBusinessOperationTest {

    @Test
    void newEventIdDoesNotCreateSecondQuote() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        recorder.recordOnce(new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L));

        recorder.recordOnce(new Quote(
                "evt-779", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L));

        assertEquals(1, recorder.quoteCount());
        assertEquals(2, recorder.handledEventCount());
    }
}
~~~

This is **this example's create-only rule**. If a new event represents a valid update, use a separate operation/version and test—do not apply this rule blindly to all order actions.

### 24.4. Two Tenants with the Same Order ID

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;

class TenantScopedIdempotencyTest {

    @Test
    void tenantsWithSameOrderIdAreIndependent() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        recorder.recordOnce(new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L));

        recorder.recordOnce(new Quote(
                "evt-778", "shop-b",
                "ORD-42", "SKU-7",
                2, 250_000L));

        assertEquals(2, recorder.quoteCount());
        assertEquals(2, recorder.handledEventCount());
    }
}
~~~

This test shows idempotency keys must be **scoped** by tenant. Never use a client-supplied ID as a global key if multiple tenants can generate matching IDs.

## 25. Concurrent Unit Test: Two Workers on the Same Event

Deduplicating in a single thread is not enough. HTTP or messaging systems can process concurrent requests arriving closely together.

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;

class ConcurrentDeduplicationTest {

    @Test
    void concurrentReplayStillCreatesOneQuote()
            throws Exception {

        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        Quote quote = new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L);

        int workers = 12;
        ExecutorService pool =
                Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                tasks.add(pool.submit(() -> {
                    try {
                        start.await();
                        recorder.recordOnce(quote);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(ex);
                    }
                }));
            }

            start.countDown();

            for (Future<?> task : tasks) {
                task.get(5, TimeUnit.SECONDS);
            }

            assertEquals(1, recorder.quoteCount());
            assertEquals(1, recorder.handledEventCount());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

`synchronized` inside the Recorder makes this example thread-safe within one process. However, **two JVM instances** do not share locks or maps; this test does not prove cross-instance production behavior. With a database, test two concurrent transactions inserting the same key and verify unique constraints and rollbacks.

### 25.1. Also Test Concurrent Conflicts

With two workers sharing `eventId` where one carries quantity 2 and the other quantity 3, only one can succeed; the other must conflict without overwriting. Which worker wins depends on thread scheduling, so tests must not hard-code that worker A always wins.

### 25.2. Application Locks Do Not Replace Unique Constraints

A Java `synchronized` block does not stop instance B from processing the same event. Even distributed locks require lease expiry, fencing tokens, and recovery. When business state lives in a relational database, unique constraints and transactions are the primary line of defense.

## 26. Integration Testing FunctionCatalog and Consumer

Create a Spring Boot application in the same package as the example beans:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }
}
~~~

With the `demo` profile for `InMemoryQuoteRecorder` and Spring Cloud Function context active, test name composition:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.test.context.ActiveProfiles;

import example.functions.OrderModels.OrderCommand;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@SpringBootTest(classes = QuoteApplication.class)
@ActiveProfiles("demo")
class QuoteCatalogReplayTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    InMemoryQuoteRecorder recorder;

    @Test
    void purePipelineReturnsQuote() {
        Function<OrderCommand, Quote> core = catalog.lookup(
                "normalizeOrder|validateOrder|calculateQuote");

        assertNotNull(core);

        Quote output = core.apply(new OrderCommand(
                "evt-801", "shop-a",
                " ord-801 ", " sku-7 ", 2));

        assertEquals(250_000L, output.totalVnd());
        assertEquals("ORD-801", output.orderId());
    }

    @Test
    void redeliveryDoesNotCreateSecondQuote() {
        Consumer<OrderCommand> pipeline = catalog.lookup(
                "normalizeOrder|validateOrder"
                + "|calculateQuote|recordQuoteOnce");

        assertNotNull(pipeline);

        OrderCommand command = new OrderCommand(
                "evt-802", "shop-a",
                "ORD-802", "SKU-7", 2);

        pipeline.accept(command);
        pipeline.accept(command);

        assertEquals(
                new Quote(
                    "evt-802", "shop-a",
                    "ORD-802", "SKU-7", 2, 250_000L),
                recorder.find("shop-a", "ORD-802"));
    }

    @Test
    void invalidDataDoesNotReachRecorder() {
        Consumer<OrderCommand> pipeline = catalog.lookup(
                "normalizeOrder|validateOrder"
                + "|calculateQuote|recordQuoteOnce");

        assertNotNull(pipeline);

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(new OrderCommand(
                    "evt-803", "shop-a",
                    "ORD-803", "SKU-7", 0)));

        assertEquals(null, recorder.find(
                "shop-a", "ORD-803"));
    }
}
~~~

This suite verifies bean names, composition order, type contracts, and duplicate-write prevention **within a demo Spring context**. When running tests in parallel against a shared context, isolate or reset the Recorder or use unique keys per test; do not treat the example as an isolation strategy for every CI configuration.

### 26.1. Running on the prod Profile

The `prod` profile requires real database implementations of `ProcessedEventStore`, `QuoteTable`, `OutboxTable`, and `QuoteFingerprint`. You cannot run production integration tests with an in-memory implementation and claim transactions were verified.

### 26.2. Testing Pre-Commit vs. Post-Commit Failures

Unit tests can verify that validation failures never invoke the Recorder. Yet **database commit followed by lost ACK** needs storage/adapter integration tests or a fault-injection harness simulating lost confirmation **after commit**.

The goal is not merely observing exceptions: verify **Quote count**, **inbox marker count**, **outbox event count**, and post-redelivery state.

## 27. Testing Real Databases: Transactions, Concurrency, and Crash Windows

In-memory tests verify decision logic, whereas database integration tests verify uniqueness, transaction isolation, and crash/recovery scenarios tied to storage.

### 27.1. Transactional Inbox Test Matrix

| Scenario | Failure Point | Expected State After Restart/Redelivery |
|---|---|---|
| Valid new event | No failure | One inbox marker, one Quote, one outbox event |
| Duplicate with same event ID | After first commit | Quote/outbox count unchanged |
| Same event ID, different payload | Reads old fingerprint | Conflict, prior data preserved |
| Two event IDs for same create op | Two concurrent transactions | Business unique constraint blocks second Quote |
| Fail after claim, before Quote insert | Inside transaction | Claim rolls back; next attempt can succeed |
| Fail after Quote insert, before outbox insert | Inside transaction | Both Quote and claim roll back |
| Fail after commit, before ACK | Outside transaction | Next delivery reads marker and no-ops |
| Process dies with PROCESSING marker | After separate claim | Lease/recovery prevents permanent stall |
| Outbox publisher dies after publish | After broker ACK, before marking published | Publish may repeat same event ID |
| Downstream consumer receives duplicate | Downstream inbox already committed | No second business side effect |

With real PostgreSQL, use Testcontainers or an isolated database environment to verify transactions. Do not test against H2 and assume `ON CONFLICT`, locks, or isolation semantics match PostgreSQL.

### 27.2. Testing Two Concurrent Transactions

A scenario worth testing:

~~~text
Transaction A                         Transaction B
-------------                         -------------
INSERT inbox evt-778
                                      INSERT inbox evt-778
                                      waits on unique constraint
INSERT Quote
INSERT Outbox
COMMIT
                                      detects duplicate
                                      compares fingerprint
                                      skips Quote/Outbox writes
                                      completes
~~~

Afterward, query the state:

~~~sql
SELECT COUNT(*)
FROM processed_event
WHERE tenant_id = 'shop-a'
  AND event_id = 'evt-778';

SELECT COUNT(*)
FROM order_quote
WHERE tenant_id = 'shop-a'
  AND order_id = 'ORD-42';

SELECT COUNT(*)
FROM outbox_event
WHERE tenant_id = 'shop-a'
  AND order_id = 'ORD-42'
  AND event_type = 'QuoteCreated';
~~~

Under this lesson's create-only rules, each count should equal **1**. If any query returns 2, uniqueness or transaction design is broken. When a system supports multiple operations/versions per order, adjust the query filters and invariants accordingly.

### 27.3. Injecting Post-Commit Errors Differently from Rollbacks

An integration test can deliberately:

1. Invoke the handler to execute the Quote + inbox transaction.
2. Allow the transaction to commit for real.
3. Simulate a lost ACK/response in the adapter without rolling back the DB.
4. Invoke the same event again.
5. Verify no new Quote or outbox record was created.
6. Verify the caller receives the appropriate stored state or outcome.

If tests only throw exceptions **before commit**, they miss redelivery's most dangerous failure mode.

### 27.4. Testing Same Event ID with Changed Payload

Send `evt-778` first with quantity 2, then resend `evt-778` with quantity 3. Tests must verify:

- The second call raises a conflict.
- The Quote retains quantity 2 and total 250000.
- Outbox emits no second event.
- No silent update happens.
- Conflicts emit diagnostic logs/metrics without leaking sensitive payloads.

### 27.5. Testing the Outbox Publisher After a Crash

If the publisher sent `outboxId=X` and lost connectivity before marking it published, a new worker may send `X` again. Test that **the downstream subscriber**, backed by its own inbox, receives two deliveries yet produces only one business side effect.

This is an end-to-end publisher-and-consumer test, not something proven by unit testing `QuoteRecorder`.

## 28. Observability: Distinguishing Valid Duplicates from Errors

Metrics must capture more than exception counts. To diagnose redeliveries and deduplication behavior, measure:

- `events_received_total`: total deliveries received, including duplicates.
- `events_processed_new_total`: newly committed operations.
- `events_duplicate_total`: known events with matching fingerprints (no-ops).
- `events_conflict_total`: same key with different payload.
- `events_invalid_total`: invalid input or schema.
- `event_processing_attempts`: adapter/application retry attempts.
- `inbox_claim_latency`: wait time on locks or unique conflicts.
- `transaction_rollback_total` by cause category.
- `outbox_pending`, `outbox_oldest_age`, `outbox_publish_retries`.
- `message_redelivery_total`, `dlq_count` per binder when exposed.

These metric names are **application suggestions**, not built-in Spring Cloud Function defaults.

### 28.1. Correlation IDs and Idempotency Keys

A structured log entry might contain:

~~~text
event=quote_processing
tenant=shop-a
eventId=evt-778
orderId=ORD-42
outcome=duplicate_noop
attempt=2
source=stream-consumer
~~~

Avoid logging full customer payloads, sensitive payment details, or tokens. Enforce privacy, log access controls, and retention policies.

### 28.2. Identifying Where Repeats Originate

A request can repeat across multiple layers. Where available, record:

| Field | Meaning |
|---|---|
| `operationId` | Identifier of one business operation |
| `eventId` | Identifier of the delivered event |
| `deliveryCount` | Delivery count if reliably provided by adapter |
| `attemptIndex` | Application-level retry attempt number |
| `retryOwner` | App, HTTP client, binder, cloud trigger |
| `outcome` | New, duplicate, conflict, invalid, failed |
| `commitStatus` | Known committed / rolled back / unknown |
| `durationMs` | Processing time |
| `traceId` | Cross-component trace correlation |

Do not assume a `deliveryCount` header exists or is authoritative on every broker—it may be best-effort metadata. Likewise, an application `attemptIndex` does not reveal total broker redeliveries.

### 28.3. Meaningful Alerts

- Sudden spike in duplicates: possible lost ACKs, retry storms, or noisy producers.
- Rising conflicts: possible bad key reuse or payload-mutating bugs.
- Long inbox claim waits: contention or lock hotspots.
- Growing outbox backlog: publisher or downstream falling behind.
- Rising post-commit errors: inspect transport, deadlines, and status responses.
- Growing DLQ poison messages: schema/version drift or validation mismatches.

A duplicate no-op is often normal expected behavior; metrics should surface **trends** rather than firing urgent pages on every single duplicate.

## 29. Common Design Mistakes

| Poor Design | Risk | Improvement |
|---|---|---|
| Write inbox first and commit separately | Crash before Quote write causes event to be skipped | Inbox + Quote in the same transaction |
| Write Quote first, marker afterward | Crash before marker causes replay to write again | Shared transaction and uniqueness |
| Using only `HashMap` or static state | Replicas and restarts do not share state | Shared durable storage |
| Deduplicating only by event ID | A new event ID can carry the same operation | Business uniqueness / version |
| Deduplicating only by order ID | Blocks valid subsequent updates | Distinguish operations / versions |
| Ignoring same key with different payload | Masks conflicts | Fingerprints and conflict errors |
| Including receipt timestamp in hash | Content-identical replays hash differently | Canonical payload without delivery metadata |
| Replaying against updated pricing rules | Old events produce different totals | Snapshots/versions or stored results |
| ACKing before database commit | Process crash can lose events | Finish transaction before ACK per adapter |
| Catching all errors in Consumer | Adapter thinks processing succeeded | Classify and propagate errors |
| Retrying full chain containing email/publish | Repeated external side effects | Outbox, provider idempotency |
| Assuming outbox guarantees exactly-once | Crash can repeat publishes | Downstream inbox/dedupe |
| Inbox TTL too short | Late replays look like new events | Match retention to replay window |
| Treating PROCESSING as DONE | Duplicates skipped before completion | Leases/recovery and clear states |
| Using `@Transactional` for external APIs | Remote effects do not roll back with DB | Outbox/saga or provider idempotency |
| Testing only sequential single calls | Misses race conditions | Concurrency and fault-injection tests |

### 29.1. Anti-Pattern: Non-Atomic Check-Then-Write

~~~java
if (!eventRepository.exists(eventId)) {
    quoteRepository.save(quote);
    eventRepository.markProcessed(eventId);
}
~~~

Without unique constraints and a shared transaction, two workers can both observe the key missing and write duplicates. If the process dies between `save` and `markProcessed`, the next attempt cannot tell whether the earlier write committed.

Replace with a unique-key claim in the same transaction as business data.

### 29.2. Anti-Pattern: Catch-All Returning Success

~~~java
try {
    recorder.recordOnce(quote);
} catch (Exception ex) {
    return "SUCCESS"; // Wrong: unknown whether it committed.
}
~~~

An exception does not prove whether a side effect failed or succeeded. Error boundaries must classify failures, query state by key when needed, and avoid fake success replies.

### 29.3. Anti-Pattern: Checking Duplicates After Sending Email

~~~text
sendEmail(...)
checkProcessed(eventId)
~~~

Once the email is sent, detecting a duplicate afterward cannot unsend it. Guard external side effects via outboxes or provider idempotency rather than tacking deduplication onto the very end.

## 30. Pre-Production Checklist

### 30.1. Identity and Data

- [ ] Clearly defined what counts as one business operation.
- [ ] Event/request ID stays stable across retries, redeliveries, and reinvocations.
- [ ] Idempotency keys are scoped by tenant, operation, and version where needed.
- [ ] Same key with different payload is detected and rejected.
- [ ] Canonical semantic fingerprint is documented clearly.
- [ ] Rule versions/snapshots are managed for replays of old data.
- [ ] Valid updates are not mistakenly blocked as create duplicates.

### 30.2. Transactions and Side Effects

- [ ] Inbox marker, Quote, and outbox commit atomically on the same datasource.
- [ ] Storage enforces unique constraints or atomic writes for concurrent workers.
- [ ] `DONE` is distinct from `PROCESSING` and uncertain commits.
- [ ] Post-commit / pre-ACK crash scenarios have a defined recovery path.
- [ ] Outbox publisher uses claims/leases and downstream deduplicates.
- [ ] Emails, payments, and external APIs use idempotency or dedicated recovery.
- [ ] Stuck markers/leases have a recovery mechanism.

### 30.3. Spring Cloud Function and Adapters

- [ ] Validation and pure Functions run before side-effecting Consumers.
- [ ] `FunctionCatalog` registers and composes names and types accurately.
- [ ] `definition` selects the right pipeline/binding in the live environment.
- [ ] HTTP resends with the same `Idempotency-Key` create no duplicate operations.
- [ ] Message binders observe completion/errors properly for ACK/retry/DLQ.
- [ ] Serverless reinvocations on another instance still deduplicate through the DB.
- [ ] Reactive retries/resubscriptions do not repeat side effects uncontrollably.
- [ ] Retries are bounded and never wastefully repeat validation or conflict errors.

### 30.4. Testing and Operations

- [ ] Tested the same event delivered twice and multiple times.
- [ ] Tested same key with different payload.
- [ ] Tested new event ID for the same business operation.
- [ ] Tested two tenants sharing the same order ID.
- [ ] Tested concurrent workers processing one event.
- [ ] Tested crashes before commit, after commit, and after publish.
- [ ] Tested against a real database, not just in-memory stores.
- [ ] Tested the actual HTTP/message/serverless adapter used in deployment.
- [ ] Metrics track new, duplicate, conflict, and outbox pending counts.
- [ ] Inbox retention matches replay windows and data policies.

Without these verifications, state current limitations honestly instead of promising end-to-end exactly-once semantics.

## 31. Practice Exercises

**Exercise 1 — Lost ACK.** The broker delivers `evt-778`, the Consumer saves the Quote, and the process dies before ACK. The broker redelivers the event. Describe the inbox/Quote/outbox state before and after redelivery.

**Exercise 2 — Key Misuse.** An event ID is sent with quantity 2, then the same event ID arrives with quantity 3. Why is checking the key and returning early insufficient? What error should be raised?

**Exercise 3 — New Event ID for the Same Operation.** The producer sends `evt-778: CreateQuote(ORD-42,2)` and then `evt-779: CreateQuote(ORD-42,2)`. The inbox treats the second event as new. Which mechanism blocks creating a second Quote?

**Exercise 4 — Valid Updates.** After creating `ORD-42`, the app receives `UpdateQuote(ORD-42,version=2)`. Why can deduplicating solely by `orderId` wrongly block valid operations?

**Exercise 5 — Two Workers.** Two replicas both see an event missing via `SELECT`. Why can both write duplicates? Propose a unique key and transaction.

**Exercise 6 — Split Transactions.** Transaction A commits a `DONE` marker; transaction B writes the Quote. The process crashes after A and before B. What is the consequence? Propose a new transaction boundary.

**Exercise 7 — Outbox.** A publisher sends `QuoteCreated` to the broker and crashes before marking it published. A new worker sends it again. Why does downstream still need an inbox?

**Exercise 8 — HTTP.** A client sends `POST` with `Idempotency-Key=req-3af9`, the response is lost after DB commit, and the client resends. How do you return the stored outcome? What if the new payload differs?

**Exercise 9 — Serverless.** Two invocations process the same event on two different instances. Why is a `static ConcurrentHashMap` not production deduplication?

**Exercise 10 — Reactor.** Given `Flux.just("1","bad","3").map(Integer::parseInt).retry(1)`, predict the signals. If `1` triggers a data write, what is the risk?

**Exercise 11 — Validation.** An event has quantity `0`. Why must the Consumer reject it before writing? Does retrying the same payload make it valid?

**Exercise 12 — Rule Versions.** An old event replays after prices increase. If recalculated and compared against the stored Quote, how could a false conflict occur? Propose preserving snapshots or command fingerprints.

**Exercise 13 — Concurrency Test.** Design a test with 12 threads calling `recordOnce` concurrently for the same Quote. What assertions are needed besides no exceptions?

**Exercise 14 — TTL.** The inbox purges markers after 24 hours, yet DLQs may replay after 30 days. What protection remains? How would you choose retention?

**Exercise 15 — Email.** A `@Transactional` method saves a Quote and sends an email. Why does a DB rollback not undo the email? How do you reduce duplicate email risk?

**Exercise 16 — ACK and Async Completion.** A `Consumer<Flux<Quote>>` self-subscribes and returns immediately. What can happen with ACK if an error occurs inside the subscription?

**Exercise 17 — Tenant Scope.** Shop A and Shop B both use `orderId=ORD-42` and `eventId=evt-778`. Why must event ID alone not be a global key?

**Exercise 18 — Fault Injection.** Pick three crash points across the inbox/Quote/outbox transaction and publishing flow. For each point, state the invariant to check upon reprocessing.

**Exercise 19 — Duplicates and Alerts.** Why is a duplicate no-op not necessarily an incident, yet a sharp rise in duplicate rate still warrants attention?

**Exercise 20 — FunctionCatalog.** Compare definitions `normalizeOrder|validateOrder|calculateQuote` and `normalizeOrder|validateOrder|calculateQuote|recordQuoteOnce`. Which pipeline has side effects, and does the framework deduplicate automatically?

### Suggested Answers

- **Exercise 1:** The DB already committed, so redelivery reads the inbox, creates no new Quote/outbox, and finishes per the binder's ACK policy.
- **Exercise 2:** A matching key does not prove matching payloads. Compare fingerprints and raise a conflict while keeping the prior record.
- **Exercise 3:** A unique business key scoped by tenant, order, and operation/version; compare Quote contents.
- **Exercise 4:** Create and Update are distinct operations requiring separate operation/version/optimistic-locking handling.
- **Exercise 5:** `SELECT` then `INSERT` has a race condition. Use unique constraints and atomic claims/writes inside a transaction.
- **Exercise 6:** A `DONE` marker without a saved Quote causes the event to be skipped. Inbox and Quote must commit together.
- **Exercise 7:** A crash after publishing lets the outbox event be republished; downstream consumers deduplicate by event ID.
- **Exercise 8:** Retrieve the stored state/response by the committed key; different payloads must raise a conflict without overwriting.
- **Exercise 9:** Instances do not share memory and can restart; use durable shared storage with stable keys.
- **Exercise 10:** Can emit `1` twice then `onError`; storage must be idempotent whenever callbacks can rerun.
- **Exercise 11:** Invalid data never fixes itself on retry; validate before side effects.
- **Exercise 12:** New rules produce a different Quote for the same command; store rules/snapshots or detect replays before recalculating.
- **Exercise 13:** Synchronize start with a latch, await all futures, and verify only one Quote and one event were recorded.
- **Exercise 14:** Business uniqueness blocks some duplicates, yet inbox retention should match real replay windows and data policies.
- **Exercise 15:** Email lives outside the DB; use an outbox and provider idempotency keys where supported.
- **Exercise 16:** The binder may ACK before the async Publisher finishes, missing errors; manage terminal signals per contract.
- **Exercise 17:** Keys must be scoped by tenant/principal/operation to avoid cross-customer collisions.
- **Exercise 18:** Before commit: both marker and Quote roll back; after commit before ACK: no-op; after publish before mark: may republish while downstream deduplicates.
- **Exercise 19:** Duplicates can be normal under at-least-once delivery; rising rates signal ACK, retry, or producer issues.
- **Exercise 20:** The first returns a pure `Function<OrderCommand,Quote>`; appending the Consumer yields `Consumer<OrderCommand>` with side effects. `FunctionCatalog` does not implement idempotency automatically.

## 32. Key Takeaways

- **A single business request can arrive multiple times** via HTTP client retries, broker redeliveries, serverless reinvocations, DLQ replays, or Reactor resubscriptions.
- A pure calculation Function is safe to rerun, whereas **a side-effecting Consumer** must be guarded by business idempotency—not Java syntax alone.
- Deduplicating by `eventId` detects redelivered messages; **business keys and operation versions** protect against producers emitting new event IDs for the same operation.
- Same key and same payload can be handled as a no-op; **same key with different payload is a conflict** that must be detected.
- **Commit inbox, Quote, and outbox together** when they must succeed atomically; unique constraints resolve concurrent worker races.
- ACKing after commit still leaves a redelivery window if the ACK is lost; storage must tolerate redeliveries.
- A transactional outbox reduces lost events yet can still publish duplicates; downstream consumers must be idempotent.
- HTTP `Idempotency-Key`, Spring Cloud Stream binders, and serverless triggers each carry their own contracts. `FunctionCatalog` and `spring.cloud.function.definition` do not provide exactly-once guarantees automatically.
- Retention, rule versions/snapshots, and business operations must be designed so late replays never corrupt results.
- **Reliability is proven by post-failure and post-replay state**, along with concurrency and crash-window tests—not just the absence of exceptions.









