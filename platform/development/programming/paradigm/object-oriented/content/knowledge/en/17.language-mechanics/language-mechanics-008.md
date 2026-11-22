# Exceptions, error states, and method contracts in Java

**Topic:** OOP → Language Mechanics

A Java method may **complete and return a result**, **reject a business request**, or **fail to complete because of an error**. Choosing between `boolean`, `Optional`, a structured result type, and exceptions determines how API callers handle each situation.

This lesson explains Java exception mechanics, error-state representation, and **method contracts**: valid callers and inputs, guarantees on success, behavior on failure, and whether object invariants remain intact.

## 1. Start with a practical scenario

A bookstore accepts reservations. Only 2 copies remain, but a customer requests 3 copies.

- **Out of stock** is an expected business condition. The UI should explain “Only 2 copies remain.”
- **A requested quantity of -3** violates the method contract. Clients should not call the API this way.
- **Database unavailable** is a technical failure. Representing it as “out of stock” misstates inventory.
- **Successful reservation** must reduce inventory by the correct count; failed reservations must not deduct stock.

These four cases have different meanings:

| Scenario | What callers need to know | Reasonable representation |
| --- | --- | --- |
| Successfully reserved | Reserved amount and remaining inventory | `Reserved` |
| Insufficient inventory | Rejection reason and current stock | `Rejected(OUT_OF_STOCK)` |
| Contract-breaking argument | Where API usage is invalid | `IllegalArgumentException` |
| Database connection failure | An issue requiring recovery, conditional retry, or an error report | Infrastructure exception with a clear cause |

Practical principle: **do not use one signal for every kind of failure**. In particular, `null` or `false` can be ambiguous when callers must take different actions.

## 2. What constitutes a method contract?

A method contract describes what **callers** and **implementers** agree on:

| Element | Question | Example for `reserve` |
| --- | --- | --- |
| **Precondition** | What must hold before calling? | Nonblank SKU; positive integer quantity |
| **Postcondition** | What does successful completion guarantee? | Inventory decreases by exactly the reserved quantity |
| **Invariant** | What must always hold for the object? | Inventory never becomes negative |
| **Failure contract** | What is returned/thrown on failure? | `Rejected` for insufficient stock; exception for invalid arguments |
| **Side effect** | What external state changes? | Adjusts inventory, but does not email/charge a payment |
| **Atomicity** | Can a failed operation leave partial changes? | Rejections leave inventory unchanged |
| **Concurrency** | Can simultaneous requests corrupt state? | Stock checks and deductions must form one protected operation |

The signature `int reserve(String sku, int amount)` specifies types but cannot tell us whether `-1` means not found, out of stock, or system failure.

A contract can be clearer through **well-named return types**, Javadoc, and tests:

~~~java
/**
 * Giữ một số lượng sản phẩm trong kho.
 *
 * @param sku mã sản phẩm khác null và không rỗng
 * @param quantity số lượng cần giữ, phải > 0
 * @return Reserved nếu giữ thành công;
 *         Rejected nếu sản phẩm không có hoặc không đủ hàng
 * @throws IllegalArgumentException nếu đầu vào sai hợp đồng
 *
 * Khi trả Rejected, tồn kho không thay đổi.
 * Khi trả Reserved, tồn kho còn lại không âm.
 */
ReserveResult reserve(String sku, int quantity);
~~~

Javadoc is **a promise**; only implementation, data constraints, and suitable tests provide evidence that the promise is upheld.

## 3. What are exceptions? How do checked and unchecked differ?

Java's exception hierarchy starts at `Throwable`. Its two principal branches are `Exception` and `Error`; `RuntimeException` extends `Exception`.

~~~mermaid
classDiagram
    Throwable <|-- Exception
    Throwable <|-- Error
    Exception <|-- IOException
    Exception <|-- RuntimeException
    RuntimeException <|-- IllegalArgumentException
    RuntimeException <|-- IllegalStateException
    RuntimeException <|-- NullPointerException
~~~

A **checked exception** extends `Throwable` but not `RuntimeException` or `Error`. When one can escape a method, callers must **catch** it or **declare it with `throws`**. Examples include `IOException` and `SQLException`.

**Unchecked exceptions** include `RuntimeException` and its subclasses. Callers are not compiler-required to catch or declare them. They often represent contract violations, invalid states, or failures whose APIs use this reporting style.

**`Error`** types such as `OutOfMemoryError` and `LinkageError` often indicate serious runtime problems. Most business code should not `catch (Throwable)` and then continue as though nothing happened.

