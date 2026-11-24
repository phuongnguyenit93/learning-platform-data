# Retrieving a Bean by Type and Executing a Processing Flow

## 1. Objective

This Spring Core Container hands-on exercise does not stop at creating an `ApplicationContext`: we retrieve a top-level bean by **Java type** and actually invoke its use case.

Workflow:

1. Define a business class `OrderService` along with two collaborator contracts `OrderRepository` and `Notifier`.
2. Register the beans with `@Configuration`/`@Bean` so Spring wires the dependencies.
3. Start `AnnotationConfigApplicationContext`.
4. Call `context.getBean(OrderService.class)` to retrieve the service bean.
5. Call `service.place(request)` and observe persistence, notification, and the return value.
6. Close the context cleanly at the end of its lifecycle.

~~~text
main()
  |-- ApplicationContext(AppConfig)
  |       +-- OrderRepository -> InMemoryOrderRepository
  |       +-- Notifier        -> ConsoleNotifier
  |       +-- OrderService(repository, notifier)
  |
  +-- getBean(OrderService.class)
          |
          +-- place(OrderRequest)
               +-- repository.save(...)
               +-- notifier.notifyPlaced(...) [if newly saved]
               +-- return status
~~~

**Distinction:** the container creates/wires beans; **invoking a method** on the bean executes the business flow. This is a console application, not an HTTP endpoint, and there is no database transaction.

## 2. What Does `getBean(Class<T>)` Do?

Example:

~~~java
OrderService service = context.getBean(OrderService.class);
~~~

This is an **illustrative syntax snippet**, assuming `context` and `OrderService` are already defined. `ApplicationContext` provides `BeanFactory` lookup capabilities:

- One bean compatible with the requested type: returns the bean reference.
- No matching bean: may throw `NoSuchBeanDefinitionException`.
- Multiple matching beans without a unique candidate: may throw `NoUniqueBeanDefinitionException`.
- Bean or dependency creation fails: may encounter `BeanCreationException` or another injection error, sometimes **right at context startup** because non-lazy singletons are created during refresh.

`getBean` does not automatically scan all classes on the classpath and `new` an arbitrary class. To retrieve a bean, you must register appropriate configuration: `@Bean`, component scanning, or a bean definition.

| API | Meaning |
| --- | --- |
| `getBean(OrderService.class)` | Lookup by type; commonly used when one matching bean exists |
| `getBean("orderService")` | Lookup by name; return type is `Object` |
| `getBean("orderService", OrderService.class)` | Lookup by name and assert exact type |
| `getBeanNamesForType(OrderService.class)` | List bean names of the given type for inspection |
| `getBeanProvider(OrderService.class)` | Provider for deferred or dynamic lookup needs |

In the example, the default bean name is the `@Bean` method name; name and type are two distinct concepts. Normally you do not need lookup by name inside business code.

## 3. Use Case: Placing an Order

We simulate order processing in which:

- `OrderRequest` is a record holding order ID, product SKU, and quantity, validating input preconditions.
- `OrderRepository` defines the contract for saving and checking whether an ID already exists.
- `Notifier` defines the contract for notifying after a successful save.
- `OrderService` knows only the two contracts, received via constructor.
- `InMemoryOrderRepository` uses a `Map` for demo purposes; `ConsoleNotifier` prints to stdout.
- `AppConfig` decides the concrete implementations and creates the beans.
- `main` retrieves `OrderService` from the context and invokes the use case.

Simple processing rule: **if the ID is new, save and notify; if the ID already exists, return a duplicate status without notifying again**. Unlike `OrderStore.save(...)` in the contract-design lesson (which throws on duplicate IDs), `OrderRepository.save(...)` here returns a boolean so the service itself decides the `ALREADY_EXISTS` branch. The two contracts represent two different domain design choices.

Contracts:

~~~java
interface OrderRepository {
    boolean save(OrderRequest order);
    boolean contains(String id);
}

interface Notifier {
    void notifyPlaced(String id);
}
~~~

The block above is **illustrative only**, not standalone because `OrderRequest` is not defined here. The `save` contract specifies: return `true` when inserting a new ID, `false` when the ID already exists. Real systems may use richer return types or domain exceptions, but every implementation must preserve the same semantics.

