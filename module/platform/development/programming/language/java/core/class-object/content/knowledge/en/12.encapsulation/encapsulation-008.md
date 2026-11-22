# Example of Protecting Balance and Transaction History with Encapsulation in Java

## Objectives

After this lesson, you will be able to:

- Design an account class whose **balance can only be modified through valid operations**, preventing callers from writing directly to fields.
- Define and enforce the rules of a **non-negative balance**, positive transaction amounts, recording successful transactions in history, and ensuring failed transactions do not mutate data.
- Explain why `private long balance` is **not enough** if a setter still allows invalid values or the history-recording method has loopholes.
- Write `deposit` and `withdraw` methods that validate preconditions, prevent `long` overflow, and then record **the new balance and a consistent history entry**.
- Distinguish between the **mutable internal history list** and the **read-only snapshot** exposed externally; avoid leaking references that allow callers to modify or clear the history.
- Use a Java 17 `record` to create an immutable transaction entry with `sequence`, transaction kind, amount, and post-transaction balance fields.
- Test identity, snapshots, exception safety, audit consistency, and multithreading issues, while distinguishing a learning model from real-world financial system requirements.
- Read, compile, and run standalone examples with deterministic output.

## 1. The Problem: Who Has the Authority to Decide the Balance and History?

Suppose you manage a simple account:

~~~text
Account
  id: "ACC-01"
  balance: 750
  history:
    #1 DEPOSIT  1000 -> balance 1000
    #2 WITHDRAW 250  -> balance 750
~~~

In the example, all monetary amounts are measured in a **hypothetical smallest unit**, stored as a `long` integer. This is not a complete model for multi-currency money; the goal is to focus on encapsulation and consistency.

A dangerous API:

~~~java
class BadAccount {
    public long balanceCents;
    public java.util.List<String> history = new java.util.ArrayList<>();
}
~~~

A caller can directly write:

~~~java
BadAccount account = new BadAccount();
account.balanceCents = -100;
account.history.add("fake withdrawal");
account.history.clear();
~~~

The snippets above are only **illustrative** and need to reside in a valid Java context. They allow creating a negative balance, fabricating transactions, or clearing the history without any control. Even if the class has a correct `deposit` method, callers can still bypass it through the public fields.

To protect the data, the class must retain control over:

1. **Entry points:** How are the initial balance and transactions created?
2. **Rules:** Is each amount valid? Is there enough balance to withdraw? Could overflow occur?
3. **State transitions:** How does the new balance correspond to the new transaction?
4. **Exit points:** What is the caller allowed to read? Does the caller receive a mutable reference to the internal history?
5. **Failures:** When an operation is rejected, are both the balance and history kept unchanged?
6. **Concurrency:** If multiple threads operate at the same time, are the check/write steps executed consistently?

**First conclusion:** Encapsulation is not just using `private`; it is **enforcing the contract across all paths for creating, updating, and observing state**.

## 2. Define Clear Invariants Before Writing Code

In the simple version with an initial balance of 0 and only two transaction types `DEPOSIT` and `WITHDRAW`, the reasonable invariants are:

- **I1:** `balanceCents >= 0` at every point after a public operation completes normally.
- **I2:** The history contains only records of transactions **actually accepted by the class**; there are no records from rejected deposits or withdrawals.
- **I3:** Each transaction has `amountCents > 0` and a non-negative post-transaction balance.
- **I4:** The transaction sequence has `sequence` increasing consecutively as 1, 2, 3... with no sequence numbers assigned to failed transactions.
- **I5:** If you traverse the history starting from a balance of 0, adding deposits and subtracting withdrawals in order, the result must equal the current balance; `balanceAfterCents` on each record must match the result at that step.
- **I6:** Callers cannot modify, add, remove, or alter the contents of records provided through the read history.
- **I7:** An invalid transaction modifies **neither the balance nor the history**.

These invariants fit **a single-account model without interest, fees, refunds, or special balance adjustments**. If fees or transfers are added later, corresponding transaction types and reconciliation rules must be added as well. You must not keep the old formula and silently mutate the balance.

### 2.1. Distinguishing Preconditions and Postconditions

| Method | Condition before execution | Outcome on success |
| --- | --- | --- |
| `Account("ACC-01")` | ID is not null/blank | Balance = 0, history is empty |
| `deposit(amount)` | Amount is positive, addition does not overflow | Balance increases by exactly amount; adds one `DEPOSIT` |
| `withdraw(amount)` | Amount is positive and does not exceed balance | Balance decreases by exactly amount; adds one `WITHDRAW` |
| `balanceCents()` | No input | Returns a `long`, does not allow modifying the field via the result |
| `history()` | No input | Returns an unmodifiable snapshot of immutable entries |
| `snapshot()` | No input | Returns a single value containing balance and history at a consistent observation point in an appropriate model |

All preconditions are checked before writing state. Do not wait until after subtracting from the balance to discover insufficient funds.

## 3. Main Java 17 Example: Simultaneously Protecting Balance and History

This example uses:

- `private long balanceCents`: balance state.
- `private final ArrayList<Transaction> history`: storage for the history that is **mutable, but internal only**.
- `record Transaction(...)`: a value-like record; it contains only primitive values and an enum, so it has no mutable components.
- `List.copyOf(history)`: an unmodifiable snapshot, not a direct reference to the internal `ArrayList`.
- `Math.addExact`: prevents `long` overflow on the balance.
- Internal `appendAndCommit` method: appends the record and then assigns the balance. All inputs have already been validated **before committing**.

