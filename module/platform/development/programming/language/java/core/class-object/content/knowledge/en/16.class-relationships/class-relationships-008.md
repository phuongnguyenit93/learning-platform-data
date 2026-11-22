# Choosing Composition or Inheritance for a Specific Requirement in Java

When designing object-oriented software, both **inheritance** and **object composition** can help reuse code and extend behavior. However, they **do not solve the exact same problem**. Choosing between them should be based on the **relationship meaning**, **behavioral contract**, **what is expected to change**, and **object lifecycles**, rather than on which approach takes fewer lines.

Two starting questions:

- **Is A truly a kind of B?** If every A object must be validly usable where B is required, and the hierarchy has a stable meaning, consider **inheritance/implements**.
- **Does A have a B, use a B, or delegate work to B?** If A collaborates with B to perform work, needs to swap functionality, or combines multiple capabilities, consider **composition + delegation**, often paired with an interface.

For example:

```java
class ReportService {
    private final Formatter formatter;

    ReportService(Formatter formatter) {
        this.formatter = formatter;
    }
}
```

`ReportService` **uses a `Formatter`**, not “is a Formatter”. Therefore, a reference field and delegation to Formatter are more semantically accurate than `class ReportService extends Formatter`.

Conversely:

```java
interface Shape {
    double area();
}

final class Rectangle implements Shape {
    // Implements the Shape contract.
}
```

`Rectangle` **is a `Shape`** under the abstraction contract, so implementing this interface makes sense. In Java, **`implements` for an interface and `extends` for a class are two different mechanisms**; both create type relationships, while inheritance from a class also shares implementation and couples to superclass state.

**Guiding conclusion:** *Prefer composition when behavior collaboration or swapping is needed; use inheritance when there is a true subtype and a stable inheritance contract*. This is a **heuristic**, not a rule forbidding inheritance.

This article uses **Java 17+**, presenting a step-by-step selection process, an example comparing the same requirement using two designs, cases where inheritance should or should not be used, along with a Java program with `javac`/`java` commands and stdout.

## 1. Defining the Relationships Correctly

### 1.1. Inheritance: The is-a Relationship

When writing:

```java
class Dog extends Animal {
}
```

`Dog` is a subtype of `Animal` through an inheritance relationship. In code, an `Animal` variable can hold a `Dog` object if access permissions and type conditions are satisfied.

When writing:

```java
class Dog implements Pet {
}
```

`Dog` commits to implementing `Pet`, a behavioral abstraction; this also enables using a `Dog` wherever a `Pet` is accepted.

**However, the two are not identical:**
- `extends` on a class carries an inheritance relationship of **implementation and state**; Java allows each class at most one direct superclass.
- `implements` on one or more interfaces satisfies a contract; an interface can contain abstract/default/static/private methods according to Java rules, but does not provide instance fields like a class.
- An interface is usually a lighter-weight choice to express a **role or capability**.

### 1.2. Composition: The has-a / works-with Relationship

When writing:

```java
class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }
}
```

`Car` holds an `Engine` to collaborate; Car does not become a subtype of Engine.

Composition in the **design technique** sense usually means combining smaller objects into an object with larger behavior, delegating appropriate work. In the **UML strong composition** sense, this term also carries the meaning of **whole–part ownership and lifecycle**. The two meanings are **related but not identical**.

For example, `Car` receives an `Engine` created by the caller: that is definitely an **association**; whether Car exclusively owns the Engine depends on the ownership contract. In design patterns, we can still say Car is “composed of components” in the sense of object composition.

### 1.3. Delegation: Forwarding Behavior

```java
class ReportService {
    private final Formatter formatter;

    String render(String input) {
        return formatter.format(input);
    }
}
```

`render` **delegates** formatting to another object. A class can both have an association with Formatter and use delegation.

### 1.4. Dependency Injection Does Not Automatically Determine Ownership

```java
ReportService(Formatter formatter) {
    this.formatter = formatter;
}
```

This is **constructor injection**. It makes the dependency visible in the signature and replaceable when creating ReportService. However, constructor injection **does not require** ReportService to own Formatter's lifecycle. Formatter can be managed by a DI container or the caller.

## 2. The Most Important Question: Is It Truly is-a?

To evaluate inheritance, don't just ask “Does A have characteristics similar to B?”. Ask:

> If a function requires `B`, will passing an object `A` always preserve the meaning and contract that the function expects?

For example:

```java
void feed(Animal animal) {
    animal.eat();
}
```

If `Dog extends Animal` and every Dog satisfies Animal's `eat()` contract, the relationship makes sense.

However, “ReportService needs to write logs” does not mean ReportService **is a Logger**:

```java
// Questionable design:
// class ReportService extends Logger { ... }
```

If the service inherits from Logger just to call `log(...)`, any place expecting a Logger could receive a ReportService, even though ReportService **does not belong to the Logger semantic domain**. This exposes unnecessary inherited operations and makes changing the logger implementation difficult.

A more appropriate approach:

```java
class ReportService {
    private final Logger logger;

    ReportService(Logger logger) {
        this.logger = logger;
    }
}
```

A `ReportService` **has/uses** a Logger, rather than **being** a Logger.

## 3. Liskov Substitution Principle (LSP)

**LSP** is the behavioral test for subtypes. If `S` is used in place of `T` where a client expects a `T`, the client's valid assumptions and contracts must continue to be preserved.

At a practical level:

- A subclass should not arbitrarily **strengthen input requirements** compared to the superclass contract.
- A subclass should not **weaken output guarantees/postconditions**.
- A subclass needs to preserve the **invariants** promised by the abstraction.
- A subclass must not produce unexpected errors or behaviors that violate the contract the client relies on.
- Compatible signatures are **not enough**: behavior must also align.

### Counterexample: Bird – Penguin

An abstraction:

```java
class Bird {
    void fly() {
        System.out.println("Flying");
    }
}
```

If `Penguin extends Bird`, yet Penguin cannot fly and must override `fly` to throw an exception:

```java
class Penguin extends Bird {
    @Override
    void fly() {
        throw new UnsupportedOperationException();
    }
}
```

then a client calling `bird.fly()` under the assumption that every Bird can fly will encounter a surprise.

**The solution is not necessarily composition for everything.** The type hierarchy can be fixed:

```java
interface Bird {
    void eat();
}

interface Flyable {
    void fly();
}

final class Sparrow implements Bird, Flyable {
    @Override
    public void eat() { }

    @Override
    public void fly() { }
}

final class Penguin implements Bird {
    @Override
    public void eat() { }
}
```

`Sparrow` and `Penguin` are both Birds under the minimal contract; only Sparrow implements Flyable. **Interface segregation and role separation** help keep subtypes meaningful.

**Lesson:** inheritance should reflect a lasting contract, not merely group classes with similar names or attributes.

## 4. “Reusing Code” Is Not a Sufficient Reason for `extends`

Suppose two classes need a formatting function:

```java
class StringUtilities {
    String normalize(String value) {
        return value.trim();
    }
}
```

Design:

```java
// class CustomerService extends StringUtilities { ... }
```

using inheritance just to avoid writing `new StringUtilities()` is a sign of **implementation inheritance for convenience** without an is-a relationship.

Better options depending on the problem:

1. **Static utility** if the behavior is pure, stateless, and suitable as a utility function.
2. **Composition/delegation** if the component has state or needs configuration or swappable implementations.
3. **Interface** if the client needs an abstract contract.
4. **Superclass** if there is a genuine subtype relationship and a portion of shared implementation carries domain meaning.

Do not treat fewer lines in the initial version as the only metric. Inheritance creates coupling between the superclass and subclasses; modifying the superclass in the future can have very wide impact.

## 5. Selection Process in 7 Steps

A sufficiently practical sequence to apply to a new requirement:

1. **Write the requirement in terms of behavior**: what must the object do, and what are its inputs/outputs/invariants?
2. **Identify roles**: which abstraction is the object a kind of, or does it merely work with it?
3. **Check substitutability** using LSP: can a child object be used in place of the parent while the client remains correct?
4. **List axes of variation**: algorithms, data sources, delivery channels, access permissions, configuration, state.
5. **Evaluate runtime change needs** and the number of ways the axes combine.
6. **Examine ownership and lifecycle**: who creates, manages, closes, and shares the component?
7. **Evaluate the long-term API**: testability, coupling, backward compatibility, complexity, and real-world performance.

When the is-a relationship is weak, there are multiple independent axes of variation, or behavior needs to change at runtime, composition usually wins. When **a stable subtype contract and protected extension points** are needed, inheritance can win.

## 6. The Same Requirement: An Inheritance Design Easily Gets Messy

**Requirement:** sales needs to calculate different discounts for regular customers and member customers. Each invoice contains items, but discount rules can change depending on promotional campaigns.

A direct inheritance approach:

```java
class Checkout {
    int total(int subtotal) {
        return subtotal;
    }
}

class MemberCheckout extends Checkout {
    @Override
    int total(int subtotal) {
        return subtotal - 10;
    }
}

class HolidayCheckout extends Checkout {
    @Override
    int total(int subtotal) {
        return subtotal - 20;
    }
}
```

