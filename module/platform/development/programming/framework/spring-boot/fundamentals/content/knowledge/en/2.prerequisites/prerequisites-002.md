# Classes, Interfaces, and Dependencies Between Objects

When building a Spring Boot application, you often see classes like `UserController`, `UserService`, `UserRepository`, or `PaymentGateway`. Each class handles one part of the job, but the application only works when the objects created from those classes know how to collaborate with one another.

To understand Spring's **Dependency Injection (DI)**, you first need to grasp three ideas in Java:

1. A **class** describes the data and behavior of a kind of object; an **object** is an instance created while the program runs.
2. An **interface** describes a contract that implementing classes commit to providing; as a result, consuming code can work with multiple different implementations.
3. A **dependency** arises when one component needs another component to complete its work. How dependencies are organized and supplied directly affects maintainability, replaceability, and testability.

This lesson progresses from plain Java to how Spring Boot wires objects together. The goal is to understand the essence of each relationship, not just memorize annotations.

## 1. Distinguishing Classes and Objects

### 1.1. A Class Describes Structure and Behavior

In Java, a **class** can declare:

- **Fields:** data or state that each object holds.
- **Constructors:** rules for initializing an object.
- **Methods:** behavior of the object.
- **Access modifiers:** visibility scopes such as `public`, `private`, or package-private.

Example creating the `Customer` class in `Customer.java`:

~~~java
public class Customer {
    private final String name;
    private int rewardPoints;

    public Customer(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Customer name is required");
        }
        this.name = name;
        this.rewardPoints = 0;
    }

    public String getName() {
        return name;
    }

    public int getRewardPoints() {
        return rewardPoints;
    }

    public void earnPoints(int points) {
        if (points <= 0) {
            throw new IllegalArgumentException("Points must be positive");
        }
        rewardPoints += points;
    }
}
~~~

Meaning:

- `Customer` is a programmer-defined **data type**.
- `name` and `rewardPoints` are state belonging to each `Customer` object.
- `Customer(String name)` is the constructor, establishing a valid initial state.
- `earnPoints` is a behavior; it validates the input before modifying state.
- `private` hides fields from external code; public methods provide controlled usage.
- `final` on `name` prevents reassigning the field's reference after initialization; it does not mean every object referenced by a `final` field is immutable.

### 1.2. An Object Is a Concrete Instance

Creating and using objects in `Main.java`:

~~~java
public class Main {
    public static void main(String[] args) {
        Customer lan = new Customer("Lan");
        Customer minh = new Customer("Minh");

        lan.earnPoints(20);
        minh.earnPoints(5);

        System.out.println(lan.getName() + ": " + lan.getRewardPoints());
        System.out.println(minh.getName() + ": " + minh.getRewardPoints());
    }
}
~~~

Output:

~~~text
Lan: 20
Minh: 5
~~~

The two variables `lan` and `minh` reference **two distinct objects**, both created from the same `Customer` class. Changing `lan`'s points does not automatically change `minh`'s points.

~~~text
                   class Customer
                 +----------------+
                 | name           |
                 | rewardPoints   |
                 | earnPoints()   |
                 +----------------+
                        │
                 creates instances
                   /          \
                  ▼            ▼
          object "Lan"    object "Minh"
          points = 20     points = 5
~~~

A variable of a class or interface type usually stores a **reference** to an object, not the entire object itself. For example:

~~~java
Customer first = new Customer("Lan");
Customer second = first;

second.earnPoints(10);
System.out.println(first.getRewardPoints()); // 10
~~~

`first` and `second` are two variables referencing **the same object**. This is an important difference compared to creating two separate objects with `new`.

### 1.3. Why Does Encapsulation Matter?

If `rewardPoints` were exposed publicly for anywhere to modify directly, another piece of code could assign `-100` and violate business rules. Keeping the field `private` and providing `earnPoints` lets the class protect the validity of its own state.

A well-designed class typically:

- Has a clear responsibility.
- Protects important data invariants.
- Provides methods expressing valid operations.
- Minimizes exposing internal storage details to external dependents.

Making all fields `private` is not enough on its own to guarantee good design; public methods must also reflect meaningful behavior.

