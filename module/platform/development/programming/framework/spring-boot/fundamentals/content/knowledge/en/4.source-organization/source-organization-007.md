# Package Boundaries Do Not Automatically Create Spring Context Boundaries

In a Spring Boot project, developers often create packages such as `controller`, `service`, and `repository`, or split by business domain into `order`, `inventory`, and `customer`. This division makes source code easier to read, search, and manage dependencies in. However, **each Java package does not automatically become a separate Spring container**. If beans across those packages are registered into the same `ApplicationContext`, they still belong to the same bean management space and can be wired together through dependency injection.

Distinguishing **Java code organization boundaries** from **Spring runtime boundaries** prevents two common misconceptions: assuming two packages automatically isolate one another, and assuming moving a class into another package will automatically create an independent sub-application.

## 1. Two Kinds of Boundaries with Different Responsibilities

### Packages Are Java's Unit of Organization and Access

In Java, a `package` declaration places a class name into a namespace:

```java
package com.example.store.order;

public class Order {
    // ...
}
```

Packages help:

- Avoid class name collisions, such as `order.Status` and `payment.Status`.
- Arrange classes by feature or architectural layer for readability and maintainability.
- Apply part of Java's access rules, particularly for members or classes with *package-private* visibility.
- Establish a structure that is easy to verify via conventions, code reviews, or architecture analysis tools.

A package is **not** an OS process, an independent class loader, a separate memory region, a separate Spring `ApplicationContext`, or a business authorization mechanism. Two `public` classes in two different packages can still import and call each other when dependencies and access rules permit.

### `ApplicationContext` Is Where Spring Manages Beans

An `ApplicationContext` is the central interface of the Spring container. It knows which bean definitions have been registered, creates and configures beans, wires dependencies, and provides container services such as events, lifecycle callbacks, and framework configuration integration.

A **bean** is an object managed by the Spring container. Beans can come from classes discovered by component scanning (`@Component`, `@Service`, `@Repository`, `@Controller`, ...) or from `@Bean` methods in a registered configuration class. Not every object created with `new` in the application automatically becomes a Spring bean.

Simple example:

```text
Java source packages                 Spring runtime
────────────────────                 ──────────────
com.example.store
├── order/
│   └── OrderService.java  ───────┐
├── inventory/                   │
│   └── InventoryService.java ───┼──> ApplicationContext
└── web/                         │       ├── orderService bean
    └── OrderController.java ────┘       ├── inventoryService bean
                                         └── orderController bean
```

Three different Java packages can contribute beans into **the same context**. The directory structure on the left merely describes how source code is organized; whether Spring registers beans on the right depends on startup configuration and bean registration mechanisms.

| Question | Decided by Java Package? | Decided by Spring Context / Configuration? |
|---|---|---|
| What is the class's fully qualified name? | Yes: `com.example.store.order.OrderService`. | No. |
| Where can a package-private class be accessed from? | Yes: Java access control. | Spring does not override Java rules. |
| Is the class instantiated as a bean? | Not directly. | Yes: component scan, `@Bean`, `@Import`, or another registration mechanism. |
| Can `OrderService` inject `InventoryService`? | Different packages do not forbid it by default. | Depends on available beans, types, qualifiers, and context configuration. |
| Across how many containers are beans managed? | Does not decide. | Determined by how the application creates/configures contexts. |
| Does it isolate data, network, or OS resources? | No. | A single context does not automatically create process/OS-level isolation either. |

## 2. How Does Spring Boot Create a Context by Default?

A typical startup class:

```java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

When `SpringApplication.run(...)` is called, Spring Boot prepares and starts an `ApplicationContext` suited to the application type and current configuration. In a typical Boot application, business beans in scanned packages are managed by that application's main context.

`@SpringBootApplication` combines core Boot application configuration capabilities, including **component scanning** and **auto-configuration**. Under default configuration, component scanning starts from the package containing the `@SpringBootApplication` class and descends into its subpackages.

Example:

```text
com.example.store
├── StoreApplication.java              <- application root package
├── order/
│   └── OrderService.java               <- scanned if it is an eligible component
├── inventory/
│   └── InventoryService.java           <- scanned if it is an eligible component
└── web/
    └── OrderController.java           <- scanned if it is an eligible component
```

The key point is that **component scanning determines which classes are considered for bean registration**, whereas **the context determines where beans are managed**. Expanding or narrowing the scan scope can change the set of beans in a context without creating a new context.

Beyond component scan, there are auto-configuration and other bean registration mechanisms. Therefore, you cannot conclude that every bean in the context must sit beneath `StoreApplication`'s package.

## 3. Example: The `order` Package Still Uses Beans from `inventory`

Suppose the project has packages `com.example.store.order` and `com.example.store.inventory`. To see the wiring clearly, create an inventory management service:

**`src/main/java/com/example/store/inventory/InventoryService.java`**

```java
package com.example.store.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    public boolean isAvailable(String sku) {
        return "SKU-001".equals(sku);
    }
}
```

Then create the order processing service:

**`src/main/java/com/example/store/order/OrderService.java`**

```java
package com.example.store.order;

import com.example.store.inventory.InventoryService;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final InventoryService inventoryService;

    public OrderService(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    public String placeOrder(String sku) {
        return inventoryService.isAvailable(sku)
                ? "ACCEPTED"
                : "OUT_OF_STOCK";
    }
}
```

What happens when launching `StoreApplication`?

1. The component scanner sees `InventoryService` and `OrderService` because they sit in subpackages of `com.example.store` and are annotated with `@Service`.
2. Spring registers the corresponding bean definitions in the application's context.
3. When creating `OrderService`, Spring looks up a bean of type `InventoryService` matching the constructor dependency.
4. `OrderService` receives that bean and can call `isAvailable(...)`, even though the two classes belong to different packages.

```text
com.example.store.order.OrderService
                │ constructor dependency
                ▼
com.example.store.inventory.InventoryService
                │
                ▼
          same Spring context
```

The `order` package does not own a separate container. Nor does `inventory` automatically hide beans from the rest of the application. The example above intentionally uses a direct dependency to clarify the mechanism; in a larger design, you may want to reduce this coupling using interfaces and architectural rules.

The `isAvailable` example only simulates data and is not an implementation of a real inventory system. What to observe is **how Spring wires the two beans**.

## 4. Changing Packages Can Affect Scanning, Not Create a New Context

Suppose you move `InventoryService` out into a **sibling** package instead of a subpackage:

```text
com.example
├── store/
│   ├── StoreApplication.java
│   └── order/OrderService.java
└── shared/
    └── InventoryService.java
```

If `StoreApplication` resides in `com.example.store`, default component scan configuration usually **does not discover** `com.example.shared.InventoryService`. The result when the context creates `OrderService` may be a missing-bean error for its constructor.

This is a **bean not found / not registered** error, not proof that `shared` gained an independent context. The Java files themselves can still compile if the classpath and Java access allow it; the failure happens when Spring resolves dependencies inside the container.

Several intentional ways to register a bean outside the default scan package:

**Approach A — Place the startup class in a suitable parent package.** If the project layout allows, placing `@SpringBootApplication` in `com.example` puts subpackages of `com.example` within default component scan scope. Weigh this carefully, as an overly broad scope can pick up unintended components.

**Approach B — Explicitly configure component scan scope.** For example:

```java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = {
        "com.example.store",
        "com.example.shared"
})
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

Adding `com.example.shared` to the scan still aims to **register additional beans into the running context**; it does not create a separate `SharedApplicationContext`. Note that `scanBasePackages` affects component scan and **does not automatically replace all discovery rules for JPA entities and Spring Data repositories**. If using JPA, also check configurations such as `@EntityScan`, `@EnableJpaRepositories`, and appropriate auto-configuration rules.

