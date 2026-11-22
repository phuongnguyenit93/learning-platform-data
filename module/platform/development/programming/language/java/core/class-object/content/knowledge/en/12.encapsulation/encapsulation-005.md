# Preventing Partially Updated State When Operations Can Fail in Java

## 1. The Problem: An Object Can Be Half-Modified Before a Method Throws an Error

**Encapsulation** is not just about making fields `private`. Encapsulation is also about a class controlling **which states are allowed to exist** and **the transitions from one valid state to another**. If a method modifies multiple fields or multiple objects and then encounters an error midway, the caller may observe a **partially updated state**: the data has been partially modified, while the business operation has not completed.

For example, an account has:

- `balance`: the current balance, non-negative.
- `reserved`: money currently held, non-negative and not exceeding `balance`.
- `available = balance - reserved`: the amount available to spend.

Suppose a method needs to move money into the reserved portion, but modifies first and checks afterward:

```java
class Account {
    private int balance = 100;
    private int reserved = 20;

    void reserveBadly(int amount) {
        reserved += amount;             // State already modified.
        if (reserved > balance) {       // Checked too late.
            throw new IllegalArgumentException("not enough balance");
        }
    }
}
```

If the caller invokes `reserveBadly(90)`, the method throws an exception because `reserved` becomes 110, which is greater than `balance` 100. **However, before throwing the error, the `reserved` field has already become 110**. An object does not automatically revert to its previous state just because of a `throw`.

Diagram:

```text
Before operation (valid)
balance = 100
reserved = 20
available = 80

     reserveBadly(90)
             |
             v
reserved = 110            <-- Already changed!
             |
             v
if (110 > 100) throw ...
             |
             v
Caller receives exception, but object:
balance = 100
reserved = 110            <-- Invalid state remains
available = -10
```

If other methods continue working with this object, the error can propagate to subsequent operations. **Preventing partially updated state** means designing methods so that errors are detected **before state is modified**, or if it has already been modified, having a mechanism to ensure the object remains in a valid state/is restored according to the contract.

> **Design goal:** for errors that the API intentionally detects and handles, the operation should **complete in full** or **leave the state as before** when possible; at a minimum, it must not break the promised invariants.

## 2. Three Concepts That Must Be Kept Separate

| Concept | Question to Answer | Example |
| --- | --- | --- |
| **Object invariant** | Which state must hold true at valid observation points? | `0 <= reserved <= balance` |
| **Failure/exception safety** | If the method does not complete, is the state still valid and kept unchanged? | A failed withdrawal must not deduct money |
| **Concurrency atomicity** | Can another thread see intermediate steps? | Two fields must be read/written under the same synchronization mechanism |

They are **related, but not identical**:

- `private` restricts field access in source code; it **does not automatically guarantee that methods update fields in the right order**.
- `throw new Exception(...)` **does not automatically roll back** assignments that have already been executed.
- `try/catch` enables error handling; by itself, it **does not create a transaction**.
- `synchronized` helps coordinate threads using the same monitor, but **does not automatically restore state** when a method throws an error.
- Writing multiple fields together in one method **does not automatically turn the entire sequence of writes into an atomic operation**.
- An operation that succeeds in RAM **does not automatically guarantee that the data has been durably committed** to a file, database, or external service.

This article focuses on **Java object-oriented design**: avoiding creating or exposing invalid state when a method/constructor can fail, and then pointing out the boundary with concurrency and out-of-process systems.

## 3. Guarantee Levels When an Operation Fails

When designing an API, several guarantee levels can be distinguished:

| Level | Meaning |
| --- | --- |
| **No explicit guarantee** | After an error, the object may be in an unspecified state under the contract, including violating invariants |
| **Basic guarantee** | The object remains in a **valid state with respect to invariants**, though it may have been partially modified |
| **Strong guarantee** | If the operation fails, the observable states covered by the contract **do not change**; if it succeeds, they update as promised |
| **No-fail guarantee** | A specific operation is designed **not to fail** under the specified conditions |

These are **contract design** concepts, not levels that Java automatically attaches to every method. “Strong guarantee” needs to clearly state its **scope**: only internal fields, or also files, events, business logs, databases, and other services?

For example, if a method sends an email and only then fails when writing to the database, reverting fields in RAM **does not recall the sent email**. Therefore, do not claim “all-or-nothing” for the entire system just because a few fields were backed up.

In many business classes, a practical goal is: **invalid input, validation exceptions, or predictable calculation errors will not change internal state**. This is a useful and testable contract.

## 4. First Technique: Validate Before Mutate

If all validity conditions can be checked from the current state and input, validation should be performed **before any mutating assignment**.

A fixed version of `reserveBadly`:

```java
class Account {
    private int balance = 100;
    private int reserved = 20;

    void reserve(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (amount > balance - reserved) {
            throw new IllegalArgumentException("not enough available balance");
        }
        reserved += amount;
    }

    int available() {
        return balance - reserved;
    }
}
```

Assuming the initial state is valid, the `reserve(90)` method checks `90 > 80` and throws an exception **before writing `reserved`**. The field remains `20`.

The condition `amount > balance - reserved` avoids having to compute `reserved + amount` before checking and, when the invariant `0 <= reserved <= balance` holds, avoids some addition overflow cases. However, if the data could be invalid from the start, the method also needs to handle **precondition state** and choose a numeric type with a sufficient value range.

### Complete Example with stdout

Save to **`ReserveSafelyDemo.java`**:

```java
class Account {
    private final int balance;
    private int reserved;

    Account(int balance, int reserved) {
        if (balance < 0 || reserved < 0 || reserved > balance) {
            throw new IllegalArgumentException("invalid opening state");
        }
        this.balance = balance;
        this.reserved = reserved;
    }

    void reserve(int amount) {
        if (amount <= 0 || amount > balance - reserved) {
            throw new IllegalArgumentException("cannot reserve " + amount);
        }
        reserved += amount;
    }

    String snapshot() {
        return "balance=" + balance
                + ", reserved=" + reserved
                + ", available=" + (balance - reserved);
    }
}

public class ReserveSafelyDemo {
    public static void main(String[] args) {
        Account account = new Account(100, 20);
        System.out.println("before: " + account.snapshot());

        try {
            account.reserve(90);
        } catch (IllegalArgumentException ex) {
            System.out.println("failed: " + ex.getMessage());
        }

        System.out.println("after failure: " + account.snapshot());
        account.reserve(30);
        System.out.println("after success: " + account.snapshot());
    }
}
```