| Component | Responsibility |
| --- | --- |
| `OrderService` | Executes the `save → notify` sequence and returns the result |
| `OrderRepository` | Persistence/lookup contract |
| `InMemoryOrderRepository` | Map-based storage implementation |
| `Notifier` | Notification dispatch contract |
| `ConsoleNotifier` | Console-printing implementation |
| `AppConfig` | Chooses and wires concrete collaborators |
| `main` | Starts the context and retrieves the entry-point bean |

Using interfaces here makes it easy to mock/fake the repository and notifier in unit tests. **Not every Spring dependency must have an interface**; a concrete class can also be injected when appropriate.

## 4. Runnable Spring Framework 7 / Java 17 Project

### 4.1. Setup

Requires JDK 17+ and Maven. The example uses Spring Framework `7.0.9` via the `spring-context` dependency; no Spring Boot, server, database, or AOP is used.

~~~text
first-bean-flow/
├── pom.xml
└── src/main/java/demo/FirstBeanFlow.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>first-bean-flow</artifactId>
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
                    <mainClass>demo.FirstBeanFlow</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Complete Java Class

Create `src/main/java/demo/FirstBeanFlow.java`:

~~~java
package demo;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class FirstBeanFlow {
    private FirstBeanFlow() {}

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

    public interface OrderRepository {
        boolean save(OrderRequest request);
        boolean contains(String id);
    }

    public interface Notifier {
        void notifyPlaced(String orderId);
    }

    public static final class InMemoryOrderRepository
            implements OrderRepository {
        private final Map<String, OrderRequest> orders =
                new LinkedHashMap<>();

        @Override
        public boolean save(OrderRequest request) {
            Objects.requireNonNull(request, "request");
            return orders.putIfAbsent(request.id(), request) == null;
        }

        @Override
        public boolean contains(String id) {
            return orders.containsKey(id);
        }
    }

    public static final class ConsoleNotifier implements Notifier {
        @Override
        public void notifyPlaced(String orderId) {
            System.out.println("NOTIFY " + orderId);
        }
    }

    public static final class OrderService {
        private final OrderRepository repository;
        private final Notifier notifier;

        public OrderService(OrderRepository repository, Notifier notifier) {
            this.repository = Objects.requireNonNull(repository, "repository");
            this.notifier = Objects.requireNonNull(notifier, "notifier");
        }

        public String place(OrderRequest request) {
            Objects.requireNonNull(request, "request");
            if (!repository.save(request)) {
                return "ALREADY_EXISTS " + request.id();
            }
            notifier.notifyPlaced(request.id());
            return "ACCEPTED " + request.id();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public OrderRepository orderRepository() {
            return new InMemoryOrderRepository();
        }

        @Bean
        public Notifier notifier() {
            return new ConsoleNotifier();
        }

        @Bean
        public OrderService orderService(
                OrderRepository repository, Notifier notifier) {
            return new OrderService(repository, notifier);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);

            System.out.println("SERVICE_BEANS "
                    + context.getBeanNamesForType(OrderService.class).length);
            System.out.println("SAME_SINGLETON "
                    + (service == context.getBean(OrderService.class)));

            OrderRequest request = new OrderRequest("O-101", "BOOK", 2);
            System.out.println(service.place(request));
            System.out.println(service.place(request));

            OrderRepository repository =
                    context.getBean(OrderRepository.class);
            System.out.println("STORED " + repository.contains("O-101"));
        }
    }
}
~~~

In the `first-bean-flow` directory, run:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Maven may download dependencies on the first run. **Stdout from the `println` statements in the program:**

~~~text
SERVICE_BEANS 1
SAME_SINGLETON true
NOTIFY O-101
ACCEPTED O-101
ALREADY_EXISTS O-101
STORED true
~~~

`mvn -version` and Maven/plugins may print version info and other logs; the six lines are **the output intentionally printed by the code**, not the entire terminal output in all environments.

### 4.3. Step-by-Step Trace

