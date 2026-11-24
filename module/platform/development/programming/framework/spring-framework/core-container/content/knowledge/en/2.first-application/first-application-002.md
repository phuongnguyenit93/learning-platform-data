# Creating Business Classes and Collaborator Contracts — Your First Spring Application

## 1. Goals and Application Overview

A useful application rarely consists of a single `main` method containing every statement. We typically need a **business class** that orchestrates a *use case*, and **collaborators** that provide persistence, send notifications, or call external systems.

In a minimal order-placement example:

- A user submits a request containing an order ID, item SKU, and quantity.
- `OrderService` validates/orchestrates the order-placement business flow.
- `OrderStore` is the **contract** for saving orders, without forcing the service to know whether data lives in memory or a database.
- `Notifier` is the **contract** for notifying when an order is accepted, without forcing the service to know whether notifications go to the console, email, or a message queue.
- An entry point creates the real implementations and passes them into `OrderService`. When using Spring, `ApplicationContext` together with `@Configuration`/`@Bean` can handle this assembly step.

Key takeaway: **model the classes and contracts first; let the assembly point decide the implementations later**. You can practice entirely in plain Java 17 first and then replace the assembly step with Spring Core Container.

~~~text
                request OrderRequest
                        |
                        v
                 +--------------+
                 | OrderService |        business class / use case
                 +--------------+
                   |          |
          uses     |          |     uses
                   v          v
             OrderStore     Notifier      collaborator contracts
                  ^           ^
                  |           |
         InMemoryOrderStore  ConsoleNotifier
                       concrete implementations
                              ^
                              |
                   main or Spring @Configuration
                      select, create, wire objects
~~~

Contracts limit what the caller **needs to know**; they are not a magic shield against every form of coupling. An interface can still be poorly designed, overly broad, or leak infrastructure details into the domain if responsibilities are placed wrongly.

## 2. Defining Roles Before Writing Code

| Component | Role | Should Know | Should Not Take On |
| --- | --- | --- | --- |
| `OrderRequest` | Valid, immutable input data | Order ID, item SKU, quantity | How to connect to a database or send email |
| `OrderService` | Executes the order-placement behavior | Processing rules and the **contracts** to call | SMTP URLs, driver names, SQL connection setup |
| `OrderStore` | Contract for saving orders | Save method and duplicate-ID error semantics | Specific SQL table schemas |
| `Notifier` | Contract for notifications | Method receiving notification info to send | Specific server addresses |
| `InMemoryOrderStore` | Demo implementation storing in RAM | Map structure and duplicate-ID checks | Business decisions of the service |
| `ConsoleNotifier` | Demo implementation printing alerts | How to write to stdout | Order acceptance conditions |
| `main` / `AppConfig` | Composition root | Which implementations are chosen, object graph | Ordering logic inside `OrderService` |

**Business classes differ from data classes:** a `record` holding data does not automatically become a service. `OrderService` is not a DTO because it has behavior; `OrderStore` is a contract rather than an HTTP-handling service.

**A collaborator does not have to be an interface.** In Java/Spring you can still inject a concrete class, especially when it is a stable dependency with no need for multiple implementations. We use interfaces here because we want to swap `ConsoleNotifier` for a fake in tests, or change the storage mechanism without modifying rules in `OrderService`.

## 3. Designing Meaningful Contracts

A good contract focuses on what the business class **wants to accomplish**, rather than describing how a specific technology works.

~~~java
public interface OrderStore {
    void save(OrderRequest order);
}

public interface Notifier {
    void notifyPlaced(String orderId);
}
~~~

This is an **illustrative snippet**, not a standalone Java file: `OrderRequest` is defined in the complete program below.

Both methods have clear meaning:

- `save(order)`: saves an order; in this demo, a duplicate ID throws an error instead of silently overwriting.
- `notifyPlaced(id)`: reports that the order was accepted; the client does not need to know how the message is delivered.

Avoid overly vague contracts like `void doSomething(Object input)`, or infrastructure-bound ones like `void executeSql(String sql)` when the service only needs `save(order)`. The level of abstraction should match real needs rather than mechanically creating an interface for every class.

**Define semantics and errors:** an interface must be understood consistently across implementations. For example, callers need to know whether `save` inserts, updates, or forbids duplicates; swapping implementations must not arbitrarily break those rules. If status return values or specialized error handling are needed, the contract can be expanded with return types and domain-specific exceptions in a real system.

