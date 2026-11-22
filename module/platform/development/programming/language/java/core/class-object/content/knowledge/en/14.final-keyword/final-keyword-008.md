# When to Use `final` to Express Design Intent in Java

**`final`** is one of the most important keywords for writing Java with a **clear design contract**. Not only does it let the compiler prevent an assignment or a method override, `final` also communicates to readers that: *this value or behavior has been determined at a certain boundary, and other code should not change it in a way contrary to the design*.

But the exact meaning depends on where you place the keyword:

- **Final field:** a field assigned according to Java's initialization rules and not arbitrarily reassigned afterward.
- **Final local variable / parameter:** a local variable or parameter that cannot be reassigned after being validly assigned.
- **Final instance method:** subclasses cannot **override** that method.
- **Final class:** no subclass can be declared to extend that class.
- **`static final` field:** a field associated with the class that cannot be reassigned per `final` rules; commonly used for constants, yet **not every `static final` reference points to immutable data**.

This article explains **when to use and when not to use `final`**, based on Java 17+, from an object-oriented programming perspective: protecting *invariants*, stabilizing identity, clarifying ownership, restricting extension points, API design, the effects of mutable references, and concurrency. The standalone examples include run instructions and stdout for verification.

## 1. Correctly Interpreting the Meaning of `final` by Position

| Declaration | Expressed Intent | `final` Does **Not** Automatically Guarantee |
| --- | --- | --- |
| `private final String id;` | The identity field is not reassigned after initialization | That the content is non-null or valid per business rules if the constructor does not validate it |
| `private final List<Item> items;` | The field always holds the same reference after initialization | That the List and the Items inside it will not be modified |
| `final int count = 3;` | The local `count` cannot be reassigned | That all related calculations are correct |
| `void send(final Request request)` | The parameter `request` cannot be reassigned in the body | That the method does not modify the Request object |
| `public final void process()` | Subclasses cannot override `process()` | That other implementations in the system cannot have different behavior |
| `public final class Money` | `extends Money` is not allowed | That the Money object is immutable or thread-safe if it has mutable fields |
| `public static final int MAX = 10;` | A value associated with the class, with restricted assignment | That the value will always fit the needs of different API versions |

Therefore, **final is a language constraint, whereas business immutability is a design constraint**. The two complement each other, but neither replaces the other.

Example:

~~~java
class Customer {
    private final String id;
    private String displayName;

    Customer(String id, String displayName) {
        this.id = java.util.Objects.requireNonNull(id, "id");
        this.displayName =
                java.util.Objects.requireNonNull(displayName, "displayName");
    }

    String id() {
        return id;
    }

    void rename(String nextName) {
        if (nextName == null || nextName.isBlank()) {
            throw new IllegalArgumentException("Tên trống");
        }
        displayName = nextName;
    }
}
~~~

This is a **class declaration snippet**, without `main` yet. `id` is designed as the **stable identity** of Customer, whereas `displayName` is allowed to change through the `rename` behavior. Not every field needs to be `final` to be considered proper object-oriented design.

## 2. Use `final` for State That Must Remain Stable After Object Creation

The clearest case is a value **established once when creating the object** with no valid use case to change it:

- The ID of an order, transaction, or entity.
- The object creation timestamp (*createdAt*) if the contract defines this timestamp as immutable.
- The currency associated with an amount value object.
- The initial configuration snapshot captured for a request.
- A dependency that the instance uses throughout its lifecycle.
- A classification key or structural information that must not change.

Example:

~~~java
import java.time.Instant;
import java.util.Objects;

class Invoice {
    private final String invoiceId;
    private final Instant createdAt;
    private long balanceDue;

    Invoice(String invoiceId, Instant createdAt, long balanceDue) {
        this.invoiceId = Objects.requireNonNull(invoiceId, "invoiceId");
        this.createdAt = Objects.requireNonNull(createdAt, "createdAt");
        if (balanceDue < 0) {
            throw new IllegalArgumentException("Số dư âm");
        }
        this.balanceDue = balanceDue;
    }

    String invoiceId() {
        return invoiceId;
    }
}
~~~

`String` and `Instant` are immutable types, so returning them does not let the caller modify the stored instance content. `balanceDue`, on the other hand, is invoice state that can change with transactions, so it does not necessarily need to be final.

### 2.1. Do Not Create a Setter for a Final Identity

If `invoiceId` is truly the identity, you should not create `setInvoiceId(...)`. Changing the identity can break:

- Business references to the invoice.
- Keys in a map or linked data.
- Audit logs or the access path of a resource.
- The meaning of `equals/hashCode` if identity participates in them.

However, `final` does not build an equality model on its own. An entity still needs to define equality rules appropriate for its domain, whereas `final` only prevents reassigning the field along valid Java code paths.

### 2.2. Choosing When to Lock the Value

`final` can be declared with an initializer:

~~~java
private final int maxRetries = 3;
~~~

or as a **blank final** assigned in the constructor:

~~~java
private final int maxRetries;

Config(int maxRetries) {
    if (maxRetries < 0) {
        throw new IllegalArgumentException("Số lần thử âm");
    }
    this.maxRetries = maxRetries;
}
~~~

The second approach expresses that **each Config instance has a configuration value chosen by the caller**, yet that value does not change after the instance is successfully created. This differs from a `static final` shared across all Config objects.

## 3. A `final` Field Still Needs Constructor Validation

The compiler verifies final/definite assignment rules; it **does not automatically verify domain invariants**.

~~~java
class WrongUser {
    final String email;

    WrongUser(String email) {
        this.email = email; // May be null/blank/invalid format
    }
}
~~~

Valid in the language, yet not necessarily valid according to business rules. A class that protects its invariant better:

~~~java
class User {
    private final String email;

    User(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email trống");
        }
        this.email = email.trim();
    }

    String email() {
        return email;
    }
}
~~~

