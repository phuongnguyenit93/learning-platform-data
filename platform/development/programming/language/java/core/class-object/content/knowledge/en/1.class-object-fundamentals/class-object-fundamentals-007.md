# Running Example: Modeling a Bank Account with Classes and Objects in Java

A bank account is a clear example of the relationship between **class**, **object**, **state**, and **behavior**. Instead of studying `class` and `new` syntax in isolation, this lesson goes from real-world requirements to a runnable Java program, and then explains exactly which concept each part of the program corresponds to.

**Scope:** this is an educational model running in a single process, sequentially one statement at a time, with amounts denominated in **whole Vietnamese dong (VND)**. The goal is to understand how to design and use objects. A real-world banking system also requires authentication, persistent storage, transaction history, concurrency control, and database transactions.

## 1. Translating real-world requirements into a model

Suppose the program must manage two accounts, An and Binh, with the following requirements:

1. Each account has an account number, an owner name, and a balance.
2. Create an account with a non-negative initial balance.
3. You can **deposit**, **withdraw**, and **transfer** money from one account to another.
4. The amount of each transaction must be positive; do not withdraw or transfer more than the balance.
5. Only methods of the class may directly modify the balance; external code may only read the balance.
6. Changing An's balance does not automatically change Binh's balance, unless a transfer operation occurs between the two accounts.

We define a **class** `BankAccount` as the common type. Each specific account is an **object** of this class.

| Problem element | Representation in Java | Meaning |
| --- | --- | --- |
| Account type | `class BankAccount` | Common definition of accounts |
| Account number | Field `accountNumber` | Business identification data of an account |
| Owner name | Field `ownerName` | Descriptive data of the account owner |
| Balance | Field `balance` | Individual state, changing with transactions |
| Open an account | Constructor `BankAccount(...)` | Establishes a valid initial state |
| Deposit money | `deposit(amount)` | Behavior that increases the balance |
| Withdraw money | `withdraw(amount)` | Behavior that decreases the balance with validation |
| Transfer money | `transferTo(receiver, amount)` | Behavior that affects two objects |
| View information | `summary()`, `balance()` | Reads state without allowing external code to modify it directly |

Two example expressions:

~~~java
BankAccount an = new BankAccount("VN001", "An", 1_000_000);
BankAccount binh = new BankAccount("VN002", "Binh", 500_000);
~~~

Both have the **type** `BankAccount`, yet they create **two different objects**. `an` and `binh` are **reference variables**, while the specific balance data belongs to the objects they point to.

## 2. Design decisions before writing code

### State and data immutability

For this simple model, the account number and owner name are set once when the object is created, so we use `private final String`. The balance changes throughout the object's lifetime, so we use `private long balance`. `final` prevents a field from being reassigned after initialization; it does not automatically make the entire object immutable.

All fields are declared `private` so calling code cannot perform dangerous operations like `an.balance = -100`. Valid changes must go through methods with validation.

### Rules that must always hold (invariants)

A valid `BankAccount` object in this lesson must satisfy:

- `accountNumber` and `ownerName` are not `null`, empty, or whitespace-only.
- `balance >= 0`.
- Deposit, withdrawal, and transfer amounts are positive integers.
- Do not transfer money to the transferring account itself.
- If a withdrawal/transfer request is invalid, the balances of the involved accounts remain unchanged.

The constructor validates the initial state. Methods that modify state check conditions before updating.

### Representing money

Because this example uses **whole VND amounts**, `long` is simple and avoids the binary representation errors of using `double` for monetary addition and subtraction. `long` still has value limits; we use `Math.addExact` to detect addition overflow instead of silently producing a wrong result. For amounts with fractional units or multiple currencies, a more appropriate design is usually `BigDecimal` together with explicit rounding rules, scale, and currency type.

## 3. Complete program

Create exactly one file named **`BankAccountDemo.java`** in the working directory. The file has two top-level classes: `BankAccount` is not `public`; `BankAccountDemo` is the `public` class containing `main`, so the file name must match `BankAccountDemo`.

~~~java
import java.util.Objects;

class BankAccount {
    private final String accountNumber;
    private final String ownerName;
    private long balance;

    BankAccount(String accountNumber, String ownerName, long initialBalance) {
        if (accountNumber == null || accountNumber.isBlank()) {
            throw new IllegalArgumentException("Số tài khoản không hợp lệ");
        }
        if (ownerName == null || ownerName.isBlank()) {
            throw new IllegalArgumentException("Tên chủ tài khoản không hợp lệ");
        }
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Số dư ban đầu không được âm");
        }

