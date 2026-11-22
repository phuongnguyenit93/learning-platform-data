# Separating Query Methods and State-Changing Methods in Java

When designing a Java class, a method can **ask what state an object is in** or **instruct the object to do something that causes its state to change**. Proactively separating these two intents makes the API easier to read, easier to test, and avoids unexpected changes when others only intend to view information.

This principle is commonly called **Command–Query Separation (CQS)**: a method should serve either as a **query** (querying and returning information without changing observable state) or as a **command** (performing a change/action, and in the strict version, typically not returning result data). This is a **design principle**, not a syntax feature or a rule enforced by the Java compiler. In practice, there are reasonable exceptions, especially for atomic operations, reporting the result of an action, or existing standard APIs.

This lesson applies to Java 17+, focusing on **the design of methods within a class and their contracts**, without yet needing multi-layered application models or database infrastructure.

## 1. Queries and Commands Answer Two Different Questions

- **Query:** “What is the current state?” For example, `account.getBalance()`, `cart.itemCount()`, or `student.isActive()`. Calling a query must not silently modify the object's business data.
- **Command:** “Change the state according to this rule.” For example, `account.deposit(amount)`, `cart.addItem(item)`, or `student.activate()`. A command checks conditions, performs a valid change, or reports an error clearly.

Example of a simple counter class:

~~~java
class Counter {
    private int count;

    int current() {    // query
        return count;
    }

    void increment() { // command
        count++;
    }

    void reset() {     // command
        count = 0;
    }
}
~~~

This snippet illustrates a class declaration and does not yet have a `main` method to run on its own. `current()` returns the value of the field without writing to any field. `increment()` and `reset()` express the intent to modify data right in their names.

| Criterion | Query | Command |
| --- | --- | --- |
| Purpose | Observe or compute information | Change state or request an action |
| Examples | `getBalance()`, `size()`, `isEmpty()` | `deposit()`, `add()`, `clear()` |
| Effect on business state | Does not change observable state according to its contract | May change state; may also reject the operation |
| Return value | Usually returns data | In strict CQS, usually `void` |
| Repeated calls without intervening updates | Logical result usually remains the same, unless dependent on the external environment | May perform the action multiple times |
| Common design mistake | A getter that both reads and updates | A command that implicitly returns data and hides other updates |

**Do not infer from the return type alone:** a `void print()` method still has an I/O side effect; an `int getAndIncrement()` method both returns a number and modifies a field. Queries and commands are classified by **behavior/contract**, not merely by name or `void`.

**Do not equate CQS with absolute purity:** a query can create a new result object or perform local computations while still not modifying business state. For queries that depend on a clock, external data, or concurrency, the result can also change between two calls even though the query itself performs no update.

## 2. Why Separate the Two Types of Methods?

### 2.1. Reducing Unexpected Side Effects

Consider the following design:

~~~java
class BadScore {
    private int points;

    int getPoints() {
        points++;       // Violates expectations: only asks yet modifies state
        return points;
    }
}
~~~

This declaration illustrates a **query mixed with a command**. A reader might use `getPoints()` multiple times to display the UI or write logs, inadvertently increasing the score each time. Debugging becomes difficult because “reading data” causes changes.

A design with clearer intent:

~~~java
class Score {
    private int points;

    int getPoints() {
        return points;  // Query: read-only
    }

    void awardPoint() {
        points++;       // Command: modifies state
    }
}
~~~

Calling `awardPoint()` signals to the user that the action may change the score, whereas `getPoints()` can be called to observe it without increasing the score.

### 2.2. Easier to Write Tests

For a query, you can check the returned result and assert that the state before and after remains unchanged. For a command, you can test a valid change, the invariant after the change, and that invalid input cases do not leave behind a partially updated state.

### 2.3. Clear Contracts When Expanding a Class

When multiple methods both “read and silently modify,” calling code has a hard time knowing the order of effects. Separation helps define preconditions and postconditions: call a query to obtain information, and call a command when you genuinely intend to make a change. This supports *encapsulation* and reduces dependence on internal field details.

## 3. Complete Example: A Wallet with Queries, Commands, and Snapshots

