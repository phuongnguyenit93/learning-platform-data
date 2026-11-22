# Encapsulation to Protect State and Validity Rules in Java

## Learning Objectives

After this lesson, you can:

- Explain **encapsulation** as placing data and operations on that data behind a controlled interface, rather than simply "changing every field to `private`".
- Distinguish between **object state**, **validity rules/object invariants** (*invariant*), and the **preconditions/postconditions** of an operation.
- Design constructors/factories that ensure objects start in a valid state and public methods that maintain a valid state upon completion.
- Use methods with business meaning such as `deposit`, `withdraw`, and `pay` instead of allowing external code to arbitrarily modify fields via uncontrolled setters.
- Distinguish validation at the API boundary from checking coordination rules across multiple fields.
- Use **defensive copying**, immutable values, unmodifiable collections, and read-only APIs to avoid exposing mutable references.
- Handle failed operations using exceptions without leaving the object in a half-updated state.
- Understand the roles of `final`, `static`, visibility, inheritance, concurrent access, and Java records; know what they do **not** guarantee on their own.
- Run and test the Java 17+ examples, including valid cases, invalid cases, and state requirements.

## 1. What Is Encapsulation?

In object-oriented programming, a class is typically responsible for:

1. **State:** data that describes the object, usually stored in instance fields.
2. **Behavior:** operations that allow reading, computing, or modifying state.
3. **Validity rules (invariants):** state conditions that must hold at the times specified by the class contract, especially after a constructor or public operation completes normally.

**Encapsulation** brings data and its related operations together into the same abstraction, while **restricting uncontrolled data modification**. External code interacts through a meaningful API and is subject to the checks defined by the class.

For example, an account balance must be non-negative:

~~~java
class Account {
    public long balance;
}
~~~

If `balance` is public and mutable, a caller can write:

~~~java
Account account = new Account();
account.balance = -500;
~~~

These snippets are **illustrative**; they compile when placed inside a proper class/method structure, yet they demonstrate a design flaw: there is no guard at the API boundary to prevent a negative balance.

A better design:

~~~java
class Account {
    private long balance;

    Account(long openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("negative opening balance");
        }
        this.balance = openingBalance;
    }

    long balance() {
        return balance;
    }

    void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance = Math.addExact(balance, amount);
    }

    void withdraw(long amount) {
        if (amount <= 0 || amount > balance) {
            throw new IllegalArgumentException("invalid withdrawal");
        }
        balance -= amount;
    }
}
~~~

Here:

- The `balance` field is declared `private`, so callers without access cannot directly write `account.balance = -500`.
- The constructor checks the initial state.
- `deposit` requires a positive deposit amount and uses `Math.addExact` to avoid silent overflow.
- `withdraw` requires a positive amount that does not exceed the balance.
- `balance()` allows reading but does not provide an arbitrary write path.

**Key takeaway:** `private` is only an **access-restriction mechanism**; encapsulation takes real effect when all paths that create or modify an object **uphold the class's contract**.

## 2. Distinguishing State, Invariants, and Operation Conditions

For `BankAccount`:

- **State:** `owner`, `balance`.
- **Invariant:** `owner` is valid and meaningful; `balance >= 0`.
- **Precondition** of `withdraw(amount)`: `amount > 0` and `amount <= balance`.
- **Postcondition** when `withdraw` succeeds: `balanceAfter == balanceBefore - amount`, the owner is unchanged, and the invariant still holds.
- **Behavior on failure:** throw an appropriate exception and **leave no partial changes** to the state managed by the method.

An invariant often involves **multiple fields** and cannot be protected simply by validating each setter individually. For example, a date range must satisfy `start <= end`; if there are two independent setters `setStart` and `setEnd`, an intermediate state violating the rule can occur, or one setter cannot be called in a reasonable order.

It is important to distinguish:

| Concept | Example | Meaning |
| --- | --- | --- |
| Field | `long balance` | Where data is stored |
| Access modifier | `private` | Restricts where direct access is allowed |
| Invariant | `balance >= 0` | State property that the class guarantees |
| Precondition | `amount > 0` | Condition required for a call |
| Postcondition | `new balance = old balance + amount` | Result of a successful operation |
| Validation | `if (amount <= 0) throw ...` | Checking inputs/conditions |
| Encapsulation | Expose only `deposit`/`withdraw` | Control over operations is centralized within the abstraction |
| Immutability | Disallow changing state after creation | A stronger design choice; not synonymous with encapsulation |

A class with private fields but unrestricted setters can still violate invariants. An immutable class with no operations that modify state after creation is even easier to reason about regarding invariants, yet its constructor still needs to validate inputs.

## 3. Complete Example: An Account Maintaining a Valid Balance

Save the file **`EncapsulatedAccountDemo.java`**:

~~~java
public class EncapsulatedAccountDemo {
    static final class BankAccount {
        private final String owner;
        private long balance;

        BankAccount(String owner, long openingBalance) {
            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException("owner is required");
            }
            if (openingBalance < 0) {
                throw new IllegalArgumentException("negative opening balance");
            }
            this.owner = owner;
            this.balance = openingBalance;
        }

        String owner() {
            return owner;
        }

