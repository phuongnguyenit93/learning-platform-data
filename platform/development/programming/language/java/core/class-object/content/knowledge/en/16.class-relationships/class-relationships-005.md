# Delegating Operations to a Component Object in Java

## 1. Lesson Objectives

In object-oriented programming, **delegation** is how an object **has another object perform part of the work**. The object that receives the request from the caller is called the **delegating/forwarding object** (*delegator*); the object that performs the specialized work is typically called a **component object, collaborator, or delegate**.

For example, a `Car` has an `Engine`. When a caller calls `car.start()`, `Car` does not necessarily perform the engine-starting logic itself; it can call `engine.start()`:

```java
class Car {
    private final Engine engine = new Engine();

    void start() {
        engine.start();
    }
}
```

The snippet above is a **class-only illustration**, assuming a class `Engine` declares an instance method `start()`. The key point is not the number of lines of code, but the **division of responsibilities**:

- `Car` decides **when** to start.
- `Engine` owns **how to start the engine**.
- The caller only needs the `Car.start()` API and is not required to know that `Engine` is used internally.

This is an important technique for implementing **has-a/uses-a** relationships, reducing coupling, increasing cohesion, and making it possible to change the implementation without having to modify every caller.

After this lesson, you will be able to:

1. Recognize a delegation call in Java code.
2. Write a class with a field referencing a component and methods that forward calls.
3. Distinguish delegation from inheritance, composition, aggregation, and wrapper/decorator.
4. Decide whether to forward all or only part of a component's API.
5. Understand ownership, aliasing, dependency injection, and error handling when a component fails.
6. Test a delegator with a fake collaborator.
7. Detect design flaws: delegation cycles, exposing a mutable component, passing wrong arguments, hiding exceptions, or creating unintended shared state.

## 2. First Example: `Car` Delegates Work to `Engine`

Create the file **`DelegationBasicsDemo.java`**:

```java
class Engine {
    private boolean running;

    void start() {
        if (!running) {
            running = true;
            System.out.println("Engine started");
        }
    }

    boolean isRunning() {
        return running;
    }
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = java.util.Objects.requireNonNull(engine);
    }

    void start() {
        System.out.println("Car receives start request");
        engine.start();
    }

    boolean isRunning() {
        return engine.isRunning();
    }
}

public class DelegationBasicsDemo {
    public static void main(String[] args) {
        Engine engine = new Engine();
        Car car = new Car(engine);

        car.start();
        System.out.println("running=" + car.isRunning());
    }
}
```

Compile and run with Java 17+:

```bash
javac DelegationBasicsDemo.java
java DelegationBasicsDemo
```

**Standard output:**

```text
Car receives start request
Engine started
running=true
```

Let's follow the execution flow:

1. `new Engine()` creates an engine object.
2. `new Car(engine)` creates a car object and holds an `engine` reference in a `private final` field.
3. The caller calls `car.start()`. The receiver of the call is the **Car object**.
4. `Car.start()` prints a message and then calls `engine.start()`. The receiver of the inner call is the **Engine object**.
5. `Engine.start()` changes the Engine's own state and prints `Engine started`.
6. `Car.isRunning()` in turn **delegates the state query** to `Engine.isRunning()`.

This is not a method invocation on the same receiver. The two objects have separate identities and responsibilities:

```text
main
  |
  | car.start()
  v
Car object
  |
  | engine.start()
  v
Engine object
  |
  +-- running: false -> true
```

**An important detail:** `final Engine engine` only prevents the `engine` field from being reassigned to another reference after valid construction; it **does not make Engine immutable**. `engine.start()` still mutates `running`.

## 3. Delegation Is Behavior; Composition Is a Structural Relationship

These two concepts often appear together, but they are **not synonymous**.

- **Composition/has-a:** a class holds a component object in a field, for example `Car` has an `Engine`.
- **Delegation:** a method **calls another object's method to perform the work**, for example `Car.start()` calls `Engine.start()`.
- **Aggregation:** a design description of the relationship between a whole object and a referenced object when lifecycle/ownership has a higher degree of independence; Java has no `aggregation` keyword.
- **Dependency:** a class uses the services of another type, whether through a field, parameter, local variable, or return value.

There can be **composition without delegation**: a class holds a component as data but handles all the logic itself without calling a method on the component.

There can be **delegation without long-term component ownership**: a method receives a collaborator object through a parameter and has it handle the work.

Example of delegation via a parameter:

```java
class ReportPrinter {
    void print(String report, java.io.PrintStream destination) {
        destination.println(report);
    }
}
```

`ReportPrinter` does not have a field holding a `PrintStream`, yet the `print` method still **hands off the actual printing** to the `destination` collaborator. This snippet is an illustrative class without `main`.

### When Is It Called a "Component Object"?

In this lesson, we focus on the case where a class has a **field referencing another object** and forwards part of the work to that object. This is the most common form of delegation in class relationships, but the essence of delegation is **transferring behavior**, not merely having a field.

## 4. How Is a Call Forwarded?

A simple example:

```java
final class OrderService {
    private final PriceCalculator calculator;

    OrderService(PriceCalculator calculator) {
        this.calculator = calculator;
    }

    int total(int price, int fee) {
        return calculator.addFee(price, fee);
    }
}
```

Here `PriceCalculator` is a hypothetical type that has `int addFee(int,int)`; this is an **illustrative snippet, not a standalone program**.

Read the line:

```java
return calculator.addFee(price, fee);
```

- `calculator` is the **receiver reference** of the instance method call.
- `addFee` is selected according to method resolution/dispatch rules.
- The arguments `price` and `fee` are passed by **value** in Java.
- The value returned by the method is forwarded by `OrderService.total` to the caller.
- If the collaborator throws an exception, the exception can **propagate out to the caller**, unless the delegator explicitly handles it.
- If the collaborator has a side effect, the side effect can occur **before the delegator finishes the method**.

There is no special `delegate` syntax in Java for the compiler to do this automatically for regular classes. We write explicit **forwarding methods** (or have a code-generation tool assist according to a specific workflow), and control the contract of the forwarding method.

## 5. A Complete Example: `Order` Delegates Price Calculation

File **`OrderDelegationDemo.java`**:

```java
final class PriceCalculator {
    int total(int basePrice, int shippingFee) {
        if (basePrice < 0 || shippingFee < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        return Math.addExact(basePrice, shippingFee);
    }
}

final class Order {
    private final int basePrice;
    private final PriceCalculator calculator;

    Order(int basePrice, PriceCalculator calculator) {
        if (basePrice < 0) {
            throw new IllegalArgumentException("negative base price");
        }

        this.basePrice = basePrice;
        this.calculator =
                java.util.Objects.requireNonNull(calculator, "calculator");
    }

    int totalWithShipping(int shippingFee) {
        return calculator.total(basePrice, shippingFee);
    }
}

public class OrderDelegationDemo {
    public static void main(String[] args) {
        PriceCalculator calculator = new PriceCalculator();
        Order order = new Order(100, calculator);

        System.out.println(order.totalWithShipping(15));
        System.out.println(order.totalWithShipping(30));
    }
}
```

```bash
javac OrderDelegationDemo.java
java OrderDelegationDemo
```

```text
115
130
```

**Roles:**

- `Order` owns the business context `basePrice` and knows it needs to provide `totalWithShipping`.
- `PriceCalculator` performs the calculation and checks for overflow.
- `Order` does not need to know where the addition details reside; it **delegates** to the calculator.
- The caller uses `Order.totalWithShipping(...)` without having to wonder which field holds the price.
- The dependency is passed through the constructor, so a new `PriceCalculator` does not have to be created every time `totalWithShipping` is called.

Using `Math.addExact` causes overflow to throw an `ArithmeticException` instead of silently wrapping the `int` value; that is the technical contract of the component. The delegator can let the exception propagate when that behavior fits the API.

## 6. Why Not Let the Caller Get the Component Directly and Call It?

Compare two APIs:

**API that exposes the component:**

```java
Engine engine() {
    return engine;
}
```

The caller writes `car.engine().start()`. Then the caller knows that `Car` uses `Engine` and depends on the `Engine` API.

**Intentional delegation API:**

```java
void start() {
    engine.start();
}
```

The caller writes `car.start()` without needing to know how a specific engine is organized.

These are two **contract-dependent** choices, not a single right answer for every system:

- If clients only need to "start the car", `car.start()` hides the details and preserves invariants.
- If the system genuinely needs to expose an engine component as a public API with its own lifecycle, a getter can be reasonable, provided coupling/ownership are managed.
- If `Engine` is mutable, returning the reference directly can allow external code to call `engine.stop()` at a time that is invalid for `Car`.

**Do not expose a getter for every component just because the field is private.** Expose **behavior appropriate for the enclosing object**.

## 7. Delegation Helps Protect the Invariants of the Enclosing Object

Suppose `BankAccount` has a `Balance` component that stores money. If the caller were allowed to modify the Balance object directly, it could break the invariants of BankAccount. An appropriate API lets BankAccount **enforce business conditions** and then delegate the balance-storing operation to the component.

File **`ControlledDelegationDemo.java`**:

```java
final class Balance {
    private int amount;

    Balance(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial");
        }
        amount = initial;
    }

    int amount() {
        return amount;
    }

    void credit(int value) {
        amount = Math.addExact(amount, value);
    }

    void debit(int value) {
        amount = Math.subtractExact(amount, value);
    }
}

final class BankAccount {
    private final Balance balance;

    BankAccount(int initial) {
        balance = new Balance(initial);
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
        balance.credit(amount);
    }

    void withdraw(int amount) {
        if (amount <= 0 || amount > balance.amount()) {
            throw new IllegalArgumentException("invalid withdrawal");
        }
        balance.debit(amount);
    }

    int balance() {
        return balance.amount();
    }
}

public class ControlledDelegationDemo {
    public static void main(String[] args) {
        BankAccount account = new BankAccount(100);

        account.deposit(30);
        account.withdraw(50);
        System.out.println("balance=" + account.balance());

        try {
            account.withdraw(200);
        } catch (IllegalArgumentException ex) {
            System.out.println("withdrawal rejected");
        }

        System.out.println("balance=" + account.balance());
    }
}
```

```bash
javac ControlledDelegationDemo.java
java ControlledDelegationDemo
```

```text
balance=80
withdrawal rejected
balance=80
```

`BankAccount.withdraw` validates the amount before delegating to `Balance.debit`. `Balance` is not public and is not returned via a getter; callers do not call `credit` or `debit` directly, and instead must use the business API of BankAccount.

**Good to know:** `Balance.credit`/`debit` do not check every invariant themselves if called with arbitrary arguments by code that has access within the same package. Therefore, this design assumes that **only BankAccount coordinates the calls**. In a complex library, validation can be added directly inside `Balance` so the component protects its own contract and reduces reliance on every caller using it correctly.

**Do not infer transaction/concurrency guarantees:** the example only handles error checks in a single thread. If multiple threads withdraw concurrently, synchronized check-and-update or an appropriate immutable/atomic design is required.

## 8. Create the Component in the Constructor or Receive It via the Constructor?

Two common approaches:

**The class creates the component itself:**

```java
class Car {
    private final Engine engine = new Engine();
}
```

**Receive the component from the caller:**

```java
class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = java.util.Objects.requireNonNull(engine);
    }
}
```

The difference is not merely syntactic:

| Aspect | Self-created component | Injected via constructor |
| --- | --- | --- |
| Who chooses the implementation? | Enclosing class | Caller/composition root |
| Coupling to concrete type | Usually higher | Can be lower when using an interface |
| Testing with a fake component | Can be harder | Easier |
| Lifecycle management | Enclosing class usually manages it | Must specify who owns/closes the component |
| Multiple instances sharing a component? | Not by default | Caller can share it |
| Component has its own configuration | Must fetch config itself | Can be provided from outside |

**Dependency injection is not always better.** For a small component that is only used internally and does not need implementation swapping or separate testing, creating it internally is reasonable and simple. For a collaborator with I/O, multiple strategies, or a need to substitute it in tests, injecting via the constructor usually makes the design clearer.

### Validate Dependencies Early

Writing:

```java
this.engine = java.util.Objects.requireNonNull(engine, "engine");
```

causes construction of `Car` to fail immediately if the dependency is null, rather than encountering a `NullPointerException` only on a later `start` call. However, **being non-null does not guarantee that the collaborator is functioning properly**, is thread-safe, or has not been closed; those require separate contracts.

## 9. Delegating Through an Interface: Swapping Implementations Without Modifying the Delegator

A more advanced step is for the delegator to hold an **interface** rather than a concrete class.

File **`StrategyDelegationDemo.java`**:

```java
interface ShippingCost {
    int cost(int weight);
}

final class StandardShipping implements ShippingCost {
    @Override
    public int cost(int weight) {
        if (weight <= 0) {
            throw new IllegalArgumentException("weight must be positive");
        }
        return weight <= 5 ? 10 : 20;
    }
}

final class ExpressShipping implements ShippingCost {
    @Override
    public int cost(int weight) {
        if (weight <= 0) {
            throw new IllegalArgumentException("weight must be positive");
        }
        return weight <= 5 ? 25 : 40;
    }
}

final class Checkout {
    private final ShippingCost shippingCost;

    Checkout(ShippingCost shippingCost) {
        this.shippingCost = java.util.Objects.requireNonNull(shippingCost);
    }

    int shipping(int weight) {
        return shippingCost.cost(weight);
    }
}

public class StrategyDelegationDemo {
    public static void main(String[] args) {
        Checkout normal = new Checkout(new StandardShipping());
        Checkout express = new Checkout(new ExpressShipping());

        System.out.println("normal=" + normal.shipping(3));
        System.out.println("express=" + express.shipping(3));
    }
}
```

```bash
javac StrategyDelegationDemo.java
java StrategyDelegationDemo
```

```text
normal=10
express=25
```

`Checkout` receives an object via the `ShippingCost` interface and delegates the cost calculation. **The same Checkout code** can work with two different concrete implementations.

### Delegation and the Strategy Pattern

The example above also illustrates the **Strategy** idea: having a family of algorithms for shipping costs and choosing the implementation via a dependency. The Strategy pattern **typically uses delegation**, but delegation is a broader technique:

- `Car` delegates work to Engine even when there is only one Engine implementation.
- `Checkout` delegates work to ShippingCost and has multiple strategies.
- Not every delegation call requires an interface.
- There is no need to create an interface for every helper class if there is only one stable implementation and no need for an abstraction.

A good choice is based on the **actual points of variation** in the system.

## 10. Delegation Is Not Inheritance

In inheritance, a subclass expresses an **is-a** relationship, for example `ElectricCar extends Car` when it fits the contract. With delegation/composition, the enclosing class has a collaborator and uses it: **has-a**.

| Criterion | Inheritance (`extends`) | Delegation via component |
| --- | --- | --- |
| Primary relationship | is-a | has-a / uses-a |
| Reuse | Inherits behavior from superclass | Calls collaborator methods |
| Coupling | Depends on superclass/hierarchy contract | Depends on component contract |
| Changing behavior | Override instance methods | Replace component/strategy object |
| Exposing methods | Inherited accessible methods are usually part of the API | Select forwarding methods to expose |
| Multiple "sources of functionality"? | Only one direct superclass | Can hold multiple components |
| Lifecycle | Subclass object is also an instance of the superclass | Component has its own identity/lifecycle |
| Runtime dispatch | Overrides dispatched by receiver object | Calls component, then dispatches by runtime component |

**Do not use `extends Engine` just because `Car` wants to call Engine's `start()`.** A car is not an engine. Writing `Car` with an `Engine` and forwarding `start` reflects the domain more accurately.

### A Trap of Inheritance for Reuse

```java
// Flawed modeling idea:
// class Car extends Engine { }
// Car does not mean a kind of Engine.
```

This is an illustration of inappropriate design, **not a statement that Java forbids the syntax**. If the actual classes allow inheritance as far as the compiler is concerned, the code can still compile, but the domain model is incorrect.

**A generally useful principle:** "favor composition/delegation over inheritance" when you want to **reuse behavior without a true is-a relationship**. This is a design guideline, not a rule forbidding all inheritance.

## 11. What Is a Forwarding Method?

A **forwarding method** is a method in the delegator that calls the collaborator to perform the corresponding functionality, often with a similar name/arguments.

```java
class PrinterFacade {
    private final Printer printer;

    PrinterFacade(Printer printer) {
        this.printer = printer;
    }

    void print(String text) {
        printer.print(text);
    }
}
```

Assuming an interface `Printer` has `void print(String)`; this is an illustrative declaration snippet.

However, forwarding **does not have to be one-to-one**:

```java
String displayName(User user) {
    return formatter.format(user.firstName(), user.lastName());
}
```

The second example is a method snippet using hypothetical types; it selects two values from the User object and delegates the formatting to the component. It is still delegation even though the delegator method's name differs from the delegate method's name and the arguments are transformed.

### Three Common Styles of Forwarding

1. **Pass-through forwarding:** `return repository.find(id);`.
2. **Wrapping with business conditions:** validate input, authorization, and state, then call `delegate.execute(...)`.
3. **Combining results:** call one or more collaborators and build a return object suitable for the caller.

A delegator can **coordinate and protect the contract**, not just be a "meaningless forwarding" layer.

## 12. Do Not Unconditionally Expose the Entire API of a Component

If the enclosing object only promises clients `addProduct` and `checkout`, exposing every method of a mutable list or repository as the API can let the caller break invariants.

A dangerous example:

```java
class Cart {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    java.util.List<String> items() {
        return items;
    }
}
```

If the caller obtains the actual list through `cart.items()`, it can call `clear`/`add` directly without Cart validating it. Even though the `items` field is `private final`, the `ArrayList` object is still mutable.

An intentional design:

```java
class Cart {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    void add(String item) {
        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException("item required");
        }
        items.add(item);
    }

    java.util.List<String> snapshot() {
        return java.util.List.copyOf(items);
    }
}
```

`Cart.add` delegates storing the element to `List.add` after validation. `snapshot` delegates copying the data to the collections library; the caller does not receive the internal mutable list.

**That is also delegation**: `Cart` uses the capability of `ArrayList`, but **retains the right to decide the API** that the outside sees.

## 13. Wrapper and Decorator: Use Cases of Delegation

A **wrapper** holds another object and forwards calls; it can add validation, logging, metrics, access control, or change the contract. The **Decorator pattern** is a wrapper pattern intended to add behavior while still providing a compatible interface.

File **`DecoratorDelegationDemo.java`**:

```java
interface Notifier {
    void send(String message);
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("send:" + message);
    }
}

final class LoggingNotifier implements Notifier {
    private final Notifier delegate;

    LoggingNotifier(Notifier delegate) {
        this.delegate = java.util.Objects.requireNonNull(delegate);
    }

    @Override
    public void send(String message) {
        System.out.println("before-send");
        delegate.send(message);
        System.out.println("after-send");
    }
}

public class DecoratorDelegationDemo {
    public static void main(String[] args) {
        Notifier notifier =
                new LoggingNotifier(new ConsoleNotifier());

        notifier.send("hello");
    }
}
```

```bash
javac DecoratorDelegationDemo.java
java DecoratorDelegationDemo
```

```text
before-send
send:hello
after-send
```

Here:

- `LoggingNotifier` **implements the same interface** `Notifier`, so callers can use it instead of ConsoleNotifier under the contract.
- It **does not extend ConsoleNotifier**; it holds a `Notifier` in the `delegate` field.
- `send` adds logging behavior before and after, and then **delegates** to the collaborator.
- The caller does not need to know how many layers of decorators are nested.

**Note on errors:** if `delegate.send(message)` throws an exception, the `after-send` line **does not run** in the current code. If you also want to log failures, you must design `try/finally` or catch the exception according to the contract. Do not log "sent successfully" when the component actually fails.

## 14. Wrapping and Forwarding Interface Methods: `@Override` Policy

When a wrapper implements an interface, the interface methods to be implemented must have valid access, typically `public` for methods of a public interface.

For example:

```java
interface ClockSource {
    long millis();
}

class FixedClock implements ClockSource {
    @Override
    public long millis() {
        return 1000L;
    }
}
```

`FixedClock` can be package-private, but the `millis` implementation method must be `public` because it implements the corresponding interface contract.

If a wrapper implements `ClockSource`:

```java
class MonitoredClock implements ClockSource {
    private final ClockSource delegate;

    MonitoredClock(ClockSource delegate) {
        this.delegate = delegate;
    }

    @Override
    public long millis() {
        return delegate.millis();
    }
}
```

`@Override` lets the compiler verify that the method has the right signature; it **does not generate forwarding automatically**. The developer still has to write the collaborator call inside the method body.

**Do not assume that** merely writing `implements SomeInterface` will automatically forward all calls to the `delegate` field. Java does not have automatic delegation for ordinary classes like the `by` syntax of some other languages.

## 15. A Component Can Support Many Methods; the Delegator Chooses Only What It Needs

A `List` has many operations such as `add`, `remove`, `clear`, `set`, and `get`. A class managing a list might decide to expose only:

- `addValidItem(String)`: with validation.
- `count()`: queries the count.
- `snapshot()`: an unmodifiable copy.

There is no need to write a forwarding method for **every** method of List.

File **`SelectiveDelegationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class GuestList {
    private final List<String> guests = new ArrayList<>();

    void register(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("invalid guest");
        }
        if (guests.contains(name)) {
            throw new IllegalArgumentException("duplicate guest");
        }
        guests.add(name);
    }

    int size() {
        return guests.size();
    }

    List<String> snapshot() {
        return List.copyOf(guests);
    }
}

public class SelectiveDelegationDemo {
    public static void main(String[] args) {
        GuestList list = new GuestList();

        list.register("An");
        list.register("Binh");

        System.out.println("count=" + list.size());
        System.out.println(list.snapshot());
    }
}
```

```bash
javac SelectiveDelegationDemo.java
java SelectiveDelegationDemo
```

```text
count=2
[An, Binh]
```

`GuestList` **delegates storage and querying** to `ArrayList`, while not letting callers arbitrarily call `clear` or replace slots. We keep the **API granularity appropriate for the domain**.

If the caller needs a feature to remove a registered person, add a method with a specific name and business conditions; there is no need to expose the whole mutable list.

## 16. Multiple Components: Dividing Work by Specialization

A class can hold **multiple collaborators** and coordinate them, with each collaborator responsible for a specific part of the work.

Example of checkout processing:

```text
CheckoutService
   |
   +-- PriceCalculator       -> calculate total
   |
   +-- PaymentGateway        -> request payment
   |
   +-- ReceiptFormatter      -> format receipt
```

If all logic is written into `CheckoutService`, the class may have too many responsibilities. If it is split into three collaborators and uses delegation, each component becomes easier to test and replace.

### Runnable Example Without External Services

File **`MultiComponentDelegationDemo.java`**:

```java
final class PriceCalculator {
    int total(int base, int shipping) {
        if (base < 0 || shipping < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        return Math.addExact(base, shipping);
    }
}

final class PaymentGateway {
    boolean pay(int amount) {
        System.out.println("charged=" + amount);
        return true;
    }
}

final class ReceiptFormatter {
    String format(int amount) {
        return "receipt:" + amount;
    }
}

final class CheckoutService {
    private final PriceCalculator calculator;
    private final PaymentGateway gateway;
    private final ReceiptFormatter formatter;

    CheckoutService(PriceCalculator calculator,
                    PaymentGateway gateway,
                    ReceiptFormatter formatter) {
        this.calculator =
                java.util.Objects.requireNonNull(calculator);
        this.gateway = java.util.Objects.requireNonNull(gateway);
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }

    String checkout(int base, int shipping) {
        int total = calculator.total(base, shipping);
        if (!gateway.pay(total)) {
            throw new IllegalStateException("payment rejected");
        }
        return formatter.format(total);
    }
}

public class MultiComponentDelegationDemo {
    public static void main(String[] args) {
        CheckoutService service = new CheckoutService(
                new PriceCalculator(),
                new PaymentGateway(),
                new ReceiptFormatter());

        System.out.println(service.checkout(100, 15));
    }
}
```

```bash
javac MultiComponentDelegationDemo.java
java MultiComponentDelegationDemo
```

```text
charged=115
receipt:115
```

**Note on the example's limitations:** `PaymentGateway` here is just a simple in-memory/console-printing fake and always returns true; it is not a real payment gateway. In a real system, payment, saving to a database, and sending events can have **side effects that do not automatically roll back** if the formatter or a subsequent step fails. Delegation **does not automatically provide transactions** across multiple collaborators.

## 17. A Delegator Can Transform Arguments or Results

Delegation does not have to be an exact pass-through with the same parameter list. A delegator can:

- Normalize input before forwarding.
- Check access permissions.
- Convert units of measurement, DTOs, or domain values.
- Combine results from multiple calls.
- Convert output into an abstraction suitable for the caller.

File **`TransformingDelegationDemo.java`**:

```java
final class TemperatureConverter {
    double celsiusToFahrenheit(double celsius) {
        return celsius * 9.0 / 5.0 + 32.0;
    }
}

final class WeatherDisplay {
    private final TemperatureConverter converter =
            new TemperatureConverter();

    String displayFahrenheit(double celsius) {
        double fahrenheit = converter.celsiusToFahrenheit(celsius);
        return String.format(java.util.Locale.ROOT, "%.1f F", fahrenheit);
    }
}

public class TransformingDelegationDemo {
    public static void main(String[] args) {
        WeatherDisplay display = new WeatherDisplay();
        System.out.println(display.displayFahrenheit(0));
        System.out.println(display.displayFahrenheit(100));
    }
}
```

```bash
javac TransformingDelegationDemo.java
java TransformingDelegationDemo
```

```text
32.0 F
212.0 F
```