Compile/run with JDK 17+:

```bash
javac ReserveSafelyDemo.java
java ReserveSafelyDemo
```

Output:

```text
before: balance=100, reserved=20, available=80
failed: cannot reserve 90
after failure: balance=100, reserved=20, available=80
after success: balance=100, reserved=50, available=50
```

Lessons from the example:

1. The constructor validates the invariant as soon as the object is created.
2. `reserve` validates the input and available balance **before mutation**.
3. When validation throws an exception, `reserved` remains unchanged.
4. On success, only one field needs to change, making it easy to preserve the invariant.

**Do not** use validation after modifying and “wait for the caller to catch the exception to fix it.” The caller does not necessarily know what changed in the object; the responsibility for maintaining invariants should stay inside the class that owns the state.

## 5. Checking Beforehand Is Not Enough If the Calculation Itself Can Fail

Code that looks as if it has already validated can still suffer from arithmetic errors:

```java
class BadCounter {
    private int count = Integer.MAX_VALUE;

    void add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        count += amount; // int can overflow.
    }
}
```

With `count = Integer.MAX_VALUE` and `amount = 1`, `int` addition in Java **overflows according to integer rules**, giving a negative result instead of automatically throwing an exception. Therefore, validating “amount is non-negative” **does not protect** the non-negative count invariant.

A proper approach when you want to reject overflow is to **compute in advance with `Math.addExact`**:

```java
class SafeCounter {
    private int count;

    SafeCounter(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial");
        }
        count = initial;
    }

    void add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        int next = Math.addExact(count, amount);
        count = next;
    }

    int count() {
        return count;
    }
}
```

`Math.addExact` throws `ArithmeticException` if the `int` result cannot be represented. Importantly: `next` is computed **before `count = next`**, so an arithmetic error does not modify the field.

### Example Run Confirming Overflow Does Not Change State

File **`OverflowSafetyDemo.java`**:

```java
public class OverflowSafetyDemo {
    private int count;

    OverflowSafetyDemo(int count) {
        this.count = count;
    }

    void add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative");
        }
        int next = Math.addExact(count, amount);
        count = next;
    }

    public static void main(String[] args) {
        OverflowSafetyDemo counter =
                new OverflowSafetyDemo(Integer.MAX_VALUE);

        try {
            counter.add(1);
        } catch (ArithmeticException ex) {
            System.out.println("overflow");
        }

        System.out.println(counter.count);
    }
}
```

```bash
javac OverflowSafetyDemo.java
java OverflowSafetyDemo
```

```text
overflow
2147483647
```

It is necessary to distinguish between **precondition validation** (`amount >= 0`) and **safe computation** (`Math.addExact`). Both are needed when you want state not to exceed its data range.

For monetary values, consider using the smallest integer unit with `long` when appropriate, or `BigDecimal` with clear precision, scale, and rounding rules; do not let numeric representation errors break invariants.

## 6. Multiple Dependent Fields: Compute the Entire New State Before Committing

An object can have multiple related fields:

```text
Inventory
- stock    : total items
- reserved : reserved items
- available = stock - reserved
Invariant: stock >= 0, reserved >= 0, reserved <= stock
```

If a method changes both `stock` and `reserved`, code like:

```java
// stock -= amount;
// reserved -= amount;
// check conditions at the end...
```

risks encountering an error after one assignment but before the remaining assignment.

**Recommended technique:** **calculate → validate → commit**:

1. Read the current state.
2. Compute **the proposed values** into local variables without modifying the object.
3. Validate conditions, arithmetic bounds, and invariants of **the entire proposed state**.
4. Only when everything is valid, assign the fields as planned.

Example:

```java
class Inventory {
    private int stock;
    private int reserved;

    Inventory(int stock, int reserved) {
        if (stock < 0 || reserved < 0 || reserved > stock) {
            throw new IllegalArgumentException("invalid inventory");
        }
        this.stock = stock;
        this.reserved = reserved;
    }

    void shipReserved(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        int nextStock = Math.subtractExact(stock, amount);
        int nextReserved = Math.subtractExact(reserved, amount);

        if (nextStock < 0 || nextReserved < 0
                || nextReserved > nextStock) {
            throw new IllegalArgumentException("cannot ship " + amount);
        }

        stock = nextStock;
        reserved = nextReserved;
    }

    String summary() {
        return "stock=" + stock + ", reserved=" + reserved;
    }
}
```

All errors expected to be handled (invalid amount, insufficient reserved stock, overflow) occur **before the two assignments**. After that come two simple field assignments.

**Limitation to state explicitly:** the two assignments `stock = ...` and `reserved = ...` **are not automatically combined by Java into a single atomic operation for other threads**. Within a single thread with valid data and no external interference, they provide strong protection against the checked exceptions. To prevent other threads from reading intermediate state, the same synchronization strategy must be used for the read/write paths.

### Runnable Program: Errors Do Not Corrupt the Two Fields

File **`InventoryCommitDemo.java`**:

```java
class Inventory {
    private int stock;
    private int reserved;

    Inventory(int stock, int reserved) {
        if (stock < 0 || reserved < 0 || reserved > stock) {
            throw new IllegalArgumentException("invalid state");
        }
        this.stock = stock;
        this.reserved = reserved;
    }

    void shipReserved(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("invalid amount");
        }

        int nextStock = Math.subtractExact(stock, amount);
        int nextReserved = Math.subtractExact(reserved, amount);

        if (nextStock < 0 || nextReserved < 0
                || nextReserved > nextStock) {
            throw new IllegalArgumentException("not enough reserved");
        }

        stock = nextStock;
        reserved = nextReserved;
    }

    String snapshot() {
        return stock + "/" + reserved;
    }
}

public class InventoryCommitDemo {
    public static void main(String[] args) {
        Inventory inventory = new Inventory(10, 4);
        System.out.println("before=" + inventory.snapshot());

        try {
            inventory.shipReserved(6);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected");
        }

        System.out.println("after reject=" + inventory.snapshot());
        inventory.shipReserved(3);
        System.out.println("after ship=" + inventory.snapshot());
    }
}
```