### Validation Boundaries

Choose two validation levels:

1. `OrderRequest` guarantees non-nonsensical state (`id`/`sku` non-blank, `quantity` positive).
2. `OrderService` coordinates saving and notifying without repeating every check already enforced by the `OrderRequest` constructor.

This example **does not yet include payments, inventory, or database transactions**. Narrowing the scope like this helps learners see DI and collaborator design clearly before tackling heavier infrastructure.

## 4. Standalone Java 17 Program, Without Spring Yet

Create the project directory as shown below. The same `PlainJavaDemo.java` file will be reused in the Spring example in Section 6; there is no need to copy the domain into another project.

~~~text
first-business-app/
├── pom.xml                         # created in the Spring section; not needed for plain Java
└── src/
    └── main/
        └── java/
            └── demo/
                ├── PlainJavaDemo.java
                └── SpringBusinessApp.java  # created in the Spring section
~~~

First file: **`src/main/java/demo/PlainJavaDemo.java`**.

~~~java
package demo;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class PlainJavaDemo {
    private PlainJavaDemo() {
    }

    // Immutable value object that validates its own invariants.
    public record OrderRequest(String id, String sku, int quantity) {
        public OrderRequest {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id must not be blank");
            }
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
        }
    }

    // Collaborator contracts.
    public interface OrderStore {
        void save(OrderRequest order);
    }

    public interface Notifier {
        void notifyPlaced(String orderId);
    }

    // In-memory implementation so the example does not need a database.
    public static final class InMemoryOrderStore implements OrderStore {
        private final Map<String, OrderRequest> orders = new HashMap<>();

        @Override
        public void save(OrderRequest order) {
            Objects.requireNonNull(order, "order");
            if (orders.putIfAbsent(order.id(), order) != null) {
                throw new IllegalStateException("duplicate order: " + order.id());
            }
        }

        public boolean contains(String id) {
            return orders.containsKey(id);
        }
    }

    // Console-based notification implementation.
    public static final class ConsoleNotifier implements Notifier {
        @Override
        public void notifyPlaced(String orderId) {
            System.out.println("NOTICE " + orderId);
        }
    }

    // Business class: does NOT instantiate InMemoryOrderStore/ConsoleNotifier itself.
    public static final class OrderService {
        private final OrderStore store;
        private final Notifier notifier;

        public OrderService(OrderStore store, Notifier notifier) {
            this.store = Objects.requireNonNull(store, "store");
            this.notifier = Objects.requireNonNull(notifier, "notifier");
        }

        public String place(OrderRequest order) {
            Objects.requireNonNull(order, "order");
            store.save(order);
            notifier.notifyPlaced(order.id());
            return "ACCEPTED " + order.id();
        }
    }

    public static void main(String[] args) {
        // Plain Java composition root: select and wire dependencies.
        InMemoryOrderStore store = new InMemoryOrderStore();
        Notifier notifier = new ConsoleNotifier();
        OrderService service = new OrderService(store, notifier);

        String result =
                service.place(new OrderRequest("O-101", "BOOK", 2));
        System.out.println(result);
        System.out.println("FOUND " + store.contains("O-101"));

        // Fake used in unit testing: does not send real notifications.
        List<String> calls = new ArrayList<>();
        Notifier fake = id -> calls.add(id);
        OrderService tested = new OrderService(new InMemoryOrderStore(), fake);

        String testedResult =
                tested.place(new OrderRequest("T-9", "PEN", 1));
        System.out.println(testedResult);
        System.out.println("FAKE_CALLS " + calls);

        if (!calls.equals(List.of("T-9"))) {
            throw new AssertionError("Notifier contract was not called once");
        }
        System.out.println("TEST PASS");
    }
}
~~~

### Compiling and Running on Java 17+

Open a terminal in the **`first-business-app`** directory using JDK 17 or higher. PowerShell/CMD/Linux/macOS all run the following commands (forward slashes `/` in paths are supported by Java tooling):

~~~bash
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/PlainJavaDemo.java
java -cp out demo.PlainJavaDemo
~~~

**Exact stdout from `PlainJavaDemo`:**

~~~text
NOTICE O-101
ACCEPTED O-101
FOUND true
ACCEPTED T-9
FAKE_CALLS [T-9]
TEST PASS
~~~

Step-by-step trace:

1. `main` creates `InMemoryOrderStore` and `ConsoleNotifier`, then passes them into the `OrderService` constructor.
2. `OrderService.place` calls `store.save`, then `notifier.notifyPlaced`; the real notifier prints `NOTICE O-101`.
3. `main` prints the return value `ACCEPTED O-101` and confirms the order exists in the store.
4. In the test block, `fake` is a lambda implementing the `Notifier` contract by recording the order ID into a list. Hence **there is no `NOTICE T-9` line**.
5. The test compares recorded calls against `List.of("T-9")`, proving the service sent exactly one notification for the expected order ID.

**Why use a `record`?** `OrderRequest` is input data whose components are accessed via `id()`, `sku()`, and `quantity()`. Records are stably supported in Java 17; the *compact constructor* `public OrderRequest { ... }` validates inputs without manually reassigning each field when conditions hold.

**Note on side-effect ordering:** the demo saves first and notifies second. If notification fails after saving, the save has already occurred; plain Java does not roll back a `Map` automatically. Real applications need clear policies such as retries, idempotency, or transactions/outbox when multiple systems are involved. That is an advanced topic, so do not implicitly claim this example is “atomic.”

## 5. What Problem Does Each Design Decision Solve?

### 5.1. The Business Class Knows Only Contracts

~~~java
public OrderService(OrderStore store, Notifier notifier) {
    this.store = Objects.requireNonNull(store, "store");
    this.notifier = Objects.requireNonNull(notifier, "notifier");
}
~~~

This snippet is already part of `PlainJavaDemo.java`. The constructor expresses **required dependencies**. Using `final` ensures the reference cannot be reassigned after object creation, though it does not automatically make the dependent object immutable or thread-safe.

The business class **does not depend on implementation names**. When you want to write to a file instead of the console or store in a database instead of a Map, the assembly point swaps in the corresponding implementation (provided the implementations uphold the contract).

### 5.2. Distinguishing `uses` from `creates`

Two ways to write it:

~~~java
// Tight coupling: the service selects and creates its collaborator.
final class BadOrderService {
    private final ConsoleNotifier notifier = new ConsoleNotifier();
}
~~~

~~~java
// Dependency injection: the service only declares what it needs.
final class BetterOrderService {
    private final Notifier notifier;

    BetterOrderService(Notifier notifier) {
        this.notifier = Objects.requireNonNull(notifier);
    }
}
~~~

These two blocks are **design illustrations**, not independently runnable because `ConsoleNotifier` and `Notifier` are reused from the main example. The key point is not forbidding `new`, but **moving the choice and construction of collaborators to the place responsible for wiring**.

A short-lived data object like `new ArrayList<>()` inside a method does not have to become a Spring bean. By contrast, an HTTP client, mail sender, or repository needing configuration/lifecycle is usually a strong candidate to pass in from outside.

### 5.3. Contracts Do Not Make Every Change Free

Swapping implementations is smooth when agreed-upon behavior stays intact. If business requirements change from “only save the order” to “deduct inventory, charge payment, and run risk checks,” `OrderService` and its contracts themselves may need to change. Avoid advertising interfaces as a way to never touch business code.

If an interface bloats with dozens of unrelated methods, split it by the capabilities each consumer needs (Interface Segregation). If there is only one stable implementation and no abstraction is needed, constructor injection of a concrete class can still make sense.

### 5.4. How Should Files Be Organized as the Application Grows?

In a real project, split `OrderRequest`, `OrderService`, `OrderStore`, `Notifier`, and implementations into clear files/packages. For example:

~~~text
demo.order/
    OrderRequest.java
    OrderService.java
    OrderStore.java
    Notifier.java
demo.adapters/
    InMemoryOrderStore.java
    ConsoleNotifier.java
demo.config/
    AppConfig.java
~~~

This is a **package organization pattern**, not a layout you must create to run the single-file demo. Packages can be named differently depending on module boundaries; do not let the domain depend on adapters just because they shared a folder in an introductory exercise.

## 6. Replacing Assembly with Spring Core Container

Keep using the exact `PlainJavaDemo.java` from Section 4. Only add **`pom.xml`** and **`SpringBusinessApp.java`**. This shows that the application **does not need its service rewritten to “switch to Spring”**: we only change where dependencies are created and supplied.

### 6.1. Maven Dependency

