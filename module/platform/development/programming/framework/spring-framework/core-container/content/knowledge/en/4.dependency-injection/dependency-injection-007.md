# Contract-Based Injection Instead of Self-Lookup in Spring Core Container

## 1. Goal: A Service Declares What It Needs Instead of Looking It Up

A business class rarely operates in isolation: it needs storage, notification delivery, validators, a clock, or an external system API. There are two opposing design directions:

- **Looking up or instantiating collaborators directly:** the service calls `new SqlRepository()`, `ApplicationContext.getBean(...)`, or a global registry whenever it needs a dependency.
- **Receiving collaborators by contract (Dependency Injection / DI):** the service explicitly declares dependencies via constructor/factory method/setter and lets external wiring provide the right implementation.

For example, an order-intake use case needs exactly two **capabilities**: reserving inventory stock and publishing a receipt. The order handler only knows `InventoryPort` and `ReceiptPort`, without needing to know whether the adapter uses a `Map`, JDBC, or a remote service.

~~~text
                  composition root
              Java main / Spring AppConfig
                   |              |
       picks InMemoryInventory   ConsoleReceipt
                   |              |
                   v              v
           InventoryPort      ReceiptPort  <--- contracts
                   \              /
                    \ constructor/
                     v          v
                      CheckoutService
                             |
                      place(Order)
                         /      \
                        v        v
                 reserve stock  publish receipt
~~~

**Inversion of Control (IoC)** here means the service does not decide how collaborators are constructed or located. The unit responsible for startup/assembly chooses concrete implementations, while the service focuses on business rules.

After this lesson, you will be able to:

1. Identify the Service Locator pattern and direct `new` of dependencies that hide or tightly couple relationships.
2. Design interfaces around **consumer needs**, rather than technology-specific APIs.
3. Write constructor injection in Java 17 and test with fakes without Spring.
4. Configure Spring `@Bean` definitions to wire the exact same business class that imports nothing from Spring.
5. Distinguish when looking up a bean at the startup boundary or using a dynamic provider remains appropriate.
6. Explain missing/multiple-bean errors, scopes, and proxies without conflating them with the essence of DI.

## 2. Problems with Creating Collaborators Internally

### 2.1. Tight Coupling via `new` Inside the Service

~~~java
// Illustrative: the class names below must be defined in a real project.
final class BadCheckoutService {
    private final JdbcInventory inventory = new JdbcInventory();
    private final SmtpReceipt receipt = new SmtpReceipt();

    String place(Order order) {
        inventory.reserve(order.sku(), order.quantity());
        receipt.publish(order.id());
        return "OK";
    }
}
~~~

The snippet above **cannot compile standalone** because `JdbcInventory`, `SmtpReceipt`, and `Order` are not defined. It highlights the problems:

- The service hardcodes JDBC/SMTP directly, so unit tests may accidentally hit a real database or mail server.
- Swapping adapters requires editing business code or adding environment conditionals inside the service.
- Connection pool config, retries, credentials, and lifecycle are pulled into a class that should not own them.
- If the service creates unnecessary instances itself, resources may be wasted or leaked.
- The service's API hides key dependencies, obscuring the object graph at the constructor.

**Not every `new` is wrong.** Creating a value object like `new Order(...)` or a local list for computation does not need to be delegated to an IoC container. The problem is **the service itself choosing and constructing system-role collaborators** that ought to arrive from the assembly boundary.

### 2.2. Service Locator: Pulling Beans Inside Business Methods

An approach that appears less coupled is holding `ApplicationContext` and looking beans up:

~~~java
// Illustrative; assumes CheckoutService and the interfaces are already declared.
final class LocatingCheckoutService {
    private final ApplicationContext context;

    LocatingCheckoutService(ApplicationContext context) {
        this.context = context;
    }

    String place(Order order) {
        InventoryPort inventory = context.getBean(InventoryPort.class);
        ReceiptPort receipt = context.getBean(ReceiptPort.class);
        // Logic using inventory and receipt...
        return "DONE";
    }
}
~~~

This too is merely an **illustrative excerpt**, not a runnable file. It removes `new` on concrete adapters yet creates other issues:

1. The constructor only exposes a dependency on `ApplicationContext`, hiding that the service **needs** `InventoryPort` and `ReceiptPort`.
2. The service imports Spring APIs; plain Java unit tests must mock the container or supply an `ApplicationContext`.
3. A missing-bean error may surface **only when that business branch runs**, rather than when the container constructs the service.
4. Bean naming/type/qualifier details leak into business logic, inviting ad-hoc fallbacks or repeated lookups.
5. When every class calls `getBean`, understanding dependency relationships and scope across the object graph becomes harder.

That is the **Service Locator** pattern inside a business class, running counter to “dependencies are supplied to the object”. It does not automatically break functionality, yet it typically reduces testability and implementation substitutability.

Do not confuse this with **`main` or a boundary adapter calling `getBean(CheckoutService.class)` once** to kick off a use case: that is a lookup at the **composition root / entry point**, not business logic hunting for hidden internal dependencies.

## 3. Good Contracts Reflect What the Service Needs

### 3.1. Two Small Contracts

The order-intake service needs these operations:

~~~java
public interface InventoryPort {
    boolean reserve(String sku, int quantity);
}

public interface ReceiptPort {
    void publish(String orderId);
}
~~~

This is an API illustration; the complete Java 17 program declares both interfaces in `ContractDemo` in section 5.

The `InventoryPort.reserve` contract is defined as:

- Return `true` if enough stock is available and reservation succeeds.
- Return `false` if stock is insufficient; in the demo, quantity remains unchanged.
- For invalid inputs, the caller/model must validate; real adapters should also guard invariants.
- For a real backend, policies for concurrent reservation, idempotency, and network/database errors must also be specified.

The `ReceiptPort.publish` contract notifies after a successful reservation. It does **not** force the service to know about email or a specific message broker. In production, reliability, retries, and failure semantics must also be defined; the demo clearly notes this limitation.

**A contract does not always have to be a Java interface.** Injecting a concrete class is fine when it is a sensible, stable dependency that does not need multiple adapters. However, small interfaces are very useful at the boundary between business logic and infrastructure, especially for swapping in fakes in unit tests.

### 3.2. Avoid Interfaces That Merely “Rename a Technology”

Example of a poor contract:

~~~java
interface InventoryPort {
    java.sql.ResultSet executeSql(String sql);
}
~~~

This is an illustrative excerpt. Despite the name `InventoryPort`, it still forces the service to know SQL and `ResultSet`; that is not a good business-oriented boundary.

Ask: “What does the consumer genuinely want to do?” If it is “reserve N units of inventory for a SKU”, `reserve(sku, n)` expresses intent far better than `executeSql(...)`.

An interface with dozens of unrelated methods also makes fakes and testing harder. Split interfaces around consumer needs (*interface segregation*) when the benefit is clear.

### 3.3. Constructor for Required Dependencies

~~~java
public CheckoutService(InventoryPort inventory, ReceiptPort receipt) {
    this.inventory = java.util.Objects.requireNonNull(inventory);
    this.receipt = java.util.Objects.requireNonNull(receipt);
}
~~~

This snippet is implemented in the runnable file in section 5. Both fields are declared `final` because the service does not need to swap dependencies after construction. When a dependency is required, a constructor fails early if omitted; using an optional setter for it risks leaving the object in an invalid state.

**DI does not require Spring.** Constructor injection is simply how an object receives dependencies from whoever creates it. Spring Core Container automates configuration and manages the bean graph; it did not invent the principle of “receiving dependencies via constructor”.

## 4. Before and After: Who Controls Implementation Selection?

| Question | Looking Up / Creating Collaborators Inside Service | Injecting by Contract |
| --- | --- | --- |
| Which classes does the service know? | Concrete adapters or Spring context APIs | The interfaces/abstractions it actually needs |
| Who chooses the adapter? | Business service | `main`, factory, Spring configuration |
| Are dependencies visible? | Easily hidden inside methods or a singleton registry | Directly visible in the constructor |
| What must unit tests do? | Spin up real I/O, mock the container, or add workarounds | Pass plain Java fake implementations |
| Switching database/email? | May require modifying the service | Swap the adapter and wiring if the contract holds |
| When a dependency is missing? | May fail late inside a method branch | Constructor or bean initialization fails early |
| Does it add automatic transactions/HTTP? | No | Also no; separate infrastructure is needed |
| Who manages collaborator lifecycle? | Easily scattered | Composition root/container has a clear place |