## 2. Interfaces: Describing a Contract Without Fixing the Implementation

Suppose an application needs to send notifications to subscribers. Today notifications are printed to the console; later they might be sent via email or pushed to a message queue.

If business code always calls a concrete email-sending class directly, switching to another channel will require modifying the business code. Instead, we can define the **contract** first.

### 2.1. Declaring an Interface

File `NotificationSender.java`:

~~~java
public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

`NotificationSender` states that an object adhering to this contract must provide a `send` operation with two parameters. The interface **does not prescribe** whether notifications must be sent via email, HTTP, or console.

In Java:

- Use the `interface` keyword to declare a contract.
- Use `implements` for a class to commit to implementing an interface.
- Ordinary methods declared as in the example above are implicitly `public abstract`.
- An interface can also have `default` methods, `static` methods, and several other supporting members. It is not limited strictly to abstract methods.
- You cannot instantiate an object directly with `new NotificationSender()` because an interface is not a concrete class with a constructor to initialize.

### 2.2. Classes Implementing the Same Contract

File `ConsoleNotificationSender.java`:

~~~java
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("[To: " + recipient + "] " + message);
    }
}
~~~

File `SilentNotificationSender.java`:

~~~java
public class SilentNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Intentionally does not send: useful in certain testing scenarios.
    }
}
~~~

Both classes can be used wherever the `NotificationSender` type is expected:

~~~java
NotificationSender sender = new ConsoleNotificationSender();
sender.send("lan@example.com", "Welcome!");
~~~

The variable `sender` is declared using the **interface** type, while the actual object is instantiated from `ConsoleNotificationSender`. At runtime, Java invokes `send` on the corresponding implementation class. Calling the same contract with different implementations is a manifestation of **polymorphism**.

~~~text
              <<interface>>
            NotificationSender
               + send(...)
                     ▲
            implements
                /     \
               /       \
              /         \
  ConsoleNotificationSender   SilentNotificationSender
       + send(...)                + send(...)
~~~

Polymorphism lets calling code state **what operation it needs**, while the implementing code decides **how that operation is performed**.

### 2.3. How Does an Interface Differ from an Abstract Class?

| Characteristic | Interface | Abstract Class |
| --- | --- | --- |
| Common purpose | Defines a role/contract that many different classes can fulfill | Shares base state or behavior across a family of related classes |
| Keyword used | `implements` | `extends` |
| Relationship with multiple types | A class can implement multiple interfaces | A class can directly extend only one class |
| Instance state | Cannot declare regular instance fields; interface fields are `public static final` constants | Can have instance fields |
| Constructor | Interfaces do not have constructors | Can have constructors to initialize superclass state |
| Methods with a body | Has `default`, `static`, and other language-permitted methods | Can have both regular methods and abstract methods |

For example, `NotificationSender` is a natural contract because different delivery mechanisms do not necessarily share state or algorithms. Conversely, a family of classes that genuinely share logic, data, and invariants might consider an abstract class.

**You do not need to create an interface for every class.** Interfaces are useful when expressing meaningful boundaries, contracts with multiple implementations, or keeping dependencies clear. A simple, stable class with no need for abstraction can still be used directly.

## 3. Dependency: When One Object Needs Another Object

In object-oriented programming, **A depends on B** if A needs B or a capability of B to do its work. Dependencies can appear through:

- A field or constructor of A receiving a B object.
- A method of A calling a method of B.
- A method of A taking B as a parameter or returning B.
- A directly instantiating B with `new B()`.
- A using B's API, data types, constants, or static methods.

Not all dependencies carry the same degree of coupling. Two classes can be deeply coupled in logic or depend only on a narrow contract.

### 3.1. An Example of Tight Coupling to a Concrete Class

Suppose `RegistrationService` is responsible for registering users and sending a welcome message:

~~~java
public class RegistrationService {
    public void register(String email) {
        // Simulate successful registration.
        ConsoleNotificationSender sender = new ConsoleNotificationSender();
        sender.send(email, "Welcome!");
    }
}
~~~

Dependency graph:

~~~text
RegistrationService
        │
        │ directly instantiates with new and calls
        ▼
ConsoleNotificationSender
~~~