1. `AnnotationConfigApplicationContext(AppConfig.class)` processes the configuration, registers beans, and instantiates non-lazy singletons during refresh.
2. `orderRepository()` creates the repository; `notifier()` creates the notifier.
3. `orderService(OrderRepository, Notifier)` receives bean dependencies from Spring and creates the service. `main` does not need to look up each dependency first.
4. `getBean(OrderService.class)` returns the matching bean. With one service in the demo, it prints `SERVICE_BEANS 1`.
5. The service bean defaults to singleton within the context. Two lookups return the same reference, printing `SAME_SINGLETON true`.
6. First `place` call: the Map does not contain the ID yet, so `putIfAbsent` returns `null`; the service sends one notification and returns `ACCEPTED O-101`.
7. Second call: the repository returns `false` because of the duplicate ID; the service returns `ALREADY_EXISTS O-101` and **does not send a notification**.
8. `getBean(OrderRepository.class)` retrieves the same singleton repository injected into the service; `contains` returns `true`.
9. `try-with-resources` closes the context and allows Spring to run corresponding bean destruction callbacks.

**Example limitations:** `LinkedHashMap` only holds data in RAM, is neither thread-safe nor durable. There is no database transaction. If the notifier fails after the repository saves, data may already have changed; Core Container does not roll back automatically.

## 5. Retrieving Beans and Dependency Injection Are Two Different Tasks

`main` calls `getBean(OrderService.class)` at the **startup boundary**. That is a legitimate lookup. However, `OrderService` does not call `context.getBean(OrderRepository.class)` inside `place`.

Instead, dependencies are explicit in the constructor:

~~~java
public OrderService(OrderRepository repository, Notifier notifier) {
    this.repository = Objects.requireNonNull(repository);
    this.notifier = Objects.requireNonNull(notifier);
}
~~~

This snippet is extracted from the full runnable file. This approach enables unit tests with fakes while avoiding the **Service Locator** anti-pattern, which hides dependencies by letting every class hold the container and pull beans at call time.

Spring creates beans via `@Bean` factory methods, resolves parameters by type, and then calls the `OrderService` constructor. **Java still uses `new` inside configuration**; what is separated out is the decision of creating collaborators away from business logic.

No `@Autowired` is needed on `@Bean` parameters in this configuration. Nor is `@ComponentScan` needed since all three beans are explicitly declared.

## 6. Retrieving Beans When Multiple Candidates or Zero Candidates Exist

**Not found:** if you remove `@Bean orderService` and have no other component registration, `getBean(OrderService.class)` can throw `NoSuchBeanDefinitionException`. If a service dependency is missing, the error may already occur at context startup because non-lazy singletons are instantiated eagerly.

**Multiple candidates:** suppose two beans implement `Notifier`. When `OrderService` accepts `Notifier` via constructor, Spring may not know which bean to pick. Clear disambiguation rules are required using `@Qualifier`, `@Primary`, or explicit candidate configuration.

**Illustrative example, not part of Section 4's runnable file**:

~~~java
@Bean("consoleNotifier")
Notifier consoleNotifier() {
    return new ConsoleNotifier();
}

@Bean("otherNotifier")
Notifier otherNotifier() {
    return new OtherNotifier();
}
~~~

`OtherNotifier` is an undefined illustrative name. Two beans sharing an interface can cause `NoUniqueBeanDefinitionException`. Lookup by name and type resolves selection explicitly:

~~~java
Notifier chosen = context.getBean("consoleNotifier", Notifier.class);
~~~

Do not rely on “whichever bean is registered first will be picked.”

**Scope:** by default, a singleton bean is one instance per bean definition **within one context**. A prototype typically produces a new instance when requested. Injecting a prototype once into a singleton does not make the dependency refresh on every method call.

**Proxy:** if AOP or `@Transactional` is enabled later, the bean retrieved from Spring may be a proxy. When JDK dynamic proxies are used, lookup by interface is generally preferable to concrete implementation; class-based proxies have restrictions such as `final` methods or classes. This demo does not enable AOP.

## 7. Testing the Use Case Independently of Spring

Constructor injection lets you instantiate the service in plain Java, for example:

~~~java
java.util.List<String> sent = new java.util.ArrayList<>();

FirstBeanFlow.OrderRepository fakeRepository =
        new FirstBeanFlow.OrderRepository() {
            public boolean save(FirstBeanFlow.OrderRequest r) {
                return true;
            }
            public boolean contains(String id) {
                return false;
            }
        };

FirstBeanFlow.Notifier fakeNotifier = sent::add;