Save **`ProtectedAccountHistoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ProtectedAccountHistoryDemo {
    enum Kind {
        DEPOSIT, WITHDRAW
    }

    record Transaction(
            long sequence,
            Kind kind,
            long amountCents,
            long balanceAfterCents) {

        Transaction {
            if (sequence <= 0) {
                throw new IllegalArgumentException("sequence must be positive");
            }
            Objects.requireNonNull(kind, "kind");
            if (amountCents <= 0 || balanceAfterCents < 0) {
                throw new IllegalArgumentException("invalid transaction values");
            }
        }

        String describe() {
            return "#" + sequence + " " + kind
                    + " amount=" + amountCents
                    + " balance=" + balanceAfterCents;
        }
    }

    static final class Account {
        private final String id;
        private long balanceCents;
        private final ArrayList<Transaction> history = new ArrayList<>();

        Account(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("account id is required");
            }
            this.id = id;
        }

        String id() {
            return id;
        }

        long balanceCents() {
            return balanceCents;
        }

        List<Transaction> history() {
            return List.copyOf(history);
        }

        void deposit(long amountCents) {
            requirePositive(amountCents);
            long updatedBalance = Math.addExact(balanceCents, amountCents);
            appendAndCommit(Kind.DEPOSIT, amountCents, updatedBalance);
        }

        void withdraw(long amountCents) {
            requirePositive(amountCents);
            if (amountCents > balanceCents) {
                throw new IllegalStateException("insufficient balance");
            }
            long updatedBalance = balanceCents - amountCents;
            appendAndCommit(Kind.WITHDRAW, amountCents, updatedBalance);
        }

        private static void requirePositive(long amountCents) {
            if (amountCents <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
        }

        private void appendAndCommit(
                Kind kind, long amountCents, long updatedBalance) {
            long sequence = Math.addExact((long) history.size(), 1L);
            Transaction entry = new Transaction(
                    sequence, kind, amountCents, updatedBalance);

            history.add(entry);
            balanceCents = updatedBalance;
        }
    }

    public static void main(String[] args) {
        Account account = new Account("ACC-01");
        System.out.println("initial=" + account.id()
                + " balance=" + account.balanceCents()
                + " entries=" + account.history().size());

        account.deposit(1000);
        account.withdraw(250);

        List<Transaction> earlier = account.history();
        System.out.println("after two=" + account.balanceCents()
                + " entries=" + earlier.size());

        for (Transaction entry : earlier) {
            System.out.println(entry.describe());
        }

        account.deposit(50);
        System.out.println("after new deposit=" + account.balanceCents()
                + " current=" + account.history().size());
        System.out.println("earlier snapshot=" + earlier.size());

        try {
            earlier.clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("history cannot be cleared");
        }

        try {
            account.withdraw(1000);
        } catch (IllegalStateException expected) {
            System.out.println("withdraw rejected");
        }

        try {
            account.deposit(Long.MAX_VALUE);
        } catch (ArithmeticException expected) {
            System.out.println("overflow rejected");
        }

        System.out.println("final balance=" + account.balanceCents()
                + " entries=" + account.history().size());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ProtectedAccountHistoryDemo.java
java ProtectedAccountHistoryDemo
~~~

**Exact stdout:**

~~~text
initial=ACC-01 balance=0 entries=0
after two=750 entries=2
#1 DEPOSIT amount=1000 balance=1000
#2 WITHDRAW amount=250 balance=750
after new deposit=800 current=3
earlier snapshot=2
history cannot be cleared
withdraw rejected
overflow rejected
final balance=800 entries=3
~~~

### 3.1. Tracing the First Two Transactions

Initially:

~~~text
balanceCents = 0
history = []
~~~

After `deposit(1000)`:

~~~text
balanceCents = 1000
history = [
  #1 DEPOSIT amount=1000 balanceAfter=1000
]
~~~

After `withdraw(250)`:

~~~text
balanceCents = 750
history = [
  #1 DEPOSIT  amount=1000 balanceAfter=1000,
  #2 WITHDRAW amount=250  balanceAfter=750
]
~~~

There is no `setBalanceCents` setter, nor any public `addTransaction(Transaction)`. Callers only request **behavior**. The class itself decides when to update the balance and when to record an entry.

### 3.2. Why Does the Next Deposit Not Modify the Earlier Snapshot?

`List<Transaction> earlier = account.history()` receives an **unmodifiable list** containing the two entries at the time of the call. When `account.deposit(50)` executes, the internal history has three entries, while the `earlier` variable still holds the list of two entries.

This is a **snapshot of the list structure**, unlike a live **view** of the internal list. In this example, the entries are immutable records, so the contents of the entries cannot be mutated in place either.

### 3.3. Why Does Withdrawing 1000 Fail While the Balance Remains 800?

After three transactions, balance = 800. `withdraw(1000)` encounters `amountCents > balanceCents` and throws `IllegalStateException` **before** calling `appendAndCommit`. Therefore, no subtraction occurs and no transaction is added.

If the method accidentally recorded the transaction first and checked for sufficient funds afterward, it could leave behind a spurious entry or corrupt the balance. The order of validation before commit is essential.

### 3.4. Why Is Depositing `Long.MAX_VALUE` Rejected?

`balanceCents` is currently 800, so `Math.addExact(800, Long.MAX_VALUE)` exceeds the `long` range and throws `ArithmeticException`. Because there is no valid `updatedBalance`, `appendAndCommit` **does not run**. Both balance and history remain unchanged.

If you used `balanceCents += amountCents` with `long`, the addition could overflow to an incorrect—or even negative—value, breaking the `balanceCents >= 0` invariant.

## 4. Choosing Currency Types and Units: Do Not Use `double` for Exact Monetary Amounts

The example above uses `long` in the smallest unit, such as illustrative "cents". This does not mean every currency has exactly two decimal places.

### 4.1. Why Is `double` Dangerous?

Decimal fractions such as 0.1 often have no exact binary representation in `double`. When performing multiple additions or subtractions, floating-point errors can make balance comparison logic unreliable.

Illustrative example:

~~~java
double value = 0.1 + 0.2;
System.out.println(value);
~~~

In standard Java, the printed line is `0.30000000000000004`. This is a property of binary representation, not a Java-specific bug. For financial data requiring decimal precision, many systems use **`BigDecimal` with defined scale/rounding** or a money type that specifies the currency code/unit.

### 4.2. Units Must Be Consistent Across All Methods

Naming the parameter `amountCents` tells the caller that the value is in the hypothetical smallest unit. Avoid:

~~~java
deposit(100);
~~~

without documentation clearly stating whether `100` means 100 dong, 100 cents, or 100 of another unit.

An API can use a `Money` wrapper/value object to carry the currency and scale. That is a design improvement when business logic grows complex; in this lesson, the `long` type keeps the focus on the principles of encapsulating balance and history.

## 5. A `private` Field Is Not Enough If a Getter Returns a Mutable Reference

An easily broken design:

~~~java
class UnsafeHistory {
    private final java.util.ArrayList<String> history =
            new java.util.ArrayList<>();

    java.util.ArrayList<String> getHistory() {
        return history;
    }
}
~~~

Although the `history` field is `private final`, the getter returns **the exact reference to the internal ArrayList**. A caller can:

~~~java
UnsafeHistory object = new UnsafeHistory();
object.getHistory().add("FAKE TRANSACTION");
object.getHistory().clear();
~~~

This is an illustrative snippet placed inside a method. There is no need to access the field directly: the caller already has a reference to the mutable list and can operate on that very object. `final` only restricts **reassigning the field reference**; it does not make the ArrayList object immutable.

### 5.1. Runnable Program: Corrupting History Through a Getter

Save **`LeakingHistoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LeakingHistoryDemo {
    static final class Account {
        private long balance = 100;
        private final List<String> history = new ArrayList<>();

        Account() {
            history.add("OPEN balance=100");
        }

        long balance() {
            return balance;
        }

        List<String> history() {
            return history; // Leaks mutable reference!
        }
    }

    public static void main(String[] args) {
        Account account = new Account();
        System.out.println("before=" + account.balance()
                + " records=" + account.history().size());

        account.history().clear();
        account.history().add("FAKE withdrawal 999");

        System.out.println("after=" + account.balance()
                + " records=" + account.history().size());
        System.out.println("history=" + account.history().get(0));
    }
}
~~~