This may be acceptable in a very small program, but has drawbacks as the system grows:

1. `RegistrationService` knows the exact concrete notification sender class.
2. To switch from console to email, you must modify `RegistrationService`.
3. To test without triggering actual delivery side effects, it is hard to swap out the sending component.
4. If `ConsoleNotificationSender` needs a URL, token, connection pool, or another dependency, the registration service gets pulled into initializing that chain of objects.

These issues are commonly referred to as **tight coupling**. They do not stem from `new` being "wrong", but from placing concrete infrastructure decisions inside business code that should not know those details.

### 3.2. Depending on an Interface and Receiving Objects from Outside

`RegistrationService.java` can be redesigned as follows:

~~~java
import java.util.Objects;

public class RegistrationService {
    private final NotificationSender notificationSender;

    public RegistrationService(NotificationSender notificationSender) {
        this.notificationSender =
                Objects.requireNonNull(notificationSender, "notificationSender");
    }

    public void register(String email) {
        // Simulate successful registration.
        notificationSender.send(email, "Welcome!");
    }
}
~~~

Now `RegistrationService` only knows the `NotificationSender` contract. It does not need to know whether the notification is sent via console, email, or another channel.

From outside, we wire the objects together:

~~~java
public class Main {
    public static void main(String[] args) {
        NotificationSender sender = new ConsoleNotificationSender();
        RegistrationService service = new RegistrationService(sender);

        service.register("lan@example.com");
    }
}
~~~

Output:

~~~text
[To: lan@example.com] Welcome!
~~~

This is **constructor injection** implemented in plain Java: the dependency is passed into the constructor of the object that needs it.

~~~mermaid
flowchart TD
    M["Main: object wiring entry point"] -->|creates| C["ConsoleNotificationSender"]
    M -->|creates with dependency| R["RegistrationService"]
    R -->|depends on contract| I["NotificationSender (interface)"]
    C -.->|implements| I
~~~

The relationship `RegistrationService -> NotificationSender` is still a **dependency**. Dependency Injection does not eliminate the dependency; it makes the dependency explicit and moves the decision of which concrete object to use outside the class.

The exact same `RegistrationService` can use a different implementation:

~~~java
NotificationSender sender = new SilentNotificationSender();
RegistrationService service = new RegistrationService(sender);
service.register("lan@example.com");
~~~

No changes to `RegistrationService`'s code are needed.

### 3.3. Who Should Be Responsible for Creating and Wiring Objects?

In the plain Java program above, `Main` acts as the **composition root**: the place where objects are created and dependencies are wired together to form the application.

This is an important design idea: the decision of "which implementation to use" can be centralized at the startup/wiring point, while business classes simply receive what they need.

If `RegistrationService` also depends on `CustomerRepository` and `PasswordEncoder`, the constructor clearly shows those needs:

~~~java
public RegistrationService(
        CustomerRepository customerRepository,
        PasswordEncoder passwordEncoder,
        NotificationSender notificationSender) {
    // Store dependencies for use in business methods.
}
~~~

The snippet above only illustrates the constructor signature; `CustomerRepository` and `PasswordEncoder` are hypothetical types not defined in the runnable example from earlier.

A constructor needing too many dependencies can be a sign that the class is taking on too many responsibilities. However, there is no absolute number that applies to every application.

## 4. Distinguishing Relationships Between Classes and Objects

Learners often confuse "class A knows class B" with "A is a kind of B", or mistake every reference relationship for inheritance. The following relationships have distinct meanings.

| Relationship | Easy-to-Remember Question | Illustration |
| --- | --- | --- |
| **Inheritance** | Is A a kind of B? | `Dog extends Animal` |
| **Interface implementation** | Does A fulfill contract B? | `EmailSender implements NotificationSender` |
| **Association** | Does an object A relate to / hold a reference to an object B? | `Order` knows the `Customer` of the order |
| **Aggregation** | Does A contain or group B while B can exist independently? | `Team` has multiple `Member`s that exist outside the team |
| **Composition** | Does A own part B with a tightly bound lifecycle in the model? | `Order` owns its `OrderLine`s |
| **Dependency / uses** | Does A need to use B to perform a behavior? | `RegistrationService` uses `NotificationSender` |