        long balance() {
            return balance;
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("deposit must be positive");
            }
            balance = Math.addExact(balance, amount);
        }

        void withdraw(long amount) {
            if (amount <= 0 || amount > balance) {
                throw new IllegalArgumentException("invalid withdrawal");
            }
            balance -= amount;
        }
    }

    public static void main(String[] args) {
        BankAccount account = new BankAccount("Lan", 100);

        System.out.println(account.owner() + ":" + account.balance());
        account.deposit(50);
        account.withdraw(30);
        System.out.println("after operations=" + account.balance());

        try {
            account.withdraw(500);
        } catch (IllegalArgumentException expected) {
            System.out.println("withdraw rejected");
        }

        System.out.println("balance remains=" + account.balance());

        try {
            account.deposit(0);
        } catch (IllegalArgumentException expected) {
            System.out.println("zero deposit rejected");
        }

        System.out.println("valid balance=" + (account.balance() >= 0));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 EncapsulatedAccountDemo.java
java EncapsulatedAccountDemo
~~~

**Exact stdout:**

~~~text
Lan:100
after operations=120
withdraw rejected
balance remains=120
zero deposit rejected
valid balance=true
~~~

**Analysis:**

1. The constructor receives `owner="Lan"` and `openingBalance=100`, and checks them before assignment.
2. `deposit(50)` increases the balance from 100 to 150.
3. `withdraw(30)` decreases it to 120 because 30 is positive and does not exceed 150.
4. `withdraw(500)` is rejected **before subtraction**, so the balance remains 120.
5. `deposit(0)` is rejected by the precondition; the balance remains unchanged.
6. The invariant `balance >= 0` continues to hold across all executed calls.

In the example, `long` represents a non-negative integer quantity, not a complete monetary system. A real banking application must consider currency units, fractional amounts, concurrency, durability, transactions, authorization, and audit logs; object-level encapsulation is only one part.

### 3.1. Why Is There No `setBalance(long)`?

If the class exposes:

~~~java
public void setBalance(long balance) {
    this.balance = balance;
}
~~~

external code can bypass `deposit`/`withdraw` and directly change the balance without a reason or violate business rules. Adding `if (balance < 0)` only prevents negative values; it is **not** enough to ensure every balance change represents a valid transaction.

For state with business meaning, prefer **command methods**:

- `deposit(amount)`: a deposit.
- `withdraw(amount)`: a withdrawal.
- `close()`: close the account when conditions are met.
- `applyInterest(rate)`: apply a clearly defined interest operation.

A simple setter may still be appropriate for configuration data without complex invariants. The goal is not to "forbid all setters", but rather **not to create a path that breaks the object's rules**.

### 3.2. Overflow Also Breaks Invariants

If the code writes `balance += amount` and `balance` is close to `Long.MAX_VALUE`, the addition can overflow and produce a negative number. When a class declares `balance >= 0`, it must account for arithmetic overflow as well, not just check `amount > 0`.

`Math.addExact(balance, amount)` throws `ArithmeticException` if the `long` addition overflows. In the program above, the result is assigned to the field **only after the right-hand expression succeeds**, so the field is not updated when the addition throws an exception.

## 4. Constructors Are the First Boundary Protecting Invariants

If a constructor can create an object in an invalid state, every subsequent method has to guard against many abnormal cases.

An example to avoid:

~~~java
class UserProfile {
    private String username;

    UserProfile() {
        // username defaults to null; the object may not be usable yet.
    }

    void setUsername(String username) {
        this.username = username;
    }
}
~~~

If business rules require username to be non-null/non-blank, callers may forget to call the setter or pass `null`. This is a **pattern capable of creating an object that is not yet valid**.

An alternative design:

~~~java
class UserProfile {
    private final String username;

    UserProfile(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("invalid username");
        }
        this.username = username;
    }

    String username() {
        return username;
    }
}
~~~

The constructor requires the necessary data; when it completes normally, `username` is always valid in this simple model.

**An important note:** a constructor can throw an exception before finishing. The caller receives no reference from the `new` expression along that path; however, side effects that the constructor has already performed on other objects, static fields, logs, etc., are not automatically rolled back.

### 4.1. A Public Constructor Is Not Mandatory

A named static factory can also serve as a controlled entry point:

~~~java
public final class Percentage {
    private final int value;

    private Percentage(int value) {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("percentage out of range");
        }
        this.value = value;
    }

    public static Percentage of(int value) {
        return new Percentage(value);
    }

    public int value() {
        return value;
    }
}
~~~

This is a valid `Percentage.java` file. Callers use `Percentage.of(70)` instead of `new Percentage(70)`. However, **a factory method does not validate automatically**: validation takes effect because the actual implementation invokes the constructor that checks the data.

### 4.2. Verify Every Constructor Overload

If a class has multiple constructors, you must ensure that **every creation path** preserves the invariant. One approach is to use constructor chaining:

~~~java
class TimerSettings {
    private final int timeoutSeconds;

    TimerSettings() {
        this(30);
    }

    TimerSettings(int timeoutSeconds) {
        if (timeoutSeconds <= 0) {
            throw new IllegalArgumentException("timeout must be positive");
        }
        this.timeoutSeconds = timeoutSeconds;
    }
}
~~~

`TimerSettings()` delegates to `TimerSettings(30)` to reuse the shared validation. This code is valid inside an appropriate class file. If any overload omits a required check, the class's entire invariant can still be broken on that creation path.

## 5. Interdependent State: Do Not Check Each Field Individually

For example, a date range consisting of `start` and `end` must always satisfy `start <= end`.

If individual fields can be modified freely, a caller can sequentially create an invalid intermediate state. Using a meaningful operation on **the pair** makes it easier to maintain the invariant.

Save **`DateRangeEncapsulationDemo.java`**:

~~~java
import java.time.LocalDate;
import java.util.Objects;

public class DateRangeEncapsulationDemo {
    static final class DateRange {
        private LocalDate start;
        private LocalDate end;

        DateRange(LocalDate start, LocalDate end) {
            changeRange(start, end);
        }

        void changeRange(LocalDate newStart, LocalDate newEnd) {
            Objects.requireNonNull(newStart, "start");
            Objects.requireNonNull(newEnd, "end");
            if (newStart.isAfter(newEnd)) {
                throw new IllegalArgumentException("start after end");
            }

            // Commit only after all validation has completed.
            this.start = newStart;
            this.end = newEnd;
        }