```bash
javac InventoryCommitDemo.java
java InventoryCommitDemo
```

```text
before=10/4
rejected
after reject=10/4
after ship=7/1
```

When `shipReserved(6)` computes `nextReserved=-2`, validation throws an error before modifying the fields. `shipReserved(3)` computes `nextStock=7`, `nextReserved=1`; both are valid and are assigned in the commit phase.

## 7. A Single Immutable State Field: Replace the Whole Snapshot Instead of Mutating Separate Fields

If related state can be packaged into **an immutable value object**, you can build the new state and then **replace a single reference**. This technique often simplifies ensuring that the object never exposes **half old state, half new state**.

In Java 17+, a `record` is one way to create an immutable data type at the level of field references (though you must still be careful if a component points to a mutable object).

Example:

```java
record BalanceState(int balance, int reserved) {
    BalanceState {
        if (balance < 0 || reserved < 0 || reserved > balance) {
            throw new IllegalArgumentException("invalid balance state");
        }
    }
}
```

A class owning the state:

```java
class Account {
    private BalanceState state = new BalanceState(100, 20);

    void reserve(int amount) {
        if (amount <= 0 || amount > state.balance() - state.reserved()) {
            throw new IllegalArgumentException("invalid reserve");
        }

        BalanceState next = new BalanceState(
                state.balance(),
                Math.addExact(state.reserved(), amount)
        );
        state = next;
    }

    BalanceState snapshot() {
        return state;
    }
}
```

In this example of **valid class code without main**, the `BalanceState` constructor checks the invariant. If creating `next` fails, the `state` field still points to the old snapshot. Only after the new valid value is created does `state = next` occur.

**This is “build new state, then replace”**, which is very useful when state consists of multiple related properties. However, for concurrent access, an appropriate visibility/atomic update strategy is required (for example, synchronization or CAS). Using only a reference field and a record **does not automatically prevent lost updates when multiple threads modify state together**.

### Standalone Runnable Example with record

Create **`SnapshotStateDemo.java`**:

```java
record State(int stock, int reserved) {
    State {
        if (stock < 0 || reserved < 0 || reserved > stock) {
            throw new IllegalArgumentException("invalid state");
        }
    }

    @Override
    public String toString() {
        return stock + "/" + reserved;
    }
}

class Warehouse {
    private State state = new State(8, 3);

    void ship(int amount) {
        State current = state;

        State next = new State(
                Math.subtractExact(current.stock(), amount),
                Math.subtractExact(current.reserved(), amount)
        );

        state = next;
    }

    String snapshot() {
        return state.toString();
    }
}

public class SnapshotStateDemo {
    public static void main(String[] args) {
        Warehouse warehouse = new Warehouse();
        System.out.println("before=" + warehouse.snapshot());

        try {
            warehouse.ship(5);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected");
        }

        System.out.println("after failure=" + warehouse.snapshot());
        warehouse.ship(2);
        System.out.println("after success=" + warehouse.snapshot());
    }
}
```

```bash
javac SnapshotStateDemo.java
java SnapshotStateDemo
```

```text
before=8/3
rejected
after failure=8/3
after success=6/1
```

- `warehouse.ship(5)` computes `State(3,-2)`, which is rejected by `State`'s compact constructor **before `state = next`**.
- `ship(2)` creates a valid `State(6,1)` and then replaces the state.
- `State` is a record with primitive components, so it holds a snapshot with stable logical state and exposes no setters to the caller.

In this example, `ship` does not yet check `amount > 0`, so for production that precondition must be added. For the program to proactively reject negative/zero values before computing, you can add `if (amount <= 0) throw ...`. This is a **limitation of the illustrative contract**; do not mistakenly assume that `State` can automatically check the semantics that “shipped quantity must be positive.”

## 8. Updating Collections: The “Add First, Validate Later” Mistake

A very common mistake is adding an element before checking the limit:

```java
class Team {
    private final java.util.List<String> members =
            new java.util.ArrayList<>();

    void addBadly(String name) {
        members.add(name);
        if (members.size() > 3) {
            throw new IllegalStateException("team is full");
        }
    }
}
```

If there are already three people, calling `addBadly("D")` adds the fourth person and then throws an exception. The team still keeps four people, violating the maximum-of-three rule.

**Basic fix:**

```java
void addSafely(String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("blank name");
    }
    if (members.size() >= 3) {
        throw new IllegalStateException("team is full");
    }
    members.add(name);
}
```

The method above is a **code snippet meant to be placed inside the `Team` class that has the `members` field**. It checks the conditions before `add`.

However, there is still an issue: a custom collection or external dependency can throw an error **during mutation**, or multiple threads may call the method concurrently. Therefore, *validate-before-mutate* is a good solution when you control the object and failure modes; it **does not automatically provide a strong guarantee for every collection/API**.

## 9. Copy → Modify the Copy → Validate → Publish

For a collection whose update involves multiple steps that can fail, the safe approach is usually to **work on a temporary copy** and replace the original reference only when the result is complete.

Create **`CopyThenCommitDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Roster {
    private List<String> members = List.of("An");

    void addBatch(List<String> incoming) {
        if (incoming == null) {
            throw new IllegalArgumentException("incoming required");
        }

        List<String> candidate = new ArrayList<>(members);

        for (String name : incoming) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("invalid member");
            }
            if (candidate.contains(name)) {
                throw new IllegalArgumentException("duplicate: " + name);
            }
            candidate.add(name);
        }

        if (candidate.size() > 3) {
            throw new IllegalStateException("too many members");
        }

        members = List.copyOf(candidate);
    }

    List<String> members() {
        return members;
    }
}

public class CopyThenCommitDemo {
    public static void main(String[] args) {
        Roster roster = new Roster();
        System.out.println("before=" + roster.members());

        try {
            roster.addBatch(List.of("Binh", "Binh"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        System.out.println("after failure=" + roster.members());
        roster.addBatch(List.of("Binh", "Chi"));
        System.out.println("after success=" + roster.members());
    }
}
```