| Category | Example | Compiler requires handling/declaration? | Key point |
| --- | --- | --- | --- |
| Checked | `IOException` | Yes | Catch or propagate |
| Unchecked | `IllegalArgumentException` | No | Still document triggering conditions |
| Error | `OutOfMemoryError` | No | Do not convert to routine business rejections |

**Do not assume** “checked means recoverable” or “unchecked means a bug.” HTTP libraries may report network failures through unchecked exceptions, while some checked failures cannot be handled meaningfully at the current layer.

## 4. `throw`, `throws`, `try`, and `catch`

`throw` actually throws an exception object:

~~~java
static void requirePositive(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity phải lớn hơn 0");
    }
}
~~~

`throws` **declares** exceptions allowed to propagate from a method:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String readSettings(Path file) throws IOException {
    return Files.readString(file);
}
~~~

A caller that can respond meaningfully catches the exception:

~~~java
try {
    String data = readSettings(Path.of("app.conf"));
    System.out.println(data);
} catch (IOException failure) {
    System.err.println("Không đọc được cấu hình: "
            + failure.getMessage());
}
~~~

These are **method/call snippets** intended for appropriate classes. Another caller may declare `throws IOException` and let a higher layer decide. Not every layer needs to catch and log.

**On throwing an exception**, Java interrupts normal execution and searches up the call stack for a matching `catch`. Without a handler, it reaches the thread/framework boundary. Statements after a throw on the same path do not execute normally.

### Catch specific exceptions before general ones

~~~java
try {
    // ... xử lý ...
} catch (IllegalArgumentException badInput) {
    // Xử lý đầu vào sai nếu tầng này có trách nhiệm.
} catch (RuntimeException unexpected) {
    // Chính sách riêng cho RuntimeException còn lại.
}
~~~

Catch subclasses in a `catch` clause before superclass handlers. Java rejects unreachable `catch` clauses: catching `RuntimeException` before a separate `IllegalArgumentException` handler is invalid.

Use **multi-catch** when different errors share a policy:

~~~java
catch (IllegalArgumentException | IllegalStateException failure) {
    // Quy tắc xử lý chung.
}
~~~

Alternatives in a multi-catch cannot have a subclass/superclass relationship. Do not combine every exception merely to reduce code length.

## 5. Choosing between business results and exceptions

Three hypothetical API designs can all be valid under different contracts:

~~~java
// Không cần phân biệt nguyên nhân, ví dụ một thao tác thử đơn giản.
boolean tryReserve(String sku, int quantity);

// Không có giá trị trả về là tình huống bình thường.
java.util.Optional<Book> findByIsbn(String isbn);

// Cần phân biệt thành công với các lý do từ chối.
ReserveResult reserve(String sku, int quantity);
~~~

With `Optional.empty()`, callers understand “no book” when `findByIsbn` specifies that behavior. **Do not** silently return empty on database connection failures: clients would mistakenly believe the book does not exist.

Some systems throw **domain exceptions** for out-of-stock requests, which can also be valid when API, UX, and handlers consistently follow that convention. But for expected rejections that callers commonly distinguish, **structured Result types** often make control flow clearer.

## 6. Complete Java 17 example: successful/rejected results and contract errors

