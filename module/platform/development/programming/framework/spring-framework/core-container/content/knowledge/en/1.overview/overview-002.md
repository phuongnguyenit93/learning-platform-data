# The Object Coupling Problem When Instantiating with `new` — Spring Core Container

## 1. Scenario: Business Logic Choosing and Creating Its Own Collaborator

Consider an order processing service. After accepting an order, it needs to call another object to send a notification. A common direct way of writing this is:

~~~java
class OrderService {
    private final EmailNotifier notifier = new EmailNotifier();

    void placeOrder(String orderId) {
        // Process the order ...
        notifier.send(orderId);
    }
}
~~~

This is an **illustrative snippet**, not a standalone compilable program: `EmailNotifier` and `send` are not defined here. The issue to recognize does not lie in the `new` syntax itself, but in the fact that **`OrderService` decides which concrete class it depends on and takes responsibility for instantiating it**.

There are two relationships to distinguish:

- **Usage dependency:** `OrderService` needs notification-sending behavior. This is a genuine business requirement.
- **Construction dependency:** `OrderService` also knows the class name `EmailNotifier`, its constructor, configuration parameters, and sometimes the entire chain of objects that `EmailNotifier` needs.

When these two concerns are mixed in a single class, the business class not only **uses** its collaborator but also **selects and assembles** that collaborator. This is a form of **tight coupling**.

> `new` is not automatically a design flaw. What warrants attention is calling `new` on a *service/dependency whose policy may change* directly inside the business class that needs to use it.

## 2. Where Exactly Does Coupling Appear?

On the line:

~~~java
private final EmailNotifier notifier = new EmailNotifier();
~~~

`OrderService` is tied to at least three decisions:

1. **Implementation type:** it must be `EmailNotifier` rather than SMS, internal notifications, sending via a queue, or a fake used during testing.
2. **Creation mechanism:** it must have a matching constructor; if later the constructor requires `HttpClient`, server configuration, or credentials, the creation code may have to change.
3. **Timing and lifecycle:** the object is created whenever an `OrderService` is instantiated; the consuming class inadvertently takes responsibility for creating it and potentially cleaning up its resources.

Common consequences:

| When requirements change | If dependencies are created directly inside the service | What is desired |
| --- | --- | --- |
| Change the notification method | Edit `OrderService` code or add multiple `if` branches to pick implementations | Change the assembly configuration |
| Test orders without sending real notifications | Hard to swap `EmailNotifier` with a fake | Inject an object that records calls |
| Deployment needs environment-specific config | Service must read/know initialization configuration | Centralize configuration at the application boundary |
| Dependencies themselves need other dependencies | Chains of `new` spread across many classes | One place responsible for building the object graph |
| Need to manage collaborator close/lifecycle | Service may not know who owns the resource | The creator/manager decides the lifecycle |

Renaming one class may not cause a big problem. However, in a system with many collaborators, changing creation rules across many classes makes code **hard to replace, hard to test, and hard to configure**. This is why Spring Core Container handles creating and wiring managed objects.

**Distinction:** declaring a field with an interface type while still writing `new EmailNotifier()` inside the service only reduces coupling at the **variable type** level; it **has not separated the instantiation decision** from the service.

## 3. Standalone Java 17 Example: Seeing the Difference

This example uses console notifications, requiring no server or Internet access. Both the tightly coupled approach and the approach receiving its dependency from outside work, but the second approach allows passing in a fake during tests.