Compile/run:

~~~bash
javac LeakingHistoryDemo.java
java LeakingHistoryDemo
~~~

Output:

~~~text
before=100 records=1
after=100 records=1
history=FAKE withdrawal 999
~~~

Calling `clear` and then `add` completely alters the history list, while the balance of 100 remains unchanged. If the class has an invariant that the history reflects balance changes, the caller has broken that invariant without calling `deposit` or `withdraw`.

**Key takeaway:** Do not directly return mutable collections (or mutable arrays/objects) belonging to the internal representation if callers are not allowed to modify them.

## 6. `List.copyOf`, `Collections.unmodifiableList`, and Defensive Copies

Three common approaches to distinguish:

| How history is returned | Can caller modify via result? | Does it reflect source list changes? | Notes |
| --- | --- | --- | --- |
| `return history;` | **Yes**, if history is mutable | It is the same object | Does not protect representation |
| `return Collections.unmodifiableList(history);` | Cannot call mutating operations through the view | **Yes**, because the view is backed by the list | Read-only view, not a snapshot |
| `return List.copyOf(history);` | Cannot modify the returned list | Does not reflect subsequent additions/removals in the mutable source | Structural snapshot; elements may still be shared |
| `return new ArrayList<>(history);` | Can modify the returned list | Does not affect the source list when only adding/removing slots | Mutable shallow copy, may suit some APIs |

For a transaction history that callers must not modify, `List.copyOf(history)` is suitable because it works conveniently as a **read-only snapshot**. However, `List.copyOf` **does not deep-copy elements**. If each entry is a mutable `Transaction` class with setters, a recipient can still modify the fields of an entry to which the account also holds a reference.

In the main example, `Transaction` is a `record` whose components are only primitives and an enum; it exposes no mutable nested objects. Therefore, callers cannot modify an entry's contents through normal accessors.

### 6.1. A Record Does Not Guarantee Deep Immutability in All Cases

~~~java
record Report(java.util.List<String> lines) { }
~~~

This snippet is valid, but it does not protect `lines` on its own. If a caller passes a mutable list and keeps a reference to it, `Report` may observe the list changing. To make the record behave as a snapshot, you can normalize it in a compact constructor:

~~~java
record Report(java.util.List<String> lines) {
    Report {
        lines = java.util.List.copyOf(lines);
    }
}
~~~

In the second `Report` definition, the component field is initialized with an unmodifiable list snapshot. The `String` elements are immutable, which makes the snapshot more solid. These are two alternative versions with the same name and must not be declared simultaneously in a single source file.

**Note:** Even when the record is immutable, you must not grant the ability to create a "confirmed transaction" through a public API that lets callers submit arbitrary fake records into the history. **Account**, not the caller, must decide which records represent events that actually occurred.

## 7. Recording History and Balance on the Same Commit Path

A risky situation:

~~~java
void depositBad(long amount) {
    balanceCents += amount;
    history.add(new Transaction(/* ... */));
}
~~~

This is **illustrative pseudocode**, not a runnable method, because the `Transaction` constructor declaration is missing. It is error-prone if:

- Amount is not validated.
- Addition overflows.
- Creating the Transaction fails after the balance has already been increased.
- Callers have another path to write balance or history that skips one of the two steps.
- Another thread reads between the two updates when the code is not synchronized.

### 7.1. A Safer Sequence in a Single-Threaded Model

~~~text
1. Receive the deposit/withdraw request
2. Check that amount is valid
3. Check whether the balance is sufficient or whether addition overflows
4. Compute updatedBalance into a local variable
5. Create the intended immutable Transaction
6. Add the Transaction to the internal history
7. Assign balanceCents = updatedBalance
8. Method returns successfully
~~~