### 4.1. Inheritance `extends`: The "is-a" Relationship

Example:

~~~java
class Animal {
    void sleep() {
        System.out.println("Sleeping");
    }
}

class Dog extends Animal {
    void bark() {
        System.out.println("Woof");
    }
}
~~~

`Dog` is a subtype of `Animal`, so a `Dog` object can be referenced by a variable of type `Animal`:

~~~java
Animal animal = new Dog();
animal.sleep();
~~~

Inheritance helps establish type hierarchies and reuse some behavior, but it also creates a dependency on the superclass structure. Do not use `extends` merely because two classes share a few similar lines of code.

### 4.2. Implementation `implements`: "Fulfilling a Contract"

~~~java
interface Printable {
    void print();
}

class Invoice implements Printable {
    @Override
    public void print() {
        System.out.println("Printing invoice");
    }
}
~~~

`Invoice` fulfills the `Printable` contract. A class can implement multiple interfaces simultaneously if all of those contracts fit its role.

### 4.3. Association: Relating to Another Object

~~~java
class Order {
    private final Customer customer;

    Order(Customer customer) {
        this.customer = customer;
    }
}
~~~

`Order` holds a reference to `Customer`. The two objects can exist independently; deleting an order does not necessarily cause the customer to disappear.

This is an **association**: a structural relationship between objects. That relationship also creates a form of dependency in the source code.

### 4.4. Composition: Composed of Owned Parts

~~~java
import java.util.ArrayList;
import java.util.List;

class Order {
    private final List<OrderLine> lines = new ArrayList<>();

    void addLine(String sku, int quantity) {
        lines.add(new OrderLine(sku, quantity));
    }

    List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}

record OrderLine(String sku, int quantity) {
}
~~~

This example models `Order` as the owner of its order lines: lines are created and managed within the scope of the order, and the returned list is a copy that prevents direct structural modification. In domain design, an individual order line typically has no independent meaning after the order is deleted.

The concept of composition refers to **ownership and lifecycle in the design model**; Java does not automatically delete object B at the exact moment A ceases to exist. The garbage collector reclaims memory based on reachability, not UML notation.

### 4.5. Aggregation: Grouping Without Exclusive Ownership

~~~java
import java.util.List;

class Team {
    private final List<Customer> members;

    Team(List<Customer> members) {
        this.members = List.copyOf(members);
    }
}
~~~

In an appropriate model, `Team` groups `Customer`s as members without owning their lifecycle. A member can still exist or belong to another group even if the `Team` is deleted.

In Java, association, aggregation, and composition **can all use reference fields**. The distinction lies in business meaning and ownership rules; looking solely at the type `List<Customer>` is usually not enough to tell for sure.

### 4.6. Dependency Is Broader Than Holding a Field

~~~java
class ReceiptPrinter {
    void printReceipt(Order order) {
        System.out.println("Order: " + order);
    }
}
~~~

`ReceiptPrinter` uses `Order` as a parameter and therefore depends on the `Order` type, even though it does not store `Order` in a field.

Similarly, a class calling `LocalDate.now()` depends on the `LocalDate` API at the call site. Not every dependency needs to be passed via constructor; we prioritize injection for collaborators that need to be swapped, have their lifecycle managed, or have behavior controlled at meaningful boundaries.

## 5. How Are Dependency Injection and Inversion of Control Related?

The two terms often appear alongside Spring, but they are not synonymous.

**Dependency Injection (DI)** is a technique where an object receives its dependencies from elsewhere rather than choosing and creating all of its dependencies itself.

**Inversion of Control (IoC)** is a broader concept: part of the control over coordination or instantiation is transferred to an external component, such as a container. The Spring IoC container manages creating and wiring many application objects, calling them **beans**.

### 5.1. Three Common Ways to Provide Dependencies

**Constructor injection**

~~~java
class ReportService {
    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = repository;
    }
}
~~~

Used when a dependency is required for the object to function. Allows keeping fields `final` and explicitly states what the class needs at creation time.

**Setter injection**

~~~java
class ReportService {
    private AuditLogger auditLogger;

    void setAuditLogger(AuditLogger auditLogger) {
        this.auditLogger = auditLogger;
    }
}
~~~