```bash
javac CopyThenCommitDemo.java
java CopyThenCommitDemo
```

```text
before=[An]
rejected: duplicate: Binh
after failure=[An]
after success=[An, Binh, Chi]
```

Explanation:

1. `members` initially starts as the immutable list `["An"]`.
2. `candidate = new ArrayList<>(members)` creates a **new list structure**.
3. For the batch `["Binh","Binh"]`, one Binh has already been added to candidate, but the second occurrence is rejected. **Only candidate is modified**; the `members` field still references the original list.
4. For a valid batch, `List.copyOf(candidate)` is created first, and then **the single `members` field is replaced** at the end.
5. The getter returns an unmodifiable list; the caller cannot alter the structure through ordinary `members().add(...)` calls.

**Note on shallow copies:** `new ArrayList<>(members)` and `List.copyOf` copy references to the element objects rather than deep-copying every object. Here the elements are immutable `String` instances, so this works well. With a `List<Person>` containing mutable `Person` objects, if you call `person.rename(...)` while preparing candidate, those mutations can still be visible in the old list. For stronger safety, you must **not mutate shared elements**, or else deep-copy them according to the contract.

**Concurrency note:** another thread could also call `addBatch` between reading `members` and committing. Without synchronization, two state updates can lose changes; the snapshot solution focuses only on **single-threaded failure safety** and does not yet resolve concurrent write contention.

## 10. An Operation Involving Multiple Objects: Transferring Value Between Two Accounts

With a money transfer transaction, two objects must change state according to the same business meaning:

```text
Before: source = 100; destination = 20
Transfer 30
After : source = 70;  destination = 50
```

A simple design flaw:

```java
// source.withdraw(30);         // Already deducted from source.
// destination.deposit(30);     // Might fail.
// => source decreased, but destination has not increased.
```

If the second step throws an exception due to overflow, its own validation, or a service failure, the transfer becomes **half a transaction**.

### Approach for In-Memory State: Compute Both Results Before Updating

In the case where both accounts only have a primitive balance in the same process and all access paths follow a shared locking mechanism, you can compute the results in advance and then commit the fields under the lock.

File **`SafeTransferDemo.java`**:

```java
final class Account {
    private static final Object LOCK = new Object();
    private int balance;

    Account(int balance) {
        if (balance < 0) {
            throw new IllegalArgumentException("negative opening balance");
        }
        this.balance = balance;
    }

    static void transfer(Account from, Account to, int amount) {
        if (from == null || to == null) {
            throw new IllegalArgumentException("account required");
        }
        if (from == to) {
            throw new IllegalArgumentException("same account");
        }
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }

        synchronized (LOCK) {
            if (amount > from.balance) {
                throw new IllegalArgumentException("insufficient funds");
            }

            int nextFrom = Math.subtractExact(from.balance, amount);
            int nextTo = Math.addExact(to.balance, amount);

            from.balance = nextFrom;
            to.balance = nextTo;
        }
    }

    int balance() {
        synchronized (LOCK) {
            return balance;
        }
    }
}

public class SafeTransferDemo {
    public static void main(String[] args) {
        Account from = new Account(100);
        Account to = new Account(20);

        try {
            Account.transfer(from, to, 150);
        } catch (IllegalArgumentException ex) {
            System.out.println("transfer rejected");
        }

        System.out.println("after rejection="
                + from.balance() + "/" + to.balance());

        Account.transfer(from, to, 30);
        System.out.println("after transfer="
                + from.balance() + "/" + to.balance());
    }
}
```

```bash
javac SafeTransferDemo.java
java SafeTransferDemo
```

```text
transfer rejected
after rejection=100/20
after transfer=70/50
```

Here:

- Both accounts are checked within the same `synchronized(LOCK)` block.
- `nextFrom` and `nextTo` are computed **before** the assignments.
- When an insufficient-funds error or overflow occurs, both fields remain unchanged.
- When there are no errors, both assignments take place inside the locked block. The `balance()` read paths also use **the same LOCK**, so a single reader cannot read a field while the transfer is holding the lock.

**Limitations to understand clearly:**

- This is an **in-memory** demo, not a database transaction or a payment service.
- A global static lock is simple, but causes every Account to contend on the same monitor; larger systems require a different concurrency design (per-account locking with a fixed order, a transactional store, etc.).
- If a caller reads `from.balance()` and then `to.balance()` in **two separate calls**, another transfer can still interleave between the two reads. To get a consistent snapshot of the balance pair, read **both inside a single critical section** or through a shared snapshot API.
- The example guarantees consistency across methods that honor `LOCK`, not atomicity against observation mechanisms outside the JVM or when the process crashes.
- Do not perform I/O, callbacks, or calls to uncontrolled code while holding a lock if it can be avoided, as doing so can cause deadlocks, slowdowns, or exceptions that are hard to recover from.

## 11. “Validate First” Can Be Wrong in a Multithreaded Environment: TOCTOU

**Time-of-check to time-of-use** (TOCTOU) is the gap between checking a condition and using that result.

Simple code:

```java
if (account.balance() >= amount) {
    account.withdraw(amount);
}
```

If multiple threads operate on the same account concurrently, both may see sufficient funds before either deducts the balance. The condition that was checked **is no longer guaranteed to hold** at the time of the update.

**Better design:** place **both checking and modifying** inside an API of the object that owns the state and use an appropriate synchronization mechanism:

```java
class LockedAccount {
    private int balance;

    LockedAccount(int balance) {
        this.balance = balance;
    }

    synchronized boolean tryWithdraw(int amount) {
        if (amount <= 0 || amount > balance) {
            return false;
        }
        balance -= amount;
        return true;
    }

    synchronized int balance() {
        return balance;
    }
}
```

