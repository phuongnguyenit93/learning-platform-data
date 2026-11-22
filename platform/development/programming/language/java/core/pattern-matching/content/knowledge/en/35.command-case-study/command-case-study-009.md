# Logging the Selected Pattern — Command Case Study (Java 21)

## 1. The problem: knowing exactly which branch handled a command

In a system that receives commands, input data is often modeled using a **sealed hierarchy**: create order, cancel order, refund order, etc. Java 21 allows using **pattern matching for `switch`** and **record patterns** to classify each command, extract components, and apply `when` guards.

However, when a request passes through a `switch`, operators may need to answer:

- **Which case** did this request select?
- Which guard caused `CreateOrder` to enter the **bulk** branch instead of the standard branch?
- Which rule rejected the command?
- Was a command merely **selected for processing**, or did the business operation **actually execute successfully**?
- Can it be traced by `traceId` **without logging access tokens, bank accounts, or private content**?

If you only log `command.getClass().getSimpleName()`, you know the outermost subtype, but **not which guarded branch** was selected. If you log the entire `command` via the record's `toString()`, you risk exposing sensitive components. If you run a second `switch` just to "rediscover the branch", you may re-evaluate guards, producing divergent results or side effects.

**Core solution of this lesson:** Use a single `switch expression` that **selects a branch once**, returns a `Decision` containing a **stable branch identifier**, and then records **one audit event** from that `Decision`. Clearly separate "pattern selected" from "operation committed successfully".

**Version:** Examples use **Java 21**, where record patterns (JEP 440) and pattern matching for `switch` (JEP 441) are standard features. No `--enable-preview` is needed. All examples run on Java SE; no external logging library is required for the demo.

After this lesson, you will be able to:
1. Design branch names (*branch identifiers*) that reflect the case actually selected.
2. Log after selection without repeating pattern matching or guards.
3. Distinguish **selected**, **accepted/rejected**, and **business execution succeeded/failed**.
4. Handle null, dominance, exhaustiveness, and exception paths properly.
5. Avoid sensitive data leakage and log injection.
6. Write tests to verify both **processing behavior** and **audit events**.

## 2. Domain model: a command hierarchy with multiple logical branches

Suppose the system supports three types of commands:

```text
Command (sealed interface)
├── CreateOrder(orderId, quantity, accessToken)
├── CancelOrder(orderId, urgent, privateReason)
└── RefundOrder(orderId, cents, bankAccount)
```

The three subtypes are records:

```java
// Illustrative snippet; full declarations are in the section 6 program.
sealed interface Command permits CreateOrder, CancelOrder, RefundOrder {}

record CreateOrder(String orderId, int quantity, String accessToken)
        implements Command {}

record CancelOrder(String orderId, boolean urgent, String privateReason)
        implements Command {}

record RefundOrder(String orderId, int cents, String bankAccount)
        implements Command {}
```

In this example:
- `quantity <= 0` causes `CreateOrder` to be rejected.
- `quantity >= 10` is a bulk `CreateOrder`.
- Remaining valid `CreateOrder` commands are standard.
- `CancelOrder.urgent == true` is the urgent cancellation branch.
- `RefundOrder.cents <= 0` is rejected; positive values are accepted for further processing.
- A null selector is recorded as `NO_COMMAND`.

**The `ACCEPTED` value in this lesson only describes the classification/acceptance result at the command decision layer. It does not mean the order has been created, money has been refunded, the transaction has committed, or an external system has responded successfully.** Section 10 discusses logging actual execution.

### Why is the subtype not enough as a log label?

These two commands have the same `CreateOrder` type:

```java
new CreateOrder("O1", 2, "token-secret-1");
new CreateOrder("O2", 10, "token-secret-2");
```

Yet they must select **two different branches**: `CREATE_STANDARD` and `CREATE_BULK`. The class name `CreateOrder` does not capture that distinction.

Similarly, a `RefundOrder` with `cents == 0` and a `RefundOrder` with `cents > 0` require different reject/accept outcomes. Therefore, the **branch identifier** must be bound to the specific branch **after guards are evaluated**, not merely to the runtime class.

## 3. Selected pattern is a separate event

Separating concepts helps avoid misleading logs:

| Concept | Example | What is guaranteed |
| --- | --- | --- |
| Command received | `type=CreateOrder` | The system has received the input data |
| Pattern selected | `branch=CREATE_BULK` | The corresponding pattern and guard were selected |
| Decision outcome | `outcome=ACCEPTED` | The decision layer agreed to proceed with processing |
| Execution started | `operation=create-order` | A workflow with side effects has started |
| Execution succeeded | `status=SUCCEEDED` | The operation/transaction met its defined success criteria |
| Execution failed | `status=FAILED` | The operation failed to meet its success criteria, with an appropriate failure reason |

If a request is labeled `CREATE_BULK` and then the repository throws an error before commit, logging `branch=CREATE_BULK` is still **correct**, whereas logging `order.created=true` would be **wrong**. Do not turn every message after a `switch` into "command processed successfully".

In this lesson, we choose a simple `Decision`:

```java
enum Branch {
    CREATE_REJECTED, CREATE_BULK, CREATE_STANDARD,
    CANCEL_URGENT, CANCEL_STANDARD,
    REFUND_REJECTED, REFUND_APPROVED, NO_COMMAND
}

record Decision(Branch branch, String outcome) {}
```