The approach can run, but try asking:

- Does a **Checkout** truly turn into a subtype when the **discount policy** changes?
- If a member customer also shops during the holidays, do we need `HolidayMemberCheckout`?
- If each checkout must support multiple discount campaigns depending on the invoice, do we have to create a new subclass object?
- If a service has already been created beforehand, how do we change the discount policy without changing the object type?

If discounting is an **independent strategy**, the Checkout subclass hierarchy couples the **“checkout type” axis** with the **“discount rule” axis**. This makes adding behavioral combinations difficult.

### Subclass Combination Risk

If there are 3 customer tiers × 4 campaigns × 2 rounding rules, designing subclasses for every combination can lead to **24 combinations** to consider, before even adding new requirements.

There may not always be all 24 concrete subclasses, yet the number of combinations is a sign that **the dimensions of change should be separated**.

## 7. Composition Design: Separating the Discount Policy

Define the contract:

```java
interface DiscountPolicy {
    int apply(int subtotal);
}
```

Checkout holds the policy:

```java
final class Checkout {
    private final DiscountPolicy policy;

    Checkout(DiscountPolicy policy) {
        this.policy = policy;
    }

    int total(int subtotal) {
        return policy.apply(subtotal);
    }
}
```

A `Checkout` **uses** a `DiscountPolicy`, rather than **being** a `DiscountPolicy`. This is the **Strategy pattern via composition**.

### Complete Java 17 Program

Save **`DiscountCompositionDemo.java`**:

```java
interface DiscountPolicy {
    int apply(int subtotal);
}

final class NoDiscount implements DiscountPolicy {
    @Override
    public int apply(int subtotal) {
        return subtotal;
    }
}

final class FixedDiscount implements DiscountPolicy {
    private final int amount;

    FixedDiscount(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("amount < 0");
        }
        this.amount = amount;
    }

    @Override
    public int apply(int subtotal) {
        return Math.max(0, subtotal - amount);
    }
}

final class PercentageDiscount implements DiscountPolicy {
    private final int percent;

    PercentageDiscount(int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("percent must be 0..100");
        }
        this.percent = percent;
    }

    @Override
    public int apply(int subtotal) {
        return subtotal - (subtotal * percent / 100);
    }
}

final class Checkout {
    private final DiscountPolicy policy;

    Checkout(DiscountPolicy policy) {
        this.policy = java.util.Objects.requireNonNull(policy);
    }

    int total(int subtotal) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal < 0");
        }
        return policy.apply(subtotal);
    }
}

public class DiscountCompositionDemo {
    public static void main(String[] args) {
        Checkout regular = new Checkout(new NoDiscount());
        Checkout member = new Checkout(new FixedDiscount(20));
        Checkout holiday = new Checkout(new PercentageDiscount(10));

        System.out.println("Regular: " + regular.total(200));
        System.out.println("Member: " + member.total(200));
        System.out.println("Holiday: " + holiday.total(200));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 DiscountCompositionDemo.java
java DiscountCompositionDemo
```

**Exact stdout:**

```text
Regular: 200
Member: 180
Holiday: 180
```

Benefits:
- `Checkout` is responsible for validating subtotal and coordinating.
- Each `DiscountPolicy` is responsible for one discount algorithm.
- Adding a new policy usually **does not require modifying `Checkout`**.
- Tests can provide a fake policy to verify that Checkout invokes it properly.
- The program can create different Checkout instances with different strategies right at runtime.

**Limitation to note:** the `subtotal * percent` calculation uses the int type and can overflow if subtotal is too large; the example illustrates a design contract, not production monetary logic. In a sales system, use appropriate monetary types (`long`/`BigDecimal`) along with well-defined rounding rules.

## 8. Composition Allows Swapping Strategies at Runtime

In the previous example, the `policy` field is `final`, so each Checkout keeps the same strategy reference. However, changing it can be allowed through a controlled operation:

```java
final class Checkout {
    private DiscountPolicy policy;

    Checkout(DiscountPolicy policy) {
        setPolicy(policy);
    }

    void setPolicy(DiscountPolicy policy) {
        this.policy = java.util.Objects.requireNonNull(policy);
    }

    int total(int subtotal) {
        return policy.apply(subtotal);
    }
}
```

If the business requirement is **“change the policy after the service is created”**, composition provides a direct way to express this. With inheritance, **the runtime class of an object cannot be turned into another subclass** simply via a setter.

However, mutating a dependency at runtime can introduce issues:
- Who has permission to change the policy?
- Are there calculations running concurrently?
- Is a policy snapshot needed for a transaction?
- Is auditing/logging of policy transitions required?

**Swappability** does not mean an object should be arbitrarily mutated in a multi-threaded system. If the requirement does not need changes partway through, **constructor injection + final field** is usually simpler and safer.

## 9. “Composition over inheritance” Does Not Mean Never Using Interfaces

A common misconception: choosing composition means not using `implements`.

In practice, designing with composition often **uses interfaces extensively**:

```java
interface Serializer {
    byte[] serialize(String value);
}

final class ExportService {
    private final Serializer serializer;

    ExportService(Serializer serializer) {
        this.serializer = serializer;
    }
}
```

Here:
- `JsonSerializer implements Serializer` is a **type abstraction** relationship.
- `ExportService` holding a `Serializer` is **composition/delegation** at the object design level.
- `ExportService` is not a subtype of Serializer.
- Another implementation of Serializer can be injected without changing ExportService.

The design rule is generally **program to an interface, prefer composition for reuse** — not “avoid all inheritance/interfaces”.

## 10. When Is Inheritance the Right Choice?

Class inheritance may be appropriate if:

- There is a **clear and stable base type contract**.
- Every valid subtype can substitute for the superclass under LSP.
- The superclass defines **shared state/behavior that truly belongs to every subtype**.
- There are **extension points** designed for subclasses to override.
- Subclasses need to share a standard workflow without bypassing invariant steps.
- The framework/domain deliberately publishes the superclass as an extension API.

For example: an **abstract job pipeline** has a method that runs the common workflow, while subclasses implement one specific step. This is an intentional **template method** scenario.

Conversely, if a subclass only wants to use a helper method from the superclass **without** having an is-a relationship, inheritance is unconvincing.

### “Is a” in Vietnamese Is Not Enough

A `Square` can be said to be a “rectangle”, but **a mutable Rectangle with independent `setWidth` and `setHeight` setters** can carry a contract incompatible with Square, which always maintains width=height. This is a classic example showing that is-a ontology **does not automatically guarantee LSP**.

Check the method-level contract rather than just domain naming.

## 11. A Sensible Inheritance Example: abstract Shape

An application needs to process all shapes under the `area()` contract. Each shape type provides its own area algorithm. Clients only need to view them through the abstraction.

Save **`ShapeInheritanceDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

abstract class Shape {
    abstract double area();

    final String describe() {
        return String.format(Locale.ROOT,
                "%s: %.2f",
                getClass().getSimpleName(), area());
    }
}

final class Rectangle extends Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("positive dimensions");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    double area() {
        return width * height;
    }
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        if (radius <= 0) {
            throw new IllegalArgumentException("positive radius");
        }
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}

public class ShapeInheritanceDemo {
    public static void main(String[] args) {
        List<Shape> shapes = List.of(
                new Rectangle(3, 4),
                new Circle(2));

        for (Shape shape : shapes) {
            System.out.println(shape.describe());
        }
    }
}
```

```bash
javac -encoding UTF-8 ShapeInheritanceDemo.java
java ShapeInheritanceDemo
```

**Stdout:**

```text
Rectangle: 12.00
Circle: 12.57
```

Why does inheritance make sense in this model?
1. Both `Rectangle` and `Circle` satisfy the same `area()` contract.
2. Clients can store a `List<Shape>` and call `describe()` without `instanceof` branching.
3. `describe()` is `final` to preserve a common format, while `area()` is an abstract extension point.
4. Each subclass controls the input values required for its own formula.
5. There is no requirement to turn a `Rectangle` into a `Circle` within the same object.

**Limitation:** the example shows reasonable inheritance with a stable abstraction. An `interface Shape` could also be suitable if the shared instance implementation of an abstract class is not needed. Choosing between an interface and an abstract class is a subsequent decision, not proof that every “Shape” must extend a superclass.

## 12. Abstract Class, Interface, or Composition?

| Requirement | Consideration |
| --- | --- |
| Multiple types of objects need to fulfill the same **capability** | Interface + implementations |
| Subtypes genuinely belong to the same **family and share state/algorithm** | Purposeful abstract class/superclass |
| A class needs to **use a capability** from outside | Interface-typed field/parameter, delegation |
| Behavior needs to change by configuration or at runtime | Strategy/DI via composition |
| Multiple behavioral axes need to be combined independently | Composition of multiple strategies/components |
| Only a helper feature is being reused | Utility/standalone component |
| Do not want to allow subclassing of the implementation | `final class` + interface/composition |
| Allow only a defined set of subtypes | `sealed class`/`sealed interface` in Java 17 |

**Do not use subclasses to model “configuration options”.** A choice such as CSV/JSON format or payment provider is usually a strategy/collaborator; not a different ontological version of the service.