**Approach C — Explicit bean registration.** You can use `@Import` with an appropriate configuration/class, or declare `@Bean` inside an already registered `@Configuration`:

```java
package com.example.store;

import com.example.shared.InventoryService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryConfiguration {
    @Bean
    InventoryService inventoryService() {
        return new InventoryService();
    }
}
```

In this example, `InventoryService` is assumed to have a no-arg constructor as illustrated in the code, and `InventoryConfiguration`'s package sits within configuration scope. `@Bean` registers the object returned by the factory method into **the context containing that configuration**. Avoid simultaneously registering multiple beans for the same purpose via multiple mechanisms without a clear reason, as it can cause name collisions or ambiguity during injection.

Do not apply the approaches above mechanically just to "fix a scan error" before understanding your package structure goals. Placing packages and entry points sensibly is usually simpler than manually listing numerous packages.

## 5. Why `@Service`, `@Component`, or `@Configuration` Are Not Context Dividers

Another confusion comes from seeing different annotations and inferring that they belong to different containers.

| Annotation / Declaration | Primary Effect | Automatically Creates a New `ApplicationContext`? |
|---|---|---|
| `@Component` | Marks class as a component candidate for bean registration. | No. |
| `@Service` | Stereotype for a business component; a variant of `@Component`. | No. |
| `@Repository` | Stereotype for a data access class; may participate in exception translation when configured. | No. |
| `@Controller` / `@RestController` | Marks web/controller component for framework registration. | No. |
| `@Configuration` | Declares a bean configuration class; its `@Bean` methods can register beans. | No. |
| `@Bean` | Registers the object returned from a factory method into the container. | No. |
| `@ComponentScan` | Specifies how component candidates are scanned. | No. |
| `@Profile` / `@Conditional` | Conditions determining whether a configuration or bean is registered. | No. |
| `@Scope` | Specifies bean scope, such as singleton or prototype. | No. |

For instance, putting `@Configuration` in `com.example.store.payment` does not make Spring open a new context for the payment package. If the configuration class is registered in the main context, the beans from its `@Bean` methods also belong to that context.

**Bean scope is not a context boundary either**: ordinary `singleton` beans are managed per container defining that bean, while `prototype` can create multiple instances per request/lookup. Differences in bean lifecycle do not turn the bean's package into a new container.

## 6. How Do You Know Beans Share the Same Context?

When an application uses one main context, you can use `ApplicationContext` to inspect registered beans. In a test placed in the same root package `com.example.store`:

```java
package com.example.store;

import com.example.store.inventory.InventoryService;
import com.example.store.order.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;

@SpringBootTest
class StoreContextTests {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private OrderService orderService;

    @Autowired
    private InventoryService inventoryService;

    @Test
    void findsBothServicesFromTheApplicationContext() {
        assertNotNull(orderService);
        assertSame(inventoryService, context.getBean(InventoryService.class));
        assertSame(orderService, context.getBean(OrderService.class));
    }
}
```

This test illustrates how both services are retrieved from the test application's `ApplicationContext`. It assumes the Spring Boot/JUnit test dependencies are present and the beans from the earlier example are properly registered. In applications with multiple contexts arranged in a parent-child hierarchy, `getBean(...)` may find beans from the parent; to determine **where a bean is actually defined**, distinguish local context beans from beans inherited in the hierarchy.

Another way to observe is printing `context.getId()` or inspecting the list of bean definitions in a specific context. **Do not infer how many contexts exist merely by counting packages or counting `@Service` annotations.**

## 7. Are One JVM, One Application, and One Context Always the Same Thing?

Not entirely. These concepts sit at different layers:

- **JVM / Java process** provides the execution environment. One process can run code that creates multiple Spring contexts.
- **Spring Boot application** is the concept of bootstrapping and configuring an application. In the common execution path, it creates one primary context.
- **`ApplicationContext`** is the container managing a specific set of beans. Different contexts can live in the same process, and may even be arranged in a parent-child relationship.
- **Package** is only a naming and organizational structure for Java classes. It does not determine the number of processes, applications, or contexts.

Diagram distinguishing two scenarios:

```text
Common scenario:

Java process
└── JVM
    └── Spring Boot application
        └── ApplicationContext A
            ├── orderService  (order package)
            ├── inventoryService (inventory package)
            └── orderController (web package)

Separately configured scenario:

Java process
└── JVM
    ├── ApplicationContext A
    │   ├── bean in order package
    │   └── bean in shared package
    └── ApplicationContext B
        ├── bean in inventory package
        └── bean in shared package
```

Contexts A and B do not appear because source code was split into packages A and B. They only appear when the program or framework **actually instantiates multiple containers**. Classes in the same package can even be registered in two different contexts, producing two distinct bean instances. Hence, package names are insufficient to deduce bean instances or runtime lifecycles.

## 8. How Are Different Contexts Connected?

In advanced scenarios, Spring supports creating multiple contexts and can establish a **context hierarchy**:

```text
Parent ApplicationContext
├── sharedConfiguration
└── sharedService
          │
          └── parent visible to children
                   │
           ┌───────┴────────┐
           ▼                ▼
Child Context A       Child Context B
├── orderService      ├── inventoryService
└── orderController   └── inventoryController
```

With a hierarchy configured, a child context can normally look up beans in the parent unless shadowed by a local bean, whereas the parent does not automatically see beans that exist only in a child. Two child contexts also cannot directly see each other's local beans by default. Exact rules depend on how the bean factories/context hierarchy are configured and used.

Conversely, two independent contexts without a parent-child relationship do not automatically share a bean registry simply by running in the same JVM. Connecting them requires an explicit mechanism: sharing objects through intentional configuration, using API/service integration, or inter-component communication by design.

Creating multiple contexts carries overhead in configuration, lifecycle management, observability, and dependency resolution. For a basic Spring Boot application, **you do not need to create a new context just to separate the `order` package from `inventory`**. The usual goal of splitting packages is code organization and dependency control, which can be addressed at the source architecture level first.

## 9. Architectural Boundaries Must Be Protected by Design and Rules

Suppose the team wants the `order` and `inventory` features to remain relatively independent. Splitting into two packages is a helpful first step, yet folder conventions alone do not forbid unwanted dependencies:

```text
com.example.store
├── order/
│   ├── api/OrderFacade.java
│   ├── internal/OrderService.java
│   └── internal/OrderCalculator.java
└── inventory/
    ├── api/InventoryQuery.java
    └── internal/InventoryRepositoryAdapter.java
```

Names like `api` and `internal` convey design intent. Still, folder/package names alone **do not make Java prevent calls into `internal`** if classes and members remain `public` and the classpath permits it. Measures that help keep boundaries clearer include:

1. **Define explicit APIs**: other areas should depend on published interfaces or services rather than directly accessing internal implementation classes.
2. **Use Java access modifiers properly**: do not put `public` on every class unnecessarily; consider package-private for implementation detail classes.
3. **Enforce a consistent dependency direction**: avoid cycles like `order → inventory → order`; when collaboration is needed, design a suitable abstraction or orchestration flow.
4. **Set up architectural verification rules**: use static checks, dependency rule tests, or appropriate tools to catch boundary violations.
5. **Consider modularization when the problem truly calls for it**: Maven/Gradle subprojects, JPMS, or modular monolith approaches can make source and build boundaries sharper, each with its own trade-offs.

In the Spring ecosystem, **Spring Modulith** is one option that helps model and verify logical modules inside a single Spring Boot application. It does not mean each logical package/module gets its own separate `ApplicationContext`. The purpose of this approach is typically controlling structure and interactions within one application, not automatically splitting into multiple processes.