This is an **illustrative class declaration without `main`**. The `tryWithdraw` method checks and deducts the balance under the same monitor of the receiver, while the getter also synchronizes on the same monitor.

Do not simply write `volatile int balance` and assume `if (balance >= amount) balance -= amount` becomes an atomic operation: `volatile` provides proper visibility/ordering, but **does not automatically combine check-and-update into a single transaction**.

When state is an immutable snapshot, you can use `AtomicReference<State>` with a CAS loop to ensure state-based updates without being overwritten by another thread. However, the callback computing the new state inside the CAS loop **may be executed multiple times**, so there must be no external side effects in that computation step.

## 12. Rollback with `try/catch`: When Is It Needed, When Is It Dangerous?

Sometimes an operation **must** perform mutation steps before all risks are known. In such cases, you can consider **controlled rollback**:

1. Record the state that needs to be restored.
2. Execute the steps that might fail.
3. If a step fails, restore the state.
4. Rethrow the exception or convert it into an error result according to the contract.

Example illustrating the idea:

```java
int oldCount = count;
try {
    count += amount;
    operationThatMayFail();
} catch (RuntimeException ex) {
    count = oldCount;
    throw ex;
}
```

This is a **non-standalone code snippet**. It can only guarantee that `count` is restored for caught `RuntimeException` instances **and** when the recovery code behaves as expected.

**Major pitfalls of manual rollback:**

- If multiple fields/objects are modified together and you only save `oldCount`, it **does not roll back the entire state**.
- If an email has been sent, a file written, a callback triggered, or an external service called, reassigning fields cannot undo that side effect.
- If a callback kept a reference to a secondary object that was mutated, rolling back fields on the primary object will not necessarily restore the secondary object's state.
- If an exception occurs **during the rollback process itself**, recovery can fail as well.
- Across multiple threads, rolling back by reassigning old values can **overwrite valid changes made by another thread** if there is no isolation mechanism.
- Do not catch every `Throwable` and treat all cases as recoverable business errors; `Error`, system resource conditions, and severe failures have different constraints.

Therefore, **prefer computing in advance and then committing** when feasible. Use manual rollback when you genuinely understand every side effect and have a contract guaranteeing recovery; for multi-resource operations, an appropriate transaction system or compensation design is needed.

## 13. `finally` and try-with-resources: Releasing Resources Differs from Rolling Back Data

Java provides `finally` and **try-with-resources** to help **close resources** when a code block finishes normally or due to an exception. However, **closing resources is not the same as restoring all business state**.

Example with a resource managed via `AutoCloseable`:

```java
class Resource implements AutoCloseable {
    void use() {
        System.out.println("using resource");
        throw new IllegalStateException("operation failed");
    }

    @Override
    public void close() {
        System.out.println("resource closed");
    }
}

public class ResourceCleanupDemo {
    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            resource.use();
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }
}
```

Save the entire code to **`ResourceCleanupDemo.java`**, then compile/run:

```bash
javac ResourceCleanupDemo.java
java ResourceCleanupDemo
```

```text
using resource
resource closed
caught: operation failed
```

`close()` is called by try-with-resources when `use()` throws an exception. This ensures a **cleanup** mechanism in the illustrative case, but does not say that every change inside `use()` has been rolled back.

**Distinguish clearly:**

- **Cleanup:** closing files, releasing locks/resources, discarding temporary sessions.
- **Rollback:** restoring business state back to before the operation.
- **Commit:** confirming the new state after completing the necessary steps.

Each requires its own API and contract. With JDBC, `Connection.rollback()` only actually rolls back changes according to the transaction rules of the connection and database when a transaction has been properly organized; not every `try-with-resources` block automatically rolls back business operations.

## 14. Database Transactions: When Changes Span Multiple Records

A transfer between two accounts stored in a database needs to be viewed as **a multi-step transaction**, not two independent update statements.

Illustrative JDBC skeleton:

```java
import java.sql.Connection;
import java.sql.SQLException;

class TransferService {
    static void transfer(Connection connection) throws SQLException {
        boolean originalAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            // Execute PreparedStatements to update the two records.
            // Check affected row counts and business conditions.
            // No SQL is executed in this illustrative snippet.

            connection.commit();
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
            throw ex;
        } finally {
            connection.setAutoCommit(originalAutoCommit);
        }
    }
}
```

This is an **illustrative structural template**, not a standalone application or a complete transaction; you must use a concrete schema, SQL, isolation level, and datasource. In systems using a connection pool, transaction ownership, manually managing `autoCommit`, and returning the connection to the pool also depend on the framework/library contract.

**Points to understand:**

- `setAutoCommit(false)` starts the transaction-control model on the connection when appropriate.
- Only call `commit()` after all steps/validations have completed.
- On error, attempt `rollback()` to discard uncommitted changes within the scope of the database transaction.
- A rollback/connection failure can leave the transaction outcome **ambiguous**, requiring reporting/investigation or a recovery mechanism; do not assert absolute success/rollback when the database returns an indeterminate state.
- A database transaction does not automatically recall sent emails or HTTP requests already processed by an external system.

**Encapsulating responsibility:** if `AccountRepository` manages persistence, transactions should be centralized at the appropriate service/repository boundary, rather than each Java entity independently opening/committing a connection and causing half-transactions.

## 15. Calling External Services: Side Effects Cannot Be Undone by Field Assignment

Suppose order processing consists of:

1. Marking the order as paid.
2. Deducting inventory.
3. Sending a confirmation email.

If step 3 fails after 1–2 succeed, you should not simply `throw` and declare that “the order has not been processed.” In reality, state has already changed.

Some architectural strategies:

- **Same-database transaction:** update the order and stock in a single transaction if they are genuinely within the same transaction scope.
- **Transactional outbox:** write the business data and “event to be sent” within the same DB transaction, and then another system sends the email/event with a retry mechanism.
- **Idempotency key:** ensures that retrying a request/event does not produce unintended duplicate effects.
- **Saga/compensating action:** when multiple services do not share a transaction, organizing steps and compensating actions can be applied — though a compensating action **does not always restore everything completely**.
- **Explicit business states:** `PENDING`, `PAID`, `FULFILLED`, `FAILED` with state transition rules, instead of a boolean flag changed before the entire task completes.

