# Completing an Integration Example with Failure Scenario Testing — Java Core Exception

## 1. Comprehensive Practice: From Exceptions to Business Contracts

A Java program can compile and run correctly on the happy path yet still fail severely when a dependency errors, a resource fails to close, a task is canceled, or data is only partially written. Therefore, when completing an integration example, you should not stop at catching an `Exception`. You need to verify **the error type, cause, resource boundaries, side effects, and the actual state received by the caller**.

This lesson builds a minimal order-creation workflow in Java 17+:

1. Receive a request containing a product ID and quantity.
2. Validate the input **before accessing any dependency**.
3. Open a session to the data store via `AutoCloseable`.
4. Read the unit price; distinguish between not found, invalid source data, and I/O failures.
5. Create a receipt with the total amount and save it to the store.
6. Send a notification after saving.
7. Close the session whether the operation succeeds or fails.
8. Observe the result when the task is executed via `ExecutorService`.
9. Test cancellation and exceptions that may occur asynchronously.

Dependencies are replaced with **in-memory fakes**, without using a real database, network, or secrets. The test suite still covers multiple adverse scenarios to verify **contracts at each boundary**. This is a self-contained program runnable with `javac`/`java`; afterward, we compare it with how JUnit 5 tests are structured in a project.

**Expected outcome:** the happy path returns the correct receipt; each failure type has a distinct code; the I/O origin remains in `getCause()`; `try-with-resources` preserves close errors; cancellation is not turned into success; and notably, an operation already saved before the notifier fails **must not be assumed unsaved**.

## 2. Scope and Contracts of the Example

To keep the exercise repeatable and independent of external environments, we use three groups:

| Component | Responsibility | State/Error Type |
| --- | --- | --- |
| `OrderService` | Validation, coordinating read–calculate–save–notify, error translation | `DomainFailure` with `Code` |
| `FakeStore` and `Session` | Open session, read unit price, save receipt, close session | `IOException` in simulated failure modes |
| `FakeNotifier` | Send notification after the receipt has been saved | `IOException` in the notify-fail scenario |
| `scenario(...)` | Run each case, assert code, close count, and persisted state | Throws `AssertionError` on mismatch |
| `asyncFailure()` | Call the workflow via `submit()`, verify `ExecutionException.getCause()` | Cause is `DomainFailure` |
| `asyncCancellation()` | Run an interruptible waiting task and call `cancel(true)` | `CancellationException` when reading Future |

The exercise includes several **intentional assumptions**:

- `Session.save` sets `persisted=true` **before** the notifier is called. The fake has no transactions or rollback.
- The success unit price is `25` and the demo quantity is `2`, so the expected total is `50`.
- `NOTIFY_FAIL` occurs after a successful save: this is a **failure with side effects**, not an error meaning "not executed".
- `CLOSE_FAIL` occurs when `close()` throws after all other operations have completed. A close error does not automatically undo the `persisted` state.
- `READ_AND_CLOSE_FAIL` causes both the read and close operations to fail, to test primary/suppressed exceptions.
- Each `scenario` creates a fresh fake; tests do not share mutated state across cases.
- The cancellation task at the end only awaits a latch without writing business data, to illustrate interruption without causing indeterminate side effects.

Do not treat this fake as a production data store implementation. In particular, a real DB has transactions, commit/rollback, and connection pools; a real notifier might succeed in sending but lose the ACK. Later sections highlight additional aspects that must be tested when replacing fakes with real dependencies.

## 3. Happy Path and Failure Path Diagram

```text
Request(id, quantity)
        |
        v
Validate request
        | invalid ------------------> INVALID_REQUEST (session not opened yet)
        v
Store.open() -> Session
        |
        v
Session.read(id)
        | IOException -------------> DEPENDENCY_UNAVAILABLE
        | null --------------------> NOT_FOUND
        | unitPrice <= 0 ----------> INVALID_DATA
        v
Calculate Receipt(total)
        |
        v
Session.save(receipt)
        | IOException -------------> DEPENDENCY_UNAVAILABLE
        v
persisted = true
        |
        v
Notifier.send(receipt)
        | IOException -------------> NOTIFICATION_FAILED
        |                            persisted may still be true
        v
Return receipt
        |
        v
Session.close()                 (always attempted after successful open)
        | IOException -------------> CLOSE_FAILED if no prior error
        | prior error exists ------> close error may be suppressed
        v
Caller receives receipt / DomainFailure
```

Note that `Session.close()` runs when exiting the `try-with-resources` block, **before the method finishes returning**. Therefore, code with a `return receipt` statement inside the `try` body can still **fail to return the receipt to the caller** if `close()` throws. This is why `CLOSE_FAIL` still reports an error even though the receipt was already saved and the notification was sent in the fake.

Similarly, an error while reading data can be the primary exception while `close()` produces a secondary error. If you only inspect the close error message while ignoring `getSuppressed()` or only assert a single error code, the test may misidentify the root cause.

## 4. Choosing Meaningful Error Types and Error Codes

The example uses an enum:

```java
enum Code {
    INVALID_REQUEST, NOT_FOUND, INVALID_DATA,
    DEPENDENCY_UNAVAILABLE, NOTIFICATION_FAILED, CLOSE_FAILED
}
```

This is a snippet from the full program shown later.

