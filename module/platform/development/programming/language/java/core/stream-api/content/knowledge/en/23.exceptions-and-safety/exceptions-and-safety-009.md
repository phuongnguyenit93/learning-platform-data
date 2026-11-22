# Separating Service Calls and Persistence from Pure Transformations

## 1. The Problem: Correct Output Is Not Enough When Side Effects Are Uncontrolled

In the **JAVA_STREAM_API** module, we learn to process data declaratively using lazy pipelines with `filter`, `map`, `reduce`, `collect`, and collectors. When elements are purely in-memory values, a pipeline like this is easy to reason about:

```java
List<Long> amounts = orders.stream()
    .filter(Order::ready)
    .map(Order::amountCents)
    .toList();
```

Now imagine a different requirement:

> For each eligible order, call the payment service, then persist a receipt to the database. If the service fails or persistence throws, we must know how far processing got and be able to retry without charging twice.

A seemingly concise version:

```java
orders.parallelStream()
    .filter(Order::ready)
    .map(order -> gateway.charge(order))
    .forEach(receipt -> repository.save(receipt));
```

embeds **two critical side effects** inside the pipeline:

- `gateway.charge` may execute an external transaction outside the process.
- `repository.save` may persist a durable record.

An exception thrown after the gateway already charged the card **does not prove the transaction was undone**. Changing `stream()` to `parallelStream()` can also fire multiple requests concurrently, altering execution order and the number of in-flight transactions when a failure occurs.

In the **Exceptions and Safety** chapter, we must separate:

1. **Pure transformations**: computing new data from inputs without calling services or mutating external state.
2. **Side-effect boundaries**: interactions with HTTP, databases, message brokers, files, emails, or other systems.
3. **Failure contracts**: confirmed success, confirmed failure, or **uncertain** outcome.
4. **Retry and idempotency policies**: replaying a request without duplicating unintended effects.

After this lesson, you can design a workflow of **planning with the Stream API → validation → controlled service calls → persistence → reporting results**, while clarifying what guarantees real systems must provide outside the Stream API.

Main examples use **Java 17+** and **JUnit 5**. Concepts of purity, checked exceptions, and the Stream API apply from Java 8 onward, while complete programs use `record` and `Stream.toList()`.

## 2. Distinguishing Pure Transformations, Local State, and Side Effects

### 2.1. What Is a Pure Transformation?

A function is considered **pure** in the context of this lesson if:

- Given the same inputs, it produces the same output per contract.
- It causes no observable state changes outside the call.
- It does not read the system clock, call networks, touch files, or depend on mutable state not passed in.
- It does not mutate input objects also used elsewhere in the program.

Example:

```java
record Price(long unitCents, long quantity) {}

static long lineTotal(Price price) {
    return Math.multiplyExact(
        price.unitCents(), price.quantity()
    );
}
```

The function takes two numbers and computes one result without network or database access. `Math.multiplyExact` can throw `ArithmeticException` on overflow; **being able to throw does not make a function impure**, as long as the error is determined purely by its inputs and causes no side effects.

Pure transformations can be used inside `map`:

```java
List<Long> totals = prices.stream()
    .map(MyCalculations::lineTotal)
    .toList();
```

### 2.2. What Is a Side Effect?

A side effect is any state change or interaction **outside the function's return value**:

| Action inside lambda | Pure? | Risk |
| --- | --- | --- |
| `n -> n * 2` | Yes | Check numeric overflow if applicable |
| `order -> new Dto(order.id(), order.amount())` | Yes if inputs are stable | Avoid exposing mutable aliases |
| `order -> Math.addExact(order.amount(), tax)` | Yes if `tax` is immutable | Can throw a pure exception |
| `order -> System.currentTimeMillis()` | No | Result depends on invocation time |
| `order -> client.fetchPrice(order.sku())` | No | I/O, timeouts, service state |
| `order -> database.insert(order)` | No | Durable write, can fail midway |
| `order -> sharedList.add(order)` | No | External mutable state, races in parallel streams |
| `order -> logger.info(order.id())` | Has side effects | Logs may be skipped or out of expected order |
| `order -> counter.incrementAndGet()` | No | Even if atomic, still depends on invocation count |

**Not all mutation is forbidden.** A collector may allocate a **local** `ArrayList` or `HashMap` to accumulate results and return a value. Such accumulation has implementation state without necessarily causing business side effects. What matters is **state ownership** and whether it is shared or observed externally while the pipeline runs.

### 2.3. Do Not Equate “No I/O” with “Pure”

A function using a `static int counter` to generate IDs performs no I/O, yet is still impure. Likewise, a `map` that mutates an input object and returns it introduces mutation observable by callers:

```java
// Anti-pattern if OrderMutable is shared elsewhere:
// orders.stream()
//     .map(order -> {
//         order.setProcessed(true);
//         return order;
//     })
//     .toList();
```

When new state is needed, prefer creating a **new record/DTO** from source fields rather than mutating inputs fed into the pipeline.

## 3. Why Isn't the Stream API a Transaction Coordinator?

### 3.1. Lazy Pipelines Do Not Guarantee Lambdas Run Upon Declaration

`filter`, `map`, and `peek` are **intermediate operations**. They typically do not run until a terminal operation starts:

```java
var pipeline = orders.stream()
    .map(order -> {
        System.out.println("Processing " + order.id());
        return order.id();
    });

// No terminal operation yet: do not expect any order to be processed.
List<String> ids = pipeline.toList();
```

This fits data transformations well, yet is the wrong place to express “send confirmation email right now” without an explicit execution step.

### 3.2. Short-Circuiting and Optimizations Can Skip Work

`limit`, `findFirst`, `anyMatch`, `noneMatch`, and other short-circuiting mechanisms may not process every source element.

```java
// Wrong if business rules require writing every order to audit store:
orders.stream()
    .peek(auditStore::save)
    .findFirst();
```

When only the first element is needed, subsequent elements may never be traversed. Moreover, Stream implementations may elide some intermediate calls when optimizations preserve terminal output; e.g., `count()` on a sized source may skip iterating element by element. `peek` is not the right place for **mandatory actions**.

### 3.3. Parallel Streams Do Not Guarantee Side-Effect Execution Order

`parallelStream().forEach(...)` makes no promise to invoke actions in encounter order. `forEachOrdered` preserves **action order** for ordered sources, yet still provides no transactions, retries, or exactly-once semantics.

```java
orders.parallelStream()
    .forEach(order -> gateway.charge(order));
// No guarantee of transaction order or state of other tasks when one fails.
```

Even when changed to:

```java
orders.parallelStream()
    .forEachOrdered(order -> gateway.charge(order));
```

Java still cannot ensure an external service charges only once across timeouts or process restarts.

### 3.4. Mid-Pipeline Exceptions Do Not Roll Back Earlier Side Effects

```text
Order O1 -> gateway charge -> DB write succeeds
Order O2 -> gateway charge -> DB write fails
Order O3 -> not yet processed
               │
               └── Java exception DOES NOT automatically refund O1/O2.
```

A `try/catch` block only alters **in-process** control flow. Undoing or compensating across multiple systems is a separate distributed-transactions problem.

## 4. Common Anti-Patterns and Practical Limits of `forEach`

### 4.1. Using `map` for Write Operations

```java
// Avoid when the goal is business orchestration:
var receipts = orders.stream()
    .map(gateway::charge)
    .map(repository::saveAndReturn)
    .toList();
```

This code cannot clearly express:

- If `charge` succeeds yet `saveAndReturn` fails, what gets returned?
- Should processing stop on the first failing order or continue for others?
- If the pipeline reruns, which orders risk getting charged twice?
- What records completed steps for crash recovery?

### 4.2. Using `peek` for Auditing

```java
// Anti-pattern: critical side effects placed inside an intermediate operation.
var ids = orders.stream()
    .peek(auditStore::record)
    .map(Order::id)
    .toList();
```

`peek` helps **observe/debug** in selected cases, yet call counts and timing should never form a durable persistence contract.