For all **anticipated** errors involving input, state, or overflow, the method throws before step 6. In a Java model with an internal ArrayList instance that is not aliased externally, this is a sequence that can be reasoned about and tested.

For failures outside the contract scope—such as out-of-memory errors, system crashes, or multiple threads reading/writing without synchronization—**you must not claim strict ACID transaction guarantees**. The section below separates the learning model from real-world system requirements.

### 7.2. Why Add to History First and Then Assign Balance?

In the main example, `appendAndCommit` uses:

~~~java
history.add(entry);
balanceCents = updatedBalance;
~~~

At this point, a valid `Transaction` already exists and `updatedBalance` has been precomputed. If `history.add` fails to complete and throws an exception, the subsequent balance assignment **does not run**. When `add` completes normally, assigning a primitive `long` is an operation without validation steps or I/O that could throw an exception in code.

A **window between the two statements** still exists: another thread accessing without synchronization could observe the updated history before the balance is updated. Therefore, the methods in the main example only guarantee consistent state under the contract of **no concurrent unsynchronized access**. For thread safety, the entire check + commit + snapshot sequence must be protected.

### 7.3. What If the Transaction Log Is Written to a Database?

When history lives in a database and balance is also persisted, these are two changes that must be coordinated via a **database transaction** or an appropriate consistency architecture. Protecting fields in a Java object **does not automatically roll back the database** when the second statement fails.

Patterns such as event sourcing, append-only ledgers, the outbox pattern, or a transaction manager may be appropriate, but they require dedicated design for durability, concurrency, duplicate requests, and recovery.

## 8. Ensuring Balance and Log Match via Replay

In a model without fees or interest, you can **recompute the balance** from history:

~~~text
running = 0
for each transaction in sequence:
    if DEPOSIT  then running = running + amount
    if WITHDRAW then running = running - amount
    verify running == transaction.balanceAfter
verify running == account.balanceCents
~~~

If there is an erroneous record or the balance was modified outside a transaction, a reconciliation check can detect the mismatch.

### 8.1. Standalone Runnable Program: Checking the Invariant from a Snapshot

Save **`HistoryInvariantDemo.java`**:

~~~java
import java.util.List;

public class HistoryInvariantDemo {
    enum Kind { DEPOSIT, WITHDRAW }

    record Transaction(
            long sequence, Kind kind,
            long amount, long balanceAfter) { }

    static long replayAndVerify(List<Transaction> history) {
        long running = 0;
        long expectedSequence = 1;

        for (Transaction item : history) {
            if (item.sequence() != expectedSequence++) {
                throw new IllegalStateException("sequence mismatch");
            }
            if (item.amount() <= 0) {
                throw new IllegalStateException("invalid amount");
            }

            if (item.kind() == Kind.DEPOSIT) {
                running = Math.addExact(running, item.amount());
            } else if (item.kind() == Kind.WITHDRAW) {
                if (item.amount() > running) {
                    throw new IllegalStateException("overdraft in log");
                }
                running -= item.amount();
            } else {
                throw new IllegalStateException("unknown kind");
            }

            if (item.balanceAfter() != running) {
                throw new IllegalStateException("balance mismatch");
            }
        }
        return running;
    }

    public static void main(String[] args) {
        List<Transaction> valid = List.of(
                new Transaction(1, Kind.DEPOSIT, 1000, 1000),
                new Transaction(2, Kind.WITHDRAW, 250, 750),
                new Transaction(3, Kind.DEPOSIT, 50, 800));

        System.out.println("replayed balance=" +
                replayAndVerify(valid));

        List<Transaction> invalid = List.of(
                new Transaction(1, Kind.DEPOSIT, 1000, 999));

        try {
            replayAndVerify(invalid);
        } catch (IllegalStateException expected) {
            System.out.println("tampered balance detected");
        }
    }
}
~~~

Compile/run:

~~~bash
javac HistoryInvariantDemo.java
java HistoryInvariantDemo
~~~

Output:

~~~text
replayed balance=800
tampered balance detected
~~~

**Explanation:**

- The valid list has three events: deposit 1000 → withdraw 250 → deposit 50, resulting in 800.
- Each `balanceAfter` is compared against the running total.
- The invalid list records the balance after the deposit as 999 instead of 1000; replay detects this and throws an exception.

**Not a complete security fraud-detection mechanism:** If an attacker has permission to modify **both the balance and all records**, an internal replay check can still match the tampered data. Real-world auditing requires access protection, durability, signatures/hashes, authorization, and appropriate immutable storage.

## 9. What Should a Transaction Object Contain?

A record in the main example contains:

| Field | Role | Suggested rule |
| --- | --- | --- |
| `sequence` | Transaction order within an account | Positive, consecutively increasing in the model |
| `kind` | `DEPOSIT` or `WITHDRAW` | Non-null, using an enum |
| `amountCents` | Transaction amount | Positive |
| `balanceAfterCents` | Balance after the operation | Non-negative; must match the change according to kind |

A larger system might add a unique `transactionId`, timestamp, currency, requestId/idempotency key, processing status, fee type, source/destination, actor, metadata, and audit trail.

### 9.1. Is a Timestamp Necessary?

It can be useful, but it is **not required** in a small example for understanding encapsulation. When recording time, distinguish among:

- **Business timestamp** (when the user created the request).
- **Timestamp when the system accepted/recorded the transaction**.
- **Timestamp when the transaction was completed/settled** (if applicable).

Do not use `LocalDateTime.now()` in a lesson requiring fixed stdout and then write an arbitrary timestamp as the exact output. For reproducible tests, use `Clock.fixed(...)` or inject a clock into the object.

### 9.2. Sequence Alone Is Not Enough as a System-Wide Transaction ID

`sequence` starting from 1, 2, 3 per account is not a global ID. Two accounts can both have transaction #1. For cross-account or database reconciliation, you need a key with sufficient information, such as `(accountId, sequence)` or a unique ID per your design.