**`final` supports immutability by preventing field reassignment**, whereas **validation ensures the assigned value satisfies the contract**. Do not replace validation with “it is final, so it is definitely valid”.

### 3.1. When a Constructor Has Multiple Branches

A blank final field must be assigned **exactly once on every initialization path that completes normally**, according to definite assignment/definite unassignment rules. You can use `if/else`:

~~~java
class Channel {
    private final String endpoint;

    Channel(boolean secure) {
        if (secure) {
            endpoint = "https://example.org";
        } else {
            endpoint = "http://example.org";
        }
    }
}
~~~

Or compute into a local variable first and then assign the final field once:

~~~java
class Channel {
    private final String endpoint;

    Channel(boolean secure) {
        String protocol = secure ? "https" : "http";
        this.endpoint = protocol + "://example.org";
    }
}
~~~

If a constructor throws an exception before completing, that path does not successfully create the object. It is not necessary to assign all final fields before throwing; however, **any path that completes normally with an unassigned field will be rejected by the compiler**.

## 4. Use `final` to Protect Object Structure, Not All Mutable Data

In an aggregate, you may want to **keep the reference to an internal collection unchanged** while allowing items to be added or removed through a controlled API.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

class ShoppingCart {
    private final List<String> items = new ArrayList<>();

    void addItem(String item) {
        String checked = Objects.requireNonNull(item, "item");
        if (checked.isBlank()) {
            throw new IllegalArgumentException("Mặt hàng trống");
        }
        items.add(checked);
    }

    List<String> items() {
        return List.copyOf(items);
    }
}
~~~

`final` on the `items` field prevents the class from reassigning `items = new ArrayList<>()` after initialization. However, `items.add(...)` is still valid: it mutates the **List object**, without reassigning the field. The `addItem` API controls the contents, while `items()` returns a list that cannot be modified through its API.

**When to use this approach:** the aggregate's lifecycle keeps the same collection object, while elements can change intentionally. If you want a completely immutable snapshot, consider using immutable data and creating a new object instead of mutating.

### 4.1. `final List` Differs from an Immutable List

~~~java
private final List<String> values =
        new java.util.ArrayList<>();
~~~

The reference `values` is final; the List is still mutable.

~~~java
private final List<String> values =
        List.of("A", "B");
~~~

Here, the List cannot be modified through its API thanks to `List.of`, not because of the `final` keyword. With immutable String elements, the overall state is easier to reason about.

### 4.2. Defensive Copying Is Still Necessary for Mutable Inputs

If the caller passes an array into the constructor:

~~~java
class Scores {
    private final int[] marks;

    Scores(int[] input) {
        this.marks = input.clone();
    }

    int[] marks() {
        return marks.clone();
    }
}
~~~

The constructor clones the input, and the getter clones the output. Therefore, the caller cannot alter the internal array through an alias of the input array or the array returned by the getter. `final` only prevents **changing the field reference**; cloning is what prevents unintended **sharing of a mutable array**.

If `input == null`, the example throws an NPE at `clone()`; a real-world API should explicitly state this or validate null according to the contract. For an array containing mutable object references, `clone()` is only a **shallow copy** and does not deep-copy the element objects.

## 5. Complete Example: `final` for Identity, Non-`final` for State Allowed to Change