### 4.3. `forEach` Is Not Strictly Forbidden

`forEach` is a terminal operation **designed for executing actions**. It fits simple cases with acceptable side effects, such as printing illustrative output:

```java
List.of("A", "B", "C").forEach(System.out::println);
```

The issue is not “every `forEach` is wrong,” but **the business guarantees the action requires**. If an action records a transaction needing retries, exactly-once handling, auditing, rollbacks, and error classification, an explicit loop over service/repository ports usually expresses responsibilities far better.

## 5. Recommended Architecture: Separating Preparation and Execution Phases

```text
     Stable input List<Order>
                 │
                 ▼
     VALIDATE (data contract)
                 │
                 ▼
     PLAN / PURE TRANSFORMS
     filter, map, collect, duplicate check,
     sum total with Math.addExact
                 │
                 ▼
       Unmodifiable Plan
       [ChargeCommand, ...]
                 │
                 ▼
      EXPLICIT EXECUTION LOOP
        ┌──────────────────────┐
        │ gateway.charge(cmd)  │
        │ receiptStore.save()  │
        └──────────────────────┘
                 │
        ┌────────┼──────────┐
        ▼        ▼          ▼
     RECORDED  CHARGE      RECORD
               UNKNOWN     FAILED
                 │
                 ▼
       ProcessReport with each outcome
```

The **preparation phase** can run repeatedly on the same inputs without causing external transactions. The **execution phase** authorizes and controls irreversible actions; it needs error policies and idempotency.

| Phase | Can use Stream API? | External side effects? | Desired guarantee |
| --- | --- | --- | --- |
| Validate | Yes or explicit loop | No | Report data errors **before** writing |
| Prepare/Plan | Yes, typically `filter/map/toList` | No | Deterministic, testable result |
| Authorize/Charge | Loop/service coordinator | **Yes** | Attach idempotency keys, bound concurrency |
| Save receipt | Repository/transaction API | **Yes** | Clear status, handle write failures |
| Summarize results | Yes, on stabilized outcomes | No | Report successes, failures, and unknowns fully |

Separating phases **does not magically create a transaction between gateway and database**; it makes failure modes **visible and addressable**.

## 6. Designing the Domain Model and Purity

Order model in the example:

```java
record Order(
    String id,
    String customerId,
    long amountCents,
    boolean ready
) {}

record ChargeCommand(
    String orderId,
    String customerId,
    long amountCents,
    String idempotencyKey
) {}
```

In the complete code, constructors validate non-blank strings and `amountCents > 0`. `ready` is a **business rule**: only ready orders enter the charge plan.

Do not generate idempotency keys with `UUID.randomUUID()` on every run for the same order, because a retry producing a new key looks like a new transaction to the gateway. In the example:

```java
String stableKey = "charge:v1:" + order.id();
```

The key is derived **deterministically** from the logical transaction ID and action version. This is only an **illustrative convention**: real systems must account for tenant/merchant, action type, transaction version, key retention TTL, and provider namespace limits.

### 6.1. Why Check Duplicates Before Calling Services?

If two input records share the same `orderId`, it could mean:

- Duplicate input data.
- Two commands for one logical transaction.
- A valid case requiring explicit merging.

In this lesson, **duplicate IDs are errors**; the whole input is checked before execution. That prevents charging several orders only to discover a duplicate at the end of the list.

### 6.2. Local State Inside `prepare` Is Not a Business Side Effect

A local `HashSet` used for duplicate detection is internal function state. It is never returned or shared across threads; the function remains **pure at its public boundary** as long as inputs are stable and unmutated.

Never put a shared `HashSet` inside `parallelStream().map(...)`. Validation can be a sequential loop while keeping data flow clear and exact.

## 7. Complete Java 17 Program: Prepare Commands, Then Call Gateway and Save Receipts

