# Separating queries from state-changing operations in class design (Command–Query Separation)

**Goal:** Distinguish read-only methods (*queries*) from methods that intentionally change state (*commands*); design understandable, testable Java APIs; handle practical exceptions without confusing CQS with CQRS architecture.

## 1. The problem: a question that silently changes something

Consider an inventory-management class:

~~~java
class Inventory {
    private int quantity = 10;

    // Nghe như truy vấn số lượng còn lại nhưng đồng thời trừ kho.
    int getAvailableQuantity(int requested) {
        if (requested > quantity) {
            throw new IllegalArgumentException("Not enough stock");
        }
        quantity -= requested;
        return quantity;
    }
}
~~~

The name `getAvailableQuantity` makes callers expect a read operation. But invoking it changes the available inventory. A UI refresh, logging operation, or test inspecting state could inadvertently reduce stock.

**Command–Query Separation (CQS)** is a method-design principle associated with Bertrand Meyer: an operation should be either **a query that provides information** or **a command that changes something**, with an explicit contract for its effects.

- **Query:** Returns data or a computed result without changing **observable business-domain state**. Examples: `availableQuantity()`, `canReserve(int)`, `balance()`.
- **Command:** Changes state or performs a side effect such as a database write, payment request, or event publication. Examples: `reserve(int)`, `deposit(amount)`, `submitOrder()`.
- **API contracts must explain potential effects:** whether repeat calls are allowed, whether an operation is idempotent, what exceptions it can raise, and what state remains after failure.

The key is not the `get...` prefix or a `void` return type, but **behavioral meaning**. A `void calculate()` method could be a poorly designed query that discards its computation. Conversely, `createOrder()` commonly needs to return the new order ID even though it is a command. CQS is **a design guideline**, not a syntax restriction.

## 2. Redesigning a small example

The original design combines reading and writing:

~~~java
final class BadStock {
    private int available = 10;

    int checkAndReserve(int units) {
        if (units <= 0 || units > available) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        available -= units;
        return available;
    }
}
~~~

There are two separate business intentions: **checking stock availability** and **actually reserving stock**. Separate them:

~~~java
final class Stock {
    private int available = 10;

    // Query: không làm thay đổi số lượng.
    int availableUnits() {
        return available;
    }

    // Query: có thể hỏi nhiều lần, không tự giữ hàng.
    boolean canReserve(int units) {
        return units > 0 && units <= available;
    }

    // Command: giữ hàng nếu thỏa điều kiện tại thời điểm thực thi.
    void reserve(int units) {
        if (!canReserve(units)) {
            throw new IllegalArgumentException("Not enough stock or invalid units");
        }
        available -= units;
    }
}
~~~

Usage:

~~~java
Stock stock = new Stock();

System.out.println(stock.canReserve(4));   // true
System.out.println(stock.availableUnits()); // 10
stock.reserve(4);                           // Command
System.out.println(stock.availableUnits()); // 6
~~~

**Important:** `canReserve(4)` cannot guarantee `reserve(4)` will subsequently succeed when concurrent threads or transactions access the same inventory. The command must **recheck conditions at write time**. Do not split the system into “query checks availability, then command decrements unconditionally” under concurrency.

## 3. Java 17: account APIs with pure queries and safe commands

The complete example uses `BigDecimal` for money and synchronizes operations on one object so checking and changing a balance are atomic within **one process**. All amounts are treated as one currency unit; real financial systems must model currency, scale, and rounding policies.

