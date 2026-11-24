# `@DependsOn` and Why `@Order` Does Not Control the Creation Order of Every Bean — Spring Boot 3.3

## 1. Objective

When Spring Boot starts, the Spring IoC container registers **BeanDefinition**s, resolves dependencies, and initializes regular singletons during `ApplicationContext.refresh()`. Two annotations are very commonly misused:

- **`@DependsOn`**: declares that **the current bean depends on one or more other beans having finished initialization first**. Dependencies are specified by **bean name**. For container-managed singletons, this relationship also affects destruction order when the context closes.
- **`@Order`**: declares **priority** for Spring **sorting** mechanisms, such as injecting `List<Handler>`, executing multiple runners, or invoking certain callbacks. It does **not** guarantee that a singleton with a smaller order number will be **created before all** singletons with larger numbers.

This lesson helps you distinguish **bean definition registration order**, **instance creation order**, **task invocation order**, and **destruction order**; use DI, `@DependsOn`, `@Order`, and `@Lazy` properly; and understand their limits. The hands-on example uses **Java 21 and Spring Boot 3.3.13**.

## 2. Why is there no single global initialization order?

A simplified startup model:

```text
SpringApplication.run(...)
  |
  +-- Create and prepare ApplicationContext
  +-- Load primary sources
  +-- refresh()
  |     +-- Process @Configuration/@ComponentScan/@Bean
  |     +-- Register BeanDefinitions
  |     +-- Resolve dependency graph
  |     +-- Create regular non-lazy singletons
  |     |     +-- constructor/factory method
  |     |     +-- inject dependencies
  |     |     +-- BeanPostProcessors and init callbacks
  |     +-- Finish refresh
  |
  +-- ApplicationStartedEvent
  +-- ApplicationRunner / CommandLineRunner
  +-- ApplicationReadyEvent
```

This diagram is a conceptual model and does not list every Spring callback. There are `@Lazy` beans, `prototype` scope, request scope, or beans created only on demand; those beans are not necessarily initialized during refresh.

If bean B needs A via its constructor, Spring must resolve dependency A before completing B's creation:

```java
@Component
class BillingService {
    private final PaymentGateway gateway;

    BillingService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

This is **illustrative**: it requires declaring the `PaymentGateway` interface and an implementation bean. Constructor injection expresses the real dependency. Usually you **do not need** `@DependsOn` when the relationship is already expressed this way.

However, if C is unrelated to A or B, there is no general guarantee that C will be created before or after them. The order observed in one run can be influenced by definition registration and container implementation details; never build business logic on accidental order.

| Kind of order | Question to ask | Appropriate mechanism |
| --- | --- | --- |
| Definition registration | Which classes/configurations did Spring discover? | `@ComponentScan`, `@Import`, `@Configuration`, `@Bean` |
| Instance creation and init | Does bean B need bean A to finish initialization first? | Constructor DI and dependency graph; `@DependsOn` for indirect relationships |
| Sorting on consumption | Multiple strategy beans in `List<Strategy>`: which comes first? | `@Order`, `Ordered` |
| Invoking startup tasks | Which runner does Boot call first? | `@Order` or `Ordered` on runners |
| Bean destruction | Which bean must be destroyed before its dependency? | Dependency graph; `@DependsOn` for singletons |
| Lifecycle component start/stop | Which `SmartLifecycle` component starts/stops per phase? | `SmartLifecycle.getPhase()` and dependencies |

## 3. `@DependsOn`: meaning and scope

### 3.1. Primary semantics

Example:

```java
@Component("cacheBootstrap")
class CacheBootstrap {
}