### 9.3. Should `balanceAfter` Be Stored in the Record?

Benefit: easy to audit and display the state after each transaction. Drawback: adds a value that **could become inconsistent** if the logging code has a bug. In the example, `Account` creates the record based on the computed `updatedBalance` and can use replay for verification.

Another option is to store only the event kind and amount, computing the balance via replay when needed. This is a trade-off among performance, data redundancy, reliability, and logging architecture.

## 10. Exceptions and Guaranteeing Unchanged Data on Rejection

In the `Account` class from the main example:

| Call | Result | Balance/history |
| --- | --- | --- |
| `deposit(0)` | `IllegalArgumentException` | Unchanged |
| `deposit(-10)` | `IllegalArgumentException` | Unchanged |
| `withdraw(0)` | `IllegalArgumentException` | Unchanged |
| `withdraw(-5)` | `IllegalArgumentException` | Unchanged |
| `withdraw(1000)` when balance is 800 | `IllegalStateException` | Unchanged |
| `deposit(Long.MAX_VALUE)` when balance is 800 | `ArithmeticException` | Unchanged |
| `new Account(null)` | `IllegalArgumentException` | No account is successfully returned by the constructor |
| `new Account("  ")` | `IllegalArgumentException` | No account is successfully created for the caller |
| `history().clear()` | `UnsupportedOperationException` | Internal history is not modified |

The exception types can be replaced with **domain-specific exceptions** in a business API. What matters is a clear contract that distinguishes invalid input, disallowed state, and arithmetic errors.

Do not catch and silently ignore all exceptions:

~~~java
try {
    account.withdraw(1000);
} catch (Exception ignored) {
    // Do not silently make the caller think the withdrawal succeeded.
}
~~~

Callers need to know whether the operation was accepted. The examples use `catch` to **print illustrative output**, not as a recommendation to ignore errors in production software.

### 10.1. Do Not Record Failed Transactions in the Success Ledger

If `withdraw(1000)` is called when the balance is 800, the method must reject it before logging a success. There may be a separate **log of rejected requests** for audit/security purposes, but that is **not** a transaction that deducted from the balance.

Separate:

- **Ledger/successful transactions:** events that actually change the balance.
- **Operational/audit attempts:** requests, validations, rejections, technical errors; these may not change the balance.

Mixing the two without clear status/semantic fields will break the replay formula.

## 11. Should the Returned History Be a Snapshot or a Live View?

Suppose a caller executes:

~~~java
List<Transaction> firstRead = account.history();
account.deposit(25);
~~~

With `List.copyOf(history)` as in the main example, `firstRead` **does not automatically include** the deposit of 25. If the caller wants updated data, it calls `account.history()` again.

Benefits of a snapshot:

- The caller gets a stable result to display or process.
- The internal list structure cannot be modified.
- Avoids an iterator over a live mutable list seeing unexpected modifications during iteration in a non-concurrent model.

Drawbacks:

- Taking a snapshot from a mutable ArrayList incurs a copy cost proportional to the number of entries.
- For very large histories, copying the entire list can consume significant CPU and memory.
- Multiple snapshots may still reflect data from different points in time.

A large API can provide **pagination**, sequence-based queries, or persistence-based history queries. Do not arbitrarily return the internal `ArrayList` for callers to modify merely for performance optimization.

### 11.1. Do Not Equate a "Read-Only Interface" with "Immutable State"

Returning the type `List<Transaction>` only determines which methods the compiler sees through the interface; `List` still declares `add` and `remove`. If the actual implementation is the internal mutable `ArrayList`, callers can invoke those mutating methods.

There must be a corresponding **contract and implementation**: an unmodifiable snapshot, immutable records, or another appropriate protection mechanism.

## 12. Risks with Mutable Entry Objects

Suppose `record Transaction` is replaced with:

~~~java
class MutableTransaction {
    private long amount;

    MutableTransaction(long amount) {
        this.amount = amount;
    }

    void setAmount(long amount) {
        this.amount = amount;
    }

    long amount() {
        return amount;
    }
}
~~~

If history holds `MutableTransaction` objects and the getter returns `List.copyOf(history)`, callers cannot add or remove elements in the returned list, **but can still call `setAmount` on an entry** if access modifiers allow it. If that is the same entry object retained by history, the internal history gets modified.

Ways to protect against this:

1. Prefer an immutable record/value object containing no mutable references when the model permits.
2. If a mutable internal entry is unavoidable, return an **immutable DTO snapshot** constructed from the entry's state without exposing the mutable object.
3. For nested collections, copy to the required depth and clearly define ownership.

**Conclusion:** Immutability of the **list** and immutability of **each transaction** are two separate requirements. The main example addresses both with an unmodifiable list snapshot **and** immutable record components.

## 13. Verifying the Immutability of a Transaction Record

In Java 17, a record such as:

~~~java
record Transaction(
        long sequence,
        Kind kind,
        long amountCents,
        long balanceAfterCents) { }
~~~

causes the compiler to generate private final component fields and accessors such as `sequence()` and `amountCents()`. If the components consist only of primitive values and an enum, API consumers have no ordinary mutating setters.

However, keep in mind:

- A record does not automatically validate that `amountCents > 0`; the compact constructor in the main example does that.
- A record does not automatically guarantee that an entry **was actually an accepted transaction**; only `Account` controlling what gets appended to history guarantees that.
- A record does not automatically deep-copy mutable components such as a `List` or an array; for those types, defensive copying is required.
- Declaring a record is not a substitute for durable history storage design or system-level tamper-resistance mechanisms.

### 13.1. Why Use an Enum for the Transaction Kind?