There is no need to apply every complex architectural pattern to a simple class; what matters is **accurately defining the boundaries of “success,” “failure,” and “committed”**.

## 16. Constructors Can Also Fail: Do Not Expose Partially Constructed Objects

Constructors typically establish the initial invariants. Validate data **before storing sensitive state or letting `this` escape**.

Example:

```java
final class Booking {
    private final String code;
    private final int seats;

    Booking(String code, int seats) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code required");
        }
        if (seats <= 0) {
            throw new IllegalArgumentException("positive seats required");
        }

        this.code = code;
        this.seats = seats;
    }

    String summary() {
        return code + ":" + seats;
    }
}
```

If validation throws an exception, the `Booking` creation expression does not complete normally and the caller receives no object from that constructor call. However, that **does not guarantee that all side effects of the constructor automatically roll back**. If the constructor already registered `this` in a static collection, started a thread, sent an event, or mutated an external object, a reference to the partially constructed object may be exposed.

### The “this escapes” Pitfall in Constructors

```java
// Illustrates a dangerous design pattern only:
class BadRegistration {
    static final java.util.List<BadRegistration> ALL =
            new java.util.ArrayList<>();

    private String name;

    BadRegistration(String name) {
        ALL.add(this); // this escapes before initialization finishes.
        if (name == null) {
            throw new IllegalArgumentException("name required");
        }
        this.name = name;
    }
}
```

If `new BadRegistration(null)` is called, the constructor throws an error, yet the `ALL` list may already hold a reference to an object without a valid `name`. This is an example of a **side effect before validation** and **object escape**.

Safe approach:

1. Validate inputs and conditions that can be checked upfront.
2. Fully initialize the object's state.
3. Avoid publishing `this` (registering in a registry, callback, or thread) inside the constructor if possible.
4. When registration is required, consider a factory/service that performs **registration after construction succeeds**; you still need to account for registration failures and retry/rollback capability.

**Note:** private final fields make the design easier to control, but do not automatically prevent callbacks or external side effects inside a constructor.

## 17. Returning New Results Instead of Mutating Inputs

One way to reduce the risk of partially updated state is to use **immutable value objects** and methods that return a new instance.

Java 17+ example:

```java
record Money(long cents) {
    Money {
        if (cents < 0) {
            throw new IllegalArgumentException("negative money");
        }
    }

    Money plus(Money other) {
        return new Money(Math.addExact(cents, other.cents));
    }
}
```

Inside `plus`, the `this` and `other` objects are not modified. If overflow occurs, `Math.addExact` throws `ArithmeticException` and the two old Money instances retain their values. If it succeeds, a new `Money` instance is returned.

### Runnable Program for Value Objects

File **`ImmutableMoneyDemo.java`**:

```java
record Money(long cents) {
    Money {
        if (cents < 0) {
            throw new IllegalArgumentException("negative");
        }
    }

    Money plus(Money other) {
        return new Money(Math.addExact(cents, other.cents()));
    }
}

public class ImmutableMoneyDemo {
    public static void main(String[] args) {
        Money original = new Money(500);
        Money addition = new Money(125);
        Money result = original.plus(addition);

        System.out.println("original=" + original.cents());
        System.out.println("result=" + result.cents());

        try {
            new Money(Long.MAX_VALUE).plus(new Money(1));
        } catch (ArithmeticException ex) {
            System.out.println("overflow rejected");
        }
    }
}
```

```bash
javac ImmutableMoneyDemo.java
java ImmutableMoneyDemo
```

```text
original=500
result=625
overflow rejected
```

**Benefit:** the input records do not change due to the `plus` method. However, immutable objects **do not eliminate** failures when coordinating multiple external systems; they only make state boundaries in RAM clearer.

If a record contains a mutable `List`, `Map`, or array, the component fields may be final, yet **the referenced object can still be mutated**. Defensive copying is needed when deep immutability is required by the contract.

## 18. Shallow Copies, Deep Copies, and Object Graphs

The copy-then-commit technique has an important limitation: **a copy of a container is not necessarily a copy of every element**.

```java
class Participant {
    String name;

    Participant(String name) {
        this.name = name;
    }
}
```

Suppose:

```java
java.util.List<Participant> original =
        new java.util.ArrayList<>();
original.add(new Participant("An"));

java.util.List<Participant> candidate =
        new java.util.ArrayList<>(original);

candidate.get(0).name = "Binh";
```

Even though `candidate` and `original` are **two list objects**, they both hold a reference to the **same Participant object**. Modifying `candidate.get(0).name` **already changed the participant that original points to** before the list was committed.

Diagram:

```text
original ──> List A [0] ────┐
                            ├──> Participant X {name="Binh"}
candidate ─> List B [0] ────┘
```

To ensure you do not mutate the original data graph while preparing the result, you can:

- **Do not modify element objects** while working on candidate; only create/replace references as appropriate.
- Use immutable element types.
- Create a **copy of each mutable element** using a constructor/factory/copy contract.
- Build a complete new state value instead of touching the original object graph.

There is no general `clone()` that automatically guarantees a deep copy for every Java object graph. You need to consider ownership, reference cycles, invariants, and cost.

## 19. Do Not Use Validation with Side Effects

A validation method should **focus on checking** and avoid arbitrarily mutating the very state it is validating.

Example to avoid:

```java
boolean validAndRemoveExpired(java.util.List<Item> items) {
    items.removeIf(Item::expired);  // Mutation mixed into validation.
    return items.size() <= 10;
}
```

This is an **illustrative code snippet** assuming `Item` has `expired()`, not a standalone runnable program. If a subsequent check fails or the method throws an exception, the list has already been modified even though the caller might think this is merely a yes/no question.

A clearer approach is to separate:

1. `validate(...)` **reads** and checks without mutating.
2. `plan(...)` creates the proposed changes in local/immutable state.
3. `commit(...)` applies them once when all conditions are satisfied.

