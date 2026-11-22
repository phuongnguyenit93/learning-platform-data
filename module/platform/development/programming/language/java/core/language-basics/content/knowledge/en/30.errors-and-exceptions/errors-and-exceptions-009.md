# Do Not Use `assert` Instead of Mandatory Input Validation — Java 17+

## 1. Core Rule: `assert` Is Not Validation

In Java, an **assertion** is an internal assumption check meant for development and diagnostics. The `assert` statement can be **disabled when the program runs**. Therefore, **do not use `assert` to replace mandatory input validation** in methods, constructors, public APIs, or business logic.

~~~java
// WRONG: condition may not be checked when assertions are disabled.
static void registerAgeWrong(int age) {
    assert age >= 0 : "age must not be negative";
    // Continues processing age even if negative when assertions are off.
}
~~~

~~~java
// RIGHT: mandatory check runs independently of -ea/-da options.
static void registerAge(int age) {
    if (age < 0) {
        throw new IllegalArgumentException("age must not be negative");
    }
    // Processes only after age is valid.
}
~~~

**Deciding question:** must this condition always be checked in the real application, even when assertions are disabled? If **yes**, use an always-on check (`if`, validation API, `Objects.requireNonNull`, etc.) and **never rely only on `assert`**.

## 2. API Contracts Must Work When Assertions Are Disabled

With `-da`, the JVM skips both the condition and the message in `assert` statements, so assertions cannot be relied upon to block bad data. The `-ea` and `-da` flags belong to the **`java` command at runtime**, placed before the `main` class name; they do not alter the application's validation obligations.

The examples below show that `IllegalArgumentException` and `Objects.requireNonNull` behave identically in both modes. Assertion syntax, class/package configuration, and side effects in `assert` expressions were covered in the previous lesson.

## 3. Why Must External Data Validation Be Mandatory?

Input data can arrive from public method arguments, constructors, users, files, networks, or integrated systems. Such data is **not an internal assumption**; it requires a **validity contract** enforced every single time.

Wrong example:

~~~java
static int calculateDiscountWrong(int percent) {
    assert percent >= 0 && percent <= 100;
    return 100 - percent;
}
~~~

When assertions are disabled, `calculateDiscountWrong(150)` still runs and returns `-50`. This is a business bug even though the arithmetic compiles cleanly—not a sign of a correct program.

Correct version:

~~~java
static int calculateDiscount(int percent) {
    if (percent < 0 || percent > 100) {
        throw new IllegalArgumentException("percent must be 0..100");
    }
    return 100 - percent;
}
~~~

Whether the JVM has assertions enabled or disabled:

- `calculateDiscount(20)` returns `80`.
- `calculateDiscount(150)` throws `IllegalArgumentException`.
- Bad input is **never allowed past the check**.

Validation is equally important for constraints not expressed as a single number: non-empty strings, in-range dates, permitted files, account states, non-negative item quantities, valid identifiers, and resource limits.

## 4. Choosing the Right Exception When Validation Fails

| Situation | Typically Appropriate Java Handling |
|---|---|
| Numeric argument outside valid range | `IllegalArgumentException` |
| Required reference argument must be non-null | `Objects.requireNonNull(value, "message")` or intentional `NullPointerException` |
| Empty/blank string argument | Check and throw `IllegalArgumentException` |
| String value cannot be parsed as a number | Handle or propagate `NumberFormatException` per contract |
| Operation cannot be performed in the current state | `IllegalStateException` |
| API declares a checked exception, such as file reading | Catch or declare `throws` per API contract |
| Assumption can fail only due to an **internal** bug | May use `assert` to catch bugs during development, not instead of validation |

~~~java
static String normalizeUser(String username) {
    java.util.Objects.requireNonNull(username, "username is required");
    if (username.isBlank()) {
        throw new IllegalArgumentException("username must not be blank");
    }
    return username.strip();
}
~~~

- `normalizeUser(null)` → throws `NullPointerException` with message `username is required`.
- `normalizeUser("   ")` → throws `IllegalArgumentException` with message `username must not be blank`.
- `normalizeUser(" Lan ")` → returns `"Lan"`.

All three behaviors are **independent of `-ea`**. Using the right exception type also tells callers which boundary validates data, which handles state, and which reports errors to users.

## 5. Reasonable Assertions for Internal Invariants

An **invariant** is something an algorithm must maintain once input data and prior steps have been properly validated. Assertions can help detect internal invariant violations during development:

~~~java
static int roundDownToEven(int value) {
    if (value < 0) {
        throw new IllegalArgumentException("value must not be negative");
    }

    int even = 2 * (value / 2);
    assert even >= 0 : "even must not be negative";
    assert even % 2 == 0 : "even must be divisible by two";
    assert even <= value : "even must not exceed original";
    return even;
}
~~~

Distinguish the two groups of checks:

1. `if (value < 0)` is **mandatory validation** because `value` is a caller-supplied argument.
2. The remaining `assert` statements check **internal results** produced by the code after validation, catching violations of the programmer's assumptions during development.

If `assert` is disabled, the return value is still right according to the designed logic. Conversely, removing the `if` means negative inputs violate the contract even when assertions are enabled on a developer machine.

If application correctness or safety requires checking an invariant in **production**, use an **always-on** check instead of hoping `assert` is enabled.

## 6. Side Effects Must Never Live Inside a Disablable Check

~~~java
int processed = 0;
// Do not write: assert ++processed == 1;
processed++;              // Business operation always runs.
assert processed == 1;   // Only checks internal state.
~~~

`assert operation();` skips **the entire `operation()` call** when assertions are disabled. Never put file writes, permission checks, data mutations, or balance deductions solely inside an assertion expression. The expression after `:` is likewise evaluated only when assertions are enabled **and false**, so it must never be used for mandatory side effects.

## 7. Rejecting Input Differs from Reporting Internal Assumption Failures

`AssertionError` extends `Error`, **not** `Exception`; `catch (Exception)` does not catch it. An assertion failure usually points to an algorithmic invariant bug, not data a user is allowed to enter wrongly.

For nulls or data ranges, use `Objects.requireNonNull`, `IllegalArgumentException`, or `IllegalStateException` per contract semantics; all such checks must work under both `-da` and `-ea`. The runnable program below intentionally catches `AssertionError` **only to demonstrate deterministic stdout**, not as a policy for handling `Error` in production systems.


## 8. Complete Java 17+ Program and Both Run Modes

Save with the exact filename **`AssertVsValidationDemo.java`**:

~~~java
import java.util.Objects;

public final class AssertVsValidationDemo {
    private AssertVsValidationDemo() {}

    static String normalizeUser(String username) {
        Objects.requireNonNull(username, "username is required");
        if (username.isBlank()) {
            throw new IllegalArgumentException("username must not be blank");
        }
        return username.strip();
    }

