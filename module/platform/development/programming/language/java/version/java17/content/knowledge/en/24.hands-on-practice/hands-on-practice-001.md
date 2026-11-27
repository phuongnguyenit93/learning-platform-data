# Transaction Modeling with Sealed Interfaces and Records in Java 17

When building a ledger or payment processing system, an application typically has multiple transaction types: deposits, withdrawals, transfers, refunds, or balance adjustments. Each transaction type has its own specific data yet participates in a shared processing workflow. If you model them with one large class containing many nullable fields, the code can easily enter invalid states—for example, a withdrawal having a destination account or a transfer missing a source account.

Java 17 provides two features well suited for modeling this domain:

- **Record** represents a structured group of data, typically immutable, with a constructor, accessors, `equals`, `hashCode`, and `toString` generated automatically.
- **Sealed interface/class** restricts which types are permitted to implement or extend a supertype.

Combining these two features lets you define a closed set of transactions where each transaction type is its own record. The compiler knows which direct types are permitted to belong to that abstraction, while records keep transaction data structured and easy to validate for invariants.

This lesson builds a simple ledger model with deposit, withdrawal, and transfer transactions; explains how to design records, validate data, handle each transaction type, ensure idempotency at the model level, and recognize the limitations when adapting the example to a production system.

## 1. Why Use Sealed Interfaces and Records?

Suppose an application has a common type named `Transaction`. Every transaction has an identifier and a timestamp of occurrence, but each type carries different data:

| Transaction type | Specific data |
| --- | --- |
| Deposit | Receiving account and amount |
| Withdrawal | Debited account and amount |
| Transfer | Source account, destination account, and amount |

You could use a single class with fields like `sourceAccount`, `destinationAccount`, `amount`, and `type`. However, that approach allows many invalid field combinations:

- Deposit does not need `sourceAccount`.
- Withdrawal does not need `destinationAccount`.
- Transfer requires both `sourceAccount` and `destinationAccount`.
- A `type` field might not match the fields currently populated.

A better model represents each case with its own dedicated type:

~~~text
                 Transaction
                (sealed interface)
                 /     |      \
                /      |       \
           Deposit Withdrawal Transfer
            record    record    record
~~~

The **sealed interface** closes the set of permitted transaction types. **Records** represent the data of each case using explicit components.

## 2. Records in Java 17

A record is a kind of class designed to carry data. For example:

~~~java
public record CustomerId(String value) {
}
~~~

The declaration above is equivalent to a class with:

- a private final field for the `value` component;
- a constructor accepting `value`;
- an accessor named `value()`;
- `equals()` and `hashCode()` based on the components;
- `toString()` representing the record name and component values.

Usage:

~~~java
CustomerId id = new CustomerId("C-100");
System.out.println(id.value());
System.out.println(id);
~~~

A record accessor uses the exact component name, such as `value()`, rather than generating `getValue()` by default like some JavaBeans.

Records are implicitly `final`. They cannot be extended by another class, though they can implement interfaces. A record also cannot declare arbitrary additional instance fields; instance state must be represented through record components.

### 2.1. A Record Does Not Guarantee Valid Data

A record's default constructor only assigns the components. If the business domain requires a value to be non-null, non-blank, or within a range, validate it in the constructor.

For example:

~~~java
public record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer ID must not be blank");
        }
        value = value.trim();
    }
}
~~~

This is a **compact canonical constructor**. It can validate or normalize parameters. After the constructor completes normally, Java automatically assigns the normalized parameters to their corresponding components.

### 2.2. Records Are Shallowly Immutable

Record components are stored in `final` fields. However, if a component points to a mutable object, that object's contents can still be modified:

~~~java
public record Report(List<String> warnings) {
}
~~~

Even though the `warnings` field is `final`, the caller can still modify the passed-in list if it is mutable. When you need an immutable snapshot, make a defensive copy:

~~~java
public record Report(List<String> warnings) {
    public Report {
        warnings = List.copyOf(warnings);
    }
}
~~~