Create **ErrorContractDemo.java**. The example uses `sealed interface` for closed result variants, `record` for immutable result data, and `synchronized` for checking/updating inventory in **one instance**.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ErrorContractDemo {
    enum RejectionReason {
        UNKNOWN_SKU, OUT_OF_STOCK
    }

    sealed interface ReserveResult permits Reserved, Rejected {}

    record Reserved(String sku, int quantity, int remaining)
            implements ReserveResult {
        Reserved {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || quantity <= 0 || remaining < 0) {
                throw new IllegalArgumentException(
                        "Kết quả giữ hàng không hợp lệ");
            }
        }
    }

    record Rejected(RejectionReason reason, String message)
            implements ReserveResult {
        Rejected {
            Objects.requireNonNull(reason, "reason");
            Objects.requireNonNull(message, "message");
        }
    }

    static final class StockService {
        private final Map<String, Integer> stock = new HashMap<>();

        StockService(Map<String, Integer> initialStock) {
            Objects.requireNonNull(initialStock, "initialStock");

            for (var entry : initialStock.entrySet()) {
                String sku = entry.getKey();
                Integer quantity = entry.getValue();

                if (sku == null || sku.isBlank()
                        || quantity == null || quantity < 0) {
                    throw new IllegalArgumentException(
                            "Tồn kho khởi tạo không hợp lệ");
                }
                stock.put(sku, quantity);
            }
        }

        /**
         * Preconditions: sku không rỗng, quantity > 0.
         * Rejected không làm thay đổi tồn kho.
         * Reserved giảm tồn đúng quantity, remaining >= 0.
         */
        synchronized ReserveResult reserve(
                String sku, int quantity) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException(
                        "SKU không được rỗng");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "Số lượng phải dương");
            }

            Integer available = stock.get(sku);
            if (available == null) {
                return new Rejected(
                        RejectionReason.UNKNOWN_SKU,
                        "Sản phẩm không tồn tại");
            }

            if (available < quantity) {
                return new Rejected(
                        RejectionReason.OUT_OF_STOCK,
                        "Chỉ còn " + available + " sản phẩm");
            }

            int remaining = available - quantity;
            stock.put(sku, remaining);
            return new Reserved(sku, quantity, remaining);
        }

        synchronized int remaining(String sku) {
            Integer quantity = stock.get(sku);
            if (quantity == null) {
                throw new IllegalArgumentException(
                        "Không có SKU: " + sku);
            }
            return quantity;
        }
    }

    public static void main(String[] args) {
        StockService service =
                new StockService(Map.of("JAVA", 3));

        ReserveResult first = service.reserve("JAVA", 2);
        ReserveResult second = service.reserve("JAVA", 2);

        System.out.println(first);
        System.out.println(second);
        System.out.println("Remaining: "
                + service.remaining("JAVA"));

        try {
            service.reserve("JAVA", 0);
        } catch (IllegalArgumentException failure) {
            System.out.println("INPUT_ERROR: "
                    + failure.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac ErrorContractDemo.java
java ErrorContractDemo
~~~

Output:

~~~text
Reserved[sku=JAVA, quantity=2, remaining=1]
Rejected[reason=OUT_OF_STOCK, message=Chỉ còn 1 sản phẩm]
Remaining: 1
INPUT_ERROR: Số lượng phải dương
~~~

**Analyzing the contract:**

1. The first reservation returns `Reserved`; stock falls from 3 to 1.
2. The second reservation exceeds available stock and returns `Rejected`. No additional units are deducted.
3. A request for quantity 0 violates the precondition and throws `IllegalArgumentException`.
4. `stock` is owned by `StockService`: the input map is copied, so no external mutable reference is retained.
5. `synchronized` protects both checking and decrementing under the service instance's monitor. This **does not replace a database transaction** or protect shared data across multiple JVMs/instances.

To expose result types to clients in other packages, define public APIs with suitable visibility. The example uses package-private types to keep the runnable Java program in one file.

## 7. Test return values and state after failure

Place the following in **ErrorContractDemoTest.java**, in the same package, with **JUnit Jupiter 5** configured:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ErrorContractDemoTest {

    @Test
    void reserveThanhCongGiamDungSoLuong() {
        var stock = new ErrorContractDemo.StockService(
                Map.of("JAVA", 3));

        assertEquals(
                new ErrorContractDemo.Reserved("JAVA", 2, 1),
                stock.reserve("JAVA", 2));
        assertEquals(1, stock.remaining("JAVA"));
    }

    @Test
    void reserveKhongDuHangKhongDoiState() {
        var stock = new ErrorContractDemo.StockService(
                Map.of("JAVA", 1));

        var result = stock.reserve("JAVA", 2);
        assertEquals(
                new ErrorContractDemo.Rejected(
                        ErrorContractDemo.RejectionReason.OUT_OF_STOCK,
                        "Chỉ còn 1 sản phẩm"),
                result);
        assertEquals(1, stock.remaining("JAVA"));
    }

    @Test
    void thamSoSaiNemExceptionTruocKhiThayDoi() {
        var stock = new ErrorContractDemo.StockService(
                Map.of("JAVA", 3));

        assertThrows(IllegalArgumentException.class,
                () -> stock.reserve("JAVA", 0));
        assertEquals(3, stock.remaining("JAVA"));
    }

    @Test
    void khongTimThaySkuLaTuChoiNghiepVu() {
        var stock = new ErrorContractDemo.StockService(
                Map.of("JAVA", 3));

        var result = stock.reserve("MISSING", 1);
        assertInstanceOf(ErrorContractDemo.Rejected.class, result);
        var rejected = (ErrorContractDemo.Rejected) result;
        assertEquals(
                ErrorContractDemo.RejectionReason.UNKNOWN_SKU,
                rejected.reason());
    }
}
~~~

These tests verify **postconditions as well as invariants**. They check not only which exception is thrown but also that failures leave stock unchanged. They do not prove race safety across servers or real database transaction behavior; integration tests are needed.

## 8. Stack traces, propagation, and preserving cause chains

When thrown, an exception searches up the call stack for a handler. If a repository encounters an error while reading a file, an application service may add business context by translating it:

~~~java
final class InventoryUnavailableException
        extends RuntimeException {
    InventoryUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}

static String loadInventoryText(java.nio.file.Path file) {
    try {
        return java.nio.file.Files.readString(file);
    } catch (java.io.IOException cause) {
        throw new InventoryUnavailableException(
                "Không tải được tồn kho: " + file, cause);
    }
}
~~~

These snippets belong in suitable Java classes/files. New exceptions retain the **cause** so investigations can trace back to the original `IOException`. Catching, printing stack traces, and rewrapping at every layer duplicates logs and obscures root causes.

A useful rule is to **catch at the layer capable of making a decision**:

~~~mermaid
sequenceDiagram
    participant Caller
    participant Service
    participant Repository
    Caller->>Service: load inventory
    Service->>Repository: read file
    Repository--xService: IOException
    Note over Service: Translate + giữ cause nếu cần
    Service--xCaller: InventoryUnavailableException
    Note over Caller: Quyết định phản hồi, log, retry có điều kiện
~~~

Do not use `new RuntimeException(e.getMessage())` when you need the cause chain; pass `e` as the `cause`.

### `getMessage()` should not serve as an error code

One error message might be Vietnamese today, English tomorrow, or gain detail after refactoring. Callers should distinguish failures by **exception type** or **structured error code**, not by parsing `getMessage()` text.

## 9. Try-with-resources, `finally`, and suppressed exceptions

When reading files, writing streams, or using connections, resources need closing. `try-with-resources` follows the `AutoCloseable` contract:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static long countLines(Path file) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(file)) {
        long count = 0;
        while (reader.readLine() != null) {
            count++;
        }
        return count;
    }
}
~~~

If both the `try` body and `close()` throw, the body exception normally remains the **primary exception**, while the close failure appears in `getSuppressed()`. This preserves the original failure.

`finally` commonly performs cleanup after `try`/`catch`, but avoid `return` inside it: that can mask a pending result or exception. `finally` is not guaranteed when the JVM terminates abruptly or the process is killed externally.

**Resource cleanup does not equal database rollback.** Closing resources does not undo a previously sent email or a payment already charged before failure.

## 10. Exceptions do not guarantee atomic operations

Consider:

~~~java
balance -= amount;
sendConfirmationEmail(); // Có thể ném exception.
~~~

If email delivery fails, `balance` has already been debited. Catching the exception does not automatically restore the balance.

Define **failure atomicity**: can an unsuccessful operation leave partial changes? Important data may require:

- Validate independent conditions **before** state changes.
- Use transactions for changes within the same transactional data source.
- For databases and message brokers, consider a **transactional outbox** to coordinate state updates and event persistence.
- For commands retried after timeout, use **idempotency keys** or duplicate-prevention conditions.
- Use optimistic locking, conditional updates, or suitable locks to prevent lost updates under concurrency.

Spring `@Transactional` does not undo sent email automatically; transaction-manager rollback behavior also depends on exception types, configuration, proxy boundaries, and managed resources. Test failures at the actual boundary.

## 11. Exception contracts under overriding and polymorphism

Suppose clients use this abstraction:

~~~java
interface AccountStore {
    /** Empty chỉ có nghĩa tài khoản không tồn tại. */
    java.util.Optional<String> findOwner(String accountId);
}
~~~

An implementation must not misreport network errors as `Optional.empty()`, which violates the “not found” meaning clients expect. The signature may be valid while **the behavioral contract is broken**.

Under the **Liskov Substitution Principle (LSP)**, substitutable implementations should preserve:

- **Preconditions:** do not impose unexpected extra requirements on callers.
- **Postconditions:** do not weaken guarantees on successful completion.
- **Invariants:** preserve state conditions promised by the abstraction.
- **Failure semantics:** keep rejection/error meanings and side-effect contracts.

At the Java syntax level, overriding methods **cannot introduce broader new checked exceptions** than the overridden method allows. But Java cannot forbid implementations from throwing unchecked runtime exceptions; behavior needs design and testing beyond compiler checks.

For example, implementing `ReadOnlyRepository` against an interface promising `save()` but always throwing `UnsupportedOperationException` suggests an overly broad contract or an unsuitable subtype; review interface segregation.

## 12. Mapping errors between the domain and APIs

| Layer | Example | Responsibility |
| --- | --- | --- |
| Controller/API | JSON missing fields, negative quantity | Validate inputs, return structured responses, avoid leaking internal data |
| Application service | Reservation/order cancellation request | Coordinate business rules, permissions, transactions, and side effects |
| Domain object | Invariant violation or disallowed state transition | Enforce preconditions/postconditions, return results or domain-specific failures |
| Repository/adapter | Database unavailable, timeout | Preserve causes, propagate or translate errors at appropriate boundaries |
| Job/queue consumer | Failed command handling | Define retries/backoff, dead-letter processing, and duplicate handling |
| HTTP boundary | Unhandled exceptions | Choose safe response statuses, log useful context |

**Domain error codes need not equal HTTP status codes.** `OUT_OF_STOCK` can be a stable domain enum; controllers choose HTTP status based on API policy. Do not couple domain objects to a web framework merely to express a rejection.

### Should you define custom exceptions?

When callers distinguish failures by type, consider:

~~~java
final class OrderAlreadyShippedException
        extends IllegalStateException {
    OrderAlreadyShippedException(String orderId) {
        super("Đơn đã giao không được hủy: " + orderId);
    }
}
~~~

You do not need a class per message. Choose meaningful stable exception types; keep tokens, payment details, and sensitive data out of messages that may reach logs.

## 13. Retries, interrupts, and asynchronous failures

**Do not retry every exception.** An `IllegalArgumentException` from a negative quantity will not recover after three attempts. A timeout may be temporary, but a timeout **after an external system processed the command** can cause duplicate charges or notifications if retried blindly.

When catching `InterruptedException` without propagating it, restore the thread's interrupt flag:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return; // Trong một phương thức void.
}
~~~