Create a wallet that stores its balance as a **`long` in the smallest unit** (for example, dong if appropriate for the model), avoiding `double` for a monetary amount that requires exact calculation. The constructor establishes the “non-negative balance” invariant, queries are read-only, and commands must validate before mutating.

Save the following snippet as the file **`WalletCqsDemo.java`**:

~~~java
public class WalletCqsDemo {
    record WalletSnapshot(
            String owner,
            long balanceCents,
            int transactionCount) {
    }

    static final class Wallet {
        private final String owner;
        private long balanceCents;
        private int transactionCount;

        Wallet(String owner, long openingBalanceCents) {
            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException("Chủ ví không hợp lệ");
            }
            if (openingBalanceCents < 0) {
                throw new IllegalArgumentException("Số dư âm");
            }
            this.owner = owner;
            this.balanceCents = openingBalanceCents;
        }

        String getOwner() {
            return owner;                       // query
        }

        long getBalanceCents() {
            return balanceCents;                // query
        }

        int getTransactionCount() {
            return transactionCount;            // query
        }

        WalletSnapshot snapshot() {
            return new WalletSnapshot(
                    owner, balanceCents, transactionCount); // query
        }

        void deposit(long cents) {               // command
            if (cents <= 0) {
                throw new IllegalArgumentException("Số tiền phải dương");
            }

            long nextBalance = Math.addExact(balanceCents, cents);
            int nextCount = Math.incrementExact(transactionCount);
            balanceCents = nextBalance;
            transactionCount = nextCount;
        }