In a transaction model, prefer immutable component types such as `String`, `UUID`, `Instant`, `BigDecimal`, `Currency`, and other immutable records. For collections, always consider defensive copying.

## 3. Sealed Interfaces in Java 17

A sealed interface restricts the direct types permitted to implement it:

~~~java
public sealed interface Transaction
        permits Deposit, Withdrawal, Transfer {
}
~~~

The `permits` clause specifies the accepted subtypes. The listed types must directly implement this interface.

Each direct subtype of a sealed class/interface must declare one of three modifiers:

- **final:** disallows further subclassing/implementation;
- **sealed:** continues restricting its own subtypes;
- **non-sealed:** reopens inheritance for that branch.

Because a record is implicitly `final`, a record can directly implement a sealed interface without writing the `final` keyword explicitly.

### 3.1. Package and Module Rules

Permitted direct subtypes must follow placement rules:

- If the supertype is in a named module, its permitted subtypes must reside in the same module.
- If the supertype is in an unnamed module, its permitted subtypes must reside in the same package.

In this lesson's example, `Transaction`, `Deposit`, `Withdrawal`, and `Transfer` are placed in the same package of an application module. This keeps the `permits` list clear and valid.

### 3.2. When to Use non-sealed?

If one branch needs to be extensible by other code, you can mark that subtype as `non-sealed`:

~~~java
public sealed interface Transaction
        permits StandardTransaction, ExtensionTransaction {
}

public sealed interface StandardTransaction
        extends Transaction
        permits Deposit, Withdrawal {
}

public non-sealed interface ExtensionTransaction
        extends Transaction {
}
~~~

The `ExtensionTransaction` branch allows other types to implement it further. However, when opening a branch like this, code handling `Transaction` must account for new subtypes that may appear.

If the domain has a controlled set of transaction types, keep the hierarchy closed using `final` records and appropriate `sealed` subtypes. Use `non-sealed` only when extensibility is genuinely part of the API contract.

## 4. Designing the Money Domain with a Record

Avoid using `double` to represent money in financial transactions because binary floating-point numbers may not represent decimal values like `0.1` accurately. Use `BigDecimal` and an explicit currency code.

In this example, the `Money` record uses `BigDecimal` together with `java.util.Currency`:

~~~java
package com.acme.ledger;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits < 0) {
            throw new IllegalArgumentException(
                    "Currency has no standard fraction digits");
        }

        amount = amount.setScale(
                fractionDigits, RoundingMode.UNNECESSARY);
    }

    public static Money of(String amount, String currencyCode) {
        String code = Objects.requireNonNull(currencyCode)
                .trim()
                .toUpperCase(Locale.ROOT);
        return new Money(
                new BigDecimal(amount),
                Currency.getInstance(code));
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    public boolean isPositive() {
        return amount.signum() > 0;
    }

    public boolean isNegative() {
        return amount.signum() < 0;
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "Cannot combine different currencies");
        }
    }

    @Override
    public String toString() {
        return amount.toPlainString() + " " + currency.getCurrencyCode();
    }
}
~~~

Key design decisions in this record:

- `amount` and `currency` must not be `null`.
- `Currency` determines the standard number of fractional digits.
- `setScale` with `RoundingMode.UNNECESSARY` normalizes `1.2` to `1.20` while rejecting rounding that loses fractional precision.
- `add` and `subtract` require the same currency.
- `Money` allows negative numbers to represent intermediate results; transaction records will enforce positive amounts, and `Ledger` will guarantee non-negative balances.

Example:

~~~java
Money a = Money.of("10.5", "USD");
Money b = Money.of("2.25", "USD");
System.out.println(a.add(b)); // 12.75 USD
~~~

The `Currency` and default fraction digits in this example fit ISO currencies supported by the JDK. If a system needs digital assets, tokens, internal units, or specialized currency rules, build a dedicated currency catalog and scale policy; `java.util.Currency` does not model every kind of asset.