`enum Kind { DEPOSIT, WITHDRAW }` prevents arbitrary strings such as `"DEPOSITT"`, `"minus"`, or `"withdraw!!"`. Code branching on transaction kind becomes clearer. However, a method can still receive a `null` enum if unchecked; therefore, the Transaction compact constructor calls `Objects.requireNonNull(kind)`.

A history with more event types will need an expanded enum and replay logic. If adding `REFUND`/`FEE`, you must determine the exact effect on the balance before recording the event.

## 14. Encapsulation Does Not Equal Business Security

A `private balanceCents` does not stop a caller authorized to invoke `deposit` from arbitrarily increasing the balance in this simple model. This is a lesson on class/object design techniques, not a real bank.

In a real system, you must define:

- **Authorization:** Who is allowed to perform which type of transaction?
- **Authentication:** Identifying the actor.
- **Idempotency:** Will a duplicated request be recorded twice?
- **Persistent transactions:** Are balance and ledger updates persisted reliably and consistently?
- **Concurrency control:** Can two concurrent withdrawal requests both read the stale balance?
- **Auditability:** Is the log protected against unauthorized modification/deletion and independently reconcilable?
- **Currency/precision:** Clear units and rounding rules.
- **Recovery:** Can state be recovered after a crash mid-operation?

None of this can be solved solely with `private`, `final`, or an unmodifiable list inside a Java object.

### 14.1. Why Should You Not Provide `public void addTransaction(...)`?

If callers can supply a `Transaction` themselves and the class simply appends it to the list, a caller can fabricate history without changing the balance. You must establish **ownership of event emission**: only operations validated by the class, such as `deposit` and `withdraw`, may append a successful transaction.

Even if an API is exposed to read history for the UI, **the API for recording successful history** must not be an arbitrary setter.

## 15. Transferring Between Two Accounts Is More Complex Than Deposit/Withdraw

A common design mistake:

~~~java
source.withdraw(amount);
destination.deposit(amount);
~~~

Suppose `source.withdraw(amount)` succeeds, but `destination.deposit(amount)` fails due to overflow or a storage error. At that point, the source has deducted the amount and recorded a withdrawal, while the destination has not credited it. The two objects can become **inconsistent in total funds**.

### 15.1. With Two Accounts, the Invariant Spans Objects

When transferring amount `m` from A to B, we want:

~~~text
A.balanceAfter = A.balanceBefore - m
B.balanceAfter = B.balanceBefore + m
Both record the corresponding transaction, or neither changes
~~~

This is an invariant **across two objects**, not within a single account alone. Calling two independent public methods **does not automatically guarantee atomicity**.

Design choices depend on the context:

- Pre-validate both accounts, and then use a locking/transaction mechanism to protect the entire commit.
- Use a dedicated transfer service to coordinate changes across both accounts.
- If the data resides in a DB, use an appropriate transaction and isolation level; also account for retries.
- For event-driven or distributed systems, a clearly designed consistency/idempotency/compensation strategy is required.

**Do not take `synchronized` on individual `withdraw`/`deposit` methods as proof that a two-object transfer is atomic.** Two sequential calls on two separate locks can still be observed in a half-completed transfer state.

## 16. Thread Safety: Protect Both Validation and Commit Together

In the main example, Account is **not yet thread-safe**. If two threads call `withdraw(700)` concurrently when the balance is 1000, both could read 1000 before either thread updates it, and then both would accept the withdrawal. This can break reconciliation between history and balance.

A simple way to model this is to synchronize all methods that read or write the related state on **the same monitor**. Standalone example:

Save **`SynchronizedAccountDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SynchronizedAccountDemo {
    record Entry(long amount, long balanceAfter) { }

    static final class Account {
        private long balance;
        private final List<Entry> entries = new ArrayList<>();

        synchronized void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            long next = Math.addExact(balance, amount);
            Entry entry = new Entry(amount, next);
            entries.add(entry);
            balance = next;
        }

        synchronized long balance() {
            return balance;
        }

        synchronized List<Entry> entries() {
            return List.copyOf(entries);
        }
    }

    public static void main(String[] args) {
        Account account = new Account();
        account.deposit(100);
        account.deposit(50);

        System.out.println("balance=" + account.balance());
        System.out.println("entries=" + account.entries().size());
    }
}
~~~

Run:

~~~bash
javac SynchronizedAccountDemo.java
java SynchronizedAccountDemo
~~~

Output:

~~~text
balance=150
entries=2
~~~

**Limitations of the synchronized example:**

- Every method in the example that accesses `balance` or `entries` is synchronized on **the same Account object**, which protects those existing operations from unsynchronized concurrent access through that API.
- However, a caller invoking `balance()` and then `entries()` in **two separate calls** can receive data from **two different points in time** if another thread makes a deposit in between. A `snapshot()` method that captures both balance and history under **the same lock** is required if you want a consistent view of both fields.
- In-memory `synchronized` does not automatically guarantee persistence/DB atomicity or transfers across multiple accounts.
- If other methods are added that read/write state without following the same synchronization contract, thread safety can be broken again.

### 16.1. Snapshotting Two Components Under the Same Lock

A conceptual example that can be placed inside a class with `balance` and `entries` fields:

~~~java
record AccountSnapshot(long balance, List<Entry> entries) {
    AccountSnapshot {
        entries = List.copyOf(entries);
    }
}

synchronized AccountSnapshot snapshot() {
    return new AccountSnapshot(balance, entries);
}
~~~

This is an **illustrative snippet**; `record AccountSnapshot` and the method need to be placed inside an appropriate class structure with an immutable `Entry`. When capturing the snapshot, both the balance and the list snapshot are read/copied under the same lock, avoiding receiving a pair from two different points in time.

In a real system, holding an object lock for a long time to copy a large history can hurt performance; consider pagination, snapshot versioning, or an appropriate storage architecture.

## 17. Testing Beyond the Happy Path

A class with invariants must be tested **before, during, and after** invalid operations.

### 17.1. Account Test Matrix

| Case | Expectation |
| --- | --- |
| `new Account("A")` | Balance 0, history empty |
| `new Account(null)` or `new Account("  ")` | Rejected |
| `deposit(100)` | Balance 100, history adds `DEPOSIT 100` |
| `withdraw(40)` after having 100 | Balance 60, history adds `WITHDRAW 40` |
| `deposit(0)`, `deposit(-1)` | Exception, state unchanged |
| `withdraw(0)`, `withdraw(-1)` | Exception, state unchanged |
| `withdraw(1000)` when balance is only 60 | Exception, state unchanged |
| Deposit causing `long` overflow | Exception, state unchanged |
| Call `history()` and then `clear()` | `UnsupportedOperationException`; internal history unchanged |
| Take an earlier snapshot, then deposit more | Earlier snapshot retains its entries |
| Replay successful entries | Matches current balance and each balanceAfter |
| Multiple threads depositing/withdrawing on the same Account | Concurrency tests required **if** the class advertises a thread-safe contract |

### 17.2. Testing State After Failures

Save **`RejectedOperationStateDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RejectedOperationStateDemo {
    static final class Account {
        private long balance;
        private final List<Long> deposits = new ArrayList<>();

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid amount");
            }
            long next = Math.addExact(balance, amount);
            deposits.add(amount);
            balance = next;
        }

        long balance() {
            return balance;
        }

        List<Long> deposits() {
            return List.copyOf(deposits);
        }
    }

    public static void main(String[] args) {
        Account account = new Account();
        account.deposit(10);

        long beforeBalance = account.balance();
        List<Long> beforeHistory = account.deposits();

        try {
            account.deposit(-5);
        } catch (IllegalArgumentException expected) {
            System.out.println("negative rejected");
        }

        System.out.println("balance unchanged=" +
                (beforeBalance == account.balance()));
        System.out.println("history unchanged=" +
                beforeHistory.equals(account.deposits()));

        try {
            account.deposit(Long.MAX_VALUE);
        } catch (ArithmeticException expected) {
            System.out.println("overflow rejected");
        }

        System.out.println("final=" + account.balance()
                + " history=" + account.deposits());
    }
}
~~~