        void withdraw(long cents) {              // command
            if (cents <= 0) {
                throw new IllegalArgumentException("Số tiền phải dương");
            }
            if (cents > balanceCents) {
                throw new IllegalStateException("Không đủ số dư");
            }

            int nextCount = Math.incrementExact(transactionCount);
            balanceCents -= cents;
            transactionCount = nextCount;
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet("Lan", 1_000);
        WalletSnapshot before = wallet.snapshot();

        System.out.println("Chủ ví: " + wallet.getOwner());
        wallet.deposit(500);
        wallet.withdraw(200);

        System.out.println("Ảnh chụp ban đầu: "
                + before.balanceCents());
        System.out.println("Số dư hiện tại: "
                + wallet.getBalanceCents());
        System.out.println("Số giao dịch: "
                + wallet.getTransactionCount());

        long firstRead = wallet.getBalanceCents();
        long secondRead = wallet.getBalanceCents();
        System.out.println("Hai lần truy vấn: "
                + firstRead + ", " + secondRead);

        try {
            wallet.withdraw(2_000);
        } catch (IllegalStateException ex) {
            System.out.println("Rút lỗi: " + ex.getMessage());
        }

        System.out.println("Sau rút lỗi: "
                + wallet.getBalanceCents());
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 WalletCqsDemo.java
java WalletCqsDemo
~~~

**Exact stdout:**

~~~text
Chủ ví: Lan
Ảnh chụp ban đầu: 1000
Số dư hiện tại: 1300
Số giao dịch: 2
Hai lần truy vấn: 1300, 1300
Rút lỗi: Không đủ số dư
Sau rút lỗi: 1300
~~~

How to read the output:

1. The constructor creates the wallet with `1_000` units and a default transaction count of `0`. The two data fields are modified only through the commands designed for them.
2. `snapshot()` creates a **structurally immutable record in this example** with a balance of `1000`. Afterward, the wallet changes; the `before` variable still holds the old number. Creating a new return value **does not mean modifying the wallet's state**.
3. `deposit(500)` computes the new balance beforehand using `Math.addExact`, then increments the transaction count; `withdraw(200)` checks for sufficient balance before subtracting. The final balance is `1000 + 500 - 200 = 1300`.
4. The two calls to `getBalanceCents()` do not write any data, so they both receive `1300` when no commands occur in between and the wallet is not modified by another thread.
5. `withdraw(2000)` is rejected **before modifying any field** because the amount exceeds the balance. The error is signaled with `IllegalStateException`; the balance remains `1300`, and the transaction count remains `2`.

Using `Math.addExact` and `Math.incrementExact` detects arithmetic overflow instead of silently writing an incorrect value. In the example, the new values are computed before assigning fields to avoid partial updates if the computation throws `ArithmeticException`. The example is designed for **a single thread or synchronization elsewhere**; two concurrent commands called on the same `Wallet` still carry a race risk if synchronization is not added.

**Key design note:** `getBalanceCents()`, `getTransactionCount()`, and `snapshot()` are all queries. `deposit()` and `withdraw()` are commands. The constructor establishes the initial state, but is not a query/command method called on an existing object.

## 4. Must a Command Always Return `void`?

The strict version of CQS recommends:

- Queries return data and do not change observable state.
- Commands perform an action without combining it with asking for and returning business data; in Java, they are typically written with `void` and represent failure using an appropriate exception.

However, **Java does not forbid commands from returning a result**. Many standard library APIs combine mutation and returning information:

~~~java
// Examples used inside a method that already has the corresponding objects:
boolean removed = list.remove("A");       // modifies the list, returns the result
String previous = map.put("id", "new");    // modifies the map, returns the previous value
int old = atomicInteger.getAndIncrement(); // atomically increments, returns the previous value
~~~

These are illustrative snippets, not a standalone program; variables `list`, `map`, and `atomicInteger` of appropriate types are required. These methods intentionally combine a change and a result into **a single logical operation**, which is sometimes necessary to avoid race conditions or to provide a convenient API.

If the business requirement is “try to make a reservation, then indicate whether it succeeded,” a `boolean tryReserve()` method can be a reasonable API even though it does not follow strict CQS. When taking a pragmatic approach, choose names that clearly reveal the action (`tryReserve`, `remove`, `getAndIncrement`) and document the result and side-effect contract.

**Do not mechanically split every combined operation into two calls** if doing so breaks atomicity. For example, replacing `getAndIncrement()` with `get()` followed by `incrementAndGet()` from two different threads no longer guarantees that reading the old value and incrementing happen as a single, uninterrupted action.

## 5. Getters Are Not Always True Queries

The name `get...` usually suggests a read operation, but you must inspect **the method body and observable effects**.

### 5.1. A Getter That Silently Modifies a Field

~~~java
class BadSequence {
    private int nextId = 1;

    int getNextId() {
        return nextId++; // returns the number and modifies state
    }
}
~~~

This is not a pure query. Clearer names would be `allocateId()` or `getAndIncrementId()` to convey the action of **consuming** an ID. If you need only to view the expected next number, add a separate query `peekNextId()` that does not modify the field, while the ID-allocating command can return the result as a pragmatic exception.

### 5.2. A Getter Returning a Mutable Reference Directly

Suppose a class internally holds a mutable list:

~~~java
import java.util.ArrayList;
import java.util.List;

class UnsafePlaylist {
    private final List<String> songs = new ArrayList<>();

    List<String> getSongs() {
        return songs; // caller can modify it directly!
    }
}
~~~

The `getSongs()` method itself does not write to any field, but the caller receives **a reference to the internal collection itself** and can call `getSongs().clear()`, bypassing the checks in the class's commands. If a command is supposed to maintain an invariant, this is a way that encapsulation gets broken.

For a list of immutable `String` elements, a clearer design is:

~~~java
import java.util.ArrayList;
import java.util.List;

class Playlist {
    private final List<String> songs = new ArrayList<>();

    List<String> getSongs() {
        return List.copyOf(songs); // query returning an unmodifiable snapshot
    }

    void addSong(String song) {
        if (song == null || song.isBlank()) {
            throw new IllegalArgumentException("Tên bài hát trống");
        }
        songs.add(song); // command
    }
}
~~~

Both are **declaration snippets for learning**, not yet programs with a `main` method. `List.copyOf` produces a result that cannot be modified through list-mutating APIs and cannot contain `null`. With immutable `String` elements, this is a suitable snapshot. For collections containing mutable objects, `List.copyOf` only performs a **shallow** copy of the list structure and does not automatically make each element immutable.

`Collections.unmodifiableList(songs)` provides a **view that disallows modification through the view**, but it can reflect subsequent changes to the backing list; it is not equivalent to a fixed snapshot. Choose according to the desired API contract.

### 5.3. Is a Getter That Performs a Calculation Considered a Query?

Yes, as long as it does not change observable business state:

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    long area() {
        return (long) width * height; // query that computes a value
    }
}
~~~

`area()` performs multiplication and a type cast without writing to any field; it is still a query. Using `long` for the result prevents `int * int` multiplication from overflowing within the range representable by this `long` multiplication.

## 6. Must a Query Have Absolutely Zero Side Effects?

CQS aims to **avoid changing the observable state of the object or business contract** when asking for information. In real systems, the boundary of a “side effect” can be subtle:

- **Allocating temporary objects and computing the return value:** generally allowed in a query; this does not change business state.
- **Logging and updating metrics:** these are technical side effects. They may be acceptable under the system contract, but if a metric or log has clear observable significance, the query is no longer “free of any side effects whatsoever” in the strict sense.
- **Lazy caching/memoization:** a getter that computes and stores a cached value changes implementation state. If this change is completely transparent to the caller, some designs still treat the getter as a query from a business perspective; special care is needed for thread safety, invalidation, errors, and computation cost.
- **Reading a clock, file, or database:** may not modify the object itself, yet returns results that vary with time or external state. You should not promise that a query always returns the exact same value at all times.
- **Calling an external service with effects:** if a method named `get...` triggers a payment request or updates a database, it clearly violates the expectations of a query API.

When an API requires strict guarantees (for example, in testing or transactions), **explicitly document the contract**: which state remains unchanged, where data comes from, and whether querying can throw exceptions or perform I/O.

## 7. Designing Commands to Preserve Invariants

An *invariant* is a condition that an object must satisfy whenever it is in a valid state. In the wallet example, the invariant is `balanceCents >= 0`. Commands must protect the invariant during validation and updates.

An example of **what not to do**:

~~~java
class UnsafeWallet {
    private long balance;