Save the following program as `SafeOrderProcessing.java`. No external framework beyond the JDK is needed for the main example; service/repository ports are simulated with in-memory classes.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class SafeOrderProcessing {

    private SafeOrderProcessing() {}

    public record Order(
        String id,
        String customerId,
        long amountCents,
        boolean ready
    ) {
        public Order {
            id = requireText(id, "id");
            customerId = requireText(customerId, "customerId");
            if (amountCents <= 0L) {
                throw new IllegalArgumentException(
                    "amountCents must be positive"
                );
            }
        }
    }

    public record ChargeCommand(
        String orderId,
        String customerId,
        long amountCents,
        String idempotencyKey
    ) {
        public ChargeCommand {
            orderId = requireText(orderId, "orderId");
            customerId = requireText(customerId, "customerId");
            idempotencyKey =
                requireText(idempotencyKey, "idempotencyKey");
            if (amountCents <= 0L) {
                throw new IllegalArgumentException(
                    "amountCents must be positive"
                );
            }
        }
    }

    public record Plan(
        List<ChargeCommand> commands,
        long plannedAmountCents
    ) {
        public Plan {
            commands = List.copyOf(commands);
        }
    }

    public record ChargeReceipt(
        String orderId, String receiptId
    ) {
        public ChargeReceipt {
            orderId = requireText(orderId, "orderId");
            receiptId = requireText(receiptId, "receiptId");
        }
    }

    public enum ExecutionStatus {
        RECORDED,
        CHARGE_UNCONFIRMED,
        RECEIPT_WRITE_FAILED
    }

    public record ExecutionResult(
        String orderId,
        ExecutionStatus status
    ) {}

    public record ProcessReport(List<ExecutionResult> results) {
        public ProcessReport {
            results = List.copyOf(results);
        }

        public long recordedCount() {
            return results.stream()
                .filter(r -> r.status() == ExecutionStatus.RECORDED)
                .count();
        }
    }

    public static class GatewayException extends Exception {
        public GatewayException(String message) {
            super(message);
        }
    }

    public static class StoreException extends Exception {
        public StoreException(String message) {
            super(message);
        }
    }

    @FunctionalInterface
    public interface ChargeGateway {
        ChargeReceipt charge(ChargeCommand command)
            throws GatewayException;
    }

    @FunctionalInterface
    public interface ReceiptStore {
        void save(ChargeReceipt receipt)
            throws StoreException;
    }

    private static String requireText(String text, String field) {
        Objects.requireNonNull(text, field);
        if (text.isBlank()) {
            throw new IllegalArgumentException(
                field + " cannot be blank"
            );
        }
        return text;
    }

    // Pure phase: read data only, validate, prepare commands.
    public static Plan prepare(List<Order> input) {
        Objects.requireNonNull(input, "input");
        List<Order> snapshot = List.copyOf(input);

        Set<String> ids = new HashSet<>();
        for (Order order : snapshot) {
            if (!ids.add(order.id())) {
                throw new IllegalArgumentException(
                    "Duplicate order ID: " + order.id()
                );
            }
        }

        List<ChargeCommand> commands = snapshot.stream()
            .filter(Order::ready)
            .map(order -> new ChargeCommand(
                order.id(),
                order.customerId(),
                order.amountCents(),
                "charge:v1:" + order.id()
            ))
            .toList();

        long total = commands.stream()
            .mapToLong(ChargeCommand::amountCents)
            .reduce(0L, Math::addExact);

        return new Plan(commands, total);
    }

    // Side-effect boundary: ordered, explicit error policy.
    public static ProcessReport execute(
        Plan plan,
        ChargeGateway gateway,
        ReceiptStore store
    ) {
        Objects.requireNonNull(plan, "plan");
        Objects.requireNonNull(gateway, "gateway");
        Objects.requireNonNull(store, "store");

        List<ExecutionResult> results = new ArrayList<>();

        for (ChargeCommand command : plan.commands()) {
            ChargeReceipt receipt;
            try {
                receipt = Objects.requireNonNull(
                    gateway.charge(command),
                    "Gateway must not return a null receipt"
                );
                if (!receipt.orderId().equals(command.orderId())) {
                    throw new IllegalStateException(
                        "Receipt does not match order ID"
                    );
                }
            } catch (GatewayException ex) {
                // Timeout/network error: DO NOT claim charge did not occur.
                results.add(new ExecutionResult(
                    command.orderId(),
                    ExecutionStatus.CHARGE_UNCONFIRMED
                ));
                continue;
            }

            try {
                store.save(receipt);
                results.add(new ExecutionResult(
                    command.orderId(),
                    ExecutionStatus.RECORDED
                ));
            } catch (StoreException ex) {
                // Charge returned a receipt, yet failed to persist durably.
                results.add(new ExecutionResult(
                    command.orderId(),
                    ExecutionStatus.RECEIPT_WRITE_FAILED
                ));
            }
        }

        return new ProcessReport(results);
    }

    // Simulation only: not a real payment gateway.
    public static final class FakeGateway
            implements ChargeGateway {
        private final Map<String, ChargeReceipt> byKey =
            new HashMap<>();

        @Override
        public ChargeReceipt charge(ChargeCommand command) {
            return byKey.computeIfAbsent(
                command.idempotencyKey(),
                unused -> new ChargeReceipt(
                    command.orderId(),
                    "R-" + command.orderId()
                )
            );
        }

        public int acceptedKeyCount() {
            return byKey.size();
        }
    }

    // Simulation only: does not replace a database/transaction.
    public static final class FakeReceiptStore
            implements ReceiptStore {
        private final Map<String, ChargeReceipt> byOrder =
            new LinkedHashMap<>();

        @Override
        public void save(ChargeReceipt receipt) {
            byOrder.put(receipt.orderId(), receipt);
        }

        public int receiptCount() {
            return byOrder.size();
        }
    }

    public static void main(String[] args) {
        List<Order> input = List.of(
            new Order("O1", "C1", 1_000L, true),
            new Order("O2", "C2", 2_000L, false),
            new Order("O3", "C1", 4_000L, true)
        );

        Plan plan = prepare(input);
        System.out.println(plan.commands().size()); // 2
        System.out.println(plan.plannedAmountCents()); // 5000

        FakeGateway gateway = new FakeGateway();
        FakeReceiptStore store = new FakeReceiptStore();
        ProcessReport report = execute(plan, gateway, store);

        System.out.println(report.recordedCount()); // 2
        System.out.println(gateway.acceptedKeyCount()); // 2
        System.out.println(store.receiptCount()); // 2
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 SafeOrderProcessing.java
java SafeOrderProcessing
```

### 7.1. Contract of `prepare`

`prepare`:

- Calls no gateway, writes no database, sends no emails.
- Uses `List.copyOf` to snapshot the input list structure and reject `null` elements.
- Checks all duplicate IDs **before** filtering ready orders, so duplicate IDs fail even if one order has `ready == false`.
- Uses `filter` and `map` to construct `ChargeCommand`s solely from validated data.
- Uses `Math.addExact` to detect `long` total overflow before starting any charges.
- Returns a `Plan` with an unmodifiable command list and `record`s immutable across primitive/String fields.

Important precondition: the source structure is not mutated concurrently **while creating the snapshot**. `List.copyOf` does not turn copying an `ArrayList` being mutated by another thread into an atomic operation.

### 7.2. Contract of `execute`

`execute`:

- Is an **explicit loop** following command order.
- Separates gateway failures from receipt-writing failures.
- Assigns `CHARGE_UNCONFIRMED` rather than guessing the gateway definitely did not charge when communication fails.
- Assigns `RECEIPT_WRITE_FAILED` if the gateway returned a receipt yet the store reported an error.
- Returns one outcome per command for **expected failures** (`GatewayException` or `StoreException`).

This is the example's **continue-on-known-error policy**: an expected error on one order does not automatically stop subsequent orders. Programming/contract violations like a gateway returning `null` or a mismatched receipt order ID are thrown so invariant violations are never masked; before production deployment, durably persist states before unexpected failures can occur.

### 7.3. Why Is This Demo Still Not “Exactly Once”?

`FakeGateway` only keeps keys in an **in-memory** `HashMap`. When the process restarts, the map vanishes. `FakeReceiptStore` is also not durable. They illustrate where responsibilities attach, **not** production payment idempotency or durability implementations.

A real system needs gateway idempotency contracts, database unique keys, post-timeout status lookup, and potentially an outbox/state workflow for crash recovery.

## 8. Separating Business States from Technical Exceptions

When a service call fails, never collapse every case into a boolean `success == false`. Distinguish what is **confirmed**, what is **unknown**, and what is **retryable**.

| Scenario | What we know | Appropriate state or handling |
| --- | --- | --- |
| Gateway returns valid receipt, repository saves | Receipt obtained and persisted | `RECORDED` |
| Gateway explicitly reports “card declined,” confirmed **not charged** | Transaction rejected | A dedicated `DECLINED` business state |
| Gateway times out after sending request | **Unknown** whether gateway charged | `CHARGE_UNCONFIRMED`, needs lookup/reconcile |
| Gateway returns receipt, repository throws | Gateway charged; persistence failed | `RECEIPT_WRITE_FAILED`, needs write recovery |
| Database confirms write failed before commit | May know write did not happen per DB contract | Handle per specific transaction/result |
| Connection lost right at DB commit | **Must not guess** commit did not occur | Query state by unique key |
| Parser spots bad input before charge | Service not yet called | Report validation error |
| Process crashes right after charge, before save | Side effect may exist without saved state | Durable intent/outbox/reconciliation |

The sample code groups `GatewayException`s into `CHARGE_UNCONFIRMED` because the simulated interface **lacks a confirmed-decline error type**. In production, the gateway adapter should classify errors per provider contract:

- **Confirmed declined:** return `Declined(reasonCode)` or an equivalent domain result.
- **Confirmed accepted:** return receipt/transaction ID.
- **Uncertain after timeout/connection reset:** return `UnknownOutcome`; never auto-recharge with a new key.

If an API lacks enough detail to distinguish, **pick the conservative state** and add a lookup/reconciliation path.

### 8.1. Why Avoid `Optional.empty()` for All Errors?

`Optional.empty()` means “no value,” and cannot distinguish:

1. Normal absence of data.
2. Service confirmed not found.
3. Service timed out.
4. Response data was invalid.
5. Persisting the result failed.

If all of these become `Optional.empty()`, downstream treats errors as empty data and silently produces incomplete reports. Use **state-bearing result types**, classified exceptions, or an explicit error report.

### 8.2. Operation Order Determines Failure Semantics

With `charge → save receipt`, a persistence error happens **after** an external side effect. You cannot merely catch `StoreException` and treat the charge as rolled back.

Switching to `save "PENDING" → charge → save "CONFIRMED"` gives the database better recovery state, yet a gap between systems still remains. A gateway call cannot automatically join a regular database transaction unless the gateway offers compatible transaction coordination.

## 9. Checked Exceptions in Lambdas: Do Not Use Wrappers to Hide Errors

Stream API functional interfaces `Function<T,R>`, `Predicate<T>`, and `Consumer<T>` do not declare `throws IOException` or arbitrary checked exceptions. Therefore:

```java
// Does not compile if client.lookup declares throws IOException:
// var values = ids.stream()
//     .map(id -> client.lookup(id))
//     .toList();
```

There are multiple options, each fitting a different contract.

### 9.1. Option A — Call the Service in a Separate Loop

```java
List<String> ids = customers.stream()
    .filter(Customer::active)
    .map(Customer::id)
    .distinct()
    .toList();

List<CustomerProfile> profiles = new ArrayList<>();
for (String id : ids) {
    // Explicit retry/timeout/failure policy outside the pipeline.
    profiles.add(client.lookup(id));
}
```

This is an **illustrative snippet inside a method with appropriate `customers` and `client` parameters**. If `lookup` throws a checked exception, the enclosing method can declare `throws` or `catch` and classify errors right at the boundary.

Advantages: easy to bound call count, attach correlation IDs, stop/continue explicitly, and close per-request resources cleanly.

### 9.2. Option B — Deliberately Translate Checked Exceptions

For **I/O source reads** when a pipeline is truly needed, Java provides `UncheckedIOException`:

```java
static String readTextUnchecked(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException ex) {
        throw new UncheckedIOException("Unable to read: " + path, ex);
    }
}
```

When calling it in `map`, ensure you:

- Preserve the `IOException` **cause**.
- Never convert errors into `null` or `Stream.empty()` just to keep the pipeline going.
- Ensure no critical side effect ran partially before the error, or have recovery mechanisms.
- Close resources at the right owner.

Translating checked to unchecked **only changes how the exception propagates**; it adds neither rollback nor retry.

### 9.3. Option C — Return Typed Outcomes

When analyzing batches of responses without **throwing** on failing items:

```java
sealed interface LookupOutcome
    permits LookupOk, LookupFailed {}

record LookupOk(String id, CustomerProfile profile)
    implements LookupOutcome {}

record LookupFailed(String id, String errorCode)
    implements LookupOutcome {}
```

With this model, use a controlled service-call phase to build `List<LookupOutcome>`, then **use a pure Stream** to classify:

```java
Map<Boolean, List<LookupOutcome>> grouped = outcomes.stream()
    .collect(Collectors.partitioningBy(
        outcome -> outcome instanceof LookupOk
    ));
```

`partitioningBy` makes no service calls; it only splits **already-materialized outcomes**. This uses the Stream API where it shines.

## 10. Retries, Idempotency, and Post-Failure Reconciliation

### 10.1. Retrying Is Unsafe Without Preconditions

Suppose the network times out after sending a charge request:

```text
Client                   Gateway
  │  charge(key=K)          │
  ├────────────────────────►│
  │                         │ processed successfully
  │  X response lost        │
  │                         │
  └── Timeout               │
```

If the client retries with a **new key** or the gateway lacks an idempotency contract, a second charge can occur. Catching and calling again does not fix this.

### 10.2. Idempotency Keys Must Represent Logical Transactions

In the example, `"charge:v1:" + order.id()` stays constant when retrying the same command. Real systems must verify:

- Is the key unique within merchant/tenant and transaction type scope?
- How long does the gateway retain key state?
- If the same key arrives with a **different amount payload**, does the gateway reject it or return the old result?
- On timeout, is there a lookup API by key or transaction ID?
- Once a key expires, does the app retry or escalate to manual review?

**Idempotency is a contract of the receiving system**, not an inherent property of `Stream.distinct()` or `Set`.

### 10.3. Retries Should Target the Exact Failing Step

| Status | Recovery action | What to avoid |
| --- | --- | --- |
| Charge outcome unknown | Query by key/transaction, reconcile before retrying | Sending a fresh unverified charge |
| Charge has receipt, DB write failed | Retry receipt write **idempotently** | Recharging just because save failed |
| Confirmed business decline | Record decline status, request alternate payment | Infinite retries under identical conditions |
| Invalid input data | Fix data/validation, build a new plan | Retrying gateway with invalid command |
| Evidence-backed transient error | Bounded retry with backoff per policy | Unbounded loop without timeouts |

### 10.4. Never Put Unbounded Retries Inside `map`

`map(order -> retry(() -> gateway.charge(order)))` obscures transaction logic, especially alongside `parallel`, `limit`, or exceptions from another stage. Better to provide a **port/service coordinator** with deadlines, concurrency bounds, a status store, and explicit retry policies.

If there is a single **read-only** HTTP call without complex error classification, `map(client::fetch)` can sometimes be pragmatic. Crucially, it is **no longer pure** and must be evaluated under timing, ordering, failure, and resource contracts—never pretending every Stream mapper is an in-memory data transform.

## 11. Safe Persistence: Transactions, Unique Keys, and Outbox

### 11.1. A Database Transaction Protects Only Operations Inside That Transaction

Multiple SQL statements on **the same database** within one transaction achieve atomic commit/rollback per isolation level and driver/DB contract.

Conceptual example:

```text
BEGIN TRANSACTION
    INSERT order_status(...)
    INSERT audit_event(...)
COMMIT
```

Yet an HTTP call to a payment gateway **does not automatically join** that database transaction. When HTTP succeeds and the database rolls back, the gateway is not rolled back automatically.

### 11.2. Outbox for Updating DB and Publishing Events

When synchronizing “save order status” and “publish event,” **transactional outbox** is a useful pattern:

```text
Transaction in the same database:
    UPDATE orders SET status = 'READY'
    INSERT INTO outbox(event_id, payload, status='PENDING')
COMMIT
                   │
                   ▼
Separate worker reads outbox:
    publish event to broker
    mark published / retry
                   │
                   ▼
Consumer processes event idempotently by event_id
```

Outbox closes the “database committed, then app crashed before publishing” gap. However, a worker can publish an event and crash before marking it published, causing the event to **be sent again**. Consumers still need **deduplication/idempotency** if the goal is logically once-only effects.

### 11.3. Calling a Gateway Before DB Writes Requires Durable Intent or Reconciliation

For payments, you can persist **processing intent** (with the idempotency key and validated payload) before calling the gateway. An execution worker can:

1. Claim a `PENDING` job.
2. Call the gateway with the stable key.
3. Save the receipt/transaction ID upon confirmation.
4. Transition status to `RECORDED`, `DECLINED`, or `UNKNOWN`.
5. Reconcile `UNKNOWN` jobs before retrying.

This is **system architecture**, not something `Collectors.toMap` or `parallelStream` generates. Job claiming, optimistic locking, deadlines, and state transitions must match the specific database/gateway.

### 11.4. When Writes May Replay, Storage Keys Must Be Unique

Example receipts table:

```text
receipts(
    order_id UNIQUE,
    gateway_transaction_id UNIQUE,
    amount,
    recorded_at
)
```

Unique constraints and well-contracted insert/upsert statements reduce duplicate writes on retry. Still, an **upsert** must verify existing data matches the logical transaction; never overwrite a receipt with a different amount silently.

## 12. Choosing Batch Policies and Completion Boundaries

There are at least three options when an element fails:

| Policy | Behavior | When suitable |
| --- | --- | --- |
| **Fail-fast** | Stop dispatching further commands at first error | Every step must pass inspection; errors are rare and non-ignorable |
| **Continue with results** | Continue processing remaining commands, record each status | Independent batch items needing full progress reporting |
| **Durable job queue** | Persist jobs and states; workers process per policy | Multi-step workflows needing crash recovery |

The `execute` example in section 7 picks **continue with results** for `GatewayException` and `StoreException`. It **does not** catch arbitrary `RuntimeException`s: if code breaks a contract, execution stops abruptly. In production, durably persist per-job state **before external calls** to recover from process crashes.

### 12.1. Distinguishing Three Kinds of “Success”

1. **Preparation succeeded:** `Plan` created, data and invariants validated.
2. **Gateway call succeeded:** system received a confirmed charge result.
3. **Entire workflow succeeded:** receipt durably saved, required audit/outbox completed, and state is recoverable after crashes.

Never collapse all three into a single `success = true` just because `collect(...)` threw no exception.

### 12.2. Partial Success Must Be Explicitly Reported

If a batch has 100 commands:

```text
RECORDED             = 94
CHARGE_UNCONFIRMED   =  3
RECEIPT_WRITE_FAILED =  3
TOTAL                = 100
```

Output should surface all three statuses and their corresponding IDs. Never return a `List<Receipt>` of 94 receipts and say “processed 100 orders” when six commands remain unresolved.

### 12.3. Empty Output Is Not a Service Error

If `filter(Order::ready)` yields zero commands, an empty `Plan.commands()` can be a valid state: **no eligible orders**. Conversely, if commands existed and the gateway timed out, never convert that into an empty `Plan` or a “nothing to do” `ProcessReport` to move on.

Separating **business-empty** from **technical failure** is essential for reporting and retries.

## 13. Calling Services Before Transformations: A Controlled Enrichment Model

Service calls do not always sit at the end. Many problems require looking up profiles, prices, or exchange rates before transforming into final outputs:

```text
Raw input records
    │
    ├─ PURE: determine lookup request keys
    ▼
Ordered, deduplicated List<LookupRequest>
    │
    ├─ I/O BOUNDARY: call service, store result/error kind
    ▼
Materialized List<LookupOutcome>
    │
    ├─ PURE: join responses with source records
    ▼
List<EnrichedRecord>
    │
    └─ I/O BOUNDARY: save/export results per transaction policy
```

### 13.1. Determining Request Keys Can Be Pure

```java
List<String> customerIds = orders.stream()
    .map(Order::customerId)
    .distinct()
    .toList();
```

On an ordered `List`, `distinct` keeps the first occurrence of each ID in encounter order. This **deduplicates repeated lookup keys** in the input; it does not guarantee external services are called exactly once across workflow retries/crashes.

### 13.2. Service Calls Should Return Explicit Outcomes

```java
List<LookupOutcome> outcomes = new ArrayList<>();

for (String id : customerIds) {
    try {
        CustomerProfile profile = profileClient.lookup(id);
        outcomes.add(new LookupOk(id, profile));
    } catch (ProfileServiceException ex) {
        outcomes.add(
            new LookupFailed(id, ex.errorCode())
        );
    }
}
```

This snippet is an **orchestration template**, not a standalone program: `profileClient`, `ProfileServiceException`, and `CustomerProfile` live in the integration layer. The intent is never to hide which requests failed and to expose only **safe error codes** in public outcomes.

### 13.3. Joining and Transforming Can Be Pure Again

Once all responses are stabilized, build a map of successful profiles:

```java
Map<String, CustomerProfile> successfulProfiles =
    outcomes.stream()
        .filter(LookupOk.class::isInstance)
        .map(LookupOk.class::cast)
        .collect(Collectors.toMap(
            LookupOk::id,
            LookupOk::profile
        ));
```

`Collectors.toMap` **throws on duplicate keys** under its two-mapper overload contract. This catches unexpected duplicate service results instead of silently overwriting.

From this map, a pure `map` can join the data, yet you must define a policy for **missing profiles**:

- If every profile is mandatory, report failure and **never publish** incomplete joins.
- If absence is valid, use a result type explicitly modeling “no profile.”
- If skipping records is allowed, return skipped counts/IDs instead of calling `filter(Objects::nonNull)` and treating the output as complete.

## 14. File Sources and Closing Resources Before Side Effects Begin

With I/O sources, reading logs/CSVs can fail **when opening** or **during iteration**. Placing service calls inside `Files.lines`'s `map` keeps the reader open while waiting on the network and risks partial writes before hitting a broken final line.

### 14.1. Safe Pattern When Input Fits in Memory

```java
Plan plan;
try (Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8)) {
    List<Order> parsed = lines
        .map(OrderParser::parseStrict)
        .toList();
    plan = SafeOrderProcessing.prepare(parsed);
}