Create the file **`FinalFieldDesignDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class FinalFieldDesignDemo {
    static final class Account {
        private final String accountId;
        private final List<String> history = new ArrayList<>();
        private long balance;

        Account(String accountId, long openingBalance) {
            this.accountId = Objects.requireNonNull(
                    accountId, "accountId");
            if (accountId.isBlank()) {
                throw new IllegalArgumentException("ID trống");
            }
            if (openingBalance < 0) {
                throw new IllegalArgumentException("Số dư âm");
            }
            this.balance = openingBalance;
            history.add("OPEN:" + openingBalance);
        }

        String id() {
            return accountId;
        }

        long balance() {
            return balance;
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("Số tiền sai");
            }
            long next = Math.addExact(balance, amount);
            balance = next;
            history.add("DEPOSIT:" + amount);
        }

        List<String> history() {
            return List.copyOf(history);
        }
    }

    public static void main(String[] args) {
        Account account = new Account("ACC-7", 100);

        account.deposit(40);
        System.out.println("ID = " + account.id());
        System.out.println("Balance = " + account.balance());
        System.out.println("History = " + account.history());

        try {
            account.deposit(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Final balance = " + account.balance());
        System.out.println("Events = " + account.history().size());

        try {
            account.history().add("FAKE");
        } catch (UnsupportedOperationException ex) {
            System.out.println("History read-only");
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 FinalFieldDesignDemo.java
java FinalFieldDesignDemo
~~~

**Exact stdout:**

~~~text
ID = ACC-7
Balance = 140
History = [OPEN:100, DEPOSIT:40]
Rejected = Số tiền sai
Final balance = 140
Events = 2
History read-only
~~~

**Design analysis:**

1. `accountId` is final: the identity is established when creating the Account and cannot be reassigned.
2. `history` is also a final reference: the class keeps the same internal List, yet events can be added through the `deposit` method.
3. `balance` is **not final** because it must change after valid transactions.
4. `deposit` validates and uses `Math.addExact` to avoid overflow when calculating the balance.
5. `history()` returns an unmodifiable structural copy, preventing the caller from inserting events directly. Here, the elements are immutable Strings.
6. `account.history().add("FAKE")` throws `UnsupportedOperationException`; the example catches the exception to ensure stable stdout.
7. The final fields **do not make Account thread-safe on their own** if multiple threads call `deposit` concurrently. Proper synchronization or an appropriate transaction model is needed in a real application.

**Takeaway:** a class can **intentionally combine final and non-final state**. That is usually a better design than marking all fields `final` without considering what kind of state they represent.

## 6. Use `final` for Dependencies That Should Not Change During an Object's Lifecycle

An object often depends on a service, clock, repository, or strategy. If the dependency is provided when creating the object and **must not be replaced afterward**, a final field clearly expresses that decision:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

class AuditService {
    private final Clock clock;

    AuditService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    Instant occurredAt() {
        return clock.instant();
    }
}
~~~

This aligns well with **constructor injection**:

- Requires the dependency to be provided upon creation.
- No public setter exists that would allow unexpectedly swapping the clock between two calls.
- Tests can pass `Clock.fixed(...)` for deterministic time.
- Each AuditService instance can use a different clock.

`final Clock clock` does not mean the Clock implementation is immutable or thread-safe in all cases; it only guarantees that the `clock` field **does not change its reference** after valid initialization.

### 6.1. When a Dependency Needs to Change

If the application genuinely supports changing strategy/configuration at runtime, a non-final field with a clear synchronization protocol may be appropriate. Alternatively, hold a final reference to **a provider object** whose API returns the current configuration:

~~~java
interface ConfigurationProvider {
    String currentRegion();
}

class Client {
    private final ConfigurationProvider provider;

    Client(ConfigurationProvider provider) {
        this.provider = java.util.Objects.requireNonNull(provider);
    }

    String region() {
        return provider.currentRegion();
    }
}
~~~

`provider` is not reassigned, yet **the result of `currentRegion()` can change over time**. This distinguishes stability of the dependency reference from stability of the data provided by the dependency.

If the provider's state changes concurrently, you must examine the provider's own thread-safety contract; `final` in Client does not replace that.

## 7. `final` for Local Variables: Locking an Assignment When It Helps the Reader

Inside a method:

~~~java
void send(String raw) {
    final String normalized = raw.trim();
    System.out.println(normalized);
}
~~~

`normalized` is assigned once. The `final` keyword indicates that this local value is a **finalized computed result**, not a variable that keeps changing across multiple steps.

This is valuable when:

- A local variable stores a **validation/normalization result** that needs to be used consistently across many lines.
- A method is long, has many branches, and accidentally reassigning a variable would be hard to spot.
- You want to emphasize that a variable is a **stable binding** in a critical block of code.
- The codebase has a convention of using `final` for locals at clear logical boundaries.

However, not every local variable has to be final:

~~~java
long sum = 0;
for (int item : numbers) {
    sum += item;
}
~~~

`sum` is an **accumulator** that legitimately must be updated. Forcing every local to be final pushes code toward unnecessary wrappers or complex expressions. You can replace it with streams where appropriate, yet **you should not rewrite code solely to eliminate a reassignment**.

### 7.1. `final` Does Not Make a Computed Value Any More Correct

~~~java
final long total = price * quantity;
~~~

If `price` and `quantity` are `long`, this expression can still overflow according to Java's arithmetic rules; final does not check for overflow. If you need to detect overflow, use `Math.multiplyExact`:

~~~java
final long total = Math.multiplyExact(price, quantity);
~~~

Meaning: **final locks the binding**, whereas **computation logic and validation** determine correctness.

## 8. `final` for Parameters: When You Need to Assert That a Parameter Name Is Not Reassigned

Method parameters can also be declared final:

~~~java
void register(final Customer customer) {
    // customer = new Customer(...); // Invalid: reassigning parameter
    System.out.println(customer.id());
}
~~~

For a reference-type parameter, final **does not prevent mutating the object**:

~~~java
static void add(final List<String> names) {
    names.add("Java"); // May be valid if the list is mutable
    // names = new ArrayList<>(); // Invalid
}
~~~

This is a fragment that requires `import java.util.List;` or a fully qualified name.

Java **always passes parameters by value**, including references. `final` does not turn pass-by-value into pass-by-reference, does not copy the object, and does not make the parameter thread-safe. It only prevents code inside the method from **reassigning the parameter variable itself**.

### 8.1. Why Should You Sometimes Use a Final Parameter?

A complex method might accidentally reuse a parameter name for an intermediate value:

~~~java
void process(String name) {
    name = name.trim();
    // Use the modified name...
}
~~~

If preserving the raw input is important, you can write:

~~~java
void process(final String rawName) {
    final String name = rawName.trim();
    // rawName is not reassigned; name is the normalized value
}
~~~

The two variable names communicate two roles: **raw input** and **normalized value**. This is a readability benefit; there is no requirement to mark every parameter final in Java.

### 8.2. When Should You Avoid Overusing It?

If a method is short and does not reassign its parameter, `final` may add verbosity without adding much information. A development team should choose a consistent style and prioritize **expressing real design** over mechanical syntactic changes.

## 9. Lambda Capture: final or *effectively final*

A local variable captured by a lambda must be **final or effectively final** (not reassigned according to Java's rules).

~~~java
import java.util.function.IntUnaryOperator;

class Calculator {
    static IntUnaryOperator plus(int amount) {
        return input -> input + amount;
    }
}
~~~

`amount` is not declared final, yet it is **effectively final** because it is not reassigned; the lambda can use it. That does not prove that the final keyword must be added.

Invalid example:

~~~java
int offset = 1;
offset++;
// java.util.function.IntUnaryOperator f = x -> x + offset;
// Error: offset is no longer effectively final.
~~~

If you need a stable value for the lambda, create a new binding:

~~~java
int offset = 1;
offset++;

final int captured = offset;
java.util.function.IntUnaryOperator f = x -> x + captured;
~~~

Here, the local `captured` is assigned once after the calculation finishes. This ensures the lambda observes the finalized value 2, rather than a mutable local variable that could change afterward.

**Be careful with mutable objects:** a final reference to a mutable List can still be used by a lambda to add or remove elements. Effectively final only refers to **the local variable's binding**; it does not require the referent object to be immutable.

## 10. Complete Example: Local `final`, Parameter `final`, and Effectively Final

Create the file **`FinalLocalDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.IntUnaryOperator;