`Branch` is an **internal code with a finite set of values**, containing no tokens, account numbers, or untrusted data. `outcome` in the demo is `"ACCEPTED"` or `"REJECTED"`. In larger systems, `String outcome` can be replaced with an `enum Outcome` to prevent typos.

An audit event can contain:

```java
record AuditEvent(String traceId, Branch branch, String outcome) {}
```

**`traceId`** in the demo is a system-issued trace ID, such as `T01`. In production, you must control the source, format, and length of trace/correlation IDs: never pass an arbitrary string verbatim from an HTTP header into text logs without validation, as that can lead to newline injection and forged log records (*log injection*).

## 4. Proper branch-selection structure in Java 21

The key point is that **every case returns the same result type** — `Decision`:

```java
// Illustrative snippet inside a method receiving Command command:
return switch (command) {
    case CreateOrder(String id, int quantity, String token)
            when quantity <= 0 ->
        new Decision(Branch.CREATE_REJECTED, "REJECTED");

    case CreateOrder(String id, int quantity, String token)
            when isBulk(quantity) ->
        new Decision(Branch.CREATE_BULK, "ACCEPTED");

    case CreateOrder(String id, int quantity, String token) ->
        new Decision(Branch.CREATE_STANDARD, "ACCEPTED");

    case CancelOrder(String id, boolean urgent, String reason)
            when urgent ->
        new Decision(Branch.CANCEL_URGENT, "ACCEPTED");

    case CancelOrder(String id, boolean urgent, String reason) ->
        new Decision(Branch.CANCEL_STANDARD, "ACCEPTED");

    case RefundOrder(String id, int cents, String account)
            when cents <= 0 ->
        new Decision(Branch.REFUND_REJECTED, "REJECTED");

    case RefundOrder(String id, int cents, String account) ->
        new Decision(Branch.REFUND_APPROVED, "ACCEPTED");

    case null ->
        new Decision(Branch.NO_COMMAND, "REJECTED");
};
```

Here:
- Each **record pattern** deconstructs the record and binds variables in the exact component positions.
- The `when` guard is only evaluated after the record pattern matches.
- If a guard returns `false`, subsequent cases are still considered.
- Guarded cases appear **before** unguarded cases of the same subtype to avoid being dominated.
- `case null` catches a null selector specifically; it is not a general fallback for the three command types.
- `Command` is sealed and its three direct permitted subtypes are records (final), so unguarded cases covering each subtype make the `switch expression` exhaustive without needing `default`.

**Important for logging:** Each branch **returns a branch ID**. There is no second step guessing the branch from the class or re-checking `quantity`/`urgent`. A guard might depend on mutable data, timing, or side effects; re-evaluating it is not a reliable way to reconstruct the selected branch.

### Guards are case-selection conditions, not a place to log arbitrarily

An approach you should not overuse:

```java
// Illustrative anti-pattern:
case CreateOrder(String id, int q, String token)
    when logAndCheckBulk(q) -> ...;
```

If `logAndCheckBulk` both logs and decides the condition:
- The log may be emitted **before knowing whether the case is actually selected**.
- When the guard returns false, a record like "selected CREATE_BULK" is inaccurate.
- If the guard throws an exception, case selection terminates abnormally; any fallback case is not considered selected.
- Testing and benchmarking become harder to separate business checks from audit side effects.

**Recommendation:** Keep guards pure and easy to understand; emit the audit event after receiving `Decision`. If you need a metric for *guard evaluated*, that is a different kind of instrumentation and must not be mislabeled as *branch selected*.

## 5. Three ways to place logging: strengths and risks

### Approach A — Logging directly inside each case

For example:

```java
// Illustrative snippet, not a complete switch expression:
case CreateOrder(String id, int quantity, String token) -> {
    audit.record(...); // log directly inside the case
    yield new Decision(Branch.CREATE_STANDARD, "ACCEPTED");
}
```

Strength: The log site is close to the selected branch. However, when many cases have long bodies, it is easy to duplicate boilerplate, miss a case, or log a branch name that does not match the branch. During refactoring, business logic and audit code become intertwined.

If business requirements demand **recording an event at the exact moment a branch is entered** before any side effect occurs, this approach can be considered, provided there is a clear contract and per-case tests. Do not treat this approach as strictly wrong.

### Approach B — Producing Decision in switch, logging once afterward

```java
// General pattern:
Decision decision = select(command);
sink.record(new AuditEvent(traceId,
    decision.branch(), decision.outcome()));
return decision;
```

Strengths:
- `Decision` itself is the source of truth for the selected branch.
- A single logging point prevents missing a case when adding subtypes.
- Easy to verify **one event per successful call**.
- Does not re-run guards; the same `Decision` can be passed to the next handler step.
- Logging can be decoupled from branch-selection rules.

This is the pattern **used in the runnable program** of this lesson.

### Approach C — Logging in the orchestration/observability adapter layer

An application service can call `select(command)`, then send the event to an `AuditSink`, logger, or tracing span. This keeps the domain decision relatively pure; logging infrastructure is encapsulated in the adapter.

Especially useful when you need:
- Structured JSON logs.
- Correlation with request/trace/span.
- Data filtering/masking policies.
- Logging at INFO/WARN/ERROR levels based on outcome.
- Control over sampling, retention, and log access permissions.

