# Classes and objects: a bank account exercise — Java OOP

## 1. Learning objectives

This exercise simulates a simple bank account to practice turning business requirements into Java **classes**, **objects**, **fields**, **methods**, **constructors**, and **data encapsulation**.

After completing the exercise, you will be able to:
- Represent an account with the BankAccount class and create multiple independent objects using the new keyword.
- Use private fields to protect balances and final for information that must not change after initialization.
- Write a constructor that validates the initial state and provide deposit, withdrawal, and transfer methods.
- Distinguish reference variables, actual objects, state, and behavior.
- Check boundary conditions, rejected transactions, and integer overflow risks.
- Write unit tests to verify business rules without connecting to a real bank.

This is an **educational OOP simulation**, not a real banking system. All data is held in memory; there is no authentication, authorization, database, accounting ledger, or distributed transaction support.

## 2. From requirements to classes and objects

Suppose we need to manage two accounts:

- Account A: account number TK001, owner An, initial balance 1.000.000 VND.
- Account B: account number TK002, owner Bình, initial balance 200.000 VND.
- Allow deposits, withdrawals, and transfers from A to B.
- Disallow negative balances and 0 or negative deposit, withdrawal, or transfer amounts.
- Report errors when an operation exceeds the long range; do not allow silent overflow.

The OOP concepts involved:

| OOP concept | Application in this example | Meaning |
| --- | --- | --- |
| Class | BankAccount | Shared blueprint for an account |
| Object | accountA, accountB | Two concrete accounts, each with its own state |
| Field | accountNumber, ownerName, balanceVnd | Data belonging to each object |
| Constructor | BankAccount(number, owner, initialBalance) | Initializes an object in a valid state |
| Method | deposit, withdraw, transferTo | Permitted operations on the balance |
| Encapsulation | private balanceVnd and public methods | Prevents external code from assigning arbitrary balances |
| Reference | accountA variable of type BankAccount | Refers to an object in memory |
| final field | accountNumber, ownerName | Cannot be reassigned after the constructor |

Class model:

~~~mermaid
classDiagram
    class BankAccount {
        -String accountNumber
        -String ownerName
        -long balanceVnd
        +BankAccount(accountNumber, ownerName, initialBalanceVnd)
        +getAccountNumber() String
        +getOwnerName() String
        +getBalanceVnd() long
        +deposit(amountVnd) void
        +withdraw(amountVnd) void
        +transferTo(receiver, amountVnd) void
    }
    class BankDemo {
        +main(args) void
    }
    BankDemo --> BankAccount : tạo và gọi phương thức
    BankAccount --> BankAccount : transferTo(receiver)
~~~

Key point: **accountA and accountB are created from the same BankAccount class but are separate objects**. Calling accountA.deposit(...) does not automatically change accountB's balance.

## 3. Defining the contract for each operation

We use **long** to store whole VND amounts, avoiding float/double in this integer-money example. For fractional amounts or multiple currencies, consider BigDecimal together with a currency code; do not use double to represent exact monetary amounts.

| Operation | Valid conditions | Result | Invalid case |
| --- | --- | --- | --- |
| Create account | Number and name are nonblank; initial balance >= 0 | Object is created | IllegalArgumentException |
| deposit(amount) | amount > 0; addition does not overflow long | balance increases by amount | IllegalArgumentException or ArithmeticException |
| withdraw(amount) | amount > 0 and amount <= balance | balance decreases by amount | IllegalArgumentException or IllegalStateException |
| transferTo(receiver, amount) | receiver is non-null and different from this account; amount > 0; sufficient funds; receiver balance does not overflow | Sender decreases and receiver increases by the same amount | NullPointerException, IllegalArgumentException, IllegalStateException, or ArithmeticException |
| getBalanceVnd() | No precondition | Returns current balance | Does not change state |

Exercise convention: an invalid operation **throws an exception without changing balances**; a valid transaction method completes normally. Every precondition is checked before mutating state.

Single-threaded transfer flow:

~~~mermaid
flowchart TD
    A["accountA.transferTo(accountB, amount)"] --> B{"Người nhận hợp lệ và khác người gửi?"}
    B -->|Không| E["Ném lỗi, không đổi số dư"]
    B -->|Có| C{"Số tiền > 0 và bên gửi đủ tiền?"}
    C -->|Không| E
    C -->|Có| D{"Số dư bên nhận cộng amount có tràn long?"}
    D -->|Có| E
    D -->|Không| F["Giảm số dư bên gửi"]
    F --> G["Tăng số dư bên nhận"]
    G --> H["Hoàn tất"]
~~~

**Intentional limitation:** transfers here are synchronous operations on two objects in the same process, assuming single-threaded access. This design **does not guarantee thread safety under concurrent execution** and has no database transaction; do not use this logic in place of real financial transaction mechanisms.

## 4. Building the complete program

Java 17 + Maven project structure:

~~~text
bank-account-oop/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── BankAccount.java
    │   └── BankDemo.java
    └── test/java/vn/example/
        └── BankAccountTest.java
~~~

### 4.1. Maven configuration

Create the pom.xml file:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>bank-account-oop</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. The BankAccount class

Create src/main/java/vn/example/BankAccount.java:

~~~java
package vn.example;

import java.util.Objects;

/**
 * Mô phỏng một tài khoản với tiền nguyên VND.
 * Phiên bản học tập: sử dụng trong một luồng, không lưu dữ liệu bền vững.
 */
public final class BankAccount {

    private final String accountNumber;
    private final String ownerName;
    private long balanceVnd;

    public BankAccount(
            String accountNumber,
            String ownerName,
            long initialBalanceVnd) {

        this.accountNumber = requireText(
                accountNumber, "accountNumber");
        this.ownerName = requireText(ownerName, "ownerName");

        if (initialBalanceVnd < 0) {
            throw new IllegalArgumentException(
                    "Initial balance must not be negative");
        }

        this.balanceVnd = initialBalanceVnd;
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
        return value.trim();
    }

    private static void requirePositive(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException(
                    "Amount must be positive");
        }
    }

    public String getAccountNumber() {
        return accountNumber;
    }

    public String getOwnerName() {
        return ownerName;
    }

    public long getBalanceVnd() {
        return balanceVnd;
    }

    public void deposit(long amountVnd) {
        requirePositive(amountVnd);
        // Tính trước; nếu tràn long thì ném ArithmeticException.
        long newBalance = Math.addExact(balanceVnd, amountVnd);
        balanceVnd = newBalance;
    }

    public void withdraw(long amountVnd) {
        requirePositive(amountVnd);

        if (amountVnd > balanceVnd) {
            throw new IllegalStateException(
                    "Insufficient balance");
        }

        balanceVnd -= amountVnd;
    }

    public void transferTo(BankAccount receiver, long amountVnd) {
        Objects.requireNonNull(receiver, "receiver");

        if (receiver == this) {
            throw new IllegalArgumentException(
                    "Cannot transfer to the same object");
        }

        requirePositive(amountVnd);

        if (amountVnd > balanceVnd) {
            throw new IllegalStateException(
                    "Insufficient balance");
        }

        // Kiểm tra tràn số phía người nhận trước khi thay đổi hai tài khoản.
        long receiverNewBalance = Math.addExact(
                receiver.balanceVnd, amountVnd);

        balanceVnd -= amountVnd;
        receiver.balanceVnd = receiverNewBalance;
    }
}
~~~

**Explanation of the important parts:**

- **private final String accountNumber, ownerName:** the account number and owner name cannot be reassigned after initialization. Here, final does not guarantee system-wide uniqueness; a real application needs account-number management.
- **private long balanceVnd:** mutable state, but other classes cannot directly assign a negative or arbitrary balance.
- **constructor:** validates all initial values before the object is used.
- **getBalanceVnd:** allows balance reads without exposing an arbitrary setBalanceVnd method.
- **deposit:** calls Math.addExact to detect overflow before updating the balance.
- **withdraw:** checks that the amount is positive and the balance is sufficient before subtracting.
- **transferTo:** accepts **another BankAccount object**. Because the code is inside the same class, Java permits access to the private balanceVnd field of another BankAccount instance.
- **receiver == this:** compares object identity. Two references can point to the same object; this prevents transfers from an account to itself.

