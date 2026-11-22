# Data Validation and Error Handling in Java Constructors

A **constructor** is where the initial state of an object is established. In many classes, it is also the best boundary for rejecting data that cannot form a valid object: an empty name, a negative quantity, a reversed time range, or a required reference that is `null`.

For example, if an account must always have an owner and a non-negative initial balance, the constructor should not silently accept `new Account("", -100)` and wait for other methods to detect the error. The goal is that **when the `new` call completes normally, the object already satisfies the invariants promised by the class**.

However, "validating data in a constructor" does not mean placing every business rule and every I/O operation inside it. This lesson distinguishes:

- **Parameter preconditions**: what form must the input data take?
- **Object invariants**: what state must hold true after creation and after each update behavior?
- **Normalization**: should whitespace be stripped, units converted, or copies of mutable data created?
- **Construction failure**: how do exceptions affect `new`, assignment, and side effects that have already occurred?
- **Error contract**: should `IllegalArgumentException`, `NullPointerException`, a checked exception, or another error type be used?
- **Testing**: proving that the constructor accepts valid data and rejects invalid data in a predictable way.

The complete programs below use Java 17+ and include expected stdout for comparison.

## 1. A Constructor Is the Boundary for Creating Valid State

Consider a class that does not guard its data:

~~~java
class Account {
    String owner;
    long balanceCents;

    Account(String owner, long balanceCents) {
        this.owner = owner;
        this.balanceCents = balanceCents;
    }
}
~~~

This is an **illustrative class**, not a standalone program. All of the following calls are accepted by this constructor:

~~~java
new Account(null, -500);
new Account("   ", 0);
~~~

If the design requires the account owner's name to have content and the balance to be non-negative, both objects are **invalid under business rules**, even though the compiler reports no errors.

A validated version:

~~~java
class Account {
    private final String owner;
    private long balanceCents;

    Account(String owner, long balanceCents) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner is required");
        }
        if (balanceCents < 0) {
            throw new IllegalArgumentException("balance must be >= 0");
        }

        this.owner = owner.strip();
        this.balanceCents = balanceCents;
    }
}
~~~

The rules are enforced before the constructor finishes:

1. `owner` must not be `null`.
2. `owner` must not be empty or consist only of whitespace according to `String.isBlank()`.
3. `balanceCents` must be non-negative.
4. `owner.strip()` removes leading and trailing Unicode whitespace as defined by the API, producing a consistent stored value.

**An invariant** is not a check that applies only at construction time. If the object has `withdraw`, `deposit`, or `rename` methods, those update methods must also preserve the invariant. The constructor only establishes the **initial state foundation**.

### A Constructor Is Not an Ordinary Method

A constructor:

~~~java
Account(String owner, long balanceCents) {
    // ...
}
~~~

has the **same name as the class** and **declares no return type**, not even `void`. When `new Account(...)` completes normally, the **`new` expression** yields a reference to the new object; the constructor does not `return` an object.

A constructor can throw an exception:

~~~java
throw new IllegalArgumentException("balance must be >= 0");
~~~

When an exception escapes construction, the `new` call **does not complete normally**, so an external assignment relying on the result of `new` may not be executed.

## 2. Types of Conditions to Check

Before coding, write down the **validity conditions** of the object. Each condition should have a clear business reason or API-protection reason.

| Check Type | Example | Notes |
| --- | --- | --- |
| Required non-`null` | `name`, `address`, `configuration` | Choose a clear policy for null |
| Non-blank string | `!name.isBlank()` | `""` and whitespace-only strings are not like ordinary strings |
| Numeric range | `quantity > 0`, `age >= 0` | Consider boundary values and overflow |
| Fixed set of values | `Status`, `DeliveryMode` | Use an enum when appropriate, and still handle null |
| Relationship between fields | `start <= end` | Do not validate only each parameter individually |
| Valid collection | Non-null, non-empty, elements meet conditions | Define whether null elements are allowed |
| Format/normalization | Product code, region code, display name | Do not mistake a simple heuristic for a complete standard rule |
| Consistency with dependencies | Configuration uses the same unit, same domain | May require a factory/service instead of a constructor |
| Default values | Empty notes, sensible limits | Avoid defaults that cause the object to have the wrong meaning |

For example, `age` being within `0..150` is just a **rule for a specific problem**, not a fixed limit of Java or all applications. Do not introduce arbitrary limits into a widely used type unless the business requires them.

### Distinguishing Required, Optional, and Missing States

Suppose a `Person` has a required `displayName` and an optional `nickname`. There are at least three possible policies for the nickname:

- Accept `null` as "no nickname yet" and store `null` as-is.
- Accept `null` but **normalize it to an empty string**.
- Reject null, forcing the caller to provide a separate value representing absence.

There is no single right approach for every API. What matters is choosing **a consistent contract** and not forcing callers to guess. For required data, rejecting early often reduces bugs far from their source.

## 3. Complete Example: Constructor Validation and Preserving Invariants After Creation

Save as **`ConstructorValidationDemo.java`**:

~~~java
public class ConstructorValidationDemo {
    static final class Account {
        private final String owner;
        private long balanceCents;

        Account(String owner, long initialBalanceCents) {
            if (owner == null) {
                throw new IllegalArgumentException("owner must not be null");
            }

            String normalizedOwner = owner.strip();
            if (normalizedOwner.isEmpty()) {
                throw new IllegalArgumentException("owner must not be blank");
            }
            if (initialBalanceCents < 0) {
                throw new IllegalArgumentException("initial balance must be >= 0");
            }

            this.owner = normalizedOwner;
            this.balanceCents = initialBalanceCents;
        }

        void deposit(long amountCents) {
            if (amountCents <= 0) {
                throw new IllegalArgumentException("deposit must be positive");
            }

            balanceCents = Math.addExact(balanceCents, amountCents);
        }

        String summary() {
            return owner + ": " + balanceCents + " cents";
        }
    }

    public static void main(String[] args) {
        Account account = new Account("  Mai  ", 12_000);
        account.deposit(5_500);
        System.out.println(account.summary());

        try {
            new Account(null, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected name: " + ex.getMessage());
        }

        try {
            new Account("An", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected balance: " + ex.getMessage());
        }

        try {
            account.deposit(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected deposit: " + ex.getMessage());
        }

        System.out.println("Still: " + account.summary());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ConstructorValidationDemo.java
java ConstructorValidationDemo
~~~

Stdout:

~~~text
Mai: 17500 cents
Rejected name: owner must not be null
Rejected balance: initial balance must be >= 0
Rejected deposit: deposit must be positive
Still: Mai: 17500 cents
~~~

Explanation:

1. `new Account("  Mai  ", 12_000)` succeeds; the constructor normalizes `"  Mai  "` to `"Mai"`.
2. `deposit(5_500)` is valid, increasing the balance to `17_500`.
3. `new Account(null, 0)` throws `IllegalArgumentException` with a message clearly identifying the invalid field.
4. `new Account("An", -1)` is rejected by the balance condition.
5. `deposit(0)` is rejected **before** updating the field; the balance remains unchanged.
6. `Math.addExact` throws `ArithmeticException` if the `long` addition overflows, instead of producing an unexpected overflowed result.

An object created validly can still become invalid if update methods skip validation. Therefore, define the invariant and check whether both the constructor **and every state-changing behavior** maintain it.

**Currency units:** The example uses `long balanceCents` and refers to `cents`. This is just a model representing monetary amounts in the smallest integer unit. Real systems must define the currency, subdivision scale, and rounding rules; do not arbitrarily use `double` for exact accounting.

## 4. Choosing an Exception Appropriate to the Cause

There is no single exception required for every constructor. Common choices include:

| Exception | When Appropriate | Example |
| --- | --- | --- |
| `IllegalArgumentException` | The argument does not satisfy the constructor contract | Negative quantity, empty code, reversed date range |
| `NullPointerException` | The input must not be null according to the API contract | `Objects.requireNonNull(name, "name")` |
| `NumberFormatException` | A string cannot be parsed into a properly formatted number | `Integer.parseInt("abc")` |
| `ArithmeticException` | An arithmetically invalid operation | `Math.addExact` detects overflow |
| Checked exception such as `IOException` | The constructor actually performs an operation that can produce an I/O error | Opening/reading a data source |
| `IllegalStateException` | The operation is invalid due to the **current state**, typically for methods rather than constructor arguments | A closed service cannot continue running |

`NumberFormatException` is a subclass of `IllegalArgumentException`. Both `NullPointerException` and `IllegalArgumentException` are unchecked exceptions in the `RuntimeException` hierarchy. They do not need to be declared in a `throws` clause under checked exception rules.

### `IllegalArgumentException` or `NullPointerException` for Null Arguments?

Both policy styles exist:

~~~java
if (name == null) {
    throw new IllegalArgumentException("name is required");
}
~~~

or:

~~~java
this.name = java.util.Objects.requireNonNull(name, "name");
~~~

`Objects.requireNonNull` throws `NullPointerException` if `name` is null. Choose a policy consistent with the API; if a public API has documentation specifying the exception type, test against that exact contract. **Do not assume that Java requires every null parameter to throw a fixed exception type.**

The snippets above are **illustrative fragments** that must be placed inside an appropriate constructor; `this.name` requires the class to have a corresponding field.

### Error Messages Should Be Specific

A good message clearly states the parameter and condition, for example:

- `"quantity must be positive"`;
- `"start must not be after end"`;
- `"owner must not be blank"`.

An overly generic message such as `"invalid"` makes it hard to identify the source of an error when a constructor has multiple parameters. However, you should not include passwords, access tokens, sensitive data, or full user input in exception messages and logs.

## 5. Checking for Null, Empty Strings, and Normalization

Strings have different states:

| Value | `value == null` | `value.isEmpty()` if non-null | `value.isBlank()` if non-null |
| --- | --- | --- | --- |
| `null` | true | Must not be called | Must not be called |
| `""` | false | true | true |
| `"   "` | false | false | true |
| `" Mai "` | false | false | false |
| `"Mai"` | false | false | false |

**Important:** Do not call `name.isBlank()` **before** handling the possibility that `name == null`, because calling a method on null will cause a `NullPointerException`.

`String.strip()` removes leading and trailing whitespace characters according to `Character.isWhitespace`, differing from `String.trim()` in the range of characters handled. `isBlank()` is also based on Java's definition of Unicode whitespace. They are useful for ordinary names, but are not a comprehensive Unicode normalization solution for all data.

A validation and normalization helper can be written as:

~~~java
static String normalizeName(String name) {
    if (name == null) {
        throw new IllegalArgumentException("name is required");
    }

    String normalized = name.strip();
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException("name must not be blank");
    }

    return normalized;
}
~~~

This is an **illustrative method**. It can be called in the constructor:

~~~java
this.name = normalizeName(name);
~~~

If multiple classes need the same naming policy, validation can be placed in a dedicated value object or a utility with a clear contract. However, avoid creating a generic helper and accidentally sharing rules across names with different requirements, such as usernames, personal names, filenames, and identifiers.

### Normalization Must Have a Business Reason

Some fields **should not be automatically stripped or case-converted**, such as passwords, whitespace-sensitive codes, digital signature data, or strings used as byte-exact keys. If the constructor modifies input content, clearly specify the rule so callers are not surprised.

## 6. Validating Multiple Related Parameters

Some objects are only valid when their parameters **have the right relationship**, even if each parameter is valid on its own.

Save the file **`DateRangeValidationDemo.java`**:

~~~java
import java.time.LocalDate;
import java.util.Objects;

public class DateRangeValidationDemo {
    static final class DateRange {
        private final LocalDate start;
        private final LocalDate end;

        DateRange(LocalDate start, LocalDate end) {
            this.start = Objects.requireNonNull(start, "start");
            this.end = Objects.requireNonNull(end, "end");

            if (end.isBefore(start)) {
                throw new IllegalArgumentException("end must be >= start");
            }
        }

        long daysInclusive() {
            return java.time.temporal.ChronoUnit.DAYS
                    .between(start, end) + 1;
        }
    }

    public static void main(String[] args) {
        DateRange range = new DateRange(
                LocalDate.of(2026, 3, 10),
                LocalDate.of(2026, 3, 12));

        System.out.println("Days: " + range.daysInclusive());

        try {
            new DateRange(
                    LocalDate.of(2026, 3, 12),
                    LocalDate.of(2026, 3, 10));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DateRangeValidationDemo.java
java DateRangeValidationDemo
~~~

Stdout:

~~~text
Days: 3
Rejected: end must be >= start
~~~

Although `start` and `end` are both valid `LocalDate` values, the constructor rejects them when `end` is before `start`. The example defines the range as **inclusive on both ends**, so `daysInclusive()` adds 1. Another system might use a half-open interval `[start, end)`; in that case, the condition and day-counting logic must be adjusted according to the contract.

**Design note:** The `DateRange` type groups two parameters that share an invariant relationship. Methods using `DateRange` can trust that a successfully constructed object does not contain an end date earlier than its start date, provided the class does not expose any way to mutate state that breaks this condition.

### Validate Before Field Assignment or After Assignment?

In `DateRange`, the two fields are assigned and then the relational condition is checked. If the constructor throws an exception, the object is not returned normally to the caller. This style is valid when **`this` is not published inside the constructor** and there are no side effects other than setting fields. However, validating all data using local variables **before assigning fields** often makes code easier to understand and reduces the risk of exposing observable intermediate state if the class is complex.

There is no Java rule requiring every validation check to happen before every assignment. The important requirement is that an object published after a successful constructor must be valid and must not leak an incomplete instance.

## 7. Constructor Failure: Does the External Assignment Take Place?

An exception thrown from a constructor and not handled within the initialization chain causes **the `new` expression to terminate abruptly**. The caller does not receive a reference normally returned by this expression.

Save **`ConstructionFailureDemo.java`**:

~~~java
public class ConstructionFailureDemo {
    static final class User {
        private final String name;

        User(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("invalid name");
            }
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        User current = new User("Original");

        try {
            current = new User(" ");
            System.out.println("assignment completed");
        } catch (IllegalArgumentException ex) {
            System.out.println("constructor failed");
        }

        System.out.println("current=" + current.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructionFailureDemo.java
java ConstructionFailureDemo
~~~

Stdout:

~~~text
constructor failed
current=Original
~~~

Explanation:

1. `current` already points to a valid User named `Original`.
2. On the right-hand side `new User(" ")`, the constructor detects a whitespace-only name and throws `IllegalArgumentException`.
3. Because the right-hand side does not complete normally, the assignment `current = ...` does not occur.
4. `current` still points to the old object; it neither becomes null nor switches to the failed instance.
5. The `assignment completed` line is not executed.

Do not conclude that Java always "rolls back" everything when a constructor fails. **Not completing a reference assignment is very different from undoing side effects that have already occurred**.

### An Object May Already Be Under Construction

The JVM may have already allocated space and executed part of an initializer or constructor before the exception occurs. In the normal case, the caller does not receive a reference from the failed `new` expression. However, if the constructor **leaks `this`** to a static collection, callback, or thread, other code may hold a reference to the incompletely initialized object. This is a very important reason not to publish `this` prematurely.

## 8. Side Effects in Constructors Are Not Automatically Undone

A constructor can modify a static field, write logs, add data to a registry, or call a service. If it subsequently throws an exception, the side effects that already occurred **do not disappear on their own**.

Save **`ConstructorSideEffectDemo.java`**:

~~~java
public class ConstructorSideEffectDemo {
    static final class Registration {
        private static int attempts;
        private static int successful;

        private final String code;

        Registration(String code) {
            attempts++;

            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code is required");
            }

            this.code = code;
            successful++;
        }

        static int attempts() {
            return attempts;
        }

        static int successful() {
            return successful;
        }

        String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        Registration ok = new Registration("A1");

        try {
            new Registration("");
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected invalid code");
        }

        System.out.println("Valid code: " + ok.code());
        System.out.println("Attempts: " + Registration.attempts());
        System.out.println("Successful: " + Registration.successful());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorSideEffectDemo.java
java ConstructorSideEffectDemo
~~~

Stdout:

~~~text
Rejected invalid code
Valid code: A1
Attempts: 2
Successful: 1
~~~

`attempts` is incremented at the beginning of the constructor, so it counts failed constructions as well. `successful` is incremented only after the data has been validated and the required field assigned. Both static fields belong to the runtime class, not to individual instances. The example runs sequentially; `++` on a static field is not inherently thread-safe.

**Takeaway:** If you want to count the number of **successfully created** objects, do not increment the counter before validation steps that might fail. For complex constructors with later steps that can still throw exceptions, incrementing at the end also requires carefully defining what "success" means, especially with external side effects.

### Avoid Performing External Transactions in Constructors When Possible

Opening connections, writing to a database, sending emails, or updating system-wide state directly inside a constructor makes error handling hard to manage:

- Data may be partially written before the constructor throws an exception.
- The caller does not receive an object, yet the external operation has already occurred.
- Retrying `new` can cause duplicate writes.
- Testing the constructor becomes environment-dependent.

For I/O or transactional tasks, it is usually better to create a valid configuration object first, and then execute a clearly named action with its own error and rollback strategy. There is no absolute rule forbidding constructors from performing I/O, but ownership, cleanup, and exception contracts must be carefully considered.

## 9. Handling Exceptions Inside or Outside the Constructor?

There are two levels of decision:

### Inside the Constructor: Detect and Reject Invalid Data

~~~java
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
~~~

This is a simple and effective pattern: the object is not successfully created with a `quantity` that violates the condition.

### Outside the Constructor: Decide the Recovery Policy

~~~java
try {
    Order order = new Order(quantity);
    save(order);
} catch (IllegalArgumentException ex) {
    System.out.println("Please correct the input");
}
~~~

This is an **illustrative snippet**, assuming `Order` and `save` are appropriately defined. The orchestration layer or UI layer can prompt for re-entry, display a user-friendly message, or reject the request. A constructor **should not decide how to display GUI/HTTP messages** if the class only describes a domain object.

### Do Not Swallow Exceptions and Keep an Invalid Object

Faulty pattern:

~~~java
class UnsafeItem {
    private int quantity;

    UnsafeItem(int quantity) {
        if (quantity <= 0) {
            System.out.println("Warning: invalid quantity");
        }
        this.quantity = quantity;
    }
}
~~~

This class allows creating `new UnsafeItem(-3)` even though it prints a warning. If the invariant requires a positive quantity, logging is not a sufficient error-handling method to protect correctness.

Only "fix" invalid data with a default when **the contract explicitly states** that the data is permitted to be normalized. For instance, a `null` value for an optional note may become an empty string; a null required identifier should not be silently turned into a random code.

## 10. Constructor Chaining: Where to Validate When There Are Multiple Overloads?

When a class has multiple constructors, it is easy to introduce a bug where **each overload validates differently**, leading to objects of the same class having inconsistent validity conditions.

In Java 17, a constructor that calls another constructor using `this(...)` must place that call as **the first statement** of the constructor. Therefore, you cannot write a few validation statements and then call `this(...)` in the same constructor under standard Java 17 syntax.

A clear design is to delegate all overloads to one primary constructor:

Save the file **`ConstructorChainingValidationDemo.java`**:

~~~java
public class ConstructorChainingValidationDemo {
    static final class Ticket {
        private final String code;
        private final int quantity;

        Ticket(String code) {
            this(code, 1);
        }

        Ticket(String code, int quantity) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code is required");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            this.code = code;
            this.quantity = quantity;
        }

        String summary() {
            return code + " x" + quantity;
        }
    }

    public static void main(String[] args) {
        System.out.println(new Ticket("VIP").summary());
        System.out.println(new Ticket("STD", 3).summary());

        try {
            new Ticket("BAD", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorChainingValidationDemo.java
java ConstructorChainingValidationDemo
~~~

Stdout:

~~~text
VIP x1
STD x3
Rejected: quantity must be positive
~~~

`Ticket(String)` calls `this(code, 1)`, without creating an extra Ticket object. The two-parameter constructor is where the **shared validation rules** live. As a result, both initialization paths enforce the same invariants.

### When Validation Is Needed Before Calling `this(...)`

You can pass **the result of a helper method** as an argument to another constructor call:

~~~java
Ticket(String code) {
    this(requireCode(code), 1);
}

private static String requireCode(String code) {
    if (code == null || code.isBlank()) {
        throw new IllegalArgumentException("code is required");
    }
    return code;
}
~~~

The snippets above are **alternative design fragments**; do not merge a constructor with the same signature into the existing demo file. The `requireCode` helper is evaluated as an argument expression before the target constructor continues to be called; if the helper throws an exception, the `new` process does not complete. Do this only when necessary; placing invariants in the target constructor is still usually easier to read.

### Validation in the Superclass

If a subclass extends a superclass, Java 17 normally requires `super(...)` at the start of the constructor when written explicitly. For example:

~~~java
class BaseConfig {
    BaseConfig(int port) {
        if (port <= 0 || port > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
    }
}

class ServerConfig extends BaseConfig {
    ServerConfig(int port, String host) {
        super(port);
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host is required");
        }
    }
}
~~~

These are two illustrative classes. The superclass constructor is responsible for validating `port`; the subclass constructor validates `host`. If `super(port)` throws an exception, the remaining statements of the subclass constructor do not run. You cannot use an ordinary `try` block placed **around** the `super(...)` call in a Java 17 constructor body; an external caller can catch the error from `new ServerConfig(...)`.

Every class in the inheritance chain should maintain the invariants for the portion of state it manages. Avoid writing subclasses that break the assumptions created by the superclass.

## 11. Protecting Mutable Inputs: When Does a Constructor Need a Defensive Copy?

Arguments that are mutable objects or collections can be **modified by the caller after the constructor finishes**. If the constructor only stores the raw reference, the initial invariant can be broken without going through any method of the class.

Consider code vulnerable to aliasing:

~~~java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> members) {
        this.members = members;
    }

    java.util.List<String> members() {
        return members;
    }
}
~~~

If the caller passes an `ArrayList` and then adds or removes elements in the old list, `Team` observes the same changes. The `members()` method also exposes the internal list for the caller to modify. A `final` field only prevents assigning another reference to `members`; **it does not make the ArrayList immutable**.

### Complete Example with `List.copyOf`

Save the file **`DefensiveCopyConstructorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class DefensiveCopyConstructorDemo {
    static final class Team {
        private final List<String> members;

        Team(List<String> members) {
            Objects.requireNonNull(members, "members");

            List<String> copy = List.copyOf(members);

            if (copy.isEmpty()) {
                throw new IllegalArgumentException("members must not be empty");
            }

            for (String member : copy) {
                if (member.isBlank()) {
                    throw new IllegalArgumentException("member must not be blank");
                }
            }

            this.members = copy;
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("Mai");
        source.add("An");

        Team team = new Team(source);

        source.add("Binh");
        System.out.println("Source: " + source);
        System.out.println("Team: " + team.members());

        try {
            team.members().add("Lan");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot modify team members");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefensiveCopyConstructorDemo.java
java DefensiveCopyConstructorDemo
~~~

Stdout:

~~~text
Source: [Mai, An, Binh]
Team: [Mai, An]
Cannot modify team members
~~~

In the constructor:

1. `Objects.requireNonNull` rejects a null list reference.
2. `List.copyOf(members)` creates or uses a list that cannot be modified through ordinary mutation APIs and does not share the mutable structure of the source `ArrayList`. It also **rejects null elements**.
3. An empty list or a member name containing only whitespace is rejected.
4. The `members` field is assigned after the data has passed validation.
5. The caller cannot modify the stored list by modifying `source` or calling `team.members().add(...)`.

**Limitation:** `List.copyOf` does not create a deep copy of the elements. With `List<Person>`, if each `Person` is mutable, the caller can still change the state of a shared `Person`. The example uses `String`, which is immutable, so it avoids this problem. In other problems, clearly define the required level of immutability.

### If an Array Is Passed

Arrays in Java are always mutable. For a primitive array `int[]`, the constructor can use `values.clone()` to copy the elements. If an accessor returns the array, it usually needs to copy it again to avoid exposing the internal reference.

~~~java
class Scores {
    private final int[] values;

    Scores(int[] values) {
        if (values == null) {
            throw new IllegalArgumentException("values required");
        }
        this.values = values.clone();
    }

    int[] values() {
        return values.clone();
    }
}
~~~

An illustrative class snippet. For an array of a reference type, `clone()` copies **the element references** rather than creating a deep copy of the element objects.

## 12. Records Must Also Protect Invariants When They Have a Constructor

Since Java 16, `record` helps represent values with fixed components. A record can declare a **compact constructor** to validate parameters before values are assigned to the record's component fields.

Save the file **`ValidatedRecordDemo.java`**:

~~~java
public class ValidatedRecordDemo {
    record Product(String code, int quantity) {
        Product {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code is required");
            }
            if (quantity < 0) {
                throw new IllegalArgumentException("quantity must be >= 0");
            }

            code = code.strip();
        }
    }

    public static void main(String[] args) {
        Product product = new Product("  P01  ", 3);

        System.out.println(product.code());
        System.out.println(product.quantity());

        try {
            new Product(" ", 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected invalid product");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ValidatedRecordDemo.java
java ValidatedRecordDemo
~~~

Stdout:

~~~text
P01
3
Rejected invalid product
~~~

In a compact constructor, the names `code` and `quantity` are parameters corresponding to the record components. After the compact constructor body completes normally, the compiler arranges the initialization of the component fields according to record rules. Assigning `code = code.strip()` inside the compact constructor causes **the normalized value** to be used to initialize the field.

**Do not infer that records are always deeply immutable:** components referencing mutable arrays or collections require an appropriate copy mechanism if you want to protect all observable state.

## 13. Checked Exceptions and Constructors Performing I/O

Normally, constructors of **value objects/domain objects** should only validate in-memory data. However, a resource-creating constructor may need I/O and may throw a checked exception.

Example declaration:

~~~java
class FileReaderResource {
    private final java.io.BufferedReader reader;

    FileReaderResource(java.nio.file.Path path)
            throws java.io.IOException {
        java.util.Objects.requireNonNull(path, "path");
        this.reader = java.nio.file.Files.newBufferedReader(path);
    }
}
~~~

This is an **illustrative class**; it has no `main` and no method to close the resource, so it is **not sufficient** for use in a real application. `Files.newBufferedReader` can throw `IOException`; therefore, the constructor declares `throws IOException`, and the caller needs to handle or declare propagation of this checked exception.

In production design:

- If a class owns a reader/file/socket, it needs a resource-closing strategy, typically implementing `AutoCloseable`.
- If a constructor opens multiple resources and a later step fails, the resources opened earlier may need to be closed during error handling.
- For a multi-step resource-creation operation, a clearly named factory or `try-with-resources` at the usage layer can make the lifecycle easier to control.
- Do not use GC as a way to close files or connections in a timely manner.

### Preserving the Root Cause

When catching a low-level exception and converting it into a more meaningful exception, preserve the **cause** if you want the caller to diagnose it:

~~~java
throw new IllegalStateException("Cannot initialize resource", cause);
~~~

This is an illustrative fragment inside a `catch` block with an appropriate `cause` variable of type `Throwable`. You should not catch every exception and simply throw `new IllegalArgumentException("invalid")`, losing the stack/cause when the real cause is I/O, permissions, or system state.

## 14. Constructors Do Not Automatically Roll Back and Should Not Leak `this`

While a constructor is running, `this` can already be used in valid instance contexts. If `this` is passed outside before the object finishes initializing, other code may hold a reference to an object in an intermediate state.

Risky design example:

~~~java
class Registry {
    static Object last;
}

class LeakyObject {
    private final String id;

    LeakyObject(String id) {
        Registry.last = this; // Publishing the reference too early.
        if (id == null) {
            throw new IllegalArgumentException("id required");
        }
        this.id = id;
    }
}
~~~

These are **two illustrative classes**, not a standalone program. If the constructor throws an exception after `Registry.last = this`, the static variable `Registry.last` already holds a reference to an **incompletely initialized** object. In the Java Memory Model, publishing `this` prematurely can also cause visibility issues across threads.

Practical guidelines:

- Validate important data and build state before publishing the object.
- Do not add `this` to a static registry in a constructor unless lifecycle and error handling are clearly controlled.
- Do not start a thread inside a constructor and let it run code that depends on uninitialized fields.
- Avoid calling **overridable** methods from a superclass constructor: the subclass may not have run its field initializers yet.
- If listener/callback registration is needed, consider doing it in a separate step **after the object is successfully created**.

**Final fields are not magic:** `private final String id` is useful for preventing field reassignment, but it cannot fix every issue if the object is published unsafely during initialization.

## 15. Do Not Call Overridable Methods from a Constructor

The issue is not just validation: when a superclass constructor calls an overridable instance method, Java still uses dynamic dispatch and may call the subclass version **before subclass fields have finished initializing**.

Save the file **`ConstructorOverridePitfallDemo.java`**:

~~~java
public class ConstructorOverridePitfallDemo {
    static class Base {
        Base() {
            System.out.println("Base constructor");
            describe();
        }

        void describe() {
            System.out.println("Base describe");
        }
    }

    static final class Child extends Base {
        private String id = "ready";

        Child() {
            System.out.println("Child constructor");
        }

        @Override
        void describe() {
            System.out.println("Child id=" + id);
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        child.describe();
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorOverridePitfallDemo.java
java ConstructorOverridePitfallDemo
~~~

Stdout:

~~~text
Base constructor
Child id=null
Child constructor
Child id=ready
~~~

The superclass constructor calls `describe()`. Because the runtime object belongs to `Child`, Java calls `Child.describe()` right then. However, Child's initializer `id = "ready"` has not run yet; the field is still at its default value `null`. Only after construction finishes does the call from `main` print `ready`.

If an overridden method performs validation based on subclass fields, it may **draw the wrong conclusion or throw an exception** while the object is not yet ready. Avoid this structure; only run safe, non-overridable helpers from a constructor when necessary.

## 16. Validation Should Not Depend on System-Wide State If Avoidable

A constructor needs to guarantee intrinsic invariants, such as `quantity > 0`. However, some conditions change over time:

- Does the user ID still exist in the database?
- Is the account name already in use?
- Is there enough inventory at the time the order is placed?
- Is the payment token still valid?
- Is an external service available?

These usually belong to a **creation/registration workflow**, a transaction, or a domain service, rather than being properties derived solely from parameters. For example, `new OrderRequest(productId, quantity)` can ensure structured data and a positive quantity, but it cannot guarantee sufficient inventory in the future.

One layering approach:

~~~text
User data
       |
       v
Validate/normalize structural data
       |
       v
new OrderRequest(...)  -> intrinsically valid request
       |
       v
OrderService checks inventory, permissions, transactions
       |
       v
Save order and perform post-processing according to policy
~~~

This is a design diagram, not a claim that every application must use a service with that exact name. Placing validation at the right layer makes constructors **predictable, easy to test, low on side effects, and free of long-running transactions**.

## 17. Testing Constructors: Valid, Boundary, and Invalid Cases

A reliable constructor needs to be verified across all three types of paths:

1. **Happy path:** valid input creates an object with the right fields.
2. **Boundary path:** values near thresholds, such as 0 if allowed, 1 if the quantity must be positive, or strings with leading and trailing whitespace.
3. **Failure path:** null, blank strings, negative numbers, reversed date order, empty collections, or invalid elements.
4. **Aliasing path:** the caller modifies the old array/list after creating the object; does the object preserve its invariant?
5. **No side effect path:** when validation fails, no external changes violating the contract occur.
6. **Consistency path:** all constructor overloads and factories reach the same valid state.

### Java Test Suite Without External Libraries

Save the file **`ConstructorTestDemo.java`**:

~~~java
public class ConstructorTestDemo {
    static final class Range {
        private final int start;
        private final int end;

        Range(int start, int end) {
            if (end < start) {
                throw new IllegalArgumentException("end must be >= start");
            }
            this.start = start;
            this.end = end;
        }

        int length() {
            return Math.subtractExact(end, start);
        }
    }

    static void assertEquals(int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "expected=" + expected + ", actual=" + actual);
        }
    }

    static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid input rejected");
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        assertEquals(5, new Range(3, 8).length());
        assertEquals(0, new Range(4, 4).length());

        expectInvalid(() -> new Range(8, 3));

        System.out.println("All constructor checks passed");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorTestDemo.java
java ConstructorTestDemo
~~~

Stdout:

~~~text
invalid input rejected
All constructor checks passed
~~~

Key points to understand:

- `Range(3, 8)` is valid and has length 5.
- `Range(4, 4)` is valid, with length 0 because the contract allows both ends to be equal.
- `Range(8, 3)` is rejected; the `expectInvalid` helper confirms the exact exception type.
- If the constructor does not throw an exception as expected, the helper throws `AssertionError` to report that the check failed.
- In `expectInvalid`, only `IllegalArgumentException` is considered a valid rejection result; if another exception is thrown, it is not silently treated as a pass.

This is a manual testing approach sufficient for learning the mechanism. In real projects, JUnit provides `assertThrows` and tools to organize many test cases more clearly.

### Do Not Test Only by Seeing That "Code Runs Without Errors"

If `new Account("Mai", 100)` runs successfully, we only know that **one valid case** works. We do not yet know whether the constructor rejects `null`, blank strings, or negative numbers. Sufficient tests must intentionally pass **invalid data** and check that invalid state does not slip past the object-creation boundary.

## 18. Common Mistakes

| Mistake | Consequence | How to Improve |
| --- | --- | --- |
| Constructor accepts any data | Object has invalid state | Define invariants and reject invalid input |
| Only printing a warning instead of throwing an exception | The caller still receives an invalid object | Throw an exception when a required condition is violated |
| Calling `name.isBlank()` without checking null first | May throw an unintended `NullPointerException` | Check null first, or deliberately use `Objects.requireNonNull` |
| Using Java's default values as valid state | `null`, 0, false may violate business rules | Initialize explicitly and validate |
| Turning every null into a default | Hides invalid data, making debugging harder | Separate required and optional fields |
| Validating each parameter while ignoring their relationship | An end date before a start date still slips through | Validate cross-field invariants |
| Constructor overloads validate differently | Same class, yet some paths create invalid objects | Delegate to a primary constructor |
| Storing a mutable input reference directly | The caller can break invariants after construction | Use defensive copies and an ownership contract |
| Returning an internal mutable array/list directly | The caller mutates state without going through methods | Return a copy or an appropriate unmodifiable view |
| Swallowing exceptions and continuing initialization | Cannot trust the object even when construction succeeds | Let exceptions propagate or recover under a clear contract |
| Writing external data before validating | The constructor fails, yet side effects still persist | Validate early and separate transactions from constructors |
| Publishing `this` before finishing | Other code sees an incompletely initialized object | Publish only after success |
| Calling an overridable method in a superclass constructor | May read subclass fields at their default values | Avoid dynamic dispatch during initialization |
| Discarding cause information when wrapping exceptions | Makes diagnosing the root error difficult | Preserve the cause when creating a new exception |
| Arbitrarily using checked exceptions for every invalid input | Callers are forced into unnecessary handling | Use exceptions according to the contract and error semantics |
| Testing only valid cases | Fails to detect accepted invalid inputs | Test invalid/boundary/aliasing cases |

## 19. Practice Exercises

### Exercise 1 — Fix an Unsafe Constructor

Given the class:

~~~java
class Product {
    String code;
    int quantity;

    Product(String code, int quantity) {
        this.code = code;
        this.quantity = quantity;
    }
}
~~~

Modify it so that:

- `code` must be non-null and non-empty after `strip()`.
- `quantity` must be greater than 0.
- Fields are `private`, and `final` if they do not need to change.
- `new Product(" P01 ", 2)` stores the normalized code `P01`.
- `new Product("", 2)`, `new Product(null, 2)`, and `new Product("P01", 0)` are rejected with the exact exception type according to your chosen contract.

### Exercise 2 — Separate Validation from I/O

A constructor accepts an email, writes a record to the database, and sends a confirmation email. Ask: If the email is invalid, has the database write already occurred? If sending the email fails, is the object returned? Propose a way to construct a valid `RegistrationRequest` in memory and then let a service execute the external transaction with an appropriate rollback/retry strategy.

### Exercise 3 — Validating a Time Window

Write `TimeWindow(LocalTime start, LocalTime end)` with a policy allowing or disallowing windows that span across midnight. If disallowed, verify that `end` is not before `start`. If allowed, clearly define how an end time on the next day is interpreted — comparing `LocalTime` alone may not be sufficient. This is an exercise in choosing **the right business invariant**, not just adding an `if`.

### Exercise 4 — Defensive Copy of an Array

Write `ExamScores(int[] scores)`:

- Disallow `scores == null`.
- Disallow an empty array if the business rules require at least one score.
- Each score must be within `0..100`.
- The constructor creates a copy of the array.
- The accessor does not directly return the internal array.

Try modifying the source array and the array from the accessor, and explain why the object's state does not change.

### Exercise 5 — Constructor Chaining

Create `Ticket(String code)` and `Ticket(String code, int quantity)` so that every path validates `code` and `quantity`. Predict what happens if the single-parameter overload assigns fields directly and skips validation. Centralize the rules in the primary constructor and test both overloads.

### Exercise 6 — Failure Path and Existing Reference

Create a valid `Account current` object, then attempt `current = new Account(" ", 10)` inside a `try-catch`. Demonstrate that `current` still points to the original object when the new constructor throws an exception. Distinguish between **failing to complete an assignment** and **rolling back all side effects**.

## 20. End-of-Lesson Checklist

- [ ] I can explain why a successfully constructed object should satisfy the class's invariants.
- [ ] I can distinguish between checking `null`, empty strings, blank strings, and normalization.
- [ ] I know when to throw `IllegalArgumentException` or use `Objects.requireNonNull`.
- [ ] I know that per-parameter conditions are not enough if the parameters have relationships with one another.
- [ ] I understand that a failing constructor prevents the `new` expression from returning a reference normally to the caller.
- [ ] I know that the caller's assignment does not happen if the right-hand side `new` throws an exception.
- [ ] I do not assume that already-executed side effects are automatically rolled back.
- [ ] I avoid publishing `this` when the object has not finished initializing.
- [ ] I avoid calling overridable methods in a constructor when they might read unready subclass state.
- [ ] I know that passing a mutable array/list to a constructor can leak state-modification access and know how to use defensive copies.
- [ ] I apply consistent validation across constructor overloads and `this(...)`.
- [ ] I can distinguish intrinsic invariants from checks on system state that changes over time.
- [ ] I know how to test valid, boundary, error, and aliasing cases.
- [ ] I compile and run the Java 17+ examples myself and explain the output based on state, exceptions, and initialization timing.

**Conclusion:** A constructor is the place to establish a valid object, not a place to "swallow" invalid data or perform every external task. **Define invariants → validate inputs → normalize/copy when needed → assign state → complete initialization**. If conditions are not met, report an error clearly so that `new` does not supply an invalid object along the success path. Together with update methods that preserve invariants, this approach makes classes easier to use, easier to test, and less prone to hard-to-diagnose state.