| Code | Condition | Meaning |
| --- | --- | --- |
| `INVALID_REQUEST` | Blank/null product ID, non-positive quantity | Caller provided invalid input; repository was not touched |
| `NOT_FOUND` | Repository returned no product | Query succeeded, but no data exists |
| `INVALID_DATA` | Unit price from source is invalid | Dependency returned data, but it violates an invariant |
| `DEPENDENCY_UNAVAILABLE` | `read` or `save` threw `IOException` | Could not complete the required operation with the dependency |
| `NOTIFICATION_FAILED` | `send` threw after `save` succeeded | Failure after the save step; must not assume it was not saved |
| `CLOSE_FAILED` | No prior error, but `close()` threw `IOException` | Resource cleanup/closing operation failed |

Error codes form a contract between layers, **not** verbatim messages from external systems. `DomainFailure` holds a `Code` and a `Throwable cause` when an I/O error occurs. This allows upper layers to distinguish input, business, and dependency errors without parsing free-form message strings.

In a real system, you must decide when to report HTTP 400, 404, 409, 422, 503, or an indeterminate status to the client. Do not default every `IOException` to 503: it can represent different conditions depending on the contract and when side effects occurred.

## 5. Complete Java 17+ Program

Create the file **`OrderIntegrationDemo.java`** with the following content. It uses only the Java Standard Library and runs on JDK 17 or higher.

```java
import java.io.IOException;
import java.util.concurrent.*;

public class OrderIntegrationDemo {
    enum Mode {
        OK, MISSING, READ_FAIL, BAD_PRICE, SAVE_FAIL,
        NOTIFY_FAIL, CLOSE_FAIL, READ_AND_CLOSE_FAIL
    }
    enum Code {
        INVALID_REQUEST, NOT_FOUND, INVALID_DATA,
        DEPENDENCY_UNAVAILABLE, NOTIFICATION_FAILED, CLOSE_FAILED
    }
    record Request(String id, int quantity) {}
    record Product(int unitPrice) {}
    record Receipt(String id, long total) {}

    static final class DomainFailure extends RuntimeException {
        final Code code;
        DomainFailure(Code code, Throwable cause) {
            super(code.name(), cause);
            this.code = code;
        }
    }

    static final class FakeStore {
        final Mode mode;
        int opens, reads, writes, closes;
        boolean persisted;

        FakeStore(Mode mode) { this.mode = mode; }

        Session open() {
            opens++;
            return new Session();
        }

        final class Session implements AutoCloseable {
            Product read(String id) throws IOException {
                reads++;
                if (mode == Mode.READ_FAIL || mode == Mode.READ_AND_CLOSE_FAIL) {
                    throw new IOException("read failed");
                }
                if (mode == Mode.MISSING) return null;
                return new Product(mode == Mode.BAD_PRICE ? -1 : 25);
            }

            void save(Receipt receipt) throws IOException {
                writes++;
                if (mode == Mode.SAVE_FAIL) {
                    throw new IOException("save failed");
                }
                persisted = true;
            }

            @Override
            public void close() throws IOException {
                closes++;
                if (mode == Mode.CLOSE_FAIL ||
                        mode == Mode.READ_AND_CLOSE_FAIL) {
                    throw new IOException("close failed");
                }
            }
        }
    }

    static final class FakeNotifier {
        final Mode mode;
        int sends;
        FakeNotifier(Mode mode) { this.mode = mode; }

        void send(Receipt receipt) throws IOException {
            sends++;
            if (mode == Mode.NOTIFY_FAIL) {
                throw new IOException("notify failed");
            }
        }
    }

    static final class OrderService {
        Receipt create(Request request, FakeStore store, FakeNotifier notifier) {
            if (request == null || request.id() == null ||
                    request.id().isBlank() || request.quantity() <= 0) {
                throw new DomainFailure(Code.INVALID_REQUEST, null);
            }
            try (FakeStore.Session session = store.open()) {
                Product product;
                try {
                    product = session.read(request.id());
                } catch (IOException ex) {
                    throw new DomainFailure(Code.DEPENDENCY_UNAVAILABLE, ex);
                }
                if (product == null) {
                    throw new DomainFailure(Code.NOT_FOUND, null);
                }
                if (product.unitPrice() <= 0) {
                    throw new DomainFailure(Code.INVALID_DATA, null);
                }
                Receipt receipt = new Receipt(request.id(),
                        (long) product.unitPrice() * request.quantity());
                try {
                    session.save(receipt);
                } catch (IOException ex) {
                    throw new DomainFailure(Code.DEPENDENCY_UNAVAILABLE, ex);
                }
                try {
                    notifier.send(receipt);
                } catch (IOException ex) {
                    throw new DomainFailure(Code.NOTIFICATION_FAILED, ex);
                }
                return receipt;
            } catch (IOException closeFailure) {
                throw new DomainFailure(Code.CLOSE_FAILED, closeFailure);
            }
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void scenario(String name, Mode mode, Request request,
            Code expectedCode, boolean expectedPersisted,
            int expectedSuppressed) {
        FakeStore store = new FakeStore(mode);
        FakeNotifier notifier = new FakeNotifier(mode);
        try {
            Receipt receipt = new OrderService().create(request, store, notifier);
            check(expectedCode == null, name + " unexpectedly succeeded");
            check(receipt.total() == 50, "wrong total");
            check(store.persisted && store.closes == 1 && notifier.sends == 1,
                    "wrong success side effects");
            System.out.println(name + ": SUCCESS total=" + receipt.total());
        } catch (DomainFailure ex) {
            check(ex.code == expectedCode, name + " wrong error code");
            check(store.persisted == expectedPersisted, "wrong persistence");
            check(ex.getSuppressed().length == expectedSuppressed,
                    name + " wrong suppressed count");
            if (ex.code == Code.INVALID_REQUEST) {
                check(store.opens == 0 && store.closes == 0,
                        "validation must happen before dependency");
            } else {
                check(store.opens == 1 && store.closes == 1,
                        "session must close exactly once");
            }
            if (ex.code == Code.DEPENDENCY_UNAVAILABLE ||
                    ex.code == Code.NOTIFICATION_FAILED ||
                    ex.code == Code.CLOSE_FAILED) {
                check(ex.getCause() instanceof IOException,
                        "IO cause not preserved");
            }
            System.out.println(name + ": " + ex.code
                    + " persisted=" + store.persisted
                    + " suppressed=" + ex.getSuppressed().length);
        }
    }

    static void asyncFailure() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<?> future = executor.submit(() ->
                    new OrderService().create(new Request("A", 2),
                            new FakeStore(Mode.READ_FAIL),
                            new FakeNotifier(Mode.READ_FAIL)));
            try {
                future.get(5, TimeUnit.SECONDS);
                throw new AssertionError("expected execution failure");
            } catch (ExecutionException ex) {
                check(ex.getCause() instanceof DomainFailure,
                        "wrong async cause");
                DomainFailure failure = (DomainFailure) ex.getCause();
                check(failure.code == Code.DEPENDENCY_UNAVAILABLE,
                        "wrong async code");
                System.out.println("ASYNC: " + failure.code);
            }
        } finally {
            executor.shutdownNow();
            check(executor.awaitTermination(5, TimeUnit.SECONDS),
                    "executor did not stop");
        }
    }

    static void asyncCancellation() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        try {
            Future<?> future = executor.submit(() -> {
                started.countDown();
                try {
                    new CountDownLatch(1).await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });
            check(started.await(5, TimeUnit.SECONDS), "task did not start");
            check(future.cancel(true), "cancellation was not accepted");
            check(finished.await(5, TimeUnit.SECONDS), "task did not stop");
            try {
                future.get();
                throw new AssertionError("expected cancellation");
            } catch (CancellationException expected) {
                System.out.println("CANCEL: CancellationException");
            }
        } finally {
            executor.shutdownNow();
            check(executor.awaitTermination(5, TimeUnit.SECONDS),
                    "executor did not stop");
        }
    }

    public static void main(String[] args) throws Exception {
        scenario("SUCCESS", Mode.OK, new Request("A", 2), null, true, 0);
        scenario("INVALID", Mode.OK, new Request("", 2),
                Code.INVALID_REQUEST, false, 0);
        scenario("MISSING", Mode.MISSING, new Request("A", 2),
                Code.NOT_FOUND, false, 0);
        scenario("READ_FAIL", Mode.READ_FAIL, new Request("A", 2),
                Code.DEPENDENCY_UNAVAILABLE, false, 0);
        scenario("BAD_PRICE", Mode.BAD_PRICE, new Request("A", 2),
                Code.INVALID_DATA, false, 0);
        scenario("SAVE_FAIL", Mode.SAVE_FAIL, new Request("A", 2),
                Code.DEPENDENCY_UNAVAILABLE, false, 0);
        scenario("NOTIFY_FAIL", Mode.NOTIFY_FAIL, new Request("A", 2),
                Code.NOTIFICATION_FAILED, true, 0);
        scenario("CLOSE_FAIL", Mode.CLOSE_FAIL, new Request("A", 2),
                Code.CLOSE_FAILED, true, 0);
        scenario("READ_CLOSE", Mode.READ_AND_CLOSE_FAIL, new Request("A", 2),
                Code.DEPENDENCY_UNAVAILABLE, false, 1);
        asyncFailure();
        asyncCancellation();
        System.out.println("INTEGRATION_CHECKS: PASS");
    }
}
```