**File `AccountDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record AccountSnapshot(BigDecimal balance, List<String> movements) {
    AccountSnapshot {
        Objects.requireNonNull(balance, "balance");
        movements = List.copyOf(Objects.requireNonNull(movements, "movements"));
    }
}

final class Account {
    private BigDecimal balance = BigDecimal.ZERO;
    private final List<String> movements = new ArrayList<>();

    // Query: trả về giá trị bất biến; không sửa trạng thái.
    synchronized BigDecimal balance() {
        return balance;
    }

    // Query: không lộ danh sách có thể sửa của lớp.
    synchronized AccountSnapshot snapshot() {
        return new AccountSnapshot(balance, movements);
    }

    // Query: không tự động trừ tiền.
    synchronized boolean canWithdraw(BigDecimal amount) {
        return amount != null
                && amount.signum() > 0
                && balance.compareTo(amount) >= 0;
    }

    // Command: ghi nhận khoản tiền vào.
    synchronized void deposit(BigDecimal amount) {
        requirePositive(amount);
        balance = balance.add(amount);
        movements.add("DEPOSIT " + amount.toPlainString());
    }

    // Command: kiểm tra lại điều kiện ngay trong vùng đồng bộ.
    synchronized void withdraw(BigDecimal amount) {
        requirePositive(amount);
        if (balance.compareTo(amount) < 0) {
            throw new IllegalStateException("Insufficient balance");
        }
        balance = balance.subtract(amount);
        movements.add("WITHDRAW " + amount.toPlainString());
    }

    private static void requirePositive(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
    }
}

public class AccountDemo {
    public static void main(String[] args) {
        Account account = new Account();

        account.deposit(new BigDecimal("100.00"));
        System.out.println(account.canWithdraw(new BigDecimal("40.00"))); // true
        System.out.println(account.balance()); // 100.00

        account.withdraw(new BigDecimal("40.00"));
        AccountSnapshot result = account.snapshot();
        System.out.println(result.balance()); // 60.00
        System.out.println(result.movements());
        // [DEPOSIT 100.00, WITHDRAW 40.00]
    }
}
~~~

Compile and run:

~~~bash
javac AccountDemo.java
java AccountDemo
~~~

**Why is CQS explicit in this design?**

| Method | Role | Return value | Changes business state? |
|---|---|---|---|
| `balance()` | Query | `BigDecimal` | No |
| `snapshot()` | Query | Immutable `AccountSnapshot` | No |
| `canWithdraw(amount)` | Query | `boolean` | No |
| `deposit(amount)` | Command | `void` | Yes: balance and history |
| `withdraw(amount)` | Command | `void` | Yes: balance and history |
| `requirePositive(amount)` | Internal validation helper | `void` or exception | No |

`AccountSnapshot` uses `List.copyOf` to create an unmodifiable collection snapshot. `BigDecimal` and `String` are immutable too. If a snapshot contains nested mutable objects, `List.copyOf` **does not** make those nested objects immutable.

`synchronized` coordinates operations on **the same Account object in one JVM**. It does not solve concurrent updates to one database account across multiple service instances; real applications need transactions, locks or optimistic locking, and concurrency control in persistence.

## 4. Visualizing reading and writing flows

~~~mermaid
flowchart TD
    Client[Ứng dụng/UI] --> Q[Query: snapshot / balance]
    Q --> S[(Trạng thái hiện tại)]
    S --> R[Trả dữ liệu, không sửa trạng thái]
    Client --> C[Command: deposit / withdraw]
    C --> V{Điều kiện hợp lệ?}
    V -->|Không| E[Trả lỗi, không thay đổi số dư]
    V -->|Có| U[Cập nhật số dư và lịch sử]
    U --> S
~~~

The UI can invoke queries repeatedly to display data without modifying an account. Commands express **an intent to take action** from a user or use case. If the UI retries a command, that is not automatically safe: consider idempotency.

## 5. CQS versus CQRS: related but different

**CQS** is a principle for **method/API design**, often applied within an OOP class. **CQRS** (*Command Query Responsibility Segregation*) is an **architectural approach** that separates command and query processing paths, sometimes with separate data models or stores.

| Aspect | CQS | CQRS |
|---|---|---|
| Level | Methods, classes, interfaces, APIs | Application/system/architecture |
| Question | Does this method read or change state? | Should reads and writes use separate models/components? |
| Must databases be split? | No | No; separate handlers may share one database |
| Goal | Predictable, usable, testable APIs | Independent read/write models based on business needs, scaling, and performance |
| Example | `account.balance()` / `account.withdraw(x)` | `WithdrawCommandHandler` / `AccountBalanceQueryHandler` |
| Cost | Usually low | Can be high: extra mapping, synchronization, eventual consistency |

An application with good CQS **does not need** CQRS. When CQRS read models update asynchronously, reads may **lag** behind successful commands; consistency requirements must be specified. CQS on one object does not inherently introduce that lag.

~~~mermaid
flowchart LR
    UI[Client] --> Query[Query API]
    UI --> Command[Command API]
    Query --> Read[(Read model)]
    Command --> Write[(Write model)]
    Write -. cập nhật/projection .-> Read
~~~

The diagram illustrates **one CQRS architecture with separate read and write models**, not a requirement for following CQS.

## 6. What counts as “not changing state”?

An ideal query has no **observable side effects** in the domain. Distinguish these cases:

1. **Business-state mutation:** `getBalance()` increments fees or `findOrder()` marks an order delivered → violates query expectations; use a clearly named command.
2. **Logs, metrics, tracing:** observability may record technical data without changing business results. Be transparent, especially for audit logs and privacy.
3. **Caching/memoization:** a getter that computes and stores a cache on first access changes internal state as an optimization. Pragmatic CQS can allow this when **observable behavior stays the same** and control flow, concurrency, and idempotency are unaffected; never hide a business command behind a cache.
4. **ORM lazy loading:** accessing a JPA entity getter may trigger SQL SELECT, network I/O, or an exception if the session is closed. Although it does not intentionally modify business data, it is no longer “pure” in the no-I/O sense. Understand persistence boundaries; do not assume all getters are cheap or safe after a transaction.
5. **Read counters or `lastSeen` updates:** when these change domain state, model them as separate commands or clearly named use cases that expose both reading and writing; do not hide them in `get...`.
6. **File reads or API calls:** these may be queries by intent when gathering information, yet they can time out or fail. “Does not change domain state” does not mean “never performs I/O.”

Repeated queries over the same data with no intervening changes should yield consistent contractual results. They need not return **the same object identity**, especially when producing fresh snapshots.

## 7. Must commands return void?

No. Classify operations by their **effects**, not just their return types.

For example, `createOrder(request)` persists a new order and returns an `OrderId`. It is still a **command**:

~~~java
record OrderId(String value) {}

interface OrderCommands {
    OrderId createOrder(CreateOrderRequest request); // Có hiệu ứng ghi
}

interface OrderQueries {
    OrderView findById(OrderId id);     // Chỉ trả dữ liệu
}
~~~

Returning an `OrderId`, success status, or new version is a valid way to report a command's outcome. However, avoid having a method silently write data and then return a complex collection while pretending to be a query. If business logic needs a newly calculated value after a write, consider returning an ID/version from the command and offering a separate query when that is useful. Do not split APIs merely to enforce “void-only commands” if this forces callers to make needless extra calls.

A useful naming convention:

- `get`, `find`, `list`, `calculate`, `can` → favor clear queries.
- `create`, `update`, `reserve`, `pay`, `withdraw`, `cancel` → clearly indicate commands.
- `getAndReset`, `readAndMarkSeen`, `checkAndReserve` → consider splitting responsibilities or renaming/documenting effects explicitly.

Names are only clues. Actual behavior depends on business rules, transactions, error handling, and permissions.

## 8. Avoid non-atomic check-then-act operations (TOCTOU)

Separating queries and commands is useful, but errors arise when callers assume a query result “locks” state:

~~~java
if (inventory.canReserve(2)) {
    inventory.reserve(2); // Một caller khác có thể đã giữ hàng trước đó.
}
~~~

This is **time-of-check to time-of-use (TOCTOU)**. To prevent it:

- The `canReserve` query helps the UI display only **temporary availability**; it cannot guarantee success.
- The `reserve` command must recheck the condition **inside the same protected update operation**.
- Within one JVM, `synchronized` or a suitable lock can combine the check and write.
- With a database, use a conditional update in a transaction or version-based/optimistic locking. For example, use `WHERE available >= :qty` and check the number of affected rows. An earlier `SELECT` alone does not prove that the condition still holds.
- Across services, define the consistency boundary where inventory is actually owned, rather than locking an object in just one application instance.

CQS separates **the intent to read** from **the intent to change**; atomicity is a separate requirement for commands.

## 9. Command idempotency and safe retries

**Queries have no business side effects**, but commands can. A command is not automatically idempotent:

- `setStatus("PAID")` is usually idempotent if repeating it creates no additional effects.
- Calling `deposit(100)` twice increases the balance twice: **not idempotent**.
- Repeating `sendEmail()` may send another email even when the data is unchanged.

When a client retries after a timeout, use an **idempotency key** linked to the transaction intent. For example, an API accepts a unique `requestId` and records the completed request so retries do not repeat its effects.

~~~text
POST /payments
Idempotency-Key: pay-req-8f9...
Body: {"orderId":"O-101","amountCents":50000}
~~~

To guarantee this across instances, key lookup/insertion and data changes must be atomic in suitable persistent storage; a single in-memory `HashSet<String>` does not ensure safety across processes or restarts.

## 10. Testing CQS through observable behavior

Using `AccountDemo.java` from section 3, create **`AccountTest.java`** with JUnit Jupiter 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class AccountTest {
    @Test
    void queriesDoNotChangeBalanceOrMovements() {
        Account account = new Account();
        account.deposit(new BigDecimal("100.00"));

        AccountSnapshot before = account.snapshot();

        assertTrue(account.canWithdraw(new BigDecimal("40.00")));
        assertEquals(0, new BigDecimal("100.00").compareTo(account.balance()));
        assertEquals(before, account.snapshot()); // Cùng giá trị quan sát được
    }

    @Test
    void commandsChangeStateAndPreserveInvariant() {
        Account account = new Account();
        account.deposit(new BigDecimal("100.00"));
        account.withdraw(new BigDecimal("40.00"));

        assertEquals(0, new BigDecimal("60.00").compareTo(account.balance()));
        assertEquals(2, account.snapshot().movements().size());

        AccountSnapshot beforeError = account.snapshot();
        assertThrows(IllegalStateException.class,
                () -> account.withdraw(new BigDecimal("100.00")));
        assertEquals(beforeError, account.snapshot());
    }

    @Test
    void snapshotCannotBeMutatedFromOutside() {
        Account account = new Account();
        account.deposit(BigDecimal.ONE);

        assertThrows(UnsupportedOperationException.class,
                () -> account.snapshot().movements().clear());
        assertEquals(1, account.snapshot().movements().size());
    }
}
~~~

These tests confirm that queries do not alter business state, commands preserve invariants on success and failure, and snapshots do not expose mutable collections. They **do not** verify database durability, distributed guarantees, or real payment effects. Those require appropriate integration tests.

There is no need to use reflection to count methods with a `get` prefix or inspect whether return types are `void`; neither proves a read/write contract.

## 11. Refactoring methods that mix queries and commands

~~~mermaid
flowchart TD
    A[Nhận diện method vừa đọc vừa thay đổi] --> B[Liệt kê kết quả và side effect]
    B --> C[Thiết kế query không thay đổi domain]
    C --> D[Thiết kế command thể hiện ý định ghi]
    D --> E[Cập nhật callers và hợp đồng lỗi]
    E --> F[Đảm bảo validation và ghi atomic]
    F --> G[Kiểm thử kết quả, rollback và retry]
~~~

Follow this sequence:

1. **Find genuinely suspicious methods:** `getAndDelete`, `fetchAndMarkRead`, `calculateAndSave`, `checkAndReserve`, getters with hidden setters, or queries that publish notifications.
2. **Identify side effects that must be preserved:** field changes, database writes, business caches, events, emails, transactions; also list current return values and exceptions.
3. **Clarify the use case:** is the user inspecting state or requesting a change? Both may justify separate APIs.
4. **Create a read-only query contract:** return snapshots/DTOs/value objects when necessary to stop callers from mutating state through returned references.
5. **Create a command that names the change:** validate inputs and enforce invariants at write time; choose a useful return value.
6. **Migrate callers:** remove dependencies on hidden getter side effects; public APIs may require deprecation and migration.
7. **Review transactions, concurrency, and retries:** prevent unlocked check-then-write sequences and add idempotency when needed.
8. **Test:** ensure queries cause no unexpected changes, commands handle success/failure consistently, and integration tests verify real effects.

**Example refactoring decision:** `MessageService.fetchAndMarkRead(id)` can become `findById(id)` and `markRead(id)` if the UI needs both previewing without marking read and explicitly marking read. If the business rule says “opening a message marks it as read,” keep an explicit **use-case command** `openMessage(id)` that returns content and documents its effects, rather than hiding them behind `getMessage`.

## 12. Common mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Getter writes business data | Refreshing the UI may cause unintended changes | Separate queries from commands or use names/contracts that disclose side effects |
| Assuming commands must return `void` | Awkward APIs and unnecessary queries for IDs/versions | Return necessary metadata from commands while keeping their identity as commands |
| Confusing CQS with CQRS | Adds architectural complexity to a simple problem | Distinguish method-level and architectural separation |
| Query returns an internal mutable `List` directly | Callers can mutate state without commands | Return a suitable snapshot or immutable view |
| Only checks a condition in an earlier query | TOCTOU/race condition | Have the command check and write atomically where the data is owned |
| Treating internal caching as a business mutation | Harmless optimizations are prohibited mechanically | Define observable state and permissible side effects precisely |
| Retrying non-idempotent commands | Repeats charges or writes | Use idempotency keys and appropriate transactions |
| Splitting every API excessively | Adds round trips and complexity | Split only where it provides real value |

## 13. Applied exercise

A library system has:

~~~java
BookView borrowAndGetBook(String bookId, String memberId);
~~~

The method decrements available copies, creates a loan receipt, and returns data for displaying the book.

Identify the actual requirements and redesign it:

- `BookView findBook(String bookId)` only reads metadata and available quantities at query time.
- `BorrowReceipt borrowBook(String bookId, String memberId, String requestId)` is a command that checks borrowing rights and inventory, then records the loan in a transaction. It can return a receipt for immediate use.
- If the UI needs the latest state after borrowing, it can query again; with optimistic updates, handle loan rejection due to competing requests.
- If the client retries, ensure `requestId` does not create duplicate loans.

**Self-check questions:** Can a caller tell which method changes the system? Are queries safe to repeat? Do commands enforce invariants at write time? Does the API specify failure states and effects on external systems?

---

**Remember:** Design methods so a question **does not secretly change business state**, while a command **clearly conveys the intent to change it**. Proper separation makes APIs predictable, but atomicity, consistency, and safe retries must still be enforced for commands with side effects.