**Condition:** The selection-layer API must return enough metadata for the adapter to know **the branch actually selected**. If the adapter only receives `Command` back and pattern-matches again, you are back to the risk of re-evaluating logic.

## 6. Complete Java 21 program: 8 branch events, no secret leakage

Create the file **`CommandPatternAuditDemo.java`**. The code uses only Java SE and writes audit output to stdout in a fixed format for **exact result verification**. `MemoryAuditSink` is a test double, not a durable/transactional production audit store.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class CommandPatternAuditDemo {
    sealed interface Command
            permits CreateOrder, CancelOrder, RefundOrder {}

    record CreateOrder(String orderId, int quantity, String accessToken)
            implements Command {}

    record CancelOrder(String orderId, boolean urgent,
                       String privateReason)
            implements Command {}

    record RefundOrder(String orderId, int cents, String bankAccount)
            implements Command {}

    enum Branch {
        CREATE_REJECTED, CREATE_BULK, CREATE_STANDARD,
        CANCEL_URGENT, CANCEL_STANDARD,
        REFUND_REJECTED, REFUND_APPROVED, NO_COMMAND
    }

    record Decision(Branch branch, String outcome) {}

    record AuditEvent(String traceId, Branch branch, String outcome) {}

    interface AuditSink {
        void record(AuditEvent event);
    }

    static final class MemoryAuditSink implements AuditSink {
        final List<AuditEvent> events = new ArrayList<>();

        @Override
        public void record(AuditEvent event) {
            events.add(event);
            System.out.printf("AUDIT trace=%s branch=%s outcome=%s%n",
                    event.traceId(), event.branch(), event.outcome());
        }
    }

    static int bulkGuardCalls;

    static boolean isBulk(int quantity) {
        bulkGuardCalls++;
        return quantity >= 10;
    }

    static Decision select(Command command) {
        return switch (command) {
            case CreateOrder(String id, int quantity, String token)
                    when quantity <= 0 ->
                new Decision(Branch.CREATE_REJECTED, "REJECTED");

            case CreateOrder(String id, int quantity, String token)
                    when isBulk(quantity) ->
                new Decision(Branch.CREATE_BULK, "ACCEPTED");

            case CreateOrder(String id, int quantity, String token) ->
                new Decision(Branch.CREATE_STANDARD, "ACCEPTED");

            case CancelOrder(String id, boolean urgent, String reason)
                    when urgent ->
                new Decision(Branch.CANCEL_URGENT, "ACCEPTED");

            case CancelOrder(String id, boolean urgent, String reason) ->
                new Decision(Branch.CANCEL_STANDARD, "ACCEPTED");

            case RefundOrder(String id, int cents, String account)
                    when cents <= 0 ->
                new Decision(Branch.REFUND_REJECTED, "REJECTED");

            case RefundOrder(String id, int cents, String account) ->
                new Decision(Branch.REFUND_APPROVED, "ACCEPTED");

            case null ->
                new Decision(Branch.NO_COMMAND, "REJECTED");
        };
    }

    static Decision handle(Command command, String traceId, AuditSink sink) {
        Objects.requireNonNull(traceId, "traceId");
        Objects.requireNonNull(sink, "sink");

        Decision decision = select(command);
        sink.record(new AuditEvent(
            traceId, decision.branch(), decision.outcome()));
        return decision;
    }

    static void verify(
            MemoryAuditSink sink, String traceId, Command command,
            Branch expectedBranch, String expectedOutcome,
            int expectedGuards) {
        int beforeEvents = sink.events.size();
        int beforeGuards = bulkGuardCalls;
        Decision decision = handle(command, traceId, sink);

        if (decision.branch() != expectedBranch ||
                !decision.outcome().equals(expectedOutcome)) {
            throw new AssertionError(
                "Wrong decision for " + traceId);
        }
        if (sink.events.size() != beforeEvents + 1) {
            throw new AssertionError(
                "Must emit exactly one audit event");
        }

        AuditEvent recorded = sink.events.get(beforeEvents);
        if (!recorded.traceId().equals(traceId) ||
                recorded.branch() != expectedBranch ||
                !recorded.outcome().equals(expectedOutcome)) {
            throw new AssertionError(
                "Audit does not match selected branch");
        }
        if (bulkGuardCalls - beforeGuards != expectedGuards) {
            throw new AssertionError(
                "Guard evaluated wrong number of times");
        }
    }

    public static void main(String[] args) {
        MemoryAuditSink sink = new MemoryAuditSink();

        verify(sink, "T01",
            new CreateOrder("O1", 2, "token-secret-1"),
            Branch.CREATE_STANDARD, "ACCEPTED", 1);
        verify(sink, "T02",
            new CreateOrder("O2", 10, "token-secret-2"),
            Branch.CREATE_BULK, "ACCEPTED", 1);
        verify(sink, "T03",
            new CreateOrder("O3", 0, "token-secret-3"),
            Branch.CREATE_REJECTED, "REJECTED", 0);

        verify(sink, "T04",
            new CancelOrder("O4", true, "cancel-confidential"),
            Branch.CANCEL_URGENT, "ACCEPTED", 0);
        verify(sink, "T05",
            new CancelOrder("O5", false, "cancel-confidential"),
            Branch.CANCEL_STANDARD, "ACCEPTED", 0);

        verify(sink, "T06",
            new RefundOrder("O6", 500, "account-777"),
            Branch.REFUND_APPROVED, "ACCEPTED", 0);
        verify(sink, "T07",
            new RefundOrder("O7", 0, "account-888"),
            Branch.REFUND_REJECTED, "REJECTED", 0);

        verify(sink, "T08", null,
            Branch.NO_COMMAND, "REJECTED", 0);

        String recorded = sink.events.toString();
        if (recorded.contains("token-secret") ||
                recorded.contains("cancel-confidential") ||
                recorded.contains("account-")) {
            throw new AssertionError(
                "Sensitive data leaked to audit");
        }

        System.out.println("EVENTS=" + sink.events.size());
        System.out.println("BULK_GUARD_CALLS=" + bulkGuardCalls);
        System.out.println("SECRETS_PRESENT=false");
    }
}
```

Compile and run on **JDK 21 or later**:

```bash
javac --release 21 CommandPatternAuditDemo.java
java CommandPatternAuditDemo
```

**Exact stdout:**

```text
AUDIT trace=T01 branch=CREATE_STANDARD outcome=ACCEPTED
AUDIT trace=T02 branch=CREATE_BULK outcome=ACCEPTED
AUDIT trace=T03 branch=CREATE_REJECTED outcome=REJECTED
AUDIT trace=T04 branch=CANCEL_URGENT outcome=ACCEPTED
AUDIT trace=T05 branch=CANCEL_STANDARD outcome=ACCEPTED
AUDIT trace=T06 branch=REFUND_APPROVED outcome=ACCEPTED
AUDIT trace=T07 branch=REFUND_REJECTED outcome=REJECTED
AUDIT trace=T08 branch=NO_COMMAND outcome=REJECTED
EVENTS=8
BULK_GUARD_CALLS=2
SECRETS_PRESENT=false
```

### Why is stdout deterministic?

The demo uses `System.out.printf` with fixed data and ordering, without adding timestamps or thread IDs. In production, loggers typically add timestamps, levels, thread names, and trace/span context, and may write asynchronously; in that setting, do not expect the **entire log line** to match verbatim every time.

The program uses an in-memory test double to demonstrate the **event schema and branch-selection path**, not to replace a real audit storage service.

## 7. Analyzing each test: the branch ID is the selected case

| Request | Command | Selected case | Outcome |
| --- | --- | --- | --- |
| `T01` | `CreateOrder(quantity=2)` | `CREATE_STANDARD` | `ACCEPTED` |
| `T02` | `CreateOrder(quantity=10)` | `CREATE_BULK` | `ACCEPTED` |
| `T03` | `CreateOrder(quantity=0)` | `CREATE_REJECTED` | `REJECTED` |
| `T04` | `CancelOrder(urgent=true)` | `CANCEL_URGENT` | `ACCEPTED` |
| `T05` | `CancelOrder(urgent=false)` | `CANCEL_STANDARD` | `ACCEPTED` |
| `T06` | `RefundOrder(cents=500)` | `REFUND_APPROVED` | `ACCEPTED` |
| `T07` | `RefundOrder(cents=0)` | `REFUND_REJECTED` | `REJECTED` |
| `T08` | `null` | `NO_COMMAND` | `REJECTED` |

`verify` does more than compare the return value. It also checks:
1. **`Decision.branch`** equals the expected value.
2. **`Decision.outcome`** equals the expected value.
3. `sink.events.size()` increases by **one** after each normal `handle` completion.
4. **The stored record** carries the exact `traceId`, branch, and outcome.
5. The `isBulk` guard is called the expected number of times in the **single-threaded flow of the lesson**.

Because these checks throw `AssertionError` directly, the demo **does not require** enabling `java -ea`.

### How many times is the guard evaluated?

In the example:
- `T01`: `quantity=2` does not satisfy the first guard `quantity <= 0`, then `isBulk(2)` runs **once** and returns false; the standard case is selected.
- `T02`: `quantity=10` causes `isBulk(10)` to run **once** and return true; the bulk case is selected.
- `T03`: `quantity=0` matches the rejected case **immediately**; `isBulk` is not called.
- The `CancelOrder`, `RefundOrder`, and null selector paths do not need to run `isBulk`.

Total `BULK_GUARD_CALLS=2`. The counter here is **for testing only**, because a mutable `static int` is not thread-safe when multiple threads process commands concurrently.

Two takeaways follow:
- Do not place audit logging inside `isBulk` and call it "bulk selected".
- If you need a metric for how many times a guard is checked, separate that metric from the **selected-branch audit event**.

### Why does the log only contain traceId, branch, and outcome?

`CreateOrder` contains `accessToken`, `CancelOrder` contains `privateReason`, and `RefundOrder` contains `bankAccount`. They are included in the commands to show that record patterns **can bind sensitive data**, yet **should not log it by default**.

The test intentionally searches for sensitive marker strings in the recorded audit events and fails if any leak occurs. This is only an example-based check; production requires masking policies, allowlists, schema reviews, and testing across all real data sources.

## 8. Anti-patterns: logging the whole record or running a second switch

### 8.1. Logging `command.toString()` can leak data

A record's default `toString()` displays the record name and all component values. With records like:

```java
// Intentional example of what not to use for audit:
System.out.println("command=" + command);
```

the resulting string may contain `accessToken`, `bankAccount`, or a private cancellation reason. Even if you do not print those fields directly inside `switch`, they can still appear indirectly through `toString()` or a logger that accepts the object and formats it automatically.

**Better approach:** Use an **allowlist** of permitted fields: a system-managed `traceId`, `branch` from an enum, `outcome` from an enum/finite string set, and approved metadata such as duration or error code. Never pass the raw command object into a log event.

### 8.2. Logging the class name cannot distinguish guarded branches

`command.getClass().getSimpleName()` can only tell you it is `CreateOrder`, not whether the branch is `CREATE_REJECTED`, `CREATE_BULK`, or `CREATE_STANDARD`. If `command` is null, `getClass()` also throws `NullPointerException`.

**Better approach:** Take `Decision.branch()` from the **same switch that selected the case**.

### 8.3. Re-running pattern matching just for logging

Do not write one switch for business logic and a second "equivalent" switch to determine the log label:

```java
// Design-level anti-pattern (illustrative only):
Decision decision = select(command);
String branchForLog = selectAgain(command);
```

If `selectAgain` has guards, it may **re-evaluate conditions**. Conditions might depend on the clock, external state, recently changed configuration, or side effects. Even if the two switches match today, they can drift when a new branch is added and someone forgets to update the logging switch.

**Better approach:** Log `decision.branch()` after `select`; do not repeat selection.

### 8.4. Logging before a guard returns true

For example:

```java
// Anti-pattern inside a guard:
case CreateOrder(String id, int quantity, String token)
        when traceBulkCandidate(quantity) -> ...