Do not claim “you will never edit a single line of code again”: if business requirements or contract semantics change, the service must still change. The benefit is **reducing the blast radius of swapping how a capability is implemented**, not denying real business changes.

## 5. Complete Java 17 Example: Contract-First and Fake Testing

First run completely in Java 17 to prove DI **does not depend on Spring**. The Java file in this section is reused directly in the Maven/Spring example in section 6, avoiding any duplicate business service copy.

### 5.1. Structure

~~~text
contract-di-demo/
├── pom.xml                         # added for Spring in section 6
└── src/
    └── main/
        └── java/
            └── demo/
                ├── ContractDemo.java
                └── SpringWiringDemo.java  # added in section 6
~~~

Create `src/main/java/demo/ContractDemo.java`:

~~~java
package demo;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.ArrayList;

public final class ContractDemo {
    private ContractDemo() {}

    public record Order(String id, String sku, int quantity) {
        public Order {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id is required");
            }
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku is required");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
        }
    }

    public interface InventoryPort {
        boolean reserve(String sku, int quantity);
    }

    public interface ReceiptPort {
        void publish(String orderId);
    }

    // In-memory demo adapter; does not replace a real database.
    public static final class InMemoryInventory implements InventoryPort {
        private final Map<String, Integer> available = new HashMap<>();

        public InMemoryInventory(Map<String, Integer> initial) {
            Objects.requireNonNull(initial, "initial");
            available.putAll(initial);
        }

        @Override
        public boolean reserve(String sku, int quantity) {
            Integer current = available.get(sku);
            if (current == null || current < quantity) {
                return false;
            }
            available.put(sku, current - quantity);
            return true;
        }
    }

    // Demo adapter: emits events as console lines.
    public static final class ConsoleReceipt implements ReceiptPort {
        @Override
        public void publish(String orderId) {
            System.out.println("EVENT " + orderId);
        }
    }

    public static final class CheckoutService {
        private final InventoryPort inventory;
        private final ReceiptPort receipt;

        public CheckoutService(InventoryPort inventory, ReceiptPort receipt) {
            this.inventory = Objects.requireNonNull(inventory, "inventory");
            this.receipt = Objects.requireNonNull(receipt, "receipt");
        }

        public String place(Order order) {
            Objects.requireNonNull(order, "order");
            if (!inventory.reserve(order.sku(), order.quantity())) {
                return "REJECTED " + order.id();
            }
            receipt.publish(order.id());
            return "ACCEPTED " + order.id();
        }
    }

    public static void main(String[] args) {
        // Plain Java composition root: concrete adapters chosen outside the service.
        InventoryPort stock = new InMemoryInventory(Map.of("BOOK", 3));
        ReceiptPort receipts = new ConsoleReceipt();
        CheckoutService service = new CheckoutService(stock, receipts);

        System.out.println(service.place(new Order("O-1", "BOOK", 2)));
        System.out.println(service.place(new Order("O-2", "BOOK", 2)));

        // Fake used directly in tests without Spring, DB, or email.
        List<String> events = new ArrayList<>();
        InventoryPort alwaysAvailable = (sku, quantity) -> true;
        ReceiptPort fakeReceipt = events::add;
        CheckoutService tested =
                new CheckoutService(alwaysAvailable, fakeReceipt);

        String testResult = tested.place(new Order("T-1", "PEN", 1));
        System.out.println("TEST_ACCEPTED " + testResult);
        System.out.println("TEST_EVENTS " + events);

        if (!"ACCEPTED T-1".equals(testResult)
                || !events.equals(List.of("T-1"))) {
            throw new AssertionError("Unexpected collaborator calls");
        }
        System.out.println("TEST PASS");
    }
}
~~~

### 5.2. `javac`/`java` Commands

Open a terminal in `contract-di-demo`, requiring JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/ContractDemo.java
java -cp out demo.ContractDemo
~~~

**Exact stdout of the plain Java program:**

~~~text
EVENT O-1
ACCEPTED O-1
REJECTED O-2
TEST_ACCEPTED ACCEPTED T-1
TEST_EVENTS [T-1]
TEST PASS
~~~

Explanation:

1. `Map.of("BOOK", 3)` supplies 3 units in stock. Order `O-1` requests 2 units: `reserve` decrements stock to 1, then `ConsoleReceipt.publish` prints `EVENT O-1`.
2. `place` returns `ACCEPTED O-1`; `main` prints the returned value after the call completes.
3. Order `O-2` requests 2 more while only 1 remains: `reserve` returns `false`; the service returns `REJECTED O-2` **without emitting an event**.
4. The test uses an `InventoryPort` lambda always returning `true` and a `ReceiptPort` lambda recording order IDs into `events`.
5. The `tested` service shares identical code with the production service, yet receives **different collaborators**. `TEST_EVENTS [T-1]` verifies the notification went through the fake, with no `EVENT T-1` line.
6. `List.of("T-1")` is the expected list; `AssertionError` is thrown only if behavior is wrong. Passing prints `TEST PASS`.

**Key takeaway:** `CheckoutService` only calls `inventory.reserve` and `receipt.publish`. It does not instantiate `InMemoryInventory`, does not call `new ConsoleReceipt`, and never imports Spring. Choosing implementations happens in `main`.

### 5.3. Evaluating the Safety of This Example

- `InMemoryInventory` uses a mutable `HashMap` and is **not thread-safe**; under concurrent requests, stock counts could corrupt without proper synchronization or a real database.
- The demo does not handle duplicate order IDs, reservation expiration, or retries: those are critical rules in real systems outside this lesson's minimal contract.
- If `receipt.publish` throws an exception **after `reserve`**, stock has already been decremented. Plain Java does not roll back automatically; Spring DI also does not add database transactions on its own.
- A `boolean reserve` is too simplistic for many real systems, yet fits focusing on the DI boundary; in production, a reservation ID and richer statuses may be needed.
- Input validation on `Order` preserves invariants, yet adapters must still guard themselves when invoked by other code; do not treat the demo as protection against passing negative quantities straight into an adapter.

## 6. Same Business Class: Spring Only Replaces the Assembly Step

Once the plain Java program runs, leave `ContractDemo.java` untouched. Now simply add Spring configuration and a main class so **the container decides the object graph**, without editing `CheckoutService`'s implementation.

### 6.1. Maven Configuration

Spring Framework 6.2.0 is compatible with Java 17. The lesson runs on `spring-context`, **without Spring Boot**, a web server, AOP, or a database. Create `pom.xml` in `contract-di-demo`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>contract-di-demo</artifactId>
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
                    <mainClass>demo.SpringWiringDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. `@Configuration` and `@Bean` with Interface Parameters

Create `src/main/java/demo/SpringWiringDemo.java`:

~~~java
package demo;

import java.util.Map;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class SpringWiringDemo {
    private SpringWiringDemo() {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public ContractDemo.InventoryPort inventory() {
            return new ContractDemo.InMemoryInventory(
                    Map.of("BOOK", 3));
        }

        @Bean
        public ContractDemo.ReceiptPort receipt() {
            return new ContractDemo.ConsoleReceipt();
        }

        @Bean
        public ContractDemo.CheckoutService checkoutService(
                ContractDemo.InventoryPort inventory,
                ContractDemo.ReceiptPort receipt) {
            return new ContractDemo.CheckoutService(inventory, receipt);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            // Reasonable lookup at the startup boundary to invoke an entry-point service.
            ContractDemo.CheckoutService service =
                    context.getBean(ContractDemo.CheckoutService.class);

            System.out.println("SERVICE_BEANS "
                    + context.getBeanNamesForType(
                            ContractDemo.CheckoutService.class).length);

            System.out.println(service.place(
                    new ContractDemo.Order("S-1", "BOOK", 1)));
            System.out.println(service.place(
                    new ContractDemo.Order("S-2", "BOOK", 3)));

            System.out.println("SAME_BEAN "
                    + (service == context.getBean(
                            ContractDemo.CheckoutService.class)));
        }
    }
}
~~~

From the `contract-di-demo` directory containing `pom.xml`, run:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Stdout printed by `SpringWiringDemo` itself in exact order:**

~~~text
SERVICE_BEANS 1
EVENT S-1
ACCEPTED S-1
REJECTED S-2
SAME_BEAN true
~~~

`mvn -version` and Maven/plugins may print additional version details, dependency download progress, or logs. The block above lists **stdout intentionally produced by the application code**, without claiming the terminal will contain only those lines.

### 6.3. Tracing the Container Mechanism