@Component
@DependsOn("cacheBootstrap")
class ReportService {
}
```

This is a **Spring illustrative snippet**, requiring imports for `@Component` and `@DependsOn` if used. When the container prepares to create `reportService`, it ensures the bean with **exact name** `cacheBootstrap` is initialized first. Bean names are case-sensitive; do not confuse a bean name with a class name or package.

Multiple dependencies can be listed:

```java
@DependsOn({"schemaCheck", "cacheBootstrap"})
```

When creating the annotated bean, Spring initializes the listed beans before it. This **does not guarantee a fixed order for unrelated beans**, and you should not infer a global order from a single annotation.

### 3.2. When is it worth using?

`@DependsOn` is useful when a bean relies on the **initialization side effect** of another bean without a clear direct object dependency, for example:

- An infrastructure bean registers an internal resource or plugin **synchronously** in its init callback.
- A bean needs a configuration or schema check performed by another bean to finish before it initializes.
- A legacy system has an indirect startup relationship not yet refactored to interface/constructor injection.

Do not treat this as a replacement for services calling each other. If `ReportService` actually needs to call methods on `CacheBootstrap`, inject it via constructor; type constraints are clearer, testing is easier, and you avoid depending on bean-name strings.

### 3.3. Destruction order for singletons

For Spring-managed **singletons**, `@DependsOn` also typically establishes the reverse destruction relationship:

```text
Initialization:  cacheBootstrap init --> reportService init
Destruction:     reportService destroy --> cacheBootstrap destroy
```

This matters when the dependent bean's `@PreDestroy` callback still needs resources provided by the other bean. Spring does not manage the full destruction lifecycle of **prototypes** the way it does for singletons; do not apply this destruction rule to every scope.

### 3.4. Where is the annotation placed?

`@DependsOn` is supported on classes registered by Spring via **component scanning** or on **`@Bean` methods**. The metadata must be processed by the corresponding registration mechanism. If a class is registered via another mechanism such as XML, placing the annotation on the class may not take effect; in XML, use the `depends-on` attribute on the bean definition.

Example with `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
class InfraConfiguration {

    @Bean("schemaCheck")
    SchemaCheck schemaCheck() {
        return new SchemaCheck();
    }

    @Bean
    @DependsOn("schemaCheck")
    ReportJob reportJob() {
        return new ReportJob();
    }
}
```

**This is a non-standalone snippet**: you must define `SchemaCheck`, `ReportJob`, and import `@Configuration`, `@Bean`, and `@DependsOn`. When Spring creates `reportJob`, the `schemaCheck` bean must be initialized first.

If `SchemaCheck` merely spawns a background thread and returns, `@DependsOn` **does not wait** for that thread to finish. It guarantees that the **bean's initialization callback** completed, not that all external services or asynchronous tasks are ready. For real schema migrations, use proper migration tools along with readiness/timeouts.

## 4. `@Order`: choosing order when the framework needs to sort

`@Order` lives in `org.springframework.core.annotation`. A **smaller** number means **higher** priority in ordering mechanisms that support this annotation. Example:

```java
@Component
@Order(10)
class FastHandler implements Handler {
    @Override
    public String name() {
        return "fast";
    }
}

@Component
@Order(20)
class SlowHandler implements Handler {
    @Override
    public String name() {
        return "slow";
    }
}
```

**The snippet above requires the `Handler` interface and imports** if run separately; Section 5 provides a complete project. When Spring injects `List<Handler>`, the order is typically `[FastHandler, SlowHandler]` according to the metadata of beans matching the interface.

However, **the order of elements in the list does not prove the order in which constructors or `@PostConstruct` ran**. The framework can resolve/instantiate beans before sorting the list. The two behaviors are separate contracts.

### 4.1. Cases where `@Order` is useful

- Collection injection: `List<Strategy>`, `Strategy[]`, or injection points supporting ordering.
- Multiple `ApplicationRunner` and `CommandLineRunner` beans: Boot sorts runners to determine **the invocation order of `run(...)`**, not the constructor order of all beans.
- Certain event listeners, interceptors, handlers, and infrastructure components with their own ordering support.
- Annotating a `@Bean` method to influence the position of the bean instance inside an injected collection when supported by the framework.

If two elements share the same order value, do not assume the order between them is determined by class name. `@Order` can be combined with `Ordered`, though you must check the contract of each specific extension point.

### 4.2. Typical mistake

```java
@Component
@Order(1)
class A {
}