    long getBalance() {
        return balance;
    }

    void setBalance(long newBalance) {
        balance = newBalance; // caller can assign a negative number
    }
}
~~~

This is an illustrative snippet. The setter exposes arbitrary mutation; the name `setBalance` does not express the business operation. Consider replacing it with meaningful commands such as `deposit(cents)` and `withdraw(cents)`, with each command managing appropriate validation.

A well-designed command typically has three clear phases:

1. **Validate:** input conditions, operation permissions, current state, and invariants.
2. **Compute:** prepare the new values; operations that can fail should be performed before assignments that cannot be rolled back, whenever feasible.
3. **Apply:** update the state within an appropriate synchronization/transaction boundary; do not leave the object in a partially updated state.

If a command fails, the contract should specify whether state may have been partially modified or is guaranteed to remain unchanged. In the `Wallet` example, validation and overflow checks are performed before assignment; in applications involving multiple external systems, rollback guarantees also depend on transactions and infrastructure.

**Not every command necessarily changes the state to something different.** For example, calling `activate()` on an already active object may be defined as idempotent, modifying nothing when the target state has already been reached. It is still a command because its intent is to request transitioning/setting the state.

## 8. Returning Values from Commands: Writing Clear Contracts

For real-world Java APIs, there are three common styles:

| Style | Example | Characteristics |
| --- | --- | --- |
| Strict CQS | `void withdraw(long amount)` | Mutating command; separate query to read the balance |
| Command returning execution status | `boolean tryWithdraw(long amount)` | A single action combining a success/failure outcome |
| Command returning a result object | `WithdrawalResult withdraw(...)` | Returns a status code, receipt, or transaction details |

The choice depends on the contract, especially atomicity requirements. A command may return **a result value that is not a pre-existing query**, such as an ID generated upon creation, if this is the only way to avoid losing correctness when multiple threads compete.

If you choose strict CQS, failures can be signaled with an appropriate exception; however, you should not turn exceptions into routine control flow when the business domain treats rejection as an expected and frequent outcome. In such cases, `try...` or a structured result type is easier to understand.

Do not name a method `getOrCreateSession()` and treat it as a query: a “get or create” method **can create a session**. The name `findOrCreate...` at least signals the possibility of mutation, though if strict CQS is needed, you should separate the query `findSession` and the command `createSession`, provided that the race between finding and creating is still handled.

## 9. Thread Safety: Separating Two Methods Does Not Replace Synchronization

CQS makes intent clear, **but it does not solve concurrency issues on its own**. With a `Wallet` used by multiple threads, `getBalanceCents()` and `withdraw()` can run concurrently; without synchronization, reads and writes can cause race/visibility issues and invariants can be broken.

A simple version that protects the counter with the same monitor:

~~~java
class SynchronizedCounter {
    private int count;