Here `WeatherDisplay` does not merely forward the `double` result; it delegates the temperature conversion to `TemperatureConverter` and then builds a formatted string for display purposes. If the external interface should return a value object instead of a string, that is a separate design decision.

## 18. Delegation Does Not Automatically Mean a "100% Pure Method"

A delegator can call a collaborator that causes side effects:

```java
void send(String message) {
    notifier.send(message);
}
```

If `notifier` sends an email or writes to a file, the call has external effects. Even though `send` is only one line of code, the enclosing class is still responsible for its **public contract**:

- If the input is invalid, should it be rejected before sending?
- If the collaborator returns false, what does the caller receive?
- If the collaborator throws an exception, should it retry?
- After an exception, did the operation partially succeed or not?
- Are logs/metrics/auditing needed?
- Can it be called again safely?

**Do not use a forwarding method to hide system errors that the caller needs to know about.** Short forwarding does not make side effects disappear.

## 19. Handling Exceptions When a Delegate Fails

A simple strategy: **let the exception propagate** when it fits the delegator's contract.

```java
int total(int price, int fee) {
    return calculator.total(price, fee);
}
```

If the calculator throws `IllegalArgumentException` due to negative input and that is also the contract of `total`, the delegator does not need a pointless `try/catch`.

When you want to provide an error at an appropriate level of abstraction:

```java
String load(String id) {
    try {
        return repository.read(id);
    } catch (java.io.IOException ex) {
        throw new IllegalStateException("Cannot load " + id, ex);
    }
}
```

This is an **illustrative method snippet**, assuming `repository.read` is declared to throw `IOException`. The `IllegalStateException(String, Throwable)` constructor preserves the **cause** for diagnosis.

**Pitfalls:**

- Do not write `catch (Exception ex) { return null; }` just to stop the caller from seeing errors; it can hide corrupted data/side effects.
- Do not automatically retry a method that has payment, DB write, or message-sending effects if there is no idempotency contract.
- If the delegator performs a mutation before calling the collaborator and the collaborator fails, the enclosing object can be left in an incomplete state. Consider validate/compute-before-commit, rollback, or properly scoped transactions.
- If the delegate returns a nullable result, the delegator must decide whether to accept null, wrap it in `Optional`, or throw an error — do not assume "the delegate always returns an object".

## 20. A "Call Then Fail" Example Showing Why Ordering Matters

Suppose:

```java
void placeOrder(Order order) {
    order.markPaid();
    gateway.charge(order.total()); // May fail.
}
```

This is a **hypothetical API snippet**, not a standalone runnable program. If `charge` fails after `markPaid`, the Order object has already transitioned to the paid state even though payment was not carried out.

This can be improved by designing the business boundaries:

1. Validate the request/order first.
2. Define which state is considered **committed**.
3. Delegate the payment operation to the gateway.
4. Update the order state based on the **reliable result** of the transaction.
5. If there is a DB and an out-of-process gateway, use patterns such as outbox/idempotency/saga when appropriate.

Delegation helps **separate where work is executed**, but **does not replace consistent state coordination**.

## 21. Managing Component Ownership and Lifecycle

A `private final Repository repository` field does not specify who **owns** the repository. There are at least two situations:

**(A) The enclosing object creates and manages the component itself:**

```java
class ReportService {
    private final Formatter formatter = new Formatter();
}
```

**(B) The enclosing object borrows/shares a dependency from the caller:**

```java
class ReportService {
    private final Formatter formatter;

    ReportService(Formatter formatter) {
        this.formatter = formatter;
    }
}
```

Both snippets are **illustrative**, assuming `Formatter` exists. It should be clearly specified:

- Who is allowed to change the component's configuration?
- Is the component shared among multiple delegators?
- Is the component thread-safe?
- Who creates/closes the resource if it implements `AutoCloseable`?
- When the outer object's lifecycle ends, is the component still used elsewhere?

### Example with a Resource

If a delegator receives a `java.io.Writer` provided by the caller, the delegator **should not arbitrarily call `close()`** in any method unless the API explicitly states that the delegator owns the Writer. Conversely, if the delegator itself creates the resource and promises to manage its lifecycle, it must have an appropriate cleanup mechanism.

**Do not apply mechanically:** "composition must always close every component", or "dependency injection must never close". Ownership is an **architectural contract** that must be defined explicitly.

## 22. Delegation and `final` References

A common pattern:

```java
private final PaymentGateway gateway;
```

`final` means the `gateway` field is not reassigned after valid construction, ensuring that the delegator continues to use **the same collaborator reference**.

However:

- The gateway object itself can still be mutable and have a cache, connection pool, or counters.
- If the component has setters called from elsewhere, the delegator's behavior can change even though the field is final.
- `final` does not make method calls thread-safe.
- `final` does not prevent the component from being closed elsewhere when there is shared ownership.
- If you need to change strategies at runtime, you can use a separate state-management approach or create a new delegator with a different dependency.

In many designs, **constructor injection + a private final field** is a good default when the collaborator does not need to change after construction, but this is an API decision, not a mandatory requirement of delegation.

## 23. Avoiding Uncontrolled Aliasing of Mutable State

File **`SharedComponentDemo.java`**:

```java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int get() {
        return value;
    }
}

class Dashboard {
    private final Counter counter;

    Dashboard(Counter counter) {
        this.counter = counter;
    }

    void record() {
        counter.increment();
    }

    int total() {
        return counter.get();
    }
}

public class SharedComponentDemo {
    public static void main(String[] args) {
        Counter shared = new Counter();

        Dashboard first = new Dashboard(shared);
        Dashboard second = new Dashboard(shared);

        first.record();
        second.record();

        System.out.println(first.total());
        System.out.println(second.total());
    }
}
```

```bash
javac SharedComponentDemo.java
java SharedComponentDemo
```

```text
2
2
```

The two Dashboard objects **share one Counter component**, because the caller passed the same `shared` reference to both constructors. As a result, both see count=2.

If the goal is for **each dashboard to have its own counter**, two separate Counter objects must be created (or the counter can be placed inside a private constructor and not shared). If the goal is a **shared counter**, the behavior is intentional, but concurrency must be accounted for.

**Delegation does not automatically define ownership, identity, or sharing.** Check where the component is created and how it is passed.

## 24. Testing Delegation with a Fake Collaborator

One benefit of designing with collaborator injection is that we can use a fake to **verify whether the delegator calls the right dependency** without needing a network, DB, or mocking framework.

File **`DelegationTestDemo.java`**:

```java
interface MessageSender {
    void send(String text);
}

final class FakeSender implements MessageSender {
    int calls;
    String lastMessage;

    @Override
    public void send(String text) {
        calls++;
        lastMessage = text;
    }
}

final class GreetingService {
    private final MessageSender sender;

    GreetingService(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }

    void greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        sender.send("Hello " + name);
    }
}

public class DelegationTestDemo {
    public static void main(String[] args) {
        FakeSender fake = new FakeSender();
        GreetingService service = new GreetingService(fake);

        service.greet("An");

        if (fake.calls != 1 || !"Hello An".equals(fake.lastMessage)) {
            throw new AssertionError("delegation failed");
        }

        System.out.println("calls=" + fake.calls);
        System.out.println("message=" + fake.lastMessage);
    }
}
```

```bash
javac DelegationTestDemo.java
java DelegationTestDemo
```

```text
calls=1
message=Hello An
```

The test verifies:

1. `GreetingService.greet("An")` does call the sender.
2. The call happens **once**.
3. The argument is forwarded correctly.
4. There is no need to create a real email client or service.

This is a **manual fake test using `main`**, not JUnit. In a real project, JUnit and mocks can be used when helpful. Do not only test "the method was called" while ignoring the **observable result/contract** of the business logic.

## 25. Testing the Failure Path Too: The Delegate Throws an Exception

A fake collaborator can be designed to throw an exception, thereby verifying how the delegator handles errors.

File **`DelegationFailureDemo.java`**:

```java
interface Sender {
    void send(String message);
}

final class FailingSender implements Sender {
    @Override
    public void send(String message) {
        throw new IllegalStateException("network unavailable");
    }
}

final class AlertService {
    private final Sender sender;

    AlertService(Sender sender) {
        this.sender = sender;
    }

    void alert(String message) {
        sender.send("ALERT:" + message);
    }
}

public class DelegationFailureDemo {
    public static void main(String[] args) {
        AlertService service = new AlertService(new FailingSender());

        try {
            service.alert("disk full");
        } catch (IllegalStateException ex) {
            System.out.println("failure=" + ex.getMessage());
        }
    }
}
```

```bash
javac DelegationFailureDemo.java
java DelegationFailureDemo
```

```text
failure=network unavailable
```

`AlertService.alert` does not catch the exception; it propagates to the caller according to Java semantics. This is valid behavior if the contract of AlertService wants the caller to know about the error. For a different API, we might wrap the exception into a dedicated error type or return an explicit error status; what matters is **not claiming the notification was sent when the collaborator failed**.

## 26. Multi-Layer Delegation and Call Tracing

Delegation can be organized into multiple layers:

```text
API Controller
    |
    v
OrderService
    |
    v
OrderRepository
    |
    v
Storage Client
```

Each layer has a different role. This is one way to build a **layered architecture**, though more layers are not always better.

File **`DelegationChainDemo.java`**:

```java
class Storage {
    String load(String key) {
        System.out.println("Storage.load");
        return "value:" + key;
    }
}

class Repository {
    private final Storage storage = new Storage();

    String find(String key) {
        System.out.println("Repository.find");
        return storage.load(key);
    }
}

class Service {
    private final Repository repository = new Repository();

    String get(String key) {
        System.out.println("Service.get");
        return repository.find(key);
    }
}

public class DelegationChainDemo {
    public static void main(String[] args) {
        Service service = new Service();

        System.out.println(service.get("A"));
    }
}
```

```bash
javac DelegationChainDemo.java
java DelegationChainDemo
```

```text
Service.get
Repository.find
Storage.load
value:A
```

This chain makes it easy to observe **which delegator calls which collaborator**, and how the resulting data flows back up. If there is only a simple behavior, creating 3 layers just to forward calls can be **overengineering**; choose the number of layers according to actual responsibilities and change requirements.

### Dangerous Delegation Cycles

If `A.process()` calls `B.process()` and `B.process()` in turn calls `A.process()` with no stopping point, the program can recurse infinitely and hit a `StackOverflowError`. A cycle of object references is not automatically a bug, but a **delegation cycle in the call flow without a stopping condition** is a problem.

Define the **direction of dependencies** and ensure a method terminates at a component that performs actual work, rather than merely passing responsibility around in circles.

## 27. Delegation and Dynamic Polymorphism of the Component

If the delegator's field has an interface type, a `delegate.method()` call can dispatch to a concrete implementation according to the runtime object:

```java
interface Formatter {
    String format(String name);
}

class UppercaseFormatter implements Formatter {
    @Override
    public String format(String name) {
        return name.toUpperCase(java.util.Locale.ROOT);
    }
}

class FormatterService {
    private final Formatter formatter;

    FormatterService(Formatter formatter) {
        this.formatter = formatter;
    }

    String show(String name) {
        return formatter.format(name);
    }
}
```

These are valid class/interface declarations, without `main`.

- **Delegation** itself is `FormatterService.show` calling `formatter.format`.
- **Polymorphism** selects the concrete implementation of `format` based on the runtime type of the Formatter object.
- **Composition** is holding Formatter via a field.
- These three elements work together, but they are not synonymous.

If the collaborator method is **static**, it is not dynamically dispatched at runtime like an instance override. Static utility calls such as `Math.max(...)` are **using a static helper**, not the "instance delegation via a component" form we are focusing on here.

## 28. Concurrency: A Delegator Does Not Automatically Make a Component Thread-Safe

If a mutable component is shared among multiple delegators or multiple threads, operations that need protection do not automatically become safe just because they are called through a wrapper.

Example of the risk:

```java
class Counter {
    private int count;

    void increase() {
        count++;
    }
}
```

Two threads calling `dashboard.record()` on a shared Counter can cause lost updates because `count++` is not an atomic read-modify-write operation.

A version of the component using an atomic type:

```java
class Counter {
    private final java.util.concurrent.atomic.AtomicInteger count =
            new java.util.concurrent.atomic.AtomicInteger();

    void increase() {
        count.incrementAndGet();
    }

    int value() {
        return count.get();
    }
}
```

The two `Counter` snippets are **alternative approaches**, not placed simultaneously in the same source set.

**Do not confuse:**

- `private final Counter counter` fixes the reference; it does not automatically protect `counter.increase()`.
- `synchronized` in one delegator is not sufficient if elsewhere the same component is called directly outside that monitor.
- An operation consisting of multiple calls to a component may require atomicity across **the entire business sequence**, not just atomicity of each individual call.
- If a component is shared, the concurrency policy must be consistent across all callers.

## 29. Avoiding a "God Object" That Just Does the Work of All Components

A good delegator coordinates only appropriate responsibilities. However, if every operation in the system passes through an `ApplicationManager` class with hundreds of forwarding methods, the class can become a **god object**.