### Compile and Run

In the directory containing the file:

```bash
javac -encoding UTF-8 OrderIntegrationDemo.java
java OrderIntegrationDemo
```

The program prints the output below when all check conditions pass. **Standard output has been verified with javac/java**:

```text
SUCCESS: SUCCESS total=50
INVALID: INVALID_REQUEST persisted=false suppressed=0
MISSING: NOT_FOUND persisted=false suppressed=0
READ_FAIL: DEPENDENCY_UNAVAILABLE persisted=false suppressed=0
BAD_PRICE: INVALID_DATA persisted=false suppressed=0
SAVE_FAIL: DEPENDENCY_UNAVAILABLE persisted=false suppressed=0
NOTIFY_FAIL: NOTIFICATION_FAILED persisted=true suppressed=0
CLOSE_FAIL: CLOSE_FAILED persisted=true suppressed=0
READ_CLOSE: DEPENDENCY_UNAVAILABLE persisted=false suppressed=1
ASYNC: DEPENDENCY_UNAVAILABLE
CANCEL: CancellationException
INTEGRATION_CHECKS: PASS
```

**Important:** the outputs above come from a simulated demo with controlled state; they are not a guarantee of completion ordering on every real executor. The async demos only print after latch/`Future` wait conditions; real-world operations may require different timeouts depending on the environment.

## 6. Why Is This Structure an Integration Example?

A single unit test can verify `validate(id)` or a mapper in isolation, whereas the exercise above tests **the interaction across multiple boundaries**:

- Validation must run before opening a dependency.
- Reading data may return "no result" or throw an I/O error.
- Successfully read data may still violate an invariant.
- Writing data may fail before marking persistence.
- Sending a notification may fail **after saving**.
- Resource closing may itself throw an exception, even when the body succeeded.
- When both the body and close fail, the primary and suppressed exceptions must be preserved.
- When running the same workflow via `ExecutorService`, the exception surfaces at `Future.get()` on the caller rather than unwinding the submitting thread's stack.
- Cancellation requires separate signaling and worker termination checks.

These aspects fit **component/integration-style tests using fake ports**. However, because no real database or server is used, it must not be called an integration test that proves the entire production environment. A true integration test with PostgreSQL, a broker, an HTTP client, or a transaction manager must also verify the semantics of those dependencies.

The term "integration" here denotes an **end-to-end workflow within the scope of the wired components**, not a claim that all external dependencies have been tested.

## 7. Input Validation Must Happen Before Side Effects

At the beginning of `OrderService.create`:

```java
if (request == null || request.id() == null ||
        request.id().isBlank() || request.quantity() <= 0) {
    throw new DomainFailure(Code.INVALID_REQUEST, null);
}
```

This is a snippet from the complete program. The check runs **before `store.open()`**.

In the `INVALID` case, the test suite verifies:

- `DomainFailure.code == INVALID_REQUEST`.
- `store.opens == 0`.
- `store.closes == 0`.
- `store.persisted == false`.
- No save or notification attempt is made.

The goal is not merely "an `IllegalArgumentException` was thrown." If a bug causes the code to open a session before validation, the test must catch that unnecessary action. Likewise, when a system processes payments, validation and authorization must occur before side effects according to the contract.

Some validations may require querying a DB to check existence or relationships. In that case, you cannot claim every validation is "zero I/O"; clearly define which steps are allowed to read, which are forbidden from writing, and assert according to the contract.

## 8. Separating "Not Found" from "Dependency Unavailable"

Suppose the repository has the contract:

```java
Product read(String id) throws IOException;
```

This is the signature of the fake in the example. It has two ways of not returning a valid `Product`:

1. **Return `null`**: the query ran, but no product exists → `NOT_FOUND`.
2. **Throw `IOException`**: no result could be retrieved due to a dependency error → `DEPENDENCY_UNAVAILABLE`.

The two cases have different meanings. If every `IOException` is turned into `null` or `Optional.empty()`, the caller might return 404 for a product that actually exists while the DB is down. If a non-existent product ID is interpreted as downtime, the caller will retry pointlessly.

The test output:

```text
MISSING: NOT_FOUND persisted=false suppressed=0
READ_FAIL: DEPENDENCY_UNAVAILABLE persisted=false suppressed=0
```

shows two distinct outcomes even though neither produces a receipt. When building a real API, use an unambiguous contract for "not found"; you can use `Optional<Product>` instead of `null`, while keeping exceptions for I/O errors.

## 9. Invalid Source Data Is Not the Same as Invalid Caller Arguments

In the `BAD_PRICE` case, `FakeStore.Session.read` returns `Product(-1)`. This is an **invalid value from the dependency**, not a request with an invalid quantity. `OrderService` detects `unitPrice <= 0` and throws `INVALID_DATA` before saving.

The test verifies:

- The input request is valid.
- The session was opened and will be closed.
- The product was read with no I/O error.
- The unit price violates the invariant, so it must not be computed or saved.
- `store.persisted == false`.
- No notification should be performed.

This distinction matters when handling data from a database, JSON, message queue, or SDK. If a DTO is syntactically valid but violates a business invariant, you should not carelessly throw `NullPointerException` or return a receipt with a negative total.

The example computes the amount using `long` to avoid overflow when multiplying two positive `int` values into an `int`. In a real application, represent money using an appropriate type and unit (such as an integer amount in the minor unit or `BigDecimal` with a rounding policy), and validate value ranges, currency, and overflow. Do not casually use floating-point numbers for financial calculations.

## 10. Classifying I/O Errors at the Right Adapter/Service Boundary

Both `read` and `save` can throw `IOException`, yet both map to `DEPENDENCY_UNAVAILABLE` in the demo contract:

```java
try {
    product = session.read(request.id());
} catch (IOException ex) {
    throw new DomainFailure(Code.DEPENDENCY_UNAVAILABLE, ex);
}
```

and:

```java
try {
    session.save(receipt);
} catch (IOException ex) {
    throw new DomainFailure(Code.DEPENDENCY_UNAVAILABLE, ex);
}
```

These are snippets taken from the program. Because the handler uses `new DomainFailure(code, ex)`, the original `Throwable` remains accessible via `getCause()`.

The test not only asserts the code but also verifies `cause instanceof IOException`. If you drop the cause, operations logs cannot easily tell where the I/O error occurred; if you always print the raw cause into the HTTP response, you risk leaking internal details. Therefore, **preserve the cause for internal diagnostics** while **returning a safe error code to the client**.

A real application may also have permission errors, conflicts, unique-constraint violations, or temporarily locked data, which need narrower mapping rather than treating everything as downtime. This exercise chooses `IOException` as a fake error class to focus on **exception translation constraints and failure path testing**.

## 11. Notification Failure After Saving: The Most Important Example

In `OrderService.create`, the order of operations is:

```text
Session.save(receipt)
       ↓
persisted = true
       ↓
Notifier.send(receipt)
       ↓
IOException if notifier fails
       ↓
DomainFailure(NOTIFICATION_FAILED)
```