If a method can declare `throws InterruptedException`, propagating is often clearer. Do not swallow interrupts and make tasks ignore cancellation or shutdown.

`CompletableFuture` can end with **exceptional completion**. A caller sees failures from `join()`/`get()` through their respective wrapper exceptions. Contracts must distinguish “scheduled,” “completed in memory,” and “confirmed by the external system.”

## 14. Common design mistakes

| Mistake | Consequence | Better approach |
| --- | --- | --- |
| `catch (Exception e) { return null; }` | Cannot distinguish connection loss from missing values | Optional for absence; separate exceptions/results for errors |
| `catch (Exception ignored) {}` | Reports false success | Deliberately handle or propagate |
| `catch (Throwable t)` in business code | Swallows serious Errors | Catch exceptions that can be handled |
| `throw new RuntimeException(e.getMessage())` | Loses original cause | `new RuntimeException("...", e)` |
| Logging full stack traces at every layer | Duplicate logs obscure error boundaries | Log at the responsible boundary |
| Comparing `getMessage()` with a literal string | Breaks when language/message changes | Use exception types or error codes |
| Returning `false` for every failure | Discards important context | Return a reasoned result or suitable exception |
| Mutating state before validation | May leave invalid state | Validate first; use transactions if needed |
| Catching exceptions and assuming rollback | Prior side effects may remain | Design atomicity/compensation |
| Retrying effectful commands without duplicate protection | Processes them twice | Idempotency keys and guarded updates |
| Treating all checked as recoverable and unchecked as bugs | Wrong for many APIs | Follow contracts and recovery policies |

## 15. Exercise: contract for transfers between accounts

Design `transfer(fromId, toId, amountVnd)` with these requirements:

1. IDs must be nonblank and distinct; transfer amounts must be positive.
2. Accounts may be missing, locked, or insufficiently funded.
3. On success, debit the source and credit the destination by exactly the amount; combined balances remain unchanged.
4. On rejection, **neither account may change**.
5. Database failures must not be reported as “account not found.”
6. If balances use `long` VND, handle overflow with `Math.addExact` or appropriate representation.
7. For concurrent transfers or queue-delivered duplicate commands, describe transactions, versioning/locking, and idempotency keys.

Specify the contract in a **preconditions/postconditions/invariants/failures** table, choose deliberately between `TransferResult` and typed domain exceptions, and write JUnit tests for success, insufficient funds, locked accounts, negative amounts, overflow, and unchanged balances after failure.

**Self-check:** Can callers distinguish business rejections from infrastructure failures? Can any exception occur after half the state has changed? Does the error contract depend on changeable message text?

**Remember:** Java exceptions provide a mechanism for reporting/propagating failures; **method contracts** define what failures mean, what callers must do, and which invariants objects must preserve. Good APIs document both success and failure paths.