        String describe() {
            return start + " -> " + end;
        }
    }

    public static void main(String[] args) {
        DateRange range = new DateRange(
                LocalDate.of(2026, 1, 1),
                LocalDate.of(2026, 1, 31));

        System.out.println("initial=" + range.describe());

        try {
            range.changeRange(
                    LocalDate.of(2026, 2, 10),
                    LocalDate.of(2026, 2, 1));
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid range rejected");
        }

        System.out.println("unchanged=" + range.describe());

        range.changeRange(
                LocalDate.of(2026, 2, 1),
                LocalDate.of(2026, 2, 28));

        System.out.println("updated=" + range.describe());
    }
}
~~~

Run:

~~~bash
javac DateRangeEncapsulationDemo.java
java DateRangeEncapsulationDemo
~~~

Output:

~~~text
initial=2026-01-01 -> 2026-01-31
invalid range rejected
unchanged=2026-01-01 -> 2026-01-31
updated=2026-02-01 -> 2026-02-28
~~~

**Why does this approach protect state?**

- The constructor calls the same `changeRange` to check the pair of dates before the object finishes initializing.
- `Objects.requireNonNull` prevents either date from being null.
- `newStart.isAfter(newEnd)` checks the relationship between the two fields.
- All conditions are checked before assigning `this.start` and `this.end`. When any condition fails, both fields retain their previous values.
- `LocalDate` is immutable, so returning or holding a reference to it does not allow callers to modify the date contents from the outside.

**Important limitation:** the checks and the two assignments **do not automatically form an atomic transaction across multiple threads**. The example guarantees consistency after a public operation under single-threaded usage or with proper synchronization; concurrency requires a separate solution.

### 5.1. Why Are `setStart` and `setEnd` Sometimes a Poor API?

Suppose the current range is `[2026-01-01, 2026-01-31]` and the caller wants to change it to `[2026-02-01, 2026-02-28]`:

- Calling `setStart(2026-02-01)` first will temporarily make start > end.
- Calling `setEnd(2026-02-28)` first may still be valid in this example, yet the caller is forced to understand and remember **the order of operations**.
- If the setters do not validate, an invalid state can exist.
- If the setters validate individually without allowing any intermediate step, some transitions whose final result is valid cannot be performed conveniently through the API.

`changeRange(newStart,newEnd)` clearly represents **a single indivisible logical operation**. When it is genuinely necessary to modify one endpoint individually, the method can still validate against the other endpoint so it does not break the invariant, though the contract should state this clearly.

## 6. Workflow-Style State: Expose Behavior, Not the `status` Field

An object should typically only be allowed to change through **defined state transitions**.

For example, an order:

~~~text
CREATED --pay()--> PAID --ship()--> SHIPPED
~~~

A public `setStatus(Status)` setter could allow external code to jump directly from `CREATED` to `SHIPPED`, breaking the invariant "if shipped, it must have been paid beforehand".

Save **`OrderStateDemo.java`**:

~~~java
public class OrderStateDemo {
    enum Status {
        CREATED, PAID, SHIPPED
    }

    static final class Order {
        private final String id;
        private Status status = Status.CREATED;

        Order(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            this.id = id;
        }

        Status status() {
            return status;
        }

        void pay() {
            if (status != Status.CREATED) {
                throw new IllegalStateException("only created orders can be paid");
            }
            status = Status.PAID;
        }

        void ship() {
            if (status != Status.PAID) {
                throw new IllegalStateException("only paid orders can be shipped");
            }
            status = Status.SHIPPED;
        }

        String summary() {
            return id + ":" + status;
        }
    }

    public static void main(String[] args) {
        Order order = new Order("O-1");
        System.out.println("initial=" + order.summary());

        try {
            order.ship();
        } catch (IllegalStateException expected) {
            System.out.println("ship before payment rejected");
        }

        System.out.println("after rejection=" + order.status());

        order.pay();
        System.out.println("after pay=" + order.summary());
        order.ship();
        System.out.println("after ship=" + order.summary());

        try {
            order.pay();
        } catch (IllegalStateException expected) {
            System.out.println("pay again rejected");
        }
    }
}
~~~

Compile/run:

~~~bash
javac OrderStateDemo.java
java OrderStateDemo
~~~

Output:

~~~text
initial=O-1:CREATED
ship before payment rejected
after rejection=CREATED
after pay=O-1:PAID
after ship=O-1:SHIPPED
pay again rejected
~~~

**Analysis:**

1. The `status` field is private and initialized to `CREATED`.
2. `ship()` checks the current state; while it is still `CREATED`, the method throws an exception **before assigning**.
3. `pay()` only permits transitioning from `CREATED` to `PAID`.
4. `ship()` only permits transitioning from `PAID` to `SHIPPED`.
5. After `SHIPPED`, calling `pay()` again is invalid.
6. Callers can read `status()` but cannot directly change `status`, because the class does not expose a setter for the status.

**Design point:** an enum alone does not automatically protect a workflow. The invariant is maintained by **the state transition conditions inside methods** and by blocking external field modification.

Real applications also need payment verification from external services, transactions, retries, and idempotency; an object-level state machine is a model demonstrating state transition rules, not a replacement for an entire order system.

## 7. Value Validation and Business Validation

Different kinds of checks:

| Check Type | Example | Typically Appropriate Location |
| --- | --- | --- |
| Non-null | `Objects.requireNonNull(name)` | Constructor, factory, command |
| Non-empty/non-blank | `name.isBlank()` | When a name is required |
| Value range | `quantity > 0`, `0 <= score <= 100` | Creation/modification API boundary |
| Multi-field relationship | `start <= end` | Simultaneous update method/constructor |
| Current state | `status == CREATED` before `pay` | State transition method |
| Overflow prevention | `Math.addExact` | Bounded integer arithmetic |
| Special contract | `Double.isFinite(x)` before accepting a measurement | Type/command using floating-point |
| Business authorization | Whether the user has permission to perform the operation | Application/service layer, appropriate domain rules |