Can be suitable when a dependency is optional or intentionally changed during the object's lifecycle. You must clearly design for the case where it has not been set and consider runtime state mutability.

**Method parameter injection**

~~~java
class ReportService {
    void generateReport(ReportRepository repository) {
        // Use repository only for this invocation.
    }
}
~~~

The dependency is supplied per invocation. Suitable when a collaborator is only needed for a specific operation, or when the dependency genuinely varies per execution.

`ReportRepository` and `AuditLogger` in the three snippets above are hypothetical types to illustrate dependency passing forms. The snippets focus on relationship design, not standalone compilable examples.

In typical Spring applications, **constructor injection** is a clear choice for required dependencies because the object cannot be validly created without them. Spring also supports injection via setters, fields, and other mechanisms, though field injection can hide dependencies when instantiating a class in plain Java.

### 5.2. Dependency Inversion Principle (DIP) Differs from DI

DIP is a design principle: high-level logic should depend on appropriate abstractions rather than binding directly to low-level implementation details. Those abstractions should not be designed merely to serve one concrete implementation.

In the example:

~~~text
           RegistrationService
      (registration business logic)
                    │
                    ▼
       NotificationSender (interface)
                    ▲
                    │
       ConsoleNotificationSender
            (delivery detail)
~~~

`RegistrationService` depends on the `NotificationSender` **contract**, while `ConsoleNotificationSender` implements that contract. DI is **how** an implementation is supplied to the service.

It is possible to use DI while still depending on a concrete class:

~~~java
class RegistrationService {
    RegistrationService(ConsoleNotificationSender sender) {
        // Still received from outside, but depends on a concrete class.
    }
}
~~~

Therefore, **DI does not automatically guarantee DIP**. The two ideas complement each other: DIP helps design sensible dependency boundaries, while DI helps wire objects at runtime.

## 6. From Plain Java to Spring Boot: Who Creates and Wires Objects?

So far, `Main` has been directly creating dependencies:

~~~java
NotificationSender sender = new ConsoleNotificationSender();
RegistrationService service = new RegistrationService(sender);
~~~

This approach is valid and works well for small applications. Once you have dozens of controllers, services, repositories, and configurations, managing the entire object graph manually becomes repetitive. Spring addresses that task through the **IoC container**.

Spring Boot makes starting and configuring the Spring application context more convenient. Component annotations and constructors make dependency relationships explicit so the container can instantiate beans and wire them together.

### 6.1. Minimal Spring Boot Example

Suppose a Spring Boot 3.x project has the `spring-boot-starter-web` dependency and the following files under package `com.example.registration`:

~~~text
src/main/java/com/example/registration/
├── RegistrationApplication.java
├── NotificationSender.java
├── ConsoleNotificationSender.java
├── RegistrationService.java
└── RegistrationController.java
~~~

**File `RegistrationApplication.java`**

~~~java
package com.example.registration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegistrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegistrationApplication.class, args);
    }
}
~~~

**File `NotificationSender.java`**

~~~java
package com.example.registration;

public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

**File `ConsoleNotificationSender.java`**

~~~java
package com.example.registration;

import org.springframework.stereotype.Component;

@Component
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("Notify " + recipient + ": " + message);
    }
}
~~~

**File `RegistrationService.java`**

~~~java
package com.example.registration;

import org.springframework.stereotype.Service;

@Service
public class RegistrationService {
    private final NotificationSender notificationSender;

    public RegistrationService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public String register(String email) {
        notificationSender.send(email, "Welcome!");
        return "Registered: " + email;
    }
}
~~~

**File `RegistrationController.java`**

~~~java
package com.example.registration;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {
    private final RegistrationService registrationService;

    public RegistrationController(RegistrationService registrationService) {
        this.registrationService = registrationService;
    }

    @PostMapping
    public ResponseEntity<String> register(@RequestParam String email) {
        return ResponseEntity.ok(registrationService.register(email));
    }
}
~~~

When the application is running, you can call:

~~~bash
curl -X POST "http://localhost:8080/registrations?email=lan%40example.com"
~~~

Sample response:

~~~text
Registered: lan@example.com
~~~