// Here the file is closed and all input has been validated.
ProcessReport report = SafeOrderProcessing.execute(
    plan, gateway, receiptStore
);
```

This snippet assumes a method with `path`, `gateway`, `receiptStore`, and `OrderParser` in scope. Key points:

- The reader/file closes **before** any charges begin.
- If parsing/validation fails, zero charge operations execute.
- Totals and duplicates are checked **before** causing side effects.
- `IOException` is never turned into an empty file.

### 14.2. When Input Cannot Be Materialized Whole

For hundreds-of-GB files, `toList()` consumes memory proportional to record count. You may need **chunked** processing or a queued workflow:

```text
read 1 chunk → parse/validate chunk → persist intent → execute → checkpoint
read next chunk → ...
```

In that case, you **no longer have the guarantee** that “every line in the entire file validated before the first transaction.” Publish an explicit partial-progress policy and save checkpoints/dedup keys to resume after failures. If file-wide all-or-nothing is required, design staging/validation prior to execution or use an appropriate transactional engine.

### 14.3. `try-with-resources` Does Not Roll Back External Writes

`try-with-resources` ensures closing the owned stream/reader; it **does not undo** rows already written to a database before a read I/O error occurred. Never confuse resource-closing correctness with workflow atomicity.

## 15. Parallel Processing: Bound Concurrency First, Never Blindly Switch to `parallelStream`

Service calls are usually blocking I/O. Concurrent calls **can** boost throughput, yet bring:

- Open connection counts, rate limits, and service quotas.
- Timeouts and cancellation behavior.
- In-flight requests still executing when one fails.
- Response order differing from encounter order.
- Duplicate side effects on retries or crashes.
- Mutable state inside adapters that may not be thread-safe.

`parallelStream()` **does not provide** rate limits, durable checkpoints, transactions, or idempotency out of the box.

### 15.1. `forEachOrdered` Solves Only Part of the Problem

`forEachOrdered` preserves action encounter order on ordered streams even in parallel mode. However, it:

- Does not make HTTP requests transactional.
- Does not persist progress durably.
- Does not ensure a later failure rolls back earlier side effects.
- Does not help ask the service whether a timed-out charge succeeded.

When transaction order matters and volume is moderate, an **explicit sequential loop** is often the simplest and most testable option.

### 15.2. When Genuine Concurrency Is Needed, Build a Dedicated Coordinator

Instead of `parallelStream().forEach(gateway::charge)`, a coordinator can enforce:

1. **Bounded concurrency:** cap concurrent requests at `k`.
2. **Per-request timeout:** never wait indefinitely.
3. **Rate limiting:** enforce request rate per service contract.
4. **Stable idempotency keys:** retrying the same logical transaction never mints a new key.
5. **Per-item result:** record each command's status.
6. **Durable checkpoint/reconciliation:** recover after crashes.
7. **Cancellation semantics:** understand that stopping waiting does not mean the server stopped processing.

These capabilities are typically built with `ExecutorService`, job queues/workers, concurrency limiters, or integration frameworks. **The Stream API can prepare command lists and summarize outcomes**, while orchestration policy belongs in a dedicated component.

### 15.3. Never Use Parallel Streams to Guarantee Exactly N External Calls

`limit(10)` limits the number of requested **output elements**, not a guarantee that “only 10 upstream mapper side effects ran” under parallel or optimized execution. Extra tasks may already have started before downstream short-circuits.

If business logic requires an exact number of commands, build a validated-size `List<ChargeCommand>` first, then hand that list to the coordinator. Never rely on lambda execution order to assign transaction identities.

## 16. Input Order, Persistence Order, and Completion Order

Three kinds of ordering must stay distinct:

| Ordering type | Example | Guaranteed by Stream API? |
| --- | --- | --- |
| **Encounter order** | Orders O1, O2, O3 from a `List` | Yes, per ordered source/pipeline contract |
| **Execution order** | O2 sends HTTP before O1 under parallel execution | Not promised by `parallel forEach` |
| **Commit/response order** | O3 commits to DB before O1 | Determined by services, transactions, and coordinator |

The main program's `execute` iterates `plan.commands()` sequentially, so **gateway call order** matches the plan list in a normal single-process run. Still, you cannot assume external systems commit in that order or no other actors send concurrent requests.

### 16.1. Ordering in a Display Report

If outcomes come from multiple parallel workers, store a `sequenceNumber` in `ChargeCommand` or `ExecutionResult`, then sort results by it **after** execution:

```java
List<ExecutionResult> orderedResults = results.stream()
    .sorted(Comparator.comparingInt(ExecutionResult::sequenceNumber))
    .toList();