## 13. Identifying Independent Axes of Variation

Suppose a notification system has two dimensions of change:

- **Channel:** email, SMS, push.
- **Content format:** short, detailed, HTML.

If subclasses are created for every combination:

```text
ShortEmailSender
DetailedEmailSender
HtmlEmailSender
ShortSmsSender
DetailedSmsSender
...
```

the number of subtypes risks growing as the product of the options in each dimension.

Composition separates them:

```java
interface Channel {
    void deliver(String message);
}

interface Template {
    String render(String name);
}

final class NotificationService {
    private final Channel channel;
    private final Template template;

    NotificationService(Channel channel, Template template) {
        this.channel = channel;
        this.template = template;
    }

    void notify(String name) {
        channel.deliver(template.render(name));
    }
}
```

Adding a new Channel does not require recreating every Template, and vice versa. This is the core benefit when a requirement has **multiple axes of variation**.

## 14. Java 17 Example: Two Independent Strategies

Save **`NotificationCompositionDemo.java`**:

```java
interface Channel {
    void deliver(String text);
}

interface Template {
    String render(String name);
}

final class ConsoleEmail implements Channel {
    @Override
    public void deliver(String text) {
        System.out.println("EMAIL: " + text);
    }
}

final class ConsoleSms implements Channel {
    @Override
    public void deliver(String text) {
        System.out.println("SMS: " + text);
    }
}

final class SimpleTemplate implements Template {
    @Override
    public String render(String name) {
        return "Hello " + name;
    }
}

final class FormalTemplate implements Template {
    @Override
    public String render(String name) {
        return "Dear " + name + ", welcome.";
    }
}

final class NotificationService {
    private final Channel channel;
    private final Template template;

    NotificationService(Channel channel, Template template) {
        this.channel = channel;
        this.template = template;
    }

    void notify(String name) {
        channel.deliver(template.render(name));
    }
}

public class NotificationCompositionDemo {
    public static void main(String[] args) {
        NotificationService email = new NotificationService(
                new ConsoleEmail(), new FormalTemplate());

        NotificationService sms = new NotificationService(
                new ConsoleSms(), new SimpleTemplate());

        email.notify("An");
        sms.notify("Bình");
    }
}
```

```bash
javac -encoding UTF-8 NotificationCompositionDemo.java
java NotificationCompositionDemo
```

**Stdout:**

```text
EMAIL: Dear An, welcome.
SMS: Hello Bình
```

Here, NotificationService **is not subclassed** into `EmailFormalNotificationService`. Instead, it **coordinates** two objects that satisfy two independent interfaces.

This is why composition is often suitable when behaviors are **composable capabilities**, rather than fixed “species” of objects.

## 15. Inheritance Creates Coupling to the Superclass Implementation

Subclasses are often bound by:

- The signatures of the superclass's constructors;
- Protected members/virtual methods exposed to subclasses;
- The order in which the superclass calls hooks;
- The rule that the superclass initializes before the subclass;
- Changes to the superclass's state/invariants;
- Superclass methods that can be overridden;
- Interactions among overridden methods.

For example, a subclass overrides `add` to count elements, while the superclass's `addAll` calls `add` for each element. If the subclass also increments the counter in `addAll`, it can accidentally **double-count**. This is a form of the issue known as **fragile base class**, when a subclass depends on the superclass's internal call details.

This does not mean inheritance is always wrong; it means **a superclass intended to support subclassing must design and document its extension contract**.

### Composition Narrows the Boundary

A wrapper holding a `Collection` interface or a service delegate usually depends only on the collaborator's **public contract**, without needing to know how internal methods call one another. Updating the delegate's implementation can have less impact on the wrapper.

However, the wrapper must also define which operations are allowed and ensure it does not omit new interface methods when the contract requires them.

## 16. Real-World Counterexample: Subclassing `HashSet` to Count Additions

If the goal is to count the number of new elements added to a `Set`, subclassing `HashSet` and overriding `add`/`addAll` very easily causes coupling to how `HashSet`/`AbstractCollection` implements those operations.

A problematic illustrative snippet:

```java
class CountingSet<E> extends java.util.HashSet<E> {
    private int additions;

    @Override
    public boolean add(E item) {
        additions++;
        return super.add(item);
    }

    @Override
    public boolean addAll(
            java.util.Collection<? extends E> items) {
        additions += items.size();
        return super.addAll(items);
    }
}
```

There are at least two semantic discrepancies:
- `add(item)` increments the counter even when the item already exists and the `Set` adds nothing.
- `addAll(items)` adds `items.size()` before calling the superclass logic, and then the superclass may call `add` along an implementation path, leading to double-counting or implementation dependence.

**Do not build a correctness proof on “the current superclass calls the hook the way you guess”.**

A composition design can manage the count of successful modifications more clearly.

## 17. Runnable Program: A Set Wrapper via Composition

Save **`CountingSetCompositionDemo.java`**:

```java
import java.util.Collection;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class CountingSet<E> {
    private final Set<E> elements = new HashSet<>();
    private int successfulAdds;

    boolean add(E value) {
        boolean changed = elements.add(value);
        if (changed) {
            successfulAdds++;
        }
        return changed;
    }

    int addAll(Collection<? extends E> values) {
        Objects.requireNonNull(values);

        int added = 0;
        for (E value : values) {
            if (add(value)) {
                added++;
            }
        }
        return added;
    }

    int size() {
        return elements.size();
    }

    int successfulAdds() {
        return successfulAdds;
    }
}

public class CountingSetCompositionDemo {
    public static void main(String[] args) {
        CountingSet<String> set = new CountingSet<>();

        System.out.println(set.add("A"));
        System.out.println(set.add("A"));
        System.out.println(set.addAll(
                java.util.List.of("A", "B", "C", "C")));
        System.out.println("size = " + set.size());
        System.out.println("adds = " + set.successfulAdds());
    }
}
```

```bash
javac -encoding UTF-8 CountingSetCompositionDemo.java
java CountingSetCompositionDemo
```

**Stdout:**

```text
true
false
2
size = 3
adds = 3
```

`CountingSet` uses `HashSet` as **a separate component** and defines the contract “successfulAdds is the number of new elements actually added through this API”.

**Limitation:** the demo wrapper **does not implement `Set<E>` yet**; it intentionally provides only the operations needed for the use case. If a drop-in `Set` is needed, a full forwarding/decorator implementation can be written, but it must properly cover the `Set` contract (iterator.remove, clear, removeAll, etc.) and precisely define the metric to count.

Do not call this wrapper a complete replacement for every `Set`, because it does not implement `Set`.

## 18. Using Delegation Instead of an Exposed Inheritance API

A subclass can **inherit too many methods** unrelated to the business domain.

For example, `class UserRepository extends ArrayList<User>`:

- The repository will gain `get(index)`, `subList`, `sort`, `removeIf`, and other mutators under the List contract.
- Callers can bypass the repository's validation/invariants.
- “Repository is-a List” is a relationship very hard to defend if the domain does not genuinely commit to List semantics.

A better structure:

```java
final class UserRepository {
    private final List<User> users = new ArrayList<>();

    void save(User user) {
        // Appropriate validation/uniqueness.
        users.add(user);
    }

    List<User> findAll() {
        return List.copyOf(users);
    }
}
```

This illustrative snippet assumes `User` is already declared and `List`/`ArrayList` are imported. The repository **has an internal list**, rather than declaring that it **is a List**.

**Benefit:** the API can expose only the necessary behaviors, avoiding being constrained by the entire inherited API from a concrete collection.

## 19. Composition and Information Hiding

Object composition is effective when **hiding implementation details**:

```java
final class Cart {
    private final List<String> skus = new ArrayList<>();

    void add(String sku) {
        skus.add(sku);
    }

    int size() {
        return skus.size();
    }
}
```

If tomorrow `ArrayList` needs to be replaced with `LinkedHashSet` or a database-backed repository, a Cart API that exposes only `add`/`size` can change its internal representation more easily than `class Cart extends ArrayList`, which exposes the entire API and semantics of ArrayList.

**However,** having a private field does not automatically mean immutability:
- A `final List` field does not prevent mutating the list.
- A getter returning the backing list directly can allow callers to break invariants.
- A caller holding a mutable input alias can modify state outside the owner.

You need to control **encapsulation and ownership**, not merely choose the keyword “composition”.

## 20. Constructor Injection and Testability

Composition often makes unit testing easier because a dependency is replaced with a **test double** implementing the same interface.

Suppose `Checkout` depends on `DiscountPolicy`. Tests do not need to inherit from `Checkout` to intercept the algorithm; instead, they supply a fake policy with predictable results.

Save **`CompositionTestDemo.java`**:

```java
interface TaxPolicy {
    int addTax(int subtotal);
}

final class Checkout {
    private final TaxPolicy policy;

    Checkout(TaxPolicy policy) {
        this.policy = policy;
    }

    int total(int subtotal) {
        return policy.addTax(subtotal);
    }
}

final class FixedTestTax implements TaxPolicy {
    private int calls;

    @Override
    public int addTax(int subtotal) {
        calls++;
        return subtotal + 7;
    }

    int calls() {
        return calls;
    }
}

public class CompositionTestDemo {
    public static void main(String[] args) {
        FixedTestTax fake = new FixedTestTax();
        Checkout checkout = new Checkout(fake);

        System.out.println(checkout.total(10));
        System.out.println("calls = " + fake.calls());
    }
}
```