Of course, some APIs intentionally combine checking and modifying, such as `tryWithdraw` or `removeIf`; the issue is not forbidding mutation, but rather that **the contract must state it clearly** and failure behavior must be designed.

## 20. Order of Validation and Order of Side Effects

Suppose a method performs:

```text
Validate input
Log success event
Compute result (may overflow)
Assign state
```

If the calculation overflows, the log has already falsely recorded “success.” Therefore, not only state fields, but also **the order of side effects** must be considered.

An order that is usually more reasonable:

```text
1. Validate input and current state.
2. Compute proposed result (may throw an error).
3. Prepare data/events that will be needed.
4. Commit state at the designed boundary.
5. Emit completion signal/log success per contract.
```

However, if logging or sending a message in step 5 fails, you must determine **whether the business state has been committed or not**. You cannot simply throw a generic exception and pretend nothing happened. With multiple external systems, using a transactional outbox, retries with idempotency, or a `PENDING_NOTIFICATION` state will be clearer.

### Why Is `System.out.println` in the Middle of a Transaction Also a Side Effect?

Console output is not rolled back when object state reverts to its previous value. In tutorials, simple log printing helps observe execution order; in production, **do not use pre-commit success output** as proof that a business operation succeeded.

## 21. Exception Handling: Preserving Causes and Error Contracts

When a method fails, the caller needs to know:

- Is the error an **invalid input**, **insufficient resources/business state**, or **system error**?
- After the error, is the object **still valid**, and does it **keep its previous state unchanged**?
- Can the caller **retry** safely?
- Did any external side effects **already succeed**?

Example:

```java
void reserve(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }
    if (amount > available()) {
        throw new IllegalStateException("not enough available items");
    }
    // Perform mutation according to the valid plan.
}
```

This is an illustrative code snippet meant to be placed in a class with an appropriate `available()` method. Distinguishing exception types helps the caller understand the error, but **exception type does not automatically guarantee safe state**. What matters most remains **the order and manner of updating**.

**Do not** catch every `RuntimeException` and return `false` if state has already been partially modified; doing so hides the error. Nor should you swallow exceptions and let the caller believe the operation succeeded. If changing the exception type, preserve the cause using an appropriate constructor and describe the contract.

For a cleanup/rollback step that might fail, avoid losing the original exception; for example, use `addSuppressed` for a rollback failure as in the JDBC skeleton above.

## 22. Common Mistakes When Preventing Partially Updated State

| Mistake | Why It Is Dangerous | Better Design |
| --- | --- | --- |
| Mutating fields before validating | Exception leaves modified fields behind | Validate before mutation |
| Checking input while ignoring overflow | State can exceed arithmetic bounds | Compute with `Math.addExact`/`subtractExact` before assigning |
| Updating field A before computing field B | Failure while computing B leaves A modified | Compute all `next...` values before commit |
| Using `private` alone and assuming the object is safe | The class's own methods can still break invariants | Every mutation path must preserve invariants |
| Calling two independent setters to update related state | Intermediate state may be invalid or exposed | A single domain operation updates the whole group |
| Adding to a list before checking capacity | The list exceeds the limit if an exception is thrown | Check upfront or use copy-then-commit |
| Cloning a list while mutating shared elements | Shallow copy does not isolate mutable elements | Immutable elements/selective deep copy |
| Using `try/catch` without rolling back | An exception does not undo prior mutations | Design explicit strong/basic guarantees |
| Treating `finally` as a transaction | Cleanup differs from rollback | Use transaction/rollback within the proper scope |
| Saving to DB then directly emitting events, treating errors as unsaved | External side effects are not reversed | Outbox/idempotency/saga when appropriate |
| Using `synchronized` and thinking exceptions auto-roll back | Lock does not save old state | Compute-before-commit and separate synchronization |
| Validating outside a lock and committing inside a lock later | TOCTOU: state may change between the two steps | Validate+commit in the same critical section |
| Factory/constructor publishing `this` before completion | May expose a half-constructed object | Finish constructing the object before publishing |
| Catching all errors as `false` | Hides corrupted state and root cause | Report errors with a contract and verify state |
| Retrying non-idempotent operations unconditionally | Can duplicate effects that already occurred | Idempotency key or deterministic outcomes |
| Changing multiple fields without synchronizing readers | Other threads may see intermediate state | Appropriate snapshot/lock/transaction |
| Treating all-or-nothing in RAM as durable on crash | No storage guarantee | Use transactional storage mechanisms |
| Allowing callers to mutate mutable state via getters | Invariant is broken outside methods | Defensive copy/unmodifiable API |

## 23. Self-Check: 12 Questions with Answers

**Question 1.** Does a method written as `balance -= amount; if (balance < 0) throw ...;` preserve state when withdrawing more than the balance?

**Answer:** No. The `balance` field was already decremented before throwing the exception. Check `amount` and the balance before assigning.

**Question 2.** Does `throw new IllegalArgumentException(...)` automatically roll back all field changes before it?

**Answer:** No. Java exceptions alter control flow; they do not provide general state rollback.

**Question 3.** Why should `Math.addExact` be called before assigning the field?

**Answer:** If it overflows, it throws `ArithmeticException` before mutation; the field still retains its old value.

**Question 4.** For two related fields, why is computing `nextA` and `nextB` beforehand beneficial?

**Answer:** Validation/computation can fail while the object remains intact; only commit when the entire proposed state is valid.

**Question 5.** Does using `synchronized` around two assignments automatically roll back if the second statement throws an exception?

**Answer:** No. Locking handles concurrency coordination; it does not automatically restore data that has already been assigned.

**Question 6.** Does creating `new ArrayList<>(original)` and then mutating a field of the object at index 0 guarantee that original remains unchanged?

**Answer:** No. The list copy is a shallow copy; both lists can point to the same mutable element object.

**Question 7.** Is a record containing `List<Person>` with a final field completely immutable?

**Answer:** Not necessarily. Person or the list may be mutable and shared; an appropriate copy/immutability design is needed.

**Question 8.** What consequence can occur when a constructor throws an exception after adding `this` to a static registry?