The application console prints:

~~~text
Notify lan@example.com: Welcome!
~~~

This example only illustrates **the object wiring process**. It does not persist registrations, validate emails, actually send emails, or build a production API.

### 6.2. What Does Spring Do at Startup?

Starting from the package containing the `@SpringBootApplication` class, default component scanning detects eligible component types in that package and its subpackages. In the example:

1. `@Component` marks `ConsoleNotificationSender` as a bean candidate.
2. `@Service` marks `RegistrationService` as a bean candidate while conveying service-layer semantics.
3. `@RestController` marks `RegistrationController` as a web component.
4. When creating `RegistrationService`, Spring sees the constructor requires `NotificationSender`, finds the compatible bean, and supplies `ConsoleNotificationSender`.
5. When creating `RegistrationController`, Spring supplies the `RegistrationService` bean.
6. Spring MVC uses the controller to handle requests to `POST /registrations`.

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] -->|creates/manages| B["ConsoleNotificationSender"]
    A -->|creates and injects NotificationSender| C["RegistrationService"]
    A -->|creates and injects RegistrationService| D["RegistrationController"]
    D -->|calls| C
    C -->|calls via interface| E["NotificationSender"]
    B -.->|implements| E
~~~

The key point to understand is that **Spring manages the application's beans**, not necessarily every Java object. An object created manually with `new` elsewhere does not automatically become a Spring bean.

For example:

~~~java
RegistrationService service =
        new RegistrationService(new ConsoleNotificationSender());
~~~

This is still valid Java, but `service` is created manually and is not automatically managed by the container. Calling the constructor directly also does not activate the full lifecycle mechanisms or processing that Spring performs for beans it manages.

### 6.3. Why Is `@Autowired` Not Needed on the Constructor Here?

When a Spring bean has only **a single constructor**, Spring can use that constructor for injection without needing `@Autowired`. Therefore:

~~~java
@Service
public class RegistrationService {
    private final NotificationSender sender;

    public RegistrationService(NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

is a common and clean idiom.

If there are multiple constructors or complex bean selection cases, constructor selection rules apply and you may need annotations, bean names, or additional configuration. What matters is that required dependencies appear clearly in the constructor signature.

## 7. What If Multiple Classes Implement the Same Interface?

Suppose the application registers another implementation:

~~~java
package com.example.registration;

import org.springframework.stereotype.Component;

@Component
public class LoggingNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("[LOG] " + recipient + ": " + message);
    }
}
~~~

Now the context may contain **two beans** compatible with `NotificationSender`:

~~~text
NotificationSender
       ▲
       ├── ConsoleNotificationSender  (@Component)
       └── LoggingNotificationSender  (@Component)
~~~

When `RegistrationService` requires a single `NotificationSender`, the container must determine which bean to use. If no rule resolves the ambiguity, Spring can fail with an error because there are multiple matching candidates.

Some design options:

### Option 1: Register Only the Needed Implementation

If an application only sends via console, there is no need to register `LoggingNotificationSender` as a bean too. This keeps the dependency graph simple and readable.

### Option 2: Use `@Qualifier` to Select a Bean Intentionally

~~~java
package com.example.registration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {
    private final NotificationSender sender;

    public RegistrationService(
            @Qualifier("consoleNotificationSender") NotificationSender sender) {
        this.sender = sender;
    }

    public String register(String email) {
        sender.send(email, "Welcome!");
        return "Registered: " + email;
    }
}
~~~

Under standard component-scan bean naming conventions, `ConsoleNotificationSender` has the default name `consoleNotificationSender`. `@Qualifier` helps select the exact candidate carrying that qualifier.

### Option 3: Use `@Primary` to Declare a Preferred Choice

~~~java
@Component
@Primary
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("Notify " + recipient + ": " + message);
    }
}
~~~

This snippet assumes the file has the required package declaration and imports for `@Component` and `@Primary`.

`@Primary` gives this bean precedence when multiple matching candidates exist and no more specific selection is provided. The choice should reflect actual needs; do not mark every implementation as primary.

If you **genuinely need all implementations**, Spring can also inject a collection such as `List<NotificationSender>`. That is a different design pattern from asking for a single implementation.