@Component
@Order(2)
class B {
}
```

You cannot conclude `A` is always initialized before `B` from those two annotations alone. No dependency has been declared between A and B.

If B needs A to finish initialization first, express the relationship via DI or `@DependsOn("a")` when it is truly a side-effect dependency. If you only need A used before B **when iterating over a list of strategies**, `@Order` is the right tool.

## 5. Complete runnable example — Java 21, Spring Boot 3.3.13

The non-web project below observes **two distinct contracts**:

1. `InvoiceService` has `@DependsOn("startupCache")`: cache must initialize before invoice. With singletons, invoice is destroyed before cache.
2. `List<TaskHandler>` is injected according to `@Order`: the runner prints `[fast, slow]`. We make **no conclusion** about the constructor order of the two handlers.

### 5.1. File structure

```text
bean-order-demo/
├── pom.xml
└── src/main/java/com/example/ordering/
    ├── BeanOrderApplication.java
    ├── StartupCache.java
    ├── InvoiceService.java
    ├── TaskHandler.java
    ├── FastTaskHandler.java
    └── SlowTaskHandler.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bean-order-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot 3.3 supports Java 21 and requires at least Java 17. `spring-boot-starter` suffices for a CLI program; no web server is needed. Imports `jakarta.annotation.PostConstruct` and `jakarta.annotation.PreDestroy` belong to the Jakarta namespace used with Spring Framework 6.

### 5.3. Infrastructure bean: `StartupCache.java`

**File `src/main/java/com/example/ordering/StartupCache.java`:**

```java
package com.example.ordering;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component("startupCache")
public class StartupCache {

    @PostConstruct
    public void init() {
        System.out.println("CACHE init");
    }

    @PreDestroy
    public void destroy() {
        System.out.println("CACHE destroy");
    }
}
```

`@Component("startupCache")` picks an explicit bean name. `@PostConstruct` is invoked when the bean initializes; `@PreDestroy` runs when Spring destroys the singleton while closing the context.

### 5.4. Dependent bean: `InvoiceService.java`

**File `src/main/java/com/example/ordering/InvoiceService.java`:**

```java
package com.example.ordering;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.context.annotation.DependsOn;
import org.springframework.stereotype.Component;

@Component
@DependsOn("startupCache")
public class InvoiceService {

    @PostConstruct
    public void init() {
        System.out.println("INVOICE init");
    }

    @PreDestroy
    public void destroy() {
        System.out.println("INVOICE destroy");
    }
}
```

The demo intentionally avoids injecting the `StartupCache` object to demonstrate dependency on an **initialization side effect**. In a real application, if `InvoiceService` calls cache APIs, inject the cache via constructor. Because of `@DependsOn`, `CACHE init` **must precede** `INVOICE init`; upon closing the context, `INVOICE destroy` **must precede** `CACHE destroy`.

### 5.5. Handlers and `@Order`

**File `src/main/java/com/example/ordering/TaskHandler.java`:**

```java
package com.example.ordering;

public interface TaskHandler {
    String name();
}
```

**File `src/main/java/com/example/ordering/FastTaskHandler.java`:**

```java
package com.example.ordering;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class FastTaskHandler implements TaskHandler {
    @Override
    public String name() {
        return "fast";
    }
}
```

**File `src/main/java/com/example/ordering/SlowTaskHandler.java`:**

```java
package com.example.ordering;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class SlowTaskHandler implements TaskHandler {
    @Override
    public String name() {
        return "slow";
    }
}
```

The two classes are independent in the dependency graph. `@Order` helps Spring sort implementations when injecting a collection, yet **does not** establish an initialization relationship between them.

### 5.6. Main class and runner

**File `src/main/java/com/example/ordering/BeanOrderApplication.java`:**

```java
package com.example.ordering;

import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BeanOrderApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(BeanOrderApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        // Close context after runner completes to observe destroy callbacks.
        try (ConfigurableApplicationContext context = app.run(args)) {
            // Spring Boot already invoked ApplicationRunner inside app.run(args).
        }
    }

    @Bean
    ApplicationRunner showHandlerOrder(List<TaskHandler> handlers) {
        return args -> {
            List<String> names = handlers.stream()
                    .map(TaskHandler::name)
                    .toList();
            System.out.println("ORDERED handlers: " + names);
        };
    }
}
```

Notes:

- `@SpringBootApplication` is in `com.example.ordering`, so component scanning finds the classes in the same package.
- `List<TaskHandler>` is a collection injection point; Spring sorts elements according to `@Order`.
- `ApplicationRunner` runs **after refresh** and before `ApplicationReadyEvent`; it does not dictate the creation order of every component.
- `try-with-resources` calls `ConfigurableApplicationContext.close()` when `run(...)` returns, letting the demo clearly observe `@PreDestroy` without forcibly killing the app.