Note: this version can create two objects with the same accountNumber because the constructor only checks that the value is nonblank. This is a limitation of the learning model; a real system requires a repository/service to manage identity and enforce uniqueness.

### 4.3. Running the program and creating two objects

Create src/main/java/vn/example/BankDemo.java:

~~~java
package vn.example;

public final class BankDemo {

    public static void main(String[] args) {
        BankAccount accountA =
                new BankAccount("TK001", "An", 1_000_000L);
        BankAccount accountB =
                new BankAccount("TK002", "Binh", 200_000L);

        accountA.deposit(200_000L);
        accountA.withdraw(50_000L);
        accountA.transferTo(accountB, 300_000L);

        System.out.println(
                accountA.getAccountNumber()
                + " - " + accountA.getOwnerName()
                + ": " + accountA.getBalanceVnd() + " VND");

        System.out.println(
                accountB.getAccountNumber()
                + " - " + accountB.getOwnerName()
                + ": " + accountB.getBalanceVnd() + " VND");
    }
}
~~~

How to interpret the expression:

~~~java
BankAccount accountA = new BankAccount("TK001", "An", 1_000_000L);
~~~

- **BankAccount** on the left is the reference variable's type.
- **accountA** is the variable name, not the entire object.
- **new BankAccount(...)** creates a BankAccount object and invokes its constructor.
- The dot in **accountA.deposit(...)** invokes behavior on the object referenced by the variable.
- Each object has its own balance; the transfer demonstrates how objects interact through methods.

Run from the directory containing pom.xml:

~~~bash
mvn test
mvn -q -DskipTests package
java -cp target/classes vn.example.BankDemo
~~~

Expected output:

~~~text
TK001 - An: 850000 VND
TK002 - Binh: 500000 VND
~~~

Manual verification:

| Step | Account A (VND) | Account B (VND) |
| --- | ---: | ---: |
| Initial | 1.000.000 | 200.000 |
| A deposits 200.000 | 1.200.000 | 200.000 |
| A withdraws 50.000 | 1.150.000 | 200.000 |
| A transfers 300.000 to B | **850.000** | **500.000** |

During the transfer, the combined balances before and after remain 1.350.000 VND. A transfer neither creates nor loses money **when the valid operation completes in this single-threaded model**.

## 5. Testing behavior and invariants with JUnit 5

Running main once is not enough: good object-oriented code must be tested in multiple states, especially when operations are rejected.