## 8. Object Lifetime Scope and the Implications of State

When you write manually:

~~~java
Customer a = new Customer("Lan");
Customer b = new Customer("Minh");
~~~

you explicitly create two objects. With Spring, the container can manage bean lifecycles by **scope**.

The common default scope of a Spring bean is **singleton per Spring application context**. This means the container typically creates one instance of that bean and reuses it whenever other beans request that dependency. "Spring singleton" should not be misunderstood as "exactly one instance of the class across the entire JVM across all application contexts".

This matters for classes with mutable state:

~~~java
@Service
public class CounterService {
    private int count;

    public int increase() {
        return ++count;
    }
}
~~~

In a web application handling multiple concurrent requests, `count` on a singleton bean is **shared state**; the `++count` operation is not safe under concurrent access. This example illustrates the risk and should not be used as a production request counter.

Conversely, a service holding only dependencies and method-local variables is much easier to reason about:

~~~java
@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

An injected dependency is not by default a fresh object per HTTP request. You must understand scope, state mutability, thread safety, and actual lifecycle when designing.

## 9. Common Mental Pitfalls

### 9.1. "Adding `@Service` to a class means calling `new` anywhere will inject its dependencies"

Incorrect. The container only performs injection on objects it manages according to the applicable mechanism. If you call `new` manually and expect `@Autowired` fields to be populated automatically, you may get `null` or fail when using the dependency.

The reliable approach is to let Spring manage beans that need injection and pass dependencies through constructors.

### 9.2. "If class A has a field of type B, A definitely owns B's lifecycle"

No. `RegistrationService` has a field of type `NotificationSender`, yet the Spring context itself may manage the sender. Holding a reference does not imply ownership or responsibility for creating/destroying that object.

### 9.3. "Having an interface guarantees low coupling"

Not necessarily. If an interface is too large or leaks implementation-specific details, callers remain heavily coupled. A good interface expresses **capabilities needed by the caller**, avoiding forcing every implementation to carry unrelated methods.

For instance, a `NotificationSender` needing only `send` is easier to use than an interface requiring methods like `connectToSmtpServer`, `flushKafkaTopic`, and `openDesktopWindow` on every implementation.

### 9.4. "If there is a circular dependency, just use field or setter injection"

Example:

~~~text
ServiceA → ServiceB → ServiceA
~~~

This is a **circular dependency**. With constructor injection, neither bean can be constructed in the normal sequence if each requires the other. Modern Spring Boot versions discourage and by default reject this kind of cycle.

Switching injection styles to mask the symptom usually hides a design issue. Re-examine the responsibilities between A and B, extract shared logic, or move orchestration up to another component where appropriate.

### 9.5. "Using interfaces means you have to use Spring"

No. The entire initial `NotificationSender` and `RegistrationService` example is plain Java. Spring did not invent interfaces, polymorphism, or DI. Spring provides a container and configuration rules to **manage object creation and wiring** at application scale.

### 9.6. "Every dependency needs its own interface"

There is no such rule. You can inject a concrete class when multiple implementations or a meaningful abstraction boundary do not yet exist. Avoid creating ceremonial interfaces just so an interface name mirrors an implementation name.

Prioritize clear responsibilities, swappability at meaningful boundaries, and actual testing needs.

## 10. Reading a Dependency Graph in a Spring Boot Application

Consider an order-processing application with the following components:

~~~text
OrderController
       │
       ▼
OrderService
       │
       ├──► OrderRepository (interface)
       │           ▲
       │           │ implements
       │           │
       │       JpaOrderRepository
       │
       └──► PaymentGateway (interface)
                   ▲
                   │ implements
                   │
             CardPaymentGateway
~~~

How to read it:

- The controller receives requests and calls the service; the controller **depends on** the service.
- The service implements ordering rules and needs persistence and payment capabilities.
- The repository and payment gateway are **abstractions** describing the needed capabilities.
- The implementing classes provide the concrete behavior.
- Spring can instantiate the beans and pass the implementations to the service if they are registered, eligible, and candidate selection resolves cleanly.

This diagram is an illustrative design model; `JpaOrderRepository` and `CardPaymentGateway` are not classes automatically generated by Spring Boot by name.