        this.accountNumber = accountNumber;
        this.ownerName = ownerName;
        this.balance = initialBalance;
    }

    String accountNumber() {
        return accountNumber;
    }

    long balance() {
        return balance;
    }

    String summary() {
        return accountNumber + " | " + ownerName + " | " + balance + " VND";
    }

    void deposit(long amount) {
        requirePositive(amount);
        balance = Math.addExact(balance, amount);
    }

    void withdraw(long amount) {
        requirePositive(amount);
        if (amount > balance) {
            throw new IllegalArgumentException("Số dư không đủ");
        }
        balance -= amount;
    }

    void transferTo(BankAccount receiver, long amount) {
        Objects.requireNonNull(receiver, "receiver");
        requirePositive(amount);

        if (receiver == this) {
            throw new IllegalArgumentException("Không thể chuyển cho chính mình");
        }
        if (amount > balance) {
            throw new IllegalArgumentException("Số dư không đủ");
        }

        // Compute beforehand so that if addition overflows, neither balance has been modified yet.
        long receiverNewBalance = Math.addExact(receiver.balance, amount);

        balance -= amount;
        receiver.balance = receiverNewBalance;
    }

    private static void requirePositive(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
    }
}

public class BankAccountDemo {
    public static void main(String[] args) {
        BankAccount an = new BankAccount("VN001", "An", 1_000_000);
        BankAccount binh = new BankAccount("VN002", "Binh", 500_000);

        System.out.println("Ban đầu:");
        System.out.println(an.summary());
        System.out.println(binh.summary());

        an.deposit(200_000);
        an.withdraw(50_000);
        an.transferTo(binh, 300_000);

        System.out.println("Sau giao dịch:");
        System.out.println(an.summary());
        System.out.println(binh.summary());

        BankAccount anotherNameForAn = an;
        System.out.println("an == anotherNameForAn: "
                + (an == anotherNameForAn));
        System.out.println("an == binh: " + (an == binh));

        try {
            an.withdraw(900_000);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rút thất bại: " + ex.getMessage());
        }

        System.out.println("Số dư An cuối: " + an.balance() + " VND");
    }
}
~~~

Requires **Java 17 or later**. In the directory containing the file, run:

~~~bash
javac -encoding UTF-8 BankAccountDemo.java
java BankAccountDemo
~~~

Output on stdout:

~~~text
Ban đầu:
VN001 | An | 1000000 VND
VN002 | Binh | 500000 VND
Sau giao dịch:
VN001 | An | 850000 VND
VN002 | Binh | 800000 VND
an == anotherNameForAn: true
an == binh: false
Rút thất bại: Số dư không đủ
Số dư An cuối: 850000 VND
~~~

`javac` may generate the `BankAccount.class` and `BankAccountDemo.class` files. A separate `BankAccount.java` file is not needed to run this example. If split into two files when expanding the project, `public` class naming and package rules must be applied consistently.

## 4. Tracing objects and reference variables

After the two `new BankAccount(...)` statements, we can visualize it as:

~~~text
CLASS: BankAccount
  defines shared fields and methods
                       |
                       v
  Variable an -------------> Object A
                             accountNumber = "VN001"
                             ownerName = "An"
                             balance = 1000000

  Variable binh -----------> Object B
                             accountNumber = "VN002"
                             ownerName = "Binh"
                             balance = 500000
~~~

The methods `deposit`, `withdraw`, and `transferTo` are **defined on the class**; when an instance method is called, the program performs the operation on the exact receiver object of that call.

`an.deposit(200_000)` affects object A. `binh` does not change because the two objects hold two separate `balance` fields. `an.transferTo(binh, 300_000)` is a case where one method intentionally updates **two** objects: the source object received via `this` and the target object received via the `receiver` parameter.

In the constructor:

~~~java
this.accountNumber = accountNumber;
this.ownerName = ownerName;
this.balance = initialBalance;
~~~

`this.accountNumber` is the field of the object being initialized; `accountNumber` without `this` on the right-hand side is the parameter. The same applies to the owner name and initial balance. `this` does not exist in a `static` method, because a `static` method is not called on a specific receiver object.

The statement:

~~~java
BankAccount anotherNameForAn = an;
~~~

**Does not create a new account.** It only copies the reference value from `an` to another variable. Therefore, `an == anotherNameForAn` evaluates to `true`: both variables point to the **same object**. `an == binh` evaluates to `false`: the two `new` expressions created two different instances.

If `anotherNameForAn.deposit(10_000)` is called, `an.balance()` will also reflect that change, because both variables observe the same object. Conversely, to have a separate object, you must create another instance in an appropriate way.

## 5. Tracking state after each transaction

We can verify every calculation without guessing the result.