```bash
javac -encoding UTF-8 CompositionTestDemo.java
java CompositionTestDemo
```

**Stdout:**

```text
17
calls = 1
```

The test double `FixedTestTax` records how many times it was called. Because `Checkout` does not create a concrete tax calculator itself, the test can check the **interaction** clearly.

However, **DI does not automatically make every test better**. If a class has no varying dependency, using an interface solely for testing can create unnecessary abstraction. Evaluate the actual need.

## 21. Inheritance Can Appropriately Use Template Method

There are requirements that need **a mandatory pipeline** followed by every subtype, while only one step is customized. This is a case where inheritance can work well.

Save **`TemplateMethodChoiceDemo.java`**:

```java
import java.util.Locale;

abstract class ImportJob {
    public final String run(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("raw required");
        }

        String normalized = raw.trim();
        return transform(normalized);
    }

    protected abstract String transform(String normalized);
}

final class UppercaseJob extends ImportJob {
    @Override
    protected String transform(String normalized) {
        return normalized.toUpperCase(Locale.ROOT);
    }
}

final class DashJob extends ImportJob {
    @Override
    protected String transform(String normalized) {
        return normalized.replace(" ", "-");
    }
}

public class TemplateMethodChoiceDemo {
    public static void main(String[] args) {
        ImportJob first = new UppercaseJob();
        ImportJob second = new DashJob();

        System.out.println(first.run("  hello java  "));
        System.out.println(second.run("  hello java  "));
    }
}
```

```bash
javac -encoding UTF-8 TemplateMethodChoiceDemo.java
java TemplateMethodChoiceDemo
```

**Stdout:**

```text
HELLO JAVA
hello-java
```

In this design:

- `ImportJob` is a **genuine base contract** for import jobs.
- `run` is `final` so subclasses cannot override it and bypass the normalize/null check by replacing the entire pipeline.
- `transform` is a clear extension point with a stable signature.
- Concrete jobs are subtypes implementing a single step.
- A subclass does **not** have the authority to rewrite the overall lifecycle.

**Warning:** the `transform` method can still throw exceptions or cause side effects. A final template method does not automatically protect all program invariants if the hook contract is too broad.

## 22. That Same Template Method Can Be Written Using Composition

If the `transform` variant needs to be supplied at runtime instead of creating an `ImportJob` subclass, we can write:

```java
interface Transformer {
    String transform(String input);
}

final class ImportService {
    private final Transformer transformer;

    ImportService(Transformer transformer) {
        this.transformer = transformer;
    }

    String run(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("raw required");
        }
        return transformer.transform(raw.trim());
    }
}
```

Two different approaches:

| Aspect | Inheritance template | Composition transformer |
| --- | --- | --- |
| Point of variation | Subclass overrides hook | Collaborator object implements interface |
| Behavior selection | Usually when selecting/instantiating subtype | When supplying the dependency |
| Replacing implementation on the same service object | Does not change runtime class | Can be designed to swap component if needed |
| Coupling | Subclass ↔ superclass hooks/state | Service ↔ interface contract |
| Scaling across multiple axes | Harder if combined in a single hierarchy | Convenient when separated into multiple interfaces |
| Well suited for | Frameworks intentionally defining a subtype family | Strategy/configuration/provider |

**There is no absolute answer.** If the project has a documented framework base class and the subtypes genuinely belong to the ImportJob family, inheritance is a reasonable choice. If the transformer is independent, shared across multiple services, and changes frequently, composition is usually more sensible.

## 23. Decorator: Extending Behavior via Wrapping Instead of Subclass Explosion

A common requirement:

> There is a `Sender` that sends notifications. We need to add logging, a prefix, and checks without modifying the concrete sender. These behaviors can be toggled on or off by configuration.

Creating `LoggedEmailSender`, `PrefixedEmailSender`, `LoggedPrefixedEmailSender` ... easily leads to subclass explosion.

**Decorator** uses a shared interface, and each wrapper holds a delegate:

```java
interface Sender {
    void send(String text);
}

final class PrefixSender implements Sender {
    private final Sender delegate;

    PrefixSender(Sender delegate) {
        this.delegate = delegate;
    }

    @Override
    public void send(String text) {
        delegate.send("[INFO] " + text);
    }
}
```

A `PrefixSender` **implements Sender** (fulfilling the contract) and **has a Sender delegate** (composition). This is a concrete example showing that polymorphism and composition are not mutually exclusive.

### Runnable Decorator Program

Save **`DecoratorChoiceDemo.java`**:

```java
interface Sender {
    void send(String text);
}

final class ConsoleSender implements Sender {
    @Override
    public void send(String text) {
        System.out.println("SEND " + text);
    }
}

final class PrefixSender implements Sender {
    private final Sender delegate;

    PrefixSender(Sender delegate) {
        this.delegate = delegate;
    }

    @Override
    public void send(String text) {
        delegate.send("[INFO] " + text);
    }
}

final class AuditSender implements Sender {
    private final Sender delegate;

    AuditSender(Sender delegate) {
        this.delegate = delegate;
    }

    @Override
    public void send(String text) {
        System.out.println("AUDIT " + text);
        delegate.send(text);
    }
}

public class DecoratorChoiceDemo {
    public static void main(String[] args) {
        Sender base = new ConsoleSender();
        Sender prefix = new PrefixSender(base);
        Sender audited = new AuditSender(prefix);

        audited.send("hello");
        base.send("plain");
    }
}
```

```bash
javac -encoding UTF-8 DecoratorChoiceDemo.java
java DecoratorChoiceDemo
```

**Stdout:**

```text
AUDIT hello
SEND [INFO] hello
SEND plain
```

Each wrapper has the `Sender` contract, while behavior is built through **object composition**. You can change the order of wrappers or omit wrappers as needed without creating a new subclass for each combination.

**Note:** the order of decorators can change the order of side effects. This is part of the system contract and must be tested; do not assume every permutation is equivalent.

## 24. Adapter: Composition When Two APIs Have No is-a Relationship

**Requirement:** the application uses the `PaymentPort` interface, while the legacy library only has an API differing in names and parameter format.

Do not write:

```java
// class PaymentService extends LegacyGateway { ... }
```

just to inherit `chargeCents`. A service is not a gateway.

An adapter takes the gateway and forwards the call:

```java
interface PaymentPort {
    String pay(int cents);
}

class LegacyGateway {
    String chargeCents(int cents) {
        return "OK:" + cents;
    }
}

final class LegacyPaymentAdapter implements PaymentPort {
    private final LegacyGateway gateway;

    LegacyPaymentAdapter(LegacyGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public String pay(int cents) {
        return gateway.chargeCents(cents);
    }
}
```

The adapter **implements** an application interface and **has-a** legacy object. This generally has less coupling than making a domain service extend an external library class.

### Complete Java 17 Example

Save **`AdapterChoiceDemo.java`**:

```java
interface PaymentPort {
    String pay(int cents);
}

final class LegacyGateway {
    String chargeCents(int cents) {
        return "OK:" + cents;
    }
}

final class LegacyPaymentAdapter implements PaymentPort {
    private final LegacyGateway gateway;

    LegacyPaymentAdapter(LegacyGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    @Override
    public String pay(int cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative cents");
        }
        return gateway.chargeCents(cents);
    }
}

final class BillingService {
    private final PaymentPort payments;

    BillingService(PaymentPort payments) {
        this.payments = payments;
    }

    String charge(int cents) {
        return payments.pay(cents);
    }
}

public class AdapterChoiceDemo {
    public static void main(String[] args) {
        PaymentPort adapter =
                new LegacyPaymentAdapter(new LegacyGateway());

        BillingService billing = new BillingService(adapter);

        System.out.println(billing.charge(1500));
    }
}
```

```bash
javac -encoding UTF-8 AdapterChoiceDemo.java
java AdapterChoiceDemo
```

**Stdout:**

```text
OK:1500
```

An adapter helps isolate the external API at the boundary. If `LegacyGateway` is replaced tomorrow, the `BillingService` domain still depends on `PaymentPort`. Production code needs to add transaction IDs, retries, idempotency, currency, and error handling; the example here only illustrates choosing the relationship.

## 25. A Class Cannot Inherit from Multiple Classes in Java

Java does not allow:

```java
// class FlyingCar extends Car, Airplane { }
// WRONG: Java does not support extending two classes.
```

However, Java allows a class to **implement multiple interfaces**:

```java
interface Flyable {
    void fly();
}

interface Drivable {
    void drive();
}

final class FlyingCar implements Flyable, Drivable {
    @Override
    public void fly() { }

    @Override
    public void drive() { }
}
```

If flying and driving behaviors are **separate, replaceable components**, composition is even more appropriate:

```java
class Vehicle {
    private final FlightSystem flightSystem;
    private final DriveSystem driveSystem;
}
```

In the last example, the types `FlightSystem`/`DriveSystem` are illustrative placeholders; they must be declared if you want to compile the snippet standalone.

**Choose according to the requirement:** if `FlyingCar` implements both contracts itself and does not need to swap implementations, multiple interfaces may suffice. If each capability is handled by a subsystem with its own configuration and lifecycle, use composition.

## 26. Java 17 Sealed Types: When the Subtype Set Is Finite and Intentional

Java 17 supports **sealed classes/interfaces**, allowing control over **direct permitted subclasses/implementations**.

For example:

```java
sealed interface Result permits Success, Failure {
}

record Success(String value) implements Result {
}

record Failure(String message) implements Result {
}
```

Both records are final types, satisfying the branching requirement of the sealed interface.

**When is a sealed hierarchy appropriate?**
- The domain has a **known and bounded set of variants**.
- Every variant is genuinely a subtype of a contract.
- You want the compiler to help restrict valid implementations.
- The API does not intend for external plugins to arbitrarily create new subtypes.

**When does composition make more sense?**
- Components/strategies are continually added by third parties.
- Multiple behavioral axes need to be combined.
- Behavior needs to be swapped at runtime.
- An object has multiple collaborating “roles” rather than being a closed variant of an abstract type.

Do not choose sealed just because it is new. A regular interface and composition can be simpler for open extensibility.

### Runnable Sealed Program

Save **`SealedChoiceDemo.java`**:

```java
sealed interface Outcome permits Success, Failure {
    String describe();
}

record Success(String value) implements Outcome {
    @Override
    public String describe() {
        return "OK: " + value;
    }
}

record Failure(String reason) implements Outcome {
    @Override
    public String describe() {
        return "ERROR: " + reason;
    }
}

public class SealedChoiceDemo {
    public static void main(String[] args) {
        Outcome first = new Success("saved");
        Outcome second = new Failure("invalid");

        System.out.println(first.describe());
        System.out.println(second.describe());
    }
}
```

```bash
javac -encoding UTF-8 SealedChoiceDemo.java
java SealedChoiceDemo
```

**Stdout:**

```text
OK: saved
ERROR: invalid
```

## 27. Final Classes and Records Suggest Composition

A `final class` cannot have subclasses. A Java record is also **implicitly final**.

```java
final class CustomerId {
    private final String value;

    CustomerId(String value) {
        this.value = value;
    }
}

record Money(long cents) {
}
```

If the requirement is to extend the behavior of a service that uses `Money` or `CustomerId`, attempting `extends Money` will fail. Instead, you typically:

- Create a service/helper that accepts the value object.
- Use an interface abstraction if there are multiple genuine implementations.
- Combine immutable values into aggregates.
- Decorate the service's behavior through collaborators.

**However,** final/record does not automatically guarantee deep immutability when a field/component is a mutable object; aliasing protection is still needed in the ownership model.

Do not remove `final` from a value object just to use inheritance as a way of reusing utilities.

## 28. Cases Where Behavior Is Replaced by User/Tenant/Runtime

If a method needs to select a strategy based on user/tenant configuration:

```java
DiscountPolicy policy = policies.forCustomer(customer);
Checkout checkout = new Checkout(policy);
```

is a good expression: the `Checkout` object is assembled with the appropriate policy for that request.

If you create a Checkout subclass for each tenant:

```text
TenantACheckout
TenantBCheckout
TenantCCheckout
...
```

then the domain/service code becomes coupled to the tenant, making it hard to extend when configurations change.

Still, it must be made clear **where the strategy is chosen**:
- In controller/service orchestration?
- In a factory?
- In a DI container scope?
- Per request or singleton?

Composition only helps separate responsibilities; the system still needs a **composition root** or factory responsible for wiring dependencies.

## 29. Composition Root: Where the Object Graph Is Assembled

One anti-pattern is when a service creates its own dependency:

```java
class Checkout {
    private final DiscountPolicy policy =
            new FixedDiscount(10);
}
```

When a requirement changes the policy, you have to edit Checkout or add conditional logic inside it.

Implementation selection can be moved out to the **composition root**:

```java
DiscountPolicy policy = new FixedDiscount(10);
Checkout checkout = new Checkout(policy);
```

This is usually code at the application startup layer, controller factory, or DI configuration.

**Points to distinguish:**
- **Composition**: Checkout collaborates with Policy.
- **Dependency injection**: Policy is supplied into Checkout.
- **Composition root**: where Policy and Checkout are chosen, created, and wired together.

A small application can wire objects manually with `new` without needing a DI framework.

## 30. Ownership and Lifecycle: Receiving a Component Does Not Mean Owning It

```java
class ReportService {
    private final OutputStream output;

    ReportService(OutputStream output) {
        this.output = output;
    }
}
```

The `output` field can represent a long-lived association/dependency. However, responsibility for `close()` **cannot be inferred automatically**:
- If `ReportService` **borrows** the output stream, the caller must close it.
- If the constructor **accepts ownership transfer**, the service may be responsible for closing it.
- If the stream is shared across multiple services, one service closing it on its own can break the others.

A good ownership contract must clearly state:
- Who creates it?
- Who may use it?
- Who may modify it?
- Who must close it?
- When does closing happen?
- Can other references still be used?

In UML, **strong composition** is tied to the whole–part lifecycle; in Java, a `final` field or a constructor parameter **does not automatically enforce exclusive ownership**.

## 31. Example of Resource-Owning Composition

Save **`OwnedResourceDemo.java`**:

```java
final class Connection implements AutoCloseable {
    private boolean closed;

    void query() {
        if (closed) {
            throw new IllegalStateException("closed");
        }
        System.out.println("query");
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("connection closed");
        }
    }
}

final class Session implements AutoCloseable {
    private final Connection connection = new Connection();

    void execute() {
        connection.query();
    }

    @Override
    public void close() {
        connection.close();
    }
}

public class OwnedResourceDemo {
    public static void main(String[] args) {
        try (Session session = new Session()) {
            session.execute();
        }
        System.out.println("done");
    }
}
```

```bash
javac -encoding UTF-8 OwnedResourceDemo.java
java OwnedResourceDemo
```

**Stdout:**

```text
query
connection closed
done
```

`Session` **creates Connection itself and is responsible for closing it**: this is strong ownership over a resource.

Conversely, if Session merely receives a shared Connection from the caller/DI container, the API must clearly define whether Session is allowed to close the shared connection. This cannot be concluded from the syntax `private final Connection connection`.

**GC does not replace `close()`.** Java does not guarantee that an object's memory is reclaimed immediately after a local variable loses its reference. For real files/sockets/connections, use `AutoCloseable` and try-with-resources or explicit lifecycle management.

## 32. Counterexample to “Every has-a Is UML Composition”

```java
final class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }
}
```

If `Engine` is created by the caller, can be shared with another object, or can have its owner transferred, the code relationship is association; **strong UML composition cannot yet be concluded**.

If `Car` creates Engine internally, controls updates, and is responsible for ending Engine's lifecycle under the contract, strong composition may fit.

**Points to distinguish:**
- In **design-pattern vocabulary**, “composition over inheritance” usually refers to **passing another object in to delegate to**, including DI/shared dependencies.
- In **UML**, a filled-diamond **composition** means specific whole–part ownership.
- A design can be good with **association + delegation** without needing to be called UML composition.

## 33. Encapsulation Boundaries and Defensive Copies

Composition can be broken if the object is modified directly from outside:

```java
class Order {
    private final List<String> items = new ArrayList<>();

    List<String> items() {
        return items; // Exposes the mutable backing list.
    }
}
```

A caller can invoke `order.items().clear()`, bypassing the `removeItem` business API.

A safer approach when elements are immutable:

```java
List<String> items() {
    return List.copyOf(items);
}
```

`List.copyOf` returns an unmodifiable snapshot of the list structure from a typical mutable source; with **mutable elements**, the copy is still shallow and can share element state. If holding mutable input from the caller, the constructor also needs a defensive copy on **input**.

**Do not confuse:** `Collections.unmodifiableList(backing)` returns an unmodifiable **view** that can reflect updates to the backing list; it does not automatically become a snapshot.

Choosing composition goes hand in hand with designing an **ownership/mutability contract**, not just tucking an object into a private field.

## 34. Inheritance and Object Initialization: The Superclass Constructor Runs First

In Java, when creating a subclass instance, the constructor passes through the superclass before the subclass finishes initializing its own fields/constructor body.

If a superclass constructor calls an overridable method, dynamic dispatch can run the subclass implementation **before the subclass's fields are explicitly initialized**.

For example:

```java
class Parent {
    Parent() {
        show();
    }

    void show() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private String state = "READY";

    @Override
    void show() {
        System.out.println(state);
    }
}
```

`new Child()` can print `null` when the `Parent` constructor calls `show()` before Child's field initializer `state = "READY"` runs.

This is a risk **specific to inheritance/lifecycle**. With composition, a constructor can usually receive an already fully initialized component; however, you must also avoid passing `this` out prematurely or invoking callbacks before the object is complete.

