# Building an Account Class with Creation, Deposit, and Withdrawal — Java 17+

This hands-on exercise builds a `BankAccount` class that can **create a new account**, **deposit money**, **withdraw money**, and **view the balance**. This is an object-oriented exercise on **data encapsulation**, **constructors**, **instance methods**, **invariants**, **exception handling**, and **testing**, not a production banking application.

Rules of the example:

- Each account has a non-empty account number and owner name that do not change after initialization.
- Each account has its own balance, stored as a `long` in **cents** for a hypothetical currency with two decimal places.
- The initial balance must not be negative; an account can be opened with a balance of 0.
- Deposits and withdrawals must have a positive amount.
- Withdrawals must not exceed the balance.
- Prevent overflow when adding money.
- If an operation fails, the balance must remain unchanged.
- There is no public setter for the balance; it can only be modified through validated business operations.

**Environment:** Java 17+. The examples include filenames, compile/run commands, and expected stdout. Every program that uses the main BankAccount class is compiled together with the `BankAccount.java` file presented in section 5. Standalone examples are clearly noted.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify the data fields and behaviors of an account.
2. Write a constructor that guards input data.
3. Use `private`, `final`, `this`, and methods with proper semantics.
4. Write `deposit`/`withdraw` and maintain the `balance >= 0` invariant.
5. Distinguish between invalid amount, insufficient funds, and overflow errors.
6. Understand exception safety: validate first, update later.
7. Know why `double` should not be used arbitrarily to store money.
8. Test success, boundary, and failure cases.
9. Distinguish between two separate accounts and two references to the same account.
10. Understand the level of protection provided by `synchronized` and its limitations.
11. Identify additional requirements for real-world applications, such as ledgers, persistence, and transfer transactions.

## 2. Analyzing Requirements into a Class

Suppose we have the user story: “I want to open an account with an account number, name, and opening balance; deposit an additional amount, withdraw an amount when funds are sufficient, and look up the remaining balance.”

| Requirement | Component | Condition |
| --- | --- | --- |
| Account number | `accountNumber` | Not null/blank |
| Owner | `ownerName` | Not null/blank |
| Balance | `balanceCents` | Non-negative |
| Open account | Constructor | Validate all inputs |
| Deposit | `deposit(amount)` | Amount > 0, no overflow |
| Withdraw | `withdraw(amount)` | Amount > 0 and amount <= balance |
| Read balance | `balanceCents()` | Does not modify state |
| Display | `balanceText()` | Format cents as a decimal string |

Definition of a class **invariant**: the conditions that every successfully constructed object and every valid public operation must preserve. Here, an account has no blank name/number, and its balance is non-negative.

## 3. Why Use a Class and Encapsulate Fields?

If you only declare:

~~~java
String id = "ACC-001";
String name = "Mai";
long balance = 10_000;
~~~

callers could write `balance = -500` without going through validation.

A class with private fields and methods expressing business operations:

~~~java
class BankAccount {
    private long balanceCents;

    void deposit(long cents) {
        // validate before adding
    }

    void withdraw(long cents) {
        // validate before subtracting
    }
}
~~~

This is **encapsulation**: the object owns its balance and is the sole place controlling changes to it. Do not expose `public long balance` and do not create an arbitrary `setBalance`.

The account number and owner name are used as immutable metadata in this lesson, so those fields are `private final`. The balance must change according to business operations, so it is private but not final.

## 4. Why Does the Example Store Money as `long` Cents?

`double` represents numbers in binary, so it cannot preserve every decimal value accurately. For example, `0.1 + 0.2` can become `0.30000000000000004`.

For a currency with two decimal places, storing in cents:
- 100.00 → 10,000 cents.
- 12.50 → 1,250 cents.
- 4.00 → 400 cents.

Integer addition/subtraction is exact **within its value range**, though `long` can still overflow. `Math.addExact` helps detect overflow instead of silently wrapping around.

**Note:** This is a convention for this lesson and does not apply to all currencies with different numbers of decimal places. For a real-world domain, currency/scale/rounding policies are needed; `BigDecimal` is a suitable option for decimal operations.

## 5. Complete Class: `BankAccount.java`