Not all validation is the job of a setter. Many conditions depend on **the entire model**, another system, or timing. Place checks in the responsible layer, avoiding arbitrary duplication that causes inconsistencies across update paths.

### 7.1. Checking for NaN and Infinity

If a class uses `double` to store a temperature or ratio, the statement `if (value < min || value > max)` **does not reject NaN**, because ordered comparisons with NaN all evaluate to `false`.

Save **`ValidatedTemperatureDemo.java`**:

~~~java
public class ValidatedTemperatureDemo {
    static final class Temperature {
        private final double celsius;

        Temperature(double celsius) {
            if (!Double.isFinite(celsius) || celsius < -273.15) {
                throw new IllegalArgumentException("invalid temperature");
            }
            this.celsius = celsius;
        }

        double celsius() {
            return celsius;
        }
    }

    public static void main(String[] args) {
        Temperature room = new Temperature(25.0);
        System.out.println("room=" + room.celsius());

        try {
            new Temperature(Double.NaN);
        } catch (IllegalArgumentException expected) {
            System.out.println("NaN rejected");
        }

        try {
            new Temperature(-300.0);
        } catch (IllegalArgumentException expected) {
            System.out.println("below absolute zero rejected");
        }

        try {
            new Temperature(Double.POSITIVE_INFINITY);
        } catch (IllegalArgumentException expected) {
            System.out.println("infinity rejected");
        }
    }
}
~~~

Run:

~~~bash
javac ValidatedTemperatureDemo.java
java ValidatedTemperatureDemo
~~~

Output:

~~~text
room=25.0
NaN rejected
below absolute zero rejected
infinity rejected
~~~

This is a simple model for temperature in degrees Celsius. It demonstrates **complete floating-point value-domain checking**, not a comprehensive physics or measurement model. If units, precision, rounding, or uncertainty are needed, the API must describe them.

## 8. A `private` Field Can Still Be Modified Indirectly Through References

An important misconception is thinking "the field is private and final, so external code cannot change the state".

Example:

~~~java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> input) {
        this.members = input;
    }

    java.util.List<String> members() {
        return members;
    }
}
~~~

This snippet compiles, yet it **does not protect the list**:

1. The constructor retains the reference to the caller's mutable list; after creating Team, a caller still holding the `input` variable can call `input.add("X")`.
2. The getter returns a reference to **the internal list itself**, so code receiving the getter's return value can call `team.members().clear()`.
3. `private` prevents accessing the field by name from another class; `final` prevents reassigning **the field reference** after initialization, but **does not** make the list immutable.

This is **representation exposure**: internal state is exposed via a mutable reference.

## 9. Defensive Copying: Protecting Internal Collections

An appropriate design approach for a collection containing **immutable elements** such as `String` is to create or provide an unmodifiable list holding the contents as of initialization time.