| Step | Statement | An (VND) | Binh (VND) | Explanation |
| --- | --- | ---: | ---: | --- |
| 0 | Create two objects | 1,000,000 | 500,000 | Constructor receives initial balances |
| 1 | `an.deposit(200_000)` | 1,200,000 | 500,000 | Only An's account is credited |
| 2 | `an.withdraw(50_000)` | 1,150,000 | 500,000 | An has sufficient funds, so it is deducted |
| 3 | `an.transferTo(binh, 300_000)` | 850,000 | 800,000 | Deduct 300,000 from An and add 300,000 to Binh |
| 4 | `an.withdraw(900_000)` | 850,000 | 800,000 | Rejected: request exceeds balance |

At step 3, the **total balance** before and after the transfer remains `1_650_000` VND because the transaction only moves money between the two simulated accounts: `1_150_000 + 500_000 = 850_000 + 800_000`. At step 4, the exception occurs **before** the balance subtraction statement, so An's account still retains 850,000 VND.

Note: deposits/withdrawals in this model do not model external sources or destinations of money, so a conservation-of-total-funds law cannot be inferred for all operations. This is an example of object state, not yet a ledger system.

## 6. Explaining the mechanics of each method

### Constructor: creating valid state from the start

The constructor `BankAccount(String, String, long)` is invoked when executing `new BankAccount(...)`. It validates the input data and then initializes the three fields. If the request is invalid, `IllegalArgumentException` is thrown and the object creation expression does not complete normally.

Key distinction: **a constructor has no return type** (do not even write `void`), its name matches the class name, and it is only part of the instance creation process. `new` is the expression that creates the object. Two constructor calls correspond to two separate objects.

### `deposit`: modifying the state of the receiver object

~~~java
void deposit(long amount) {
    requirePositive(amount);
    balance = Math.addExact(balance, amount);
}
~~~

First, it checks `amount > 0`. Next, `Math.addExact` performs exact addition of the two `long` values or throws `ArithmeticException` on overflow. Because the addition is evaluated before the assignment, the balance does not change if an overflow error occurs. `balance` inside an instance method is equivalent to `this.balance` in this context.

### `withdraw`: without breaking the invariant

~~~java
void withdraw(long amount) {
    requirePositive(amount);
    if (amount > balance) {
        throw new IllegalArgumentException("Số dư không đủ");
    }
    balance -= amount;
}
~~~

Checking that the amount is positive and checking the balance **happen before** the subtraction. As a result, a withdrawal call that leaves `balance` negative cannot complete through this method path. External code also cannot directly modify the `private balance` field.

### `transferTo`: interaction between two objects

Transferring money is an operation involving two objects:

- `this` is the **sending** account, which is the object to the left of the dot in `an.transferTo(...)`.
- `receiver` is the **receiving** account, passed via the argument; in the example, it is the object referenced by `binh`.

The checks sequentially reject a `null` receiver, a non-positive amount, transferring to oneself, and insufficient balance. The expression `receiver == this` compares **object identity**, not account number or account owner.

After validation, the method computes `receiverNewBalance` before assigning to avoid deducting from the sender only to discover that crediting the receiver overflows `long`. This improves consistency in a **sequentially executed example**; it does not create a bank transaction with ACID guarantees. When multiple threads, multiple processes, or system failures occur, proper synchronization, storage transactions, and recovery mechanisms are still required.

### `summary` and `balance`: reading data without granting modification access

`summary()` creates a string representation of the state. `balance()` returns a `long` value; calling `long amount = an.balance()` only copies the integer without exposing a way to mutate the internal field. This is a simple way to separate **read state** access from **modify state** access.

## 7. Distinguishing object identity from business identity

There are two distinct questions:

1. **Do two references point to the same object in the JVM?** For reference types, `a == b` answers this question.
2. **Do two records describe the same business account?** This question is typically based on `accountNumber` along with the system's identification rules, not solely on `==`.

Illustrative example (the lines below are a snippet placed inside a method, not a standalone program):

~~~java
BankAccount first = new BankAccount("VN100", "Lan", 100_000);
BankAccount second = new BankAccount("VN100", "Lan", 100_000);

System.out.println(first == second); // false
System.out.println(first.accountNumber().equals(second.accountNumber())); // true
~~~

The two objects have **different reference identities** because they were created by two `new` calls, even though they share the same account number. In a real application, a repository usually has to ensure that account numbers are unique; the constructor in this example has no knowledge of other existing objects and therefore **does not enforce system-wide uniqueness**.

You should not arbitrarily override `equals()` just to compare every field of an account. Choosing business equality criteria and their relationship with `hashCode()` is a separate design decision, especially when an object has mutable state.

## 8. Cases to test

Lessons about objects are not just about successful outcomes. The cases below show whether the state-protection guards work as expected.