Save the file **`ManualWiringDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ManualWiringDemo {
    interface Notifier {
        void send(String orderId);
    }

    static final class ConsoleNotifier implements Notifier {
        @Override
        public void send(String orderId) {
            System.out.println("CONSOLE " + orderId);
        }
    }

    // Service chooses the implementation class and creates its own dependency.
    static final class HardWiredOrderService {
        private final ConsoleNotifier notifier = new ConsoleNotifier();

        void place(String orderId) {
            System.out.println("ORDER " + orderId);
            notifier.send(orderId);
        }
    }

    // Service only depends on the behavioral contract.
    static final class OrderService {
        private final Notifier notifier;

        OrderService(Notifier notifier) {
            this.notifier = Objects.requireNonNull(notifier, "notifier");
        }

        void place(String orderId) {
            System.out.println("ORDER " + orderId);
            notifier.send(orderId);
        }
    }

    // Test fake: only records calls, sends nothing externally.
    static final class RecordingNotifier implements Notifier {
        private final List<String> events = new ArrayList<>();

        @Override
        public void send(String orderId) {
            events.add(orderId);
        }

        List<String> events() {
            return events;
        }
    }

    public static void main(String[] args) {
        System.out.println("-- hard-wired --");
        new HardWiredOrderService().place("A01");

        System.out.println("-- injected --");
        new OrderService(new ConsoleNotifier()).place("B02");

        RecordingNotifier fake = new RecordingNotifier();
        new OrderService(fake).place("T03");
        if (!fake.events().equals(List.of("T03"))) {
            throw new AssertionError("Notifier was not called as expected");
        }
        System.out.println("events=" + fake.events());
        System.out.println("test=PASS");
    }
}
~~~

Open a terminal in the directory containing the file using **JDK 17+** (PowerShell/CMD or bash):

~~~bash
javac --release 17 -encoding UTF-8 ManualWiringDemo.java
java ManualWiringDemo
~~~

**Exact stdout:**

~~~text
-- hard-wired --
ORDER A01
CONSOLE A01
-- injected --
ORDER B02
CONSOLE B02
ORDER T03
events=[T03]
test=PASS
~~~

Step-by-step explanation:

1. `HardWiredOrderService` always creates `ConsoleNotifier`. To change how notifications are sent, you usually have to modify the service class itself or redesign the creation point.
2. `OrderService` receives `Notifier` through its **constructor**. It only knows the `send(orderId)` call, not how the implementation class is instantiated.
3. In `main`, `new OrderService(new ConsoleNotifier())` is still valid: `main` is acting as the **composition root**, the place where the application is assembled.
4. In the test check, we pass `RecordingNotifier`. Checking `events=[T03]` proves the service called the notification port properly, **without needing** email, network connections, or a Spring context.
5. The example prints `ORDER` to represent a simulated business operation; it **does not write to a real database**. In a real system, persisting the order would be performed by a separate collaborator if needed.

To test additional error branches or swap the notification mechanism, simply pass in a different `Notifier` implementation. There is no need to modify `OrderService` for each test environment.

## 4. What Does Constructor Injection Solve?

In the improved version:

~~~java
final class OrderService {
    private final Notifier notifier;

    OrderService(Notifier notifier) {
        this.notifier = java.util.Objects.requireNonNull(notifier);
    }

    void place(String id) {
        notifier.send(id);
    }
}
~~~

This is an **illustrative snippet**, separate from the complete file in section 3. Three important design decisions:

- **Behavioral contract:** `Notifier` describes *what needs to be done*; concrete classes decide *how to do it*.
- **Injection:** the collaborator reference is passed in via the constructor instead of being created inside the service. For required dependencies, a `final` field and constructor make the requirement explicit.
- **Separating the assembly site:** the business class does not have to locate, create, or choose an implementation option.

This is an application of the **Dependency Inversion Principle (DIP)** when the business layer points toward an appropriate abstraction instead of pointing directly toward infrastructure details. **Dependency Injection (DI)** is a technique for supplying collaborators from outside; DI itself does not require Spring or interfaces in every situation. You can inject a concrete class when reasonable, though an abstraction is often helpful when implementations genuinely need to be swapped.

The core difference is:

~~~text
Hard-coded inside the service:
OrderService ──new──> ConsoleNotifier

Provided from outside:
Composition root ──new──> ConsoleNotifier
        │
        └──new OrderService(notifier)──> OrderService ──uses──> Notifier
~~~

**It is not "delete every `new`":** we *move the decision of creating and wiring* out of the business class. Somewhere must still instantiate the objects.

## 5. Checking the Level of Decoupling

Changing the field type to `Notifier` **is not enough** if `OrderService` still calls `new EmailNotifier()` internally: the service still decides the implementation and how it is instantiated. The design litmus test is to ask **"who chooses and creates the collaborator?"**. With `OrderService(Notifier notifier)`, the answer lies with the caller/composition root; the service only calls the `send` contract.

Moving implementation selection outside makes it possible to change the notifier or configuration with minimal edits to business logic. If the contract or order-processing rules change, `OrderService` may still need changes — DI separates object-creation responsibilities; it does not guarantee immutable business code.

## 6. Where Does Spring Core Container Come In?

Plain Java can already perform constructor injection as shown in section 3. Spring adds an **IoC container** to manage objects registered as **beans** and assemble them based on configuration.

- **IoC (*Inversion of Control*):** responsibility for coordinating creation, configuration, and linking of beans shifts from business code to the container/configuration site.
- **DI (*Dependency Injection*):** a mechanism for supplying dependencies into an object; in this example, via a constructor parameter.
- **Bean:** an object registered with and managed by the Spring container in an `ApplicationContext`.
- **Object graph:** the network of objects depending on one another, e.g., `OrderService → Notifier`.

Spring does not make `new` "disappear." It simply helps **centralize bean creation and wiring decisions**. An object created with `new` at an arbitrary place **does not automatically become a bean** just because the project uses Spring.

Beans can be provided via `@Configuration` + `@Bean` or via component scanning (`@Component`/`@Service` and constructor injection). This lesson chooses **explicit `@Bean` methods** so the assembly site is clearly visible. There is no need to confuse `@Bean` with business code or put Spring annotations into `OrderService` itself.

## 7. Runnable Spring Program: Moving Assembly into Configuration

Requires **JDK 17+**, Apache Maven, and the ability to download Maven dependencies on the first run. The example uses **Spring Framework 6.2.0** with `spring-context`, without Spring Boot and without a web server. Spring 6.x requires Java 17 or higher.

Create the structure:

~~~text
coupling-spring/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringCouplingDemo.java
~~~

File **`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>coupling-spring</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.SpringCouplingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **`src/main/java/demo/SpringCouplingDemo.java`**:

~~~java
package demo;

import java.util.Objects;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SpringCouplingDemo {
    public interface Notifier {
        void send(String orderId);
    }

    public static final class ConsoleNotifier implements Notifier {
        @Override
        public void send(String orderId) {
            System.out.println("NOTIFY " + orderId);
        }
    }

    public static final class OrderService {
        private final Notifier notifier;

        public OrderService(Notifier notifier) {
            this.notifier = Objects.requireNonNull(notifier, "notifier");
        }

        public void place(String orderId) {
            System.out.println("ORDER " + orderId);
            notifier.send(orderId);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Notifier notifier() {
            return new ConsoleNotifier();
        }

        @Bean
        public OrderService orderService(Notifier notifier) {
            return new OrderService(notifier);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(OrderService.class).place("S04");
        }
    }
}
~~~

From the `coupling-spring` directory, run:

~~~bash
mvn -q compile exec:java
~~~

**Stdout lines printed by the program:**

~~~text
ORDER S04
NOTIFY S04
~~~

The Maven command may emit other messages depending on version, plugins, environment, or dependency downloads; the two lines above are the **stdout printed by the example logic**, without claiming Maven's full output is always only two lines.

### Tracing Bean Creation and Wiring

1. `new AnnotationConfigApplicationContext(AppConfig.class)` creates the context and processes the configuration.
2. `@Bean notifier()` returns a `ConsoleNotifier`. `new` **still exists**, but in the configuration class instead of inside `OrderService`.
3. `@Bean orderService(Notifier notifier)` declares a requirement for a bean of type `Notifier`; Spring finds the matching bean and passes it into the parameter.
4. Spring returns `OrderService` with its dependency wired; `context.getBean(OrderService.class)` retrieves the bean from the container.
5. `place("S04")` invokes the expected behavior; `try-with-resources` closes the context after use.

By default, beans in Spring have `singleton` scope **per container**. This is not a guarantee that the entire JVM has exactly one object across all contexts. If a type has multiple matching beans, the selection must be configured explicitly (for example `@Qualifier`/`@Primary` or injecting by an appropriate name); Spring does not guess business intent.

In this example, if you change `notifier()` to return a different implementation of the same `Notifier` contract, `OrderService`'s logic does not need to change. Configuration is still application code and must be tested appropriately.

## 8. Comparing Three Assembly Approaches

| Criterion | `new` directly inside service | Manual injection in Java | Injection via Spring container |
| --- | --- | --- | --- |
| Does the service know the concrete notifier class? | Yes | No, if accepting an interface | No, if accepting an interface |
| Where is the implementation chosen? | Inside the service | `main`/factory/composition root | `@Configuration`/component setup |
| Needs Spring to operate? | No | No | Yes, for the container part |
| Swapping a fake in unit tests | Usually harder | Easy: pass via constructor | Service can be tested plainly via constructor; integration tests have context |
| Who manages bean lifecycle? | Self-creating code | Assembler/owner | Spring manages beans belonging to the context |
| Completely eliminates `new`? | No | No | No |

**Key point:** Spring is a tool for organizing dependency creation and wiring; the design benefit comes primarily from the business class **accepting dependencies explicitly** rather than locking itself to a single implementation.

You do not have to boot Spring for every unit test. With `OrderService(Notifier)`, testing business logic can just use `RecordingNotifier` as a plain Java program. Spring integration tests are for verifying context configuration and bean wiring when that is what needs confirmation.

## 9. When Is `new` Completely Reasonable?

**`new` is not forbidden** in a Spring application. Distinguish by purpose and ownership:

- **Value objects or temporary data:** `new BigDecimal("12.50")`, `new ArrayList<>()`, short-lived result objects, etc., generally do not need to be Spring beans.
- **Internal objects owned by the class:** if it is simply an implementation detail and creation needs no configuration or swapping, `new` in place can be clearest.
- **Composition root or `@Bean` factory:** using `new` to create collaborators outside business classes is completely normal.
- **Infrastructure collaborators needing configuration, sharing, mocking/testing, or lifecycle:** usually good candidates to pass from outside or register as beans.
- **Objects created by third-party libraries:** you may not control constructors or turn them into beans directly; an adapter/factory at the right boundary layer may be needed.

Do not turn *every object* into a singleton bean: per-request data, mutable state, and resources with independent lifecycles need appropriate scopes/lifecycles. Conversely, calling `new` on a connection client on every request without managing cleanup can also cause waste or resource leaks.

A helpful question: **"If tomorrow I change how this part is implemented or tested, do I need to edit the business class or just change the assembly?"** If you always have to edit the business class just to swap infrastructure, coupling is usually higher than necessary.

## 10. Common Misconceptions and Mistakes

| Misconception | Accurate understanding |
| --- | --- |
| "Every `new` breaks DI." | Only when a business class chooses/creates *dependencies that should be decoupled* does an issue usually arise; creating value objects is normal. |
| "Just declaring an interface achieves decoupling." | If the service still calls `new ConcreteNotifier()`, the creation decision remains there. |
| "Using Spring means never writing `new`." | `@Bean` factories still commonly use `new`; what changes is where the object graph is coordinated. |
| "A manually created object automatically becomes a Spring bean." | No. Only objects registered/managed by the container receive the corresponding container mechanisms. |
| "Every class should use `@Autowired` on fields." | Constructor injection makes required dependencies clearer and supports unit tests without a context. |
| "Spring automatically picks the right bean when multiple share an interface." | Clear selection rules are needed if there are multiple candidates; ambiguous configuration can fail context startup. |
| "Separating DI means business code never changes." | Changing business behavior/contracts still requires edits; DI mainly isolates implementation/instantiation changes. |
| "Constructor injection automatically prevents all circular dependency errors." | If A needs B and B needs A right at creation time, that is still a design issue; break the cycle rather than hiding it with tricks. |
| "A singleton bean means thread-safe." | Scope does not automatically guarantee safety with concurrently mutated state. |
| "Unit tests must start Spring." | Explicitly injected logic can be tested with plain Java fakes; only start a context when testing wiring. |

An additional risk: passing `ApplicationContext` into every class and calling `getBean(...)` everywhere turns dependencies into **hidden lookups** (Service Locator). That can make dependencies hard to see and hard to test. In typical business services, prefer declaring collaborators via the constructor.

## 11. Exercises and Explained Answers

**Exercise 1 — identify the locked-in decision.**

~~~java
class ReportService {
    private final PdfExporter exporter = new PdfExporter();

    void export() {
        exporter.write();
    }
}
~~~

`PdfExporter` here is an illustrative type, not yet defined. Question: what is the main problem?

**Answer:** `ReportService` locks in both the *exporter type* and *how the exporter is created*. When switching to another export format or mocking in tests, you must modify code or redesign the class. Creating an `Exporter` abstraction and receiving it via the constructor is one way to improve it if real substitutability is needed.

**Exercise 2 — fix the creation site.** With `Notifier` and `OrderService` in section 3, how do you use a fake in tests without starting a Spring context?

**Answer:** create `RecordingNotifier fake = new RecordingNotifier();` then `new OrderService(fake)`. Check `fake.events()` to verify the interaction. The test does not have to invoke the real `ConsoleNotifier`.

**Exercise 3 — spot valid `new` usage.** Why does `return new ConsoleNotifier();` inside a `@Bean` method not contradict the goal of reducing coupling?

**Answer:** this location **is responsible for assembling** and choosing the implementation. The business service only receives `Notifier`; creation details are isolated in configuration. Spring manages the returned bean.

**Exercise 4 — distinguish approaches.** If a class receives `Notifier` via its constructor but `main` itself runs `new ConsoleNotifier()`, has DI been used?

**Answer:** **Yes.** Passing an object from outside into the constructor is constructor injection; Spring is not a mandatory prerequisite.

**Exercise 5 — decide whether a bean is needed.** Should a method creating `new ArrayList<String>()` to collect temporary results turn that list into a singleton bean?

**Answer:** Usually no. A temporary list holds per-call state, not a shared infrastructure collaborator. Turning it into a singleton can mix state across multiple calls and increase concurrency risks.

## 12. Checklist When Encountering Code with Many `new` Calls

1. Identify **which business class** needs a behavior and **which concrete class** is being self-instantiated.
2. Distinguish temporary value objects from **services/collaborators** that may be swapped or need configuration.
3. Check whether the collaborator's constructor/lifecycle pulls databases, networks, files, or config secrets into the business class.
4. Design a **small, meaningful contract** when multiple implementations actually exist; do not create interfaces merely out of habit.
5. Use **constructor injection** to pass required dependencies into the class.
6. Move implementation selection/creation to a **composition root**, factory, or Spring `@Configuration`.
7. Test the business class with simple fakes, verifying behavior without relying on external systems.
8. Test Spring configuration separately when you need to confirm beans are created and wired properly.
9. Watch bean lifecycles, mutable state, configuration errors, and cases with multiple implementations.
10. Only refactor where there is clear benefit; avoid turning `new` for simple data objects into complex machinery.

**Conclusion:** What increases coupling is not the `new` keyword by itself, but letting a business class **simultaneously use, choose, and instantiate its concrete dependencies**. Constructor injection separates those two roles even in plain Java. Spring Core Container further supports managing and wiring beans in a clear configuration location, making implementation swaps, testing, and lifecycle management easier as a project grows.