Run:

~~~bash
javac RejectedOperationStateDemo.java
java RejectedOperationStateDemo
~~~

Output:

~~~text
negative rejected
balance unchanged=true
history unchanged=true
overflow rejected
final=10 history=[10]
~~~

This is an **auxiliary example managing deposits only** to isolate checking that state remains unchanged on failure. The main example is the full deposit/withdraw model with the Transaction record.

### 17.3. Why Not Compare Only the History Size?

A buggy method can **modify an entry's contents** while keeping the list size unchanged. Therefore, invariant tests should check:

- Balance.
- Number of entries.
- Order/sequence.
- Kind, amount, and balanceAfter of each entry.
- Whether records can be modified or removed via returned references.
- Whether replaying the history matches the balance.

With immutable transaction values and unmodifiable snapshots, testing and reasoning become much more reliable.

## 18. Common Design Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| `public balanceCents` | Callers increment/decrement arbitrarily | `private` field and valid operations |
| `private balance` but public `setBalance(any)` | Callers still break invariants via the setter | Prefer `deposit`/`withdraw` and validation |
| Checking amount after updating balance | Failure leaves invalid state behind | Validate before commit |
| Adding `long` without checking overflow | Balance can overflow into negative numbers | `Math.addExact` or an appropriate monetary type |
| Withdrawing when amount > balance | Can produce a negative balance | Check before subtracting |
| Allowing callers to write history directly | Callers add fake transactions or remove real ones | Only Account appends when an operation is accepted |
| Returning internal `ArrayList` via getter | Callers modify/clear history | Return an unmodifiable snapshot |
| Using `Collections.unmodifiableList(internal)` thinking it is a snapshot | A live view can reflect subsequent changes | Use `List.copyOf` if a snapshot is needed |
| `List.copyOf` with mutable entries | Callers modify entries through references | Immutable transactions or DTO copies |
| Record containing a mutable list/array treated as deeply immutable | Component reference still points to a mutable object | Defensive copy in constructor/accessor |
| Transaction with wrong `balanceAfter` | Ledger cannot reconstruct the balance | Create entry from updatedBalance and verify via replay |
| Logging rejected transactions as successful ones | Ledger and balance do not match | Separate the successful ledger from audit attempts |
| Swallowing exceptions and reporting success | Callers misinterpret the outcome | Propagate or return a domain error per the contract |
| Assuming `private` alone prevents unauthorized access | Lacks authorization and persistence controls | Design security at the application and DB layers |
| Treating separate `withdraw`/`deposit` calls as an atomic transfer | Failure mid-way leaves accounts out of sync | Coordinate transactions/locking per the architecture |
| Sharing an Account across threads without synchronization | Races, inconsistent state/history | Synchronize checks + updates + snapshots |
| Thinking `final history` makes the list immutable | Final only locks the field reference | Avoid exposing the mutable list; use a copy |

## 19. Design Process Applicable to Similar Problems

When building a class that stores **primary state** and a **history of state changes**, proceed step by step:

1. **Identify state and units:** balance in cents/minor units; amounts must use the same unit.
2. **Define invariants:** non-negative balance; history reconstructs state; every event is valid.
3. **Hide representation:** private fields; no direct public setters for critical state.
4. **Choose valid commands:** `deposit`, `withdraw` with clear names and contracts.
5. **Validate upfront:** amount, sufficient balance, overflow, current state.
6. **Compute candidate state:** avoid mutating the object piecemeal and discovering errors afterward.
7. **Create an immutable event:** from actual transaction data and post-success state.
8. **Controlled commit:** history and balance must change as one logical operation; define failure semantics.
9. **Return read models only:** snapshots/unmodifiable collections, without exposing mutable internals.
10. **Verify reconciliation:** replay and check sequence/amount/balanceAfter.
11. **Define the concurrency contract:** do not share across threads or synchronize completely; snapshot related state together when needed.
12. **Test failure cases too:** invalid amounts, insufficient funds, overflow, history mutation, and concurrent requests if applicable.