### 5.7. Run and compare output

Requires JDK 21, Maven, and Maven dependencies available. Inside `bean-order-demo`:

```bash
java -version
mvn -version
mvn package
java -jar target/bean-order-demo-0.0.1-SNAPSHOT.jar
```

The five lines printed by the program, **ignoring Boot's banner and logs**, are:

```text
CACHE init
INVOICE init
ORDERED handlers: [fast, slow]
INVOICE destroy
CACHE destroy
```

Framework logs may appear in between; the block above presents **only the example's own lines**. Explanation:

- `CACHE init` before `INVOICE init`: due to `@DependsOn("startupCache")`.
- `ORDERED handlers: [fast, slow]`: due to sorting `List<TaskHandler>` based on `@Order(10)` and `@Order(20)`.
- `INVOICE destroy` before `CACHE destroy`: due to the singleton dependency relationship when closing the context.
- The code does not log handler constructors, because the sorted list output **says nothing about the creation order** of the two objects.

When reading the console, do not confuse a sorted collection's output with lifecycle logs. The two behaviors have completely different contracts.

## 6. Other lifecycles and limitations of both annotations

### 6.1. `@PostConstruct` / `@PreDestroy`

`@PostConstruct` runs after dependency injection and necessary bean preparation have taken place; `@PreDestroy` runs when the container destroys eligible managed beans. They do not establish an application-wide order on their own. Relative ordering **between beans** comes from the dependency graph or dedicated lifecycle contracts.

Spring Boot 3/Spring Framework 6 use `jakarta.annotation.PostConstruct` and `jakarta.annotation.PreDestroy`; legacy `javax.annotation` imports may not be compatible without separate legacy libraries.

### 6.2. `@Lazy` and scope

- `@Lazy` can defer singleton creation until requested.
- If an **eager** singleton has `@DependsOn("lazyDependency")`, Spring must create `lazyDependency` before creating the eager bean.
- If the bean carrying `@DependsOn` is itself lazy and nothing requests it, the annotation does not automatically force it to initialize at startup.
- `prototype` beans are created on demand; Spring does not manage prototype destroy callbacks the same way as singletons.

Thus you must separate “**when a bean is requested**” from “**dependency order while creating a bean**”.

### 6.3. `SmartLifecycle` and start/stop ordering

Some components, such as message consumers, need to be **started/stopped** after objects are created. `SmartLifecycle.getPhase()` has its own mechanism to coordinate start/stop by phase; that is separate from constructor or `@PostConstruct` order. Do not assume `@Order` on a component controls all `SmartLifecycle` phases.

### 6.4. Runners and listeners have their own ordering

When startup tasks need to run sequentially, `ApplicationRunner`/`CommandLineRunner` support `@Order` or `Ordered` so Boot orders **calls to `run(...)`** across runner beans. That order still does not tell you **when** the singleton runner beans themselves were **instantiated** relative to other beans.

Certain event listeners can use `@Order` to sort callbacks for the same event. Listener ordering cannot cause `ApplicationReadyEvent` to fire before `ApplicationStartedEvent`.

## 7. Common errors and misconceptions

| Scenario | Problem | How to resolve |
| --- | --- | --- |
| Putting `@Order(1)` on a bean to “init before” `@Order(2)` | `@Order` does not establish global startup relationships | Use DI or `@DependsOn` when a real dependency exists |
| `@DependsOn("StartupCache")` when bean name is `startupCache` | Bean name mismatch; names are case-sensitive | Check registered bean name and fix the annotation |
| Putting `@DependsOn` on a class not scanned/registered via component scan | Metadata may not be applied | Place on `@Bean` method or corresponding definition mechanism |
| A depends on B, B depends on A | Circular dependency; initialization cannot complete | Split responsibilities and eliminate the cycle |
| Using `@DependsOn` to wait for database/remote service readiness | Only ensures bean initialized, not external systems ready | Use real migrations, readiness probes, timeouts, and health checks |
| A's init method starts an async task and returns | B may initialize while the task is still unfinished | Wait for completion properly or coordinate startup explicitly |
| `@Lazy` does not initialize at startup | Bean has not been requested yet | Check lazy/eager settings and dependency graph |
| Two beans share the same `@Order` | Relative order is unspecified | Pick distinct order values if needed |
| `@PreDestroy` prints nothing | Context was killed or not closed as expected | Close context in tests/demos; check scope and shutdown mode |
| Tests assert incidental log order | Accidental log order does not prove a container contract | Test the dependency relationship or sorted collection directly |