Signs:

- Public methods only have generic names like `doTask1`, `doTask2`.
- The enclosing object holds too many unrelated components.
- A client that only needs one small feature still has to import a large manager.
- Every change in any domain requires modifying the manager.
- The component's API surface is copied verbatim even when unnecessary.

How to improve:

1. Group components along **domain/use-case boundaries**.
2. A delegator should provide **behavior at the right level of abstraction**.
3. If a client legitimately needs to use a collaborator directly, inject that collaborator/interface itself instead of forcing calls through the manager.
4. Do not create a forwarding layer if it does not provide a valuable invariant, lifecycle, security boundary, orchestration, or API stability.

**Delegation is not an end in itself.** It is a technique that helps collaborating objects have clear responsibilities.

## 30. When Should You Choose Delegation Over Inheritance?

A quick checklist:

- If object A **is not a kind of** object B, do not `extends B` just to call a method.
- If A needs to use **part of the capabilities** of B, a component field + method forwarding is usually appropriate.
- If you need to **swap the implementation** at runtime or in tests, inject an interface collaborator.
- If you need to **add behavior** before/after a method while keeping the same interface, a wrapper/decorator may be appropriate.
- If you only use a universal stateless helper like `Math.abs`, you can call the static method directly without necessarily creating a component.
- If A truly is a subtype of B under all client expectations, inheritance/interface implementation may still be appropriate.
- If the component needs its own lifecycle, decide ownership first.
- If the enclosing API must protect invariants, do not indiscriminately expose a mutable collaborator.

### Key Question

> "Should the client tell object A: *perform this business behavior*, or does the client need to know B and coordinate all of B's methods itself?"

If the answer is behavior at the level of A, consider an `A.operation()` API that delegates to B internally. If the client is genuinely a valid consumer of B, sometimes providing B directly via dependency injection is simpler.

## 31. Common Mistakes

| Mistake | Why it is wrong / dangerous | How to handle it |
| --- | --- | --- |
| Using `extends` just to reuse a utility method | Incorrect is-a model | Use an appropriate component or helper |
| Assuming a component field automatically creates delegation | Java does not auto-forward methods | Write explicit forwarding methods |
| Returning a mutable component via a public getter | Caller can bypass invariants | Expose behavior or a snapshot |
| Declaring a `final` field and believing the component is immutable | Final only fixes the reference | Design mutability/ownership separately |
| Creating a component on every call even when state needs to be kept | State can be lost and resources wasted | Keep a field / configure the lifecycle properly |
| Unintentionally creating a static shared component for all instances | Shared mutable state is hard to control | Instance dependency or inject intentionally |
| Not checking for null dependencies in the constructor | Late and confusing failures | `Objects.requireNonNull` where appropriate |
| Wrapper implements an interface but narrows method access | Interface method contract requires public | Use `public`/`@Override` properly |
| Changing the signature when forwarding without stating it clearly | Caller does not know the behavior/validation | Design the API and document clearly |
| Swallowing exceptions from a collaborator | Hides failures, unclear state | Propagate or translate errors with a cause |
| Unconditionally retrying an external operation | Side effects may repeat | Idempotency/retry contract |
| Creating an A→B→A cycle with no stopping point | Can stack overflow | Break the cycle and separate responsibilities |
| Treating a wrapper as thread-safe because it has a final field | Mutable delegate still has races | Synchronize/make atomic per contract |
| Too many pointless forwarding layers | Coupling and complexity increase | Only add a layer when it provides value |
| Testing only output without checking delegate calls for important behavior | Easy to forward wrong arguments | Test behavior + fake collaborator |
| Testing only invocation without checking invariants | Misses domain bugs | Test results, errors, and state |
| A collaborator closes a resource owned by the caller | Breaks ownership | Clearly define who closes it |
| Overusing interfaces for every helper | Over-abstraction | Only create interfaces when there is a real contract/variation |
| Assuming delegation always has transactions | Each component has its own failure modes | Orchestrate transactions/compensation |
| Confusing delegation with aggregation | One is call behavior, the other describes object relations | Distinguish structure and behavior |

## 32. Comprehensive Practice: Delegating to a Storage Object

Problem: design `Library` to allow callers to register a book title and query the count, without being able to directly mutate the stored data. `Library` holds a `BookStore` component dedicated to storage.

File **`LibraryDelegationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class BookStore {
    private final List<String> titles = new ArrayList<>();

    void add(String title) {
        titles.add(title);
    }

    boolean contains(String title) {
        return titles.contains(title);
    }

    int count() {
        return titles.size();
    }

    List<String> snapshot() {
        return List.copyOf(titles);
    }
}

final class Library {
    private final BookStore store;

    Library(BookStore store) {
        this.store = Objects.requireNonNull(store);
    }

    void register(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title required");
        }
        String normalized = title.trim();

        if (store.contains(normalized)) {
            throw new IllegalArgumentException("duplicate title");
        }

        store.add(normalized);
    }

    int numberOfBooks() {
        return store.count();
    }

    List<String> catalog() {
        return store.snapshot();
    }
}

public class LibraryDelegationDemo {
    public static void main(String[] args) {
        Library library = new Library(new BookStore());

        library.register(" Java Core ");
        library.register("Clean Code");

        System.out.println("count=" + library.numberOfBooks());
        System.out.println("catalog=" + library.catalog());

        try {
            library.register("Java Core");
        } catch (IllegalArgumentException ex) {
            System.out.println("duplicate rejected");
        }

        System.out.println("count=" + library.numberOfBooks());
    }
}
```

```bash
javac LibraryDelegationDemo.java
java LibraryDelegationDemo
```

```text
count=2
catalog=[Java Core, Clean Code]
duplicate rejected
count=2
```

**Responsibility analysis:**

- `BookStore` handles storing/querying the list.
- `Library` owns the domain rules: non-blank title, trimming leading/trailing whitespace, and rejecting duplicates.
- `Library.register` **delegates `contains` and `add`** to store after validation.
- `numberOfBooks` **delegates `count`**.
- `catalog` delegates creating a snapshot without returning the original mutable list.
- Callers only see the Library API and do not need to call BookStore methods directly.

**Extension point:** If `BookStore` is shared across multiple Library objects or multiple threads, the `contains` + `add` operations must be synchronized to avoid races/duplicates. This single-threaded example does not solve atomicity on its own.

## 33. Improvement Exercises Based on the Library Example

After running `LibraryDelegationDemo`, try:

1. Add an `unregister(String)` method to `Library` with explicit validation, delegating removal to the store.
2. Convert `BookStore` into a `CatalogStore` interface with `add`, `contains`, `count`, and `snapshot`; create `InMemoryCatalogStore` to implement it.
3. Write a `FakeCatalogStore` that records the passed argument, and test that `Library.register` trims the title.
4. Add a condition allowing at most three titles; place the validation in the Library API, and verify that an error does not modify the list.
5. Try returning the internal mutable list through a getter, and observe why the caller can break invariants.
6. If two threads register the same title concurrently, redesign check-and-add into an atomic operation inside the component or coordinate locking.
7. If the store actually accesses a database, define the contract for I/O errors, transactions, and lifecycle.

### Suggested Architecture After Improvements

```text
Client
  |
  | library.register("Java")
  v
Library
  |
  | catalogStore.registerIfAbsent("Java")
  v
CatalogStore interface
  |
  +-- InMemoryCatalogStore
  |
  +-- DatabaseCatalogStore
```

Designing `registerIfAbsent` as a single operation on the component can avoid having the delegator separate `contains` and `add` in a concurrent environment. When using a database, the implementation also needs appropriate constraints/indexes/transactions.

## 34. Self-Check Questions with Answers

**Question 1.** A class A has a field B, yet has never called a method on B. Is it certain that delegation has been used?

**Answer:** Not necessarily. A has a **reference/component relationship**, whereas delegation refers to A delegating the execution of behavior to B.

**Question 2.** `car.start()` calls `engine.start()` internally. Are the receivers of the outer call and the inner call the same object?

**Answer:** No. Outside, the receiver is the Car object; inside, the receiver is the Engine object.

**Question 3.** Does delegation require using an interface?

**Answer:** No. You can delegate to a concrete class; an interface is useful when there is an abstract contract or a need to swap implementations.

**Question 4.** Does using `private final Engine engine` make Engine state immutable?

**Answer:** No. Final only fixes the field reference; Engine can still be mutated.

**Question 5.** Should a class that has a component expose a getter that directly returns the component?

**Answer:** No. Consider the API at the domain level and the risk of callers bypassing invariants.

**Question 6.** Why is `Car extends Engine` usually inappropriate?

**Answer:** A Car **has** an engine, not a kind of engine. Delegation represents has-a more accurately than inheritance is-a.

**Question 7.** Is a wrapper that implements the `Notifier` interface and calls `delegate.send()` a decorator?

**Answer:** It can be a decorator when the wrapper keeps the same contract and adds behavior; if it only forwards as-is, it may just be a forwarding wrapper.

**Question 8.** Does `@Override` on a forwarding method automatically generate the code that calls the collaborator?

**Answer:** No. The developer must write the body.

**Question 9.** When a component is injected via the constructor, who must close it?

**Answer:** It depends on the ownership contract; it cannot be inferred from injection alone. You must specify who owns/closes it and whether there are shared consumers.

**Question 10.** If the delegate throws an exception, does the delegator automatically roll back state by default?

**Answer:** No. The exception propagates if not caught; rollback must be designed explicitly.

**Question 11.** When the same mutable Counter is injected into two Dashboards, can a count change on one side be seen on the other?

**Answer:** Yes. Both hold aliases to the same Counter object.

**Question 12.** Is the static utility method `Math.max` delegation to a component instance?

**Answer:** Not in the context of this lesson; that is a static helper call that does not need a component object to receive the call.

**Question 13.** Does a delegator need to copy all methods of a component into its public API?

**Answer:** No. Expose only the behavior needed by the client, optionally validating/transforming/composing.

**Question 14.** If multiple threads concurrently execute `contains` and then `add` to a store, does delegation automatically guarantee uniqueness?

**Answer:** No. Check-then-act has a race condition; an atomic operation or appropriate synchronization/transaction is required.

**Question 15.** How can you test a delegator without making network calls?

**Answer:** Inject a fake collaborator implementing the same interface and verify the input, call count, outcome, and exception behavior.

**Question 16.** What can the cycle `A.go() -> B.go() -> A.go()` cause?

**Answer:** Without a stopping condition, calls repeat infinitely until a stack overflow or similar error occurs.

**Question 17.** If a delegator only forwards a single method, is it always a bad design?

**Answer:** No. It can stabilize the public API, protect lifecycle, support testing/mocking, or represent a domain abstraction. However, a layer that provides no value should be reconsidered.

**Question 18.** Can the Strategy pattern use delegation?

**Answer:** Yes. The context typically holds a strategy object and calls the strategy method; delegation is broader than Strategy.

## 35. Code Review Checklist

- [ ] Do the delegator and collaborator have **clearly distinct responsibilities**?
- [ ] Is there a genuine has-a/uses-a relationship rather than misusing inheritance?
- [ ] Does the component field have an appropriate `private` scope?
- [ ] Does the constructor receive/create the collaborator in accordance with its ownership/lifecycle?
- [ ] Are dependencies checked early for null/valid configuration?
- [ ] Are interfaces created only when there is clear abstraction/variation or a clear contract?
- [ ] Do public methods provide **behavior at the delegator level** without exposing unnecessary details?
- [ ] Is a mutable component or shared collection accidentally exposed via a getter?
- [ ] Are arguments validated/normalized before forwarding when needed?
- [ ] Does the return value match the type/contract the caller expects?
- [ ] Are exceptions/cause/retry/idempotency handled within the scope of responsibility?
- [ ] Does the delegation perform a mutation before a call that can fail?
- [ ] If there are multiple collaborators, do the steps require transactions/compensation?
- [ ] Is the component shared across multiple delegators or threads?
- [ ] Is the mutable component thread-safe; do multiple operations need an atomic boundary?
- [ ] Is it specified who closes resources and when?
- [ ] Are there delegation cycles or unnecessary layering?
- [ ] Do tests have a fake collaborator verifying input, call count, results, and failure paths?
- [ ] Are invariants protected when a component changes or fails?
- [ ] Do the Java examples have filenames matching the public class, with accurate `javac`/`java` commands and stdout?

---

**Remember:** **Delegating operations to a component object** is when an object **holds or receives a collaborator and then calls the collaborator's method to perform the appropriate part of the work**. Composition/has-a describes the **structural relationship**, whereas delegation describes **how behavior is carried out**. When well designed, the delegator exposes an API at the right level of responsibility, keeps the component internal, validates/coordinates where appropriate, and can swap implementations via an interface when needed. Delegation does not automatically make an object immutable, does not automatically guarantee thread safety or transactions, and does not require creating a wrapper for every method. Use it to **divide responsibilities and keep object boundaries clear**, not merely to forward calls for the sake of having a layer.