Save **`DefensiveTeamDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DefensiveTeamDemo {
    static final class Team {
        private final String name;
        private final List<String> members;

        Team(String name, List<String> input) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            this.name = name;
            this.members = List.copyOf(input);
        }

        String name() {
            return name;
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> external = new ArrayList<>(List.of("Lan"));
        Team team = new Team("Core", external);

        external.add("Minh");

        System.out.println("external=" + external);
        System.out.println("team=" + team.name() + ":" + team.members());

        try {
            team.members().add("An");
        } catch (UnsupportedOperationException expected) {
            System.out.println("getter cannot add");
        }

        System.out.println("team remains=" + team.members());
    }
}
~~~

Compile/run:

~~~bash
javac DefensiveTeamDemo.java
java DefensiveTeamDemo
~~~

Output:

~~~text
external=[Lan, Minh]
team=Core:[Lan]
getter cannot add
team remains=[Lan]
~~~

**Why?**

- `List.copyOf(input)` creates/provides an **unmodifiable** list holding the elements present at creation time.
- Adding `"Minh"` to `external` afterward does not cause `team.members()` to gain a member.
- Callers receiving `team.members()` cannot call `add` either; the collection API throws `UnsupportedOperationException`.
- Because the elements are immutable `String`s, holding references to the String elements does not allow a "member name" to be modified in place.

**Important detail:** `List.copyOf` **does not accept null elements**, and it may reuse an input list that is already a suitable unmodifiable list; **do not assume it always allocates a new list object by identity**. What you should rely on is **the contract regarding data and modifiability**, not `==` comparison.

### 9.1. An Unmodifiable View Differs from an Independent Snapshot

~~~java
List<String> view = java.util.Collections.unmodifiableList(external);
~~~

An `unmodifiableList(external)` is a **view that disallows modification through the view**, but if other code still modifies `external`, the view can **reflect those changes**. It does not by itself protect state from an existing mutable reference source.

With `List.copyOf(external)`, the resulting element structure does not change with subsequent additions, removals, or slot updates to `external` after the call. However, if **the element objects are mutable**, both lists can still share those exact elements.

**Do not conflate "read-only interface", "unmodifiable collection", "snapshot", and "deep immutability".** They guarantee different things.

## 10. Defensive Copying for Arrays

Arrays are mutable objects in Java. If a getter returns the internal array directly, a caller can modify its elements and break rules even though the field holding it is `private final`.

Save **`EncapsulatedScoresDemo.java`**:

~~~java
import java.util.Arrays;

public class EncapsulatedScoresDemo {
    static final class Scores {
        private final int[] values;

        Scores(int[] input) {
            if (input == null || input.length == 0) {
                throw new IllegalArgumentException("scores required");
            }
            for (int score : input) {
                if (score < 0 || score > 100) {
                    throw new IllegalArgumentException("score out of range");
                }
            }
            this.values = input.clone();
        }

        int[] values() {
            return values.clone();
        }

        int highest() {
            return Arrays.stream(values).max().orElseThrow();
        }
    }

    public static void main(String[] args) {
        int[] external = {60, 90};
        Scores scores = new Scores(external);

        external[0] = -100;
        System.out.println("after input changed=" +
                Arrays.toString(scores.values()));

        int[] received = scores.values();
        received[1] = 500;
        System.out.println("after getter changed=" +
                Arrays.toString(scores.values()));

        System.out.println("highest=" + scores.highest());

        try {
            new Scores(new int[] {10, 120});
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid input rejected");
        }
    }
}
~~~

Commands:

~~~bash
javac EncapsulatedScoresDemo.java
java EncapsulatedScoresDemo
~~~

Output:

~~~text
after input changed=[60, 90]
after getter changed=[60, 90]
highest=90
invalid input rejected
~~~

Here, the constructor **checks every element first**, then calls `clone()` on the `int[]` array; the `values()` getter also calls `clone()`. A caller cannot mutate the internal array by retaining the input array or modifying the returned array.

For a one-dimensional `int[]`, the primitive element values are copied independently. If it were a `Student[]` with mutable `Student`s, `clone()` would only copy **references to the Student objects**; to avoid indirect mutation, you must protect the element objects or use an appropriate immutable representation.

### 10.1. Why Might Validating Before Copying Require Additional Concurrency Consideration?

The example above checks `input` and then calls `clone()`. If another thread concurrently modifies **the same input array** between those two steps, the clone could contain unchecked data.

A more robust design when **callers can share or mutate inputs concurrently** requires defining an ownership contract and coordinating appropriate synchronization; you can **copy first, validate on the copy, and then store that exact copy**:

~~~java
int[] candidate = input.clone();
for (int score : candidate) {
    if (score < 0 || score > 100) {
        throw new IllegalArgumentException("invalid score");
    }
}
this.values = candidate;
~~~

This illustrative snippet narrows the window of "validating one array and storing a different snapshot", yet it **does not by itself provide an atomic snapshot** if another party writes to the array concurrently during cloning; you still must ensure callers do not mutate concurrently or apply proper synchronization. The key point is to **validate the exact data you actually intend to store**, rather than checking the source and assuming it will not change.

## 11. Classes with Mutable Nested Objects: Copying Only the Collection Is Not Enough

If a class holds a `List<Address>` and `Address` has `setCity(...)`, `List.copyOf` will make the list structure unmodifiable, but **does not clone the Address elements**. A caller could keep a reference to an original `Address` and modify its city; internal Team/Customer objects could then observe the change indirectly.

### 11.1. Designing with Immutable Value Objects

Save **`ImmutableAddressBookDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ImmutableAddressBookDemo {
    record Address(String city) {
        Address {
            Objects.requireNonNull(city, "city");
            if (city.isBlank()) {
                throw new IllegalArgumentException("blank city");
            }
        }
    }

    static final class AddressBook {
        private final List<Address> addresses;

        AddressBook(List<Address> source) {
            this.addresses = List.copyOf(source);
        }

        List<Address> addresses() {
            return addresses;
        }
    }

    public static void main(String[] args) {
        List<Address> external =
                new ArrayList<>(List.of(new Address("Ha Noi")));

        AddressBook book = new AddressBook(external);
        external.set(0, new Address("Hue"));

        System.out.println("external=" + external.get(0).city());
        System.out.println("book=" + book.addresses().get(0).city());

        try {
            new Address("");
        } catch (IllegalArgumentException expected) {
            System.out.println("blank address rejected");
        }
    }
}
~~~

Run:

~~~bash
javac ImmutableAddressBookDemo.java
java ImmutableAddressBookDemo
~~~

Output:

~~~text
external=Hue
book=Ha Noi
blank address rejected
~~~

**Analysis:**

- `Address` is a Java record with a single component `String city`, where String is immutable.
- The compact constructor `Address { ... }` validates before record initialization completes.
- There are no setters or mutable components on `Address`, so Address objects have immutable content in this simple design.
- `List.copyOf` protects the list structure against subsequent modifications to `external`.
- Combining **immutable elements + an unmodifiable list snapshot** makes it easier for the API to protect state.

**Records do not automatically create deep immutability.** If a record contains a `List<String>` or `int[]`, references to mutable objects can be shared; defensive copies are needed in the constructor/accessors as appropriate. A record is a data modeling tool; it does not automatically guarantee all invariants.

## 12. What Does `final` Protect and What Does It Not Protect?

Table:

| Declaration | Java-Level Guarantee | Not Automatically Guaranteed |
| --- | --- | --- |
| `private int count` | Callers without access cannot directly access it via the API | That public methods will not make count negative |
| `private final int id` | The field is assigned only according to final initialization rules and cannot be arbitrarily reassigned | Whether the ID is valid under business rules |
| `private final List<String> members` | **The field reference** cannot be reassigned after valid initialization | Whether the List object itself is mutable |
| `public final class Config` | No subclass of this class can be created | That Config instances are automatically immutable |
| `static final List<?> CACHED` | The field reference is shared and cannot be reassigned after initialization | Whether the list contents are thread-safe or immutable |

`final` is useful for expressing state that must not be replaced and for reducing update paths, yet the class still needs validation, appropriate visibility, and ownership of mutable subobjects.

### 12.1. Immutable Objects Can Simplify Invariants

If state does not need to change, consider an **immutable class**:

~~~java
final class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("dimensions must be positive");
        }
        this.width = width;
        this.height = height;
    }

    long area() {
        return (long) width * height;
    }
}
~~~

This is a valid class. `width` and `height` are both private final primitives; after creation there is no path to modify them. The constructor ensures each dimension is positive, so every call to `area()` can rely on that invariant.