    static int requirePercent(int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("percent must be 0..100");
        }
        return percent;
    }

    static int roundDownToEven(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("value must not be negative");
        }
        int even = 2 * (value / 2);
        assert even >= 0 : "even must not be negative";
        assert even % 2 == 0 : "even must be divisible by two";
        assert even <= value : "even must not exceed original";
        return even;
    }

    static final class Wallet {
        private int balance;

        Wallet(int openingBalance) {
            if (openingBalance < 0) {
                throw new IllegalArgumentException("opening balance negative");
            }
            this.balance = openingBalance;
        }

        void withdraw(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            if (amount > balance) {
                throw new IllegalStateException("insufficient funds");
            }
            balance -= amount;
            assert balance >= 0 : "internal balance invariant broken";
        }

        int getBalance() {
            return balance;
        }
    }

    // INTENTIONAL BUG: used only to compare -da vs. -ea, never in real code.
    private static int buggyInternalCalculation() {
        int computed = -1;
        assert computed >= 0 : "internal computed negative";
        return computed;
    }

    public static void main(String[] args) {
        System.out.println("assertions enabled="
                + AssertVsValidationDemo.class.desiredAssertionStatus());

        System.out.println("user=" + normalizeUser(" Lan "));
        System.out.println("percent=" + requirePercent(80));

        Wallet wallet = new Wallet(100);
        wallet.withdraw(30);
        System.out.println("balance=" + wallet.getBalance());
        System.out.println("even=" + roundDownToEven(7));

        try {
            normalizeUser(null);
        } catch (NullPointerException ex) {
            System.out.println("null user=" + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
        }

        try {
            normalizeUser("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("blank user=" + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
        }

        try {
            requirePercent(150);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid percent="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        try {
            wallet.withdraw(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid withdraw="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        try {
            wallet.withdraw(100);
        } catch (IllegalStateException ex) {
            System.out.println("insufficient="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        System.out.println("balance after rejection=" + wallet.getBalance());

        // Catching AssertionError is ONLY for this illustrative lesson.
        try {
            System.out.println("buggy internal="
                    + buggyInternalCalculation());
        } catch (AssertionError ex) {
            System.out.println("internal assertion=" + ex.getMessage());
        }

        System.out.println("finished=true");
    }
}
~~~

**Compile once** with JDK 17+, with no Maven/Gradle, external libraries, or preview features required.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 AssertVsValidationDemo.java
java -da -cp . AssertVsValidationDemo
java -ea -cp . AssertVsValidationDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\AssertVsValidationDemo.java
java -da -cp . AssertVsValidationDemo
java -ea -cp . AssertVsValidationDemo
~~~

### Exact stdout with `-da` (assertions disabled)

~~~text
assertions enabled=false
user=Lan
percent=80
balance=70
even=6
null user=NullPointerException:username is required
blank user=IllegalArgumentException:username must not be blank
invalid percent=IllegalArgumentException:percent must be 0..100
invalid withdraw=IllegalArgumentException:amount must be positive
insufficient=IllegalStateException:insufficient funds
balance after rejection=70
buggy internal=-1
finished=true
~~~

### Exact stdout with `-ea` (assertions enabled)

~~~text
assertions enabled=true
user=Lan
percent=80
balance=70
even=6
null user=NullPointerException:username is required
blank user=IllegalArgumentException:username must not be blank
invalid percent=IllegalArgumentException:percent must be 0..100
invalid withdraw=IllegalArgumentException:amount must be positive
insufficient=IllegalStateException:insufficient funds
balance after rejection=70
internal assertion=internal computed negative
finished=true
~~~

**Output analysis:**

1. `assertions enabled=...` reports the assertion status of **the demo class itself**.
2. Valid user and percentage inputs work normally. After withdrawing 30 from a wallet holding 100, the balance is 70.
3. `null` input, whitespace-only string, percentage `150`, withdrawal of `0`, and withdrawal exceeding balance **are all rejected identically** in both modes.
4. `roundDownToEven(7)` returns 6; all internal `assert` checks pass when enabled.
5. `buggyInternalCalculation()` has an intentional assumption bug. Under `-da`, the `assert` statement checks nothing and returns `-1`; under `-ea`, it throws `AssertionError` and the demo branch prints the message.
6. **Key takeaway:** mandatory validation does not change between `-da` and `-ea`; only internal diagnostic assertion checks depend on this flag.

## 9. Writing Proper Tests for APIs

If a method declares that it only accepts `percent` in `0..100`, test both valid data and invalid data **even when assertions are disabled**.

Conceptual test example, independent of any framework:

~~~java
int accepted = requirePercent(50);     // Must be 50.
try {
    requirePercent(150);
    throw new IllegalStateException("expected validation to reject input");
} catch (IllegalArgumentException expected) {
    // Invalid value was rejected per contract.
}
~~~

Note that this is **illustrative code** using `requirePercent` from section 8; real tests should reside in an appropriate test class/access scope and use test framework assertions or a proper test harness. When testing exceptions, do not rely solely on the language's `assert` statement that gets disabled at runtime.

In JUnit, test methods like `assertThrows` from the test library are not equivalent to the Java `assert` statement. They execute through the test library's mechanisms and are not turned into `assert` statements skipped under `-da`.

**Test in both modes:** the same validation suite must pass when run with `-da` and `-ea`. Depending on policy, use `-ea` during development/testing to catch internal bugs early, while ensuring API correctness never depends on deployers enabling that flag.

## 10. When Can `assert` Be Used?

Appropriate places (only for **internal** assumptions unaffected by untrusted, unvalidated data):

- Checking intermediate results after a transformation whose invariant the algorithm guarantees.
- Marking internal branches designed to be unreachable under proven conditions.
- Verifying postconditions once processing finishes when correctness is already ensured independently of assertions.
- Helping detect programming errors when running dev/test environments with `-ea` enabled.

Conversely, **do not use `assert`** as the sole mechanism to:

- Validate inputs of public methods, REST handlers, constructors, or CLI arguments.
- Check null/blank/data bounds that must hold in production.
- Enforce access control, authentication, or transaction safety.
- Check mandatory state (such as sufficient balance for withdrawal).
- Perform side-effecting work, call APIs, mutate objects, or grant permissions.

Never try to "fix" a missing business check by forcing users to run the application with `-ea`. **The validation code itself must always execute.**

## 11. Common Mistakes

| Mistake | Risk | Fix |
|---|---|---|
| `assert age >= 0;` as the sole input check | Negative values slip through when assertions are off | `if (age < 0) throw new IllegalArgumentException(...)` |
| `assert username != null;` in a public API | Null callers are not rejected when disabled | `Objects.requireNonNull(username, ...)` |
| Assuming `-ea` is always on in production | The JVM may run with assertions disabled by default | Make validation independent of assertion flags |
| `assert ++counter > 0;` | When disabled, `counter` does not increment | Separate mandatory operations from assertions |
| `assert authorize(user);` | When disabled, permission checks are skipped | Call mandatory authorization logic and check results with regular conditions |
| Catching `Exception` expecting to handle `AssertionError` | `AssertionError` does not extend `Exception` | Fix internal bugs; do not use `Error` for validation |
| Writing `assert condition : logAndReturn();` | Detail also does not run when disabled or when condition is true | Do not rely on side effects in `assert` |
| Using `assert` to signal "insufficient funds" | That is an expected business state | Check and throw `IllegalStateException` or return a contract result |
| Writing validation tests that only run under `-ea` | Does not prove safety when disabled | Run tests under both `-da` and `-ea` |
| Catching validation failures with `catch (AssertionError)` | Turns input errors into an off-contract `Error` | Throw an input exception with clear type and message |
| Thinking `assert` runs at compile time | The assertion statement is syntax-checked at compile time, while the condition is evaluated at runtime if enabled | Distinguish compiler checks from runtime assertions |
| Using one `assert` for every abnormal issue | Obscures error types and does not guarantee checking | Separate input, state, and internal invariants and use the right mechanism |

## 12. Exercises with Answers

**A — Spotting a design flaw.** Given the method:

~~~java
static double divide(double a, double b) {
    assert b != 0;
    return a / b;
}
~~~

If the contract requires **rejecting a zero divisor** at all times, is the snippet above sufficient?

**Answer:** No. When assertions are disabled, with floating-point `double`, dividing by 0 can produce `Infinity` or `NaN` instead of being rejected. Add:

~~~java
if (b == 0.0) {
    throw new IllegalArgumentException("divisor must not be zero");
}
~~~

**B — Enabling/disabling assertions.** Which command enables assertions for the example class?

**Answer:** `java -ea -cp . AssertVsValidationDemo`. To disable explicitly: `java -da -cp . AssertVsValidationDemo`.

**C — Why is `assert ++count > 0;` dangerous?**

**Answer:** Under `-da`, the condition expression is not evaluated, so `count` **does not increment**. Never place mandatory data updates inside an assertion.

**D — Error category.** Is `AssertionError` under `Exception` or `Error`?

**Answer:** Under `Error`; `catch (Exception)` does not catch `AssertionError`.

**E — Classifying conditions.** `user != null` on a public API and `computed >= 0` after an algorithm has validated input values: which condition must be validation?

**Answer:** `user != null` is **mandatory validation**; `computed >= 0` can be an internal assertion if it is an invariant guaranteed by the algorithm and skipping the assert does not break production behavior.

**F — Comparing two runs.** What happens to `requirePercent(150)` under `-da` and `-ea`?

**Answer:** Both throw `IllegalArgumentException`. Only `buggyInternalCalculation()` shows a difference due to its assertion statement.

## 13. Checklist and Conclusion

- [ ] Understand that `assert` checks internal assumptions and can be disabled at runtime.
- [ ] Know `assert condition;` and `assert condition : detail;`.
- [ ] Know that `-ea` enables and `-da` disables application assertions per JVM configuration.
- [ ] Never use `assert` instead of mandatory input data validation.
- [ ] Use `if`, `throw IllegalArgumentException`, and `Objects.requireNonNull` appropriately per contract.
- [ ] Use `IllegalStateException` for invalid-state operations when appropriate.
- [ ] Know that `AssertionError` belongs to the `Error` branch, not ordinary input exceptions.
- [ ] Never place side effects, authorization, or data mutations inside assertion expressions.
- [ ] Distinguish between internal invariants and external input constraints.
- [ ] Test validation even under `-da`.
- [ ] Run `AssertVsValidationDemo.java` on JDK 17+ with both `-da` and `-ea` and compare both stdout outputs.

**Conclusion:** `assert` helps detect **internal assumption bugs** when enabled, but **is not guaranteed to execute on every run**. Any input condition or business rule that must be enforced requires **always-on validation** that throws exceptions or returns results per the API contract—never rely solely on `assert`.