Because notification happens **after saving**, the `NOTIFY_FAIL` case produces:

```text
NOTIFY_FAIL: NOTIFICATION_FAILED persisted=true suppressed=0
```

This demonstrates an essential principle: **an exception result does not mean no side effects occurred**. If a caller sees `NOTIFICATION_FAILED` and retries the entire order-creation command without checking, it may create duplicate orders or send duplicate notifications.

In a production system, design one of the following policies with a clear contract:

- **Transactional outbox:** save business data and a "notification pending" record in the same DB transaction; a dedicated worker sends notifications with controlled retries.
- **Idempotency key:** every order-creation request carries a stable ID so retries do not create new records when the same transaction has already been processed.
- **Staged status:** `PERSISTED_NOTIFICATION_PENDING` or an equivalent status, enabling tracking and reconciliation.
- **Compensation:** if a distributed workflow cannot use a single transaction, define compensating actions that can themselves fail and must be monitored.
- **Reconciliation:** when a notifier returns a timeout or loses an ACK, do not conclude "not sent"; you may need to query/track the receiving system.

The example intentionally **does not auto-rollback** in the fake because there is no transaction. That is a design lesson, not a missing feature to hide with `catch (Exception)`.

## 12. Close Failure After a Successful Body

`try-with-resources` calls `close()` when exiting the block, including after the `return receipt` statement in the `try` body. With `Mode.CLOSE_FAIL`, the read, save, and notify steps may have already completed; then `close()` throws `IOException`, and the outermost handler translates it into `DomainFailure(CLOSE_FAILED, cause)`.

Output:

```text
CLOSE_FAIL: CLOSE_FAILED persisted=true suppressed=0
```

Thus, an exception on close **does not prove the save operation failed**. In a real system, `close()` may flush, commit, return a connection to a pool, or release a file handle depending on its contract. The state after a close failure must be verified against the specific dependency, not inferred from the exception type alone.

The fake's contract here: `save` sets `persisted=true` immediately, and `close` does not revert it. The test relies on this assumption explicitly.

Do not catch `IOException` from close and silently ignore it if a close failure can lead to data loss, unflushed files, or resource leaks. Depending on requirements, you may need to report an **uncertain** state rather than retrying immediately.

## 13. Primary and Suppressed Exceptions When Both Read and Close Fail

The `READ_AND_CLOSE_FAIL` case produces two exceptions:

1. `session.read` throws `IOException("read failed")`.
2. The service translates it into `DomainFailure(DEPENDENCY_UNAVAILABLE, cause)`.
3. Upon exiting `try-with-resources`, `session.close()` throws `IOException("close failed")`.
4. Java keeps `DomainFailure` as the **primary exception**, and attaches the close error to the suppressed array.

Result:

```text
READ_CLOSE: DEPENDENCY_UNAVAILABLE persisted=false suppressed=1
```

Distinguish clearly:

- `getCause()` returns the cause of `DomainFailure`, here the I/O error during read.
- `getSuppressed()` contains the `Throwable` from closing the resource.
- The close error does not replace the read error when a prior primary exception exists.
- Do not conclude cleanup succeeded completely just because you see `DEPENDENCY_UNAVAILABLE`.

For stricter testing, beyond the suppressed count, you can check:

```java
DomainFailure failure = /* failure from OrderService.create(...) */;
Throwable[] suppressed = failure.getSuppressed();
if (suppressed.length != 1 ||
        !(suppressed[0] instanceof IOException) ||
        !"close failed".equals(suppressed[0].getMessage())) {
    throw new AssertionError("Close failure was not retained");
}
```

This is an **additional assertion snippet**, not a standalone compilable block: the `failure` variable must be obtained from the `READ_AND_CLOSE_FAIL` case, and `DomainFailure` lives inside the program's class. In real unit tests, use JUnit's `assertEquals` and `assertInstanceOf` where appropriate.

If multiple `AutoCloseable` resources are declared in one resource header, Java closes them in reverse initialization order. Secondary close errors can be added as suppressed in the order they occur; test the event order as well, not just `length`, when close order matters.

## 14. Testing Arrange, Act, and Assert Failures Differently

Even in an integration example, tests must not produce false positives by expecting an exception across too many steps:

```java
assertThrows(DomainFailure.class, () -> {
    FakeStore store = createStoreFromExternalConfig();
    FakeNotifier notifier = setupNotifier();
    new OrderService().create(request, store, notifier);
});
```

This is a **JUnit 5 snippet with the wrong scope** when setup helpers can throw the same `DomainFailure` type. If setup fails before calling `create`, the test can still pass without exercising the SUT.

Better pattern:

```java
FakeStore store = new FakeStore(Mode.READ_FAIL);
FakeNotifier notifier = new FakeNotifier(Mode.READ_FAIL);
OrderService service = new OrderService();
Request request = new Request("A", 2);

DomainFailure failure = assertThrows(
        DomainFailure.class,
        () -> service.create(request, store, notifier));

assertEquals(Code.DEPENDENCY_UNAVAILABLE, failure.code);
assertInstanceOf(IOException.class, failure.getCause());
assertFalse(store.persisted);
assertEquals(1, store.closes);
```

This is a **JUnit Jupiter** snippet requiring assertion imports and application classes, not a standalone Java SE program. `Arrange` creates the fakes; `Act` is **only** `service.create` inside `assertThrows`; `Assert` checks the code, cause, and side effects.