The multiplication casts to `long` before multiplying to avoid `int` overflow for large valid dimensions. If you also need to guarantee no `long` overflow, you must impose additional bounds or use another checked arithmetic operation.

## 13. Do Not Leave an Object Partially Modified When an Operation Fails

A public method may have to update **multiple fields**. If it assigns one field and then validates another, the object can be left in an inconsistent state when an exception is thrown.

**Error-prone design:**

~~~java
class Rectangle {
    private int width = 2;
    private int height = 3;

    void resizeBad(int newWidth, int newHeight) {
        width = newWidth;
        if (newWidth <= 0 || newHeight <= 0) {
            throw new IllegalArgumentException("invalid dimensions");
        }
        height = newHeight;
    }
}
~~~

With `resizeBad(-5,3)`, `width` has already become -5 **before** the method throws an exception. If the invariant is `width > 0`, the object is left in an invalid state.

**Fix:** validate all inputs before modifying state:

~~~java
class Rectangle {
    private int width = 2;
    private int height = 3;

    void resize(int newWidth, int newHeight) {
        if (newWidth <= 0 || newHeight <= 0) {
            throw new IllegalArgumentException("invalid dimensions");
        }
        width = newWidth;
        height = newHeight;
    }
}
~~~

These are **two alternative implementations** of the `Rectangle` class; you must not declare both classes with the same name in the same package at the same time. In the second version, validation fails before assigning fields, so the previous state is preserved.

For more complex operations (calling external services, writing files/DB, multiple side effects), "validate first, then assign" may **not be enough** to achieve true transactions/rollback. Still, this is the foundational principle at the object level: **compute and validate a candidate state, and commit only when valid**.

### 13.1. Exceptions for Input and State

- `IllegalArgumentException` is usually appropriate when an **argument value** does not satisfy the method's condition.
- `NullPointerException` via `Objects.requireNonNull` can clearly express a non-null contract.
- `IllegalStateException` is appropriate when the object's **current state** does not permit the operation (`ship` before `pay`).
- `ArithmeticException` from `Math.addExact` signals overflow; it can be translated into a clearer domain exception if the API contract specifies one.

Do not catch all exceptions and ignore them: the caller will assume the operation succeeded even though nothing actually changed. Clearly specify both **the success path** and **the failure path**.

## 14. Invariant Updates and Concurrency: Encapsulation Does Not Guarantee Thread Safety

Protecting a field with `private` does not automatically make update operations safe when **multiple threads** share the same object.

For example, a counter:

~~~java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
~~~

Even though the field is private and callers only go through methods, `value++` is not an atomic operation under the Java Memory Model. If multiple threads call `increment` concurrently, a race condition can occur and increments can be lost.

A simple way to protect a counter object from concurrent updates is to use appropriate synchronization:

~~~java
class Counter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int value() {
        return value;
    }
}
~~~

This is **an alternative implementation** of the `Counter` class. Both the read and write in this example use the instance's same intrinsic monitor. Depending on the problem, you can choose `AtomicInteger`, locks, or immutable state replaced as a whole.

For objects with multiple fields and coordinated invariants, you must ensure that **the entire check + update operation** is synchronized as a single unit when shared across multiple threads; synchronizing only getters or relying only on final references may not be sufficient.

**Do not interpret "encapsulation" as "automatically thread-safe" or "self-protecting against reflection, serialization, or code running with different privileges".** It is a language-level design/API boundary, not a comprehensive security or concurrency solution.

## 15. When Should You Provide Getters, Setters, and Command Methods?

There is no need to mechanically turn every field into `getX()/setX()`.

A **getter** is appropriate if callers genuinely need to know a piece of state. Still, consider:

- Returning a primitive value or an immutable object usually carries low risk.
- Returning a reference to an internal mutable collection/array can break encapsulation.
- An aggregate getter such as `availableBalance()` is sometimes more appropriate than exposing multiple individual fields.
- A getter can compute a result from state; it does not necessarily have to return a field directly.

A **setter** is appropriate when assigning a value is **independent and safe**, for example changing an optional note according to the contract. However:

- For a balance, use `deposit`/`withdraw` instead of `setBalance`.
- For a date range, use `changeRange(start,end)` to validate the relationship between the two fields.
- For a workflow, use `pay`/`ship` instead of an arbitrary `setStatus`.

A **command method** describes a valid action: the caller requests what to do, and the class takes responsibility for how to do it, what to validate, and which invariants to preserve.

### 15.1. Design the API Around Behavior, Not Storage Structure

For example, instead of exposing:

~~~java
public int quantity;
public boolean reserved;
~~~

an inventory object can expose `reserve(int amount)`, `release(int amount)`, and `availableQuantity()`, and enforce `0 <= reservedQuantity <= stockQuantity` according to its contract.

When the class's internals change from `int` fields to a value object or another structure, the business API can remain unchanged. This is a major maintainability benefit of encapsulation: **callers depend on behavior, not on field layout**.

## 16. Inheritance and the Risk of Breaking Invariants from Subclasses

If a class has `protected` fields that subclasses can modify directly, a subclass can bypass the superclass's validation.

A risky example:

~~~java
class BaseAccount {
    protected long balance;
}
~~~

A subclass in a valid access context can write `balance = -100`, breaking the invariant that the superclass intended to maintain.

A safer design is:

- Keep fields `private`.
- Provide protected/public **operations with explicit validation** if subclasses need extension points.
- Avoid calling overridable instance methods from a constructor when the subclass object is not yet fully initialized, unless the design has a very explicit safeguard.
- Consider a `final class` or composition if inheritance adds no value.

**Inheritance does not necessarily have to be forbidden:** extension points must be chosen carefully so that every subclass still honors the superclass contract. Liskov substitution is a broader principle: if a subclass alters behavior in a way that breaks invariants or the contract, the shared abstraction loses reliability.