```

This is an **illustration for an `ExecutionResult` variant adding `sequenceNumber`**, not a compiling call against the two-field record in the main program. Sorting only changes **report presentation order**, not the order requests reached the gateway.

### 16.2. Duplicate Data: `distinct` Is Not Once-Only Write Control

`distinct` filters duplicates by `equals` within a **single stream traversal**. It has no memory of which transactions previous application runs persisted; it never replaces idempotency keys or unique constraints.

When a batch reruns after a crash, a durable state store must identify which commands already succeeded, have not run, or remain uncertain.

## 17. Logging, Metrics, and Security at Side-Effect Boundaries

Logging is a side effect, yet normally essential for operations. The right practice is not “ban logging,” but **place logging at coordinated boundaries**:

```text
execute command
    │
    ├─ log request ID + operation type (never log tokens/PII)
    ├─ call gateway with timeout and idempotency key
    ├─ log classified status + latency
    ├─ save receipt
    └─ log persistence step and state update
```

**Never use `peek` for mandatory audit logging**, because a terminal call may short-circuit or an implementation may optimize away intermediate stages that do not affect the result.

### 17.1. Operational Metrics Should Be Separated

| Metric | What it measures |
| --- | --- |
| `commands_planned` | Commands validated and planned |
| `gateway_confirmed` | Commands with confirmed gateway success |
| `charge_unconfirmed` | Commands with unknown result after error |
| `receipt_recorded` | Receipts persisted |
| `receipt_write_failed` | Persistence errors after receiving receipt |
| `reconciliation_pending` | Items requiring reconciliation |
| `retry_attempts` | Retry count, not new transactions |

Total planned commands should reconcile against final batch statuses. Never use `"success"` log line counts or mapper invocation counts as financial records.

### 17.2. Never Leak Sensitive Data in Error Reports

An SDK exception may contain URLs, request bodies, tokens, or payment info. `ExecutionResult` in the example exposes **status codes**, not raw `ex.getMessage()`. When investigation is needed:

- Use correlation IDs / trace IDs generated per system policy.
- Log causes to an access-controlled channel with redaction.
- Never store raw card details or secret keys inside `Plan`/logs.
- Separate internal technical details from API-facing messages.

## 18. JUnit 5 Tests: Proving Purity and Side-Effect Boundaries

The tests below run on JDK 17 and JUnit Jupiter, using `SafeOrderProcessing` from section 7. They verify **planned values**, **simulated call counts**, **status reporting**, and **key reuse**. They do not assume the fake gateway is a durable payment provider.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class SafeOrderProcessingTest {

    private static List<SafeOrderProcessing.Order> sample() {
        return List.of(
            new SafeOrderProcessing.Order("O1", "C1", 100L, true),
            new SafeOrderProcessing.Order("O2", "C2", 200L, false),
            new SafeOrderProcessing.Order("O3", "C1", 300L, true)
        );
    }

    @Test
    void prepareIsDeterministicAndHasStableKeys() {
        var first = SafeOrderProcessing.prepare(sample());
        var second = SafeOrderProcessing.prepare(sample());

        assertEquals(first, second);
        assertEquals(2, first.commands().size());
        assertEquals(400L, first.plannedAmountCents());
        assertEquals(List.of("O1", "O3"),
            first.commands().stream()
                .map(SafeOrderProcessing.ChargeCommand::orderId)
                .toList());
        assertEquals("charge:v1:O1",
            first.commands().get(0).idempotencyKey());
    }

    @Test
    void duplicateIdsAreRejectedBeforeExternalCalls() {
        var duplicates = List.of(
            new SafeOrderProcessing.Order("O1", "C1", 100L, true),
            new SafeOrderProcessing.Order("O1", "C9", 999L, false)
        );

        assertThrows(IllegalArgumentException.class, () ->
            SafeOrderProcessing.prepare(duplicates)
        );
        // execute is not called: prepare only builds the plan.
    }

    @Test
    void overflowIsRejectedDuringPurePreparation() {
        var tooLarge = List.of(
            new SafeOrderProcessing.Order(
                "O1", "C1", Long.MAX_VALUE, true
            ),
            new SafeOrderProcessing.Order("O2", "C2", 1L, true)
        );

        assertThrows(ArithmeticException.class, () ->
            SafeOrderProcessing.prepare(tooLarge)
        );
    }

    @Test
    void planDoesNotTrackLaterSourceListStructuralChanges() {
        ArrayList<SafeOrderProcessing.Order> input =
            new ArrayList<>(sample());
        var plan = SafeOrderProcessing.prepare(input);

        input.clear();
        assertEquals(2, plan.commands().size());
        assertThrows(UnsupportedOperationException.class, () ->
            plan.commands().clear()
        );
    }

    @Test
    void noReadyOrderMeansNoGatewayOrStoreCall() {
        var plan = SafeOrderProcessing.prepare(
            List.of(new SafeOrderProcessing.Order(
                "O1", "C1", 100L, false
            ))
        );
        AtomicInteger gatewayCalls = new AtomicInteger();
        AtomicInteger storeCalls = new AtomicInteger();

        var report = SafeOrderProcessing.execute(
            plan,
            cmd -> {
                gatewayCalls.incrementAndGet();
                return new SafeOrderProcessing.ChargeReceipt(
                    cmd.orderId(), "R1"
                );
            },
            receipt -> storeCalls.incrementAndGet()
        );

        assertTrue(report.results().isEmpty());
        assertEquals(0, gatewayCalls.get());
        assertEquals(0, storeCalls.get());
    }

    @Test
    void confirmedChargeIsRecorded() {
        AtomicInteger gatewayCalls = new AtomicInteger();
        AtomicInteger storeCalls = new AtomicInteger();
        var plan = SafeOrderProcessing.prepare(sample());

        var report = SafeOrderProcessing.execute(
            plan,
            cmd -> {
                gatewayCalls.incrementAndGet();
                return new SafeOrderProcessing.ChargeReceipt(
                    cmd.orderId(), "R-" + cmd.orderId()
                );
            },
            receipt -> {
                storeCalls.incrementAndGet();
            }
        );

        assertEquals(2, gatewayCalls.get());
        assertEquals(2, storeCalls.get());
        assertEquals(2L, report.recordedCount());
        assertEquals(
            SafeOrderProcessing.ExecutionStatus.RECORDED,
            report.results().get(0).status()
        );
    }

    @Test
    void gatewayTimeoutIsReportedAsUnconfirmedNotDeclined() {
        AtomicInteger storeCalls = new AtomicInteger();
        var plan = SafeOrderProcessing.prepare(
            List.of(sample().get(0))
        );

        var report = SafeOrderProcessing.execute(
            plan,
            cmd -> {
                throw new SafeOrderProcessing.GatewayException(
                    "Simulated timeout"
                );
            },
            receipt -> storeCalls.incrementAndGet()
        );

        assertEquals(0, storeCalls.get());
        assertEquals(
            SafeOrderProcessing.ExecutionStatus.CHARGE_UNCONFIRMED,
            report.results().get(0).status()
        );
    }

    @Test
    void writeFailureDoesNotClaimChargeWasUndone() {
        var plan = SafeOrderProcessing.prepare(
            List.of(sample().get(0))
        );

        var report = SafeOrderProcessing.execute(
            plan,
            cmd -> new SafeOrderProcessing.ChargeReceipt(
                cmd.orderId(), "R1"
            ),
            receipt -> {
                throw new SafeOrderProcessing.StoreException(
                    "DB unavailable"
                );
            }
        );

        assertEquals(
            SafeOrderProcessing.ExecutionStatus.RECEIPT_WRITE_FAILED,
            report.results().get(0).status()
        );
        assertEquals(0L, report.recordedCount());
    }

    @Test
    void fakeGatewayDeduplicatesStableKeyAcrossTwoRuns() {
        var plan = SafeOrderProcessing.prepare(sample());
        var gateway = new SafeOrderProcessing.FakeGateway();
        var store = new SafeOrderProcessing.FakeReceiptStore();

        SafeOrderProcessing.execute(plan, gateway, store);
        SafeOrderProcessing.execute(plan, gateway, store);

        assertEquals(2, gateway.acceptedKeyCount());
        assertEquals(2, store.receiptCount());
        // In-memory fake does not prove durability across restarts.
    }

    @Test
    void invalidOrderIsRejectedBeforePlan() {
        assertThrows(IllegalArgumentException.class, () ->
            new SafeOrderProcessing.Order(
                "O1", "C1", -1L, true
            )
        );
        assertThrows(IllegalArgumentException.class, () ->
            new SafeOrderProcessing.Order(
                "", "C1", 100L, true
            )
        );
        assertThrows(NullPointerException.class, () ->
            SafeOrderProcessing.prepare(null)
        );
    }
}
```