Create src/test/java/vn/example/BankAccountTest.java:

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class BankAccountTest {

    @Test
    void newlyCreatedAccountsHaveIndependentState() {
        BankAccount a = new BankAccount("TK001", "An", 100L);
        BankAccount b = new BankAccount("TK002", "Binh", 50L);

        a.deposit(20L);

        assertEquals(120L, a.getBalanceVnd());
        assertEquals(50L, b.getBalanceVnd());
        assertEquals("TK001", a.getAccountNumber());
        assertEquals("Binh", b.getOwnerName());
    }

    @Test
    void depositIncreasesBalance() {
        BankAccount account = new BankAccount("A", "An", 100L);

        account.deposit(25L);

        assertEquals(125L, account.getBalanceVnd());
    }

    @Test
    void withdrawDecreasesBalance() {
        BankAccount account = new BankAccount("A", "An", 100L);

        account.withdraw(100L);

        assertEquals(0L, account.getBalanceVnd());
    }

    @Test
    void cannotWithdrawMoreThanAvailableBalance() {
        BankAccount account = new BankAccount("A", "An", 100L);

        assertThrows(IllegalStateException.class,
                () -> account.withdraw(101L));

        assertEquals(100L, account.getBalanceVnd());
    }

    @Test
    void transactionsRejectZeroAndNegativeAmounts() {
        BankAccount a = new BankAccount("A", "An", 100L);
        BankAccount b = new BankAccount("B", "Binh", 50L);

        assertThrows(IllegalArgumentException.class,
                () -> a.deposit(0L));
        assertThrows(IllegalArgumentException.class,
                () -> a.deposit(-2L));
        assertThrows(IllegalArgumentException.class,
                () -> a.withdraw(0L));
        assertThrows(IllegalArgumentException.class,
                () -> a.transferTo(b, -10L));

        assertEquals(100L, a.getBalanceVnd());
        assertEquals(50L, b.getBalanceVnd());
    }

    @Test
    void transferMovesMoneyBetweenTwoObjects() {
        BankAccount a = new BankAccount("A", "An", 200L);
        BankAccount b = new BankAccount("B", "Binh", 50L);

        a.transferTo(b, 80L);

        assertEquals(120L, a.getBalanceVnd());
        assertEquals(130L, b.getBalanceVnd());
        assertEquals(250L,
                a.getBalanceVnd() + b.getBalanceVnd());
    }

    @Test
    void failedTransferPreservesBothBalances() {
        BankAccount a = new BankAccount("A", "An", 40L);
        BankAccount b = new BankAccount("B", "Binh", 70L);

        assertThrows(IllegalStateException.class,
                () -> a.transferTo(b, 41L));

        assertEquals(40L, a.getBalanceVnd());
        assertEquals(70L, b.getBalanceVnd());
    }

    @Test
    void cannotTransferToSameAccountOrNull() {
        BankAccount account =
                new BankAccount("A", "An", 100L);

        assertThrows(IllegalArgumentException.class,
                () -> account.transferTo(account, 10L));
        assertThrows(NullPointerException.class,
                () -> account.transferTo(null, 10L));

        assertEquals(100L, account.getBalanceVnd());
    }

    @Test
    void overflowFailsWithoutChangingBalances() {
        BankAccount a = new BankAccount("A", "An", 100L);
        BankAccount b =
                new BankAccount("B", "Binh", Long.MAX_VALUE);

        assertThrows(ArithmeticException.class,
                () -> a.transferTo(b, 1L));

        assertEquals(100L, a.getBalanceVnd());
        assertEquals(Long.MAX_VALUE, b.getBalanceVnd());

        assertThrows(ArithmeticException.class,
                () -> b.deposit(1L));
        assertEquals(Long.MAX_VALUE, b.getBalanceVnd());
    }

    @Test
    void constructorRejectsInvalidInitialState() {
        assertThrows(IllegalArgumentException.class,
                () -> new BankAccount("", "An", 10L));
        assertThrows(IllegalArgumentException.class,
                () -> new BankAccount("A", " ", 10L));
        assertThrows(IllegalArgumentException.class,
                () -> new BankAccount("A", "An", -1L));
    }
}
~~~

There are **10 @Test methods**. Running mvn test should successfully execute all 10 tests in the specified files, with 0 failures and 0 errors.

### Why check the state after a failure?

An incorrect implementation might do this:

~~~java
// Ví dụ cố tình SAI, không dùng thay phương thức transferTo thật:
balanceVnd -= amountVnd;
receiver.deposit(amountVnd);
~~~

If receiver.deposit(...) fails because of long overflow, the sender has already been debited. The transaction is then only partially applied. The correct code **computes the receiver's new balance first, then updates both balances** in one thread.

The overflowFailsWithoutChangingBalances test protects this invariant. However, two assignments are still not atomic under concurrent access or process failure; proper synchronization/transactions and ledger design are required to address those cases.

## 6. OOP reasoning questions based on the exercise

**Can another class assign account.balanceVnd = -5?** No, because the field is private. Other classes must use the public API, where BankAccount enforces its invariants. A balance getter does not grant direct write access.

**Why not declare balanceVnd static?** static would create a class-level field potentially shared by all objects. Each BankAccount needs its own state, so balanceVnd is an instance field.