When reading the following constructor:

~~~java
public OrderService(
        OrderRepository orderRepository,
        PaymentGateway paymentGateway) {
    this.orderRepository = orderRepository;
    this.paymentGateway = paymentGateway;
}
~~~

you can immediately deduce: `OrderService` requires two collaborators to operate. Whether the system uses MySQL, PostgreSQL, a mock payment gateway, or a real gateway depends on the implementations wired from outside.

Reading **constructors and parameter types** is often the most helpful first step in understanding how a Spring Boot class connects to other components.

## 11. Step-by-Step Practice

### Exercise A: Identifying Classes and Objects

Given the code:

~~~java
Customer a = new Customer("Lan");
Customer b = a;
Customer c = new Customer("Lan");

b.earnPoints(15);
~~~

Determine:

1. How many `Customer` objects are created?
2. What is `a.getRewardPoints()`?
3. What is `c.getRewardPoints()`?
4. Why do `a` and `c` have the same name yet are not the same object?

**Solution hint:** There are two `new` calls, so two objects are created; `b` references the same object as `a`. `a`'s points are 15, while `c`'s are 0. Having the same name value does not determine whether two variables reference the same object.

### Exercise B: Swapping an Implementation Without Editing the Service

From the plain Java example in section 3, add a class:

~~~java
public class PrefixNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("NOTICE: " + recipient + " - " + message);
    }
}
~~~

Update the wiring point:

~~~java
NotificationSender sender = new PrefixNotificationSender();
RegistrationService service = new RegistrationService(sender);
service.register("minh@example.com");
~~~

Explain why changing only **the object passed to the constructor** works without modifying `RegistrationService.register`.

**Hint:** The service only knows the `NotificationSender` interface and calls `send`. The specific behavior depends on the implementing object passed in.

### Exercise C: Classifying Relationships

For each description, identify the most appropriate relationship:

| Scenario | Suggested Answer |
| --- | --- |
| `Bird extends Animal` | Inheritance |
| `SmsSender implements NotificationSender` | Interface implementation |
| `CheckoutService` calls `PaymentGateway.charge(...)` | Dependency |
| `Order` owns its own `OrderLine`s | Composition in the business model |
| `Team` contains `Member`s that still exist if the team is deleted | Aggregation in the business model |

Note: a piece of code can exhibit multiple relationship types at once. For example, `Order` holds references to order lines so it has a structural relationship, while also depending on the `OrderLine` type in source code.

### Exercise D: Predicting an Injection Error

A Spring project has two beans:

~~~java
@Component
class EmailSender implements NotificationSender {
    public void send(String recipient, String message) {
        // ...
    }
}

@Component
class SmsSender implements NotificationSender {
    public void send(String recipient, String message) {
        // ...
    }
}
~~~

While the service requires:

~~~java
@Service
class RegistrationService {
    RegistrationService(NotificationSender sender) {
        // ...
    }
}
~~~

What can happen at startup? State two ways to handle it.

**Hint:** If multiple valid beans exist and Spring cannot resolve a unique candidate, bean creation can fail. You can register a single appropriate implementation, or use `@Qualifier` or `@Primary` according to specific selection rules.

## 12. Key Takeaways Before Diving Deeper into Spring Boot

In Java, a **class** defines an object's capabilities and state, while an **interface** expresses a contract. An object can collaborate with another object by holding a reference, receiving it via constructor, or using it in a method call. These relationships form a **dependency graph**.

When designing an application, we want dependencies to be explicit, properly scoped to responsibilities, and flexible enough to swap implementations. **Constructor injection** makes required dependencies visible right at instantiation. **Dependency inversion** directs business logic toward appropriate abstractions. Combining both approaches makes code easier to extend and test as the system grows.

Spring Boot uses the Spring IoC container to handle creating and wiring many beans according to application configuration. Therefore, when you encounter `@Service`, `@Repository`, `@Component`, `@RestController`, or a constructor taking other types, read them as signals showing **which object holds which responsibility and which collaborators it needs**. Understanding that forms the foundation for learning Spring IoC, Dependency Injection, bean lifecycles, auto-configuration, and Spring Boot application architecture.