### Verification Program

Save **`ConstructorOverrideRiskDemo.java`**:

```java
class Parent {
    Parent() {
        show();
    }

    void show() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private String state = "READY";

    @Override
    void show() {
        System.out.println("Child state: " + state);
    }
}

public class ConstructorOverrideRiskDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac -encoding UTF-8 ConstructorOverrideRiskDemo.java
java ConstructorOverrideRiskDemo
```

**Stdout:**

```text
Child state: null
```

Do not treat this as a recommended design approach. It illustrates why subclass coupling and overridable constructor calls carry risk. A base class intentionally designed for subclassing should avoid calling overridable methods from constructors.

## 35. When Does Inheritance Beat Composition for Simplicity?

A small system with a stable **closed hierarchy**—for example, `Success` and `Failure` as two genuinely distinct result states—can be represented using a sealed interface + records.

If you try to use composition for everything:

```java
class Outcome {
    private final StatusKind kind;
    private final Object payload;
}
```

and then constantly check `kind` and cast `payload`, the design can have weaker type safety than a clear hierarchy.

When each type **is a valid variant** of an abstraction and the set of variants is managed, a polymorphic subtype model is the natural approach.

### Cases Where Inheritance Fits Well

- The entity has a genuine subtype, and all clients using the base contract remain valid.
- The domain has a closed data family needing variant modeling (sealed interface/record).
- A framework declares an abstract base class and a clear override contract.
- A base class contains stable code/hooks where subclasses are truly kinds of the base.
- A polymorphic API is needed for the same behavior where implementations genuinely belong to one role.

**Key point:** good design sometimes uses **inheritance for roles/interfaces** and **composition for behavior/dependencies** in the same solution.

## 36. When Does Composition Clearly Beat Inheritance?

Strong signals:

- The real relationship is **uses-a/has-a**, not is-a.
- You want to swap algorithms or implementations by configuration/runtime.
- Multiple variants can be combined independently.
- The new class only wants to reuse part of another class's helper functionality.
- The superclass exposes too much inappropriate public/protected API.
- Component lifecycle/ownership needs to be managed separately from the service.
- You need to test using fake/mock collaborators without altering internal superclass state.
- You want to avoid depending on how the superclass calls internal methods.
- You want adapter/decorator/strategy instead of increasing the number of subclasses.
- A third-party library class has an API/constructor/invariants prone to change.

Composition has its own costs: extra interfaces, forwarding boilerplate, object wiring, null/lifecycle handling, and potential over-abstraction if overused. Therefore, “composition always wins” is also wrong.

## 37. Quick Decision Table by Specific Requirement

| Requirement | Usually Suitable Approach | Reason |
| --- | --- | --- |
| A `Dog` needs to be used as an `Animal` under a valid contract | Inheritance or interface | Is-a/substitutability |
| `OrderService` needs to send email | Composition with `MessageSender` | Uses-a; delivery channel is swappable |
| Application has CSV/JSON/XML formats | Composition Strategy | Format algorithm is an axis of variation |
| Need to validate then run a customizable step of the same Jobs family | Abstract base + final template | Pipeline invariant |
| Object has multiple features that can be toggled on/off | Composition/decorators | Avoid subclass combinations |
| One type of object has multiple roles (Comparable, Closeable...) | Implement appropriate interfaces | Capability contract, no superclass implementation needed |
| A hierarchy has a bounded set of Success/Failure results | Sealed interface + records | Closed sum-like variants |
| Repository wants to use ArrayList for storage | Composition | Repository is not a List |
| Need to adapt a legacy payment gateway | Adapter + composition | Separate external implementation |
| An `Order` owns OrderLines in the domain | Strong composition/aggregate | Part lifecycle and invariants |
| Multiple services share a connection pool | Association/DI; separate pool owner | Shared dependency, not exclusively owned |
| Framework only allows extending `AbstractController` | Inheritance when the contract is guaranteed | Follow framework extension points |
| Want code similar to a superclass, but LSP fails | Composition/re-split contract | Avoid false subtypes |
| Need to change discount policy per request | Composition/factory | Strategy selected at runtime |
| Only need a `Math.max` function | Static utility | No object relation needed |
| Need to add audit/logging without modifying sender | Decorator | Wrapping behavior |

These are suggestions, not automatic conclusions. A large requirement may need **both** at different boundaries.

## 38. Step-by-Step “Requirement → Relationship → Code” Method

Given a requirement:

> A report export system. A report has a title and data; users can choose PDF or CSV; every report must have access permissions checked before exporting; the storage provider can switch from local to cloud.

Analysis:

**Step 1 — Responsibilities:**
- `Report`: the report's data and invariants.
- `ReportExporter`: how to create a file from Report.
- `Storage`: how to save bytes/files.
- `ExportService`: checks permissions, then coordinates exporting and saving.

**Step 2 — Variations:**
- Export format: PDF/CSV.
- Storage: local/cloud.
- Authorization: can vary by policy.

**Step 3 — Relationships:**
- `Report` **is not** an Exporter or Storage.
- `ExportService` **uses** Exporter, Storage, and Authorizer.
- `PdfExporter` and `CsvExporter` both **implement `ReportExporter`**.
- `LocalStorage` and `CloudStorage` both **implement `Storage`**.

**Step 4 — Choices:**
- Use composition to coordinate the three dependencies.
- Use interfaces to make implementations polymorphic.
- Use one entry point with permission checking; avoid letting subclasses override and skip the check.
- Use DI/a factory at the composition root to select components by config.
- If resources exist, define the owner/`close()` separately.

You should not create a hierarchy:

```text
PdfLocalAuthorizedExportService
PdfCloudAuthorizedExportService
CsvLocalAuthorizedExportService
CsvCloudAuthorizedExportService
...
```

because that combines multiple independent axes of variation.

## 39. Java 17 Program for the Report Problem

Below is a minimal version for **export format + storage**, with a permission check step. It does not perform real PDF generation; the text `PDF:` is just a marker to focus on relationship design.

Save **`ReportDesignDemo.java`**:

```java
import java.util.Objects;

record Report(String title, String body) {
    Report {
        Objects.requireNonNull(title);
        Objects.requireNonNull(body);
    }
}

interface ReportExporter {
    String export(Report report);
}

final class CsvExporter implements ReportExporter {
    @Override
    public String export(Report report) {
        return "CSV:" + report.title() + "|" + report.body();
    }
}

final class PdfMarkerExporter implements ReportExporter {
    @Override
    public String export(Report report) {
        return "PDF:" + report.title() + "|" + report.body();
    }
}

interface Storage {
    void save(String content);
}

final class ConsoleStorage implements Storage {
    @Override
    public void save(String content) {
        System.out.println("SAVED " + content);
    }
}

interface Authorizer {
    boolean canExport(String user);
}

final class NamedUserAuthorizer implements Authorizer {
    @Override
    public boolean canExport(String user) {
        return "admin".equals(user);
    }
}

final class ExportService {
    private final ReportExporter exporter;
    private final Storage storage;
    private final Authorizer authorizer;

    ExportService(
            ReportExporter exporter,
            Storage storage,
            Authorizer authorizer) {
        this.exporter = Objects.requireNonNull(exporter);
        this.storage = Objects.requireNonNull(storage);
        this.authorizer = Objects.requireNonNull(authorizer);
    }

    void exportFor(String user, Report report) {
        if (!authorizer.canExport(user)) {
            System.out.println("DENIED " + user);
            return;
        }
        storage.save(exporter.export(report));
    }
}

public class ReportDesignDemo {
    public static void main(String[] args) {
        Report report = new Report("Sales", "Q1");

        Authorizer auth = new NamedUserAuthorizer();
        Storage storage = new ConsoleStorage();

        ExportService csv = new ExportService(
                new CsvExporter(), storage, auth);
        ExportService pdf = new ExportService(
                new PdfMarkerExporter(), storage, auth);

        csv.exportFor("admin", report);
        pdf.exportFor("guest", report);
        pdf.exportFor("admin", report);
    }
}
```

Run:

```bash
javac -encoding UTF-8 ReportDesignDemo.java
java ReportDesignDemo
```

**Stdout:**

```text
SAVED CSV:Sales|Q1
DENIED guest
SAVED PDF:Sales|Q1
```

**Understanding the relationships:**

- `Report` is data, not `extends ReportExporter` or `Storage`.
- `CsvExporter`/`PdfMarkerExporter` satisfy **is-a ReportExporter** under the interface contract.
- `ConsoleStorage` satisfies **is-a Storage**.
- `ExportService` **has/uses** three collaborators and **delegates** tasks to them.
- `ExportService.exportFor` checks permissions **before** calling exporter/storage.
- Combining CSV/PDF with Storage/Auth is independent; no need to subclass ExportService for every combination.

**Practical limitations:** a real CSV exporter must escape delimiters/quotes, PDF requires a library and specification, authorization needs identity/policy control, and Storage needs error/transaction handling. The example uses marker strings and stable output solely to illustrate **architectural decisions**.

## 40. Avoiding Too Many Interfaces That Add No Value

Composition can cause **overengineering** if, for a simple object with no variations and no need for a test double, the author creates:

```text
INameReader
NameReaderImpl
NameReaderFactory
NameReaderManager
NameReaderManagerAdapter
...
```

without a clear reason to swap implementations.

Some situations where you should **not rush to abstract**:
- Small value objects using `record`.
- Simple stateless helper functions.
- A stable service with no collaborators that need replacing.
- Abstractions created merely because “every class must have an interface” even though clients do not need one.

Principle: **place abstractions where there is variation or a responsibility boundary**, not to inflate the number of types to make a diagram look pretty.

**A concrete collaborator private field is still composition.** An interface adds value when you truly need to separate the contract from the implementation.

## 41. Comparing Coupling and Changeability

| Criterion | Class inheritance | Composition via interface |
| --- | --- | --- |
| Relationship | Is-a/subtype + implementation sharing | Has-a/uses-a + delegation |
| Superclass state sharing | Possible | Not automatic; collaborator holds its own state |
| Coupling to superclass internals | Can be strong, especially with protected hooks | Primarily through the interface contract if hidden properly |
| Swapping collaborator implementation | Cannot change the current runtime class | Can be changed via injection/new instance/config |
| Multiple behavioral axes | Easily leads to many subclasses | Combine independent components |
| Process protection | Final template method | Service controls flow and delegates steps |
| Test isolation | May require subclasses/test hooks | Convenient interface fake/mock |
| Exposed API | Subclass inherits applicable members | Wrapper exposes only the desired API |
| Lifecycle | Parent–child constructor chain is tightly coupled | Component has its own ownership/lifecycle |
| Code overhead | May have less initial wiring | May require more interfaces/delegation |
| Risks | LSP, fragile base class, overriding lifecycle | Over-abstraction, wiring, alias/ownership |
| Best used when | Stable subtype relationship | Collaboration, strategies, runtime variation |

**Do not treat the table as a performance proof.** The JVM optimizes virtual methods and interface calls quite aggressively; architectural choices should be based on semantics, maintainability, and benchmarks if performance is a critical constraint.

## 42. Static Utility, Association, and Inheritance: Choosing the Right Tool

Not every operation needs one of these two techniques:

```java
int maximum = Math.max(10, 20);
```

This is a pure **static utility** call, with no collaborator object needing to be stored in a field.

If a helper has configuration, caching, or an external resource:
- It may be worth making it an injected service component.
- If it is just a pure expression, a static method may suffice.
- You should not create a superclass just to pull a static helper into a hierarchy.

A useful criterion:

**Stateful behavior managed by an instance?** Consider an instance collaborator/composition.

**Pure stateless calculation?** Consider a static function or functional interface if the implementation needs to be swappable.

**Behavior belonging to the subtype itself?** Consider instance polymorphism/interface/inheritance.

## 43. API Compatibility: Inheritance Constrains Library Users

If a library publishes:

```java
public class BaseProcessor {
    protected void step() {
    }
}
```

clients may have already created subclasses overriding `step()`. Modifying the superclass:
- Adding/changing methods;
- Changing the call order of hooks;
- Changing access;
- Marking as final;
- Changing invariants in the constructor;

can break source/binary compatibility or client behavior.

With composition over a narrow interface, a library can isolate many implementation details from external plugins. However, **changing the interface contract** can also break compatibility, so versioning and contract testing are similarly needed.

### Practical Rule

A class should be designed “for inheritance” only when **the author intentionally supports subclassing**, documenting overridable methods and the semantics of hooks. Otherwise, consider a `final class` or not exposing protected extension points, while providing interfaces/composition for extension.

## 44. `equals`/`hashCode` and Subtypes

A base class that defines `equals` based on its fields, followed by a subclass adding fields, can lead to **symmetry** or **transitivity** issues if each subtype has different comparison logic.

Conceptual example of the risk:

- Base compares using only `id`.
- Subclass wants to include `region` in `equals`.
- `base.equals(child)` can be true, while `child.equals(base)` is false if written inconsistently.

This is why **value objects** are often designed as `final` or use a `record` with appropriate immutable components, instead of allowing subclasses to add state to the equality model.

If the business logic requires multiple variants, a sealed hierarchy or a well-designed identifier/value contract can be used.

**Composition reduces the need to subclass value types**, yet holding a collaborator object also requires considering whether equality semantics should depend on identity or value.

## 45. State Mutation and Concurrency

Composition does not automatically guarantee thread safety; neither does inheritance.

```java
final class Catalog {
    private final List<String> items =
            new ArrayList<>();
}
```

Even though Catalog is final and keeps the list private, the list is still mutable. If multiple threads update it, you must define synchronization or use appropriate immutable snapshots/concurrent collections.

Similarly, a strategy object **shared across multiple services** may hold mutable cache/state. Constructor injection does not mean the strategy is automatically thread-safe.

When designing:
- Evaluate whether the component is **stateless/immutable**.
- If mutable, who has write permission?
- Is a single instance shared, or is there one instance per request?
- Does closing a resource affect other services?
- At what level must operations be atomic?

Do not pick inheritance or composition as a cure for all race conditions; they solve **relationship structure**, whereas concurrency is a separate contract.

## 46. Signs a Design Should Be Refactored

### From Inheritance to Composition

Signs:
- Multiple subclasses differing only because of config.
- Overriding a method to disable superclass functionality with an exception.
- A subclass inherits solely to get a helper method.
- Changes in the parent break a series of subclasses.
- Tests have to subclass the service just to fake an external dependency.
- Lots of `instanceof`/casting because the hierarchy does not fit.
- Inheriting from a concrete collection while wanting to forbid mutators.

One refactoring path:
1. Identify the capability actually used from the base class.
2. Create a dedicated interface for that capability.
3. Extract the implementation into a collaborator.
4. Inject the collaborator into the using class.
5. Turn overrides into implementations/decorators/strategies where appropriate.
6. Test to preserve public behavior before removing extends.

### From Complex Composition to a Hierarchy/Simplification

Signs:
- Dozens of wrapper classes that merely forward identically.
- Variants that are truly closed alternatives but use `Object` + if/cast.
- The system needs to enforce a shared invariant across a subtype family, yet lacks a stable abstraction.
- Overlapping interfaces that serve no real client.

You can merge interfaces, use records/sealed variants, or use an abstract class with a clear contract. **Refactor according to domain constraints**, not slogans.

## 47. A Problem Requiring Both Approaches

Suppose a company has multiple `PaymentProvider` implementations, each with its own logic, while a `PaymentService` needs retry and logging.

Design:
- `PaymentProvider` interface with `pay(...)`.
- `StripeProvider` and `BankProvider` implementations of the interface.
- `PaymentService` holds a provider and a retry policy: composition.
- A `RetryingProvider` decorator implements `PaymentProvider` and holds a delegate: both a subtype under the contract and composition.
- A payment result can be sealed `PaymentResult` variants (Success/Failure) if the variant set is designed to be closed.

Conceptual diagram:

```text
PaymentService
    |
    +-- has-a --> PaymentProvider <---- implemented by Providers
    |
    +-- has-a --> RetryPolicy

RetryingProvider -- implements --> PaymentProvider
RetryingProvider -- has-a -------> PaymentProvider

PaymentResult (sealed)
    +-- Success
    +-- Failure
```

**A system can use inheritance/interfaces where genuine subtypes exist, and composition where collaboration occurs.** That is usually the most balanced approach.

## 48. A Decision Checklist for Pull Requests

Before writing `extends B`:

1. Is A genuinely **a B** in the domain?
2. Can a client accepting B use A without encountering unexpected unsupported operations?
3. Do B's invariants, preconditions, and postconditions still hold for A?
4. Does A need to inherit all of B's public/protected contract?
5. Is the superclass designed/documented for subclass overriding?
6. Are you depending on the call order of the superclass's internal methods?
7. Do constructors/hook methods risk invoking overrides while subclass state is uninitialized?
8. Where could changing B break A?
9. Is this relationship merely for reusing code/algorithms?
10. Would a separate interface and a collaborator express the intent more accurately?

Before writing `private final B b;`:

1. Does A merely **use** B, or does A truly **own** B?
2. Who creates B, who replaces B, and who calls `close()` on B if needed?
3. Does the implementation need to change at runtime/via config?
4. Does interface B have a stable contract worth existing?
5. Is B shared across multiple clients?
6. If B is mutable, could external aliases break invariants?
7. Does the API expose a mutable backing object or collection?
8. Does B need to be thread-safe? Is B's scope singleton/request/object?
9. Are unnecessary interfaces/forwarding code being created?
10. Does the caller need to pass B in, or should A create a simple private detail itself?

If you cannot yet answer the most important questions, clarify the requirement/contract before locking in the architecture.

## 49. Exercise 1: Repository Extending a Collection

**Prompt:** `UserRepository` needs to add/remove/find Users, without letting callers freely mutate internal storage. Should it use `extends ArrayList<User>` to get methods for free?

**Answer:** Usually **no**. `ArrayList` provides broad mutators and indexed collection semantics that do not necessarily belong to the Repository contract. Use **composition** with a private `List<User>`, write an appropriate `save`/`findById`/`removeById` API, and protect invariants. Use a repository interface if multiple backend implementations are needed.