1. `AnnotationConfigApplicationContext(AppConfig.class)` reads `@Configuration` and `@Bean` metadata and instantiates non-lazy singletons during refresh.
2. The `inventory` bean exposes an `InventoryPort`, backed by `InMemoryInventory` with 3 BOOK units initially.
3. The `receipt` bean exposes `ReceiptPort`, backed by `ConsoleReceipt`.
4. `checkoutService(InventoryPort inventory, ReceiptPort receipt)` declares its two dependencies by **parameter type**, without calling `getBean` inside the factory body.
5. Spring resolves the matching beans and invokes the factory method to instantiate `CheckoutService`. Inside the service, fields remain the two Java interfaces.
6. `main` calls `getBean(CheckoutService.class)` to obtain **an entry point**. That is the right place to touch the context. Subsequent business execution runs via `service.place`; the service **holds no `ApplicationContext`**.
7. Order `S-1` reserves 1 unit, leaving 2; prints `EVENT S-1` then `ACCEPTED S-1`. `S-2` requests 3, so it is rejected without emitting an event.
8. `CheckoutService` defaults to singleton within the context, so the second lookup returns the same reference and prints `SAME_BEAN true`.
9. `try-with-resources` closes the context; Spring executes appropriate cleanup callbacks for beans it manages.

**`@Autowired` is not required on `CheckoutService`'s constructor** in this example because the bean is created via a `@Bean` factory method receiving dependencies. Nor do you need `@Service` on the business class or component scanning enabled; `@Bean` already registers the instance with the container.

### 6.4. What If You Want `@Component` and Automatic Constructor Injection?

An alternative (not used simultaneously with `@Bean checkoutService` unless you want duplicate beans) is marking the class as a component:

~~~java
@Component
public final class CheckoutService {
    private final InventoryPort inventory;
    private final ReceiptPort receipt;

    public CheckoutService(InventoryPort inventory, ReceiptPort receipt) {
        this.inventory = inventory;
        this.receipt = receipt;
    }
}
~~~

This is an **illustrative alternative design snippet**, not an edit to `ContractDemo.java` in section 5. With component scanning enabled on the right package and beans for both interfaces present, Spring can pick the **single constructor** without `@Autowired` (in modern Spring Framework). Then the business class carries a Spring annotation, yet still never calls `getBean` itself.

If the goal is keeping the business layer completely unaware of Spring, `@Bean` configuration as in the main example fits better; both are valid DI approaches, and no mechanism forces every contract-implementing class to be a `@Component`.

## 7. Common Mistake: Seeing an Interface While Still Locked to an Adapter

Example:

~~~java
final class NotActuallyDecoupled {
    private final InventoryPort inventory =
            new InMemoryInventory(java.util.Map.of("BOOK", 3));
}
~~~

This is **non-standalone illustrative code**: even though the field has type `InventoryPort`, the class still decides `new InMemoryInventory`. Consequently, changing the adapter still requires modifying the consuming class.

For contract-based injection, **the constructor receives `InventoryPort`** rather than instantiating it. Do not confuse “a field declared with an interface type” with “letting external code pick the implementation”.

Likewise, a class taking an `ApplicationContext context` parameter and calling `getBean(InventoryPort.class)` in every method still knows more about container internals than necessary, even without naming concrete adapter classes.

## 8. Missing or Multiple Beans Implementing the Same Contract

### 8.1. No Candidate

If Spring needs to create `CheckoutService` via `@Bean checkoutService(InventoryPort,ReceiptPort)` while the context has not registered a `ReceiptPort`, bean initialization fails with a dependency error such as `UnsatisfiedDependencyException`. For non-lazy singletons, the failure typically surfaces **during context refresh**, before `main` ever calls `getBean(CheckoutService.class)`.

This is generally better than failing late inside a branch where the service dynamically looks up `ReceiptPort`. Still, remember that Spring cannot detect every business or resource error via DI alone.

### 8.2. Two Implementations for the Same Interface

Suppose both `ConsoleReceipt` and `EmailReceipt` exist as `ReceiptPort` beans. Spring cannot know which bean to inject without a single selection rule.

One explicit choice in Java configuration:

~~~java
@Bean
CheckoutService checkoutService(
        InventoryPort inventory,
        @Qualifier("consoleReceipt") ReceiptPort receipt) {
    return new CheckoutService(inventory, receipt);
}
~~~