public class FinalLocalDemo {
    static int normalized(final int input) {
        final int safe = Math.max(input, 0);
        return safe;
    }

    static IntUnaryOperator plus(final int amount) {
        return value -> value + amount;
    }

    static void append(final List<String> values, final String item) {
        values.add(item);
        // values = new ArrayList<>(); // Error: final parameter
    }

    public static void main(String[] args) {
        final String title = "Java";
        final List<String> topics = new ArrayList<>();

        append(topics, title);
        append(topics, "OOP");

        int offset = 3; // Effectively final, not reassigned
        IntUnaryOperator op = value -> value + offset;

        System.out.println("Title = " + title);
        System.out.println("Topics = " + topics);
        System.out.println("Safe = " + normalized(-5));
        System.out.println("Plus = " + plus(10).applyAsInt(2));
        System.out.println("Captured = " + op.applyAsInt(7));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FinalLocalDemo.java
java FinalLocalDemo
~~~

Exact stdout:

~~~text
Title = Java
Topics = [Java, OOP]
Safe = 0
Plus = 12
Captured = 10
~~~

`title` is not reassigned; `topics` is a final reference, yet the List still accepts additional elements. `offset` does not have the final keyword, yet it is still captured because it is effectively final. The final parameter in `append` does not prevent `values.add(item)` when the List is mutable.

The intention here is to **restrict reassignment and express the variable's role**, not to create a deeply immutable object or a different parameter-passing mechanism.

## 11. Use `final` for a Method When Subclasses Must Not Change That Contract

A **final instance method** prevents subclasses from **overriding** it. This is an important tool when a method enforces a **mandatory workflow**, protects an invariant, or maintains a contract that every subclass must respect.

~~~java
abstract class Operation {
    public final String execute(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Input trống");
        }
        return perform(input.trim());
    }

    protected abstract String perform(String input);
}
~~~

A subclass can customize the `perform` step, yet cannot override `execute` to bypass validation. This is a form of the **template method**: final entry point + controlled extension hook.

### 11.1. A Final Method Cannot Be Overridden

~~~java
class ChildOperation extends Operation {
    @Override
    protected String perform(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }

    // @Override
    // public String execute(String input) { return input; }
    // Invalid: execute in the superclass is final.
}
~~~

The invalid lines are commented out so the class snippet remains valid. If you uncomment the `execute` method in the subclass, the compiler reports an error because a final method cannot be overridden.

**When to use:** an entry point must apply uniform validation, auditing, transaction lifecycle handling, or invariant conditions, while subclasses are only allowed to supply strategies for specific steps.

**Limitation:** final on a method does not prove that all code is safe. If a final method calls a `protected abstract perform` hook that has unexpected side effects, a subclass can still corrupt state if the API does not clearly define the hook contract and control data sources.

### 11.2. Complete Example of a Controlled Extension Point

Create the file **`FinalMethodDemo.java`**:

~~~java
import java.util.Locale;

public class FinalMethodDemo {
    static abstract class Processor {
        public final String process(String raw) {
            if (raw == null || raw.isBlank()) {
                throw new IllegalArgumentException("Input trống");
            }
            String checked = raw.trim();
            return transform(checked);
        }

        protected abstract String transform(String text);
    }

    static final class UpperProcessor extends Processor {
        @Override
        protected String transform(String text) {
            return text.toUpperCase(Locale.ROOT);
        }
    }

    static final class WrappedProcessor extends Processor {
        @Override
        protected String transform(String text) {
            return "[" + text + "]";
        }
    }