### 18.1. What Each Test Proves

| Test | Verified guarantee |
| --- | --- |
| `prepareIsDeterministicAndHasStableKeys` | Identical input yields equivalent plan |
| `duplicateIdsAreRejectedBeforeExternalCalls` | Duplicate inputs blocked in pure phase |
| `overflowIsRejectedDuringPurePreparation` | Never charges when total overflows numeric range |
| `planDoesNotTrackLaterSourceListStructuralChanges` | Plan unaffected by caller mutating source list after prepare |
| `noReadyOrderMeansNoGatewayOrStoreCall` | Zero commands means external ports are not called |
| `confirmedChargeIsRecorded` | Each simulated command called gateway and store |
| `gatewayTimeoutIsReportedAsUnconfirmedNotDeclined` | Timeouts are not interpreted as confirmed non-charge |
| `writeFailureDoesNotClaimChargeWasUndone` | Receipt persistence error has its own status |
| `fakeGatewayDeduplicatesStableKeyAcrossTwoRuns` | Proves **fake** retains keys in the same process, nothing more |

In production testing, add **integration tests** against a sandbox gateway, real database, and crash-restart recovery flows. Unit tests with fakes only prove orchestration code handles and emits states according to the interface.

### 18.2. Never Put Random Sleeps in Correctness Unit Tests