Create the file **`BankAccount.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class BankAccount {
    private final String accountNumber;
    private final String ownerName;
    private long balanceCents;

    public BankAccount(
            String accountNumber,
            String ownerName,
            long openingCents) {
        this.accountNumber =
                requiredText(accountNumber, "accountNumber");
        this.ownerName =
                requiredText(ownerName, "ownerName");

        if (openingCents < 0) {
            throw new IllegalArgumentException(
                    "openingCents must not be negative");
        }
        this.balanceCents = openingCents;
    }

    private static String requiredText(
            String value, String field) {
        Objects.requireNonNull(value, field);
        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
        return normalized;
    }

    private static void requirePositive(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException(
                    "amountCents must be positive");
        }
    }

    public String accountNumber() {
        return accountNumber;
    }

    public String ownerName() {
        return ownerName;
    }

    public synchronized long balanceCents() {
        return balanceCents;
    }

    public synchronized String balanceText() {
        return BigDecimal.valueOf(balanceCents, 2)
                .toPlainString();
    }

    public synchronized void deposit(long amountCents) {
        requirePositive(amountCents);
        long next = Math.addExact(
                balanceCents, amountCents);
        balanceCents = next;
    }

    public synchronized void withdraw(long amountCents) {
        requirePositive(amountCents);
        if (amountCents > balanceCents) {
            throw new InsufficientFundsException(
                    "insufficient funds");
        }
        balanceCents -= amountCents;
    }

    public static final class InsufficientFundsException
            extends RuntimeException {
        public InsufficientFundsException(String message) {
            super(message);
        }
    }
}
~~~

### Why Does This Implementation Preserve the Invariant?

- `accountNumber` and `ownerName` are validated before assignment; `strip` removes leading and trailing whitespace.
- `openingCents < 0` throws an exception; no successfully constructed instance is returned with a negative balance.
- `balanceCents` is a private field, so callers cannot bypass deposit/withdraw.
- `deposit` checks that the amount is positive, computes `next` using `Math.addExact`, and **only then assigns the field**.
- `withdraw` checks that the amount is positive and that funds are sufficient **before subtracting**.
- `synchronized` serializes calls that read/write the balance on the same instance when all access goes through these methods.
- The insufficient-funds exception is categorized separately so callers can catch the specific business error.

`BigDecimal.valueOf(balanceCents, 2).toPlainString()` is used only for display; the stored state remains long cents.

## 6. Runnable Program: Opening an Account, Depositing, and Withdrawing

Create **`AccountDemo.java`**:

~~~java
public class AccountDemo {
    public static void main(String[] args) {
        BankAccount account = new BankAccount(
                " ACC-001 ", " Mai ", 10_000);

        System.out.println("account=" +
                account.accountNumber());
        System.out.println("owner=" +
                account.ownerName());
        System.out.println("opening=" +
                account.balanceText());

        account.deposit(1_250);
        System.out.println("after deposit=" +
                account.balanceText());

        account.withdraw(400);
        System.out.println("after withdraw=" +
                account.balanceText());

        try {
            account.withdraw(99_999);
        } catch (BankAccount.InsufficientFundsException ex) {
            System.out.println("error=" + ex.getMessage());
        }

        System.out.println("remaining=" +
                account.balanceText());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java AccountDemo.java
java AccountDemo
~~~

Stdout:

~~~text
account=ACC-001
owner=Mai
opening=100.00
after deposit=112.50
after withdraw=108.50
error=insufficient funds
remaining=108.50
~~~

Calculation: 10,000 + 1,250 - 400 = 10,850 cents, corresponding to 108.50. The withdrawal of 99,999 cents is rejected **before modifying the balance**, so the balance remains unchanged.

## 7. Constructor and the `this` Keyword

A constructor has the same name as the class and **no return type**:

~~~java
public BankAccount(
        String accountNumber,
        String ownerName,
        long openingCents) {
    // ...
}
~~~

`this.accountNumber` is the field of the current object; `accountNumber` in the argument to `requiredText` is the parameter with the same name.

At the call site:

~~~java
BankAccount account =
        new BankAccount("A", "An", 0);
~~~

If the constructor completes normally, `new` returns a reference to a valid account. If the constructor throws an exception, the expression does not return a successfully created account to assign to the caller.

Do not publish `this` to a global registry before validation completes: other code could observe a partially initialized state. Do not use a static balance because a static field would be shared across all instances.

## 8. Runnable Program: Constructor Rejects Invalid Inputs

Create **`AccountCreationErrorsDemo.java`**:

~~~java
public class AccountCreationErrorsDemo {
    public static void main(String[] args) {
        try {
            new BankAccount("   ", "Mai", 100);
        } catch (IllegalArgumentException ex) {
            System.out.println("blank id rejected");
        }

        try {
            new BankAccount("A", "Mai", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative opening rejected");
        }

        try {
            new BankAccount("A", null, 0);
        } catch (NullPointerException ex) {
            System.out.println("null owner rejected");
        }

        BankAccount valid =
                new BankAccount("A", "Mai", 0);
        System.out.println("balance=" +
                valid.balanceCents());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java AccountCreationErrorsDemo.java
java AccountCreationErrorsDemo
~~~

Stdout:

~~~text
blank id rejected
negative opening rejected
null owner rejected
balance=0
~~~

The null policy and blank policy differ: `Objects.requireNonNull` throws NullPointerException, while `strip().isEmpty()` detects blank input and throws IllegalArgumentException.

## 9. Deposit: Validate First, Add Later

In the main class:

~~~java
public synchronized void deposit(long amountCents) {
    requirePositive(amountCents);
    long next = Math.addExact(balanceCents, amountCents);
    balanceCents = next;
}
~~~

Three things to remember:
1. The amount must be positive.
2. The addition must be representable as a `long`.
3. Only assign state after both conditions are satisfied.

Do not use `deposit(-100)` in place of withdrawing money, because doing so bypasses the insufficient-funds check in `withdraw`.

## 10. Runnable Program: Invalid Deposit and Overflow

Create **`DepositFailuresDemo.java`**:

~~~java
public class DepositFailuresDemo {
    public static void main(String[] args) {
        BankAccount account =
                new BankAccount("A", "Mai", 1_000);

        try {
            account.deposit(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("zero rejected");
        }

        try {
            account.deposit(-20);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative rejected");
        }

        System.out.println("unchanged=" +
                account.balanceCents());

        BankAccount max = new BankAccount(
                "MAX", "Mai", Long.MAX_VALUE);
        try {
            max.deposit(1);
        } catch (ArithmeticException ex) {
            System.out.println("overflow rejected");
        }
        System.out.println("max unchanged=" +
                (max.balanceCents() == Long.MAX_VALUE));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java DepositFailuresDemo.java
java DepositFailuresDemo
~~~

Stdout:

~~~text
zero rejected
negative rejected
unchanged=1000
overflow rejected
max unchanged=true
~~~

`Math.addExact` throws ArithmeticException before the assignment. Regular addition with long can overflow and wrap around, so it is not enough to protect money.

## 11. Withdraw: Check Sufficient Funds Before Subtracting

In the main class:

~~~java
public synchronized void withdraw(long amountCents) {
    requirePositive(amountCents);
    if (amountCents > balanceCents) {
        throw new InsufficientFundsException(
                "insufficient funds");
    }
    balanceCents -= amountCents;
}
~~~

If the balance is non-negative, the amount is positive, and amount <= balance, the subtraction produces a non-negative balance. **Withdrawing the exact full balance** is allowed, bringing the balance to 0.

Incorrect:

~~~java
// balanceCents -= amountCents;
// if (balanceCents < 0) {
//     throw new IllegalArgumentException("insufficient");
// }
~~~

Because the state is modified **before throwing**, leaving the object in an invalid state if it is not rolled back properly.

## 12. Runnable Program: Full Withdrawal and Insufficient Funds Error

Create **`WithdrawFailuresDemo.java`**:

~~~java
public class WithdrawFailuresDemo {
    public static void main(String[] args) {
        BankAccount account =
                new BankAccount("A", "Mai", 500);

        account.withdraw(500);
        System.out.println("after full withdraw=" +
                account.balanceCents());

        try {
            account.withdraw(1);
        } catch (BankAccount.InsufficientFundsException ex) {
            System.out.println("insufficient");
        }

        try {
            account.withdraw(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative rejected");
        }

        System.out.println("final=" +
                account.balanceCents());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java WithdrawFailuresDemo.java
java WithdrawFailuresDemo
~~~

Stdout:

~~~text
after full withdraw=0
insufficient
negative rejected
final=0
~~~

All failures occur before the subtraction. That is the **exception safety** that the class preserves.

## 13. Exceptions and Caller Error Handling

| Condition | Error in Design |
| --- | --- |
| Null account number/owner | `NullPointerException` |
| Blank account number/owner | `IllegalArgumentException` |
| Negative opening balance | `IllegalArgumentException` |
| Deposit/withdraw <=0 | `IllegalArgumentException` |
| Withdraw exceeds balance | `InsufficientFundsException` |
| Deposit overflow | `ArithmeticException` |

A custom exception helps distinguish **invalid input** from **insufficient funds**:

~~~java
try {
    account.withdraw(amountCents);
    System.out.println("withdraw successful");
} catch (BankAccount.InsufficientFundsException ex) {
    System.out.println("not enough balance");
} catch (IllegalArgumentException ex) {
    System.out.println("invalid amount");
}
~~~

This is a snippet for a caller/controller, not a standalone runnable program.

Exception messages are for diagnostics; do not parse message text as a protocol. In real systems, use error codes or structured responses and do not write sensitive data to logs.

## 14. “Validate First, Commit Later” Is an Important Habit

We separate:
- **Check:** Is the input valid?
- **Compute:** Is the candidate balance representable?
- **Commit:** Assign the new state once after the checks.

For deposit:
- Check for a positive amount.
- Compute using Math.addExact; if it fails, do not mutate yet.
- Assign balance.

For withdraw:
- Check for a positive amount.
- Check for sufficient funds.
- Subtract from balance.

If a public method fails, the balance remains unchanged; that is the contract of the current version.

If transaction history or database writes are added later, a single assignment is no longer sufficient. Updating the balance and the ledger requires a separate transaction boundary.

## 15. Test Suite Without External Libraries

Create **`BankAccountTest.java`**:

~~~java
public class BankAccountTest {
    private static int checks;

    static void check(boolean ok, String label) {
        checks++;
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void expect(
            Class<? extends Throwable> type,
            Runnable action) {
        checks++;
        try {
            action.run();
        } catch (Throwable caught) {
            if (type.isInstance(caught)) {
                return;
            }
            throw new AssertionError(
                    "unexpected exception: " + caught, caught);
        }
        throw new AssertionError(
                "missing " + type.getSimpleName());
    }

    public static void main(String[] args) {
        BankAccount a =
                new BankAccount(" A ", " Mai ", 1_000);

        check(a.accountNumber().equals("A"), "number");
        check(a.ownerName().equals("Mai"), "owner");
        check(a.balanceCents() == 1_000, "opening");

        a.deposit(250);
        check(a.balanceCents() == 1_250, "deposit");

        a.withdraw(200);
        check(a.balanceCents() == 1_050, "withdraw");

        expect(IllegalArgumentException.class,
                () -> a.deposit(0));
        expect(IllegalArgumentException.class,
                () -> a.withdraw(-1));
        expect(BankAccount.InsufficientFundsException.class,
                () -> a.withdraw(2_000));
        check(a.balanceCents() == 1_050,
                "unchanged on failures");

        expect(IllegalArgumentException.class,
                () -> new BankAccount(" ", "Mai", 0));
        expect(NullPointerException.class,
                () -> new BankAccount("A", null, 0));
        expect(IllegalArgumentException.class,
                () -> new BankAccount("A", "Mai", -1));

        BankAccount max =
                new BankAccount("MAX", "Mai", Long.MAX_VALUE);
        expect(ArithmeticException.class,
                () -> max.deposit(1));
        check(max.balanceCents() == Long.MAX_VALUE,
                "unchanged on overflow");

        BankAccount empty =
                new BankAccount("EMPTY", "An", 500);
        empty.withdraw(500);
        check(empty.balanceCents() == 0, "withdraw all");

        System.out.println("PASS " + checks + " checks");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java BankAccountTest.java
java BankAccountTest
~~~

Stdout:

~~~text
PASS 15 checks
~~~

Count breakdown: 3 initial checks + 1 deposit + 1 withdrawal + 3 expected failures + 1 unchanged + 3 invalid constructors + 1 expected overflow + 1 overflow unchanged + 1 withdraw all = 15.

Catching `Throwable` in the helper is an approach limited to a **test harness** in order to report an exception different from what was expected. In production, avoid catching Throwable indiscriminately because it also includes `Error`.

## 16. Boundary Cases to Test

| Test Case | Expected Result |
| --- | --- |
| Opening = 0 | Account created successfully |
| Opening = -1 | Reject |
| Number = blank | Reject |
| Owner = null | Reject |
| Deposit = 1 | Increase by 1 cent |
| Deposit = 0 or negative | Reject and keep balance |
| Deposit causing overflow | Reject and keep balance |
| Withdraw = 1 when sufficient | Decrease by 1 cent |
| Withdraw = balance | Balance becomes 0 |
| Withdraw > balance | Insufficient funds, balance unchanged |
| Withdraw = 0 or negative | Reject |
| Two account objects | Separate balances |
| Two aliases to the same object | Both see the same balance |

Do not test only the happy path. A class that retains an incorrect balance after a rejected operation is a serious bug even if normal additions and subtractions work correctly.

## 17. Object Identity and Reference Aliases

~~~java
BankAccount first =
        new BankAccount("A", "Mai", 100);
BankAccount alias = first;
BankAccount second =
        new BankAccount("A", "Mai", 100);
~~~

- `first == alias` → true, because they refer to the same instance.
- `first == second` → false, because there are two separate `new` expressions.
- Depositing via `alias` changes the state observed by `first`.
- `second` does not change.

### Runnable Program

Create **`AccountIdentityDemo.java`**:

~~~java
public class AccountIdentityDemo {
    public static void main(String[] args) {
        BankAccount first =
                new BankAccount("A", "Mai", 100);
        BankAccount alias = first;
        BankAccount second =
                new BankAccount("A", "Mai", 100);

        alias.deposit(50);

        System.out.println("alias=" + (first == alias));
        System.out.println("same as second=" +
                (first == second));
        System.out.println("first=" + first.balanceCents());
        System.out.println("second=" + second.balanceCents());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java AccountIdentityDemo.java
java AccountIdentityDemo
~~~

Stdout:

~~~text
alias=true
same as second=false
first=150
second=100
~~~

An account is an object with identity; you should not automatically override equals based solely on balance. Two accounts with the same balance do not mean they are the same entity.

## 18. Concurrency: Why Use `synchronized`

Depositing involves multiple read-modify-write steps. If two threads read the old balance and both compute/assign the new balance without synchronization, **an update can be lost**.

The synchronized methods of BankAccount use the monitor belonging to **each instance**:
- One thread executes deposit/withdraw at a time on the same account.
- The synchronized balance getter sees the state protected by that monitor.
- It does not prevent threads from operating on different accounts.
- It does not solve transactions involving multiple accounts.

### Runnable Program with Four Workers

Create **`ConcurrentDepositsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConcurrentDepositsDemo {
    public static void main(String[] args) throws Exception {
        BankAccount account =
                new BankAccount("A", "Mai", 0);
        ExecutorService pool =
                Executors.newFixedThreadPool(4);
        List<Future<?>> jobs = new ArrayList<>();

        try {
            for (int worker = 0; worker < 4; worker++) {
                jobs.add(pool.submit(() -> {
                    for (int i = 0; i < 1_000; i++) {
                        account.deposit(1);
                    }
                }));
            }

            for (Future<?> job : jobs) {
                job.get();
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("cents=" +
                account.balanceCents());
        System.out.println("money=" +
                account.balanceText());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java ConcurrentDepositsDemo.java
java ConcurrentDepositsDemo
~~~

Stdout:

~~~text
cents=4000
money=40.00
~~~

4 workers × 1,000 deposits × 1 cent = 4,000 cents. `Future.get()` waits for tasks to complete and throws an exception if a task fails.

## 19. Reading Then Withdrawing Is Not an Atomic Transaction

Example:

~~~java
if (account.balanceCents() >= 500) {
    account.withdraw(500);
}
~~~

The two method calls are **two separate critical sections**. Another thread could withdraw after the getter but before withdraw; in that case, withdraw still performs its own check and throws InsufficientFundsException.

**Proper design:** the caller invokes withdraw and catches the error; do not assume check-then-act outside the account is atomic.

Similarly:

~~~java
from.withdraw(amount);
to.deposit(amount);
~~~

is not a safe transfer transaction. If the credit fails after the debit, the two balances become inconsistent. A real transfer requires transaction semantics, lock ordering, and rollback/persistence/recovery, which is outside the scope of this single-account creation/deposit/withdrawal lesson.

## 20. Safely Parsing Money Strings into Cents

The main version uses long cents to make the unit explicit. The UI might receive `"12.50"`, then parse it using BigDecimal and convert to cents:

Create **`MoneyInputDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyInputDemo {
    static long toCents(String input) {
        return new BigDecimal(input.strip())
                .setScale(2, RoundingMode.UNNECESSARY)
                .movePointRight(2)
                .longValueExact();
    }

    public static void main(String[] args) {
        BankAccount account =
                new BankAccount("A", "Mai", 0);
        account.deposit(toCents("12.50"));
        account.withdraw(toCents("2.25"));

        System.out.println("balance=" +
                account.balanceText());

        try {
            toCents("0.001");
        } catch (ArithmeticException ex) {
            System.out.println("fraction rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java MoneyInputDemo.java
java MoneyInputDemo
~~~

Stdout:

~~~text
balance=10.25
fraction rejected
~~~

`setScale(2, RoundingMode.UNNECESSARY)` rejects inputs when rounding would be required; `longValueExact` rejects non-integral or overflow conversions. The controller must also handle null, NumberFormatException, and locale/currency policies.

## 21. BigDecimal as State: Another Option

When decimal arithmetic is needed, `BigDecimal` can be stored, provided scale/rounding rules are defined. BigDecimal is immutable: `add`/`subtract` return a new object.

Create **`DecimalAccountDemo.java`**, a standalone program that does not need BankAccount.java:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class DecimalAccountDemo {
    static final class Account {
        private BigDecimal balance;

        Account(BigDecimal opening) {
            balance = normalized(opening);
            if (balance.signum() < 0) {
                throw new IllegalArgumentException("opening");
            }
        }

        private static BigDecimal normalized(BigDecimal raw) {
            Objects.requireNonNull(raw, "raw");
            try {
                return raw.setScale(2, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException("fraction", ex);
            }
        }

        void deposit(BigDecimal raw) {
            BigDecimal amount = normalized(raw);
            if (amount.signum() <= 0) {
                throw new IllegalArgumentException("amount");
            }
            balance = balance.add(amount);
        }

        void withdraw(BigDecimal raw) {
            BigDecimal amount = normalized(raw);
            if (amount.signum() <= 0) {
                throw new IllegalArgumentException("amount");
            }
            if (amount.compareTo(balance) > 0) {
                throw new IllegalArgumentException("insufficient");
            }
            balance = balance.subtract(amount);
        }

        BigDecimal balance() {
            return balance;
        }
    }

    public static void main(String[] args) {
        Account account =
                new Account(new BigDecimal("100.00"));
        account.deposit(new BigDecimal("12.50"));
        account.withdraw(new BigDecimal("2.25"));

        System.out.println(account.balance().toPlainString());

        try {
            account.deposit(new BigDecimal("0.001"));
        } catch (IllegalArgumentException ex) {
            System.out.println("fraction rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DecimalAccountDemo.java
java DecimalAccountDemo
~~~

Stdout:

~~~text
110.25
fraction rejected
~~~

The example uses two decimal places and a single thread. Do not use `new BigDecimal(0.1)` for literal decimal input if you want exact string representation; prefer `new BigDecimal("0.1")`.

## 22. Extensions Not to Rush Into

A real-world account class typically needs:
- Specific currency and minor unit rules.
- Transaction history/ledger and audit events.
- ID uniqueness and persistence identity.
- Authorization for deposit/withdraw.
- Limits and business policies.
- Database transactions, optimistic locking, and idempotency.
- Transfers with atomic debit/credit and recovery.
- Error messages/localization, and privacy/logging.
- Multithreaded testing, persistence testing, and failure testing.

If a history list is added directly to BankAccount, an operation must update **both the balance and history** consistently; if appending to history fails after the balance changes, a transaction/rollback strategy is required. Therefore, this lesson keeps the scope strictly to **in-memory creation/deposit/withdrawal**.

## 23. Anti-Patterns and How to Fix Them

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| `public long balance` | Bypasses checks | Private field |
| `static long balance` | Shared balance across accounts | Instance field |
| Public `setBalance` | Callers modify arbitrarily | Domain methods |
| Constructor allows negative opening | Invalid object | Validate in constructor |
| Depositing negative amount | Bypasses withdrawal rule | Reject |
| Subtracting before checking | Negative state when throwing | Check first |
| Not checking overflow | Arithmetic wrap | Math.addExact |
| Using double for money | Decimal precision issue | Long cents/BigDecimal |
| Catching all exceptions and ignoring | Hides errors | Catch specifically |
| Using balance to define entity equals | Wrong identity | Choose an ID/reference policy |
| Assuming synchronized suffices for transfer | Partial failure | Transaction boundary |
| Not testing invalid inputs | Invariant bug | Negative tests |
| Printing sensitive data to logs | Privacy risk | Logging policy |

## 24. Exercises with Answers

**Exercise 1.** Open with 20,000 cents, deposit 5,000, withdraw 3,000. What is the balance? **Answer:** 22,000 cents = 220.00.

**Exercise 2.** Open with 500, withdraw 501. What happens? **Answer:** InsufficientFundsException, and the balance remains 500.

**Exercise 3.** Does `deposit(0)` change the balance? **Answer:** No; IllegalArgumentException.

**Exercise 4.** Open with Long.MAX_VALUE, then `deposit(1)`? **Answer:** ArithmeticException, state unchanged.

**Exercise 5.** Create a and b using two `new BankAccount` calls with the same data. Is `a == b`? **Answer:** False.

**Exercise 6.** With `BankAccount alias = a; alias.deposit(100);`, what happens to `a.balanceCents()`? **Answer:** Increases by 100 because it is the same object.

**Exercise 7.** Why is `private static long balance` wrong? **Answer:** Static state belongs to the class, not separately to each instance.

**Exercise 8.** Why must the constructor validate the opening balance? **Answer:** To prevent an invalid object from being successfully created.

**Exercise 9.** `withdraw(balance)`? **Answer:** Valid if balance>0; afterwards it equals 0.

**Exercise 10.** Why is `from.withdraw(x); to.deposit(x)` not a safe transfer? **Answer:** The credit step can fail after the debit, lacking atomicity/rollback.

**Exercise 11.** Why is `double` unsuitable for exact decimal money? **Answer:** It cannot represent every decimal fraction accurately.

**Exercise 12.** If calling the getter shows sufficient funds and another thread withdraws first, what should the withdraw method do? **Answer:** Re-check under the lock itself and throw if funds are insufficient.

## 25. Workflow to Complete the Exercise

1. Identify fields and invariants.
2. Write a constructor that checks for null, blank, and negative opening balance.
3. Use private fields and necessary getters.
4. Do not expose a setter for the balance.
5. Write `deposit`: positive-check → Math.addExact → assignment.
6. Write `withdraw`: positive-check → sufficient-check → subtraction.
7. Declare a dedicated exception for insufficient funds.
8. Write main to create an account, deposit/withdraw, and print the balance.
9. Test happy paths, zero/negative amounts, insufficient funds, and overflow.
10. Ensure state remains unchanged after an exception.
11. Consider synchronization for the same account instance.
12. Separate UI parsing from the domain class.
13. Design ledger/persistence/transfer at a higher architectural layer when needed.

## 26. End-of-Lesson Checklist

- [ ] I can create `BankAccount` using a constructor.
- [ ] I use `private` for state and `final` for fixed fields.
- [ ] I understand how `this.field` differs from a parameter with the same name.
- [ ] I do not use a static balance.
- [ ] I reject null/blank account numbers and owners.
- [ ] I reject a negative opening balance.
- [ ] I do not publicly expose setBalance.
- [ ] I understand the balance>=0 invariant.
- [ ] I write deposit as positive-only.
- [ ] I use Math.addExact to prevent overflow.
- [ ] I write withdraw as positive-only and with a sufficient-balance check.
- [ ] I allow withdrawing the entire balance.
- [ ] I have a dedicated exception for insufficient funds.
- [ ] I do not mutate the balance before validation.
- [ ] I test that state remains unchanged when a method fails.
- [ ] I understand long cents applies only to the chosen currency scale.
- [ ] I know BigDecimal from String and RoundingMode.UNNECESSARY.
- [ ] I can run AccountDemo and BankAccountTest.
- [ ] I distinguish an alias reference from a new object.
- [ ] I know synchronized does not automatically make transfers atomic.
- [ ] I separate business logic from input parsing/presentation.
- [ ] I know this model cannot yet replace a production banking ledger.

**Conclusion:** The account class is a classic example of the principle of **encapsulating state and enforcing invariants at update points**. The constructor ensures the account starts valid; `deposit` and `withdraw` are controlled behaviors; exceptions do not corrupt state; and tests verify both successes and failures. On Java 17+, combining **private fields, validation, checked arithmetic, exception handling, and purposeful synchronization** yields an in-memory account model that is clear, extensible, and easy to test.