If fixture setup throws an error, the test must **fail in Arrange** rather than being treated as an expected exception from the service. This is especially important when integrating complex database/container test setups.

## 15. Why Have opens/reads/writes/closes Counters?

Asserting only the error code can miss a resource management bug. For instance, the service might return `INVALID_REQUEST` properly while still opening a session or calling the notifier before validation: the response looks right while the side effects are wrong.

The fake records counters:

```java
int opens, reads, writes, closes;
boolean persisted;
```

In `scenario(...)`:

- For `INVALID_REQUEST`, expect `opens == 0` and `closes == 0`.
- For cases that opened a session, expect `opens == 1`, `closes == 1`.
- For failures before save, expect `persisted == false`.
- For `NOTIFY_FAIL` or `CLOSE_FAIL`, expect `persisted == true`.
- For the happy path, expect the correct total and that the notifier was called.

When moving to a test framework, you can also assert exact `reads`, `writes`, and `sends` counts to increase coverage. However, do not assert internal details that are not part of the contract: for example, if refactoring merges two reads into a single query without changing public behavior, tests coupled too tightly to implementation details become brittle.

**Counters are only justified when the call count itself is part of the contract**, such as never sending a notification before saving or never writing when input is invalid.

## 16. A Required Failure Scenario Matrix

| Scenario | Error code | Persisted | Close | What to prove |
| --- | --- | --- | --- | --- |
| Valid input, healthy dependencies | No error | true | 1 | Receipt total `50`, notifier called |
| Empty product ID | `INVALID_REQUEST` | false | 0 | Validation blocks I/O upfront |
| Product does not exist | `NOT_FOUND` | false | 1 | Not found differs from unavailable |
| Read fails with `IOException` | `DEPENDENCY_UNAVAILABLE` | false | 1 | I/O cause is preserved |
| Invalid unit price | `INVALID_DATA` | false | 1 | Invalid data is not saved |
| Save fails before commit | `DEPENDENCY_UNAVAILABLE` | false | 1 | No false success reported |
| Notifier fails after save | `NOTIFICATION_FAILED` | true | 1 | Failure after side effect |
| Close fails after successful body | `CLOSE_FAILED` | true | 1 | Body return is not the final return |
| Read fails + close fails | `DEPENDENCY_UNAVAILABLE` | false | 1 | Close error is suppressed |
| Task via Executor fails | Cause `DomainFailure` | depends on case | per fake | `get()` throws `ExecutionException` |
| Waiting worker is canceled | Future canceled | N/A | pool stopped | `get()` throws `CancellationException` |

A more thorough test suite with real dependencies should also add: lost ACK after commit, timeouts, duplicate request retries, failed transaction rollback, duplicate notifier delivery, connection pool exhaustion, resource close timeouts, concurrent request contention, and data access permissions.

Each case should have **one clear objective**: error type, side effect, or lifecycle. Do not just check that "some exception was thrown" while ignoring the final state.

## 17. Java Future: Worker Errors Do Not Enter a Catch Around submit

The example program submits `OrderService.create` to an executor:

```java
Future<?> future = executor.submit(() ->
        new OrderService().create(new Request("A", 2),
                new FakeStore(Mode.READ_FAIL),
                new FakeNotifier(Mode.READ_FAIL)));
```

This snippet is from the program's `asyncFailure`. The error from `create` happens inside the worker. It does not enter a `catch` block surrounding `submit()` on the caller; instead, the `Future` completes abnormally.

When calling:

```java
try {
    future.get(5, TimeUnit.SECONDS);
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Verify that cause is a DomainFailure with code DEPENDENCY_UNAVAILABLE.
}
```

this snippet is inside a method that handles checked exceptions. `Future.get()` throws `ExecutionException` with `DomainFailure` as its cause. The task failed according to contract, not because of a network error on the caller thread.

Distinguish clearly:

- `ExecutionException`: the task completed abnormally; inspect its cause.
- `InterruptedException`: the thread **waiting** on the Future was interrupted.
- `TimeoutException`: the caller waited past the deadline; does not prove the task was canceled.
- `CancellationException`: the Future was canceled.

Do not use `catch (Exception)` and turn everything into a dependency error; a worker bug, caller timeout, and cancellation are distinct conditions.

## 18. Testing `cancel(true)` and Cooperative Interruption

The `asyncCancellation()` section creates a worker waiting on `CountDownLatch.await()`. The caller waits for `started` and then calls:

```java
future.cancel(true);
```

Because the task is waiting, it can respond to the interrupt with `InterruptedException`. In the worker:

```java
try {
    new CountDownLatch(1).await();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} finally {
    finished.countDown();
}
```

This is an excerpt from the complete program. The handler restores the interrupt flag and lets the task exit, and `finally` signals `finished` so the test confirms the worker passed through cleanup.

The test verifies:

1. The worker **had started** before calling cancel.
2. `future.cancel(true)` returns true in this deterministic scenario.
3. The worker signals `finished` within the test timeout.
4. `future.get()` throws `CancellationException`.
5. The pool is asked to shut down and `awaitTermination` confirms termination.

**Important:** `Future.cancel(true)` is a cancellation request. For uncooperative tasks or non-interruptible I/O, it does not forcibly stop all work. A Future may report canceled while some side effects continue. Therefore, the test uses a latch to verify the worker passed through cleanup rather than relying solely on `future.isDone()`.