**Can two variables reference the same object?** Yes:

~~~java
BankAccount first = new BankAccount("A", "An", 100L);
BankAccount alias = first;
alias.deposit(50L);
System.out.println(first.getBalanceVnd()); // 150
~~~

Assigning alias = first copies the **reference**; it does not create a new object. Both variables therefore observe the same balance of 150 VND.

**Why not provide setBalanceVnd?** An unrestricted setter could bypass validation of the source of funds. deposit, withdraw, and transferTo express business operations and enforce preconditions before updating state.

**How can transferTo modify receiver.balanceVnd if the field is private?** In Java, private access is scoped to the class. Code inside BankAccount can access the private fields of any BankAccount instance. Code in BankDemo cannot.

**Are deposits/withdrawals and transfers equally safe?** No. Deposits and withdrawals change one object's state; transfers update two related objects. A multithreaded or distributed system must handle contention and durable transaction state.

## 7. Identifying common mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Declaring balanceVnd public | External code can break invariants | Use private fields and expose business operations |
| Declaring static balanceVnd | All objects share one balance | Use an instance field |
| Withdrawing before checking sufficient funds | Can produce a negative balance or invalid state | Validate before subtracting |
| Failing to reject amount <= 0 | Negative withdrawals can add money | Enforce a positive amount in every operation |
| Using double for money | Binary rounding errors are possible | Use long in the smallest currency unit or BigDecimal |
| Failing to check overflow | long may wrap silently | Use Math.addExact and boundary tests |
| Debiting sender before validating receiver | An exception can leave a partial update | Compute and validate all results before mutation |
| Comparing String with == | Compares references instead of content | Use equals for String value comparisons |
| Testing only the happy path | Negative, overflow, and insufficient-funds cases expose defects | Test invariants and failure paths |
| Treating the simulation as a real bank system | Lacks transactions, concurrency controls, authentication, and auditing | Add dedicated production architecture |

## 8. Extension exercises

### Exercise A — Print account information

Implement summary() to return a String containing the account number, owner name, and balance. Do not let callers modify the balance through the result. Call it from BankDemo to observe the two objects' independent information.

### Exercise B — Transaction history

Add a Transaction type containing the transaction kind, amount, and timestamp. Consider exposing a read-only transaction list with List.copyOf(...) and injecting Clock into the constructor for deterministic time tests. Decide explicitly whether rejected transactions are recorded.

### Exercise C — Two account types

Add SavingsAccount with interest or CheckingAccount with different withdrawal rules. Use inheritance only when there is a genuine is-a relationship that satisfies the contract; for changing interest/fee policies, consider composition via InterestPolicy/FeePolicy interfaces. Do not extend BankAccount merely to inherit its private fields.

### Exercise D — Advanced transfers

Simulate concurrent transfer requests between two accounts and analyze why checking a balance before updating it can introduce race conditions. Propose a stable lock-acquisition order or database transactions; write dedicated concurrency tests once the environment has been designed correctly.

### Exercise E — Separating responsibilities

If the application must find accounts by number and guarantee unique account numbers, should BankAccount contain a global static list? Propose AccountRepository/BankService for account storage and explain why BankAccount should stay focused on its own invariants and behavior.

## 9. Self-assessment checklist

- [ ] Create at least two independent BankAccount objects using new.
- [ ] Identify the class, object, instance field, constructor, and method.
- [ ] Explain how first and alias can reference the same object.
- [ ] Prevent arbitrary balance changes from outside the class.
- [ ] Perform deposit/withdrawal/transfer arithmetic correctly and reject invalid amounts.
- [ ] Preserve all affected balances when a transaction fails in this single-threaded model.
- [ ] Organize the code into valid Java files and run BankDemo and the JUnit tests.
- [ ] Understand the model's limitations regarding concurrency, durability, and auditing.

**Expected outcome:** You have built a class with appropriate account responsibilities, initialized and coordinated objects, controlled data through encapsulation, and verified invariants with tests instead of observing only a single run of main.