Use the same Spring Framework 7.0.9 / Java 17 baseline as in the library setup lesson. The example is a console application using `spring-context`, **without Spring Boot, a web server, or a database**.

Create `pom.xml` in the `first-business-app` directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>first-business-app</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                    <mainClass>demo.SpringBusinessApp</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Bean Configuration and Spring Program

Create `src/main/java/demo/SpringBusinessApp.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class SpringBusinessApp {
    private SpringBusinessApp() {
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public PlainJavaDemo.InMemoryOrderStore orderStore() {
            return new PlainJavaDemo.InMemoryOrderStore();
        }

        @Bean
        public PlainJavaDemo.Notifier notifier() {
            return new PlainJavaDemo.ConsoleNotifier();
        }

        @Bean
        public PlainJavaDemo.OrderService orderService(
                PlainJavaDemo.OrderStore store,
                PlainJavaDemo.Notifier notifier) {
            return new PlainJavaDemo.OrderService(store, notifier);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            PlainJavaDemo.OrderService service =
                    context.getBean(PlainJavaDemo.OrderService.class);

            String result = service.place(
                    new PlainJavaDemo.OrderRequest("S-202", "NOTEBOOK", 3));

            System.out.println(result);
            System.out.println("FOUND "
                    + context.getBean(
                            PlainJavaDemo.InMemoryOrderStore.class
                      ).contains("S-202"));
        }
    }
}
~~~

From the `first-business-app` directory (containing `pom.xml`), run:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Stdout lines printed by `SpringBusinessApp`, in order:**

~~~text
NOTICE S-202
ACCEPTED S-202
FOUND true
~~~

`mvn -version` and Maven/plugins may print their own lines (versions, logs, or dependency download progress). The stdout block above shows only the **three lines produced by the example logic**. On the first run, Maven needs to be able to download dependencies if they are not cached yet.

### 6.3. What Did Spring Do in Place of Plain Java `main`?

1. `AnnotationConfigApplicationContext(AppConfig.class)` reads the configuration class and initializes the context.
2. `@Bean orderStore()` creates `InMemoryOrderStore`; `@Bean notifier()` creates `ConsoleNotifier`. They become beans managed by the container.
3. `@Bean orderService(OrderStore store, Notifier notifier)` declares two dependencies by their contract types. Spring resolves matching beans and passes them into the factory method parameters.
4. `new PlainJavaDemo.OrderService(store, notifier)` still exists **inside the configuration**, but `OrderService` does not `new` those collaborators itself.
5. `context.getBean(OrderService.class)` retrieves the fully wired service; `place` behavior and `OrderRequest` data remain unchanged.
6. `try-with-resources` closes the context. For Spring-managed beans, appropriate destruction callbacks are handled according to the context's lifecycle.

**No `@Autowired` is needed on `@Bean` parameters**: Spring resolves factory method dependencies automatically. `@ComponentScan` is also unnecessary because all beans are registered via `@Bean` in `AppConfig`.

**No need to annotate `PlainJavaDemo.OrderService` with `@Service`**: the class itself can remain a plain Java class; the container manages the instance returned by `@Bean`. Spring annotations should be used because they serve a specific mechanism, not to make the domain “look like Spring.”

## 7. Boundary Between Plain Java and Spring

| Criterion | Plain Java | Spring Core Container |
| --- | --- | --- |
| Who calls `new` on collaborators? | `main`, a factory, or composition root | `@Bean` factory/configuration or bean creation mechanism |
| Who passes `OrderStore` and `Notifier` into the service? | Manual wiring code | Container resolves `@Bean` method parameters |
| Must the service import Spring? | No | **No**, when using an independent domain as in the example |
| Can fakes be substituted in tests? | Yes, passed via constructor | Yes, and the service can be tested **without** a context |
| Do objects become Spring beans? | No, unless explicitly registered in a container | Yes, for instances created/registered via `@Bean` |
| Primary lifecycle | Creator/owner manages it | Container coordinates lifecycle for managed beans |
| Automatic REST endpoints/transactions? | No | **No**; separate infrastructure is required |

**DI is not synonymous with Spring**; constructor injection already appeared in the plain Java example. Spring helps configure and manage the object graph as the system grows. Conversely, using Spring does not automatically fix poor contract design: putting business logic inside `@Configuration` or calling `ApplicationContext.getBean(...)` everywhere still leaves an architecture hard to test and maintain.

### Avoiding Singleton Misconceptions

By default, `@Bean` typically has `singleton` scope within *one* container. This means one instance of the bean per definition in the context; **it does not mean thread safety**. `InMemoryOrderStore` here uses a `HashMap` for demonstration; **it is not suitable as a multithreaded production store** without proper synchronization or storage choice. Do not treat it like a real database.

## 8. Testing Contracts and Business Classes

### 8.1. Unit Testing Without Spring

With dependencies supplied via constructor, a fake can replace `Notifier`. Section 4 demonstrated `List<String> calls` to verify the service emitted the right order ID. We can also verify that invalid arguments are rejected before touching the store.

An additional **conceptually independent** check that can be inserted into plain Java `main` (omit from the main program if you want to preserve Section 4's exact stdout):

~~~java
try {
    new PlainJavaDemo.OrderRequest("BAD", "BOOK", 0);
    throw new AssertionError("Expected validation failure");
} catch (IllegalArgumentException expected) {
    System.out.println("VALIDATION PASS");
}
~~~

Placing the block above in `main` after the examples will **additionally print** `VALIDATION PASS`. Do not treat it as part of the stdout published in Section 4.

Further tests you can try:

- `new OrderService(null, notifier)` must throw `NullPointerException` due to `requireNonNull`.
- Calling `save` twice with the same `id` on one `InMemoryOrderStore` must reject the second call.
- When a fake `Notifier` throws an exception, by this demo's design the store has already saved the order. Tests should make this limitation explicit rather than assuming rollback.
- Replace the `OrderStore` implementation with a recording fake to verify the service forwards the exact `OrderRequest`.

### 8.2. Integration Testing with Spring Context

Unit tests for `OrderService` do not need to start Spring. However, to test *wiring*, you can build a context from `AppConfig` in a test, retrieve `OrderService` via `getBean`, and verify dependencies and invocations.

Things to verify in an integration test:

- Exactly one matching `OrderStore` and `Notifier` candidate exists to inject.
- Context configuration starts up cleanly.
- The `OrderService` bean can be retrieved with no missing dependencies.
- If multiple implementations of the same interface are added, the selection mechanism (`@Primary`, `@Qualifier`, naming...) is unambiguous.
- Do not test for “exactly one bean across the entire JVM”: singleton scope is per container.

When testing wiring with real data sources or email servers, isolate the test environment to prevent unintended side effects.

## 9. Next Steps from Your First Application

When evolving this into a more useful application, you can grow it incrementally:

1. **Domain model:** add order status, pricing, and meaningful constraints. Pick an appropriate monetary type; avoid `double` for exact financial calculations.
2. **Repository:** replace `InMemoryOrderStore` with a database implementation while preserving the save contract and duplicate-ID error semantics.
3. **Notifier:** add email/queue delivery with appropriate retry and idempotency policies; never hard-code secrets into business classes.
4. **Service:** split inventory, payment, and approval rules if the use case demands it; do not cram every behavior into a single “God Service.”
5. **Configuration:** keep implementation selection, client creation, and resource management in adapters/configuration.
6. **Transactions:** if multi-step persistence consistency is required, configure a transaction manager and transaction boundaries. `@Bean` alone does not provide database transactions.
7. **Web API:** when HTTP is needed, add controllers and Spring Web MVC or WebFlux. `spring-context` alone does not open an HTTP port.
8. **Error observability:** emit clear exceptions/logs; define retry policies if sending notifications fails.
9. **Testing:** unit test services with fakes, integration test wiring and persistence, and acceptance test end-to-end flows.

Note the design order: **contracts reflect the needs of the consuming class**, and then adapter technologies are selected. Do not let library or infrastructure names dictate your entire business API.

## 10. Common Mistakes and How to Spot Them

| Symptom | Cause / Remediation |
| --- | --- |
| Service both processes orders and calls `new JdbcConnection` directly | Mixing business logic and construction details; move collaborators to constructor parameters |
| Field declared as `OrderStore` but initialized with `new SqlOrderStore()` inside the service | Still locks in a concrete implementation; using an interface on the field is not enough |
| Constructor has 10–15 unrelated dependencies | Re-evaluate service responsibilities; consider splitting use cases or using an aggregator rather than hiding bloat behind injection |
| Service calls `ApplicationContext.getBean(...)` everywhere | Service Locator hides dependencies; prefer constructor injection |
| `@Bean orderService` cannot find `OrderStore` | Bean not registered, wrong type, or inactive profile; inspect configuration |
| Two `Notifier` beans exist causing ambiguous injection | Select an implementation via `@Qualifier`/`@Primary` or clarify configuration |
| Calling `new OrderService(...)` outside the context and expecting bean lifecycle | Objects outside the container are not managed as beans |
| Using the demo's `HashMap` store for concurrent requests | Mutable state is not thread-safe; use appropriate storage/synchronization |
| Fake test only asserts no exception was thrown, never checking calls | Assert the order ID sent and the invocation count |
| `Notifier` fails and caller assumes the store rolls back automatically | There is no transaction or compensation; design an explicit consistency policy |
| Skipping validation of `id`/`quantity` | Invalid data leaks deep into collaborators; enforce invariants on the right object |
| Writing interfaces solely to “follow the pattern” with no purpose | Avoid redundant abstractions; design for real substitutability and boundaries |

## 11. Self-Practice Exercises with Answers

**Exercise 1 — identify locked dependencies.** Why is this snippet harder to test?

~~~java
class OrderService {
    private final SmtpNotifier notifier = new SmtpNotifier();
}
~~~

This is illustrative code (`SmtpNotifier` is omitted). **Answer:** the service chooses the SMTP implementation and instantiates it itself. To substitute a fake for testing, you have to modify the code or use workarounds; constructor injection solves this by accepting the `Notifier` contract.

**Exercise 2 — adding another implementation.** Suppose you have `RecordingNotifier implements Notifier`. Do you need to modify `OrderService.place` to use this fake?

**Answer:** No, as long as the fake honors the contract. Simply pass `RecordingNotifier` when constructing the service or swap the `Notifier` bean in the test configuration.

**Exercise 3 — responsibility of `@Bean`.** Why does `return new PlainJavaDemo.InMemoryOrderStore();` inside `@Bean` not violate the rule against calling `new` in business classes?

**Answer:** `@Configuration` is responsible for **choosing and creating dependencies**. `OrderService` remains unaware of the concrete class and is not where adapters are instantiated.

**Exercise 4 — distinguishing contracts from data.** Should `OrderRequest` be created as a singleton Spring bean to reuse across all orders?

**Answer:** No. `OrderRequest` holds per-request data. Create a new immutable record for each request; turning it into a singleton bean introduces the wrong lifecycle coupling.

**Exercise 5 — error-handling rules.** If saving the order succeeds but sending the notification fails, does the current example roll back?

**Answer:** No. `save` ran before `notifyPlaced`, and there is no transaction or compensation mechanism. An explicit policy is needed to handle this case in a real application.

**Exercise 6 — switching persistence.** If you switch from `InMemoryOrderStore` to `JdbcOrderStore`, which parts change?

**Answer:** Write the new adapter implementing `OrderStore`, update bean/factory configuration, and add the appropriate DataSource/driver/tests. `OrderService` does not need to change if the contract and business rules stay the same.

## 12. Checklist Before Completing Your First Application

- [ ] Identify one use case with clear behavior (e.g., placing an order).
- [ ] Name the business class after its behavior: `OrderService.place`.
- [ ] Define input data and invariants: `OrderRequest`.
- [ ] Create only the collaborator contracts actually needed: `OrderStore`, `Notifier`.
- [ ] Give each implementation a single primary responsibility; do not cram business logic into adapters.
- [ ] Declare required dependencies in the constructor and check for non-null.
- [ ] Wire with plain Java `main` first, verifying output and basic errors.
- [ ] Create fakes to test the service without real I/O.
- [ ] When adding Spring, use `@Configuration`/`@Bean` to wire the object graph without altering business rules.
- [ ] Verify `mvn compile exec:java` runs and distinguish program stdout from Maven logs.
- [ ] Check duplicate IDs, invalid inputs, collaborator exceptions, and non-atomic side effects.
- [ ] Do not equate the IoC Container with database transactions, an HTTP server, or a unit testing framework.

**Conclusion:** When building your first Spring application, separate **business classes** from **collaborator contracts**. `OrderService` expresses the order-placement behavior; `OrderStore` and `Notifier` express the capabilities the service requires. Java 17 already supports constructor injection and fake-based testing. Spring Core Container creates and wires beans via `@Configuration`/`@Bean` without forcing the domain to depend directly on Spring — providing a foundation to scale your application while keeping every class's responsibilities under control.