If a task executes a real transaction, you need a dedicated policy for idempotency and post-cancellation state; the demo intentionally performs no transaction in the cancellation scenario to avoid indeterminate results.

## 19. Managing the Pool and Avoiding Hanging Tests

In both async methods, the executor is created with `Executors.newSingleThreadExecutor()`. When exiting the method:

```java
executor.shutdownNow();
check(executor.awaitTermination(5, TimeUnit.SECONDS),
        "executor did not stop");
```

This is a snippet from the program. `shutdownNow()` attempts to stop running tasks, typically via interruption. `awaitTermination()` waits for the executor to finish; if it does not terminate within the limit, the test detects the failure instead of hanging silently.

In typical production code:

- `shutdown()` requests stopping acceptance of new tasks while letting submitted tasks finish per policy.
- `awaitTermination(timeout, unit)` waits with a bounded timeout.
- `shutdownNow()` is **best effort** and does not guarantee every worker stops immediately.
- If the thread managing the pool is interrupted while waiting, it must follow cancellation policy and usually restore the interrupt flag if not propagating the exception.
- Do not shut down a shared executor owned by a framework or another module.

Tests can use a timeout longer than 5 seconds on overloaded CI, but should not use arbitrary `Thread.sleep` calls to guess when a thread is done. `CountDownLatch`, `Future.get(timeout)`, and `awaitTermination` provide clearer signals.

## 20. From a Self-Check Program to JUnit 5

The program uses `check(...)` so it can run standalone without a build tool. In a real project, organize it into JUnit Jupiter tests. For example:

```java
@Test
void notificationFailureDoesNotUndoPersistedOrder() {
    FakeStore store = new FakeStore(Mode.NOTIFY_FAIL);
    FakeNotifier notifier = new FakeNotifier(Mode.NOTIFY_FAIL);
    OrderService service = new OrderService();

    DomainFailure failure = assertThrows(
            DomainFailure.class,
            () -> service.create(new Request("A", 2), store, notifier));

    assertEquals(Code.NOTIFICATION_FAILED, failure.code);
    assertInstanceOf(IOException.class, failure.getCause());
    assertTrue(store.persisted);
    assertEquals(1, store.closes);
    assertEquals(1, notifier.sends);
}
```

This is a **JUnit 5 snippet** that must be placed in a test class with imports/visibility to the types inside `OrderIntegrationDemo`. It is not a standalone program runnable with `javac` without adding JUnit and adjusting package/static imports.

Another test to verify suppression:

```java
@Test
void readFailureKeepsCloseFailureSuppressed() {
    FakeStore store = new FakeStore(Mode.READ_AND_CLOSE_FAIL);
    FakeNotifier notifier = new FakeNotifier(Mode.READ_AND_CLOSE_FAIL);

    DomainFailure failure = assertThrows(DomainFailure.class,
            () -> new OrderService().create(new Request("A", 2),
                    store, notifier));

    assertEquals(Code.DEPENDENCY_UNAVAILABLE, failure.code);
    assertInstanceOf(IOException.class, failure.getCause());
    assertEquals(1, failure.getSuppressed().length);
    assertEquals("close failed", failure.getSuppressed()[0].getMessage());
    assertFalse(store.persisted);
    assertEquals(1, store.closes);
}
```

The assertions require importing `org.junit.jupiter.api.Test` and static methods from `org.junit.jupiter.api.Assertions`. When splitting classes into separate source files, inject the repository/notifier via interfaces instead of having the service depend directly on fakes. That is the natural refactoring step when turning a learning demo into a production architecture.

## 21. Refactoring to Ports/Adapters for Maintainable Testing

In the demo, `OrderService.create` takes `FakeStore` and `FakeNotifier` directly so everything fits in a single runnable file. In a real project, move dependencies to interfaces:

```java
interface OrderStore {
    Session open() throws IOException;
    interface Session extends AutoCloseable {
        Product read(String id) throws IOException;
        void save(Receipt receipt) throws IOException;
        @Override void close() throws IOException;
    }
}

interface Notifier {
    void send(Receipt receipt) throws IOException;
}
```

This is an **API design snippet**, with `Product`/`Receipt` belonging to the domain defined in the application. If `open()` can also throw `IOException`, the service must map session initialization errors separately; it must not be confused with a close failure.

Benefits:

- Unit tests use in-memory fakes with clearly controlled failure modes.
- Integration tests use real adapters connected to a DB/message broker.
- The service only knows the read/save/send contract, not JDBC/HTTP implementation details.
- Easy to attach retry, timeout, and circuit breakers at the adapter with clear responsibilities.
- API mapping and transaction boundaries can be tested independently.

However, do not create interfaces just because "every class needs an interface." Use abstraction when it helps swap dependencies, control side effects, or improve practical testability.

## 22. Extending Tests for Session-Open Failures

The demo simulates errors in `read`, `save`, and `close`, while `FakeStore.open()` always succeeds. A real repository can fail right when acquiring a connection.

If you change the signature to:

```java
OrderStore.Session open() throws IOException;
```

then the service must distinguish **open failure** from **close failure**. Do not place a single `catch (IOException)` after the entire `try-with-resources` block and assume every I/O error is a close failure.

Example pattern:

```java
OrderStore.Session session;
try {
    session = store.open();
} catch (IOException ex) {
    throw new DomainFailure(Code.DEPENDENCY_UNAVAILABLE, ex);
}

try (session) {
    // Read, validate, save, notify.
} catch (IOException ex) {
    // IOException from close if operations in the body
    // have already been caught/translated to domain errors in the right place.
    throw new DomainFailure(Code.CLOSE_FAILED, ex);
}
```