| Operation | Expected result | State after error |
| --- | --- | --- |
| `new BankAccount("", "An", 0)` | `IllegalArgumentException` | No valid instance completes creation |
| `new BankAccount("VN004", "An", -1)` | `IllegalArgumentException` | No valid instance completes creation |
| `an.deposit(0)` | `IllegalArgumentException` | `an.balance` remains unchanged |
| `an.withdraw(-10)` | `IllegalArgumentException` | `an.balance` remains unchanged |
| `an.withdraw(900_000)` when An has 850,000 | `IllegalArgumentException` | An still has 850,000 |
| `an.transferTo(an, 1)` | `IllegalArgumentException` | Unchanged |
| `an.transferTo(null, 1)` | `NullPointerException` | Unchanged |
| `an.deposit(Long.MAX_VALUE)` when An has a positive balance | `ArithmeticException` | Balance unchanged due to addition overflow |

In these illustrative test rows, `an` is assumed to reference an already created account with an appropriate balance. These are **test scenarios**, not statements executed in the `main` method above.

Another useful scenario: if the receiving account has a balance near `Long.MAX_VALUE`, `transferTo` may throw `ArithmeticException` when computing the receiver's new balance; in the sequential flow written above, both objects' balances remain unchanged because execution has not reached the final two assignments.

## 9. Common modeling mistakes

| Mistake | Consequence | How to address |
| --- | --- | --- |
| Using `public long balance` | Anywhere can set a negative balance or bypass business rules | Keep it `private` and change state through methods |
| Using `double` to store monetary amounts | Binary representation errors can skew financial calculations | Use integer smallest units or `BigDecimal` as required |
| Writing `BankAccount other = an` and assuming a new account was created | Both variables share the exact same object and state | Distinguish copying a reference from creating an object |
| Making `balance` `static` | All accounts see a single shared balance field | Use an instance field for each account's balance |
| Updating the balance first, validating afterward | An invalid request may leave state altered | Check conditions and perform failable calculations before assigning |
| Not checking `amount <= 0` | A negative deposit becomes a withdrawal, or a negative withdrawal becomes a deposit | Check for a positive amount at the start of each behavior |
| Relying on `==` to identify accounts by account number | Two different instances can have the same business identifier | Distinguish JVM identity from business keys |
| Assuming an object is persisted after calling `new` | Restarting the program loses in-memory state | Integrate separate storage and transactions when needed |
| Assuming the current `transferTo` is thread-safe | Concurrent transactions may read/write inconsistent balances | Design synchronization, transaction coordination, and storage to meet requirements |

One often overlooked point: `private` only restricts language-level access and supports encapsulation; it does not replace authentication, authorization, or data protection in a real banking application.

## 10. From a simple example to a larger design

In this model, one class is enough to understand the foundational concepts. As requirements grow, you can consider separating responsibilities:

- `BankAccount` holds the core data and rules of a single account.
- A transaction service coordinates transfers between accounts, validates requests, and uses an appropriate transaction mechanism.
- A repository manages unique identifiers, and reads and writes persistent state.
- A separate transaction record can store timestamp, amount, sender/receiver accounts, transaction ID, and outcome for reconciliation.

This is a direction for future expansion, not a mandatory requirement to understand `class` and `object`. In this demo, **objects live only in memory** and all operations run sequentially in `main`; you should not use this model directly to handle real money or conclude that it is secure enough for a banking system.

The strength of the current design is that you can clearly observe **one class creating multiple objects, each object having its own state, and objects cooperating through method calls**.

## 11. Practice exercises with the same model

**Exercise 1 — Predict the state.** Create account C with a balance of `100_000`, call `deposit(20_000)`, and then `withdraw(30_000)`. What is the final balance? If you add a `withdraw(100_000)` call, what happens?

**Exercise 2 — Distinguish objects and variables.** Given `BankAccount alias = an;`. After calling `alias.deposit(5_000)`, how does the value of `an.balance()` change? Why? What would be different if you wrote `new BankAccount(...)` to create another account?

**Exercise 3 — Changing requirements.** Allow an account to have a per-withdrawal limit. Should that check be placed in the calling `main` code or in the class's `withdraw` method? If another currency is added, is using only `long balance` expressive enough?

**Exercise 4 — Spot the bug.** A developer writes `balance -= amount` at the start of `withdraw` and only afterward checks `amount > 0` and whether the balance is negative. Explain why this approach can corrupt the state and rewrite it in validate-first, update-later order.

Quick check: Exercise 1 gives `90_000` and the 100,000 withdrawal is rejected with the balance unchanged; Exercise 2 increases the balance on the **same object** so both variables observe the new value; Exercise 3 needs to enforce the business limit where state mutation is controlled along with a monetary model that specifies unit/currency explicitly; Exercise 4 must check that the amount is positive and the balance is sufficient before subtracting.

When looking at any class design, ask yourself four questions: **What does the class describe? What state does each object hold? Who is allowed to change that state? When objects interact, what rules must always hold?** The bank account example is precisely how those four questions are applied in Java.