```

If `traceBulkCandidate` logs "CREATE_BULK selected" and then returns false, the audit event is wrong. A guard **being evaluated** does not mean that case **was selected**.

## 9. Exhaustiveness, dominance, and null: three rules to protect

### 9.1. Adding a subtype must trigger a branch log review

Suppose you add:

```java
// Illustrative model change:
record RescheduleOrder(String orderId, String slot)
        implements Command {}
```

You must update `permits RescheduleOrder` on the sealed interface. With `select` listing each subtype without a `default`, the Java 21 compiler reports that the `switch expression` is not exhaustive when the new case is missing.

This acts as a **built-in reminder to update branches and event schemas**:
- Choose business behavior for `RescheduleOrder`.
- Assign a distinct Branch ID if meaningful.
- Add tests asserting both the new branch and its audit event.
- Review data classification so `slot` or private fields are not logged accidentally.
- Update dashboards/metrics/documentation for the new schema.

Do not blindly add `default -> new Decision(OTHER, "ACCEPTED")` just to make the build green if the requirement is to classify every command explicitly.

### 9.2. Guarded cases must precede unguarded cases covering the whole subtype

Incorrect example:

```java
// INTENTIONALLY WRONG, placed in the same switch:
case CreateOrder(String id, int quantity, String token) ->
    new Decision(Branch.CREATE_STANDARD, "ACCEPTED");