This is **illustrative**, assuming the matching types and bean names are defined. Requires importing `org.springframework.beans.factory.annotation.Qualifier`.

- `@Qualifier` narrows bean candidates at the designated injection point.
- `@Primary` can mark one bean as the default preferred candidate.
- If you want to use **all** implementations (e.g., multiple notification channels), inject `List<ReceiptPort>` or `Map<String,ReceiptPort>` and build an explicit strategy rather than arbitrarily picking the first bean.
- If selection depends on per-order runtime data (email vs. SMS), that is a **business strategy/router** requirement. `@Primary` does not choose dynamically based on per-request data.

**One interface does not guarantee only one bean exists.** Always plan for names/qualifiers or an explicit strategy as the module grows.

## 9. Scope, Lifecycle, and Why You Shouldn't Look Up Beans Per Request

Spring beans default to `singleton` scope, typically one instance per bean definition in each container. Calling `getBean(InventoryPort.class)` repeatedly on a singleton does not allocate a new adapter each time; yet scattered lookups still create coupling and hide dependencies.

With `prototype`, calling `getBean` can produce a new object on each request. That is one scenario that tempts developers to pass the whole `ApplicationContext` into a service to “grab prototypes itself”.

There is usually a better option: pass a **factory/provider with a clear contract** or `ObjectProvider<T>` at the appropriate infrastructure layer, depending on intent.

Illustrative example:

~~~java
public interface TaskSessionFactory {
    TaskSession newSession();
}

public final class TaskExecutor {
    private final TaskSessionFactory sessions;

    public TaskExecutor(TaskSessionFactory sessions) {
        this.sessions = sessions;
    }

    public void execute() {
        TaskSession session = sessions.newSession();
        // Use the session according to its defined lifecycle.
    }
}
~~~

This is **illustrative code**, missing the `TaskSession` definition. The idea: when business logic needs “create a new session”, declare a **factory contract**. The factory's adapter can use Spring's `ObjectProvider<TaskSession>` or another allocation mechanism, without business logic needing to know `getBean("taskSession")`.

Reasonable exceptions for direct lookup include:

- `main` or a startup class retrieving an entry-point service.
- Framework/infrastructure code such as factories, plugin registries, or extension processors that intentionally interact with the container.
- Cases genuinely requiring dynamic resolution, isolated cleanly inside a dedicated adapter rather than scattered across the domain.

Do not turn “avoid Service Locator in business logic” into a dogma of “`getBean` is strictly forbidden everywhere”; what matters is **location and degree of coupling**.

## 10. Spring-Independent Tests and Container Wiring Tests

### 10.1. Business Unit Tests

`ContractDemo.main` already used fakes for both interfaces. A real unit test suite (JUnit or another framework) can split cases into:

- **Happy path:** inventory returns true, receipt is invoked exactly once with the exact ID, result is accepted.
- **Insufficient stock:** inventory returns false, receipt is not invoked, result is rejected.
- **Invalid input:** `new Order("X", "BOOK", 0)` throws `IllegalArgumentException`.
- **Missing dependency:** `new CheckoutService(null, receipt)` throws `NullPointerException` in the constructor.
- **Collaborator failure:** if inventory throws an exception, receipt does not run; if receipt throws after reserve, an explicit recovery policy is required.
- **Implementation swap:** replacing fakes with real adapters requires no change to how the service calls the contract.

These tests **do not need to boot Spring**. That is a major payoff of having the service accept interfaces via constructor without importing `ApplicationContext`.

### 10.2. Configuration Integration Tests

To verify the container wires beans properly, build a context from `AppConfig`, retrieve `CheckoutService`, and run a use case. With multiple profiles or implementations, test that missing-dependency or ambiguity cases fail early as expected.

Do not write every unit test by booting a full Spring context when the code under test is pure Java business logic; doing so slows tests down, obscures failures, and couples tests to external configuration unnecessarily.

### 10.3. Do Not Confuse DI with Transactions or Business Consistency

Constructor injection only defines **who uses which dependency**. If a use case must update a database and emit a message without losing events, use transactions/outbox/idempotency per an appropriate architecture. `@Bean` and `@Autowired` **do not automatically** make reserve and publish atomic together.

## 11. Swapping Implementations per Environment

The `InventoryPort` contract allows swapping adapters via Spring configuration. Example:

~~~java
// Illustrative configuration example, not a standalone runnable file.
@Bean
InventoryPort inventory(DataSource dataSource) {
    return new JdbcInventory(dataSource);
}
~~~

This snippet requires defining `JdbcInventory`, configuring a `DataSource`, and adding a real JDBC driver; it **cannot** run with just the `spring-context` dependency from the main example.

Common ways to select adapters:

1. **Per-environment `@Bean` declarations**: local runs use in-memory storage, production uses JDBC or an API client.
2. **`@Profile` / `@Conditional`**: register beans based on profile/condition; verify candidate dependencies and actual runtime environment.
3. **`@Primary` / `@Qualifier`**: pick a default or specific candidate when multiple implementations share a type.
4. **Dedicated factory configuration**: if an adapter needs credentials or client pools, keep construction and lifecycle in configuration/infrastructure.
5. **Adapters behind business interfaces**: avoid injecting `DataSource` or `ApplicationContext` straight into services just to pick adapters internally.

Swapping implementations does not guarantee equivalent behavior if semantics change. A new adapter must uphold what the contract promises: when `reserve` returns true/false, what side effects occur, and how errors are reported.

## 12. Detailed Design Principles

### 12.1. Dependency Inversion Principle (DIP) and DI

- **DIP** is a design principle: high-level modules should not tightly depend on low-level infrastructure modules; both should depend on appropriate abstractions.
- **DI** is a technique for supplying dependencies to an object from outside, achievable in plain Java or with a container such as Spring.
- **IoC container** is a tool that organizes object creation, configuration, and lifecycle; it is not synonymous with DIP or DI.
- **Interface** is a Java language mechanism for describing contracts; it does not create DI by itself.

You can use constructor injection with a **concrete class** and still be doing DI; conversely, you can declare an interface yet instantiate its implementation inside the service, keeping coupling intact. Design quality depends on **responsibility boundaries**, not interface count alone.

### 12.2. Dependencies Should Be “Only What You Need”

If a service only needs to check stock levels, do not force it to depend on a warehouse management interface with a hundred methods. Create a minimal consumer-tailored contract, such as `InventoryQuery`, when beneficial.

There is no reason to turn every value object like `Order`, `Money`, or `Address` into singleton Spring beans. They hold per-use-case data and are instantiated along their own business lifecycle.

### 12.3. The Composition Root Is Allowed to Know Concrete Implementations

The composition root has every right to know both `InMemoryInventory` and `CheckoutService`, because its job is **assembling the object graph**. In Spring, `@Configuration`/`@Bean` in the infrastructure layer is one way to express that composition root.

Do not misapply “the domain must not know concrete adapters” into “configuration must not know adapters either”, or nothing will be left to decide which implementation gets used.

## 13. Common Mistakes and How to Spot Them

| Mistake / Symptom | Understanding and How to Fix |
| --- | --- |
| Calling `new JdbcRepository()` inside every service | The service is choosing infrastructure; inject collaborators from config |
| Changing field to an interface while still doing `new Concrete()` | An interface alone does not change where implementation choice happens |
| Injecting `ApplicationContext` across the domain | Encourages Service Locator; declare real dependencies in constructors |
| Assuming `getBean` is bad in every location | Lookups at entry points or infrastructure factories can be appropriate |
| Interfaces designed around SQL/client APIs | Contracts should express capabilities the consumer needs |
| Constructors with dozens of unrelated collaborators | Review service responsibilities; split use cases/aggregators |
| Missing bean only fails during a specific order flow | Check for hidden lookups/lazy dependencies; move required deps to constructors |
| `NoSuchBeanDefinitionException` | Check bean registration, type, active profiles, and context |
| `NoUniqueBeanDefinitionException` | Check candidates, `@Primary`/`@Qualifier`, or selection strategy |
| Manually instantiating a bean and expecting AOP/transactions | Objects outside the Spring container are not automatically proxied/intercepted |
| `@Bean` returns an interface yet code always looks up concrete class | Bean metadata/proxies/type exposure can break concrete lookups; prefer the registered contract |
| Treating singleton beans as automatically thread-safe | Scope does not guarantee concurrency safety; inspect mutable state |
| Fakes only assert that no exception was thrown | Assert return values, call counts, and exact arguments |
| Real adapter fails and assuming DI rolls back | Transactions/consistency are a separate mechanism |
| Service pulls prototypes via `getBean` every time | Consider an injected factory/provider with a clear contract |
| Putting `@Component` on every class in the project | Bean registration is only for objects the container must manage |

