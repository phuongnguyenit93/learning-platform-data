# Writing Tests for Initialization, Updates, Boundary Cases, and Invalid Input — Java 17+

## Objectives

This lesson belongs to the **Design and Practice** topic of core Java. After completing it, you will be able to:

- Identify **valid inputs, initial values, invariants**, and observable behavior of a class.
- Write tests for constructors/factories: default values, normalization, all boundary values, and cases that cannot be instantiated.
- Write tests for state-changing methods: successful operations, operation sequences, rejected commands, and rollback/strong exception guarantee when required.
- Select **equivalence partitions** and **boundary values**: min-1, min, min+1, max-1, max, max+1; null, empty, blank; zero, overflow, and time data.
- Use **Arrange–Act–Assert**, dedicated test fixtures, meaningful assertions, and easily diagnosable error labels.
- Distinguish between checking **return values**, **object state**, **exception type**, and **external side effects**; do not overlook state after an exception.
- Avoid fake tests: only calling a method, using `catch(Exception)` and letting it PASS, or using Java `assert` while forgetting `-ea`.
- Check defensive copies, immutable value objects, and derived values after an update.
- Use table-driven/property testing for multiple cases with the same logic and a state-transition matrix for workflows.
- Know how to organize tests using JUnit Jupiter 5, `@Test`, `@BeforeEach`, `assertThrows`, `assertAll`, `@ParameterizedTest`, along with Maven Surefire.
- Write stable unit tests: fixed inputs, controlled clocks, and no reliance on network, thread sleeps, GC timing, or HashMap order.
- Compile and run Java 17+ test suites on your own **without external libraries**, verify expected stdout, and find real bugs.

> **Scope and version:** JDK 17 and later. Programs with `public class FileName` can run **standalone** using the `javac --release 17` and `java` commands. Snippets without main are for illustration only. The JUnit Maven example in a later section requires explicitly declared dependencies.

## 1. Testing Is Not Just Calling a Method

Suppose we have an `Account` with an initial balance of 100:

~~~java
Account account = new Account(100); // Arrange
account.deposit(50);                // Act
check(account.balance() == 150, "deposit"); // Assert
~~~

Without the final assertion, the test would pass even if `deposit` were an empty method. A valuable test must describe **observable correct behavior**.

Each contract should include:

1. **Input/precondition:** initial values, object state, collaborators.
2. **Operation:** constructor, method, state transition.
3. **Expected value/state:** what must change and what remains unchanged.
4. **Invalid path:** when processing cannot proceed, which error is reported and what state results.
5. **Invariant:** properties that must continue to hold after operations.

Account example:

~~~text
opening >= 0
deposit amount > 0
withdraw amount > 0 and <= balance
balance never negative
invalid input must not change balance
arithmetic overflow must be rejected
~~~

### 1.1. Four Mandatory Test Groups

| Group | Examples | What to Verify |
| --- | --- | --- |
| Initialization | Account(0), Account(-1) | Correct initial state, invalid rejected |
| Updates | deposit(50), withdraw(20) | Before/after and invariants |
| Boundary cases | withdraw(balance), quantity 1/100 | No off-by-one errors |
| Invalid input | null, blank, negative, overflow | Correct exception, state uncorrupted |

A test suite with only the happy path does not guarantee invariants. A suite with only exceptions does not guarantee valid operations work.

## 2. Assertions Must Actually Execute

The Java keyword `assert` is disabled by default if you run `java Main` without `-ea`. To ensure tests cannot be silently skipped, use JUnit or a helper:

~~~java
static void check(boolean ok, String label) {
    if (!ok) {
        throw new AssertionError(label);
    }
}
~~~

For exceptions, the pattern is:

~~~java
static void expectThrows(
        Class<? extends Throwable> kind, Runnable operation) {
    try {
        operation.run();
    } catch (Throwable caught) {
        if (kind.isInstance(caught)) {
            return;
        }
        throw new AssertionError("wrong exception", caught);
    }
    throw new AssertionError("missing exception");
}
~~~

These small helpers are only used in standalone programs. JUnit `assertThrows` provides better error reporting and uses the `Executable` functional interface to support checked exceptions. `catch(Throwable)` only serves to verify the exact type in the demo helper, not as a pattern for handling all errors in production.

**Never:**

~~~java
try {
    account.withdraw(-1);
} catch (Exception ignored) {
    // PASS? Wrong: might swallow an NPE caused by a bug.
}
~~~

It does not report a failure when the operation does not throw, and it might accept an exception type different from the contract.

## 3. Constructor Tests: Valid Inputs, Normalization, Null, and Boundaries

Example requirement: A Customer has a non-empty name after `strip()`, and age in the range [0,150].

Case classes:
- age=0 and 150 are valid;
- age=-1 and 151 are rejected;
- name=null → NPE;
- name="" and name="   " → IllegalArgumentException;
- name="  Lan  " → canonical value "Lan".

### 3.1. Program 1 — Constructor Validation

Save **`ConstructorTest.java`**:

~~~java
import java.util.Objects;

public class ConstructorTest {
    static final class Customer {
        private final String name;
        private final int age;

        Customer(String name, int age) {
            Objects.requireNonNull(name, "name");
            String cleaned = name.strip();
            if (cleaned.isEmpty()) {
                throw new IllegalArgumentException("blank");
            }
            if (age < 0 || age > 150) {
                throw new IllegalArgumentException("age");
            }
            this.name = cleaned;
            this.age = age;
        }

        String name() {
            return name;
        }