This is an **architectural snippet**, not a standalone program; `OrderStore` and `DomainFailure` must be defined. The goal is to avoid misclassifying the exception source. If body operations still have untranslated `IOException`s, the outer catch could still receive them; therefore, you cannot assert that every `IOException` reaching the final catch definitely comes from `close` unless the body contract guarantees it.

A session-open failure test should verify that read/save/notify are not called and that close is not called on a session that was never successfully initialized.

## 23. Integration Failures That Cannot Be Simulated with a Single Exception

A real-world failure often involves multiple states:

**Timeout after a write command:** The caller times out, yet the DB may have already committed. Retries must use idempotency or reconciliation, not rely solely on `TimeoutException`.

**Lost ACK from broker:** The notification may have been sent, yet the application did not receive the response. Do not assume `IOException` means the notification was not delivered.

**Deadlock or lock timeout:** The transaction may be rolled back by the database, or only a single statement may be aborted. You need the specific driver/DB contract.

**Interrupted during I/O:** Some APIs respond to interruption, while others require closing the socket/stream or setting a timeout; never promise that every `cancel(true)` stops immediately.

**Close failure after a successful operation:** Data might be partially saved, flushing may not have succeeded, or the connection pool may be unhealthy. Do not infer "committed/not committed" without knowing the semantics.

**Concurrent requests with the same key:** A single-threaded fake test does not prove uniqueness, transaction isolation, race freedom, or idempotency under load.

**Errors in the test setup step:** Do not confuse an exception from creating a database/container/fixture with a failure of the SUT. Place Arrange outside the `assertThrows` lambda.

Hence, a good suite typically has **unit tests for mapping and control branches**, **component tests for workflows**, **integration tests with real dependencies or near-real environments**, and a few **end-to-end tests** verifying the public protocol. Each test layer has its own purpose; you do not need to repeat every case at every layer.

## 24. Designing Error Handling and Safe Responses

`DomainFailure.code` can be mapped to a response at the API boundary. Design example:

| Domain code | Suggested response | Notes |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 / `INVALID_REQUEST` | Do not expose raw input if it contains private data |
| `NOT_FOUND` | 404 / `NOT_FOUND` | Depends on access permissions and anti-enumeration policy |
| `INVALID_DATA` | 502 or 500 depending on boundary | Invalid source data differs from invalid caller input |
| `DEPENDENCY_UNAVAILABLE` | 503 when truly unavailable | Keep cause in access-controlled internal logs |
| `NOTIFICATION_FAILED` | Business-meaningful partial/pending state | Do not suggest blindly retrying the entire workflow |
| `CLOSE_FAILED` | Error or indeterminate state | Do not claim the save did not happen |

This is an **architectural suggestion**, not a fixed HTTP mapping for every system. `INVALID_DATA` could be data from an external source or generated by the application itself; status assignment depends on the contract.

Public responses should contain a stable code, a safe message, and a non-sensitive correlation ID. Do not include raw `IOException.getMessage()`, stack traces, bearer tokens, or request bodies in responses. Dependency errors may contain data that must not be exposed.

In logging, record the operation, code, elapsed time, request ID, and side-effect status according to a schema. Do not log the same `Throwable` at every layer just because there is a `catch`; designate one place responsible for final error observability.

## 25. Review Checklist Before Considering the Practice Complete

1. **Right scope:** The workflow covers validation, reading, calculation, writing, notification, resource closing, and an async caller.
2. **Runnable code:** File/class names match, uses Java 17+ APIs, complete imports, includes `javac`/`java` commands.
3. **Happy path:** Produces the exact receipt, closes resources, and invokes required dependencies.
4. **Validation:** Invalid input must not open a session or cause side effects.
5. **Not found vs. I/O:** Do not mix "no data" with "unable to query."
6. **Invalid source data:** Do not persist output based on an invalid unit price.
7. **Dependency cause:** Exception translation preserves `getCause()` for diagnostics.
8. **Partial success:** Notifier/close failures after saving do not lead tests to assume it was not saved.
9. **Suppressed:** When both body and close fail, primary and `getSuppressed()` are accurate.
10. **Executor:** `Future.get()` distinguishes `ExecutionException` from cancellation/interrupt/timeout.
11. **Cancellation:** The task cooperates with interruption, and the test has signals confirming cleanup and pool shutdown.
12. **Isolation:** Each scenario has fresh fakes; no dependency on test order or data from previous cases.
13. **Determinism:** Uses meaningful latches/timeouts, not arbitrary short sleeps.
14. **Cleanup:** Pool and session have closing paths; cleanup errors are not masked.
15. **Error messages:** Clients do not receive raw causes or sensitive data.
16. **Retry:** Do not auto-retry operations that may have committed without idempotency and reconciliation.
17. **Test boundaries:** Fixture setup, SUT action, and assertions are separated.
18. **Extensibility:** Ports/adapters allow switching from fakes to real dependencies with appropriate integration tests.

**Conclusion:** a Java example is only truly complete when **failure paths are specified and tested** just as thoroughly as the happy path. Verify error codes, causes, suppressed exceptions, dependency call counts, persisted state, task cancellation, and resource closing. An exception caught by the right class that loses information or hides side effects is still a design flaw—especially when integrating multiple dependencies and asynchronous execution.