case CreateOrder(String id, int quantity, String token)
        when quantity >= 10 ->
    new Decision(Branch.CREATE_BULK, "ACCEPTED");
```

The unguarded case matches all `CreateOrder` instances; the bulk case below it is **dominated**. The compiler reports an error, so they cannot be treated as two equally selectable cases.

In the demo, the `quantity <= 0` and `isBulk(quantity)` guards appear before the unguarded `CreateOrder` case. As a result, the logged branch ID reflects the policy from most specific to most general.

### 9.3. `case null` is not the same as `default`

`case null -> new Decision(Branch.NO_COMMAND, "REJECTED")` handles a null selector according to the demo contract. In a Java 21 pattern switch, a plain `default` does not mean a null selector will be matched.

A null record component is also different from a null selector. For example, `new CreateOrder("O1", 2, null)` is still a non-null `CreateOrder` and can match the record pattern. In Java 21, an unconditional type pattern at a component position declared as `String` can bind null; therefore, do not assume a null component automatically causes a record pattern to fail.

**Domain design:** In production you can forbid null/blank tokens at the constructor or boundary; this lesson keeps the data simple to demonstrate auditing without leaking tokens. Do not confuse "not logging tokens" with "not validating tokens".

## 10. Logging pattern selection vs. logging execution outcomes

A key practice in command systems is separating **phases**:

```text
request received
   |
   v
select(Command) --> Decision(branch, outcome)
   |
   +--> audit: COMMAND_PATTERN_SELECTED
   |
   v
business handler / transaction / external service
   |
   +--> audit: COMMAND_EXECUTION_SUCCEEDED
   |                 or
   +--> audit: COMMAND_EXECUTION_FAILED
```

In the demo, `ACCEPTED` is only input classification. To log execution outcomes, an application service can follow this **illustrative pattern**:

```java
// Java-style pseudocode: execute(...) and audit... functions are
// provided by the application service/adapter and do not run standalone.
Decision decision = select(command);
auditSelection(traceId, decision.branch(), decision.outcome());

if ("REJECTED".equals(decision.outcome())) {
    return;
}