### Example API Boundary Between Two Packages

An inventory package can publish a simple interface:

```java
package com.example.store.inventory.api;

public interface InventoryQuery {
    boolean isAvailable(String sku);
}
```

Internal implementation:

```java
package com.example.store.inventory.internal;

import com.example.store.inventory.api.InventoryQuery;
import org.springframework.stereotype.Service;

@Service
class InventoryQueryService implements InventoryQuery {
    @Override
    public boolean isAvailable(String sku) {
        return "SKU-001".equals(sku);
    }
}
```

The order service only imports the interface:

```java
package com.example.store.order;

import com.example.store.inventory.api.InventoryQuery;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final InventoryQuery inventory;

    public OrderService(InventoryQuery inventory) {
        this.inventory = inventory;
    }

    public boolean canPlaceOrder(String sku) {
        return inventory.isAvailable(sku);
    }
}
```

As long as the root package is scanned and there is one eligible bean for `InventoryQuery`, Spring can inject that implementation into the constructor via the interface. Both still reside in **the same context**, yet at the source level, `order` is far less coupled to `inventory`'s implementation details.

In this example, `InventoryQueryService` is intentionally left package-private; code outside `inventory.internal` cannot reference that class directly as a normal Java type. Spring is still capable of registering non-`public` component classes under standard configuration. This is a **Java access boundary**, not a Spring context isolation mechanism or absolute security boundary.

## 10. Separating Packages Does Not Mean Separating Transactions, Data, or Security

When beans in `order` and `inventory` share one `ApplicationContext`, splitting package names **does not automatically provide**:

- Separate databases, separate schemas, or separate data access privileges.
- Independent transaction managers or per-package transaction boundaries.
- Thread pools, heaps, or JVM resources isolated per package.
- Separate authentication/authorization rules per package.
- Circuit breakers, timeouts, or network boundaries like those between services over HTTP.

For example, `@Transactional` acts on Spring-managed calls according to proxy/aspect mechanics and the corresponding transaction configuration; it does **not** give a method in `order` an independent transaction separate from `inventory` because of its package. If two services participate in the same transaction, the outcome depends on call flow, propagation, transaction manager, and datasource—not on package names.

Similarly, putting payment code in `com.example.store.payment` does not automatically shield it from unauthorized calls. Security boundaries require real authentication, authorization, access policies, and data controls. Package conventions only help developers know where to place those mechanisms.

## 11. Distinguishing Package Scan from Test Context Structure

Spring Boot Test can create separate **test ApplicationContexts** for different test configurations. For example:

- `@SpringBootTest` typically starts a Spring test context based on the application configuration to test broad integration.
- `@WebMvcTest` targets a slice of web MVC configuration; other service beans may not be loaded automatically and require appropriate test dependency provisioning.
- Different tests can reuse a context cached by Spring Test when configurations match, or create another context when configuration changes.

This **does not prove each package has its own context**. Spring Test determines test context scope by annotations, configuration, and caching rules—it does not automatically create one context for `order` and another for `inventory` just because they sit in two packages.

Therefore, when `OrderService` can inject `InventoryService` in the real application yet fails to inject it in a slice test, the cause likely lies in **test configuration scope**, not because packages isolated the two beans. Reading test annotations and loaded beans accurately helps diagnose the issue.

## 12. Symptoms Commonly Misinterpreted