    public static void main(String[] args) {
        Processor upper = new UpperProcessor();
        Processor wrapped = new WrappedProcessor();

        System.out.println("Upper = " + upper.process("  java  "));
        System.out.println("Wrapped = " + wrapped.process("  oop "));

        try {
            upper.process(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 FinalMethodDemo.java
java FinalMethodDemo
~~~

**Exact stdout:**

~~~text
Upper = JAVA
Wrapped = [oop]
Rejected = Input trống
~~~

Notes:

1. `process` is final, so subclasses cannot replace the entire validation pipeline.
2. `transform` is protected abstract, allowing each subclass to implement a custom step.
3. `UpperProcessor` and `WrappedProcessor` are both final because the example does not need another inheritance layer.
4. A final method still uses dynamic dispatch for the `transform` hook; `final` only prevents overriding **the process method**, rather than disabling all polymorphism inside the body.

**Do not make all methods final out of habit** if a class is designed with rich extension points. The choice should be based on the extension contract, not the mindset “the more final, the safer”.

## 12. When Should You Declare a Class `final`?

Use `final class` when **you do not want the class to be inherited from** as part of the API contract.

Some reasonable scenarios:

- A **value object** whose representation/invariants are controlled by the class itself, needing no subclasses.
- An **implementation detail** not designed for extension.
- A **helper class** or a class with specific semantics that could easily be broken if a subclass overrides behavior.
- A class that **does not need to be a base class**; opening up inheritance without a clear extension contract can create awkward dependencies.
- You want to ensure that the class has a set of instance behavior implementations that cannot be altered by arbitrary subclasses.

~~~java
public final class Money {
    private final long cents;
    private final String currency;

    public Money(long cents, String currency) {
        this.cents = cents;
        this.currency =
                java.util.Objects.requireNonNull(currency, "currency");
    }

    public long cents() {
        return cents;
    }

    public String currency() {
        return currency;
    }
}
~~~

This is an illustrative class placed in the file `Money.java`. `Money` cannot be extended via `class SpecialMoney extends Money`; the compiler rejects it. However, this is not yet a complete money model: you must consider value ranges, currency rules, rounding, equality, and arithmetic.

### 12.1. `final class` Does Not Automatically Make Instances Immutable

~~~java
final class Box {
    int value;

    void update(int next) {
        value = next;
    }
}
~~~

The `Box` class is final, yet `value` is still mutable. No one can subclass Box; that is **different from** no one being able to change the state of a Box object.

### 12.2. When Not to Make a Class Final

Do not declare a class final if **inheritance is an intentional extension point** and already has a stable contract:

- A base class of a framework that requires implementers to use `extends`.
- An abstract class providing templates/hooks for subclasses to customize.
- A library API that guarantees clients can create subclasses and override designated methods.

If a class is `abstract` so it can have subclasses, it **cannot also be `final`**:

~~~java
// abstract final class Bad {} // Invalid
~~~

Conversely, you can make **some methods final** in an abstract class while leaving other methods abstract/overridable, as in the `Processor` example above.

## 13. `final` or Designing with Interfaces and Composition?

`final` is not the only answer to the problem of controlling extension.

For example, instead of letting clients use `extends PaymentService` to swap a dependency, we can introduce an interface:

~~~java
interface PaymentGateway {
    boolean charge(long amount);
}

final class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway =
                java.util.Objects.requireNonNull(gateway, "gateway");
    }

    boolean pay(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount phải dương");
        }
        return gateway.charge(amount);
    }
}
~~~

`PaymentService` is final: the API does not support direct subclassing. Yet behavior can still be configured through the **PaymentGateway interface**. Different implementations, test doubles, and strategies are injected explicitly.

**This design is usually appropriate when you need to “swap dependent behavior”, not “change the identity of the service class”**. Composition makes extension points clearer to control than letting subclasses override arbitrary methods.

### 13.1. `final` Does Not Eliminate Polymorphism

A final class can still **implement an interface** and be used polymorphically through the interface type:

~~~java
interface Formatter {
    String format(String text);
}

final class LowerFormatter implements Formatter {
    @Override
    public String format(String text) {
        return text.toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

`LowerFormatter` cannot be subclassed, yet its objects can still be held in a `Formatter` variable. Runtime dispatch through the interface still works. **Final prevents inheriting from that class; it does not prevent that class from implementing an interface and participating in polymorphism.**

## 14. `static final` for Constants with Stable Meaning

A typical use:

~~~java
class Protocol {
    static final int MAX_PACKET_BYTES = 1_024;
    static final String VERSION = "1";
}
~~~

Use `static` because the values belong to the class, not to each individual object. Use `final` because the binding should not be reassigned.

If the value needs to be exposed to callers outside the package/class, consider appropriate visibility:

~~~java
public final class Limits {
    public static final int MAX_ITEMS = 100;

    private Limits() {
    }
}
~~~

This is a utility class with a public constant; code uses `Limits.MAX_ITEMS` without creating an instance. However, **public constants are part of the API**: changing the name, type, meaning, or value can affect client code.

### 14.1. Compile-Time Constants and the Inlining Issue

For a `static final` primitive or String whose initializer is a valid constant expression, Java has the concept of a **constant variable**. The client compiler can **inline the value** into the client bytecode.

Library example:

~~~java
public final class ApiConstants {
    public static final int PAGE_SIZE = 20;
}
~~~

If the library changes `PAGE_SIZE` to 50 and releases a new version, **clients already compiled against the old version may continue using the value 20** until they are recompiled. Therefore, avoid exposing a compile-time constant for a value **that can change across deployments/versions** if you need clients to always look up the latest runtime value.

When you need a value that can vary by environment:

~~~java
public final class Settings {
    private Settings() {
    }

    public static int pageSize() {
        return Integer.getInteger("app.page.size", 20);
    }
}
~~~

The snippet above is an example of an API that computes the value at call time, rather than a static final compile-time constant. You should validate the property and ensure consistency if using this in production.

### 14.2. A `static final` Reference Is Not Necessarily a Compile-Time Constant

~~~java
static final java.time.Instant STARTED_AT =
        java.time.Instant.now();
~~~

`Instant.now()` executes when the class is initialized and returns an object; this is not a compile-time constant. Similarly, `static final List<String> TAGS = List.of(...)` has a final reference, yet is not a primitive/String constant variable under JLS rules.

## 15. Avoid Using `public static final` for Uncontrolled Mutable Singleton Objects

A misleading example:

~~~java
import java.util.ArrayList;
import java.util.List;

class Registry {
    public static final List<String> USERS = new ArrayList<>();
}
~~~

Even though `USERS` is static final, any code with access can still call:

~~~java
Registry.USERS.add("Lan");
Registry.USERS.clear();
~~~

That is, **global mutable state** can be modified by uncontrolled callers. The final keyword does not prevent those changes.

Design if the data is truly an immutable constant:

~~~java
import java.util.List;

final class Registry {
    static final List<String> DEFAULT_USERS =
            List.of("Guest", "Admin");
}
~~~

On the other hand, if this is a dynamic registry, you should design an API that manages concurrency, ownership, validation, and lifecycle, and avoid returning a shared mutable collection directly.

### 15.1. Do Not Use a Constant Interface Just to Inherit Constants

A pattern like:

~~~java
interface Constants {
    int LIMIT = 10;
}

class Service implements Constants {
}
~~~

causes `Service` to “receive” constants through an interface without Service itself fulfilling any behavioral contract. In modern design, **avoid abusing the constant interface pattern**. It is usually clearer to use `Limits.LIMIT` from a utility class or an appropriate enum/value object.

## 16. `final`, Immutable Objects, and Records in Java 17

For an object to be truly **immutable by contract**, more than `final` is usually required:

1. No API that mutates state after creation.
2. Fields representing state cannot be arbitrarily reassigned.
3. Do not expose a mutable representation through getters.
4. If accepting mutable input, defend by copying or converting to an immutable representation.
5. Prevent subclasses from breaking invariants via overriding/hiding, or design a safe extension contract.
6. Do not allow `this` to escape during initialization.

An immutable class can use a final class + private final fields, yet you must also consider **the state of nested objects**.

### 16.1. Record: Concise Syntax for Data That Rarely Changes

In Java 17:

~~~java
record Coordinate(int x, int y) {
    Coordinate movedBy(int dx, int dy) {
        return new Coordinate(
                Math.addExact(x, dx),
                Math.addExact(y, dy));
    }
}
~~~

The `Coordinate` record is **implicitly final**, its corresponding component fields are private final with accessors `x()` and `y()`; no setters are generated. `movedBy` returns a new object, keeping the old object unchanged.

However, a record is not automatically **deeply immutable** when a component is a mutable reference:

~~~java
import java.util.List;

record Tags(List<String> values) {
    Tags {
        values = List.copyOf(values);
    }
}
~~~

The compact constructor normalizes/copies `values`; since the elements are immutable Strings, this is a way to build a record whose state is easier to control. If it were `List<MutableItem>`, `List.copyOf` would not deep-copy each element object.

### 16.2. Not Every Entity Should Be an Immutable Record

An order that must go through multiple states may be better modeled as a mutable entity with **final identity + controlled commands**. Forcing all state into a final immutable class and creating a new object after every action may or may not be suitable, depending on the system. Consider object identity, the persistence model, concurrent access, and history requirements.

## 17. `final` and the Java Memory Model: Helpful, but Not Magic

Final fields have **special rules when an object is properly constructed** in the Java Memory Model. These rules help guarantee visibility of final field values under the right conditions, including some common scenarios where references are shared without synchronization.

However:

- A **final reference** can point to a **mutable object**; final does not make subsequent modifications on that object thread-safe.
- A class containing a final field and non-final mutable fields can still suffer from data races.
- **Publishing `this` prematurely** inside a constructor can let other code observe the object before initialization completes.
- Invariants spanning **multiple fields** may still need synchronization or an immutable snapshot when multiple threads read and write.
- `final` is not equivalent to `volatile`, `synchronized`, `AtomicInteger`, or a lock.

An unsafe publication example:

~~~java
class Unsafe {
    static Unsafe current;

    final String id;

    Unsafe(String id) {
        current = this; // Exposes the object before assigning id
        this.id = id;
    }
}
~~~

This is an illustration to **avoid**. The `id` field is properly assigned by the constructor under definite assignment if it completes normally, yet the object can be read from the static field by another thread before initialization finishes.

### 17.1. `final` on a Counter Reference Does Not Replace Atomic Operations

~~~java
class Metrics {
    private final java.util.concurrent.atomic.AtomicInteger count =
            new java.util.concurrent.atomic.AtomicInteger();

    int record() {
        return count.incrementAndGet();
    }
}
~~~

`final` prevents replacing the AtomicInteger object stored in the field, while `incrementAndGet` guarantees atomic increment behavior according to the AtomicInteger contract. These are two different properties, and both are useful.

If you use `final int count`, you cannot increment the field with `count++` after initialization. **Choose the mechanism based on the business requirement:** if a counter needs to change, the counter's field or value must have an appropriate way to change; `final` is not a mandatory badge of quality on every field.

## 18. When Does `final` Make a Design Unnecessarily Hard to Extend?

### 18.1. Library Base Classes

If a class is published as a **base class for library users to inherit from**, adding `final` to the class is a change that **breaks source/binary compatibility** with existing subclasses. Similarly, changing an overridable method to final can invalidate other implementations or subclasses.

Before using final in a public/protected API, ask:

- Does this class have a clear extension contract, or is it just a concrete implementation?
- Which methods are subclasses allowed to override?
- Do third-party clients need to customize behavior via inheritance?
- Can an interface or composition be provided for controlled extension without direct subclassing?

### 18.2. Test Doubles and Mocking

Some test frameworks create subclasses to mock classes or methods, so `final` can affect how **certain tools or configurations** mock them. However, you should not automatically remove final from a well-designed domain or API just to accommodate a specific tool.

Options:

- Mock/inject through an interface.
- Use a fake implementation of the dependency.
- Use constructor injection.
- Use a mocking framework suitable for final classes/methods if the framework/version actually supports it.
- Test behavior through the public API instead of overriding private implementation details.

**Do not claim that every mocking framework is unable to mock final classes**; support depends on the version and configuration.

### 18.3. Serialization, ORM, Proxies

Some frameworks generate proxies/subclasses or require special constructor/field access. A final class or final method may conflict with a specific proxying approach, yet requirements vary by framework and version.

Check the framework's contract before deciding to open up a class or remove final. If persistence concerns force the domain model to be more open than desired, consider separating the domain model, DTO, and persistence mapping where appropriate.

## 19. When Is `final` Not Needed on a Method or Class?

Not every class needs to be final. Scenarios **intentionally supporting overriding/inheritance**:

~~~java
abstract class Notifier {
    public final void notifySafely(String message) {
        if (message == null || message.isBlank()) {
            throw new IllegalArgumentException("message trống");
        }
        deliver(message);
    }

    protected abstract void deliver(String message);
}
~~~

The `Notifier` class must be subclassed to implement `deliver`. It **cannot** be a final class, yet `notifySafely` can be final to protect the validation step.

A method that subclasses need to override according to the contract is **not** final:

~~~java
protected abstract void deliver(String message);
~~~

**Good design often combines**: locking entry points that have mandatory invariants, and leaving clearly documented hooks open.

### 19.1. A `private final` Method Usually Adds Little Additional Value

A private instance method cannot be overridden by a subclass as an inherited method. Adding `final` to a private method usually does not provide any useful overriding protection. Java permits certain valid modifier combinations, yet **do not use final decoratively** if that property is already guaranteed by the access scope or other syntax.

### 19.2. Constructors Cannot Be Declared Final

Constructors are not overridden like instance methods, so using `final` on a constructor makes no sense:

~~~java
class Example {
    // final Example() {} // Invalid constructor modifier syntax
    Example() {
    }
}
~~~

Similarly, a `final` class cannot be combined with `abstract` to require subclassing; the goals of the two modifiers contradict each other.

## 20. Notes on the Compiler and Optimization

Do not choose `final` solely expecting it to be “guaranteed faster”. The JVM/JIT uses various inlining and devirtualization techniques based on runtime profiling, the class hierarchy, and specific conditions; a non-final method **can still be optimized**, while final **does not guarantee specific performance**.

Choose final primarily because:

- It makes the **contract** clear.
- It helps the compiler catch unintended reassignment/overriding/subclassing errors.
- It supports **immutability and reasoning**.
- It carries specific semantics in the **Java Memory Model** when used properly.

If performance truly matters, benchmark reliably (for example, with appropriate JMH benchmarks) instead of assuming that adding final will produce a fixed improvement.

## 21. Comparing `final` with `private`, `static`, `volatile`, and `synchronized`

| Keyword/Mechanism | Primary Question Answered | What It Cannot Replace |
| --- | --- | --- |
| `private` | Who can access the member? | Finality/immutability |
| `final` field | Can the field be reassigned after initialization? | Deep immutability, validation |
| `static` | Does the member belong to the class or an instance? | Finality or thread safety |
| `volatile` | What are the visibility/ordering semantics of concurrent field access? | Atomic compound updates, invariants |
| `synchronized` | Which execution paths must share a monitor and associated happens-before guarantees? | Immutable design, business validation |
| `AtomicInteger` | Is read-modify-write atomic for integer state? | Correctness of the entire aggregate |
| `List.copyOf` | Does it provide a structurally unmodifiable snapshot? | Deep copying of every mutable element |
| `final class` | Is extending this class allowed? | Thread safety, non-null state |

Do not combine keywords without understanding their meanings. For example, a final field **is not designed to keep being assigned new values like volatile mutable state**. A `private static final` reference to a mutable HashMap still requires an appropriate concurrency protocol.

## 22. Rules for Choosing `final` by Object Responsibility

| Scenario | Usually Reasonable Decision | Reason |
| --- | --- | --- |
| Immutable order ID | `private final String orderId` | Identity does not change after initialization |
| Display name allowed to change | Non-final field + `rename(...)` | Controlled change |
| Stable service dependency | `private final Repository repository` | Constructor injection, no reassignment |
| Internal list whose elements change | `private final List<Item> items` + commands | The reference does not change, yet the contents can change |
| Small immutable value | `final class` or `record` + immutable fields | No subclassing needed, value semantics |
| Continuously incrementing counter | Non-final primitive/atomic state; possibly a final reference to an atomic object | State must change |
| Public validation pipeline | `public final process()` + protected hook | Prevent overriding to bypass validation |
| Base class extended via inheritance | Non-final class | Has an extension contract |
| Truly fixed constant | `static final` primitive/String/immutable data | Shared value |
| Changing runtime configuration | Provider, method, or controlled mutable state | Do not misuse a compile-time constant |
| Finalized local result | `final` local if it improves clarity | Avoid unintended reassignment |
| Local accumulator | Non-final local | Needs updates across loop iterations |
| Lambda capture | Final or effectively final | Satisfies capture rules |
| DTO/framework proxy | Follow the specific framework's requirements | Do not turn final into an absolute rule |

**There is no “standard final-field ratio” for every project.** The number of final declarations should come from **invariants and legitimate mutability rules**, not a mechanical quota.

## 23. Common Mistakes When Using `final`

1. **“Every field should be final for better code.”** False. State with valid business changes does not need reassignment locked; design appropriate commands and validation instead.
2. **“`final List` is an immutable List.”** False. Final only prevents reassigning the reference; it does not forbid `add/remove` on a mutable List.
3. **“`final Customer c` makes the Customer object unchangeable.”** False for locals/parameters: `c` cannot be reassigned, yet the object itself may be mutable.
4. **“A final reference is always non-null.”** False. `null` can still be assigned once if the type is a reference and the contract does not forbid it.
5. **“A final field automatically validates input.”** False. The compiler checks assignment, not domain rules.
6. **“A final class cannot implement an interface.”** False. It cannot be subclassed, yet it can still implement interfaces.
7. **“A final method prevents all polymorphism.”** False. Other overridable hooks or interface dispatch still work.
8. **“The more final methods, the easier to extend.”** No. Final closes an extension point; you must consider whether clients are meant to override it according to the API.
9. **“No test framework supports final.”** False. Support depends on the framework, version, and configuration.
10. **“Final definitely makes code run faster.”** There is no such guarantee; choose final for semantics.
11. **“`static final` is always a compile-time constant.”** False. Only qualifying constant variables of primitive/String types with valid constant expressions qualify.
12. **“Changing a public static final primitive in a library makes old clients automatically read the new value.”** Not necessarily; it may have been inlined into client bytecode.
13. **“A public static final mutable collection is safe for the entire application.”** False. Callers can still mutate the object if the API allows it.
14. **“Adding final to a dependency prevents all runtime configuration changes.”** False. The provider object stays fixed, yet it can still supply changing data.
15. **“Final eliminates the need for thread synchronization.”** False for mutable state, publication protocols, and nested objects.
16. **“A final parameter changes parameter passing semantics.”** False. Java is still pass-by-value.
17. **“You must write `final` before every lambda-captured variable.”** No. Effectively final is sufficient.
18. **“A final constructor prevents constructor overriding.”** Invalid. Constructors are not overridden.
19. **“`abstract final class` both forbids inheritance and requires inheritance.”** Contradictory; the compiler rejects it.
20. **“`private final` on every helper is always necessary.”** Usually redundant because a private method is already not overridable from subclasses.

## 24. Self-Check Exercises with Answers

**Question 1.** With `private final String id` and `private String name`, what does this split express?

**Answer:** `id` is a stable binding after initialization; `name` can be changed through valid behaviors. The class must still validate both according to its contract.

**Question 2.** Can a field `final List<String> items` have `items.add("A")` called on it?

**Answer:** Yes, if the List object is mutable and the code has access. `final` does not make the List immutable.

**Question 3.** Can a final field receive `null` in the constructor?

**Answer:** Yes, at the language level. However, if the contract requires non-null, the constructor must explicitly reject null.

**Question 4.** Does `final List<String> items` let the constructor skip defensive copying of the input?

**Answer:** No. If the constructor stores a mutable input reference, the caller can mutate the List externally. `List.copyOf` or an appropriate copy helps protect the structure.

**Question 5.** When should a class be declared final?

**Answer:** When the class is not designed as a base class or extension point, for example a concrete implementation or a value object requiring a stable contract. Do not use it if inheritance is an explicit requirement.

**Question 6.** Can a final class participate in polymorphism via an interface?

**Answer:** Yes. It can implement interfaces; it only prohibits subclasses from extending that class.

**Question 7.** Why might a template method be final in an abstract class?

**Answer:** So that all subclasses must go through a mandatory validation/orchestration workflow; subclasses can only customize explicitly opened hooks.

**Question 8.** Does a final method prevent calling an overridable method inside its body?

**Answer:** No. Final prevents overriding the final method itself; calls to other instance hooks can still dispatch dynamically based on the runtime object.

**Question 9.** Can `static final int PAGE_SIZE = 20` cause client bytecode to keep 20 after the library changes it to 50?

**Answer:** Yes, if the value was inlined by the client compiler as a compile-time constant. Consider the public API contract and recompilation.

**Question 10.** Can a service with `private final Clock clock` read a “current time” that changes over time?

**Answer:** Yes. The reference to Clock is not reassigned, yet `clock.instant()` can return different Instants depending on time and implementation.

**Question 11.** Does `final Parameter p` prevent calling a method that mutates the state of object p?

**Answer:** No. It only prevents reassigning the parameter variable `p`; it does not freeze the object.

**Question 12.** Does a lambda require a captured variable to be declared with the final keyword?

**Answer:** No. Effectively final is enough when the local/parameter is not reassigned according to Java's rules.

**Question 13.** Is `final int count` suitable for a counter that changes many times?

**Answer:** No, if you intend to update the `count` field itself. You can use a mutable field with synchronization/atomic operations or a final reference to an atomic counter, depending on the design.

**Question 14.** Does making a field `final` provide unconditional Java Memory Model safe publication?

**Answer:** No. Final fields have special initialization semantics when an object is properly constructed; avoid `this` escaping and still manage mutable state/concurrency separately.

**Question 15.** Should an abstract class be declared final?

**Answer:** No. `abstract` requires subclassing to complete the implementation, whereas `final` forbids subclassing; this combination is invalid.

**Question 16.** Why does `private static final List<String> TAGS = List.of("A")` express intent better than a mutable `public static final ArrayList` used as a constant?

**Answer:** It hides the reference from callers outside the class and uses a structurally unmodifiable List; the String data is immutable. A public mutable ArrayList lets external callers mutate global state even though the field is final.

## 25. Checklist When Deciding Whether to Add `final`

Before using the keyword, ask about **intent**, not just syntax:

1. **Does this field represent identity or stable structure?** If so, consider final.
2. **Does the value need to be chosen at initialization and remain unchanged?** Use a blank final + constructor validation where appropriate.
3. **Does the field hold a mutable reference?** Final is no substitute for defensive copying, read-only exposure, or deep immutability.
4. **Does this state have valid business changes?** If so, do not force final on the value that needs reassignment; expose controlled commands.
5. **Should the dependency be replaced during the object's lifecycle?** If not, final constructor injection is a good choice.
6. **Is the local/parameter reassigned?** You can use final if it improves clarity; there is no need to apply it mechanically.
7. **Will the variable be captured by a lambda?** It only needs to be final or effectively final.
8. **Does the method represent a mandatory workflow that must not be bypassed via overriding?** A final method may be appropriate.
9. **Is the class a public extension point?** If so, do not make the class final; document its hooks and protected APIs.
10. **Can interface/composition be used instead of inheritance?** Consider extending behavior through a dependency.
11. **Is a public static final value truly fixed across versions?** If not, consider an accessor/configuration to avoid constant inlining and coupling.
12. **Does a static final reference point to a mutable object?** Do not expose a global mutable collection without control.
13. **Are there specific ORM/proxy/test framework requirements?** Check compatibility before choosing a final class/method.
14. **Is multi-threading involved?** Final does not replace mutexes/atomics/visibility for state changes after initialization.
15. **Are you adding final just for “performance” or an “everything-final style”?** Prioritize the contract; measure performance if it is truly needed.
16. **For constructors:** ensure blank finals are assigned exactly once on every normal completion path, and avoid exposing `this` before initialization completes.

## Conclusion

`final` is most valuable when it **expresses an intentional design decision**:

- **Final field** protects identity, dependencies, and bindings that should not be reassigned after initialization.
- **Final local/parameter** prevents reassignment when doing so makes the code's meaning clearer.
- **Final method** protects a part of a contract that subclasses must not override.
- **Final class** closes off inheritance when a class is not designed to be inherited from.
- **Static final** expresses shared data with a fixed binding, especially for carefully designed constants.

Remember what `final` **does not do**: it does not automatically validate data, does not guarantee a non-null reference, does not freeze the mutable object inside, does not create thread safety on its own, and does not prove that an API is always valid according to business rules. **Choose `final` based on who owns the data, what is allowed to change, and which boundaries must remain stable** — that is how to use this keyword to make Java classes easier to understand, modify, and maintain over the long term.