try {
    execute(command, decision);
    auditExecution(traceId, decision.branch(), "SUCCEEDED");
} catch (RuntimeException ex) {
    auditExecution(traceId, decision.branch(), "FAILED");
    throw ex;
}
```

This is an **architectural pattern, not a compiled program**; depending on the real system, exceptions may be converted into domain results or handled at another boundary. The key points are:
- The `PATTERN_SELECTED` event records the fact of which case was chosen.
- The `EXECUTION_SUCCEEDED` event is only emitted when the use case's **definition of success** is met, not merely when a guard passes.
- The `EXECUTION_FAILED` event is emitted when the operation fails, while the original exception is preserved according to the error policy.
- All three can share the same `traceId` while having **different event types/phases**.

**Atomicity warning:** If the transaction commit and the log sink sending to another system are not in the same transaction, an event may be sent while the transaction rolls back, or vice versa. If the business requires durable/exactly-once auditing at storage level, design a transactional outbox, idempotency keys, retries, or an appropriate transactional audit mechanism. A single `sink.record(...)` call in code **does not** guarantee an event is stored exactly once in a distributed system.

## 11. Exception paths: when is no pattern selected?

Not every call to `select` returns a `Decision`. For example:
- The selector expression throws **before entering the switch**.
- A user-defined record accessor throws an exception during deconstruction (Java 21 may wrap it in `MatchException` with a cause).
- A `when` guard throws an exception. In that case, the guard is not treated as "false" to try the next case; the exception propagates.
- Code inside a case body throws an exception before yielding/returning `Decision`.
- Differences between compile-time and runtime hierarchies can lead to an unexpected `MatchException`.

**Consequence:** If `select(command)` has not produced a `Decision`, do not log a specific branch ID as if that branch had been selected. Emit a separate **selection failure event**, such as `COMMAND_SELECTION_FAILED` with a filtered error class/cause, instead of fabricating `CREATE_STANDARD` or `OTHER`.

### Layered error-handling pattern

```java
// Illustrative snippet when AuditSink sink, traceId, and Command command are available.
// This is an error-event policy, not verbatim code used in the demo.
Decision decision;

try {
    decision = select(command);
} catch (RuntimeException ex) {
    // Record a SELECTION_FAILED event at a separate boundary;
    // DO NOT call select() again and DO NOT treat the error as a selected case.
    reportSelectionFailure(traceId, ex.getClass().getSimpleName());
    throw ex;
}

sink.record(new AuditEvent(
    traceId, decision.branch(), decision.outcome()));
