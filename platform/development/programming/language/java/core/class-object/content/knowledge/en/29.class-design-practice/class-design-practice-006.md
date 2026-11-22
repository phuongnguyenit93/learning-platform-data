# Combining Accounts, Transactions, and Account Holders Using References in Java 17+

## 1. Practical Problem: Objects Related to Each Other

In an account management application, three easily recognizable concepts are the **account holder** (`Customer` or `AccountHolder`), the **account** (`BankAccount`), and the **transaction** (`Transaction`). Instead of stuffing all information into one giant class, object-oriented design represents them as **independent objects linked by typed references**.

Example of a conceptual model:

~~~text
 Customer C01 ("Lan")
       ^
       | owner
       |
 Account A100 ---------> Transaction TX1
       |                      |
       |                      +-- account ------> Account A100
       |
       +-- balance = 125.00

 Customer C01 ("Lan")
       ^
       | owner
 Account A200 ---------> Transaction TX2
~~~

Two different `Account` objects can both reference **a single Customer object**. A `Transaction` can reference the account it affects; for a transfer, the transaction can hold **two account references**: the sending account and the receiving account. This is **linking objects**, not automatically creating data copies or database records.

~~~java
final class Customer {
    final String id;
    final String name;

    Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }
}

final class BankAccount {
    final String accountNumber;
    final Customer owner;

    BankAccount(String accountNumber, Customer owner) {
        this.accountNumber = accountNumber;
        this.owner = owner;
    }
}
~~~

The two declarations above are **valid**, with no `main` yet. If you create a Customer object and pass that reference to two BankAccount constructors, both accounts have `owner == customer`. Java does not clone Customer when passing an argument: the object reference is **passed by value**.

**Lesson focus:** understanding the object graph, object identity, one-to-many relationships, transaction operations, invariants between objects, data snapshots, and the boundary between an in-memory model and a real bank.

This lesson belongs to **Java core – class-object**, in the **Design and Practice** group, topic **Combining Accounts, Transactions, and Account Holders Using References**. The standalone programs use **Java 17+**, with defined file names, `javac`/`java` commands, and deterministic stdout. The financial simulation examples are solely for **learning object-oriented design**, not a core-banking system with authentication, durability, proper auditing, and distributed atomicity.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Analyze the three entities Customer, Account, and Transaction, and the responsibilities of each class.
2. Represent relationships using **object reference fields** instead of just descriptive strings.
3. Explain the difference between **sharing a reference**, **having the same business ID**, and **creating an object copy**.
4. Understand that Java passes references **by value**, and does not pass objects or variables by reference in the C++ sense.
5. Model a Customer owning multiple Accounts, and an Account having multiple Transactions.
6. Choose between **unidirectional** and **bidirectional** relationships and know how to maintain consistency.
7. Build `deposit`, `withdraw`, and `transfer` methods with condition checks.
8. Know how to use `BigDecimal` instead of `double` for money and maintain scale/currency according to policy.
9. Understand how a transaction referencing a live Account differs from a transaction storing a snapshot.
10. Prevent exposing mutable collections, mutable identity fields, and unintended aliasing.
11. Distinguish object identity `==` from business equality by account ID.
12. Analyze reference cycles, retention, and garbage collection in an object graph.
13. Understand that simulating a transfer with two method calls **does not automatically become an ACID database transaction**.
14. State the boundary between an in-memory graph and a database/ORM with foreign keys.
15. Design tests covering relationships, balances, history, business errors, and concurrency.
16. Build a small integrated program yourself with verifiable output.

## 3. Separating Responsibilities Properly

| Object | Typical Data | Appropriate Responsibilities | Should Not Take On |
| --- | --- | --- | --- |
| `Customer` | ID, name, contact/profile | Identify the account holder, perform valid profile updates | Handle all transactions and database infrastructure itself |
| `BankAccount` | Account ID, owner reference, balance | Protect the balance, perform permitted operations, provide state | Store all profile fields as uncontrolled copies |
| `Transaction` | Transaction ID, account references or account IDs, amount, timestamp/status | Describe an operation or a recorded event | Arbitrarily modify the account balance just via the constructor |
| `BankService` | Account store, business rules | Coordinate transfers, validation, repository | Hide important invariants in the UI |
| `LedgerEntry` | Account ID/reference, signed delta, balance snapshot | Record a specific ledger entry | Act as the "source of truth" without an accounting design |

This is a **suggested separation of responsibilities for learning**; there is no fixed set of class names that every system must use. A real bank typically has more than one account holder, joint owners, roles, product types, fees, multiple currencies, a double-entry ledger, approvals, event streams, and durable storage.

**Principle:** give each class a clear reason to change. Reference another class when you need to link data or behavior, instead of creating a "God object" that contains everything.

## 4. What Does a Reference Actually Link?

Consider:

~~~java
Customer owner = new Customer("C01", "Lan");
BankAccount account = new BankAccount("A100", owner);
~~~

This is a valid snippet if the classes from the first section are in scope. After the two statements:

- **One Customer object** is created.
- **One BankAccount object** is created.
- The local variable `owner` holds a reference to the Customer.
- The field `account.owner` holds **another reference pointing to the same Customer object**.
- The constructor does not copy the Customer data; it receives and stores a **reference value**.

In Java, arguments are **passed by value**. For a reference-type parameter, the value passed is the reference; the callee can modify a mutable object through the reference, but **reassigning the parameter** cannot change the reference held in the caller's variable.

Do not confuse "same object" with "same data": two Customer objects can have the same ID and name yet still be two separate objects, where `a == b` is false.

## 5. Complete Program 1 — Transaction References Account, Account References Owner

File **`AccountReferencesDemo.java`**:

~~~java
import java.math.BigDecimal;

record Customer(String id, String name) {
}

final class Account {
    private final String number;
    private final Customer owner;

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    String number() {
        return number;
    }

    Customer owner() {
        return owner;
    }
}

record Transaction(String id, Account account,
                   BigDecimal amount) {
}