## 14. Exercises with Answers

**Exercise 1.** `CheckoutService` only needs to call `inventory.reserve`; why shouldn't it take `DataSource` directly and run SQL itself?

**Answer:** Then the service would have to know persistence details. `InventoryPort` captures the exact capability needed, while the adapter can use JDBC outside business logic.

**Exercise 2.** Changing a field from `JdbcInventory` to `InventoryPort` while keeping `new JdbcInventory()` inside the service—is that DI yet?

**Answer:** Not for this boundary's DI goal. The service still picks and constructs its collaborator; it should receive `InventoryPort` via constructor or another injection point.

**Exercise 3.** Does `main` calling `context.getBean(CheckoutService.class)` violate the rule against Service Locator?

**Answer:** Not necessarily. `main` is the entry point/composition boundary; one deliberate lookup to start a use case differs from business services repeatedly fetching hidden dependencies.

**Exercise 4.** Why is `ReceiptPort fakeReceipt = events::add` valid in Java 17?

**Answer:** `ReceiptPort` has one abstract method `void publish(String)`. The method reference to `List.add(String)` returns a boolean, yet Java allows value-returning invocations to satisfy `void`-returning functional interfaces by discarding the return value.

**Exercise 5.** If two beans share type `ReceiptPort`, will Spring reliably pick whichever was declared first?

**Answer:** No. An explicit selection rule is needed, such as qualifier/primary or deliberate multi-bean injection design.

**Exercise 6.** If a service takes `InventoryPort` and `ReceiptPort` via constructor, do unit tests need a Spring context?

**Answer:** No. Pass fake implementations in plain Java and assert outputs/calls.

**Exercise 7.** If you add a database adapter that changes `reserve`'s true/false policy, is the service guaranteed to stay correct?

**Answer:** No. Swapping implementations is only safe when contract semantics actually hold; testing the adapter is essential.

**Exercise 8.** If you need a fresh `TaskSession` object per execution, is injecting `ApplicationContext` into the domain the only solution?

**Answer:** No. You can inject a `TaskSessionFactory` interface or a provider wrapped inside an infrastructure adapter. The domain only needs the “create new session” capability.

**Exercise 9.** Why doesn't a Spring `@Bean` factory method violate “services should not `new` collaborators themselves”?

**Answer:** Configuration/composition root is responsible for instantiating and choosing implementations; calling `new` inside a factory method is appropriate. What to avoid is **business services** taking on that infrastructure responsibility.

## 15. Application Checklist

- [ ] List the collaborators a service genuinely needs to execute a use case.
- [ ] Define contracts around consumer business needs, not detailed SQL/SMTP/HTTP APIs.
- [ ] Place required dependencies directly in the constructor.
- [ ] Check for non-null/invariants when constructing the service as needed.
- [ ] Never `new` infrastructure adapters inside a service.
- [ ] Never scatter `ApplicationContext.getBean` calls across business methods.
- [ ] Let the composition root/`@Configuration` choose concrete adapters.
- [ ] Ensure each contract has the right matching bean or an explicit selection rule.
- [ ] Use fakes to unit test services without a Spring context.
- [ ] Test Spring wiring separately from business logic tests.
- [ ] When on-demand instance creation is needed, prefer a factory/provider contract over leaking container APIs into the domain.
- [ ] Identify scope and lifecycle for stateful collaborators and resources.
- [ ] Never assume DI provides transactions, locking, retries, or rollback.
- [ ] Test the semantics and error cases of each implementation, not merely that interfaces compile.
- [ ] Do not create unnecessary abstractions for every class just to “follow a pattern”.

### Spring Documentation References

- [Dependency Injection and Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [ApplicationContextAware and Coupling Limits](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html)
- [Java-based Bean Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java/basic-concepts.html)

**Conclusion:** With contract-based DI, `CheckoutService` receives `InventoryPort` and `ReceiptPort` from outside instead of creating or looking them up itself. Java constructor injection keeps dependencies explicit and unit testing easy; Spring Core Container simply replaces manual composition-root wiring with managed bean configuration and lifecycle. Service Locator has occasional utility at infrastructure boundaries, yet keep business classes free of container coupling when all they need are capabilities expressed as interfaces.