        int age() {
            return age;
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static void expect(Class<? extends Throwable> kind,
                       Runnable operation) {
        try {
            operation.run();
        } catch (Throwable caught) {
            if (kind.isInstance(caught)) {
                return;
            }
            throw new AssertionError("wrong error", caught);
        }
        throw new AssertionError("expected error");
    }

    public static void main(String[] args) {
        Customer baby = new Customer(" Lan ", 0);
        Customer elder = new Customer("Minh", 150);
        check(baby.name().equals("Lan"), "normalized");
        check(baby.age() == 0, "lower bound");
        check(elder.age() == 150, "upper bound");

        expect(NullPointerException.class,
                () -> new Customer(null, 20));
        expect(IllegalArgumentException.class,
                () -> new Customer("", 20));
        expect(IllegalArgumentException.class,
                () -> new Customer("   ", 20));
        expect(IllegalArgumentException.class,
                () -> new Customer("A", -1));
        expect(IllegalArgumentException.class,
                () -> new Customer("A", 151));

        System.out.println("constructor tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 ConstructorTest.java
java ConstructorTest
~~~

Stdout:

~~~text
constructor tests passed
~~~

**Key takeaway:** Tests do not only check whether a constructor throws. They check both valid object state and normalization. When a constructor fails, the caller does not receive a fully initialized instance; if the constructor also calls an external dependency, tests must ensure there are no unintended side effects.

## 4. Constructor Overloads and Default Values

If a class has:

~~~java
class Timer {
    private final int seconds;

    Timer() {
        this(30);
    }

    Timer(int seconds) {
        if (seconds <= 0) {
            throw new IllegalArgumentException("seconds");
        }
        this.seconds = seconds;
    }
}
~~~

All paths must share the invariant seconds>0. Testing one valid constructor does not prove the other overload is correct. You should test default=30, minimum=1, invalid 0, and a typical explicit value.

### 4.1. Program 2 — Overload Tests

Save **`OverloadTest.java`**:

~~~java
public class OverloadTest {
    static final class Timer {
        private final int seconds;

        Timer() {
            this(30);
        }

        Timer(int seconds) {
            if (seconds <= 0) {
                throw new IllegalArgumentException("seconds");
            }
            this.seconds = seconds;
        }

        int seconds() {
            return seconds;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(new Timer().seconds() == 30, "default");
        check(new Timer(1).seconds() == 1, "min");
        check(new Timer(60).seconds() == 60, "explicit");

        try {
            new Timer(0);
            throw new AssertionError("zero accepted");
        } catch (IllegalArgumentException expected) {
            // Validation works.
        }

        System.out.println("overload tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 OverloadTest.java
java OverloadTest
~~~

Stdout:

~~~text
overload tests passed
~~~

## 5. Update Tests: Before, Act, After, and Rejected Action

An Account can deposit/withdraw, but must keep balance≥0. We need:

- initial balance;
- deposit success;
- withdraw success;
- withdrawing the exact balance to 0;
- rejecting 0/negative deposit;
- rejecting withdraw exceeding balance;
- rejecting overflow instead of wraparound;
- every rejected command keeps balance as before.

If a method updates multiple fields, check **all canonical fields** after rejection rather than just one field.

### 5.1. Program 3 — Update and Unchanged State on Failure

Save **`AccountTest.java`**:

~~~java
public class AccountTest {
    static final class Account {
        private long balance;

        Account(long opening) {
            if (opening < 0) {
                throw new IllegalArgumentException("opening");
            }
            balance = opening;
        }

        long balance() {
            return balance;
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("deposit");
            }
            balance = Math.addExact(balance, amount);
        }

        void withdraw(long amount) {
            if (amount <= 0 || amount > balance) {
                throw new IllegalArgumentException("withdraw");
            }
            balance -= amount;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void expect(Class<? extends Throwable> kind,
                       Runnable operation) {
        try {
            operation.run();
        } catch (Throwable caught) {
            if (kind.isInstance(caught)) {
                return;
            }
            throw new AssertionError("wrong exception", caught);
        }
        throw new AssertionError("no exception");
    }

    public static void main(String[] args) {
        Account account = new Account(100);
        check(account.balance() == 100, "initial");

        account.deposit(50);
        check(account.balance() == 150, "deposit");

        account.withdraw(25);
        check(account.balance() == 125, "withdraw");

        long beforeError = account.balance();
        expect(IllegalArgumentException.class,
                () -> account.deposit(0));
        expect(IllegalArgumentException.class,
                () -> account.deposit(-1));
        expect(IllegalArgumentException.class,
                () -> account.withdraw(0));
        expect(IllegalArgumentException.class,
                () -> account.withdraw(126));

        check(account.balance() == beforeError,
                "invalid commands preserve balance");

        Account nearMax = new Account(Long.MAX_VALUE - 1);
        expect(ArithmeticException.class,
                () -> nearMax.deposit(2));
        check(nearMax.balance() == Long.MAX_VALUE - 1,
                "overflow must not mutate balance");

        Account exact = new Account(100);
        exact.withdraw(100);
        check(exact.balance() == 0, "exact full withdrawal");

        System.out.println("account tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 AccountTest.java
java AccountTest
~~~

Stdout:

~~~text
account tests passed
~~~

In `balance = Math.addExact(balance, amount)`, if Math.addExact throws, the RHS does not return a value, so the assignment never completes. That helps preserve balance in the overflow case. Do not assume that every method with multiple assignments is atomic; with DB/concurrency, appropriate transactions or synchronization are still required.

## 6. Equivalence Partitioning and Boundary-Value Analysis

For a quantity field in [1,100]:

| Partition | Representative Values | Expected |
| --- | --- | --- |
| Below | -1, 0 | Reject |
| Min | 1 | Accept |
| In range | 2, 50, 99 | Accept |
| Max | 100 | Accept |
| Above | 101, 1000 | Reject |

The focus is on the **min-1 / min / min+1 / max-1 / max / max+1** points to catch off-by-one errors. Include special data types: null, empty, whitespace, integer min/max, overflow, and date-time boundaries.

### 6.1. Program 4 — Quantity Boundary

Save **`QuantityTest.java`**:

~~~java
public class QuantityTest {
    record Line(long cents, int quantity) {
        Line {
            if (cents < 0) {
                throw new IllegalArgumentException("price");
            }
            if (quantity < 1 || quantity > 100) {
                throw new IllegalArgumentException("quantity");
            }
        }

        long total() {
            return Math.multiplyExact(cents, quantity);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void reject(int quantity) {
        try {
            new Line(50, quantity);
            throw new AssertionError("accepted " + quantity);
        } catch (IllegalArgumentException expected) {
            // Rejected.
        }
    }

    public static void main(String[] args) {
        check(new Line(50, 1).total() == 50, "min");
        check(new Line(50, 2).total() == 100, "min+1");
        check(new Line(50, 99).total() == 4950, "max-1");
        check(new Line(50, 100).total() == 5000, "max");
        reject(-1);
        reject(0);
        reject(101);
        System.out.println("quantity tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 QuantityTest.java
java QuantityTest
~~~

Stdout:

~~~text
quantity tests passed
~~~

## 7. Table-Driven Tests for Multiple Inputs with the Same Behavior

If input→expected is easy to express as a table, use a record/array instead of dozens of repetitive methods.

Example policy:
- Scores outside [0,100] are rejected.
- A if ≥90, B if ≥80, C if ≥50, D otherwise.

~~~text
score:      0  49  50  79  80  89  90 100
expected:   D   D   C   C   B   B   A   A
~~~

### 7.1. Program 5 — Table-Driven Grade Test

Save **`GradeTest.java`**:

~~~java
public class GradeTest {
    record Case(int score, String expected) {
    }

    static String grade(int score) {
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException("score");
        }
        if (score >= 90) {
            return "A";
        }
        if (score >= 80) {
            return "B";
        }
        if (score >= 50) {
            return "C";
        }
        return "D";
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Case[] tests = {
                new Case(0, "D"), new Case(49, "D"),
                new Case(50, "C"), new Case(79, "C"),
                new Case(80, "B"), new Case(89, "B"),
                new Case(90, "A"), new Case(100, "A")
        };

        for (Case test : tests) {
            check(test.expected().equals(grade(test.score())),
                    "score=" + test.score());
        }

        for (int invalid : new int[] {-1, 101}) {
            try {
                grade(invalid);
                throw new AssertionError("accepted " + invalid);
            } catch (IllegalArgumentException expected) {
                // Outside score domain.
            }
        }

        System.out.println("table cases=" + tests.length);
        System.out.println("grade tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 GradeTest.java
java GradeTest
~~~

Stdout:

~~~text
table cases=8
grade tests passed
~~~

The table above is just an illustrative policy, not a mandatory grading scale. A good test accurately expresses the **business requirement** rather than the test author's implicit assumptions.

## 8. State-Transition Tests: Constructor + Workflow Updates

An Order object can have states:

~~~text
DRAFT ──pay────► PAID
   |
   └──cancel───► CANCELLED
~~~

Other transitions are forbidden in this demo. Tests should verify:
- A new Order is in DRAFT.
- Pay from DRAFT to PAID.
- Cancel from DRAFT to CANCELLED.
- Cannot pay twice, cannot cancel PAID, and cannot pay CANCELLED.
- A rejected transition must preserve the original state.

### 8.1. Program 6 — Order Lifecycle Tests

Save **`OrderStateTest.java`**:

~~~java
public class OrderStateTest {
    enum State {
        DRAFT, PAID, CANCELLED
    }

    static final class Order {
        private State state = State.DRAFT;

        State state() {
            return state;
        }

        void pay() {
            if (state != State.DRAFT) {
                throw new IllegalStateException("pay");
            }
            state = State.PAID;
        }

        void cancel() {
            if (state != State.DRAFT) {
                throw new IllegalStateException("cancel");
            }
            state = State.CANCELLED;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void rejected(Runnable action) {
        try {
            action.run();
        } catch (IllegalStateException expected) {
            return;
        }
        throw new AssertionError("invalid transition accepted");
    }

    public static void main(String[] args) {
        Order paid = new Order();
        check(paid.state() == State.DRAFT, "initial");
        paid.pay();
        check(paid.state() == State.PAID, "paid");

        rejected(paid::pay);
        rejected(paid::cancel);
        check(paid.state() == State.PAID, "paid remains");

        Order cancelled = new Order();
        cancelled.cancel();
        check(cancelled.state() == State.CANCELLED, "cancelled");
        rejected(cancelled::pay);
        check(cancelled.state() == State.CANCELLED,
                "cancelled remains");

        System.out.println("state transition tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 OrderStateTest.java
java OrderStateTest
~~~

Stdout:

~~~text
state transition tests passed
~~~

Each test scenario has a fresh Order fixture. One test should not rely on another test having already paid on a shared object.

## 9. Exception Safety: Validate Before Changing Multiple Fields

Anti-pattern:

~~~java
void change(int nextQuantity, long nextPrice) {
    quantity = nextQuantity;
    validate(nextPrice); // May throw.
    price = nextPrice;
}
~~~

If validate throws, quantity has already been modified; thus an invalid input can leave the object inconsistent. When the contract requires **all-or-nothing**, tests must snapshot both quantity and price.

Fix: validate the inputs and compute derived constraints **before** any assignments. This does not by itself replace a database transaction or concurrency lock when multiple threads are involved, but it is sufficient to illustrate a single-threaded object.

### 9.1. Program 7 — Atomic Update Tests

Save **`AtomicUpdateTest.java`**:

~~~java
public class AtomicUpdateTest {
    static final class Line {
        private int quantity;
        private long price;

        Line(int quantity, long price) {
            change(quantity, price);
        }

        void change(int nextQuantity, long nextPrice) {
            if (nextQuantity <= 0 || nextPrice < 0) {
                throw new IllegalArgumentException("line");
            }
            Math.multiplyExact(nextQuantity, nextPrice);
            quantity = nextQuantity;
            price = nextPrice;
        }

        int quantity() {
            return quantity;
        }

        long price() {
            return price;
        }

        long total() {
            return Math.multiplyExact(quantity, price);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void rejected(Class<? extends Throwable> kind,
                         Runnable operation) {
        try {
            operation.run();
        } catch (Throwable caught) {
            if (kind.isInstance(caught)) {
                return;
            }
            throw new AssertionError("wrong exception", caught);
        }
        throw new AssertionError("missing exception");
    }

    public static void main(String[] args) {
        Line line = new Line(2, 100);
        line.change(3, 150);
        check(line.total() == 450, "valid update");

        rejected(IllegalArgumentException.class,
                () -> line.change(0, 200));
        check(line.quantity() == 3 && line.price() == 150,
                "after invalid");

        rejected(ArithmeticException.class,
                () -> line.change(2, Long.MAX_VALUE));
        check(line.quantity() == 3 && line.price() == 150,
                "after overflow");
        check(line.total() == 450, "derived total");

        System.out.println("atomic update tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 AtomicUpdateTest.java
java AtomicUpdateTest
~~~

Stdout:

~~~text
atomic update tests passed
~~~

## 10. Null, Empty, and Blank Are Distinct Data Types

For String input:
- Null: no object exists; may throw an NPE if the contract uses `requireNonNull`.
- Empty: `""` has length 0.
- Blank: `"   "` has length>0, yet `isBlank()` is true.
- Normalized: `"  Lan  "` can be stripped to "Lan".
- Unicode: `String.length()` counts UTF-16 code units, not necessarily the number of grapheme clusters; the domain must define the unit of measurement for user-facing limits.

### 10.1. Program 8 — Text Input Tests

Save **`TextInputTest.java`**:

~~~java
import java.util.Objects;

public class TextInputTest {
    record UserName(String value) {
        UserName {
            value = Objects.requireNonNull(value).strip();
            if (value.isBlank() || value.length() > 12) {
                throw new IllegalArgumentException("username");
            }
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void rejects(Class<? extends Throwable> kind,
                        Runnable operation) {
        try {
            operation.run();
        } catch (Throwable caught) {
            if (kind.isInstance(caught)) {
                return;
            }
            throw new AssertionError("wrong exception", caught);
        }
        throw new AssertionError("not rejected");
    }

    public static void main(String[] args) {
        check(new UserName(" Lan ").value().equals("Lan"),
                "normalized");
        check(new UserName("A").value().length() == 1, "min");
        check(new UserName("123456789012").value().length() == 12,
                "max");

        rejects(NullPointerException.class,
                () -> new UserName(null));
        rejects(IllegalArgumentException.class,
                () -> new UserName(""));
        rejects(IllegalArgumentException.class,
                () -> new UserName("    "));
        rejects(IllegalArgumentException.class,
                () -> new UserName("1234567890123"));

        System.out.println("text input tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 TextInputTest.java
java TextInputTest
~~~

Stdout:

~~~text
text input tests passed
~~~

If the spec limits 12 code points instead of UTF-16 units, you must adjust the rule and tests accordingly; do not treat the example as a universal username policy.

## 11. Testing Defensive Copies and Not Exposing Mutable State

A record with a List component has a final reference, yet it is **not necessarily deeply immutable**. If it retains a mutable input List directly, the caller can add/remove elements after the constructor completes.

Use `List.copyOf` to create an unmodifiable snapshot of the List structure; for nested mutable elements, it is still a shallow copy. Tests should check:
- caller mutating the original list does not affect the object;
- the getter does not allow mutation;
- null list and null elements are handled according to the contract;
- derived count/sum are not stale.

### 11.1. Program 9 — Defensive Copy Tests

Save **`DefensiveCopyTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class DefensiveCopyTest {
    record Basket(List<String> items) {
        Basket {
            items = List.copyOf(items);
        }

        int count() {
            return items.size();
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket basket = new Basket(source);
        source.add("B");

        check(basket.count() == 1, "snapshot size");
        check(basket.items().equals(List.of("A")),
                "snapshot contents");

        try {
            basket.items().add("C");
            throw new AssertionError("mutable getter");
        } catch (UnsupportedOperationException expected) {
            // Correctly unmodifiable.
        }

        try {
            new Basket(null);
            throw new AssertionError("null list accepted");
        } catch (NullPointerException expected) {
            // Rejected.
        }

        try {
            new Basket(Arrays.asList("A", null));
            throw new AssertionError("null element accepted");
        } catch (NullPointerException expected) {
            // List.copyOf rejects null elements.
        }

        System.out.println("defensive copy tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 DefensiveCopyTest.java
java DefensiveCopyTest
~~~

Stdout:

~~~text
defensive copy tests passed
~~~

## 12. Derived State After an Immutable Update

An immutable Line should store source fields and compute total when needed. Tests must verify that the old object remains **unchanged** after creating a new instance and after an invalid attempt.

### 12.1. Program 10 — Immutable Update Tests

Save **`ImmutableUpdateTest.java`**:

~~~java
public class ImmutableUpdateTest {
    record Line(long cents, int quantity) {
        Line {
            if (cents < 0 || quantity <= 0) {
                throw new IllegalArgumentException("line");
            }
        }

        long total() {
            return Math.multiplyExact(cents, quantity);
        }

        Line withQuantity(int next) {
            return new Line(cents, next);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Line original = new Line(100, 2);
        Line updated = original.withQuantity(3);

        check(original.quantity() == 2, "old quantity");
        check(original.total() == 200, "old total");
        check(updated.quantity() == 3, "new quantity");
        check(updated.total() == 300, "new total");

        try {
            original.withQuantity(-1);
            throw new AssertionError("negative accepted");
        } catch (IllegalArgumentException expected) {
            // Old value unchanged.
        }

        check(original.total() == 200, "after rejection");

        System.out.println("immutable update tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 ImmutableUpdateTest.java
java ImmutableUpdateTest
~~~

Stdout:

~~~text
immutable update tests passed
~~~

If the class uses a cached total field, this test will catch the regression “quantity changed but old total still appears”.

## 13. Numeric Extremes and Overflow

You should test:
- domain min/max;
- zero and negative values if forbidden;
- derived operations such as `quantity * price` near limits;
- BigDecimal precision/rounding if monetary amounts have fractions;
- integer division/wrong units (cents versus dollars).

`Math.multiplyExact` and `Math.addExact` are tools for detecting long overflow instead of silent wraparound.

### 13.1. Program 11 — Overflow Boundary Tests

Save **`OverflowTest.java`**:

~~~java
public class OverflowTest {
    record Line(long priceCents, int quantity) {
        Line {
            if (priceCents < 0 || quantity < 0) {
                throw new IllegalArgumentException("line");
            }
        }

        long total() {
            return Math.multiplyExact(priceCents, quantity);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(new Line(0, 10).total() == 0, "zero");
        check(new Line(125, 3).total() == 375, "normal");
        check(new Line(Long.MAX_VALUE, 1).total()
                == Long.MAX_VALUE, "max");

        try {
            new Line(Long.MAX_VALUE, 2).total();
            throw new AssertionError("overflow accepted");
        } catch (ArithmeticException expected) {
            // Exact arithmetic rejects overflow.
        }

        System.out.println("overflow tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 OverflowTest.java
java OverflowTest
~~~

Stdout:

~~~text
overflow tests passed
~~~

Do not pin the exact message of a JDK-thrown ArithmeticException if the contract only requires the exception type.

## 14. Time Boundary Tests Must Be Deterministic

Use `LocalDate.of(...)` or inject a `Clock`; do not rely on `LocalDate.now()` in tests with fixed expected values. Example: a subscription active on **[start, end)** (start inclusive, end exclusive).

Tests:
- day before start → false;
- start day → true;
- last day before end → true;
- end day → false;
- end<=start → constructor rejects.

### 14.1. Program 12 — Period Boundary Tests

Save **`PeriodTest.java`**:

~~~java
import java.time.LocalDate;

public class PeriodTest {
    record Subscription(LocalDate start, LocalDate end) {
        Subscription {
            if (start == null || end == null ||
                    !start.isBefore(end)) {
                throw new IllegalArgumentException("period");
            }
        }

        boolean activeAt(LocalDate day) {
            if (day == null) {
                throw new IllegalArgumentException("day");
            }
            return !day.isBefore(start) && day.isBefore(end);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Subscription s = new Subscription(
                LocalDate.of(2026, 10, 1),
                LocalDate.of(2026, 11, 1));

        check(!s.activeAt(LocalDate.of(2026, 9, 30)),
                "before start");
        check(s.activeAt(LocalDate.of(2026, 10, 1)),
                "inclusive start");
        check(s.activeAt(LocalDate.of(2026, 10, 31)),
                "last active day");
        check(!s.activeAt(LocalDate.of(2026, 11, 1)),
                "exclusive end");

        try {
            new Subscription(LocalDate.of(2026, 11, 1),
                    LocalDate.of(2026, 11, 1));
            throw new AssertionError("empty period accepted");
        } catch (IllegalArgumentException expected) {
            // Zero duration not allowed.
        }

        System.out.println("period tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 PeriodTest.java
java PeriodTest
~~~

Stdout:

~~~text
period tests passed
~~~

In a timestamp domain, you need `Instant` and a timezone/DST contract; do not automatically reduce every “expiry” to LocalDate.

## 15. Property/Invariant Testing over a Small Domain

Instead of a single input, use loops to check properties:

~~~text
price>=0, quantity>=0
total=price×quantity
total>=0 in the non-overflow domain
quantity=0 ⇒ total=0
~~~

Looping price=0..20 and quantity=0..20 checks 21×21=441 cases. It does not prove all long values, but it finds regressions well.

### 15.1. Program 13 — Property Test

Save **`PropertyTest.java`**:

~~~java
public class PropertyTest {
    record Line(long price, int quantity) {
        Line {
            if (price < 0 || quantity < 0) {
                throw new IllegalArgumentException("line");
            }
        }

        long total() {
            return Math.multiplyExact(price, quantity);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        int cases = 0;
        for (int price = 0; price <= 20; price++) {
            for (int quantity = 0; quantity <= 20; quantity++) {
                Line line = new Line(price, quantity);
                check(line.total() == (long) price * quantity,
                        "formula");
                check(line.total() >= 0, "nonnegative");
                if (quantity == 0) {
                    check(line.total() == 0, "zero quantity");
                }
                cases++;
            }
        }
        System.out.println("property cases=" + cases);
        System.out.println("property tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 PropertyTest.java
java PropertyTest
~~~

Stdout:

~~~text
property cases=441
property tests passed
~~~

In larger projects, you can use property-based libraries to generate data and shrink failures, though that requires a separate dependency. If using random inputs, save the seed to reproduce failures.

## 16. Test Isolation: No Shared Mutable Fixtures

Test B must not depend on test A running first. A classic mistake:

~~~java
// static Account shared = new Account(100);
// testA deposit(50), testB expects initial=100.
// Results depend on order and cause a flaky suite.
~~~

Each test should create its own object or use `@BeforeEach`. Do not depend on an unreset static collection, machine timezone, network, thread scheduling, or GC timing.

### 16.1. Program 14 — Independent Fixtures

Save **`IsolationTest.java`**:

~~~java
public class IsolationTest {
    static class Counter {
        private int value;

        Counter(int initial) {
            value = initial;
        }

        void increment() {
            value++;
        }

        int value() {
            return value;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void testIncrement() {
        Counter counter = new Counter(10);
        counter.increment();
        check(counter.value() == 11, "increment");
    }

    static void testInitial() {
        Counter counter = new Counter(10);
        check(counter.value() == 10, "initial");
    }

    public static void main(String[] args) {
        testIncrement();
        testInitial();
        testInitial();
        testIncrement();

        System.out.println("isolation tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 IsolationTest.java
java IsolationTest
~~~

Stdout:

~~~text
isolation tests passed
~~~

## 17. Testing Side Effects with a Fake Dependency

If a class sends a notification upon successful registration, tests should not send real emails. Inject an interface and a fake that records messages in memory. Verify that **a notification is sent when valid** and **no notification is sent on invalid input**.

### 17.1. Program 15 — Notifier Fake

Save **`NotifierTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class NotifierTest {
    interface Notifier {
        void send(String message);
    }

    static final class FakeNotifier implements Notifier {
        private final List<String> sent = new ArrayList<>();

        @Override
        public void send(String message) {
            sent.add(message);
        }

        List<String> sent() {
            return List.copyOf(sent);
        }
    }

    static final class Registration {
        private final Notifier notifier;

        Registration(Notifier notifier) {
            this.notifier = Objects.requireNonNull(notifier);
        }

        void register(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name");
            }
            notifier.send("registered:" + name);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        FakeNotifier fake = new FakeNotifier();
        Registration service = new Registration(fake);
        service.register("Lan");

        check(fake.sent().equals(List.of("registered:Lan")),
                "valid notification");

        try {
            service.register(" ");
            throw new AssertionError("blank accepted");
        } catch (IllegalArgumentException expected) {
            // Validation should have no side effect.
        }

        check(fake.sent().size() == 1,
                "error must not notify");

        System.out.println("notifier tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 NotifierTest.java
java NotifierTest
~~~

Stdout:

~~~text
notifier tests passed
~~~

## 18. Sequence Tests and Idempotence

A stateful object may behave correctly when testing individual calls yet fail after multiple operations. For example:

~~~text
new Counter(0)
increase → 1
increase → 2
decrease → 1
reset → 0
decrease → exception and remains 0
~~~

Sequence tests should verify intermediate states as well; if the business logic requires an idempotent command, invoke it repeatedly and compare the corresponding results. Do not assume every command must be idempotent: `increment` is naturally not idempotent, whereas `setStatus(PAID)` may have a different contract.

### 18.1. Program 16 — Counter Sequence Test

Save **`SequenceTest.java`**:

~~~java
public class SequenceTest {
    static final class Counter {
        private int value;

        Counter(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial");
            }
            value = initial;
        }

        int value() {
            return value;
        }

        void increase() {
            value = Math.addExact(value, 1);
        }

        void decrease() {
            if (value == 0) {
                throw new IllegalStateException("zero");
            }
            value--;
        }

        void reset() {
            value = 0;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Counter c = new Counter(0);
        check(c.value() == 0, "initial");
        c.increase();
        c.increase();
        check(c.value() == 2, "two increases");
        c.decrease();
        check(c.value() == 1, "decrease");
        c.reset();
        check(c.value() == 0, "reset");

        try {
            c.decrease();
            throw new AssertionError("negative allowed");
        } catch (IllegalStateException expected) {
            check(c.value() == 0, "state unchanged");
        }

        System.out.println("sequence tests passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 SequenceTest.java
java SequenceTest
~~~

Stdout:

~~~text
sequence tests passed
~~~

## 19. JUnit Jupiter 5 in a Maven Project

Hand-written helpers are great for standalone Java 17 exercises. Real-world projects should use JUnit Jupiter:

- `@Test`: a test method.
- `@BeforeEach`: a fresh fixture before each invocation.
- `assertEquals(expected,actual)`, `assertTrue/False`: values.
- `assertThrows(Expected.class, executable)`: exception type.
- `assertAll(...)`: related assertions.
- `@ParameterizedTest` and `@ValueSource`/`@CsvSource`: multiple test cases.
- `assertIterableEquals`: iterables in order.

JUnit is not part of the JDK standard library. Maven requires the appropriate dependency.

### 19.1. Project Layout

~~~text
account-junit/
├── pom.xml
└── src/
    ├── main/java/example/Account.java
    └── test/java/example/AccountTest.java
~~~

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>account-junit</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.11.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version 5.10.2 is pinned for illustration so the build is reproducible, without claiming it is the “latest” for the current year. When Maven does not yet have the dependencies cached, a connection to Maven repositories is required on the first build.

**`src/main/java/example/Account.java`:**

~~~java
package example;

public final class Account {
    private long balance;

    public Account(long opening) {
        if (opening < 0) {
            throw new IllegalArgumentException("opening");
        }
        balance = opening;
    }

    public long balance() {
        return balance;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
        balance = Math.addExact(balance, amount);
    }

    public void withdraw(long amount) {
        if (amount <= 0 || amount > balance) {
            throw new IllegalArgumentException("amount");
        }
        balance -= amount;
    }
}
~~~

**`src/test/java/example/AccountTest.java`:**

~~~java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.*;

class AccountTest {
    private Account account;

    @BeforeEach
    void setUp() {
        account = new Account(100);
    }

    @Test
    void constructorInitializesCorrectly() {
        assertEquals(100, account.balance());
        assertThrows(IllegalArgumentException.class,
                () -> new Account(-1));
    }

    @Test
    void updatesChangeBalance() {
        account.deposit(50);
        assertEquals(150, account.balance());
        account.withdraw(25);
        assertEquals(125, account.balance());
    }

    @ParameterizedTest
    @ValueSource(longs = {0, -1, Long.MIN_VALUE})
    void invalidDepositsPreserveBalance(long amount) {
        long before = account.balance();
        assertThrows(IllegalArgumentException.class,
                () -> account.deposit(amount));
        assertEquals(before, account.balance());
    }

    @Test
    void withdrawalBeyondBalanceIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> account.withdraw(101));
        assertEquals(100, account.balance());
    }

    @Test
    void overflowPreservesPreviousBalance() {
        Account large = new Account(Long.MAX_VALUE - 1);
        assertThrows(ArithmeticException.class,
                () -> large.deposit(2));
        assertEquals(Long.MAX_VALUE - 1, large.balance());
    }

    @Test
    void exactWithdrawalReachesZero() {
        account.withdraw(100);
        assertAll(
                () -> assertEquals(0, account.balance()),
                () -> assertThrows(IllegalArgumentException.class,
                        () -> account.withdraw(1)));
    }
}
~~~

### 19.2. Running JUnit with Maven

From inside `account-junit`:

~~~bash
mvn test
~~~

Maven builds and runs **8 invocations**: five `@Test` methods, plus three invocations of a single `@ParameterizedTest`. JUnit `@BeforeEach` creates a fresh Account(100) for each invocation.

Detailed Maven/Surefire output depends on the version and system, so Maven's console stdout is not fixed here. Expect the build to **PASS**, with no tests failing. If Maven or network access for dependencies is missing, that is an environment issue that cannot be resolved using only the JDK's `javac`.

### 19.3. Asserting the Right Type

`assertThrows(IllegalArgumentException.class, action)` accepts IllegalArgumentException and its subclasses. If you only check RuntimeException, an unrelated NullPointerException could be mistakenly accepted as expected. Choose the specific type according to the contract. If the exact type is required, JUnit provides `assertThrowsExactly` in supported versions.

## 20. Unit Tests, Integration Tests, and External State

A unit test for Account/Line should not depend on:
- a production DB and production data;
- the network or a real payment/email service;
- an uncleaned shared filesystem path;
- `LocalDate.now()` and differing timezones across machines;
- unseeded `Math.random()`;
- thread scheduling waited on with `Thread.sleep`;
- `HashMap` iteration order without a contract;
- GC and finalizer timing.

If a test truly needs a DB/service, classify it as an integration test, use a sandbox/test DB, and clean up explicitly. Replace external dependencies in unit tests with fakes/stubs or design for injection.

## 21. Mutation Testing: Do Assertions Catch Real Bugs?

A suite can achieve high line coverage and still miss bugs. Imagine someone “mutates” the code:

- Change `amount > balance` to `amount >= balance`: the test withdrawing the exact balance must fail.
- Change `quantity < 1` to `quantity < 0`: the quantity=0 test must fail.
- Delete `balance -= amount`: the state assertion must fail.
- Change `Math.addExact` to `+`: the overflow test must fail.
- Remove `List.copyOf`: the defensive-copy test must fail.
- Call the notifier before validation: the fake test must fail.
- Change `day.isBefore(end)` to an inclusive end: the boundary test must fail.

If tests merely “call the code” without failing on these faults, strengthen your assertions. Mutation-testing tools such as PIT can help in projects with a build system; they are not a requirement for core Java exercises.

## 22. Testing Anti-Patterns to Avoid

| Anti-pattern | Consequence | Replace With |
| --- | --- | --- |
| Happy path only | Misses edge/error cases | Four-group matrix |
| Calling a method without asserting | False PASS | Assert state/result |
| `catch(Exception)` then PASS | Hides unexpected NPE | Exact contract type |
| Not failing when no exception is thrown | Invalid input accepted still PASSes | `assertThrows`/helper |
| Java `assert` without -ea | Tests may not execute | JUnit/helper |
| `==` for String content | Confuses identity and value | `equals` |
| Checking only the exception | Partial state mutation slips through | Check state after error |
| Sharing a static fixture | Test-order dependence | Fresh per test |
| `LocalDate.now()` | Flaky across dates/timezones | Fixed input date/Clock |
| HashMap order assertion | Nondeterminism | Map equality/keys |
| `Thread.sleep(100)` | Race/flaky | Test scheduler/latch |
| Real network in unit tests | Slow/flaky/external effects | Fake/stub |
| Hardcoding JDK error messages | Brittle | Check type/code contract |
| Not testing min/max | Off-by-one | Boundary-value analysis |
| Not testing overflow | Silent wraparound | Exact math tests |
| Exposing backing ArrayList | External mutation | Defensive-copy test |
| Reflecting into private methods | Test coupling | Public behavior |
| Looking only at coverage % | Does not verify correctness | Mutation/invariants |

## 23. Practical Checklist

- [ ] Is every constructor/factory tested with valid/default/invalid inputs?
- [ ] Are class invariants clearly written before selecting cases?
- [ ] Is state asserted immediately after initialization?
- [ ] Do update tests check before/after and unchanged fields?
- [ ] Does an invalid update verify both the exception **and** unchanged state?
- [ ] Do inclusive/exclusive boundaries test min-1/min/min+1 and max-1/max/max+1?
- [ ] Are null, blank, empty, length, and Unicode policies properly understood?
- [ ] Are overflow/precision checked when the domain involves money/large numbers?
- [ ] Are there sequence/state-transition tests?
- [ ] Are there defensive-copy tests for mutable inputs?
- [ ] Are there table-driven/property cases?
- [ ] Are assertions guaranteed to execute without relying on disabled `assert`?
- [ ] Are test fixtures independent so re-running/reordering has no effect?
- [ ] Is there a fake to verify external side effects?
- [ ] Are tests deterministic with respect to clock/timezone/random/order?
- [ ] Are unit vs. integration tests properly distinguished?
- [ ] Are there tests guarding against previously seen bugs?
- [ ] Are JUnit/Maven dependencies completely declared?
- [ ] Can the assertions catch common mutations?
- [ ] Can the code compile/run on JDK 17+ with the matching filename?

## 24. Exercises with Answers

**1.** Age allows [0,150]; pick six boundary values?  
**Answer:** -1,0,1,149,150,151.

**2.** Account balance=100, withdraw(100) and withdraw(101)?  
**Answer:** 100 is valid, leaving balance=0; 101 throws and the state remains unchanged on an account starting at 100.

**3.** Is `catch(RuntimeException)` sufficient to test invalid input?  
**Answer:** No, it can hide an NPE bug or the wrong exception type.

**4.** A method changes quantity before validating price; an invalid price throws. How to test?  
**Answer:** Assert the exception and that both the old quantity/price remain unchanged.

**5.** A List constructor only assigns the input reference. Which test catches this bug?  
**Answer:** Modify the input list after construction and verify the object does not change if the contract requires a snapshot.

**6.** Is Subscription [start,end) still active on the end day?  
**Answer:** No; test before start, start, before end, and end.

**7.** `Long.MAX_VALUE * 2` for total money?  
**Answer:** Use Math.multiplyExact and expect ArithmeticException according to the contract.

**8.** A test only fails after another test runs?  
**Answer:** Shared mutable state; create a fresh fixture for each case.

**9.** How many times does a `@ParameterizedTest` receiving three inputs run?  
**Answer:** Three invocations.

**10.** Invalid registration throws, yet the notifier receives another message; does the test PASS?  
**Answer:** No; an erroneous external side effect occurred.

**11.** Does Java `assert` run by default with `java App`?  
**Answer:** No; `-ea` or JUnit/a helper is required.

**12.** Comparing two different String objects with the same content using `==`?  
**Answer:** Not guaranteed to be true; use equals.

**13.** Quantity [1,100], which values near the boundaries should be tested?  
**Answer:** 0,1,2,99,100,101.

**14.** Quantity changes from 2→3, and the old total stays 200?  
**Answer:** A bug if price=100; test that total becomes 300.

**15.** Does `Thread.sleep(100)` guarantee async completion?  
**Answer:** No; use appropriate synchronization/test clock/scheduler.

**16.** Property loop with price=0..20 and quantity=0..20?  
**Answer:** 441 cases.

**17.** Should reflection be used to test a private method?  
**Answer:** No; prioritize the observable contract through public methods.

**18.** Does 100% line coverage prove a class is correct?  
**Answer:** No; assertions and boundary/error scenarios are still needed.

## 25. References

- [JLS 17 `8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructors and initialization.
- [JLS 17 `11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): throw/catch and exception semantics.
- [JLS 17 `14.10 — assert Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.10): conditions for running Java assertions.
- [JLS 17 `15.26 — Assignment Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26): evaluation/assignments.
- [Java SE 17 Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): null input checks.
- [Java SE 17 Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)) and [multiplyExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long)): overflow detection.
- [Java SE 17 List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable collection copies.
- [Java SE 17 LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): deterministic dates.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): Jupiter annotations/assertions, lifecycle, and parameterized tests.
- [JUnit Jupiter 5.10.2 Assertions API](https://junit.org/junit5/docs/5.10.2/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html): `assertEquals`/`assertThrows`/`assertAll`.
- [JUnit Jupiter 5.10.2 ParameterizedTest API](https://junit.org/junit5/docs/5.10.2/api/org.junit.jupiter.params/org/junit/jupiter/params/ParameterizedTest.html): parameterized invocations.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): running test suites.

## Summary

For a stateful Java class, good tests must answer:

- **Initialization:** Does a new object have the right fields, defaults, invariants, and validation?
- **Updates:** Does a successful method update the right state while leaving unrelated parts unchanged?
- **Boundaries:** Are there off-by-one, overflow, time-boundary, or empty/null corner cases?
- **Errors:** Does the exception match the contract, and does it leave behind any partial mutation or side effects?

Organize tests with **Arrange–Act–Assert**, choose boundaries from the spec, use independent fixtures, and verify values/state/side effects rather than just “not throwing”. Use JUnit 5 to organize real projects; use JDK 17 helpers for standalone learning programs. Aim for tests that can catch **a buggy implementation**, not merely increase coverage.
