# Separating Data Transformation from Sending Notifications, Writing Files, or Updating Systems

## 1. The Problem: Data Transformation and Side Effects Are Two Different Responsibilities

In functional programming with Java, an important design principle is **separating the computation of new values from actions that mutate the outside world**. This is the difference between:

- **Data transformation:** normalizing inputs, validating, filtering, calculating, grouping, sorting, generating reports, or creating an unexecuted update request.
- **Side effects:** sending emails/SMS, writing files, updating databases, calling APIs, writing messages to a broker, mutating global variables, printing to the console, or mutating shared object state.

For example, a list of orders needs its totals calculated and confirmations sent:

```java
// Only compute data, do not send emails yet:
List<Receipt> receipts = orders.stream()
        .map(OrderService::calculateReceipt)
        .toList();

// Perform actions at the I/O boundary:
for (Receipt receipt : receipts) {
    notifier.send(receipt); // Has side effects.
}
```

This is **illustrative code**: `OrderService`, `Receipt`, `orders`, and `notifier` are application-defined types/variables. The key point is that the `calculateReceipt` calculation does not send emails itself; sending happens **after the results to be sent have been produced**.

By contrast, the following approach mixes responsibilities:

```java
// Discouraged: mixing I/O into a mapper:
List<Receipt> receipts = orders.stream()
        .map(order -> {
            Receipt receipt = calculateReceipt(order);
            database.save(receipt);
            mailClient.send(receipt.email());
            return receipt;
        })
        .toList();
```

The snippet above is also illustrative. It causes an operation named as a “data mapping” to silently affect the database and email system. This makes unit testing harder, retries more dangerous, side-effect ordering less clear, and causes problems when switching to `parallelStream()` or reusing the mapper.

**Lesson goal:** design pipelines in the direction of **computation → creating a plan/values → controlled side-effect execution**, while understanding the limits of this separation: it improves code organization and testability, but **does not automatically turn multiple I/O operations into an atomic transaction**.

## 2. What Is a Pure Function and Why Is It Useful?

A function is generally called a **pure function** if:

1. Given the same inputs and the same conditions under which it is defined, the function returns the same result.
2. It has no observable side effects beyond returning its result (no writing files, no calling external systems, no mutating shared state).

Example:

```java
static long lineTotal(int quantity, long unitPriceCents) {
    return Math.multiplyExact(quantity, unitPriceCents);
}
```

`lineTotal(2, 150)` returns `300`. The function does not update a database or mutate passed-in objects. `Math.multiplyExact` may throw `ArithmeticException` if multiplication overflows, but **the ability to throw an exception does not automatically mean a function has side effects**.

Conversely:

```java
static void sendReceipt(Receipt receipt, MailClient mailClient) {
    mailClient.send(receipt.email(), receipt.totalCents());
}
```

This snippet illustrates a method that causes a side effect; the `Receipt` and `MailClient` types are application-defined. The actual outcome depends on the email service, network, permissions, and system state. Calling it again may send another notification.

### Benefits of separation

| Aspect | Pure computation | Side-effect execution |
| --- | --- | --- |
| Ease of testing via input/output | Usually very easy | Requires fakes/mocks, integration tests, or a sandbox |
| Repeating the operation | Usually does not alter the system | May cause duplicate actions |
| Dependency on time/network/files | Should not depend on them | Usually depends on them |
| Parallelizability | Easier when no mutable state is shared | Must consider concurrency, idempotency, ordering |
| Failure handling | Calculation and validation errors | I/O errors, timeouts, partial success |
| Desired output | New object/record/collection | State change or sending information externally |

Separating the two groups of responsibilities helps clarify **which part decides what the data should do**, and **which part is responsible for actually doing it**.

## 3. Three-Stage Design: Prepare, Plan, Execute

A clear way to organize this:

```text
INPUT
   |
   v
[1. Validate and normalize]
   |       data error? -> report clear error
   v
[2. Transform + build immutable plan]
   |       PreparedOrder / Message / ReportRow / Plan
   v
========== SIDE-EFFECT BOUNDARY ==========
   |
   v
[3. Write file / update system / send notification]
   |       I/O error? -> retry, log, compensate, outbox...
   v
Execution status / delivery result
```

**Stage 1 — Validate and normalize.** Convert DTOs, validate quantities/unit prices/emails, and verify required properties. If data is invalid, it should be detected **before** creating hard-to-undo side effects.

**Stage 2 — Build the plan.** Calculate order totals, create report records, determine recipient addresses and message content. The output is **data describing the work**, not the result of a successful send. With Java 17, `record` and `List.copyOf` are very convenient for creating values that are hard to mutate accidentally.

**Stage 3 — Execute.** A separate class/interface controls files, repositories, email, message brokers, or HTTP. This is where transactions, retries, idempotency, timeouts, and error-handling strategies are defined.

The names can be `prepare`/`plan`/`execute`, `calculate`/`persist`/`notify`, or organized as *functional core, imperative shell*. There does not have to be literally three classes; what matters is a **clear boundary of responsibilities**.