```

The `reportSelectionFailure` helper and inputs are provided by the application/observability layer; this snippet only illustrates the control flow. Do not put raw exception messages or stack traces into sensitive audit logs if they might contain tokens, private URLs, or personal data. Stack traces can go to restricted-access error logs under a separate policy.

**Do not let a logging failure turn into a "branch logic failure":** If the sink throws an exception while emitting an event, that is an audit infrastructure failure, distinct from a selection failure. Define a clear policy: fail closed if audit is mandatory; handle the error in the adapter and continue business processing if telemetry is best-effort and safe. Do not wrap `select`, `sink.record`, and `execute` in one broad `catch` and label every error as "no match".

## 12. Organizing structured logging in production

The demo prints:

```text
AUDIT trace=T02 branch=CREATE_BULK outcome=ACCEPTED
```

In a real system, store this as a **structured event with dedicated fields**, for example:

```json
{
  "event": "command.pattern_selected",
  "traceId": "T02",
  "branch": "CREATE_BULK",
  "outcome": "ACCEPTED"
}
```

This JSON illustrates the schema, not a requirement to depend on a specific logging technology.

A logging adapter can map `AuditEvent` into fields for SLF4J/Logback, Log4j, java.util.logging, OpenTelemetry, or your organization's observability platform. **Libraries do not make logs safe automatically**; you must define schemas, field allowlists, sanitization, and access controls.

### Fields to include and exclude

| Field | Log? | Condition |
| --- | --- | --- |
| `event`/`phase` | Yes | Stable, consistent enum/event name |
| `traceId` | Yes | System-managed ID, normalized and length-bounded |
| `branch` | Yes | Finite branch code, containing no payload |
| `outcome` | Yes | Well-defined set of values |
| `durationMs` | Yes, when useful | Measured with an appropriate clock, with clear phase semantics |
| `commandType` | Optional | Static label, not a replacement for branch |
| `errorCode` | Yes, when needed | Categorized error code, containing no PII |
| `accessToken`/passwords/API keys | **No** | Secrets must be excluded from audit/telemetry |
| Account numbers, payment details | Strict policy | Avoid by default; masking/tokenization and access control |
| `privateReason`/free-form text | Usually no | May contain PII, sensitive content, and injection characters |
| Full `command.toString()` | Not by default | Record `toString` may print every component |

**Risk-reduction tip:** Design your log schema using an **allowlist from the start**, rather than logging every field and trying to scrub sensitive ones later.

### Branch codes should remain stable across refactors

If you use `Branch.CREATE_BULK`, dashboards can query by `branch="CREATE_BULK"`. When renaming a class or adding a record component, you do not necessarily have to change the branch ID if the business meaning has not changed.

When semantics genuinely change, treat renaming a branch code as an **event schema change**: consider versioning, update alerts/dashboards, and support a transition period if downstream systems depend on it.

### Cardinality and cost

`branch` from an enum has low cardinality, making it suitable for metrics. Conversely, `orderId`, tokens, request payloads, or `traceId` have high cardinality: turning them into metric labels can explode time-series counts. Tracing IDs are useful for logs/traces, but every trace ID value should not be attached as a label on aggregated metrics.

If command traffic is very high, logging every match can incur significant I/O, CPU, storage, and retention costs. Distinguish **mandatory audit** from **samplable diagnostic logs**; sampling is inappropriate when legal or compliance policies require complete records.

## 13. Thread safety and correlation under concurrent command processing

In the section 6 program there is:

```java
static int bulkGuardCalls;
```

This is a **counter for a single-threaded test**, not a concurrent telemetry design. When multiple threads run `select` simultaneously, `++` is not atomic; the count can be wrong.

In a real application:
- Use a metrics SDK or thread-safe counter if you want to count guard/branch hits.
- Keep `traceId` in a request context or pass it explicitly down the call chain.
- Never use a `static String currentBranch` variable to remember the current request's branch; another request can overwrite it.
- If using MDC/ThreadLocal, set and clear the context in the proper lifecycle; async tasks/virtual threads need framework-supported context propagation.
- An audit event should be an object carrying all required request metadata passed to the sink; never reconstruct the branch from global state.

Especially with async processing, `PATTERN_SELECTED` may appear long before `EXECUTION_SUCCEEDED`. A request correlation ID links them, though it does not guarantee strict ordering if the sink is asynchronous or data arrives from multiple processes.

## 14. Testing logging properly

The test suite should verify both **business decisions** and **audit semantics**. Checking only that stdout contains `CreateOrder` is not enough.

### 14.1. Branch test matrix

| Case | Boundary data | What to assert |
| --- | --- | --- |
| Create invalid | `quantity=0`, optionally also -1 | `CREATE_REJECTED`, `REJECTED`, bulk guard not called |
| Create standard | `quantity=1` or 9 | `CREATE_STANDARD`, `ACCEPTED` |
| Create bulk | `quantity=10` or 11 | `CREATE_BULK`, `ACCEPTED` |
| Cancel urgent | `urgent=true` | `CANCEL_URGENT` |
| Cancel normal | `urgent=false` | `CANCEL_STANDARD` |
| Refund invalid | `cents=0`, optionally also -1 | `REFUND_REJECTED` |
| Refund approved | `cents=1` or 500 | `REFUND_APPROVED` |
| Null command | `command=null` | `NO_COMMAND`, `REJECTED` |

For the `quantity >= 10` guard, the **9/10** boundary pair is critical. A bulk test using 100 will not catch a bug where `> 10` was written instead of `>= 10`.

### 14.2. Exact event count for a single selection

After a normal `handle` call in the demo, `events.size()` must increase by **exactly one**. Tests should inspect the new event's metadata, not just the total count.

However, **"one event object added to an in-memory list" is not equivalent to exactly-once delivery** in an asynchronous/distributed system. Production requires additional integration tests for retries, duplicates, audit sink failures, and persistence.

### 14.3. Guard is not re-evaluated

`verify` compares the `isBulk` call count before and after `handle`:
- Valid `CreateOrder` commands check the bulk guard once.
- Invalid `CreateOrder` commands are handled by the earlier rejection case, so the bulk guard does not run.
- Other subtypes do not call the bulk guard.

If a handler re-runs `select` just for logging, the counter increases more than expected and the test catches the discrepancy.

### 14.4. No secret leakage

Test data intentionally includes `"token-secret-1"`, `"cancel-confidential"`, and `"account-777"`. The test checks for any occurrence of these markers in recorded events. If someone later replaces `AuditEvent` with a `Command` field or logs the whole record, the test can detect the leak.

For production, also add:
- Format validation for client-supplied IDs (CR/LF, control characters).
- Tests with Unicode content and long payloads.
- Verification of masking rules in logging adapters.
- Verification of access controls and log retention periods.
- Verification of the field set for each command type, including new subtypes.

### 14.5. Testing exception paths

Add tests that the demo does not simulate directly:
- Guard throws an exception → no false `PATTERN_SELECTED` event is emitted.
- Record accessor fails → the error is classified as a selection failure, not logged as a "selected branch".
- Logging sink throws an error → handled according to mandatory vs. best-effort audit policy, without re-running the business command.
- Business execution fails after selection → an `EXECUTION_FAILED` event is emitted instead of `EXECUTION_SUCCEEDED`.
- Runtime receives a new subtype after a hierarchy change → review exhaustive switches and handle build/deploy failures.

## 15. Common mistakes in code reviews

| Mistake | Risk | Fix |
| --- | --- | --- |
| Logging `command.toString()` | Exposes all record components, potentially secrets | Log an allowlisted schema with branch ID |
| Logging only the class name | Cannot distinguish guards on the same subtype | Return `Branch` from the actually selected case |
| Logging "selected" inside a guard | False guard still produces a misleading log | Separate guard instrumentation from branch selected |
| Running a second switch for the branch | Guards re-evaluated; two switches can drift | Use `Decision.branch()` once |
| Logging "success" right after case selection | Business work has not committed/completed yet | Separate selection, execution success/failure events |
| Broad `default` for all unknown commands | New subtypes are not reviewed thoroughly | Keep sealed switches exhaustive when appropriate |
| Unguarded case before guarded case of same type | Guarded case is dominated | Specific cases first, fallback later |
| Forgetting to handle null selector | May throw NPE instead of expected event | `case null` or boundary validation |
| Catching all exceptions as "OTHER branch" | Masks guard/accessor/handler errors | Distinguish selection failures from real branches |
| Attaching `traceId` to all metric labels | High cardinality | Use `traceId` in logs/traces, low-cardinality labels in metrics |
| Treating one sink call as exactly-once | Retries/transport can duplicate or drop events | Idempotency, outbox, transaction policy |
| Using a global variable for `currentBranch` | Race conditions across requests | Immutable decision/event and request context |
| Logging exception messages verbatim | May leak PII or system internals | Filtered error code/type, appropriate access control |
| Logging everything at INFO under high traffic | High CPU/I/O/storage cost | Separate mandatory audit from samplable logs |

## 16. Implementation workflow for the command case study

A practical workflow for adding branch auditing to a command system:

1. **List the command hierarchy:** Identify permitted subtypes and business-meaningful `when` conditions.
2. **Define the branch taxonomy:** Choose stable, meaningful branch codes such as `CREATE_BULK` and `REFUND_REJECTED`; never use user data as branch names.
3. **Create a result type:** `Decision(branch, outcome)` or a dedicated domain result with audit metadata, preserving the business return value.
4. **Select the branch exactly once:** Keep `switch`/guards semantically clear; never re-run for logging.
5. **Emit the event after selection:** Record the branch from `Decision` through an adapter; ensure raw commands never enter the schema.
6. **Separate execution outcomes:** If the action has side effects, emit a separate event upon actual success or failure.
7. **Handle failure paths:** Classify selector, guard, accessor, sink, and handler errors; do not collapse everything into "other case".
8. **Test subtypes and guards:** Cover boundary cases, null, audit event counts, and metadata correctness.
9. **Test log safety:** Secrets, CR/LF injection, high-cardinality fields, retention, and access policies.
10. **Integrate observability:** Use managed trace/correlation IDs, clear event schemas, and appropriate metric labels.
11. **Evaluate reliability:** If mandatory audit records cannot be lost, design transactional/outbox mechanisms and check for duplicates.
12. **Review when extending the hierarchy:** Adding a subtype requires updating decision logic, branch IDs, tests, and downstream dashboards/schemas.

The key principle is that **every audit event must describe something that actually happened**. "Pattern selected" is a selection-layer fact; "command completed" is an execution-layer fact.

## 17. Practice exercises

**Exercise 1 — 9/10 bulk threshold:** Add `CreateOrder("O9", 9, ...)` and `CreateOrder("O10", 10, ...)` to the tests. Expect branches `CREATE_STANDARD` and `CREATE_BULK`, with `isBulk` called exactly once per request.

**Exercise 2 — Add a new command:** Create `record RescheduleOrder(String orderId, String slot) implements Command` and update `permits`. Observe `javac` reporting non-exhaustiveness if `select` is missing the case. Add Branch ID `RESCHEDULE_STANDARD` and test the audit event. Do not add `default` just to avoid handling the subtype.

**Exercise 3 — Prove why logging class names is insufficient:** Given two `CreateOrder` instances with quantities 2 and 10, print `getClass().getSimpleName()` in a standalone snippet and compare it with `Decision.branch()`. Explain the difference.

**Exercise 4 — Separate selection and execution:** Write an illustrative `execute` that throws an exception when calling a repository. After `Decision` returns `ACCEPTED`, log `PATTERN_SELECTED` and then log `EXECUTION_FAILED` at the failure boundary. Ensure `EXECUTION_SUCCEEDED` is not logged by mistake.

**Exercise 5 — Guard fails abnormally:** Create a `when` guard calling a method that throws `IllegalArgumentException` in a separate experiment. Prove that no success branch ID is produced and that fallback cases are not tried as if the guard returned false. Design a `SELECTION_FAILED` event to observe the error.

**Exercise 6 — Prevent data leakage:** Intentionally modify `MemoryAuditSink` to print `command.toString()` in a test branch; observe the secret test failing. Restore allowlist-based logging. Test a payload containing newline characters and identify where correlation IDs should be normalized.

**Exercise 7 — Audit reliability:** Suppose the audit sink sends events to a message broker, but the broker times out without responding. Design an idempotency key and retry policy so "one method call" is not mistaken for "exactly-once delivered". Specify when an outbox is needed.

## 18. Conclusion

**To log the selected pattern, let the selected branch itself produce the branch metadata.** In Java 21, sealed command hierarchies and record patterns let `switch` classify commands cleanly. `when` guards determine the specific branch; a `Decision` containing `Branch` lets the outer layer record an audit event **once** without re-running matching logic.

Do not equate **pattern selected** with **business execution succeeded**, do not log raw records containing sensitive data, and do not assume a single logging call means exactly-once delivery. A reliable design separates **selection, decision, execution, and audit delivery**, backed by tests for branch correctness, null handling, guards, secret leakage, and failure paths.

## References

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Java Language Specification SE 21 — `14.11 switch Statements`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11
- Java Language Specification SE 21 — `14.30 Patterns`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- Java Language Specification SE 21 — `15.28 switch Expressions`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- Java SE 21 — java.util.logging: https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/package-summary.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