## 5. Defining Transaction and the Transaction Records

Create the sealed interface:

**Transaction.java**

~~~java
package com.acme.ledger;

import java.time.Instant;
import java.util.UUID;

public sealed interface Transaction
        permits Deposit, Withdrawal, Transfer {

    UUID id();

    Instant occurredAt();
}
~~~

The interface declares the shared attributes:

- `id`: unique identifier of the transaction;
- `occurredAt`: business timestamp when the transaction occurred.

Each specific transaction type provides the corresponding components.

### 5.1. Deposit

**Deposit.java**

~~~java
package com.acme.ledger;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record Deposit(
        UUID id,
        String accountId,
        Money amount,
        Instant occurredAt
) implements Transaction {

    public Deposit {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (accountId == null || accountId.isBlank()) {
            throw new IllegalArgumentException(
                    "Account ID must not be blank");
        }
        accountId = accountId.trim();

        if (!amount.isPositive()) {
            throw new IllegalArgumentException(
                    "Deposit amount must be positive");
        }
    }
}
~~~

`Deposit` contains only the receiving account and the amount. There is no source account field.

### 5.2. Withdrawal

**Withdrawal.java**

~~~java
package com.acme.ledger;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record Withdrawal(
        UUID id,
        String accountId,
        Money amount,
        Instant occurredAt
) implements Transaction {

    public Withdrawal {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (accountId == null || accountId.isBlank()) {
            throw new IllegalArgumentException(
                    "Account ID must not be blank");
        }
        accountId = accountId.trim();

        if (!amount.isPositive()) {
            throw new IllegalArgumentException(
                    "Withdrawal amount must be positive");
        }
    }
}
~~~

`Withdrawal` contains the debited account and a positive amount. The rule checking whether the account has sufficient balance is enforced when applying the transaction to the ledger.

### 5.3. Transfer

**Transfer.java**

~~~java
package com.acme.ledger;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record Transfer(
        UUID id,
        String fromAccountId,
        String toAccountId,
        Money amount,
        Instant occurredAt
) implements Transaction {

    public Transfer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (fromAccountId == null || fromAccountId.isBlank()) {
            throw new IllegalArgumentException(
                    "Source account ID must not be blank");
        }
        if (toAccountId == null || toAccountId.isBlank()) {
            throw new IllegalArgumentException(
                    "Destination account ID must not be blank");
        }

        fromAccountId = fromAccountId.trim();
        toAccountId = toAccountId.trim();

        if (fromAccountId.equals(toAccountId)) {
            throw new IllegalArgumentException(
                    "Source and destination must be different");
        }
        if (!amount.isPositive()) {
            throw new IllegalArgumentException(
                    "Transfer amount must be positive");
        }
    }
}
~~~

`Transfer` verifies that the two accounts are different and that the amount is positive. Checking that both accounts exist and share the same currency happens when the transaction is applied.

### 5.4. Why Records Fit Transactions Well

Once created, a transaction should not be arbitrarily mutated. Records provide:

- `final` components;
- concise, clear accessors;
- data-based `equals`/`hashCode`;
- a convenient `toString` for debugging (though sensitive data should not be logged);
- a constructor to centralize input validation.

A record does not automatically make its entire object graph immutable. In this example, the components—`UUID`, `String`, `Instant`, and `Money`—are already designed to be immutable, so each transaction represents a stable data snapshot.

## 6. Handling Transaction Types with instanceof Pattern Matching

Once you have a `Transaction`, a handler function can accept the supertype and branch by subtype:

~~~java
static void describe(Transaction transaction) {
    if (transaction instanceof Deposit deposit) {
        System.out.println(
                "Deposit " + deposit.amount()
                        + " into " + deposit.accountId());
    } else if (transaction instanceof Withdrawal withdrawal) {
        System.out.println(
                "Withdraw " + withdrawal.amount()
                        + " from " + withdrawal.accountId());
    } else if (transaction instanceof Transfer transfer) {
        System.out.println(
                "Transfer " + transfer.amount()
                        + " from " + transfer.fromAccountId()
                        + " to " + transfer.toAccountId());
    } else {
        throw new IllegalStateException(
                "Unsupported transaction type: "
                        + transaction.getClass().getName());
    }
}
~~~

Pattern matching for `instanceof` became a finalized feature in Java 16, so it works normally in Java 17 without enabling preview features.

A sealed interface restricts the valid subtypes, but the `if/else` chain above is not compiler-checked for exhaustiveness like a finalized pattern switch. The final branch remains useful for catching cases where the model changed or handling code has not been updated.

**Version note:** pattern matching for `switch` is still a preview feature in Java 17. This example uses stable `instanceof` pattern matching without `--enable-preview`. When developing on Java 17, do not treat pattern `switch` as finalized syntax.

## 7. Modeling Balances with a Ledger Record

We need a ledger state holding each account's balance and the set of applied transaction IDs. Use a record to represent an immutable snapshot:

**Ledger.java**

~~~java
package com.acme.ledger;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public record Ledger(
        Map<String, Money> balances,
        Set<UUID> appliedTransactionIds
) {
    public Ledger {
        balances = Map.copyOf(balances);
        appliedTransactionIds = Set.copyOf(appliedTransactionIds);

        balances.forEach((accountId, balance) -> {
            if (accountId.isBlank()) {
                throw new IllegalArgumentException(
                        "Account ID must not be blank");
            }
            if (balance.isNegative()) {
                throw new IllegalArgumentException(
                        "Account balance must not be negative");
            }
        });
    }

    public Ledger apply(Transaction transaction) {
        Objects.requireNonNull(transaction, "transaction");

        if (appliedTransactionIds.contains(transaction.id())) {
            return this;
        }

        Map<String, Money> nextBalances =
                new HashMap<>(balances);

        if (transaction instanceof Deposit deposit) {
            Money current = requireBalance(
                    nextBalances, deposit.accountId());
            nextBalances.put(
                    deposit.accountId(),
                    current.add(deposit.amount()));

        } else if (transaction instanceof Withdrawal withdrawal) {
            Money current = requireBalance(
                    nextBalances, withdrawal.accountId());
            Money updated = current.subtract(withdrawal.amount());

            if (updated.isNegative()) {
                throw new IllegalArgumentException(
                        "Insufficient funds");
            }

            nextBalances.put(withdrawal.accountId(), updated);

        } else if (transaction instanceof Transfer transfer) {
            Money source = requireBalance(
                    nextBalances, transfer.fromAccountId());
            Money destination = requireBalance(
                    nextBalances, transfer.toAccountId());

            Money updatedSource =
                    source.subtract(transfer.amount());
            Money updatedDestination =
                    destination.add(transfer.amount());

            if (updatedSource.isNegative()) {
                throw new IllegalArgumentException(
                        "Insufficient funds");
            }

            nextBalances.put(
                    transfer.fromAccountId(), updatedSource);
            nextBalances.put(
                    transfer.toAccountId(), updatedDestination);

        } else {
            throw new IllegalStateException(
                    "Unsupported transaction type: "
                            + transaction.getClass().getName());
        }

        Set<UUID> nextIds =
                new HashSet<>(appliedTransactionIds);
        nextIds.add(transaction.id());

        return new Ledger(nextBalances, nextIds);
    }

    private static Money requireBalance(
            Map<String, Money> balances,
            String accountId) {
        Money balance = balances.get(accountId);
        if (balance == null) {
            throw new IllegalArgumentException(
                    "Unknown account: " + accountId);
        }
        return balance;
    }
}
~~~

### 7.1. Immutable Snapshots and Defensive Copies

The `Ledger` constructor calls:

- `Map.copyOf(balances)`;
- `Set.copyOf(appliedTransactionIds)`.