    synchronized int current() { // synchronized query
        return count;
    }

    synchronized void increment() { // synchronized command
        count++;
    }
}
~~~

This is an illustrative declaration snippet. `synchronized` protects access when **all** related operations go through the appropriate monitor. The query remains a query because it does not modify count.

However, **two separate calls still do not form a compound atomic operation**:

~~~java
// Not sufficient to guarantee that "if count < 10 then increment" is atomic:
if (counter.current() < 10) {
    counter.increment();
}
~~~

Suppose two threads both read `9`; both may decide to increment, and the total becomes `11`. To preserve the “do not exceed 10” invariant, put **check + update** into the same synchronized command:

~~~java
class BoundedCounter {
    private int count;

    synchronized int current() {
        return count; // query
    }

    synchronized void incrementIfBelowTen() {
        if (count < 10) {
            count++;
        }
    }
}
~~~

This snippet is also illustrative. The command method protects the upper-bound condition because no other thread can interleave between the check and the update when all accesses follow the same lock.

**Practical rule:** a query can help the UI **display** state, but do not use a stale query result as proof that a future command will definitely be valid in a concurrent environment. The command must **re-check** the condition within the appropriate synchronization or transaction boundary.

## 10. Queries Can Depend on State Outside the Object

In some cases, a query is not completely determined by instance fields alone:

~~~java
import java.time.Clock;
import java.time.Instant;

class Deadline {
    private final Instant expiresAt;
    private final Clock clock;

    Deadline(Instant expiresAt, Clock clock) {
        this.expiresAt = expiresAt;
        this.clock = clock;
    }

    boolean isExpired() {
        return !Instant.now(clock).isBefore(expiresAt);
    }
}
~~~

This is a declaration snippet without `main`. `isExpired()` **does not change the state of `Deadline`**, so it fits the query role, even though its result can change from `false` to `true` as time passes. Injecting `Clock` lets tests control time without manipulating the system clock.

Similarly, a query reading a database table can return new results after someone else updates the table, even though the query itself performs no modification. The query/command classification is about **the intent and effect of the call itself**, not a promise that “every call will forever return the same result.”

## 11. How Does CQS Differ from CQRS?

**CQS** (*Command–Query Separation*) is a principle at the **method/API** level: a method should be responsible for reading **or** changing state.

**CQRS** (*Command Query Responsibility Segregation*) is an **architectural pattern** that separates the command-handling path from the query-handling path (typically at the application, service, or system layer). A CQRS system may have separate read/write models, but it is **not mandatory** for every project to use two databases or event sourcing.

| Characteristic | CQS | CQRS |
| --- | --- | --- |
| Scope of application | Method, class, API | Application architecture, read/write processing flows |
| Goal | Clear method contracts and side effects | Optimize read/write models and responsibilities |
| Separate infrastructure required? | No | Not mandatory; depends on design |
| Event sourcing required? | No | No |
| Example | `getBalance()` vs. `deposit()` | `AccountQueryService` vs. `AccountCommandService` |

In this Java class-object module, master CQS **directly inside a class** first; CQRS is included only as a conceptual distinction to avoid confusing the two names.

## 12. Choosing Method Names That Match Intent

A method's name is the shortest documentation of its side effects. Some suggestions:

| Intent | Illustrative Names | Reason |
| --- | --- | --- |
| Reading a field/property | `getName()`, `balance()` | Callers expect no business state change |
| Boolean query | `isActive()`, `hasItems()` | Expresses a question |
| Computing from state | `calculateTotal()`, `estimatedCost()` | Returns a computed result |
| Searching | `findById()`, `contains()` | Expresses an inquiry |
| Incrementing, decrementing, updating | `increment()`, `rename()`, `deposit()` | Expresses a mutating action |
| Removing or resetting | `removeItem()`, `clear()` | Expresses intent to change state |
| Conditional execution returning a result | `tryReserve()`, `removeIfPresent()` | Callers know this is an action with an outcome |
| Atomic read-and-modify | `getAndIncrement()`, `computeIfAbsent()` | The name proactively indicates the method may mutate state |

Not every method starting with `get` is a query; read **the contract and implementation** to confirm. Conversely, a `calculateTotal()` method that returns the amount from items should not arbitrarily add items, finalize the order, or write a fee into a field.

JavaBeans-style getters and setters have value for certain frameworks, but in a domain model, automatically writing setters for every field often breaks control over invariants. Expose only operations that are valid in the business domain.

## 13. Cases That Require Closer Thought

### 13.1. Updating an Object and Returning `this` for Chaining

~~~java
class MutableBuilder {
    private String value = "";