## 50. Exercise 2: Circles and Rectangles

**Prompt:** We need to iterate over a list of shapes and compute their areas; the shape types are fixed and every shape satisfies `area()`. What should we choose?

**Answer:** A `Shape` interface or abstract class with `Circle`/`Rectangle` implementations makes sense. If shared implementation/state is not needed, an **interface** usually suffices; if a shared template method/contract with state is needed, consider an abstract class. Either way, subtypes must satisfy LSP.

## 51. Exercise 3: Logging for All Services

**Prompt:** `OrderService`, `InvoiceService`, and `UserService` all need to write logs. Should they use `extends Logger`?

**Answer:** **No**, not just for code reuse. The services **use** a Logger, rather than being types of Logger. Inject a Logger interface or use an appropriate logging facility. Constructor injection can make testing and configuration easier, though logger lifecycle responsibility still needs to be clear if resources are involved.

## 52. Exercise 4: Switching Notification Channels at Runtime

**Prompt:** The user chooses Email or SMS when clicking send. Push needs to be added in the future.

**Answer:** Use a `MessageSender`/`Channel` interface with implementations, where the service **receives the collaborator per request or chosen by a factory**. This is composition/strategy. A hierarchy of `EmailUser`/`SmsUser` does not accurately reflect the axis of variation.

## 53. Exercise 5: Fixed Template Algorithm

**Prompt:** Every import must run `validate -> normalize -> persist`, differing only in the data parsing step, and the application intentionally defines a family of import jobs.

**Answer:** An abstract base `ImportJob` with `final execute` and abstract/protected `parse` can be appropriate. If parsing needs to be swapped independently or one import service supports multiple parsers, composition using a `Parser` interface also fits. The decision depends on the extension contract and runtime variability.

## 54. Exercise 6: Square – Rectangle and LSP

**Prompt:** `Rectangle` has independent `setWidth`/`setHeight`. `Square extends Rectangle`, but each setter forces both sides to be equal.

**Answer:** This is a sign of an **LSP violation** if Rectangle's clients rely on the two dimensions being independently modifiable. Although “Square is a rectangle” mathematically, Rectangle's mutability contract is incompatible. Consider immutable shapes with a different contract, a Shape interface, or composition of dimensions depending on the use case.

## 55. Exercise 7: Combining Audit and Compression

**Prompt:** A Writer needs to be able to enable auditing, data compression, and encryption, and combine any features in a configured order.

**Answer:** Using a **decorator chain/composition** is usually better than creating subclasses for every combination. Each wrapper implements the Writer interface and holds a Writer delegate. You need to test the transformation order and stream/resource ownership, especially who is responsible for closing.

## 56. Exercise 8: Library API Only Has `AbstractProvider`

**Prompt:** A framework publishes an abstract class with protected extension points and requires concrete providers to extend it for registration.

**Answer:** Inheritance is the **chosen framework contract** and can be used if the subclass adheres to the hooks/invariants. Wrap the framework in an adapter at the boundary so your domain does not have to deeply extend a concrete framework type if you want to reduce coupling.

## 57. Exercise 9: Multiple Consumers Sharing One Connection Pool

**Prompt:** Multiple services receive the same `DataSource` from the DI container; service A finishes before B. Should service A close DataSource?

**Answer:** Usually **no** if DataSource is owned by the container/app. Service A only has an association/dependency and **borrows** the resource. The actual owner manages closing according to the application lifecycle. Having a `private final DataSource` field does not prove ownership transfer.

## 58. Exercise 10: Success/Failure Variants

**Prompt:** An operation returns one of two results, Success or Failure; the variant set is closed and clients handle it according to the contract.

**Answer:** `sealed interface Result permits Success, Failure` and corresponding records can fit well in Java 17. This is a **subtype variants** relationship rather than necessarily strategy composition. If result-handling logic becomes complex, a visitor/service can be added instead of inserting too many switches/casts.

## 59. Exercise 11: Dynamic Payment Rules

**Prompt:** A payment service has three dimensions: payment gateway, fraud checker, and fee policy. Each component is chosen independently.

**Answer:** Composition of three interfaces: `PaymentGateway`, `FraudChecker`, and `FeePolicy`. Adding a gateway does not force creating every fee/fraud subclass combination. Use a composition root/factory and consider transactions/ownership/concurrency.

## 60. Exercise 12: Classes Using the Same Stateless Helper

**Prompt:** Five classes need to parse an integer string with the same simple rule, with no configuration and no external dependencies.

**Answer:** A **static utility** or a method on the right abstraction may be enough. There is no need to create a hierarchy or a DI interface. Choose the simple solution that satisfies the contract.

## 61. Exercise 13: Final Class and Extensibility

**Prompt:** A value object uses `final class CustomerId`. We want to support multiple ways of validating ID formats across different markets.

**Answer:** Keep `CustomerId` as a non-subclassable value object; use a **validator strategy** `CustomerIdValidator` or an appropriate factory/parse policy. Do not remove final and create subclasses for each market if the variations are really validation rules separate from identity.

## 62. Exercise 14: Protected Hooks and Constructor Risks

**Prompt:** A base class constructor calls `initialize()`, and the subclass override reads a field assigned in the subclass's initializer.

**Answer:** There is a risk of reading an uninitialized field (possibly seeing `null`/`0`). Avoid calling overridable methods from constructors; place steps requiring subtype state into a post-construction operation or use a fully constructed component and coordinate explicitly.

## 63. Exercise 15: A Class That Both Implements an Interface and Holds a Delegate

**Prompt:** `CachingRepository implements Repository` and has a `Repository delegate` field. Is this inheritance or composition?

**Answer:** **Both aspects:** `CachingRepository` is a subtype of the `Repository` interface by contract, and uses **composition/delegation** to the real repository. It is a wrapper/decorator that can cache reads. Interface inheritance does not mean inheriting implementation from a concrete repository.

## 64. Common Mistakes When Choosing

| Mistake | Why It Causes Problems | How to Fix |
| --- | --- | --- |
| Using `extends` just to use a few methods | False is-a, exposes inherited API, strong coupling | Composition/utility |
| Subclass throws `UnsupportedOperationException` for parent contract | Violates subtype expectations | Split role interfaces/hierarchy |
| One subclass per configuration | Combinatorial explosion | Strategies/components |
| Overusing `instanceof` and casting each subtype | The abstraction may be wrong | Polymorphism or split appropriate operations |
| Superclass constructor calls overridable hook | Subclass state not initialized yet | Avoid calling virtual methods during construction |
| Subclass depends on superclass internal call graph | Fragile base class | Document hooks or use delegation |
| Repository extends `ArrayList` | Exposes non-domain API | Private collection + business methods |
| Giving every class an interface | Increases cognitive overhead without real variation | Only create abstractions with a consumer/use case |
| Calling every field reference UML composition | Ownership is not automatically implied | Specify the lifecycle contract |
| Concluding a `final` field makes the object immutable | Mutable state can still change via reference | Copy/immutable representation |
| Injecting a shared resource then calling `close` on its own | Closes a resource owned by someone else | Identify the owner |
| Using inheritance to solve test mocking | Distorts domain design | Injection via interface |
| Thinking composition avoids inheritance/interfaces | Strategy implementations still implement interfaces | Distinguish is-a contract from has-a collaborator |
| Thinking inheritance is always faster | The JVM optimizes depending on workload | Benchmark when needed |
| Using sealed for open plugin extensions | Sealed restricts direct subtypes | Open interface if extensibility is needed |
| Subclassing an immutable value to add equality fields | Easily breaks `equals` contract | Final/record, role abstractions |
| Creating a shared mutable component without synchronization | Race conditions | Thread-safety/immutability |
| Changing policy at runtime without considering transactions | Inconsistent results | Policy snapshot or controlled lifecycle |

## 65. Conclusion: Choose by Relationship Meaning and Changeability

A simple rule of thumb to remember:

```text
If A is truly B and satisfies B's contract:
    -> Consider extends/implements.
       If shared implementation/state is needed:
           -> Consider abstract/base class.
       If a role contract is needed:
           -> Interface may suffice.

If A needs B to complete the work:
    -> Consider has-a/uses-a + delegation.
       If B has multiple implementations:
           -> Interface + DI/Strategy.
       If stacking additional features is needed:
           -> Decorator/Wrapper.
       If combining multiple axes is needed:
           -> Composition of multiple components.

If only a pure calculation is needed:
    -> Utility/static function may be the simplest.
```

**Three final principles:**

1. **Place is-a strictly where genuine substitutability exists.** Inheritance must preserve the behavioral contract, not merely share code.
2. **Use composition to model collaboration and independent change.** Collaborators are wired via interfaces/constructors/factories, while ownership and lifetime must still be defined.
3. **Avoid extremes.** A good design can use a sealed hierarchy for results, interfaces for roles, an abstract base class for framework hooks, and composition for strategies within the same application.

The right choice is the one that makes **specific requirements easy to express, invariants easy to protect, the API easy to test, and future changes less likely to cause unintended side effects**.