### 7.1. Circular dependency configuration

```java
@Component("a")
@DependsOn("b")
class A {
}

@Component("b")
@DependsOn("a")
class B {
}
```

This is a **broken configuration pattern**, shown only for analysis. Spring can detect the circular dependency and throw an exception when attempting initialization. Do not resolve this by disabling cycle checks; redesign the relationship.

### 7.2. Establishing only local ordering, not system-wide ordering

If B has `@DependsOn("a")` while C is unrelated:

```text
A --> B      (B must initialize after A)
C            (independent)
```

Orders A-B-C, A-C-B, or C-A-B all satisfy A before B. **You cannot deduce C's position.** To add more constraints, you must have real dependencies to declare.

### 7.3. Distinguishing init-order tests from priority tests

For `@DependsOn`, verify in B's initialization callback that A's **synchronous** init work has already completed. For `@Order`, verify that the injected `List<Handler>` or runner invocation sequence matches the expected order. These are two different assertions; do not use one to prove the other.

## 8. Choosing in real projects

**Scenario 1 — `PaymentService` must call `PaymentGateway`:** constructor injection. Type-safe and testable; no redundant `@DependsOn` needed.

**Scenario 2 — `ReportService` depends on `SchemaRegistrar`'s init side effect:** consider `@DependsOn("schemaRegistrar")`, if there is no actual object dependency and the init work is synchronous. Document clearly why the dependency exists.

**Scenario 3 — 5 strategies implementing the same interface need priority by business rule:** `@Order` + inject `List<Strategy>` and iterate. Do not use this annotation to dictate creation order of all singletons in list order.

**Scenario 4 — two runners must execute task A then B before ready:** use `ApplicationRunner`/`CommandLineRunner` with `@Order` on the runners themselves, or model a real dependency where suitable. Boot runs runners after refresh, before ready.

**Scenario 5 — a message consumer and provider need phased start/stop:** use `SmartLifecycle` and appropriate dependencies. `@Order` does not manage these phases.

## 9. Self-check exercises

1. State the difference between definition registration order, instance creation order, and `List<Handler>` sorting order.
2. In the demo, why is `CACHE init` guaranteed before `INVOICE init`? Why is destruction reversed?
3. Why does `[fast, slow]` **not prove** `FastTaskHandler` was created before `SlowTaskHandler`?
4. Remove `@DependsOn("startupCache")` and rerun. Even if the log order stays the same, what is **no longer** guaranteed?
5. Change `FastTaskHandler`'s `@Order(10)` to `@Order(30)`. Predict and verify `List<TaskHandler>` when the runner executes.
6. Change `InvoiceService` to take `StartupCache` via constructor. Do you still need `@DependsOn`?
7. Rename the cache bean to `cacheBootstrap` while keeping `@DependsOn("startupCache")`. Why can startup fail?
8. Add `@Lazy` to `StartupCache` while keeping `InvoiceService` eager. What happens when invoice initializes?
9. If both are lazy and neither is requested, are the two init callbacks guaranteed to run at startup?
10. With `@DependsOn({"a","b"})` on C, can you assert A always initializes before B?
11. Write two `ApplicationRunner`s with `@Order(10)` and `@Order(20)`. Distinguish **runner invocation order** from **runner bean creation order**.
12. Why does `@DependsOn` not guarantee a background thread started by A has finished when B initializes?
13. When running the demo, why is closing `ConfigurableApplicationContext` needed to observe `@PreDestroy`?
14. When is `SmartLifecycle.getPhase()` more appropriate than `@Order` or `@DependsOn`?

**Success criteria:** run the demo, correctly explain all five output lines, choose DI/`@DependsOn`/`@Order` for their real purpose, and avoid inferring guarantees from incidental bean creation order.

## 10. Official documentation

- Spring Framework 6.1 — `@Order` and singleton startup: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/annotation/Order.html
- Spring Framework 6.1 — `@DependsOn` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DependsOn.html
- Spring Framework — Using depends-on: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html
- Spring Framework — Bean scopes and prototypes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — Java Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Boot 3.3 — SpringApplication and runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