A well-protected class makes it **difficult for callers to put data into an inconsistent state**, rather than merely telling users "do not edit balance manually".

## 20. Self-Check Questions with Answers

**Question 1.** Why can't you declare `public long balanceCents` and expect callers to only invoke `withdraw`?  
**Answer:** Because callers can still directly assign a negative value or a value without a corresponding history event.

**Question 2.** Is the `private final ArrayList<Transaction> history` field enough to protect history if a getter returns `history`?  
**Answer:** No. `final` only prevents reassigning the field reference; callers receiving the same ArrayList can still call `clear` or `add`.

**Question 3.** Why must `deposit(-10)` be rejected before computing and recording?  
**Answer:** A deposit amount must not be negative; if it were still processed, balance and history could reflect an invalid business operation.

**Question 4.** Why is `Math.addExact` needed in the example using `long`?  
**Answer:** To detect overflow and avoid storing an overflowed balance.

**Question 5.** When withdrawing 1000 from a balance of 800, should the history record `WITHDRAW 1000` in the successful transactions ledger?  
**Answer:** No. The operation is rejected, and both the balance and successful history remain unchanged. Audit attempts are a separate concern.

**Question 6.** If both `balance` and `history` fields are private, yet a method increases balance while forgetting to record history, which invariant is broken?  
**Answer:** The balance is no longer fully explained by the history of successful events.

**Question 7.** Is `List.copyOf(history)` a live view or a structural snapshot of the mutable history?  
**Answer:** A structural snapshot; subsequent additions or removals in the mutable history do not appear in the returned list.

**Question 8.** Can `Collections.unmodifiableList(history)` reflect transactions that Account appends later?  
**Answer:** Yes, because it is an unmodifiable **view** attached to the backing list, not necessarily a snapshot.

**Question 9.** Why does the record `Transaction(long amount, long balanceAfter)` not automatically guarantee an authentic history?  
**Answer:** A record is just a data type; callers can instantiate any record if the constructor is accessible. Only Account's logic controlling which events are appended guarantees successful events.

**Question 10.** Why is `List.copyOf` alone insufficient if each entry has a `setAmount` setter?  
**Answer:** The list cannot be modified, but the entry objects can still be mutable and shared. Immutable entries or appropriate element copies are needed.

**Question 11.** After two transactions totaling a balance of 750, the caller gets `snapshot = account.history()`; then Account deposits another 50. Does the earlier snapshot automatically grow to three entries?  
**Answer:** No. With `List.copyOf`, it retains the two entries present when it was created.

**Question 12.** If a caller gets `history()` and calls `clear()`, what happens in the main example?  
**Answer:** The returned list is unmodifiable, so it throws `UnsupportedOperationException`; the internal history remains intact.

**Question 13.** Why is it risky for a method to update balance first and only then attempt to create the Transaction?  
**Answer:** If creating or appending the event fails, the balance may already have changed without the ledger recording it.

**Question 14.** What benefit does `balanceAfter` provide, and what must be checked?  
**Answer:** It helps observe the state after each transaction, but it must be reconciled against adding/subtracting events in order to avoid storing inconsistent redundant data.

**Question 15.** Are two transactions that both have sequence 1 but belong to two different accounts the same event?  
**Answer:** No. Sequence only increments within a single account in this model; account identity or a global ID is needed to distinguish them.

**Question 16.** When transferring funds between two accounts, is calling `source.withdraw` followed by `destination.deposit` enough to guarantee atomicity?  
**Answer:** No. If the second operation fails, the source has already been debited. An appropriate coordination/transaction mechanism is needed.

**Question 17.** Why does `private` not automatically prevent double-spend when two threads withdraw concurrently?  
**Answer:** It only blocks direct field access from callers; it does not synchronize checks and updates across threads.

**Question 18.** If Account exposes `balance()` and `history()` as both synchronized, but a caller invokes them separately, will it always receive values from the same point in time?  
**Answer:** No. Another thread can perform an update between the two calls. A combined snapshot under the same lock is needed for a consistent view.

**Question 19.** For monetary data, why is `double` generally not chosen to store exact amounts?  
**Answer:** Certain decimal fractions do not have exact binary representations; use a money type with currency/scale or `BigDecimal` when business requirements call for it.

**Question 20.** What does a history replay that detects a `balanceAfter` mismatch help ensure, and what does it not ensure?  
**Answer:** It helps detect inconsistencies among existing events; it does not automatically ensure that the history was not tampered with by an actor permitted to modify multiple fields simultaneously.

## References

- Java Language Specification, [`6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): restricting access to fields and methods.
- Java Language Specification, [`8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): field declarations, `private`, and `final`.
- Java Platform API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): returning an unmodifiable list containing the current elements.
- Java Platform API, [`Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): read-only view of a backing list.
- Java Platform API, [`Math.addExact(long,long)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)): overflow detection.
- Java Platform API, [`Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): modeling record values, combining validation and choosing immutable components.

## Key Takeaways

In an account with a balance and transaction history, **successful encapsulation** means callers only request `deposit`/`withdraw` while **Account itself takes responsibility** for validating the amount, computing the new balance, recording successful events, rejecting invalid operations, and maintaining reconcilability.

Hiding `balance` and `history` with `private` is only the first step. You must prevent callers from modifying history via getters, protect each transaction entry from mutable aliases, prevent overflow, and ensure failed operations do not alter the balance or ledger. `List.copyOf` together with an immutable `record Transaction` is a simple solution for a **read snapshot**. For multithreading, persistence, or transfers between accounts, you must add synchronization/transactions, authorization, durability, and audit controls; `private` does not replace those mechanisms on its own.