**Answer:** The registry may still hold a reference to an object whose initialization is incomplete, even though the caller did not receive an object from a successful `new` expression.

**Question 9.** Does `try-with-resources` guarantee that all database/field updates roll back?

**Answer:** No. It manages closing resources; transaction rollback must be organized separately according to the contract.

**Question 10.** Why does a method transferring money across two services need a more complex mechanism than two assignments in RAM?

**Answer:** There are independent networks, storage, and side effects; no single Java lock or try-catch automatically creates a distributed transaction. Appropriate transactions/outbox/idempotency/sagas are needed.

**Question 11.** If two threads both check `balance >= amount` before withdrawing, what can happen?

**Answer:** Both may see sufficient funds while the total withdrawn exceeds the balance due to TOCTOU. Check-and-update needs appropriate synchronization/CAS/transactions.

**Question 12.** Does “if a method fails, state does not change” include an email that was already sent beforehand?

**Answer:** Only if the specific contract/boundary and mechanism guarantee it. For an email already sent externally, it usually cannot be rolled back by reassigning a Java field.

## 24. Final Practice Exercise: Find and Fix the Partial Mutation Bug

Problem: A `GiftCard` has `balance` (amount) and `spent` (total amount spent). Invariant:

```text
balance >= 0
spent >= 0
```

Incorrect code:

```java
class GiftCard {
    private int balance;
    private int spent;

    GiftCard(int balance) {
        this.balance = balance;
    }

    void payBadly(int amount) {
        balance -= amount;    // Mutates first.
        spent += amount;      // May overflow.
        if (balance < 0) {
            throw new IllegalArgumentException("not enough");
        }
    }
}
```

**Answer for yourself:** If `amount > balance` or `spent + amount` overflows `int`, does the class still preserve the invariant? Can you fix it so those errors happen **before mutation**?

### One Solution Using calculate → validate → commit

Create **`GiftCardSafetyDemo.java`**:

```java
class GiftCard {
    private int balance;
    private int spent;

    GiftCard(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial");
        }
        this.balance = initial;
    }

    void pay(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
        if (amount > balance) {
            throw new IllegalArgumentException("insufficient balance");
        }

        int nextBalance = Math.subtractExact(balance, amount);
        int nextSpent = Math.addExact(spent, amount);

        if (nextBalance < 0 || nextSpent < 0) {
            throw new IllegalArgumentException("invalid resulting state");
        }

        balance = nextBalance;
        spent = nextSpent;
    }

    String snapshot() {
        return "balance=" + balance + ", spent=" + spent;
    }
}

public class GiftCardSafetyDemo {
    public static void main(String[] args) {
        GiftCard card = new GiftCard(50);
        System.out.println("before: " + card.snapshot());

        try {
            card.pay(70);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected");
        }

        System.out.println("after failure: " + card.snapshot());
        card.pay(20);
        System.out.println("after success: " + card.snapshot());
    }
}
```

```bash
javac GiftCardSafetyDemo.java
java GiftCardSafetyDemo
```

```text
before: balance=50, spent=0
rejected
after failure: balance=50, spent=0
after success: balance=30, spent=20
```

**Solution analysis:**

1. The constructor rejects a negative balance value.
2. The `pay` method checks `amount > 0` and sufficient balance before any mutation.
3. `Math.subtractExact` and `Math.addExact` compute the two proposed results. If either calculation fails, both fields remain intact.
4. The invariant conditions of the result are verified before committing.
5. The final two assignments apply the new state. This example discusses single-threaded failure safety; if multiple threads access the card, you must synchronize the read/write paths or use an immutable snapshot.

### Advanced Scenario

If `spent` must not exceed a limit, add that limit to the **result validation phase**, rather than adding an `if` check that throws an error after `spent` has already been assigned. If payment must write to a database and emit an event, extend the transaction contract beyond `GiftCard`'s state instead of merely adding a `try/catch`.

## 25. Code Review Checklist Before Publishing a Method That Can Fail

- [ ] Does the object have **clear invariants** after construction and after every public operation?
- [ ] Does each failure path define the **post-error state**?
- [ ] Are inputs and preconditions validated **before mutation** whenever feasible?
- [ ] Are overflow/parse/lookup calculations that can throw errors executed before commit?
- [ ] For multiple fields, are **all new values** computed and invariants checked before assignment?
- [ ] Can an **immutable snapshot** be used instead of updating multiple separate fields?
- [ ] For collections, has **copy → validate → commit** been considered?
- [ ] Does the copy truly isolate mutable element objects that need protection?
- [ ] Does any getter or constructor accidentally expose an alias to mutable internal state?
- [ ] Do any external side effects occur before the business operation is considered committed?
- [ ] When rolling back, is enough state saved and are all rollback steps reliable?
- [ ] If rollback fails, is the original exception preserved and the indeterminate state reported?
- [ ] Are **cleanup**, **rollback**, and **commit** conflated into one concept?
- [ ] Does any constructor/factory publish `this` too early?
- [ ] In multithreading, are validation and mutation inside the **same appropriate synchronization boundary**?
- [ ] Can readers observe intermediate state through individual fields or unsynchronized getters?
- [ ] If calling a database or external service, does the API have an appropriate transaction/idempotency/retry contract?
- [ ] Do unit tests verify **state before/after predictable errors**, not just checking the exception type?
- [ ] Do tests cover **arithmetic bounds, full lists, null/duplicate data, and multi-step failures**?
- [ ] Does the documentation clearly state the post-failure state and retryability?

---

**Remember:** Preventing partially updated state is **a core part of encapsulation**. `private` fields help centralize write access, but **every method that owns state must still preserve invariants**. When an operation can fail, prioritize **validate first → compute the full new state → commit later**. For collections and object graphs, you can **copy → modify/validate on the copy → publish the new state**, while keeping shallow copies in mind. `throw`, `try/catch`, `finally`, and `synchronized` **do not automatically provide general rollback**. For concurrency, databases, and out-of-process side effects, dedicated transaction/synchronization boundaries and error contracts are required to avoid treating a half-finished operation as complete.