    MutableBuilder append(String text) {
        value += text;
        return this;
    }
}
~~~

This is an illustrative snippet of a builder-style API; `append()` is a **command with a return value**, because it modifies `value` and returns `this` to enable chained calls. This is an intentional design exception, not a query. In an application requiring strict CQS, you can choose builder commands that return `void` or apply an immutable style that returns a new object under a different contract.

### 13.2. Immutable Objects and “With” Methods

~~~java
record Point(int x, int y) {
    Point movedBy(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}
~~~

`movedBy()` **does not modify** the current `Point`; it returns another instance. For an immutable value object, this method can be viewed as a computation/query that produces a new value even though its name suggests a move action. What matters is the “does not mutate the receiver” contract; calling code should know to keep the returned result if it wants to use the new point.

### 13.3. Queries Returning Reference Values

If a query returns `List<OrderItem>` and the `OrderItem` objects are mutable, even with `List.copyOf`, the recipient can still modify the state of the shared elements. When designing a query that must not allow callers to interfere with internal data, consider returning an **immutable DTO/record snapshot**, an appropriate deep copy, or read-only APIs with a clear contract. “The method does not assign to any field” is not enough to guarantee encapsulation if it exposes mutable child objects.

### 13.4. Events and Notifications

If the command `rename("New")` emits a domain event, the event is the result of a state change and typically fits the command's responsibility. By contrast, a query `getName()` that silently sends an email or triggers an external update causes major surprises and makes testing difficult. Distinguish purely technical logging/metrics from business effects.

## 14. Testing the CQS Contract

A testing framework is not mandatory in order to reason properly. For a simple object, you can verify:

1. **Queries return the correct values:** the initial state created by the constructor results in `getBalanceCents() == 1000`.
2. **Queries do not change state:** capture the state before; call the query once or multiple times; capture it again and compare the business values.
3. **Commands produce the expected outcome:** after `deposit(500)`, the balance increases accurately once; `getTransactionCount()` increases by one.
4. **Commands reject invalid input:** passing a negative amount or requesting a withdrawal exceeding the balance must fail according to the contract; the state remains unchanged if that is a design guarantee.
5. **No mutable state leakage:** modifying a collection or object returned from a query must not break the object's invariants if the API promises read-only data.
6. **Concurrency:** if the object is shared across threads, there must be tests and reasoning based on the synchronization protocol; simply running it many times without “seeing an error yet” is not sufficient proof of thread safety.

Consider the following manual check example (a snippet inside a method that has a `wallet` object from the `WalletCqsDemo` example):

~~~java
long before = wallet.getBalanceCents();

wallet.getOwner();
wallet.snapshot();
wallet.getTransactionCount();

long after = wallet.getBalanceCents();
System.out.println(before == after); // true if there are no intervening updates
~~~

These queries are designed to be read-only, so in a single-threaded context the comparison result is `true`. You should not use the `before == after` condition alone as proof against **all** kinds of side effects: for example, a method could temporarily modify and then restore a field, write logs, or mutate a child object that comparing only the balance does not detect.

## 15. Common Mistakes and How to Fix Them

1. **A getter increments a counter on every call:** `getVisits()` executes `visits++`. Separate `registerVisit()` (command) and `getVisits()` (query).
2. **Reading a list via a getter and mutating it through the returned result:** `cart.getItems().clear()` breaks encapsulation. Provide only an appropriate view or snapshot; create `clearCart()` with validation if clearing the cart is a business action.
3. **Giving every field an arbitrary setter:** this can produce invalid states. Replace them with commands corresponding to permitted actions.
4. **Assuming no side effects based on the `get` prefix:** methods like `getOrCreate...` or `getAndIncrement...` imply mutation. Read the contract and choose clear names.
5. **Splitting an atomic operation into a query followed by a command:** for example, checking the balance and then withdrawing in two separate calls across multiple threads. Put the check and the update inside the same transaction/lock.
6. **Assuming a command must always return `void`:** many sound APIs need to return a result code, a new version, or the pre-update value. Treat CQS as a guiding principle and choose exceptions with clear justification.
7. **Queries writing data for “convenience” on later calls:** memoization/lazy initialization can be appropriate, but require a clear contract, consistency, and synchronization. Avoid caching that causes successive queries to unexpectedly change semantics or fail differently.
8. **Forgetting failure behavior:** a command that throws an exception after already modifying some fields can leave the object in an invalid state. Compute/validate first and apply updates atomically when required.
9. **Confusing CQS with CQRS:** CQS is about method design; CQRS refers to separating responsibilities in system architecture and does not automatically require microservices or two databases.
10. **Assuming a query always returns the same value:** state can be modified between calls, or an external data source can change. CQS does not eliminate variation caused by time or other actors.

## 16. Self-Check

**Question 1.** Why is `int getBalanceAndChargeFee()` a name that raises concern when considering CQS?

**Answer:** The name indicates that the method both reads the balance and charges a fee (modifying state). If a caller only wants to read the balance, charging a fee is an unexpected side effect. You should separate the balance-reading query and the fee-charging command, or use a clear name and contract if a combined operation is required.

**Question 2.** Is a getter that does not assign to any field, yet returns an internal `ArrayList` directly, sufficient to be considered a safe query?

**Answer:** Calling the getter may not mutate state immediately, but the API exposes a mutable reference, allowing callers to bypass commands and break invariants. You should return an appropriate view or snapshot, or design a read-only DTO.

**Question 3.** Is the `void reset()` method a query because it returns no result?

**Answer:** No. `reset()` is a command because its intent is to change state, even though it returns `void`.

**Question 4.** Should you replace `AtomicInteger.getAndIncrement()` with `get()` followed by `incrementAndGet()` just to adhere to strict CQS?

**Answer:** No, not if you need to return the pre-update value atomically. Two separate calls create an opportunity for other threads to interleave; `getAndIncrement()` is an intentionally combined API.

**Question 5.** A `Wallet` object has `getBalanceCents()` and `withdraw(...)`. Why is the logic `if (wallet.getBalanceCents() >= amount) wallet.withdraw(amount)` not sufficient to guarantee correctness in a multithreaded environment?

**Answer:** Another update can occur between the query and the command. The command must re-check the condition itself inside an appropriate synchronization/transaction boundary; the external check should only be used as a display hint.

**Question 6.** Does `Point movedBy(...)` on an immutable record, returning a new `Point`, modify the receiver?

**Answer:** No. It creates a new value and leaves the old object unchanged. The meaning of the method must be made clear to callers so they know to use the returned result if they want the “moved point.”

**Question 7.** Does applying CQS to a class require using CQRS, event sourcing, or a microservice architecture?

**Answer:** No. Even a simple Java class can follow CQS without needing any of those architectural patterns.

When designing a Java method, ask four questions: **is the caller asking a question or requesting a change?**; **does the method have any side effects that could cause surprises?**; **where are the invariants protected?**; and **if it needs to both mutate and return a result, is there an atomicity requirement or business contract justifying the combination?** Answering these questions clearly ensures that query/command separation delivers practical correctness rather than just being a naming rule.