FirstBeanFlow.OrderService service =
        new FirstBeanFlow.OrderService(fakeRepository, fakeNotifier);

String result = service.place(
        new FirstBeanFlow.OrderRequest("T-1", "PEN", 1));

if (!"ACCEPTED T-1".equals(result)
        || !sent.equals(java.util.List.of("T-1"))) {
    throw new AssertionError("Unexpected call sequence");
}
~~~

This snippet illustrates writing a **test inside the same project**; it is not a standalone file with `main` and does not add lines to Section 4's stdout. To test the duplicate branch, the fake repository should return `false` when the ID already exists and assert the notifier is **not** called again.

Keep concerns separate: unit tests verify service logic with fakes; integration tests start the context to verify wiring; real database or message broker tests verify infrastructure.

## 8. Error Handling and Common Mistakes

| Situation | What to Check |
| --- | --- |
| Treating `getBean` like `new` | Beans must be registered/managed; lookup does not instantiate arbitrary classes |
| Calling `getBean` yields no business outcome | You must invoke a method on the service |
| `NoSuchBeanDefinitionException` | Wrong context, missing bean definition, wrong profile/scanning |
| `NoUniqueBeanDefinitionException` | Multiple candidates exist; specify the bean explicitly |
| `UnsatisfiedDependencyException` | A bean's dependency could not be resolved |
| `BeanCreationException` | Factory method, constructor, or init hook threw an exception |
| Instantiating via `new` outside container and expecting AOP/transactions | Instances outside the container are not automatically proxied |
| Confusing bean name with class name | Default `@Bean` name is normally the method name |
| Assuming singleton means thread-safe | Scope does not guarantee concurrency safety of a mutable Map |
| Repository saves then notifier fails | No automatic rollback; design a consistency strategy |
| Overusing `context.getBean` in every service | Hides dependencies; prefer constructor injection |

Do not catch exceptions from `getBean` to silently instantiate a fallback service manually without considering bean management and lifecycle goals.

## 9. Self-Practice Exercises

**1.** If you only retrieve `OrderService` without calling `place`, is any order saved by the use case?

**Answer:** No. The bean may already be instantiated, but `save` operations reside inside `place`.

**2.** Why are two result lines printed (`ACCEPTED` and `ALREADY_EXISTS`) yet only one `NOTIFY O-101` line?

**Answer:** The first call saves successfully and notifies. On the second call, the ID is duplicate, `save` returns `false`, and the service returns `ALREADY_EXISTS` immediately.

**3.** Will two calls to `getBean(OrderService.class)` always return the same reference?

**Answer:** Only under the singleton configuration used in this example. A prototype bean can return different instances.

**4.** Is calling `context.getBean("orderService", OrderService.class)` valid here?

**Answer:** Yes, because the factory method in `AppConfig` is named `orderService`, unless the bean name is customized.

**5.** If there are two `Notifier` beans, what should you fix?

**Answer:** Specify the selection explicitly using `@Qualifier`, `@Primary`, or appropriate configuration; avoid relying on registration order.

**6.** Is a Spring context required to unit test `OrderService`?

**Answer:** No. Dependencies are injected through the constructor, so tests can supply plain Java fakes.

## 10. End-of-Lesson Checklist

- [ ] JDK 17+, Maven, and `spring-context` are set up.
- [ ] File is placed at `src/main/java/demo/FirstBeanFlow.java` in package `demo`.
- [ ] `@Configuration` contains the three related beans.
- [ ] Context initializes cleanly with unambiguous dependencies.
- [ ] Service is retrieved via `getBean(OrderService.class)`.
- [ ] `service.place(request)` is invoked after lookup.
- [ ] Understand the `save → notify → return` flow and the duplicate branch.
- [ ] Distinguish application output from Maven logs.
- [ ] Close the context when finished.
- [ ] Do not mistake a `Map` for a database or expect Core Container to create transactions automatically.
- [ ] Test business logic with fakes and test wiring with a Spring context when needed.

**Conclusion:** `getBean(OrderService.class)` hands startup code the entry point to an **object graph assembled by Spring**. Creating and injecting dependencies is organized by the container; `OrderService` enforces business rules and coordinates the repository and notifier. Separating those roles properly is the core step of your first Spring application.