## 17. Public API, Serialization, and Reflection

A class with private fields **does not guarantee** that every framework or runtime mechanism is prevented from instantiating or modifying state via special paths:

- Some serializers/ORMs can create instances and restore state through their own mechanisms, potentially bypassing normal public constructors.
- Reflection with appropriate access permissions or module configuration can access non-public members under specific conditions.
- Deserialization or framework-driven population may require validation after data restoration.

Therefore, for objects with critical invariants, you must examine **all creation and restoration paths** in the runtime environment, not just `new` calls in application source code.

Conversely, you should not exaggerate by claiming that private is completely useless: it remains a strong tool for keeping most callers within the designed API, supporting maintainability and compile-time checks.

## 18. How to Test Invariants and Encapsulated APIs

For a class that protects state, test **both success and failure cases**.

### 18.1. Scenario Table for `BankAccount`

| Scenario | Expected Outcome |
| --- | --- |
| Create with initial balance 100 | Succeeds, balance = 100 |
| Create with negative balance | Throws an exception |
| `deposit(50)` | Balance increases by exactly 50 |
| `deposit(0)` or negative | Rejected, balance remains unchanged |
| `withdraw(30)` from 150 | Balance = 120 |
| `withdraw(500)` from 120 | Rejected, balance remains 120 |
| Deposit causing `long` overflow | Throws an exception, no field assignment after overflow |
| Caller attempts `account.balance = -1` | Does not compile from code outside private access |
| Call state-reading method | Returns consistent values according to the contract |

### 18.2. Scenario Table for Mutable References

| Scenario | Expectation for a Protected API |
| --- | --- |
| Caller modifies the list passed to the constructor | Internal state is not automatically affected if an appropriate snapshot is stored |
| Caller calls `getterList().add(...)` | Cannot mutate internal state through the getter if an unmodifiable list is returned |
| Caller modifies the input array after construction | Internal array preserves an independent snapshot |
| Caller modifies the array returned by the getter | Internal array does not change if the getter clones it |
| List contains mutable elements still retained by the caller | **Risk of sharing** unless elements are immutable or defensively copied |
| Call update with two fields violating their relationship | Operation is rejected before committing |
| Multiple threads update the same object | Must verify the concurrency contract separately |

### 18.3. Assertions and Automated Tests

Java has `assert`, but by default assertions may **not be enabled** at runtime without `-ea`. You should not use `assert` as a substitute for public API validation on potentially invalid data coming from users/systems.

For example:

~~~java
if (amount <= 0) {
    throw new IllegalArgumentException("amount must be positive");
}
~~~

is appropriate for protecting the invariant **even when assertion mode is disabled**.

In a real project, you can use JUnit to test:

- Initialization paths.
- Every method that can modify state.
- Boundary inputs: `0`, negative, large, null, blank, NaN, and overflow.
- State before and after an exception.
- Defensive copies and unintended aliases.
- Invalid sequencing/transitions.
- Concurrency scenarios if the object guarantees thread safety.

## 19. Common Mistakes to Avoid

| Mistake/Misconception | Problem | How to Handle |
| --- | --- | --- |
| "Encapsulation = just adding private to fields." | Public methods can still corrupt state | Design invariants and validate every creation/update path |
| Creating an object that requires a name while the constructor leaves the name null | The object is invalid immediately after initialization | Require the data and validate in the constructor/factory |
| Every field has a public setter | Callers can bypass business behavior | Use command methods with clear meaning and preconditions |
| A setter for one field breaks its relationship with another field | Cross-field invariants can be lost | Perform coordinated updates or use immutable replacement |
| Validating after already assigning the first field | An exception leaves a half-updated state | Validate the candidate state before committing |
| `balance += amount` without considering overflow | The field can overflow into a negative number | Use `Math.addExact`/intentional bounds |
| `private final List` with a getter returning a mutable list | Exposes a mutable representation | Snapshot/unmodifiable API/defensive copy |
| Using `List.copyOf` with mutable elements and assuming a deep copy | Elements can still be modified through aliases | Use immutable elements or necessary deep copying |
| An `int[]` array getter returns the original array | Callers alter data bypassing validation | Clone on input and output if the contract requires independence |
| Validating an array and then storing a clone from a concurrent mutable source | There is a window where the source can be modified | Copy and validate the data to be stored; define the concurrency contract |
| Marking a field `final` and assuming the object is immutable | Final only protects field reference assignment | Protect mutable referents or design an immutable class |
| Private `status` enum while exposing `setStatus(any)` | Callers bypass the workflow | Use validated state-transition methods |
| A method catches an exception and silently ignores it | Callers assume the operation succeeded | Report errors per contract or return an explicit result |
| Exposing `protected` mutable fields arbitrarily for subclasses | Subclasses break invariants | Private fields, protected validated hooks |
| Assuming private makes an object thread-safe | Mutations can still race | Design synchronization/atomicity according to the contract |
| Using `assert` instead of public method validation | Assertions can be disabled | Use always-active checks and appropriate exceptions |
| Testing only the happy path | Does not prove the invariant holds on failure | Test invalid inputs and state before/after exceptions |

## 20. Checklist for Designing a Class with Invariants

When starting to create a new Java class, answer these questions in order:

1. **What does the object represent?** Is there a clear abstraction?
2. **What is the minimum state that needs to be stored?** Are there any redundant fields or ones that lead to two sources of truth?
3. **Which invariants must always hold** after a constructor or public command completes normally?
4. **Which inputs are invalid?** Null, blank, negative, out-of-range, NaN, overflow, or inconsistent combinations?
5. **How many creation paths exist?** Do all constructors and factories invoke shared validation?
6. **Who is allowed to modify state?** Can fields be kept private with only domain operations exposed?
7. **At which step can operations fail?** Can candidates be checked/computed before assigning fields?
8. **Are there cases where multiple fields transition together?** Should a command update the whole group rather than using independent setters?
9. **Do any mutable references enter or leave the object?** Collections, arrays, Date, builders, or user-defined mutable types?
10. **What is the ownership model?** Does the class keep a snapshot or intentionally share an instance? Are callers allowed to modify returned data?
11. **Is an immutable object needed?** Can you use private final primitives/immutable values, records, or methods returning new objects?
12. **Could a subclass break invariants?** Should the class be final, or should a controlled protected API be designed?
13. **Is the object shared across threads?** If so, how should cross-field checks and updates be synchronized or made atomic?
14. **Are there framework or serialization creation paths?** Ensure restored data is validated via an appropriate mechanism.
15. **Do tests cover failure behavior and post-error state?** Not just printing output for valid calls.

A well-encapsulated class helps callers **use the API correctly by default** and makes it **hard to put the object into an invalid state**. Documentation and method names are just as important as access modifiers.

## 21. Self-Check Questions with Answers

**Question 1.** Class `Account` has `public long balance;`. Why does having a `withdraw` method that checks the balance still fail to guarantee the invariant?  
**Answer:** Callers can still write `account.balance = -100` directly, bypassing the checking method.

**Question 2.** If `balance` is changed to `private` but an unchecked setter `setBalance(long)` is added, has the class protected its invariant?  
**Answer:** No. Callers can still create a negative balance through the exposed API. `private` only blocks direct field access.

**Question 3.** Why must a constructor validate required data?  
**Answer:** So the object finishes initialization in a valid state, without forcing every caller to remember corrective steps after creation.

**Question 4.** Does `final List<String> members` make the list immutable?  
**Answer:** No. `final` only prevents reassigning the field reference; if the list is mutable, elements can still be added or removed through an alias.

**Question 5.** Why does `List.copyOf(input)` help protect a String list against the caller adding elements to `input` after construction?  
**Answer:** It provides an unmodifiable list with the elements present at the time of the call; subsequent structural changes to the input list do not automatically change the stored list.

**Question 6.** If a list contains mutable `Address` objects, does `List.copyOf` create a deep copy?  
**Answer:** No. References to the Address elements can still be shared. Immutable elements or deep defensive copies are needed if state isolation is desired.

**Question 7.** With `int[] input`, why should a class that needs to keep an independent snapshot clone it in both the constructor and the getter?  
**Answer:** Because arrays are mutable; without copying, a caller could retain and modify the input array or modify the array returned by the getter.

**Question 8.** Why can two setters `setStart`/`setEnd` make it difficult to guarantee the invariant `start <= end`?  
**Answer:** They allow modifying one field at a time, which can create invalid intermediate states. A method that updates the date pair can validate the entire relationship before committing.

**Question 9.** What should Order's `ship()` method do when the status is still `CREATED`?  
**Answer:** Reject it before changing state (for example with `IllegalStateException`); the Order remains `CREATED` according to the contract.

**Question 10.** If `deposit` validates that the amount is positive, can the invariant `balance >= 0` still be broken if `long` addition overflows?  
**Answer:** Yes, if plain unchecked `+` is used. `Math.addExact` throws an exception on overflow, preventing an incorrectly computed value from being assigned to balance.

**Question 11.** Why is `Double.isFinite` useful when validating measurements?  
**Answer:** It excludes NaN and infinity, values that can slip past range comparisons in unexpected ways.

**Question 12.** Does `final class` automatically guarantee that all objects of the class are immutable?  
**Answer:** No. `final class` prevents inheritance; it does not prevent modifying fields or mutable referenced objects.

**Question 13.** Why does checking inputs first before updating fields help with exception safety?  
**Answer:** If an input is invalid, the method throws an exception before modifying state. However, for side effects outside the object or under concurrency, additional measures are needed.

**Question 14.** Are `private int count` and the method `increment() { count++; }` automatically thread-safe?  
**Answer:** No. `count++` is not atomic when multiple threads operate concurrently; private does not provide synchronization.

**Question 15.** Why can keeping fields private help evolve an implementation with minimal disruption to callers?  
**Answer:** Callers depend on public behavior rather than field layout; the class can change how data is stored while preserving method contracts.

**Question 16.** When is a simple setter still appropriate?  
**Answer:** When directly assigning an attribute is a valid operation with clear validation and does not bypass an invariant; not every class needs complex domain commands.

**Question 17.** Why might a framework that instantiates objects via non-standard paths require separate validation?  
**Answer:** Because some object restoration mechanisms may not invoke the constructor API the way normal callers do; invariants still need to be protected according to the contract/framework.

**Question 18.** What should be verified after a command is rejected?  
**Answer:** The proper exception or error result and that **the object's state remains valid**, ideally unchanged for operations committed to fail without state change.

## References

- Java Language Specification, [`6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): access control for classes and members.
- Java Language Specification, [`8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): field modifiers and `final`.
- Java Language Specification, [`8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): initializing objects through constructors.
- Java Platform API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable list snapshot per contract.
- Java Platform API, [`Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)): integer addition overflow check.
- Java Platform API, [`Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): non-null check.

## Key Takeaways

**Effective encapsulation = keeping state inside a well-bounded abstraction + exposing only operations that maintain validity rules**. A `private` field is the first step, but it is not enough: constructors must create valid objects; public commands must validate and preserve invariants; getters and constructors must not unintentionally expose mutable representations. When updating multiple fields, **validate candidates before committing**; when sharing arrays/collections, consider **defensive copying**, shallow vs. deep sharing, and ownership.

Do not conflate `private`, `final`, immutability, thread safety, or system security. They address different requirements. A well-designed Java class makes it easy for callers to do the right thing and hard to do the wrong thing: **what matters most is not how much data is hidden, but that every public path respects the object's contract**.