This prevents callers from mutating the map or set after constructing `Ledger`. If you only declare the components as `final` while keeping the mutable `HashMap`/`HashSet` passed in by the caller, the record could still be mutated indirectly.

### 7.2. Each apply Returns a New Ledger

The `apply` method:

1. Checks whether the transaction has already been applied.
2. Copies the current balances into a new map.
3. Computes the new balances.
4. Enforces business rules such as account existence and sufficient funds.
5. Adds the transaction ID to the set of processed IDs.
6. Returns a new `Ledger`.

If computation fails, the original `Ledger` remains unchanged. For `Transfer`, both source and destination balances are computed before updating the new map, so no intermediate state is ever exposed.

### 7.3. Currency Validation

`Money.add()` and `Money.subtract()` reject operations between two different currencies. Consequently:

- `Deposit` only succeeds if the balance and amount share the same currency.
- `Withdrawal` only succeeds if the balance and amount share the same currency.
- `Transfer` requires `amount` to be compatible with both the source and destination balances.

If two accounts have different currencies, `Transfer` is rejected in this model. Foreign currency conversion requires a separate model with exchange rates, effective timestamps, rate sources, fees, and rounding rules.

## 8. Running the Ledger Model

Example program:

**LedgerDemo.java**

~~~java
package com.acme.ledger;

import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

public class LedgerDemo {
    public static void main(String[] args) {
        Ledger ledger = new Ledger(
                Map.of(
                        "A-100", Money.of("100.00", "USD"),
                        "B-200", Money.of("25.00", "USD")
                ),
                Set.of()
        );

        Transfer transfer = new Transfer(
                UUID.fromString(
                        "11111111-1111-1111-1111-111111111111"),
                "A-100",
                "B-200",
                Money.of("10.00", "USD"),
                Instant.parse("2026-01-15T10:00:00Z")
        );

        ledger = ledger.apply(transfer);

        System.out.println(ledger.balances());
        // A-100 = 90.00 USD
        // B-200 = 35.00 USD

        Ledger afterDuplicate = ledger.apply(transfer);
        System.out.println(afterDuplicate.balances());
        // Does not debit/credit a second time.
    }
}
~~~

Compile the files in the package:

~~~bash
javac -d out src/com/acme/ledger/*.java
java -cp out com.acme.ledger.LedgerDemo
~~~

The example above demonstrates in-memory modeling and state computation. It is not yet a banking system or a durable bookkeeping mechanism.

## 9. Idempotency and Transaction Identifiers

In distributed systems, a request may be resent due to a timeout, a retry, or the client failing to receive a response. If the same transaction is applied twice, balances could be updated repeatedly.

The `Ledger` in this example stores `appliedTransactionIds`. When encountering an existing ID, `apply` returns the current snapshot:

~~~java
if (appliedTransactionIds.contains(transaction.id())) {
    return this;
}
~~~

This illustrates idempotency by transaction ID. To apply this in a production system:

- The ID must be generated by a trusted source or validated according to the request contract.
- The ID needs a clear uniqueness scope, such as per tenant or per account where appropriate.
- Duplicate ID checking and entry persistence must occur atomically within the same storage transaction.
- You must define how to handle the same ID being resent with a different payload.
- The idempotency table requires an appropriate retention policy and a unique index in the database.

An in-memory `Set` is insufficient across multiple instances, restarts, or concurrent processing. It only illustrates the concept at the model level.

## 10. Distinguishing Command, Transaction, and Event

In domain design, the word "transaction" can refer to multiple concepts. Name them clearly:

| Concept | Meaning | Example |
| --- | --- | --- |
| Command | A request for the system to perform an action. | `TransferFunds(from, to, amount)` |
| Transaction/domain operation | A business workflow that validates and executes an action. | Checking balance, limits, account status. |
| Event/ledger entry | An accepted and recorded event or accounting entry. | `FundsTransferred`, `DepositPosted` |
| Database transaction | The commit/rollback boundary of storage. | `BEGIN`, `UPDATE balances`, `INSERT ledger`, `COMMIT`. |

The `Deposit`, `Withdrawal`, and `Transfer` records in the example act as transaction data created to be applied to the ledger. In a production system, you can separate unaccepted commands from committed events/entries.

For example:

~~~java
public sealed interface TransferCommand
        permits CreateTransfer {
}

public record CreateTransfer(
        String fromAccountId,
        String toAccountId,
        Money amount,
        UUID requestId
) implements TransferCommand {
}
~~~

Only after processing the command successfully does the application create an event or ledger entry with an ID and posting timestamp. This separation distinguishes "a user requested a transfer" from "the transfer was accepted and posted by the system".

## 11. Extending the Model with Reversal Transactions

If the domain needs `Reversal`, you can add a new record to `permits`:

~~~java
public sealed interface Transaction
        permits Deposit, Withdrawal, Transfer, Reversal {
    UUID id();
    Instant occurredAt();
}
~~~

The `Reversal` record can reference the original transaction:

~~~java
public record Reversal(
        UUID id,
        UUID originalTransactionId,
        Money amount,
        Instant occurredAt
) implements Transaction {

    public Reversal {
        if (id == null || originalTransactionId == null
                || amount == null || occurredAt == null) {
            throw new IllegalArgumentException(
                    "Reversal fields must not be null");
        }
        if (id.equals(originalTransactionId)) {
            throw new IllegalArgumentException(
                    "A transaction cannot reverse itself");
        }
        if (!amount.isPositive()) {
            throw new IllegalArgumentException(
                    "Reversal amount must be positive");
        }
    }
}
~~~

After adding the subtype, all `Transaction` handling logic must be updated to define the reversal rules. The example above only performs basic data validation; it does not yet verify that the original transaction exists, has not already been reversed, is within the refund window, or uses the same currency.

A sealed hierarchy makes type expansion an intentional change: both `permits` and the corresponding business handlers must be updated.

## 12. When to Use a Sealed Interface Instead of an Enum?

An `enum` fits when each case only needs a single value from a fixed set of constants:

~~~java
public enum TransactionType {
    DEPOSIT,
    WITHDRAWAL,
    TRANSFER
}
~~~

An `enum` is simple for storing a transaction type, but it does not by itself constrain the specific data for each type. You would still need a shared class with many fields or multiple separate data structures.

A sealed interface combined with records fits when each case has its own data structure:

~~~java
Transaction transaction =
        new Transfer(
                UUID.randomUUID(),
                "A-100",
                "B-200",
                Money.of("10.00", "USD"),
                Instant.now());
~~~

You can use both if an `enum` is needed to represent a type code in an external protocol, but avoid maintaining two unsynchronized sources of truth between an enum `type` field and the actual subtype.

| Need | Choice |
| --- | --- |
| Simple list of states/types without distinct payloads | `enum` |
| Each case carries its own data | `sealed interface` + `records` |
| API allowing third parties to add implementations | Regular `interface` or an intentional `non-sealed` branch |
| Data transmitted via JSON/message broker | Sealed model plus explicitly configured serializer/schema |

## 13. Pattern Matching and Exhaustive Handling in Java 17

A sealed interface informs the compiler of its direct subtypes. However, in Java 17, pattern matching for `switch` is still a preview feature. If you want code that does not depend on preview features, use `instanceof` pattern matching:

~~~java
if (transaction instanceof Deposit deposit) {
    processDeposit(deposit);
} else if (transaction instanceof Withdrawal withdrawal) {
    processWithdrawal(withdrawal);
} else if (transaction instanceof Transfer transfer) {
    processTransfer(transfer);
} else {
    throw new IllegalStateException("Unknown transaction");
}
~~~

You do not need `--enable-preview` for this syntax in Java 17.

If a project intentionally opts into Java 17 preview features, pattern `switch` can be tested with the corresponding compiler and runtime preview flags. However, preview syntax may change between releases; do not put it into stable APIs if the target is non-preview Java 17.

## 14. Validating Invariants in the Right Layer

A good model splits validation by responsibility:

| Layer | Example invariants |
| --- | --- |
| `Money` | Non-null amount/currency, valid scale, same-currency addition/subtraction |
| `Deposit`/`Withdrawal` | Valid ID and timestamp, non-blank account ID, positive amount |
| `Transfer` | Distinct source/destination accounts, both IDs valid, positive amount |
| `Ledger` | Snapshot has no negative balances, defensively copied map/set |
| Use case/domain service | Account exists, sufficient funds, limits, and account status |
| Persistence/database | Atomic ledger entry write and balance update, unique ID, transaction isolation |

Do not cram all validation into record constructors. A record can enforce intrinsic invariants of the data it represents; rules that require access to a repository, system clock, or multiple aggregates typically belong in an application or domain service.

For example, whether an account exists requires inspecting the ledger or repository, so it cannot be verified solely inside the `Transfer` constructor.

## 15. Important Limitations of the Sample Model

The `Ledger` in this lesson is an in-memory learning model. Before using it for real money or multi-user systems, additional mechanisms are required:

### 15.1. Atomicity and Concurrency

Two threads may read the same `Ledger` snapshot simultaneously and produce two new snapshots. If the application overwrites the reference without synchronization, one update can be lost.

Immutable records make snapshots easy to share, but they do not provide transaction isolation on their own. In production, use database transactions, optimistic locking/versioning, row locking, or appropriate synchronization.

### 15.2. Durability

An in-memory ledger loses data when the process stops. Real systems require durable entry storage, backups, recovery, and write-order control.

### 15.3. Double-Entry Accounting

The example updates a balance map directly for clarity. Accounting systems typically use ledger entries with debits/credits and a rule that total debits equal total credits. Balances can be computed from entries or maintained as a reconcilable projection.

### 15.4. Currency Conversion and Fees

The sample `Transfer` only supports two accounts in the same currency with no fees. Currency conversion requires exchange rates, rate sources, lock-in timestamps, rounding policies, and discrepancy accounting.

### 15.5. Authorization and Audit

Sealed interfaces and records do not verify whether the caller is authorized to transfer funds. Systems need authentication, authorization, limits, fraud checks, audit trails, and dispute-handling workflows.

### 15.6. Serialization and Schema Evolution

Records and sealed hierarchies do not automatically create compatible schemas for JSON or message brokers. When serializing outside the process, you must define discriminators, versioning, subtype mapping, and a policy for unknown subtypes.

## 16. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Cannot add subtype to sealed interface | Subtype is missing from `permits` or violates package/module rules. | Update `permits` and place the subtype in the same module (or same package in an unnamed module). |
| Compiler reports subtype is not `final`/`sealed`/`non-sealed` | Direct subtype lacks the required inheritance modifier. | Use `final`, `sealed`, or `non-sealed`; records are implicitly `final`. |
| Record allows null/blank data | Using default constructor without validation. | Use a compact canonical constructor and validate invariants. |
| Record containing a collection is still mutated | A `final` field only fixes the reference, not the collection contents. | Use `List.copyOf`, `Set.copyOf`, or `Map.copyOf`. |
| `Money.equals` behaves unexpectedly | `BigDecimal` values have different scales or currencies differ. | Normalize scale in constructor and keep currency in the component. |
| Adding money of different currencies | Currency mismatch not checked before arithmetic. | Place currency checks inside `Money.add`/`subtract`. |
| `Transfer` updates one side and fails on the other | Mutating state directly before checking all conditions. | Compute both balances on a copy before creating the new snapshot. |
| A transaction is applied twice | Missing idempotency key or non-atomic ID check. | Use a unique transaction ID and a unique constraint in persistence. |
| Two threads lose an update | Immutable snapshots do not solve concurrent commits on their own. | Use database transactions, optimistic locking, or synchronization. |
| Added a new record but handler missed a branch | `if/else` is not checked for exhaustiveness by the compiler. | Update all consumers, keep a clear fallback branch, and test every subtype. |
| Pattern switch fails to compile on default Java 17 | Pattern matching for `switch` is a preview feature in Java 17. | Use stable `instanceof` pattern matching or intentionally enable preview for experiments. |
| Logging a record leaks sensitive data | Auto-generated `toString` prints all components. | Keep secrets/PII out of components; log selectively. |

## 17. Practice Exercises

### Exercise 1 — Add a Fee Transaction Type

Create a `Fee` record with `id`, `accountId`, `amount`, and `occurredAt`. Add `Fee` to `Transaction`'s `permits` list. Define the positive amount rule and how `Ledger` applies the fee.

### Exercise 2 — Create the Money Record

Write a `Money` record using `BigDecimal` and `Currency`. The constructor must normalize scale according to the currency without lossy rounding. Implement `add`/`subtract` rejecting mismatched currencies.

### Exercise 3 — Protect Transfer

Add validation ensuring source and destination accounts differ. In `apply`, compute the new balances for both accounts before creating the new `Ledger`. Explain why this avoids returning a partially updated state.

### Exercise 4 — Idempotency

Create two transactions with the same ID and apply them sequentially. Determine the expected result. Then explain why an in-memory `Set` is insufficient to guarantee idempotency across multiple instances or a database.

### Exercise 5 — Command and Event

Separate the `TransferFunds` request from the `FundsTransferred` event. Identify which fields belong to the request and which exist only after the transaction has been accepted.

### Exercise 6 — Add a New Subtype

Add `Reversal` to the sealed hierarchy. List every place that must be updated: `permits`, constructor validation, `Ledger` logic, serialization mapping, and tests.

### Exercise 7 — Pattern Handling

Write a function describing a `Transaction` using `instanceof` pattern matching. Explain why the code runs stably on Java 17 without preview flags.

## 18. Key Takeaways for Modeling Transactions with Sealed Interfaces and Records

- Records model data by component, automatically generating accessors, `equals`, `hashCode`, and `toString`.
- Use compact constructors to validate and normalize components before creating the record.
- Records have `final` fields but are only shallowly immutable; use defensive copies for collections or mutable components.
- Sealed interfaces restrict direct subtypes via `permits`.
- Direct subtypes must be `final`, `sealed`, or `non-sealed`; records are implicitly `final`.
- Permitted subtypes must be in the same named module as the supertype, or the same package if the supertype belongs to an unnamed module.
- Each transaction type should have its own record to avoid nullable fields and invalid data combinations.
- Use `BigDecimal` for monetary amounts, attach currency, and enforce scale/rounding explicitly.
- Enforce intrinsic invariants in the record; enforce account existence, funds, and authorization in the appropriate business layer.
- `instanceof` pattern matching is stable syntax in Java 17; pattern matching for `switch` remains a preview feature in Java 17.
- Immutable snapshots make state easier to reason about, but do not automatically provide atomicity, concurrency control, or durability.
- Production idempotency requires stable transaction IDs and atomic persistence guarantees.
- The sample model does not replace double-entry ledgers, database transactions, authorization, auditing, or real payment rules.

### References

- [Java SE 17 Language Specification — Records](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10) — record syntax and semantics.
- [Java SE 17 Language Specification — Sealed Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6) — sealed class declarations and permitted subclasses.
- [Java SE 17 Language Specification — Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4) — sealed interface rules.
- [Java SE 17 Language Specification — Pattern Matching for instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2) — pattern variables in `instanceof`.
- [JEP 395: Records](https://openjdk.org/jeps/395) — records as a standard feature.
- [JEP 409: Sealed Classes](https://openjdk.org/jeps/409) — sealed classes/interfaces finalized in Java 17.
- [JEP 406: Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406) — preview status of pattern `switch` in Java 17.