| Situation | Easy-to-Make Misconception | Accurate Understanding |
|---|---|---|
| Moved `@Service` outside root package and startup reports missing bean. | "The new package opened a different Spring context." | The bean may be outside component scan; check registration mechanisms. |
| Two `@Service` beans in two packages inject each other. | "Spring connected two separate contexts." | They may belong to the same context and inject normally. |
| Two packages have the same repository style and same database. | "Each package will have its own repository/transaction." | Database/transaction boundaries are decided by explicit configuration, not by packages. |
| `@Configuration` placed under `config/payment`. | "This is the Payment Context." | This is a configuration class; beans are registered into the context containing that configuration. |
| Added `@ComponentScan` for package `shared`. | "Spring will create an additional Shared Context." | Spring expands component discovery scope for the context being configured. |
| An MVC test cannot see a service from another package. | "The two packages cannot communicate." | A slice test may intentionally load only a subset of beans. |
| A `public` class in `inventory.internal` is imported by `order`. | "The name `internal` forbids the dependency." | Java still permits access if visibility and dependencies allow it; enforce explicit architectural rules. |
| Two classes in the same package are registered in two contexts. | "There must only be one instance because they share a package." | Different contexts can hold independent bean instances based on configuration and scope. |

If you hit `NoSuchBeanDefinitionException` or `required a bean of type ... that could not be found`, check step by step whether the class is actually registered, the scan scope, `@Profile`/`@Conditional` conditions, bean configuration/imports, and which context type is running. **Do not start with the hypothesis that each folder/package is an independent container.**

## 13. Hands-On Exercises

### Exercise 1 — Two Packages, One Context

Create a Spring Boot project with root package `com.example.store`; add `InventoryService` and `OrderService` following section 3's example. Ensure the starter needed for the Spring context is present in the build file. Start the application or run section 6's test and confirm Spring can retrieve both services via constructor injection.

**Expected observation:** Two classes in two packages are registered in the same standard application context. Package relationships do not prevent dependency injection.

### Exercise 2 — Move a Service Outside Default Package Scan

Move `InventoryService` to `com.example.shared`. Keep `StoreApplication` in `com.example.store` and try running it. Observe the missing bean error when no other registration mechanism exists. Then use explicit scoped component scan or a valid bean declaration to restore the dependency.

**Question:** Which action changed **bean registration**? Did any step in this exercise automatically create an independent context?

### Exercise 3 — Restrict Dependencies at the Source Level

Change `OrderService`'s dependency from the concrete class `InventoryService` to the interface `InventoryQuery`, then place the package-private implementation in `inventory.internal`. Try writing code in package `order` that references the implementation class name directly. The Java compiler enforces visibility rules, while Spring can still inject the implementation via the interface if the bean is properly registered.

**Expected observation:** You can enforce access limits and dependency rules **without multiplying the number of Spring contexts**.

### Exercise 4 — Compare Application Context and Test Slice

Once you have learned Spring testing, use a `@SpringBootTest` test to retrieve `OrderService` and `InventoryService`. Next, create a `@WebMvcTest` test for a controller using `OrderService`; observe which beans are loaded and supply test dependencies appropriately. Explain the result using test configuration scope, not package counts.

## 14. The Right Mindset When Designing Spring Boot Structure

When asking "How should we separate `order` and `inventory`?", first identify **which boundary you actually want**:

| Goal | Typically Appropriate Tool / Idea |
|---|---|
| Easy-to-find code with clear names | Java packages by feature or layer. |
| Expose only specific APIs between parts | Interfaces, access modifiers, dependency rules, and architecture tests. |
| Reduce coupling between business modules | Modular monolith, clear module structure, and dependency checks. |
| Control which beans exist | Component scan, `@Bean`, `@Import`, conditional configuration. |
| Need multiple independently managed bean sets/lifecycles | Explicitly configure multiple `ApplicationContext`s, if truly needed. |
| Need process isolation, independent scaling/deployment | Separate runtime and deployment architecture with appropriate communication. |
| Need to protect data and endpoints | Authentication, authorization, and real access-control mechanisms. |

**A package is a source code organization tool. A Spring `ApplicationContext` is the runtime container managing beans.** Having multiple packages does not mean having multiple contexts, and having two beans in two packages does not stop Spring from injecting them within the same application. To have a boundary enforced for real, you must design and configure the mechanism matching that kind of boundary.