## 4. Why Shouldn't `sendEmail` or `writeFile` Be Placed in `map`?

`Stream.map` is designed to transform each element into a new value:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
```

Ideally, a mapper expresses a computation:

```java
List<String> normalized = emails.stream()
        .map(String::trim)
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .toList();
```

Meanwhile:

```java
List<String> risky = emails.stream()
        .map(email -> {
            notificationService.send(email);
            return email;
        })
        .toList();
```

is an illustrative snippet assuming `emails` and `notificationService`, and it mixes the send operation with transformation. There are several risks:

- **Laziness:** creating a pipeline does not run the mapper yet; side effects occur when a terminal operation consumes the data.
- **Short-circuiting:** when using `findFirst`, `limit`, or short-circuiting terminal operations, not every element needs to be visited, so you cannot rely on the mapper to send exactly once for all elements.
- **Optimization:** the Stream API is allowed to optimize certain cases; side effects that are not required by the data operation itself may not happen as you expect.
- **Parallelism:** `parallelStream` can run the mapper on different threads; the send order is no longer the list order.
- **Retries:** re-evaluating the pipeline can unintentionally repeat send/write calls.

**Computations that return data** belong in `map`/`filter`/`reduce`; **I/O execution** belongs at a separate orchestration point, such as a loop or an explicitly invoked service adapter.

### Is `peek` an alternative place to log or send emails?

`peek` is an intermediate operation primarily useful for observation/debugging. It is **not suitable as a mandatory place for auditing, sending emails, or writing to a database**. The number of times the `peek` action is called can depend on how the stream is consumed and on pipeline optimizations.

For example:

```java
long count = List.of("A", "B", "C").stream()
        .peek(System.out::println)
        .count();
```

You cannot assert that the three lines A, B, C **must** be printed in every implementation: with a sized source, `count()` can obtain the count without executing the intermediate pipeline. This is why `peek` is not a reliable notification mechanism.

## 5. Complete Java 17 Example: Planning Orders Then Executing

The following example intentionally **separates two parts**:

1. Pure computation part: from `Order`, compute `PreparedOrder` and CSV rows.
2. I/O part: write a real CSV file to a temporary file; simulate system updates and sending notifications using a test executor with an event log.

The program simulates an email-sending failure on order A02, showing that **side effects before the failure still persist**. It then runs again to illustrate a duplicate-avoidance mechanism within the scope of the demo process. This is not a real email/database implementation.

Create the file **`SeparateEffectsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

public class SeparateEffectsDemo {
    record Line(String sku, int quantity, int unitCents) {}

    record Order(String id, String email, List<Line> lines) {
        Order {
            lines = List.copyOf(lines);
        }
    }

    record PreparedOrder(String id, String email, long totalCents) {}

    record Plan(List<PreparedOrder> items, List<String> csvLines) {
        Plan {
            items = List.copyOf(items);
            csvLines = List.copyOf(csvLines);
        }
    }

    // Pure: validate data and calculate total. No I/O writes.
    static PreparedOrder prepare(Order order) {
        long total = order.lines().stream()
                .mapToLong(line -> {
                    if (line.quantity() <= 0 || line.unitCents() < 0) {
                        throw new IllegalArgumentException("invalid line");
                    }
                    return Math.multiplyExact(
                            (long) line.quantity(), line.unitCents());
                })
                .reduce(0L, Math::addExact);

        return new PreparedOrder(order.id(), order.email(), total);
    }

    // Pure: build a plan from data, without sending/writing anything.
    static Plan buildPlan(List<Order> orders) {
        List<PreparedOrder> prepared = orders.stream()
                .map(SeparateEffectsDemo::prepare)
                .toList();

        List<String> csv = Stream.concat(
                Stream.of("orderId,totalCents"),
                prepared.stream()
                        .map(p -> p.id() + "," + p.totalCents()))
                .toList();

        return new Plan(prepared, csv);
    }

    // Side-effect executor class for demonstration only.
    static final class DemoEffects {
        private final Path report;
        private final List<String> events = new ArrayList<>();
        private final Set<String> updated = new HashSet<>();
        private final Set<String> mailed = new HashSet<>();
        boolean failMailA02 = true;

        DemoEffects(Path report) {
            this.report = report;
        }