public class AccountReferencesDemo {
    public static void main(String[] args) {
        Customer lan = new Customer("C01", "Lan");
        Account savings = new Account("A100", lan);
        Transaction entry = new Transaction(
                "TX1", savings, new BigDecimal("25.00"));

        System.out.println("owner=" + savings.owner().name());
        System.out.println("account=" + entry.account().number());
        System.out.println("amount=" + entry.amount().toPlainString());
        System.out.println("same account="
                + (entry.account() == savings));
        System.out.println("same owner="
                + (entry.account().owner() == lan));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AccountReferencesDemo.java
java AccountReferencesDemo
~~~

**Stdout:**

~~~text
owner=Lan
account=A100
amount=25.00
same account=true
same owner=true
~~~

`Transaction.account()` returns the exact reference that was passed in. Calling `entry.account().owner()` traverses **two reference edges** in the graph. Both `==` checks are true because they are the same object instance. This models the relationship; the Transaction record itself **does not automatically add 25.00 to the balance**.

## 6. One Owner Object, Multiple Accounts: Aliasing

A customer can open two accounts. If both Account fields point to the same Customer object, changes to the Customer's **mutable profile** will be seen by both accounts, because they **do not hold copies**.

~~~text
accountA.owner -----+
                    |
                    v
                Customer C01
                    ^
                    |
accountB.owner -----+
~~~

This can be an advantage: changing the display name in one place makes all account views read the latest profile. However, it can also be a risk: a historical Transaction needs to store the owner's name at the time the document was issued; reading today's live profile does not accurately reproduce the information from that moment.

**Design rule:** when you need a **live shared entity**, hold a reference. When you need a **historical immutable value**, store a snapshot/ID under a separate contract. Do not unthinkingly use a reference for both needs.

## 7. Complete Program 2 — Customer Updates Are Reflected Across Two Accounts

File **`SharedOwnerDemo.java`**:

~~~java
final class Customer {
    private final String id;
    private String displayName;

    Customer(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    String displayName() {
        return displayName;
    }

    void rename(String next) {
        if (next == null || next.isBlank()) {
            throw new IllegalArgumentException("name");
        }
        displayName = next;
    }
}

final class Account {
    private final String number;
    private final Customer owner;

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    Customer owner() {
        return owner;
    }
}

public class SharedOwnerDemo {
    public static void main(String[] args) {
        Customer customer = new Customer("C01", "Lan");
        Account a = new Account("A100", customer);
        Account b = new Account("A200", customer);

        System.out.println("before="
                + a.owner().displayName() + "/"
                + b.owner().displayName());

        customer.rename("Mai");

        System.out.println("after="
                + a.owner().displayName() + "/"
                + b.owner().displayName());
        System.out.println("same owner="
                + (a.owner() == b.owner()));
        System.out.println("different accounts=" + (a != b));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SharedOwnerDemo.java
java SharedOwnerDemo
~~~

**Stdout:**

~~~text
before=Lan/Lan
after=Mai/Mai
same owner=true
different accounts=true
~~~

The Accounts remain two different objects; Customer is one shared object. Because `displayName` can change, the views display the new name. The `id` field preserves a stable business identity, though it is not yet used to enforce any database rules in the demo.

## 8. Java Passes References by Value; Assigning a Parameter Cannot Change the Reference of the Caller's Variable

A common misconception: "Objects are passed by reference, so a method can change the external account variable."

Example:

~~~java
static void replace(Account account) {
    account = new Account("A999", account.owner());
}
~~~

This is a valid **method snippet** if Account already has the constructor and owner accessor. Reassigning the `account` parameter only changes the **method's local variable**, not the caller's variable.

Conversely, if `account` references a mutable object and the method calls `account.deposit(...)`, the contents of that object can change and the caller can observe it.

Distinguish three actions:
1. **Read a field through a reference:** the caller and callee both see the value associated with the object.
2. **Mutate the referenced object:** change the state of the shared object if the API allows it.
3. **Reassign a reference variable:** only changes that specific variable and does not automatically change other aliases.

## 9. Complete Program 3 — Reassigning a Parameter Does Not Change External Aliases

File **`ReferenceParameterDemo.java`**:

~~~java
final class Holder {
    int value;

    Holder(int value) {
        this.value = value;
    }
}

public class ReferenceParameterDemo {
    static void mutate(Holder item) {
        item.value = 7;
    }

    static void reassign(Holder item) {
        item = new Holder(99);
        System.out.println("inside=" + item.value);
    }

    public static void main(String[] args) {
        Holder original = new Holder(1);

        mutate(original);
        System.out.println("after mutate=" + original.value);

        reassign(original);
        System.out.println("after reassign=" + original.value);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ReferenceParameterDemo.java
java ReferenceParameterDemo
~~~

**Stdout:**

~~~text
after mutate=7
inside=99
after reassign=7
~~~

The example uses Holder instead of Account to isolate Java's semantics. `mutate` changes the shared object, whereas `reassign` only makes the parameter name point to another object. The same rule applies to Customer, BankAccount, and Transaction.

## 10. One-to-Many Relationship: Account Holder Holds a List of Accounts

A Customer can be associated with multiple accounts, so it can be designed as:

~~~java
final class Customer {
    private final java.util.List<Account> accounts =
            new java.util.ArrayList<>();
}
~~~

This is a **class snippet**, illustrating only the field. However, to keep the model consistent, we need to decide who has the authority to add an Account:

- Does Customer create the account through its own factory method?
- Does BankService create the account and then register it with Customer?
- Can an Account ever be transferred to another Customer?
- Do the Accounts in `Customer.accounts` actually have `account.owner() == customer`?
- Are duplicate account numbers allowed?
- Are joint accounts supported?

For this lesson, we choose a simple policy: Customer creates its Accounts and keeps the list; each Account has a final `owner`. This is an illustrative **single-owner one-to-many relationship** and does not yet address joint ownership in a real bank.

## 11. Complete Program 4 — Customer Creates and Lists Accounts

File **`CustomerAccountsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Customer {
    private final String id;
    private final List<Account> accounts = new ArrayList<>();

    Customer(String id) {
        this.id = id;
    }

    Account openAccount(String number) {
        if (number == null || number.isBlank()) {
            throw new IllegalArgumentException("number");
        }
        for (Account current : accounts) {
            if (current.number().equals(number)) {
                throw new IllegalArgumentException("duplicate account");
            }
        }

        Account result = new Account(number, this);
        accounts.add(result);
        return result;
    }

    List<Account> accounts() {
        return List.copyOf(accounts);
    }
}

final class Account {
    private final String number;
    private final Customer owner;

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    String number() {
        return number;
    }

    Customer owner() {
        return owner;
    }
}

public class CustomerAccountsDemo {
    public static void main(String[] args) {
        Customer owner = new Customer("C01");
        Account checking = owner.openAccount("A100");
        Account saving = owner.openAccount("A200");

        System.out.println("accounts=" + owner.accounts().size());
        System.out.println("first=" + owner.accounts().get(0).number());
        System.out.println("second=" + saving.number());
        System.out.println("same owner="
                + (checking.owner() == saving.owner()));
        System.out.println("owner points back="
                + (saving.owner() == owner));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CustomerAccountsDemo.java
java CustomerAccountsDemo
~~~

**Stdout:**

~~~text
accounts=2
first=A100
second=A200
same owner=true
owner points back=true
~~~

`accounts()` returns `List.copyOf`: the caller cannot modify the list structure through this accessor. However, this is a **shallow copy**: the Account objects in the list are still the exact same references that were stored, not deep clones.

**Limitation of the example:** the duplicate check only considers Accounts opened through **this Customer instance**. A real bank must check account-number uniqueness using a registry/database with transaction constraints; a list on Customer cannot serve as the system-wide authority.

## 12. Unidirectional or Bidirectional Relationship?

**Unidirectional**: Account has `owner`, while Customer does not store `accounts`. To find a Customer's accounts, you can query a repository/service.

~~~text
Account ----owner----> Customer
~~~

**Bidirectional**: Customer has a collection of Accounts, and each Account also has an owner.

~~~text
Customer ----accounts----> Account
    ^                        |
    +----------owner---------+
~~~

A bidirectional design makes navigation convenient, but it introduces a **relationship invariant** that must be maintained:

> If `account` is in `customer.accounts()`, then `account.owner() == customer` under the model's single-owner policy.

If the code allows `customerA.accounts.add(accountOwnedByB)`, the graph is no longer consistent. This is not a GC bug; it is a model data bug.

Choose unidirectional when:
- One side rarely needs navigation.
- Finding the collection is handled by a repository/query.
- You want to reduce coupling and the overhead of keeping both sides synchronized.

Choose bidirectional when:
- Both navigation directions have domain meaning.
- A single service/factory controls relationship updates.
- There are clear invariant tests.

## 13. A Reference Relationship Does Not Automatically Create Business Data

If a Transaction record only has `Account account` and `BigDecimal amount` fields, creating the record **does not add to or subtract from the balance**:

~~~java
Transaction entry =
        new Transaction("TX1", account,
                new java.math.BigDecimal("10.00"));
~~~

This is a snippet based on the corresponding declarations. It only creates an object that records data.

For a real transaction to take place, there must be a **business operation** that performs validation and updates the account/ledger according to a protocol:

1. Validate that the amount is valid.
2. Check that the account exists and its state permits the operation.
3. Check balance/limits if withdrawing.
4. Apply the balance/ledger change within an appropriate transaction boundary.
5. Record the record/entry with the required identity and timestamp/status.
6. Publish the result according to the API.
7. If persistence is present, perform proper commit/rollback or recovery.

In small in-memory examples, we only simulate a subset of this workflow, and we must state the limitations clearly.

## 14. Using `BigDecimal` for Money and Scale Policy

Avoid using `double` as the unit for storing balances because binary floating-point representation cannot accurately represent many decimal fractions.

~~~java
java.math.BigDecimal amount =
        new java.math.BigDecimal("10.50");
~~~

This is a valid statement. The constructor taking a **decimal string** preserves the expected value and scale. You should avoid `new BigDecimal(0.1)` when you want the exact decimal 0.1; the constructor from double carries the exact binary value passed in, which is usually not the ideal decimal 0.1.

**However, BigDecimal alone does not solve the entire money problem:**

- **Currency:** USD and VND cannot be arbitrarily added together just because both are BigDecimal.
- **Scale:** some currency units have 2 decimal places; other currencies have different rules.
- **Rounding:** division, exchange rates, taxes, and fees require `RoundingMode` and a consistent policy.
- **Precision:** arithmetic in BigDecimal is accurate when operations and context are chosen appropriately.
- **Equality:** `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` is false due to different scales, whereas `compareTo` treats them as having the same numeric value.
- **Nonnegative amounts:** validate with `signum() > 0` if the business rules require it.

The demo programs use a single assumed currency, all amounts are entered with scale 2, and no currency conversion is performed.

## 15. Complete Program 5 — deposit, withdraw, and Entry History Referencing Account

File **`AccountLedgerDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

record Customer(String id, String name) {
}

record Entry(int sequence, Account account,
             BigDecimal change, BigDecimal balanceAfter) {
}

final class Account {
    private final String number;
    private final Customer owner;
    private BigDecimal balance = new BigDecimal("0.00");
    private final List<Entry> history = new ArrayList<>();

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    BigDecimal balance() {
        return balance;
    }

    Customer owner() {
        return owner;
    }

    List<Entry> history() {
        return List.copyOf(history);
    }

    void deposit(BigDecimal amount) {
        requirePositive(amount);
        balance = balance.add(amount);
        history.add(new Entry(
                history.size() + 1, this, amount, balance));
    }

    void withdraw(BigDecimal amount) {
        requirePositive(amount);
        if (balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }
        balance = balance.subtract(amount);
        history.add(new Entry(
                history.size() + 1, this, amount.negate(), balance));
    }

    private static void requirePositive(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
    }
}

public class AccountLedgerDemo {
    public static void main(String[] args) {
        Customer lan = new Customer("C01", "Lan");
        Account account = new Account("A100", lan);

        account.deposit(new BigDecimal("100.00"));
        account.withdraw(new BigDecimal("30.00"));

        System.out.println("owner=" + account.owner().name());
        System.out.println("balance=" + account.balance());
        System.out.println("entries=" + account.history().size());
        System.out.println("first delta="
                + account.history().get(0).change());
        System.out.println("second delta="
                + account.history().get(1).change());
        System.out.println("entry points back="
                + (account.history().get(0).account() == account));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AccountLedgerDemo.java
java AccountLedgerDemo
~~~

**Stdout:**

~~~text
owner=Lan
balance=70.00
entries=2
first delta=100.00
second delta=-30.00
entry points back=true
~~~

Account holds `List<Entry>`; each Entry holds a **reference to the same Account**. This is bidirectional Account→Entry→Account. Because Account holds history, the graph has a cycle. **A cycle is not automatically a memory leak** if the entire graph is no longer reachable from roots; however, retaining Account for a long time retains Entries along this reference direction.

`balanceAfter` is recorded using an immutable BigDecimal at the time of the operation, so a past Entry has a **balance snapshot**, even though `entry.account().balance()` continues to change afterward.

**Financial limitations:** sequence numbers using `history.size()+1` are only illustrative within a single Account instance; they are not system-wide unique transaction IDs, nor are they thread-safe or durable. Withdrawing and recording an entry here have no database transaction/rollback.

## 16. Why Does Storing History in Account Need Ownership Rules?

If Account allows external code to arbitrarily modify `history`, the caller could delete past entries, insert fake entries, or change the order:

~~~java
// Poorly designed API (illustrative idea):
// public List<Entry> getHistory() { return history; }
~~~

This is a commented-out snippet, not a runnable declaration. Instead:

~~~java
List<Entry> history() {
    return List.copyOf(history);
}
~~~

This method **prevents the caller from adding/removing elements via the returned list**, but it does not deep-copy the element objects. If Entry is a record with immutable components such as BigDecimal, returning a shallow structural snapshot is usually acceptable in examples.

**Key distinctions:**
- `List.copyOf` creates a new list or reuses an eligible immutable list per its contract; it does not promise a deep clone.
- An `Entry` record having final component references does not make the Account object it points to immutable.
- If history should only contain **immutable audit snapshots**, it is better to store the Account ID or snapshot fields rather than a live Account reference.

For systems with legal audit requirements, you should use an append-only persisted ledger/event store with controls, rather than treating an in-heap list as sufficient.

## 17. Transfer Transaction Model: One Transaction Has Two Reference Ends

A transfer connects:

~~~text
             Transaction T9
              /          \
       sourceAccount   targetAccount
            |               |
            v               v
        Account A        Account B
            |               |
            v               v
        Owner C1          Owner C2
~~~

At the OOP level, a record:

~~~java
record Transfer(String id,
                Account source,
                Account target,
                java.math.BigDecimal amount) {
}
~~~

is one way to record **references to two accounts**. However, the record constructor only stores the components; it **does not automatically update balances** and does not guarantee that the source/target belong to an authorized owner.

A transfer service needs to check:
- Source/target are non-null and are two different accounts by business identity.
- The amount is positive and the currency/scale is valid.
- Source has an appropriate balance or limit.
- The request has transfer authorization and anti-fraud checks (outside the demo).
- The two balance changes and the ledger recording lie within an atomic/durable transaction boundary in a real system.

You cannot replace these responsibilities by declaring two reference fields.

## 18. Complete Program 6 — In-Memory Transfer

File **`TransferReferencesDemo.java`**:

~~~java
import java.math.BigDecimal;

record Customer(String id, String name) {
}

final class Account {
    private final String number;
    private final Customer owner;
    private BigDecimal balance;

    Account(String number, Customer owner, BigDecimal opening) {
        if (number == null || owner == null
                || opening == null || opening.signum() < 0) {
            throw new IllegalArgumentException("invalid account");
        }
        this.number = number;
        this.owner = owner;
        this.balance = opening;
    }

    String number() {
        return number;
    }

    Customer owner() {
        return owner;
    }

    BigDecimal balance() {
        return balance;
    }

    void debit(BigDecimal amount) {
        if (balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }
        balance = balance.subtract(amount);
    }

    void credit(BigDecimal amount) {
        balance = balance.add(amount);
    }
}

record Transfer(String id, Account source,
                Account target, BigDecimal amount) {
}

public class TransferReferencesDemo {
    static Transfer transfer(String id, Account from,
                             Account to, BigDecimal amount) {
        if (from == null || to == null
                || from == to || amount == null
                || amount.signum() <= 0) {
            throw new IllegalArgumentException("invalid transfer");
        }
        if (from.balance().compareTo(amount) < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }

        from.debit(amount);
        to.credit(amount);
        return new Transfer(id, from, to, amount);
    }

    public static void main(String[] args) {
        Account source = new Account("A100",
                new Customer("C01", "Lan"),
                new BigDecimal("80.00"));
        Account target = new Account("A200",
                new Customer("C02", "Minh"),
                new BigDecimal("10.00"));

        Transfer record = transfer("T9", source, target,
                new BigDecimal("30.00"));

        System.out.println("source=" + source.balance());
        System.out.println("target=" + target.balance());
        System.out.println("total="
                + source.balance().add(target.balance()));
        System.out.println("from reference="
                + (record.source() == source));
        System.out.println("to owner="
                + record.target().owner().name());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 TransferReferencesDemo.java
java TransferReferencesDemo
~~~

**Stdout:**

~~~text
source=50.00
target=40.00
total=90.00
from reference=true
to owner=Minh
~~~

A Transfer record connects the exact **two Account objects that were modified**. The total balance, 80.00+10.00 before and 50.00+40.00 after, equals 90.00 in the fee-free model.

**This is not a safe transfer implementation to deploy in a real bank.** The two calls `debit` and `credit` are two separate mutations, with no transaction rollback if a failure occurs partway through and no synchronization between threads. Checking the balance before debiting is **not enough** to prevent race conditions. A real environment requires transactions/locking/persistence/idempotency.

## 19. When Objects Have the Same ID but Different References

Java distinguishes:

- **Object identity:** `a == b` checks whether they are the same object reference.
- **Business identity:** `a.accountNumber().equals(b.accountNumber())` compares the business key.
- **Value equality:** `a.equals(b)` depends on the implementation of `equals`; for records, it usually compares the components.

Example:

~~~java
Account a = new Account("A100", owner);
Account b = new Account("A100", owner);
~~~

This snippet relies on an appropriate constructor. It is possible that `a != b` even though accountNumber has the same string.

In the banking domain, two objects with the same account number may represent **one business entity across two different loads from the database**. A process should not rely on `==` between entities loaded from different repositories to decide whether they are the same business account.

**However,** you also should not define equals/hashCode based solely on a mutable ID that can change: mutating a key currently inside a HashMap/HashSet causes hard-to-find bugs. Identity fields need to be stable according to policy.

## 20. Complete Program 7 — Reference Identity Differs from Business ID

File **`AccountIdentityDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Set;

final class Account {
    private final String number;

    Account(String number) {
        this.number = number;
    }

    String number() {
        return number;
    }
}

public class AccountIdentityDemo {
    public static void main(String[] args) {
        Account a = new Account("A100");
        Account b = new Account("A100");

        Set<Account> objects = new HashSet<>();
        objects.add(a);
        objects.add(b);

        System.out.println("same object=" + (a == b));
        System.out.println("same account number="
                + a.number().equals(b.number()));
        System.out.println("set size=" + objects.size());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 AccountIdentityDemo.java
java AccountIdentityDemo
~~~

**Stdout:**

~~~text
same object=false
same account number=true
set size=2
~~~

The Account class does not override equals/hashCode, so the Set distinguishes the two Account instances by Object equality. A repository must not allow two business records with duplicate account numbers just because they are different objects.

If you define equals by account number, consider uniqueness, bank/tenant scope, unassigned ID lifecycles, consistency with hashCode, and ORM proxy types before applying it.

## 21. Live Reference Differs from Historical Snapshot

A transaction history usually must reflect the **state at the time of the transaction**, not live attributes that keep changing.

Suppose Customer changes their display name from Lan to Mai. If Transaction only stores `Customer customer`, a history page that reconstructs the name via `transaction.customer().displayName()` will display **Mai**, even though at the time the document was issued the owner's name was Lan.

Two different needs:

| Need | Store Live Reference | Store Snapshot |
| --- | --- | --- |
| Display the owner's current profile | Suitable | May become stale |
| Check which customer currently owns an account | Can be suitable if it is an authoritative graph | Snapshot does not update automatically |
| Print a point-in-time historical document | Insufficient if fields are mutable | Suitable for an audit snapshot |
| Retain linked account IDs long-term | May retain a large object graph | IDs/immutable values are more compact |
| Persist data / look up outside the process | Requires persistence mapping | Snapshot fields may be easier to serialize |

There is no universal choice for every situation. Many designs use **both accountId/customerId** and **snapshot fields** in a transaction event, and then fetch the live profile from the repository when needed.

## 22. Complete Program 8 — Snapshot Does Not Change When Customer Name Changes

File **`OwnerSnapshotDemo.java`**:

~~~java
final class Customer {
    private final String id;
    private String name;

    Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }

    String id() {
        return id;
    }

    String name() {
        return name;
    }

    void rename(String value) {
        name = value;
    }
}

final class Account {
    private final String number;
    private final Customer owner;

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    String number() {
        return number;
    }

    Customer owner() {
        return owner;
    }
}

record ReceiptSnapshot(String accountNumber,
                       String customerId,
                       String ownerNameAtIssue) {
}

public class OwnerSnapshotDemo {
    public static void main(String[] args) {
        Customer customer = new Customer("C01", "Lan");
        Account account = new Account("A100", customer);

        ReceiptSnapshot receipt = new ReceiptSnapshot(
                account.number(), customer.id(), customer.name());

        customer.rename("Mai");

        System.out.println("live name=" + account.owner().name());
        System.out.println("receipt name=" + receipt.ownerNameAtIssue());
        System.out.println("receipt owner ID=" + receipt.customerId());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 OwnerSnapshotDemo.java
java OwnerSnapshotDemo
~~~

**Stdout:**

~~~text
live name=Mai
receipt name=Lan
receipt owner ID=C01
~~~

Account links to the live Customer, whereas ReceiptSnapshot stores three immutable Strings. This is a simple example of **separating a live entity reference from a historical value**.

A real-world model needs timestamps, a timezone policy, legal documents, currency, transaction IDs, verified data, and durable storage. A record on the heap does not automatically become an unalterable audit trail.

## 23. A Transaction Record Has Final Fields, but Does Not Make Account Immutable

Given:

~~~java
record Transaction(String id, Account account) {
}
~~~

The Transaction record is implicitly final and its component fields are final. However, `account` is still a reference to a **mutable Account**.

If Account increases its balance from 10.00 to 20.00, calling `transaction.account().balance()` afterward reads **20.00**, not the 10.00 at the time the transaction was created.

**This is shallow immutability:** the component reference in the record cannot be reassigned via the record accessor, yet the referenced object can still mutate. If history needs to freeze `balanceAfter`, store an immutable BigDecimal at event time:

~~~java
record TransactionSnapshot(String id,
                           String accountNumber,
                           java.math.BigDecimal balanceAfter) {
}
~~~

This is a valid record declaration. BigDecimal is immutable, though validation against null/invalid currency still belongs in the constructor/service.

## 24. Complete Program 9 — Record Holds a Live Account and an Immutable Balance Snapshot

File **`TransactionSnapshotDemo.java`**:

~~~java
import java.math.BigDecimal;

final class Account {
    private BigDecimal balance = new BigDecimal("0.00");

    void deposit(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount");
        }
        balance = balance.add(amount);
    }

    BigDecimal balance() {
        return balance;
    }
}

record Transaction(String id, Account account,
                   BigDecimal balanceAfter) {
}

public class TransactionSnapshotDemo {
    public static void main(String[] args) {
        Account account = new Account();

        account.deposit(new BigDecimal("10.00"));
        Transaction first =
                new Transaction("T1", account, account.balance());

        account.deposit(new BigDecimal("5.00"));

        System.out.println("snapshot=" + first.balanceAfter());
        System.out.println("live=" + first.account().balance());
        System.out.println("same account="
                + (first.account() == account));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 TransactionSnapshotDemo.java
java TransactionSnapshotDemo
~~~

**Stdout:**

~~~text
snapshot=10.00
live=15.00
same account=true
~~~

`balanceAfter` is a stored BigDecimal value and does not change; the mutable Account continues to reflect the new balance. This is why transaction history needs to **distinguish between reference state and event-time state**.

## 25. What Does a `final` Field Protect in an Object Graph?

If you declare:

~~~java
private final Customer owner;
~~~

in BankAccount, the `owner` reference field **cannot be reassigned** after valid construction. However:
- The Customer object can have mutable profile fields.
- A Customer can own multiple Accounts.
- If you want to change ownership according to business rules, you need a dedicated design instead of secretly modifying the final field.
- A final reference **does not guarantee that the owner cannot be garbage-collected**: reachability depends on graph roots.
- An account can be stored in a repository under an account ID; the same business entity can be materialized into new objects.

`final` helps maintain a fixed ownership structure in a small model, but it does not replace domain invariants: owner exists, account ID is unique, customer is active, and currency is compatible.

When the business supports joint owners or ownership transfers, a single `Account.owner` model may no longer be suitable. You should move to membership/authorization records rather than trying to "hack" a reference field.

## 26. Bidirectional Relationships Require a Single Update Entry Point

If Account and Customer each hold a reference/list to the other, opening an account should be performed through **one method that protects the invariant**.

A weak design allows:

~~~java
// Poor idea: letting external code manipulate each direction separately
// customer.accounts.add(account);
// account.owner = anotherCustomer;
~~~

The commented lines illustrate the risk, not a recommended API.

A safer design:
1. Customer or AccountService serves as the entry point for creating an Account.
2. The Account constructor checks for a non-null owner and account number.
3. The entry point adds the Account to the correct Customer's collection.
4. Do not expose the mutable collection.
5. Do not expose an arbitrary owner setter.
6. When ownership transfer is needed, use **a single domain operation** that updates all related relationships in sync and checks policy.

Even with a simple creation function, if the program runs multi-threaded, concurrency constraints are needed to prevent two requests from creating the same account number at the same time.

## 27. Complete Program 10 — Checking the Owner Relationship When Creating a Payment Request

File **`OwnerValidationDemo.java`**:

~~~java
import java.math.BigDecimal;

record Customer(String id) {
}

final class Account {
    private final String number;
    private final Customer owner;

    Account(String number, Customer owner) {
        if (number == null || owner == null) {
            throw new IllegalArgumentException("account");
        }
        this.number = number;
        this.owner = owner;
    }

    Customer owner() {
        return owner;
    }

    String number() {
        return number;
    }
}

record PaymentRequest(Account account, Customer requestedBy,
                      BigDecimal amount) {
    PaymentRequest {
        if (account == null || requestedBy == null
                || amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("invalid payment");
        }
        if (account.owner() != requestedBy) {
            throw new IllegalArgumentException("owner mismatch");
        }
    }
}

public class OwnerValidationDemo {
    public static void main(String[] args) {
        Customer lan = new Customer("C01");
        Customer minh = new Customer("C02");
        Account account = new Account("A100", lan);

        PaymentRequest valid =
                new PaymentRequest(account, lan,
                        new BigDecimal("2.00"));
        System.out.println("valid reference="
                + (valid.account().owner() == valid.requestedBy()));

        try {
            new PaymentRequest(account, minh,
                    new BigDecimal("2.00"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OwnerValidationDemo.java
java OwnerValidationDemo
~~~

**Stdout:**

~~~text
valid reference=true
rejected=owner mismatch
~~~

The example checks an **in-memory reference consistency invariant**. It is **not** real authorization. In a real system, a caller could submit a fake customerId; the service must authenticate the principal, check permissions to perform the operation on the account, handle joint ownership, and enforce other policies. If two Customer objects have the same business ID but are different instances, `!=` here will reject it; that is a consequence of the demo using object identity, not a universal business rule.

## 28. Back References and Object Graph Cycles Do Not Automatically Cause Memory Leaks

When Account holds List<Transaction> and Transaction holds Account, the graph has a cycle:

~~~text
GC Root ---> Account ---> List<Transaction> ---> Transaction
                 ^                              |
                 +--------- account ------------+
~~~

Java's GC can collect cycles when **the entire graph becomes unreachable** from GC roots. What causes memory to be retained for too long is usually a **root that still holds the graph**, such as a static registry, an unbounded cache, an event listener, or an active session.

For example, a `static Map<String,Account>` retains Account long-term; Account holds the entire history, and each Transaction holds Account. In that case, history remains reachable through the registry. Even though local variables have gone out of scope, the objects are not garbage as long as a strong reference path from the Map remains.

**Designing for large histories:** you can keep only the most recent portion in memory, paginate from the database, or store IDs/snapshots instead of references to full entities. GC does not replace eviction and retention policies.

## 29. Complete Program 11 — Observing Reference Cycles and Breaking Long-Term Relationships

File **`RelationshipLifecycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Account {
    private final String id;
    private final List<Transaction> transactions =
            new ArrayList<>();

    Account(String id) {
        this.id = id;
    }

    void add(String transactionId) {
        transactions.add(new Transaction(transactionId, this));
    }

    List<Transaction> transactions() {
        return List.copyOf(transactions);
    }

    void clearInMemoryHistory() {
        transactions.clear();
    }
}

record Transaction(String id, Account account) {
}

public class RelationshipLifecycleDemo {
    public static void main(String[] args) {
        Account account = new Account("A100");
        account.add("T1");
        account.add("T2");

        Transaction first = account.transactions().get(0);

        System.out.println("count=" + account.transactions().size());
        System.out.println("back reference="
                + (first.account() == account));

        account.clearInMemoryHistory();
        System.out.println("count after clear="
                + account.transactions().size());
        System.out.println("first ID still=" + first.id());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 RelationshipLifecycleDemo.java
java RelationshipLifecycleDemo
~~~

**Stdout:**

~~~text
count=2
back reference=true
count after clear=0
first ID still=T1
~~~

`clearInMemoryHistory()` removes references from the Account list, yet the local variable `first` still holds Transaction, and Transaction in turn holds Account. Therefore, you must not conclude that "the two objects were collected by GC after clear."

The example clarifies **reference paths**. In a financial product, clearing history solely to free memory must not mean deleting mandatory persisted audit data.

## 30. Composition, Aggregation, and Association in the Model

Three common UML/OOP terms:

- **Association**: Transaction knows about Account and can navigate to Account.
- **Aggregation (shared concept)**: Customer is associated with a set of Accounts, but Accounts can be managed independently by a registry/database.
- **Composition (stronger lifecycle ownership)**: one object owns subobjects and determines their lifecycle; for example, an Account in a pure-heap model creates and holds internal LedgerEntries.

Java has no separate `aggregation` or `composition` keyword. Both can use **reference fields and collections**; the difference lies primarily in the **ownership contract, creation/destruction, visibility, and invariants**.

You should describe:
1. Who creates Account?
2. Can Account exist if the Customer object in memory is no longer present?
3. Must a historical Transaction continue to exist after Account is closed?
4. Who is allowed to delete/modify the relationship?
5. Is the data stored in a DB?
6. If the same business account is loaded multiple times, how is object identity handled?

Looking only at `private Customer owner;` does not tell you all the answers.

## 31. A Closed Account Differs from an Account Object Reaching the End of Its Lifecycle

Closing an account in business terms may transition its status from ACTIVE to CLOSED, yet the Java Account object is still referenced in history, reports, or services.

~~~java
enum AccountStatus {
    ACTIVE, CLOSED
}
~~~

This is a valid declaration. An Account model can have:

~~~java
private AccountStatus status = AccountStatus.ACTIVE;
~~~

This is a valid field snippet inside the Account class. When closing a business account, the code changes the status and rejects future withdrawals, but it does **not** delete records, history, and legal data just because the account is inactive.

By contrast, `AutoCloseable.close()` on a file/database resource cleans up a native/managed resource. **Do not confuse** `account.close()` (closing a banking product) with `Connection.close()` or garbage collection of the Account object.

Domain naming should clarify semantics: `closeAccount()`, `deactivate()`, or `changeStatus()` may express intent better than an ambiguous `close()` method in the model.

## 32. A Real Ledger Differs from an In-Memory Transaction Collection

A `List<Transaction>` in Account is suitable for learning object references. However, in a system requiring audit/durability, a ledger must also address:

- Each entry has a unique ID and a reliable ordering.
- Amount/currency/precision are validated consistently.
- Debit/credit postings need to balance according to the accounting model.
- Entries are durably persisted and cannot be arbitrarily modified/deleted.
- Transfers have an **idempotency key** to prevent duplication on request retries.
- There are pending/posted/reversed statuses instead of directly "editing a past transaction."
- There are trace/audit details, the authorizing principal, system-assigned timestamps, and versioning.
- Account balance updates and ledger record operations are committed atomically or use a recovery protocol.
- DB constraints prevent duplicate account numbers/transaction IDs from being created.

`record Transaction(...)` in Java is only a **data carrier**; it does not automatically guarantee ACID, auditing, or nonrepudiation. Those guarantees come from the service, persistence, access control, infrastructure, and operational procedures.

## 33. Thread Safety: Two Threads Modifying the Balance Simultaneously

An Account has a mutable `BigDecimal balance`. If two threads call `deposit()` at the same time without synchronization, both may read the same old balance and write their new result, losing one update.

Conceptual example:

~~~text
initial balance = 10
Thread A reads 10, wants +5
Thread B reads 10, wants +7
Thread A writes 15
Thread B writes 17
Result is 17 instead of 22
~~~

This is one **possible interleaving** for unsynchronized code, not the only output of every execution.

An immutable `BigDecimal` does not make the `balance` field automatically atomic. Creating a new BigDecimal and reassigning the field is still a read-modify-write operation that requires concurrency control.

**A simple learning approach:** have a **single service** own the Accounts and synchronize all read/write operations through the same monitor. This illustrates the principle of protecting invariants, not an efficient architecture for production throughput or distributed services.

## 34. Complete Program 12 — A Service Synchronizing Operations in Memory

File **`SynchronizedLedgerDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;

final class LedgerService {
    static final class Account {
        private final String number;
        private BigDecimal balance;

        private Account(String number, BigDecimal opening) {
            this.number = number;
            this.balance = opening;
        }
    }

    private final Map<String, Account> accounts =
            new LinkedHashMap<>();

    synchronized Account open(String number, BigDecimal opening) {
        if (number == null || number.isBlank()
                || opening == null || opening.signum() < 0
                || accounts.containsKey(number)) {
            throw new IllegalArgumentException("account");
        }
        Account account = new Account(number, opening);
        accounts.put(number, account);
        return account;
    }

    synchronized void transfer(Account from, Account to,
                               BigDecimal amount) {
        if (from == null || to == null || from == to
                || amount == null || amount.signum() <= 0
                || accounts.get(from.number) != from
                || accounts.get(to.number) != to) {
            throw new IllegalArgumentException("transfer");
        }
        if (from.balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }

        from.balance = from.balance.subtract(amount);
        to.balance = to.balance.add(amount);
    }

    synchronized BigDecimal balance(Account account) {
        if (account == null
                || accounts.get(account.number) != account) {
            throw new IllegalArgumentException("unknown account");
        }
        return account.balance;
    }
}

public class SynchronizedLedgerDemo {
    public static void main(String[] args) {
        LedgerService service = new LedgerService();
        LedgerService.Account a =
                service.open("A100", new BigDecimal("40.00"));
        LedgerService.Account b =
                service.open("A200", new BigDecimal("10.00"));

        service.transfer(a, b, new BigDecimal("15.00"));

        System.out.println("A=" + service.balance(a));
        System.out.println("B=" + service.balance(b));
        System.out.println("total="
                + service.balance(a).add(service.balance(b)));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SynchronizedLedgerDemo.java
java SynchronizedLedgerDemo
~~~

**Stdout:**

~~~text
A=25.00
B=25.00
total=50.00
~~~

`LedgerService` controls all mutations and reads in the example using **the same monitor** (`synchronized` instance methods). The mutable balance fields of the nested Account are private; callers cannot manipulate them directly. When all access actually goes through this service, transfer/read operations do not interleave partway through.

**Limitations:** does not guarantee durable atomicity across database/process crashes; does not handle multiple JVM instances, distributed transactions, overdraft/fees/currency, or external side effects. A global monitor also limits throughput; in production you may need database transactions, row locks, optimistic locking, event sourcing, or other appropriate concurrency strategies.

## 35. Can a Customer Reference Replace a Foreign Key in a Database?

Within a single JVM process:

~~~java
Account account = new Account("A100", owner);
~~~

Account can hold an object reference to the owner. However, when persisted to a relational database, the relationship is usually represented by an **ID/foreign key**:

~~~text
CUSTOMER
  id     name
  C01    Lan

ACCOUNT
  account_no  customer_id  balance
  A100        C01          50.00

TRANSACTION
  id   source_account_no   target_account_no   amount
  T9   A100                A200                10.00
~~~

These are **illustrative data tables**, not SQL DDL. In a database:
- Foreign keys express relationships using business IDs.
- An ORM may load the same entity as a single managed object within one persistence context, but identity across different contexts/sessions **should not be assumed to be the same Java reference**.
- Lazy loading/proxies can affect access behavior and `equals`.
- Transaction records storing IDs help reduce coupling to live object graphs and support history.
- Changes on the heap are not considered durable until the persistence layer commits successfully.

**Important:** `==` on entity objects is not a sole replacement for matching foreign keys/business identity.

## 36. When to Store Only an Account ID vs. When to Hold an Object Reference?

| Need | Direct Account Reference | Account ID |
| --- | --- | --- |
| OOP demo within the same JVM | Simple, easy to navigate | Requires an extra lookup |
| Domain service processing an already loaded entity | Can be convenient | Still useful for verifying identity |
| Data sent over the network | Unsuitable for serializing arbitrary object graphs | ID/DTO is usually better |
| Long-term historical ledger | Live state can change, graph is heavy | ID + snapshot value is clearer |
| ORM entity association | Mapping supports references | Database still uses foreign keys |
| Long-term cache | May retain too many objects | ID and bounded cache help control retention |
| Two different JVMs/processes | No shared Java reference across processes | Use a persistent identifier |
| Authorization | A reference alone is not enough | Principal/resource policy is still required |

The choice depends on the layer. A request DTO might carry only the account number; the domain service validates it, resolves the ID to an entity within a transaction context, and then operates on the entities. Each layer has its own responsibility, rather than choosing "references only" or "IDs only" across the entire application.

## 37. Managing Relationships When an Account Has Multiple Owners

The demo lesson uses `Account.owner` with a single Customer. In real business scenarios, a joint account or authorized users may require multiple people with roles:

~~~text
Account A100
  |
  +-- Membership(customer=C01, role=PRIMARY_OWNER)
  |
  +-- Membership(customer=C02, role=JOINT_OWNER)
  |
  +-- Authorization(customer=C03, scope=VIEW_ONLY)
~~~

A good model in that case can use:
- `Customer` and `Account` as two entities.
- `AccountMembership` linking Customer–Account with role, effective dates, and status.
- A service deciding who can transfer/withdraw.
- A Transaction record storing the actor identity separately from the account owner.
- All relationships checked at the database/application layers.

**Do not use `account.owner() == request.customer()` as the sole permission check** when the system has delegated permissions or objects loaded from different repositories.

## 38. Choosing the Right Object Identity/Equality for the Model

Three choices for Account:

**A. Default Object identity:** `equals` is not overridden. Suitable in simulations where each instance is a distinct entity; two loads with the same ID are not equal under Object.equals.

**B. Equality by immutable business ID:** useful in some domains, but you must define the uniqueness scope, when the ID is assigned, and hashCode consistency. If the ID is initially null and assigned after placing the object into a HashSet, the design breaks easily.

**C. Equality by full value:** suitable for **value objects/records**, less suitable for a mutable account entity whose balance/history changes. If equals/hashCode depends on balance, the object can "get lost" in a HashSet after a deposit.

Do not choose B/C just because the IDE can generate equals/hashCode. Decide on **identity semantics** first, then implement them with immutable keys and symmetry/transitivity/consistency tests.

## 39. Updating the Balance Should Not Be a Public Setter

A weak design:

~~~java
class Account {
    public java.math.BigDecimal balance;
}
~~~

This is a valid class but a poor domain model: callers can write a negative balance or change the value without a corresponding transaction.

A better design:
- Make the field `private`.
- Read via an accessor or snapshot.
- Modify via domain methods with validation.
- Coordinate transfers in a service with a transaction boundary.
- Record ledger entries with an ID and timestamp/status when appropriate.
- Prevent UI/generic serialization code from arbitrarily modifying the balance.

**Encapsulation does not mean security**: if a service uses private account fields yet lets any caller invoke `withdraw` without authentication, the system is still unprotected. The Java language only helps protect valid manipulation paths within the program; authorization is the application's responsibility.

## 40. Testing Important Invariants

For each operation, test at least:

| Scenario | Expectation |
| --- | --- |
| Customer opens two Accounts | Account references point to the right Customer object |
| Rename Customer | Live views see the new name if the reference is intentionally shared |
| Create ReceiptSnapshot | Historical name does not change after profile update |
| Deposit a positive amount | Balance increases and entry is recorded |
| Withdraw exceeding balance | Rejected; balance/history remain unchanged |
| Null or negative/zero amount | Rejected |
| Transfer between two accounts | Source decreases, target increases, total stays unchanged if fee-free |
| Transfer from an Account to itself | Rejected per policy |
| Same account ID but different objects | Do not infer `==` is true |
| Retrieve history list | Cannot add/remove directly through the returned list |
| Wrong request owner | Rejected per the demo reference policy |
| Concurrent mutations | Must have appropriate service/DB synchronization |
| History holds references | Do not assume automatic GC collection even after local variable scope ends |
| Repository persistence | Has uniqueness, foreign-key, and transaction constraints |

A test for a **rejection path** should verify there is no partial mutation. A test for **transfer success** should also verify that the two account references in the Transfer result are the exact objects that were processed.

## 41. Complete Program 13 — Withdrawing Beyond the Balance Does Not Modify Account

File **`WithdrawalInvariantDemo.java`**:

~~~java
import java.math.BigDecimal;

final class Account {
    private BigDecimal balance;

    Account(BigDecimal opening) {
        if (opening == null || opening.signum() < 0) {
            throw new IllegalArgumentException("opening");
        }
        this.balance = opening;
    }

    void withdraw(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount");
        }
        if (balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }
        balance = balance.subtract(amount);
    }

    BigDecimal balance() {
        return balance;
    }
}

public class WithdrawalInvariantDemo {
    public static void main(String[] args) {
        Account account = new Account(new BigDecimal("20.00"));

        try {
            account.withdraw(new BigDecimal("30.00"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("unchanged=" + account.balance());
        account.withdraw(new BigDecimal("5.00"));
        System.out.println("after valid=" + account.balance());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 WithdrawalInvariantDemo.java
java WithdrawalInvariantDemo
~~~

**Stdout:**

~~~text
rejected=insufficient funds
unchanged=20.00
after valid=15.00
~~~

Checking the balance before mutation guarantees that **withdrawing beyond the balance in a single-threaded environment** does not change state. Do not infer that concurrency is solved: if there are multiple threads, the precondition and update need to be executed within the same synchronization/transaction boundary.

## 42. Integrated Problem: Two Customers, Three Accounts, Multiple Transactions

Small combined design:

1. `Customer` has an ID and a display name.
2. `Account` has an account number, an owner reference, a mutable balance, and history.
3. `LedgerEvent` is an immutable record storing the transaction code, account ID, and delta/snapshot.
4. `Bank` manages account number uniqueness in a registry.
5. `Bank.deposit` and `Bank.transfer` check preconditions and update the entities.
6. Print total balances and verify owner links.

In this model, **BankService is the single coordination point**. Both sides of a transfer are handled by the same service instance; there are no threads or persistence. This is an easily extensible way to organize responsibilities for learning, not a replacement for a database transaction.

## 43. Complete Program 14 — In-Memory Banking Application

File **`BankObjectGraphDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

record Customer(String id, String name) {
}

record LedgerEvent(String code, String accountNumber,
                   String kind, BigDecimal amount,
                   BigDecimal balanceAfter) {
}

final class Account {
    private final String number;
    private final Customer owner;
    private BigDecimal balance = new BigDecimal("0.00");
    private final List<LedgerEvent> history = new ArrayList<>();

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    String number() {
        return number;
    }

    Customer owner() {
        return owner;
    }

    BigDecimal balance() {
        return balance;
    }

    List<LedgerEvent> history() {
        return List.copyOf(history);
    }

    void apply(String code, String kind, BigDecimal delta) {
        BigDecimal next = balance.add(delta);
        if (next.signum() < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }
        balance = next;
        history.add(new LedgerEvent(
                code, number, kind, delta, balance));
    }
}

final class Bank {
    private final Map<String, Account> accounts =
            new LinkedHashMap<>();

    Account open(String number, Customer customer) {
        if (number == null || number.isBlank()
                || customer == null || accounts.containsKey(number)) {
            throw new IllegalArgumentException("account");
        }
        Account account = new Account(number, customer);
        accounts.put(number, account);
        return account;
    }

    void deposit(String code, Account account, BigDecimal amount) {
        requireMember(account);
        requirePositive(amount);
        account.apply(code, "DEPOSIT", amount);
    }

    void transfer(String code, Account source,
                  Account target, BigDecimal amount) {
        requireMember(source);
        requireMember(target);
        requirePositive(amount);
        if (source == target || source.balance().compareTo(amount) < 0) {
            throw new IllegalArgumentException("invalid transfer");
        }

        source.apply(code + "-D", "TRANSFER_OUT", amount.negate());
        target.apply(code + "-C", "TRANSFER_IN", amount);
    }

    private void requireMember(Account account) {
        if (account == null
                || accounts.get(account.number()) != account) {
            throw new IllegalArgumentException("unknown account");
        }
    }

    private static void requirePositive(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount");
        }
    }
}

public class BankObjectGraphDemo {
    public static void main(String[] args) {
        Bank bank = new Bank();
        Customer lan = new Customer("C01", "Lan");
        Customer minh = new Customer("C02", "Minh");

        Account a = bank.open("A100", lan);
        Account b = bank.open("A200", minh);
        Account c = bank.open("A300", lan);

        bank.deposit("T1", a, new BigDecimal("100.00"));
        bank.deposit("T2", b, new BigDecimal("20.00"));
        bank.transfer("T3", a, b, new BigDecimal("25.00"));

        System.out.println("A100=" + a.balance());
        System.out.println("A200=" + b.balance());
        System.out.println("A300=" + c.balance());
        System.out.println("owner A and C same="
                + (a.owner() == c.owner()));
        System.out.println("A entries=" + a.history().size());
        System.out.println("B entries=" + b.history().size());
        System.out.println("A last kind="
                + a.history().get(1).kind());
        System.out.println("total="
                + a.balance().add(b.balance()).add(c.balance()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 BankObjectGraphDemo.java
java BankObjectGraphDemo
~~~

**Stdout:**

~~~text
A100=75.00
A200=45.00
A300=0.00
owner A and C same=true
A entries=2
B entries=2
A last kind=TRANSFER_OUT
total=120.00
~~~

**Why this is correct:** the two deposits bring the system total from 0 to 120.00. Transferring 25.00 from A to B keeps the total at 120.00; A has 75.00 left, and B becomes 45.00. Account A and C both reference Customer Lan. The two ledger entries from the transfer record both directions: `TRANSFER_OUT` and `TRANSFER_IN`.

**Limitations to state clearly:** the two calls `source.apply`/`target.apply` are not an atomic database transaction; there is no rollback if an unexpected exception occurs in between, and there is no synchronization, idempotency, or persisted ledger. In the demo, the inputs are valid and `apply` performs no external I/O, so the output is deterministic; in a real system, atomicity/durability must be explicitly designed.

## 44. Common Design Mistakes

| Mistake | Problem | Fix |
| --- | --- | --- |
| Storing owner name separately in each account and forgetting to update it | Profile data diverges | Reference the live Customer or take an intentional snapshot |
| Using a live reference in an audit receipt | History "renames" itself to match the new profile | Store an immutable event-time snapshot |
| Using `==` to compare two Accounts loaded from DB | The same business entity may have multiple Java instances | Compare stable business IDs according to policy |
| Two objects with duplicate account numbers in a registry | Violates uniqueness | Enforce constraint at service/database |
| Public `balance` setter/field | No business-rule protection | Encapsulate and validate operations |
| Using double to represent money | Floating-point inaccuracies | BigDecimal from String, currency/scale policy |
| Transferring via two updates without a transaction | Partial failure/concurrency | Transaction boundary/locks/ledger |
| Not checking for negative/null amount | Wrong balance or unclear exceptions | Validate before mutation |
| Returning a mutable history list | Caller modifies/deletes data | Read-only snapshot, persisted ledger |
| Record Transaction holds Account and is assumed deeply immutable | Account is still mutable | Distinguish references from event snapshots |
| Bidirectional relationship updated arbitrarily | Owner/collections conflict | Use a single factory/service as the entry point |
| Retaining history graphs forever in a static cache | Retention/memory pressure | Pagination, eviction, persistence |
| Not distinguishing actor from account owner | Incorrect authorization | Identity, roles, authorization service |
| Confusing "closing an account" with object disposal | Business lifecycle differs from GC | Status model, history retention |
| Treating a Transaction constructor as a commit | Object creation does not persist | Explicit service/repository/transaction |

## 45. Roadmap for Building a Small Product from the Lesson Model

A step-by-step implementation approach:

1. **Start with two immutable values:** `CustomerId` and `AccountNumber`, or just Strings with validation.
2. **Define Customer:** immutable ID, profile fields according to rules.
3. **Define Account:** account ID, owner/memberships, currency, balance, and status.
4. **Create a factory/service:** account number uniqueness in an in-memory registry or DB.
5. **Create Transaction/LedgerEntry:** ID, account links/IDs, signed amounts, and event-time snapshots.
6. **Define operations:** deposit, withdraw, and transfer with clear preconditions and postconditions.
7. **Add tests:** aliasing, validation, balances, history, and duplicate IDs.
8. **Do not expose mutable internals:** defensive collection API; restrict setters.
9. **Separate DTOs from entities:** the external API carries only permitted data and stable IDs.
10. **Add persistence:** foreign keys, unique constraints, transactions, and migrations.
11. **Add security:** caller authentication, per-account authorization, and rate limiting/auditing.
12. **Add concurrency:** optimistic/pessimistic locking or an appropriate ledger-centric design.
13. **Add observability:** logs/metrics that do not expose sensitive information.
14. **Add idempotency and recovery:** retried requests do not debit funds twice.
15. **Verify complex domain cases:** multiple currencies, joint owners, fees, reversals, and reconciliation.

This lesson stops at the **Java core object relationships** layer: clarifying references and invariants. The downstream technologies are mentioned so learners do not misunderstand the scope of guarantees provided by in-memory code.

## 46. Practice Exercises

**Question 1.** An Account holds `Customer owner`. When passing Customer to the constructor, does Java create a copy of Customer?

**Question 2.** Two Accounts point to the same Customer. What is the result of `a.owner() == b.owner()`?

**Question 3.** If Customer is mutable and renamed, will an Account reading `owner.name()` via the live reference see the old name or the new name?

**Question 4.** If Transaction needs to store the owner's name at the time the document is printed, should you use a live reference or a snapshot?

**Question 5.** If two Account objects have the same `accountNumber` but were instantiated with `new` twice, is `a == b` automatically true?

**Question 6.** What semantics does `equals` of an Account class without an override have?

**Question 7.** Why should a List<Account> returned by Customer not simply be the internal mutable list?

**Question 8.** Does `List.copyOf(accounts)` deep-clone each Account object?

**Question 9.** State an invariant of a bidirectional Customer↔Account relationship.

**Question 10.** If Customer.accounts contains an Account belonging to another Customer, what problem arises?

**Question 11.** If a Transaction record has a final Account reference, is Account.balance immutable?

**Question 12.** Why is BigDecimal from String more suitable for amounts than `double` in the examples?

**Question 13.** Is `BigDecimal("10.0").equals(BigDecimal("10.00"))` true? What about `compareTo`?

**Question 14.** Where should a negative deposit amount be handled?

**Question 15.** With balance=20.00 and withdraw=30.00, what is the expected postcondition?

**Question 16.** If a Transfer holds source and target Account references without invoking a business operation, does it transfer balances automatically?

**Question 17.** After transferring 30.00 from an account with 80.00 to an account with 10.00, what are the two balances?

**Question 18.** Why is the total of balances preserved in the fee-free transfer example?

**Question 19.** Are two `debit` and `credit` calls automatically an atomic database transaction?

**Question 20.** If two threads deposit to the same account without locking, what errors can occur?

**Question 21.** Why does an immutable BigDecimal still not make a mutable balance field thread-safe?

**Question 22.** In a service synchronized with `synchronized`, which operations must share the same monitor so that an intermediate transfer state is not observed?

**Question 23.** If Account→Transaction→Account forms a reference cycle, does the JVM automatically treat it as a memory leak?

**Question 24.** If a static registry retains Account and history indefinitely, why does GC not collect the entries?

**Question 25.** How does `TransactionSnapshot(balanceAfter)` differ from `transaction.account().balance()`?

**Question 26.** When Customer changes name after a snapshot has been created, should the receipt snapshot change?

**Question 27.** Why are stable IDs/foreign keys needed when storing data in a database?

**Question 28.** Can you pass a Java object reference directly between two JVM processes and use it like a shared-memory address?

**Question 29.** Why is checking `account.owner() == requester` not sufficient as real-world authorization?

**Question 30.** When there are joint owners, what limitations can a single `Customer owner` field cause?

**Question 31.** Does an Account having a business status of CLOSED mean the Java object has been collected by GC?

**Question 32.** Should the entire audit history be stored solely in an unpersisted ArrayList?

**Question 33.** Why can mutating an account ID be dangerous if Account is already inside a HashMap?

**Question 34.** If a service returns a live Account object to the UI, what risks should be considered?

**Question 35.** Provide three tests that should be included when building an OOP mini-bank.

### Answers and Explanations

1. No; the constructor receives a reference value pointing to the same Customer object.
2. True if both store the exact same Customer object.
3. The new name, because the reference points to the live mutable Customer.
4. Store immutable/event-time snapshot fields and stable IDs.
5. No; `==` compares object identity, not the account number.
6. Object identity semantics, unless a different implementation is inherited/overridden.
7. The caller could remove/add Accounts, corrupting relationships and history.
8. No; the list structure is immutable, while the elements are still the original references.
9. If an Account belongs to Customer.accounts, then Account.owner must be that Customer under the single-owner policy.
10. The object graph contradicts itself; bidirectional navigation becomes inconsistent.
11. No; final fixes the reference, while Account itself can be mutable.
12. To avoid binary floating-point representation discrepancies for decimal amounts.
13. Equals is false because the scales differ; compareTo returns 0 because they have the same numeric value.
14. In the domain operation/constructor responsible for protecting invariants, before mutation.
15. Throw/reject and leave balance/history unchanged.
16. No; a record constructor does not automatically execute business logic.
17. Source 50.00, target 40.00.
18. With no fees, source decreases by the exact amount that target increases.
19. No; real business logic requires transactions/locking/recovery.
20. Lost update, stale read, or violated invariants.
21. Read–compute–assign consists of multiple steps and can be interleaved.
22. Mutations and reads need to be synchronized under the same service/transaction policy.
23. No; a cycle is collectible once it is no longer reachable from roots.
24. The registry holds strong references, so entries remain reachable.
25. The snapshot holds the value at event time; the live accessor reads the current balance.
26. No; history must retain the snapshot according to its contract.
27. To identify entities across sessions/processes and enforce referential integrity/uniqueness.
28. No; you must use serialization/IDs/network APIs rather than sharing heap references directly.
29. It does not authenticate the principal, roles/delegation, or business permissions; reference identity also differs across repository loads.
30. It cannot model multiple roles/owners; an association/membership model is needed.
31. No; business status is distinct from object reachability.
32. Not sufficient for audit/durability; an appropriate persisted ledger is needed.
33. Mutable keys/equality/hashCode can cause lookups to fail and break invariants.
34. Callers could observe/mutate shared state outside the boundary, leak data, or lack authorization.
35. Examples: same Customer reference across two Accounts; transfer preserves total balances; withdrawing beyond the limit does not mutate state.

## 47. Design and Code Review Checklist

- [ ] Do Customer, Account, and Transaction have distinct responsibilities?
- [ ] Are relationships represented by references or IDs at the appropriate layer?
- [ ] Is the difference between a reference alias and an object copy understood?
- [ ] Is `==` distinguished from the business identity `accountNumber`?
- [ ] Are owner/account IDs prevented from changing arbitrarily?
- [ ] If a Customer owns multiple Accounts, is there an entry point that keeps the relationship consistent?
- [ ] If there is bidirectional navigation, are there invariants/tests for both sides?
- [ ] Is the mutable account balance private and modified only through domain operations?
- [ ] Is the amount validated as non-null/positive with appropriate currency/scale?
- [ ] Is BigDecimal from String used instead of double for money examples?
- [ ] Does a failed withdraw avoid causing a partial update/history entry?
- [ ] Does transfer use the correct two account references and preserve balance conservation when fee-free?
- [ ] Is using reference identity `==` as the sole authorization check avoided?
- [ ] Is the same business entity across multiple ORM sessions accounted for?
- [ ] Are immutable snapshots used for history instead of relying entirely on the live profile?
- [ ] Is it understood that a final record component reference only guarantees shallow immutability?
- [ ] Does the history getter avoid exposing the internal mutable list?
- [ ] Does history/ledger have appropriate ID, ordering, and persistence for a real system?
- [ ] Do caches/static registries have a retention policy?
- [ ] Do you avoid assuming GC will collect object graphs that remain strongly reachable?
- [ ] Is concurrency of deposit/withdraw/transfer protected within scope?
- [ ] Do you avoid claiming two mutations constitute an ACID transaction?
- [ ] Are ID uniqueness, invalid inputs, and transfer failures tested?
- [ ] Are joint ownership/roles considered if required by the domain?
- [ ] Is the account's CLOSED status not confused with resource close/GC?
- [ ] Is ownership/reference vs. snapshot documented at the API boundary?
- [ ] Is sensitive data kept out of toString/logging in a real product?

## 48. Official Java 17 Documentation

- [JLS 17 §4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): reference types and object references.
- [JLS 17 §4.12 — Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12): variables, field values, and references.
- [JLS 17 §15.9 — Class Instance Creation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): creating objects with new.
- [JLS 17 §15.21.3 — Reference Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21.3): meaning of `==` for references.
- [JLS 17 §8.3.1.2 — final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): final reference fields.
- [JLS 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record payload and component accessors.
- [Java SE 17 — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal arithmetic and scale.
- [Java SE 17 — `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable copy of a collection structure.
- [Java SE 17 — `Map`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): key/value associations.
- [Java SE 17 — `HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): set based on equals/hashCode.
- [Java SE 17 — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): constructor input checks.
- [Java SE 17 — `Object.equals`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): default identity equality.
- [Java SE 17 — `Thread`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): concurrency and multi-threaded programs.
- [JLS 17 §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java memory model/synchronization.
- [Java SE 17 — `Connection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): JDBC lifecycle/commit/rollback.
- [Java SE 17 — `PreparedStatement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): prepared SQL operations.
- [Java SE 17 — `ResultSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): SQL result cursor and resource lifecycle.

## 49. Summary

**An object-oriented Java model can link Customer, Account, and Transaction using typed reference fields.** Two accounts can both point to one Customer object; a transaction can point to the related account or both the source and target accounts of a transfer. This enables clear navigation and sharing, while also creating the responsibility to keep **relationships and state consistent**.

Always separate three concepts: **object identity** (same Java instance), **business identity** (same account/customer ID), and **historical snapshot** (value recorded at event time). A live reference makes current updates visible; an immutable snapshot keeps history from changing along with a new profile or balance.

For money, use BigDecimal and validate amount/currency. For bidirectional relationships, manage updates through a single entry point. For history, do not expose mutable collections and do not confuse a record's final reference with deep immutability. For transfers, **two balance-changing operations do not automatically form an atomic/durable transaction**: a real system needs security, persistence, a ledger, concurrency, recovery, and tests.

From this lesson, what matters is not writing lots of references, but deciding **what each reference means, who owns the object, who is allowed to modify it, and what must remain true after every business operation**.