To simulate timeouts, the fake gateway **throws `GatewayException`**. Unit tests need neither `Thread.sleep` nor real network waits, avoiding flaky tests. Real concurrency, timeouts, connection resets, and mid-step crashes should be tested via controlled integration/chaos tests.

## 19. Anti-Patterns and Mistakes to Avoid

| Anti-pattern | What can go wrong | Replacement |
| --- | --- | --- |
| Calling `gateway.charge` directly in `map` | Hard to control retries, timeouts, request counts, and partial success | Build `ChargeCommand` with `map`, call gateway in coordinator |
| Writing to DB inside `peek` | Intermediate operations may be skipped | Write via service/repository in explicit step |
| Treating `forEachOrdered` as a transaction | Ordered, yet not atomic or rolled back | System-level transactions/workflow states |
| `parallelStream().forEach(repository::save)` on unsafe repository | Races, exceeds connection limits | Explicit concurrency coordination |
| `catch (Exception ex) { return null; }` inside mapper | Swallows data, I/O, and programming errors | Domain outcomes or classified exceptions |
| `catch (IOException ex) { return Stream.empty(); }` | Unreadable file becomes empty data | Report source failure, never fake success |
| Retrying HTTP charge with fresh `UUID.randomUUID()` | One logical transaction gets multiple keys | Stable idempotency key, status lookup |
| Re-charging after receipt write error | Can duplicate transactions | Idempotent receipt write retry, never re-charge |
| Assigning `DECLINED` to timeouts | Gateway may have charged successfully | Use **unconfirmed** status, reconcile |
| Using `distinct` thinking each order saves once forever | Has no memory across runs | Durable deduplication / unique constraints |
| Returning raw exception messages in responses | Risk of leaking tokens/PII | Safe error codes + redacted logging |
| Updating a shared mutable map from lambdas | Violates non-interference and thread safety | Owned collector or explicit loop |
| Testing only `toList()` output | Misses gateway call counts or wrong states | Fake ports + integration tests |
| Running side effects before validating the batch | Tail input fails after partial charges | Prepare/validate all when size allows |
| Materializing billions of records into `List` | Out-of-memory risk | Chunking/staging/checkpoints with partial-progress contract |
| Assuming `Stream.close()` rolls back operations | Only manages stream-bound resources | Separate transaction/compensation design |

### 19.1. Why Is `peek` Still Useful?

`peek` can inspect values at a processing stage when debugging:

```java
List<String> normalized = names.stream()
    .map(String::strip)
    .peek(value -> System.out.println("DEBUG: " + value))
    .filter(value -> !value.isEmpty())
    .toList();
```

Treat this only as **ad-hoc diagnostic logging**. Never establish an audit contract assuming every input produces one record and never depend on pipeline optimization choices.

### 19.2. Mock Verification “Called Twice” Is Insufficient for Distributed Systems

A mock may count two `gateway.charge` calls in a happy run; that does not prove:

- The transaction runs once when the process crashes.
- Whether a timeout happened before or after server persistence.
- Whether the gateway actually enforces idempotency keys.
- Whether receipts persist durably upon `save` returning.
- That two workers never claim the same job in production.

These guarantees must be designed and tested at **system boundaries**, not assumed from Java Stream API properties.

## 20. Workflow for Refactoring an I/O Pipeline into Two Phases

Suppose you inherit legacy code:

```java
var result = orders.stream()
    .filter(Order::ready)
    .map(order -> gateway.charge(order))
    .map(receipt -> repository.saveAndReturn(receipt))
    .toList();
```

It mixes transformations, service calls, and persistence. A step-by-step refactoring path:

### Step 1 — List Every Actual Side Effect

Do not judge only by the name `map`; check function implementations or port docs:

| Function | Reads external state? | Writes external state? | Possible errors? |
| --- | --- | --- | --- |
| `Order::ready` | No if Order is immutable | No | Mostly data errors |
| `orderToCommand` | No | No | Validation/overflow |
| `gateway.charge` | Yes, service state | Yes, payment | Timeout, decline, server error |
| `repository.save` | Yes, database | Yes, receipt record | Conflict, timeout, DB error |

The goal is identifying boundaries **needing operational policy**, not merely changing syntax.

### Step 2 — Move Pure Transformations into `prepare`

```java
Plan plan = prepare(orders);
```

Check before execution:

- `orderId` is valid and unique.
- `amountCents` fits supported bounds.
- Only `ready` orders enter the command list.
- Totals use `Math.addExact` to avoid silent overflow.
- Every command carries a stable key.

### Step 3 — Define Ports Instead of Calling SDKs Directly Inside Mappers

```java
interface ChargeGateway {
    ChargeReceipt charge(ChargeCommand command)
        throws GatewayException;
}

interface ReceiptStore {
    void save(ChargeReceipt receipt)
        throws StoreException;
}
```

With these interfaces, orchestration code can be tested using fakes, while real adapters translate HTTP/SQL failures into structured business errors or outcomes.

### Step 4 — Decide Boundary Policy

For example:

- On uncertain gateway error: record `CHARGE_UNCONFIRMED` and route to reconciliation.
- On database error when receipt exists: record `RECEIPT_WRITE_FAILED` for persistence retry.
- If halting the whole batch is needed: **halt** on classified failure and return/persist statuses of processed commands, never assuming the batch rolled back automatically.

### Step 5 — Emit `ProcessReport` and Reconcile Totals

```java
ProcessReport report = execute(plan, gateway, receiptStore);

long recorded = report.results().stream()
    .filter(r -> r.status() == ExecutionStatus.RECORDED)
    .count();

long uncertain = report.results().stream()
    .filter(r ->
        r.status() == ExecutionStatus.CHARGE_UNCONFIRMED)
    .count();
```

Type names here are nested inside `SafeOrderProcessing` (section 7); outside that class, use static imports or write `SafeOrderProcessing.ProcessReport` and `SafeOrderProcessing.ExecutionStatus`.

Under continue-on-known-error with no unexpected failures, outcome count equals command count. In production, also inspect durable state to catch jobs interrupted by crashes.

### Step 6 — Add Integration Tests Before Increasing Concurrency

Prioritize testing:

1. Timeout before gateway processes.
2. Timeout **after** gateway processes.
3. Receipt persistence failure after charge confirmation.
4. Worker restart between the two steps.
5. Retries with the same key, identical payload vs. altered payload.
6. Two workers attempting to claim the same job.
7. Status lookup results matching batch reports.

Only once semantics are solid should you raise concurrency, benchmark, or introduce queues.

## 21. Practice Exercises

### Exercise 1 — Classifying Pure Functions and Side-Effecting Functions

Given `normalizeName`, `calculateTax`, `LocalDate.now`, `db.insert`, `http.get`, `new Dto`, and `sharedCounter.incrementAndGet`. Classify which can sit inside `map` as pure transformations and which must be separated. Explain why a method taking immutable inputs yet **reading the clock** is still impure.

### Exercise 2 — Refactoring a Database-Writing Pipeline

Transform:

```java
orders.stream()
    .filter(Order::ready)
    .map(repository::save)
    .toList();
```

into:

1. A `Plan` holding pure `SaveCommand`s.
2. A loop calling `repository.save`.
3. A `ProcessReport` recording success or error per command.

Define whether the batch **fails fast** or **continues**. Never return a “saved” list omitting failed commands.

### Exercise 3 — Timeouts Do Not Prove Business Failure

Describe the event sequence:

```text
charge(K) sent → gateway charges successfully → response lost
```

Why is `catch (TimeoutException) { retry(newKey); }` dangerous? Propose idempotency rules and a transaction lookup API before retrying.

### Exercise 4 — Two Errors at Two Different Points

In `SafeOrderProcessing`, simulate:

- Gateway throwing `GatewayException` for O1.
- Store throwing `StoreException` for O3.

What is each order's status? Is any order guaranteed not to have been charged? Write a JUnit test checking each `ExecutionStatus` and store call count.

### Exercise 5 — Duplicate IDs and Amount Overflow

Add two orders sharing `id` with different `customerId`s. Verify `prepare` rejects them before any service calls. Also create two orders whose sum exceeds `Long.MAX_VALUE`, verifying `Math.addExact` fails the preparation phase without returning a `Plan`.

### Exercise 6 — Enrichment Before Pure Transformations

Given an order list with many repeated `customerId`s:

1. Use Stream to produce distinct customer IDs.
2. Call the profile lookup service in an explicit step.
3. Return `LookupOk` / `LookupFailed` per ID.
4. Join results into a report using pure transformations.

If a profile is missing or the service times out, choose fail-fast or best-effort policy and explain how metrics are affected.

### Exercise 7 — Very Large File Sources

Design an import pipeline for a hundreds-of-GB CSV file. Why are `readAllLines` or `Files.lines(...).toList()` before all transactions unsuitable? Propose chunk sizes, validation, durable intent, checkpoints, and dedup keys. Explain the difference between “one chunk finished” and “whole file finished.”

### Exercise 8 — Outbox and Event Publishing

An app must update `Order.status` in the database and publish an `OrderApproved` event. Sketch the transactional outbox, publishing worker, and idempotent consumer. Point out the gap that can publish an event **more than once**, and why `Stream.distinct()` cannot solve it.

### Exercise 9 — Concurrency Limits

Suppose a gateway allows at most 5 concurrent requests and 100 requests/minute. Plan a coordinator for 1,000 commands covering:

- Concurrent task limit.
- Rate-limiting mechanism.
- Per-request deadline.
- Stable idempotency key.
- Per-request outcome persistence.
- Reconciling unknown-status requests.

Explain why simply calling `orders.parallelStream()` fails to satisfy these requirements.

### Exercise 10 — Immutability and Input Preconditions

Prove `List.copyOf` keeps `Plan` insulated when callers add/remove elements in the original list **after snapshot creation**. Then replace `Order` with a mutable class whose `amountCents` getter can change from another thread; explain why `List.copyOf` **does not deep-copy** elements and why value objects or defensive copies are needed.

### Exercise 11 — Exact Contract of `peek`

Write a stream snippet using `peek` for debug logging. Apply different terminals (`toList`, `count`, `findFirst`) on fresh streams. Explain why log counts are an unreliable measure of “elements processed” or audit actions recorded.

### Exercise 12 — Defining “Completed”

A batch has 95 saved receipts, 3 unconfirmed charges, and 2 failed receipt saves. Design the return DTO for API and dashboard. Specify:

- Should it return HTTP 200, 207, or an async workflow status? Depends on API contract.
- Which IDs must be reconciled?
- Under what condition can you report “batch complete with zero pending work”?
- On retry queries, how do you prevent triggering unintended extra charges?

## 22. Pre-Production Design Checklist

- [ ] Clearly identified which steps are **pure** and which cause external side effects.
- [ ] Validation/duplicate checks run **before** side effects whenever possible.
- [ ] Commands carry identifiers and stable idempotency keys.
- [ ] Explicit contracts exist for confirmed charge, decline, and unknown outcome.
- [ ] Exceptions are classified; never swallowed into `null` or empty results.
- [ ] Auditing does not rely on `peek` or mapper invocation counts.
- [ ] Rate limiting and transactions do not rely on `parallelStream`.
- [ ] Fail-fast vs. continue-on-error is explicitly defined per batch.
- [ ] Durable state/progress enables recovery after process crashes.
- [ ] Timed-out requests have lookup/reconciliation paths.
- [ ] Receipt persistence and DB steps use appropriate transactions/unique constraints.
- [ ] Compensation strategies exist where business rules require cross-system undo.
- [ ] Charges are never retried merely because receipt persistence failed.
- [ ] I/O sources have clear owners and `try-with-resources`.
- [ ] Batch/chunk sizes, timeouts, and concurrency are appropriately bounded.
- [ ] Outcome reports include all statuses and remaining pending counts.
- [ ] Outputs never expose tokens, card data, or sensitive raw exceptions.
- [ ] Unit tests with fake ports and integration tests with real systems exist.
- [ ] Documented explicitly that the Stream API provides **neither** exactly-once delivery **nor** distributed transactions.

## 23. Decision Table and Summary

| Problem | Typical appropriate approach |
| --- | --- |
| Transform immutable records to DTOs | Pure `map` in Stream |
| Filter elements by business rules | `filter` with pure predicate |
| Sum and summarize over stable datasets | `reduce`, `collect`, or summary collector |
| Validate entire batch before calling external systems | Pure `prepare` → immutable `Plan` → `execute` |
| Call API per command and persist status | Service coordinator with bounded concurrency and per-item results |
| Timeout after request may have processed | **UNCONFIRMED** status, lookup/reconcile |
| Retry a side-effecting command | Stable idempotency key + receiver contract |
| Persist receipt after charge failed to save | Retry save/reconcile, **never recharge by default** |
| Update DB and publish events | Transactional outbox + idempotent consumer |
| Write to same database atomically | DB transaction per database contract |
| Process huge files | Chunking/staging/checkpoints, expose partial progress |
| File source from `Files.lines` | `try-with-resources` before crossing side-effect boundary |
| Upstream may short-circuit | Never place mandatory audit/charge inside `peek`/mapper |
| Preserve report display order | Carry sequence ID and sort after collecting; do not equate with commit order |
| Need valid empty results | Model separately from service or file errors |
| Prove correctness on failures | Fake ports, status assertions, integration/failure tests |

### Conclusion

**Separating service calls and persistence from pure transformations** is a design principle that lets the Java Stream API excel at its true role: **describing data processing**, rather than masquerading as a transaction coordinator. `filter`, `map`, `reduce`, and `collect` are powerful for building plans and aggregating results; HTTP, databases, queues, and side effects need boundaries with explicit error policies, states, timeouts, retries, idempotency, and operational observability.

A short pipeline is not automatically safer than a well-named loop with proper contracts. Favor **deterministic outcomes in the pure phase**, **coordinated actions at the side-effect phase**, and **recoverable state on failures**. That makes testing, parallelization, and incident recovery far easier to reason about while still leveraging the declarative transformations of **JAVA_STREAM_API**.