        void writeReport(Plan plan) throws IOException {
            Files.writeString(
                    report,
                    String.join("\n", plan.csvLines()) + "\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);
            events.add("FILE written");
        }

        void updateSystem(PreparedOrder item) {
            // Fake repository: does not call a real database.
            if (updated.add(item.id())) {
                events.add("DB " + item.id());
            } else {
                events.add("DB skip " + item.id());
            }
        }

        void sendNotification(PreparedOrder item) {
            // Fake mail service: simulates a failure at A02.
            if (item.id().equals("A02") && failMailA02) {
                events.add("MAIL failed A02");
                throw new IllegalStateException("mail offline");
            }
            if (mailed.add(item.id())) {
                events.add("MAIL " + item.id());
            } else {
                events.add("MAIL skip " + item.id());
            }
        }

        void execute(Plan plan) throws IOException {
            writeReport(plan);
            for (PreparedOrder item : plan.items()) {
                updateSystem(item);
                sendNotification(item);
            }
        }

        List<String> events() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args) throws IOException {
        List<Order> orders = List.of(
                new Order("A01", "lan@example.test", List.of(
                        new Line("BOOK", 2, 150),
                        new Line("PEN", 1, 50))),
                new Order("A02", "minh@example.test", List.of(
                        new Line("BAG", 1, 800)))
        );

        Plan plan = buildPlan(orders);
        List<String> totals = plan.items().stream()
                .map(p -> p.id() + "=" + p.totalCents())
                .toList();

        System.out.println("Prepared: " + totals);
        System.out.println("CSV rows planned: " + plan.csvLines().size());

        // Temporary file is only created at the side-effect boundary.
        Path report = Files.createTempFile("orders-demo-", ".csv");
        try {
            DemoEffects effects = new DemoEffects(report);
            System.out.println("Before execute: " + effects.events());

            try {
                effects.execute(plan);
            } catch (IllegalStateException ex) {
                System.out.println("First error: " + ex.getMessage());
            }

            System.out.println("Events after failure: " + effects.events());
            System.out.println("File rows: "
                    + Files.readAllLines(report, StandardCharsets.UTF_8));

            // Restore simulated mail and re-execute the plan.
            effects.failMailA02 = false;
            effects.execute(plan);
            System.out.println("Events after retry: " + effects.events());
        } finally {
            Files.deleteIfExists(report);
        }
    }
}
```

Compile and run with **JDK 17 or higher**:

```bash
javac --release 17 SeparateEffectsDemo.java
java SeparateEffectsDemo
```

**Expected stdout:**

```text
Prepared: [A01=350, A02=800]
CSV rows planned: 3
Before execute: []
First error: mail offline
Events after failure: [FILE written, DB A01, MAIL A01, DB A02, MAIL failed A02]
File rows: [orderId,totalCents, A01,350, A02,800]
Events after retry: [FILE written, DB A01, MAIL A01, DB A02, MAIL failed A02, FILE written, DB skip A01, MAIL skip A01, DB skip A02, MAIL A02]
```

### Detailed Explanation of the Example

**Computation step.** `prepare` iterates over `Line` items and computes `quantity * unitCents` using `Math.multiplyExact`, then sums them with `Math.addExact`. A01 has 2 × 150 + 1 × 50 = **350** cents; A02 has 1 × 800 = **800** cents. If there is a non-positive quantity or negative unit price, `IllegalArgumentException` is thrown before a plan is successfully created. Validation only makes sense when corresponding business rules exist; this example accepts unit price 0 to illustrate a free item.

**Planning step.** `buildPlan` creates two `PreparedOrder` records and three CSV lines including a header line. Both `Order` and `Plan` copy their lists in the constructor, so the list structure cannot be modified through external references. This is a **data** plan, without calling any repository or mail service yet.

**File-writing step.** `DemoEffects.execute` calls `writeReport`. `Files.writeString` writes UTF-8 to the existing temporary file and replaces the old content with the CSV lines, using a fixed `\n` newline. `Files.readAllLines` near the end proves the real file was written; the temporary file name is not printed so stdout is independent of the machine's path. The `finally` block deletes the temporary file after the demo.

**Update and notification steps.** `updateSystem` and `sendNotification` only **simulate** a database and mail service using in-memory `Set`/`List` structures. They do not access real systems. After A01 succeeds, A02 is marked as updated in the DB, but the simulated mail fails, so the sequence stops. The log proves that side effects that already occurred do not roll back automatically.

**Retry avoids duplicates in the demo.** When mail delivery for A02 is re-enabled and `execute` runs again, writing the file repeats with the same content; the `Set` collections storing already-updated or already-mailed IDs skip the second attempt for parts that already succeeded. Therefore, A01 is not “sent again” in the log, while A02 is sent for the first time after the failure.

**Simulation limits:** the `Set` collections only exist within a single Java instance and **are not sufficient to guarantee idempotency in a real system**. If the application restarts, has multiple instances, or a send request succeeds but the client times out before receiving the response, durable mechanisms are needed such as idempotency keys, unique constraints, an outbox, delivery state tracking, and deduplication per the service contract.

The program does not rely on `HashSet` iteration order; event order is recorded sequentially in an `ArrayList`, and output always iterates over the input `List.of`. The CSV file only contains order IDs and integer cent totals, so complex quoting is unnecessary. In applications with commas, newlines, quotes in CSV fields, or untrusted IDs, proper escaping or a standard CSV library should be used.

## 6. Why Must Writing Files, Sending Emails, or Updating DB Have a Clear “Entry Point”?

An explicit orchestration method is clearer:

```java
Plan plan = buildPlan(orders);
effects.execute(plan);
```

It helps distinguish:

- `buildPlan` can run in unit tests without a file system, database, or email.
- `execute` can be tested separately with fake effects or integration tests.
- Readers know exactly **when side effects begin**.
- Access-control checks, retries, transactions, and auditing are centralized in the I/O layer.
- A *preview* or *dry run* can be displayed from the Plan before actual execution.

If you write `map(order -> { mail.send(...); db.save(...); return ...; })`, readers have to inspect every mapper carefully to know where I/O happens. This makes it difficult to assess whether a pipeline is safe to run in parallel, stop early, or rerun.

### The “functional core, imperative shell” model

This is a common name for this separation:

```text
+---------------------------------------------------+
| FUNCTIONAL CORE                                    |
| validate -> normalize -> calculate -> build Plan  |
| returns new values, touches no DB/email/files      |
+---------------------------------------------------+
                      |
                      v
+---------------------------------------------------+
| IMPERATIVE SHELL                                   |
| load inputs -> call core -> persist -> notify     |
| handles I/O, transactions, retries, monitoring, timeouts |
+---------------------------------------------------+
```

You don't need to think of the core as a different framework. It can just be a few `static` methods, records, and plain Java services. The goal is to **reduce the number of places in the program that can mutate the system**.

## 7. Do Not Confuse List Immutability with Pipeline Purity

`Stream.toList()` on Java 16+ returns a structurally unmodifiable list. However, returning an unmodifiable list **does not turn a mapper with side effects into a pure function**:

```java
List<Receipt> result = orders.stream()
        .map(order -> {
            notification.send(order);
            return calculateReceipt(order);
        })
        .toList();
```

This illustrative code still sends notifications inside `map`, regardless of whether the resulting list can be modified.

Conversely, a mutable list created **locally inside a function** and then returned as an unmodifiable copy can be a pure implementation, as long as the computation does not mutate external state. “Mutate nothing at all” is not the sole condition; what matters is **having no observable side effects beyond the return value**, and keeping inputs unchanged.

### `record` and `List.copyOf` only protect partially

`record` helps express data by value and has `final` fields, but a record holding a reference to a mutable object can still observe changes to that object. `List.copyOf` copies the **list structure** and forbids structural modification, but does not automatically deep-copy every element.

In the complete example, `Order` contains `Line` records with only `String`/`int`, and `PreparedOrder` is also a record with `String`/`long`; with such data, the design achieves better practical immutability. If any field is a mutable `Date`, `ArrayList`, or other mutable object, defensive copying and an ownership policy must be added.

## 8. Should `forEach` Be Used to Send Notifications?

`forEach` is a terminal operation that accepts a `Consumer`:

```java
plan.items().stream()
        .forEach(item -> notifier.send(item));
```

This is illustrative code. It **can be appropriate** when the side-effect boundary is already clear and you deliberately want to invoke an action on each item. But you must understand:

- `Stream.forEach` is terminal and returns no result data.
- If `parallelStream().forEach` is used, send order is not guaranteed and actions may run concurrently.
- If an action throws an exception, the pipeline propagates the error; in a parallel pipeline, other actions may have already run.
- `forEach` does not provide transactions, retries, idempotency, or timeout management.
- If you need to stop immediately when a step fails, make it explicit that the program is running **sequentially**.

The `for` loop in `DemoEffects.execute` is appropriate because readers clearly see the business order `write report → update A01 → send A01 → update A02 → send A02`. There is no mandatory rule to replace every loop with a Stream. **Functional programming does not mean forbidding `for` or `try/catch`.**

### Does `forEachOrdered` solve all ordering issues?

`forEachOrdered` guarantees actions run in encounter order if the source is ordered, even on a parallel stream, but **does not turn external operations into a transaction**, does not prevent duplicate sends on its own, and does not force all upstream computations to run sequentially. If multiple business events depend on each other, a simple sequential loop can be easier to audit.

## 9. Avoid Using `peek` for Mandatory Auditing

A counterexample:

```java
long total = orders.stream()
        .peek(order -> audit.log("Processing " + order.id()))
        .mapToLong(Order::amount)
        .sum();
```

This illustrative snippet assumes `orders`, `audit`, and `Order::amount`. `peek` is often convenient for debugging, but it is not the right place for mandatory auditing. Laziness, short-circuiting, pipeline optimizations, and parallel processing make the assumption “one record produces one side effect” unreliable when auditing is a business requirement.

If auditing is an important requirement, give it a **dedicated action in the shell**, paired with a transaction or a reliable event-recording mechanism depending on the system. For example, create `AuditEvent` as **data** in the Plan, and then let the I/O layer record it according to contract.

## 10. Separating Notification Data from the Send Operation as Well

A way to extend the plan:

```java
record EmailCommand(String id, String address, String subject, String body) {}

List<EmailCommand> messages = prepared.stream()
        .map(item -> new EmailCommand(
                item.id(),
                item.email(),
                "Receipt " + item.id(),
                "Total: " + item.totalCents() + " cents"))
        .toList();
```

`prepared` is an illustrative `List<PreparedOrder>`. This is a transformation that produces **send commands as data**, not already-sent commands. The orchestration layer can write commands to an outbox, send them via a notifier, apply retry policies, or choose another channel.

There are two states that must be distinguished:

- `EmailCommand` has been **created in memory**.
- The email has been **accepted or successfully sent by the external system** per the provider's contract.

They are not equivalent. A successfully created plan does not mean the email reached the inbox; even an HTTP 200 from a mail service does not necessarily mean the recipient read the message.

### Benefits of “data as commands”

When “which email needs to be sent” is represented as an object:

1. You can preview/dry-run without actually sending.
2. You can unit test the subject, address, and body from inputs.
3. You can store them in an outbox in a structured way.
4. You can detect duplicates by business key before calling the service.
5. You can attach retry metadata without re-running the entire computation step.

However, these command objects often contain personal information; logging, storage, and transmission must comply with the application's access controls, privacy policies, and auditability requirements.

## 11. Handling Computation Errors Differently from I/O Execution Errors

### Errors in the preparation step

For example, negative quantities or overflow:

```java
static long total(int quantity, int cents) {
    if (quantity <= 0 || cents < 0) {
        throw new IllegalArgumentException("invalid input");
    }
    return Math.multiplyExact((long) quantity, cents);
}
```

Errors can be detected before writing files, updating systems, or sending notifications. For invalid inputs, return a clear validation error. If you need to validate **all** records to return a list of errors, you can represent errors as a Result instead of failing fast on the first record.

### Errors in the execution step

`Files.writeString` can throw a checked `IOException`. Email/APIs can often fail with timeouts or unsuccessful status codes. Database writes can fail with constraint/connection/transaction errors.

An execution method should declare or translate exceptions according to a meaningful contract, for example:

```java
void execute(Plan plan) throws IOException {
    writeReport(plan);
    for (PreparedOrder item : plan.items()) {
        updateSystem(item);
        sendNotification(item);
    }
}
```

This illustrative snippet matches the types in the complete program. If `writeReport` throws `IOException`, the update/mail steps have not been called in that execution. However, the file-write operation itself **may have already written partially** before throwing; do not assume every I/O failure happens before any side effect occurs. If an update/mail step fails, earlier steps may also remain in effect.

### Do not “swallow” errors just to keep the pipeline going

```java
// Do not swallow all errors unconditionally:
try {
    mail.send(message);
} catch (RuntimeException ex) {
    // ignore
}
```

This is illustrative code. Ignoring an error might be reasonable for an auxiliary *best-effort* log in a well-defined context, but it is very dangerous if business requirements treat sending/updating as mandatory. Clearly define which cases may be ignored, which must be retried, and which must report failure.

## 12. Partial Failure: Separating Responsibilities Does Not Guarantee Atomicity

Suppose you need three side effects:

```text
1. Update order status in the database
2. Write report to a file
3. Send confirmation email
```

These steps often live in **three different systems**. A database transaction does not automatically roll back an email that was already sent or a file that was already written.

| Failing step | What may have already happened |
| --- | --- |
| Before DB update | No update yet, but preparation has already run |
| During DB update | May roll back or leave partial results depending on transaction |
| After DB update, before file write | DB is changed, file/email not executed yet |
| During file write | File may be partially written, DB may already be changed |
| After file write, when sending email | DB/file exist, email may or may not have succeeded |
| Email succeeded but response lost | Unclear whether caller observed success |

To get strong guarantees, you must additionally design **transactions, outbox, saga/compensation, or idempotency**, depending on the architecture. Do not assume that merely using `Stream.toList()` or “pure functions” solves distributed systems problems.

### Transaction within one system vs. multiple systems

A database transaction can ensure that operations **within that transaction's scope** commit or roll back together. External file systems and email APIs **do not automatically participate** in that transaction. Therefore, putting `mailClient.send` inside a `@Transactional` service method does not make the email roll back when the database rolls back.

When you need to emit events reliably after a DB update, **transactional outbox** is a common pattern:

1. In the same DB transaction, update business data and insert an outbox record.
2. Commit the transaction.
3. Another worker reads the outbox, sends the message to the broker/email, and records the processed state.
4. Use idempotency/deduplication to limit the harm of redelivery.

An outbox avoids the case where the DB commits and the process dies before recording the intent to send, but **does not automatically make delivery truly exactly-once across all systems**. You must understand the broker/consumer contract and design for duplicate handling.

## 13. Idempotency: Why Is It Especially Important During Retries?

An action is **idempotent** in a practical sense if repeating the same request multiple times produces the **same business state outcome** as doing it once, given the same identifying key and contract conditions. For example, setting an order's status to “CONFIRMED” is usually easier to make idempotent than “increment confirmation count by 1”.

The risk of retries:

```java
for (Order order : orders) {
    chargePayment(order);
    sendEmail(order);
}
```

This is illustrative code without defining `chargePayment` and `sendEmail`. If payment was charged but sending the email failed, re-running the whole loop could **charge the payment twice**. Separating computation into a Plan makes the steps needing retry clear, but the I/O layer still needs an idempotency policy.

Some techniques:

- Assign a stable **idempotency key** for each business action (`orderId + operationType + version`), rather than generating a new random key on every retry.
- Use **unique constraints** or durable transaction states to reject duplicate updates.
- Persist **pending/sent/failed** states in a controlled way to know which steps can continue.
- For external systems, use idempotency APIs if supported by the provider.
- For file reports, consider writing to a temporary file followed by an **atomic move** if the file system supports it and atomic publishing is required; check errors/paths and rerun behavior.

In `SeparateEffectsDemo`, the two `Set` collections only demonstrate the idea “if already done, skip next time” within **a single run**, and do not replace durable storage and concurrency handling in a real system.

## 14. Writing Files: CSV Data First, I/O Operation Later

Generating report content can be a pure transformation:

```java
List<String> rows = prepared.stream()
        .map(p -> p.id() + "," + p.totalCents())
        .toList();
```

But writing those lines to a file is a side effect:

```java
Files.writeString(
        path,
        String.join("\n", rows) + "\n",
        StandardCharsets.UTF_8);
```

These snippets are illustrative and require declaring `prepared`, `path`, and appropriate imports. Thanks to separation:

- You can unit test CSV formatting without touching the file system.
- You can inspect a preview and validate data before writing.
- You can swap CSV for JSON without changing the file-writing layer.
- You can choose overwrite, append, or rename policies in the I/O layer.
- You can test permission errors, out-of-disk errors, or missing directories in integration tests.

**Avoid writing to a file inside `Stream.map` and returning the element**: that makes the pipeline hard to test, introduces resource risks, and makes partial writes hard to control. If you need streaming performance for very large files that cannot fit in RAM, you can still separate the “record-formatting function” from the “writing function”, then use a processing loop with explicit `BufferedWriter`/`try-with-resources` management. Separating responsibilities **does not force materializing all data into a giant List**.

### Large files: the pure boundary still exists during streaming

```java
try (BufferedWriter writer = Files.newBufferedWriter(path, UTF_8)) {
    for (Order order : orders) {
        PreparedOrder prepared = prepare(order); // Compute data.
        writer.write(renderCsv(prepared));        // I/O.
        writer.newLine();
    }
}
```

This is a **partial example** requiring `orders`, `prepare`, `renderCsv`, `path`, and imports, not a standalone program. Even though the loop processes line by line, the two responsibilities remain two separate methods. Error handling and file atomicity must be defined separately.

## 15. Sending Notifications: Prepare the Message Before Dispatching

Do not mix message formatting with transport:

```java
// Do not combine message creation and transport in a mapper:
orders.stream().map(order -> {
    String body = formatReceipt(order);
    mailClient.send(order.email(), body);
    return body;
});
```

This snippet also **has no terminal operation**: it only builds a pipeline, so the send action may not happen at all. That easily creates bugs because readers mistake it for having sent.

How to separate:

```java
List<EmailCommand> commands = orders.stream()
        .map(this::buildEmailCommand)
        .toList();

for (EmailCommand command : commands) {
    mailClient.send(command);
}
```

Both snippets are illustrative code with application-defined types/variables. The first step decides *what to send and to whom*; the second step decides *how to send it, how to retry, or how to report errors*. Separation also allows swapping the mail service without touching billing rules.

## 16. Updating Systems: Create Update Intent and Apply Separately

For example, from newly computed statuses:

```java
record UpdateCommand(String orderId, String newStatus) {}

List<UpdateCommand> updates = orders.stream()
        .filter(this::eligibleForConfirmation)
        .map(order -> new UpdateCommand(order.id(), "CONFIRMED"))
        .toList();
```

`eligibleForConfirmation` and `Order` are illustrative domain code. `updates` is just **data**, not yet a DB update.

Side-effect step:

```java
for (UpdateCommand update : updates) {
    repository.apply(update);
}
```

The repository layer is responsible for transactions, optimistic locking, unique constraints, auditing, and connection errors. If multiple updates must commit together, consider a batch transaction **within a clear DB boundary**, rather than hoping a loop is atomic by default.

If the status calculation itself depends on data changing concurrently in the database, you cannot assume the Plan computed upfront is still valid at execution time. You may need **versions**, **compare-and-set**, optimistic locking, or a transaction that re-checks conditions before committing.

## 17. Testing: Split into Pure Unit Tests and Integration Tests for I/O

### Testing transformation functions

`prepare` and `buildPlan` can be tested by comparing data:

```java
Plan plan = buildPlan(input);

assertEquals(2, plan.items().size());
assertEquals(350L, plan.items().get(0).totalCents());
assertEquals("orderId,totalCents", plan.csvLines().get(0));
```

This is **illustrative test code**; `assertEquals` requires JUnit or an equivalent assertion library, and `input` requires test data and the types from the program. Pure tests do not need email/database/file mocks.

### Testing the execution layer with a fake

Replace a real email service with a fake that records calls:

```java
interface Notifier {
    void send(String address, String body);
}

final class RecordingNotifier implements Notifier {
    final List<String> sent = new ArrayList<>();
    @Override
    public void send(String address, String body) {
        sent.add(address + ":" + body);
    }
}
```

This is a **type definition** snippet in a test or appropriate Java file, requiring `List`/`ArrayList` imports. The execution layer calls `Notifier` via dependency injection or constructor. Unit tests can verify “sent to the right person, once in the given scenario” without sending real emails.

### Integration tests

For the I/O layer, you should also test:

- Files are created at allowed paths, content has the right encoding/format, resources are closed, and overwrite/append policies behave properly.
- DB commits/rollbacks as required, along with optimistic locking and unique constraint cases.
- Email/broker returns timeout or 429/5xx errors, retry/backoff behavior, and retry limits.
- What happens if the process stops **after DB commit but before sending**.
- Idempotency when a request is resent or two workers execute concurrently.
- Sensitive information handling: customer data is not logged indiscriminately.

Routine tests should not send real emails or update production databases.

## 18. Reading the Roles of `Function` and `Consumer` Correctly

`Function<T,R>` represents an operation taking T and returning R; `Consumer<T>` takes T and returns `void`. This suggests:

```java
Function<Order, PreparedOrder> transform =
        SeparateEffectsDemo::prepare;

Consumer<PreparedOrder> deliver =
        item -> notifier.send(item);
```

This is illustrative code with `notifier` in scope. `transform` is suited to express computation, and `deliver` usually expresses a side effect. However:

**Just because a lambda has type `Function` does not mean it is pure.** You can still write a Function that mutates a shared variable or sends an email and returns a result. Conversely, a `Consumer` might have no observable side effects (e.g., an empty body). Purity is a property of **actual behavior**, not guaranteed by interface names.

### `andThen` and side-effect ordering

`Consumer.andThen` chains two actions:

```java
Consumer<PreparedOrder> save = repository::save;
Consumer<PreparedOrder> notify = notifier::send;

Consumer<PreparedOrder> workflow = save.andThen(notify);
```

This snippet assumes `repository`/`notifier` with matching signatures. If `save.accept` throws an exception, `notify.accept` does not run. If `save` succeeds and `notify` throws, the earlier save **does not roll back automatically**. `andThen` is convenient for ordering operations, but does not replace an orchestration layer with transactions/idempotency/compensation.

## 19. Parallel Streams and Unsafe Actions

A transformation pipeline with no shared state is usually easier to run in parallel:

```java
List<PreparedOrder> prepared = orders.parallelStream()
        .map(SeparateEffectsDemo::prepare)
        .toList();
```

With an ordered source like `List`, `toList()` preserves encounter order. However, Java does not guarantee the mapper runs in that order or on the same thread. Because `prepare` does not update shared state, the risk of race conditions is reduced.

Conversely:

```java
orders.parallelStream()
        .forEach(order -> mailClient.send(order.email()));
```

is a parallel I/O operation that can happen concurrently with no guaranteed send order. Beyond thread safety of the mail client, you must consider rate limits, connection limits, retries, idempotency, and processing time. **Do not default to parallel streams for I/O**; consider dedicated executors, queues, batch workers, or asynchronous APIs designed with backpressure and monitoring.

If a fixed transactional order is needed, use an explicit orchestration layer; `forEachOrdered` only constrains action execution to encounter order and does not turn external effects into a shared transaction.

## 20. Situations Requiring Design Decisions

| Situation | Design to consider |
| --- | --- |
| Only filtering, normalizing customer names | Pure `map`/`filter` and `toList` |
| Generating CSV without writing a file yet | Return report rows/records as data |
| Writing large files line by line | Pure render function + I/O loop with `try-with-resources` |
| Computing email content | Return `EmailCommand`, do not send in mapper |
| Email must be sent after DB commit | DB transaction + appropriate outbox/dispatcher |
| Updating DB and calling REST API | Orchestrate side effects, timeouts, idempotency, error handling |
| Need to preview changes | Compute `Plan` then display preview/dry-run |
| One data record is invalid | Validate before side effects or use Result containing errors |
| Send fails partway through | Persist state, selective retry, do not blindly re-invoke committed actions |
| Multiple workers processing concurrently | Idempotency keys, concurrency control, and load limits |

The specific choice also depends on consistency requirements, data volume, source/destination types, and tolerance for duplicate sends.

## 21. Common Mistakes

**Mistake 1 — Sending notifications inside `map` or `filter`.** The data pipeline becomes coupled to I/O; changing the terminal operation or parallelizing can change behavior. Create commands/plans first and send at a separate boundary.

**Mistake 2 — Using `peek` for mandatory auditing.** `peek` has no contract to run for every element if the terminal operation does not require it. Auditing must use an appropriately guaranteed mechanism.

**Mistake 3 — Thinking `toList` running the pipeline means “orders are saved”.** `toList` collects **values in memory**; it does not write to a DB or send emails.

**Mistake 4 — Thinking separating pure functions gives automatic rollback.** Separation improves testability, but already-executed side effects can still persist when a later step fails.

**Mistake 5 — Retrying the whole plan without idempotency.** This can cause duplicate sends, double charges, or duplicate file appends.

**Mistake 6 — Creating a plan and implicitly assuming conditions remain unchanged until commit.** External data can change; use versions/transactions/validation at execution time if needed.

**Mistake 7 — Using a shared `ArrayList` to collect from `parallelStream().forEach`.** This risks race conditions; use a collector or `toList` for data results.

**Mistake 8 — Hiding I/O errors inside a lambda with `catch (Exception ignored)`.** Callers won't know a failure occurred, causing inconsistent state. Define clear error contracts.

**Mistake 9 — Assuming a record or unmodifiable list makes the entire object graph immutable.** Nested mutable objects can still change; consider defensive copying and ownership.

**Mistake 10 — Putting real files/emails/databases into computation unit tests.** Tests become slow, flaky, and risk altering external data. Use fakes for orchestration and separate integration tests.

**Mistake 11 — Relying on a database transaction to roll back emails too.** Transactions do not automatically extend to external systems; use outbox/compensation when needed.

**Mistake 12 — Treating a successful mail API call as proof the recipient read it.** Distinguish delivery confirmation levels per the service contract.

**Mistake 13 — Parallelizing I/O without accounting for load limits.** This can exceed rate limits, exhaust connections, or build up large retry queues; design concurrency and backpressure explicitly.

**Mistake 14 — Collecting millions of objects just to write a large file sequentially.** You don't have to materialize the entire dataset: separating a pure mapper from a resource-managed writer still supports line-by-line processing.

## 22. Practice Exercises

1. Write a `static String normalizeEmail(String email)` function that only trims/lowercases using `Locale.ROOT`. Explain why it can be tested without a mail service.
2. From `List<Order>`, create `List<PreparedOrder>` using `map`, compute totals with `Math.addExact`, and write to no systems. Verify the output with orders A01/A02 from `SeparateEffectsDemo`.
3. Design `record EmailCommand(String orderId,String email,String body)`. Use `map` to create a list of commands and write a dispatch loop in a separate layer.
4. Refactor `orders.stream().map(order -> { repository.save(order); return order.id(); }).toList()` into two parts: purely computing IDs and saving via a separate service. State the benefits and execution-order risks.
5. Using a fake `Notifier` that records calls, test that A01 has exactly one send request in a successful scenario.
6. Simulate A02 failing to send after A01 has been updated. Record the remaining state and explain why all steps must not be re-invoked unconditionally.
7. Add a `ReportRow` record and a pure `toCsvRow(PreparedOrder)` function. Write a unit test verifying the string has the right ID and total without touching the filesystem.
8. Write a report to a temporary file using `try/finally` or `try-with-resources`, read it back, and delete it after the test. Test the case where the file cannot be written and the error policy.
9. Design an `UpdateCommand(orderId,status,version)` to check optimistic locking in the repository layer. Why isn't validation when building the Plan enough?
10. Compare running `orders.parallelStream().map(this::prepare).toList()` with `orders.parallelStream().forEach(mailClient::send)`. Which pipeline is usually easier to keep thread-safe and why?
11. Create a pipeline that only uses `peek` to log an audit and then calls `count()`. Explain why the audit might not be emitted as expected.
12. Sketch a transactional outbox: in one transaction, update the order and write an `OutboxEvent`; another worker sends the email. Describe how to prevent duplicate sends if the worker crashes after sending.
13. For data too large to fit entirely in RAM, design how to use a pure `renderCsv` function together with `BufferedWriter` in the I/O layer.
14. List all side effects of an invoice-sending feature: email, file, DB, metrics, logs, message broker; identify which actions are mandatory, which are best effort, and their required order.

## 23. Pre-Production Checklist

- Are **values to produce** clearly distinguished from **actions to execute**?
- Does any mapper or predicate secretly call files, databases, emails, HTTP APIs, or mutate external state?
- Is input data sufficiently validated before hard-to-undo side effects?
- Can the computation part be unit tested purely via input/output?
- Is there a `Plan`, `EmailCommand`, `UpdateCommand`, or equivalent structure to preview before sending?
- Are the starting point and order of side effects clearly defined in the shell?
- When an error occurs mid-sequence, which steps have already taken effect and which can be retried?
- For multi-system DB/file/email flows, is **partial failure** handled rather than implicitly assuming a single shared transaction?
- Do repeatable operations have idempotency keys and appropriate durable storage?
- If parallelism is used, do mappers avoid shared mutable state and does the I/O layer limit concurrency?
- Are I/O resources properly closed, and do files have appropriate overwrite/append and synchronization policies?
- Are **computation tests**, **orchestration tests with fakes**, and **external-system integration tests** clearly separated?

**Conclusion:** Use `map`/`filter`/`reduce` to **compute data and build plans**, then use an orchestration layer with clear naming, error contracts, and responsibilities to **write files, send notifications, or update systems**. This separation keeps most business logic easy to understand, test, and reuse, while exposing real-world I/O concerns — idempotency, transactions, concurrency, and partial failure — in the exact place where they need to be solved.
